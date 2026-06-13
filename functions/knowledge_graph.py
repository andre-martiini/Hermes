"""
Grafo de Conhecimento Hermes
============================
Implementa as Cloud Functions e helpers do grafo de conhecimento:

  Fase 1 — on_tarefa_created_kg:
    Trigger Firestore onCreate em tarefas/{taskId}.
    Gera kg_tags via prompt Retrieval-First (prioriza tags existentes).

  Fase 2 — on_tarefa_concluida_kg:
    Trigger Firestore onUpdate em tarefas/{taskId}.
    Detecta transição → 'concluído', cristaliza o diário em um Nó Conceitual
    via Dual-Pass (embedding → top-3 candidatos → LLM decide).
    Atualiza o centróide do nó (média vetorial incremental).

  RAG — extract_kg_rag_context(db, api_key, area_tematica, tags, top_n, token_limit):
    Extrai subgrafo ranqueado por peso_semantico × time_decay (λ=0.001).
    Circuit breaker: remove nó de menor rank até caber em token_limit.

  HTTP — buscar_procedimento:
    Callable HTTPS para tool calling do Copiloto.
    Aceita query livre e retorna os nós mais relevantes com citações.

  HTTP — crystallize_task_manual:
    Callable HTTPS para cristalizar manualmente uma tarefa já concluída
    (útil para migração e reteste).
"""

from __future__ import annotations

import json
import io
import math
import re
import tempfile
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Optional

from firebase_admin import firestore
from firebase_functions import firestore_fn, https_fn, options, pubsub_fn, scheduler_fn
from google.cloud.firestore_v1 import ArrayUnion
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from gemini_cost_controls import (
    GEMINI_BALANCED_MODEL,
    GEMINI_DOCUMENT_MODEL,
    GEMINI_EMBEDDING_MODEL,
    GEMINI_STRUCTURED_MODEL,
    embed_content_logged,
    generate_content_logged,
)

# ─── Constantes ──────────────────────────────────────────────────────────────

LAMBDA_DECAY = 0.001          # meia-vida ≈ 693 dias (~2 anos)
TOKEN_SAFETY_LIMIT = 8_000    # tokens máximos no payload RAG
CHARS_PER_TOKEN = 4           # estimativa rápida (sem tokenizer externo)
TOP_N_NODES = 5               # candidatos iniciais para o circuit breaker
DUAL_PASS_CANDIDATES = 3      # nós enviados ao LLM no Dual-Pass
NOISE_PREFIXES = (            # entradas de chat descartadas na cristalização
    "🤖 IA:",
    "✅ Sistema:",
    "[PROPOSAL]",
    "[/PROPOSAL]",
)

# ─── Módulo de Artefatos ─────────────────────────────────────────────────────
ARTEFATO_TOKEN_CAP    = 15_000
# ─── Módulo Acervo Global ─────────────────────────────────────────────────────
KG_TOKEN_LIMIT     = 6_000   # budget máximo para Nós Conceituais no RAG híbrido
ACERVO_TOKEN_LIMIT = 2_000   # budget máximo para Acervo Global no RAG híbrido
ARTEFATO_CHAR_CAP     = ARTEFATO_TOKEN_CAP * CHARS_PER_TOKEN  # ≈ 60 000 chars
ARTEFATO_PUBSUB_TOPIC = "hermes-artefato-kg"
SUPPORTED_MIMES = frozenset({
    "application/pdf",
    "application/msword",
    "application/json",
    "application/xml",
    "message/rfc822",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/csv",
    "text/xml",
    "text/plain",
    "text/markdown",
    "text/html",
    "image/jpeg",
    "image/png",
})

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
FILE_SEARCH_STORE_MODEL = "models/gemini-embedding-2"
FILE_SEARCH_QUERY_MODEL = GEMINI_BALANCED_MODEL
FILE_SEARCH_WAIT_SECONDS = 90


def _is_docx(filename: str | None = None, mime_type: str | None = None) -> bool:
    return (mime_type or "").lower().strip() == DOCX_MIME_TYPE or (filename or "").lower().endswith(".docx")


def _extract_docx_text(file_bytes: bytes) -> str:
    import mammoth

    result = mammoth.extract_raw_text(io.BytesIO(file_bytes))
    return (result.value or "").strip()
_DRIVE_ID_RE = re.compile(
    r"(?:drive\.google\.com/(?:file/d/|open\?id=)|docs\.google\.com/\w+/d/)([a-zA-Z0-9_-]{20,})"
)
URL_RE = re.compile(r"https?://[^\s\)\"\'<>]+")


# ─── Helpers: banco e LLM ────────────────────────────────────────────────────

def _get_db():
    return firestore.client()


def _get_api_key(db) -> Optional[str]:
    doc = db.collection("system").document("api_keys").get()
    return doc.to_dict().get("gemini_api_key") if doc.exists else None


def _gemini_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


_EMBEDDING_DIM = 768  # dimensão esperada do gemini-embedding-001


def _get_embedding(
    text: str,
    api_key: str,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[float]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    
    response = embed_content_logged(
        client,
        model=GEMINI_EMBEDDING_MODEL,
        contents=text[:8000],
        feature=f"knowledge_graph.embedding.{task_type.lower()}",
        db=_get_db(),
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=_EMBEDDING_DIM
        )
    )
    
    vec = response.embeddings[0].values
    if len(vec) != _EMBEDDING_DIM:
        raise ValueError(
            f"Dimensão inválida: esperado {_EMBEDDING_DIM}, "
            f"recebido {len(vec)}. task_type={task_type!r}"
        )
    return vec


# ─── Helpers: álgebra vetorial ───────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _update_centroid(old_vec: list[float], n: int, new_vec: list[float]) -> list[float]:
    """Média vetorial incremental: new_centroid = (old * n + new) / (n + 1)."""
    return [(old_vec[i] * n + new_vec[i]) / (n + 1) for i in range(len(old_vec))]


# ─── Helpers: diário limpo ───────────────────────────────────────────────────

def _build_clean_diary(task_data: dict) -> str:
    """
    Constrói o texto do diário descartando ruído:
      - Entradas de acompanhamento com prefixos de sistema/IA
      - Mensagens de chat irrelevantes (rascunhos, erros, [PROPOSAL])
    Prioriza entradas validadas do acompanhamento e decisões consolidadas do chat.
    """
    lines: list[str] = [
        f"Ação: {task_data.get('titulo', '(sem título)')}",
        f"Área: {task_data.get('area_tematica', '')}",
        f"Projeto: {task_data.get('projeto', '')}",
        "",
        "=== DIÁRIO DE BORDO ===",
    ]

    def _obter_data_ordenacao(entry):
        d = entry.get('data')
        if not d:
            return ""
        if isinstance(d, str):
            return d
        import datetime as _datetime
        if isinstance(d, _datetime.datetime):
            if d.tzinfo is None:
                d = d.replace(tzinfo=_datetime.timezone.utc)
            return d.isoformat()
        if isinstance(d, _datetime.date):
            return d.isoformat()
        if hasattr(d, 'isoformat'):
            try:
                return d.isoformat()
            except Exception:
                pass
        return str(d)

    entries = sorted(
        task_data.get("acompanhamento", []),
        key=_obter_data_ordenacao,
    )
    for entry in entries:
        nota = (entry.get("nota") or "").strip()
        if not nota:
            continue
        if any(nota.startswith(prefix) for prefix in NOISE_PREFIXES):
            continue
        date_label = entry.get("data", "")
        if date_label:
            if isinstance(date_label, str):
                try:
                    val = date_label.strip()
                    if val.endswith('Z'):
                        val = val[:-1] + '+00:00'
                    dt = datetime.fromisoformat(val)
                    date_label = dt.strftime("%d/%m/%Y %H:%M")
                except Exception:
                    pass
            elif hasattr(date_label, "strftime"):
                try:
                    date_label = date_label.strftime("%d/%m/%Y %H:%M")
                except Exception:
                    pass
            else:
                date_label = str(date_label)
        else:
            date_label = ""
        lines.append(f"[{date_label}] {nota}")

    # Decisões consolidadas do chat (apenas mensagens longas do assistente, sem artefatos)
    chat_decisions: list[str] = []
    for msg in task_data.get("chat_history", []):
        if msg.get("role") != "assistant":
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if any(content.startswith(p) for p in NOISE_PREFIXES):
            continue
        if msg.get("isArtifact"):
            continue
        if len(content) > 80:  # apenas respostas substantivas
            chat_decisions.append(content[:600])  # trunca para não explodir o prompt

    if chat_decisions:
        lines.append("")
        lines.append("=== DECISÕES E ANÁLISES DO COPILOTO ===")
        for i, d in enumerate(chat_decisions, 1):
            lines.append(f"{i}. {d}")

    return "\n".join(lines)


# ─── Helpers: tokens ─────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


# ─── Módulo de Artefatos: helpers ────────────────────────────────────────────

def _infer_mime(nome: str) -> str:
    """Infere MIME type pela extensão do arquivo."""
    n = nome.lower()
    if n.endswith(".pdf"):  return "application/pdf"
    if n.endswith(".doc"):  return "application/msword"
    if n.endswith(".docx"): return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if n.endswith(".xls"):  return "application/vnd.ms-excel"
    if n.endswith(".xlsx"): return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if n.endswith(".pptx"): return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if n.endswith(".csv"):  return "text/csv"
    if n.endswith(".txt"):  return "text/plain"
    if n.endswith(".json"): return "application/json"
    if n.endswith(".xml"):  return "application/xml"
    if n.endswith(".eml"):  return "message/rfc822"
    if n.endswith(".md") or n.endswith(".markdown"): return "text/markdown"
    if n.endswith(".html") or n.endswith(".htm"): return "text/html"
    return "application/octet-stream"


def _extract_drive_id(url: str) -> str:
    """Extrai o file_id de uma URL do Google Drive/Docs."""
    m = _DRIVE_ID_RE.search(url)
    return m.group(1) if m else ""


