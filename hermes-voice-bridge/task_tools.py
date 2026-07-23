"""Tools de acao (tarefa) para a sessao de voz — leitura de detalhe, diario de
bordo e edicao de plano de acao.

Espelham a semantica das closures do copiloto textual (functions/main.py::
registrar_no_diario e editar_plano_acao): mesmo formato de entrada de diario
({data, nota} em ArrayUnion no campo 'acompanhamento') e mesmo fuzzy-match de
plano que preserva o status 'completed' dos passos existentes. Quando a sessao
de voz e aberta dentro de uma acao, o task_id da sessao e usado como padrao —
o usuario pode falar "anota no diario" sem dizer qual tarefa.
"""

from __future__ import annotations

import difflib
import uuid
from datetime import datetime, timezone

from google.cloud import firestore as gc_firestore

from database import get_db

TASK_TOOL_DECLARATIONS = [
    {
        "name": "consultar_acao_atual",
        "description": (
            "Retorna o detalhe completo de uma acao/tarefa do Hermes: titulo, status, "
            "datas, descricao, notas, plano de acao com passos concluidos/pendentes e "
            "ultimas entradas do diario de bordo. Se a sessao estiver dentro de uma "
            "acao, pode ser chamada sem task_id."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task_id": {
                    "type": "STRING",
                    "description": "ID da tarefa. Opcional se a sessao ja esta dentro de uma acao.",
                }
            },
        },
    },
    {
        "name": "registrar_no_diario",
        "description": (
            "Registra uma entrada no diario de bordo de uma acao/tarefa do Hermes. "
            "Use sempre que o usuario pedir para anotar, registrar ou logar algo no diario."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "nota": {
                    "type": "STRING",
                    "description": "Texto da entrada a registrar no diario.",
                },
                "task_id": {
                    "type": "STRING",
                    "description": "ID da tarefa alvo. Opcional se a sessao ja esta dentro de uma acao.",
                },
            },
            "required": ["nota"],
        },
    },
    {
        "name": "editar_plano_acao",
        "description": (
            "Substitui/atualiza o plano de acao de uma tarefa. Envie a lista completa "
            "dos passos desejados; passos com texto igual ou muito parecido aos atuais "
            "preservam o status de concluido. Use APENAS depois de descrever a mudanca "
            "em voz alta e o usuario confirmar."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "novo_plano": {
                    "type": "ARRAY",
                    "description": "Lista completa dos passos do plano apos a edicao.",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "text": {"type": "STRING", "description": "Texto do passo."},
                            "id": {"type": "STRING", "description": "ID do passo existente, se conhecido."},
                        },
                        "required": ["text"],
                    },
                },
                "justificativa": {
                    "type": "STRING",
                    "description": "Motivo da alteracao (sera gravado no diario da tarefa).",
                },
                "task_id": {
                    "type": "STRING",
                    "description": "ID da tarefa. Opcional se a sessao ja esta dentro de uma acao.",
                },
            },
            "required": ["novo_plano", "justificativa"],
        },
    },
    {
        "name": "concluir_passo_plano",
        "description": (
            "Marca um passo do plano de acao como concluido (ou reabre, com concluido=false). "
            "Identifica o passo pelo texto aproximado falado pelo usuario."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "texto_passo": {
                    "type": "STRING",
                    "description": "Texto (aproximado) do passo a marcar.",
                },
                "concluido": {
                    "type": "BOOLEAN",
                    "description": "true para concluir (padrao), false para reabrir.",
                },
                "task_id": {
                    "type": "STRING",
                    "description": "ID da tarefa. Opcional se a sessao ja esta dentro de uma acao.",
                },
            },
            "required": ["texto_passo"],
        },
    },
]

TASK_TOOL_NAMES = {decl["name"] for decl in TASK_TOOL_DECLARATIONS}


