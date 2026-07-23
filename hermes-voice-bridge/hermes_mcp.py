"""Ponte entre a sessao de voz do navegador e o servidor MCP do Hermes
(functions/mcp_server.py).

As 4 tools auditadas do MCP (consultar_historico_acoes, buscar_arquivos_acervo,
buscar_contato, calculadora) sao executadas COM O TOKEN DO PROPRIO USUARIO da
sessao — assim o audit log e a whitelist do MCP continuam valendo, sem duplicar
codigo de executor aqui. As tools locais de tools.py continuam existindo em
paralelo (leitura direta no Firestore, mais rapidas); os catalogos nao tem
nomes em comum.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger("hermes_voice_bridge.mcp")

_TIMEOUT_SECONDS = 25


class McpError(Exception):
    pass


def _mcp_url() -> str:
    url = os.getenv("HERMES_MCP_URL", "").strip()
    if not url:
        raise McpError("HERMES_MCP_URL nao configurada no ambiente do voice-bridge.")
    return url


def _rpc(method: str, params: dict, id_token: str) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        response = httpx.post(
            _mcp_url(),
            json=payload,
            headers={"Authorization": f"Bearer {id_token}"},
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise McpError(f"Falha de rede ao chamar o MCP ({method}): {exc}") from exc

    if response.status_code != 200:
        raise McpError(f"MCP retornou HTTP {response.status_code} em {method}: {response.text[:200]}")

    body = response.json()
    if body.get("error"):
        error = body["error"]
        raise McpError(f"MCP erro {error.get('code')}: {error.get('message')}")
    return body.get("result") or {}


def list_tools(id_token: str) -> list[dict]:
    """Retorna as tools do MCP ja convertidas para o formato de function
    declarations usado nas configs do Gemini Live (tipos em maiusculas)."""
    result = _rpc("tools/list", {}, id_token)
    declarations = []
    for tool in result.get("tools") or []:
        declarations.append(
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": _schema_to_gemini(tool.get("inputSchema") or {"type": "object"}),
            }
        )
    return declarations


def tool_names(declarations: list[dict]) -> set[str]:
    return {d["name"] for d in declarations}


def call_tool(name: str, args: dict, id_token: str) -> dict:
    """Executa uma tool no MCP e devolve um dict serializavel para o Gemini."""
    try:
        result = _rpc("tools/call", {"name": name, "arguments": args or {}}, id_token)
    except McpError as exc:
        logger.warning("Falha MCP em %s: %s", name, exc)
        return {"erro": str(exc)}

    if result.get("isError"):
        texts = [c.get("text", "") for c in result.get("content") or [] if c.get("type") == "text"]
        return {"erro": " ".join(texts) or "Tool retornou erro sem detalhe."}

    structured = result.get("structuredContent")
    if structured is not None:
        return {"resultado": structured}

    texts = [c.get("text", "") for c in result.get("content") or [] if c.get("type") == "text"]
    joined = "\n".join(t for t in texts if t)
    if not joined:
        return {"resultado": "(sem conteudo)"}
    try:
        return {"resultado": json.loads(joined)}
    except ValueError:
        return {"resultado": joined}


def read_voice_context(id_token: str) -> str:
    """Le o resource hermes://voice-context do MCP (contexto do copiloto de voz)."""
    try:
        result = _rpc("resources/read", {"uri": "hermes://voice-context"}, id_token)
    except McpError as exc:
        logger.warning("Falha ao ler voice-context do MCP: %s", exc)
        return ""
    texts = [c.get("text", "") for c in result.get("contents") or []]
    return "\n".join(t for t in texts if t).strip()


_JSON_TO_GEMINI_TYPE = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


def _schema_to_gemini(schema: dict) -> dict:
    json_type = str(schema.get("type", "string")).lower()
    gemini_type = _JSON_TO_GEMINI_TYPE.get(json_type, "STRING")

    if gemini_type == "OBJECT":
        converted = {
            "type": "OBJECT",
            "properties": {
                key: _schema_to_gemini(value)
                for key, value in (schema.get("properties") or {}).items()
            },
        }
        if schema.get("required"):
            converted["required"] = schema["required"]
        return converted

    if gemini_type == "ARRAY":
        return {
            "type": "ARRAY",
            "items": _schema_to_gemini(schema.get("items") or {"type": "string"}),
        }

    converted = {"type": gemini_type}
    if schema.get("description"):
        converted["description"] = schema["description"]
    return converted
