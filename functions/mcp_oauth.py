"""Authorization server OAuth 2.1 do servidor MCP do Hermes.

Existe para as superficies hospedadas do Claude (Claude.ai, Desktop, mobile,
Cowork), que nao tem `headersHelper`: elas so aceitam `oauth_dcr`, `oauth_cimd`,
`oauth_anthropic_creds`, `static_headers` (beta) ou `none`. Este modulo entrega
o primeiro — OAuth 2.0 com Dynamic Client Registration e PKCE S256.

## Por que tudo fica na origem do Hosting

A origem `cloudfunctions.net` nao consegue servir `/.well-known/*`: o primeiro
segmento do path e o nome da funcao, entao `/.well-known/oauth-...` procuraria
uma funcao com esse nome e o Google Frontend devolve 404 sem invocar codigo
nosso — invisivel ate nos logs. A primeira versao disto tentou contornar com o
`resource_metadata` do `401` apontando para outro host, o que a especificacao
permite. Nao bastou: a tentativa de conectar pelo Cowork falhou no registro
**sem nenhuma requisicao chegar ao servidor**, sinal de que o cliente procura o
discovery antes de receber o `401` que traria o ponteiro.

Entao MCP e OAuth passaram a atender na mesma origem do Firebase Hosting, que e
a recomendacao explicita da documentacao de conectores: assim todo caminho de
sondagem do RFC 9728 resolve, com ou sem o ponteiro.

A origem escolhida e `firebaseapp.com`, e nao `web.app`, por causa do service
worker do PWA — ver o comentario em ISSUER.

O preco e o timeout: um rewrite do Hosting corta em 60s, contra 300s da funcao
direta. Por isso a URL direta continua valendo — e o que o Claude Code usa com
`headersHelper`, e o caminho para as tools longas (`gerar_relatorio`,
`ler_documento_na_integra`).

## Fluxo

    Claude                     este modulo                    Firebase Auth
      | -- POST /oauth/register (DCR) --> client_id
      | -- GET  /oauth/authorize ------> pagina de consentimento
      |                                        | -- login Google --> ID token
      |                                  verifica ID token + allowlist
      | <-- redirect com `code` --------------|
      | -- POST /oauth/token (code+verifier) -> access (JWT) + refresh

O access token e um JWT HS256 proprio, com `aud` fixado no recurso MCP — nao um
Firebase ID token repassado. Repassar o par de tokens do Firebase entregaria ao
cliente a identidade inteira do usuario, com refresh de longa duracao e sem
escopo; o token proprio e limitado a este recurso e revogavel isoladamente.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode, urlparse

import jwt
from firebase_functions import https_fn, options
from firebase_admin import auth as firebase_auth
from firebase_admin import firestore

# Origem do OAuth. Deliberadamente o dominio `firebaseapp.com` e nao o `web.app`,
# embora os dois sirvam o mesmo site do Hosting.
#
# O PWA do Hermes registra um service worker em `web.app`, e o fallback de
# navegacao dele devolve o index.html do app para QUALQUER rota da origem — sem
# tocar na rede. Era isso que quebrava a vinculacao: o Claude abria a pagina de
# autorizacao e recebia a tela inicial do Hermes, servida do cache do navegador.
# Nada aparecia no log do servidor porque nenhuma requisicao saia da maquina.
#
# `vite.config.ts` ganhou um navigateFallbackDenylist para essas rotas, mas isso
# so vale quando o service worker antigo for substituido no navegador de cada
# usuario. Manter o OAuth numa origem sem service worker torna o fluxo imune.
ISSUER = "https://gestao-hermes.firebaseapp.com"

# URL canonica do MCP para clientes OAuth, e o valor do campo `resource` do
# protected resource metadata — que precisa bater literalmente com o que o
# usuario digita no cliente.
#
# Fica na origem do Hosting, e nao na Cloud Function direta, porque so ela serve
# `/.well-known/*`: na origem `cloudfunctions.net` o primeiro segmento do path e
# o nome da funcao, entao qualquer caminho de discovery devolve 404 do Google
# Frontend sem sequer invocar codigo nosso. Com MCP e discovery na mesma origem,
# todos os caminhos de sondagem do RFC 9728 funcionam — que e a recomendacao
# explicita da documentacao de conectores.
MCP_RESOURCE = f"{ISSUER}/mcp"

# A URL direta da funcao continua valendo para quem monta o header por conta
# propria (Claude Code com headersHelper) e para tools longas: um rewrite do
# Hosting corta em 60s, a funcao direta vai a 300s. Aceita como audiencia para
# nao invalidar um token emitido contra ela.
MCP_RESOURCE_DIRETO = "https://us-central1-gestao-hermes.cloudfunctions.net/mcpServer"

# O mesmo endpoint tambem responde pelo dominio do PWA; aceito como audiencia
# para nao invalidar token de quem tenha configurado o conector por ali.
MCP_RESOURCE_WEBAPP = "https://gestao-hermes.web.app/mcp"

_AUDIENCIAS_ACEITAS = [MCP_RESOURCE, MCP_RESOURCE_DIRETO, MCP_RESOURCE_WEBAPP]

SCOPE_PADRAO = "hermes:tools"

_ACCESS_TTL_SEC = 3600          # 1h; o cliente renova pelo refresh
_REFRESH_TTL_SEC = 60 * 60 * 24 * 30
_CODE_TTL_SEC = 120             # janela curta: o resgate e imediato

# Curto de proposito: o discovery e servido pelo CDN do Hosting, e uma hora de
# cache atrasaria demais qualquer correcao no `resource` ou nos endpoints.
_CACHE_DISCOVERY_SEC = 300

_COL_CLIENTS = "mcp_oauth_clients"
_COL_CODES = "mcp_oauth_codes"
_COL_REFRESH = "mcp_oauth_refresh"

_signing_secret_cache: str | None = None


# --------------------------------------------------------------------------
# Helpers de baixo nivel
# --------------------------------------------------------------------------

def _db():
    return firestore.client()


def _agora() -> int:
    return int(time.time())


def _hash(valor: str) -> str:
    """Codes e refresh tokens vao para o Firestore so como hash.

    Quem ler o banco nao consegue reconstruir um token utilizavel.
    """
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def _signing_secret() -> str:
    """Segredo HS256, gerado na primeira execucao e guardado em `system/`.

    `system/**` e negado a todo mundo nas firestore.rules — so o Admin SDK
    alcanca, que e exatamente o backend.
    """
    global _signing_secret_cache
    if _signing_secret_cache:
        return _signing_secret_cache

    ref = _db().collection("system").document("mcp_oauth")
    snap = ref.get()
    dados = snap.to_dict() or {} if snap.exists else {}
    segredo = dados.get("signing_secret")
    if not segredo:
        segredo = secrets.token_urlsafe(48)
        ref.set({"signing_secret": segredo}, merge=True)
    _signing_secret_cache = segredo
    return segredo


def _json(payload: dict, status: int = 200, cache_sec: int = 0) -> https_fn.Response:
    headers = {"Cache-Control": f"public, max-age={cache_sec}" if cache_sec else "no-store"}
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        mimetype="application/json",
        headers=headers,
    )


def _erro_oauth(codigo: str, descricao: str, status: int = 400) -> https_fn.Response:
    """Erro no formato do RFC 6749.

    O codigo importa: o Claude so trata refresh token invalido corretamente
    quando recebe `invalid_grant`; um codigo custom faz o refresh falhar em
    silencio e a conexao morrer sem reautenticar.
    """
    return _json({"error": codigo, "error_description": descricao}, status=status)


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

def emitir_access_token(uid: str, client_id: str, scope: str, resource: str) -> str:
    agora = _agora()
    return jwt.encode(
        {
            "iss": ISSUER,
            "sub": uid,
            "aud": resource or MCP_RESOURCE,
            "client_id": client_id,
            "scope": scope,
            "iat": agora,
            "exp": agora + _ACCESS_TTL_SEC,
            "jti": secrets.token_urlsafe(12),
        },
        _signing_secret(),
        algorithm="HS256",
    )


def validar_access_token(token: str) -> dict | None:
    """Valida um access token emitido aqui. `None` se nao for um (ou expirou).

    Usado por `mcp_server.py`, que aceita tanto este token quanto um Firebase
    ID Token — sao os dois canais: superficies hospedadas e Claude Code.
    """
    try:
        return jwt.decode(
            token,
            _signing_secret(),
            algorithms=["HS256"],
            audience=_AUDIENCIAS_ACEITAS,
            issuer=ISSUER,
        )
    except Exception:
        return None


def _emitir_refresh_token(uid: str, client_id: str, scope: str, resource: str) -> str:
    bruto = secrets.token_urlsafe(40)
    _db().collection(_COL_REFRESH).document(_hash(bruto)).set({
        "uid": uid,
        "client_id": client_id,
        "scope": scope,
        "resource": resource,
        "criado_em": _agora(),
        "expira_em": _agora() + _REFRESH_TTL_SEC,
    })
    return bruto


def _consumir_refresh_token(bruto: str, client_id: str) -> dict | None:
    """Le e invalida um refresh token. Rotacao e obrigatoria para client publico.

    DCR registra o Claude como cliente publico, e a especificacao de autorizacao
    do MCP adota a exigencia do OAuth 2.1 de rotacionar refresh tokens nesse caso.
    """
    ref = _db().collection(_COL_REFRESH).document(_hash(bruto))
    snap = ref.get()
    if not snap.exists:
        return None
    dados = snap.to_dict() or {}
    ref.delete()
    if dados.get("client_id") != client_id or dados.get("expira_em", 0) < _agora():
        return None
    return dados


# --------------------------------------------------------------------------
# Clientes (DCR) e redirect URIs
# --------------------------------------------------------------------------

def _redirect_permitido(registradas: list[str], pedida: str) -> bool:
    """Comparacao exata, com excecao do loopback.

    O Claude Code e cliente nativo e usa redirect de loopback numa porta efemera
    (RFC 8252): a porta muda a cada sessao, entao a comparacao ignora a porta
    para `localhost` e `127.0.0.1`. As superficies hospedadas usam sempre
    `https://claude.ai/api/mcp/auth_callback`, que casa exatamente.
    """
    if pedida in registradas:
        return True

    alvo = urlparse(pedida)
    if alvo.scheme != "http" or alvo.hostname not in ("localhost", "127.0.0.1"):
        return False

    for registrada in registradas:
        r = urlparse(registrada)
        if (r.scheme == "http"
                and r.hostname in ("localhost", "127.0.0.1")
                and r.path == alvo.path):
            return True
    return False


def _carregar_client(client_id: str) -> dict | None:
    snap = _db().collection(_COL_CLIENTS).document(client_id).get()
    return snap.to_dict() if snap.exists else None


def _handle_register(req: https_fn.Request) -> https_fn.Response:
    """Dynamic Client Registration (RFC 7591). Corpo em JSON, nao form-urlencoded."""
    corpo = req.get_json(silent=True) or {}
    redirect_uris = corpo.get("redirect_uris") or []

    # O que o cliente pede fica no log: quando o registro devolve 201 e mesmo
    # assim o fluxo nao avanca para /oauth/authorize, a diferenca entre pedido e
    # resposta e a unica pista disponivel deste lado.
    print(f"[mcp_oauth] DCR pedido: {json.dumps(corpo, ensure_ascii=False, default=str)[:900]}")

    if not isinstance(redirect_uris, list) or not redirect_uris:
        return _erro_oauth("invalid_redirect_uri", "redirect_uris e obrigatorio")

    client_id = f"hermes-{secrets.token_urlsafe(16)}"
    agora = _agora()
    registro = {
        "client_id": client_id,
        # Ecoa o que o cliente pediu, quando pediu algo valido: o RFC manda a
        # resposta refletir os metadados registrados, e um cliente que compara o
        # que enviou com o que voltou trava se receber outra coisa.
        "redirect_uris": [str(u) for u in redirect_uris],
        "client_name": str(corpo.get("client_name") or "Cliente MCP"),
        "grant_types": [str(g) for g in (corpo.get("grant_types")
                                         or ["authorization_code", "refresh_token"])],
        "response_types": [str(r) for r in (corpo.get("response_types") or ["code"])],
        # Cliente publico: nao ha segredo a guardar num app que roda no
        # dispositivo do usuario. A prova de posse e o PKCE.
        "token_endpoint_auth_method": "none",
        "scope": str(corpo.get("scope") or SCOPE_PADRAO),
        "client_id_issued_at": agora,
        # RFC 7591 3.2.1: obrigatorio quando ha client_secret. Nao ha, mas
        # clientes que leem o campo sem checar tratam a ausencia como erro.
        "client_secret_expires_at": 0,
    }
    _db().collection(_COL_CLIENTS).document(client_id).set({**registro, "criado_em": agora})
    print(f"[mcp_oauth] DCR resposta: client_id={client_id} redirect_uris={registro['redirect_uris']}")
    return _json(registro, status=201)


# --------------------------------------------------------------------------
# /authorize
# --------------------------------------------------------------------------

_PAGINA_CONSENTIMENTO = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Autorizar acesso ao Hermes</title>
<style>
  :root { color-scheme: light dark; }
  body { margin:0; min-height:100vh; display:grid; place-items:center;
         font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;
         background:#0b0d12; color:#e7e9ee; padding:24px; }
  .card { max-width:420px; width:100%; background:#151922; border:1px solid #252b38;
          border-radius:14px; padding:28px; }
  h1 { font-size:19px; margin:0 0 6px; }
  p { color:#a4acbd; margin:0 0 18px; font-size:14px; }
  .app { background:#1c2230; border-radius:9px; padding:12px 14px; margin-bottom:18px;
         font-size:14px; word-break:break-all; }
  .app b { color:#e7e9ee; }
  ul { margin:0 0 20px; padding-left:20px; color:#a4acbd; font-size:14px; }
  button { width:100%; padding:12px; border:0; border-radius:9px; background:#4f7cff;
           color:#fff; font-size:15px; font-weight:600; cursor:pointer; }
  button:disabled { opacity:.55; cursor:default; }
  .erro { margin-top:14px; color:#ff8080; font-size:14px; }
</style></head><body>
<div class="card">
  <h1>Autorizar acesso ao Hermes</h1>
  <p>Um cliente esta pedindo permissao para operar o Hermes em seu nome.</p>
  <div class="app">Cliente: <b>__CLIENT_NAME__</b><br>Retorno: __REDIRECT__</div>
  <ul>
    <li>Ler e criar acoes, agenda, financas, saude e contatos</li>
    <li>Enviar WhatsApp exige confirmacao a cada envio</li>
  </ul>
  <button id="b">Entrar com Google e autorizar</button>
  <div class="erro" id="e"></div>
</div>
<script>
  // Erro de carregamento do modulo (CSP, rede, gstatic bloqueado) nao aparece em
  // lugar nenhum da UI: a pagina fica bonita e inerte. Aqui ele vira texto.
  window.addEventListener("error", (ev) => {
    const alvo = document.getElementById("e");
    if (alvo && !alvo.textContent) alvo.textContent = "Falha ao carregar: " + (ev.message || ev.type);
  });
</script>
<script type="module">
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, GoogleAuthProvider, signInWithRedirect, getRedirectResult }
  from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

const app = initializeApp(__FIREBASE_CONFIG__);
const auth = getAuth(app);
const botao = document.getElementById("b");
const erro = document.getElementById("e");

// Troca o ID token do login pelo `code` e devolve o controle ao cliente OAuth.
async function concluir(user) {
  const resp = await fetch("/oauth/authorize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_token: await user.getIdToken(), params: __PARAMS__ }),
  });
  const dados = await resp.json();
  if (!resp.ok) throw new Error(dados.error_description || dados.error || "falha");
  location.href = dados.redirect;
}

// O handler do clique e ligado ANTES de qualquer await. Uma promessa lenta
// aqui — e `getRedirectResult` pode demorar — deixaria o botao inerte: a pagina
// parece pronta e simplesmente nao responde ao clique.
botao.onclick = async () => {
  botao.disabled = true; erro.textContent = "";
  try {
    // Redirect, e nao popup. Esta pagina e aberta DENTRO de um popup pelo
    // cliente OAuth, e popup dentro de popup e bloqueado na maioria dos
    // navegadores. O redirect navega a propria janela ate o Google e volta para
    // esta mesma URL, com os parametros da autorizacao preservados na query.
    await signInWithRedirect(auth, new GoogleAuthProvider());
  } catch (ex) {
    erro.textContent = ex.message || String(ex);
    botao.disabled = false;
  }
};

// Volta do Google: retoma o fluxo de onde parou.
try {
  const voltando = await getRedirectResult(auth);
  if (voltando?.user) {
    botao.disabled = true;
    botao.textContent = "Concluindo...";
    await concluir(voltando.user);
  }
} catch (ex) {
  erro.textContent = ex.message || String(ex);
}
</script></body></html>"""


