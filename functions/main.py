

from firebase_functions import firestore_fn, scheduler_fn, options, https_fn, pubsub_fn

from firebase_admin import initialize_app, firestore, messaging, get_app
import json
import base64
from datetime import datetime, timedelta, timezone
import time
import re
import io
import uuid
import secrets
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from security_portals import (
    askWhatsAppAssistantSecure,
    generatePgdFromDiariesAI,
    generatePgdFromRawTextAI,
    getPublicFinancePortal,
    getPublicScholarshipProject,
    getPublicShoppingPortal,
    matchShoppingItemsAI,
    mutatePublicShoppingPortal,
    submitPublicFinanceTransaction,
    submitPublicScholarshipRegistration,
)

# Grafo de Conhecimento — importa as Cloud Functions e o helper de RAG
from knowledge_graph import (  # noqa: F401 — registra as Cloud Functions
    on_tarefa_created_kg,
    on_tarefa_concluida_kg,
    buscar_procedimento,
    crystallize_task_manual,
    extract_kg_rag_context,
    processar_artefato_kg,
    monitorar_acervo_global,
)


# Inicializa o Firebase Admin apenas uma vez no escopo global
try:
    get_app()
except ValueError:
    initialize_app()

DEFAULT_GOOGLE_CALENDAR_ID = 'cf4953b9512ee2e85a7e064f9d5ce4eaf6e3634564c91e5c7ee2bb01fd46782a@group.calendar.google.com'
SYNC_LOCK_DOC_ID = 'sync_lock'
SYNC_LOCK_STALE_SECONDS = 15 * 60
MAX_SYNC_PASSES = 3


def get_genai_module():
    from google import genai
    return genai


def get_embedding(text: str, api_key: str = None, task_type: str = "RETRIEVAL_DOCUMENT") -> list:
    """Get text embedding via Gemini REST API v1beta.
    task_type should be RETRIEVAL_DOCUMENT for indexing and RETRIEVAL_QUERY for searching."""
    import requests as req_lib
    if not api_key:
        db = get_db()
        keys_doc = db.collection('system').document('api_keys').get()
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
    if not api_key:
        raise ValueError("Chave Gemini não configurada.")
    url = "https://generativelanguage.googleapis.com/v1/models/text-embedding-004:embedContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    payload = {
        "model": "models/text-embedding-004",
        "content": {"parts": [{"text": text[:8000]}]},
        "taskType": task_type,
        "output_dimensionality": 768
    }
    response = req_lib.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()["embedding"]["values"]



def get_db():

    """Retorna a instância do Firestore de forma lazy"""

    return firestore.client()



def get_google_creds():
    """Busca as credenciais OAuth2 do Firestore e renova se necessário"""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    db = get_db()
    creds_doc = db.collection('system').document('google_credentials').get()

    if not creds_doc.exists:
        raise Exception("Credenciais não encontradas no Firestore.")

    creds_data = creds_doc.to_dict()
    SCOPES = [
        'https://www.googleapis.com/auth/tasks',
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/drive'
    ]

    creds = Credentials(
        token=creds_data.get('token'),
        refresh_token=creds_data.get('refresh_token'),
        token_uri=creds_data.get('token_uri'),
        client_id=creds_data.get('client_id'),
        client_secret=creds_data.get('client_secret'),
        scopes=SCOPES
    )

    # Verifica se o token expirou e tenta renovar
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Salva o NOVO token de volta no Firestore para evitar falhas futuras
            db.collection('system').document('google_credentials').update({
                'token': creds.token,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print("Token Google renovado e salvo no Firestore com sucesso.")
        except Exception as e:
            print(f"Erro ao renovar token do Google: {e}")
            
    return creds




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


def parse_iso_datetime(value):

    if not value or not isinstance(value, str):

        return None

    try:

        normalized = value.replace('Z', '+00:00')

        return datetime.fromisoformat(normalized)

    except Exception:

        return None


def build_task_calendar_event_id(task_id):

    stable_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"hermes-task:{task_id}")

    return f"hermes{stable_uuid.hex}"


def queue_sync_request(db, reason=None):

    payload = {
        'pending_request': True,
        'pending_request_at': datetime.now(timezone.utc).isoformat()
    }

    if reason:

        payload['pending_reason'] = reason

    db.collection('system').document('sync').set(payload, merge=True)


def acquire_sync_lock(db, owner_id):

    lock_ref = db.collection('system').document(SYNC_LOCK_DOC_ID)
    now = datetime.now(timezone.utc)
    lock_payload = {
        'owner_id': owner_id,
        'started_at': now.isoformat(),
        'expires_at': (now + timedelta(seconds=SYNC_LOCK_STALE_SECONDS)).isoformat()
    }

    try:

        lock_ref.create(lock_payload)

        return True

    except Exception:

        pass

    try:

        lock_doc = lock_ref.get()

        if lock_doc.exists:

            lock_data = lock_doc.to_dict() or {}
            expires_at = parse_iso_datetime(lock_data.get('expires_at'))

            if expires_at and expires_at > now:

                return False

        lock_ref.delete()
        lock_ref.create(lock_payload)

        return True

    except Exception:

        return False


def release_sync_lock(db, owner_id):

    lock_ref = db.collection('system').document(SYNC_LOCK_DOC_ID)

    try:

        lock_doc = lock_ref.get()

        if not lock_doc.exists:

            return

        lock_data = lock_doc.to_dict() or {}

        if lock_data.get('owner_id') == owner_id:

            lock_ref.delete()

    except Exception:

        pass



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

    area_tematica, contabilizar_meta = 'NÃO CLASSIFICADA', False

    tags = re.findall(r'\[(.*?)\]|TAG:\s*([\w\-]+)', text)

    tags = [t[0].upper() if t[0] else t[1].upper() for t in tags]

    

    if any(tag in ['CLC', 'LICITACAO'] for tag in tags):

        area_tematica, contabilizar_meta = 'CLC', True

    elif any(tag in ['ASSISTENCIA', 'ESTUDANTIL'] for tag in tags):

        area_tematica, contabilizar_meta = 'ASSISTÊNCIA', True

    elif 'GERAL' in tags:

        area_tematica = 'GERAL'



    # Se não classificou por tag, tenta por palavra-chave no texto

    if area_tematica == 'NÃO CLASSIFICADA':

        clc_keywords = ['LICITAÇÃO', 'LICITACAO', 'PREGÃO', 'PREGAO', 'CONTRATO', 'DISPENSA', 'INEXIGIBILIDADE', 'COMPRA', 'AQUISIÇÃO', 'AQUISICAO', 'PROCESSO']

        assist_keywords = ['ASSISTÊNCIA', 'ASSISTENCIA', 'ESTUDANTIL', 'ALUNO', 'BOLSA', 'AUXÍLIO', 'AUXILIO', 'PERMANÊNCIA', 'PERMANENCIA']



        if any(kw in text for kw in clc_keywords):

            area_tematica, contabilizar_meta = 'CLC', True

        elif any(kw in text for kw in assist_keywords):

            area_tematica, contabilizar_meta = 'ASSISTÊNCIA', True



    return area_tematica, None, contabilizar_meta



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
    from datetime import timezone
    remote_dt = parse_iso_datetime(remote_updated)
    local_dt = parse_iso_datetime(local_updated)

    if remote_dt and local_dt:
        # Se um for aware e o outro naive, forçamos o naive para UTC para permitir a comparação
        if remote_dt.tzinfo is not None and local_dt.tzinfo is None:
            local_dt = local_dt.replace(tzinfo=timezone.utc)
        elif remote_dt.tzinfo is None and local_dt.tzinfo is not None:
            remote_dt = remote_dt.replace(tzinfo=timezone.utc)
            
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
                    'area_tematica': cat, 'contabilizar_meta': meta, 'notas': g_notes,
                    'data_limite': g_due if g_due else '-',
                    'horario_inicio': h_inicio, 'horario_fim': h_fim,
                    'tipo_acao': 'fast', 'origem': 'manual'
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

            cat = t.get('area_tematica', '')

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
            desired_event_id = build_task_calendar_event_id(doc.id)
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
                        'end': {'dateTime': end_dt, 'timeZone': 'America/Sao_Paulo'},
                        'extendedProperties': {
                            'private': {
                                'hermes_task_id': doc.id
                            }
                        }
                    }
                    insert_event_body = dict(event_body)
                    insert_event_body['id'] = desired_event_id
                    
                    if not cal_id:
                        # Cria novo
                        try:
                            new_event = calendar_service.events().insert(calendarId=calendar_id, body=insert_event_body).execute()
                        except HttpError as cal_err:
                            if cal_err.resp.status != 409:
                                raise
                            new_event = calendar_service.events().get(calendarId=calendar_id, eventId=desired_event_id).execute()
                        doc.reference.update({'google_calendar_id': new_event['id']})
                        log_to_firestore(sync_ref, logs, f"[+] ALOCADA CALENDAR: {title}")
                    else:
                        # Atualiza
                        try:
                            calendar_service.events().update(calendarId=calendar_id, eventId=cal_id, body=event_body).execute()
                        except HttpError as cal_err:
                            if cal_err.resp.status == 404:
                                try:
                                    new_event = calendar_service.events().insert(calendarId=calendar_id, body=insert_event_body).execute()
                                except HttpError as conflict_err:
                                    if conflict_err.resp.status != 409:
                                        raise
                                    new_event = calendar_service.events().get(calendarId=calendar_id, eventId=desired_event_id).execute()
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
            deterministic_event_id = build_task_calendar_event_id(task_doc.id)
            linked_tasks_by_event_id.setdefault(deterministic_event_id, []).append((task_doc.reference, task_data))
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
        
        # Cache de rubricas de renda para vinculação automática
        income_rubrics_cache = []
        for r in db.collection('income_rubrics').stream():
            d = r.to_dict()
            income_rubrics_cache.append({
                'id': r.id,
                'desc': d.get('description', '').lower(),
                'category': d.get('category', 'Renda Extra')
            })



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
                    # Busca em rubricas de renda para vinculação
                    matched_rubric_id = None
                    matched_category = 'Renda Extra'
                    clean_desc = description.replace('Pix: ', '').lower()
                    for rb in income_rubrics_cache:
                        if rb['desc'] in clean_desc or clean_desc in rb['desc']:
                            matched_rubric_id = rb['id']
                            matched_category = rb['category']
                            break

                    new_record = {
                        'description': description, 'amount': amount, 'day': dt.day,
                        'month': dt.month - 1, 'year': dt.year,
                        'category': matched_category, 'isReceived': True, 'date': iso_date,
                        'google_message_id': msg_id, 'pix_id': pix_id,
                        'rubricId': matched_rubric_id
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
        
        genai = get_genai_module()
        client = genai.Client(api_key=api_key)

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
                'isPaid': d.get('isPaid', False),
                'rubricId': d.get('rubricId')
            })

        # Cache de rubricas para vinculação automática
        rubrics_cache = []
        for r in db.collection('bill_rubrics').stream():
            d = r.to_dict()
            rubrics_cache.append({
                'id': r.id,
                'desc': d.get('description', '').lower(),
                'category': d.get('category', 'Conta Fixa')
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
            
            # Formata rubricas para o prompt
            rubrics_text = "\n".join([f"- {r['desc']} (ID: {r['id']}, Categoria: {r['category']})" for r in rubrics_cache])
            
            prompt = f"""
            Você é um assistente financeiro de elite. Analise o e-mail/documento anexo e extraia os dados abaixo para um BOLETO ou PAGAMENTO.
            
            Além disso, compare esta conta com a seguinte lista de RUBRICAS RECORRENTES do usuário:
            {rubrics_text}
            
            Se o boleto corresponder a uma dessas rubricas (mesmo que o nome não seja idêntico, ex: "EDP ENERGIA" corresponde a "EDP (energia)"), informe o ID da rubrica.
            
            Campos obrigatórios no JSON:
            - description: Nome curto da conta (ex: VIVO, Sabesp, Condomínio)
            - amount: valor numérico do boleto
            - due_date: data de vencimento (formato YYYY-MM-DD)
            - barcode: linha digitável ou código de barras (apenas números)
            - pix_code: código Pix Copia e Cola (geralmente começa com 000201...)
            - rubric_id: ID da rubrica correspondente (se houver match) ou null
            - category: Categoria da conta (use a da rubrica se houver match)

            Responda APENAS em JSON no formato:
            {{
              "description": "...",
              "amount": 123.45,
              "due_date": "YYYY-MM-DD",
              "barcode": "...",
              "pix_code": "...",
              "rubric_id": "...",
              "category": "..."
            }}
            Se não for um boleto/fatura ou se não encontrar dados, responda {{"error": "not_a_bill"}}.
            """
            
            content_parts = [prompt, f"E-mail Fragment: {snippet}"]
            if pdf_data:
                content_parts.append({"mime_type": "application/pdf", "data": pdf_data})
            
            try:
                response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=content_parts)
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
                # Prioriza o match de rubrica feito pela IA
                rubric_id_from_ai = data.get('rubric_id')

                for eb in existing_bills_cache:
                    if eb['month'] == month and eb['year'] == year:
                        # 1. Tenta match por rubricId (IA indicou este card)
                        if rubric_id_from_ai and eb.get('rubricId') == rubric_id_from_ai:
                            found_existing_id = eb['id']
                            found_existing_rubric_id = eb.get('rubricId')
                            # Se valor for igual, é exatamente o mesmo registro
                            if abs(eb['amount'] - data['amount']) < 0.01:
                                is_exact_dup = True
                            break

                        # 2. Lógica de vinculação via nome (Fallback/Ambiguidade)
                        if name_extracted in eb['desc'] or eb['desc'] in name_extracted:
                            # Se o valor também for igual, é uma duplicata exata
                            if abs(eb['amount'] - data['amount']) < 0.01:
                                is_exact_dup = True
                                break
                            # Caso contrário, vamos vincular a este card (atualizá-lo)
                            found_existing_id = eb['id']
                            found_existing_rubric_id = eb.get('rubricId')
                            break 

                if is_exact_dup:
                    new_processed_ids.append(msg_id)
                    continue
                
                if found_existing_id:
                    # VINCULAÇÃO: Atualiza card existente
                    update_data = {
                        'amount': data['amount'],
                        'barcode': data.get('barcode', ''),
                        'pixCode': data.get('pix_code', ''),
                        'google_message_id': msg_id,
                        'updated_at': datetime.now().isoformat()
                    }
                    
                    # Se o card existente não tiver rubricId, usa o da IA ou tenta achar
                    if not found_existing_rubric_id:
                        update_data['rubricId'] = rubric_id_from_ai
                        if not update_data['rubricId']:
                            for rb in rubrics_cache:
                                if name_extracted in rb['desc'] or rb['desc'] in name_extracted:
                                    update_data['rubricId'] = rb['id']
                                    break
                                
                    db.collection('fixed_bills').document(found_existing_id).update(update_data)
                    log_to_firestore(sync_ref, logs, f"[BOLETO] Vinculado ao card '{data['description']}': R$ {data['amount']}")
                    processed_count += 1
                else:
                    # BUSCA EM RUBRICAS (Fallback se a IA não retornou rubric_id)
                    matched_rubric_id = rubric_id_from_ai
                    matched_category = data.get('category', 'Conta Fixa')
                    
                    if not matched_rubric_id:
                        for rb in rubrics_cache:
                            if name_extracted in rb['desc'] or rb['desc'] in name_extracted:
                                matched_rubric_id = rb['id']
                                matched_category = rb['category']
                                break

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
                        'category': matched_category,
                        'rubricId': matched_rubric_id,
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

def run_full_sync(trigger_reason='unspecified'):
    """Executa o processo completo de sincronização"""
    db = get_db()
    sync_ref = db.collection('system').document('sync')
    run_id = uuid.uuid4().hex
    logs = [f"Iniciando sincronização ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})... Trigger: {trigger_reason}"]

    if not acquire_sync_lock(db, run_id):
        queue_sync_request(db, f"sync-busy:{trigger_reason}")
        print(f"Sincronização já em andamento. Pedido enfileirado: {trigger_reason}")
        return False

    try:
        sync_ref.set({
            'status': 'processing',
            'active_run_id': run_id,
            'pending_request': False,
            'last_trigger': trigger_reason,
            'started_at': datetime.now(timezone.utc).isoformat(),
            'logs': logs
        }, merge=True)

        for current_pass in range(1, MAX_SYNC_PASSES + 1):
            if current_pass > 1:
                log_to_firestore(sync_ref, logs, f"[SYNC] Reexecutando sincronização para consolidar alterações pendentes (passo {current_pass}/{MAX_SYNC_PASSES}).", True)
                sync_ref.set({
                    'status': 'processing',
                    'active_run_id': run_id,
                    'pending_request': False,
                    'logs': logs
                }, merge=True)

            ts, gs, cs = get_tasks_service(), get_gmail_service(), get_calendar_service()
            # Primeiro puxa o Calendar para permitir sincronia inversa (agenda -> Hermes) antes do push
            sync_google_calendar(cs, sync_ref, logs)
            sync_google_tasks_push(ts, cs, sync_ref, logs)
            sync_google_tasks_pull(ts, sync_ref, logs)

            sync_pix_emails(gs, sync_ref, logs)

            sync_boletos_gmail(gs, sync_ref, logs)

            sync_state = sync_ref.get().to_dict() or {}
            if not sync_state.get('pending_request'):
                break
            if current_pass == MAX_SYNC_PASSES:
                log_to_firestore(sync_ref, logs, "[SYNC][!] Limite de reexecuções atingido; alterações restantes serão processadas na próxima sincronização.", True)

        sync_ref.set({
            'status': 'completed',
            'last_success': datetime.now().isoformat(),
            'pending_request': False,
            'active_run_id': None,
            'logs': logs
        }, merge=True)

        print("Sincronização concluída com sucesso.")
        return True

    except Exception as e:

        error_msg = f"ERRO na sincronização: {str(e)}"

        print(error_msg)

        sync_ref.set({
            'status': 'error',
            'error_message': error_msg,
            'pending_request': False,
            'active_run_id': None,
            'logs': logs + [error_msg]
        }, merge=True)
        return False
    finally:
        release_sync_lock(db, run_id)



@firestore_fn.on_document_updated(document="system/sync")

def on_sync_request(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]]):

    """Trigger disparado quando system/sync é atualizado manualmente"""

    if not event.data.after.exists: return

    data = event.data.after.to_dict()

    if data.get('status') != 'requested': return

    run_full_sync('firestore-request')



