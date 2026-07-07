import os
import re
import json
import base64
import tempfile
from datetime import datetime

def build_gmail_query(trigger: dict) -> str | None:
    """
    Compila os campos sender, subjectKeywords e bodyKeywords de um email_trigger
    em uma string de busca padrão compatível com a API do Gmail.
    Supports comma or semicolon separated multiple senders.
    """
    parts = []
    
    sender = trigger.get("sender", "").strip()
    if sender:
        senders = [s.strip() for s in re.split(r'[,;]+', sender) if s.strip()]
        if senders:
            if len(senders) == 1:
                parts.append(f"from:{senders[0]}")
            else:
                joined = " OR ".join(senders)
                parts.append(f"from:({joined})")
        
    subject_kws = trigger.get("subjectKeywords", "").strip()
    if subject_kws:
        kws = [k.strip() for k in re.split(r'[,;]+', subject_kws) if k.strip()]
        if kws:
            joined = " OR ".join(f'"{k}"' for k in kws)
            parts.append(f"subject:({joined})")
            
    body_kws = trigger.get("bodyKeywords", "").strip()
    if body_kws:
        kws = [k.strip() for k in re.split(r'[,;]+', body_kws) if k.strip()]
        if kws:
            joined = " OR ".join(f'"{k}"' for k in kws)
            parts.append(f"({joined})")
            
    if parts:
        return " ".join(parts)
    return None

