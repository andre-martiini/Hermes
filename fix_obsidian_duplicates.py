import os
import json
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

# Configurações
BASE_DIR = r"C:\Users\andre\Documents\Hermes"
OBSIDIAN_LOCAL_DIR = os.path.join(BASE_DIR, "OBSIDIAN_VIEW")

def get_drive_service():
    creds = Credentials.from_authorized_user_file(os.path.join(BASE_DIR, 'token.json'))
    return build('drive', 'v3', credentials=creds)

def clean_and_push_obsidian():
    service = get_drive_service()
    
    # 1. Localizar a pasta raiz KnowledgeHermes
    results = service.files().list(q="name = 'KnowledgeHermes' and trashed = false").execute()
    if not results.get('files'):
        print("Erro: Pasta KnowledgeHermes não encontrada no Drive.")
        return
    root_id = results['files'][0]['id']
    
    # 2. Localizar a subpasta OBSIDIAN_GRAPH
    results = service.files().list(q=f"name = 'OBSIDIAN_GRAPH' and '{root_id}' in parents and trashed = false").execute()
    if not results.get('files'):
        print("Pasta OBSIDIAN_GRAPH não encontrada. Criando nova...")
        folder = service.files().create(body={'name': 'OBSIDIAN_GRAPH', 'parents': [root_id], 'mimeType': 'application/vnd.google-apps.folder'}, fields='id').execute()
        folder_id = folder.get('id')
    else:
        folder_id = results['files'][0]['id']
        print(f"Limpando arquivos existentes em OBSIDIAN_GRAPH (ID: {folder_id})...")
        
        # 3. Deletar TODOS os arquivos atuais na pasta do Drive
        page_token = None
        while True:
            results = service.files().list(q=f"'{folder_id}' in parents and trashed = false", fields="nextPageToken, files(id, name)", pageToken=page_token).execute()
            items = results.get('files', [])
            for item in items:
                print(f" -> Deletando: {item['name']}")
                service.files().delete(fileId=item['id']).execute()
            page_token = results.get('nextPageToken')
            if not page_token: break
            
    # 4. Upload Massivo da pasta local OBSIDIAN_VIEW
    print("\nIniciando upload da carga limpa...")
    files_to_upload = [f for f in os.listdir(OBSIDIAN_LOCAL_DIR) if f.endswith(".md")]
    total = len(files_to_upload)
    
    for i, filename in enumerate(files_to_upload):
        print(f"[{i+1}/{total}] Subindo: {filename}")
        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaFileUpload(os.path.join(OBSIDIAN_LOCAL_DIR, filename), mimetype='text/markdown')
        service.files().create(body=file_metadata, media_body=media).execute()

    print("\n✅ Sucesso! A pasta OBSIDIAN_GRAPH no Drive está 100% sincronizada e sem duplicados.")

if __name__ == "__main__":
    clean_and_push_obsidian()
