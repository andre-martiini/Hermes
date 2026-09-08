"""Callbacks do Telegram - mesclagem de contatos e vinculo de e-mail

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
import html
from datetime import datetime, timezone

from telegram_utils import _answer_callback_query, _send_telegram_message

def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id, _persist_callback_turn, _pending_web_card, _clear_pending_web_card) -> bool:
    """Trata merge_confirm:/merge_ignore: (mesclagem de contatos) e emlink: (vinculo de e-mail a acao). Retorna True se tratou."""
    if data.startswith("merge_confirm:"):
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

    else:
        return False
    return True
