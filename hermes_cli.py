
import argparse
import json
import re
import os
import sys
import base64
from datetime import datetime, timezone, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import time
import uuid

# Imports para Google APIs
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError

# Escopos para Google APIs
SCOPES = [
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/forms.body'
]

DEBUG_MODE = True # Ativa log detalhado de cada tarefa no terminal do sistema

# Configuração do Firebase
KEY_FILE = 'firebase_service_account_key.json'

def get_units_mapping(db):
    mapping = {
        'CLC': ['licitação', 'pregão', 'irp', 'processo'],
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
        if not creds.has_scopes(SCOPES):
            print("Token existente nao tem todos os escopos necessarios. Iniciando nova autenticacao...")
            os.remove('token.json')
            creds = None
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                print("Token expirado ou revogado. Iniciando nova autenticação...")
                if os.path.exists('token.json'):
                    os.remove('token.json')
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists('credentials.json'):
                print("ERRO: 'credentials.json' não encontrado. Baixe do Google Cloud Console.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            
            print("\n----- ATENÇÃO -----")
            print("Seu navegador deve abrir agora. Se você vir a tela 'ERR_CONNECTION_REFUSED', significa que o Google bloqueou portas dinâmicas.")
            print("Tentando forçar a captura via localhost:8080...")
            print("-------------------\n")
            
            try:
                # Tenta forçar a porta padrão
                creds = flow.run_local_server(port=8080)
            except Exception as e:
                print(f"Erro ao ligar o servidor local ({e}). Usando modo console. Copie a URL abaixo:")
                creds = flow.run_console()

        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def get_tasks_service():
    return build('tasks', 'v1', credentials=get_google_creds())

def get_gmail_service():
    return build('gmail', 'v1', credentials=get_google_creds())

def archive_gmail_message(service, msg_id, log=None, reason="financeiro"):
    try:
        service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'removeLabelIds': ['INBOX']}
        ).execute()
        if log:
            log(f"[GMAIL] E-mail financeiro arquivado ({reason}): {msg_id}")
        return True
    except Exception as e:
        if log:
            log(f"[GMAIL] Aviso: nao foi possivel arquivar {msg_id}: {e}")
        else:
            print(f"[GMAIL] Aviso: nao foi possivel arquivar {msg_id}: {e}")
        return False

def get_calendar_service():
    return build('calendar', 'v3', credentials=get_google_creds())

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

def extract_time_from_notes(notes):
    if not notes: return None, None
    match = re.search(r'\[Horário:\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\]', notes)
    if match:
        return match.group(1), match.group(2)
    return None, None

def update_notes_with_time(notes, start, end):
    if not notes: notes = ""
    pattern = r'\[Horário:\s*\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\]'
    new_block = f"[Horário: {start} - {end}]" if start and end else ""
    
    if re.search(pattern, notes):
        if new_block:
            return re.sub(pattern, new_block, notes)
        else:
            return re.sub(pattern, '', notes).strip()
    else:
        if new_block:
            return f"{notes}\n\n{new_block}".strip()
        else:
            return notes

def normalize_task_title(title):
    if not isinstance(title, str):
        return title

    compact = re.sub(r'\s+', ' ', title).strip()
    if not compact:
        return compact

    small_words = {
        'de', 'da', 'do', 'das', 'dos',
        'e', 'em', 'na', 'no', 'nas', 'nos',
        'a', 'o', 'as', 'os',
        'para', 'por', 'com'
    }

    def normalize_piece(piece, is_first):
        if not piece:
            return piece
        if re.fullmatch(r'[A-Z0-9]{2,5}', piece):
            return piece
        lower = piece.lower()
        if (not is_first) and lower in small_words:
            return lower
        return lower[:1].upper() + lower[1:]

    words = []
    for word_index, word in enumerate(compact.split(' ')):
        parts = re.split(r'([/-])', word)
        normalized_parts = []
        part_index = 0
        for part in parts:
            if part in ('/', '-'):
                normalized_parts.append(part)
                continue
            normalized_parts.append(normalize_piece(part, word_index == 0 and part_index == 0))
            part_index += 1
        words.append(''.join(normalized_parts))

    return ' '.join(words)

