"""Migra os lembretes do Telegram para os novos check-ins guiados (N5).

- Remove o lembrete antigo 'pain_checkin' (Check-in lombar), substituido
  pelo fluxo guiado da noite.
- Cria/atualiza 'morning_checkin' (12:00) e 'night_checkin'.
- ATENCAO: o night_checkin e gravado com o horario passado em --night-time
  (default 20:00, para o teste de hoje). O default de codigo e 19:00; depois
  do teste, ajuste para 19:00 pela tela de Lembretes ou rode de novo com
  --night-time 19:00.

Uso: python scripts/migrate_checkin_reminders.py [--night-time HH:MM]
"""
import sys
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

KEY_FILE = 'firebase_service_account_key.json'


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def main():
    night_time = '20:00'
    if '--night-time' in sys.argv:
        night_time = sys.argv[sys.argv.index('--night-time') + 1]

    db = init_db()
    now_iso = datetime.now(timezone.utc).isoformat()

    old_ref = db.collection('health_telegram_reminders').document('pain_checkin')
    if old_ref.get().exists:
        old_ref.delete()
        print("Apagado: health_telegram_reminders/pain_checkin (Check-in lombar)")
    else:
        print("pain_checkin nao tinha documento no Firestore (era so default de codigo) — nada a apagar.")

    db.collection('health_telegram_reminders').document('morning_checkin').set({
        'id': 'morning_checkin',
        'title': 'Check-in da manhã',
        'message': 'André, hora do check-in da manhã — 3 perguntas rápidas sobre dor e sono.',
        'time': '12:00',
        'enabled': True,
        'daysOfWeek': [0, 1, 2, 3, 4, 5, 6],
        'category': 'checkin_morning',
        'data_atualizacao': now_iso,
    }, merge=True)
    print("Gravado: morning_checkin as 12:00")

    db.collection('health_telegram_reminders').document('night_checkin').set({
        'id': 'night_checkin',
        'title': 'Check-in da noite',
        'message': 'André, hora do check-in da noite — uma pergunta por vez, leva menos de 1 minuto.',
        'time': night_time,
        'enabled': True,
        'daysOfWeek': [0, 1, 2, 3, 4, 5, 6],
        'category': 'checkin_night',
        'data_atualizacao': now_iso,
    }, merge=True)
    print(f"Gravado: night_checkin as {night_time}")
    if night_time != '19:00':
        print("LEMBRETE: depois do teste, ajustar night_checkin para 19:00 (pela tela ou --night-time 19:00).")


if __name__ == '__main__':
    main()
