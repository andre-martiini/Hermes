import os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

KEY_FILE = 'c:/Users/T-GAMER/Documents/gestao-Hermes/firebase_service_account_key.json'

def list_tasks():
    if not os.path.exists(KEY_FILE):
        print("Service account key not found.")
        return

    cred = credentials.Certificate(KEY_FILE)
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred)
        
    db = firestore.client()

    today = "2026-04-14"
    tomorrow = "2026-04-15"

    print(f"--- Tarefas para {today} ---")
    docs_today = db.collection('tarefas').where('data_limite', '==', today).stream()
    for doc in docs_today:
        data = doc.to_dict()
        print(f"- {data.get('titulo')} (ID: {doc.id})")

    print(f"\n--- Tarefas para {tomorrow} ---")
    docs_tomorrow = db.collection('tarefas').where('data_limite', '==', tomorrow).stream()
    for doc in docs_tomorrow:
        data = doc.to_dict()
        print(f"- {data.get('titulo')} (ID: {doc.id})")

if __name__ == '__main__':
    list_tasks()
