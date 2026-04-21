# tools/busca_grafo.py
import re
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from datetime import datetime, timezone, timedelta

GRAFO_COLLECTION  = "tarefas"
FALLBACK_LIMIT    = 200   # quantos docs recentes puxar antes do filtro em memória
RESULT_LIMIT      = 10    # máximo de resultados retornados ao LLM

# Campos de texto que serão inspecionados em cada documento
CAMPOS_TEXTO = ["titulo", "descricao", "tags", "responsavel", "status"]


def _compilar_padrao_estrito(termo: str) -> re.Pattern:
    """
    Compila um padrão que exige o termo como palavra isolada.
    - \\b garante que "IRP" não bata em "IRPF", "CIRP", "SIRP" etc.
    - re.IGNORECASE para cobrir variações de caixa quando relevante.
    - re.escape protege caracteres especiais no termo.
    """
    return re.compile(
        r"\b" + re.escape(termo) + r"\b",
        re.IGNORECASE,
    )


def _doc_bate_com_padrao(doc_dict: dict, padrao: re.Pattern) -> bool:
    """Retorna True somente se ao menos um campo de texto contiver o termo isolado."""
    for campo in CAMPOS_TEXTO:
        valor = doc_dict.get(campo)
        if isinstance(valor, str) and padrao.search(valor):
            return True
        if isinstance(valor, list):          # campo 'tags' pode ser lista
            for item in valor:
                if isinstance(item, str) and padrao.search(item):
                    return True
    return False


def buscar_tarefas(query: str, area_tematica: str = None, dias_retroativos: int = 120, match_mode: str = "all", data_limite_inicio: str = None, data_limite_fim: str = None) -> dict:
    """
    Tool chamada pelo LLM para buscar no Grafo de Conhecimento (tarefas).

    Estratégia:
        1. Puxa tarefas recentes.
        2. Aplica filtros de área_tematica e data_limite se fornecidos.
        3. Aplica regex em cada termo da query.
    """
    db = firestore.Client()

    try:
        # 1. Definir janela de tempo de criação (para não varrer o banco todo)
        corte_dt = datetime.now(tz=timezone.utc) - timedelta(days=dias_retroativos)
        corte_str = corte_dt.isoformat().replace("+00:00", "Z")

        # 2. Busca base no Firestore
        query_ref = db.collection(GRAFO_COLLECTION).where(filter=FieldFilter("data_criacao", ">=", corte_str))
        
        if area_tematica:
            query_ref = query_ref.where(filter=FieldFilter("area_tematica", "==", area_tematica))

        if data_limite_inicio:
            query_ref = query_ref.where(filter=FieldFilter("data_limite", ">=", data_limite_inicio))
        
        if data_limite_fim:
            query_ref = query_ref.where(filter=FieldFilter("data_limite", "<=", data_limite_fim))

        docs_ref = (
            query_ref.order_by("data_criacao", direction=firestore.Query.DESCENDING)
            .limit(FALLBACK_LIMIT)
            .stream()
        )

        # 3. Compilar padrões
        termos = [t.strip() for t in query.split() if t.strip()]
        
        # Se não houver termos, apenas retornamos os últimos docs filtrados pelas datas/área
        if not termos:
            resultados = []
            for doc in docs_ref:
                data = doc.to_dict()
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

        padroes = [_compilar_padrao_estrito(t) for t in termos]

        # 4. Filtro em memória
        resultados = []
        for doc in docs_ref:
            data = doc.to_dict()
            
            # Lógica de match
            if match_mode == "all":
                match = all(_doc_bate_com_padrao(data, p) for p in padroes)
            else: # "any"
                match = any(_doc_bate_com_padrao(data, p) for p in padroes)

            if match:
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
