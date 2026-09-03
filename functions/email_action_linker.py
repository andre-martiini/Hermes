"""
Motor compartilhado de vínculo sinal↔ação: qualquer canal (e-mail, SIPAC,
Calendar, WhatsApp, Monitor de Páginas, ...) pode propor que um evento se
relaciona a uma ação (tarefa) em andamento/stand-by, via cartão de
confirmação no Telegram (ou na fila web em DashboardView.tsx) que grava a
nota no diário de bordo e opcionalmente reativa a ação.

O nome do arquivo é histórico — nasceu só para e-mail (`link_emails_to_actions`,
ainda o único produtor que analisa o sinal com IA) — mas `queue_and_maybe_send_suggestion`
e `apply_suggestion` são genéricos e usados por todos os produtores. A coleção
`email_action_suggestions` também manteve o nome histórico.

Toda sugestão passa por confirmação humana antes de tocar numa tarefa. Para
o produtor de e-mail isso é especialmente importante: a classificação vem de
conteúdo controlado pelo remetente do e-mail, então não é tratada como sinal
confiável o suficiente para agir sozinha. Produtores com matching determinístico
(SIPAC por número de processo, Calendar por ID do evento) não têm esse risco,
mas mesmo assim pedem confirmação — o objetivo é registro no diário, não
automação silenciosa.

Schema da coleção: docs/okf/arquitetura/schema-firestore.md
Mapa de onde cada produtor é chamado: docs/okf/arquitetura/cloud-functions.md
"""

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from gemini_cost_controls import GEMINI_LIGHT_MODEL, generate_content_logged

FEATURE_NAME = "email_action_linker"

DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_MAX_LLM_CALLS_PER_PASS = 10
DEFAULT_MAX_SUGGESTIONS_PER_PASS = 5
DEFAULT_LOOKBACK = "2d"
EXPIRE_AFTER_DAYS = 7
GMAIL_QUERY_MAX_RESULTS = 20
GMAIL_MAX_PAGES_PER_PASS = 5
DEFAULT_IGNORED_SENDERS = ["notifications@github.com", "@github.com"]


def is_sender_ignored(sender_raw: str | None, ignored_patterns: list[str]) -> bool:
    """Verifica de forma determinística se um remetente deve ser ignorado.
    Casa endereço de e-mail (via parseaddr), domínio (ex. @github.com) ou texto do remetente.
    """
    if not sender_raw or not ignored_patterns:
        return False
    raw_lower = str(sender_raw).strip().lower()
    from email.utils import parseaddr
    _, addr = parseaddr(sender_raw)
    addr_lower = addr.strip().lower()
    for pattern in ignored_patterns:
        p = str(pattern).strip().lower()
        if not p:
            continue
        if p in addr_lower or p in raw_lower:
            return True
    return False

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
    ignored_raw = cfg.get("ignored_senders")
    if ignored_raw is None:
        ignored_senders = list(DEFAULT_IGNORED_SENDERS)
    else:
        ignored_senders = [str(x).strip().lower() for x in ignored_raw if str(x).strip()]
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "min_confidence": float(cfg.get("min_confidence", DEFAULT_MIN_CONFIDENCE)),
        "max_llm_calls_per_pass": int(cfg.get("max_llm_calls_per_pass", DEFAULT_MAX_LLM_CALLS_PER_PASS)),
        "max_suggestions_per_pass": int(cfg.get("max_suggestions_per_pass", DEFAULT_MAX_SUGGESTIONS_PER_PASS)),
        "lookback": str(cfg.get("lookback", DEFAULT_LOOKBACK)),
        "ignored_senders": ignored_senders,
    }


