# tools/busca_grafo.py
import re
from datetime import datetime, timedelta, timezone

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

GRAFO_COLLECTION = "tarefas"
FALLBACK_LIMIT = 500
RESULT_LIMIT = 50

# Campos de texto inspecionados no filtro em memoria.
CAMPOS_TEXTO = ["titulo", "descricao", "tags", "responsavel", "status"]

_STATUS_ALIASES = {
    "em andamento": "em andamento",
    "andamento": "em andamento",
    "concluida": "concluida",
    "concluido": "concluida",
    "cancelada": "cancelada",
    "cancelado": "cancelada",
    "pendente": "pendente",
    "atrasada": "atrasada",
    "atrasado": "atrasada",
}


def _extrair_status_da_query(query: str) -> tuple[str | None, str]:
    """Detecta status canonico na query e devolve (status, query_limpa)."""
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
    for campo in CAMPOS_TEXTO:
        valor = doc_dict.get(campo)
        if isinstance(valor, str) and padrao.search(valor):
            return True
        if isinstance(valor, list):
            for item in valor:
                if isinstance(item, str) and padrao.search(item):
                    return True
    return False


def _normalizar_status(status: str | None) -> str:
    return (status or "").strip().lower()


def _matches_filters(
    data: dict,
    termos: list[str],
    match_mode: str,
    area_tematica: str = None,
    data_limite_inicio: str = None,
    data_limite_fim: str = None,
    status: str = None,
    corte_str: str = None,
) -> bool:
    if status and _normalizar_status(data.get("status")) != _normalizar_status(status):
        return False

    if area_tematica and data.get("area_tematica") != area_tematica:
        return False

    data_limite = str(data.get("data_limite") or "")
    if data_limite_inicio and (not data_limite or data_limite < data_limite_inicio):
        return False
    if data_limite_fim and (not data_limite or data_limite > data_limite_fim):
        return False

    if corte_str:
        data_criacao = str(data.get("data_criacao") or "")
        if not data_criacao or data_criacao < corte_str:
            return False

    if termos:
        padroes = [_compilar_padrao_estrito(t) for t in termos]
        if match_mode == "all":
            return all(_doc_bate_com_padrao(data, p) for p in padroes)
        return any(_doc_bate_com_padrao(data, p) for p in padroes)

    return True


def _formatar_resultado(doc_id: str, data: dict) -> dict:
    return {
        "id": doc_id,
        "titulo": data.get("titulo", "sem titulo"),
        "status": data.get("status", ""),
        "responsavel": data.get("responsavel", ""),
        "criado_em": str(data.get("data_criacao", "")),
        "area": data.get("area_tematica", ""),
        "data_limite": data.get("data_limite", ""),
        "descricao": (data.get("descricao") or "")[:350],
    }


def _stream_with_index_fallback(query_ref, db):
    try:
        return query_ref.limit(FALLBACK_LIMIT).stream(), None
    except Exception as err:
        err_text = str(err).lower()
        if type(err).__name__ != "FailedPrecondition" and "requires an index" not in err_text:
            raise
        return db.collection(GRAFO_COLLECTION).limit(FALLBACK_LIMIT).stream(), "composite_index_missing"


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

    Quando faltar indice composto, aplica fallback em memoria sem bloquear a busca.
    """
    db = firestore.Client()

    try:
        if not status and query:
            status_detectado, query = _extrair_status_da_query(query)
            if status_detectado:
                status = status_detectado

        termos = [t.strip() for t in (query or "").split() if t.strip()]
        corte_str = None

        query_ref = db.collection(GRAFO_COLLECTION)
        if status:
            query_ref = query_ref.where(filter=FieldFilter("status", "==", status))
        else:
            corte_dt = datetime.now(tz=timezone.utc) - timedelta(days=dias_retroativos)
            corte_str = corte_dt.isoformat().replace("+00:00", "Z")
            query_ref = query_ref.where(filter=FieldFilter("data_criacao", ">=", corte_str))

        if area_tematica:
            query_ref = query_ref.where(filter=FieldFilter("area_tematica", "==", area_tematica))
        if data_limite_inicio:
            query_ref = query_ref.where(filter=FieldFilter("data_limite", ">=", data_limite_inicio))
        if data_limite_fim:
            query_ref = query_ref.where(filter=FieldFilter("data_limite", "<=", data_limite_fim))

        docs_ref, fallback_reason = _stream_with_index_fallback(query_ref, db)

        resultados = []
        for doc in docs_ref:
            data = doc.to_dict() or {}
            if not _matches_filters(
                data,
                termos=termos,
                match_mode=match_mode,
                area_tematica=area_tematica,
                data_limite_inicio=data_limite_inicio,
                data_limite_fim=data_limite_fim,
                status=status,
                corte_str=corte_str,
            ):
                continue

            resultados.append(_formatar_resultado(doc.id, data))
            if len(resultados) >= RESULT_LIMIT:
                break

        response = {"resultados": resultados, "erro": None}
        if fallback_reason:
            response["aviso"] = "Busca executada com fallback local por falta de indice composto no Firestore."
        return response

    except Exception as e:
        return {
            "resultados": [],
            "erro": f"[ERRO TECNICO BuscaGrafo] {type(e).__name__}: {str(e)}",
        }
