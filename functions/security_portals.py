from datetime import datetime
import json
import re
import secrets

from firebase_functions import https_fn, options
from firebase_admin import firestore, get_app, initialize_app
from whatsapp_assistant_logic import (
    build_chat_candidates as wa_build_chat_candidates,
    build_chat_disambiguation_markdown as wa_build_chat_disambiguation_markdown,
    build_no_results_markdown as wa_build_no_results_markdown,
    build_whatsapp_context as wa_build_whatsapp_context,
    build_whatsapp_memory_summary as wa_build_whatsapp_memory_summary,
    filter_messages_by_time_scope as wa_filter_messages_by_time_scope,
    resolve_search_keywords as wa_resolve_search_keywords,
    resolve_time_scope as wa_resolve_time_scope,
    select_relevant_messages as wa_select_relevant_messages,
    should_prompt_for_chat_confirmation as wa_should_prompt_for_chat_confirmation,
)


try:
    get_app()
except ValueError:
    initialize_app()


def get_db():
    return firestore.client()


def get_genai_module():
    import google.generativeai as genai
    return genai


def get_system_api_keys(db=None):
    db = db or get_db()
    keys_doc = db.collection('system').document('api_keys').get()
    return keys_doc.to_dict() or {} if keys_doc.exists else {}


def get_gemini_key(db=None):
    keys = get_system_api_keys(db)
    return keys.get('gemini_api_key')


def require_authenticated(req: https_fn.CallableRequest):
    if not req.auth:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="Autenticacao obrigatoria."
        )
    return req.auth


def get_public_portal_config(portal_name: str, token: str, db=None):
    db = db or get_db()
    provided = str(token or '').strip()
    if not provided:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Token do portal e obrigatorio."
        )

    config_doc = db.collection('public_configs').document(portal_name).get()
    if not config_doc.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="Portal indisponivel."
        )

    config = config_doc.to_dict() or {}
    expected = str(config.get('token') or '')
    if not expected or not secrets.compare_digest(expected, provided):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="Token invalido ou expirado."
        )

    return config


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

    stopwords = {
        'quais', 'qual', 'como', 'quando', 'onde', 'porque', 'pra', 'para', 'com', 'sem',
        'hoje', 'amanha', 'ontem', 'tarde', 'manha', 'noite', 'mensagem', 'mensagens',
        'pedido', 'pediu', 'grupo', 'chat', 'nesse', 'nessa', 'neste', 'naquele',
        'sobre', 'dos', 'das', 'de', 'do', 'da', 'e', 'ou', 'a', 'o', 'as', 'os', 'um', 'uma'
    }
    useful = [token for token in tokenize_text(normalized) if len(token) > 2 and token not in stopwords]
    if not useful:
        return None
    return ' '.join(useful[:4])


def extract_search_keywords(text):
    stopwords = {
        'quais', 'qual', 'como', 'quando', 'onde', 'porque', 'pra', 'para', 'com', 'sem',
        'hoje', 'amanha', 'ontem', 'tarde', 'manha', 'noite', 'mensagem', 'mensagens',
        'pedido', 'pediu', 'grupo', 'chat', 'nesse', 'nessa', 'neste', 'naquele', 'sobre',
        'dos', 'das', 'de', 'do', 'da', 'e', 'ou', 'a', 'o', 'as', 'os', 'um', 'uma',
        'me', 'diga', 'buscar', 'ache', 'encontre', 'procure'
    }
    return [token for token in tokenize_text(text) if len(token) > 2 and token not in stopwords][:8]


def apply_keyword_filter_to_messages(items, keywords):
    normalized_keywords = [normalize_text(keyword) for keyword in keywords if normalize_text(keyword)]
    if not normalized_keywords:
        return items

    filtered = []
    for item in items:
        searchable = normalize_text(' '.join([
            str(item.get('content') or ''),
            str(item.get('transcription_text') or ''),
            ' '.join(item.get('links') or []),
            str(item.get('author_name') or ''),
            str(item.get('contact_name') or ''),
            str(item.get('chat_name') or '')
        ]))
        if all(keyword in searchable for keyword in normalized_keywords):
            filtered.append(item)
    return filtered


