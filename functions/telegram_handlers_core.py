"""Handlers centrais do Telegram: dispatcher de callbacks, pipeline de mensagens
e os 3 entry points do Firebase Functions

Extraido de hermes_core_logic.py (P02, modularizacao por area --
hermes_core_logic.py e telegram_utils.py cresceram alem do teto de ~64000
tokens de saida por chamada de escrita do Argos; ver decisao do Andre em
2026-09-08). Contem o que restou de `_handle_telegram_callback` (setup +
dispatcher, tentando telegram_callbacks_saude/confirmacoes/contatos/sessao em
sequencia) e de `_process_telegram_message` (setup, resposta deterministica via
telegram_message_deterministic, personalidade/historico/midia, ferramentas via
telegram_message_tools, chamada ao Gemini e envio da resposta), alem dos 3
entry points do Firebase (telegramWebhook, on_health_log_red_flag,
on_telegram_inbound) -- ficam juntos aqui porque main.py os importa
diretamente de hermes_core_logic.py para registro de deploy, e manter
_handle_telegram_callback/_process_telegram_message no mesmo arquivo que os
entry points evita import circular com hermes_core_logic.py (que reexporta
estes 5 nomes deste arquivo).

Split puramente mecanico: nenhuma linha de logica foi reescrita. O corpo de
cada callback por area foi substituido por um loop que tenta cada modulo em
sequencia (cada `handle()` devolve True se tratou); o bloco deterministico
virou uma chamada a `try_deterministic_reply(...)`; os 21 closures de
ferramentas do Gemini viraram uma chamada a `build_telegram_tool_closures(...)`.

ATENCAO para mock.patch/mock.patch.object em testes: as funcoes deste arquivo
resolvem nomes livres pelo namespace DESTE modulo (telegram_handlers_core), nao
pelo de hermes_core_logic -- mesmo padrao documentado em telegram_utils.py. Um
`mock.patch.object(hermes_core_logic, "_send_telegram_message", ...)` nao
intercepta uma chamada feita de dentro de uma funcao deste arquivo.
"""
import html
import os
import re
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore, get_app, initialize_app
from firebase_functions import firestore_fn, https_fn, options
from firebase_functions.firestore_fn import Change, DocumentSnapshot, Event

import telegram_callbacks_confirmacoes
import telegram_callbacks_contatos
import telegram_callbacks_saude
import telegram_callbacks_sessao
from telegram_message_deterministic import try_deterministic_reply
from telegram_message_tools import build_telegram_tool_closures
from telegram_utils import (
    _CONFIRM_ACAO_KEYBOARD,
    _CONFIRM_FINANCEIRO_KEYBOARD,
    _CONFIRM_WHATSAPP_KEYBOARD,
    _HEALTH_RED_FLAG_MESSAGE,
    _MAX_FILE_BYTES,
    _MAX_HISTORY_TURNS,
    _answer_callback_query,
    _build_system_instruction_guarded_v2,
    _build_tts_director_instruction,
    _build_web_copilot_telegram_adaptation,
    _cached_acao_snapshot,
    _cached_doc_get,
    _delete_telegram_message,
    _download_telegram_file,
    _ensure_copilot_session,
    _extract_document_text,
    _extract_response_mode,
    _extract_voice_profile,
    _format_context_files_response,
    _format_web_copilot_text_for_telegram,
    _get_allowed_chat_id,
    _get_api_keys,
    _get_db,
    _get_session,
    _get_telegram_file,
    _get_telegram_token,
    _health_red_flag_active,
    _is_context_file_request,
    _is_explicit_web_request,
    _is_internal_hermes_request,
    _is_invalid_argument_error,
    _load_copilot_session_history,
    _load_telegram_media_bytes,
    _perf_log,
    _perf_mark,
    _perf_now_ms,
    _persist_copilot_message,
    _run_gemini_text,
    _run_gemini_tts,
    _run_gemini_turn,
    _run_web_copilot_engine,
    _sanitize_chat_history,
    _save_session,
    _send_contextual_response,
    _send_telegram_document,
    _send_telegram_message,
    _send_telegram_photo,
    _send_telegram_session_message,
    _send_telegram_typing,
    _send_telegram_voice,
    _send_tts_failure_notice_contextual,
    _session_matches_processing_state,
    _store_telegram_media,
    _telegram_action_heartbeat,
    _transcode_audio_for_telegram_voice,
    _transcribe_audio_bytes,
    _upload_telegram_file_to_drive,
    _wrap_pcm_audio_as_wav,
    carregar_areas_tematicas_validas,
)

