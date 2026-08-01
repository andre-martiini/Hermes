import json
import os
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.cloud.firestore_v1 import FieldFilter

from database import get_db

LOCAL_TZ = ZoneInfo(os.getenv("HERMES_TIMEZONE", "America/Sao_Paulo"))
OPEN_TASK_STATUSES = ("em andamento", "stand-by")

GEMINI_TOOL_DECLARATIONS = [
    {
        "function_declarations": [
            {
                "name": "buscar_tarefas_pendentes_hoje",
                "description": (
                    "Busca no Firestore as tarefas do Hermes com data_limite igual a hoje "
                    "e status em andamento ou stand-by."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "limite": {
                            "type": "INTEGER",
                            "description": "Numero maximo de tarefas retornadas.",
                        }
                    },
                },
            },
            {
                "name": "buscar_tarefas_amanha",
                "description": (
                    "Busca no Firestore as tarefas abertas do Hermes com data_limite igual a amanha."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "limite": {
                            "type": "INTEGER",
                            "description": "Numero maximo de tarefas retornadas.",
                        }
                    },
                },
            },
            {
                "name": "buscar_tarefas_atrasadas",
                "description": "Busca tarefas abertas do Hermes com data_limite anterior a hoje.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "limite": {
                            "type": "INTEGER",
                            "description": "Numero maximo de tarefas retornadas.",
                        }
                    },
                },
            },
            {
                "name": "buscar_tarefas_por_periodo",
                "description": "Busca tarefas abertas do Hermes entre duas datas no formato YYYY-MM-DD.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "data_inicio": {
                            "type": "STRING",
                            "description": "Data inicial no formato YYYY-MM-DD.",
                        },
                        "data_fim": {
                            "type": "STRING",
                            "description": "Data final no formato YYYY-MM-DD.",
                        },
                        "limite": {
                            "type": "INTEGER",
                            "description": "Numero maximo de tarefas retornadas.",
                        },
                    },
                    "required": ["data_inicio", "data_fim"],
                },
            },
            {
                "name": "buscar_tarefas_por_termo",
                "description": (
                    "Busca tarefas no Hermes por termo no titulo, descricao, notas, projeto, area ou tags."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "termo": {
                            "type": "STRING",
                            "description": "Termo ou frase de busca.",
                        },
                        "status": {
                            "type": "STRING",
                            "description": "Filtro opcional de status.",
                        },
                        "limite": {
                            "type": "INTEGER",
                            "description": "Numero maximo de tarefas retornadas.",
                        },
                    },
                    "required": ["termo"],
                },
            },
            {
                "name": "resumo_projetos_ativos",
                "description": (
                    "Resume projetos cadastrados no Hermes e conta tarefas abertas ligadas a cada projeto."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "limite": {
                            "type": "INTEGER",
                            "description": "Numero maximo de projetos retornados.",
                        }
                    },
                },
            },
            {
                "name": "buscar_memorias_relevantes",
                "description": (
                    "Busca memorias e fatos registrados no Hermes por termo textual simples."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "termo": {
                            "type": "STRING",
                            "description": "Termo ou frase para localizar memorias.",
                        },
                        "limite": {
                            "type": "INTEGER",
                            "description": "Numero maximo de memorias retornadas.",
                        },
                    },
                    "required": ["termo"],
                },
            },
        ]
    }
]


def buscar_tarefas_pendentes_hoje(limite: int = 25) -> dict:
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    return _buscar_tarefas_por_datas(today, today, limite=limite, label="hoje")


