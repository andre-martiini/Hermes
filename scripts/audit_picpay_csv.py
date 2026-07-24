import os
import csv
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

def init_db():
    if not os.path.exists(KEY_FILE):
        print(f"ERRO: {KEY_FILE} não encontrado.")
        return None
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()

def audit():
    csv_file = r'C:\Users\T-GAMER\Downloads\extrato-2026-07-01-2026-07-23.csv'
    if not os.path.exists(csv_file):
        print("CSV não encontrado.")
        return

    csv_rows = []
    with open(csv_file, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            csv_rows.append(row)

    print(f"Total de linhas no extrato CSV: {len(csv_rows)}")

    pix_debits_csv = []
    for r in csv_rows:
        tipo = r.get('tipo', '')
        val_raw = r.get('valor', '').replace('−', '-').replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        try:
            val = float(val_raw)
        except:
            val = 0.0
        if 'Pix enviado' in tipo:
            pix_debits_csv.append({'data': r.get('data'), 'destino': r.get('origem / destino'), 'valor': abs(val)})

    print(f"Total de Pix enviados no CSV do PicPay: {len(pix_debits_csv)} -- Soma: R$ {sum(p['valor'] for p in pix_debits_csv):.2f}")

    # Fetch DB items
    docs = list(db.collection('finance_transactions').stream())
    july_db = []
    for d in docs:
        data = d.to_dict()
        if data.get('status') == 'deleted':
            continue
        m = data.get('month')
        y = data.get('year')
        date_str = data.get('date', '')
        if (m == 6 and y == 2026) or ('2026-07' in date_str):
            july_db.append(data)

    pix_db = [t for t in july_db if t.get('category') == 'Pix' or 'pix' in t.get('description', '').lower()]
    print(f"Total de Pix em finance_transactions no DB: {len(pix_db)} -- Soma: R$ {sum(float(t.get('amount', 0)) for t in pix_db):.2f}")

if __name__ == '__main__':
    audit()
