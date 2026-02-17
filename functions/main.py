
import re
from datetime import datetime
from firebase_functions import firestore_fn
from firebase_admin import initialize_app, firestore
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Inicializa o Firebase Admin
initialize_app()
db = firestore.client()

# Escopos para Google APIs
SCOPES = [
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/gmail.readonly'
]

def get_google_creds():
    """Busca as credenciais OAuth2 do Firestore"""
    creds_doc = db.collection('system').document('google_credentials').get()
    if not creds_doc.exists:
        raise Exception("Credenciais não encontradas no Firestore.")
    
    creds_data = creds_doc.to_dict()
    return Credentials(
        token=creds_data.get('token'),
        refresh_token=creds_data.get('refresh_token'),
        token_uri=creds_data.get('token_uri'),
        client_id=creds_data.get('client_id'),
        client_secret=creds_data.get('client_secret'),
        scopes=SCOPES
    )

def get_tasks_service():
    return build('tasks', 'v1', credentials=get_google_creds())

def get_gmail_service():
    return build('gmail', 'v1', credentials=get_google_creds())

def log_to_firestore(sync_ref, logs, message, force_update=False):
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    logs.append(log_entry)
    print(log_entry)
    if force_update:
        sync_ref.update({'logs': logs})

def classify_task(title, notes):
    text = f"{title} {notes}".upper()
    categoria, contabilizar_meta = 'NÃO CLASSIFICADA', False
    tags = re.findall(r'\[(.*?)\]|TAG:\s*([\w\-]+)', text)
    tags = [t[0].upper() if t[0] else t[1].upper() for t in tags]
    
    if any(tag in ['CLC', 'LICITACAO'] for tag in tags):
        categoria, contabilizar_meta = 'CLC', True
    elif any(tag in ['ASSISTENCIA', 'ESTUDANTIL'] for tag in tags):
        categoria, contabilizar_meta = 'ASSISTÊNCIA', True
    elif 'GERAL' in tags:
        categoria = 'GERAL'
    return categoria, None, contabilizar_meta

def sync_google_tasks_pull(service, sync_ref, logs):
    try:
        results = service.tasklists().list().execute()
        tasklist_id = next((item['id'] for item in results.get('items', []) if 'tarefa' in item['title'].lower()), None)
        if not tasklist_id: return
        
        g_tasks = []
        next_page_token = None
        while True:
            res = service.tasks().list(tasklist=tasklist_id, showCompleted=True, showHidden=True, maxResults=100, pageToken=next_page_token).execute()
            g_tasks.extend(res.get('items', []))
            if not res.get('nextPageToken') or len(g_tasks) >= 200: break
            next_page_token = res.get('nextPageToken')

        local_tasks = {t.to_dict().get('google_id'): (t.id, t.to_dict()) for t in db.collection('tarefas').stream() if t.to_dict().get('google_id')}
        
        for gt in g_tasks:
            g_id, title = gt['id'], gt.get('title', '(Sem Título)')
            g_updated = gt.get('updated', '')
            status = 'concluído' if gt.get('status') == 'completed' else 'em andamento'
            
            if g_id in local_tasks:
                doc_id, t_old = local_tasks[g_id]
                if t_old.get('data_atualizacao', '') < g_updated:
                    db.collection('tarefas').document(doc_id).update({
                        'titulo': title, 'status': status, 'data_atualizacao': g_updated,
                        'data_conclusao': gt.get('completed'), 'notas': gt.get('notes', '')
                    })
                    log_to_firestore(sync_ref, logs, f"[-] ATUALIZADA: {title}")
            else:
                cat, sys, meta = classify_task(title, gt.get('notes', ''))
                db.collection('tarefas').add({
                    'titulo': title, 'projeto': 'GOOGLE', 'google_id': g_id, 'status': status,
                    'data_criacao': datetime.now().isoformat(), 'data_atualizacao': g_updated,
                    'categoria': cat, 'contabilizar_meta': meta, 'notas': gt.get('notes', '')
                })
                log_to_firestore(sync_ref, logs, f"[+] IMPORTADA: {title}")
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"ERRO PULL: {e}")

