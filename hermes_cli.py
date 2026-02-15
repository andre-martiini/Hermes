
import argparse
import json
import re
import os
import sys
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, firestore
import time

# Imports para Google Tasks API
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Escopo para leitura e escrita de tarefas (Push/Pull)
SCOPES = ['https://www.googleapis.com/auth/tasks']
DEBUG_MODE = True # Ativa log detalhado de cada tarefa no terminal do sistema

# Configuração do Firebase
KEY_FILE = 'firebase_service_account_key.json'

def init_db():
    if not os.path.exists(KEY_FILE):
        print(f"ERRO: Arquivo de chave {KEY_FILE} não encontrado.")
        sys.exit(1)
    
    cred = credentials.Certificate(KEY_FILE)
    firebase_admin.initialize_app(cred)
    return firestore.client()

def get_tasks_service():
    """
    Autenticação básica via credentials.json e token.json local.
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("ERRO: 'credentials.json' não encontrado. Baixe do Google Cloud Console.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('tasks', 'v1', credentials=creds)

def sync_google_tasks(db, log_list=None, sync_ref=None):
    """
    Busca tarefas pendentes no Google e sincroniza com Firestore.
    """
    last_ui_update = [0]
    def log(msg, force_ui=False):
        print(msg)
        if log_list is not None: 
            log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            now_ts = time.time()
            if sync_ref and (force_ui or now_ts - last_ui_update[0] > 1.2):
                try: 
                    sync_ref.update({'logs': log_list})
                    last_ui_update[0] = now_ts
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
            # REMOVIDO: completedMin para garantir que pegamos tarefas de ontem mesmo que o Google atrase o selo de tempo
            g_results = service.tasks().list(
                tasklist=tasklist_id, 
                showCompleted=True, 
                showHidden=True, 
                maxResults=100,
                pageToken=next_page_token
            ).execute()
            
            items = g_results.get('items', [])
            g_tasks.extend(items)
            
            # Limite de segurança se não quiser ler milhares de tarefas antigas
            if len(g_tasks) >= 200 or not g_results.get('nextPageToken'):
                break
            next_page_token = g_results.get('nextPageToken')

        log(f"Total de {len(g_tasks)} tarefas identificadas no Google. Analisando...", force_ui=True)

        # OTIMIZAÇÃO: Carrega tarefas locais de uma vez (apenas as que têm google_id)
        local_docs = db.collection('tarefas').get() # Carrega tudo para garantir que pegamos tarefas novas sem ID
        local_tasks = {}
        for t in local_docs:
            d = t.to_dict()
            gid = d.get('google_id')
            if gid:
                local_tasks[gid] = (t.id, d)
            else:
                # Indexa por título para evitar duplicatas se a tarefa já existe mas está sem ID
                local_tasks[f"title_{d.get('titulo')}"] = (t.id, d)

        for gt in g_tasks:
            g_id = gt['id']
            title = gt.get('title', '(Sem Título)')
            g_updated = gt.get('updated', '')
            due = gt.get('due', None)
            deadline = due.split('T')[0] if due else '-'
            h_status = 'concluído' if gt.get('status') == 'completed' else 'em andamento'
            
            # Log de processamento para auditoria no terminal
            if DEBUG_MODE:
                log(f"Google encontrou: {title} (ID: {g_id[:8]}...)")
            
            categoria, sistema, contabilizar_meta = classify_task(title, gt.get('notes', ''))
            
            existing_data = local_tasks.get(g_id) or local_tasks.get(f"title_{title}")
            
            if existing_data:
                doc_id, t_old = existing_data
                
                # Se não tem google_id mas o título coincide, vincula
                if not t_old.get('google_id'):
                    db.collection('tarefas').document(doc_id).update({'google_id': g_id, 'data_atualizacao': g_updated})
                    log(f"[*] VINCULADA: {title}")
                    continue

                # Só atualiza se o Google tiver algo mais novo
                h_updated = t_old.get('data_atualizacao', '')
                if h_updated and g_updated and h_updated >= g_updated:
                    continue

                has_changed = (
                    t_old.get('status') != h_status or
                    t_old.get('titulo') != title or
                    t_old.get('data_conclusao') != gt.get('completed') or
                    t_old.get('data_limite') != deadline
                )
                
                if has_changed:
                    db.collection('tarefas').document(doc_id).update({
                        'titulo': title, 'data_limite': deadline, 'status': h_status,
                        'data_conclusao': gt.get('completed'), 'data_atualizacao': g_updated
                    })
                    log(f"[-] ATUALIZADA: {title}")
            else:
                db.collection('tarefas').add({
                    'titulo': title, 'projeto': 'GOOGLE', 'data_limite': deadline,
                    'google_id': g_id, 'status': h_status, 'data_criacao': datetime.now().isoformat(),
                    'data_conclusao': gt.get('completed'), 'data_atualizacao': g_updated,
                    'categoria': categoria, 'contabilizar_meta': contabilizar_meta
                })
                log(f"[+] IMPORTADA: {title}")
                
        log("PULL CONCLUÍDO.", force_ui=True)
    except Exception as e:
        log(f"ERRO PULL: {e}", force_ui=True)

def push_google_tasks(db, log_list=None, sync_ref=None):
    """
    Pega as tarefas do Firestore (que possuem google_id) e atualiza o Google Tasks.
    """
    last_ui_update = [0]
    def log(msg, force_ui=False):
        print(msg)
        if log_list is not None: 
            log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            now_ts = time.time()
            if sync_ref and (force_ui or now_ts - last_ui_update[0] > 1.2):
                try: 
                    sync_ref.update({'logs': log_list})
                    last_ui_update[0] = now_ts
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

        g_results = service.tasks().list(tasklist=tasklist_id, showCompleted=True, showHidden=True, maxResults=100).execute()
        g_tasks_map = {item['id']: item for item in g_results.get('items', [])}
        tasks = db.collection('tarefas').stream()
        
        count = 0
        for doc in tasks:
            t = doc.to_dict()
            g_id = t.get('google_id')
            h_status = t.get('status')
            
            if h_status == 'excluído':
                if g_id:
                    try: service.tasks().delete(tasklist=tasklist_id, task=g_id).execute()
                    except: pass
                    log(f"[X] REMOVIDA: {t['titulo']}")
                doc.reference.delete()
                continue

            # Só processa se houve mudança real ou tarefa nova
            due_date = f"{t['data_limite']}T00:00:00Z" if t.get('data_limite') and t.get('data_limite') != '-' else None
            g_status = 'completed' if t.get('status') == 'concluído' else 'needsAction'

            if not g_id:
                new_task = service.tasks().insert(tasklist=tasklist_id, body={'title': t['titulo'], 'notes': t.get('notas', ''), 'status': g_status, 'due': due_date}).execute()
                doc.reference.update({'google_id': new_task['id'], 'data_atualizacao': new_task.get('updated')})
                log(f"[+] ENVIADA: {t['titulo']}")
                count += 1
                continue

            g_task = g_tasks_map.get(g_id)
            if g_task and t.get('data_atualizacao', '') > g_task.get('updated', ''):
                service.tasks().update(tasklist=tasklist_id, task=g_id, body={'id': g_id, 'title': t['titulo'], 'notes': t.get('notas', ''), 'status': g_status, 'due': due_date}).execute()
                log(f"[^] ATUALIZADA NO GOOGLE: {t['titulo']}")
                count += 1

        log(f"PUSH FINALIZADO: {count} atualizações.", force_ui=True)
    except Exception as e:
        log(f"ERRO PUSH: {e}", force_ui=True)

def list_tasks(db):
    tasks_ref = db.collection('tarefas')
    docs = tasks_ref.stream()
    tasks = []
    for doc in docs:
        d = doc.to_dict()
        d['id'] = doc.id
        tasks.append(d)
    print(json.dumps(tasks, indent=2, ensure_ascii=False))

def classify_task(title, notes):
    """
    Classifica a tarefa com base em tags no título ou notas.
    Suporta formatos: [TAG] ou Tag: TAG
    """
    # Normalização para busca
    text = f"{title} {notes}".upper()
    
    categoria = 'NÃO CLASSIFICADA'
    contabilizar_meta = False

    # Regex para encontrar tags em [] ou após 'TAG: '
    tags = re.findall(r'\[(.*?)\]|TAG:\s*([\w\-]+)', text)
    tags = [t[0] or t[1] for t in tags]
    tags = [t.upper() for t in tags]

    # Mapeamento de Tags para Categorias
    if any(tag in ['CLC', 'LICITACAO'] for tag in tags):
        categoria = 'CLC'
        contabilizar_meta = True
    elif any(tag in ['ASSISTENCIA', 'ESTUDANTIL', 'ASSISTENCIA-ESTUDANTIL'] for tag in tags):
        categoria = 'ASSISTÊNCIA'
        contabilizar_meta = True
    elif 'GERAL' in tags:
        categoria = 'GERAL'
    elif 'NAO CLASSIFICADA' in tags:
        categoria = 'NÃO CLASSIFICADA'

    return categoria, None, contabilizar_meta

def create_task(db, title, unit, deadline, status, notes=''):
    # Validações rigorosas
    if len(title) < 10:
        print("ERRO: Título muito curto (mínimo 10 caracteres).")
        return

    valid_status = ['em andamento', 'concluído']
    if status not in valid_status:
        print(f"ERRO: Status inválido. Use: {', '.join(valid_status)}")
        return

    # Nova Lógica de Classificação
    categoria, sistema, contabilizar_meta = classify_task(title, notes)
    
    task_data = {
        'titulo': title,
        'projeto': unit,
        'data_limite': deadline,
        'status': status,
        'prioridade': 'média',
        'categoria': categoria,
        'contabilizar_meta': contabilizar_meta,
        'data_criacao': datetime.now().isoformat(),
        'data_atualizacao': datetime.now().isoformat(),
        'acompanhamento': [],
        'entregas_relacionadas': []
    }
    
    if sistema:
        task_data['sistema'] = sistema

    doc_ref = db.collection('tarefas').add(task_data)
    print(f"SUCESSO: Tarefa {categoria} criada com ID {doc_ref[1].id}")
    if sistema:
        print(f"SISTEMA IDENTIFICADO: {sistema}")



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
    valid_status = ['em andamento', 'concluído']
    if status not in valid_status:
        print(f"ERRO: Status inválido. Use: {', '.join(valid_status)}")
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
def watch_commands(db):
    """
    Monitora a coleção 'system' documento 'sync' para disparar sincronização.
    """
    print("MÓDULO DE SINCRONIZAÇÃO AUTOMÁTICA INICIADO")
    print("Aguardando comandos do painel web... (Ctrl+C para encerrar)")
    
    sync_doc_ref = db.collection('system').document('sync')
    
    def on_snapshot(doc_snapshot, changes, read_time):
        for doc in doc_snapshot:
            data = doc.to_dict()
            if not data: continue
            
            status = data.get('status')
            if status == 'requested':
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] COMANDO RECEBIDO")
                
                log_entries = ["Iniciando processamento..."]
                sync_doc_ref.update({
                    'status': 'processing',
                    'logs': log_entries
                })
                
                try:
                    # Executa Push
                    push_google_tasks(db, log_entries, sync_doc_ref)
                    
                    # Executa Pull
                    sync_google_tasks(db, log_entries, sync_doc_ref)
                    
                    # Finaliza Logs
                    sync_doc_ref.update({
                        'status': 'completed',
                        'last_success': datetime.now().isoformat(),
                        'logs': log_entries
                    })
                    print("Sincronização concluída.")
                    
                except Exception as e:
                    print(f"ERRO: {e}")
                    log_entries.append(f"ERRO FATAL: {str(e)}")
                    sync_doc_ref.update({
                        'status': 'error',
                        'error_message': str(e),
                        'logs': log_entries
                    })
            
    doc_watch = sync_doc_ref.on_snapshot(on_snapshot)
    
    while True:
        time.sleep(1)

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
    create_p.add_argument('--notes', default='', help='Notas para classificação via regex')



    # Adicionar nota
    note_p = subparsers.add_parser('add-note', help='Adiciona nota de acompanhamento')
    note_p.add_argument('--id', required=True)
    note_p.add_argument('--text', required=True)

    # Atualizar status
    status_p = subparsers.add_parser('update-status', help='Atualiza status da tarefa')
    status_p.add_argument('--id', required=True)
    status_p.add_argument('--status', required=True)
    status_p.add_argument('--note', help='Nota opcional justificando a mudança')

    # Sincronizar Google Tasks
    subparsers.add_parser('sync-tasks', help='Sincroniza tarefas do Google Tasks API (PULL)')
    subparsers.add_parser('push-tasks', help='Envia alterações do Firestore para o Google Tasks (PUSH)')
    subparsers.add_parser('watch', help='Modo daemon: aguarda comandos de sincronização do painel')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    db = init_db()

    if args.command == 'list-tasks':
        list_tasks(db)
    elif args.command == 'create-task':
        create_task(db, args.title, args.unit, args.deadline, args.status, args.notes if hasattr(args, 'notes') else '')
    elif args.command == 'add-note':
        add_note(db, args.id, args.text)
    elif args.command == 'update-status':
        update_status(db, args.id, args.status, args.note)

    elif args.command == 'sync-tasks':
        sync_google_tasks(db)
    elif args.command == 'push-tasks':
        push_google_tasks(db)
    elif args.command == 'watch':
        watch_commands(db)

if __name__ == '__main__':
    main()
