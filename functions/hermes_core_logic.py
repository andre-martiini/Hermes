"""
Hermes Core Logic — Telegram Integration (Low-Latency Refactor)

Pipeline:
  telegramWebhook  → auth + idempotência + enfileira em telegram_inbound
  on_telegram_inbound → roteamento 2 estágios + slot-filling + execução de tool
"""
import json
import os
import re
import tempfile
import threading
import time
import unicodedata
import wave
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

import requests as _requests
from firebase_admin import firestore, get_app, initialize_app, storage
from firebase_functions import firestore_fn, https_fn, options
from firebase_functions.firestore_fn import Event, DocumentSnapshot

try:
    get_app()
except ValueError:
    initialize_app()

_MAX_FILE_BYTES = 20 * 1024 * 1024
_MAX_INLINE_MEDIA_BYTES = 700 * 1024
_TTS_MODEL_ID = "gemini-3.1-flash-tts-preview"
_TEXT_MODEL_ID = "gemini-3-flash-preview"
_GENERAL_RESPONSE_MODEL = "gemini-3-flash-preview"
_DEFAULT_MALE_VOICE = "Charon"
_MAX_TTS_TRANSCRIPT_CHARS = 1500


# ---------------------------------------------------------------------------
# Infra helpers
# ---------------------------------------------------------------------------

def _get_db():
    return firestore.client()


def _get_api_keys(db=None):
    db = db or _get_db()
    doc = db.collection("system").document("api_keys").get()
    return doc.to_dict() or {} if doc.exists else {}


def _get_telegram_token(db=None) -> str:
    keys = _get_api_keys(db)
    token = keys.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("telegram_bot_token não configurado em system/api_keys.")
    return token


def _get_allowed_chat_id() -> Optional[str]:
    return os.environ.get("ALLOWED_TELEGRAM_CHAT_ID")


# ---------------------------------------------------------------------------
# Telegram API helpers (kept inline for backward-compat with audio/TTS path)
# ---------------------------------------------------------------------------

def _send_telegram_message(token: str, chat_id: str | int, text: str, parse_mode: str = "HTML") -> Optional[int]:
    if len(text) > 4096:
        text = text[:4090] + "\n..."
    resp = _requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
        timeout=30,
    )
    if resp.ok:
        return resp.json().get("result", {}).get("message_id")
    print(f"[Telegram] sendMessage failed: {resp.status_code} {resp.text[:300]}")
    return None


def _edit_telegram_message(token: str, chat_id: str | int, message_id: int, text: str, parse_mode: str = "HTML") -> bool:
    if len(text) > 4096:
        text = text[:4090] + "\n..."
    resp = _requests.post(
        f"https://api.telegram.org/bot{token}/editMessageText",
        json={"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode},
        timeout=30,
    )
    return resp.ok


def _send_telegram_chat_action(token: str, chat_id: str | int, action: str):
    try:
        _requests.post(
            f"https://api.telegram.org/bot{token}/sendChatAction",
            json={"chat_id": chat_id, "action": action},
            timeout=5,
        )
    except Exception:
        pass


def _send_telegram_typing(token: str, chat_id: str | int):
    _send_telegram_chat_action(token, chat_id, "typing")


@contextmanager
def _telegram_action_heartbeat(token: str, chat_id: str | int, action: str, interval_seconds: int = 4):
    stop_event = threading.Event()

    def _loop():
        while not stop_event.is_set():
            _send_telegram_chat_action(token, chat_id, action)
            stop_event.wait(interval_seconds)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=1)


def _send_telegram_voice(token: str, chat_id: str | int, audio_bytes: bytes, filename: str, mime_type: str, caption: str = "") -> bool:
    files = {"voice": (filename, audio_bytes, mime_type)}
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    resp = _requests.post(
        f"https://api.telegram.org/bot{token}/sendVoice",
        data=data, files=files, timeout=120,
    )
    if not resp.ok:
        print(f"[Telegram] sendVoice failed: {resp.status_code} {resp.text[:500]}")
    return bool(resp.ok)


def _send_telegram_document(token: str, chat_id: str | int, file_bytes: bytes, filename: str, mime_type: str, caption: str = "") -> bool:
    files = {"document": (filename, file_bytes, mime_type)}
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    resp = _requests.post(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data=data, files=files, timeout=120,
    )
    if not resp.ok:
        print(f"[Telegram] sendDocument failed: {resp.status_code} {resp.text[:500]}")
    return bool(resp.ok)


def _get_telegram_file(token: str, file_id: str) -> dict:
    resp = _requests.get(
        f"https://api.telegram.org/bot{token}/getFile",
        params={"file_id": file_id}, timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("result", {})


def _download_telegram_file(token: str, file_path: str) -> bytes:
    resp = _requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}", timeout=60)
    resp.raise_for_status()
    return resp.content


# ---------------------------------------------------------------------------
# Media storage
# ---------------------------------------------------------------------------

def _store_telegram_media(file_bytes: bytes, file_name: str, mime_type: str, chat_id: str) -> tuple[str | None, str | None]:
    import base64
    if len(file_bytes) <= _MAX_INLINE_MEDIA_BYTES:
        return base64.b64encode(file_bytes).decode(), None
    safe_name = os.path.basename(file_name or f"upload_{int(time.time())}")
    bucket = storage.bucket()
    path = f"telegram_uploads/{chat_id}/{int(time.time())}_{safe_name}"
    blob = bucket.blob(path)
    blob.upload_from_string(file_bytes, content_type=mime_type)
    return None, path