def build_whatsapp_context(messages):
    attachments = []
    lines = []

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

        media_line = (
            f"anexo_ref={attachment['referenceId']} anexo_nome={attachment['fileName']} anexo_url={attachment['url']}"
            if attachment else
            'anexo_ref=none'
        )

        lines.append(' | '.join([
            f"id={message.get('id')}",
            f"chat={message.get('chat_name') or '(sem chat)'}",
            f"contato={message.get('contact_name') or '(sem contato)'}",
            f"autor={message.get('author_name') or message.get('contact_name') or '(sem autor)'}",
            f"timestamp={message.get('timestamp')}",
            f"tipo={message.get('message_type')}",
            f"conteudo={message.get('content') or '(vazio)'}",
            f"transcricao={message.get('transcription_text') or '(sem transcricao)'}",
            f"links={', '.join(message.get('links') or []) or '(sem links)'}",
            media_line,
        ]))

    return '\n'.join(lines), attachments


def parse_json_response(raw_text):
    cleaned = (raw_text or '').strip()
    cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    return json.loads(cleaned)


@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=120)
def matchShoppingItemsAI(req: https_fn.CallableRequest):
    require_authenticated(req)

    data = req.data or {}
    text = str(data.get('text') or '').strip()
    catalog_items = data.get('catalogItems') or []

    if not text:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Texto do pedido e obrigatorio."
        )

    db = get_db()
    gemini_key = get_gemini_key(db)
    if not gemini_key:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Chave Gemini nao configurada."
        )

    catalog = '\n'.join([
        f"ID:{item.get('id')}|NOME:{item.get('nome')}|CAT:{item.get('categoria')}"
        for item in catalog_items if isinstance(item, dict)
    ])

    prompt = f"""Voce e um assistente de lista de compras. O usuario descreveu itens que deseja comprar.

CATALOGO DISPONIVEL (id|nome|categoria):
{catalog or '(vazio)'}

PEDIDO DO USUARIO:
"{text}"

Sua tarefa:
1. Para cada item mencionado pelo usuario, encontre o item mais proximo no catalogo (matching fuzzy/semantico tolerante a abreviacoes, sinonimos e erros).
2. Identifique a quantidade mencionada (numero + unidade se houver). Se nao mencionado, use "1 un".
3. Se nao houver correspondencia razoavel no catalogo, marque isNew=true com o nome como o usuario falou.

Responda SOMENTE com JSON valido no formato abaixo, sem markdown, sem explicacoes:
{{
  "itens": [
    {{ "catalogId": "ID_DO_ITEM_OU_null_SE_NOVO", "nomeExibido": "Nome para exibir", "quantidade": "2", "unit": "kg", "isNew": false }}
  ]
}}"""

    try:
        genai = get_genai_module()
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        result = model.generate_content(prompt)
        parsed = parse_json_response(result.text or '')
        return parsed
    except Exception as e:
        print(f"Erro em matchShoppingItemsAI: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Falha ao processar pedido com IA."
        )


