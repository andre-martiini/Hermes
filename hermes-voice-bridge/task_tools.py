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
import re
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
    {
        "name": "reagendar_acao",
        "description": (
            "Move a data de execucao (data_limite) de uma tarefa para uma nova data. "
            "E A UNICA ferramenta capaz de adiar, reagendar ou realocar uma tarefa — "
            "use SEMPRE que o usuario pedir isso. Nao existe outra forma de mudar a "
            "data; NUNCA diga que uma tarefa foi adiada/reagendada sem chamar esta "
            "ferramenta e receber status 'ok' de volta."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "nova_data": {
                    "type": "STRING",
                    "description": "Nova data de execucao no formato YYYY-MM-DD.",
                },
                "justificativa": {
                    "type": "STRING",
                    "description": "Motivo da mudanca de data (sera gravado no diario da tarefa).",
                },
                "task_id": {
                    "type": "STRING",
                    "description": "ID da tarefa. Opcional se a sessao ja esta dentro de uma acao.",
                },
            },
            "required": ["nova_data", "justificativa"],
        },
    },
    {
        "name": "mudar_status_acao",
        "description": (
            "Muda o status de uma tarefa. E A UNICA ferramenta capaz de colocar "
            "uma tarefa em standby/pausada, reabrir ('em andamento'), concluir ou "
            "excluir. NUNCA diga que uma tarefa foi pausada, concluida, excluida "
            "ou reaberta sem chamar esta ferramenta e receber status 'ok' de volta."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "novo_status": {
                    "type": "STRING",
                    "description": (
                        "Um de: 'em andamento' (aberta/reaberta), 'stand-by' "
                        "(pausada), 'concluído', 'excluído'."
                    ),
                },
                "justificativa": {
                    "type": "STRING",
                    "description": "Motivo da mudanca de status (sera gravado no diario da tarefa).",
                },
                "task_id": {
                    "type": "STRING",
                    "description": "ID da tarefa. Opcional se a sessao ja esta dentro de uma acao.",
                },
            },
            "required": ["novo_status", "justificativa"],
        },
    },
    {
        "name": "criar_lembrete_acao",
        "description": (
            "Agenda um lembrete (notificacao futura) para uma tarefa em uma data e "
            "horario especificos. E A UNICA ferramenta capaz de criar lembretes. "
            "NUNCA diga que um lembrete foi criado sem chamar esta ferramenta e "
            "receber status 'ok' de volta."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "data": {
                    "type": "STRING",
                    "description": "Data do lembrete no formato YYYY-MM-DD.",
                },
                "horario": {
                    "type": "STRING",
                    "description": "Horario do lembrete no formato HH:MM (24h).",
                },
                "texto": {
                    "type": "STRING",
                    "description": "Texto opcional que aparecera no lembrete.",
                },
                "task_id": {
                    "type": "STRING",
                    "description": "ID da tarefa. Opcional se a sessao ja esta dentro de uma acao.",
                },
            },
            "required": ["data", "horario"],
        },
    },
    {
        "name": "criar_nova_acao",
        "description": (
            "Cria uma NOVA acao/tarefa no sistema Hermes no Firestore. "
            "Use SEMPRE que o usuario pedir para criar, adicionar ou registrar uma nova acao, tarefa ou item de trabalho. "
            "NUNCA diga que uma acao foi criada sem chamar esta ferramenta e receber status 'ok' de volta."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "titulo": {
                    "type": "STRING",
                    "description": "Titulo claro e conciso da nova acao.",
                },
                "descricao": {
                    "type": "STRING",
                    "description": "Descricao detalhada do objetivo ou contexto da acao (opcional).",
                },
                "data_limite": {
                    "type": "STRING",
                    "description": "Data limite no formato YYYY-MM-DD (ex: 2026-08-10). Se o usuario disser um dia da semana, converta para YYYY-MM-DD usando a data atual.",
                },
                "prioridade": {
                    "type": "STRING",
                    "description": "Prioridade da acao: 'alta', 'media' ou 'baixa'. Padrao e 'media'.",
                },
                "responsavel": {
                    "type": "STRING",
                    "description": "Nome da pessoa responsavel pela acao (opcional).",
                },
                "passos_plano_acao": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Lista de textos dos passos ou sub-tarefas para o plano de acao (opcional).",
                },
            },
            "required": ["titulo"],
        },
    },
]

TASK_TOOL_NAMES = {decl["name"] for decl in TASK_TOOL_DECLARATIONS}


