import os
import requests
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(r"C:\Users\andre\Documents\Hermes")
load_dotenv(BASE_DIR / "services" / "whatsapp-capture" / ".env")
api_key = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY")

if not api_key:
    # Tenta Firestore
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = credentials.Certificate(str(BASE_DIR / "firebase_service_account_key.json"))
    if not firebase_admin._apps: firebase_admin.initialize_app(cred)
    db = firestore.client()
    doc = db.collection('system').document('api_keys').get()
    api_key = doc.to_dict().get('gemini_api_key')

print(f"Testando chave: {api_key[:10]}...")

# Tentar v1beta e v1 com diferentes modelos
models_to_try = [
    "v1beta/models/gemini-1.5-flash:generateContent",
    "v1/models/gemini-1.5-flash:generateContent",
    "v1beta/models/gemini-pro:generateContent"
]

for endpoint in models_to_try:
    url = f"https://generativelanguage.googleapis.com/{endpoint}?key={api_key.strip()}"
    payload = {"contents": [{"parts": [{"text": "Oi"}]}]}
    print(f"Tentando: {endpoint}...")
    try:
        r = requests.post(url, json=payload)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print(f"✅ SUCESSO com {endpoint}")
            break
        else:
            print(f"Erro: {r.text[:200]}")
    except Exception as e:
        print(f"Falha: {e}")
