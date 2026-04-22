import time
from typing import Optional

_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL = 300  # 5 minutos


def is_authorized(db, chat_id: str, env_fallback: Optional[str] = None) -> bool:
    if env_fallback and chat_id == env_fallback:
        return True

    now = time.monotonic()
    cached = _cache.get(chat_id)
    if cached:
        authorized, expires_at = cached
        if now < expires_at:
            return authorized

    try:
        doc = db.collection("whitelist").document(chat_id).get()
        authorized = doc.exists and (doc.to_dict() or {}).get("active", False)
    except Exception:
        authorized = False

    _cache[chat_id] = (authorized, now + _CACHE_TTL)
    return authorized
