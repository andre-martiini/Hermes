import os
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

def migrate():
    if not os.path.exists(KEY_FILE):
        print("Service account key not found.")
        return

    cred = credentials.Certificate(KEY_FILE)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    # 1. Update origin == 'google' -> 'manual'
    # 2. Update categoria -> area_tematica
    docs = db.collection('tarefas').stream()
    count_updated = 0

    for doc in docs:
        data = doc.to_dict()
        updates = {}
        updated = False

        if data.get('origem') == 'google':
            updates['origem'] = 'manual'
            updated = True
        
        if 'categoria' in data:
            updates['area_tematica'] = data['categoria']
            updates['categoria'] = firestore.DELETE_FIELD
            updated = True
        
        if updated:
            doc.reference.update(updates)
            count_updated += 1
            print(f"Updated doc {doc.id}")

    print(f"Migration finished. {count_updated} documents updated.")

if __name__ == '__main__':
    migrate()
