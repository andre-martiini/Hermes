
import firebase_admin
from firebase_admin import credentials, firestore
import os

def fix_atlas():
    if not os.path.exists('firebase_service_account_key.json'):
        print("Error: firebase_service_account_key.json not found.")
        return

    if not firebase_admin._apps:
        cred = credentials.Certificate('firebase_service_account_key.json')
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    print("Searching for Atlas system...")
    
    # Busca por repo que contenha 'atlas'
    sistemas_ref = db.collection('sistemas_detalhes').stream()
    found = False
    for doc in sistemas_ref:
        data = doc.to_dict()
        repo = data.get('repositorio_principal', '').lower()
        nome = data.get('nome', '').lower()
        
        if 'atlas' in repo or 'atlas' in nome or 'atlas' in doc.id.lower():
            print(f"Found system: ID={doc.id}, Name={data.get('nome')}, Repo={data.get('repositorio_principal')}")
            doc.reference.update({'nome': 'Atlas'})
            print(f"Updated name to 'Atlas' for document {doc.id}")
            found = True
    
    if not found:
        print("Atlas system not found. Creating a new entry...")
        db.collection('sistemas_detalhes').add({
            'nome': 'Atlas',
            'repositorio_principal': 'https://github.com/andre-martiini/novo-sistema-atlas',
            'github_rag_synced_at': None
        })
        print("Created new system 'Atlas'")

if __name__ == "__main__":
    fix_atlas()
