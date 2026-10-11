"""Reserva de emergencia editavel fora da tela (item 9 do prompt de ajustes financeiros).

O valor fica em `finance_settings/config.emergencyReserveCurrent` (e o alvo em
`emergencyReserveTarget`), que a tela edita e o `bolso` das metas le. Ate
11/10/2026 nenhuma tool gravava ali: em 02/10 o dono autorizou corrigir a
reserva para o valor da XP e nao havia como.

So os dois campos sao gravados (merge): o documento tem orcamentos e outras
reservas que nao sao desta ferramenta. Cada mudanca vira um registro em
`reserva_emergencia_historico`, fora do documento que a tela regrava inteiro.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

COLECAO_CONFIG = "finance_settings"
DOC_CONFIG = "config"
COLECAO_HISTORICO = "reserva_emergencia_historico"
TETO = 10_000_000.0

_CAMPOS = {"valor_atual": "emergencyReserveCurrent", "valor_alvo": "emergencyReserveTarget"}


def _numero(valor, nome: str) -> float:
    if isinstance(valor, bool):
        raise ValueError(f"{nome} precisa ser um valor em reais.")
    if isinstance(valor, (int, float)):
        numero = float(valor)
    else:
        texto = re.sub(r"[^\d,.\-]", "", str(valor or ""))
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            numero = float(texto)
        except ValueError:
            raise ValueError(f"{nome} nao e um valor em reais: {valor!r}.") from None
    numero = round(numero, 2)
    if not 0 <= numero <= TETO:
        raise ValueError(f"{nome} fora da faixa (0 a {TETO:,.0f}): {numero}.")
    return numero


def _reserva(config: dict) -> dict:
    return {"atual": config.get("emergencyReserveCurrent"), "alvo": config.get("emergencyReserveTarget")}


def _igual(a, b: float) -> bool:
    try:
        return round(float(a), 2) == b
    except (TypeError, ValueError):
        return False


def atualizar(db, *, valor_atual=None, valor_alvo=None, fonte: str = "", observacao: str = "",
              canal: str = "mcp") -> dict:
    """Grava os valores informados, registra o historico e confirma relendo."""
    pedidos = {campo: _numero(valor, nome)
               for nome, campo, valor in (("valor_atual", _CAMPOS["valor_atual"], valor_atual),
                                          ("valor_alvo", _CAMPOS["valor_alvo"], valor_alvo))
               if valor is not None}
    if not pedidos:
        raise ValueError("Informe valor_atual (o que ha hoje na reserva) e/ou valor_alvo.")

    ref = db.collection(COLECAO_CONFIG).document(DOC_CONFIG)
    antes = ref.get().to_dict() or {}
    mudancas = {campo: {"de": antes.get(campo), "para": valor}
                for campo, valor in pedidos.items() if not _igual(antes.get(campo), valor)}
    if not mudancas:
        return {"estado": "verificado", "sem_mudanca": True, "reserva": _reserva(antes)}

    ref.set({campo: m["para"] for campo, m in mudancas.items()}, merge=True)
    historico = db.collection(COLECAO_HISTORICO).document(uuid.uuid4().hex[:20])
    historico.set({
        "em": datetime.now(timezone.utc).isoformat(),
        "mudancas": mudancas,
        "fonte": str(fonte or "").strip()[:200],
        "observacao": str(observacao or "").strip()[:500],
        "canal": canal,
    })

    depois = ref.get().to_dict() or {}
    gravou = all(_igual(depois.get(campo), m["para"]) for campo, m in mudancas.items())
    return {
        "estado": "verificado" if gravou else "falhou",
        "reserva": _reserva(depois),
        "anterior": _reserva(antes),
        "historico_id": historico.id,
        "fonte": str(fonte or "").strip() or None,
        "motivo": None if gravou else "a releitura nao bateu com o valor gravado",
    }
