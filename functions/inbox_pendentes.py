"""Índice pequeno e determinístico de conversas que podem esperar resposta.

O MCP não consulta o histórico inteiro de WhatsApp ao montar ``obter_estado_atual``:
o worker de triagem atualiza uma linha por chat nesta coleção.  Assim, o resumo
matinal só lê ``inbox_pendentes`` e continua previsível mesmo quando o histórico
de mensagens cresce.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from email.utils import parseaddr
from datetime import datetime, timezone

from firebase_admin import firestore

from gemini_cost_controls import GEMINI_LIGHT_MODEL, generate_content_logged


COLLECTION = "inbox_pendentes"
# DEV-2026-0004 sub-entrega 7/9, proposta (b)(ii): cache de classificações do
# LLM -- ver `_classificar_necessidade_resposta` para a chave exata.
LLM_CLASSIFICACAO_COLLECTION = "inbox_pendentes_classificacao_llm"
_FEATURE_CLASSIFICADOR_LLM = "inbox_pendentes_classificador"
_LLM_ROTULOS_VALIDOS = {"pergunta", "pedido", "informativo", "encerramento"}
# Mapeia o rótulo do classificador para a chave de `filtered` correspondente.
# DELIBERADAMENTE contadores PRÓPRIOS (não os mesmos que a heurística usa
# para o equivalente, "informativo"/"encerramentos") -- achado da revisão
# adversarial: a heurística é regex/léxico estático e bem testado, mas a
# taxa de filtragem do LLM pode variar com mudanças de modelo/prompt sem que
# ninguém perceba se ficasse escondida dentro do mesmo contador. Contadores
# separados permitem monitorar "o classificador começou a filtrar demais"
# sem precisar de detalhe por item.
_LLM_ROTULO_PARA_FILTRO = {"informativo": "informativo_llm", "encerramento": "encerramentos_llm"}
# Achado CRÍTICO da revisão adversarial: `email_action_suggestions` tem seu
# `snippet`/`sender`/`internal_date` REESCRITOS a cada refresh de
# `email_action_linker.atualizar_direcao_emails_aplicados`, a partir da
# mensagem mais RECENTE da thread -- mas o id do documento (`doc.id`,
# usado como `message_id` no laço de e-mail de `coletar()`) nunca muda.
# Cachear só por `message_id` faria uma classificação de uma mensagem ANTIGA
# (ex.: "informativo") ser silenciosamente reaplicada a uma mensagem NOVA e
# diferente que chegou depois na mesma thread -- o "achado A" desta demanda
# de novo (exclusão indevida por dado congelado), só que impossível de
# perceber porque nada muda de nome. Por isso a chave de cache inclui um
# fingerprint do TEXTO classificado: qualquer mudança de conteúdo já invalida
# o cache sozinha, sem precisar que `email_action_linker.py` grave nenhum
# campo novo. Prefixo de canal (`wa`/`email`) é defesa extra, barata, contra
# uma colisão entre um id de mensagem do WhatsApp e um do Gmail.
def _chave_cache_classificacao(message_id: str, texto: str, is_email: bool) -> str:
    canal = "email" if is_email else "wa"
    fingerprint = hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]
    return f"{canal}:{message_id}:{fingerprint}"


# Idem, achado HIGH da revisão adversarial: `coletar()` é chamado de forma
# SÍNCRONA na abertura de toda sessão MCP (`morning_summary.gerar()`, que
# documenta explicitamente "não faz RPC ao WhatsApp/Gmail durante a abertura
# de uma sessão MCP" -- ver o comentário lá) e também da tool
# `listar_respostas_pendentes`. Sem limite, um cache frio (logo após esta
# sub-entrega entrar em produção, ou um backlog grande) dispararia uma
# chamada Gemini SEQUENCIAL para cada mensagem sobrevivente aos filtros
# gratuitos, quebrando essa garantia de latência. Um orçamento baixo e fixo
# por passada mantém o pior caso pequeno; itens além do orçamento passam sem
# classificar (mesmo comportamento de "sem client disponível" -- nunca
# escondidos por falta de orçamento) e são reconsiderados na próxima
# passada, então o cache esquenta gradualmente sem nunca bloquear nada.
_LLM_MAX_CLASSIFICACOES_POR_PASSADA = 5
_STANDBY_STATUS_ALIASES = {"stand-by", "standby", "stand by", "cgby"}
_ACTIVE_STATUS_ALIASES = {"em andamento", "andamento", "nao iniciado", "não iniciado", "pendente"}
MAX_ITEMS = 15
EMAIL_SUGGESTIONS_LIMIT = 60
BACKFILL_PAGE_SIZE = 100
_AUTO_SENDER = re.compile(r"^(noreply|no-reply|naoresponda|nao-responda|notificacao|notification|mailer-daemon|newsletter)[@._-]", re.I)
_MEDIA_PREFIX = ("/9j/", "ivbor")
_DATA_URI = re.compile(r"^data:[^;,\s]+(?:;[^,\s]+)*;base64,", re.I)
_DEFAULT_DOMAINS = {"eventos.ifnmg.edu.br", "picpay.com", "picpay.com.br"}
# DEV-2026-0004 sub-entrega 3/9: usado tanto como léxico de palavras isoladas
# quanto como frases -- ver `_is_closing_message`, que exige a mensagem
# INTEIRA (todas as palavras) seja coberta por itens deste set, nunca só uma
# palavra solta em meio a outras (a primeira versão desta sub-entrega fazia
# isso e a revisão adversarial mostrou que "Ok, pode me ligar agora" ou "Bom
# dia, poderia confirmar isso" -- pedidos de verdade -- também casavam e
# ficavam escondidos do André; ver `_is_closing_message` para o algoritmo de
# cobertura). As frases de 3+ palavras abaixo são literais, tiradas dos 9
# encerramentos do achado B4 da demanda ("Obrigada pelo retorno", "Ok,
# obrigada por avisar", "De nada, André!", "Boa noite e fique com Deus") --
# deliberadamente não decompostas em palavras soltas ("retorno", "avisar",
# "andre" isolados não entram no léxico) para não reabrir a mesma brecha.
_DEFAULT_ENDINGS = {"ok", "okay", "blz", "beleza", "obrigado", "obrigada", "obrigadao", "obrigadinho", "mto obrigado", "mto obrigada", "muito obrigado", "muito obrigada", "vlw", "flw", "valeu", "ja foi", "entendi", "entendido", "ah sim entendi", "combinado", "perfeito", "show", "top", "joia", "ate amanha", "ate logo", "ate mais", "bom dia", "boa tarde", "boa noite", "abraco", "abracos", "abs", "de nada", "de nada andre", "obrigada pelo retorno", "obrigado pelo retorno", "obrigada por avisar", "obrigado por avisar", "boa noite e fique com deus"}
# Interjeições de uma palavra só (risada, alívio) sem conteúdo informativo --
# ex.: "Ufaaaaa" (achado B4). Repetição de letra no fim é normal em WhatsApp;
# `(?:ha|he){2,}` cobre variações de risada como "hahaha"/"hehehe" (a versão
# original só absorvia repetição de "a" ou "e" ao final, perdendo "hehehe").
_INTERJECTION_RE = re.compile(r"^(ufa+|kk+|rs+|(?:ha|he){2,}h?a?|uhu+|eba+)$")


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
        # DEV-2026-0004 sub-entrega 7/9: chave de cache do classificador LLM
        # (`_classificar_necessidade_resposta`) -- o id da mensagem em si, não
        # do chat, para que a classificação não fique presa a uma mensagem
        # antiga quando uma nova chega no mesmo chat.
        "message_id": str(message.get("id") or "").strip() or None,
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


# DEV-2026-0004 sub-entrega 4/9: prefixos/formato das notas de diário
# AUTOMÁTICAS geradas por `email_action_linker._build_diary_note` ao
# vincular um sinal a uma ação -- ver docstring de `_diario_mais_recente`.
# A SEGUNDA rodada de revisão adversarial encontrou que um coringa genérico
# (`\[\S+ Hermes\]`) também casava com prefixos GENUÍNOS usados por outras
# rotinas do sistema para notas reais e confirmadas -- "[Copiloto Hermes]"
# (main.py, tools/hermes_tools.py, telegram_message_tools.py) e "[Telegram
# Hermes]" (tools/telegram_extended.py) -- excluindo tratamento de verdade
# da comparação (o oposto do achado da primeira rodada: em vez de esconder
# uma pendência real, isso faz o auto-resolve nunca disparar quando a nota
# mais recente é uma dessas). Corrigido restringindo a classe de caracteres
# aos ícones REAIS de `email_action_linker._CANAL_ICONS` (mais o fallback
# "🔔" de `.get(canal, "🔔")`) -- mantidos aqui como literal, não
# importados, para não criar uma dependência de módulo nova só por isso
# (este arquivo é o índice leve e determinístico descrito no docstring do
# módulo). Se `_CANAL_ICONS` ganhar um ícone novo, esta lista precisa
# acompanhar -- comentário espelhado ao lado de `_CANAL_ICONS` para isso
# não passar despercebido.
_AUTO_LINK_ICONS = "📧📱📋📅🌐🔔"
_AUTO_LINK_NOTE_RE = re.compile(r"^(?:EMAIL|WHATSAPP)::JSON::|^\[[" + _AUTO_LINK_ICONS + r"] Hermes\]\s")


def _diario_mais_recente(acompanhamento) -> datetime | None:
    """DEV-2026-0004 sub-entrega 4/9: data da entrada de diário mais recente
    e GENUÍNA (nota real -- não um marcador AUTOMÁTICO de vínculo, que só
    registra o instante em que um sinal foi ligado à ação, nunca evidência
    de que André tratou algo; esse vínculo em si é só a razão da mensagem
    aparecer aqui). `email_action_linker._build_diary_note` produz três
    formatos para esse marcador, um por grupo de canal -- todos excluídos
    por `_AUTO_LINK_NOTE_RE`:
      - ``EMAIL::JSON::{...}`` (canal e-mail);
      - ``WHATSAPP::JSON::{...}`` (canal whatsapp);
      - ``[{icone} Hermes] {rótulo}: ...`` (demais canais -- sipac,
        calendar, pagina -- sempre começa com um ícone entre colchetes
        seguido de " Hermes]").
    A primeira versão desta função só excluía o primeiro formato -- a
    revisão adversarial mostrou que os outros dois têm o mesmo problema:
    vincular uma conversa de WhatsApp (ou um processo SIPAC, reunião etc.)
    a uma ação grava uma nota tão automática quanto a de e-mail, no mesmo
    fluxo de um clique (`apply_suggestion`) -- sem essa exclusão, vincular
    QUALQUER sinal a uma ação com outra pendência ainda em aberto esconderia
    essa pendência na hora, mesmo sem André ter feito nada a respeito dela.
    Ver `_resolved_by_diario`."""
    latest = None
    for entry in acompanhamento or []:
        if not isinstance(entry, dict):
            continue
        nota = str(entry.get("nota") or "")
        if _AUTO_LINK_NOTE_RE.match(nota):
            continue
        when = _as_datetime(entry.get("data"))
        if when and (latest is None or when > latest):
            latest = when
    return latest


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
            "diario_mais_recente": _diario_mais_recente(task.get("acompanhamento")),
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


def _contacts(db) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Nomes de contato por chat_id e, DEV-2026-0004 sub-entrega 5/9 proposta
    (c)(ii), o vínculo de identidade do MESMO contato entre WhatsApp e
    e-mail -- só quando o MESMO doc de `perfil_pessoas` tem `whatsapp_chat_id`
    E `email` preenchidos ao mesmo tempo (os dois syncs independentes --
    Google Contacts para `email`, `linkWhatsappContacts` por últimos 8
    dígitos do telefone para `whatsapp_chat_id` -- já vincularam essa pessoa
    nos dois canais). Sem essa dupla confirmação não dá para saber com
    segurança que é o mesmo contato; os dois dicionários de e-mail ficam
    vazios de propósito nesse caso, nunca um palpite por nome/telefone.

    Devolve (nome_por_chat, email_por_chat, chat_por_email) -- o terceiro é
    o inverso do segundo, para ir de um remetente de e-mail até o chat de
    WhatsApp correspondente. Os dois novos são usados só para checar, do
    OUTRO canal, se André já respondeu depois da mensagem pendente -- ver
    `coletar()`."""
    nome_por_chat, email_por_chat, chat_por_email = {}, {}, {}
    for doc in db.collection("perfil_pessoas").stream():
        data = doc.to_dict() or {}
        chat_id = str(data.get("whatsapp_chat_id") or "").strip()
        nome = str(data.get("nome") or "").strip()
        email = str(data.get("email") or "").strip().lower()
        if chat_id and nome:
            nome_por_chat[chat_id] = nome
        if chat_id and email:
            email_por_chat[chat_id] = email
            chat_por_email[email] = chat_id
    return nome_por_chat, email_por_chat, chat_por_email


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


