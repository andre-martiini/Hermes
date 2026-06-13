"""
Backfill controlado do Gemini File Search para documentos existentes do acervo_global.

Uso:
  python scripts/backfill_file_search_acervo.py --dry-run
  python scripts/backfill_file_search_acervo.py --limit 10

O script e idempotente: ignora documentos que ja possuem acervo_global.file_search.store_name,
baixa o arquivo original, envia ao Gemini File Search e propaga o payload para
indice_artefatos onde acervo_id == <doc_id>.
"""

from __future__ import annotations

import argparse
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import firebase_admin
import requests
from firebase_admin import credentials, firestore
from google import genai
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIALS = ROOT / "firebase_service_account_key.json"

FILE_SEARCH_STORE_MODEL = "models/gemini-embedding-2"
FILE_SEARCH_WAIT_SECONDS = 90
STORE_DOC = ("system", "file_search")

SUPPORTED_MIMES = {
    "application/pdf",
    "application/msword",
    "application/json",
    "application/xml",
    "message/rfc822",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/csv",
    "text/xml",
    "text/plain",
    "text/markdown",
    "text/html",
    "image/jpeg",
    "image/png",
}


def init_firebase(credentials_path: Path):
    if firebase_admin._apps:
        return firestore.client()
    cred = credentials.Certificate(str(credentials_path))
    firebase_admin.initialize_app(cred)
    return firestore.client()


def get_api_key(db) -> str:
    snap = db.collection("system").document("api_keys").get()
    api_key = (snap.to_dict() or {}).get("gemini_api_key") if snap.exists else None
    if not api_key:
        raise RuntimeError("Chave Gemini nao encontrada em system/api_keys.")
    return api_key