def _build_candidate(doc_id: str, data: dict) -> dict | None:
    if data.get("email_link_optout"):
        return None
    status_norm = _normalize_status(data.get("status"))
    if not _is_candidate_status(status_norm):
        return None
    acompanhamento = data.get("acompanhamento") or []
    recentes = [
        (entry.get("nota") or "")[:200]
        for entry in acompanhamento[-2:]
        if isinstance(entry, dict)
    ]
    return {
        "id": doc_id,
        "titulo": (data.get("titulo") or "(sem título)").strip(),
        "projeto": (data.get("projeto") or "").strip(),
        "area_tematica": (data.get("area_tematica") or "").strip(),
        "tags": data.get("tags") or [],
        "status": data.get("status") or "",
        "is_standby": _is_standby(status_norm),
        "notas": (data.get("notas") or "").strip()[:300],
        "acompanhamento_recente": recentes,
        # Chaves de matching determinístico usadas pelos produtores sem IA
        # (SIPAC por número de processo, Calendar por ID do evento) e pela
        # pré-filtragem de candidatos do WhatsApp por chat vinculado manualmente
        # (ver whatsapp_ingest.py:triage_whatsapp_messages).
        "processo_sei": (data.get("processo_sei") or "").strip(),
        "google_calendar_id": (data.get("google_calendar_id") or "").strip(),
        "whatsapp_chat_ids": [
            str(v.get("chat_id") or "").strip()
            for v in (data.get("whatsapp_vinculos") or [])
            if isinstance(v, dict) and str(v.get("chat_id") or "").strip()
        ],
    }


def _load_candidate_tasks(db) -> list[dict]:
    candidates = []
    for doc in db.collection("tarefas").stream():
        candidate = _build_candidate(doc.id, doc.to_dict() or {})
        if candidate:
            candidates.append(candidate)
    return candidates


def _load_candidate_task_by_id(db, task_id: str) -> dict | None:
    """Busca uma única candidata por ID — usado por produtores que já sabem
    a qual ação um sinal se refere (ex.: Monitor de Páginas com task_id salvo)."""
    if not task_id:
        return None
    doc = db.collection("tarefas").document(task_id).get()
    if not doc.exists:
        return None
    return _build_candidate(doc.id, doc.to_dict() or {})


def _normalize_digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


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


_CANAL_ICONS = {"email": "📧", "whatsapp": "📱", "sipac": "📋", "calendar": "📅", "pagina": "🌐"}
_CANAL_LABELS = {
    "email": "E-mail",
    "whatsapp": "Conversa de WhatsApp",
    "sipac": "Processo SIPAC",
    "calendar": "Reunião",
    "pagina": "Página monitorada",
}


def _signal_title(data: dict) -> str:
    return str(data.get("titulo_sinal") or data.get("subject") or "(sem título)")


def _signal_origin(data: dict) -> str:
    return str(data.get("origem_sinal") or data.get("sender") or "")