@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=120)
def generatePgdFromDiariesAI(req: https_fn.CallableRequest):
    require_authenticated(req)

    data = req.data or {}
    entrega = str(data.get('entrega') or '').strip()
    descricao_entrega = str(data.get('descricaoEntrega') or '').strip()
    year_month = str(data.get('yearMonth') or '').strip()
    entries = data.get('entries') or []

    if not entrega or not isinstance(entries, list) or len(entries) == 0:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Entrega e entradas do diario sao obrigatorias."
        )

    db = get_db()
    gemini_key = get_gemini_key(db)
    if not gemini_key:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Chave Gemini nao configurada."
        )

    payload = '\n'.join([
        f"[{entry.get('data')}] tarefa={entry.get('task_titulo')} | id={entry.get('task_id')} | nota={str(entry.get('nota') or '').replace(chr(10), ' ')[:450]}"
        for entry in entries[:200]
    ])

    prompt = (
        "Voce e um assistente de prestacao de contas PGD.\n"
        "Objetivo: transformar registros de diario de bordo em trabalhos executados para uma entrega institucional.\n\n"
        f"Entrega: {entrega}\n"
        f"Descricao da entrega: {descricao_entrega}\n"
        f"Periodo alvo: {year_month}\n\n"
        "Regras:\n"
        "1. Agrupe registros proximos por tema e continuidade (pode ser dia unico ou intervalo).\n"
        "2. Escreva descricao objetiva e auditavel em portugues.\n"
        "3. Datas no formato YYYY-MM-DD.\n"
        "4. Nao invente fatos fora das notas.\n"
        "5. Se os registros originais mencionarem um numero de processo, inclua esse numero na descricao_atividade correspondente.\n"
        "6. Gere entre 1 e 12 registros.\n\n"
        f"Entrada:\n{payload}\n\n"
        "Responda SOMENTE JSON valido:\n"
        "{\n  \"registros\": [\n    {\n      \"descricao_atividade\": \"texto\",\n      \"data_inicio\": \"YYYY-MM-DD\",\n      \"data_fim\": \"YYYY-MM-DD\",\n      \"task_ids\": [\"id1\",\"id2\"]\n    }\n  ]\n}"
    )

    try:
        genai = get_genai_module()
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        result = model.generate_content(prompt)
        parsed = parse_json_response(result.text or '')
        return {'registros': parsed.get('registros') or []}
    except Exception as e:
        print(f"Erro em generatePgdFromDiariesAI: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Falha ao gerar registros PGD com IA."
        )


@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=120)
def generatePgdFromRawTextAI(req: https_fn.CallableRequest):
    require_authenticated(req)

    data = req.data or {}
    entrega = str(data.get('entrega') or '').strip()
    descricao_entrega = str(data.get('descricaoEntrega') or '').strip()
    raw_text = str(data.get('rawText') or '').strip()

    if not entrega or not raw_text:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Entrega e texto bruto sao obrigatorios."
        )

    db = get_db()
    gemini_key = get_gemini_key(db)
    if not gemini_key:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Chave Gemini nao configurada."
        )

    prompt = (
        "Voce e um assistente para prestacao de contas PGD.\n"
        "Converta o texto bruto abaixo em registros estruturados de execucao.\n\n"
        f"Entrega: {entrega}\n"
        f"Descricao da entrega: {descricao_entrega}\n\n"
        "Regras obrigatorias:\n"
        "1. Identifique corretamente cada data presente no texto.\n"
        "2. Se houver varias tarefas no mesmo dia, agrupe tudo em um unico registro desse dia.\n"
        "3. Quando houver continuidade natural entre dias, voce pode usar intervalo.\n"
        "4. Refine a descricao para ficar objetiva e auditavel.\n"
        "5. Nao invente fatos fora do texto.\n"
        "6. Datas devem estar no formato YYYY-MM-DD.\n"
        "7. Evite fragmentar em muitos registros curtos.\n"
        "8. Se o texto bruto mencionar um numero de processo, inclua esse numero na descricao_atividade correspondente.\n\n"
        f"Texto bruto:\n{raw_text}\n\n"
        "Responda APENAS JSON valido:\n"
        "{\n  \"registros\": [\n    {\n      \"descricao_atividade\": \"texto objetivo\",\n      \"data_inicio\": \"YYYY-MM-DD\",\n      \"data_fim\": \"YYYY-MM-DD\"\n    }\n  ]\n}"
    )

    try:
        genai = get_genai_module()
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        result = model.generate_content(prompt)
        parsed = parse_json_response(result.text or '')
        return {'registros': parsed.get('registros') or []}
    except Exception as e:
        print(f"Erro em generatePgdFromRawTextAI: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Falha ao estruturar texto PGD com IA."
        )


