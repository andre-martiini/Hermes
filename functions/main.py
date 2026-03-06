

from firebase_functions import firestore_fn, scheduler_fn, options, https_fn, pubsub_fn

from firebase_admin import initialize_app, firestore, messaging
import json
import base64
import google.generativeai as genai
from datetime import datetime, timedelta, timezone
import time
import re
import io
import uuid


# Inicializa o Firebase Admin apenas uma vez no escopo global

initialize_app()

DEFAULT_GOOGLE_CALENDAR_ID = 'cf4953b9512ee2e85a7e064f9d5ce4eaf6e3634564c91e5c7ee2bb01fd46782a@group.calendar.google.com'



def get_db():

    """Retorna a instância do Firestore de forma lazy"""

    return firestore.client()



def get_google_creds():

    """Busca as credenciais OAuth2 do Firestore"""

    from google.oauth2.credentials import Credentials

    db = get_db()

    creds_doc = db.collection('system').document('google_credentials').get()

    if not creds_doc.exists:

        raise Exception("Credenciais não encontradas no Firestore.")

    

    creds_data = creds_doc.to_dict()

    SCOPES = [

        'https://www.googleapis.com/auth/tasks',

        'https://www.googleapis.com/auth/gmail.readonly',

        'https://www.googleapis.com/auth/calendar',  # Modificado para leitura e escrita na nova regra

        'https://www.googleapis.com/auth/drive'

    ]

    return Credentials(

        token=creds_data.get('token'),

        refresh_token=creds_data.get('refresh_token'),

        token_uri=creds_data.get('token_uri'),

        client_id=creds_data.get('client_id'),

        client_secret=creds_data.get('client_secret'),

        scopes=SCOPES

    )



def get_tasks_service():

    from googleapiclient.discovery import build

    return build('tasks', 'v1', credentials=get_google_creds())



def get_gmail_service():

    from googleapiclient.discovery import build

    return build('gmail', 'v1', credentials=get_google_creds())



def get_calendar_service():

    from googleapiclient.discovery import build

    return build('calendar', 'v3', credentials=get_google_creds())



def get_drive_service():

    from googleapiclient.discovery import build

    return build('drive', 'v3', credentials=get_google_creds())


def get_target_calendar_id(db=None):

    db = db or get_db()

    try:

        cfg_doc = db.collection('system').document('config').get()

        if cfg_doc.exists:

            cfg = cfg_doc.to_dict() or {}

            calendar_id = (
                cfg.get('googleCalendarId')
                or cfg.get('google_calendar_id')
                or cfg.get('calendarId')
            )

            if isinstance(calendar_id, str) and calendar_id.strip():

                return calendar_id.strip()

    except Exception:

        pass

    return DEFAULT_GOOGLE_CALENDAR_ID


def get_sync_calendar_ids(db=None):

    target_calendar_id = get_target_calendar_id(db)
    calendar_ids = ['primary']

    if target_calendar_id and target_calendar_id != 'primary':
        calendar_ids.append(target_calendar_id)

    return calendar_ids



def emit_notification_backend(title, message, n_type='info', link=None):

    from datetime import datetime

    import uuid

    db = get_db()

    notif_id = str(uuid.uuid4())[:9]

    db.collection('notificacoes').document(notif_id).set({

        'id': notif_id,

        'title': title,

        'message': message,

        'type': n_type,

        'timestamp': datetime.now().isoformat(),

        'isRead': False,

        'link': link,

        'sent_to_push': False

    })



def log_to_firestore(sync_ref, logs, message, force_update=False):

    from datetime import datetime

    timestamp = datetime.now().strftime('%H:%M:%S')

    log_entry = f"[{timestamp}] {message}"

    logs.append(log_entry)

    print(log_entry)

    if force_update:

        sync_ref.update({'logs': logs})



    if "ERRO" in message.upper():

        emit_notification_backend("Erro de Sincronização", message, 'error')

    elif "[PIX]" in message.upper():

        emit_notification_backend("Novo Pix Recebido", message, 'success', 'financeiro')



def classify_task(title, notes):

    import re

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



    # Se não classificou por tag, tenta por palavra-chave no texto

    if categoria == 'NÃO CLASSIFICADA':

        clc_keywords = ['LICITAÇÃO', 'LICITACAO', 'PREGÃO', 'PREGAO', 'CONTRATO', 'DISPENSA', 'INEXIGIBILIDADE', 'COMPRA', 'AQUISIÇÃO', 'AQUISICAO', 'PROCESSO']

        assist_keywords = ['ASSISTÊNCIA', 'ASSISTENCIA', 'ESTUDANTIL', 'ALUNO', 'BOLSA', 'AUXÍLIO', 'AUXILIO', 'PERMANÊNCIA', 'PERMANENCIA']



        if any(kw in text for kw in clc_keywords):

            categoria, contabilizar_meta = 'CLC', True

        elif any(kw in text for kw in assist_keywords):

            categoria, contabilizar_meta = 'ASSISTÊNCIA', True



    return categoria, None, contabilizar_meta



def extract_time_from_notes(notes):

    import re

    if not notes: return None, None

    match = re.search(r'\[Horário:\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\]', notes)

    if match:

        return match.group(1), match.group(2)

    return None, None



def update_notes_with_time(notes, start, end):

    import re

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

    import re

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

    from datetime import datetime

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    # Google APIs frequentemente retornam UTC com sufixo "Z"
    if text.endswith('Z'):
        text = f"{text[:-1]}+00:00"

    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def is_remote_calendar_newer(remote_updated, local_updated):

    remote_dt = parse_iso_datetime(remote_updated)
    local_dt = parse_iso_datetime(local_updated)

    if remote_dt and local_dt:
        return remote_dt > local_dt
    if remote_dt and not local_dt:
        return True
    return False


def extract_schedule_from_calendar_event(event, tz_name='America/Sao_Paulo'):

    from datetime import timedelta
    from zoneinfo import ZoneInfo

    start_info = event.get('start', {}) or {}
    end_info = event.get('end', {}) or {}

    start_dt = parse_iso_datetime(start_info.get('dateTime'))
    end_dt = parse_iso_datetime(end_info.get('dateTime'))

    if start_dt:
        tz = ZoneInfo(tz_name)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=tz)
        start_local = start_dt.astimezone(tz)

        if end_dt:
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=tz)
            end_local = end_dt.astimezone(tz)
        else:
            end_local = start_local + timedelta(hours=1)

        return {
            'data_inicio': start_local.date().isoformat(),
            'data_limite': start_local.date().isoformat(),
            'horario_inicio': start_local.strftime('%H:%M'),
            'horario_fim': end_local.strftime('%H:%M')
        }

    # Eventos "dia inteiro" (sem horário) - mantém data e limpa horários
    start_date = start_info.get('date')
    if isinstance(start_date, str) and start_date.strip():
        single_date = start_date.strip()
        return {
            'data_inicio': single_date,
            'data_limite': single_date,
            'horario_inicio': None,
            'horario_fim': None
        }

    return None


def sync_google_tasks_pull(service, sync_ref, logs):

    from datetime import datetime

    db = get_db()

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

            g_id = gt['id']
            title_raw = gt.get('title', '(Sem Título)')
            title = normalize_task_title(title_raw)
            title_was_normalized = title != title_raw

            g_updated = gt.get('updated', '')

            status = 'concluído' if gt.get('status') == 'completed' else 'em andamento'

            g_due = gt.get('due', '').split('T')[0] if gt.get('due') else None

            

            # Extração de horários das notas

            g_notes = gt.get('notes', '')

            h_inicio, h_fim = extract_time_from_notes(g_notes)

            

            # Duração padrão de 1h se houver início mas não fim

            if h_inicio and not h_fim:

                try:

                    h, m = map(int, h_inicio.split(':'))

                    h_fim = f"{(h+1)%24:02d}:{m:02d}"

                except: pass



            if g_id in local_tasks:

                doc_id, t_old = local_tasks[g_id]

                if t_old.get('data_atualizacao', '') < g_updated:

                    applied_updated = datetime.now().isoformat() if title_was_normalized else g_updated

                    update_data = {

                        'titulo': title, 'status': status, 'data_atualizacao': applied_updated,

                        'data_conclusao': gt.get('completed'), 'notas': g_notes,

                        'horario_inicio': h_inicio, 'horario_fim': h_fim

                    }

                    if g_due: update_data['data_limite'] = g_due

                    db.collection('tarefas').document(doc_id).update(update_data)

                    log_to_firestore(sync_ref, logs, f"[-] ATUALIZADA: {title}")

            else:

                cat, sys, meta = classify_task(title, g_notes)

                db.collection('tarefas').add({

                    'titulo': title, 'projeto': 'GOOGLE', 'google_id': g_id, 'status': status,

                    'data_criacao': datetime.now().isoformat(), 'data_atualizacao': datetime.now().isoformat() if title_was_normalized else g_updated,

                    'categoria': cat, 'contabilizar_meta': meta, 'notas': g_notes,

                    'data_limite': g_due if g_due else '-',

                    'horario_inicio': h_inicio, 'horario_fim': h_fim

                })

                log_to_firestore(sync_ref, logs, f"[+] IMPORTADA: {title}")

    except Exception as e:

        log_to_firestore(sync_ref, logs, f"ERRO PULL: {e}")