def call_task_tool(name: str, args: dict, session_task_id: str | None) -> dict:
    args = dict(args or {})
    task_id = str(args.get("task_id") or session_task_id or "").strip()
    if not task_id:
        return {
            "erro": (
                "Nenhuma acao no contexto. Pergunte ao usuario qual acao usar e "
                "busque o ID com as ferramentas de busca de tarefas."
            )
        }

    if name == "consultar_acao_atual":
        return _consultar_acao(task_id)
    if name == "registrar_no_diario":
        return _registrar_no_diario(task_id, str(args.get("nota") or ""))
    if name == "editar_plano_acao":
        return _editar_plano_acao(task_id, args.get("novo_plano") or [], str(args.get("justificativa") or ""))
    if name == "concluir_passo_plano":
        concluido = args.get("concluido")
        return _concluir_passo(task_id, str(args.get("texto_passo") or ""), True if concluido is None else bool(concluido))
    return {"erro": f"Tool de tarefa desconhecida: {name}"}


def build_task_context(task_id: str) -> str:
    """Bloco de contexto da acao para a system instruction da sessao de voz."""
    detail = _consultar_acao(task_id)
    if detail.get("erro"):
        return ""

    tarefa = detail["tarefa"]
    lines = [
        "## ACAO EM FOCO (a sessao de voz foi aberta dentro desta acao)",
        f"- task_id: {task_id}",
        f"- titulo: {tarefa.get('titulo')}",
        f"- status: {tarefa.get('status')} | data_limite: {tarefa.get('data_limite')} | projeto: {tarefa.get('projeto')} | area: {tarefa.get('area_tematica')}",
    ]
    if tarefa.get("descricao"):
        lines.append(f"- descricao: {tarefa['descricao']}")
    if tarefa.get("notas"):
        lines.append(f"- notas: {tarefa['notas']}")

    plano = tarefa.get("plano_acao") or []
    if plano:
        lines.append("- plano de acao:")
        for passo in plano:
            marcador = "[x]" if passo.get("completed") else "[ ]"
            lines.append(f"  {marcador} ({passo.get('id')}) {passo.get('text')}")

    diario = tarefa.get("diario_recente") or []
    if diario:
        lines.append("- ultimas entradas do diario:")
        for entry in diario:
            lines.append(f"  - {entry.get('data', '')[:10]}: {entry.get('nota')}")

    lines.append(
        "Perguntas do usuario sobre 'essa acao/tarefa' se referem a ela. Para "
        "anotar no diario ou mexer no plano desta acao, use as ferramentas sem "
        "precisar de task_id."
    )
    return "\n".join(lines)


def _consultar_acao(task_id: str) -> dict:
    snap = get_db().collection("tarefas").document(task_id).get()
    if not snap.exists:
        return {"erro": f"Tarefa '{task_id}' nao encontrada."}
    data = snap.to_dict() or {}

    acompanhamento = data.get("acompanhamento") or []
    diario_recente = sorted(
        [e for e in acompanhamento if isinstance(e, dict)],
        key=lambda e: str(e.get("data") or ""),
    )[-5:]

    return {
        "tarefa": {
            "id": task_id,
            "titulo": data.get("titulo"),
            "status": data.get("status"),
            "data_inicio": data.get("data_inicio"),
            "data_limite": data.get("data_limite"),
            "projeto": data.get("projeto"),
            "area_tematica": data.get("area_tematica"),
            "tipo_acao": data.get("tipo_acao"),
            "descricao": _clip(data.get("descricao"), 1200),
            "notas": _clip(data.get("notas"), 1200),
            "plano_acao": [
                {"id": p.get("id"), "text": p.get("text") or p.get("texto"), "completed": bool(p.get("completed"))}
                for p in (data.get("plano_acao") or [])
                if isinstance(p, dict)
            ],
            "diario_recente": [
                {"data": str(e.get("data") or ""), "nota": _clip(e.get("nota"), 400)}
                for e in diario_recente
            ],
        }
    }


def _registrar_no_diario(task_id: str, nota: str) -> dict:
    nota = nota.strip()
    if not nota:
        return {"erro": "Nota vazia."}

    task_ref = get_db().collection("tarefas").document(task_id)
    snap = task_ref.get()
    if not snap.exists:
        return {"erro": f"Tarefa '{task_id}' nao encontrada."}

    entry = {"data": datetime.now(timezone.utc).isoformat(), "nota": nota}
    task_ref.update({"acompanhamento": gc_firestore.ArrayUnion([entry])})
    titulo = (snap.to_dict() or {}).get("titulo", task_id)
    return {"status": "ok", "task_id": task_id, "titulo": titulo, "nota_registrada": nota}


