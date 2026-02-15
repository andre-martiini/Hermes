"""
Firebase Cloud Function para sincronização automática com Google Tasks
Dispara automaticamente quando o documento system/sync é atualizado
"""

import json
import re
from datetime import datetime
from google.cloud import firestore
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import functions_framework

# Configuração do Firestore
db = firestore.Client()

# Escopo para Google Tasks API
SCOPES = ['https://www.googleapis.com/auth/tasks']

def get_tasks_service():
    """
    Cria o serviço do Google Tasks usando as credenciais armazenadas no Firestore
    """
    # Busca as credenciais do Firestore
    creds_doc = db.collection('system').document('google_credentials').get()
    
    if not creds_doc.exists:
        raise Exception("Credenciais do Google não encontradas no Firestore. Execute o setup primeiro.")
    
    creds_data = creds_doc.to_dict()
    
    # Cria as credenciais OAuth2
    creds = Credentials(
        token=creds_data.get('token'),
        refresh_token=creds_data.get('refresh_token'),
        token_uri=creds_data.get('token_uri'),
        client_id=creds_data.get('client_id'),
        client_secret=creds_data.get('client_secret'),
        scopes=SCOPES
    )
    
    return build('tasks', 'v1', credentials=creds)

def log_to_firestore(sync_ref, logs, message, force_update=False):
    """Adiciona log e atualiza o Firestore"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    logs.append(log_entry)
    print(log_entry)
    
    if force_update:
        sync_ref.update({'logs': logs})

def classify_task(title, notes):
    """
    Classifica a tarefa com base em tags no título ou notas.
    Suporta formatos: [TAG] ou Tag: TAG
    """
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

def sync_google_tasks_pull(service, sync_ref, logs):
    """
    Busca tarefas pendentes no Google e sincroniza com Firestore (PULL)
    """
    try:
        # Busca a lista de tarefas
        results = service.tasklists().list().execute()
        tasklists = results.get('items', [])
        tasklist_id = None
        target_name = 'tarefa-gerais'
        
        for item in tasklists:
            clean_title = item['title'].lower().replace(' ', '-').replace('s', '') if 'tarefa' in item['title'].lower() else item['title'].lower()
            if item['title'].lower() == target_name or clean_title == target_name.replace('s', ''):
                tasklist_id = item['id']
                log_to_firestore(sync_ref, logs, f"Iniciando PULL de: {item['title']}", True)
                break
        
        if not tasklist_id:
            log_to_firestore(sync_ref, logs, "ERRO: Lista não encontrada.", True)
            return
        
        # Busca todas as tarefas
        g_tasks = []
        next_page_token = None
        while True:
            g_results = service.tasks().list(
                tasklist=tasklist_id,
                showCompleted=True,
                showHidden=True,
                maxResults=100,
                pageToken=next_page_token
            ).execute()
            
            items = g_results.get('items', [])
            g_tasks.extend(items)
            
            if len(g_tasks) >= 200 or not g_results.get('nextPageToken'):
                break
            next_page_token = g_results.get('nextPageToken')
        
        log_to_firestore(sync_ref, logs, f"Total de {len(g_tasks)} tarefas identificadas no Google. Analisando...", True)
        
        # Carrega tarefas locais
        local_docs = db.collection('tarefas').stream()
        local_tasks = {}
        for t in local_docs:
            d = t.to_dict()
            gid = d.get('google_id')
            if gid:
                local_tasks[gid] = (t.id, d)
            else:
                local_tasks[f"title_{d.get('titulo')}"] = (t.id, d)
        
        # Processa cada tarefa do Google
        for gt in g_tasks:
            g_id = gt['id']
            title = gt.get('title', '(Sem Título)')
            g_updated = gt.get('updated', '')
            due = gt.get('due', None)
            deadline = due.split('T')[0] if due else '-'
            h_status = 'concluído' if gt.get('status') == 'completed' else 'em andamento'
            
            categoria, sistema, contabilizar_meta = classify_task(title, gt.get('notes', ''))
            
            existing_data = local_tasks.get(g_id) or local_tasks.get(f"title_{title}")
            
            if existing_data:
                doc_id, t_old = existing_data
                
                # Se não tem google_id mas o título coincide, vincula
                if not t_old.get('google_id'):
                    db.collection('tarefas').document(doc_id).update({
                        'google_id': g_id,
                        'data_atualizacao': g_updated
                    })
                    log_to_firestore(sync_ref, logs, f"[*] VINCULADA: {title}")
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
                        'titulo': title,
                        'data_limite': deadline,
                        'status': h_status,
                        'data_conclusao': gt.get('completed'),
                        'data_atualizacao': g_updated
                    })
                    log_to_firestore(sync_ref, logs, f"[-] ATUALIZADA: {title}")
            else:
                # Cria nova tarefa
                db.collection('tarefas').add({
                    'titulo': title,
                    'projeto': 'GOOGLE',
                    'data_limite': deadline,
                    'google_id': g_id,
                    'status': h_status,
                    'data_criacao': datetime.now().isoformat(),
                    'data_conclusao': gt.get('completed'),
                    'data_atualizacao': g_updated,
                    'categoria': categoria,
                    'contabilizar_meta': contabilizar_meta
                })
                log_to_firestore(sync_ref, logs, f"[+] IMPORTADA: {title}")
        
        log_to_firestore(sync_ref, logs, "PULL CONCLUÍDO.", True)
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"ERRO PULL: {e}", True)
        raise

def sync_google_tasks_push(service, sync_ref, logs):
    """
    Pega as tarefas do Firestore e atualiza o Google Tasks (PUSH)
    """
    try:
        # Busca a lista de tarefas
        results = service.tasklists().list().execute()
        tasklists = results.get('items', [])
        tasklist_id = None
        target_name = 'tarefa-gerais'
        
        for item in tasklists:
            clean_title = item['title'].lower().replace(' ', '-').replace('s', '') if 'tarefa' in item['title'].lower() else item['title'].lower()
            if item['title'].lower() == target_name or clean_title == target_name.replace('s', ''):
                tasklist_id = item['id']
                log_to_firestore(sync_ref, logs, f"Iniciando PUSH para: {item['title']}", True)
                break
        
        if not tasklist_id:
            log_to_firestore(sync_ref, logs, "ERRO: Lista destino não encontrada.", True)
            return
        
        # Busca tarefas do Google
        g_results = service.tasks().list(
            tasklist=tasklist_id,
            showCompleted=True,
            showHidden=True,
            maxResults=100
        ).execute()
        g_tasks_map = {item['id']: item for item in g_results.get('items', [])}
        
        # Busca tarefas do Firestore
        tasks = db.collection('tarefas').stream()
        
        count = 0
        for doc in tasks:
            t = doc.to_dict()
            g_id = t.get('google_id')
            h_status = t.get('status')
            
            # Remove tarefas excluídas
            if h_status == 'excluído':
                if g_id:
                    try:
                        service.tasks().delete(tasklist=tasklist_id, task=g_id).execute()
                        log_to_firestore(sync_ref, logs, f"[X] REMOVIDA: {t['titulo']}")
                    except:
                        pass
                doc.reference.delete()
                continue
            
            # Prepara dados
            due_date = f"{t['data_limite']}T00:00:00Z" if t.get('data_limite') and t.get('data_limite') != '-' else None
            g_status = 'completed' if t.get('status') == 'concluído' else 'needsAction'
            
            # Cria nova tarefa no Google se não existir
            if not g_id:
                new_task = service.tasks().insert(
                    tasklist=tasklist_id,
                    body={
                        'title': t['titulo'],
                        'notes': t.get('notas', ''),
                        'status': g_status,
                        'due': due_date
                    }
                ).execute()
                doc.reference.update({
                    'google_id': new_task['id'],
                    'data_atualizacao': new_task.get('updated')
                })
                log_to_firestore(sync_ref, logs, f"[+] ENVIADA: {t['titulo']}")
                count += 1
                continue
            
            # Atualiza tarefa existente se necessário
            g_task = g_tasks_map.get(g_id)
            if g_task and t.get('data_atualizacao', '') > g_task.get('updated', ''):
                service.tasks().update(
                    tasklist=tasklist_id,
                    task=g_id,
                    body={
                        'id': g_id,
                        'title': t['titulo'],
                        'notes': t.get('notas', ''),
                        'status': g_status,
                        'due': due_date
                    }
                ).execute()
                log_to_firestore(sync_ref, logs, f"[^] ATUALIZADA NO GOOGLE: {t['titulo']}")
                count += 1
        
        log_to_firestore(sync_ref, logs, f"PUSH FINALIZADO: {count} atualizações.", True)
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"ERRO PUSH: {e}", True)
        raise

@functions_framework.cloud_event
def on_sync_request(cloud_event):
    """
    Cloud Function disparada quando o documento system/sync é modificado
    """
    # Extrai dados do evento
    data = cloud_event.data
    
    # Verifica se é uma atualização (não criação ou deleção)
    if not data.get('value'):
        return
    
    # Pega os dados do documento
    fields = data['value']['fields']
    status = fields.get('status', {}).get('stringValue', '')
    
    # Só processa se o status for 'requested'
    if status != 'requested':
        return
    
    print("Sincronização solicitada via Cloud Function")
    
    # Referência ao documento de sync
    sync_ref = db.collection('system').document('sync')
    
    # Inicializa logs
    logs = ["Iniciando processamento via Cloud Function..."]
    
    try:
        # Atualiza status para processing
        sync_ref.update({
            'status': 'processing',
            'logs': logs
        })
        
        # Obtém serviço do Google Tasks
        service = get_tasks_service()
        
        # Executa PUSH
        sync_google_tasks_push(service, sync_ref, logs)
        
        # Executa PULL
        sync_google_tasks_pull(service, sync_ref, logs)
        
        # Finaliza com sucesso
        sync_ref.update({
            'status': 'completed',
            'last_success': datetime.now().isoformat(),
            'logs': logs
        })
        
        print("Sincronização concluída com sucesso")
        
    except Exception as e:
        print(f"ERRO na sincronização: {e}")
        logs.append(f"ERRO FATAL: {str(e)}")
        sync_ref.update({
            'status': 'error',
            'error_message': str(e),
            'logs': logs
        })
