import os
import sys
from pathlib import Path

# Adiciona o diretório do Hermes ao path
HERMES_DIR = Path(r"C:\Users\andre\Documents\Hermes")
sys.path.append(str(HERMES_DIR))

from hermes_cli import init_db

def main():
    db = init_db()
    print("📋 [HERMES] Buscando localização dos Diários de Bordo...")
    
    # Tenta encontrar em tarefas
    tasks = db.collection('tarefas').limit(50).stream()
    found = False
    for t in tasks:
        data = t.to_dict()
        # Verifica se existe campo 'diario' ou 'logs' ou 'historico'
        possiveis_campos = ['diario', 'log', 'historico', 'descricao', 'notas']
        for campo in possiveis_campos:
            if campo in data and data[campo]:
                print(f"✅ Encontrado campo '{campo}' na tarefa {t.id}")
                print(f"   Conteúdo: {str(data[campo])[:200]}...")
                found = True
        
        # Verifica subcoleções
        colls = [c.id for c in t.reference.collections()]
        if colls:
            print(f"📂 Tarefa {t.id} possui subcoleções: {colls}")
            for c_id in colls:
                sample = db.collection('tarefas').document(t.id).collection(c_id).limit(1).get()
                if sample:
                    print(f"   Exemplo de {c_id}: {sample[0].to_dict()}")
            found = True
            
    if not found:
        # Tenta buscar uma coleção global de diários
        print("❓ Não encontrado nas tarefas. Buscando coleção global 'diarios' ou 'historico'...")
        globals = ['diarios', 'historico', 'logs_tarefas', 'task_logs']
        for g in globals:
            sample = db.collection(g).limit(1).get()
            if sample:
                print(f"✨ Encontrada coleção global: {g}")
                print(f"   Amostra: {sample[0].to_dict()}")
                found = True

if __name__ == "__main__":
    main()
