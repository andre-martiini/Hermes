# -*- coding: utf-8 -*-
import os
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()

# Transferencias da XP para Andre, erroneamente lancadas como gasto Pix na conta PicPay
DOC_IDS = [
    'DYetOgj4HzeEt1pvolbb',  # R$ 2.708,53 - 01/07/2026
    'jlJZAPzsDWkXh9sYG1TW',  # R$ 1.343,08 - 08/07/2026
]

def main():
    for doc_id in DOC_IDS:
        ref = db.collection('finance_transactions').document(doc_id)
        doc = ref.get()
        if not doc.exists:
            print(f"Documento {doc_id} nao encontrado.")
            continue
        d = doc.to_dict()
        if d.get('status') == 'deleted':
            print(f"{doc_id} ja estava deleted.")
            continue
        print(f"Antes: id={doc_id} amount={d.get('amount')} date={d.get('date')} desc={d.get('description')!r}")
        ref.update({'status': 'deleted'})
        print(f"-> marcado como status=deleted (transferencia XP, nao e movimento do PicPay)")

if __name__ == '__main__':
    main()