try:
    get_app()
except ValueError:
    initialize_app()

def _handle_telegram_callback(db, token: str, callback_query: dict) -> "https_fn.Response":
    """Processa um callback_query de botão inline de forma síncrona (sem LLM)."""
    query_id = callback_query.get("id", "")
    data = (callback_query.get("data") or "").strip()
    message = callback_query.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))

    if not chat_id or not data:
        _answer_callback_query(token, query_id)
        return https_fn.Response("OK", status=200)

    allowed = _get_allowed_chat_id()
    if allowed and chat_id != allowed:
        _answer_callback_query(token, query_id)
        return https_fn.Response("OK", status=200)

    try:
        session = _get_session(db, chat_id)
        copilot_session_id = _ensure_copilot_session(
            db,
            chat_id,
            session,
            first_text=f"[Botão Telegram] {data}",
            from_user=callback_query.get("from") or {},
        )
        _save_session(db, chat_id, session)
    except Exception as exc:
        # Nada foi executado ainda neste ponto (nenhuma ação do botão rodou), então é seguro
        # afirmar que não foi registrado e pedir para tentar de novo.
        print(f"[TelegramCallback] Falha ao inicializar sessão para callback '{data}': {exc}")
        _answer_callback_query(token, query_id, "Não consegui registrar. Tente novamente.")
        _send_telegram_message(token, chat_id, "⚠️ Erro interno ao iniciar essa ação. Tente novamente.")
        return https_fn.Response("OK", status=200)

    def _persist_callback_turn(user_label: str, assistant_text: str):
        _persist_copilot_message(db, copilot_session_id, "user", user_label, source="telegram_callback")
        _persist_copilot_message(db, copilot_session_id, "assistant", assistant_text, source="telegram_callback")

    def _pending_web_card(card_type: str) -> dict | None:
        card = (session.get("pending_web_cards") or {}).get(card_type)
        return card if isinstance(card, dict) else None

    def _clear_pending_web_card(card_type: str):
        cards = session.get("pending_web_cards") or {}
        cards.pop(card_type, None)
        if cards:
            session["pending_web_cards"] = cards
        else:
            session.pop("pending_web_cards", None)



    for _mod in (
        telegram_callbacks_saude,
        telegram_callbacks_confirmacoes,
        telegram_callbacks_contatos,
        telegram_callbacks_sessao,
    ):
        if _mod.handle(
            db, token, query_id, chat_id, data, message, session,
            copilot_session_id, _persist_callback_turn, _pending_web_card,
            _clear_pending_web_card,
        ):
            return https_fn.Response("OK", status=200)

    _answer_callback_query(token, query_id)
    return https_fn.Response("OK", status=200)


