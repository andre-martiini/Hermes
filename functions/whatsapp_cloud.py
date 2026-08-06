"""
Hermes WhatsApp Cloud API Integration
Webhook receiver (Meta WhatsApp Business Platform) + processador de lote assíncrono.

Fluxo: o usuário encaminha um lote de mensagens (texto, áudio, vídeo, imagem) de
uma conversa do WhatsApp para o número vinculado ao Hermes, preservando a ordem
cronológica, e fecha o lote enviando "#resumo" (opcionalmente com uma instrução,
ex.: "#resumo focar nas datas"). O webhook (`whatsappCloudWebhook`) só valida e
enfileira cada mensagem em `whatsapp_cloud_inbound` — nunca aguarda transcrição ou
Gemini. O trigger assíncrono (`on_whatsapp_cloud_inbound`) reconhece a mensagem de
fechamento, reúne o lote pendente do remetente em ordem cronológica (timestamp
original do WhatsApp, não o de chegada no Firestore), transcreve áudio/vídeo,
descreve imagens, gera um resumo via Gemini e responde no próprio WhatsApp.

Ver guia de configuração em docs/okf/integracoes/whatsapp-cloud-api.md.
"""
import hashlib
import hmac
import os
import re
import time
import unicodedata
from typing import Optional

import requests as _requests
from firebase_admin import firestore, get_app, initialize_app
from firebase_functions import firestore_fn, https_fn, options
from firebase_functions.firestore_fn import Event, DocumentSnapshot

from gemini_cost_controls import GEMINI_BALANCED_MODEL, generate_content_logged
from hermes_core_logic import (
    _get_db,
    _get_api_keys,
    _get_hermes_storage_bucket,
    _transcribe_audio_bytes,
    _MAX_INLINE_MEDIA_BYTES,
)

try:
    get_app()
except ValueError:
    initialize_app()

GRAPH_API_VERSION = "v22.0"
_MAX_MEDIA_BYTES = 20 * 1024 * 1024  # limite de mídia recebida da própria Cloud API
_MAX_BATCH_ITEMS = 150  # teto defensivo por lote; excedente fica pendente para o próximo #resumo
_WHATSAPP_SUMMARY_MODEL = os.environ.get("WHATSAPP_SUMMARY_MODEL", GEMINI_BALANCED_MODEL)
_BATCH_TRIGGER_RE = re.compile(r"^#?\s*resumo\b", re.IGNORECASE)
_MIME_EXTENSIONS = {
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/amr": "amr",
    "video/mp4": "mp4",
    "video/3gpp": "3gp",
}


# ---------------------------------------------------------------------------
# Helpers puros (sem I/O) — parsing e assinatura
# ---------------------------------------------------------------------------

def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_wa_number(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "")


def parse_batch_trigger(text: str) -> tuple[bool, Optional[str]]:
    """Detecta a mensagem de fechamento de lote ("#resumo"/"resumo", com
    instrução opcional depois). Retorna (é_gatilho, instrução_extra|None)."""
    original = (text or "").strip()
    if not original:
        return False, None
    normalized = _strip_accents(original).lower()
    match = _BATCH_TRIGGER_RE.match(normalized)
    if not match:
        return False, None
    extra = original[match.end():].strip(" :,-")
    return True, (extra or None)


def _verify_meta_signature(raw_body: bytes, signature_header: Optional[str], app_secret: str) -> bool:
    if not signature_header or not app_secret:
        return False
    try:
        algo, _, provided = signature_header.partition("=")
        if algo != "sha256" or not provided:
            return False
        expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, provided)
    except Exception:
        return False


def _guess_extension(mime_type: Optional[str], fallback_kind: str) -> str:
    if mime_type:
        base_mime = mime_type.split(";")[0].strip().lower()
        if base_mime in _MIME_EXTENSIONS:
            return _MIME_EXTENSIONS[base_mime]
    return "ogg" if fallback_kind == "audio" else "mp4"


# ---------------------------------------------------------------------------
# Configuração (system/api_keys)
# ---------------------------------------------------------------------------

def _get_whatsapp_cloud_config(db=None) -> dict:
    keys = _get_api_keys(db)
    return {
        "token": keys.get("whatsapp_cloud_token") or os.environ.get("WHATSAPP_CLOUD_TOKEN", ""),
        "phone_number_id": keys.get("whatsapp_cloud_phone_number_id") or os.environ.get("WHATSAPP_CLOUD_PHONE_NUMBER_ID", ""),
        "verify_token": keys.get("whatsapp_cloud_verify_token") or os.environ.get("WHATSAPP_CLOUD_VERIFY_TOKEN", ""),
        "app_secret": keys.get("whatsapp_cloud_app_secret") or os.environ.get("WHATSAPP_CLOUD_APP_SECRET", ""),
        "allowed_number": _normalize_wa_number(
            keys.get("whatsapp_cloud_allowed_number") or os.environ.get("WHATSAPP_CLOUD_ALLOWED_NUMBER", "")
        ),
    }


