"""Telemetria completa de uso de IA (DEV-2026-0003, PR 2).

Fecha dois furos do relatório de custos:

1. **Gemini fora do wrapper.** ~50 chamadas do código vão direto em
   ``client.models.generate_content(...)`` (main.py, knowledge_graph.py,
   fatura_cartao.py, tools/...), passando ao largo de ``generate_content_logged``
   e, portanto, de ``system_usage/gemini``. Este módulo intercepta, na classe
   ``google.genai.models.Models``, os métodos ``generate_content``,
   ``generate_content_stream`` e ``embed_content`` e registra o uso via
   ``gemini_cost_controls.log_gemini_usage`` com ``feature="auto:<modulo>.<funcao>"``
   (o chamador é descoberto pela pilha). Chamadas que já passam por
   ``generate_content_logged`` / ``send_message_logged`` são ignoradas aqui, para
   não contar duas vezes. ``Chat.send_message`` usa ``Models.generate_content``
   por baixo, então chats diretos também ficam cobertos.

2. **Claude sem telemetria.** ``log_claude_usage`` grava em
   ``system_usage/claude/daily/{dia}`` no mesmo formato de ``system_usage/gemini``
   (``calls``, ``tokens{input,output,cache_read,cache_write,total}``, ``models``,
   ``features``, ``estimated_usd``). É chamado por ``llm_providers.claude_provider``
   ao fim de cada ``run_tool_loop``. Preços (US$/Mtok) em ``_CLAUDE_PRICE_USD_PER_MTOK``
   — telemetria, não fatura; ajustar via env ``HERMES_CLAUDE_PRICES_JSON``
   (``{"claude-fable-5": {"input": 5, "output": 25, "cache_read": 0.5, "cache_write": 6.25}}``).

Instalação: ``install()`` é idempotente e é chamada no fim de
``gemini_cost_controls`` (importado por ``main.py`` em todas as functions).
Desligar: ``HERMES_LLM_USAGE_HOOKS=0``. Nenhum erro deste módulo chega ao
código de negócio.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

_installed = False
_db_factory = None  # injetável nos testes

_SKIP_MODULE_PREFIXES = (
    "google.",
    "llm_usage_hooks",
    "gemini_cost_controls",
    "concurrent.",
    "threading",
    "asyncio",
    "importlib",
    "unittest",
)
_LOGGED_WRAPPERS = {"generate_content_logged", "send_message_logged"}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _safe(value: Any) -> str:
    key = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "unknown")).strip("_")
    return (key or "unknown")[:80]


def _get_db():
    if _db_factory is not None:
        return _db_factory()
    try:
        from firebase_admin import firestore

        return firestore.client()
    except Exception:
        return None


def inside_logged_wrapper() -> bool:
    """True se a chamada atual veio de dentro de generate_content_logged/send_message_logged."""
    frame = sys._getframe(1)
    while frame is not None:
        if frame.f_code.co_name in _LOGGED_WRAPPERS and "gemini_cost_controls" in str(frame.f_globals.get("__name__", "")):
            return True
        frame = frame.f_back
    return False


def caller_label() -> str:
    """``modulo.funcao`` do primeiro frame de código da aplicação na pilha."""
    frame = sys._getframe(1)
    while frame is not None:
        module = str(frame.f_globals.get("__name__", "") or "")
        if module and not module.startswith(_SKIP_MODULE_PREFIXES):
            return _safe(f"{module.rsplit('.', 1)[-1]}.{frame.f_code.co_name}")
        frame = frame.f_back
    return "unknown"


# --------------------------------------------------------------------------- #
# Gemini: chamadas diretas
# --------------------------------------------------------------------------- #
def _log_gemini(response: Any, model: str) -> None:
    try:
        from gemini_cost_controls import log_gemini_usage

        log_gemini_usage(response, model=str(model), feature=f"auto:{caller_label()}", db=_get_db())
    except Exception as exc:
        print(f"[LLMUsageHooks] falha ao registrar uso Gemini: {exc}")


class _LoggingStream:
    """Envelopa generate_content_stream: registra o uso do último chunk ao terminar."""

    def __init__(self, inner: Any, model: str):
        self._inner = inner
        self._model = model
        self._last = None
        self._done = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self._inner)
        except StopIteration:
            self._finish()
            raise
        if getattr(chunk, "usage_metadata", None) is not None:
            self._last = chunk
        return chunk

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        if self._last is not None:
            _log_gemini(self._last, self._model)

    def close(self) -> None:
        self._finish()
        close = getattr(self._inner, "close", None)
        if callable(close):
            close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _wrap_generate_content(original):
    def generate_content(self, *args, **kwargs):
        response = original(self, *args, **kwargs)
        try:
            if not inside_logged_wrapper():
                _log_gemini(response, kwargs.get("model") or "unknown")
        except Exception:
            pass
        return response

    generate_content.__wrapped_by_llm_usage_hooks__ = True
    return generate_content


def _wrap_generate_content_stream(original):
    def generate_content_stream(self, *args, **kwargs):
        stream = original(self, *args, **kwargs)
        try:
            if inside_logged_wrapper():
                return stream
            return _LoggingStream(stream, kwargs.get("model") or "unknown")
        except Exception:
            return stream

    generate_content_stream.__wrapped_by_llm_usage_hooks__ = True
    return generate_content_stream


def _wrap_embed_content(original):
    def embed_content(self, *args, **kwargs):
        response = original(self, *args, **kwargs)
        try:
            if not inside_logged_wrapper():
                # EmbedContentResponse não traz usage_metadata: registra a chamada
                # (calls +1) com o modelo, sem tokens.
                _log_gemini(response, kwargs.get("model") or "unknown")
        except Exception:
            pass
        return response

    embed_content.__wrapped_by_llm_usage_hooks__ = True
    return embed_content


def install(models_cls: Any = None) -> bool:
    """Instala os hooks na classe Models do google-genai (idempotente)."""
    global _installed
    if os.environ.get("HERMES_LLM_USAGE_HOOKS", "1") == "0":
        return False
    if models_cls is None:
        if _installed:
            return True
        try:
            from google.genai import models as _models

            models_cls = _models.Models
        except Exception as exc:
            print(f"[LLMUsageHooks] google-genai indisponível, hooks não instalados: {exc}")
            return False

    def _patch(name, wrapper):
        current = getattr(models_cls, name, None)
        if current is None or getattr(current, "__wrapped_by_llm_usage_hooks__", False):
            return
        setattr(models_cls, name, wrapper(current))

    _patch("generate_content", _wrap_generate_content)
    _patch("generate_content_stream", _wrap_generate_content_stream)
    _patch("embed_content", _wrap_embed_content)
    _installed = True
    return True


# --------------------------------------------------------------------------- #
# Claude
# --------------------------------------------------------------------------- #
# US$ por 1M tokens. Estimativa para telemetria; a fatura da Anthropic é a fonte
# de verdade. Sobrescrever com HERMES_CLAUDE_PRICES_JSON.
_CLAUDE_PRICE_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-fable-5": {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    "claude-opus-4-8": {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    "claude-opus-4-5": {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write": 1.25},
}


def claude_prices() -> dict[str, dict[str, float]]:
    table = dict(_CLAUDE_PRICE_USD_PER_MTOK)
    raw = os.environ.get("HERMES_CLAUDE_PRICES_JSON")
    if raw:
        try:
            for model, prices in json.loads(raw).items():
                table[str(model)] = {k: float(v) for k, v in dict(prices).items()}
        except Exception as exc:
            print(f"[LLMUsageHooks] HERMES_CLAUDE_PRICES_JSON inválido: {exc}")
    return table


def _match_price(model: str, table: dict[str, dict[str, float]]) -> dict[str, float] | None:
    model = (model or "").lower()
    if model in table:
        return table[model]
    # "claude-opus-4-8-20260301" → prefixo mais longo que case
    best = None
    for key in table:
        if model.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return table.get(best) if best else None


def estimate_claude_usd(model: str, usage: dict[str, Any]) -> float | None:
    prices = _match_price(model, claude_prices())
    if not prices:
        return None
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    cache_write = int(usage.get("cache_creation_input_tokens") or 0)
    usd = (
        inp * prices.get("input", 0.0)
        + out * prices.get("output", 0.0)
        + cache_read * prices.get("cache_read", 0.0)
        + cache_write * prices.get("cache_write", 0.0)
    ) / 1_000_000
    return round(usd, 6)


def build_claude_usage_update(usage: dict[str, Any], model: str, feature: str, day: str) -> dict[str, Any]:
    """Payload de ``set(merge=True)`` com Increment — mesmo formato de system_usage/gemini."""
    from google.cloud.firestore_v1 import Increment, SERVER_TIMESTAMP

    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    cache_write = int(usage.get("cache_creation_input_tokens") or 0)
    total = inp + out + cache_read + cache_write
    rounds = int(usage.get("rounds") or 1)
    estimated = estimate_claude_usd(model, usage)

    tokens: dict[str, Any] = {}
    if inp:
        tokens["input"] = Increment(inp)
    if out:
        tokens["output"] = Increment(out)
    if cache_read:
        tokens["cache_read"] = Increment(cache_read)
    if cache_write:
        tokens["cache_write"] = Increment(cache_write)
    if total:
        tokens["total"] = Increment(total)

    update: dict[str, Any] = {
        "date": day,
        "updated_at": SERVER_TIMESTAMP,
        "calls": Increment(1),
        "api_rounds": Increment(rounds),
        "models": {_safe(model): {"calls": Increment(1), "tokens_total": Increment(total)}},
        "features": {_safe(feature): {"calls": Increment(1), "tokens_total": Increment(total)}},
    }
    if tokens:
        update["tokens"] = tokens
    if estimated is not None:
        update["estimated_usd"] = Increment(float(estimated))
        update["models"][_safe(model)]["estimated_usd"] = Increment(float(estimated))
        update["features"][_safe(feature)]["estimated_usd"] = Increment(float(estimated))
    return update


def log_claude_usage(usage: dict[str, Any], *, model: str, feature: str, db: Any = None) -> dict[str, Any] | None:
    """Registra um turno completo do Claude (todas as rodadas) em system_usage/claude."""
    try:
        estimated = estimate_claude_usd(model, usage)
        payload = {"feature": feature, "model": model, "usage": dict(usage), "estimated_usd": estimated}
        print(f"[ClaudeUsage] {json.dumps(payload, ensure_ascii=False, default=str)}")
        if os.environ.get("HERMES_CLAUDE_USAGE_FIRESTORE", "1") == "0":
            return payload
        db = db or _get_db()
        if db is None:
            return payload
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        db.collection("system_usage").document("claude").collection("daily").document(day).set(
            build_claude_usage_update(usage, model, feature, day), merge=True
        )
        return payload
    except Exception as exc:
        print(f"[ClaudeUsage] falha ao registrar uso: {exc}")
        return None
