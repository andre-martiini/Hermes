# tools/busca_grafo.py
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

GRAFO_COLLECTION = "tarefas"
FALLBACK_LIMIT = 2000   # docs lidos do Firestore em cada passagem
RESULT_LIMIT = 50       # resultados devolvidos ao chamador

# Campos de texto inspecionados no filtro em memória.
CAMPOS_TEXTO = [
    "titulo",
    "descricao",
    "tags",
    "kg_tags",
    "responsavel",
    "status",
    "notas",
    "area_tematica",
    "processo_sei",
    "sintese_demanda",
    "demanda",
    "projeto",
    "sistema",
]

# Stopwords ignoradas na segmentação de termos de busca.
_STOPWORDS = {
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "uma",
    "os", "as", "no", "na", "com", "por", "para", "dos", "das",
    "nos", "nas", "ao", "se", "ou", "is", "the", "and", "of",
}

# Aliases de status: normalizado sem acento → valor canônico (também sem acento)
_STATUS_ALIASES = {
    "em andamento": "em andamento",
    "andamento":    "em andamento",
    "concluida":    "concluido",   # canônico sem acento
    "concluido":    "concluido",
    "cancelada":    "cancelado",
    "cancelado":    "cancelado",
    "pendente":     "pendente",
    "atrasada":     "atrasado",
    "atrasado":     "atrasado",
}