from googleapiclient.errors import HttpError



def sync_google_tasks_push(service, calendar_service, sync_ref, logs):

    from datetime import datetime

    db = get_db()
    calendar_id = get_target_calendar_id(db)

    try:

        results = service.tasklists().list().execute()

        tasklist_id = next((item['id'] for item in results.get('items', []) if 'tarefa' in item['title'].lower()), None)



        if not tasklist_id: 
            # Verifica se há list default
            default_list = service.tasklists().get(tasklist='@default').execute()
            tasklist_id = default_list.get('id')
            if not tasklist_id: return

        

        # Pega todas as tarefas do Google (com paginação) para o mapa

        g_tasks_map = {}

        next_page_token = None

        while True:

            g_results = service.tasks().list(tasklist=tasklist_id, showCompleted=True, showHidden=True, maxResults=100, pageToken=next_page_token).execute()

            for item in g_results.get('items', []):

                g_tasks_map[item['id']] = item

            next_page_token = g_results.get('nextPageToken')

            if not next_page_token or len(g_tasks_map) >= 500: break

        

        for doc in db.collection('tarefas').stream():

            t = doc.to_dict()

            cat = t.get('categoria', '')

            if cat == 'SISTEMAS': continue



            g_id = t.get('google_id')
            raw_title = t.get('titulo') or '(Sem Título)'
            title = normalize_task_title(raw_title)
            local_updated = t.get('data_atualizacao', '')
            if title != raw_title:
                local_updated = datetime.now().isoformat()
                doc.reference.update({'titulo': title, 'data_atualizacao': local_updated})

            if t.get('status') == 'excluído':

                if g_id:

                    try: 

                        service.tasks().delete(tasklist=tasklist_id, task=g_id).execute()

                        log_to_firestore(sync_ref, logs, f"[X] REMOVIDA DO GOOGLE: {title}")

                    except HttpError as e:

                        if e.resp.status == 404:

                            log_to_firestore(sync_ref, logs, f"[!] Task {g_id} já não existia no Google.")

                doc.reference.delete()

                continue

            

            g_status = 'completed' if t.get('status') == 'concluído' else 'needsAction'
            
            # Decisão: se houver horario_inicio, enviaremos pro CALENDAR como EVENTO também!
            sync_to_calendar = bool(t.get('horario_inicio') and t.get('data_limite') and t.get('data_limite') != '-')

            if t.get('data_limite') and t.get('data_limite') != '-':
                # Pro Tasks, precisa ser 00:00:00.000Z por limitacao da API.
                g_due = f"{t.get('data_limite')}T00:00:00.000Z"
            else:
                g_due = None

            # Atualiza as notas com o horário para garantir a sincronia

            h_inicio, h_fim = t.get('horario_inicio'), t.get('horario_fim')

            # Se não houver fim mas houver início, assume-se 1h de duração

            if h_inicio and not h_fim:

                try:

                    h, m = map(int, h_inicio.split(':'))

                    h_fim = f"{(h+1)%24:02d}:{m:02d}"

                except: pass

            

            updated_notes = update_notes_with_time(t.get('notas', ''), h_inicio, h_fim)

            # --- PARTE 1: Sincronia Padrão do Google Tasks (sempre) ---
            if not g_id:
                body = {'title': title, 'notes': updated_notes, 'status': g_status}
                if g_due: body['due'] = g_due
                new_task = service.tasks().insert(tasklist=tasklist_id, body=body).execute()
                doc.reference.update({'google_id': new_task['id'], 'data_atualizacao': new_task.get('updated'), 'notas': updated_notes, 'horario_fim': h_fim if not t.get('horario_fim') else t.get('horario_fim')})
                log_to_firestore(sync_ref, logs, f"[+] ENVIADA TASKS: {title}")
                g_id = new_task['id'] # Para usar no Calendar se precisar
            elif g_id in g_tasks_map and local_updated > g_tasks_map[g_id].get('updated', ''):
                body = {'id': g_id, 'title': title, 'notes': updated_notes, 'status': g_status}
                if g_due: body['due'] = g_due
                try:
                    service.tasks().update(tasklist=tasklist_id, task=g_id, body=body).execute()
                    log_to_firestore(sync_ref, logs, f"[^] ATUALIZADA NO TASKS: {title}")
                    if updated_notes != t.get('notas', ''):
                        doc.reference.update({'notas': updated_notes})
                except HttpError as e:
                    if e.resp.status == 404:
                        doc.reference.update({'google_id': None})
            
            # --- PARTE 2: Sincronia Google Calendar (Se possuir horário) ---
            cal_id = t.get('google_calendar_id')
            if sync_to_calendar and g_status == 'needsAction': # Só agenda eventos não concluídos
                # Prepara o Evento
                from datetime import datetime, timezone
                try:
                    # Converte pra ISO 8601 string para API (Timezone default da máquina rodando)
                    start_dt = f"{t.get('data_limite')}T{h_inicio}:00-03:00"
                    end_dt = f"{t.get('data_limite')}T{h_fim}:00-03:00"
                    
                    event_body = {
                        'summary': f"Tarefa: {title}",
                        'description': updated_notes,
                        'start': {'dateTime': start_dt, 'timeZone': 'America/Sao_Paulo'},
                        'end': {'dateTime': end_dt, 'timeZone': 'America/Sao_Paulo'}
                    }
                    
                    if not cal_id:
                        # Cria novo
                        new_event = calendar_service.events().insert(calendarId=calendar_id, body=event_body).execute()
                        doc.reference.update({'google_calendar_id': new_event['id']})
                        log_to_firestore(sync_ref, logs, f"[+] ALOCADA CALENDAR: {title}")
                    else:
                        # Atualiza
                        try:
                            calendar_service.events().update(calendarId=calendar_id, eventId=cal_id, body=event_body).execute()
                        except HttpError as cal_err:
                            if cal_err.resp.status == 404:
                                new_event = calendar_service.events().insert(calendarId=calendar_id, body=event_body).execute()
                                doc.reference.update({'google_calendar_id': new_event['id']})
                except Exception as ce:
                    log_to_firestore(sync_ref, logs, f"[CAL][!] Falha ao sincronizar evento da tarefa '{title}': {ce}")
            elif (not sync_to_calendar or g_status == 'completed') and cal_id:
                 # Tem ID no cal, mas perdeu horario ou foi completada - Remove do Calendar
                 try:
                     calendar_service.events().delete(calendarId=calendar_id, eventId=cal_id).execute()
                 except HttpError as ce: pass
                 doc.reference.update({'google_calendar_id': None})
                 


    except Exception as e:

        log_to_firestore(sync_ref, logs, f"ERRO PUSH: {e}")



