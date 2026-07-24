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

def clean_duplicates():
    print("=== INICIANDO LIMPEZA RETROATIVA DE DUPLICATAS ===")
    
    failed_keywords = ['não foi possível concluir', 'recusado', 'cancelado', 'estornado', 'falhou']
    
    for col in ['finance_transactions', 'finance_income']:
        docs = list(db.collection(col).stream())
        print(f"\nLendo {len(docs)} documentos da coleção '{col}'...")
        
        deleted_failed = 0
        valid_items = []
        
        for doc in docs:
            d = doc.to_dict()
            desc = d.get('description', '')
            if d.get('status') == 'deleted':
                continue
                
            if any(kw in desc.lower() for kw in failed_keywords):
                doc.reference.delete()
                deleted_failed += 1
                continue
                
            dt = parse_dt(d.get('date'))
            valid_items.append({
                'id': doc.id,
                'ref': doc.reference,
                'description': desc,
                'amount': float(d.get('amount', 0.0)),
                'date': dt,
                'date_str': str(d.get('date', '')),
                'google_message_id': d.get('google_message_id'),
                'pix_id': d.get('pix_id')
            })
            
        print(f"[{col}] Removidas {deleted_failed} transações de falha/recusa.")
        
        grouped = {}
        for item in valid_items:
            if item['date']:
                day_key = item['date'].strftime('%Y-%m-%d')
            else:
                day_key = item['date_str'][:10]
            
            key = (day_key, round(item['amount'], 2))
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(item)
            
        deleted_dups = 0
        for key, group in grouped.items():
            if len(group) > 1:
                def sort_priority(item):
                    desc = item['description'].lower()
                    score = 0
                    if 'google pay' in desc: score += 10
                    if item['pix_id']: score += 5
                    if item['google_message_id']: score += 2
                    score += len(desc) * 0.01
                    return score

                group.sort(key=sort_priority, reverse=True)
                keep_item = group[0]
                
                for dup in group[1:]:
                    print(f"Deletando duplicata [{col}]: '{dup['description']}' (R$ {dup['amount']:.2f}) do dia {key[0]} (Mantendo: '{keep_item['description']}')")
                    dup['ref'].delete()
                    deleted_dups += 1
                    
        print(f"[{col}] Removidas {deleted_dups} transações duplicadas!")

if __name__ == '__main__':
    clean_duplicates()
