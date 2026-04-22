import re

with open('functions/main.py', 'r') as f:
    content = f.read()

new_worker = """
# ─────────────────────────────────────────────────────────────────────────────
# DEEP RESEARCH MAX (MVP) - Worker Assíncrono e Resiliência
# ─────────────────────────────────────────────────────────────────────────────
@firestore_fn.on_document_created(
    document="deep_research_tasks/{taskId}",
    memory=options.MemoryOption.GB_2,
    timeout_sec=3600 # 60 minutos
)
def deep_research_worker(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]):
    \"\"\"
    Worker Assíncrono que processa a pesquisa, chamando iterativamente a API do Gemini.
    \"\"\"
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

    # 55 minutos de software timeout em segundos (3300)
    MAX_EXECUTION_TIME = 3300
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
        keys_doc = db.collection('system').document('api_keys').get()
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
        keys_doc = db.collection('system').document('api_keys').get()
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        if not api_key:
            api_key = os.environ.get("GEMINI_API_KEY")

        if not api_key:
            raise Exception("Chave de API do Gemini não configurada.")

        client = genai.Client(api_key=api_key)

        # Iterative Loop Control
        DEPTH_CAP = 3
        accumulated_context = ""
        last_response = ""

        for i in range(DEPTH_CAP):
            # Check Timeout
            if time.time() - start_time > MAX_EXECUTION_TIME:
                 raise Exception("Software Timeout (55 min) excedido.")

            # Check Cancelled
            if check_cancelled():
                 print("[DeepResearch] Pesquisa cancelada pelo usuário.")
                 return

            prompt = f"Você é o agente Hermes focado em Pesquisa Profunda. Pesquise intensamente sobre: '{topic}'. Iteração {i+1} de {DEPTH_CAP}."
            if accumulated_context:
                prompt += f"\\n\\nBaseando-se no que já foi levantado:\\n{accumulated_context[:3000]}\\n\\nExpanda a pesquisa com novos fatos, aprofunde as nuances."

            response = client.models.generate_content(
                model='gemini-3.1-pro-preview',
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.7),
            )
            last_response = response.text
            accumulated_context += f"\\n\\n---\\n\\n{response.text}"


        # Final Format HTML
        if check_cancelled(): return

        html_prompt = "Você é o agente Hermes. Formate a pesquisa final sobre o tópico a seguir em HTML limpo, profissional, sem markdown backticks (`html `), pronto para renderização ou conversão para PDF. Mantenha os detalhes valiosos e inclua um pequeno resumo executivo (1 parágrafo) no início."
        html_prompt += f"\\n\\nConteúdo Final Pesquisado:\\n{accumulated_context}"

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

        puppeteer_secret = os.environ.get('PUPPETEER_INTERNAL_SECRET', 'dummy_secret')
        project_id = os.environ.get('GCP_PROJECT', 'hermes') # Adjust for actual deployment

        # Emulando chamada local para o microserviço HTTP.
        # Num ambiente produtivo Cloud Run, usaríamos a URL nativa do Cloud Functions (process.env.PUPPETEER_URL).
        # Assumindo aqui uma chamada REST base.
        pdf_buffer = b''
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
            else:
                print(f"[DeepResearch] Fallback: falha ao gerar PDF, HTTP {pdf_res.status_code}")
        except Exception as pdf_err:
             print(f"[DeepResearch] Puppeteer Node unreachable: {pdf_err}")


        # Upload to Drive
        if check_cancelled(): return

        from setup_credentials import get_google_auth, get_db
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        import io
        import uuid

        creds = get_google_auth(db)
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

        # Acervo Global (Gravação Enxuta)
        acervo_ref = db.collection('conhecimento_mestre').document()
        acervo_ref.set({
             'titulo': f"Deep Research: {topic}",
             'data_criacao': firestore.firestore.SERVER_TIMESTAMP,
             'solicitante': requester_email,
             'resumo': resumo_executivo,
             'link_pdf': pdf_link,
             'link_html': html_link,
             'origem': 'deep_research_max'
        })

        # Success Status
        task_ref.update({
            'status': 'COMPLETED',
            'completed_at': firestore.firestore.SERVER_TIMESTAMP,
            'result_links': [pdf_link, html_link]
        })

        send_telegram_notification(f"✅ Pesquisa concluída: {topic}\\nResumo: {resumo_executivo[:100]}...\\nAcesse PDF: {pdf_link}")

    except Exception as e:
        error_msg = str(e)
        print(f"[DeepResearch] Falha: {error_msg}\\n{traceback.format_exc()}")
        if check_cancelled(): return # Avoid overwriting Cancel status

        task_ref.update({
            'status': 'FAILED',
            'error': error_msg,
            'failed_at': firestore.firestore.SERVER_TIMESTAMP
        })

        send_telegram_notification(f"❌ A pesquisa profunda sobre '{topic}' falhou ou excedeu o limite de tempo.\\nErro: {error_msg[:100]}")
"""

with open('functions/main.py', 'w') as f:
    f.write(content + "\n" + new_worker)
