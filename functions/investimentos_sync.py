"""Sincronizacao entre a decisao de investimentos e as acoes do Hermes.

Quando o motor do `sistema-decisao-investimentos` emite uma decisao mensal com
`trocou: true`, esta rotina cria uma acao no Hermes contendo as ordens de
rebalanceamento como etapas do plano de acao.

A rotina e idempotente: consulta se ja existe uma tarefa com a tag
`investimentos-decisao-{mes}` antes de criar, evitando duplicacao.
"""

from datetime import datetime, timezone
import uuid
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from firebase_functions import options, scheduler_fn
from agent_runs import instrumentada

import subtarefas


def sincronizar_decisao_investimentos(db) -> dict:
    """Verifica a decisao vigente de investimentos e cria acao no Hermes se houver troca."""
    import investimentos

    carteira_info = investimentos.carteira()
    if not isinstance(carteira_info, dict) or "erro" in carteira_info:
        return {
            "status": "erro",
            "detalhe": (
                carteira_info.get("erro")
                if isinstance(carteira_info, dict)
                else "erro_desconhecido"
            ),
        }

    decisao = carteira_info.get("decisao_vigente")
    if not decisao or not decisao.get("trocou"):
        return {
            "status": "sem_troca",
            "mes": decisao.get("mes") if decisao else None,
        }

    mes = decisao.get("mes") or datetime.now().strftime("%Y-%m")
    tag_dedup = f"investimentos-decisao-{mes}"

    # Checagem de idempotencia: busca se a acao ja foi criada para este mes
    docs = (
        db.collection("tarefas")
        .where("tags", "array_contains", tag_dedup)
        .limit(1)
        .get()
    )
    for doc in docs:
        return {
            "status": "ja_existe",
            "mes": mes,
            "task_id": doc.id,
            "titulo": (doc.to_dict() or {}).get("titulo"),
        }

    nova_posicao = decisao.get("nova_posicao")
    posicao_anterior = decisao.get("posicao_anterior")

    # Carteira ja na posicao nova: a troca foi executada e confirmada antes desta
    # rodada. O servico devolve ordens vazias nesse caso, e criar a acao agora
    # pediria para fazer de novo o que ja foi feito.
    if nova_posicao and carteira_info.get("posicao") == nova_posicao:
        return {"status": "ja_executada", "mes": mes, "posicao": nova_posicao}

    titulo = (
        f"Executar rebalanceamento de investimentos: {posicao_anterior} → {nova_posicao} ({mes})"
    )

    ordens = decisao.get("ordens") or []
    plano_etapas = []
    if ordens:
        for idx, o in enumerate(ordens):
            texto = (
                o.get("texto")
                or f"{str(o.get('operacao', '')).capitalize()} {o.get('quantidade', '')} {o.get('ativo', '')}"
            )
            plano_etapas.append({
                "id": f"etapa_{idx+1}",
                "texto": texto,
                "estado": "pendente",
            })
    else:
        plano_etapas = [
            {
                "id": "etapa_1",
                "texto": f"Vender posição {posicao_anterior} na corretora",
                "estado": "pendente",
            },
            {
                "id": "etapa_2",
                "texto": f"Comprar posição {nova_posicao} na corretora",
                "estado": "pendente",
            },
            {
                "id": "etapa_3",
                "texto": (
                    f"Confirmar no Gaspar via tool "
                    f"registrar_execucao_investimento(ativo='{nova_posicao}')"
                ),
                "estado": "pendente",
            },
        ]

    now_utc = datetime.now(timezone.utc).isoformat()
    now_sp = datetime.now(ZoneInfo("America/Sao_Paulo"))
    today_str = now_sp.strftime("%Y-%m-%d")

    msg = decisao.get("mensagem") or ""
    descricao = (
        f"O motor de decisão recomendou a troca da carteira no mês de {mes}.\n\n"
        f"Posição anterior: {posicao_anterior}\n"
        f"Nova posição recomendada: {nova_posicao}\n\n"
        f"Ordens sugeridas:\n{msg}\n\n"
        "Após executar as ordens na corretora, use a tool MCP registrar_execucao_investimento "
        "para registrar a nova posição e atualizar o caixa."
    )

    # Mesma validacao do caminho normal de criacao (hermes_tools.criar_acao_no_sistema):
    # area fora da lista vira GERAL. "FINANCAS" fixo criava acao numa area inexistente.
    from hermes_core_logic import carregar_areas_tematicas_validas, normalizar_area_tematica
    area = normalizar_area_tematica("FINANÇAS", carregar_areas_tematicas_validas(db))

    task_id = str(uuid.uuid4())[:20]
    task_doc = {
        "id": task_id,
        "titulo": titulo,
        "descricao": descricao,
        "data_limite": today_str,
        "area_tematica": area,
        "tipo_acao": "fast",
        "tags": ["investimentos", "decisao-mensal", tag_dedup],
        "notas": decisao.get("justificativa") or "",
        "plano_acao": subtarefas.converter_plano(plano_etapas),
        "status": "em andamento",
        "origem": "sistema_decisao_investimentos",
        "projeto": "GERAL",
        "data_criacao": now_utc,
        "data_atualizacao": now_utc,
        "contabilizar_meta": True,
        "acompanhamento": [
            {
                "data": now_utc,
                "nota": (
                    f"Ação criada automaticamente a partir da decisão mensal ({mes}) "
                    "do sistema de investimentos com trocou=true."
                ),
            }
        ],
        "entregas_relacionadas": [],
        "pool_dados": [],
        "plano_acao_historico": [],
        "sync_status": "new",
    }

    db.collection("tarefas").document(task_id).set(task_doc)

    return {
        "status": "acao_criada",
        "task_id": task_id,
        "titulo": titulo,
        "mes": mes,
        "ordens": len(plano_etapas),
    }


@scheduler_fn.on_schedule(
    schedule="30 7 1 * *",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
@instrumentada("sincronizar_investimentos_pos_decisao")
def sincronizar_investimentos_pos_decisao(event: scheduler_fn.ScheduledEvent = None) -> None:
    """Rodada do dia 1 depois da decisao mensal.

    A decisao sai as 06h (com novas tentativas ate ~06h45) e o briefing das 05h
    ainda ve a decisao do mes anterior: sem esta rodada, a acao de uma troca so
    nasceria no dia seguinte. Idempotente pela tag do mes.
    """
    from main import get_db

    resultado = sincronizar_decisao_investimentos(get_db())
    print(f"[InvestimentosSync] Rodada pos-decisao: {resultado}")
