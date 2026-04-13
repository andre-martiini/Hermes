import os
import json
import time
import shutil
import re
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# Configurações
BASE_DIR = Path(r"C:\Users\andre\Documents\Hermes")
INPUT_DIR = BASE_DIR / "ENTRADA_HERMES"
ARCHIVE_DIR = BASE_DIR / "ORIGINAIS_HERMES"
PROCESSED_DIR = BASE_DIR / "CONHECIMENTO_PROCESSADO"
DB_PATH = BASE_DIR / "hermes_relational_knowledge.json"
CRED_PATH = BASE_DIR / "firebase_service_account_key.json"

def get_api_key():
    # Tenta Firestore primeiro (padrão Hermes 2026)
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(str(CRED_PATH))
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        doc = db.collection('system').document('api_keys').get()
        if doc.exists:
            return doc.to_dict().get('gemini_api_key')
    except: pass
    
    # Fallback para .env
    load_dotenv(BASE_DIR / "services" / "whatsapp-capture" / ".env")
    return os.getenv("GEMINI_API_KEY")

api_key = get_api_key()

PROMPT_SISTEMA = """
Você é o Hermes Gatekeeper. Sua função é caracterizar documentos para um banco de dados relacional avançado e classificá-los com alta precisão.
Analise o texto e extraia os metadados com base na taxonomia do sistema (ex: CLC, ASSISTÊNCIA, TI, GERAL).
Responda APENAS em JSON com esta estrutura:
{
  "title": "título curto e claro",
  "category": "categoria principal",
  "tags": ["tag1", "tag2"],
  "entities": ["Entidade A", "Projeto B"],
  "tldr": "resumo de 1 frase",
  "summary": "resumo executivo detalhado",
  "details": "detalhes técnicos e datas",
  "type": "paper|report|legal_doc|note",
  "confidence": 0.95,
  "links": ["relacionamento_1"]
}
"""

def call_gemini_31(text):
    if not api_key: raise ValueError("Chave API não encontrada.")
    # Usando o modelo solicitado pelo usuário: gemini-3.1-flash-lite-preview
    model_name = "gemini-3.1-flash-lite-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": f"{PROMPT_SISTEMA}\n\nDocumento:\n{text}"}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    result = r.json()
    return result['candidates'][0]['content']['parts'][0]['text']

def process_file(file_path):
    print(f"🧠 [Gemini 3.1] Caracterizando: {file_path.name}")
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_text = f.read(30000)

        response_text = call_gemini_31(raw_text)
        data = json.loads(response_text)
        
        item_id = f"item_{int(time.time())}_{file_path.stem[:10]}"
        archive_name = f"{item_id}_{file_path.name}"
        
        new_item = {
            "id": item_id,
            "display": {"title": data.get("title", file_path.stem), "tldr": data.get("tldr", "")},
            "technical": {
                "model": "gemini-3.1-flash-lite",
                "type": data.get("type", "note"),
                "category": data.get("category", "GERAL"),
                "tags": data.get("tags", []),
                "entities": data.get("entities", []),
                "confidence_weight": data.get("confidence", 0.9),
                "created_at": datetime.now().isoformat(),
                "original_file": archive_name
            },
            "content": {"summary": data.get("summary", ""), "details": data.get("details", "")},
            "graph": {"explicit_links": data.get("links", [])}
        }
        
        # Salvamento triplo (Local, Drive-Sync e Firestore)
        PROCESSED_DIR.mkdir(exist_ok=True)
        with open(PROCESSED_DIR / f"{item_id}.json", "w", encoding="utf-8") as f:
            json.dump(new_item, f, indent=2, ensure_ascii=False)

        try:
            db = firestore.client()
            db.collection('conhecimento_relacional').document(item_id).set(new_item)
        except: pass

        shutil.move(file_path, ARCHIVE_DIR / archive_name)
        print(f"✅ Item processado: {new_item['display']['title']}")
        
    except Exception as e:
        print(f"❌ Erro em {file_path.name}: {e}")

if __name__ == "__main__":
    for f in INPUT_DIR.glob("*"):
        if f.is_file(): process_file(f)
