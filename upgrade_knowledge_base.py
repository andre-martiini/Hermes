import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(r"C:\Users\andre\Documents\Hermes")
PROCESS_DIR = BASE_DIR / "CONHECIMENTO_PROCESSADO"
DB_PATH = BASE_DIR / "00_HERMES_MASTER_INDEX.json"

def get_api_key():
    import firebase_admin
    from firebase_admin import credentials, firestore
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(str(BASE_DIR / "firebase_service_account_key.json"))
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        doc = db.collection('system').document('api_keys').get()
        if doc.exists:
            return doc.to_dict().get('gemini_api_key')
    except: pass
    load_dotenv(BASE_DIR / "services" / "whatsapp-capture" / ".env")
    return os.getenv("GEMINI_API_KEY")

API_KEY = get_api_key()

PROMPT = """Você é um classificador de ontologias de nível avançado. 
Analise o Título e Resumo deste Nó de Conhecimento e defina as Categorias, Tags e Entidades de forma coesa.
Siga rigidamente as seguintes definições:
- category: Apenas a área macro (ex: CLC, ASSISTÊNCIA, TI, RH, GERAL, ESTUDOS).
- tags: Conceitos, assutos e tópicos abstratos tratados (ex: Processo, PIX, Nota Técnica, Bug, Edital).
- entities: Pessoas, Sistemas, Órgãos, Departamentos ou Locais físicos reais (ex: IFES, AUDIN, CGPAE, Notion, Ezequiel).

Retorne APENAS um JSON estrito:
{{
  "category": "MACRO AREA",
  "tags": ["tag1", "tag2"],
  "entities": ["Entidade A", "Entidade B"]
}}

Nó de Conhecimento:
Título: {title}
Resumo: {summary}
Detalhes: {details}
Links Atuais: {links}
"""

def enrich_node(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Se já foi enriquecido, pular
    tech = data.get("technical", {})
    if "category" in tech and "entities" in tech:
        return False

    title = data.get("display", {}).get("title", "")
    summary = data.get("content", {}).get("summary", "")
    details = data.get("content", {}).get("details", "")
    links = data.get("graph", {}).get("explicit_links", [])

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={API_KEY.strip()}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": PROMPT.format(title=title, summary=summary, details=details, links=links)}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    try:
        r = requests.post(url, json=payload, headers=headers)
        r.raise_for_status()
        res_json = r.json()
        import re
        text_resp = res_json['candidates'][0]['content']['parts'][0]['text']
        match = re.search(r'\{.*\}', text_resp, re.DOTALL)
        if match:
            text_resp = match.group(0)
        ai_data = json.loads(text_resp)

        # Atualizar
        tech["category"] = ai_data.get("category", "GERAL")
        tech["tags"] = ai_data.get("tags", [])
        tech["entities"] = ai_data.get("entities", [])
        data["technical"] = tech
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Enriquecido: {title[:30]} -> Cat: {tech['category']}")
        return True
    except Exception as e:
        print(f"❌ Erro ao tentar enriquecer {title[:30]}: {e}")
        return False

if __name__ == "__main__":
    count = 0
    files = list(PROCESS_DIR.glob("*.json"))
    print(f"🔄 Verificando {len(files)} arquivos em busca de nós legados...")
    
    for f in files:
        if enrich_node(f):
            count += 1
            time.sleep(0.5) # Anti-Spam
            
    if count > 0:
        print(f"\n🎉 {count} nós atualizados para o padrão de Alta Inteligência.")
        print("Recomenda-se rodar o hermes_cli.py para reconstituir o Índice Mestre!")
    else:
        print("\n✨ Todos os nós já estão no padrão atual.")