def _build_suggestion_message(data: dict) -> str:
    canal = data.get("canal") or "email"
    icon = _CANAL_ICONS.get(canal, "🔔")
    label = _CANAL_LABELS.get(canal, "Sinal")
    titulo_sinal = _signal_title(data)
    origem_sinal = _signal_origin(data)
    task_titulo = data.get("task_titulo") or "(ação)"
    task_status = data.get("task_status") or ""
    resumo = data.get("resumo") or ""
    nota = data.get("nota_sugerida") or ""

    # Calendar é um caso à parte: o evento só existe porque o próprio Hermes o criou a
    # partir do horário da própria ação (tarefas.google_calendar_id só é preenchido nesse
    # sentido — ver link_calendar_events_to_actions) — não há incerteza nem "descoberta"
    # de relação, é sempre a mesma ação, com certeza. A mensagem evita fingir uma
    # correlação encontrada; só avisa que o compromisso já agendado terminou.
    if canal == "calendar":
        lines = [f"{icon} A reunião da ação abaixo terminou", ""]
    else:
        lines = [f"{icon} {label} relacionado(a) a uma ação", ""]
    if canal == "email":
        lines.append(f"De: {origem_sinal or 'Desconhecido'}")
        lines.append(f"Assunto: {titulo_sinal}")
    else:
        lines.append(titulo_sinal)
        if origem_sinal:
            lines.append(origem_sinal)
    lines.append("")
    lines.append(f"Ação: {task_titulo} ({task_status})" if task_status else f"Ação: {task_titulo}")
    if resumo:
        lines.append(resumo)

    # Elementos executivos extraídos pelo produtor (hoje só WhatsApp, ver
    # whatsapp_ingest.py) — o que torna o cartão de confirmação acionável em
    # vez de um resumo solto: itens de ação, pontos de decisão (auditoria) e
    # a mudança concreta que será aplicada na ação se confirmada.
    itens_de_acao = data.get("itens_de_acao") or []
    if itens_de_acao:
        lines.append("")
        lines.append("📌 Itens de ação:")
        for item in itens_de_acao[:5]:
            desc = item.get("descricao") if isinstance(item, dict) else str(item)
            resp = item.get("responsavel") if isinstance(item, dict) else None
            prazo = item.get("prazo") if isinstance(item, dict) else None
            bit = f"• {desc}"
            extras = [x for x in (resp, f"prazo {prazo}" if prazo else None) if x]
            if extras:
                bit += f" ({', '.join(extras)})"
            lines.append(bit)

    decisoes = data.get("decisoes") or []
    if decisoes:
        lines.append("")
        lines.append("🧭 Decisões / pontos de auditoria:")
        for d in decisoes[:5]:
            lines.append(f"• {d}")

    mutacoes = data.get("mutacoes_propostas") or {}
    mutacoes_desc = _describe_mutations(mutacoes)
    if mutacoes_desc:
        lines.append("")
        lines.append("🛠️ Mudança sugerida na ação:")
        for m in mutacoes_desc:
            lines.append(f"• {m}")

    if nota:
        lines.append("")
        lines.append("Nota proposta para o diário:")
        lines.append(f'"{nota}"')
    return "\n".join(lines)


def _describe_mutations(mutacoes: dict | None) -> list[str]:
    """Traduz `mutacoes_propostas` em frases curtas para o cartão de confirmação
    e para registrar no diário o que de fato foi aplicado (ver apply_suggestion)."""
    if not mutacoes:
        return []
    out = []
    novas_etapas = mutacoes.get("novas_etapas") or []
    if novas_etapas:
        out.append(f"+{len(novas_etapas)} etapa(s) no plano de ação")
    nova_data_limite = mutacoes.get("nova_data_limite")
    if nova_data_limite:
        out.append(f"Prazo ajustado para {nova_data_limite}")
    lembrete = mutacoes.get("lembrete_sugerido") or {}
    if lembrete.get("data"):
        out.append(f"Lembrete criado para {lembrete['data']}")
    return out


def _build_suggestion_keyboard(msg_id: str, reativar_sugerido: bool, tem_mutacoes: bool = False) -> list:
    # O prefixo "emlink" é histórico (nasceu só para e-mail); hoje é o callback
    # genérico de confirmação de vínculo sinal↔ação usado por todos os canais.
    top_row = [{"text": "✅ Registrar no diário", "callback_data": f"emlink:{msg_id}:ok"}]
    if reativar_sugerido:
        top_row = [{"text": "🔄 Registrar + reativar", "callback_data": f"emlink:{msg_id}:on"}] + top_row
    rows = [top_row]
    if tem_mutacoes:
        # "mut" registra a nota E aplica as mutações propostas (novas etapas no plano,
        # ajuste de prazo, lembrete) — e também reativa se `reativar_sugerido` for true,
        # para não obrigar duas confirmações separadas quando ambas fazem sentido juntas.
        rows.append([{"text": "📋 Registrar + aplicar mudanças", "callback_data": f"emlink:{msg_id}:mut"}])
    rows.append([{"text": "❌ Ignorar", "callback_data": f"emlink:{msg_id}:no"}])
    return rows


