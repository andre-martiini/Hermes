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
from firebase_functions import firestore_fn, https_fn, options

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


# ─── Helpers: banco e LLM ────────────────────────────────────────────────────

def _get_db():
    return firestore.client()


def _get_api_key(db) -> Optional[str]:
    doc = db.collection("system").document("api_keys").get()
    return doc.to_dict().get("gemini_api_key") if doc.exists else None


def _gemini_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


def _get_embedding(text: str, api_key: str) -> list[float]:
    """Embedding via Gemini REST — reutiliza o helper do main.py."""
    import requests as req_lib
    url = (
        "https://generativelanguage.googleapis.com/v1beta"
        "/models/gemini-embedding-001:embedContent"
    )
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text[:8000]}]},
        "taskType": "RETRIEVAL_DOCUMENT",
    }
    r = req_lib.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["embedding"]["values"]


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
        model="gemini-2.0-flash-lite", contents=prompt
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
            model="gemini-2.0-flash-lite", contents=prompt
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
        model="gemini-2.0-flash-lite", contents=prompt
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
        model="gemini-2.0-flash", contents=summary_prompt
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
) -> tuple[list[dict], str]:
    """
    Extrai o subgrafo RAG para uma nova tarefa.

    Retorna:
      (nodes_payload, formatted_context_string)

    nodes_payload: lista de dicts com {node_id, titulo, resumo, score, tasks}
    formatted_context_string: string pronta para injetar no prompt do Copiloto
      com marcadores de citação [1], [2]…
    """
    # ── Busca nós da mesma área ────────────────────────────────────────────────
    nodes_in_area = []
    nodes_stream = (
        db.collection("knowledge_nodes")
        .where("area_tematica", "==", area_tematica)
        .stream()
    )
    for ndoc in nodes_stream:
        nd = ndoc.to_dict() or {}
        nodes_in_area.append({"id": ndoc.id, **nd})

    if not nodes_in_area:
        return [], ""

    # ── Scoring: similaridade de tags + time decay ────────────────────────────
    tag_set = set(t.lower() for t in (tags or []))
    scored = []
    for node in nodes_in_area:
        # Recupera arestas para obter pesos semânticos e datas de conclusão
        edges = (
            db.collection("knowledge_edges")
            .where("node_id", "==", node["id"])
            .stream()
        )
        edge_list = [e.to_dict() for e in edges]

        if not edge_list:
            continue

        # Peso semântico médio das arestas do nó
        avg_peso = sum(e.get("peso_semantico", 0.7) for e in edge_list) / len(edge_list)

        # Time decay: usa a aresta mais recente (tarefa mais nova)
        dates = [e.get("data_conclusao", "") for e in edge_list if e.get("data_conclusao")]
        latest_date = max(dates) if dates else ""
        decay = _time_decay(latest_date) if latest_date else 1.0

        # Bônus por sobreposição de tags
        node_tags = set(t.lower() for t in (node.get("task_ids") or []))
        # usa as kg_tags das tarefas vinculadas (lookup mais caro — omitido no scoring rápido)
        # em vez disso, compara título do nó com as tags da nova tarefa
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

    # ── Circuit Breaker ────────────────────────────────────────────────────────
    # Remove o nó de menor rank até o payload total caber em token_limit.
    # Nunca trunca — remove por inteiro.
    def _payload_tokens(nodes: list[dict]) -> int:
        return sum(_estimate_tokens(n.get("resumo", "")) for n in nodes)

    while len(candidates) > 1 and _payload_tokens(candidates) > token_limit:
        candidates.pop()  # remove o de menor score (já está ordenado desc)

    if not candidates:
        return [], ""

    # ── Formata o contexto com citações ───────────────────────────────────────
    lines = ["=== CONTEXTO OPERACIONAL DO GRAFO DE CONHECIMENTO ===", ""]
    for i, node in enumerate(candidates, 1):
        lines.append(
            f"[{i}] Nó: \"{node['titulo']}\" "
            f"(relevância: {node['score']:.2f}, baseado em {node['n_tasks']} tarefa(s))"
        )
        if node.get("resumo"):
            lines.append(f"    Procedimento: {node['resumo'][:400]}")
        lines.append("")

    lines.append(
        "Use marcadores [1], [2]… no texto da resposta para indicar a fonte de cada informação."
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

    # Embedding da query para busca vetorial
    query_embedding = _get_embedding(query, api_key)

    # Busca nós (filtra por área se fornecida)
    collection_query = db.collection("knowledge_nodes")
    if area:
        collection_query = collection_query.where("area_tematica", "==", area)

    nodes_raw = []
    for ndoc in collection_query.stream():
        nd = ndoc.to_dict() or {}
        node_emb = nd.get("embedding")
        if not node_emb:
            continue
        sim = _cosine_similarity(query_embedding, node_emb)
        # Time decay via aresta mais recente
        edges = list(
            db.collection("knowledge_edges").where("node_id", "==", ndoc.id).stream()
        )
        dates = [e.to_dict().get("data_conclusao", "") for e in edges if e.to_dict().get("data_conclusao")]
        decay = _time_decay(max(dates)) if dates else 1.0
        avg_peso = (
            sum(e.to_dict().get("peso_semantico", 0.7) for e in edges) / len(edges)
            if edges else 0.7
        )
        score = avg_peso * decay * (0.5 + 0.5 * sim)  # combina peso estrutural e semântico
        nodes_raw.append({
            "node_id": ndoc.id,
            "titulo": nd.get("titulo", ""),
            "resumo": nd.get("resumo", ""),
            "area_tematica": nd.get("area_tematica", ""),
            "score": round(score, 5),
            "n_tasks": nd.get("n_tasks", 0),
            "task_ids": nd.get("task_ids", []),
        })

    nodes_raw.sort(key=lambda x: x["score"], reverse=True)
    candidates = nodes_raw[:top_n]

    # Circuit breaker
    while len(candidates) > 1 and sum(_estimate_tokens(n.get("resumo", "")) for n in candidates) > TOKEN_SAFETY_LIMIT:
        candidates.pop()

    # Formata contexto com citações
    lines = [f"Resultados para a busca: \"{query}\"", ""]
    for i, node in enumerate(candidates, 1):
        lines.append(
            f"[{i}] \"{node['titulo']}\" | Área: {node['area_tematica']} | "
            f"Relevância: {node['score']:.2f} | Baseado em {node['n_tasks']} tarefa(s)"
        )
        if node.get("resumo"):
            lines.append(f"    {node['resumo'][:500]}")
        lines.append("")

    return {
        "nodes": candidates,
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
