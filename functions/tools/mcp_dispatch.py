"""Executores de tools para o servidor MCP (functions/mcp_server.py).

O copiloto web (askCopilotoHermes, em functions/main.py) mantem as ~42 tools
do catalogo como closures presas ao escopo da requisicao (db, session_id,
user_uid, gemini_key). Isso impede reuso direto por um cliente externo como
o MCP. Este modulo reimplementa, fora de qualquer closure, apenas as tools
que ja estao marcadas como MCP_ENABLED em tools/registry.py — hoje as que
sao seguras (somente leitura ou puras) e nao dependem de estado de sessao.

Para a busca de tarefas e de acervo, a logica abaixo espelha o comportamento
das closures equivalentes em main.py (consultar_historico_acoes / buscar_
arquivos_acervo). E duplicacao deliberada, nao acidental: main.py e grande
e sensivel demais para refatorar as pressa so para eliminar essas ~80 linhas.
Ao migrar mais tools para ca, avaliar convergir main.py para importar daqui.

Adicionar uma tool nova aqui SEMPRE em conjunto com:
  1. entrada em tools/registry.py::_CATALOG (se ainda nao existir)
  2. schema em tools/schemas/<nome>.json (se ainda nao existir)
  3. nome adicionado a tools/registry.py::_MCP_ENABLED (e _VOICE_ENABLED, se aplicavel)
"""

from __future__ import annotations

_STOPWORDS_QUERY = {
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "uma",
    "os", "as", "no", "na", "com", "por", "para", "dos", "das",
    "nos", "nas", "ao", "se", "ou",
}


class ToolNotAvailable(Exception):
    """Tool existe no catalogo mas ainda nao tem executor ligado ao MCP."""


def execute_tool(name: str, arguments: dict) -> dict:
    """Executa uma tool MCP-enabled pelo nome. Levanta ToolNotAvailable se nao ligada."""
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolNotAvailable(name)
    return handler(arguments or {})


def _consultar_historico_acoes(args: dict) -> dict:
    from tools.busca_grafo import buscar_tarefas

    query = str(args.get("query") or "")
    area_tematica = args.get("area_tematica")
    status = args.get("status")
    data_limite_inicio = args.get("data_limite_inicio")
    data_limite_fim = args.get("data_limite_fim")
    limite = int(args.get("ultimas_n_acoes") or 20)

    q_terms = [w for w in query.lower().split() if w not in _STOPWORDS_QUERY and len(w) > 2]
    initial_mode = "all" if len(q_terms) >= 2 else "any"

    res = buscar_tarefas(
        query,
        area_tematica=area_tematica,
        match_mode=initial_mode,
        data_limite_inicio=data_limite_inicio,
        data_limite_fim=data_limite_fim,
        status=status,
        limite=limite,
    )
    if initial_mode == "all" and not res.get("resultados"):
        res = buscar_tarefas(
            query,
            area_tematica=area_tematica,
            match_mode="any",
            data_limite_inicio=data_limite_inicio,
            data_limite_fim=data_limite_fim,
            status=status,
            limite=limite,
        )

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


def _buscar_arquivos_acervo(args: dict) -> dict:
    from tools.busca_acervo import buscar_acervo

    query = str(args.get("query") or "")
    res = buscar_acervo(query)
    if res.get("erro"):
        return {"erro": res["erro"], "resultados": []}

    resultados = res.get("resultados", [])
    return {"total_retornado": len(resultados), "resultados": resultados}


def _buscar_contato(args: dict) -> dict:
    from firebase_admin import firestore

    termo = str(args.get("termo") or "").strip().lower()
    limite = max(1, min(int(args.get("limite") or 5), 20))
    if not termo:
        return {"erro": "Termo de busca vazio.", "candidatos": []}

    db = firestore.client()
    candidatos = []
    for doc in db.collection("perfil_pessoas").limit(500).stream():
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


def _calculadora(args: dict) -> dict:
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


_HANDLERS = {
    "consultar_historico_acoes": _consultar_historico_acoes,
    "buscar_arquivos_acervo": _buscar_arquivos_acervo,
    "buscar_contato": _buscar_contato,
    "calculadora": _calculadora,
}