def parse_iso_datetime(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def is_iso_after(left_value, right_value):
    left = parse_iso_datetime(left_value)
    right = parse_iso_datetime(right_value)
    if not left:
        return False
    if not right:
        return True
    return left > right

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
            title_raw = gt.get('title', '(Sem Título)')
            title = normalize_task_title(title_raw)
            title_was_normalized = title != title_raw
            g_updated = gt.get('updated', '')
            due = gt.get('due', None)
            deadline = due.split('T')[0] if due else '-'
            h_status = 'concluído' if gt.get('status') == 'completed' else 'em andamento'
            
            # Extração de horários das notas
            g_notes = gt.get('notes', '')
            h_inicio, h_fim = extract_time_from_notes(g_notes)
            
            # Duração padrão de 1h se houver início mas não fim
            if h_inicio and not h_fim:
                try:
                    h, m = map(int, h_inicio.split(':'))
                    h_fim = f"{(h+1)%24:02d}:{m:02d}"
                except: pass

            area_tematica, sistema, contabilizar_meta = classify_task(title, g_notes, dynamic_mapping)
            existing_data = local_tasks.get(g_id) or local_tasks.get(f"title_{title}") or local_tasks.get(f"title_{title_raw}")
            
            if existing_data:
                doc_id, t_old = existing_data
                if not t_old.get('google_id'):
                    applied_updated = datetime.now().isoformat() if title_was_normalized else g_updated
                    db.collection('tarefas').document(doc_id).update({
                        'titulo': title,
                        'google_id': g_id, 
                        'data_atualizacao': applied_updated, 
                        'notas': g_notes,
                        'horario_inicio': h_inicio,
                        'horario_fim': h_fim
                    })
                    log(f"[*] VINCULADA: {title}")
                    continue
                
                h_updated = t_old.get('data_atualizacao', '')
                
                remote_is_newer = is_iso_after(g_updated, h_updated)
                if not remote_is_newer:
                    continue

                deadline_changed = t_old.get('data_limite') != deadline
                
                has_changed = (t_old.get('status') != h_status or 
                               t_old.get('titulo') != title or 
                               deadline_changed or 
                               t_old.get('horario_inicio') != h_inicio or
                               t_old.get('horario_fim') != h_fim)
                
                if has_changed:
                    applied_updated = datetime.now().isoformat() if title_was_normalized else g_updated
                    db.collection('tarefas').document(doc_id).update({
                        'titulo': title, 'data_limite': deadline, 'data_inicio': deadline, 'status': h_status,
                        'data_conclusao': gt.get('completed'), 'data_atualizacao': applied_updated,
                        'notas': g_notes, 'sync_status': 'updated', 
                        'last_sync_date': datetime.now().isoformat(),
                        'horario_inicio': h_inicio,
                        'horario_fim': h_fim
                    })
                    if deadline_changed:
                        log(f"[#] PRAZO SINCRONIZADO: {title} ({deadline})")
                    else:
                        log(f"[-] ATUALIZADA: {title}")
            else:
                applied_updated = datetime.now().isoformat() if title_was_normalized else g_updated
                db.collection('tarefas').add({
                    'titulo': title, 'projeto': 'GOOGLE', 'data_limite': deadline, 'data_inicio': deadline,
                    'google_id': g_id, 'status': h_status, 'data_criacao': datetime.now().isoformat(),
                    'data_conclusao': gt.get('completed'), 'data_atualizacao': applied_updated,
                    'area_tematica': area_tematica, 'contabilizar_meta': contabilizar_meta,
                    'notas': g_notes, 'sync_status': 'new', 'last_sync_date': datetime.now().isoformat(),
                    'horario_inicio': h_inicio, 'horario_fim': h_fim
                })
                log(f"[+] IMPORTADA: {title}")
        cleanup_old_sync_badges(db, log)
        log("PULL CONCLUÍDO.", force_ui=True)
    except Exception as e:
        log(f"ERRO PULL: {e}", force_ui=True)

def sync_google_calendar(db, log_list=None, sync_ref=None):
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
        service = get_calendar_service()
        log("Sincronizando Google Calendar...")

        time_min = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace('+00:00', 'Z')
        time_max = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace('+00:00', 'Z')

        events_result = service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        log(f"Encontrados {len(events)} eventos no Calendar. Sincronizando...")

        count = 0
        for event in events:
            event_id = event['id']
            summary = event.get('summary', '(Sem título)')
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))

            db.collection('google_calendar_events').document(event_id).set({
                'google_id': event_id,
                'titulo': summary,
                'data_inicio': start,
                'data_fim': end,
                'last_sync': datetime.now().isoformat()
            }, merge=True)
            count += 1

        # Cleanup: Remove eventos que não vieram na resposta (excluídos do Google)
        # Mas apenas dentro da janela de tempo consultada
        fetched_ids = {e['id'] for e in events}
        try:
            existing_docs = db.collection('google_calendar_events').stream()
            deleted_count = 0
            for doc in existing_docs:
                d = doc.to_dict()
                e_start = d.get('data_inicio')
                if not e_start: continue
                
                # Verifica se o evento está dentro da janela de sincronização
                if time_min <= e_start <= time_max:
                    if doc.id not in fetched_ids:
                        doc.reference.delete()
                        deleted_count += 1
                        
            if deleted_count > 0:
                log(f"[CAL] {deleted_count} eventos excluídos localmente.", force_ui=True)
        except Exception as cleanup_err:
            log(f"Erro na limpeza do calendário: {cleanup_err}")

        log(f"[CAL] {count} eventos sincronizados.", force_ui=True)
    except Exception as e:
        log(f"ERRO CALENDAR: {e}", force_ui=True)

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

        calendar_service = get_calendar_service()

        # Pega todas as tarefas do Google (com paginação) para o mapa
        g_tasks_map = {}
        next_page_token = None
        while True:
            g_results = service.tasks().list(tasklist=tasklist_id, showCompleted=True, showHidden=True, maxResults=100, pageToken=next_page_token).execute()
            for item in g_results.get('items', []):
                g_tasks_map[item['id']] = item
            next_page_token = g_results.get('nextPageToken')
            if not next_page_token or len(g_tasks_map) >= 500: break

        tasks = db.collection('tarefas').stream()
        count = 0
        for doc in tasks:
            t = doc.to_dict()
            g_id = t.get('google_id')
            h_status = t.get('status')
            raw_title = t.get('titulo') or '(Sem Título)'
            title = normalize_task_title(raw_title)
            local_updated = t.get('data_atualizacao', '')
            if title != raw_title:
                local_updated = datetime.now().isoformat()
                doc.reference.update({'titulo': title, 'data_atualizacao': local_updated})
            
            if h_status == 'excluído':
                if g_id:
                    try: 
                        service.tasks().delete(tasklist=tasklist_id, task=g_id).execute()
                        log(f"[X] REMOVIDA DO GOOGLE: {title}")
                    except HttpError as e:
                        if e.resp.status == 404:
                            log(f"[!] Task {g_id} já não existia no Google.")
                        else:
                            log(f"[!] Erro ao deletar no Google: {e}")
                doc.reference.delete()
                continue

            sync_to_calendar = bool(t.get('horario_inicio') and t.get('data_limite') and t.get('data_limite') != '-')

            due_date = f"{t['data_limite']}T00:00:00Z" if t.get('data_limite') and t.get('data_limite') != '-' else None

            g_status = 'completed' if t.get('status') == 'concluído' else 'needsAction'
            
            # Atualiza as notas com o horário para garantir a sincronia de volta
            h_inicio, h_fim = t.get('horario_inicio'), t.get('horario_fim')
            if h_inicio and not h_fim:
                try:
                    h, m = map(int, h_inicio.split(':'))
                    h_fim = f"{(h+1)%24:02d}:{m:02d}"
                except: pass
            
            updated_notes = update_notes_with_time(t.get('notas', ''), h_inicio, h_fim)

            if not g_id:
                body = {'title': title, 'notes': updated_notes, 'status': g_status, 'due': due_date}
                new_task = service.tasks().insert(tasklist=tasklist_id, body=body).execute()
                doc.reference.update({
                    'google_id': new_task['id'], 
                    'data_atualizacao': new_task.get('updated'), 
                    'notas': updated_notes, 
                    'horario_fim': h_fim if not t.get('horario_fim') else t.get('horario_fim')
                })
                log(f"[+] ENVIADA: {title}"); count += 1
                continue
            g_task = g_tasks_map.get(g_id)
            if g_task and local_updated > g_task.get('updated', ''):
                body = {'id': g_id, 'title': title, 'notes': updated_notes, 'status': g_status, 'due': due_date}
                try:
                    service.tasks().update(tasklist=tasklist_id, task=g_id, body=body).execute()
                    log(f"[^] ATUALIZADA NO GOOGLE: {title}"); count += 1
                    if updated_notes != t.get('notas', ''):
                        doc.reference.update({'notas': updated_notes})
                except HttpError as e:
                    if e.resp.status == 404:
                        log(f"[!] Task {g_id} não encontrada no Google - Limpando ID para re-envio.")
                        doc.reference.update({'google_id': None})
                    else:
                        raise e
            
            # --- PARTE 2: Sincronia Google Calendar (Se possuir horário) ---
            cal_id = t.get('google_calendar_id')
            if sync_to_calendar and g_status == 'needsAction':
                try:
                    start_dt = f"{t.get('data_limite')}T{h_inicio}:00-03:00"
                    end_dt = f"{t.get('data_limite')}T{h_fim}:00-03:00"
                    event_body = {
                        'summary': f"Tarefa: {title}",
                        'description': updated_notes,
                        'start': {'dateTime': start_dt, 'timeZone': 'America/Sao_Paulo'},
                        'end': {'dateTime': end_dt, 'timeZone': 'America/Sao_Paulo'}
                    }
                    if not cal_id:
                        new_event = calendar_service.events().insert(calendarId='primary', body=event_body).execute()
                        doc.reference.update({'google_calendar_id': new_event['id']})
                        log(f"[+] ALOCADA CALENDAR: {title}")
                    else:
                        try:
                            calendar_service.events().update(calendarId='primary', eventId=cal_id, body=event_body).execute()
                        except HttpError as cal_err:
                            if cal_err.resp.status == 404:
                                new_event = calendar_service.events().insert(calendarId='primary', body=event_body).execute()
                                doc.reference.update({'google_calendar_id': new_event['id']})
                except Exception as ce:
                    pass
            elif (not sync_to_calendar or g_status == 'completed') and cal_id:
                 try:
                     calendar_service.events().delete(calendarId='primary', eventId=cal_id).execute()
                 except HttpError as ce: pass
                 doc.reference.update({'google_calendar_id': None})

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
            if msg_id in processed_ids or msg_id in existing_google_ids:
                archive_gmail_message(service, msg_id, log, "pix-ja-processado")
                continue
            
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
                        archive_gmail_message(service, msg_id, log, "pix-duplicado")
                        continue
                    db.collection('finance_income').add({
                        'description': description, 'amount': amount, 'day': dt.day,
                        'month': dt.month - 1, 'year': dt.year, 'status': 'active',
                        'data_recebimento': iso_date, 'google_message_id': msg_id
                    })
                else:
                    if record in existing_transactions:
                        new_processed_ids.append(msg_id)
                        archive_gmail_message(service, msg_id, log, "pix-duplicado")
                        continue
                    db.collection('finance_transactions').add({
                        'description': description, 'amount': amount, 'date': iso_date,
                        'status': 'active', 'google_message_id': msg_id
                    })
                    
                new_processed_ids.append(msg_id)
                log(f"[PIX] Processado: {description} (R$ {amount:.2f})")
                archive_gmail_message(service, msg_id, log, "pix-lancado")
        
        if new_processed_ids:
            updated_ids = list(set(processed_ids + new_processed_ids))
            db.collection('system').document('processed_emails').set({'ids': updated_ids}, merge=True)
    except Exception as e:
        log(f"ERRO PIX: {e}")

