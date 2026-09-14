"""Cost controls and telemetry helpers for Gemini usage in Hermes."""

from __future__ import annotations

import json
import os
import re
import copy
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

# Dia de faturamento visto pelo André é o dia civil em America/Sao_Paulo, não o
# dia UTC. Os documentos diários de system_usage (aqui e em llm_usage_hooks.py/
# firestore_metrics.py) são indexados por este fuso — antes eram indexados por
# UTC, o que jogava o consumo das 21h-24h BRT (0h-3h UTC do dia seguinte) para
# o documento do dia seguinte (achado 5 de 04/09/2026).
TZ = ZoneInfo("America/Sao_Paulo")


GEMINI_LIGHT_MODEL = os.environ.get("GEMINI_LIGHT_MODEL", "gemini-3.5-flash-lite")
GEMINI_BALANCED_MODEL = os.environ.get("GEMINI_BALANCED_MODEL", "gemini-3.5-flash-lite")
GEMINI_FRONTIER_MODEL = os.environ.get("GEMINI_FRONTIER_MODEL", "gemini-3.6-flash")
GEMINI_PRO_MODEL = os.environ.get("GEMINI_PRO_MODEL", "gemini-3.1-pro-preview")
GEMINI_ROUTING_MODEL = os.environ.get("GEMINI_ROUTING_MODEL", GEMINI_LIGHT_MODEL)
GEMINI_STRUCTURED_MODEL = os.environ.get("GEMINI_STRUCTURED_MODEL", GEMINI_LIGHT_MODEL)
GEMINI_DOCUMENT_MODEL = os.environ.get("GEMINI_DOCUMENT_MODEL", GEMINI_BALANCED_MODEL)
GEMINI_TRANSCRIPTION_MODEL = os.environ.get("GEMINI_TRANSCRIPTION_MODEL", GEMINI_BALANCED_MODEL)
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
GEMINI_TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
GEMINI_FLEX_TIMEOUT_MS = int(os.environ.get("GEMINI_FLEX_TIMEOUT_MS", "600000"))
GEMINI_FLEX_FALLBACK_TO_STANDARD = os.environ.get("GEMINI_FLEX_FALLBACK_TO_STANDARD", "1") != "0"


_DEFAULT_FLEX_FEATURES = {
    "knowledge_graph.artifact_text_extraction",
    "knowledge_graph.artifact_summary",
    "security_portals.pgd_from_diaries",
    "security_portals.pgd_from_raw_text",
    "telegram_extended.report_skeleton",
    "telegram_extended.report_section",
    "simulation.orchestrator.plan",
}


# Text-token estimate for Gemini Developer API paid tier, USD per 1M tokens.
# This is telemetry only; billing source of truth remains Google/AI Studio.
_MODEL_PRICE_USD_PER_MTOK = {
    "gemini-3.6-flash": {"input": 1.50, "output": 7.50, "cached_input": 0.15},
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50, "cached_input": 0.03},
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00, "cached_input": 0.15},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50, "cached_input": 0.025},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40, "cached_input": 0.01},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50, "cached_input": 0.03},
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00, "cached_input": 0.20},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00, "cached_input": 0.125},
    "gemini-embedding-001": {"input": 0.15, "output": 0.00, "cached_input": 0.00},
    # Modelos que faltavam na tabela (achado 2 de 04/09/2026) — toda chamada
    # com eles saía do relatório como custo zero. Preços confirmados em
    # ai.google.dev/gemini-api/docs/pricing (checado em 14/09/2026); sem
    # "cached_input" publicado para nenhum dos dois, então o fallback em
    # _estimate_usd usa o preço de input normal para tokens em cache.
    # Saída de imagem é cobrada por token, mas o próprio Google já resolve a
    # tabela para um preço fixo por imagem por faixa de resolução (0,5K/1K/2K/4K)
    # — o preço por token abaixo reproduz esse valor quando aplicado ao
    # candidates_token_count devolvido pela API.
    "gemini-3.1-flash-image": {"input": 0.50, "output": 60.00},
    # O modelo legado continua listado na página oficial de preços (verificado
    # em 14/09/2026): US$0,50/Mtok de texto de entrada e US$10/Mtok de áudio
    # de saída no tier Standard. GEMINI_TTS_MODEL ainda o usa como padrão.
    "gemini-2.5-flash-preview-tts": {"input": 0.50, "output": 10.00},
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