def _get_google_creds_kg(db):
    """Credenciais OAuth2 do Firestore com escopo Drive (espelho de main.py)."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    creds_doc = db.collection("system").document("google_credentials").get()
    if not creds_doc.exists:
        raise RuntimeError("Credenciais Google nao encontradas no Firestore.")
    d = creds_doc.to_dict()
    expiry_val = d.get("expiry_date") or d.get("expiry")
    parsed_expiry = None
    if expiry_val:
        from datetime import datetime, timezone
        if isinstance(expiry_val, datetime):
            parsed_expiry = expiry_val
        elif isinstance(expiry_val, (int, float)):
            if expiry_val > 1e11:  # milliseconds
                expiry_val = expiry_val / 1000.0
            parsed_expiry = datetime.fromtimestamp(expiry_val, timezone.utc)
        elif isinstance(expiry_val, str):
            try:
                parsed_expiry = datetime.fromisoformat(expiry_val.replace('Z', '+00:00'))
            except ValueError:
                pass

        if parsed_expiry and parsed_expiry.tzinfo is not None:
            parsed_expiry = parsed_expiry.astimezone(timezone.utc).replace(tzinfo=None)

    creds = Credentials(
        token=d.get("token"),
        refresh_token=d.get("refresh_token"),
        token_uri=d.get("token_uri"),
        client_id=d.get("client_id"),
        client_secret=d.get("client_secret"),
        scopes=["https://www.googleapis.com/auth/drive"],
        expiry=parsed_expiry,
    )
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            db.collection("system").document("google_credentials").update(
                {
                    "token": creds.token,
                    "expiry_date": creds.expiry,
                    "updated_at": firestore.SERVER_TIMESTAMP
                }
            )
        except Exception as exc:
            print(f"[KG Artefato] Falha ao renovar token Google: {exc}")
    return creds


def _download_from_drive(file_id: str, db) -> bytes:
    """Baixa um arquivo do Google Drive pelo ID."""
    from googleapiclient.discovery import build
    service = build("drive", "v3", credentials=_get_google_creds_kg(db))
    return service.files().get_media(fileId=file_id).execute()


def _aggregate_artefatos(task_data: dict, db) -> list[dict]:
    """
    Agrega artefatos de 3 fontes e desduplicates por URL.
    Retorna lista com status_indexacao='pendente'.

    Fontes:
      1. pool_dados[tipo='arquivo']
      2. URLs do Google Drive encontradas no acompanhamento (Diário de Bordo)
      3. Arquivos do extra_context_id (coleção 'conhecimento')
    """
    seen_urls: set = set()
    result: list = []

    def _add(nome: str, url: str, tipo_mime: str, drive_file_id: str = ""):
        url = url.rstrip("/")
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        entry: dict = {
            "nome": nome or url.split("/")[-1] or "artefato",
            "url": url,
            "tipo_mime": tipo_mime,
            "resumo_semantico": None,
            "status_indexacao": "pendente",
        }
        if drive_file_id:
            entry["drive_file_id"] = drive_file_id
        result.append(entry)

    # Fonte 1: pool_dados
    for item in task_data.get("pool_dados", []):
        if item.get("tipo") != "arquivo":
            continue
        file_id = item.get("drive_file_id", "")
        url = item.get("valor", "")
        if not url and file_id:
            url = f"https://drive.google.com/file/d/{file_id}/view"
        if not file_id and url:
            file_id = _extract_drive_id(url)
        nome = item.get("nome", "")
        _add(nome, url, _infer_mime(nome), file_id)

    # Fonte 2: URLs Drive brutas no diário
    for entry in task_data.get("acompanhamento", []):
        nota = entry.get("nota", "") or ""
        for url in URL_RE.findall(nota):
            if "drive.google.com" not in url and "docs.google.com" not in url:
                continue
            file_id = _extract_drive_id(url)
            nome = url.split("/")[-1].split("?")[0] or "link-diario"
            _add(nome, url, "application/pdf", file_id)

    # Fonte 3: extra_context_id
    extra_ctx_id = task_data.get("extra_context_id")
    if extra_ctx_id:
        try:
            for doc in (
                db.collection("conhecimento")
                .where("extra_context_id", "==", extra_ctx_id)
                .stream()
            ):
                d = doc.to_dict() or {}
                url = d.get("url_drive", "")
                nome = d.get("titulo", "")
                tipo = d.get("tipo_arquivo", "")
                if tipo == "pdf":
                    mime = "application/pdf"
                elif tipo in ("doc", "docx"):
                    mime = "application/msword" if tipo == "doc" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif tipo in ("xls", "xlsx"):
                    mime = "application/vnd.ms-excel" if tipo == "xls" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                elif tipo == "csv":
                    mime = "text/csv"
                elif tipo == "pptx":
                    mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                elif tipo in ("txt", "text", "plain"):
                    mime = "text/plain"
                elif tipo == "json":
                    mime = "application/json"
                elif tipo == "xml":
                    mime = "application/xml"
                elif tipo == "eml":
                    mime = "message/rfc822"
                elif tipo in ("md", "markdown"):
                    mime = "text/markdown"
                elif tipo in ("html", "htm"):
                    mime = "text/html"
                else:
                    mime = _infer_mime(nome)
                _add(nome, url, mime, _extract_drive_id(url))
        except Exception as exc:
            print(f"[KG Artefato] Erro ao buscar extra_context ({extra_ctx_id}): {exc}")

    return result


def _dispatch_artefatos_pubsub(project_id: str, task_id: str, artefatos: list) -> None:
    """Publica uma mensagem por artefato no tópico hermes-artefato-kg (origem='tarefa')."""
    import json
    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, ARTEFATO_PUBSUB_TOPIC)
    for idx, art in enumerate(artefatos):
        msg = {
            "origem": "tarefa",
            "task_id": task_id,
            "artefato_idx": idx,
            "url": art["url"],
            "tipo_mime": art["tipo_mime"],
            "drive_file_id": art.get("drive_file_id", ""),
            "nome": art["nome"],
        }
        publisher.publish(topic_path, json.dumps(msg).encode("utf-8"))
    print(f"[KG Artefato] {len(artefatos)} mensagens publicadas para tarefa {task_id}")


def _update_artefato_status(
    db, task_id: str, idx: int, status: str, resumo: Optional[str]
) -> None:
    """Atualiza status_indexacao e resumo_semantico de um item em artefatos_kg."""
    task_ref = db.collection("tarefas").document(task_id)
    snap = task_ref.get()
    if not snap.exists:
        print(f"[KG Artefato] Tarefa nao encontrada para update: {task_id}")
        return
    artefatos = (snap.to_dict() or {}).get("artefatos_kg", [])
    if idx >= len(artefatos):
        print(f"[KG Artefato] Indice {idx} fora do array artefatos_kg da tarefa {task_id}")
        return
    artefatos[idx]["status_indexacao"] = status
    if resumo is not None:
        artefatos[idx]["resumo_semantico"] = resumo
    task_ref.update({"artefatos_kg": artefatos})


def _gather_artefatos_for_node(db, task_ids: list, max_tasks: int = 3, max_per_task: int = 2) -> list:
    """
    Busca resumos de artefatos das tarefas mais recentes vinculadas a um nó.
    Retorna lista de (nome, resumo) para inclusão no contexto RAG.
    """
    items = []
    for t_id in task_ids[-max_tasks:]:
        try:
            snap = db.collection("tarefas").document(t_id).get()
            if not snap.exists:
                continue
            for art in (snap.to_dict() or {}).get("artefatos_kg", []):
                if art.get("status_indexacao") == "concluido" and art.get("resumo_semantico"):
                    items.append((art["nome"], art["resumo_semantico"]))
                    if len(items) >= max_tasks * max_per_task:
                        return items
        except Exception:
            continue
    return items


# ─── Módulo Acervo Global: helpers ───────────────────────────────────────────

def _fetch_tag_vocabulary(db) -> list[str]:
    """
    Lê o dicionário centralizado de tags (system/tag_vocabulary) — 1 leitura.
    Fallback: scan de 500 tarefas para bootstrap quando o doc ainda não existe.
    """
    try:
        vocab_doc = db.collection("system").document("tag_vocabulary").get()
        if vocab_doc.exists:
            tags = vocab_doc.to_dict().get("tags", [])
            if tags:
                return sorted(set(str(t).strip() for t in tags if t))
    except Exception as exc:
        print(f"[KG Tags] Erro ao ler tag_vocabulary: {exc}")
    return _fetch_all_existing_tags(db)


def _update_acervo_doc(
    db,
    acervo_id: str,
    status: str,
    resumo: Optional[str],
    tags: list,
    embedding: list,
    extra: Optional[dict] = None,
) -> None:
    """Atualiza um documento acervo_global com o resultado da indexação."""
    update: dict = {"status_indexacao": status}
    if resumo is not None:
        update["resumo_semantico"] = resumo
    if tags:
        update["tags"] = tags
    if embedding:
        update["embedding"] = embedding
    if extra:
        update.update(extra)
    try:
        db.collection("acervo_global").document(acervo_id).update(update)
    except Exception as exc:
        print(f"[KG Acervo] Erro ao atualizar acervo_global/{acervo_id}: {exc}")


def _write_to_indice_artefatos(
    db,
    nome: str,
    url: str,
    tipo_mime: str,
    resumo: str,
    embedding: list,
    tags: list,
    origem: str,
    task_id: Optional[str] = None,
    acervo_id: Optional[str] = None,
    texto_bruto: Optional[str] = None,
    file_search: Optional[dict] = None,
) -> None:
    """Grava entrada no índice vetorial unificado (indice_artefatos)."""
    doc_id = str(uuid.uuid4())[:16]
    entry: dict = {
        "nome": nome,
        "url": url,
        "tipo_mime": tipo_mime,
        "resumo_semantico": resumo,
        # Vector é obrigatório: listas simples não entram no índice vetorial
        # e ficam invisíveis ao find_nearest usado nas buscas do acervo.
        "embedding": Vector(list(map(float, embedding))) if embedding else embedding,
        "tags": tags,
        "origem": origem,
        "indexed_at": firestore.SERVER_TIMESTAMP,
    }
    if task_id:
        entry["task_id"] = task_id
    if acervo_id:
        entry["acervo_id"] = acervo_id
    if texto_bruto:
        # Limite defensivo: o upstream já trunca em ARTEFATO_CHAR_CAP, mas garantimos aqui.
        entry["texto_bruto"] = texto_bruto[:ARTEFATO_CHAR_CAP]
    if file_search:
        entry["file_search"] = file_search
    db.collection("indice_artefatos").document(doc_id).set(entry)
    print(f"[KG IndiceArtefatos] Entrada gravada: {nome} ({origem})")


def _plain_genai_value(value):
    """Converte objetos do SDK Gemini para estruturas simples graváveis no Firestore."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_plain_genai_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain_genai_value(v) for k, v in value.items() if v is not None}
    for method_name in ("model_dump", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                return _plain_genai_value(method())
            except Exception:
                pass
    if hasattr(value, "__dict__"):
        return {
            str(k): _plain_genai_value(v)
            for k, v in vars(value).items()
            if not k.startswith("_") and v is not None
        }
    return str(value)


def _get_or_create_file_search_store(db, api_key: str) -> Optional[str]:
    """Retorna o File Search Store do Hermes, criando um store piloto se necessário."""
    doc_ref = db.collection("system").document("file_search")
    try:
        snap = doc_ref.get()
        current_data = snap.to_dict() or {} if snap.exists else {}
        current = current_data.get("store_name")
        if current and current_data.get("embedding_model") == FILE_SEARCH_STORE_MODEL:
            return current
        if current:
            print("[KG FileSearch] Store atual nao e multimodal; tentando criar store novo.")

        client = _gemini_client(api_key)
        store_name = None
        store = None
        try:
            store = client.file_search_stores.create(
                config={
                    "display_name": "Hermes Acervo Global",
                    "embedding_model": FILE_SEARCH_STORE_MODEL,
                }
            )
            embedding_model_status = FILE_SEARCH_STORE_MODEL
        except Exception as exc:
            print(f"[KG FileSearch] SDK nao aceitou embedding_model; tentando REST: {exc}")
            try:
                import requests
                rest_resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/fileSearchStores?key={api_key}",
                    json={
                        "display_name": "Hermes Acervo Global",
                        "embedding_model": FILE_SEARCH_STORE_MODEL,
                    },
                    timeout=30,
                )
                rest_resp.raise_for_status()
                rest_data = rest_resp.json()
                store_name = rest_data.get("name")
                if not store_name:
                    raise RuntimeError(f"REST sem name: {rest_data}")
                store = None
                embedding_model_status = FILE_SEARCH_STORE_MODEL
            except Exception as rest_exc:
                if current:
                    print(f"[KG FileSearch] REST com embedding_model falhou; mantendo store atual: {rest_exc}")
                    return current
                print(f"[KG FileSearch] REST com embedding_model falhou; criando store padrao: {rest_exc}")
                store = client.file_search_stores.create(
                    config={"display_name": "Hermes Acervo Global"}
                )
                embedding_model_status = "default"
        if not store_name:
            store_name = getattr(store, "name", None)
        if not store_name:
            print("[KG FileSearch] Store criado sem campo name no retorno.")
            return None
        doc_ref.set({
            "store_name": store_name,
            "display_name": "Hermes Acervo Global",
            "embedding_model": embedding_model_status,
            "created_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        print(f"[KG FileSearch] Store criado: {store_name}")
        return store_name
    except Exception as exc:
        print(f"[KG FileSearch] Falha ao criar/obter store: {exc}")
        return None


def _build_file_search_metadata(
    nome: str,
    tipo_mime: str,
    origem: str,
    tags: list,
    task_id: Optional[str] = None,
    acervo_id: Optional[str] = None,
) -> list[dict]:
    """Metadados simples para permitir filtros no Gemini File Search."""
    metadata = [
        {"key": "nome", "string_value": nome[:500]},
        {"key": "tipo_mime", "string_value": tipo_mime},
        {"key": "origem", "string_value": origem},
    ]
    if task_id:
        metadata.append({"key": "task_id", "string_value": task_id})
    if acervo_id:
        metadata.append({"key": "acervo_id", "string_value": acervo_id})
    clean_tags = [str(tag).strip() for tag in (tags or [])[:20] if str(tag).strip()]
    if clean_tags:
        metadata.append({"key": "primary_tag", "string_value": clean_tags[0][:100]})
    for idx, tag_value in enumerate(clean_tags, 1):
        metadata.append({"key": f"tag_{idx:02d}", "string_value": tag_value[:100]})
    return metadata


def _index_file_search_document(
    db,
    api_key: str,
    file_bytes: bytes,
    nome: str,
    tipo_mime: str,
    origem: str,
    tags: list,
    task_id: Optional[str] = None,
    acervo_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Indexa o arquivo bruto no Gemini File Search.

    Esta camada é opcional: qualquer falha vira log e o RAG Firestore continua
    sendo a fonte principal.
    """
    store_name = _get_or_create_file_search_store(db, api_key)
    if not store_name:
        return None

    client = _gemini_client(api_key)
    metadata = _build_file_search_metadata(
        nome, tipo_mime, origem, tags, task_id=task_id, acervo_id=acervo_id
    )
    suffix = "." + (nome.rsplit(".", 1)[-1] if "." in nome else "bin")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        try:
            operation = client.file_search_stores.upload_to_file_search_store(
                file=temp_path,
                file_search_store_name=store_name,
                config={"display_name": nome, "custom_metadata": metadata},
            )
        except Exception as metadata_exc:
            print(f"[KG FileSearch] Upload com metadados falhou; tentando sem metadados: {metadata_exc}")
            operation = client.file_search_stores.upload_to_file_search_store(
                file=temp_path,
                file_search_store_name=store_name,
                config={"display_name": nome},
            )

        start = time.monotonic()
        while not getattr(operation, "done", False):
            if time.monotonic() - start > FILE_SEARCH_WAIT_SECONDS:
                print(f"[KG FileSearch] Upload ainda pendente apos timeout: {nome}")
                break
            time.sleep(5)
            operation = client.operations.get(operation)

        response = _plain_genai_value(getattr(operation, "response", None))
        document_name = response.get("name") if isinstance(response, dict) else None
        payload = {
            "store_name": store_name,
            "document_name": document_name,
            "operation_name": getattr(operation, "name", None),
            "status": "concluido" if getattr(operation, "done", False) else "pendente",
            "metadata": metadata,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        print(f"[KG FileSearch] Documento enviado: {nome} ({payload['status']})")
        return payload
    except Exception as exc:
        print(f"[KG FileSearch] Falha ao indexar {nome}: {exc}")
        return None
    finally:
        if temp_path:
            try:
                import os
                os.remove(temp_path)
            except Exception:
                pass


def _assign_acervo_tags(
    db, api_key: str, nome: str, texto_cap: str, existing_tags: list[str]
) -> list[str]:
    """Atribui tags ao arquivo avulso via Retrieval-First (mesmo padrão da Fase 1)."""
    client = _gemini_client(api_key)
    tags_list = ", ".join(f'"{t}"' for t in existing_tags[:100]) if existing_tags else "(nenhuma ainda)"
    prompt = f"""Você é um classificador de documentos corporativos do sistema Hermes.

Arquivo: {nome}
Conteúdo (trecho):
{texto_cap[:1500]}

Tags existentes no sistema (priorize o reuso):
{tags_list}

Regras:
1. Retorne entre 1 e 7 tags que descrevam o TIPO e TEMA deste documento.
2. Prefira reusar tags da lista quando cobrirem o escopo.
3. Crie tag inédita APENAS se nenhuma existente se aplicar (ex: manual de ferramenta nova).
4. Tags curtas (1-3 palavras), em português, sem acentos especiais.
5. Responda APENAS com um array JSON. Exemplo: ["Contrato", "Licitacao", "PNAE"]

Responda:"""
    response = client.models.generate_content(
        model=GEMINI_STRUCTURED_MODEL, contents=prompt
    )
    raw = (response.text or "").strip()
    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if not match:
        return []
    try:
        tags = json.loads(match.group(0))
        return [str(t).strip() for t in tags if t and str(t).strip()][:7]
    except Exception:
        return []


def _dispatch_acervo_pubsub(
    project_id: str, acervo_id: str, url: str, tipo_mime: str, drive_file_id: str, nome: str
) -> None:
    """Publica uma mensagem única de acervo no tópico hermes-artefato-kg e aguarda confirmação."""
    import json as _json
    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, ARTEFATO_PUBSUB_TOPIC)
    msg = {
        "origem": "acervo",
        "acervo_id": acervo_id,
        "url": url,
        "tipo_mime": tipo_mime,
        "drive_file_id": drive_file_id,
        "nome": nome,
    }
    future = publisher.publish(topic_path, _json.dumps(msg).encode("utf-8"))
    future.result(timeout=10)  # Garante que a mensagem foi aceita pelo Pub/Sub


# ─── Fase 1: geração de tags Retrieval-First ─────────────────────────────────

def _generate_kg_tags(task_data: dict, existing_tags: list[str], api_key: str) -> list[str]:
    """
    Gera até 5 tags para a tarefa.
    Instrui a LLM a priorizar tags existentes; só cria inédita se nenhuma cobrir o escopo.
    """
    client = _gemini_client(api_key)

    titulo = task_data.get("titulo", "")
    area = task_data.get("area_tematica", "")
    descricao = task_data.get("descricao") or task_data.get("notas") or ""

    tags_list = ", ".join(f'"{t}"' for t in existing_tags[:80]) if existing_tags else "(nenhuma ainda)"

    prompt = f"""Você é um classificador de tarefas operacionais do sistema Hermes.

Tarefa: {titulo}
Área Temática: {area}
Descrição: {descricao[:500]}

Tags existentes no sistema (priorize o reuso):
{tags_list}

Regras:
1. Retorne entre 1 e 5 tags que descrevam o TIPO DE PROCEDIMENTO desta tarefa.
2. Prefira sempre reusar tags da lista acima quando cobrirem o escopo.
3. Crie uma tag INÉDITA apenas se nenhuma existente se aplicar.
4. Tags devem ser curtas (1-3 palavras), em português, sem acentos especiais.
5. Responda APENAS com um array JSON de strings. Exemplo: ["Contratação", "Dispensa", "CLC"]

Responda:"""

    response = client.models.generate_content(
        model=GEMINI_STRUCTURED_MODEL, contents=prompt
    )
    raw = (response.text or "").strip()

    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if not match:
        return []
    try:
        tags = json.loads(match.group(0))
        return [str(t).strip() for t in tags if t and str(t).strip()][:5]
    except Exception:
        return []


@firestore_fn.on_document_created(document="tarefas/{taskId}", memory=options.MemoryOption.MB_512, timeout_sec=120)
def on_tarefa_created_kg(event: firestore_fn.Event[firestore_fn.DocumentSnapshot]):
    """
    Fase 1 — Instanciação: gera kg_tags via Retrieval-First logo após a criação da tarefa.
    Disparado para QUALQUER origem (frontend, Copiloto, Google Tasks sync, Telegram, etc).
    Não acessa o diário (ainda vazio). Custo: 1 chamada LLM leve.
    """
    if not event.data or not event.data.exists:
        return

    task_data = event.data.to_dict() or {}
    task_id = event.params["taskId"]

    # Já tem tags: nada a fazer
    if task_data.get("kg_tags"):
        return
    # Única área excluída: tarefas internas do sistema
    if task_data.get("area_tematica") == "SISTEMAS":
        return
    # Fallback para tarefas sem area_tematica (ex: importadas do Google Tasks)
    if not task_data.get("area_tematica"):
        task_data["area_tematica"] = "GERAL"

    db = _get_db()
    api_key = _get_api_key(db)
    if not api_key:
        print(f"[KG Fase1] API key não encontrada para tarefa {task_id}")
        return

    # Coleta todas as tags existentes no banco (índice de tags)
    existing_tags = _fetch_all_existing_tags(db)

    try:
        tags = _generate_kg_tags(task_data, existing_tags, api_key)
        if tags:
            db.collection("tarefas").document(task_id).update({"kg_tags": tags})
            # Sincroniza dicionário centralizado (1 escrita, custo fixo)
            try:
                db.collection("system").document("tag_vocabulary").set(
                    {"tags": ArrayUnion(tags)}, merge=True
                )
            except Exception as exc:
                print(f"[KG Fase1] Erro ao atualizar tag_vocabulary: {exc}")
            print(f"[KG Fase1] Tags geradas para {task_id} (área={task_data['area_tematica']}): {tags}")
        else:
            print(f"[KG Fase1] Nenhuma tag gerada para tarefa {task_id}")
    except Exception as e:
        print(f"[KG Fase1] Erro ao gerar tags para {task_id}: {e}")


def _fetch_all_existing_tags(db) -> list[str]:
    """Busca todas as kg_tags distintas já registradas no banco (amostra de 500 tarefas)."""
    seen: set[str] = set()
    docs = db.collection("tarefas").select(["kg_tags"]).limit(500).stream()
    for doc in docs:
        for tag in (doc.to_dict() or {}).get("kg_tags", []):
            if tag:
                seen.add(tag)
    return sorted(seen)


# ─── Fase 2: cristalização ────────────────────────────────────────────────────

def _dual_pass_find_or_create_node(
    db,
    api_key: str,
    summary: str,
    embedding: list[float],
    area_tematica: str,
    task_id: str,
) -> tuple[str, float]:
    """
    Dual-Pass:
      1. Busca os DUAL_PASS_CANDIDATES nós conceituais mais próximos via cosine similarity.
      2. Envia para a LLM decidir: anexar a um existente ou criar nó inédito.
    Retorna (node_id, peso_semantico).
    """
    # ── Filtro 1: busca vetorial nos nós da mesma área ──────────────────────
    candidates = []
    nodes_stream = (
        db.collection("knowledge_nodes")
        .where("area_tematica", "==", area_tematica)
        .stream()
    )
    for ndoc in nodes_stream:
        nd = ndoc.to_dict() or {}
        node_emb = nd.get("embedding")
        if not node_emb:
            continue
        sim = _cosine_similarity(embedding, node_emb)
        candidates.append({
            "id": ndoc.id,
            "titulo": nd.get("titulo", ""),
            "resumo": nd.get("resumo", "")[:300],
            "similarity": sim,
        })

    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    top_candidates = candidates[:DUAL_PASS_CANDIDATES]

    # ── Filtro 2: LLM decide ─────────────────────────────────────────────────
    if top_candidates:
        candidates_text = "\n".join(
            f"{i+1}. [{c['id']}] \"{c['titulo']}\" (similaridade: {c['similarity']:.2f})\n   Resumo: {c['resumo']}"
            for i, c in enumerate(top_candidates)
        )
        prompt = f"""Você é um classificador de conhecimento operacional do sistema Hermes.

Resumo do procedimento executado na tarefa recém-concluída:
\"\"\"{summary[:800]}\"\"\"

Nós Conceituais existentes para a área "{area_tematica}":
{candidates_text}

Decisão:
- Se este procedimento se encaixa em um dos nós acima (mesma natureza operacional), responda com o ID do nó. Exemplo: ANEXAR:abc123
- Se este é um procedimento genuinamente diferente de todos os acima, responda: CRIAR_NOVO
Responda APENAS com uma das opções acima, sem mais texto."""

        client = _gemini_client(api_key)
        response = client.models.generate_content(
            model=GEMINI_STRUCTURED_MODEL, contents=prompt
        )
        decision = (response.text or "").strip()

        if decision.startswith("ANEXAR:"):
            node_id = decision.split(":", 1)[1].strip()
            # Valida que o nó existe
            if db.collection("knowledge_nodes").document(node_id).get().exists:
                best_sim = next(
                    (c["similarity"] for c in top_candidates if c["id"] == node_id),
                    top_candidates[0]["similarity"] if top_candidates else 0.7,
                )
                return node_id, round(best_sim, 4)

    # ── Cria nó inédito ───────────────────────────────────────────────────────
    new_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()
    db.collection("knowledge_nodes").document(new_id).set({
        "id": new_id,
        "titulo": _derive_node_title(summary, area_tematica, api_key),
        "area_tematica": area_tematica,
        "embedding": Vector(list(map(float, embedding))),
        "n_tasks": 0,
        "task_ids": [],
        "resumo": summary[:600],
        "data_criacao": now,
        "data_atualizacao": now,
    })
    print(f"[KG Fase2] Nó inédito criado: {new_id}")
    return new_id, 1.0


def _derive_node_title(summary: str, area: str, api_key: str) -> str:
    """Gera um título curto (3-6 palavras) para o novo Nó Conceitual."""
    client = _gemini_client(api_key)
    prompt = f"""Crie um título curto (3 a 6 palavras) para um Nó Conceitual de conhecimento operacional na área "{area}".
O nó agrupará tarefas com o seguinte tipo de procedimento:
\"\"\"{summary[:400]}\"\"\"
Responda APENAS com o título, sem pontuação final. Exemplo: Contratação CLC Dispensa"""
    response = client.models.generate_content(
        model=GEMINI_STRUCTURED_MODEL, contents=prompt
    )
    title = (response.text or "").strip().strip(".").strip()
    return title[:80] if title else f"Procedimento {area}"


def _crystallize_task(task_id: str, task_data: dict, db, api_key: str):
    """
    Cristaliza uma tarefa concluída no grafo:
    1. Constrói diário limpo
    2. Gera resumo do procedimento
    3. Dual-Pass → encontra ou cria Nó Conceitual
    4. Atualiza centróide do nó
    5. Grava concept_node_id + kg_crystallized na tarefa
    """
    area = task_data.get("area_tematica") or "GERAL"
    clean_diary = _build_clean_diary(task_data)

    client = _gemini_client(api_key)

    # ── Resumo do procedimento ────────────────────────────────────────────────
    summary_prompt = f"""Você é um analista de processos operacionais do sistema Hermes.
Leia o diário de bordo abaixo e redija um resumo técnico conciso (máximo 5 frases) descrevendo:
1. O que foi feito (procedimento operatório)
2. Decisões-chave tomadas
3. Resultado final

Diário:
{clean_diary[:4000]}

Resumo:"""

    summary_response = client.models.generate_content(
        model=GEMINI_STRUCTURED_MODEL, contents=summary_prompt
    )
    summary = (summary_response.text or "").strip()
    if not summary:
        summary = f"Tarefa concluída: {task_data.get('titulo', task_id)}"

    # ── Embedding do resumo ───────────────────────────────────────────────────
    embedding = _get_embedding(summary, api_key)

    # ── Dual-Pass ─────────────────────────────────────────────────────────────
    node_id, peso = _dual_pass_find_or_create_node(
        db, api_key, summary, embedding, area, task_id
    )

    # ── Atualiza centróide e lista de tarefas do nó ───────────────────────────
    node_ref = db.collection("knowledge_nodes").document(node_id)
    node_doc = node_ref.get()
    if node_doc.exists:
        nd = node_doc.to_dict() or {}
        old_emb = nd.get("embedding", embedding)
        n = nd.get("n_tasks", 0)
        new_centroid = _update_centroid(old_emb, n, embedding)
        existing_ids = nd.get("task_ids", [])
        if task_id not in existing_ids:
            existing_ids.append(task_id)
        node_ref.update({
            "embedding": Vector(list(map(float, new_centroid))),
            "n_tasks": n + 1,
            "task_ids": existing_ids,
            "resumo": summary[:600],
            "data_atualizacao": datetime.now(timezone.utc).isoformat(),
        })

    # ── Grava aresta na coleção knowledge_edges ───────────────────────────────
    edge_id = f"{task_id}_{node_id}"
    db.collection("knowledge_edges").document(edge_id).set({
        "task_id": task_id,
        "node_id": node_id,
        "peso_semantico": peso,
        "data_conclusao": task_data.get("data_conclusao") or datetime.now(timezone.utc).date().isoformat(),
    })

    # ── Marca a tarefa como cristalizada ─────────────────────────────────────
    db.collection("tarefas").document(task_id).update({
        "concept_node_id": node_id,
        "kg_crystallized": True,
    })

    print(f"[KG Fase2] Tarefa {task_id} cristalizada -> no {node_id} (peso={peso})")

    # ── Módulo de Artefatos: agrega e despacha Pub/Sub ────────────────────────
    import os as _os
    artefatos = _aggregate_artefatos(task_data, db)
    if artefatos:
        db.collection("tarefas").document(task_id).update({"artefatos_kg": artefatos})
        project_id = _os.environ.get("GCLOUD_PROJECT", "gestao-hermes")
        try:
            _dispatch_artefatos_pubsub(project_id, task_id, artefatos)
        except Exception as exc:
            print(f"[KG Artefato] Erro ao despachar Pub/Sub para {task_id}: {exc}")


@firestore_fn.on_document_updated(document="tarefas/{taskId}", memory=options.MemoryOption.GB_1, timeout_sec=300)
def on_tarefa_concluida_kg(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]]):
    """
    Fase 2 — Cristalização: disparada quando uma tarefa muda para 'concluído'.
    Executa apenas uma vez (guard: kg_crystallized).
    """
    if not event.data.after or not event.data.after.exists:
        return

    before = (event.data.before.to_dict() if event.data.before and event.data.before.exists else {}) or {}
    after = event.data.after.to_dict() or {}

    # Guard: só processa a transição para 'concluído' e apenas uma vez
    if after.get("status") != "concluído":
        return
    if before.get("status") == "concluído":
        return
    if after.get("kg_crystallized"):
        return
    if after.get("area_tematica") in ("SISTEMAS", None, ""):
        return

    task_id = event.params["taskId"]
    db = _get_db()
    api_key = _get_api_key(db)
    if not api_key:
        print(f"[KG Fase2] API key não encontrada para tarefa {task_id}")
        return

    try:
        _crystallize_task(task_id, after, db, api_key)
    except Exception as e:
        import traceback
        print(f"[KG Fase2] Erro ao cristalizar tarefa {task_id}: {traceback.format_exc()}")


# ─── Módulo de Artefatos: worker Pub/Sub ─────────────────────────────────────

@pubsub_fn.on_message_published(
    topic=ARTEFATO_PUBSUB_TOPIC,
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
)
def processar_artefato_kg(event: pubsub_fn.CloudEvent[pubsub_fn.MessagePublishedData]):
    """
    Worker Pub/Sub — processa um artefato de Tarefa ou do Acervo Global.

    Bifurcação por campo 'origem':
      'tarefa' (padrão): atualiza artefatos_kg[idx] na tarefa + grava em indice_artefatos.
      'acervo': grava/atualiza acervo_global + grava em indice_artefatos, com tag assignment.

    Fluxo comum:
      1. Valida MIME type (aceita apenas tríade corporativa)
      2. Baixa o arquivo (Drive OAuth ou URL pública) — Fail-Silently se inacessível
      3. Extrai texto via Gemini (até ARTEFATO_CHAR_CAP chars)
      4. Gera resumo_semantico em parágrafo denso
      5. Gera embedding do resumo
      6. Despacho final conforme origem

    Tópico: hermes-artefato-kg
    """
    import base64 as _b64
    import json

    # ── Decodifica mensagem ───────────────────────────────────────────────────
    try:
        # No Gen 2, event.data.message.data contém os bytes em base64
        msg_bytes = event.data.message.data
        if msg_bytes:
            # O SDK pode já entregar os bytes decodificados ou em base64 string
            if isinstance(msg_bytes, str):
                raw = _b64.b64decode(msg_bytes).decode("utf-8")
            else:
                raw = msg_bytes.decode("utf-8")
        else:
            # Fallback para .text se disponível (compatibilidade)
            raw = getattr(event.data.message, "text", "")

        if not raw:
            print("[KG Artefato] Erro: Mensagem Pub/Sub vazia.")
            return

        data = json.loads(raw)
    except Exception as exc:
        print(f"[KG Artefato] Erro ao decodificar mensagem Pub/Sub: {exc}")
        return

    origem        = data.get("origem", "tarefa")  # backward compat: default 'tarefa'
    url           = data.get("url", "")
    tipo_mime     = data.get("tipo_mime", "")
    drive_file_id = data.get("drive_file_id", "")
    nome          = data.get("nome", "artefato")

    # ── Campos específicos por origem ─────────────────────────────────────────
    if origem == "tarefa":
        task_id  = data.get("task_id", "")
        idx      = data.get("artefato_idx")
        acervo_id = None
        if not task_id or idx is None:
            print("[KG Artefato] Mensagem invalida: task_id ou artefato_idx ausente")
            return
    else:
        acervo_id = data.get("acervo_id", "")
        task_id   = None
        idx       = None
        if not acervo_id:
            print("[KG Artefato] Mensagem invalida: acervo_id ausente")
            return

    db = _get_db()
    api_key = _get_api_key(db)
    if not api_key:
        print(f"[KG Artefato] API key ausente — {origem} {task_id or acervo_id}")
        return

    # ── Valida MIME type ─────────────────────────────────────────────────────
    if tipo_mime not in SUPPORTED_MIMES:
        if origem == "tarefa":
            _update_artefato_status(db, task_id, idx, "ignorado_mime", None)
        else:
            _update_acervo_doc(db, acervo_id, "ignorado_mime", None, [], [])
        print(f"[KG Artefato] MIME ignorado ({tipo_mime}): {nome}")
        return

    # ── Download ─────────────────────────────────────────────────────────────
    try:
        if drive_file_id:
            file_bytes = _download_from_drive(drive_file_id, db)
        else:
            fid = _extract_drive_id(url)
            if fid:
                file_bytes = _download_from_drive(fid, db)
            else:
                import requests as _req
                resp = _req.get(url, timeout=30)
                resp.raise_for_status()
                file_bytes = resp.content
    except Exception as exc:
        if origem == "tarefa":
            _update_artefato_status(db, task_id, idx, "falha_acesso", None)
        else:
            _update_acervo_doc(db, acervo_id, "falha_acesso", None, [], [])
        print(f"[KG Artefato] Falha no download ({nome}): {exc}")
        return

    # ── Extração de texto via Gemini ─────────────────────────────────────────
    try:
        client = _gemini_client(api_key)
        if _is_docx(nome, tipo_mime):
            texto = _extract_docx_text(file_bytes)
        else:
            from google.genai import types
            extract_resp = generate_content_logged(
                client,
                model=GEMINI_DOCUMENT_MODEL,
                contents=[
                    "Extraia todo o texto relevante deste documento. "
                    "Ignore cabecalhos repetitivos, rodapes e numeracao de paginas.",
                    types.Part.from_bytes(data=file_bytes, mime_type=tipo_mime),
                ],
                feature="knowledge_graph.artifact_text_extraction",
                db=db,
            )
            texto = (extract_resp.text or "").strip()
    except Exception as exc:
        if origem == "tarefa":
            _update_artefato_status(db, task_id, idx, "falha_acesso", None)
        else:
            _update_acervo_doc(db, acervo_id, "falha_acesso", None, [], [])
        print(f"[KG Artefato] Falha na extracao de texto ({nome}): {exc}")
        return

    # ── Token cap ────────────────────────────────────────────────────────────
    truncado  = len(texto) > ARTEFATO_CHAR_CAP
    texto_cap = texto[:ARTEFATO_CHAR_CAP]

    # ── Resumo semântico ─────────────────────────────────────────────────────
    try:
        summary_resp = generate_content_logged(
            client,
            model=GEMINI_DOCUMENT_MODEL,
            contents=(
                f"Voce e um analista de documentos corporativos.\n"
                f"Resuma o objetivo e os principais parametros deste documento "
                f"em um paragrafo denso (maximo 5 frases). "
                f"Seja objetivo e tecnico. Inclua: tipo do documento, "
                f"seu proposito central e dados-chave.\n\n"
                f"Documento: \"{nome}\"\nConteudo:\n{texto_cap}\n\nResumo:"
            ),
            feature="knowledge_graph.artifact_summary",
            db=db,
        )
        resumo = (summary_resp.text or "").strip()
    except Exception as exc:
        if origem == "tarefa":
            _update_artefato_status(db, task_id, idx, "falha_acesso", None)
        else:
            _update_acervo_doc(db, acervo_id, "falha_acesso", None, [], [])
        print(f"[KG Artefato] Falha ao sumarizar ({nome}): {exc}")
        return

    status_final = "falha_limite_tamanho" if truncado else "concluido"

    # ── Embedding do resumo ───────────────────────────────────────────────────
    emb: list = []
    try:
        emb = _get_embedding(resumo, api_key)
    except Exception as exc:
        print(f"[KG Artefato] Falha ao gerar embedding ({nome}): {exc}")

    # ── Despacho final por origem ─────────────────────────────────────────────
    if origem == "tarefa":
        _update_artefato_status(db, task_id, idx, status_final, resumo)
        # Herda tags da tarefa para o índice vetorial
        tags: list = []
        try:
            snap = db.collection("tarefas").document(task_id).get()
            tags = (snap.to_dict() or {}).get("kg_tags", []) if snap.exists else []
        except Exception:
            pass
        file_search_payload = _index_file_search_document(
            db, api_key, file_bytes, nome, tipo_mime, "tarefa", tags, task_id=task_id
        )
        if emb:
            _write_to_indice_artefatos(
                db, nome, url, tipo_mime, resumo, emb, tags, "tarefa",
                task_id=task_id, texto_bruto=texto_cap, file_search=file_search_payload,
            )
    else:  # acervo
        existing_tags = _fetch_tag_vocabulary(db)
        tags = _assign_acervo_tags(db, api_key, nome, texto_cap, existing_tags)
        file_search_payload = _index_file_search_document(
            db, api_key, file_bytes, nome, tipo_mime, "acervo", tags, acervo_id=acervo_id
        )
        extra_update = {"file_search": file_search_payload} if file_search_payload else None
        _update_acervo_doc(db, acervo_id, status_final, resumo, tags, emb, extra=extra_update)
        if emb:
            _write_to_indice_artefatos(
                db, nome, url, tipo_mime, resumo, emb, tags, "acervo",
                acervo_id=acervo_id, texto_bruto=texto_cap, file_search=file_search_payload,
            )
        # Sincroniza novas tags no vocabulário centralizado
        if tags:
            try:
                db.collection("system").document("tag_vocabulary").set(
                    {"tags": ArrayUnion(tags)}, merge=True
                )
            except Exception as exc:
                print(f"[KG Acervo] Erro ao sync tag_vocabulary: {exc}")

    print(f"[KG Artefato] OK — {nome} [{status_final}] ({origem})")


# ─── Acervo Global: Cron Job de ingestão ─────────────────────────────────────

def executar_monitoramento_acervo_global() -> None:
    """
    Core function — monitora a Pasta de Deságue no Google Drive.
    """
    import os as _os
    from googleapiclient.discovery import build

    db = _get_db()

    # ── Lê configuração ───────────────────────────────────────────────────────
    settings_doc = db.collection("system").document("settings").get()
    if not settings_doc.exists:
        print("[Acervo] system/settings não encontrado — cron abortado")
        return
    settings_data = settings_doc.to_dict() or {}
    folder_id = settings_data.get("drop_folder_id", "")
    if not folder_id:
        print("[Acervo] drop_folder_id não configurado — cron abortado")
        return

    # ── Credenciais Drive ─────────────────────────────────────────────────────
    try:
        creds = _get_google_creds_kg(db)
    except Exception as exc:
        print(f"[Acervo] Erro ao obter credenciais Drive: {exc}")
        return

    service = build("drive", "v3", credentials=creds)

    # ── Lista todos os arquivos na pasta (paginação completa) ─────────────────
    all_files: list = []
    page_token: Optional[str] = None
    while True:
        kwargs_api: dict = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "nextPageToken, files(id, name, mimeType)",
            "pageSize": 1000,
        }
        if page_token:
            kwargs_api["pageToken"] = page_token
        try:
            resp = service.files().list(**kwargs_api).execute()
        except Exception as exc:
            print(f"[Acervo] Erro ao listar Drive: {exc}")
            return
        all_files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    if not all_files:
        print("[Acervo] Pasta de Deságue vazia — nada a processar")
        return

    print(f"[Acervo] {len(all_files)} arquivo(s) encontrado(s) na pasta")

    # ── Map de arquivos conhecidos: drive_file_id -> {acervo_id, status} ─────
    acervo_map: dict = {}
    for doc in db.collection("acervo_global").stream():
        d = doc.to_dict() or {}
        fid = d.get("drive_file_id")
        if fid:
            acervo_map[fid] = {
                "id": doc.id,
                "status": d.get("status_indexacao", "pendente")
            }

    # ── Filtra e despacha ─────────────────────────────────────────────────────
    project_id = _os.environ.get("GCLOUD_PROJECT", "gestao-hermes")
    novos = 0
    reprocessados = 0

    for f in all_files:
        fid  = f.get("id", "")
        nome = f.get("name", "arquivo")
        mime = f.get("mimeType", "")
        if not fid:
            continue

        url = f"https://drive.google.com/file/d/{fid}/view"

        # Se já existe no acervo_global
        if fid in acervo_map:
            info = acervo_map[fid]
            # Se não está concluído nem ignorado propositalmente, tenta re-despachar
            if info["status"] not in ("concluido", "ignorado_mime"):
                # Já existe mas está travado ou falhou? Re-despacha para o Worker Pub/Sub
                try:
                    # Reseta status para pendente se não estiver
                    if info["status"] != "pendente":
                        db.collection("acervo_global").document(info["id"]).update({
                            "status_indexacao": "pendente"
                        })
                    _dispatch_acervo_pubsub(project_id, info["id"], url, mime, fid, nome)
                    reprocessados += 1
                except Exception as exc:
                    print(f"[Acervo] Erro ao re-despachar {nome}: {exc}")
            continue

        # Novo documento: cria registro e despacha
        acervo_id = str(uuid.uuid4())[:16]
        try:
            db.collection("acervo_global").document(acervo_id).set({
                "nome": nome,
                "url": url,
                "tipo_mime": mime,
                "drive_file_id": fid,
                "resumo_semantico": None,
                "tags": [],
                "status_indexacao": "pendente",
                "indexed_at": firestore.SERVER_TIMESTAMP,
            })
            _dispatch_acervo_pubsub(project_id, acervo_id, url, mime, fid, nome)
            novos += 1
        except Exception as exc:
            print(f"[Acervo] Erro ao processar novo arquivo {nome}: {exc}")

    print(f"[Acervo] Monitoramento concluído. Novos: {novos}, Re-despachados: {reprocessados}")

    print(f"[Acervo] {novos} arquivo(s) novo(s) despachados para indexação")


@scheduler_fn.on_schedule(
    schedule="every 15 minutes",
    memory=options.MemoryOption.MB_512,
    timeout_sec=540,
)
def monitorar_acervo_global(*args, **kwargs) -> None:
    """
    Cron Job — monitora a Pasta de Deságue no Google Drive a cada 15 minutos.
    """
    executar_monitoramento_acervo_global()


# ─── RAG: extração com time decay + circuit breaker ──────────────────────────

def _time_decay(data_conclusao: str) -> float:
    """
    Calcula o fator de decaimento: e^(-0.001 * dias_desde_conclusao).
    Marco zero: data_conclusao. Calculado em memória, sem escrita no banco.
    """
    try:
        conclusion = datetime.fromisoformat(data_conclusao.replace("Z", "+00:00")).date()
        today = datetime.now(timezone.utc).date()
        days = max(0, (today - conclusion).days)
        return math.exp(-LAMBDA_DECAY * days)
    except Exception:
        return 1.0


def extract_kg_rag_context(
    db,
    api_key: str,
    area_tematica: str,
    tags: list[str],
    top_n: int = TOP_N_NODES,
    token_limit: int = TOKEN_SAFETY_LIMIT,
    kg_token_limit: int = KG_TOKEN_LIMIT,
    acervo_token_limit: int = ACERVO_TOKEN_LIMIT,
) -> tuple[list[dict], str]:
    """
    Extrai contexto RAG híbrido para uma nova tarefa.

    Dois eixos em paralelo:
      A) Relacional (Single-hop): Nós Conceituais do KG por área (A Prática) — até kg_token_limit.
      B) Vetorial (Similarity Search): indice_artefatos via Firestore KNN (A Teoria) — até acervo_token_limit.

    Retorna:
      (nodes_payload, formatted_context_string)

    nodes_payload: lista de dicts com {node_id, titulo, resumo, score, tasks}
    formatted_context_string: string pronta para injetar no prompt do Copiloto
      com marcadores de citação [1], [2]… e bloco condicional de conflito.
    """
    # ── A) Busca relacional: Nós Conceituais da mesma área ────────────────────
    nodes_in_area = []
    nodes_stream = (
        db.collection("knowledge_nodes")
        .where("area_tematica", "==", area_tematica)
        .stream()
    )
    for ndoc in nodes_stream:
        nd = ndoc.to_dict() or {}
        nodes_in_area.append({"id": ndoc.id, **nd})

    candidates: list[dict] = []
    if nodes_in_area:
        # ── Scoring: peso semântico × time decay + bônus de tags ──────────────
        tag_set = set(t.lower() for t in (tags or []))
        scored = []
        for node in nodes_in_area:
            edges = (
                db.collection("knowledge_edges")
                .where("node_id", "==", node["id"])
                .stream()
            )
            edge_list = [e.to_dict() for e in edges]
            if not edge_list:
                continue

            avg_peso = sum(e.get("peso_semantico", 0.7) for e in edge_list) / len(edge_list)
            dates = [e.get("data_conclusao", "") for e in edge_list if e.get("data_conclusao")]
            decay = _time_decay(max(dates)) if dates else 1.0
            node_text = (node.get("titulo", "") + " " + node.get("resumo", "")).lower()
            tag_bonus = sum(0.05 for t in tag_set if t in node_text)
            score = avg_peso * decay + tag_bonus

            scored.append({
                "node_id": node["id"],
                "titulo": node.get("titulo", ""),
                "resumo": node.get("resumo", ""),
                "score": round(score, 5),
                "n_tasks": node.get("n_tasks", 0),
                "task_ids": node.get("task_ids", []),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        candidates = scored[:top_n]

        # ── Circuit Breaker KG: remove menor rank até caber em kg_token_limit ─
        def _kg_tokens(nodes: list[dict]) -> int:
            return sum(_estimate_tokens(n.get("resumo", "")) for n in nodes)

        while len(candidates) > 1 and _kg_tokens(candidates) > kg_token_limit:
            candidates.pop()

    # ── B) Busca vetorial: Acervo Global via Firestore KNN ────────────────────
    acervo_items: list[dict] = []
    acervo_erro: str | None = None
    try:
        # RETRIEVAL_QUERY (assimétrico): obrigatório para queries, nunca RETRIEVAL_DOCUMENT
        query_text = f"área: {area_tematica}. contexto: {', '.join(tags or [])}".lower()
        query_emb = _get_embedding(query_text, api_key, task_type="RETRIEVAL_QUERY")

        # find_nearest só existe em CollectionReference — nunca encadeie .where() antes
        acervo_stream = (
            db.collection("indice_artefatos")
            .find_nearest(
                vector_field="embedding",
                query_vector=Vector(query_emb),   # ← wrapper obrigatório
                distance_measure=DistanceMeasure.COSINE,
                limit=5,
            )
            .get()
        )
        for adoc in acervo_stream:
            ad = adoc.to_dict() or {}
            if ad.get("resumo_semantico"):
                acervo_items.append(ad)

        # Circuit Breaker Acervo: descarta menor distância (último na lista KNN) primeiro
        while acervo_items:
            total = sum(_estimate_tokens(a.get("resumo_semantico", "")) for a in acervo_items)
            if total <= acervo_token_limit:
                break
            acervo_items.pop()
    except Exception as exc:
        # Expõe o erro cru — o LLM deve reportar, não mascarar
        acervo_erro = f"[ERRO TÉCNICO FindNearest] {type(exc).__name__}: {exc}"
        print(acervo_erro)

    # ── Retorno antecipado se nenhum eixo retornou dados ─────────────────────
    if not candidates and not acervo_items and not acervo_erro:
        return [], ""

    # ── Formata o contexto ────────────────────────────────────────────────────
    lines = ["=== CONTEXTO OPERACIONAL DO GRAFO DE CONHECIMENTO ===", ""]

    # Eixo A: Nós Conceituais (A Prática)
    if candidates:
        lines.append("--- HISTÓRICO DE TAREFAS (A Prática) ---")
        lines.append("")
        for i, node in enumerate(candidates, 1):
            lines.append(
                f"[{i}] Nó: \"{node['titulo']}\" "
                f"(relevância: {node['score']:.2f}, baseado em {node['n_tasks']} tarefa(s))"
            )
            if node.get("resumo"):
                lines.append(f"    Procedimento: {node['resumo'][:400]}")

            artefato_items = _gather_artefatos_for_node(db, node.get("task_ids", []))
            if artefato_items:
                lines.append("    Artefatos produzidos/utilizados:")
                for art_nome, art_resumo in artefato_items:
                    lines.append(f"      • {art_nome}: {art_resumo[:200]}")

            lines.append("")

        lines.append(
            "Use marcadores [1], [2]… no texto da resposta para indicar a fonte de cada informação."
        )

    # Eixo B: Erro técnico do FindNearest — reportar literalmente ao LLM
    if acervo_erro:
        lines.append("")
        lines.append("--- ACERVO GLOBAL (Documentação e Manuais — A Teoria) ---")
        lines.append("")
        lines.append(f"⚠️ {acervo_erro}")
        lines.append(
            "INSTRUÇÃO: Reporte este erro LITERALMENTE ao usuário. "
            "Não tente responder a pergunta como se o Acervo estivesse disponível."
        )

    # Eixo B: Acervo Global (A Teoria) — bloco condicional
    if acervo_items:
        lines.append("")
        lines.append("--- ACERVO GLOBAL (Documentação e Manuais — A Teoria) ---")
        lines.append("")
        for i, item in enumerate(acervo_items, 1):
            ext = item.get("tipo_mime", "").split(".")[-1].upper() or "DOC"
            lines.append(f"[A{i}] {item.get('nome', 'Documento')} ({ext})")
            lines.append(f"    {item.get('resumo_semantico', '')[:300]}")
            lines.append("")

        lines.append(
            "INSTRUÇÕES DE CONFLITO: Você possui duas fontes de verdade. "
            "O [Histórico de Tarefas] representa como a equipe executa na prática. "
            "O [Acervo Global] representa documentação e manuais. "
            "Se houver divergência entre ambos, NÃO omita nenhuma. "
            "Apresente a divergência explicitamente e pergunte ao usuário qual caminho deseja seguir."
        )

    return candidates, "\n".join(lines)


# ─── HTTP: buscar_procedimento (tool calling do Copiloto) ─────────────────────

@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=120)
def buscar_procedimento(req: https_fn.CallableRequest):
    """
    Tool calling do Copiloto.
    Aceita query livre e retorna os nós mais relevantes para responder
    perguntas sobre procedimentos operacionais passados.

    Input:  { query: str, area_tematica?: str, top_n?: int }
    Output: { nodes: [...], context: str }
    """
    data = req.data
    query = (data.get("query") or "").strip()
    area = (data.get("area_tematica") or "").strip()
    top_n = min(int(data.get("top_n", TOP_N_NODES)), 10)

    if not query:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="query é obrigatório.",
        )

    db = _get_db()
    api_key = _get_api_key(db)
    if not api_key:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Chave Gemini não configurada.",
        )

    # Substituído pela implementação corrigida do Especialista GCP (ARTEFATO 2)
    from tools.busca_grafo import buscar_tarefas
    res = buscar_tarefas(query)
    
    if res.get("erro"):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=res["erro"],
        )
    
    resultados = res.get("resultados", [])
    
    # Formata contexto compatível com o retorno esperado
    lines = [f"Resultados para a busca (Grafo): \"{query}\"", ""]
    for i, r in enumerate(resultados, 1):
        lines.append(
            f"[{i}] \"{r['titulo']}\" | Status: {r['status']} | "
            f"Responsável: {r['responsavel']} | Data: {r['criado_em']}"
        )
        if r.get("descricao"):
            lines.append(f"    {r['descricao']}")
        lines.append("")

    return {
        "nodes": resultados, # Adaptado: retorna tarefas como se fossem nós
        "context": "\n".join(lines),
    }


# ─── HTTP: cristalização manual (migração e reteste) ─────────────────────────

@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=300)
def crystallize_task_manual(req: https_fn.CallableRequest):
    """
    Cristaliza manualmente uma tarefa já concluída.
    Útil para migração de tarefas históricas e reteste.

    Input:  { taskId: str, force?: bool }
    Output: { success: bool, node_id?: str }
    """
    task_id = (req.data.get("taskId") or "").strip()
    force = bool(req.data.get("force", False))

    if not task_id:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="taskId é obrigatório.",
        )

    db = _get_db()
    task_doc = db.collection("tarefas").document(task_id).get()
    if not task_doc.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND,
            message="Tarefa não encontrada.",
        )

    task_data = task_doc.to_dict() or {}

    if task_data.get("status") != "concluído":
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Apenas tarefas concluídas podem ser cristalizadas.",
        )

    if task_data.get("kg_crystallized") and not force:
        return {"success": True, "node_id": task_data.get("concept_node_id"), "already_done": True}

    api_key = _get_api_key(db)
    if not api_key:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Chave Gemini não configurada.",
        )

    try:
        _crystallize_task(task_id, task_data, db, api_key)
        updated = db.collection("tarefas").document(task_id).get().to_dict() or {}
        return {"success": True, "node_id": updated.get("concept_node_id")}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[KG Manual] Erro ao cristalizar {task_id}: {tb}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e),
        )


# ─── Smart Search (KnowledgeView 2.0) ────────────────────────────────────────

SMART_SEARCH_TOP_N = 10
SMART_SEARCH_KNN_CANDIDATES = 50  # candidatos vetoriais puros antes do post-filtering


def _normalize_search_text(value: str) -> str:
    """Normaliza texto para matching lexical tolerante a acentos e caixa."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_only.lower().strip()


def _extract_query_terms(query: str) -> list[str]:
    """Quebra a query em termos úteis para busca lexical complementar."""
    normalized = _normalize_search_text(query)
    return [term for term in re.findall(r"\w+", normalized) if len(term) >= 2]


def _score_artefato_lexical(ad: dict, query: str, terms: list[str]) -> float:
    """
    Complementa o KNN quando o embedding do resumo não captura nome do arquivo,
    siglas ou trechos literais relevantes para o usuário.
    """
    if not query:
        return 0.0

    normalized_query = _normalize_search_text(query)
    nome = _normalize_search_text(ad.get("nome", ""))
    resumo = _normalize_search_text(ad.get("resumo_semantico", ""))
    texto_bruto = _normalize_search_text(ad.get("texto_bruto", ""))
    tags = [_normalize_search_text(t) for t in (ad.get("tags") or []) if t]
    tags_text = " ".join(tags)
    corpus = " ".join(part for part in [nome, resumo, tags_text, texto_bruto] if part)

    if not corpus:
        return 0.0

    score = 0.0

    if normalized_query and normalized_query in nome:
        score += 12.0
    elif normalized_query and normalized_query in tags_text:
        score += 8.0
    elif normalized_query and normalized_query in resumo:
        score += 6.0
    elif normalized_query and normalized_query in texto_bruto:
        score += 4.0

    if terms:
        hits_nome = sum(1 for term in terms if term in nome)
        hits_tags = sum(1 for term in terms if term in tags_text)
        hits_resumo = sum(1 for term in terms if term in resumo)
        hits_texto = sum(1 for term in terms if term in texto_bruto)

        if hits_nome == len(terms):
            score += 8.0
        elif hits_nome:
            score += 3.0 + hits_nome

        if hits_tags:
            score += 2.5 + (hits_tags * 0.5)
        if hits_resumo:
            score += 2.0 + (hits_resumo * 0.4)
        if hits_texto:
            score += min(3.0, 0.3 * hits_texto)

        overlap = sum(1 for term in terms if term in corpus)
        score += overlap / max(len(terms), 1)

    return score


def _parse_iso_date(value) -> Optional[datetime]:
    """Tolerante a None, Timestamp do Firestore, string ISO ou datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _in_date_window(
    candidate: Optional[datetime],
    start: Optional[datetime],
    end: Optional[datetime],
) -> bool:
    """True se a data cair na janela (bordas inclusivas). Sem data → passa (não penaliza)."""
    if candidate is None:
        return True
    if start and candidate < start:
        return False
    if end and candidate > end:
        return False
    return True


def _tags_match(item_tags: list, required: set[str]) -> bool:
    """Interseção: requer que pelo menos uma tag pedida esteja presente (case-insensitive)."""
    if not required:
        return True
    item_set = {str(t).strip().lower() for t in (item_tags or []) if t}
    return bool(item_set & required)


def _route_intent(query: str, api_key: str) -> str:
    """Roteia para BUSCA_SIMPLES ou SINTESE_PROFUNDA via LLM. Fallback: BUSCA_SIMPLES."""
    client = _gemini_client(api_key)
    prompt = f"""Classifique a intenção da consulta do usuário em UMA das duas categorias:

BUSCA_SIMPLES — o usuário quer encontrar documentos, arquivos ou tarefas específicas (palavras-chave, títulos, nomes). Exemplos: "Relatórios 2025", "contrato PNAE", "dispensa de licitação".

SINTESE_PROFUNDA — o usuário quer uma explicação, um passo-a-passo, um "como fazer", um resumo ou uma comparação que exige raciocínio sobre múltiplas fontes. Exemplos: "Como elaboramos o relatório de gestão de 2025?", "Qual o procedimento para dispensa?", "O que decidimos sobre o edital X?".

Consulta: "{query}"

Responda APENAS com uma das duas palavras: BUSCA_SIMPLES ou SINTESE_PROFUNDA."""
    try:
        response = client.models.generate_content(
            model=GEMINI_STRUCTURED_MODEL, contents=prompt
        )
        raw = (response.text or "").strip().upper()
        if "SINTESE" in raw:
            return "SINTESE_PROFUNDA"
        return "BUSCA_SIMPLES"
    except Exception as exc:
        print(f"[smart_search_kg] Falha no roteador: {exc} — fallback BUSCA_SIMPLES")
        return "BUSCA_SIMPLES"


def _search_nodes(
    db,
    query_emb: list[float],
    area_tematica: Optional[str],
    tags_set: set[str],
    date_start: Optional[datetime],
    date_end: Optional[datetime],
) -> list[dict]:
    """Busca em knowledge_nodes: filtra em memória (área, tags via task_ids, data) e ranqueia por similaridade."""
    base = db.collection("knowledge_nodes")
    if area_tematica:
        stream = base.where("area_tematica", "==", area_tematica).stream()
    else:
        stream = base.stream()

    scored: list[dict] = []
    for ndoc in stream:
        nd = ndoc.to_dict() or {}
        node_emb = nd.get("embedding")
        if not node_emb:
            continue

        # Filtro de data: usa data_atualizacao (fallback data_criacao)
        node_date = _parse_iso_date(nd.get("data_atualizacao") or nd.get("data_criacao"))
        if not _in_date_window(node_date, date_start, date_end):
            continue

        # Filtro de tags: nó não tem tags próprias; reusa interseção com texto do nó
        # OU herda tags das tarefas vinculadas (consulta pontual, só se há filtro)
        if tags_set:
            node_text = (nd.get("titulo", "") + " " + nd.get("resumo", "")).lower()
            direct_match = any(t in node_text for t in tags_set)
            if not direct_match:
                # Busca tags das tarefas vinculadas como fallback
                inherited: set[str] = set()
                for tid in (nd.get("task_ids") or [])[:5]:  # amostra
                    try:
                        tdoc = db.collection("tarefas").document(tid).get()
                        if tdoc.exists:
                            for t in (tdoc.to_dict() or {}).get("kg_tags", []):
                                inherited.add(str(t).strip().lower())
                    except Exception:
                        continue
                if not (inherited & tags_set):
                    continue

        sim = _cosine_similarity(query_emb, node_emb)
        scored.append({
            "id": ndoc.id,
            "type": "node",
            "title": nd.get("titulo", ""),
            "snippet": (nd.get("resumo") or "")[:400],
            "resumo_semantico": nd.get("resumo") or "",
            "tags": [],
            "date": (nd.get("data_atualizacao") or nd.get("data_criacao") or ""),
            "area_tematica": nd.get("area_tematica", ""),
            "task_ids": nd.get("task_ids", []),
            "score": sim,
            "n_tasks": nd.get("n_tasks", 0),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def _search_artefatos(
    db,
    query: str,
    query_emb: list[float],
    tags_set: set[str],
    date_start: Optional[datetime],
    date_end: Optional[datetime],
    tipo_filter: str,
) -> list[dict]:
    """
    Busca vetorial em indice_artefatos com post-filtering em memória.
    Usa find_nearest com limit maior e aplica filtros locais — evita Composite Vector Indexes no GCP.
    """
    lexical_terms = _extract_query_terms(query)
    results_by_id: dict[str, dict] = {}

    try:
        stream = (
            db.collection("indice_artefatos")
            .find_nearest(
                vector_field="embedding",
                query_vector=Vector(query_emb),
                distance_measure=DistanceMeasure.COSINE,
                limit=SMART_SEARCH_KNN_CANDIDATES,
            )
            .get()
        )
    except Exception as exc:
        print(f"[smart_search_kg] FindNearest falhou: {exc}")
        stream = []

    for adoc in stream:
        ad = adoc.to_dict() or {}
        if not ad.get("resumo_semantico"):
            continue

        if not _tags_match(ad.get("tags", []), tags_set):
            continue

        art_date = _parse_iso_date(ad.get("indexed_at"))
        if not _in_date_window(art_date, date_start, date_end):
            continue

        results_by_id[adoc.id] = {
            "id": adoc.id,
            "type": "artefato",
            "title": ad.get("nome", "Documento"),
            "snippet": (ad.get("resumo_semantico") or "")[:400],
            "resumo_semantico": ad.get("resumo_semantico") or "",
            "tags": ad.get("tags", []),
            "date": ad.get("indexed_at", ""),
            "area_tematica": "",
            "drive_url": ad.get("url", ""),
            "drive_file_id": _extract_drive_id(ad.get("url", "")),
            "tipo_mime": ad.get("tipo_mime", ""),
            "origem": ad.get("origem", ""),
            "task_id": ad.get("task_id", ""),
            "acervo_id": ad.get("acervo_id", ""),
            "file_search": ad.get("file_search"),
            "score": 20.0,
        }

    try:
        lexical_stream = db.collection("indice_artefatos").stream()
    except Exception as exc:
        print(f"[smart_search_kg] Stream lexical de artefatos falhou: {exc}")
        lexical_stream = []

    for adoc in lexical_stream:
        ad = adoc.to_dict() or {}
        if not ad.get("resumo_semantico"):
            continue

        if not _tags_match(ad.get("tags", []), tags_set):
            continue

        art_date = _parse_iso_date(ad.get("indexed_at"))
        if not _in_date_window(art_date, date_start, date_end):
            continue

        lexical_score = _score_artefato_lexical(ad, query, lexical_terms)
        if lexical_score <= 0:
            continue

        if adoc.id in results_by_id:
            results_by_id[adoc.id]["score"] = max(
                results_by_id[adoc.id].get("score", 0.0),
                20.0 + lexical_score,
            )
            continue

        results_by_id[adoc.id] = {
            "id": adoc.id,
            "type": "artefato",
            "title": ad.get("nome", "Documento"),
            "snippet": (ad.get("resumo_semantico") or "")[:400],
            "resumo_semantico": ad.get("resumo_semantico") or "",
            "tags": ad.get("tags", []),
            "date": ad.get("indexed_at", ""),
            "area_tematica": "",
            "drive_url": ad.get("url", ""),
            "drive_file_id": _extract_drive_id(ad.get("url", "")),
            "tipo_mime": ad.get("tipo_mime", ""),
            "origem": ad.get("origem", ""),
            "task_id": ad.get("task_id", ""),
            "acervo_id": ad.get("acervo_id", ""),
            "file_search": ad.get("file_search"),
            "score": lexical_score,
        }

    filtered = list(results_by_id.values())
    filtered.sort(key=lambda x: x["score"], reverse=True)
    return filtered


def _serialize_date(value) -> str:
    """Converte Timestamp/datetime/string em ISO string para o payload JSON."""
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    # Firestore DatetimeWithNanoseconds possui isoformat
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _build_synthesis(
    query: str,
    results: list[dict],
    api_key: str,
) -> str:
    """Gera síntese em linguagem natural com citações [1], [2] mapeadas à ordem de `results`."""
    if not results:
        return ""

    fontes_lines: list[str] = []
    for i, r in enumerate(results, 1):
        tipo_label = "Nó Conceitual" if r["type"] == "node" else "Documento"
        fontes_lines.append(
            f"[{i}] {tipo_label}: \"{r['title']}\"\n    Resumo: {r['resumo_semantico'][:500]}"
        )
    fontes = "\n\n".join(fontes_lines)

    prompt = f"""Você é o motor de respostas do sistema Hermes. Responda à pergunta do usuário APENAS com base nas fontes abaixo.

PERGUNTA: "{query}"

FONTES DISPONÍVEIS:
{fontes}

REGRAS OBRIGATÓRIAS:
1. Redija uma resposta direta, técnica e objetiva (máximo 8 frases).
2. SEMPRE cite as fontes usando marcadores [1], [2], etc., exatamente como aparecem acima.
3. Cada afirmação substantiva deve ter pelo menos uma citação.
4. Se as fontes não cobrem a pergunta, diga isso explicitamente — NÃO invente.
5. Não repita os títulos das fontes como preâmbulo; vá direto à resposta.

Resposta:"""

    try:
        client = _gemini_client(api_key)
        response = client.models.generate_content(
            model=GEMINI_STRUCTURED_MODEL, contents=prompt
        )
        return (response.text or "").strip()
    except Exception as exc:
        print(f"[smart_search_kg] Falha na síntese: {exc}")
        return ""


def _extract_file_search_citations(response) -> list[dict]:
    """Extrai citações, páginas e metadados do grounding_metadata do File Search."""
    grounding = getattr(response, "grounding_metadata", None)
    if not grounding:
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            grounding = getattr(candidates[0], "grounding_metadata", None)
    chunks = getattr(grounding, "grounding_chunks", None) if grounding else None
    citations: list[dict] = []
    for idx, chunk in enumerate(chunks or [], 1):
        ctx = getattr(chunk, "retrieved_context", None)
        if not ctx:
            continue
        custom_metadata = []
        for item in getattr(ctx, "custom_metadata", None) or []:
            item_plain = _plain_genai_value(item)
            if isinstance(item_plain, dict):
                custom_metadata.append(item_plain)
        citations.append({
            "index": idx,
            "title": getattr(ctx, "title", "") or "",
            "uri": getattr(ctx, "uri", "") or "",
            "text": (getattr(ctx, "text", "") or "")[:1200],
            "page_number": getattr(ctx, "page_number", None),
            "media_id": getattr(ctx, "media_id", None),
            "file_search_store": getattr(ctx, "file_search_store", "") or "",
            "custom_metadata": custom_metadata,
        })
    return citations


def _build_file_search_metadata_filter(tags_set: set[str], tipo_filter: str) -> str:
    """Monta um filtro conservador de metadados para o File Search."""
    parts: list[str] = []
    if tags_set:
        tag = sorted(tags_set)[0].replace('"', '\\"')
        parts.append(f'primary_tag = "{tag}"')
    return " AND ".join(parts)


def _build_file_search_synthesis(
    query: str,
    api_key: str,
    tags_set: set[str],
    tipo_filter: str,
) -> Optional[dict]:
    """
    Consulta o Gemini File Search gerenciado para uma síntese com citações/páginas.

    Fallback silencioso: se o store ainda não existe ou a API falha, a síntese
    local baseada no Firestore segue funcionando.
    """
    try:
        db = _get_db()
        store_doc = db.collection("system").document("file_search").get()
        store_name = (store_doc.to_dict() or {}).get("store_name") if store_doc.exists else None
        if not store_name:
            return None

        from google.genai import types

        metadata_filter = _build_file_search_metadata_filter(tags_set, tipo_filter)
        file_search_args: dict = {"file_search_store_names": [store_name]}
        if metadata_filter:
            file_search_args["metadata_filter"] = metadata_filter

        prompt = f"""Voce e o motor de respostas do Hermes. Responda a pergunta do usuario usando somente os documentos recuperados pelo File Search.

Pergunta: {query}

Regras:
1. Seja direto, tecnico e objetivo.
2. Cite as fontes no texto quando a informacao vier de documento.
3. Se os documentos nao cobrirem a pergunta, diga isso explicitamente.
4. Nao invente numeros, datas, status ou obrigacoes."""

        client = _gemini_client(api_key)
        response = client.models.generate_content(
            model=FILE_SEARCH_QUERY_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        file_search=types.FileSearch(**file_search_args)
                    )
                ]
            ),
        )
        answer = (getattr(response, "text", "") or "").strip()
        citations = _extract_file_search_citations(response)
        if not answer and not citations:
            return None
        return {
            "synthesis": answer,
            "citations": citations,
            "store_name": store_name,
            "metadata_filter": metadata_filter,
        }
    except Exception as exc:
        print(f"[smart_search_kg] File Search indisponivel: {exc}")
        return None


@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.GB_1,
    timeout_sec=120,
)
def smart_search_kg(req: https_fn.CallableRequest):
    """
    Motor de respostas do KnowledgeView 2.0.

    Roteia a intenção (BUSCA_SIMPLES vs SINTESE_PROFUNDA), executa busca híbrida
    (Nós Conceituais + Acervo via KNN com post-filtering) e, se necessário,
    sintetiza a resposta com citações [1], [2].

    Input:
      {
        query: str,
        filtros?: {
          area_tematica?: str,
          tags?: list[str],
          data_inicio?: str (ISO),
          data_fim?: str (ISO),
          tipo?: "all" | "node" | "artefato"
        }
      }

    Output:
      {
        intent: "BUSCA_SIMPLES" | "SINTESE_PROFUNDA",
        synthesis?: str,
        results: list[{id, type, title, snippet, resumo_semantico, tags, date,
                       area_tematica, drive_url?, drive_file_id?, task_ids?, ...}]
      }
    """
    data = req.data or {}
    query = (data.get("query") or "").strip()
    if not query:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="query é obrigatório.",
        )

    filtros = data.get("filtros") or {}
    area_tematica = (filtros.get("area_tematica") or "").strip() or None
    tags_set = {str(t).strip().lower() for t in (filtros.get("tags") or []) if t}
    date_start = _parse_iso_date(filtros.get("data_inicio"))
    date_end = _parse_iso_date(filtros.get("data_fim"))
    tipo_filter = (filtros.get("tipo") or "all").lower()

    db = _get_db()
    api_key = _get_api_key(db)
    if not api_key:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Chave Gemini não configurada.",
        )

    # ── Passo 1: Roteador de intenção ─────────────────────────────────────────
    intent = _route_intent(query, api_key)

    # ── Passo 2: Busca híbrida ────────────────────────────────────────────────
    try:
        query_emb = _get_embedding(query, api_key, task_type="RETRIEVAL_QUERY")
    except Exception as exc:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=f"Falha ao gerar embedding da query: {exc}",
        )

    node_results: list[dict] = []
    artefato_results: list[dict] = []

    if tipo_filter in ("all", "node"):
        node_results = _search_nodes(
            db, query_emb, area_tematica, tags_set, date_start, date_end
        )
    if tipo_filter in ("all", "artefato"):
        artefato_results = _search_artefatos(
            db, query, query_emb, tags_set, date_start, date_end, tipo_filter
        )

    # Merge intercalado: prioriza melhores scores mantendo diversidade de tipos
    node_results.sort(key=lambda x: x["score"], reverse=True)
    merged: list[dict] = []
    i, j = 0, 0
    while len(merged) < SMART_SEARCH_TOP_N and (i < len(node_results) or j < len(artefato_results)):
        if i < len(node_results) and (j >= len(artefato_results) or len(merged) % 2 == 0):
            merged.append(node_results[i])
            i += 1
        elif j < len(artefato_results):
            merged.append(artefato_results[j])
            j += 1

    # Sanitiza o payload: remove campos internos e serializa datas
    for r in merged:
        r.pop("score", None)
        r["date"] = _serialize_date(r.get("date"))

    # ── Passo 3: Síntese condicional ──────────────────────────────────────────
    synthesis = ""
    file_search_payload = None
    if intent == "SINTESE_PROFUNDA" and merged:
        if tipo_filter in ("all", "artefato"):
            file_search_payload = _build_file_search_synthesis(
                query, api_key, tags_set, tipo_filter
            )
        if file_search_payload and file_search_payload.get("synthesis"):
            synthesis = file_search_payload["synthesis"]
        else:
            synthesis = _build_synthesis(query, merged, api_key)

    response: dict = {
        "intent": intent,
        "results": merged,
    }
    if synthesis:
        response["synthesis"] = synthesis
    if file_search_payload:
        response["file_search"] = file_search_payload

    return response


@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.MB_256,
    timeout_sec=30,
)
def get_artefato_raw_text(req: https_fn.CallableRequest):
    """
    Lazy-load do texto bruto de um item (Raio-X da IA).

    Input:  { id: str, tipo: "node" | "artefato" }
    Output: { texto_bruto: str, truncated: bool }

    Para 'node': retorna o resumo técnico (nós não guardam texto bruto).
    Para 'artefato': lê `texto_bruto` de indice_artefatos. Entradas antigas sem
    esse campo retornam string vazia com aviso em `texto_bruto`.
    """
    data = req.data or {}
    item_id = (data.get("id") or "").strip()
    tipo = (data.get("tipo") or "").strip().lower()

    if not item_id or tipo not in ("node", "artefato"):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="id e tipo ('node' | 'artefato') são obrigatórios.",
        )

    db = _get_db()

    if tipo == "node":
        snap = db.collection("knowledge_nodes").document(item_id).get()
        if not snap.exists:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND,
                message="Nó Conceitual não encontrado.",
            )
        nd = snap.to_dict() or {}
        return {
            "texto_bruto": nd.get("resumo") or "",
            "truncated": False,
        }

    # tipo == "artefato"
    snap = db.collection("indice_artefatos").document(item_id).get()
    if not snap.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND,
            message="Artefato não encontrado no índice.",
        )
    ad = snap.to_dict() or {}
    texto = ad.get("texto_bruto") or ""
    if not texto:
        return {
            "texto_bruto": "",
            "truncated": False,
            "aviso": "Este artefato foi indexado antes da ativação do Raio-X. Reprocesse para disponibilizar o texto bruto.",
        }

    truncated = len(texto) > ARTEFATO_CHAR_CAP
    return {
        "texto_bruto": texto[:ARTEFATO_CHAR_CAP],
        "truncated": truncated,
    }


@firestore_fn.on_document_written(document="tarefas/{taskId}", memory=options.MemoryOption.MB_512, timeout_sec=120)
def on_tarefa_written_extract_people(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]]):
    """
    Gatilho disparado em qualquer criação ou atualização de tarefa.
    Extrai nomes de pessoas mencionadas usando Gemini e registra as interações.
    """
    if not event.data or not event.data.after or not event.data.after.exists:
        return # Documento deletado, ignora.

    task_data = event.data.after.to_dict() or {}
    task_id = event.params["taskId"]
    
    # Ignora tarefas internas do sistema
    if task_data.get("area_tematica") == "SISTEMAS":
        return
        
    # Extrai o texto relevante para analisar
    titulo = task_data.get("titulo") or ""
    descricao = task_data.get("descricao") or ""
    
    # Processa os diários de bordo (acompanhamento)
    acompanhamentos = task_data.get("acompanhamento") or []
    diary_texts = []
    for entry in acompanhamentos:
        if isinstance(entry, dict):
            diary_texts.append(entry.get("nota") or "")
        else:
            diary_texts.append(str(entry))
    diary_content = "\n".join(diary_texts)
    
    full_text = f"Título: {titulo}\nDescrição: {descricao}\nDiário de Bordo:\n{diary_content}"
    
    # Para evitar execuções repetidas desnecessárias (otimização de custo/performance)
    import hashlib
    current_hash = hashlib.md5(full_text.encode('utf-8')).hexdigest()
    if task_data.get("last_processed_people_hash") == current_hash:
        return # Sem alteração no conteúdo relevante para pessoas
        
    db = _get_db()
    api_key = _get_api_key(db)
    if not api_key:
        print(f"[EXTRACAO PESSOAS] API key não encontrada para tarefa {task_id}")
        return
        
    # Chamamos o Gemini para extrair os nomes
    prompt = f"""Você é um assistente cognitivo especializado em análise de texto corporativo.
Sua tarefa é analisar o texto de uma tarefa (ações, descrições e diário de bordo) e identificar todos os nomes próprios de pessoas reais mencionadas.

Texto da Tarefa:
\"\"\"{full_text}\"\"\"

Regras de Extração:
1. Identifique apenas nomes de pessoas físicas reais (ex: "João Silva", "André", "Profa. Maria").
2. Ignore nomes de órgãos, empresas, siglas, cargos genéricos isolados ("o presidente", "a CLC") ou objetos.
3. Para cada pessoa identificada, extraia o fragmento de contexto mais relevante onde o nome foi mencionado (ex: "João entregou as certidões").
4. Se nenhuma pessoa for mencionada, retorne uma lista vazia.
5. Responda APENAS com um array JSON contendo objetos com os campos "nome" (apenas o nome da pessoa) e "contexto" (frase ou frase aproximada do texto).
Exemplo de retorno esperado:
[
  {{"nome": "João Silva", "contexto": "João Silva ficou responsável pelo pregão"}},
  {{"nome": "Carlos", "contexto": "Ligar para Carlos amanhã"}}
]

Sua resposta em JSON:"""

    try:
        client = _gemini_client(api_key)
        response = client.models.generate_content(
            model=GEMINI_STRUCTURED_MODEL, contents=prompt
        )
        raw_response = (response.text or "").strip()
        
        # Faz parse do JSON
        import re
        json_match = re.search(r'\[\s*\{.*\}\s*\]', raw_response, re.DOTALL)
        extracted_people = []
        if json_match:
            try:
                extracted_people = json.loads(json_match.group(0))
            except Exception as parse_err:
                print(f"[EXTRACAO PESSOAS] Falha no parse JSON via regex match: {parse_err}")
        else:
            # Tenta fazer o parse direto caso não tenha as tags markdown
            clean_raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_response, flags=re.IGNORECASE).strip()
            if clean_raw.startswith('[') and clean_raw.endswith(']'):
                try:
                    extracted_people = json.loads(clean_raw)
                except Exception as parse_err:
                    print(f"[EXTRACAO PESSOAS] Falha no parse JSON direto: {parse_err}")
                
        if not extracted_people:
            # Salva o hash para evitar reprocessar
            db.collection("tarefas").document(task_id).update({
                "last_processed_people_hash": current_hash
            })
            return
            
        now_str = datetime.now(timezone.utc).isoformat()
        
        # Processa cada pessoa identificada
        for p_info in extracted_people:
            p_name = p_info.get("nome", "").strip()
            p_context = p_info.get("contexto", "").strip()
            if not p_name:
                continue
                
            # Busca pessoa existente no Firestore pelo nome
            q_name = db.collection('perfil_pessoas').where('nome', '==', p_name).limit(1).get()
            pessoa_id = None
            
            if q_name:
                pessoa_id = q_name[0].id
            else:
                # Busca por similaridade simples
                all_people = db.collection('perfil_pessoas').limit(200).stream()
                best_match = None
                p_name_lower = p_name.lower()
                for p_doc in all_people:
                    p_data = p_doc.to_dict() or {}
                    db_name = (p_data.get('nome') or "").lower()
                    if db_name == p_name_lower or p_name_lower in db_name or db_name in p_name_lower:
                        best_match = p_doc.id
                        break
                if best_match:
                    pessoa_id = best_match
                    
            # Se não encontrou, cria um perfil provisório
            if not pessoa_id:
                initials = "".join([part[0].upper() for part in p_name.split() if part])[:2]
                colors = ["bg-indigo-500", "bg-purple-500", "bg-pink-500", "bg-rose-500", "bg-amber-500", "bg-emerald-500", "bg-teal-500", "bg-cyan-500", "bg-sky-500", "bg-blue-500"]
                import hashlib as pyhash
                color_idx = int(pyhash.md5(p_name.encode('utf-8')).hexdigest(), 16) % len(colors)
                avatar_color = colors[color_idx]
                
                new_ref = db.collection('perfil_pessoas').document()
                new_payload = {
                    "nome": p_name,
                    "email": "",
                    "telefone": "",
                    "tags": ['Extraído por IA'],
                    "origem": 'extracao_ia',
                    "avatar_color": avatar_color,
                    "avatar_initials": initials,
                    "data_criacao": now_str,
                    "data_atualizacao": now_str
                }
                new_ref.set(new_payload)
                pessoa_id = new_ref.id
                
            # Cria interacao única
            context_hash = hashlib.md5(p_context.encode('utf-8')).hexdigest()[:8]
            interacao_id = f"{task_id}_{pessoa_id}_{context_hash}"
            
            inter_ref = db.collection('interacoes_pessoas').document(interacao_id)
            if not inter_ref.get().exists:
                inter_ref.set({
                    "id": interacao_id,
                    "pessoa_id": pessoa_id,
                    "tarefa_id": task_id,
                    "tipo": 'mencao_diario' if 'diário' in p_context.lower() or 'diario' in p_context.lower() else 'mencao_tarefa',
                    "data": now_str,
                    "descricao": p_context[:1000],
                    "link_origem": f"/tarefas?id={task_id}",
                    "data_criacao": now_str
                })
                
        # Por fim, salva o hash processado na tarefa
        db.collection("tarefas").document(task_id).update({
            "last_processed_people_hash": current_hash
        })
        print(f"[EXTRACAO PESSOAS] Sucesso ao processar tarefa {task_id}. Pessoas identificadas: {len(extracted_people)}")
        
    except Exception as e:
        print(f"[EXTRACAO PESSOAS] Erro ao extrair nomes da tarefa {task_id}: {e}")
