"""
Vincula e-mails recebidos a ações (tarefas) em andamento/stand-by via IA,
propondo confirmação por Telegram e registro no diário de bordo.

Toda sugestão passa por confirmação humana (Telegram ou fila web em
DashboardView.tsx) antes de tocar em uma tarefa — a classificação vem de
conteúdo controlado pelo remetente do e-mail, então não é tratada como
sinal confiável o suficiente para agir sozinha.

Schema da coleção `email_action_suggestions`: docs/okf/arquitetura/schema-firestore.md
Mapa de onde esta função é chamada: docs/okf/arquitetura/cloud-functions.md
"""

import base64
import json
from datetime import datetime, timedelta, timezone

from gemini_cost_controls import GEMINI_LIGHT_MODEL, generate_content_logged

FEATURE_NAME = "email_action_linker"

DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_MAX_LLM_CALLS_PER_PASS = 10
DEFAULT_MAX_SUGGESTIONS_PER_PASS = 5
DEFAULT_LOOKBACK = "2d"
EXPIRE_AFTER_DAYS = 7
GMAIL_QUERY_MAX_RESULTS = 20
GMAIL_MAX_PAGES_PER_PASS = 5

# Classificações de e-mail são geradas por um LLM a partir de conteúdo controlado
# pelo remetente (assunto/corpo do e-mail) — não são um sinal confiável o suficiente
# para agir sem confirmação humana (um e-mail malicioso poderia tentar instruir o
# modelo a escolher uma ação e reportar confiança alta). Por isso não existe
# auto-aplicação: toda sugestão "related" sempre passa por confirmação manual
# (Telegram ou fila web), independente da confiança relatada pelo modelo.

# Mesma tolerância a variantes de status usada no frontend (isStandbyStatus,
# src/utils/helpers.tsx) e no matching lexical de ações (busca_grafo.py).
_STANDBY_STATUS_ALIASES = {"stand-by", "standby", "stand by", "cgby"}
_ACTIVE_STATUS_ALIASES = {"em andamento", "andamento", "nao iniciado", "não iniciado", "pendente"}


