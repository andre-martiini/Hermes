
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

def check_last_diagnosis():
    if not os.path.exists('firebase_service_account_key.json'):
        print("Error: firebase_service_account_key.json not found.")
        return

    if not firebase_admin._apps:
        cred = credentials.Certificate('firebase_service_account_key.json')
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    print("Fetching last diagnosis...")
    diags = db.collection('diagnosticos_codigo').order_by('criadoEm', direction=firestore.Query.DESCENDING).limit(1).get()
    
    if not diags:
        print("No diagnosis found.")
        return
        
    diag = diags[0].to_dict()
    print(f"ID: {diags[0].id}")
    print(f"System: {diag.get('sistemaId')}")
    print(f"Repo: {diag.get('nomeRepositorio')}")
    print(f"Files Analyzed: {diag.get('arquivosAnalisados')}")
    print(f"Diagnosis: {diag.get('diagnostico')}")
    print(f"Blocks: {len(diag.get('blocosSR', []))}")

if __name__ == "__main__":
    check_last_diagnosis()
