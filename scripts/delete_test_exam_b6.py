"""Remove o(s) registro(s) de teste criado(s) por create_test_exam_b6.py.

Localiza pelo prefixo '[TESTE B6' no titulo -- nao apaga nada que nao bata
com esse prefixo.

Uso: python scripts/delete_test_exam_b6.py
"""
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def main():
    db = init_db()
    docs = list(db.collection('exames').stream())
    deleted = 0
    for d in docs:
        data = d.to_dict() or {}
        if str(data.get('titulo', '')).startswith('[TESTE B6'):
            d.reference.delete()
            print(f"Apagado: exames/{d.id} — {data.get('titulo')}")
            deleted += 1
    print(f"Total apagado: {deleted}")


if __name__ == '__main__':
    main()
