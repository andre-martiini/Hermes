"""Decisão de continuação do runner (P08 do plano de autonomia, passos 4-7).

Função pura: traduz o `ResultadoRunner` de um lote (`autonomy.runner`) no
próximo estado do pedido durável e no momento da continuação, SEM I/O, Cloud
Tasks ou relógio escondido. O wiring grava o estado e enfileira a tarefa; aqui
só se decide, e as regras são as do contrato:

- sucesso do runner nunca fecha o pedido: `CONCLUIDO` vai para `VERIFICANDO`
  (passo 4, "verificar"); só o verificador conclui;
- espera humana/externa não segura worker (passo 5): `AGUARDANDO_EXTERNO`,
  sem continuação imediata;
- limite estourado é pausa recuperável (passo 6): `RETENTATIVA_AGENDADA` em
  intervalo curto, com teto de pausas para não girar para sempre;
- 429/indisponibilidade/timeout (passo 7): backoff de `autonomy.requests`
  até `DEFAULT_MAX_TENTATIVAS`, depois `FALHA_FINAL`; recusa, contexto
  excedido e saída inválida são `FALHA_FINAL`.

Todas as transições partem de `EM_ANDAMENTO` e são conferidas contra
`validar_transicao` nos testes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from autonomy.requests import (
    DEFAULT_MAX_TENTATIVAS,
    RequestStatus,
    calcular_backoff_segundos,
)
from autonomy.runner import Esperar, ResultadoRunner, StatusRunner

PAUSA_LIMITE_SEGUNDOS = 60.0
MAX_PAUSAS_LIMITE = 20


@dataclass(frozen=True)
class DecisaoContinuacao:
    novo_status: RequestStatus
    continuar_em: datetime | None = None
    tentativas: int = 0
    pausas: int = 0
    motivo: str = ""
    condicao_espera: str = ""


def decidir_continuacao(
    resultado: ResultadoRunner,
    agora: datetime,
    tentativas: int = 0,
    pausas: int = 0,
    rng: object | None = None,
) -> DecisaoContinuacao:
    """`tentativas`/`pausas` são os contadores já gravados no pedido."""
    if not isinstance(resultado, ResultadoRunner) or not isinstance(resultado.status, StatusRunner):
        return DecisaoContinuacao(
            RequestStatus.FALHA_FINAL, tentativas=tentativas, pausas=pausas,
            motivo="resultado_runner_invalido",
        )
    if not isinstance(agora, datetime) or agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("agora deve ser datetime com fuso.")
    for nome, v in (("tentativas", tentativas), ("pausas", pausas)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"{nome} deve ser inteiro >= 0")
    try:
        # soma em UTC: timedelta somado a datetime com fuso de DST usa relógio de parede
        agora = agora.astimezone(timezone.utc)
        return _decidir(resultado, agora, tentativas, pausas, rng)
    except OverflowError:
        raise ValueError("agora fora do intervalo suportado.") from None


def _decidir(
    resultado: ResultadoRunner, agora: datetime, tentativas: int, pausas: int, rng: object | None,
) -> DecisaoContinuacao:
    st = resultado.status
    base = dict(tentativas=tentativas, pausas=pausas, motivo=resultado.motivo)
    if st is StatusRunner.CONCLUIDO:
        return DecisaoContinuacao(RequestStatus.VERIFICANDO, **base)
    if st is StatusRunner.AGUARDANDO:
        espera = resultado.espera
        if not isinstance(espera, Esperar) or not isinstance(espera.condicao, str) or not espera.condicao.strip():
            return DecisaoContinuacao(
                RequestStatus.FALHA_FINAL, tentativas=tentativas, pausas=pausas,
                motivo="espera_sem_condicao",
            )
        acordar = getattr(espera, "acordar_em", None)
        if not isinstance(acordar, datetime) or acordar.tzinfo is None or acordar.utcoffset() is None:
            acordar = None  # tipo errado ou sem fuso é ambíguo: espera sem horário (sweep acorda)
        else:
            acordar = acordar.astimezone(timezone.utc)
        return DecisaoContinuacao(
            RequestStatus.AGUARDANDO_EXTERNO, continuar_em=acordar,
            condicao_espera=espera.condicao, **base,
        )
    if st is StatusRunner.PAUSADO_LIMITE:
        if pausas + 1 > MAX_PAUSAS_LIMITE:
            return DecisaoContinuacao(
                RequestStatus.FALHA_FINAL, tentativas=tentativas, pausas=pausas,
                motivo="pausas_esgotadas",
            )
        return DecisaoContinuacao(
            RequestStatus.RETENTATIVA_AGENDADA,
            continuar_em=agora + timedelta(seconds=PAUSA_LIMITE_SEGUNDOS),
            tentativas=tentativas, pausas=pausas + 1, motivo=resultado.motivo,
        )
    if st is StatusRunner.RETENTAR:
        if tentativas + 1 > DEFAULT_MAX_TENTATIVAS:
            return DecisaoContinuacao(
                RequestStatus.FALHA_FINAL, tentativas=tentativas, pausas=pausas,
                motivo="tentativas_esgotadas",
            )
        espera_s = calcular_backoff_segundos(tentativas + 1, rng)
        return DecisaoContinuacao(
            RequestStatus.RETENTATIVA_AGENDADA,
            continuar_em=agora + timedelta(seconds=espera_s),
            tentativas=tentativas + 1, pausas=pausas, motivo=resultado.motivo,
        )
    return DecisaoContinuacao(RequestStatus.FALHA_FINAL, **base)
