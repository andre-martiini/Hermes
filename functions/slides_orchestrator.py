from firebase_functions import https_fn, pubsub_fn, options
from firebase_admin import firestore
import json
import uuid
import os
import tempfile
import sys
from pathlib import Path
from datetime import datetime, timezone


def _get_slides_bucket():
    from firebase_admin import storage

    project_id = os.environ.get("GCLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or "gestao-hermes"
    candidates = [
        os.environ.get("SLIDES_STORAGE_BUCKET"),
        os.environ.get("FIREBASE_STORAGE_BUCKET"),
        f"{project_id}-slides-us-central1",
        f"{project_id}.firebasestorage.app",
        f"{project_id}.appspot.com",
    ]

    checked = []
    for bucket_name in [name for name in candidates if name]:
        bucket = storage.bucket(bucket_name)
        checked.append(bucket_name)
        if bucket.exists():
            return bucket

    raise RuntimeError(
        "Nenhum bucket de Storage disponível para slides. "
        f"Buckets testados: {', '.join(checked)}"
    )


def _short_error(exc: Exception, max_len: int = 500) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:max_len]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

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

    from main import get_db
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

    from main import get_db
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
    max_instances=3,
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
    concurrency=1,
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

    from main import get_db
    db = get_db()
    job_ref = db.collection('slide_jobs').document(job_id)

    try:
        def publish_finalizer_if_ready():
            """
            Uses a Firestore transaction with a 'finalizer_dispatched' flag to ensure
            the finalizer is triggered exactly once, even under concurrent workers.
            """
            should_dispatch = False
            should_mark_error = False

            @firestore.transactional
            def _check_and_mark(transaction, ref):
                nonlocal should_dispatch, should_mark_error
                snap = ref.get(transaction=transaction)
                if not snap.exists:
                    return
                data = snap.to_dict() or {}
                if data.get("finalizer_dispatched") or data.get("status") != "processing":
                    return

                statuses = data.get("slides_status") or []
                if not statuses or not all(s.get("status") in {"completed", "error"} for s in statuses):
                    return

                if any(s.get("status") == "error" for s in statuses):
                    transaction.update(ref, {
                        "status": "error",
                        "error_msg": "Falha ao gerar um ou mais slides. Veja os detalhes por slide.",
                        "completedAt": firestore.SERVER_TIMESTAMP,
                    })
                    should_mark_error = True
                    return

                if all(s.get("status") == "completed" for s in statuses):
                    transaction.update(ref, {"finalizer_dispatched": True})
                    should_dispatch = True

            _check_and_mark(db.transaction(), job_ref)

            if should_mark_error or not should_dispatch:
                return

            from google.cloud import pubsub_v1
            publisher = pubsub_v1.PublisherClient()
            project_id = os.environ.get("GCLOUD_PROJECT", "gestao-hermes")
            finalizer_topic_path = publisher.topic_path(project_id, "slide-finalizer")
            msg = json.dumps({"job_id": job_id})
            publisher.publish(finalizer_topic_path, msg.encode("utf-8"))

        # Atualiza status individual para processing
        def update_status(status_str):
            updated = False

            @firestore.transactional
            def _txn(transaction, ref):
                nonlocal updated
                snap = ref.get(transaction=transaction)
                if not snap.exists: return
                data = snap.to_dict() or {}
                if data.get("status") != "processing":
                    return
                statuses = data.get("slides_status") or []
                if slide_index >= len(statuses):
                    raise IndexError(f"Slide index out of range: {slide_index}")
                if statuses[slide_index].get("status") in {"completed", "error"}:
                    return
                statuses[slide_index] = {
                    **statuses[slide_index],
                    "status": status_str,
                    "updatedAt": _now_iso(),
                }
                transaction.update(ref, {"slides_status": statuses})
                updated = True
            _txn(db.transaction(), job_ref)
            return updated

        if not update_status("processing"):
            print(f"Skipping slide {slide_index} for {job_id}: job is no longer processing.")
            return

        keys_doc = db.collection('system').document('api_keys').get()
        gemini_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

        if not gemini_key:
            raise Exception("Chave Gemini não configurada.")

        from google import genai
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
        bucket = _get_slides_bucket()
        blob_path = f"slides/{job_id}/slide_{slide_index:03d}.svg"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(svg_content, content_type="image/svg+xml")

        update_status("completed")

        publish_finalizer_if_ready()

    except Exception as e:
        print(f"Error in executor for slide {slide_index}: {e}")
        @firestore.transactional
        def _err_txn(transaction, ref):
            snap = ref.get(transaction=transaction)
            if not snap.exists: return
            data = snap.to_dict() or {}
            if data.get("status") != "processing":
                return
            statuses = data.get("slides_status") or []
            if slide_index >= len(statuses):
                raise IndexError(f"Slide index out of range: {slide_index}")
            statuses[slide_index] = {
                **statuses[slide_index],
                "status": "error",
                "error_msg": _short_error(e),
                "updatedAt": _now_iso(),
            }
            transaction.update(ref, {"slides_status": statuses})
        _err_txn(db.transaction(), job_ref)
        publish_finalizer_if_ready()

