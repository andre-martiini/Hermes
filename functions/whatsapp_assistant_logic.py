from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError


SEARCH_STOPWORDS = {
    'quais', 'qual', 'como', 'quando', 'onde', 'porque', 'por', 'pra', 'para', 'com', 'sem',
    'hoje', 'amanha', 'ontem', 'tarde', 'manha', 'noite', 'mensagem', 'mensagens', 'pedido',
    'pediu', 'grupo', 'chat', 'nesse', 'nessa', 'neste', 'naquele', 'sobre', 'dos', 'das',
    'de', 'do', 'da', 'e', 'ou', 'a', 'o', 'as', 'os', 'um', 'uma', 'me', 'diga', 'buscar',
    'ache', 'encontre', 'procure', 'mostre', 'veja', 'quero', 'preciso', 'quais', 'qual'
}
FOLLOW_UP_PATTERNS = (
    'e hoje',
    'e ontem',
    'e depois',
    'sobre isso',
    'sobre esse assunto',
    'nesse grupo',
    'neste grupo',
    'nesse chat',
    'neste chat',
    'mesmo grupo',
    'mesmo chat',
    'continuacao',
    'continuidade',
    'depois disso',
    'responderam',
    'seguiram',
)
ATTACHMENT_HINTS = {'anexo', 'anexos', 'arquivo', 'arquivos', 'pdf', 'documento', 'foto', 'imagem', 'audio', 'video'}


def get_timezone(tz_name='America/Sao_Paulo'):
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=-3))


def normalize_text(value):
    import unicodedata

    if not value:
        return ''

    normalized = unicodedata.normalize('NFD', str(value))
    normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
    normalized = normalized.lower()
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def tokenize_text(value):
    normalized = normalize_text(value)
    return [token for token in normalized.split(' ') if token]


def fuzzy_score(candidate, query_value):
    a = normalize_text(candidate)
    b = normalize_text(query_value)
    if not a or not b:
        return 0
    if a == b:
        return 1
    if b in a:
        return 0.95

    a_tokens = set(tokenize_text(a))
    b_tokens = tokenize_text(b)
    if not b_tokens:
        return 0

    overlap = 0
    for token in b_tokens:
        if token in a_tokens:
            overlap += 1
            continue

        for candidate_token in a_tokens:
            if candidate_token.startswith(token) or token.startswith(candidate_token):
                overlap += 0.65
                break

    return overlap / len(b_tokens)


def extract_chat_keyword_from_text(text):
    normalized = normalize_text(text)
    if not normalized:
        return None

    match = re.search(r'(?:grupo|chat)\s+(?:do|da|de)?\s*([a-z0-9\s]{2,})', normalized)
    if match and match.group(1):
        return match.group(1).strip()

    useful = [token for token in tokenize_text(normalized) if len(token) > 2 and token not in SEARCH_STOPWORDS]
    if not useful:
        return None
    return ' '.join(useful[:4])


def extract_search_keywords(text):
    return [token for token in tokenize_text(text) if len(token) > 2 and token not in SEARCH_STOPWORDS][:8]


def is_follow_up_command(text):
    normalized = normalize_text(text)
    if not normalized:
        return False
    if normalized.startswith('e '):
        return True
    return any(pattern in normalized for pattern in FOLLOW_UP_PATTERNS)


def resolve_search_keywords(command, previous_keywords=None):
    current_keywords = extract_search_keywords(command)
    previous_keywords = [normalize_text(keyword) for keyword in (previous_keywords or []) if normalize_text(keyword)]

    if current_keywords and previous_keywords and is_follow_up_command(command):
        combined = []
        for keyword in previous_keywords + current_keywords:
            if keyword not in combined:
                combined.append(keyword)
        return combined[:8]

    if current_keywords:
        return current_keywords[:8]

    if previous_keywords and is_follow_up_command(command):
        return previous_keywords[:8]

    return current_keywords[:8]


