"""Deduplicação idempotente de eventos com efeito (ex.: webhooks) via Firestore.

Contrato: check_and_register NUNCA "permite processamento" silenciosamente
quando não consegue determinar com segurança se o update_id já foi
processado. Falha de transação ou backend sem suporte a transação retornam
um resultado recuperável SEM efeito (RESULTADO_ERRO_TRANSACAO /
RESULTADO_ERRO_CONFIGURACAO) -- o chamador deve tratar isso como falha
visível (ex.: responder com status HTTP não-2xx para a entrega poder ser
repetida depois), nunca como processamento silencioso disfarçado de sucesso.
Ver docs/plano-hermes-autonomo-2026-09-06.md, P01 passo 4.
"""

from datetime import datetime, timezone, timedelta

from firebase_admin import firestore as _fs

RESULTADO_NOVO = "novo"
RESULTADO_DUPLICADO = "duplicado"
RESULTADO_ERRO_CONFIGURACAO = "erro_configuracao"
RESULTADO_ERRO_TRANSACAO = "erro_transacao"


def check_and_register(db, update_id: str | int) -> str:
    """Verifica e registra um update_id de forma idempotente e atômica.

    Retorna:
      RESULTADO_NOVO: update_id é novo -- o chamador deve processar o evento.
      RESULTADO_DUPLICADO: update_id já foi registrado -- não processar de novo.
      RESULTADO_ERRO_CONFIGURACAO: backend Firestore sem suporte a transação --
        não é seguro decidir; não processar agora.
      RESULTADO_ERRO_TRANSACAO: a transação de verificação/registro falhou --
        não é seguro decidir; não processar agora.

    Em ambos os casos de erro, NENHUM efeito é produzido e nada é registrado
    como processado -- o chamador deve devolver um resultado recuperável
    (ex.: status HTTP não-2xx) para que a entrega possa ser repetida depois,
    em vez de "permitir processamento" silenciosamente sob incerteza.

    Sem update_id não há o que deduplicar: retorna RESULTADO_NOVO direto.
    """
    if not update_id:
        return RESULTADO_NOVO

    if not hasattr(db, "transaction"):
        print(
            f"[Idempotency] Backend Firestore sem suporte a transação; "
            f"update_id={update_id} recusado (sem efeito) para evitar "
            f"processamento duplicado não verificável."
        )
        return RESULTADO_ERRO_CONFIGURACAO

    ref = db.collection("idempotency").document(str(update_id))
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    @_fs.transactional
    def _txn(transaction):
        snap = ref.get(transaction=transaction)
        if snap.exists:
            return RESULTADO_DUPLICADO
        transaction.set(ref, {
            "processed_at": _fs.SERVER_TIMESTAMP,
            "expires_at": expires_at,
        })
        return RESULTADO_NOVO

    try:
        txn = db.transaction()
        return _txn(txn)
    except Exception as exc:
        # Falha real de transação (ex.: Aborted após esgotar tentativas). Não
        # há fallback para "permitir processamento" -- retorna erro explícito
        # em vez de arriscar processar (e potencialmente duplicar o efeito
        # de) um evento que não foi possível confirmar como novo.
        print(f"[Idempotency] Transação Firestore falhou para update_id={update_id}: {exc}")
        return RESULTADO_ERRO_TRANSACAO
