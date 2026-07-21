"""Servidor MCP do Hermes — fase 1.

Expoe, via uma unica Cloud Function HTTP (`mcpServer`), um subconjunto do
protocolo MCP (Model Context Protocol) sobre JSON-RPC 2.0 em POST sincrono:
`initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`.

Decisoes de escopo desta fase (ver docs/okf/copiloto/proposta-interface-vocal-mcp.md):

- Deploy como Cloud Function Python (mesmo codebase de functions/main.py),
  nao um servico Cloud Run separado — evita infraestrutura nova e min-instances
  adicionais, alinhado com a prioridade de reducao de custos.
- `tools/list` so retorna tools com executor real ligado (ver
  tools/registry.py::_MCP_ENABLED e tools/mcp_dispatch.py). As demais ~38
  tools do catalogo ainda vivem como closures presas ao request do copiloto
  web e nao sao expostas aqui ainda — listar uma tool que falha ao ser chamada
  seria pior do que nao lista-la.
- Transporte simplificado: um JSON-RPC por POST, resposta unica em JSON (sem
  variante SSE do "Streamable HTTP"). Suficiente para um cliente
  servidor-a-servidor (ex.: orquestrador de voz local) chamando tool a tool.
- Autenticacao por Firebase ID Token (Authorization: Bearer <token>) + lista
  branca de UID em Firestore (system/mcp_access.allowed_uids), com fallback
  em env var HERMES_MCP_ALLOWED_UIDS. Sem uid configurado em nenhum dos dois,
  o acesso e negado (fail closed).
"""

from __future__ import annotations

import json
import os
import time

from firebase_functions import https_fn, options
from firebase_admin import auth as firebase_auth
from firebase_admin import firestore

from tools import registry
from tools.mcp_dispatch import ToolNotAvailable, execute_tool
from copilot_context import build_mcp_voice_context

MCP_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "hermes-mcp"
SERVER_VERSION = "0.1.0"

_RESOURCE_VOICE_CONTEXT = "hermes://voice-context"

_ALLOWLIST_CACHE_TTL_SEC = 300
_allowlist_cache: dict[str, object] | None = None

_RATE_LIMIT_MAX_CALLS = 60
_RATE_LIMIT_WINDOW_SEC = 60
_rate_limit_hits: dict[str, list[float]] = {}

_CORS_ORIGINS = [
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


class McpError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@https_fn.on_request(
    cors=options.CorsOptions(cors_origins=_CORS_ORIGINS, cors_methods=["GET", "POST"]),
    memory=options.MemoryOption.MB_512,
    timeout_sec=60,
)
def mcpServer(req: https_fn.Request) -> https_fn.Response:
    if req.method == "GET":
        return _json_response({
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "status": "ok",
        })

    if req.method != "POST":
        return _json_response({"error": "method_not_allowed"}, status=405)

    try:
        body = req.get_json(silent=True) or {}
    except Exception:
        return _json_rpc_error(None, -32700, "Parse error")

    rpc_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    if not isinstance(method, str):
        return _json_rpc_error(rpc_id, -32600, "Invalid Request: 'method' ausente ou invalido")

    try:
        uid = _authenticate(req)
        _check_rate_limit(uid)
    except McpError as auth_err:
        return _json_rpc_error(rpc_id, auth_err.code, auth_err.message)

    try:
        if method == "initialize":
            result = _handle_initialize()
        elif method == "tools/list":
            result = _handle_tools_list()
        elif method == "tools/call":
            result = _handle_tools_call(params, uid=uid)
        elif method == "resources/list":
            result = _handle_resources_list()
        elif method == "resources/read":
            result = _handle_resources_read(params, uid=uid)
        else:
            return _json_rpc_error(rpc_id, -32601, f"Metodo desconhecido: {method}")
    except McpError as mcp_err:
        return _json_rpc_error(rpc_id, mcp_err.code, mcp_err.message)
    except Exception as exc:  # noqa: BLE001 — nunca vazar stack trace ao cliente
        print(f"[mcp_server] Erro inesperado em method={method}: {exc}")
        return _json_rpc_error(rpc_id, -32000, "Erro interno no servidor MCP")

    return _json_response({"jsonrpc": "2.0", "id": rpc_id, "result": result})


# --------------------------------------------------------------------------
# Autenticacao e limites
# --------------------------------------------------------------------------

def _authenticate(req: https_fn.Request) -> str:
    header = req.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise McpError(-32001, "Authorization: Bearer <Firebase ID Token> obrigatorio")

    token = header[len("Bearer "):].strip()
    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception:
        raise McpError(-32001, "ID Token invalido ou expirado")

    uid = decoded.get("uid")
    if not uid:
        raise McpError(-32001, "ID Token nao contem uid")

    if not _is_uid_allowed(uid):
        raise McpError(-32002, "UID nao autorizado a usar o servidor MCP do Hermes")

    return uid


def _is_uid_allowed(uid: str) -> bool:
    global _allowlist_cache

    now = time.monotonic()
    if _allowlist_cache and now < _allowlist_cache["expires_at"]:
        return uid in _allowlist_cache["uids"]

    uids: set[str] = set()
    try:
        db = firestore.client()
        snap = db.collection("system").document("mcp_access").get()
        if snap.exists:
            uids.update(str(u) for u in (snap.to_dict() or {}).get("allowed_uids", []))
    except Exception as exc:
        print(f"[mcp_server] Falha ao ler whitelist system/mcp_access: {exc}")

    env_uids = os.environ.get("HERMES_MCP_ALLOWED_UIDS", "")
    uids.update(u.strip() for u in env_uids.split(",") if u.strip())

    _allowlist_cache = {"uids": uids, "expires_at": now + _ALLOWLIST_CACHE_TTL_SEC}
    return uid in uids


def _check_rate_limit(uid: str) -> None:
    """Limite best-effort por instancia (nao compartilhado entre instancias
    do Cloud Functions). Suficiente para o uso single-user atual; se o
    servidor MCP ganhar mais clientes, mover para um contador em Firestore."""
    now = time.monotonic()
    hits = [t for t in _rate_limit_hits.get(uid, []) if now - t < _RATE_LIMIT_WINDOW_SEC]
    if len(hits) >= _RATE_LIMIT_MAX_CALLS:
        raise McpError(-32005, "Limite de chamadas ao servidor MCP excedido, tente novamente em instantes")
    hits.append(now)
    _rate_limit_hits[uid] = hits


# --------------------------------------------------------------------------
# Metodos MCP
# --------------------------------------------------------------------------

def _handle_initialize() -> dict:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "capabilities": {"tools": {}, "resources": {}},
    }


