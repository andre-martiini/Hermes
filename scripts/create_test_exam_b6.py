"""Cria um unico registro de teste em 'exames' para verificar o achado B6
(campos achadosChave/profissional/especialidade/proximaReavaliacao/tags no card).

Claramente identificado como teste no titulo, para nao ser confundido com um
registro medico real. Rode scripts/delete_test_exam_b6.py depois que o
revisor confirmar, para nao deixar lixo na base.

Uso: python scripts/create_test_exam_b6.py
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
    proxima_reavaliacao = (today + timedelta(days=20)).strftime('%Y-%m-%d')

    doc_ref = db.collection('exames').document()
    doc_ref.set({
        'titulo': '[TESTE B6 — apagar apos revisao] Retorno ortopedico',
        'data': today.strftime('%Y-%m-%d'),
        'tipo': 'consulta',
        'doutor_local': 'Dr. Igor Zanon — Clinica Ortopedica',
        'resultados': 'Registro de teste criado para verificar renderizacao dos campos '
                       'estruturados no card do arquivo medico (achado B6 da revisao).',
        'data_criacao': today.isoformat(),
        'achadosChave': 'Reducao de 40% na compressao radicular comparado ao exame anterior.',
        'profissional': 'Dr. Igor Zanon',
        'especialidade': 'Ortopedia — Coluna',
        'proximaReavaliacao': proxima_reavaliacao,
        'tags': ['teste-b6', 'coluna-lombar'],
    })
    print(f"Documento de teste criado: exames/{doc_ref.id}")
    print(f"proximaReavaliacao: {proxima_reavaliacao}")


if __name__ == '__main__':
    main()
