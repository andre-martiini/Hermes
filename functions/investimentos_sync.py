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
                    f"Confirmar no Hermes via tool "
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

    task_id = str(uuid.uuid4())[:20]
    task_doc = {
        "id": task_id,
        "titulo": titulo,
        "descricao": descricao,
        "data_limite": today_str,
        "area_tematica": "FINANCAS",
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