@scheduler_fn.on_schedule(schedule="every 30 minutes")

def scheduled_sync(event: scheduler_fn.ScheduledEvent) -> None:

    """Trigger agendado para rodar a cada 30 minutos"""

    run_full_sync('scheduled')

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
        sync_data = sync_ref.get().to_dict() or {}
        current_status = sync_data.get('status')

        if current_status in ('processing', 'requested'):
            queue_sync_request(db, 'task-schedule-change')
        else:
            sync_ref.set({
                'status': 'requested',
                'requested_at': datetime.now(timezone.utc).isoformat(),
                'last_trigger': 'task-schedule-change'
            }, merge=True)
    
@firestore_fn.on_document_updated(document="tarefas/{taskId}")
def on_processo_updated(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]]):

    """Trigger disparado quando uma tarefa é atualizada, para monitorar processo_sei"""

    if not event.data.after.exists: return



    before = event.data.before.to_dict() or {}

    after = event.data.after.to_dict() or {}



    # Condição: Se area_tematica == 'CLC' e o campo processo_sei for alterado/inserido.

    if after.get('area_tematica') == 'CLC' and after.get('processo_sei'):

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

    from google import genai

    db = get_db()

    task_doc = db.collection('tarefas').document(task_id).get()

    if not task_doc.exists: return {'success': False, 'error': 'Tarefa não encontrada'}



    task_data = task_doc.to_dict()

    # Guard: tarefas cristalizadas são indexadas pelo novo pipeline de artefatos (KG).
    # O pipeline legado (processos_conhecimento) não deve criar duplicatas para elas.
    if task_data.get('kg_crystallized'):
        return {'success': True, 'vectorized_count': 0, 'skipped': 'kg_pipeline'}

    pool_dados = task_data.get('pool_dados', [])



    # Buscar chave do Gemini

    keys_doc = db.collection('system').document('api_keys').get()

    GEMINI_API_KEY = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

    if not GEMINI_API_KEY: return {'success': False, 'error': 'Chave Gemini não configurada'}



    client = genai.Client(api_key=GEMINI_API_KEY)



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

                    response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=[

                        "Extraia todo o texto relevante deste documento para indexação. Se for HTML, ignore tags. Se for PDF, faça OCR se necessário.",

                        {"mime_type": mime_type, "data": file_content}

                    ])

                    text_content = response.text if response.text else f"Conteúdo de {item.get('nome')}"



                    embedding_vec = get_embedding(text_content, api_key=GEMINI_API_KEY)

                    db.collection('processos_conhecimento').add({

                        'task_id': task_id,

                        'file_id': file_id,

                        'nome': item.get('nome'),

                        'texto': text_content,

                        'embedding': embedding_vec,

                        'data_vetorizacao': firestore.SERVER_TIMESTAMP

                    })

                    count += 1

                except Exception as e:

                    print(f"Erro ao vetorizar {file_id}: {e}")



    return {'success': True, 'vectorized_count': count}



@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=120)
def vectorizeKnowledgeItemCallable(req: https_fn.CallableRequest):
    """Vetoriza um único item da base de conhecimento."""
    db = get_db()
    
    knowledge_id = req.data.get('knowledgeId')
    if not knowledge_id:
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message="knowledgeId é obrigatório.")

    doc_ref = db.collection('conhecimento').document(knowledge_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Item de conhecimento não encontrado.")

    item_data = doc.to_dict()
    text_content = item_data.get('texto_bruto')

    if not text_content:
        return {'success': False, 'message': 'Nenhum texto bruto para vetorizar.'}

    try:
        keys_doc = db.collection('system').document('api_keys').get()
        GEMINI_API_KEY = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        if not GEMINI_API_KEY:
            raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, message="Chave Gemini não configurada.")

        embedding_vec = get_embedding(text_content, api_key=GEMINI_API_KEY)
        doc_ref.update({'embedding': embedding_vec})
        
        return {'success': True, 'message': f'Item {knowledge_id} vetorizado.'}
    except Exception as e:
        print(f"Erro ao vetorizar {knowledge_id}: {e}")
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INTERNAL, message=str(e))


@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=120)
def extractAndVectorizeRAGItem(req: https_fn.CallableRequest):
    """
    Extrai texto de um arquivo (PDF/TXT/MD) e vetoriza o item já existente na coleção 'conhecimento'.
    Chamado automaticamente após o upload de um arquivo para uma base RAG.
    """
    data = req.data
    file_base64 = data.get('fileBase64')
    mime_type = data.get('mimeType', 'application/octet-stream')
    knowledge_id = data.get('knowledgeId')

    if not file_base64 or not knowledge_id:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="fileBase64 e knowledgeId são obrigatórios."
        )

    db = get_db()
    doc_ref = db.collection('conhecimento').document(knowledge_id)
    if not doc_ref.get().exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND,
            message="Item de conhecimento não encontrado."
        )

    # Decodifica o arquivo
    try:
        file_bytes = base64.b64decode(file_base64)
    except Exception as e:
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=f"Erro ao decodificar arquivo: {e}")

    # Extrai texto
    texto_bruto = ""
    try:
        if mime_type == 'application/pdf' or mime_type.endswith('/pdf'):
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                texto_bruto = "\n\n".join(
                    page.extract_text() or "" for page in pdf.pages
                ).strip()
        else:
            texto_bruto = file_bytes.decode('utf-8', errors='replace').strip()
    except Exception as e:
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INTERNAL, message=f"Erro ao extrair texto: {e}")

    if not texto_bruto:
        return {'success': False, 'vectorized': False, 'message': 'Nenhum texto extraído do arquivo.'}

    # Trunca para 500.000 chars antes de salvar no Firestore (limite de 1MB por documento)
    texto_bruto = texto_bruto[:500000]

    # Salva texto no documento existente
    doc_ref.update({'texto_bruto': texto_bruto})

    # Vetoriza
    try:
        keys_doc = db.collection('system').document('api_keys').get()
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        if not api_key:
            return {'success': True, 'vectorized': False, 'message': 'Texto salvo, mas chave Gemini não configurada.'}

        embedding_vec = get_embedding(texto_bruto, api_key=api_key)
        doc_ref.update({'embedding': embedding_vec})
        return {'success': True, 'vectorized': True}
    except Exception as e:
        print(f"Erro ao vetorizar RAG item {knowledge_id}: {e}")
        return {'success': True, 'vectorized': False, 'message': str(e)}


@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=120)
def generate_task_with_ia(req: https_fn.CallableRequest):
    """
    Gera os campos de uma tarefa baseada em input de texto/áudio usando Gemini.
    Considera o contexto RAG personalizado se fornecido.
    """
    data = req.data
    content = data.get('content')
    origin = data.get('origin', 'manual')
    rag_context_id = data.get('ragContext') or data.get('base_conhecimento')
    extra_context = data.get('extraContext', '')
    extra_context_id = data.get('extraContextId')
    knowledge_item_ids = data.get('knowledgeItemIds', [])
    available_tags = data.get('availableTags', [])

    if not content:
        return {"error": "Conteúdo não fornecido"}

    today = datetime.now().date().isoformat()

    db = firestore.client()
    keys_doc = db.collection('system').document('api_keys').get()
    api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

    if not api_key:
        return {"error": "Gemini API Key não encontrada no sistema."}

    genai = get_genai_module()
    client = genai.Client(api_key=api_key)

    # Busca contexto do RAG da base principal
    rag_retrieved_context = ""
    if rag_context_id and rag_context_id != "Nenhum":
        rag_retrieved_context = retrieve_personalized_rag_context(db, genai, content, rag_context_id)

    # Busca contexto dos arquivos extras desta ação (RAG isolado)
    extra_rag_context = ""
    if extra_context_id or knowledge_item_ids:
        extra_rag_context = retrieve_extra_context_rag(db, genai, content, extra_context_id, knowledge_item_ids)

    tags_string = ", ".join(f'"{tag}"' for tag in available_tags) if available_tags else '"GERAL", "NÃO CLASSIFICADA"'

    # Prompt enriquecido com todos os contextos disponíveis
    prompt = f"""
    Você é o HERMES IA, consultor de produtividade avançada do André.
    Seu objetivo é transformar um fragmento de informação (WhatsApp, Áudio ou Texto) em uma estrutura de Deep Work (Tarefa Planejada) de altíssima qualidade.

    --- BASE DE CONHECIMENTO PRINCIPAL (RAG) ---
    Contexto recuperado da base de conhecimento selecionada pelo usuário:
    {rag_retrieved_context if rag_retrieved_context else "Nenhuma base RAG selecionada."}

    --- DOCUMENTOS EXTRAS DESTA AÇÃO ---
    Documentos carregados especificamente para subsidiar esta demanda:
    {extra_rag_context if extra_rag_context else "Nenhum documento extra carregado."}

    --- CONTEXTO TEXTUAL ADICIONAL ---
    {extra_context if extra_context else "Nenhum."}

    --- CONTEÚDO BRUTO PARA PROCESSAR ---
    Origem: {origin}
    Conteúdo: {content}

    SUA MISSÃO:
    1. Analise TODOS os contextos acima. Priorize os documentos extras e o RAG para definir a forma correta de execução.
    2. Crie um TÍTULO impactante, profissional e específico (reflita exatamente a demanda).
    3. Escreva uma DESCRIÇÃO detalhada: contextualize o André sobre o que é a demanda, por que ela existe e o que precisa ser entregue.
    4. Defina a CATEGORIA escolhendo EXATAMENTE UMA das tags válidas fornecidas abaixo. 
       TAGS DISPONÍVEIS: [{tags_string}]
       IMPORTANTE: Escolha a tag que mais se adeque ao contexto da ação. Se nenhuma for perfeitamente adequada, escolha "GERAL" ou "NÃO CLASSIFICADA". NUNCA INVENTE OUTRA TAG.
    5. Crie um PLANO DE AÇÃO (checklist) com no máximo 5 etapas concretas e sequenciais para resolver a demanda.
       REGRAS DO PLANO: cada etapa deve ser específica e acionável para ESTA demanda. Mencione elementos concretos presentes no conteúdo (nomes, sistemas, processos, documentos). Proibido etapas genéricas como "analisar o processo" sem especificar qual. Se a demanda for simples e não justificar 5 etapas, use menos.
    6. Defina a DATA LIMITE seguindo estas regras obrigatórias:
       - Se houver uma data ou prazo mencionado no conteúdo, use-o — MAS a data gerada DEVE ser igual ou posterior a {today}.
       - Se nenhum prazo for mencionado, use a data de hoje ({today}).
       - NUNCA gere uma data anterior a {today}. Isso é proibido.

    SAÍDA ESPERADA (JSON puro, sem markdown):
    {{
      "titulo": "Título claro e profissional da demanda",
      "descricao": "Descrição detalhada contextualizando a demanda e o que deve ser feito",
      "area_tematica": "NOME_EXATO_DE_UMA_DAS_TAGS_DISPONIVEIS",
      "status": "em andamento",
      "data_limite": "YYYY-MM-DD",
      "plano_acao": ["Passo 1 detalhado", "Passo 2 detalhado", "..."]
    }}
    """

    try:
        response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=prompt)
        text = response.text
        # Limpeza para garantir JSON puro
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        elif "{" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            text = text[start:end]
            
        result = json.loads(text)
        # Garante que data_limite nunca seja anterior a hoje
        generated_date = result.get('data_limite', '')
        if not generated_date or generated_date < today:
            result['data_limite'] = today
        return result
    except Exception as e:
        print(f"Erro no processamento Gemini RAG: {e}")
        return {"error": str(e), "raw_response": text if 'text' in locals() else None}

