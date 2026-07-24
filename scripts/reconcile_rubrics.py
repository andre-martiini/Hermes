import os
import sys
import re
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

def parse_dt(d_str):
    if not d_str: return None
    try:
        dt = datetime.fromisoformat(d_str.replace('Z', '+00:00'))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        try:
            parts = [int(x) for x in d_str.split('T')[0].split('-')]
            return datetime(parts[0], parts[1], parts[2], tzinfo=timezone.utc)
        except:
            return None

def reconcile_existing_transactions():
    print("=== INICIANDO CONCILIAÇÃO RETROATIVA DE RUBRICAS DE CONTAS (SAÍDAS) ===")
    
    rubrics = list(db.collection('bill_rubrics').stream())
    bill_rubrics = []
    for r in rubrics:
        d = r.to_dict()
        desc = d.get('description', '')
        keywords = [w.strip().lower() for w in re.split(r'[\(\)\s,-]+', desc) if len(w.strip()) > 2]
        bill_rubrics.append({'id': r.id, 'desc': desc.lower(), 'keywords': keywords, 'full_desc': desc})
        
    print(f"Carregadas {len(bill_rubrics)} rubricas de contas de saída.")
    
    trans_docs = list(db.collection('finance_transactions').stream())
    print(f"Analisando {len(trans_docs)} transações ativas...")
    
    reconciled_count = 0
    
    for doc in trans_docs:
        d = doc.to_dict()
        if d.get('status') == 'deleted': continue
        desc = d.get('description', '').lower()
        amount = float(d.get('amount', 0.0))
        date_str = str(d.get('date', ''))
        dt = parse_dt(date_str)
        if not dt: continue
        
        matched_rubric = None
        for rb in bill_rubrics:
            if rb['desc'] in desc or any(kw in desc for kw in rb['keywords']):
                matched_rubric = rb
                break
                
        if matched_rubric:
            month = dt.month - 1
            year = dt.year
            
            fb_docs = list(db.collection('fixed_bills').where('month', '==', month).where('year', '==', year).stream())
            found_fb = None
            for fb in fb_docs:
                fb_data = fb.to_dict()
                if fb_data.get('rubricId') == matched_rubric['id'] or matched_rubric['desc'] in fb_data.get('description', '').lower():
                    found_fb = fb
                    break
                    
            if found_fb:
                found_fb.reference.update({
                    'isPaid': True,
                    'amount': amount,
                    'data_pagamento': date_str,
                    'google_message_id': d.get('google_message_id'),
                    'pix_id': d.get('pix_id')
                })
                print(f"Baixada Conta Fixa existente: '{matched_rubric['full_desc']}' R$ {amount:.2f} ({month+1}/{year})")
            else:
                db.collection('fixed_bills').add({
                    'description': matched_rubric['full_desc'],
                    'amount': amount,
                    'dueDay': dt.day,
                    'month': month,
                    'year': year,
                    'isPaid': True,
                    'rubricId': matched_rubric['id'],
                    'google_message_id': d.get('google_message_id'),
                    'pix_id': d.get('pix_id'),
                    'created_at': date_str
                })
                print(f"Criada/Baixada Conta Fixa: '{matched_rubric['full_desc']}' R$ {amount:.2f} ({month+1}/{year})")
                
            doc.reference.delete()
            reconciled_count += 1
            print(f"Removido dos lançamentos avulsos: '{d.get('description')}' (R$ {amount:.2f})")

    print(f"\n=== CONCILIAÇÃO FINALIZADA: {reconciled_count} lançamentos conciliados e removidos das transações avulsas! ===")

if __name__ == '__main__':
    reconcile_existing_transactions()
