"""
Hermes Godmode — modo estratégico do Copiloto, rodando sobre Claude
(Anthropic) em vez de Gemini. Módulo aditivo: não altera nada do fluxo
existente de askCopilotoHermes; expõe seu próprio callable e seu próprio
registro de ferramentas, todas de leitura, sobre as coleções de tarefas,
metas estratégicas e conhecimento já usadas pelo restante do app.

Os módulos financeiro e de saúde estão temporariamente desvinculados do
Godmode (em ajuste separado) — não há ferramentas nem calibração de dados
para eles aqui.
"""

import os

from firebase_admin import firestore
from firebase_functions import https_fn, options

from llm_providers import claude_provider

GODMODE_MODEL = os.environ.get("GODMODE_MODEL", "claude-3-5-sonnet-20241022")
GODMODE_FALLBACK_MODEL = os.environ.get("GODMODE_FALLBACK_MODEL", "claude-3-5-haiku-20241022")
GODMODE_MAX_TOKENS = int(os.environ.get("GODMODE_MAX_TOKENS", "4096"))
GODMODE_FUNCTION_TIMEOUT_SEC = 300

GODMODE_PERSONA = (
    "## MODO GODMODE — Diretor de Estratégia e Operações Virtual\n"
    "Você é o Hermes Godmode: um conselheiro adversário, não um assistente condescendente. "
    "Sua função é auditar viabilidade e confrontar premissas do usuário com dados reais do "
    "sistema — nunca validar por educação.\n\n"
    "Escopo atual: apenas tarefas/ações, metas estratégicas e base de conhecimento. Os módulos "
    "financeiro e de saúde estão temporariamente fora do seu escopo — você não tem ferramentas "
    "para consultá-los. Se a pergunta depender de dados financeiros ou de saúde, diga isso "
    "explicitamente e não estime ou infira esses números a partir de outras fontes.\n\n"
    "Regras de conduta:\n"
    "- Nunca bajule. Discorde com fundamento quando os fatos não sustentarem o pedido.\n"
    "- Toda afirmação de risco, custo ou prazo deve estar ancorada em dado concreto obtido via "
    "ferramenta. Se não houver dado suficiente, diga isso explicitamente em vez de estimar sem base.\n"
    "- Aponte o custo de oportunidade: onde o tempo analisado traria mais alavancagem.\n\n"
    "Regras de formatação (a leitura é majoritariamente em celular):\n"
    "- Nunca use tabelas Markdown — são ilegíveis em tela estreita. Prefira listas de tópicos, "
    "com o item em negrito seguido de uma explicação curta.\n"
    "- Frases curtas e diretas. Evite parágrafos longos.\n\n"
    "Quando a pergunta pedir uma análise estratégica (não uma consulta factual simples), estruture "
    "a resposta em exatamente três seções, nesta ordem, cada uma em tópicos (nunca em tabela):\n"
    "1. **Diagnóstico de Falha** — inconsistências, riscos de execução e desalinhamentos identificados.\n"
    "2. **Matriz de Trade-offs** — 2 ou 3 rotas de ação, cada uma em um tópico com custo, risco e impacto.\n"
    "3. **Plano de Contingência** — recomendação imediata de mitigação ou realocação de recursos.\n"
    "Para perguntas factuais diretas, responda direto, sem forçar essa estrutura."
)


def _get_persona(db) -> str:
    parts = [GODMODE_PERSONA]
    try:
        core_doc = db.collection("system").document("copilot_core").get()
        if core_doc.exists:
            content = (core_doc.to_dict() or {}).get("content")
            if content:
                parts.append(f"## CORE ESTÁTICO DO COPILOTO\n{content}")
    except Exception:
        pass
    return "\n\n".join(parts)


def _get_user_profile_text(db, uid: str | None) -> str:
    if not uid:
        return "(usuário não autenticado)"
    try:
        snap = db.collection("usuarios").document(uid).get()
        profile = (snap.to_dict() or {}).get("ai_profile") if snap.exists else {}
    except Exception:
        return "(perfil indisponível)"
    if not profile:
        return "(perfil ainda não configurado)"
    lines = [f"- {key}: {profile[key]}" for key in ("nome", "cargo", "setor", "email") if profile.get(key)]
    return "\n".join(lines) or "(perfil sem dados básicos)"


_GAPPS_EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

