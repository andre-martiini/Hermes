"""Login único no Hermes; a senha é descartada e o refresh token vai ao keyring."""

from __future__ import annotations

import getpass
import sys

import requests

import firebase_auth


def main() -> int:
    email = input("E-mail do Hermes: ").strip()
    password = getpass.getpass("Senha do Hermes: ")
    response = requests.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
        params={"key": firebase_auth._api_key()},
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=20,
    )
    password = None
    if response.status_code != 200:
        print(f"Login do Hermes falhou ({response.status_code}).")
        return 1
    firebase_auth.store_refresh_token(response.json()["refreshToken"])
    print("Sessão Hermes armazenada com segurança no Gerenciador de Credenciais do Windows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
