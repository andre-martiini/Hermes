"""Autenticação Firebase local; somente o refresh token fica no cofre do SO."""

from __future__ import annotations

import os
import time
from pathlib import Path

import keyring
import requests
from dotenv import load_dotenv

KEYRING_SERVICE = "hermes-voice-client"
KEYRING_USER = "firebase-refresh-token"
_cached_token: str | None = None
_expires_at = 0.0


class AuthError(RuntimeError):
    pass


def load_environment() -> None:
    here = Path(__file__).resolve().parent
    load_dotenv(here / ".env")
    load_dotenv(here.parent / "hermes-voice-client" / ".env")


def _api_key() -> str:
    load_environment()
    value = os.environ.get("FIREBASE_WEB_API_KEY", "").strip()
    if not value:
        raise AuthError("FIREBASE_WEB_API_KEY não configurada no .env do agente ou do cliente de voz.")
    return value


def has_session() -> bool:
    return bool(keyring.get_password(KEYRING_SERVICE, KEYRING_USER))


def store_refresh_token(value: str) -> None:
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, value)


def get_id_token(*, force_refresh: bool = False) -> str:
    global _cached_token, _expires_at
    now = time.monotonic()
    if not force_refresh and _cached_token and now < _expires_at:
        return _cached_token
    refresh_token = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    if not refresh_token:
        raise AuthError("Sessão Hermes ausente. Execute login_hermes.py uma vez.")
    response = requests.post(
        "https://securetoken.googleapis.com/v1/token",
        params={"key": _api_key()},
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=20,
    )
    if response.status_code != 200:
        raise AuthError(f"Não foi possível renovar a sessão Hermes ({response.status_code}).")
    payload = response.json()
    rotated = payload.get("refresh_token")
    if rotated and rotated != refresh_token:
        store_refresh_token(rotated)
    _cached_token = payload["id_token"]
    _expires_at = now + max(60, int(payload.get("expires_in", 3600)) - 120)
    return _cached_token
