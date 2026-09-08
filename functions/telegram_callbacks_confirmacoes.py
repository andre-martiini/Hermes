"""Callbacks do Telegram - confirmacoes (acao, financeiro, WhatsApp)

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

from autonomy import policy as autonomy_policy
from autonomy.contracts import Decisao, Principal, TipoPrincipal
from telegram_utils import (
    _answer_callback_query,
    _clear_telegram_inline_keyboard,
    _save_session,
    _send_telegram_message,
)

def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id, _persist_callback_turn, _pending_web_card, _clear_pending_web_card) -> bool:
    """Trata confirm_acao/cancel_acao, confirm_financeiro/cancel_financeiro, confirm_whatsapp/cancel_whatsapp e wa_cancel:. Retorna True se tratou."""
    if data == "confirm_acao":
        _answer_callback_query(token, query_id, "Processando registro...")
        # Remove o teclado inline imediatamente para que um duplo toque acidental não
        # reenvie o mesmo callback_query enquanto esta chamada ainda está em andamento.
        _clear_telegram_inline_keyboard(token, chat_id, message.get("message_id"))
        pending = session.get("pending_confirmations", {}).get("acao")
        if not pending:
            response_text = "⚠️ Nenhuma ação pendente de confirmação encontrada ou o prazo expirou."
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

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
            return True
        if _dedup_status == "pending":
            response_text = "⏳ Essa ação já está sendo registrada por outra chamada. Verifique a lista de ações em alguns segundos."
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

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
            return True

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
            return True

        # Preflight de autonomy.policy (P02 sub-entrega 10/N) — este é o
        # único ponto de integração possível para este fluxo: a closure de
        # tool-calling do Gemini que monta `pending` (schedule_whatsapp_message,
        # mais abaixo neste arquivo) roda dentro do processamento da mensagem
        # e nunca teve acesso resolvido a `db`/política; a decisão real de
        # "isto pode ser enviado" só pode ser tomada aqui, no clique do botão
        # "Confirmar" — imediatamente antes do envio de fato, o que também
        # cobre o caso de o estado de autonomia mudar entre a prévia e a
        # confirmação (limitação que mcp_server.py ainda tem, ver
        # `_decisao_piso_mcp`). TipoPrincipal.DONO_INTERATIVO + origem_humana
        # =True porque este é literalmente um clique de botão em tempo real
        # do próprio dono — o canal com o sinal de presença humana mais forte
        # que existe hoje (mais forte que CLIENTE_ASSISTIDO, usado pelo MCP).
        # Hoje (`system/autonomy_state` ainda não é escrito por nada) isto
        # sempre resolve REQUIRE_APPROVAL e cai no mesmo fluxo de sempre, sem
        # mudar nenhum comportamento visível — só passa a bloquear no dia em
        # que autonomia for pausada ou posta em somente-preparação. Em
        # nenhum dos dois ramos de bloqueio o `pending` é descartado: o dono
        # pode tentar "Confirmar" de novo mais tarde (se destravar) ou usar o
        # botão "Cancelar" já existente — um bloqueio temporário de política
        # não deve apagar silenciosamente o rascunho que ele já aprovou.
        principal = Principal(
            uid=session.get("userId"),
            tipo=TipoPrincipal.DONO_INTERATIVO,
            canal="telegram",
            origem_humana=True,
        )
        decisao_piso = autonomy_policy.decisao_piso(db, principal, "schedule_whatsapp_message", pending)
        if decisao_piso is not None and decisao_piso.decision == Decisao.DENY:
            response_text = (
                "🚫 Bloqueado pela política de autonomia vigente: "
                + html.escape(decisao_piso.motivo_legivel or "ação não permitida agora.")
            )
            _persist_callback_turn("Botão: confirmar WhatsApp", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True
        if decisao_piso is not None and decisao_piso.decision == Decisao.PREPARE_ONLY:
            response_text = (
                "⏸️ Autonomia está em modo somente-preparação: esta mensagem não "
                "pode ser enviada agora. " + html.escape(decisao_piso.motivo_legivel or "")
            ).strip()
            _persist_callback_turn("Botão: confirmar WhatsApp", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

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

    else:
        return False
    return True
