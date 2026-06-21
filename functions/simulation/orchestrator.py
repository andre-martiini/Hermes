"""O orquestrador (CEO): transforma um objetivo da empresa em tarefas por setor.

`plan()` recebe um `planner` plugavel:
- heuristic_planner: roda offline, sem LLM (default, util em testes).
- make_gemini_planner(api_key): usa o Gemini Pro como "cerebro" de alta inteligencia.

Ambos retornam uma lista de Task ja' roteadas para setores e (quando aplicavel)
com a ferramenta real do registry que pretendem usar.
"""

from __future__ import annotations

import json
from typing import Callable

from .models import Branch, ExecutorType, Task, TaskKind
from .roles import Sector, SECTOR_TOOLS

# Assinatura de um planner: (objetivo, setores_disponiveis) -> lista de Task
Planner = Callable[[str, list[str]], list[Task]]


# Sinais de que um passo SO' um humano pode fazer/decidir (handoff obrigatorio).
HUMAN_ONLY_KEYWORDS = (
    "assinar", "assinatura", "contrato", "juridic", "jurídic", "rescis",
    "demit", "demiss", "politic", "política", "autoriza verba", "decisao final",
    "decisão final", "homologa",
)

# Sinais de que ha' uma bifurcacao a decidir (no' de decisao com ramos).
DECISION_KEYWORDS = (
    "decidir", "renegoci", "escolher", "avaliar opcoes", "avaliar opções",
    "definir estrategia", "definir estratégia",
)


def _is_human_only(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in HUMAN_ONLY_KEYWORDS)


# Palavras-chave -> (setor, ferramenta sugerida, titulo)
_KEYWORD_ROUTING = [
    (("financ", "orcament", "custo", "pagamento", "receita", "despesa"),
     Sector.FINANCEIRO, "registrar_item_financeiro_v2", "Analisar e registrar movimentacao financeira"),
    (("contrat", "pessoa", "bolsist", "rh", "equipe", "colaborad"),
     Sector.RH, "buscar_contato", "Mapear pessoas envolvidas"),
    (("compra", "aquisic", "fornecedor", "suprimento", "material"),
     Sector.AQUISICOES, "mutar_lista_compras", "Levantar e registrar itens de compra"),
    (("projeto", "prazo", "cronograma", "agenda", "reuniao", "entrega"),
     Sector.PROJETOS, "criar_acao_no_sistema", "Estruturar o projeto e prazos"),
    (("pesquis", "estudo", "documento", "manual", "conhecim", "fonte"),
     Sector.CONHECIMENTO, "pesquisar_internet", "Pesquisar e fundamentar"),
    (("email", "whatsapp", "comunic", "mensagem", "aviso", "divulg"),
     Sector.COMUNICACAO, "schedule_whatsapp_message", "Preparar comunicacao"),
    (("sistema", "ti", "automac", "integrac", "bug", "tecnolog"),
     Sector.TI, "criar_acao_no_sistema", "Tratar item tecnico"),
]


def heuristic_planner(goal: str, sectors: list[str]) -> list[Task]:
    """Decomposicao por palavras-chave, sem LLM. Determinista e barata."""
    g = goal.lower()
    tasks: list[Task] = []

    for keywords, sector, tool, title in _KEYWORD_ROUTING:
        if sector not in sectors:
            continue
        if any(k in g for k in keywords):
            tasks.append(Task(
                title=title,
                sector=sector,
                description=f"Derivada do objetivo: {goal}",
                tool=tool,
                params={"contexto": goal},
            ))

    # Fallback: se nada casou, joga uma tarefa de pesquisa para o setor de Conhecimento.
    if not tasks:
        tasks.append(Task(
            title="Investigar o objetivo e propor plano",
            sector=Sector.CONHECIMENTO,
            description=goal,
            tool="pesquisar_internet",
            params={"contexto": goal},
        ))

    # No' de decisao com ramos, quando o objetivo sugere uma bifurcacao.
    if any(k in g for k in DECISION_KEYWORDS) and Sector.DIRETORIA in sectors:
        tasks.extend(_build_decision_subtree(goal, human_critical=_is_human_only(goal)))

    # Passo so'-humano (handoff): assinatura, decisao juridica/politica, etc.
    if _is_human_only(g):
        tasks.append(Task(
            title="Formalizar/assinar (somente humano)",
            sector=Sector.DIRETORIA,
            description=f"Etapa que exige uma pessoa: {goal}",
            executor_type=ExecutorType.HUMAN,
            params={"contexto": goal},
        ))

    # A Diretoria sempre fecha consolidando um relatorio, dependendo das demais.
    consolidacao = Task(
        title="Consolidar resultados e gerar relatorio executivo",
        sector=Sector.DIRETORIA,
        description=f"Sintese final do objetivo: {goal}",
        tool="gerar_relatorio",
        params={"contexto": goal},
        depends_on=[t.id for t in tasks],
    )
    tasks.append(consolidacao)
    return tasks