def _process_telegram_message(db, data: dict):
    """Full processing pipeline for one incoming Telegram message."""
    from google.genai import types
    from tools.busca_grafo import buscar_tarefas
    from tools.busca_acervo import buscar_acervo
    perf_state = {"start_ms": _perf_now_ms(), "_last_ms": _perf_now_ms(), "steps": [], "tool_calls": []}

    chat_id = str(data.get("chat_id", ""))
    text = (data.get("text") or "").strip()
    file_info = data.get("file_info")   # {file_id, file_unique_id, file_size, mime_type, file_name}
    audio_info = data.get("audio_info") # {file_id, file_size, mime_type, duration}
    media_bytes_b64 = data.get("media_bytes_b64")  # base64 of already-downloaded file
    media_storage_path = data.get("media_storage_path")

    if not chat_id:
        return

    keys = _get_api_keys(db)
    gemini_key = keys.get("gemini_api_key")
    token = keys.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    session = _get_session(db, chat_id)
    if not gemini_key or not token:
        _send_telegram_session_message(db, token, chat_id, "⚠️ Configuração incompleta. Contate o administrador.", session=session)
        return
    copilot_session_id = _ensure_copilot_session(
        db,
        chat_id,
        session,
        first_text=text,
        from_user=data.get("from_user") or {},
    )
    _save_session(db, chat_id, session)

    copilot_user_message_persisted = False

    def _persist_turn_to_copilot(
        user_content: str,
        assistant_content: str,
        *,
        tools_used: list | None = None,
        persist_user: bool = True,
    ):
        if persist_user:
            _persist_copilot_message(db, copilot_session_id, "user", user_content, source="telegram")
        _persist_copilot_message(
            db,
            copilot_session_id,
            "assistant",
            assistant_content,
            source="telegram",
            tools_used=tools_used,
        )

    _perf_mark(perf_state, "telegram.bootstrap")
    response_mode, text = _extract_response_mode(text, session)
    voice_profile, text = _extract_voice_profile(text, "masculina")
    print(f"[Core] initial response_mode={response_mode} voice_profile={voice_profile}")
    _perf_mark(perf_state, "telegram.session_load")

    if try_deterministic_reply(
        db, token, chat_id, text, session, gemini_key, response_mode,
        voice_profile, perf_state, _persist_turn_to_copilot,
    ):
        return

    # --- Load copilot personality ---
    try:
        core_doc = _cached_doc_get(db, "system", "copilot_core")
        copilot_core = (core_doc.to_dict() or {}).get("content", "") if core_doc.exists else ""
    except Exception:
        copilot_core = ""
    try:
        soul_doc = _cached_doc_get(db, "system", "copilot_soul")
        copilot_soul = (soul_doc.to_dict() or {}).get("content", "") if soul_doc.exists else ""
    except Exception:
        copilot_soul = ""

    contexto_ativo = session.get("contexto_ativo", "geral")
    request_acao_id = session.get("acao_id")
    # When locked to an action, pull its data snapshot for LLM injection
    acao_snapshot = session.get("acao_context_snapshot") if contexto_ativo == "acao" else None
    if contexto_ativo == "acao" and request_acao_id:
        fresh_snapshot = _cached_acao_snapshot(db, request_acao_id)
        if fresh_snapshot:
            acao_snapshot = fresh_snapshot
            session["acao_context_snapshot"] = fresh_snapshot
            session["acao_titulo"] = fresh_snapshot.get("titulo") or session.get("acao_titulo")
        _perf_mark(perf_state, "telegram.action_snapshot")
    system_instruction = _build_system_instruction_guarded_v2(copilot_core, copilot_soul, contexto_ativo, acao_snapshot)

    # Áreas temáticas válidas: o copiloto só pode SELECIONAR uma existente, nunca inventar.
    _areas_validas = carregar_areas_tematicas_validas(db)
    system_instruction = (
        system_instruction
        + "\n\nÁREAS TEMÁTICAS VÁLIDAS (ao criar ações, escolha EXATAMENTE UMA desta lista; "
        + "NUNCA invente outra): "
        + ", ".join(_areas_validas)
        + ". Se nenhuma se encaixar, use 'GERAL'."
    )

    # --- Restore history (trimmed) — isolated buffer when action-locked ---
    hist_key = "history_acao" if contexto_ativo == "acao" else "history"
    raw_history = session.get(hist_key, [])
    # Keep last N turns (each turn = user + model = 2 items)
    if len(raw_history) > _MAX_HISTORY_TURNS * 2:
        raw_history = raw_history[-((_MAX_HISTORY_TURNS * 2)):]
    telegram_history = _sanitize_chat_history([
        types.Content(role=h["role"], parts=[types.Part(text=p["text"]) for p in h.get("parts", [])])
        for h in raw_history
        if h.get("role") and h.get("parts")
    ], types)
    copilot_history = _load_copilot_session_history(db, copilot_session_id, types)
    history = copilot_history or telegram_history
    if copilot_history:
        _perf_mark(perf_state, "telegram.copilot_history_load")

    # --- Resolve user message parts ---
    user_parts = []
    file_context_text = ""
    telegram_drive_file = None

    # Audio transcription
    if audio_info and (media_bytes_b64 or media_storage_path):
        audio_bytes = _load_telegram_media_bytes(media_bytes_b64, media_storage_path)
        if not audio_bytes:
            user_parts.append(types.Part(text="[Áudio recebido mas o arquivo não foi encontrado para transcrição]"))
            audio_bytes = None
        if not audio_bytes:
            pass
        else:
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
                file_context_text = f"[Transcrição de áudio]: {transcription}"
                user_parts.append(types.Part(text=file_context_text))
            else:
                user_parts.append(types.Part(text="[Áudio recebido mas a transcrição falhou]"))
            _perf_mark(perf_state, "telegram.audio_transcription")

    # File/document
    elif file_info and (media_bytes_b64 or media_storage_path):
        import uuid as _uuid
        import mimetypes
        file_bytes = _load_telegram_media_bytes(media_bytes_b64, media_storage_path)
        if not file_bytes:
            user_parts.append(types.Part(text="[Arquivo recebido mas o conteudo nao foi encontrado]"))
        else:
            fname = file_info.get("file_name") or f"upload_{_uuid.uuid4().hex[:8]}"
            mime = file_info.get("mime_type", "application/octet-stream")

            # Corrigir Mime Type se for genérico ou ausente
            if mime == "application/octet-stream" or not mime:
                guessed, _ = mimetypes.guess_type(fname)
                if guessed:
                    mime = guessed

            # Sobe para o Drive para que o arquivo possa ser processado pelo mesmo
            # motor (askCopilotoHermes) usado pelo Copiloto web — isso garante que o
            # arquivo seja indexado no RAG e vinculado ao contexto/pool_dados da ação,
            # em vez de ficar visível só durante esta troca de mensagens no Telegram.
            if os.environ.get("TELEGRAM_USE_WEB_COPILOT", "1") != "0":
                telegram_drive_file = _upload_telegram_file_to_drive(file_bytes, fname, mime)

            _GEMINI_NATIVE_MIMES = {
                # Images
                'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/heic', 'image/heif',
                # Audio
                'audio/wav', 'audio/mp3', 'audio/mpeg', 'audio/aac', 'audio/flac', 'audio/ogg', 'audio/m4a',
                # Video
                'video/mp4', 'video/mpeg', 'video/quicktime', 'video/webm',
                # Documents
                'application/pdf', 'text/plain', 'text/csv', 'text/html', 'text/markdown',
            }

            if mime in _GEMINI_NATIVE_MIMES:
                user_parts.append(types.Part.from_bytes(data=file_bytes, mime_type=mime))
                user_parts.append(types.Part(text=(
                    f"[Arquivo recebido]: {fname} ({mime})\n"
                    "Analise este arquivo, identifique o que ele mostra e sugira como ele se relaciona ao contexto atual."
                )))
            else:
                # Tenta extrair texto localmente para formatos não suportados nativamente (Excel, Word, PowerPoint, etc.)
                extracted_text = _extract_document_text(file_bytes, fname, mime)
                if extracted_text:
                    user_parts.append(types.Part(text=(
                        f"[Conteúdo extraído do arquivo recebido '{fname}']:\n\n{extracted_text}\n\n"
                        "Analise as informações do documento acima e sugira como elas se relacionam ao contexto atual."
                    )))
                else:
                    # Se não puder extrair e não for nativo, informa o erro de forma limpa
                    user_parts.append(types.Part(text=(
                        f"[Arquivo recebido]: {fname} ({mime})\n"
                        f"⚠️ Nota: O formato deste arquivo não é suportado diretamente e não foi possível extrair seu conteúdo. "
                        "Por favor, envie o conteúdo em formato compatível (PDF, imagens, planilhas CSV ou texto simples)."
                    )))
            _perf_mark(perf_state, "telegram.file_upload")

    # Text
    if text:
        user_parts.append(types.Part(text=text))

    if not user_parts:
        user_parts.append(types.Part(text="[Mensagem sem conteúdo processável]"))

    request_text_for_routing = " ".join(
        p.text for p in user_parts if hasattr(p, "text") and getattr(p, "text", "")
    )
    user_content_for_copilot = "\n\n".join(
        p.text for p in user_parts if hasattr(p, "text") and getattr(p, "text", "")
    ).strip() or text or "[Mensagem sem conteúdo processável]"
    internal_hermes_request = _is_internal_hermes_request(request_text_for_routing)
    explicit_web_request = _is_explicit_web_request(request_text_for_routing)

    # Deterministic path for links/docs in a locked action context. This avoids
    # the model inventing anchor text or Drive URLs when the user asks for files.
    if contexto_ativo == "acao" and acao_snapshot and _is_context_file_request(request_text_for_routing):
        response_text = _format_context_files_response(acao_snapshot, request_text_for_routing)
        _persist_turn_to_copilot(user_content_for_copilot, response_text)
        user_turn = {"role": "user", "parts": [{"text": p.text} for p in user_parts if hasattr(p, "text") and p.text]}
        model_turn = {"role": "model", "parts": [{"text": response_text}]}
        new_history = raw_history + [user_turn, model_turn]
        if len(new_history) > _MAX_HISTORY_TURNS * 2:
            new_history = new_history[-(_MAX_HISTORY_TURNS * 2):]
        session[hist_key] = new_history
        _save_session(db, chat_id, session)
        _send_contextual_response(
            db,
            token,
            chat_id,
            response_text,
            session=session,
            response_mode=response_mode,
            gemini_key=gemini_key,
            voice_profile=voice_profile,
            perf_state=perf_state,
        )
        _perf_log(
            "telegram.request.direct_context_files",
            perf_state,
            {"chat_id": chat_id, "acao_id": request_acao_id},
        )
        return

    if os.environ.get("TELEGRAM_USE_WEB_COPILOT", "1") != "0" and (not file_info or telegram_drive_file):
        processing_msg_id = None
        try:
            _send_telegram_typing(token, chat_id)
            processing_msg_id = _send_telegram_session_message(
                db,
                token,
                chat_id,
                "⏳ <i>Estou processando pelo Copiloto Hermes...</i>",
                session=session,
            )
            _persist_copilot_message(db, copilot_session_id, "user", user_content_for_copilot, source="telegram")
            copilot_user_message_persisted = True
            delegated = _run_web_copilot_engine(
                prompt=request_text_for_routing,
                session_id=copilot_session_id,
                task_id=request_acao_id,
                user_uid=session.get("userId"),
                drive_files=[telegram_drive_file] if telegram_drive_file else None,
            )
            delegated_text = (delegated.get("result") or "").strip()
            if not delegated_text:
                raise RuntimeError("Motor web nao retornou texto.")

            # Intercept markdown images
            images_to_send = re.findall(r'!\[.*?\]\((https?://[^\)]+)\)', delegated_text)
            for img_url in images_to_send:
                _send_telegram_photo(token, chat_id, img_url)

            # Clean up the text before sending to telegram
            clean_delegated_text = re.sub(r'!\[.*?\]\((https?://[^\)]+)\)', '', delegated_text).strip()

            response_text = _format_web_copilot_text_for_telegram(clean_delegated_text)
            card_text, inline_keyboard = _build_web_copilot_telegram_adaptation(session, delegated, delegated_text)
            if card_text:
                response_text = f"{response_text}\n{card_text}"
            if processing_msg_id:
                _delete_telegram_message(token, chat_id, processing_msg_id)
            user_turn = {"role": "user", "parts": [{"text": p.text} for p in user_parts if hasattr(p, "text") and p.text]}
            model_turn = {"role": "model", "parts": [{"text": delegated_text}]}
            new_history = raw_history + [user_turn, model_turn]
            if len(new_history) > _MAX_HISTORY_TURNS * 2:
                new_history = new_history[-(_MAX_HISTORY_TURNS * 2):]
            session[hist_key] = new_history
            _save_session(db, chat_id, session)
            _send_contextual_response(
                db,
                token,
                chat_id,
                response_text,
                session=session,
                response_mode=response_mode,
                gemini_key=gemini_key,
                voice_profile=voice_profile,
                inline_keyboard=inline_keyboard,
                perf_state=perf_state,
            )
            _perf_mark(perf_state, "telegram.web_copilot_response")
            _perf_log(
                "telegram.request.web_copilot_complete",
                perf_state,
                {
                    "chat_id": chat_id,
                    "copilot_session_id": copilot_session_id,
                    "response_mode": response_mode,
                },
            )
            return
        except Exception as web_copilot_err:
            if processing_msg_id:
                _delete_telegram_message(token, chat_id, processing_msg_id)
            print(f"[SessionBridge] Fallback para motor Telegram: {web_copilot_err}")
            _perf_mark(perf_state, "telegram.web_copilot_fallback")

    # --- Memory context ---
    # Skips Firestore read for short/trivial messages (< 4 meaningful words)
    try:
        query_text = text or file_context_text or ""
        _STOPWORDS_MEM = {"de", "a", "o", "que", "e", "do", "da", "em", "um", "uma",
                          "os", "as", "no", "na", "com", "por", "para", "sim", "nao",
                          "ok", "crie", "faça", "faz", "ola", "oi"}
        _meaningful_words = [w for w in query_text.lower().split()
                             if w not in _STOPWORDS_MEM and len(w) > 2]
        if len(_meaningful_words) >= 4:
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
    _perf_mark(perf_state, "telegram.memory_context")
    tools_list = build_telegram_tool_closures(
        db, session, contexto_ativo, acao_snapshot, request_acao_id,
        internal_hermes_request, explicit_web_request, _areas_validas,
    )
    function_map = {fn.__name__: fn for fn in tools_list}
    # --- Gemini call ---
    _send_telegram_typing(token, chat_id)
    processing_msg_id = _send_telegram_session_message(
        db,
        token,
        chat_id,
        "⏳ <i>Estou processando seu pedido, aguarde um minuto...</i>",
        session=session,
    )

    try:
        response_text = _run_gemini_turn(
            db=db,
            gemini_key=gemini_key,
            system_instruction=system_instruction,
            history=history,
            user_message_parts=user_parts,
            tools_list=tools_list,
            function_map=function_map,
            perf_state=perf_state,
            sistema_id_contexto=None,
        )
    except Exception as gemini_err:
        if processing_msg_id:
            _delete_telegram_message(token, chat_id, processing_msg_id)
        import traceback as _tb
        print(f"[Core] Gemini error: {gemini_err}\n{_tb.format_exc()}")
        _perf_log("telegram.request.error", perf_state, {"chat_id": chat_id, "error": str(gemini_err)})
        latest_session = _get_session(db, chat_id)
        detalhe = html.escape(str(gemini_err))[:300]
        if _is_invalid_argument_error(gemini_err):
            aviso = (
                "⚠️ O modelo recusou a requisição (400 INVALID_ARGUMENT). "
                "Tente reenviar em uma frase mais curta; se persistir, peça \"limpar conversa\" para zerar o histórico.\n"
                f"<i>Detalhe técnico: {detalhe}</i>"
            )
        else:
            aviso = f"⚠️ Erro ao processar: {detalhe}"
        _send_telegram_session_message(
            db,
            token,
            chat_id,
            aviso,
            session=latest_session,
        )
        return

    if processing_msg_id:
        _delete_telegram_message(token, chat_id, processing_msg_id)

    # --- Persist history — write to isolated buffer when action-locked ---
    user_turn = {"role": "user", "parts": [{"text": p.text} for p in user_parts if hasattr(p, "text") and p.text]}
    model_turn = {"role": "model", "parts": [{"text": response_text}]}
    new_history = raw_history + [user_turn, model_turn]
    if len(new_history) > _MAX_HISTORY_TURNS * 2:
        new_history = new_history[-(_MAX_HISTORY_TURNS * 2):]
    latest_session = _get_session(db, chat_id)

    # Sincroniza mudanças feitas pelas ferramentas (closures) no objeto 'session' original
    if "pending_confirmations" in session:
        latest_session["pending_confirmations"] = session["pending_confirmations"]
    if "_pending_confirm_type" in session:
        latest_session["_pending_confirm_type"] = session["_pending_confirm_type"]

    if not _session_matches_processing_state(latest_session, contexto_ativo, request_acao_id):
        print(
            f"[Session] Discarding stale response for chat_id={chat_id} "
            f"contexto={contexto_ativo} acao_id={request_acao_id!r}"
        )
        _perf_log(
            "telegram.request.discarded_stale_session",
            perf_state,
            {"chat_id": chat_id, "contexto_ativo": contexto_ativo, "acao_id": request_acao_id},
        )
        return
    latest_session[hist_key] = new_history

    # --- Detecção de propostas pendentes para anexar botões ---
    inline_keyboard = None
    if latest_session.get("_pending_confirm_type") == "acao":
        inline_keyboard = _CONFIRM_ACAO_KEYBOARD
    elif latest_session.get("_pending_confirm_type") == "financeiro":
        inline_keyboard = _CONFIRM_FINANCEIRO_KEYBOARD
    elif latest_session.get("_pending_confirm_type") == "whatsapp":
        inline_keyboard = _CONFIRM_WHATSAPP_KEYBOARD

    # --- Send response ---
    # Text goes out first; session is persisted after so it doesn't block the user.

    # Intercept markdown images
    images_to_send = re.findall(r'!\[.*?\]\((https?://[^\)]+)\)', response_text)
    for img_url in images_to_send:
        _send_telegram_photo(token, chat_id, img_url)

    # Clean up the text before sending to telegram
    clean_response_text = re.sub(r'!\[.*?\]\((https?://[^\)]+)\)', '', response_text).strip()

    _send_telegram_session_message(db, token, chat_id, clean_response_text, session=latest_session, inline_keyboard=inline_keyboard)

    _perf_mark(perf_state, "telegram.text_response")

    tools_used = []
    for call in perf_state.get("tool_calls", []):
        name = call.get("name")
        if name and name not in tools_used:
            tools_used.append(name)
    _persist_turn_to_copilot(
        user_content_for_copilot,
        response_text,
        tools_used=tools_used,
        persist_user=not copilot_user_message_persisted,
    )
    _perf_mark(perf_state, "telegram.copilot_history_persist")

    _save_session(db, chat_id, latest_session)
    _perf_mark(perf_state, "telegram.history_persist")

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
            _perf_mark(perf_state, "telegram.audio_response")
        except Exception as tts_err:
            print(f"[Core] TTS error: {tts_err}")
            _perf_log("telegram.request.tts_error", perf_state, {"chat_id": chat_id, "error": str(tts_err)})
            _send_tts_failure_notice_contextual(db, token, chat_id, session=latest_session)
    _perf_log(
        "telegram.request.complete",
        perf_state,
        {
            "chat_id": chat_id,
            "response_mode": response_mode,
            "history_turns": len(raw_history) // 2,
        },
    )

