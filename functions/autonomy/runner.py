"""Núcleo do runner autônomo (P08 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, passos 1, 4, 5, 6, 7 e 11).

Lógica pura, sem I/O e sem Claude real: o transporte do modelo
(`PlannerModel`) e o executor de domínio (`ToolExecutor`) são interfaces
separadas (passo 1), exercitadas aqui por dublês. Cloud Tasks, worker HTTP,
IAM e o cliente Claude de verdade ficam para sub-entregas de wiring,
sempre em shadow/off (passo 11).

O histórico guarda só nome/ok/erro de cada ferramenta (checkpoint pequeno,
sem conteúdo de domínio); levar `dados` ao planner é decisão do wiring, que
é quem sabe o que pode ser persistido.

`executar_lote` roda UM lote de uma execução (carregar contexto -> planejar
-> executar -> checkpoint) e TERMINA com um resultado tipado; nunca espera
humano ou terceiro dentro da chamada (passo 5): `Esperar` vira
`AGUARDANDO` com a condição persistível. Estourar qualquer limite (rodadas,
ferramentas, tokens, duração) vira `PAUSADO_LIMITE` recuperável com
checkpoint -- nunca `CONCLUIDO` (passo 6). `CONCLUIDO` só sai quando o
planner declara o fim explicitamente.

Erros do modelo (429, indisponibilidade, timeout, recusa, contexto grande,
saída inválida) são resultados tipados (passo 7), não exceções: rate limit,
indisponibilidade e timeout pedem retentativa; recusa e contexto excedido
são falha final.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Protocol


class TipoErroModelo(str, Enum):
    RATE_LIMIT = "rate_limit"
    INDISPONIVEL = "indisponivel"
    TIMEOUT = "timeout"
    RECUSA = "recusa"
    CONTEXTO_EXCEDIDO = "contexto_excedido"


_ERROS_RETENTAVEIS = frozenset(
    {TipoErroModelo.RATE_LIMIT, TipoErroModelo.INDISPONIVEL, TipoErroModelo.TIMEOUT}
)


class StatusRunner(str, Enum):
    CONCLUIDO = "concluido"
    AGUARDANDO = "aguardando"
    PAUSADO_LIMITE = "pausado_limite"
    RETENTAR = "retentar"
    FALHA = "falha"


@dataclass(frozen=True)
class ChamadaFerramenta:
    nome: str
    argumentos: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoFerramenta:
    ok: bool
    dados: Mapping[str, Any] = field(default_factory=dict)
    erro: str = ""  # código curto [a-z0-9_]; texto livre é descartado do histórico


@dataclass(frozen=True)
class ErroModelo:
    tipo: TipoErroModelo
    detalhe: str = ""


@dataclass(frozen=True)
class Esperar:
    """Condição persistível (resposta de terceiro, decisão do André, horário)."""

    condicao: str
    acordar_em: datetime | None = None


@dataclass(frozen=True)
class Concluir:
    resumo: str = ""


@dataclass(frozen=True)
class SaidaPlanner:
    """Próximo lote: chamadas a executar OU um desfecho (`Esperar`/`Concluir`).

    `tokens` é o consumo REAL da chamada ao modelo (entrada + saída).
    """

    chamadas: tuple[ChamadaFerramenta, ...] = ()
    desfecho: Esperar | Concluir | None = None
    tokens: int = 0


class PlannerModel(Protocol):
    def planejar(
        self, contexto: Mapping[str, Any], historico: tuple[Mapping[str, Any], ...]
    ) -> SaidaPlanner | ErroModelo: ...


class ToolExecutor(Protocol):
    def executar(self, chamada: ChamadaFerramenta) -> ResultadoFerramenta: ...


_MIN_DURACAO_SEGUNDOS = 0.001  # abaixo de 1 µs o timedelta arredonda para 0
_MAX_DURACAO_SEGUNDOS = 86_400  # um dia; também evita overflow de timedelta


@dataclass(frozen=True)
class LimitesRunner:
    max_rodadas: int = 5
    max_ferramentas: int = 20
    max_tokens: int = 50_000
    max_duracao_segundos: float = 240.0
    max_saidas_invalidas: int = 2

    def __post_init__(self) -> None:
        for nome in ("max_rodadas", "max_ferramentas", "max_tokens", "max_saidas_invalidas"):
            v = getattr(self, nome)
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise ValueError(f"{nome} deve ser inteiro >= 1")
        d = self.max_duracao_segundos
        if (
            isinstance(d, bool) or not isinstance(d, (int, float))
            or not _MIN_DURACAO_SEGUNDOS <= d <= _MAX_DURACAO_SEGUNDOS
        ):
            raise ValueError(f"max_duracao_segundos deve estar em [{_MIN_DURACAO_SEGUNDOS}, {_MAX_DURACAO_SEGUNDOS}]")


@dataclass(frozen=True)
class ResultadoRunner:
    status: StatusRunner
    motivo: str = ""
    rodadas: int = 0
    ferramentas: int = 0
    tokens: int = 0
    historico: tuple[Mapping[str, Any], ...] = ()
    espera: Esperar | None = None
    erro_modelo: ErroModelo | None = None


_CODIGO_ERRO = re.compile(r"[a-z0-9_]{1,40}")


def _codigo_erro(erro: Any) -> str:
    """Só códigos curtos tipados entram no histórico; texto livre do adaptador
    (resposta de provedor, URL, dado de domínio) nunca é persistido."""
    if isinstance(erro, str) and _CODIGO_ERRO.fullmatch(erro):
        return erro
    return "erro_ferramenta" if erro else ""


def _saida_valida(saida: Any, permitidas: frozenset[str]) -> str:
    """Devolve '' se válida, senão o motivo. Ferramenta desconhecida inclusa."""
    if not isinstance(saida, SaidaPlanner):
        return "saida_nao_e_SaidaPlanner"
    if isinstance(saida.tokens, bool) or not isinstance(saida.tokens, int) or saida.tokens < 0:
        return "tokens_invalidos"
    if saida.desfecho is not None and not isinstance(saida.desfecho, (Esperar, Concluir)):
        return "desfecho_invalido"
    if isinstance(saida.desfecho, Esperar) and (
        not isinstance(saida.desfecho.condicao, str) or not saida.desfecho.condicao.strip()
    ):
        return "espera_sem_condicao"
    if not isinstance(saida.chamadas, tuple):
        return "chamadas_nao_e_tupla"
    if saida.desfecho is not None and saida.chamadas:
        return "desfecho_com_chamadas"
    if saida.desfecho is None and not saida.chamadas:
        return "saida_vazia"
    for c in saida.chamadas:
        if not isinstance(c, ChamadaFerramenta) or not isinstance(c.nome, str):
            return "chamada_invalida"
        if c.nome not in permitidas:
            return "ferramenta_desconhecida:" + _codigo_erro(c.nome or "?").replace("erro_ferramenta", "nome_invalido")
    return ""


def executar_lote(
    planner: PlannerModel,
    executor: ToolExecutor,
    contexto: Mapping[str, Any],
    ferramentas_permitidas: frozenset[str],
    limites: LimitesRunner | None = None,
    historico_inicial: tuple[Mapping[str, Any], ...] = (),
    agora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ResultadoRunner:
    if isinstance(ferramentas_permitidas, (str, bytes)):
        raise TypeError("ferramentas_permitidas deve ser um conjunto de nomes, não str")
    ferramentas_permitidas = frozenset(ferramentas_permitidas)
    limites = limites or LimitesRunner()
    inicio = agora()
    historico = tuple(historico_inicial)
    rodadas = n_ferr = tokens = invalidas = 0

    def _res(status: StatusRunner, motivo: str = "", **kw: Any) -> ResultadoRunner:
        return ResultadoRunner(
            status=status, motivo=motivo, rodadas=rodadas, ferramentas=n_ferr,
            tokens=tokens, historico=historico, **kw,
        )

    while True:
        if agora() - inicio >= timedelta(seconds=limites.max_duracao_segundos):
            return _res(StatusRunner.PAUSADO_LIMITE, "duracao")
        if rodadas >= limites.max_rodadas:
            return _res(StatusRunner.PAUSADO_LIMITE, "rodadas")
        if tokens >= limites.max_tokens:
            return _res(StatusRunner.PAUSADO_LIMITE, "tokens")

        rodadas += 1
        try:
            saida = planner.planejar(contexto, historico)
        except Exception as exc:  # transporte do modelo nunca derruba o worker
            return _res(
                StatusRunner.RETENTAR, "excecao_planner",
                erro_modelo=ErroModelo(TipoErroModelo.INDISPONIVEL, type(exc).__name__),
            )
        if isinstance(saida, ErroModelo):
            if not isinstance(saida.tipo, TipoErroModelo):
                return _res(StatusRunner.FALHA, "erro_modelo_tipo_invalido")
            st = StatusRunner.RETENTAR if saida.tipo in _ERROS_RETENTAVEIS else StatusRunner.FALHA
            return _res(st, saida.tipo.value, erro_modelo=saida)

        motivo = _saida_valida(saida, ferramentas_permitidas)
        if motivo:
            if isinstance(getattr(saida, "tokens", None), int) and not isinstance(saida.tokens, bool):
                tokens += max(saida.tokens, 0)
            invalidas += 1
            historico += ({"tipo": "saida_invalida", "motivo": motivo},)
            if invalidas >= limites.max_saidas_invalidas:
                return _res(StatusRunner.FALHA, f"saida_invalida:{motivo}")
            continue

        tokens += saida.tokens
        if tokens > limites.max_tokens:
            return _res(StatusRunner.PAUSADO_LIMITE, "tokens")
        if agora() - inicio >= timedelta(seconds=limites.max_duracao_segundos):
            return _res(StatusRunner.PAUSADO_LIMITE, "duracao")
        if isinstance(saida.desfecho, Concluir):
            return _res(StatusRunner.CONCLUIDO, saida.desfecho.resumo)
        if isinstance(saida.desfecho, Esperar):
            return _res(StatusRunner.AGUARDANDO, saida.desfecho.condicao, espera=saida.desfecho)

        if len(saida.chamadas) > limites.max_ferramentas:
            # um lote que sozinho excede o teto nunca caberia: pausar de novo
            # reproduziria o mesmo plano para sempre
            return _res(StatusRunner.FALHA, "lote_excede_max_ferramentas")
        if n_ferr + len(saida.chamadas) > limites.max_ferramentas:
            return _res(StatusRunner.PAUSADO_LIMITE, "ferramentas")
        for chamada in saida.chamadas:
            if agora() - inicio >= timedelta(seconds=limites.max_duracao_segundos):
                return _res(StatusRunner.PAUSADO_LIMITE, "duracao")
            try:
                r = executor.executar(chamada)
            except Exception as exc:
                r = ResultadoFerramenta(ok=False, erro=type(exc).__name__)
            n_ferr += 1
            historico += ({
                "tipo": "ferramenta", "nome": chamada.nome,
                "ok": getattr(r, "ok", False) is True,
                "erro": _codigo_erro(getattr(r, "erro", "")),
            },)
