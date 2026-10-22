"""Prazo expresso x estimativa de acompanhamento (P07 do plano de autonomia,
passo 4).

Lógica pura -- sem I/O e sem wiring. O prazo que a pessoa disse
(`Prazo.natureza == expresso`, com data) é vinculante: o acompanhamento só
começa depois dele. Sem prazo expresso com data, o momento de olhar de novo é
uma ESTIMATIVA -- percentil 75 do histórico de horas de resposta daquele
contato, usado só com amostra mínima -- e nunca é tratada como prazo
contratual (`vinculante=False`). Sem amostra suficiente, vale o padrão fixo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from autonomy.commitments import PRAZO_ESTIMADO, PRAZO_EXPRESSO, Prazo

AMOSTRA_MINIMA = 5
PADRAO_HORAS = 24.0
MIN_HORAS = 1.0
MAX_HORAS = 168.0
FUSO_PADRAO = "America/Sao_Paulo"

ORIGEM_EXPRESSO = "prazo_expresso"
ORIGEM_HISTORICO = "historico_contato"
ORIGEM_PADRAO = "padrao"


@dataclass(frozen=True)
class Acompanhamento:
    verificar_em: datetime  # UTC, sem microssegundos
    origem: str
    vinculante: bool  # True só para prazo expresso com data
    amostra: int = 0


def _horas_validas(horas) -> list[float]:
    if type(horas) not in (list, tuple):
        raise ValueError("horas deve ser lista ou tupla de números")
    saida = []
    for h in horas:
        if type(h) is int:
            h = float(min(h, 10**9)) if h > 0 else 0.0  # int enorme não estoura
        if type(h) is not float or not math.isfinite(h) or h <= 0:
            raise ValueError("horas de resposta devem ser números finitos e positivos")
        saida.append(h)
    return saida


def estimar_horas(horas_resposta, amostra_minima: int = AMOSTRA_MINIMA) -> float | None:
    """Percentil 75 (posto mais próximo) limitado a [MIN_HORAS, MAX_HORAS];
    None se a amostra for menor que a mínima."""
    if type(amostra_minima) is not int or amostra_minima < 1:
        raise ValueError("amostra_minima deve ser int >= 1")
    ordenadas = sorted(_horas_validas(horas_resposta))
    if len(ordenadas) < amostra_minima:
        return None
    p75 = ordenadas[math.ceil(0.75 * len(ordenadas)) - 1]
    return min(max(p75, MIN_HORAS), MAX_HORAS)


def _utc(dt, nome: str) -> datetime:
    try:
        if not isinstance(dt, datetime) or dt.utcoffset() is None:
            raise ValueError(f"{nome} deve ser datetime com fuso")
        return dt.astimezone(timezone.utc).replace(microsecond=0)
    except ValueError:
        raise
    except Exception:
        raise ValueError(f"{nome} inválido ou fora do intervalo") from None


def planejar_acompanhamento(
    prazo, enviado_em, horas_resposta=(), fuso: str = FUSO_PADRAO
) -> Acompanhamento:
    """Quando olhar de novo o compromisso. `enviado_em` é o momento em que a
    promessa foi feita; `horas_resposta`, o histórico do contato (lista ou
    tupla). Só levanta ValueError."""
    try:
        return _planejar(prazo, enviado_em, horas_resposta, fuso)
    except ValueError:
        raise
    except Exception:
        raise ValueError("entrada inválida") from None


def _planejar(prazo, enviado_em, horas_resposta, fuso) -> Acompanhamento:
    if prazo is not None and not isinstance(prazo, Prazo):
        raise ValueError("prazo deve ser Prazo ou None")
    base = _utc(enviado_em, "enviado_em")
    try:
        tz = ZoneInfo(fuso)
    except Exception:
        raise ValueError("fuso inválido") from None
    historico = _horas_validas(horas_resposta)  # valida mesmo quando não usa
    if prazo is not None:
        if type(prazo.natureza) is not str or prazo.natureza not in (PRAZO_EXPRESSO, PRAZO_ESTIMADO):
            raise ValueError("natureza do prazo inválida")
        if prazo.data is not None and type(prazo.data) is not date:
            raise ValueError("data do prazo inválida")

    try:
        if prazo is not None and prazo.natureza == PRAZO_EXPRESSO and prazo.data is not None:
            # Vence no fim do dia prometido (no fuso do dono); olha logo depois.
            meia_noite = datetime.combine(prazo.data + timedelta(days=1), time.min, tzinfo=tz)
            verificar = _utc(meia_noite, "prazo")
            if verificar <= base:
                raise ValueError("prazo expresso anterior à promessa")
            return Acompanhamento(verificar, ORIGEM_EXPRESSO, True)

        horas = estimar_horas(historico)
        if horas is not None:
            return Acompanhamento(
                (base + timedelta(hours=horas)).replace(microsecond=0), ORIGEM_HISTORICO, False, len(historico))
        return Acompanhamento(base + timedelta(hours=PADRAO_HORAS), ORIGEM_PADRAO, False, len(historico))
    except OverflowError:
        raise ValueError("data fora do intervalo") from None


__all__ = [
    "Acompanhamento", "AMOSTRA_MINIMA", "PADRAO_HORAS", "estimar_horas",
    "planejar_acompanhamento", "ORIGEM_EXPRESSO", "ORIGEM_HISTORICO", "ORIGEM_PADRAO",
]