@pubsub_fn.on_message_published(
    topic="slide-finalizer",
    memory=options.MemoryOption.GB_2,
    timeout_sec=540
)
def slideFinalizeWorker(event: pubsub_fn.CloudEvent[pubsub_fn.MessagePublishedData]):
    """
    Post-processing, SVG to PPTX, upload to Drive, alter ACL, and notify.
    """
    message_data = event.data.message.json
    job_id = message_data.get("job_id")

    if not job_id: return

    from main import get_db
    db = get_db()
    job_ref = db.collection('slide_jobs').document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists: return

    job = job_doc.to_dict()
    if job.get("status") != "processing":
        print(f"Skipping finalizer for {job_id}: status={job.get('status')}")
        return

    statuses = job.get("slides_status") or []
    if not statuses or any(s.get("status") != "completed" for s in statuses):
        job_ref.update({
            "status": "error",
            "error_msg": "Finalização abortada: nem todos os slides foram concluídos com sucesso."
        })
        return

    user_email = job.get("userEmail")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Download SVGs
        bucket = _get_slides_bucket()
        blobs = bucket.list_blobs(prefix=f"slides/{job_id}/")

        svg_output_dir = os.path.join(tmpdir, "svg_output")
        svg_final_dir = os.path.join(tmpdir, "svg_final")
        os.makedirs(svg_output_dir, exist_ok=True)
        os.makedirs(svg_final_dir, exist_ok=True)

        for blob in blobs:
            file_path = os.path.join(svg_output_dir, os.path.basename(blob.name))
            blob.download_to_filename(file_path)

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ppt_master'))
        from finalize_svg import crop_images_in_svg, embed_icons_in_file, fix_image_aspect_in_svg
        from svg_finalize.embed_icons import DEFAULT_ICONS_DIR
        icons_dir = DEFAULT_ICONS_DIR

        # 2. Finalize SVGs usando helpers file-based do PPT Master
        for svg_file in os.listdir(svg_output_dir):
            if not svg_file.endswith(".svg"):
                continue
            src_path = os.path.join(svg_output_dir, svg_file)
            dest_path = os.path.join(svg_final_dir, svg_file)
            svg_path = Path(dest_path)

            with open(src_path, "r", encoding="utf-8") as src_file:
                with open(dest_path, "w", encoding="utf-8") as dest_file:
                    dest_file.write(src_file.read())

            embed_icons_in_file(svg_path, icons_dir, dry_run=False, verbose=False)
            crop_images_in_svg(str(svg_path), dry_run=False, verbose=False)
            fix_image_aspect_in_svg(str(svg_path), dry_run=False, verbose=False)

        # 3. Export to PPTX
        # A pasta tmpdir deve agir como o root directory do projeto para o ppt-master.
        # Precisamos criar as pastas esperadas (exports, notes) mesmo que vazias
        os.makedirs(os.path.join(tmpdir, "exports"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "notes"), exist_ok=True)

        # Cria arquivo total.md vazio para evitar erros do builder se ele ler
        with open(os.path.join(tmpdir, "notes", "total.md"), "w") as f:
            f.write("")

        from svg_to_pptx import create_pptx_with_native_svg

        # Gerar o PPTX
        try:
            pptx_path = os.path.join(tmpdir, "exports", f"{job_id}.pptx")
            svg_files = sorted(Path(svg_final_dir).glob("*.svg"))
            if len(svg_files) != len(statuses):
                raise RuntimeError(
                    f"Quantidade de SVGs inválida: {len(svg_files)} gerados para {len(statuses)} slides."
                )
            build_ok = create_pptx_with_native_svg(
                svg_files=svg_files,
                output_path=Path(pptx_path),
                use_native_shapes=True,
                verbose=False,
            )
            if not build_ok:
                raise RuntimeError("Falha na montagem do PPTX a partir dos SVGs finalizados.")
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

        from main import emit_notification_backend
        emit_notification_backend(
            title="Apresentação Concluída",
            message="Sua apresentação foi gerada com sucesso e está pronta no Google Drive.",
            n_type="success",
            link=web_view_link
        )

@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST", "OPTIONS"]),
)
def cancelSlideJob(req: https_fn.CallableRequest):
    """
    Cancels a processing slide job, marking all non-terminal slides as error.
    """
    uid = req.auth.uid if req.auth else None
    if not uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Usuário não autenticado."
        )

    job_id = (req.data or {}).get('jobId')
    if not job_id:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="jobId é obrigatório."
        )

    from main import get_db
    db = get_db()
    job_ref = db.collection('slide_jobs').document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND,
            message="Job não encontrado."
        )

    job = job_doc.to_dict()

    if job.get('userId') != uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="Sem permissão para cancelar este job."
        )

    if job.get('status') != 'processing':
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Apenas jobs em processamento podem ser cancelados."
        )

    updated_statuses = [
        s if s['status'] in {'completed', 'error'} else {**s, 'status': 'error'}
        for s in (job.get('slides_status') or [])
    ]

    job_ref.update({
        'slides_status': updated_statuses,
        'status': 'error',
        'error_msg': 'Cancelado pelo usuário.',
        'finalizer_dispatched': True,
        'cancelledAt': firestore.SERVER_TIMESTAMP
    })

    return {'success': True}