def _handle_tools_list() -> dict:
    tools = []
    for name in registry.list_mcp_enabled_tools():
        schema = registry.get_schema(name)
        tools.append({
            "name": name,
            "description": schema.get("description", ""),
            "inputSchema": schema.get("parameters", {"type": "object", "properties": {}}),
            "_meta": {
                "needsConfirmation": registry.needs_confirmation(name),
                "voiceEnabled": registry.is_voice_enabled(name),
            },
        })
    return {"tools": tools}


def _handle_tools_call(params: dict, *, uid: str) -> dict:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str) or not name:
        raise McpError(-32602, "params.name obrigatorio em tools/call")

    if not registry.is_mcp_enabled(name):
        raise McpError(-32003, f"Tool '{name}' nao esta disponivel via MCP nesta fase")

    if registry.needs_confirmation(name) and arguments.get("_confirmed") is not True:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "status": "confirmation_required",
                    "tool": name,
                    "message": "Esta acao exige confirmacao explicita antes de executar. "
                               "Repita a chamada com arguments._confirmed=true apos o usuario confirmar em voz.",
                }, ensure_ascii=False),
            }],
            "isError": False,
        }

    start = time.monotonic()
    try:
        result = execute_tool(name, arguments)
        is_error = bool(result.get("erro")) if isinstance(result, dict) else False
        text = json.dumps(result, ensure_ascii=False, default=str)
    except ToolNotAvailable:
        raise McpError(-32003, f"Tool '{name}' nao tem executor ligado ao MCP")
    except Exception as exc:  # noqa: BLE001
        is_error = True
        text = json.dumps({"erro": str(exc)}, ensure_ascii=False)
    finally:
        _audit_log(uid=uid, tool=name, arguments=arguments, latency_ms=(time.monotonic() - start) * 1000)

    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _handle_resources_list() -> dict:
    return {
        "resources": [{
            "uri": _RESOURCE_VOICE_CONTEXT,
            "name": "Contexto do copiloto Hermes",
            "description": "Persona, perfil do usuario autenticado e memorias recentes — para compor o system prompt de um cliente de voz.",
            "mimeType": "text/plain",
        }]
    }


def _handle_resources_read(params: dict, *, uid: str) -> dict:
    uri = params.get("uri")
    if uri != _RESOURCE_VOICE_CONTEXT:
        raise McpError(-32602, f"Resource desconhecido: {uri}")

    db = firestore.client()
    text = build_mcp_voice_context(db, uid=uid)
    return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]}


# --------------------------------------------------------------------------
# Auditoria e helpers HTTP
# --------------------------------------------------------------------------

def _audit_log(*, uid: str, tool: str, arguments: dict, latency_ms: float) -> None:
    try:
        db = firestore.client()
        db.collection("mcp_audit_log").add({
            "uid": uid,
            "tool": tool,
            "arguments": json.loads(json.dumps(arguments, ensure_ascii=False, default=str)),
            "latency_ms": round(latency_ms, 1),
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
    except Exception as exc:
        print(f"[mcp_server] Falha ao gravar audit log (tool={tool}): {exc}")


def _json_response(payload: dict, status: int = 200) -> https_fn.Response:
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        mimetype="application/json",
    )


def _json_rpc_error(rpc_id, code: int, message: str) -> https_fn.Response:
    status = 401 if code == -32001 else 403 if code == -32002 else 200
    return _json_response({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": code, "message": message},
    }, status=status)