def _config_firebase_web() -> dict:
    """Config publica do app web, lida de `public_configs/firebase_web`.

    Nao e segredo (vai no bundle do front-end), mas fica em Firestore em vez de
    literal aqui para nao criar mais uma copia do padrao `AIza...` no repositorio.
    """
    snap = _db().collection("public_configs").document("firebase_web").get()
    return (snap.to_dict() or {}) if snap.exists else {}


def _config_pagina_consentimento() -> dict:
    """Config do Firebase para a pagina, com `authDomain` na origem que a serve.

    Deixar o authDomain apontando para outro dominio faz o login depender de
    storage cross-origin, que os navegadores particionam — falha silenciosa e
    dificil de diagnosticar.
    """
    return {**_config_firebase_web(), "authDomain": urlparse(ISSUER).netloc}


def _validar_pedido_authorize(params: dict) -> tuple[dict | None, https_fn.Response | None]:
    client_id = params.get("client_id") or ""
    redirect_uri = params.get("redirect_uri") or ""

    cliente = _carregar_client(client_id)
    if not cliente:
        return None, _erro_oauth("invalid_client", "client_id desconhecido")
    if not _redirect_permitido(cliente.get("redirect_uris", []), redirect_uri):
        return None, _erro_oauth("invalid_request", "redirect_uri nao registrada")
    if params.get("response_type") != "code":
        return None, _erro_oauth("unsupported_response_type", "apenas response_type=code")
    if params.get("code_challenge_method") != "S256":
        return None, _erro_oauth("invalid_request", "PKCE S256 obrigatorio")
    if not params.get("code_challenge"):
        return None, _erro_oauth("invalid_request", "code_challenge obrigatorio")
    return cliente, None


