"""Deduplicação idempotente por chave (ex.: delivery_id de webhook, update_id
de bot) usando um documento-sentinela em `idempotency/{key}`, criado dentro de
uma transação Firestore para que duas chamadas concorrentes com a mesma chave
não possam ambas concluir que a chave é nova.
"""

from datetime import datetime, timezone, timedelta

from firebase_admin import firestore as _fs


def check_and_register(db, update_id: str | int) -> bool:
    """Retorna True se `update_id` é novo (o chamador deve processar, e o
    documento-sentinela já foi registrado atomicamente); False se já
    processado antes (o chamador deve pular, sem efeito).

    Se a verificação transacional falhar por um motivo real — Firestore
    indisponível, contenção esgotando tentativas etc. — a exceção original é
    propagada, e NÃO é convertida silenciosamente em "pode processar" (achado
    do plano de autonomia, P01 passo 4: erro de idempotência em caminho com
    efeito deve virar resultado recuperável sem efeito, nunca "permitir
    processamento" às escondidas). Um erro aqui significa que não dá para
    garantir que a chave já foi vista; processar mesmo assim arrisca duplicar
    justamente o efeito que a idempotência existe para evitar. Cabe ao
    chamador tratar essa exceção como "recuperável sem efeito" — por exemplo,
    respondendo um erro HTTP a um webhook para que o remetente reentregue mais
    tarde com a mesma chave (GitHub e a maioria dos provedores de webhook já
    fazem isso automaticamente para respostas não-2xx).
    """
    if not update_id:
        return True

    ref = db.collection("idempotency").document(str(update_id))
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    @_fs.transactional
    def _txn(transaction, ref):
        snap = ref.get(transaction=transaction)
        if snap.exists:
            return False
        transaction.set(ref, {
            "processed_at": _fs.SERVER_TIMESTAMP,
            "expires_at": expires_at,
        })
        return True

    txn = db.transaction()
    return _txn(txn, ref)
