
import argparse
import json
import re
import os
import sys
import base64
from datetime import datetime, timezone
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

# Escopos para Google APIs (Tasks e Gmail Readonly)
SCOPES = [
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/gmail.readonly'
]

DEBUG_MODE = True # Ativa log detalhado de cada tarefa no terminal do sistema

# Configuração do Firebase
KEY_FILE = 'firebase_service_account_key.json'

def get_units_mapping(db):
    mapping = {
        'CLC': ['licitação', 'pregão', 'irp'],
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
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("ERRO: 'credentials.json' não encontrado. Baixe do Google Cloud Console.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def get_tasks_service():
    return build('tasks', 'v1', credentials=get_google_creds())

def get_gmail_service():
    return build('gmail', 'v1', credentials=get_google_creds())

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
            title = gt.get('title', '(Sem Título)')
            g_updated = gt.get('updated', '')
            due = gt.get('due', None)
            deadline = due.split('T')[0] if due else '-'
            h_status = 'concluído' if gt.get('status') == 'completed' else 'em andamento'
            
            categoria, sistema, contabilizar_meta = classify_task(title, gt.get('notes', ''), dynamic_mapping)
            existing_data = local_tasks.get(g_id) or local_tasks.get(f"title_{title}")
            
            if existing_data:
                doc_id, t_old = existing_data
                if not t_old.get('google_id'):
                    db.collection('tarefas').document(doc_id).update({'google_id': g_id, 'data_atualizacao': g_updated, 'notas': gt.get('notes', '')})
                    log(f"[*] VINCULADA: {title}")
                    continue
                h_updated = t_old.get('data_atualizacao', '')
                if h_updated and g_updated and h_updated >= g_updated: continue
                has_changed = (t_old.get('status') != h_status or t_old.get('titulo') != title or t_old.get('data_limite') != deadline)
                if has_changed:
                    db.collection('tarefas').document(doc_id).update({
                        'titulo': title, 'data_limite': deadline, 'status': h_status,
                        'data_conclusao': gt.get('completed'), 'data_atualizacao': g_updated,
                        'notas': gt.get('notes', ''), 'sync_status': 'updated', 'last_sync_date': datetime.now().isoformat()
                    })
                    log(f"[-] ATUALIZADA: {title}")
            else:
                db.collection('tarefas').add({
                    'titulo': title, 'projeto': 'GOOGLE', 'data_limite': deadline,
                    'google_id': g_id, 'status': h_status, 'data_criacao': datetime.now().isoformat(),
                    'data_conclusao': gt.get('completed'), 'data_atualizacao': g_updated,
                    'categoria': categoria, 'contabilizar_meta': contabilizar_meta,
                    'notas': gt.get('notes', ''), 'sync_status': 'new', 'last_sync_date': datetime.now().isoformat()
                })
                log(f"[+] IMPORTADA: {title}")
        cleanup_old_sync_badges(db, log)
        log("PULL CONCLUÍDO.", force_ui=True)
    except Exception as e:
        log(f"ERRO PULL: {e}", force_ui=True)

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
            due_date = f"{t['data_limite']}T00:00:00Z" if t.get('data_limite') and t.get('data_limite') != '-' else None
            g_status = 'completed' if t.get('status') == 'concluído' else 'needsAction'
            if not g_id:
                new_task = service.tasks().insert(tasklist=tasklist_id, body={'title': t['titulo'], 'notes': t.get('notas', ''), 'status': g_status, 'due': due_date}).execute()
                doc.reference.update({'google_id': new_task['id'], 'data_atualizacao': new_task.get('updated')})
                log(f"[+] ENVIADA: {t['titulo']}"); count += 1
                continue
            g_task = g_tasks_map.get(g_id)
            if g_task and t.get('data_atualizacao', '') > g_task.get('updated', ''):
                service.tasks().update(tasklist=tasklist_id, task=g_id, body={'id': g_id, 'title': t['titulo'], 'notes': t.get('notas', ''), 'status': g_status, 'due': due_date}).execute()
                log(f"[^] ATUALIZADA NO GOOGLE: {t['titulo']}"); count += 1
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
    args = parser.parse_args()
    if not args.command: parser.print_help(); return
    db = init_db()
    if args.command == 'sync-tasks': sync_google_tasks(db)
    elif args.command == 'watch': watch_commands(db)
    elif args.command == 'sync-pix': sync_pix_emails(db)

if __name__ == '__main__': main()
