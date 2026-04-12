
import firebase_admin
from firebase_admin import credentials, firestore
import os
import re
import unicodedata

# --- LÓGICA DO PARADIGMA V2 (Baseada no functions/main.py) ---

def normalize_text(value):
    if not value: return ''
    normalized = unicodedata.normalize('NFD', str(value))
    normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
    return normalized.lower().strip()

def build_memory_location(domain_hint, room, drawer):
    wing = 'captura'
    if domain_hint == 'sistemas_e_codigo': wing = 'sistemas'
    elif domain_hint == 'operacoes_administrativas': wing = 'operacoes'
    
    path = f"{wing} / {room} / {drawer}".lower().replace(' ', '_')
    return {
        'wing': wing,
        'room': room.lower().replace(' ', '_'),
        'drawer': drawer.lower().replace(' ', '_'),
        'path_label': path
    }

def classify_document(filename, text):
    corpus = f"{filename}\n{text[:2000]}".lower()
    
    # Regras de Domínio Simplificadas para a Simulação
    if any(term in corpus for term in ['bug', 'erro', 'api', 'código', 'repo', 'deploy', 'ts', 'js', 'py', 'hermes', 'mago']):
        domain = 'sistemas_e_codigo'
        room = 'desenvolvimento'
    elif any(term in corpus for term in ['processo', 'sei', 'ofício', 'licitação', 'financeiro', 'pgd', 'ata']):
        domain = 'operacoes_administrativas'
        room = 'administrativo'
    else:
        domain = 'captura_e_conhecimento'
        room = 'biblioteca'
        
    return domain, room

def extract_semantics(filename, content):
    ext = os.path.splitext(filename)[1].lower()
    if ext in ['.ts', '.tsx', '.js', '.py']:
        # Regex simples para identificar funções e classes
        matches = re.findall(r'(?:def|function|class|const)\s+([a-zA-Z_][a-zA-Z0-9_]*)', content)
        return sorted(list(set(matches)))[:10]
    return []

# --- MOTOR DE SIMULAÇÃO ---

def run_simulation():
    # Caminho absoluto para a chave
    key_path = 'firebase_service_account_key.json'
    
    if not os.path.exists(key_path):
        print(f"❌ Erro: Arquivo {key_path} não encontrado na raiz.")
        return

    # Inicializa Firebase
    if not firebase_admin._apps:
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    # Pega uma amostra de 10 itens para simulação
    docs = db.collection('conhecimento').limit(10).stream()
    
    count = 0
    print("Simulation Results:")
    for doc in docs:
        count += 1
        data = doc.to_dict()
        titulo = data.get('titulo', 'Sem Título')
        texto = data.get('texto_bruto', '')
        
        domain, room = classify_document(titulo, texto)
        drawer = data.get('categoria', 'documentos').lower()
        new_location = build_memory_location(domain, room, drawer)
        
        print(f"Item {count}: {titulo}")
        print(f" - Wing: {new_location['wing']}")
        print(f" - Room: {new_location['room']}")
        print(f" - Path: {new_location['path_label']}")
        print("-" * 20)

    if count == 0:
        print("⚠️  Nenhum documento encontrado na coleção 'conhecimento'.")
    else:
        print(f"\n✅ Simulação concluída para {count} itens. Nenhum dado foi alterado no Firestore.")

if __name__ == "__main__":
    run_simulation()
