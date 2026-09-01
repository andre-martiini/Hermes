"""Índice pequeno e determinístico de conversas que podem esperar resposta.

O MCP não consulta o histórico inteiro de WhatsApp ao montar ``obter_estado_atual``:
o worker de triagem atualiza uma linha por chat nesta coleção.  Assim, o resumo
matinal só lê ``inbox_pendentes`` e continua previsível mesmo quando o histórico
de mensagens cresce.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone


COLLECTION = "inbox_pendentes"
ACTIVE_STATUSES = {"em andamento", "stand-by"}
MAX_ITEMS = 15


def _as_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "to_datetime"):
        return _as_datetime(value.to_datetime())
    text = str(value or "").strip()
    if not text:
        return None
    # Gmail guarda internalDate em milissegundos desde Unix epoch.
    if text.isdigit() and len(text) >= 11:
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value) -> str | None:
    parsed = _as_datetime(value)
    return parsed.isoformat() if parsed else (str(value) if value else None)


def _doc_id(prefix: str, source_id: str) -> str:
    encoded = base64.urlsafe_b64encode(source_id.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{prefix}_{encoded}"


def atualizar_whatsapp(db, message: dict) -> None:
    """Espelha a última mensagem de um chat, sem reler o histórico.

    É chamado pelo mesmo ciclo que já consome ``whatsapp_messages``. Mensagens
    fora de ordem não podem sobrescrever uma mais recente.
    """
    chat_id = str(message.get("chat_id") or "").strip()
    when = _as_datetime(message.get("timestamp"))
    if not chat_id or not when:
        return
    ref = db.collection(COLLECTION).document(_doc_id("wa", chat_id))
    existing = ref.get()
    if existing.exists:
        current = _as_datetime((existing.to_dict() or {}).get("desde"))
        if current and current > when:
            return
    ref.set({
        "tipo": "whatsapp",
        "chat_id": chat_id,
        "chat_name": str(message.get("chat_name") or chat_id),
        "is_group": bool(message.get("is_group")),
        "ultima_de_andre": bool(message.get("from_me")),
        "desde": when,
        "trecho": str(message.get("content") or "")[:120],
        "updated_at": datetime.now(timezone.utc),
    }, merge=True)


def _allowlist(db) -> set[str]:
    settings = db.collection("system").document("settings").get()
    data = settings.to_dict() if settings.exists else {}
    ingest = (data or {}).get("whatsapp_ingest") or {}
    if ingest.get("leitura_total"):
        return {"*"}
    return {str(x).strip() for x in (ingest.get("chats_allowlist") or []) if str(x).strip()}


def _active_tasks(db) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    """Retorna ações ativas por chat, por e-mail e por id.

    E-mails já vinculados são identificados pelo envelope ``EMAIL::JSON`` do
    diário, cuja URL termina no id Gmail salvo no vínculo aprovado.
    """
    by_chat, by_email, by_id = {}, {}, {}
    for doc in db.collection("tarefas").stream():
        task = doc.to_dict() or {}
        if str(task.get("status") or "").strip().lower() not in ACTIVE_STATUSES:
            continue
        item = {
            "id": doc.id,
            "titulo": str(task.get("titulo") or "(sem título)"),
            "execution_lane": str(task.get("execution_lane") or ""),
            "degradation_count": int(task.get("degradation_count") or 0),
        }
        by_id[doc.id] = item
        for link in task.get("whatsapp_vinculos") or []:
            if isinstance(link, dict) and str(link.get("chat_id") or "").strip():
                by_chat[str(link["chat_id"]).strip()] = item
        for entry in task.get("acompanhamento") or []:
            note = str((entry or {}).get("nota") or "") if isinstance(entry, dict) else ""
            if not note.startswith("EMAIL::JSON::"):
                continue
            try:
                payload = json.loads(note.split("EMAIL::JSON::", 1)[1])
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            message_id = str(payload.get("v") or "").rstrip("/").split("/")[-1]
            if message_id:
                by_email[message_id] = item
    return by_chat, by_email, by_id


def _contacts(db) -> dict[str, str]:
    result = {}
    for doc in db.collection("perfil_pessoas").stream():
        data = doc.to_dict() or {}
        chat_id = str(data.get("whatsapp_chat_id") or "").strip()
        if chat_id and str(data.get("nome") or "").strip():
            result[chat_id] = str(data["nome"]).strip()
    return result


def _item(*, contato: str, canal: str, desde, trecho: str, task: dict | None,
          paused_until, now: datetime) -> dict | None:
    received = _as_datetime(desde)
    if not received:
        return None
    pause = _as_datetime(paused_until)
    if pause and pause > now:
        return None
    out = {
        "contato": contato,
        "canal": canal,
        "desde": _iso(received),
        "horas_aguardando": round(max(0, (now - received).total_seconds()) / 3600, 1),
        "acao_vinculada": ({"id": task["id"], "titulo": task["titulo"]} if task else None),
        "trecho": str(trecho or "")[:120],
        "pausada_ate": _iso(pause),
    }
    if pause and pause <= now:
        out["retomada_devida"] = True
    # O estado atual não possui a lane "critica" como valor canônico; aceita-a
    # caso seja introduzida e também reconhece a degradação já classificada como
    # crítica pelo resumo matinal.
    out["_critica"] = bool(task and (task["execution_lane"] == "critica" or task["degradation_count"] >= 3))
    return out


def coletar(db, now: datetime | None = None) -> dict:
    """Lê o índice materializado e devolve no máximo quinze respostas devidas."""
    now = now or datetime.now(timezone.utc)
    allowed = _allowlist(db)
    by_chat, by_email, by_id = _active_tasks(db)
    contacts = _contacts(db)
    items = []

    for doc in db.collection(COLLECTION).stream():
        data = doc.to_dict() or {}
        if data.get("tipo") != "whatsapp" or data.get("ultima_de_andre"):
            continue
        chat_id = str(data.get("chat_id") or "")
        if "*" not in allowed and chat_id not in allowed:
            continue
        task = by_chat.get(chat_id)
        # D1: regra conservadora aprovada. Grupos sem ação ativa não entram.
        if data.get("is_group") and not task:
            continue
        item = _item(
            contato=contacts.get(chat_id) or str(data.get("chat_name") or chat_id),
            canal="whatsapp_grupo" if data.get("is_group") else "whatsapp",
            desde=data.get("desde"), trecho=data.get("trecho") or "", task=task,
            paused_until=data.get("pausada_ate"), now=now,
        )
        if item:
            items.append(item)

    # O email-action-linker conserva os metadados da mensagem na sugestão; só
    # entram sugestões que já viraram um vínculo real no diário da ação.
    for doc in db.collection("email_action_suggestions").stream():
        data = doc.to_dict() or {}
        task = by_email.get(doc.id) or by_id.get(str(data.get("task_id") or ""))
        if not task or str(data.get("canal") or "") != "email":
            continue
        if not str(data.get("status") or "").startswith("applied"):
            continue
        item = _item(
            contato=str(data.get("sender") or data.get("origem_sinal") or "E-mail"),
            canal="gmail", desde=data.get("internal_date") or data.get("analyzed_at"),
            trecho=str(data.get("snippet") or data.get("resumo") or ""), task=task,
            paused_until=None, now=now,
        )
        if item:
            items.append(item)

    items.sort(key=lambda item: (not item.pop("_critica"), -item["horas_aguardando"], item["desde"]))
    omitted = max(0, len(items) - MAX_ITEMS)
    result = {"itens": items[:MAX_ITEMS]}
    if omitted:
        result["total_omitido"] = omitted
    return result
