"""Telemetria completa de uso de IA (DEV-2026-0003, PR 2).

Fecha um furo do relatório de custos:

1. **Gemini fora do wrapper.** ~50 chamadas do código vão direto em
   ``client.models.generate_content(...)`` (main.py, knowledge_graph.py,
   fatura_cartao.py, tools/...), passando ao largo de ``generate_content_logged``
   e, portanto, de ``system_usage/gemini``. Este módulo intercepta, na classe
   ``google.genai.models.Models``, os métodos ``generate_content``,
   ``generate_content_stream`` e ``embed_content`` e registra o uso via
   ``gemini_cost_controls.log_gemini_usage`` com ``feature="auto:<modulo>.<funcao>"``
   (o chamador é descoberto pela pilha). Chamadas que já passam por
   ``generate_content_logged`` / ``send_message_logged`` / ``embed_content_logged``
   são ignoradas aqui, para não contar duas vezes. ``Chat.send_message`` usa
   ``Models.generate_content`` por baixo, então chats diretos também ficam cobertos.

A telemetria de Claude (``system_usage/claude``) saiu em 2026-09-19, quando o Hermes deixou
a Anthropic: os agentes passaram a usar ``llm_providers.gemini_provider``, que já registra
pelo ``generate_content_logged``. O histórico antigo em ``system_usage/claude`` segue no Firestore.

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
from zoneinfo import ZoneInfo

# Ver gemini_cost_controls.TZ — mesmo motivo: system_usage é indexado pelo dia
# civil em America/Sao_Paulo, não UTC (achado 5 de 04/09/2026).
TZ = ZoneInfo("America/Sao_Paulo")

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
_LOGGED_WRAPPERS = {"generate_content_logged", "send_message_logged", "embed_content_logged"}


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
def _log_gemini(response: Any, model: str, *, usage_override: dict[str, Any] | None = None) -> None:
    try:
        from gemini_cost_controls import log_gemini_usage

        log_gemini_usage(
            response,
            model=str(model),
            feature=f"auto:{caller_label()}",
            db=_get_db(),
            usage_override=usage_override,
        )
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
                model = kwargs.get("model") or (args[0] if args else "unknown")
                from gemini_cost_controls import _usage_dict, count_input_tokens_free

                usage = _usage_dict(response)
                if not usage:
                    # EmbedContentResponse não traz usage_metadata na Gemini
                    # Developer API (achado 6 de 04/09/2026) — sem isso a
                    # chamada saía do relatório com custo zero, sempre.
                    # count_tokens é gratuito; usamos como fallback. `self`
                    # aqui já É o objeto Models (mesmo que client.models).
                    contents = kwargs.get("contents") or (args[1] if len(args) > 1 else None)
                    if contents is not None:
                        tokens = count_input_tokens_free(self, model=model, contents=contents)
                        if tokens:
                            usage = {"prompt_token_count": tokens, "total_token_count": tokens}
                _log_gemini(response, model, usage_override=usage or None)
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
