import json
import os

_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")

_CATALOG: dict[str, str] = {
    "consultar_historico_acoes": "Busca acoes, tarefas e projetos no Hermes por frase natural, texto aproximado, status, area ou prazo",
    "buscar_arquivos_acervo": "Busca documentos, manuais e arquivos no Acervo Global do Hermes",
    "buscar_conversas_whatsapp": "Busca conversas de WhatsApp indexadas (digests) por similaridade semantica",
    "pesquisar_internet": "Busca informacoes recentes e atuais na internet",
    "ler_pagina_web": "Le e extrai o conteudo completo de uma URL",
    "consultar_agenda": "Consulta eventos e compromissos na agenda do Google Calendar",
    "encontrar_slot_livre": "Encontra o proximo horario livre disponivel na agenda",
    "criar_acao_no_sistema": "Cria uma nova acao ou tarefa no Hermes com titulo, area, data de execucao, prazo final opcional e plano",
    "agendar_lembrete_acao": "Agenda um lembrete para uma acao do Hermes com data, horario e texto opcional",
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
    "preparar_edicao_em_lote": "Prepara proposta de edicao de campos para multiplas tarefas simultaneamente sem gravar no banco",
    "gerar_relatorio": "Gera um relatorio estruturado em Markdown e salva no sistema",
    "gerar_rascunho_formulario": "Gera um rascunho estruturado de formulario com perguntas e tipos",
    "obter_portal_financeiro_publico": "Lista transacoes externas do portal financeiro publico",
    "registrar_transacao_financeira_publica": "Registra uma nova transacao externa no portal financeiro publico",
    "obter_portal_compras_publico": "Lista itens do portal publico de compras",
    "mutar_portal_compras_publico": "Executa acoes simples no portal publico de compras",
    "mutar_lista_compras": "Cria, atualiza, remove ou importa itens da lista de compras interna",
    # Sem a leitura, `update` e `delete` eram inuteis pelo MCP: os dois exigem
    # item_id e nao havia de onde tira-lo. E nao dava para conferir o efeito da
    # propria escrita sem pedir ao usuario que abrisse a tela.
    "consultar_lista_compras": "Le a lista de compras com o item_id de cada item, o que esta planejado e o que ja foi comprado",
    # Detector de subproduto: o trabalho ja feito que rende um ativo com um passo
    # a mais. Sem a alca de decisao as sugestoes ficam na fila sem resposta, e a
    # que mais importa e "nunca" — sem ela o sistema repete e vira barulho.
    "consultar_elevacoes_sugeridas": "Lista as elevacoes sugeridas que esperam decisao, com o material que ja existe e o objetivo servido",
    "decidir_elevacao": "Aceita, adia ou descarta para sempre uma elevacao sugerida",
    "obter_projeto_bolsas_publico": "Consulta dados publicos de um projeto de bolsas por ID",
    "registrar_inscricao_bolsa_publica": "Registra uma inscricao publica em um projeto de bolsas",
    "consultar_financas_v2": "Consulta detalhada do financeiro interno: rendas, obrigações, metas e transações",
    "registrar_item_financeiro_v2": "Registra uma nova movimentação (renda ou despesa) no financeiro interno",
    "calculadora": "Calculadora dedicada para calculos matematicos ad-hoc ou projecoes.",
    "schedule_whatsapp_message": "Agenda ou envia uma mensagem de WhatsApp para um contato.",
    "pausar_conversa": "Enfileira uma resposta de pausa no WhatsApp e agenda a retomada após confirmação explícita",
    "buscar_contato": "Busca contatos por nome, email ou tag em perfil_pessoas para resolver menções a pessoas",
    "preparar_vinculo_contatos": "Prepara proposta de vínculo de pessoas a uma tarefa (gera card de confirmação)",
    "preparar_atualizacao_contato": "Prepara criação ou atualização de contato com novos fatos (gera card de confirmação)",
    "registrar_interacao_contato": "Registra interação silenciosa no histórico de um contato (sem confirmação)",
    # Tools que ja existiam como closure no copiloto web mas nunca tinham entrado
    # no catalogo — entraram junto com a migracao para tools/hermes_tools.py.
    # A descricao antiga prometia "passos" e "sono", que nao existem no modelo:
    # o que ha e caminhada em km, calorias, qualidade do sono e dor.
    "consultar_saude": "Consulta dados de saude: peso, cintura, caminhada, calorias, qualidade do sono e dor",
    "registrar_saude": "Registra o que o USUARIO declarou de saude no dia: peso, cintura, dor, sono",
    "consultar_dados_cadastrais": "Consulta dados cadastrais pessoais (documentos, contato, familia, formacao, carreira, banco, plano de saude)",
    "registrar_no_diario": "Registra uma entrada livre no diario de bordo de uma acao",
    "gerar_imagem": "Gera uma imagem a partir de uma descricao textual e devolve a URL publica",
    "preparar_reagendamento_em_lote": "Prepara reagendamento de varias acoes redistribuidas por dias uteis, sem gravar",
    "preparar_remocao_horarios_em_lote": "Prepara a remocao de horarios de varias acoes em lote, sem gravar",
    "criar_objetivo_estrategico": "Cria um objetivo estrategico com pilar, meta, diretrizes, indicadores e marcos",
    "editar_objetivo_estrategico": "Edita campos de um objetivo estrategico existente",
    "gerenciar_item_estrategico": "Adiciona, edita, remove ou conclui um indicador ou marco de um objetivo",
    "excluir_objetivo_estrategico": "Exclui definitivamente um objetivo estrategico",
    "consultar_processo_sipac": "Consulta um processo no SIPAC: dados gerais, interessados, movimentacoes e documentos",
    "acompanhar_processo_sipac": "Ativa ou desativa o monitoramento automatico de um processo SIPAC",
    # Contraparte de gravacao das tools `preparar_*`. No web app quem chama e o
    # card de confirmacao da UI; canais sem UI (MCP) precisam chamar diretamente,
    # senao a proposta preparada nunca e aplicada.
    "confirmar_edicao_acao": "Aplica de fato a edicao de acao montada por preparar_edicao_acao",
    "confirmar_edicao_em_lote": "Aplica de fato a edicao em lote montada por preparar_edicao_em_lote",
    "confirmar_reagendamento_em_lote": "Aplica de fato o reagendamento em lote montado por preparar_reagendamento_em_lote",
    # Contraparte das tools longas, que devolvem job_id em vez do resultado.
    "consultar_job": "Busca o resultado de uma tool longa que devolveu status processing e um job_id",
    # Escrita direta: o par preparar/confirmar existe por causa do card da UI
    # web, que um cliente MCP nao tem — la o proprio cliente confirma com o
    # usuario antes de chamar. As `preparar_*` continuam, para a web.
    "editar_acao": "Edita uma acao diretamente, sem o passo de preparacao",
    "editar_acoes_em_lote": "Edita varias acoes de uma vez, diretamente",
    "reagendar_acoes_em_lote": "Redistribui acoes por dias uteis e ja aplica",
    "obter_estado_atual": "Panorama do dia numa chamada: acoes, agenda, janelas livres e pendencias",
    "obter_acao": "Uma acao inteira e SEM TRUNCAMENTO: descricao, notas, plano completo e diario",
    # Ingestao de arquivo: sem ela, anexo so entrava por link de algo que ja
    # estava no Drive, e comprovante nascido fora dele ficava orfao.
    "anexar_arquivo": "Anexa um arquivo a uma acao: grava no Drive, vincula e escreve no diario",
    "preparar_upload": "Devolve URL assinada para subir arquivo local sem passa-lo pela conversa",
    "remover_anexo": "Remove um anexo da acao, preservando a trilha de auditoria do diario",
    # Fatura de cartao: o que um boleto nao tem — em que se gastou e o que
    # ja esta comprometido nos meses seguintes.
    "consultar_fatura_cartao": "Consulta os lancamentos da fatura do cartao, com total por estabelecimento",
    "consultar_compromissos_futuros": "Projeta quanto de cada mes futuro ja esta comprometido por compras parceladas",
    # WhatsApp: a consolidacao ja existia e so era acionavel pela Caixa de
    # Entrada na web. Leitura de conteudo exige chat na allowlist.
    "listar_conversas_whatsapp": "Lista as conversas de WhatsApp, marcando quais estao monitoradas",
    "ler_mensagens_whatsapp": "Le as mensagens de uma conversa monitorada, para escolher o recorte",
    "consolidar_whatsapp": "Consolida um recorte de mensagens: transcreve midia e sintetiza resumo e itens de acao",
    "ler_consolidacao_whatsapp": "Le uma consolidacao inteira, ou as mais recentes de uma conversa",
    "consultar_envio_whatsapp": "Estado real de uma mensagem enfileirada: enviada, na fila ou falhou",
}

