"""Catalogo de tools do Hermes executavel fora do copiloto web.

Fonte unica de execucao para qualquer canal que nao seja o `askCopilotoHermes`
(servidor MCP, voz, automacoes). Cada handler recebe um `ToolContext` explicito
em vez de capturar `db`/`user_uid`/`session_id` por closure.

Como cada tool chega aqui, em ordem de preferencia — a regra e sempre reusar,
nunca reescrever:

1. **Delegacao a `tools/telegram_extended.py`** (20 tools). Aquele modulo ja
   implementa metade do catalogo com a assinatura `execute(nome, slots, db)`,
   sem closure nenhuma. Os nomes de slot conferidos um a um contra
   `tools/schemas/*.json` — onde havia divergencia, o proprio `execute` aceita
   os dois aliases.
2. **Delegacao a modulos dedicados** (`strategy_tools`, `health_tools`,
   `dados_cadastrais`, `hermes_calendar_tools`, `busca_grafo`, `busca_acervo`,
   `whatsapp_ingest`, `lista_compras`, ...) — 17 tools.
3. **Implementacao extraida da closure** — so as ~11 tools que nao existiam em
   nenhum outro lugar. As closures correspondentes em `main.py` passam a
   delegar para ca, entao isto NAO e duplicacao: e a unica copia.

Os retornos sao preservados exatamente como o copiloto web os produz (str na
maioria, dict em algumas), justamente para que `main.py` possa delegar sem
mudanca de comportamento observavel.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from tools.tool_context import ToolContext


class ToolNotAvailable(Exception):
    """Tool nao existe ou nao tem executor ligado fora do copiloto web."""


# ---------------------------------------------------------------------------
# 1. Delegacao a tools/telegram_extended.py
# ---------------------------------------------------------------------------

_TELEGRAM_TOOLS = {
    "obter_contexto_tela",
    "ler_documento_na_integra",
    "salvar_pop_global",
    "resolver_conflito_memoria",
    "atualizar_personalidade",
    "resolver_conflito_procedimento",
    "editar_plano_acao",
    "preparar_edicao_acao",
    "gerar_relatorio",
    "gerar_rascunho_formulario",
    "obter_portal_financeiro_publico",
    "registrar_transacao_financeira_publica",
    "obter_portal_compras_publico",
    "mutar_portal_compras_publico",
    "mutar_lista_compras",
    "obter_projeto_bolsas_publico",
    "registrar_inscricao_bolsa_publica",
    "consultar_financas_v2",
}


def _via_telegram(nome: str):
    def handler(ctx: ToolContext, args: dict):
        from tools.telegram_extended import execute as _execute

        slots = dict(args)
        # `gerar_relatorio`, `editar_plano_acao` e `obter_contexto_tela` operam
        # sobre uma acao; quando o canal ja tem uma em contexto, evita exigir o id.
        if "task_id" in slots and not slots.get("task_id") and ctx.task_id:
            slots["task_id"] = ctx.task_id
        return _execute(nome, slots, ctx.db)

    return handler


def _registrar_item_financeiro_v2(ctx: ToolContext, args: dict):
    from tools.telegram_extended import execute as _execute

    # A categoria nao e inferida nem pedida ao usuario por decisao de produto;
    # o copiloto web e o Telegram gravam "Geral" fixo. Mesmo contrato aqui.
    slots = {**args, "categoria": "Geral"}
    return _execute("registrar_item_financeiro_v2", slots, ctx.db)


def _consultar_lista_compras(ctx: ToolContext, args: dict):
    """Contraparte de leitura de `mutar_lista_compras`, na mesma unica copia."""
    from tools import lista_compras

    try:
        return lista_compras.consultar(
            ctx.db,
            filtro=args.get("filtro"),
            busca=args.get("busca"),
            limite=args.get("limite"),
        )
    except lista_compras.ListaComprasError as erro:
        return erro.message


def _consultar_elevacoes_sugeridas(ctx: ToolContext, args: dict):
    import deteccao_subproduto

    return deteccao_subproduto.listar_pendentes(ctx.db, limite=int(args.get("limite") or 20))


def _decidir_elevacao(ctx: ToolContext, args: dict):
    import deteccao_subproduto
    from morning_summary import _hoje_sp

    return deteccao_subproduto.decidir(
        ctx.db, args.get("sugestao_id"), args.get("decisao"), _hoje_sp())


def _agendar_lembrete_acao(ctx: ToolContext, args: dict):
    from tools.telegram_extended import execute as _execute

    task_id = (args.get("task_id") or ctx.task_id or "").strip()
    if not task_id:
        return "ERRO|Nenhuma acao em contexto e nenhum task_id informado para agendar o lembrete."
    return _execute("agendar_lembrete_acao", {**args, "task_id": task_id}, ctx.db)


# ---------------------------------------------------------------------------
# 2. Delegacao a modulos dedicados
# ---------------------------------------------------------------------------

_STOPWORDS_QUERY = {
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "uma",
    "os", "as", "no", "na", "com", "por", "para", "dos", "das",
    "nos", "nas", "ao", "se", "ou",
}


def _consultar_historico_acoes(ctx: ToolContext, args: dict):
    from tools.busca_grafo import buscar_tarefas

    query = str(args.get("query") or "")
    area_tematica = args.get("area_tematica")
    status = args.get("status")
    data_limite_inicio = args.get("data_limite_inicio")
    data_limite_fim = args.get("data_limite_fim")
    limite = int(args.get("ultimas_n_acoes") or 20)

    # Duas palavras significativas ou mais => exige todas (match_mode="all"),
    # caindo para "any" quando isso nao retorna nada. Mesma heuristica do copiloto.
    q_terms = [w for w in query.lower().split() if w not in _STOPWORDS_QUERY and len(w) > 2]
    initial_mode = "all" if len(q_terms) >= 2 else "any"

    def _run(mode):
        return buscar_tarefas(
            query,
            area_tematica=area_tematica,
            match_mode=mode,
            data_limite_inicio=data_limite_inicio,
            data_limite_fim=data_limite_fim,
            status=status,
            limite=limite,
        )

    res = _run(initial_mode)
    if initial_mode == "all" and not res.get("resultados"):
        res = _run("any")

    if res.get("erro"):
        return {"erro": res["erro"], "resultados": []}

    resultados = res.get("resultados", [])
    return {
        "total_retornado": len(resultados),
        "resultados": resultados,
        "filtros": {
            "query": query,
            "area_tematica": area_tematica,
            "status": status,
            "data_limite_inicio": data_limite_inicio,
            "data_limite_fim": data_limite_fim,
        },
    }


def _buscar_arquivos_acervo(ctx: ToolContext, args: dict):
    from tools.busca_acervo import buscar_acervo

    res = buscar_acervo(str(args.get("query") or ""))
    if res.get("erro"):
        return {"erro": res["erro"], "resultados": []}
    resultados = res.get("resultados", [])
    return {"total_retornado": len(resultados), "resultados": resultados}


def _buscar_contato(ctx: ToolContext, args: dict):
    termo = str(args.get("termo") or "").strip().lower()
    limite = max(1, min(int(args.get("limite") or 5), 20))
    if not termo:
        return {"erro": "Termo de busca vazio.", "candidatos": []}

    candidatos = []
    for doc in ctx.db.collection("perfil_pessoas").limit(500).stream():
        data = doc.to_dict() or {}
        nome = str(data.get("nome") or "").lower()
        email = str(data.get("email") or "").lower()
        tags = [str(t).lower() for t in (data.get("tags") or [])]

        score = 0.0
        if nome == termo or email == termo:
            score = 1.0
        elif termo in nome:
            score = 0.8
        elif termo in email:
            score = 0.7
        elif any(termo in t for t in tags):
            score = 0.5

        if score > 0:
            candidatos.append({
                "pessoa_id": doc.id,
                "nome": data.get("nome", ""),
                "email": data.get("email", ""),
                "telefone": data.get("telefone", ""),
                "whatsapp_chat_id": data.get("whatsapp_chat_id", ""),
                "tags": data.get("tags", []),
                "score": score,
            })

    candidatos.sort(key=lambda item: -item["score"])
    return {"candidatos": candidatos[:limite]}


def _consultar_job(ctx: ToolContext, args: dict):
    """Resultado de uma tool longa despachada para execucao assincrona."""
    from mcp_jobs import ler_job

    return ler_job(ctx.user_uid, str(args.get("job_id") or ""))


def _calculadora(ctx: ToolContext, args: dict):
    import math

    expressao = str(args.get("expressao") or "")
    try:
        allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("__")}
        code = compile(expressao, "<string>", "eval")
        for used_name in code.co_names:
            if used_name not in allowed_names:
                raise NameError(f"O uso de '{used_name}' nao e permitido.")
        result = eval(code, {"__builtins__": {}}, allowed_names)  # noqa: S307 — sandbox restrito acima
        return {"expressao": expressao, "resultado": str(result)}
    except Exception as exc:
        return {"expressao": expressao, "erro": f"Erro de calculo: {exc}"}


def _consultar_agenda(ctx: ToolContext, args: dict):
    """Compromissos do periodo, de TODAS as agendas sincronizadas.

    Ate 28/08/2026 esta tool consultava so `get_target_calendar_id` — a agenda
    dedicada onde o Hermes escreve. Os compromissos reais do dono ficam na
    `primary`, entao a resposta trazia apenas o que o proprio Hermes tinha
    criado: numa semana com 35 compromissos, devolveu 1. Uma reuniao existente
    foi reportada como inexistente por causa disso.
    """
    try:
        from main import get_calendar_service, get_sync_calendar_ids
        import hermes_calendar_tools as hc_tools

        c_service = get_calendar_service()
        ids = get_sync_calendar_ids(ctx.db)
        if not c_service or not ids:
            return "Google Calendar nao configurado."
        inicio, fim = args.get("data_inicio"), args.get("data_fim")
        events, falhas = hc_tools.consultar_eventos_multi(c_service, ids, inicio, fim)
        return hc_tools.formatar_eventos_para_llm(
            events, periodo=(inicio, fim), agendas=ids, falhas=falhas)
    except Exception as e:
        # A falha precisa ser inconfundivel: um erro lido como "agenda vazia"
        # faz propor trabalho por cima de compromisso real.
        return (f"ERRO ao consultar agenda: {e}. NAO trate isto como agenda vazia — "
                "a consulta falhou e os compromissos do periodo sao desconhecidos.")


def _encontrar_slot_livre(ctx: ToolContext, args: dict):
    """Proximo horario livre, olhando TODAS as agendas sincronizadas.

    Mesmo defeito de `_consultar_agenda` e com consequencia pior: calcular
    tempo livre sobre uma agenda que so tem eventos do Hermes faz quase tudo
    parecer vago, e a proposta cai por cima de compromisso real.
    """
    try:
        from main import get_calendar_service, get_sync_calendar_ids
        import hermes_calendar_tools as hc_tools

        c_service = get_calendar_service()
        ids = get_sync_calendar_ids(ctx.db)
        if not c_service or not ids:
            return "Erro: Google Calendar nao configurado."
        slot = hc_tools.encontrar_proximo_slot(
            c_service, ids, args.get("a_partir_de"), int(args.get("duracao_min") or 30)
        )
        if not slot:
            return "Nenhum slot livre encontrado."
        slot["agendas_consultadas"] = len(ids)
        return json.dumps(slot, ensure_ascii=False)
    except Exception as e:
        return (f"ERRO ao buscar slot livre: {e}. NAO trate isto como "
                "disponibilidade — a agenda nao pode ser lida.")


def _consultar_saude(ctx: ToolContext, args: dict):
    try:
        from health_tools import build_health_summary

        return json.dumps(
            build_health_summary(
                ctx.db,
                int(args.get("ultimos_dias") or 7),
                args.get("data_especifica"),
            ),
            ensure_ascii=False,
            default=str,
        )
    except Exception as e:
        return f"Erro ao consultar dados de saude: {e}"


def _consultar_dados_cadastrais(ctx: ToolContext, args: dict):
    try:
        from dados_cadastrais import get_dados_cadastrais

        return json.dumps(
            get_dados_cadastrais(ctx.db, ctx.user_uid, args.get("secao") or ""),
            ensure_ascii=False,
            default=str,
        )
    except Exception as e:
        return f"ERRO|{e}"


def _buscar_e_analisar_email(ctx: ToolContext, args: dict):
    try:
        from tools.buscar_e_analisar_email import buscar_e_analisar_email as _fn

        return _fn(
            query=str(args.get("query") or ""),
            max_results=min(int(args.get("max_results") or 5), 5),
        )
    except Exception as e:
        return f"Erro: {e}"


def _schedule_whatsapp_message(ctx: ToolContext, args: dict):
    from tools.schedule_whatsapp_message import schedule_whatsapp_message as _fn

    return _fn(
        ctx.db,
        contact_number=args.get("contact_number"),
        message=args.get("message"),
        scheduled_time=args.get("scheduled_time"),
    )


def _buscar_conversas_whatsapp(ctx: ToolContext, args: dict):
    from whatsapp_ingest import buscar_conversas_whatsapp as _buscar

    res = _buscar(ctx.db, str(args.get("query") or ""), int(args.get("limite") or 5))
    if res.get("erro"):
        return f"⚠️ {res['erro']}"
    resultados = res.get("resultados", [])
    if not resultados:
        return "Nenhuma conversa de WhatsApp indexada encontrada para esta busca."

    linhas = []
    for r in resultados:
        topicos = ", ".join(r.get("topicos") or [])
        chat_id_info = f" (chat_id: {r.get('chat_id')})" if r.get("chat_id") else ""
        linhas.append(
            f"- [{r.get('chat_name')}]{chat_id_info} {r.get('resumo')}"
            + (f" (topicos: {topicos})" if topicos else "")
        )
    return "\n".join(linhas)


def _salvar_memoria_global(ctx: ToolContext, args: dict):
    from main import (
        _classify_memory_candidate,
        _normalize_memory_category,
        _save_memory_node,
    )

    fato = args.get("fato")
    categoria = args.get("categoria")
    try:
        retention = _classify_memory_candidate(
            api_key=ctx.gemini_key, fato=fato, categoria=categoria
        )
        if not retention.get("should_save"):
            return json.dumps({
                "status": "ignored",
                "reason": retention.get("reason", "retention_filter"),
                "categoria": retention.get(
                    "normalized_category", _normalize_memory_category(categoria)
                ),
                "confidence": retention.get("confidence", 0.0),
            }, ensure_ascii=False)

        result = _save_memory_node(
            db=ctx.db,
            api_key=ctx.gemini_key,
            fato=fato,
            categoria=retention.get("normalized_category", categoria),
            session_id=ctx.session_id,
            user_uid=ctx.user_uid,
        )
        result["retention_reason"] = retention.get("reason")
        result["retention_confidence"] = retention.get("confidence")
        return json.dumps(result, ensure_ascii=False)
    except Exception as mem_err:
        return json.dumps({"status": "error", "reason": str(mem_err)}, ensure_ascii=False)


def _strategy(nome: str):
    def handler(ctx: ToolContext, args: dict):
        import strategy_tools

        fn = getattr(strategy_tools, nome)
        return fn(ctx.db, ctx.user_uid, **args)

    return handler


# ---------------------------------------------------------------------------
# 3. Implementacoes extraidas das closures de askCopilotoHermes
# ---------------------------------------------------------------------------

_WEB_TRIGGERS = (
    "http://", "https://", "www.", "internet", "na web", "busca online",
    "pesquise", "pesquisar", "notícia", "noticias", "cotação", "cotacao",
    "atualiz", "link", "site", "acesse",
)


def pesquisar_internet(ctx: ToolContext, args: dict, *, prompt_gate: str | None = None):
    """Busca na internet via Tavily.

    `prompt_gate` existe para o copiloto web: la a tool so pode disparar se o
    prompt do usuario mencionar internet/URL, porque o Gemini tendia a chamar a
    busca sem o usuario ter pedido. Canais como o MCP passam `None` e o portao
    fica desligado — quando o Claude escolhe esta tool, a escolha ja e explicita
    e nao existe "prompt do usuario" para inspecionar.
    """
    import requests as _req

    if prompt_gate is not None:
        if not any(t in prompt_gate.lower() for t in _WEB_TRIGGERS):
            return ('{"blocked": true, "reason": "O prompt nao menciona internet, URL ou busca '
                    'atual. Use esta ferramenta apenas quando o usuario pedir explicitamente '
                    'informacoes da web."}')

    try:
        from main import _cached_doc_get

        keys_doc_web = _cached_doc_get(ctx.db, "system", "api_keys")
        tavily_key = keys_doc_web.to_dict().get("tavily_api_key") if keys_doc_web.exists else None
        if not tavily_key:
            return ('{"error": "Tavily API key nao configurada. Informe ao usuario que a busca '
                    'na internet esta indisponivel no momento."}')

        resp = _req.post(
            "https://api.tavily.com/search",
            json={
                "api_key": tavily_key,
                "query": args.get("query"),
                "search_depth": "advanced",
                "include_answer": True,
                "include_raw_content": False,
                "max_results": 5,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        parts = []
        if data.get("answer"):
            parts.append(f"RESPOSTA DIRETA: {data['answer']}\n")
        for r in data.get("results", []):
            parts.append(
                f"FONTE: {r.get('title', '')} ({r.get('url', '')})\n{r.get('content', '')}"
            )
        return "\n\n".join(parts) if parts else "Nenhum resultado encontrado para esta busca."
    except _req.exceptions.Timeout:
        return ('{"error": "Timeout ao acessar a Tavily API. Informe ao usuario que a busca '
                'demorou demais e tente novamente."}')
    except Exception as web_err:
        return (f'{{"error": "Falha na busca: {web_err}. Informe ao usuario que nao foi '
                f'possivel realizar a pesquisa."}}')


def ler_pagina_web(ctx: ToolContext, args: dict):
    import requests as _req

    url = args.get("url")
    try:
        resp = _req.get(
            f"https://r.jina.ai/{url}",
            headers={"Accept": "text/markdown", "X-No-Cache": "true"},
            timeout=25,
        )
        if resp.status_code in (403, 401, 429):
            return ('{"error": "Falha de acesso: O servidor alvo bloqueou a leitura por questoes '
                    'de seguranca (Cloudflare/Paywall/Rate-limit). Informe ao usuario de forma '
                    'clara que nao foi possivel ler este conteudo especifico."}')
        resp.raise_for_status()

        content = resp.text.strip()
        if len(content) > 12000:
            content = content[:12000] + "\n\n[...conteudo truncado para caber no contexto...]"
        return content if content else "A pagina foi carregada mas nao contem conteudo legivel."
    except _req.exceptions.Timeout:
        return ('{"error": "Timeout ao tentar ler a pagina. O servidor demorou demais para '
                'responder. Informe ao usuario."}')
    except Exception as scrape_err:
        return (f'{{"error": "Falha ao ler a pagina: {scrape_err}. Informe ao usuario que nao '
                f'foi possivel acessar o conteudo."}}')


def registrar_correcao_procedimento(ctx: ToolContext, args: dict):
    try:
        import uuid as _corr_uuid

        _corr_id = str(_corr_uuid.uuid4())[:12]
        ctx.db.collection("correcoes_pendentes").document(_corr_id).set({
            "id": _corr_id,
            "area_tematica": args.get("area_tematica"),
            "titulo_procedimento": args.get("titulo_procedimento"),
            "correcao_descrita": args.get("correcao_descrita"),
            "novo_conteudo_proposto": args.get("novo_conteudo_proposto"),
            "justificativa_usuario": args.get("justificativa"),
            "status": "pendente",
            "data_criacao": firestore.SERVER_TIMESTAMP,
            "session_id": ctx.session_id or "",
            "task_id": ctx.task_id or "",
        })
        return (
            f"✅ Correcao para '{args.get('titulo_procedimento')}' registrada (ID: {_corr_id}). "
            "O Motor de Evolucao ira verificar a conformidade e atualizar o procedimento em "
            "segundo plano."
        )
    except Exception as _corr_err:
        return f"⚠️ Falha ao registrar correcao: {_corr_err}"


def registrar_no_diario(ctx: ToolContext, args: dict):
    try:
        alvo = (args.get("task_id_alvo") or ctx.task_id or "").strip()
        if not alvo:
            return "ERRO|Sem tarefa ativa. Informe o ID da tarefa onde registrar."
        nota = args.get("nota")
        if not (nota or "").strip():
            return "ERRO|Nota vazia."

        task_ref = ctx.db.collection("tarefas").document(alvo)
        task_doc = task_ref.get()
        if not task_doc.exists:
            return f"ERRO|Tarefa '{alvo}' nao encontrada."

        entry = {"data": datetime.now(timezone.utc).isoformat(), "nota": nota.strip()}
        task_ref.update({"acompanhamento": firestore.ArrayUnion([entry])})
        titulo_tarefa = (task_doc.to_dict() or {}).get("titulo", alvo)
        return json.dumps(
            {"status": "ok", "task_id": alvo, "titulo": titulo_tarefa}, ensure_ascii=False
        )
    except Exception as _err:
        return f"ERRO|{_err}"


def preparar_vinculo_contatos(ctx: ToolContext, args: dict):
    try:
        task_id = args.get("task_id")
        if not task_id:
            return "ERRO|task_id e obrigatorio."
        tdoc = ctx.db.collection("tarefas").document(str(task_id)).get()
        if not tdoc.exists:
            return f"ERRO|Tarefa '{task_id}' nao encontrada."
        return json.dumps({
            "kind": "contact_link",
            "task_id": task_id,
            "task_titulo": (tdoc.to_dict() or {}).get("titulo", ""),
            "mencoes": args.get("mencoes") or [],
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)
    except Exception as _re:
        return f"ERRO|{_re}"


def preparar_atualizacao_contato(ctx: ToolContext, args: dict):
    try:
        nome = args.get("nome")
        campos_novos = args.get("campos_novos") or {}
        pessoa_id = args.get("pessoa_id")
        if not nome or not campos_novos:
            return "ERRO|nome e campos_novos sao obrigatorios."

        contato_atual = None
        if pessoa_id:
            pdoc = ctx.db.collection("perfil_pessoas").document(str(pessoa_id)).get()
            if not pdoc.exists:
                return f"ERRO|Contato '{pessoa_id}' nao encontrado."
            contato_atual = pdoc.to_dict()

        return json.dumps({
            "kind": "contact_upsert",
            "modo": "update" if pessoa_id else "create",
            "pessoa_id": pessoa_id,
            "nome": nome,
            "contato_atual": contato_atual,
            "campos_novos": campos_novos,
            "justificativa": args.get("justificativa") or "",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, default=str)
    except Exception as _re:
        return f"ERRO|{_re}"


def registrar_interacao_contato(ctx: ToolContext, args: dict):
    try:
        pessoa_id = args.get("pessoa_id")
        descricao = args.get("descricao")
        if not pessoa_id or not descricao:
            return "ERRO|pessoa_id e descricao sao obrigatorios."

        pref = ctx.db.collection("perfil_pessoas").document(str(pessoa_id)).get()
        if not pref.exists:
            return f"ERRO|Contato '{pessoa_id}' nao encontrado."

        now_iso = datetime.now(timezone.utc).isoformat()
        sess_id = args.get("sessao_copiloto_id") or ctx.session_id
        payload = {
            "pessoa_id": str(pessoa_id),
            "descricao": str(descricao)[:280],
            "tipo": "mencao_copiloto",
            "data": now_iso,
            "data_criacao": now_iso,
        }
        if args.get("tarefa_id"):
            payload["tarefa_id"] = str(args["tarefa_id"])
        if sess_id:
            payload["sessao_copiloto_id"] = str(sess_id)

        # Tag "Copiloto" faz o contato aparecer no filtro correspondente da UI.
        try:
            tags_atuais = (pref.to_dict() or {}).get("tags") or []
            if "Copiloto" not in tags_atuais:
                ctx.db.collection("perfil_pessoas").document(str(pessoa_id)).update(
                    {"tags": tags_atuais + ["Copiloto"]}
                )
        except Exception as _tag_err:
            print(f"[hermes_tools] Aviso: falha ao marcar tag Copiloto em {pessoa_id}: {_tag_err}")

        new_ref = ctx.db.collection("interacoes_pessoas").document()
        new_ref.set(payload)
        return json.dumps({"status": "ok", "interacao_id": new_ref.id}, ensure_ascii=False)
    except Exception as _re:
        return f"ERRO|{_re}"


def _normalize_hhmm(t_str: str | None) -> str | None:
    if not t_str:
        return None
    t_str = str(t_str).strip()
    if ":" not in t_str:
        return None
    try:
        h, m = t_str.split(":")
        return f"{int(h):02d}:{int(m):02d}"
    except Exception:
        return t_str


def criar_acao_no_sistema(
    ctx: ToolContext,
    args: dict,
    *,
    areas_validas: list | None = None,
    artefatos_pendentes_vinculo: list | None = None,
):
    """Cria uma acao no Hermes.

    `areas_validas` e `artefatos_pendentes_vinculo` sao injetados pelo copiloto
    web, que ja os tem carregados no escopo do request. Canais sem eles (MCP)
    passam `None`: as areas sao recarregadas do Firestore e nao ha anexos
    pendentes para vincular, porque nao houve upload nesta mensagem.
    """
    from hermes_core_logic import (
        carregar_areas_tematicas_validas,
        normalizar_area_tematica,
    )
    from main import (
        claim_action_dedup_slot,
        get_calendar_service,
        get_target_calendar_id,
        release_action_dedup_slot,
        store_action_dedup_result,
        _cached_doc_get,
    )

    titulo = args.get("titulo")
    data_limite = args.get("data_limite")
    horario_inicio = _normalize_hhmm(args.get("horario_inicio"))
    horario_fim = _normalize_hhmm(args.get("horario_fim"))
    prazo_final = args.get("prazo_final")

    try:
        import uuid as _uuid
        from zoneinfo import ZoneInfo

        if areas_validas is None:
            areas_validas = carregar_areas_tematicas_validas(ctx.db)
        area_tematica = normalizar_area_tematica(args.get("area_tematica") or "GERAL", areas_validas)

        now_iso = datetime.now(timezone.utc).isoformat()
        now_local = datetime.now(ZoneInfo("America/Sao_Paulo"))
        today_brt = now_local.strftime("%Y-%m-%d")

        if not data_limite or str(data_limite) < today_brt:
            data_limite = today_brt
        if prazo_final and str(prazo_final) < today_brt:
            prazo_final = today_brt

        if data_limite == today_brt and horario_inicio:
            current_time_str = now_local.strftime("%H:%M")
            if horario_inicio < current_time_str:
                return (f"ERRO|Nao e possivel agendar um horario anterior ao horario atual "
                        f"({current_time_str}). Por favor, escolha um horario posterior.")

        # Idempotencia: reivindica atomicamente a chave (titulo, data, horario) para
        # evitar criar a mesma acao duas ou tres vezes quando o modelo chama esta tool
        # mais de uma vez para o mesmo pedido.
        _dedup_status, _dedup_task_id = claim_action_dedup_slot(
            ctx.db, titulo, data_limite, horario_inicio
        )
        if _dedup_status == "duplicate":
            return f"OK|{_dedup_task_id}"
        if _dedup_status == "pending":
            return ("ERRO|Esta acao ja esta sendo registrada por outra chamada. Aguarde alguns "
                    "segundos e verifique a lista de acoes antes de tentar de novo.")

        task_id = str(_uuid.uuid4())[:20]

        try:
            import hermes_calendar_tools as hc_tools

            c_service = get_calendar_service()
            c_id = get_target_calendar_id(ctx.db)
            if c_service and c_id and horario_inicio and horario_fim:
                hc_tools.reagendar_acoes_hermes(
                    ctx.db, c_service, c_id, data_limite, horario_inicio, horario_fim
                )
        except Exception as e:
            print(f"[hermes_tools] Erro ao reagendar iterativo: {e}")

        # `str(passo)` num objeto dava o repr do dicionario: uma etapa enviada
        # como {"texto": ..., "data_prevista": ...} virava a string
        # "{'texto': ..., 'data_prevista': ...}" dentro do plano. Duas outras
        # copias desta conversao ja usavam `converter_plano`; esta, que e a do
        # MCP, tinha ficado para tras.
        import subtarefas as _sub
        plano_convertido = _sub.converter_plano(args.get("plano_acao"))

        tags = args.get("tags") or []
        source_knowledge_id = None
        source_knowledge_text = args.get("sourceKnowledgeText")
        if source_knowledge_text:
            from knowledge_graph import _get_embedding

            try:
                kg_id = str(_uuid.uuid4())[:20]
                keys_doc = _cached_doc_get(ctx.db, "system", "api_keys")
                gemini_key = keys_doc.to_dict().get("gemini_api_key") if keys_doc.exists else None
                if not gemini_key:
                    raise ValueError("Gemini API Key nao encontrada (system/api_keys).")

                ctx.db.collection("conhecimento_mestre").document(kg_id).set({
                    "id": kg_id,
                    "titulo": f"Contexto de E-mail: {titulo}",
                    "tipo": "paragrafo",
                    "conteudo_regra": source_knowledge_text,
                    "justificativa_da_regra": "Contexto extraido via integracao Gmail-Hermes",
                    "tags": tags,
                    "area_tematica": area_tematica,
                    "status": "ativo",
                    "origem": "gmail_copiloto",
                    "task_origin_id": task_id,
                    "peso_semantico": 1.0,
                    "data_criacao": now_iso,
                    "data_atualizacao": now_iso,
                    "embedding": _get_embedding(source_knowledge_text, gemini_key),
                })
                source_knowledge_id = kg_id
            except Exception as e_kg:
                print(f"[hermes_tools] Erro ao criar No de Fonte do Gmail: {e_kg}")

        tipo_acao = args.get("tipo_acao") or "fast"
        doc = {
            "titulo": (titulo or "").strip(),
            "descricao": args.get("descricao") or "",
            "area_tematica": (area_tematica or "GERAL").upper(),
            "data_limite": data_limite or None,
            "prazo_final": prazo_final or None,
            "tipo_acao": tipo_acao if tipo_acao in ("fast", "deep") else "fast",
            "tags": list(tags),
            "notas": args.get("notas") or "",
            "plano_acao": plano_convertido,
            "status": "em andamento",
            # "copiloto" em qualquer canal: e o mesmo cerebro decidindo, e a UI
            # ja filtra por essa origem. Quem chamou de fato fica no mcp_audit_log.
            "origem": "copiloto",
            "projeto": "GERAL",
            "data_criacao": now_iso,
            "data_atualizacao": now_iso,
            "contabilizar_meta": True,
            # Vinculo estrategico na criacao. O campo ja existia nas acoes e so
            # era preenchido pela tela; sem ele aqui, uma elevacao aceita nascia
            # sem o objetivo que a justificou — e o card prometia o contrario.
            **({"estrategia_objetivo_id": str(args["estrategia_objetivo_id"]).strip()}
               if str(args.get("estrategia_objetivo_id") or "").strip() else {}),
            "acompanhamento": [],
            "entregas_relacionadas": [],
            "pool_dados": [],
            "plano_acao_historico": [],
            "sync_status": "new",
            "horario_inicio": horario_inicio,
            "horario_fim": horario_fim,
            "sourceGmailMessageId": args.get("sourceGmailMessageId") or None,
            "sourceKnowledgeId": source_knowledge_id or None,
        }

        dias_semana = args.get("dias_da_semana_recorrencia")
        dia_mes = args.get("dia_do_mes_recorrencia")
        if args.get("recorrencia_semanal") and dias_semana:
            doc["recorrencia"] = {
                "ativo": True,
                "frequencia": "semanal",
                "dias_da_semana": sorted({max(0, min(6, int(d))) for d in dias_semana}),
            }
            intervalo = args.get("intervalo_semanas_recorrencia")
            if intervalo and int(intervalo) > 1:
                doc["recorrencia"]["intervalo_semanas"] = min(12, int(intervalo))
        elif args.get("recorrencia_mensal") and dia_mes:
            doc["recorrencia"] = {
                "ativo": True,
                "frequencia": "mensal",
                "dia_do_mes": max(1, min(31, int(dia_mes))),
            }

        if artefatos_pendentes_vinculo:
            # Anexos enviados na mesma mensagem, antes de a tarefa existir.
            doc["acompanhamento"] = [
                {
                    "data": item["data_criacao"],
                    "nota": (f"📎 [Copiloto] Arquivo '{item['nome']}' "
                             f"({item.get('_natureza') or 'documento'}) carregado junto com a "
                             f"criacao desta acao."),
                }
                for item in artefatos_pendentes_vinculo
            ]
            doc["pool_dados"] = [
                {k: v for k, v in item.items() if k != "_natureza"}
                for item in artefatos_pendentes_vinculo
            ]
            artefatos_pendentes_vinculo.clear()

        ctx.db.collection("tarefas").document(task_id).set(doc)
        store_action_dedup_result(ctx.db, titulo, data_limite, horario_inicio, task_id)
        print(f"[hermes_tools] Acao criada: id={task_id}, titulo='{titulo}'")
        return f"OK|{task_id}"
    except Exception as _ce:
        print(f"[hermes_tools] Erro ao criar acao: {_ce}")
        release_action_dedup_slot(ctx.db, titulo, data_limite, horario_inicio)
        return f"ERRO|{_ce}"


_ALLOWED_EDIT_FIELDS = {
    "titulo", "descricao", "data_limite", "data_inicio", "prazo_final",
    "horario_inicio", "horario_fim", "status", "tags", "area_tematica",
    "tipo_acao", "notas", "email_link_optout",
}


def _normalizar_status_acao(valor):
    if valor is None:
        return valor
    raw = str(valor).strip().lower()
    try:
        import unicodedata

        raw = "".join(
            c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn"
        )
    except Exception:
        pass
    raw = " ".join(raw.replace("_", " ").replace("-", " ").split())
    if raw in ("concluido", "concluida", "concluir", "finalizado", "finalizada", "completed", "done"):
        return "concluído"
    if raw in ("stand by", "standby", "pausado", "pausada", "pausar"):
        return "stand-by"
    if raw in ("em andamento", "andamento", "pendente", "aberto", "aberta", "reabrir"):
        return "em andamento"
    if raw in ("excluido", "excluir", "excluida", "cancelado", "cancelar", "cancelada",
               "deletar", "deletado", "apagar", "remover"):
        return "excluído"
    return valor


def _stringify_campo(valor):
    if isinstance(valor, dict):
        return json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor)
    return str(valor) if valor is not None else ""


def preparar_edicao_em_lote(ctx: ToolContext, args: dict):
    try:
        itens = args.get("itens")
        if not itens or not isinstance(itens, list):
            return "ERRO|Forneca uma lista de itens com 'task_id' e 'alteracoes'."

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prepared_items = []

        for item in itens:
            tid = str(item.get("task_id") or "").strip()
            if not tid:
                continue
            alteracoes = item.get("alteracoes") or {}

            for campo, rotulo in (("data_limite", "A data de execucao"), ("prazo_final", "O prazo final")):
                if campo in alteracoes:
                    val = alteracoes[campo]
                    if val and val not in ("-", "0000-00-00") and val < today_str:
                        return f"ERRO|{rotulo} da acao '{tid}' nao pode ser no passado ({val})."

            task_doc = ctx.db.collection("tarefas").document(tid).get()
            if not task_doc.exists:
                return f"ERRO|Acao '{tid}' nao encontrada."

            task_data = task_doc.to_dict() or {}
            if task_data.get("status") in ("concluído", "excluído") and alteracoes.get(
                "status"
            ) not in ("em andamento", "stand-by"):
                return (f"ERRO|A acao '{task_data.get('titulo', tid)}' ja foi concluida ou "
                        f"excluida e nao pode ser editada.")

            alteracoes_diff = {}
            for campo, novo_valor in alteracoes.items():
                if campo not in _ALLOWED_EDIT_FIELDS:
                    continue
                if campo == "status":
                    novo_valor = _normalizar_status_acao(novo_valor)
                alteracoes_diff[campo] = {
                    "original": _stringify_campo(task_data.get(campo)),
                    "novo": _stringify_campo(novo_valor),
                    "novo_raw": novo_valor,
                }

            if not alteracoes_diff:
                continue

            snapshot_ts = task_data.get("data_atualizacao") or task_data.get("data_criacao", "")
            prepared_items.append({
                "task_id": tid,
                "titulo": task_data.get("titulo", "Acao sem titulo"),
                "alteracoes": alteracoes_diff,
                "snapshot_ts": str(snapshot_ts),
            })

        if not prepared_items:
            return "ERRO|Nenhum campo valido para editar nas acoes fornecidas."

        return json.dumps({
            "tipo": "edicao_em_lote",
            "items": prepared_items,
            "justificativa": args.get("justificativa") or "Edicao de multiplas acoes via Copiloto Hermes.",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)
    except Exception as _pe:
        return f"ERRO|{_pe}"


def _coletar_tarefas_lote(ctx: ToolContext, filtro_data, task_ids, status_excluidos):
    tasks = []
    if task_ids:
        for tid in task_ids:
            tdoc = ctx.db.collection("tarefas").document(str(tid)).get()
            if tdoc.exists:
                t = tdoc.to_dict()
                if t.get("status") not in status_excluidos:
                    tasks.append({"_doc_id": str(tid), **t})
    else:
        q = (
            ctx.db.collection("tarefas")
            .where("data_limite", "==", filtro_data)
            .where("status", "in", ["em andamento", "stand-by"])
            .get()
        )
        for qdoc in q:
            tasks.append({"_doc_id": qdoc.id, **qdoc.to_dict()})
    return tasks


def preparar_reagendamento_em_lote(ctx: ToolContext, args: dict):
    try:
        filtro_data = args.get("filtro_data")
        task_ids = args.get("task_ids")
        if not filtro_data and not task_ids:
            return "ERRO|Forneca filtro_data (YYYY-MM-DD) ou task_ids (lista de IDs)."

        tasks = _coletar_tarefas_lote(ctx, filtro_data, task_ids, ("concluído", "cancelado"))
        if not tasks:
            return "ERRO|Nenhuma acao encontrada com os criterios informados."

        estrategia = args.get("estrategia") or "data_criacao"
        if estrategia == "tipo_acao":
            tasks.sort(key=lambda x: (0 if x.get("tipo_acao") == "fast" else 1, x.get("data_criacao", "")))
        elif estrategia == "alfa":
            tasks.sort(key=lambda x: x.get("titulo", "").lower())
        else:
            tasks.sort(key=lambda x: x.get("data_criacao", ""))

        nova_data_inicio = args.get("nova_data_inicio")
        try:
            start_date = datetime.strptime(nova_data_inicio, "%Y-%m-%d").date()
            today_date = datetime.now(timezone.utc).date()
            if start_date < today_date:
                start_date = today_date
        except (ValueError, TypeError):
            return f"ERRO|Formato de data invalido: '{nova_data_inicio}'. Use YYYY-MM-DD."

        def _next_weekday(d):
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d

        max_por_semana = int(args.get("max_por_semana") or 5)
        day_cursor = _next_weekday(start_date)
        count_this_week = 0
        items = []

        for task in tasks:
            if count_this_week >= max_por_semana:
                day_cursor += timedelta(days=7 - day_cursor.weekday())
                day_cursor = _next_weekday(day_cursor)
                count_this_week = 0

            items.append({
                "task_id": task["_doc_id"],
                "titulo": task.get("titulo", ""),
                "data_limite_original": task.get("data_limite", ""),
                "horario_inicio_original": task.get("horario_inicio"),
                "horario_fim_original": task.get("horario_fim"),
                "nova_data_limite": day_cursor.strftime("%Y-%m-%d"),
                "novo_horario_inicio": None,
                "novo_horario_fim": None,
            })

            count_this_week += 1
            day_cursor = _next_weekday(day_cursor + timedelta(days=1))

        return json.dumps({
            "items": items,
            "justificativa": args.get("justificativa")
            or f"Reagendamento em lote para semana de {nova_data_inicio}.",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)
    except Exception as _re:
        return f"ERRO|{_re}"


def preparar_remocao_horarios_em_lote(ctx: ToolContext, args: dict):
    try:
        filtro_data = args.get("filtro_data")
        task_ids = args.get("task_ids")
        if not filtro_data and not task_ids:
            return "ERRO|Forneca filtro_data (YYYY-MM-DD) ou task_ids (lista de IDs)."

        tasks = _coletar_tarefas_lote(ctx, filtro_data, task_ids, ("concluído", "excluído"))
        tasks_com_horario = [t for t in tasks if t.get("horario_inicio")]
        if not tasks_com_horario:
            if tasks:
                return "ERRO|Nenhuma das acoes encontradas possui horario definido."
            return "ERRO|Nenhuma acao encontrada com os criterios informados."

        items = [{
            "task_id": task["_doc_id"],
            "titulo": task.get("titulo", ""),
            "data_limite_original": task.get("data_limite", ""),
            "horario_inicio_original": task.get("horario_inicio"),
            "horario_fim_original": task.get("horario_fim"),
            "nova_data_limite": task.get("data_limite", ""),
            "novo_horario_inicio": None,
            "novo_horario_fim": None,
        } for task in tasks_com_horario]

        return json.dumps({
            "items": items,
            "justificativa": args.get("justificativa") or "Remocao de horarios em lote via Copiloto Hermes.",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)
    except Exception as _re:
        return f"ERRO|{_re}"


def gerar_imagem(ctx: ToolContext, args: dict):
    from google.genai import types

    from gemini_cost_controls import check_and_increment_limit

    try:
        limit_images = int(os.environ.get("LIMIT_IMAGE_GENERATION", "5"))
        if not check_and_increment_limit(ctx.db, ctx.user_uid, "image_generation", limit_images):
            return "ERRO|Voce atingiu o limite diario de 5 geracoes de imagem."

        import uuid

        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=args.get("proporcao") or "1:1", image_size="1K"
            ),
            thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
        )
        resp = ctx.genai_client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=[args.get("prompt")],
            config=config,
        )

        image_bytes = None
        if getattr(resp, "candidates", None):
            cand = resp.candidates[0]
            if getattr(cand, "content", None) and getattr(cand.content, "parts", None):
                for part in cand.content.parts:
                    if getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
                        image_bytes = part.inline_data.data
                        break

        if not image_bytes:
            return "ERRO|Nao foi possivel gerar a imagem."

        from hermes_core_logic import _blob_public_url, _get_hermes_storage_bucket

        bucket = _get_hermes_storage_bucket()
        blob = bucket.blob(f"imagens_geradas/img_{uuid.uuid4().hex[:8]}.jpg")
        blob.upload_from_string(image_bytes, content_type="image/jpeg")
        url = _blob_public_url(blob)
        return f"![Imagem Gerada]({url})\n\n*(Imagem gerada via Imagen 3. URL: {url})*"
    except Exception as e:
        import traceback

        print(f"[hermes_tools] Erro ao gerar imagem: {e}\n{traceback.format_exc()}")
        return f"⚠️ Erro ao gerar imagem: {e}"


def consultar_processo_sipac(ctx: ToolContext, args: dict):
    numero_processo = args.get("numero_processo")
    try:
        from hermes_core_logic import _call_web_callable

        res = _call_web_callable(
            function_name="consultarProcessoSipac",
            data={"numeroProcesso": numero_processo},
            user_uid=ctx.user_uid,
        )

        lines = [
            f"=== DETALHES DO PROCESSO SIPAC {res.get('numeroProcesso')} ===",
            f"Status: {res.get('status')}",
            f"Unidade Atual: {res.get('unidadeAtual')}",
            f"Natureza: {res.get('natureza')}",
            f"Assunto: {res.get('assuntoCodigo')} - {res.get('assuntoDescricao')}",
        ]
        if res.get("observacao") and res.get("observacao") != "Não informado":
            lines.append(f"Observacao: {res.get('observacao')}")
        lines.append(f"Autuacao: {res.get('dataAutuacion')} as {res.get('horarioAutuacion')}")

        lines.append("\nInteressados:")
        for i in res.get("interessados", []):
            lines.append(f"- {i.get('tipo')}: {i.get('nome')}")

        lines.append("\nDocumentos Publicos:")
        for d in res.get("documentos", []):
            url_str = f" | Link: {d.get('url')}" if d.get("url") else " | (Acesso Restrito)"
            lines.append(
                f"- Seq #{d.get('ordem')} - Tipo: {d.get('tipo')} | Data: {d.get('data')} | "
                f"Origem: {d.get('unidadeOrigem')}{url_str}"
            )

        lines.append("\nMovimentacoes Recentes (Linha do Tempo):")
        for m in res.get("movimentacoes", [])[:8]:
            lines.append(
                f"- [{m.get('data')} {m.get('horario')}] De {m.get('unidadeOrigem')} para "
                f"{m.get('unidadeDestino')} | Recebedor: {m.get('usuarioRecebedor') or 'N/A'}"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"⚠️ Erro ao consultar processo {numero_processo} no SIPAC: {e}"


def acompanhar_processo_sipac(ctx: ToolContext, args: dict):
    import re as _re

    numero_processo = args.get("numero_processo")
    acompanhar = args.get("acompanhar")
    acompanhar = True if acompanhar is None else bool(acompanhar)
    try:
        from hermes_core_logic import _call_web_callable

        res = _call_web_callable(
            function_name="consultarProcessoSipac",
            data={"numeroProcesso": numero_processo},
            user_uid=ctx.user_uid,
        )

        clean_num = _re.sub(r"[^\d]", "", str(numero_processo))
        doc_id = f"{ctx.user_uid}_{clean_num}" if ctx.user_uid else f"global_{clean_num}"
        ctx.db.collection("sipac_processos").document(doc_id).set({
            "acompanhar": acompanhar,
            "numeroProcesso": res.get("numeroProcesso", numero_processo),
            "uid": ctx.user_uid or "global",
            "ultimaConsulta": datetime.now(timezone.utc).isoformat(),
            **res,
        }, merge=True)

        status_str = "ATIVADO" if acompanhar else "DESATIVADO"
        return (f"Sucesso: O acompanhamento automatico para o processo {numero_processo} "
                f"foi {status_str}.")
    except Exception as e:
        return f"⚠️ Erro ao alterar acompanhamento para o processo {numero_processo}: {e}"


# ---------------------------------------------------------------------------
# 4. Callables existentes expostas como tool (aplicam as propostas `preparar_*`)
# ---------------------------------------------------------------------------

def _mensagem_de_erro(exc: Exception, origem: str = "") -> str:
    """Uma mensagem de erro que nunca sai vazia.

    `https_fn.HttpsError` nao implementa `__str__` util: a mensagem fica em
    `.message` e o `str()` volta vazio. Em 28/08/2026 tres chamadas de
    `editar_acao` responderam `{"erro": ""}` e nada foi gravado — quem leu
    concluiu que a edicao tinha passado.
    """
    for atributo in ("message", "detail", "args"):
        valor = getattr(exc, atributo, None)
        if isinstance(valor, (list, tuple)):
            valor = "; ".join(str(v) for v in valor if str(v).strip())
        texto = str(valor or "").strip()
        if texto:
            return f"{type(exc).__name__}: {texto}" + (f" (em {origem})" if origem else "")
    codigo = getattr(exc, "code", None)
    return (f"{type(exc).__name__} sem mensagem"
            + (f", codigo {codigo}" if codigo else "")
            + (f" (em {origem})" if origem else "")
            + " — a operacao NAO foi aplicada.")


def _via_callable(nome_callable: str, mapear=None):
    """Expoe uma Cloud Function callable como tool.

    As tools `preparar_*` so montam uma proposta — quem grava e a callable
    correspondente, acionada pelo card de confirmacao na UI do Hermes. Canais
    sem essa UI precisam do outro lado do par, senao a proposta morre no ar.
    """

    def handler(ctx: ToolContext, args: dict):
        import main

        from tools.callable_bridge import invoke_callable

        data = mapear(ctx, args) if mapear else dict(args)
        try:
            return invoke_callable(
                getattr(main, nome_callable), data, uid=ctx.user_uid, token={"uid": ctx.user_uid}
            )
        except Exception as exc:
            # `str(exc)` era vazio para `HttpsError`, que guarda o texto em
            # `.message` — a tool respondia {"erro": ""} e quem lia entendia que
            # nao havia erro. Um erro sem mensagem e pior que uma excecao.
            return {"erro": _mensagem_de_erro(exc, nome_callable)}

    return handler


def _map_confirmar_edicao_acao(ctx: ToolContext, args: dict):
    return {
        "taskId": args.get("task_id"),
        "alteracoes": args.get("alteracoes") or {},
        "snapshotTs": args.get("snapshot_ts") or "",
        "sessionId": ctx.session_id,
    }


def _map_confirmar_edicao_em_lote(ctx: ToolContext, args: dict):
    return {
        "items": args.get("items") or [],
        "justificativa": args.get("justificativa") or "Edicao em lote via canal externo.",
        "sessionId": ctx.session_id,
    }


def _map_confirmar_reagendamento(ctx: ToolContext, args: dict):
    return {
        "items": args.get("items") or [],
        "justificativa": args.get("justificativa") or "Reagendamento em lote via canal externo.",
        "sessionId": ctx.session_id,
    }



# ---------------------------------------------------------------------------
# 5. Escrita direta — o par preparar/confirmar sem a ida e volta
# ---------------------------------------------------------------------------
#
# `preparar_*` existe porque a UI do Hermes renderiza um card de confirmacao: a
# proposta e montada, o usuario clica, a callable grava. Num cliente MCP nao ha
# card — o proprio cliente mostra ao usuario o que vai fazer antes de fazer —
# entao o par vira duas chamadas para uma acao so.
#
# Estas versoes diretas nao afrouxam validacao nenhuma: elas chamam as mesmas
# callables de gravacao, que revalidam tudo (acao existe, nao esta concluida,
# campo permitido, status normalizado). O que some e so o passo intermediario.
# As `preparar_*` continuam existindo para a web.


# Campos que uma acao aceita editar. Fora daqui, nada e gravado.
_CAMPOS_EDITAVEIS = (
    "titulo", "descricao", "data_limite", "prazo_final", "horario_inicio",
    "horario_fim", "status", "tags", "area_tematica", "tipo_acao", "notas",
    "projeto", "estrategia_objetivo_id",
)


def editar_acao(ctx: ToolContext, args: dict):
    """Aplica a edicao direto, sem passar por preparar_edicao_acao.

    Sem `snapshot_ts`: aquela checagem protege contra a acao mudar entre a
    geracao do card e o clique do usuario, e aqui nao ha intervalo nenhum.

    Aceita `alteracoes={"data_limite": ...}` e tambem os campos soltos no nivel
    de cima. O schema pede o aninhado, mas chamar com `data_limite=...` direto e
    a leitura natural do nome da tool — e ate 28/08/2026 essa chamada era aceita
    em silencio, sem alterar nada e respondendo com erro vazio.
    """
    alteracoes = dict(args.get("alteracoes") or {})
    for campo in _CAMPOS_EDITAVEIS:
        if campo in args and campo not in alteracoes and args[campo] is not None:
            alteracoes[campo] = args[campo]

    if not alteracoes:
        return {"erro": ("Nenhum campo para alterar. Passe `alteracoes` como um mapa "
                         "campo -> novo valor (ex.: alteracoes={\"data_limite\": "
                         "\"2026-09-01\"}), ou os campos direto na chamada. "
                         f"Campos aceitos: {', '.join(_CAMPOS_EDITAVEIS)}."),
                "task_id": args.get("task_id"), "aplicado": False}

    resultado = _via_callable("confirmarEdicaoAcao", _map_confirmar_edicao_acao)(ctx, {
        "task_id": args.get("task_id"),
        "alteracoes": alteracoes,
    })
    if not isinstance(resultado, dict) or "erro" in resultado:
        return resultado

    # `campos_alterados` vem da callable, que sabe o que de fato gravou —
    # pedir `data_limite` tambem move `data_inicio`. O que se pediu fica em
    # `campos_pedidos`, para a diferenca ser visivel em vez de contraditoria.
    resultado.setdefault("campos_alterados", sorted(alteracoes.keys()))
    resultado["campos_pedidos"] = sorted(alteracoes.keys())

    # `motivo_adiamento` era aceito e descartado em silencio. Numa acao adiada
    # 33 vezes, e a unica informacao que explica o porque — vira linha de
    # diario, que e onde ela fica junto do resto da historia da acao.
    motivo = str(args.get("motivo_adiamento") or args.get("motivo") or "").strip()
    if motivo and ctx.db:
        try:
            from datetime import datetime, timezone

            from google.cloud import firestore as gcf

            ctx.db.collection("tarefas").document(str(args.get("task_id"))).update({
                "acompanhamento": gcf.ArrayUnion([{
                    "data": datetime.now(timezone.utc).isoformat(),
                    "nota": f"[Copiloto Hermes] Motivo do ajuste: {motivo}",
                }])
            })
            resultado["motivo_registrado"] = True
        except Exception as exc:  # noqa: BLE001
            resultado["motivo_registrado"] = False
            resultado["aviso"] = f"A edicao foi aplicada, mas o motivo nao foi gravado: {exc}"
    return resultado


def editar_acoes_em_lote(ctx: ToolContext, args: dict):
    """Edita varias acoes de uma vez, sem o passo de preparacao.

    `confirmarEdicaoEmLote` aceita tanto o formato cru (campo -> valor) quanto o
    diff que `preparar_edicao_em_lote` produz, entao os itens passam direto.
    """
    return _via_callable("confirmarEdicaoEmLote", _map_confirmar_edicao_em_lote)(ctx, {
        "items": args.get("itens") or [],
        "justificativa": args.get("justificativa"),
    })


def reagendar_acoes_em_lote(ctx: ToolContext, args: dict):
    """Redistribui acoes por dias uteis e ja aplica.

    Aqui a etapa de preparacao NAO e descartada: e ela que faz a conta da
    distribuicao (respeitando `max_por_semana`, pulando fim de semana). O que se
    elimina e a volta ao cliente no meio do caminho.
    """
    proposta = execute("preparar_reagendamento_em_lote", args, ctx)
    if isinstance(proposta, str) and proposta.startswith("ERRO|"):
        return proposta

    try:
        dados = json.loads(proposta) if isinstance(proposta, str) else proposta
    except json.JSONDecodeError:
        return f"ERRO|Resposta inesperada ao preparar o reagendamento: {str(proposta)[:200]}"

    itens = dados.get("items") or []
    if not itens:
        return "ERRO|Nenhuma acao para reagendar."

    resultado = _via_callable("confirmarReagendamentoEmLote", _map_confirmar_reagendamento)(ctx, {
        "items": itens,
        "justificativa": dados.get("justificativa"),
    })
    if isinstance(resultado, dict):
        resultado["reagendadas"] = len(itens)
    return resultado


def anexar_arquivo(ctx: ToolContext, args: dict):
    """Sobe um arquivo para o Drive e vincula a uma acao, numa chamada so."""
    from tools.anexar_arquivo import anexar

    return anexar(ctx, args)


def _whatsapp(nome: str):
    """Handler das tools de WhatsApp, com a recusa por allowlist virando erro
    legivel em vez de excecao — o limite e esperado, nao falha."""
    def handler(ctx: ToolContext, args: dict):
        from tools import whatsapp_tools

        try:
            return getattr(whatsapp_tools, nome)(ctx, args)
        except whatsapp_tools.WhatsAppNaoMonitorado as limite:
            return {"erro": str(limite), "motivo": "chat_nao_monitorado"}
        except ValueError as exc:
            return {"erro": str(exc)}

    return handler


def preparar_upload(ctx: ToolContext, args: dict):
    """URL assinada para subir um arquivo local sem passa-lo pela conversa."""
    from tools.anexar_arquivo import preparar_upload as _preparar

    try:
        return _preparar(ctx, args)
    except ValueError as exc:
        return {"erro": str(exc)}


def remover_anexo(ctx: ToolContext, args: dict):
    """Remove um anexo da acao, preservando a trilha de auditoria do diario."""
    from tools.anexar_arquivo import remover_anexo as _remover

    return _remover(ctx, args)


def consultar_fatura_cartao(ctx: ToolContext, args: dict):
    """Lancamentos da fatura de cartao, com total por estabelecimento."""
    from fatura_cartao import consultar

    return consultar(
        ctx.db,
        competencia=args.get("competencia"),
        desde=args.get("desde"),
        estabelecimento=args.get("estabelecimento"),
        apenas_parceladas=bool(args.get("apenas_parceladas")),
        limite=int(args.get("limite") or 200),
    )


def consultar_compromissos_futuros(ctx: ToolContext, args: dict):
    """Quanto de cada mes futuro ja esta comprometido por compras parceladas.

    E o numero que a fatura sozinha nao da: ela diz o que foi gasto, isto diz
    quanto do mes que vem ja esta gasto antes de comecar.
    """
    from fatura_cartao import projetar_parcelas

    return projetar_parcelas(ctx.db, meses=int(args.get("meses") or 12))


def obter_estado_atual(ctx: ToolContext, args: dict):
    """Panorama do dia numa chamada: acoes, agenda, pendencias, heranca.

    Existe porque toda sessao de um cliente MCP comeca do zero e precisava de
    tres ou quatro chamadas so para se situar. Reusa o coletor deterministico do
    resumo matinal, que ja fazia esse trabalho para a tela inicial da web.
    """
    from morning_summary import build_morning_summary

    data = str(args.get("data") or "").strip() or None
    try:
        return build_morning_summary(ctx.db, data)
    except Exception as exc:  # noqa: BLE001
        return {"erro": f"Falha ao montar o estado atual: {exc}"}


def obter_acao(ctx: ToolContext, args: dict):
    """Uma acao inteira, sem corte. O oposto de `consultar_historico_acoes`.

    A busca existe para achar entre muitas, e por isso corta cada campo em 200
    caracteres (`busca_grafo.py`). Isso serve para relatar status e nao serve
    para reparar dado: em 28/08/2026 um plano corrompido nao pode ser corrigido
    pelo MCP porque regravar a partir do texto truncado apagaria o que nao
    estava visivel — perda silenciosa, exatamente o que se estava corrigindo.

    Aqui nada e truncado. O diario vem limitado por padrao porque cresce sem
    teto (ha acao com 35 entradas), mas o limite e explicito e ajustavel.
    """
    task_id = str(args.get("task_id") or ctx.task_id or "").strip()
    if not task_id:
        return {"erro": "Informe task_id."}

    snap = ctx.db.collection("tarefas").document(task_id).get()
    if not snap.exists:
        return {"erro": f"Acao '{task_id}' nao encontrada.", "status": "not_found"}

    import subtarefas

    d = snap.to_dict() or {}
    plano = d.get("plano_acao") or []
    feitas, totais = subtarefas.contar(plano)
    limite_diario = max(0, min(int(args.get("limite_diario") or 20), 200))
    acomp = [e for e in (d.get("acompanhamento") or []) if isinstance(e, dict)]

    etapas = []
    for i in plano:
        if not isinstance(i, dict) or not subtarefas.texto_de(i):
            continue
        etapa = {
            "id": i.get("id"),
            "texto": subtarefas.texto_de(i),   # inteiro, sem corte
            "estado": subtarefas.estado_de(i),
            "data_prevista": subtarefas.data_prevista_de(i, d.get("data_limite"), plano) or None,
        }
        if i.get("aguardando_de"):
            etapa["aguardando_de"] = i["aguardando_de"]
        if int(i.get("degradation_count") or 0):
            etapa["degradation_count"] = int(i["degradation_count"])
        etapas.append(etapa)

    return {
        "id": snap.id,
        "titulo": d.get("titulo"),
        "descricao": d.get("descricao") or "",
        "notas": d.get("notas") or "",
        "status": d.get("status"),
        "area_tematica": d.get("area_tematica"),
        "projeto": d.get("projeto"),
        "data_limite": d.get("data_limite"),
        "data_inicio": d.get("data_inicio"),
        "prazo_final": d.get("prazo_final"),
        "horario_inicio": d.get("horario_inicio"),
        "horario_fim": d.get("horario_fim"),
        "tags": d.get("tags") or [],
        "execution_lane": subtarefas.derivar_lane(plano, d.get("execution_lane")),
        "degradation_count": subtarefas.degradacao_da_acao(plano, d.get("degradation_count")),
        "estrategia_objetivo_id": d.get("estrategia_objetivo_id"),
        "plano_acao": etapas,
        "etapas_feitas": feitas,
        "etapas_totais": totais,
        "anexos": [
            {"nome": x.get("nome"), "link": x.get("valor") or x.get("link"),
             "drive_file_id": x.get("drive_file_id")}
            for x in (d.get("pool_dados") or [])
            if isinstance(x, dict) and x.get("tipo") == "arquivo"
        ],
        "diario": [{"data": str(e.get("data")), "nota": e.get("nota")}
                   for e in acomp[-limite_diario:]] if limite_diario else [],
        "diario_total": len(acomp),
        "observacao": ("Campos completos, sem truncamento. O diário traz as "
                       f"{min(limite_diario, len(acomp))} entradas mais recentes de "
                       f"{len(acomp)}; use limite_diario para ver mais."),
    }


def _registrar_saude(ctx: ToolContext, args: dict):
    from tools.registrar_saude import registrar

    return registrar(ctx, args)


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

_HANDLERS: dict = {
    # Delegadas a telegram_extended
    **{nome: _via_telegram(nome) for nome in _TELEGRAM_TOOLS},
    "registrar_item_financeiro_v2": _registrar_item_financeiro_v2,
    "agendar_lembrete_acao": _agendar_lembrete_acao,

    # Delegadas a modulos dedicados
    "consultar_lista_compras": _consultar_lista_compras,
    "consultar_elevacoes_sugeridas": _consultar_elevacoes_sugeridas,
    "decidir_elevacao": _decidir_elevacao,
    "consultar_historico_acoes": _consultar_historico_acoes,
    "buscar_arquivos_acervo": _buscar_arquivos_acervo,
    "buscar_contato": _buscar_contato,
    "calculadora": _calculadora,
    "consultar_job": _consultar_job,
    "consultar_agenda": _consultar_agenda,
    "encontrar_slot_livre": _encontrar_slot_livre,
    "consultar_saude": _consultar_saude,
    "registrar_saude": _registrar_saude,
    "consultar_dados_cadastrais": _consultar_dados_cadastrais,
    "buscar_e_analisar_email": _buscar_e_analisar_email,
    "schedule_whatsapp_message": _schedule_whatsapp_message,
    "buscar_conversas_whatsapp": _buscar_conversas_whatsapp,
    "salvar_memoria_global": _salvar_memoria_global,
    "criar_objetivo_estrategico": _strategy("criar_objetivo_estrategico"),
    "editar_objetivo_estrategico": _strategy("editar_objetivo_estrategico"),
    "gerenciar_item_estrategico": _strategy("gerenciar_item_estrategico"),
    "excluir_objetivo_estrategico": _strategy("excluir_objetivo_estrategico"),

    # Extraidas das closures
    "pesquisar_internet": pesquisar_internet,
    "ler_pagina_web": ler_pagina_web,
    "registrar_correcao_procedimento": registrar_correcao_procedimento,
    "registrar_no_diario": registrar_no_diario,
    "preparar_vinculo_contatos": preparar_vinculo_contatos,
    "preparar_atualizacao_contato": preparar_atualizacao_contato,
    "registrar_interacao_contato": registrar_interacao_contato,
    "criar_acao_no_sistema": criar_acao_no_sistema,
    "preparar_edicao_em_lote": preparar_edicao_em_lote,
    "preparar_reagendamento_em_lote": preparar_reagendamento_em_lote,
    "preparar_remocao_horarios_em_lote": preparar_remocao_horarios_em_lote,
    "gerar_imagem": gerar_imagem,
    "consultar_processo_sipac": consultar_processo_sipac,
    "acompanhar_processo_sipac": acompanhar_processo_sipac,

    # Aplicacao das propostas preparar_*
    "confirmar_edicao_acao": _via_callable("confirmarEdicaoAcao", _map_confirmar_edicao_acao),
    "confirmar_edicao_em_lote": _via_callable("confirmarEdicaoEmLote", _map_confirmar_edicao_em_lote),
    "confirmar_reagendamento_em_lote": _via_callable(
        "confirmarReagendamentoEmLote", _map_confirmar_reagendamento
    ),

    # Escrita direta, sem o passo de preparacao
    "editar_acao": editar_acao,
    "editar_acoes_em_lote": editar_acoes_em_lote,
    "reagendar_acoes_em_lote": reagendar_acoes_em_lote,
    "obter_estado_atual": obter_estado_atual,
    "obter_acao": obter_acao,
    "listar_conversas_whatsapp": _whatsapp("listar_conversas"),
    "ler_mensagens_whatsapp": _whatsapp("ler_mensagens"),
    "consolidar_whatsapp": _whatsapp("consolidar"),
    "ler_consolidacao_whatsapp": _whatsapp("ler_consolidacao"),
    "consultar_envio_whatsapp": _whatsapp("consultar_envio"),
    "anexar_arquivo": anexar_arquivo,
    "preparar_upload": preparar_upload,
    "remover_anexo": remover_anexo,
    "consultar_fatura_cartao": consultar_fatura_cartao,
    "consultar_compromissos_futuros": consultar_compromissos_futuros,
}


def list_tools() -> list[str]:
    """Nomes de todas as tools executaveis fora do copiloto web."""
    return sorted(_HANDLERS)


def has_tool(name: str) -> bool:
    return name in _HANDLERS


def execute(name: str, arguments: dict | None, ctx: ToolContext):
    """Executa uma tool pelo nome. Levanta ToolNotAvailable se nao registrada."""
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolNotAvailable(name)
    return handler(ctx, arguments or {})
