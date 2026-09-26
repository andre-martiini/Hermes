"""Verificadores determinísticos de resultado (P04 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, seção 4.6 "Verificadores de
resultado" e passo 8 do pacote: "Implementar verificadores determinísticos
das primeiras operações: tarefa, artefato, consolidação e outbox").

D07 do plano: "Evidência define conclusão. Texto 'terminei' e sucesso HTTP
não bastam. Cada passo tem verificador tipado." Este módulo é a peça que
`autonomy/execution.py::registrar_resultado_observado` já cita como "ainda
não implementado" -- ver sua docstring: "Esta função NÃO valida a evidência
em si (isso é autonomy/verifiers.py, passo 8 do pacote, ainda não
implementado)".

Cada função abaixo recebe uma evidência TÍPICA (uma dataclass por operação,
com o que foi observado e o que se esperava) e devolve um
`ResultadoVerificacao` com um dos três valores -- nunca um booleano solto,
porque "falta de certeza suficiente" (seção 4.6) é um terceiro caso
genuinamente distinto de aceitar ou refutar:

- `ACEITO`: a evidência confirma o efeito pretendido.
- `REFUTADO`: a evidência CONTRADIZ o efeito pretendido (destino errado,
  campo preservado foi alterado, seção obrigatória ausente) -- um erro real,
  não uma lacuna.
- `PENDENTE`: a evidência disponível não é suficiente para decidir nenhum
  dos dois -- corresponde a "aguardando_evidencia" (seção 4.6: "mantém
  aguardando_evidencia e busca o dado faltante; não transforma a hipótese em
  fato"). Nunca vira `ACEITO` por omissão.

Este módulo é lógica pura, sem I/O e sem depender de `autonomy.execution`
nem `autonomy.requests` -- mesma divisão de responsabilidade dos módulos
irmãos: quem decide a TRANSIÇÃO de estado do pedido a partir do
`ResultadoVerificacao` (ex.: `ACEITO` -> `CONCLUIDO`, `REFUTADO` ->
`RETENTATIVA_AGENDADA` ou `FALHA_FINAL` segundo `autonomy.sweep`, `PENDENTE`
-> permanece `VERIFICANDO` ou vira `RESULTADO_DESCONHECIDO`) é o wiring
futuro (passo 5/6/9 do pacote), não este módulo -- D05: "Modelo propõe;
código decide efeitos permitidos", aqui aplicado à camada de verificação: a
evidência é resolvida por quem chama (releitura real do documento, resposta
do worker, etc.), este módulo só JULGA a evidência já resolvida.

Escopo desta sub-entrega -- as primeiras quatro linhas da tabela da seção
4.6, na ordem em que o passo 8 as nomeia ("tarefa, artefato, consolidação e
outbox"):

| Operação | Evidência necessária | O que não basta |
|---|---|---|
| Atualizar tarefa/plano | Releitura de campos alterados, versão e preservação dos demais | Texto do agente ou HTTP 200 |
| Consolidar áudio | Job concluído, referência à consolidação e cobertura dos IDs solicitados | Job criado |
| Produzir briefing | Artefato persistido, seções exigidas e referências acessíveis | Texto transitório na sessão |
| Enviar WhatsApp | Recibo do worker com destino real e provider message ID | Aprovação, pending ou intenção de envio |

As seis linhas restantes da tabela (ACK de entrega/leitura, cumprir
promessa, reagendar, Argos, finanças/saúde) ficam para sub-entregas
seguintes -- cada uma tem seu próprio pacote-dono no plano (P07 promessas,
P16 Argos, F07 finanças/saúde) e não faz sentido adiantar o contrato de
evidência antes desses pacotes definirem o que fica disponível para
verificar.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResultadoVerificacao(Enum):
    """Os três desfechos possíveis de julgar uma evidência -- ver docstring
    do módulo para o motivo de não ser um booleano."""

    ACEITO = "aceito"
    REFUTADO = "refutado"
    PENDENTE = "pendente"


#: Sentinela para distinguir "campo ausente na releitura" de "campo presente
#: com valor None" -- um `Mapping[str, Any]` legítimo pode ter `None` como
#: valor real de um campo (ex.: uma data que foi limpa de propósito).
_AUSENTE = object()


@dataclass(frozen=True)
class VerificacaoResultado:
    """Saída comum de toda função `verificar_*` deste módulo.

    `motivo` é sempre preenchido e pensado para ser apresentável (mesmo
    espírito de `autonomy.contracts.PolicyDecision.motivo_legivel`) -- quem
    chama pode logar/persistir só este texto sem perder o essencial do
    porquê. `detalhes` carrega os campos específicos que embasaram a decisão
    (ex.: quais chaves divergiram), para depuração e para preencher
    `evidence_refs`/diagnóstico sem exigir que o chamador refaça o cálculo.
    """

    resultado: ResultadoVerificacao
    motivo: str
    detalhes: Mapping[str, Any] = field(default_factory=dict)

    def aceito(self) -> bool:
        return self.resultado is ResultadoVerificacao.ACEITO


# ---------------------------------------------------------------------------
# Atualizar tarefa/plano
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenciaAtualizacaoTarefa:
    """Evidência para "Atualizar tarefa/plano" -- seção 4.6: "Releitura de
    campos alterados, versão e preservação dos demais."

    `campos_releitura` é a releitura REAL do documento após a escrita --
    deve conter tanto as chaves que a operação pretendia alterar quanto as
    que deveriam ter sido preservadas; uma chave ausente é tratada como
    "ainda não sabemos", não como "não mudou" (ver `_AUSENTE` no topo do
    módulo).

    `versao_esperada`/`versao_releitura` seguem a convenção do plano (seção
    4.1: "IDs estáveis e ... revision") -- um documento que expõe controle
    de versão/revisão; passar `None` nos dois quando a fonte não tiver
    versionamento (aceito, mas reduz a força da verificação: duas escritas
    concorrentes com o mesmo conteúdo final ficam indistinguíveis)."""

    campos_alterados_esperados: Mapping[str, Any]
    campos_preservados_esperados: Mapping[str, Any]
    campos_releitura: Mapping[str, Any]
    versao_esperada: int | None = None
    versao_releitura: int | None = None


def verificar_atualizacao_tarefa(evidencia: EvidenciaAtualizacaoTarefa) -> VerificacaoResultado:
    """"Texto do agente ou HTTP 200" não bastam (seção 4.6) -- só a
    releitura importa. Três checagens, na ordem em que uma falha é mais
    informativa:

    1. Versão: se ambas foram informadas e não conferem, a releitura pode
       ser de ANTES da escrita (replicação/cache atrasado) ou a escrita
       pode ter sido sobrescrita por outra concorrente -- `PENDENTE`, não
       `REFUTADO`: não há evidência de que o efeito não ocorreu, só de que
       esta releitura específica não o capturou ainda.
    2. Preservação: qualquer campo que deveria permanecer igual e mudou é
       `REFUTADO` -- isso é sinal de efeito colateral real (a escrita
       tocou algo que não devia), não falta de evidência.
    3. Alteração: qualquer campo esperado ausente da releitura é
       `PENDENTE` (ainda não temos essa parte da evidência); qualquer
       campo presente mas com valor diferente do esperado é `REFUTADO`.
    """
    if (
        evidencia.versao_esperada is not None
        and evidencia.versao_releitura is not None
        and evidencia.versao_releitura != evidencia.versao_esperada
    ):
        return VerificacaoResultado(
            ResultadoVerificacao.PENDENTE,
            motivo=(
                f"versão da releitura ({evidencia.versao_releitura}) não confere com a "
                f"versão esperada após a escrita ({evidencia.versao_esperada}) -- releitura "
                "pode estar desatualizada."
            ),
            detalhes={
                "versao_esperada": evidencia.versao_esperada,
                "versao_releitura": evidencia.versao_releitura,
            },
        )

    campos_preservados_violados = {
        campo: {"esperado": valor_esperado, "observado": evidencia.campos_releitura.get(campo, _AUSENTE)}
        for campo, valor_esperado in evidencia.campos_preservados_esperados.items()
        if evidencia.campos_releitura.get(campo, _AUSENTE) != valor_esperado
        and evidencia.campos_releitura.get(campo, _AUSENTE) is not _AUSENTE
    }
    if campos_preservados_violados:
        return VerificacaoResultado(
            ResultadoVerificacao.REFUTADO,
            motivo=(
                f"{len(campos_preservados_violados)} campo(s) que deveriam ser preservados "
                f"mudaram de valor: {sorted(campos_preservados_violados)}."
            ),
            detalhes={"campos_preservados_violados": campos_preservados_violados},
        )

    campos_ausentes = {
        campo
        for campo in evidencia.campos_alterados_esperados
        if evidencia.campos_releitura.get(campo, _AUSENTE) is _AUSENTE
    }
    if campos_ausentes:
        return VerificacaoResultado(
            ResultadoVerificacao.PENDENTE,
            motivo=(
                f"{len(campos_ausentes)} campo(s) alterado(s) esperado(s) ainda não aparecem "
                f"na releitura: {sorted(campos_ausentes)}."
            ),
            detalhes={"campos_ausentes": sorted(campos_ausentes)},
        )

    campos_divergentes = {
        campo: {"esperado": valor_esperado, "observado": evidencia.campos_releitura.get(campo)}
        for campo, valor_esperado in evidencia.campos_alterados_esperados.items()
        if evidencia.campos_releitura.get(campo) != valor_esperado
    }
    if campos_divergentes:
        return VerificacaoResultado(
            ResultadoVerificacao.REFUTADO,
            motivo=(
                f"{len(campos_divergentes)} campo(s) alterado(s) não têm o valor esperado na "
                f"releitura: {sorted(campos_divergentes)}."
            ),
            detalhes={"campos_divergentes": campos_divergentes},
        )

    return VerificacaoResultado(
        ResultadoVerificacao.ACEITO,
        motivo="releitura confirma todos os campos alterados, preserva os demais e a versão confere.",
    )


# ---------------------------------------------------------------------------
# Consolidar áudio
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenciaConsolidacaoAudio:
    """Evidência para "Consolidar áudio" -- seção 4.6: "Job concluído,
    referência à consolidação e cobertura dos IDs solicitados." "Job
    criado" não basta (F04, seção 7: "dez reentregas do mesmo evento não
    criam dez consolidações" e "resultado parcial não é reportado como
    completo")."""

    job_concluido: bool
    referencia_consolidacao: str | None
    ids_solicitados: frozenset[str]
    ids_cobertos: frozenset[str]