def sync_google_calendar(service, sync_ref, logs):

    from datetime import datetime, timedelta, timezone

    db = get_db()
    calendar_ids = get_sync_calendar_ids(db)

    try:

        log_to_firestore(sync_ref, logs, "Sincronizando Google Calendar...", True)

        time_min = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace('+00:00', 'Z')

        time_max = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace('+00:00', 'Z')

        count = 0

        seen_ids = set()

        linked_tasks_by_event_id = {}
        for task_doc in db.collection('tarefas').stream():
            task_data = task_doc.to_dict() or {}
            linked_event_id = task_data.get('google_calendar_id')
            if isinstance(linked_event_id, str) and linked_event_id.strip():
                linked_tasks_by_event_id.setdefault(linked_event_id.strip(), []).append((task_doc.reference, task_data))

        for calendar_id in calendar_ids:

            try:

                events_result = service.events().list(

                    calendarId=calendar_id, timeMin=time_min, timeMax=time_max,

                    singleEvents=True, orderBy='startTime'

                ).execute()

                events = events_result.get('items', [])

            except Exception as cal_err:

                log_to_firestore(sync_ref, logs, f"[CAL][!] Falha ao listar agenda '{calendar_id}': {cal_err}")

                continue

            for event in events:

                event_id = event['id']

                doc_id = f"{calendar_id}__{event_id}"

                seen_ids.add(doc_id)

                summary = event.get('summary', '(Sem titulo)')

                start = event['start'].get('dateTime', event['start'].get('date'))

                end = event['end'].get('dateTime', event['end'].get('date'))

                db.collection('google_calendar_events').document(doc_id).set({

                    'google_id': event_id,

                    'calendar_id': calendar_id,

                    'titulo': summary,

                    'data_inicio': start,

                    'data_fim': end,

                    'last_sync': datetime.now().isoformat()

                }, merge=True)

                count += 1

                # Sincronia inversa: evento do Calendar (criado pelo Hermes) atualiza data/horário da tarefa
                linked_tasks = linked_tasks_by_event_id.get(event_id, [])
                if not linked_tasks:
                    continue

                schedule = extract_schedule_from_calendar_event(event)
                if not schedule:
                    continue

                event_updated = event.get('updated', '')
                for task_ref, task_data in linked_tasks:
                    local_updated = task_data.get('data_atualizacao', '')
                    if not is_remote_calendar_newer(event_updated, local_updated):
                        continue

                    local_date = task_data.get('data_limite') or task_data.get('data_inicio')
                    local_start = task_data.get('horario_inicio')
                    local_end = task_data.get('horario_fim')
                    has_schedule_change = (
                        local_date != schedule.get('data_limite')
                        or local_start != schedule.get('horario_inicio')
                        or local_end != schedule.get('horario_fim')
                    )

                    if not has_schedule_change:
                        continue

                    updated_notes = update_notes_with_time(
                        task_data.get('notas', ''),
                        schedule.get('horario_inicio'),
                        schedule.get('horario_fim')
                    )

                    task_updates = {
                        **schedule,
                        'notas': updated_notes,
                        # Usa "agora" para garantir que o push subsequente preserve esse ajuste no Tasks/Calendar
                        'data_atualizacao': datetime.now().isoformat()
                    }
                    task_ref.update(task_updates)
                    task_data.update(task_updates)
                    log_to_firestore(sync_ref, logs, f"[CAL->HERMES] Horário atualizado pela agenda: {task_data.get('titulo', '(Sem titulo)')}")

        # Limpeza de eventos deletados no Google Calendar (somente janela sincronizada)

        docs = db.collection('google_calendar_events')\
            .where('data_inicio', '>=', time_min)\
            .where('data_inicio', '<=', time_max)\
            .stream()

        deleted_count = 0

        for doc in docs:

            if doc.id not in seen_ids:

                doc.reference.delete()

                deleted_count += 1

        log_to_firestore(sync_ref, logs, f"[CAL] {count} eventos sincronizados em {len(calendar_ids)} agenda(s). {deleted_count} removidos.")

    except Exception as e:

        log_to_firestore(sync_ref, logs, f"ERRO CAL: {e}")

def sync_pix_emails(service, sync_ref, logs):

    """

    Busca emails de Pix e registra no Financeiro (Versão Cloud Function)

    """

    import re

    import time

    from datetime import datetime, timezone

    db = get_db()

    

    try:

        log_to_firestore(sync_ref, logs, "Buscando emails de Pix a partir de 01/02/2026...")

        # Query: Assuntos de Pix + Data limite

        query = 'after:2026/02/01 subject:(Pix recebido OR Pix realizado OR "Pix enviado" OR "transferência Pix")'

        

        results = service.users().messages().list(userId='me', q=query, maxResults=50).execute()

        messages = results.get('messages', [])

        

        if not messages:

            log_to_firestore(sync_ref, logs, "Nenhum Pix encontrado para os critérios de busca.")

            return

        

        log_to_firestore(sync_ref, logs, f"Encontrados {len(messages)} e-mails potenciais de Pix. Analisando...")



        # Cache de transações existentes para evitar duplicatas (Bloqueio de duplicidade financeira)

        # Cada item: {'amount': float, 'date': datetime, 'pix_id': str, 'description': str}

        existing_transactions = []

        existing_income = []

        existing_google_ids = set()



        def parse_iso_date(date_str):

            if not date_str: return None

            try: return datetime.fromisoformat(date_str.replace('Z', '+00:00'))

            except: return None



        for t in db.collection('finance_transactions').stream():

            data = t.to_dict()

            existing_transactions.append({

                'description': data.get('description'),

                'amount': data.get('amount'),

                'date': parse_iso_date(data.get('date')),

                'pix_id': data.get('pix_id')

            })

            if data.get('google_message_id'): existing_google_ids.add(data['google_message_id'])



        for t in db.collection('finance_income').stream():

            data = t.to_dict()

            existing_income.append({

                'description': data.get('description'),

                'amount': data.get('amount'),

                'date': parse_iso_date(data.get('date')),

                'pix_id': data.get('pix_id')

            })

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

            

            # Regex para capturar valor R$ e ID do Pix (E2E ID)

            content = f"{subject} {snippet}"

            value_match = re.search(r'R\$\s*(\d+(?:[\.,]\d+)?)', content)

            pix_id_match = re.search(r'\b(E[A-Z0-9]{31})\b', content)

            pix_id = pix_id_match.group(1) if pix_id_match else None



            if value_match:

                val_str = value_match.group(1).replace('.', '').replace(',', '.')

                amount = float(val_str)

                # Classificação aprimorada de renda vs despesa

                is_income = any(word in content.lower() for word in ['recebido', 'recebeu', 'recebida', 'recebimento', 'creditado', 'entrada'])

                description = f"Pix: {subject}"

                iso_date = dt.isoformat()

                

                # Verificação de redundância aprimorada para evitar duplicatas de diferentes instituições

                is_duplicate = False

                target_cache = existing_income if is_income else existing_transactions



                for item in target_cache:

                    # 1. Por ID do Pix (E2E ID)

                    if pix_id and item.get('pix_id') == pix_id:

                        is_duplicate = True; break



                    # 2. Por Valor e Proximidade Temporal (janela de 5 minutos)

                    if item.get('amount') == amount and item.get('date'):

                        diff = abs((item['date'] - dt).total_seconds())

                        if diff < 300: # 5 minutos

                            is_duplicate = True; break



                    # 3. Legado/Exata (Descrição e Valor)

                    if item.get('description') == description and item.get('amount') == amount:

                        is_duplicate = True; break



                if is_duplicate:

                    new_processed_ids.append(msg_id)

                    continue
                    new_processed_ids.append(msg_id)
                    continue

                # Salva no banco
                if is_income:
                    new_record = {
                        'description': description, 'amount': amount, 'day': dt.day,
                        'month': dt.month - 1, 'year': dt.year,
                        'category': 'Renda Extra', 'isReceived': True, 'date': iso_date,
                        'google_message_id': msg_id, 'pix_id': pix_id
                    }
                    db.collection('finance_income').add(new_record)
                    existing_income.append({'amount': amount, 'date': dt, 'pix_id': pix_id, 'description': description})
                else:
                    sprint = 1 if dt.day < 8 else 2 if dt.day < 15 else 3 if dt.day < 22 else 4
                    new_record = {
                        'description': description, 'amount': amount, 'date': iso_date,
                        'sprint': sprint, 'category': 'Alimentação', # Original was 'Alimentação', keeping it.
                        'google_message_id': msg_id, 'pix_id': pix_id
                    }
                    db.collection('finance_transactions').add(new_record)
                    existing_transactions.append({'amount': amount, 'date': dt, 'pix_id': pix_id, 'description': description})
                
                new_processed_ids.append(msg_id)
                log_to_firestore(sync_ref, logs, f"[PIX] Processado: {description} (R$ {amount:.2f})")


        if new_processed_ids:
            updated_ids = list(set(processed_ids + new_processed_ids))[-500:] # Changed from -200 to -500
            db.collection('system').document('processed_emails').set({'ids': updated_ids}, merge=True)

    except Exception as e:
        log_to_firestore(sync_ref, logs, f"ERRO PIX: {e}")


