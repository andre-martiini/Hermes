import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from database import get_db

LOCAL_TZ = ZoneInfo(os.getenv("HERMES_TIMEZONE", "America/Sao_Paulo"))

COPILOT_SOUL_DEFAULT = {
    "tone": "Consultivo, analitico e objetivo.",
    "detail_level": "Alto o suficiente para orientar execucao, sem prolixidade.",
    "interaction_style": "Clareza, transparencia sobre incertezas e foco em proximos passos concretos.",
}


def build_voice_context() -> str:
    db = get_db()
    sections = [
        _format_core_context(db),
        _format_user_profile(db),
        _format_recent_memories(db),
    ]
    return "\n\n".join(section for section in sections if section.strip())


def _format_core_context(db) -> str:
    core = _get_doc_dict(db, "system", "copilot_core")
    soul = _get_doc_dict(db, "system", "copilot_soul") or COPILOT_SOUL_DEFAULT

    lines = ["## CONTEXTO CENTRAL DO HERMES"]
    if core.get("content"):
        lines.append(f"- nucleo: {_clean(core.get('content'), 900)}")

    soul_content = soul.get("content")
    if soul_content:
        lines.append(f"- alma/persona: {_clean(soul_content, 700)}")
    else:
        for key in ("tone", "detail_level", "interaction_style"):
            if soul.get(key):
                lines.append(f"- {key}: {_clean(soul.get(key), 260)}")

    lines.append(
        "- modo_voz: responda como conversa falada, priorizando brevidade, clareza e continuidade."
    )
    return "\n".join(lines)


def _format_user_profile(db) -> str:
    uid = os.getenv("HERMES_DEFAULT_USER_ID", "").strip()
    user_doc = None

    if uid:
        snap = db.collection("usuarios").document(uid).get()
        if snap.exists:
            user_doc = {"id": snap.id, **(snap.to_dict() or {})}

    if not user_doc:
        for snap in db.collection("usuarios").limit(1).stream():
            user_doc = {"id": snap.id, **(snap.to_dict() or {})}
            break

    if not user_doc:
        return "## PERFIL DO USUARIO\n- perfil ainda nao encontrado em usuarios."

    ai_profile = user_doc.get("ai_profile") or {}
    lines = ["## PERFIL DO USUARIO"]
    for key in ("nome", "cargo", "setor", "email"):
        value = ai_profile.get(key) or user_doc.get(key)
        if value:
            lines.append(f"- {key}: {_clean(value, 220)}")

    preferences = ai_profile.get("preferences")
    if preferences:
        lines.append(f"- preferencias: {_clean(json.dumps(preferences, ensure_ascii=False), 420)}")

    history = ai_profile.get("historico_deduzido") or []
    if history:
        compact = [
            {
                "texto": item.get("texto"),
                "at": item.get("at"),
            }
            for item in history[-5:]
            if item.get("texto")
        ]
        if compact:
            lines.append(
                f"- historico_deduzido_recente: {_clean(json.dumps(compact, ensure_ascii=False), 700)}"
            )

    if len(lines) == 1:
        lines.append(f"- id: {user_doc['id']}")
    return "\n".join(lines)


def _format_recent_memories(db, limit: int = 8) -> str:
    memories = []
    try:
        docs = (
            db.collection("knowledge_nodes")
            .order_by("data_criacao", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
    except Exception:
        docs = db.collection("knowledge_nodes").limit(limit).stream()

    for snap in docs:
        data = snap.to_dict() or {}
        content = (
            data.get("texto_memoria")
            or data.get("fato")
            or data.get("resumo")
            or data.get("titulo")
            or ""
        )
        if not content:
            continue
        memories.append(
            f"- [{data.get('tipo') or data.get('categoria') or 'memoria'}] {_clean(content, 280)}"
        )

    if not memories:
        return ""
    return "## MEMORIAS RECENTES DO HERMES\n" + "\n".join(memories)


def _get_doc_dict(db, collection: str, document: str) -> dict:
    try:
        snap = db.collection(collection).document(document).get()
        if snap.exists:
            return snap.to_dict() or {}
    except Exception:
        return {}
    return {}


def _clean(value, max_chars: int) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."
