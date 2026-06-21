"""Setores e roster padrao da empresa simulada.

Cada setor mapeia para uma "area tematica" do Hermes e para um subconjunto das
ferramentas reais do registry (`functions/tools/registry.py`). Assim os agentes
trabalham com as MESMAS acoes que o sistema ja expoe, sem inventar capacidades.
"""

from __future__ import annotations

from .models import Agent


class Sector:
    DIRETORIA = "DIRETORIA"        # orquestrador / CEO
    FINANCEIRO = "FINANCEIRO"
    RH = "RH"
    TI = "TI"
    AQUISICOES = "AQUISICOES"
    PROJETOS = "PROJETOS"
    CONHECIMENTO = "CONHECIMENTO"
    COMUNICACAO = "COMUNICACAO"


# Ferramentas reais do registry que cada setor pode acionar.
# Os nomes batem com functions/tools/registry.py.
SECTOR_TOOLS: dict[str, list[str]] = {
    Sector.DIRETORIA: [
        "consultar_historico_acoes",
        "gerar_relatorio",
        "salvar_memoria_global",
    ],
    Sector.FINANCEIRO: [
        "consultar_financas_v2",
        "registrar_item_financeiro_v2",
        "registrar_transacao_financeira_publica",
        "obter_portal_financeiro_publico",
        "calculadora",
    ],
    Sector.RH: [
        "buscar_contato",
        "preparar_atualizacao_contato",
        "registrar_interacao_contato",
        "obter_projeto_bolsas_publico",
        "registrar_inscricao_bolsa_publica",
    ],
    Sector.TI: [
        "consultar_historico_acoes",
        "criar_acao_no_sistema",
        "editar_plano_acao",
        "registrar_correcao_procedimento",
    ],
    Sector.AQUISICOES: [
        "obter_portal_compras_publico",
        "mutar_portal_compras_publico",
        "mutar_lista_compras",
    ],
    Sector.PROJETOS: [
        "criar_acao_no_sistema",
        "consultar_agenda",
        "encontrar_slot_livre",
        "agendar_lembrete_acao",
    ],
    Sector.CONHECIMENTO: [
        "buscar_arquivos_acervo",
        "ler_documento_na_integra",
        "pesquisar_internet",
        "ler_pagina_web",
        "salvar_pop_global",
    ],
    Sector.COMUNICACAO: [
        "schedule_whatsapp_message",
        "buscar_e_analisar_email",
        "gerar_rascunho_formulario",
    ],
}


def default_company() -> list[Agent]:
    """Monta um roster inicial: um CEO (orquestrador) + um agente por setor.

    Da' pra expandir com varios agentes por setor depois (a fila/engine ja suporta
    multiplos agentes no mesmo setor trabalhando em paralelo).
    """
    roster = [
        Agent(
            name="Atena",
            role="CEO / Orquestradora",
            sector=Sector.DIRETORIA,
            persona="Estrategica e direta. Quebra objetivos em tarefas claras e prioriza por impacto.",
            allowed_tools=SECTOR_TOOLS[Sector.DIRETORIA],
        ),
        Agent(
            name="Midas",
            role="Analista Financeiro",
            sector=Sector.FINANCEIRO,
            persona="Cauteloso com numeros. Sempre confere antes de registrar movimentacao.",
            allowed_tools=SECTOR_TOOLS[Sector.FINANCEIRO],
        ),
        Agent(
            name="Hera",
            role="Pessoas & Cultura",
            sector=Sector.RH,
            persona="Cuidadosa com pessoas e dados de contato.",
            allowed_tools=SECTOR_TOOLS[Sector.RH],
        ),
        Agent(
            name="Hefesto",
            role="Tecnologia",
            sector=Sector.TI,
            persona="Pragmatico. Resolve com o menor numero de passos.",
            allowed_tools=SECTOR_TOOLS[Sector.TI],
        ),
        Agent(
            name="Hermes Jr.",
            role="Compras & Suprimentos",
            sector=Sector.AQUISICOES,
            persona="Negociador, busca o melhor custo-beneficio.",
            allowed_tools=SECTOR_TOOLS[Sector.AQUISICOES],
        ),
        Agent(
            name="Apolo",
            role="Gerente de Projetos",
            sector=Sector.PROJETOS,
            persona="Organizado com prazos e agenda.",
            allowed_tools=SECTOR_TOOLS[Sector.PROJETOS],
        ),
        Agent(
            name="Mnemosine",
            role="Conhecimento & Pesquisa",
            sector=Sector.CONHECIMENTO,
            persona="Curiosa, gosta de fundamentar tudo em fontes.",
            allowed_tools=SECTOR_TOOLS[Sector.CONHECIMENTO],
        ),
        Agent(
            name="Iris",
            role="Comunicacao",
            sector=Sector.COMUNICACAO,
            persona="Clara e cordial nas mensagens externas.",
            allowed_tools=SECTOR_TOOLS[Sector.COMUNICACAO],
        ),
    ]
    return roster
