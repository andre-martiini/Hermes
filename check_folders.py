import os
import sys
from pathlib import Path

# Adiciona o diretório atual ao path para importar hermes_cli
sys.path.append(str(Path(__file__).parent))

try:
    from hermes_cli import get_drive_service
    service = get_drive_service()
    
    # Procurar pelas duas pastas principais
    for folder_name in ['gestao-Hermes', 'KnowledgeHermes']:
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, fields='files(id, name)').execute()
        folders = results.get('files', [])
        
        print(f"\n--- Buscando: {folder_name} ---")
        if not folders:
            print("Nenhuma pasta encontrada.")
        else:
            for f in folders:
                print(f"ID: {f['id']} | Nome: {f['name']}")
            
except Exception as e:
    print(f"Erro: {e}")
