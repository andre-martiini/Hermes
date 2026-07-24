import os
from collections import defaultdict
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

def init_db():
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
        return None

def audit():
    for col in ['finance_transactions', 'finance_income']:
        print(f"\n=== {col} (agrupado por dia+valor, apenas leitura) ===")
        groups = defaultdict(list)
        for doc in db.collection(col).stream():
            d = doc.to_dict()
            if d.get('status') == 'deleted':
                continue
            dt = parse_dt(d.get('date'))
            day_key = dt.strftime('%Y-%m-%d') if dt else str(d.get('date'))[:10]
            amount = round(float(d.get('amount', 0.0)), 2)
            groups[(day_key, amount)].append({
                'id': doc.id,
                'desc': d.get('description', ''),
                'date': d.get('date'),
                'gid': d.get('google_message_id'),
                'pix': d.get('pix_id'),
            })

        any_found = False
        for (day, amount), items in sorted(groups.items()):
            if len(items) > 1:
                any_found = True
                print(f"  {day} R$ {amount:.2f} -> {len(items)} lançamentos:")
                for it in items:
                    print(f"    id={it['id']} date={it['date']} gid={it['gid']} pix={it['pix']} desc={it['desc']!r}")
        if not any_found:
            print("  Nenhum grupo com mais de 1 lançamento no mesmo dia+valor.")

if __name__ == '__main__':
    audit()