def _is_closing_message(words: list[str], endings: set[str]) -> bool:
    """DEV-2026-0004 sub-entrega 3/9: substitui a checagem antiga (o texto
    inteiro, já sem pontuação/maiúsculas, precisava ser IGUAL a um item do
    set) por uma cobertura mais tolerante a variações de pontuação/quebra de
    linha, mas que continua exigindo a mensagem INTEIRA -- todas as palavras,
    não só uma -- seja reconhecida como encerramento.

    Tenta casar, em sequência, as frases de `endings` com 2+ palavras contra
    trechos contíguos de `words` (a mais longa primeiro, para "boa noite e
    fique com deus" não deixar sobras que uma frase mais curta cobriria
    melhor); marca essas posições como cobertas. Qualquer palavra que sobra
    também precisa estar em `endings` como item de uma palavra só. Só quando
    TODAS as palavras da mensagem terminam cobertas -- por frase ou por
    palavra solta -- é que ela conta como encerramento.

    A primeira versão desta função bastava UMA palavra qualquer da mensagem
    bater no léxico (ou uma frase aparecer como substring solta) -- a revisão
    adversarial mostrou que isso escondia pedidos de verdade ("Ok, pode me
    ligar agora", "Bom dia, poderia confirmar isso"): a exigência de
    cobertura total fecha essa brecha sem perder os 9 exemplos reais do
    achado B4 (que viraram frases literais em `_DEFAULT_ENDINGS` em vez de
    palavras soltas decompostas -- ver o comentário ali)."""
    if not words:
        return False
    if len(words) == 1 and _INTERJECTION_RE.match(words[0]):
        return True
    phrases = sorted((e for e in endings if len(e.split()) > 1), key=lambda p: -len(p.split()))
    single_words = {e for e in endings if len(e.split()) == 1}
    covered = [False] * len(words)
    for phrase in phrases:
        p_tokens = phrase.split()
        n = len(p_tokens)
        if n > len(words):
            continue
        for start in range(0, len(words) - n + 1):
            if not any(covered[start:start + n]) and words[start:start + n] == p_tokens:
                for i in range(start, start + n):
                    covered[i] = True
    return all(covered[i] or words[i] in single_words for i in range(len(words)))