def verificar_consolidacao_audio(evidencia: EvidenciaConsolidacaoAudio) -> VerificacaoResultado:
    """Job ainda não concluído é `PENDENTE` -- pode terminar depois, "job
    criado" é exatamente o estado insuficiente citado na seção 4.6, não um
    erro. Job concluído sem referência é `REFUTADO` -- terminou e não
    produziu o artefato esperado, um desfecho definitivo, não uma lacuna
    temporária. Cobertura parcial (faltam IDs solicitados) é `PENDENTE`,
    nunca `ACEITO` -- aceite de F04: "resultado parcial não é reportado
    como completo"."""
    if not evidencia.job_concluido:
        return VerificacaoResultado(
            ResultadoVerificacao.PENDENTE,
            motivo="job de consolidação ainda não concluiu -- job criado não é evidência suficiente.",
        )
    if not evidencia.referencia_consolidacao:
        return VerificacaoResultado(
            ResultadoVerificacao.REFUTADO,
            motivo="job concluiu mas não produziu nenhuma referência de consolidação.",
        )
    ids_faltantes = evidencia.ids_solicitados - evidencia.ids_cobertos
    if ids_faltantes:
        return VerificacaoResultado(
            ResultadoVerificacao.PENDENTE,
            motivo=(
                f"cobertura parcial -- {len(ids_faltantes)} de {len(evidencia.ids_solicitados)} "
                "ID(s) solicitado(s) ainda não aparecem na consolidação."
            ),
            detalhes={"ids_faltantes": sorted(ids_faltantes)},
        )
    return VerificacaoResultado(
        ResultadoVerificacao.ACEITO,
        motivo="job concluído, referência de consolidação presente e todos os IDs solicitados cobertos.",
        detalhes={"referencia_consolidacao": evidencia.referencia_consolidacao},
    )