def _csv_env_set(name: str) -> set[str] | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}


def should_use_flex(feature: str) -> bool:
    """Return whether a feature should use Gemini Flex inference."""
    if os.environ.get("HERMES_GEMINI_FLEX_ENABLED", "1") == "0":
        return False

    disabled = _csv_env_set("HERMES_GEMINI_FLEX_DISABLED_FEATURES") or set()
    if feature in disabled:
        return False

    configured = _csv_env_set("HERMES_GEMINI_FLEX_FEATURES")
    allowed = configured if configured is not None else _DEFAULT_FLEX_FEATURES
    return "*" in allowed or feature in allowed


def _is_flex_capacity_error(error: Exception) -> bool:
    code = getattr(error, "code", None)
    status = str(getattr(error, "status", "") or "").upper()
    full_text = f"{error} {status}".upper()
    return code in {429, 503} or any(
        token in full_text
        for token in (
            "RESOURCE_EXHAUSTED",
            "TOO MANY REQUESTS",
            "429",
            "UNAVAILABLE",
            "SERVICE UNAVAILABLE",
            "503",
        )
    )


def _plain_config(config: Any) -> dict[str, Any]:
    data = _plain(config)
    return data if isinstance(data, dict) else {}


def _with_service_tier(config: Any, tier: str | None) -> Any:
    """Return a config with service_tier set, preserving existing options when possible."""
    if tier is None:
        return config

    if config is None:
        return {
            "service_tier": tier,
            "http_options": {"timeout": GEMINI_FLEX_TIMEOUT_MS},
        }

    if isinstance(config, dict):
        updated = dict(config)
        updated["service_tier"] = tier
        http_options = dict(updated.get("http_options") or {})
        http_options.setdefault("timeout", GEMINI_FLEX_TIMEOUT_MS)
        updated["http_options"] = http_options
        return updated

    http_options = getattr(config, "http_options", None)
    updates: dict[str, Any] = {"service_tier": tier}
    if http_options is None:
        updates["http_options"] = {"timeout": GEMINI_FLEX_TIMEOUT_MS}

    model_copy = getattr(config, "model_copy", None)
    if callable(model_copy):
        try:
            return model_copy(update=updates)
        except Exception:
            pass

    try:
        cloned = copy.copy(config)
        for key, value in updates.items():
            setattr(cloned, key, value)
        return cloned
    except Exception:
        data = _plain_config(config)
        data.update(updates)
        if "http_options" not in data:
            data["http_options"] = {"timeout": GEMINI_FLEX_TIMEOUT_MS}
        return data


def _set_request_config(kwargs: dict[str, Any], config: Any) -> dict[str, Any]:
    updated = dict(kwargs)
    updated["config"] = config
    return updated


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