def _noise_reason(*, trecho: str, sender: str, is_email: bool, has_contact: bool, has_task: bool,
                  domains: set[str], endings: set[str], andre_em_to: bool | None = None) -> str | None:
    raw = str(trecho or "").strip()
    norm = _normalize_text(raw)
    if is_email:
        address = (parseaddr(str(sender or ""))[1] or str(sender or "")).lower().strip()
        if _AUTO_SENDER.match(address) or any(address.endswith("@" + d) for d in domains):
            return "automaticos"
        # DEV-2026-0004 sub-entrega 3/9: André só em Cc (nunca em To) é o
        # caso 2 do achado B -- e-mail informativo, não dirigido a ele, não
        # pede resposta. `andre_em_to is False` (nunca None) para não filtrar
        # quando o sinal não pôde ser calculado (ver `_andre_em_to`).
        if andre_em_to is False:
            return "informativo"
    if not raw or raw.lower().startswith(_MEDIA_PREFIX) or _DATA_URI.match(raw) or not re.sub(r"[^\w]", "", norm):
        return "sem_texto"
    if not is_email and not has_contact and not has_task and re.search(r"oferta|cart[aã]o|desconto|promo[cç][aã]o|fatura|clique|aproveite", norm):
        return "automaticos"
    words = re.findall(r"\w+", norm)
    if "?" not in raw and len(words) <= 6 and _is_closing_message(words, endings):
        return "encerramentos"
    return None