def buscar_tarefas_amanha(limite: int = 25) -> dict:
    tomorrow = (datetime.now(LOCAL_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
    return _buscar_tarefas_por_datas(tomorrow, tomorrow, limite=limite, label="amanha")


def buscar_tarefas_atrasadas(limite: int = 30) -> dict:
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    limit_value = _bounded_limit(limite, default=30, maximum=30)
    tasks = _load_task_candidates(max_docs=700)
    filtered = [
        task
        for task in tasks
        if _is_open_task(task)
        and _is_iso_date(str(task.get("data_limite") or ""))
        and str(task.get("data_limite")) < today
    ]
    filtered.sort(key=lambda item: str(item.get("data_limite") or "9999-99-99"))
    return {
        "data_referencia": today,
        "total_encontrado": len(filtered),
        "total_retornado": min(len(filtered), limit_value),
        "truncado": len(filtered) > limit_value,
        "tarefas": [_format_task(task["_id"], task) for task in filtered[:limit_value]],
    }


def buscar_tarefas_por_periodo(
    data_inicio: str,
    data_fim: str,
    limite: int = 15,
) -> dict:
    start = _parse_date_or_today(data_inicio)
    end = _parse_date_or_today(data_fim)
    if end < start:
        start, end = end, start
    return _buscar_tarefas_por_datas(
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
        limite=limite,
        label="periodo",
    )


def buscar_tarefas_por_termo(
    termo: str,
    status: str | None = None,
    limite: int = 10,
) -> dict:
    limit_value = _bounded_limit(limite, default=10, maximum=30)
    normalized_term = _normalize(termo)
    if not normalized_term:
        return {"erro": "Termo de busca vazio.", "tarefas": []}

    tasks = _load_task_candidates(max_docs=900)
    matches = []
    for task in tasks:
        if status and _normalize(task.get("status")) != _normalize(status):
            continue
        haystack = _normalize(
            " ".join(
                str(task.get(key) or "")
                for key in (
                    "titulo",
                    "descricao",
                    "notas",
                    "projeto",
                    "area_tematica",
                    "processo_sei",
                    "sistema",
                )
            )
            + " "
            + " ".join(str(tag) for tag in (task.get("tags") or []))
        )
        if all(term in haystack for term in normalized_term.split()):
            matches.append(task)

    matches.sort(key=lambda item: str(item.get("data_limite") or "9999-99-99"))
    return {
        "termo": termo,
        "total_retornado": min(len(matches), limit_value),
        "tarefas": [_format_task(task["_id"], task) for task in matches[:limit_value]],
    }


def _buscar_tarefas_por_datas(
    data_inicio: str,
    data_fim: str,
    *,
    limite: int,
    label: str,
) -> dict:
    limit_value = _bounded_limit(limite, default=10, maximum=25)

    tasks = _load_task_candidates(max_docs=700)
    filtered = [
        task
        for task in tasks
        if _is_open_task(task)
        and data_inicio <= str(task.get("data_limite") or "") <= data_fim
    ]
    filtered.sort(key=lambda item: (str(item.get("data_limite") or ""), str(item.get("titulo") or "")))

    return {
        "consulta": label,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        # total_encontrado e a contagem REAL no banco; total_retornado pode ser
        # menor por causa do limite. Ao informar quantas tarefas existem,
        # SEMPRE use total_encontrado.
        "total_encontrado": len(filtered),
        "total_retornado": min(len(filtered), limit_value),
        "truncado": len(filtered) > limit_value,
        "tarefas": [_format_task(task["_id"], task) for task in filtered[:limit_value]],
    }


def resumo_projetos_ativos(limite: int = 10) -> dict:
    limit_value = _bounded_limit(limite, default=10, maximum=25)
    db = get_db()

    project_docs = list(db.collection("projetos").limit(limit_value).stream())
    open_task_docs = (
        db.collection("tarefas")
        .where(filter=FieldFilter("status", "in", list(OPEN_TASK_STATUSES)))
        .limit(500)
        .stream()
    )
    open_tasks_by_project = Counter(
        str((doc.to_dict() or {}).get("projeto") or "GERAL") for doc in open_task_docs
    )

    projetos = []
    for doc in project_docs:
        data = doc.to_dict() or {}
        name = str(data.get("nome") or doc.id)
        projetos.append(
            {
                "id": doc.id,
                "nome": name,
                "descricao": _truncate(data.get("descricao"), 180),
                "tarefas_abertas": open_tasks_by_project.get(name, 0)
                + open_tasks_by_project.get(doc.id, 0),
                "orcamento": data.get("orcamento"),
            }
        )

    return {
        "total_retornado": len(projetos),
        "projetos": projetos,
    }


def buscar_memorias_relevantes(termo: str, limite: int = 8) -> dict:
    limit_value = _bounded_limit(limite, default=8, maximum=20)
    normalized_term = _normalize(termo)
    if not normalized_term:
        return {"erro": "Termo de busca vazio.", "memorias": []}

    memories = []
    for snap in get_db().collection("knowledge_nodes").limit(700).stream():
        data = snap.to_dict() or {}
        content = (
            data.get("texto_memoria")
            or data.get("fato")
            or data.get("resumo")
            or data.get("titulo")
            or ""
        )
        haystack = _normalize(
            " ".join(
                str(data.get(key) or "")
                for key in ("texto_memoria", "fato", "resumo", "titulo", "categoria", "tipo")
            )
        )
        if all(term in haystack for term in normalized_term.split()):
            memories.append(
                {
                    "id": snap.id,
                    "tipo": data.get("tipo"),
                    "categoria": data.get("categoria"),
                    "conteudo": _truncate(content, 320),
                }
            )

    return {
        "termo": termo,
        "total_retornado": min(len(memories), limit_value),
        "memorias": memories[:limit_value],
    }


def call_tool(name: str, args: dict | None = None) -> dict:
    args = args or {}
    if name == "buscar_tarefas_pendentes_hoje":
        return buscar_tarefas_pendentes_hoje(limite=args.get("limite", 10))
    if name == "buscar_tarefas_amanha":
        return buscar_tarefas_amanha(limite=args.get("limite", 10))
    if name == "buscar_tarefas_atrasadas":
        return buscar_tarefas_atrasadas(limite=args.get("limite", 10))
    if name == "buscar_tarefas_por_periodo":
        return buscar_tarefas_por_periodo(
            data_inicio=args.get("data_inicio", ""),
            data_fim=args.get("data_fim", ""),
            limite=args.get("limite", 15),
        )
    if name == "buscar_tarefas_por_termo":
        return buscar_tarefas_por_termo(
            termo=args.get("termo", ""),
            status=args.get("status"),
            limite=args.get("limite", 10),
        )
    if name == "resumo_projetos_ativos":
        return resumo_projetos_ativos(limite=args.get("limite", 10))
    if name == "buscar_memorias_relevantes":
        return buscar_memorias_relevantes(
            termo=args.get("termo", ""),
            limite=args.get("limite", 8),
        )
    return {"erro": f"Ferramenta desconhecida: {name}"}


def call_tool_json(name: str, args: dict | None = None) -> str:
    return json.dumps(call_tool(name, args), ensure_ascii=False)


def _bounded_limit(value, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _format_task(doc_id: str, data: dict) -> dict:
    return {
        "id": doc_id,
        "titulo": data.get("titulo"),
        "status": data.get("status"),
        "projeto": data.get("projeto"),
        "area_tematica": data.get("area_tematica"),
        "tipo_acao": data.get("tipo_acao"),
        "data_limite": data.get("data_limite"),
        "horario_inicio": data.get("horario_inicio"),
        "horario_fim": data.get("horario_fim"),
        "execution_lane": data.get("execution_lane"),
        "responsavel": data.get("responsavel"),
        "tags": data.get("tags"),
        "processo_sei": data.get("processo_sei"),
        "descricao": _truncate(data.get("descricao") or data.get("notas"), 220),
    }


def _truncate(value, max_chars: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."


def _load_task_candidates(max_docs: int = 700) -> list[dict]:
    docs = get_db().collection("tarefas").limit(max_docs).stream()
    return [{"_id": doc.id, **(doc.to_dict() or {})} for doc in docs]


def _is_open_task(task: dict) -> bool:
    return str(task.get("status") or "") in OPEN_TASK_STATUSES


def _is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _parse_date_or_today(value: str):
    try:
        return datetime.strptime(str(value or ""), "%Y-%m-%d").date()
    except ValueError:
        return datetime.now(LOCAL_TZ).date()


def _normalize(value) -> str:
    import re
    import unicodedata

    ascii_text = unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii",
        "ignore",
    ).decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).strip()