def _normalize_status(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _is_standby(status_norm: str) -> bool:
    return status_norm in _STANDBY_STATUS_ALIASES


def _is_candidate_status(status_norm: str) -> bool:
    return status_norm in _STANDBY_STATUS_ALIASES or status_norm in _ACTIVE_STATUS_ALIASES


def _load_settings(db) -> dict:
    from main import _cached_doc_get

    doc = _cached_doc_get(db, "system", "settings")
    cfg = ((doc.to_dict() or {}) if doc.exists else {}).get("email_action_linker") or {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "min_confidence": float(cfg.get("min_confidence", DEFAULT_MIN_CONFIDENCE)),
        "max_llm_calls_per_pass": int(cfg.get("max_llm_calls_per_pass", DEFAULT_MAX_LLM_CALLS_PER_PASS)),
        "max_suggestions_per_pass": int(cfg.get("max_suggestions_per_pass", DEFAULT_MAX_SUGGESTIONS_PER_PASS)),
        "lookback": str(cfg.get("lookback", DEFAULT_LOOKBACK)),
    }


def _load_candidate_tasks(db) -> list[dict]:
    candidates = []
    for doc in db.collection("tarefas").stream():
        data = doc.to_dict() or {}
        if data.get("email_link_optout"):
            continue
        status_norm = _normalize_status(data.get("status"))
        if not _is_candidate_status(status_norm):
            continue
        acompanhamento = data.get("acompanhamento") or []
        recentes = [
            (entry.get("nota") or "")[:200]
            for entry in acompanhamento[-2:]
            if isinstance(entry, dict)
        ]
        candidates.append({
            "id": doc.id,
            "titulo": (data.get("titulo") or "(sem título)").strip(),
            "projeto": (data.get("projeto") or "").strip(),
            "area_tematica": (data.get("area_tematica") or "").strip(),
            "tags": data.get("tags") or [],
            "status": data.get("status") or "",
            "is_standby": _is_standby(status_norm),
            "notas": (data.get("notas") or "").strip()[:300],
            "acompanhamento_recente": recentes,
        })
    return candidates


def _format_candidates_for_prompt(candidates: list[dict]) -> str:
    lines = []
    for c in candidates:
        bits = [f"id={c['id']}", f'título="{c["titulo"]}"', f"status={c['status']}"]
        if c["projeto"]:
            bits.append(f"projeto={c['projeto']}")
        if c["area_tematica"]:
            bits.append(f"área={c['area_tematica']}")
        if c["tags"]:
            bits.append(f"tags={', '.join(c['tags'][:6])}")
        if c["notas"]:
            bits.append(f'notas="{c["notas"]}"')
        if c["acompanhamento_recente"]:
            bits.append('último registro no diário="' + " | ".join(c["acompanhamento_recente"]) + '"')
        lines.append("- " + "; ".join(bits))
    return "\n".join(lines)


def _extract_email_body(payload: dict) -> str:
    text_parts, html_parts = [], []

    def walk(part):
        mime_type = part.get("mimeType")
        body = part.get("body") or {}
        data = body.get("data")
        if data:
            try:
                decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
            except Exception:
                decoded = ""
            if decoded and mime_type == "text/plain":
                text_parts.append(decoded)
            elif decoded and mime_type == "text/html":
                html_parts.append(decoded)
        for sub_part in part.get("parts") or []:
            walk(sub_part)

    walk(payload or {})

    if text_parts:
        body = "\n".join(text_parts)
    elif html_parts:
        try:
            import html2text

            h = html2text.HTML2Text()
            h.ignore_links = True
            h.ignore_images = True
            h.body_width = 0
            body = "\n".join(h.handle(part) for part in html_parts)
        except Exception:
            body = ""
    else:
        body = ""

    body = "\n".join(line for line in body.split("\n") if line.strip())
    return body[:4000]


def _build_prompt(sender: str, subject: str, body: str, snippet: str, candidates_text: str) -> str:
    return f"""
Você é o Hermes, assistente pessoal que administra as ações (tarefas) do usuário.
Analise o e-mail abaixo e decida se ele tem relação direta com alguma das ações
ativas listadas. Só aponte relação quando houver um vínculo claro e específico
(mesmo assunto, mesma contraparte, mesmo processo/projeto) — na dúvida, prefira
dizer que não há relação.

AÇÕES ATIVAS DO USUÁRIO:
{candidates_text or "(nenhuma ação ativa no momento)"}

E-MAIL RECEBIDO:
De: {sender}
Assunto: {subject}
Corpo:
{body or snippet}

Responda APENAS com um JSON no formato exato:
{{
  "related": true|false,
  "task_id": "id da ação mais provável, ou null se related=false",
  "confidence": 0.0 a 1.0,
  "resumo": "1 a 3 frases (português) do que este e-mail significa PARA ESSA AÇÃO",
  "nota_sugerida": "nota curta e objetiva para o diário de bordo da ação",
  "reativar_sugerido": true|false
}}

Regras:
- "task_id" deve ser exatamente um dos IDs listados acima, ou null.
- "reativar_sugerido" só pode ser true se a ação correspondente estiver com status "stand-by"
  e o e-mail for um evento que justifique retomar o trabalho nela.
- Se não houver relação clara com nenhuma ação, responda {{"related": false, "task_id": null,
  "confidence": 0.0, "resumo": "", "nota_sugerida": "", "reativar_sugerido": false}}.
"""


def _analyze_email(client, db, sender: str, subject: str, body: str, snippet: str, candidates_text: str) -> dict:
    from google.genai import types

    prompt = _build_prompt(sender, subject, body, snippet, candidates_text)
    response = generate_content_logged(
        client,
        model=GEMINI_LIGHT_MODEL,
        contents=prompt,
        feature=FEATURE_NAME,
        db=db,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )
    raw = (response.text or "").strip()
    if "```json" in raw:
        raw = raw.split("```json")[-1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[-1].split("```")[0].strip()
    return json.loads(raw)


def _build_suggestion_message(data: dict) -> str:
    sender = data.get("sender") or "Desconhecido"
    subject = data.get("subject") or "(sem assunto)"
    task_titulo = data.get("task_titulo") or "(ação)"
    task_status = data.get("task_status") or ""
    resumo = data.get("resumo") or ""
    nota = data.get("nota_sugerida") or ""

    lines = [
        "📧 E-mail relacionado a uma ação",
        "",
        f"De: {sender}",
        f"Assunto: {subject}",
        "",
        f"Ação: {task_titulo} ({task_status})" if task_status else f"Ação: {task_titulo}",
    ]
    if resumo:
        lines.append(resumo)
    if nota:
        lines.append("")
        lines.append("Nota proposta para o diário:")
        lines.append(f'"{nota}"')
    return "\n".join(lines)


def _build_suggestion_keyboard(msg_id: str, reativar_sugerido: bool) -> list:
    top_row = [{"text": "✅ Registrar no diário", "callback_data": f"emlink:{msg_id}:ok"}]
    if reativar_sugerido:
        top_row = [{"text": "🔄 Registrar + reativar", "callback_data": f"emlink:{msg_id}:on"}] + top_row
    return [top_row, [{"text": "❌ Ignorar", "callback_data": f"emlink:{msg_id}:no"}]]


def _send_email_suggestion_telegram(db, chat_id, msg_id: str, data: dict, send_fn) -> bool:
    text = _build_suggestion_message(data)
    keyboard = _build_suggestion_keyboard(msg_id, bool(data.get("reativar_sugerido")))
    return bool(send_fn(db, chat_id, text, keyboard))


def _build_email_diary_note(msg_id: str, data: dict) -> str:
    """
    Serializa a nota no mesmo formato rico `EMAIL::JSON::{...}` que o frontend
    entende nativamente (ver src/utils/diaryEntries.ts, buildDiaryEmailNote),
    para que o DiarioBordoUI renderize um chip em vez de texto cru.
    """
    gmail_link = f"https://mail.google.com/mail/u/0/#all/{msg_id}"
    payload = {
        "n": str(data.get("subject") or "(sem assunto)"),
        "v": gmail_link,
        "s": str(data.get("sender") or ""),
        "r": str(data.get("resumo") or "").strip(),
    }
    return "EMAIL::JSON::" + json.dumps(payload, ensure_ascii=False)


def apply_suggestion(db, msg_id: str, data: dict, reactivate: bool) -> bool:
    """
    Confirma a ação de um usuário sobre uma sugestão `pending` (via Telegram
    ou fila web): grava a entrada no diário de bordo da ação vinculada (e
    opcionalmente reativa uma ação em stand-by) e marca a sugestão como
    aplicada — tudo dentro de uma única transação Firestore.

    A atomicidade importa por dois motivos: (1) evita que uma falha parcial
    (nota gravada na tarefa, mas a atualização do doc de sugestão falha)
    deixe a sugestão presa em "pending" — o que faria uma nova tentativa
    duplicar a entrada no diário, já que cada nota carrega um timestamp novo
    e `ArrayUnion` não deduplica por conteúdo; e (2) o `get` da sugestão
    dentro da transação recusa aplicar duas vezes a mesma sugestão em caso de
    corrida (ex.: duplo toque no botão do Telegram, ou Telegram e fila web
    decidindo ao mesmo tempo).
    """
    from firebase_admin import firestore

    task_id = data.get("task_id")
    if not task_id:
        return False

    task_ref = db.collection("tarefas").document(task_id)
    suggestion_ref = db.collection("email_action_suggestions").document(msg_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    entry = {"data": now_iso, "nota": _build_email_diary_note(msg_id, data)}
    new_status = "applied_reactivated" if reactivate else "applied"

    transaction = db.transaction()

    @firestore.transactional
    def _run(transaction):
        suggestion_snap = suggestion_ref.get(transaction=transaction)
        if not suggestion_snap.exists or (suggestion_snap.to_dict() or {}).get("status") != "pending":
            return False
        task_snap = task_ref.get(transaction=transaction)
        if not task_snap.exists:
            return False

        task_updates = {"acompanhamento": firestore.ArrayUnion([entry]), "data_atualizacao": now_iso}
        if reactivate:
            task_updates["status"] = "em andamento"
            task_updates["data_conclusao"] = None
        transaction.update(task_ref, task_updates)
        transaction.update(suggestion_ref, {
            "status": new_status,
            "applied_at": now_iso,
            "decided_at": now_iso,
        })
        return True

    return _run(transaction)


def _collect_fresh_message_ids(service, query: str, needed: int, suggestions_col) -> list[str]:
    """
    Pagina os resultados do Gmail (via `nextPageToken`) até reunir `needed`
    mensagens que ainda não têm doc em `email_action_suggestions`, respeitando
    um teto de páginas por passada (`GMAIL_MAX_PAGES_PER_PASS`) para não deixar
    o custo de API do Gmail crescer sem limite numa caixa muito cheia.

    Sem paginação, uma caixa com mais de `GMAIL_QUERY_MAX_RESULTS` mensagens
    novas na janela de `lookback` nunca teria as mensagens além da primeira
    página analisadas: a query (mais recentes primeiro) sempre traz o mesmo
    topo, essas já têm doc de sugestão, e as mais antigas só seriam
    alcançadas se a janela de `lookback` não as tivesse excluído antes.
    """
    fresh_ids: list[str] = []
    page_token = None
    for _ in range(GMAIL_MAX_PAGES_PER_PASS):
        request = service.users().messages().list(
            userId='me', q=query, maxResults=GMAIL_QUERY_MAX_RESULTS, pageToken=page_token
        )
        results = request.execute(num_retries=3)
        for m_info in results.get('messages', []) or []:
            msg_id = m_info['id']
            if suggestions_col.document(msg_id).get().exists:
                continue
            fresh_ids.append(msg_id)
            if len(fresh_ids) >= needed:
                return fresh_ids
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return fresh_ids


def link_emails_to_actions(db, service, sync_ref, logs):
    """
    Analisa e-mails recentes da caixa de entrada em busca de relação com ações
    em andamento/stand-by; propõe atualização e registro no diário via Telegram.
    Protegido internamente para nunca interromper o restante do `run_full_sync`.
    """
    from main import (
        _cached_doc_get,
        _gmail_message_headers,
        _resolve_default_telegram_chat_id,
        _send_telegram_message_raw_with_keyboard,
        get_genai_module,
        log_to_firestore,
    )

    settings = _load_settings(db)
    if not settings["enabled"]:
        return

    log_to_firestore(sync_ref, logs, "[EMAIL-LINK] Verificando e-mails relacionados a ações...", True)

    suggestions_col = db.collection("email_action_suggestions")
    chat_id = _resolve_default_telegram_chat_id(db)
    now = datetime.now(timezone.utc)
    sent_this_pass = 0

    # --- Etapa A: escoa sugestões pendentes que não couberam no teto de uma passada anterior,
    # e expira sugestões já enviadas há mais de EXPIRE_AFTER_DAYS sem resposta.
    try:
        backlog = list(suggestions_col.where("status", "==", "pending").stream())
    except Exception as exc:
        backlog = []
        log_to_firestore(sync_ref, logs, f"[EMAIL-LINK][ERRO] Falha ao consultar backlog de sugestões: {exc}", True)

    for doc in backlog:
        data = doc.to_dict() or {}
        if data.get("telegram_sent"):
            try:
                analyzed_at = datetime.fromisoformat(str(data.get("analyzed_at")))
                if analyzed_at.tzinfo is None:
                    analyzed_at = analyzed_at.replace(tzinfo=timezone.utc)
                if (now - analyzed_at) > timedelta(days=EXPIRE_AFTER_DAYS):
                    doc.reference.update({"status": "expired"})
            except Exception:
                pass
            continue
        if sent_this_pass >= settings["max_suggestions_per_pass"]:
            continue
        if chat_id and _send_email_suggestion_telegram(db, chat_id, doc.id, data, _send_telegram_message_raw_with_keyboard):
            doc.reference.update({"telegram_sent": True, "sent_at": now.isoformat()})
            sent_this_pass += 1

    # --- Etapa B: analisa e-mails novos ---
    query = f'in:inbox newer_than:{settings["lookback"]} -category:promotions -category:social'
    try:
        fresh_message_ids = _collect_fresh_message_ids(service, query, settings["max_llm_calls_per_pass"], suggestions_col)
    except Exception as exc:
        log_to_firestore(sync_ref, logs, f"[EMAIL-LINK][ERRO] Falha ao listar e-mails: {exc}", True)
        return

    if not fresh_message_ids:
        log_to_firestore(sync_ref, logs, "[EMAIL-LINK] Nenhum e-mail novo para analisar.", True)
        return

    candidates = _load_candidate_tasks(db)
    if not candidates:
        log_to_firestore(sync_ref, logs, "[EMAIL-LINK] Nenhuma ação ativa/stand-by elegível; nada a vincular.", True)
        return
    candidates_text = _format_candidates_for_prompt(candidates)
    candidates_by_id = {c["id"]: c for c in candidates}

    keys_doc = _cached_doc_get(db, 'system', 'api_keys')
    api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
    if not api_key:
        log_to_firestore(sync_ref, logs, "[EMAIL-LINK][ERRO] Gemini API Key não configurada (system/api_keys).", True)
        return

    genai = get_genai_module()
    client = genai.Client(api_key=api_key)

    analyzed = 0

    for msg_id in fresh_message_ids:
        try:
            msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute(num_retries=3)
        except Exception as exc:
            log_to_firestore(sync_ref, logs, f"[EMAIL-LINK][!] Falha ao buscar e-mail {msg_id}: {exc}", True)
            continue

        sender, subject = _gmail_message_headers(msg)
        snippet = msg.get('snippet', '')
        body = _extract_email_body(msg.get('payload', {}))

        try:
            analysis = _analyze_email(client, db, sender, subject, body, snippet, candidates_text)
        except Exception as exc:
            log_to_firestore(sync_ref, logs, f"[EMAIL-LINK][!] Falha na análise IA do e-mail {msg_id}: {exc}", True)
            continue

        analyzed += 1
        related = bool(analysis.get("related"))
        task_id = analysis.get("task_id")
        try:
            confidence = max(0.0, min(1.0, float(analysis.get("confidence") or 0.0)))
        except Exception:
            confidence = 0.0

        base_doc = {
            "google_message_id": msg_id,
            "subject": subject,
            "sender": sender,
            "snippet": snippet,
            "internal_date": msg.get('internalDate'),
            "analyzed_at": now.isoformat(),
            "model": GEMINI_LIGHT_MODEL,
            "related": related,
            "confidence": confidence,
        }

        if not related or not task_id or task_id not in candidates_by_id or confidence < settings["min_confidence"]:
            base_doc["status"] = "no_match"
            suggestions_col.document(msg_id).set(base_doc)
            continue

        task = candidates_by_id[task_id]
        reativar_sugerido = bool(analysis.get("reativar_sugerido")) and task["is_standby"]
        base_doc.update({
            "task_id": task_id,
            "task_titulo": task["titulo"],
            "task_status": task["status"],
            "resumo": str(analysis.get("resumo") or "").strip(),
            "nota_sugerida": str(analysis.get("nota_sugerida") or "").strip(),
            "reativar_sugerido": reativar_sugerido,
            "status": "pending",
            "telegram_sent": False,
        })
        suggestions_col.document(msg_id).set(base_doc)

        if sent_this_pass >= settings["max_suggestions_per_pass"]:
            continue
        if chat_id and _send_email_suggestion_telegram(db, chat_id, msg_id, base_doc, _send_telegram_message_raw_with_keyboard):
            suggestions_col.document(msg_id).update({"telegram_sent": True, "sent_at": now.isoformat()})
            sent_this_pass += 1

    if analyzed:
        log_to_firestore(sync_ref, logs, f"[EMAIL-LINK] {analyzed} e-mail(is) analisado(s).", True)
