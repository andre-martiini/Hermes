import datetime
from firebase_admin import firestore

def schedule_whatsapp_message(db, contact_number: str, message: str, scheduled_time: str) -> str:
    """
    Agenda ou envia uma mensagem de WhatsApp inserindo na fila do Firestore.
    """
    try:
        contact_number = str(contact_number or "").strip()
        message = str(message or "").strip()
        scheduled_time = str(scheduled_time or "").strip()
        if not contact_number:
            raise ValueError("contact_number vazio")
        if not message:
            raise ValueError("message vazio")
        if not scheduled_time:
            raise ValueError("scheduled_time vazio")

        dt = datetime.datetime.fromisoformat(scheduled_time.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)

        doc_ref = db.collection("whatsapp_outbox").document()
        doc_ref.set({
            "to_number": contact_number,
            "content": message,
            "scheduled_for": dt,
            "status": "pending",
            "created_at": firestore.SERVER_TIMESTAMP,
        })

        return f"Mensagem agendada com sucesso para {contact_number} as {scheduled_time}."
    except Exception as e:
        return f"Erro ao agendar mensagem no WhatsApp: {e}"