def sync_google_tasks_push(service, sync_ref, logs):
    try:
        results = service.tasklists().list().execute()
        tasklist_id = next((item['id'] for item in results.get('items', []) if 'tarefa' in item['title'].lower()), None)
        if not tasklist_id: return
        
        g_results = service.tasks().list(tasklist=tasklist_id, showCompleted=True, showHidden=True, maxResults=100).execute()
        g_tasks_map = {item['id']: item for item in g_results.get('items', [])}
        
        for doc in db.collection('tarefas').stream():
            t = doc.to_dict()
            g_id, title = t.get('google_id'), t.get('titulo')
            if t.get('status') == 'excluído':
                if g_id: service.tasks().delete(tasklist=tasklist_id, task=g_id).execute()
                doc.reference.delete()
                continue
            
            g_status = 'completed' if t.get('status') == 'concluído' else 'needsAction'
            if not g_id:
                new_task = service.tasks().insert(tasklist=tasklist_id, body={'title': title, 'notes': t.get('notas', ''), 'status': g_status}).execute()
                doc.reference.update({'google_id': new_task['id'], 'data_atualizacao': new_task.get('updated')})
                log_to_firestore(sync_ref, logs, f"[+] ENVIADA: {title}")
            elif g_id in g_tasks_map and t.get('data_atualizacao', '') > g_tasks_map[g_id].get('updated', ''):
                service.tasks().update(tasklist=tasklist_id, task=g_id, body={'id': g_id, 'title': title, 'notes': t.get('notas', ''), 'status': g_status}).execute()
                log_to_firestore(sync_ref, logs, f"[^] ATUALIZADA NO GOOGLE: {title}")
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"ERRO PUSH: {e}")

def sync_pix_emails(service, sync_ref, logs):
    try:
        log_to_firestore(sync_ref, logs, "Buscando Pix (desde 01/02/2026)...", True)
        query = 'after:2026/02/01 subject:(Pix recebido OR Pix realizado OR "Pix enviado" OR "transferência Pix")'
        results = service.users().messages().list(userId='me', q=query, maxResults=50).execute()
        messages = results.get('messages', [])
        if not messages: return

        processed_ids = db.collection('system').document('processed_emails').get().to_dict().get('ids', [])
        
        # Cache de existentes (incluindo deletados)
        existing_google_ids = set()
        existing_transactions = []
        existing_income = []
        
        for coll in ['finance_transactions', 'finance_income']:
            for t in db.collection(coll).stream():
                data = t.to_dict()
                gid = data.get('google_message_id')
                if gid: existing_google_ids.add(gid)
                if coll == 'finance_transactions':
                    existing_transactions.append((data.get('description'), data.get('amount'), data.get('date')))
                else:
                    existing_income.append((data.get('description'), data.get('amount'), data.get('date')))

        new_ids = []
        for msg in messages:
            msg_id = msg['id']
            if msg_id in processed_ids or msg_id in existing_google_ids: continue
            
            details = service.users().messages().get(userId='me', id=msg_id).execute()
            internal_date_ms = int(details.get('internalDate', datetime.now().timestamp() * 1000))
            dt = datetime.fromtimestamp(internal_date_ms / 1000.0)
            
            snippet, subject = details.get('snippet', ''), ''
            for h in details.get('payload', {}).get('headers', []):
                if h['name'] == 'Subject': subject = h['value']; break
            
            val = re.search(r'R\$\s*(\d+(?:[\.,]\d+)?)', f"{subject} {snippet}")
            if val:
                amount = float(val.group(1).replace('.', '').replace(',', '.'))
                is_inc = any(w in f"{subject} {snippet}".lower() for w in ['recebido', 'recebeu', 'recebida'])
                description = f"Pix: {subject}"
                iso_date = dt.isoformat()
                record = (description, amount, iso_date)
                
                if is_inc:
                    if record not in existing_income:
                        db.collection('finance_income').add({
                            'description': description, 'amount': amount, 'day': dt.day,
                            'month': dt.month - 1, 'year': dt.year, 'category': 'Renda Extra',
                            'isReceived': True, 'date': iso_date, 'google_message_id': msg_id,
                            'status': 'active'
                        })
                else:
                    if record not in existing_transactions:
                        db.collection('finance_transactions').add({
                            'description': description, 'amount': amount, 'date': iso_date,
                            'sprint': (dt.day // 7) + 1, 'category': 'Alimentação',
                            'google_message_id': msg_id, 'status': 'active'
                        })
                new_ids.append(msg_id)
                log_to_firestore(sync_ref, logs, f"[PIX] {subject} (R$ {amount})")
        
        if new_ids:
            updated_ids = list(set(processed_ids + new_ids))[-200:]
            db.collection('system').document('processed_emails').set({'ids': updated_ids}, merge=True)
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"ERRO PIX: {e}")

@firestore_fn.on_document_updated(document="system/sync")
def on_sync_request(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]]):
    """Trigger disparado quando system/sync é atualizado"""
    if not event.data.after.exists: return
    data = event.data.after.to_dict()
    if data.get('status') != 'requested': return
    
    sync_ref = db.collection('system').document('sync')
    logs = ["Iniciando via Firebase Function Gen 2..."]
    try:
        sync_ref.update({'status': 'processing', 'logs': logs})
        ts, gs = get_tasks_service(), get_gmail_service()
        sync_google_tasks_push(ts, sync_ref, logs)
        sync_google_tasks_pull(ts, sync_ref, logs)
        sync_pix_emails(gs, sync_ref, logs)
        sync_ref.update({'status': 'completed', 'last_success': datetime.now().isoformat(), 'logs': logs})
    except Exception as e:
        logs.append(f"ERRO: {str(e)}")
        sync_ref.update({'status': 'error', 'error_message': str(e), 'logs': logs})
