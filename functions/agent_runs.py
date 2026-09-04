"""Observabilidade das sessões agendadas do Claude (agent_runs).

Registra execuções de rotinas agendadas (briefing, varredura de follow-ups,
executor de pedidos autônomos, etc.) para alimentar métricas de proatividade
e revisões periódicas do Eixo 6 do plano Hermes → Jarvis.
"""

from __future__ import annotations

import datetime
from firebase_admin import firestore

COLLECTION = "agent_runs"

STATUS_SUCESSO = "sucesso"
STATUS_ERRO = "erro"
STATUS_PARCIAL = "parcial"

STATUS_VALIDOS = {STATUS_SUCESSO, STATUS_ERRO, STATUS_PARCIAL}


# ---------------------------------------------------------------------------
# Lógica pura (montagem e validação)
# ---------------------------------------------------------------------------


def montar_registro(
    rotina: str,
    resumo: str,
    contadores: dict | None = None,
    status: str = STATUS_SUCESSO,
    erro: str | None = None,
    iniciado_em: str | None = None,
    finalizado_em: str | None = None,
) -> dict:
    """Valida os dados da execução e monta o dicionário pronto para gravação.

    Retorna {'erro': '...'} caso haja inconsistência nos dados obrigatórios.
    """
    rotina_limpa = str(rotina or "").strip()
    if not rotina_limpa:
        return {"erro": "rotina é obrigatória."}

    resumo_limpo = str(resumo or "").strip()
    if not resumo_limpo:
        return {"erro": "resumo é obrigatório."}

    status_limpo = str(status or STATUS_SUCESSO).strip().lower()
    if status_limpo not in STATUS_VALIDOS:
        return {"erro": f"status inválido: '{status}'. Permitidos: {sorted(STATUS_VALIDOS)}"}

    erro_limpo = str(erro).strip() if erro is not None and str(erro).strip() != "" else None
    if status_limpo == STATUS_ERRO and not erro_limpo:
        return {"erro": "erro é obrigatório quando status é 'erro'."}

    if contadores is not None and not isinstance(contadores, dict):
        return {"erro": "contadores deve ser um objeto/dicionário."}

    return {
        "rotina": rotina_limpa,
        "resumo": resumo_limpo,
        "status": status_limpo,
        "contadores": dict(contadores) if contadores else {},
        "erro": erro_limpo,
        "iniciado_em": str(iniciado_em).strip() if iniciado_em else None,
        "finalizado_em": str(finalizado_em).strip() if finalizado_em else None,
    }


def _to_iso(dt: object) -> str | None:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


# ---------------------------------------------------------------------------
# Operações Firestore (I/O)
# ---------------------------------------------------------------------------


def registrar(db, **kwargs) -> dict:
    """Valida e grava um novo registro de execução na coleção agent_runs."""
    doc_data = montar_registro(**kwargs)
    if "erro" in doc_data and "rotina" not in doc_data:
        return doc_data

    payload = dict(doc_data)
    payload["criado_em"] = firestore.SERVER_TIMESTAMP
    if not payload.get("finalizado_em"):
        payload["finalizado_em"] = firestore.SERVER_TIMESTAMP

    col = db.collection(COLLECTION)
    add_res = col.add(payload)

    if isinstance(add_res, tuple):
        run_id = add_res[1].id
    elif hasattr(add_res, "id"):
        run_id = add_res.id
    else:
        run_id = str(add_res)

    return {
        "status": "ok",
        "run_id": run_id,
        "registro": doc_data,
    }


def listar_recentes(db, rotina: str | None = None, limite: int = 20) -> dict:
    """Lista execuções recentes da coleção agent_runs.

    Filtra por rotina se especificada. Ordena por criado_em decrescente
    (mais recentes primeiro).
    """
    limite_ajustado = max(1, min(int(limite or 20), 50))
    query = db.collection(COLLECTION)
    if rotina:
        query = query.where("rotina", "==", str(rotina).strip())

    docs = list(query.stream())
    runs: list[dict] = []

    for doc in docs:
        d = doc.to_dict() or {}
        runs.append({
            "id": doc.id,
            "rotina": d.get("rotina"),
            "status": d.get("status"),
            "resumo": d.get("resumo"),
            "contadores": d.get("contadores") or {},
            "erro": d.get("erro"),
            "iniciado_em": _to_iso(d.get("iniciado_em")),
            "finalizado_em": _to_iso(d.get("finalizado_em")),
            "criado_em": _to_iso(d.get("criado_em")),
        })

    def _sort_key(x: dict) -> str:
        return x.get("criado_em") or ""

    runs.sort(key=_sort_key, reverse=True)
    return {
        "total": len(runs),
        "runs": runs[:limite_ajustado],
    }