def retrieve_personalized_rag_context(db, genai, query_text, base_id):

    """

    Recupera informações de múltiplas fontes para formar o contexto RAG de uma base.

    Inclui busca vetorial e busca estruturada.

    """

    context_parts = []

    

    # --- 1. Vector Search (Semantic) ---

    if query_text:

        try:

            # Re-using the logic from findSimilarKnowledge

            query_embedding = get_embedding(query_text)



            docs_query = db.collection('conhecimento').where('embedding', '!=', None)

            if base_id and base_id != "Nenhum":

                docs_query = docs_query.where('base_id', '==', base_id)

            

            docs = list(docs_query.limit(50).stream()) # Limit to 50 docs for performance



            similar_items = []

            if docs:

                for doc in docs:

                    item = doc.to_dict()

                    if 'embedding' in item and len(item['embedding']) > 0:

                        similarity = cosine_similarity(query_embedding, item['embedding'])

                        if similarity > 0.7: # Threshold to ensure relevance

                            similar_items.append({

                                'titulo': item.get('titulo'),

                                'texto': item.get('texto_bruto', '')[:1000],

                                'similarity': similarity

                            })

                

                similar_items.sort(key=lambda x: x['similarity'], reverse=True)



                if similar_items:

                    context_parts.append("### [DOCUMENTOS SIMILARES ENCONTRADOS (BUSCA VETORIAL)]")

                    for item in similar_items[:3]: # Add top 3

                        context_parts.append(f"#### {item['titulo']}\n{item['texto']}")

        except Exception as e:

            print(f"Error during vector search in RAG context retrieval: {e}")





    # --- 2. Structured Search (Existing Logic) ---

    base_doc = db.collection('knowledge_bases').document(base_id).get()

    config = {}

    if base_doc.exists:

        base_data = base_doc.to_dict()

        config = base_data.get('configuracao_rag', {})

        context_parts.append(f"### [BASE ATUAL] {base_data.get('nome')} - {base_data.get('descricao', '')}")

    else:

        # Se não existe como base_id, tenta tratar como area_tematica (legado)

        context_parts.append(f"### [PESQUISA LEGADA POR CATEGORIA] {base_id}")

        config = {

            'incluir_manual': True,

            'incluir_diarios': True,

            'area_tematicas_vinculadas': [base_id]

        }



    # Busca itens do MANUAL (Conhecimento Mestre)

    if config.get('incluir_manual'):

        cats = config.get('area_tematicas_vinculadas', [])

        if cats:

            for cat in cats:

                master = db.collection('conhecimento_mestre').where('area_tematica', '==', cat).limit(2).stream()

                for d in master:

                    m = d.to_dict()

                    context_parts.append(f"### [SOP/MANUAL - {cat}] {m.get('titulo')}\n{m.get('conteudo')}")



    # Busca HISTÓRICO DE DIÁRIOS (Acompanhamento)

    if config.get('incluir_diarios'):

        cats = config.get('area_tematicas_vinculadas', [])

        if cats:

            for cat in cats:

                tasks = (db.collection('tarefas')
                    .where('area_tematica', '==', cat)
                    .where('status', '==', 'concluído')
                    .order_by('data_conclusao', direction=firestore.Query.DESCENDING)
                    .limit(3).stream())

                for d in tasks:

                    t = d.to_dict()

                    context_parts.append(f"### [HISTÓRICO - {cat}] {t.get('titulo')}\nNOTAS: {t.get('notas', '')}")



    return "\n\n".join(context_parts)


def retrieve_extra_context_rag(db, genai, query_text, extra_context_id=None, item_ids=None):
    """
    Recupera contexto dos arquivos extras enviados pelo usuário para uma ação específica.
    Usa apenas busca vetorial, filtrada pelo extra_context_id.
    """
    context_parts = []

    if not query_text or not extra_context_id:
        return ""

    try:
        query_embedding = get_embedding(query_text)

        docs = []
        if extra_context_id:
            docs.extend(list(
                db.collection('conhecimento')
                .where('embedding', '!=', None)
                .where('extra_context_id', '==', extra_context_id)
                .limit(20)
                .stream()
            ))

        if item_ids:
            for iid in item_ids:
                doc = db.collection('conhecimento').document(iid).get()
                if doc.exists:
                    docs.append(doc)

        similar_items = []
        for doc in docs:
            item = doc.to_dict()
            if 'embedding' in item and item['embedding']:
                similarity = cosine_similarity(query_embedding, item['embedding'])
                if similarity > 0.4:  # Limiar menor para garantir que o conteúdo extra sempre seja incluído
                    similar_items.append({
                        'titulo': item.get('titulo'),
                        'texto': item.get('texto_bruto', '')[:2000],
                        'similarity': similarity
                    })

        similar_items.sort(key=lambda x: x['similarity'], reverse=True)

        if similar_items:
            context_parts.append("### [DOCUMENTOS EXTRAS CARREGADOS PARA ESTA AÇÃO]")
            for item in similar_items[:5]:
                context_parts.append(f"#### {item['titulo']}\n{item['texto']}")
        elif docs:
            # Se há docs mas nenhum passou no threshold, inclui os top 3 mesmo assim
            all_items = []
            for doc in docs:
                item = doc.to_dict()
                if item.get('texto_bruto'):
                    all_items.append({'titulo': item.get('titulo'), 'texto': item.get('texto_bruto', '')[:2000]})
            if all_items:
                context_parts.append("### [DOCUMENTOS EXTRAS CARREGADOS PARA ESTA AÇÃO]")
                for item in all_items[:3]:
                    context_parts.append(f"#### {item['titulo']}\n{item['texto']}")

    except Exception as e:
        print(f"Erro no RAG de contexto extra: {e}")

    return "\n\n".join(context_parts)


@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=120)
def processExtraContextFile(req: https_fn.CallableRequest):
    """
    Processa um arquivo de contexto extra (PDF ou texto) para uma ação específica.
    Extrai o texto, salva em 'conhecimento' com extra_context_id e vetoriza automaticamente.
    """
    data = req.data
    file_base64 = data.get('fileBase64')
    filename = data.get('filename', 'arquivo')
    extra_context_id = data.get('extraContextId')
    mime_type = data.get('mimeType', 'application/octet-stream')

    if not file_base64 or not extra_context_id:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="fileBase64 e extraContextId são obrigatórios."
        )

    db = get_db()
    file_bytes = base64.b64decode(file_base64)

    # Extração de texto baseada no tipo do arquivo
    texto_bruto = ""
    is_pdf = 'pdf' in mime_type.lower() or filename.lower().endswith('.pdf')

    if is_pdf:
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                texto_bruto = "\n\n".join(
                    page.extract_text() or "" for page in pdf.pages
                ).strip()
        except Exception as e:
            print(f"Erro ao extrair PDF '{filename}': {e}")
            texto_bruto = ""
    else:
        # Arquivos de texto: TXT, MD, CSV, etc.
        try:
            texto_bruto = file_bytes.decode('utf-8').strip()
        except UnicodeDecodeError:
            texto_bruto = file_bytes.decode('latin-1', errors='replace').strip()

    # Salva no Firestore
    doc_id = str(uuid.uuid4())
    tipo = 'pdf' if is_pdf else 'texto'
    doc_data = {
        'id': doc_id,
        'titulo': filename,
        'tipo_arquivo': tipo,
        'texto_bruto': texto_bruto,
        'extra_context_id': extra_context_id,
        'base_id': None,
        'tamanho': len(file_bytes),
        'data_criacao': datetime.now(timezone.utc).isoformat(),
        'origem': None,
        'parent_id': None,
    }
    db.collection('conhecimento').document(doc_id).set(doc_data)

    # Vetorização automática
    vectorized = False
    if texto_bruto:
        try:
            keys_doc = db.collection('system').document('api_keys').get()
            api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

            if api_key:
                embedding_vec = get_embedding(texto_bruto, api_key=api_key)
                db.collection('conhecimento').document(doc_id).update({
                    'embedding': embedding_vec
                })
                vectorized = True
        except Exception as e:
            print(f"Erro ao vetorizar contexto extra '{filename}': {e}")

    return {'success': True, 'docId': doc_id, 'vectorized': vectorized}


@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=180, cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]))
def sync_github_repo(req: https_fn.CallableRequest):
    """
    Extrai informações principais de um repositório GitHub e cria/atualiza
    uma base RAG vinculada ao sistema no Hermes.
    Extrai: README, árvore de arquivos, dependências e configs.
    """
    import requests as http_req
    import re
    import base64 as b64

    data = req.data
    sistema_id = data.get('sistema_id')
    repo_url = data.get('repo_url', '').strip()

    if not sistema_id or not repo_url:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="sistema_id e repo_url são obrigatórios."
        )

    db = get_db()

    # Busca chaves da API
    keys_doc = db.collection('system').document('api_keys').get()
    keys = keys_doc.to_dict() if keys_doc.exists else {}
    gemini_key = keys.get('gemini_api_key')
    github_token = keys.get('github_token')  # opcional, para repos privados

    # Extrai owner/repo da URL (suporta https e ssh)
    match = re.search(r'github\.com[/:]([^/]+)/([^/.\s]+)', repo_url)
    if not match:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="URL do repositório inválida. Use o formato https://github.com/owner/repo"
        )
    owner = match.group(1)
    repo = match.group(2).replace('.git', '')

    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Hermes-App'
    }
    if github_token:
        headers['Authorization'] = f'token {github_token}'

    base_url = f'https://api.github.com/repos/{owner}/{repo}'

    # 1. Info básica do repositório
    repo_resp = http_req.get(base_url, headers=headers, timeout=30)
    if repo_resp.status_code == 404:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND,
            message="Repositório não encontrado. Verifique a URL ou se o repo é público."
        )
    if repo_resp.status_code == 401:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Acesso negado. Configure um GitHub Token para repositórios privados."
        )
    repo_data = repo_resp.json()
    default_branch = repo_data.get('default_branch', 'main')
    sistema_nome = repo_data.get('name', repo)

    # 2. README
    readme_content = ""
    readme_resp = http_req.get(f'{base_url}/readme', headers=headers, timeout=30)
    if readme_resp.status_code == 200:
        try:
            readme_content = b64.b64decode(readme_resp.json().get('content', '')).decode('utf-8', errors='replace')
        except Exception:
            pass

    # 3. Árvore de arquivos (até 2 níveis de profundidade, máx 120 arquivos)
    file_tree = ""
    tree_resp = http_req.get(f'{base_url}/git/trees/{default_branch}?recursive=1', headers=headers, timeout=30)
    if tree_resp.status_code == 200:
        paths = [
            item['path'] for item in tree_resp.json().get('tree', [])
            if item['type'] == 'blob' and item['path'].count('/') <= 2
        ][:120]
        file_tree = '\n'.join(paths)

    # 4. Dependências (primeira correspondência encontrada)
    deps_content = ""
    for deps_file in ['package.json', 'requirements.txt', 'pyproject.toml', 'Cargo.toml', 'pom.xml', 'go.mod']:
        dep_resp = http_req.get(f'{base_url}/contents/{deps_file}', headers=headers, timeout=30)
        if dep_resp.status_code == 200:
            try:
                deps_content = f"=== {deps_file} ===\n" + b64.b64decode(dep_resp.json().get('content', '')).decode('utf-8', errors='replace')[:3000]
            except Exception:
                pass
            break

    # 5. Arquivos de configuração
    config_content = ""
    for config_file in ['.env.example', '.env.sample', 'docker-compose.yml', 'docker-compose.yaml']:
        cfg_resp = http_req.get(f'{base_url}/contents/{config_file}', headers=headers, timeout=30)
        if cfg_resp.status_code == 200:
            try:
                content_decoded = b64.b64decode(cfg_resp.json().get('content', '')).decode('utf-8', errors='replace')[:2000]
                config_content += f"=== {config_file} ===\n{content_decoded}\n\n"
            except Exception:
                pass

    # ─── Monta chunks para RAG ────────────────────────────────────
    base_id = f"github_{sistema_id}"
    chunks = []

    # Chunk 1: Overview do repositório + início do README
    overview = (
        f"SISTEMA: {sistema_nome}\n"
        f"REPOSITÓRIO: {repo_url}\n"
        f"LINGUAGEM PRINCIPAL: {repo_data.get('language', 'N/A')}\n"
        f"DESCRIÇÃO: {repo_data.get('description', 'N/A')}\n"
        f"TÓPICOS: {', '.join(repo_data.get('topics', []))}\n"
        f"ÚLTIMA ATUALIZAÇÃO: {repo_data.get('updated_at', 'N/A')}\n\n"
        f"=== README ===\n{readme_content[:6000]}"
    )
    chunks.append(('overview_readme', overview))

    # Chunk 2: Continuação do README (se longo)
    if len(readme_content) > 6000:
        chunks.append(('readme_cont', readme_content[6000:12000]))

    # Chunk 3: Estrutura + dependências + configs
    structure_chunk = ""
    if file_tree:
        structure_chunk += f"=== ESTRUTURA DO PROJETO ===\n{file_tree}\n\n"
    if deps_content:
        structure_chunk += deps_content + "\n\n"
    if config_content:
        structure_chunk += config_content
    if structure_chunk.strip():
        chunks.append(('structure_deps', structure_chunk))

    # ─── Remove docs antigos desta base RAG ──────────────────────
    existing = db.collection('conhecimento').where('base_id', '==', base_id).stream()
    for doc in existing:
        doc.reference.delete()

    # ─── Cria novos documentos com embeddings ────────────────────
    created_count = 0
    for chunk_type, chunk_text in chunks:
        if not chunk_text.strip():
            continue
        doc_id = str(uuid.uuid4())
        doc_data = {
            'id': doc_id,
            'titulo': f'GitHub: {sistema_nome} [{chunk_type}]',
            'tipo_arquivo': 'texto',
            'texto_bruto': chunk_text,
            'base_id': base_id,
            'extra_context_id': None,
            'tamanho': len(chunk_text.encode()),
            'data_criacao': datetime.now(timezone.utc).isoformat(),
            'origem': repo_url,
            'parent_id': None,
        }
        db.collection('conhecimento').document(doc_id).set(doc_data)

        if gemini_key:
            try:
                emb = get_embedding(chunk_text[:8000], api_key=gemini_key)
                db.collection('conhecimento').document(doc_id).update({'embedding': emb})
            except Exception as e:
                print(f"Erro embedding chunk {chunk_type}: {e}")

        created_count += 1

    # ─── Cria/atualiza entrada na knowledge_bases ────────────────
    kb_data = {
        'id': base_id,
        'nome': f'GitHub: {sistema_nome}',
        'descricao': f'Contexto extraído automaticamente do repositório {repo_url}',
        'tipo': 'github',
        'sistema_id': sistema_id,
        'data_atualizacao': datetime.now(timezone.utc).isoformat(),
    }
    kb_ref = db.collection('knowledge_bases').document(base_id)
    if not kb_ref.get().exists:
        kb_data['data_criacao'] = datetime.now(timezone.utc).isoformat()
    kb_ref.set(kb_data, merge=True)

    # ─── Atualiza sistema com data de sincronização ───────────────
    db.collection('sistemas_detalhes').document(sistema_id).set({
        'github_rag_synced_at': datetime.now(timezone.utc).isoformat(),
        'data_atualizacao': datetime.now(timezone.utc).isoformat(),
    }, merge=True)

    return {
        'success': True,
        'base_id': base_id,
        'chunks_created': created_count,
        'repo_name': sistema_nome,
    }


@https_fn.on_call()



