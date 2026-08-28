"""Enfileira uma mensagem de WhatsApp para o worker enviar.

## Enfileirar nao e enviar

Quem grava aqui e o Hermes; quem entrega e o worker local, num cron separado.
Entre os dois ha tudo o que pode dar errado: sessao caida, numero fora do
WhatsApp, destino recusado.

Ate 28/08/2026 esta funcao devolvia "Mensagem agendada com sucesso", e era so o
que o agente sabia. Nesse dia dois envios foram aceitos, falharam no worker e o
agente afirmou ao dono que tinha mandado — sem ter como saber. A frase estava
tecnicamente correta e mesmo assim enganava, porque "sucesso" e lido como
entrega.

Agora o retorno diz o que de fato aconteceu e devolve o `job_id`, para o estado
real poder ser consultado depois em `whatsapp_outbox/{job_id}`.
"""

import datetime

from firebase_admin import firestore


def schedule_whatsapp_message(db, contact_number: str, message: str, scheduled_time: str) -> str:
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

        # O numero e normalizado no envio (`resolverDestino` no worker, que usa
        # `client.getNumberId`); aqui so se recusa o que nao tem digito nenhum,
        # para o erro sair antes de virar um job condenado.
        if not any(c.isdigit() for c in contact_number):
            raise ValueError(f"contact_number sem digitos: {contact_number!r}")

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

        return (
            f"Mensagem ENFILEIRADA (ainda nao enviada) para {contact_number}, "
            f"prevista para {scheduled_time}. job_id={doc_ref.id}. "
            "A entrega e feita pelo worker local e pode falhar depois disto — "
            "consulte whatsapp_outbox/{} para o estado real antes de afirmar ao "
            "usuario que a mensagem foi enviada.".format(doc_ref.id)
        )
    except Exception as e:
        return f"Erro ao agendar mensagem no WhatsApp: {e}"
