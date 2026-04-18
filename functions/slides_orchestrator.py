from firebase_functions import https_fn, pubsub_fn, options
from firebase_admin import firestore
import json
import uuid
import os
import tempfile
import base64
import sys
from google import genai
from main import get_db, emit_notification_backend

# Import ppt-master tools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ppt_master'))
from finalize_svg import crop_images_in_svg, embed_icons_in_file, embed_images_in_svg, fix_image_aspect_in_svg
import svg_to_pptx.main as pptx_exporter

@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
)
def iniciarJobSlides(req: https_fn.CallableRequest):
    """
    Inicia o job assíncrono de geração de slides.
    """
    uid = req.auth.uid if req.auth else None
    if not uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Usuário não autenticado."
        )

    # Pegamos o email pelo Auth token
    user_email = req.auth.token.get('email')

    data = req.data or {}
    rascunho = data.get('rascunho')
    slides_data = data.get('slides')

    if not rascunho or not slides_data:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Dados insuficientes."
        )

    db = get_db()

    # Criar registro de job
    job_id = f"slides_job_{uuid.uuid4().hex}"

    job_data = {
        "userId": uid,
        "userEmail": user_email,
        "status": "processing",
        "tema": rascunho,
        "totalSlides": len(slides_data),
        "slides_status": [{"index": i, "status": "pending"} for i in range(len(slides_data))],
        "timestamp": firestore.SERVER_TIMESTAMP,
        "slides_data": slides_data
    }

    db.collection('slide_jobs').document(job_id).set(job_data)

    # Disparar tópico Pub/Sub (Strategist)
    from google.cloud import pubsub_v1
    publisher = pubsub_v1.PublisherClient()
    project_id = os.environ.get("GCLOUD_PROJECT", "gestao-hermes")
    topic_path = publisher.topic_path(project_id, "slide-strategist")

    message_json = json.dumps({"job_id": job_id})
    publisher.publish(topic_path, message_json.encode("utf-8"))

    return {"jobId": job_id, "status": "started"}

@pubsub_fn.on_message_published(topic="slide-strategist")
def slideStrategistWorker(event: pubsub_fn.CloudEvent[pubsub_fn.MessagePublishedData]):
    """
    Agente Strategist: define o design spec e enfileira os workers.
    """
    message_data = event.data.message.json
    job_id = message_data.get("job_id")

    if not job_id:
        print("No job_id provided.")
        return

    db = get_db()
    job_ref = db.collection('slide_jobs').document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists:
        print(f"Job {job_id} not found.")
        return

    job = job_doc.to_dict()
    slides_data = job.get("slides_data", [])

    # (Em uma versão avançada, o LLM definiria o design system aqui.
    # Por ora, passamos as instruções padrão e disparamos um worker por slide)

    from google.cloud import pubsub_v1
    publisher = pubsub_v1.PublisherClient()
    project_id = os.environ.get("GCLOUD_PROJECT", "gestao-hermes")
    executor_topic_path = publisher.topic_path(project_id, "slide-executor")

    for i, slide in enumerate(slides_data):
        msg = json.dumps({
            "job_id": job_id,
            "slide_index": i,
            "slide_data": slide
        })
        publisher.publish(executor_topic_path, msg.encode("utf-8"))

    print(f"Strategist finished for {job_id}, queued {len(slides_data)} slides.")


@pubsub_fn.on_message_published(
    topic="slide-executor",
    max_instances=5 # Limite para evitar 429 da API
)
def slideExecutorWorker(event: pubsub_fn.CloudEvent[pubsub_fn.MessagePublishedData]):
    """
    Agente Executor: gera o SVG para a página via Gemini.
    """
    message_data = event.data.message.json
    job_id = message_data.get("job_id")
    slide_index = message_data.get("slide_index")
    slide_data = message_data.get("slide_data")

    if not job_id or slide_index is None:
        return

    db = get_db()
    job_ref = db.collection('slide_jobs').document(job_id)

    try:
        # Atualiza status individual para processing
        def update_status(status_str):
            @firestore.transactional
            def _txn(transaction, ref):
                snap = ref.get(transaction=transaction)
                if not snap.exists: return
                statuses = snap.get("slides_status")
                statuses[slide_index]["status"] = status_str
                transaction.update(ref, {"slides_status": statuses})
            _txn(db.transaction(), job_ref)

        update_status("processing")

        keys_doc = db.collection('system').document('api_keys').get()
        gemini_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

        if not gemini_key:
            raise Exception("Chave Gemini não configurada.")

        client = genai.Client(api_key=gemini_key)

        # Gerar SVG (Simplificado - o motor real faria o mapping do template)
        prompt = f"""
        Gere um código SVG válido para um slide de apresentação (1920x1080).
        Layout: {slide_data.get('layout', 'titulo_e_conteudo')}
        Título: {slide_data.get('titulo', '')}
        Tópicos: {json.dumps(slide_data.get('topicos', []))}

        Retorne APENAS o código SVG bruto. Não inclua blocos markdown como ```xml ou ```svg.
        """

        response = client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=prompt
        )

        svg_content = response.text.replace("```svg", "").replace("```xml", "").replace("```", "").strip()

        # Salvar SVG no Storage
        from firebase_admin import storage
        bucket = storage.bucket()
        blob_path = f"slides/{job_id}/slide_{slide_index:03d}.svg"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(svg_content, content_type="image/svg+xml")

        update_status("completed")

        # Verificar se é o último slide
        job_doc = job_ref.get()
        statuses = job_doc.get("slides_status")
        all_completed = all(s["status"] == "completed" for s in statuses)
        has_error = any(s["status"] == "error" for s in statuses)

        if all_completed or (all_completed and has_error):
            from google.cloud import pubsub_v1
            publisher = pubsub_v1.PublisherClient()
            project_id = os.environ.get("GCLOUD_PROJECT", "gestao-hermes")
            finalizer_topic_path = publisher.topic_path(project_id, "slide-finalizer")
            msg = json.dumps({"job_id": job_id})
            publisher.publish(finalizer_topic_path, msg.encode("utf-8"))

    except Exception as e:
        print(f"Error in executor for slide {slide_index}: {e}")
        @firestore.transactional
        def _err_txn(transaction, ref):
            snap = ref.get(transaction=transaction)
            if not snap.exists: return
            statuses = snap.get("slides_status")
            statuses[slide_index]["status"] = "error"
            transaction.update(ref, {"slides_status": statuses})
        _err_txn(db.transaction(), job_ref)