@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
    timeout_sec=120
)
def askWhatsAppAssistantSecure(req: https_fn.CallableRequest):
    require_authenticated(req)

    data = req.data or {}
    command = str(data.get('command') or '').strip()
    context = data.get('context') if isinstance(data.get('context'), dict) else {}
    conversation_history = data.get('conversationHistory') if isinstance(data.get('conversationHistory'), list) else []

    if not command:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Comando e obrigatorio."
        )

    db = get_db()
    gemini_key = get_gemini_key(db)
    if not gemini_key:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Chave Gemini nao configurada."
        )

    try:
        docs = db.collection('whatsapp_messages').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(600).stream()
        recent = []
        for snap in docs:
            item = snap.to_dict() or {}
            item['id'] = snap.id
            recent.append(item)

        selected_chat_id = context.get('selectedChatId')
        selected_chat_name = context.get('selectedChatName')
        previous_keywords = context.get('lastSearchKeywords') or []
        chat_keyword = extract_chat_keyword_from_text(command)
        candidates = wa_build_chat_candidates(recent, chat_keyword)

        user_requested_chat_switch = bool(chat_keyword and (
            not selected_chat_name or fuzzy_score(selected_chat_name, chat_keyword) < 0.82
        ))
        pending_disambiguation = False
        assumed_chat = False

        if user_requested_chat_switch:
            if candidates and not wa_should_prompt_for_chat_confirmation(candidates):
                selected_chat_id = candidates[0]['chatId']
                selected_chat_name = candidates[0]['chatName']
                assumed_chat = True
            elif candidates:
                pending_disambiguation = True
        elif not selected_chat_id and candidates:
            if not wa_should_prompt_for_chat_confirmation(candidates):
                selected_chat_id = candidates[0]['chatId']
                selected_chat_name = candidates[0]['chatName']
                assumed_chat = True
            else:
                pending_disambiguation = True

        keywords = wa_resolve_search_keywords(command, previous_keywords)
        time_scope = wa_resolve_time_scope(command)
        scope_label = time_scope['label'] if time_scope else None

        response_context = {
            'selectedChatId': selected_chat_id,
            'selectedChatName': selected_chat_name,
            'candidateChats': candidates,
            'lastSearchKeywords': keywords,
            'searchScopeLabel': scope_label,
            'pendingDisambiguation': pending_disambiguation,
        }

        if pending_disambiguation:
            memory_summary = wa_build_whatsapp_memory_summary(
                selected_chat_name=selected_chat_name,
                keywords=keywords,
                scope_label=scope_label,
                result_count=0,
                pending_disambiguation=True,
            )
            response_context['memorySummary'] = memory_summary
            response_context['resultCount'] = 0
            response_context['lastMessageIds'] = []
            return {
                'markdown': wa_build_chat_disambiguation_markdown(chat_keyword, candidates),
                'attachments': [],
                'context': response_context,
            }

        items = recent
        if selected_chat_id:
            items = [item for item in items if item.get('chat_id') == selected_chat_id]
            if not selected_chat_name and items:
                selected_chat_name = items[0].get('chat_name')
                response_context['selectedChatName'] = selected_chat_name

        scoped_items = wa_filter_messages_by_time_scope(items, time_scope)
        if time_scope and not scoped_items:
            memory_summary = wa_build_whatsapp_memory_summary(
                selected_chat_name=selected_chat_name,
                keywords=keywords,
                scope_label=scope_label,
                result_count=0,
            )
            response_context['memorySummary'] = memory_summary
            response_context['resultCount'] = 0
            response_context['lastMessageIds'] = []
            return {
                'markdown': wa_build_no_results_markdown(
                    selected_chat_name=selected_chat_name,
                    keywords=keywords,
                    scope_label=scope_label,
                ),
                'attachments': [],
                'context': response_context,
            }

        search_base = scoped_items if scoped_items else items
        selected_messages = wa_select_relevant_messages(search_base, keywords, command, max_messages=18)

        if not selected_messages:
            memory_summary = wa_build_whatsapp_memory_summary(
                selected_chat_name=selected_chat_name,
                keywords=keywords,
                scope_label=scope_label,
                result_count=0,
            )
            response_context['memorySummary'] = memory_summary
            response_context['resultCount'] = 0
            response_context['lastMessageIds'] = []
            return {
                'markdown': wa_build_no_results_markdown(
                    selected_chat_name=selected_chat_name,
                    keywords=keywords,
                    scope_label=scope_label,
                ),
                'attachments': [],
                'context': response_context,
            }

        context_block, attachments, message_ids = wa_build_whatsapp_context(selected_messages)
        memory_summary = wa_build_whatsapp_memory_summary(
            selected_chat_name=selected_chat_name,
            keywords=keywords,
            scope_label=scope_label,
            result_count=len(selected_messages),
        )
        response_context['memorySummary'] = memory_summary
        response_context['resultCount'] = len(selected_messages)
        response_context['lastMessageIds'] = message_ids
        response_context['pendingDisambiguation'] = False

        recent_conversation_lines = []
        for message in conversation_history[-10:]:
            if not isinstance(message, dict):
                continue
            speaker = 'Usuario' if message.get('role') == 'user' else 'Assistente'
            message_text = re.sub(r'\s+', ' ', str(message.get('text') or '')).strip()[:240]
            recent_conversation_lines.append(f"{speaker}: {message_text}")
        recent_conversation = '\n'.join(recent_conversation_lines)

        system_instruction = (
            "Voce e o assistente de consulta de WhatsApp do Hermes.\n"
            "Responda apenas com base nas evidencias fornecidas.\n"
            "Nao invente mensagens, anexos, datas ou participantes.\n"
            "Se os dados estiverem incompletos, diga isso explicitamente.\n"
            "Se um grupo foi assumido automaticamente, mencione isso com clareza.\n"
            "Quando houver anexos, cite o referenceId no formato [ARQ-N].\n"
            "Prefira markdown leve, objetivo e facil de escanear."
        )
        prompt = (
            f"Pedido atual do usuario: {command}\n"
            f"Memoria anterior da sessao: {context.get('memorySummary') or '(sem memoria anterior)'}\n"
            f"Resumo atualizado da sessao: {memory_summary}\n"
            f"Grupo selecionado: {selected_chat_name or 'nenhum'} ({selected_chat_id or 'sem id'})\n"
            f"Grupo assumido automaticamente nesta resposta: {'sim' if assumed_chat else 'nao'}\n"
            f"Candidatos de chat parecidos: {json.dumps(candidates, ensure_ascii=False)}\n"
            f"Historico recente da conversa:\n{recent_conversation or '(sem historico)'}\n\n"
            f"Evidencias recuperadas ({len(selected_messages)} mensagens):\n{context_block}\n\n"
            "Estruture a resposta assim, quando fizer sentido:\n"
            "1. Resposta direta ao pedido.\n"
            "2. Pontos de apoio ou resumo curto das mensagens.\n"
            "3. Incertezas ou proximos passos, somente se realmente houver lacuna.\n"
        )

        genai = get_genai_module()
        genai.configure(api_key=gemini_key)
        generation_config = {
            'temperature': 0.25,
            'top_p': 0.9,
            'max_output_tokens': 900,
        }
        try:
            model = genai.GenerativeModel('gemini-3.1-flash-lite', system_instruction=system_instruction)
            result = model.generate_content(prompt, generation_config=generation_config)
        except TypeError:
            model = genai.GenerativeModel('gemini-3.1-flash-lite')
            result = model.generate_content([system_instruction, prompt], generation_config=generation_config)
        markdown = (result.text or '').strip() or 'Nao consegui gerar uma resposta com o contexto atual.'

        return {
            'markdown': markdown,
            'attachments': attachments,
            'context': response_context,
        }
    except https_fn.HttpsError:
        raise
    except Exception as e:
        print(f"Erro em askWhatsAppAssistantSecure: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Falha ao consultar mensagens do WhatsApp."
        )


