"""Loop de raciocinio do copiloto de voz: Gemini + tools do servidor MCP do
Hermes. Espelha o padrao ja usado em functions/main.py::askCopilotoHermes
(chats.create + automatic_function_calling desabilitado + loop manual de
function_calls), so que as tools sao executadas remotamente via MCP em vez
de closures locais.
"""

from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

import mcp_client

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
MAX_TOOL_ROUNDS = 4
MAX_HISTORY_TURNS = 8  # cada turno = 1 entrada de usuario + 1 de modelo no history

VOICE_SYSTEM_SUFFIX = """

Voce e o copiloto de voz do Hermes, rodando como cliente local no computador
do usuario. Respostas devem ser curtas, diretas e naturais para audicao por
voz — evite listas longas, markdown ou links extensos. Ao decidir usar uma
ferramenta, prossiga direto, sem pedir permissao antes. Se uma ferramenta
retornar status "confirmation_required", peca confirmacao explicita em voz
ao usuario antes de repetir a chamada com arguments._confirmed=true."""

_JSON_TYPE_TO_GEMINI = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "array": types.Type.ARRAY,
    "object": types.Type.OBJECT,
}


def _json_schema_to_gemini(schema: dict) -> types.Schema:
    json_type = str(schema.get("type", "string")).lower()
    gemini_type = _JSON_TYPE_TO_GEMINI.get(json_type, types.Type.STRING)

    if gemini_type == types.Type.OBJECT:
        properties = {
            key: _json_schema_to_gemini(value)
            for key, value in (schema.get("properties") or {}).items()
        }
        return types.Schema(
            type=types.Type.OBJECT,
            properties=properties,
            required=schema.get("required") or [],
        )

    if gemini_type == types.Type.ARRAY:
        items_schema = schema.get("items") or {"type": "string"}
        return types.Schema(type=types.Type.ARRAY, items=_json_schema_to_gemini(items_schema))

    return types.Schema(type=gemini_type, description=schema.get("description", ""))


def _build_gemini_tools(mcp_tools: list[dict]) -> list[types.Tool]:
    declarations = []
    for tool in mcp_tools:
        input_schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
        declarations.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters=_json_schema_to_gemini(input_schema),
            )
        )
    if not declarations:
        return []
    return [types.Tool(function_declarations=declarations)]


class VoiceSession:
    """Uma instancia por conexao WebSocket (uma sessao de conversa)."""

    def __init__(self, *, gemini_api_key: str, status_cb=None):
        self._client = genai.Client(api_key=gemini_api_key)
        self._status_cb = status_cb or (lambda _msg: None)
        self._chat = None
        self._chat_config: types.GenerateContentConfig | None = None

    def _notify(self, message: str) -> None:
        try:
            self._status_cb(message)
        except Exception as exc:  # noqa: BLE001 — nunca deixar o callback derrubar a sessao
            print(f"[orchestrator] status_cb falhou: {exc}")

    def _ensure_chat(self):
        if self._chat is not None:
            return self._chat

        self._notify("Conectando ao Hermes...")
        mcp_tools = mcp_client.list_tools()
        gemini_tools = _build_gemini_tools(mcp_tools)

        try:
            voice_context = mcp_client.read_voice_context()
        except Exception as exc:
            print(f"[orchestrator] Falha ao ler hermes://voice-context: {exc}")
            voice_context = ""

        system_instruction = (voice_context + "\n\n" + VOICE_SYSTEM_SUFFIX).strip()

        self._chat_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.4,
            tools=gemini_tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self._chat = self._client.chats.create(model=GEMINI_MODEL, config=self._chat_config)
        return self._chat

    def _trim_history_if_needed(self) -> None:
        history = self._chat.get_history()
        max_entries = MAX_HISTORY_TURNS * 2
        if len(history) <= max_entries:
            return
        trimmed = history[-max_entries:]
        self._chat = self._client.chats.create(
            model=GEMINI_MODEL,
            config=self._chat_config,
            history=trimmed,
        )

    def handle_user_text(self, text: str) -> str:
        chat = self._ensure_chat()
        self._notify("Pensando...")
        response = chat.send_message(text)

        for _round in range(MAX_TOOL_ROUNDS):
            function_calls = response.function_calls
            if not function_calls:
                break

            names = ", ".join(sorted({fc.name for fc in function_calls}))
            self._notify(f"Consultando o Hermes: {names}...")

            response_parts = []
            for fc in function_calls:
                result_text = self._execute_tool(fc.name, dict(fc.args or {}))
                response_parts.append(
                    types.Part.from_function_response(name=fc.name, response={"result": result_text})
                )

            self._notify("Consolidando resposta...")
            response = chat.send_message(response_parts)

        self._trim_history_if_needed()
        return (response.text or "").strip()

    def _execute_tool(self, name: str, arguments: dict) -> str:
        try:
            outcome = mcp_client.call_tool(name, arguments)
            text = json.dumps(outcome["data"], ensure_ascii=False, default=str)
        except mcp_client.McpError as exc:
            text = json.dumps({"erro": f"Falha ao chamar '{name}' via MCP: {exc.message}"}, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            text = json.dumps({"erro": f"Falha inesperada ao chamar '{name}': {exc}"}, ensure_ascii=False)

        if len(text) > 8000:
            text = text[:8000] + '..."[truncado]"'
        return text
