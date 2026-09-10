"""Servidor MCP do Hermes.

Expoe, via uma unica Cloud Function HTTP (`mcpServer`), o catalogo de tools do
Hermes sobre JSON-RPC 2.0: `initialize`, `server/discover`, `tools/list`,
`tools/call`, `resources/list`, `resources/templates/list`, `resources/read`,
`ping`.

Decisoes de escopo:

- Conformidade com a revisao 2026-07-28: `_SUPPORTED_PROTOCOL_VERSIONS` inclui
  essa versao (desde a PR #193, para o discovery do ChatGPT), entao QUALQUER
  resultado "complete" devolvido por este dispatch leva `resultType` — nao so
  `server/discover`/`tools/list`/`tools/call` (o achado original do Codex na
  PR #193, reproduzido ao vivo em 07/09/2026: toda chamada de `tools/call` —
  nao um subconjunto de handlers — falhava por falta do campo), mas tambem
  `ping`, `resources/list`, `resources/read`, `resources/templates/list`,
  `prompts/list` e `prompts/get` (mesma exigencia, mesmo risco, fechados na
  mesma correcao para nao deixar a proxima chamada nova descobrir a mesma
  lacuna de novo). `tools/list` e `server/discover` tambem levam
  `ttlMs`/`cacheScope` por serem catalogos cacheaveis (ver `_CATALOG_TTL_MS`);
  os demais nao, pelo mesmo raciocinio que ja valia para `tools/call`
  (resultado por chamada, nao um catalogo). O UNICO metodo que continua fora
  disso e o proprio `initialize`: o resultado dele e a propria negociacao de
  versao, entao gate-lo pela versao que ele ainda esta negociando nao faz
  sentido — ele responde no formato legado (sem `_meta` por chamada), como
  sempre respondeu. O restante do contrato da revisao 2026-07-28 (metadado de
  versao/cliente por requisicao em `_meta`, MRTR/elicitation real) tambem NAO
  esta implementado — isso cobre exatamente o que um cliente 2026-nativo
  comum verifica antes de aceitar uma resposta como valida, sem se
  comprometer com o resto do contrato sem necessidade real ainda.

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
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from firebase_functions import https_fn, options
from firebase_admin import auth as firebase_auth
from firebase_admin import firestore

from tools import registry
from tools.hermes_tools import ToolNotAvailable, execute as execute_tool, preview as preview_tool
from tools.tool_context import ToolContext, principal_de
from copilot_context import build_mcp_voice_context
from autonomy import policy as autonomy_policy
from autonomy.contracts import (
    Decisao,
    EstadoAutonomia,
    Principal,
    PolicyDecision,
    PolicyRequest,
    TipoPrincipal,
)

MCP_PROTOCOL_VERSION = "2025-06-18"
# "2026-07-28" e a revisao atual da especificacao (o primeiro "era moderna",
# com `_meta`/`server/discover` por requisicao em vez do handshake antigo por
# `initialize`); os demais valores cobrem clientes na era "legada". O Hermes
# continua respondendo no estilo legado — so nao rejeita quem se anuncia com a
# versao nova. Ver `_handle_server_discover` sobre o motivo de anunciar o
# metodo mesmo sem migrar o transporte inteiro.
_SUPPORTED_PROTOCOL_VERSIONS = {
    "2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28",
}
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
# acrescenta tools ao gate. Estes dois efeitos externos, contudo, nunca podem
# ser removidos por configuracao: uma lista vazia em producao nao pode tornar o
# envio de mensagem (inclusive a pausa) executavel sem o "sim" do usuario.
#
# As duas escritas de investimento entram pelo mesmo criterio, com uma diferenca
# de grau: o efeito nao so escapa do Hermes como nao tem desfazer NENHUM.
# `registrar_aporte_investimento` SOMA ao `aporte_total` de um servico que nao
# expoe estorno — registrado em dobro, o rendimento fica errado para sempre, e a
# correcao nao existe de nenhum dos dois lados. `registrar_execucao_investimento`
# vem junto por ser a mesma classe de acao e deixar linha permanente no log de
# movimentos de la.
#
# O motivo de o piso importar aqui tambem merece registro: `confirm_tools` esteve
# vazia em producao por um contorno do WhatsApp em 27/08/2026, e nao por decisao
# sobre escrita de dinheiro. Sem o piso, a sobra de um conserto de outra feature
# governaria, calada, ferramentas que mexem em dinheiro.
#
# ESTE CONJUNTO NAO CRESCE POR HABITO (condicao do dono, 02/09/2026). Uma
# candidata nova e decisao explicita, tomada uma vez, com o motivo escrito aqui —
# e nao "parece do mesmo tipo, entao entra". Piso que cresce por default vira o
# problema que ele resolve: gating que ninguem escolheu, governando por inercia.
#
# Fonte única (P02 sub-entrega 2/N, docs/autonomia/execucao.md): ate aqui este
# conjunto era mantido em duplicata, tambem em `autonomy/policy.py::
# FLOOR_CONFIRMACAO_OBRIGATORIA` (sub-entrega 1/N), com um teste de regressao
# em test_policy.py garantindo que os dois nunca divergissem. Agora so existe
# la — este nome continua existindo como ALIAS local (nada mais neste arquivo
# precisou mudar: `_CONFIRMACAO_PADRAO`, `_access_config()` e
# `_exige_confirmacao()` seguem lendo esta variavel, sem saber que ela agora
# aponta para o modulo de politica). O comentario acima (motivo de cada tool
# estar aqui, e de o conjunto nao crescer por habito) continua sendo a fonte
# de verdade em prosa — mantido aqui, e nao so em policy.py, porque e este
# arquivo que o dono le quando mexe no canal MCP.
_CONFIRMACAO_OBRIGATORIA: frozenset[str] = autonomy_policy.FLOOR_CONFIRMACAO_OBRIGATORIA
_CONFIRMACAO_PADRAO: set[str] = set(_CONFIRMACAO_OBRIGATORIA)
_CONFIRMACAO_TTL = timedelta(minutes=10)
# Ver `_status_claim_pendente`: folga acima do timeout_sec=300 da função
# `mcpServer` (comentário de `_TOOLS_LONGAS` abaixo) para nunca rotular como
# abandonado um claim que ainda pode estar dentro do próprio limite da
# função; folga abaixo de `_CONFIRMACAO_TTL` para o caso ficar identificável
# como "resultado incerto" antes que a confirmação em si pareça só expirada.
_CLAIM_ABANDONADA_APOS = timedelta(minutes=6)
_WHATSAPP_JOB_ID_RE = re.compile(r"\bjob_id=([A-Za-z0-9_-]+)")

# Tools que passam de um minuto e por isso nao podem rodar dentro do request.
#
# Pela URL direta da funcao ha 300s; pela URL do Hosting — a que Cowork, Desktop
# e celular usam — o limite e 60s, e o cliente recebe erro de gateway sem
# explicacao. Em vez de depender de qual rota atendeu, o comportamento e o mesmo
# nas duas: devolve `job_id` na hora e o trabalho vai para o trigger de 540s.
#
# `pesquisar_internet` e `ler_pagina_web` tambem sao _ASYNC_TOOLS no registry,
# mas os timeouts delas sao 20s e 25s — cabem sincronas, e faze-las assincronas
# so acrescentaria uma ida e volta ao caso comum.
_TOOLS_LONGAS: set[str] = {
    "gerar_relatorio",
    "ler_documento_na_integra",
    "buscar_e_analisar_email",
}

_RATE_LIMIT_MAX_CALLS = 60
_RATE_LIMIT_WINDOW_SEC = 60
_rate_limit_hits: dict[str, list[float]] = {}

_CORS_ORIGINS = [
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# TTL de respostas "catalogo" (`server/discover` e `tools/list`) — capacidades,
# identidade e schema das tools so mudam em deploy, entao 5 min (mesmo criterio
# do cache de discovery OAuth em mcp_oauth.py) evita re-fetch constante sem
# arriscar informacao desatualizada por muito tempo. `cacheScope="public"`:
# nenhuma das duas respostas contem dado do usuario (a autorizacao de quem pode
# USAR o Hermes continua sendo feita por fora, no OAuth; `tools/list` nao
# recebe uid nem ctx — ver `_handle_tools_list`) e e identica para qualquer
# cliente autenticado. Compartilhada entre as duas por ser exatamente o mesmo
# raciocinio — nao duas coincidencias que podem divergir sem ninguem notar.
_CATALOG_TTL_MS = 300_000

# Compartilhado entre `initialize` (era legada) e `server/discover` (era
# moderna, 2026-07-28+) — as duas formas de um cliente aprender a usar o
# Hermes antes da primeira chamada real. Extrair para uma constante evita as
# duas respostas divergirem sem que ninguem decida isso de proposito.
_INSTRUCTIONS = (
    "Hermes e o sistema de gestao pessoal e profissional do usuario: "
    "acoes, agenda, financas, saude, contatos, acervo e memoria.\n\n"
    "- Comece uma conversa nova com `obter_estado_atual` para se situar "
    "no dia, em vez de perguntar ao usuario o que esta acontecendo.\n"
    "- Quando o usuario afirmar um fato duravel sobre si, sobre pessoas "
    "ou sobre como as coisas funcionam, grave com `salvar_memoria_global`. "
    "O Hermes so aprende o que for gravado explicitamente.\n"
    "- O trabalho e organizado como macroacao dividida em subtarefas "
    "(`plano_acao`). O controle fino vive na subtarefa: `editar_plano_acao` "
    "marca cada etapa como `em_andamento`, `aguardando_terceiro` (com "
    "`aguardando_de`) ou `feito`, e da data propria a ela. Vale marcar — "
    "etapa esperando terceiro nao acumula adiamento, e a faixa da acao e "
    "deduzida dessas marcacoes. Omitir um campo preserva o valor atual.\n"
    "- Para editar acoes prefira `editar_acao` e `editar_acoes_em_lote`. "
    "As tools `preparar_*` existem para a interface web, que renderiza um "
    "card de confirmacao, e exigem uma segunda chamada para gravar.\n"
    "- Tools longas devolvem status `processing` com um `job_id`; busque o "
    "resultado com `consultar_job`.\n"
    "- `schedule_whatsapp_message` manda mensagem para terceiros em nome "
    "do usuario. Mostre o destinatario e o texto exato e espere ele "
    "concordar antes de chamar — e o unico efeito que nao da para "
    "desfazer de dentro do Hermes. Se o servidor responder pedindo "
    "confirmacao, chame `confirmar_acao` com o `confirmation_id` devolvido.\n"
    "- Para anexar arquivo, a ordem de preferencia e: `drive_file_id` "
    "(arquivo que ja esta no Drive — peca ao usuario para joga-lo la pelo "
    "celular se ainda nao estiver), `gmail_message_id`, `url`, e por fim "
    "`preparar_upload`. NUNCA transcreva o arquivo para base64 nem o suba "
    "por outro conector: base64 gerado por modelo chega truncado e grava "
    "sem erro. `conteudo_base64` existe so para arquivo minusculo e exige "
    "sha256 do arquivo de origem.\n"
    "- Leitura de WhatsApp pode estar liberada em todas as conversas ou "
    "restrita a uma lista — `listar_conversas_whatsapp` diz qual e o caso. "
    "Uma recusa com motivo `chat_nao_monitorado` e o limite funcionando, "
    "nao um erro a contornar: peca ao usuario que libere a conversa. E "
    "mesmo com acesso amplo, leia o que a pergunta pede: ha terceiros "
    "nessas conversas que nao sabem que um agente le."
)


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
    caminho = (req.path or "/").rstrip("/")

    # Servido tambem aqui, e nao so no Hosting, para o cliente que sonda o
    # metadata relativo a propria URL do MCP em vez de seguir o ponteiro do 401.
    if caminho.endswith("/.well-known/oauth-protected-resource"):
        from mcp_oauth import protected_resource_metadata

        return _json_response(protected_resource_metadata())

    # Upload do arquivo pela propria origem do MCP.
    #
    # Fica antes de `_authenticate` de proposito: o `upload_token` E a
    # credencial. Com `headersHelper` o Bearer do MCP nem chega ao modelo, que e
    # quem monta o comando de upload — exigi-lo aqui inviabilizaria a rota. O
    # token tem 128 bits, vale 15 minutos, e uso unico e esta preso a um uid e a
    # um arquivo ja declarado por tamanho e digest; mesmo modelo de uma URL
    # assinada.
    if "/upload/" in caminho and req.method in ("PUT", "POST"):
        from tools.anexar_arquivo import receber_upload

        token = caminho.rsplit("/", 1)[-1]
        try:
            resultado = receber_upload(firestore.client(), None, token, req.get_data())
        except Exception as exc:  # noqa: BLE001
            print(f"[mcp_server] Falha no upload de {token}: {exc}")
            resultado = {"erro": "Falha ao gravar o arquivo.", "status": 500}
        return _json_response(resultado, status=resultado.pop("status", 200))

    if req.method == "GET":
        # Health-check num path proprio. O GET na raiz NAO pode devolver 200:
        # e por ele que um cliente OAuth descobre que precisa autenticar, e a
        # especificacao exige o 401 — `WWW-Authenticate` numa resposta 200 e
        # ignorado. Antes daqui, qualquer GET caia neste health e respondia 200,
        # o que escondia o desafio de autenticacao.
        if caminho.endswith("/health"):
            return _json_response({
                "server": SERVER_NAME,
                "version": SERVER_VERSION,
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "status": "ok",
            })
        try:
            _authenticate(req)
        except McpError as auth_err:
            return _json_rpc_error(None, auth_err.code, auth_err.message)
        # Autenticado, mas nao ha stream SSE a abrir neste transporte sincrono.
        return https_fn.Response("", status=405, headers={"Allow": "POST"})

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

    dispatch_started = time.monotonic()
    try:
        if method == "initialize":
            result = _handle_initialize(params)
        elif method == "server/discover":
            result = _handle_server_discover(params)
        elif method == "ping":
            # "complete" tambem aqui por consistencia com todo o resto do
            # dispatch (ver comentario de escopo no topo do arquivo) — nao ha
            # razao para um pong ser a unica resposta sem o campo.
            result = {"resultType": "complete"}
        elif method == "tools/list":
            result = _handle_tools_list()
        elif method == "tools/call":
            result = _handle_tools_call(params, ctx=ctx)
        elif method == "resources/list":
            result = _handle_resources_list()
        elif method == "prompts/list":
            result = _handle_prompts_list()
        elif method == "prompts/get":
            result = _handle_prompts_get(params)
        elif method == "resources/templates/list":
            result = {"resourceTemplates": [], "resultType": "complete"}
        elif method == "resources/read":
            result = _handle_resources_read(params, uid=uid)
        else:
            _log_mcp_call(method, ok=False, error_code=-32601,
                          latency_ms=(time.monotonic() - dispatch_started) * 1000)
            return _json_rpc_error(rpc_id, -32601, f"Metodo desconhecido: {method}")
    except McpError as mcp_err:
        _log_mcp_call(method, ok=False, error_code=mcp_err.code,
                      latency_ms=(time.monotonic() - dispatch_started) * 1000)
        return _json_rpc_error(rpc_id, mcp_err.code, mcp_err.message)
    except Exception as exc:  # noqa: BLE001 — nunca vazar stack trace ao cliente
        print(f"[mcp_server] Erro inesperado em method={method}: {exc}")
        _log_mcp_call(method, ok=False, error_code=-32000,
                      latency_ms=(time.monotonic() - dispatch_started) * 1000)
        return _json_rpc_error(rpc_id, -32000, "Erro interno no servidor MCP")

    _log_mcp_call(method, ok=True, result=result,
                  latency_ms=(time.monotonic() - dispatch_started) * 1000)
    return _json_response({"jsonrpc": "2.0", "id": rpc_id, "result": result})


# --------------------------------------------------------------------------
# Autenticacao e limites
# --------------------------------------------------------------------------

def _authenticate(req: https_fn.Request) -> str:
    """Aceita os dois tipos de credencial, nesta ordem.

    1. Access token OAuth emitido por `mcp_oauth.py` — e o que as superficies
       hospedadas do Claude (Claude.ai, Desktop, Cowork) usam, porque la nao
       existe `headersHelper`. Validado localmente, sem I/O.
    2. Firebase ID Token — o caminho do Claude Code e do cliente de voz, que
       montam o header por conta propria.

    A ordem e por custo: o JWT proprio verifica com um HMAC local, enquanto
    `verify_id_token` pode ir buscar as chaves publicas do Google.
    """
    header = req.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise McpError(-32001, "Authorization: Bearer <token> obrigatorio")

    token = header[len("Bearer "):].strip()

    from mcp_oauth import validar_access_token

    claims = validar_access_token(token)
    if claims:
        uid = claims.get("sub")
    else:
        try:
            uid = firebase_auth.verify_id_token(token).get("uid")
        except Exception:
            raise McpError(-32001, "Token invalido ou expirado")

    if not uid:
        raise McpError(-32001, "Token nao identifica um usuario")

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
        "confirm_tools": _CONFIRMACAO_OBRIGATORIA | (
            _CONFIRMACAO_PADRAO if confirmar is None else confirmar
        ),
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
    # Conferir tambem aqui torna a garantia independente de caches antigos e de
    # quem construir uma configuracao de teste/manual fora de `_access_config`.
    return nome in _CONFIRMACAO_OBRIGATORIA or nome in _access_config()["confirm_tools"]


def _principal_mcp(ctx: ToolContext) -> Principal:
    """Constrói o `Principal` (autonomy/contracts.py) deste canal, para o
    preflight do motor de política (P02 sub-entrega 2/N).

    O servidor MCP é de acesso único: `_is_uid_allowed` já restringe a
    própria autenticação a um único uid dono (ver `_authenticate` — sem uid
    configurado em `system/mcp_access.allowed_uids` ou na env var, o acesso é
    negado). Toda chamada que chega até aqui já foi autenticada por um
    cliente MCP hospedado (Claude.ai, Claude Desktop, Claude Code) com o
    dono efetivamente acompanhando a sessão em tempo real — mesmo sem clique
    de UI por chamada individual —, que é exatamente a definição de
    `TipoPrincipal.CLIENTE_ASSISTIDO`, não `DONO_INTERATIVO` (não há UI de
    clique aqui) nem `ROTINA_COWORK`/`RUNNER_SERVICO` (não há job assíncrono
    sem sessão neste caminho).

    `origem_humana=True` é passado explicitamente, nunca herdado do default
    do dataclass — cuidado deliberado registrado em
    docs/autonomia/execucao.md (pendência da sub-entrega 1/N): este é o
    canal do próprio dono, então o valor está correto, mas escrevê-lo aqui
    documenta a decisão em vez de deixá-la implícita no default.

    Desde a sub-entrega 5/N, a construção em si (uid/canal → `Principal`,
    default de `origem_humana` por tipo) é `tools.tool_context.principal_de`
    — compartilhado com qualquer canal futuro que precise da mesma lógica.
    Esta função continua existindo, com o mesmo nome e assinatura, só para
    preservar a decisão do TIPO (CLIENTE_ASSISTIDO, nunca inferido) e o
    raciocínio documentado acima; `test_mcp_server.py::TestPrincipalMcp`
    prova que o resultado não mudou.
    """
    return principal_de(ctx, TipoPrincipal.CLIENTE_ASSISTIDO, origem_humana=True)


def _decisao_piso_mcp(ctx: ToolContext, nome: str, argumentos: dict) -> PolicyDecision | None:
    """Preflight de `autonomy.policy.avaliar()` para os tools do piso.

    Retorna `None` quando `nome` não está classificado em
    `autonomy_policy.CLASSE_EFEITO_PISO` — hoje isso cobre exatamente os
    tools do piso hardcoded (`FLOOR_CONFIRMACAO_OBRIGATORIA`); um tool
    exigindo confirmação só por config (`system/mcp_access.confirm_tools`,
    além do piso) não tem `classe_efeito` conhecida e continua pelo fluxo de
    confirmação antigo, sem passar pelo motor — limitação documentada em
    docs/autonomia/execucao.md (P02 sub-entrega 2/N): classificar tools
    configuráveis fica para quando houver uma fonte de classificação além do
    dicionário hardcoded `CLASSE_EFEITO_PISO`.

    Chamado uma única vez, na CRIAÇÃO da prévia de confirmação (dentro de
    `_handle_tools_call`) — não é repetido no momento de EXECUTAR uma
    confirmação já criada (`_executar_confirmacao`). Reavaliar a política no
    momento da execução (para cobrir o caso raro de o estado de autonomia
    mudar dentro da janela de 10 minutos da confirmação) ainda não está
    implementado; registrado como limitação conhecida, não escondida, em
    docs/autonomia/execucao.md.

    P02 sub-entrega 13/N — fim da duplicação: no caminho feliz (Firestore
    acessível), esta função agora DELEGA inteiramente para
    `autonomy_policy.decisao_piso(db, principal, nome, argumentos)`, em vez
    de reimplementar em paralelo o mesmo lookup de classe_efeito + resolução
    de estado + `PolicyRequest` + `avaliar()` com fallback fail-closed +
    `registrar_decisao()`. Essa duplicação (registrada como pendência desde
    a sub-entrega 6/N) já tinha custo real: a correção fail-closed da
    sub-entrega 12/N precisou ser aplicada manualmente duas vezes, uma em
    cada função. A ÚNICA razão para esta função continuar existindo, em vez
    de os chamadores usarem `decisao_piso()` diretamente, é a diferença de
    como `db` chega: `decisao_piso()` recebe um `db` já resolvido (nunca
    lança ao ser passado como argumento); aqui, `ctx.db` é uma property lazy
    que pode lançar na PRÓPRIA inicialização do cliente Firestore (ex.: "The
    default Firebase app does not exist") — falha que fica FORA de qualquer
    try/except de `decisao_piso()`/`estado_autonomia_atual()`/
    `registrar_decisao()`, já que todos eles protegem falha de LEITURA/
    ESCRITA usando um `db` válido, não a resolução do próprio `db`. Por
    isso `ctx.db` é isolado aqui, numa única tentativa, antes de delegar.

    Quando essa tentativa falha (`db is None`): sem um `db` utilizável não
    há como chamar `decisao_piso()` (ela pressupõe `db` resolvido) nem
    registrar a decisão de verdade. O fallback abaixo reproduz o mesmo
    resultado observável do código anterior a esta sub-entrega
    (`estado=SOMENTE_PREPARACAO`, `avaliar()` com o mesmo guard fail-closed
    de `decisao_erro_avaliacao()`, sem tentativa de registro). Simplificação
    deliberada em relação ao código anterior: antes, uma segunda tentativa
    de acessar `ctx.db` acontecia dentro do try/except de
    `registrar_decisao`, e falhava do mesmo jeito na prática (nada indica
    que `ctx.db` se recupere entre duas chamadas na mesma requisição) —
    nunca produzia um registro; esta versão não repete a tentativa, sem
    mudança de comportamento observável hoje (ver
    `test_ctx_db_indisponivel_cai_em_somente_preparacao_sem_registrar`).
    """
    classe_efeito = autonomy_policy.CLASSE_EFEITO_PISO.get(nome)
    if classe_efeito is None:
        return None

    try:
        db = ctx.db
    except Exception as exc:  # noqa: BLE001 — nunca derrubar a chamada por falha ao resolver o cliente Firestore
        print(f"[mcp_server] Falha ao resolver ctx.db para preflight de '{nome}': {exc}")
        db = None

    principal = _principal_mcp(ctx)

    if db is not None:
        return autonomy_policy.decisao_piso(db, principal, nome, argumentos)

    # `db` inutilizável: sem `registrar_decisao` possível (não há onde
    # gravar), mas a decisão em si ainda precisa existir, fail-closed —
    # mesmo raciocínio de `decisao_piso()`, sem o passo de auditoria.
    request = PolicyRequest(
        principal=principal,
        ferramenta=nome,
        classe_efeito=classe_efeito,
        argumentos_resolvidos=argumentos,
        estado_autonomia=EstadoAutonomia.SOMENTE_PREPARACAO,
    )
    try:
        return autonomy_policy.avaliar(request)
    except Exception as exc:  # noqa: BLE001 — principal malformado nunca deixa a tool do piso passar sem confirmação
        print(f"[mcp_server] Falha ao avaliar política do piso (sem db) para '{nome}': {exc}")
        return autonomy_policy.decisao_erro_avaliacao(
            request,
            motivo_legivel=(
                f"Falha interna ao avaliar a política de autonomia para '{nome}'; "
                "bloqueado por segurança."
            ),
        )


def _criar_confirmacao(ctx: ToolContext, nome: str, argumentos: dict, previa: dict | None) -> str:
    """Guarda a proposta concreta que o usuario esta prestes a aprovar.

    O segundo request MCP e independente do primeiro. Persistir a previa evita
    que atalhos relativos (por exemplo, ``amanha_manha``) ou a resolucao de um
    contato sejam calculados novamente depois do "sim".
    """
    confirmation_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + _CONFIRMACAO_TTL
    ctx.db.collection("mcp_confirmations").document(confirmation_id).set({
        "uid": ctx.user_uid,
        "tool": nome,
        "arguments": argumentos,
        "preview": previa,
        "created_at": now,
        "expires_at": expires_at,
        "expira_em": expires_at,
    })
    ctx.mcp_confirmation_expires_at = expires_at
    return confirmation_id


def _ler_confirmacao(ctx: ToolContext, nome: str, argumentos: dict, confirmation_id: object) -> dict:
    """Valida e devolve uma proposta previamente apresentada ao mesmo usuario."""
    if not isinstance(confirmation_id, str) or not confirmation_id.strip():
        raise ValueError("Repita a chamada com o confirmation_id devolvido pela prévia.")
    snap = ctx.db.collection("mcp_confirmations").document(confirmation_id).get()
    if not snap.exists:
        raise ValueError("Confirmação não encontrada ou já expirada; peça uma nova prévia.")
    data = snap.to_dict() or {}
    if data.get("uid") != ctx.user_uid or data.get("tool") != nome:
        raise ValueError("Confirmação não pertence a esta chamada.")
    expires_at = data.get("expires_at")
    if not isinstance(expires_at, datetime) or expires_at <= datetime.now(timezone.utc):
        raise ValueError("Confirmação expirada; peça uma nova prévia.")
    return data


def _resultado_confirmacao_whatsapp(ctx: ToolContext, argumentos: dict, result, *, wait_seconds: float = 5):
    """Acrescenta o job e, para envio imediato, o estado que o worker já gravou."""
    if not isinstance(result, str):
        return result
    match = _WHATSAPP_JOB_ID_RE.search(result)
    if not match:
        return result
    resposta = {"resultado": result, "job_id": match.group(1)}
    try:
        scheduled_at = datetime.fromisoformat(
            str(argumentos.get("scheduled_time") or "").replace("Z", "+00:00")
        )
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    except ValueError:
        return resposta
    if scheduled_at > datetime.now(timezone.utc) + timedelta(seconds=90):
        return resposta

    # A espera curta só cobre o caso "agora". Não transforma agendamento futuro
    # em polling de cinco segundos nem afirma entrega quando o worker ainda não a
    # registrou.
    try:
        ref = ctx.db.collection("whatsapp_outbox").document(resposta["job_id"])
        deadline = time.monotonic() + wait_seconds
        while True:
            snap = ref.get()
            if snap.exists:
                status = (snap.to_dict() or {}).get("status")
                if status in {"pending", "sending", "sent", "failed"}:
                    resposta["status_outbox"] = status
                if status in {"sent", "failed"} or time.monotonic() >= deadline:
                    return resposta
            if time.monotonic() >= deadline:
                return resposta
            time.sleep(0.5)
    except Exception as exc:  # consulta é conveniência; a confirmação já executou
        print(f"[mcp_server] Falha ao consultar outbox da confirmação: {exc}")
        return resposta


def _status_claim_pendente(claim_data: dict) -> dict:
    """Decide o texto para um claim que já existe e ainda não tem resultado.

    Duas leituras possíveis do mesmo fato ("claimed_at" presente, sem
    executed_at): a tentativa anterior pode estar genuinamente em andamento
    (comum: latência da tool), ou pode ter sido abandonada por uma
    interrupção do servidor (timeout da função, reinício de instância) --
    nesse segundo caso a tool pode já ter rodado e produzido efeito, mas
    ninguém chegou a gravar o resultado. Não dá para diferenciar os dois
    casos com certeza, então o corte usa `_CLAIM_ABANDONADA_APOS`: folga
    generosa acima do timeout_sec=300 da própria função `mcpServer` (ver
    comentário de `_TOOLS_LONGAS` acima), para nunca rotular como abandonado
    um claim que ainda pode legitimamente estar rodando dentro do próprio
    limite da função. Em NENHUM dos dois casos a tool é reexecutada aqui --
    a diferença é a mensagem devolvida ao chamador e, para o caso abandonado,
    o campo `erro`: achado da revisão adversarial (ver execucao.md) -- sem
    ele, `_handle_tools_call` computa `isError: false` (mesma convenção
    neutra de `em_execucao`, via `bool(result.get("erro"))`), e nada no
    envelope MCP distingue estruturalmente "aguarde, está rodando" de
    "resultado desconhecido, não repita sem checar". Um agente menos
    cauteloso podia ler a mensagem e mesmo assim abrir uma confirmação nova
    para a mesma ação. `erro` truthy aqui faz o cliente MCP receber
    `isError: true`, sinal mais difícil de ignorar do que só o texto.
    """
    claimed_at = claim_data.get("claimed_at")
    if isinstance(claimed_at, datetime) and datetime.now(timezone.utc) - claimed_at >= _CLAIM_ABANDONADA_APOS:
        return {
            "status": "resultado_incerto",
            "erro": (
                "Uma tentativa anterior desta confirmação foi reivindicada e não "
                "terminou de forma registrada -- provável interrupção do servidor "
                "(timeout ou reinício de instância). O efeito pode já ter "
                "ocorrido. Não repita esta ação automaticamente (nem abrindo uma "
                "confirmação nova para a mesma ação): verifique o histórico antes "
                "de decidir se uma nova ação é necessária."
            ),
        }
    return {"status": "em_execucao", "message": "Confirmação já está sendo executada."}


def _executar_confirmacao(ctx: ToolContext, confirmation_id: object, *, tool_esperada: str | None = None) -> dict:
    """Executa uma única vez a proposta congelada, sem confiar no cliente."""
    if not isinstance(confirmation_id, str) or not confirmation_id.strip():
        return {"erro": "confirmation_id obrigatório"}
    ref = ctx.db.collection("mcp_confirmations").document(confirmation_id)
    snap = ref.get()
    if not snap.exists:
        return {"erro": "Confirmação não encontrada ou expirada."}
    data = snap.to_dict() or {}
    if data.get("uid") != ctx.user_uid:
        return {"erro": "Confirmação não pertence a este usuário."}
    if data.get("executed_at") or data.get("executada_em"):
        return {"status": "ja_executada", "resultado_anterior": data.get("result", data.get("resultado"))}

    # Reivindicação abandonada (P01 passo 6, achado A03 em espírito: "aprovação
    # não encerra compromisso"). Verificamos se um claim já existe ANTES do
    # teste de expiração de propósito: um claim tomado e nunca resolvido não
    # pode virar "expirada, peça uma nova prévia" -- isso na prática liberaria
    # uma segunda tentativa (nova confirmação, nova reivindicação, tool
    # rodando de novo) sem saber se a primeira já produziu o efeito. Uma vez
    # que um claim é encontrado, este confirmation_id nunca mais executa a
    # tool -- só relata `em_execucao` ou `resultado_incerto` via
    # `_status_claim_pendente`, para sempre. Resolver de verdade (sweep de
    # leases vencidos com resultado observado) é o escopo maior do P04; aqui
    # o objetivo é não mentir sobre o estado e não duplicar efeito.
    claim = ref.collection("claims").document("execute")
    claim_snap = claim.get()
    if claim_snap.exists:
        return _status_claim_pendente(claim_snap.to_dict() or {})

    expires_at = data.get("expires_at")
    if not isinstance(expires_at, datetime) or expires_at <= datetime.now(timezone.utc):
        return {"erro": "Confirmação expirada; peça uma nova prévia."}
    nome, argumentos = data.get("tool"), dict(data.get("arguments") or {})
    if not isinstance(nome, str) or not registry.is_mcp_enabled(nome):
        return {"erro": "Tool da confirmação não está disponível."}
    if tool_esperada and nome != tool_esperada:
        return {"erro": "Confirmação não pertence a esta chamada."}
    # `create` é atômico no Firestore: duas confirmações concorrentes não podem
    # obter a mesma reivindicação. O outbox usa o mesmo id como segunda barreira
    # para WhatsApp.
    try:
        claim.create({"claimed_at": datetime.now(timezone.utc)})
    except Exception:
        # Concorrência real entre a checagem acima e este ponto: outra chamada
        # tomou o claim primeiro. Mesma regra de `_status_claim_pendente`.
        latest = ref.get().to_dict() or {}
        if latest.get("executed_at") or latest.get("executada_em"):
            return {"status": "ja_executada", "resultado_anterior": latest.get("result", latest.get("resultado"))}
        return _status_claim_pendente(claim.get().to_dict() or {})
    ctx.mcp_confirmation_id = confirmation_id
    ctx.mcp_confirmation_created_at = data.get("created_at")
    ctx.mcp_confirmation_preview = data.get("preview")
    ctx.mcp_confirmed_tool = nome
    ctx.mcp_confirmed_arguments = argumentos
    try:
        result = execute_tool(nome, argumentos, ctx)
    except Exception as exc:  # não deixar uma confirmação reivindicada sem resultado
        result = {"erro": f"Falha ao executar a confirmação: {exc}"}
    if nome == "schedule_whatsapp_message":
        result = _resultado_confirmacao_whatsapp(ctx, argumentos, result)
    executed_at = datetime.now(timezone.utc)
    # Os nomes originais em inglês continuam para documentos D2; os aliases em
    # português tornam o documento inspecionável pelo contrato atual sem migração.
    ref.set({"executed_at": executed_at, "executada_em": executed_at,
             "result": result, "resultado": result}, merge=True)
    return result if isinstance(result, dict) else {"resultado": result}


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
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        # O cliente mostra isto ao modelo antes da primeira mensagem. Cobre o que
        # nao da para deduzir da lista de tools — em especial a captura de
        # memoria, que no copiloto web era subproduto da conversa e aqui depende
        # de chamada explicita.
        "instructions": _INSTRUCTIONS,
    }


def _handle_server_discover(params: dict) -> dict:
    """`server/discover` — a especificacao MCP 2026-07-28 exige que todo
    servidor o implemente ("Servers MUST implement it"); o Hermes nao tinha
    handler nenhum, entao qualquer chamada caia no `-32601 Metodo
    desconhecido` generico.

    IMPORTANTE (verificado na propria especificacao, nao suposto): chamar
    `server/discover` e OPCIONAL para o cliente — a especificacao so o marca
    como recomendado (`SHOULD`) num cenario especifico, a sondagem de
    compatibilidade no transporte stdio, que nao e o caso do Hermes (HTTP).
    Em Streamable HTTP a especificacao descreve outro mecanismo de deteccao
    (tentar um request "moderno" e inspecionar o corpo de um eventual `400`).
    Isto significa que implementar este metodo cobre uma lacuna real e
    obrigatoria da especificacao, mas **nao ha confirmacao de que seja o que
    o ChatGPT tenta chamar** — os logs da investigacao que motivou esta
    mudanca mostram ZERO requisicoes chegando a `/mcp` apos o OAuth, em
    qualquer tentativa; ou seja, nenhuma chamada a `server/discover` (nem a
    nenhum outro metodo) foi de fato observada falhando aqui. A causa do
    "action discovery failed" relatado pode estar inteiramente do lado do
    ChatGPT, antes de qualquer requisicao de rede. Ver PR para o relato
    completo dessa investigacao.
    """
    return {
        "resultType": "complete",
        "supportedVersions": sorted(_SUPPORTED_PROTOCOL_VERSIONS),
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        "_meta": {
            "io.modelcontextprotocol/serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        },
        "instructions": _INSTRUCTIONS,
        # MUST pela especificacao (server/utilities/caching) para todo
        # resultado com resultType "complete" de server/discover: sem estes
        # dois campos a propria resposta que anuncia conformidade com a
        # revisao 2026-07-28 seria no-conformante com ela.
        "ttlMs": _CATALOG_TTL_MS,
        "cacheScope": "public",
    }


def _handle_tools_list() -> dict:
    """Catalogo de tools do canal MCP.

    `resultType`/`ttlMs`/`cacheScope`: mesmo achado do Codex na PR #193 sobre
    `tools/call` (ver `_text_result`) tambem apontou este metodo — um cliente
    que negocia "2026-07-28" (possivel desde que essa versao entrou em
    `_SUPPORTED_PROTOCOL_VERSIONS` na mesma PR) exige `resultType` em TODO
    resultado "complete", e como `tools/list` e uma resposta-catalogo (nao
    muda por chamada, so por deploy — ver `_CATALOG_TTL_MS`), o mesmo raciocinio
    de cache de `server/discover` (secao server/utilities/caching da
    especificacao) se aplica igual. `tools/call` NAO leva `ttlMs`/`cacheScope`
    de proposito: cada chamada tem argumentos e efeito proprios, nao e um
    catalogo cacheavel do mesmo jeito.
    """
    tools = []
    for name in registry.list_mcp_enabled_tools():
        try:
            schema = registry.get_schema(name)
        except (FileNotFoundError, OSError) as exc:
            # Handler existe mas o schema sumiu: omitir e seguir e melhor do que
            # derrubar o `tools/list` inteiro e deixar o cliente sem nenhuma tool.
            print(f"[mcp_server] Schema ausente para '{name}', tool omitida: {exc}")
            continue
        input_schema = dict(schema.get("parameters", {"type": "object", "properties": {}}))
        if _exige_confirmacao(name):
            props = dict(input_schema.get("properties") or {})
            props.setdefault("_confirmed", {"type": "boolean", "description": "Confirma a prévia persistida."})
            props.setdefault("_confirmation_id", {"type": "string", "description": "ID devolvido pela prévia."})
            input_schema["properties"] = props
        tool_entry = {
            "name": name,
            "description": schema.get("description", ""),
            "inputSchema": input_schema,
            "_meta": {
                # `needsConfirmation` e o que ESTE canal exige (a dupla chamada
                # com `_confirmed`); `mutates` diz se a tool grava, independente
                # do gating — o cliente pode querer pedir aprovacao mesmo onde o
                # servidor nao exige.
                "needsConfirmation": _exige_confirmacao(name),
                "mutates": registry.needs_confirmation(name),
                "voiceEnabled": registry.is_voice_enabled(name),
            },
        }
        # P03 passo 3, sub-entrega 6/N: `annotations` do protocolo MCP
        # (readOnlyHint/destructiveHint por enquanto — ver docstring de
        # `registry.mcp_annotations` para o porque de idempotentHint/
        # openWorldHint ficarem fora desta sub-entrega). Campo OPCIONAL no
        # objeto Tool — omitido (nao um dict vazio) quando a tool nao tem
        # entrada no inventario, para nao publicar metadado vazio sem
        # sentido.
        annotations = registry.mcp_annotations(name)
        if annotations:
            tool_entry["annotations"] = annotations
        tools.append(tool_entry)
    return {
        "tools": tools,
        "resultType": "complete",
        "ttlMs": _CATALOG_TTL_MS,
        "cacheScope": "public",
    }


def _handle_tools_call(params: dict, *, ctx: ToolContext) -> dict:
    name = params.get("name")
    arguments = dict(params.get("arguments") or {})
    if not isinstance(name, str) or not name:
        raise McpError(-32602, "params.name obrigatorio em tools/call")

    if name == "confirmar_acao":
        # O contexto e novo por request, mas limpar estes atributos deixa a
        # funcao correta tambem quando chamada diretamente em testes.
        ctx.mcp_confirmed_tool = None
        ctx.mcp_confirmed_arguments = None
        start = time.monotonic()
        result = _executar_confirmacao(ctx, arguments.get("confirmation_id"))
        confirmed_tool = getattr(ctx, "mcp_confirmed_tool", None)
        is_err = bool(result.get("erro")) if isinstance(result, dict) else False
        if confirmed_tool:
            _audit_log(uid=ctx.user_uid, tool=confirmed_tool,
                       arguments=getattr(ctx, "mcp_confirmed_arguments", {}),
                       latency_ms=(time.monotonic() - start) * 1000,
                       is_error=is_err)
        return _text_result(result, is_error=is_err)

    if not registry.is_mcp_enabled(name):
        raise McpError(-32003, f"Tool '{name}' nao esta disponivel via MCP")

    confirmed = arguments.pop("_confirmed", None)
    confirmation_id = arguments.pop("_confirmation_id", None)
    if _exige_confirmacao(name) and confirmed is True:
        if confirmation_id:
            # Compatibilidade com clientes que ainda repetem a tool original.
            # Executa a mesma proposta persistida de `confirmar_acao`, jamais os
            # argumentos que o cliente reenviou.
            ctx.mcp_confirmed_tool = None
            ctx.mcp_confirmed_arguments = None
            start = time.monotonic()
            result = _executar_confirmacao(ctx, confirmation_id, tool_esperada=name)
            confirmed_tool = getattr(ctx, "mcp_confirmed_tool", None)
            is_err = bool(result.get("erro")) if isinstance(result, dict) else False
            if confirmed_tool:
                _audit_log(uid=ctx.user_uid, tool=confirmed_tool,
                           arguments=getattr(ctx, "mcp_confirmed_arguments", {}),
                           latency_ms=(time.monotonic() - start) * 1000,
                           is_error=is_err)
            return _text_result(result, is_error=is_err)
        else:
            # Tools do piso sempre exigem o confirmation_id de uma confirmação
            # real e persistida, hook de prévia ou não (P02 sub-entrega 2/N —
            # achado da revisão adversarial daquela sub-entrega, verificado
            # ponta a ponta contra o dispatch real: `criar_rascunho_email`,
            # `registrar_aporte_investimento` e `registrar_execucao_investimento`
            # não têm hook de prévia — `tools/hermes_tools.py::preview()`
            # devolve `None` para as três — então uma ÚNICA chamada `tools/call`
            # com `_confirmed=true` (sem `_confirmation_id`) executava direto
            # por este ramo: sem nunca criar uma confirmação real, sem nunca
            # passar por `_decisao_piso_mcp` (chamado só no ramo de CRIAÇÃO de
            # confirmação, no `elif` abaixo), e sem o "sim" explícito que o
            # comentário de `_CONFIRMACAO_OBRIGATORIA` promete ser inegociável
            # para o piso ("uma lista vazia em produção não pode tornar o envio
            # de mensagem executável sem o 'sim' do usuário" — o mesmo vale, a
            # fortiori, para as duas escritas de investimento, que não têm
            # desfazer nenhum). Esta era exatamente a lacuna de governança que
            # este preflight deveria fechar; a compatibilidade legada não pode
            # reabri-la para o piso.
            if name in autonomy_policy.FLOOR_CONFIRMACAO_OBRIGATORIA:
                return _text_result({
                    "erro": (
                        "Esta ação faz parte do piso de confirmação obrigatória e "
                        "exige o confirmation_id de uma confirmação real: repita a "
                        "chamada sem '_confirmed' para receber a prévia e o "
                        "confirmation_id."
                    ),
                }, is_error=True)
            try:
                proposta_previa = preview_tool(name, ctx, arguments)
            except Exception as exc:
                return _text_result({"erro": str(exc)}, is_error=True)
            if proposta_previa is not None:
                return _text_result({
                    "erro": "Esta confirmação precisa do confirmation_id devolvido pela prévia.",
                }, is_error=True)
            # Achado de segurança (P02 sub-entrega 7/N), mesma classe do fechado
            # acima para o piso: uma tool de confirmação obrigatória só por
            # config (`system/mcp_access.confirm_tools`, fora do piso
            # hardcoded) que também não tem hook de prévia (`preview_tool`
            # devolve `None`) caía exatamente no mesmo atalho — `_confirmed=true`
            # sem `_confirmation_id` executava direto, sem nunca criar uma
            # confirmação real nem passar por qualquer preflight de política. A
            # sub-entrega 2/N já tinha identificado esta lacuna na sua própria
            # revisão adversarial ("o mesmo tipo de gap... ainda é teoricamente
            # possível para uma tool adicionada só por config... vale endereçar
            # quando uma futura sub-entrega tratar de tools configuráveis via
            # política" — docs/autonomia/execucao.md) e deixou o atalho aberto
            # deliberadamente, chamando-o de "compatibilidade legada" — mas hoje
            # `system/mcp_access.confirm_tools` está vazio em produção (ver o
            # comentário no topo deste arquivo sobre o contorno de 27/08/2026) e
            # nenhuma tool nesse estado (confirmação por config, sem hook) foi
            # identificada como configurada — fechar isto não muda nenhum
            # comportamento observável hoje, só a lacuna teórica para quando
            # alguém configurar uma tool assim no futuro. Fechado: TODA tool que
            # exige confirmação (piso ou config) sempre exige o confirmation_id
            # de uma confirmação real, hook de prévia ou não — a mesma garantia
            # do piso, sem mais exceção "legada".
            return _text_result({
                "erro": (
                    "Esta ação exige confirmação e não tem prévia disponível: "
                    "repita a chamada sem '_confirmed' para criar uma "
                    "confirmação e receber o confirmation_id."
                ),
            }, is_error=True)
    elif _exige_confirmacao(name):
        # Preflight do motor de política (P02 sub-entrega 2/N) — só decide
        # algo para tools classificados em `CLASSE_EFEITO_PISO` (ver
        # `_decisao_piso_mcp`); os demais tools de confirmação obrigatória
        # (adicionados só por config) seguem direto para o fluxo abaixo,
        # inalterado. `DENY`/`PREPARE_ONLY` decidem e retornam aqui, ANTES de
        # criar qualquer prévia de confirmação — hoje (`system/autonomy_state`
        # ainda não é escrito por nada em produção) `estado_autonomia_atual`
        # sempre resolve ATIVO, então este bloco produz sempre
        # `REQUIRE_APPROVAL` e cai no mesmo fluxo de sempre, sem mudar
        # comportamento visível; ele só passa a ter efeito no dia em que
        # `system/autonomy_state` for escrito pela primeira vez.
        decisao_piso = _decisao_piso_mcp(ctx, name, arguments)
        if decisao_piso is not None and decisao_piso.decision == Decisao.DENY:
            return _text_result({
                "status": "denied",
                "tool": name,
                "reason_code": decisao_piso.reason_code,
                "message": decisao_piso.motivo_legivel or (
                    "Ação bloqueada pela política de autonomia vigente."
                ),
            }, is_error=True)
        if decisao_piso is not None and decisao_piso.decision == Decisao.PREPARE_ONLY:
            return _text_result({
                "status": "prepare_only",
                "tool": name,
                "reason_code": decisao_piso.reason_code,
                "message": (
                    "Autonomia está em modo somente-preparação: esta ação não "
                    "pode ser confirmada/executada agora. "
                    + (decisao_piso.motivo_legivel or "")
                ).strip(),
            }, is_error=False)
        erro_argumentos = _erro_campos_obrigatorios(name, arguments)
        if erro_argumentos is not None:
            return erro_argumentos
        erro_tipos = _erro_tipos_invalidos(name, arguments)
        if erro_tipos is not None:
            return erro_tipos
        erro_valores = _erro_valores_invalidos(name, arguments)
        if erro_valores is not None:
            return erro_valores
        try:
            proposal = preview_tool(name, ctx, arguments)
        except Exception as exc:  # prévia inválida deve apontar o dado, sem mutar
            return _text_result({"erro": str(exc)}, is_error=True)
        # Uma prévia pode recusar o destino. Neste caso não há ato a confirmar e
        # não se deixa uma confirmação pendente para um identificador cru.
        if proposal and proposal.get("status") in {"destinatario_desconhecido", "destinatario_ambiguo"}:
            return _text_result(proposal, is_error=False)
        try:
            confirmation_id = _criar_confirmacao(ctx, name, arguments, proposal)
        except Exception as exc:
            return _text_result({"erro": str(exc)}, is_error=True)
        if proposal is not None:
            return _text_result({
                "status": proposal.get("status", "confirmation_required"),
                "tool": name,
                "confirmation_required": True,
                "preview": proposal,
                "confirmation_id": confirmation_id,
                "expira_em": getattr(ctx, "mcp_confirmation_expires_at", datetime.now(timezone.utc) + _CONFIRMACAO_TTL).isoformat(),
                "message": "Confira a prévia e, após o sim explícito, chame confirmar_acao(confirmation_id) para executar.",
            }, is_error=False)
        return _text_result({
            "status": "confirmation_required",
            "tool": name,
            "confirmation_id": confirmation_id,
            "expira_em": getattr(ctx, "mcp_confirmation_expires_at", datetime.now(timezone.utc) + _CONFIRMACAO_TTL).isoformat(),
            "message": (
                "Esta acao grava no Hermes e exige confirmacao explicita do usuario. "
                "Mostre a ele exatamente o que sera feito e, apos o 'sim', chame "
                "confirmar_acao(confirmation_id) para executar."
            ),
        }, is_error=False)

    # `task_id` no argumento tem prioridade; serve tambem para dar contexto as
    # tools que aceitam a acao implicitamente.
    if arguments.get("task_id"):
        ctx.task_id = str(arguments["task_id"])

    erro_argumentos = _erro_campos_obrigatorios(name, arguments)
    if erro_argumentos is not None:
        return erro_argumentos

    erro_tipos = _erro_tipos_invalidos(name, arguments)
    if erro_tipos is not None:
        return erro_tipos

    erro_valores = _erro_valores_invalidos(name, arguments)
    if erro_valores is not None:
        return erro_valores

    # O perfil do usuario era alimentado so por `askCopilotoHermes`. Com a
    # interacao migrando para clientes MCP, aquele caminho para de ser exercido e
    # `ai_profile.historico_deduzido` congela — sem erro e sem log. Registrar
    # aqui mantem o sistema sabendo o que o usuario anda pedindo.
    try:
        from mcp_signals import registrar as registrar_sinal

        registrar_sinal(ctx.user_uid, name, arguments, ctx.task_id)
    except Exception as exc:  # noqa: BLE001 — telemetria nunca derruba a chamada
        print(f"[mcp_server] Falha ao registrar sinal de intencao: {exc}")

    if name in _TOOLS_LONGAS:
        from mcp_jobs import criar_job

        job_id = criar_job(
            ctx.user_uid, name, arguments,
            session_id=ctx.session_id, task_id=ctx.task_id,
        )
        _audit_log(uid=ctx.user_uid, tool=name, arguments=arguments, latency_ms=0.0, is_error=False)
        return _text_result({
            "status": "processing",
            "job_id": job_id,
            "tool": name,
            "message": (
                "Esta tool leva mais de um minuto e roda fora do request. Chame "
                "consultar_job com este job_id em alguns segundos para pegar o "
                "resultado; se ainda estiver 'processing', consulte de novo."
            ),
        }, is_error=False)

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
            is_error=is_error,
        )

    # Mesmo motivo do `resultType` em `_text_result` acima — este e o unico
    # retorno de `tools/call` que nao passa por ela (monta o envelope direto
    # porque `text` aqui pode ja vir como string crua do executor, nao um
    # payload dict a serializar).
    return {"content": [{"type": "text", "text": text}], "isError": is_error, "resultType": "complete"}


def _erro_campos_obrigatorios(name: str, arguments: dict) -> dict | None:
    """Preflight de `_handle_tools_call` (P03 passo 2, sub-entrega 2/N):
    `None` quando a chamada tem todos os campos que o proprio schema
    publicado (`tools/list`) marca como `required`; senao, a resposta MCP
    de erro pronta para devolver direto.

    So checa presenca, nao tipo (ver docstring de
    `registry.campos_obrigatorios_ausentes`). Chamado em dois pontos de
    `_handle_tools_call`, os dois unicos onde `arguments` de fato representa
    o payload de negocio completo da tool: antes de criar a previa de uma
    tool que exige confirmacao, e antes de executar direto uma tool que
    nao exige. Deliberadamente NAO chamado no reenvio `_confirmed=true`
    (`arguments` ali e so o envelope `_confirmation_id`, o payload real ja
    foi validado — ou nao — quando a previa foi criada) nem dentro de
    `_executar_confirmacao` (roda sobre o argumento ja congelado no
    Firestore na criacao da previa, nao sobre entrada nova do cliente).
    """
    ausentes = registry.campos_obrigatorios_ausentes(name, arguments)
    if not ausentes:
        return None
    campos = ", ".join(f"'{c}'" for c in ausentes)
    return _text_result({
        "erro": (
            f"Campo(s) obrigatório(s) ausente(s) para '{name}': {campos}. "
            "Preencha e tente novamente."
        ),
    }, is_error=True)


def _erro_tipos_invalidos(name: str, arguments: dict) -> dict | None:
    """Preflight de `_handle_tools_call` (P03 passo 2, sub-entrega 4/N):
    `None` quando nenhum campo presente tem tipo ESTRUTURAL (`array`/
    `object`) incompatível com o schema publicado; senão, a resposta MCP de
    erro pronta para devolver.

    Só cobre `array`/`object` -- os quatro tipos escalares
    (`string`/`integer`/`number`/`boolean`) ficam de fora desta sub-entrega
    de propósito (ver docstring de `registry.tipos_invalidos` para o
    porquê: handlers já toleram deliberadamente `"20"` onde esperam `20`,
    e uma checagem escalar estrita rejeitaria chamadas que hoje funcionam).
    Mesmo dentro de `array`/`object`, uma lista fechada de campos com
    tolerância comprovada a string JSON (achado da revisão adversarial,
    ver `registry._CAMPOS_COM_TOLERANCIA_A_STRING_JSON`) fica de fora.

    Chamado logo depois de `_erro_campos_obrigatorios`, nos mesmos dois
    pontos de `_handle_tools_call` onde `arguments` representa o payload de
    negócio completo -- mesmo raciocínio de escopo, não repetido aqui.
    """
    problemas = registry.tipos_invalidos(name, arguments)
    if not problemas:
        return None
    detalhes = "; ".join(
        f"'{p['campo']}' (esperado {p['esperado']}, recebido {p['recebido']})"
        for p in problemas
    )
    return _text_result({
        "erro": (
            f"Campo(s) com tipo inválido para '{name}': {detalhes}. "
            "Corrija o formato e tente novamente."
        ),
    }, is_error=True)


def _erro_valores_invalidos(name: str, arguments: dict) -> dict | None:
    """Preflight de `_handle_tools_call` (P03 passo 2, sub-entrega 5/N):
    `None` quando nenhum campo presente tem valor fora da lista `enum` que o
    schema publicado (`tools/list`) declara para ele; senão, a resposta MCP
    de erro pronta para devolver.

    Só cobre propriedades de nível superior que de fato declaram `enum` (ver
    docstring de `registry.valores_invalidos` para o catálogo atual e para o
    porquê de `enum` aninhado, como o de cada etapa de `plano_acao`/
    `etapas`, ficar fora desta sub-entrega).

    Chamado logo depois de `_erro_tipos_invalidos`, nos mesmos dois pontos
    de `_handle_tools_call` onde `arguments` representa o payload de
    negócio completo -- mesmo raciocínio de escopo, não repetido aqui. Como
    nenhum campo com `enum` no catálogo atual é `array`/`object`, não há
    conflito de prioridade real com `_erro_tipos_invalidos` hoje; a ordem
    (tipo antes de valor) é só para manter o mesmo padrão de "checagem mais
    estrutural primeiro" das duas sub-entregas anteriores.
    """
    problemas = registry.valores_invalidos(name, arguments)
    if not problemas:
        return None
    detalhes = "; ".join(
        f"'{p['campo']}' (recebido {p['recebido']!r}, esperado um de {p['esperado']})"
        for p in problemas
    )
    return _text_result({
        "erro": (
            f"Valor inválido para '{name}': {detalhes}. "
            "Corrija o valor e tente novamente."
        ),
    }, is_error=True)


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
        # Fecha o achado do Codex na PR #193 (07/09/2026): `_SUPPORTED_PROTOCOL_
        # VERSIONS` passou a incluir "2026-07-28" (para o `server/discover` do
        # ChatGPT), mas nenhum retorno de `tools/call` levava `resultType` — um
        # cliente 2026-nativo que negocia essa versao (por `initialize` ou por
        # `server/discover`) passa a EXIGIR o campo em toda resposta; sem ele
        # cada chamada de tool era rejeitada por validacao de schema, mesmo com
        # a chamada tendo sido executada com sucesso no servidor. Reproduzido ao
        # vivo nesta investigacao (relato do dono, 07/09/2026): TODA chamada
        # falhava, nao so um subconjunto de handlers — o formato de resposta e
        # unico para qualquer tool, entao a lacuna era uniforme. "complete" e o
        # unico valor que faz sentido aqui (nenhuma tool do Hermes usa o fluxo
        # de multiplas idas-e-vindas do proprio protocolo — MRTR/elicitation —
        # que e o outro caso previsto, "input_required"; os fluxos de
        # confirmacao do Hermes sao caseiros, dentro do payload JSON, nao o
        # mecanismo nativo do protocolo). Em conexoes de era anterior a 2026 o
        # campo e ignorado pelo cliente (a especificacao descreve isso como
        # "estranho e descartado antes da validacao"), entao adiciona-lo aqui
        # incondicionalmente nao quebra nenhum cliente legado.
        "resultType": "complete",
    }


def _handle_prompts_list() -> dict:
    """Os POPs do Hermes, publicados como prompts MCP.

    Um POP e um procedimento operacional que o usuario ja escreveu e versionou em
    `pops_diretrizes`. No copiloto web ele entra sozinho no system prompt quando
    um gatilho casa com o texto — util, mas invisivel e nao acionavel.

    Como prompt MCP ele vira algo que o usuario escolhe: o procedimento deixa de
    ser um documento que ele precisa lembrar de seguir e passa a ser executavel.
    Nao ha logica nova aqui, so exposicao do que ja existe.
    """
    prompts = []
    for snap in firestore.client().collection("pops_diretrizes").limit(100).stream():
        dados = snap.to_dict() or {}
        instrucao = (dados.get("instrucao_sistema") or "").strip()
        titulo = (dados.get("titulo") or "").strip()
        if not instrucao or not titulo:
            continue
        gatilhos = [str(g) for g in (dados.get("gatilhos") or []) if str(g).strip()]
        prompts.append({
            "name": snap.id,
            "title": titulo,
            "description": (
                ("[SEMPRE ATIVO] " if dados.get("sempre_ativo") is True else "")
                + f"POP do Hermes: {titulo}."
                + (f" Aciona em: {', '.join(gatilhos[:6])}." if gatilhos else "")
            ),
        })
    return {"prompts": prompts, "resultType": "complete"}


def _handle_prompts_get(params: dict) -> dict:
    nome = params.get("name")
    if not isinstance(nome, str) or not nome:
        raise McpError(-32602, "params.name obrigatorio em prompts/get")

    snap = firestore.client().collection("pops_diretrizes").document(nome).get()
    if not snap.exists:
        raise McpError(-32602, f"POP desconhecido: {nome}")

    dados = snap.to_dict() or {}
    titulo = (dados.get("titulo") or nome).strip()
    instrucao = (dados.get("instrucao_sistema") or "").strip()
    if not instrucao:
        raise McpError(-32602, f"POP '{titulo}' nao tem instrucao_sistema definida.")

    return {
        "description": f"POP do Hermes: {titulo}",
        "messages": [{
            "role": "user",
            "content": {
                "type": "text",
                "text": (
                    f"Siga este procedimento operacional do Hermes.\n\n"
                    f"## {titulo}\n\n{instrucao}\n\n"
                    "Use as tools do Hermes para executar o que o procedimento pedir. "
                    "Se faltar algum dado para seguir um passo, pergunte antes de "
                    "prosseguir em vez de supor."
                ),
            },
        }],
        "resultType": "complete",
    }


def _handle_resources_list() -> dict:
    return {
        "resources": [{
            "uri": _RESOURCE_VOICE_CONTEXT,
            "name": "Contexto do copiloto Hermes",
            "description": "Persona, perfil do usuario autenticado e memorias recentes — para compor o system prompt de um cliente externo.",
            "mimeType": "text/plain",
        }],
        "resultType": "complete",
    }


def _handle_resources_read(params: dict, *, uid: str) -> dict:
    uri = params.get("uri")
    if uri != _RESOURCE_VOICE_CONTEXT:
        raise McpError(-32602, f"Resource desconhecido: {uri}")

    db = firestore.client()
    text = build_mcp_voice_context(db, uid=uid)
    return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": text}], "resultType": "complete"}


# --------------------------------------------------------------------------
# Auditoria e helpers HTTP
# --------------------------------------------------------------------------

def _audit_log(
    *,
    uid: str | None,
    tool: str,
    arguments: dict,
    latency_ms: float,
    is_error: bool = False,
) -> None:
    try:
        db = firestore.client()
        db.collection("mcp_audit_log").add({
            "uid": uid,
            "tool": tool,
            "arguments": json.loads(json.dumps(arguments, ensure_ascii=False, default=str)),
            "latency_ms": round(latency_ms, 1),
            "is_error": bool(is_error),
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
    except Exception as exc:
        print(f"[mcp_server] Falha ao gravar audit log (tool={tool}): {exc}")


def _mcp_call_log_info(
    method: str,
    *,
    ok: bool,
    latency_ms: float,
    result: dict | None = None,
    error_code: int | None = None,
) -> dict:
    """Monta o registro de uma chamada JSON-RPC ao `/mcp`, sem I/O.

    Existe porque o access log generico do Cloud Run (o que ja usamos para
    diagnosticar a integracao com o ChatGPT) mostra status/duracao/tamanho por
    HTTP request, mas nao o METODO JSON-RPC dentro do corpo — a pergunta mais
    comum ao investigar um cliente novo ("chegou a chamar tools/list? quantas
    tools voltaram?") exigia abrir cada linha manualmente. So numeros e nomes
    de metodo/tool: nunca argumento, token, code, verifier ou qualquer dado
    pessoal do usuario.
    """
    info: dict = {"method": method, "ok": ok, "latency_ms": round(latency_ms, 1)}
    if error_code is not None:
        info["error_code"] = error_code
    if ok and isinstance(result, dict):
        if method == "tools/list":
            info["tool_count"] = len(result.get("tools") or [])
        elif method == "tools/call":
            info["is_error"] = bool(result.get("isError"))
        elif method == "server/discover":
            info["supported_versions"] = result.get("supportedVersions")
        try:
            info["response_bytes"] = len(json.dumps(result, ensure_ascii=False, default=str))
        except Exception:
            pass
    return info


def _log_mcp_call(
    method: str,
    *,
    ok: bool,
    latency_ms: float,
    result: dict | None = None,
    error_code: int | None = None,
) -> None:
    try:
        info = _mcp_call_log_info(method, ok=ok, latency_ms=latency_ms, result=result, error_code=error_code)
        print(f"[mcp_server] chamada: {json.dumps(info, ensure_ascii=False)}")
    except Exception as exc:  # noqa: BLE001 — instrumentacao nunca derruba a chamada
        print(f"[mcp_server] Falha ao logar chamada (method={method}): {exc}")


def _json_response(payload: dict, status: int = 200) -> https_fn.Response:
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        mimetype="application/json",
    )


# Aponta o cliente para o protected resource metadata, que por sua vez aponta
# para o authorization server. Sem este header no 401 o Claude nao tem como
# descobrir onde autenticar: a origem de Cloud Functions nao consegue servir
# `/.well-known/*` (o primeiro segmento do path e o nome da funcao), entao o
# fallback por sondagem daquelas rotas nunca acha nada. Ver mcp_oauth.py.
_RESOURCE_METADATA_URL = (
    "https://gestao-hermes.firebaseapp.com/.well-known/oauth-protected-resource"
)


def _json_rpc_error(rpc_id, code: int, message: str) -> https_fn.Response:
    status = 401 if code == -32001 else 403 if code == -32002 else 200
    resposta = _json_response({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": code, "message": message},
    }, status=status)
    if status == 401:
        # O 401 e obrigatorio: o Claude ignora WWW-Authenticate numa resposta 200.
        resposta.headers["WWW-Authenticate"] = (
            f'Bearer resource_metadata="{_RESOURCE_METADATA_URL}"'
        )
    return resposta