# ---------------------------------------------------------------------------
# Produzir briefing (artefato)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenciaArtefatoBriefing:
    """Evidência para "Produzir briefing" -- seção 4.6: "Artefato
    persistido, seções exigidas e referências acessíveis." "Texto
    transitório na sessão" não basta -- por isso `artefato_persistido` e
    `referencia_artefato` são dois campos distintos: um artefato só existe
    de fato quando há ONDE recuperá-lo depois, fora da sessão que o
    escreveu.

    `referencias_fontes`/`referencias_acessiveis` seguem F01 (seção 7),
    passo 6: "se faltou evidência importante, tentar buscá-la; indicar a
    lacuna quando a fonte estiver indisponível" -- uma fonte citada mas
    inacessível não invalida o briefing (ele pode legitimamente registrar a
    lacuna), então isso é tratado como `PENDENTE`, não `REFUTADO` (ver
    função)."""

    artefato_persistido: bool
    referencia_artefato: str | None
    secoes_exigidas: frozenset[str]
    secoes_presentes: frozenset[str]
    referencias_fontes: frozenset[str] = frozenset()
    referencias_acessiveis: frozenset[str] = frozenset()


def verificar_artefato_briefing(evidencia: EvidenciaArtefatoBriefing) -> VerificacaoResultado:
    """Não persistido é `REFUTADO` direto -- "texto transitório na sessão"
    é precisamente o caso que a seção 4.6 diz não bastar, um desfecho
    definitivo (o passo terminou sem produzir o artefato exigido), não uma
    lacuna a preencher depois. Seção obrigatória ausente também é
    `REFUTADO` -- o exemplo de missão da seção 4.3 usa
    `required_sections` como parte do próprio critério de aceite
    (`artifact_exists_and_matches`), não como algo opcional. Fonte citada
    mas inacessível é `PENDENTE` -- ver docstring da evidência."""
    if not evidencia.artefato_persistido or not evidencia.referencia_artefato:
        return VerificacaoResultado(
            ResultadoVerificacao.REFUTADO,
            motivo="artefato não foi persistido (ou não tem referência recuperável) -- texto transitório não basta.",
        )
    secoes_faltantes = evidencia.secoes_exigidas - evidencia.secoes_presentes
    if secoes_faltantes:
        return VerificacaoResultado(
            ResultadoVerificacao.REFUTADO,
            motivo=(
                f"{len(secoes_faltantes)} seção(ões) exigida(s) ausente(s) do artefato: "
                f"{sorted(secoes_faltantes)}."
            ),
            detalhes={"secoes_faltantes": sorted(secoes_faltantes)},
        )
    referencias_inacessiveis = evidencia.referencias_fontes - evidencia.referencias_acessiveis
    if referencias_inacessiveis:
        return VerificacaoResultado(
            ResultadoVerificacao.PENDENTE,
            motivo=(
                f"artefato completo, mas {len(referencias_inacessiveis)} referência(s) de fonte "
                "citada(s) não estão acessíveis -- lacuna a registrar, não a inventar."
            ),
            detalhes={"referencias_inacessiveis": sorted(referencias_inacessiveis)},
        )
    return VerificacaoResultado(
        ResultadoVerificacao.ACEITO,
        motivo="artefato persistido, todas as seções exigidas presentes e referências acessíveis.",
        detalhes={"referencia_artefato": evidencia.referencia_artefato},
    )


