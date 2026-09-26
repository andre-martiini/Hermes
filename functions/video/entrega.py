"""Entrega do Hermes Vídeo: Drive do dono, vínculo com a ação e aviso no Telegram.

Autocontido de propósito: roda nas functions E no worker (Cloud Run Job), que não
carrega o `main.py` (mais de 200 KB e todas as dependências das functions). Por
isso a credencial do Drive é lida aqui, espelhando o essencial de
`main.get_google_creds` — mesmo documento (`system/google_credentials`), mesmos
campos, mesma renovação com gravação do token novo. Mudou o formato lá? Mude aqui.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from firebase_admin import firestore


def _expiracao(valor):
    if isinstance(valor, datetime):
        exp = valor
    elif isinstance(valor, (int, float)):
        exp = datetime.fromtimestamp(valor / 1000.0 if valor > 1e11 else valor, timezone.utc)
    elif isinstance(valor, str):
        try:
            exp = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    # google.oauth2 compara com utcnow() ingênuo.
    return exp.astimezone(timezone.utc).replace(tzinfo=None) if exp.tzinfo else exp


def credenciais_do_dono(db):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    ref = db.collection("system").document("google_credentials")
    snap = ref.get()
    if not snap.exists:
        raise RuntimeError("Credenciais Google do dono não encontradas (system/google_credentials).")
    d = snap.to_dict() or {}
    creds = Credentials(token=d.get("token"), refresh_token=d.get("refresh_token"), token_uri=d.get("token_uri"),
                        client_id=d.get("client_id"), client_secret=d.get("client_secret"),
                        scopes=d.get("scopes"), expiry=_expiracao(d.get("expiry_date") or d.get("expiry")))
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            # Mesmo tratamento do main: autorização revogada pede nova autorização ao dono.
            if "invalid_grant" in str(exc):
                ref.set({"auth_status": "reauth_required", "auth_error": "invalid_grant",
                         "updated_at": firestore.SERVER_TIMESTAMP}, merge=True)
            raise
        ref.update({"token": creds.token, "expiry_date": creds.expiry, "updated_at": firestore.SERVER_TIMESTAMP})
    return creds


def drive_do_dono(db):
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=credenciais_do_dono(db), cache_discovery=False)


def anexar_na_acao(db, acao_id: str, *, nome: str, link: str, drive_id: str, nota: str) -> None:
    """Mesmo formato de `tools/anexar_arquivo.py`: item no pool de dados + arquivo e nota no diário."""
    agora = datetime.now(timezone.utc).isoformat()
    item = {"id": str(uuid.uuid4())[:8], "tipo": "arquivo", "valor": link, "nome": nome,
            "data_criacao": agora, "drive_file_id": drive_id}
    arquivo = "FILE::JSON::" + json.dumps({"n": nome, "v": link}, ensure_ascii=False)
    db.collection("tarefas").document(acao_id).update({
        "pool_dados": firestore.ArrayUnion([item]),
        "acompanhamento": firestore.ArrayUnion([{"data": agora, "nota": arquivo}, {"data": agora, "nota": nota}]),
    })


def _chat_id(db) -> str | None:
    try:
        for doc in db.collection("usuarios").where("telegram_chat_id", "!=", None).limit(1).stream():
            valor = (doc.to_dict() or {}).get("telegram_chat_id")
            if str(valor or "").strip():
                return str(valor).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[video.entrega] chat_id via usuarios falhou: {exc}")
    chaves = db.collection("system").document("api_keys").get()
    dados = (chaves.to_dict() or {}) if chaves.exists else {}
    for campo in ("telegram_chat_id", "telegram_allowed_chat_id", "allowed_telegram_chat_id"):
        if str(dados.get(campo) or "").strip():
            return str(dados[campo]).strip()
    geral = db.collection("configuracoes").document("geral").get()
    dados = (geral.to_dict() or {}) if geral.exists else {}
    for campo in ("telegram_chat_id", "telegram_allowed_chat_id"):
        if str(dados.get(campo) or "").strip():
            return str(dados[campo]).strip()
    return None


def avisar_telegram(db, texto: str) -> bool:
    """Aviso ao dono. Falha de aviso nunca derruba a entrega (o vídeo já está no Drive)."""
    import os

    import requests

    try:
        chaves = db.collection("system").document("api_keys").get()
        token = ((chaves.to_dict() or {}) if chaves.exists else {}).get("telegram_bot_token") \
            or os.environ.get("TELEGRAM_BOT_TOKEN")
        chat = _chat_id(db)
        if not token or not chat:
            return False
        resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat, "text": texto}, timeout=10)
        return resp.ok
    except Exception as exc:  # noqa: BLE001
        print(f"[video.entrega] aviso no Telegram falhou: {exc}")
        return False
