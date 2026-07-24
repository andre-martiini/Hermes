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

def reconcile_by_amount_and_rubrics():
    print("=== INICIANDO CONCILIAÇÃO POR VALOR E RUBRICAS (FIXED BILLS) ===")
    
    fixed_bills_docs = list(db.collection('fixed_bills').stream())
    fixed_bills_by_month = {}
    
    for fb in fixed_bills_docs:
        d = fb.to_dict()
        m = d.get('month')
        y = d.get('year')
        amt = round(float(d.get('amount', 0.0)), 2)
        if m is not None and y is not None and amt > 0:
            key = (m, y, amt)
            if key not in fixed_bills_by_month:
                fixed_bills_by_month[key] = []
            fixed_bills_by_month[key].append({'ref': fb.reference, 'id': fb.id, 'data': d})
            
    rubrics = list(db.collection('bill_rubrics').stream())
    bill_rubrics = []
    for r in rubrics:
        d = r.to_dict()
        desc = d.get('description', '')
        keywords = [w.strip().lower() for w in re.split(r'[\(\)\s,-]+', desc) if len(w.strip()) > 2]
        bill_rubrics.append({'id': r.id, 'desc': desc.lower(), 'keywords': keywords, 'full_desc': desc})
        
    print(f"Carregadas {len(fixed_bills_docs)} contas fixas e {len(bill_rubrics)} rubricas.")

    trans_docs = list(db.collection('finance_transactions').stream())
    reconciled_count = 0
    
    for doc in trans_docs:
        d = doc.to_dict()
        if d.get('status') == 'deleted': continue
        desc = d.get('description', '').lower()
        amount = round(float(d.get('amount', 0.0)), 2)
        date_str = str(d.get('date', ''))
        dt = parse_dt(date_str)
        if not dt: continue
        
        month = dt.month - 1
        year = dt.year
        
        fb_key = (month, year, amount)
        found_fb = None
        if fb_key in fixed_bills_by_month and fixed_bills_by_month[fb_key]:
            found_fb = fixed_bills_by_month[fb_key][0]
            
        matched_rubric = None
        if not found_fb:
            for rb in bill_rubrics:
                if rb['desc'] in desc or any(kw in desc for kw in rb['keywords']):
                    matched_rubric = rb
                    break
            if matched_rubric:
                fb_docs = list(db.collection('fixed_bills').stream())
                for fb in fb_docs:
                    fb_data = fb.to_dict()
                    if fb_data.get('month') == month and fb_data.get('year') == year:
                        if fb_data.get('rubricId') == matched_rubric['id'] or matched_rubric['desc'] in fb_data.get('description', '').lower():
                            found_fb = {'ref': fb.reference, 'data': fb_data}
                            break
                        
        if found_fb:
            found_fb['ref'].update({
                'isPaid': True,
                'amount': amount,
                'data_pagamento': date_str,
                'google_message_id': d.get('google_message_id'),
                'pix_id': d.get('pix_id')
            })
            doc.reference.delete()
            reconciled_count += 1
            print(f"Conciliada Conta Fixa: '{found_fb['data'].get('description')}' (R$ {amount:.2f}) do mês {month+1}/{year} - Removido dos lançamentos avulsos: '{d.get('description')}'")
            
    print(f"\n=== FINALIZADO: {reconciled_count} lançamentos de Contas Fixas conciliados e removidos de finance_transactions! ===")

if __name__ == '__main__':
    reconcile_by_amount_and_rubrics()
