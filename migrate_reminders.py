import os
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

def migrate_reminders():
    if not os.path.exists(KEY_FILE):
        print("Service account key not found.")
        return

    # Check if app already initialized
    try:
        app = firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(KEY_FILE)
        app = firebase_admin.initialize_app(cred)

    db = firestore.client()

    docs = db.collection('tarefas').stream()
    count_updated = 0

    for doc in docs:
        data = doc.to_dict()
        if 'reminder_at' in data and 'reminder_sent' not in data:
            doc.reference.update({'reminder_sent': False})
            count_updated += 1
            print(f"Updated doc {doc.id} with reminder_sent=False")

    print(f"Reminder Migration finished. {count_updated} documents updated.")

if __name__ == '__main__':
    migrate_reminders()
