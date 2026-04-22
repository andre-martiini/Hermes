from datetime import datetime, timezone, timedelta

from firebase_admin import firestore

_SESSION_TTL_MINUTES = 30


def get_session(db, chat_id: str) -> dict | None:
    doc = db.collection("telegram_sessions").document(chat_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    expires_at = data.get("expires_at")
    if expires_at:
        now = datetime.now(timezone.utc)
        exp_ts = expires_at.timestamp() if hasattr(expires_at, "timestamp") else 0
        if now.timestamp() > exp_ts:
            doc.reference.delete()
            return None
    return data


def save_slot_session(
    db,
    chat_id: str,
    tool_name: str,
    slots: dict,
    required_params: list,
    trace_id: str,
    history: list | None = None,
    awaiting_confirmation: bool = False,
):
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_SESSION_TTL_MINUTES)
    db.collection("telegram_sessions").document(chat_id).set({
        "chat_id": chat_id,
        "mode": "slot_filling",
        "tool_name": tool_name,
        "slots": slots,
        "required_params": required_params,
        "awaiting_confirmation": awaiting_confirmation,
        "trace_id": trace_id,
        "history": history or [],
        "updated_at": firestore.SERVER_TIMESTAMP,
        "expires_at": expires_at,
    })


def save_general_session(db, chat_id: str, history: list, trace_id: str):
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_SESSION_TTL_MINUTES)
    db.collection("telegram_sessions").document(chat_id).set({
        "chat_id": chat_id,
        "mode": "general",
        "history": history,
        "trace_id": trace_id,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "expires_at": expires_at,
    })


def clear_session(db, chat_id: str):
    db.collection("telegram_sessions").document(chat_id).delete()


def trim_history(history: list, max_turns: int = 5) -> list:
    max_entries = max_turns * 2
    return history[-max_entries:] if len(history) > max_entries else history
