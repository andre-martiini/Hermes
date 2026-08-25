#!/usr/bin/env python3
"""Emite o header Authorization para o servidor MCP do Hermes.

Feito para o `headersHelper` do Claude Code: o cliente executa este script na
hora de conectar e mescla o JSON impresso no stdout nos headers da conexao.

    {"Authorization": "Bearer <Firebase ID Token>"}

Por que existe: `mcpServer` autentica com Firebase ID Token, que vale 1 hora.
Um token colado a mao em `--header` para de funcionar no meio do dia; este
script gera um novo a cada conexao.

O token NAO e gravado em disco em momento algum — e mintado, impresso e
esquecido. Se a sessao passar de uma hora, reconecte o servidor no cliente
(`/mcp` no Claude Code) para gerar outro.

Fluxo: chave de service account -> custom token (assinado localmente) ->
troca por ID token no endpoint `signInWithCustomToken` do Firebase Auth.

Uso:
    python scripts/hermes_mcp_headers.py

Configuracao por variavel de ambiente (todas opcionais, com padrao para este repo):
    HERMES_SERVICE_ACCOUNT  caminho da chave de service account
                            (padrao: firebase_service_account_key.json na raiz)
    HERMES_MCP_UID          uid a autenticar (padrao: le de system/mcp_access)
    HERMES_FIREBASE_API_KEY Web API key do projeto (padrao: a do app web)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERVICE_ACCOUNT_PADRAO = os.path.join(_RAIZ, "firebase_service_account_key.json")

# Web API key do app cliente. Nao e segredo: ja vai no bundle do front-end, e
# sozinha nao autentica nada — a troca exige o custom token assinado acima.
_API_KEY_PADRAO = "AIzaSyCc00Qqsa7Zgfx9NZkLoPj_gvXcuMczuxk"

_SIGN_IN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={key}"
)


def _erro(mensagem: str, codigo: int = 1):
    print(mensagem, file=sys.stderr)
    raise SystemExit(codigo)


def _resolver_uid(app, caminho_credencial: str) -> str:
    """UID a autenticar: da env var, ou o primeiro da allowlist do servidor.

    Ler a allowlist evita ter que repetir o uid em dois lugares — o servidor ja
    precisa dele em `system/mcp_access.allowed_uids`.
    """
    uid_env = (os.environ.get("HERMES_MCP_UID") or "").strip()
    if uid_env:
        return uid_env

    from firebase_admin import firestore

    snap = firestore.client(app).collection("system").document("mcp_access").get()
    permitidos = (snap.to_dict() or {}).get("allowed_uids", []) if snap.exists else []
    if not permitidos:
        _erro(
            "Nenhum uid encontrado em system/mcp_access.allowed_uids e HERMES_MCP_UID "
            "nao esta definida.\nConfigure a allowlist do servidor MCP antes de conectar "
            "(veja docs/okf/copiloto/mcp-servidor.md)."
        )
    if len(permitidos) > 1:
        print(
            f"[aviso] {len(permitidos)} uids na allowlist; usando '{permitidos[0]}'. "
            "Defina HERMES_MCP_UID para escolher outro.",
            file=sys.stderr,
        )
    return str(permitidos[0])


def _trocar_por_id_token(custom_token: str, api_key: str) -> str:
    corpo = json.dumps({"token": custom_token, "returnSecureToken": True}).encode("utf-8")
    requisicao = urllib.request.Request(
        _SIGN_IN_URL.format(key=api_key),
        data=corpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", errors="replace")
        _erro(f"Firebase recusou a troca do custom token (HTTP {exc.code}): {detalhe}")
    except urllib.error.URLError as exc:
        _erro(f"Falha de rede ao falar com o Firebase Auth: {exc.reason}")

    id_token = dados.get("idToken")
    if not id_token:
        _erro(f"Resposta do Firebase sem idToken: {dados}")
    return id_token


def main() -> None:
    caminho = os.environ.get("HERMES_SERVICE_ACCOUNT") or _SERVICE_ACCOUNT_PADRAO
    if not os.path.exists(caminho):
        _erro(
            f"Chave de service account nao encontrada em: {caminho}\n"
            "Defina HERMES_SERVICE_ACCOUNT com o caminho correto."
        )

    try:
        import firebase_admin
        from firebase_admin import auth, credentials
    except ImportError:
        _erro(
            "firebase-admin nao esta instalado neste Python.\n"
            "Instale com: pip install firebase-admin\n"
            "(ou aponte o headersHelper para o Python do venv de functions/)"
        )

    # Nome proprio para nao colidir com um app default ja inicializado caso
    # este modulo seja importado de dentro de outro processo.
    try:
        app = firebase_admin.get_app("hermes-mcp-headers")
    except ValueError:
        app = firebase_admin.initialize_app(
            credentials.Certificate(caminho), name="hermes-mcp-headers"
        )

    uid = _resolver_uid(app, caminho)
    custom_token = auth.create_custom_token(uid, app=app).decode("utf-8")
    id_token = _trocar_por_id_token(
        custom_token, os.environ.get("HERMES_FIREBASE_API_KEY") or _API_KEY_PADRAO
    )

    # Unica coisa no stdout: o cliente MCP le isto como JSON.
    print(json.dumps({"Authorization": f"Bearer {id_token}"}))


if __name__ == "__main__":
    main()
