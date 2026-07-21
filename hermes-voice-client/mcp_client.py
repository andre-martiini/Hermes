"""Cliente HTTP fino para o servidor MCP do Hermes (functions/mcp_server.py).

JSON-RPC 2.0 sincrono sobre POST, autenticado por Firebase ID Token (via
auth.get_id_token()). Ver docs/okf/copiloto/proposta-interface-vocal-mcp.md
para o contrato completo.
"""

from __future__ import annotations

import json
import os

import requests

import auth

_VOICE_CONTEXT_URI = "hermes://voice-context"


class McpError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _endpoint() -> str:
    url = os.environ.get("HERMES_MCP_URL", "").strip()
    if not url:
        raise RuntimeError("HERMES_MCP_URL nao configurada no .env")
    return url


def _call(method: str, params: dict | None = None, *, request_id: int = 1, _force_refresh: bool = False) -> dict:
    id_token = auth.get_id_token(force_refresh=_force_refresh)
    resp = requests.post(
        _endpoint(),
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
        headers={"Authorization": f"Bearer {id_token}"},
        timeout=30,
    )

    if resp.status_code == 401 and not _force_refresh:
        return _call(method, params, request_id=request_id, _force_refresh=True)

    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        error = body["error"]
        raise McpError(error.get("code"), error.get("message", "Erro MCP desconhecido"))
    return body.get("result", {})


def list_tools() -> list[dict]:
    return _call("tools/list").get("tools", [])


def call_tool(name: str, arguments: dict) -> dict:
    """Retorna {"is_error": bool, "data": dict}. `data` ja vem decodificado do JSON."""
    result = _call("tools/call", {"name": name, "arguments": arguments})
    content = result.get("content") or []
    text = content[0]["text"] if content and content[0].get("type") == "text" else "{}"
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = {"raw": text}
    return {"is_error": bool(result.get("isError", False)), "data": parsed}


def read_voice_context() -> str:
    result = _call("resources/read", {"uri": _VOICE_CONTEXT_URI})
    contents = result.get("contents") or []
    return contents[0]["text"] if contents else ""
