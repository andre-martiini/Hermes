"""Cadastra a XP em `bill_pdf_password_configs`, no mesmo lugar e do mesmo
jeito que a Elo ja esta cadastrada — so metadado (remetente, rotulo,
identificador do segredo). A SENHA continua sendo digitada pelo Andre na
tela do Gaspar (Configuracoes > financeiro), nunca por este script nem por
chat: sem isso o documento nem aparece na lista de senhas da tela.

Idempotente: so cria se o documento "xp" ainda nao existir. Reexecutar e
seguro.

Uso: python scripts/seed_bill_pdf_password_config_xp.py
"""
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'

CONFIG = {
    'id': 'xp',
    'label': 'Fatura XP',
    'kind': 'pdf',
    'senders': ['fatura@xpi.com.br'],
    'secret_id': 'bill-pdf-password-xp',
    'rubric_id': '',
    'active': True,
}


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def main():
    db = init_db()
    ref = db.collection('bill_pdf_password_configs').document(CONFIG['id'])
    if ref.get().exists:
        print(f"ja existe: bill_pdf_password_configs/{CONFIG['id']} — nada feito.")
        return
    ref.set(CONFIG)
    print(f"criado: bill_pdf_password_configs/{CONFIG['id']} ({CONFIG['label']}, "
          f"remetente {CONFIG['senders'][0]}).")
    print("Falta so o Andre digitar a senha do PDF na tela do Gaspar "
          "(Configuracoes > financeiro) para a fatura comecar a entrar sozinha.")


if __name__ == '__main__':
    main()
