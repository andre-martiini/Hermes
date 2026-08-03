import io
import json
import os
import re
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
            {
                "name": "navegar_sistema",
                "description": (
                    "Navega na interface do sistema Hermes para um modulo ou visao especifica. "
                    "Use quando o usuario pedir para ir, abrir ou acessar uma tela/modulo, ou para 'programar o meu dia' / 'fazer a programação do dia'. "
                    "Modulos aceitos: 'dashboard', 'programacao_dia' (abrir agenda do dia), 'financeiro', 'saude', 'acoes', 'servicos', 'estrategia', 'godmode', 'conhecimento', 'contatos', 'rag-bases', 'ferramentas', 'licitacoes', 'assistencia', 'pgc', 'concluidas'."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "modulo": {
                            "type": "STRING",
                            "description": "Nome do modulo ou visao de destino (ex: programacao_dia, acoes, financeiro, saude, dashboard, estrategia, ferramentas, etc).",
                        }
                    },
                    "required": ["modulo"],
                },
            },
            {
                "name": "abrir_detalhe_acao",
                "description": (
                    "OBRIGATORIO: Abre a janela/modal de detalhamento ou execucao de uma acao/tarefa no Hermes na tela do usuario. "
                    "Chame SEMPRE esta ferramenta quando o usuario pedir para abrir, ver, detalhar ou mostrar uma acao especifica. "
                    "Nao apenas responda ou busque no banco de dados; voce DEVE chamar esta ferramenta para abrir o modal na tela dele."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "id_ou_termo": {
                            "type": "STRING",
                            "description": "ID exato da acao ou titulo/nome da acao que o usuario quer abrir na tela.",
                        }
                    },
                    "required": ["id_ou_termo"],
                },
            },
            {
                "name": "abrir_ferramenta",
                "description": (
                    "Abre uma ferramenta especifica dentro do Hermes. "
                    "Ferramentas validas: 'shopping' (Lista de Compras), 'transcription' (Transcricao), 'batch_transcription', 'meeting_transcription', 'sipac_tracking' (SIPAC), 'monitor_paginas', 'long_transcription', 'pop_manager'."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "ferramenta_id": {
                            "type": "STRING",
                            "description": "ID da ferramenta (ex: shopping, transcription, sipac_tracking, etc).",
                        }
                    },
                    "required": ["ferramenta_id"],
                },
            },
            {
                "name": "fechar_detalhe_acao",
                "description": (
                    "Fecha o modal/janela de detalhamento de acao que esta aberta na tela do usuario. "
                    "Use quando o usuario pedir para sair da acao, fechar o detalhamento, fechar a tarefa ou voltar da acao para a lista."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
            {
                "name": "filtrar_acoes",
                "description": (
                    "Aplica um filtro de busca textual ou status na lista de acoes do Hermes."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "termo_busca": {
                            "type": "STRING",
                            "description": "Termo de busca para filtrar na tela de acoes.",
                        },
                        "status": {
                            "type": "STRING",
                            "description": "Filtro de status (ex: 'em andamento', 'concluida', etc).",
                        },
                    },
                },
            },
            {
                "name": "ler_conteudo_link_drive",
                "description": (
                    "Le e extrai o conteudo textual completo de um arquivo ou link do Google Drive "
                    "(Google Docs, Planilhas, PDFs, Word, arquivos de texto, etc). "
                    "Use quando o usuario pedir para ler, resumir, analisar ou investigar o conteudo de um link ou arquivo do Google Drive."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "url_ou_id": {
                            "type": "STRING",
                            "description": "URL completa do Google Drive/Docs/Sheets (ex: https://drive.google.com/file/d/.../view) ou o ID exato do arquivo no Drive.",
                        }
                    },
                    "required": ["url_ou_id"],
                },
            },
            {
                "name": "enviar_whatsapp_contato",
                "description": (
                    "Prepara e abre a conversa do WhatsApp no computador/navegador do usuario com um contato do Hermes. "
                    "Use SEMPRE que o usuario pedir para enviar WhatsApp, mandar um ZAP ou abrir conversa com alguem da agenda de contatos."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "nome_ou_telefone": {
                            "type": "STRING",
                            "description": "Nome da pessoa cadastrada no modulo de Contatos do Hermes (ex: 'Maria', 'Joao Silva') ou numero de telefone.",
                        },
                        "mensagem": {
                            "type": "STRING",
                            "description": "Texto da mensagem a ser enviada no WhatsApp.",
                        },
                    },
                    "required": ["nome_ou_telefone", "mensagem"],
                },
            },
            {
                "name": "agendar_whatsapp_contato",
                "description": (
                    "Agenda o envio de uma mensagem de WhatsApp para um contato num horario futuro. "
                    "No horario programado, o Hermes enviara os botoes de confirmacao ('Sim, Enviar' / 'Cancelar') no Telegram. "
                    "Use quando o usuario pedir para agendar, programar ou marcar um WhatsApp para depois/amanha/data especifica."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "nome_ou_telefone": {
                            "type": "STRING",
                            "description": "Nome da pessoa nos Contatos ou numero de telefone.",
                        },
                        "mensagem": {
                            "type": "STRING",
                            "description": "Texto da mensagem a ser enviada.",
                        },
                        "data_horario": {
                            "type": "STRING",
                            "description": "Data e horario para o envio (ex: '2026-08-04 14:00', 'amanha as 10h', 'hoje as 18h30').",
                        },
                    },
                    "required": ["nome_ou_telefone", "mensagem", "data_horario"],
                },
            },
        ]
    }
]

