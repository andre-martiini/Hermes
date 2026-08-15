"""Cria dois registros de teste em 'exames' para verificar o achado A16
(badge de proximidade da proxima reavaliacao no card do arquivo medico).

Um com proximaReavaliacao ~20 dias no futuro (estado ambar esperado) e
outro com data ja passada (estado vermelho "atrasada" esperado).

Claramente identificados pelo prefixo '[TESTE' no titulo -- use
scripts/delete_test_exams.py para remover depois que o revisor confirmar
os dois estados.

Uso: python scripts/create_test_exams_a16.py
"""
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone

KEY_FILE = 'firebase_service_account_key.json'


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def main():
    db = init_db()
    today = datetime.now(timezone.utc)

    ambar_data = (today + timedelta(days=20)).strftime('%Y-%m-%d')
    atrasada_data = (today - timedelta(days=9)).strftime('%Y-%m-%d')

    registros = [
        {
            'titulo': '[TESTE A16 — âmbar — apagar apos revisao] Reavaliacao proxima',
            'data': today.strftime('%Y-%m-%d'),
            'tipo': 'consulta',
            'doutor_local': 'Dr. Igor Zanon — Clinica Ortopedica',
            'resultados': 'Registro de teste para verificar o estado ambar do badge de reavaliacao (achado A16).',
            'data_criacao': today.isoformat(),
            'proximaReavaliacao': ambar_data,
            'tags': ['teste-a16'],
        },
        {
            'titulo': '[TESTE A16 — atrasada — apagar apos revisao] Reavaliacao vencida',
            'data': today.strftime('%Y-%m-%d'),
            'tipo': 'consulta',
            'doutor_local': 'Dr. Igor Zanon — Clinica Ortopedica',
            'resultados': 'Registro de teste para verificar o estado vermelho ("atrasada") do badge de reavaliacao (achado A16).',
            'data_criacao': today.isoformat(),
            'proximaReavaliacao': atrasada_data,
            'tags': ['teste-a16'],
        },
    ]

    for registro in registros:
        doc_ref = db.collection('exames').document()
        doc_ref.set(registro)
        print(f"Criado: exames/{doc_ref.id} — {registro['titulo']} — proximaReavaliacao {registro['proximaReavaliacao']}")


if __name__ == '__main__':
    main()
