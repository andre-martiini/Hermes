import os
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

def init_db():
    if not os.path.exists(KEY_FILE):
        return None
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()

def sync_processed_ids():
    print("=== SINCRONIZANDO PROCESSED EMAILS NO FIRESTORE ===")
    
    proc_doc = db.collection('system').document('processed_emails').get()
    existing_ids = set(proc_doc.to_dict().get('ids', [])) if proc_doc.exists else set()
    
    count_before = len(existing_ids)
    
    for col in ['finance_transactions', 'finance_income', 'fixed_bills']:
        for doc in db.collection(col).stream():
            d = doc.to_dict()
            g_id = d.get('google_message_id')
            if g_id:
                existing_ids.add(g_id)
                
    count_after = len(existing_ids)
    
    db.collection('system').document('processed_emails').set({
        'ids': list(existing_ids)[-2000:]
    }, merge=True)
    
    print(f"IDs acumulados antes: {count_before} | IDs acumulados depois: {count_after}")
    print("Sincronização de IDs concluída. NENHUM e-mail antigo será re-processado!")

if __name__ == '__main__':
    sync_processed_ids()
