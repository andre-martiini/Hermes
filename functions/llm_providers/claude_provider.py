"""
Cliente fino para a Claude Messages API (Anthropic), com um loop de
tool-calling equivalente ao já usado para Gemini em askCopilotoHermes
(main.py): até GODMODE_MAX_ROUNDS rodadas, execução paralela das tools
de uma mesma rodada via ThreadPoolExecutor, resultado final em texto.
"""

import json
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor

GODMODE_MAX_ROUNDS = 10
GODMODE_MAX_TOOL_WORKERS = 8
GODMODE_TOOL_RESULT_CHAR_LIMIT = 8000

# Campos aceitos de volta pela Messages API ao reenviar um bloco do assistente no
# histórico. O SDK anthropic é permissivo na leitura (ToolUseBlock/TextBlock têm
# additionalProperties=True) e pode incluir campos novos só de resposta (ex.:
# "caller", "toolset_name") que a própria API rejeita como input com 400 "Extra
# inputs are not permitted" — por isso NÃO dá pra reenviar block.model_dump() cru.
_TOOL_USE_ALLOWED_KEYS = {"type", "id", "name", "input"}
_TEXT_ALLOWED_KEYS = {"type", "text"}


def _serialize_block_for_request(block) -> dict:
    dumped = block.model_dump()
    if block.type == "tool_use":
        return {k: v for k, v in dumped.items() if k in _TOOL_USE_ALLOWED_KEYS}
    if block.type == "text":
        return {k: v for k, v in dumped.items() if k in _TEXT_ALLOWED_KEYS}
    return dumped


def _is_model_unavailable_error(exc: Exception) -> bool:
    """Detecta um modelo indisponível (ex: rollout parcial) sem depender do
    pacote anthropic estar importado neste módulo — inspeciona status_code
    (APIStatusError) e o corpo da mensagem como fallback."""
    if getattr(exc, "status_code", None) == 404:
        return True
    message = str(exc).lower()
    return "not_found_error" in message or ("model" in message and "not available" in message)


def run_tool_loop(
    client,
    model: str,
    system_instruction: str,
    tools: list[dict],
    function_map: dict,
    history: list[dict],
    user_message: str,
    max_tokens: int = 4096,
    max_rounds: int = GODMODE_MAX_ROUNDS,
    fallback_model: str | None = None,
) -> dict:
    """
    Executa um turno completo de conversa com tool-calling na Claude Messages API.

    client: instância de anthropic.Anthropic
    tools: lista de dicts {"name", "description", "input_schema"} (JSON Schema)
    function_map: dict {nome_da_tool: callable(**kwargs) -> objeto serializável em JSON}
    history: mensagens Claude já acumuladas em turnos anteriores
             ([{"role": "user"|"assistant", "content": str}, ...])
    user_message: texto da nova mensagem do usuário
    fallback_model: se o `model` primário responder "não disponível" (404),
             a rodada é refeita automaticamente com este modelo, e todas as
             rodadas seguintes do mesmo turno passam a usá-lo.

    Retorna: {"text", "history", "tools_used", "usage", "model_used", "fallback_used"}
    """
    messages = list(history)
    messages.append({"role": "user", "content": user_message})

    tools_used: list[str] = []
    usage_totals = {"input_tokens": 0, "output_tokens": 0}
    final_text = ""
    hit_round_limit = True
    active_model = model
    fallback_used = False

    for _round in range(max_rounds):
        def _create(model_name: str):
            return client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                system=system_instruction,
                tools=tools,
                messages=messages,
            )

        try:
            response = _create(active_model)
        except Exception as exc:
            if fallback_model and active_model != fallback_model and _is_model_unavailable_error(exc):
                active_model = fallback_model
                fallback_used = True
                response = _create(active_model)
            else:
                raise

        usage = getattr(response, "usage", None)
        if usage is not None:
            usage_totals["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
            usage_totals["output_tokens"] += getattr(usage, "output_tokens", 0) or 0

        assistant_content = [_serialize_block_for_request(block) for block in response.content]
        messages.append({"role": "assistant", "content": assistant_content})

        text_blocks = [block.text for block in response.content if block.type == "text"]
        if text_blocks:
            final_text = "\n".join(text_blocks)

        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_use_blocks:
            hit_round_limit = False
            break

        def _execute(block):
            fn = function_map.get(block.name)
            if fn is None:
                return block.id, {"error": f"Ferramenta desconhecida: {block.name}"}
            try:
                return block.id, fn(**(block.input or {}))
            except Exception as exc:
                return block.id, {"error": str(exc)}

        with _ThreadPoolExecutor(max_workers=min(len(tool_use_blocks), GODMODE_MAX_TOOL_WORKERS)) as executor:
            results = list(executor.map(_execute, tool_use_blocks))

        tools_used.extend(block.name for block in tool_use_blocks)

        tool_result_content = [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps(result, ensure_ascii=False, default=str)[:GODMODE_TOOL_RESULT_CHAR_LIMIT],
            }
            for tool_use_id, result in results
        ]
        messages.append({"role": "user", "content": tool_result_content})

    if hit_round_limit and not final_text:
        final_text = (
            "Atingi o limite de rodadas de ferramentas sem chegar a uma resposta final. "
            "Tente reformular o pedido em um escopo menor."
        )

    return {
        "text": final_text,
        "history": messages,
        "tools_used": tools_used,
        "usage": usage_totals,
        "model_used": active_model,
        "fallback_used": fallback_used,
    }
