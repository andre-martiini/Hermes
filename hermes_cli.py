
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

def sync_google_tasks(db):
    """
    Busca tarefas pendentes no Google e sincroniza com Firestore.
    """
    try:
        service = get_tasks_service()
        
        # Busca todas as listas de tarefas
        results = service.tasklists().list().execute()
        tasklists = results.get('items', [])
        
        # Procura a lista específica 'tarefa-gerais' - Busca mais flexível
        tasklist_id = None
        target_name = 'tarefa-gerais'
        
        print(f"Listas encontradas: {[l['title'] for l in tasklists]}")

        for item in tasklists:
            # Match exato ou flexível (sem plurais/traços)
            clean_title = item['title'].lower().replace(' ', '-').replace('s', '') if 'tarefa' in item['title'].lower() else item['title'].lower()
            clean_target = target_name.replace('s', '')
            
            if item['title'].lower() == target_name or clean_title == clean_target:
                tasklist_id = item['id']
                print(f"Sincronizando tarefas da lista: {item['title']} (ID: {tasklist_id})")
                break
        
        if not tasklist_id:
            print(f"ERRO: Lista '{target_name}' não encontrada.")
            print("Listas disponíveis:")
            for l in tasklists:
                print(f" - {l['title']}")
            return

        # Busca todas as tarefas pendentes com paginação
        # Otimização: Traz concluídas apenas a partir do dia 1º do mês atual
        now = datetime.now()
        start_month_rfc = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%dT00:00:00Z')

        g_tasks = []
        next_page_token = None
        
        while True:
            tasks_results = service.tasks().list(
                tasklist=tasklist_id, 
                showCompleted=True, 
                showHidden=True,
                completedMin=start_month_rfc, # FILTER: Current month onwards
                pageToken=next_page_token,
                maxResults=100
            ).execute()
            
            g_tasks.extend(tasks_results.get('items', []))
            next_page_token = tasks_results.get('nextPageToken')
            if not next_page_token:
                break

        print(f"Total de tarefas identificadas (incluindo concluídas): {len(g_tasks)}")
        today = datetime.now().date()

        for gt in g_tasks:
            g_id = gt['id']
            title = gt.get('title', '(Sem Título)')
            notes = gt.get('notes', '')
            due = gt.get('due', None)
            g_status = gt.get('status')
            completed_at = gt.get('completed') # RFC3339
            
            # Formatação de data limite
            deadline = '-'
            if due:
                deadline = due.split('T')[0]

            # Mapeamento de status: Google -> Hermes
            # 'completed' -> 'concluído', 'needsAction' -> 'em andamento'
            h_status = 'concluído' if g_status == 'completed' else 'em andamento'
            
            # Classificação inteligente
            categoria, sistema, contabilizar_meta = classify_task(title, notes)
            
            # Busca se já existe no firestore pelo google_id
            existing = db.collection('tarefas').where('google_id', '==', g_id).limit(1).get()
            
            if len(existing) > 0:
                t_old = existing[0].to_dict()
                doc_ref = existing[0].reference
                
                # Comparação de versão: Last Write Wins
                h_updated = t_old.get('data_atualizacao', '')
                g_updated = gt.get('updated', '') # RFC3339 from Google
                
                # Se a versão local (Hermes) for estritamente mais recente que a do Google,
                # não sobrescrevemos localmente. O usuário deve usar push-tasks para enviar ao Google.
                if h_updated and g_updated and h_updated > g_updated:
                    print(f"[!] PRESERVADA (Local mais recente): {title}")
                    continue

                # Otimização: Só atualiza se houver mudança REAL nos campos observados
                has_changed = (
                    t_old.get('status') != h_status or
                    t_old.get('titulo') != title or
                    t_old.get('notas') != notes or
                    t_old.get('data_conclusao') != completed_at
                )
                
                if not has_changed:
                    continue

                # Preserva a data_criacao original
                data_criacao = t_old.get('data_criacao')
                
                task_data = {
                    'titulo': title,
                    'data_limite': deadline,
                    'categoria': categoria,
                    'contabilizar_meta': contabilizar_meta,
                    'notas': notes,
                    'status': h_status,
                    'data_conclusao': completed_at,
                    'data_atualizacao': g_updated # Sincroniza o timestamp com o do Google
                }
                if sistema: task_data['sistema'] = sistema
                
                doc_ref.update(task_data)
                print(f"[-] PULL OK (Sincronizado): {title} | Status: {h_status}")
            else:
                # Nova Tarefa: Google já filtrou concluídas antigas via completedMin
                # Mas por segurança, se houver algo concluído, importamos pois passou no filtro
                
                # Tenta extrair data do título ou notas (ex: 14/02/2026)
                data_match = re.search(r'(\d{2})/(\d{2})/(\d{4})', f"{title} {notes}")
                if data_match:
                    d, m, y = data_match.groups()
                    data_criacao = f"{y}-{m}-{d}T00:00:00"
                else:
                    data_criacao = datetime.now().isoformat()

                task_data = {
                    'titulo': title,
                    'projeto': 'GOOGLE', # Unidade padrão para importados
                    'data_limite': deadline,
                    'categoria': categoria,
                    'contabilizar_meta': contabilizar_meta,
                    'google_id': g_id,
                    'notas': notes,
                    'status': h_status,
                    'data_criacao': data_criacao,
                    'data_conclusao': completed_at,
                    'data_atualizacao': gt.get('updated') # Sincroniza o timestamp inicial
                }
                if sistema: task_data['sistema'] = sistema
                
                db.collection('tarefas').add(task_data)
                print(f"[+] IMPORTADA: {title} [{categoria}] | Criada em: {data_criacao}")
                
        print(f"\nSINCROIZAÇÃO CONCLUÍDA: {len(g_tasks)} tarefas processadas.")

    except HttpError as err:
        print(f"ERRO GOOGLE API: {err}")
    except Exception as e:
        print(f"ERRO INESPERADO: {str(e)}")

