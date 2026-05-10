

from firebase_functions import firestore_fn, scheduler_fn, options, https_fn, pubsub_fn

from firebase_admin import initialize_app, firestore, messaging, get_app
import json
import base64
from datetime import datetime, timedelta, timezone
import math
import time
import threading
import re
import io
import uuid
import secrets
import os
import sys
import unicodedata

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from security_portals import (
    generatePgdFromDiariesAI,
    generatePgdFromRawTextAI,
    getPublicFinancePortal,
    getPublicScholarshipProject,
    getPublicShoppingPortal,
    matchShoppingItemsAI,
    mutateShoppingList,
    mutatePublicShoppingPortal,
    submitPublicFinanceTransaction,
    submitPublicScholarshipRegistration,
)
from pdf_precision import extract_pdf_text_with_fallback, is_pdf_mime_type

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def is_docx_mime_type(filename: str | None = None, mime_type: str | None = None) -> bool:
    mime = (mime_type or "").lower().strip()
    name = (filename or "").lower().strip()
    return mime == DOCX_MIME_TYPE or name.endswith(".docx")


def extract_docx_text(file_bytes: bytes) -> tuple[str, dict]:
    import mammoth

    result = mammoth.extract_raw_text(io.BytesIO(file_bytes))
    warnings = [
        getattr(message, "message", str(message))
        for message in (getattr(result, "messages", None) or [])
    ]
    metadata = {"source": "mammoth", "warnings": warnings}
    return (result.value or "").strip(), metadata

from knowledge_graph import (  # noqa: F401 — registra as Cloud Functions
    on_tarefa_created_kg,
    on_tarefa_concluida_kg,
    buscar_procedimento,
    crystallize_task_manual,
    extract_kg_rag_context,
    processar_artefato_kg,
    monitorar_acervo_global,
    executar_monitoramento_acervo_global,
    smart_search_kg,
    get_artefato_raw_text,
)
from hermes_core_logic import (  # noqa: F401 — registra as Cloud Functions
    telegramWebhook,
    on_telegram_inbound,
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
COPILOT_FUNCTION_TIMEOUT_SEC = 540
COPILOT_SOFT_DEADLINE_SEC = 510
COPILOT_MODEL_TIMEOUT_MS = 90000
COPILOT_TOOL_TIMEOUT_SEC = 60

# ---------------------------------------------------------------------------
# In-process Firestore document cache (TTL = 60 s per Cloud Function instance)
# Evita leituras repetidas de system/api_keys, system/copilot_core, etc.
# ---------------------------------------------------------------------------
_DOC_CACHE: dict = {}
_DOC_CACHE_TTL = 60  # seconds

# Cache da coleção pops_diretrizes. Mantemos curto porque POP recém-criado
# precisa ser observado pelo copiloto na conversa seguinte.
_POPS_DATA_CACHE: tuple | None = None  # (monotonic_ts, list[dict])
_POPS_DATA_TTL = 30

# Cache de _bootstrap_user_ai_profile por UID (TTL 60 s)
_PROFILE_CACHE: dict = {}  # uid -> (monotonic_ts, dict)

def _cached_doc_get(db, collection: str, document: str):
    key = f"{collection}/{document}"
    now = time.monotonic()
    cached = _DOC_CACHE.get(key)
    if cached and (now - cached[0]) < _DOC_CACHE_TTL:
        return cached[1]
    doc = db.collection(collection).document(document).get()
    _DOC_CACHE[key] = (now, doc)
    return doc


def get_genai_module():
    from google import genai
    return genai


def get_gemini_api_key() -> str | None:
    db = get_db()
    keys_doc = _cached_doc_get(db, 'system', 'api_keys')
    return keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None


def get_embedding(text: str, api_key: str = None, task_type: str = "RETRIEVAL_DOCUMENT") -> list:
    """Get text embedding via Gemini SDK (gemini-embedding-001, 768 dims).
    task_type should be RETRIEVAL_DOCUMENT for indexing and RETRIEVAL_QUERY for searching."""
    from google import genai
    from google.genai import types
    if not api_key:
        api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError("Chave Gemini não configurada.")
    client = genai.Client(api_key=api_key)
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text[:8000],
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=768  # trava dimensional: compatível com vetores existentes no Firestore
        )
    )
    return response.embeddings[0].values


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_db():

    """Retorna a instância do Firestore de forma lazy"""

    return firestore.client()

def _perf_now_ms() -> int:
    return int(time.perf_counter() * 1000)


def _perf_mark(perf_state: dict, name: str):
    started_at = perf_state.get("_last_ms", perf_state["start_ms"])
    now_ms = _perf_now_ms()
    perf_state.setdefault("steps", []).append({
        "name": name,
        "duration_ms": max(0, now_ms - started_at),
    })
    perf_state["_last_ms"] = now_ms


def _perf_log(prefix: str, perf_state: dict, extra: dict | None = None):
    payload = {
        "prefix": prefix,
        "total_ms": max(0, _perf_now_ms() - perf_state["start_ms"]),
        "steps": perf_state.get("steps", []),
    }
    if perf_state.get("tool_calls"):
        payload["tool_calls"] = perf_state["tool_calls"]
    if extra:
        payload.update(extra)
    try:
        print(f"[Perf] {json.dumps(payload, ensure_ascii=False)}")
    except Exception:
        print(f"[Perf] {prefix} total_ms={payload['total_ms']}")


GOOGLE_BASE_SCOPES = [
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive',
]

GOOGLE_FORMS_SCOPES = GOOGLE_BASE_SCOPES + [
    'https://www.googleapis.com/auth/forms.body'
]


class GoogleAuthRevokedError(Exception):
    """Raised when Google OAuth credentials need a new user consent flow."""


GOOGLE_REAUTH_MESSAGE = (
    "Autenticacao Google expirada ou revogada. Execute setup_credentials.bat "
    "na raiz do projeto para refazer o login Google e atualizar system/google_credentials."
)


def is_google_invalid_grant_error(exc):
    text = str(exc).lower()
    if "invalid_grant" in text or "token has been expired or revoked" in text:
        return True
    cause = getattr(exc, "__cause__", None)
    if cause and cause is not exc:
        return is_google_invalid_grant_error(cause)
    context = getattr(exc, "__context__", None)
    if context and context is not exc:
        return is_google_invalid_grant_error(context)
    return False


def get_google_creds(scopes=None):
    """Busca as credenciais OAuth2 do Firestore e renova se necessário"""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    db = get_db()
    creds_doc = db.collection('system').document('google_credentials').get()

    if not creds_doc.exists:
        raise Exception("Credenciais não encontradas no Firestore.")

    creds_data = creds_doc.to_dict()
    stored_scopes = creds_data.get('scopes') or GOOGLE_BASE_SCOPES

    creds = Credentials(
        token=creds_data.get('token'),
        refresh_token=creds_data.get('refresh_token'),
        token_uri=creds_data.get('token_uri'),
        client_id=creds_data.get('client_id'),
        client_secret=creds_data.get('client_secret'),
        scopes=stored_scopes
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
            if is_google_invalid_grant_error(e):
                db.collection('system').document('google_credentials').set({
                    'auth_status': 'reauth_required',
                    'auth_error': 'invalid_grant',
                    'auth_error_message': GOOGLE_REAUTH_MESSAGE,
                    'updated_at': firestore.SERVER_TIMESTAMP
                }, merge=True)
                raise GoogleAuthRevokedError(GOOGLE_REAUTH_MESSAGE) from e
            
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


def is_iso_after(left_value, right_value):
    from datetime import timezone
    left_dt = parse_iso_datetime(left_value)
    right_dt = parse_iso_datetime(right_value)

    if left_dt and right_dt:
        if left_dt.tzinfo is not None and right_dt.tzinfo is None:
            right_dt = right_dt.replace(tzinfo=timezone.utc)
        elif left_dt.tzinfo is None and right_dt.tzinfo is not None:
            left_dt = left_dt.replace(tzinfo=timezone.utc)
        return left_dt > right_dt
    if left_dt and not right_dt:
        return True
    if right_dt and not left_dt:
        return False
    if left_value and right_value:
        return str(left_value) > str(right_value)
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

                if is_iso_after(g_updated, t_old.get('data_atualizacao', '')):

                    applied_updated = datetime.now().isoformat() if title_was_normalized else g_updated

                    update_data = {

                        'titulo': title, 'status': status, 'data_atualizacao': applied_updated,

                        'data_conclusao': gt.get('completed'), 'notas': g_notes,

                        'horario_inicio': h_inicio, 'horario_fim': h_fim

                    }

                    if g_due:
                        update_data['data_limite'] = g_due
                        update_data['data_inicio'] = g_due

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

                # 1. Remover do Google Tasks
                if g_id:

                    try: 

                        service.tasks().delete(tasklist=tasklist_id, task=g_id).execute()

                        log_to_firestore(sync_ref, logs, f"[X] REMOVIDA DO GOOGLE TASKS: {title}")

                    except HttpError as e:

                        if e.resp.status == 404:

                            log_to_firestore(sync_ref, logs, f"[!] Task {g_id} já não existia no Google Tasks.")

                # 2. Remover do Google Calendar
                cal_id = t.get('google_calendar_id')
                if cal_id:
                    try:
                        calendar_service.events().delete(calendarId=calendar_id, eventId=cal_id).execute()
                        log_to_firestore(sync_ref, logs, f"[X] REMOVIDA DO CALENDAR: {title}")
                    except Exception as e:
                        log_to_firestore(sync_ref, logs, f"[!] Erro ao remover do Calendar: {e}")

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
            elif g_id in g_tasks_map and is_iso_after(local_updated, g_tasks_map[g_id].get('updated', '')):
                body = {'id': g_id, 'title': title, 'notes': updated_notes, 'status': g_status}
                if g_due: body['due'] = g_due
                try:
                    updated_task = service.tasks().update(tasklist=tasklist_id, task=g_id, body=body).execute()
                    log_to_firestore(sync_ref, logs, f"[^] ATUALIZADA NO TASKS: {title}")
                    sync_updates = {}
                    if updated_task.get('updated'):
                        sync_updates['data_atualizacao'] = updated_task.get('updated')
                    if updated_notes != t.get('notas', ''):
                        sync_updates['notas'] = updated_notes
                    if h_fim and not t.get('horario_fim'):
                        sync_updates['horario_fim'] = h_fim
                    if sync_updates:
                        doc.reference.update(sync_updates)
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

        if is_google_invalid_grant_error(e):
            raise GoogleAuthRevokedError(GOOGLE_REAUTH_MESSAGE) from e

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

                if is_google_invalid_grant_error(cal_err):
                    raise GoogleAuthRevokedError(GOOGLE_REAUTH_MESSAGE) from cal_err

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
                    if not is_iso_after(event_updated, local_updated):
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

        if is_google_invalid_grant_error(e):
            raise GoogleAuthRevokedError(GOOGLE_REAUTH_MESSAGE) from e

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
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        if not api_key:
            log_to_firestore(sync_ref, logs, "ERRO: Gemini API Key não encontrada (em system/api_keys).")
            return
        
        from google.genai import types

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
                content_parts.append(types.Part.from_bytes(data=pdf_data, mime_type="application/pdf"))
            
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
            
            # Ingestão de Documentos (Acervo Global)
            log_to_firestore(sync_ref, logs, "[SYNC] Verificando novos documentos na Pasta de Deságue (Acervo Global)...", True)
            executar_monitoramento_acervo_global()

            sync_system_repositories_to_rag(db, sync_ref, logs)

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

        if isinstance(e, GoogleAuthRevokedError) or is_google_invalid_grant_error(e):
            error_msg = f"ERRO GOOGLE AUTH: {GOOGLE_REAUTH_MESSAGE}"
            try:
                db.collection('system').document('google_credentials').set({
                    'auth_status': 'reauth_required',
                    'auth_error': 'invalid_grant',
                    'auth_error_message': GOOGLE_REAUTH_MESSAGE,
                    'updated_at': firestore.SERVER_TIMESTAMP
                }, merge=True)
            except Exception as auth_status_err:
                print(f"Falha ao marcar reautenticacao Google: {auth_status_err}")
        else:
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



@firestore_fn.on_document_updated(document="system/sync", timeout_sec=540, memory=options.MemoryOption.GB_1)

def on_sync_request(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]]):

    """Trigger disparado quando system/sync é atualizado manualmente"""

    if not event.data.after.exists: return

    data = event.data.after.to_dict()

    if data.get('status') != 'requested': return

    run_full_sync('firestore-request')



@scheduler_fn.on_schedule(schedule="every 30 minutes", timeout_sec=540, memory=options.MemoryOption.GB_1)

def scheduled_sync(event: scheduler_fn.ScheduledEvent) -> None:

    """Trigger agendado para rodar a cada 30 minutos"""

    run_full_sync('scheduled')


def _normalize_notification_title(title: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(title or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.strip().lower()


def _should_mirror_notification_to_telegram(notif: dict) -> bool:
    """Mantem o Telegram restrito as categorias importantes e acionaveis."""
    title = _normalize_notification_title(notif.get('title'))

    exact_titles = {
        "erro de sincronizacao",
        "novo pix recebido",
        "novos boletos",
        "acoes vencidas",
        "alerta de orcamento",
        "auditoria pgd",
        "apresentacao concluida",
        "pesquisa concluida",
        "pesquisa profunda concluida",
        "pesquisa profunda falhou",
    }
    if title in exact_titles:
        return True

    if title in {"hermes: proxima tarefa", "hermes: encerramento de tarefa"}:
        return True

    # Lembretes especificos de acao ja sao enviados ao Telegram pelo scheduler
    # com mensagem mais detalhada; nao duplicamos via espelhamento generico.
    if title.startswith("lembrete:"):
        return False

    return False


def _build_telegram_notification_message(notif: dict) -> str:
    title = str(notif.get('title') or 'Hermes').strip()
    message = str(notif.get('message') or '').strip()
    n_type = str(notif.get('type') or 'info').strip()
    link = str(notif.get('link') or '').strip()

    icons = {
        'success': '✅',
        'warning': '⚠️',
        'error': '🚨',
        'info': '🔔',
    }
    lines = [f"{icons.get(n_type, '🔔')} Hermes - {title}"]
    if message:
        lines.extend(["", message])
    if link:
        label = "Link" if link.startswith(("http://", "https://")) else "Destino no Hermes"
        lines.extend(["", f"{label}: {link}"])
    return "\n".join(lines)

@firestore_fn.on_document_created(document="notificacoes/{notification_id}", memory=options.MemoryOption.MB_512)

def on_notificacao_created(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]):

    """Trigger disparado quando uma nova notificação é criada"""

    if not event.data: return

    notif = event.data.to_dict()

    if not notif: return

    title = notif.get('title', 'Hermes')

    message = notif.get('message', '')

    db = get_db()

    updates = {}

    if not notif.get('sent_to_telegram') and _should_mirror_notification_to_telegram(notif):

        telegram_chat_id = _resolve_default_telegram_chat_id(db)

        if telegram_chat_id:

            sent = _send_telegram_message_raw(db, telegram_chat_id, _build_telegram_notification_message(notif))

            updates['sent_to_telegram'] = bool(sent)

            if not sent:

                updates['telegram_error'] = 'send_failed'

        else:

            updates['sent_to_telegram'] = False

            updates['telegram_error'] = 'chat_id_not_configured'

    if notif.get('sent_to_push'):

        if updates:

            event.data.reference.update(updates)

        return

    tokens_docs = db.collection('fcm_tokens').stream()
    tokens = list({doc.id for doc in tokens_docs if doc.id})
    if not tokens:

        print("Nenhum token FCM encontrado para enviar push.")

        if updates:

            event.data.reference.update(updates)

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

            bad_tokens = [
                tokens[idx] for idx, resp in enumerate(response.responses)
                if not resp.success and resp.exception
                and "registration-token-not-registered" in str(resp.exception).lower()
            ]

            if bad_tokens:

                for i in range(0, len(bad_tokens), 500):

                    batch = db.batch()

                    for token in bad_tokens[i:i + 500]:

                        batch.delete(db.collection('fcm_tokens').document(token))

                    batch.commit()

                print(f"Removidos {len(bad_tokens)} tokens FCM inválidos.")

        updates['sent_to_push'] = True

        event.data.reference.update(updates)

    except Exception as e:

        print(f"Erro ao enviar push notification: {str(e)}")

        if updates:

            event.data.reference.update(updates)



@scheduler_fn.on_schedule(
    schedule="every 1 minutes",
    memory=options.MemoryOption.GB_1,
    timeout_sec=120,
)

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

    now_iso = now.strftime('%Y-%m-%dT%H:%M:%S')

    tasks_with_reminders = db.collection('tarefas')\
            .where('reminder_sent', '==', False)\
            .where('reminder_at', '<=', now_iso)\
            .stream()



    for task_doc in tasks_with_reminders:

        t = task_doc.to_dict()

        title = t.get('titulo', 'Ação Pendente')
        task_reminders = _normalize_task_reminders(t)
        due_reminder = next((reminder for reminder in task_reminders if not reminder.get('reminder_sent')), None)
        reminder_iso = due_reminder.get('reminder_at') if due_reminder else t.get('reminder_at')

        emit_notification_backend(

            f"Lembrete: {title}",

            "Está na hora de realizar esta ação agendada!",

            'warning',

            'acoes'

        )

        

        owner_uid = t.get('created_by_uid')
        telegram_chat_id = _resolve_telegram_chat_id_for_uid(db, owner_uid) or _resolve_default_telegram_chat_id(db)
        telegram_message = _build_task_reminder_telegram_message(t, reminder_iso)
        if telegram_chat_id:
            _send_telegram_message_raw(db, telegram_chat_id, telegram_message)
        else:
            print(f"[Telegram] Nenhum chat_id encontrado para lembrete da tarefa {task_doc.id}")

        # Marca como enviado para não repetir

        if due_reminder:
            updated_reminders = []
            matched = False
            for reminder in task_reminders:
                if not matched and reminder.get('id') == due_reminder.get('id'):
                    updated_reminders.append({**reminder, 'reminder_sent': True})
                    matched = True
                else:
                    updated_reminders.append(reminder)
            task_doc.reference.update(_build_task_reminder_state_payload(updated_reminders))
        else:
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

        if isinstance(e, GoogleAuthRevokedError) or is_google_invalid_grant_error(e):
            try:
                get_db().collection('system').document('google_credentials').set({
                    'auth_status': 'reauth_required',
                    'auth_error': 'invalid_grant',
                    'auth_error_message': GOOGLE_REAUTH_MESSAGE,
                    'updated_at': firestore.SERVER_TIMESTAMP
                }, merge=True)
            except Exception as auth_status_err:
                print(f"Falha ao marcar reautenticacao Google: {auth_status_err}")
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
                message=GOOGLE_REAUTH_MESSAGE
            )

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

        # No Gen 2, event.data.message.data contém os bytes
        msg_bytes = event.data.message.data
        if msg_bytes:
            import base64
            if isinstance(msg_bytes, str):
                message_text = base64.b64decode(msg_bytes).decode('utf-8')
            else:
                message_text = msg_bytes.decode('utf-8')
        else:
             message_text = getattr(event.data.message, "text", "")



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

    keys_doc = _cached_doc_get(db, 'system', 'api_keys')

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
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
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
    filename = data.get('filename') or data.get('fileName') or 'arquivo'
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
    extraction_strategy = "text_decode"
    extraction_metadata = None
    try:
        if is_pdf_mime_type(filename, mime_type):
            pdf_result = extract_pdf_text_with_fallback(
                file_bytes,
                filename,
                api_key=get_gemini_api_key(),
                allow_gemini_fallback=True,
            )
            texto_bruto = pdf_result.get('text', '')
            extraction_strategy = pdf_result.get('strategy', 'none')
            extraction_metadata = pdf_result.get('metadata')
        elif is_docx_mime_type(filename, mime_type):
            texto_bruto, extraction_metadata = extract_docx_text(file_bytes)
            extraction_strategy = "docx_mammoth"
        else:
            texto_bruto = file_bytes.decode('utf-8', errors='replace').strip()
    except Exception as e:
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INTERNAL, message=f"Erro ao extrair texto: {e}")

    if not texto_bruto:
        return {'success': False, 'vectorized': False, 'message': 'Nenhum texto extraído do arquivo.'}

    # Trunca para 500.000 chars antes de salvar no Firestore (limite de 1MB por documento)
    texto_bruto = texto_bruto[:500000]

    # Salva texto no documento existente
    doc_updates = {
        'texto_bruto': texto_bruto,
        'texto_extraido_por': extraction_strategy,
    }
    if extraction_metadata:
        doc_updates['extraction_metadata'] = extraction_metadata
    doc_ref.update(doc_updates)

    # Vetoriza
    try:
        api_key = get_gemini_api_key()
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
    keys_doc = _cached_doc_get(db, 'system', 'api_keys')
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
    extraction_strategy = "text_decode"
    extraction_metadata = None
    is_pdf = is_pdf_mime_type(filename, mime_type)
    is_docx = is_docx_mime_type(filename, mime_type)

    if is_pdf:
        try:
            pdf_result = extract_pdf_text_with_fallback(
                file_bytes,
                filename,
                api_key=get_gemini_api_key(),
                allow_gemini_fallback=True,
            )
            texto_bruto = pdf_result.get('text', '')
            extraction_strategy = pdf_result.get('strategy', 'none')
            extraction_metadata = pdf_result.get('metadata')
        except Exception as e:
            print(f"Erro ao extrair PDF '{filename}': {e}")
            texto_bruto = ""
    elif is_docx:
        try:
            texto_bruto, extraction_metadata = extract_docx_text(file_bytes)
            extraction_strategy = "docx_mammoth"
        except Exception as e:
            print(f"Erro ao extrair DOCX '{filename}': {e}")
            texto_bruto = ""
    else:
        # Arquivos de texto: TXT, MD, CSV, etc.
        try:
            texto_bruto = file_bytes.decode('utf-8').strip()
        except UnicodeDecodeError:
            texto_bruto = file_bytes.decode('latin-1', errors='replace').strip()

    # Salva no Firestore
    doc_id = str(uuid.uuid4())
    tipo = 'pdf' if is_pdf else 'docx' if is_docx else 'texto'
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
        'texto_extraido_por': extraction_strategy,
    }
    if extraction_metadata:
        doc_data['extraction_metadata'] = extraction_metadata
    db.collection('conhecimento').document(doc_id).set(doc_data)

    # Vetorização automática
    vectorized = False
    if texto_bruto:
        try:
            api_key = get_gemini_api_key()

            if api_key:
                embedding_vec = get_embedding(texto_bruto, api_key=api_key)
                db.collection('conhecimento').document(doc_id).update({
                    'embedding': embedding_vec
                })
                vectorized = True
        except Exception as e:
            print(f"Erro ao vetorizar contexto extra '{filename}': {e}")

    return {'success': True, 'docId': doc_id, 'vectorized': vectorized}


def _sync_github_repo_internal(sistema_id: str, repo_url: str, skip_if_unchanged: bool = False, db=None) -> dict:
    """
    Extrai informações principais de um repositório GitHub e cria/atualiza
    uma base RAG vinculada ao sistema no Hermes.
    Extrai: README, árvore de arquivos, dependências e configs.
    """
    import requests as http_req
    import base64 as b64

    repo_url = (repo_url or '').strip()

    if not sistema_id or not repo_url:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="sistema_id e repo_url são obrigatórios."
        )

    db = db or get_db()

    # Busca chaves da API
    keys_doc = _cached_doc_get(db, 'system', 'api_keys')
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
    branch_sha = None
    branch_resp = http_req.get(f'{base_url}/branches/{default_branch}', headers=headers, timeout=30)
    if branch_resp.status_code == 200:
        branch_sha = ((branch_resp.json().get('commit') or {}).get('sha') or '').strip() or None
    if not branch_sha:
        branch_sha = (repo_data.get('pushed_at') or repo_data.get('updated_at') or '').strip() or None

    sistema_ref = db.collection('sistemas_detalhes').document(sistema_id)
    if skip_if_unchanged and branch_sha:
        sistema_data = sistema_ref.get().to_dict() or {}
        last_sha = (sistema_data.get('github_rag_last_commit_sha') or '').strip()
        last_repo_url = (sistema_data.get('github_rag_repo_url') or sistema_data.get('repositorio_principal') or '').strip()
        if last_sha == branch_sha and last_repo_url == repo_url:
            checked_at = datetime.now(timezone.utc).isoformat()
            sistema_ref.set({
                'github_rag_checked_at': checked_at,
                'github_rag_repo_url': repo_url,
                'data_atualizacao': checked_at,
            }, merge=True)
            return {
                'success': True,
                'skipped': True,
                'reason': 'unchanged',
                'base_id': f"github_{sistema_id}",
                'chunks_created': 0,
                'repo_name': sistema_nome,
                'commit_sha': branch_sha,
            }

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
    synced_at = datetime.now(timezone.utc).isoformat()
    sistema_ref.set({
        'github_rag_synced_at': synced_at,
        'github_rag_checked_at': synced_at,
        'github_rag_last_commit_sha': branch_sha,
        'github_rag_repo_url': repo_url,
        'data_atualizacao': synced_at,
    }, merge=True)

    return {
        'success': True,
        'skipped': False,
        'base_id': base_id,
        'chunks_created': created_count,
        'repo_name': sistema_nome,
        'commit_sha': branch_sha,
    }


def sync_system_repositories_to_rag(db, sync_ref, logs):
    """Sincroniza bases RAG de sistemas apenas quando o repo mudou."""
    try:
        sistemas = []
        for doc_snap in db.collection('sistemas_detalhes').stream():
            data = doc_snap.to_dict() or {}
            repo_url = (data.get('repositorio_principal') or '').strip()
            if repo_url:
                sistemas.append((doc_snap.id, data.get('nome') or data.get('nome_sistema') or doc_snap.id, repo_url))

        if not sistemas:
            log_to_firestore(sync_ref, logs, "[RAG] Nenhum repositorio de sistema configurado.", True)
            return

        synced_count = 0
        skipped_count = 0
        failed_count = 0
        log_to_firestore(sync_ref, logs, f"[RAG] Verificando {len(sistemas)} repositorio(s) de sistemas...", True)

        for sistema_id, sistema_nome, repo_url in sistemas:
            try:
                result = _sync_github_repo_internal(sistema_id, repo_url, skip_if_unchanged=True, db=db)
                if result.get('skipped'):
                    skipped_count += 1
                    log_to_firestore(sync_ref, logs, f"[RAG] Sem alteracoes: {sistema_nome}.")
                else:
                    synced_count += 1
                    log_to_firestore(sync_ref, logs, f"[RAG] Sincronizado: {sistema_nome} ({result.get('chunks_created', 0)} chunks).")
            except Exception as e:
                failed_count += 1
                log_to_firestore(sync_ref, logs, f"[RAG][!] Falha ao verificar {sistema_nome}: {e}")

        log_to_firestore(sync_ref, logs, f"[RAG] Concluido. {synced_count} sincronizado(s), {skipped_count} sem alteracao, {failed_count} falha(s).", True)
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"[RAG][!] Erro geral na sincronizacao de sistemas: {e}", True)


@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=180, cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]))
def sync_github_repo(req: https_fn.CallableRequest):
    data = req.data or {}
    return _sync_github_repo_internal(
        data.get('sistema_id'),
        data.get('repo_url', ''),
        skip_if_unchanged=bool(data.get('skip_if_unchanged', False)),
    )


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

        keys_doc = _cached_doc_get(db, 'system', 'api_keys')

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

        GEMINI_API_KEY = get_gemini_api_key()

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

        elif is_pdf_mime_type(file_metadata.get('name'), mime_type):

            pdf_result = extract_pdf_text_with_fallback(
                content,
                file_metadata.get('name') or 'documento.pdf',
                api_key=GEMINI_API_KEY,
                allow_gemini_fallback=True,
            )
            extracted_pdf_text = (pdf_result.get('text') or '').strip()

            if extracted_pdf_text:
                prompt = f"""

            Analise o texto abaixo, extraído de um PDF, e retorne em JSON:

            1. texto_bruto: Conteúdo principal extraído.

            2. resumo_tldr: Resumo de até 3 linhas.

            3. tags: Lista de 5-10 palavras-chave.

            4. area_tematica: Uma única palavra de classificação.

            TEXTO EXTRAÍDO:

            {extracted_pdf_text[:100000]}

            """

                parts = [prompt]
            else:
                prompt = """

            Analise este PDF e retorne em JSON:

            1. texto_bruto: Conteúdo principal extraído.

            2. resumo_tldr: Resumo de até 3 linhas.

            3. tags: Lista de 5-10 palavras-chave.

            4. area_tematica: Uma única palavra de classificação.

            """

                parts = [{"mime_type": mime_type, "data": content}, prompt]

        elif is_docx_mime_type(file_metadata.get('name'), mime_type):

            extracted_docx_text, docx_metadata = extract_docx_text(content)

            prompt = f"""

            Analise o texto abaixo, extraÃ­do de um arquivo Word DOCX, e retorne em JSON:

            1. texto_bruto: ConteÃºdo principal extraÃ­do.

            2. resumo_tldr: Resumo de atÃ© 3 linhas.

            3. tags: Lista de 5-10 palavras-chave.

            4. area_tematica: Uma Ãºnica palavra de classificaÃ§Ã£o.

            METADADOS DA EXTRAÃ‡ÃƒO:

            {json.dumps(docx_metadata, ensure_ascii=False)}

            TEXTO EXTRAÃDO:

            {extracted_docx_text[:100000]}

            """

            parts = [prompt]

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







        keys_doc = _cached_doc_get(db, 'system', 'api_keys')







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



            keys_doc = _cached_doc_get(db, 'system', 'api_keys')



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



