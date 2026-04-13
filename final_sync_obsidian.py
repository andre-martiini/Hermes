import os
import sys
import json
import shutil
from pathlib import Path

# Adiciona o diretório do Hermes ao path
HERMES_DIR = Path(r"C:\Users\andre\Documents\Hermes")
sys.path.append(str(HERMES_DIR))

from hermes_cli import init_db, export_to_obsidian, push_knowledge_to_drive, generate_master_index

def main():
    print("🚀 [HERMES] Iniciando Sincronização Final de Alta Fidelidade...")
    
    # 1. Limpar visualização local antiga para forçar regeneração
    obsidian_local = HERMES_DIR / "OBSIDIAN_VIEW"
    if obsidian_local.exists():
        print(f"🧹 Limpando cache local de visualização...")
        shutil.rmtree(obsidian_local, ignore_errors=True)
    obsidian_local.mkdir(exist_ok=True)
    
    # 2. Inicializar Banco
    db = init_db()
    
    # 3. Rodar Exportação (Isso vai usar o MarkItDown que configuramos)
    print("💎 Convertendo arquivos com MarkItDown (Alta Fidelidade)...")
    export_to_obsidian()
    
    # 4. Rodar Índice Mestre
    print("📋 Atualizando Índice Mestre...")
    generate_master_index(db)
    
    # 5. Sincronia final com Drive já está embutida no export_to_obsidian (que atualizamos)
    print("\n✅ Processo concluído! Verifique a pasta OBSIDIAN_GRAPH no seu Google Drive.")

if __name__ == "__main__":
    main()
