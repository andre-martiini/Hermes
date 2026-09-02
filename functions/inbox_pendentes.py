"""Índice pequeno e determinístico de conversas que podem esperar resposta.

O MCP não consulta o histórico inteiro de WhatsApp ao montar ``obter_estado_atual``:
o worker de triagem atualiza uma linha por chat nesta coleção.  Assim, o resumo
matinal só lê ``inbox_pendentes`` e continua previsível mesmo quando o histórico
de mensagens cresce.
"""

from __future__ import annotations

import base64
import json
import re
from email.utils import parseaddr
from datetime import datetime, timezone

from firebase_admin import firestore


COLLECTION = "inbox_pendentes"
_STANDBY_STATUS_ALIASES = {"stand-by", "standby", "stand by", "cgby"}
_ACTIVE_STATUS_ALIASES = {"em andamento", "andamento", "nao iniciado", "não iniciado", "pendente"}
MAX_ITEMS = 15
EMAIL_SUGGESTIONS_LIMIT = 60
BACKFILL_PAGE_SIZE = 100
_AUTO_SENDER = re.compile(r"^(noreply|no-reply|naoresponda|nao-responda|notificacao|notification|mailer-daemon|newsletter)[@._-]", re.I)
_MEDIA_PREFIX = ("/9j/", "ivbor")
_DATA_URI = re.compile(r"^data:[^;,\s]+(?:;[^,\s]+)*;base64,", re.I)
_DEFAULT_DOMAINS = {"eventos.ifnmg.edu.br", "picpay.com", "picpay.com.br"}
_DEFAULT_ENDINGS = {"ok", "okay", "blz", "beleza", "obrigado", "obrigada", "mto obrigado", "mto obrigada", "muito obrigado", "muito obrigada", "valeu", "ja foi", "entendi", "ah sim entendi", "combinado", "perfeito", "show", "top", "joia", "ate amanha", "ate logo", "bom dia", "boa tarde", "boa noite", "abraco", "abs"}


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


def _is_active_status(value) -> bool:
    normalized = " ".join(str(value or "").strip().lower().split())
    return normalized in _ACTIVE_STATUS_ALIASES or normalized in _STANDBY_STATUS_ALIASES


def _whatsapp_payload(message: dict, when: datetime) -> dict:
    chat_id = str(message.get("chat_id") or "").strip()
    return {
        "tipo": "whatsapp",
        "chat_id": chat_id,
        "chat_name": str(message.get("chat_name") or chat_id),
        "is_group": bool(message.get("is_group")),
        "ultima_de_andre": bool(message.get("from_me")),
        "desde": when,
        "trecho": str(message.get("content") or "")[:120],
        "mentioned_ids": [str(x) for x in (message.get("mentioned_ids") or []) if str(x)],
        "mentions_andre": bool(message.get("mentions_andre")),
        "quoted_msg_id": message.get("quoted_msg_id") or None,
        "quoted_from_me": message.get("quoted_from_me"),
        "quoted_author": message.get("quoted_author") or None,
        "updated_at": datetime.now(timezone.utc),
    }


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
    ref.set(_whatsapp_payload(message, when), merge=True)


def atualizar_whatsapp_em_lote(db, messages: list[dict]) -> int:
    """Atualiza só a mensagem mais recente de cada chat, em batches Firestore."""
    latest: dict[str, tuple[datetime, dict]] = {}
    for message in messages:
        chat_id = str(message.get("chat_id") or "").strip()
        when = _as_datetime(message.get("timestamp"))
        if chat_id and when and (chat_id not in latest or when > latest[chat_id][0]):
            latest[chat_id] = (when, message)
    updates = []
    for chat_id, (when, message) in latest.items():
        ref = db.collection(COLLECTION).document(_doc_id("wa", chat_id))
        existing = ref.get()
        current = _as_datetime((existing.to_dict() or {}).get("desde")) if existing.exists else None
        if not current or current <= when:
            updates.append((ref, _whatsapp_payload(message, when)))
    for start in range(0, len(updates), 500):
        batch = db.batch()
        for ref, payload in updates[start:start + 500]:
            batch.set(ref, payload, merge=True)
        batch.commit()
    return len(updates)