@https_fn.on_call(timeout_sec=60)
def getPublicFinancePortal(req: https_fn.CallableRequest):
    data = req.data or {}
    token = data.get('token')
    db = get_db()
    config = get_public_portal_config('finance_portal', token, db)

    docs = db.collection('finance_transactions').where('origin', '==', 'external').stream()
    transactions = []
    for snap in docs:
        item = snap.to_dict() or {}
        if item.get('status') == 'deleted':
            continue
        item['id'] = snap.id
        transactions.append(item)
    transactions.sort(key=lambda entry: str(entry.get('date') or ''), reverse=True)

    return {
        'valid': True,
        'settings': {
            'externalSpendingLimit': float(config.get('limit') or 0),
        },
        'transactions': transactions,
    }


@https_fn.on_call(timeout_sec=60)
def submitPublicFinanceTransaction(req: https_fn.CallableRequest):
    data = req.data or {}
    token = data.get('token')
    description = str(data.get('description') or '').strip()
    amount = data.get('amount')

    if not description:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Descricao e obrigatoria."
        )

    try:
        numeric_amount = float(amount)
    except Exception:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Valor invalido."
        )

    db = get_db()
    get_public_portal_config('finance_portal', token, db)

    now = datetime.now()
    day = now.day
    sprint = 1 if day < 8 else 2 if day < 15 else 3 if day < 22 else 4

    ref = db.collection('finance_transactions').document()
    ref.set({
        'description': description,
        'amount': numeric_amount,
        'date': now.isoformat(),
        'sprint': sprint,
        'category': 'Gasto Externo',
        'status': 'active',
        'origin': 'external'
    })

    return {'success': True, 'id': ref.id}


