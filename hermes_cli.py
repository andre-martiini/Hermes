
import argparse
import json
import os
import sys
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# Configuração do Firebase
KEY_FILE = 'firebase_service_account_key.json'

def init_db():
    if not os.path.exists(KEY_FILE):
        print(f"ERRO: Arquivo de chave {KEY_FILE} não encontrado.")
        sys.exit(1)
    
    cred = credentials.Certificate(KEY_FILE)
    firebase_admin.initialize_app(cred)
    return firestore.client()

def list_tasks(db):
    tasks_ref = db.collection('tarefas')
    docs = tasks_ref.stream()
    tasks = []
    for doc in docs:
        d = doc.to_dict()
        d['id'] = doc.id
        tasks.append(d)
    print(json.dumps(tasks, indent=2, ensure_ascii=False))

def create_task(db, title, unit, deadline, status):
    # Validações rigorosas
    if len(title) < 10:
        print("ERRO: Título muito curto (mínimo 10 caracteres).")
        return

    valid_status = ['pendente', 'em andamento', 'concluído', 'bloqueado']
    if status not in valid_status:
        print(f"ERRO: Status inválido. Use: {', '.join(valid_status)}")
        return

    # Check if unit exists (opcional, mas recomendado)
    # Identificação PGC
    is_pgc = any(x in unit.upper() for x in ['CLC', 'ASSIST', 'ESTUDANTIL', 'ANTIU'])
    
    task_data = {
        'titulo': title,
        'projeto': unit,
        'data_limite': deadline,
        'status': status,
        'prioridade': 'média',
        'data_criacao': datetime.now().isoformat(),
        'data_atualizacao': datetime.now().isoformat(),
        'acompanhamento': [],
        'entregas_relacionadas': []
    }

    doc_ref = db.collection('tarefas').add(task_data)
    print(f"SUCESSO: Tarefa criada com ID {doc_ref[1].id}")
    if is_pgc:
        print("NOTA: Esta tarefa foi identificada como PGC/Estratégica.")

def add_note(db, task_id, note):
    task_ref = db.collection('tarefas').document(task_id)
    task = task_ref.get()
    
    if not task.exists:
        print(f"ERRO: Tarefa {task_id} não encontrada.")
        return

    new_log = {
        'data': datetime.now().isoformat(),
        'nota': note
    }
    
    task_ref.update({
        'acompanhamento': firestore.ArrayUnion([new_log]),
        'data_atualizacao': datetime.now().isoformat()
    })
    print(f"SUCESSO: Nota adicionada à tarefa {task_id}")

def update_status(db, task_id, status, note=None):
    valid_status = ['pendente', 'em andamento', 'concluído', 'bloqueado']
    if status not in valid_status:
        print(f"ERRO: Status inválido.")
        return

    task_ref = db.collection('tarefas').document(task_id)
    updates = {
        'status': status,
        'data_atualizacao': datetime.now().isoformat()
    }
    
    if note:
        new_log = {'data': datetime.now().isoformat(), 'nota': note}
        updates['acompanhamento'] = firestore.ArrayUnion([new_log])

    task_ref.update(updates)
    print(f"SUCESSO: Status da tarefa {task_id} atualizado para {status}")

def main():
    parser = argparse.ArgumentParser(description='Hermes DB Admin CLI for Bots')
    subparsers = parser.add_subparsers(dest='command')

    # Listar tarefas
    subparsers.add_parser('list-tasks', help='Lista todas as tarefas')

    # Criar tarefa
    create_p = subparsers.add_parser('create-task', help='Cria uma nova tarefa')
    create_p.add_argument('--title', required=True)
    create_p.add_argument('--unit', required=True)
    create_p.add_argument('--deadline', required=True, help='YYYY-MM-DD')
    create_p.add_argument('--status', default='pendente')

    # Adicionar nota
    note_p = subparsers.add_parser('add-note', help='Adiciona nota de acompanhamento')
    note_p.add_argument('--id', required=True)
    note_p.add_argument('--text', required=True)

    # Atualizar status
    status_p = subparsers.add_parser('update-status', help='Atualiza status da tarefa')
    status_p.add_argument('--id', required=True)
    status_p.add_argument('--status', required=True)
    status_p.add_argument('--note', help='Nota opcional justificando a mudança')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    db = init_db()

    if args.command == 'list-tasks':
        list_tasks(db)
    elif args.command == 'create-task':
        create_task(db, args.title, args.unit, args.deadline, args.status)
    elif args.command == 'add-note':
        add_note(db, args.id, args.text)
    elif args.command == 'update-status':
        update_status(db, args.id, args.status, args.note)

if __name__ == '__main__':
    main()