def _send_suggestion_telegram(db, chat_id, msg_id: str, data: dict, send_fn) -> bool:
    text = _build_suggestion_message(data)
    keyboard = _build_suggestion_keyboard(
        msg_id,
        bool(data.get("reativar_sugerido")),
        bool(data.get("mutacoes_propostas")),
    )
    return bool(send_fn(db, chat_id, text, keyboard))


# Retrocompat: nome antigo usado por chamadores já escritos antes da generalização multi-canal.
_send_email_suggestion_telegram = _send_suggestion_telegram


def _build_diary_note(msg_id: str, data: dict, mutacoes_aplicadas: list[str] | None = None) -> str:
    """
    Para e-mail e WhatsApp, serializa a nota no formato rico `TIPO::JSON::{...}`
    que o frontend entende nativamente (ver src/utils/diaryEntries.ts) para que
    o DiarioBordoUI renderize um chip. Para os demais canais usa texto simples —
    estender o envelope rico a cada canal fica para quando fizer sentido, não é
    essencial para o valor do vínculo.

    `mutacoes_aplicadas` (frases de _describe_mutations) documenta no próprio
    registro do diário o que de fato mudou na ação, quando `apply_suggestion`
    aplicou as mutações propostas — sem isso a auditoria da mudança ficaria só
    no doc de sugestão, que não é visível na tela da ação.
    """
    canal = data.get("canal") or "email"
    resumo = str(data.get("resumo") or "").strip()

    if canal == "email":
        gmail_link = f"https://mail.google.com/mail/u/0/#all/{msg_id}"
        payload = {
            "n": _signal_title(data) or "(sem assunto)",
            "v": gmail_link,
            "s": _signal_origin(data),
            "r": resumo,
        }
        return "EMAIL::JSON::" + json.dumps(payload, ensure_ascii=False)

    if canal == "whatsapp":
        payload = {
            "n": _signal_title(data) or "(conversa)",
            "v": "",
            "s": _signal_origin(data),
            "r": resumo,
            "itens": data.get("itens_de_acao") or [],
            "decisoes": data.get("decisoes") or [],
            "periodo_inicio": data.get("periodo_inicio") or "",
            "periodo_fim": data.get("periodo_fim") or "",
            "mutacoes_aplicadas": mutacoes_aplicadas or [],
        }
        return "WHATSAPP::JSON::" + json.dumps(payload, ensure_ascii=False)

    icon = _CANAL_ICONS.get(canal, "🔔")
    label = _CANAL_LABELS.get(canal, "Sinal")
    lines = [f"[{icon} Hermes] {label}: {_signal_title(data)}"]
    origem_sinal = _signal_origin(data)
    if origem_sinal:
        lines.append(origem_sinal)
    if resumo:
        lines.append(resumo)
    link_externo = data.get("link_externo")
    if link_externo:
        lines.append(f"Link: {link_externo}")
    if mutacoes_aplicadas:
        lines.append("")
        lines.append("Alterações aplicadas na ação:")
        for m in mutacoes_aplicadas:
            lines.append(f"• {m}")
    return "\n".join(lines)