def parse_iso_timestamp(value):
    if not value or not isinstance(value, str):
        return None

    normalized = value.strip().replace('Z', '+00:00')
    if not normalized:
        return None

    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def resolve_time_scope(command, now=None, tz_name='America/Sao_Paulo'):
    normalized = normalize_text(command)
    if not normalized:
        return None

    tz = get_timezone(tz_name)
    reference_now = now or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)
    reference_local = reference_now.astimezone(tz)

    def build_range(start_local, end_local, label):
        return {
            'label': label,
            'start': start_local.astimezone(timezone.utc),
            'end': end_local.astimezone(timezone.utc),
        }

    day_start = reference_local.replace(hour=0, minute=0, second=0, microsecond=0)

    if 'hoje' in normalized:
        return build_range(day_start, day_start + timedelta(days=1), 'hoje')

    if 'ontem' in normalized:
        return build_range(day_start - timedelta(days=1), day_start, 'ontem')

    if 'semana passada' in normalized:
        current_week_start = day_start - timedelta(days=day_start.weekday())
        return build_range(current_week_start - timedelta(days=7), current_week_start, 'semana passada')

    if 'esta semana' in normalized or 'nessa semana' in normalized:
        current_week_start = day_start - timedelta(days=day_start.weekday())
        return build_range(current_week_start, current_week_start + timedelta(days=7), 'esta semana')

    hours_match = re.search(r'ultim(?:a|as|o|os)\s+(\d+)\s+hora', normalized)
    if hours_match:
        hours = max(1, min(int(hours_match.group(1)), 72))
        return {
            'label': f'ultimas {hours} horas',
            'start': reference_now.astimezone(timezone.utc) - timedelta(hours=hours),
            'end': reference_now.astimezone(timezone.utc),
        }

    days_match = re.search(r'ultim(?:o|os|a|as)\s+(\d+)\s+dia', normalized)
    if days_match:
        days = max(1, min(int(days_match.group(1)), 30))
        return {
            'label': f'ultimos {days} dias',
            'start': reference_now.astimezone(timezone.utc) - timedelta(days=days),
            'end': reference_now.astimezone(timezone.utc),
        }

    return None


def filter_messages_by_time_scope(items, time_scope):
    if not time_scope:
        return list(items)

    filtered = []
    for item in items:
        timestamp = parse_iso_timestamp(item.get('timestamp'))
        if not timestamp:
            continue
        if time_scope['start'] <= timestamp < time_scope['end']:
            filtered.append(item)
    return filtered


def build_chat_candidates(items, chat_keyword):
    if not chat_keyword:
        return []

    best_by_chat = {}
    for item in items:
        chat_id = item.get('chat_id')
        chat_name = item.get('chat_name')
        if not chat_id or not chat_name:
            continue

        score = fuzzy_score(chat_name, chat_keyword)
        if score < 0.28:
            continue

        current = best_by_chat.get(chat_id)
        if current and current['score'] >= score:
            continue

        best_by_chat[chat_id] = {
            'chatId': chat_id,
            'chatName': chat_name,
            'isGroup': bool(item.get('is_group')),
            'score': round(score, 2),
        }

    return sorted(best_by_chat.values(), key=lambda candidate: candidate['score'], reverse=True)[:6]


def should_prompt_for_chat_confirmation(candidates, current_chat_id=None):
    if current_chat_id or len(candidates) < 2:
        return False

    top_score = candidates[0]['score']
    second_score = candidates[1]['score']
    if top_score < 0.58:
        return True

    return (top_score - second_score) < 0.09


def score_message_relevance(message, keywords, command_text=''):
    keywords = [normalize_text(keyword) for keyword in keywords if normalize_text(keyword)]
    searchable_parts = [
        message.get('content') or '',
        message.get('transcription_text') or '',
        ' '.join(message.get('links') or []),
        message.get('author_name') or '',
        message.get('contact_name') or '',
        message.get('chat_name') or '',
        ((message.get('media') or {}).get('fileName') or ''),
    ]
    searchable = normalize_text(' '.join(searchable_parts))
    searchable_tokens = set(tokenize_text(searchable))

    score = 0.0
    matched = 0
    for keyword in keywords:
        if keyword in searchable:
            score += 2.1
            matched += 1
            continue

        for token in searchable_tokens:
            if token.startswith(keyword) or keyword.startswith(token):
                score += 1.15
                matched += 1
                break

    if keywords:
        if matched == len(keywords):
            score += 1.1
        elif matched:
            score += matched / len(keywords)
    else:
        score += 0.25

    media = message.get('media') or {}
    if media.get('url') and any(hint in normalize_text(command_text) for hint in ATTACHMENT_HINTS):
        score += 0.45

    timestamp = parse_iso_timestamp(message.get('timestamp'))
    if timestamp:
        hours_ago = max((datetime.now(timezone.utc) - timestamp).total_seconds() / 3600, 0)
        if hours_ago <= 24:
            score += 0.5
        elif hours_ago <= 72:
            score += 0.2

    return round(score, 4)


def select_relevant_messages(items, keywords, command_text='', max_messages=18):
    if not items:
        return []

    if not keywords:
        recent_items = items[:max_messages]
        return sorted(recent_items, key=lambda item: item.get('timestamp') or '')

    scored = []
    for index, item in enumerate(items):
        score = score_message_relevance(item, keywords, command_text)
        if score <= 0:
            continue
        scored.append({'index': index, 'score': score})

    scored.sort(key=lambda entry: (entry['score'], items[entry['index']].get('timestamp') or ''), reverse=True)
    if not scored:
        recent_items = items[:max_messages]
        return sorted(recent_items, key=lambda item: item.get('timestamp') or '')

    strong_hits = [entry for entry in scored if entry['score'] >= 1.15] or scored[:4]
    included_indexes = set()
    for entry in strong_hits[:8]:
        hit_index = entry['index']
        for neighbor in range(max(0, hit_index - 1), min(len(items), hit_index + 2)):
            included_indexes.add(neighbor)
        if len(included_indexes) >= max_messages:
            break

    selected = [items[index] for index in sorted(included_indexes)]
    selected.sort(key=lambda item: item.get('timestamp') or '')
    return selected[:max_messages]