def _estimate_usd(model: str, usage: dict[str, Any], service_tier: str | None = None) -> float | None:
    price = _MODEL_PRICE_USD_PER_MTOK.get(model)
    if not price:
        return None
    input_tokens = _usage_int(usage, "prompt_token_count", "promptTokenCount")
    output_tokens = _usage_int(usage, "candidates_token_count", "candidatesTokenCount")
    # Tokens de raciocínio (extended thinking) são cobrados à MESMA taxa dos
    # tokens de saída — confirmado em ai.google.dev/gemini-api/docs/thinking
    # ("response pricing is the sum of output tokens and thinking tokens") e
    # na própria tabela de preços, cuja coluna de saída é rotulada "Output
    # price (including thinking tokens)". Sem somar aqui (achado 3 de
    # 04/09/2026), o custo de todo raciocínio ficava fora da conta — foi o que
    # explicou a diferença de 4.177 tokens no total_token_count de 03/09 que
    # não batia com prompt+candidates.
    thoughts_tokens = _usage_int(usage, "thoughts_token_count", "thoughtsTokenCount")
    cached_tokens = _usage_int(
        usage,
        "cached_content_token_count",
        "cachedContentTokenCount",
    )
    billable_input = max(0, input_tokens - cached_tokens)
    cost = (
        billable_input * price["input"]
        + cached_tokens * price.get("cached_input", price["input"])
        + (output_tokens + thoughts_tokens) * price["output"]
    ) / 1_000_000
    # NÃO aplicamos mais desconto de Flex aqui (achado 4 de 04/09/2026,
    # revisitado em 14/09/2026): a resposta de generate_content não devolve
    # nenhum campo que confirme se a requisição foi de fato servida em tier
    # flex. Verificado no SDK google-genai (types.py): GenerateContentResponse
    # .usage_metadata não tem "service_tier"; o único campo candidato,
    # traffic_type, tem a docstring "This enum is not supported in Gemini
    # API." (é exclusivo do LiveServerMessage, outro endpoint). Aplicar 50% de
    # desconto por INTENÇÃO (`use_flex`), sem confirmação, é exatamente o tipo
    # de subdimensionamento que esta investigação apurou — então a estimativa
    # assume o pior caso (preço padrão) até existir uma forma confiável de
    # confirmar o tier realmente aplicado. `service_tier` continua no payload
    # de log (campo "extra") só como registro do que foi pedido, não do que
    # foi de fato cobrado.
    return round(cost, 8)


