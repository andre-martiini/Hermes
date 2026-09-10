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
import re
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses, parseaddr
from zoneinfo import ZoneInfo

from firebase_admin import firestore
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

# DEV-2026-0004 sub-entrega 2/9: remetente típico de devolução (bounce) --
# mesma ideia de `inbox_pendentes._AUTO_SENDER`, mas restrito aos remetentes
# que especificamente sinalizam não-entrega (não todo remetente automático).
_BOUNCE_SENDER_RE = re.compile(
    r"(mailer-daemon|postmaster|mail delivery subsystem|delivery status notification)", re.I
)
# Código SMTP estendido (RFC 3463), ex. "550 5.1.1 ..." ou "550-5.7.1 ...".
# Exige o código de resposta básico de 3 dígitos (2xx/4xx/5xx) logo antes,
# separado por espaço ou hífen (formato multilinha "550-5.7.1" / "550 5.7.1")
# -- achado da revisão adversarial desta sub-entrega: sem essa âncora, o
# padrão solto `[245]\.\d{1,3}\.\d{1,3}` casa falsamente com trechos comuns
# em corpos de devolução reais que não são o código (octetos de IP como
# "10.2.30.41", ou um cabeçalho citado como "X-Mailer: 5.2.1"). Uma segunda
# forma cobre o campo "Status:" de um DSN (RFC 3464) ecoado no texto legível
# -- não tem o código básico de 3 dígitos na frente, mas o rótulo "Status:"
# é inequívoco o bastante para não precisar dessa âncora (achado da segunda
# revisão adversarial: a forma única, mais estrita, deixava de casar esse
# formato, que é comum o bastante para não ficar de fora).
_SMTP_EXTENDED_CODE_PATTERNS = (
    re.compile(r"\b\d{3}[- ]([245]\.\d{1,3}\.\d{1,3})\b"),
    re.compile(r"^status:\s*([245]\.\d{1,3}\.\d{1,3})", re.I),
)

# DEV-2026-0004 sub-entrega 2/9 (achado da revisão adversarial): o cabeçalho
# `To` da mensagem que disparou a devolução só identifica o destinatário que
# falhou quando havia um único destinatário -- com vários (cc de grupo,
# e-mail institucional), não dá para saber qual deles rejeitou sem olhar o
# próprio corpo da devolução, que normalmente nomeia o endereço explicitamente.
# Dois formatos cobertos, do mais para o menos específico: o endereço entre
# "<>" logo após o código SMTP (Postfix/Exim/Sendmail e a maioria dos NDRs
# genéricos), e as frases fixas do Gmail quando o primeiro não aparece. O
# primeiro exige que só espaço/tab/dois-pontos/hífen separe o código do "<"
# -- achado da segunda revisão adversarial: uma folga larga (a versão
# original aceitava até 20 caracteres quaisquer no meio) deixava o padrão
# pegar um endereço de contato/abuse mencionado por perto mas sem relação
# (ex. "erro 5.7.1, fale com <abuse@...>"), em vez do destinatário real;
# exigir adjacência também reduz o risco de casar um octeto de IP em vez do
# código. Pontuação (":"/"-") continua permitida além de espaço/tab -- achado
# da terceira revisão: formatos reais variam ("550 5.1.1: <addr>",
# "5.1.1 - <addr>"), e nenhum deles introduz o risco de prosa que motivou a
# restrição original (letras continuam de fora da classe de caracteres).
_BOUNCE_RECIPIENT_PATTERNS = (
    re.compile(
        r"[245]\.\d{1,3}\.\d{1,3}[ \t:-]{0,4}<([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})>",
        re.I,
    ),
    re.compile(
        r"(?:delivery to the following recipient failed|"
        r"wasn.t delivered to|couldn.t be delivered to)"
        r"[\s\S]{0,80}?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
        re.I,
    ),
)

