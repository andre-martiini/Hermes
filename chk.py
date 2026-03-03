import firebase_admin
from firebase_admin import credentials, firestore
cred = credentials.Certificate('firebase_service_account_key.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

for doc in db.collection('tarefas').where('google_calendar_id', '!=', '').stream():
    d = doc.to_dict()
    print(f"Tarefa: {d.get('titulo')} | Cal ID: {d.get('google_calendar_id')} | Horário: {d.get('horario_inicio')} | Data: {d.get('data_limite')} | Notas: {repr(d.get('notas'))}")
