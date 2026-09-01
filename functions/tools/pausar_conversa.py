"""Pausa uma conversa de WhatsApp com confirmação obrigatória no MCP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
from zoneinfo import ZoneInfo

from firebase_admin import firestore

from inbox_pendentes import _doc_id


TZ = ZoneInfo("America/Sao_Paulo")
ACTIVE_STATUSES = {"em andamento", "stand-by"}


def _digits(value) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())


def _next_business_day(day):
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _parse_resume(value, now: datetime | None = None) -> tuple[datetime, str]:
    now = now or datetime.now(TZ)
    raw = str(value or "").strip()
    if raw == "amanha_manha":
        target = datetime.combine(_next_business_day(now.date()), datetime.min.time(), TZ).replace(hour=8)
        return target, "amanhã de manhã"
    if raw == "hoje_tarde":
        target = datetime.combine(now.date(), datetime.min.time(), TZ).replace(hour=14)
        return target, "hoje à tarde"
    if not raw:
        raise ValueError("Informe retomar_em em ISO datetime, amanha_manha ou hoje_tarde.")
    try:
        target = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("retomar_em deve ser ISO datetime, amanha_manha ou hoje_tarde.") from exc
    if target.tzinfo is None:
        raise ValueError("retomar_em precisa incluir fuso horário (ex.: -03:00).")
    target = target.astimezone(TZ)
    meses = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
    phrase = f"dia {target.day} de {meses[target.month - 1]}"
    if target.hour or target.minute:
        phrase += f" às {target.hour:02d}h" + (f"{target.minute:02d}" if target.minute else "")
    return target, phrase


def _find_chat(ctx, value: str) -> dict:
    query = str(value or "").strip()
    if not query:
        raise ValueError("Informe contato_ou_grupo.")
    digits = _digits(query)
    matches = []
    for doc in ctx.db.collection("perfil_pessoas").stream():
        data = doc.to_dict() or {}
        name = str(data.get("nome") or "").strip()
        phone = str(data.get("telefone") or "").strip()
        chat_id = str(data.get("whatsapp_chat_id") or "").strip()
        if query.lower() == name.lower() or query == chat_id or (digits and digits == _digits(phone)):
            if chat_id:
                matches.append({"nome": name or chat_id, "chat_id": chat_id,
                                "to_number": phone or chat_id, "tipo": "contato"})
    # Grupo não é um contato individual, mas só é aceito se estiver no índice de
    # chats já conhecido pelo Hermes — nunca se cria um destinatário por texto livre.
    for doc in ctx.db.collection("whatsapp_chats").stream():
        data = doc.to_dict() or {}
        chat_id = str(data.get("chat_id") or doc.id).strip()
        name = str(data.get("chat_name") or "").strip()
        if chat_id.endswith("@g.us") and (query == chat_id or query.lower() == name.lower()):
            matches.append({"nome": name or chat_id, "chat_id": chat_id,
                            "to_number": chat_id, "tipo": "grupo"})
    unique = {m["chat_id"]: m for m in matches}
    if not unique:
        raise ValueError("Contato ou grupo não resolvido na base do Hermes; nada foi enviado.")
    if len(unique) > 1:
        raise ValueError("Contato ou grupo ambíguo; informe nome completo, número ou chat_id.")
    return next(iter(unique.values()))


def _linked_task(ctx, chat_id: str, requested: str | None) -> tuple[dict | None, object | None]:
    if requested:
        snap = ctx.db.collection("tarefas").document(str(requested)).get()
        if not snap.exists:
            raise ValueError(f"Ação '{requested}' não encontrada.")
        data = snap.to_dict() or {}
        data["id"] = snap.id
        return data, snap.reference
    for snap in ctx.db.collection("tarefas").stream():
        data = snap.to_dict() or {}
        if str(data.get("status") or "").strip().lower() not in ACTIVE_STATUSES:
            continue
        if any(isinstance(link, dict) and str(link.get("chat_id") or "") == chat_id
               for link in (data.get("whatsapp_vinculos") or [])):
            data["id"] = snap.id
            return data, snap.reference
    return None, None


def _last_excerpt(ctx, chat_id: str) -> str:
    snap = ctx.db.collection("inbox_pendentes").document(_doc_id("wa", chat_id)).get()
    return str((snap.to_dict() or {}).get("trecho") or "") if snap.exists else ""


def preview(ctx, args: dict, *, now: datetime | None = None) -> dict:
    """Dados concretos para o gate MCP; não grava nem enfileira mensagem."""
    resolved = _find_chat(ctx, args.get("contato_ou_grupo"))
    resume, when_text = _parse_resume(args.get("retomar_em"), now)
    text = str(args.get("mensagem") or "").strip()
    if not text:
        text = (f"{resolved['nome']}, vi sua mensagem. Não consigo tratar agora — "
                f"volto a isso {when_text}. Se for urgente, me liga.")
    task, _ = _linked_task(ctx, resolved["chat_id"], args.get("acao_id"))
    return {
        "status": "aguardando_confirmacao",
        "destinatario": {"nome": resolved["nome"], "chat_id": resolved["chat_id"], "tipo": resolved["tipo"]},
        "mensagem": text,
        "retomar_em": resume.isoformat(),
        "acao_vinculada": ({"id": task.get("id"), "titulo": task.get("titulo")} if task else None),
    }


def pausar(ctx, args: dict) -> dict:
    """Executa depois do gate MCP ter recebido ``_confirmed: true``."""
    proposal = preview(ctx, args)
    destination = proposal["destinatario"]
    task, task_ref = _linked_task(ctx, destination["chat_id"], args.get("acao_id"))

    from tools.schedule_whatsapp_message import schedule_whatsapp_message
    queued = schedule_whatsapp_message(ctx.db, _find_chat(ctx, args.get("contato_ou_grupo"))["to_number"],
                                        proposal["mensagem"], datetime.now(timezone.utc).isoformat())
    if queued.startswith("Erro"):
        return {"erro": queued}

    pause_until = proposal["retomar_em"]
    inbox_ref = ctx.db.collection("inbox_pendentes").document(_doc_id("wa", destination["chat_id"]))
    inbox_ref.set({"tipo": "whatsapp", "chat_id": destination["chat_id"],
                   "pausada_ate": pause_until, "updated_at": datetime.now(timezone.utc)}, merge=True)

    if task and task_ref:
        import subtarefas
        plan = list(task.get("plano_acao") or [])
        excerpt = _last_excerpt(ctx, destination["chat_id"])
        step_text = f"Retomar com {destination['nome']}: {excerpt or 'mensagem pendente'}"
        step = next((x for x in plan if isinstance(x, dict) and x.get("pausa_conversa_chat_id") == destination["chat_id"]), None)
        if step:
            step.update({"text": step_text, "estado": "aguardando_terceiro", "completed": False,
                         "aguardando_de": "André", "data_prevista": pause_until})
        else:
            plan.append({"id": str(uuid.uuid4())[:8], "text": step_text, "completed": False,
                         "estado": "aguardando_terceiro", "aguardando_de": "André",
                         "data_prevista": pause_until, "pausa_conversa_chat_id": destination["chat_id"]})
        now_iso = datetime.now(timezone.utc).isoformat()
        task_ref.update({
            "plano_acao": plan,
            "execution_lane": subtarefas.derivar_lane(plan, task.get("execution_lane")),
            "acompanhamento": firestore.ArrayUnion([{
                "data": now_iso,
                "nota": f"Conversa pausada com {destination['nome']}. Texto enviado: {proposal['mensagem']} Retomar em {pause_until}.",
            }]),
        })

    return {"status": "enfileirada", "destinatario": destination, "mensagem": proposal["mensagem"],
            "retomar_em": pause_until, "envio": queued, "acao_atualizada": bool(task_ref)}
