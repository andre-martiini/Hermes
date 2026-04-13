import os
import json
import time
import shutil
from pathlib import Path
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io

# Configurações de Caminho
BASE_DIR = Path(r"C:\Users\andre\Documents\Hermes")
INPUT_DIR = BASE_DIR / "ENTRADA_HERMES"
PROCESSED_DIR = BASE_DIR / "CONHECIMENTO_PROCESSADO"
CRED_PATH = BASE_DIR / "firebase_service_account_key.json"

# IDs de Pasta no Google Drive
FOLDER_LEGACY = "1YcA-M2i-H_P9A6UiUmkK8UmPRDWdj2hA" # gestao-Hermes
FOLDER_RAW = None # Será encontrada dentro de KnowledgeHermes
FOLDER_INTELLIGENCE = None # Será encontrada dentro de KnowledgeHermes

def init_services():
    # Firebase
    if not firebase_admin._apps:
        cred = credentials.Certificate(str(CRED_PATH))
        firebase_admin.initialize_app(cred)
    db = firestore.client()

    # Google Drive (Assumindo que hermes_cli já criou o token.json)
    from google.oauth2.credentials import Credentials
    creds = Credentials.from_authorized_user_file(str(BASE_DIR / 'token.json'))
    drive_service = build('drive', 'v3', credentials=creds)
    
    return db, drive_service

def get_subfolder_ids(service):
    global FOLDER_RAW, FOLDER_INTELLIGENCE
    results = service.files().list(q="name = 'KnowledgeHermes' and trashed = false").execute()
    if not results.get('files'): return
    root_id = results['files'][0]['id']
    
    # RawData
    res = service.files().list(q=f"name = 'RawData' and '{root_id}' in parents and trashed = false").execute()
    if res.get('files'): FOLDER_RAW = res['files'][0]['id']
    
    # Hermes Relational Knowledge
    res = service.files().list(q=f"name = 'Hermes Relational Knowledge' and '{root_id}' in parents and trashed = false").execute()
    if res.get('files'): FOLDER_INTELLIGENCE = res['files'][0]['id']