COPILOT_SOUL_DEFAULT = {
    "tone": "Consultivo, analítico e objetivo.",
    "detail_level": "Alto o suficiente para orientar execução, sem prolixidade.",
    "interaction_style": "Clareza, transparência sobre incertezas e foco em próximos passos concretos.",
}

MEMORY_NODE_TYPES = {"regra_global", "fato_isolado"}
MEMORY_SIMILARITY_CREATE_THRESHOLD = 0.90
MEMORY_SIMILARITY_DUPLICATE_THRESHOLD = 0.965
MEMORY_MIN_FACT_LENGTH = 24


def _iso_now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_memory_category(value: str | None) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "regra": "regra_global",
        "regra_global": "regra_global",
        "regra global": "regra_global",
        "policy": "regra_global",
        "fato": "fato_isolado",
        "fato_isolado": "fato_isolado",
        "fato isolado": "fato_isolado",
        "fact": "fato_isolado",
    }
    return aliases.get(raw, "fato_isolado")


def _normalize_text_for_match(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _normalize_pop_text(text: str | None) -> str:
    raw = unicodedata.normalize("NFKD", (text or "").strip().lower())
    without_accents = "".join(ch for ch in raw if not unicodedata.combining(ch))
    without_punct = re.sub(r"[^\w\s]", " ", without_accents)
    return re.sub(r"\s+", " ", without_punct).strip()


def _match_pop_directives(db, prompt: str) -> list[dict]:
    global _POPS_DATA_CACHE
    prompt_norm = _normalize_pop_text(prompt)
    if not prompt_norm:
        return []

    prompt_terms = set(prompt_norm.split())

    try:
        now = time.monotonic()
        used_cache = False
        if _POPS_DATA_CACHE and (now - _POPS_DATA_CACHE[0]) < _POPS_DATA_TTL:
            all_pops = _POPS_DATA_CACHE[1]
            used_cache = True
        else:
            all_pops = [
                {"id": d.id, **( d.to_dict() or {})}
                for d in db.collection("pops_diretrizes").stream()
            ]
            _POPS_DATA_CACHE = (now, all_pops)

        def _collect_matches(pops: list[dict]) -> list[dict]:
            matched: list[dict] = []

            for pop in pops:
                gatilhos = pop.get("gatilhos", []) or []
                instrucao = (pop.get("instrucao_sistema") or "").strip()
                titulo = (pop.get("titulo") or pop.get("id") or "POP").strip()

                if not instrucao or not isinstance(gatilhos, list):
                    continue

                matched_triggers: list[str] = []
                for gatilho in gatilhos:
                    gatilho_norm = _normalize_pop_text(str(gatilho))
                    if not gatilho_norm:
                        continue

                    gatilho_terms = gatilho_norm.split()
                    if gatilho_norm in prompt_norm:
                        matched_triggers.append(str(gatilho))
                        continue

                    if len(gatilho_terms) > 1 and all(term in prompt_terms for term in gatilho_terms):
                        matched_triggers.append(str(gatilho))
                        continue

                if matched_triggers:
                    matched.append({
                        "id": pop.get("id", ""),
                        "titulo": titulo,
                        "instrucao_sistema": instrucao,
                        "matched_triggers": matched_triggers,
                        "score": max(len(_normalize_pop_text(trigger).split()) for trigger in matched_triggers),
                    })

            return matched

        matched = _collect_matches(all_pops)

        # Se o cache estiver velho e ainda dentro do TTL, um POP cadastrado há
        # segundos pode não existir na lista local. Em caso de miss, revalida.
        if not matched and used_cache:
            refreshed_at = time.monotonic()
            all_pops = [
                {"id": d.id, **(d.to_dict() or {})}
                for d in db.collection("pops_diretrizes").stream()
            ]
            _POPS_DATA_CACHE = (refreshed_at, all_pops)
            matched = _collect_matches(all_pops)

    except Exception as pop_err:
        print(f"[POP] Erro ao buscar diretrizes: {pop_err}")
        return []

    matched.sort(key=lambda item: item.get("score", 0), reverse=True)
    return matched[:3]


def _get_copilot_core(db):
    doc = _cached_doc_get(db, "system", "copilot_core")
    if doc.exists:
        data = doc.to_dict() or {}
        if data.get("content"):
            return data
    return {
        "content": (
            "NUNCA exponha segredos, chaves de API, tokens, credenciais ou dados sensíveis. "
            "Nunca invente fatos. Se houver conflito entre memórias, exponha a divergência e peça validação explícita do usuário. "
            "Use apenas JSON válido quando uma ferramenta exigir JSON."
        ),
        "source": "default",
    }


def _get_copilot_soul(db):
    doc = _cached_doc_get(db, "system", "copilot_soul")
    if doc.exists:
        data = doc.to_dict() or {}
        if any(data.get(key) for key in ("tone", "detail_level", "interaction_style", "content")):
            return data

    payload = {
        **COPILOT_SOUL_DEFAULT,
        "content": (
            f"Tom: {COPILOT_SOUL_DEFAULT['tone']} "
            f"Nível de detalhamento: {COPILOT_SOUL_DEFAULT['detail_level']} "
            f"Estilo: {COPILOT_SOUL_DEFAULT['interaction_style']}"
        ),
        "updated_at": firestore.SERVER_TIMESTAMP,
        "created_by": "system_bootstrap",
    }
    try:
        ref = db.collection("system").document("copilot_soul")
        ref.set(payload, merge=True)
    except Exception:
        pass
    return payload


def _bootstrap_user_ai_profile(db, uid: str | None):
    if not uid:
        return {}

    now = time.monotonic()
    cached = _PROFILE_CACHE.get(uid)
    if cached and (now - cached[0]) < _DOC_CACHE_TTL:
        return cached[1]

    user_ref = db.collection("usuarios").document(uid)
    snap = user_ref.get()
    base_data = snap.to_dict() if snap.exists else {}
    ai_profile = dict((base_data or {}).get("ai_profile") or {})
    changed = False

    if not ai_profile.get("uid"):
        ai_profile["uid"] = uid
        changed = True

    if base_data:
        for src_key, dst_key in (
            ("nome", "nome"),
            ("cargo", "cargo"),
            ("setor", "setor"),
            ("email", "email"),
        ):
            if base_data.get(src_key) and not ai_profile.get(dst_key):
                ai_profile[dst_key] = base_data.get(src_key)
                changed = True

    if not ai_profile.get("preferences"):
        ai_profile["preferences"] = {
            "response_style": "objetivo",
            "memory_capture": "automatico_com_validacao",
        }
        changed = True

    if changed:
        ai_profile["updated_at"] = firestore.SERVER_TIMESTAMP
        user_ref.set({"ai_profile": ai_profile}, merge=True)

    _PROFILE_CACHE[uid] = (now, ai_profile)
    return ai_profile


def _format_ai_profile_for_prompt(ai_profile: dict) -> str:
    if not ai_profile:
        return "(perfil de usuário ainda não bootstrapado)"

    lines = []
    for key in ("nome", "cargo", "setor", "email"):
        value = ai_profile.get(key)
        if value:
            lines.append(f"- {key}: {value}")

    prefs = ai_profile.get("preferences") or {}
    if prefs:
        lines.append(f"- preferencias: {json.dumps(prefs, ensure_ascii=False)}")

    history = ai_profile.get("historico_deduzido") or []
    if history:
        lines.append(f"- historico_deduzido: {json.dumps(history[:5], ensure_ascii=False)}")

    return "\n".join(lines) if lines else "(perfil sem atributos relevantes)"


def _find_similar_memory_nodes(db, fato: str, api_key: str, limit: int = 5):
    fato = (fato or "").strip()
    if not fato:
        return []

    try:
        query_embedding = list(map(float, get_embedding(fato, api_key=api_key, task_type="RETRIEVAL_QUERY")))
    except Exception as exc:
        print(f"[Memoria] Falha ao gerar embedding da consulta: {exc}")
        return []

    candidates = []
    for snap in db.collection("knowledge_nodes").limit(200).stream():
        data = snap.to_dict() or {}
        if data.get("tipo") not in MEMORY_NODE_TYPES:
            continue
        node_embedding = data.get("embedding")
        if not node_embedding:
            continue
        try:
            similarity = _cosine_similarity(query_embedding, list(node_embedding))
        except Exception:
            continue
        candidates.append({
            "id": snap.id,
            "similarity": similarity,
            "data": data,
        })

    candidates.sort(key=lambda item: item["similarity"], reverse=True)
    return candidates[:limit]


def _build_memory_context(db, api_key: str, user_prompt: str, limit: int = 4) -> str:
    candidates = _find_similar_memory_nodes(db, user_prompt, api_key, limit=limit)
    if not candidates:
        return ""

    lines = []
    for item in candidates:
        data = item["data"]
        content = (
            data.get("texto_memoria")
            or data.get("resumo")
            or data.get("titulo")
            or ""
        ).strip()
        if not content:
            continue
        tipo = data.get("tipo", "fato_isolado")
        lines.append(
            f"- [{tipo}] {content[:350]} (id={item['id']}, similaridade={item['similarity']:.3f})"
        )
    if not lines:
        return ""
    return "[MEMÓRIAS GLOBAIS RELEVANTES]\n" + "\n".join(lines)


def _save_user_profile_signal(db, uid: str | None, prompt_text: str, task_id: str | None, system_id: str | None):
    if not uid or not prompt_text:
        return
    profile_ref = db.collection("usuarios").document(uid)
    doc = profile_ref.get()
    ai_profile = dict((doc.to_dict() or {}).get("ai_profile") or {})
    history = list(ai_profile.get("historico_deduzido") or [])
    snippet = prompt_text.strip().replace("\n", " ")
    if len(snippet) > 180:
        snippet = snippet[:177] + "..."
    entry = {
        "texto": snippet,
        "taskId": task_id or None,
        "systemId": system_id or None,
        "at": _iso_now_utc(),
    }
    if not history or history[-1].get("texto") != entry["texto"]:
        history.append(entry)
    ai_profile["historico_deduzido"] = history[-10:]
    ai_profile["last_task_id"] = task_id or ai_profile.get("last_task_id")
    ai_profile["last_system_id"] = system_id or ai_profile.get("last_system_id")
    ai_profile["updated_at"] = firestore.SERVER_TIMESTAMP
    profile_ref.set({"ai_profile": ai_profile}, merge=True)


def _should_consider_memory_by_heuristic(fato: str, categoria: str) -> tuple[bool, str]:
    text = (fato or "").strip()
    lower = text.lower()
    categoria_norm = _normalize_memory_category(categoria)

    if len(text) < MEMORY_MIN_FACT_LENGTH:
        return False, "too_short"

    noisy_prefixes = (
        "ok",
        "obrigado",
        "valeu",
        "bom dia",
        "boa tarde",
        "boa noite",
        "segue",
        "pode fazer",
        "confirmo",
        "cancelar",
        "teste",
    )
    if lower in noisy_prefixes:
        return False, "casual_reply"

    noisy_substrings = (
        "kkkk",
        "haha",
        "rsrs",
        "por favor",
        "obrigad",
        "bom trabalho",
        "isso mesmo",
        "pode seguir",
    )
    if any(token in lower for token in noisy_substrings):
        return False, "small_talk"

    transient_signals = (
        "hoje",
        "amanhã",
        "ontem",
        "agora",
        "daqui a pouco",
        "nesta conversa",
        "nessa conversa",
        "neste chat",
        "anexo",
        "arquivo enviado",
        "mensagem acima",
    )
    if categoria_norm == "fato_isolado" and any(token in lower for token in transient_signals):
        return False, "transient_context"

    durable_signals = (
        "sempre",
        "nunca",
        "regra",
        "procedimento",
        "padrão",
        "preferência",
        "preferencia",
        "convencao",
        "convenção",
        "fonte de verdade",
        "passamos a operar",
        "a partir de agora",
        "deve ser",
        "deve usar",
    )
    if categoria_norm == "regra_global" and any(token in lower for token in durable_signals):
        return True, "durable_rule_signal"

    return True, "heuristic_pass"


def _classify_memory_candidate(api_key: str, fato: str, categoria: str) -> dict:
    heuristic_ok, heuristic_reason = _should_consider_memory_by_heuristic(fato, categoria)
    if not heuristic_ok:
        return {
            "should_save": False,
            "reason": heuristic_reason,
            "confidence": 0.95,
            "normalized_category": _normalize_memory_category(categoria),
        }

    try:
        client = get_genai_module().Client(api_key=api_key)
        prompt = (
            "Você é um filtro de retenção cognitiva do Hermes.\n"
            "Decida se um fato deve ser salvo como memória global de longo prazo.\n"
            "Salve APENAS itens duráveis: regras de negócio, preferências operacionais estáveis, convenções permanentes ou fatos reutilizáveis.\n"
            "NÃO salve: small talk, confirmações momentâneas, contexto transitório, conteúdo efêmero de uma conversa, mensagens vagas ou ruído.\n"
            "Retorne APENAS JSON válido no formato:\n"
            "{\"should_save\":true|false,\"reason\":\"...\",\"confidence\":0.0,\"normalized_category\":\"regra_global|fato_isolado\"}\n\n"
            f"Categoria proposta: {_normalize_memory_category(categoria)}\n"
            f"Fato candidato: {fato}"
        )
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt
        )
        raw_text = (response.text or "").strip()
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        parsed = json.loads(json_match.group(0) if json_match else raw_text)
        return {
            "should_save": bool(parsed.get("should_save")),
            "reason": str(parsed.get("reason") or "llm_decision"),
            "confidence": float(parsed.get("confidence") or 0.0),
            "normalized_category": _normalize_memory_category(parsed.get("normalized_category") or categoria),
        }
    except Exception as exc:
        print(f"[Memoria] Fallback no classificador de retenção: {exc}")
        return {
            "should_save": True,
            "reason": heuristic_reason,
            "confidence": 0.51,
            "normalized_category": _normalize_memory_category(categoria),
        }


def _save_memory_node(
    db,
    api_key: str,
    fato: str,
    categoria: str,
    session_id: str | None = None,
    user_uid: str | None = None,
    force_update_id: str | None = None,
):
    fato = (fato or "").strip()
    if not fato:
        return {"status": "ignored", "reason": "empty_fact"}

    categoria_norm = _normalize_memory_category(categoria)
    fato_norm = _normalize_text_for_match(fato)
    embedding = list(map(float, get_embedding(fato, api_key=api_key, task_type="RETRIEVAL_DOCUMENT")))
    now = _iso_now_utc()

    if force_update_id:
        ref = db.collection("knowledge_nodes").document(force_update_id)
        snap = ref.get()
        if not snap.exists:
            return {"status": "error", "reason": "memory_not_found", "memory_id": force_update_id}
        current = snap.to_dict() or {}
        title = (fato[:72] + "...") if len(fato) > 72 else fato
        ref.set({
            "id": force_update_id,
            "titulo": title,
            "tipo": categoria_norm,
            "resumo": fato[:600],
            "texto_memoria": fato,
            "embedding": embedding,
            "data_atualizacao": now,
            "origem_memoria": "copiloto",
            "ultima_sessao_id": session_id,
            "ultimo_usuario_id": user_uid,
            "memoria_status": "ativa",
            "updated_from_conflict": True,
        }, merge=True)
        return {
            "status": "updated",
            "memory_id": force_update_id,
            "categoria": categoria_norm,
            "previous_text": current.get("texto_memoria") or current.get("resumo") or "",
        }

    candidates = _find_similar_memory_nodes(db, fato, api_key, limit=3)
    best = candidates[0] if candidates else None
    if best and best["similarity"] >= MEMORY_SIMILARITY_CREATE_THRESHOLD:
        best_data = best["data"]
        best_text = _normalize_text_for_match(best_data.get("texto_memoria") or best_data.get("resumo") or "")
        if best["similarity"] >= MEMORY_SIMILARITY_DUPLICATE_THRESHOLD or best_text == fato_norm:
            ref = db.collection("knowledge_nodes").document(best["id"])
            ref.set({
                "data_atualizacao": now,
                "ultima_sessao_id": session_id,
                "ultimo_usuario_id": user_uid,
                "ultimo_fato_observado": fato,
            }, merge=True)
            return {
                "status": "ignored",
                "reason": "duplicate",
                "memory_id": best["id"],
                "categoria": best_data.get("tipo") or categoria_norm,
                "similarity": round(best["similarity"], 4),
            }

        return {
            "status": "conflict",
            "memory_id": best["id"],
            "categoria_existente": best_data.get("tipo") or categoria_norm,
            "existing_text": best_data.get("texto_memoria") or best_data.get("resumo") or "",
            "similarity": round(best["similarity"], 4),
            "proposed_text": fato,
        }

    memory_id = str(uuid.uuid4())[:12]
    title = (fato[:72] + "...") if len(fato) > 72 else fato
    db.collection("knowledge_nodes").document(memory_id).set({
        "id": memory_id,
        "titulo": title,
        "tipo": categoria_norm,
        "resumo": fato[:600],
        "texto_memoria": fato,
        "embedding": embedding,
        "area_tematica": "GLOBAL",
        "n_tasks": 0,
        "task_ids": [],
        "data_criacao": now,
        "data_atualizacao": now,
        "origem_memoria": "copiloto",
        "ultima_sessao_id": session_id,
        "ultimo_usuario_id": user_uid,
        "memoria_status": "ativa",
    })
    return {
        "status": "saved",
        "memory_id": memory_id,
        "categoria": categoria_norm,
    }


def _format_pending_memory_conflict(conflict_data: dict | None) -> str:
    if not conflict_data:
        return ""
    existing_text = (conflict_data.get("existing_text") or "").strip()
    proposed_text = (conflict_data.get("proposed_text") or "").strip()
    if not existing_text or not proposed_text:
        return ""
    return (
        "[CONFLITO DE MEMÓRIA PENDENTE]\n"
        f"- memoria_id: {conflict_data.get('memory_id', '')}\n"
        f"- versao_existente: {existing_text}\n"
        f"- versao_proposta: {proposed_text}\n"
        "Se o usuário decidir, use resolver_conflito_memoria(memoria_id, decisao, fato_atualizado, categoria).\n"
        "decisao = 'manter_existente' ou 'substituir_pelo_novo'.\n"
    )


@scheduler_fn.on_schedule(
    schedule="0 4 * * *",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=180,
)
def consolidar_memorias_copiloto(event: scheduler_fn.ScheduledEvent):
    db = get_db()
    try:
        keys_doc = _cached_doc_get(db, "system", "api_keys")
        gemini_key = keys_doc.to_dict().get("gemini_api_key") if keys_doc.exists else None
        if not gemini_key:
            print("[Memoria] gemini_api_key indisponível; consolidação ignorada.")
            return

        client = get_genai_module().Client(api_key=gemini_key)
        nodes = []
        for snap in db.collection("knowledge_nodes").stream():
            data = snap.to_dict() or {}
            if data.get("tipo") not in MEMORY_NODE_TYPES:
                continue
            if data.get("memoria_status") == "consolidada":
                continue
            updated_at = data.get("data_atualizacao") or data.get("data_criacao") or ""
            nodes.append({"id": snap.id, "data": data, "updated_at": updated_at})

        processed_ids = set()
        merges = 0
        for current in nodes:
            if current["id"] in processed_ids:
                continue
            current_text = (current["data"].get("texto_memoria") or current["data"].get("resumo") or "").strip()
            if not current_text:
                continue
            similar = _find_similar_memory_nodes(db, current_text, gemini_key, limit=4)
            merge_candidates = []
            for candidate in similar:
                if candidate["id"] == current["id"]:
                    continue
                if candidate["similarity"] < 0.975:
                    continue
                candidate_text = (candidate["data"].get("texto_memoria") or candidate["data"].get("resumo") or "").strip()
                if not candidate_text:
                    continue
                merge_candidates.append({
                    "id": candidate["id"],
                    "tipo": candidate["data"].get("tipo") or current["data"].get("tipo") or "fato_isolado",
                    "texto": candidate_text,
                })

            if not merge_candidates:
                continue

            group = [{
                "id": current["id"],
                "tipo": current["data"].get("tipo") or "fato_isolado",
                "texto": current_text,
            }] + merge_candidates[:2]

            prompt = (
                "Você é um curador cognitivo do Hermes. Receberá memórias quase duplicadas.\n"
                "Una as memórias em UMA versão consolidada, removendo redundância e preservando a regra/fato mais útil.\n"
                "Retorne APENAS JSON válido no formato:\n"
                "{\"titulo\":\"...\",\"texto_memoria\":\"...\",\"tipo\":\"regra_global|fato_isolado\",\"ids_fundidos\":[\"id1\",\"id2\"]}\n\n"
                f"Memórias:\n{json.dumps(group, ensure_ascii=False)}"
            )
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt
            )
            raw_text = (response.text or "").strip()
            json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            merged = json.loads(json_match.group(0) if json_match else raw_text)
            fused_ids = [mid for mid in merged.get("ids_fundidos", []) if isinstance(mid, str)]
            if current["id"] not in fused_ids:
                fused_ids.insert(0, current["id"])

            keep_id = fused_ids[0]
            merged_text = (merged.get("texto_memoria") or current_text).strip()
            merged_tipo = _normalize_memory_category(merged.get("tipo"))
            merged_title = (merged.get("titulo") or merged_text[:72] or "Memória global").strip()
            merged_embedding = list(map(float, get_embedding(merged_text, api_key=gemini_key, task_type="RETRIEVAL_DOCUMENT")))

            db.collection("knowledge_nodes").document(keep_id).set({
                "titulo": merged_title[:80],
                "tipo": merged_tipo,
                "texto_memoria": merged_text,
                "resumo": merged_text[:600],
                "embedding": merged_embedding,
                "data_atualizacao": _iso_now_utc(),
                "consolidado_em": firestore.SERVER_TIMESTAMP,
                "origem_curadoria": "llm_cron",
            }, merge=True)

            for drop_id in fused_ids[1:]:
                db.collection("knowledge_nodes").document(drop_id).set({
                    "memoria_status": "consolidada",
                    "consolidado_no_id": keep_id,
                    "data_atualizacao": _iso_now_utc(),
                }, merge=True)
                processed_ids.add(drop_id)

            processed_ids.add(keep_id)
            merges += max(0, len(fused_ids) - 1)

        print(f"[Memoria] Consolidação concluída. merges={merges}")
    except Exception as exc:
        print(f"[Memoria] Falha na consolidação: {exc}")


def _resolve_telegram_chat_id_for_uid(db, uid: str | None):
    if not uid:
        return None
    try:
        user_doc = db.collection("usuarios").document(uid).get()
        if not user_doc.exists:
            return None
        data = user_doc.to_dict() or {}
        for key in ("telegram_chat_id", "telegramChatId", "chat_id", "telegram_id"):
            value = data.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
    except Exception as exc:
        print(f"[DeepResearch] Falha ao resolver telegram_chat_id para uid={uid}: {exc}")
    return None


def _resolve_default_telegram_chat_id(db):
    # 1. Tenta encontrar chat_id na coleção de usuários
    try:
        candidates = (
            db.collection("usuarios")
            .where("telegram_chat_id", "!=", None)
            .limit(1)
            .stream()
        )
        for doc in candidates:
            data = doc.to_dict() or {}
            value = data.get("telegram_chat_id")
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
    except Exception as exc:
        print(f"[Telegram] Falha ao resolver chat_id via usuarios: {exc}")

    # 2. Fallback Firestore: system/api_keys (mesmo doc do bot token)
    for key in ("telegram_chat_id", "telegram_allowed_chat_id", "allowed_telegram_chat_id"):
        try:
            keys_doc = _cached_doc_get(db, "system", "api_keys")
            if keys_doc.exists:
                value = (keys_doc.to_dict() or {}).get(key)
                if isinstance(value, (str, int)) and str(value).strip():
                    return str(value).strip()
        except Exception:
            pass

    # 3. Fallback Firestore: configuracoes/geral
    for key in ("telegram_chat_id", "telegram_allowed_chat_id"):
        try:
            cfg_doc = _cached_doc_get(db, "configuracoes", "geral")
            if cfg_doc.exists:
                value = (cfg_doc.to_dict() or {}).get(key)
                if isinstance(value, (str, int)) and str(value).strip():
                    return str(value).strip()
        except Exception:
            pass

    # 4. Fallback variável de ambiente
    env_chat_id = os.environ.get("ALLOWED_TELEGRAM_CHAT_ID")
    if env_chat_id and str(env_chat_id).strip():
        return str(env_chat_id).strip()

    return None


def _send_telegram_message_raw(db, chat_id: str | int | None, text: str):
    if not chat_id or not text:
        return False
    try:
        import requests

        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        bot_token = keys_doc.to_dict().get('telegram_bot_token') if keys_doc.exists else None
        bot_token = bot_token or os.environ.get('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            print("[Telegram] TELEGRAM_BOT_TOKEN nao configurado.")
            return False

        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": str(chat_id), "text": text},
            timeout=10
        )
        if not resp.ok:
            print(f"[Telegram] Falha ao enviar lembrete: {resp.status_code} {resp.text[:300]}")
            return False
        return True
    except Exception as exc:
        print(f"[Telegram] Erro ao enviar lembrete: {exc}")
        return False


def _build_task_reminder_telegram_message(task: dict, reminder_iso: str | None):
    title = (task.get('titulo') or 'Ação pendente').strip()
    status = (task.get('status') or 'não informado').strip()
    descricao = (task.get('descricao') or '').strip()
    reminder_label = ''
    if reminder_iso:
        try:
            reminder_dt = datetime.fromisoformat(str(reminder_iso))
            reminder_label = reminder_dt.strftime('%d/%m/%Y às %H:%M')
        except Exception:
            reminder_label = str(reminder_iso)

    plan_items = task.get('plano_acao') or []
    pending_steps = []
    for item in plan_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or '').strip()
        if text and not item.get('completed'):
            pending_steps.append(text)
        if len(pending_steps) >= 3:
            break

    lines = [
        "Lembrete de ação",
        f"Título: {title}",
    ]

    if reminder_label:
        lines.append(f"Agendado para: {reminder_label}")
    lines.append(f"Status atual: {status}")

    if descricao:
        resumo = descricao if len(descricao) <= 220 else f"{descricao[:217]}..."
        lines.append(f"Contexto: {resumo}")

    if pending_steps:
        lines.append("Próximas etapas:")
        for idx, step in enumerate(pending_steps, start=1):
            lines.append(f"{idx}. {step}")
    else:
        lines.append("Próximas etapas: revise a ação e defina o próximo passo operacional.")

    return "\n".join(lines)


def _normalize_task_reminders(task: dict):
    reminders = task.get('reminders') or []
    normalized = []
    if isinstance(reminders, list):
        for idx, reminder in enumerate(reminders):
            if not isinstance(reminder, dict):
                continue
            reminder_at = reminder.get('reminder_at')
            if not reminder_at:
                continue
            normalized.append({
                'id': str(reminder.get('id') or f"legacy-{idx}"),
                'reminder_at': str(reminder_at),
                'reminder_sent': bool(reminder.get('reminder_sent')),
                'created_at': str(reminder.get('created_at') or reminder_at),
            })

    if not normalized and task.get('reminder_at'):
        normalized.append({
            'id': 'legacy-reminder',
            'reminder_at': str(task.get('reminder_at')),
            'reminder_sent': bool(task.get('reminder_sent')),
            'created_at': str(task.get('data_atualizacao') or task.get('data_criacao') or task.get('reminder_at')),
        })

    normalized.sort(key=lambda item: item.get('reminder_at') or '')
    return normalized


def _build_task_reminder_state_payload(reminders: list[dict]):
    ordered = sorted(reminders, key=lambda item: item.get('reminder_at') or '')
    next_pending = next((item for item in ordered if not item.get('reminder_sent')), None)
    return {
        'reminders': ordered,
        'reminder_at': next_pending.get('reminder_at') if next_pending else None,
        'reminder_sent': bool(next_pending.get('reminder_sent')) if next_pending else True,
    }

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

        keys_doc = _cached_doc_get(db, 'system', 'api_keys')

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



