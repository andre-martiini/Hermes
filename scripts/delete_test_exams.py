"""Remove qualquer registro de teste em 'exames' cujo titulo comece com
'[TESTE' — convencao usada por create_test_exam_b6.py e
create_test_exams_a16.py. Nao apaga nada que nao bata com esse prefixo.

So rode depois que o revisor confirmar que ja verificou tudo que dependia
do(s) registro(s) -- apagar cedo demais destrava a verificacao (ja
aconteceu uma vez com o B6/A16).

Uso: python scripts/delete_test_exams.py
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
        if str(data.get('titulo', '')).startswith('[TESTE'):
            d.reference.delete()
            print(f"Apagado: exames/{d.id} — {data.get('titulo')}")
            deleted += 1
    print(f"Total apagado: {deleted}")


if __name__ == '__main__':
    main()
