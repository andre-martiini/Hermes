"""
Hermes Core Logic — Telegram Integration
Webhook receiver + Firestore-triggered async processor.

Este arquivo passou de monolito (3183 linhas) para shim de reexportacao pura
(P02, modularizacao por area -- ele e telegram_utils.py cresceram alem do teto
de ~64000 tokens de saida por chamada de escrita do Argos, o que os deixava
permanentemente inescreviveis pela ferramenta `argos_escrever_arquivo_repositorio`;
ver decisao do Andre em 2026-09-08). Toda a logica foi movida, sem reescrita,
para modulos por area:

- telegram_callbacks_saude.py -- check-ins de saude (health_checkin: etc.)
- telegram_callbacks_confirmacoes.py -- confirm_acao/financeiro/whatsapp, cancel_*, wa_cancel:
- telegram_callbacks_contatos.py -- merge_confirm:/merge_ignore:, emlink:
- telegram_callbacks_sessao.py -- ai_notif:, reagendamento_lote:, exit_context, lock:,
  reset_session_*, webedit_*/webbatch_*/webmem_* (cards do Copiloto Web), diary_*, outbox:, argos_auth:
- telegram_message_deterministic.py -- respostas sem LLM (caminhada, /entrar, busca+trava
  de contexto, listagem/busca deterministica de acoes, comandos, pedido de reset)
- telegram_message_tools.py -- os 21 closures de function-calling do Gemini
- telegram_handlers_core.py -- o que restou de _handle_telegram_callback (setup +
  dispatcher) e _process_telegram_message (setup, personalidade/historico/midia,
  chamada ao Gemini, envio da resposta), mais os 3 entry points do Firebase
  Functions (telegramWebhook, on_health_log_red_flag, on_telegram_inbound)

Este arquivo continua existindo só por compatibilidade de atributo
(`hermes_core_logic.<nome>` continua funcionando para quem importa daqui,
como main.py). ATENÇÃO ao escrever mock.patch/mock.patch.object: isto NÃO
redireciona uma chamada de nome livre feita de dentro de uma função que mora
em outro módulo -- essa chamada resolve pelo namespace do módulo onde a
função foi definida, não pelo daqui. Para interceptar uma chamada interna a
um destes nomes, mire o módulo onde a função que faz a chamada realmente
mora (telegram_utils, telegram_callbacks_*, telegram_message_*, ou
telegram_handlers_core -- não hermes_core_logic). Detalhe completo e exemplos
no docstring de telegram_utils.py e de telegram_handlers_core.py.
"""
from firebase_admin import get_app, initialize_app

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

# Reexporta os handlers centrais e os 3 entry points do Firebase Functions,
# que ficam em telegram_handlers_core.py (ver docstring acima e a de lá --
# mantidos juntos para evitar import circular, já que main.py importa estes
# 5 nomes diretamente daqui para registro de deploy das Cloud Functions).
from telegram_handlers_core import (
    _handle_telegram_callback,
    _process_telegram_message,
    on_health_log_red_flag,
    on_telegram_inbound,
    telegramWebhook,
)