_NEEDS_CONFIRMATION: set[str] = {
    "criar_acao_no_sistema",
    "agendar_lembrete_acao",
    "editar_plano_acao",
    "salvar_memoria_global",
    "salvar_pop_global",
    "resolver_conflito_memoria",
    "resolver_conflito_procedimento",
    "registrar_transacao_financeira_publica",
    "mutar_lista_compras",
    "decidir_elevacao",
    "mutar_portal_compras_publico",
    "registrar_inscricao_bolsa_publica",
    "registrar_item_financeiro_v2",
    "schedule_whatsapp_message",
    "pausar_conversa",
    "preparar_vinculo_contatos",
    "preparar_atualizacao_contato",
    # Gravam direto, sem card de confirmacao intermediario.
    "registrar_no_diario",
    "criar_objetivo_estrategico",
    "editar_objetivo_estrategico",
    "gerenciar_item_estrategico",
    "excluir_objetivo_estrategico",
    "acompanhar_processo_sipac",
    "gerar_imagem",
    # Escrita direta, para canais sem card de confirmacao.
    "anexar_arquivo",
    "remover_anexo",
    # Cria job de processamento e consome transcricao paga de midia.
    "consolidar_whatsapp",
    "editar_acao",
    "editar_acoes_em_lote",
    "reagendar_acoes_em_lote",
    # Contraparte de gravacao das `preparar_*`: e aqui que a mutacao acontece.
    "confirmar_edicao_acao",
    "confirmar_edicao_em_lote",
    "confirmar_reagendamento_em_lote",
}