def _resolved_by_diario(task: dict | None, message_when: datetime | None) -> bool:
    """DEV-2026-0004 sub-entrega 4/9, proposta (c)(i): a ação vinculada já
    tem uma entrada de diário genuína registrada DEPOIS da própria
    mensagem -- André já tratou o assunto através da ação, a mensagem não
    precisa de resposta direta (achado B, caso 3: Gabriela, DAE/Proen,
    Marcos Marinho -- e-mails com anexo já tratados na ação, diário
    posterior à mensagem).

    Comparação estrita (`>`, nunca `>=`): uma entrada no MESMO instante da
    mensagem (ou antes dela) não conta -- pode ter sido o que criou o
    vínculo, não um tratamento posterior de verdade.

    Limitação conhecida e deliberada: a comparação é por AÇÃO, não por
    thread/mensagem específica -- qualquer entrada de diário genuína mais
    recente que a mensagem conta, mesmo que a ação tenha mais de uma
    mensagem vinculada e a entrada trate de outra. Correlacionar o
    CONTEÚDO da entrada com o remetente/assunto de cada mensagem exigiria
    um mecanismo bem maior (e mais frágil); o vínculo mensagem->ação já
    existente é o que hoje estabelece essa relação."""
    if not task or not message_when:
        return False
    latest = task.get("diario_mais_recente")
    return bool(latest and latest > message_when)


