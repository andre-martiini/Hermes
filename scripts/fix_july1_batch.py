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

def main():
    # 1. Corrige o aporte real (XP -> PicPay), valor mal parseado
    income_ref = db.collection('finance_income').document('NvMdha1HhwLJ2tCjXHLB')
    d = income_ref.get().to_dict()
    print(f"Antes (income): amount={d.get('amount')} desc={d.get('description')!r}")
    income_ref.update({
        'amount': 4948.14,
        'description': 'Pix recebido: Aporte XP -> PicPay',
    })
    print("-> amount corrigido para 4948.14")

    # 2. Remove os dois lancamentos fantasma (Pix da XP que nunca tocaram o PicPay)
    for doc_id, label in [
        ('g8dEBI7FLA0ufZyGohOz', 'R$50,00 RONAN BENEDITO DA SILVA'),
        ('pFmMiPKbDc5G1Nl0tn7B', 'R$300,00 ALNINIVE CORREIA ARAUJO MARTINI'),
    ]:
        ref = db.collection('finance_transactions').document(doc_id)
        d = ref.get().to_dict()
        if not d or d.get('status') == 'deleted':
            print(f"{doc_id} ja deleted ou nao encontrado.")
            continue
        print(f"Antes (transaction {label}): amount={d.get('amount')} desc={d.get('description')!r}")
        ref.update({'status': 'deleted'})
        print(f"-> marcado como status=deleted (Pix interno da XP, nao movimenta o PicPay)")

if __name__ == '__main__':
    main()