def _build_decision_subtree(goal: str, human_critical: bool = False) -> list[Task]:
    """Cria um no' de decisao com dois ramos mutuamente exclusivos.

    O engine, ao resolver a decisao, ativa o ramo escolhido e poda o outro.
    Se `human_critical`, a decisao e' um no' critico: so' um humano escolhe.
    """
    ramo_a = Task(
        title="Caminho A: avaliar manter o fornecedor atual",
        sector=Sector.AQUISICOES,
        tool="obter_portal_compras_publico",
        params={"contexto": goal},
    )
    ramo_b = Task(
        title="Caminho B: prospectar novo fornecedor",
        sector=Sector.CONHECIMENTO,
        tool="pesquisar_internet",
        params={"contexto": goal},
    )
    decisao = Task(
        title="Decidir a estrategia",
        sector=Sector.DIRETORIA,
        kind=TaskKind.DECISION,
        executor_type=ExecutorType.HUMAN if human_critical else ExecutorType.AGENT,
        description=f"Bifurcacao do objetivo: {goal}",
        branches=[
            Branch(label="Manter fornecedor atual", unlocks=[ramo_a.id],
                   criteria="Quando ja' ha' relacao boa e custo aceitavel."),
            Branch(label="Buscar novo fornecedor", unlocks=[ramo_b.id],
                   criteria="Quando o custo atual e' alto ou ha' risco de fornecimento."),
        ],
    )
    # Os ramos so' ficam prontos depois que a decisao for resolvida.
    ramo_a.depends_on = [decisao.id]
    ramo_b.depends_on = [decisao.id]
    return [decisao, ramo_a, ramo_b]


def make_gemini_planner(api_key: str, model: str | None = None) -> Planner:
    """Cria um planner que usa o Gemini Pro para decompor o objetivo.

    Faz lazy-import de google.genai; so' e' usado quando ha' chave configurada.
    Em caso de qualquer falha, cai no heuristic_planner para nao travar a simulacao.
    """
    def _planner(goal: str, sectors: list[str]) -> list[Task]:
        try:
            from google import genai
            from google.genai import types
            from gemini_cost_controls import GEMINI_PRO_MODEL, generate_content_logged

            catalog = {s: SECTOR_TOOLS.get(s, []) for s in sectors}
            prompt = (
                "Voce e' a CEO de uma empresa de agentes. Decomponha o OBJETIVO em "
                "tarefas objetivas, cada uma atribuida a um SETOR e, quando fizer sentido, "
                "a uma FERRAMENTA do catalogo do setor.\n\n"
                f"SETORES E FERRAMENTAS:\n{json.dumps(catalog, ensure_ascii=False, indent=2)}\n\n"
                f"OBJETIVO: {goal}\n\n"
                "Retorne APENAS um JSON: uma lista de objetos com as chaves "
                '"title", "sector", "description", "tool" (ou null). '
                "Use exatamente os nomes de setor e ferramenta do catalogo."
            )
            client = genai.Client(api_key=api_key)
            resp = generate_content_logged(
                client,
                model=model or GEMINI_PRO_MODEL,
                contents=prompt,
                feature="simulation.orchestrator.plan",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )
            raw = (resp.text or "").strip()
            data = json.loads(raw)
            tasks: list[Task] = []
            for item in data:
                sector = item.get("sector")
                if sector not in sectors:
                    continue
                tasks.append(Task(
                    title=item.get("title", "Tarefa"),
                    sector=sector,
                    description=item.get("description", ""),
                    tool=item.get("tool") or None,
                    params={"contexto": goal},
                ))
            if tasks:
                return tasks
        except Exception:
            pass
        # Fallback resiliente.
        return heuristic_planner(goal, sectors)

    return _planner


def route_sector(text: str, sectors: list[str]) -> tuple[str, str | None]:
    """Roteia um texto livre (ex: um passo do plano) para (setor, ferramenta)."""
    t = text.lower()
    for keywords, sector, tool, _title in _KEYWORD_ROUTING:
        if sector in sectors and any(k in t for k in keywords):
            return sector, tool
    fallback = Sector.PROJETOS if Sector.PROJETOS in sectors else sectors[0]
    return fallback, "criar_acao_no_sistema"


def plan_from_action(action: dict, sectors: list[str],
                     planner: Planner | None = None) -> list[Task]:
    """Decompoe a partir de uma Tarefa real do Hermes (leitura, sem escrever nela).

    Usa o plano de acao existente (`plano_de_acao`/`plan`) como esqueleto: cada
    passo vira uma tarefa roteada para um setor. Passos com cara de 'so' humano'
    ja' nascem como handoff. Sem plano, cai no planner de objetivo livre.
    """
    title = action.get("titulo") or action.get("title") or "Acao"
    desc = action.get("descricao") or action.get("description") or ""
    goal = f"{title}. {desc}".strip()

    plano = action.get("plano_de_acao") or action.get("plan") or []
    steps = [
        (item.get("text") if isinstance(item, dict) else str(item))
        for item in plano
    ]
    steps = [s for s in steps if s]

    if not steps:
        return plan(goal, sectors, planner)

    tasks: list[Task] = []
    for step in steps:
        sector, tool = route_sector(step, sectors)
        human = _is_human_only(step)
        tasks.append(Task(
            title=step,
            sector=sector,
            description=f"Passo da acao '{title}'",
            executor_type=ExecutorType.HUMAN if human else ExecutorType.AGENT,
            tool=None if human else tool,
            params={"contexto": goal},
        ))

    consolidacao = Task(
        title="Consolidar resultados e gerar relatorio executivo",
        sector=Sector.DIRETORIA,
        description=f"Sintese final da acao: {title}",
        tool="gerar_relatorio",
        params={"contexto": goal},
        depends_on=[t.id for t in tasks],
    )
    tasks.append(consolidacao)
    return tasks


def plan(goal: str, sectors: list[str], planner: Planner | None = None) -> list[Task]:
    planner = planner or heuristic_planner
    return planner(goal, sectors)
