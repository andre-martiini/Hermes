
import argparse
import json
import re
import os
import sys
import base64
from datetime import datetime, timezone, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import time

# Imports para Google APIs
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError

# Escopos para Google APIs (Tasks e Gmail Readonly)
SCOPES = [
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive'
]

DEBUG_MODE = True # Ativa log detalhado de cada tarefa no terminal do sistema

# Configuração do Firebase
KEY_FILE = 'firebase_service_account_key.json'

def sync_hermes_knowledge(db=None):
    """Sincroniza do Drive e processa a entrada local."""
    import subprocess
    input_dir = r"C:\Users\andre\Documents\Hermes\ENTRADA_HERMES"
    
    # 1. Tenta buscar novidades do Google Drive primeiro
    try:
        if db:
            sync_google_drive_knowledge(db)
            # NOVO: Sobe arquivos que foram colocados localmente para o Drive
            push_raw_files_to_drive()
    except Exception as e:
        print(f"Aviso: Falha ao sincronizar brutos com Drive: {e}")

    # 2. Processa o que estiver na pasta de entrada
    if os.path.exists(input_dir) and any(os.scandir(input_dir)):
        print("\n[🧠 HERMES] Verificando entrada de novos conhecimentos...")
        try:
            script_path = r"C:\Users\andre\Documents\Hermes\hermes_gatekeeper.py"
            venv_python = r"C:\Users\andre\Documents\Hermes\functions\venv\Scripts\python.exe"
            if not os.path.exists(venv_python): venv_python = "python"
            
            subprocess.run([venv_python, script_path], check=True)
            print("[🧠 HERMES] Base de conhecimento sincronizada localmente.\n")
            
            # 3. Após processar local, sobe os JSONs para o Drive
            if db:
                push_knowledge_to_drive(db)
                generate_master_index(db)
                # NOVO: Exporta para o formato Obsidian (.md)
                export_to_obsidian()
        except Exception as e:
            print(f"Aviso: Não foi possível atualizar o conhecimento: {e}\n")

def push_knowledge_to_drive(db):
    """Sobe os arquivos JSON de CONHECIMENTO_PROCESSADO para o subdiretório no Drive."""
    import io
    from googleapiclient.http import MediaFileUpload
    
    print("[☁️ DRIVE] Sincronizando conhecimento tratado...")
    service = get_drive_service()
    processed_dir = r"C:\Users\andre\Documents\Hermes\CONHECIMENTO_PROCESSADO"
    if not os.path.exists(processed_dir): return

    # 1. Garantir a existência da pasta raiz 'KnowledgeHermes'
    results = service.files().list(
        q="name = 'KnowledgeHermes' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id)"
    ).execute()
    roots = results.get('files', [])
    if not roots:
        root = service.files().create(body={'name': 'KnowledgeHermes', 'mimeType': 'application/vnd.google-apps.folder'}, fields='id').execute()
        root_id = root.get('id')
    else:
        root_id = roots[0]['id']

    # 2. Garantir a subpasta 'Hermes Relational Knowledge'
    results = service.files().list(
        q=f"name = 'Hermes Relational Knowledge' and '{root_id}' in parents and trashed = false",
        fields="files(id)"
    ).execute()
    folders = results.get('files', [])
    if not folders:
        folder = service.files().create(body={'name': 'Hermes Relational Knowledge', 'parents': [root_id], 'mimeType': 'application/vnd.google-apps.folder'}, fields='id').execute()
        folder_id = folder.get('id')
    else:
        folder_id = folders[0]['id']

    # 3. Sincronizar arquivos
    results = service.files().list(q=f"'{folder_id}' in parents and trashed = false", fields="files(name)").execute()
    existing_drive_files = {f['name'] for f in results.get('files', [])}
    
    count = 0
    for filename in os.listdir(processed_dir):
        if filename.endswith(".json") and filename not in existing_drive_files:
            file_metadata = {'name': filename, 'parents': [folder_id]}
            media = MediaFileUpload(os.path.join(processed_dir, filename), mimetype='application/json')
            service.files().create(body=file_metadata, media_body=media).execute()
            count += 1
    
    if count > 0: print(f"[☁️ DRIVE] {count} item(ns) tratados enviados para KnowledgeHermes/Hermes Relational Knowledge.")