def _load_telegram_media_bytes(media_bytes_b64: str | None, storage_path: str | None) -> bytes | None:
    if media_bytes_b64:
        import base64
        return base64.b64decode(media_bytes_b64)
    if storage_path:
        bucket = storage.bucket()
        blob = bucket.blob(storage_path)
        return blob.download_as_bytes()
    return None


def _upload_to_storage(file_bytes: bytes, file_name: str, mime_type: str, chat_id: str) -> str:
    bucket = storage.bucket()
    path = f"telegram_uploads/{chat_id}/{file_name}"
    blob = bucket.blob(path)
    blob.upload_from_string(file_bytes, content_type=mime_type)
    blob.make_public()
    return blob.public_url


# ---------------------------------------------------------------------------
# Audio transcription
# ---------------------------------------------------------------------------

def _transcribe_audio_bytes(audio_bytes: bytes, extension: str, db) -> str:
    keys = _get_api_keys(db)
    groq_key = keys.get("groq_api_key")
    if not groq_key:
        return "[Transcrição indisponível: chave Groq não configurada]"

    from groq import Groq
    client = Groq(api_key=groq_key)
    suffix = extension if extension.startswith(".") else f".{extension}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(tmp_path), f),
                model="whisper-large-v3-turbo",
                response_format="json",
                language="pt",
                temperature=0.0,
            )
        return transcription.text or ""
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# TTS helpers
# ---------------------------------------------------------------------------

def _normalize_for_matching(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _extract_response_mode(text: str, session: dict) -> tuple[str, str]:
    raw_text = (text or "").strip()
    if not raw_text:
        return session.get("response_mode", "texto"), raw_text

    lowered = _normalize_for_matching(raw_text)
    explicit_audio_markers = ("/audio", "#audio", "[audio]", "mensagem de voz", "em voz", "por voz")
    audio_keywords = ("audio", "voz")
    request_verbs = ("responda", "resposta", "mande", "manda", "envie", "quero")
    wants_audio = any(marker in lowered for marker in explicit_audio_markers)
    if not wants_audio:
        wants_audio = any(v in lowered for v in request_verbs) and any(k in lowered for k in audio_keywords)

    if wants_audio:
        cleaned = raw_text
        for pat in [
            r"^/audio\b", r"#audio|\[audio\]",
            r"(me\s+)?responda\s+(em|por|para|pro?)\s+(o\s+)?[aá]udio",
            r"resposta\s+(em|por|para|pro?)\s+(o\s+)?[aá]udio",
            r"envie\s+(em|por|para|pro?)\s+(o\s+)?[aá]udio",
            r"(me\s+)?mande\s+(em|por|para|pro?)\s+(o\s+)?[aá]udio",
            r"quero\s+(em|por|para|pro?)\s+(o\s+)?[aá]udio",
            r"mensagem de voz", r"\b(em|por)\s+voz\b",
        ]:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
        return "audio", cleaned.strip(" ,.-")

    explicit_text_markers = ("/texto", "#texto", "[texto]")
    if any(marker in lowered for marker in explicit_text_markers):
        cleaned = re.sub(r"^/texto\b|#texto|\[texto\]", "", raw_text, flags=re.IGNORECASE).strip()
        return "texto", cleaned

    return session.get("response_mode", "texto"), raw_text


def _extract_voice_profile(text: str, default_voice: str = "masculina") -> tuple[str, str]:
    raw_text = (text or "").strip()
    if not raw_text:
        return default_voice, raw_text

    lowered = _normalize_for_matching(raw_text)
    masculine_markers = ("#voz:masculina", "[voz:masculina]", "/voz masculina", "voz masculina", "na voz masculina", "com voz masculina")
    if any(marker in lowered for marker in masculine_markers):
        cleaned = re.sub(r"#voz:masculina|\[voz:masculina\]|/voz masculina", "", raw_text, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\b(na|com)?\s*voz masculina\b", "", cleaned, flags=re.IGNORECASE).strip()
        return "masculina", cleaned
    return default_voice, raw_text


def _build_tts_director_instruction(voice_profile: str) -> str:
    return (
        "Voce e o diretor de TTS do Hermes. "
        "Recebera uma resposta factual pronta e deve apenas converte-la em um roteiro curto para fala natural. "
        "Nao adicione fatos novos. Nao inclua links, nomes tecnicos longos nem listas densas. "
        "Nao use tags, colchetes nem anotacoes de palco. Entregue apenas o texto a ser falado. "
        "Mantenha tom de assistente operacional, conversa um a um, sem soar como narrador. "
        f"Perfil de voz desejado: {voice_profile}. Responda apenas com o roteiro final."
    )


def _run_gemini_text(gemini_key: str, system_instruction: str, user_prompt: str, model_id: str = _TEXT_MODEL_ID) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=gemini_key)
    response = client.models.generate_content(
        model=model_id,
        contents=user_prompt,
        config=types.GenerateContentConfig(system_instruction=system_instruction),
    )
    return (response.text or "").strip()


def _run_gemini_tts(gemini_key: str, script_text: str, voice_profile: str) -> tuple[bytes, str]:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=gemini_key)
    style_prompt = (
        "### DIRECTOR'S NOTES\n"
        "Style: concise operational assistant, one-to-one, practical and calm.\n"
        "Pacing: natural conversational pace.\n"
        "Tone: professional, direct, grounded, helpful and discreet.\n\n"
        "### SCRIPT\n"
        f"\"{script_text[:_MAX_TTS_TRANSCRIPT_CHARS]}\""
    )
    response = client.models.generate_content(
        model=_TTS_MODEL_ID,
        contents=style_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=_DEFAULT_MALE_VOICE)
                )
            ),
        ),
    )
    for candidate in (response.candidates or []):
        for part in (candidate.content.parts or []):
            inline_data = getattr(part, "inline_data", None)
            if inline_data and getattr(inline_data, "data", None):
                return inline_data.data, getattr(inline_data, "mime_type", "audio/L16;rate=24000")
    raise RuntimeError("Gemini TTS não retornou áudio.")