def call_task_tool(name: str, args: dict, session_task_id: str | None) -> dict:
    args = dict(args or {})
    if name == "criar_nova_acao":
        return _criar_nova_acao(
            titulo=str(args.get("titulo") or ""),
            descricao=str(args.get("descricao") or ""),
            data_limite=str(args.get("data_limite")) if args.get("data_limite") else None,
            prioridade=str(args.get("prioridade") or "média"),
            responsavel=str(args.get("responsavel")) if args.get("responsavel") else None,
            passos_plano_acao=args.get("passos_plano_acao") if isinstance(args.get("passos_plano_acao"), list) else None,
        )

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
    if name == "reagendar_acao":
        return _reagendar_acao(task_id, str(args.get("nova_data") or ""), str(args.get("justificativa") or ""))
    if name == "mudar_status_acao":
        return _mudar_status_acao(task_id, str(args.get("novo_status") or ""), str(args.get("justificativa") or ""))
    if name == "criar_lembrete_acao":
        return _criar_lembrete_acao(
            task_id,
            str(args.get("data") or ""),
            str(args.get("horario") or ""),
            str(args.get("texto") or ""),
        )
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


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _reagendar_acao(task_id: str, nova_data: str, justificativa: str) -> dict:
    nova_data = nova_data.strip()
    if not _DATE_RE.match(nova_data):
        return {"erro": "Data invalida — use o formato YYYY-MM-DD."}
    if not justificativa.strip():
        return {"erro": "Justificativa vazia — descreva o motivo da mudanca de data."}

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if nova_data < today_str:
        return {"erro": f"A data de execucao nao pode ser no passado ({nova_data})."}

    task_ref = get_db().collection("tarefas").document(task_id)
    snap = task_ref.get()
    if not snap.exists:
        return {"erro": f"Tarefa '{task_id}' nao encontrada."}

    data = snap.to_dict() or {}
    if data.get("status") in ("concluído", "excluído"):
        return {"erro": "Esta tarefa ja foi concluida ou excluida e nao pode ser reagendada."}

    data_anterior = data.get("data_limite")
    now_iso = datetime.now(timezone.utc).isoformat()
    diary_entry = {
        "data": now_iso,
        "nota": f"[Copiloto de Voz] Data de execucao alterada de {data_anterior or 'sem data'} para {nova_data}: {justificativa.strip()}",
    }
    task_ref.update({
        "data_limite": nova_data,
        "data_atualizacao": now_iso,
        "acompanhamento": gc_firestore.ArrayUnion([diary_entry]),
    })
    return {"status": "ok", "task_id": task_id, "data_anterior": data_anterior, "nova_data": nova_data}


_STATUS_VALIDOS = {"em andamento", "stand-by", "concluído", "excluído"}