def _outgoing_email_by_contact(db, by_email: dict, by_id: dict) -> dict[str, datetime]:
    """DEV-2026-0004 sub-entrega 5/9, proposta (c)(ii): data do e-mail mais
    recente que o PRÓPRIO André mandou a cada contato, entre os vínculos
    aplicados (mesma fonte de `_applied_email_suggestions`).

    A SEGUNDA rodada de revisão adversarial encontrou que a primeira versão
    não exigia ação ATIVA vinculada, ao contrário de `emails_by_thread` em
    `coletar()` e do próprio `_resolved_by_diario` -- um e-mail respondido
    por André numa ação já CONCLUÍDA (ou sem ação nenhuma) contava como
    evidência de tratamento para uma pendência de WhatsApp completamente
    diferente do mesmo contato, sem relação com trabalho em andamento
    nenhum. Risco maior que o do vínculo por diário (que já exige ação
    ativa): aqui são dois canais e possivelmente dois assuntos diferentes,
    então a barra de evidência não podia ficar mais frouxa. Corrigido
    exigindo `task` resolvido (mesmo padrão de `by_email`/`by_id` de
    `_active_tasks`) antes de contar a data -- `by_email`/`by_id` recebidos
    do chamador, já calculados uma vez por `coletar()`.

    `origem_sinal` guarda o remetente ORIGINAL da thread (quem a
    disparou) -- nunca reescrito por `atualizar_direcao_emails_aplicados`,
    por isso continua identificando o contato mesmo depois que a direção da
    thread virou "última de André" (`sender`, esse sim, passa a apontar
    para o próprio André nesse caso -- ver docstring de
    `atualizar_direcao_emails_aplicados`). Quando o mesmo contato aparece em
    mais de uma thread (com ação ativa), fica a data mais recente."""
    latest: dict[str, datetime] = {}
    for doc in _applied_email_suggestions(db):
        data = doc.to_dict() or {}
        if str(data.get("canal") or "") != "email" or not data.get("ultima_mensagem_de_andre"):
            continue
        if not str(data.get("status") or "").startswith("applied"):
            continue
        task = by_email.get(doc.id) or by_id.get(str(data.get("task_id") or ""))
        if not task:
            continue
        address = (parseaddr(str(data.get("origem_sinal") or ""))[1] or "").strip().lower()
        if not address:
            continue
        when = _as_datetime(data.get("internal_date"))
        if when and (address not in latest or when > latest[address]):
            latest[address] = when
    return latest


def _resolved_cross_channel(*, contact_key: str | None, message_when: datetime | None,
                            outgoing_by_contact: dict) -> bool:
    """DEV-2026-0004 sub-entrega 5/9, proposta (c)(ii): André já respondeu
    ao MESMO contato pelo OUTRO canal depois da mensagem pendente (achado B
    implícito -- Wagner/Vetor, "André afirma que já tratou": quando o
    tratamento aconteceu por e-mail para uma pendência de WhatsApp, ou
    vice-versa, não precisa de resposta duplicada no canal original).

    `contact_key` é o identificador do contato NO OUTRO canal -- endereço
    de e-mail normalizado para resolver um item de WhatsApp, chat_id para
    resolver um item de e-mail -- já resolvido pelo chamador via
    `_contacts()`; None quando `perfil_pessoas` não liga os dois canais
    para essa pessoa (nunca um palpite). `outgoing_by_contact` é o mapa
    contato->data mais recente no OUTRO canal (`_outgoing_email_by_contact`
    para o lado e-mail; o equivalente para WhatsApp é construído em
    `coletar()` a partir do próprio índice já lido, sem nova consulta).

    Comparação estrita (`>`, nunca `>=`), mesmo motivo de
    `_resolved_by_diario`: uma resposta no mesmo instante da mensagem não
    conta como posterior a ela."""
    if not contact_key or not message_when:
        return False
    when = outgoing_by_contact.get(contact_key)
    return bool(when and when > message_when)


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


