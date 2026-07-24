import os
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()

DOC_ID = 'NMSABd3FI8sU7Kv9Vcp7'  # lançamento manual duplicado ("Pix enviado: THAIS DO ESTREITO MARTINI")

def main():
    ref = db.collection('finance_transactions').document(DOC_ID)
    doc = ref.get()
    if not doc.exists:
        print(f"Documento {DOC_ID} não encontrado (já removido ou ID incorreto).")
        return
    d = doc.to_dict()
    print(f"Antes: {d}")
    if d.get('status') == 'deleted':
        print("Já estava marcado como deleted. Nada a fazer.")
        return
    ref.update({'status': 'deleted'})
    print(f"Documento {DOC_ID} marcado como status=deleted (soft-delete). Mantido o lançamento automático via Google Pay (id=wwjRCZh8YulEkMJoJrdu).")

if __name__ == '__main__':
    main()
