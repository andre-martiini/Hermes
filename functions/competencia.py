"""Mes de referencia do financeiro: "2026-10" na entrada, nome do mes na saida.

`fixed_bills` e `income_entries` guardam `month` de 0 a 11 (padrao do JavaScript).
As tools recebiam esse numero cru e devolviam sem nome, e em 01/10/2026 os dados
de setembro foram lidos como "agosto". `competencia` ("YYYY-MM", mes de 1 a 12)
tem precedencia; `mes` 0-11 continua aceito para nao quebrar quem ja o usa.
"""
from __future__ import annotations

import re
from datetime import datetime

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")

_FORMATO = re.compile(r"^(\d{4})-(\d{2})$")


def ler(competencia: str) -> tuple[int, int]:
    """"2026-10" -> (9, 2026): mes 0-11, como esta gravado."""
    achado = _FORMATO.match(str(competencia or "").strip())
    if not achado or not 1 <= int(achado.group(2)) <= 12:
        raise ValueError(f"competencia deve ser YYYY-MM (ex.: 2026-10), veio {competencia!r}.")
    return int(achado.group(2)) - 1, int(achado.group(1))


def resolver(slots: dict, agora: datetime | None = None) -> tuple[int, int]:
    """(mes 0-11, ano): competencia > mes/ano > mes atual."""
    if slots.get("competencia"):
        return ler(slots["competencia"])
    agora = agora or datetime.now()
    mes = slots.get("mes")
    ano = slots.get("ano")
    if mes is None:
        mes = agora.month - 1
    if ano is None:
        ano = agora.year
    return int(mes), int(ano)


def periodo(mes0: int, ano: int) -> dict:
    return {
        "mes": int(mes0),
        "ano": int(ano),
        "competencia": f"{int(ano):04d}-{int(mes0) + 1:02d}",
        "mes_nome": MESES[int(mes0)],
        "mes_1a12": int(mes0) + 1,
    }