# ---------------------------------------------------------------------------
# Graph API (Meta) — mídia e envio
# ---------------------------------------------------------------------------

def _get_whatsapp_media_info(token: str, media_id: str) -> dict:
    resp = _requests.get(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _download_whatsapp_media(token: str, media_url: str) -> bytes:
    resp = _requests.get(media_url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.content


def _send_whatsapp_text(token: str, phone_number_id: str, to: str, text: str) -> bool:
    if not token or not phone_number_id or not to:
        return False
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }
    try:
        resp = _requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        if resp.status_code >= 300:
            print(f"[WhatsAppCloud] Falha ao enviar mensagem: {resp.status_code} {resp.text[:300]}")
            return False
        return True
    except Exception as exc:
        print(f"[WhatsAppCloud] Erro ao enviar mensagem: {exc}")
        return False


def _send_whatsapp_text_chunked(token: str, phone_number_id: str, to: str, text: str, chunk_size: int = 4096) -> None:
    text = (text or "").strip()
    if not text:
        return
    for start in range(0, len(text), chunk_size):
        _send_whatsapp_text(token, phone_number_id, to, text[start:start + chunk_size])


# ---------------------------------------------------------------------------
# Armazenamento de mídia recebida (inline em base64 se pequena, senão Storage)
# ---------------------------------------------------------------------------

def _store_whatsapp_media_bytes(file_bytes: bytes, file_name: str, mime_type: Optional[str], sender: str) -> tuple[Optional[str], Optional[str]]:
    import base64

    if len(file_bytes) <= _MAX_INLINE_MEDIA_BYTES:
        return base64.b64encode(file_bytes).decode(), None

    bucket = _get_hermes_storage_bucket()
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", file_name or f"media_{int(time.time())}")
    path = f"whatsapp_cloud_uploads/{sender}/{int(time.time())}_{safe_name}"
    blob = bucket.blob(path)
    blob.upload_from_string(file_bytes, content_type=mime_type or "application/octet-stream")
    return None, path


def _load_whatsapp_media_bytes(media_bytes_b64: Optional[str], storage_path: Optional[str]) -> Optional[bytes]:
    if media_bytes_b64:
        import base64

        return base64.b64decode(media_bytes_b64)
    if storage_path:
        bucket = _get_hermes_storage_bucket()
        return bucket.blob(storage_path).download_as_bytes()
    return None


def _delete_whatsapp_storage_media(storage_path: Optional[str]) -> None:
    if not storage_path:
        return
    try:
        bucket = _get_hermes_storage_bucket()
        bucket.blob(storage_path).delete()
    except Exception as exc:
        print(f"[WhatsAppCloud] Falha ao expurgar {storage_path}: {exc}")


def _extract_audio_track(video_bytes: bytes, extension: str) -> tuple[bytes, str]:
    """Extrai a faixa de áudio de um vídeo via FFmpeg (mesma abordagem de
    `transcreverAudio` em main.py)."""
    import subprocess
    import tempfile
    import imageio_ffmpeg

    suffix = extension if extension.startswith(".") else f".{extension}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as src:
        src.write(video_bytes)
        src_path = src.name
    dst_path = None
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        dst_fd, dst_path = tempfile.mkstemp(suffix=".m4a")
        os.close(dst_fd)
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", src_path, "-vn", "-acodec", "aac", "-b:a", "128k", dst_path],
            check=True,
            capture_output=True,
        )
        with open(dst_path, "rb") as f:
            return f.read(), "m4a"
    finally:
        for path in (src_path, dst_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


def _describe_image(db, image_bytes: bytes, mime_type: Optional[str]) -> str:
    from google import genai
    from google.genai import types

    keys = _get_api_keys(db)
    gemini_key = keys.get("gemini_api_key")
    if not gemini_key:
        return "[Descrição indisponível: Gemini API Key não configurada]"

    client = genai.Client(api_key=gemini_key)
    response = generate_content_logged(
        client,
        model=_WHATSAPP_SUMMARY_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/jpeg"),
            "Descreva objetivamente o conteúdo desta imagem em até 3 frases, em português. "
            "Se houver texto visível relevante (print de tela, documento, mensagem), transcreva-o.",
        ],
        feature="whatsapp_cloud.image_description",
    )
    return (response.text or "").strip() or "[Sem descrição]"


