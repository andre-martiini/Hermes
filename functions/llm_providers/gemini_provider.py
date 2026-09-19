"""
Loop de tool-calling sobre a Gemini API, com a mesma interface de
`claude_provider.run_tool_loop` (tools no formato {"name", "description",
"input_schema"}, `function_map`, histórico em texto) para os agentes do Hermes
trocarem de provedor sem reescrever suas ferramentas.

Diferenças que importam do Gemini 3.x:
- `max_output_tokens` inclui o raciocínio (~300-600 tokens mesmo em pergunta
  trivial): sem folga a resposta visível sai cortada. O provider soma
  THINKING_HEADROOM_TOKENS ao `max_tokens` pedido.
- O raciocínio não desliga (`minimal` e `thinking_budget=0` não são aceitos no
  3.8 Flash); `thinking_level="low"` é o mais barato e rápido que funciona.
- O conteúdo do modelo é reenviado sem alteração no histórico da rodada: ele
  carrega as assinaturas de raciocínio que a API exige de volta com o resultado
  das ferramentas.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor

from google.genai import types

from gemini_cost_controls import generate_content_logged

MAX_ROUNDS = 10
MAX_TOOL_WORKERS = 8
TOOL_RESULT_CHAR_LIMIT = 8000
THINKING_HEADROOM_TOKENS = 2048

_CAPACITY_MARKERS = ("unavailable", "overloaded", "resource_exhausted", "deadline_exceeded", "internal")


def _tool_declarations(tools: list[dict]) -> list:
    declarations = []
    for tool in tools or []:
        schema = tool.get("input_schema") or {}
        kwargs = {"name": tool["name"], "description": tool.get("description") or ""}
        if schema.get("properties"):
            kwargs["parameters_json_schema"] = schema
        declarations.append(types.FunctionDeclaration(**kwargs))
    return declarations


def _history_to_contents(history: list[dict] | None) -> list:
    contents = []
    for item in history or []:
        text = item.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        role = "model" if item.get("role") == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    return contents


def _status_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _is_model_unavailable_error(exc: Exception) -> bool:
    """Modelo inexistente ou sem capacidade agora: vale tentar o modelo de reserva."""
    code = _status_code(exc)
    if code in (404, 429, 500, 503, 504):
        return True
    message = str(exc).lower()
    return "not found" in message or any(marker in message for marker in _CAPACITY_MARKERS)


def _is_thinking_config_error(exc: Exception) -> bool:
    return _status_code(exc) == 400 and "thinking" in str(exc).lower()


def _tool_result_payload(result) -> dict:
    """O Gemini exige um objeto no resultado da ferramenta; o JSON longo é cortado."""
    serialized = json.dumps(result, ensure_ascii=False, default=str)
    if len(serialized) > TOOL_RESULT_CHAR_LIMIT:
        return {"result": serialized[:TOOL_RESULT_CHAR_LIMIT], "truncated": True}
    payload = json.loads(serialized)
    return payload if isinstance(payload, dict) else {"result": payload}


def _caller_feature() -> str:
    try:
        frame = sys._getframe(2)  # _caller_feature <- run_tool_loop <- chamador
        name = str(frame.f_globals.get("__name__", "") or "")
        return f"agent.{name.rsplit('.', 1)[-1] or 'unknown'}"
    except Exception:
        return "agent.unknown"


def run_tool_loop(
    client,
    model: str,
    system_instruction: str,
    tools: list[dict],
    function_map: dict,
    history: list[dict],
    user_message: str,
    max_tokens: int = 4096,
    max_rounds: int = MAX_ROUNDS,
    fallback_model: str | None = None,
    feature: str | None = None,
    db=None,
    thinking_level: str | None = "low",
    force_tools: list[str] | None = None,
    stop_after_tools: set[str] | None = None,
) -> dict:
    """
    Executa um turno completo de conversa com tool-calling na Gemini API.

    client: instância de google.genai.Client
    tools / function_map / history / user_message: como em claude_provider
    max_tokens: orçamento da resposta visível (o provider soma a folga do raciocínio)
    fallback_model: usado quando o principal falha por modelo inexistente ou sem
             capacidade (404/429/5xx); as rodadas seguintes do turno o mantêm
    feature: rótulo da telemetria de custo (system_usage/gemini); padrão "agent.<módulo chamador>"
    thinking_level: esforço de raciocínio; se o modelo o rejeitar, a rodada é refeita sem ele
    force_tools: se dado, o modelo é OBRIGADO a chamar uma dessas ferramentas em cada rodada
    stop_after_tools: se alguma destas ferramentas for executada, o turno termina ali,
             sem a rodada extra em que o modelo comentaria o resultado (uma chamada a menos)

    Retorna: {"text", "history", "tools_used", "usage", "model_used", "fallback_used"}
    """
    feature = feature or _caller_feature()
    declarations = _tool_declarations(tools)
    tool_config = None
    if force_tools:
        tool_config = types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="ANY", allowed_function_names=list(force_tools))
        )

    contents = _history_to_contents(history)
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    tools_used: list[str] = []
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "rounds": 0}
    final_text = ""
    hit_round_limit = True
    active_model = model
    fallback_used = False
    use_thinking = bool(thinking_level)

    def _config():
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            tool_config=tool_config,
            max_output_tokens=max_tokens + THINKING_HEADROOM_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level) if use_thinking else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def _generate(model_name: str):
        return generate_content_logged(
            client, model=model_name, contents=contents, feature=feature, db=db, config=_config()
        )

    for _round in range(max_rounds):
        response = None
        last_exc: Exception | None = None
        for _attempt in range(3):
            try:
                response = _generate(active_model)
                break
            except Exception as exc:
                last_exc = exc
                if use_thinking and _is_thinking_config_error(exc):
                    use_thinking = False
                elif fallback_model and active_model != fallback_model and _is_model_unavailable_error(exc):
                    active_model = fallback_model
                    fallback_used = True
                else:
                    raise
        if response is None:
            raise last_exc

        usage = getattr(response, "usage_metadata", None)
        usage_totals["rounds"] += 1
        if usage is not None:
            usage_totals["input_tokens"] += getattr(usage, "prompt_token_count", 0) or 0
            usage_totals["output_tokens"] += (getattr(usage, "candidates_token_count", 0) or 0) + (
                getattr(usage, "thoughts_token_count", 0) or 0
            )
            usage_totals["cache_read_input_tokens"] += getattr(usage, "cached_content_token_count", 0) or 0

        candidates = getattr(response, "candidates", None) or []
        content = getattr(candidates[0], "content", None) if candidates else None
        parts = list(getattr(content, "parts", None) or [])
        if content is not None:
            contents.append(content)

        text = "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))
        if text:
            final_text = text

        calls = [p.function_call for p in parts if getattr(p, "function_call", None)]
        if not calls:
            hit_round_limit = False
            break

        def _execute(call):
            fn = function_map.get(call.name)
            if fn is None:
                return call.name, {"error": f"Ferramenta desconhecida: {call.name}"}
            try:
                return call.name, fn(**dict(call.args or {}))
            except Exception as exc:
                return call.name, {"error": str(exc)}

        with _ThreadPoolExecutor(max_workers=min(len(calls), MAX_TOOL_WORKERS)) as executor:
            results = list(executor.map(_execute, calls))

        tools_used.extend(name for name, _ in results)
        if stop_after_tools and any(name in stop_after_tools for name, _ in results):
            hit_round_limit = False
            break

        contents.append(types.Content(role="user", parts=[
            types.Part.from_function_response(name=name, response=_tool_result_payload(result))
            for name, result in results
        ]))

    if hit_round_limit and not final_text:
        final_text = (
            "Atingi o limite de rodadas de ferramentas sem chegar a uma resposta final. "
            "Tente reformular o pedido em um escopo menor."
        )

    return {
        "text": final_text,
        "history": contents,
        "tools_used": tools_used,
        "usage": usage_totals,
        "model_used": active_model,
        "fallback_used": fallback_used,
    }
