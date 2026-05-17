import datetime
from firebase_admin import firestore

def schedule_whatsapp_message(db, contact_number: str, message: str, scheduled_time: str) -> str:
    """
    Agenda ou envia uma mensagem de WhatsApp inserindo na fila do Firestore.
    """
    try:
        # Convert ISO 8601 string to a datetime object
        dt = datetime.datetime.fromisoformat(scheduled_time.replace("Z", "+00:00"))

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