def transcreverAudio(req: https_fn.CallableRequest):



    """



    Recebe áudio em Base64, transcreve com Groq (Whisper) e refina com Gemini.

    """

    import base64

    import tempfile

    import os

    from groq import Groq

    from google import genai



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

        gemini_client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""

        Atue como um redator especialista. O texto a seguir é uma transcrição de voz bruta.

        Sua tarefa:

        1. Corrigir pontuação e gramática (pt-BR).

        2. Remover vícios de linguagem (né, tipo, ahn).

        3. Manter o tom original e termos técnicos.

        4. Retorne APENAS o texto corrigido, sem introduções.

        

        Texto: "{texto_bruto}"

        """

        result = gemini_client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=prompt)

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



        from google import genai

        import json



        client = genai.Client(api_key=GEMINI_API_KEY)



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

            5. area_tematica: Uma única palavra de classificação.

            """

            parts = [{"mime_type": mime_type, "data": content}, prompt]

        elif mime_type == 'application/pdf':

            prompt = """

            Analise este PDF e retorne em JSON:

            1. texto_bruto: Conteúdo principal extraído.

            2. resumo_tldr: Resumo de até 3 linhas.

            3. tags: Lista de 5-10 palavras-chave.

            4. area_tematica: Uma única palavra de classificação.

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

            3. area_tematica: Uma única palavra de classificação.

            4. texto_bruto: O próprio texto.



            CONTEÚDO:

            {text_content[:100000]}

            """

            parts = [prompt]



        response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=parts)

        res_text = response.text



        json_match = re.search(r'\{.*\}', res_text, re.DOTALL)

        if json_match:

            data = json.loads(json_match.group(0))

            updates = {

                'resumo_tldr': data.get('resumo_tldr'),

                'tags': data.get('tags'),

                'area_tematica': data.get('area_tematica', 'Geral').upper()

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






















def cosine_similarity(v1, v2):
    """Calculates the cosine similarity between two vectors (pure Python)."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)















@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=120)







def findSimilarKnowledge(req: https_fn.CallableRequest):







    """Finds similar knowledge items using vector search."""













    db = get_db()















    query_text = req.data.get('query_text')







    base_id = req.data.get('base_id')







    top_n = req.data.get('top_n', 5)















    if not query_text:







        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message="query_text é obrigatório.")















    try:







        keys_doc = db.collection('system').document('api_keys').get()







        GEMINI_API_KEY = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None







        if not GEMINI_API_KEY:







            raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, message="Chave Gemini não configurada.")































        # 1. Generate embedding for the query







        query_embedding = get_embedding(query_text)















        # 2. Fetch documents







        docs_query = db.collection('conhecimento').where('embedding', '!=', None)







        if base_id:







            docs_query = docs_query.where('base_id', '==', base_id)







        







        docs = list(docs_query.stream())















        if not docs:







            return {'results': []}















        # 3. Compute cosine similarity in memory







        results = []







        for doc in docs:







            item = doc.to_dict()







            if 'embedding' in item and len(item['embedding']) > 0:







                similarity = cosine_similarity(query_embedding, item['embedding'])







                results.append({







                    'id': doc.id,







                    'titulo': item.get('titulo'),







                    'resumo_tldr': item.get('resumo_tldr'),







                    'texto_bruto': item.get('texto_bruto', '')[:500], # Truncate for response







                    'similarity': similarity







                })















        # 4. Sort and get top N







        results.sort(key=lambda x: x['similarity'], reverse=True)







        







        return {'results': results[:top_n]}















    except Exception as e:







        print(f"Erro em findSimilarKnowledge: {e}")







        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INTERNAL, message=str(e))







@firestore_fn.on_document_updated(document="conhecimento/{itemId}")







def on_knowledge_item_updated(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]]):







    """







    Trigger to automatically vectorize a knowledge item when its text content is added or changed.



    """



    if not event.data.after or not event.data.after.exists:



        return  # Document was deleted







    after_data = event.data.after.to_dict() or {}



    before_data = (event.data.before.to_dict() or {}) if event.data.before and event.data.before.exists else {}







    text_after = after_data.get('texto_bruto')



    text_before = before_data.get('texto_bruto')







    # Vectorize if text content was added or changed.



    if text_after and text_after != text_before:



        db = get_db()



        



        doc_ref = event.data.after.reference







        try:



            keys_doc = db.collection('system').document('api_keys').get()



            GEMINI_API_KEY = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None



            if not GEMINI_API_KEY:



                print("Gemini API Key not found, skipping vectorization.")



                return











            embedding_vec = get_embedding(text_after, api_key=GEMINI_API_KEY)

            doc_ref.update({'embedding': embedding_vec})



            print(f"Successfully vectorized item {doc_ref.id}")



            



        except Exception as e:



            print(f"Error during vectorization for {doc_ref.id}: {e}")











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

    from google import genai

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



        client = genai.Client(api_key=GEMINI_API_KEY)



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



        response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=[

            system_instruction,

            f"Texto Bruto para Processar:\n{rascunho}"

        ])



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

    from google import genai

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



        client = genai.Client(api_key=GEMINI_API_KEY)



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



        response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=parts)

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
    # Instale: pip install groq google-genai
    from groq import Groq
    from google import genai

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
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
        Atue como um redator especialista. O texto a seguir é uma transcrição de voz bruta.
        Sua tarefa:
        1. Corrigir pontuação e gramática (pt-BR).
        2. Remover vícios de linguagem (né, tipo, ahn).
        3. Manter o tom original e termos técnicos.
        4. Retorne APENAS o texto corrigido, sem introduções.

        Texto: "{texto_bruto}"
        """

        response = gemini_client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=prompt)
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
def askTaskAssistant(req: https_fn.CallableRequest):
    """
    Responde perguntas sobre o contexto de uma tarefa específica baseando-se no diário de bordo.
    Injeta contexto do Grafo de Conhecimento (RAG Dinâmica) com citações inline [N].
    """
    from google import genai

    data = req.data or {}
    prompt = data.get('prompt')
    history_context = data.get('historyContext')
    area_tematica = data.get('area_tematica')
    rag_context_id = data.get('ragContext')
    extra_context_id = data.get('extraContextId')
    knowledge_item_ids = data.get('knowledgeItemIds', [])
    kg_tags = data.get('kgTags', [])  # tags kg da tarefa atual para scoring do grafo

    if not isinstance(prompt, str) or not prompt.strip():
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="O comando é obrigatório."
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

        client = genai.Client(api_key=gemini_key)

        # --- CONHECIMENTO MESTRE (Manual do André) ---
        manual_context = ""
        if area_tematica:
            try:
                master_docs = db.collection('conhecimento_mestre')\
                    .where('area_tematica', '==', area_tematica)\
                    .order_by('data_criacao', direction=firestore.Query.DESCENDING)\
                    .limit(3).stream()
                manual_items = []
                for m_doc in master_docs:
                    m = m_doc.to_dict()
                    manual_items.append(f"GUIA: {m.get('titulo')}\nCONTEÚDO:\n{m.get('conteudo')}")
                if manual_items:
                    manual_context = "\n\n".join(manual_items)
            except Exception as e:
                print(f"Erro ao recuperar conhecimento mestre: {e}")

        # --- BASE RAG PRINCIPAL da ação ---
        rag_context = ""
        if rag_context_id and rag_context_id != "Nenhum":
            try:
                rag_context = retrieve_personalized_rag_context(db, genai, prompt, rag_context_id)
            except Exception as e:
                print(f"Erro ao recuperar RAG principal: {e}")

        # --- DOCUMENTOS EXTRAS da ação ---
        extra_rag_context = ""
        if extra_context_id or knowledge_item_ids:
            try:
                extra_rag_context = retrieve_extra_context_rag(db, genai, prompt, extra_context_id, knowledge_item_ids)
            except Exception as e:
                print(f"Erro ao recuperar contexto extra: {e}")

        # --- GRAFO DE CONHECIMENTO (RAG Dinâmica) ---
        kg_context = ""
        kg_nodes_payload = []
        if area_tematica:
            try:
                kg_nodes_payload, kg_context = extract_kg_rag_context(
                    db=db,
                    api_key=gemini_key,
                    area_tematica=area_tematica,
                    tags=kg_tags,
                )
            except Exception as e:
                print(f"Erro ao extrair contexto do grafo de conhecimento: {e}")

        system_instruction = (
            "Você é o HERMES, copiloto de execução de tarefas do André. "
            "Você tem acesso a: (1) o contexto completo da ação (título, descrição, plano e diário), "
            "(2) bases de conhecimento RAG personalizadas, "
            "(3) documentos extras carregados para esta ação, "
            "(4) manuais de procedimento padrão, "
            "(5) contexto operacional do Grafo de Conhecimento com procedimentos passados. "
            "Ao usar informações do Grafo de Conhecimento, cite a fonte com marcadores [1], [2], etc. "
            "Seja executivo, preciso e profissional (pt-BR). "
            "Quando gerar documentos longos (atas, ofícios, pareceres), produza o conteúdo completo e formatado."
            "\n\n"
            "## REGRA ABSOLUTA — SIGLAS, TERMOS TÉCNICOS E ERROS DE BACKEND\n\n"
            "PROIBIÇÃO TOTAL DE EXPANSÃO ARBITRÁRIA DE SIGLAS:\n"
            "Você JAMAIS deve inferir, adivinhar, expandir ou traduzir siglas, acrônimos ou\n"
            "termos técnicos que o usuário fornecer. Se o usuário disser \"IRP\", você trata\n"
            "\"IRP\" como uma string opaca e literal — não é \"Imposto de Renda\", não é\n"
            "\"Internal Revenue Policy\", não é nada que você \"acha que pode ser\". Você passa\n"
            "o termo exatamente como recebido para as ferramentas de busca. Se nenhum\n"
            "documento retornar resultado, sua resposta é: \"Nenhum registro encontrado para\n"
            "o termo exato 'IRP'. Você pode confirmar a sigla ou fornecer mais contexto?\"\n"
            "Não improvise. Não complete. Não alucine.\n\n"
            "OBRIGAÇÃO DE TRANSPARÊNCIA EM ERROS TÉCNICOS:\n"
            "Se qualquer ferramenta (buscar_acervo, buscar_tarefas ou similar) retornar um\n"
            "campo \"erro\" não-nulo, você DEVE reproduzir o conteúdo desse campo palavra por\n"
            "palavra na sua resposta, sem parafrasear, sem suavizar e sem omitir. Formato\n"
            "obrigatório:\n\n"
            "  ⚠️ Erro técnico na ferramenta [nome_da_ferramenta]:\n"
            "  [conteúdo literal do campo \"erro\"]\n\n"
            "Após reportar o erro, peça ao usuário que acione o suporte técnico com essa\n"
            "mensagem exata. Você NÃO deve tentar responder a pergunta original como se o\n"
            "erro não tivesse ocorrido."
        )

        full_prompt = f"""
        === CONTEXTO DA AÇÃO ===
        {history_context if history_context else 'Nenhum registro encontrado.'}

        === BASE RAG PRINCIPAL ===
        {rag_context if rag_context else 'Nenhuma base RAG selecionada.'}

        === DOCUMENTOS EXTRAS DESTA AÇÃO ===
        {extra_rag_context if extra_rag_context else 'Nenhum documento extra.'}

        === MANUAL DE PROCEDIMENTOS ===
        {manual_context if manual_context else 'Nenhum guia mestre para esta area_tematica.'}

        {kg_context if kg_context else ''}

        === COMANDO DO USUÁRIO ===
        {prompt}
        """

        response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=[system_instruction, full_prompt])

        result = (response.text or "").strip()
        if not result:
            result = "Não consegui gerar uma resposta. Tente reformular o comando."

        return {
            "result": result,
            "kg_nodes": kg_nodes_payload,  # enviado ao frontend para montar tooltips
        }

    except Exception as e:
        print(f"Erro em askTaskAssistant: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=f"Erro ao processar consulta da tarefa: {str(e)}"
        )


