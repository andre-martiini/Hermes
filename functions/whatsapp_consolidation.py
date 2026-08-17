"""
Job de consolidação da Caixa de Entrada WhatsApp (WhatsappInboxView.tsx).

O frontend cria um doc em `whatsapp_consolidacoes` (o write é o RPC — mesmo
padrão de `copilot_jobs`) com os IDs das mensagens selecionadas; o trigger
`on_whatsapp_consolidacao_created` (main.py) chama `process_consolidation_job`,
que: transcreve os áudios (Groq/Whisper com fallback Gemini) e vídeos (Gemini
nativo — fala + descrição do conteúdo visual), cacheando o resultado de volta
em `whatsapp_messages.transcription_text`, monta o transcript literal POR CÓDIGO (nunca pela IA — é a garantia anti-alucinação),
sintetiza resumo/itens de ação/decisões com uma única chamada de IA restrita
ao transcript, grava um digest vetorizado em `whatsapp_digests` (mantém a
busca semântica do copiloto viva com dados curados, agora que a triagem
automática de whatsapp_ingest.py está desligada) e marca as mensagens
consolidadas. Progresso e resultado são empurrados por campos no próprio doc
do job, que o frontend assina via onSnapshot.
"""

import json
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from gemini_cost_controls import GEMINI_BALANCED_MODEL, generate_content_logged

FEATURE_SYNTHESIS = "whatsapp_consolidation.synthesis"

