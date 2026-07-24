# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import firebase_admin
from firebase_admin import credentials as fb_credentials, firestore

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
KEY_FILE = 'firebase_service_account_key.json'

def get_gmail():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    return build('gmail', 'v1', credentials=creds)

def get_db():
    cred = fb_credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()

gmail = get_gmail()
db = get_db()

# Todos os IDs do Gmail vinculados a lancamentos ativos no Firestore
gid_map = {}
for col in ['finance_transactions', 'finance_income']:
    for doc in db.collection(col).stream():
        d = doc.to_dict()
        if d.get('status') == 'deleted':
            continue
        gid = d.get('google_message_id')
        if gid:
            gid_map[gid] = {'col': col, 'id': doc.id, 'amount': d.get('amount'), 'date': d.get('date'), 'desc': d.get('description')}

print(f"Total de lancamentos ativos com google_message_id: {len(gid_map)}")

# Busca todos os emails da XP no periodo
query = 'from:xpi.com.br after:2026/02/01'
messages = []
page_token = None
while True:
    results = gmail.users().messages().list(userId='me', q=query, maxResults=100, pageToken=page_token).execute()
    batch = results.get('messages', [])
    messages.extend(batch)
    page_token = results.get('nextPageToken')
    if not page_token:
        break

print(f"Total de e-mails de xpi.com.br encontrados no Gmail: {len(messages)}")

xp_ids = {m['id'] for m in messages}
contaminated = [gid for gid in gid_map if gid in xp_ids]

print(f"\n=== Lancamentos no Firestore originados de e-mails da XP (CONTAMINACAO) ===")
total = 0.0
for gid in contaminated:
    info = gid_map[gid]
    print(f"  {info['col']}/{info['id']} amount={info['amount']} date={info['date']} desc={info['desc']!r} gid={gid}")
    total += float(info['amount'] or 0)
print(f"\nTotal contaminado: R$ {total:.2f} em {len(contaminated)} lancamentos")