def sync_boletos_gmail(service, sync_ref, logs):
    """
    Explora o Gmail em busca de boletos, extraia dados via IA e salva no Firestore (fixed_bills).
    """
    db = get_db()
    
    log_to_firestore(sync_ref, logs, "Buscando boletos no Gmail via IA...")
    
    # Query para emails com anexos PDF ou assuntos de fatura/boleto/pagamento
    # Pegamos os mais recentes para a sincronia automática
    query = 'has:attachment filename:pdf (subject:(boleto OR fatura OR bill OR pagamento OR "o seu boleto" OR "sua fatura" OR "vencimento") OR "boleto" OR "fatura")'
    
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=15).execute()
        messages = results.get('messages', [])
        
        if not messages:
            log_to_firestore(sync_ref, logs, "Nenhum boleto recente encontrado no Gmail.")
            return

        # Configurar Gemini
        keys_doc = db.collection('system').document('api_keys').get()
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        if not api_key:
            log_to_firestore(sync_ref, logs, "ERRO: Gemini API Key não encontrada (em system/api_keys).")
            return
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        
        processed_count = 0
        
        # Cache de boletos existentes para permitir duplicatas ou vinculação
        existing_bills_cache = []
        for b in db.collection('fixed_bills').stream():
            d = b.to_dict()
            existing_bills_cache.append({
                'id': b.id,
                'desc': d.get('description', '').lower(),
                'amount': d.get('amount'),
                'month': d.get('month'),
                'year': d.get('year'),
                'isPaid': d.get('isPaid', False)
            })

        processed_emails_doc = db.collection('system').document('processed_emails').get()
        processed_ids = processed_emails_doc.to_dict().get('ids', []) if processed_emails_doc.exists else []
        new_processed_ids = []

        for m_info in messages:
            msg_id = m_info['id']
            if msg_id in processed_ids: continue
            
            msg = service.users().messages().get(userId='me', id=msg_id).execute()
            snippet = msg.get('snippet', '')

            # Tentar baixar o primeiro PDF encontrado
            pdf_data = None
            def find_pdf(part):
                nonlocal pdf_data
                if part.get('parts'):
                    for sub in part['parts']: find_pdf(sub)
                if part.get('filename', '').lower().endswith('.pdf') and part.get('body', {}).get('attachmentId'):
                    att = service.users().messages().attachments().get(userId='me', messageId=msg_id, id=part['body']['attachmentId']).execute()
                    pdf_data = base64.urlsafe_b64decode(att['data'])
                    return
            
            find_pdf(msg['payload'])
            
            prompt = """
            Você é um assistente financeiro de elite. Analise o e-mail/documento anexo e extraia os dados abaixo para um BOLETO ou PAGAMENTO.
            Campos obrigatórios no JSON:
            - description: Nome curto da conta (ex: VIVO, Sabesp, Condomínio)
            - amount: valor numérico do boleto
            - due_date: data de vencimento (formato YYYY-MM-DD)
            - barcode: linha digitável ou código de barras (apenas números)
            - pix_code: código Pix Copia e Cola (geralmente começa com 000201...)

            Responda APENAS em JSON no formato:
            {
              "description": "...",
              "amount": 123.45,
              "due_date": "YYYY-MM-DD",
              "barcode": "...",
              "pix_code": "..."
            }
            Se não for um boleto/fatura ou se não encontrar dados, responda {"error": "not_a_bill"}.
            """
            
            content_parts = [prompt, f"E-mail Fragment: {snippet}"]
            if pdf_data:
                content_parts.append({"mime_type": "application/pdf", "data": pdf_data})
            
            try:
                response = model.generate_content(content_parts)
                res_text = response.text.strip()
                if "```json" in res_text:
                    res_text = res_text.split("```json")[-1].split("```")[0].strip()
                elif "```" in res_text:
                    res_text = res_text.split("```")[-1].split("```")[0].strip()
                
                data = json.loads(res_text)
                if data.get('error'): 
                    new_processed_ids.append(msg_id)
                    continue
                
                due_dt = datetime.fromisoformat(data['due_date'])
                month = due_dt.month - 1
                year = due_dt.year
                
                found_existing_id = None
                is_exact_dup = False
                name_extracted = data['description'].lower()

                for eb in existing_bills_cache:
                    if eb['month'] == month and eb['year'] == year:
                        # Lógica de vinculação inteligente (Pela descrição aproximada)
                        if name_extracted in eb['desc'] or eb['desc'] in name_extracted:
                            # Se o valor também for igual, é uma duplicata exata
                            if abs(eb['amount'] - data['amount']) < 0.01:
                                is_exact_dup = True
                                break
                            # Caso contrário, se o nome bater, vamos vincular a este card (atualizá-lo)
                            found_existing_id = eb['id']
                            break # Achamos o card para vincular

                if is_exact_dup:
                    new_processed_ids.append(msg_id)
                    continue
                
                if found_existing_id:
                    # VINCULAÇÃO: Atualiza card existente
                    db.collection('fixed_bills').document(found_existing_id).update({
                        'amount': data['amount'],
                        'barcode': data.get('barcode', ''),
                        'pixCode': data.get('pix_code', ''),
                        'google_message_id': msg_id,
                        'updated_at': datetime.now().isoformat()
                    })
                    log_to_firestore(sync_ref, logs, f"[BOLETO] Vinculado ao card '{data['description']}': R$ {data['amount']}")
                    processed_count += 1
                else:
                    # CRIAÇÃO: Adiciona novo card
                    db.collection('fixed_bills').add({
                        'description': data['description'],
                        'amount': data['amount'],
                        'dueDay': due_dt.day,
                        'month': month,
                        'year': year,
                        'barcode': data.get('barcode', ''),
                        'pixCode': data.get('pix_code', ''),
                        'isPaid': False,
                        'category': 'Conta Fixa',
                        'google_message_id': msg_id,
                        'created_at': datetime.now().isoformat()
                    })
                    log_to_firestore(sync_ref, logs, f"[BOLETO] Importado (Novo Card): {data['description']} (R$ {data['amount']})")
                    processed_count += 1
                
                new_processed_ids.append(msg_id)

            except Exception as e:
                error_msg = str(e)
                if "The document has no pages" in error_msg:
                    log_to_firestore(sync_ref, logs, f"Aviso: O PDF da mensagem {msg_id} está vazio. Ignorando.")
                else:
                    log_to_firestore(sync_ref, logs, f"Aviso: Erro ao processar mensagem {msg_id}: {e}")
                new_processed_ids.append(msg_id)

        if new_processed_ids:
            updated_ids = list(set(processed_ids + new_processed_ids))[-500:]
            db.collection('system').document('processed_emails').set({'ids': updated_ids}, merge=True)

        if processed_count > 0:
            log_to_firestore(sync_ref, logs, f"Sincronização de boletos concluída. {processed_count} novos boletos.")
            emit_notification_backend("Novos Boletos", f"{processed_count} novos boletos foram importados do Gmail.", "success", "financeiro")
    
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"ERRO na busca de boletos: {e}")


@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=540)
def sync_gmail_bills_callable(req: https_fn.CallableRequest):
    """Executa a sincronização de boletos do Gmail manualmente via app"""
    db = get_db()
    sync_ref = db.collection('system').document('sync')
    logs = [f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando sincronização manual via App..."]
    
    try:
        gs = get_gmail_service()
        sync_boletos_gmail(gs, sync_ref, logs)
        
        sync_ref.update({
            'status': 'completed',
            'last_success': datetime.now().isoformat(),
            'logs': logs
        })
        return {"success": True}
    except Exception as e:
        error_msg = f"Erro na sincronização manual: {str(e)}"
        log_to_firestore(sync_ref, logs, error_msg)
        return {"success": False, "error": error_msg}

def run_full_sync():
    """Executa o processo completo de sincronização"""
    db = get_db()
    sync_ref = db.collection('system').document('sync')
    logs = [f"Iniciando sincronização ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})..."]
    try:
        ts, gs, cs = get_tasks_service(), get_gmail_service(), get_calendar_service()
        # Primeiro puxa o Calendar para permitir sincronia inversa (agenda -> Hermes) antes do push
        sync_google_calendar(cs, sync_ref, logs)
        sync_google_tasks_push(ts, cs, sync_ref, logs)
        sync_google_tasks_pull(ts, sync_ref, logs)

        sync_pix_emails(gs, sync_ref, logs)

        sync_boletos_gmail(gs, sync_ref, logs)
        sync_ref.update({
            'status': 'completed',
            'last_success': datetime.now().isoformat(),

            'logs': logs

        })

        print("Sincronização concluída com sucesso.")

    except Exception as e:

        error_msg = f"ERRO na sincronização: {str(e)}"

        print(error_msg)

        sync_ref.update({

            'status': 'error',

            'error_message': error_msg,

            'logs': logs + [error_msg]

        })



@firestore_fn.on_document_updated(document="system/sync")

def on_sync_request(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]]):

    """Trigger disparado quando system/sync é atualizado manualmente"""

    if not event.data.after.exists: return

    data = event.data.after.to_dict()

    if data.get('status') != 'requested': return

    db = get_db()

    db.collection('system').document('sync').update({'status': 'processing'})

    run_full_sync()