def _handle_authorize_get(req: https_fn.Request) -> https_fn.Response:
    params = {k: req.args.get(k) for k in (
        "client_id", "redirect_uri", "response_type", "code_challenge",
        "code_challenge_method", "state", "scope", "resource",
    )}
    cliente, falha = _validar_pedido_authorize(params)
    if falha:
        return falha

    html = (
        _PAGINA_CONSENTIMENTO
        .replace("__CLIENT_NAME__", _escapar(cliente.get("client_name", "Cliente MCP")))
        .replace("__REDIRECT__", _escapar(params["redirect_uri"]))
        .replace("__FIREBASE_CONFIG__", json.dumps(_config_pagina_consentimento()))
        .replace("__PARAMS__", json.dumps(params))
    )
    return https_fn.Response(html, status=200, mimetype="text/html",
                             headers={"Cache-Control": "no-store"})


def _escapar(texto: str) -> str:
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _handle_authorize_post(req: https_fn.Request) -> https_fn.Response:
    """Segunda etapa: a pagina devolve o ID token do login e os params originais."""
    corpo = req.get_json(silent=True) or {}
    params = corpo.get("params") or {}
    cliente, falha = _validar_pedido_authorize(params)
    if falha:
        return falha

    try:
        decodificado = firebase_auth.verify_id_token(corpo.get("id_token") or "")
    except Exception:
        return _erro_oauth("access_denied", "Login invalido ou expirado", status=401)

    uid = decodificado.get("uid")
    if not uid or not _uid_autorizado(uid):
        return _erro_oauth(
            "access_denied",
            "Esta conta nao esta autorizada a usar o servidor MCP do Hermes.",
            status=403,
        )

    codigo = secrets.token_urlsafe(32)
    _db().collection(_COL_CODES).document(_hash(codigo)).set({
        "uid": uid,
        "client_id": params["client_id"],
        "redirect_uri": params["redirect_uri"],
        "code_challenge": params["code_challenge"],
        "scope": params.get("scope") or SCOPE_PADRAO,
        # Clampeia o `resource` (RFC 8707) ao que de fato existe: sem isso o
        # cliente escolheria a `aud` do token, e uma audiencia arbitraria nao
        # seria aceita por ninguem — falha silenciosa e dificil de rastrear.
        "resource": _resource_valido(params.get("resource")),
        "expira_em": _agora() + _CODE_TTL_SEC,
    })

    query = {"code": codigo}
    if params.get("state"):
        query["state"] = params["state"]
    separador = "&" if "?" in params["redirect_uri"] else "?"
    return _json({"redirect": f"{params['redirect_uri']}{separador}{urlencode(query)}"})


