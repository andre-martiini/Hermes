"""Callbacks do Telegram - sessao, notificacoes, reagendamento em lote, cards do Copiloto Web, diario e outbox

Extraido de hermes_core_logic.py::_handle_telegram_callback (P02, modularizacao
por area -- hermes_core_logic.py e telegram_utils.py cresceram alem do teto de
~64000 tokens de saida por chamada de escrita do Argos; ver decisao do Andre em
2026-09-08). Split puramente mecanico: nenhuma linha de logica foi reescrita, so
movida e envolvida por `def handle(...) -> bool`. Cada `return
https_fn.Response("OK", status=200)` virou `return True` (o chamador, em
telegram_handlers_core.py, sempre monta essa mesma resposta no fim -- o valor de
retorno aqui so diz se este modulo tratou o callback, para o dispatcher decidir
se tenta o proximo).

ATENCAO para mock.patch/mock.patch.object em testes: as funcoes deste arquivo
resolvem nomes livres (`_send_telegram_message`, `_answer_callback_query`,
etc.) pelo namespace DESTE modulo, nao pelo de hermes_core_logic nem de
telegram_handlers_core -- mesmo padrao documentado em telegram_utils.py. Um
`mock.patch.object(hermes_core_logic, "_send_telegram_message", ...)` nao
intercepta uma chamada feita de dentro de uma funcao deste arquivo.
"""
from datetime import datetime, timezone

from telegram_utils import (
    _EXIT_KEYBOARD,
    _answer_callback_query,
    _cached_acao_snapshot,
    _call_web_callable,
    _find_latest_copilot_card_message_id,
    _save_session,
    _send_telegram_message,
    _send_telegram_message_with_keyboard,
    _send_telegram_session_message,
    _set_latest_copilot_card_status,
)

def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id, _persist_callback_turn, _pending_web_card, _clear_pending_web_card) -> bool:
    """Trata ai_notif:, reagendamento_lote:, exit_context, lock:, reset_session_confirm/cancel, webedit_*/webbatch_*/webmem_* (cards do Copiloto Web), diary_edit:/diary_ok:, outbox: e argos_auth:. Retorna True se tratou."""
    if data.startswith("ai_notif:"):
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
            return True

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
            return True
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
            return True
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
            return True
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
        return False
    return True