@scheduler_fn.on_schedule(schedule="every 30 minutes")

def scheduled_sync(event: scheduler_fn.ScheduledEvent) -> None:

    """Trigger agendado para rodar a cada 30 minutos"""

    run_full_sync()

@firestore_fn.on_document_created(document="notificacoes/{notification_id}")

def on_notificacao_created(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]):

    """Trigger disparado quando uma nova notificação é criada"""

    if not event.data: return

    notif = event.data.to_dict()

    if not notif or notif.get('sent_to_push'): return

    title = notif.get('title', 'Hermes')

    message = notif.get('message', '')

    db = get_db()

    tokens_docs = db.collection('fcm_tokens').stream()
    tokens = list({doc.id for doc in tokens_docs if doc.id})
    if not tokens:

        print("Nenhum token FCM encontrado para enviar push.")

        return

    push_message = messaging.MulticastMessage(
        data={
            'id': str(notif.get('id', '')),
            'title': str(title),
            'message': str(message),
            'link': str(notif.get('link', '')),
            'type': str(notif.get('type', 'info'))
        },
        tokens=tokens,
    )
    try:

        response = messaging.send_each_for_multicast(push_message)

        print(f"Push enviado: {response.success_count} sucesso, {response.failure_count} falha.")

        if response.failure_count > 0:

            for idx, resp in enumerate(response.responses):

                if not resp.success:

                    if resp.exception and "registration-token-not-registered" in str(resp.exception).lower():

                        bad_token = tokens[idx]

                        db.collection('fcm_tokens').document(bad_token).delete()

        event.data.reference.update({'sent_to_push': True})

    except Exception as e:

        print(f"Erro ao enviar push notification: {str(e)}")



@scheduler_fn.on_schedule(schedule="every 1 minutes")

def check_and_send_reminders(event: scheduler_fn.ScheduledEvent) -> None:

    """Verifica e envia lembretes agendados (hábitos, pesagem, customizados e ações)"""

    from datetime import datetime, timedelta

    import pytz

    

    db = get_db()

    # Define o fuso horário de Brasília para comparar com as strings de horário do usuário (HH:mm)

    tz = pytz.timezone('America/Sao_Paulo')

    now = datetime.now(tz)

    current_time_str = now.strftime('%H:%M')

    today_str = now.strftime('%Y-%m-%d')

    day_of_week = now.weekday() # 0 = Monday, 1 = Tuesday... 6 = Sunday (Note: Python index matches our dayOfWeek if 0=Mon, but let's check)

    # No helper.tsx: dayOfWeek: 1 // Segunda-feira. Python: 0=Mon, 1=Tue... 

    # Precisamos ajustar para 0=Dom? Não, vamos seguir o padrão do AppSettings.

    # AppSettings weighInReminder dayOfWeek: 0-6 (0=Dom no JS Date.getDay())

    # Python now.strftime('%w') retorna 0 para Domingo.

    js_day_of_week = int(now.strftime('%w'))



    # 1. Carrega Configurações

    settings_doc = db.collection('configuracoes').document('geral').get()

    if settings_doc.exists:

        settings = settings_doc.to_dict()

        notifs_config = settings.get('notifications', {})

        

        # --- Lembrete de Hábitos ---

        habits = notifs_config.get('habitsReminder', {})

        if habits.get('enabled') and habits.get('time') == current_time_str:

            remind_id = f"habits_{today_str}"

            # Verifica se já enviou hoje

            if not db.collection('system_reminders').document(remind_id).get().exists:

                emit_notification_backend(

                    "Lembrete de Hábitos",

                    "Hora de registrar seus hábitos de hoje para manter sua rotina nos trilhos!",

                    'info',

                    'saude'

                )

                db.collection('system_reminders').document(remind_id).set({'sent_at': now.isoformat()})



        # --- Lembrete de Pesagem ---

        weigh_in = notifs_config.get('weighInReminder', {})

        if weigh_in.get('enabled') and weigh_in.get('time') == current_time_str:

            freq = weigh_in.get('frequency', 'weekly')

            target_day = weigh_in.get('dayOfWeek', 1)

            

            should_remind = False

            if js_day_of_week == target_day:

                if freq == 'weekly':

                    should_remind = True

                elif freq == 'biweekly':

                    # Lógica simplificada de biweekly baseada no timestamp da semana

                    week_num = int(now.strftime('%V'))

                    if week_num % 2 == 0: should_remind = True

                elif freq == 'monthly' and now.day == 1:

                    should_remind = True

            

            if should_remind:

                remind_id = f"weighin_{today_str}"

                if not db.collection('system_reminders').document(remind_id).get().exists:

                    emit_notification_backend(

                        "Lembrete de Pesagem",

                        "Hora de registrar seu peso para acompanhar sua evolução no módulo Saúde!",

                        'info',

                        'saude'

                    )

                    db.collection('system_reminders').document(remind_id).set({'sent_at': now.isoformat()})



        # --- Notificações Customizadas ---

        custom_notifs = notifs_config.get('custom', [])

        for cn in custom_notifs:

            if cn.get('enabled') and cn.get('time') == current_time_str:

                freq = cn.get('frequency', 'daily')

                should_send = False

                

                if freq == 'daily':

                    should_send = True

                elif freq == 'weekly' and js_day_of_week in cn.get('daysOfWeek', []):

                    should_send = True

                elif freq == 'monthly' and now.day == cn.get('dayOfMonth', 1):

                    should_send = True

                

                if should_send:

                    remind_id = f"custom_{cn.get('id')}_{today_str}"

                    if not db.collection('system_reminders').document(remind_id).get().exists:

                        emit_notification_backend(

                            "Lembrete Personalizado",

                            cn.get('message', 'Notificação Hermes'),

                            'info'

                        )

                        db.collection('system_reminders').document(remind_id).set({'sent_at': now.isoformat()})



    # 2. Lembretes de Ações (Specific Task Reminders)

    from google.cloud.firestore import Query

    # Busca tarefas com reminder_at definido e que ainda não foram marcadas como lembradas

    tasks_with_reminders = db.collection('tarefas')\
            .where('reminder_at', '<=', now.isoformat())\
            .where('reminder_sent', '==', False)\
            .stream()



    for task_doc in tasks_with_reminders:

        t = task_doc.to_dict()

        title = t.get('titulo', 'Ação Pendente')

        task_id = task_doc.id

        

        emit_notification_backend(

            f"Lembrete: {title}",

            "Está na hora de realizar esta ação agendada!",

            'warning',

            'acoes'

        )

        

        # Marca como enviado para não repetir

        task_doc.reference.update({'reminder_sent': True})



@https_fn.on_call()

def upload_to_drive(req: https_fn.CallableRequest):

    """Realiza o upload de um arquivo para o Google Drive"""

    import base64

    from googleapiclient.http import MediaIoBaseUpload

    import io

    data = req.data

    file_name = data.get('fileName')

    file_content_b64 = data.get('fileContent')

    mime_type = data.get('mimeType', 'application/octet-stream')

    folder_id = data.get('folderId')

    if not file_name or not file_content_b64:

        raise https_fn.HttpsError(

            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,

            message="O nome e o conteúdo do arquivo são obrigatórios."

        )

    try:

        service = get_drive_service()

        file_metadata = {'name': file_name}

        if folder_id:

            file_metadata['parents'] = [folder_id]

        file_content = base64.b64decode(file_content_b64)

        fh = io.BytesIO(file_content)

        media = MediaIoBaseUpload(fh, mimetype=mime_type, resumable=True)

        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        
        # Share the file publicly so frontend preview thumbnails work without 403 errors
        try:
            service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
        except Exception as perm_e:
            print(f"Aviso: Não foi possível definir a permissão pública: {perm_e}")

        return {'fileId': file.get('id'), 'webViewLink': file.get('webViewLink')}

    except Exception as e:

        print(f"Erro no upload para o Drive: {str(e)}")

        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INTERNAL, message=str(e))



@firestore_fn.on_document_written(document="tarefas/{taskId}")
def on_tarefa_written(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]]):
    """Trigger disparado quando uma tarefa é atualizada, para monitorar processo_sei e horário"""
    if not event.data or not event.data.after or not event.data.after.exists: return

    after = event.data.after.to_dict() or {}
    before = event.data.before.to_dict() if event.data.before and event.data.before.exists else {}

    taskId = event.params['taskId']
    db = get_db()

    # Checa alteração de horário de início/fim ou prazo para forçar trigger pro Google Tasks/Calendar
    if (
        after.get('horario_inicio') != before.get('horario_inicio')
        or after.get('horario_fim') != before.get('horario_fim')
        or after.get('data_limite') != before.get('data_limite')
    ):
        sync_ref = db.collection('system').document('sync')
        db.collection('system').document('sync').update({'status': 'requested'})
    