def _resource_valido(pedido: str | None) -> str:
    """So devolve um recurso que este servidor de fato protege."""
    return pedido if pedido in _AUDIENCIAS_ACEITAS else MCP_RESOURCE


def _uid_autorizado(uid: str) -> bool:
    """Mesma allowlist do servidor MCP — uma fonte so para quem pode entrar."""
    snap = _db().collection("system").document("mcp_access").get()
    permitidos = (snap.to_dict() or {}).get("allowed_uids", []) if snap.exists else []
    return uid in {str(u) for u in permitidos}


# --------------------------------------------------------------------------
# /token
# --------------------------------------------------------------------------

def _verificar_pkce(verifier: str, challenge: str) -> bool:
    calculado = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(calculado, challenge)


def _handle_token(req: https_fn.Request) -> https_fn.Response:
    # RFC 6749 4.1.3: o corpo vem form-urlencoded, nao JSON. `req.form` cobre isso;
    # o fallback em JSON existe so para clientes fora do padrao.
    dados = req.form.to_dict() if req.form else (req.get_json(silent=True) or {})
    grant = dados.get("grant_type")
    client_id = dados.get("client_id") or ""

    if grant == "authorization_code":
        return _token_por_codigo(dados, client_id)
    if grant == "refresh_token":
        return _token_por_refresh(dados, client_id)
    return _erro_oauth("unsupported_grant_type", f"grant_type nao suportado: {grant}")