def _normalizar_status_acao(valor: str) -> str | None:
    raw = str(valor or "").strip().lower()
    try:
        import unicodedata
        raw = "".join(c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    raw = raw.replace("_", " ").replace("-", " ")
    raw = " ".join(raw.split())
    if raw in ("concluido", "concluida", "concluir", "finalizado", "finalizada", "completed", "done"):
        return "concluído"
    if raw in ("stand by", "standby", "pausado", "pausada", "pausar"):
        return "stand-by"
    if raw in ("em andamento", "andamento", "pendente", "aberto", "aberta", "reabrir"):
        return "em andamento"
    if raw in ("excluido", "excluir", "excluida", "cancelado", "cancelar", "cancelada", "deletar", "deletado", "apagar", "remover"):
        return "excluído"
    return None


def _mudar_status_acao(task_id: str, novo_status: str, justificativa: str) -> dict:
    normalizado = _normalizar_status_acao(novo_status)
    if not normalizado:
        return {"erro": f"Status invalido: '{novo_status}'. Use um de: {', '.join(sorted(_STATUS_VALIDOS))}."}
    if not justificativa.strip():
        return {"erro": "Justificativa vazia — descreva o motivo da mudanca de status."}

    task_ref = get_db().collection("tarefas").document(task_id)
    snap = task_ref.get()
    if not snap.exists:
        return {"erro": f"Tarefa '{task_id}' nao encontrada."}

    data = snap.to_dict() or {}
    status_anterior = data.get("status")

    now_iso = datetime.now(timezone.utc).isoformat()
    diary_entry = {
        "data": now_iso,
        "nota": f"[Copiloto de Voz] Status alterado de '{status_anterior}' para '{normalizado}': {justificativa.strip()}",
    }
    task_ref.update({
        "status": normalizado,
        "data_atualizacao": now_iso,
        "acompanhamento": gc_firestore.ArrayUnion([diary_entry]),
    })
    return {"status": "ok", "task_id": task_id, "status_anterior": status_anterior, "novo_status": normalizado}


_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _criar_lembrete_acao(task_id: str, data_lembrete: str, horario: str, texto: str) -> dict:
    data_lembrete = data_lembrete.strip()
    horario = horario.strip()[:5]
    texto = texto.strip()[:500]

    if not _DATE_RE.match(data_lembrete):
        return {"erro": "Data invalida — use o formato YYYY-MM-DD."}
    if not _TIME_RE.match(horario):
        return {"erro": "Horario invalido — use o formato HH:MM."}
    try:
        datetime.strptime(f"{data_lembrete} {horario}", "%Y-%m-%d %H:%M")
    except ValueError:
        return {"erro": "Data ou horario inexistente."}

    task_ref = get_db().collection("tarefas").document(task_id)
    snap = task_ref.get()
    if not snap.exists:
        return {"erro": f"Tarefa '{task_id}' nao encontrada."}

    data = snap.to_dict() or {}
    titulo = data.get("titulo", task_id)
    reminder_at = f"{data_lembrete}T{horario}:00"

    reminders_raw = data.get("reminders") if isinstance(data.get("reminders"), list) else []
    normalized = []
    for idx, reminder in enumerate(reminders_raw):
        if not isinstance(reminder, dict) or not reminder.get("reminder_at"):
            continue
        normalized.append({
            "id": str(reminder.get("id") or f"legacy-{idx}"),
            "reminder_at": str(reminder.get("reminder_at")),
            "reminder_sent": bool(reminder.get("reminder_sent")),
            "created_at": str(reminder.get("created_at") or reminder.get("reminder_at")),
            "message": str(reminder.get("message") or "").strip(),
        })

    now_iso = datetime.now(timezone.utc).isoformat()
    new_reminder = {
        "id": str(uuid.uuid4())[:12],
        "reminder_at": reminder_at,
        "reminder_sent": False,
        "created_at": now_iso,
        "created_by": "voz",
    }
    if texto:
        new_reminder["message"] = texto

    ordered = sorted([*normalized, new_reminder], key=lambda item: item.get("reminder_at") or "")
    next_pending = next((item for item in ordered if not item.get("reminder_sent")), None)

    diary_entry = {
        "data": now_iso,
        "nota": f"[Copiloto de Voz] Lembrete agendado para {data_lembrete} {horario}.",
    }
    task_ref.update({
        "reminders": ordered,
        "reminder_at": next_pending.get("reminder_at") if next_pending else None,
        "reminder_sent": bool(next_pending.get("reminder_sent")) if next_pending else True,
        "data_atualizacao": now_iso,
        "acompanhamento": gc_firestore.ArrayUnion([diary_entry]),
    })
    return {"status": "ok", "task_id": task_id, "titulo": titulo, "reminder_at": reminder_at}


def _criar_nova_acao(
    titulo: str,
    descricao: str = "",
    data_limite: str | None = None,
    prioridade: str = "média",
    responsavel: str | None = None,
    passos_plano_acao: list[str] | None = None,
) -> dict:
    if not titulo or not titulo.strip():
        return {"status": "erro", "mensagem": "O título da ação é obrigatório."}

    db = get_db()
    task_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    plano_acao = []
    if passos_plano_acao:
        for idx, item_text in enumerate(passos_plano_acao, start=1):
            if isinstance(item_text, str) and item_text.strip():
                plano_acao.append({
                    "id": f"p_{idx}_{str(uuid.uuid4())[:8]}",
                    "item": item_text.strip(),
                    "concluido": False,
                })

    diary_entry = {
        "data": now_iso,
        "nota": "Ação criada via Copiloto de Voz Hermes.",
        "autor": "Copiloto de Voz",
    }

    doc_payload = {
        "id": task_id,
        "titulo": titulo.strip(),
        "descricao": (descricao or "").strip(),
        "status": "não iniciado",
        "prioridade": prioridade if prioridade in ("alta", "média", "baixa") else "média",
        "data_criacao": now_iso,
        "data_atualizacao": now_iso,
        "criado_por": "voz",
        "reminder_sent": False,
        "reminders": [],
        "pool_dados": [],
        "plano_acao": plano_acao,
        "acompanhamento": [diary_entry],
    }

    if data_limite and re.match(r"^\d{4}-\d{2}-\d{2}$", data_limite.strip()):
        doc_payload["data_limite"] = data_limite.strip()

    if responsavel and responsavel.strip():
        doc_payload["responsavel"] = responsavel.strip()

    try:
        db.collection("tarefas").document(task_id).set(doc_payload)
        return {
            "status": "ok",
            "mensagem": f"Ação '{titulo.strip()}' criada com sucesso no Hermes!",
            "task_id": task_id,
            "titulo": titulo.strip(),
            "data_limite": doc_payload.get("data_limite"),
        }
    except Exception as exc:
        return {"status": "erro", "mensagem": f"Falha ao criar ação no Firestore: {exc}"}


def _clip(value, max_chars: int) -> str:
    text = str(value or "").strip()
    return text[:max_chars]