def migrate_files(drive_service):
    print("\n[📁] Iniciando migração de arquivos da gestao-Hermes...")
    results = drive_service.files().list(q=f"'{FOLDER_LEGACY}' in parents and trashed = false", fields="files(id, name, mimeType)").execute()
    files = results.get('files', [])
    
    for f in files:
        if 'folder' in f['mimeType']: continue
        print(f" -> Baixando para processamento: {f['name']}")
        
        # Download local para ENTRADA_HERMES (para o Gatekeeper processar)
        request = drive_service.files().get_media(fileId=f['id'])
        fh = io.FileIO(os.path.join(INPUT_DIR, f['name']), 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        
        # Opcional: Upload para a nova pasta RawData no Drive para backup
        if FOLDER_RAW:
            file_metadata = {'name': f['name'], 'parents': [FOLDER_RAW]}
            media = MediaFileUpload(os.path.join(INPUT_DIR, f['name']))
            drive_service.files().create(body=file_metadata, media_body=media).execute()

def migrate_entities(db):
    print("\n[🧠] Extraindo Entidades (Sistemas e Ações) do Firestore...")
    
    # 1. Sistemas (unidades/conhecimento_mestre)
    print(" -> Mapeando Sistemas e Hubs...")
    units = db.collection('unidades').get()
    for u in units:
        data = u.to_dict()
        name = data.get('nome') or data.get('titulo', 'Sistema Sem Nome')
        item_id = f"sys_{u.id}"
        item = {
            "id": item_id,
            "display": {"title": f"Sistema: {name}", "tldr": f"Entidade legada: {name}"},
            "technical": {"type": "system", "confidence_weight": 1.0, "created_at": datetime.now().isoformat()},
            "content": {"summary": f"Mapeamento de sistema/unidade: {name}", "details": str(data)},
            "graph": {"explicit_links": data.get('palavras_chave', [])}
        }
        db.collection('conhecimento_relacional').document(item_id).set(item)
        with open(PROCESSED_DIR / f"{item_id}.json", "w", encoding="utf-8") as f:
            json.dump(item, f, indent=2, ensure_ascii=False)

    # 2. Ações (tarefas)
    print(" -> Mapeando Ações (Tarefas) com Diário de Bordo...")
    tasks = db.collection('tarefas').get()
    for t in tasks:
        data = t.to_dict()
        title = data.get('titulo', 'Ação Sem Título')
        status = data.get('status', 'n/a')
        item_id = f"act_{t.id}"
        
        # Puxar o Diário de Bordo (Subcoleção acompanhamento)
        journal_entries = []
        try:
            logs = db.collection('tarefas').document(t.id).collection('acompanhamento').order_by('data', direction=firestore.Query.DESCENDING).get()
            for log in logs:
                l_data = log.to_dict()
                date_str = l_data.get('data')
                if hasattr(date_str, 'isoformat'): date_str = date_str.isoformat()
                journal_entries.append(f"[{date_str}] {l_data.get('descricao', '')}")
        except Exception as e:
            print(f"       ! Erro ao ler acompanhamento de {t.id}: {e}")

        journal_text = "\n".join(journal_entries) if journal_entries else "Nenhum registro no diário de bordo."

        # NOVO: Mineração Relacional via IA (Gemini 3.1)
        if journal_entries:
            print(f"       🧠 Minerando relações narrativas em: {title}...")
            from hermes_gatekeeper import call_gemini_31
            mining_prompt = f"""
            Analise o seguinte diário de bordo de uma tarefa e extraia uma lista de ENTIDADES RELACIONAIS 
            (Sistemas, Pessoas, Projetos, Documentos, Órgãos) citados. 
            Retorne APENAS uma lista de strings separadas por vírgula, sem explicações.
            Exemplo: SEI, João Silva, Orçamento 2026, INPI
            ---
            DIÁRIO: {journal_text[:3000]}
            """
            try:
                mined_links = call_gemini_31(mining_prompt)
                extra_links = [l.strip() for l in mined_links.split(",") if l.strip()]
                print(f"       ✅ Relações descobertas: {extra_links}")
            except:
                extra_links = []
        else:
            extra_links = []

        # Filtro de Ruído Relacional (Remove placeholders de legado)
        forbidden_links = ["GOOGLE", "GOOGLE TASKS", "GOOGLE_TASKS", "NÃO CLASSIFICADA", "GERAL"]
        base_links = [data.get('categoria'), data.get('projeto')]
        all_potential_links = [l for l in (base_links + extra_links) if l and l.upper() not in forbidden_links]
        
        item = {
            "id": item_id,
            "display": {"title": f"Ação: {title}", "tldr": f"Tarefa legada com status: {status}"},
            "technical": {"type": "action", "confidence_weight": 0.8, "created_at": datetime.now().isoformat()},
            "content": {"summary": f"Tarefa importada do sistema original.", "details": f"Status: {status} | Notas: {data.get('notas', '')}", "journal": journal_text},
            "graph": {"explicit_links": list(set(all_potential_links))}
        }
        db.collection('conhecimento_relacional').document(item_id).set(item)
        with open(PROCESSED_DIR / f"{item_id}.json", "w", encoding="utf-8") as f:
            json.dump(item, f, indent=2, ensure_ascii=False)
            
    print(f" -> {len(units)} Sistemas e {len(tasks)} Ações migradas para o modelo relacional.")

def run_gatekeeper():
    print("\n[⚙️] Ativando Gatekeeper p/ processar novos arquivos...")
    import subprocess
    venv_python = r"C:\Users\andre\Documents\Hermes\functions\venv\Scripts\python.exe"
    gatekeeper_path = r"C:\Users\andre\Documents\Hermes\hermes_gatekeeper.py"
    subprocess.run([venv_python, gatekeeper_path], check=True)

if __name__ == "__main__":
    db, drive = init_services()
    get_subfolder_ids(drive)
    
    # Executa Migração - PRIORIDADE: ENTES RELACIONAIS PRIMEIRO
    migrate_entities(db)
    migrate_files(drive)
    
    # Chama o Gatekeeper para dar inteligência aos arquivos recém-migrados
    run_gatekeeper()
    
    # Sincronia Final com o Drive (Garante que tudo subiu e gera o Índice/Obsidian)
    print("\n[☁️] Finalizando sincronia com a nuvem...")
    from hermes_cli import push_knowledge_to_drive, generate_master_index, export_to_obsidian, push_raw_files_to_drive
    push_raw_files_to_drive()
    push_knowledge_to_drive(db)
    generate_master_index(db)
    export_to_obsidian()
    
    print("\n[✅] Migração e Sincronia concluídas! O Drive agora é o seu mestre de conhecimento.")
