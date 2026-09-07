"""
Hermes Core Logic — Telegram Integration
Webhook receiver + Firestore-triggered async processor.
"""
import copy
import json
import html
import os
import re
import base64
import tempfile
import threading
import time
import unicodedata
import wave
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Optional

import requests as _requests
from firebase_admin import firestore, get_app, initialize_app, storage
from firebase_functions import firestore_fn, https_fn, options
from firebase_functions.firestore_fn import Event, Change, DocumentSnapshot
from google.cloud.firestore_v1 import DocumentReference
from gemini_cost_controls import (
    GEMINI_BALANCED_MODEL,
    GEMINI_TRANSCRIPTION_MODEL,
    GEMINI_TTS_MODEL,
    generate_content_logged,
    send_message_logged,
)

try:
    get_app()
except ValueError:
    initialize_app()


# Reexporta tudo que foi extraído para telegram_utils.py (P02 sub-entrega
# 6/N->9/N), só por compatibilidade de atributo (`hermes_core_logic.<nome>`
# continua existindo). ATENÇÃO ao escrever mock.patch/mock.patch.object: isto
# NÃO redireciona uma chamada de nome livre feita de dentro de uma função que
# mora em telegram_utils.py -- essa chamada resolve pelo namespace de
# telegram_utils, não pelo daqui. Para interceptar uma chamada interna a um
# destes nomes, mire `telegram_utils.<nome>`, não `hermes_core_logic.<nome>`.
# Detalhe completo e exemplos no docstring de telegram_utils.py.
from telegram_utils import (
    _action_query_terms,
    _answer_callback_query,
    _blob_public_url,
    _build_action_keyboard,
    _build_gemini_tools,
    _build_system_instruction,
    _build_system_instruction_guarded,
    _build_system_instruction_guarded_v2,
    _build_tts_director_instruction,
    _build_web_copilot_telegram_adaptation,
    _cached_acao_snapshot,
    _cached_doc_get,
    _call_web_callable,
    _clean_action_search_query,
    _clear_telegram_inline_keyboard,
    _delete_telegram_message,
    _download_telegram_file,
    _drive_url_from_file,
    _ensure_copilot_session,
    _extract_action_lookup_query,
    _extract_action_search_context_query,
    _extract_document_text,
    _extract_drive_file_id,
    _extract_natural_context_query,
    _extract_response_mode,
    _extract_task_ids_from_text,
    _extract_voice_profile,
    _fetch_acao_snapshot,
    _fetch_actions_by_date,
    _find_latest_copilot_card_message_id,
    _format_action_lookup_results,
    _format_actions_simple_list,
    _format_context_files_response,
    _format_context_locked_message,
    _format_km,
    _format_web_copilot_text_for_telegram,
    _get_allowed_chat_id,
    _get_api_keys,
    _get_db,
    _get_hermes_storage_bucket,
    _get_session,
    _get_telegram_file,
    _get_telegram_token,
    _handle_command,
    _health_entry_source_after_telegram,
    _health_red_flag_active,
    _is_action_context_locked,
    _is_context_file_request,
    _is_explicit_web_request,
    _is_internal_hermes_request,
    _is_invalid_argument_error,
    _is_list_actions_request,
    _is_reset_request,
    _load_copilot_session_history,
    _load_telegram_media_bytes,
    _lock_action_session,
    _merge_inline_keyboards,
    _neutralize_hidden_links,
    _normalize_for_matching,
    _parse_diary_file_note,
    _perf_log,
    _perf_mark,
    _perf_now_ms,
    _persist_copilot_message,
    _requested_date_from_text,
    _required_param_names,
    _resolve_user_id_for_telegram_chat,
    _run_gemini_text,
    _run_gemini_tts,
    _run_gemini_turn,
    _run_web_copilot_engine,
    _safe_telegram_session_id,
    _sanitize_chat_history,
    _sanitize_tool_schema,
    _save_session,
    _search_actions_for_context,
    _select_context_result,
    _send_contextual_response,
    _send_telegram_chat_action,
    _send_telegram_document,
    _send_telegram_message,
    _send_telegram_message_with_keyboard,
    _send_telegram_photo,
    _send_telegram_session_message,
    _send_telegram_typing,
    _send_telegram_voice,
    _send_tts_failure_notice,
    _send_tts_failure_notice_contextual,
    _session_matches_processing_state,
    _set_latest_copilot_card_status,
    _store_telegram_media,
    _summarize_memory_conflict,
    _summarize_pending_batch_reschedule,
    _summarize_pending_edit,
    _telegram_action_heartbeat,
    _thinking_config_for_model,
    _transcode_audio_for_telegram_voice,
    _transcribe_audio_bytes,
    _transcribe_video_bytes,
    _try_register_walk_block,
    _upload_telegram_file_to_drive,
    _upload_to_storage,
    _wrap_pcm_audio_as_wav,
    carregar_areas_tematicas_validas,
    normalizar_area_tematica,
    _ACTION_SEARCH_STOPWORDS,
    _ACTION_SNAPSHOT_CACHE,
    _ACTION_SNAPSHOT_CACHE_TTL,
    _AREAS_VALIDAS_CACHE,
    _AREAS_VALIDAS_TTL,
    _BATCH_EDIT_FIELD_SCHEMA,
    _CONFIRM_ACAO_KEYBOARD,
    _CONFIRM_FINANCEIRO_KEYBOARD,
    _CONFIRM_WHATSAPP_KEYBOARD,
    _COPILOT_SESSION_HISTORY_LIMIT,
    _DEFAULT_MALE_VOICE,
    _DOC_CACHE,
    _DOC_CACHE_TTL,
    _DRIVE_ID_PATTERNS,
    _EXIT_KEYBOARD,
    _HEALTH_RADICULAR_LOCATIONS,
    _HEALTH_RED_FLAG_MESSAGE,
    _HEALTH_THERAPY_MODALITIES,
    _HEALTH_TRIGGER_TYPES,
    _HTML_ANCHOR_RE,
    _MAX_FILE_BYTES,
    _MAX_HISTORY_TURNS,
    _MAX_INLINE_MEDIA_BYTES,
    _MAX_TTS_TRANSCRIPT_CHARS,
    _RESET_CONFIRM_KEYBOARD,
    _SCHEMA_FIELDS_TO_DROP,
    _TELEGRAM_USER_CACHE,
    _TELEGRAM_USER_CACHE_TTL,
    _TEXT_MODEL_ID,
    _TOOL_PARAMETER_OVERRIDES,
    _TTS_MODEL_ID,
    _VIDEO_INLINE_MAX_BYTES,
    _VIDEO_MIME_MAP,
    _VIDEO_TRANSCRIPTION_PROMPT,
    _WALK_FILLER_RE,
    _WALK_KCAL_RE,
    _WALK_MINUTES_RE,
    _WALK_REGISTER_RE,
    _WALK_STEPS_RE,
)


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



    if data.startswith("health_checkin:"):
        parts = data.split(":")
        checkin_date = parts[1] if len(parts) > 1 else ""
        checkin_mode = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", checkin_date):
                raise ValueError("data inválida")
            _answer_callback_query(token, query_id, "Check-in iniciado")
            if checkin_mode == "morning":
                response_text = (
                    "☀️ <b>Check-in da manhã</b>\n\n"
                    "Que nota você dá para a dor nos primeiros minutos depois de levantar da cama, "
                    "antes da caminhada? (0 = sem dor, 10 = pior possível)"
                )
                pain_keyboard = [
                    [{"text": str(n), "callback_data": f"health_mpain:{checkin_date}:{n}"} for n in range(0, 6)],
                    [{"text": str(n), "callback_data": f"health_mpain:{checkin_date}:{n}"} for n in range(6, 11)],
                ]
            else:
                response_text = "🌙 <b>Check-in da noite</b>\n\nComo ficou sua lombar hoje? (0 = sem dor, 10 = pior possível)"
                pain_keyboard = [
                    [{"text": str(n), "callback_data": f"health_pain:{checkin_date}:{n}"} for n in range(0, 6)],
                    [{"text": str(n), "callback_data": f"health_pain:{checkin_date}:{n}"} for n in range(6, 11)],
                ]
            _persist_callback_turn(f"Iniciar check-in ({'manhã' if checkin_mode == 'morning' else 'noite'})", response_text)
            _send_telegram_message_with_keyboard(token, chat_id, response_text, pain_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao iniciar check-in guiado: {exc}")
            _answer_callback_query(token, query_id, "Não consegui iniciar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui iniciar o check-in. Toque no botão novamente.")

    elif data.startswith("health_mpain:"):
        parts = data.split(":")
        mpain_date = parts[1] if len(parts) > 1 else ""
        mpain_raw = parts[2] if len(parts) > 2 else ""
        try:
            mpain_score = max(0, min(10, int(mpain_raw)))
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", mpain_date):
                raise ValueError("data inválida")
            doc_ref = db.collection("health_exercise_logs").document(mpain_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_pain = current_data.get("pain") or {}
            current_pain["morning"] = mpain_score
            current_pain["telegram_checked_at"] = datetime.now(timezone.utc).isoformat()
            doc_ref.set({"pain": current_pain, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, f"Dor ao acordar: {mpain_score}/10")
            response_text = "✅ Dor ao acordar registrada: <b>" + f"{mpain_score}/10</b>. E depois da caminhada, como ficou?"
            _persist_callback_turn(f"Check-in manhã — dor ao acordar: {mpain_score}/10", response_text)
            afterwalk_keyboard = [
                [{"text": str(n), "callback_data": f"health_mafterwalk:{mpain_date}:{n}"} for n in range(0, 6)],
                [{"text": str(n), "callback_data": f"health_mafterwalk:{mpain_date}:{n}"} for n in range(6, 11)],
            ]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, afterwalk_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar dor da manhã: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a dor da manhã. Tente responder novamente.")

    elif data.startswith("health_mafterwalk:"):
        parts = data.split(":")
        afterwalk_date = parts[1] if len(parts) > 1 else ""
        afterwalk_raw = parts[2] if len(parts) > 2 else ""
        try:
            afterwalk_score = max(0, min(10, int(afterwalk_raw)))
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", afterwalk_date):
                raise ValueError("data inválida")
            doc_ref = db.collection("health_exercise_logs").document(afterwalk_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_pain = current_data.get("pain") or {}
            current_pain["afterWalk"] = afterwalk_score
            doc_ref.set({"pain": current_pain, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, f"Dor após a caminhada: {afterwalk_score}/10")
            response_text = f"✅ Dor após a caminhada registrada: <b>{afterwalk_score}/10</b>. Você acordou com dor durante a noite?"
            _persist_callback_turn(f"Check-in manhã — dor após a caminhada: {afterwalk_score}/10", response_text)
            woke_keyboard = [[
                {"text": "Sim", "callback_data": f"health_woke:{afterwalk_date}:sim"},
                {"text": "Não", "callback_data": f"health_woke:{afterwalk_date}:nao"},
            ]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, woke_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar dor após a caminhada: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar essa resposta. Tente novamente.")

    elif data.startswith("health_woke:"):
        parts = data.split(":")
        woke_date = parts[1] if len(parts) > 1 else ""
        woke_raw = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", woke_date):
                raise ValueError("data inválida")
            woke_in_pain = woke_raw == "sim"
            doc_ref = db.collection("health_exercise_logs").document(woke_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            sleep_quality = current_data.get("sleepQuality") or {}
            sleep_quality["wokeInPain"] = woke_in_pain
            doc_ref.set({"sleepQuality": sleep_quality, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, "Registrado")
            response_text = f"✅ Acordou com dor: <b>{'sim' if woke_in_pain else 'não'}</b>. Como foi a qualidade do sono? (1 = péssima, 5 = ótima)"
            _persist_callback_turn(f"Check-in manhã — acordou com dor: {'sim' if woke_in_pain else 'não'}", response_text)
            quality_keyboard = [[{"text": str(n), "callback_data": f"health_sleepq:{woke_date}:{n}"} for n in range(1, 6)]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, quality_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar despertar com dor: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar essa resposta. Tente novamente.")

    elif data.startswith("health_sleepq:"):
        parts = data.split(":")
        sleepq_date = parts[1] if len(parts) > 1 else ""
        sleepq_raw = parts[2] if len(parts) > 2 else ""
        try:
            sleepq_score = max(1, min(5, int(sleepq_raw)))
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", sleepq_date):
                raise ValueError("data inválida")
            doc_ref = db.collection("health_exercise_logs").document(sleepq_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            sleep_quality = current_data.get("sleepQuality") or {}
            sleep_quality["quality"] = sleepq_score
            if "wokeInPain" not in sleep_quality:
                sleep_quality["wokeInPain"] = False
            doc_ref.set({"sleepQuality": sleep_quality, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, f"Sono: {sleepq_score}/5")
            response_text = f"✅ Qualidade do sono: <b>{sleepq_score}/5</b>.\n\n☀️ Check-in da manhã completo! O da noite chega às 19h."
            _persist_callback_turn(f"Check-in manhã — sono: {sleepq_score}/5", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar qualidade do sono: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a qualidade do sono. Tente novamente.")

    elif data.startswith("health_pain:"):
        parts = data.split(":")
        pain_date = parts[1] if len(parts) > 1 else ""
        pain_raw = parts[2] if len(parts) > 2 else ""
        try:
            pain_score = max(0, min(10, int(pain_raw)))
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", pain_date):
                raise ValueError("data inválida")
            doc_ref = db.collection("health_exercise_logs").document(pain_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_pain = current_data.get("pain") or {}
            current_pain["evening"] = pain_score
            current_pain["telegram_checked_at"] = datetime.now(timezone.utc).isoformat()
            doc_ref.set({"pain": current_pain, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, f"Dor registrada: {pain_score}/10")
            response_text = f"✅ Dor registrada: <b>{pain_score}/10</b> em {pain_date}. Onde você sente o sintoma na perna?"
            _persist_callback_turn(f"Check-in lombar: {pain_score}/10", response_text)
            radicular_keyboard = [
                [{"text": label, "callback_data": f"health_radic:{pain_date}:{value}"}]
                for value, label in _HEALTH_RADICULAR_LOCATIONS
            ]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, radicular_keyboard)
            # O alerta de sinal vermelho (dor >= 9) e disparado pelo trigger
            # on_health_log_red_flag ao ver a escrita acima, nao aqui.
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar dor: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar esse check-in lombar. Tente responder novamente.")

    elif data.startswith("health_radic:"):
        parts = data.split(":")
        radic_date = parts[1] if len(parts) > 1 else ""
        radic_location = parts[2] if len(parts) > 2 else ""
        valid_locations = {value for value, _ in _HEALTH_RADICULAR_LOCATIONS}
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", radic_date) or radic_location not in valid_locations:
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(radic_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_radicular = current_data.get("radicular") or {}
            current_radicular["location"] = radic_location
            doc_ref.set({"radicular": current_radicular, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            location_label = dict(_HEALTH_RADICULAR_LOCATIONS).get(radic_location, radic_location)
            _answer_callback_query(token, query_id, f"Sintoma: {location_label}")
            response_text = f"✅ Sintoma na perna: <b>{location_label}</b>. Treino de força hoje?"
            _persist_callback_turn(f"Sintoma radicular: {location_label}", response_text)
            strength_keyboard = [[
                {"text": "Sim", "callback_data": f"health_strength:{radic_date}:sim"},
                {"text": "Não", "callback_data": f"health_strength:{radic_date}:nao"},
            ]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, strength_keyboard)
            # O alerta de sinal vermelho (local == "pe") e disparado pelo trigger
            # on_health_log_red_flag ao ver a escrita acima, nao aqui.
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar sintoma radicular: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar o sintoma. Tente novamente.")

    elif data.startswith("health_strength:"):
        parts = data.split(":")
        strength_date = parts[1] if len(parts) > 1 else ""
        strength_raw = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", strength_date) or strength_raw not in ("sim", "nao"):
                raise ValueError("dados inválidos")
            done = strength_raw == "sim"
            doc_ref = db.collection("health_exercise_logs").document(strength_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_strength = current_data.get("strength") or {}
            current_strength["done"] = done
            doc_ref.set({"strength": current_strength, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, "Treino registrado" if done else "Ok, sem treino hoje")
            response_text = f"✅ Treino de força: <b>{'sim' if done else 'não'}</b>. Fez alguma terapia hoje?"
            _persist_callback_turn(f"Treino de força: {'sim' if done else 'não'}", response_text)
            therapy_keyboard = [
                [{"text": label, "callback_data": f"health_therapy:{strength_date}:{value}"}]
                for value, label in _HEALTH_THERAPY_MODALITIES
            ]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, therapy_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar treino: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar o treino. Tente novamente.")

    elif data.startswith("health_therapy:"):
        parts = data.split(":")
        therapy_date = parts[1] if len(parts) > 1 else ""
        therapy_value = parts[2] if len(parts) > 2 else ""
        valid_therapies = {value for value, _ in _HEALTH_THERAPY_MODALITIES}
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", therapy_date) or therapy_value not in valid_therapies:
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(therapy_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            therapy_list = [] if therapy_value == "nenhuma" else [therapy_value]
            doc_ref.set({"therapy": therapy_list, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            therapy_label = dict(_HEALTH_THERAPY_MODALITIES).get(therapy_value, therapy_value)
            _answer_callback_query(token, query_id, f"Terapia: {therapy_label}")
            response_text = f"✅ Terapia: <b>{therapy_label}</b>. Como foi a alimentação hoje?"
            _persist_callback_turn(f"Modalidade terapêutica: {therapy_label}", response_text)
            diet_keyboard = [[
                {"text": "Sim", "callback_data": f"health_diet:{therapy_date}:sim"},
                {"text": "Parcial", "callback_data": f"health_diet:{therapy_date}:parcial"},
                {"text": "Não", "callback_data": f"health_diet:{therapy_date}:nao"},
            ]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, diet_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar terapia: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a terapia. Tente novamente.")

    elif data.startswith("health_diet:"):
        parts = data.split(":")
        diet_date = parts[1] if len(parts) > 1 else ""
        diet_value = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", diet_date) or diet_value not in ("sim", "parcial", "nao"):
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(diet_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_nutrition = current_data.get("nutrition") or {}
            current_nutrition["plan"] = diet_value
            doc_ref.set({"nutrition": current_nutrition, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, f"Cardápio: {diet_value}")
            response_text = "✅ Alimentação registrada. Bateu a proteína hoje?"
            _persist_callback_turn(f"Aderência alimentar: {diet_value}", response_text)
            protein_keyboard = [[
                {"text": "Sim", "callback_data": f"health_protein:{diet_date}:sim"},
                {"text": "Não", "callback_data": f"health_protein:{diet_date}:nao"},
            ]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, protein_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar alimentação: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a alimentação. Tente novamente.")

    elif data.startswith("health_protein:"):
        parts = data.split(":")
        protein_date = parts[1] if len(parts) > 1 else ""
        protein_value = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", protein_date) or protein_value not in ("sim", "nao"):
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(protein_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            current_nutrition = current_data.get("nutrition") or {}
            current_nutrition["proteinTarget"] = protein_value == "sim"
            doc_ref.set({"nutrition": current_nutrition, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, "Registrado")
            response_text = "✅ Proteína registrada. Medicação de hoje foi igual a de ontem?"
            _persist_callback_turn(f"Proteína batida: {protein_value}", response_text)
            meds_keyboard = [[
                {"text": "Igual a ontem", "callback_data": f"health_meds:{protein_date}:same"},
                {"text": "Nada hoje", "callback_data": f"health_meds:{protein_date}:clear"},
            ]]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, meds_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar proteína: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a proteína. Tente novamente.")

    elif data.startswith("health_meds:"):
        parts = data.split(":")
        meds_date = parts[1] if len(parts) > 1 else ""
        meds_action = parts[2] if len(parts) > 2 else ""
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", meds_date) or meds_action not in ("same", "clear"):
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(meds_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            if meds_action == "same":
                yesterday = (datetime.strptime(meds_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
                yesterday_doc = db.collection("health_exercise_logs").document(yesterday).get()
                yesterday_meds = (yesterday_doc.to_dict() or {}).get("meds") if yesterday_doc.exists else None
                new_meds = yesterday_meds or {"pregabalina": False, "dipirona": 0, "adorlan": 0, "fexofenadina": False}
                meds_summary = "igual a ontem"
            else:
                new_meds = {"pregabalina": False, "dipirona": 0, "adorlan": 0, "fexofenadina": False}
                meds_summary = "nada hoje"
            doc_ref.set({"meds": new_meds, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            _answer_callback_query(token, query_id, "Medicação registrada")
            response_text = f"✅ Medicação: <b>{meds_summary}</b>. Algum evento ou gatilho hoje?"
            _persist_callback_turn(f"Medicação: {meds_summary}", response_text)
            trigger_keyboard = [
                [{"text": label, "callback_data": f"health_trigger:{meds_date}:{value}"}]
                for value, label in _HEALTH_TRIGGER_TYPES
            ]
            _send_telegram_message_with_keyboard(token, chat_id, response_text, trigger_keyboard)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar medicação: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar a medicação. Tente novamente. Edite pelo painel se preferir.")

    elif data.startswith("health_trigger:"):
        parts = data.split(":")
        trigger_date = parts[1] if len(parts) > 1 else ""
        trigger_value = parts[2] if len(parts) > 2 else ""
        valid_triggers = {value for value, _ in _HEALTH_TRIGGER_TYPES}
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", trigger_date) or trigger_value not in valid_triggers:
                raise ValueError("dados inválidos")
            doc_ref = db.collection("health_exercise_logs").document(trigger_date)
            current = doc_ref.get()
            current_data = (current.to_dict() or {}) if current.exists else {}
            trigger_types = [] if trigger_value == "nenhum" else [trigger_value]
            current_triggers = current_data.get("triggers") or {}
            current_triggers["types"] = trigger_types
            doc_ref.set({"triggers": current_triggers, "entrySource": _health_entry_source_after_telegram(current_data)}, merge=True)
            trigger_label = dict(_HEALTH_TRIGGER_TYPES).get(trigger_value, trigger_value)
            _answer_callback_query(token, query_id, "Registrado")
            response_text = f"✅ Check-in lombar completo para {trigger_date}. Gatilho: <b>{trigger_label}</b>.\n\nPara adicionar uma observação, use o painel."
            _persist_callback_turn(f"Evento/gatilho: {trigger_label}", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as exc:
            print(f"[HealthCheckin] Falha ao registrar gatilho: {exc}")
            _answer_callback_query(token, query_id, "Não consegui registrar.")
            _send_telegram_message(token, chat_id, "⚠️ Não consegui registrar o gatilho. Tente novamente.")

    elif data.startswith("ai_notif:"):
        parts = data.split(":")
        notif_id = parts[1] if len(parts) > 1 else ""
        action = parts[2] if len(parts) > 2 else ""
        if not notif_id or action not in ("useful", "dismiss"):
            _answer_callback_query(token, query_id)
        else:
            try:
                doc_ref = db.collection("scheduled_notifications").document(notif_id)
                doc_ref.set(
                    {
                        "feedback": "useful" if action == "useful" else "dismissed",
                        "feedback_at": datetime.now(timezone.utc).isoformat(),
                    },
                    merge=True,
                )
                toast = "Marcado como útil, obrigado!" if action == "useful" else "Ok, vou evitar repetir isso."
                _answer_callback_query(token, query_id, toast)
                response_text = (
                    "👍 Feedback registrado: notificação útil."
                    if action == "useful"
                    else "👎 Feedback registrado: notificação dispensada."
                )
                _persist_callback_turn(f"Feedback IA ({notif_id}): {action}", response_text)
            except Exception as exc:
                print(f"[AINotifications] Falha ao registrar feedback de {notif_id}: {exc}")
                _answer_callback_query(token, query_id, "Não consegui registrar o feedback.")

    elif data.startswith("reagendamento_lote:"):
        parts = data.split(":")
        proposta_id = parts[1] if len(parts) > 1 else ""
        action = parts[2] if len(parts) > 2 else ""
        if not proposta_id or action not in ("aplicar", "descartar"):
            _answer_callback_query(token, query_id)
        else:
            try:
                doc_ref = db.collection("reagendamentos_propostos").document(proposta_id)
                doc_snap = doc_ref.get()
                if not doc_snap.exists:
                    _answer_callback_query(token, query_id, "Proposta não encontrada.")
                else:
                    proposta = doc_snap.to_dict() or {}
                    status_atual = proposta.get("status")
                    if status_atual != "pending":
                        _answer_callback_query(token, query_id, f"Proposta já processada ({status_atual}).")
                    elif action == "descartar":
                        doc_ref.set(
                            {
                                "status": "descartado",
                                "descartado_em": datetime.now(timezone.utc).isoformat(),
                            },
                            merge=True,
                        )
                        _answer_callback_query(token, query_id, "Proposta descartada.")
                        response_text = "❌ Proposta de reagendamento em lote descartada."
                        _persist_callback_turn(f"Reagendamento lote ({proposta_id}): descartar", response_text)
                        _send_telegram_message(token, chat_id, response_text)
                    elif action == "aplicar":
                        items = proposta.get("items") or []
                        justificativa = (
                            proposta.get("justificativa")
                            or "Reagendamento em lote semanal via aprovação no Telegram."
                        )

                        import main
                        from tools.callable_bridge import invoke_callable

                        resultado = invoke_callable(
                            main.confirmarReagendamentoEmLote,
                            {"items": items, "justificativa": justificativa},
                            uid=None,
                            token={"uid": None},
                        )
                        doc_ref.set(
                            {
                                "status": "aplicado",
                                "aplicado_em": datetime.now(timezone.utc).isoformat(),
                                "resultado_aplicacao": resultado,
                            },
                            merge=True,
                        )
                        _answer_callback_query(token, query_id, f"{len(items)} ações reagendadas!")
                        response_text = f"✅ Reagendamento em lote aplicado com sucesso para {len(items)} ação(ões)."
                        _persist_callback_turn(f"Reagendamento lote ({proposta_id}): aplicar", response_text)
                        _send_telegram_message(token, chat_id, response_text)
            except Exception as exc:
                print(f"[ReagendamentoLote] Falha ao processar callback de {proposta_id}: {exc}")
                _answer_callback_query(token, query_id, "Erro ao processar reagendamento.")

    elif data == "exit_context":
        acao_titulo = session.get("acao_titulo") or "anterior"
        response_text = f"✅ Saindo do contexto <b>{acao_titulo}</b>. Voltando ao modo geral."
        _answer_callback_query(token, query_id, "Contexto liberado.")
        session["contexto_ativo"] = "geral"
        session["acao_id"] = None
        session["acao_titulo"] = None
        session["acao_context_snapshot"] = None
        session["history_acao"] = []
        _save_session(db, chat_id, session)
        _persist_callback_turn("Botão: Sair do Contexto", response_text)
        _send_telegram_message(
            token, chat_id,
            response_text
        )

    elif data.startswith("lock:"):
        task_id = data[len("lock:"):]
        _answer_callback_query(token, query_id, "Carregando contexto...")
        snapshot = _cached_acao_snapshot(db, task_id)
        if not snapshot:
            response_text = f"⚠️ Ação <code>{task_id}</code> não encontrada."
            _persist_callback_turn(f"Botão: entrar no contexto task:{task_id}", response_text)
            _send_telegram_session_message(
                db,
                token, chat_id,
                response_text
            )
            return https_fn.Response("OK", status=200)

        titulo = snapshot.get("titulo", task_id)
        response_text = (
            f"🔒 <b>[Contexto: {titulo}]</b>\n\n"
            f"Contexto trancado. Estou focado exclusivamente nesta ação.\n"
            f"Histórico anterior isolado — nenhum ruído de conversas passadas.\n\n"
            f"Use <i>Sair do Contexto</i> para retornar ao modo geral."
        )
        session["contexto_ativo"] = "acao"
        session["acao_id"] = task_id
        session["acao_titulo"] = titulo
        session["acao_context_snapshot"] = snapshot
        session["history_acao"] = []
        _save_session(db, chat_id, session)
        _persist_callback_turn(f"Botão: entrar no contexto task:{task_id}", response_text)

        _send_telegram_message_with_keyboard(
            token, chat_id,
            response_text,
            _EXIT_KEYBOARD,
        )

    elif data == "reset_session_confirm":
        ctx = session.get("contexto_ativo", "geral")
        hist_key = "history_acao" if ctx == "acao" else "history"
        session[hist_key] = []
        _save_session(db, chat_id, session)
        _answer_callback_query(token, query_id, "Histórico limpo!")
        response_text = f"✅ Histórico do contexto <b>{ctx}</b> foi limpo. Podemos recomeçar!"
        _persist_callback_turn("Botão: confirmar limpeza de histórico", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data == "reset_session_cancel":
        _answer_callback_query(token, query_id, "Ação cancelada.")
        response_text = "Ok, mantive o histórico atual."
        _persist_callback_turn("Botão: cancelar limpeza de histórico", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data == "webedit_confirm":
        _answer_callback_query(token, query_id, "Aplicando edição...")
        pending = _pending_web_card("edit")
        if not pending:
            response_text = "Não encontrei uma edição pendente para confirmar."
            _persist_callback_turn("Botão: confirmar edição", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return https_fn.Response("OK", status=200)
        try:
            alteracoes = {}
            for campo, change in (pending.get("alteracoes") or {}).items():
                change = change if isinstance(change, dict) else {}
                alteracoes[campo] = change.get("novo_raw") if "novo_raw" in change else change.get("novo")
            message_id = _find_latest_copilot_card_message_id(db, copilot_session_id, "pendingEdit")
            result = _call_web_callable(
                function_name="confirmarEdicaoAcao",
                data={
                    "sessionId": copilot_session_id,
                    "messageId": message_id,
                    "taskId": pending.get("task_id"),
                    "alteracoes": alteracoes,
                    "snapshotTs": pending.get("snapshot_ts"),
                },
                user_uid=session.get("userId"),
                timeout=60,
            )
            _clear_pending_web_card("edit")
            _save_session(db, chat_id, session)
            status = result.get("status") or "completed"
            response_text = "Edição confirmada e aplicada no Hermes." if status == "completed" else (result.get("message") or f"Edição retornou status: {status}")
            _persist_callback_turn("Botão: confirmar edição", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as exc:
            response_text = f"Erro ao confirmar edição: {exc}"
            _persist_callback_turn("Botão: confirmar edição", response_text)
            _send_telegram_message(token, chat_id, response_text)

    elif data == "webedit_cancel":
        _answer_callback_query(token, query_id, "Edição cancelada.")
        _clear_pending_web_card("edit")
        _set_latest_copilot_card_status(db, copilot_session_id, "pendingEdit", "cancelled")
        _save_session(db, chat_id, session)
        response_text = "Edição cancelada. Nada foi alterado."
        _persist_callback_turn("Botão: cancelar edição", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data == "webbatch_confirm":
        _answer_callback_query(token, query_id, "Reagendando...")
        pending = _pending_web_card("batch_reschedule")
        if not pending:
            response_text = "Não encontrei um reagendamento em lote pendente para confirmar."
            _persist_callback_turn("Botão: confirmar reagendamento em lote", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return https_fn.Response("OK", status=200)
        try:
            message_id = _find_latest_copilot_card_message_id(db, copilot_session_id, "pendingBatchReschedule")
            result = _call_web_callable(
                function_name="confirmarReagendamentoEmLote",
                data={
                    "sessionId": copilot_session_id,
                    "messageId": message_id,
                    "items": pending.get("items") or [],
                    "justificativa": pending.get("justificativa") or "Reagendamento em lote via Telegram.",
                },
                user_uid=session.get("userId"),
                timeout=60,
            )
            _clear_pending_web_card("batch_reschedule")
            _save_session(db, chat_id, session)
            response_text = f"Reagendamento confirmado. Ações atualizadas: {result.get('count', 0)}."
            _persist_callback_turn("Botão: confirmar reagendamento em lote", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as exc:
            response_text = f"Erro ao confirmar reagendamento: {exc}"
            _persist_callback_turn("Botão: confirmar reagendamento em lote", response_text)
            _send_telegram_message(token, chat_id, response_text)

    elif data == "webbatch_cancel":
        _answer_callback_query(token, query_id, "Reagendamento cancelado.")
        _clear_pending_web_card("batch_reschedule")
        _set_latest_copilot_card_status(db, copilot_session_id, "pendingBatchReschedule", "cancelled")
        _save_session(db, chat_id, session)
        response_text = "Reagendamento em lote cancelado. Nada foi alterado."
        _persist_callback_turn("Botão: cancelar reagendamento em lote", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data in ("webmem_keep_old", "webmem_keep_new"):
        decision = "manter_existente" if data == "webmem_keep_old" else "substituir_pelo_novo"
        _answer_callback_query(token, query_id, "Resolvendo memória...")
        conflict = _pending_web_card("memory_conflict")
        if not conflict:
            response_text = "Não encontrei um conflito de memória pendente."
            _persist_callback_turn("Botão: resolver conflito de memória", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return https_fn.Response("OK", status=200)
        try:
            message_id = _find_latest_copilot_card_message_id(db, copilot_session_id, "pendingMemoryConflict")
            result = _call_web_callable(
                function_name="confirmarConflitoMemoria",
                data={
                    "sessionId": copilot_session_id,
                    "messageId": message_id,
                    "memoriaId": conflict.get("memoria_id") or conflict.get("memory_id") or conflict.get("id"),
                    "decisao": decision,
                    "fatoAtualizado": conflict.get("proposed_text") or "",
                    "categoria": conflict.get("categoria") or "fato_isolado",
                },
                user_uid=session.get("userId"),
                timeout=60,
            )
            _clear_pending_web_card("memory_conflict")
            _save_session(db, chat_id, session)
            response_text = f"Conflito de memória resolvido: {result.get('decision', decision)}."
            _persist_callback_turn("Botão: resolver conflito de memória", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as exc:
            response_text = f"Erro ao resolver conflito de memória: {exc}"
            _persist_callback_turn("Botão: resolver conflito de memória", response_text)
            _send_telegram_message(token, chat_id, response_text)

    elif data == "confirm_acao":
        _answer_callback_query(token, query_id, "Processando registro...")
        # Remove o teclado inline imediatamente para que um duplo toque acidental não
        # reenvie o mesmo callback_query enquanto esta chamada ainda está em andamento.
        _clear_telegram_inline_keyboard(token, chat_id, message.get("message_id"))
        pending = session.get("pending_confirmations", {}).get("acao")
        if not pending:
            response_text = "⚠️ Nenhuma ação pendente de confirmação encontrada ou o prazo expirou."
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return https_fn.Response("OK", status=200)

        # Reivindicação atômica (título, data, horário) — evita criar a mesma ação mais de
        # uma vez quando o Telegram reenvia o mesmo callback_query (timeout de webhook) ou
        # o usuário toca duas vezes antes do teclado acima ser removido. Ver bug de eventos
        # duplicados na agenda / claim_action_dedup_slot em main.py.
        from main import claim_action_dedup_slot, store_action_dedup_result, release_action_dedup_slot
        _dedup_status, _dedup_task_id = claim_action_dedup_slot(
            db, pending.get("titulo"), pending.get("data_limite"), pending.get("horario_inicio")
        )
        if _dedup_status == "duplicate":
            response_text = f"✅ Essa ação já havia sido registrada.\nID: <code>{_dedup_task_id}</code>\nTítulo: {pending.get('titulo')}"
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)
            session.get("pending_confirmations", {}).pop("acao", None)
            if session.get("_pending_confirm_type") == "acao":
                session.pop("_pending_confirm_type", None)
            _save_session(db, chat_id, session)
            return https_fn.Response("OK", status=200)
        if _dedup_status == "pending":
            response_text = "⏳ Essa ação já está sendo registrada por outra chamada. Verifique a lista de ações em alguns segundos."
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return https_fn.Response("OK", status=200)

        # Executa a criação (lógica de criar_acao_no_sistema)
        try:
            import uuid as _uuid
            now_iso = datetime.now(timezone.utc).isoformat()
            task_id = str(_uuid.uuid4())[:20]

            # Reuso da lógica de reagendamento se houver horários
            try:
                from main import get_calendar_service, get_target_calendar_id
                import hermes_calendar_tools as hc_tools
                c_service = get_calendar_service()
                c_id = get_target_calendar_id(db)
                if c_service and c_id and pending.get("horario_inicio") and pending.get("horario_fim"):
                    hc_tools.reagendar_acoes_hermes(db, c_service, c_id, pending.get("data_limite"), pending.get("horario_inicio"), pending.get("horario_fim"))
            except Exception: pass

            import subtarefas as _sub
            plano_convertido = _sub.converter_plano(pending.get("plano_acao"))

            doc = {
                "id": task_id,
                "titulo": pending["titulo"].strip(),
                "descricao": pending.get("descricao") or "",
                "area_tematica": pending.get("area_tematica") or "GERAL",
                "data_limite": pending.get("data_limite"),
                "prazo_final": pending.get("prazo_final"),
                "horario_inicio": pending.get("horario_inicio"),
                "horario_fim": pending.get("horario_fim"),
                "tipo_acao": pending.get("tipo_acao") or "fast",
                "tags": pending.get("tags") or [],
                "notas": pending.get("notas") or "",
                "plano_acao": plano_convertido,
                "status": "em andamento",
                "criado_em": now_iso,
                "data_criacao": now_iso,
                "origem_ingestao": "telegram",
                "sync_status": "new",
            }
            db.collection("tarefas").document(task_id).set(doc)
            store_action_dedup_result(db, pending.get("titulo"), pending.get("data_limite"), pending.get("horario_inicio"), task_id)

            # Limpa pendência
            session.get("pending_confirmations", {}).pop("acao", None)
            if session.get("_pending_confirm_type") == "acao":
                session.pop("_pending_confirm_type", None)
            _save_session(db, chat_id, session)

            response_text = f"✅ <b>Ação registrada com sucesso!</b>\nID: <code>{task_id}</code>\nTítulo: {pending['titulo']}"
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as e:
            release_action_dedup_slot(db, pending.get("titulo"), pending.get("data_limite"), pending.get("horario_inicio"))
            response_text = f"❌ Erro ao registrar ação: {e}"
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)

    elif data == "cancel_acao":
        _answer_callback_query(token, query_id, "Cancelado.")
        session.get("pending_confirmations", {}).pop("acao", None)
        if session.get("_pending_confirm_type") == "acao":
            session.pop("_pending_confirm_type", None)
        _save_session(db, chat_id, session)
        response_text = "❌ Registro de ação cancelado pelo usuário."
        _persist_callback_turn("Botão: cancelar registro de ação", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data == "confirm_financeiro":
        _answer_callback_query(token, query_id, "Processando lançamento...")
        pending = session.get("pending_confirmations", {}).get("financeiro")
        if not pending:
            response_text = "⚠️ Nenhum lançamento financeiro pendente."
            _persist_callback_turn("Botão: confirmar lançamento financeiro", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return https_fn.Response("OK", status=200)

        try:
            from tools.telegram_extended import execute
            res = execute("registrar_item_financeiro_v2", pending, db)

            session.get("pending_confirmations", {}).pop("financeiro", None)
            if session.get("_pending_confirm_type") == "financeiro":
                session.pop("_pending_confirm_type", None)
            _save_session(db, chat_id, session)

            response_text = f"✅ <b>Lançamento financeiro realizado!</b>\n{res}"
            _persist_callback_turn("Botão: confirmar lançamento financeiro", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as e:
            response_text = f"❌ Erro no financeiro: {e}"
            _persist_callback_turn("Botão: confirmar lançamento financeiro", response_text)
            _send_telegram_message(token, chat_id, response_text)

    elif data == "cancel_financeiro":
        _answer_callback_query(token, query_id, "Cancelado.")
        session.get("pending_confirmations", {}).pop("financeiro", None)
        if session.get("_pending_confirm_type") == "financeiro":
            session.pop("_pending_confirm_type", None)
        _save_session(db, chat_id, session)
        response_text = "❌ Lançamento financeiro descartado."
        _persist_callback_turn("Botão: cancelar lançamento financeiro", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data == "confirm_whatsapp":
        _answer_callback_query(token, query_id, "Enfileirando mensagem...")
        pending = session.get("pending_confirmations", {}).get("whatsapp")
        if not pending:
            response_text = "⚠️ Nenhuma mensagem de WhatsApp pendente."
            _persist_callback_turn("Botão: confirmar WhatsApp", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return https_fn.Response("OK", status=200)

        try:
            from tools.schedule_whatsapp_message import schedule_whatsapp_message as _schedule_whatsapp
            res = _schedule_whatsapp(
                db,
                pending.get("contact_number") or "",
                pending.get("message") or "",
                pending.get("scheduled_time") or "",
            )

            session.get("pending_confirmations", {}).pop("whatsapp", None)
            if session.get("_pending_confirm_type") == "whatsapp":
                session.pop("_pending_confirm_type", None)
            _save_session(db, chat_id, session)

            response_text = f"✅ <b>WhatsApp confirmado.</b>\n{html.escape(str(res))}"
            _persist_callback_turn("Botão: confirmar WhatsApp", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as e:
            response_text = f"❌ Erro ao enfileirar WhatsApp: {html.escape(str(e))}"
            _persist_callback_turn("Botão: confirmar WhatsApp", response_text)
            _send_telegram_message(token, chat_id, response_text)

    elif data == "cancel_whatsapp":
        _answer_callback_query(token, query_id, "Cancelado.")
        session.get("pending_confirmations", {}).pop("whatsapp", None)
        if session.get("_pending_confirm_type") == "whatsapp":
            session.pop("_pending_confirm_type", None)
        _save_session(db, chat_id, session)
        response_text = "❌ Envio de WhatsApp descartado."
        _persist_callback_turn("Botão: cancelar WhatsApp", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data.startswith("wa_cancel:"):
        doc_id = data.split("wa_cancel:")[1].strip()
        _answer_callback_query(token, query_id, "Agendamento cancelado.")
        try:
            if doc_id:
                db.collection("whatsapp_outbox").document(doc_id).update({
                    "status": "canceled",
                    "canceled_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
        except Exception as exc:
            print(f"[TelegramCallback] Erro ao cancelar WhatsApp agendado {doc_id}: {exc}")

        response_text = "❌ <b>Envio de WhatsApp agendado foi cancelado.</b>"
        _persist_callback_turn("Botão: cancelar WhatsApp agendado", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data.startswith("merge_confirm:"):
        req_id = data.split("merge_confirm:")[1].strip()
        req_doc = db.collection("contact_merge_requests").document(req_id).get()
        if not req_doc.exists:
            _answer_callback_query(token, query_id, "Solicitação não encontrada.")
        else:
            req_data = req_doc.to_dict() or {}
            primary_id = req_data.get("primary_id")
            secondary_id = req_data.get("secondary_id")

            from contact_merge_utils import execute_contact_merge
            res = execute_contact_merge(db, primary_id, [secondary_id])

            if res.get("success"):
                db.collection("contact_merge_requests").document(req_id).update({
                    "status": "merged",
                    "merged_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
                _answer_callback_query(token, query_id, "Contatos mesclados!")
                msg = f"✅ <b>Contatos mesclados com sucesso!</b>\nOs perfis <b>{html.escape(str(req_data.get('secondary_name', '')))}</b> e <b>{html.escape(str(req_data.get('primary_name', '')))}</b> foram unificados."
            else:
                _answer_callback_query(token, query_id, "Erro ao mesclar.")
                msg = f"❌ Erro ao mesclar contatos: {html.escape(str(res.get('error', '')))}"

            _persist_callback_turn("Botão: confirmar mesclagem de contatos", msg)
            _send_telegram_message(token, chat_id, msg)

    elif data.startswith("merge_ignore:"):
        req_id = data.split("merge_ignore:")[1].strip()
        req_doc = db.collection("contact_merge_requests").document(req_id).get()
        if not req_doc.exists:
            _answer_callback_query(token, query_id, "Solicitação não encontrada.")
        else:
            req_data = req_doc.to_dict() or {}
            pair_key = req_data.get("pair_key")
            if pair_key:
                db.collection("ignored_contact_merges").add({
                    "pair_key": pair_key,
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "reason": req_data.get("reason", "")
                })
            db.collection("contact_merge_requests").document(req_id).update({
                "status": "ignored",
                "ignored_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            _answer_callback_query(token, query_id, "Sugestão ignorada.")
            msg = f"❌ <b>Sugestão de mesclagem ignorada.</b>\nEsta combinação de contatos não será mais sugerida."
            _persist_callback_turn("Botão: ignorar mesclagem de contatos", msg)
            _send_telegram_message(token, chat_id, msg)

    elif data.startswith("emlink:"):
        parts = data.split(":")
        msg_id = parts[1] if len(parts) > 1 else ""
        action = parts[2] if len(parts) > 2 else ""
        suggestion_ref = db.collection("email_action_suggestions").document(msg_id) if msg_id else None
        suggestion_doc = suggestion_ref.get() if suggestion_ref else None

        if not msg_id or action not in ("ok", "on", "no", "mut") or not suggestion_doc or not suggestion_doc.exists:
            _answer_callback_query(token, query_id, "Sugestão não encontrada.")
        else:
            suggestion_data = suggestion_doc.to_dict() or {}
            if suggestion_data.get("status") != "pending":
                _answer_callback_query(token, query_id, "Essa sugestão já foi resolvida ou expirou.")
            elif action == "no":
                suggestion_ref.update({
                    "status": "dismissed",
                    "decided_at": datetime.now(timezone.utc).isoformat(),
                })
                _answer_callback_query(token, query_id, "Ok, ignorado.")
                msg = "❌ <b>Sugestão de vínculo de e-mail ignorada.</b>"
                _persist_callback_turn("Botão: ignorar vínculo de e-mail", msg)
                _send_telegram_message(token, chat_id, msg)
            else:
                from email_action_linker import apply_suggestion

                apply_mutations = action == "mut"
                # "mut" (botão "Registrar + aplicar mudanças") também reativa quando a
                # sugestão já indicava isso — evita exigir duas confirmações separadas
                # quando registrar, reativar e aplicar as mutações fazem sentido juntos.
                reactivate = action == "on" or (apply_mutations and bool(suggestion_data.get("reativar_sugerido")))
                # apply_suggestion grava a nota no diário, opcionalmente aplica as
                # mutações propostas (plano de ação/prazo/lembrete) e marca a sugestão
                # como aplicada numa única transação Firestore (evita duplicar a nota se
                # uma etapa falhar a meio, e recusa aplicar duas vezes a mesma sugestão
                # numa corrida).
                applied = apply_suggestion(db, msg_id, suggestion_data, reactivate=reactivate, apply_mutations=apply_mutations)
                if not applied:
                    _answer_callback_query(token, query_id, "Não foi possível registrar.")
                    msg = "⚠️ Não foi possível registrar — a sugestão já foi decidida em outro lugar ou a ação não foi encontrada."
                    _persist_callback_turn("Botão: registrar vínculo de e-mail", msg)
                    _send_telegram_message(token, chat_id, msg)
                else:
                    task_titulo = suggestion_data.get("task_titulo") or "(ação)"
                    _answer_callback_query(token, query_id, "Registrado no diário de bordo!")
                    if apply_mutations:
                        msg = f"📋 <b>Registrado no diário e ação atualizada:</b>\n{html.escape(str(task_titulo))}"
                    elif reactivate:
                        msg = f"🔄 <b>Registrado no diário e ação reativada:</b>\n{html.escape(str(task_titulo))}"
                    else:
                        msg = f"✅ <b>Registrado no diário de bordo:</b>\n{html.escape(str(task_titulo))}"
                    _persist_callback_turn("Botão: registrar vínculo de e-mail", msg)
                    _send_telegram_message(token, chat_id, msg)

    elif data.startswith("diary_edit:"):
        diary_date = data.split("diary_edit:")[1].strip()
        session["pending_diary_edit"] = diary_date
        _save_session(db, chat_id, session)
        _answer_callback_query(token, query_id, "Me conta o que ajustar.")
        msg = f"✍️ Pode me contar o que você quer mudar no diário de {diary_date}. Sua próxima mensagem vira o ajuste."
        _persist_callback_turn("Botão: ajustar diário pessoal", msg)
        _send_telegram_message(token, chat_id, msg)

    elif data.startswith("diary_ok:"):
        diary_date = data.split("diary_ok:")[1].strip()
        try:
            db.collection("diario_pessoal").document(diary_date).update({"confirmado": True})
        except Exception as exc:
            print(f"[Diario] Falha ao confirmar diário {diary_date}: {exc}")
        _answer_callback_query(token, query_id, "Combinado!")

    elif data.startswith("outbox:"):
        parts = data.split(":")
        outbox_id = parts[1] if len(parts) > 1 else ""
        action = parts[2] if len(parts) > 2 else ""

        if not outbox_id or action not in ("ok", "no", "edit"):
            _answer_callback_query(token, query_id, "Ação não reconhecida.")
        elif action == "ok":
            from outbox_aprovacao import aprovar_rascunho
            res = aprovar_rascunho(db, outbox_id, telegram_token=token, chat_id=chat_id)
            if res.get("status") == "already_decided":
                _answer_callback_query(token, query_id, "Este rascunho já foi decidido.")
            elif res.get("status") == "not_found":
                _answer_callback_query(token, query_id, "Rascunho não encontrado.")
            elif res.get("status") == "ok":
                _answer_callback_query(token, query_id, "Enviado para a fila!")
                _persist_callback_turn(f"Botão: aprovar rascunho outbox:{outbox_id}", "✅ Enviado para a fila")
            else:
                _answer_callback_query(token, query_id, f"Erro: {res.get('erro', 'falha ao aprovar')}")
        elif action == "no":
            from outbox_aprovacao import descartar_rascunho
            telegram_msg_id = message.get("message_id") if isinstance(message, dict) else None
            res = descartar_rascunho(
                db, outbox_id, telegram_token=token, chat_id=chat_id, telegram_msg_id=telegram_msg_id
            )
            if res.get("status") == "already_decided":
                _answer_callback_query(token, query_id, "Este rascunho já foi decidido.")
            elif res.get("status") == "not_found":
                _answer_callback_query(token, query_id, "Rascunho não encontrado.")
            elif res.get("status") == "ok":
                _answer_callback_query(token, query_id, "Rascunho descartado.")
                _persist_callback_turn(f"Botão: descartar rascunho outbox:{outbox_id}", "🗑️ Rascunho descartado")
            else:
                _answer_callback_query(token, query_id, f"Erro: {res.get('erro', 'falha ao descartar')}")
        elif action == "edit":
            session["pending_outbox_edit"] = outbox_id
            _save_session(db, chat_id, session)
            _answer_callback_query(token, query_id, "Me manda o texto novo.")
            msg = "✍️ Me manda o texto novo em resposta a esta mensagem."
            _persist_callback_turn(f"Botão: editar rascunho outbox:{outbox_id}", msg)
            _send_telegram_message(token, chat_id, msg)

    elif data.startswith("argos_auth:"):
        parts = data.split(":")
        solicitacao_id = parts[1] if len(parts) > 1 else ""
        decisao = parts[2] if len(parts) > 2 else ""

        if not solicitacao_id or decisao not in ("aprovar", "recusar"):
            _answer_callback_query(token, query_id, "Ação não reconhecida.")
        else:
            from argos_autorizacao import decidir_autorizacao
            telegram_msg_id = message.get("message_id") if isinstance(message, dict) else None
            res = decidir_autorizacao(
                db, solicitacao_id, decisao, telegram_token=token, chat_id=chat_id, telegram_msg_id=telegram_msg_id
            )
            if res.get("status") == "already_decided":
                _answer_callback_query(token, query_id, "Esta solicitação já foi decidida.")
            elif res.get("status") == "not_found":
                _answer_callback_query(token, query_id, "Solicitação não encontrada.")
            elif res.get("status") == "ok" and decisao == "aprovar":
                _answer_callback_query(token, query_id, "Autorizado!")
                _persist_callback_turn(f"Botão: autorizar argos_auth:{solicitacao_id}", "✅ Autorizado")
            elif res.get("status") == "ok":
                _answer_callback_query(token, query_id, "Recusado.")
                _persist_callback_turn(f"Botão: recusar argos_auth:{solicitacao_id}", "❌ Recusado")
            else:
                _answer_callback_query(token, query_id, f"Erro: {res.get('erro', 'falha ao decidir')}")

    else:

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

    # --- Registro rápido de caminhada na esteira (determinístico, sem LLM) ---
    walk_reply = _try_register_walk_block(db, text)
    if walk_reply:
        _persist_turn_to_copilot(text, walk_reply)
        _send_telegram_session_message(db, token, chat_id, walk_reply, session=session)
        return

    # --- Ajuste de diário pessoal pendente (botão "✍️ Ajustar") — a próxima mensagem
    # livre vira o pedido de revisão, sem passar pelo roteador geral de chat. ---
    pending_diary_date = session.get("pending_diary_edit")
    if pending_diary_date and text and not text.startswith("/"):
        from personal_diary import apply_diary_feedback
        session.pop("pending_diary_edit", None)
        _save_session(db, chat_id, session)
        try:
            diary_reply = apply_diary_feedback(db, pending_diary_date, text)
        except Exception as exc:
            print(f"[Diario] Falha ao aplicar ajuste: {exc}")
            diary_reply = "⚠️ Não consegui ajustar o diário agora. Tente novamente mais tarde."
        _persist_turn_to_copilot(text, diary_reply)
        _send_telegram_session_message(db, token, chat_id, diary_reply, session=session)
        return

    # --- Ajuste de rascunho de outbox WhatsApp pendente (botão "✏️ Editar") ---
    pending_outbox_id = session.get("pending_outbox_edit")
    if pending_outbox_id and text and not text.startswith("/"):
        from outbox_aprovacao import aplicar_edicao_rascunho
        session.pop("pending_outbox_edit", None)
        _save_session(db, chat_id, session)
        try:
            res_edit = aplicar_edicao_rascunho(
                db,
                pending_outbox_id,
                text,
                telegram_token=token,
                chat_id=chat_id,
            )
            if res_edit.get("status") == "ok":
                outbox_reply = "✍️ Texto do rascunho atualizado com sucesso! Um novo card de aprovação foi enviado acima."
            else:
                outbox_reply = f"⚠️ Não consegui atualizar o rascunho: {res_edit.get('erro', 'erro desconhecido')}"
        except Exception as exc:
            print(f"[OutboxAprovacao] Falha ao aplicar edição de rascunho: {exc}")
            outbox_reply = "⚠️ Ocorreu um erro ao atualizar o rascunho."
        _persist_turn_to_copilot(text, outbox_reply)
        _send_telegram_session_message(db, token, chat_id, outbox_reply, session=session)
        return

    # --- /entrar command — busca semântica de ações para travamento de contexto ---
    if re.match(r"^/entrar(\s|$)", text, re.IGNORECASE):
        query = text[len("/entrar"):].strip()
        results = _search_actions_for_context(db, query)
        if not results:
            reply_text = (
                f"Nenhuma ação encontrada para <i>{query}</i>." if query
                else "Nenhuma ação cadastrada no sistema."
            )
            _persist_turn_to_copilot(text, reply_text, tools_used=["buscar_tarefas"])
            _send_telegram_session_message(
                db,
                token,
                chat_id,
                reply_text,
                session=session,
            )
        else:
            header = (
                f"Resultados para <i>{query}</i>. Toque para entrar no contexto:" if query
                else "Ações recentes. Toque para entrar no contexto:"
            )
            _persist_turn_to_copilot(text, header, tools_used=["buscar_tarefas"])
            _send_telegram_session_message(
                db,
                token,
                chat_id,
                header,
                session=session,
                inline_keyboard=_build_action_keyboard(results),
            )
        return

    # --- Natural-language action search + context lock
    # Ex: "pesquisa a acao de X e ative o contexto"
    action_search_context_query = _extract_action_search_context_query(text)
    if action_search_context_query:
        results = _search_actions_for_context(db, action_search_context_query)
        selected = _select_context_result(action_search_context_query, results)
        if selected:
            snapshot = _cached_acao_snapshot(db, selected["id"])
            if not snapshot:
                response_text = "Encontrei a acao, mas nao consegui carregar o snapshot real do contexto. Tente novamente em instantes."
                _persist_turn_to_copilot(text, response_text, tools_used=["buscar_tarefas"])
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
                return
            _lock_action_session(session, selected["id"], snapshot)
            _save_session(db, chat_id, session)
            response_text = _format_context_locked_message(snapshot)
            _persist_turn_to_copilot(text, response_text, tools_used=["buscar_tarefas"])
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
            return

        if results:
            header = (
                f"Encontrei algumas acoes para <i>{html.escape(action_search_context_query)}</i>. "
                "Toque na correta para eu travar o contexto real:"
            )
            _persist_turn_to_copilot(text, header, tools_used=["buscar_tarefas"])
            _send_contextual_response(
                db,
                token,
                chat_id,
                header,
                session=session,
                inline_keyboard=_build_action_keyboard(results),
                response_mode=response_mode,
                gemini_key=gemini_key,
                voice_profile=voice_profile,
                perf_state=perf_state,
            )
            return

        response_text = f"Nenhuma acao encontrada para <i>{html.escape(action_search_context_query)}</i>. Nao ativei contexto sem uma acao real."
        _persist_turn_to_copilot(text, response_text, tools_used=["buscar_tarefas"])
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
        return

    # --- Natural-language context lock ("entre no contexto da acao X") ---
    natural_context_query = _extract_natural_context_query(text)
    if natural_context_query is not None:
        results = _search_actions_for_context(db, natural_context_query)
        selected = _select_context_result(natural_context_query, results)
        if selected:
            snapshot = _cached_acao_snapshot(db, selected["id"])
            if not snapshot:
                response_text = "Encontrei a acao, mas nao consegui carregar o snapshot real do contexto. Tente novamente em instantes."
                _persist_turn_to_copilot(text, response_text, tools_used=["buscar_tarefas"])
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
                return
            _lock_action_session(session, selected["id"], snapshot)
            _save_session(db, chat_id, session)
            response_text = _format_context_locked_message(snapshot)
            _persist_turn_to_copilot(text, response_text, tools_used=["buscar_tarefas"])
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
            return

        if results:
            header = (
                f"Encontrei mais de uma acao para <i>{html.escape(natural_context_query or 'sua busca')}</i>. "
                "Toque na correta para eu travar o contexto real:"
            )
            _persist_turn_to_copilot(text, header, tools_used=["buscar_tarefas"])
            _send_contextual_response(
                db,
                token,
                chat_id,
                header,
                session=session,
                inline_keyboard=_build_action_keyboard(results),
                response_mode=response_mode,
                gemini_key=gemini_key,
                voice_profile=voice_profile,
                perf_state=perf_state,
            )
            return

        response_text = f"Nenhuma acao encontrada para <i>{html.escape(natural_context_query or text)}</i>. Nao ativei contexto sem uma acao real."
        _persist_turn_to_copilot(text, response_text, tools_used=["buscar_tarefas"])
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
        return

    # --- Deterministic action list ("liste as ações de hoje") ---
    is_list_req, list_date = _is_list_actions_request(text)
    if is_list_req:
        results = _fetch_actions_by_date(list_date)
        response_text = _format_actions_simple_list(results, list_date)
        _persist_turn_to_copilot(text, response_text, tools_used=["buscar_tarefas"])
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
        return

    # --- Deterministic action lookup ("busque a acao relacionada a X") ---
    action_lookup_query = _extract_action_lookup_query(text)
    if action_lookup_query:
        results = _search_actions_for_context(db, action_lookup_query)
        response_text = _format_action_lookup_results(action_lookup_query, results)
        _persist_turn_to_copilot(text, response_text, tools_used=["buscar_tarefas"])
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
        return

    # --- Command handler ---
    if text.startswith("/"):
        reply = _handle_command(text, session)
        if reply:
            _save_session(db, chat_id, session)
            _persist_turn_to_copilot(text, reply)
            _send_telegram_session_message(db, token, chat_id, reply, session=session)
            return
        # Unknown command — fall through to Gemini

    # --- Natural-language reset request ---
    if _is_reset_request(text):
        ctx = session.get("contexto_ativo", "geral")
        response_text = f"Você tem certeza que deseja limpar o histórico desta sessão (<b>{ctx}</b>)? Isto ajudará a evitar alucinações, mas eu esquecerei o que acabamos de conversar."
        _persist_turn_to_copilot(text, response_text)
        _send_telegram_message_with_keyboard(
            token, chat_id,
            response_text,
            _RESET_CONFIRM_KEYBOARD,
        )
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

    # --- Tool definitions ---
    def consultar_historico_acoes(
        query: str,
        area_tematica: str = None,
        data_limite_inicio: str = None,
        data_limite_fim: str = None,
        status: str = None,
    ):
        """Busca ações e tarefas no Hermes. Use status para filtrar por estado (ex: 'em andamento', 'concluída', 'cancelada'). Use data_limite_inicio/fim (YYYY-MM-DD) para filtrar por prazo."""
        if contexto_ativo == "acao" and acao_snapshot:
            titulo_acao = acao_snapshot.get("titulo") or request_acao_id or "ação atual"
            return (
                f"Contexto trancado na ação '{titulo_acao}'. "
                "Os dados desta ação já estão carregados no contexto — use-os diretamente. "
                "Para pesquisar outras ações, o usuário deve sair primeiro com /sair."
            )
        from tools.busca_grafo import buscar_tarefas

        _STOPWORDS_TG = {"de", "a", "o", "que", "e", "do", "da", "em", "um", "uma",
                         "os", "as", "no", "na", "com", "por", "para", "dos", "das",
                         "nos", "nas", "ao", "se", "ou", "acao", "acoes", "tarefa",
                         "tarefas", "pesquisa", "pesquisar", "pesquise", "busca",
                         "buscar", "busque", "procura", "procurar", "procure",
                         "localiza", "localizar", "localize", "ative", "ativar",
                         "ativa", "contexto"}
        _tg_terms = [w for w in re.findall(r"[\w./-]+", _normalize_for_matching(query), flags=re.UNICODE) if w not in _STOPWORDS_TG and len(w) > 2]
        _tg_mode = "all" if len(_tg_terms) >= 2 else "any"
        res = buscar_tarefas(query, area_tematica=area_tematica, match_mode=_tg_mode,
                             data_limite_inicio=data_limite_inicio, data_limite_fim=data_limite_fim,
                             status=status)
        if _tg_mode == "all" and not res.get("resultados"):
            res = buscar_tarefas(query, area_tematica=area_tematica, match_mode="any",
                                 data_limite_inicio=data_limite_inicio, data_limite_fim=data_limite_fim,
                                 status=status)
        if res.get("erro"):
            return f"⚠️ [ERRO] {res['erro']}"
        resultados = res.get("resultados", [])
        if not resultados:
            filtros_desc = []
            if query and query.strip():
                filtros_desc.append(f"query='{query.strip()}'")
            if status:
                filtros_desc.append(f"status='{status}'")
            if area_tematica:
                filtros_desc.append(f"area='{area_tematica}'")
            if data_limite_inicio or data_limite_fim:
                filtros_desc.append(f"prazo=[{data_limite_inicio or '*'} a {data_limite_fim or '*'}]")
            filtros_str = ", ".join(filtros_desc) if filtros_desc else "(sem filtros)"
            return (
                f"NENHUMA TAREFA ENCONTRADA com os filtros: {filtros_str}.\n"
                "INSTRUCAO OBRIGATORIA: Informe ao usuario que nao encontrou. "
                "NAO invente titulos, status ou dados. NAO use RAG para compensar."
            )
        lines = [
            "=== TAREFAS REAIS ENCONTRADAS NO BANCO DE DADOS ===",
            "REGRA: Use EXCLUSIVAMENTE os campos abaixo. Nao invente, nao complete, nao use RAG.",
            "",
        ]
        if res.get("aviso"):
            lines.append(f"AVISO TECNICO: {res['aviso']}")
        for r in resultados:
            lines.append(f"ID: {r['id']}")
            lines.append(f"Titulo: {r['titulo']}")
            lines.append(f"Status: {r['status']} | Tipo: {r.get('tipo_acao') or 'nao informado'}")
            lines.append(f"Prazo: {r.get('data_limite', 'N/A')} | Area: {r['area']}")
            if r.get('processo_sei'):
                lines.append(f"Processo SEI: {r['processo_sei']}")
            lines.append(f"Responsavel: {r['responsavel'] or 'nao informado'}")
            if r.get('tags'):
                lines.append(f"Tags: {', '.join(r['tags'])}")
            if r.get('sintese_demanda'):
                lines.append(f"Sintese da Demanda: {r['sintese_demanda']}")
            if r.get('descricao'):
                lines.append(f"Descricao: {r['descricao']}")
            if r.get('notas'):
                lines.append(f"Notas: {r['notas']}")
            plano = r.get('plano_acao', [])
            if plano:
                lines.append("Plano de Acao:")
                for passo in plano:
                    lines.append(f"  {passo}")
            acomp = r.get('acompanhamento_recente', [])
            if acomp:
                lines.append("Diario de Bordo (ultimas entradas):")
                for entrada in acomp:
                    lines.append(f"  {entrada}")
            lines.append("---")
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
            if internal_hermes_request and not explicit_web_request:
                return (
                    '{"error": "Bloqueado: o pedido atual e interno do Hermes. '
                    'Nao use internet como substituto para consultas do sistema."}'
                )
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
        prazo_final: str = None,
        tipo_acao: str = "fast",
        tags: list[str] = None,
        notas: str = "",
        plano_acao: list[str] = None,
        horario_inicio: str = None,
        horario_fim: str = None,
        recorrencia_mensal: bool = False,
        dia_do_mes_recorrencia: int = None,
        recorrencia_semanal: bool = False,
        dias_da_semana_recorrencia: list[int] = None,
        intervalo_semanas_recorrencia: int = None,
    ):
        """
        Cria uma nova ação no Hermes. Apresente draft ao usuário antes de chamar.
        Retorna 'OK|{ID}' em caso de sucesso ou 'ERRO|{detalhe}'.
        IMPORTANTE: area_tematica deve ser EXATAMENTE UMA das áreas temáticas válidas
        listadas no contexto do sistema. Nunca invente uma nova; se nenhuma se encaixar, use 'GERAL'.
        - data_limite: DATA DE EXECUÇÃO (YYYY-MM-DD), o dia em que o trabalho deve ser feito. Não é o prazo.
        - prazo_final: PRAZO FINAL (YYYY-MM-DD), opcional — só preencha se o usuário mencionar um prazo real distinto da data de execução.
        - recorrencia_mensal: True se o usuário pedir para a ação se repetir todo mês (ex.: "todo dia 5", "mensalmente").
        - dia_do_mes_recorrencia: dia do mês (1 a 31) em que a ação deve se repetir. Obrigatório quando recorrencia_mensal=True.
        - recorrencia_semanal: True se o usuário pedir para a ação se repetir semanalmente (ex.: "todos os domingos", "toda segunda e quarta", "a cada 15 dias").
        - dias_da_semana_recorrencia: lista de dias da semana (0=domingo, 1=segunda, ..., 6=sábado). Aceita um ou mais dias. Obrigatório quando recorrencia_semanal=True.
        - intervalo_semanas_recorrencia: repetir a cada N semanas (1=toda semana, 2=quinzenal, etc.). Opcional; padrão 1.
        Use recorrencia_semanal OU recorrencia_mensal, nunca ambas.
        """
        import uuid as _uuid
        # Garante que o copiloto só use áreas temáticas existentes (fallback 'GERAL').
        area_tematica = normalizar_area_tematica(area_tematica, _areas_validas)
        now_iso = datetime.now(timezone.utc).isoformat()

        # Normalização de horários
        def normalize_hhmm(t_str: str) -> str | None:
            if not t_str:
                return None
            t_str = str(t_str).strip()
            if ":" not in t_str:
                return None
            try:
                h, m = t_str.split(":")
                return f"{int(h):02d}:{int(m):02d}"
            except:
                return t_str

        horario_inicio = normalize_hhmm(horario_inicio)
        horario_fim = normalize_hhmm(horario_fim)

        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt
        tz = ZoneInfo("America/Sao_Paulo")
        now_local = _dt.now(tz)
        today_local = now_local.strftime("%Y-%m-%d")

        if not data_limite or str(data_limite) < today_local:
            data_limite = today_local

        if prazo_final and str(prazo_final) < today_local:
            prazo_final = today_local

        if data_limite == today_local and horario_inicio:
            current_time_str = now_local.strftime("%H:%M")
            if horario_inicio < current_time_str:
                return f"ERRO|Não é possível agendar um horário anterior ao horário atual ({current_time_str}). Por favor, escolha um horário posterior."

        # Idempotência: reivindica atomicamente a chave (título, data, horário) para evitar
        # criar a mesma ação duas ou três vezes quando o modelo chama esta tool mais de uma
        # vez para o mesmo pedido (retry, lote de function calls repetido) — sintoma relatado
        # como "aparece duplicada no mesmo horário, com evento duplicado na agenda".
        from main import claim_action_dedup_slot, store_action_dedup_result
        _dedup_status, _dedup_task_id = claim_action_dedup_slot(db, titulo, data_limite, horario_inicio)
        if _dedup_status == "duplicate":
            print(f"[Core] Ação duplicada evitada: reaproveitando {_dedup_task_id} em vez de criar outra.")
            return f"OK|{_dedup_task_id}"
        if _dedup_status == "pending":
            return "ERRO|Esta ação já está sendo registrada por outra chamada. Aguarde alguns segundos e verifique a lista de ações antes de tentar de novo."

        task_id = str(_uuid.uuid4())[:20]
        # Aceita lista de strings (uso historico) ou de objetos com os campos da
        # subtarefa — `subtarefas.converter_plano` normaliza os dois.
        import subtarefas as _sub
        plano_convertido = _sub.converter_plano(plano_acao)
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
            "prazo_final": prazo_final,
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
        if recorrencia_semanal and dias_da_semana_recorrencia:
            doc["recorrencia"] = {
                "ativo": True,
                "frequencia": "semanal",
                "dias_da_semana": sorted({max(0, min(6, int(d))) for d in dias_da_semana_recorrencia}),
            }
            if intervalo_semanas_recorrencia and int(intervalo_semanas_recorrencia) > 1:
                doc["recorrencia"]["intervalo_semanas"] = min(12, int(intervalo_semanas_recorrencia))
        elif recorrencia_mensal and dia_do_mes_recorrencia:
            doc["recorrencia"] = {
                "ativo": True,
                "frequencia": "mensal",
                "dia_do_mes": max(1, min(31, int(dia_do_mes_recorrencia))),
            }
        try:
            db.collection("tarefas").document(task_id).set(doc)
            store_action_dedup_result(db, titulo, data_limite, horario_inicio, task_id)
            return f"OK|{task_id}"
        except Exception as e:
            from main import release_action_dedup_slot
            release_action_dedup_slot(db, titulo, data_limite, horario_inicio)
            return f"ERRO|{e}"

    def reagendar_acoes_em_lote(
        nova_data_inicio: str,
        max_por_semana: int = 5,
        estrategia: str = "data_criacao",
        filtro_data: str = None,
        task_ids: list[str] = None,
        justificativa: str = "",
    ):
        """
        Reagenda múltiplas ações de uma vez, redistribuindo-as a partir de uma data de início.
        Executa imediatamente após confirmação do usuário.

        Parâmetros:
        - nova_data_inicio: YYYY-MM-DD — primeiro dia útil a partir do qual distribuir as ações
        - max_por_semana: máximo de ações por semana (padrão 5)
        - estrategia: "data_criacao" (padrão) | "tipo_acao" (fast primeiro) | "alfa" (alfabética)
        - filtro_data: YYYY-MM-DD — seleciona ações com data_limite igual a essa data
        - task_ids: lista explícita de IDs de tarefas (alternativa ao filtro_data)
        - justificativa: motivo gravado no diário de cada ação reagendada

        Retorna resumo textual com as ações reagendadas ou mensagem de erro.
        """
        try:
            from datetime import timedelta as _td

            if not filtro_data and not task_ids:
                return "ERRO|Forneça filtro_data (YYYY-MM-DD) ou task_ids."

            tasks = []
            if task_ids:
                for tid in (task_ids or []):
                    tdoc = db.collection('tarefas').document(str(tid)).get()
                    if tdoc.exists:
                        t = tdoc.to_dict()
                        if t.get('status') not in ('concluído', 'cancelado'):
                            tasks.append({'_id': str(tid), **t})
            else:
                q = db.collection('tarefas')\
                    .where('data_limite', '==', filtro_data)\
                    .where('status', 'in', ['em andamento', 'stand-by'])\
                    .get()
                for qdoc in q:
                    tasks.append({'_id': qdoc.id, **qdoc.to_dict()})

            if not tasks:
                return "Nenhuma ação encontrada com os critérios informados."

            if estrategia == 'tipo_acao':
                tasks.sort(key=lambda x: (0 if x.get('tipo_acao') == 'fast' else 1, x.get('data_criacao', '')))
            elif estrategia == 'alfa':
                tasks.sort(key=lambda x: x.get('titulo', '').lower())
            else:
                tasks.sort(key=lambda x: x.get('data_criacao', ''))

            try:
                start_date = datetime.strptime(nova_data_inicio, "%Y-%m-%d").date()
                today_date = datetime.now(timezone.utc).date()
                if start_date < today_date:
                    start_date = today_date
            except ValueError:
                return f"ERRO|Formato de data inválido: '{nova_data_inicio}'. Use YYYY-MM-DD."

            def _next_weekday(d):
                while d.weekday() >= 5:
                    d += _td(days=1)
                return d

            day_cursor = _next_weekday(start_date)

            batch = db.batch()
            now_iso = datetime.now(timezone.utc).isoformat()
            diary_entry = {
                'data': now_iso,
                'nota': f"[Copiloto Hermes] {justificativa or 'Reagendamento em lote.'}"
            }

            count_this_week = 0
            updated_lines = []

            for task in tasks:
                if count_this_week >= max_por_semana:
                    days_to_monday = 7 - day_cursor.weekday()
                    day_cursor += _td(days=days_to_monday)
                    day_cursor = _next_weekday(day_cursor)
                    count_this_week = 0

                nova_data_str = day_cursor.strftime("%Y-%m-%d")
                task_ref = db.collection('tarefas').document(task['_id'])
                batch.update(task_ref, {
                    'data_limite': nova_data_str,
                    'data_inicio': nova_data_str,
                    'data_atualizacao': now_iso,
                    'acompanhamento': firestore.ArrayUnion([diary_entry]),
                })
                updated_lines.append(f"• [{task.get('titulo', task['_id'])}](task:{task['_id']}) → {nova_data_str}")

                count_this_week += 1
                day_cursor += _td(days=1)
                day_cursor = _next_weekday(day_cursor)

            batch.commit()
            return f"✅ {len(updated_lines)} ações reagendadas:\n" + "\n".join(updated_lines)

        except Exception as _e:
            return f"ERRO|{_e}"

    def editar_acoes_em_lote(
        itens: list[dict],
        justificativa: str = "",
    ):
        """
        Edita múltiplas ações no sistema simultaneamente (ex.: alterar datas de execução, prazos finais, status, áreas temáticas, tags, etc.).

        Parâmetros:
        - itens: lista de dicionários contendo:
          - task_id (str): ID da tarefa a ser alterada
          - alteracoes (dict): dicionário com campos e novos valores (ex.: {"data_limite": "2026-08-25"})
        - justificativa: motivo registrado no diário de acompanhamento de cada ação
        """
        try:
            from datetime import datetime as _dt, timezone as _tz

            def _como_dict(valor):
                """Aceita dict ou JSON serializado — o schema declarado pode ter
                virado STRING no saneamento, e o modelo às vezes manda texto."""
                if isinstance(valor, dict):
                    return valor
                if isinstance(valor, str) and valor.strip():
                    try:
                        carregado = json.loads(valor)
                        return carregado if isinstance(carregado, dict) else {}
                    except Exception:
                        return {}
                return {}

            if isinstance(itens, str):
                try:
                    itens = json.loads(itens)
                except Exception:
                    return "ERRO|Não consegui ler a lista de itens. Envie uma lista com 'task_id' e 'alteracoes'."
            if isinstance(itens, dict):
                itens = [itens]
            if not itens or not isinstance(itens, list):
                return "ERRO|Forneça uma lista de itens com 'task_id' e 'alteracoes'."

            _ALLOWED = {'titulo', 'descricao', 'data_limite', 'data_inicio', 'prazo_final', 'horario_inicio', 'horario_fim', 'status', 'tags', 'area_tematica', 'tipo_acao', 'notas', 'email_link_optout'}
            today_str = _dt.now(_tz.utc).strftime("%Y-%m-%d")
            now_iso = _dt.now(_tz.utc).isoformat()
            batch = db.batch()
            count = 0
            resumo_linhas = []

            for item in itens:
                item = _como_dict(item)
                tid = str(item.get('task_id') or '').strip()
                if not tid:
                    continue
                alteracoes = _como_dict(item.get('alteracoes'))
                task_ref = db.collection('tarefas').document(tid)
                task_doc = task_ref.get()
                if not task_doc.exists:
                    continue
                task_data = task_doc.to_dict() or {}
                updates = {}
                for campo, novo_valor in alteracoes.items():
                    if campo not in _ALLOWED:
                        continue
                    if campo == 'status':
                        if novo_valor in ('concluido', 'concluida', 'finalizado'): novo_valor = 'concluído'
                        elif novo_valor in ('stand by', 'standby'): novo_valor = 'stand-by'
                        elif novo_valor in ('em andamento', 'andamento', 'aberto'): novo_valor = 'em andamento'
                        elif novo_valor in ('excluido', 'excluir', 'cancelado', 'deletar'): novo_valor = 'excluído'
                    updates[campo] = novo_valor

                if not updates:
                    continue

                if 'data_limite' in updates or 'data_inicio' in updates:
                    single_date = updates.get('data_limite') or updates.get('data_inicio') or ''
                    if single_date and single_date not in ('-', '0000-00-00') and single_date < today_str:
                        single_date = today_str
                    updates['data_limite'] = single_date
                    updates['data_inicio'] = single_date

                updates['data_atualizacao'] = now_iso
                if updates.get('status') == 'concluído':
                    updates['data_conclusao'] = now_iso
                elif updates.get('status') in ('em andamento', 'stand-by'):
                    updates['data_conclusao'] = None

                campos_desc = ', '.join(f"{k}='{v}'" for k, v in updates.items() if k not in ('data_atualizacao', 'data_conclusao'))
                diary_entry = {
                    'data': now_iso,
                    'nota': f"[Copiloto Hermes/Telegram] Edição em lote ({justificativa}). Campos alterados: {campos_desc}."
                }
                batch.update(task_ref, {
                    **updates,
                    'acompanhamento': firestore.ArrayUnion([diary_entry])
                })
                count += 1
                titulo = task_data.get('titulo', tid)
                resumo_linhas.append(f"• {titulo}: {campos_desc}")

            if count == 0:
                return "Nenhuma ação pôde ser atualizada com os dados fornecidos."

            batch.commit()
            return f"Sucesso! {count} ações atualizadas:\n" + "\n".join(resumo_linhas)
        except Exception as e:
            return f"ERRO ao editar ações em lote: {e}"

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

    def agendar_lembrete_acao(data: str, horario: str, task_id: str = None, texto: str = ""):
        """
        Agenda um lembrete para uma acao do Hermes.
        data: Data do lembrete no formato YYYY-MM-DD.
        horario: Horario do lembrete no formato HH:MM.
        task_id: ID da acao. Opcional quando ja existe uma acao em contexto.
        texto: Texto personalizado opcional que aparecera no lembrete.
        """
        from tools.telegram_extended import execute
        actual_task_id = task_id or request_acao_id or session.get("current_task_id")
        if not actual_task_id:
            return "ERRO|Nenhuma ação ativa em contexto e nenhum task_id foi informado para agendar o lembrete."
        slots = {"task_id": actual_task_id, "data": data, "horario": horario, "texto": texto}
        return execute("agendar_lembrete_acao", slots, db)

    def consultar_financas_v2(mes: int = None, ano: int = None):
        """Retorna resumo financeiro (balancete, metas, extrato). mes (0-11), ano (YYYY). Se mes for omitido, assume o mes anterior ao atual."""
        from tools.telegram_extended import execute
        return execute("consultar_financas_v2", {"mes": mes, "ano": ano}, db)

    def registrar_item_financeiro_v2(tipo: str, descricao: str, valor: float, mes: int = None, ano: int = None, data: str = None):
        """
        Registra nova renda, obrigacao_fixa ou transacao_avulsa no sistema financeiro.
        tipo: 'renda' | 'obrigacao_fixa' | 'transacao_avulsa'.
        Obrigatório apresentar rascunho completo ao usuário para confirmação antes de persistir.
        Categoria não deve ser inferida nem solicitada por enquanto; o sistema grava "Geral" internamente.
        """
        from tools.telegram_extended import execute
        slots = {"tipo": tipo, "descricao": descricao, "valor": valor, "categoria": "Geral", "mes": mes, "ano": ano, "data": data}
        return execute("registrar_item_financeiro_v2", slots, db)

    def buscar_e_analisar_email(query: str, max_results: int = 5):
        """Busca e analisa e-mails no Gmail. Use query padrão do Gmail (ex: 'from:x@y.com newer_than:2d')."""
        try:
            from tools.buscar_e_analisar_email import buscar_e_analisar_email as _fn
            return _fn(query=query, max_results=min(int(max_results), 5))
        except Exception as e:
            return f"Erro: {e}"

    def propor_acao_para_confirmacao(
        titulo: str,
        descricao: str = "",
        area_tematica: str = "GERAL",
        data_limite: str = None,
        prazo_final: str = None,
        tipo_acao: str = "fast",
        tags: list[str] = None,
        notas: str = "",
        plano_acao: list[str] = None,
        horario_inicio: str = None,
        horario_fim: str = None,
    ):
        """
        Gera uma proposta de criação de ação para o usuário confirmar via botões.
        Use esta ferramenta SEMPRE antes de criar uma ação.
        - data_limite: DATA DE EXECUÇÃO (YYYY-MM-DD), o dia em que o trabalho deve ser feito. Não é o prazo.
        - prazo_final: PRAZO FINAL (YYYY-MM-DD), opcional — só preencha se o usuário mencionar um prazo real distinto da data de execução.
        """
        # Normalização de horários
        def normalize_hhmm(t_str: str) -> str | None:
            if not t_str:
                return None
            t_str = str(t_str).strip()
            if ":" not in t_str:
                return None
            try:
                h, m = t_str.split(":")
                return f"{int(h):02d}:{int(m):02d}"
            except:
                return t_str

        horario_inicio = normalize_hhmm(horario_inicio)
        horario_fim = normalize_hhmm(horario_fim)

        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt
        tz = ZoneInfo("America/Sao_Paulo")
        now_local = _dt.now(tz)
        today_local = now_local.strftime("%Y-%m-%d")

        eff_limit = data_limite or today_local
        if eff_limit < today_local:
            eff_limit = today_local

        eff_prazo_final = prazo_final
        if eff_prazo_final and eff_prazo_final < today_local:
            eff_prazo_final = today_local

        if eff_limit == today_local and horario_inicio:
            current_time_str = now_local.strftime("%H:%M")
            if horario_inicio < current_time_str:
                return f"ERRO|Não é possível propor um horário anterior ao horário atual ({current_time_str}). Por favor, escolha um horário posterior."

        pending_data = {
            "titulo": titulo,
            "descricao": descricao,
            "area_tematica": area_tematica,
            "data_limite": eff_limit,
            "prazo_final": eff_prazo_final,
            "tipo_acao": tipo_acao,
            "tags": tags or [],
            "notas": notas,
            "plano_acao": plano_acao or [],
            "horario_inicio": horario_inicio,
            "horario_fim": horario_fim,
        }
        session.setdefault("pending_confirmations", {})["acao"] = pending_data
        session["_pending_confirm_type"] = "acao"

        draft = (
            f"📝 <b>PROPOSTA DE AÇÃO</b>\n"
            f"• Título: {titulo}\n"
            f"• Área: {area_tematica}\n"
            f"• Data de Execução: {pending_data['data_limite']}\n"
        )
        if pending_data['prazo_final']:
            draft += f"• Prazo Final: {pending_data['prazo_final']}\n"
        if tags: draft += f"• Tags: {', '.join(tags)}\n"
        if plano_acao: draft += f"• Passos: {len(plano_acao)}\n"

        return f"Proposta gerada com sucesso. Draft: {draft}\n\n[SISTEMA: Os botões de confirmação serão anexados automaticamente a esta resposta.]"

    def propor_lancamento_financeiro(tipo: str, descricao: str, valor: float, mes: int = None, ano: int = None, data: str = None):
        """
        Gera uma proposta de lançamento financeiro para o usuário confirmar via botões.
        tipo: 'renda' | 'obrigacao_fixa' | 'transacao_avulsa'.
        Categoria não deve ser inferida nem exibida por enquanto.
        """
        pending_data = {
            "tipo": tipo,
            "descricao": descricao,
            "valor": valor,
            "categoria": "Geral",
            "mes": mes,
            "ano": ano,
            "data": data
        }
        session.setdefault("pending_confirmations", {})["financeiro"] = pending_data
        session["_pending_confirm_type"] = "financeiro"

        draft = (
            f"💰 <b>PROPOSTA DE LANÇAMENTO</b>\n"
            f"• Tipo: {tipo}\n"
            f"• Descrição: {descricao}\n"
            f"• Valor: R$ {valor:.2f}\n"
        )
        return f"Proposta financeira gerada. Draft: {draft}\n\n[SISTEMA: Os botões de confirmação serão anexados automaticamente a esta resposta.]"

    def schedule_whatsapp_message(contact_number: str, message: str, scheduled_time: str) -> str:
        """
        Prepara uma mensagem de WhatsApp para confirmacao por botoes.
        O enfileiramento real acontece apenas no callback confirm_whatsapp.
        """
        pending_data = {
            "contact_number": str(contact_number or "").strip(),
            "message": str(message or "").strip(),
            "scheduled_time": str(scheduled_time or "").strip(),
        }
        session.setdefault("pending_confirmations", {})["whatsapp"] = pending_data
        session["_pending_confirm_type"] = "whatsapp"

        draft = (
            f"📲 <b>PROPOSTA DE WHATSAPP</b>\n"
            f"• Destinatário: {html.escape(pending_data['contact_number'])}\n"
            f"• Agendamento: {html.escape(pending_data['scheduled_time'])}\n"
            f"• Mensagem: {html.escape(pending_data['message'][:700])}"
        )
        return f"Proposta de WhatsApp gerada. Draft: {draft}\n\n[SISTEMA: Os botões de confirmação serão anexados automaticamente a esta resposta.]"

    # O Telegram usa closures próprias (inclusive confirmações por botões),
    # não o catálogo MCP. Reutilizar os handlers mantém a regra de negócio única.
    def ativar_modo_secretario(contatos: list[str] = None, duracao_horas: float = None) -> str:
        """Ativa o atendimento autônomo no WhatsApp para contatos autorizados.

        Args:
            contatos: Nomes, telefones ou JIDs. Omitir mantém a lista atual.
            duracao_horas: Duração em horas; 0.5 equivale a 30 minutos.
                Omitir mantém ativo até desligar manualmente.
        """
        from tools.hermes_tools import execute
        from tools.tool_context import ToolContext

        resultado = execute(
            "ativar_modo_secretario",
            {"contatos": contatos, "duracao_horas": duracao_horas},
            ToolContext(_db=db, canal="telegram"),
        )
        return json.dumps(resultado, ensure_ascii=False, default=str)

    def desativar_modo_secretario() -> str:
        """Desativa imediatamente o atendimento autônomo do Modo Secretário no WhatsApp."""
        from tools.hermes_tools import execute
        from tools.tool_context import ToolContext

        resultado = execute("desativar_modo_secretario", {}, ToolContext(_db=db, canal="telegram"))
        return json.dumps(resultado, ensure_ascii=False, default=str)

    def consultar_status_modo_secretario() -> str:
        """Consulta se o Modo Secretário está ativo, seus contatos e a expiração."""
        from tools.hermes_tools import execute
        from tools.tool_context import ToolContext

        resultado = execute("consultar_status_modo_secretario", {}, ToolContext(_db=db, canal="telegram"))
        return json.dumps(resultado, ensure_ascii=False, default=str)

    tools_list = [

        consultar_historico_acoes,
        buscar_arquivos_acervo,
        pesquisar_internet,
        ler_pagina_web,
        consultar_agenda,
        encontrar_slot_livre,
        criar_acao_no_sistema,
        reagendar_acoes_em_lote,
        editar_acoes_em_lote,
        salvar_memoria_global,
        registrar_correcao_procedimento,
        buscar_e_analisar_email,
        consultar_financas_v2,
        registrar_item_financeiro_v2,
        propor_acao_para_confirmacao,
        propor_lancamento_financeiro,
        schedule_whatsapp_message,
        agendar_lembrete_acao,
        ativar_modo_secretario,
        desativar_modo_secretario,
        consultar_status_modo_secretario,
    ]


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
