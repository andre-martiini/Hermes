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
    # 1. Corrige data do estacionamento (real: 04/07 10:30, estava 20/07)
    ref = db.collection('finance_transactions').document('MlkMDR2QBGO2F4EzqWlk')
    d = ref.get().to_dict()
    print(f"Antes (estacionamento): date={d.get('date')} day={d.get('day')}")
    ref.update({
        'date': '2026-07-04T13:30:00.000Z',  # 10:30 BRT (UTC-3)
        'day': 4,
    })
    print("-> data corrigida para 04/07/2026")

    # 2. Corrige data do rendimento (real: 01/07 09:56, estava 23/07)
    ref = db.collection('finance_income').document('kWbqNYKXSkxEMGm4oQAi')
    d = ref.get().to_dict()
    print(f"\nAntes (rendimento): date={d.get('date')} day={d.get('day')} month={d.get('month')}")
    ref.update({
        'date': '2026-07-01T12:56:00.000Z',  # 09:56 BRT (UTC-3)
        'day': 1,
        'month': 6,  # 0-indexed (julho)
    })
    print("-> data corrigida para 01/07/2026")

    # 3. Adiciona o pagamento recebido faltante (22/07, R$20,00, @neuzinhahortela)
    new_record = {
        'description': 'Pagamento recebido: @neuzinhahortela',
        'amount': 20.0,
        'day': 22,
        'month': 6,  # julho, 0-indexed
        'year': 2026,
        'category': 'Geral',
        'isReceived': True,
        'date': '2026-07-22T23:27:00.000Z',  # 20:27 BRT (UTC-3)
        'provider': 'PicPay',
    }
    doc_ref = db.collection('finance_income').add(new_record)[1]
    print(f"\n-> Novo lancamento criado: finance_income/{doc_ref.id} (R$ 20,00, 22/07/2026)")

if __name__ == '__main__':
    main()