def log_gemini_usage(
    response: Any,
    *,
    model: str,
    feature: str,
    db: Any = None,
    extra: dict[str, Any] | None = None,
    usage_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Log Gemini token usage without ever failing the caller.

    ``usage_override`` substitui o usage lido de ``response.usage_metadata``
    quando o chamador já sabe que a resposta não vai trazer nada usável ali
    (caso de ``embed_content`` — ver ``count_input_tokens_free``) e mediu os
    tokens por outra via.
    """
    usage = usage_override if usage_override is not None else _usage_dict(response)
    total_tokens = _usage_int(usage, "total_token_count", "totalTokenCount")
    service_tier = str((extra or {}).get("service_tier") or "").strip().lower() or None
    estimated_usd = _estimate_usd(model, usage, service_tier=service_tier)
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

        day = datetime.now(TZ).strftime("%Y-%m-%d")
        doc = (
            db.collection("system_usage")
            .document("gemini")
            .collection("daily")
            .document(day)
        )
        model_key = _safe_key(model)
        feature_key = _safe_key(feature)
        prompt_tokens = _usage_int(usage, "prompt_token_count", "promptTokenCount")
        output_tokens = _usage_int(usage, "candidates_token_count", "candidatesTokenCount")
        thoughts_tokens = _usage_int(usage, "thoughts_token_count", "thoughtsTokenCount")
        cached_tokens = _usage_int(
            usage,
            "cached_content_token_count",
            "cachedContentTokenCount",
        )

        # Dicts aninhados de fato: `set(merge=True)` não expande chaves com
        # ponto em field paths (só `update()` faz isso), então usar
        # "tokens.total" como string viraria um campo literal com ponto
        # no nome em vez de tokens: {total: ...}.
        model_fields: dict[str, Any] = {"calls": firestore.Increment(1)}
        feature_fields: dict[str, Any] = {"calls": firestore.Increment(1)}
        tokens_fields: dict[str, Any] = {}

        if total_tokens:
            tokens_fields["total"] = firestore.Increment(total_tokens)
            model_fields["tokens_total"] = firestore.Increment(total_tokens)
            feature_fields["tokens_total"] = firestore.Increment(total_tokens)
        if prompt_tokens:
            tokens_fields["input"] = firestore.Increment(prompt_tokens)
        if output_tokens:
            tokens_fields["output"] = firestore.Increment(output_tokens)
        if thoughts_tokens:
            # Registrado à parte para visibilidade, mas já somado ao output
            # em _estimate_usd — cobrado à mesma taxa (ver comentário lá).
            tokens_fields["thoughts"] = firestore.Increment(thoughts_tokens)
        if cached_tokens:
            tokens_fields["cached_input"] = firestore.Increment(cached_tokens)

        updates: dict[str, Any] = {
            "date": day,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "calls": firestore.Increment(1),
            "models": {model_key: model_fields},
            "features": {feature_key: feature_fields},
        }
        if tokens_fields:
            updates["tokens"] = tokens_fields
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
    use_flex = should_use_flex(feature)
    call_kwargs = kwargs
    if use_flex:
        call_kwargs = _set_request_config(kwargs, _with_service_tier(kwargs.get("config"), "flex"))

    try:
        response = client.models.generate_content(model=model, contents=contents, **call_kwargs)
    except Exception as exc:
        if not (use_flex and GEMINI_FLEX_FALLBACK_TO_STANDARD and _is_flex_capacity_error(exc)):
            raise
        print(f"[GeminiFlex] feature={feature} model={model} flex unavailable; retrying standard: {exc}")
        response = client.models.generate_content(model=model, contents=contents, **kwargs)
        log_gemini_usage(
            response,
            model=model,
            feature=feature,
            db=db,
            extra={"service_tier": "standard", "flex_fallback": True},
        )
        return response

    extra = {"service_tier": "flex"} if use_flex else None
    log_gemini_usage(response, model=model, feature=feature, db=db, extra=extra)
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


def count_input_tokens_free(models: Any, *, model: str, contents: Any) -> int:
    """Conta tokens de entrada via ``count_tokens`` — endpoint gratuito da
    Gemini API (confirmado em firebase.google.com/docs/ai-logic/count-tokens:
    "There's no charge for calling countTokens"). Usado como fallback quando a
    resposta não traz ``usage_metadata`` utilizável (caso de ``embed_content``
    — ver ``embed_content_logged``). ``models`` é o objeto com o método
    ``count_tokens(model=..., contents=...)`` (``client.models`` ou, dentro do
    hook de interceptação, o próprio ``Models`` já vinculado). Nunca lança:
    retorna 0 em caso de falha, para não impedir a chamada original.
    """
    try:
        result = models.count_tokens(model=model, contents=contents)
        return int(getattr(result, "total_tokens", 0) or 0)
    except Exception as exc:
        print(f"[GeminiUsage] count_tokens falhou para {model}: {exc}")
        return 0


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
    usage = _usage_dict(response)
    if not usage:
        # EmbedContentResponse não traz usage_metadata na Gemini Developer API
        # (confirmado no SDK: só é preenchido na rota Vertex :embedContent, e
        # mesmo lá não para gemini-embedding-001, o modelo padrão daqui) — sem
        # isso, TODA chamada de embedding saía do relatório com custo zero,
        # sempre (achado 6 de 04/09/2026, estrutural, não um bug ocasional).
        tokens = count_input_tokens_free(client.models, model=model, contents=contents)
        if tokens:
            usage = {"prompt_token_count": tokens, "total_token_count": tokens}
    log_gemini_usage(response, model=model, feature=feature, db=db, usage_override=usage)
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


def decrement_limit(
    db: Any,
    user_id: str | None,
    feature: str,
) -> None:
    """Decrements the daily limit counter for a feature if an operation fails or produces an error."""
    if not user_id or db is None:
        return

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
        if doc.exists:
            current = doc.to_dict().get(feature, 0)
            if current > 0:
                ref.set({
                    feature: firestore.Increment(-1),
                    "updated_at": firestore.SERVER_TIMESTAMP
                }, merge=True)
    except Exception as e:
        print(f"[GeminiUsage] Failed to decrement limit for {user_id}/{feature}: {e}")




# --------------------------------------------------------------------------- #
# Telemetria completa de IA (DEV-2026-0003 / Issue #203, PR 2)
# --------------------------------------------------------------------------- #
# Intercepta as chamadas Gemini feitas fora de generate_content_logged e a
# telemetria do Claude — ver llm_usage_hooks.py. Este módulo é importado por
# main.py em todas as functions, então o hook é instalado uma vez por instância.
# Desligar: HERMES_LLM_USAGE_HOOKS=0.
try:
    import llm_usage_hooks as _llm_usage_hooks

    _llm_usage_hooks.install()
except Exception as _exc:  # telemetria nunca impede o carregamento do módulo
    print(f"[LLMUsageHooks] hook não instalado: {_exc}")
