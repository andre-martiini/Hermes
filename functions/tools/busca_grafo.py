# tools/busca_grafo.py
import re
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from datetime import datetime, timezone, timedelta

GRAFO_COLLECTION  = "tarefas"
FALLBACK_LIMIT    = 500   # quantos docs puxar antes do filtro em memória
RESULT_LIMIT      = 50    # máximo de resultados retornados ao LLM

# Campos de texto que serão inspecionados em cada documento
CAMPOS_TEXTO = ["titulo", "descricao", "tags", "responsavel", "status"]

# Valores canônicos de status reconhecidos para extração automática da query
_STATUS_ALIASES = {
    "em andamento":  "em andamento",
    "andamento":     "em andamento",
    "concluída":     "concluída",
    "concluida":     "concluída",
    "concluído":     "concluída",
    "concluido":     "concluída",
    "cancelada":     "cancelada",
    "cancelado":     "cancelada",
    "pendente":      "pendente",
    "atrasada":      "atrasada",
    "atrasado":      "atrasada",
}


def _extrair_status_da_query(query: str) -> tuple[str | None, str]:
    """
    Detecta status canônico mencionado na query e devolve (status, query_sem_status).
    Tenta frases compostas antes de termos isolados.
    """
    lowered = query.lower()
    for alias in sorted(_STATUS_ALIASES, key=len, reverse=True):
        if alias in lowered:
            status_valor = _STATUS_ALIASES[alias]
            query_limpa = re.sub(re.escape(alias), "", lowered, flags=re.IGNORECASE).strip(" ,.-")
            return status_valor, query_limpa
    return None, query


def _compilar_padrao_estrito(termo: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(termo) + r"\b", re.IGNORECASE)


def _doc_bate_com_padrao(doc_dict: dict, padrao: re.Pattern) -> bool:
    """Retorna True se ao menos um campo de texto contiver o termo isolado."""
    for campo in CAMPOS_TEXTO:
        valor = doc_dict.get(campo)
        if isinstance(valor, str) and padrao.search(valor):
            return True
        if isinstance(valor, list):
            for item in valor:
                if isinstance(item, str) and padrao.search(item):
                    return True
    return False


def buscar_tarefas(
    query: str,
    area_tematica: str = None,
    dias_retroativos: int = 365,
    match_mode: str = "all",
    data_limite_inicio: str = None,
    data_limite_fim: str = None,
    status: str = None,
) -> dict:
    """
    Busca tarefas no Firestore.

    - status: filtro nativo direto (ex: 'em andamento'). Se não fornecido, tenta
      extrair da query automaticamente.
    - Quando status é usado, o filtro de janela temporal é removido para garantir
      que todas as tarefas com aquele status sejam encontradas.
    """
    db = firestore.Client()

    try:
        # Auto-detectar status da query se não fornecido explicitamente
        if not status and query:
            status_detectado, query = _extrair_status_da_query(query)
            if status_detectado:
                status = status_detectado

        query_ref = db.collection(GRAFO_COLLECTION)

        # Filtro por status nativo (não precisa de janela temporal)
        if status:
            query_ref = query_ref.where(filter=FieldFilter("status", "==", status))
        else:
            # Sem status, aplica janela temporal para não varrer o banco todo
            corte_dt = datetime.now(tz=timezone.utc) - timedelta(days=dias_retroativos)
            corte_str = corte_dt.isoformat().replace("+00:00", "Z")
            query_ref = query_ref.where(filter=FieldFilter("data_criacao", ">=", corte_str))

        if area_tematica:
            query_ref = query_ref.where(filter=FieldFilter("area_tematica", "==", area_tematica))

        if data_limite_inicio:
            query_ref = query_ref.where(filter=FieldFilter("data_limite", ">=", data_limite_inicio))

        if data_limite_fim:
            query_ref = query_ref.where(filter=FieldFilter("data_limite", "<=", data_limite_fim))

        docs_ref = query_ref.limit(FALLBACK_LIMIT).stream()

        # Compilar padrões de texto restantes (após extração de status)
        termos = [t.strip() for t in query.split() if t.strip()]

        resultados = []
        for doc in docs_ref:
            data = doc.to_dict()

            if termos:
                padroes = [_compilar_padrao_estrito(t) for t in termos]
                if match_mode == "all":
                    match = all(_doc_bate_com_padrao(data, p) for p in padroes)
                else:
                    match = any(_doc_bate_com_padrao(data, p) for p in padroes)
                if not match:
                    continue

            resultados.append({
                "id":          doc.id,
                "titulo":      data.get("titulo", "sem título"),
                "status":      data.get("status", ""),
                "responsavel": data.get("responsavel", ""),
                "criado_em":   str(data.get("data_criacao", "")),
                "area":        data.get("area_tematica", ""),
                "data_limite": data.get("data_limite", ""),
                "descricao":   (data.get("descricao") or "")[:350],
            })

            if len(resultados) >= RESULT_LIMIT:
                break

        return {"resultados": resultados, "erro": None}

    except Exception as e:
        return {
            "resultados": [],
            "erro": f"[ERRO TÉCNICO BuscaGrafo] {type(e).__name__}: {str(e)}",
        }