def sync_google_drive_acervo(db, logs=None, sync_ref=None):
    def log(msg):
        if logs is not None: logs.append(msg)
        if sync_ref: sync_ref.update({'logs': logs})
        print(msg)

    log("Verificando Pasta de Deságue (Acervo Global)...")
    try:
        # 1. Configuração
        settings_doc = db.collection("system").document("settings").get()
        folder_id = settings_doc.to_dict().get("drop_folder_id", "") if settings_doc.exists else ""
        if not folder_id:
            log("Aviso: drop_folder_id não configurado.")
            return

        # 2. Drive Service
        service = build("drive", "v3", credentials=get_google_creds())
        
        # 3. Listagem
        all_files = []
        page_token = None
        while True:
            resp = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name, mimeType)",
                pageSize=100
            ).execute()
            all_files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token: break

        if not all_files:
            log("Pasta de Deságue vazia.")
            return

        # 4. Filtro de já indexados
        # ── Map de arquivos conhecidos ─────────────
        acervo_map = {}
        for doc in db.collection("acervo_global").stream():
            d = doc.to_dict() or {}
            fid_stored = d.get("drive_file_id")
            if fid_stored:
                acervo_map[fid_stored] = d.get("status_indexacao", "pendente")

        # 5. Processamento
        count = 0
        for f in all_files:
            fid = f.get('id')
            if not fid or fid in acervo_map: continue
            
            acervo_id = str(uuid.uuid4())[:16]
            url = f"https://drive.google.com/file/d/{fid}/view"
            db.collection("acervo_global").document(acervo_id).set({
                "nome": f.get('name'),
                "url": url,
                "tipo_mime": f.get('mimeType'),
                "drive_file_id": fid,
                "status_indexacao": "pendente",
                "indexed_at": firestore.SERVER_TIMESTAMP,
            })
            log(f"[Acervo] Novo documento detectado: {f.get('name')}")
            count += 1
        
        if count > 0:
            log(f"Sincronização do acervo concluída. {count} novos arquivos pendentes para IA.")
        else:
            log("Nenhum arquivo novo no acervo.")
            
    except Exception as e:
        log(f"Erro no acervo: {e}")


