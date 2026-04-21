"""
Hermes Core Logic — Telegram Integration
Webhook receiver + Firestore-triggered async processor.
"""
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Optional

import requests as _requests
from firebase_admin import firestore, get_app, initialize_app, storage
from firebase_functions import firestore_fn, https_fn, options
from firebase_functions.firestore_fn import Event, Change, DocumentSnapshot
from google.cloud.firestore_v1 import DocumentReference

try:
    get_app()
except ValueError:
    initialize_app()

_MAX_HISTORY_TURNS = 20
_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_db():
    return firestore.client()


def _get_api_keys(db=None):
    db = db or _get_db()
    doc = db.collection("system").document("api_keys").get()
    return doc.to_dict() or {} if doc.exists else {}


def _get_telegram_token(db=None) -> str:
    keys = _get_api_keys(db)
    token = keys.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("telegram_bot_token não configurado em system/api_keys.")
    return token


def _get_allowed_chat_id() -> Optional[str]:
    return os.environ.get("ALLOWED_TELEGRAM_CHAT_ID")


def _send_telegram_message(token: str, chat_id: str | int, text: str, parse_mode: str = "HTML"):
    """POST direto à Telegram Bot API."""
    # Telegram HTML: truncate at 4096 chars
    if len(text) > 4096:
        text = text[:4090] + "\n..."
    resp = _requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
        timeout=30,
    )
    if not resp.ok:
        print(f"[Telegram] sendMessage failed: {resp.status_code} {resp.text[:300]}")


def _send_telegram_typing(token: str, chat_id: str | int):
    try:
        _requests.post(
            f"https://api.telegram.org/bot{token}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5,
        )
    except Exception:
        pass