UI_TOOL_NAMES = {"navegar_sistema", "abrir_detalhe_acao", "fechar_detalhe_acao", "abrir_ferramenta", "filtrar_acoes"}




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
    if name == "ler_conteudo_link_drive":
        return ler_conteudo_link_drive(
            url_ou_id=args.get("url_ou_id") or args.get("url") or args.get("id") or ""
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


_DRIVE_ID_RE = re.compile(
    r"(?:drive\.google\.com/(?:file/d/|open\?id=)|docs\.google\.com/\w+/d/)([a-zA-Z0-9_-]{20,})"
)


def _extract_drive_file_id(value: str) -> str | None:
    if not value:
        return None
    match = _DRIVE_ID_RE.search(value)
    if match:
        return match.group(1)
    cleaned = value.strip()
    if len(cleaned) >= 20 and "/" not in cleaned and " " not in cleaned:
        return cleaned
    return None


def ler_conteudo_link_drive(url_ou_id: str) -> dict:
    """Extrai e le o conteudo em texto de um arquivo ou link do Google Drive."""
    import io
    fid = _extract_drive_file_id(url_ou_id)
    if not fid:
        return {"erro": f"Nao foi possivel extrair um File ID valido do link fornecido: {url_ou_id}"}

    db = get_db()
    creds_doc = db.collection("system").document("google_credentials").get()
    if not creds_doc.exists:
        return {"erro": "Credenciais do Google Drive nao encontradas no sistema (Firestore: system/google_credentials)."}

    creds_data = creds_doc.to_dict() or {}
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload

        creds = Credentials(
            token=creds_data.get("token") or creds_data.get("access_token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
        )
        service = build("drive", "v3", credentials=creds)
        meta = service.files().get(fileId=fid, fields="name,mimeType").execute()
        file_name = meta.get("name", "arquivo_drive")
        mime = meta.get("mimeType", "application/octet-stream")

        gapps_mime = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }

        if mime in gapps_mime:
            request = service.files().export_media(fileId=fid, mimeType=gapps_mime[mime])
        else:
            request = service.files().get_media(fileId=fid)

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        content_bytes = buffer.getvalue()

        text = ""
        lower_name = file_name.lower()

        if mime in gapps_mime or lower_name.endswith((".txt", ".csv", ".md", ".json", ".xml", ".html")):
            text = content_bytes.decode("utf-8", errors="replace")
        elif lower_name.endswith(".pdf") or mime == "application/pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(content_bytes))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as pdf_err:
                text = f"[Falha ao ler PDF com pypdf: {pdf_err}]"
        elif lower_name.endswith(".docx"):
            try:
                import mammoth
                text = mammoth.extract_raw_text(io.BytesIO(content_bytes)).value or ""
            except Exception as docx_err:
                text = f"[Falha ao ler DOCX: {docx_err}]"
        else:
            text = content_bytes.decode("utf-8", errors="replace")

        cleaned_text = text.lstrip("\ufeff").strip()
        if len(cleaned_text) > 8000:
            cleaned_text = cleaned_text[:8000] + "\n... [conteudo truncado para brevidade]"

        return {
            "status": "sucesso",
            "nome_arquivo": file_name,
            "mime_type": mime,
            "conteudo_texto": cleaned_text or "Arquivo sem texto extraivel.",
        }
    except Exception as exc:
        return {"erro": f"Falha ao acessar ou ler arquivo no Google Drive (ID: {fid}): {exc}"}


def _limpar_telefone(raw_phone: str) -> str:
    digits = re.sub(r"\D", "", str(raw_phone or ""))
    if digits.startswith("0"):
        digits = digits[1:]
    if digits.startswith("55") and len(digits) in (12, 13):
        return digits
    if len(digits) in (10, 11):
        return f"55{digits}"
    if not digits.startswith("55") and len(digits) >= 8:
        return f"55{digits}"
    return digits


def enviar_whatsapp_contato(nome_ou_telefone: str, mensagem: str) -> dict:
    """Busca contato no Firestore perfil_pessoas/usuarios e gera a URL de envio do WhatsApp."""
    import urllib.parse

    nome_ou_tel = str(nome_ou_telefone or "").strip()
    msg = str(mensagem or "").strip()
    if not nome_ou_tel:
        return {"erro": "Informe o nome ou número de telefone do contato."}

    db = get_db()
    contato_encontrado = None
    telefone_bruto = None

    if re.search(r"\d{8,}", nome_ou_tel):
        telefone_bruto = nome_ou_tel
    else:
        termo_lower = nome_ou_tel.lower()
        for snap in db.collection("perfil_pessoas").stream():
            d = snap.to_dict() or {}
            nome = str(d.get("nome") or "").strip()
            tel = d.get("telefone") or d.get("whatsapp") or d.get("celular") or d.get("fone")
            if nome and tel and termo_lower in nome.lower():
                contato_encontrado = nome
                telefone_bruto = str(tel)
                break

        if not telefone_bruto:
            for snap in db.collection("usuarios").stream():
                d = snap.to_dict() or {}
                nome = str(d.get("nome") or "").strip()
                tel = d.get("telefone") or d.get("whatsapp") or d.get("celular")
                if nome and tel and termo_lower in nome.lower():
                    contato_encontrado = nome
                    telefone_bruto = str(tel)
                    break

    if not telefone_bruto:
        return {
            "erro": f"Não foi possível encontrar o telefone de '{nome_ou_tel}' no cadastro de Contatos do Hermes. Verifique se a pessoa está cadastrada com número de telefone."
        }

    tel_formatado = _limpar_telefone(telefone_bruto)
    if not tel_formatado or len(tel_formatado) < 10:
        return {
            "erro": f"O número de telefone de '{contato_encontrado or nome_ou_tel}' ({telefone_bruto}) parece inválido."
        }

    msg_encoded = urllib.parse.quote(msg)
    url_whatsapp = f"https://api.whatsapp.com/send?phone={tel_formatado}&text={msg_encoded}"

    return {
        "status": "ok",
        "contato": contato_encontrado or nome_ou_tel,
        "telefone": tel_formatado,
        "mensagem": msg,
        "url_whatsapp": url_whatsapp,
        "instrucao_ui": "enviar_whatsapp_contato",
    }


def agendar_whatsapp_contato(nome_ou_telefone: str, mensagem: str, data_horario: str) -> dict:
    """Agenda o envio de mensagem de WhatsApp salvando na coleção whatsapp_outbox no Firestore."""
    from database import get_db
    import re
    from datetime import datetime, timedelta, timezone

    nome_ou_tel = str(nome_ou_telefone or "").strip()
    msg = str(mensagem or "").strip()
    dh_str = str(data_horario or "").strip()

    if not nome_ou_tel or not msg or not dh_str:
        return {"erro": "Informe contato, mensagem e data/horário para agendar o WhatsApp."}

    db = get_db()
    contato_encontrado = None
    telefone_bruto = None

    if re.search(r"\d{8,}", nome_ou_tel):
        telefone_bruto = nome_ou_tel
    else:
        termo_lower = nome_ou_tel.lower()
        for snap in db.collection("perfil_pessoas").stream():
            d = snap.to_dict() or {}
            nome = str(d.get("nome") or "").strip()
            tel = d.get("telefone") or d.get("whatsapp") or d.get("celular") or d.get("fone")
            if nome and tel and termo_lower in nome.lower():
                contato_encontrado = nome
                telefone_bruto = str(tel)
                break

        if not telefone_bruto:
            for snap in db.collection("usuarios").stream():
                d = snap.to_dict() or {}
                nome = str(d.get("nome") or "").strip()
                tel = d.get("telefone") or d.get("whatsapp") or d.get("celular")
                if nome and tel and termo_lower in nome.lower():
                    contato_encontrado = nome
                    telefone_bruto = str(tel)
                    break

    if not telefone_bruto:
        return {
            "erro": f"Não foi possível encontrar o telefone de '{nome_ou_tel}' nos Contatos. Verifique o cadastro."
        }

    tel_formatado = _limpar_telefone(telefone_bruto)
    if not tel_formatado or len(tel_formatado) < 10:
        return {"erro": f"O número de telefone de '{contato_encontrado or nome_ou_tel}' é inválido."}

    now_local = datetime.now(LOCAL_TZ)
    dt_target = None

    dh_lower = dh_str.lower()
    m_time = re.search(r"(\d{1,2})[h:](\d{2})?", dh_lower)
    hh = int(m_time.group(1)) if m_time else 14
    mm = int(m_time.group(2)) if (m_time and m_time.group(2)) else 0

    if "amanh" in dh_lower:
        target_date = (now_local + timedelta(days=1)).date()
        dt_target = datetime(target_date.year, target_date.month, target_date.day, hh, mm, tzinfo=LOCAL_TZ)
    elif "hoje" in dh_lower:
        dt_target = datetime(now_local.year, now_local.month, now_local.day, hh, mm, tzinfo=LOCAL_TZ)
    else:
        try:
            cleaned_iso = dh_str.replace("Z", "").strip()
            if "T" in cleaned_iso or " " in cleaned_iso:
                dt_raw = datetime.fromisoformat(cleaned_iso)
                dt_target = dt_raw.replace(tzinfo=LOCAL_TZ) if dt_raw.tzinfo is None else dt_raw
        except Exception:
            pass

    if not dt_target:
        dt_target = datetime(now_local.year, now_local.month, now_local.day, hh, mm, tzinfo=LOCAL_TZ)
        if dt_target <= now_local:
            dt_target += timedelta(days=1)

    doc_ref = db.collection("whatsapp_outbox").document()
    doc_ref.set({
        "to_number": tel_formatado,
        "contact_name": contato_encontrado or nome_ou_tel,
        "content": msg,
        "scheduled_for": dt_target,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })

    horario_formatado = dt_target.strftime("%d/%m/%Y às %H:%M")
    return {
        "status": "sucesso",
        "contato": contato_encontrado or nome_ou_tel,
        "telefone": tel_formatado,
        "mensagem": msg,
        "horario_programado": horario_formatado,
        "resposta_voz": f"WhatsApp para {contato_encontrado or nome_ou_tel} agendado com sucesso para {horario_formatado}. No horário, enviarei os botões de confirmação no Telegram.",
    }


