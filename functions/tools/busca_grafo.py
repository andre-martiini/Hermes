# tools/busca_grafo.py
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

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
    "porfavor", "favor", "por-favor", "pf", "pfv", "gostaria", "quero",
    "queria", "preciso", "necessito", "pode", "poderia", "me", "minha",
    "meu", "seu", "sua", "relacionado", "relacionada", "referente",
    "sobre", "acerca", "cujo", "cuja", "qual", "quais",
    "nome", "chamada", "chamado", "registrada", "registrado", "sistema",
    "hermes", "historico", "histórico",
    "acao", "acoes", "tarefa", "tarefas", "pesquisa", "pesquisar",
    "pesquise", "busca", "buscar", "busque", "procura", "procurar",
    "procure", "localiza", "localizar", "localize", "ative", "ativar",
    "ativa", "contexto",
}

# Equivalencias de dominio e correcoes comuns. A busca continua local e
# deterministica, mas ganha tolerancia sem depender de servicos externos.
_SEARCH_SYNONYMS = {
    "contratacao": {
        "contratar", "contrato", "contratual", "aquisicao", "compra",
        "compras", "licitacao", "dispensa", "locacao", "aluguel",
    },
    "contratar": {"contratacao", "contrato", "locacao", "dispensa"},
    "contrato": {"contratacao", "contratar", "locacao"},
    "locacao": {"contratacao", "aluguel", "contrato", "contratar"},
    "aluguel": {"locacao", "contratacao"},
    "dispensa": {"contratacao", "licitacao", "eletronica", "publicacao"},
    "licitacao": {"contratacao", "dispensa", "compra", "aquisicao"},
    "aquisicao": {"contratacao", "compra", "compras", "licitacao"},
    "compra": {"aquisicao", "contratacao", "compras"},
    "compras": {"compra", "aquisicao", "contratacao"},
    "imobiliario": {"mobiliario", "moveis"},
    "imobiliarios": {"mobiliario", "mobiliarios", "moveis"},
    "mobiliario": {"imobiliario", "moveis", "mesa", "cadeira", "cadeiras"},
    "mobiliarios": {"mobiliario", "moveis"},
    "movel": {"mobiliario", "moveis"},
    "moveis": {"mobiliario", "mobiliarios"},
    "som": {"audio", "sonorizacao", "microfone"},
    "audio": {"som", "sonorizacao"},
    "sonorizacao": {"som", "audio"},
    "evento": {"eventos"},
    "eventos": {"evento"},
}

_SEARCH_FIELDS = [
    ("titulo", 6.0),
    ("processo_sei", 7.0),
    ("tags", 4.0),
    ("kg_tags", 4.0),
    ("sintese_demanda", 3.5),
    ("demanda", 3.5),
    ("descricao", 3.0),
    ("area_tematica", 2.5),
    ("projeto", 2.5),
    ("sistema", 2.5),
    ("responsavel", 2.0),
    ("notas", 1.8),
    ("status", 1.2),
    ("pool_dados", 1.6),
    ("acompanhamento", 1.2),
]

_MIN_TERM_SCORE = 9.0

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


