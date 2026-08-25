#!/usr/bin/env python3
"""Cria um cliente OAuth com client_id fixo, para informar no conector.

O Dynamic Client Registration funciona (responde 201 com o eco correto), mas o
Claude nao avancava para `/oauth/authorize` depois dele. A propria mensagem de
erro do conector oferece a saida: informar um OAuth Client ID nas configuracoes
avancadas, o que pula o DCR e leva direto a autorizacao.

Um client_id pre-registrado tambem e estavel — nao gera um cliente novo a cada
conexao, que e o efeito colateral do DCR.

Uso:
    python scripts/seed_mcp_oauth_client.py [client_id]

Padrao: `hermes-cowork`, com o redirect das superficies hospedadas do Claude.
"""

from __future__ import annotations

import os
import sys
import time

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CLIENT_ID_PADRAO = "hermes-cowork"
REDIRECT_URIS = [
    # Superficies hospedadas: Claude.ai, Desktop, mobile, Cowork.
    "https://claude.ai/api/mcp/auth_callback",
    # Claude Code, que e cliente nativo e usa loopback em porta efemera
    # (RFC 8252) — a porta e ignorada na comparacao.
    "http://localhost/callback",
    "http://127.0.0.1/callback",
]


def main() -> None:
    client_id = sys.argv[1] if len(sys.argv) > 1 else CLIENT_ID_PADRAO

    import firebase_admin
    from firebase_admin import credentials, firestore

    chave = os.environ.get("HERMES_SERVICE_ACCOUNT") or os.path.join(
        _RAIZ, "firebase_service_account_key.json"
    )
    if not os.path.exists(chave):
        raise SystemExit(f"Service account nao encontrada em {chave}")

    try:
        app = firebase_admin.get_app("hermes-seed-client")
    except ValueError:
        app = firebase_admin.initialize_app(
            credentials.Certificate(chave), name="hermes-seed-client"
        )

    registro = {
        "client_id": client_id,
        "redirect_uris": REDIRECT_URIS,
        "client_name": "Hermes (client fixo)",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        # Cliente publico: a prova de posse e o PKCE, nao um segredo.
        "token_endpoint_auth_method": "none",
        "scope": "hermes:tools",
        "client_id_issued_at": int(time.time()),
        "client_secret_expires_at": 0,
        "criado_em": int(time.time()),
        "origem": "seed_mcp_oauth_client.py",
    }
    firestore.client(app).collection("mcp_oauth_clients").document(client_id).set(registro)

    print(f"cliente gravado: {client_id}")
    print("\nNo conector, em Advanced settings:")
    print(f"  OAuth Client ID:     {client_id}")
    print("  OAuth Client Secret: (deixe em branco)")


if __name__ == "__main__":
    main()
