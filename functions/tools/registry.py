import json
import os

_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")

_CATALOG: dict[str, str] = {
    "consultar_historico_acoes": "Busca acoes, tarefas e projetos no Hermes por frase natural, texto aproximado, status, area ou prazo",
    "buscar_arquivos_acervo": "Busca documentos, manuais e arquivos no Acervo Global do Hermes",
    "pesquisar_internet": "Busca informacoes recentes e atuais na internet",
    "ler_pagina_web": "Le e extrai o conteudo completo de uma URL",
    "consultar_agenda": "Consulta eventos e compromissos na agenda do Google Calendar",
    "encontrar_slot_livre": "Encontra o proximo horario livre disponivel na agenda",
    "criar_acao_no_sistema": "Cria uma nova acao ou tarefa no Hermes com titulo, area, prazo e plano",
    "salvar_memoria_global": "Salva um fato duravel ou preferencia permanente na memoria global",
    "registrar_correcao_procedimento": "Registra uma correcao ou melhoria em um procedimento existente",
    "buscar_e_analisar_email": "Busca e analisa e-mails no Gmail usando query padrao",
    "obter_contexto_tela": "Recupera o contexto completo de uma tarefa, incluindo diario, plano e arquivos",
    "ler_documento_na_integra": "Le um documento do Drive e responde uma pergunta exata com base no conteudo",
    "salvar_pop_global": "Cria ou atualiza um POP operacional reutilizavel",
    "resolver_conflito_memoria": "Resolve conflitos entre memorias globais previamente detectados",
    "atualizar_personalidade": "Atualiza a personalidade dinamica do copiloto Hermes",
    "resolver_conflito_procedimento": "Valida ou resolve um procedimento marcado para revisao",
    "editar_plano_acao": "Atualiza o plano de acao de uma tarefa existente preservando passos concluidos",
    "preparar_edicao_acao": "Prepara uma proposta de edicao de campos de uma tarefa sem gravar no banco",
    "gerar_relatorio": "Gera um relatorio estruturado em Markdown e salva no sistema",
    "gerar_rascunho_formulario": "Gera um rascunho estruturado de formulario com perguntas e tipos",
    "obter_portal_financeiro_publico": "Lista transacoes externas do portal financeiro publico",
    "registrar_transacao_financeira_publica": "Registra uma nova transacao externa no portal financeiro publico",
    "obter_portal_compras_publico": "Lista itens do portal publico de compras",
    "mutar_portal_compras_publico": "Executa acoes simples no portal publico de compras",
    "mutar_lista_compras": "Cria, atualiza, remove ou importa itens da lista de compras interna",
    "obter_projeto_bolsas_publico": "Consulta dados publicos de um projeto de bolsas por ID",
    "registrar_inscricao_bolsa_publica": "Registra uma inscricao publica em um projeto de bolsas",
    "consultar_financas_v2": "Consulta detalhada do financeiro interno: rendas, obrigações, metas e transações",
    "registrar_item_financeiro_v2": "Registra uma nova movimentação (renda ou despesa) no financeiro interno",
    "calculadora": "Calculadora dedicada para calculos matematicos ad-hoc ou projecoes.",
    "schedule_whatsapp_message": "Agenda ou envia uma mensagem de WhatsApp para um contato.",
}

_NEEDS_CONFIRMATION: set[str] = {
    "criar_acao_no_sistema",
    "editar_plano_acao",
    "salvar_memoria_global",
    "salvar_pop_global",
    "resolver_conflito_memoria",
    "resolver_conflito_procedimento",
    "registrar_transacao_financeira_publica",
    "mutar_lista_compras",
    "mutar_portal_compras_publico",
    "registrar_inscricao_bolsa_publica",
    "registrar_item_financeiro_v2",
    "schedule_whatsapp_message",
}

_ASYNC_TOOLS: set[str] = {
    "buscar_e_analisar_email",
    "ler_documento_na_integra",
    "gerar_relatorio",
    "pesquisar_internet",
    "ler_pagina_web",
}

_schema_cache: dict[str, dict] = {}


def get_short_catalog() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in _CATALOG.items())


def list_tool_names() -> set[str]:
    return set(_CATALOG.keys())


def get_schema(tool_name: str) -> dict:
    if tool_name not in _schema_cache:
        path = os.path.join(_SCHEMA_DIR, f"{tool_name}.json")
        with open(path, "r", encoding="utf-8") as f:
            _schema_cache[tool_name] = json.load(f)
    return _schema_cache[tool_name]


def needs_confirmation(tool_name: str) -> bool:
    return tool_name in _NEEDS_CONFIRMATION


def is_async(tool_name: str) -> bool:
    return tool_name in _ASYNC_TOOLS


def get_required_params(tool_name: str) -> list[str]:
    schema = get_schema(tool_name)
    return schema.get("parameters", {}).get("required", [])
