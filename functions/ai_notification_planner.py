"""
Resto do antigo planejador proativo de notificações por IA.

O job diário `ai_notification_planner_daily` (agente Gemini que propunha até 3
notificações por dia) foi removido em 26/09/2026 por não ser usado (ver
docs/okf/operacoes/custos.md). Ficam aqui as peças ainda vivas:

- `_reserve_and_create_notification` e a janela `AI_PLANNER_WINDOW_*`, usados
  pelos detectores da fila `atencao` (ver `atencao.py`) para gravar em
  `scheduled_notifications` respeitando o teto diário;
- `dispatch_pending_ai_notifications` e `dispatch_scheduled_whatsapp_messages`,
  chamados a partir de `check_and_send_reminders` (main.py) — o motor de 1 em
  1 minuto que despacha os lembretes.
"""

import datetime
import os

from firebase_admin import firestore

AI_PLANNER_MAX_DAILY_NOTIFICATIONS = int(os.environ.get("AI_PLANNER_MAX_DAILY_NOTIFICATIONS", "3"))
AI_PLANNER_WINDOW_START = os.environ.get("AI_PLANNER_WINDOW_START", "07:00")
AI_PLANNER_WINDOW_END = os.environ.get("AI_PLANNER_WINDOW_END", "22:00")
AI_PLANNER_STALE_HOURS = 2

_CATEGORY_ICONS = {"acoes": "🗒️", "estrategia": "🎯", "geral": "🤖"}


def _ai_planner_counter_ref(db, today_str: str):
    return (
        db.collection("system_usage")
        .document("ai_planner_notifications")
        .collection("daily")
        .document(today_str)
    )


def _reserve_and_create_notification(db, today_str: str, doc_ref, doc_payload: dict) -> bool:
    """
    Reserva atomicamente uma vaga no teto diario e cria o documento da notificacao na
    MESMA transacao Firestore. Nasceu porque o antigo planejador (removido) executava
    tool calls em paralelo — um contador em memória permitiria duas threads lerem a
    mesma contagem antes de qualquer uma incrementar, estourando o teto. A transacao do Firestore serializa essa leitura+
    escrita mesmo entre threads e entre execucoes sobrepostas do scheduler, porque todas
    disputam o mesmo documento contador (chave = data de hoje).
    """
    counter_ref = _ai_planner_counter_ref(db, today_str)

    @firestore.transactional
    def _txn(transaction):
        snap = counter_ref.get(transaction=transaction)
        current = (snap.to_dict() or {}).get("count", 0) if snap.exists else 0
        if current >= AI_PLANNER_MAX_DAILY_NOTIFICATIONS:
            return False
        transaction.set(counter_ref, {"count": current + 1, "updated_at": firestore.SERVER_TIMESTAMP}, merge=True)
        transaction.set(doc_ref, doc_payload)
        return True

    try:
        return _txn(db.transaction())
    except Exception as exc:
        print(f"[AIPlanner] Falha ao reservar vaga de notificacao: {exc}")
        return False


def dispatch_pending_ai_notifications(db, now) -> None:
    """
    Consome `scheduled_notifications` com status 'pending' e send_at <= agora,
    enviando cada uma ao Telegram com botões de feedback (👍 útil / 👎 dispensar).
    Chamado a partir de check_and_send_reminders (main.py), a cada 1 minuto —
    o mesmo motor determinístico que já despacha os demais lembretes.
    """
    from main import _resolve_default_telegram_chat_id, _send_telegram_message_raw_with_keyboard

    try:
        pending = (
            db.collection("scheduled_notifications")
            .where("status", "==", "pending")
            .where("send_at", "<=", now)
            .stream()
        )
    except Exception as exc:
        print(f"[AINotifications] Falha ao consultar fila de notificações agendadas: {exc}")
        return

    for doc_snap in pending:
        data = doc_snap.to_dict() or {}
        title = str(data.get("title") or "Gaspar IA").strip()
        message = str(data.get("message") or "").strip()
        category = str(data.get("category") or "geral").strip()
        icon = _CATEGORY_ICONS.get(category, "🤖")

        chat_id = _resolve_default_telegram_chat_id(db)
        if not chat_id:
            print(f"[AINotifications] Nenhum chat_id do Telegram configurado; notificação {doc_snap.id} permanece pendente.")
            continue

        text = f"{icon} Gaspar IA — {title}\n\n{message}" if message else f"{icon} Gaspar IA — {title}"
        keyboard = [[
            {"text": "👍 Útil", "callback_data": f"ai_notif:{doc_snap.id}:useful"},
            {"text": "👎 Dispensar", "callback_data": f"ai_notif:{doc_snap.id}:dismiss"},
        ]]
        sent = _send_telegram_message_raw_with_keyboard(db, chat_id, text, keyboard)

        if sent:
            doc_snap.reference.update({"status": "sent", "sent_at": now.isoformat(), "telegram_sent": True})
            continue

        send_at_dt = data.get("send_at")
        stale = False
        try:
            if send_at_dt and (now - send_at_dt) > datetime.timedelta(hours=AI_PLANNER_STALE_HOURS):
                stale = True
        except Exception:
            pass

        if stale:
            doc_snap.reference.update({"status": "failed", "telegram_sent": False})
            print(f"[AINotifications] Notificação {doc_snap.id} expirou após falhas repetidas; marcada como 'failed'.")
        else:
            print(f"[AINotifications] Falha ao enviar notificação {doc_snap.id}; nova tentativa no próximo ciclo.")


