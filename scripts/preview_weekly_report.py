"""Preview read-only da placa de resultado do N14 (Relatorio Semanal), sem
gravar nada no Firestore -- so para validar a logica de build_weekly_report_card
antes/depois de o agendamento rodar.

Uso: python scripts/preview_weekly_report.py [YYYY-MM-DD]
     (a data deve ser um domingo; se omitida, usa o domingo mais recente)
"""
import sys
import json
from datetime import datetime, timedelta

sys.path.insert(0, 'functions')

import firebase_admin
from firebase_admin import credentials, firestore
from health_weekly_report import build_weekly_report_card, iso_week_key

KEY_FILE = 'firebase_service_account_key.json'


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def most_recent_sunday() -> str:
    today = datetime.now()
    offset = (today.weekday() - 6) % 7  # weekday(): Mon=0..Sun=6
    return (today - timedelta(days=offset)).strftime('%Y-%m-%d')


def main():
    week_end = sys.argv[1] if len(sys.argv) > 1 else most_recent_sunday()
    db = init_db()
    card = build_weekly_report_card(db, week_end)
    print(f"Relatorio (preview, nao gravado): {iso_week_key(week_end)}")
    print(json.dumps(card, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