def _editar_plano_acao(task_id: str, novo_plano: list, justificativa: str) -> dict:
    if not justificativa.strip():
        return {"erro": "Justificativa vazia — descreva o motivo da alteracao."}

    task_ref = get_db().collection("tarefas").document(task_id)
    snap = task_ref.get()
    if not snap.exists:
        return {"erro": f"Tarefa '{task_id}' nao encontrada."}

    data = snap.to_dict() or {}
    plano_atual = [p for p in (data.get("plano_acao") or []) if isinstance(p, dict)]
    plano_por_id = {p["id"]: p for p in plano_atual if p.get("id")}
    textos_originais = [str(p.get("text") or p.get("texto") or "") for p in plano_atual]

    plano_final = []
    for item in novo_plano:
        if not isinstance(item, dict):
            continue
        texto_novo = str(item.get("text") or item.get("texto") or "").strip()
        if not texto_novo:
            continue

        item_id = str(item.get("id") or "")
        if item_id and item_id in plano_por_id:
            original = plano_por_id[item_id]
            plano_final.append({"id": item_id, "text": texto_novo, "completed": original.get("completed", False)})
            continue

        matches = difflib.get_close_matches(texto_novo, textos_originais, n=1, cutoff=0.85)
        if matches:
            original = plano_atual[textos_originais.index(matches[0])]
            plano_final.append({
                "id": original.get("id", str(uuid.uuid4())[:8]),
                "text": texto_novo,
                "completed": original.get("completed", False),
            })
            continue

        plano_final.append({"id": str(uuid.uuid4())[:8], "text": texto_novo, "completed": False})

    if not plano_final:
        return {"erro": "Novo plano vazio — nada foi alterado."}

    now_iso = datetime.now(timezone.utc).isoformat()
    diary_entry = {"data": now_iso, "nota": f"[Copiloto de Voz] Plano de acao atualizado: {justificativa.strip()}"}
    task_ref.update({
        "plano_acao": plano_final,
        "data_atualizacao": now_iso,
        "acompanhamento": gc_firestore.ArrayUnion([diary_entry]),
    })
    return {
        "status": "ok",
        "task_id": task_id,
        "total_passos": len(plano_final),
        "plano_atualizado": plano_final,
    }


def _concluir_passo(task_id: str, texto_passo: str, concluido: bool) -> dict:
    texto_passo = texto_passo.strip()
    if not texto_passo:
        return {"erro": "Texto do passo vazio."}

    task_ref = get_db().collection("tarefas").document(task_id)
    snap = task_ref.get()
    if not snap.exists:
        return {"erro": f"Tarefa '{task_id}' nao encontrada."}

    data = snap.to_dict() or {}
    plano = [p for p in (data.get("plano_acao") or []) if isinstance(p, dict)]
    textos = [str(p.get("text") or p.get("texto") or "") for p in plano]

    matches = difflib.get_close_matches(texto_passo, textos, n=1, cutoff=0.5)
    if not matches:
        return {
            "erro": "Nao encontrei um passo parecido com esse texto.",
            "passos_disponiveis": textos,
        }

    idx = textos.index(matches[0])
    plano[idx]["completed"] = concluido

    now_iso = datetime.now(timezone.utc).isoformat()
    verbo = "concluido" if concluido else "reaberto"
    diary_entry = {"data": now_iso, "nota": f"[Copiloto de Voz] Passo {verbo}: {matches[0]}"}
    task_ref.update({
        "plano_acao": plano,
        "data_atualizacao": now_iso,
        "acompanhamento": gc_firestore.ArrayUnion([diary_entry]),
    })
    return {"status": "ok", "passo": matches[0], "concluido": concluido}


def _clip(value, max_chars: int) -> str:
    text = str(value or "").strip()
    return text[:max_chars]