@firestore_fn.on_document_updated(document="tarefas/{taskId}")
def on_processo_updated(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]]):

    """Trigger disparado quando uma tarefa é atualizada, para monitorar processo_sei"""

    if not event.data.after.exists: return



    before = event.data.before.to_dict() or {}

    after = event.data.after.to_dict() or {}



    # Condição: Se categoria == 'CLC' e o campo processo_sei for alterado/inserido.

    if after.get('categoria') == 'CLC' and after.get('processo_sei'):

        if before.get('processo_sei') != after.get('processo_sei'):

            taskId = event.params['taskId']

            db = get_db()

            db.collection('tarefas').document(taskId).update({'sync_status': 'processando'})



            # Dispara via PubSub para o Node.js

            from google.cloud import pubsub_v1

            import json

            import os



            try:

                publisher = pubsub_v1.PublisherClient()

                topic_path = publisher.topic_path(os.environ.get('GCLOUD_PROJECT'), 'scrape-sipac')



                message_data = {

                    "taskId": taskId,

                    "processoSei": after.get('processo_sei'),

                    "folderId": db.collection('system').document('config').get().to_dict().get('googleDriveFolderId')

                }



                publisher.publish(topic_path, json.dumps(message_data).encode('utf-8'))

                print(f"Mensagem enviada para tópico scrape-sipac: {taskId}")

            except Exception as e:

                print(f"Erro ao publicar no PubSub: {e}")



@pubsub_fn.on_message_published(topic="vectorize-process")

def on_vectorize_requested(event: pubsub_fn.CloudEvent[pubsub_fn.MessagePublishedData]):

    """Trigger disparado via PubSub para vetorizar documentos"""

    import json

    try:

        message_text = event.data.message.text

        if not message_text:

             # Em algumas versões, pode estar em event.data.message.data (base64)

             import base64

             message_text = base64.b64decode(event.data.message.data).decode('utf-8')



        data = json.loads(message_text)

        task_id = data.get('taskId')

        if task_id:

            process_vectorization(task_id)

    except Exception as e:

        print(f"Erro ao processar mensagem PubSub: {e}")



@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=540)

def vectorize_process_docs_callable(req: https_fn.CallableRequest):

    """Versão callable para o frontend ou testes manuais"""

    task_id = req.data.get('taskId')

    if not task_id: return {'success': False, 'error': 'taskId faltante'}

    return process_vectorization(task_id)



def process_vectorization(task_id):

    """Lógica central de extração e vetorização"""

    import google.generativeai as genai

    db = get_db()

    task_doc = db.collection('tarefas').document(task_id).get()

    if not task_doc.exists: return {'success': False, 'error': 'Tarefa não encontrada'}



    task_data = task_doc.to_dict()

    pool_dados = task_data.get('pool_dados', [])



    # Buscar chave do Gemini

    keys_doc = db.collection('system').document('api_keys').get()

    GEMINI_API_KEY = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

    if not GEMINI_API_KEY: return {'success': False, 'error': 'Chave Gemini não configurada'}



    genai.configure(api_key=GEMINI_API_KEY)

    model = genai.GenerativeModel("gemini-2.5-flash-lite")



    count = 0

    for item in pool_dados:

        if item.get('tipo') == 'arquivo' and item.get('drive_file_id'):

            file_id = item['drive_file_id']

            # Verifica se já foi vetorizado

            existing = db.collection('processos_conhecimento').where('file_id', '==', file_id).get()

            if not existing:

                try:

                    # Download do Drive

                    service = get_drive_service()

                    request = service.files().get_media(fileId=file_id)

                    file_content = request.execute()



                    # Determinar MIME type

                    mime_type = "application/pdf" if item.get('nome', '').lower().endswith('.pdf') else "text/html"



                    # Extração de texto via Gemini 1.5 Flash

                    response = model.generate_content([

                        "Extraia todo o texto relevante deste documento para indexação. Se for HTML, ignore tags. Se for PDF, faça OCR se necessário.",

                        {"mime_type": mime_type, "data": file_content}

                    ])

                    text_content = response.text if response.text else f"Conteúdo de {item.get('nome')}"



                    embedding = genai.embed_content(

                        model="models/text-embedding-004",

                        content=text_content,

                        task_type="retrieval_document"

                    )



                    db.collection('processos_conhecimento').add({

                        'task_id': task_id,

                        'file_id': file_id,

                        'nome': item.get('nome'),

                        'texto': text_content,

                        'embedding': embedding['embedding'],

                        'data_vetorizacao': firestore.SERVER_TIMESTAMP

                    })

                    count += 1

                except Exception as e:

                    print(f"Erro ao vetorizar {file_id}: {e}")



    return {'success': True, 'vectorized_count': count}



@https_fn.on_call()

def transcreverAudio(req: https_fn.CallableRequest):

    """

    Recebe áudio em Base64, transcreve com Groq (Whisper) e refina com Gemini.

    """

    import base64

    import tempfile

    import os

    from groq import Groq

    import google.generativeai as genai



    # Buscar chaves de API no Firestore

    try:

        db = get_db()

        keys_doc = db.collection('system').document('api_keys').get()

        if not keys_doc.exists:

            raise Exception("Documento system/api_keys não encontrado.")

        keys = keys_doc.to_dict()

        GROQ_API_KEY = keys.get('groq_api_key')

        GEMINI_API_KEY = keys.get('gemini_api_key')

        

        if not GROQ_API_KEY or not GEMINI_API_KEY:

            raise Exception("Chaves de API incompletas em system/api_keys.")

            

    except Exception as e:

        print(f"Erro ao buscar chaves de API: {e}")

        raise https_fn.HttpsError(

            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,

            message="Configuração de API pendente no sistema."

        )



    data = req.data

    audio_base64 = data.get('audioBase64')

    extension = data.get('extension', '.m4a')



    if not extension.startswith('.'):

        extension = f".{extension}"



    if not audio_base64:

        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message="Áudio não fornecido.")



    temp_filename = None

    try:

        # 1. Decodificar Base64 para arquivo temporário

        audio_data = base64.b64decode(audio_base64)

        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temp_audio:

            temp_audio.write(audio_data)

            temp_filename = temp_audio.name



        # 2. Transcrição via Groq (Whisper Large V3 Turbo)

        client = Groq(api_key=GROQ_API_KEY)

        with open(temp_filename, "rb") as file_stream:

            transcription = client.audio.transcriptions.create(

                file=(os.path.basename(temp_filename), file_stream), 

                model="whisper-large-v3-turbo",

                response_format="json",

                language="pt",

                temperature=0.0

            )

        texto_bruto = transcription.text



        # Refinamento via Gemini Flash

        genai.configure(api_key=GEMINI_API_KEY)

        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        prompt = f"""

        Atue como um redator especialista. O texto a seguir é uma transcrição de voz bruta.

        Sua tarefa:

        1. Corrigir pontuação e gramática (pt-BR).

        2. Remover vícios de linguagem (né, tipo, ahn).

        3. Manter o tom original e termos técnicos.

        4. Retorne APENAS o texto corrigido, sem introduções.

        

        Texto: "{texto_bruto}"

        """

        result = model.generate_content(prompt)

        texto_refinado = result.text



        return {"raw": texto_bruto, "refined": texto_refinado}

    except Exception as e:

        print(f"Erro na transcrição: {str(e)}")

        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INTERNAL, message=f"Falha ao processar áudio: {str(e)}")

    finally:

        if temp_filename and os.path.exists(temp_filename):

            try:

                os.remove(temp_filename)

            except:

                pass



