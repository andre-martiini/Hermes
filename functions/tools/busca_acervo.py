# tools/busca_acervo.py
from google import genai
from google.genai import types
from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure

from gemini_cost_controls import GEMINI_EMBEDDING_MODEL, embed_content_logged

# ─── Constantes ──────────────────────────────────────────────────────────────
EMBEDDING_MODEL   = GEMINI_EMBEDDING_MODEL          # 768 dims (output_dimensionality=768)
EMBEDDING_DIM     = 768
ACERVO_COLLECTION = "indice_artefatos"
EMBEDDING_FIELD   = "embedding"

# ─── Sanitizador de embedding ─────────────────────────────────────────────────
def _sanitize_embedding(raw: list) -> list[float]:
    """
    Garante exatamente EMBEDDING_DIM floats.
    Levanta ValueError com mensagem clara se o shape estiver errado.
    """
    vec = [float(v) for v in raw]          # converte np.float32, int, etc.
    if len(vec) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding com dimensão inválida: esperado {EMBEDDING_DIM}, "
            f"recebido {len(vec)}. Verifique o modelo e o campo 'embedding'."
        )
    return vec


# ─── Geração de embedding de query ───────────────────────────────────────────
def _gerar_embedding_query(texto: str) -> list[float]:
    """
    Gera embedding de query usando o mesmo modelo e dimensão do knowledge_graph.py:
    gemini-embedding-001 com output_dimensionality=768.
    Isso garante compatibilidade com todos os vetores gravados no indice_artefatos.
    """
    # 1. Recuperar chave do Firestore
    db = firestore.Client()
    keys_doc = db.collection('system').document('api_keys').get()
    api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None

    if not api_key:
        raise ValueError("Chave Gemini não encontrada em system/api_keys no Firestore.")

    # 2. Configurar cliente
    client = genai.Client(api_key=api_key)

    # 3. Mesmo modelo e dimensão usados na indexação (knowledge_graph._get_embedding)
    resposta = embed_content_logged(
        client,
        model=EMBEDDING_MODEL,
        contents=texto,
        feature="busca_acervo.embedding.query",
        db=db,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIM  # 768 — obrigatório para compatibilidade
        )
    )

    raw = resposta.embeddings[0].values
    return _sanitize_embedding(raw)


# ─── Função principal da Tool ─────────────────────────────────────────────────
def buscar_acervo(query: str, limite: int = 5) -> dict:
    """
    Tool chamada pelo LLM para buscar no Acervo Global (indice_artefatos).

    Retorna:
        {"resultados": [...], "erro": None}          → sucesso
        {"resultados": [],    "erro": "<str(e) cru>"} → falha exposta ao LLM
    """
    db = firestore.Client()

    try:
        # 1. Gerar e sanitizar embedding
        query_vector = _gerar_embedding_query(query)

        # 2. Montar a VectorQuery com FindNearest
        collection_ref = db.collection(ACERVO_COLLECTION)

        vector_query = collection_ref.find_nearest(
            vector_field=EMBEDDING_FIELD,
            query_vector=Vector(query_vector),       # ← obrigatório: wrapper Vector()
            distance_measure=DistanceMeasure.COSINE, # ← enum, não string
            limit=limite,
        )

        # 3. Executar
        docs = vector_query.get()

        resultados = []
        for doc in docs:
            data = doc.to_dict()
            origem = data.get("origem", "acervo")
            resultados.append({
                "id":        doc.id,
                "titulo":    data.get("titulo", "sem título"),
                "trecho":    data.get("trecho", ""),
                "fonte":     data.get("fonte", ""),
                "url_drive": data.get("url_drive", ""),
                "task_id":   data.get("task_id"),
                "origem":    origem,
                "distancia": getattr(doc, "distance", None),
            })

        return {"resultados": resultados, "erro": None}

    except Exception as e:
        return {
            "resultados": [],
            "erro": f"[ERRO TÉCNICO FindNearest] {type(e).__name__}: {str(e)}",
        }
