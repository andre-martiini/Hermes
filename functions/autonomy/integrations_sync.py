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
`montar_saude_integracao`. Nenhum `main.py`/scheduler importa este módulo --
a leitura sob demanda vive em `tools/hermes_tools.py`
(`_coletar_saudes_integracoes`), que agora alimenta tanto a tool
`consultar_saude_integracoes` (seção 6 do plano) quanto `obter_estado_atual`
(substituindo ali o fallback de zero que existia antes para esta fonte --
`morning_summary.py` continua com os fallbacks próprios dela, fora do escopo
deste módulo). Lógica pura -- recebe o `dict` já lido e um `heartbeat_at`
explícito, nunca acessa Firestore diretamente -- mesmo padrão incremental já
usado no resto do pacote de autonomia."""

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

    `error_code` vem de `last_calendar_error_at`/`last_calendar_error_message`
    (sinal PRÓPRIO do passo Calendar/Tasks) quando o doc já tem o campo novo;
    senão cai para `status == "error"` do doc inteiro -- `status == "partial"`
    não existe para este doc (só `run_full_sync`, que não distingue sucesso
    parcial: ou completa tudo, ou marca `error`). Ver LIMITAÇÃO RESOLVIDA
    abaixo para o porquê dos dois caminhos.

    LIMITAÇÃO RESOLVIDA (achado real de revisão automática do Codex,
    comment_id=4131386963, P2, na PR que fechou a tool
    `consultar_saude_integracoes`, seção 6 do plano): `system/sync` também é
    escrito por `sync_gmail_bills_callable` (`main.py`, sincronização MANUAL
    de boletos do Gmail via app) -- `sync_ref.update({"status": "completed",
    "last_success": ...})` ao final, SEM nenhuma sincronização de Calendar
    envolvida. Usar `last_success` como referência de frescor do Calendar
    deixava a saúde reportada vulnerável a um refresh causado por uma ação
    totalmente alheia (boletos). `run_full_sync` agora grava
    `last_calendar_success_at` logo após o passo Calendar/Tasks (chamadas a
    `sync_google_calendar`/`sync_google_tasks_push`/`sync_google_tasks_pull`)
    terminar sem exceção -- mesmo padrão de heartbeat PRÓPRIO já usado para o
    WhatsApp (`saude_whatsapp`/`last_query_success_at`, sub-entrega
    anterior). Este leitor prefere o campo novo; `last_success` continua como
    fallback só para o período de transição entre o deploy desta sub-entrega
    e a primeira rodada de sync seguinte (doc antigo, ainda sem o campo
    novo) -- durante essa janela a limitação antiga (refresh por boletos)
    ainda se aplica.

    LIMITAÇÃO PARCIALMENTE RESOLVIDA (achado real de revisão adversarial
    independente, confirmado lendo o corpo das 3 funções): "terminar sem
    exceção" sozinho é uma barra bem mais baixa do que "sincronizou de
    verdade". `sync_google_calendar` e `sync_google_tasks_push` (`main.py`)
    têm cada uma um único `except Exception` externo que só RE-propaga
    `GoogleAuthRevokedError` (credencial revogada) -- qualquer outro erro (API
    do Google fora do ar, erro de quota, exceção de bug no processamento,
    falha de escrita no Firestore) é só logado ("ERRO CAL"/"ERRO PUSH") e a
    função retorna normalmente; `sync_google_tasks_pull` não repropaga NADA,
    nem credencial revogada ("ERRO PULL", sempre retorna normalmente). A
    sub-entrega que introduziu o sinal de erro PRÓPRIO (ver LIMITAÇÃO
    RESOLVIDA abaixo) fechou boa parte desta lacuna sem mudar nenhuma das 3
    funções: `run_full_sync` agora varre as linhas que elas escreveram em
    `logs` durante o passo e trata qualquer "ERRO CAL"/"ERRO PUSH"/"ERRO PULL"
    encontrada no INÍCIO de uma linha (depois de remover o prefixo
    "[HH:MM:SS] " de `log_to_firestore`) como erro do passo, mesmo quando a
    função engoliu a exceção e retornou normalmente -- esses casos hoje gravam
    `last_calendar_error_at` (não mais um falso `last_calendar_success_at`).
    O que PERMANECE aberto, concretamente (achado real da mesma revisão, não
    hipotético): dois `except` POR ITEM dentro de `sync_google_tasks_push` e
    `sync_google_calendar` logam com um prefixo DIFERENTE e continuam o loop
    sem propagar -- `"[CAL][!] Falha ao sincronizar evento da tarefa '{title}':
    {ce}"` (uma tarefa específica) e `"[CAL][!] Falha ao listar agenda
    '{calendar_id}': {cal_err}"` (um `calendar_id` específico, quando há mais
    de um configurado). RESOLVIDO (P05 sub-entrega 15/N): `run_full_sync`
    agora reconhece também o prefixo "[CAL][!]" na mesma varredura (além de
    "ERRO CAL"/"ERRO PUSH"/"ERRO PULL") -- uma falha real e persistente em UM
    item (calendário OU tarefa, mas não todos) já não grava mais heartbeat de
    SUCESSO silenciosamente; grava `last_calendar_error_at` como qualquer
    outro erro engolido do passo, mesma agregação "pior resultado vence" já
    usada pelo resto deste mecanismo. O que PERMANECE aberto, sem mudança
    desta sub-entrega (ver LIMITAÇÃO CONHECIDA, AINDA ABERTA #3 abaixo): o
    sinal continua agregado ao passo Calendar/Tasks INTEIRO, não por
    `calendar_id`/tarefa individual -- decisão de produto própria, fora de
    escopo. Mais genericamente: um erro que não comece a mensagem com uma
    dessas 4 strings (um `except` futuro com texto diferente, ou um retorno
    silencioso sem log nenhum) continua indetectável por este mecanismo --
    ainda não é prova formal de que a listagem/gravação de eventos funcionou,
    só uma rede bem mais ampla do que "nenhuma exceção chegou até
    `run_full_sync`".
    `test_falha_no_calendar_nao_grava_heartbeat_proprio` (test_sync_custos.py)
    cobre o caso de exceção propagada (`GoogleAuthRevokedError` ou qualquer
    outra, via mock, inclusive com mensagem vazia);
    `test_erro_engolido_do_passo_calendar_grava_heartbeat_de_erro`
    (test_sync_custos.py) cobre o caso antes invisível, de erro logado no
    INÍCIO da mensagem mas não propagado;
    `test_titulo_de_tarefa_com_texto_de_erro_nao_e_falso_positivo`
    (test_sync_custos.py) cobre o falso positivo descartado por exigir o
    marcador no início (um título de tarefa contendo literalmente "ERRO CAL:"
    no meio de uma linha de SUCESSO não deve gravar erro);
    `test_erro_por_item_de_tarefa_grava_heartbeat_de_erro`/
    `test_erro_por_item_de_listar_agenda_grava_heartbeat_de_erro`
    (test_sync_custos.py, P05 sub-entrega 15/N) cobrem os dois casos antes
    invisíveis desta sub-entrega.

    LIMITAÇÃO RESOLVIDA (sub-entrega seguinte à anterior) -- `error_code`
    deixou de depender do `status`/`error_message` GLOBAIS ao ciclo inteiro de
    `run_full_sync` quando o doc já tem o par `last_calendar_error_at`/
    `last_calendar_error_message` (gravado por `main.py::run_full_sync` a
    CADA ciclo, logo após o passo Calendar/Tasks, erro OU `None`). Antes: se
    um passo SEM relação com Calendar e rodando DEPOIS dele no mesmo ciclo
    falhasse (ex.: `sync_allcare_portal_bills`, sem try/except próprio em
    `run_full_sync`), o bloco de erro geral gravava `status: "error"` e
    `error_message` desse passo alheio no MESMO doc -- sem apagar
    `last_calendar_success_at` -- e `calcular_status_integracao`
    (`autonomy/integrations.py`) forçava `UNAVAILABLE` sempre que `error_code`
    não era `None`, independente da frescor. Agora, com o campo novo presente,
    `error_code` só reflete um erro do PRÓPRIO passo Calendar/Tasks (inclusive
    os antes engolidos sem propagar, "ERRO CAL"/"ERRO PUSH"/"ERRO PULL",
    detectados varrendo os logs que o passo escreveu naquele ciclo -- ver
    `run_full_sync`) -- um Allcare que falhe depois não derruba mais a saúde
    reportada do Calendar. Mantém o MESMO padrão incremental de fallback já
    usado para a frescor: enquanto o doc não tiver `last_calendar_error_at`
    (período de transição, ciclo anterior ao deploy desta sub-entrega), cai
    para o `status`/`error_message` globais, idêntico ao comportamento
    anterior. `test_heartbeat_do_calendar_nao_depende_de_passos_posteriores`
    (test_sync_custos.py) cobre o doc bruto e o `IntegrationHealth` resultante
    deste cenário, agora confirmando a resolução em vez da limitação.

    LIMITAÇÃO CONHECIDA, AINDA ABERTA #3 (achado real de revisão automática
    do Codex, comment_id=4125412121, P2, na PR da sub-entrega que introduziu
    este módulo): o sinal não é específico de cada `calendar_id` --
    `sync_google_calendar` (`main.py`, por `calendar_id`) captura falhas
    comuns de listagem (qualquer erro exceto credencial revogada) e apenas
    loga e CONTINUA para o próximo calendário (`continue`, sem propagar).
    PARCIALMENTE RESOLVIDA (P05 sub-entrega 15/N): essa falha já não fica
    mais invisível -- desde que `run_full_sync` passou a reconhecer também o
    prefixo "[CAL][!]" (ver LIMITAÇÃO PARCIALMENTE RESOLVIDA acima), uma
    falha persistente ao listar um ou mais calendários (ou ao sincronizar
    uma tarefa específica) já marca `last_calendar_error_at` e, por
    extensão, o `status` agregado deste `IntegrationHealth` -- deixou de
    "não impedir o heartbeat de avançar". O que PERMANECE aberto: o sinal
    continua agregado (pior resultado entre TODOS os calendários/tarefas do
    ciclo vence, igual ao resto deste mecanismo), não um sinal POR
    `calendar_id`/tarefa -- correção de verdade nesse sentido mais fino
    exige decidir como agregar vários calendários num único
    `IntegrationHealth` com granularidade própria (ex.: expor QUAL
    `calendar_id` falhou, não só que algum falhou), decisão de produto
    própria, fora do escopo desta sub-entrega; ver `pendencias` do bloco
    desta sub-entrega em docs/autonomia/execucao.md."""
    doc = doc or {}
    status = doc.get("status")
    if "last_calendar_error_at" in doc:
        error_code = (
            _error_code_de_mensagem(doc.get("last_calendar_error_message"))
            if doc.get("last_calendar_error_at") is not None
            else None
        )
    else:
        error_code = _error_code_de_mensagem(doc.get("error_message")) if status == "error" else None
    limite_degradado, limite_indisponivel = LIMITES_POR_INTEGRACAO["calendar"]
    referencia = doc.get("last_calendar_success_at")
    if referencia is None:
        referencia = doc.get("last_success")
    return montar_saude_integracao(
        integration="calendar",
        heartbeat_at=heartbeat_at,
        last_success_at=_sem_referencia_futura(_extrair_instante(referencia), heartbeat_at),
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
    """`system/whatsapp_ingest` -- cursor de dados (`last_processed_at`,
    `last_processed_doc_id` como desempate, irrelevante para saúde/frescor) e,
    desde a correção abaixo, um heartbeat de SUCESSO DE CONSULTA
    (`last_query_success_at`) separado -- nenhum campo de status/erro existe
    neste doc (confirmado em `whatsapp_ingest.py`), então `error_code` é
    sempre `None`; a única fonte de sinal é a frescor.

    LIMITAÇÃO CONHECIDA E RESOLVIDA (achado real de revisão automática do
    Codex, comment_id=4125412129, P2, na PR da sub-entrega 3/N): usar só
    `last_processed_at` como referência de frescor confundia "sync quebrado"
    com "conta ociosa, nada novo para sincronizar" -- `triage_whatsapp_messages`
    só avança esse cursor quando a query encontra mensagem nova, então uma
    conta legitimamente ociosa por horas podia ser reportada como
    `DEGRADED`/`UNAVAILABLE` mesmo com o polling horário rodando
    perfeitamente. `triage_whatsapp_messages` agora grava
    `last_query_success_at` (`_query_success_heartbeat_write`) assim que a
    consulta a `whatsapp_messages` tem êxito (sem exceção), incondicional
    quanto a encontrar mensagem nova ou não -- cobre os caminhos de "nenhuma
    mensagem nova" e "triagem desligada" -- então é a referência de frescor
    preferida aqui. `last_processed_at` continua como fallback só para o
    período de transição entre o deploy desta sub-entrega e a primeira
    rodada de polling seguinte (doc antigo, ainda sem o campo novo).

    Deliberadamente NÃO é um heartbeat incondicional de "a função foi
    invocada" (achado real de revisão automática do Codex,
    comment_id=4147530697, sobre uma versão anterior desta correção que
    gravava o heartbeat ANTES da consulta, cobrindo inclusive uma consulta
    persistentemente quebrada): o valor repassado aqui para `last_success_at`
    -- e, por extensão, exposto pela tool `consultar_saude_integracoes` como
    "último sucesso" -- só avança quando a consulta em si é CONFIRMADA
    bem-sucedida, preservando o contrato de `last_success_at` (leitura
    confirmada, não mera tentativa).

    LIMITAÇÃO RESIDUAL, AINDA ASSIM (mesmo espírito das limitações
    documentadas em `saude_calendar`/`saude_gmail` acima): "consulta teve
    êxito" não é o mesmo que "ingestão está funcionando de ponta a ponta" --
    uma falha persistente DEPOIS da consulta (análise por IA sempre
    lançando exceção, gravação de digest/sugestão sempre falhando) não é
    capturada por este sinal e continuaria reportando `HEALTHY`. Escopo
    deliberado desta sub-entrega (só a consulta, o mesmo tipo de sinal que
    `last_success` já representa para `saude_calendar`/`saude_gmail`); um
    sinal de saúde fim-a-fim exigiria instrumentar cada etapa downstream
    separadamente, fora do escopo aqui."""
    doc = doc or {}
    limite_degradado, limite_indisponivel = LIMITES_POR_INTEGRACAO["whatsapp"]
    referencia = doc.get("last_query_success_at")
    if referencia is None:
        referencia = doc.get("last_processed_at")
    return montar_saude_integracao(
        integration="whatsapp",
        heartbeat_at=heartbeat_at,
        last_success_at=_sem_referencia_futura(_extrair_instante(referencia), heartbeat_at),
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