def classify_task(title, notes, mapping=None):
    if mapping is None: mapping = {'CLC': [], 'ASSISTÊNCIA': []}
    title_upper, notes_upper = title.upper(), notes.upper()
    full_text = f"{title_upper} {notes_upper}"
    area_tematica, contabilizar_meta = 'NÃO CLASSIFICADA', False
    
    for area, keywords in mapping.items():
        if any(kw.upper() in title_upper for kw in keywords):
            area_tematica = area
            if area in ['CLC', 'ASSISTÊNCIA']: contabilizar_meta = True
            return area_tematica, None, contabilizar_meta

    tags = re.findall(r'\[(.*?)\]|TAG:\s*([\w\-]+)', full_text)
    tags = [t[0].upper() if t[0] else t[1].upper() for t in tags]
    if any(tag in ['CLC', 'LICITACAO'] for tag in tags): area_tematica, contabilizar_meta = 'CLC', True
    elif any(tag in ['ASSISTENCIA', 'ESTUDANTIL'] for tag in tags): area_tematica, contabilizar_meta = 'ASSISTÊNCIA', True
    elif 'GERAL' in tags: area_tematica = 'GERAL'
    return area_tematica, None, contabilizar_meta

def get_embedding_cli(text, api_key):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text[:8000],
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768
        )
    )
    return response.embeddings[0].values

