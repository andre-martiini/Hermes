"""Leitores puros dos documentos de sync já existentes hoje, convertendo cada
um em `IntegrationHealth` (P05 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, seção "P05 — Normalizar eventos e
saúde das integrações", continuação do passo 8: "Substituir zeros de
fallback por status de fonte; manter resumo parcial utilizável.", achado A09).

`autonomy/integrations.py` (P05 sub-entrega 2/N, passo 7) definiu a FORMA do
registro de saúde e a regra de derivação de status, mas nenhum trigger real
ainda persistia ou lia `IntegrationHealth` -- só ficou documentado, no
próprio módulo e no bloco da sub-entrega em docs/autonomia/execucao.md, QUAL
documento de sync já existente cada integração usa hoje: `system/sync`
(Calendar/Tasks, via `run_full_sync`/`main.py`), o doc próprio de contatos
(`CONTACTS_SYNC_STATE_DOC_ID` = `sync_contatos`, via
`_registrar_execucao_contatos`), `system/gmail_sync` (via
`_executar_sync_gmail_com_lock`) e `system/whatsapp_ingest` (cursor, via
`triage_whatsapp_messages`) -- SIPAC, finanças e repositório (GitHub) não têm
nenhum documento de sync persistido hoje.

Este módulo faz a PONTE entre a forma bruta desses quatro documentos (lidos
como `dict`, exatamente como `DocumentSnapshot.to_dict()` devolve) e
`montar_saude_integracao` -- ainda sem nenhum trigger/scheduler real
chamando isto (nenhum `main.py`/scheduler importa este módulo ainda; o
wiring de verdade -- decidir QUANDO recalcular, onde EXPOR o resultado
-- fica para uma sub-entrega futura, que também precisa fechar a tool
`consultar_saude_integracoes` da seção 6 do plano e o uso em
`obter_estado_atual`/`hermes_tools.py` para substituir os fallbacks de zero
hoje espalhados em `morning_summary.py`). Lógica pura -- recebe o `dict` já
lido e um `heartbeat_at` explícito, nunca acessa Firestore diretamente --
mesmo padrão incremental já usado no resto do pacote de autonomia."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from .integrations import IntegrationHealth, montar_saude_integracao

#: Nome de erro usado quando o doc de sync marca `status="error"` mas não
#: guarda nenhuma mensagem utilizável (não deveria acontecer hoje -- todo
#: escritor de `status="error"` também grava `error_message`/`erro` -- mas
#: `error_code` não pode ser string vazia, então um fallback explícito é
#: melhor do que um `ValueError` de `calcular_status_integracao` por causa de
#: um doc gravado por uma versão futura do escritor que omita a mensagem).
ERRO_SEM_MENSAGEM = "erro_sem_mensagem_no_doc_de_sync"

#: Thresholds por integração, justificados pela cadência real de cada
#: trigger hoje (não um valor arbitrário único como os DEFAULT_LIMITE_* de
#: `autonomy/integrations.py`, que são só um ponto de partida genérico):
#: - "calendar": `run_full_sync` roda a cada hora (`main.py`, scheduler
#:   "every 60 minutes") -- degradado após faltarem 2 ciclos (2h), já que um
#:   único ciclo perdido é esperado eventualmente (retry/lock ocupado) e não
#:   deve por si só virar alarme; indisponível após 6h, mesmo teto genérico
#:   de DEFAULT_LIMITE_INDISPONIVEL_SEGUNDOS.
#: - "contacts": só roda no máximo 1x a cada CONTACTS_SYNC_MIN_INTERVAL_S = 6h
#:   (`main.py::_contatos_devem_rodar`) -- um `last_success` de 5h59 é
#:   perfeitamente normal, então degradado precisa ficar bem acima de 6h
#:   (12h) e indisponível ainda mais generoso (48h), já que é uma integração
#:   de baixa prioridade (metadados de contato, não dados operacionais).
#: - "gmail": `gmail_sync_safety_net` roda a cada 4h como piso garantido
#:   (`main.py`, scheduler "every 4 hours"), além do webhook em tempo real
#:   quando habilitado -- degradado com folga acima do piso da rede de
#:   segurança (5h) para não confundir "webhook desligado, rede de segurança
#:   ainda não rodou" com degradação real; indisponível em 24h (problema do
#:   lado da API do Google costuma ser transitório).
#: - "whatsapp": cursor avançado dentro do mesmo ciclo horário de
#:   `run_full_sync` (branch `escopo_completo` que chama
#:   `triage_whatsapp_messages`) -- mesma cadência do Calendar, mesmos
#:   thresholds.
LIMITES_POR_INTEGRACAO: Mapping[str, tuple[float, float]] = {
    "calendar": (2 * 60 * 60, 6 * 60 * 60),
    "contacts": (12 * 60 * 60, 48 * 60 * 60),
    "gmail": (5 * 60 * 60, 24 * 60 * 60),
    "whatsapp": (2 * 60 * 60, 6 * 60 * 60),
}

#: Tolerância máxima de desvio de relógio que `_sem_referencia_futura` corta
#: (clamp) para `heartbeat_at` em vez de descartar a referência -- achado
#: real de revisão adversarial independente (P05 sub-entrega 3/N, 2ª
#: rodada): a primeira versão do clamp (ver `_sem_referencia_futura`) cortava
#: QUALQUER referência futura para `heartbeat_at`, sem limite de magnitude --
#: um campo corrompido gravado anos no futuro (bug de escritor, fuso errado,
#: campo trocado) seria silenciosamente reportado como `HEALTHY` com
#: `lag_seconds=0.0` até o relógio real alcançar aquele valor, mascarando uma
#: anomalia de dados real como "acabou de sincronizar" -- pior do que o
#: `ValueError` que o clamp existe para evitar, já que aquele pelo menos
#: tornava o problema visível. Acima desta tolerância, a referência é
#: descartada (vira `None`, ou seja, `UNKNOWN`) em vez de cortada -- ver
#: `_sem_referencia_futura`.
TOLERANCIA_RELOGIO_SEGUNDOS = 120


def _extrair_instante(valor: Any) -> datetime | None:
    """Converte um campo bruto de timestamp de um doc de sync em `datetime`
    tz-aware, ou `None` se ausente/ilegível.

    Aceita tanto `datetime` nativo (um `Timestamp` do Firestore já vem como
    `datetime` tz-aware quando lido pelo client -- é o caso de
    `system/whatsapp_ingest.last_processed_at`, copiado direto do campo
    `ingested_at` de `whatsapp_messages`) quanto string ISO 8601 (é o caso de
    `system/sync.last_success`/`finished_at`, `system/gmail_sync.last_success`
    e `sync_contatos.ultima_execucao`, todos gravados via `.isoformat()`).

    `datetime` NAIVE (sem `tzinfo`) é tratado como UTC -- mesmo padrão já
    usado em `main.py::is_remote_calendar_newer` para o mesmo tipo de
    inconsistência: `system/sync.last_success` é gravado com
    `datetime.now().isoformat()` (SEM `timezone.utc`, ao contrário de
    `finished_at`/`started_at` do mesmo doc, que usam
    `datetime.now(timezone.utc).isoformat()`) -- um resquício pré-existente
    do escritor em `main.py::run_full_sync`, não algo que este módulo de
    leitura pode corrigir na origem. Assumir UTC é a mesma correção que o
    resto do código já faz para esse campo específico; o ambiente de
    execução das Cloud Functions roda em UTC."""
    if isinstance(valor, datetime):
        return valor if valor.tzinfo is not None else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None
        if texto.endswith("Z"):
            texto = f"{texto[:-1]}+00:00"
        try:
            resultado = datetime.fromisoformat(texto)
        except ValueError:
            return None
        return resultado if resultado.tzinfo is not None else resultado.replace(tzinfo=timezone.utc)
    return None


def _error_code_de_mensagem(mensagem: Any) -> str:
    texto = str(mensagem).strip() if mensagem is not None else ""
    return texto if texto else ERRO_SEM_MENSAGEM


def _sem_referencia_futura(instante: datetime | None, heartbeat_at: datetime) -> datetime | None:
    """Protege contra o `ValueError` de `calcular_lag_segundos`/
    `montar_saude_integracao` quando a referência já extraída (tz-aware) é
    POSTERIOR a `heartbeat_at` -- achado real de revisão adversarial
    independente (P05 sub-entrega 3/N): `heartbeat_at` normalmente é
    capturado pelo chamador (`datetime.now(timezone.utc)`) ANTES de buscar o
    doc de sync no Firestore -- uma sincronização que termina bem no meio
    dessa janela (ou um simples desvio de relógio entre o processo que grava
    o doc e o que lê) produz exatamente essa condição, não um caso
    hipotético; nenhum teste anterior desta sub-entrega cobria isso.
    Diferente de `IntegrationHealth.__post_init__`, que deve falhar fechado
    quando alguém CONSTRÓI um registro à mão com dados inconsistentes (ver
    docstring de `autonomy/integrations.py`), estes leitores recebem dados
    brutos de fora e não podem derrubar quem os chama por causa de um
    desvio de relógio de poucos segundos.

    Dentro de `TOLERANCIA_RELOGIO_SEGUNDOS`, corta (clamp) a referência em
    `heartbeat_at`, equivalente a `lag_seconds=0.0` (a leitura mais fresca
    que faz sentido reportar). ACIMA da tolerância, descarta a referência de
    todo (devolve `None`, que os leitores levam a `UNKNOWN` em vez de
    `HEALTHY`) -- achado real de uma 2ª rodada de revisão adversarial
    independente sobre a 1ª versão deste clamp, que cortava QUALQUER
    distância sem limite: um campo corrompido gravado muito no futuro (bug
    de escritor, fuso errado, campo trocado) seria silenciosamente reportado
    como `HEALTHY` até o relógio real alcançar aquele valor -- mascarando
    uma anomalia de dados real como "acabou de sincronizar", pior do que o
    `ValueError` que o clamp existe para evitar (que ao menos tornava o
    problema visível). `UNKNOWN` é o resultado correto para dado não
    confiável: nem "saudável" (não sabemos se está), nem uma afirmação de
    erro específica (não sabemos a causa) -- mesmo espírito de
    "indisponibilidade não é dado vazio" do módulo base, aplicado aqui a
    dado não confiável em vez de dado ausente."""
    if instante is None:
        return None
    delta = (instante - heartbeat_at).total_seconds()
    if delta <= 0:
        return instante
    if delta <= TOLERANCIA_RELOGIO_SEGUNDOS:
        return heartbeat_at
    return None


def saude_calendar(doc: Mapping[str, Any] | None, heartbeat_at: datetime) -> IntegrationHealth:
    """`system/sync` -- Calendar/Tasks, escrito por `main.py::run_full_sync`.

    `error_code` só quando `status == "error"` -- `status == "partial"` não
    existe para este doc (só `run_full_sync`, que não distingue sucesso
    parcial: ou completa tudo, ou marca `error`). Usa `last_success` (não
    `finished_at`) como referência de frescor: `finished_at` também é gravado
    em `status == "error"` (fim da rodada, com ou sem sucesso), então usá-lo
    misturaria "quando a última rodada terminou" com "quando a última
    LEITURA confiável aconteceu" -- exatamente a distinção que
    `last_success_at` existe para preservar.

    LIMITAÇÃO CONHECIDA (achado real de revisão automática do Codex,
    comment_id=4125412121, P2, na PR desta sub-entrega): `last_success` é do
    job GLOBAL de `run_full_sync`, não específico do Calendar --
    `sync_google_calendar` (`main.py`, por `calendar_id`) captura falhas
    comuns de listagem (qualquer erro exceto credencial revogada) e apenas
    loga e CONTINUA para o próximo calendário (`continue`, sem propagar),
    então uma falha persistente ao listar um ou mais calendários não impede
    o job global de terminar com `status="completed"` e `last_success`
    fresco. Um Calendar genuinamente quebrado (não por credencial revogada)
    pode ser reportado como `HEALTHY` por este leitor. Correção de verdade
    exige um sinal de sucesso/erro PRÓPRIO do Calendar, que não existe hoje
    -- fora do escopo desta sub-entrega (leitor puro dos docs já existentes,
    sem novo escritor); ver `pendencias` do bloco desta sub-entrega em
    docs/autonomia/execucao.md.

    CONFIRMAÇÃO ADICIONAL (achado real de revisão automática do Codex,
    comment_id=4131386963, P2, na PR que fechou a tool
    `consultar_saude_integracoes`, seção 6 do plano): o mesmo doc
    `system/sync` também é escrito por `sync_gmail_bills_callable`
    (`main.py`, sincronização MANUAL de boletos do Gmail via app) --
    `sync_ref.update({"status": "completed", "last_success": ...})` ao
    final, SEM nenhuma sincronização de Calendar envolvida. Ou seja, o
    escritor que "refresca" `last_success` nem sempre é `run_full_sync`
    (job periódico que ao menos tenta o Calendar) -- pode ser uma ação de
    usuário sobre boletos, completamente alheia ao Calendar. Mesma causa
    raiz do achado anterior (o timestamp é do doc, não da integração),
    mesma correção pendente (sinal próprio do Calendar), mesmo motivo de
    não ser corrigido aqui."""
    doc = doc or {}
    status = doc.get("status")
    error_code = _error_code_de_mensagem(doc.get("error_message")) if status == "error" else None
    limite_degradado, limite_indisponivel = LIMITES_POR_INTEGRACAO["calendar"]
    return montar_saude_integracao(
        integration="calendar",
        heartbeat_at=heartbeat_at,
        last_success_at=_sem_referencia_futura(_extrair_instante(doc.get("last_success")), heartbeat_at),
        error_code=error_code,
        limite_degradado_segundos=limite_degradado,
        limite_indisponivel_segundos=limite_indisponivel,
    )


def saude_contacts(doc: Mapping[str, Any] | None, heartbeat_at: datetime) -> IntegrationHealth:
    """`sync_contatos` (`CONTACTS_SYNC_STATE_DOC_ID`) -- só guarda
    `ultima_execucao`, sem nenhum campo de erro/status (uma falha durante o
    sync de contatos só aparece nos `logs` de `system/sync`, nunca neste
    doc) -- `error_code` é sempre `None` aqui; a única fonte de sinal é a
    frescor de `ultima_execucao`."""
    doc = doc or {}
    limite_degradado, limite_indisponivel = LIMITES_POR_INTEGRACAO["contacts"]
    return montar_saude_integracao(
        integration="contacts",
        heartbeat_at=heartbeat_at,
        last_success_at=_sem_referencia_futura(_extrair_instante(doc.get("ultima_execucao")), heartbeat_at),
        error_code=None,
        limite_degradado_segundos=limite_degradado,
        limite_indisponivel_segundos=limite_indisponivel,
    )


def saude_gmail(doc: Mapping[str, Any] | None, heartbeat_at: datetime) -> IntegrationHealth:
    """`system/gmail_sync`, escrito por `main.py::_executar_sync_gmail_com_lock`.

    `status == "partial"` (rodou até o fim, mas alguma etapa interna falhou
    -- `etapas_com_erro` -- sem que `last_success` avance) NÃO vira
    `error_code`: o próprio comentário do escritor em `main.py` diz que isso
    "não conta como sucesso", então `last_success` fica parado no valor
    anterior -- o cálculo de frescor sozinho já degrada o status conforme o
    tempo passa, sem precisar de um `error_code` artificial para um estado
    que não é bem "indisponível", é "sucesso represado". Só `status ==
    "error"` (falha que interrompeu a rodada inteira) vira `error_code`.
    Ignora deliberadamente o doc `gmail_watch` (`last_notification_at`/
    `watch_active`) nesta sub-entrega -- combinar dois docs num único sinal
    de saúde é decisão de escopo própria (um `watch` inativo com a rede de
    segurança de polling ainda saudável não é necessariamente uma
    integração degradada), deixada para uma sub-entrega futura dedicada."""
    doc = doc or {}
    status = doc.get("status")
    error_code = _error_code_de_mensagem(doc.get("error_message")) if status == "error" else None
    limite_degradado, limite_indisponivel = LIMITES_POR_INTEGRACAO["gmail"]
    return montar_saude_integracao(
        integration="gmail",
        heartbeat_at=heartbeat_at,
        last_success_at=_sem_referencia_futura(_extrair_instante(doc.get("last_success")), heartbeat_at),
        error_code=error_code,
        limite_degradado_segundos=limite_degradado,
        limite_indisponivel_segundos=limite_indisponivel,
    )


def saude_whatsapp(doc: Mapping[str, Any] | None, heartbeat_at: datetime) -> IntegrationHealth:
    """`system/whatsapp_ingest` -- só um cursor (`last_processed_at`, lido
    aqui; `last_processed_doc_id`, desempate por doc_id do cursor composto
    desde a correção de colisão de milissegundo em `_next_cursor_after_batch`,
    é irrelevante para saúde/frescor), sem nenhum campo de status/erro
    (confirmado em `whatsapp_ingest.py`: toda gravação deste doc via
    `cursor_ref.set(..., merge=True)` sempre inclui `last_processed_at`,
    exceto quando a mensagem retida mais antiga já é o primeiro documento do
    lote -- aí nada é gravado nesta passada) -- `error_code` é sempre `None`;
    a única fonte de sinal é a frescor do cursor.

    LIMITAÇÃO CONHECIDA (achado real de revisão automática do Codex,
    comment_id=4125412129, P2, na PR desta sub-entrega): `last_processed_at`
    é a idade da ÚLTIMA MENSAGEM processada, não da última tentativa de
    sincronização bem-sucedida -- `triage_whatsapp_messages`
    (`whatsapp_ingest.py`) retorna sem avançar o cursor sempre que a query
    não encontra nenhum documento novo (`whatsapp_messages` vazio desde o
    cursor atual). Uma conta legitimamente ociosa (ninguém manda mensagem
    por horas) pode ser reportada como `DEGRADED`/`UNAVAILABLE` mesmo com o
    polling horário rodando perfeitamente -- cursor de dados não distingue
    "sync quebrado" de "nada de novo para sincronizar". Correção de verdade
    exige um sinal de tentativa/sucesso SEPARADO do cursor de dados (ex.:
    `last_attempt_at` gravado a cada rodada do polling, sucesso ou não), que
    não existe hoje -- fora do escopo desta sub-entrega (leitor puro dos
    docs já existentes, sem novo escritor); ver `pendencias` do bloco desta
    sub-entrega em docs/autonomia/execucao.md."""
    doc = doc or {}
    limite_degradado, limite_indisponivel = LIMITES_POR_INTEGRACAO["whatsapp"]
    return montar_saude_integracao(
        integration="whatsapp",
        heartbeat_at=heartbeat_at,
        last_success_at=_sem_referencia_futura(_extrair_instante(doc.get("last_processed_at")), heartbeat_at),
        error_code=None,
        limite_degradado_segundos=limite_degradado,
        limite_indisponivel_segundos=limite_indisponivel,
    )


def saude_sem_sincronizacao_persistida(integration: str, heartbeat_at: datetime) -> IntegrationHealth:
    """SIPAC, finanças e repositório (GitHub) não têm NENHUM documento de
    sync persistido hoje (confirmado por busca no código -- nenhum grep por
    `sipac`/`SIPAC` combinado com `sync`/`system.` encontra escritor
    nenhum) -- sempre `UNKNOWN`, nunca um registro ausente nem zero (mesma
    exigência de "indisponibilidade não é dado vazio" do módulo base).
    Existe só para essas três integrações terem uma entrada explícita e
    consistente em qualquer lugar que agregue `IntegrationHealth` de todas
    as integrações (ex.: uma futura `consultar_saude_integracoes`), em vez
    de silenciosamente não aparecerem na lista."""
    return montar_saude_integracao(integration=integration, heartbeat_at=heartbeat_at)