def truncate_text(value, max_length=320):
    collapsed = re.sub(r'\s+', ' ', str(value or '')).strip()
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[:max_length - 1].rstrip()}…"


def format_prompt_timestamp(value, tz_name='America/Sao_Paulo'):
    timestamp = parse_iso_timestamp(value)
    if not timestamp:
        return str(value or 'sem horario')

    local = timestamp.astimezone(get_timezone(tz_name))
    return local.strftime('%Y-%m-%d %H:%M')


def build_whatsapp_context(messages):
    attachments = []
    message_ids = []
    prompt_blocks = []
    multiple_chats = len({item.get('chat_id') for item in messages if item.get('chat_id')}) > 1

    for index, message in enumerate(messages):
        media = message.get('media') or {}
        attachment = None
        if media.get('url'):
            attachment = {
                'referenceId': f"ARQ-{index + 1}",
                'messageId': message.get('id'),
                'fileName': media.get('fileName') or f"arquivo-{index + 1}",
                'mimeType': media.get('mimeType') or 'application/octet-stream',
                'url': media.get('url'),
                'contactName': message.get('author_name') or message.get('contact_name'),
                'timestamp': message.get('timestamp'),
            }
            attachments.append(attachment)

        header = [f"[MSG-{index + 1}] {format_prompt_timestamp(message.get('timestamp'))}"]
        if multiple_chats:
            header.append(f"chat={message.get('chat_name') or '(sem chat)'}")
        header.append(f"autor={message.get('author_name') or message.get('contact_name') or '(sem autor)'}")
        header.append(f"tipo={message.get('message_type') or 'text'}")

        block_lines = [' | '.join(header)]
        content = truncate_text(message.get('content'))
        transcription = truncate_text(message.get('transcription_text'))
        links = message.get('links') or []

        if content:
            block_lines.append(f"texto: {content}")

        if transcription and transcription != content:
            block_lines.append(f"transcricao: {transcription}")

        if links:
            block_lines.append(f"links: {', '.join(links[:3])}")

        if attachment:
            block_lines.append(
                f"anexo: {attachment['referenceId']} ({attachment['fileName']}, {attachment['mimeType']})"
            )

        prompt_blocks.append('\n'.join(block_lines))
        message_ids.append(message.get('id'))

    return '\n\n'.join(prompt_blocks), attachments[:8], [item for item in message_ids if item][:24]


def build_whatsapp_memory_summary(selected_chat_name=None, keywords=None, scope_label=None, result_count=0,
                                  pending_disambiguation=False):
    parts = []
    if selected_chat_name:
        parts.append(f"Grupo em foco: {selected_chat_name}.")
    else:
        parts.append("Nenhum grupo fixado.")

    if keywords:
        parts.append(f"Tema recente: {', '.join(keywords[:4])}.")
    else:
        parts.append("Tema recente: mensagens mais novas.")

    if scope_label:
        parts.append(f"Recorte: {scope_label}.")

    parts.append(f"Mensagens usadas como evidencia: {int(result_count or 0)}.")

    if pending_disambiguation:
        parts.append("Selecao de chat ainda pendente.")

    return ' '.join(parts)


def build_chat_disambiguation_markdown(chat_keyword, candidates):
    lines = [
        f"Encontrei mais de um chat parecido com **{chat_keyword or 'sua busca'}**:",
        '',
    ]
    for candidate in candidates[:5]:
        lines.append(f"- **{candidate['chatName']}**")

    lines.extend([
        '',
        'Diga o nome exato do chat que voce quer abrir e eu continuo a busca nesse contexto.',
    ])
    return '\n'.join(lines)


def build_no_results_markdown(selected_chat_name=None, keywords=None, scope_label=None):
    scope_text = f" no recorte **{scope_label}**" if scope_label else ''
    if selected_chat_name:
        head = f"Nao encontrei mensagens relevantes em **{selected_chat_name}**{scope_text}."
    else:
        head = f"Nao encontrei mensagens relevantes{scope_text}."

    suggestion = "Tente citar uma palavra do assunto, o nome do autor ou um grupo mais especifico."
    if keywords:
        suggestion = (
            f"Busquei por **{', '.join(keywords[:4])}**. "
            "Se precisar, refine com autor, data ou um trecho literal da conversa."
        )

    return '\n'.join([head, '', suggestion])