@https_fn.on_request(
    cors=options.CorsOptions(cors_origins=["https://app.hermes.com", "http://localhost:3001", "http://localhost:5173", "http://localhost:3025", "http://127.0.0.1:3001", "http://127.0.0.1:5173", "http://127.0.0.1:3025"], cors_methods=["GET", "POST"]),
    timeout_sec=10,
    memory=options.MemoryOption.GB_1,
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

    db = _get_db()
    try:
        token = _get_telegram_token(db)
    except Exception:
        return https_fn.Response("OK", status=200)

    # --- Handle callback_query (botões inline — travamento/destravamento de contexto) ---
    callback_query = update.get("callback_query")
    if callback_query:
        try:
            return _handle_telegram_callback(db, token, callback_query)
        except Exception as exc:
            # Rede de segurança para falhas inesperadas que escapem de _handle_telegram_callback
            # (ela já trata o bootstrap da sessão à parte, com uma mensagem afirmando que nada
            # foi registrado). Aqui a ação do botão pode já ter sido aplicada antes da exceção
            # (ex.: exit_context salva a sessão antes de enviar a mensagem final), então evitamos
            # afirmar que "nada foi registrado" para não incentivar o usuário a repetir uma ação
            # que já ocorreu (ex.: confirmar um lançamento financeiro duas vezes).
            print(f"[telegramWebhook] Falha ao processar callback_query: {exc}")
            import traceback
            traceback.print_exc()
            query_id = callback_query.get("id", "")
            chat_id = str(((callback_query.get("message") or {}).get("chat") or {}).get("id", ""))
            try:
                _answer_callback_query(token, query_id, "Ocorreu um erro. Confira o resultado antes de repetir.")
            except Exception:
                pass
            try:
                if chat_id:
                    _send_telegram_message(
                        token, chat_id,
                        f"⚠️ Ocorreu um erro ao concluir essa ação: {exc}\nVerifique se ela já foi aplicada antes de tentar de novo."
                    )
            except Exception:
                pass
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
    media_storage_path = None

    # Audio / Voice
    audio = message.get("audio") or message.get("voice")
    if audio:
        file_size = audio.get("file_size", 0)
        if file_size > _MAX_FILE_BYTES:
            _send_telegram_session_message(
                db,
                token,
                chat_id,
                "⚠️ Áudio muito grande (máximo 20 MB). Use o portal Web para arquivos maiores.",
            )
            return https_fn.Response("OK", status=200)
        try:
            file_meta = _get_telegram_file(token, audio["file_id"])
            file_bytes = _download_telegram_file(token, file_meta["file_path"])
            media_bytes_b64, media_storage_path = _store_telegram_media(
                file_bytes,
                f"audio_{message_id}.ogg",
                audio.get("mime_type", "audio/ogg"),
                chat_id,
            )
            audio_info = {
                "file_id": audio["file_id"],
                "file_size": file_size,
                "mime_type": audio.get("mime_type", "audio/ogg"),
                "duration": audio.get("duration", 0),
            }
        except Exception as e:
            print(f"[Webhook] Audio media prepare error: {e}")
            _send_telegram_session_message(
                db,
                token,
                chat_id,
                f"⚠️ Não consegui preparar o áudio para processamento: {e}\nTente novamente ou envie o texto diretamente.",
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
                _send_telegram_session_message(
                    db,
                    token,
                    chat_id,
                    "⚠️ Arquivo muito grande (máximo 20 MB). Use o portal Web para arquivos maiores.",
                )
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
                    file_bytes,
                    file_info["file_name"],
                    file_info["mime_type"],
                    chat_id,
                )
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
        "media_storage_path": media_storage_path,
        "received_at": firestore.SERVER_TIMESTAMP,
        "processed": False,
    }
    db.collection("telegram_inbound").document(f"{chat_id}_{message_id}").set(payload)

    return https_fn.Response("OK", status=200)