@pubsub_fn.on_message_published(
    topic="slide-finalizer",
    memory=options.MemoryOption.GB_2,
    timeout_sec=3600
)
def slideFinalizeWorker(event: pubsub_fn.CloudEvent[pubsub_fn.MessagePublishedData]):
    """
    Post-processing, SVG to PPTX, upload to Drive, alter ACL, and notify.
    """
    message_data = event.data.message.json
    job_id = message_data.get("job_id")

    if not job_id: return

    db = get_db()
    job_ref = db.collection('slide_jobs').document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists: return

    job = job_doc.to_dict()
    user_email = job.get("userEmail")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Download SVGs
        from firebase_admin import storage
        bucket = storage.bucket()
        blobs = bucket.list_blobs(prefix=f"slides/{job_id}/")

        svg_output_dir = os.path.join(tmpdir, "svg_output")
        svg_final_dir = os.path.join(tmpdir, "svg_final")
        os.makedirs(svg_output_dir, exist_ok=True)
        os.makedirs(svg_final_dir, exist_ok=True)

        for blob in blobs:
            file_path = os.path.join(svg_output_dir, os.path.basename(blob.name))
            blob.download_to_filename(file_path)

        # 2. Finalize SVGs (usando os scripts do PPT Master na íntegra)
        for svg_file in os.listdir(svg_output_dir):
            if not svg_file.endswith(".svg"): continue
            src_path = os.path.join(svg_output_dir, svg_file)
            dest_path = os.path.join(svg_final_dir, svg_file)

            with open(src_path, "r", encoding="utf-8") as f:
                svg_content = f.read()

            # Executar pipeline de finalização:
            svg_content = embed_icons_in_file(svg_content)
            svg_content = crop_images_in_svg(svg_content)
            svg_content = fix_image_aspect_in_svg(svg_content)

            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(svg_content)

        # 3. Export to PPTX via pptx_exporter module
        # A pasta tmpdir deve agir como o root directory do projeto para o ppt-master.
        # Precisamos criar as pastas esperadas (exports, notes) mesmo que vazias
        os.makedirs(os.path.join(tmpdir, "exports"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "notes"), exist_ok=True)

        # Cria arquivo total.md vazio para evitar erros do builder se ele ler
        with open(os.path.join(tmpdir, "notes", "total.md"), "w") as f:
            f.write("")

        # Como o pacote svg_to_pptx do hugohe espera um projeto no sys.argv, podemos
        # simular chamando a API do builder diretamente ou modificando sys.argv (não recomendado).
        # Vamos importar a API direta de conversão.
        from ppt_master.svg_to_pptx import create_pptx_with_native_svg

        # Gerar o PPTX
        try:
            pptx_path = os.path.join(tmpdir, "exports", f"{job_id}.pptx")
            create_pptx_with_native_svg(tmpdir, "final", pptx_path)
        except Exception as build_err:
            print(f"Erro na geração nativa do PPTX: {build_err}")
            # Se falhar, atualiza o job e aborta
            job_ref.update({"status": "error", "error_msg": str(build_err)})
            return

        # 4. Upload to Drive & Set ACL
        from main import get_drive_service
        service = get_drive_service()

        from googleapiclient.http import MediaFileUpload
        file_metadata = {
            'name': f"{job.get('tema', 'Apresentacao')[:30]}.pptx",
            'mimeType': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        }
        media = MediaFileUpload(pptx_path, mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation', resumable=True)

        uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        file_id = uploaded_file.get('id')
        web_view_link = uploaded_file.get('webViewLink')

        # Set ACL
        if user_email:
            permission = {
                'type': 'user',
                'role': 'writer',
                'emailAddress': user_email
            }
            service.permissions().create(fileId=file_id, body=permission, fields='id').execute()

        # 5. Clean up Storage
        for blob in bucket.list_blobs(prefix=f"slides/{job_id}/"):
            blob.delete()

        # 6. Update Job & Notify
        job_ref.update({
            "status": "completed",
            "driveLink": web_view_link,
            "completedAt": firestore.SERVER_TIMESTAMP
        })

        emit_notification_backend(
            title="Apresentação Concluída",
            message="Sua apresentação foi gerada com sucesso e está pronta no Google Drive.",
            n_type="success",
            link=web_view_link
        )
