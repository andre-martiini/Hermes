"""Auditoria read-only do modulo Saude (Hermes).

Nao escreve nada no Firestore. Gera um relatorio de contagem e cobertura de
campos para confirmar que a extensao do documento diario (health_exercise_logs)
com os novos campos clinicos nao perdeu nem alterou nenhum registro existente.

Uso: python scripts/audit_health_data.py
"""
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def audit_simple_collection(db, name):
    docs = list(db.collection(name).stream())
    print(f"\n=== {name} ===")
    print(f"Total de documentos: {len(docs)}")
    return docs


def audit_exercise_logs(db):
    docs = list(db.collection('health_exercise_logs').stream())
    print("\n=== health_exercise_logs (registro diario) ===")
    print(f"Total de documentos: {len(docs)}")
    if not docs:
        return

    ids = sorted(d.id for d in docs)
    print(f"Intervalo de datas: {ids[0]} a {ids[-1]}")

    field_counts = {
        'pain': 0,
        'walkBlocks': 0,
        'walk (legado)': 0,
        'radicular': 0,
        'strength': 0,
        'therapy': 0,
        'nutrition': 0,
        'sleepQuality': 0,
        'meds': 0,
        'triggers': 0,
        'note': 0,
        'pain.telegram_checked_at': 0,
    }
    malformed = []

    for d in docs:
        data = d.to_dict() or {}
        if data.get('pain') is not None:
            field_counts['pain'] += 1
            if isinstance(data['pain'], dict) and data['pain'].get('telegram_checked_at'):
                field_counts['pain.telegram_checked_at'] += 1
        if data.get('walkBlocks') is not None:
            field_counts['walkBlocks'] += 1
        if data.get('walk') is not None:
            field_counts['walk (legado)'] += 1
        for key in ('radicular', 'strength', 'therapy', 'nutrition', 'sleepQuality', 'meds', 'triggers', 'note'):
            if data.get(key) is not None:
                field_counts[key] += 1
        if not isinstance(data.get('id', d.id), str):
            malformed.append(d.id)

    print("\nCobertura de campos (quantos documentos tem cada campo preenchido):")
    for key, count in field_counts.items():
        pct = (count / len(docs) * 100) if docs else 0
        print(f"  {key:28s} {count:4d} / {len(docs)} ({pct:5.1f}%)")

    if malformed:
        print(f"\nAVISO: {len(malformed)} documento(s) com formato inesperado: {malformed[:20]}")
    else:
        print("\nNenhum documento com formato inesperado encontrado.")


def audit_exams(db):
    docs = list(db.collection('exames').stream())
    print("\n=== exames (arquivo medico) ===")
    print(f"Total de documentos: {len(docs)}")
    tipos = {}
    with_attachments = 0
    for d in docs:
        data = d.to_dict() or {}
        tipo = data.get('tipo', '(sem tipo)')
        tipos[tipo] = tipos.get(tipo, 0) + 1
        if data.get('pool_dados'):
            with_attachments += 1
    print(f"Por tipo: {tipos}")
    print(f"Com anexos: {with_attachments} / {len(docs)}")


def main():
    db = init_db()

    weights = audit_simple_collection(db, 'health_weights')
    waist = audit_simple_collection(db, 'health_waist')
    audit_simple_collection(db, 'health_telegram_reminders')
    audit_simple_collection(db, 'health_settings')
    audit_simple_collection(db, 'health_exercise_settings')

    if weights:
        dates = sorted(d.to_dict().get('date', '') for d in weights)
        print(f"Intervalo de datas (peso): {dates[0]} a {dates[-1]}")
    if waist:
        dates = sorted(d.to_dict().get('date', '') for d in waist)
        print(f"Intervalo de datas (cintura): {dates[0]} a {dates[-1]}")

    audit_exercise_logs(db)
    audit_exams(db)

    print("\n=== Fim da auditoria (nenhum dado foi alterado) ===")


if __name__ == '__main__':
    main()