def _resposta_token(uid: str, client_id: str, scope: str, resource: str) -> https_fn.Response:
    return _json({
        "access_token": emitir_access_token(uid, client_id, scope, resource),
        "token_type": "Bearer",
        "expires_in": _ACCESS_TTL_SEC,
        "refresh_token": _emitir_refresh_token(uid, client_id, scope, resource),
        "scope": scope,
    })


def _token_por_codigo(dados: dict, client_id: str) -> https_fn.Response:
    codigo = dados.get("code") or ""
    ref = _db().collection(_COL_CODES).document(_hash(codigo))
    snap = ref.get()
    if not snap.exists:
        return _erro_oauth("invalid_grant", "code invalido ou ja utilizado")

    registro = snap.to_dict() or {}
    ref.delete()   # uso unico, mesmo se a validacao abaixo falhar

    if registro.get("expira_em", 0) < _agora():
        return _erro_oauth("invalid_grant", "code expirado")
    if registro.get("client_id") != client_id:
        return _erro_oauth("invalid_grant", "code emitido para outro client_id")
    if registro.get("redirect_uri") != dados.get("redirect_uri"):
        return _erro_oauth("invalid_grant", "redirect_uri diferente da usada na autorizacao")
    if not _verificar_pkce(dados.get("code_verifier") or "", registro.get("code_challenge", "")):
        return _erro_oauth("invalid_grant", "code_verifier nao confere com o code_challenge")

    return _resposta_token(
        registro["uid"], client_id,
        registro.get("scope") or SCOPE_PADRAO,
        registro.get("resource") or MCP_RESOURCE,
    )