_ASYNC_TOOLS: set[str] = {
    "buscar_e_analisar_email",
    "ler_documento_na_integra",
    "gerar_relatorio",
    "pesquisar_internet",
    "ler_pagina_web",
}

# Tools disponiveis via servidor MCP. A fonte da verdade e o executor
# `tools/hermes_tools.py`: se ha handler la, a tool roda fora do copiloto web e
# pode ser exposta. Derivar em vez de manter uma lista manual evita o modo de
# falha antigo — anunciar em `tools/list` uma tool que falha ao ser chamada.
#
# A intersecao com _CATALOG e deliberada: `tools/list` so publica o que tem
# descricao no catalogo E schema em `schemas/`, entao um handler novo sem
# schema simplesmente nao aparece, em vez de quebrar o cliente.
def _mcp_enabled() -> set[str]:
    from tools import hermes_tools

    return {name for name in hermes_tools.list_tools() if name in _CATALOG}


# Tools que nao fazem sentido faladas continuam fora do canal de voz mesmo
# estando disponiveis via MCP (formulario, imagem, relatorio longo, lote).
_VOICE_EXCLUDED: set[str] = {
    "gerar_rascunho_formulario",
    "gerar_imagem",
    "gerar_relatorio",
    "preparar_edicao_em_lote",
    "preparar_reagendamento_em_lote",
    "preparar_remocao_horarios_em_lote",
    "confirmar_edicao_em_lote",
    "confirmar_reagendamento_em_lote",
    "ler_documento_na_integra",
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


def is_mcp_enabled(tool_name: str) -> bool:
    return tool_name in _mcp_enabled()


def is_voice_enabled(tool_name: str) -> bool:
    return tool_name in _mcp_enabled() and tool_name not in _VOICE_EXCLUDED


def list_mcp_enabled_tools() -> list[str]:
    """Nomes do catalogo com executor real ligado ao servidor MCP, na ordem do catalogo."""
    enabled = _mcp_enabled()
    return [name for name in _CATALOG if name in enabled]


def has_schema(tool_name: str) -> bool:
    try:
        get_schema(tool_name)
        return True
    except (FileNotFoundError, OSError):
        return False


def get_required_params(tool_name: str) -> list[str]:
    schema = get_schema(tool_name)
    return schema.get("parameters", {}).get("required", [])
