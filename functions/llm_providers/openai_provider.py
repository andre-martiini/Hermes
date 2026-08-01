"""
Cliente fino para a OpenAI Responses API — usado apenas para o A/B test do
GPT-5.6 Luna (reasoning effort baixo) contra os modelos Gemini padrão do
Hermes. Espelha o padrão de telemetria de custo de gemini_cost_controls.py
para permitir comparação de custo lado a lado entre os dois providers.

Escopo deliberadamente mínimo: sem tool-calling, sem streaming — só o
suficiente para classificações/extrações curtas como as do roteador de
intenção. Se o A/B validar o Luna para mais casos, isso cresce depois.
"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timezone
from typing import Any

LUNA_MODEL = os.environ.get("OPENAI_LUNA_MODEL", "gpt-5.6-luna")
LUNA_DEFAULT_EFFORT = os.environ.get("OPENAI_LUNA_REASONING_EFFORT", "low")

# USD por 1M tokens, tier padrão (pós corte de 80% em 30/jul/2026). Telemetria
# apenas — fonte da verdade de cobrança continua sendo o dashboard da OpenAI.
_MODEL_PRICE_USD_PER_MTOK = {
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20},
}


def _safe_key(value: str | None) -> str:
    key = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "unknown")).strip("_")
    return (key or "unknown")[:90]


def should_use_luna_ab(pct_env: str, default: str = "0") -> bool:
    """Sorteia se esta chamada deve ir para o Luna em vez do Gemini, conforme
    a porcentagem em `pct_env` (0-100). Desativado por padrão (0%) — precisa
    ser ligado explicitamente por env var para começar o A/B."""
    try:
        pct = float(os.environ.get(pct_env, default))
    except ValueError:
        pct = 0.0
    return pct > 0 and random.random() * 100 < pct


def _estimate_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = _MODEL_PRICE_USD_PER_MTOK.get(model)
    if not price:
        return None
    cost = (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000
    return round(cost, 8)


def log_openai_usage(
    response: Any,
    *,
    model: str,
    feature: str,
    db: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Loga uso de tokens da OpenAI no mesmo formato de log_gemini_usage, em
    uma coleção paralela (system_usage/openai), para comparar custo real
    entre os dois providers durante o A/B."""
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    reasoning_tokens = 0
    output_details = getattr(usage, "output_tokens_details", None)
    if output_details is not None:
        reasoning_tokens = getattr(output_details, "reasoning_tokens", 0) or 0

    estimated_usd = _estimate_usd(model, input_tokens, output_tokens)
    payload = {
        "feature": feature,
        "provider": "openai",
        "model": model,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
        },
        "estimated_usd": estimated_usd,
    }
    if extra:
        payload["extra"] = extra
    try:
        print(f"[OpenAIUsage] {json.dumps(payload, ensure_ascii=False)}")
    except Exception:
        print(f"[OpenAIUsage] feature={feature} model={model} tokens={input_tokens + output_tokens}")

    if db is None or os.environ.get("HERMES_OPENAI_USAGE_FIRESTORE", "1") == "0":
        return payload

    try:
        from firebase_admin import firestore

        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        doc = (
            db.collection("system_usage")
            .document("openai")
            .collection("daily")
            .document(day)
        )
        model_key = _safe_key(model)
        feature_key = _safe_key(feature)
        tokens_total = input_tokens + output_tokens

        updates: dict[str, Any] = {
            "date": day,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "calls": firestore.Increment(1),
            "models": {model_key: {"calls": firestore.Increment(1), "tokens_total": firestore.Increment(tokens_total)}},
            "features": {feature_key: {"calls": firestore.Increment(1), "tokens_total": firestore.Increment(tokens_total)}},
            "tokens": {
                "input": firestore.Increment(input_tokens),
                "output": firestore.Increment(output_tokens),
                "reasoning": firestore.Increment(reasoning_tokens),
            },
        }
        if estimated_usd is not None:
            updates["estimated_usd"] = firestore.Increment(float(estimated_usd))
        doc.set(updates, merge=True)
    except Exception as exc:
        print(f"[OpenAIUsage] Firestore aggregate failed: {exc}")
    return payload


def generate_text_logged(
    client: Any,
    *,
    model: str,
    input_text: str,
    feature: str,
    instructions: str | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    db: Any = None,
) -> Any:
    """Chamada mínima à Responses API com telemetria de custo. Propaga
    qualquer exceção — quem chama decide o que fazer (aqui, sempre fail-open
    igual ao lado Gemini)."""
    kwargs: dict[str, Any] = {
        "model": model,
        "input": input_text,
        "reasoning": {"effort": reasoning_effort or LUNA_DEFAULT_EFFORT},
    }
    if instructions:
        kwargs["instructions"] = instructions
    if max_output_tokens:
        kwargs["max_output_tokens"] = max_output_tokens

    response = client.responses.create(**kwargs)
    log_openai_usage(response, model=model, feature=feature, db=db)
    return response