@firestore_fn.on_document_written(document="health_exercise_logs/{date}")
def on_health_log_red_flag(event: Event[Change[DocumentSnapshot]]) -> None:
    """Envia o alerta de sinais de alerta assim que um registro diário (painel ou
    Telegram) passa a atender a uma das condições de risco.

    Dois guards distintos, para dois problemas distintos:
    1. Transição before->after: evita reenviar quando o campo de risco já estava
       ativo antes desta escrita (ex.: usuário edita outro campo no mesmo dia).
    2. Claim atômico em `sentAlerts`: Cloud Functions gen2 tem entrega "at-least-once"
       — o mesmo evento pode ser reprocessado. Sem uma reivindicação atômica *antes*
       de enviar, duas execuções do mesmo evento passam pelo guard 1 e ambas
       enviam. `create()` só é bem-sucedido para a primeira; a segunda recebe
       AlreadyExists e para ali, antes de tocar no Telegram.
    """
    if not event.data or not event.data.after or not event.data.after.exists:
        return
    after = event.data.after.to_dict() or {}
    before = event.data.before.to_dict() if event.data.before and event.data.before.exists else {}

    now_active = _health_red_flag_active(after)
    was_active = _health_red_flag_active(before)
    if not now_active or (now_active and was_active):
        return

    date_id = event.params.get("date", "")
    db = _get_db()

    claim_ref = db.collection("sentAlerts").document(f"{date_id}_redFlag")
    try:
        claim_ref.create({
            "type": "health_red_flag",
            "date": date_id,
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
        })
    except Exception as exc:
        print(f"[HealthRedFlag] Claim para {date_id} já existente (redelivery) ou falhou: {exc}")
        return

    chat_id = _get_allowed_chat_id()
    if not chat_id:
        keys = _cached_doc_get(db, "system", "api_keys").to_dict() or {}
        chat_id = keys.get("telegram_chat_id") or keys.get("allowed_telegram_chat_id")
    if not chat_id:
        print("[HealthRedFlag] Nenhum chat_id do Telegram configurado.")
        return

    token = _get_telegram_token(db)
    _send_telegram_message(token, chat_id, _HEALTH_RED_FLAG_MESSAGE)

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
        if not data.get("callback_action"):
            _process_telegram_message(db, data)
    except Exception as e:
        print(f"[on_telegram_inbound] Unhandled error: {e}")
        import traceback
        traceback.print_exc()
        snap.reference.update({"error": str(e)})
        try:
            chat_id = data.get("chat_id")
            db = _get_db()
            token = _get_telegram_token(db)
            if chat_id and token:
                _send_telegram_session_message(
                    db,
                    token,
                    chat_id,
                    f"⚠️ Erro interno ao processar mensagem: {e}",
                )
        except Exception:
            pass