def sync_google_drive_knowledge(db):
    """Busca brutos da subpasta 'RawData' dentro de 'KnowledgeHermes'."""
    import io
    from googleapiclient.http import MediaIoBaseDownload
    
    print("[☁️ DRIVE] Verificando novos dados em KnowledgeHermes/RawData...")
    service = get_drive_service()
    input_dir = r"C:\Users\andre\Documents\Hermes\ENTRADA_HERMES"
    
    # 1. Encontrar a pasta raiz 'KnowledgeHermes'
    results = service.files().list(
        q="name = 'KnowledgeHermes' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id)"
    ).execute()
    roots = results.get('files', [])
    if not roots:
        # Se não existe a raiz, cria ela e a pasta de entrada
        root = service.files().create(body={'name': 'KnowledgeHermes', 'mimeType': 'application/vnd.google-apps.folder'}, fields='id').execute()
        root_id = root.get('id')
        service.files().create(body={'name': 'RawData', 'parents': [root_id], 'mimeType': 'application/vnd.google-apps.folder'}).execute()
        print("[☁️ DRIVE] Estrutura 'KnowledgeHermes/RawData' criada. Adicione arquivos lá.")
        return
    
    root_id = roots[0]['id']

    # 2. Encontrar a subpasta 'RawData'
    results = service.files().list(
        q=f"name = 'RawData' and '{root_id}' in parents and trashed = false",
        fields="files(id)"
    ).execute()
    folders = results.get('files', [])
    if not folders:
        service.files().create(body={'name': 'RawData', 'parents': [root_id], 'mimeType': 'application/vnd.google-apps.folder'}).execute()
        print("[☁️ DRIVE] Subpasta 'RawData' criada dentro de 'KnowledgeHermes'.")
        return
    
    folder_id = folders[0]['id']
    
    # 3. Listar e baixar arquivos
    results = service.files().list(q=f"'{folder_id}' in parents and trashed = false", fields="files(id, name, mimeType)").execute()
    files = results.get('files', [])
    
    processed_ref = db.collection('system').document('processed_drive_files')
    processed_ids = (processed_ref.get().to_dict() or {}).get('ids', [])
    new_ids = []

    for f in files:
        if f['id'] in processed_ids or 'folder' in f['mimeType']: continue
        print(f"[☁️ DRIVE] Puxando bruto: {f['name']}...")
        request = service.files().get_media(fileId=f['id'])
        fh = io.FileIO(os.path.join(input_dir, f['name']), 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        new_ids.append(f['id'])

    if new_ids:
        updated_ids = list(set(processed_ids + new_ids))[-500:]
        processed_ref.set({'ids': updated_ids}, merge=True)
        print(f"[☁️ DRIVE] {len(new_ids)} novo(s) arquivo(s) prontos para processamento.")

def push_raw_files_to_drive():
    """Sincroniza arquivos brutos colocados localmente para a pasta RawData no Drive."""
    import os
    from googleapiclient.http import MediaFileUpload
    
    print("[☁️ DRIVE] Espelhando arquivos locais para RawData...")
    service = get_drive_service()
    input_dir = r"C:\Users\andre\Documents\Hermes\ENTRADA_HERMES"
    
    # 1. Localizar KnowledgeHermes/RawData
    results = service.files().list(q="name = 'KnowledgeHermes' and trashed = false").execute()
    if not results.get('files'): return
    root_id = results['files'][0]['id']
    
    results = service.files().list(q=f"name = 'RawData' and '{root_id}' in parents and trashed = false").execute()
    if not results.get('files'): return
    folder_id = results['files'][0]['id']

    # 2. Listar arquivos no Drive
    results = service.files().list(q=f"'{folder_id}' in parents and trashed = false").execute()
    existing_drive_files = {f['name'] for f in results.get('files', [])}

    # 3. Subir o que falte
    for filename in os.listdir(input_dir):
        if filename not in existing_drive_files and os.path.isfile(os.path.join(input_dir, filename)):
            print(f"[☁️ DRIVE] Sincronizando bruto para nuvem: {filename}...")
            file_metadata = {'name': filename, 'parents': [folder_id]}
            media = MediaFileUpload(os.path.join(input_dir, filename))
            service.files().create(body=file_metadata, media_body=media).execute()

def generate_master_index(db):
    """Consolida todos os JSONs de conhecimento em um único arquivo de Índice Mestre."""
    import os
    import json
    from googleapiclient.http import MediaFileUpload
    
    print("[🧠] Gerando Índice Mestre do Conhecimento...")
    processed_dir = r"C:\Users\andre\Documents\Hermes\CONHECIMENTO_PROCESSADO"
    index_path = r"C:\Users\andre\Documents\Hermes\00_HERMES_MASTER_INDEX.json"
    
    if not os.path.exists(processed_dir): return
    
    master_index = {
        "generated_at": datetime.now().isoformat(),
        "total_items": 0,
        "items": []
    }
    
    for filename in os.listdir(processed_dir):
        if filename.endswith(".json") and filename != "00_HERMES_MASTER_INDEX.json":
            try:
                with open(os.path.join(processed_dir, filename), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    category = data.get("technical", {}).get("category", "GERAL")
                    tags = data.get("technical", {}).get("tags", [])
                    entities = data.get("technical", {}).get("entities", [])
                    explicit_links = data.get("graph", {}).get("explicit_links", [])
                    
                    master_index["items"].append({
                        "id": data.get("id"),
                        "title": data.get("display", {}).get("title"),
                        "type": data.get("technical", {}).get("type"),
                        "category": category,
                        "tags": tags,
                        "entities": entities,
                        "tldr": data.get("display", {}).get("tldr"),
                        "created_at": data.get("technical", {}).get("created_at")
                    })
                    master_index["total_items"] += 1
            except: continue
            
    # Processamento de Grafo (Inspirado no Graphify-4)
    print("[🧠] Analisando Conexões e Estruturas de Grafo (God Nodes)...")
    try:
        import networkx as nx
        G = nx.Graph()
        for item in master_index["items"]:
            # O arquivo em si é o centro ("hub")
            doc_id = item["id"]
            G.add_node(doc_id, type="document")
            
            # Anexar as tags e entidades (Conceitos/God Nodes potenciais)
            concepts = item.get("entities", []) + item.get("tags", [])
            for concept in concepts:
                if not concept or len(concept) < 2: continue
                c_id = f"c_{concept.strip().upper()}"
                G.add_node(c_id, type="concept", label=concept.strip())
                G.add_edge(doc_id, c_id)
                
        # Calcula nós mais influentes (degree de networkx)
        degrees = dict(G.degree())
        concept_degrees = [(n, d) for n, d in degrees.items() if n.startswith("c_")]
        top_concepts = sorted(concept_degrees, key=lambda x: x[1], reverse=True)[:15]
        
        # Injeta métricas relacional-globais no RAG
        master_index["graph_insights"] = {
            "god_nodes": [{"label": G.nodes[n].get("label"), "degree": d} for n, d in top_concepts],
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges()
        }
    except Exception as e:
        print(f"⚠️ Aviso: Falha na análise estrutural de grafo: {e}")
            
    # Salvar localmente
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(master_index, f, indent=2, ensure_ascii=False)
        
    # Subir para o Drive (Na raiz da KnowledgeHermes)
    try:
        service = get_drive_service()
        results = service.files().list(q="name = 'KnowledgeHermes' and trashed = false").execute()
        if not results.get('files'): return
        root_id = results['files'][0]['id']
        
        print("[☁️ DRIVE] Atualizando Índice Mestre na nuvem...")
        # Deletar anterior se existir
        existing = service.files().list(q=f"name = '00_HERMES_MASTER_INDEX.json' and '{root_id}' in parents and trashed = false").execute()
        for f in existing.get('files', []):
            service.files().delete(fileId=f['id']).execute()
            
        file_metadata = {'name': '00_HERMES_MASTER_INDEX.json', 'parents': [root_id]}
        media = MediaFileUpload(index_path, mimetype='application/json')
        service.files().create(body=file_metadata, media_body=media).execute()
        print(f"[🧠] Índice Mestre com {master_index['total_items']} itens sincronizado.")
    except Exception as e:
        print(f"Aviso: Erro ao subir índice mestre: {e}")

def export_to_obsidian():
    """Converte os JSONs relacionais em arquivos Markdown amigáveis ao Obsidian usando MarkItDown."""
    import os
    import json
    from googleapiclient.http import MediaFileUpload
    
    print("[💎] Gerando visualização Obsidian (Markdown Alta Fidelidade)...")
    base_dir = r"C:\Users\andre\Documents\Hermes"
    processed_dir = os.path.join(base_dir, "CONHECIMENTO_PROCESSADO")
    obsidian_dir = os.path.join(base_dir, "OBSIDIAN_VIEW")
    originals_dir = os.path.join(base_dir, "ORIGINAIS_HERMES")
    os.makedirs(obsidian_dir, exist_ok=True)
    
    # Inicializa MarkItDown
    try:
        from markitdown import MarkItDown
        md_engine = MarkItDown()
    except Exception as e:
        print(f"Aviso: MarkItDown falhou ao carregar: {e}")
        md_engine = None

    if not os.path.exists(processed_dir): return
    
    count = 0
    for filename in os.listdir(processed_dir):
        if filename.endswith(".json") and filename != "00_HERMES_MASTER_INDEX.json":
            try:
                with open(os.path.join(processed_dir, filename), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                title = data.get("display", {}).get("title", "Sem Título")
                md_filename = f"{filename.replace('.json', '')}.md"
                md_path = os.path.join(obsidian_dir, md_filename)
                
                # 1. Construir Frontmatter e Resumo (IA)
                content = f"---\n"
                content += f"id: {data.get('id')}\n"
                content += f"type: {data.get('technical', {}).get('type')}\n"
                content += f"created_at: {data.get('technical', {}).get('created_at')}\n"
                content += f"confidence: {data.get('technical', {}).get('confidence_weight', '')}\n"
                content += f"---\n\n"
                content += f"# {title}\n\n"
                content += f"## 📝 TLDR\n{data.get('display', {}).get('tldr', '')}\n\n"
                content += f"## 🤖 Resumo da IA\n{data.get('content', {}).get('summary', '')}\n\n"
                
                # 3. Diário de Bordo (Se existir)
                journal = data.get("content", {}).get("journal")
                if journal and journal != "Nenhum registro no diário de bordo.":
                    content += f"## 📅 Diário de Bordo\n"
                    content += f"```text\n{journal}\n```\n\n"

                # 4. Inserir Conteúdo Íntegro (MarkItDown)
                original_file = data.get("technical", {}).get("original_file")
                if md_engine and original_file:
                    original_path = os.path.join(originals_dir, original_file)
                    if os.path.exists(original_path):
                        print(f"   ∟ Convertendo corpo técnico: {original_file}")
                        try:
                            conversion = md_engine.convert(original_path)
                            content += f"## 📄 Conteúdo Original Extratado\n\n"
                            content += conversion.text_content
                            content += "\n\n"
                        except Exception as ce:
                            content += f"\n> [!WARNING] Falha na conversão MarkItDown: {ce}\n\n"

                # 3. Relações do Grafo
                links = data.get("graph", {}).get("explicit_links", [])
                if links:
                    content += f"## 🔗 Relações\n"
                    for link in links:
                        content += f"- [[{link}]]\n"
                
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(content)
                count += 1
            except: continue

    # Sincronizar pasta Obsidian com o Drive
    try:
        service = get_drive_service()
        results = service.files().list(q="name = 'KnowledgeHermes' and trashed = false").execute()
        if not results.get('files'): return
        root_id = results['files'][0]['id']
        
        # Encontrar ou criar subpasta OBSIDIAN_GRAPH
        res = service.files().list(q=f"name = 'OBSIDIAN_GRAPH' and '{root_id}' in parents and trashed = false").execute()
        if not res.get('files'):
            folder = service.files().create(body={'name': 'OBSIDIAN_GRAPH', 'parents': [root_id], 'mimeType': 'application/vnd.google-apps.folder'}, fields='id').execute()
            folder_id = folder.get('id')
        else:
            folder_id = res['files'][0]['id']
            
        # Listar para saber o que atualizar ou criar
        existing = service.files().list(q=f"'{folder_id}' in parents and trashed = false", fields="files(id, name)").execute()
        drive_files = {f['name']: f['id'] for f in existing.get('files', [])}
        
        for f in os.listdir(obsidian_dir):
            if f.endswith(".md"):
                file_metadata = {'name': f}
                media = MediaFileUpload(os.path.join(obsidian_dir, f), mimetype='text/markdown')
                
                if f in drive_files:
                    # Atualizar
                    service.files().update(fileId=drive_files[f], media_body=media).execute()
                else:
                    # Criar novo
                    file_metadata['parents'] = [folder_id]
                    service.files().create(body=file_metadata, media_body=media).execute()
        
        print(f"[☁️ DRIVE] {count} arquivos de Alta Fidelidade atualizados no seu Grafo Obsidian.")
        
    except Exception as e:
        print(f"Aviso: Erro ao sincronizar Obsidian: {e}")

def get_units_mapping(db):
    mapping = {
        'CLC': ['licitação', 'pregão', 'irp', 'processo'],
        'ASSISTÊNCIA': ['bolsa', 'auxílio', 'assistência'],
        'DEV': ['bug', 'deploy', 'código']
    }
    try:
        docs = db.collection('unidades').get()
        for doc in docs:
            data = doc.to_dict()
            nome = data.get('nome', '').upper()
            palavras = data.get('palavras_chave', [])
            if nome and palavras:
                if nome in mapping:
                    mapping[nome].extend(palavras)
                else:
                    mapping[nome] = palavras
        for area in mapping:
            mapping[area] = list(set(str(p).strip().upper() for p in mapping[area]))
    except Exception as e:
        print(f"Aviso: Não foi possível carregar unidades dinâmicas: {e}")
    return mapping

def init_db():
    if not os.path.exists(KEY_FILE):
        print(f"ERRO: Arquivo de chave {KEY_FILE} não encontrado.")
        sys.exit(1)
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()

def get_google_creds():
    """
    Autenticação via credentials.json e token.json local.
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                print("Token expirado ou revogado. Iniciando nova autenticação...")
                if os.path.exists('token.json'):
                    os.remove('token.json')
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists('credentials.json'):
                print("ERRO: 'credentials.json' não encontrado. Baixe do Google Cloud Console.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            
            print("\n----- ATENÇÃO -----")
            print("Seu navegador deve abrir agora. Se você vir a tela 'ERR_CONNECTION_REFUSED', significa que o Google bloqueou portas dinâmicas.")
            print("Tentando forçar a captura via localhost:8080...")
            print("-------------------\n")
            
            try:
                # Tenta forçar a porta padrão
                creds = flow.run_local_server(port=8080)
            except Exception as e:
                print(f"Erro ao ligar o servidor local ({e}). Usando modo console. Copie a URL abaixo:")
                creds = flow.run_console()

        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def get_tasks_service():
    return build('tasks', 'v1', credentials=get_google_creds())

def get_gmail_service():
    return build('gmail', 'v1', credentials=get_google_creds())

def get_calendar_service():
    return build('calendar', 'v3', credentials=get_google_creds())

def get_drive_service():
    return build('drive', 'v3', credentials=get_google_creds())

def cleanup_old_sync_badges(db, log_func=None):
    def log(msg):
        if log_func: log_func(msg)
        else: print(msg)
    try:
        from datetime import timedelta
        from google.cloud.firestore_v1.base_query import FieldFilter
        limite = (datetime.now() - timedelta(hours=24)).isoformat()
        
        # Usando FieldFilter para evitar avisos de argumentos posicionais
        query = db.collection('tarefas').where(filter=FieldFilter('last_sync_date', '<', limite)).where(filter=FieldFilter('sync_status', 'in', ['new', 'updated']))
        tarefas_antigas = query.stream()
        
        count = 0
        for tarefa in tarefas_antigas:
            db.collection('tarefas').document(tarefa.id).update({'sync_status': 'synced'})
            count += 1
        if count > 0: log(f"🧹 Limpeza: {count} badge(s) antigo(s) removido(s).")
    except Exception as e:
        log(f"Aviso: Erro na limpeza de badges: {e}")

def extract_time_from_notes(notes):
    if not notes: return None, None
    match = re.search(r'\[Horário:\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\]', notes)
    if match:
        return match.group(1), match.group(2)
    return None, None

def update_notes_with_time(notes, start, end):
    if not notes: notes = ""
    pattern = r'\[Horário:\s*\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\]'
    new_block = f"[Horário: {start} - {end}]" if start and end else ""
    
    if re.search(pattern, notes):
        if new_block:
            return re.sub(pattern, new_block, notes)
        else:
            return re.sub(pattern, '', notes).strip()
    else:
        if new_block:
            return f"{notes}\n\n{new_block}".strip()
        else:
            return notes

def normalize_task_title(title):
    if not isinstance(title, str):
        return title

    compact = re.sub(r'\s+', ' ', title).strip()
    if not compact:
        return compact

    small_words = {
        'de', 'da', 'do', 'das', 'dos',
        'e', 'em', 'na', 'no', 'nas', 'nos',
        'a', 'o', 'as', 'os',
        'para', 'por', 'com'
    }

    def normalize_piece(piece, is_first):
        if not piece:
            return piece
        if re.fullmatch(r'[A-Z0-9]{2,5}', piece):
            return piece
        lower = piece.lower()
        if (not is_first) and lower in small_words:
            return lower
        return lower[:1].upper() + lower[1:]

    words = []
    for word_index, word in enumerate(compact.split(' ')):
        parts = re.split(r'([/-])', word)
        normalized_parts = []
        part_index = 0
        for part in parts:
            if part in ('/', '-'):
                normalized_parts.append(part)
                continue
            normalized_parts.append(normalize_piece(part, word_index == 0 and part_index == 0))
            part_index += 1
        words.append(''.join(normalized_parts))

    return ' '.join(words)

def sync_google_tasks(db, log_list=None, sync_ref=None):
    last_ui_update = [0]
    def log(msg, force_ui=False):
        print(msg)
        if log_list is not None: 
            log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            now_ts = time.time()
            if sync_ref and (force_ui or now_ts - last_ui_update[0] > 1.2):
                try: sync_ref.update({'logs': log_list}); last_ui_update[0] = now_ts
                except: pass

    try:
        service = get_tasks_service()
        results = service.tasklists().list().execute()
        tasklists = results.get('items', [])
        tasklist_id = None
        target_name = 'tarefa-gerais'
        for item in tasklists:
            clean_title = item['title'].lower().replace(' ', '-').replace('s', '') if 'tarefa' in item['title'].lower() else item['title'].lower()
            if item['title'].lower() == target_name or clean_title == target_name.replace('s', ''):
                tasklist_id = item['id']
                log(f"Iniciando PULL de: {item['title']}")
                break
        if not tasklist_id:
            log("ERRO: Lista não encontrada.")
            return

        g_tasks = []
        next_page_token = None
        while True:
            g_results = service.tasks().list(tasklist=tasklist_id, showCompleted=True, showHidden=True, maxResults=100, pageToken=next_page_token).execute()
            items = g_results.get('items', [])
            g_tasks.extend(items)
            if len(g_tasks) >= 200 or not g_results.get('nextPageToken'): break
            next_page_token = g_results.get('nextPageToken')

        log(f"Total de {len(g_tasks)} tarefas identificadas no Google. Analisando...", force_ui=True)
        dynamic_mapping = get_units_mapping(db)
        local_docs = db.collection('tarefas').get()
        local_tasks = {}
        for t in local_docs:
            d = t.to_dict()
            gid = d.get('google_id')
            if gid: local_tasks[gid] = (t.id, d)
            else: local_tasks[f"title_{d.get('titulo')}"] = (t.id, d)

        for gt in g_tasks:
            g_id = gt['id']
            title_raw = gt.get('title', '(Sem Título)')
            title = normalize_task_title(title_raw)
            title_was_normalized = title != title_raw
            g_updated = gt.get('updated', '')
            due = gt.get('due', None)
            deadline = due.split('T')[0] if due else '-'
            h_status = 'concluído' if gt.get('status') == 'completed' else 'em andamento'
            
            # Extração de horários das notas
            g_notes = gt.get('notes', '')
            h_inicio, h_fim = extract_time_from_notes(g_notes)
            
            # Duração padrão de 1h se houver início mas não fim
            if h_inicio and not h_fim:
                try:
                    h, m = map(int, h_inicio.split(':'))
                    h_fim = f"{(h+1)%24:02d}:{m:02d}"
                except: pass

            categoria, sistema, contabilizar_meta = classify_task(title, g_notes, dynamic_mapping)
            existing_data = local_tasks.get(g_id) or local_tasks.get(f"title_{title}") or local_tasks.get(f"title_{title_raw}")
            
            if existing_data:
                doc_id, t_old = existing_data
                if not t_old.get('google_id'):
                    applied_updated = datetime.now().isoformat() if title_was_normalized else g_updated
                    db.collection('tarefas').document(doc_id).update({
                        'titulo': title,
                        'google_id': g_id, 
                        'data_atualizacao': applied_updated, 
                        'notas': g_notes,
                        'horario_inicio': h_inicio,
                        'horario_fim': h_fim
                    })
                    log(f"[*] VINCULADA: {title}")
                    continue
                
                h_updated = t_old.get('data_atualizacao', '')
                
                # O prazo final deve sempre refletir o do Google (Fonte da Verdade)
                deadline_changed = t_old.get('data_limite') != deadline
                
                # Se o prazo mudou, ignoramos o shortcut do timestamp para garantir a sincronia
                if h_updated and g_updated and h_updated >= g_updated and not deadline_changed: continue
                
                has_changed = (t_old.get('status') != h_status or 
                               t_old.get('titulo') != title or 
                               deadline_changed or 
                               t_old.get('horario_inicio') != h_inicio or
                               t_old.get('horario_fim') != h_fim)
                
                if has_changed:
                    applied_updated = datetime.now().isoformat() if title_was_normalized else g_updated
                    db.collection('tarefas').document(doc_id).update({
                        'titulo': title, 'data_limite': deadline, 'status': h_status,
                        'data_conclusao': gt.get('completed'), 'data_atualizacao': applied_updated,
                        'notas': g_notes, 'sync_status': 'updated', 
                        'last_sync_date': datetime.now().isoformat(),
                        'horario_inicio': h_inicio,
                        'horario_fim': h_fim
                    })
                    if deadline_changed:
                        log(f"[#] PRAZO SINCRONIZADO: {title} ({deadline})")
                    else:
                        log(f"[-] ATUALIZADA: {title}")
            else:
                applied_updated = datetime.now().isoformat() if title_was_normalized else g_updated
                db.collection('tarefas').add({
                    'titulo': title, 'projeto': 'GOOGLE', 'data_limite': deadline,
                    'google_id': g_id, 'status': h_status, 'data_criacao': datetime.now().isoformat(),
                    'data_conclusao': gt.get('completed'), 'data_atualizacao': applied_updated,
                    'categoria': categoria, 'contabilizar_meta': contabilizar_meta,
                    'notas': g_notes, 'sync_status': 'new', 'last_sync_date': datetime.now().isoformat(),
                    'horario_inicio': h_inicio, 'horario_fim': h_fim
                })
                log(f"[+] IMPORTADA: {title}")
        cleanup_old_sync_badges(db, log)
        log("PULL CONCLUÍDO.", force_ui=True)
    except Exception as e:
        log(f"ERRO PULL: {e}", force_ui=True)

def sync_google_calendar(db, log_list=None, sync_ref=None):
    last_ui_update = [0]
    def log(msg, force_ui=False):
        print(msg)
        if log_list is not None:
            log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            now_ts = time.time()
            if sync_ref and (force_ui or now_ts - last_ui_update[0] > 1.2):
                try: sync_ref.update({'logs': log_list}); last_ui_update[0] = now_ts
                except: pass
    try:
        service = get_calendar_service()
        log("Sincronizando Google Calendar...")

        time_min = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace('+00:00', 'Z')
        time_max = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace('+00:00', 'Z')

        events_result = service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        log(f"Encontrados {len(events)} eventos no Calendar. Sincronizando...")

        count = 0
        for event in events:
            event_id = event['id']
            summary = event.get('summary', '(Sem título)')
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))

            db.collection('google_calendar_events').document(event_id).set({
                'google_id': event_id,
                'titulo': summary,
                'data_inicio': start,
                'data_fim': end,
                'last_sync': datetime.now().isoformat()
            }, merge=True)
            count += 1

        # Cleanup: Remove eventos que não vieram na resposta (excluídos do Google)
        # Mas apenas dentro da janela de tempo consultada
        fetched_ids = {e['id'] for e in events}
        try:
            existing_docs = db.collection('google_calendar_events').stream()
            deleted_count = 0
            for doc in existing_docs:
                d = doc.to_dict()
                e_start = d.get('data_inicio')
                if not e_start: continue
                
                # Verifica se o evento está dentro da janela de sincronização
                if time_min <= e_start <= time_max:
                    if doc.id not in fetched_ids:
                        doc.reference.delete()
                        deleted_count += 1
                        
            if deleted_count > 0:
                log(f"[CAL] {deleted_count} eventos excluídos localmente.", force_ui=True)
        except Exception as cleanup_err:
            log(f"Erro na limpeza do calendário: {cleanup_err}")

        log(f"[CAL] {count} eventos sincronizados.", force_ui=True)
    except Exception as e:
        log(f"ERRO CALENDAR: {e}", force_ui=True)

def push_google_tasks(db, log_list=None, sync_ref=None):
    last_ui_update = [0]
    def log(msg, force_ui=False):
        print(msg)
        if log_list is not None: 
            log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            now_ts = time.time()
            if sync_ref and (force_ui or now_ts - last_ui_update[0] > 1.2):
                try: sync_ref.update({'logs': log_list}); last_ui_update[0] = now_ts
                except: pass
    try:
        service = get_tasks_service()
        results = service.tasklists().list().execute()
        tasklists = results.get('items', [])
        tasklist_id = None
        target_name = 'tarefa-gerais'
        for item in tasklists:
            clean_title = item['title'].lower().replace(' ', '-').replace('s', '') if 'tarefa' in item['title'].lower() else item['title'].lower()
            if item['title'].lower() == target_name or clean_title == target_name.replace('s', ''):
                tasklist_id = item['id']
                log(f"Iniciando PUSH para: {item['title']}")
                break
        if not tasklist_id:
            log("ERRO: Lista destino não encontrada.")
            return

        calendar_service = get_calendar_service()

        # Pega todas as tarefas do Google (com paginação) para o mapa
        g_tasks_map = {}
        next_page_token = None
        while True:
            g_results = service.tasks().list(tasklist=tasklist_id, showCompleted=True, showHidden=True, maxResults=100, pageToken=next_page_token).execute()
            for item in g_results.get('items', []):
                g_tasks_map[item['id']] = item
            next_page_token = g_results.get('nextPageToken')
            if not next_page_token or len(g_tasks_map) >= 500: break

        tasks = db.collection('tarefas').stream()
        count = 0
        for doc in tasks:
            t = doc.to_dict()
            g_id = t.get('google_id')
            h_status = t.get('status')
            raw_title = t.get('titulo') or '(Sem Título)'
            title = normalize_task_title(raw_title)
            local_updated = t.get('data_atualizacao', '')
            if title != raw_title:
                local_updated = datetime.now().isoformat()
                doc.reference.update({'titulo': title, 'data_atualizacao': local_updated})
            
            if h_status == 'excluído':
                if g_id:
                    try: 
                        service.tasks().delete(tasklist=tasklist_id, task=g_id).execute()
                        log(f"[X] REMOVIDA DO GOOGLE: {title}")
                    except HttpError as e:
                        if e.resp.status == 404:
                            log(f"[!] Task {g_id} já não existia no Google.")
                        else:
                            log(f"[!] Erro ao deletar no Google: {e}")
                doc.reference.delete()
                continue

            sync_to_calendar = bool(t.get('horario_inicio') and t.get('data_limite') and t.get('data_limite') != '-')

            due_date = f"{t['data_limite']}T00:00:00Z" if t.get('data_limite') and t.get('data_limite') != '-' else None

            g_status = 'completed' if t.get('status') == 'concluído' else 'needsAction'
            
            # Atualiza as notas com o horário para garantir a sincronia de volta
            h_inicio, h_fim = t.get('horario_inicio'), t.get('horario_fim')
            if h_inicio and not h_fim:
                try:
                    h, m = map(int, h_inicio.split(':'))
                    h_fim = f"{(h+1)%24:02d}:{m:02d}"
                except: pass
            
            updated_notes = update_notes_with_time(t.get('notas', ''), h_inicio, h_fim)

            if not g_id:
                body = {'title': title, 'notes': updated_notes, 'status': g_status, 'due': due_date}
                new_task = service.tasks().insert(tasklist=tasklist_id, body=body).execute()
                doc.reference.update({
                    'google_id': new_task['id'], 
                    'data_atualizacao': new_task.get('updated'), 
                    'notas': updated_notes, 
                    'horario_fim': h_fim if not t.get('horario_fim') else t.get('horario_fim')
                })
                log(f"[+] ENVIADA: {title}"); count += 1
                continue
            g_task = g_tasks_map.get(g_id)
            if g_task and local_updated > g_task.get('updated', ''):
                body = {'id': g_id, 'title': title, 'notes': updated_notes, 'status': g_status, 'due': due_date}
                try:
                    service.tasks().update(tasklist=tasklist_id, task=g_id, body=body).execute()
                    log(f"[^] ATUALIZADA NO GOOGLE: {title}"); count += 1
                    if updated_notes != t.get('notas', ''):
                        doc.reference.update({'notas': updated_notes})
                except HttpError as e:
                    if e.resp.status == 404:
                        log(f"[!] Task {g_id} não encontrada no Google - Limpando ID para re-envio.")
                        doc.reference.update({'google_id': None})
                    else:
                        raise e
            
            # --- PARTE 2: Sincronia Google Calendar (Se possuir horário) ---
            cal_id = t.get('google_calendar_id')
            if sync_to_calendar and g_status == 'needsAction':
                try:
                    start_dt = f"{t.get('data_limite')}T{h_inicio}:00-03:00"
                    end_dt = f"{t.get('data_limite')}T{h_fim}:00-03:00"
                    event_body = {
                        'summary': f"Tarefa: {title}",
                        'description': updated_notes,
                        'start': {'dateTime': start_dt, 'timeZone': 'America/Sao_Paulo'},
                        'end': {'dateTime': end_dt, 'timeZone': 'America/Sao_Paulo'}
                    }
                    if not cal_id:
                        new_event = calendar_service.events().insert(calendarId='primary', body=event_body).execute()
                        doc.reference.update({'google_calendar_id': new_event['id']})
                        log(f"[+] ALOCADA CALENDAR: {title}")
                    else:
                        try:
                            calendar_service.events().update(calendarId='primary', eventId=cal_id, body=event_body).execute()
                        except HttpError as cal_err:
                            if cal_err.resp.status == 404:
                                new_event = calendar_service.events().insert(calendarId='primary', body=event_body).execute()
                                doc.reference.update({'google_calendar_id': new_event['id']})
                except Exception as ce:
                    pass
            elif (not sync_to_calendar or g_status == 'completed') and cal_id:
                 try:
                     calendar_service.events().delete(calendarId='primary', eventId=cal_id).execute()
                 except HttpError as ce: pass
                 doc.reference.update({'google_calendar_id': None})

        log(f"PUSH FINALIZADO: {count} atualizações.", force_ui=True)
    except Exception as e:
        log(f"ERRO PUSH: {e}", force_ui=True)

def sync_pix_emails(db, log_list=None, sync_ref=None):
    """
    Busca emails de Pix e registra no Financeiro (Versão CLI)
    """
    def log(msg, force_ui=False):
        print(msg)
        if log_list is not None: 
            log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            if sync_ref:
                try: sync_ref.update({'logs': log_list})
                except: pass

    try:
        service = get_gmail_service()
        log("Buscando emails de Pix a partir de 01/02/2026...")
        # Query: Assuntos de Pix + Data limite
        query = 'after:2026/02/01 subject:(Pix recebido OR Pix realizado OR "Pix enviado" OR "transferência Pix" OR "Pix enviado")'
        
        results = service.users().messages().list(userId='me', q=query, maxResults=50).execute()
        messages = results.get('messages', [])
        
        if not messages:
            log("Nenhum Pix encontrado para os critérios de busca.")
            return
        
        log(f"Encontrados {len(messages)} e-mails potenciais de Pix. Analisando...")

        # Cache de transações existentes para evitar duplicatas
        existing_transactions = []
        existing_income = []
        existing_google_ids = set()

        for t in db.collection('finance_transactions').stream():
            data = t.to_dict()
            existing_transactions.append((data.get('description'), data.get('amount'), data.get('date')))
            if data.get('google_message_id'): existing_google_ids.add(data['google_message_id'])

        for t in db.collection('finance_income').stream():
            data = t.to_dict()
            existing_income.append((data.get('description'), data.get('amount'), data.get('date')))
            if data.get('google_message_id'): existing_google_ids.add(data['google_message_id'])

        processed_emails_doc = db.collection('system').document('processed_emails').get()
        processed_ids = processed_emails_doc.to_dict().get('ids', []) if processed_emails_doc.exists else []
        new_processed_ids = []

        for msg in messages:
            msg_id = msg['id']
            if msg_id in processed_ids or msg_id in existing_google_ids: continue
            
            details = service.users().messages().get(userId='me', id=msg_id).execute()
            internal_date_ms = int(details.get('internalDate', time.time() * 1000))
            dt = datetime.fromtimestamp(internal_date_ms / 1000.0, tz=timezone.utc)
            
            snippet = details.get('snippet', '')
            subject = ''
            for header in details.get('payload', {}).get('headers', []):
                if header['name'] == 'Subject': subject = header['value']; break
            
            value_match = re.search(r'R\$\s*(\d+(?:[\.,]\d+)?)', f"{subject} {snippet}")
            if value_match:
                val_str = value_match.group(1).replace('.', '').replace(',', '.')
                amount = float(val_str)
                is_income = any(word in subject.lower() or word in snippet.lower() for word in ['recebido', 'recebeu', 'recebida'])
                description = f"Pix: {subject}"
                iso_date = dt.isoformat()
                
                # Verificação de redundância adicional (mesmo que não esteja no processed_ids)
                record = (description, amount, iso_date)
                if is_income:
                    if record in existing_income:
                        new_processed_ids.append(msg_id)
                        continue
                    db.collection('finance_income').add({
                        'description': description, 'amount': amount, 'day': dt.day,
                        'month': dt.month - 1, 'year': dt.year,
                        'category': 'Renda Extra', 'isReceived': True, 'date': iso_date,
                        'google_message_id': msg_id, 'status': 'active'
                    })
                else:
                    if record in existing_transactions:
                        new_processed_ids.append(msg_id)
                        continue
                    sprint = 1 if dt.day < 8 else 2 if dt.day < 15 else 3 if dt.day < 22 else 4
                    db.collection('finance_transactions').add({
                        'description': description, 'amount': amount, 'date': iso_date,
                        'sprint': sprint, 'category': 'Alimentação',
                        'google_message_id': msg_id, 'status': 'active'
                    })
                new_processed_ids.append(msg_id)
                log(f"[PIX] Processado: {description} (R$ {amount:.2f}) - Data: {dt.strftime('%d/%m/%y')}")

        if new_processed_ids:
            updated_ids = list(set(processed_ids + new_processed_ids))[-200:]
            db.collection('system').document('processed_emails').set({'ids': updated_ids}, merge=True)
    except Exception as e:
        log(f"ERRO PIX: {e}")

def classify_task(title, notes, mapping=None):
    if mapping is None: mapping = {'CLC': [], 'ASSISTÊNCIA': []}
    title_upper, notes_upper = title.upper(), notes.upper()
    full_text = f"{title_upper} {notes_upper}"
    categoria, contabilizar_meta = 'NÃO CLASSIFICADA', False
    
    for area, keywords in mapping.items():
        if any(kw.upper() in title_upper for kw in keywords):
            categoria = area
            if area in ['CLC', 'ASSISTÊNCIA']: contabilizar_meta = True
            return categoria, None, contabilizar_meta

    tags = re.findall(r'\[(.*?)\]|TAG:\s*([\w\-]+)', full_text)
    tags = [t[0].upper() if t[0] else t[1].upper() for t in tags]
    if any(tag in ['CLC', 'LICITACAO'] for tag in tags): categoria, contabilizar_meta = 'CLC', True
    elif any(tag in ['ASSISTENCIA', 'ESTUDANTIL'] for tag in tags): categoria, contabilizar_meta = 'ASSISTÊNCIA', True
    elif 'GERAL' in tags: categoria = 'GERAL'
    return categoria, None, contabilizar_meta

def watch_commands(db):
    print("MÓDULO DE SINCRONIZAÇÃO AUTOMÁTICA INICIADO")
    sync_doc_ref = db.collection('system').document('sync')
    def on_snapshot(doc_snapshot, changes, read_time):
        for doc in doc_snapshot:
            data = doc.to_dict()
            if not data or data.get('status') != 'requested': continue
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] COMANDO RECEBIDO")
            log_entries = ["Iniciando processamento..."]
            sync_doc_ref.update({'status': 'processing', 'logs': log_entries})
            try:
                push_google_tasks(db, log_entries, sync_doc_ref)
                sync_google_tasks(db, log_entries, sync_doc_ref)
                sync_google_calendar(db, log_entries, sync_doc_ref)
                sync_pix_emails(db, log_entries, sync_doc_ref)
                sync_doc_ref.update({'status': 'completed', 'last_success': datetime.now().isoformat(), 'logs': log_entries})
                print("Sincronização concluída.")
            except Exception as e:
                print(f"ERRO: {e}"); log_entries.append(f"ERRO FATAL: {str(e)}")
                sync_doc_ref.update({'status': 'error', 'error_message': str(e), 'logs': log_entries})
    doc_watch = sync_doc_ref.on_snapshot(on_snapshot)
    while True: time.sleep(1)

def main():
    parser = argparse.ArgumentParser(description='Hermes CLI')
    subparsers = parser.add_subparsers(dest='command')
    subparsers.add_parser('sync-tasks')
    subparsers.add_parser('watch')
    subparsers.add_parser('sync-pix')
    subparsers.add_parser('sync-cal')
    args = parser.parse_args()
    if not args.command: parser.print_help(); return
    
    # Ingestão de conhecimento prioritária
    db = init_db()
    sync_hermes_knowledge(db)
    if args.command == 'sync-tasks': sync_google_tasks(db)
    elif args.command == 'watch': watch_commands(db)
    elif args.command == 'sync-pix': sync_pix_emails(db)
    elif args.command == 'sync-cal': sync_google_calendar(db)

if __name__ == '__main__': main()