def _transcode_audio_for_telegram_voice(audio_bytes: bytes, mime_type: str) -> tuple[bytes, str, str] | tuple[None, None, None]:
    import shutil
    import subprocess

    sample_rate = 24000
    rate_match = re.search(r"rate=(\d+)", (mime_type or "").lower())
    if rate_match:
        sample_rate = int(rate_match.group(1))

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return None, None, None

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "input.wav")
        ogg_path = os.path.join(tmpdir, "output.ogg")
        with wave.open(wav_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_bytes)
        cmd = [ffmpeg_bin, "-y", "-i", wav_path, "-c:a", "libopus", "-b:a", "32k", ogg_path]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0 or not os.path.exists(ogg_path):
            print(f"[TTS] ffmpeg transcode failed: {proc.stderr[:400]}")
            return None, None, None
        with open(ogg_path, "rb") as f:
            return f.read(), "audio/ogg", "hermes_voice.ogg"


def _wrap_pcm_audio_as_wav(audio_bytes: bytes, mime_type: str) -> tuple[bytes, str, str]:
    sample_rate = 24000
    rate_match = re.search(r"rate=(\d+)", (mime_type or "").lower())
    if rate_match:
        sample_rate = int(rate_match.group(1))
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_bytes)
    return wav_buffer.getvalue(), "audio/wav", "hermes_audio.wav"


def _send_tts_failure_notice(token: str, chat_id: str | int):
    _send_telegram_message(token, chat_id, "⚠️ Falha técnica ao gerar o áudio. Repita a solicitação ou peça resposta em texto.")


def _deliver_response(token: str, chat_id: str | int, response_text: str, response_mode: str,
                       voice_profile: str, gemini_key: str, message_id_to_edit: Optional[int] = None):
    """Entrega a resposta final ao usuário — texto ou áudio."""
    if response_mode == "audio":
        try:
            with _telegram_action_heartbeat(token, chat_id, "record_voice"):
                tts_script = _run_gemini_text(
                    gemini_key=gemini_key,
                    system_instruction=_build_tts_director_instruction(voice_profile),
                    user_prompt=response_text,
                )
                audio_bytes, audio_mime = _run_gemini_tts(
                    gemini_key=gemini_key,
                    script_text=tts_script or response_text,
                    voice_profile=voice_profile,
                )
                tg_audio_bytes, tg_audio_mime, tg_audio_name = _transcode_audio_for_telegram_voice(audio_bytes, audio_mime)
                if tg_audio_bytes:
                    if not _send_telegram_voice(token, chat_id, tg_audio_bytes, tg_audio_name, tg_audio_mime):
                        raise RuntimeError("Falha ao enviar voice note.")
                else:
                    wav_bytes, wav_mime, wav_name = _wrap_pcm_audio_as_wav(audio_bytes, audio_mime)
                    if not _send_telegram_document(token, chat_id, wav_bytes, wav_name, wav_mime, caption="Resposta em áudio"):
                        raise RuntimeError("Falha ao enviar arquivo de áudio.")
        except Exception as tts_err:
            print(f"[Core] TTS error: {tts_err}")
            _send_tts_failure_notice(token, chat_id)
    else:
        if message_id_to_edit:
            if not _edit_telegram_message(token, chat_id, message_id_to_edit, response_text):
                _send_telegram_message(token, chat_id, response_text)
        else:
            _send_telegram_message(token, chat_id, response_text)


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------

def _handle_command(text: str, session: dict, db, chat_id: str, token: str) -> bool:
    """
    Trata comandos /start /contexto /sair /status.
    Retorna True se o comando foi tratado (não deve seguir para o pipeline).
    """
    text = (text or "").strip()
    m = re.match(r"^/contexto\s+(.+)$", text, re.IGNORECASE)
    if m:
        ctx = m.group(1).strip()
        from core.session import clear_session
        clear_session(db, chat_id)
        _send_telegram_message(token, chat_id, f"Contexto ativo: <b>{ctx}</b>. Histórico reiniciado.")
        return True

    if re.match(r"^/sair$", text, re.IGNORECASE):
        from core.session import clear_session
        clear_session(db, chat_id)
        _send_telegram_message(token, chat_id, "Sessão encerrada. Voltando ao modo geral.")
        return True

    if re.match(r"^/start$", text, re.IGNORECASE):
        _send_telegram_message(token, chat_id, (
            "👋 Olá! Sou o <b>Hermes Copiloto</b>.\n\n"
            "Comandos:\n"
            "• <code>/contexto [nome]</code> — foca em uma área\n"
            "• <code>/sair</code> — encerra a sessão atual\n"
            "• <code>/status</code> — exibe estado da sessão\n\n"
            "Envie texto, áudio ou arquivos (máx. 20 MB)."
        ))
        return True

    if re.match(r"^/status$", text, re.IGNORECASE):
        mode = session.get("mode", "geral") if session else "geral"
        tool = session.get("tool_name", "") if session else ""
        slots = session.get("slots", {}) if session else {}
        msg = f"<b>Modo:</b> {mode}"
        if tool:
            msg += f"\n<b>Ferramenta ativa:</b> {tool}"
            msg += f"\n<b>Parâmetros coletados:</b> {', '.join(slots.keys()) or 'nenhum'}"
        _send_telegram_message(token, chat_id, msg)
        return True

    return False


