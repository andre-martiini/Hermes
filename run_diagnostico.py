import os
import sys
import json
from pathlib import Path

# Adiciona o diretório do Hermes ao path
HERMES_DIR = Path(r"C:\Users\andre\Documents\Hermes")
sys.path.append(str(HERMES_DIR))

from hermes_cli import init_db

def main():
    db = init_db()
    output_info = []
    
    # Pega uma amostra de tarefas
    tasks = db.collection('tarefas').limit(5).get()
    for t in tasks:
        data = t.to_dict()
        task_info = {
            "id": t.id,
            "fields": list(data.keys()),
            "data_sample": {k: str(v)[:100] for k, v in data.items() if v}
        }
        # Tenta pegar subcoleções de forma segura
        try:
            colls = [c.id for c in t.reference.collections()]
            task_info["subcollections"] = colls
        except:
            task_info["subcollections"] = "error_listing"
            
        output_info.append(task_info)
        
    # Salva em um arquivo para leitura garantida
    with open("C:\\Users\\andre\\Documents\\Hermes\\diagnostico_diario.json", "w", encoding="utf-8") as f:
        json.dump(output_info, f, indent=2, ensure_ascii=False)
    print("Sucesso! Diagnóstico salvo em diagnostico_diario.json")

if __name__ == "__main__":
    main()
