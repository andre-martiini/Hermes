import os
from functools import lru_cache

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, firestore

load_dotenv()


@lru_cache(maxsize=1)
def get_db():
    project_id = os.getenv("FIREBASE_PROJECT_ID") or None
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    options = {"projectId": project_id} if project_id else None

    if not firebase_admin._apps:
        if credentials_path:
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred, options)
        else:
            firebase_admin.initialize_app(options=options)

    return firestore.client()


class BrowserAuthError(Exception):
    pass


def verify_browser_id_token(id_token: str) -> str:
    """Valida um Firebase ID Token e confere o UID contra a mesma whitelist
    usada pelo servidor MCP (system/mcp_access.allowed_uids), com fallback em
    HERMES_MCP_ALLOWED_UIDS. Levanta BrowserAuthError se invalido ou nao
    autorizado. Retorna o uid em caso de sucesso."""
    get_db()  # garante que o firebase_admin app foi inicializado
    try:
        decoded = firebase_auth.verify_id_token(id_token)
    except Exception as exc:  # noqa: BLE001
        raise BrowserAuthError(f"Token invalido: {exc}") from exc

    uid = decoded.get("uid")
    if not uid:
        raise BrowserAuthError("Token sem uid.")

    if not _is_uid_allowed(uid):
        raise BrowserAuthError("UID nao autorizado a usar o copiloto de voz do Hermes.")

    return uid


def _is_uid_allowed(uid: str) -> bool:
    allowed: set[str] = set()

    env_uids = os.getenv("HERMES_MCP_ALLOWED_UIDS", "").strip()
    if env_uids:
        allowed.update(u.strip() for u in env_uids.split(",") if u.strip())

    try:
        doc = get_db().collection("system").document("mcp_access").get()
        if doc.exists:
            allowed.update(doc.to_dict().get("allowed_uids") or [])
    except Exception:
        pass

    return uid in allowed