def _summarize_batch(db, transcript: str, extra_instruction: Optional[str]) -> str:
    if not transcript.strip():
        return "O lote não continha conteúdo para resumir."

    keys = _get_api_keys(db)
    gemini_key = keys.get("gemini_api_key")
    if not gemini_key:
        return "[Resumo indisponível: Gemini API Key não configurada]"

    from google import genai

    client = genai.Client(api_key=gemini_key)
    instruction_line = f"\nInstrução adicional do usuário: {extra_instruction}" if extra_instruction else ""
    prompt = (
        "Você recebeu um lote de mensagens de uma conversa do WhatsApp, na ordem cronológica em que "
        "foram enviadas (numeradas [1], [2], ...). Cada item pode ser texto, a transcrição de um áudio/vídeo "
        "ou a descrição de uma imagem. Escreva um resumo objetivo em português do que esse conjunto de "
        "mensagens significa em conjunto — do que se trata, decisões ou pedidos importantes, e qualquer "
        "prazo ou data mencionados. Não invente informação que não esteja no texto."
        f"{instruction_line}\n\n--- MENSAGENS ---\n{transcript}"
    )
    response = generate_content_logged(
        client,
        model=_WHATSAPP_SUMMARY_MODEL,
        contents=prompt,
        feature="whatsapp_cloud.batch_summary",
    )
    return (response.text or "").strip() or "[Resumo vazio]"


def _render_batch_item(db, item: dict) -> tuple[str, str]:
    msg_type = item.get("message_type")
    text = (item.get("text") or "").strip()

    if msg_type == "text":
        return "Texto", (text or "(vazio)")

    if msg_type in ("audio", "video"):
        media_bytes = _load_whatsapp_media_bytes(item.get("media_bytes_b64"), item.get("media_storage_path"))
        label = "Vídeo (áudio)" if msg_type == "video" else "Áudio"
        if not media_bytes:
            return label, "[Falha: mídia indisponível]"
        try:
            extension = _guess_extension(item.get("media_mime_type"), msg_type)
            audio_bytes = media_bytes
            if msg_type == "video":
                audio_bytes, extension = _extract_audio_track(media_bytes, extension)
            transcript = _transcribe_audio_bytes(audio_bytes, extension, db)
        except Exception as exc:
            transcript = f"[Falha ao transcrever: {exc}]"
        if text:
            return label, f"{transcript}\n(legenda: {text})"
        return label, transcript

    if msg_type == "image":
        media_bytes = _load_whatsapp_media_bytes(item.get("media_bytes_b64"), item.get("media_storage_path"))
        if not media_bytes:
            return "Imagem", "[Falha: mídia indisponível]"
        try:
            description = _describe_image(db, media_bytes, item.get("media_mime_type"))
        except Exception as exc:
            description = f"[Falha ao descrever imagem: {exc}]"
        if text:
            return "Imagem", f"{description}\n(legenda: {text})"
        return "Imagem", description

    if msg_type == "document":
        name = item.get("media_filename") or "arquivo"
        mime = item.get("media_mime_type") or "tipo desconhecido"
        return "Documento", f"Anexo recebido: {name} ({mime}). Conteúdo não extraído automaticamente nesta versão."

    return (msg_type or "Mensagem"), (text or "(sem conteúdo)")


def _build_transcript_sections(db, claimed_items: list[dict]) -> tuple[str, list[str]]:
    content_items = [d for d in claimed_items if not d.get("is_batch_trigger")]
    content_items.sort(key=lambda d: (d.get("wa_timestamp") or 0, d.get("wa_message_id") or ""))

    sections: list[str] = []
    storage_paths_to_purge: list[str] = []

    for idx, item in enumerate(content_items, start=1):
        label, body = _render_batch_item(db, item)
        storage_path = item.get("media_storage_path")
        if storage_path:
            storage_paths_to_purge.append(storage_path)
        sections.append(f"[{idx}] {label}\n{body}")

    return "\n\n".join(sections), storage_paths_to_purge


# ---------------------------------------------------------------------------
# Reivindicação transacional do lote pendente
# ---------------------------------------------------------------------------