def backfill_whatsapp_inicial(db) -> bool:
    """Reconstrói o índice uma página por vez a partir do registro de chats.

    O cursor da triagem cobre apenas mensagens que chegam depois dele. Este
    backfill independente consulta a última mensagem de cada chat conhecido,
    portanto o primeiro avanço do cursor não torna pendências históricas
    invisíveis. O marcador deixa a operação retomável e limitada por rodada.
    """
    marker_ref = db.collection("system").document("inbox_pendentes_backfill")
    marker = marker_ref.get()
    marker_data = marker.to_dict() or {} if marker.exists else {}
    if marker_data.get("completed_at"):
        return True
    last_chat_id = str(marker_data.get("last_chat_id") or "")
    query = db.collection("whatsapp_chats").order_by("__name__")
    if last_chat_id:
        query = query.start_after({"__name__": last_chat_id})
    chats = list(query.limit(BACKFILL_PAGE_SIZE).stream())
    if not chats:
        marker_ref.set({"completed_at": datetime.now(timezone.utc)}, merge=True)
        return True
    latest_messages = []
    for chat in chats:
        data = chat.to_dict() or {}
        chat_id = str(data.get("chat_id") or chat.id).strip()
        if not chat_id:
            continue
        rows = list(db.collection("whatsapp_messages")
                    .where("chat_id", "==", chat_id)
                    .order_by("timestamp", direction=firestore.Query.DESCENDING)
                    .limit(1).stream())
        if rows:
            latest_messages.append(rows[0].to_dict() or {})
    atualizar_whatsapp_em_lote(db, latest_messages)
    marker_ref.set({"last_chat_id": chats[-1].id, "updated_at": datetime.now(timezone.utc)}, merge=True)
    if len(chats) < BACKFILL_PAGE_SIZE:
        marker_ref.set({"completed_at": datetime.now(timezone.utc)}, merge=True)
        return True
    return False


def _allowlist(db) -> set[str]:
    settings = db.collection("system").document("settings").get()
    data = settings.to_dict() if settings.exists else {}
    ingest = (data or {}).get("whatsapp_ingest") or {}
    if ingest.get("leitura_total"):
        return {"*"}
    return {str(x).strip() for x in (ingest.get("chats_allowlist") or []) if str(x).strip()}


def _andre_ids(db) -> set[str]:
    settings = db.collection("system").document("settings").get()
    data = settings.to_dict() if settings.exists else {}
    ingest = (data or {}).get("whatsapp_ingest") or {}
    return {str(x).strip() for x in (ingest.get("andre_chat_ids") or []) if str(x).strip()}


def _active_tasks(db) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    """Retorna ações ativas por chat, por e-mail e por id.

    E-mails já vinculados são identificados pelo envelope ``EMAIL::JSON`` do
    diário, cuja URL termina no id Gmail salvo no vínculo aprovado.
    """
    by_chat, by_email, by_id = {}, {}, {}
    for doc in db.collection("tarefas").stream():
        task = doc.to_dict() or {}
        if not _is_active_status(task.get("status")):
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


def _noise_config(db) -> tuple[set[str], set[str]]:
    try:
        snap = db.collection("config").document("inbox_pendentes").get()
        data = snap.to_dict() or {} if snap.exists else {}
    except Exception:
        data = {}
    return (_DEFAULT_DOMAINS | {str(x).lower() for x in (data.get("remetentes_ignorados") or [])},
            _DEFAULT_ENDINGS | {_normalize_text(x) for x in (data.get("encerramentos") or [])})


def _normalize_text(value) -> str:
    import unicodedata
    return " ".join("".join(c for c in unicodedata.normalize("NFD", str(value or "").lower()) if unicodedata.category(c) != "Mn").split())


def _noise_reason(*, trecho: str, sender: str, is_email: bool, has_contact: bool, has_task: bool, domains: set[str], endings: set[str]) -> str | None:
    raw = str(trecho or "").strip()
    norm = _normalize_text(raw)
    if is_email:
        address = (parseaddr(str(sender or ""))[1] or str(sender or "")).lower().strip()
        if _AUTO_SENDER.match(address) or any(address.endswith("@" + d) for d in domains):
            return "automaticos"
    if not raw or raw.lower().startswith(_MEDIA_PREFIX) or _DATA_URI.match(raw) or not re.sub(r"[^\w]", "", norm):
        return "sem_texto"
    if not is_email and not has_contact and not has_task and re.search(r"oferta|cart[aã]o|desconto|promo[cç][aã]o|fatura|clique|aproveite", norm):
        return "automaticos"
    words = re.findall(r"\w+", norm)
    if "?" not in raw and len(words) <= 6 and norm.rstrip(".") in endings:
        return "encerramentos"
    return None


def _applied_email_suggestions(db):
    """Lê somente os vínculos aplicados, nunca a coleção histórica inteira."""
    collection = db.collection("email_action_suggestions")
    # O fallback atende os fakes mínimos dos testes; Firestore real sempre usa a
    # consulta indexada e limitada abaixo.
    if not hasattr(collection, "where"):
        return collection.stream()
    try:
        return collection.where(
            filter=firestore.FieldFilter("status", "in", ["applied", "applied_reactivated"])
        ).limit(EMAIL_SUGGESTIONS_LIMIT).stream()
    except TypeError:
        return collection.where("status", "in", ["applied", "applied_reactivated"]).limit(EMAIL_SUGGESTIONS_LIMIT).stream()


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