def _normalizar_texto_busca(valor) -> str:
    texto = _remover_acentos(str(valor or "")).lower()
    texto = texto.replace("_", " ").replace("—", " ").replace("–", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _tokenizar_busca(valor) -> list[str]:
    texto = _normalizar_texto_busca(valor)
    return re.findall(r"[a-z0-9]+(?:[./-][a-z0-9]+)*", texto, flags=re.UNICODE)


def _termo_eh_ruido(termo: str) -> bool:
    termo_norm = _normalizar_texto_busca(termo).strip(".,;:!?()[]{}'\"")
    termo_compacto = re.sub(r"[^a-z0-9]+", "", termo_norm)
    return (
        len(termo_norm) <= 2
        or termo_norm in _STOPWORDS
        or termo_compacto in _STOPWORDS
    )


def _parece_identificador(termo: str) -> bool:
    return sum(1 for c in termo if c.isdigit()) >= 5 and any(c in termo for c in "./-")


def _singularizar_leve(termo: str) -> set[str]:
    variantes = {termo}
    if len(termo) <= 3:
        return variantes
    if termo.endswith("coes") and len(termo) > 5:
        variantes.add(f"{termo[:-4]}cao")
    if termo.endswith("oes") and len(termo) > 5:
        variantes.add(f"{termo[:-3]}ao")
    if termo.endswith("ais") and len(termo) > 5:
        variantes.add(f"{termo[:-3]}al")
    if termo.endswith("eis") and len(termo) > 5:
        variantes.add(f"{termo[:-3]}el")
    if termo.endswith("is") and len(termo) > 4:
        variantes.add(termo[:-1])
    if termo.endswith("s") and not termo.endswith("ss"):
        variantes.add(termo[:-1])
    return {v for v in variantes if len(v) > 1}


def _expandir_termo(termo: str) -> set[str]:
    termo_norm = _normalizar_texto_busca(termo).strip(".,;:!?()[]{}'\"")
    variantes = _singularizar_leve(termo_norm)
    for variante in list(variantes):
        variantes.update(_SEARCH_SYNONYMS.get(variante, set()))
    for variante in list(variantes):
        variantes.update(_singularizar_leve(variante))
    return {v for v in variantes if v and not _termo_eh_ruido(v)}


def _preparar_termos_busca(query: str) -> list[str]:
    termos = []
    vistos = set()
    for termo in _tokenizar_busca(query or ""):
        termo = termo.strip(".,;:!?()[]{}'\"")
        if _termo_eh_ruido(termo):
            continue
        chave = termo
        if chave not in vistos:
            vistos.add(chave)
            termos.append(chave)

    if not termos:
        for termo in _tokenizar_busca(query or ""):
            if termo not in vistos:
                vistos.add(termo)
                termos.append(termo)
    return termos


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


def _texto_normalizado(valor) -> str:
    if isinstance(valor, str):
        return _remover_acentos(valor).lower()
    if isinstance(valor, list):
        return " ".join(_texto_normalizado(item) for item in valor)
    if isinstance(valor, dict):
        return " ".join(_texto_normalizado(item) for item in valor.values())
    return _remover_acentos(str(valor or "")).lower()


def _normalizar_data_comparavel(valor) -> str:
    if not valor:
        return ""
    if hasattr(valor, "isoformat"):
        try:
            return valor.isoformat()
        except Exception:
            pass
    texto = str(valor)
    match = re.search(r"\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+-]+Z?)?", texto)
    return match.group(0).replace(" ", "T") if match else texto


def _partes_texto_busca(data: dict) -> list[tuple[str, str, list[str], float]]:
    partes = []
    for campo, peso in _SEARCH_FIELDS:
        texto = _texto_normalizado(data.get(campo))
        if not texto:
            continue
        texto = _normalizar_texto_busca(texto)
        tokens = list(dict.fromkeys(_tokenizar_busca(texto)))
        partes.append((campo, texto, tokens, peso))
    return partes


def _score_variante_em_texto(variante: str, texto: str, tokens: list[str], peso: float) -> float:
    if not variante:
        return 0.0

    score = 0.0
    if variante in tokens:
        score = max(score, 12.0 * peso)
    elif len(variante) >= 4 and variante in texto:
        score = max(score, 9.0 * peso)

    if _parece_identificador(variante):
        for token in tokens[:900]:
            if len(variante) >= 5 and token.startswith(variante):
                score = max(score, 7.0 * peso)
                break
        return score

    if len(variante) >= 4:
        for token in tokens[:900]:
            if token == variante:
                continue
            if len(token) >= 4 and (token.startswith(variante) or variante.startswith(token)):
                score = max(score, 7.0 * peso)
                break

    if len(variante) >= 5:
        best_ratio = 0.0
        for token in tokens[:900]:
            if len(token) < 4:
                continue
            if abs(len(token) - len(variante)) > max(3, int(len(variante) * 0.45)):
                continue
            ratio = SequenceMatcher(None, variante, token).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                if best_ratio >= 0.95:
                    break
        if best_ratio >= 0.92:
            score = max(score, 8.0 * peso)
        elif best_ratio >= 0.88:
            score = max(score, 6.0 * peso)
        elif best_ratio >= 0.80 and len(variante) >= 8:
            score = max(score, 4.0 * peso)

    return score


def _score_termo(data: dict, termo: str, partes: list[tuple[str, str, list[str], float]] | None = None) -> float:
    variantes = _expandir_termo(termo)
    if not variantes:
        return 0.0
    partes = partes or _partes_texto_busca(data)

    best = 0.0
    for _campo, texto, tokens, peso in partes:
        for variante in variantes:
            best = max(best, _score_variante_em_texto(variante, texto, tokens, peso))
    return best


def _cobertura_minima(termos: list[str], match_mode: str) -> int:
    total = len(termos)
    if total <= 0:
        return 0
    if match_mode != "all":
        return 1
    if total <= 2:
        return total
    if total <= 4:
        return max(2, total - 1)
    return max(3, int(total * 0.65))


def _calcular_match_busca(data: dict, termos: list[str], query: str = "") -> tuple[float, int]:
    if not termos:
        return 0.0, 0

    partes = _partes_texto_busca(data)
    termo_scores = [_score_termo(data, termo, partes) for termo in termos]
    matched = sum(1 for score in termo_scores if score >= _MIN_TERM_SCORE)
    score = sum(termo_scores)

    titulo = _normalizar_texto_busca(data.get("titulo"))
    texto_total = " ".join(parte[1] for parte in partes)
    query_norm = _normalizar_texto_busca(query)
    termos_phrase = " ".join(termos)

    if query_norm and len(query_norm) >= 4:
        if query_norm in titulo:
            score += 160
        elif query_norm in texto_total:
            score += 80

    if termos_phrase and len(termos_phrase) >= 4:
        if termos_phrase in titulo:
            score += 120
        elif termos_phrase in texto_total:
            score += 50

    title_hits = 0
    title_tokens = _tokenizar_busca(titulo)
    for termo in termos:
        variantes = _expandir_termo(termo)
        if any(
            variante in title_tokens
            or (len(variante) >= 4 and variante in titulo)
            or any(len(variante) >= 5 and SequenceMatcher(None, variante, token).ratio() >= 0.88 for token in title_tokens)
            for variante in variantes
        ):
            title_hits += 1

    if title_hits == len(termos):
        score += 90
    elif title_hits >= _cobertura_minima(termos, "all"):
        score += 45

    processo = _normalizar_texto_busca(data.get("processo_sei"))
    processo_compacto = re.sub(r"[^a-z0-9]+", "", processo)
    for termo in termos:
        termo_compacto = re.sub(r"[^a-z0-9]+", "", termo)
        if termo_compacto and len(termo_compacto) >= 6 and termo_compacto in processo_compacto:
            score += 140

    if matched:
        score += (matched / max(1, len(termos))) * 35
    return score, matched


def _calcular_score(data: dict, termos: list[str], query: str = "") -> int:
    score, _matched = _calcular_match_busca(data, termos, query)
    return int(round(score))


def _doc_bate_busca(data: dict, termos: list[str], match_mode: str, query: str = "") -> bool:
    if not termos:
        return True
    score, matched = _calcular_match_busca(data, termos, query)
    if matched >= _cobertura_minima(termos, match_mode):
        return True
    # Um match de frase/processo muito forte deve sobreviver mesmo com tokens
    # ausentes por causa de abreviacoes ou redacao diferente.
    return score >= 130 and matched >= 1


def _matches_filters(
    data: dict,
    termos: list[str],
    match_mode: str,
    query: str = "",
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
    data_limite = _normalizar_data_comparavel(data.get("data_limite"))[:10]
    if data_limite_inicio and (not data_limite or data_limite < data_limite_inicio):
        return False
    if data_limite_fim and (not data_limite or data_limite > data_limite_fim):
        return False

    # Filtro de corte temporal (data_criacao)
    if corte_str:
        data_criacao = _normalizar_data_comparavel(data.get("data_criacao"))
        if not data_criacao or data_criacao < corte_str:
            return False

    # Filtro de termos de texto
    if termos:
        return _doc_bate_busca(data, termos, match_mode, query=query)

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

def _adicionar_docs_unicos(destino: list, docs: list, vistos: set[str]) -> None:
    for doc in docs:
        doc_id = str(getattr(doc, "id", ""))
        if not doc_id or doc_id in vistos:
            continue
        vistos.add(doc_id)
        destino.append(doc)


def _listar_docs_base(db, limit: int) -> tuple[list, str | None, Exception | None]:
    try:
        return (
            list(
                db.collection(GRAFO_COLLECTION)
                .order_by("data_criacao", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            ),
            None,
            None,
        )
    except Exception as ordered_err:
        try:
            return (
                list(db.collection(GRAFO_COLLECTION).limit(limit).stream()),
                "fallback local sem ordenacao",
                None,
            )
        except Exception as plain_err:
            return [], None, plain_err or ordered_err


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
    Busca tarefas no Firestore com consultas simples e ranqueamento local.
    Evita indices compostos; filtros finos e relevancia sao aplicados em memoria.
    """
    try:
        db = firestore.Client()

        # ── Extração automática de status da query ───────────────────────────
        if not status and query:
            status_detectado, query = _extrair_status_da_query(query)
            if status_detectado:
                status = status_detectado

        # Filtra comandos/stopwords e prepara termos com normalizacao unica.
        termos = _preparar_termos_busca(query or "")
        collect_limit = min(FALLBACK_LIMIT, max(limite * 10, limite, RESULT_LIMIT))

        # Text searches should behave like a ranked search engine. We use
        # data_criacao only to fetch/order candidates; it is a hard filter only
        # for empty/listing queries.
        corte_str = None
        if not termos:
            corte_dt = datetime.now(tz=timezone.utc) - timedelta(days=dias_retroativos)
            corte_str = corte_dt.isoformat().replace("+00:00", "Z")

        avisos = []
        docs_stream = []
        vistos: set[str] = set()

        if status:
            status_canonico = _normalizar_status(status)
            status_variants = [status_canonico]
            _ACENTO_MAP = {
                "concluido": "concluído",
                "cancelado": "cancelado",
                "atrasado": "atrasado",
            }
            if status_canonico in _ACENTO_MAP:
                status_variants.append(_ACENTO_MAP[status_canonico])

            for status_value in dict.fromkeys(status_variants):
                try:
                    status_docs = list(
                        db.collection(GRAFO_COLLECTION)
                        .where(filter=FieldFilter("status", "==", status_value))
                        .limit(FALLBACK_LIMIT)
                        .stream()
                    )
                    _adicionar_docs_unicos(docs_stream, status_docs, vistos)
                except Exception:
                    avisos.append("fallback local por status")

        base_docs, base_aviso, base_err = _listar_docs_base(db, FALLBACK_LIMIT)
        if base_err and not docs_stream:
            return {"resultados": [], "erro": f"[ERRO BuscaGrafo] {type(base_err).__name__}: {base_err}"}
        if base_aviso:
            avisos.append(base_aviso)
        _adicionar_docs_unicos(docs_stream, base_docs, vistos)

        # ── Filtragem in-memory ───────────────────────────────────────────────
        resultados = []
        for doc in docs_stream:
            data = doc.to_dict() or {}
            if not _matches_filters(
                data,
                termos=termos,
                match_mode=match_mode,
                query=query or "",
                area_tematica=area_tematica,
                data_limite_inicio=data_limite_inicio,
                data_limite_fim=data_limite_fim,
                status=status,
                corte_str=corte_str,
            ):
                continue
            result = _formatar_resultado(doc.id, data)
            result["_match_score"] = _calcular_score(data, termos, query=query or "")
            resultados.append(result)
            if not termos and len(resultados) >= collect_limit:
                break

        # ── Segunda chance: relaxa match_mode para "any" ──────────────────────
        if not resultados and termos and match_mode == "all":
            avisos.append("busca ampliada any")
            for doc in docs_stream:  # reitera o mesmo stream já carregado
                data = doc.to_dict() or {}
                if not _matches_filters(
                    data,
                    termos=termos,
                    match_mode="any",
                    query=query or "",
                    area_tematica=area_tematica,
                    data_limite_inicio=data_limite_inicio,
                    data_limite_fim=data_limite_fim,
                    status=status,
                    corte_str=None,  # ignora corte temporal na segunda chance
                ):
                    continue
                result = _formatar_resultado(doc.id, data)
                result["_match_score"] = _calcular_score(data, termos, query=query or "")
                resultados.append(result)

        resultados = sorted(resultados, key=lambda r: r.get("_match_score", 0), reverse=True)[:limite]
        for result in resultados:
            result.pop("_match_score", None)

        response: dict = {"resultados": resultados, "erro": None}
        aviso = "|".join(dict.fromkeys(a for a in avisos if a))
        if aviso:
            response["aviso"] = aviso.strip("|")
        return response

    except Exception as e:
        return {
            "resultados": [],
            "erro": f"[ERRO TECNICO BuscaGrafo] {type(e).__name__}: {str(e)}",
        }