def _claim_pending_batch(db, sender: str) -> tuple[list[dict], bool]:
    """Busca todas as mensagens não processadas do remetente, em ordem
    cronológica pelo timestamp original do WhatsApp, e marca como processadas
    numa transação (evita reprocessar sob retry do trigger do Firestore).
    Retorna (itens_reivindicados, houve_truncamento)."""
    query = (
        db.collection("whatsapp_cloud_inbound")
        .where("sender", "==", sender)
        .where("processed", "==", False)
        .order_by("wa_timestamp")
        .order_by("__name__")
    )
    candidates = list(query.stream())
    content_candidates = [d for d in candidates if not (d.to_dict() or {}).get("is_batch_trigger")]
    trigger_candidates = [d for d in candidates if (d.to_dict() or {}).get("is_batch_trigger")]

    truncated = len(content_candidates) > _MAX_BATCH_ITEMS
    if truncated:
        content_candidates = content_candidates[:_MAX_BATCH_ITEMS]

    to_claim = content_candidates + trigger_candidates
    if not to_claim:
        return [], False

    transaction = db.transaction()

    @firestore.transactional
    def _claim(tx):
        # Todas as leituras precisam vir antes de qualquer escrita na mesma transação.
        fresh_snapshots = [(doc.reference, doc.reference.get(transaction=tx)) for doc in to_claim]
        claimed_pairs = []
        for ref, fresh in fresh_snapshots:
            if not fresh.exists:
                continue
            fdata = fresh.to_dict() or {}
            if fdata.get("processed"):
                continue
            claimed_pairs.append((ref, fdata))
        for ref, _fdata in claimed_pairs:
            tx.update(ref, {"processed": True, "processed_at": firestore.SERVER_TIMESTAMP})
        return [fdata for _, fdata in claimed_pairs]

    return _claim(transaction), truncated


# ---------------------------------------------------------------------------
# Webhook (Meta) — porteiro rápido, nunca aguarda transcrição/Gemini
# ---------------------------------------------------------------------------

@https_fn.on_request(timeout_sec=20, memory=options.MemoryOption.GB_1)
def whatsappCloudWebhook(req: https_fn.Request) -> https_fn.Response:
    """
    Recebe eventos da WhatsApp Cloud API (Meta): valida a assinatura, filtra
    pelo número autorizado e enfileira cada mensagem em `whatsapp_cloud_inbound`.
    O processamento pesado (transcrição, resumo) acontece no trigger assíncrono
    `on_whatsapp_cloud_inbound`.
    """
    db = _get_db()
    config = _get_whatsapp_cloud_config(db)

    if req.method == "GET":
        mode = req.args.get("hub.mode")
        verify_token = req.args.get("hub.verify_token") or ""
        challenge = req.args.get("hub.challenge", "")
        if mode == "subscribe" and config["verify_token"] and hmac.compare_digest(verify_token, config["verify_token"]):
            return https_fn.Response(challenge, status=200)
        return https_fn.Response("Forbidden", status=403)

    if req.method != "POST":
        return https_fn.Response("OK", status=200)

    raw_body = req.get_data() or b""
    if config.get("app_secret"):
        signature = req.headers.get("X-Hub-Signature-256")
        if not _verify_meta_signature(raw_body, signature, config["app_secret"]):
            print("[WhatsAppCloud] Assinatura inválida — payload descartado.")
            return https_fn.Response("OK", status=200)
    else:
        print("[WhatsAppCloud] whatsapp_cloud_app_secret não configurado — pulando verificação de assinatura.")

    try:
        payload = req.get_json(silent=True) or {}
    except Exception:
        return https_fn.Response("OK", status=200)

    token = config.get("token")
    allowed_number = config.get("allowed_number")

    try:
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                for message in value.get("messages") or []:
                    _handle_inbound_message(db, token, allowed_number, message)
    except Exception as exc:
        print(f"[WhatsAppCloud] Erro ao processar webhook: {exc}")

    return https_fn.Response("OK", status=200)


