from google.cloud import firestore
import json

def list_tasks():
    db = firestore.Client(project='gestao-hermes')
    docs = db.collection('tarefas').stream()
    found = []
    for doc in docs:
        d = doc.to_dict()
        text = str(d.get('titulo', '')) + " " + str(d.get('descricao', ''))
        if any(w in text.lower() for w in ['mobiliário', 'mobiliario', 'eventos', 'som']):
            found.append({'id': doc.id, 'titulo': d.get('titulo'), 'status': d.get('status'), 'data_limite': d.get('data_limite')})
    
    print(json.dumps(found, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    list_tasks()
