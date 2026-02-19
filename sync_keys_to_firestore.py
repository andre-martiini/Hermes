import firebase_admin
from firebase_admin import credentials, firestore
import os
from dotenv import load_dotenv

# Carrega a chave do .env do Bot
load_dotenv(dotenv_path='Hermes-Bot/.env')
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Erro: GEMINI_API_KEY não encontrada no .env do Bot.")
    exit(1)

# Inicializa Firebase
cred_path = "firebase_service_account_key.json"
if os.path.exists(cred_path):
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    print(f"Atualizando Firestore com a chave: {GEMINI_API_KEY[:4]}...{GEMINI_API_KEY[-4:]}")
    
    doc_ref = db.collection('system').document('api_keys')
    doc_ref.set({'gemini_api_key': GEMINI_API_KEY}, merge=True)
    
    print("Sucesso! Firestore atualizado.")
else:
    print(f"Erro: Arquivo {cred_path} não encontrado.")