def _token_por_refresh(dados: dict, client_id: str) -> https_fn.Response:
    registro = _consumir_refresh_token(dados.get("refresh_token") or "", client_id)
    if not registro:
        return _erro_oauth("invalid_grant", "refresh_token invalido, expirado ou ja rotacionado")
    if not _uid_autorizado(registro["uid"]):
        return _erro_oauth("invalid_grant", "uid nao esta mais autorizado")
    return _resposta_token(
        registro["uid"], client_id,
        registro.get("scope") or SCOPE_PADRAO,
        registro.get("resource") or MCP_RESOURCE,
    )


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------

def protected_resource_metadata() -> dict:
    return {
        # Precisa bater exatamente com a URL que o usuario digita no cliente.
        "resource": MCP_RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": [SCOPE_PADRAO],
        "bearer_methods_supported": ["header"],
        "resource_name": "Hermes MCP",
        "resource_documentation": f"{ISSUER}/",
    }


def authorization_server_metadata() -> dict:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/oauth/authorize",
        "token_endpoint": f"{ISSUER}/oauth/token",
        "registration_endpoint": f"{ISSUER}/oauth/register",
        "scopes_supported": [SCOPE_PADRAO],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        # Cliente publico: o PKCE substitui o segredo de cliente.
        "token_endpoint_auth_methods_supported": ["none"],
        # Obrigatorio anunciar: clientes conformes conferem isto antes de comecar.
        "code_challenge_methods_supported": ["S256"],
    }


