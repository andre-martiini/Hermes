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

from .models import Task
from .roles import Sector, SECTOR_TOOLS

# Assinatura de um planner: (objetivo, setores_disponiveis) -> lista de Task
Planner = Callable[[str, list[str]], list[Task]]


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


def plan(goal: str, sectors: list[str], planner: Planner | None = None) -> list[Task]:
    planner = planner or heuristic_planner
    return planner(goal, sectors)
