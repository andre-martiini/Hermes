"""
Hermes Core Logic — Telegram Integration
Webhook receiver + Firestore-triggered async processor.
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
from firebase_functions.firestore_fn import Event, Change, DocumentSnapshot
from google.cloud.firestore_v1 import DocumentReference

try:
    get_app()
except ValueError:
    initialize_app()

_MAX_HISTORY_TURNS = 20
_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB
_TTS_MODEL_ID = "gemini-3.1-flash-tts-preview"
_TEXT_MODEL_ID = "gemini-3-flash-preview"
_DEFAULT_MALE_VOICE = "Charon"
_MAX_TTS_TRANSCRIPT_CHARS = 1500

# ---------------------------------------------------------------------------
# Helpers
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


def _send_telegram_message(token: str, chat_id: str | int, text: str, parse_mode: str = "HTML"):
    """POST direto à Telegram Bot API."""
    # Telegram HTML: truncate at 4096 chars
    if len(text) > 4096:
        text = text[:4090] + "\n..."
    resp = _requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
        timeout=30,
    )
    if not resp.ok:
        print(f"[Telegram] sendMessage failed: {resp.status_code} {resp.text[:300]}")


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
    files = {
        "voice": (filename, audio_bytes, mime_type),
    }
    data = {
        "chat_id": str(chat_id),
    }
    if caption:
        data["caption"] = caption[:1024]
    resp = _requests.post(
        f"https://api.telegram.org/bot{token}/sendVoice",
        data=data,
        files=files,
        timeout=120,
    )
    if not resp.ok:
        print(f"[Telegram] sendVoice failed: {resp.status_code} {resp.text[:500]}")
    return bool(resp.ok)


def _send_telegram_document(token: str, chat_id: str | int, file_bytes: bytes, filename: str, mime_type: str, caption: str = "") -> bool:
    files = {
        "document": (filename, file_bytes, mime_type),
    }
    data = {
        "chat_id": str(chat_id),
    }
    if caption:
        data["caption"] = caption[:1024]
    resp = _requests.post(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data=data,
        files=files,
        timeout=120,
    )
    if not resp.ok:
        print(f"[Telegram] sendDocument failed: {resp.status_code} {resp.text[:500]}")
    return bool(resp.ok)


def _get_telegram_file(token: str, file_id: str) -> dict:
    """Calls getFile and returns the file metadata dict."""
    resp = _requests.get(
        f"https://api.telegram.org/bot{token}/getFile",
        params={"file_id": file_id},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("result", {})


def _download_telegram_file(token: str, file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    resp = _requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


# ---------------------------------------------------------------------------
# Session state machine
# ---------------------------------------------------------------------------

def _get_session(db, chat_id: str) -> dict:
    doc = db.collection("telegram_sessions").document(chat_id).get()
    return doc.to_dict() or {"chat_id": chat_id, "contexto_ativo": "geral", "history": []}


def _save_session(db, chat_id: str, session: dict):
    session["updated_at"] = firestore.SERVER_TIMESTAMP
    db.collection("telegram_sessions").document(chat_id).set(session)


def _handle_command(text: str, session: dict) -> Optional[str]:
    """
    Returns a reply string if the message is a state-machine command, else None.
    Side-effects: mutates session.
    """
    text = (text or "").strip()
    m = re.match(r"^/contexto\s+(.+)$", text, re.IGNORECASE)
    if m:
        ctx = m.group(1).strip()
        session["contexto_ativo"] = ctx
        session["history"] = []  # fresh history for new context
        return f"Contexto ativo definido como <b>{ctx}</b>. Histórico reiniciado."

    if re.match(r"^/sair$", text, re.IGNORECASE):
        previous = session.get("contexto_ativo", "geral")
        session["contexto_ativo"] = "geral"
        session["history"] = []
        return f"Saindo do contexto <b>{previous}</b>. Voltando ao modo geral."

    if re.match(r"^/start$", text, re.IGNORECASE):
        return (
            "👋 Olá! Sou o <b>Hermes Copiloto</b>.\n\n"
            "Comandos disponíveis:\n"
            "• <code>/contexto [nome]</code> — foca em uma área específica (ex: /contexto finanças)\n"
            "• <code>/sair</code> — retorna ao modo geral\n\n"
            "Envie texto, áudio ou arquivos. Tamanho máximo: 20 MB."
        )

    if re.match(r"^/status$", text, re.IGNORECASE):
        ctx = session.get("contexto_ativo", "geral")
        turns = len(session.get("history", [])) // 2
        return f"Contexto ativo: <b>{ctx}</b>\nTurnos no histórico: {turns}"

    return None


# ---------------------------------------------------------------------------
# Audio transcription (reusing Groq / Gemini pattern from main.py)
# ---------------------------------------------------------------------------

def _transcribe_audio_bytes(audio_bytes: bytes, extension: str, db) -> str:
    import base64 as _b64
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
# Media upload to Firebase Storage
# ---------------------------------------------------------------------------

def _upload_to_storage(file_bytes: bytes, file_name: str, mime_type: str, chat_id: str) -> str:
    """Uploads to Firebase Storage and returns the public URL (gs://)."""
    bucket = storage.bucket()
    path = f"telegram_uploads/{chat_id}/{file_name}"
    blob = bucket.blob(path)
    blob.upload_from_string(file_bytes, content_type=mime_type)
    blob.make_public()
    return blob.public_url


# ---------------------------------------------------------------------------
# Gemini orchestration
# ---------------------------------------------------------------------------

def _build_system_instruction(copilot_core: str, copilot_soul: str, contexto_ativo: str) -> str:
    from datetime import datetime as _dt
    today = _dt.now(timezone.utc).strftime("%Y-%m-%d")
    ctx_hint = (
        f"\n\n<b>Contexto ativo:</b> {contexto_ativo}"
        if contexto_ativo != "geral"
        else ""
    )
    return (
        f"Você é o Copiloto Hermes, estrategista sênior de processos. Hoje é {today}."
        f"{ctx_hint}\n\n"
        "## CORE ESTÁTICO DO COPILOTO\n"
        f"{copilot_core}\n\n"
        "## PERSONALIDADE DINÂMICA ATUAL\n"
        f"{copilot_soul}\n\n"
        "## CANAL DE COMUNICAÇÃO: TELEGRAM\n"
        "REGRA ABSOLUTA DE FORMATAÇÃO: Você está respondendo via Telegram. "
        "Use EXCLUSIVAMENTE as seguintes tags HTML suportadas pelo Telegram: "
        "<b>negrito</b>, <i>itálico</i>, <code>código inline</code>, <pre>bloco de código</pre>. "
        "PROIBIDO usar Markdown (asteriscos, underlines, backticks, #, ##). "
        "Listas: use • ou - como prefixo de linha, sem Markdown. "
        "Mantenha respostas concisas — Telegram tem limite de 4096 caracteres por mensagem.\n\n"
        "## REGRAS ABSOLUTAS\n"
        "1. JAMAIS expanda siglas arbitrariamente.\n"
        "2. Se qualquer ferramenta retornar campo 'erro', reproduza o erro literal.\n"
        "3. Agendamento/Agenda: Você DEVE usar consultar_agenda ou encontrar_slot_livre ANTES de agendar. Horário de funcionamento: 08:00 às 19:00, janela D+7. Se houver conflito em horário específico, pergunte se força inserção ou busca outro slot. Na criação, use os campos horario_inicio e horario_fim.\n"
        "4. Para criar uma ação, apresente um draft estruturado primeiro com Título, Início/Fim (se houver), Área Temática e Tipo. Aguarde confirmação explicita.\n"
        "5. Links de tarefas: use o formato task:{ID} no texto (ex: 'Ação task:abc123').\n"
        "6. Acione salvar_memoria_global apenas para fatos duráveis e preferências estáveis.\n"
    )


def _normalize_for_matching(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.lower()


def _extract_response_mode(text: str, session: dict) -> tuple[str, str]:
    raw_text = (text or "").strip()
    if not raw_text:
        return session.get("response_mode", "texto"), raw_text

    lowered = _normalize_for_matching(raw_text)
    explicit_audio_markers = (
        "/audio",
        "#audio",
        "[audio]",
        "mensagem de voz",
        "em voz",
        "por voz",
    )
    audio_keywords = ("audio", "voz")
    request_verbs = ("responda", "resposta", "mande", "manda", "envie", "quero")
    wants_audio = any(marker in lowered for marker in explicit_audio_markers)
    if not wants_audio:
        wants_audio = any(v in lowered for v in request_verbs) and any(k in lowered for k in audio_keywords)

    if wants_audio:
        cleaned = raw_text
        cleaned = re.sub(r"^/audio\b", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"#audio|\[audio\]", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"(me\s+)?responda\s+(em|por|para|pro?)\s+(o\s+)?[aá]udio", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"resposta\s+(em|por|para|pro?)\s+(o\s+)?[aá]udio", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"envie\s+(em|por|para|pro?)\s+(o\s+)?[aá]udio", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"(me\s+)?mande\s+(em|por|para|pro?)\s+(o\s+)?[aá]udio", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"quero\s+(em|por|para|pro?)\s+(o\s+)?[aá]udio", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"mensagem de voz", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\b(em|por)\s+voz\b", "", cleaned, flags=re.IGNORECASE).strip()
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
    masculine_markers = (
        "#voz:masculina",
        "[voz:masculina]",
        "/voz masculina",
        "voz masculina",
        "na voz masculina",
        "com voz masculina",
    )

    if any(marker in lowered for marker in masculine_markers):
        cleaned = re.sub(r"#voz:masculina|\[voz:masculina\]|/voz masculina", "", raw_text, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\b(na|com)?\s*voz masculina\b", "", cleaned, flags=re.IGNORECASE).strip()
        return "masculina", cleaned

    return default_voice, raw_text


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


def _build_tts_director_instruction(voice_profile: str) -> str:
    return (
        "Voce e o diretor de TTS do Hermes. "
        "Recebera uma resposta factual pronta e deve apenas converte-la em um roteiro curto para fala natural. "
        "Nao adicione fatos novos. "
        "Nao inclua links, nomes tecnicos longos nem listas densas. "
        "Nao use tags, colchetes nem anotacoes de palco. "
        "Entregue apenas o texto a ser falado. "
        "Mantenha tom de assistente operacional, conversa um a um, sem soar como narrador. "
        "Priorize objetividade, proximidade e sobriedade. "
        f"Perfil de voz desejado: {voice_profile}. "
        "Responda apenas com o roteiro final."
    )


def _run_gemini_tts(gemini_key: str, script_text: str, voice_profile: str) -> tuple[bytes, str]:
    from google import genai
    from google.genai import types

    voice_name = _DEFAULT_MALE_VOICE
    client = genai.Client(api_key=gemini_key)
    style_prompt = (
        "### DIRECTOR'S NOTES\n"
        "Style: concise operational assistant, one-to-one, practical and calm.\n"
        "Pacing: natural conversational pace, with short pauses only when meaning changes.\n"
        "Tone: professional, direct, grounded, helpful and discreet.\n"
        "Delivery: do not sound like a narrator, announcer, storyteller, presenter or commercial voice-over.\n"
        "Delivery: sound like a senior assistant speaking directly to one person.\n\n"
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
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )

    for candidate in (response.candidates or []):
        for part in (candidate.content.parts or []):
            inline_data = getattr(part, "inline_data", None)
            if inline_data and getattr(inline_data, "data", None):
                return inline_data.data, getattr(inline_data, "mime_type", "audio/L16;rate=24000")
    raise RuntimeError("Gemini TTS nÃ£o retornou Ã¡udio.")


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
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            wav_path,
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            ogg_path,
        ]
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
    _send_telegram_message(
        token,
        chat_id,
        "⚠️ Houve uma falha tÃ©cnica ao gerar o Ã¡udio. Repita a solicitaÃ§Ã£o ou peÃ§a a resposta em texto.",
    )


def _run_gemini_turn(
    db,
    gemini_key: str,
    system_instruction: str,
    history: list,
    user_message_parts: list,
    tools_list: list,
    function_map: dict,
) -> str:
    """Runs a full Gemini multi-turn exchange and returns the final text response."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=gemini_key)
    model_id = "gemini-3-flash-preview"

    chat = client.chats.create(
        model=model_id,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools_list,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
        history=history,
    )

    response = chat.send_message(user_message_parts)

    # Agentic loop — processa tool calls até obter resposta de texto
    for _ in range(10):
        if not response.candidates:
            break
        candidate = response.candidates[0]
        if candidate.finish_reason and candidate.finish_reason.name not in ("STOP", "MAX_TOKENS", ""):
            break

        # Coleta function calls neste turno
        func_calls = []
        for part in (candidate.content.parts or []):
            if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                func_calls.append(part.function_call)

        if not func_calls:
            break

        # Executa todas as tool calls e coleta resultados
        tool_results = []
        for fc in func_calls:
            fn = function_map.get(fc.name)
            if fn is None:
                result_text = f"Ferramenta '{fc.name}' não encontrada."
            else:
                try:
                    kwargs = dict(fc.args or {})
                    result = fn(**kwargs)
                    result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                except Exception as tool_err:
                    result_text = f"Erro ao executar {fc.name}: {tool_err}"
            tool_results.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result_text},
                )
            )

        response = chat.send_message(tool_results)

    # Extrai texto final
    text_parts = []
    if response.candidates:
        for part in (response.candidates[0].content.parts or []):
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
    return "\n".join(text_parts).strip() or "Não consegui gerar uma resposta. Tente novamente."


# ---------------------------------------------------------------------------
# Main processing logic
# ---------------------------------------------------------------------------

def _process_telegram_message(db, data: dict):
    """Full processing pipeline for one incoming Telegram message."""
    from google.genai import types
    from tools.busca_grafo import buscar_tarefas
    from tools.busca_acervo import buscar_acervo

    chat_id = str(data.get("chat_id", ""))
    text = (data.get("text") or "").strip()
    file_info = data.get("file_info")   # {file_id, file_unique_id, file_size, mime_type, file_name}
    audio_info = data.get("audio_info") # {file_id, file_size, mime_type, duration}
    media_bytes_b64 = data.get("media_bytes_b64")  # base64 of already-downloaded file

    if not chat_id:
        return

    keys = _get_api_keys(db)
    gemini_key = keys.get("gemini_api_key")
    token = keys.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not gemini_key or not token:
        _send_telegram_message(token, chat_id, "⚠️ Configuração incompleta. Contate o administrador.")
        return

    session = _get_session(db, chat_id)
    response_mode, text = _extract_response_mode(text, session)
    voice_profile, text = _extract_voice_profile(text, "masculina")
    print(f"[Core] initial response_mode={response_mode} voice_profile={voice_profile}")

    # --- Command handler ---
    if text.startswith("/"):
        reply = _handle_command(text, session)
        if reply:
            _save_session(db, chat_id, session)
            _send_telegram_message(token, chat_id, reply)
            return
        # Unknown command — fall through to Gemini

    # --- Load copilot personality ---
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

    contexto_ativo = session.get("contexto_ativo", "geral")
    system_instruction = _build_system_instruction(copilot_core, copilot_soul, contexto_ativo)

    # --- Restore history (trimmed) ---
    raw_history = session.get("history", [])
    # Keep last N turns (each turn = user + model = 2 items)
    if len(raw_history) > _MAX_HISTORY_TURNS * 2:
        raw_history = raw_history[-((_MAX_HISTORY_TURNS * 2)):]
    history = [
        types.Content(role=h["role"], parts=[types.Part(text=p["text"]) for p in h.get("parts", [])])
        for h in raw_history
        if h.get("role") and h.get("parts")
    ]

    # --- Resolve user message parts ---
    user_parts = []
    file_context_text = ""

    # Audio transcription
    if audio_info and media_bytes_b64:
        import base64
        audio_bytes = base64.b64decode(media_bytes_b64)
        mime = audio_info.get("mime_type", "audio/ogg")
        raw_ext = mime.split("/")[-1]
        ext = "ogg" if raw_ext in ("ogg", "oga") else raw_ext
        _send_telegram_typing(token, chat_id)
        try:
            transcription = _transcribe_audio_bytes(audio_bytes, ext, db)
        except Exception as transcribe_err:
            print(f"[Core] Transcription error: {transcribe_err}")
            import traceback; traceback.print_exc()
            transcription = None
        if transcription:
            if response_mode != "audio":
                transcribed_mode, cleaned_transcription = _extract_response_mode(transcription, session)
                if transcribed_mode == "audio":
                    response_mode = "audio"
                    transcription = cleaned_transcription
            voice_profile, transcription = _extract_voice_profile(transcription, voice_profile)
            print(f"[Core] transcription response_mode={response_mode} voice_profile={voice_profile} transcription={transcription[:160]}")
            file_context_text = f"[Transcri??o de ?udio]: {transcription}"
            user_parts.append(types.Part(text=file_context_text))
        else:
            user_parts.append(types.Part(text="[?udio recebido mas transcri??o falhou]"))

    # File/document
    elif file_info and media_bytes_b64:
        import base64, uuid as _uuid
        file_bytes = base64.b64decode(media_bytes_b64)
        fname = file_info.get("file_name") or f"upload_{_uuid.uuid4().hex[:8]}"
        mime = file_info.get("mime_type", "application/octet-stream")
        try:
            pub_url = _upload_to_storage(file_bytes, fname, mime, chat_id)
            file_context_text = (
                f"[Arquivo recebido]: {fname} ({mime})\n"
                f"URL: {pub_url}\n"
                "Analise este arquivo, identifique o que ele mostra e sugira como ele se relaciona ao contexto atual."
            )
        except Exception as up_err:
            file_context_text = f"[Arquivo recebido: {fname}] (falha no upload: {up_err})"
        user_parts.append(types.Part(text=file_context_text))

    # Text
    if text:
        user_parts.append(types.Part(text=text))

    if not user_parts:
        user_parts.append(types.Part(text="[Mensagem sem conteúdo processável]"))

    # --- Memory context ---
    try:
        from knowledge_graph import _get_embedding
        query_text = text or file_context_text or ""
        if query_text:
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
                mem_text = "## MEMÓRIA GLOBAL ATIVA\n" + "\n".join(mem_lines)
                system_instruction = system_instruction + "\n\n" + mem_text
    except Exception:
        pass

    # --- Tool definitions ---
    def consultar_historico_acoes(
        query: str,
        area_tematica: str = None,
        data_limite_inicio: str = None,
        data_limite_fim: str = None,
        status: str = None,
    ):
        """Busca ações e tarefas no Hermes. Use status para filtrar por estado (ex: 'em andamento', 'concluída', 'cancelada'). Use data_limite_inicio/fim (YYYY-MM-DD) para filtrar por prazo."""
        from tools.busca_grafo import buscar_tarefas

        res = buscar_tarefas(query, area_tematica=area_tematica, match_mode="all",
                             data_limite_inicio=data_limite_inicio, data_limite_fim=data_limite_fim,
                             status=status)
        if not res.get("resultados"):
            res = buscar_tarefas(query, area_tematica=area_tematica, match_mode="any",
                                 data_limite_inicio=data_limite_inicio, data_limite_fim=data_limite_fim,
                                 status=status)
        if res.get("erro"):
            return f"⚠️ [ERRO] {res['erro']}"
        resultados = res.get("resultados", [])
        if not resultados:
            return f"Nenhum registro encontrado para '{query}'."
        lines = ["--- TAREFAS ENCONTRADAS ---"]
        for r in resultados:
            lines.append(
                f"ID: {r['id']} | {r['titulo']} | {r['status']} | "
                f"Prazo: {r.get('data_limite','N/A')} | Área: {r['area']}"
            )
        return "\n".join(lines)

    def buscar_arquivos_acervo(query: str):
        """Busca documentos, manuais e arquivos no Acervo Global do Hermes."""
        from tools.busca_acervo import buscar_acervo
        res = buscar_acervo(query)
        if res.get("erro"):
            return f"⚠️ [ERRO] {res['erro']}"
        resultados = res.get("resultados", [])
        if not resultados:
            return "Nenhum documento encontrado."
        return "\n\n".join(
            f"DOC: {r['titulo']} | FONTE: {r['fonte']}\nTRECHO: {r['trecho']}"
            for r in resultados
        )

    def pesquisar_internet(query: str):
        """Busca informações recentes na internet via Tavily."""
        try:
            tavily_key = _get_api_keys(db).get("tavily_api_key")
            if not tavily_key:
                return '{"error": "Tavily não configurado."}'
            resp = _requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "search_depth": "advanced",
                      "include_answer": True, "include_raw_content": False, "max_results": 5},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            parts = []
            if data.get("answer"):
                parts.append(f"RESPOSTA: {data['answer']}\n")
            for r in data.get("results", []):
                parts.append(f"FONTE: {r.get('title','')} ({r.get('url','')})\n{r.get('content','')}")
            return "\n\n".join(parts) or "Sem resultados."
        except Exception as e:
            return f'{{"error": "{e}"}}'

    def ler_pagina_web(url: str):
        """Lê o conteúdo de uma URL via Jina Reader."""
        try:
            resp = _requests.get(f"https://r.jina.ai/{url}",
                                 headers={"Accept": "text/markdown"}, timeout=25)
            if resp.status_code in (401, 403, 429):
                return '{"error": "Acesso bloqueado pela página de destino."}'
            resp.raise_for_status()
            content = resp.text.strip()
            return content[:12000] + "\n[truncado]" if len(content) > 12000 else content
        except Exception as e:
            return f'{{"error": "{e}"}}'

    def consultar_agenda(data_inicio: str, data_fim: str):
        """Retorna eventos ocupados no período para verificação de disponibilidade (YYYY-MM-DD)."""
        try:
            from main import get_calendar_service, get_target_calendar_id
            import hermes_calendar_tools as hc_tools
            c_service = get_calendar_service()
            # Na main.py talvez get_db e db global não funcionem direto dentro da tool, mas 'db' é capturado!
            c_id = get_target_calendar_id(db)
            if not c_service or not c_id:
                return "Google Calendar não configurado."
            events = hc_tools.consultar_eventos(c_service, c_id, data_inicio, data_fim)
            return hc_tools.formatar_eventos_para_llm(events)
        except Exception as e:
            return f"Erro ao consultar agenda: {e}"

    def encontrar_slot_livre(a_partir_de: str, duracao_min: int = 30):
        """Encontra o próximo horário livre na agenda. a_partir_de = YYYY-MM-DD. Retorna JSON com data, horario_inicio, horario_fim."""
        try:
            from main import get_calendar_service, get_target_calendar_id
            import hermes_calendar_tools as hc_tools
            c_service = get_calendar_service()
            c_id = get_target_calendar_id(db)
            if not c_service or not c_id:
                return "Erro: Google Calendar não configurado."
            slot = hc_tools.encontrar_proximo_slot(c_service, c_id, a_partir_de, duracao_min)
            if slot:
                import json as _js
                return _js.dumps(slot, ensure_ascii=False)
            return "Nenhum slot livre encontrado."
        except Exception as e:
            return f"Erro ao buscar slot livre: {e}"

    def criar_acao_no_sistema(
        titulo: str,
        descricao: str = "",
        area_tematica: str = "GERAL",
        data_limite: str = None,
        tipo_acao: str = "fast",
        tags: list[str] = None,
        notas: str = "",
        plano_acao: list[str] = None,
        horario_inicio: str = None,
        horario_fim: str = None,
    ):
        """
        Cria uma nova ação no Hermes. Apresente draft ao usuário antes de chamar.
        Retorna 'OK|{ID}' em caso de sucesso ou 'ERRO|{detalhe}'.
        """
        import uuid as _uuid
        now_iso = datetime.now(timezone.utc).isoformat()
        today = (datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        if not data_limite:
            data_limite = today
        task_id = str(_uuid.uuid4())[:20]
        plano_convertido = [
            {"id": str(_uuid.uuid4())[:8], "text": str(p), "completed": False}
            for p in (plano_acao or []) if str(p).strip()
        ]
        try:
            from main import get_calendar_service, get_target_calendar_id
            import hermes_calendar_tools as hc_tools
            c_service = get_calendar_service()
            c_id = get_target_calendar_id(db)
            if c_service and c_id and horario_inicio and horario_fim:
                hc_tools.reagendar_acoes_hermes(db, c_service, c_id, data_limite, horario_inicio, horario_fim)
        except Exception as e:
            print(f"[Core] Erro ao reagendar iterativo: {e}")

        doc = {
            "id": task_id,
            "titulo": titulo.strip(),
            "descricao": descricao or "",
            "area_tematica": area_tematica or "GERAL",
            "data_limite": data_limite,
            "horario_inicio": horario_inicio,
            "horario_fim": horario_fim,
            "tipo_acao": tipo_acao or "fast",
            "tags": tags or [],
            "notas": notas or "",
            "plano_acao": plano_convertido,
            "status": "em andamento",
            "criado_em": now_iso,
            "data_criacao": now_iso,
            "data_atualizacao": now_iso,
            "origem_ingestao": "telegram",
            "acompanhamento": [],
            "sync_status": "new",
        }
        try:
            db.collection("tarefas").document(task_id).set(doc)
            return f"OK|{task_id}"
        except Exception as e:
            return f"ERRO|{e}"

    def salvar_memoria_global(fato: str, categoria: str):
        """Persiste fato durável na memória global do Hermes. Apenas para regras estáveis e preferências permanentes."""
        try:
            import uuid as _uuid
            node_id = str(_uuid.uuid4())[:16]
            db.collection("knowledge_nodes").document(node_id).set({
                "id": node_id,
                "fato": fato,
                "categoria": categoria,
                "data_criacao": datetime.now(timezone.utc).isoformat(),
                "origem": "telegram",
            })
            return json.dumps({"status": "saved", "id": node_id}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "reason": str(e)}, ensure_ascii=False)

    def registrar_correcao_procedimento(
        area_tematica: str,
        titulo_procedimento: str,
        correcao_descrita: str,
        novo_conteudo_proposto: str,
        justificativa: str,
    ):
        """[FERRAMENTA OCULTA] Registra correção de procedimento silenciosamente."""
        try:
            import uuid as _uuid
            cid = str(_uuid.uuid4())[:12]
            db.collection("correcoes_pendentes").document(cid).set({
                "id": cid,
                "area_tematica": area_tematica,
                "titulo_procedimento": titulo_procedimento,
                "correcao_descrita": correcao_descrita,
                "novo_conteudo_proposto": novo_conteudo_proposto,
                "justificativa_usuario": justificativa,
                "status": "pendente",
                "data_criacao": firestore.SERVER_TIMESTAMP,
                "origem": "telegram",
            })
            return f"Correção registrada (ID: {cid})."
        except Exception as e:
            return f"Erro: {e}"

    def buscar_e_analisar_email(query: str, max_results: int = 5):
        """Busca e analisa e-mails no Gmail. Use query padrão do Gmail (ex: 'from:x@y.com newer_than:2d')."""
        try:
            from tools.buscar_e_analisar_email import buscar_e_analisar_email as _fn
            return _fn(query=query, max_results=min(int(max_results), 5))
        except Exception as e:
            return f"Erro: {e}"

    tools_list = [
        consultar_historico_acoes,
        buscar_arquivos_acervo,
        pesquisar_internet,
        ler_pagina_web,
        consultar_agenda,
        encontrar_slot_livre,
        criar_acao_no_sistema,
        salvar_memoria_global,
        registrar_correcao_procedimento,
        buscar_e_analisar_email,
    ]

    function_map = {fn.__name__: fn for fn in tools_list}

    # --- Gemini call ---
    _send_telegram_typing(token, chat_id)
    try:
        response_text = _run_gemini_turn(
            db=db,
            gemini_key=gemini_key,
            system_instruction=system_instruction,
            history=history,
            user_message_parts=user_parts,
            tools_list=tools_list,
            function_map=function_map,
        )
    except Exception as gemini_err:
        print(f"[Core] Gemini error: {gemini_err}")
        _send_telegram_message(token, chat_id, f"⚠️ Erro ao processar: {gemini_err}")
        return

    # --- Persist history ---
    def _serialize_part(p):
        return {"text": getattr(p, "text", "") or ""}

    user_turn = {"role": "user", "parts": [{"text": p.text} for p in user_parts if hasattr(p, "text") and p.text]}
    model_turn = {"role": "model", "parts": [{"text": response_text}]}
    new_history = raw_history + [user_turn, model_turn]
    # Trim
    if len(new_history) > _MAX_HISTORY_TURNS * 2:
        new_history = new_history[-(_MAX_HISTORY_TURNS * 2):]
    session["history"] = new_history
    _save_session(db, chat_id, session)

    # --- Send response ---
    if response_mode == "audio":
        try:
            with _telegram_action_heartbeat(token, chat_id, "record_voice"):
                print(f"[Core] sending audio with voice_profile={voice_profile}")
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
                        raise RuntimeError("Falha ao enviar voice note pelo Telegram.")
                else:
                    wav_bytes, wav_mime, wav_name = _wrap_pcm_audio_as_wav(audio_bytes, audio_mime)
                    if not _send_telegram_document(token, chat_id, wav_bytes, wav_name, wav_mime, caption="Resposta em audio"):
                        raise RuntimeError("Falha ao enviar arquivo de audio pelo Telegram.")
        except Exception as tts_err:
            print(f"[Core] TTS error: {tts_err}")
            _send_tts_failure_notice(token, chat_id)
            return
    else:
        _send_telegram_message(token, chat_id, response_text)


# ---------------------------------------------------------------------------
# Cloud Functions
# ---------------------------------------------------------------------------

@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["GET", "POST"]),
    timeout_sec=10,
    memory=options.MemoryOption.MB_256,
)
def telegramWebhook(req: https_fn.Request) -> https_fn.Response:
    """
    Porteiro: recebe POST do Telegram, valida, enfileira no Firestore e retorna 200.
    Nunca bloqueia aguardando processamento Gemini.
    """
    if req.method != "POST":
        return https_fn.Response("OK", status=200)

    try:
        update = req.get_json(silent=True) or {}
    except Exception:
        return https_fn.Response("OK", status=200)

    # --- Extrair mensagem ---
    message = update.get("message") or update.get("edited_message") or {}
    if not message:
        return https_fn.Response("OK", status=200)

    chat = message.get("chat", {})
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        return https_fn.Response("OK", status=200)

    # --- Validação single-owner ---
    allowed = _get_allowed_chat_id()
    if allowed and chat_id != allowed:
        return https_fn.Response("OK", status=200)  # silent ignore

    text = message.get("text") or message.get("caption") or ""
    from_user = message.get("from", {})
    message_id = str(message.get("message_id", ""))

    # --- Detectar mídia ---
    audio_info = None
    file_info = None
    media_bytes_b64 = None

    db = _get_db()

    try:
        token = _get_telegram_token(db)
    except Exception:
        return https_fn.Response("OK", status=200)

    # Audio / Voice
    audio = message.get("audio") or message.get("voice")
    if audio:
        file_size = audio.get("file_size", 0)
        if file_size > _MAX_FILE_BYTES:
            _send_telegram_message(
                token, chat_id,
                "⚠️ Áudio muito grande (máximo 20 MB). Use o portal Web para arquivos maiores."
            )
            return https_fn.Response("OK", status=200)
        try:
            import base64
            file_meta = _get_telegram_file(token, audio["file_id"])
            file_bytes = _download_telegram_file(token, file_meta["file_path"])
            media_bytes_b64 = base64.b64encode(file_bytes).decode()
            audio_info = {
                "file_id": audio["file_id"],
                "file_size": file_size,
                "mime_type": audio.get("mime_type", "audio/ogg"),
                "duration": audio.get("duration", 0),
            }
        except Exception as e:
            print(f"[Webhook] Audio download error: {e}")
            _send_telegram_message(
                token, chat_id,
                f"⚠️ Não consegui baixar o áudio: {e}\nTente novamente ou envie o texto diretamente."
            )
            return https_fn.Response("OK", status=200)

    # Document / Photo
    doc = message.get("document")
    photos = message.get("photo")
    if not audio_info:
        media_obj = doc or (photos[-1] if photos else None)
        if media_obj:
            file_size = media_obj.get("file_size", 0)
            if file_size > _MAX_FILE_BYTES:
                _send_telegram_message(
                    token, chat_id,
                    "⚠️ Arquivo muito grande (máximo 20 MB). Use o portal Web para arquivos maiores."
                )
                return https_fn.Response("OK", status=200)
            try:
                import base64
                file_meta = _get_telegram_file(token, media_obj["file_id"])
                file_bytes = _download_telegram_file(token, file_meta["file_path"])
                media_bytes_b64 = base64.b64encode(file_bytes).decode()
                file_info = {
                    "file_id": media_obj["file_id"],
                    "file_size": file_size,
                    "file_name": doc.get("file_name", "arquivo") if doc else "foto.jpg",
                    "mime_type": (doc.get("mime_type") if doc else "image/jpeg") or "application/octet-stream",
                }
            except Exception as e:
                print(f"[Webhook] File download error: {e}")

    if not text and not audio_info and not file_info:
        return https_fn.Response("OK", status=200)

    # --- Enfileira no Firestore ---
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "from_user": from_user,
        "audio_info": audio_info,
        "file_info": file_info,
        "media_bytes_b64": media_bytes_b64,
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
    """
    Trigger assíncrono: processa a mensagem enfileirada e envia resposta ao Telegram.
    """
    snap = event.data
    if not snap or not snap.exists:
        return

    data = snap.to_dict() or {}
    if data.get("processed"):
        return

    # Marca como em processamento para evitar double-trigger
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
            token = _get_telegram_token(_get_db())
            if chat_id and token:
                _send_telegram_message(token, chat_id, f"⚠️ Erro interno ao processar mensagem: {e}")
        except Exception:
            pass