# --------------------------------------------------------------------------
# Roteamento
# --------------------------------------------------------------------------

@https_fn.on_request(
    cors=options.CorsOptions(cors_origins=["https://claude.ai", ISSUER],
                             cors_methods=["GET", "POST", "OPTIONS"]),
    memory=options.MemoryOption.MB_512,
    timeout_sec=30,
)
def mcpOAuth(req: https_fn.Request) -> https_fn.Response:
    caminho = (req.path or "/").rstrip("/") or "/"

    try:
        # `in` e nao `endswith`: o RFC 9728 manda sondar
        # `/.well-known/oauth-protected-resource/<path-do-recurso>`, entao a rota
        # chega com sufixo. O mesmo vale para o RFC 8414 com issuer em subpath.
        if "/.well-known/oauth-protected-resource" in caminho:
            return _json(protected_resource_metadata(), cache_sec=_CACHE_DISCOVERY_SEC)
        if "/.well-known/oauth-authorization-server" in caminho:
            return _json(authorization_server_metadata(), cache_sec=_CACHE_DISCOVERY_SEC)
        if caminho.endswith("/oauth/register"):
            return _handle_register(req)
        if caminho.endswith("/oauth/authorize"):
            if req.method == "POST":
                return _handle_authorize_post(req)
            return _handle_authorize_get(req)
        if caminho.endswith("/oauth/token"):
            return _handle_token(req)
    except Exception as exc:  # noqa: BLE001 — nunca vazar stack trace
        print(f"[mcp_oauth] Erro em {caminho}: {exc}")
        return _erro_oauth("server_error", "Erro interno no authorization server", status=500)

    return _erro_oauth("invalid_request", f"Rota desconhecida: {caminho}", status=404)
