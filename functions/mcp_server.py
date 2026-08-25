"""Servidor MCP do Hermes.

Expoe, via uma unica Cloud Function HTTP (`mcpServer`), o catalogo de tools do
Hermes sobre JSON-RPC 2.0: `initialize`, `tools/list`, `tools/call`,
`resources/list`, `resources/templates/list`, `resources/read`, `ping`.

Decisoes de escopo:

- Deploy como Cloud Function Python (mesmo codebase de functions/main.py),
  nao um servico Cloud Run separado — evita infraestrutura nova e min-instances
  adicionais, alinhado com a prioridade de reducao de custos.
- As tools vem de `tools/hermes_tools.py`, que executa o catalogo inteiro fora
  dos closures de `askCopilotoHermes`. `tools/list` publica o que tem handler,
  descricao no catalogo e schema — nunca uma tool que falharia ao ser chamada.
- Transporte: Streamable HTTP na sua forma minima — um JSON-RPC por POST com
  resposta `application/json`. Notificacoes (mensagens sem `id`) recebem `202`
  sem corpo, como manda a especificacao; responder um erro JSON-RPC a uma
  notificacao quebra o handshake de clientes estritos.
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
from tools.hermes_tools import ToolNotAvailable, execute as execute_tool
from tools.tool_context import ToolContext
from copilot_context import build_mcp_voice_context

MCP_PROTOCOL_VERSION = "2025-06-18"
_SUPPORTED_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
SERVER_NAME = "hermes-mcp"
SERVER_VERSION = "0.2.0"

_RESOURCE_VOICE_CONTEXT = "hermes://voice-context"

_ACCESS_CACHE_TTL_SEC = 300
_access_cache: dict[str, object] | None = None

# Quais tools exigem `_confirmed=true` NESTE canal.
#
# `registry._NEEDS_CONFIRMATION` marca ~25 tools que gravam, e continua valendo
# para o copiloto web e para o motor de simulacao. No canal MCP o cliente ja tem
# seu proprio pedido de permissao por chamada, entao exigir a dupla ida e volta
# em tudo so adiciona atrito sem adicionar um humano ao circuito.
#
# O envio de WhatsApp fica de fora por decisao explicita do dono do sistema
# (2026-08-25): manda mensagem em nome dele para terceiros, e o unico efeito que
# nao da para desfazer de dentro do Hermes.
#
# Configuravel sem deploy: `system/mcp_access.confirm_tools` (lista de nomes)
# sobrepoe este padrao — inclusive para voltar a exigir confirmacao em tudo.
_CONFIRMACAO_PADRAO: set[str] = {"schedule_whatsapp_message"}

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
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
)
def mcpServer(req: https_fn.Request) -> https_fn.Response:
    if req.method == "GET":
        return _json_response({
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "status": "ok",
        })

    if req.method == "DELETE":
        # Encerramento de sessao no Streamable HTTP. O servidor e stateless,
        # entao nao ha nada a limpar — mas responder 405 faz alguns clientes
        # logarem erro no fim de toda conversa.
        return https_fn.Response("", status=204)

    if req.method != "POST":
        return _json_response({"error": "method_not_allowed"}, status=405)

    try:
        body = req.get_json(silent=True) or {}
    except Exception:
        return _json_rpc_error(None, -32700, "Parse error")

    if not isinstance(body, dict):
        return _json_rpc_error(None, -32600, "Invalid Request: esperado um unico objeto JSON-RPC")

    rpc_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}
    is_notification = "id" not in body

    if not isinstance(method, str):
        if is_notification:
            return https_fn.Response("", status=202)
        return _json_rpc_error(rpc_id, -32600, "Invalid Request: 'method' ausente ou invalido")

    try:
        uid = _authenticate(req)
        _check_rate_limit(uid)
    except McpError as auth_err:
        if is_notification:
            return https_fn.Response("", status=202)
        return _json_rpc_error(rpc_id, auth_err.code, auth_err.message)

    # Notificacoes nao levam resposta. `notifications/initialized` chega logo apos
    # o handshake; devolver corpo (ou erro) aqui derruba clientes estritos.
    if is_notification:
        return https_fn.Response("", status=202)

    ctx = ToolContext(
        user_uid=uid,
        session_id=req.headers.get("Mcp-Session-Id") or None,
        canal="mcp",
    )

    try:
        if method == "initialize":
            result = _handle_initialize(params)
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = _handle_tools_list()
        elif method == "tools/call":
            result = _handle_tools_call(params, ctx=ctx)
        elif method == "resources/list":
            result = _handle_resources_list()
        elif method == "resources/templates/list":
            result = {"resourceTemplates": []}
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


def _access_config() -> dict:
    """Le `system/mcp_access` (allowlist + politica de confirmacao), memoizado.

    Uma leitura so para as duas coisas: sao consultadas juntas em toda chamada.
    """
    global _access_cache

    now = time.monotonic()
    if _access_cache and now < _access_cache["expires_at"]:
        return _access_cache

    uids: set[str] = set()
    confirmar: set[str] | None = None
    leitura_ok = True
    try:
        db = firestore.client()
        snap = db.collection("system").document("mcp_access").get()
        if snap.exists:
            dados = snap.to_dict() or {}
            uids.update(str(u) for u in dados.get("allowed_uids", []))
            if isinstance(dados.get("confirm_tools"), list):
                confirmar = {str(t) for t in dados["confirm_tools"]}
    except Exception as exc:
        leitura_ok = False
        print(f"[mcp_server] Falha ao ler system/mcp_access: {exc}")

    env_uids = os.environ.get("HERMES_MCP_ALLOWED_UIDS", "")
    uids.update(u.strip() for u in env_uids.split(",") if u.strip())

    config = {
        "uids": uids,
        "confirm_tools": _CONFIRMACAO_PADRAO if confirmar is None else confirmar,
        # Uma falha de leitura resulta em allowlist vazia (fail closed). Cachear
        # isso por 5 min transformaria um soluco do Firestore em cinco minutos de
        # acesso negado — entao so memoiza leitura bem-sucedida.
        "expires_at": now + (_ACCESS_CACHE_TTL_SEC if leitura_ok else 0),
    }
    if leitura_ok:
        _access_cache = config
    return config


def _is_uid_allowed(uid: str) -> bool:
    return uid in _access_config()["uids"]


def _exige_confirmacao(nome: str) -> bool:
    """Gating do canal MCP — ver `_CONFIRMACAO_PADRAO`."""
    return nome in _access_config()["confirm_tools"]


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

def _handle_initialize(params: dict) -> dict:
    # Ecoa a versao pedida quando conhecida; senao propoe a nossa e deixa o
    # cliente decidir se continua.
    pedida = params.get("protocolVersion")
    versao = pedida if pedida in _SUPPORTED_PROTOCOL_VERSIONS else MCP_PROTOCOL_VERSION
    return {
        "protocolVersion": versao,
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "capabilities": {"tools": {}, "resources": {}},
    }


def _handle_tools_list() -> dict:
    tools = []
    for name in registry.list_mcp_enabled_tools():
        try:
            schema = registry.get_schema(name)
        except (FileNotFoundError, OSError) as exc:
            # Handler existe mas o schema sumiu: omitir e seguir e melhor do que
            # derrubar o `tools/list` inteiro e deixar o cliente sem nenhuma tool.
            print(f"[mcp_server] Schema ausente para '{name}', tool omitida: {exc}")
            continue
        tools.append({
            "name": name,
            "description": schema.get("description", ""),
            "inputSchema": schema.get("parameters", {"type": "object", "properties": {}}),
            "_meta": {
                # `needsConfirmation` e o que ESTE canal exige (a dupla chamada
                # com `_confirmed`); `mutates` diz se a tool grava, independente
                # do gating — o cliente pode querer pedir aprovacao mesmo onde o
                # servidor nao exige.
                "needsConfirmation": _exige_confirmacao(name),
                "mutates": registry.needs_confirmation(name),
                "voiceEnabled": registry.is_voice_enabled(name),
            },
        })
    return {"tools": tools}


def _handle_tools_call(params: dict, *, ctx: ToolContext) -> dict:
    name = params.get("name")
    arguments = dict(params.get("arguments") or {})
    if not isinstance(name, str) or not name:
        raise McpError(-32602, "params.name obrigatorio em tools/call")

    if not registry.is_mcp_enabled(name):
        raise McpError(-32003, f"Tool '{name}' nao esta disponivel via MCP")

    confirmed = arguments.pop("_confirmed", None)
    if _exige_confirmacao(name) and confirmed is not True:
        return _text_result({
            "status": "confirmation_required",
            "tool": name,
            "message": (
                "Esta acao grava no Hermes e exige confirmacao explicita do usuario. "
                "Mostre a ele exatamente o que sera feito e, apos o 'sim', repita a "
                "chamada com arguments._confirmed=true."
            ),
        }, is_error=False)

    # `task_id` no argumento tem prioridade; serve tambem para dar contexto as
    # tools que aceitam a acao implicitamente.
    if arguments.get("task_id"):
        ctx.task_id = str(arguments["task_id"])

    start = time.monotonic()
    is_error = False
    try:
        result = execute_tool(name, arguments, ctx)
        is_error = bool(result.get("erro")) if isinstance(result, dict) else _looks_like_error(result)
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    except ToolNotAvailable:
        raise McpError(-32003, f"Tool '{name}' nao tem executor ligado ao MCP")
    except Exception as exc:  # noqa: BLE001
        is_error = True
        text = json.dumps({"erro": str(exc)}, ensure_ascii=False)
    finally:
        _audit_log(
            uid=ctx.user_uid,
            tool=name,
            arguments=arguments,
            latency_ms=(time.monotonic() - start) * 1000,
        )

    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _looks_like_error(result) -> bool:
    """As tools herdadas do copiloto web sinalizam falha no proprio texto.

    `ERRO|...` e o contrato do copiloto; o prefixo de aviso aparece nas tools que
    vieram do canal Telegram. Marcar `isError` deixa o cliente MCP distinguir
    falha de resposta legitima em vez de tratar todo texto como sucesso.
    """
    if not isinstance(result, str):
        return False
    return result.startswith("ERRO|") or result.startswith("⚠️")


def _text_result(payload: dict, *, is_error: bool) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "isError": is_error,
    }


def _handle_resources_list() -> dict:
    return {
        "resources": [{
            "uri": _RESOURCE_VOICE_CONTEXT,
            "name": "Contexto do copiloto Hermes",
            "description": "Persona, perfil do usuario autenticado e memorias recentes — para compor o system prompt de um cliente externo.",
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

def _audit_log(*, uid: str | None, tool: str, arguments: dict, latency_ms: float) -> None:
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
