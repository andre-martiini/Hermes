"""Cost controls and telemetry helpers for Gemini usage in Hermes."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any


GEMINI_LIGHT_MODEL = os.environ.get("GEMINI_LIGHT_MODEL", "gemini-2.5-flash-lite")
GEMINI_BALANCED_MODEL = os.environ.get("GEMINI_BALANCED_MODEL", "gemini-3.1-flash-lite")
GEMINI_FRONTIER_MODEL = os.environ.get("GEMINI_FRONTIER_MODEL", "gemini-3.5-flash")
GEMINI_PRO_MODEL = os.environ.get("GEMINI_PRO_MODEL", "gemini-3.1-pro-preview")
GEMINI_ROUTING_MODEL = os.environ.get("GEMINI_ROUTING_MODEL", GEMINI_LIGHT_MODEL)
GEMINI_STRUCTURED_MODEL = os.environ.get("GEMINI_STRUCTURED_MODEL", GEMINI_LIGHT_MODEL)
GEMINI_DOCUMENT_MODEL = os.environ.get("GEMINI_DOCUMENT_MODEL", GEMINI_BALANCED_MODEL)
GEMINI_TRANSCRIPTION_MODEL = os.environ.get("GEMINI_TRANSCRIPTION_MODEL", GEMINI_BALANCED_MODEL)
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
GEMINI_TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")


# Text-token estimate for Gemini Developer API paid tier, USD per 1M tokens.
# This is telemetry only; billing source of truth remains Google/AI Studio.
_MODEL_PRICE_USD_PER_MTOK = {
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00, "cached_input": 0.15},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50, "cached_input": 0.025},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40, "cached_input": 0.01},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50, "cached_input": 0.03},
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00, "cached_input": 0.20},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00, "cached_input": 0.125},
    "gemini-embedding-001": {"input": 0.15, "output": 0.00, "cached_input": 0.00},
}


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    for method_name in ("model_dump", "to_json_dict", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                return _plain(method())
            except TypeError:
                try:
                    return _plain(method(exclude_none=True))
                except Exception:
                    pass
            except Exception:
                pass
    if hasattr(value, "__dict__"):
        return {
            str(k): _plain(v)
            for k, v in vars(value).items()
            if not str(k).startswith("_") and v is not None
        }
    return str(value)


def _safe_key(value: str | None) -> str:
    key = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "unknown")).strip("_")
    return (key or "unknown")[:90]


def _usage_dict(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return {}
    data = _plain(usage)
    return data if isinstance(data, dict) else {}


def _usage_int(usage: dict[str, Any], *names: str) -> int:
    for name in names:
        value = usage.get(name)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return 0


def _estimate_usd(model: str, usage: dict[str, Any]) -> float | None:
    price = _MODEL_PRICE_USD_PER_MTOK.get(model)
    if not price:
        return None
    input_tokens = _usage_int(usage, "prompt_token_count", "promptTokenCount")
    output_tokens = _usage_int(usage, "candidates_token_count", "candidatesTokenCount")
    cached_tokens = _usage_int(
        usage,
        "cached_content_token_count",
        "cachedContentTokenCount",
    )
    billable_input = max(0, input_tokens - cached_tokens)
    cost = (
        billable_input * price["input"]
        + cached_tokens * price.get("cached_input", price["input"])
        + output_tokens * price["output"]
    ) / 1_000_000
    return round(cost, 8)


def log_gemini_usage(
    response: Any,
    *,
    model: str,
    feature: str,
    db: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Log Gemini token usage without ever failing the caller."""
    usage = _usage_dict(response)
    total_tokens = _usage_int(usage, "total_token_count", "totalTokenCount")
    estimated_usd = _estimate_usd(model, usage)
    payload = {
        "feature": feature,
        "model": model,
        "usage": usage,
        "estimated_usd": estimated_usd,
    }
    if extra:
        payload["extra"] = extra
    try:
        print(f"[GeminiUsage] {json.dumps(payload, ensure_ascii=False)}")
    except Exception:
        print(f"[GeminiUsage] feature={feature} model={model} total_tokens={total_tokens}")

    if db is None or os.environ.get("HERMES_GEMINI_USAGE_FIRESTORE", "1") == "0":
        return payload

    try:
        from firebase_admin import firestore

        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        doc = (
            db.collection("system_usage")
            .document("gemini")
            .collection("daily")
            .document(day)
        )
        model_key = _safe_key(model)
        feature_key = _safe_key(feature)
        updates = {
            "date": day,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "calls": firestore.Increment(1),
            f"models.{model_key}.calls": firestore.Increment(1),
            f"features.{feature_key}.calls": firestore.Increment(1),
        }
        prompt_tokens = _usage_int(usage, "prompt_token_count", "promptTokenCount")
        output_tokens = _usage_int(usage, "candidates_token_count", "candidatesTokenCount")
        cached_tokens = _usage_int(
            usage,
            "cached_content_token_count",
            "cachedContentTokenCount",
        )
        if total_tokens:
            updates["tokens.total"] = firestore.Increment(total_tokens)
            updates[f"models.{model_key}.tokens_total"] = firestore.Increment(total_tokens)
            updates[f"features.{feature_key}.tokens_total"] = firestore.Increment(total_tokens)
        if prompt_tokens:
            updates["tokens.input"] = firestore.Increment(prompt_tokens)
        if output_tokens:
            updates["tokens.output"] = firestore.Increment(output_tokens)
        if cached_tokens:
            updates["tokens.cached_input"] = firestore.Increment(cached_tokens)
        if estimated_usd is not None:
            updates["estimated_usd"] = firestore.Increment(float(estimated_usd))
        doc.set(updates, merge=True)
    except Exception as exc:
        print(f"[GeminiUsage] Firestore aggregate failed: {exc}")
    return payload


def generate_content_logged(
    client: Any,
    *,
    model: str,
    contents: Any,
    feature: str,
    db: Any = None,
    **kwargs: Any,
) -> Any:
    response = client.models.generate_content(model=model, contents=contents, **kwargs)
    log_gemini_usage(response, model=model, feature=feature, db=db)
    return response


def send_message_logged(
    chat: Any,
    message: Any,
    *,
    model: str,
    feature: str,
    db: Any = None,
) -> Any:
    response = chat.send_message(message)
    log_gemini_usage(response, model=model, feature=feature, db=db)
    return response


def embed_content_logged(
    client: Any,
    *,
    model: str,
    contents: Any,
    feature: str,
    db: Any = None,
    **kwargs: Any,
) -> Any:
    response = client.models.embed_content(model=model, contents=contents, **kwargs)
    log_gemini_usage(response, model=model, feature=feature, db=db)
    return response


def check_and_increment_limit(
    db: Any,
    user_id: str | None,
    feature: str,
    max_limit: int,
) -> bool:
    """Checks if the user has reached the daily limit for a specific feature.
    If not, increments it and returns True. If yes, returns False.
    """
    if not user_id or db is None:
        return True

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        from firebase_admin import firestore

        ref = (
            db.collection("system_usage")
            .document("user_limits")
            .collection(user_id)
            .document(day)
        )
        doc = ref.get()
        current = 0
        if doc.exists:
            current = doc.to_dict().get(feature, 0)

        if current >= max_limit:
            return False

        ref.set({
            feature: firestore.Increment(1),
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        return True
    except Exception as e:
        print(f"[GeminiUsage] Failed to check/increment limit for {user_id}/{feature}: {e}")
        return True  # Fail-open if Firestore fails