# Valores exatos que podem estar gravados no Firestore (com acento),
# mapeados para o canônico sem acento.
_STATUS_DB_NORMALIZE = {
    "concluído":  "concluido",
    "concluída":  "concluido",
    "concluido":  "concluido",
    "concluida":  "concluido",
    "cancelado":  "cancelado",
    "cancelada":  "cancelado",
    "em andamento": "em andamento",
    "andamento":  "em andamento",
    "pendente":   "pendente",
    "atrasado":   "atrasado",
    "atrasada":   "atrasado",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de texto
# ──────────────────────────────────────────────────────────────────────────────

def _remover_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalizar_status(status: str | None) -> str:
    """Normaliza status removendo acentos e caixa para comparação segura."""
    raw = _remover_acentos(status or "").strip().lower()
    return _STATUS_DB_NORMALIZE.get(raw, raw)


def _extrair_status_da_query(query: str) -> tuple[str | None, str]:
    """Detecta status canônico na query e devolve (status_canônico, query_limpa)."""
    lowered = _remover_acentos(query).lower()
    for alias in sorted(_STATUS_ALIASES, key=len, reverse=True):
        if alias in lowered:
            status_valor = _STATUS_ALIASES[alias]
            query_limpa = re.sub(re.escape(alias), "", lowered, flags=re.IGNORECASE).strip(" ,.-")
            return status_valor, query_limpa
    return None, query


def _compilar_padrao(termo: str) -> re.Pattern:
    termo_limpo = _remover_acentos(termo).lower()
    return re.compile(re.escape(termo_limpo), re.IGNORECASE)


def _doc_bate_com_padrao(doc_dict: dict, padrao: re.Pattern) -> bool:
    for campo in CAMPOS_TEXTO:
        valor = doc_dict.get(campo)
        if isinstance(valor, str):
            if padrao.search(_remover_acentos(valor)):
                return True
        elif isinstance(valor, list):
            for item in valor:
                if isinstance(item, str) and padrao.search(_remover_acentos(item)):
                    return True
                if isinstance(item, dict):
                    if any(
                        isinstance(v, str) and padrao.search(_remover_acentos(v))
                        for v in item.values()
                    ):
                        return True
        elif isinstance(valor, dict):
            if any(
                isinstance(v, str) and padrao.search(_remover_acentos(v))
                for v in valor.values()
            ):
                return True

    for item in doc_dict.get("pool_dados") or []:
        if not isinstance(item, dict):
            continue
        searchable = " ".join(str(item.get(k) or "") for k in ("nome", "valor", "tipo"))
        if padrao.search(_remover_acentos(searchable)):
            return True

    for item in doc_dict.get("acompanhamento") or []:
        if not isinstance(item, dict):
            continue
        nota = item.get("nota")
        if isinstance(nota, str) and padrao.search(_remover_acentos(nota)):
            return True
    return False


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
    # Filtro de status com normalização de acentos
    if status and _normalizar_status(data.get("status")) != _normalizar_status(status):
        return False

    # Filtro de área temática
    if area_tematica and _remover_acentos(data.get("area_tematica", "")).lower() != _remover_acentos(area_tematica).lower():
        return False

    # Filtro de data_limite (range)
    data_limite = str(data.get("data_limite") or "")
    if data_limite_inicio and (not data_limite or data_limite < data_limite_inicio):
        return False
    if data_limite_fim and (not data_limite or data_limite > data_limite_fim):
        return False

    # Filtro de corte temporal (data_criacao)
    if corte_str:
        data_criacao = str(data.get("data_criacao") or "")
        if not data_criacao or data_criacao < corte_str:
            return False

    # Filtro de termos de texto
    if termos:
        padroes = [_compilar_padrao(t) for t in termos]
        if match_mode == "all":
            return all(_doc_bate_com_padrao(data, p) for p in padroes)
        return any(_doc_bate_com_padrao(data, p) for p in padroes)

    return True


def _formatar_resultado(doc_id: str, data: dict) -> dict:
    """Retorna campos reais da tarefa. Inclui acompanhamento recente e notas
    para que o modelo nao precise recorrer ao RAG para 'enriquecer' os dados."""

    # Últimas 3 entradas do acompanhamento (campo de log/diário da tarefa)
    acomp_raw = data.get("acompanhamento") or []
    acomp_entries = []
    for entry in sorted(acomp_raw, key=lambda e: e.get("data", ""), reverse=True)[:3]:
        nota = (entry.get("nota") or "").strip()
        data_entry = (entry.get("data") or "")[:10]  # só a data YYYY-MM-DD
        if nota:
            acomp_entries.append(f"[{data_entry}] {nota[:300]}")

    # Plano de ação: lista de passos com status de conclusão
    plano_raw = data.get("plano_acao") or []
    plano_entries = []
    for passo in plano_raw:
        if isinstance(passo, dict):
            texto = (passo.get("text") or passo.get("titulo") or "").strip()
            concluido = passo.get("completed", False)
            if texto:
                marcador = "✓" if concluido else "○"
                plano_entries.append(f"{marcador} {texto[:200]}")
        elif isinstance(passo, str) and passo.strip():
            plano_entries.append(f"○ {passo.strip()[:200]}")

    # Tags (kg_tags tem prioridade; fallback para tags genéricas)
    tags = data.get("kg_tags") or data.get("tags") or []

    return {
        "id": doc_id,
        "titulo": data.get("titulo", "sem titulo"),
        "status": data.get("status", ""),
        "tipo_acao": data.get("tipo_acao", ""),
        "responsavel": data.get("responsavel", ""),
        "criado_em": str(data.get("data_criacao", ""))[:10],
        "area": data.get("area_tematica", ""),
        "data_limite": data.get("data_limite", ""),
        "processo_sei": data.get("processo_sei", ""),
        "tags": tags,
        "descricao": (data.get("descricao") or "")[:500],
        "notas": (data.get("notas") or "")[:400],
        "sintese_demanda": (data.get("sintese_demanda") or data.get("demanda") or "")[:400],
        "plano_acao": plano_entries,           # passos estruturados da ação
        "acompanhamento_recente": acomp_entries,  # dados reais do diário
    }


# ──────────────────────────────────────────────────────────────────────────────
# Busca principal
# ──────────────────────────────────────────────────────────────────────────────

def buscar_tarefas(
    query: str,
    area_tematica: str = None,
    dias_retroativos: int = 365,
    match_mode: str = "all",
    data_limite_inicio: str = None,
    data_limite_fim: str = None,
    status: str = None,
    limite: int = 50,
) -> dict:
    """
    Busca tarefas no Firestore usando no máximo UM filtro simples no banco
    (elimina FailedPrecondition por índices compostos ausentes).
    Todo o restante do filtro é aplicado em memória.
    """
    db = firestore.Client()

    try:
        # ── Extração automática de status da query ───────────────────────────
        if not status and query:
            status_detectado, query = _extrair_status_da_query(query)
            if status_detectado:
                status = status_detectado

        # Filtra stopwords e termos muito curtos dos termos de busca
        termos_raw = [t.strip() for t in (query or "").split() if t.strip()]
        termos = [t for t in termos_raw if _remover_acentos(t).lower() not in _STOPWORDS and len(t) > 2]
        if not termos and termos_raw:
            termos = termos_raw  # preserva se tudo era stopword (ex: busca por "oi")

        # ── Estratégia: UM único filtro Firestore para evitar índice composto ─
        # Se houver status, filtra só por status (igualdade — índice automático).
        # Se não, filtra por data_criacao (range simples — índice automático).
        # TODOS os outros critérios vão para in-memory (_matches_filters).
        corte_str = None
        aviso = None

        if status:
            # Usa o canônico normalizado (sem acento) para a query
            status_canonico = _normalizar_status(status)
            # Tenta também o valor com acento que pode estar no DB
            # Primeiro sem acento (padrão mais comum após migração)
            query_ref = (
                db.collection(GRAFO_COLLECTION)
                .where(filter=FieldFilter("status", "==", status_canonico))
                .limit(FALLBACK_LIMIT)
            )
            try:
                docs_stream = list(query_ref.stream())
            except Exception:
                docs_stream = []

            # Se não achou (ex: DB usa "concluído" com acento), tenta com acento
            _ACENTO_MAP = {
                "concluido": "concluído",
                "cancelado": "cancelado",   # já sem acento
                "atrasado":  "atrasado",    # já sem acento
            }
            if not docs_stream and status_canonico in _ACENTO_MAP:
                try:
                    docs_stream = list(
                        db.collection(GRAFO_COLLECTION)
                        .where(filter=FieldFilter("status", "==", _ACENTO_MAP[status_canonico]))
                        .limit(FALLBACK_LIMIT)
                        .stream()
                    )
                except Exception:
                    pass

            # Se ainda vazio, faz varredura geral (sem filtro Firestore)
            if not docs_stream:
                corte_dt = datetime.now(tz=timezone.utc) - timedelta(days=dias_retroativos)
                corte_str = corte_dt.isoformat().replace("+00:00", "Z")
                try:
                    docs_stream = list(
                        db.collection(GRAFO_COLLECTION)
                        .order_by("data_criacao", direction=firestore.Query.DESCENDING)
                        .limit(FALLBACK_LIMIT)
                        .stream()
                    )
                    aviso = "varredura_geral"
                except Exception as e:
                    return {"resultados": [], "erro": f"[ERRO BuscaGrafo] {type(e).__name__}: {e}"}

        else:
            # Sem status: filtra só por data_criacao (range simples)
            corte_dt = datetime.now(tz=timezone.utc) - timedelta(days=dias_retroativos)
            corte_str = corte_dt.isoformat().replace("+00:00", "Z")
            try:
                docs_stream = list(
                    db.collection(GRAFO_COLLECTION)
                    .where(filter=FieldFilter("data_criacao", ">=", corte_str))
                    .limit(FALLBACK_LIMIT)
                    .stream()
                )
            except Exception:
                # Fallback total sem filtro
                try:
                    docs_stream = list(
                        db.collection(GRAFO_COLLECTION)
                        .order_by("data_criacao", direction=firestore.Query.DESCENDING)
                        .limit(FALLBACK_LIMIT)
                        .stream()
                    )
                    aviso = "fallback_sem_filtro"
                except Exception as e:
                    return {"resultados": [], "erro": f"[ERRO BuscaGrafo] {type(e).__name__}: {e}"}

        # ── Filtragem in-memory ───────────────────────────────────────────────
        resultados = []
        for doc in docs_stream:
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
            if len(resultados) >= limite:
                break

        # ── Segunda chance: relaxa match_mode para "any" ──────────────────────
        if not resultados and termos and match_mode == "all":
            aviso = (aviso or "") + "|busca_ampliada_any"
            for doc in docs_stream:  # reitera o mesmo stream já carregado
                data = doc.to_dict() or {}
                if not _matches_filters(
                    data,
                    termos=termos,
                    match_mode="any",
                    area_tematica=area_tematica,
                    data_limite_inicio=data_limite_inicio,
                    data_limite_fim=data_limite_fim,
                    status=status,
                    corte_str=None,  # ignora corte temporal na segunda chance
                ):
                    continue
                resultados.append(_formatar_resultado(doc.id, data))
                if len(resultados) >= limite:
                    break

        # Terceira chance: alguns documentos usam data_criacao como Timestamp
        # Firestore, outros como string ISO. A query inicial compara com string e
        # pode excluir documentos reais sem erro. Aqui varremos documentos
        # ordenados e ignoramos apenas o corte por data_criacao.
        if not resultados and termos and not status:
            aviso = (aviso or "") + "|varredura_sem_corte_data"
            try:
                fallback_docs = list(
                    db.collection(GRAFO_COLLECTION)
                    .order_by("data_criacao", direction=firestore.Query.DESCENDING)
                    .limit(FALLBACK_LIMIT)
                    .stream()
                )
            except Exception:
                fallback_docs = []

            fallback_modes = [match_mode]
            if match_mode == "all":
                fallback_modes.append("any")

            for fallback_mode in fallback_modes:
                for doc in fallback_docs:
                    data = doc.to_dict() or {}
                    if not _matches_filters(
                        data,
                        termos=termos,
                        match_mode=fallback_mode,
                        area_tematica=area_tematica,
                        data_limite_inicio=data_limite_inicio,
                        data_limite_fim=data_limite_fim,
                        status=status,
                        corte_str=None,
                    ):
                        continue
                    resultados.append(_formatar_resultado(doc.id, data))
                    if len(resultados) >= limite:
                        break
                if resultados:
                    break

        response: dict = {"resultados": resultados, "erro": None}
        if aviso:
            response["aviso"] = aviso.strip("|")
        return response

    except Exception as e:
        return {
            "resultados": [],
            "erro": f"[ERRO TECNICO BuscaGrafo] {type(e).__name__}: {str(e)}",
        }