# ---------------------------------------------------------------------------
# Tool executors
# ---------------------------------------------------------------------------

def _execute_tool(tool_name: str, slots: dict, db) -> str:
    """Executa a ferramenta identificada com os slots preenchidos."""
    try:
        if tool_name == "consultar_historico_acoes":
            from tools.busca_grafo import buscar_tarefas
            res = buscar_tarefas(
                slots.get("query", ""),
                area_tematica=slots.get("area_tematica"),
                match_mode="all",
                data_limite_inicio=slots.get("data_limite_inicio"),
                data_limite_fim=slots.get("data_limite_fim"),
                status=slots.get("status"),
            )
            if not res.get("resultados"):
                res = buscar_tarefas(slots.get("query", ""), area_tematica=slots.get("area_tematica"), match_mode="any",
                                     data_limite_inicio=slots.get("data_limite_inicio"),
                                     data_limite_fim=slots.get("data_limite_fim"), status=slots.get("status"))
            if res.get("erro"):
                return f"⚠️ {res['erro']}"
            resultados = res.get("resultados", [])
            if not resultados:
                return f"Nenhuma ação encontrada para <b>{slots.get('query')}</b>."
            lines = [f"<b>Ações encontradas ({len(resultados)}):</b>"]
            for r in resultados:
                lines.append(f"• <code>{r['id']}</code> | {r['titulo']} | {r['status']} | Prazo: {r.get('data_limite', 'N/A')}")
            return "\n".join(lines)

        elif tool_name == "buscar_arquivos_acervo":
            from tools.busca_acervo import buscar_acervo
            res = buscar_acervo(slots.get("query", ""))
            if res.get("erro"):
                return f"⚠️ {res['erro']}"
            resultados = res.get("resultados", [])
            if not resultados:
                return "Nenhum documento encontrado."
            return "\n\n".join(
                f"<b>{r['titulo']}</b> | {r['fonte']}\n{r['trecho']}" for r in resultados
            )

        elif tool_name == "pesquisar_internet":
            tavily_key = _get_api_keys(db).get("tavily_api_key")
            if not tavily_key:
                return "⚠️ Tavily não configurado."
            resp = _requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": slots.get("query", ""),
                      "search_depth": "advanced", "include_answer": True,
                      "include_raw_content": False, "max_results": 5},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            parts = []
            if data.get("answer"):
                parts.append(f"<b>Resposta:</b> {data['answer']}\n")
            for r in data.get("results", []):
                parts.append(f"<b>{r.get('title', '')}</b>\n{r.get('content', '')}")
            return "\n\n".join(parts) or "Sem resultados."

        elif tool_name == "ler_pagina_web":
            url = slots.get("url", "")
            resp = _requests.get(f"https://r.jina.ai/{url}", headers={"Accept": "text/markdown"}, timeout=25)
            if resp.status_code in (401, 403, 429):
                return "⚠️ Acesso bloqueado pela página de destino."
            resp.raise_for_status()
            content = resp.text.strip()
            return content[:12000] + "\n[truncado]" if len(content) > 12000 else content

        elif tool_name == "consultar_agenda":
            from main import get_calendar_service, get_target_calendar_id
            import hermes_calendar_tools as hc_tools
            c_service = get_calendar_service()
            c_id = get_target_calendar_id(db)
            if not c_service or not c_id:
                return "Google Calendar não configurado."
            events = hc_tools.consultar_eventos(c_service, c_id, slots.get("data_inicio", ""), slots.get("data_fim", ""))
            return hc_tools.formatar_eventos_para_llm(events)

        elif tool_name == "encontrar_slot_livre":
            from main import get_calendar_service, get_target_calendar_id
            import hermes_calendar_tools as hc_tools
            c_service = get_calendar_service()
            c_id = get_target_calendar_id(db)
            if not c_service or not c_id:
                return "Google Calendar não configurado."
            slot = hc_tools.encontrar_proximo_slot(c_service, c_id, slots.get("a_partir_de", ""), int(slots.get("duracao_min", 30)))
            if slot:
                return json.dumps(slot, ensure_ascii=False)
            return "Nenhum slot livre encontrado no período."

        elif tool_name == "criar_acao_no_sistema":
            import uuid as _uuid
            now_iso = datetime.now(timezone.utc).isoformat()
            task_id = str(_uuid.uuid4())[:20]
            data_limite = slots.get("data_limite") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            plano_convertido = [
                {"id": str(_uuid.uuid4())[:8], "text": str(p), "completed": False}
                for p in (slots.get("plano_acao") or []) if str(p).strip()
            ]
            horario_inicio = slots.get("horario_inicio")
            horario_fim = slots.get("horario_fim")
            try:
                from main import get_calendar_service, get_target_calendar_id
                import hermes_calendar_tools as hc_tools
                c_service = get_calendar_service()
                c_id = get_target_calendar_id(db)
                if c_service and c_id and horario_inicio and horario_fim:
                    hc_tools.reagendar_acoes_hermes(db, c_service, c_id, data_limite, horario_inicio, horario_fim)
            except Exception as e:
                print(f"[Core] Erro ao reagendar: {e}")

            doc = {
                "id": task_id,
                "titulo": slots.get("titulo", "").strip(),
                "descricao": slots.get("descricao", ""),
                "area_tematica": slots.get("area_tematica", "GERAL"),
                "data_limite": data_limite,
                "horario_inicio": horario_inicio,
                "horario_fim": horario_fim,
                "tipo_acao": slots.get("tipo_acao", "fast"),
                "tags": slots.get("tags", []),
                "notas": slots.get("notas", ""),
                "plano_acao": plano_convertido,
                "status": "em andamento",
                "criado_em": now_iso,
                "data_criacao": now_iso,
                "data_atualizacao": now_iso,
                "origem_ingestao": "telegram",
                "acompanhamento": [],
                "sync_status": "new",
            }
            db.collection("tarefas").document(task_id).set(doc)
            return f"✅ Ação criada com sucesso!\n<b>ID:</b> <code>{task_id}</code>\n<b>Título:</b> {doc['titulo']}"

        elif tool_name == "salvar_memoria_global":
            import uuid as _uuid
            node_id = str(_uuid.uuid4())[:16]
            db.collection("knowledge_nodes").document(node_id).set({
                "id": node_id,
                "fato": slots.get("fato", ""),
                "categoria": slots.get("categoria", ""),
                "data_criacao": datetime.now(timezone.utc).isoformat(),
                "origem": "telegram",
            })
            return f"✅ Memorizado: <i>{slots.get('fato', '')}</i>"

        elif tool_name == "registrar_correcao_procedimento":
            import uuid as _uuid
            cid = str(_uuid.uuid4())[:12]
            db.collection("correcoes_pendentes").document(cid).set({
                "id": cid,
                "area_tematica": slots.get("area_tematica", ""),
                "titulo_procedimento": slots.get("titulo_procedimento", ""),
                "correcao_descrita": slots.get("correcao_descrita", ""),
                "novo_conteudo_proposto": slots.get("novo_conteudo_proposto", ""),
                "justificativa_usuario": slots.get("justificativa", ""),
                "status": "pendente",
                "data_criacao": firestore.SERVER_TIMESTAMP,
                "origem": "telegram",
            })
            return f"✅ Correção registrada (ID: <code>{cid}</code>)."

        elif tool_name == "buscar_e_analisar_email":
            from tools.buscar_e_analisar_email import buscar_e_analisar_email as _fn
            return _fn(query=slots.get("query", ""), max_results=min(int(slots.get("max_results", 5)), 5))

        return f"⚠️ Ferramenta '{tool_name}' não reconhecida."

    except Exception as e:
        print(f"[Core] execute_tool error ({tool_name}): {e}")
        return f"⚠️ Erro ao executar <b>{tool_name}</b>: {e}"


