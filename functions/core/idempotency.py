from datetime import datetime, timezone, timedelta

from firebase_admin import firestore as _fs


def check_and_register(db, update_id: str | int) -> bool:
    """Retorna True se o update_id é novo (deve processar). False se duplicado."""
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

    try:
        txn = db.transaction()
        return _txn(txn, ref)
    except Exception:
        return True  # em caso de erro, permite processamento