def push_google_tasks(db):
    """
    Pega as tarefas do Firestore (que possuem google_id) e atualiza o Google Tasks.
    """
    try:
        service = get_tasks_service()
        
        # Busca todas as listas de tarefas
        results = service.tasklists().list().execute()
        tasklists = results.get('items', [])
        
        # Procura a lista específica 'tarefa-gerais' - Busca mais flexível
        tasklist_id = None
        target_name = 'tarefa-gerais'
        
        for item in tasklists:
            # Match exato ou flexível (sem plurais/traços)
            clean_title = item['title'].lower().replace(' ', '-').replace('s', '') if 'tarefa' in item['title'].lower() else item['title'].lower()
            clean_target = target_name.replace('s', '')
            
            if item['title'].lower() == target_name or clean_title == clean_target:
                tasklist_id = item['id']
                print(f"Enviando atualizações para a lista: {item['title']} (ID: {tasklist_id})")
                break
        
        if not tasklist_id:
            print(f"ERRO: Lista '{target_name}' não encontrada para o PUSH.")
            return

        # Busca versões do Google para comparar (para os que já existem)
        g_results = service.tasks().list(tasklist=tasklist_id, showCompleted=True, showHidden=True, maxResults=100).execute()
        g_tasks_map = {item['id']: item for item in g_results.get('items', [])}

        # Busca todas as tarefas do Firestore que podem precisar de PUSH
        tasks_ref = db.collection('tarefas').stream()
        
        count = 0
        for doc in tasks_ref:
            t = doc.to_dict()
            g_id = t.get('google_id')
            h_status = t.get('status')
            
            # FILTRO DE OTIMIZAÇÃO: Ignorar concluídas antigas (antes do mês atual)
            # Isso impede que o push tente sincronizar histórico legado desnecessariamente
            if h_status == 'concluído':
                data_conclusao = t.get('data_conclusao')
                # Start of month in ISO format for string comparison
                start_month_iso = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
                
                # Se não tem data de conclusão (antiga) ou é anterior ao mês atual, PULA.
                if not data_conclusao or data_conclusao < start_month_iso:
                    continue
            
            # 0. DELEÇÃO: Se a tarefa foi marcada como excluída no Hermes
            if h_status == 'excluído':
                if g_id:
                    try:
                        service.tasks().delete(tasklist=tasklist_id, task=g_id).execute()
                        print(f"[X] G-DELETE OK: {t['titulo']}")
                    except HttpError as e:
                        if e.resp.status == 404:
                            print(f"[!] SKIP DELETE (Não encontrada no Google): {t['titulo']}")
                        else:
                            print(f"[X] ERRO AO DELETAR NO GOOGLE ({t['titulo']}): {e}")
                
                # Independente se deletou no Google ou não (podia nem existir lá), removemos do Firestore
                doc.reference.delete()
                print(f"[*] FS-REMOVE OK: {t['titulo']}")
                count += 1
                continue

            # 1. Preparação comum
            due_date = None
            if t.get('data_limite') and t.get('data_limite') != '-':
                due_date = f"{t['data_limite']}T00:00:00Z"
            
            g_status = 'completed' if t.get('status') == 'concluído' else 'needsAction'

            if not g_id:
                # 2. CRIAÇÃO: Sem google_id ainda
                new_task_body = {
                    'title': t['titulo'],
                    'notes': t.get('notas', ''),
                    'status': g_status
                }
                if due_date: new_task_body['due'] = due_date
                
                try:
                    g_new_task = service.tasks().insert(tasklist=tasklist_id, body=new_task_body).execute()
                    doc.reference.update({
                        'google_id': g_new_task['id'],
                        'data_atualizacao': g_new_task.get('updated')
                    })
                    print(f"[+] PUSH NEW: {t['titulo']}")
                    count += 1
                except HttpError as e:
                    print(f"[X] ERRO AO CRIAR NO GOOGLE ({t['titulo']}): {e}")
                continue

            # 3. ATUALIZAÇÃO: Conferência de versão
            g_task = g_tasks_map.get(g_id)
            if g_task:
                h_updated = t.get('data_atualizacao', '')
                g_updated = g_task.get('updated', '')
                
                if h_updated and g_updated and g_updated > h_updated:
                    print(f"[!] SKIP PUSH: {t['titulo']} (Versão no Google é mais recente)")
                    continue
                
                if h_updated == g_updated:
                    continue

            # Prepara body de update
            updated_task_body = {
                'id': g_id,
                'title': t['titulo'],
                'notes': t.get('notas', ''),
                'status': g_status
            }
            if due_date: updated_task_body['due'] = due_date

            try:
                g_updated_task = service.tasks().update(tasklist=tasklist_id, task=g_id, body=updated_task_body).execute()
                doc.reference.update({'data_atualizacao': g_updated_task.get('updated')})
                print(f"[^] PUSH OK: {t['titulo']}")
                count += 1
            except HttpError as e:
                print(f"[X] ERRO NO PUSH ({t['titulo']}): {e}")

        print(f"\nSINCROIZAÇÃO (PUSH) CONCLUÍDA: {count} tarefas processadas.")

    except Exception as e:
        print(f"ERRO NO PUSH: {str(e)}")

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
    
    # Callback para mudanças em tempo real
    def on_snapshot(doc_snapshot, changes, read_time):
        for doc in doc_snapshot:
            data = doc.to_dict()
            if not data: continue
            
            status = data.get('status')
            if status == 'requested':
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] COMANDO RECEBIDO: Inciando sincronização...")
                
                # Marca como processando
                sync_doc_ref.update({'status': 'processing'})
                
                try:
                    # Executa Push (Hermes -> Google)
                    print(">>> Enviando dados para o Google...")
                    push_google_tasks(db)
                    
                    # Executa Pull (Google -> Hermes) - Opcional, mas bom para garantir consistência
                    print(">>> Buscando novidades do Google...")
                    sync_google_tasks(db)
                    
                    sync_doc_ref.update({
                        'status': 'completed',
                        'last_success': datetime.now().isoformat()
                    })
                    print("SKU: Sincronização concluída com sucesso.")
                    
                except Exception as e:
                    print(f"ERRO DE SINCRONIZAÇÃO: {e}")
                    sync_doc_ref.update({
                        'status': 'error',
                        'error_message': str(e)
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