def _build_confirmation_draft(tool_name: str, slots: dict) -> str:
    """Gera mensagem de confirmação para ferramentas que precisam de aprovação."""
    if tool_name == "criar_acao_no_sistema":
        lines = ["<b>📋 Draft da Ação — confirme para criar:</b>\n"]
        lines.append(f"<b>Título:</b> {slots.get('titulo', '(não informado)')}")
        lines.append(f"<b>Área:</b> {slots.get('area_tematica', '(não informado)')}")
        lines.append(f"<b>Prazo:</b> {slots.get('data_limite', '(não informado)')}")
        if slots.get("descricao"):
            lines.append(f"<b>Descrição:</b> {slots['descricao']}")
        if slots.get("tipo_acao"):
            lines.append(f"<b>Tipo:</b> {slots['tipo_acao']}")
        if slots.get("horario_inicio"):
            lines.append(f"<b>Horário:</b> {slots['horario_inicio']} → {slots.get('horario_fim', '?')}")
        if slots.get("plano_acao"):
            lines.append("<b>Plano:</b>")
            for step in slots["plano_acao"]:
                lines.append(f"  • {step}")
        lines.append("\nResponda <b>sim</b> para confirmar ou <b>não</b> para cancelar.")
        return "\n".join(lines)
    return "Confirme a operação respondendo <b>sim</b> ou <b>não</b>."


# ---------------------------------------------------------------------------
# General LLM response (conversational, no tool)
# ---------------------------------------------------------------------------