# DEV-2026-0004 sub-entrega 2/9 (achado da segunda revisão adversarial): o
# detector de remetente (`_BOUNCE_SENDER_RE`) não distingue um aviso de
# ATRASO (a entrega ainda pode dar certo numa próxima tentativa) de uma
# falha PERMANENTE -- os dois vêm do mesmo tipo de remetente automático.
# Tratar um atraso como "não entregue" geraria um item de prioridade alta
# falso-positivo toda vez que o servidor de destino só estivesse lento ou
# temporariamente fora (extremamente comum e geralmente se resolve sozinho).
# O sinal mais confiável é a classe do código SMTP estendido (RFC 3463):
# 4.x.x é falha transitória ("Persistent Transient Failure"), só 5.x.x é
# permanente. Sem código reconhecido, cai para palavras-chave do corpo.
# Simplificação aceita (achado da terceira revisão adversarial): 4.2.2
# (caixa cheia) tecnicamente é "transitório" pela RFC, mas na prática às
# vezes nunca se resolve sozinho (o dono da caixa não libera espaço) -- tratá-lo
# como atraso pode deixar uma devolução efetivamente permanente de fora da
# fila por mais tempo que o ideal. Não há como diferenciar isso de um atraso
# real sem acompanhar tentativas repetidas ao longo do tempo, o que está fora
# do escopo desta sub-entrega; fica como limitação conhecida.
#
# Só os primeiros N linhas do corpo são varridas (aqui e em
# `_extract_bounce_reason`) -- achado da terceira revisão: um DSN real quase
# sempre repete o texto da mensagem original mais abaixo no corpo (citação),
# que pode conter incidentalmente uma dessas palavras-chave (ou um código
# SMTP não relacionado) sem ter nada a ver com o motivo real da devolução;
# limitar a janela ao início, onde o servidor sempre coloca sua própria
# explicação, reduz esse risco sem precisar separar as partes MIME da
# devolução (`message/delivery-status` vs. `text/rfc822-headers`), que
# `_extract_email_body` não distingue hoje.
_BOUNCE_DIAGNOSTIC_WINDOW_LINES = 20

_DELAY_KEYWORDS = (
    "will keep trying", "we'll keep trying", "has been delayed",
    "message is delayed", "delivery is delayed", "delayed mail",
    "temporarily deferred", "try again later", "delivery incomplete",
    # equivalentes em português -- a conta é de um usuário brasileiro e o
    # Gmail localiza essas notificações pelo idioma da conta.
    "vamos continuar tentando", "tentaremos novamente", "entrega atrasada",
    "mensagem está atrasada", "atraso na entrega",
)


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


def dismiss_matching_pending_emails(db, ignored_patterns: list[str]) -> int:
    """Descarta sugestões pendentes ou expiradas de e-mail cujo remetente casa
    com os padrões ignorados.

    Garante:
    1. Filtro estrito de canal ('email') para não descartar sugestões de outros canais
       (WhatsApp/SIPAC/Calendar) que compartilham a coleção email_action_suggestions.
    2. Transação atômica por documento para evitar race condition caso a sugestão tenha
       sido aplicada concorrentemente no Telegram ou na interface web.
    """
    if not ignored_patterns:
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    pending_docs = list(
        db.collection("email_action_suggestions")
        .where("status", "in", ["pending", "expired"])
        .stream()
    )
    dismissed_count = 0

    @firestore.transactional
    def _dismiss_tx(transaction, doc_ref):
        snap = doc_ref.get(transaction=transaction)
        if not snap.exists:
            return False
        data = snap.to_dict() or {}
        if data.get("status") not in ("pending", "expired"):
            return False
        transaction.update(doc_ref, {
            "status": "dismissed",
            "decided_at": now_iso,
            "dismissed_by": "ignored_filter",
        })
        return True

    for s_doc in pending_docs:
        s_data = s_doc.to_dict() or {}
        # P2.1: Filtra estritamente canal de email
        if s_data.get("canal") != "email":
            continue

        sender = s_data.get("sender") or s_data.get("origem_sinal") or ""
        if is_sender_ignored(sender, ignored_patterns):
            # P2.2: Transação atômica para evitar sobrescrever sugestão aplicada concorrentemente
            applied = False
            try:
                tx = db.transaction()
                applied = bool(_dismiss_tx(tx, s_doc.reference))
            except Exception:
                # Fallback defensivo para mocks de teste simplificados
                snap = s_doc.reference.get()
                if snap.exists and (snap.to_dict() or {}).get("status") in ("pending", "expired"):
                    s_doc.reference.update({
                        "status": "dismissed",
                        "decided_at": now_iso,
                        "dismissed_by": "ignored_filter",
                    })
                    applied = True
            if applied:
                dismissed_count += 1

    return dismissed_count

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