_PLAIN_TEXT_EXTENSIONS = (".txt", ".csv", ".md", ".markdown", ".json", ".xml", ".html", ".htm", ".eml")


def _extract_attached_file_text(drive_file_id: str, gemini_key: str | None) -> tuple[str, str]:
    """Baixa do Drive o arquivo anexado à mensagem e extrai seu texto. Retorna (nome_real, texto)."""
    from main import get_drive_service  # import tardio: evita import circular com main.py

    import io as _io

    from googleapiclient.http import MediaIoBaseDownload

    drive_service = get_drive_service()
    meta = drive_service.files().get(fileId=drive_file_id, fields="name,mimeType").execute()
    real_name = meta.get("name", "arquivo anexado")
    mime = meta.get("mimeType", "application/octet-stream")

    if mime in _GAPPS_EXPORT_MIME:
        request = drive_service.files().export_media(fileId=drive_file_id, mimeType=_GAPPS_EXPORT_MIME[mime])
    else:
        request = drive_service.files().get_media(fileId=drive_file_id)

    buffer = _io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    file_bytes = buffer.getvalue()

    lower_name = real_name.lower()
    if mime.startswith("image/"):
        text = (
            "(Este anexo é uma imagem — o Godmode ainda não realiza leitura visual/OCR. "
            "Peça ao usuário para descrever em texto o conteúdo relevante da imagem.)"
        )
    elif mime in _GAPPS_EXPORT_MIME or lower_name.endswith(_PLAIN_TEXT_EXTENSIONS):
        text = file_bytes.decode("utf-8", errors="replace")
    elif lower_name.endswith(".docx") or mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        import mammoth

        text = mammoth.extract_raw_text(_io.BytesIO(file_bytes)).value or ""
    elif lower_name.endswith(".pptx") or mime == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        from pptx import Presentation

        prs = Presentation(_io.BytesIO(file_bytes))
        parts = [
            shape.text.strip()
            for slide in prs.slides
            for shape in slide.shapes
            if hasattr(shape, "text") and shape.text.strip()
        ]
        text = "\n".join(parts)
    elif lower_name.endswith(".xlsx") or mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        import pandas as pd

        sheets = pd.read_excel(_io.BytesIO(file_bytes), sheet_name=None)
        text = "\n\n".join(f"ABA: {name}\n{sheet.to_csv(index=False)}" for name, sheet in sheets.items())
    elif lower_name.endswith(".pdf") or mime == "application/pdf":
        from pdf_precision import extract_pdf_text_with_fallback

        result = extract_pdf_text_with_fallback(
            file_bytes, real_name, api_key=gemini_key, allow_gemini_fallback=bool(gemini_key)
        )
        text = result.get("text") or ""
    else:
        text = ""

    return real_name, text.strip()