def _get_telegram_file(token: str, file_id: str) -> dict:
    """Calls getFile and returns the file metadata dict."""
    resp = _requests.get(
        f"https://api.telegram.org/bot{token}/getFile",
        params={"file_id": file_id},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("result", {})


def _download_telegram_file(token: str, file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    resp = _requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


# ---------------------------------------------------------------------------
# Session state machine
# ---------------------------------------------------------------------------

def _get_session(db, chat_id: str) -> dict:
    doc = db.collection("telegram_sessions").document(chat_id).get()
    return doc.to_dict() or {"chat_id": chat_id, "contexto_ativo": "geral", "history": []}


def _save_session(db, chat_id: str, session: dict):
    session["updated_at"] = firestore.SERVER_TIMESTAMP
    db.collection("telegram_sessions").document(chat_id).set(session)


def _handle_command(text: str, session: dict) -> Optional[str]:
    """
    Returns a reply string if the message is a state-machine command, else None.
    Side-effects: mutates session.
    """
    text = (text or "").strip()
    m = re.match(r"^/contexto\s+(.+)$", text, re.IGNORECASE)
    if m:
        ctx = m.group(1).strip()
        session["contexto_ativo"] = ctx
        session["history"] = []  # fresh history for new context
        return f"Contexto ativo definido como <b>{ctx}</b>. Histórico reiniciado."

    if re.match(r"^/sair$", text, re.IGNORECASE):
        previous = session.get("contexto_ativo", "geral")
        session["contexto_ativo"] = "geral"
        session["history"] = []
        return f"Saindo do contexto <b>{previous}</b>. Voltando ao modo geral."

    if re.match(r"^/start$", text, re.IGNORECASE):
        return (
            "👋 Olá! Sou o <b>Hermes Copiloto</b>.\n\n"
            "Comandos disponíveis:\n"
            "• <code>/contexto [nome]</code> — foca em uma área específica (ex: /contexto finanças)\n"
            "• <code>/sair</code> — retorna ao modo geral\n\n"
            "Envie texto, áudio ou arquivos. Tamanho máximo: 20 MB."
        )

    if re.match(r"^/status$", text, re.IGNORECASE):
        ctx = session.get("contexto_ativo", "geral")
        turns = len(session.get("history", [])) // 2
        return f"Contexto ativo: <b>{ctx}</b>\nTurnos no histórico: {turns}"

    return None


# ---------------------------------------------------------------------------
# Audio transcription (reusing Groq / Gemini pattern from main.py)
# ---------------------------------------------------------------------------

def _transcribe_audio_bytes(audio_bytes: bytes, extension: str, db) -> str:
    import base64 as _b64
    keys = _get_api_keys(db)
    groq_key = keys.get("groq_api_key")
    if not groq_key:
        return "[Transcrição indisponível: chave Groq não configurada]"

    from groq import Groq
    client = Groq(api_key=groq_key)
    suffix = extension if extension.startswith(".") else f".{extension}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(tmp_path), f),
                model="whisper-large-v3-turbo",
                response_format="json",
                language="pt",
                temperature=0.0,
            )
        return transcription.text or ""
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Media upload to Firebase Storage
# ---------------------------------------------------------------------------

def _upload_to_storage(file_bytes: bytes, file_name: str, mime_type: str, chat_id: str) -> str:
    """Uploads to Firebase Storage and returns the public URL (gs://)."""
    bucket = storage.bucket()
    path = f"telegram_uploads/{chat_id}/{file_name}"
    blob = bucket.blob(path)
    blob.upload_from_string(file_bytes, content_type=mime_type)
    blob.make_public()
    return blob.public_url


# ---------------------------------------------------------------------------
# Gemini orchestration
# ---------------------------------------------------------------------------

def _build_system_instruction(copilot_core: str, copilot_soul: str, contexto_ativo: str) -> str:
    from datetime import datetime as _dt
    today = _dt.now(timezone.utc).strftime("%Y-%m-%d")
    ctx_hint = (
        f"\n\n<b>Contexto ativo:</b> {contexto_ativo}"
        if contexto_ativo != "geral"
        else ""
    )
    return (
        f"Você é o Copiloto Hermes, estrategista sênior de processos. Hoje é {today}."
        f"{ctx_hint}\n\n"
        "## CORE ESTÁTICO DO COPILOTO\n"
        f"{copilot_core}\n\n"
        "## PERSONALIDADE DINÂMICA ATUAL\n"
        f"{copilot_soul}\n\n"
        "## CANAL DE COMUNICAÇÃO: TELEGRAM\n"
        "REGRA ABSOLUTA DE FORMATAÇÃO: Você está respondendo via Telegram. "
        "Use EXCLUSIVAMENTE as seguintes tags HTML suportadas pelo Telegram: "
        "<b>negrito</b>, <i>itálico</i>, <code>código inline</code>, <pre>bloco de código</pre>. "
        "PROIBIDO usar Markdown (asteriscos, underlines, backticks, #, ##). "
        "Listas: use • ou - como prefixo de linha, sem Markdown. "
        "Mantenha respostas concisas — Telegram tem limite de 4096 caracteres por mensagem.\n\n"
        "## REGRAS ABSOLUTAS\n"
        "1. JAMAIS expanda siglas arbitrariamente.\n"
        "2. Se qualquer ferramenta retornar campo 'erro', reproduza o erro literal.\n"
        "3. Para criar uma ação, apresente um draft primeiro e aguarde confirmação explícita.\n"
        "4. Links de tarefas: use o formato task:{ID} no texto (ex: 'Ação task:abc123').\n"
        "5. Se o usuário corrigir um procedimento, acione registrar_correcao_procedimento silenciosamente.\n"
        "6. Acione salvar_memoria_global apenas para fatos duráveis e preferências estáveis.\n"
    )


def _run_gemini_turn(
    db,
    gemini_key: str,
    system_instruction: str,
    history: list,
    user_message_parts: list,
    tools_list: list,
    function_map: dict,
) -> str:
    """Runs a full Gemini multi-turn exchange and returns the final text response."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=gemini_key)
    model_id = "gemini-3-flash-preview"

    chat = client.chats.create(
        model=model_id,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools_list,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
        history=history,
    )

    response = chat.send_message(user_message_parts)

    # Agentic loop — processa tool calls até obter resposta de texto
    for _ in range(10):
        if not response.candidates:
            break
        candidate = response.candidates[0]
        if candidate.finish_reason and candidate.finish_reason.name not in ("STOP", "MAX_TOKENS", ""):
            break

        # Coleta function calls neste turno
        func_calls = []
        for part in (candidate.content.parts or []):
            if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                func_calls.append(part.function_call)

        if not func_calls:
            break

        # Executa todas as tool calls e coleta resultados
        tool_results = []
        for fc in func_calls:
            fn = function_map.get(fc.name)
            if fn is None:
                result_text = f"Ferramenta '{fc.name}' não encontrada."
            else:
                try:
                    kwargs = dict(fc.args or {})
                    result = fn(**kwargs)
                    result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                except Exception as tool_err:
                    result_text = f"Erro ao executar {fc.name}: {tool_err}"
            tool_results.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result_text},
                )
            )

        response = chat.send_message(tool_results)

    # Extrai texto final
    text_parts = []
    if response.candidates:
        for part in (response.candidates[0].content.parts or []):
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
    return "\n".join(text_parts).strip() or "Não consegui gerar uma resposta. Tente novamente."


# ---------------------------------------------------------------------------
# Main processing logic
# ---------------------------------------------------------------------------

def _process_telegram_message(db, data: dict):
    """Full processing pipeline for one incoming Telegram message."""
    from google.genai import types
    from tools.busca_grafo import buscar_tarefas
    from tools.busca_acervo import buscar_acervo

    chat_id = str(data.get("chat_id", ""))
    text = (data.get("text") or "").strip()
    file_info = data.get("file_info")   # {file_id, file_unique_id, file_size, mime_type, file_name}
    audio_info = data.get("audio_info") # {file_id, file_size, mime_type, duration}
    media_bytes_b64 = data.get("media_bytes_b64")  # base64 of already-downloaded file

    if not chat_id:
        return

    keys = _get_api_keys(db)
    gemini_key = keys.get("gemini_api_key")
    token = keys.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not gemini_key or not token:
        _send_telegram_message(token, chat_id, "⚠️ Configuração incompleta. Contate o administrador.")
        return

    session = _get_session(db, chat_id)

    # --- Command handler ---
    if text.startswith("/"):
        reply = _handle_command(text, session)
        if reply:
            _save_session(db, chat_id, session)
            _send_telegram_message(token, chat_id, reply)
            return
        # Unknown command — fall through to Gemini

    # --- Load copilot personality ---
    try:
        core_doc = db.collection("system").document("copilot_core").get()
        copilot_core = (core_doc.to_dict() or {}).get("content", "") if core_doc.exists else ""
    except Exception:
        copilot_core = ""
    try:
        soul_doc = db.collection("system").document("copilot_soul").get()
        copilot_soul = (soul_doc.to_dict() or {}).get("content", "") if soul_doc.exists else ""
    except Exception:
        copilot_soul = ""

    contexto_ativo = session.get("contexto_ativo", "geral")
    system_instruction = _build_system_instruction(copilot_core, copilot_soul, contexto_ativo)

    # --- Restore history (trimmed) ---
    raw_history = session.get("history", [])
    # Keep last N turns (each turn = user + model = 2 items)
    if len(raw_history) > _MAX_HISTORY_TURNS * 2:
        raw_history = raw_history[-((_MAX_HISTORY_TURNS * 2)):]
    history = [
        types.Content(role=h["role"], parts=[types.Part(text=p["text"]) for p in h.get("parts", [])])
        for h in raw_history
        if h.get("role") and h.get("parts")
    ]

    # --- Resolve user message parts ---
    user_parts = []
    file_context_text = ""

    # Audio transcription
    if audio_info and media_bytes_b64:
        import base64
        audio_bytes = base64.b64decode(media_bytes_b64)
        mime = audio_info.get("mime_type", "audio/ogg")
        raw_ext = mime.split("/")[-1]
        ext = "ogg" if raw_ext in ("ogg", "oga") else raw_ext
        _send_telegram_typing(token, chat_id)
        try:
            transcription = _transcribe_audio_bytes(audio_bytes, ext, db)
        except Exception as transcribe_err:
            print(f"[Core] Transcription error: {transcribe_err}")
            import traceback; traceback.print_exc()
            transcription = None
        if transcription:
            file_context_text = f"[Transcrição de áudio]: {transcription}"
            user_parts.append(types.Part(text=file_context_text))
        else:
            user_parts.append(types.Part(text="[Áudio recebido mas transcrição falhou]"))

    # File/document
    elif file_info and media_bytes_b64:
        import base64, uuid as _uuid
        file_bytes = base64.b64decode(media_bytes_b64)
        fname = file_info.get("file_name") or f"upload_{_uuid.uuid4().hex[:8]}"
        mime = file_info.get("mime_type", "application/octet-stream")
        try:
            pub_url = _upload_to_storage(file_bytes, fname, mime, chat_id)
            file_context_text = (
                f"[Arquivo recebido]: {fname} ({mime})\n"
                f"URL: {pub_url}\n"
                "Analise este arquivo, identifique o que ele mostra e sugira como ele se relaciona ao contexto atual."
            )
        except Exception as up_err:
            file_context_text = f"[Arquivo recebido: {fname}] (falha no upload: {up_err})"
        user_parts.append(types.Part(text=file_context_text))

    # Text
    if text:
        user_parts.append(types.Part(text=text))

    if not user_parts:
        user_parts.append(types.Part(text="[Mensagem sem conteúdo processável]"))

    # --- Memory context ---
    try:
        from knowledge_graph import _get_embedding
        query_text = text or file_context_text or ""
        if query_text:
            memory_docs = (
                db.collection("knowledge_nodes")
                .order_by("data_criacao", direction=firestore.Query.DESCENDING)
                .limit(4)
                .stream()
            )
            mem_lines = []
            for m_doc in memory_docs:
                m = m_doc.to_dict() or {}
                fato = m.get("fato", "")
                cat = m.get("categoria", "")
                if fato:
                    mem_lines.append(f"- [{cat}] {fato}")
            if mem_lines:
                mem_text = "## MEMÓRIA GLOBAL ATIVA\n" + "\n".join(mem_lines)
                system_instruction = system_instruction + "\n\n" + mem_text
    except Exception:
        pass

    # --- Tool definitions ---
    def consultar_historico_acoes(
        query: str,
        area_tematica: str = None,
        data_limite_inicio: str = None,
        data_limite_fim: str = None,
    ):
        """Busca ações e tarefas no Hermes. Use data_limite_inicio/fim (YYYY-MM-DD) para filtrar por prazo."""
        from tools.busca_grafo import buscar_tarefas

        res = buscar_tarefas(query, area_tematica=area_tematica, match_mode="all",
                             data_limite_inicio=data_limite_inicio, data_limite_fim=data_limite_fim)
        if not res.get("resultados"):
            res = buscar_tarefas(query, area_tematica=area_tematica, match_mode="any",
                                 data_limite_inicio=data_limite_inicio, data_limite_fim=data_limite_fim)
        if res.get("erro"):
            return f"⚠️ [ERRO] {res['erro']}"
        resultados = res.get("resultados", [])
        if not resultados:
            return f"Nenhum registro encontrado para '{query}'."
        lines = ["--- TAREFAS ENCONTRADAS ---"]
        for r in resultados:
            lines.append(
                f"ID: {r['id']} | {r['titulo']} | {r['status']} | "
                f"Prazo: {r.get('data_limite','N/A')} | Área: {r['area']}"
            )
        return "\n".join(lines)

    def buscar_arquivos_acervo(query: str):
        """Busca documentos, manuais e arquivos no Acervo Global do Hermes."""
        from tools.busca_acervo import buscar_acervo
        res = buscar_acervo(query)
        if res.get("erro"):
            return f"⚠️ [ERRO] {res['erro']}"
        resultados = res.get("resultados", [])
        if not resultados:
            return "Nenhum documento encontrado."
        return "\n\n".join(
            f"DOC: {r['titulo']} | FONTE: {r['fonte']}\nTRECHO: {r['trecho']}"
            for r in resultados
        )

    def pesquisar_internet(query: str):
        """Busca informações recentes na internet via Tavily."""
        try:
            tavily_key = _get_api_keys(db).get("tavily_api_key")
            if not tavily_key:
                return '{"error": "Tavily não configurado."}'
            resp = _requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "search_depth": "advanced",
                      "include_answer": True, "include_raw_content": False, "max_results": 5},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            parts = []
            if data.get("answer"):
                parts.append(f"RESPOSTA: {data['answer']}\n")
            for r in data.get("results", []):
                parts.append(f"FONTE: {r.get('title','')} ({r.get('url','')})\n{r.get('content','')}")
            return "\n\n".join(parts) or "Sem resultados."
        except Exception as e:
            return f'{{"error": "{e}"}}'

    def ler_pagina_web(url: str):
        """Lê o conteúdo de uma URL via Jina Reader."""
        try:
            resp = _requests.get(f"https://r.jina.ai/{url}",
                                 headers={"Accept": "text/markdown"}, timeout=25)
            if resp.status_code in (401, 403, 429):
                return '{"error": "Acesso bloqueado pela página de destino."}'
            resp.raise_for_status()
            content = resp.text.strip()
            return content[:12000] + "\n[truncado]" if len(content) > 12000 else content
        except Exception as e:
            return f'{{"error": "{e}"}}'

    def criar_acao_no_sistema(
        titulo: str,
        descricao: str = "",
        area_tematica: str = "GERAL",
        data_limite: str = None,
        tipo_acao: str = "fast",
        tags: list[str] = None,
        notas: str = "",
        plano_acao: list[str] = None,
    ):
        """
        Cria uma nova ação no Hermes. Apresente draft ao usuário antes de chamar.
        Retorna 'OK|{ID}' em caso de sucesso ou 'ERRO|{detalhe}'.
        """
        import uuid as _uuid
        now_iso = datetime.now(timezone.utc).isoformat()
        today = (datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        if not data_limite:
            data_limite = today
        task_id = str(_uuid.uuid4())[:20]
        plano_convertido = [
            {"id": str(_uuid.uuid4())[:8], "text": str(p), "completed": False}
            for p in (plano_acao or []) if str(p).strip()
        ]
        doc = {
            "id": task_id,
            "titulo": titulo.strip(),
            "descricao": descricao or "",
            "area_tematica": area_tematica or "GERAL",
            "data_limite": data_limite,
            "tipo_acao": tipo_acao or "fast",
            "tags": tags or [],
            "notas": notas or "",
            "plano_acao": plano_convertido,
            "status": "em andamento",
            "criado_em": now_iso,
            "data_atualizacao": now_iso,
            "origem_ingestao": "telegram",
            "acompanhamento": [],
        }
        try:
            db.collection("tarefas").document(task_id).set(doc)
            return f"OK|{task_id}"
        except Exception as e:
            return f"ERRO|{e}"

    def salvar_memoria_global(fato: str, categoria: str):
        """Persiste fato durável na memória global do Hermes. Apenas para regras estáveis e preferências permanentes."""
        try:
            import uuid as _uuid
            node_id = str(_uuid.uuid4())[:16]
            db.collection("knowledge_nodes").document(node_id).set({
                "id": node_id,
                "fato": fato,
                "categoria": categoria,
                "data_criacao": datetime.now(timezone.utc).isoformat(),
                "origem": "telegram",
            })
            return json.dumps({"status": "saved", "id": node_id}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "reason": str(e)}, ensure_ascii=False)

    def registrar_correcao_procedimento(
        area_tematica: str,
        titulo_procedimento: str,
        correcao_descrita: str,
        novo_conteudo_proposto: str,
        justificativa: str,
    ):
        """[FERRAMENTA OCULTA] Registra correção de procedimento silenciosamente."""
        try:
            import uuid as _uuid
            cid = str(_uuid.uuid4())[:12]
            db.collection("correcoes_pendentes").document(cid).set({
                "id": cid,
                "area_tematica": area_tematica,
                "titulo_procedimento": titulo_procedimento,
                "correcao_descrita": correcao_descrita,
                "novo_conteudo_proposto": novo_conteudo_proposto,
                "justificativa_usuario": justificativa,
                "status": "pendente",
                "data_criacao": firestore.SERVER_TIMESTAMP,
                "origem": "telegram",
            })
            return f"Correção registrada (ID: {cid})."
        except Exception as e:
            return f"Erro: {e}"

    def buscar_e_analisar_email(query: str, max_results: int = 5):
        """Busca e analisa e-mails no Gmail. Use query padrão do Gmail (ex: 'from:x@y.com newer_than:2d')."""
        try:
            from tools.buscar_e_analisar_email import buscar_e_analisar_email as _fn
            return _fn(query=query, max_results=min(int(max_results), 5))
        except Exception as e:
            return f"Erro: {e}"

    tools_list = [
        consultar_historico_acoes,
        buscar_arquivos_acervo,
        pesquisar_internet,
        ler_pagina_web,
        criar_acao_no_sistema,
        salvar_memoria_global,
        registrar_correcao_procedimento,
        buscar_e_analisar_email,
    ]

    function_map = {fn.__name__: fn for fn in tools_list}

    # --- Gemini call ---
    _send_telegram_typing(token, chat_id)
    try:
        response_text = _run_gemini_turn(
            db=db,
            gemini_key=gemini_key,
            system_instruction=system_instruction,
            history=history,
            user_message_parts=user_parts,
            tools_list=tools_list,
            function_map=function_map,
        )
    except Exception as gemini_err:
        print(f"[Core] Gemini error: {gemini_err}")
        _send_telegram_message(token, chat_id, f"⚠️ Erro ao processar: {gemini_err}")
        return

    # --- Persist history ---
    def _serialize_part(p):
        return {"text": getattr(p, "text", "") or ""}

    user_turn = {"role": "user", "parts": [{"text": p.text} for p in user_parts if hasattr(p, "text") and p.text]}
    model_turn = {"role": "model", "parts": [{"text": response_text}]}
    new_history = raw_history + [user_turn, model_turn]
    # Trim
    if len(new_history) > _MAX_HISTORY_TURNS * 2:
        new_history = new_history[-(_MAX_HISTORY_TURNS * 2):]
    session["history"] = new_history
    _save_session(db, chat_id, session)

    # --- Send response ---
    _send_telegram_message(token, chat_id, response_text)


# ---------------------------------------------------------------------------
# Cloud Functions
# ---------------------------------------------------------------------------

@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["GET", "POST"]),
    timeout_sec=10,
    memory=options.MemoryOption.MB_256,
)
def telegramWebhook(req: https_fn.Request) -> https_fn.Response:
    """
    Porteiro: recebe POST do Telegram, valida, enfileira no Firestore e retorna 200.
    Nunca bloqueia aguardando processamento Gemini.
    """
    if req.method != "POST":
        return https_fn.Response("OK", status=200)

    try:
        update = req.get_json(silent=True) or {}
    except Exception:
        return https_fn.Response("OK", status=200)

    # --- Extrair mensagem ---
    message = update.get("message") or update.get("edited_message") or {}
    if not message:
        return https_fn.Response("OK", status=200)

    chat = message.get("chat", {})
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        return https_fn.Response("OK", status=200)

    # --- Validação single-owner ---
    allowed = _get_allowed_chat_id()
    if allowed and chat_id != allowed:
        return https_fn.Response("OK", status=200)  # silent ignore

    text = message.get("text") or message.get("caption") or ""
    from_user = message.get("from", {})
    message_id = str(message.get("message_id", ""))

    # --- Detectar mídia ---
    audio_info = None
    file_info = None
    media_bytes_b64 = None

    db = _get_db()

    try:
        token = _get_telegram_token(db)
    except Exception:
        return https_fn.Response("OK", status=200)

    # Audio / Voice
    audio = message.get("audio") or message.get("voice")
    if audio:
        file_size = audio.get("file_size", 0)
        if file_size > _MAX_FILE_BYTES:
            _send_telegram_message(
                token, chat_id,
                "⚠️ Áudio muito grande (máximo 20 MB). Use o portal Web para arquivos maiores."
            )
            return https_fn.Response("OK", status=200)
        try:
            import base64
            file_meta = _get_telegram_file(token, audio["file_id"])
            file_bytes = _download_telegram_file(token, file_meta["file_path"])
            media_bytes_b64 = base64.b64encode(file_bytes).decode()
            audio_info = {
                "file_id": audio["file_id"],
                "file_size": file_size,
                "mime_type": audio.get("mime_type", "audio/ogg"),
                "duration": audio.get("duration", 0),
            }
        except Exception as e:
            print(f"[Webhook] Audio download error: {e}")
            _send_telegram_message(
                token, chat_id,
                f"⚠️ Não consegui baixar o áudio: {e}\nTente novamente ou envie o texto diretamente."
            )
            return https_fn.Response("OK", status=200)

    # Document / Photo
    doc = message.get("document")
    photos = message.get("photo")
    if not audio_info:
        media_obj = doc or (photos[-1] if photos else None)
        if media_obj:
            file_size = media_obj.get("file_size", 0)
            if file_size > _MAX_FILE_BYTES:
                _send_telegram_message(
                    token, chat_id,
                    "⚠️ Arquivo muito grande (máximo 20 MB). Use o portal Web para arquivos maiores."
                )
                return https_fn.Response("OK", status=200)
            try:
                import base64
                file_meta = _get_telegram_file(token, media_obj["file_id"])
                file_bytes = _download_telegram_file(token, file_meta["file_path"])
                media_bytes_b64 = base64.b64encode(file_bytes).decode()
                file_info = {
                    "file_id": media_obj["file_id"],
                    "file_size": file_size,
                    "file_name": doc.get("file_name", "arquivo") if doc else "foto.jpg",
                    "mime_type": (doc.get("mime_type") if doc else "image/jpeg") or "application/octet-stream",
                }
            except Exception as e:
                print(f"[Webhook] File download error: {e}")

    if not text and not audio_info and not file_info:
        return https_fn.Response("OK", status=200)

    # --- Enfileira no Firestore ---
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "from_user": from_user,
        "audio_info": audio_info,
        "file_info": file_info,
        "media_bytes_b64": media_bytes_b64,
        "received_at": firestore.SERVER_TIMESTAMP,
        "processed": False,
    }
    db.collection("telegram_inbound").document(f"{chat_id}_{message_id}").set(payload)

    return https_fn.Response("OK", status=200)


@firestore_fn.on_document_created(
    document="telegram_inbound/{docId}",
    timeout_sec=540,
    memory=options.MemoryOption.GB_2,
)
def on_telegram_inbound(event: Event[DocumentSnapshot]) -> None:
    """
    Trigger assíncrono: processa a mensagem enfileirada e envia resposta ao Telegram.
    """
    snap = event.data
    if not snap or not snap.exists:
        return

    data = snap.to_dict() or {}
    if data.get("processed"):
        return

    # Marca como em processamento para evitar double-trigger
    snap.reference.update({"processed": True, "processing_started_at": firestore.SERVER_TIMESTAMP})

    try:
        db = _get_db()
        _process_telegram_message(db, data)
    except Exception as e:
        print(f"[on_telegram_inbound] Unhandled error: {e}")
        import traceback
        traceback.print_exc()
        snap.reference.update({"error": str(e)})
        try:
            chat_id = data.get("chat_id")
            token = _get_telegram_token(_get_db())
            if chat_id and token:
                _send_telegram_message(token, chat_id, f"⚠️ Erro interno ao processar mensagem: {e}")
        except Exception:
            pass
