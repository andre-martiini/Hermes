"""
Regenera e publica as credenciais OAuth do Google usadas pelo Hermes.

Uso recomendado a partir da raiz do projeto:
    setup_credentials.bat
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

import firebase_admin
from firebase_admin import credentials as firebase_credentials
from firebase_admin import firestore
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/contacts",
]


def _root_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_google_client_config(credentials_path):
    with open(credentials_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    client = data.get("installed") or data.get("web")
    if not client:
        raise RuntimeError("Formato invalido em credentials.json: esperado bloco 'installed' ou 'web'.")
    return client


def _backup_and_remove(path):
    if not os.path.exists(path):
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.revoked-{stamp}.bak"
    shutil.move(path, backup_path)
    print(f"Token antigo movido para: {backup_path}")


def _authenticate(credentials_path, token_path, force):
    creds = None
    if os.path.exists(token_path) and not force:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if not creds.has_scopes(SCOPES):
            print("Token existente nao tem todos os escopos necessarios. Sera feita uma nova autenticacao.")
            _backup_and_remove(token_path)
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token and not force:
        try:
            creds.refresh(Request())
        except RefreshError:
            print("Refresh token expirado ou revogado. Sera feita uma nova autenticacao.")
            _backup_and_remove(token_path)
            creds = None

    if force or not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
        print("")
        print("Abrindo login Google. Autorize a conta que o Hermes deve usar.")
        print("Se o navegador nao abrir, copie a URL exibida no terminal.")
        print("Aguarde esta janela mostrar a mensagem de sucesso antes de fechar.")
        print("")
        previous_relax_scope = os.environ.get("OAUTHLIB_RELAX_TOKEN_SCOPE")
        os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
        try:
            creds = flow.run_local_server(
                port=8080,
                prompt="consent",
                access_type="offline",
                include_granted_scopes="true",
            )
        finally:
            if previous_relax_scope is None:
                os.environ.pop("OAUTHLIB_RELAX_TOKEN_SCOPE", None)
            else:
                os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = previous_relax_scope

    tmp_token_path = f"{token_path}.tmp"
    with open(tmp_token_path, "w", encoding="utf-8") as token_fh:
        token_fh.write(creds.to_json())
    if force:
        _backup_and_remove(token_path)
    os.replace(tmp_token_path, token_path)
    return creds


def _publish_to_firestore(root_dir, creds, google_client):
    key_path = os.path.join(root_dir, "firebase_service_account_key.json")
    if not os.path.exists(key_path):
        raise FileNotFoundError("firebase_service_account_key.json nao encontrado na raiz do projeto.")

    if not firebase_admin._apps:
        firebase_admin.initialize_app(firebase_credentials.Certificate(key_path))

    db = firestore.client()
    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri or google_client.get("token_uri") or "https://oauth2.googleapis.com/token",
        "client_id": google_client.get("client_id"),
        "client_secret": google_client.get("client_secret"),
        "scopes": list(creds.scopes or SCOPES),
        "expiry_date": getattr(creds, "expiry", None),
        "auth_status": "ok",
        "auth_error": firestore.DELETE_FIELD,
        "auth_error_message": firestore.DELETE_FIELD,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    db.collection("system").document("google_credentials").set(payload, merge=True)


def setup_credentials(force=False):
    root_dir = _root_dir()
    credentials_path = os.path.join(root_dir, "credentials.json")
    token_path = os.path.join(root_dir, "token.json")

    if not os.path.exists(credentials_path):
        raise FileNotFoundError("credentials.json nao encontrado na raiz do projeto.")

    google_client = _load_google_client_config(credentials_path)
    creds = _authenticate(credentials_path, token_path, force)

    if not creds.refresh_token:
        raise RuntimeError(
            "O Google nao retornou refresh_token. Rode novamente com --force e confirme a tela de consentimento."
        )

    _publish_to_firestore(root_dir, creds, google_client)
    print("")
    print("Credenciais Google atualizadas com sucesso em token.json e system/google_credentials.")
    print("Agora faca deploy das functions se necessario: firebase deploy --only functions")
    print("")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="forca novo login e substitui token.json")
    args = parser.parse_args()
    try:
        setup_credentials(force=args.force)
    except Exception as exc:
        print(f"ERRO: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