def start_file_indexing(item_id, item_data):

    """Lógica central de indexação com Gemini"""

    url_drive = item_data.get('url_drive')

    if not url_drive:

        return {'success': False, 'error': 'URL não encontrada'}



    import re

    def extract_file_id(url):

        match = re.search(r'[-\w]{25,}', url)

        return match.group(0) if match else None



    file_id = extract_file_id(url_drive)

    if not file_id:

        return {'success': False, 'error': 'ID do arquivo não identificado na URL'}



    try:

        db = get_db()

        keys_doc = db.collection('system').document('api_keys').get()

        if not keys_doc.exists:

            return {'success': False, 'error': 'Configuração de API não encontrada (system/api_keys)'}



        GEMINI_API_KEY = keys_doc.to_dict().get('gemini_api_key')

        if not GEMINI_API_KEY:

            return {'success': False, 'error': 'Chave de API Gemini não configurada'}



        import google.generativeai as genai

        import json



        genai.configure(api_key=GEMINI_API_KEY)

        model = genai.GenerativeModel("gemini-2.5-flash-lite") # Usando modelo preferencial do André



        service = get_drive_service()

        file_metadata = service.files().get(fileId=file_id, fields='mimeType, name').execute()

        mime_type = file_metadata.get('mimeType')



        request = service.files().get_media(fileId=file_id)

        content = request.execute()



        prompt = ""

        parts = []



        if mime_type.startswith('image/'):

            prompt = """

            Analise esta imagem e retorne em JSON:

            1. ocr: Todo o texto escrito na imagem.

            2. descricao: Descrição semântica detalhada.

            3. resumo_tldr: Resumo de até 3 linhas.

            4. tags: Lista de 5-10 palavras-chave.

            5. categoria: Uma única palavra de classificação.

            """

            parts = [{"mime_type": mime_type, "data": content}, prompt]

        elif mime_type == 'application/pdf':

            prompt = """

            Analise este PDF e retorne em JSON:

            1. texto_bruto: Conteúdo principal extraído.

            2. resumo_tldr: Resumo de até 3 linhas.

            3. tags: Lista de 5-10 palavras-chave.

            4. categoria: Uma única palavra de classificação.

            """

            parts = [{"mime_type": mime_type, "data": content}, prompt]

        else:

            text_content = ""

            try:

                text_content = content.decode('utf-8')

            except:

                text_content = "[Binário]"



            prompt = f"""

            Analise este conteúdo e retorne em JSON:

            1. resumo_tldr: Resumo de até 3 linhas.

            2. tags: Lista de 5-10 palavras-chave.

            3. categoria: Uma única palavra de classificação.

            4. texto_bruto: O próprio texto.



            CONTEÚDO:

            {text_content[:100000]}

            """

            parts = [prompt]



        response = model.generate_content(parts)

        res_text = response.text



        json_match = re.search(r'\{.*\}', res_text, re.DOTALL)

        if json_match:

            data = json.loads(json_match.group(0))

            updates = {

                'resumo_tldr': data.get('resumo_tldr'),

                'tags': data.get('tags'),

                'categoria': data.get('categoria', 'Geral').upper()

            }



            if mime_type.startswith('image/'):

                updates['texto_bruto'] = f"OCR: {data.get('ocr')}\n\nDESCRIÇÃO: {data.get('descricao')}"

            else:

                updates['texto_bruto'] = data.get('texto_bruto') or item_data.get('titulo')



            db.collection('conhecimento').document(item_id).set(updates, merge=True)

            return {'success': True, 'item_id': item_id}

        return {'success': False, 'error': 'Não foi possível gerar metadados JSON'}



    except Exception as e:

        print(f"Erro ao processar arquivo {item_id}: {str(e)}")

        return {'success': False, 'error': str(e)}



@firestore_fn.on_document_created(document="conhecimento/{itemId}")

def on_arquivo_adicionado(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]):

    """Trigger disparado quando um novo arquivo é adicionado"""

    if not event.data: return

    item_data = event.data.to_dict()

    item_id = event.params["itemId"]



    # Ignora links diretos (sem processamento de IA/OCR)

    if item_data.get('tipo_arquivo') == 'link':

        return



    if item_data.get('tags') and item_data.get('resumo_tldr'):

        return



    start_file_indexing(item_id, item_data)



@https_fn.on_call(

    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),

    memory=options.MemoryOption.GB_2,

    timeout_sec=540

)

def processarArquivoIA(req: https_fn.CallableRequest):

    """Callable para disparar processamento manual"""

    item_id = req.data.get('itemId')

    if not item_id:

        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message="ID do item é obrigatório")

    

    db = get_db()

    doc = db.collection('conhecimento').document(item_id).get()

    if not doc.exists:

        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Arquivo não encontrado")

    

    # Limpa campos antigos para mostrar o loader no front se necessário e garantir re-processamento

    db.collection('conhecimento').document(item_id).update({

        'resumo_tldr': None,

        'tags': None

    })



    return start_file_indexing(item_id, doc.to_dict())

@https_fn.on_call(memory=options.MemoryOption.GB_1)

def gerarSlidesIA(req: https_fn.CallableRequest):

    """

    Gera conteúdo para slides a partir de um texto bruto.

    """

    import google.generativeai as genai

    import json



    data = req.data

    rascunho = data.get('rascunho')

    qtd_slides = data.get('qtdSlides', 5)



    if not rascunho:

        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message="Texto bruto não fornecido.")



    try:

        db = get_db()

        keys_doc = db.collection('system').document('api_keys').get()

        if not keys_doc.exists:

            raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, message="Configuração de API pendente.")

        

        GEMINI_API_KEY = keys_doc.to_dict().get('gemini_api_key')

        if not GEMINI_API_KEY:

            raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, message="Chave Gemini não configurada.")



        genai.configure(api_key=GEMINI_API_KEY)

        model = genai.GenerativeModel("gemini-2.5-flash-lite") # Usando o modelo solicitado no slides-ia e preferido do André



        system_instruction = f"""

        Atue como Especialista em Design de Apresentações Profissionais.

        Sua tarefa é transformar o texto bruto fornecido em uma estrutura de apresentação de slides premium.

        

        Regras de Negócio:

        1. Gere EXATAMENTE {qtd_slides} slides.

        2. Use layouts variados: 'capa' (apenas no primeiro), 'titulo_e_conteudo', 'somente_titulo'. (EVITE outros layouts complexos por enquanto).

        3. Tópicos: Use frases curtas, impactantes e diretas. No máximo 4 tópicos por slide. 

        4. IMPORTANTE: O campo 'topicos' deve ser SEMPRE uma lista de strings simples. Nunca use objetos ou dicionários dentro desta lista.

        5. Prompt de Imagem: Forneça um prompt em INGLÊS detalhado para cada slide, focado em imagens corporativas, modernas e de alta qualidade (minimalista, 4k, profissional).

        6. Tom de voz: Profissional, executivo e inspirador.



        Retorne APENAS um objeto JSON seguindo este esquema:

        {{

          "slides": [

            {{

              "numero": 1,

              "layout": "capa",

              "titulo": "Título Principal",

              "topicos": ["Subtítulo ou frase de impacto"],

              "prompt_imagem": "Professional corporate background..."

            }}

          ]

        }}

        """



        response = model.generate_content([

            system_instruction,

            f"Texto Bruto para Processar:\n{rascunho}"

        ], generation_config={"response_mime_type": "application/json"})



        # Limpeza básica caso venha com markdown

        text_response = response.text.replace('```json', '').replace('```', '').strip()

        return json.loads(text_response)



    except Exception as e:

        print(f"Erro ao gerar slides: {str(e)}")

        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INTERNAL, message=str(e))



@https_fn.on_call(memory=options.MemoryOption.GB_1)

def processInvoiceOCR(req: https_fn.CallableRequest):

    """

    Processa uma Nota Fiscal (PDF/Imagem) do Google Drive usando Gemini e extrai dados estruturados.

    """

    import google.generativeai as genai

    import json

    import re



    file_id = req.data.get('fileId')

    if not file_id:

        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message="fileId é obrigatório.")



    try:

        db = get_db()

        keys_doc = db.collection('system').document('api_keys').get()

        GEMINI_API_KEY = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None



        if not GEMINI_API_KEY:

             raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, message="Chave Gemini não configurada.")



        genai.configure(api_key=GEMINI_API_KEY)

        model = genai.GenerativeModel("gemini-1.5-flash") # Using Flash for speed/cost



        # Download from Drive

        service = get_drive_service()

        file_metadata = service.files().get(fileId=file_id, fields='mimeType, name').execute()

        mime_type = file_metadata.get('mimeType')



        request = service.files().get_media(fileId=file_id)

        file_content = request.execute()



        prompt = """

        Analise este documento (Nota Fiscal ou Recibo) e extraia os seguintes dados em formato JSON estrito:

        {

            "fornecedor": "Nome da Empresa",

            "cnpj": "XX.XXX.XXX/0001-XX",

            "data_emissao": "YYYY-MM-DD",

            "valor_total": 0.00,

            "itens": [

                {

                    "descricao": "Nome do Produto",

                    "quantidade": 1,

                    "valor_unitario": 0.00,

                    "valor_total": 0.00

                }

            ]

        }

        Se algum campo não for encontrado, retorne null ou lista vazia.

        Normalize a data para ISO 8601.

        Normalize valores numéricos para float (ponto flutuante).

        """



        parts = [{"mime_type": mime_type, "data": file_content}, prompt]



        response = model.generate_content(parts)

        res_text = response.text



        # Clean Markdown code blocks if present

        json_match = re.search(r'```json\s*(.*?)\s*```', res_text, re.DOTALL)

        if json_match:

            json_str = json_match.group(1)

        else:

            json_str = res_text



        data = json.loads(json_str)

        return data



    except Exception as e:

        print(f"Erro no OCR de Nota Fiscal: {str(e)}")

        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INTERNAL, message=str(e))