def apply_suggestion(db, msg_id: str, data: dict, reactivate: bool, apply_mutations: bool = False) -> bool:
    """
    Confirma a ação de um usuário sobre uma sugestão `pending` (via Telegram
    ou fila web): grava a entrada no diário de bordo da ação vinculada,
    opcionalmente reativa uma ação em stand-by e, se `apply_mutations` (botão
    "Registrar + aplicar mudanças"), aplica as `mutacoes_propostas` extraídas
    na triagem — novas etapas em `plano_acao`, ajuste de `data_limite` e/ou um
    novo lembrete — tudo dentro de uma única transação Firestore. Marca a
    sugestão como aplicada.

    `apply_mutations` só tem efeito quando a sugestão de fato carrega
    `mutacoes_propostas` (hoje só o produtor de WhatsApp gera isso); para os
    demais canais o parâmetro é um no-op silencioso.

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
    from main import _normalize_task_reminders, _build_task_reminder_state_payload

    task_id = data.get("task_id")
    if not task_id:
        return False

    task_ref = db.collection("tarefas").document(task_id)
    suggestion_ref = db.collection("email_action_suggestions").document(msg_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    mutacoes = data.get("mutacoes_propostas") if apply_mutations else None
    entry = {"data": now_iso, "nota": _build_diary_note(msg_id, data, _describe_mutations(mutacoes))}
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
        task_data = task_snap.to_dict() or {}

        if mutacoes:
            novas_etapas = mutacoes.get("novas_etapas") or []
            if novas_etapas:
                plano_atual = task_data.get("plano_acao") or []
                novos_itens = [{"id": str(uuid.uuid4())[:8], "text": texto, "completed": False} for texto in novas_etapas]
                task_updates["plano_acao"] = [*plano_atual, *novos_itens]

            nova_data_limite = mutacoes.get("nova_data_limite")
            if nova_data_limite:
                task_updates["data_limite"] = nova_data_limite

            lembrete = mutacoes.get("lembrete_sugerido") or {}
            if lembrete.get("data"):
                reminders = _normalize_task_reminders(task_data)
                reminders.append({
                    "id": str(uuid.uuid4())[:12],
                    "reminder_at": f"{lembrete['data']}T09:00:00",
                    "reminder_sent": False,
                    "created_at": now_iso,
                    "message": str(lembrete.get("texto") or ""),
                })
                task_updates.update(_build_task_reminder_state_payload(reminders))

        if reactivate:
            task_updates["status"] = "em andamento"
            task_updates["data_conclusao"] = None
            # Toda ação "em andamento" precisa necessariamente de uma data (mesma regra
            # aplicada no frontend por applyStandbyDateRules, src/utils/helpers.tsx) —
            # sem isso a reativação automática via sinal (e-mail/WhatsApp) deixava a
            # ação em limbo: status ativo mas sem data, fora do fluxo de Hoje/Amanhã.
            data_atual = task_updates.get("data_limite") or task_data.get("data_limite")
            if not data_atual or data_atual in ("-", "0000-00-00"):
                hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
                task_updates["data_limite"] = hoje
                task_updates["data_inicio"] = hoje
        transaction.update(task_ref, task_updates)
        transaction.update(suggestion_ref, {
            "status": new_status,
            "applied_at": now_iso,
            "decided_at": now_iso,
        })
        return True

    return _run(transaction)


def queue_and_maybe_send_suggestion(
    db,
    suggestion_id: str,
    *,
    canal: str,
    task: dict,
    titulo_sinal: str,
    origem_sinal: str = "",
    resumo: str = "",
    nota_sugerida: str = "",
    reativar_sugerido: bool = False,
    confidence: float = 1.0,
    chat_id=None,
    send_fn=None,
    extra: dict | None = None,
) -> dict:
    """
    Ponto de entrada compartilhado para qualquer produtor de sinal (SIPAC,
    Calendar, WhatsApp, Monitor de Páginas, ...) propor um vínculo sinal↔ação:
    grava a sugestão `pending` e, se houver `chat_id`, tenta enviar o cartão
    de confirmação imediatamente. Idempotente por `suggestion_id` — chame com
    um ID determinístico e estável por sinal (ex.: `sipac_{notification_id}`,
    `calendar_{google_event_id}`) para dedupe estrutural, no mesmo espírito
    do e-mail (ID do doc = ID da mensagem do Gmail).

    `task` é o dicionário de candidata no formato de `_load_candidate_tasks`
    (precisa de ao menos `id`, `titulo`, `status`, `is_standby`).

    Não escreve se já existir uma sugestão com esse ID — produtores devem
    checar isso antes de fazer trabalho caro (embedding, chamada de IA); esta
    função só protege contra a escrita em si.
    """
    suggestions_col = db.collection("email_action_suggestions")
    doc_ref = suggestions_col.document(suggestion_id)
    if doc_ref.get().exists:
        return {}

    now_iso = datetime.now(timezone.utc).isoformat()
    base_doc = {
        "canal": canal,
        "titulo_sinal": titulo_sinal,
        "origem_sinal": origem_sinal,
        "task_id": task["id"],
        "task_titulo": task.get("titulo"),
        "task_status": task.get("status"),
        "resumo": resumo,
        "nota_sugerida": nota_sugerida or resumo,
        "reativar_sugerido": bool(reativar_sugerido) and bool(task.get("is_standby")),
        "related": True,
        "confidence": confidence,
        "analyzed_at": now_iso,
        "status": "pending",
        "telegram_sent": False,
    }
    if extra:
        base_doc.update(extra)

    doc_ref.set(base_doc)

    if chat_id:
        if send_fn is None:
            from main import _send_telegram_message_raw_with_keyboard
            send_fn = _send_telegram_message_raw_with_keyboard
        if _send_suggestion_telegram(db, chat_id, suggestion_id, base_doc, send_fn):
            base_doc["telegram_sent"] = True
            doc_ref.update({"telegram_sent": True, "sent_at": now_iso})

    return base_doc


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


def atualizar_direcao_emails_aplicados(db, service, limit: int = 60) -> None:
    """Materializa a direção atual das threads ligadas a ações.

    A abertura de `obter_estado_atual` não chama Gmail. Esta etapa roda no sync
    que já possui o serviço Gmail e atualiza no máximo sessenta vínculos ativos:
    se a última mensagem de uma thread for do André, ela deixa de aparecer como
    resposta pendente; se for recebida, seu timestamp avança para a mensagem
    mais recente da thread.
    """
    suggestions = db.collection("email_action_suggestions")
    try:
        docs = list(suggestions.where("status", "in", ["applied", "applied_reactivated"]).limit(limit).stream())
        own_email = str(service.users().getProfile(userId="me").execute().get("emailAddress") or "").strip().lower()
    except Exception as exc:
        print(f"[EMAIL-LINK] Falha ao atualizar direção de e-mails aplicados: {exc}")
        return
    if not own_email:
        return

    def _from(message: dict) -> str:
        headers = ((message.get("payload") or {}).get("headers") or [])
        raw = next((str(h.get("value") or "") for h in headers if str(h.get("name") or "").lower() == "from"), "")
        from email.utils import parseaddr
        return parseaddr(raw)[1].strip().lower()

    checked_at = datetime.now(timezone.utc).isoformat()
    for doc in docs:
        data = doc.to_dict() or {}
        message_id = str(data.get("google_message_id") or doc.id).strip()
        thread_id = str(data.get("gmail_thread_id") or "").strip()
        try:
            if not thread_id:
                source = service.users().messages().get(userId="me", id=message_id, format="metadata", metadataHeaders=["From"]).execute()
                thread_id = str(source.get("threadId") or "").strip()
            if not thread_id:
                continue
            thread = service.users().threads().get(userId="me", id=thread_id, format="metadata", metadataHeaders=["From"]).execute()
            messages = thread.get("messages") or []
            if not messages:
                continue
            latest = messages[-1]
            doc.reference.set({
                "gmail_thread_id": thread_id,
                "ultima_mensagem_de_andre": _from(latest) == own_email,
                "internal_date": latest.get("internalDate") or data.get("internal_date"),
                "email_last_checked_at": checked_at,
            }, merge=True)
        except Exception as exc:
            print(f"[EMAIL-LINK] Falha ao atualizar thread {thread_id or message_id}: {exc}")


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
    atualizar_direcao_emails_aplicados(db, service)
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
    query_excludes = []
    for pat in settings.get("ignored_senders", []):
        pat_clean = pat.strip()
        if pat_clean and " " not in pat_clean and len(pat_clean) <= 60:
            query_excludes.append(f"-from:{pat_clean}")
    if query_excludes:
        query = f"{query} {' '.join(query_excludes)}"
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
        if is_sender_ignored(sender, settings.get("ignored_senders", [])):
            base_doc = {
                "canal": "email",
                "titulo_sinal": subject,
                "origem_sinal": sender,
                "google_message_id": msg_id,
                "gmail_thread_id": msg.get("threadId"),
                "subject": subject,
                "sender": sender,
                "snippet": msg.get('snippet', ''),
                "internal_date": msg.get('internalDate'),
                "analyzed_at": now.isoformat(),
                "status": "ignored",
                "ignored_reason": "ignored_sender",
                "related": False,
            }
            suggestions_col.document(msg_id).set(base_doc)
            continue

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
            "canal": "email",
            "titulo_sinal": subject,
            "origem_sinal": sender,
            "google_message_id": msg_id,
            "gmail_thread_id": msg.get("threadId"),
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
            # Corpo do e-mail já limpo/truncado (mesmo texto usado no prompt de análise,
            # ver _extract_email_body) — permite que um pedido personalizado do usuário na
            # fila web (DashboardView.tsx) tenha acesso a detalhes concretos (números de
            # processo, valores, datas) que o `resumo` da IA pode ter condensado.
            "texto_original": body,
        })
        suggestions_col.document(msg_id).set(base_doc)

        if sent_this_pass >= settings["max_suggestions_per_pass"]:
            continue
        if chat_id and _send_email_suggestion_telegram(db, chat_id, msg_id, base_doc, _send_telegram_message_raw_with_keyboard):
            suggestions_col.document(msg_id).update({"telegram_sent": True, "sent_at": now.isoformat()})
            sent_this_pass += 1

    if analyzed:
        log_to_firestore(sync_ref, logs, f"[EMAIL-LINK] {analyzed} e-mail(is) analisado(s).", True)


def try_link_sipac_notification(db, notification_id: str, notif: dict) -> bool:
    """
    Chamado por `on_notificacao_created` (main.py) quando o scraper SIPAC
    (`functions_node/index.js`, `link == '@SipacTrackingTool'`) cria uma
    notificação de mudança. Casa o número do processo com ações ativas por
    `tarefas.processo_sei` — matching determinístico, sem IA — e propõe
    registrar a movimentação no diário de bordo.

    Retorna True se encontrou uma ação correspondente e conseguiu enviar o
    cartão de confirmação — nesse caso o chamador pula o espelhamento
    genérico da notificação, para não duplicar o aviso. False caso
    contrário (sem ação correspondente, ou falha no envio), quando o
    chamador deve cair para o espelhamento genérico como reserva.
    """
    from main import _resolve_default_telegram_chat_id

    numero_processo = str(notif.get("numeroProcesso") or "").strip()
    numero_digits = _normalize_digits(numero_processo)
    if not numero_digits:
        return False

    candidates = _load_candidate_tasks(db)
    task = next((c for c in candidates if _normalize_digits(c.get("processo_sei")) == numero_digits), None)
    if not task:
        return False

    chat_id = _resolve_default_telegram_chat_id(db)
    if not chat_id:
        return False

    resumo = str(notif.get("message") or "").strip()[:600]
    result = queue_and_maybe_send_suggestion(
        db,
        f"sipac_{notification_id}",
        canal="sipac",
        task=task,
        titulo_sinal=f"Processo {numero_processo}",
        origem_sinal=str(notif.get("assunto") or "SIPAC"),
        resumo=resumo,
        nota_sugerida=resumo,
        reativar_sugerido=True,
        chat_id=chat_id,
        extra={"numero_processo": numero_processo},
    )
    return bool(result and result.get("telegram_sent"))


CALENDAR_EVENT_LOOKBACK_MINUTES = 180
# `google_calendar_events.data_fim` é gravado cru a partir da API do Calendar (`main.py`,
# `event['end'].get('dateTime', ...)`)  —  offset LOCAL do calendário (ex. "-03:00" no Brasil),
# nunca normalizado para UTC. Comparar essas strings contra limites em UTC por ordem
# lexicográfica é incorreto (às 15h UTC, um evento que terminou 11h -03:00 = 14h UTC —
# já dentro da janela — perde na comparação de string porque "11" < "12"). Por isso a
# pré-filtragem por string abaixo usa uma folga generosa só para manter a query barata;
# a comparação que decide de fato usa datetimes normalizados para UTC.
CALENDAR_QUERY_SLACK_MINUTES = 360


def link_calendar_events_to_actions(db, sync_ref, logs):
    """
    Propõe registrar no diário de bordo o fechamento de reuniões vinculadas
    a uma ação. Matching determinístico por `tarefas.google_calendar_id` —
    o mesmo campo já usado pela sincronia reversa Calendar→Hermes em
    `sync_google_calendar` — sem IA, sem custo. Chamada no fim de
    `run_full_sync`, depois de `link_emails_to_actions`.
    """
    from main import _resolve_default_telegram_chat_id, log_to_firestore, parse_iso_datetime

    settings = _load_settings(db)
    if not settings["enabled"]:
        return

    now = datetime.now(timezone.utc)
    lookback = timedelta(minutes=CALENDAR_EVENT_LOOKBACK_MINUTES)
    slack = timedelta(minutes=CALENDAR_QUERY_SLACK_MINUTES)
    query_window_start = (now - lookback - slack).isoformat()
    query_window_end = (now + slack).isoformat()

    try:
        events = list(
            db.collection("google_calendar_events")
            .where("data_fim", ">=", query_window_start)
            .where("data_fim", "<=", query_window_end)
            .stream()
        )
    except Exception as exc:
        log_to_firestore(sync_ref, logs, f"[CAL-LINK][ERRO] Falha ao consultar eventos encerrados: {exc}", True)
        return
    if not events:
        return

    candidates_by_calendar_id = {
        c["google_calendar_id"]: c for c in _load_candidate_tasks(db) if c.get("google_calendar_id")
    }
    if not candidates_by_calendar_id:
        return

    chat_id = _resolve_default_telegram_chat_id(db)
    suggestions_col = db.collection("email_action_suggestions")
    linked = 0

    for event_doc in events:
        event = event_doc.to_dict() or {}
        # Eventos que o próprio Hermes criou na agenda (ver 'criado_pelo_hermes' em
        # sync_google_calendar, main.py) não viram sinal: o sistema já sabe dessa ação
        # porque foi ele quem agendou — sinalizar de volta seria redundante.
        if event.get("criado_pelo_hermes"):
            continue
        google_id = event.get("google_id")
        task = candidates_by_calendar_id.get(google_id)
        if not task:
            continue

        # Comparação de verdade, com fuso normalizado — corrige o pré-filtro por string acima.
        end_dt = parse_iso_datetime(event.get("data_fim"))
        if end_dt is None or end_dt.tzinfo is None:
            continue  # evento "dia inteiro" (sem horário) ou data_fim ilegível — não é "reunião encerrada"
        end_dt = end_dt.astimezone(timezone.utc)
        if not (now - lookback <= end_dt <= now):
            continue

        suggestion_id = f"calendar_{google_id}"
        if suggestions_col.document(suggestion_id).get().exists:
            continue

        titulo = event.get("titulo") or "(sem título)"
        hora_fim = end_dt.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M")
        resumo = f"A reunião \"{titulo}\" terminou às {hora_fim}."

        result = queue_and_maybe_send_suggestion(
            db,
            suggestion_id,
            canal="calendar",
            task=task,
            titulo_sinal=titulo,
            origem_sinal="Google Calendar",
            resumo=resumo,
            nota_sugerida=resumo,
            reativar_sugerido=True,
            chat_id=chat_id,
        )
        if result:
            linked += 1

    if linked:
        log_to_firestore(sync_ref, logs, f"[CAL-LINK] {linked} reunião(ões) encerrada(s) vinculada(s) a ações.", True)
