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
) -> dict:
    """
    Executa um turno completo de conversa com tool-calling na Claude Messages API.

    client: instância de anthropic.Anthropic
    tools: lista de dicts {"name", "description", "input_schema"} (JSON Schema)
    function_map: dict {nome_da_tool: callable(**kwargs) -> objeto serializável em JSON}
    history: mensagens Claude já acumuladas em turnos anteriores
             ([{"role": "user"|"assistant", "content": str}, ...])
    user_message: texto da nova mensagem do usuário

    Retorna: {"text", "history", "tools_used", "usage"}
    """
    messages = list(history)
    messages.append({"role": "user", "content": user_message})

    tools_used: list[str] = []
    usage_totals = {"input_tokens": 0, "output_tokens": 0}
    final_text = ""
    hit_round_limit = True

    for _round in range(max_rounds):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_instruction,
            tools=tools,
            messages=messages,
        )

        usage = getattr(response, "usage", None)
        if usage is not None:
            usage_totals["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
            usage_totals["output_tokens"] += getattr(usage, "output_tokens", 0) or 0

        assistant_content = [block.model_dump() for block in response.content]
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
    }
