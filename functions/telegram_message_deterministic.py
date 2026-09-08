"""Respostas deterministicas do Telegram (sem LLM)

Extraido de hermes_core_logic.py::_process_telegram_message (P02, modularizacao
por area -- hermes_core_logic.py e telegram_utils.py cresceram alem do teto de
~64000 tokens de saida por chamada de escrita do Argos; ver decisao do Andre em
2026-09-08). Split puramente mecanico: nenhuma linha de logica foi reescrita, so
movida e envolvida por `def try_deterministic_reply(...) -> bool`. Cada `return`
(sem valor) do bloco original virou `return True` (mensagem tratada, chamador
para por aqui); se nenhum ramo bater, cai no `return False` final (o chamador
segue para o fluxo do Gemini).

ATENCAO para mock.patch/mock.patch.object em testes: as funcoes deste arquivo
resolvem nomes livres (`_handle_command`, `_save_session`, etc.) pelo namespace
DESTE modulo, nao pelo de hermes_core_logic nem de telegram_handlers_core --
mesmo padrao documentado em telegram_utils.py.
"""
import html
import re

from telegram_utils import (
    _RESET_CONFIRM_KEYBOARD,
    _build_action_keyboard,
    _cached_acao_snapshot,
    _extract_action_lookup_query,
    _extract_action_search_context_query,
    _extract_natural_context_query,
    _fetch_actions_by_date,
    _format_action_lookup_results,
    _format_actions_simple_list,
    _format_context_locked_message,
    _handle_command,
    _is_list_actions_request,
    _is_reset_request,
    _lock_action_session,
    _save_session,
    _search_actions_for_context,
    _select_context_result,
    _send_contextual_response,
    _send_telegram_message_with_keyboard,
    _send_telegram_session_message,
    _try_register_walk_block,
)

def try_deterministic_reply(db, token, chat_id, text, session, gemini_key, response_mode, voice_profile, perf_state, _persist_turn_to_copilot) -> bool:
    """Tenta responder sem LLM (caminhada, edicao de diario/outbox pendente, /entrar,
    busca+trava de contexto, listagem/busca deterministica de acoes, comandos, pedido
    de reset). Retorna True se tratou (a chamada ja enviou a resposta e persistiu o
    turno); False se nenhum ramo bateu e o fluxo deve seguir para o Gemini."""
    # --- Registro rápido de caminhada na esteira (determinístico, sem LLM) ---
    walk_reply = _try_register_walk_block(db, text)
    if walk_reply:
        _persist_turn_to_copilot(text, walk_reply)
        _send_telegram_session_message(db, token, chat_id, walk_reply, session=session)
        return True

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
        return True

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
        return True

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
        return True

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
                return True
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
            return True

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
            return True

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
        return True

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
                return True
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
            return True

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
            return True

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
        return True

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
        return True

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
        return True

    # --- Command handler ---
    if text.startswith("/"):
        reply = _handle_command(text, session)
        if reply:
            _save_session(db, chat_id, session)
            _persist_turn_to_copilot(text, reply)
            _send_telegram_session_message(db, token, chat_id, reply, session=session)
            return True
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
        return True

    return False
