import os
import sys
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

def init_db():
    if not os.path.exists(KEY_FILE):
        print(f"ERRO: Arquivo de chave {KEY_FILE} não encontrado.")
        sys.exit(1)
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()

def reconcile_picpay_july():
    print("=================================================================")
    print("  HERMES - CONCILIAÇÃO BANCÁRIA PICPAY (JULHO / 2026)")
    print("=================================================================\n")

    # 1. Carregar transações do mês de Julho/2026
    tx_docs = list(db.collection('finance_transactions').stream())
    inc_docs = list(db.collection('finance_income').stream())

    july_txs = []
    for doc in tx_docs:
        d = doc.to_dict()
        if d.get('status') == 'deleted':
            continue
        m = d.get('month')
        y = d.get('year')
        date_str = d.get('date', '')
        if (m == 6 and y == 2026) or ('2026-07' in date_str):
            july_txs.append({'id': doc.id, 'ref': doc.reference, 'data': d})

    july_incs = []
    for doc in inc_docs:
        d = doc.to_dict()
        if d.get('status') == 'deleted':
            continue
        m = d.get('month')
        y = d.get('year')
        date_str = d.get('date', '')
        if (m == 6 and y == 2026) or ('2026-07' in date_str):
            july_incs.append({'id': doc.id, 'ref': doc.reference, 'data': d})

    print(f"--> Transações encontradas em Julho/2026: {len(july_txs)} débitos/saídas e {len(july_incs)} entradas.\n")

    # 2. Remoção de Falsos Débitos da XP (R$ 2.708,00 e R$ 1.343,00)
    xp_deleted_count = 0
    xp_deleted_amount = 0.0
    for item in july_txs:
        d = item['data']
        desc = d.get('description', '').lower()
        amt = float(d.get('amount', 0.0))
        doc_id = item['id']
        
        # XP debits identification
        is_xp_2708 = doc_id == 'M4gHGGCkWyrPjcHJWM21' or abs(amt - 2708.00) < 1.0 or abs(amt - 2708.53) < 1.0
        is_xp_1343 = doc_id == 'N321yFy5u3Fvkrsie40n' or abs(amt - 1343.00) < 1.0 or abs(amt - 1343.08) < 1.0
        
        if doc_id in ['M4gHGGCkWyrPjcHJWM21', 'N321yFy5u3Fvkrsie40n'] or (amt in [2708.0, 2708.53, 1343.0, 1343.08] and 'pix' in desc):
            print(f"[REMOVER XP] Deletando falso débito XP: '{d.get('description')}' (R$ {amt:.2f}) [Doc ID: {doc_id}]")
            item['ref'].delete()
            xp_deleted_count += 1
            xp_deleted_amount += amt

    # 3. Estorno de Correção Manual Sem Lastro (R$ 103,10)
    manual_deleted_count = 0
    for item in july_txs:
        d = item['data']
        desc = d.get('description', '').lower()
        amt = float(d.get('amount', 0.0))
        if abs(amt - 103.10) < 0.01 or ('ajuste' in desc and abs(amt - 103.10) < 1.0):
            print(f"[REMOVER MANUAL] Estornando ajuste sem lastro: '{d.get('description')}' (R$ {amt:.2f}) [Doc ID: {item['id']}]")
            item['ref'].delete()
            manual_deleted_count += 1

    # 4. Inserção do Pix Ausente (R$ 50,00 - THAIS DO ESTREITO MARTINI)
    thais_found = False
    for item in july_txs:
        d = item['data']
        desc = d.get('description', '').upper()
        amt = float(d.get('amount', 0.0))
        if 'THAIS' in desc and abs(amt - 50.00) < 0.01:
            thais_found = True
            print(f"[OK] Pix da Thais do Estreito Martini (R$ 50,00) já existe no banco.")
            break

    if not thais_found:
        print("[INSERIR PIX] Inserindo Pix ausente: THAIS DO ESTREITO MARTINI (R$ 50,00 em 20/07/2026)...")
        db.collection('finance_transactions').add({
            'description': 'Pix enviado: THAIS DO ESTREITO MARTINI',
            'amount': 50.00,
            'date': '2026-07-20T08:47:00.000Z',
            'day': 20,
            'month': 6,
            'year': 2026,
            'category': 'Pix',
            'provider': 'PicPay',
            'transactionId': '178454807466973735',
            'processing_state': 'RECONCILED',
            'createdAt': firestore.SERVER_TIMESTAMP
        })

    # 5. Inserção de Itens Não-Pix da Conta PicPay
    parking_found = False
    for item in july_txs:
        d = item['data']
        desc = d.get('description', '').lower()
        amt = float(d.get('amount', 0.0))
        if 'estacionamento' in desc and abs(amt - 3.10) < 0.01:
            parking_found = True
            break
    if not parking_found:
        print("[INSERIR DÉBITO] Inserindo débito não-Pix de estacionamento (R$ 3,10)...")
        db.collection('finance_transactions').add({
            'description': 'Débito: Estacionamento',
            'amount': 3.10,
            'date': '2026-07-20T12:00:00.000Z',
            'day': 20,
            'month': 6,
            'year': 2026,
            'category': 'Outros',
            'provider': 'PicPay',
            'processing_state': 'RECONCILED',
            'createdAt': firestore.SERVER_TIMESTAMP
        })

    payment_rcvd_found = False
    for item in july_incs:
        d = item['data']
        desc = d.get('description', '').lower()
        amt = float(d.get('amount', 0.0))
        if 'neuzinhahortela' in desc and abs(amt - 20.00) < 0.01:
            payment_rcvd_found = True
            break
    if not payment_rcvd_found:
        print("[INSERIR ENTRADA] Inserindo pagamento recebido: @neuzinhahortela (R$ 20,00)...")
        db.collection('finance_income').add({
            'description': 'Pagamento recebido: @neuzinhahortela',
            'amount': 20.00,
            'date': '2026-07-22T20:27:00.000Z',
            'day': 22,
            'month': 6,
            'year': 2026,
            'category': 'Renda Extra',
            'provider': 'PicPay',
            'isReceived': True,
            'createdAt': firestore.SERVER_TIMESTAMP
        })

    yield_found = False
    for item in july_incs:
        d = item['data']
        desc = d.get('description', '').lower()
        amt = float(d.get('amount', 0.0))
        if 'rendimento' in desc and abs(amt - 0.46) < 0.01:
            yield_found = True
            break
    if not yield_found:
        print("[INSERIR RENDIMENTO] Inserindo rendimento PicPay (R$ 0,46)...")
        db.collection('finance_income').add({
            'description': 'Rendimento PicPay em conta',
            'amount': 0.46,
            'date': '2026-07-23T23:59:00.000Z',
            'day': 23,
            'month': 6,
            'year': 2026,
            'category': 'Rendimentos',
            'provider': 'PicPay',
            'isReceived': True,
            'createdAt': firestore.SERVER_TIMESTAMP
        })

    print("\n=================================================================")
    print("  CONCILIAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=================================================================")

if __name__ == '__main__':
    reconcile_picpay_july()
