
import firebase_admin
from firebase_admin import credentials, firestore
import os
import re
from datetime import datetime

# --- CONFIGURAÇÃO E SEGURANÇA ---
KEY_PATH = 'firebase_service_account_key.json'
PARADIGM_VERSION = "2.0"

def get_db():
    if not firebase_admin._apps:
        # Tenta encontrar a chave na raiz
        if not os.path.exists(KEY_PATH):
            raise FileNotFoundError(f"Chave {KEY_PATH} não encontrada na raiz do projeto.")
        cred = credentials.Certificate(KEY_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# --- LÓGICA DE TRANSFORMAÇÃO ---

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
    if any(term in corpus for term in ['bug', 'api', 'código', 'repo', 'deploy', 'ts', 'js', 'py', 'hermes', 'mago']):
        return 'sistemas_e_codigo', 'desenvolvimento'
    elif any(term in corpus for term in ['processo', 'sei', 'licitação', 'financeiro', 'pgd', 'ata']):
        return 'operacoes_administrativas', 'administrativo'
    return 'captura_e_conhecimento', 'biblioteca'

def extract_semantics(filename, content):
    ext = os.path.splitext(filename)[1].lower()
    if ext in ['.ts', '.tsx', '.js', '.py']:
        matches = re.findall(r'(?:def|function|class|const)\s+([a-zA-Z_][a-zA-Z0-9_]*)', content)
        return sorted(list(set(matches)))[:15]
    return []

# --- EXECUÇÃO ---

def migrate():
    try:
        db = get_db()
    except Exception as e:
        print(f"❌ Erro ao conectar ao Firebase: {e}")
        return
    
    print("\n" + "="*50)
    print("⚠️  ALERTA: MIGRAÇÃO DEFINITIVA PARA PARADIGMA V2")
    print("="*50)
    print(f"Destino: Coleção 'conhecimento'")
    print(f"Ação: Adicionar memory_location, semantics e versionamento.")
    
    confirm = input("\nTem certeza que deseja aplicar estas mudanças no Firestore? (S/N): ")
    
    if confirm.upper() != 'S':
        print("\n❌ Operação cancelada pelo usuário.")
        return

    print("\n🚀 Iniciando migração...")
    
    docs = list(db.collection('conhecimento').stream())
    total_docs = len(docs)
    batch = db.batch()
    count = 0
    batch_count = 0

    for doc in docs:
        data = doc.to_dict()
        
        # Ignorar itens já atualizados para esta versão
        if data.get('paradigm_version') == PARADIGM_VERSION:
            continue

        titulo = data.get('titulo', 'Sem Título')
        texto = data.get('texto_bruto', '')
        
        # Executar Lógica de Paradigma
        domain, room = classify_document(titulo, texto)
        drawer = data.get('categoria', 'documentos').lower()
        new_location = build_memory_location(domain, room, drawer)
        semantics = extract_semantics(titulo, texto)
        
        # Preparar Update (Não removemos nada, apenas adicionamos)
        updates = {
            'memory_location': new_location,
            'domain_hint': domain,
            'semantics': semantics,
            'paradigm_version': PARADIGM_VERSION,
            'last_reprocessed': datetime.now().isoformat(),
            'version': data.get('version', 1)
        }
        
        batch.update(doc.reference, updates)
        count += 1
        batch_count += 1
        
        # Commit a cada 50 documentos (limite de segurança do Firestore)
        if batch_count >= 50:
            batch.commit()
            print(f"📦 Progresso: {count}/{total_docs} documentos processados...")
            batch = db.batch()
            batch_count = 0

    # Commit final dos remanescentes
    if batch_count > 0:
        batch.commit()
        print(f"📦 Progresso final: {count}/{total_docs} documentos processados.")

    if count == 0:
        print("\n✨ Todos os documentos já estão na versão mais recente do paradigma.")
    else:
        print(f"\n✨ SUCESSO: {count} documentos foram elevados ao Paradigma {PARADIGM_VERSION}.")

if __name__ == "__main__":
    migrate()