def sync_rag_knowledge_bases(db, log_list=None, sync_ref=None):
    last_ui_update = [0]
    def log(msg, force_ui=False):
        print(msg)
        if log_list is not None:
            log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            now_ts = time.time()
            if sync_ref and (force_ui or now_ts - last_ui_update[0] > 1.2):
                try: sync_ref.update({'logs': log_list}); last_ui_update[0] = now_ts
                except: pass

    log("[RAG] Sincronizando itens de conhecimento pendentes...", force_ui=True)
    try:
        keys_doc = db.collection('system').document('api_keys').get()
        GEMINI_API_KEY = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        if not GEMINI_API_KEY:
            log("[RAG][!] Sincronização falhou: Chave Gemini não configurada.")
            return

        docs = db.collection('conhecimento').stream()
        pending_items = []
        for doc in docs:
            data = doc.to_dict() or {}
            if not data.get('embedding') or (data.get('tipo_arquivo') == 'link' and not data.get('texto_bruto')):
                pending_items.append((doc.id, data, doc.reference))

        if not pending_items:
            log("[RAG] Nenhum item pendente de vetorização ou sincronização.", force_ui=True)
            return

        log(f"[RAG] Encontrados {len(pending_items)} itens para processamento.", force_ui=True)
        
        import requests
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        drive_service = None
        
        success_count = 0
        for doc_id, data, doc_ref in pending_items:
            titulo = data.get('titulo') or 'Sem título'
            tipo = data.get('tipo_arquivo', '').lower()
            url = data.get('url_drive')
            texto_bruto = data.get('texto_bruto', '')

            try:
                # 1. Extração de texto para links pendentes
                if tipo == 'link' and url and not texto_bruto:
                    log(f"[RAG] Extraindo texto do link: {titulo} ({url})...")
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    resp = requests.get(url, headers=headers, timeout=15)
                    if resp.status_code == 200:
                        html_truncated = resp.text[:120000]
                        prompt = "Extraia todo o texto relevante e útil deste HTML para indexação em um RAG. Ignore tags, cabeçalhos de navegação do site, links de rodapé e propagandas."
                        response = client.models.generate_content(
                            model="gemini-3.5-flash",
                            contents=[prompt, html_truncated]
                        )
                        if response.text:
                            texto_bruto = response.text.strip()
                            doc_ref.update({
                                'texto_bruto': texto_bruto,
                                'texto_extraido_por': 'sync_runner_link_scraper'
                            })
                            log(f"[RAG] Texto extraído com sucesso para o link: {titulo}")
                    else:
                        log(f"[RAG][!] Falha ao baixar link {url} (Status: {resp.status_code})")
                
                # 2. Indexação de arquivos do Drive (se não tiver texto bruto)
                if tipo != 'link' and not texto_bruto and url:
                    log(f"[RAG] Indexando arquivo do Drive pendente: {titulo} ({doc_id})...")
                    drive_file_id = None
                    if 'drive.google.com' in url:
                        match = re.search(r'[-\w]{25,}', url)
                        if match:
                            drive_file_id = match.group(0)
                    else:
                        drive_file_id = url

                    if drive_file_id:
                        if not drive_service:
                            drive_service = build("drive", "v3", credentials=get_google_creds())
                        
                        request_media = drive_service.files().get_media(fileId=drive_file_id)
                        content = request_media.execute()
                        
                        mime_type = "application/pdf" if titulo.lower().endswith('.pdf') else "text/plain"
                        prompt = "Extraia todo o texto relevante deste documento para indexação. Se for HTML, ignore tags. Se for PDF, faça OCR se necessário."
                        response = client.models.generate_content(
                            model="gemini-3.5-flash",
                            contents=[prompt, {"mime_type": mime_type, "data": content}]
                        )
                        if response.text:
                            texto_bruto = response.text.strip()
                            doc_ref.update({
                                'texto_bruto': texto_bruto,
                                'texto_extraido_por': 'sync_runner_file_indexer'
                            })
                            log(f"[RAG] Texto extraído com sucesso para o arquivo: {titulo}")
                    else:
                        log(f"[RAG][!] Não foi possível identificar ID do Drive da URL: {url}")
                
                # 3. Geração de Embedding
                if texto_bruto:
                    latest_data = doc_ref.get().to_dict() or {}
                    if not latest_data.get('embedding'):
                        log(f"[RAG] Gerando embedding para: {titulo}...")
                        embedding_vec = get_embedding_cli(texto_bruto, GEMINI_API_KEY)
                        doc_ref.update({'embedding': embedding_vec})
                        log(f"[RAG][+] Sincronizado e vetorizado: {titulo}", force_ui=True)
                        success_count += 1
            except Exception as item_err:
                log(f"[RAG][!] Erro ao processar item {titulo} ({doc_id}): {item_err}")
                
        log(f"[RAG] Sincronização de conhecimento concluída. {success_count} itens processados.", force_ui=True)
    except Exception as e:
        log(f"[RAG][!] Erro na sincronização de conhecimento: {e}", force_ui=True)

def watch_commands(db):
    print("MÓDULO DE SINCRONIZAÇÃO AUTOMÁTICA INICIADO")
    get_google_creds()  # força autenticação OAuth antes de entrar no loop
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
                sync_google_calendar(db, log_entries, sync_doc_ref)
                sync_pix_emails(db, log_entries, sync_doc_ref)
                sync_google_drive_acervo(db, log_entries, sync_doc_ref)
                sync_rag_knowledge_bases(db, log_entries, sync_doc_ref)
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
    subparsers.add_parser('sync-cal')
    subparsers.add_parser('sync-acervo')
    args = parser.parse_args()
    if not args.command: parser.print_help(); return
    db = init_db()
    if args.command == 'sync-tasks': sync_google_tasks(db)
    elif args.command == 'watch': watch_commands(db)
    elif args.command == 'sync-pix': sync_pix_emails(db)
    elif args.command == 'sync-cal': sync_google_calendar(db)
    elif args.command == 'sync-acervo': sync_google_drive_acervo(db)

if __name__ == '__main__': main()