def process_email_triggers(db, service, sync_ref, logs):
    """
    Busca tarefas em status 'stand-by' com gatilhos ativos, consulta o Gmail,
    processa novos emails e atualiza o Firestore e Telegram de acordo.
    """
    from main import (
        _send_telegram_message_raw,
        get_genai_module,
        _cached_doc_get,
        _resolve_telegram_chat_id_for_uid,
        _resolve_default_telegram_chat_id,
        log_to_firestore,
        GEMINI_LIGHT_MODEL
    )
    from gemini_cost_controls import log_gemini_usage

    log_to_firestore(sync_ref, logs, "[GMAIL-TRIGGER] Iniciando verificação de gatilhos para tarefas em stand-by...", True)

    standby_tasks = []
    try:
        # Buscamos tarefas em stand-by
        for doc in db.collection("tarefas").where("status", "==", "stand-by").stream():
            task_data = doc.to_dict()
            task_data["_id"] = doc.id
            trigger = task_data.get("email_trigger", {})
            if trigger and trigger.get("enabled"):
                standby_tasks.append(task_data)
    except Exception as e:
        log_to_firestore(sync_ref, logs, f"[GMAIL-TRIGGER][ERRO] Erro ao carregar tarefas em stand-by: {e}", True)
        return

    if not standby_tasks:
        log_to_firestore(sync_ref, logs, "[GMAIL-TRIGGER] Nenhuma tarefa em stand-by com gatilho ativo encontrada.", True)
        return

    # Verificar se alguma tarefa usará a análise por IA
    needs_ai = any(t.get("email_trigger", {}).get("action_to_take") == "run_ai_analysis" for t in standby_tasks)
    client = None
    if needs_ai:
        keys_doc = _cached_doc_get(db, 'system', 'api_keys')
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        if api_key:
            genai = get_genai_module()
            client = genai.Client(api_key=api_key)
        else:
            log_to_firestore(sync_ref, logs, "[GMAIL-TRIGGER][!] Gemini API Key não configurada. Ações com análise de IA usarão comportamento padrão (apenas mover status).", True)

    for task in standby_tasks:
        task_id = task["_id"]
        trigger = task["email_trigger"]
        action_to_take = trigger.get("action_to_take", "status_to_andamento")
        ai_instructions = trigger.get("ai_instructions", "")
        telegram_alert = trigger.get("telegram_alert", False)
        last_triggered_id = trigger.get("last_triggered_email_id")
        
        query = build_gmail_query(trigger)
        if not query:
            log_to_firestore(sync_ref, logs, f"[GMAIL-TRIGGER][!] Query vazia para a tarefa '{task.get('titulo')}' ({task_id}). Pulando...", True)
            continue

        log_to_firestore(sync_ref, logs, f"[GMAIL-TRIGGER] Checando query '{query}' para a tarefa '{task.get('titulo')}'", True)

        try:
            # Busca o e-mail mais recente correspondente à query
            results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
            messages = results.get('messages', [])
            
            if not messages:
                continue

            msg_info = messages[0]
            msg_id = msg_info['id']

            # Se o e-mail já foi o que ativou o gatilho da última vez, ignora
            if last_triggered_id == msg_id:
                continue

            log_to_firestore(sync_ref, logs, f"[GMAIL-TRIGGER] Novo e-mail ({msg_id}) detectado para a tarefa '{task.get('titulo')}'!", True)

            # Busca detalhes do e-mail
            msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            
            sender = "Desconhecido"
            subject = "Sem Assunto"
            headers = msg.get('payload', {}).get('headers', [])
            for h in headers:
                name_lower = h['name'].lower()
                if name_lower == 'from':
                    sender = h['value']
                elif name_lower == 'subject':
                    subject = h['value']

            snippet = msg.get('snippet', '')

            # Extração de conteúdo
            text_parts = []
            html_parts = []
            attachments = []

            def walk_parts(part):
                mime_type = part.get('mimeType')
                body = part.get('body', {})
                data = body.get('data')
                filename = part.get('filename', '')
                
                if filename and body.get('attachmentId') and mime_type == 'application/pdf':
                    attachments.append({
                        'id': body['attachmentId'],
                        'filename': filename,
                        'size': body.get('size', 0)
                    })
                elif data:
                    if mime_type == 'text/plain':
                        text_parts.append(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', errors='replace'))
                    elif mime_type == 'text/html':
                        html_parts.append(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', errors='replace'))
                
                if 'parts' in part:
                    for subpart in part['parts']:
                        walk_parts(subpart)

            walk_parts(msg.get('payload', {}))

            email_body = ""
            if text_parts:
                email_body = "\n".join(text_parts)
            elif html_parts:
                try:
                    import html2text
                    h = html2text.HTML2Text()
                    h.ignore_links = False
                    h.ignore_images = True
                    h.body_width = 0
                    email_body = "\n".join([h.handle(html) for html in html_parts])
                except Exception:
                    email_body = snippet
            else:
                email_body = snippet

            email_body = "\n".join([line for line in email_body.split("\n") if line.strip()])

            # Processamento de PDFs anexos
            pdf_contents = []
            for att in attachments:
                try:
                    att_obj = service.users().messages().attachments().get(userId='me', messageId=msg_id, id=att['id']).execute()
                    file_data = base64.urlsafe_b64decode(att_obj['data'])
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                        temp_file.write(file_data)
                        temp_path = temp_file.name
                    try:
                        import pdfplumber
                        with pdfplumber.open(temp_path) as pdf:
                            extracted_text = ""
                            for page in pdf.pages[:5]:  # Máximo de 5 páginas
                                text = page.extract_text()
                                if text:
                                    extracted_text += text + "\n"
                            if extracted_text:
                                pdf_contents.append(f"--- Anexo PDF [{att['filename']}] ---\n{extracted_text[:2000]}")
                    finally:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                except Exception as e_pdf:
                    print(f"[GMAIL-TRIGGER] Erro ao ler anexo PDF {att['filename']}: {e_pdf}")

            full_email_context = f"De: {sender}\nAssunto: {subject}\n\nCorpo:\n{email_body}"
            if pdf_contents:
                full_email_context += "\n\n=== ANEXOS EXTRAÍDOS ===\n" + "\n\n".join(pdf_contents)

            # Preparar payload padrão de atualização
            now_iso = datetime.now().isoformat()
            updates = {
                "status": "em andamento",
                "email_trigger.last_triggered_email_id": msg_id,
                "data_atualizacao": now_iso
            }

            # Histórico de Acompanhamento da tarefa
            accompaniment = task.get("acompanhamento", [])
            new_note = f"Gatilho de e-mail disparado.\nDe: {sender}\nAssunto: {subject}\nSnippet: {snippet}"
            accompaniment.append({
                "data": datetime.now().strftime("%Y-%m-%d"),
                "nota": new_note
            })
            updates["acompanhamento"] = accompaniment

            ai_summary_telegram = ""

            # Caso queira rodar Análise de IA
            if action_to_take == "run_ai_analysis" and client:
                prompt = f"""
                Você é o assistente inteligente Hermes.
                Uma tarefa que estava em stand-by foi reativada por um e-mail recebido.
                
                DADOS DA TAREFA:
                - Título: {task.get('titulo')}
                - Descrição: {task.get('descricao', 'Nenhuma')}
                - Notas atuais: {task.get('notas', 'Nenhuma')}
                - Checklist atual: {json.dumps(task.get('plano_acao', []))}
                
                CONTEÚDO DO E-MAIL RECEBIDO:
                {full_email_context}
                
                INSTRUÇÕES DO USUÁRIO PARA EXTRAÇÃO/IA:
                {ai_instructions or "Analise o e-mail e atualize as notas/plano de ação de acordo."}
                
                Gere um JSON com atualizações aplicáveis à tarefa.
                Regras para as notas: incorpore as novas informações (ex: datas, valores, mensagens importantes) às notas existentes de forma estruturada.
                Regras para o plano de ação: retorne a lista de itens de checklist atualizada (marque itens como completos ou adicione novos se necessário). Cada item deve conter 'id', 'text' e 'completed'.
                Regras para o status: escolha o status final da tarefa. Geralmente será 'em andamento', mas você pode sugerir 'concluído' se a resposta do e-mail resolver plenamente a demanda.
                Regras para o resumo do telegram: escreva um resumo de 1 a 3 frases em português descrevendo a novidade do e-mail e a decisão tomada.
                
                Responda APENAS com o JSON no formato:
                {{
                  "notas": "...",
                  "plano_acao": [
                    {{"id": "...", "text": "...", "completed": true}}
                  ],
                  "status": "...",
                  "resumo_telegram": "..."
                }}
                """
                try:
                    response = client.models.generate_content(
                        model=GEMINI_LIGHT_MODEL,
                        contents=prompt
                    )
                    res_text = response.text.strip()
                    if "```json" in res_text:
                        res_text = res_text.split("```json")[-1].split("```")[0].strip()
                    elif "```" in res_text:
                        res_text = res_text.split("```")[-1].split("```")[0].strip()
                    
                    ai_data = json.loads(res_text)
                    log_gemini_usage(response, model=GEMINI_LIGHT_MODEL, feature="gmail_trigger_analysis", db=db)

                    if ai_data.get("notas"):
                        updates["notas"] = ai_data["notas"]
                    if ai_data.get("plano_acao"):
                        updates["plano_acao"] = ai_data["plano_acao"]
                    if ai_data.get("status"):
                        updates["status"] = ai_data["status"]
                    if ai_data.get("resumo_telegram"):
                        ai_summary_telegram = ai_data["resumo_telegram"]

                except Exception as e_ai:
                    log_to_firestore(sync_ref, logs, f"[GMAIL-TRIGGER][!] Erro na análise de IA para a tarefa {task_id}: {e_ai}", True)

            # Atualiza o Firestore
            db.collection("tarefas").document(task_id).update(updates)
            log_to_firestore(sync_ref, logs, f"[GMAIL-TRIGGER] Tarefa '{task.get('titulo')}' atualizada com sucesso para status '{updates['status']}'!", True)

            # Envia alerta no Telegram
            if telegram_alert:
                owner_uid = task.get("userId")
                telegram_chat_id = _resolve_telegram_chat_id_for_uid(db, owner_uid) or _resolve_default_telegram_chat_id(db)
                if telegram_chat_id:
                    msg_text = f"📧 *GATILHO DE E-MAIL DISPARADO*\n\n"
                    msg_text += f"📌 *Tarefa:* {task.get('titulo')}\n"
                    msg_text += f"📬 *Remetente:* {sender}\n"
                    msg_text += f"✉️ *Assunto:* {subject}\n"
                    msg_text += f"⚙️ *Novo Status:* {updates['status']}\n\n"
                    
                    if ai_summary_telegram:
                        msg_text += f"🤖 *Resumo da IA:*\n{ai_summary_telegram}\n\n"
                    else:
                        msg_text += f"📝 *Snippet:* {snippet}\n\n"
                    
                    msg_text += f"A ação saiu de 'stand-by' e foi movida para '{updates['status']}'."
                    _send_telegram_message_raw(db, telegram_chat_id, msg_text)
                    log_to_firestore(sync_ref, logs, f"[GMAIL-TRIGGER] Alerta enviado ao Telegram (chat_id: {telegram_chat_id}).", True)

        except Exception as e_task:
            log_to_firestore(sync_ref, logs, f"[GMAIL-TRIGGER][ERRO] Falha ao processar gatilho da tarefa {task_id}: {e_task}", True)

    log_to_firestore(sync_ref, logs, "[GMAIL-TRIGGER] Fim da verificação de gatilhos de e-mail.", True)