def _build_general_system_instruction(db) -> str:
    from datetime import datetime as _dt
    today = _dt.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        core_doc = db.collection("system").document("copilot_core").get()
        copilot_core = (core_doc.to_dict() or {}).get("content", "") if core_doc.exists else ""
    except Exception:
        copilot_core = ""
    try:
        soul_doc = db.collection("system").document("copilot_soul").get()
        copilot_soul = (soul_doc.to_dict() or {}).get("content", "") if soul_doc.exists else ""
    except Exception:
        copilot_soul = ""

    mem_text = ""
    try:
        memory_docs = (
            db.collection("knowledge_nodes")
            .order_by("data_criacao", direction=firestore.Query.DESCENDING)
            .limit(4)
            .stream()
        )
        mem_lines = []
        for m_doc in memory_docs:
            m = m_doc.to_dict() or {}
            fato = m.get("fato", "")
            cat = m.get("categoria", "")
            if fato:
                mem_lines.append(f"- [{cat}] {fato}")
        if mem_lines:
            mem_text = "\n\n## MEMÓRIA GLOBAL ATIVA\n" + "\n".join(mem_lines)
    except Exception:
        pass

    return (
        f"Você é o Copiloto Hermes, estrategista sênior de processos. Hoje é {today}.\n\n"
        f"## CORE\n{copilot_core}\n\n## PERSONALIDADE\n{copilot_soul}\n\n"
        "## CANAL: TELEGRAM\n"
        "Use APENAS tags HTML do Telegram: <b>, <i>, <code>, <pre>. "
        "PROIBIDO Markdown (asteriscos, #, backticks). "
        "Listas: use • ou - como prefixo. Respostas concisas (máx 4096 chars).\n\n"
        "## REGRAS\n"
        "1. JAMAIS expanda siglas arbitrariamente.\n"
        "2. Se qualquer ferramenta retornar campo 'erro', reproduza o erro literal.\n"
        "3. Links de tarefas: use o formato task:{ID}.\n"
        f"{mem_text}"
    )


def _run_general_response(db, gemini_key: str, message: str, history: list) -> str:
    """Resposta conversacional sem tool — usa histórico mínimo (últimas 5 trocas)."""
    from google import genai
    from google.genai import types

    system_instruction = _build_general_system_instruction(db)
    client = genai.Client(api_key=gemini_key)

    # Reconstrói histórico no formato Gemini
    gemini_history = []
    for h in history:
        role = h.get("role")
        text = h.get("text", "")
        if role and text:
            gemini_history.append(types.Content(role=role, parts=[types.Part(text=text)]))

    chat = client.chats.create(
        model=_GENERAL_RESPONSE_MODEL,
        config=types.GenerateContentConfig(system_instruction=system_instruction),
        history=gemini_history,
    )
    response = chat.send_message(message)
    text_parts = []
    if response.candidates:
        for part in (response.candidates[0].content.parts or []):
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
    return "\n".join(text_parts).strip() or "Não consegui gerar uma resposta. Tente novamente."


# ---------------------------------------------------------------------------
# Main processing pipeline
# ---------------------------------------------------------------------------