def _build_tools(
    db,
    user_uid: str | None,
    gemini_key: str | None,
    attached_drive_file_id: str | None = None,
    attached_file_name: str | None = None,
):
    """Registro de ferramentas somente-leitura do Godmode."""

    def consultar_tarefas(status: str = "", area_tematica: str = "", incluir_concluidas: bool = False, limite: int = 50) -> dict:
        limite = max(1, min(int(limite or 50), 150))
        query = db.collection("tarefas")
        # Só um filtro no Firestore por vez (evita depender de índice composto);
        # o restante do filtro é aplicado em memória.
        if area_tematica:
            query = query.where("area_tematica", "==", area_tematica)
        elif status:
            query = query.where("status", "==", status)

        tarefas = []
        for d in query.limit(limite * 3).stream():
            data = d.to_dict() or {}
            if status and data.get("status") != status:
                continue
            if not status and not incluir_concluidas and data.get("status") == "concluído":
                continue
            if area_tematica and data.get("area_tematica") != area_tematica:
                continue
            tarefas.append({
                "id": d.id,
                "titulo": data.get("titulo"),
                "status": data.get("status"),
                "area_tematica": data.get("area_tematica"),
                "projeto": data.get("projeto"),
                "data_limite": data.get("data_limite"),
                "prazo_final": data.get("prazo_final"),
                "contabilizar_meta": data.get("contabilizar_meta"),
                "tags": data.get("tags"),
            })
            if len(tarefas) >= limite:
                break
        return {"tarefas": tarefas}

    def consultar_metas_estrategicas(apenas_ativas: bool = True) -> dict:
        if not user_uid:
            return {"error": "Sem usuário autenticado — não é possível ler metas pessoais."}
        query = db.collection("estrategia_pessoal").where("userId", "==", user_uid)
        metas = [dict(d.to_dict() or {}, id=d.id) for d in query.limit(80).stream()]
        if apenas_ativas:
            metas = [
                m for m in metas
                if str(m.get("status", "")).lower() not in ("concluido", "concluído", "cancelado", "arquivado")
            ]
        return {"metas": metas}

    def buscar_conhecimento(consulta: str, area_tematica: str = "", tags: list | None = None) -> dict:
        if not gemini_key:
            return {"error": "RAG indisponível: chave Gemini não configurada (necessária para embeddings)."}
        try:
            from knowledge_graph import extract_kg_rag_context
            nodes, context_str = extract_kg_rag_context(
                db=db,
                api_key=gemini_key,
                area_tematica=area_tematica or consulta,
                tags=tags or [],
            )
            return {"nodes": nodes[:20], "contexto": context_str[:6000]}
        except Exception as exc:
            return {"error": str(exc)}

    def ler_arquivo_anexado(query_especifica: str = "") -> dict:
        if not attached_drive_file_id:
            return {"erro": "Nenhum arquivo foi anexado a esta mensagem."}
        try:
            real_name, text = _extract_attached_file_text(attached_drive_file_id, gemini_key)
        except Exception as exc:
            return {"erro": f"Falha ao ler o arquivo anexado ({attached_file_name or attached_drive_file_id}): {exc}"}
        if not text:
            return {"arquivo": real_name, "aviso": "Não foi possível extrair texto deste arquivo."}
        return {"arquivo": real_name, "conteudo": text[:7000]}

    function_map = {
        "consultar_tarefas": consultar_tarefas,
        "consultar_metas_estrategicas": consultar_metas_estrategicas,
        "buscar_conhecimento": buscar_conhecimento,
    }
    if attached_drive_file_id:
        function_map["ler_arquivo_anexado"] = ler_arquivo_anexado

    tools_schema = [
        {
            "name": "consultar_tarefas",
            "description": (
                "Lista tarefas/ações do usuário (título, status, área temática, prazos). "
                "Por padrão oculta tarefas concluídas — use incluir_concluidas para trazê-las. "
                "Atenção: tarefas com campo 'projeto' preenchido tratam de projetos institucionais, "
                "não de assuntos pessoais do usuário."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["em andamento", "stand-by", "concluído"],
                        "description": "Filtra por status exato. Deixe vazio para todos.",
                    },
                    "area_tematica": {
                        "type": "string",
                        "description": "Filtra por área temática exata, se conhecida.",
                    },
                    "incluir_concluidas": {
                        "type": "boolean",
                        "description": "Se true, inclui tarefas com status 'concluído' quando nenhum status específico for informado.",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Número máximo de tarefas retornadas (padrão 50, máximo 150).",
                    },
                },
            },
        },
        {
            "name": "consultar_metas_estrategicas",
            "description": (
                "Lista os objetivos/metas estratégicas pessoais do usuário autenticado "
                "(equivalente a metas de PGD/plano de gestão)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "apenas_ativas": {
                        "type": "boolean",
                        "description": "Se true (padrão), oculta metas concluídas/canceladas/arquivadas.",
                    },
                },
            },
        },
        {
            "name": "buscar_conhecimento",
            "description": (
                "Busca semântica (RAG) na base de conhecimento/procedimentos já registrada no Hermes "
                "(knowledge_graph) para embasar a análise com precedentes reais."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Texto da busca."},
                    "area_tematica": {
                        "type": "string",
                        "description": "Área temática para restringir a busca, se conhecida.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags adicionais para refinar a busca.",
                    },
                },
                "required": ["consulta"],
            },
        },
    ]

    if attached_drive_file_id:
        tools_schema.append({
            "name": "ler_arquivo_anexado",
            "description": (
                f"Lê o conteúdo do arquivo '{attached_file_name or 'anexo'}' que o usuário anexou "
                "a esta mensagem e retorna seu texto extraído. Use sempre que a pergunta se referir "
                "ao conteúdo desse anexo antes de responder."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query_especifica": {
                        "type": "string",
                        "description": "O que exatamente você precisa encontrar no arquivo (opcional, ajuda a focar a leitura).",
                    },
                },
            },
        })

    return tools_schema, function_map