@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
)
def criar_apresentacao_slides(req: https_fn.CallableRequest):
    """
    Persiste o esqueleto de apresentação confirmado pelo usuário no Firestore
    (coleção slides_drafts) e injeta o link tool:slides:{draftId} no histórico
    da sessão do Copiloto. Não invoca nenhum modelo de linguagem.
    """
    import json

    uid = req.auth.uid if req.auth else None
    if not uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Usuário não autenticado."
        )

    data = req.data or {}
    session_id = data.get('sessionId')
    tema_geral = (data.get('temaGeral') or '').strip()
    slides = data.get('slides')

    if not slides or not isinstance(slides, list):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Campo 'slides' é obrigatório e deve ser uma lista."
        )
    if not tema_geral:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Campo 'temaGeral' é obrigatório."
        )

    try:
        db = get_db()

        # 1. Persiste o draft na coleção slides_drafts
        draft_ref = db.collection('slides_drafts').add({
            "userId": uid,
            "sessionId": session_id or None,
            "tema_geral": tema_geral,
            "slides": slides,
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
        draft_id = draft_ref[1].id

        # 2. Injeta mensagem com o link no histórico da sessão
        if session_id:
            db.collection('sessoes_copiloto').document(session_id).collection('mensagens').add({
                "role": "assistant",
                "content": f"✅ Apresentação gerada com sucesso!\n\n[Abrir Apresentação](tool:slides:{draft_id})",
                "timestamp": firestore.SERVER_TIMESTAMP,
            })
            db.collection('sessoes_copiloto').document(session_id).set({
                "lastMessageAt": firestore.SERVER_TIMESTAMP
            }, merge=True)

        return {"draftId": draft_id}

    except Exception as e:
        print(f"Erro em criar_apresentacao_slides: {e}")
        import traceback
        print(traceback.format_exc())
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )


@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST", "OPTIONS"]),
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
)
def criar_formulario_google(req: https_fn.CallableRequest):
    """
    Cria um formulário no Google Forms a partir de um schema JSON validado
    (Draft-and-Approve) gerado pelo Copiloto e confirmado pelo usuário.
    Garante permissão pública por padrão via Google Drive API.
    """
    from googleapiclient.discovery import build

    uid = req.auth.uid if req.auth else None
    if not uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Usuário não autenticado."
        )

    data = req.data or {}
    session_id = data.get('sessionId')
    form_data = data.get('form')

    if not form_data or not isinstance(form_data, dict):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="O campo 'form' é obrigatório e deve ser um objeto JSON."
        )

    titulo = form_data.get('titulo')
    if not titulo:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="O formulário precisa ter um título ('titulo')."
        )

    descricao = form_data.get('descricao', '')
    perguntas = form_data.get('perguntas', [])

    try:
        creds = get_google_creds(GOOGLE_FORMS_SCOPES)
        forms_service = build('forms', 'v1', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)

        # 1. Cria o formulário inicial vazio (retorna um ID)
        new_form = {
            "info": {
                "title": titulo,
                "documentTitle": titulo
            }
        }
        form_result = forms_service.forms().create(body=new_form).execute()
        form_id = form_result.get('formId')
        responder_uri = form_result.get('responderUri')

        # 2. Configura a permissão do Drive para acesso público a respondentes
        try:
            drive_service.permissions().create(
                fileId=form_id,
                body={
                    'type': 'anyone',
                    'role': 'reader'
                }
            ).execute()
        except Exception as perm_err:
            print(f"[Forms] Aviso: Falha ao setar permissão pública via Drive API: {perm_err}")
            # Não falhamos toda a operação apenas por erro de permissão (ex: restrições do workspace)

        # 3. Monta as requisições em lote para popular o formulário
        requests = []

        # Adiciona a descrição
        if descricao:
            requests.append({
                "updateFormInfo": {
                    "info": {
                        "description": descricao
                    },
                    "updateMask": "description"
                }
            })

        # Processa as perguntas
        for i, q in enumerate(perguntas):
            tipo = q.get('tipo', 'texto_curto')
            texto = q.get('texto', 'Pergunta sem título')
            obrigatoria = bool(q.get('obrigatoria', False))

            question_item = {
                "question": {
                    "required": obrigatoria,
                }
            }

            if tipo == 'texto_curto':
                question_item["question"]["textQuestion"] = {"paragraph": False}
            elif tipo == 'paragrafo':
                question_item["question"]["textQuestion"] = {"paragraph": True}
            elif tipo in ['multipla_escolha', 'caixas_selecao', 'lista_suspensa']:
                opcoes = q.get('opcoes', ['Opção 1'])
                options_list = [{"value": opt} for opt in opcoes]

                choice_type = "RADIO"
                if tipo == 'caixas_selecao':
                    choice_type = "CHECKBOX"
                elif tipo == 'lista_suspensa':
                    choice_type = "DROP_DOWN"

                question_item["question"]["choiceQuestion"] = {
                    "type": choice_type,
                    "options": options_list
                }
            elif tipo == 'escala_linear':
                question_item["question"]["scaleQuestion"] = {
                    "low": q.get('escala_min', 1),
                    "high": q.get('escala_max', 5),
                    "lowLabel": q.get('rotulo_min', ''),
                    "highLabel": q.get('rotulo_max', '')
                }
            else:
                # Fallback
                question_item["question"]["textQuestion"] = {"paragraph": False}

            requests.append({
                "createItem": {
                    "item": {
                        "title": texto,
                        "questionItem": question_item
                    },
                    "location": {
                        "index": i
                    }
                }
            })

        if requests:
            forms_service.forms().batchUpdate(
                formId=form_id,
                body={"requests": requests}
            ).execute()

        return {"formId": form_id, "responderUri": responder_uri}

    except Exception as e:
        print(f"Erro em criar_formulario_google: {e}")
        import traceback
        print(traceback.format_exc())
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )
@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
)
def diagnosticar_codigo(req: https_fn.CallableRequest):
    """
    Dois modos roteados pela IA:
      - 'repo'    : acessa o repositório GitHub do sistema, seleciona arquivos relevantes
                    e gera diagnóstico com contexto completo do projeto.
      - 'snippet' : analisa diretamente o código colado pelo usuário, sem acesso ao repo.
    Ambos os modos produzem blocos SEARCH/REPLACE e um arquivo hermes_refactor.md.
    """
    import requests as http_requests
    import json
    import re

    data = req.data or {}
    session_id = data.get('sessionId')
    uid = req.auth.uid if req.auth else None
    if not uid and data.get('bridgeChannel') == 'telegram' and session_id:
        try:
            bridge_db = get_db()
            session_doc = bridge_db.collection('sessoes_copiloto').document(session_id).get()
            session_data = session_doc.to_dict() or {} if session_doc.exists else {}
            if session_data.get('channel') == 'telegram':
                uid = session_data.get('userId') or f"telegram:{session_data.get('telegramChatId') or session_id}"
        except Exception as bridge_auth_err:
            print(f"[diagnosticar_codigo] Falha no bridge auth Telegram: {bridge_auth_err}")
    if not uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Autenticação necessária."
        )

    task_id = req.data.get('taskId')
    descricao_problema = req.data.get('descricaoProblema', '').strip()
    mode = req.data.get('mode', 'repo')  # 'repo' | 'snippet'

    # Campos específicos por modo
    sistema_id = req.data.get('sistemaId', '').strip()
    code_snippet = req.data.get('codeSnippet', '').strip()
    file_name = req.data.get('fileName', 'snippet').strip() or 'snippet'

    if not descricao_problema:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="descricaoProblema é obrigatório."
        )
    if mode == 'repo' and not sistema_id:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="sistemaId é obrigatório no modo repo."
        )
    if mode == 'snippet' and not code_snippet:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="codeSnippet é obrigatório no modo snippet."
        )

    try:
        from google import genai
        from google.genai import types

        db = get_db()

        # ── Credenciais comuns ─────────────────────────────────────────────────
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        keys = keys_doc.to_dict() if keys_doc.exists else {}
        gemini_api_key = keys.get('gemini_api_key')

        if not gemini_api_key:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
                message="Chave Gemini não configurada."
            )

        client = genai.Client(api_key=gemini_api_key)

        def extract_json(text):
            if not text:
                return ""
            cleaned = text.strip()
            if '```json' in cleaned:
                return cleaned.split('```json', 1)[1].split('```', 1)[0].strip()
            if '```' in cleaned:
                return cleaned.split('```', 1)[1].split('```', 1)[0].strip()
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            if start != -1 and end != -1 and end > start:
                return cleaned[start:end + 1]
            return cleaned

        def normalize_diag_data(raw_text, parsed_data, fallback_files):
            parsed_data = parsed_data if isinstance(parsed_data, dict) else {}

            diagnostico = parsed_data.get('diagnostico')
            if not isinstance(diagnostico, str):
                diagnostico = ''
            diagnostico = diagnostico.strip()

            raw_text = (raw_text or '').strip()
            extracted_text = extract_json(raw_text)
            raw_without_json = raw_text if raw_text == extracted_text else raw_text.replace(extracted_text, '').strip()

            arquivos_impactados = parsed_data.get('arquivos_impactados')
            if not isinstance(arquivos_impactados, list):
                arquivos_impactados = []
            arquivos_impactados = [str(item).strip() for item in arquivos_impactados if str(item).strip()]
            if not arquivos_impactados:
                arquivos_impactados = list(fallback_files)

            blocos_sr = parsed_data.get('blocos_sr')
            if not isinstance(blocos_sr, list):
                blocos_sr = []
            blocos_sr_normalizados = []
            for bloco in blocos_sr:
                if not isinstance(bloco, dict):
                    continue
                bloco_norm = {
                    'arquivo': str(bloco.get('arquivo', '')).strip(),
                    'descricao': str(bloco.get('descricao', '')).strip(),
                    'search': str(bloco.get('search', '')).strip('\n'),
                    'replace': str(bloco.get('replace', '')).strip('\n'),
                }
                if any(bloco_norm.values()):
                    blocos_sr_normalizados.append(bloco_norm)

            alerta_impacto = parsed_data.get('alerta_impacto')
            if not isinstance(alerta_impacto, str):
                alerta_impacto = ''
            alerta_impacto = alerta_impacto.strip()

            if not diagnostico:
                if raw_without_json:
                    diagnostico = raw_without_json
                elif raw_text:
                    diagnostico = raw_text
                elif blocos_sr_normalizados:
                    diagnostico = (
                        "O modelo retornou sugestoes de alteracao, mas nao preencheu o campo "
                        "'diagnostico' em formato estruturado."
                    )
                else:
                    diagnostico = (
                        "Nao foi possivel estruturar a analise automatica em texto. "
                        "Revise os arquivos impactados e tente gerar o diagnostico novamente."
                    )

            if not alerta_impacto:
                alerta_impacto = 'Verifique os modulos dependentes antes de aplicar.'

            return {
                'diagnostico': diagnostico,
                'arquivos_impactados': arquivos_impactados,
                'alerta_impacto': alerta_impacto,
                'blocos_sr': blocos_sr_normalizados,
            }

        # ══════════════════════════════════════════════════════════════════════
        # MODO SNIPPET — analisa código colado diretamente, sem acesso ao repo
        # ══════════════════════════════════════════════════════════════════════
        if mode == 'snippet':
            task_ctx = f'\nContexto de tarefa (ID): {task_id}' if task_id else ''
            snippet_label = f'snippet · {file_name}'

            snippet_prompt = (
                "Você é um engenheiro de software sênior especialista em diagnóstico e refatoração.\n\n"
                f"## CONTEXTO{task_ctx}\n"
                f"Arquivo: {file_name}\n"
                f"Problema relatado: {descricao_problema}\n\n"
                f"## CÓDIGO FORNECIDO\n```\n{code_snippet}\n```\n\n"
                "## TAREFA\n"
                "Analise o código e gere um diagnóstico técnico completo.\n"
                "Retorne APENAS um JSON válido (sem markdown) com esta estrutura exata:\n"
                '{\n'
                '  "diagnostico": "causa raiz em 2-4 parágrafos",\n'
                '  "arquivos_impactados": ["' + file_name + '"],\n'
                '  "alerta_impacto": "riscos de quebra ao aplicar a correção",\n'
                '  "blocos_sr": [\n'
                '    {\n'
                f'      "arquivo": "{file_name}",\n'
                '      "descricao": "o que esta correção faz",\n'
                '      "search": "trecho original EXATO com 2-3 linhas de contexto antes e depois",\n'
                '      "replace": "trecho corrigido completo"\n'
                '    }\n'
                '  ]\n'
                '}\n\n'
                "Regras para SEARCH/REPLACE:\n"
                "1. O bloco search deve ser copiado LITERALMENTE do código fornecido\n"
                "2. Inclua 2-3 linhas de contexto para âncora única\n"
                "3. O bloco replace contém o código corrigido (mantenha indentação)"
            )

            snip_resp = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=snippet_prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            snip_text = (snip_resp.text or '').strip()
            try:
                diag_data = normalize_diag_data(snip_text, json.loads(extract_json(snip_text)), [file_name])
            except Exception as e:
                print(f"Erro ao parsear diagnostico de snippet: {e}")
                diag_data = normalize_diag_data(snip_text, {}, [file_name])
            blocos_sr = diag_data.get('blocos_sr', [])
            files_analyzed = [file_name]

            md_header = [
                "# Hermes — Diagnóstico de Código (Snippet)",
                f"**Arquivo:** `{file_name}`  ",
                f"**Problema:** {descricao_problema}",
            ]

        # ══════════════════════════════════════════════════════════════════════
        # MODO REPO — acessa GitHub, seleciona arquivos, analisa com contexto
        # ══════════════════════════════════════════════════════════════════════
        else:
            github_token = keys.get('github_token')
            if not github_token:
                raise https_fn.HttpsError(
                    code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
                    message="GitHub token não configurado em system/api_keys."
                )

            # Busca URL do repositório
            sistema_doc = db.collection('sistemas_detalhes').document(sistema_id).get()
            
            # Fallback robusto: busca case-insensitive ignorando prefixos como 'SISTEMA:'
            if not sistema_doc.exists:
                sistemas_all = db.collection('sistemas_detalhes').get()
                target_id = sistema_id.strip().lower().replace('sistema:', '')
                
                for doc in sistemas_all:
                    data = doc.to_dict() or {}
                    # Normaliza IDs e Nomes para comparação
                    doc_id_norm = doc.id.strip().lower().replace('sistema:', '')
                    doc_name_norm = (data.get('nome') or "").strip().lower().replace('sistema:', '')
                    
                    if doc_id_norm == target_id or doc_name_norm == target_id or target_id in (data.get('repositorio_principal') or "").lower():
                        sistema_doc = doc
                        break
            
            if not sistema_doc.exists:
                raise https_fn.HttpsError(
                    code=https_fn.FunctionsErrorCode.NOT_FOUND,
                    message=f"Sistema '{sistema_id}' não encontrado em sistemas_detalhes."
                )
            
            repo_url = (sistema_doc.to_dict() or {}).get('repositorio_principal', '').strip()
            if not repo_url:
                raise https_fn.HttpsError(
                    code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
                    message="Campo 'repositorio_principal' não configurado para este sistema."
                )

            match = re.match(r'https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$', repo_url)
            if not match:
                raise https_fn.HttpsError(
                    code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                    message=f"URL de repositório inválida: {repo_url}"
                )
            owner, repo = match.group(1), match.group(2)
            snippet_label = f'{owner}/{repo}'

            gh_headers = {
                'Authorization': f'token {github_token}',
                'Accept': 'application/vnd.github.v3+json',
            }

            # Branch padrão
            repo_info = http_requests.get(
                f'https://api.github.com/repos/{owner}/{repo}',
                headers=gh_headers, timeout=30
            )
            if repo_info.status_code != 200:
                raise https_fn.HttpsError(
                    code=https_fn.FunctionsErrorCode.INTERNAL,
                    message=f"Erro ao acessar repositório GitHub ({repo_info.status_code})."
                )
            default_branch = repo_info.json().get('default_branch', 'main')

            # Árvore completa
            tree_resp = http_requests.get(
                f'https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1',
                headers=gh_headers, timeout=30
            )
            if tree_resp.status_code != 200:
                raise https_fn.HttpsError(
                    code=https_fn.FunctionsErrorCode.INTERNAL,
                    message=f"Erro ao buscar árvore do repositório ({tree_resp.status_code})."
                )

            ignore_patterns = (
                'node_modules/', '.git/', 'dist/', 'build/', '__pycache__/',
                '.pytest_cache/', 'venv/', '.venv/', '.next/', 'coverage/',
            )
            code_extensions = {
                '.py', '.ts', '.tsx', '.js', '.jsx', '.css', '.json', '.html',
                '.md', '.yaml', '.yml', '.sh', '.sql', '.go', '.rs', '.java',
                '.kt', '.swift', '.dart', '.env.example', '.toml', '.cfg',
            }
            all_blobs = [
                f['path'] for f in tree_resp.json().get('tree', [])
                if f.get('type') == 'blob'
            ]
            filtered_files = []
            for fp in all_blobs:
                if any(ign in fp for ign in ignore_patterns):
                    continue
                ext = '.' + fp.split('.')[-1].lower() if '.' in fp.split('/')[-1] else ''
                if ext in code_extensions:
                    filtered_files.append(fp)

            # Gemini seleciona arquivos relevantes
            file_list_text = '\n'.join(filtered_files[:400])
            selection_prompt = (
                f"Você é um engenheiro sênior analisando o repositório GitHub `{owner}/{repo}`.\n\n"
                f"Objetivo/Problema: {descricao_problema}\n\n"
                f"Lista de arquivos:\n{file_list_text}\n\n"
                "Selecione os arquivos mais relevantes para resolver o problema ou implementar o recurso (máx. 10).\n"
                "Priorize arquivos de lógica (services, controllers, components) em vez de configurações.\n"
                "Retorne APENAS um JSON válido (sem markdown):\n"
                '{"arquivos": ["path/file1"], "justificativa": "breve explicação"}'
            )
            sel_resp = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=selection_prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            sel_text = (sel_resp.text or '').strip()
            
            # Extração robusta de JSON
            def extract_json(text):
                if '```json' in text:
                    return text.split('```json')[1].split('```')[0].strip()
                if '```' in text:
                    return text.split('```')[1].split('```')[0].strip()
                # Tenta localizar por chaves se não houver markdown
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1:
                    return text[start:end+1]
                return text

            sel_text = extract_json(sel_text)
            
            try:
                selected_files = json.loads(sel_text).get('arquivos', [])[:8]
            except Exception as e:
                print(f"Erro ao parsear arquivos selecionados: {e}")
                print(f"Texto original: {sel_text}")
                selected_files = []

            # Baixa conteúdo (máx. 50 KB cada) via API de Content (suporta repos privados)
            files_content = {}
            for fp in selected_files:
                try:
                    # Usamos a API de contents com header raw para suportar tokens em repos privados
                    raw_api_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{fp}?ref={default_branch}'
                    raw_resp = http_requests.get(
                        raw_api_url, 
                        headers={**gh_headers, 'Accept': 'application/vnd.github.v3.raw'}, 
                        timeout=15
                    )
                    if raw_resp.status_code == 200:
                        content = raw_resp.text
                        if len(content) > 50000:
                            content = content[:50000] + '\n... [TRUNCADO]'
                        files_content[fp] = content
                    else:
                        print(f"Falha ao baixar {fp} ({raw_api_url}): Status {raw_resp.status_code}")
                except Exception as fetch_err:
                    print(f"Erro ao baixar {fp}: {fetch_err}")

            files_context = '\n\n'.join(
                f'### {path}\n```\n{content}\n```'
                for path, content in files_content.items()
            )
            task_ctx = f'\nContexto de tarefa (ID): {task_id}' if task_id else ''

            diagnosis_prompt = (
                "Você é um engenheiro de software sênior especialista em arquitetura e implementação.\n\n"
                f"## CONTEXTO\nRepositório: {owner}/{repo}{task_ctx}\n"
                f"Demanda/Problema: {descricao_problema}\n\n"
                f"## CÓDIGO FONTE ATUAL\n{files_context}\n\n"
                "## TAREFA\n"
                "Analise o código e proponha a solução/correção.\n"
                "Se for um bug, identifique a causa raiz. Se for um recurso novo, identifique os pontos de inserção.\n"
                "Retorne APENAS um JSON válido (sem markdown):\n"
                '{\n'
                '  "diagnostico": "análise técnica em 2-4 parágrafos (causa raiz ou plano de implementação)",\n'
                '  "arquivos_impactados": ["path/file.py"],\n'
                '  "alerta_impacto": "riscos de quebra ou dependências necessárias",\n'
                '  "blocos_sr": [{\n'
                '    "arquivo": "path/file.py",\n'
                '    "descricao": "breve descrição da alteração neste bloco",\n'
                '    "search": "código original EXATO (2-3 linhas de contexto para âncora)",\n'
                '    "replace": "código completo corrigido/atualizado (mantenha indentação)"\n'
                '  }]\n'
                '}\n\n'
                "REGRAS CRÍTICAS:\n"
                "1. O campo 'search' deve ser ABSOLUTAMENTE IDÊNTICO ao conteúdo original nos arquivos acima.\n"
                "2. Se for criar código novo dentro de uma classe/função, inclua as linhas vizinhas no 'search'.\n"
                "3. Se for um arquivo novo ou se não houver código para substituir, omita o bloco ou use uma âncora clara."
            )
            diag_resp = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=diagnosis_prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            diag_text = (diag_resp.text or '').strip()
            try:
                diag_data = normalize_diag_data(diag_text, json.loads(extract_json(diag_text)), list(files_content.keys()))
            except Exception as e:
                print(f"Erro ao parsear diagnóstico: {e}")
                print(f"Texto bruto do diagnÃ³stico: {diag_text}")
                diag_data = normalize_diag_data(diag_text, {}, list(files_content.keys()))
            blocos_sr = diag_data.get('blocos_sr', [])
            files_analyzed = list(files_content.keys())

            md_header = [
                "# Hermes — Diagnóstico de Código",
                f"**Repositório:** `{owner}/{repo}`  ",
                f"**Sistema:** `{sistema_id}`  ",
                f"**Problema:** {descricao_problema}",
            ]

        # ── Geração do Markdown de handoff (comum a ambos os modos) ──────────
        md_lines = md_header + [
            "",
            "---",
            "",
            "## Diagnóstico da Falha",
            "",
            diag_data.get('diagnostico', ''),
            "",
            "---",
            "",
            "## Arquivos Impactados",
            "",
        ]
        for f in diag_data.get('arquivos_impactados', []):
            md_lines.append(f"- `{f}`")
        md_lines += [
            "",
            "---",
            "",
            "## Instruções de Refatoração",
            "",
            "> **Como usar:** Arraste este arquivo para o chat da sua IA no VS Code "
            "(Cursor, GitHub Copilot, Aider) e instrua: "
            "_\"Aplique as correções contidas neste arquivo\"_",
            "",
        ]
        for i, bloco in enumerate(blocos_sr, 1):
            md_lines += [
                f"### Correção {i}: {bloco.get('descricao', '')}",
                "",
                f"**Arquivo:** `{bloco.get('arquivo', '')}`",
                "",
                "<<<<<<< SEARCH",
                bloco.get('search', ''),
                "=======",
                bloco.get('replace', ''),
                ">>>>>>> REPLACE",
                "",
                "---",
                "",
            ]
        md_lines += [
            "## Alerta de Impacto",
            "",
            f"⚠️ {diag_data.get('alerta_impacto', 'Verifique os módulos dependentes antes de aplicar.')}",
            "",
            "---",
            f"_Gerado pelo Hermes Copiloto · modo {mode}_",
        ]
        md_content = '\n'.join(md_lines)

        # ── Persiste em diagnosticos_codigo ───────────────────────────────────
        diag_ref = db.collection('diagnosticos_codigo').add({
            'uid': uid,
            'sessionId': session_id,
            'taskId': task_id,
            'mode': mode,
            'sistemaId': sistema_id or None,
            'nomeRepositorio': snippet_label,
            'descricaoProblema': descricao_problema,
            'arquivosAnalisados': files_analyzed,
            'diagnostico': diag_data.get('diagnostico', ''),
            'blocosSR': blocos_sr,
            'alertaImpacto': diag_data.get('alerta_impacto', ''),
            'markdownContent': md_content,
            'criadoEm': firestore.SERVER_TIMESTAMP,
        })
        diag_id = diag_ref[1].id

        # ── Injeta mensagem na sessão ─────────────────────────────────────────
        if session_id:
            try:
                modo_label = "snippet" if mode == "snippet" else f"repositório `{snippet_label}`"
                db.collection('sessoes_copiloto').document(session_id).collection('mensagens').add({
                    'role': 'assistant',
                    'content': (
                        f'✅ **Diagnóstico concluído!** '
                        f'{len(blocos_sr)} correção(ões) em {len(files_analyzed)} arquivo(s) '
                        f'({modo_label}).\n\n'
                        f'[Abrir Diagnóstico](tool:diagnosis:{diag_id})'
                    ),
                    'timestamp': firestore.SERVER_TIMESTAMP,
                })
                db.collection('sessoes_copiloto').document(session_id).set({
                    'lastMessageAt': firestore.SERVER_TIMESTAMP,
                }, merge=True)
            except Exception as msg_err:
                print(f"Erro ao injetar mensagem de diagnóstico: {msg_err}")

        return {'diagId': diag_id}

    except https_fn.HttpsError:
        raise
    except Exception as e:
        print(f"Erro em diagnosticar_codigo: {e}")
        import traceback
        print(traceback.format_exc())
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )


@https_fn.on_call(memory=options.MemoryOption.MB_512, timeout_sec=30)
def corrigir_sintaxe_mermaid(req: https_fn.CallableRequest):
    """
    Recebe código Mermaid inválido e o erro do compilador JS, retorna apenas o código corrigido.
    Chamado pelo self-healing loop do componente MermaidBlock no frontend (máx. 3 tentativas).
    """
    from google import genai
    from google.genai import types

    uid = req.auth.uid if req.auth else None
    if not uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Usuário não autenticado."
        )

    data = req.data or {}
    codigo_mermaid = (data.get('codigoMermaid') or '').strip()
    erro_compilador = (data.get('erroCompilador') or '').strip()

    if not codigo_mermaid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Campo 'codigoMermaid' é obrigatório."
        )

    try:
        db = get_db()
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        gemini_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

        if not gemini_key:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INTERNAL,
                message="Chave Gemini não configurada."
            )

        client = genai.Client(api_key=gemini_key)

        system_instruction = (
            "Você é um especialista em sintaxe Mermaid. "
            "Receberá um código Mermaid inválido e o erro gerado pelo compilador. "
            "Retorne APENAS o código Mermaid corrigido — sem blocos de markdown (não inclua ```mermaid), "
            "sem explicações, sem texto adicional. "
            "Mantenha o tipo de diagrama original. Corrija somente a sintaxe."
        )

        user_message = (
            f"Código Mermaid inválido:\n{codigo_mermaid}\n\n"
            f"Erro do compilador:\n{erro_compilador}"
        )

        response = client.models.generate_content(
            model='gemini-2.0-flash',
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,
                max_output_tokens=2048,
            ),
            contents=user_message,
        )

        codigo_corrigido = (response.text or '').strip()
        # Strip markdown wrapper defensively in case the model added it anyway
        if codigo_corrigido.startswith('```mermaid'):
            codigo_corrigido = codigo_corrigido[10:].strip()
        if codigo_corrigido.startswith('```'):
            codigo_corrigido = codigo_corrigido[3:].strip()
        if codigo_corrigido.endswith('```'):
            codigo_corrigido = codigo_corrigido[:-3].strip()

        return {'codigoCorrigido': codigo_corrigido}

    except https_fn.HttpsError:
        raise
    except Exception as e:
        print(f"Erro em corrigir_sintaxe_mermaid: {e}")
        import traceback
        print(traceback.format_exc())
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )


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

        keys_doc = _cached_doc_get(db, 'system', 'api_keys')

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
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        
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
    from firebase_admin import firestore

    data = req.data or {}
    prompt = data.get('prompt')
    history_context = data.get('historyContext')
    area_tematica = data.get('area_tematica')
    rag_context_id = data.get('ragContext')
    extra_context_id = data.get('extraContextId')
    knowledge_item_ids = data.get('knowledgeItemIds', [])
    kg_tags = data.get('kgTags', [])

    if not isinstance(prompt, str) or not prompt.strip():
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="O comando é obrigatório."
        )

    try:
        db = get_db()

        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
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

        # --- DADOS FINANCEIROS (Módulo Financeiro) ---
        finance_context = ""
        if area_tematica == 'FINANCEIRO':
            try:
                from datetime import datetime
                import json
                from tools.telegram_extended import execute
                
                now = datetime.now()
                mes_atual = now.month - 1
                ano_atual = now.year
                
                fin_data_atual = execute("consultar_financas_v2", {"mes": mes_atual, "ano": ano_atual}, db)
                data_json = json.loads(fin_data_atual)
                
                resumo = data_json.get("resumo", {})
                metas = data_json.get("metas", [])
                reserva = data_json.get("reserva_emergencia", {})
                detalhes = data_json.get("detalhes", {})
                
                parts = []
                parts.append("=== DADOS FINANCEIROS ATUAIS ===")
                parts.append(f"Período: {mes_atual+1}/{ano_atual}")
                parts.append(f"Renda Total: R$ {resumo.get('total_renda', 0):.2f} (Recebida: R$ {resumo.get('renda_recebida', 0):.2f})")
                parts.append(f"Contas Totais: R$ {resumo.get('total_contas', 0):.2f} (Pagas: R$ {resumo.get('contas_pagas', 0):.2f})")
                parts.append(f"Saldo Previsto: R$ {resumo.get('saldo_previsto', 0):.2f}")
                parts.append(f"Saldo Atual: R$ {resumo.get('saldo_atual', 0):.2f}")
                
                parts.append("\nReserva de Emergência:")
                parts.append(f"- Alvo: R$ {reserva.get('alvo', 0):.2f}")
                parts.append(f"- Atual: R$ {reserva.get('atual', 0):.2f}")
                
                parts.append("\nMetas Financeiras:")
                for meta in metas:
                    parts.append(f"- {meta.get('name')}: R$ {meta.get('targetAmount', 0):.2f} (Prioridade: {meta.get('priority')})")
                
                parts.append("\nRendas Detalhadas:")
                for r in detalhes.get("rendas", []):
                    status = "Recebido" if r.get("isReceived") else "Pendente"
                    parts.append(f"- {r.get('description')}: R$ {r.get('amount', 0):.2f} ({status}, Categoria: {r.get('category')})")
                
                parts.append("\nContas Detalhadas:")
                for c in detalhes.get("contas", []):
                    status = "Pago" if c.get("isPaid") else "Pendente"
                    parts.append(f"- {c.get('description')}: R$ {c.get('amount', 0):.2f} ({status}, Categoria: {c.get('category')})")
                
                trans_docs = db.collection("finance_transactions").where("status", "==", "active").stream()
                avulsas = []
                for doc in trans_docs:
                    d = doc.to_dict()
                    date_str = d.get("date")
                    if date_str:
                        try:
                            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            if dt.month - 1 == mes_atual and dt.year == ano_atual:
                                avulsas.append(d)
                        except:
                            pass
                
                if avulsas:
                    parts.append("\nTransações Avulsas do Mês:")
                    for t in avulsas:
                        parts.append(f"- {t.get('description')}: R$ {t.get('amount', 0):.2f} (Sprint {t.get('sprint')}, Categoria: {t.get('category')})")
                
                finance_context = "\n".join(parts)
            except Exception as e:
                print(f"Erro ao extrair dados financeiros: {e}")

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

        {finance_context if finance_context else ''}

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
            "kg_nodes": kg_nodes_payload,
        }

    except https_fn.HttpsError:
        raise
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
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
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
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST", "OPTIONS"]),
    memory=options.MemoryOption.GB_1,
    timeout_sec=COPILOT_FUNCTION_TIMEOUT_SEC
)
def askCopilotoHermes(req: https_fn.CallableRequest):
    """
    Módulo Copiloto Hermes
    Estrategista sênior de processos com Tool Calling e RAG Híbrido.
    """
    from google import genai
    from google.genai import types

    data = req.data or {}
    perf_state = {"start_ms": _perf_now_ms(), "_last_ms": _perf_now_ms(), "steps": [], "tool_calls": []}
    request_start_monotonic = time.monotonic()
    prompt = (data.get('prompt') or "").strip()
    task_id = data.get('taskId')
    system_id = data.get('systemId')
    session_id = data.get('sessionId')
    drive_file_id = data.get('driveFileId')
    drive_file_name = (data.get('driveFileName') or 'documento').strip()
    routing_index = data.get('routingIndex') or []
    user_uid = req.auth.uid if req.auth else None

    def _copilot_remaining_sec() -> float:
        elapsed = time.monotonic() - request_start_monotonic
        return max(0.0, COPILOT_SOFT_DEADLINE_SEC - elapsed)

    # Ingestão muda: arquivo sem texto → prompt padrão de catalogação
    if not prompt and drive_file_id:
        prompt = (
            "Analise o arquivo anexado, identifique o que ele mostra e explique "
            "como isso se relaciona com a ação em contexto."
        )

    if not prompt:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Prompt é obrigatório."
        )

    try:
        db = get_db()
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        gemini_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

        if not gemini_key:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
                message="Chave Gemini não configurada."
            )

        client = genai.Client(api_key=gemini_key)
        copilot_core = _get_copilot_core(db)
        copilot_soul = _get_copilot_soul(db)
        ai_profile = _bootstrap_user_ai_profile(db, user_uid)
        threading.Thread(
            target=_save_user_profile_signal,
            args=(db, user_uid, prompt, task_id, system_id),
            daemon=True,
        ).start()
        _prompt_words = [w for w in prompt.lower().split() if len(w) > 2]
        memory_context = _build_memory_context(db, gemini_key, prompt, limit=4) if len(_prompt_words) >= 4 else ""
        matched_pop_directives = _match_pop_directives(db, prompt)
        _perf_mark(perf_state, "web.bootstrap")

        tools_routing_context = ""
        if routing_index:
            tools_routing_context = "\n\n## CATÁLOGO DE FERRAMENTAS DISPONÍVEIS\n"
            tools_routing_context += "Você pode acionar ferramentas interativas na interface do usuário usando a função `acionar_ferramenta`. "
            tools_routing_context += "Não peça permissão para usar as ferramentas, acione-as diretamente se a intenção do usuário bater com as chaves (keys) ou a tag abaixo:\n\n"
            for t in routing_index:
                tools_routing_context += f"- ID da Ferramenta: {t['id']}\n"
                tools_routing_context += f"  Tag Explícita: {t.get('tag', '')}\n"
                tools_routing_context += f"  Chaves de Ativação (Keys): {', '.join(t.get('keys', []))}\n\n"
            tools_routing_context += "ATENÇÃO: Caso o usuário use uma Tag Explícita (ex: @SlidesTool) mas o texto do pedido exija algo totalmente diferente (ex: 'Gerar nota fiscal'), seja juiz semântico, suspenda o acionamento e alerte-o sobre a contradição.\n"

        session_conflict_context = ""
        session_ref = None
        if session_id:
            session_ref = db.collection('sessoes_copiloto').document(session_id)
            try:
                session_doc = session_ref.get()
                if session_doc.exists:
                    session_conflict_context = _format_pending_memory_conflict(
                        (session_doc.to_dict() or {}).get("pendingMemoryConflict")
                    )
            except Exception as session_err:
                print(f"[Memoria] Falha ao ler conflito pendente da sessão {session_id}: {session_err}")

        # --- DEFINIÇÃO DE FERRAMENTAS ---
        _perf_mark(perf_state, "web.session_context")
        def consultar_historico_acoes(query: str, area_tematica: str = None, data_limite_inicio: str = None, data_limite_fim: str = None, ultimas_n_acoes: int = 20, status: str = None):
            """
            Busca tarefas reais no banco de dados do Hermes por texto, area, prazo e/ou status.
            Retorna somente dados oficiais — nao mistura com RAG ou procedimentos.
            Use status para filtrar (ex: 'em andamento', 'concluido', 'cancelado').
            Use data_limite_inicio e data_limite_fim (YYYY-MM-DD) para filtrar por prazo.
            Use ultimas_n_acoes (default 20) para buscar em lote.
            """
            from tools.busca_grafo import buscar_tarefas
            _STOPWORDS_Q = {"de", "a", "o", "que", "e", "do", "da", "em", "um", "uma",
                            "os", "as", "no", "na", "com", "por", "para", "dos", "das",
                            "nos", "nas", "ao", "os", "se", "ou"}
            _q_terms = [w for w in query.lower().split() if w not in _STOPWORDS_Q and len(w) > 2]
            _initial_mode = "all" if len(_q_terms) >= 2 else "any"
            res_exact = buscar_tarefas(query,
                                       area_tematica=area_tematica,
                                       match_mode=_initial_mode,
                                       data_limite_inicio=data_limite_inicio,
                                       data_limite_fim=data_limite_fim,
                                       status=status,
                                       limite=ultimas_n_acoes)
            # Tenta com match_mode=any se all nao encontrou
            if _initial_mode == "all" and not res_exact.get("resultados"):
                res_exact = buscar_tarefas(query,
                                           area_tematica=area_tematica,
                                           match_mode="any",
                                           data_limite_inicio=data_limite_inicio,
                                           data_limite_fim=data_limite_fim,
                                           status=status,
                                           limite=ultimas_n_acoes)

            if res_exact.get("erro"):
                return f"⚠️ [ERRO TÉCNICO BuscaGrafo] {res_exact['erro']}"

            resultados = res_exact.get("resultados", [])

            # CAMINHO A: Tarefas reais encontradas — retorna SOMENTE elas.
            # Nao inclui contexto semantico para evitar mistura de fontes (alucinacao de titulo/dados).
            if resultados:
                lines = [
                    "=== TAREFAS REAIS ENCONTRADAS NO BANCO DE DADOS ===",
                    "REGRA: Use EXCLUSIVAMENTE os campos abaixo. Nao invente, nao complete, nao use RAG.",
                    "",
                ]
                for r in resultados:
                    lines.append(f"ID: {r['id']}")
                    lines.append(f"Titulo: {r['titulo']}")
                    lines.append(f"Status: {r['status']} | Tipo: {r.get('tipo_acao') or 'nao informado'}")
                    lines.append(f"Prazo: {r.get('data_limite', 'N/A')} | Area: {r['area']} | Criado em: {r['criado_em']}")
                    if r.get('processo_sei'):
                        lines.append(f"Processo SEI: {r['processo_sei']}")
                    lines.append(f"Responsavel: {r.get('responsavel') or 'nao informado'}")
                    if r.get('tags'):
                        tags_val = r['tags']
                        tags_str = ', '.join(tags_val) if isinstance(tags_val, list) else str(tags_val)
                        lines.append(f"Tags: {tags_str}")
                    if r.get('sintese_demanda'):
                        lines.append(f"Sintese da Demanda: {r['sintese_demanda']}")
                    if r.get('descricao'):
                        lines.append(f"Descricao: {r['descricao']}")
                    if r.get('notas'):
                        lines.append(f"Notas: {r['notas']}")
                    plano = r.get('plano_acao', [])
                    if plano:
                        lines.append("Plano de Acao:")
                        for passo in plano:
                            lines.append(f"  {passo}")
                    acomp = r.get('acompanhamento_recente', [])
                    if acomp:
                        lines.append("Diario de Bordo (ultimas entradas):")
                        for entrada in acomp:
                            lines.append(f"  {entrada}")
                    lines.append(f"[Abrir Acao](task:{r['id']})")
                    lines.append("---")
                return "\n".join(lines)

            # CAMINHO B: Nenhuma tarefa real encontrada.
            # Retorna mensagem direta sem fallback semantico.
            # O modelo NAO deve inventar dados nem usar RAG para compensar.
            filtros_desc = []
            if query and query.strip():
                filtros_desc.append(f"query='{query.strip()}'")
            if status:
                filtros_desc.append(f"status='{status}'")
            if area_tematica:
                filtros_desc.append(f"area='{area_tematica}'")
            if data_limite_inicio or data_limite_fim:
                filtros_desc.append(f"prazo=[{data_limite_inicio or '*'} a {data_limite_fim or '*'}]")
            filtros_str = ", ".join(filtros_desc) if filtros_desc else "(sem filtros)"
            return (
                f"NENHUMA TAREFA ENCONTRADA no banco de dados com os filtros: {filtros_str}.\n"
                "INSTRUCAO OBRIGATORIA: Informe ao usuario que nao encontrou. NAO invente titulos, "
                "status, prazos ou qualquer dado de tarefa. NAO use RAG, acervo ou memoria para fabricar uma resposta."
            )

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
                # Valida existência no Drive — arquivos deletados/na lixeira são omitidos do contexto
                _ctx_drive = get_drive_service()
                arquivos_disponiveis = []
                for item in t.get('pool_dados', []):
                    if item.get('tipo') != 'arquivo':
                        continue
                    fid = item.get('drive_file_id')
                    if not fid:
                        url_val = item.get('valor', '')
                        match = _DRIVE_ID_RE.search(url_val)
                        fid = match.group(1) if match else None
                    if not fid:
                        continue
                    try:
                        _meta = _ctx_drive.files().get(fileId=fid, fields='id,trashed').execute()
                        if _meta.get('trashed'):
                            continue
                    except Exception:
                        continue
                    arquivos_disponiveis.append({
                        "nome": item.get('nome', 'Arquivo sem nome'),
                        "drive_file_id": fid
                    })
                
                context = {
                    "id": id_tarefa,
                    "titulo": t.get('titulo'),
                    "area_tematica": t.get('area_tematica'),
                    "sistema_id": t.get('sistema_id') or None,
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
            _prompt_lower = (prompt or "").lower()
            _web_triggers = (
                "http://", "https://", "www.", "internet", "na web", "busca online",
                "pesquise", "pesquisar", "notícia", "noticias", "cotação", "cotacao",
                "atualiz", "link", "site", "acesse",
            )
            if not any(t in _prompt_lower for t in _web_triggers):
                return '{"blocked": true, "reason": "O prompt não menciona internet, URL ou busca atual. Use esta ferramenta apenas quando o usuário pedir explicitamente informações da web."}'
            import requests as _req
            try:
                keys_doc_web = _cached_doc_get(db, 'system', 'api_keys')
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


        def buscar_e_analisar_email(query: str, max_results: int = 5):
            """
            Busca e analisa e-mails no Gmail usando uma query estruturada.
            Use esta ferramenta quando o usuário pedir para verificar, ler ou analisar e-mails.
            Retorna o texto higienizado e o conteúdo de anexos (PDF, CSV).

            Args:
                query: Query de busca padrão do Gmail (ex: 'from:nome@empresa.com newer_than:2d', 'subject:"reunião"').
                max_results: Número máximo de e-mails a processar (limite: 5).
            """
            import os
            import tempfile
            import base64

            try:
                import html2text
            except ImportError:
                return "⚠️ Dependência html2text não instalada. Avise o desenvolvedor."

            try:
                gs = get_gmail_service()
            except Exception as e:
                return f"⚠️ Erro ao inicializar serviço do Gmail: {str(e)}"

            try:
                results = gs.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
                messages = results.get('messages', [])

                if not messages:
                    return "Nenhum e-mail encontrado para a query informada."

                output = []
                for msg in messages:
                    msg_id = msg['id']
                    full_msg = gs.users().messages().get(userId='me', id=msg_id, format='full').execute()

                    payload = full_msg.get('payload', {})
                    headers = payload.get('headers', [])

                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'Sem Assunto')
                    sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Desconhecido')
                    date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')

                    text_parts = []
                    html_parts = []
                    attachments = []

                    def walk_parts(part):
                        mime_type = part.get('mimeType')
                        body = part.get('body', {})
                        data = body.get('data')
                        filename = part.get('filename', '')

                        if filename and body.get('attachmentId'):
                            size = body.get('size', 0)
                            if size < 50000 and mime_type.startswith('image/'):
                                pass
                            elif mime_type in ['application/pdf', 'text/csv']:
                                attachments.append({
                                    'id': body['attachmentId'],
                                    'filename': filename,
                                    'mime_type': mime_type,
                                    'size': size
                                })
                        elif data:
                            if mime_type == 'text/plain':
                                text_parts.append(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', errors='replace'))
                            elif mime_type == 'text/html':
                                html_parts.append(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', errors='replace'))

                        if 'parts' in part:
                            for subpart in part['parts']:
                                walk_parts(subpart)

                    walk_parts(payload)

                    clean_text = ""
                    if text_parts:
                        clean_text = "\n".join(text_parts)
                    elif html_parts:
                        h = html2text.HTML2Text()
                        h.ignore_links = False
                        h.ignore_images = True
                        h.body_width = 0
                        clean_text = "\n".join([h.handle(html) for html in html_parts])

                    clean_text = "\n".join([line for line in clean_text.split("\n") if line.strip()])

                    msg_str = f"--- E-MAIL ---\nID: {msg_id}\nDe: {sender}\nAssunto: {subject}\nData: {date_str}\n\n[Corpo do E-mail]\n{clean_text}\n"

                    for att in attachments:
                        att_id = att['id']
                        att_name = att['filename']
                        msg_str += f"\n[Anexo: {att_name}]\n"

                        try:
                            att_obj = gs.users().messages().attachments().get(userId='me', messageId=msg_id, id=att_id).execute()
                            file_data = base64.urlsafe_b64decode(att_obj['data'])

                            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(att_name)[1] if '.' in att_name else '') as temp_file:
                                temp_file.write(file_data)
                                temp_path = temp_file.name

                            try:
                                if att['mime_type'] == 'application/pdf':
                                    pdf_result = extract_pdf_text_with_fallback(
                                        file_data,
                                        att_name,
                                        allow_gemini_fallback=False,
                                        max_pages=10,
                                    )
                                    extracted_text = pdf_result.get('text', '')
                                    msg_str += f"Conteúdo do PDF (Extração):\n{extracted_text[:3000]}\n"
                                elif att['mime_type'] == 'text/csv':
                                    import csv
                                    with open(temp_path, 'r', encoding='utf-8', errors='replace') as f:
                                        reader = csv.reader(f)
                                        lines = [",".join(row) for i, row in enumerate(reader) if i < 50]
                                        msg_str += f"Conteúdo do CSV (Primeiras 50 linhas):\n" + "\n".join(lines) + "\n"
                            finally:
                                if os.path.exists(temp_path):
                                    os.remove(temp_path)
                        except Exception as e_att:
                            msg_str += f"(Erro ao processar anexo {att_name}: {e_att})\n"

                    output.append(msg_str)

                # Indexar implicitamente no Grafo (Nó de Fonte) para o primeiro email (se houver), se a intenção for gerar RAG Node
                # Note: O RAG Node será instanciado na criação de tarefa, ou podemos fazer aqui?
                # A instrução: "o texto do e-mail é uma entidade primária e deve ser processado pelas funções do knowledge_graph.py para gerar um Nó de Fonte"
                # A melhor abordagem é ter uma ferramenta adicional "indexar_email_grafo", ou então retornar o texto do email, e ao criar_acao_no_sistema() a IA passar os campos do email!

                return "\n\n==========================\n\n".join(output)
            except Exception as e:
                return f"⚠️ Erro ao processar e-mails: {str(e)}"

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

                from googleapiclient.http import MediaIoBaseDownload

                # 2a. Google Workspace files must be exported, not downloaded
                _GAPPS_EXPORT_MAP = {
                    'application/vnd.google-apps.document': 'text/plain',
                    'application/vnd.google-apps.spreadsheet': 'text/csv',
                    'application/vnd.google-apps.presentation': 'text/plain',
                }
                if _mime in _GAPPS_EXPORT_MAP:
                    _export_mime = _GAPPS_EXPORT_MAP[_mime]
                    _req_dl = _drive_service.files().export_media(
                        fileId=drive_file_id, mimeType=_export_mime
                    )
                    _fh = _io.BytesIO()
                    _dl = MediaIoBaseDownload(_fh, _req_dl)
                    _done = False
                    while not _done:
                        _, _done = _dl.next_chunk()
                    _exported_text = _fh.getvalue().decode('utf-8', errors='replace').strip()
                    _response = client.models.generate_content(
                        model=model_id,
                        contents=[(
                            f"Você recebeu o conteúdo exportado do arquivo '{_real_name}'. "
                            f"Responda exclusivamente à pergunta abaixo com base nesse conteúdo.\n\n"
                            f"PERGUNTA: {query_especifica}\n\n"
                            "REGRAS:\n"
                            "- Se a informação existir, responda de forma precisa e cite o trecho de origem.\n"
                            "- Se a informação não existir, declare: 'A informação solicitada não foi encontrada neste documento.'\n"
                            "- Não invente dados externos.\n\n"
                            f"CONTEÚDO DO DOCUMENTO:\n{_exported_text[:120000]}"
                        )]
                    )
                    _answer = (_response.text or "").strip()
                    return f"[Leitura de '{_real_name}']\n{_answer}" if _answer else "Não foi possível extrair a resposta do documento."

                # 2b. Download binary for all other file types
                _req_dl = _drive_service.files().get_media(fileId=drive_file_id)
                _fh = _io.BytesIO()
                _dl = MediaIoBaseDownload(_fh, _req_dl)
                _done = False
                while not _done:
                    _, _done = _dl.next_chunk()
                _fh.seek(0)
                _file_bytes = _fh.read()

                # 2c. Office formats: extract text locally — Gemini File API does not support them
                _OFFICE_DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                _OFFICE_PPTX = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
                _OFFICE_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                if _mime == _OFFICE_DOCX or _real_name.lower().endswith('.docx'):
                    import mammoth as _mammoth
                    _docx_result = _mammoth.extract_raw_text(_io.BytesIO(_file_bytes))
                    _office_text = (_docx_result.value or '').strip()
                    _response = client.models.generate_content(
                        model=model_id,
                        contents=[(
                            f"Você recebeu o conteúdo extraído do arquivo Word '{_real_name}'. "
                            f"Responda exclusivamente à pergunta abaixo com base nesse conteúdo.\n\n"
                            f"PERGUNTA: {query_especifica}\n\n"
                            "REGRAS:\n"
                            "- Se a informação existir, responda de forma precisa e cite o trecho de origem.\n"
                            "- Se a informação não existir, declare: 'A informação solicitada não foi encontrada neste documento.'\n"
                            "- Não invente dados externos.\n\n"
                            f"CONTEÚDO DO DOCUMENTO:\n{_office_text[:120000]}"
                        )]
                    )
                    _answer = (_response.text or "").strip()
                    return f"[Leitura de '{_real_name}']\n{_answer}" if _answer else "Não foi possível extrair a resposta do documento."
                if _mime == _OFFICE_PPTX or _real_name.lower().endswith('.pptx'):
                    from pptx import Presentation as _Presentation
                    _prs = _Presentation(_io.BytesIO(_file_bytes))
                    _slides_text = []
                    for _slide in _prs.slides:
                        for _shape in _slide.shapes:
                            if hasattr(_shape, 'text') and _shape.text.strip():
                                _slides_text.append(_shape.text.strip())
                    _office_text = '\n'.join(_slides_text).strip()
                    _response = client.models.generate_content(
                        model=model_id,
                        contents=[(
                            f"Você recebeu o conteúdo extraído da apresentação PowerPoint '{_real_name}'. "
                            f"Responda exclusivamente à pergunta abaixo com base nesse conteúdo.\n\n"
                            f"PERGUNTA: {query_especifica}\n\n"
                            "REGRAS:\n"
                            "- Se a informação existir, responda de forma precisa e cite o trecho de origem.\n"
                            "- Se a informação não existir, declare: 'A informação solicitada não foi encontrada neste documento.'\n"
                            "- Não invente dados externos.\n\n"
                            f"CONTEÚDO DO DOCUMENTO:\n{_office_text[:120000]}"
                        )]
                    )
                    _answer = (_response.text or "").strip()
                    return f"[Leitura de '{_real_name}']\n{_answer}" if _answer else "Não foi possível extrair a resposta do documento."

                if _mime == _OFFICE_XLSX or _real_name.lower().endswith('.xlsx'):
                    import pandas as _pd
                    _df_list = _pd.read_excel(_io.BytesIO(_file_bytes), sheet_name=None)
                    _sheets_text = []
                    for _sheet_name, _df in _df_list.items():
                        _sheets_text.append(f"ABA: {_sheet_name}\n{_df.to_csv(index=False)}")
                    _office_text = "\n\n".join(_sheets_text).strip()
                    _response = client.models.generate_content(
                        model=model_id,
                        contents=[(
                            f"Você recebeu o conteúdo extraído da planilha Excel '{_real_name}'. "
                            f"Responda exclusivamente à pergunta abaixo com base nesse conteúdo.\n\n"
                            f"PERGUNTA: {query_especifica}\n\n"
                            "REGRAS:\n"
                            "- Se a informação existir, responda de forma precisa e cite o trecho de origem.\n"
                            "- Se a informação não existir, declare: 'A informação solicitada não foi encontrada neste documento.'\n"
                            "- Não invente dados externos.\n\n"
                            f"CONTEÚDO DO DOCUMENTO:\n{_office_text[:120000]}"
                        )]
                    )
                    _answer = (_response.text or "").strip()
                    return f"[Leitura de '{_real_name}']\n{_answer}" if _answer else "Não foi possível extrair a resposta do documento."

                if is_pdf_mime_type(_real_name, _mime):
                    _pdf_result = extract_pdf_text_with_fallback(
                        _file_bytes,
                        _real_name,
                        api_key=gemini_key,
                        allow_gemini_fallback=False,
                    )
                    _pdf_text = (_pdf_result.get('text') or '').strip()
                    if _pdf_text:
                        _response = client.models.generate_content(
                            model=model_id,
                            contents=[(
                                f"Você recebeu a extração local do arquivo '{_real_name}'. "
                                f"Responda exclusivamente à pergunta abaixo com base nesse conteúdo.\n\n"
                                f"PERGUNTA: {query_especifica}\n\n"
                                "REGRAS:\n"
                                "- Se a informação existir, responda de forma precisa e cite o trecho de origem.\n"
                                "- Se a informação não existir, declare: 'A informação solicitada não foi encontrada neste documento.'\n"
                                "- Não invente dados externos.\n\n"
                                f"CONTEÚDO EXTRAÍDO:\n{_pdf_text[:120000]}"
                            )]
                        )
                        _answer = (_response.text or "").strip()
                        return f"[Leitura de '{_real_name}']\n{_answer}" if _answer else "Não foi possível extrair a resposta do documento."

                # 3. Salva temporariamente e envia para Gemini File API
                _ext = _os.path.splitext(_real_name)[1] or '.bin'
                with _tempfile.NamedTemporaryFile(delete=False, suffix=_ext) as _tmp:
                    _tmp.write(_file_bytes)
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

        def salvar_memoria_global(fato: str, categoria: str):
            """
            Ferramenta de retenção de memória global do Copiloto Hermes.
            Use apenas para fatos duráveis, preferências estáveis do ambiente ou regras de negócio
            que possam ser úteis em conversas futuras. Nunca use para ruído transitório.
            """
            try:
                retention = _classify_memory_candidate(
                    api_key=gemini_key,
                    fato=fato,
                    categoria=categoria,
                )
                if not retention.get("should_save"):
                    return json.dumps({
                        "status": "ignored",
                        "reason": retention.get("reason", "retention_filter"),
                        "categoria": retention.get("normalized_category", _normalize_memory_category(categoria)),
                        "confidence": retention.get("confidence", 0.0),
                    }, ensure_ascii=False)
                result = _save_memory_node(
                    db=db,
                    api_key=gemini_key,
                    fato=fato,
                    categoria=retention.get("normalized_category", categoria),
                    session_id=session_id,
                    user_uid=user_uid,
                )
                result["retention_reason"] = retention.get("reason")
                result["retention_confidence"] = retention.get("confidence")
                return json.dumps(result, ensure_ascii=False)
            except Exception as mem_err:
                return json.dumps({
                    "status": "error",
                    "reason": str(mem_err),
                }, ensure_ascii=False)

        def salvar_pop_global(
            titulo: str,
            gatilhos: list[str],
            instrucao_sistema: str
        ):
            """
            Cria ou atualiza um POP operacional persistido em pops_diretrizes.
            Use apenas quando houver pedido explícito do usuário para cadastrar ou atualizar um POP.
            """
            global _POPS_DATA_CACHE
            try:
                titulo_clean = (titulo or "").strip()
                instrucao_clean = (instrucao_sistema or "").strip()

                if not titulo_clean:
                    return json.dumps({"status": "error", "reason": "titulo_obrigatorio"}, ensure_ascii=False)
                if not instrucao_clean:
                    return json.dumps({"status": "error", "reason": "instrucao_obrigatoria"}, ensure_ascii=False)

                gatilhos_clean = []
                seen_gatilhos = set()
                for gatilho in gatilhos or []:
                    gatilho_clean = str(gatilho or "").strip().lower()
                    gatilho_norm = _normalize_pop_text(gatilho_clean)
                    if not gatilho_norm or gatilho_norm in seen_gatilhos:
                        continue
                    seen_gatilhos.add(gatilho_norm)
                    gatilhos_clean.append(gatilho_clean)

                if not gatilhos_clean:
                    return json.dumps({"status": "error", "reason": "gatilhos_obrigatorios"}, ensure_ascii=False)

                titulo_norm = _normalize_pop_text(titulo_clean)
                gatilhos_norm = {_normalize_pop_text(item) for item in gatilhos_clean}
                existing_ref = None
                existing_data = None

                for pop_doc in db.collection("pops_diretrizes").stream():
                    pop_data = pop_doc.to_dict() or {}
                    existing_title_norm = _normalize_pop_text(pop_data.get("titulo") or "")
                    existing_triggers_norm = {
                        _normalize_pop_text(item)
                        for item in (pop_data.get("gatilhos") or [])
                        if _normalize_pop_text(item)
                    }

                    if titulo_norm and titulo_norm == existing_title_norm:
                        existing_ref = pop_doc.reference
                        existing_data = pop_data
                        break

                    if gatilhos_norm and existing_triggers_norm.intersection(gatilhos_norm):
                        existing_ref = pop_doc.reference
                        existing_data = pop_data
                        break

                payload = {
                    "titulo": titulo_clean,
                    "gatilhos": gatilhos_clean,
                    "instrucao_sistema": instrucao_clean,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "updated_by": user_uid or "copiloto",
                    "origem": "copiloto",
                }

                if existing_ref:
                    payload["created_at"] = existing_data.get("created_at", firestore.SERVER_TIMESTAMP)
                    existing_ref.set(payload, merge=True)
                    _POPS_DATA_CACHE = None
                    return json.dumps({
                        "status": "updated",
                        "pop_id": existing_ref.id,
                        "titulo": titulo_clean,
                        "gatilhos": gatilhos_clean,
                    }, ensure_ascii=False)

                new_ref = db.collection("pops_diretrizes").document()
                payload["created_at"] = firestore.SERVER_TIMESTAMP
                new_ref.set(payload)
                _POPS_DATA_CACHE = None
                return json.dumps({
                    "status": "saved",
                    "pop_id": new_ref.id,
                    "titulo": titulo_clean,
                    "gatilhos": gatilhos_clean,
                }, ensure_ascii=False)
            except Exception as pop_err:
                return json.dumps({
                    "status": "error",
                    "reason": str(pop_err),
                }, ensure_ascii=False)

        def resolver_conflito_memoria(
            memoria_id: str,
            decisao: str,
            fato_atualizado: str = "",
            categoria: str = "fato_isolado"
        ):
            """
            Resolve um conflito explícito de memória após confirmação do usuário.
            decisao aceita: manter_existente, substituir_pelo_novo.
            """
            try:
                decisao_norm = (decisao or "").strip().lower()
                if decisao_norm == "manter_existente":
                    db.collection("knowledge_nodes").document(memoria_id).set({
                        "data_atualizacao": _iso_now_utc(),
                        "conflito_resolvido_em": firestore.SERVER_TIMESTAMP,
                        "ultima_decisao_humana": "manter_existente",
                    }, merge=True)
                    return json.dumps({
                        "status": "resolved",
                        "decision": "kept_existing",
                        "memory_id": memoria_id,
                    }, ensure_ascii=False)

                if decisao_norm != "substituir_pelo_novo":
                    return json.dumps({
                        "status": "error",
                        "reason": "decisao_invalida",
                    }, ensure_ascii=False)

                result = _save_memory_node(
                    db=db,
                    api_key=gemini_key,
                    fato=fato_atualizado,
                    categoria=categoria,
                    session_id=session_id,
                    user_uid=user_uid,
                    force_update_id=memoria_id,
                )
                result["decision"] = "replaced_existing"
                return json.dumps(result, ensure_ascii=False)
            except Exception as resolve_err:
                return json.dumps({
                    "status": "error",
                    "reason": str(resolve_err),
                }, ensure_ascii=False)

        def atualizar_personalidade(
            nova_personalidade: str,
            motivo: str = ""
        ):
            """
            Ferramenta silenciosa para atualizar a personalidade dinâmica do copiloto
            quando o usuário pedir mudança de tom, estilo ou nível de detalhamento.
            """
            try:
                novo_texto = (nova_personalidade or "").strip()
                if not novo_texto:
                    return json.dumps({"status": "ignored", "reason": "empty_personality"}, ensure_ascii=False)

                soul_ref = db.collection("system").document("copilot_soul")
                soul_ref.set({
                    "content": novo_texto,
                    "last_reason": (motivo or "").strip(),
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "updated_by_uid": user_uid,
                    "source": "copiloto",
                }, merge=True)
                return json.dumps({"status": "updated", "content": novo_texto[:300]}, ensure_ascii=False)
            except Exception as soul_err:
                return json.dumps({"status": "error", "reason": str(soul_err)}, ensure_ascii=False)

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

        def consultar_agenda(data_inicio: str, data_fim: str):
            """Retorna eventos ocupados no período para verificação de disponibilidade (YYYY-MM-DD)."""
            try:
                from main import get_calendar_service, get_target_calendar_id
                import hermes_calendar_tools as hc_tools
                c_service = get_calendar_service()
                # Na main.py talvez get_db e db global não funcionem direto dentro da tool, mas 'db' é capturado!
                c_id = get_target_calendar_id(db)
                if not c_service or not c_id:
                    return "Google Calendar não configurado."
                events = hc_tools.consultar_eventos(c_service, c_id, data_inicio, data_fim)
                return hc_tools.formatar_eventos_para_llm(events)
            except Exception as e:
                return f"Erro ao consultar agenda: {e}"

        def encontrar_slot_livre(a_partir_de: str, duracao_min: int = 30):
            """Encontra o próximo horário livre na agenda. a_partir_de = YYYY-MM-DD. Retorna JSON com data, horario_inicio, horario_fim."""
            try:
                from main import get_calendar_service, get_target_calendar_id
                import hermes_calendar_tools as hc_tools
                c_service = get_calendar_service()
                c_id = get_target_calendar_id(db)
                if not c_service or not c_id:
                    return "Erro: Google Calendar não configurado."
                slot = hc_tools.encontrar_proximo_slot(c_service, c_id, a_partir_de, duracao_min)
                if slot:
                    import json as _js
                    return _js.dumps(slot, ensure_ascii=False)
                return "Nenhum slot livre encontrado."
            except Exception as e:
                return f"Erro ao buscar slot livre: {e}"

        def consultar_financas_v2(mes: int = None, ano: int = None):
            """Retorna resumo financeiro unificado (rendas, obrigações, metas e balancete) para um período. Use mes (0-11) e ano (YYYY)."""
            try:
                from tools.telegram_extended import execute
                return execute("consultar_financas_v2", {"mes": mes, "ano": ano}, db)
            except Exception as e:
                return f"Erro ao consultar finanças: {e}"

        def registrar_item_financeiro_v2(tipo: str, descricao: str, valor: float, categoria: str = "Geral", mes: int = None, ano: int = None, data: str = None):
            """
            Registra uma nova entrada financeira (renda, obrigacao_fixa ou transacao_avulsa).
            Obrigatório apresentar rascunho (draft) ao usuário para confirmação antes de persistir.
            Parâmetros:
            - tipo: 'renda', 'obrigacao_fixa' ou 'transacao_avulsa'
            - valor: valor numérico
            - mes/ano: período de competência (opcional)
            """
            try:
                from tools.telegram_extended import execute
                slots = {"tipo": tipo, "descricao": descricao, "valor": valor, "categoria": categoria, "mes": mes, "ano": ano, "data": data}
                return execute("registrar_item_financeiro_v2", slots, db)
            except Exception as e:
                return f"Erro ao registrar item financeiro: {e}"

        def criar_acao_no_sistema(
            titulo: str,
            descricao: str = "",
            area_tematica: str = "GERAL",
            data_limite: str = None,
            tipo_acao: str = "fast",
            tags: list[str] = [],
            notas: str = "",
            plano_acao: list[str] = [],
            sourceGmailMessageId: str = None,
            sourceKnowledgeText: str = None,
            horario_inicio: str = None,
            horario_fim: str = None,
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
            - sourceGmailMessageId: se a ação veio de um e-mail, passe o ID da mensagem para controle de duplicação.
            - sourceKnowledgeText: se houver texto do e-mail longo a ser arquivado, passe-o aqui para instanciar um Nó de RAG.
            Retorna o ID da tarefa criada ou mensagem de erro.
            """
            try:
                import uuid as _uuid
                from datetime import datetime as _dt, timezone as _tz

                now_iso = _dt.now(_tz.utc).isoformat()
                today_brt = (_dt.now(_tz.utc) + timedelta(hours=-3)).date().isoformat()
                if not data_limite:
                    data_limite = today_brt
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


                source_knowledge_id = None
                if sourceKnowledgeText:
                    from knowledge_graph import _get_embedding
                    try:
                        kg_id = str(_uuid.uuid4())[:20]
                        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
                        gemini_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
                        if not gemini_key:
                            raise ValueError("Gemini API Key não encontrada (system/api_keys).")

                        embedding = _get_embedding(sourceKnowledgeText, gemini_key)

                        db.collection('conhecimento_mestre').document(kg_id).set({
                            'id': kg_id,
                            'titulo': f'Contexto de E-mail: {titulo}',
                            'tipo': 'paragrafo',
                            'conteudo_regra': sourceKnowledgeText,
                            'justificativa_da_regra': 'Contexto extraído via integração Gmail-Hermes',
                            'tags': tags or [],
                            'area_tematica': area_tematica,
                            'status': 'ativo',
                            'origem': 'gmail_copiloto',
                            'task_origin_id': task_id,
                            'peso_semantico': 1.0,
                            'data_criacao': now_iso,
                            'data_atualizacao': now_iso,
                            'embedding': embedding
                        })
                        source_knowledge_id = kg_id
                    except Exception as e_kg:
                        print(f"Erro ao criar Nó de Fonte do Gmail: {e_kg}")

                now_iso = now_iso

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
                    "horario_inicio": horario_inicio,
                    "horario_fim": horario_fim,

                    "sourceGmailMessageId": sourceGmailMessageId or None,
                    "sourceKnowledgeId": source_knowledge_id or None,}

                try:
                    from main import get_calendar_service, get_target_calendar_id
                    import hermes_calendar_tools as hc_tools
                    c_service = get_calendar_service()
                    c_id = get_target_calendar_id(db)
                    if c_service and c_id and horario_inicio and horario_fim:
                        hc_tools.reagendar_acoes_hermes(db, c_service, c_id, data_limite, horario_inicio, horario_fim)
                except Exception as e:
                    print(f"[Copiloto] Erro ao reagendar: {e}")

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

        def registrar_no_diario(
            nota: str,
            task_id_alvo: str = None,
        ):
            """
            Registra uma entrada livre no diário de bordo de uma tarefa.
            Use sempre que o usuário pedir para anotar, registrar ou logar algo no diário.
            Parâmetros:
            - nota: texto da entrada a registrar.
            - task_id_alvo: ID da tarefa alvo (opcional). Se omitido, usa a tarefa da sessão ativa.
              Quando não houver tarefa no contexto, informe o usuário e peça qual ação usar
              ANTES de chamar esta função.
            Retorna JSON com status e título da tarefa, ou 'ERRO|{detalhe}'.
            """
            try:
                from datetime import datetime as _dt, timezone as _tz
                alvo = (task_id_alvo or task_id or "").strip()
                if not alvo:
                    return "ERRO|Sem tarefa ativa. Informe o ID da tarefa onde registrar."
                if not (nota or "").strip():
                    return "ERRO|Nota vazia."
                task_ref = db.collection('tarefas').document(alvo)
                task_doc = task_ref.get()
                if not task_doc.exists:
                    return f"ERRO|Tarefa '{alvo}' não encontrada."
                now_iso = _dt.now(_tz.utc).isoformat()
                entry = {'data': now_iso, 'nota': nota.strip()}
                task_ref.update({'acompanhamento': firestore.ArrayUnion([entry])})
                titulo_tarefa = (task_doc.to_dict() or {}).get('titulo', alvo)
                print(f"[Copiloto] Diário registrado na tarefa {alvo}.")
                return json.dumps({"status": "ok", "task_id": alvo, "titulo": titulo_tarefa}, ensure_ascii=False)
            except Exception as _err:
                print(f"[Copiloto] Erro ao registrar no diário: {_err}")
                return f"ERRO|{str(_err)}"

        def gerar_relatorio(
            titulo: str,
            tipo: str,
            contexto: str,
            secoes_customizadas: list[str] = None
        ):
            """
            Gera um relatório estruturado em Markdown e o salva no sistema.
            Use quando o usuário solicitar um relatório formal, análise consolidada ou documento.

            Parâmetros:
            - titulo: título do relatório
            - tipo: "executivo", "técnico", "analítico", "progresso" ou "situacional"
            - contexto: contexto completo coletado (resultados de buscas, fatos, dados relevantes)
            - secoes_customizadas: lista de nomes de seções específicas a incluir (opcional)

            Retorna JSON com o ID do relatório gerado.
            """
            try:
                from datetime import datetime as _dt, timezone as _tz
                import uuid as _uuid

                now_iso = _dt.now(_tz.utc).isoformat()
                data_hoje = (_dt.now(_tz.utc) + timedelta(hours=-3)).strftime("%d/%m/%Y")
                report_id = str(_uuid.uuid4())[:16]

                # 1. Gera skeleton de seções via LLM
                skeleton_prompt = (
                    f'Você é um arquiteto de relatórios técnicos.\n'
                    f'Crie um esqueleto de seções para um relatório {tipo} intitulado "{titulo}".\n'
                    f'CONTEXTO (resumo):\n{contexto[:2500]}\n\n'
                    f'Responda APENAS com JSON no formato:\n{{"secoes": ["Seção 1", "Seção 2", ...]}}\n\n'
                    f'Regras:\n'
                    f'- Entre 4 e 7 seções\n'
                    f'- Primeira seção: "Sumário Executivo"\n'
                    f'- Última seção: "Conclusão e Recomendações"\n'
                    f'- Seções exclusivas, sem sobreposição\n'
                )
                if secoes_customizadas:
                    skeleton_prompt += f'- Inclua obrigatoriamente: {secoes_customizadas}\n'

                skeleton_resp = client.models.generate_content(
                    model="gemini-3.1-flash-lite-preview",
                    contents=skeleton_prompt
                )
                skeleton_text = skeleton_resp.text or ""
                json_match = re.search(r'\{.*?\}', skeleton_text, re.DOTALL)
                if json_match:
                    parsed_sk = json.loads(json_match.group())
                    secoes = parsed_sk.get("secoes", [])
                else:
                    secoes = ["Sumário Executivo", "Análise", "Dados e Evidências", "Conclusão e Recomendações"]

                # 2. Gera conteúdo por seção com deduplicação progressiva
                sections_content = {}
                sections_already_covered = []

                for secao in secoes:
                    dedup_hint = ""
                    if sections_already_covered:
                        dedup_hint = f"\nASSUNTOS JÁ ABORDADOS (NÃO REPETIR): {', '.join(sections_already_covered)}"

                    section_prompt = (
                        f'Você é um redator técnico sênior escrevendo a seção "{secao}" '
                        f'de um relatório {tipo} intitulado "{titulo}".\n'
                        f'Data: {data_hoje}\n\n'
                        f'CONTEXTO E DADOS:\n{contexto[:4000]}\n'
                        f'{dedup_hint}\n\n'
                        f'Escreva APENAS o conteúdo desta seção em Markdown.\n'
                        f'- Use ## para subseções se necessário\n'
                        f'- Use listas, tabelas e negritos para clareza\n'
                        f'- Tom formal e objetivo\n'
                        f'- NÃO inclua o título da seção (será adicionado automaticamente)\n'
                        f'- Entre 150 e 400 palavras\n'
                    )

                    sect_resp = client.models.generate_content(
                        model="gemini-3.1-pro-preview",
                        contents=section_prompt
                    )
                    sections_content[secao] = sect_resp.text or "*(conteúdo indisponível)*"
                    sections_already_covered.append(secao)

                # 3. Compila Markdown final
                tipo_label = tipo.capitalize()
                md_parts = [
                    f"# {titulo}",
                    "",
                    f"**Tipo:** Relatório {tipo_label}  ",
                    f"**Data:** {data_hoje}  ",
                    f"**Gerado por:** Hermes Copiloto  ",
                    "",
                    "---",
                    "",
                ]
                for secao, content in sections_content.items():
                    md_parts.append(f"## {secao}")
                    md_parts.append("")
                    md_parts.append(content)
                    md_parts.append("")

                final_markdown = "\n".join(md_parts)

                # 4. Salva no Firestore (coleção relatorios)
                db.collection('relatorios').document(report_id).set({
                    "id": report_id,
                    "titulo": titulo,
                    "tipo": tipo,
                    "markdown": final_markdown,
                    "secoes": secoes,
                    "session_id": session_id,
                    "task_id": task_id,
                    "createdAt": firestore.SERVER_TIMESTAMP,
                    "driveFileId": None,
                    "driveUrl": None
                })

                print(f"[Copiloto] Relatório '{titulo}' gerado ({len(secoes)} seções) — ID: {report_id}")
                return json.dumps({
                    "report_id": report_id,
                    "titulo": titulo,
                    "secoes": secoes,
                    "status": "gerado"
                }, ensure_ascii=False)

            except Exception as _rep_err:
                import traceback as _tb
                print(f"[Copiloto] Erro ao gerar relatório: {_rep_err}\n{_tb.format_exc()}")
                return f"⚠️ Erro ao gerar relatório: {str(_rep_err)}"


        def gerar_rascunho_formulario(titulo: str, descricao: str, perguntas: list[dict]):
            """
            NÃO CHAME ESTA FERRAMENTA DIRETAMENTE SE VOCÊ JÁ EMITIR O BLOCO [FORM]...[/FORM].
            Ferramenta auxiliar para forçar o LLM a emitir a estrutura do formulário de forma estruturada.
            """
            pass

        def preparar_edicao_acao(
            task_id: str,
            alteracoes: dict,
            justificativa: str
        ):
            """
            Prepara uma proposta de edição de ação para confirmação interativa do usuário.
            NÃO realiza nenhuma mutação no banco de dados — apenas valida e retorna o payload.

            Use SEMPRE antes de editar qualquer campo de uma ação existente.
            O sistema renderiza um card visual para o usuário confirmar ou cancelar.

            Parâmetros:
            - task_id: ID da tarefa a ser editada
            - alteracoes: dicionário com campos e novos valores.
              Campos suportados: titulo, descricao, data_limite, status, tags, area_tematica, tipo_acao, notas
              Exemplo: {"data_limite": "2026-05-15", "titulo": "Novo Título"}
            - justificativa: frase curta explicando o motivo (gravada silenciosamente no diário)

            Retorna JSON string com payload de confirmação ou string de erro.
            """
            try:
                _ALLOWED_FIELDS = {'titulo', 'descricao', 'data_limite', 'data_inicio', 'horario_inicio', 'horario_fim', 'status', 'tags', 'area_tematica', 'tipo_acao', 'notas'}

                def _normalizar_status_acao(valor):
                    if valor is None:
                        return valor
                    raw = str(valor).strip().lower()
                    try:
                        import unicodedata
                        raw = ''.join(c for c in unicodedata.normalize('NFD', raw) if unicodedata.category(c) != 'Mn')
                    except Exception:
                        pass
                    raw = raw.replace('_', ' ').replace('-', ' ')
                    raw = ' '.join(raw.split())
                    if raw in ('concluido', 'concluida', 'concluir', 'finalizado', 'finalizada', 'completed', 'done'):
                        return 'concluído'
                    if raw in ('stand by', 'standby', 'pausado', 'pausada', 'pausar'):
                        return 'stand-by'
                    if raw in ('em andamento', 'andamento', 'pendente', 'aberto', 'aberta', 'reabrir'):
                        return 'em andamento'
                    return valor

                task_ref = db.collection('tarefas').document(task_id)
                task_doc = task_ref.get()

                if not task_doc.exists:
                    return f"ERRO|Ação '{task_id}' não encontrada."

                task_data = task_doc.to_dict()

                if task_data.get('status') == 'concluído':
                    return "ERRO|Esta ação já foi concluída e não pode ser editada."

                # Monta o diff de campos (original vs. novo)
                alteracoes_diff = {}
                for campo, novo_valor in (alteracoes or {}).items():
                    if campo not in _ALLOWED_FIELDS:
                        continue
                    if campo == 'status':
                        novo_valor = _normalizar_status_acao(novo_valor)
                    original = task_data.get(campo)
                    original_str = ', '.join(str(v) for v in original) if isinstance(original, list) else (str(original) if original is not None else '')
                    novo_str = ', '.join(str(v) for v in novo_valor) if isinstance(novo_valor, list) else (str(novo_valor) if novo_valor is not None else '')
                    alteracoes_diff[campo] = {
                        'original': original_str,
                        'novo': novo_str,
                        'novo_raw': novo_valor
                    }

                if not alteracoes_diff:
                    return "ERRO|Nenhum campo válido para editar."

                snapshot_ts = task_data.get('data_atualizacao') or task_data.get('data_criacao', '')
                payload = {
                    'task_id': task_id,
                    'titulo': task_data.get('titulo', ''),
                    'alteracoes': alteracoes_diff,
                    'justificativa': justificativa or '',
                    'snapshot_ts': str(snapshot_ts),
                    'status': 'pending'
                }

                print(f"[Copiloto] Edição preparada para task_id={task_id}: {list(alteracoes_diff.keys())}")
                return json.dumps(payload, ensure_ascii=False)

            except Exception as _pe:
                print(f"[Copiloto] Erro ao preparar edição: {_pe}")
                return f"ERRO|{str(_pe)}"

        def preparar_reagendamento_em_lote(
            nova_data_inicio: str,
            max_por_semana: int = 5,
            estrategia: str = "data_criacao",
            filtro_data: str = None,
            task_ids: list[str] = None,
            justificativa: str = "",
        ):
            """
            Prepara reagendamento em lote de ações para confirmação interativa do usuário.
            NÃO realiza nenhuma mutação — retorna payload para card de confirmação visual.

            Parâmetros:
            - nova_data_inicio: YYYY-MM-DD — primeiro dia útil a partir do qual redistribuir as ações
            - max_por_semana: máximo de ações alocadas por semana (padrão 5)
            - estrategia: critério de ordenação das ações — "data_criacao" (padrão, mais antigas primeiro),
              "tipo_acao" (fast antes de deep), "alfa" (ordem alfabética pelo título)
            - filtro_data: YYYY-MM-DD — seleciona ações com data_limite igual a esta data (ex: hoje)
            - task_ids: lista explícita de IDs (alternativa ao filtro_data)
            - justificativa: frase curta explicando o motivo (gravada silenciosamente no diário de cada ação)

            Retorna JSON string com payload de confirmação ou string de erro.
            """
            try:
                from datetime import timedelta as _td

                if not filtro_data and not task_ids:
                    return "ERRO|Forneça filtro_data (YYYY-MM-DD) ou task_ids (lista de IDs)."

                tasks = []
                if task_ids:
                    for tid in (task_ids or []):
                        tdoc = db.collection('tarefas').document(str(tid)).get()
                        if tdoc.exists:
                            t = tdoc.to_dict()
                            if t.get('status') not in ('concluído', 'cancelado'):
                                tasks.append({'_doc_id': str(tid), **t})
                else:
                    q = db.collection('tarefas')\
                        .where('data_limite', '==', filtro_data)\
                        .where('status', 'in', ['em andamento', 'stand-by'])\
                        .get()
                    for qdoc in q:
                        tasks.append({'_doc_id': qdoc.id, **qdoc.to_dict()})

                if not tasks:
                    return "ERRO|Nenhuma ação encontrada com os critérios informados."

                if estrategia == 'tipo_acao':
                    tasks.sort(key=lambda x: (0 if x.get('tipo_acao') == 'fast' else 1, x.get('data_criacao', '')))
                elif estrategia == 'alfa':
                    tasks.sort(key=lambda x: x.get('titulo', '').lower())
                else:
                    tasks.sort(key=lambda x: x.get('data_criacao', ''))

                try:
                    from datetime import date as _date
                    start_date = datetime.strptime(nova_data_inicio, "%Y-%m-%d").date()
                except ValueError:
                    return f"ERRO|Formato de data inválido: '{nova_data_inicio}'. Use YYYY-MM-DD."

                def _next_weekday(d):
                    while d.weekday() >= 5:
                        d += _td(days=1)
                    return d

                day_cursor = _next_weekday(start_date)
                count_this_week = 0
                items = []

                for task in tasks:
                    if count_this_week >= max_por_semana:
                        days_to_monday = 7 - day_cursor.weekday()
                        day_cursor += _td(days=days_to_monday)
                        day_cursor = _next_weekday(day_cursor)
                        count_this_week = 0

                    items.append({
                        'task_id': task['_doc_id'],
                        'titulo': task.get('titulo', ''),
                        'data_limite_original': task.get('data_limite', ''),
                        'horario_inicio_original': task.get('horario_inicio'),
                        'horario_fim_original': task.get('horario_fim'),
                        'nova_data_limite': day_cursor.strftime("%Y-%m-%d"),
                        'novo_horario_inicio': None,
                        'novo_horario_fim': None,
                    })

                    count_this_week += 1
                    day_cursor += _td(days=1)
                    day_cursor = _next_weekday(day_cursor)

                payload = {
                    'items': items,
                    'justificativa': justificativa or f"Reagendamento em lote para semana de {nova_data_inicio}.",
                    'status': 'pending',
                    'created_at': datetime.now(timezone.utc).isoformat(),
                }

                print(f"[Copiloto] Reagendamento em lote preparado: {len(items)} ações.")
                return json.dumps(payload, ensure_ascii=False)

            except Exception as _re:
                print(f"[Copiloto] Erro em preparar_reagendamento_em_lote: {_re}")
                return f"ERRO|{str(_re)}"

        # Configuração do Chat com ferramentas
        model_id = "gemini-3.1-pro-preview"
        
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")

        # Busca catálogo de sistemas para o "de-para" exato que o usuário solicitou
        try:
            sistemas_docs = db.collection('sistemas_detalhes').get()
            catalogo_sistemas = []
            for s_doc in sistemas_docs:
                s_data = s_doc.to_dict()
                s_nome = s_data.get('nome', 'Sem Nome')
                s_id = s_doc.id
                catalogo_sistemas.append(f"- {s_nome}: {s_id}")
            sistemas_str = "\n".join(catalogo_sistemas) if catalogo_sistemas else "Nenhum sistema cadastrado."
        except Exception as e:
            print(f"Erro ao buscar catálogo de sistemas: {e}")
            sistemas_str = "Erro ao carregar catálogo."

        system_instruction = (
            f"Você é o Copiloto Hermes, estrategista sênior de processos. Hoje é {today_str}. "
            f"{('CONTEXTO TÉCNICO VINCULADO (OBRIGATÓRIO): ' + (f'sistemaId={system_id}, ' if system_id else '') + (f'taskId={task_id}. ' if task_id else '')) if (system_id or task_id) else ''}"
            "\n\n## CORE ESTÁTICO DO COPILOTO\n"
            f"{copilot_core.get('content', '')}\n\n"
            "## PERSONALIDADE DINÂMICA ATUAL\n"
            f"{copilot_soul.get('content') or json.dumps(copilot_soul, ensure_ascii=False)}\n\n"
            "## PERFIL OPERACIONAL DO USUÁRIO\n"
            f"{_format_ai_profile_for_prompt(ai_profile)}\n\n"
            f"{tools_routing_context}"
            "\n\nCATÁLOGO DE SISTEMAS (Mapeamento Exato de Nome para ID):\n"
            f"{sistemas_str}\n\n"
            "Ao realizar diagnósticos ou operações em sistemas, utilize SEMPRE o ID técnico do catálogo acima correspondente ao nome citado pelo usuário.\n\n"
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
            "PROIBIÇÃO: Você NUNCA deve gerar links com `https://` ou URLs de sites externos para se referir a ações do sistema. Use APENAS o prefixo `task:`.\n"
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
            "## CRIAÇÃO E ALOCAÇÃO DE AÇÕES NA AGENDA (CRÍTICO)\n\n"
            "Quando o usuário solicitar a criação ou agendamento de uma ação/tarefa, siga OBRIGATORIAMENTE este protocolo:\n\n"
            "ETAPA 0 — VERIFICAÇÃO DE DISPONIBILIDADE NA AGENDA:\n"
            "Você DEVE usar consultar_agenda(data_inicio, data_fim) ou encontrar_slot_livre(data) ANTES de apresentar qualquer proposta ao usuário.\n"
            "Se o usuário pedir um horário específico (ex: 'amanhã às 14h') e houver colisão (conflito detectado): trave a inserção perguntando se ele quer Forçar a sobreposição ou Buscar próximo horário livre.\n"
            "Se o usuário for flexível ('agende para amanhã'), use encontrar_slot_livre para acomodar no primeiro espaço vazio (duração padrão 30min).\n"
            "Restrição: A agenda opera estritamente entre 08:00 e 19:00, dentro de uma janela de 7 dias úteis.\n\n"
            "ETAPA 1 — DRAFT (apresentar antes de criar):\n"
            "Apresente um resumo estruturado para o usuário confirmar:\n"
            "  📋 **Draft da Ação na Agenda**\n"
            "  - **Título:** [título]\n"
            "  - **Início/Fim:** [ex: 2026-05-15 14:00 às 14:30]\n"
            "  - **Área Temática:** [área ou projeto baseada no contexto; PERGUNTE SE FOR AMBÍGUA]\n"
            "  - **Tipo:** [fast / deep]\n"
            "  Confirma a alocação desta ação?\n\n"
            "ETAPA 2 — CONFIRMAÇÃO:\n"
            "Só chame criar_acao_no_sistema após receber confirmação explícita ('sim', 'confirma', 'pode criar', 'ok', etc.).\n"
            "Se o usuário ajustar algum campo no draft, incorpore as correções antes de criar.\n\n"
            "ETAPA 3 — COMMIT E LINK:\n"
            "Após criar_acao_no_sistema retornar 'OK|{ID}', responda obrigatoriamente:\n"
            "  ✅ Ação criada: [Título da Ação](task:{ID})\n"
            "  Você também pode clicar no link acima para abrir a sala de operações imediatamente.\n"
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
            "O usuário não precisa aprovar este texto — é gravado silenciosamente no diário da tarefa.\n\n"
            "## EDIÇÃO DE CAMPOS DE AÇÕES — CARD DE CONFIRMAÇÃO (CRÍTICO)\n\n"
            "Quando o usuário solicitar alteração de campos de uma ação existente (título, prazo, status,\n"
            "área temática, tags, descrição, notas, tipo), siga OBRIGATORIAMENTE este protocolo:\n\n"
            "ETAPA 0 — BUSCA OBRIGATÓRIA:\n"
            "Use consultar_historico_acoes() para localizar a ação com precisão.\n"
            "Nunca suponha um task_id sem buscar. Prefira a correspondência mais exata ao nome/contexto informado.\n"
            "Se houver ambiguidade, apresente as opções ao usuário antes de prosseguir.\n\n"
            "## MEMÓRIA E COGNIÇÃO AUTÔNOMA\n"
            "Quando identificar uma regra de negócio durável, uma preferência operacional estável ou um fato global útil em conversas futuras, "
            "acione salvar_memoria_global(fato, categoria) silenciosamente.\n"
            "Categorias válidas: 'regra_global' e 'fato_isolado'.\n"
            "Nunca grave memória para ruído passageiro, opiniões momentâneas, mensagens genéricas ou detalhes descartáveis.\n"
            "Também NÃO grave saudações, confirmações simples, contexto efêmero desta conversa, anexos transitórios ou decisões ainda não estabilizadas.\n"
            "Prefira gravar apenas convenções permanentes, preferências recorrentes, regras operacionais, fontes de verdade e fatos reutilizáveis.\n"
            "Se salvar_memoria_global retornar status='conflict', interrompa a automação e pergunte explicitamente ao usuário qual versão deve permanecer verdadeira.\n"
            "Após o usuário decidir, use resolver_conflito_memoria() para convergir a fonte de verdade.\n"
            "Se o usuário pedir mudança de tom, estilo, profundidade ou comportamento, use atualizar_personalidade() para reescrever a personalidade dinâmica.\n\n"
            "ETAPA 1 — PROPOSTA VIA FERRAMENTA:\n"
            "## POPS OPERACIONAIS\n"
            "Se o usuário pedir explicitamente para criar, cadastrar, registrar ou atualizar um POP/Procedimento Operacional Padrão,\n"
            "use salvar_pop_global(titulo, gatilhos, instrucao_sistema).\n"
            "Use essa ferramenta apenas quando houver intenção clara de persistir um POP reutilizável no Gestor de POPs.\n"
            "Gatilhos devem ser uma lista de frases curtas que disparam o POP.\n"
            "Após salvar_pop_global com sucesso, deixe claro para o usuário que o POP foi salvo ou atualizado no Gestor de POPs.\n\n"
            "Chame preparar_edicao_acao(task_id, alteracoes, justificativa) com:\n"
            "- task_id: ID da ação encontrada\n"
            "- alteracoes: dicionário com APENAS os campos que mudam. Ex: {\"data_limite\": \"2026-05-15\"}\n"
            "- justificativa: frase curta explicando o motivo (gravada silenciosamente no diário)\n"
            "Esta ferramenta NÃO faz mutação no banco. Ela prepara o payload para um card de confirmação visual.\n\n"
            "ETAPA 2 — AGUARDAR O CARD:\n"
            "Após chamar preparar_edicao_acao com sucesso, sua resposta de texto DEVE ser APENAS:\n"
            "  ✏️ Preparei a edição para sua confirmação. Verifique o card abaixo e confirme ou cancele.\n"
            "NÃO repita os dados da edição no texto — eles já estão no card visual.\n"
            "NÃO chame nenhuma outra ferramenta de escrita nesta mensagem.\n\n"
            "ETAPA 3 — APÓS CONFIRMAÇÃO:\n"
            "A confirmação ocorre pelo clique no botão do card — não pelo chat de texto.\n"
            "Se o usuário disser 'confirmo' ou 'pode fazer' no chat, explique:\n"
            "  'A confirmação de segurança deve ser feita clicando no botão ✅ do card acima.'\n\n"
            "CAMPOS SUPORTADOS: titulo, descricao, data_limite, data_inicio, horario_inicio, horario_fim, status, tags, area_tematica, tipo_acao, notas.\n"
            "Para alteração do plano de ação (passos), use o fluxo de EDIÇÃO DE PLANO DE AÇÃO acima.\n\n"
            "## REAGENDAMENTO EM LOTE — REDISTRIBUIÇÃO DE AÇÕES (CRÍTICO)\n\n"
            "Quando o usuário pedir para mover, reagendar ou redistribuir múltiplas ações de uma vez "
            "(ex: 'mova as ações de hoje para a próxima semana', 'redistribua 5 por semana'), "
            "siga OBRIGATORIAMENTE este protocolo:\n\n"
            "ETAPA 0 — ENTENDIMENTO DOS CRITÉRIOS:\n"
            "Identifique:\n"
            "  a) Filtro de origem: data_limite = qual data? Ex: hoje → use a data atual no formato YYYY-MM-DD.\n"
            "  b) Data de início do reagendamento: qual o primeiro dia útil alvo? Ex: 'próxima semana' → segunda-feira da próxima semana.\n"
            "  c) Máximo por semana: quanto o usuário quer alocar por semana? Padrão: 5.\n"
            "  d) Estratégia de ordenação: se não especificada, use 'data_criacao' (mais antigas primeiro).\n"
            "Se qualquer parâmetro for ambíguo, esclareça com uma pergunta direta ANTES de chamar a ferramenta.\n\n"
            "ETAPA 1 — PREPARAÇÃO:\n"
            "Chame preparar_reagendamento_em_lote(nova_data_inicio, max_por_semana, estrategia, filtro_data, task_ids, justificativa).\n"
            "Esta ferramenta NÃO muta o banco — apenas prepara o plano de redistribuição.\n\n"
            "ETAPA 2 — AGUARDAR O CARD:\n"
            "Após chamar preparar_reagendamento_em_lote com sucesso, sua resposta de texto DEVE ser APENAS:\n"
            "  📅 Preparei o plano de reagendamento. Verifique o card abaixo e confirme ou cancele.\n"
            "NÃO liste os reagendamentos no texto — eles já estão no card visual.\n"
            "NÃO chame nenhuma outra ferramenta de escrita nesta mensagem.\n\n"
            "ETAPA 3 — APÓS CONFIRMAÇÃO:\n"
            "A confirmação ocorre pelo clique no botão do card — não pelo chat de texto.\n\n"
            "PARÂMETRO justificativa: gere automaticamente uma frase concisa descrevendo o reagendamento "
            "(ex: 'Reagendamento em lote das ações de 2026-04-25 para a semana de 2026-04-28.').\n\n"
            "## GERAÇÃO DE RELATÓRIOS — PROTOCOLO COLLECT-THEN-REPORT\n\n"
            "Quando o usuário solicitar um relatório, análise formal, resumo executivo ou documento consolidado:\n\n"
            "ETAPA 1 — COLETA DE CONTEXTO:\n"
            "Antes de chamar gerar_relatorio, colete o máximo de contexto relevante usando as ferramentas disponíveis:\n"
            "- consultar_historico_acoes() — tarefas e histórico de execução\n"
            "- buscar_arquivos_acervo() — documentos e artefatos relevantes\n"
            "- obter_contexto_tela() — contexto da tarefa em foco (se taskId disponível)\n"
            "Consolide tudo em uma string de contexto densa para passar ao relatório.\n\n"
            "ETAPA 2 — GERAÇÃO:\n"
            "Chame gerar_relatorio(titulo, tipo, contexto) com:\n"
            "- titulo: título claro e descritivo\n"
            "- tipo: 'executivo', 'técnico', 'analítico', 'progresso' ou 'situacional'\n"
            "- contexto: string com todos os dados coletados nas buscas\n\n"
            "ETAPA 3 — RESPOSTA:\n"
            "Após gerar_relatorio retornar sucesso, responda OBRIGATORIAMENTE:\n"
            "  📄 **Relatório gerado com sucesso!**\n"
            "  - **Título:** [titulo]\n"
            "  - **Seções:** [lista das seções]\n"
            "  Clique no botão abaixo para abrir o relatório completo.\n"
            "NÃO reproduza o conteúdo do relatório no chat — ele está disponível no modal de leitura.\n\n"
            "## GERAÇÃO DE APRESENTAÇÃO DE SLIDES — PADRÃO DRAFT-FIRST (CRÍTICO)\n\n"
            "Quando o usuário solicitar uma apresentação de slides, siga OBRIGATORIAMENTE este protocolo:\n\n"
            "ETAPA 1 — ESQUELETO (Preview):\n"
            "Nunca gere o arquivo imediatamente. Apresente um esqueleto estruturado e emita o bloco [PRESENTATION]...[/PRESENTATION].\n"
            "Inclua no texto da resposta (ANTES do bloco):\n"
            "  📊 **Proposta de Apresentação: [tema]**\n"
            "  ⏱️ Tempo estimado: [X–Y minutos] (calcule dinamicamente pela densidade do conteúdo)\n\n"
            "O bloco [PRESENTATION] deve conter um objeto JSON com esta estrutura exata:\n"
            "  [PRESENTATION]{\"temaGeral\": \"string\", \"slides\": [{\"ordem\": 1, \"tipo_layout\": \"Capa\", \"titulo\": \"string\", \"subtitulo\": \"string\", \"topicos\": [], \"sugestao_imagem\": \"string\"}, ...]}\n"
            "[/PRESENTATION]\n\n"
            "Regras para o esqueleto:\n"
            "  - tipo_layout deve ser 'Capa' (apenas slide 1) ou 'Conteudo'\n"
            "  - topicos: lista de strings curtas (máx. 4 por slide)\n"
            "  - subtitulo: string vazia se não aplicável\n"
            "  - sugestao_imagem: descrição em português de imagem corporativa minimalista\n"
            "  - Use contexto da tarefa ativa (obter_contexto_tela) se taskId estiver presente; caso contrário, use estritamente o prompt/anexo\n\n"
            "ETAPA 2 — ITERAÇÃO (Ajustar):\n"
            "Se o usuário pedir ajuste na estrutura, regere o bloco [PRESENTATION] com as modificações solicitadas.\n"
            "Mantenha o mesmo formato. Não execute nenhuma ferramenta de persistência nesta etapa.\n\n"
            "ETAPA 3 — CONFIRMAÇÃO:\n"
            "Após confirmação do usuário ('confirmar', 'ok', 'gerar', etc.), o FRONTEND chama criar_apresentacao_slides diretamente.\n"
            "Você NÃO chama nenhuma ferramenta nesta etapa — apenas oriente o usuário a clicar em 'Confirmar'.\n"
            "Após o link tool:slides:{id} aparecer no chat, responda:\n"
            "  ✅ Apresentação pronta! Clique em **Abrir Apresentação** para editar e exportar.\n\n"
            "## DIAGNÓSTICO DE CÓDIGO — PADRÃO DRAFT-FIRST (CRÍTICO)\n\n"
            "Quando o usuário relatar um bug ou cole código para análise, VOCÊ decide o modo correto e emite o bloco [DIAGNOSIS].\n\n"
            "### ROTEAMENTO AUTOMÁTICO DE MODO\n\n"
            "MODO REPO — use quando:\n"
            "  - O usuário menciona um sistema específico OU taskId está presente (consulte obter_contexto_tela)\n"
            "  - O bug é sistêmico, envolve múltiplos arquivos ou integração entre módulos\n"
            "  - O usuário quer análise completa do repositório\n\n"
            "MODO SNIPPET — use quando:\n"
            "  - O usuário colou código diretamente no chat (bloco de código presente na mensagem)\n"
            "  - Não há sistema identificado no contexto\n"
            "  - O problema é localizado e autocontido\n\n"
            "### ETAPA 1 — IDENTIFICAÇÃO E EMISSÃO DO BLOCO\n\n"
            "Emita o bloco [DIAGNOSIS]...[/DIAGNOSIS] com o JSON apropriado para o modo escolhido.\n\n"
            "MODO REPO — JSON (Use o 'sistemaId' do contexto técnico OU do campo 'sistema_id' retornado por obter_contexto_tela OU do catálogo de sistemas acima):\n"
            '  [DIAGNOSIS]{"mode": "repo", "sistemaId": "id_exato_do_catalogo", "descricaoProblema": "descrição técnica concisa"}[/DIAGNOSIS]\n\n'
            "REGRA CRÍTICA: Se NÃO for possível determinar o sistemaId a partir de nenhuma dessas fontes, "
            "NÃO emita mode='repo' com sistemaId nulo. Em vez disso, use MODO SNIPPET ou pergunte "
            "ao usuário: 'Qual é o ID do sistema? Consulte o catálogo: [lista os sistemas disponíveis]'.\n\n"
            "MODO SNIPPET — JSON (inclua o código extraído da mensagem do usuário, escapado como string JSON):\n"
            '  [DIAGNOSIS]{"mode": "snippet", "codeSnippet": "...código aqui...", "fileName": "nome_inferido.ext", "descricaoProblema": "descrição técnica concisa"}[/DIAGNOSIS]\n\n'
            "Texto ANTES do bloco deve conter:\n"
            "  Modo repo:    🔍 **Diagnóstico Solicitado: [nome do sistema]** — Repositório será analisado. Confirme para iniciar.\n"
            "  Modo snippet: 🔍 **Diagnóstico de Snippet** — Código recebido. Confirme para analisar.\n\n"
            "### ETAPA 2 — ITERAÇÃO\n"
            "Se o usuário ajustar o problema, o sistema ou o código, regere o bloco [DIAGNOSIS] com as modificações.\n\n"
            "### ETAPA 3 — CONFIRMAÇÃO\n"
            "Após confirmação, o FRONTEND chama diagnosticar_codigo diretamente.\n"
            "Você NÃO chama nenhuma ferramenta. Aguarde o link tool:diagnosis:{id} aparecer no chat."

            "## GERAÇÃO DE FORMULÁRIO GOOGLE — PADRÃO DRAFT-FIRST (CRÍTICO)\n\n"
            "Quando o usuário solicitar a criação de um formulário, questionário ou pesquisa de qualquer tipo, siga OBRIGATORIAMENTE este protocolo:\n\n"
            "ETAPA 1 — ESQUELETO (Preview):\n"
            "Nunca chame APIs externas. Emita o bloco [FORM]...[/FORM] para exibir um rascunho visual ao usuário.\n"
            "Inclua no texto da resposta (ANTES do bloco):\n"
            "  📝 **Proposta de Formulário: [título]**\n\n"
            "O bloco [FORM] deve conter um objeto JSON com esta estrutura exata:\n"
            "  [FORM]{\"titulo\": \"string\", \"descricao\": \"string (opcional)\", \"perguntas\": [{\"tipo\": \"texto_curto\" | \"paragrafo\" | \"multipla_escolha\" | \"caixas_selecao\" | \"lista_suspensa\" | \"escala_linear\", \"texto\": \"string\", \"opcoes\": [\"opt1\", \"opt2\"] (se aplicável), \"escala_min\": 1, \"escala_max\": 5, \"rotulo_min\": \"string\", \"rotulo_max\": \"string\", \"obrigatoria\": true}]}[/FORM]\n\n"
            "Regras para as perguntas:\n"
            "  - tipo: DEVE ser exatamente um destes: 'texto_curto', 'paragrafo', 'multipla_escolha', 'caixas_selecao', 'lista_suspensa', 'escala_linear'.\n"
            "  - opcoes: obrigatório apenas para os tipos: 'multipla_escolha', 'caixas_selecao', 'lista_suspensa'.\n"
            "  - atributos de escala (escala_min, escala_max, rotulo_min, rotulo_max): obrigatórios apenas para 'escala_linear'.\n\n"
            "ETAPA 2 — ITERAÇÃO (Ajustar):\n"
            "Se o usuário pedir ajuste, regere o bloco [FORM] com as modificações solicitadas.\n"
            "Não execute nenhuma ferramenta de persistência nesta etapa.\n\n"
            "ETAPA 3 — CONFIRMAÇÃO:\n"
            "Após confirmação do usuário, o FRONTEND chamará a Cloud Function criar_formulario_google e inserirá o link de sucesso diretamente no chat.\n"
            "Você NÃO chama nenhuma ferramenta nesta etapa — apenas oriente o usuário a clicar em 'Confirmar e Gerar Link' no card de rascunho de formulário.\n\n"

            "## DIAGRAMAS E VISUALIZAÇÕES — RENDERIZAÇÃO DIRETA (CRÍTICO)\n\n"
            "REGRA ABSOLUTA: Sempre que o usuário pedir um diagrama, fluxograma, fluxo, mapa, grafo, sequência, "
            "hierarquia, cronograma, mapa mental ou qualquer visualização estrutural, você DEVE obrigatoriamente "
            "gerar o código dentro de um bloco de código com a linguagem 'mermaid', exatamente assim:\n\n"
            "```mermaid\n"
            "<código aqui>\n"
            "```\n\n"
            "NUNCA escreva o código Mermaid como texto puro, sem o bloco de código. "
            "NUNCA omita os marcadores de abertura (```mermaid) e fechamento (```). "
            "O frontend detecta o bloco pela linguagem 'mermaid' e renderiza o diagrama visualmente — "
            "sem o bloco correto, o diagrama não aparece.\n"
            "Não explique o diagrama antes de gerá-lo, a menos que seja explicitamente solicitado.\n"
            "Escolha o tipo de diagrama mais adequado: flowchart, sequenceDiagram, classDiagram, "
            "stateDiagram-v2, erDiagram, gantt, mindmap, timeline, pie, quadrantChart, xychart-beta, etc.\n\n"
            "## GOVERNANCA DE FONTES — REGRA CRITICA\n"
            "Quando descrever uma tarefa encontrada por consultar_historico_acoes, "
            "use SOMENTE os campos retornados por essa ferramenta (Titulo, Status, Prazo, Area, Descricao, Tags, Sintese, Plano de Acao, Diario de Bordo, Notas). "
            "E PROIBIDO completar, interpretar ou inferir informacoes da tarefa usando dados do RAG, acervo ou memoria global. "
            "Se um campo nao constar no retorno da ferramenta, responda 'nao informado' em vez de inventar.\n\n"
            "## GOVERNANÇA FINANCEIRA — REGRA ABSOLUTA\n"
            "10. Você NUNCA deve inventar, supor ou estimar valores financeiros (gastos, rendas ou saldos).\n"
            "11. Para qualquer dúvida sobre finanças, use EXCLUSIVAMENTE a ferramenta `consultar_financas_v2`.\n"
            "12. Para novos registros, use `registrar_item_financeiro_v2` sempre apresentando um rascunho para o usuário confirmar antes.\n"
            "Caso a ferramenta retorne que não há dados, relate isso honestamente. Não tente usar o RAG para buscar dados financeiros internos.\n"
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


        dynamic_tools = []
        _function_map = {
            'buscar_e_analisar_email': buscar_e_analisar_email,
            'consultar_historico_acoes': consultar_historico_acoes,
            'buscar_arquivos_acervo': buscar_arquivos_acervo,
            'obter_contexto_tela': obter_contexto_tela,
            'pesquisar_internet': pesquisar_internet,
            'ler_pagina_web': ler_pagina_web,
            'ler_documento_na_integra': ler_documento_na_integra,
            'registrar_correcao_procedimento': registrar_correcao_procedimento,
            'salvar_memoria_global': salvar_memoria_global,
            'salvar_pop_global': salvar_pop_global,
            'resolver_conflito_memoria': resolver_conflito_memoria,
            'atualizar_personalidade': atualizar_personalidade,
            'resolver_conflito_procedimento': resolver_conflito_procedimento,
            'criar_acao_no_sistema': criar_acao_no_sistema,
            'editar_plano_acao': editar_plano_acao,
            'preparar_edicao_acao': preparar_edicao_acao,
            'registrar_no_diario': registrar_no_diario,
            'gerar_relatorio': gerar_relatorio,
            'gerar_rascunho_formulario': gerar_rascunho_formulario,
            'consultar_agenda': consultar_agenda,
            'encontrar_slot_livre': encontrar_slot_livre,
            'preparar_reagendamento_em_lote': preparar_reagendamento_em_lote,
            'consultar_financas_v2': consultar_financas_v2,
            'registrar_item_financeiro_v2': registrar_item_financeiro_v2,
            'calculadora': calculadora,
        }

        # Cria função genérica de acionamento que o loop manual do Python irá ignorar
        # mas que vamos retornar direto pro frontend
        def acionar_ferramenta(tool_id: str, parametros: dict = None):
            return {"intent": "tool_invocation", "tool_id": tool_id, "parametros": parametros or {}}

        _function_map['acionar_ferramenta'] = acionar_ferramenta

        for t in routing_index:
            tool_id = t['id']
            schema = t.get('parametersSchema', {})
            props = {}
            required = schema.get('required', [])
            for k, v in schema.get('properties', {}).items():
                v_type = v.get('type', 'string').upper()
                if v_type == 'STRING':
                    t_enum = types.Type.STRING
                elif v_type == 'INTEGER':
                    t_enum = types.Type.INTEGER
                elif v_type == 'NUMBER':
                    t_enum = types.Type.NUMBER
                elif v_type == 'BOOLEAN':
                    t_enum = types.Type.BOOLEAN
                elif v_type == 'ARRAY':
                    t_enum = types.Type.ARRAY
                elif v_type == 'OBJECT':
                    t_enum = types.Type.OBJECT
                else:
                    t_enum = types.Type.STRING
                props[k] = types.Schema(type=t_enum, description=v.get('description', ''))

            tool_func = types.FunctionDeclaration(
                name=f"acionar_{tool_id}",
                description=f"Aciona a ferramenta interativa {tool_id} na interface do usuário.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties=props,
                    required=required
                )
            )
            dynamic_tools.append(tool_func)

            # Helper function to intercept dynamic tools
            def _make_tool_invoker(tid):
                def invoke(**kwargs):
                    return {"intent": "tool_invocation", "tool_id": tid, "parametros": kwargs}
                return invoke

            _function_map[f"acionar_{tool_id}"] = _make_tool_invoker(tool_id)


        # Reassign map for old static tools if needed but we just updated it above
        _old_function_map = {
            'buscar_e_analisar_email': buscar_e_analisar_email,
            'consultar_historico_acoes': consultar_historico_acoes,
            'buscar_arquivos_acervo': buscar_arquivos_acervo,
            'obter_contexto_tela': obter_contexto_tela,
            'pesquisar_internet': pesquisar_internet,
            'ler_pagina_web': ler_pagina_web,
            'ler_documento_na_integra': ler_documento_na_integra,
            'registrar_correcao_procedimento': registrar_correcao_procedimento,
            'salvar_memoria_global': salvar_memoria_global,
            'salvar_pop_global': salvar_pop_global,
            'resolver_conflito_memoria': resolver_conflito_memoria,
            'atualizar_personalidade': atualizar_personalidade,
            'resolver_conflito_procedimento': resolver_conflito_procedimento,
            'criar_acao_no_sistema': criar_acao_no_sistema,
            'editar_plano_acao': editar_plano_acao,
            'preparar_edicao_acao': preparar_edicao_acao,
            'registrar_no_diario': registrar_no_diario,
            'gerar_relatorio': gerar_relatorio,
            'gerar_rascunho_formulario': gerar_rascunho_formulario,
            'consultar_agenda': consultar_agenda,
            'encontrar_slot_livre': encontrar_slot_livre,
            'preparar_reagendamento_em_lote': preparar_reagendamento_em_lote,
            'consultar_financas_v2': consultar_financas_v2,
            'registrar_item_financeiro_v2': registrar_item_financeiro_v2,
            'calculadora': calculadora,
        }
        # Ferramentas internas que não devem aparecer para o usuário
        _HIDDEN_TOOLS = {'registrar_correcao_procedimento', 'resolver_conflito_memoria'}

        chat = client.chats.create(
            model=model_id,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction + _correcao_hint,
                http_options=types.HttpOptions(timeout=COPILOT_MODEL_TIMEOUT_MS),
                tools=[
                    buscar_e_analisar_email,
                    consultar_historico_acoes,
                    buscar_arquivos_acervo,
                    obter_contexto_tela,
                    pesquisar_internet,
                    ler_pagina_web,
                    ler_documento_na_integra,
                    registrar_correcao_procedimento,
                    salvar_memoria_global,
                    salvar_pop_global,
                    resolver_conflito_memoria,
                    atualizar_personalidade,
                    resolver_conflito_procedimento,
                    criar_acao_no_sistema,
                    editar_plano_acao,
                    preparar_edicao_acao,
                    registrar_no_diario,
                    gerar_relatorio,
                    gerar_rascunho_formulario,
                    consultar_agenda,
                    encontrar_slot_livre,
                    preparar_reagendamento_em_lote,
                    consultar_financas_v2,
                    registrar_item_financeiro_v2,
                    calculadora,
                ] + dynamic_tools,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            ),
            history=history
        )
        _perf_mark(perf_state, "web.chat_create")

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
                is_image_file = real_mime_type.startswith('image/')
                task_context_summary = ""
                if task_id:
                    try:
                        task_doc = db.collection('tarefas').document(task_id).get()
                        if task_doc.exists:
                            task_data = task_doc.to_dict() or {}
                            plano = task_data.get('plano_acao', []) or []
                            task_context_summary = (
                                f"Tarefa atual: {task_data.get('titulo', 'Sem título')}\n"
                                f"Área temática: {task_data.get('area_tematica', 'Não informada')}\n"
                                f"Descrição: {task_data.get('descricao', '')[:1200]}\n"
                                f"Plano atual: {' | '.join(plano[:5]) if plano else 'Não definido'}"
                            )
                    except Exception as task_ctx_err:
                        print(f"[Copiloto] Aviso: falha ao montar contexto resumido da tarefa {task_id}: {task_ctx_err}")

                # 2. Baixa o binário para memória volátil
                request_dl = drive_service.files().get_media(fileId=drive_file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request_dl)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                fh.seek(0)
                file_bytes = fh.read()
                local_pdf_text = ""
                local_pdf_metadata = None
                local_docx_text = ""
                local_docx_metadata = None
                if is_pdf_mime_type(real_file_name, real_mime_type):
                    pdf_result = extract_pdf_text_with_fallback(
                        file_bytes,
                        real_file_name,
                        api_key=gemini_key,
                        allow_gemini_fallback=False,
                    )
                    local_pdf_text = (pdf_result.get('text') or '').strip()
                    local_pdf_metadata = pdf_result.get('metadata')
                elif is_docx_mime_type(real_file_name, real_mime_type):
                    local_docx_text, local_docx_metadata = extract_docx_text(file_bytes)

                gemini_file = None
                local_extracted_text = local_pdf_text or local_docx_text
                local_extraction_metadata = local_pdf_metadata or local_docx_metadata
                if is_image_file or not local_extracted_text:
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
                    if is_image_file:
                        extraction_prompt = (
                            f"Você recebeu a imagem '{real_file_name}'. "
                            "Analise o conteúdo visual integral e retorne EXCLUSIVAMENTE um JSON válido, "
                            "sem markdown, sem texto extra, com esta estrutura:\n"
                            '{"titulo": "...", "natureza": "...", "resumo": "...", '
                            '"ocr": "...", "descricao_visual": "...", '
                            '"elementos_chave": ["..."], "evidencias": ["..."], '
                            '"relacao_com_acao": "...", "utilidade_pratica": "..."}\n'
                            "Regras:\n"
                            "- titulo: nome curto e útil do anexo.\n"
                            "- natureza: classifique a imagem com precisão (ex: print de sistema, comprovante, gráfico, documento fotografado, quadro, planilha capturada, foto de ambiente).\n"
                            "- resumo: resumo executivo em 3 a 5 frases.\n"
                            "- ocr: transcreva o texto visível mais relevante. Se não houver, use string vazia.\n"
                            "- descricao_visual: descreva objetivamente o que aparece na imagem.\n"
                            "- elementos_chave: liste de 3 a 8 elementos centrais percebidos.\n"
                            "- evidencias: liste fatos observáveis que sustentam sua leitura.\n"
                            "- relacao_com_acao: explique como a imagem se conecta com a tarefa em foco. Se não houver contexto suficiente, diga isso explicitamente.\n"
                            "- utilidade_pratica: diga como o Hermes deve usar esta imagem para apoiar a ação.\n"
                            f"\nCONTEXTO DA AÇÃO:\n{task_context_summary or 'Nenhuma tarefa ativa foi fornecida.'}"
                        )
                    elif local_extracted_text:
                        extraction_prompt = (
                            f"Você recebeu o texto extraído localmente do arquivo '{real_file_name}'. "
                            "Retorne EXCLUSIVAMENTE um JSON válido, sem markdown, sem texto extra, com esta estrutura:\n"
                            '{"titulo": "...", "natureza": "...", "resumo": "...", '
                            '"relacao_com_acao": "...", "utilidade_pratica": "..."}\n'
                            "Onde:\n"
                            "- titulo: nome/título do documento\n"
                            "- natureza: categoria (ex: Edital, Contrato, Relatório, Manual, Planilha, etc.)\n"
                            "- resumo: resumo executivo em 3 a 5 frases sobre conteúdo e utilidade\n"
                            "- relacao_com_acao: explique a conexão do arquivo com a tarefa atual; se não houver contexto suficiente, diga isso explicitamente\n"
                            "- utilidade_pratica: diga como o Hermes deve usar este arquivo para apoiar a ação\n"
                            f"\nCONTEXTO DA AÇÃO:\n{task_context_summary or 'Nenhuma tarefa ativa foi fornecida.'}\n\n"
                            f"METADADOS DA EXTRAÇÃO LOCAL: {json.dumps(local_extraction_metadata or {}, ensure_ascii=False)}\n\n"
                            f"TEXTO EXTRAÍDO:\n{local_extracted_text[:120000]}"
                        )
                        extraction_response = client.models.generate_content(
                            model=model_id,
                            contents=[extraction_prompt]
                        )
                    else:
                        extraction_prompt = (
                            f"Você recebeu o arquivo '{real_file_name}'. "
                            "Leia no máximo os primeiros 8.000 tokens de conteúdo. "
                            "Retorne EXCLUSIVAMENTE um JSON válido, sem markdown, sem texto extra, com esta estrutura:\n"
                            '{"titulo": "...", "natureza": "...", "resumo": "...", '
                            '"relacao_com_acao": "...", "utilidade_pratica": "..."}\n'
                            "Onde:\n"
                            "- titulo: nome/título do documento\n"
                            "- natureza: categoria (ex: Edital, Contrato, Relatório, Manual, Planilha, etc.)\n"
                            "- resumo: resumo executivo em 3 a 5 frases sobre conteúdo e utilidade\n"
                            "- relacao_com_acao: explique a conexão do arquivo com a tarefa atual; se não houver contexto suficiente, diga isso explicitamente\n"
                            "- utilidade_pratica: diga como o Hermes deve usar este arquivo para apoiar a ação\n"
                            f"\nCONTEXTO DA AÇÃO:\n{task_context_summary or 'Nenhuma tarefa ativa foi fornecida.'}"
                        )
                    if is_image_file or not local_extracted_text:
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
                    relacao_com_acao = meta.get('relacao_com_acao', '')
                    utilidade_pratica = meta.get('utilidade_pratica', '')
                    ocr_doc = meta.get('ocr', '') if is_image_file else ''
                    descricao_visual = meta.get('descricao_visual', '') if is_image_file else ''
                    elementos_chave = meta.get('elementos_chave', []) if is_image_file else []
                    evidencias = meta.get('evidencias', []) if is_image_file else []
                    if not isinstance(elementos_chave, list):
                        elementos_chave = [str(elementos_chave)]
                    if not isinstance(evidencias, list):
                        evidencias = [str(evidencias)]

                    # 6. Vetoriza e grava no indice_artefatos
                    from knowledge_graph import _get_embedding
                    embed_text_parts = [
                        titulo_doc,
                        natureza_doc,
                        resumo_doc,
                        relacao_com_acao,
                        utilidade_pratica,
                    ]
                    if is_image_file:
                        embed_text_parts.extend([
                            descricao_visual,
                            ocr_doc,
                            " | ".join(elementos_chave[:8]),
                            " | ".join(evidencias[:8]),
                        ])
                    embed_text = " | ".join(part for part in embed_text_parts if part)
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
                        'texto_bruto': (local_extracted_text or ocr_doc or resumo_doc)[:500000],
                        'fonte': natureza_doc,
                        'embedding': Vector(embedding_floats),
                        'tipo_arquivo': real_mime_type.split('/')[-1],
                        'mime_type': real_mime_type,
                        'url_drive': drive_link,
                        'drive_file_id': drive_file_id,
                        'data_criacao': firestore.SERVER_TIMESTAMP,
                        'origem': origem_doc,
                        'task_id': task_id or None,
                        'categoria': 'Copiloto Hermes',
                        'relacao_com_acao': relacao_com_acao,
                        'utilidade_pratica': utilidade_pratica,
                        'ocr': ocr_doc,
                        'descricao_visual': descricao_visual,
                        'elementos_chave': elementos_chave[:8],
                        'evidencias': evidencias[:8],
                        'texto_extraido_por': 'local_extractor' if local_extracted_text else ('gemini_ocr' if is_image_file else 'gemini_file_api'),
                        'extraction_metadata': local_extraction_metadata if local_extraction_metadata else None,
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
                        f"Tipo MIME: {real_mime_type}\n"
                        f"Título extraído: {titulo_doc}\n"
                        f"Natureza: {natureza_doc}\n"
                        f"Resumo: {resumo_doc}\n"
                        f"Relação com a ação: {relacao_com_acao or 'Não inferida.'}\n"
                        f"Utilidade prática: {utilidade_pratica or 'Não inferida.'}\n"
                        f"Texto local relevante: {local_extracted_text[:2500] if local_extracted_text else 'Não aplicável.'}\n"
                        f"OCR relevante: {ocr_doc[:2500] if ocr_doc else 'Sem texto legível relevante.'}\n"
                        f"Descrição visual: {descricao_visual or 'Não aplicável.'}\n"
                        f"Elementos-chave: {', '.join(elementos_chave[:8]) if elementos_chave else 'Nenhum listado.'}\n"
                        f"Evidências observáveis: {', '.join(evidencias[:8]) if evidencias else 'Nenhuma listada.'}\n"
                        f"Link original: {drive_link}\n"
                        f"[/CONTEXTO DO ARQUIVO ANEXADO]"
                    )

                finally:
                    # Limpeza obrigatória — evita acúmulo na File API do Gemini
                    if gemini_file is not None:
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
        _perf_mark(perf_state, "web.file_ingestion")
        initial_context = ""
        if task_id:
            initial_context = f"DICA DE CONTEXTO: O usuário está visualizando a tarefa {task_id}. " \
                             f"Use obter_contexto_tela('{task_id}') para se situar antes de responder."

        # Monta prompt final combinando task context + file context + pergunta do usuário
        context_parts = []
        if initial_context:
            context_parts.append(initial_context)
        if memory_context:
            context_parts.append(memory_context)
        if session_conflict_context:
            context_parts.append(session_conflict_context)
        if file_context:
            context_parts.append(file_context)
        context_parts.append(f"USUÁRIO: {prompt}")
        if matched_pop_directives:
            pop_lines = [
                "[DIRETRIZES OPERACIONAIS (POPs) CORRESPONDENTES - OBRIGATORIAS]"
            ]
            for idx, pop in enumerate(matched_pop_directives, start=1):
                triggers = ", ".join(pop.get("matched_triggers", []))
                pop_lines.append(
                    f"{idx}. TITULO: {pop.get('titulo', 'POP')}\n"
                    f"GATILHOS ACIONADOS: {triggers or 'n/a'}\n"
                    f"INSTRUCAO:\n{pop.get('instrucao_sistema', '')}"
                )
            pop_lines.append(
                "Aplique as diretrizes acima ao responder e ao decidir quais ferramentas usar. "
                "As diretrizes acima ja foram recuperadas do Gestor de POPs; nao declare ausencia de POP "
                "nem use Acervo/Internet apenas para confirmar a existencia deste POP. "
                "Se houver conflito entre POP e pedido literal do usuario, exponha o conflito antes de agir."
            )
            pop_lines.append("[/DIRETRIZES OPERACIONAIS (POPs) CORRESPONDENTES - OBRIGATORIAS]")
            context_parts.append("\n".join(pop_lines))
        final_prompt = "\n\n".join(context_parts)
        _perf_mark(perf_state, "web.prompt_build")
        # Loop manual de tool calling — intercepta cada chamada para rastrear ferramentas usadas
        tools_used: list[str] = []
        pending_edit_data = None
        pending_batch_reschedule_data = None
        pending_memory_conflict = None
        report_data = None
        tool_invocation_data = None
        deadline_fallback_text = None
        response = chat.send_message(final_prompt)
        _perf_mark(perf_state, "web.first_model_response")
        _max_iter = 10
        for _round in range(_max_iter):
            if _copilot_remaining_sec() < 75:
                deadline_fallback_text = (
                    "A consulta chegou perto do limite seguro de processamento. "
                    "Interrompi antes do timeout para preservar a conversa. "
                    "Tente pedir uma leitura mais especifica ou dividir a solicitacao em partes menores."
                )
                _perf_mark(perf_state, "web.soft_deadline")
                break

            fcs = response.function_calls
            if not fcs:
                break
            
            function_response_parts = []
            # Constraint: Se mais de 3 roundtrips, forçar consolidação ou emitir aviso parcial
            if _round >= 3:
                # Injeta aviso diretamente no contexto do próximo turno para forçar consolidação
                function_response_parts.append(types.Part(text="\nAVISO DE PERFORMANCE: Você já realizou 3 rodadas de consultas sequenciais. Para evitar latência excessiva, consolide TODAS as buscas restantes em um único lote (batch) nesta rodada ou emita uma resposta parcial informando que está compilando os dados."))
            break_loop = False
            # Paralelismo de Execução de Ferramentas: processa múltiplas ferramentas simultaneamente em uma única rodada
            from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor, wait as _futures_wait
            
            def _execute_tool(idx, fc):
                fn = _function_map.get(fc.name)
                tool_start_ms = _perf_now_ms()
                tool_invocation_data_local = None
                
                if fn is None:
                    res = f"Ferramenta '{fc.name}' não encontrada."
                else:
                    try:
                        res = fn(**(fc.args or {}))
                        if isinstance(res, dict) and res.get("intent") == "tool_invocation":
                            tool_invocation_data_local = res
                    except Exception as _fe:
                        res = f"Erro ao executar {fc.name}: {_fe}"
                
                perf_state.setdefault("tool_calls", []).append({
                    "name": fc.name,
                    "duration_ms": max(0, _perf_now_ms() - tool_start_ms),
                })
                return (res, tool_invocation_data_local)

            _executor = _ThreadPoolExecutor(max_workers=min(len(fcs), 8))
            try:
                _futures = [_executor.submit(_execute_tool, i, fc) for i, fc in enumerate(fcs)]
                _tool_wait_sec = min(COPILOT_TOOL_TIMEOUT_SEC, max(5.0, _copilot_remaining_sec() - 75))
                _done_futures, _pending_futures = _futures_wait(_futures, timeout=_tool_wait_sec)
                if _pending_futures:
                    for _pending in _pending_futures:
                        _pending.cancel()
                    deadline_fallback_text = (
                        "Uma das consultas internas demorou demais e eu interrompi o processamento "
                        "antes que a conversa ficasse travada. Tente pedir primeiro uma lista objetiva "
                        "dos itens pendentes e, em seguida, solicite a proposta completa."
                    )
                    _perf_mark(perf_state, "web.tool_timeout")

                for _i, _future in enumerate(_futures):
                    _fc = fcs[_i]
                    if _future not in _done_futures:
                        result = f"Timeout ao executar {getattr(_fc, 'name', 'ferramenta')}: limite de {COPILOT_TOOL_TIMEOUT_SEC}s excedido."
                        tool_invocation_data_local = None
                    else:
                        result, tool_invocation_data_local = _future.result()
                    
                    if tool_invocation_data_local:
                        tool_invocation_data = tool_invocation_data_local
                        break_loop = True
                    
                    # Processamento síncrono de efeitos colaterais
                    if _fc.name == 'preparar_edicao_acao' and isinstance(result, str) and result.startswith('{'):
                        try: pending_edit_data = json.loads(result)
                        except: pass
                    if _fc.name == 'preparar_reagendamento_em_lote' and isinstance(result, str) and result.startswith('{'):
                        try: pending_batch_reschedule_data = json.loads(result)
                        except: pass
                    if _fc.name == 'gerar_relatorio' and isinstance(result, str) and result.startswith('{'):
                        try:
                            parsed_rep = json.loads(result)
                            if parsed_rep.get('report_id'): report_data = parsed_rep
                        except: pass
                    if _fc.name == 'salvar_memoria_global' and isinstance(result, str) and result.startswith('{'):
                        try:
                            parsed_mem = json.loads(result)
                            if parsed_mem.get('status') == 'conflict':
                                parsed_mem.setdefault('status_ui', 'pending')
                                pending_memory_conflict = parsed_mem
                            if session_ref:
                                if parsed_mem.get('status') == 'conflict':
                                    session_ref.set({"pendingMemoryConflict": parsed_mem, "lastMemoryConflictAt": firestore.SERVER_TIMESTAMP}, merge=True)
                                else:
                                    session_ref.update({"pendingMemoryConflict": firestore.DELETE_FIELD, "lastMemoryConflictAt": firestore.DELETE_FIELD})
                        except: pass
                    if _fc.name == 'resolver_conflito_memoria' and isinstance(result, str) and result.startswith('{'):
                        try:
                            parsed_resolution = json.loads(result)
                            if session_ref and parsed_resolution.get('status') in {'resolved', 'updated'}:
                                session_ref.set({"pendingMemoryConflict": firestore.DELETE_FIELD, "lastMemoryConflictResolutionAt": firestore.SERVER_TIMESTAMP}, merge=True)
                                try: session_ref.update({"lastMemoryConflictAt": firestore.DELETE_FIELD})
                                except: pass
                        except: pass

                    if _fc.name not in _HIDDEN_TOOLS and _fc.name not in tools_used:
                        tools_used.append(_fc.name)

                    _result_str = str(result)
                    if len(_result_str) > 12000:
                        _result_str = _result_str[:12000] + "\n[...resultado truncado por tamanho...]"
                    
                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=_fc.name,
                            response={"result": _result_str}
                        )
                    )
            finally:
                _executor.shutdown(wait=False, cancel_futures=True)

            if break_loop:
                break

            if deadline_fallback_text:
                break

            if _copilot_remaining_sec() < 75:
                deadline_fallback_text = (
                    "Executei as ferramentas necessarias, mas a consolidacao da resposta chegou perto "
                    "do limite seguro de processamento. Para evitar uma falha por timeout, parei aqui. "
                    "Tente refazer a pergunta de forma mais focada ou solicitar o proximo trecho."
                )
                _perf_mark(perf_state, "web.soft_deadline")
                break

            try:
                response = chat.send_message(function_response_parts)
                _perf_mark(perf_state, "web.tool_roundtrip")
            except Exception as _send_err:
                from google.genai.errors import ServerError as _GeminiServerError
                if isinstance(_send_err, _GeminiServerError) and '500' in str(_send_err):
                    print(f"[Copiloto] Gemini 500 ao enviar resultados de ferramentas — tentando com payload reduzido: {_send_err}")
                    _reduced_parts = []
                    for _p in function_response_parts:
                        try:
                            _r = _p.function_response.response.get("result", "")
                            if len(_r) > 4000:
                                _r = _r[:4000] + "\n[...truncado para retry...]"
                            _reduced_parts.append(
                                types.Part.from_function_response(
                                    name=_p.function_response.name,
                                    response={"result": _r}
                                )
                            )
                        except Exception:
                            _reduced_parts.append(_p)
                    response = chat.send_message(_reduced_parts)
                    _perf_mark(perf_state, "web.tool_roundtrip_retry")
                else:
                    raise

        if tool_invocation_data:
            clean_text = "[Invocando Ferramenta...]"
            suggested_title = prompt[:50] if prompt and len(prompt) < 100 else None

            if session_id:
                try:
                    db.collection('sessoes_copiloto').document(session_id).collection('mensagens').add({
                        "role": "assistant",
                        "content": clean_text,
                        "toolInvocation": tool_invocation_data,
                        "toolsUsed": tools_used if tools_used else None,
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    db.collection('sessoes_copiloto').document(session_id).set({
                        "lastMessageAt": firestore.SERVER_TIMESTAMP
                    }, merge=True)
                except Exception as e:
                    print(f"Erro ao salvar invocação de ferramenta no Firestore: {e}")

            _perf_mark(perf_state, "web.tool_invocation_persist")
            _perf_log(
                "web.askCopiloto.complete",
                perf_state,
                {
                    "session_id": session_id,
                    "task_id": task_id,
                    "mode": "tool_invocation",
                    "tools_used": tools_used,
                },
            )
            return {
                "result": clean_text,
                "kg_nodes": kg_nodes_payload,
                "toolInvocation": tool_invocation_data,
                "suggestedTitle": suggested_title
            }

        if deadline_fallback_text:
            result_text = deadline_fallback_text
        else:
            try:
                result_text = response.text or ""
            except Exception as _text_err:
                print(f"[Copiloto] response.text falhou: {_text_err}")
                result_text = ""
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

        # Extração de Esqueleto de Apresentação [PRESENTATION]{...}[/PRESENTATION]
        presentation_data = None
        if "[PRESENTATION]" in clean_text:
            try:
                pres_parts = clean_text.split("[PRESENTATION]")
                pres_raw = pres_parts[1].split("[/PRESENTATION]")[0]
                presentation_data = json.loads(pres_raw)
                clean_text = pres_parts[0] + (pres_parts[1].split("[/PRESENTATION]")[1] if "[/PRESENTATION]" in pres_parts[1] else "")
                clean_text = clean_text.strip()
            except Exception as e:
                print(f"Erro ao extrair apresentação: {e}")


        # Extração de Formulário [FORM]{...}[/FORM]
        form_data = None
        if "[FORM]" in clean_text:
            try:
                form_parts = clean_text.split("[FORM]")
                form_raw = form_parts[1].split("[/FORM]")[0]
                form_data = json.loads(form_raw)
                clean_text = form_parts[0] + (form_parts[1].split("[/FORM]")[1] if "[/FORM]" in form_parts[1] else "")
                clean_text = clean_text.strip()
            except Exception as e:
                print(f"Erro ao extrair formulário: {e}")

        # Extração de Solicitação de Diagnóstico [DIAGNOSIS]{...}[/DIAGNOSIS]
        diagnosis_request_data = None
        if "[DIAGNOSIS]" in clean_text:
            try:
                diag_parts = clean_text.split("[DIAGNOSIS]")
                diag_raw = diag_parts[1].split("[/DIAGNOSIS]")[0]
                diagnosis_request_data = json.loads(diag_raw)
                clean_text = diag_parts[0] + (diag_parts[1].split("[/DIAGNOSIS]")[1] if "[/DIAGNOSIS]" in diag_parts[1] else "")
                clean_text = clean_text.strip()
            except Exception as e:
                print(f"Erro ao extrair diagnóstico: {e}")

        # Salva a resposta do assistente no Firestore para o histórico
        if session_id:
            try:
                db.collection('sessoes_copiloto').document(session_id).collection('mensagens').add({
                    "role": "assistant",
                    "content": clean_text,
                    "proposedPlan": proposal_data.get("items") if proposal_data else None,
                    "proposedPresentation": presentation_data if presentation_data else None,
                    "proposedDiagnosis": diagnosis_request_data if diagnosis_request_data else None,
                    "proposedForm": form_data if form_data else None,
                    "toolsUsed": tools_used if tools_used else None,
                    "pendingEdit": pending_edit_data,
                    "pendingBatchReschedule": pending_batch_reschedule_data,
                    "pendingMemoryConflict": pending_memory_conflict,
                    "reportId": report_data.get('report_id') if report_data else None,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                # Atualiza timestamp da sessão
                db.collection('sessoes_copiloto').document(session_id).set({
                    "lastMessageAt": firestore.SERVER_TIMESTAMP
                }, merge=True)
            except Exception as e:
                print(f"Erro ao salvar resposta no Firestore: {e}")

        # Tenta extrair título sugerido se for início de sessão
        _perf_mark(perf_state, "web.response_persist")
        suggested_title = None
        if prompt and len(prompt) < 100:
            suggested_title = prompt[:50]

        _perf_log(
            "web.askCopiloto.complete",
            perf_state,
            {
                "session_id": session_id,
                "task_id": task_id,
                "mode": "assistant_text",
                "tools_used": tools_used,
            },
        )
        return {
            "result": clean_text,
            "proposedPlan": proposal_data.get("items") if proposal_data else None,
            "proposedPresentation": presentation_data if presentation_data else None,
            "proposedDiagnosis": diagnosis_request_data if diagnosis_request_data else None,
            "pendingMemoryConflict": pending_memory_conflict,
            "suggestedTitle": suggested_title,
            "pendingEdit": pending_edit_data,
            "reportId": report_data.get('report_id') if report_data else None
        }

    except Exception as e:
        print(f"Erro em askCopilotoHermes: {e}")
        _perf_log("web.askCopiloto.error", perf_state, {"session_id": session_id, "task_id": task_id, "error": str(e)})
        import traceback
        print(traceback.format_exc())
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )

@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
    timeout_sec=30
)
def confirmarEdicaoAcao(req: https_fn.CallableRequest):
    """
    Confirma e executa uma edição de ação pendente gerada pelo Copiloto Hermes.
    Aplica validação lazy antes de mutar: verifica que a ação não foi modificada
    desde a geração do card de confirmação.
    """
    data = req.data or {}
    session_id = data.get('sessionId')
    message_id = data.get('messageId')
    task_id = data.get('taskId')
    alteracoes = data.get('alteracoes', {})
    snapshot_ts = data.get('snapshotTs', '')

    if not task_id or not alteracoes:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="taskId e alteracoes são obrigatórios."
        )

    def _set_card_status(db_ref, status, error_msg=None):
        if not session_id or not message_id:
            return
        try:
            update_payload = {'pendingEdit.status': status}
            if error_msg:
                update_payload['pendingEdit.errorMessage'] = error_msg
            db_ref.collection('sessoes_copiloto').document(session_id)\
                .collection('mensagens').document(message_id)\
                .update(update_payload)
        except Exception as _ue:
            print(f"[confirmarEdicaoAcao] Falha ao atualizar status do card: {_ue}")

    try:
        from datetime import datetime as _dt, timezone as _tz

        db_ref = get_db()
        task_ref = db_ref.collection('tarefas').document(task_id)
        task_doc = task_ref.get()

        # Validação 1: ação existe?
        if not task_doc.exists:
            msg = 'Edição bloqueada: Esta ação não existe mais.'
            _set_card_status(db_ref, 'invalidated', msg)
            return {'status': 'invalidated', 'message': msg}

        task_data = task_doc.to_dict()

        # Validação 2: ação já concluída?
        if task_data.get('status') == 'concluído':
            msg = 'Edição bloqueada: Esta ação já foi concluída.'
            _set_card_status(db_ref, 'invalidated', msg)
            return {'status': 'invalidated', 'message': msg}

        # Validação 3 (lazy): ação foi modificada desde a geração do card?
        current_ts = task_data.get('data_atualizacao') or task_data.get('data_criacao', '')
        if snapshot_ts and current_ts and str(current_ts) != str(snapshot_ts):
            msg = 'Edição bloqueada: Esta ação foi modificada após a geração deste card.'
            _set_card_status(db_ref, 'invalidated', msg)
            return {'status': 'invalidated', 'message': msg}

        # Aplica mudanças — somente campos whitelistados
        _ALLOWED = {'titulo', 'descricao', 'data_limite', 'data_inicio', 'horario_inicio', 'horario_fim', 'status', 'tags', 'area_tematica', 'tipo_acao', 'notas'}

        def _normalizar_status_acao(valor):
            if valor is None:
                return valor
            raw = str(valor).strip().lower()
            try:
                import unicodedata
                raw = ''.join(c for c in unicodedata.normalize('NFD', raw) if unicodedata.category(c) != 'Mn')
            except Exception:
                pass
            raw = raw.replace('_', ' ').replace('-', ' ')
            raw = ' '.join(raw.split())
            if raw in ('concluido', 'concluida', 'concluir', 'finalizado', 'finalizada', 'completed', 'done'):
                return 'concluído'
            if raw in ('stand by', 'standby', 'pausado', 'pausada', 'pausar'):
                return 'stand-by'
            if raw in ('em andamento', 'andamento', 'pendente', 'aberto', 'aberta', 'reabrir'):
                return 'em andamento'
            return valor

        updates = {}
        for campo, novo_valor in alteracoes.items():
            if campo not in _ALLOWED:
                continue
            if campo == 'status':
                novo_valor = _normalizar_status_acao(novo_valor)
                if novo_valor not in ('em andamento', 'stand-by', 'concluído'):
                    continue
            updates[campo] = novo_valor

        # Acoes usam data unica. Mantem data_limite e data_inicio espelhadas
        # mesmo quando a edicao vier de ferramentas/backend que enviam so um campo.
        if 'data_limite' in updates or 'data_inicio' in updates:
            single_date = updates.get('data_limite') or updates.get('data_inicio') or ''
            updates['data_limite'] = single_date
            updates['data_inicio'] = single_date

        if not updates:
            _set_card_status(db_ref, 'error', 'Nenhum campo válido para atualizar.')
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Nenhum campo válido para atualizar."
            )

        now_iso = _dt.now(_tz.utc).isoformat()
        updates['data_atualizacao'] = now_iso
        if updates.get('status') == 'concluído':
            updates['data_conclusao'] = now_iso
        elif updates.get('status') in ('em andamento', 'stand-by'):
            updates['data_conclusao'] = None

        campos_desc = ', '.join(k for k in updates if k not in ('data_atualizacao', 'data_conclusao'))
        diary_entry = {
            'data': now_iso,
            'nota': f"[Copiloto Hermes] Ação editada via card de confirmação. Campos alterados: {campos_desc}."
        }

        task_ref.update({
            **updates,
            'acompanhamento': firestore.ArrayUnion([diary_entry])
        })

        _set_card_status(db_ref, 'completed')
        print(f"[confirmarEdicaoAcao] task_id={task_id} atualizado: {list(updates.keys())}")
        return {'status': 'completed'}

    except https_fn.HttpsError:
        raise
    except Exception as e:
        print(f"Erro em confirmarEdicaoAcao: {e}")
        try:
            _set_card_status(get_db(), 'error', str(e))
        except Exception:
            pass
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )


@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
    timeout_sec=30
)
def confirmarReagendamentoEmLote(req: https_fn.CallableRequest):
    """
    Confirma e executa o reagendamento em lote de ações preparado pelo Copiloto Hermes.
    Aplica as novas datas atomicamente via WriteBatch e registra no diário de cada ação.
    """
    data = req.data or {}
    session_id = data.get('sessionId')
    message_id = data.get('messageId')
    items = data.get('items', [])
    justificativa = data.get('justificativa', 'Reagendamento em lote via Copiloto Hermes.')

    if not items:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="items é obrigatório e não pode ser vazio."
        )

    def _set_batch_card_status(db_ref, status, error_msg=None):
        if not session_id or not message_id:
            return
        try:
            update_payload = {'pendingBatchReschedule.status': status}
            if error_msg:
                update_payload['pendingBatchReschedule.errorMessage'] = error_msg
            db_ref.collection('sessoes_copiloto').document(session_id)\
                .collection('mensagens').document(message_id)\
                .update(update_payload)
        except Exception as _ue:
            print(f"[confirmarReagendamentoEmLote] Falha ao atualizar card: {_ue}")

    try:
        from datetime import datetime as _dt, timezone as _tz

        db_ref = get_db()
        batch = db_ref.batch()
        now_iso = _dt.now(_tz.utc).isoformat()
        diary_entry = {
            'data': now_iso,
            'nota': f"[Copiloto Hermes] {justificativa}"
        }

        count = 0
        for item in items:
            task_id = item.get('task_id')
            if not task_id:
                continue

            updates = {'data_atualizacao': now_iso}
            if item.get('nova_data_limite'):
                updates['data_limite'] = item['nova_data_limite']
                updates['data_inicio'] = item['nova_data_limite']
            if item.get('novo_horario_inicio') is not None:
                updates['horario_inicio'] = item['novo_horario_inicio']
            if item.get('novo_horario_fim') is not None:
                updates['horario_fim'] = item['novo_horario_fim']

            task_ref = db_ref.collection('tarefas').document(task_id)
            batch.update(task_ref, {
                **updates,
                'acompanhamento': firestore.ArrayUnion([diary_entry])
            })
            count += 1

        batch.commit()
        _set_batch_card_status(db_ref, 'completed')
        print(f"[confirmarReagendamentoEmLote] {count} ações reagendadas.")
        return {'status': 'completed', 'count': count}

    except https_fn.HttpsError:
        raise
    except Exception as e:
        print(f"Erro em confirmarReagendamentoEmLote: {e}")
        try:
            _set_batch_card_status(get_db(), 'error', str(e))
        except Exception:
            pass
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )


@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.MB_256,
    timeout_sec=60
)
def confirmarConflitoMemoria(req: https_fn.CallableRequest):
    data = req.data or {}
    session_id = data.get('sessionId')
    message_id = data.get('messageId')
    memoria_id = data.get('memoriaId')
    decisao = data.get('decisao')
    fato_atualizado = data.get('fatoAtualizado') or ''
    categoria = data.get('categoria') or 'fato_isolado'

    if not session_id or not message_id or not memoria_id or not decisao:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="sessionId, messageId, memoriaId e decisao são obrigatórios."
        )

    try:
        db = get_db()
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        gemini_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        if not gemini_key:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
                message="Chave Gemini não configurada."
            )

        user_uid = req.auth.uid if req.auth else None
        result = _save_memory_node(
            db=db,
            api_key=gemini_key,
            fato=fato_atualizado,
            categoria=categoria,
            session_id=session_id,
            user_uid=user_uid,
            force_update_id=memoria_id if decisao == 'substituir_pelo_novo' else None,
        ) if decisao == 'substituir_pelo_novo' else {
            "status": "resolved",
            "decision": "kept_existing",
            "memory_id": memoria_id,
        }

        msg_ref = db.collection('sessoes_copiloto').document(session_id).collection('mensagens').document(message_id)
        update_payload = {
            'pendingMemoryConflict.status_ui': 'resolved' if decisao == 'substituir_pelo_novo' else 'kept',
            'pendingMemoryConflict.decisao_final': decisao,
            'pendingMemoryConflict.resolvedAt': firestore.SERVER_TIMESTAMP,
        }
        if decisao == 'substituir_pelo_novo':
            update_payload['pendingMemoryConflict.proposed_text'] = fato_atualizado
        msg_ref.update(update_payload)

        db.collection('sessoes_copiloto').document(session_id).set({
            'pendingMemoryConflict': firestore.DELETE_FIELD,
            'lastMemoryConflictResolutionAt': firestore.SERVER_TIMESTAMP,
        }, merge=True)

        return {
            "status": result.get("status", "resolved"),
            "decision": decisao,
            "memoryId": memoria_id,
        }
    except https_fn.HttpsError:
        raise
    except Exception as e:
        print(f"Erro em confirmarConflitoMemoria: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )


def buscar_procedimento_internal(query_text: str, area_tematica: str = None):
    # Wrapper interno para chamar a lógica de buscar_procedimento sem o overhead do Callable HTTPS
    try:
        db = get_db()
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

        from knowledge_graph import _get_embedding, _cosine_similarity

        # Sanitização de input
        q_text = (query_text or "").strip()
        if not q_text:
            q_text = "procedimentos operacionais"

        # Short-query fast-path: skip embedding + scan for 1-word queries
        _SW = {"de", "a", "o", "que", "e", "do", "da", "em", "um", "uma", "os", "as",
               "no", "na", "com", "por", "para", "dos", "das"}
        _q_meaningful = [w for w in q_text.lower().split() if w not in _SW and len(w) > 2]
        if len(_q_meaningful) < 2:
            return {"context": f"Nenhum registro encontrado para '{q_text}'.", "resultados": []}

        from google.cloud.firestore_v1.vector import Vector
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
        from google.cloud.firestore_v1.base_query import FieldFilter

        query_embedding = _get_embedding(q_text, api_key)
        query_vector = list(map(float, query_embedding))

        # Otimização: Uso de Vector Search Nativo do Firestore (find_nearest)
        # Substitui a varredura manual de 200 documentos por filtragem no banco.
        collection_ref = db.collection("knowledge_nodes")
        vector_query = collection_ref
        if area_tematica:
            vector_query = vector_query.where(filter=FieldFilter("area_tematica", "==", area_tematica))
        
        vector_query = vector_query.find_nearest(
            vector_field="embedding",
            query_vector=Vector(query_vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=5
        )

        nodes_raw = []
        for ndoc in vector_query.stream():
            nd = ndoc.to_dict() or {}
            nodes_raw.append({
                "titulo": nd.get("titulo"),
                "resumo": nd.get("resumo"),
                "area_tematica": nd.get("area_tematica"),
                "score": nd.get("__vector_distance__", 0.0) # find_nearest retorna distância
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

        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
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
    from google import genai

    _db = get_db()
    _gemini_key = get_gemini_api_key()
    _evo_client = genai.Client(api_key=_gemini_key)

    # Recupera chave Tavily para consenso web
    _tavily_key = ''
    try:
        _keys_doc = __cached_doc_get(db, 'system', 'api_keys')
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


# ─── Salvar Relatório no Google Drive ────────────────────────────────────────

@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.MB_512,
    timeout_sec=120
)
def salvarRelatorioNoDrive(req: https_fn.CallableRequest):
    """
    Converte um relatório Markdown para HTML e faz upload no Google Drive
    como Google Doc editável nativo.
    """
    data = req.data or {}
    relatorio_id = data.get('relatorioId')

    if not relatorio_id:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="relatorioId é obrigatório."
        )

    try:
        db = get_db()

        # 1. Busca o relatório no Firestore
        rel_doc = db.collection('relatorios').document(relatorio_id).get()
        if not rel_doc.exists:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND,
                message=f"Relatório '{relatorio_id}' não encontrado."
            )

        rel = rel_doc.to_dict()
        titulo = rel.get('titulo', 'Relatório Hermes')
        markdown_text = rel.get('markdown', '')

        # 2. Converte Markdown → HTML (conversor inline sem dependências externas)
        def _md_to_html(md: str) -> str:
            lines = md.split('\n')
            html = []
            in_ul = False
            in_table = False
            table_header_parsed = False

            def flush_lists():
                nonlocal in_ul
                if in_ul:
                    html.append('</ul>')
                    in_ul = False

            def flush_table():
                nonlocal in_table
                if in_table:
                    html.append('</table>')
                    in_table = False

            for line in lines:
                s = line.strip()
                
                # TABLE DETECTION
                if (s.startswith('|') or (in_table and s.count('|') >= 1)) and s.endswith('|'):
                    flush_lists()
                    if not in_table:
                        html.append('<table border="1" style="border-collapse: collapse; width: 100%; margin-bottom: 20px;">')
                        in_table = True
                        table_header_parsed = False
                    
                    if re.match(r'^\|[\s:-|]+\|$', s):
                        table_header_parsed = True
                        continue
                    
                    # Basic cell extraction
                    cells = [c.strip() for c in line.strip('|').split('|')]
                    tag = 'th' if not table_header_parsed else 'td'
                    html.append('  <tr>')
                    for cell in cells:
                        # Inline formatting for cells
                        c_html = cell
                        c_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', c_html)
                        c_html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', c_html)
                        c_html = re.sub(r'`(.+?)`', r'<code>\1</code>', c_html)
                        html.append(f'    <{tag} style="padding: 10px; border: 1px solid #ccc; text-align: left;">{c_html}</{tag}>')
                    html.append('  </tr>')
                    continue
                else:
                    flush_table()

                s_orig = line.rstrip()
                if not s_orig.strip():
                    flush_lists()
                    html.append('<br/>')
                    continue

                if s_orig.startswith('### '):
                    flush_lists()
                    html.append(f'<h3>{s_orig[4:]}</h3>')
                elif s_orig.startswith('## '):
                    flush_lists()
                    html.append(f'<h2>{s_orig[3:]}</h2>')
                elif s_orig.startswith('# '):
                    flush_lists()
                    html.append(f'<h1>{s_orig[2:]}</h1>')
                elif s_orig == '---':
                    flush_lists()
                    html.append('<hr/>')
                elif s_orig.startswith('- ') or s_orig.startswith('* '):
                    if not in_ul:
                        html.append('<ul>')
                        in_ul = True
                    # Inline formatting for list items
                    li_text = s_orig[2:]
                    li_text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', li_text)
                    li_text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', li_text)
                    html.append(f'  <li>{li_text}</li>')
                else:
                    flush_lists()
                    # Regular paragraph with inline formatting
                    p_text = s_orig
                    p_text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', p_text)
                    p_text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', p_text)
                    p_text = re.sub(r'`(.+?)`', r'<code>\1</code>', p_text)
                    html.append(f'<p>{p_text}</p>')

            flush_lists()
            flush_table()

            body = '\n'.join(html)
            return f'<html><head><meta charset="utf-8"/></head><body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">{body}</body></html>'

        html_content = _md_to_html(markdown_text)

        # 3. Upload para o Drive como Google Doc nativo
        drive_service = get_drive_service()
        from googleapiclient.http import MediaInMemoryUpload

        media = MediaInMemoryUpload(
            html_content.encode('utf-8'),
            mimetype='text/html',
            resumable=False
        )
        uploaded = drive_service.files().create(
            body={'name': titulo, 'mimeType': 'application/vnd.google-apps.document'},
            media_body=media,
            fields='id,webViewLink'
        ).execute()

        drive_file_id = uploaded.get('id')
        drive_url = uploaded.get('webViewLink')

        # 4. Atualiza Firestore com dados do Drive
        db.collection('relatorios').document(relatorio_id).update({
            'driveFileId': drive_file_id,
            'driveUrl': drive_url
        })

        print(f"[Relatorio] '{titulo}' salvo no Drive — fileId: {drive_file_id}")
        return {"driveFileId": drive_file_id, "driveUrl": drive_url}

    except https_fn.HttpsError:
        raise
    except Exception as e:
        import traceback
        print(f"[Relatorio] Erro ao salvar no Drive: {e}\n{traceback.format_exc()}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )

# ==============================================================================
# IMPORTAÇÃO DO MÓDULO DE SLIDES ORCHESTRATOR
# ==============================================================================
from slides_orchestrator import (
    iniciarJobSlides,
    cancelSlideJob,
    slideStrategistWorker,
    slideExecutorWorker,
    slideFinalizeWorker
)


# ─────────────────────────────────────────────────────────────────────────────
# DEEP RESEARCH MAX (MVP) - Callables
# ─────────────────────────────────────────────────────────────────────────────

@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.MB_256,
    timeout_sec=30
)
def startDeepResearch(req: https_fn.CallableRequest):
    """
    Inicia uma pesquisa profunda.
    Valida dados, injeta serverTimestamp e cria o doc em deep_research_tasks.
    """
    try:
        uid = req.auth.uid if req.auth else None
        if not uid:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Usuário não autenticado."
            )

        data = req.data or {}
        topic = (data.get('topic') or '').strip()

        if not topic:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Topic is required."
            )

        db = get_db()
        requester_email = (
            ((req.auth.token or {}).get('email') if req.auth else None)
            or data.get('requester_email')
            or 'unknown'
        )
        telegram_chat_id = _resolve_telegram_chat_id_for_uid(db, uid)
        task_ref = db.collection('deep_research_tasks').document()
        task_ref.set({
            'status': 'PENDING',
            'topic': topic,
            'created_by_uid': uid,
            'requester_email': requester_email,
            'telegram_chat_id': telegram_chat_id,
            'created_at': firestore.SERVER_TIMESTAMP
        })

        return {"taskId": task_ref.id, "status": "PENDING"}
    except Exception as e:
        if isinstance(e, https_fn.HttpsError):
            raise e
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )

@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.MB_256,
    timeout_sec=30
)
def cancelDeepResearch(req: https_fn.CallableRequest):
    """
    Cancela uma pesquisa profunda, atualizando o status do doc.
    """
    try:
        uid = req.auth.uid if req.auth else None
        if not uid:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Usuário não autenticado."
            )

        data = req.data or {}
        task_id = data.get('taskId')

        if not task_id:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Task ID is required."
            )

        db = get_db()
        task_ref = db.collection('deep_research_tasks').document(task_id)

        doc = task_ref.get()
        if not doc.exists:
             raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND,
                message="Task not found."
            )

        task_data = doc.to_dict() or {}
        owner_uid = task_data.get('created_by_uid')
        if owner_uid and owner_uid != uid:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
                message="Você não tem permissão para cancelar esta pesquisa."
            )

        task_ref.update({
            'status': 'CANCELLED',
            'cancelled_at': firestore.SERVER_TIMESTAMP
        })

        return {"taskId": task_id, "status": "CANCELLED"}
    except Exception as e:
        if isinstance(e, https_fn.HttpsError):
            raise e
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )


# ─────────────────────────────────────────────────────────────────────────────
# DEEP RESEARCH MAX (MVP) - Worker Assíncrono e Resiliência
# ─────────────────────────────────────────────────────────────────────────────
@firestore_fn.on_document_created(
    document="deep_research_tasks/{taskId}",
    memory=options.MemoryOption.GB_2,
    timeout_sec=540 # limite de 9 minutos para gatilhos Firestore
)
def deep_research_worker(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]):
    """
    Worker Assíncrono que processa a pesquisa, chamando iterativamente a API do Gemini.
    """
    if not event.data:
        return

    doc_data = event.data.to_dict() or {}
    task_id = event.params.get('taskId')
    topic = doc_data.get('topic', 'Tema Desconhecido')
    requester_email = doc_data.get('requester_email', 'unknown')
    telegram_chat_id = doc_data.get('telegram_chat_id', None)

    db = get_db()
    task_ref = db.collection('deep_research_tasks').document(task_id)

    import time
    from google import genai
    from google.genai import types
    import traceback
    import requests

    # Mantém margem abaixo do limite real de 540s do trigger Firestore.
    MAX_EXECUTION_TIME = 480
    start_time = time.time()

    def check_cancelled():
        doc = task_ref.get()
        if doc.exists and doc.to_dict().get('status') == 'CANCELLED':
            return True
        return False

    def send_telegram_notification(msg: str):
        if not telegram_chat_id:
             print("[DeepResearch] No telegram_chat_id provided, skipping notification.")
             return
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        bot_token = keys_doc.to_dict().get('telegram_bot_token') if keys_doc.exists else None
        bot_token = bot_token or os.environ.get('TELEGRAM_BOT_TOKEN')
        if not bot_token:
             print("[DeepResearch] No TELEGRAM_BOT_TOKEN found in system config or env.")
             return

        try:
             url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
             requests.post(url, json={"chat_id": telegram_chat_id, "text": msg}, timeout=10)
        except Exception as te:
             print(f"[DeepResearch] Telegram notification failed: {te}")


    try:
        if check_cancelled():
            print("[DeepResearch] Pesquisa cancelada antes do início do processamento.")
            return

        task_ref.update({
            'status': 'RUNNING',
            'started_at': firestore.SERVER_TIMESTAMP
        })

        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        if not api_key:
            api_key = os.environ.get("GEMINI_API_KEY")

        if not api_key:
            raise Exception("Chave de API do Gemini não configurada.")

        client = genai.Client(api_key=api_key)
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        grounded_config = types.GenerateContentConfig(
            temperature=0.7,
            tools=[grounding_tool],
        )

        # Iterative Loop Control
        DEPTH_CAP = 3
        accumulated_context = ""
        last_response = ""

        for i in range(DEPTH_CAP):
            # Check Timeout
            if time.time() - start_time > MAX_EXECUTION_TIME:
                 raise Exception("Software Timeout (~8 min) excedido.")

            # Check Cancelled
            if check_cancelled():
                 print("[DeepResearch] Pesquisa cancelada pelo usuário.")
                 return

            prompt = f"""Você é o agente Hermes focado em Pesquisa Profunda com consulta à web.
Pesquise sobre: "{topic}".
Iteração {i+1} de {DEPTH_CAP}.

Requisitos:
- Use a Pesquisa Google quando ela ajudar a confirmar fatos, datas, normas, pessoas, empresas ou eventos recentes.
- Destaque incertezas e conflitos entre fontes.
- Inclua links/fontes citadas no texto sempre que a ferramenta retornar evidências.
"""
            if accumulated_context:
                prompt += f"\n\nBaseando-se no que já foi levantado:\n{accumulated_context[:3000]}\n\nExpanda a pesquisa com novos fatos, aprofunde as nuances."

            response = client.models.generate_content(
                model='gemini-3.1-pro-preview',
                contents=prompt,
                config=grounded_config,
            )
            last_response = response.text
            accumulated_context += f"\n\n---\n\n{response.text}"


        # Final Format HTML
        if check_cancelled(): return

        html_prompt = "Você é o agente Hermes. Formate a pesquisa final sobre o tópico a seguir em HTML limpo, profissional, sem markdown backticks (`html `), pronto para renderização ou conversão para PDF. Mantenha os detalhes valiosos, preserve links/fontes citadas e inclua um pequeno resumo executivo (1 parágrafo) no início."
        html_prompt += f"\n\nConteúdo Final Pesquisado:\n{accumulated_context}"

        final_html_response = client.models.generate_content(
                model='gemini-3.1-pro-preview',
                contents=html_prompt,
                config=types.GenerateContentConfig(temperature=0.3),
        )

        final_html = final_html_response.text.strip()
        if final_html.startswith("```html"):
             final_html = final_html[7:]
        if final_html.endswith("```"):
             final_html = final_html[:-3]

        resumo_executivo = last_response[:200] + "..." # Fallback extract

        # Generate PDF (Call Node.js Endpoint)
        if check_cancelled(): return

        puppeteer_secret = os.environ.get('PUPPETEER_INTERNAL_SECRET')
        project_id = (
            os.environ.get('GCLOUD_PROJECT')
            or os.environ.get('GCP_PROJECT')
            or os.environ.get('GOOGLE_CLOUD_PROJECT')
            or 'gestao-hermes'
        )

        # Emulando chamada local para o microserviço HTTP.
        # Num ambiente produtivo Cloud Run, usaríamos a URL nativa do Cloud Functions (process.env.PUPPETEER_URL).
        # Assumindo aqui uma chamada REST base.
        pdf_buffer = b''
        pdf_status = 'skipped_missing_secret'
        if not puppeteer_secret:
            print("[DeepResearch] PUPPETEER_INTERNAL_SECRET ausente; pulando PDF e salvando HTML.")
        else:
            try:
                # We assume node endpoint is deployed and reachable.
                # Se a URL não estiver definida (ex: local), vamos fazer o mock ou erro controlado.
                node_url = os.environ.get('PUPPETEER_SERVICE_URL', f'https://us-central1-{project_id}.cloudfunctions.net/generatePdfFromHtml')
                pdf_res = requests.post(
                    node_url,
                    json={'html': final_html},
                    headers={'Authorization': f'Bearer {puppeteer_secret}'},
                    timeout=60
                )
                if pdf_res.status_code == 200:
                    pdf_buffer = pdf_res.content
                    pdf_status = 'generated'
                else:
                    pdf_status = f'http_{pdf_res.status_code}'
                    print(f"[DeepResearch] Fallback: falha ao gerar PDF, HTTP {pdf_res.status_code}")
            except Exception as pdf_err:
                 pdf_status = 'unreachable'
                 print(f"[DeepResearch] Puppeteer Node unreachable: {pdf_err}")


        # Upload to Drive
        if check_cancelled(): return

        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        import io
        import uuid

        creds = get_google_creds(scopes=['https://www.googleapis.com/auth/drive'])
        drive_service = build('drive', 'v3', credentials=creds)

        # Encontra pasta
        folder_id = None
        try:
             config_doc = db.collection('configuracoes').document('geral').get()
             if config_doc.exists: folder_id = config_doc.to_dict().get('googleDriveFolderId')
        except: pass

        pdf_link = "N/A"
        if pdf_buffer:
             file_metadata = {'name': f'DeepResearch_{uuid.uuid4().hex[:8]}.pdf'}
             if folder_id: file_metadata['parents'] = [folder_id]
             media = MediaIoBaseUpload(io.BytesIO(pdf_buffer), mimetype='application/pdf', resumable=True)
             uploaded_pdf = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
             pdf_link = uploaded_pdf.get('webViewLink')

        html_metadata = {'name': f'DeepResearch_{uuid.uuid4().hex[:8]}.html'}
        if folder_id: html_metadata['parents'] = [folder_id]
        media_html = MediaIoBaseUpload(io.BytesIO(final_html.encode('utf-8')), mimetype='text/html', resumable=True)
        uploaded_html = drive_service.files().create(body=html_metadata, media_body=media_html, fields='id, webViewLink').execute()
        html_link = uploaded_html.get('webViewLink')

        clean_text = re.sub(r"<[^>]+>", " ", final_html)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        tags = ["deep_research", "pesquisa_profunda"]
        try:
            emb = get_embedding(
                f"Deep Research: {topic}\n\nResumo: {resumo_executivo}\n\n{clean_text[:7000]}",
                api_key=api_key,
            )
        except Exception as emb_err:
            print(f"[DeepResearch] Falha ao gerar embedding do resultado: {emb_err}")
            emb = []

        # Acervo Global (Gravação Enxuta)
        legacy_ref = db.collection('conhecimento_mestre').document()
        legacy_ref.set({
             'titulo': f"Deep Research: {topic}",
             'data_criacao': firestore.SERVER_TIMESTAMP,
             'solicitante': requester_email,
             'resumo': resumo_executivo,
             'link_pdf': pdf_link,
             'link_html': html_link,
             'origem': 'deep_research_max'
        })

        acervo_ref = db.collection('acervo_global').document()
        acervo_ref.set({
             'nome': f"Deep Research: {topic}",
             'titulo': f"Deep Research: {topic}",
             'url': html_link,
             'link_html': html_link,
             'link_pdf': pdf_link,
             'tipo_mime': 'text/html',
             'origem': 'deep_research_max',
             'status_indexacao': 'concluido',
             'resumo_semantico': resumo_executivo,
             'tags': tags,
             'embedding': emb,
             'texto_bruto': clean_text[:60000],
             'solicitante': requester_email,
             'data_criacao': firestore.SERVER_TIMESTAMP,
             'indexed_at': firestore.SERVER_TIMESTAMP,
        })

        if emb:
            db.collection('indice_artefatos').document().set({
                'nome': f"Deep Research: {topic}",
                'url': html_link,
                'tipo_mime': 'text/html',
                'resumo_semantico': resumo_executivo,
                'embedding': emb,
                'tags': tags,
                'origem': 'deep_research_max',
                'acervo_id': acervo_ref.id,
                'texto_bruto': clean_text[:60000],
                'indexed_at': firestore.SERVER_TIMESTAMP,
            })

        # Success Status
        task_ref.update({
            'status': 'COMPLETED',
            'completed_at': firestore.SERVER_TIMESTAMP,
            'result_links': [pdf_link, html_link],
            'html_link': html_link,
            'pdf_link': pdf_link,
            'pdf_status': pdf_status,
            'acervo_id': acervo_ref.id,
            'legacy_kg_id': legacy_ref.id,
        })

        send_telegram_notification(f"✅ Pesquisa concluída: {topic}\nResumo: {resumo_executivo[:100]}...\nAcesse HTML: {html_link}")

    except Exception as e:
        error_msg = str(e)
        print(f"[DeepResearch] Falha: {error_msg}\n{traceback.format_exc()}")
        if check_cancelled(): return # Avoid overwriting Cancel status

        task_ref.update({
            'status': 'FAILED',
            'error': error_msg,
            'failed_at': firestore.SERVER_TIMESTAMP
        })

        send_telegram_notification(f"❌ A pesquisa profunda sobre '{topic}' falhou ou excedeu o limite de tempo.\nErro: {error_msg[:100]}")

@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.MB_512,
    timeout_sec=30
)
def analisarInsightProativo(req: https_fn.CallableRequest):
    """
    Analisa o contexto de uma tarefa e retorna um insight proativo (se relevante).
    Chamado com debounce após mudanças no diário ou plano de ação.
    Retorna: { nivel: 1|2|null, texto: str|null, alvo: "diario"|"plano"|null, planoProposto: list|null }
    """
    from google import genai as _genai
    import json as _json

    data = req.data or {}
    task_id = (data.get('taskId') or '').strip()
    titulo = (data.get('titulo') or '').strip()
    status = (data.get('status') or '').strip()
    data_limite = (data.get('dataLimite') or '').strip()
    prazo_final = (data.get('prazoFinal') or '').strip()
    plano_acao = data.get('planoAcao') or []
    acompanhamento_recente = data.get('acompanhamentoRecente') or []

    if not task_id:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="taskId é obrigatório."
        )

    try:
        db = get_db()
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        gemini_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

        if not gemini_key:
            return {"nivel": None, "texto": None, "alvo": None, "planoProposto": None}

        client = _genai.Client(api_key=gemini_key)

        plano_txt = '\n'.join([
            f"{i+1}. [{'X' if item.get('completed') else ' '}] {item.get('text', '')}"
            for i, item in enumerate(plano_acao)
        ]) or 'Nenhum passo definido.'

        diario_txt = '\n'.join([
            f"[{entry.get('data', '')}] {entry.get('nota', '')}"
            for entry in acompanhamento_recente[-10:]
        ]) or 'Nenhum registro.'

        prompt = f"""Você é um analista de produtividade. Analise o estado atual desta ação e determine se há um insight genuinamente útil.

CONTEXTO:
Título: {titulo}
Status: {status}
Prazo Final: {prazo_final or 'Não definido'}
Data de Execução: {data_limite or 'Não definida'}
REVISÃO DE DATAS: O Hermes entende que 'Data de Execução' é apenas planejamento, não o prazo final. Ignore contradições de datas entre execução e diário.

PLANO DE AÇÃO:
{plano_txt}

DIÁRIO (entradas recentes):
{diario_txt}

CLASSIFICAÇÃO:
- NIVEL_1 (Crítico): Erro lógico real (ex: planejar algo para o passado ou pós-conclusão), gargalo crítico esquecido.
- NIVEL_2 (Otimização): Sugestão de melhoria ou passo faltante.
- NIVEL_3 (Ideia Criativa): Conexões estratégicas ou ideias laterais.
- SEM_INSIGHT: situação adequada.

REGRAS ADICIONAIS:
- NUNCA critique a "Data de Execução" se ela for antes do evento mencionado (isso é ANTECIPAÇÃO).
- Só critique a "Data de Execução" se ela for DEPOIS do "Prazo Final" (se existir).
- Seja conciso e evite ser óbvio.

REGRAS:
- Só retorne insight se for genuinamente valioso. Evite insights genéricos ou óbvios.
- Para alvo "plano", inclua plano_proposto com todos os itens revisados (array de objetos com "id", "text", "completed").
- Para alvo "acoes", inclua acoes_propostas (array de objetos com "titulo", "descricao", "tags").
- Use IDs de 8 chars para itens novos no plano. Preserve id e completed dos itens existentes quando mantidos.
- Se o alvo não for "plano", plano_proposto deve ser null. Se não houver novas ações, acoes_propostas deve ser null.

RESPONDA APENAS COM JSON VÁLIDO (sem markdown):
{{"nivel": 1|2|3|null, "texto": "...", "alvo": "diario"|"plano"|"acoes"|null, "plano_proposto": [...]|null, "acoes_propostas": [...]|null}}

Se SEM_INSIGHT: {{"nivel": null, "texto": null, "alvo": null, "plano_proposto": null, "acoes_propostas": null}}"""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"temperature": 0.3, "max_output_tokens": 1024}
        )

        result_text = (response.text or '').strip()
        if result_text.startswith('```'):
            lines = result_text.split('\n')
            lines = [l for l in lines if not l.startswith('```')]
            result_text = '\n'.join(lines).strip()

        parsed = _json.loads(result_text)
        nivel = parsed.get('nivel')
        texto = parsed.get('texto')
        alvo = parsed.get('alvo')
        plano_proposto = parsed.get('plano_proposto')
        acoes_propostas = parsed.get('acoes_propostas')

        if nivel not in (1, 2, 3, None):
            nivel = None
        if alvo not in ('diario', 'plano', 'acoes', None):
            alvo = None

        return {
            "nivel": nivel,
            "texto": texto,
            "alvo": alvo,
            "planoProposto": plano_proposto if alvo == 'plano' and isinstance(plano_proposto, list) else None,
            "acoesPropostas": acoes_propostas if alvo == 'acoes' and isinstance(acoes_propostas, list) else None
        }

    except Exception as e:
        print(f"[analisarInsightProativo] Erro: {e}")
        return {"nivel": None, "texto": None, "alvo": None, "planoProposto": None}



def calculadora(expressao: str) -> str:
    """Calculadora dedicada para calculos matematicos ad-hoc ou projecoes hipoteticas. Nao utilize para grandes matrizes."""
    import math
    try:
        allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("__")}
        code = compile(expressao, "<string>", "eval")
        for name in code.co_names:
            if name not in allowed_names:
                raise NameError(f"O uso de '{name}' nao e permitido.")
        result = eval(code, {"__builtins__": {}}, allowed_names)
        return str(result)
    except Exception as e:
        return f"Erro de calculo: {e}"

@https_fn.on_call(memory=options.MemoryOption.MB_256)
def classificarAreaTematica(req: https_fn.CallableRequest) -> dict:
    from google import genai
    from google.genai import types
    data = req.data
    titulo = data.get("titulo", "")
    descricao = data.get("descricao", "")
    notas = data.get("notas", "")
    texto = f"Titulo: {titulo}\nDescricao: {descricao}\nNotas: {notas}"
    
    api_key = get_gemini_api_key()
    if not api_key:
        return {"area_tematica": "Nenhuma"}
        
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"Classifique a Area Tematica do seguinte texto como uma de: Saude, Financeira, Nenhuma. Retorne APENAS a palavra correta.\n\nTexto: {texto}",
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=10
            )
        )
        res = (response.text or "Nenhuma").strip().strip('\'"').capitalize()
        if res == "Saude":
            res = "Saúde"
        if res not in ["Saúde", "Financeira", "Nenhuma"]:
            res = "Nenhuma"
            
        return {"area_tematica": res}
    except Exception as e:
        print(f"Erro na classificacao tematica: {e}")
        return {"area_tematica": "Nenhuma"}

# Import daily WIP reset job
from daily_reset_job import daily_wip_reset_and_degradation


@https_fn.on_call(memory=options.MemoryOption.MB_512, timeout_sec=60)
def gerarResumoFinanceiro(req: https_fn.CallableRequest):
    """
    Gera um parágrafo curto de diagnóstico de saúde financeira a partir de um snapshot compacto.
    Projetado para ser chamado apenas quando os dados financeiros mudam (fingerprint diferente).
    """
    from google import genai
    from google.genai import types

    data = req.data or {}
    snapshot = data.get('snapshot')

    if not snapshot or not isinstance(snapshot, dict):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="snapshot é obrigatório."
        )

    api_key = get_gemini_api_key()
    if not api_key:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Chave Gemini não configurada."
        )

    import json
    snapshot_text = json.dumps(snapshot, ensure_ascii=False, indent=2)

    prompt = f"""Você é um consultor financeiro pessoal. Analise o snapshot financeiro abaixo e escreva um diagnóstico de saúde financeira em 3 a 5 frases curtas e diretas em português.

Seja específico com os números. Destaque o ponto mais crítico primeiro. Se há algo positivo notável, mencione. Termine com uma recomendação prática e concreta para o mês atual.

Não use listas, markdown, títulos nem emojis — apenas parágrafos corridos.

SNAPSHOT:
{snapshot_text}"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=300
            )
        )
        summary = (response.text or "").strip()
        return {"summary": summary}
    except Exception as e:
        print(f"Erro ao gerar resumo financeiro: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Erro ao gerar resumo financeiro."
        )
