"""
Hermes Godmode — modo estratégico do Copiloto, rodando sobre Claude
(Anthropic) em vez de Gemini. Módulo aditivo: não altera nada do fluxo
existente de askCopilotoHermes; expõe seu próprio callable e seu próprio
registro de ferramentas, todas de leitura, sobre as mesmas coleções do
Firestore já usadas pelo restante do app.
"""

import os

from firebase_admin import firestore
from firebase_functions import https_fn, options

from llm_providers import claude_provider

GODMODE_MODEL = os.environ.get("GODMODE_MODEL", "claude-fable-5")
GODMODE_FALLBACK_MODEL = os.environ.get("GODMODE_FALLBACK_MODEL", "claude-opus-4-8")
GODMODE_MAX_TOKENS = int(os.environ.get("GODMODE_MAX_TOKENS", "4096"))
GODMODE_FUNCTION_TIMEOUT_SEC = 300

GODMODE_PERSONA = (
    "## MODO GODMODE — Diretor de Estratégia e Operações Virtual\n"
    "Você é o Hermes Godmode: um conselheiro adversário, não um assistente condescendente. "
    "Sua função é auditar viabilidade e confrontar premissas do usuário com dados reais do "
    "sistema — nunca validar por educação.\n\n"
    "Regras de conduta:\n"
    "- Nunca bajule. Discorde com fundamento quando os fatos não sustentarem o pedido.\n"
    "- Toda afirmação de risco, custo ou prazo deve estar ancorada em dado concreto obtido via "
    "ferramenta. Se não houver dado suficiente, diga isso explicitamente em vez de estimar sem base.\n"
    "- Aponte o custo de oportunidade: onde o tempo/orçamento analisado traria mais alavancagem.\n\n"
    "Quando a pergunta pedir uma análise estratégica (não uma consulta factual simples), estruture "
    "a resposta em exatamente três seções, nesta ordem:\n"
    "1. **Diagnóstico de Falha** — inconsistências, riscos de execução e desalinhamentos identificados.\n"
    "2. **Matriz de Trade-offs** — 2 ou 3 rotas de ação, com custo, risco e impacto de cada uma.\n"
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


def _build_tools(db, user_uid: str | None, gemini_key: str | None):
    """Registro de ferramentas somente-leitura do Godmode."""

    def consultar_projetos(nome_contendo: str = "") -> dict:
        needle = (nome_contendo or "").strip().lower()
        out = []
        for d in db.collection("projetos").stream():
            data = d.to_dict() or {}
            nome = data.get("nome", "")
            if needle and needle not in nome.lower():
                continue
            out.append({"id": d.id, "nome": nome, "orcamento": data.get("orcamento") or {}})
        return {"projetos": out[:100]}

    def consultar_itens_orcamento(projeto_id: str) -> dict:
        if not projeto_id:
            return {"error": "projeto_id é obrigatório."}
        itens = []
        totais_rubrica: dict = {}
        totais_status: dict = {}
        docs = db.collection("projetos").document(projeto_id).collection("itens_orcamento").stream()
        for d in docs:
            data = d.to_dict() or {}
            valor = float(data.get("valor_unitario_estimado") or 0) * float(data.get("quantidade") or 0)
            rubrica = data.get("rubrica", "indefinida")
            status = data.get("status", "indefinido")
            totais_rubrica[rubrica] = totais_rubrica.get(rubrica, 0) + valor
            totais_status[status] = totais_status.get(status, 0) + valor
            itens.append({**data, "id": d.id, "valor_total": valor})
        return {"itens": itens[:200], "totais_por_rubrica": totais_rubrica, "totais_por_status": totais_status}

    def consultar_vinculos_bolsistas(projeto_id: str = "") -> dict:
        query = db.collection("vinculos_projeto")
        if projeto_id:
            query = query.where("projeto_id", "==", projeto_id)
        vinculos = [dict(d.to_dict() or {}, id=d.id) for d in query.limit(150).stream()]

        pessoa_ids = {v.get("pessoa_id") for v in vinculos if v.get("pessoa_id")}
        tipo_ids = {v.get("tipo_bolsa_id") for v in vinculos if v.get("tipo_bolsa_id")}

        pessoas = {}
        for pid in pessoa_ids:
            snap = db.collection("perfil_pessoas").document(pid).get()
            if snap.exists:
                pessoas[pid] = (snap.to_dict() or {}).get("nome")

        tipos = {}
        for tid in tipo_ids:
            snap = db.collection("tipos_bolsa").document(tid).get()
            if snap.exists:
                data = snap.to_dict() or {}
                tipos[tid] = {"nome": data.get("nome_modalidade"), "valor_integral": data.get("valor_integral")}

        for v in vinculos:
            v["pessoa_nome"] = pessoas.get(v.get("pessoa_id"))
            v["tipo_bolsa"] = tipos.get(v.get("tipo_bolsa_id"))

        return {"vinculos": vinculos}

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

    function_map = {
        "consultar_projetos": consultar_projetos,
        "consultar_itens_orcamento": consultar_itens_orcamento,
        "consultar_vinculos_bolsistas": consultar_vinculos_bolsistas,
        "consultar_metas_estrategicas": consultar_metas_estrategicas,
        "buscar_conhecimento": buscar_conhecimento,
    }

    tools_schema = [
        {
            "name": "consultar_projetos",
            "description": (
                "Lista projetos cadastrados com seu orçamento (custeio/capital/bolsas). "
                "Use um filtro de nome para restringir."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "nome_contendo": {
                        "type": "string",
                        "description": "Filtro opcional por substring no nome do projeto.",
                    },
                },
            },
        },
        {
            "name": "consultar_itens_orcamento",
            "description": (
                "Lista os itens de orçamento planejados/aprovados/executados de um projeto "
                "específico, com totais por rubrica e por status."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "projeto_id": {"type": "string", "description": "ID do documento do projeto em 'projetos'."},
                },
                "required": ["projeto_id"],
            },
        },
        {
            "name": "consultar_vinculos_bolsistas",
            "description": (
                "Lista vínculos de bolsistas/pessoas a projetos (datas, percentual de recebimento, "
                "tipo de bolsa, status). Opcionalmente filtra por projeto."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "projeto_id": {
                        "type": "string",
                        "description": "ID do projeto para filtrar os vínculos. Deixe vazio para todos.",
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
    user_uid = req.auth.uid if req.auth else None

    if not user_uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Autenticação obrigatória para usar o Hermes Godmode.",
        )
    if not prompt:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Prompt é obrigatório.",
        )

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
    tools, function_map = _build_tools(db, user_uid, gemini_key)

    try:
        result = claude_provider.run_tool_loop(
            client=client,
            model=GODMODE_MODEL,
            system_instruction=system_instruction,
            tools=tools,
            function_map=function_map,
            history=history,
            user_message=prompt,
            max_tokens=GODMODE_MAX_TOKENS,
        )
    except anthropic.APIStatusError as exc:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAVAILABLE,
            message=f"Erro na Claude API: {exc}",
        )

    mensagens_ref.add(
        {
            "role": "assistant",
            "content": result["text"],
            "toolsUsed": result["tools_used"],
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
    session_ref.set({"lastMessageAt": firestore.SERVER_TIMESTAMP}, merge=True)

    return {
        "result": result["text"],
        "sessionId": session_id,
        "toolsUsed": result["tools_used"],
        "usage": result["usage"],
    }