def _handle_inbound_message(db, token: str, allowed_number: Optional[str], message: dict) -> None:
    sender = _normalize_wa_number(message.get("from"))
    if not sender:
        return
    if allowed_number and sender != allowed_number:
        print(f"[WhatsAppCloud] Remetente não autorizado ignorado: {sender}")
        return

    wa_message_id = message.get("id") or f"{sender}_{message.get('timestamp', int(time.time()))}"
    msg_type = message.get("type", "unknown")

    text_body = ""
    media_id = None
    media_mime = None
    filename = None

    if msg_type == "text":
        text_body = (message.get("text") or {}).get("body", "")
    elif msg_type in ("audio", "video", "image", "document"):
        media_obj = message.get(msg_type) or {}
        media_id = media_obj.get("id")
        media_mime = media_obj.get("mime_type")
        filename = media_obj.get("filename")
        text_body = media_obj.get("caption") or ""
    elif msg_type == "button":
        text_body = (message.get("button") or {}).get("text", "")
    else:
        # Tipos não suportados (localização, contato, sticker, reação...) — ignora silenciosamente.
        return

    is_trigger, trigger_instruction = parse_batch_trigger(text_body)

    media_bytes_b64 = None
    media_storage_path = None
    if media_id and token:
        try:
            media_info = _get_whatsapp_media_info(token, media_id)
            media_url = media_info.get("url")
            if media_url:
                file_bytes = _download_whatsapp_media(token, media_url)
                if len(file_bytes) <= _MAX_MEDIA_BYTES:
                    media_bytes_b64, media_storage_path = _store_whatsapp_media_bytes(
                        file_bytes, filename or f"{msg_type}_{wa_message_id}", media_mime, sender,
                    )
                else:
                    print(f"[WhatsAppCloud] Mídia {wa_message_id} excede {_MAX_MEDIA_BYTES} bytes — ignorada.")
        except Exception as exc:
            print(f"[WhatsAppCloud] Falha ao baixar mídia {media_id}: {exc}")

    db.collection("whatsapp_cloud_inbound").document(wa_message_id).set({
        "sender": sender,
        "wa_message_id": wa_message_id,
        "wa_timestamp": int(message.get("timestamp") or 0),
        "message_type": msg_type,
        "text": text_body,
        "media_id": media_id,
        "media_mime_type": media_mime,
        "media_filename": filename,
        "media_bytes_b64": media_bytes_b64,
        "media_storage_path": media_storage_path,
        "is_batch_trigger": is_trigger,
        "trigger_instruction": trigger_instruction,
        "received_at": firestore.SERVER_TIMESTAMP,
        "processed": False,
    })


# ---------------------------------------------------------------------------
# Trigger assíncrono — fecha e processa o lote
# ---------------------------------------------------------------------------

@firestore_fn.on_document_created(
    document="whatsapp_cloud_inbound/{docId}",
    timeout_sec=540,
    memory=options.MemoryOption.GB_2,
)
def on_whatsapp_cloud_inbound(event: Event[DocumentSnapshot]) -> None:
    """
    Quando a mensagem enfileirada é o gatilho de fechamento de lote ("#resumo"),
    reúne as mensagens pendentes do remetente em ordem cronológica, transcreve
    áudio/vídeo, descreve imagens, resume com Gemini e responde no WhatsApp.
    Mensagens que não fecham lote apenas ficam na fila — nada é processado até
    o "#resumo" chegar.
    """
    snap = event.data
    if not snap or not snap.exists:
        return
    data = snap.to_dict() or {}
    if not data.get("is_batch_trigger"):
        return

    db = _get_db()
    config = _get_whatsapp_cloud_config(db)
    token = config.get("token")
    phone_number_id = config.get("phone_number_id")
    sender = data.get("sender")
    if not sender:
        return

    claimed_items, truncated = _claim_pending_batch(db, sender)
    if not claimed_items:
        # Já reivindicado por uma execução anterior (retry) ou lote vazio.
        return

    content_items = [d for d in claimed_items if not d.get("is_batch_trigger")]
    if not content_items:
        _send_whatsapp_text(
            token, phone_number_id, sender,
            "Não encontrei mensagens pendentes para resumir. Encaminhe o lote e mande #resumo de novo.",
        )
        return

    storage_paths_to_purge: list[str] = []
    try:
        transcript, storage_paths_to_purge = _build_transcript_sections(db, claimed_items)
        summary = _summarize_batch(db, transcript, data.get("trigger_instruction"))

        truncation_note = (
            f"\n\n⚠️ O lote tinha mais de {_MAX_BATCH_ITEMS} itens; processei os {_MAX_BATCH_ITEMS} mais antigos. "
            "Envie #resumo de novo para processar o restante."
            if truncated else ""
        )

        _send_whatsapp_text_chunked(token, phone_number_id, sender, f"📋 Resumo do lote\n\n{summary}{truncation_note}")
        if transcript:
            _send_whatsapp_text_chunked(token, phone_number_id, sender, f"🗒️ Transcrição completa\n\n{transcript}")

        db.collection("whatsapp_cloud_batches").document().set({
            "sender": sender,
            "item_count": len(content_items),
            "transcript": transcript,
            "summary": summary,
            "trigger_instruction": data.get("trigger_instruction"),
            "truncated": truncated,
            "created_at": firestore.SERVER_TIMESTAMP,
        })
    except Exception as exc:
        print(f"[on_whatsapp_cloud_inbound] Erro ao processar lote de {sender}: {exc}")
        import traceback
        traceback.print_exc()
        _send_whatsapp_text(token, phone_number_id, sender, f"⚠️ Erro ao processar o lote: {exc}")
    finally:
        for path in storage_paths_to_purge:
            _delete_whatsapp_storage_media(path)