def _process_telegram_message(db, data: dict):
    """Pipeline principal de processamento de uma mensagem Telegram."""
    from core import tracing, router as core_router
    from core.session import (
        get_session, save_slot_session, save_general_session,
        clear_session, trim_history,
    )
    from tools import registry

    chat_id = str(data.get("chat_id", ""))
    raw_text = (data.get("text") or "").strip()
    file_info = data.get("file_info")
    audio_info = data.get("audio_info")
    media_bytes_b64 = data.get("media_bytes_b64")
    media_storage_path = data.get("media_storage_path")
    trace_id = data.get("trace_id", tracing.generate_trace_id())
    tracing.set_trace_id(trace_id)

    if not chat_id:
        return

    keys = _get_api_keys(db)
    gemini_key = keys.get("gemini_api_key")
    token = keys.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not gemini_key or not token:
        _send_telegram_message(token or "", chat_id, "⚠️ Configuração incompleta. Contate o administrador.")
        return

    session = get_session(db, chat_id) or {}
    response_mode, text = _extract_response_mode(raw_text, session)
    voice_profile, text = _extract_voice_profile(text, "masculina")

    tracing.log("INFO", "message_received", chat_id=chat_id, mode=response_mode, has_audio=bool(audio_info))

    # --- Resolve conteúdo de áudio/arquivo ---
    file_context_text = ""
    if audio_info and (media_bytes_b64 or media_storage_path):
        audio_bytes = _load_telegram_media_bytes(media_bytes_b64, media_storage_path)
        if audio_bytes:
            mime = audio_info.get("mime_type", "audio/ogg")
            raw_ext = mime.split("/")[-1]
            ext = "ogg" if raw_ext in ("ogg", "oga") else raw_ext
            _send_telegram_typing(token, chat_id)
            try:
                transcription = _transcribe_audio_bytes(audio_bytes, ext, db)
                if transcription:
                    transcribed_mode, cleaned = _extract_response_mode(transcription, session)
                    if transcribed_mode == "audio":
                        response_mode = "audio"
                        transcription = cleaned
                    voice_profile, transcription = _extract_voice_profile(transcription, voice_profile)
                    file_context_text = transcription
                    if not text:
                        text = transcription
                    tracing.log("INFO", "audio_transcribed", chars=len(transcription))
            except Exception as te:
                tracing.log("ERROR", "transcription_failed", error=str(te))

    elif file_info and (media_bytes_b64 or media_storage_path):
        import uuid as _uuid
        file_bytes = _load_telegram_media_bytes(media_bytes_b64, media_storage_path)
        if file_bytes:
            fname = file_info.get("file_name") or f"upload_{_uuid.uuid4().hex[:8]}"
            mime = file_info.get("mime_type", "application/octet-stream")
            try:
                pub_url = _upload_to_storage(file_bytes, fname, mime, chat_id)
                file_context_text = (
                    f"[Arquivo recebido]: {fname} ({mime})\nURL: {pub_url}\n"
                    "Analise este arquivo e relacione ao contexto atual."
                )
            except Exception as ue:
                file_context_text = f"[Arquivo recebido: {fname}] (falha no upload: {ue})"
            if not text:
                text = file_context_text

    if not text:
        return

    # --- Comandos ---
    if text.startswith("/"):
        if _handle_command(text, session, db, chat_id, token):
            return

    # --- Sessão de slot-filling ativa? ---
    active_tool = session.get("tool_name") if session.get("mode") == "slot_filling" else None

    if active_tool and session.get("awaiting_confirmation"):
        # Usuário está respondendo ao draft de confirmação
        if core_router.is_confirmation(text):
            provisional_msg_id = _send_telegram_message(token, chat_id, "⏳ Executando...")
            result = _execute_tool(active_tool, session.get("slots", {}), db)
            clear_session(db, chat_id)
            tracing.log("INFO", "tool_executed", tool=active_tool)
            _deliver_response(token, chat_id, result, response_mode, voice_profile, gemini_key,
                              message_id_to_edit=provisional_msg_id)
        elif core_router.is_cancellation(text):
            clear_session(db, chat_id)
            _send_telegram_message(token, chat_id, "Operação cancelada.")
        else:
            _send_telegram_message(token, chat_id, "Responda <b>sim</b> para confirmar ou <b>não</b> para cancelar.")
        return

    if active_tool:
        # Slot-filling em andamento: extrai mais parâmetros
        current_slots = session.get("slots", {})
        required_params = session.get("required_params", [])
        _send_telegram_typing(token, chat_id)
        updated_slots = core_router.extract_slots(gemini_key, active_tool, text, current_slots, registry.get_schema(active_tool))
        missing = core_router.get_missing_params(required_params, updated_slots)

        if missing:
            save_slot_session(db, chat_id, active_tool, updated_slots, required_params, trace_id,
                              history=session.get("history", []))
            _send_telegram_message(token, chat_id, core_router.get_missing_param_prompt(missing))
            return

        # Todos os slots preenchidos
        if registry.needs_confirmation(active_tool):
            save_slot_session(db, chat_id, active_tool, updated_slots, required_params, trace_id,
                              history=session.get("history", []), awaiting_confirmation=True)
            _send_telegram_message(token, chat_id, _build_confirmation_draft(active_tool, updated_slots))
            return

        provisional_msg_id = _send_telegram_message(token, chat_id, "⏳ Executando...")
        result = _execute_tool(active_tool, updated_slots, db)
        clear_session(db, chat_id)
        tracing.log("INFO", "tool_executed", tool=active_tool)
        _deliver_response(token, chat_id, result, response_mode, voice_profile, gemini_key,
                          message_id_to_edit=provisional_msg_id)
        return

    # --- Sem sessão ativa: Stage 1 — classificação ---
    _send_telegram_typing(token, chat_id)
    tool_name = core_router.classify_tool(gemini_key, text, registry.get_short_catalog())

    if tool_name:
        # Stage 2 — extração de slots
        schema = registry.get_schema(tool_name)
        required_params = registry.get_required_params(tool_name)
        slots = core_router.extract_slots(gemini_key, tool_name, text, {}, schema)
        missing = core_router.get_missing_params(required_params, slots)

        if missing:
            save_slot_session(db, chat_id, tool_name, slots, required_params, trace_id)
            _send_telegram_message(token, chat_id, core_router.get_missing_param_prompt(missing))
            tracing.log("INFO", "slot_filling_started", tool=tool_name, missing=missing)
            return

        # Slots completos desde a primeira mensagem
        if registry.needs_confirmation(tool_name):
            save_slot_session(db, chat_id, tool_name, slots, required_params, trace_id, awaiting_confirmation=True)
            _send_telegram_message(token, chat_id, _build_confirmation_draft(tool_name, slots))
            return

        provisional_msg_id = _send_telegram_message(token, chat_id, "⏳ Processando...")
        result = _execute_tool(tool_name, slots, db)
        tracing.log("INFO", "tool_executed", tool=tool_name)
        _deliver_response(token, chat_id, result, response_mode, voice_profile, gemini_key,
                          message_id_to_edit=provisional_msg_id)
        return

    # --- Sem tool identificada: resposta conversacional ---
    history = trim_history(session.get("history", []))
    response_text = _run_general_response(db, gemini_key, text, history)
    new_history = trim_history(history + [{"role": "user", "text": text}, {"role": "model", "text": response_text}])
    save_general_session(db, chat_id, new_history, trace_id)
    _deliver_response(token, chat_id, response_text, response_mode, voice_profile, gemini_key)


# ---------------------------------------------------------------------------
# Cloud Functions
# ---------------------------------------------------------------------------