@https_fn.on_call(timeout_sec=60)
def getPublicShoppingPortal(req: https_fn.CallableRequest):
    data = req.data or {}
    token = data.get('token')
    db = get_db()
    get_public_portal_config('shopping_portal', token, db)

    docs = db.collection('shopping_items').stream()
    items = []
    for snap in docs:
        item = snap.to_dict() or {}
        item['id'] = snap.id
        items.append(item)

    return {'valid': True, 'items': items}


@https_fn.on_call(timeout_sec=60)
def mutatePublicShoppingPortal(req: https_fn.CallableRequest):
    data = req.data or {}
    token = data.get('token')
    action = str(data.get('action') or '').strip()
    item_id = data.get('itemId')
    value = data.get('value')
    db = get_db()
    get_public_portal_config('shopping_portal', token, db)

    if action in {'toggle_planned', 'toggle_purchased', 'update_quantity'} and not item_id:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="itemId e obrigatorio."
        )

    if action == 'toggle_planned':
        ref = db.collection('shopping_items').document(str(item_id))
        snap = ref.get()
        if not snap.exists:
            raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Item nao encontrado.")
        item = snap.to_dict() or {}
        ref.update({'isPlanned': not bool(item.get('isPlanned')), 'isPurchased': False})
    elif action == 'toggle_purchased':
        ref = db.collection('shopping_items').document(str(item_id))
        snap = ref.get()
        if not snap.exists:
            raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Item nao encontrado.")
        item = snap.to_dict() or {}
        ref.update({'isPurchased': not bool(item.get('isPurchased'))})
    elif action == 'update_quantity':
        db.collection('shopping_items').document(str(item_id)).update({'quantidade': str(value or '')})
    elif action in {'clear_planning', 'finalize'}:
        batch = db.batch()
        for snap in db.collection('shopping_items').stream():
            item = snap.to_dict() or {}
            if item.get('isPlanned') or item.get('isPurchased'):
                batch.update(snap.reference, {'isPlanned': False, 'isPurchased': False})
        batch.commit()
    else:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Acao invalida."
        )

    return {'success': True}