def _get_llm_client(db):
    """DEV-2026-0004 sub-entrega 7/9: constrói o client Gemini só quando
    algum item de fato sobreviveu aos filtros gratuitos (heurística,
    diário, canal cruzado) e precisa da classificação paga -- mesmo padrão
    de inicialização preguiçosa do resto do módulo (nunca ler
    `system/api_keys` ou montar o client à toa). Falha (chave ausente,
    import quebrado, etc.) devolve None em vez de propagar exceção: quem
    chama trata None exatamente como "sem classificador disponível agora" e
    NÃO filtra a mensagem -- ver `_classificar_necessidade_resposta`."""
    try:
        from main import get_genai_module, get_gemini_api_key
        api_key = get_gemini_api_key()
        if not api_key:
            return None
        genai = get_genai_module()
        return genai.Client(api_key=api_key)
    except Exception as exc:
        print(f"[INBOX-PENDENTES] Falha ao inicializar cliente Gemini para o classificador: {exc}")
        return None


def _build_prompt_classificador(texto: str, is_email: bool) -> str:
    fonte = "e-mail" if is_email else "mensagem de WhatsApp"
    return f"""Você é o Hermes, assistente pessoal do André. Classifique se a mensagem
abaixo de fato PEDE uma resposta ou ação dele, ou se pode ficar sem resposta.

MENSAGEM ({fonte}):
{texto}

Responda APENAS com um JSON no formato exato:
{{
  "rotulo": "pergunta" | "pedido" | "informativo" | "encerramento",
  "justificativa": "1 frase curta (português) explicando a escolha"
}}

Definições:
- "pergunta": faz uma pergunta direta que espera resposta do André.
- "pedido": pede uma ação, decisão ou providência do André (mesmo sem "?").
- "informativo": avisa ou informa algo, sem esperar resposta (ex.: "segue o
  anexo", cópia de e-mail em que André não é o destinatário principal,
  atualização de status já concluída).
- "encerramento": fecha a conversa (agradecimento, confirmação final,
  despedida) e não abre nada novo.

Na dúvida entre "pedido"/"pergunta" e "informativo"/"encerramento", prefira
"pedido" ou "pergunta" -- é bem menos custoso o André ver uma mensagem à toa
do que perder uma que de fato precisava de resposta."""


