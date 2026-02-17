
import firebase_admin
from firebase_admin import credentials, firestore
import json

def inspect():
    if not firebase_admin._apps:
        cred = credentials.Certificate('firebase_service_account_key.json')
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    with open('db_dump.txt', 'w', encoding='utf-8') as f:
        f.write("--- FINANCE TRANSACTIONS ---\n")
        docs = db.collection('finance_transactions').stream()
        for d in docs:
            data = d.to_dict()
            f.write(f"ID: {d.id} | Desc: {data.get('description')} | Val: {data.get('amount')} | Date: {data.get('date')}\n")
            
        f.write("\n--- FINANCE INCOME ---\n")
        docs = db.collection('finance_income').stream()
        for d in docs:
            data = d.to_dict()
            f.write(f"ID: {d.id} | Desc: {data.get('description')} | Val: {data.get('amount')} | Date: {data.get('date')}\n")

        f.write("\n--- TAREFAS (HIDDEN AUTO-SYNC) ---\n")
        t_docs = db.collection('tarefas').stream()
        for t in t_docs:
            t_data = t.to_dict()
            t_title = t_data.get('titulo', '')
            if 'gasto semanal' in t_title.lower():
                f.write(f"ID: {t.id} | Titulo: {t_title} | Status: {t_data.get('status')}\n")

        f.write("\n--- PROCESSED EMAILS ---\n")
        proc = db.collection('system').document('processed_emails').get()
        if proc.exists:
            ids = proc.to_dict().get('ids', [])
            f.write(f"Total processed IDs: {len(ids)}\n")
            for i in ids:
                f.write(f"{i}\n")
        else:
            f.write("Document 'system/processed_emails' NOT FOUND\n")
    print("Dump saved to db_dump.txt")

if __name__ == "__main__":
    inspect()