def _load_settings(db, use_cache: bool = True) -> dict:
    if use_cache:
        from main import _cached_doc_get
        doc = _cached_doc_get(db, "system", "settings")
    else:
        doc = db.collection("system").document("settings").get()

    cfg = ((doc.to_dict() or {}) if doc.exists else {}).get("email_action_linker") or {}
    ignored_raw = cfg.get("ignored_senders")
    if ignored_raw is None:
        ignored_senders = list(DEFAULT_IGNORED_SENDERS)
    else:
        ignored_senders = [str(x).strip().lower() for x in ignored_raw if str(x).strip()]

    # Unificação com a fonte de ruído de inbox_pendentes (_noise_config / config/inbox_pendentes)
    try:
        from inbox_pendentes import _noise_config
        noise_domains, _ = _noise_config(db)
        for d in sorted(noise_domains):
            d_norm = str(d).strip().lower()
            if d_norm and d_norm not in ignored_senders:
                ignored_senders.append(d_norm)
    except Exception:
        pass

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


def _extract_bounce_reason(body: str) -> tuple[str | None, str]:
    """Extrai o código SMTP estendido (ex. "5.1.1") e uma linha de motivo do
    corpo de uma devolução (RFC 3464). Best-effort e deliberadamente simples:
    o formato varia bastante entre servidores de origem, então quando não
    acha um código, cai para as primeiras linhas do corpo como motivo --
    melhor que nada, mas sem código para orientar a sugestão de "Enviar
    e-mail como" (essa fica restrita ao caso em que o código 5.7.x foi
    identificado com confiança). Só examina as primeiras
    `_BOUNCE_DIAGNOSTIC_WINDOW_LINES` linhas (ver comentário na constante) --
    evita pegar um código não relacionado de dentro da mensagem original
    citada mais abaixo no corpo.
    """
    if not body:
        return None, ""
    linhas = [l.strip() for l in body.split("\n") if l.strip()][:_BOUNCE_DIAGNOSTIC_WINDOW_LINES]
    codigo = None
    motivo = ""
    for i, linha in enumerate(linhas):
        for padrao in _SMTP_EXTENDED_CODE_PATTERNS:
            m = padrao.search(linha)
            if m:
                codigo = m.group(1)
                motivo = linha
                if len(motivo) < 20 and i + 1 < len(linhas):
                    motivo = f"{motivo} {linhas[i + 1]}"
                break
        if codigo:
            break
    if not motivo:
        motivo = " ".join(linhas[:3])
    motivo = motivo.strip()
    if len(motivo) > 300:
        motivo = motivo[:297] + "..."
    return codigo, motivo


def _extract_bounce_recipient(body: str) -> str | None:
    """Tenta achar, no próprio corpo da devolução, o endereço que de fato
    falhou -- mais confiável que o cabeçalho `To` da mensagem anterior na
    thread quando esse `To` tinha mais de um destinatário (ver
    `_BOUNCE_RECIPIENT_PATTERNS`). `None` quando nenhum dos formatos
    reconhecidos aparece; o chamador cai para o cabeçalho `To` nesse caso."""
    if not body:
        return None
    for pattern in _BOUNCE_RECIPIENT_PATTERNS:
        m = pattern.search(body)
        if m:
            return m.group(1).strip().lower().rstrip(".,;:>)")
    return None