@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["GET", "POST"]),
    timeout_sec=10,
    memory=options.MemoryOption.GB_1,
)
def telegramWebhook(req: https_fn.Request) -> https_fn.Response:
    """
    Porteiro: recebe POST do Telegram, valida auth + idempotência,
    enfileira no Firestore e retorna 200 imediatamente.
    """
    if req.method != "POST":
        return https_fn.Response("OK", status=200)

    try:
        update = req.get_json(silent=True) or {}
    except Exception:
        return https_fn.Response("OK", status=200)

    message = update.get("message") or update.get("edited_message") or {}
    if not message:
        return https_fn.Response("OK", status=200)

    chat = message.get("chat", {})
    chat_id = str(chat.get("id", ""))
    update_id = update.get("update_id")

    if not chat_id:
        return https_fn.Response("OK", status=200)

    # --- Autorização ---
    from core import auth as core_auth
    db = _get_db()
    allowed_env = _get_allowed_chat_id()
    if not core_auth.is_authorized(db, chat_id, env_fallback=allowed_env):
        return https_fn.Response("OK", status=200)

    # --- Idempotência ---
    from core import idempotency as core_idem
    if not core_idem.check_and_register(db, update_id):
        return https_fn.Response("OK", status=200)

    text = message.get("text") or message.get("caption") or ""
    from_user = message.get("from", {})
    message_id = str(message.get("message_id", ""))

    audio_info = None
    file_info = None
    media_bytes_b64 = None
    media_storage_path = None

    try:
        token = _get_telegram_token(db)
    except Exception:
        return https_fn.Response("OK", status=200)

    # --- Mídia: áudio / voz ---
    audio = message.get("audio") or message.get("voice")
    if audio:
        file_size = audio.get("file_size", 0)
        if file_size > _MAX_FILE_BYTES:
            _send_telegram_message(token, chat_id, "⚠️ Áudio muito grande (máx. 20 MB).")
            return https_fn.Response("OK", status=200)
        try:
            file_meta = _get_telegram_file(token, audio["file_id"])
            file_bytes = _download_telegram_file(token, file_meta["file_path"])
            media_bytes_b64, media_storage_path = _store_telegram_media(
                file_bytes, f"audio_{message_id}.ogg", audio.get("mime_type", "audio/ogg"), chat_id,
            )
            audio_info = {
                "file_id": audio["file_id"],
                "file_size": file_size,
                "mime_type": audio.get("mime_type", "audio/ogg"),
                "duration": audio.get("duration", 0),
            }
        except Exception as e:
            print(f"[Webhook] Audio download error: {e}")
            _send_telegram_message(token, chat_id, f"⚠️ Não consegui baixar o áudio: {e}")
            return https_fn.Response("OK", status=200)

    # --- Mídia: documento / foto ---
    doc = message.get("document")
    photos = message.get("photo")
    if not audio_info:
        media_obj = doc or (photos[-1] if photos else None)
        if media_obj:
            file_size = media_obj.get("file_size", 0)
            if file_size > _MAX_FILE_BYTES:
                _send_telegram_message(token, chat_id, "⚠️ Arquivo muito grande (máx. 20 MB).")
                return https_fn.Response("OK", status=200)
            try:
                file_meta = _get_telegram_file(token, media_obj["file_id"])
                file_bytes = _download_telegram_file(token, file_meta["file_path"])
                file_info = {
                    "file_id": media_obj["file_id"],
                    "file_size": file_size,
                    "file_name": doc.get("file_name", "arquivo") if doc else "foto.jpg",
                    "mime_type": (doc.get("mime_type") if doc else "image/jpeg") or "application/octet-stream",
                }
                media_bytes_b64, media_storage_path = _store_telegram_media(
                    file_bytes, file_info["file_name"], file_info["mime_type"], chat_id,
                )
            except Exception as e:
                print(f"[Webhook] File download error: {e}")

    if not text and not audio_info and not file_info:
        return https_fn.Response("OK", status=200)

    # --- Gera trace_id e enfileira ---
    from core.tracing import generate_trace_id
    trace_id = generate_trace_id()

    payload = {
        "chat_id": chat_id,
        "update_id": update_id,
        "message_id": message_id,
        "text": text,
        "from_user": from_user,
        "audio_info": audio_info,
        "file_info": file_info,
        "media_bytes_b64": media_bytes_b64,
        "media_storage_path": media_storage_path,
        "trace_id": trace_id,
        "received_at": firestore.SERVER_TIMESTAMP,
        "processed": False,
    }
    db.collection("telegram_inbound").document(f"{chat_id}_{message_id}").set(payload)
    return https_fn.Response("OK", status=200)


@firestore_fn.on_document_created(
    document="telegram_inbound/{docId}",
    timeout_sec=540,
    memory=options.MemoryOption.GB_2,
)
def on_telegram_inbound(event: Event[DocumentSnapshot]) -> None:
    """Trigger assíncrono: processa mensagem enfileirada e envia resposta ao Telegram."""
    snap = event.data
    if not snap or not snap.exists:
        return

    data = snap.to_dict() or {}
    if data.get("processed"):
        return

    snap.reference.update({"processed": True, "processing_started_at": firestore.SERVER_TIMESTAMP})

    try:
        db = _get_db()
        _process_telegram_message(db, data)
    except Exception as e:
        print(f"[on_telegram_inbound] Unhandled error: {e}")
        import traceback
        traceback.print_exc()
        snap.reference.update({"error": str(e)})
        try:
            chat_id = data.get("chat_id")
            trace_id = data.get("trace_id", "?")
            token = _get_telegram_token(_get_db())
            if chat_id and token:
                _send_telegram_message(
                    token, chat_id,
                    f"⚠️ Erro interno ao processar mensagem. Código: <code>{trace_id[:8]}</code>"
                )
        except Exception:
            pass