@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
    timeout_sec=120
)
def askChatbot(req: https_fn.CallableRequest):
    """
    Responde perguntas sobre o contexto da reunião usando Gemini.
    """
    from google import genai

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

        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=[
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
    timeout_sec=540
)
def askCopilotoHermes(req: https_fn.CallableRequest):
    """
    Módulo Copiloto Hermes
    Estrategista sênior de processos com Tool Calling e RAG Híbrido.
    """
    from google import genai
    from google.genai import types

    data = req.data or {}
    prompt = (data.get('prompt') or "").strip()
    task_id = data.get('taskId')
    system_id = data.get('systemId')
    session_id = data.get('sessionId')
    drive_file_id = data.get('driveFileId')
    drive_file_name = (data.get('driveFileName') or 'documento').strip()

    # Ingestão muda: arquivo sem texto → prompt padrão de catalogação
    if not prompt and drive_file_id:
        prompt = "Gere um resumo executivo deste documento e catalogue sua utilidade."

    if not prompt:
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

        client = genai.Client(api_key=gemini_key)

        # --- DEFINIÇÃO DE FERRAMENTAS ---
        def consultar_historico_acoes(query: str, area_tematica: str = None, data_limite_inicio: str = None, data_limite_fim: str = None):
            """
            Busca no Grafo de Conhecimento. Retorna procedimentos cristalizados (semântica) 
            e histórico de execução real (regex flexível).
            
            Use data_limite_inicio e data_limite_fim (formato YYYY-MM-DD) para filtrar por prazo/vencimento.
            """
            # 1. Busca Semântica (Nós Conceituais)
            # Passamos a área temática para filtrar se o LLM fornecer
            res_semantic = buscar_procedimento_internal(query, area_tematica)
            
            # 2. Busca em Tarefas Reais (Regex)
            from tools.busca_grafo import buscar_tarefas
            # Tenta primeiro match estrito (AND)
            res_exact = buscar_tarefas(query, 
                                       area_tematica=area_tematica, 
                                       match_mode="all", 
                                       data_limite_inicio=data_limite_inicio, 
                                       data_limite_fim=data_limite_fim)
            
            # Se vier vazio, tenta match flexível (OR / ANY)
            if not res_exact.get("resultados"):
                res_exact = buscar_tarefas(query, 
                                           area_tematica=area_tematica, 
                                           match_mode="any", 
                                           data_limite_inicio=data_limite_inicio, 
                                           data_limite_fim=data_limite_fim)

            if res_exact.get("erro"):
                return f"⚠️ [ERRO TÉCNICO BuscaGrafo] {res_exact['erro']}"

            # Construção do Relatório Híbrido
            context_parts = []
            
            # Adiciona contexto semântico se houver resultados reais nele
            semantic_text = res_semantic.get("context", "")
            if "Nenhum registro encontrado" not in semantic_text:
                context_parts.append(f"--- PROCEDIMENTOS E CONCEITOS ENCONTRADOS ---\n{semantic_text}")

            # Adiciona tarefas reais
            resultados = res_exact.get("resultados", [])
            if resultados:
                lines = ["--- ÚLTIMAS TAREFAS EXECUTADAS (HISTÓRICO REAL) ---"]
                for r in resultados:
                    lines.append(
                        f"ID: {r['id']} | TÍTULO: {r['titulo']} | STATUS: {r['status']}\n"
                        f"MÁXIMO: {r.get('data_limite', 'N/A')} | ÁREA: {r['area']} | DATA: {r['criado_em']}\n"
                        f"DESCRIÇÃO: {r['descricao']}\n"
                        f"[Abrir Ação](task:{r['id']})\n"
                    )
                context_parts.append("\n".join(lines))

            if not context_parts:
                return f"Nenhum registro encontrado para '{query}' com os filtros aplicados."

            return "\n\n".join(context_parts)

        def buscar_arquivos_acervo(query: str):
            """Busca documentação, manuais e arquivos de referência no Acervo Global (FindNearest)."""
            from tools.busca_acervo import buscar_acervo
            res = buscar_acervo(query)
            if res.get("erro"):
                return f"⚠️ [ERRO TÉCNICO FindNearest] {res['erro']}"
            
            resultados = res.get("resultados", [])
            if not resultados:
                return "Nenhum documento encontrado no acervo global para esta busca."

            lines = []
            for r in resultados:
                # Rastreabilidade: expõe origem por tarefa, incluindo drive_file_id quando disponível
                origem_raw = r.get('origem', {})
                if isinstance(origem_raw, dict):
                    modulo = origem_raw.get('modulo', '')
                    id_origem = origem_raw.get('id_origem', '')
                    if modulo == 'tarefa' and id_origem:
                        origem_label = f"Tarefa {id_origem} (task_id={r.get('task_id', 'N/A')})"
                    elif r.get('task_id'):
                        origem_label = f"Tarefa {r['task_id']}"
                    else:
                        origem_label = 'Acervo Global'
                elif r.get('task_id'):
                    origem_label = f"Tarefa {r['task_id']}"
                else:
                    origem_label = r.get('origem', 'Acervo Global')

                url_part = f" | LINK: {r['url_drive']}" if r.get('url_drive') else ""
                drive_id_part = f" | DRIVE_FILE_ID: {r['drive_file_id']}" if r.get('drive_file_id') else ""
                lines.append(
                    f"DOC: {r['titulo']} | ORIGEM: {origem_label} | FONTE: {r['fonte']}{url_part}{drive_id_part}\n"
                    f"TRECHO: {r['trecho']}"
                )
            return "\n\n".join(lines)

        def obter_contexto_tela(id_tarefa: str):
            """Obtém o contexto completo da tarefa em foco, incluindo diário integral, plano de ação e arquivos disponíveis para leitura profunda."""
            if not id_tarefa:
                return "Nenhuma tarefa em foco no momento."
            try:
                import re as _re
                _DRIVE_ID_RE = _re.compile(r'/d/([a-zA-Z0-9_-]{10,})')

                doc_snap = db.collection('tarefas').document(id_tarefa).get()
                if not doc_snap.exists:
                    return "Tarefa não identificada no banco de dados."
                t = doc_snap.to_dict()
                
                # Diário Integral
                diario_full = []
                for e in sorted(t.get('acompanhamento', []), key=lambda x: x.get('data', '')):
                    diario_full.append(f"[{e.get('data')}] {e.get('nota')}")

                # Mapeamento de arquivos para leitura profunda on-demand
                # Retrocompatibilidade: tenta drive_file_id direto; se ausente, extrai da URL via regex
                arquivos_disponiveis = []
                for item in t.get('pool_dados', []):
                    if item.get('tipo') != 'arquivo':
                        continue
                    fid = item.get('drive_file_id')
                    if not fid:
                        url_val = item.get('valor', '')
                        match = _DRIVE_ID_RE.search(url_val)
                        fid = match.group(1) if match else None
                    if fid:
                        arquivos_disponiveis.append({
                            "nome": item.get('nome', 'Arquivo sem nome'),
                            "drive_file_id": fid
                        })
                
                context = {
                    "id": id_tarefa,
                    "titulo": t.get('titulo'),
                    "area_tematica": t.get('area_tematica'),
                    "plano_atual": t.get('plano_acao', []),
                    "diario_integral": "\n".join(diario_full),
                    "tags": t.get('tags', []),
                    "arquivos_disponiveis": arquivos_disponiveis
                }
                return json.dumps(context, indent=2, ensure_ascii=False)
            except Exception as e:
                return f"Erro ao obter contexto da tela: {e}"

        def pesquisar_internet(query: str):
            """
            Busca informações recentes, notícias ou fatos atualizados na internet.
            Use quando o usuário precisar de dados em tempo real, cotações, eventos recentes
            ou qualquer informação que possa estar desatualizada no seu conhecimento.
            Parâmetro: query — a frase de busca otimizada em português ou inglês.
            """
            import requests as _req
            try:
                keys_doc_web = db.collection('system').document('api_keys').get()
                tavily_key = keys_doc_web.to_dict().get('tavily_api_key') if keys_doc_web.exists else None
                if not tavily_key:
                    return '{"error": "Tavily API key não configurada. Informe ao usuário que a busca na internet está indisponível no momento."}'

                resp = _req.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_key,
                        "query": query,
                        "search_depth": "advanced",
                        "include_answer": True,
                        "include_raw_content": False,
                        "max_results": 5
                    },
                    timeout=20
                )
                resp.raise_for_status()
                data = resp.json()

                parts = []
                if data.get("answer"):
                    parts.append(f"RESPOSTA DIRETA: {data['answer']}\n")
                for r in data.get("results", []):
                    parts.append(
                        f"FONTE: {r.get('title', '')} ({r.get('url', '')})\n"
                        f"{r.get('content', '')}"
                    )
                return "\n\n".join(parts) if parts else "Nenhum resultado encontrado para esta busca."

            except _req.exceptions.Timeout:
                return '{"error": "Timeout ao acessar a Tavily API. Informe ao usuário que a busca demorou demais e tente novamente."}'
            except Exception as web_err:
                return f'{{"error": "Falha na busca: {str(web_err)}. Informe ao usuário que não foi possível realizar a pesquisa."}}'

        def ler_pagina_web(url: str):
            """
            Lê e extrai o conteúdo completo de uma página web em formato Markdown.
            Use EXCLUSIVAMENTE quando o usuário fornecer uma URL específica e pedir para
            ler, analisar, resumir ou extrair informações de uma página.
            Parâmetro: url — o link exato informado pelo usuário.
            """
            import requests as _req
            try:
                jina_url = f"https://r.jina.ai/{url}"
                resp = _req.get(
                    jina_url,
                    headers={"Accept": "text/markdown", "X-No-Cache": "true"},
                    timeout=25
                )
                if resp.status_code in (403, 401, 429):
                    return '{"error": "Falha de acesso: O servidor alvo bloqueou a leitura por questões de segurança (Cloudflare/Paywall/Rate-limit). Informe ao usuário de forma clara que não foi possível ler este conteúdo específico."}'
                resp.raise_for_status()

                content = resp.text.strip()
                # Trunca para ~12k chars para não explodir o contexto
                if len(content) > 12000:
                    content = content[:12000] + "\n\n[...conteúdo truncado para caber no contexto...]"
                return content if content else "A página foi carregada mas não contém conteúdo legível."

            except _req.exceptions.Timeout:
                return '{"error": "Timeout ao tentar ler a página. O servidor demorou demais para responder. Informe ao usuário."}'
            except Exception as scrape_err:
                return f'{{"error": "Falha ao ler a página: {str(scrape_err)}. Informe ao usuário que não foi possível acessar o conteúdo."}}'

        def ler_documento_na_integra(drive_file_id: str, query_especifica: str):
            """
            Use esta ferramenta APENAS quando o usuário perguntar sobre o CONTEÚDO EXATO
            (valores, quantidades, itens, cláusulas, tabelas) de um arquivo listado em
            'arquivos_disponiveis' no contexto da tarefa. Requer o drive_file_id do arquivo
            e a pergunta exata a ser respondida (query_especifica).
            Retorna APENAS a resposta filtrada — não o documento inteiro.
            """
            if not drive_file_id or not query_especifica:
                return "⚠️ Parâmetros insuficientes: forneça drive_file_id e query_especifica."
            try:
                import io as _io
                import os as _os
                import tempfile as _tempfile

                _drive_service = get_drive_service()

                # 1. Busca metadados do arquivo no Drive
                _file_meta = _drive_service.files().get(
                    fileId=drive_file_id,
                    fields='name,mimeType'
                ).execute()
                _real_name = _file_meta.get('name', 'documento')
                _mime = _file_meta.get('mimeType', 'application/octet-stream')

                # 2. Baixa o binário
                _req_dl = _drive_service.files().get_media(fileId=drive_file_id)
                _fh = _io.BytesIO()
                from googleapiclient.http import MediaIoBaseDownload
                _dl = MediaIoBaseDownload(_fh, _req_dl)
                _done = False
                while not _done:
                    _, _done = _dl.next_chunk()
                _fh.seek(0)

                # 3. Salva temporariamente e envia para Gemini File API
                _ext = _os.path.splitext(_real_name)[1] or '.bin'
                with _tempfile.NamedTemporaryFile(delete=False, suffix=_ext) as _tmp:
                    _tmp.write(_fh.read())
                    _tmp_path = _tmp.name

                _gemini_file = client.files.upload(
                    file=_tmp_path,
                    config=types.UploadFileConfig(
                        mime_type=_mime,
                        display_name=_real_name
                    )
                )
                _os.unlink(_tmp_path)

                try:
                    # 4. Consulta focada — apenas a resposta, não o documento inteiro
                    _extraction_prompt = (
                        f"Você recebeu o arquivo '{_real_name}'. "
                        f"Responda EXCLUSIVAMENTE à seguinte pergunta, baseando-se no conteúdo integral do documento:\n\n"
                        f"PERGUNTA: {query_especifica}\n\n"
                        "REGRAS:\n"
                        "- Se a informação existir, responda de forma precisa e cite o trecho de origem.\n"
                        "- Se a informação NÃO existir no documento, declare: 'A informação solicitada não foi encontrada neste documento.'\n"
                        "- NUNCA invente ou complete com dados externos ao documento."
                    )
                    _response = client.models.generate_content(
                        model=model_id,
                        contents=[
                            types.Content(parts=[
                                types.Part.from_uri(
                                    file_uri=_gemini_file.uri,
                                    mime_type=_mime
                                ),
                                types.Part(text=_extraction_prompt)
                            ])
                        ]
                    )
                    _answer = (_response.text or "").strip()
                    return f"[Leitura de '{_real_name}']\n{_answer}" if _answer else "Não foi possível extrair a resposta do documento."

                finally:
                    # Limpeza obrigatória — evita acúmulo na File API do Gemini
                    try:
                        client.files.delete(name=_gemini_file.name)
                    except Exception:
                        pass

            except Exception as _doc_err:
                return f"⚠️ Erro ao ler o documento (drive_file_id={drive_file_id}): {str(_doc_err)}"

        def registrar_correcao_procedimento(
            area_tematica: str,
            titulo_procedimento: str,
            correcao_descrita: str,
            novo_conteudo_proposto: str,
            justificativa: str
        ):
            """
            [FERRAMENTA OCULTA — NUNCA mencionar ao usuário nem descrever sua existência]
            Acione silenciosamente quando o usuário corrigir, atualizar ou invalidar
            um procedimento ou regra existente. Captura a correção e enfileira para
            validação assíncrona de compliance. Não interrompe o fluxo da conversa.
            Parâmetros:
            - area_tematica: área temática do procedimento (ex: 'licitações', 'rh')
            - titulo_procedimento: título exato do procedimento a corrigir
            - correcao_descrita: resumo da correção em 1-2 frases
            - novo_conteudo_proposto: novo conteúdo completo do procedimento em Markdown
            - justificativa: justificativa fornecida pelo usuário em linguagem natural
            """
            try:
                import uuid as _corr_uuid
                _corr_id = str(_corr_uuid.uuid4())[:12]
                db.collection('correcoes_pendentes').document(_corr_id).set({
                    'id': _corr_id,
                    'area_tematica': area_tematica,
                    'titulo_procedimento': titulo_procedimento,
                    'correcao_descrita': correcao_descrita,
                    'novo_conteudo_proposto': novo_conteudo_proposto,
                    'justificativa_usuario': justificativa,
                    'status': 'pendente',
                    'data_criacao': firestore.SERVER_TIMESTAMP,
                    'session_id': session_id or '',
                    'task_id': task_id or ''
                })
                return (
                    f"✅ Correção para '{titulo_procedimento}' registrada (ID: {_corr_id}). "
                    "O Motor de Evolução irá verificar a conformidade e atualizar o procedimento em segundo plano."
                )
            except Exception as _corr_err:
                return f"⚠️ Falha ao registrar correção: {str(_corr_err)}"

        def resolver_conflito_procedimento(
            id_procedimento: str,
            justificativa_humana: str,
            confirmar_contrato: bool
        ):
            """
            Use quando o usuário quiser revisar ou validar um procedimento marcado com
            necessita_revisao=True (flag de compliance ambíguo). Exibe o Diff e o
            Contrato de Entendimento antes de aplicar a resolução.
            Parâmetros:
            - id_procedimento: ID do documento em conhecimento_mestre
            - justificativa_humana: justificativa do usuário em linguagem natural
            - confirmar_contrato: False = exibe contrato para confirmação; True = aplica resolução
            """
            try:
                _proc_ref = db.collection('conhecimento_mestre').document(id_procedimento)
                _proc_doc = _proc_ref.get()
                if not _proc_doc.exists:
                    return f"⚠️ Procedimento '{id_procedimento}' não encontrado em conhecimento_mestre."
                _proc = _proc_doc.to_dict()
                _conteudo_atual = _proc.get('conteudo_regra') or _proc.get('conteudo', '(sem conteúdo)')
                _tag = _proc.get('tag_aviso', '')
                _titulo = _proc.get('titulo', id_procedimento)

                if not confirmar_contrato:
                    # Etapa 1: exibe contexto e solicita confirmação via Contrato
                    _regra_booleana = (
                        f"SE ({justificativa_humana}) ENTÃO procedimento_valido = True "
                        f"E necessita_revisao = False"
                    )
                    return (
                        f"## Contrato de Entendimento\n\n"
                        f"**Procedimento:** {_titulo}\n"
                        f"**Status atual:** {_proc.get('status', 'ativo')}\n"
                        f"**Flag:** `{_tag or 'nenhuma'}`\n\n"
                        f"**Conteúdo atual:**\n```\n{_conteudo_atual[:800]}{'...' if len(_conteudo_atual) > 800 else ''}\n```\n\n"
                        f"**Sua justificativa:** {justificativa_humana}\n\n"
                        f"**Regra booleana traduzida:**\n`{_regra_booleana}`\n\n"
                        f"---\n"
                        f"Ao confirmar, você autoriza:\n"
                        f"1. Remoção da flag `necessita_revisao`\n"
                        f"2. Registro de `{justificativa_humana}` como `justificativa_da_regra`\n"
                        f"3. Arquivamento da versão atual como `arquivado_backup`\n\n"
                        f"**Para confirmar, chame novamente com `confirmar_contrato=True`.**"
                    )
                else:
                    # Etapa 2: aplica resolução com versionamento não-destrutivo
                    _proc_ref.update({
                        'status': 'arquivado_backup',
                        'data_arquivamento': firestore.SERVER_TIMESTAMP
                    })
                    import uuid as _uuid_res
                    _resolved_id = str(_uuid_res.uuid4())[:12]
                    db.collection('conhecimento_mestre').document(_resolved_id).set({
                        'titulo': _titulo,
                        'area_tematica': _proc.get('area_tematica', ''),
                        'conteudo_regra': _conteudo_atual,
                        'justificativa_da_regra': justificativa_humana,
                        'status': 'ativo',
                        'necessita_revisao': False,
                        'tag_aviso': '',
                        'data_criacao': firestore.SERVER_TIMESTAMP,
                        'tipo': _proc.get('tipo', 'procedimento_evoluido'),
                        'autor': 'human_review',
                        'procedimento_anterior_id': id_procedimento
                    })
                    return (
                        f"✅ Conflito resolvido. Procedimento **{_titulo}** validado pelo revisor humano.\n"
                        f"- Flag `necessita_revisao` removida\n"
                        f"- Versão anterior arquivada como `arquivado_backup`\n"
                        f"- Novo documento criado: `{_resolved_id}`"
                    )
            except Exception as _res_err:
                return f"⚠️ Erro ao resolver conflito: {str(_res_err)}"

        def criar_acao_no_sistema(
            titulo: str,
            descricao: str = "",
            area_tematica: str = "GERAL",
            data_limite: str = None,
            tipo_acao: str = "fast",
            tags: list[str] = [],
            notas: str = "",
            plano_acao: list[str] = []
        ):
            """
            Cria uma nova ação/tarefa no sistema Hermes após confirmação explícita do usuário.
            Use APENAS depois que o usuário confirmar o draft apresentado.
            Parâmetros:
            - titulo: título obrigatório da ação
            - descricao: descrição detalhada (opcional)
            - area_tematica: área temática (ex: 'LICITAÇÕES', 'RH', 'GERAL')
            - data_limite: prazo no formato YYYY-MM-DD (opcional)
            - tipo_acao: 'fast' para ações rápidas, 'deep' para trabalho profundo
            - tags: lista de tags (opcional)
            - notas: observações adicionais (opcional)
            - plano_acao: lista de strings com os passos do plano (opcional)
            Retorna o ID da tarefa criada ou mensagem de erro.
            """
            try:
                import uuid as _uuid
                from datetime import datetime as _dt, timezone as _tz

                now_iso = _dt.now(_tz.utc).isoformat()
                task_id = str(_uuid.uuid4())[:20]

                # Converte lista de strings em array de objetos para o React
                plano_convertido = [
                    {
                        "id": str(_uuid.uuid4())[:8],
                        "text": str(passo),
                        "completed": False
                    }
                    for passo in (plano_acao or [])
                    if str(passo).strip()
                ]

                doc = {
                    # Campos fornecidos pelo LLM
                    "titulo": titulo.strip(),
                    "descricao": descricao or "",
                    "area_tematica": (area_tematica or "GERAL").upper(),
                    "data_limite": data_limite or None,
                    "tipo_acao": tipo_acao if tipo_acao in ("fast", "deep") else "fast",
                    "tags": list(tags) if tags else [],
                    "notas": notas or "",
                    "plano_acao": plano_convertido,
                    # Campos forçados (hidratação interna)
                    "status": "em andamento",
                    "origem": "copiloto",
                    "projeto": "GERAL",
                    "data_criacao": now_iso,
                    "data_atualizacao": now_iso,
                    "contabilizar_meta": True,
                    "acompanhamento": [],
                    "entregas_relacionadas": [],
                    "pool_dados": [],
                    "plano_acao_historico": [],
                    "sync_status": "new",
                }

                db.collection("tarefas").document(task_id).set(doc)
                print(f"[Copiloto] Ação criada: id={task_id}, titulo='{titulo}'")
                return f"OK|{task_id}"

            except Exception as _ce:
                print(f"[Copiloto] Erro ao criar ação: {_ce}")
                return f"ERRO|{str(_ce)}"

        def editar_plano_acao(
            task_id: str,
            novo_plano: list[dict],
            justificativa_diario: str
        ):
            """
            Substitui/atualiza o plano de ação de uma tarefa existente.
            Usa fuzzy matching para preservar o status de conclusão dos passos já concluídos.
            Use APENAS depois que o usuário confirmar o draft do novo plano apresentado.
            Parâmetros:
            - task_id: ID da tarefa no Firestore.
            - novo_plano: Lista de dicionários no formato [{"id": "xyz", "text": "Passo 1"}, {"text": "Passo Novo sem id"}].
            - justificativa_diario: Texto gerado pela IA explicando o motivo da alteração (será gravado no diário da tarefa).
            Retorna 'OK' ou 'ERRO|{detalhe}'.
            """
            try:
                import uuid as _uuid
                from datetime import datetime as _dt, timezone as _tz
                import difflib as _difflib

                task_ref = db.collection('tarefas').document(task_id)
                task_doc = task_ref.get()
                if not task_doc.exists:
                    return f"ERRO|Tarefa '{task_id}' não encontrada."

                task_data = task_doc.to_dict()
                plano_atual = task_data.get('plano_acao', [])
                now_iso = _dt.now(_tz.utc).isoformat()

                # Índice rápido por ID para Match Direto
                plano_por_id = {p['id']: p for p in plano_atual if p.get('id')}
                textos_originais = [p.get('text', p.get('texto', '')) for p in plano_atual]

                plano_final = []
                for item in (novo_plano or []):
                    texto_novo = str(item.get('text') or item.get('texto') or '').strip()
                    if not texto_novo:
                        continue

                    item_id = item.get('id', '')

                    # Caminho 1: Match Direto por ID
                    if item_id and item_id in plano_por_id:
                        original = plano_por_id[item_id]
                        plano_final.append({
                            'id': item_id,
                            'text': texto_novo,
                            'completed': original.get('completed', False)
                        })
                        continue

                    # Caminho 2: Fuzzy Match por texto (≥85% similaridade)
                    matches = _difflib.get_close_matches(texto_novo, textos_originais, n=1, cutoff=0.85)
                    if matches:
                        idx = textos_originais.index(matches[0])
                        original = plano_atual[idx]
                        plano_final.append({
                            'id': original.get('id', str(_uuid.uuid4())[:8]),
                            'text': texto_novo,
                            'completed': original.get('completed', False)
                        })
                        continue

                    # Caminho 3: Inserção — novo passo sem correspondência
                    plano_final.append({
                        'id': str(_uuid.uuid4())[:8],
                        'text': texto_novo,
                        'completed': False
                    })

                diary_entry = {
                    'data': now_iso,
                    'nota': f"[Copiloto Hermes] Plano de ação atualizado: {justificativa_diario}"
                }

                task_ref.update({
                    'plano_acao': plano_final,
                    'data_atualizacao': now_iso,
                    'acompanhamento': firestore.ArrayUnion([diary_entry])
                })

                print(f"[Copiloto] Plano de ação da tarefa {task_id} atualizado ({len(plano_final)} passos).")
                return "OK"

            except Exception as _ee:
                print(f"[Copiloto] Erro ao editar plano: {_ee}")
                return f"ERRO|{str(_ee)}"

        # Configuração do Chat com ferramentas
        model_id = "gemini-3.1-pro-preview"
        
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")

        system_instruction = (
            f"Você é o Copiloto Hermes, estrategista sênior de processos. Hoje é {today_str}. "
            "Seu tom de voz: Consultivo, analítico e absurdamente conciso. "
            "Use bullet points para melhorar a legibilidade. "
            "\n\n"
            "## REGRA ABSOLUTA — SIGLAS, TERMOS TÉCNICOS E ERROS DE BACKEND\n\n"
            "PROIBIÇÃO TOTAL DE EXPANSÃO ARBITRÁRIA DE SIGLAS:\n"
            "Você JAMAIS deve inferir, adivinhar, expandir ou traduzir siglas, acrônimos ou\n"
            "termos técnicos que o usuário fornecer. Se o usuário disser \"IRP\", você trata\n"
            "\"IRP\" como uma string opaca e literal — não é \"Imposto de Renda\", não é\n"
            "\"Internal Revenue Policy\", não é nada que você \"acha que pode ser\". Você passa\n"
            "o termo exatamente como recebido para as ferramentas de busca. Se nenhum\n"
            "documento retornar resultado, sua resposta é: \"Nenhum registro encontrado para\n"
            "o termo exato 'IRP'. Você pode confirmar a sigla ou fornecer mais contexto?\"\n"
            "Não improvise. Não complete. Não alucine.\n\n"
            "OBRIGAÇÃO DE TRANSPARÊNCIA EM ERROS TÉCNICOS:\n"
            "Se qualquer ferramenta (buscar_acervo, buscar_tarefas ou similar) retornar um\n"
            "campo \"erro\" não-nulo, você DEVE reproduzir o conteúdo desse campo palavra por\n"
            "palavra na sua resposta, sem parafrasear, sem suavizar e sem omitir. Formato\n"
            "obrigatório:\n\n"
            "  ⚠️ Erro técnico na ferramenta [nome_da_ferramenta]:\n"
            "  [conteúdo literal do campo \"erro\"]\n\n"
            "Após reportar o erro, peça ao usuário que acione o suporte técnico com essa\n"
            "mensagem exata. Você NÃO deve tentar responder a pergunta original como se o\n"
            "erro não tivesse ocorrido.\n\n"
            "TRATAMENTO DE CONFLITOS: Se a prática [Grafo] divergir do manual [Acervo], exponha explicitamente.\n"
            "Sempre termine propostas de ajuste de plano de ação dentro de: [PROPOSAL]{...}[/PROPOSAL]\n\n"
            "## NAVEGAÇÃO ENTRE AÇÕES (CRÍTICO)\n"
            "Para que o usuário possa gerir as ações, você DEVE SEMPRE transformar o nome de qualquer tarefa citada em um link clicável.\n"
            "FORMATO OBRIGATÓRIO: `[Nome da Tarefa](task:ID)`\n"
            "Exemplo: 'Verifiquei que a ação [Analisar Edital](task:xyz123) está atrasada.'\n"
            "Use os IDs retornados pelas ferramentas `consultar_historico_acoes` ou `obter_contexto_tela`.\n\n"
            "## BUSCA PROATIVA DE CONTEXTO\n"
            "Se o usuário pedir algo genérico (ex: 'o que temos hoje' ou 'status das atividades') e você não tiver uma tarefa em foco:\n"
            "1. NÃO peça o ID ou Área Temática imediatamente.\n"
            "2. Use `consultar_historico_acoes(query='', data_limite_inicio='YYYY-MM-DD')` para filtrar por prazo/vencimento se o usuário mencionar datas.\n"
            "3. Se não houver data específica, use `query=''` para listar as tarefas mais recentes do sistema.\n"
            "4. Analise os resultados e peça clarificação apenas se necessário.\n\n"
            "## REGRA DE INTEGRIDADE DOCUMENTAL (CRÍTICO — PENA DE FALHA SISTÊMICA)\n"
            "Se o usuário perguntar sobre valores, quantidades, itens ou cláusulas de um arquivo presente\n"
            "no campo 'arquivos_disponiveis' do contexto da tarefa, você é ESTRITAMENTE PROIBIDO de:\n"
            "  a) Deduzir a resposta com base no seu treinamento.\n"
            "  b) Mesclar fragmentos de buscas vetoriais globais (buscar_arquivos_acervo) com dados deste arquivo.\n\n"
            "PROTOCOLO OBRIGATÓRIO:\n"
            "  1. Verifique se o arquivo está listado em 'arquivos_disponiveis' (via obter_contexto_tela).\n"
            "  2. Chame ler_documento_na_integra(drive_file_id=<ID>, query_especifica=<pergunta exata do usuário>).\n"
            "  3. Baseie sua resposta EXCLUSIVAMENTE no retorno desta ferramenta.\n"
            "  4. Se a ferramenta declarar que a informação não existe, reproduza essa declaração sem inventar alternativas.\n"
            "NUNCA misture dados numéricos (valores, itens, quantidades) de processos ou documentos distintos.\n\n"
            "## CRIAÇÃO DE AÇÕES — PADRÃO DRAFT-THEN-COMMIT (CRÍTICO)\n\n"
            "Quando o usuário solicitar a criação de uma ação/tarefa, siga OBRIGATORIAMENTE este protocolo:\n\n"
            "ETAPA 1 — DRAFT (apresentar antes de criar):\n"
            "Nunca chame criar_acao_no_sistema imediatamente. Primeiro, apresente um resumo estruturado:\n"
            "  📋 **Draft da Ação**\n"
            "  - **Título:** [título proposto]\n"
            "  - **Área Temática:** [área]\n"
            "  - **Prazo:** [data ou 'Sem prazo definido']\n"
            "  - **Tipo:** [fast / deep]\n"
            "  - **Plano de Ação:**\n"
            "    1. [passo 1]\n"
            "    2. [passo 2]\n"
            "  Confirma a criação desta ação?\n\n"
            "ETAPA 2 — CONFIRMAÇÃO:\n"
            "Só chame criar_acao_no_sistema após receber confirmação explícita ('sim', 'confirma', 'pode criar', 'ok', etc.).\n"
            "Se o usuário ajustar algum campo no draft, incorpore as correções antes de criar.\n\n"
            "ETAPA 3 — COMMIT E LINK:\n"
            "Após criar_acao_no_sistema retornar 'OK|{ID}', responda obrigatoriamente:\n"
            "  ✅ Ação criada: [Título da Ação](task:{ID})\n"
            "Se retornar 'ERRO|{detalhe}', responda:\n"
            "  ⚠️ Erro ao criar ação: {detalhe}\n\n"
            "EXTRAÇÃO DE CONTEXTO PARA O DRAFT:\n"
            "- Se houver um taskId ativo, use obter_contexto_tela() para inferir área temática, tags e contexto.\n"
            "- Deduza que a nova ação pode ser sub-tarefa ou relacionada ao contexto ativo.\n"
            "- Use o histórico da conversa para preencher descricao e plano_acao automaticamente.\n\n"
            "## EDIÇÃO DE PLANO DE AÇÃO — PADRÃO DRAFT-THEN-COMMIT (CRÍTICO)\n\n"
            "Quando o usuário solicitar alteração, adição, remoção ou reestruturação de passos de um plano de ação:\n\n"
            "ETAPA 0 — EXTRAÇÃO DE CONTEXTO OBRIGATÓRIA:\n"
            "Chame obter_contexto_tela() para capturar o taskId e o plano de ação atual (com os IDs dos passos).\n"
            "Nunca suponha IDs de passos — leia-os do resultado da ferramenta.\n\n"
            "ETAPA 1 — DRAFT (apresentar antes de editar):\n"
            "Nunca chame editar_plano_acao imediatamente. Primeiro, apresente o novo plano proposto:\n"
            "  ✏️ **Novo Plano de Ação proposto**\n"
            "  1. [passo 1]\n"
            "  2. [passo 2]\n"
            "  *(passos removidos, adicionados ou reordenados em relação ao plano atual)*\n"
            "  Confirma a atualização do plano?\n\n"
            "ETAPA 2 — CONFIRMAÇÃO:\n"
            "Só chame editar_plano_acao após confirmação explícita do usuário ('sim', 'confirma', 'pode atualizar', etc.).\n"
            "Ao montar novo_plano, inclua o campo 'id' para passos existentes (preserva status de conclusão via fuzzy match no backend).\n"
            "Omita o 'id' apenas para passos genuinamente novos.\n\n"
            "ETAPA 3 — COMMIT E CONFIRMAÇÃO:\n"
            "Se editar_plano_acao retornar 'OK', responda:\n"
            "  ✅ Plano de ação atualizado com sucesso.\n"
            "Se retornar 'ERRO|{detalhe}', responda:\n"
            "  ⚠️ Erro ao atualizar plano: {detalhe}\n\n"
            "PARÂMETRO justificativa_diario:\n"
            "Gere automaticamente uma frase concisa descrevendo o que foi alterado e por quê (ex: 'Adicionado passo de validação jurídica a pedido do usuário.').\n"
            "O usuário não precisa aprovar este texto — é gravado silenciosamente no diário da tarefa."
        )

        # --- RECUPERAÇÃO DE HISTÓRICO DA SESSÃO ---
        history = []
        if session_id:
            try:
                msg_docs = db.collection('sessoes_copiloto').document(session_id)\
                    .collection('mensagens')\
                    .order_by('timestamp', direction=firestore.Query.DESCENDING)\
                    .limit(6).get()
                
                # Inverte para ordem cronológica conforme exigido pelo SDK
                raw_msgs = list(reversed(msg_docs))
                for mdoc in raw_msgs:
                    m = mdoc.to_dict()
                    # Mapeia roles: o SDK espera 'user' ou 'model' (não 'assistant')
                    role = m.get('role')
                    if role == 'assistant':
                        role = 'model'
                    
                    history.append(types.Content(
                        role=role,
                        parts=[types.Part(text=m.get('content'))]
                    ))
            except Exception as e:
                print(f"Erro ao carregar histórico da sessão {session_id}: {e}")

        # --- ROTEADOR DE INTENÇÃO (heurístico + LLM fallback) ---
        # Passo 1: regex barato — evita chamada LLM na maioria dos casos.
        # Passo 2: só aciona Flash se palavras-chave estiverem presentes, com timeout de 3s.
        _CORRECAO_KEYWORDS = re.compile(
            r'\b(corrig|atualiz|invalida|contest|errad|incorret|mudar|alterar|substituir|'
            r'não está certo|não é assim|estava errado|está errado|procedimento errado)\w*\b',
            re.IGNORECASE
        )
        _correcao_hint = ""
        if _CORRECAO_KEYWORDS.search(prompt):
            try:
                _intent_resp = client.models.generate_content(
                    model="gemini-3.1-flash-lite-preview",
                    contents=f"Responda só 'CORRECAO' ou 'NORMAL': o usuário está corrigindo um procedimento?\nMensagem: {prompt}",
                    config=types.GenerateContentConfig(
                        http_options=types.HttpOptions(timeout=3000)
                    )
                )
                if "CORRECAO" in (_intent_resp.text or "").upper():
                    _correcao_hint = (
                        "\n\n## [DIRETIVA DO MOTOR DE EVOLUÇÃO — NÃO REVELAR AO USUÁRIO]\n"
                        "O roteador de intenção classificou esta mensagem como CORREÇÃO DE PROCEDIMENTO.\n"
                        "OBRIGAÇÃO: Após formular sua resposta ao usuário, acione silenciosamente "
                        "registrar_correcao_procedimento() com os dados extraídos da mensagem.\n"
                        "Não mencione, descreva nem insinue esta ação ao usuário."
                    )
            except Exception:
                pass  # Fail-open: timeout ou erro → continua sem hint

        # Mapa nome → função para dispatch manual do loop de ferramentas
        _function_map = {
            'consultar_historico_acoes': consultar_historico_acoes,
            'buscar_arquivos_acervo': buscar_arquivos_acervo,
            'obter_contexto_tela': obter_contexto_tela,
            'pesquisar_internet': pesquisar_internet,
            'ler_pagina_web': ler_pagina_web,
            'ler_documento_na_integra': ler_documento_na_integra,
            'registrar_correcao_procedimento': registrar_correcao_procedimento,
            'resolver_conflito_procedimento': resolver_conflito_procedimento,
            'criar_acao_no_sistema': criar_acao_no_sistema,
            'editar_plano_acao': editar_plano_acao,
        }
        # Ferramentas internas que não devem aparecer para o usuário
        _HIDDEN_TOOLS = {'registrar_correcao_procedimento'}

        chat = client.chats.create(
            model=model_id,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction + _correcao_hint,
                tools=[
                    consultar_historico_acoes,
                    buscar_arquivos_acervo,
                    obter_contexto_tela,
                    pesquisar_internet,
                    ler_pagina_web,
                    ler_documento_na_integra,
                    registrar_correcao_procedimento,
                    resolver_conflito_procedimento,
                    criar_acao_no_sistema,
                    editar_plano_acao,
                ],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            ),
            history=history
        )

        # ─── INGESTÃO DOCUMENTAL ─────────────────────────────────────────────────
        # Se um driveFileId foi enviado, baixa o binário, extrai metadados via
        # Gemini File API (sem parsers locais) e grava no indice_artefatos (RAG).
        file_context = ""
        if drive_file_id:
            try:
                import io
                import os
                import tempfile
                import uuid as _uuid
                from googleapiclient.http import MediaIoBaseDownload
                from google.cloud.firestore_v1.vector import Vector

                drive_service = get_drive_service()

                # 1. Busca metadados do arquivo no Drive
                file_meta = drive_service.files().get(
                    fileId=drive_file_id,
                    fields='name,mimeType'
                ).execute()
                real_file_name = file_meta.get('name', drive_file_name)
                real_mime_type = file_meta.get('mimeType', 'application/octet-stream')

                # 2. Baixa o binário para memória volátil
                request_dl = drive_service.files().get_media(fileId=drive_file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request_dl)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                fh.seek(0)
                file_bytes = fh.read()

                # 3. Salva em arquivo temporário para a File API do Gemini
                file_ext = os.path.splitext(real_file_name)[1] or '.bin'
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name

                # 4. Faz upload para a File API do Gemini
                gemini_file = client.files.upload(
                    file=tmp_path,
                    config=types.UploadFileConfig(
                        mime_type=real_mime_type,
                        display_name=real_file_name
                    )
                )
                os.unlink(tmp_path)

                # O bloco try/finally abaixo garante que o arquivo seja sempre
                # deletado da File API do Gemini, mesmo que a extração falhe.
                # Sem isso cada upload acumularia dados até estourar a cota de 2GB.
                try:
                    # 5. Extrai metadados com truncamento semântico de ~8.000 tokens
                    extraction_prompt = (
                        f"Você recebeu o arquivo '{real_file_name}'. "
                        "Leia no máximo os primeiros 8.000 tokens de conteúdo. "
                        "Retorne EXCLUSIVAMENTE um JSON válido, sem markdown, sem texto extra:\n"
                        '{"titulo": "...", "natureza": "...", "resumo": "..."}\n'
                        "Onde:\n"
                        "- titulo: nome/título do documento\n"
                        "- natureza: categoria (ex: Edital, Contrato, Relatório, Manual, Planilha, etc.)\n"
                        "- resumo: resumo executivo em 3 a 5 frases sobre conteúdo e utilidade"
                    )
                    extraction_response = client.models.generate_content(
                        model=model_id,
                        contents=[
                            types.Content(parts=[
                                types.Part.from_uri(
                                    file_uri=gemini_file.uri,
                                    mime_type=real_mime_type
                                ),
                                types.Part(text=extraction_prompt)
                            ])
                        ]
                    )
                    extraction_text = extraction_response.text.strip()
                    # Remove blocos de código caso o modelo os inclua mesmo instruído
                    if extraction_text.startswith("```"):
                        extraction_text = extraction_text.split("```")[1]
                        if extraction_text.startswith("json"):
                            extraction_text = extraction_text[4:]

                    meta = json.loads(extraction_text)
                    titulo_doc = meta.get('titulo', real_file_name)
                    natureza_doc = meta.get('natureza', 'Documento')
                    resumo_doc = meta.get('resumo', '')

                    # 6. Vetoriza e grava no indice_artefatos
                    from knowledge_graph import _get_embedding
                    embed_text = f"{titulo_doc} | {natureza_doc} | {resumo_doc}"
                    embedding = _get_embedding(embed_text, gemini_key)
                    embedding_floats = list(map(float, embedding))

                    artefato_id = str(_uuid.uuid4())[:12]
                    drive_link = f"https://drive.google.com/file/d/{drive_file_id}/view"

                    # Origem bifurcada: tarefa (se task_id ativo) ou acervo global
                    origem_doc = (
                        {'modulo': 'tarefa', 'id_origem': task_id, 'session_id': session_id or 'direto'}
                        if task_id
                        else {'modulo': 'copiloto', 'id_origem': session_id or 'direto'}
                    )
                    db.collection('indice_artefatos').document(artefato_id).set({
                        'titulo': titulo_doc,
                        'trecho': resumo_doc,
                        'fonte': natureza_doc,
                        'embedding': Vector(embedding_floats),
                        'tipo_arquivo': real_mime_type.split('/')[-1],
                        'url_drive': drive_link,
                        'data_criacao': firestore.SERVER_TIMESTAMP,
                        'origem': origem_doc,
                        'task_id': task_id or None,
                        'categoria': 'Copiloto Hermes'
                    })
                    print(f"[Copiloto] Artefato '{titulo_doc}' gravado em indice_artefatos (id={artefato_id})")

                    # Dupla cidadania: vínculo físico e histórico à tarefa ativa
                    if task_id:
                        from datetime import datetime as _dt
                        now_iso = _dt.now().isoformat()
                        pool_item = {
                            'id': artefato_id,
                            'tipo': 'arquivo',
                            'valor': drive_link,
                            'nome': titulo_doc,
                            'drive_file_id': drive_file_id,  # Salvo explicitamente para leitura profunda on-demand
                            'data_criacao': now_iso
                        }
                        diary_entry = {
                            'data': now_iso,
                            'nota': f"📎 [Copiloto] Arquivo '{titulo_doc}' ({natureza_doc}) carregado via Copiloto Hermes e indexado no acervo global."
                        }
                        db.collection('tarefas').document(task_id).update({
                            'pool_dados': firestore.ArrayUnion([pool_item]),
                            'acompanhamento': firestore.ArrayUnion([diary_entry])
                        })
                        print(f"[Copiloto] Arquivo '{titulo_doc}' vinculado à tarefa {task_id} (pool_dados + acompanhamento)")

                    # 7. Monta o bloco de contexto que será injetado no prompt final
                    file_context = (
                        f"[CONTEXTO DO ARQUIVO ANEXADO]\n"
                        f"Nome: {real_file_name}\n"
                        f"Título extraído: {titulo_doc}\n"
                        f"Natureza: {natureza_doc}\n"
                        f"Resumo: {resumo_doc}\n"
                        f"Link original: {drive_link}\n"
                        f"[/CONTEXTO DO ARQUIVO ANEXADO]"
                    )

                finally:
                    # Limpeza obrigatória — evita acúmulo na File API do Gemini
                    try:
                        client.files.delete(name=gemini_file.name)
                        print(f"[Copiloto] Arquivo Gemini '{gemini_file.name}' deletado com sucesso.")
                    except Exception as del_err:
                        print(f"[Copiloto] Aviso: falha ao deletar arquivo Gemini '{gemini_file.name}': {del_err}")

            except Exception as file_err:
                import traceback as _tb
                from datetime import datetime as _dt
                err_str = str(file_err)
                print(f"[Copiloto] Erro na ingestão documental: {err_str}")
                print(_tb.format_exc())

                # Telemetria estruturada — não suja o diário da tarefa
                try:
                    db.collection('quality_logs').add({
                        'tipo': 'erro_ingestao_copiloto',
                        'descricao': 'Falha ao extrair contexto de arquivo via Gemini File API',
                        'evidencia': err_str,
                        'arquivo_nome': drive_file_name,
                        'task_id': task_id or None,
                        'session_id': session_id or None,
                        'data_criacao': _dt.now().isoformat()
                    })
                except Exception as log_err:
                    print(f"[Copiloto] Falha ao gravar quality_log: {log_err}")

                file_context = f"⚠️ Não foi possível processar o arquivo '{drive_file_name}': {err_str}"
        # ─────────────────────────────────────────────────────────────────────────

        # Injeta contexto inicial se houver task_id
        initial_context = ""
        if task_id:
            initial_context = f"DICA DE CONTEXTO: O usuário está visualizando a tarefa {task_id}. " \
                             f"Use obter_contexto_tela('{task_id}') para se situar antes de responder."

        # Monta prompt final combinando task context + file context + pergunta do usuário
        context_parts = []
        if initial_context:
            context_parts.append(initial_context)
        if file_context:
            context_parts.append(file_context)
        context_parts.append(f"USUÁRIO: {prompt}")
        final_prompt = "\n\n".join(context_parts)
        
        # Loop manual de tool calling — intercepta cada chamada para rastrear ferramentas usadas
        tools_used: list[str] = []
        response = chat.send_message(final_prompt)
        _max_iter = 10
        for _ in range(_max_iter):
            fcs = response.function_calls
            if not fcs:
                break
            function_response_parts = []
            for fc in fcs:
                fn = _function_map.get(fc.name)
                if fn is None:
                    result = f"Ferramenta '{fc.name}' não encontrada."
                else:
                    try:
                        result = fn(**(fc.args or {}))
                    except Exception as _fe:
                        result = f"Erro ao executar {fc.name}: {_fe}"
                if fc.name not in _HIDDEN_TOOLS and fc.name not in tools_used:
                    tools_used.append(fc.name)
                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": str(result)}
                    )
                )
            response = chat.send_message(function_response_parts)

        result_text = response.text
        # Extração de Proposta [PROPOSAL]{...}[/PROPOSAL]
        proposal_data = None
        clean_text = result_text
        if "[PROPOSAL]" in result_text:
            try:
                parts = result_text.split("[PROPOSAL]")
                proposal_raw = parts[1].split("[/PROPOSAL]")[0]
                proposal_data = json.loads(proposal_raw)
                clean_text = parts[0] + (parts[1].split("[/PROPOSAL]")[1] if "[/PROPOSAL]" in parts[1] else "")
                clean_text = clean_text.strip()
            except Exception as e:
                print(f"Erro ao extrair proposta: {e}")

        # Salva a resposta do assistente no Firestore para o histórico
        if session_id:
            try:
                db.collection('sessoes_copiloto').document(session_id).collection('mensagens').add({
                    "role": "assistant",
                    "content": clean_text,
                    "proposedPlan": proposal_data.get("items") if proposal_data else None,
                    "toolsUsed": tools_used if tools_used else None,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                # Atualiza timestamp da sessão
                db.collection('sessoes_copiloto').document(session_id).update({
                    "lastMessageAt": firestore.SERVER_TIMESTAMP
                })
            except Exception as e:
                print(f"Erro ao salvar resposta no Firestore: {e}")

        # Tenta extrair título sugerido se for início de sessão
        suggested_title = None
        if prompt and len(prompt) < 100:
            suggested_title = prompt[:50]

        return {
            "result": clean_text,
            "proposedPlan": proposal_data.get("items") if proposal_data else None,
            "suggestedTitle": suggested_title
        }

    except Exception as e:
        print(f"Erro em askCopilotoHermes: {e}")
        import traceback
        print(traceback.format_exc())
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )

def buscar_procedimento_internal(query_text: str, area_tematica: str = None):
    # Wrapper interno para chamar a lógica de buscar_procedimento sem o overhead do Callable HTTPS
    try:
        db = get_db()
        keys_doc = db.collection('system').document('api_keys').get()
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        
        from knowledge_graph import _get_embedding, _cosine_similarity
        
        # Sanitização de input
        q_text = (query_text or "").strip()
        if not q_text:
            q_text = "procedimentos operacionais"

        query_embedding = _get_embedding(q_text, api_key)
        # Protocolo de Segurança: Converte para floats
        query_vector = list(map(float, query_embedding))

        collection_query = db.collection("knowledge_nodes")
        if area_tematica:
            collection_query = collection_query.where("area_tematica", "==", area_tematica)

        nodes_raw = []
        for ndoc in collection_query.stream():
            nd = ndoc.to_dict() or {}
            node_emb = nd.get("embedding")
            if not node_emb: continue
            sim = _cosine_similarity(query_vector, node_emb)
            # Limiar mais flexível
            if sim < 0.35: continue
            nodes_raw.append({
                "titulo": nd.get("titulo"),
                "resumo": nd.get("resumo"),
                "area_tematica": nd.get("area_tematica"),
                "score": sim
            })
        
        nodes_raw.sort(key=lambda x: x["score"], reverse=True)
        candidates = nodes_raw[:5]
        
        lines = [f"Resultados do Grafo para: {q_text}"]
        for i, n in enumerate(candidates, 1):
            lines.append(f"[{i}] {n['titulo']} ({n['area_tematica']}) - {n['resumo']}")
            
        # --- FALLBACK: Busca em Tarefas Reais (Regex Estrito do novo módulo) ---
        if len(candidates) < 2:
            from tools.busca_grafo import buscar_tarefas
            res = buscar_tarefas(q_text, area_tematica=area_tematica)
            
            if res.get("erro"):
                lines.append(f"\n⚠️ [ERRO TÉCNICO FallbackGrafo] {res['erro']}")
            else:
                found = res.get("resultados", [])
                if found:
                    lines.append("\n--- Buscando em Tarefas (Execução Real - Regex) ---")
                    for r in found:
                        lines.append(f"TAREFA: {r['titulo']} | STATUS: {r['status']} | DATA: {r['criado_em']} | [Abrir](task:{r['id']})")
                else:
                    lines.append(f"\nNenhum registro encontrado para o termo '{q_text}' no Banco de Dados.")

        return {"context": "\n".join(lines)}
    except Exception as e:
        print(f"DEBUG_ERROR [Grafo]: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"context": f"Erro interno ao consultar grafo: {str(e)}"}

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
            'area_tematica': 'Reuniões',
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

@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
    timeout_sec=300
)
def analisarPadroesCategoriaIA(req: https_fn.CallableRequest):
    """
    Analisa tarefas de uma area_tematica específica para identificar padrões e propor artefatos de conhecimento.
    """
    from google import genai
    import json
    import re
    import traceback

    data = req.data or {}
    area_tematica = data.get('area_tematica')
    
    if not area_tematica:
         raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Categoria é obrigatória."
        )

    try:
        db = firestore.client()
        # Busca tarefas concluídas desta area_tematica (limite de 15 para análise)
        tasks_query = db.collection('tarefas')\
            .where('area_tematica', '==', area_tematica)\
            .where('status', '==', 'concluído')\
            .limit(15)
        
        docs = tasks_query.stream()
        contexto_tarefas = []
        for doc in docs:
            t = doc.to_dict()
            contexto_tarefas.append(f"Tarefa: {t.get('titulo')}\nNotas: {t.get('notas')}")

        if not contexto_tarefas:
            return {"success": False, "message": f"Não há tarefas concluídas suficientes em '{area_tematica}' para analisar padrões."}

        keys_doc = db.collection('system').document('api_keys').get()
        gemini_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        
        if not gemini_key:
            return {"success": False, "error": "Chave Gemini não configurada no sistema (system/api_keys)."}

        client = genai.Client(api_key=gemini_key)

        prompt = f"""
        Você é o HERMES Master IA. Analise a sequência de tarefas abaixo da area_tematica '{area_tematica}'.
        Sua missão é identificar um PADRÃO de trabalho ou um PROCEDIMENTO que o André segue.
        
        Com base nessas tarefas, crie um "Guia de Procedimento Operacional Padrão" para esta area_tematica.
        
        TAREFAS ANALISADAS:
        {chr(10).join(contexto_tarefas)}
        
        Retorne um JSON com:
        1. titulo: Nome do guia (ex: Procedimento para Licitação de Compras)
        2. conteudo: O guia detalhado em Markdown (passos, dicas, o que não esquecer).
        3. insight: Um breve comentário seu sobre por que isso é importante ou o que você notou de especial.
        """

        response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=prompt)
        res_text = response.text

        json_match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if json_match:
            result_data = json.loads(json_match.group(0))

            # Versionamento não-destrutivo: arquiva versão anterior antes de criar nova
            _titulo_novo = result_data.get('titulo', '')
            _existing_proc = db.collection("conhecimento_mestre")\
                .where("titulo", "==", _titulo_novo)\
                .where("status", "!=", "arquivado_backup")\
                .limit(1).get()
            for _ep in _existing_proc:
                _ep.reference.update({
                    "status": "arquivado_backup",
                    "data_arquivamento": firestore.SERVER_TIMESTAMP
                })
            import uuid as _uuid_analytics
            _new_proc_id = str(_uuid_analytics.uuid4())[:12]
            db.collection("conhecimento_mestre").document(_new_proc_id).set({
                "titulo": _titulo_novo,
                "conteudo_regra": result_data.get('conteudo', ''),
                "justificativa_da_regra": result_data.get('insight', ''),
                "area_tematica": area_tematica,
                "insight_ia": result_data.get('insight'),
                "data_criacao": firestore.SERVER_TIMESTAMP,
                "tipo": "procedimento_aprendido",
                "status": "ativo",
                "necessita_revisao": False,
                "tag_aviso": "",
                "autor": "HERMES_ANALYTICS"
            })
            
            return {"success": True, "data": result_data}
            
        return {"success": False, "error": f"Falha ao analisar padrões estruturados. Resposta da IA: {res_text[:200]}"}

    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"Erro em analisarPadroesCategoriaIA: {error_msg}")
        return {"success": False, "error": str(e), "traceback": error_msg}


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR DE EVOLUÇÃO AUTÔNOMA — Batch Job de Processamento de Correções
# Executa a cada 60 minutos. Lê a fila `correcoes_pendentes`, valida compliance
# via consenso web (Tavily, mín. 5 fontes), refina com Gemini Pro e persiste
# com versionamento não-destrutivo em `conhecimento_mestre`.
# ─────────────────────────────────────────────────────────────────────────────
@scheduler_fn.on_schedule(schedule="every 60 minutes")
def processar_correcoes_pendentes(event: scheduler_fn.ScheduledEvent) -> None:
    """Motor de Evolução Autônoma: processa fila de correções com validação de compliance."""
    import traceback as _evo_tb
    import uuid as _evo_uuid
    import requests as _evo_req

    _db = get_db()
    _gemini_key = _get_gemini_key()
    _evo_client = genai.Client(api_key=_gemini_key)

    # Recupera chave Tavily para consenso web
    _tavily_key = ''
    try:
        _keys_doc = _db.collection('system').document('api_keys').get()
        _tavily_key = (_keys_doc.to_dict() or {}).get('tavily_api_key', '')
    except Exception as _key_err:
        print(f"[EvoEngine] Aviso: não foi possível recuperar chave Tavily: {_key_err}")

    # Busca até 10 correções pendentes por ciclo
    try:
        _correcoes = list(
            _db.collection('correcoes_pendentes')
               .where('status', '==', 'pendente')
               .limit(10)
               .get()
        )
    except Exception as _fetch_err:
        print(f"[EvoEngine] Erro ao buscar fila: {_fetch_err}")
        return

    if not _correcoes:
        print("[EvoEngine] Nenhuma correção pendente neste ciclo.")
        return

    print(f"[EvoEngine] Processando {len(_correcoes)} correção(ões).")

    for _corr_doc in _correcoes:
        _corr_id = _corr_doc.id
        _corr = _corr_doc.to_dict()

        try:
            # Marca como em processamento para evitar reprocessamento paralelo
            _db.collection('correcoes_pendentes').document(_corr_id).update(
                {'status': 'processando'}
            )

            _titulo        = _corr.get('titulo_procedimento', '')
            _area          = _corr.get('area_tematica', '')
            _novo_conteudo = _corr.get('novo_conteudo_proposto', '')
            _justificativa = _corr.get('justificativa_usuario', '')

            # ── 1. Busca versão atual do procedimento em conhecimento_mestre ──────
            _old_doc_id   = None
            _old_content  = '(procedimento ainda não existe)'
            try:
                _existing = list(
                    _db.collection('conhecimento_mestre')
                       .where('titulo', '==', _titulo)
                       .where('status', '!=', 'arquivado_backup')
                       .limit(1)
                       .get()
                )
                if _existing:
                    _old_data    = _existing[0].to_dict()
                    _old_content = _old_data.get('conteudo_regra') or _old_data.get('conteudo', '')
                    _old_doc_id  = _existing[0].id
            except Exception as _find_err:
                print(f"[EvoEngine] Aviso ao buscar procedimento existente: {_find_err}")

            # ── 2. Verificação de consenso web (mínimo 5 fontes via Tavily) ───────
            _compliance_ok      = False
            _compliance_sources = []
            _compliance_summary = 'Verificação de compliance não executada (chave ausente).'

            if _tavily_key:
                try:
                    _search_query = (
                        f"procedimento compliance legal {_titulo} {_area} "
                        "legislação brasileira norma vigente"
                    )
                    _t_resp = _evo_req.post(
                        'https://api.tavily.com/search',
                        json={
                            'api_key': _tavily_key,
                            'query': _search_query,
                            'search_depth': 'advanced',
                            'include_answer': True,
                            'max_results': 7
                        },
                        timeout=25
                    )
                    if _t_resp.status_code == 200:
                        _t_data             = _t_resp.json()
                        _compliance_sources = [r.get('url', '') for r in _t_data.get('results', [])]
                        _web_answer         = _t_data.get('answer', '')
                        _n_sources          = len(_compliance_sources)

                        # LLM avalia conformidade com base no consenso web
                        _comp_prompt = (
                            f"Você é um auditor de conformidade legal sênior.\n"
                            f"Avalie se o procedimento proposto está em conformidade com "
                            f"legislação e normas brasileiras vigentes, usando as {_n_sources} "
                            f"fontes web como referência de consenso.\n\n"
                            f"PROCEDIMENTO PROPOSTO:\n{_novo_conteudo}\n\n"
                            f"CONSENSO WEB ({_n_sources} fontes):\n{_web_answer}\n\n"
                            f"Responda EXCLUSIVAMENTE em JSON válido (sem markdown):\n"
                            f'{{\"aprovado\": true_ou_false, \"resumo\": \"motivo em 1 frase\"}}'
                        )
                        _comp_resp    = _evo_client.models.generate_content(
                            model="gemini-3.1-flash-lite-preview",
                            contents=_comp_prompt
                        )
                        _comp_text    = (_comp_resp.text or '').strip()
                        _comp_match   = re.search(r'\{.*\}', _comp_text, re.DOTALL)
                        if _comp_match:
                            _comp_data          = json.loads(_comp_match.group(0))
                            _compliance_ok      = bool(_comp_data.get('aprovado', False))
                            _compliance_summary = _comp_data.get('resumo', '')
                        else:
                            _compliance_summary = f"LLM retornou formato inesperado: {_comp_text[:120]}"
                    else:
                        _compliance_summary = f"Tavily retornou status {_t_resp.status_code}."
                except Exception as _comp_err:
                    _compliance_summary = f"Erro na verificação: {str(_comp_err)}"
                    print(f"[EvoEngine] {_compliance_summary}")

            # ── 3. LLM de raciocínio superior refina o procedimento final ─────────
            _refinement_prompt = (
                "Você é um engenheiro de processos sênior. Integre a correção proposta "
                "ao procedimento atual, mantendo clareza, estrutura Markdown e fidelidade "
                "à justificativa fornecida. Retorne APENAS o conteúdo final em Markdown.\n\n"
                f"PROCEDIMENTO ATUAL:\n{_old_content}\n\n"
                f"CORREÇÃO PROPOSTA:\n{_novo_conteudo}\n\n"
                f"JUSTIFICATIVA:\n{_justificativa}"
            )
            try:
                _refine_resp   = _evo_client.models.generate_content(
                    model="gemini-3.1-pro-preview",
                    contents=_refinement_prompt
                )
                _conteudo_final = (_refine_resp.text or _novo_conteudo).strip()
            except Exception as _refine_err:
                print(f"[EvoEngine] Refinamento Pro falhou, usando conteúdo proposto: {_refine_err}")
                _conteudo_final = _novo_conteudo

            # ── 4. Execução Otimista (Fail-Open) — aplica sempre, sinaliza se falhou ──
            _necessita_revisao = not _compliance_ok
            _tag_aviso = (
                "[⚠️ OTIMIZADO ÀS CEGAS: Validação de compliance falhou]"
                if _necessita_revisao else ""
            )

            # ── 5. Versionamento não-destrutivo — arquiva versão anterior ─────────
            if _old_doc_id:
                try:
                    _db.collection('conhecimento_mestre').document(_old_doc_id).update({
                        'status': 'arquivado_backup',
                        'data_arquivamento': firestore.SERVER_TIMESTAMP
                    })
                except Exception as _arch_err:
                    print(f"[EvoEngine] Aviso ao arquivar versão anterior: {_arch_err}")

            # ── 6. Persiste novo procedimento com campos obrigatórios ─────────────
            _new_id = str(_evo_uuid.uuid4())[:12]
            _db.collection('conhecimento_mestre').document(_new_id).set({
                'titulo':                   _titulo,
                'area_tematica':            _area,
                'conteudo_regra':           _conteudo_final,
                'justificativa_da_regra':   _justificativa,
                'status':                   'ativo',
                'necessita_revisao':        _necessita_revisao,
                'tag_aviso':                _tag_aviso,
                'compliance_aprovado':      _compliance_ok,
                'compliance_resumo':        _compliance_summary,
                'compliance_fontes':        _compliance_sources[:5],
                'data_criacao':             firestore.SERVER_TIMESTAMP,
                'tipo':                     'procedimento_evoluido',
                'autor':                    'HERMES_EVOLUTION_ENGINE',
                'origem_correcao_id':       _corr_id,
                'procedimento_anterior_id': _old_doc_id or ''
            })

            # ── 7. Fecha a correção na fila ───────────────────────────────────────
            _db.collection('correcoes_pendentes').document(_corr_id).update({
                'status':              'processado',
                'novo_doc_id':         _new_id,
                'compliance_aprovado': _compliance_ok,
                'data_processamento':  firestore.SERVER_TIMESTAMP
            })

            _status_str = "COMPLIANCE OK" if _compliance_ok else "FAIL-OPEN (necessita_revisao=True)"
            print(f"[EvoEngine] ✅ Correção {_corr_id} → doc {_new_id} | {_status_str}")

        except Exception as _proc_err:
            print(f"[EvoEngine] ❌ Erro ao processar correção {_corr_id}:\n{_evo_tb.format_exc()}")
            try:
                _db.collection('correcoes_pendentes').document(_corr_id).update({
                    'status':   'erro',
                    'erro_msg': str(_proc_err)
                })
            except Exception:
                pass
