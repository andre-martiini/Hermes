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
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from firebase_admin import firestore
from firebase_functions import firestore_fn, https_fn, options, pubsub_fn, scheduler_fn
from google.cloud.firestore_v1 import ArrayUnion
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure

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
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
})
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
    
    response = client.models.embed_content(
        model="gemini-embedding-001",  # Modelo atualizado recomendado
        contents=text[:8000],
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

    entries = sorted(
        task_data.get("acompanhamento", []),
        key=lambda e: e.get("data", ""),
    )
    for entry in entries:
        nota = (entry.get("nota") or "").strip()
        if not nota:
            continue
        if any(nota.startswith(prefix) for prefix in NOISE_PREFIXES):
            continue
        date_label = entry.get("data", "")
        try:
            date_label = datetime.fromisoformat(date_label).strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
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
    if n.endswith(".docx"): return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if n.endswith(".xlsx"): return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if n.endswith(".csv"):  return "text/csv"
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
    creds = Credentials(
        token=d.get("token"),
        refresh_token=d.get("refresh_token"),
        token_uri=d.get("token_uri"),
        client_id=d.get("client_id"),
        client_secret=d.get("client_secret"),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            db.collection("system").document("google_credentials").update(
                {"token": creds.token, "updated_at": firestore.SERVER_TIMESTAMP}
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
                    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif tipo in ("xlsx", "csv"):
                    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
) -> None:
    """Atualiza um documento acervo_global com o resultado da indexação."""
    update: dict = {"status_indexacao": status}
    if resumo is not None:
        update["resumo_semantico"] = resumo
    if tags:
        update["tags"] = tags
    if embedding:
        update["embedding"] = embedding
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
) -> None:
    """Grava entrada no índice vetorial unificado (indice_artefatos)."""
    doc_id = str(uuid.uuid4())[:16]
    entry: dict = {
        "nome": nome,
        "url": url,
        "tipo_mime": tipo_mime,
        "resumo_semantico": resumo,
        "embedding": embedding,
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
    db.collection("indice_artefatos").document(doc_id).set(entry)
    print(f"[KG IndiceArtefatos] Entrada gravada: {nome} ({origem})")


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
        model="gemini-3-flash-preview", contents=prompt
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
    """Publica uma mensagem única de acervo no tópico hermes-artefato-kg."""
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
    publisher.publish(topic_path, _json.dumps(msg).encode("utf-8"))


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
        model="gemini-3-flash-preview", contents=prompt
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
    Não acessa o diário (ainda vazio). Custo: 1 chamada LLM leve.
    """
    if not event.data or not event.data.exists:
        return

    task_data = event.data.to_dict() or {}
    task_id = event.params["taskId"]

    # Não processa tarefas de sistema ou já com tags
    if task_data.get("kg_tags"):
        return
    if task_data.get("area_tematica") in ("SISTEMAS", None, ""):
        return

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
            print(f"[KG Fase1] Tags geradas para {task_id}: {tags}")
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
            model="gemini-3-flash-preview", contents=prompt
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
        "embedding": embedding,
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
        model="gemini-3-flash-preview", contents=prompt
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
        model="gemini-3-flash-preview", contents=summary_prompt
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
            "embedding": new_centroid,
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
        raw = event.data.message.text
        if not raw:
            raw = _b64.b64decode(event.data.message.data).decode("utf-8")
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
        file_b64 = _b64.b64encode(file_bytes).decode("utf-8")
        extract_resp = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                "Extraia todo o texto relevante deste documento. "
                "Ignore cabecalhos repetitivos, rodapes e numeracao de paginas.",
                {"mime_type": tipo_mime, "data": file_b64},
            ],
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
        summary_resp = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=(
                f"Voce e um analista de documentos corporativos.\n"
                f"Resuma o objetivo e os principais parametros deste documento "
                f"em um paragrafo denso (maximo 5 frases). "
                f"Seja objetivo e tecnico. Inclua: tipo do documento, "
                f"seu proposito central e dados-chave.\n\n"
                f"Documento: \"{nome}\"\nConteudo:\n{texto_cap}\n\nResumo:"
            ),
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
        if emb:
            _write_to_indice_artefatos(
                db, nome, url, tipo_mime, resumo, emb, tags, "tarefa",
                task_id=task_id, texto_bruto=texto_cap,
            )
    else:  # acervo
        existing_tags = _fetch_tag_vocabulary(db)
        tags = _assign_acervo_tags(db, api_key, nome, texto_cap, existing_tags)
        _update_acervo_doc(db, acervo_id, status_final, resumo, tags, emb)
        if emb:
            _write_to_indice_artefatos(
                db, nome, url, tipo_mime, resumo, emb, tags, "acervo",
                acervo_id=acervo_id, texto_bruto=texto_cap,
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

@scheduler_fn.on_schedule(
    schedule="every 15 minutes",
    memory=options.MemoryOption.MB_512,
    timeout_sec=540,
)
def monitorar_acervo_global(event: scheduler_fn.ScheduledEvent) -> None:
    """
    Cron Job — monitora a Pasta de Deságue no Google Drive a cada 15 minutos.

    Fluxo:
      1. Lê drop_folder_id de system/settings
      2. Lista todos os arquivos na pasta via Drive API (com paginação nextPageToken)
      3. Cruza com drive_file_ids já em acervo_global para detectar apenas inéditos
      4. Cria doc pendente em acervo_global e despacha para hermes-artefato-kg
    """
    import os as _os
    import json as _json
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
        kwargs: dict = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "nextPageToken, files(id, name, mimeType)",
            "pageSize": 1000,
        }
        if page_token:
            kwargs["pageToken"] = page_token
        try:
            resp = service.files().list(**kwargs).execute()
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

    # ── Busca drive_file_ids já indexados (1 query por stream) ───────────────
    indexed_ids: set = set()
    for doc in db.collection("acervo_global").select(["drive_file_id"]).stream():
        fid = (doc.to_dict() or {}).get("drive_file_id", "")
        if fid:
            indexed_ids.add(fid)

    # ── Filtra e despacha apenas arquivos inéditos ────────────────────────────
    project_id = _os.environ.get("GCLOUD_PROJECT", "gestao-hermes")
    novos = 0
    for f in all_files:
        fid  = f.get("id", "")
        nome = f.get("name", "arquivo")
        mime = f.get("mimeType", "")

        if not fid or fid in indexed_ids:
            continue

        # Cria documento pendente em acervo_global antes de despachar
        acervo_id = str(uuid.uuid4())[:16]
        url = f"https://drive.google.com/file/d/{fid}/view"
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

        try:
            _dispatch_acervo_pubsub(project_id, acervo_id, url, mime, fid, nome)
            novos += 1
        except Exception as exc:
            print(f"[Acervo] Erro ao despachar {nome}: {exc}")

    print(f"[Acervo] {novos} arquivo(s) novo(s) despachados para indexação")


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
            model="gemini-3-flash-preview", contents=prompt
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
        return []

    filtered: list[dict] = []
    for adoc in stream:
        ad = adoc.to_dict() or {}
        if not ad.get("resumo_semantico"):
            continue

        # Filtro de tags
        if not _tags_match(ad.get("tags", []), tags_set):
            continue

        # Filtro de data
        art_date = _parse_iso_date(ad.get("indexed_at"))
        if not _in_date_window(art_date, date_start, date_end):
            continue

        filtered.append({
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
            # distance não é exposta pelo SDK por padrão; usamos a ordem retornada como score
            "score": 1.0,
        })

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
            model="gemini-3-flash-preview", contents=prompt
        )
        return (response.text or "").strip()
    except Exception as exc:
        print(f"[smart_search_kg] Falha na síntese: {exc}")
        return ""


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
            db, query_emb, tags_set, date_start, date_end, tipo_filter
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
    if intent == "SINTESE_PROFUNDA" and merged:
        synthesis = _build_synthesis(query, merged, api_key)

    response: dict = {
        "intent": intent,
        "results": merged,
    }
    if synthesis:
        response["synthesis"] = synthesis

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
