
from firebase_functions import firestore_fn, scheduler_fn, options, https_fn, pubsub_fn
from firebase_admin import initialize_app, firestore, messaging

# Inicializa o Firebase Admin apenas uma vez no escopo global
initialize_app()

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
        'https://www.googleapis.com/auth/calendar.readonly',
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
            g_id, title = gt['id'], gt.get('title', '(Sem Título)')
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
                    update_data = {
                        'titulo': title, 'status': status, 'data_atualizacao': g_updated,
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
                    'data_criacao': datetime.now().isoformat(), 'data_atualizacao': g_updated,
                    'categoria': cat, 'contabilizar_meta': meta, 'notas': g_notes,
                    'data_limite': g_due if g_due else '-',
                    'horario_inicio': h_inicio, 'horario_fim': h_fim
                })
                log_to_firestore(sync_ref, logs, f"[+] IMPORTADA: {title}")
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"ERRO PULL: {e}")

from googleapiclient.errors import HttpError

def sync_google_tasks_push(service, sync_ref, logs):
    db = get_db()
    try:
        results = service.tasklists().list().execute()
        tasklist_id = next((item['id'] for item in results.get('items', []) if 'tarefa' in item['title'].lower()), None)
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
            if cat.startswith('SISTEMA:') or cat == 'SISTEMAS': continue

            g_id, title = t.get('google_id'), t.get('titulo')
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
            g_due = f"{t.get('data_limite')}T00:00:00Z" if t.get('data_limite') and t.get('data_limite') != '-' else None
            
            # Se houver horário de início, tentamos enviar no due
            if t.get('horario_inicio') and g_due:
                g_due = f"{t.get('data_limite')}T{t['horario_inicio']}:00Z"

            # Atualiza as notas com o horário para garantir a sincronia
            h_inicio, h_fim = t.get('horario_inicio'), t.get('horario_fim')
            # Se não houver fim mas houver início, assume-se 1h de duração
            if h_inicio and not h_fim:
                try:
                    h, m = map(int, h_inicio.split(':'))
                    h_fim = f"{(h+1)%24:02d}:{m:02d}"
                except: pass
            
            updated_notes = update_notes_with_time(t.get('notas', ''), h_inicio, h_fim)

            if not g_id:
                body = {'title': title, 'notes': updated_notes, 'status': g_status}
                if g_due: body['due'] = g_due
                new_task = service.tasks().insert(tasklist=tasklist_id, body=body).execute()
                doc.reference.update({'google_id': new_task['id'], 'data_atualizacao': new_task.get('updated'), 'notas': updated_notes, 'horario_fim': h_fim if not t.get('horario_fim') else t.get('horario_fim')})
                log_to_firestore(sync_ref, logs, f"[+] ENVIADA: {title}")
            elif g_id in g_tasks_map and t.get('data_atualizacao', '') > g_tasks_map[g_id].get('updated', ''):
                body = {'id': g_id, 'title': title, 'notes': updated_notes, 'status': g_status}
                if g_due: body['due'] = g_due
                try:
                    service.tasks().update(tasklist=tasklist_id, task=g_id, body=body).execute()
                    log_to_firestore(sync_ref, logs, f"[^] ATUALIZADA NO GOOGLE: {title}")
                    if updated_notes != t.get('notas', ''):
                        doc.reference.update({'notas': updated_notes})
                except HttpError as e:
                    if e.resp.status == 404:
                        log_to_firestore(sync_ref, logs, f"[!] Task {g_id} não encontrada no Google - Limpando ID local.")
                        doc.reference.update({'google_id': None})
                    else:
                        raise e
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"ERRO PUSH: {e}")

def sync_google_calendar(service, sync_ref, logs):
    from datetime import datetime, timedelta, timezone
    db = get_db()
    try:
        log_to_firestore(sync_ref, logs, "Sincronizando Google Calendar...", True)
        time_min = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace('+00:00', 'Z')
        time_max = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace('+00:00', 'Z')

        events_result = service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        count = 0
        seen_ids = set()
        for event in events:
            event_id = event['id']
            seen_ids.add(event_id)
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

        # Limpeza de eventos deletados no Google Calendar
        # Buscamos apenas eventos no Firestore que estão dentro do período sincronizado para evitar stream total
        docs = db.collection('google_calendar_events')\
            .where('data_inicio', '>=', time_min)\
            .where('data_inicio', '<=', time_max)\
            .stream()
        deleted_count = 0
        for doc in docs:
            if doc.id not in seen_ids:
                doc.reference.delete()
                deleted_count += 1

        log_to_firestore(sync_ref, logs, f"[CAL] {count} eventos sincronizados. {deleted_count} removidos.")
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

                new_record = {
                    'description': description, 'amount': amount, 'date': iso_date,
                    'google_message_id': msg_id, 'pix_id': pix_id, 'status': 'active'
                }

                if is_income:
                    new_record.update({
                        'day': dt.day, 'month': dt.month - 1, 'year': dt.year,
                        'category': 'Renda Extra', 'isReceived': True
                    })
                    db.collection('finance_income').add(new_record)
                    existing_income.append({'amount': amount, 'date': dt, 'pix_id': pix_id, 'description': description})
                else:
                    sprint = 1 if dt.day < 8 else 2 if dt.day < 15 else 3 if dt.day < 22 else 4
                    new_record.update({
                        'sprint': sprint, 'category': 'Alimentação'
                    })
                    db.collection('finance_transactions').add(new_record)
                    existing_transactions.append({'amount': amount, 'date': dt, 'pix_id': pix_id, 'description': description})
                new_processed_ids.append(msg_id)
                log_to_firestore(sync_ref, logs, f"[PIX] {subject} (R$ {amount:.2f})")

        if new_processed_ids:
            updated_ids = list(set(processed_ids + new_processed_ids))[-200:]
            db.collection('system').document('processed_emails').set({'ids': updated_ids}, merge=True)
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"ERRO PIX: {e}")

def run_full_sync():
    """Executa o processo completo de sincronização"""
    from datetime import datetime
    db = get_db()
    sync_ref = db.collection('system').document('sync')
    logs = [f"Iniciando sincronização ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})..."]
    try:
        ts, gs, cs = get_tasks_service(), get_gmail_service(), get_calendar_service()
        sync_google_tasks_push(ts, sync_ref, logs)
        sync_google_tasks_pull(ts, sync_ref, logs)
        sync_google_calendar(cs, sync_ref, logs)
        sync_pix_emails(gs, sync_ref, logs)
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
    tokens = [doc.id for doc in tokens_docs]
    if not tokens:
        print("Nenhum token FCM encontrado para enviar push.")
        return
    push_message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=message),
        data={
            'id': str(notif.get('id', '')),
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
        return {'fileId': file.get('id'), 'webViewLink': file.get('webViewLink')}
    except Exception as e:
        print(f"Erro no upload para o Drive: {str(e)}")
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INTERNAL, message=str(e))

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
    if not audio_base64:
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message="Áudio não fornecido.")

    temp_filename = None
    try:
        # 1. Decodificar Base64 para arquivo temporário
        audio_data = base64.b64decode(audio_base64)
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as temp_audio:
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