MAX_MESSAGES_PER_JOB = 200
MAX_AUDIO_BYTES = 24 * 1024 * 1024  # margem sob o limite de 25MB/arquivo do Groq
# Mesmo allowlist de extensões de on_long_transcription_uploaded (main.py) + oga
# (whatsapp-web.js grava ptt como audio/ogg; o worker deriva a extensão do mime).
AUDIO_EXT_ALLOWLIST = {"flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "oga", "wav", "webm"}
AUDIO_MESSAGE_TYPES = {"ptt", "audio"}

MAX_VIDEO_BYTES = 100 * 1024 * 1024  # vídeo de WhatsApp real fica bem abaixo disso
MAX_VIDEO_PROCESSING_SECONDS = 300  # orçamento do loop de vídeo, dentro do teto de 540s do trigger — protege contra job preso em "processing" (timeout duro mata a execução sem exceção catável)
# Convencional + subtipo de MIME cru (o worker deriva a extensão de mimetype.split('/')[1])
VIDEO_EXT_ALLOWLIST = {"mp4", "quicktime", "mov", "webm", "3gpp", "3gp", "mpeg", "mpg", "mkv", "avi", "m4v"}
VIDEO_MESSAGE_TYPES = {"video"}

TZ_SP = ZoneInfo("America/Sao_Paulo")


def _ts_to_local(ts) -> datetime | None:
    if ts is None:
        return None
    if hasattr(ts, "astimezone"):
        return ts.astimezone(TZ_SP)
    return None


def _ts_to_iso(ts) -> str:
    return ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")


def _author_label(msg: dict) -> str:
    if msg.get("from_me"):
        return "Eu"
    return str(msg.get("author_name") or "Contato").strip() or "Contato"


def _ext_from_storage_path(storage_path: str) -> str:
    tail = str(storage_path or "").rsplit(".", 1)
    return tail[1].lower() if len(tail) == 2 else ""


def _build_transcript(messages: list[dict]) -> str:
    """Transcript literal, montado deterministicamente — cabeçalho de dia quando a
    data muda, uma linha `[HH:mm] Autor: conteúdo` por mensagem. Áudios e vídeos usam
    a transcrição (ou o placeholder de indisponibilidade) preenchida em
    `_transcribe_selected_audios`/`_transcribe_selected_videos` — vídeo preserva a
    legenda ao lado da transcrição; demais mídias viram `[tipo]` + legenda."""
    lines: list[str] = []
    last_day: str | None = None
    for msg in messages:
        dt = _ts_to_local(msg.get("timestamp"))
        day = dt.strftime("%d/%m/%Y") if dt else "?"
        hhmm = dt.strftime("%H:%M") if dt else "--:--"
        if day != last_day:
            lines.append(f"--- {day} ---")
            last_day = day

        author = _author_label(msg)
        mtype = str(msg.get("message_type") or "chat")
        content = str(msg.get("content") or "").strip()

        if mtype in AUDIO_MESSAGE_TYPES:
            body = f"[áudio] {str(msg.get('transcription_text') or '[áudio sem transcrição]').strip()}"
        elif mtype in VIDEO_MESSAGE_TYPES:
            transcr = str(msg.get("transcription_text") or "[vídeo sem transcrição]").strip()
            body = f"[vídeo] {transcr}" + (f" — legenda: {content}" if content else "")
        elif content:
            body = content if mtype == "chat" else f"[{mtype}] {content}"
        else:
            body = f"[{mtype}]"

        lines.append(f"[{hhmm}] {author}: {body}")
    return "\n".join(lines)


def _build_synthesis_prompt(chat_name: str, transcript: str) -> str:
    hoje = datetime.now(TZ_SP).strftime("%Y-%m-%d")
    return f"""Você é o Hermes, assistente pessoal. Abaixo está o transcript LITERAL de mensagens
selecionadas da conversa de WhatsApp "{chat_name}" (montado automaticamente, sem interpretação).
Hoje é {hoje}.

TRANSCRIPT:
{transcript}

Produza um relatório executivo do que está NESTE transcript. Responda APENAS com um JSON no formato exato:
{{
  "resumo": "2 a 5 frases (português) do que a conversa trata",
  "topicos": ["até 4 palavras/expressões-chave"],
  "itens_de_acao": [
    {{"descricao": "o que precisa ser feito", "responsavel": "eu" | "contato" | "nome citado", "prazo": "YYYY-MM-DD ou null"}}
  ],
  "decisoes": ["pontos acordados/definidos na conversa — compromissos, valores, responsabilidades"]
}}

Regras:
- Referencie APENAS o que está no transcript acima. Não infira compromissos, valores ou prazos que não foram ditos.
- "itens_de_acao" e "decisoes" ficam vazios ([]) quando o transcript não traz nada desse tipo — não invente.
- Datas relativas ("amanhã", "sexta") devem ser convertidas para YYYY-MM-DD com base na data da mensagem em que aparecem (os cabeçalhos --- dd/mm/aaaa --- marcam os dias).
- Trechos "[áudio sem transcrição]", "[áudio não capturado]", "[vídeo sem transcrição]", "[vídeo não capturado]" ou "[Transcrição indisponível...]" indicam conteúdo inacessível — não especule sobre eles.
"""


def _transcribe_selected_audios(db, job_ref, messages: list[dict], refs_by_id: dict) -> tuple[int, int]:
    """Preenche `transcription_text` em cada mensagem de áudio da seleção — do cache
    quando já existe, senão baixando do Storage e transcrevendo. Cacheia cada sucesso
    imediatamente no doc da mensagem (job morrendo no áudio N preserva os N-1
    anteriores; reconsolidação nunca repaga Groq). Retorna (transcritos, ignorados)."""
    from google.cloud import firestore as gcf
    from hermes_core_logic import _get_hermes_storage_bucket, _transcribe_audio_bytes

    audio_msgs = [m for m in messages if str(m.get("message_type")) in AUDIO_MESSAGE_TYPES]
    if not audio_msgs:
        return 0, 0

    n_transcritos = 0
    n_ignorados = 0
    bucket = None
    total = len(audio_msgs)

    for i, msg in enumerate(audio_msgs, start=1):
        if str(msg.get("transcription_text") or "").strip():
            continue  # cache hit — não conta como novo transcrito nem ignorado

        media = msg.get("media") or {}
        storage_path = str(media.get("storage_path") or "").strip()
        if not storage_path:
            msg["transcription_text"] = "[áudio não capturado]"
            n_ignorados += 1
            continue
        if int(media.get("sizeBytes") or 0) > MAX_AUDIO_BYTES:
            msg["transcription_text"] = "[áudio ignorado: excede 24MB]"
            n_ignorados += 1
            continue
        ext = _ext_from_storage_path(storage_path)
        if ext not in AUDIO_EXT_ALLOWLIST:
            msg["transcription_text"] = f"[áudio ignorado: formato .{ext or '?'} não suportado]"
            n_ignorados += 1
            continue

        job_ref.set({
            "progress": f"Transcrevendo áudio {i}/{total}",
            "updated_at": gcf.SERVER_TIMESTAMP,
        }, merge=True)

        try:
            if bucket is None:
                bucket = _get_hermes_storage_bucket()
            audio_bytes = bucket.blob(storage_path).download_as_bytes()
        except Exception as exc:
            print(f"[WA-CONSOL] Falha ao baixar {storage_path}: {exc}")
            msg["transcription_text"] = "[áudio ignorado: falha ao baixar do Storage]"
            n_ignorados += 1
            continue

        texto = _transcribe_audio_bytes(audio_bytes, ext, db)
        msg["transcription_text"] = texto
        if texto.startswith("[Transcrição indisponível"):
            # Erro transitório dos motores — não cachear, para o retry funcionar.
            n_ignorados += 1
            continue

        n_transcritos += 1
        msg_ref = refs_by_id.get(msg.get("id"))
        if msg_ref is not None:
            try:
                msg_ref.set({
                    "transcription_text": texto,
                    "transcription_model": "whisper-large-v3-turbo",
                }, merge=True)
            except Exception as exc:
                print(f"[WA-CONSOL] Falha ao cachear transcrição de {msg.get('id')}: {exc}")

    return n_transcritos, n_ignorados


def _transcribe_selected_videos(db, job_ref, messages: list[dict], refs_by_id: dict) -> tuple[int, int]:
    """Preenche `transcription_text` em cada mensagem de vídeo da seleção — mesmo padrão
    de `_transcribe_selected_audios`, mais um orçamento de tempo (MAX_VIDEO_PROCESSING_SECONDS):
    ao estourar, os vídeos restantes viram ignorados (nada fica cacheado neles, então uma
    nova consolidação os retenta) em vez de arriscar o timeout duro do trigger, que mata a
    execução sem exceção catável e deixaria o job preso em 'processing' para sempre."""
    from google.cloud import firestore as gcf
    from hermes_core_logic import _get_hermes_storage_bucket, _transcribe_video_bytes

    video_msgs = [m for m in messages if str(m.get("message_type")) in VIDEO_MESSAGE_TYPES]
    if not video_msgs:
        return 0, 0

    n_transcritos = 0
    n_ignorados = 0
    bucket = None
    total = len(video_msgs)
    start_time = time.monotonic()

    for i, msg in enumerate(video_msgs, start=1):
        if str(msg.get("transcription_text") or "").strip():
            continue  # cache hit — não conta como novo transcrito nem ignorado

        if time.monotonic() - start_time > MAX_VIDEO_PROCESSING_SECONDS:
            msg["transcription_text"] = "[vídeo ignorado: orçamento de tempo do job esgotado]"
            n_ignorados += 1
            continue

        media = msg.get("media") or {}
        storage_path = str(media.get("storage_path") or "").strip()
        if not storage_path:
            msg["transcription_text"] = "[vídeo não capturado]"
            n_ignorados += 1
            continue
        if int(media.get("sizeBytes") or 0) > MAX_VIDEO_BYTES:
            msg["transcription_text"] = f"[vídeo ignorado: excede {MAX_VIDEO_BYTES // (1024 * 1024)}MB]"
            n_ignorados += 1
            continue
        ext = _ext_from_storage_path(storage_path)
        if ext not in VIDEO_EXT_ALLOWLIST:
            msg["transcription_text"] = f"[vídeo ignorado: formato .{ext or '?'} não suportado]"
            n_ignorados += 1
            continue

        job_ref.set({
            "progress": f"Transcrevendo vídeo {i}/{total}",
            "updated_at": gcf.SERVER_TIMESTAMP,
        }, merge=True)

        try:
            if bucket is None:
                bucket = _get_hermes_storage_bucket()
            video_bytes = bucket.blob(storage_path).download_as_bytes()
        except Exception as exc:
            print(f"[WA-CONSOL] Falha ao baixar {storage_path}: {exc}")
            msg["transcription_text"] = "[vídeo ignorado: falha ao baixar do Storage]"
            n_ignorados += 1
            continue

        texto = _transcribe_video_bytes(video_bytes, ext, db)
        msg["transcription_text"] = texto
        if texto.startswith("[Transcrição indisponível"):
            # Erro transitório do motor — não cachear, para o retry funcionar.
            n_ignorados += 1
            continue

        n_transcritos += 1
        msg_ref = refs_by_id.get(msg.get("id"))
        if msg_ref is not None:
            try:
                msg_ref.set({
                    "transcription_text": texto,
                    "transcription_model": "gemini-video-understanding",
                }, merge=True)
            except Exception as exc:
                print(f"[WA-CONSOL] Falha ao cachear transcrição de vídeo {msg.get('id')}: {exc}")

    return n_transcritos, n_ignorados


def process_consolidation_job(db, job_ref, job: dict) -> None:
    """Corpo do trigger on_whatsapp_consolidacao_created (main.py). Qualquer exceção
    não tratada vira status='error' no doc do job (o chamador faz o try/except)."""
    from google.cloud import firestore as gcf
    from main import get_genai_module, _cached_doc_get
    from whatsapp_ingest import _sanitize_itens_de_acao, _sanitize_decisoes, _save_whatsapp_digest

    job_id = job_ref.id
    chat_id = str(job.get("chat_id") or "").strip()
    chat_name = str(job.get("chat_name") or chat_id).strip() or chat_id
    message_ids = [str(m).strip() for m in (job.get("message_ids") or []) if str(m).strip()]

    if not chat_id or not message_ids:
        raise ValueError("Job sem chat_id ou sem message_ids.")
    if len(message_ids) > MAX_MESSAGES_PER_JOB:
        raise ValueError(f"Seleção excede o máximo de {MAX_MESSAGES_PER_JOB} mensagens.")

    job_ref.set({"status": "processing", "progress": "Carregando mensagens...",
                 "updated_at": gcf.SERVER_TIMESTAMP}, merge=True)

    col = db.collection("whatsapp_messages")
    snaps = db.get_all([col.document(mid) for mid in message_ids])
    messages: list[dict] = []
    refs_by_id: dict = {}
    for snap in snaps:
        if not snap.exists:
            continue
        data = snap.to_dict() or {}
        data["id"] = snap.id
        messages.append(data)
        refs_by_id[snap.id] = snap.reference
    if not messages:
        raise ValueError("Nenhuma das mensagens selecionadas foi encontrada.")

    messages.sort(key=lambda m: (m.get("timestamp") is None, m.get("timestamp")))

    # 1. Transcrição (com cache) — preenche transcription_text em cada áudio/vídeo.
    n_transcritos, n_ignorados = _transcribe_selected_audios(db, job_ref, messages, refs_by_id)
    n_videos_transcritos, n_videos_ignorados = _transcribe_selected_videos(db, job_ref, messages, refs_by_id)

    # 2. Transcript literal — determinístico, por código.
    transcript = _build_transcript(messages)

    # 3. Síntese por IA, restrita ao transcript.
    job_ref.set({"progress": "Sintetizando...", "updated_at": gcf.SERVER_TIMESTAMP}, merge=True)

    keys_doc = _cached_doc_get(db, "system", "api_keys")
    api_key = keys_doc.to_dict().get("gemini_api_key") if keys_doc.exists else None
    if not api_key:
        raise RuntimeError("Gemini API Key não configurada (system/api_keys).")

    genai = get_genai_module()
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = generate_content_logged(
        client,
        model=GEMINI_BALANCED_MODEL,
        contents=_build_synthesis_prompt(chat_name, transcript),
        feature=FEATURE_SYNTHESIS,
        db=db,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
    )
    raw = (response.text or "").strip()
    if "```json" in raw:
        raw = raw.split("```json")[-1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[-1].split("```")[0].strip()
    analysis = json.loads(raw)

    resumo = str(analysis.get("resumo") or "").strip()
    topicos = [str(t) for t in (analysis.get("topicos") or []) if str(t).strip()][:4]
    itens_de_acao = _sanitize_itens_de_acao(analysis.get("itens_de_acao"))
    decisoes = _sanitize_decisoes(analysis.get("decisoes"))

    # 4. Digest vetorizado curado — mantém buscar_conversas_whatsapp vivo.
    digest_id = f"consol_{job_id}"
    try:
        _save_whatsapp_digest(db, digest_id, chat_id, chat_name, messages, {
            "resumo": resumo,
            "topicos": topicos,
            "relevancia": "consolidacao",
            "itens_de_acao": itens_de_acao,
            "decisoes": decisoes,
            "datas_mencionadas": [],
        }, api_key)
    except Exception as exc:
        print(f"[WA-CONSOL] Falha ao gravar digest {digest_id}: {exc}")
        digest_id = None

    # 5. Marcar mensagens como consolidadas (badge na timeline).
    batch = db.batch()
    for mid, ref in refs_by_id.items():
        batch.set(ref, {"consolidation_ids": gcf.ArrayUnion([job_id])}, merge=True)
    batch.commit()

    # 5.1. Vínculo best-effort com perfil_pessoas (interacoes_pessoas)
    if chat_id.endswith("@c.us"):
        try:
            person_docs = list(db.collection("perfil_pessoas").where("whatsapp_chat_id", "==", chat_id).limit(2).stream())
            if len(person_docs) == 1:
                person_id = person_docs[0].id
                last_msg_ts = _ts_to_iso(messages[-1].get("timestamp")) or datetime.now(timezone.utc).isoformat()
                now_iso = datetime.now(timezone.utc).isoformat()
                interacao_data = {
                    "pessoa_id": person_id,
                    "tipo": "whatsapp",
                    "data": last_msg_ts,
                    "descricao": resumo,
                    "consolidacao_id": job_id,
                    "link_origem": "/whatsapp",
                    "data_criacao": now_iso,
                }
                db.collection("interacoes_pessoas").document().set(interacao_data)
                print(f"[WA-CONSOL] Interacao registrada para pessoa {person_id} (chat {chat_id}).")
            elif len(person_docs) >= 2:
                print(f"[WA-CONSOL] Aviso: múltiplos contatos com o mesmo whatsapp_chat_id={chat_id}. Vínculo automático ignorado.")
        except Exception as person_err:
            print(f"[WA-CONSOL] Falha ao registrar interacao em perfil_pessoas: {person_err}")

    # 6. Resultado final.
    attachments = [
        {"message_id": m["id"], "mimeType": (m.get("media") or {}).get("mimeType") or "",
         "storage_path": (m.get("media") or {}).get("storage_path") or ""}
        for m in messages
        if (m.get("media") or {}).get("storage_path")
        and str(m.get("message_type")) not in AUDIO_MESSAGE_TYPES | VIDEO_MESSAGE_TYPES
    ]
    job_ref.set({
        "status": "completed",
        "progress": None,
        "error": None,
        "transcript_literal": transcript,
        "resumo": resumo,
        "itens_de_acao": itens_de_acao,
        "decisoes": decisoes,
        "periodo_inicio": _ts_to_iso(messages[0].get("timestamp")),
        "periodo_fim": _ts_to_iso(messages[-1].get("timestamp")),
        "n_mensagens": len(messages),
        "n_audios_transcritos": n_transcritos,
        "n_audios_ignorados": n_ignorados,
        "n_videos_transcritos": n_videos_transcritos,
        "n_videos_ignorados": n_videos_ignorados,
        "attachments": attachments,
        "digest_id": digest_id,
        "updated_at": gcf.SERVER_TIMESTAMP,
    }, merge=True)
