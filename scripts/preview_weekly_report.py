"""Preview read-only do N14 (Relatorio Semanal) -- placa (Fase 1), ajuste
(Fase 2) e auditoria (Fase 3, so a parte em codigo), sem gravar nada no
Firestore. Nao chama o Gemini -- a narrativa final (generate_weekly_narrative)
depende de importar functions/main.py, que ja inicializa o proprio Firebase
Admin app, e duplicar isso aqui so pra testar prosa nao vale o risco de
conflito com o init_db() deste script.

Uso: python scripts/preview_weekly_report.py [YYYY-MM-DD]
     (a data deve ser um domingo; se omitida, usa o domingo mais recente)
"""
import sys
import json
from datetime import datetime, timedelta

sys.path.insert(0, 'functions')

import firebase_admin
from firebase_admin import credentials, firestore
from health_weekly_report import (
    build_weekly_report_card,
    build_weekly_adjustment,
    build_weekly_audit,
    _audit_fallback_text,
    _logs_for_week,
    _week_bounds,
    iso_week_key,
)

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

    week_start, _ = _week_bounds(week_end)
    week_logs = _logs_for_week(db, week_start, week_end)

    prev_week_end = (datetime.strptime(week_start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_doc = db.collection("health_weekly_reports").document(iso_week_key(prev_week_end)).get()
    prev_report = prev_doc.to_dict() if prev_doc.exists else None
    prev_card = prev_report.get("card") if prev_report else None

    adjustment = build_weekly_adjustment(week_logs, card, prev_card)
    print("\n--- Ajuste (Fase 2) ---")
    print(json.dumps(adjustment, indent=2, ensure_ascii=False))

    audit = build_weekly_audit(prev_report, card)
    audit_text = _audit_fallback_text(audit)
    print("\n--- Auditoria (Fase 3, parte em codigo) ---")
    print(json.dumps(audit, indent=2, ensure_ascii=False, default=str))
    print(f"Texto seco da auditoria: {audit_text}")


if __name__ == '__main__':
    main()