@https_fn.on_call()
def transcrever_audio(req: https_fn.CallableRequest):
    """
    Recebe áudio em Base64, transcreve com Groq (Whisper-Large-V3-Turbo) e refina com Gemini.
    """
    import base64
    import tempfile
    import os
    # Instale: pip install groq google-generativeai
    from groq import Groq
    import google.generativeai as genai

    data = req.data
    audio_base64 = data.get('audioBase64')

    if not audio_base64:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Áudio não fornecido."
        )

    # Buscar chaves de API no Firestore
    try:
        # Import local (dentro da função ou escopo global se preferir, mas aqui segue o padrão do fix)
        # Assumindo que get_db já existe no main.py. Mas o fix_main.py injeta apenas ESTA função?
        # Sim, ele injeta `transcrever_audio`.
        # Precisamos garantir que `get_db` esteja disponível ou usar firestore.client() direto?
        # O arquivo main.py tem `from firebase_admin import firestore` e `initialize_app`.
        # Melhor usar `firestore.client()` diretamente para garantir, já que `get_db` é custom.
        # Mas `main.py` tem `get_db` definido no topo. Vamos usar `get_db()` para consistência,
        # assumindo que o `fix_main.py` insere isso num arquivo que tem `get_db`.
        
        # Como não temos certeza se `get_db` está acessível no escopo (python é permissivo),
        # vamos usar o padrão seguro: importar firestore.
        from firebase_admin import firestore
        db = firestore.client()
        keys_doc = db.collection('system').document('api_keys').get()
        
        if not keys_doc.exists:
             raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, 
                message="Chaves de API não configuradas (system/api_keys)."
            )
            
        keys = keys_doc.to_dict()
        GROQ_API_KEY = keys.get('groq_api_key')
        GEMINI_API_KEY = keys.get('gemini_api_key')
        
    except Exception as e:
        print(f"Erro ao buscar chaves: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Erro interno de configuração."
        )

    temp_path = None
    try:
        # 1. Converter Base64 para arquivo temporário
        # b64decode retorna bytes
        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception:
             raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Base64 inválido."
            )
        
        # Cria um arquivo temporário físico para o Groq poder ler
        # O sufixo .m4a é importante para o ffmpeg interno do whisper identificar o formato se necessário
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name

        # 2. Transcrição via Groq
        client = Groq(api_key=GROQ_API_KEY)
        
        with open(temp_path, "rb") as file_stream:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(temp_path), file_stream), 
                model="whisper-large-v3-turbo",
                response_format="json",
                language="pt",
                temperature=0.0
            )

        texto_bruto = transcription.text

        # 3. Refinamento via Gemini Flash
        genai.configure(api_key=GEMINI_API_KEY)
        # Usando o modelo solicitado (2.5-flash)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = f"""
        Atue como um redator especialista. O texto a seguir é uma transcrição de voz bruta.
        Sua tarefa:
        1. Corrigir pontuação e gramática (pt-BR).
        2. Remover vícios de linguagem (né, tipo, ahn).
        3. Manter o tom original e termos técnicos.
        4. Retorne APENAS o texto corrigido, sem introduções.
        
        Texto: "{texto_bruto}"
        """
        
        response = model.generate_content(prompt)
        texto_refinado = response.text

        return {
            "raw": texto_bruto,
            "refined": texto_refinado
        }

    except Exception as e:
        print(f"Erro na transcrição: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=f"Falha ao processar áudio: {str(e)}"
        )
    finally:
        # Limpeza
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
    timeout_sec=120
)
def askChatbot(req: https_fn.CallableRequest):
    """
    Responde perguntas sobre o contexto da reunião usando Gemini.
    """
    import google.generativeai as genai

    prompt = (req.data or {}).get('prompt')
    if not isinstance(prompt, str) or not prompt.strip():
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Prompt é obrigatório."
        )

    try:
        db = get_db()
        keys_doc = db.collection('system').document('api_keys').get()
        gemini_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        if not gemini_key:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
                message="Chave Gemini não configurada."
            )

        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
        response = model.generate_content(
            [
                "Você é um assistente de reunião em pt-BR. Responda com objetividade, "
                "baseando-se no contexto recebido. Se o contexto estiver incompleto, "
                "deixe claro que a resposta é parcial.",
                prompt.strip(),
            ]
        )

        result = (response.text or "").strip()
        if not result:
            result = "Não consegui gerar uma resposta com o contexto atual da reunião."
        return {"result": result}

    except https_fn.HttpsError:
        raise
    except Exception as e:
        print(f"Erro em askChatbot: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Falha ao processar sua solicitação no assistente de reunião."
        )


@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
    timeout_sec=120
)
def salvarTranscricaoReuniao(req: https_fn.CallableRequest):
    """
    Salva a transcrição consolidada de uma reunião no Google Drive e registra no módulo conhecimento.
    """
    import io
    from datetime import datetime
    from googleapiclient.http import MediaIoBaseUpload

    data = req.data or {}
    content = data.get('content')
    started_at = data.get('startedAt')
    ended_at = data.get('endedAt')
    file_name = data.get('fileName')

    if not isinstance(content, str) or not content.strip():
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Conteúdo da transcrição é obrigatório."
        )

    def _parse_iso_date(value: str | None) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    started_dt = _parse_iso_date(started_at) or datetime.now()
    ended_dt = _parse_iso_date(ended_at) or datetime.now()

    if not file_name:
        file_name = f"Reuniao_{started_dt.strftime('%Y-%m-%d_%H-%M')}.txt"

    try:
        db = get_db()
        service = get_drive_service()

        root_folder_id = None
        try:
            config_doc = db.collection('system').document('config').get()
            if config_doc.exists:
                root_folder_id = (config_doc.to_dict() or {}).get('googleDriveFolderId')
        except Exception as config_err:
            print(f"Aviso: não foi possível ler system/config: {config_err}")

        # Garante a pasta "Reuniões" na raiz configurada para o conhecimento.
        folder_query = (
            "mimeType='application/vnd.google-apps.folder' "
            "and trashed=false "
            "and name='Reuniões'"
        )
        if root_folder_id:
            folder_query += f" and '{root_folder_id}' in parents"

        folders = service.files().list(
            q=folder_query,
            fields='files(id, name)',
            pageSize=1
        ).execute().get('files', [])

        if folders:
            reunioes_folder_id = folders[0]['id']
        else:
            folder_metadata = {
                'name': 'Reuniões',
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if root_folder_id:
                folder_metadata['parents'] = [root_folder_id]

            folder = service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            reunioes_folder_id = folder.get('id')

        payload = content.encode('utf-8')
        media = MediaIoBaseUpload(io.BytesIO(payload), mimetype='text/plain', resumable=True)

        uploaded = service.files().create(
            body={'name': file_name, 'parents': [reunioes_folder_id]},
            media_body=media,
            fields='id, webViewLink, size'
        ).execute()

        file_id = uploaded.get('id')
        web_link = uploaded.get('webViewLink')

        try:
            service.permissions().create(
                fileId=file_id,
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()
        except Exception as perm_e:
            print(f"Aviso: não foi possível definir permissão pública no arquivo de reunião: {perm_e}")

        db.collection('conhecimento').document(file_id).set({
            'id': file_id,
            'titulo': file_name,
            'tipo_arquivo': 'txt',
            'url_drive': web_link,
            'tamanho': int(uploaded.get('size') or len(payload)),
            'data_criacao': datetime.now().isoformat(),
            'origem': {'modulo': 'reunioes', 'id_origem': started_dt.isoformat()},
            'categoria': 'Reuniões',
            'parent_id': 'biblioteca',
            'meeting_started_at': started_dt.isoformat(),
            'meeting_ended_at': ended_dt.isoformat()
        }, merge=True)

        return {
            'success': True,
            'fileId': file_id,
            'webViewLink': web_link,
            'fileName': file_name,
            'folderId': reunioes_folder_id
        }

    except https_fn.HttpsError:
        raise
    except Exception as e:
        print(f"Erro ao salvar transcrição de reunião: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Falha ao salvar transcrição da reunião no Google Drive."
        )