def coletar(db, now: datetime | None = None, incluir_filtrados: bool = False, limite: int = MAX_ITEMS) -> dict:
    """Lê o índice materializado e devolve no máximo quinze respostas devidas."""
    now = now or datetime.now(timezone.utc)
    allowed = _allowlist(db)
    andre_ids = _andre_ids(db)
    by_chat, by_email, by_id = _active_tasks(db)
    contacts = _contacts(db)
    items = []
    filtered = {"automaticos": 0, "encerramentos": 0, "sem_texto": 0}
    domains, endings = _noise_config(db)

    for doc in db.collection(COLLECTION).stream():
        data = doc.to_dict() or {}
        if data.get("tipo") != "whatsapp" or data.get("ultima_de_andre"):
            continue
        chat_id = str(data.get("chat_id") or "")
        if "*" not in allowed and chat_id not in allowed:
            continue
        task = by_chat.get(chat_id)
        inclusion_reason = "conversa_direta"
        if data.get("is_group"):
            # D1b: quando o capturador trouxe metadados da mensagem, uma menção
            # explícita ao André ou resposta a mensagem dele basta para o grupo
            # entrar. Dados antigos, sem esses campos, continuam no fallback
            # conservador e não são reprocessados.
            mentions = {str(x) for x in (data.get("mentioned_ids") or [])}
            relevant = bool(data.get("mentions_andre") or data.get("quoted_from_me") or (mentions & andre_ids))
            metadata_present = (data.get("mentioned_ids") is not None or data.get("quoted_msg_id") is not None
                                or data.get("quoted_from_me") is not None)
            if not relevant and (not task or metadata_present):
                continue
            inclusion_reason = "mencao" if (data.get("mentions_andre") or (mentions & andre_ids)) else ("resposta_a_mim" if data.get("quoted_from_me") else "grupo_vinculado")
        reason = _noise_reason(trecho=data.get("trecho") or "", sender="", is_email=False,
                               has_contact=chat_id in contacts, has_task=bool(task), domains=domains, endings=endings)
        if reason and not incluir_filtrados:
            filtered[reason] += 1
            continue
        item = _item(
            contato=contacts.get(chat_id) or str(data.get("chat_name") or chat_id),
            canal="whatsapp_grupo" if data.get("is_group") else "whatsapp",
            desde=data.get("desde"), trecho=data.get("trecho") or "", task=task,
            paused_until=data.get("pausada_ate"), now=now,
        )
        if item:
            item["motivo_inclusao"] = inclusion_reason
            items.append(item)

    # O email-action-linker conserva os metadados da mensagem na sugestão; só
    # entram sugestões que já viraram um vínculo real no diário da ação. Há no
    # máximo uma pendência por thread: a direção da última mensagem é atualizada
    # pelo sync de e-mail, então uma resposta do André fecha a thread inteira.
    emails_by_thread = {}
    for doc in _applied_email_suggestions(db):
        data = doc.to_dict() or {}
        task = by_email.get(doc.id) or by_id.get(str(data.get("task_id") or ""))
        if not task or str(data.get("canal") or "") != "email":
            continue
        if not str(data.get("status") or "").startswith("applied"):
            continue
        key = str(data.get("gmail_thread_id") or doc.id)
        current = emails_by_thread.get(key)
        if current is None or (_as_datetime(data.get("internal_date")) or datetime.min.replace(tzinfo=timezone.utc)) > current[0]:
            emails_by_thread[key] = (_as_datetime(data.get("internal_date")) or datetime.min.replace(tzinfo=timezone.utc), doc, data, task)

    for _, doc, data, task in emails_by_thread.values():
        if data.get("ultima_mensagem_de_andre"):
            continue
        reason = _noise_reason(trecho=data.get("snippet") or data.get("resumo") or "", sender=data.get("sender") or "",
                               is_email=True, has_contact=False, has_task=bool(task), domains=domains, endings=endings)
        if reason and not incluir_filtrados:
            filtered[reason] += 1
            continue
        item = _item(
            contato=str(data.get("sender") or data.get("origem_sinal") or "E-mail"),
            canal="gmail", desde=data.get("internal_date") or data.get("analyzed_at"),
            trecho=str(data.get("snippet") or data.get("resumo") or ""), task=task,
            paused_until=None, now=now,
        )
        if item:
            item["motivo_inclusao"] = "conversa_direta"
            items.append(item)

    items.sort(key=lambda item: (not item.pop("_critica"), -item["horas_aguardando"], item["desde"]))
    limite = max(1, min(int(limite or MAX_ITEMS), 100))
    omitted = max(0, len(items) - limite)
    result = {"itens": items[:limite], "filtrados": filtered}
    if omitted:
        result["total_omitido"] = omitted
    return result