def _classificar_necessidade_resposta(db, get_client, *, message_id: str | None, texto: str,
                                      is_email: bool, pode_classificar=lambda: True) -> str | None:
    """DEV-2026-0004 sub-entrega 7/9, proposta (b)(ii): classifica com Gemini
    Flash Lite (`GEMINI_LIGHT_MODEL`, já usado em `email_action_linker.py`)
    se a mensagem pede resposta, com cache em `LLM_CLASSIFICACAO_COLLECTION`
    -- ver `_chave_cache_classificacao` para por que a chave inclui um
    fingerprint do texto, não só o `message_id`.

    `get_client` é uma função sem argumentos (não o client já pronto): só é
    chamada depois de confirmado que NÃO há cache para esta mensagem -- ou
    seja, o client (e a leitura de `system/api_keys` que ele exige) só é
    montado quando algo de fato vai ser classificado. `coletar()` passa uma
    versão memoizada (mesmo client reaproveitado entre mensagens da mesma
    passada, nunca reconstruído à toa a cada cache-hit) -- ver seu uso ali.

    `pode_classificar` é outra função sem argumentos, chamada no mesmo ponto
    (depois do cache-miss, antes de `get_client()`): devolve False quando o
    orçamento de chamadas novas desta passada (`_LLM_MAX_CLASSIFICACOES_POR_PASSADA`)
    já acabou -- controla o CUSTO da chamada em si (ao contrário de
    `get_client`, que controla se ela é sequer possível). Um cache-hit nunca
    consulta `pode_classificar` nem consome orçamento -- só uma classificação
    nova conta.

    Devolve um dos rótulos de `_LLM_ROTULOS_VALIDOS`, ou None quando a
    classificação não pôde ser obtida (sem `message_id`/texto para cachear,
    orçamento da passada esgotado, sem client/chave configurada, resposta
    malformada, erro de rede). None SEMPRE significa "não filtrar, deixa
    passar" -- nunca "filtrar". Uma falha de classificação escondendo a
    mensagem inteira seria o "achado A" desta demanda de novo (fechamento
    indevido por falha silenciosa), só que na direção pior: lá o item ficava
    preso aberto por engano; aqui a mensagem sumiria da fila sem André nunca
    vê-la. O chamador só filtra quando o rótulo devolvido está em
    `_LLM_ROTULO_PARA_FILTRO`."""
    message_id = str(message_id or "").strip()
    texto = str(texto or "").strip()
    if not message_id or not texto:
        return None
    cache_ref = db.collection(LLM_CLASSIFICACAO_COLLECTION).document(
        _chave_cache_classificacao(message_id, texto, is_email))
    try:
        cached = cache_ref.get()
        if cached.exists:
            rotulo = (cached.to_dict() or {}).get("rotulo")
            if rotulo in _LLM_ROTULOS_VALIDOS:
                return rotulo
    except Exception as exc:
        print(f"[INBOX-PENDENTES] Falha ao ler cache do classificador ({message_id}): {exc}")
    if not pode_classificar():
        return None
    client = get_client()
    if client is None:
        return None
    try:
        from google.genai import types
        response = generate_content_logged(
            client,
            model=GEMINI_LIGHT_MODEL,
            contents=_build_prompt_classificador(texto, is_email),
            feature=_FEATURE_CLASSIFICADOR_LLM,
            db=db,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
        )
        raw = (response.text or "").strip()
        if "```json" in raw:
            raw = raw.split("```json")[-1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[-1].split("```")[0].strip()
        parsed = json.loads(raw)
        rotulo = str(parsed.get("rotulo") or "").strip().lower()
        justificativa = str(parsed.get("justificativa") or "").strip()[:300]
    except Exception as exc:
        print(f"[INBOX-PENDENTES] Falha ao classificar via LLM ({message_id}): {exc}")
        return None
    if rotulo not in _LLM_ROTULOS_VALIDOS:
        return None
    try:
        cache_ref.set({
            "rotulo": rotulo,
            "justificativa": justificativa,
            "classificado_em": datetime.now(timezone.utc),
        })
    except Exception as exc:
        print(f"[INBOX-PENDENTES] Falha ao cachear classificação LLM ({message_id}): {exc}")
    return rotulo


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
    contacts, email_por_chat, chat_por_email = _contacts(db)
    outgoing_email = _outgoing_email_by_contact(db, by_email, by_id)
    # DEV-2026-0004 sub-entrega 5/9: última mensagem de André por chat, só
    # para os chats cuja mensagem mais recente É dela -- preenchido abaixo,
    # dentro do próprio laço de WhatsApp (nenhuma consulta nova), e usado
    # depois no laço de e-mail para resolver pendências de e-mail cujo
    # contato já foi respondido por WhatsApp. Ver `_resolved_cross_channel`.
    whatsapp_last_outgoing: dict[str, datetime] = {}
    items = []
    filtered = {"automaticos": 0, "encerramentos": 0, "sem_texto": 0, "informativo": 0,
                "informativo_llm": 0, "encerramentos_llm": 0,
                "tratado_na_acao": 0, "tratado_em_outro_canal": 0}
    domains, endings = _noise_config(db)
    # DEV-2026-0004 sub-entrega 7/9: montado (e memoizado) só na primeira
    # mensagem desta passada que sobra sem cache -- a maioria das passadas de
    # `coletar()` nunca chega a precisar disso, e quando precisa, o mesmo
    # client é reaproveitado para as demais mensagens da passada em vez de
    # reconstruído a cada uma. Ver `_get_llm_client`/`_classificar_necessidade_resposta`.
    _llm_client_box: list = []

    def _get_llm_client_memo():
        if not _llm_client_box:
            _llm_client_box.append(_get_llm_client(db))
        return _llm_client_box[0]

    # Orçamento de classificações NOVAS (cache-miss) por passada -- ver
    # `_LLM_MAX_CLASSIFICACOES_POR_PASSADA`. Compartilhado entre os dois
    # laços (WhatsApp e e-mail) desta mesma chamada de `coletar()`.
    _llm_orcamento_restante = [_LLM_MAX_CLASSIFICACOES_POR_PASSADA]

    def _pode_classificar():
        if _llm_orcamento_restante[0] <= 0:
            return False
        _llm_orcamento_restante[0] -= 1
        return True

    for doc in db.collection(COLLECTION).stream():
        data = doc.to_dict() or {}
        if data.get("tipo") != "whatsapp":
            continue
        chat_id = str(data.get("chat_id") or "")
        if "*" not in allowed and chat_id not in allowed:
            continue
        if data.get("ultima_de_andre"):
            when = _as_datetime(data.get("desde"))
            if chat_id and when:
                whatsapp_last_outgoing[chat_id] = when
            continue
        task = by_chat.get(chat_id)
        inclusion_reason = "conversa_direta"
        if data.get("is_group"):
            # D1b: quando o capturador trouxe metadados da mensagem, uma menção
            # explícita ao André ou resposta a mensagem dele basta para o grupo
            # entrar. Dados antigos, sem esses campos, continuam no fallback
            # conservador e não são reprocessados.
            mentions = {str(x) for x in (data.get("mentioned_ids") or [])}
            quoted_author = str(data.get("quoted_author") or "")
            resposta_a_mim = bool(data.get("quoted_from_me") or quoted_author in andre_ids)
            relevant = bool(data.get("mentions_andre") or resposta_a_mim or (mentions & andre_ids))
            metadata_present = (data.get("mentioned_ids") is not None or data.get("quoted_msg_id") is not None
                                or data.get("quoted_from_me") is not None)
            if not relevant and (not task or metadata_present):
                continue
            inclusion_reason = "mencao" if (data.get("mentions_andre") or (mentions & andre_ids)) else ("resposta_a_mim" if resposta_a_mim else "grupo_vinculado")
        reason = _noise_reason(trecho=data.get("trecho") or "", sender="", is_email=False,
                               has_contact=chat_id in contacts, has_task=bool(task), domains=domains, endings=endings)
        if reason and not incluir_filtrados:
            filtered[reason] += 1
            continue
        wa_when = _as_datetime(data.get("desde"))
        if _resolved_by_diario(task, wa_when) and not incluir_filtrados:
            filtered["tratado_na_acao"] += 1
            continue
        if _resolved_cross_channel(contact_key=email_por_chat.get(chat_id), message_when=wa_when,
                                   outgoing_by_contact=outgoing_email) and not incluir_filtrados:
            filtered["tratado_em_outro_canal"] += 1
            continue
        # DEV-2026-0004 sub-entrega 7/9, proposta (b)(ii): último estágio,
        # depois de todo filtro gratuito -- só chama o LLM (pago, ainda que
        # cacheado por message_id) para quem sobrou. Pulado inteiramente em
        # modo auditoria (`incluir_filtrados=True`): esse modo existe para
        # inspecionar o que os filtros ESTÃO fazendo, não para gastar
        # chamadas de LLM extras sem afetar o resultado.
        if not incluir_filtrados:
            rotulo = _classificar_necessidade_resposta(
                db, _get_llm_client_memo, message_id=data.get("message_id"),
                texto=data.get("trecho") or "", is_email=False,
                pode_classificar=_pode_classificar,
            )
            filtro = _LLM_ROTULO_PARA_FILTRO.get(rotulo)
            if filtro:
                filtered[filtro] += 1
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
                               is_email=True, has_contact=False, has_task=bool(task), domains=domains, endings=endings,
                               andre_em_to=data.get("andre_em_to"))
        if reason and not incluir_filtrados:
            filtered[reason] += 1
            continue
        email_when = _as_datetime(data.get("internal_date") or data.get("analyzed_at"))
        if _resolved_by_diario(task, email_when) and not incluir_filtrados:
            filtered["tratado_na_acao"] += 1
            continue
        sender_address = (parseaddr(str(data.get("sender") or ""))[1] or "").strip().lower()
        if _resolved_cross_channel(contact_key=chat_por_email.get(sender_address), message_when=email_when,
                                   outgoing_by_contact=whatsapp_last_outgoing) and not incluir_filtrados:
            filtered["tratado_em_outro_canal"] += 1
            continue
        # DEV-2026-0004 sub-entrega 7/9, proposta (b)(ii): mesmo estágio final
        # do laço de WhatsApp acima -- `doc.id` em `email_action_suggestions`
        # é o `google_message_id` original (gravado assim em
        # `email_action_linker.py`, `suggestions_col.document(msg_id).set(...)`),
        # usado aqui só como METADE da chave de cache: `snippet`/`sender`
        # deste MESMO doc são reescritos a cada refresh de
        # `atualizar_direcao_emails_aplicados` para refletir a mensagem mais
        # recente da thread, então o fingerprint do texto (dentro de
        # `_chave_cache_classificacao`) é o que garante que uma resposta nova
        # na mesma thread não herda a classificação de uma mensagem antiga e
        # diferente que por acaso caiu no mesmo `doc.id`.
        if not incluir_filtrados:
            rotulo = _classificar_necessidade_resposta(
                db, _get_llm_client_memo, message_id=doc.id,
                texto=str(data.get("snippet") or data.get("resumo") or ""), is_email=True,
                pode_classificar=_pode_classificar,
            )
            filtro = _LLM_ROTULO_PARA_FILTRO.get(rotulo)
            if filtro:
                filtered[filtro] += 1
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