def get_or_create_store(db, api_key: str) -> str:
    col, doc_id = STORE_DOC
    doc_ref = db.collection(col).document(doc_id)
    snap = doc_ref.get()
    current_data = snap.to_dict() or {} if snap.exists else {}
    current = current_data.get("store_name")
    if current and current_data.get("embedding_model") == FILE_SEARCH_STORE_MODEL:
        return current
    if current:
        print("[WARN] Store atual nao e multimodal; tentando criar store novo.")

    client = genai.Client(api_key=api_key)
    store_name = None
    store = None
    try:
        store = client.file_search_stores.create(
            config={
                "display_name": "Hermes Acervo Global",
                "embedding_model": FILE_SEARCH_STORE_MODEL,
            }
        )
        embedding_model_status = FILE_SEARCH_STORE_MODEL
    except Exception as exc:
        print(f"[WARN] SDK nao aceitou embedding_model; tentando REST: {exc}")
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/fileSearchStores?key={api_key}",
                json={
                    "display_name": "Hermes Acervo Global",
                    "embedding_model": FILE_SEARCH_STORE_MODEL,
                },
                timeout=30,
            )
            response.raise_for_status()
            store_name = response.json().get("name")
            if not store_name:
                raise RuntimeError(f"REST sem name: {response.text}")
            embedding_model_status = FILE_SEARCH_STORE_MODEL
        except Exception as rest_exc:
            if current:
                print(f"[WARN] REST com embedding_model falhou; mantendo store atual: {rest_exc}")
                return current
            print(f"[WARN] REST com embedding_model falhou; criando store padrao: {rest_exc}")
            store = client.file_search_stores.create(
                config={"display_name": "Hermes Acervo Global"}
            )
            embedding_model_status = "default"
    if not store_name:
        store_name = getattr(store, "name", None)
    if not store_name:
        raise RuntimeError("File Search Store criado sem campo name.")
    doc_ref.set(
        {
            "store_name": store_name,
            "display_name": "Hermes Acervo Global",
            "embedding_model": embedding_model_status,
            "created_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    return store_name


def get_drive_credentials(db):
    snap = db.collection("system").document("google_credentials").get()
    if not snap.exists:
        raise RuntimeError("Credenciais Google nao encontradas em system/google_credentials.")
    data = snap.to_dict() or {}
    expiry_val = data.get("expiry_date") or data.get("expiry")
    parsed_expiry = None
    if expiry_val:
        from datetime import datetime, timezone
        if isinstance(expiry_val, datetime):
            parsed_expiry = expiry_val
        elif isinstance(expiry_val, (int, float)):
            if expiry_val > 1e11:  # milliseconds
                expiry_val = expiry_val / 1000.0
            parsed_expiry = datetime.fromtimestamp(expiry_val, timezone.utc)
        elif isinstance(expiry_val, str):
            try:
                parsed_expiry = datetime.fromisoformat(expiry_val.replace('Z', '+00:00'))
            except ValueError:
                pass

        if parsed_expiry and parsed_expiry.tzinfo is not None:
            parsed_expiry = parsed_expiry.astimezone(timezone.utc).replace(tzinfo=None)

    stored_scopes = data.get("scopes") or ["https://www.googleapis.com/auth/drive"]
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=stored_scopes,
        expiry=parsed_expiry,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        db.collection("system").document("google_credentials").update(
            {
                "token": creds.token,
                "expiry_date": creds.expiry,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
        )
    return creds


def download_file(db, url: str, drive_file_id: str) -> bytes:
    if drive_file_id:
        service = build("drive", "v3", credentials=get_drive_credentials(db))
        return service.files().get_media(fileId=drive_file_id).execute()
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def build_metadata(doc_id: str, data: dict) -> list[dict]:
    metadata = [
        {"key": "nome", "string_value": str(data.get("nome") or "")[:500]},
        {"key": "tipo_mime", "string_value": str(data.get("tipo_mime") or "")},
        {"key": "origem", "string_value": "acervo"},
        {"key": "acervo_id", "string_value": doc_id},
    ]
    clean_tags = [str(tag).strip() for tag in (data.get("tags") or [])[:20] if str(tag).strip()]
    if clean_tags:
        metadata.append({"key": "primary_tag", "string_value": clean_tags[0][:100]})
    for idx, value in enumerate(clean_tags, 1):
        metadata.append({"key": f"tag_{idx:02d}", "string_value": value[:100]})
    return metadata


def upload_file_search(
    api_key: str,
    store_name: str,
    doc_id: str,
    data: dict,
    file_bytes: bytes,
) -> dict:
    client = genai.Client(api_key=api_key)
    nome = str(data.get("nome") or doc_id)
    suffix = "." + (nome.rsplit(".", 1)[-1] if "." in nome else "bin")
    metadata = build_metadata(doc_id, data)
    temp_path: Optional[str] = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        try:
            operation = client.file_search_stores.upload_to_file_search_store(
                file=temp_path,
                file_search_store_name=store_name,
                config={"display_name": nome, "custom_metadata": metadata},
            )
        except Exception as exc:
            print(f"  [WARN] Upload com metadados falhou; tentando sem metadados: {exc}")
            operation = client.file_search_stores.upload_to_file_search_store(
                file=temp_path,
                file_search_store_name=store_name,
                config={"display_name": nome},
            )

        start = time.monotonic()
        while not getattr(operation, "done", False):
            if time.monotonic() - start > FILE_SEARCH_WAIT_SECONDS:
                break
            time.sleep(5)
            operation = client.operations.get(operation)

        response = getattr(operation, "response", None)
        document_name = getattr(response, "name", None)
        return {
            "store_name": store_name,
            "document_name": document_name,
            "operation_name": getattr(operation, "name", None),
            "status": "concluido" if getattr(operation, "done", False) else "pendente",
            "metadata": metadata,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def update_indexes(db, acervo_id: str, payload: dict, dry_run: bool) -> int:
    if dry_run:
        return 0
    count = 0
    for snap in db.collection("indice_artefatos").where("acervo_id", "==", acervo_id).stream():
        snap.reference.update({"file_search": payload})
        count += 1
    return count


def eligible_docs(db, include_pending: bool):
    snapshots = list(db.collection("acervo_global").stream())
    for snap in snapshots:
        data = snap.to_dict() or {}
        existing = data.get("file_search") or {}
        if existing.get("store_name") and not include_pending:
            yield "skip_indexed", snap, data
            continue
        if data.get("tipo_mime") not in SUPPORTED_MIMES:
            yield "skip_mime", snap, data
            continue
        if not data.get("url") and not data.get("drive_file_id"):
            yield "skip_source", snap, data
            continue
        yield "eligible", snap, data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", default=str(DEFAULT_CREDENTIALS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="0 = sem limite")
    parser.add_argument("--include-pending", action="store_true")
    args = parser.parse_args()

    db = init_firebase(Path(args.credentials))
    api_key = get_api_key(db)

    counts = {"eligible": 0, "skip_indexed": 0, "skip_mime": 0, "skip_source": 0, "ok": 0, "error": 0}
    store_name = None if args.dry_run else get_or_create_store(db, api_key)

    for status, snap, data in eligible_docs(db, args.include_pending):
        counts[status] = counts.get(status, 0) + 1
        if status != "eligible":
            continue
        if args.limit and counts["ok"] >= args.limit:
            continue

        label = f"{snap.id} | {data.get('nome', '(sem nome)')}"
        print(f"[{'DRY' if args.dry_run else 'RUN'}] {label}")
        if args.dry_run:
            continue

        try:
            file_bytes = download_file(db, data.get("url", ""), data.get("drive_file_id", ""))
            payload = upload_file_search(api_key, store_name, snap.id, data, file_bytes)
            snap.reference.update({"file_search": payload})
            updated = update_indexes(db, snap.id, payload, dry_run=False)
            print(f"  [OK] status={payload['status']} indice_artefatos_atualizados={updated}")
            counts["ok"] += 1
        except Exception as exc:
            print(f"  [ERRO] {type(exc).__name__}: {exc}")
            counts["error"] += 1

    print("\nResumo:")
    for key in sorted(counts):
        print(f"  {key}: {counts[key]}")


if __name__ == "__main__":
    main()