@https_fn.on_call(timeout_sec=60)
def getPublicScholarshipProject(req: https_fn.CallableRequest):
    data = req.data or {}
    project_id = str(data.get('projectId') or '').strip()
    token = str(data.get('token') or '').strip()

    if not project_id or not token:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Projeto e token sao obrigatorios."
        )

    db = get_db()
    snap = db.collection('projetos').document(project_id).get()
    if not snap.exists:
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Projeto nao encontrado.")

    project = snap.to_dict() or {}
    expected = str(project.get('public_registration_token') or '')
    if not expected or not secrets.compare_digest(expected, token):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="Link invalido ou expirado."
        )

    return {
        'valid': True,
        'project': {
            'id': snap.id,
            'nome': project.get('nome'),
        }
    }


@https_fn.on_call(timeout_sec=60)
def submitPublicScholarshipRegistration(req: https_fn.CallableRequest):
    data = req.data or {}
    project_id = str(data.get('projectId') or '').strip()
    token = str(data.get('token') or '').strip()
    form = data.get('formData') or {}

    if not project_id or not token or not isinstance(form, dict):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Dados do cadastro invalidos."
        )

    required_fields = ['nome', 'cpf', 'rg', 'email', 'telefone']
    missing = [field for field in required_fields if not str(form.get(field) or '').strip()]
    if missing:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message=f"Campos obrigatorios ausentes: {', '.join(missing)}"
        )

    db = get_db()
    project_snap = db.collection('projetos').document(project_id).get()
    if not project_snap.exists:
        raise https_fn.HttpsError(code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Projeto nao encontrado.")

    project = project_snap.to_dict() or {}
    expected = str(project.get('public_registration_token') or '')
    if not expected or not secrets.compare_digest(expected, token):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="Link invalido ou expirado."
        )

    cpf = str(form.get('cpf') or '').strip()
    perfil_data = {
        'nome': str(form.get('nome') or '').strip(),
        'cpf': cpf,
        'rg': str(form.get('rg') or '').strip(),
        'email': str(form.get('email') or '').strip(),
        'telefone': str(form.get('telefone') or '').strip(),
        'endereco': str(form.get('endereco') or '').strip(),
        'lattes': str(form.get('lattes') or '').strip(),
        'campus': str(form.get('campus') or '').strip(),
        'curso': str(form.get('curso') or '').strip(),
        'dados_bancarios': {
            'banco': str(form.get('banco') or '').strip(),
            'agencia': str(form.get('agencia') or '').strip(),
            'conta': str(form.get('conta') or '').strip(),
            'chave_pix': str(form.get('chave_pix') or '').strip(),
        },
        'data_atualizacao': datetime.now().isoformat(),
    }

    pessoas = list(db.collection('perfil_pessoas').where('cpf', '==', cpf).limit(1).stream())
    if pessoas:
        pessoa_ref = pessoas[0].reference
        pessoa_ref.update(perfil_data)
        pessoa_id = pessoas[0].id
    else:
        pessoa_ref = db.collection('perfil_pessoas').document()
        pessoa_ref.set({
            **perfil_data,
            'data_criacao': datetime.now().isoformat(),
        })
        pessoa_id = pessoa_ref.id

    existing_links = [
        snap for snap in db.collection('vinculos_projeto')
        .where('projeto_id', '==', project_id)
        .where('pessoa_id', '==', pessoa_id)
        .stream()
        if normalize_text((snap.to_dict() or {}).get('status') or '') == normalize_text('Em regularizacao')
    ]
    if not existing_links:
        db.collection('vinculos_projeto').document().set({
            'pessoa_id': pessoa_id,
            'projeto_id': project_id,
            'data_inicio': datetime.now().date().isoformat(),
            'data_fim_prevista': '',
            'status': 'Em regularização',
            'tipo_bolsa_id': '',
            'percentual_recebimento': 100,
            'valor_bolsa_mensal_atual': 0
        })

    return {'success': True}