def dispatch_scheduled_whatsapp_messages(db, now) -> None:
    """
    Consome `whatsapp_outbox` com status 'pending' e scheduled_for <= agora,
    enviando notificação no Telegram com 2 botões:
    1. [ ✅ Sim, Enviar no WhatsApp ] -> URL wa.me direct link
    2. [ ❌ Cancelar ] -> Callback button para desativar agendamento.
    """
    import urllib.parse
    from main import _cached_doc_get, _resolve_default_telegram_chat_id, _send_telegram_message_raw_with_keyboard

    # Coordenação com o worker local (services/whatsapp-capture): quando o envio automático
    # está habilitado E o worker deu sinal de vida recentemente, ele é quem reivindica e
    # envia de verdade via claimOutboxMessage — esta função fica de fora para não roubar o
    # doc 'pending' dele. Sem essa checagem, as duas rotinas competiam pelo mesmo doc a cada
    # minuto e a CF quase sempre vencia, fazendo o envio automático nunca acontecer de fato.
    try:
        settings_doc = _cached_doc_get(db, "system", "settings")
        auto_send_enabled = bool((settings_doc.to_dict() or {}).get("whatsapp_auto_send_enabled")) if settings_doc.exists else False
        if auto_send_enabled:
            worker_doc = db.collection("system").document("whatsapp_worker").get()
            worker_data = worker_doc.to_dict() or {} if worker_doc.exists else {}
            last_seen = worker_data.get("last_seen")
            # `ready` reflete o estado real do client whatsapp-web.js (ver writeHeartbeat em
            # services/whatsapp-capture/index.js) — um heartbeat recente sozinho não garante que
            # o worker está autenticado/conectado, só que o processo está de pé.
            if worker_data.get("ready") and last_seen and (now - last_seen) <= datetime.timedelta(minutes=10):
                return
    except Exception as exc:
        print(f"[WhatsAppOutbox] Falha ao checar coordenação com o worker local: {exc}")

    try:
        pending = (
            db.collection("whatsapp_outbox")
            .where("status", "==", "pending")
            .where("scheduled_for", "<=", now)
            .stream()
        )
    except Exception as exc:
        print(f"[WhatsAppOutbox] Falha ao consultar fila de WhatsApp agendados: {exc}")
        return

    for doc_snap in pending:
        data = doc_snap.to_dict() or {}
        to_number = str(data.get("to_number") or "").strip()
        content = str(data.get("content") or "").strip()
        contact_name = str(data.get("contact_name") or to_number).strip()

        chat_id = _resolve_default_telegram_chat_id(db)
        if not chat_id:
            print(f"[WhatsAppOutbox] Nenhum chat_id configurado no Telegram; agendamento {doc_snap.id} mantido.")
            continue

        msg_encoded = urllib.parse.quote(content)
        whatsapp_url = f"https://api.whatsapp.com/send?phone={to_number}&text={msg_encoded}"

        text = (
            f"📲 <b>WhatsApp Programado Chegou na Hora!</b>\n\n"
            f"👤 <b>Contato</b>: {contact_name} (<code>{to_number}</code>)\n"
            f"💬 <b>Mensagem</b>:\n<i>\"{content}\"</i>\n\n"
            f"Deseja enviar esta mensagem agora?"
        )
        keyboard = [
            [
                {"text": "✅ Sim, Enviar no WhatsApp", "url": whatsapp_url},
            ],
            [
                {"text": "☑️ Já enviei", "callback_data": f"wa_confirm_sent:{doc_snap.id}"},
                {"text": "❌ Cancelar", "callback_data": f"wa_cancel:{doc_snap.id}"}
            ]
        ]

        sent = _send_telegram_message_raw_with_keyboard(db, chat_id, text, keyboard)
        if sent:
            # Transacional e revalida o status (achado da revisão adversarial
            # de cancelar_envio_whatsapp, 22/09/2026): um `.update()` cru aqui
            # podia sobrescrever um cancelamento concorrente de volta para
            # 'notified' -- ver outbox_aprovacao.marcar_notificado.
            from outbox_aprovacao import marcar_notificado
            if marcar_notificado(db, doc_snap.id, notified_at=now):
                print(f"[WhatsAppOutbox] Agendamento {doc_snap.id} notificado via Telegram com sucesso.")
            else:
                print(
                    f"[WhatsAppOutbox] Agendamento {doc_snap.id} mudou de status "
                    "(provavelmente cancelado) entre a consulta e a notificação; "
                    "card do Telegram já enviado, mas status não foi sobrescrito."
                )