# ---------------------------------------------------------------------------
# Enviar WhatsApp (outbox)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenciaEnvioWhatsApp:
    """Evidência para "Enviar WhatsApp" -- seção 4.6: "Recibo do worker com
    destino real e provider message ID." "Aprovação, pending ou intenção de
    envio" não bastam -- achado A03 do plano (seção 1.3): "outbox_aprovacao.py
    ... resolve atenção com 'mensagem aprovada e enviada' ao passar para
    pending" é exatamente o erro que esta evidência é desenhada para não
    repetir: `recibo_do_worker` é sobre o EFEITO observado pelo worker
    depois do envio, nunca sobre aprovação ou o estado `pending` da fila.

    `destino_confirmado` existe separado de `destino_esperado` porque um
    recibo do worker sem destino conferido não prova que a mensagem foi
    para quem devia (ex.: um bug de resolução de contato que a aprovação
    humana não detectaria, já que ela aprova o RASCUNHO, não o envio
    real)."""

    recibo_do_worker: bool
    destino_esperado: str
    destino_confirmado: str | None
    provider_message_id: str | None


def verificar_envio_whatsapp(evidencia: EvidenciaEnvioWhatsApp) -> VerificacaoResultado:
    """Sem recibo do worker: `PENDENTE` -- "aprovação, pending ou intenção
    de envio" (seção 4.6) é literalmente este caso, e a seção 1.3 (achado
    A05) diz que a queda entre "enviado externamente" e "gravado como
    sent" deve ser representada como resultado desconhecido, não como
    sucesso nem como falha definitiva -- decidir entre reconciliar e
    reagendar é do chamador (`autonomy.sweep`/wiring), não deste
    verificador.

    Recibo presente mas destino divergente: `REFUTADO` -- a mensagem
    aparentemente saiu, mas não para quem devia; isso é um erro real
    (destinatário errado), nunca "falta de evidência" -- não deve ser
    tratado como pendente esperando mais dados, porque mais dados não vão
    corrigir um destino já errado.

    Recibo e destino corretos mas sem provider message ID: `PENDENTE` --
    o worker confirma o efeito, mas sem o identificador do provedor não há
    como correlacionar com um eventual ACK de entrega depois (a linha
    seguinte da tabela da seção 4.6, fora do escopo desta sub-entrega)."""
    if not evidencia.recibo_do_worker:
        return VerificacaoResultado(
            ResultadoVerificacao.PENDENTE,
            motivo="sem recibo do worker -- aprovação, pending ou intenção de envio não comprovam envio real.",
        )
    if not evidencia.destino_confirmado or evidencia.destino_confirmado != evidencia.destino_esperado:
        return VerificacaoResultado(
            ResultadoVerificacao.REFUTADO,
            motivo=(
                f"recibo do worker presente, mas o destino confirmado "
                f"({evidencia.destino_confirmado!r}) não confere com o destino esperado "
                f"({evidencia.destino_esperado!r})."
            ),
            detalhes={
                "destino_esperado": evidencia.destino_esperado,
                "destino_confirmado": evidencia.destino_confirmado,
            },
        )
    if not evidencia.provider_message_id:
        return VerificacaoResultado(
            ResultadoVerificacao.PENDENTE,
            motivo="recibo do worker confirma o destino certo, mas sem provider message ID para correlacionar.",
        )
    return VerificacaoResultado(
        ResultadoVerificacao.ACEITO,
        motivo="recibo do worker confirma destino correto e provider message ID presente.",
        detalhes={"provider_message_id": evidencia.provider_message_id},
    )