def _load_history(db, session_id: str) -> list[dict]:
    if not session_id:
        return []
    docs = (
        db.collection("sessoes_godmode")
        .document(session_id)
        .collection("mensagens")
        .order_by("timestamp")
        .limit(40)
        .stream()
    )
    history = []
    for d in docs:
        data = d.to_dict() or {}
        role = "assistant" if data.get("role") == "assistant" else "user"
        content = data.get("content") or ""
        if content:
            history.append({"role": role, "content": content})
    return history


@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST", "OPTIONS"]),
    memory=options.MemoryOption.GB_2,
    timeout_sec=GODMODE_FUNCTION_TIMEOUT_SEC,
)
def askHermesGodmode(req: https_fn.CallableRequest):
    data = req.data or {}
    prompt = (data.get("prompt") or "").strip()
    session_id = (data.get("sessionId") or "").strip()
    drive_file_id = (data.get("driveFileId") or "").strip() or None
    drive_file_name = (data.get("driveFileName") or "").strip() or None
    user_uid = req.auth.uid if req.auth else None

    if not user_uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Autenticação obrigatória para usar o Hermes Godmode.",
        )
    if not prompt and not drive_file_id:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Prompt é obrigatório.",
        )
    if not prompt:
        prompt = f"Arquivo anexado: {drive_file_name or 'documento'}"

    try:
        import anthropic
    except ImportError:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Dependência 'anthropic' não instalada no ambiente de functions.",
        )

    db = firestore.client()
    keys_doc = db.collection("system").document("api_keys").get()
    keys_data = keys_doc.to_dict() if keys_doc.exists else {}
    claude_key = (keys_data or {}).get("claude_api_key")
    gemini_key = (keys_data or {}).get("gemini_api_key")

    if not claude_key:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Chave Claude não configurada (system/api_keys.claude_api_key).",
        )

    if not session_id:
        session_ref = db.collection("sessoes_godmode").document()
        session_id = session_ref.id
        session_ref.set(
            {
                "userId": user_uid,
                "createdAt": firestore.SERVER_TIMESTAMP,
                "lastMessageAt": firestore.SERVER_TIMESTAMP,
                "titulo": prompt[:80],
            }
        )
    else:
        session_ref = db.collection("sessoes_godmode").document(session_id)

    mensagens_ref = session_ref.collection("mensagens")
    # Carrega o histórico ANTES de gravar a mensagem atual do usuário — o loop
    # de tool-calling já injeta `prompt` como o turno mais recente, então
    # gravar antes duplicaria esse turno (e quebraria a alternância obrigatória
    # de roles da Claude Messages API).
    history = _load_history(db, session_id)
    mensagens_ref.add(
        {"role": "user", "content": prompt, "timestamp": firestore.SERVER_TIMESTAMP}
    )

    client = anthropic.Anthropic(api_key=claude_key)
    system_instruction = _get_persona(db) + "\n\n## PERFIL DO USUÁRIO\n" + _get_user_profile_text(db, user_uid)
    tools, function_map = _build_tools(db, user_uid, gemini_key, drive_file_id, drive_file_name)

    llm_user_message = prompt
    if drive_file_id:
        llm_user_message = (
            f"[O usuário anexou o arquivo '{drive_file_name or 'documento'}' a esta mensagem. "
            "Use a ferramenta ler_arquivo_anexado para consultar o conteúdo antes de responder.]\n\n"
            f"{prompt}"
        )

    try:
        result = claude_provider.run_tool_loop(
            client=client,
            model=GODMODE_MODEL,
            system_instruction=system_instruction,
            tools=tools,
            function_map=function_map,
            history=history,
            user_message=llm_user_message,
            max_tokens=GODMODE_MAX_TOKENS,
            fallback_model=GODMODE_FALLBACK_MODEL,
        )
    except anthropic.APIStatusError as exc:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAVAILABLE,
            message=f"Erro na Claude API (modelo principal e fallback indisponíveis): {exc}",
        )

    mensagens_ref.add(
        {
            "role": "assistant",
            "content": result["text"],
            "toolsUsed": result["tools_used"],
            "modelUsed": result["model_used"],
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
    session_ref.set({"lastMessageAt": firestore.SERVER_TIMESTAMP}, merge=True)

    return {
        "result": result["text"],
        "sessionId": session_id,
        "toolsUsed": result["tools_used"],
        "usage": result["usage"],
        "modelUsed": result["model_used"],
        "fallbackUsed": result["fallback_used"],
    }
