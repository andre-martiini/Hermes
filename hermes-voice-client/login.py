"""Autenticacao unica: faz login com email/senha no Firebase Auth do Hermes,
guarda apenas o refresh token no keyring do sistema e descarta a senha da
memoria imediatamente. Rode uma vez (e de novo se a sessao expirar/for
revogada) antes de usar main.py.
"""

from __future__ import annotations

import getpass
import os
import sys

import requests
from dotenv import load_dotenv

import auth

load_dotenv()


def main() -> None:
    api_key = os.environ.get("FIREBASE_WEB_API_KEY", "").strip()
    if not api_key:
        print("Defina FIREBASE_WEB_API_KEY no .env antes de rodar este script.")
        sys.exit(1)

    email = input("Email Hermes (Firebase Auth): ").strip()
    password = getpass.getpass("Senha: ")

    resp = requests.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
        params={"key": api_key},
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=15,
    )
    password = None  # descarta da memoria assim que possivel

    if resp.status_code != 200:
        print(f"Falha no login: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)

    data = resp.json()
    auth.store_refresh_token(data["refreshToken"])
    print(f"Login ok para uid={data['localId']}.")
    print("Refresh token salvo no keyring do sistema (nao fica em arquivo texto).")
    print(
        "Se ainda nao fez isso: peca para adicionar esse uid em "
        "system/mcp_access.allowed_uids no Firestore do Hermes, senao o "
        "servidor MCP vai recusar as chamadas."
    )


if __name__ == "__main__":
    main()
