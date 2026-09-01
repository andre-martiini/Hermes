"""Criação de rascunhos Gmail com anexos por referência, nunca por base64."""

from __future__ import annotations

import base64
import hashlib
import html
import mimetypes
import re
from datetime import datetime, timezone
from email.message import EmailMessage

from firebase_admin import firestore


def _markdown_to_html(text: str) -> str:
    escaped = html.escape(str(text or ""))
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    lines = []
    for line in escaped.splitlines() or [""]:
        if line.startswith("# "):
            lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            lines.append(f"<h2>{line[3:]}</h2>")
        else:
            lines.append(f"<p>{line}</p>")
    return "\n".join(lines)


def _headers(message: dict) -> dict[str, str]:
    return {str(h.get("name") or "").lower(): str(h.get("value") or "")
            for h in ((message.get("payload") or {}).get("headers") or [])}


def _thread_recipients(service, thread_id: str) -> tuple[list[str], dict[str, str]]:
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    messages = thread.get("messages") or []
    if not messages:
        raise ValueError(f"Thread '{thread_id}' não contém mensagens.")
    headers = _headers(messages[-1])
    to = headers.get("reply-to") or headers.get("from")
    if not to:
        raise ValueError("Não foi possível herdar destinatário da thread.")
    return [to], headers


def criar(ctx, args: dict) -> dict:
    if "conteudo_base64" in args or any(isinstance(item, dict) and "conteudo_base64" in item for item in (args.get("anexos") or [])):
        return {"erro": "conteudo_base64 não é aceito; envie o arquivo via preparar_upload e use upload_token."}
    from main import get_gmail_service
    from tools.anexar_arquivo import resolver_anexo_por_referencia

    service = get_gmail_service()
    thread_id = str(args.get("responder_a_thread_id") or "").strip()
    recipients = [str(x).strip() for x in (args.get("para") or []) if str(x).strip()]
    thread_headers = {}
    if thread_id:
        inherited, thread_headers = _thread_recipients(service, thread_id)
        if not recipients:
            recipients = inherited
    if not recipients:
        return {"erro": "Informe para; só pode ficar vazio quando responder_a_thread_id herdar destinatários."}
    subject = str(args.get("assunto") or "").strip() or str(thread_headers.get("subject") or "").strip()
    if not subject:
        return {"erro": "Informe assunto."}

    message = EmailMessage()
    message["To"] = ", ".join(recipients)
    cc = [str(x).strip() for x in (args.get("cc") or []) if str(x).strip()]
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    if thread_id:
        if thread_headers.get("message-id"):
            message["In-Reply-To"] = thread_headers["message-id"]
            message["References"] = thread_headers.get("references", thread_headers["message-id"])
    body = str(args.get("corpo") or "")
    message.set_content(body)
    message.add_alternative(_markdown_to_html(body), subtype="html")

    attached = []
    try:
        for reference in args.get("anexos") or []:
            data, name = resolver_anexo_por_referencia(ctx, reference)
            mime, _ = mimetypes.guess_type(name)
            main, sub = (mime or "application/octet-stream").split("/", 1)
            message.add_attachment(data, maintype=main, subtype=sub, filename=name)
            attached.append({"nome": name, "tamanho_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    except ValueError as exc:
        return {"erro": str(exc)}

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    body_api = {"message": {"raw": raw}}
    if thread_id:
        body_api["message"]["threadId"] = thread_id
    draft = service.users().drafts().create(userId="me", body=body_api).execute()
    draft_id = str(draft.get("id") or "")
    if not draft_id:
        return {"erro": "Gmail não devolveu o id do rascunho."}
    task_id = str(args.get("acao_id") or "").strip()
    if task_id:
        task_ref = ctx.db.collection("tarefas").document(task_id)
        if not task_ref.get().exists:
            return {"erro": f"Ação '{task_id}' não encontrada; rascunho criado sem diário: {draft_id}"}
        names = ", ".join(f"{a['nome']} ({a['tamanho_bytes']} bytes)" for a in attached) or "sem anexos"
        task_ref.update({"acompanhamento": firestore.ArrayUnion([{
            "data": datetime.now(timezone.utc).isoformat(),
            "nota": f"Rascunho de e-mail criado (draft {draft_id}), anexos: {names}. Não enviado.",
        }])})
    return {"status": "draft_created", "draft_id": draft_id,
            "link": f"https://mail.google.com/mail/u/0/#drafts/{draft_id}", "anexos": attached,
            "enviado": False}
