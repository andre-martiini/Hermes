"""Cliente mínimo das callables autenticadas usadas pelo agente."""

from __future__ import annotations

import os

import requests

import firebase_auth


class HermesApiError(RuntimeError):
    pass


def call(function_name: str, data: dict, *, timeout: int = 150) -> dict:
    firebase_auth.load_environment()
    project = os.environ.get("HERMES_PROJECT_ID", "gestao-hermes").strip()
    url = f"https://us-central1-{project}.cloudfunctions.net/{function_name}"
    for attempt in range(2):
        token = firebase_auth.get_id_token(force_refresh=attempt > 0)
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"data": data},
            timeout=timeout,
        )
        if response.status_code not in (401, 403) or attempt == 1:
            break
    try:
        payload = response.json()
    except ValueError as error:
        raise HermesApiError(f"Resposta inválida do Hermes ({response.status_code}).") from error
    if response.status_code != 200 or payload.get("error"):
        detail = (payload.get("error") or {}).get("message") or f"HTTP {response.status_code}"
        raise HermesApiError(str(detail))
    return dict(payload.get("result") or payload.get("data") or {})