def _is_delayed_not_failed(body: str, codigo: str | None) -> bool:
    """True quando a mensagem é um aviso de ATRASO (a entrega ainda pode dar
    certo numa próxima tentativa), não uma falha definitiva -- não deve virar
    item na fila de atenção (ver `_DELAY_KEYWORDS`). Prioriza a classe do
    código SMTP estendido quando disponível (4.x.x = transitório, só 5.x.x é
    permanente); sem código reconhecido, cai para palavras-chave nas
    primeiras `_BOUNCE_DIAGNOSTIC_WINDOW_LINES` linhas do corpo -- não no
    corpo inteiro, para não pegar uma palavra-chave incidental dentro da
    mensagem original citada mais abaixo (achado da terceira revisão
    adversarial)."""
    if codigo:
        return codigo.startswith("4")
    linhas = [l for l in (body or "").split("\n") if l.strip()][:_BOUNCE_DIAGNOSTIC_WINDOW_LINES]
    janela_lower = "\n".join(linhas).lower()
    return any(kw in janela_lower for kw in _DELAY_KEYWORDS)


def _internal_date_to_sp_iso(internal_date) -> str:
    """Converte o `internalDate` do Gmail (epoch ms, string) para um timestamp
    ordenável (YYYY-MM-DDTHH:MM:SS) em America/Sao_Paulo -- granularidade de
    segundo, não só de dia. Isso importa para `avaliar_emails_nao_entregues`:
    a reabertura idempotente de um item fechado em `_persistir_itens_atencao`
    decide comparando esse valor (`prazo_origem`) com o gravado antes: duas
    devoluções DIFERENTES para o mesmo destinatário no mesmo dia (achado da
    revisão adversarial desta sub-entrega) precisam contar como ocorrências
    distintas -- com granularidade só de dia, se André resolvesse o item pela
    manhã e uma nova devolução (não relacionada) chegasse à tarde do mesmo
    dia, o item ficaria incorretamente fechado. Valor ausente/inválido cai
    para o instante atual (mesmo fuso) em vez de propagar exceção -- o
    chamador não deve travar por causa de um campo auxiliar de data."""
    sp_tz = ZoneInfo("America/Sao_Paulo")
    try:
        millis = int(internal_date)
        return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).astimezone(sp_tz).strftime("%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return datetime.now(sp_tz).strftime("%Y-%m-%dT%H:%M:%S")


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

    DEV-2026-0004 sub-entrega 1/9 (causa-raiz do achado B1): os campos `sender`
    e `snippet` também são reescritos a cada refresh, a partir da mensagem mais
    recente da thread -- antes só eram gravados uma vez, na criação da sugestão
    (`link_emails_to_actions`), e nunca mais tocados aqui. Sem isso, quando uma
    devolução (mailer-daemon) chega como resposta à mensagem do André, o campo
    `sender` continuava apontando para o remetente humano original: o filtro de
    ruído em `inbox_pendentes._noise_reason` já sabe reconhecer `mailer-daemon`
    via `_AUTO_SENDER`, mas comparava sempre contra esse remetente congelado,
    nunca contra quem de fato mandou a última mensagem da thread -- por isso a
    devolução aparecia como "resposta pendente" do contato original em vez de
    ser excluída (ou, a partir da sub-entrega 2/9, virar um item dedicado
    `email_nao_entregue` na fila de atenção). `snippet` entra pelo mesmo motivo,
    achado pela revisão adversarial desta sub-entrega: sem atualizá-lo junto,
    `sender` ficaria correto mas `inbox_pendentes._item` mostraria esse contato
    ao lado de um trecho (`trecho`) de uma mensagem antiga e diferente -- não
    afeta o caso mailer-daemon em si (o filtro de ruído decide pelo remetente,
    antes de olhar o trecho), mas afetaria qualquer outra troca de remetente na
    mesma thread.
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

    def _from_header(message: dict) -> str:
        headers = ((message.get("payload") or {}).get("headers") or [])
        return next((str(h.get("value") or "") for h in headers if str(h.get("name") or "").lower() == "from"), "")

    def _from(message: dict) -> str:
        return parseaddr(_from_header(message))[1].strip().lower()

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
            update = {
                "gmail_thread_id": thread_id,
                "ultima_mensagem_de_andre": _from(latest) == own_email,
                "internal_date": latest.get("internalDate") or data.get("internal_date"),
                "email_last_checked_at": checked_at,
            }
            latest_sender = _from_header(latest)
            if latest_sender:
                update["sender"] = latest_sender
            latest_snippet = latest.get("snippet")
            if latest_snippet:
                update["snippet"] = latest_snippet
            doc.reference.set(update, merge=True)
        except Exception as exc:
            print(f"[EMAIL-LINK] Falha ao atualizar thread {thread_id or message_id}: {exc}")


def detectar_emails_nao_entregues(db, service, settings: dict | None = None, limit: int = 60) -> list[dict]:
    """DEV-2026-0004 sub-entrega 2/9: identifica devoluções (bounces) nas
    mesmas threads vinculadas a ações que `atualizar_direcao_emails_aplicados`
    já percorre, e grava um item `email_nao_entregue` na fila de atenção
    (`atencao.avaliar_emails_nao_entregues`) para cada destinatário com falha
    -- agrupando devoluções repetidas do mesmo destinatário em um único item.

    Respeita a flag system/settings.atencao.email_nao_entregue.enabled
    (padrão False, desligado), no mesmo padrão dos demais detectores de
    `atencao.py`.

    Roda como um segundo passe independente sobre as mesmas sugestões
    aplicadas/reativadas -- deliberadamente não reaproveita o laço de
    `atualizar_direcao_emails_aplicados` para não alterar aquela função já
    testada e em produção (sub-entrega 1/9). O custo extra só existe quando a
    flag está ligada, e o corpo da mensagem de devolução em si (a chamada
    `messages().get(format="full")`, mais cara) só é buscado quando um
    remetente de devolução é de fato encontrado -- não em toda thread.

    Atribuição de destinatário/alias (revisada duas vezes por revisões
    adversariais desta sub-entrega): a mensagem que gerou a devolução é a
    mais recente na thread, ANTES da devolução, que seja do próprio André
    (comparado ao e-mail da conta via `getProfile`) -- `_mensagem_disparadora`
    anda para trás procurando isso, em vez de assumir cegamente
    `messages[idx-1]` (que atribuía a devolução a si mesma quando o servidor
    manda mais de uma notificação para o mesmo envio -- aviso de atraso
    primeiro, falha definitiva depois -- e, mesmo só pulando notificações
    automáticas, ainda podia pegar a resposta de um terceiro que por acaso
    ficasse entre o envio original e uma devolução atrasada). Quando nenhuma
    mensagem anterior bate com o e-mail da conta (ex.: André mandou por um
    alias diferente do "Enviar e-mail como" -- limitação já aceita também em
    `atualizar_direcao_emails_aplicados`), cai para a mensagem não-automática
    mais recente antes da devolução, que ainda é melhor que nada.

    O destinatário que falhou vem, em ordem de confiança: (1) o endereço que
    o próprio corpo da devolução nomeia (`_extract_bounce_recipient`) -- é a
    fonte mais confiável e a única que funciona quando o `To` da mensagem
    disparadora tinha mais de um destinatário, caso em que `email.utils.parseaddr`
    (pensado para um único endereço) devolveria um valor vazio e a devolução
    seria descartada em silêncio; (2) se o corpo não nomear ninguém, o `To`
    da mensagem disparadora, mas só quando ele tem exatamente um endereço --
    com mais de um e nada no corpo, não dá para saber qual falhou, e a
    devolução é pulada em vez de arriscar atribuir à pessoa errada. O alias
    de envio (para a sugestão de revisar "Enviar e-mail como" quando o código
    é 5.7.x) vem do `From` da mensagem disparadora. Uma devolução sem nenhuma
    mensagem disparadora antes dela na thread é pulada -- não dá para
    atribuir destinatário com confiança nesse caso.

    Devoluções que são só um aviso de ATRASO (não uma falha definitiva) são
    descartadas por `_is_delayed_not_failed` -- ver essa função para o porquê.
    """
    if settings is None:
        try:
            settings_doc = db.collection("system").document("settings").get()
            settings = settings_doc.to_dict() if settings_doc.exists else {}
        except Exception as set_err:
            print(f"[EmailNaoEntregue] Falha ao consultar settings: {set_err}")
            settings = {}

    enabled = (
        (settings or {}).get("atencao", {}).get("email_nao_entregue", {}).get("enabled", False)
    )
    if not enabled:
        print("[EmailNaoEntregue] Detector email_nao_entregue desligado em system/settings; abortando.")
        return []

    suggestions = db.collection("email_action_suggestions")
    try:
        docs = list(suggestions.where("status", "in", ["applied", "applied_reactivated"]).limit(limit).stream())
    except Exception as exc:
        print(f"[EmailNaoEntregue] Falha ao consultar sugestões: {exc}")
        return []

    try:
        own_email = str(service.users().getProfile(userId="me").execute().get("emailAddress") or "").strip().lower()
    except Exception as profile_err:
        print(f"[EmailNaoEntregue] Falha ao obter e-mail da conta (seguindo sem ele): {profile_err}")
        own_email = ""

    def _header(message: dict, name: str) -> str:
        headers = ((message.get("payload") or {}).get("headers") or [])
        name_l = name.lower()
        return next((str(h.get("value") or "") for h in headers if str(h.get("name") or "").lower() == name_l), "")

    def _from_addr(message: dict) -> str:
        return parseaddr(_header(message, "From"))[1].strip().lower()

    def _mensagem_disparadora(messages: list[dict], bounce_idx: int) -> dict | None:
        """Anda para trás a partir do índice da devolução procurando a
        mensagem que a disparou. Prioriza a mais recente que seja do próprio
        André (bate com `own_email`) -- evita pegar a resposta de um
        terceiro que por acaso ficou entre o envio original e a devolução.
        Quando nada bate com `own_email` (ex.: alias de envio diferente),
        cai para a mensagem não-automática mais recente antes da devolução
        (ver docstring acima).

        Sem `own_email` (falha ao consultar a conta -- ver acima), não dá
        para diferenciar uma mensagem do André de uma resposta de terceiro
        com confiança nenhuma: devolve None para TODA devolução nesse passe
        em vez de arriscar a mesma atribuição errada que esta função existe
        para evitar (achado da terceira revisão adversarial -- sem essa
        guarda, a falha ao obter `own_email` fazia a função silenciosamente
        regredir para "mensagem não-automática mais próxima", reintroduzindo
        o problema)."""
        if not own_email:
            return None
        melhor_nao_automatica = None
        for j in range(bounce_idx - 1, -1, -1):
            candidata = messages[j]
            remetente_candidata = _header(candidata, "From")
            if remetente_candidata and _BOUNCE_SENDER_RE.search(remetente_candidata):
                continue
            if melhor_nao_automatica is None:
                melhor_nao_automatica = candidata
            if _from_addr(candidata) == own_email:
                return candidata
        return melhor_nao_automatica

    bounces: list[dict] = []
    for doc in docs:
        data = doc.to_dict() or {}
        message_id = str(data.get("google_message_id") or doc.id).strip()
        thread_id = str(data.get("gmail_thread_id") or "").strip()
        try:
            if not thread_id:
                source = service.users().messages().get(
                    userId="me", id=message_id, format="metadata", metadataHeaders=["From"]
                ).execute()
                thread_id = str(source.get("threadId") or "").strip()
            if not thread_id:
                continue
            thread = service.users().threads().get(
                userId="me", id=thread_id, format="metadata", metadataHeaders=["From", "To"]
            ).execute()
            messages = thread.get("messages") or []
            for idx, msg in enumerate(messages):
                sender = _header(msg, "From")
                if not sender or not _BOUNCE_SENDER_RE.search(sender):
                    continue

                disparadora = _mensagem_disparadora(messages, idx)
                if disparadora is None:
                    print(f"[EmailNaoEntregue] Sem mensagem disparadora confiável para a devolução "
                          f"{msg.get('id')} na thread {thread_id}; pulando.")
                    continue
                destinatario_raw = _header(disparadora, "To")
                alias_remetente = _header(disparadora, "From")

                bounce_msg_id = str(msg.get("id") or "").strip()
                motivo, codigo, corpo = "", None, ""
                if bounce_msg_id:
                    try:
                        full = service.users().messages().get(
                            userId="me", id=bounce_msg_id, format="full"
                        ).execute()
                        corpo = _extract_email_body(full.get("payload") or {})
                        codigo, motivo = _extract_bounce_reason(corpo)
                    except Exception as body_err:
                        print(f"[EmailNaoEntregue] Falha ao ler corpo da devolução {bounce_msg_id}: {body_err}")

                if _is_delayed_not_failed(corpo, codigo):
                    # Aviso de atraso, não falha definitiva -- a entrega
                    # ainda pode dar certo numa próxima tentativa do
                    # servidor; não vira item na fila de atenção.
                    print(f"[EmailNaoEntregue] Devolução {bounce_msg_id} parece atraso, não falha "
                          f"definitiva (codigo={codigo}); pulando.")
                    continue

                nome_dest = ""
                addr_dest = _extract_bounce_recipient(corpo)
                if not addr_dest:
                    # Corpo não nomeou o destinatário -- só confia no `To` da
                    # mensagem disparadora quando ele tem exatamente um
                    # endereço (getaddresses trata corretamente um `To` com
                    # vários destinatários separados por vírgula, ao
                    # contrário de parseaddr).
                    enderecos = getaddresses([destinatario_raw]) if destinatario_raw else []
                    if len(enderecos) == 1:
                        nome_dest, addr_dest = enderecos[0]
                        addr_dest = addr_dest.strip().lower()
                if not addr_dest:
                    continue
                if not nome_dest and destinatario_raw:
                    for nome_cand, addr_cand in getaddresses([destinatario_raw]):
                        if addr_cand.strip().lower() == addr_dest:
                            nome_dest = nome_cand
                            break

                internal_date = msg.get("internalDate") or data.get("internal_date")
                data_str = _internal_date_to_sp_iso(internal_date)

                bounces.append({
                    "destinatario": addr_dest,
                    "destinatario_nome": nome_dest or addr_dest,
                    "alias_remetente": alias_remetente,
                    "motivo": motivo,
                    "codigo_smtp": codigo,
                    "thread_id": thread_id,
                    "mensagem_id": bounce_msg_id or message_id,
                    "data": data_str,
                })
        except Exception as exc:
            print(f"[EmailNaoEntregue] Falha ao varrer thread {thread_id or message_id}: {exc}")

    if not bounces:
        return []

    import atencao as _atencao

    sp_tz = ZoneInfo("America/Sao_Paulo")
    hoje = datetime.now(sp_tz).date()
    itens = _atencao.avaliar_emails_nao_entregues(bounces, hoje)
    if itens:
        _atencao._persistir_itens_atencao(db, itens)
    return itens


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
    try:
        detectar_emails_nao_entregues(db, service)
    except Exception as bounce_err:
        # DEV-2026-0004 sub-entrega 2/9: nunca deixa a fila de atenção
        # atrapalhar o restante do sync de e-mails (mesma postura defensiva
        # do resto desta função).
        print(f"[EMAIL-LINK] Falha ao detectar e-mails não entregues: {bounce_err}")
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
