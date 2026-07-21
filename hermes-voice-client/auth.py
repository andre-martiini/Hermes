"""Gerencia o Firebase ID Token usado para autenticar no servidor MCP do Hermes.

O refresh token fica no keyring do sistema operacional (nunca em arquivo texto).
O ID token e cacheado em memoria e renovado automaticamente pouco antes de expirar.
"""

from __future__ import annotations

import os
import time

import keyring
import requests

KEYRING_SERVICE = "hermes-voice-client"
KEYRING_USER = "firebase-refresh-token"

_cached_id_token: str | None = None
_cached_expires_at: float = 0.0


class AuthError(Exception):
    pass


def _api_key() -> str:
    key = os.environ.get("FIREBASE_WEB_API_KEY", "").strip()
    if not key:
        raise AuthError("FIREBASE_WEB_API_KEY nao configurada no .env")
    return key


def store_refresh_token(refresh_token: str) -> None:
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, refresh_token)


def has_refresh_token() -> bool:
    return bool(keyring.get_password(KEYRING_SERVICE, KEYRING_USER))


def _get_refresh_token() -> str:
    token = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    if not token:
        raise AuthError(
            "Nenhuma sessao Hermes encontrada no keyring do sistema. "
            "Rode 'python login.py' primeiro para autenticar."
        )
    return token


def get_id_token(*, force_refresh: bool = False) -> str:
    global _cached_id_token, _cached_expires_at

    now = time.monotonic()
    if not force_refresh and _cached_id_token and now < _cached_expires_at:
        return _cached_id_token

    refresh_token = _get_refresh_token()
    resp = requests.post(
        "https://securetoken.googleapis.com/v1/token",
        params={"key": _api_key()},
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=15,
    )
    if resp.status_code != 200:
        raise AuthError(f"Falha ao renovar ID token do Firebase: {resp.status_code} {resp.text[:300]}")

    data = resp.json()
    id_token = data["id_token"]
    new_refresh_token = data.get("refresh_token")
    expires_in = int(data.get("expires_in", 3600))

    if new_refresh_token and new_refresh_token != refresh_token:
        store_refresh_token(new_refresh_token)

    _cached_id_token = id_token
    _cached_expires_at = now + max(60, expires_in - 120)  # renova 2 min antes de expirar
    return id_token
