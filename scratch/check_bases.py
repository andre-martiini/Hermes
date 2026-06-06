import sys
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Force UTF-8 output encoding for Windows command prompt
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    cred = credentials.Certificate('firebase_service_account_key.json')
    firebase_admin.initialize_app(cred)
except Exception as e:
    pass

db = firestore.client()

print("--- KNOWLEDGE BASES ---")
docs = db.collection('knowledge_bases').stream()
for d in docs:
    data = d.to_dict()
    print(f"ID: {d.id} | Nome: {data.get('nome')} | Emoji: {data.get('emoji')}")
