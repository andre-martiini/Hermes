import json
import os

from tools.inventory import (
    DominioRede,
    Idempotencia,
    LeituraEscrita,
    Reversibilidade,
    get_inventory_entry,
)

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
    "consultar_promocoes_autonomia_sugeridas": "Lista sugestões de promoção de autonomia por tipo de rascunho WhatsApp que esperam decisão",
    "decidir_promocao_autonomia": "Aplica a decisão do usuário (aceitar, adiar, nunca) sobre a promoção de autonomia de um tipo de rascunho WhatsApp",
    "revogar_promocao_autonomia": "Revoga a promoção de autonomia de um tipo já promovido, voltando a exigir aprovação prévia no Telegram",
    "obter_projeto_bolsas_publico": "Consulta dados publicos de um projeto de bolsas por ID",
    "registrar_inscricao_bolsa_publica": "Registra uma inscricao publica em um projeto de bolsas",
    "consultar_financas_v2": "Consulta detalhada do financeiro interno: rendas, obrigações, metas e transações",
    "registrar_item_financeiro_v2": "Registra uma nova movimentação (renda ou despesa) no financeiro interno",
    "calculadora": "Calculadora dedicada para calculos matematicos ad-hoc ou projecoes.",
    "schedule_whatsapp_message": "Agenda ou envia uma mensagem de WhatsApp para um contato.",
    "criar_rascunho_whatsapp": "Cria um rascunho de WhatsApp e envia card de aprovação em um toque ao Telegram do dono",
    "listar_rascunhos_pendentes": "Lista rascunhos de mensagens de WhatsApp aguardando aprovação no Telegram",
    "aprovar_rascunho_whatsapp": "Aprova um rascunho de WhatsApp pendente no outbox (via Cowork) para entrega imediata",
    "descartar_rascunho_whatsapp": "Descarta um rascunho de WhatsApp pendente no outbox (via Cowork)",
    "cancelar_envio_whatsapp": "Cancela um envio de WhatsApp já aprovado/agendado (pending/notified) antes de o worker entregá-lo",
    # Portao humano via Telegram para o conector Claude-Argos: aprovar plano,
    # enfileirar execucao e mesclar PR sao "ato humano" por desenho no Argos;
    # este trio faz o Andre decidir pelo Telegram antes de qualquer uma delas
    # ser chamada.
    "solicitar_autorizacao_argos": "Pede ao André, por um card no Telegram, autorização para aprovar um plano, enfileirar uma execução ou mesclar um PR no Argos",
    "consultar_autorizacao_argos": "Consulta o estado de uma solicitação de autorização do Argos (aguardando, aprovado, recusado ou expirado)",
    "consumir_autorizacao_argos": "Marca uma autorização aprovada do Argos como usada — uso único, chamar só imediatamente antes de agir no Argos",
    "confirmar_acao": "Executa uma confirmação MCP persistida uma única vez",
    "pausar_conversa": "Enfileira uma resposta de pausa no WhatsApp e agenda a retomada após confirmação explícita",
    "criar_rascunho_email": "Cria um rascunho Gmail com anexos por referência; nunca envia a mensagem",
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
    "listar_respostas_pendentes": "Lista a fila de respostas pendentes, com opção de auditar itens filtrados",
    "dispensar_resposta_pendente": "Marca um item da fila de respostas pendentes como tratado, para não reaparecer",
    "obter_acao": "Uma acao inteira e SEM TRUNCAMENTO: descricao, notas, plano completo e diario",
    # Ingestao de arquivo: sem ela, anexo so entrava por link de algo que ja
    # estava no Drive, e comprovante nascido fora dele ficava orfao.
    "anexar_arquivo": "Anexa um arquivo a uma acao: grava no Drive, vincula e escreve no diario",
    # O conector do Drive so cria arquivo; atualizar um documento virava criar outro
    # (ID e link novos, versao antiga solta). Esta troca o conteudo no MESMO arquivo.
    "atualizar_arquivo_drive": "Atualiza o conteudo de um arquivo que ja existe no Drive (Google Doc ou texto), no mesmo ID e link",
    "preparar_upload": "Devolve URL assinada para subir arquivo local sem passa-lo pela conversa",
    "remover_anexo": "Remove um anexo da acao, preservando a trilha de auditoria do diario",
    # Fatura de cartao: o que um boleto nao tem — em que se gastou e o que
    # ja esta comprometido nos meses seguintes.
    "consultar_fatura_cartao": "Consulta os lancamentos da fatura do cartao, com total por estabelecimento",
    "consultar_compromissos_futuros": "Projeta quanto de cada mes futuro ja esta comprometido por compras parceladas",
    # WhatsApp: a consolidacao ja existia e so era acionavel pela Caixa de
    # Entrada na web. Leitura de conteudo exige chat na allowlist.
    "listar_conversas_whatsapp": "Lista as conversas de WhatsApp, marcando quais estao monitoradas",
    "sincronizar_conversas_whatsapp": "Solicita ao worker do WhatsApp uma sincronização imediata do catálogo de conversas; use se um grupo recém-adicionado não aparecer e depois repita a busca",
    "ler_mensagens_whatsapp": "Le as mensagens de uma conversa monitorada, para escolher o recorte",
    "consolidar_whatsapp": "Consolida um recorte de mensagens: transcreve midia e sintetiza resumo e itens de acao",
    "ler_consolidacao_whatsapp": "Le uma consolidacao inteira, ou as mais recentes de uma conversa",
    "consultar_envio_whatsapp": "Estado real de uma mensagem enfileirada: enviada, na fila ou falhou",
    # Investimentos: o Hermes nao decide nem executa nada: le a carteira do
    # servico `decisao-investimentos` e registra o que o USUARIO declarou ter
    # feito na corretora. Quem decide e o motor deterministico do outro lado.
    "consultar_investimentos": "Consulta a carteira de investimentos: posicao, valor, caixa, aporte total e rendimento contra o CDI",
    "registrar_aporte_investimento": "Registra dinheiro novo que o usuario enviou a corretora (SOMA ao total aportado)",
    "registrar_execucao_investimento": "Registra a posicao que o usuario passou a ter depois de executar uma ordem na corretora",
    # Fila de atencao unificada
    "obter_fila_atencao": "Lista a fila de atencao unificada: itens de acoes, conversas e rotinas que demandam decisao",
    "resolver_item_atencao": "Resolve, descarta ou delega um item da fila de atencao, registrando o desfecho",
    # Pedidos de trabalho autonomo
    "consultar_pedidos_agente": "Lista pedidos de trabalho autonomo enfileirados pelo sistema para o agente executar",
    "concluir_pedido_agente": "Conclui ou registra erro em um pedido de trabalho autonomo executado pelo agente",
    # Observabilidade de execucoes do agente
    "registrar_execucao_agente": "Registra uma execucao de rotina agendada do agente para observabilidade e metricas",
    "consultar_execucoes_agente": "Consulta o historico de execucoes recentes de rotinas agendadas do agente",
    # Modo Secretário no WhatsApp (Contato Prioritário)
    "preparar_contato_prioritario_secretario": "Registra um briefing prioritário para o Modo Secretário no WhatsApp atender um contato específico durante a indisponibilidade do André",
    "consultar_contatos_prioritarios_secretario": "Lista os briefings prioritários cadastrados para o Modo Secretário no WhatsApp",
    "cancelar_contato_prioritario_secretario": "Cancela ou encerra antecipadamente o briefing prioritário de um contato no Modo Secretário",
    # Modo Secretário no WhatsApp (ativação self-service)
    "ativar_modo_secretario": "Ativa o Modo Secretário no WhatsApp com contatos autorizados (ou escopo universal de todos os individuais/grupos), janela de ativação (início e fim arbitrários) e orientações opcionais",
    "desativar_modo_secretario": "Desativa imediatamente o Modo Secretário no WhatsApp",
    "consultar_status_modo_secretario": "Consulta o status atual do Modo Secretário (ativo, contatos na allowlist e expiração)",
    # Motor de política de autonomia (P02 passo 7, autonomy/policy.py) — leitura
    # e simulação, nunca aplicação direta: `preparar_politica` só devolve um
    # diff, nunca persiste nada sozinho.
    "consultar_politica": "Consulta a política de autonomia vigente para um escopo: permissões, limites, versão e origem",
    "simular_politica": "Avalia um lote de pedidos hipotéticos contra a política de autonomia, sem aplicar nada",
    "preparar_politica": "Prepara uma proposta de mudança na política de autonomia contra uma versão base, devolvendo um diff explícito",
    # Hermes Vídeo (functions/video/) — Fase 1: criar e consultar, sem custo.
    "video_criar_projeto": "Cria um projeto de vídeo a partir do roteiro aprovado (cenas, narração, bíblia visual) e devolve a estimativa de custo; não gera nada pago",
    "video_status": "Estado de um projeto de vídeo: etapa atual, cenas, progresso dos clipes, custo estimado e real, link do vídeo",
}

_NEEDS_CONFIRMATION: set[str] = {
    "resolver_item_atencao",
    "dispensar_resposta_pendente",
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
    "decidir_promocao_autonomia",
    "revogar_promocao_autonomia",
    "mutar_portal_compras_publico",
    "registrar_inscricao_bolsa_publica",
    "registrar_item_financeiro_v2",
    "schedule_whatsapp_message",
    "criar_rascunho_whatsapp",
    "pausar_conversa",
    "criar_rascunho_email",
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
    "atualizar_arquivo_drive",
    "remover_anexo",
    # Cria job de processamento e consome transcricao paga de midia.
    "consolidar_whatsapp",
    # Cria um pedido interno para o worker atualizar o catálogo de chats.
    "sincronizar_conversas_whatsapp",
    "editar_acao",
    "editar_acoes_em_lote",
    "reagendar_acoes_em_lote",
    # Contraparte de gravacao das `preparar_*`: e aqui que a mutacao acontece.
    "confirmar_edicao_acao",
    "confirmar_edicao_em_lote",
    "confirmar_reagendamento_em_lote",
    # Gravam na carteira real. Atencao: estar AQUI nao gateia nada — este
    # conjunto so alimenta o metadado `mutates` do `tools/list`. Quem exige a
    # dupla chamada e `mcp_server._CONFIRMACAO_OBRIGATORIA`, onde as duas tambem
    # estao, justamente porque a politica do canal esta vazia desde 27/08/2026.
    "registrar_aporte_investimento",
    "registrar_execucao_investimento",
    # Modo Secretário no WhatsApp (Contato Prioritário)
    "preparar_contato_prioritario_secretario",
    "consultar_contatos_prioritarios_secretario",
    "cancelar_contato_prioritario_secretario",
    # Modo Secretário no WhatsApp (mutam system/settings)
    "ativar_modo_secretario",
    "desativar_modo_secretario",
    # Aprovação, descarte e cancelamento de rascunhos/envios de WhatsApp via Cowork
    "aprovar_rascunho_whatsapp",
    "descartar_rascunho_whatsapp",
    "cancelar_envio_whatsapp",
    # Portao de autorizacao Telegram para o conector Claude-Argos: as duas que
    # mutam estado (pedir e consumir); consultar e so leitura, fica de fora.
    "solicitar_autorizacao_argos",
    "consumir_autorizacao_argos",
    # Grava o projeto de vídeo (custo zero; as tools pagas chegam na Fase 4).
    "video_criar_projeto",
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
    # Escrita de dinheiro por voz nao: um numero mal transcrito ("mil e
    # quinhentos") grava valor errado num registro que acumula e que o servico
    # nao sabe estornar. Consultar por voz continua liberado.
    "registrar_aporte_investimento",
    "registrar_execucao_investimento",
    # `simular_politica` recebe um lote de pedidos estruturados (cada um com
    # principal, ferramenta, classe de efeito etc.) — inviável de ditar; e
    # `preparar_politica` propõe mudança na própria política de confirmação
    # obrigatória, decisão de dono que voz não deveria facilitar por engano.
    "simular_politica",
    "preparar_politica",
    # Roteiro de vídeo é uma estrutura de cenas com narração e bíblia visual —
    # escrito e aprovado na conversa com o Claude, não ditado. Status continua falado.
    "video_criar_projeto",
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


def campos_obrigatorios_ausentes(tool_name: str, arguments: dict) -> list[str]:
    """Nomes dos campos que o schema publicado (`tools/list`) marca como
    `required` e que nao vieram em `arguments` — ausentes da chave ou com
    valor `None`. Lista vazia quer dizer "nada de errado aqui".

    P03 passo 2 ("validacao de argumentos"), sub-entrega 2/N, primeira fatia: so a metade
    "obrigatorio ausente", nao checagem de tipo. E a fatia mais segura de
    introduzir sem risco de rejeitar uma chamada que hoje funciona — um
    campo que o proprio schema ja declara `required` nunca foi, por
    definicao, uma chamada suportada quando ausente; o dispatch de hoje so
    nao tem NENHUM preflight que diga isso ao cliente antes de a tool
    tentar rodar (o handler, se checar, devolve string livre tipo
    "ERRO|..."; se nao checar, ou propaga uma excecao Python crua via
    `except Exception` em `mcp_server.py` ou, pior, segue em frente com um
    dado incompleto). Checagem de TIPO (schema `type`) ficou para uma
    sub-entrega separada (P03 sub-entrega 4/N, ver `tipos_invalidos`
    abaixo) -- e mesmo ali so a metade estrutural (`array`/`object`); os
    quatro tipos escalares continuam de fora, porque a investigacao feita
    naquela sub-entrega confirmou o risco suspeitado aqui: handlers reais
    ja toleram deliberadamente um numero como string (ex.: `int(args.get(
    "limite") or 20)`), e uma checagem escalar estrita rejeitaria chamadas
    que hoje funcionam.

    Falha aberta, nunca fechada: schema ausente, ilegivel ou com formato
    inesperado (achado da revisao adversarial desta sub-entrega: um
    `except` estreito demais aqui viraria "falha fechada" na pratica, via o
    `except Exception` de nivel superior em `mcp_server.py` transformando
    qualquer excecao nao prevista num erro generico para TODA chamada
    daquela tool — o oposto exato desta garantia) nao bloqueia a chamada
    (mesma filosofia de `_handle_tools_list` ao omitir uma tool com schema
    quebrado em vez de derrubar o catalogo inteiro) — o objetivo e dar um
    erro mais claro quando ha certeza do problema, nunca inventar um
    bloqueio novo por causa de uma falha de infraestrutura de leitura de
    schema.
    """
    try:
        schema = get_schema(tool_name)
        parametros = schema.get("parameters") or {}
        required = parametros.get("required") or []
        if not isinstance(required, list) or not isinstance(arguments, dict):
            return []
        return [campo for campo in required
                if isinstance(campo, str) and (campo not in arguments or arguments.get(campo) is None)]
    except (FileNotFoundError, OSError, json.JSONDecodeError, AttributeError, TypeError):
        return []


_TIPOS_JSON_PARA_PYTHON = {
    "array": list,
    "object": dict,
}


# Achado da revisao adversarial desta sub-entrega: `subtarefas.py::
# normalizar_entrada_plano` (gatilho: incidente real de 28/08/2026, ver a
# docstring dela) ja aceita deliberadamente uma STRING com o JSON de uma
# lista de etapas e a decodifica antes de usar -- string que nao e JSON
# valido de lista ainda e recusada, so que pelo proprio handler (mensagem
# especifica de `PlanoInvalido`), nao por aqui. Sem esta excecao, o
# preflight bloquearia uma chamada que o handler ja trata com seguranca,
# repetindo com um campo "quase certo" o mesmo risco que a sub-entrega 2/N
# identificou para os tipos escalares (ver docstring de
# `campos_obrigatorios_ausentes`). Achado via `tools/hermes_tools.py:1050`
# (`criar_acao_no_sistema`, chama `subtarefas.converter_plano` que chama
# `normalizar_entrada_plano`) e `tools/telegram_extended.py:361-378`
# (`editar_plano_acao`, resolve os apelidos `novo_plano`/`plano_acao`/
# `etapas` e chama `subtarefas.mesclar_plano`, que tambem chama
# `normalizar_entrada_plano`). Isto NAO generaliza para outros campos
# array/object (ex.: `tags`/`alteracoes` de `editar_acao`, que nao tem essa
# normalizacao e onde uma string preenchida seria silenciosamente tratada
# como se fosse a lista/dict) -- por isso a excecao e uma lista fechada de
# pares (tool, campo) com tolerancia comprovada, nao uma regra geral tipo
# "aceitar string se for JSON valido do tipo certo".
_CAMPOS_COM_TOLERANCIA_A_STRING_JSON = {
    ("criar_acao_no_sistema", "plano_acao"),
    ("editar_plano_acao", "novo_plano"),
    ("editar_plano_acao", "plano_acao"),
    ("editar_plano_acao", "etapas"),
}


def tipos_invalidos(tool_name: str, arguments: dict) -> list[dict]:
    """Campos presentes em `arguments` cujo valor não bate com o tipo
    ESTRUTURAL (`array`/`object`) que o schema publicado (`tools/list`)
    declara para eles. Lista vazia quer dizer "nada de errado aqui"; cada
    item devolvido é `{"campo": ..., "esperado": ..., "recebido": ...}`.

    P03 passo 2, sub-entrega 4/N: a fatia de "checagem de tipo" que a
    sub-entrega 2/N (ver `campos_obrigatorios_ausentes` acima) deixou de
    fora deliberadamente -- mas só metade dela. Cobre unicamente os dois
    tipos ESTRUTURAIS do JSON Schema (`array` deve ser lista, `object` deve
    ser dict) e DELIBERADAMENTE NÃO cobre os quatro tipos escalares
    (`string`/`integer`/`number`/`boolean`).

    Essa fronteira não é arbitrária -- é o resultado de investigar os 105
    schemas e os handlers reais que os consomem (`tools/hermes_tools.py`)
    antes de implementar, não uma suposição. Os campos escalares numéricos/
    booleanos já são tratados com tolerância DELIBERADA pelo próprio
    handler hoje: `int(args.get("limite") or 20)` aceita de bom grado tanto
    `20` quanto `"20"`; `bool(args.get("apenas_ativos"))` aceita qualquer
    valor truthy. Uma checagem estrita aqui rejeitaria uma chamada "meio
    certa" que HOJE FUNCIONA -- exatamente o risco que a sub-entrega 2/N
    identificou e adiou (ver docstring de `campos_obrigatorios_ausentes`).
    Os campos estruturais não têm essa mesma tolerância pré-existente:
    `alteracoes = dict(args.get("alteracoes") or {})` (`hermes_tools.py`,
    `editar_acao`) levanta um `ValueError` opaco se vier uma string no
    lugar de objeto; `tags = args.get("tags") or []` (`hermes_tools.py:
    1052`) é pior -- se vier uma string NÃO-vazia, `"abc" or []` resolve
    para `"abc"`, e o código segue tratando uma STRING como se fosse a
    lista, sem erro nenhum ali, até explodir (ou, pior, iterar caractere
    por caractere silenciosamente) num ponto mais fundo e mais difícil de
    depurar. Para os dois tipos estruturais não há tolerância a preservar,
    e o risco inclui corrupção silenciosa de dado, não só exceção crua.

    Só verifica campos PRESENTES (ausência/`None` é responsabilidade de
    `campos_obrigatorios_ausentes`, não desta função) -- aplica a campos
    obrigatórios e opcionais igualmente, porque o risco (crash ou
    corrupção silenciosa) independe de o campo ser obrigatório.

    Exceção fechada e documentada (ver `_CAMPOS_COM_TOLERANCIA_A_STRING_JSON`
    acima) para os poucos pares (tool, campo) onde o próprio handler já
    normaliza uma string JSON com segurança -- sem ela este preflight
    bloquearia uma chamada válida hoje.

    Falha aberta, mesma filosofia de `campos_obrigatorios_ausentes`: schema
    ausente, ilegível ou malformado nunca bloqueia a chamada por conta
    própria.
    """
    try:
        schema = get_schema(tool_name)
        propriedades = (schema.get("parameters") or {}).get("properties") or {}
        if not isinstance(propriedades, dict) or not isinstance(arguments, dict):
            return []
        problemas = []
        for campo, prop_schema in propriedades.items():
            if not isinstance(prop_schema, dict):
                continue
            tipo_esperado = prop_schema.get("type")
            tipo_python = _TIPOS_JSON_PARA_PYTHON.get(tipo_esperado)
            if tipo_python is None:
                continue  # so array/object nesta fatia -- ver docstring acima
            if campo not in arguments or arguments.get(campo) is None:
                continue  # ausencia e responsabilidade de campos_obrigatorios_ausentes
            if (tool_name, campo) in _CAMPOS_COM_TOLERANCIA_A_STRING_JSON:
                continue  # handler ja normaliza string JSON com seguranca
            valor = arguments[campo]
            if not isinstance(valor, tipo_python):
                problemas.append({
                    "campo": campo,
                    "esperado": tipo_esperado,
                    "recebido": type(valor).__name__,
                })
        return problemas
    except (FileNotFoundError, OSError, json.JSONDecodeError, AttributeError, TypeError):
        return []


def valores_invalidos(tool_name: str, arguments: dict) -> list[dict]:
    """Campos presentes em `arguments` cujo valor não está entre os
    permitidos pela lista `enum` que o schema publicado (`tools/list`)
    declara para eles. Lista vazia quer dizer "nada de errado aqui"; cada
    item devolvido é `{"campo": ..., "esperado": ..., "recebido": ...}`,
    onde `esperado` é a própria lista `enum` e `recebido` é o valor
    recebido (não o tipo dele — aqui o que importa é pertencimento, não
    tipo).

    P03 passo 2, sub-entrega 5/N: terceira fatia da validação de
    argumentos, depois de presença (sub-entrega 2/N) e tipo estrutural
    array/object (sub-entrega 4/N). Levantamento nos 105 schemas (10/09/2026)
    encontrou 8 propriedades de nível superior, em 7 tools, que declaram
    `enum` — todas do tipo `string` (`decidir_promocao_autonomia.decisao`,
    `obter_fila_atencao.estado`/`origem`, `registrar_execucao_agente.status`,
    `registrar_execucao_investimento.ativo`,
    `registrar_item_financeiro_v2.tipo`, `resolver_item_atencao.estado`,
    `solicitar_autorizacao_argos.tipo`). Nenhuma se sobrepõe a
    `tipos_invalidos`: como esta função só cobre `array`/`object`, um campo
    `string` com `enum` passa direto por ela e só é avaliado aqui — não há
    conflito de prioridade a resolver entre as duas.

    Escopo deliberadamente igual ao de `tipos_invalidos`: só propriedades de
    NÍVEL SUPERIOR (as chaves diretas de `parameters.properties`). Dois
    schemas (`criar_acao_no_sistema.json`, `editar_plano_acao.json`)
    declaram `enum` só ANINHADO, no schema de cada item do array
    `plano_acao`/`etapas` (o campo `estado` de cada etapa) — isso fica fora
    do escopo pela mesma razão estrutural que já vale para
    `tipos_invalidos`: o campo de nível superior que contém esse array pode
    chegar como string JSON bruta (ver
    `_CAMPOS_COM_TOLERANCIA_A_STRING_JSON`), e validar o conteúdo aninhado
    exigiria decodificar essa string aqui — vira parser de plano, não
    checagem estrutural de preflight. Como a iteração é só sobre
    `parameters.properties` de nível superior, esse `enum` aninhado nunca
    aparece nela; não precisou de uma exceção explícita como a dos campos
    tolerantes a string JSON.

    Só verifica campos PRESENTES (ausência/`None` é responsabilidade de
    `campos_obrigatorios_ausentes`) e só quando o schema de fato declara uma
    lista `enum` não vazia — a maioria dos campos não declara, e para esses
    a função não tem nada a dizer.

    Exceção fechada e documentada (ver `_CAMPOS_COM_ENUM_TOLERANTE_A_CASE`
    abaixo) para os poucos pares (tool, campo) onde o próprio handler já
    normaliza maiúscula/minúscula e espaço nas pontas antes de comparar --
    sem ela este preflight, em comparação exata, bloquearia uma chamada que
    esses handlers aceitam hoje (achado da 1ª rodada de revisão adversarial
    desta sub-entrega, mesma classe de regressão que motivou
    `_CAMPOS_COM_TOLERANCIA_A_STRING_JSON` em `tipos_invalidos`). A exceção
    é DELIBERADAMENTE FECHADA, não uma tolerância geral -- a 2ª rodada de
    revisão (feita sobre esta correção, não sobre o diff original) achou
    que uma tolerância geral teria sido pior que o problema original:
    `obter_fila_atencao` (`estado`/`origem`) não tem handler tolerante --
    `atencao.coletar_fila_atencao` usa o valor cru num filtro `==` do
    Firestore, sem normalizar nada. Com tolerância geral, `estado="ABERTO"`
    passaria pelo preflight, chegaria ao filtro do Firestore, não bateria
    com o valor armazenado (sempre minúsculo) e devolveria SILENCIOSAMENTE
    zero itens, sem erro nenhum -- indistinguível de "nada pendente", pior
    que o excesso de rigor que esta sub-entrega tentava evitar. Por isso a
    tolerância vale só para os pares com tolerância comprovada no próprio
    handler (ver a lista abaixo), nunca por padrão.

    Falha aberta, mesma filosofia de `campos_obrigatorios_ausentes` e
    `tipos_invalidos`: schema ausente, ilegível ou malformado nunca bloqueia
    a chamada por conta própria.
    """
    try:
        schema = get_schema(tool_name)
        propriedades = (schema.get("parameters") or {}).get("properties") or {}
        if not isinstance(propriedades, dict) or not isinstance(arguments, dict):
            return []
        problemas = []
        for campo, prop_schema in propriedades.items():
            if not isinstance(prop_schema, dict):
                continue
            valores_permitidos = prop_schema.get("enum")
            if not isinstance(valores_permitidos, list) or not valores_permitidos:
                continue  # so campos que de fato declaram enum nao vazio
            if campo not in arguments or arguments.get(campo) is None:
                continue  # ausencia e responsabilidade de campos_obrigatorios_ausentes
            valor = arguments[campo]
            tolerante = (tool_name, campo) in _CAMPOS_COM_ENUM_TOLERANTE_A_CASE
            if not _bate_algum_valor_permitido(valor, valores_permitidos, tolerante):
                problemas.append({
                    "campo": campo,
                    "esperado": valores_permitidos,
                    "recebido": valor,
                })
        return problemas
    except (FileNotFoundError, OSError, json.JSONDecodeError, AttributeError, TypeError):
        return []


# Achado da 1ª rodada de revisao adversarial da sub-entrega 5/N: estes 4
# handlers ja normalizam o valor recebido antes de comparar contra o mesmo
# conjunto que o schema declara em `enum` -- `promocao_autonomia.py:158`
# (`decisao_limpa = str(decisao or "").strip().lower()`),
# `investimentos.py:191` (`ativo = str(ativo or "").strip().upper()`),
# `agent_runs.py:48` (`status_limpo = str(status or STATUS_SUCESSO)
# .strip().lower()`), `argos_autorizacao.py:133` (`tipo = str(tipo or "")
# .strip()`; so espaco, sem case). Lista FECHADA de pares (tool, campo) com
# tolerancia comprovada -- NAO generaliza para os outros 4 campos com enum
# (`obter_fila_atencao.estado`/`origem`, `resolver_item_atencao.estado`,
# `registrar_item_financeiro_v2.tipo`), que comparam em modo exato nos
# handlers e, no caso de `obter_fila_atencao`, nem validam -- usam o valor
# cru num filtro `==` do Firestore (ver docstring de `valores_invalidos`
# para o porque uma tolerancia geral teria sido uma regressao nova, achada
# na 2a rodada de revisao adversarial sobre esta mesma correcao).
_CAMPOS_COM_ENUM_TOLERANTE_A_CASE = {
    ("decidir_promocao_autonomia", "decisao"),
    ("registrar_execucao_investimento", "ativo"),
    ("registrar_execucao_agente", "status"),
    ("solicitar_autorizacao_argos", "tipo"),
}


def _bate_algum_valor_permitido(valor, valores_permitidos: list, tolerante_a_case: bool) -> bool:
    """`True` se `valor` está em `valores_permitidos` — por igualdade exata
    sempre, e, só quando `tolerante_a_case` é `True` (par (tool, campo) na
    lista fechada `_CAMPOS_COM_ENUM_TOLERANTE_A_CASE`) e `valor` é `str`,
    também por igualdade tolerante a maiúscula/minúscula e espaço nas
    pontas contra qualquer permitido que também seja `str` (ver docstring
    de `valores_invalidos` para o porquê da lista ser fechada).
    """
    if valor in valores_permitidos:
        return True
    if not tolerante_a_case or not isinstance(valor, str):
        return False
    normalizado = valor.strip().casefold()
    return any(
        isinstance(permitido, str) and permitido.strip().casefold() == normalizado
        for permitido in valores_permitidos
    )


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


def mcp_annotations(tool_name: str) -> dict:
    """`ToolAnnotations` do MCP (`readOnlyHint`/`destructiveHint`/
    `openWorldHint`/`idempotentHint`) para o catalogo publicado em
    `tools/list` -- P03 passo 3 do plano de autonomia ("Adicionar
    outputSchema, structuredContent, annotations e envelope aos caminhos
    compativeis"). `readOnlyHint`/`destructiveHint` vieram da sub-entrega
    6/N; `openWorldHint`, da sub-entrega 7/N; `idempotentHint`, das
    sub-entregas 16/N a 23/N (53 das ~61 tools de escrita/leitura_e_escrita
    elegiveis ja classificadas -- ver `Idempotencia` em `tools/inventory.py`;
    o universo elegivel cresceu de ~59 para ~61 entre a sub-entrega 19/N e a
    20/N por causa de tools novas adicionadas por PRs de funcionalidade fora
    deste plano, `atualizar_arquivo_drive` e `sincronizar_conversas_
    whatsapp`, ja classificadas por quem as implementou). Das ~8 restantes,
    NENHUMA ficou "nunca investigada" apos a sub-entrega 23/N -- todas as
    tools de escrita/leitura_e_escrita elegiveis ja foram lidas pelo menos
    uma vez; as que faltam ficaram deliberadamente SEM classificacao por
    ambiguidade genuina (ver paragrafo abaixo).
    `outputSchema`/`structuredContent`/envelope seguem fora de escopo --
    exigem definir um contrato de dados por tool, ver docs/autonomia/execucao.md.

    `readOnlyHint` vem de `leitura_escrita` e `destructiveHint` de
    `reversibilidade` -- ambos do inventario investigado em P03 sub-entrega
    1/N (`tools/inventory.py`).

    `openWorldHint` vem do campo `dominio_rede` (P03 sub-entrega 7/N,
    `DominioRede`), NAO de `necessidade_de_rede` direto: uma tool que fala
    com o Google Calendar do dono opera num dominio fechado e conhecido (a
    agenda do proprio dono), nao um "mundo aberto" de entidades arbitrarias
    -- so tools como `pesquisar_internet`/`ler_pagina_web` se qualificam de
    verdade. Mapear `necessidade_de_rede` direto para `openWorldHint`
    produziria metadado ERRADO para a maioria das tools com rede (Calendar,
    Gmail, Drive, Telegram, Gemini) -- pior que nao declarar nada: sao
    metadados, nao controles de autorizacao (secao 6.1 do plano), mas um
    cliente MCP pode usa-los para decidir se pede confirmacao extra, e
    metadado errado (em qualquer direcao) e pior que omissao.

    Das 28 tools com `necessidade_de_rede=True`, 21 tem `dominio_rede`
    classificado (19 `FECHADO`, 2 `ABERTO`, ver `tools/inventory.py`); 7
    ficam deliberadamente SEM classificacao (`dominio_rede=None`, hint
    omitido, cai no default cauteloso da especificacao) por serem
    genuinamente ambiguas mesmo apos leitura direta do codigo:
    `confirmar_acao` (delega para uma de varias tools, alvo variavel, ver
    `nota` no inventario), `consultar_processo_sipac`/
    `acompanhar_processo_sipac` (scraper de portal institucional externo,
    fora do controle do Hermes, sujeito a mudanca de estrutura sem aviso),
    `anexar_arquivo` (pode envolver "URL arbitraria conforme a origem",
    textualmente o caso `ABERTO`, mas nem sempre), e as tres tools de
    `investimentos` (servico externo que por sua vez busca dados de
    mercado via yfinance/SGS-Bacen -- fora do controle direto do Hermes e
    do proprio servico).

    `idempotentHint` vem do campo `idempotencia` (P03 sub-entrega 16/N,
    `Idempotencia`) -- pede saber, por HANDLER, se chamar de novo com os
    MESMOS argumentos tem efeito adicional no ambiente; nenhum outro campo
    do inventario sustenta essa pergunta (nem `reversibilidade`, que e
    sobre "da para desfazer depois", nem `dominio_rede`, que e sobre O QUE a
    tool alcança pela rede, nao sobre REPETIR a chamada sem custo). So faz
    sentido quando `readOnlyHint` e False, mesma convencao de
    `destructiveHint` -- e so e emitido quando `entry.idempotencia` esta de
    fato classificado.

    9 tools investigadas nesta primeira fatia (leitura direta do handler
    real, nao do nome/descricao): `criar_acao_no_sistema`,
    `salvar_memoria_global`, `dispensar_resposta_pendente` e
    `concluir_pedido_agente` sao IDEMPOTENTE (dedup por chave exata,
    dedup por similaridade de embedding, `.set()` com ID deterministico, e
    transacao Firestore com `already_decided`, respectivamente -- ver
    `nota` de cada uma em `tools/inventory.py`). IDEMPOTENTE aqui nao
    significa "sem limite de tempo": `criar_acao_no_sistema` so dedupla
    DENTRO da janela de `ttl_minutes=15` de `claim_action_dedup_slot`
    (main.py) -- repetir a MESMA chamada depois desse intervalo cria uma
    acao nova, ver `test_action_dedup_slot.py` para as duas metades desse
    comportamento provadas. `agendar_lembrete_acao`,
    `registrar_no_diario`, `editar_acao`, `resolver_item_atencao` e
    `registrar_execucao_agente` sao NAO_IDEMPOTENTE (todas por `append`
    sem chave de dedup -- `ArrayUnion`/`ArrayUnion` indireto via
    `registrar_no_diario`, ou `col.add()` sem ID deterministico).

    Mais 9 tools investigadas na sub-entrega 17/N: `registrar_saude` e
    `consultar_investimentos` sao IDEMPOTENTE (upsert por dia+campo com
    consulta antes de escrever, e dedup por tag `investimentos-decisao-
    {mes}` antes de criar, respectivamente -- ver `nota` de cada uma).
    Assim como o TTL de `criar_acao_no_sistema`, nenhuma das duas usa
    exclusao mutua atomica (`create()`/transacao) -- e "consulta, depois
    escreve" quando chamadas se sobrepoem de verdade (duas tentativas em
    voo ao mesmo tempo, nao um retry sequencial depois de receber a
    resposta) pode, em teoria, deixar as duas passarem pela checagem antes
    de qualquer uma escrever; nao corrigido nesta fatia, so documentado
    (achado da revisao adversarial da sub-entrega 17/N). `registrar_
    transacao_financeira_publica`, `registrar_item_financeiro_v2`,
    `pausar_conversa`, `criar_rascunho_email`, `registrar_interacao_
    contato`, `registrar_aporte_investimento` e `registrar_execucao_
    investimento` sao NAO_IDEMPOTENTE (auto-ID sem dedup, ou efeito
    externo documentado no proprio modulo -- ver `nota` de cada uma).

    Mais 9 tools investigadas na sub-entrega 18/N: `desativar_modo_
    secretario`, `cancelar_contato_prioritario_secretario` e `editar_
    objetivo_estrategico` sao IDEMPOTENTE (reset determinístico de um
    singleton sem campo variável; `.update()` sem checar status atual,
    convergindo para o mesmo status a cada chamada; `.update()`
    determinístico por `objetivo_id`, sem append -- ver `nota` de cada
    uma). `ativar_modo_secretario`, `preparar_contato_prioritario_
    secretario`, `remover_anexo`, `criar_objetivo_estrategico`,
    `preparar_upload` e `anexar_arquivo` sao NAO_IDEMPOTENTE: as duas
    primeiras recalculam um prazo (`desativa_em`/`valido_ate`) a partir de
    "agora" a cada chamada, estendendo-o de verdade a cada repetição; as
    demais quatro criam um recurso novo por chamada (ID automático do
    Firestore, ID novo do Drive, token aleatório, ou `ArrayUnion` com
    timestamp novo) sem nenhuma chave de dedup. Duas tools do mesmo módulo
    `strategy_tools.py` foram investigadas e deliberadamente deixadas SEM
    classificação (mesmo critério de `revogar_promocao_autonomia`, sub-
    entrega 16/N -- "um hint errado é pior que a omissão"): `excluir_
    objetivo_estrategico` (repetir depois do primeiro sucesso devolve erro
    em vez de um "já excluído" gracioso, embora o AMBIENTE não mude mais)
    e `gerenciar_item_estrategico` (o comportamento depende do parâmetro
    `acao` interno à tool -- os quatro ramos têm respostas diferentes à
    pergunta de idempotência, um hint único não os descreveria
    honestamente).

    Mais 9 tools investigadas na sub-entrega 19/N: `salvar_pop_global`,
    `atualizar_personalidade` e `resolver_conflito_memoria` sao
    IDEMPOTENTE (dedup por título/gatilho antes de escrever; `.set(merge=
    True)` num documento singleton; e escrita sempre por `memoria_id` já
    conhecido em vez de ID novo, respectivamente -- ver `nota` de cada
    uma). `registrar_correcao_procedimento`, `resolver_conflito_
    procedimento`, `editar_plano_acao`, `gerar_relatorio`, `gerar_imagem`
    e `criar_rascunho_whatsapp` sao NAO_IDEMPOTENTE (ID novo por `uuid4()`
    sem dedup, ou `ArrayUnion` incondicional a cada chamada -- ver `nota`
    de cada uma). Achado incidental desta sub-entrega: para 6 das 9 tools
    (`salvar_pop_global`, `resolver_conflito_memoria`, `atualizar_
    personalidade`, `resolver_conflito_procedimento`, `editar_plano_acao`,
    `gerar_relatorio`), o HANDLER REAL do servidor MCP é `tools/
    telegram_extended.py::execute` -- as closures homônimas em `main.py`
    (usadas pelo copiloto web) são implementações independentes, não
    delegadas (comentário explícito no próprio código-fonte); a
    classificação e os testes desta sub-entrega leem o código de `tools/
    telegram_extended.py`, não o de `main.py`. Mais 5 tools foram
    investigadas e deliberadamente deixadas SEM classificação por
    ambiguidade genuína, mesmo critério já usado para `revogar_promocao_
    autonomia`/`gerenciar_item_estrategico` (sub-entregas 16/N e 18/N):
    `decidir_elevacao` e `decidir_promocao_autonomia` (falham-fechado na
    repetição, mas devolvem só `{"ok": False, "erro": ...}` sem status
    estruturado que distinga "já decidido" de erro real), `confirmar_acao`
    (idempotência depende da tool delegada em cada chamada, fora do
    escopo de leitura de um handler único), e `mutar_portal_compras_
    publico`/`mutar_lista_compras` (múltiplos ramos por parâmetro `acao`
    interno, com pelo menos um ramo — um toggle de verdade — violando
    idempotência por definição).

    Mais 5 tools investigadas na sub-entrega 20/N, o grupo coeso de
    aprovação/descarte de rascunho + autorização Argos já identificado como
    próxima fatia natural pela sub-entrega 19/N: `aprovar_rascunho_
    whatsapp`, `descartar_rascunho_whatsapp`, `consultar_autorizacao_argos`
    e `consumir_autorizacao_argos` são IDEMPOTENTE (as quatro convergem
    para um status terminal gracioso -- `already_decided`/`already_used` --
    dentro de uma transação Firestore que revalida o status atual antes de
    escrever, ou, no caso de `consultar_autorizacao_argos`, porque a
    escrita passiva de expiração só acontece enquanto o status ainda é
    `aguardando_decisao`; ver `nota` de cada uma). `solicitar_autorizacao_
    argos` é NAO_IDEMPOTENTE (`db.collection(COLLECTION).document()` sem
    argumento gera um ID novo do Firestore e dispara um novo card no
    Telegram a cada chamada, sem nenhuma checagem de dedup por
    tipo/sistema_id/demanda_id -- mesmo padrão já aceito para `criar_
    objetivo_estrategico`/`criar_rascunho_whatsapp`).

    Mais 4 tools investigadas na sub-entrega 21/N, o grupo coeso de edição/
    reagendamento em lote de ações já identificado como próxima fatia
    natural pela sub-entrega 20/N: `confirmar_edicao_em_lote`, `editar_
    acoes_em_lote`, `confirmar_reagendamento_em_lote` e `reagendar_acoes_
    em_lote` são as quatro NAO_IDEMPOTENTE -- `confirmar_edicao_em_lote` e
    `editar_acoes_em_lote` são dois wrappers finos sobre a MESMA callable
    (`main.py::confirmarEdicaoEmLote`), e `confirmar_reagendamento_em_lote`
    e `reagendar_acoes_em_lote` sobre `main.py::confirmarReagendamentoEmLote`
    -- ambas as callables fazem `batch.update(..., 'acompanhamento':
    firestore.ArrayUnion([diary_entry]))` por item, com um `diary_entry`
    novo (timestamp novo) a cada chamada bem-sucedida, incondicionalmente;
    repetir a MESMA chamada com os MESMOS `items` não diverge no valor
    final dos campos editados, mas acrescenta uma nota nova ao diário de
    cada ação a cada vez -- mesmo padrão já usado em `editar_acao` (sub-
    entrega 16/N). `reagendar_acoes_em_lote` acumula um segundo motivo,
    documentado em `nota`: o passo de preparação (`preparar_reagendamento_
    em_lote`) é refeito a cada chamada e, quando a seleção é por
    `filtro_data`, filtra exatamente pelo campo (`data_limite`) que a
    confirmação acabou de mudar -- repetir tende a não encontrar mais nada
    e falhar cedo, uma auto-limitação parcial e dependente dos dados, não
    uma proteção estrutural (ver `nota` de cada uma em `tools/inventory.py`
    para a evidência por handler e os testes que provam o crescimento do
    diário em `test_confirmar_lote_nao_idempotente.py`).

    Mais 1 tool investigada na sub-entrega 22/N, a versão singular do par
    edição/edição-em-lote coberto na sub-entrega 21/N: `confirmar_edicao_
    acao` é NAO_IDEMPOTENTE -- chama a MESMA callable `main.py::
    confirmarEdicaoAcao` que `editar_acao` (sub-entrega 16/N), com a mesma
    raiz (`ArrayUnion` incondicional a cada chamada bem-sucedida). Diferença
    real: ao contrário de `editar_acao`, esta tool repassa `snapshot_ts`
    (parâmetro opcional do schema, devolvido por `preparar_edicao_acao`) à
    callable, que recusa a gravação com `status: 'invalidated'` se o valor
    não bater com `data_atualizacao` atual -- como a própria gravação já
    reescreve esse campo, uma SEGUNDA chamada idêntica com o MESMO
    `snapshot_ts` falha em vez de duplicar a nota, uma auto-limitação real
    que o grupo em lote da sub-entrega 21/N não tem. Não é idempotência de
    verdade (a segunda chamada devolve erro, não o mesmo sucesso) e só se
    aplica quando o chamador de fato envia `snapshot_ts` -- sem ele, mesmo
    comportamento sem proteção de `editar_acao`. Classificação conservadora
    mantida em NAO_IDEMPOTENTE (ver `nota` em `tools/inventory.py` e os
    testes em `test_confirmar_edicao_acao_nao_idempotente.py`).

    Mais 5 tools investigadas na sub-entrega 23/N, fechando a lista das
    "nunca investigadas": `acompanhar_processo_sipac` (IDEMPOTENTE -- doc
    `sipac_processos/{uid}_{numero}` com ID deterministico, `.set(merge=
    True)` converge no mesmo `acompanhar`; achado real e nao-bloqueante
    registrado na nota do inventario sobre `snapshot_hash` colidir com o
    baseline do cron `scheduledSipacSync`, P05); `consolidar_whatsapp`
    (NAO_IDEMPOTENTE -- ID automatico + `.set()` incondicional cria um
    segundo job de consolidacao a cada repeticao); `consultar_contatos_
    prioritarios_secretario` (IDEMPOTENTE -- mesmo desenho de `consultar_
    autorizacao_argos`, expiracao guardada por status converge apos a
    primeira chamada que encontra o item vencido); `registrar_inscricao_
    bolsa_publica` (IDEMPOTENTE -- `vinculos_projeto` checado por
    project_id+cpf antes de criar, segunda chamada devolve `alreadyLinked`
    sem duplicar); `schedule_whatsapp_message` (NAO_IDEMPOTENTE -- o
    `idempotency_key=ctx.mcp_confirmation_id` so protege retry dentro da
    MESMA confirmacao MCP, mesmo caveat ja aceito para `pausar_conversa`,
    que delega para a mesma funcao). Ver `nota` de cada entrada em
    `tools/inventory.py` para a evidencia completa por handler e os testes
    em `test_idempotencia_sub23.py`.

    As ~8 tools restantes (`decidir_elevacao`, `decidir_promocao_
    autonomia`, `confirmar_acao`, `mutar_portal_compras_publico`, `mutar_
    lista_compras`, `revogar_promocao_autonomia`, `excluir_objetivo_
    estrategico`, `gerenciar_item_estrategico`) foram investigadas e
    deliberadamente deixadas sem classificação (`idempotencia=None`, hint
    omitido) por ambiguidade genuína -- ver `nota` de cada uma em
    `tools/inventory.py` para não repetir a investigação. Nenhuma tool
    elegível ficou sem ao menos uma leitura direta do handler.

    Omitir hints nao investigados com confianca nao e regressao: a
    especificacao MCP ja define default conservador para quem nao declara
    `ToolAnnotations` (`destructiveHint`/`openWorldHint` default `true`, o
    lado mais cauteloso em ambos os casos).

    Falha aberta, mesma filosofia das outras funcoes deste modulo: tool sem
    entrada no inventario (nao deveria acontecer --
    `test_tool_inventory.py::TestParidadeComCatalogo` garante paridade 1:1
    com o catalogo -- mas nao e este modulo que deve quebrar `tools/list` se
    isso um dia divergir) devolve dict vazio; o cliente MCP cai nos defaults
    da propria especificacao.
    """
    try:
        entry = get_inventory_entry(tool_name)
    except (AttributeError, TypeError):
        return {}
    if entry is None:
        return {}
    read_only = entry.leitura_escrita == LeituraEscrita.LEITURA
    annotations: dict = {"readOnlyHint": read_only}
    if not read_only:
        # So faz sentido quando readOnlyHint e False (secao 6.1 do plano e a
        # propria especificacao MCP). `NAO_APLICA` (as 3 tools
        # leitura_e_escrita com escrita de efeito colateral passivo ou
        # idempotente, documentada em nota -- nunca o proposito da tool, ver
        # tools/inventory.py) nao e destrutiva no sentido que o hint
        # pretende comunicar; tratada como False, mesmo grupo de
        # `reversivel`.
        annotations["destructiveHint"] = entry.reversibilidade == Reversibilidade.IRREVERSIVEL
        # Mesma condicao "so quando readOnlyHint e False" de destructiveHint
        # acima (secao 6.1 do plano e a especificacao MCP) -- idempotencia
        # so e populada no inventario para tools nao-leitura-pura (ver
        # docstring de Idempotencia), entao esta guarda e redundante com o
        # dado hoje, mas documenta a regra em vez de depender so da
        # invariante de dados.
        if entry.idempotencia == Idempotencia.IDEMPOTENTE:
            annotations["idempotentHint"] = True
        elif entry.idempotencia == Idempotencia.NAO_IDEMPOTENTE:
            annotations["idempotentHint"] = False
    if entry.dominio_rede == DominioRede.FECHADO:
        annotations["openWorldHint"] = False
    elif entry.dominio_rede == DominioRede.ABERTO:
        annotations["openWorldHint"] = True
    return annotations


# P03 passo 3, fatia `outputSchema`/`structuredContent`: ao contrario de
# `annotations` (que deriva de campos ja classificados no inventario para
# as 105 tools -- ver `mcp_annotations` acima), outputSchema exige definir
# um CONTRATO DE DADOS por tool -- nao ha atalho generico (serializar
# qualquer dict de retorno como "o schema" seria publicar um contrato
# inventado, nunca verificado contra a forma real do resultado, e um
# contrato errado e pior que a omissao, mesma razao ja usada para os hints
# nao investigados de `mcp_annotations`). Por isso comeca como lista
# FECHADA, uma tool investigada por vez -- mesmo padrao das outras excecoes
# fechadas deste modulo (`_CAMPOS_COM_TOLERANCIA_A_STRING_JSON`,
# `_CAMPOS_COM_ENUM_TOLERANTE_A_CASE`).
#
# `calculadora` e a primeira: `_calculadora` (tools/hermes_tools.py) e pura
# e deterministica -- sem rede, sem Firestore (confirmado no inventario:
# necessidade_de_rede=False, verificador="determinístico, recomputável
# pelo chamador") -- e sempre devolve um dict achatado com EXATAMENTE duas
# formas possiveis: sucesso, `{"expressao": str, "resultado": str}`, ou
# falha, `{"expressao": str, "erro": str}` -- nunca as duas juntas, nunca
# um terceiro campo (ver o corpo de `_calculadora`). E o candidato de menor
# risco do catalogo para o primeiro contrato real: nao exigiu investigar
# comportamento assincrono, paginacao nem variacao de forma por argumento.
#
# `buscar_contato` e a segunda (P03 sub-entrega 9/N): `_buscar_contato`
# (tools/hermes_tools.py) tambem e pura leitura, sem rede (inventario:
# necessidade_de_rede=False), e devolve so duas formas -- termo vazio,
# `{"erro": str, "candidatos": []}`, ou sucesso, `{"candidatos": [...]}`
# -- nunca um terceiro campo no nivel superior (o corpo da funcao so tem
# esses dois `return`). Cada item de `candidatos` e montado inteiramente a
# mao dentro da propria funcao, com TODAS as 8 chaves sempre presentes
# (`modelo_interacao` incluido -- por isso esta em `required` tambem,
# mesmo podendo valer `None`).
#
# ACHADO DA 1a RODADA DE REVISAO ADVERSARIAL (corrigido aqui): a versao
# original deste comentario afirmava que pessoa_id/nome/email/telefone/
# whatsapp_chat_id sao "sempre string" so por causa do default `""` em
# `data.get(campo, "")` -- mas `dict.get(chave, default)` so devolve o
# default quando a CHAVE ESTA AUSENTE; se `perfil_pessoas` tiver um
# documento com o campo presente e de outro tipo (ex.: `telefone`
# gravado como numero, ou `tags` gravado como string em vez de lista --
# ha pelo menos 10 pontos de escrita diferentes nesta colecao, em
# main.py, telegram_extended.py, contact_merge_utils.py e outros,
# nenhum auditado aqui), o valor cru atravessa sem cast, e
# `structuredContent` (que nunca e validado contra `outputSchema` antes
# de sair) divergiria silenciosamente do contrato publicado para esse
# candidato especifico. Isto NAO trava nada no proprio Hermes (nenhum
# caminho valida o envelope contra o schema antes de responder) e nao e
# motivo para omitir o contrato -- string/array continuam sendo o tipo
# PRETENDIDO e majoritario destes campos -- mas e uma garantia mais fraca
# que a de `calculadora` (onde tudo passa por `str()` explicito no
# proprio handler) ou a de `score`/`pessoa_id` aqui (score e sempre
# `float` por construcao no proprio `_buscar_contato`; pessoa_id e
# sempre `doc.id`, que o SDK do Firestore garante ser string). Registrado
# como pendencia nao-bloqueante nesta sub-entrega, nao corrigido por
# validacao adicional -- adicionar tal validacao mudaria o comportamento
# de producao da tool, fora do escopo de uma fatia de contrato.
#
# `modelo_interacao` continua com contrato deliberadamente solto (`type:
# ["object", "null"]`, sem `properties`/`additionalProperties` aninhado):
# confirmado em `main.py::parse_resposta_modelo_pessoa`, o unico lugar
# que escreve este campo, ele e sempre `None` OU um dict de 4 chaves --
# mas o CONTEUDO desse dict e gerado por LLM, e um contrato errado sobre
# ele seria pior que declarar so o tipo externo confirmado. Pelo mesmo
# espirito, `tags` fica tipada como `array` sem `items`: o valor vem
# direto de `data.get("tags", [])` sem normalizacao de elemento.
_OUTPUT_SCHEMAS: dict[str, dict] = {
    "calculadora": {
        "type": "object",
        "properties": {
            "expressao": {"type": "string"},
            "resultado": {"type": "string"},
            "erro": {"type": "string"},
        },
        "required": ["expressao"],
        "additionalProperties": False,
    },
    "buscar_contato": {
        "type": "object",
        "properties": {
            "erro": {"type": "string"},
            "candidatos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "pessoa_id": {"type": "string"},
                        "nome": {"type": "string"},
                        "email": {"type": "string"},
                        "telefone": {"type": "string"},
                        "whatsapp_chat_id": {"type": "string"},
                        "tags": {"type": "array"},
                        "modelo_interacao": {"type": ["object", "null"]},
                        "score": {"type": "number"},
                    },
                    "required": [
                        "pessoa_id", "nome", "email", "telefone",
                        "whatsapp_chat_id", "tags", "modelo_interacao", "score",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["candidatos"],
        "additionalProperties": False,
    },
    # `consultar_lista_compras` (P03 sub-entrega 10/N) -- terceira tool com
    # outputSchema, mais segura que `buscar_contato` quanto a garantia de
    # tipo NA PROPRIA FUNCAO (campos passados direto do documento do
    # Firestore ali, sem coercao): `tools/lista_compras.py::_item_publico`
    # forca `str()`/`bool()` em CADA campo do item antes de devolver, com
    # uma excecao: `ordem` (opcional, so presente quando o documento tem o
    # campo) e passado adiante sem coercao de tipo. A colecao `shopping_items`
    # tambem e lida/escrita por outros caminhos de codigo fora de
    # `tools/lista_compras.py` (pelo menos `tools/telegram_extended.py`,
    # `security_portals.py` e o frontend web); nenhum dos que foram
    # inspecionados grava `ordem` com tipo diferente de inteiro, mas isso e
    # uma verificacao empirica dos caminhos checados, nao uma auditoria
    # completa da colecao -- risco aceito e nao-bloqueante, mesma categoria
    # e mesmo tratamento da pendencia equivalente registrada para
    # `buscar_contato`/`perfil_pessoas` na sub-entrega 9/N (ver historico
    # completo desta verificacao, incluindo os achados de revisao
    # adversarial que motivaram esta redacao, no diario desta sub-entrega).
    # `filtro` e enum fechado (`_FILTROS` em
    # lista_compras.py resolve qualquer entrada para um destes 5 valores
    # antes de devolver; entrada invalida levanta erro ANTES de montar a
    # resposta, nunca aparece aqui). `total`/`planejados`/`comprados`
    # descrevem sempre a lista inteira, nao a fatia filtrada (ver docstring
    # de `lista_compras.consultar`) -- por isso nao sao redundantes com
    # `encontrados`/`retornados`, que sim refletem o filtro/paginacao
    # aplicados. `truncado` fica de fora de `required`: so aparece quando
    # `True` (o handler nunca escreve `truncado: False`).
    "consultar_lista_compras": {
        "type": "object",
        "properties": {
            "total": {"type": "integer"},
            "planejados": {"type": "integer"},
            "comprados": {"type": "integer"},
            "filtro": {
                "type": "string",
                "enum": ["todos", "planejados", "comprados", "pendentes", "nao_planejados"],
            },
            "encontrados": {"type": "integer"},
            "retornados": {"type": "integer"},
            "itens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "nome": {"type": "string"},
                        "categoria": {"type": "string"},
                        "quantidade": {"type": "string"},
                        "unit": {"type": "string"},
                        "isPlanned": {"type": "boolean"},
                        "isPurchased": {"type": "boolean"},
                        "ordem": {"type": "integer"},
                    },
                    "required": [
                        "item_id", "nome", "categoria", "quantidade",
                        "unit", "isPlanned", "isPurchased",
                    ],
                    "additionalProperties": False,
                },
            },
            "truncado": {"type": "boolean"},
        },
        "required": [
            "total", "planejados", "comprados", "filtro",
            "encontrados", "retornados", "itens",
        ],
        "additionalProperties": False,
    },
    # `consultar_execucoes_agente` (P03 sub-entrega 11/N) -- quarta tool com
    # outputSchema, e a com a garantia de tipo mais forte encontrada ate
    # agora no catalogo: a colecao Firestore que ela le (`agent_runs`) tem
    # UM UNICO ESCRITOR em todo o repositorio -- `agent_runs.registrar`,
    # chamado so pela tool `registrar_execucao_agente` -- e esse escritor
    # SEMPRE passa por `agent_runs.montar_registro` antes de gravar, que
    # valida cada campo (rotina/resumo nao podem ser vazios, status tem que
    # estar no enum de 3 valores, contadores so e aceito se for dict ou
    # None) e devolve so `{"erro": ...}` sem chamar `col.add(...)` quando
    # algum campo obrigatorio falha -- nunca grava um documento fora dessa
    # forma. Confirmado por busca exaustiva no repositorio: nenhum outro
    # arquivo escreve na colecao `agent_runs` por fora de `registrar`
    # (`retro_agente.py`, o unico outro modulo que menciona a colecao, so a
    # LE). Diferente de `buscar_contato`/`perfil_pessoas` e
    # `consultar_lista_compras`/`shopping_items` (sub-entregas 9/N e 10/N),
    # aqui nao ha varios pontos de escrita nao auditados -- ha exatamente
    # um, e ele valida antes de gravar. Duas candidatas do mesmo formato
    # (leitura de sugestoes pendentes) foram descartadas nesta sub-entrega:
    # `consultar_elevacoes_sugeridas`/`deteccao_subproduto.listar_pendentes`
    # e `consultar_promocoes_autonomia_sugeridas`/
    # `promocao_autonomia.listar_promocoes_pendentes` tem as duas um formato
    # ALTERNATIVO de erro (`{"total": 0, "sugestoes"|"promocoes": [],
    # "erro": str(exc)}`) quando a consulta ao Firestore falha -- modelar
    # outputSchema pra elas exigiria decidir se o contrato cobre as duas
    # formas possiveis ou so a normal, investigacao maior que esta fatia;
    # ATUALIZACAO (sub-entrega 29/N): essa objecao nao se aplica mais a
    # `consultar_promocoes_autonomia_sugeridas` -- o padrao `oneOf`
    # (estabelecido na sub-entrega 14/N para `consultar_historico_acoes`,
    # reusado desde entao) resolve exatamente essa decisao; ver a entrada
    # propria dela no fim deste dict. `consultar_elevacoes_sugeridas`
    # continua descartada, nao reinvestigada nesta sub-entrega.
    # `agent_runs.listar_recentes` nao tem esse formato alternativo (uma
    # falha de consulta propaga como excecao nao tratada, fora do escopo de
    # outputSchema, mesmo tratamento generico de qualquer handler sem
    # try/except ao redor da consulta). `contadores` fica com contrato
    # solto (`type: object`, sem `properties` aninhado): e um dict livre
    # passado por quem chama `registrar_execucao_agente`, sem forma fixa
    # entre rotinas diferentes -- mesmo espirito ja usado para
    # `modelo_interacao` (buscar_contato). `erro`/`iniciado_em`/
    # `finalizado_em`/`criado_em` sao `["string", "null"]`: `_to_iso`
    # (`agent_runs.py`) sempre devolve string ou `None`, nunca outro tipo;
    # `finalizado_em` e `criado_em` sao sempre preenchidos pelo proprio
    # `registrar` quando ausentes (`firestore.SERVER_TIMESTAMP`), entao na
    # pratica nunca chegam `None` por um caminho de escrita atual -- o
    # `null` fica so como precaucao contra documento legado sem o campo,
    # nunca observado, mesmo tratamento dado a `finalizado_em`/`iniciado_em`
    # de outras tools deste modulo quando a garantia de presenca nao vem do
    # proprio schema JSON e sim de um comportamento de codigo auditado.
    "consultar_execucoes_agente": {
        "type": "object",
        "properties": {
            "total": {"type": "integer"},
            "runs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "rotina": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["sucesso", "erro", "parcial"],
                        },
                        "resumo": {"type": "string"},
                        "contadores": {"type": "object"},
                        "erro": {"type": ["string", "null"]},
                        "iniciado_em": {"type": ["string", "null"]},
                        "finalizado_em": {"type": ["string", "null"]},
                        "criado_em": {"type": ["string", "null"]},
                    },
                    "required": [
                        "id", "rotina", "status", "resumo", "contadores",
                        "erro", "iniciado_em", "finalizado_em", "criado_em",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["total", "runs"],
        "additionalProperties": False,
    },
    # `consultar_pedidos_agente` (P03 sub-entrega 12/N) -- quinta tool com
    # outputSchema. Investigadas e descartadas nesta sub-entrega, por
    # devolverem STRING (json.dumps) em vez de dict -- mesmo motivo de
    # `consultar_politica` (sub-entrega 10/N): `obter_portal_compras_publico`
    # e `obter_projeto_bolsas_publico` (`tools/telegram_extended.py`, ambas
    # `return json.dumps(...)`), e `simular_politica`/`preparar_politica`
    # (`tools/hermes_tools.py::_simular_politica`/`_preparar_politica`, que
    # sempre fazem `json.dumps(...)` antes de retornar, mesmo no caminho de
    # sucesso). `consultar_pedidos_agente` e backed por
    # `agent_requests.listar_pendentes`, que devolve dict cru -- candidata
    # viavel.
    #
    # Escritor da colecao `agent_requests`: busca exaustiva no repositorio
    # (grep por `collection("agent_requests")`, por `COLLECTION` do proprio
    # modulo e por `agent_requests.enfileirar_ou_atualizar`) encontrou UM
    # UNICO ponto de criacao de documento -- `atencao_whatsapp.py` (fluxo
    # `audio_relevante`), que sempre chama `enfileirar_ou_atualizar` com
    # `tipo=agent_requests.TIPO_CONSOLIDAR_AUDIO` ("consolidar_audio",
    # unica constante de tipo que existe no modulo) e
    # `origem="atencao_whatsapp.audio_relevante"` -- os dois parametros
    # obrigatorios (sem default) da funcao, nunca omitidos por esse
    # chamador. `firestore.rules` nega escrita direta do cliente em
    # `agent_requests` (mesma lista que nega `agent_runs`), entao o unico
    # caminho de escrita e mesmo o descrito acima. NOTA CORRETIVA: a
    # pendencia registrada na sub-entrega 11/N (docs/autonomia/execucao.md)
    # citava "varios escritores (atencao_whatsapp.py, mcp_jobs.py,
    # agent_requests.py)" para esta colecao -- essa lista estava errada:
    # `mcp_jobs.py` so MENCIONA `agent_requests.py` em comentarios de
    # comparacao de padrao (mesmo estilo de transacao Firestore), nunca
    # escreve na colecao. O bloco original nao e reescrito (ja arquivado),
    # mas o erro nao e repetido aqui -- mesma licao ja registrada na
    # sub-entrega 10/N sobre nao enumerar exaustivamente sem checar cada
    # nome citado.
    #
    # `status` e enum fechado de UM valor (`["pendente"]`) por uma garantia
    # mais forte que "escritor unico": e o proprio filtro da QUERY
    # (`listar_pendentes` faz `.where("status", "==", STATUS_PENDENTE)`),
    # entao nenhum documento com outro valor de `status` jamais aparece no
    # resultado, independente de quantos escritores a colecao tiver
    # (inclusive um segundo escritor futuro nao quebraria essa garantia
    # especifica, ainda que quebrasse outras).
    #
    # `payload` fica com contrato solto (`type: object`, sem `properties`
    # aninhado) DELIBERADAMENTE, mesmo sabendo que o unico `tipo` hoje
    # (`consolidar_audio`) tem forma fixa e totalmente coagida
    # (`agent_requests.montar_payload_consolidar_audio`: `chat_id`/
    # `chat_name` via `str(x or "").strip()`, `mensagem_ids` via
    # `list(x or [])`, `acao_id`/`item_atencao_id` via
    # `str(x).strip() if x else None`) -- porque `payload` e conceitualmente
    # POR TIPO (o proprio docstring do modulo fala em "tarefas autonomas",
    # so uma implementada ate agora), e modelar a forma de um unico tipo
    # tornaria o contrato invalido no dia em que um segundo `tipo` aparecer
    # com payload diferente, sem que ninguem precise mudar este schema --
    # mesmo espirito de `contadores` (consultar_execucoes_agente) e
    # `modelo_interacao` (buscar_contato). Pelo mesmo motivo `tipo` (campo
    # do item, nao o parametro da tool) fica como `string` solta, nao enum:
    # ao contrario de `status`, a garantia de UM valor aqui vem so de "so
    # existe um escritor hoje", nao de um filtro de query -- um enum de um
    # valor ficaria errado assim que o segundo tipo (que o proprio design
    # antecipa) aparecesse. `origem` tambem fica `string` solta pelo mesmo
    # motivo (parametro livre da funcao, so hardcoded em UM valor no unico
    # call site atual).
    #
    # `id` e sempre `doc.id` (garantido string pelo SDK do Firestore).
    # `item_atencao_id`/`acao_id` (campos do NIVEL SUPERIOR do item, nao os
    # de dentro de `payload`) sao `[string, null]`: vem direto de
    # `d.get(...)` sem coercao -- no unico call site atual, `item_atencao_id`
    # sempre recebe uma string (`doc_id`, usado antes como chave do proprio
    # documento de atencao) e `acao_id` pode ser `None` legitimamente
    # (`item.get("acao_id")` de um item de atencao sem acao vinculada) --
    # mas nenhum dos dois passa por `str()`/coercao explicita dentro de
    # `listar_pendentes`, mesma categoria de risco nao-bloqueante ja
    # registrada para campos sem coercao no ponto de leitura (`ordem` em
    # consultar_lista_compras, campos de `perfil_pessoas` em buscar_contato).
    # `criado_em`/`atualizado_em` passam por uma funcao `_to_iso` PROPRIA de
    # `agent_requests.py` -- funcionalmente identica a de `agent_runs.py`
    # (mesmo corpo: `None` vira `None`, objeto com `.isoformat()` vira
    # string, qualquer outra coisa vira `str()`), mas uma DUPLICATA, nao
    # importada de la -- achado da 1a rodada de revisao adversarial desta
    # sub-entrega, corrigindo uma versao anterior deste comentario que
    # dizia "a mesma `_to_iso`" (as duas funcoes podem divergir no futuro
    # sem que a outra mude). De qualquer forma, string ou `None`, nunca
    # outro tipo.
    #
    # Historico completo da revisao adversarial desta sub-entrega (quantas
    # rodadas, o que cada uma achou): docs/autonomia/execucao.md, sub-entrega
    # 12/N -- mesma licao ja registrada na sub-entrega 10/N sobre uma
    # narrativa rodada-a-rodada nao pertencer a um comentario de codigo
    # permanente (o numero de rodadas muda enquanto a revisao ainda esta em
    # andamento; fixar esse numero aqui no meio do processo e o mesmo erro,
    # so que sobre o proprio processo de revisao em vez de sobre a
    # colecao Firestore).
    "consultar_pedidos_agente": {
        "type": "object",
        "properties": {
            "total": {"type": "integer"},
            "pedidos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "tipo": {"type": "string"},
                        "status": {"type": "string", "enum": ["pendente"]},
                        "payload": {"type": "object"},
                        "origem": {"type": "string"},
                        "item_atencao_id": {"type": ["string", "null"]},
                        "acao_id": {"type": ["string", "null"]},
                        "criado_em": {"type": ["string", "null"]},
                        "atualizado_em": {"type": ["string", "null"]},
                    },
                    "required": [
                        "id", "tipo", "status", "payload", "origem",
                        "item_atencao_id", "acao_id", "criado_em", "atualizado_em",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["total", "pedidos"],
        "additionalProperties": False,
    },
    # `consultar_historico_acoes` (P03 sub-entrega 14/N) -- sexta tool com
    # outputSchema, e a PRIMEIRA a usar `oneOf`: ao contrario das cinco
    # anteriores, o handler (`tools/hermes_tools.py::_consultar_historico_acoes`)
    # tem duas formas de nivel superior genuinamente diferentes, nao uma
    # forma unica com campos as vezes ausentes (`truncado` em
    # `consultar_lista_compras`, `erro` em `buscar_contato`) -- SUCESSO e
    # ERRO aqui sao dois conjuntos de campos obrigatorios DISJUNTOS:
    #   - sucesso: `{"total_retornado": int, "resultados": [...], "filtros": {...}}`
    #   - erro: `{"erro": str, "resultados": []}` (`resultados` SEMPRE lista
    #     vazia -- hardcoded pelo proprio handler, que descarta o que
    #     `buscar_tarefas` devolveu em `resultados` no seu dict de erro)
    # Esta era a pendencia deixada pelas sub-entregas 12/N e 13/N ("avaliar
    # `oneOf` -- nunca usado neste catalogo -- antes de escolher qual
    # candidata fazer primeiro"). Decidido usar `oneOf` com as duas formas
    # COMPLETAS (cada uma com seu proprio `required`/
    # `additionalProperties: False`) em vez de uma forma unica com todos os
    # campos fora de `required`: a alternativa aceitaria hibridos invalidos
    # (ex.: `erro` e `filtros` juntos) que o handler real nunca produz.
    #
    # Handler investigado direto no codigo: `_consultar_historico_acoes`
    # chama `busca_grafo.buscar_tarefas` (ate duas vezes -- reintentando com
    # `match_mode="any"` quando a tentativa com `match_mode="all"` nao acha
    # nada, controle de fluxo interno que nunca aparece na forma da
    # resposta final). Se `buscar_tarefas` devolver `erro` (excecao
    # capturada dentro dela mesma, ou falha na consulta base ao Firestore),
    # o handler devolve `{"erro": ..., "resultados": []}` e para; senao,
    # monta a forma de sucesso. Nao ha terceiro formato -- `buscar_tarefas`
    # tambem pode devolver um campo `aviso` (string, quando precisou
    # relaxar filtros ou ampliar a busca), mas esse campo NUNCA chega ao
    # retorno do handler: ele so le `res.get("erro")` e
    # `res.get("resultados", [])`, o resto de `res` e descartado.
    #
    # `resultados` (forma de sucesso) e uma lista de itens montados por
    # `busca_grafo._formatar_resultado`, sempre o MESMO dict literal de 15
    # chaves (nenhuma condicional): `id` (sempre `doc.id`, garantido string
    # pelo SDK do Firestore); `criado_em` (coercao de tipo garantida por
    # `str()` explicito -- `str(data.get("data_criacao", ""))[:10]`, sempre
    # string mesmo que o campo no Firestore seja Timestamp/data/ausente);
    # `plano_acao` e `acompanhamento_recente` (as duas construidas
    # inteiramente a mao dentro de `_formatar_resultado`, so anexando
    # strings formatadas -- `f"{marcador} {texto[:200]}"` e `f"[{data}]
    # {nota[:300]}"` -- garantia de tipo tao forte quanto `criado_em`, ao
    # contrario dos demais campos textuais, por isso `array` de `string`,
    # nao `array` solto); e sete campos (`titulo`, `status`, `tipo_acao`,
    # `responsavel`, `area`, `data_limite`, `processo_sei`) que sao
    # `data.get(campo, default)` CRU, sem coercao nenhuma no ponto de
    # leitura (`default` e `"sem titulo"` so para `titulo`; `""` para os
    # outros seis) -- se o documento (`GRAFO_COLLECTION`) tiver algum desses
    # campos gravado com tipo diferente de string, o valor cru vaza para a
    # resposta --
    # mesma categoria de risco ja aceita e nao-bloqueante de `ordem`
    # (`consultar_lista_compras`) e dos campos de `perfil_pessoas`
    # (`buscar_contato`), sem auditoria de todo escritor de
    # `GRAFO_COLLECTION` feita nesta sub-entrega. `tags` fica `array` solto
    # (mesmo espirito de `buscar_contato`); `descricao`/`notas`/
    # `sintese_demanda` sao `(data.get(campo) or "")[:500|400]` -- coagido
    # para string se o valor original for falsy ou ja string. ACHADO da 3a
    # rodada de revisao adversarial desta sub-entrega, corrigindo uma
    # versao anterior deste comentario que dizia que um valor truthy
    # nao-string aqui sempre levantaria `TypeError`: isso so vale para
    # ESCALARES nao-fatiaveis (int/float/bool) -- uma SEQUENCIA truthy
    # (list/tuple/bytes/range) sobrevive ao `[:500]`/`[:400]` sem erro e
    # vaza para a resposta do jeito que veio do Firestore (confirmado:
    # `(["a", "b"] or "")[:500]` devolve `["a", "b"]`, nao levanta nada).
    # Ou seja, estes tres campos tem a MESMA categoria de risco nao-
    # bloqueante dos sete campos crus acima para entradas tipo sequencia
    # (vazamento silencioso), e uma categoria mais segura (falha ruidosa)
    # so para entradas escalares nao-fatiaveis -- nao a garantia
    # uniformemente mais segura que a redacao anterior alegava.
    #
    # `filtros` (forma de sucesso) e eco dos ARGUMENTOS DE ENTRADA, nao
    # dados persistidos: `query` e sempre string (`str(args.get("query") or
    # "")`, mesma coercao de `expressao` em `calculadora`); os quatro
    # campos restantes (`area_tematica`, `status`, `data_limite_inicio`,
    # `data_limite_fim`) sao `None` quando o chamador omite (o schema
    # publicado em `tools/schemas/consultar_historico_acoes.json` os
    # declara como `string` opcional, nao `required`) ou `str(valor)`
    # quando informado -- por isso `["string", "null"]`. ACHADO da revisao
    # adversarial desta sub-entrega: ate a correcao, esses quatro campos
    # eram `args.get(campo)` CRU (sem `str()`) -- como o schema publicado
    # em `tools/list` so declara o tipo esperado sem checagem escalar em
    # runtime (ver `registry.tipos_invalidos`), um chamador MCP mandando
    # `area_tematica: 5` ou `status: ["a", "b"]` fazia esse valor vazar sem
    # coercao para `filtros`, violando o proprio contrato aqui publicado --
    # reproduzido de verdade (nao so hipotetico) antes da correcao. Corrigido
    # com `tools/hermes_tools.py::_filtro_str_ou_none` (ver docstring la
    # para o raciocinio completo, incluindo por que a coercao fica so no
    # ECO de saida, nao dentro de `busca_grafo.buscar_tarefas`).
    #
    # Historico completo da revisao adversarial desta sub-entrega:
    # docs/autonomia/execucao.md, sub-entrega 14/N.
    "consultar_historico_acoes": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "total_retornado": {"type": "integer"},
                    "resultados": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "titulo": {"type": "string"},
                                "status": {"type": "string"},
                                "tipo_acao": {"type": "string"},
                                "responsavel": {"type": "string"},
                                "criado_em": {"type": "string"},
                                "area": {"type": "string"},
                                "data_limite": {"type": "string"},
                                "processo_sei": {"type": "string"},
                                "tags": {"type": "array"},
                                "descricao": {"type": "string"},
                                "notas": {"type": "string"},
                                "sintese_demanda": {"type": "string"},
                                "plano_acao": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "acompanhamento_recente": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "id", "titulo", "status", "tipo_acao", "responsavel",
                                "criado_em", "area", "data_limite", "processo_sei",
                                "tags", "descricao", "notas", "sintese_demanda",
                                "plano_acao", "acompanhamento_recente",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "filtros": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "area_tematica": {"type": ["string", "null"]},
                            "status": {"type": ["string", "null"]},
                            "data_limite_inicio": {"type": ["string", "null"]},
                            "data_limite_fim": {"type": ["string", "null"]},
                        },
                        "required": [
                            "query", "area_tematica", "status",
                            "data_limite_inicio", "data_limite_fim",
                        ],
                        "additionalProperties": False,
                    },
                },
                "required": ["total_retornado", "resultados", "filtros"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "erro": {"type": "string"},
                    "resultados": {"type": "array", "maxItems": 0},
                },
                "required": ["erro", "resultados"],
                "additionalProperties": False,
            },
        ],
    },
    # `obter_acao` (P03 sub-entrega 15/N) -- setima tool com outputSchema,
    # e a com MAIS campos de nivel superior ate agora (24). Handler
    # (`tools/hermes_tools.py::obter_acao`) tem 3 `return` no total, nao 2:
    # `{"erro": "Informe task_id."}` (sem `task_id`, nem proprio nem de
    # `ctx.task_id`); `{"erro": "...", "status": "not_found"}` (doc
    # inexistente); e a forma de sucesso. Ao contrario de
    # `consultar_historico_acoes` (sub-entrega 14/N), as duas formas de erro
    # NAO sao disjuntas o bastante para justificar um terceiro ramo de
    # `oneOf`: a unica diferenca entre elas e a PRESENCA do campo `status`
    # (sempre o mesmo unico valor, `"not_found"`, quando aparece) -- mesmo
    # padrao ja usado para campo opcional que so aparece as vezes (`truncado`
    # em `consultar_lista_compras`), nao um formato alternativo genuino.
    # Modelado como UM ramo de erro com `status` fora de `required`, e
    # `oneOf` com so 2 ramos no total (sucesso / erro), nao 3.
    #
    # `id`/`titulo`/`descricao`/`notas`/`status`/`area_tematica`/`projeto`/
    # `data_limite`/`data_inicio`/`prazo_final`/`horario_inicio`/
    # `horario_fim`/`tags`/`estrategia_objetivo_id` sao os MESMOS campos
    # (mesma colecao `tarefas`, confirmado em `busca_grafo.GRAFO_COLLECTION
    # == "tarefas"`) que `consultar_historico_acoes` ja expos com risco
    # aceito e nao-bloqueante para tipo errado -- mas aqui SEM o `or
    # default` que aquela tool aplica (`data.get(campo, "")`): `obter_acao`
    # faz `d.get(campo)` cru, sem segundo argumento, entao o campo AUSENTE
    # vira `None` de verdade (nao `""`), e por isso tem `null` no tipo onde
    # aquela tool nao precisou. `descricao`/`notas` sao a excecao: usam `or
    # ""`, que cobre o caso ausente/falsy com string vazia (mesmo risco
    # residual de valor truthy nao-string vazar cru, categoria ja aceita
    # para `descricao`/`notas`/`sintese_demanda` em `consultar_historico_
    # acoes`) -- por isso ficam sem `null`. `id` e sempre `snap.id`
    # (garantido string pelo SDK do Firestore).
    #
    # `tags` e `d.get("tags") or []`: mesmo risco aceito de
    # `buscar_contato`/`consultar_historico_acoes` (valor truthy nao-lista
    # vaza cru) -- fica `array` solto, sem `null` (o `or []` cobre o caso
    # ausente).
    #
    # `execution_lane` (`subtarefas.derivar_lane`) e `degradation_count`
    # (`subtarefas.degradacao_da_acao`) sao os dois campos com a garantia de
    # tipo MAIS FORTE desta tool: as duas funcoes SEMPRE devolvem,
    # respectivamente, `str(...)` e `int(...)` explicitos em todo ramo
    # interno (lidas as duas funcoes por completo em `subtarefas.py`) --
    # nunca passam o valor gravado adiante sem coercao. `execution_lane`
    # fica como `string` solta, nao enum: o ramo "sem etapa aberta" pode
    # devolver o `lane_gravada` ORIGINAL sem normalizar quando ele nao for
    # vazio (`return str(lane_gravada or "").strip() or "avanco"`), e nada
    # impede hoje um valor gravado direto no Firestore por fora desta
    # funcao -- um enum fechado quebraria nesse caso, mesmo motivo ja usado
    # para `tipo`/`origem` em `consultar_pedidos_agente` (sub-entrega 12/N).
    #
    # `contexto_agente` (`d.get("contexto_agente")`) tinha UM UNICO escritor
    # em todo o repositorio: `main.py::processar_contexto_agente`, chamado
    # so pelo gatilho Firestore `on_document_written` em `tarefas/{taskId}`
    # -- busca exaustiva por `"contexto_agente":` como CHAVE DE ESCRITA
    # confirma isso. REMOVIDO em 17/09/2026 (custo -- ~90% do Gemini do
    # Hermes vinha desse gatilho e do irmao de extracao de pessoas; ver
    # diario da acao b066fbd2-8552-4321-b): o campo agora e so-leitura,
    # so aparece em tarefas ja processadas antes da remocao, nunca mais
    # cresce. O formato abaixo documenta o que ja existe gravado. Esse
    # escritor gravava sempre `None` (quando o parse do
    # LLM falha ou fica vazio -- nesse caso grava so `last_processed_
    # contexto_hash`, sem tocar `contexto_agente`) ou o dict devolvido por
    # `parse_resposta_contexto`, que TEM forma fixa e coagida (`resumo`:
    # `str(...).strip()`, nunca vazio quando o dict e devolvido;
    # `pessoas_chave`/`ultimas_decisoes`/`travas`: sempre listas, cada item
    # `str(...).strip()`; `onde_esta_o_codigo`: `None` ou string;
    # `atualizado_em`: sempre string ISO). Fica com contrato solto (`type:
    # ["object", "null"]`, sem `properties` aninhado) DELIBERADAMENTE, mesmo
    # sabendo a forma exata -- mesmo espirito de `modelo_interacao`
    # (`buscar_contato`): e conteudo gerado por LLM sobre texto livre da
    # acao, e nao ha nenhum OUTRO leitor deste campo no catalogo MCP hoje
    # que precise validar sub-campos individualmente. Aprofundar o contrato
    # pode ser feito numa fatia futura, sem quebrar este.
    #
    # `plano_acao` (`etapas`, construido no proprio handler) -- a parte mais
    # trabalhosa desta sub-entrega: alem de `converter_plano`/`mesclar_plano`
    # (que sempre terminam em `subtarefas.normalizar`, garantindo `id`
    # string nao-vazia, `estado` num dos 4 valores fechados, `aguardando_de`
    # string ate 200 chars quando presente, `degradation_count` int quando
    # presente), ha um OITAVO ponto de escrita que NAO passa por
    # `normalizar`: `tools/pausar_conversa.py` monta a etapa de pausa a mao
    # (`{"id": str(uuid.uuid4())[:8], "text": ..., "estado":
    # "aguardando_terceiro", "aguardando_de": "André", "data_prevista":
    # pause_until, ...}`). Os TIPOS gravados por esse caminho batem com o
    # que `normalizar` produziria (id string, estado enum valido,
    # aguardando_de string literal), mas por caminho diferente -- por isso
    # este comentario, e nao so "escritor unico via normalizar", documenta
    # os dois caminhos. `texto`/`estado` no proprio `obter_acao` passam por
    # `subtarefas.texto_de`/`estado_de` (sempre string / sempre um dos 4
    # valores de `ESTADOS`, mesmo em documento legado sem `estado` gravado
    # -- `estado_de` deduz de `completed`), garantia forte independente de
    # quem escreveu. `data_prevista` passa por `subtarefas.data_prevista_de`
    # (sempre `str(...)` internamente) + `or None` no handler -- string
    # nao-vazia ou `None`, nunca outro tipo, MESMO que o valor gravado no
    # Firestore por `pausar_conversa.py` (`pause_until`) tenha outro tipo
    # antes de passar por `str()`. JA `id` da etapa e `i.get("id")` CRU, sem
    # `estado_de`/`texto_de` no meio -- documento legado de ANTES de
    # `subtarefas.py` (2026-08-26, ver docstring do modulo: "subtarefa era
    # texto com marcador de concluida") pode ter etapa em formato dict sem
    # `id` nenhum, nunca tocada por `mesclar_plano` desde entao; por isso
    # `id` da etapa tem `null` no tipo, ao contrario do `id` do nivel
    # superior (`snap.id`, sempre garantido pelo SDK).
    #
    # `anexos` (`pool_dados` filtrado por `tipo == "arquivo"`) -- 4
    # escritores encontrados (`main.py` linhas ~8805, ~11303/11326,
    # `tools/anexar_arquivo.py`, mais `tools/hermes_tools.py::
    # criar_acao_no_sistema` que so REPASSA itens ja montados por um dos
    # tres primeiros): todos gravam `nome` (string) e `valor` (string, URL,
    # sempre truthy nos 4 -- o fallback `x.get("link")` no handler e
    # morto hoje, nenhum escritor usa a chave `"link"`); `drive_file_id`
    # SO aparece em 2 dos 4 (ausente no caminho SIPAC, `main.py` ~8805) --
    # por isso `["string", "null"]`. `nome`/`link` ficam tambem com `null`
    # no tipo por precaucao contra item de `pool_dados` anterior a estes
    # 4 escritores (mesma categoria de risco do `id` da etapa acima, nao
    # demonstrado, so nao descartado).
    #
    # `diario` (`acompanhamento[-limite_diario:]`) -- `data` e SEMPRE
    # string: `str(e.get("data"))` no proprio handler, sem `or` no meio,
    # entao ATE `None` vira a string literal `"None"` (comportamento real,
    # nao um bug desta sub-entrega). `nota` e `e.get("nota")` CRU. A via
    # principal de escrita hoje (tool MCP `registrar_no_diario`) GARANTE
    # string de fato: `nota = args.get("nota")` seguido de `(nota or
    # "").strip()` para validar vazio -- um valor truthy NAO-string
    # (ex.: `nota: 5`) levanta `AttributeError` NESSA MESMA LINHA (`int`
    # nao tem `.strip()`), capturado pelo `try/except` externo da funcao e
    # devolvido como erro da tool, nunca chega a gravar. As demais escritas
    # de `acompanhamento` encontradas no repositorio (main.py,
    # telegram_extended.py, hermes_tools.py, pausar_conversa.py,
    # anexar_arquivo.py, email_action_linker.py, investimentos_sync.py,
    # outbox_aprovacao.py) usam f-string (`f"..."`, coage para string
    # sempre, independente do tipo interpolado) ou uma variavel de string
    # ja validada -- nenhuma grava um valor cru nao-string encontrada nesta
    # busca, mas a lista de escritores e grande o bastante (8+) para nao
    # reivindicar auditoria exaustiva de cada um; risco residual aceito e
    # nao-bloqueante, mesma categoria das demais leituras cruas desta tool.
    #
    # `etapas_feitas`/`etapas_totais` (`subtarefas.contar`) e `diario_total`
    # (`len(acomp)`) sao sempre `int` (contagem local, sem ler campo
    # gravado). `observacao` e sempre string (f-string montada no proprio
    # handler).
    #
    # Investigacao completa (as 8 fontes de `plano_acao`, os 4 escritores de
    # `pool_dados`/anexo, o escritor unico de `contexto_agente`, a analise
    # de `registrar_no_diario` sobre `nota`) e as rodadas de revisao
    # adversarial: docs/autonomia/execucao.md, sub-entrega 15/N.
    "obter_acao": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "titulo": {"type": ["string", "null"]},
                    "descricao": {"type": "string"},
                    "notas": {"type": "string"},
                    "status": {"type": ["string", "null"]},
                    "area_tematica": {"type": ["string", "null"]},
                    "projeto": {"type": ["string", "null"]},
                    "data_limite": {"type": ["string", "null"]},
                    "data_inicio": {"type": ["string", "null"]},
                    "prazo_final": {"type": ["string", "null"]},
                    "horario_inicio": {"type": ["string", "null"]},
                    "horario_fim": {"type": ["string", "null"]},
                    "tags": {"type": "array"},
                    "execution_lane": {"type": "string"},
                    "degradation_count": {"type": "integer"},
                    "estrategia_objetivo_id": {"type": ["string", "null"]},
                    "contexto_agente": {"type": ["object", "null"]},
                    "plano_acao": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": ["string", "null"]},
                                "texto": {"type": "string"},
                                "estado": {
                                    "type": "string",
                                    "enum": [
                                        "pendente", "em_andamento",
                                        "aguardando_terceiro", "feito",
                                    ],
                                },
                                "data_prevista": {"type": ["string", "null"]},
                                "aguardando_de": {"type": "string"},
                                "degradation_count": {"type": "integer"},
                            },
                            "required": ["id", "texto", "estado", "data_prevista"],
                            "additionalProperties": False,
                        },
                    },
                    "etapas_feitas": {"type": "integer"},
                    "etapas_totais": {"type": "integer"},
                    "anexos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nome": {"type": ["string", "null"]},
                                "link": {"type": ["string", "null"]},
                                "drive_file_id": {"type": ["string", "null"]},
                            },
                            "required": ["nome", "link", "drive_file_id"],
                            "additionalProperties": False,
                        },
                    },
                    "diario": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "data": {"type": "string"},
                                "nota": {"type": ["string", "null"]},
                            },
                            "required": ["data", "nota"],
                            "additionalProperties": False,
                        },
                    },
                    "diario_total": {"type": "integer"},
                    "observacao": {"type": "string"},
                },
                "required": [
                    "id", "titulo", "descricao", "notas", "status",
                    "area_tematica", "projeto", "data_limite", "data_inicio",
                    "prazo_final", "horario_inicio", "horario_fim", "tags",
                    "execution_lane", "degradation_count",
                    "estrategia_objetivo_id", "contexto_agente", "plano_acao",
                    "etapas_feitas", "etapas_totais", "anexos", "diario",
                    "diario_total", "observacao",
                ],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "erro": {"type": "string"},
                    "status": {"type": "string", "enum": ["not_found"]},
                },
                "required": ["erro"],
                "additionalProperties": False,
            },
        ],
    },
    # `listar_rascunhos_pendentes` (P03 sub-entrega 24/N) -- oitava tool com
    # outputSchema. Handler (`tools/hermes_tools.py::listar_rascunhos_pendentes`)
    # so repassa `limite` para `outbox_aprovacao.listar_rascunhos`, que tem
    # UMA UNICA forma de retorno (sem `try/except` proprio, sem ramo de
    # erro alternativo) -- diferente de `consultar_historico_acoes`/
    # `obter_acao` (sub-entregas 14/N e 15/N), nao precisa de `oneOf`.
    #
    # `status` e enum de EXATAMENTE 2 valores pela MESMA garantia ja usada
    # em `consultar_pedidos_agente` (sub-entrega 12/N): nao "escritor
    # unico" -- a colecao `whatsapp_outbox` tem MUITOS escritores, em
    # varios modulos Python (`outbox_aprovacao.py` tem pelo menos seis
    # funcoes que escrevem `status`: `criar_rascunho`, `aprovar_rascunho`,
    # `descartar_rascunho`, `aplicar_edicao_rascunho`,
    # `expirar_rascunhos_pendentes`, `_degradar_rascunho_promovido_sem_
    # mandato`; mais `tools/schedule_whatsapp_message.py`,
    # `ai_notification_planner.py`, `telegram_callbacks_confirmacoes.py`)
    # e tambem fora de Python (`services/whatsapp-capture/index.js`, o
    # worker Node do WhatsApp, e `hermes-voice-bridge/tools.py`, o cliente
    # de voz) -- e sim o filtro da propria QUERY
    # (`.where("status", "in", [STATUS_AGUARDANDO, STATUS_AGUARDANDO_JANELA])`
    # em `outbox_aprovacao.listar_rascunhos`): nenhum documento com outro
    # valor de `status` pode aparecer no resultado, INDEPENDENTE de quantos
    # escritores a colecao tiver ou do que cada um escreva -- essa e a
    # garantia que importa para o contrato publicado, e nao depende de
    # enumerar todo escritor.
    #
    # NOTA DE PROCESSO (as tres rodadas de revisao adversarial desta
    # sub-entrega): uma versao anterior deste comentario tentava listar
    # TODOS os escritores da colecao e prova-los individualmente
    # inofensivos ao enum -- cada rodada de revisao achou pelo menos um
    # escritor real que a "lista exaustiva" anterior tinha omitido
    # (`aplicar_edicao_rascunho`/`_degradar_rascunho_promovido_sem_mandato`
    # na 1a rodada; `ai_notification_planner.py`/`hermes-voice-bridge/
    # tools.py` na 2a; `aprovar_rascunho`/`descartar_rascunho`/
    # `expirar_rascunhos_pendentes`/`services/whatsapp-capture/index.js`
    # na 3a) -- nenhum deles jamais mudou o veredito do enum (nenhum
    # escreve `aguardando_aprovacao`/`aguardando_janela` fora do gate que
    # ja exige o documento estar num desses dois estados), mas a proposta
    # de enumeracao exaustiva e um alvo que nao para de crescer numa
    # colecao com escritores em multiplos runtimes. Por isso a redacao
    # final abandona a enumeracao completa e fica só com a garantia
    # estrutural (o filtro da query), que e a unica coisa de que o
    # contrato publicado aqui depende.
    #
    # Os outros 13 campos do item vem de UM UNICO LITERAL de dict dentro de
    # `listar_rascunhos` (`outbox_aprovacao.py`, sem chave condicional --
    # todos os 13 sempre presentes, ao contrario de `truncado`
    # (`consultar_lista_compras`) ou `status` no ramo de erro (`obter_acao`)):
    #   - `id` (`doc.id`, garantido string pelo SDK do Firestore).
    #   - `destinatario_nome`/`to_number`/`motivo`/`origem` sao
    #     `["string", "null"]` -- CORRECAO da revisao Codex nesta PR (achado
    #     real, nao um nit): a versao original desta nota provava que
    #     `criar_rascunho` (o UNICO caminho de criacao que gera os dois
    #     status do filtro) sempre PREENCHE estes quatro campos com string
    #     nao-vazia (`motivo`/`contact_number` validados nao-vazios antes do
    #     payload; `destinatario_nome`/`to_number` caem para `contact_number`
    #     quando `nome`/`chat_id` sao falsy; `origem or "claude"`) -- mas
    #     isso so cobre documentos criados PELA VERSAO ATUAL de
    #     `criar_rascunho`. `listar_rascunhos` LE estes quatro campos com
    #     `d.get(campo)` CRU, sem segundo argumento (ao contrario de `tipo`,
    #     que tem `d.get("tipo", "outro")`) -- um documento que nao passe
    #     por essa escrita exata (formato legado de antes deste payload,
    #     edicao manual no Firestore, ou um escritor futuro que nao inclua
    #     um desses campos) leria como `None`, nao como string vazia.
    #     Nenhum caso assim foi OBSERVADO nesta investigacao (o unico
    #     caminho de criacao ativo sempre preenche os quatro), mas a
    #     garantia de tipo depende do ESCRITOR e nao do LEITOR (mesma
    #     categoria de risco ja aceita para `acao_id`/`item_atencao_id`
    #     abaixo, exceto que ali o `None` e por DESENHO, nao por ausencia de
    #     coercao) -- por isso nullable, corrigindo o schema original que
    #     os declarava como string obrigatoria sem `null`. `tipo` continua
    #     `string` sem `null`: tem default (`"outro"`) no PROPRIO ponto de
    #     leitura, garantia mais forte que a dos quatro campos acima.
    #     `origem` continua sem enum (nao um terceiro valor fixo como
    #     `status`), so ganhou `null` pelo mesmo motivo dos outros tres.
    #     O parametro opcional `destinatario_resolvido`
    #     (usado so por `secretario_whatsapp.py::enviar_resposta_via_
    #     outbox`, um unico call site) repassa `chat_id`/`nome` do
    #     CHAMADOR sem coercao de tipo -- mas isso NAO e um risco residual
    #     para ESTA tool (CORRECAO da 1a rodada de revisao adversarial
    #     desta sub-entrega, que apontou a nota original como
    #     mal-atribuida): esse unico call site sempre passa
    #     `envio_imediato=True`, que forca `status_inicial = STATUS_PENDING`
    #     incondicionalmente em `criar_rascunho` -- um documento criado por
    #     esse caminho NUNCA pode aparecer no resultado de
    #     `listar_rascunhos` (o filtro da query exclui `STATUS_PENDING`).
    #     Continua sendo um risco residual real para `criar_rascunho`
    #     (a funcao) e para o campo publicado por `criar_rascunho_
    #     whatsapp` caso essa tool algum dia ganhe outputSchema propria,
    #     so nao se aplica ao contrato desta tool especifica.
    #   - `acao_id`/`item_atencao_id` sao `["string", "null"]` --
    #     DELIBERADAMENTE nullable: `criar_rascunho` grava os dois SEMPRE
    #     (nunca ausentes do documento), mas com valor `None` quando o
    #     chamador nao informa (`str(acao_id).strip() if acao_id else
    #     None`) -- nao e "campo ausente", e "campo presente com valor
    #     null" por desenho (tarefa/item de atencao vinculado e opcional).
    #   - `foi_editado` e SEMPRE `bool`, garantia mais forte que a do
    #     documento gravado: `listar_rascunhos` aplica `bool(d.get(
    #     "foi_editado", False))` na PROPRIA leitura (coercao local,
    #     mesmo espirito de `trecho` abaixo), independente do que estiver
    #     gravado no Firestore.
    #   - `trecho` e SEMPRE `string`, mesma razao: `str(d.get("content")
    #     or "")[:120]` na propria leitura, nunca o campo `content` cru.
    #   - `envio_liberado_em`/`criado_em` sao `["string", "null"]`: passam
    #     por `outbox_aprovacao._to_iso`, que devolve `None` so para
    #     entrada `None`, `.isoformat()` para datetime/Timestamp, e
    #     `str(val)` para QUALQUER outra coisa -- nunca um terceiro tipo.
    #     `envio_liberado_em` so e gravado quando `is_promovido` (ausente
    #     do documento no caminho regular; `d.get(...)` sem default vira
    #     `None`, que `_to_iso` mantem `None`).
    #   - `telegram_message_id` e `["integer", "null"]` -- ACHADO desta
    #     sub-entrega: nao e string como o padrao `_to_iso` dos dois campos
    #     de data faria supor. `criar_rascunho` so grava este campo
    #     (`doc_ref.update({"telegram_message_id": telegram_msg_id})`)
    #     QUANDO `telegram_msg_id` e truthy, e esse valor vem de
    #     `telegram_utils._send_telegram_message_with_keyboard`, que
    #     devolve `resp.json().get("result", {}).get("message_id")` --
    #     `message_id` e um INTEIRO na API do Telegram, nunca string.
    #     Confirmado tambem por `test_outbox_aprovacao.py` (fixture
    #     `"telegram_message_id": 999`, literal inteiro). Campo AUSENTE
    #     (nunca gravado) quando o envio ao Telegram falha ou nao ha
    #     token/chat configurado -- por isso nullable, nunca outro tipo.
    #
    # Investigacao completa e as rodadas de revisao adversarial desta
    # sub-entrega: docs/autonomia/execucao.md, sub-entrega 24/N.
    "listar_rascunhos_pendentes": {
        "type": "object",
        "properties": {
            "total": {"type": "integer"},
            "rascunhos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["aguardando_aprovacao", "aguardando_janela"],
                        },
                        "destinatario_nome": {"type": ["string", "null"]},
                        "to_number": {"type": ["string", "null"]},
                        "motivo": {"type": ["string", "null"]},
                        "trecho": {"type": "string"},
                        "acao_id": {"type": ["string", "null"]},
                        "item_atencao_id": {"type": ["string", "null"]},
                        "origem": {"type": ["string", "null"]},
                        "tipo": {"type": "string"},
                        "foi_editado": {"type": "boolean"},
                        "envio_liberado_em": {"type": ["string", "null"]},
                        "criado_em": {"type": ["string", "null"]},
                        "telegram_message_id": {"type": ["integer", "null"]},
                    },
                    "required": [
                        "id", "status", "destinatario_nome", "to_number",
                        "motivo", "trecho", "acao_id", "item_atencao_id",
                        "origem", "tipo", "foi_editado", "envio_liberado_em",
                        "criado_em", "telegram_message_id",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["total", "rascunhos"],
        "additionalProperties": False,
    },
    # `consultar_job` (P03 sub-entrega 25/N) -- nona tool com outputSchema.
    # Handler real: `tools/hermes_tools.py::_consultar_job` e um passthrough
    # puro para `mcp_jobs.ler_job(ctx.user_uid, job_id)` -- lido por
    # completo. Escritor: `mcp_jobs.py` e o UNICO arquivo do repositorio que
    # grava na colecao `mcp_jobs` (confirmado por busca -- so
    # `mcp_jobs.criar_job`/`on_mcp_job_created`/`_reivindicar_job` tocam essa
    # colecao; nenhum outro modulo, ao contrario de `whatsapp_outbox`,
    # sub-entrega 24/N). Enumeracao completa dos 4 pontos de escrita de
    # `status` confirma que so 3 valores sao gravados: `"processing"`
    # (`criar_job`, unico valor inicial) e, so pelo trigger
    # `on_mcp_job_created`, `"done"` ou `"error"` -- nenhum quarto valor em
    # nenhum dos 4 `ref.update(...)` do arquivo.
    #
    # `ler_job` tem 5 `return` distintos, a MAIOR contagem de ramos deste
    # catalogo ate agora (mais que os 3 de `obter_acao`, sub-entrega 15/N):
    #   1. sem `job_id`: `{"erro": "job_id obrigatorio."}` -- SEM `status`,
    #      SEM `job_id`/`tool` (a checagem `if not job_id` acontece antes de
    #      qualquer leitura ao Firestore).
    #   2. job inexistente OU `dados.get("uid") != uid`: `{"erro": ...,
    #      "status": "not_found"}` -- a MESMA resposta para os dois casos,
    #      deliberado (comentario do proprio handler: "confirmar que o id
    #      existe ja vazaria informacao para quem esta tentando adivinhar").
    #   3. `status == "done"`: `{"job_id", "tool", "status": "done",
    #      "resultado"}`.
    #   4. `status == "error"`: `{"job_id", "tool", "status": "error",
    #      "erro", "erro_tipo"?, "bloqueio_politica"?}`.
    #   5. qualquer outro `status` (so `"processing"` e alcancavel hoje, ver
    #      enumeracao acima): `{"job_id", "tool", "status", "mensagem"}`.
    # Os ramos 1 e 2 sao a MESMA forma de erro que `obter_acao` ja usa
    # (campo `status` opcional, so muda a PRESENCA dele) -- por isso um unico
    # branch de erro aqui tambem, `status` fora de `required`, e NAO um
    # terceiro ramo de `oneOf` so para essa diferenca. Os ramos 3/4/5
    # compartilham `job_id`/`tool`/`status` mas tem o RESTO dos campos
    # obrigatorios DISJUNTO (`resultado` xor `erro`+opcionais xor
    # `mensagem`) -- por isso 3 branches sao genuinamente necessarios, alem
    # do branch de erro-sem-job -- 4 branches de `oneOf` no total, o maior
    # numero deste catalogo ate agora.
    #
    # `job_id`/`tool` (ramos 3/4/5): `job_id` e sempre o PARAMETRO de
    # entrada (nao `dados.get("job_id")`), garantido nao-vazio pelo `if not
    # job_id` do ramo 1 -- sempre `string`. `tool` e `dados.get("tool")`,
    # sempre presente e nao-vazio: o UNICO escritor (`criar_job`) grava
    # `"tool": tool` incondicionalmente, com `tool` vindo de `name` (que
    # `mcp_server._handle_tools_call` so despacha para `criar_job` quando
    # `name in _TOOLS_LONGAS`, nunca vazio) -- por isso `string` sem `null`.
    #
    # `resultado` (ramo 3, `status == "done"`): documentado como `string`
    # HOJE, mas e um contrato de SNAPSHOT, nao uma garantia estrutural como
    # o enum de `listar_rascunhos_pendentes` -- registrado explicitamente
    # para nao repetir o erro de redacao corrigido na sub-entrega 24/N.
    # `_TOOLS_LONGAS` (`mcp_server.py`) tem hoje EXATAMENTE 3 tools:
    # `gerar_relatorio`, `ler_documento_na_integra`, `buscar_e_analisar_
    # email` -- as 3 unicas que podem produzir um job com `status == "done"`.
    # Lidos os 3 handlers por completo (`tools/telegram_extended.py`, ramos
    # `gerar_relatorio`/`ler_documento_na_integra`; `tools/buscar_e_
    # analisar_email.py`): TODO `return` das 3 e uma `string` (Markdown/
    # texto simples num caso de sucesso; `json.dumps(...)`/`f"⚠️ ..."` nos
    # outros) -- nenhum dict, nenhuma lista. `mcp_jobs._preparar_resultado`
    # confirma que uma `string` passa DIRETO para o campo `resultado`
    # gravado (so um valor NAO-string passaria por `json.dumps` e ficaria
    # ESTRUTURADO no Firestore -- caminho hoje inalcancavel pelas 3 tools
    # atuais, mas o mecanismo em si e generico: `execute()` e o MESMO
    # dispatcher usado por qualquer tool do catalogo, entao uma QUARTA tool
    # futura em `_TOOLS_LONGAS` que devolva dict/lista quebraria esta
    # garantia sem tocar nenhuma linha deste comentario). Por isso `string`
    # sem `null` aqui, mas com este caveat: revisar este campo sempre que
    # `_TOOLS_LONGAS` ganhar uma nova entrada.
    #
    # ACHADO desta sub-entrega, NAO corrigido (fora do escopo de uma fatia
    # so-schema): o campo `truncado` (bool, gravado pelo mesmo `ref.update`
    # que grava `resultado` em `on_mcp_job_created`, sinaliza quando
    # `_MAX_RESULTADO_CHARS` cortou o texto) e lido de volta por `ler_job`
    # -- so `resultado`/`job_id`/`tool`/`status` sao copiados para `saida`.
    # Um consumidor de `consultar_job` nao tem como saber, pela resposta,
    # que um `resultado` longo foi cortado no meio, apesar do dado existir
    # no Firestore. Nao endereçado aqui: mudar o que `ler_job` devolve e uma
    # mudanca de COMPORTAMENTO do handler, nao so de documentacao do
    # contrato existente -- registrado em pendencias para uma fatia futura
    # (`ler_job`/P03 passo 4, ou P05).
    #
    # `erro`/`erro_tipo`/`bloqueio_politica` (ramo 4, `status == "error"`):
    # `erro` e sempre `dados.get("erro")`, e as 4 escritas de `status:
    # "error"` em `on_mcp_job_created` SEMPRE incluem `erro` (string,
    # `str(exc)` ou mensagem construida) -- por isso obrigatorio, sem
    # `null`. `erro_tipo` e um dos 4 valores fechados de `mcp_jobs.py`
    # (`ERRO_TIPO_POLITICA`/`ERRO_TIPO_RESULTADO`/`ERRO_TIPO_EXCECAO`/
    # `ERRO_TIPO_CONFIGURACAO`) -- as 4 escritas de erro SEMPRE gravam um
    # destes hoje, mas `ler_job` mantem a checagem `if dados.get(
    # "erro_tipo") is not None` (comentario do proprio handler: campo
    # "ausente so em jobs gravados antes desta sub-entrega [anterior,
    # P01]") -- por isso OPCIONAL aqui, nao obrigatorio, seguindo o que o
    # LEITOR realmente garante (nao o que todo escritor atual grava) --
    # mesmo criterio ja usado para campos opcionais desta familia
    # (`truncado` em `consultar_lista_compras`, `status` no ramo de erro de
    # `obter_acao`). `bloqueio_politica` e opcional pelo mesmo motivo, so
    # presente quando `erro_tipo == "politica"`: `{"decision": string,
    # "reason_code": string}`, forma fixa gravada a mao em
    # `on_mcp_job_created` (`decisao.decision.value` sempre string do enum
    # `Decisao`). `reason_code` SEM `null` -- CORRECAO da 1a rodada de
    # revisao adversarial desta sub-entrega, que apontou a redacao anterior
    # ("pode ser None") como nao verificada: `autonomy/contracts.py::
    # PolicyDecision.reason_code` e tipado `str` (nao `str | None`), e os 4
    # pontos de construcao de `PolicyDecision` em `autonomy/policy.py`
    # (incluindo `_decisao_padrao_por_classe`, tipada `-> tuple[Decisao,
    # str, bool]`) sempre passam um literal de string, nunca `None`.
    #
    # `mensagem` (ramo 5, unico `status` alcancavel hoje: `"processing"`) e
    # uma string literal fixa no proprio `ler_job`, nunca dado do Firestore
    # -- garantia mais forte que qualquer outro campo desta tool.
    #
    # Investigacao completa desta sub-entrega: docs/autonomia/execucao.md,
    # sub-entrega 25/N.
    "consultar_job": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "erro": {"type": "string"},
                    "status": {"const": "not_found"},
                },
                "required": ["erro"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "tool": {"type": "string"},
                    "status": {"const": "done"},
                    "resultado": {"type": "string"},
                },
                "required": ["job_id", "tool", "status", "resultado"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "tool": {"type": "string"},
                    "status": {"const": "error"},
                    "erro": {"type": "string"},
                    "erro_tipo": {
                        "type": "string",
                        "enum": ["politica", "resultado_tool", "excecao", "erro_configuracao"],
                    },
                    "bloqueio_politica": {
                        "type": "object",
                        "properties": {
                            "decision": {"type": "string"},
                            "reason_code": {"type": "string"},
                        },
                        "required": ["decision", "reason_code"],
                        "additionalProperties": False,
                    },
                },
                "required": ["job_id", "tool", "status", "erro"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "tool": {"type": "string"},
                    "status": {"const": "processing"},
                    "mensagem": {"type": "string"},
                },
                "required": ["job_id", "tool", "status", "mensagem"],
                "additionalProperties": False,
            },
        ],
    },
    # `buscar_arquivos_acervo` (P03 sub-entrega 26/N) -- decima tool com
    # outputSchema. Handler (`tools/hermes_tools.py::_buscar_arquivos_acervo`)
    # e um wrapper fino sobre `tools/busca_acervo.py::buscar_acervo`, lido
    # por completo: SEMPRE devolve exatamente 2 chaves (`resultados`: list,
    # `erro`: str ou None) -- nunca uma terceira forma, nunca as duas
    # simultaneamente truthy de outro jeito. O wrapper colapsa isso em 2
    # branches de oneOf pela mesma checagem `if res.get("erro")`:
    #   1. erro: `{"erro": <str>, "resultados": []}` -- `resultados` sempre
    #      lista vazia (o proprio wrapper substitui por `[]` literal, nao
    #      repassa o que `buscar_acervo` devolveu no ramo de excecao, que
    #      tambem e sempre `[]`).
    #   2. sucesso: `{"total_retornado": <int, len()>, "resultados": [...]}`.
    #
    # Item de `resultados` (forma de sucesso) tem 8 chaves fixas, montadas a
    # mao em `busca_acervo.buscar_acervo` (nenhuma vem direto de
    # `doc.to_dict()` sem passar por `.get(campo, default)`):
    #   - `id`: sempre `doc.id` -- string garantida pelo SDK do Firestore.
    #   - `titulo`/`trecho`/`fonte`/`url_drive`: `data.get(campo, "<default
    #     string>")`. Os 3 escritores conhecidos da colecao `indice_
    #     artefatos` (unico backing da query, `ACERVO_COLLECTION`) foram
    #     lidos por completo: `knowledge_graph._write_to_indice_artefatos` e
    #     o writer de anexo SIPAC (`main.py`, ~linha 8835) NUNCA gravam
    #     `titulo`/`trecho`/`fonte`/`url_drive` (usam `nome`/`resumo_
    #     semantico`/`url` em vez disso) -- por isso esses 4 campos caem no
    #     default string do proprio `.get()` para documentos vindos desses
    #     2 escritores. O terceiro escritor (anexo do Copiloto, `main.py`,
    #     ~linha 11291) grava os 4 com esses nomes exatos, mas os valores
    #     de 3 deles (`titulo_doc`/`resumo_doc`/`natureza_doc`, -> `titulo`/
    #     `trecho`/`fonte`) vem de `meta.get(...)`, onde `meta =
    #     json.loads(extraction_text)` e a RESPOSTA LIVRE de um modelo
    #     Gemini (sem `response_schema` nem validacao de tipo). ACHADO da
    #     revisao do Codex nesta PR, CORRIGIDO: `titulo_doc = meta.get(
    #     'titulo', real_file_name)` so aplica o fallback quando a CHAVE
    #     esta AUSENTE do JSON -- se o modelo devolver `{"titulo": null,
    #     ...}` (chave presente, valor `null`), `dict.get` devolve `None`
    #     DIRETO, ignorando o fallback (confirmado: `{"titulo": None}.get(
    #     "titulo", "x")` e `None`, nao `"x"`). O mesmo vale para `resumo`/
    #     `natureza` (`trecho`/`fonte`), que nem tem fallback nenhum
    #     (default `''` so no `.get()` de `busca_acervo`, nunca acionado
    #     quando a chave existe com `null`). Por isso os 3 campos sao
    #     `["string", "null"]`, nao `"string"` puro -- refletindo o tipo
    #     REALMENTE alcancavel por este caminho, nao so o pretendido pelo
    #     prompt. Um valor de outro tipo (numero, lista, dict) continua
    #     residual e nao-bloqueante, mesma categoria ja aceita para campos
    #     de origem LLM em `_buscar_contato` (sub-entrega 9/N,
    #     `modelo_interacao`): normalizar tudo exigiria mudar o
    #     comportamento de producao do escritor, fora do escopo desta
    #     fatia. `url_drive` e DIFERENTE -- construido deterministicamente
    #     via f-string (`main.py`, linha do `drive_link`), nunca vem do
    #     JSON do Gemini -- por isso continua `string` pura, sem `null`.
    #     `url_drive` so e gravado por este 3o escritor -- os outros 2 usam
    #     a chave `url` (nunca lida por `buscar_acervo`), entao esse campo
    #     cai no default `""` para qualquer documento fora deste 3o
    #     escritor.
    #   - `task_id`: `data.get("task_id")`, SEM default -- vira `None`
    #     quando a chave nao existe. Os 3 escritores: `knowledge_graph`
    #     grava a chave so quando o parametro e truthy (`if task_id:
    #     entry["task_id"] = task_id`); o writer SIPAC sempre grava
    #     `"task_id": target_task_id` (string, o id da acao vinculada); o
    #     writer do Copiloto grava `'task_id': task_id or None` (string ou
    #     `None` explicito). Em todos os casos, `string` ou `None` -- nunca
    #     um terceiro tipo -- por isso `["string", "null"]`.
    #   - `origem`: `data.get("origem", "acervo")` -- ACHADO desta
    #     sub-entrega: NAO e sempre string. Os 2 primeiros escritores gravam
    #     `origem` como STRING (`knowledge_graph`: parametro `origem: str`;
    #     writer SIPAC: literal `"tarefa"`); mas o 3o escritor (Copiloto,
    #     `main.py` ~linhas 11286-11302) grava um DICT (`{"modulo":
    #     "tarefa"|"copiloto", "id_origem": ..., "session_id": ...}`
    #     conforme `task_id` esteja ativo) -- `buscar_acervo` repassa esse
    #     valor sem normalizar. Documentado como `["string", "object"]`, sem
    #     `properties` aninhadas (o formato do dict varia por ramo do 3o
    #     escritor) -- nao corrigido aqui: normalizar o tipo mudaria o dado
    #     devolvido hoje, fora do escopo de uma fatia so-schema.
    #   - `distancia`: `getattr(doc, "distance", None)` -- GARANTIA
    #     ESTRUTURAL, nao so observacao de hoje: `busca_acervo.py` chama
    #     `find_nearest(...)` SEM passar `distance_result_field` (o unico
    #     parametro que faria o servidor anexar uma distancia ao resultado
    #     -- confirmado lendo a assinatura de `find_nearest` em
    #     `google.cloud.firestore_v1.base_collection`, versao 2.28.0 fixada
    #     em `requirements.txt`); e `DocumentSnapshot` (`base_document.py`/
    #     `document.py` da mesma biblioteca) NUNCA define um atributo
    #     `distance` em nenhum caminho de codigo, com ou sem esse
    #     parametro. Ou seja, `getattr(doc, "distance", None)` sempre cai no
    #     default `None` -- confirmado inspecionando a biblioteca instalada,
    #     nao so lendo a chamada. Documentado como `{"type": "null"}` (nao
    #     `["number", "null"]`): campo sempre presente, sempre `null`, nao
    #     um valor as vezes ausente as vezes numerico.
    #
    # `resultados` (ramo de erro) e sempre `[]` -- mesma convencao de
    # `maxItems: 0` ja usada em `consultar_historico_acoes` (sub-entrega
    # 14/N).
    #
    # Colecao `indice_artefatos` tem 3 escritores em 2 arquivos diferentes
    # (`knowledge_graph.py`, `main.py` x2) -- MAIS de um, mas TODOS os 3
    # foram lidos e enumerados por completo aqui (nao a mesma situacao de
    # `whatsapp_outbox`, sub-entrega 24/N, onde a lista de escritores
    # continuava crescendo a cada rodada de revisao) -- os 3 pontos de
    # escrita foram encontrados por busca direta (`grep -rn
    # "indice_artefatos"`) e nenhuma rodada de revisao adversarial desta
    # sub-entrega encontrou um 4o.
    #
    # `buscar_arquivos_acervo` nao tinha NENHUM teste dedicado antes desta
    # sub-entrega (nem do handler, nem de `busca_acervo.buscar_acervo`) --
    # lacuna fechada aqui com testes novos em `test_hermes_tools.py`
    # (`TestExecucao`, mockando `tools.busca_acervo.buscar_acervo`
    # diretamente), alem dos testes de contrato/`structuredContent` deste
    # arquivo.
    #
    # Investigacao completa desta sub-entrega: docs/autonomia/execucao.md,
    # sub-entrega 26/N.
    "buscar_arquivos_acervo": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "total_retornado": {"type": "integer"},
                    "resultados": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "titulo": {"type": ["string", "null"]},
                                "trecho": {"type": ["string", "null"]},
                                "fonte": {"type": ["string", "null"]},
                                "url_drive": {"type": "string"},
                                "task_id": {"type": ["string", "null"]},
                                "origem": {"type": ["string", "object"]},
                                "distancia": {"type": "null"},
                            },
                            "required": [
                                "id", "titulo", "trecho", "fonte", "url_drive",
                                "task_id", "origem", "distancia",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["total_retornado", "resultados"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "erro": {"type": "string"},
                    "resultados": {"type": "array", "maxItems": 0},
                },
                "required": ["erro", "resultados"],
                "additionalProperties": False,
            },
        ],
    },
    # `consultar_status_modo_secretario` (P03 sub-entrega 27/N) -- decima
    # primeira tool com outputSchema, backed por
    # `secretario_whatsapp.consultar_status_modo_secretario` (passthrough
    # puro em `tools/hermes_tools.py::_consultar_status_modo_secretario`,
    # sem args). PRIMEIRA tool do catalogo com UMA FORMA SO onde TODOS os
    # campos sao sempre obrigatorios (ao contrario de `calculadora`/
    # `buscar_contato`/`consultar_lista_compras`, que tambem tem forma
    # unica mas com campos as vezes AUSENTES, ou de `consultar_historico_
    # acoes` em diante, que usam `oneOf`): a funcao nunca levanta excecao
    # (o corpo inteiro le config via `secretario_whatsapp.
    # obter_config_secretario`, que tem seu proprio `try/except Exception`
    # e sempre devolve um dict default em caso de erro; o loop que monta
    # `contatos_detalhes` tambem tem `try/except Exception` em volta da
    # UNICA chamada que pode falhar, o `.get()` do documento do chat) e
    # sempre constroi as 8 chaves do dict de retorno sem nenhum `if` que
    # pule uma delas -- lido por completo (`secretario_whatsapp.py`,
    # `consultar_status_modo_secretario` e `obter_config_secretario`).
    #
    # `chats_allowlist` (nivel superior) e SEMPRE lista de string:
    # `obter_config_secretario` forca `[str(x).strip() for x in (...) if
    # str(x).strip()]` nos dois `return` (sucesso e except). `contatos_
    # detalhes` e montado a mao, item a item, dentro da propria funcao --
    # `chat_id` e sempre um elemento de `chats_allowlist` (ja garantido
    # string), `nome` comeca como esse mesmo `chat_id` e so e sobrescrito
    # por `str((doc.to_dict() or {}).get("chat_name") or cid)`, sempre
    # string em ambos os casos.
    #
    # `orientacoes_em_vigor`/`orientacoes_padrao`/`orientacoes_sessao` sao
    # sempre `string | null`: as tres vem, direta ou indiretamente, de
    # `secretario_whatsapp.normalizar_orientacoes`, que so devolve `str`
    # ou `None` (nunca outro tipo) -- lida por completo.
    #
    # ACHADO da revisao do Codex nesta PR, CORRIGIDO: `desativa_em` tinha
    # DOIS escritores com garantias de tipo diferentes. O caminho normal
    # (`secretario_whatsapp.ativar_modo_secretario`/
    # `desativar_modo_secretario`) so grava `limite.isoformat()` (string)
    # ou `None`. Mas `main.py::updateAutomationSettings` (callable HTTP
    # `whatsapp_secretario.desativa_em`, usado pelo frontend web) repassa
    # `sec_updates["desativa_em"] = sec_cfg["desativa_em"]` DIRETO do corpo
    # da requisicao, sem coercao de tipo nem validacao de schema -- um
    # cliente que mande um numero, lista ou dict nesse campo gravaria
    # exatamente isso em `system/settings`. A 1a rodada de revisao
    # adversarial (Agent tool, sem contexto) confirmou o achado e, alem
    # disso, que o frontend hoje NUNCA envia esse campo nesse endpoint
    # (`src/components/modals/Modals.tsx`), tornando o caminho fraco
    # puramente teorico na pratica -- mas o Codex apontou corretamente que
    # "nenhuma evidencia hoje" nao e uma GARANTIA ESTRUTURAL, e um cliente
    # MCP que valide `structuredContent` contra o `outputSchema` quebraria
    # se algum dia um valor nao-string fosse gravado. CORRIGIDO
    # normalizando na LEITURA (`secretario_whatsapp.obter_config_
    # secretario`, nao no endpoint HTTP): `desativa_em` agora e sempre
    # coagido para `str(...)` quando presente e nao-string, antes de
    # qualquer uso (inclusive antes de `_esta_expirado`, que ja fazia
    # `str()` internamente e tolerava qualquer tipo via `try/except`, sem
    # mudanca de comportamento ali) -- escolhido em vez de validar/rejeitar
    # em `updateAutomationSettings` porque normalizar na leitura fecha a
    # lacuna para QUALQUER escritor presente ou futuro daquele campo, nao
    # so o conhecido hoje, e nao muda o comportamento de um endpoint HTTP
    # fora do escopo MCP. `desativa_em` agora tem a MESMA garantia
    # estrutural dos demais campos desta tool.
    #
    # Investigacao completa desta sub-entrega: docs/autonomia/execucao.md,
    # sub-entrega 27/N.
    "consultar_status_modo_secretario": {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean"},
            "desativa_em": {"type": ["string", "null"]},
            "chats_allowlist": {"type": "array", "items": {"type": "string"}},
            "contatos_detalhes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "string"},
                        "nome": {"type": "string"},
                    },
                    "required": ["chat_id", "nome"],
                    "additionalProperties": False,
                },
            },
            "orientacoes_em_vigor": {"type": ["string", "null"]},
            "orientacoes_padrao": {"type": ["string", "null"]},
            "orientacoes_sessao": {"type": ["string", "null"]},
            "mensagem": {"type": "string"},
        },
        "required": [
            "enabled", "desativa_em", "chats_allowlist", "contatos_detalhes",
            "orientacoes_em_vigor", "orientacoes_padrao", "orientacoes_sessao",
            "mensagem",
        ],
        "additionalProperties": False,
    },
    # `consultar_contatos_prioritarios_secretario` (P03 sub-entrega 28/N) --
    # decima segunda tool com outputSchema, backed por
    # `secretario_whatsapp.consultar_contatos_prioritarios` (passthrough
    # puro em `tools/hermes_tools.py::
    # _consultar_contatos_prioritarios_secretario`, que so resolve o
    # default/None de `apenas_ativos` antes de repassar). `oneOf` de 2
    # branches, mesma forma de `buscar_arquivos_acervo`/`consultar_
    # historico_acoes`: a funcao tem UM `try/except Exception` cobrindo o
    # loop inteiro de leitura -- qualquer excecao (ex.: Firestore fora do
    # ar) cai direto no branch de erro, sem meio-termo.
    #   1. erro: `{"erro": <str>, "contatos_prioritarios": []}` -- SEM
    #      `total`/`apenas_ativos`, ao contrario do branch de sucesso (o
    #      `return` de erro so tem essas 2 chaves, lido por completo).
    #   2. sucesso: `{"total": <int, len()>, "apenas_ativos": <bool,
    #      repassado>, "contatos_prioritarios": [...]}`.
    #
    # `secretario_contatos_prioritarios` (colecao lida) tem UM UNICO ponto
    # de CRIACAO de documento em todo o repositorio --
    # `secretario_whatsapp.preparar_contato_prioritario` (confirmado por
    # `grep -rn "COLLECTION_PRIORITARIOS"`: so 2 arquivos usam essa
    # constante, `secretario_whatsapp.py`, e nenhum outro modulo referencia
    # a string literal da colecao) -- mesma categoria de garantia de
    # `consultar_execucoes_agente` (sub-entrega 11/N) e `consultar_pedidos_
    # agente` (sub-entrega 12/N). Diferente de `busca_acervo`/`lista_
    # compras`, a propria `consultar_contatos_prioritarios` NAO reconstroi
    # o item campo a campo com `.get(chave, default)` -- devolve `doc.
    # to_dict()` quase cru (so acrescenta `id` e pode reescrever `status`
    # para o expirado na propria leitura, ver `tools/inventory.py`), entao
    # a garantia de forma do item vem inteira do UNICO escritor, nao da
    # funcao de leitura:
    #   - `id`: sempre `doc.id` -- string garantida pelo SDK do Firestore.
    #   - `chat_id`/`chat_name`: `preparar_contato_prioritario` sempre grava
    #     as 2 chaves como string -- `chat_id` vem de `resolver_
    #     identificador_contato`, que SEMPRE devolve `(str, str)` (o
    #     segundo elemento nunca fica vazio: cai no proprio identificador
    #     de entrada como ultimo fallback em todo caminho lido) -- lido por
    #     completo.
    #   - `assunto`/`o_que_precisa_saber`: sempre string NAO-VAZIA --
    #     `preparar_contato_prioritario` valida e devolve erro ANTES de
    #     gravar se qualquer um vier vazio (`if not assunto_limpo: return
    #     {"erro": ...}`), entao nenhum documento gravado tem esses campos
    #     ausentes ou vazios.
    #   - `status`: enum FECHADO de 4 valores (`ativo`/`concluido`/
    #     `expirado`/`cancelado`) -- os 4 unicos `STATUS_PRIORITARIO_*`
    #     definidos no modulo; toda escrita de `status` usa uma dessas
    #     constantes, nunca uma string livre -- os 6 pontos de escrita da
    #     colecao (1 criacao + 5 `.update()`: expiracao automatica DENTRO
    #     da propria `consultar_contatos_prioritarios`, uma SEGUNDA
    #     expiracao automatica independente em `obter_briefing_ativo`
    #     [achado da revisao adversarial desta sub-entrega -- nao e o
    #     mesmo ponto, e uma funcao separada que tambem le esta colecao],
    #     cancelamento, e os 2 pontos de conclusao) foram encontrados por
    #     `grep -rn "COLLECTION_PRIORITARIOS"` e lidos por completo.
    #   - `valido_ate`: sempre string ISO, nunca `None` -- gravado por
    #     `_calcular_validade_iso`, que SEMPRE devolve `.isoformat()` (se
    #     `validade_horas` for omitido, usa o fim do dia corrente em vez de
    #     devolver `None`) -- lida por completo.
    #   - `resumo_estruturado`/`informacao_obtida`: `None`/`None` na
    #     criacao, viram `str`/`bool` nos 2 pontos de conclusao (limite de
    #     trocas atingido e investigacao concluida pela LLM) -- a CHAVE
    #     sempre existe (gravada explicitamente como `None` na criacao),
    #     so o VALOR muda -- por isso `["string", "null"]`/`["boolean",
    #     "null"]` em vez de campo as vezes ausente.
    #   - `criado_em`/`atualizado_em`: `firestore.SERVER_TIMESTAMP` na
    #     criacao e em toda atualizacao -- sempre presentes. O executor
    #     MCP serializa o dict via `json.dumps(..., default=str)`
    #     (`mcp_server._handle_tools_call`) antes do round-trip que vira
    #     `structuredContent`; `default=str` sobre um `DatetimeWithNanoseconds`
    #     (subclasse de `datetime.datetime`) cai no `datetime.__str__`
    #     herdado, sempre uma string -- por isso `string`, nao um tipo
    #     custom nem `object`.
    #   - `concluido_em`: gravado nos mesmos 2 pontos de `resumo_
    #     estruturado`/`informacao_obtida` acima -- fica FORA de `required`
    #     no item, mesma convencao de `truncado` (`listar_rascunhos_
    #     pendentes`, sub-entrega 24/N) e `ordem` (`consultar_lista_
    #     compras`, sub-entrega 10/N). Quando presente, mesma garantia de
    #     tipo string de `criado_em`/`atualizado_em` (mesmo mecanismo de
    #     serializacao). ACHADO da revisao adversarial desta sub-entrega,
    #     nao-bloqueante: a chave NAO implica de volta que o documento
    #     esteja concluido -- `preparar_contato_prioritario` grava com
    #     `doc_ref.set(doc_data, merge=True)` (linha ~741) e `doc_data` NAO
    #     inclui `concluido_em`, entao um `merge=True` sobre um documento
    #     ja concluido (reregistrar o MESMO `chat_id` como prioritario de
    #     novo, sem guarda contra isso) reseta `status` para `ativo` e
    #     `resumo_estruturado`/`informacao_obtida` para `None` (ambos
    #     explicitos em `doc_data`), mas preserva o `concluido_em` do ciclo
    #     anterior -- semantica padrao de merge do Firestore, so mescla as
    #     chaves passadas. Documentado aqui como risco aceito: o campo
    #     continua sempre `string` quando presente (nao quebra o schema),
    #     so a leitura "presente implica concluido" e falsa nesse cenario
    #     -- nenhum teste cobre esse reregistro hoje.
    #
    # `contatos_prioritarios` (ramo de erro) e sempre `[]` -- mesma
    # convencao de `maxItems: 0` ja usada em `consultar_historico_acoes`/
    # `buscar_arquivos_acervo`.
    #
    # Handler (`_consultar_contatos_prioritarios_secretario`) nao tinha
    # NENHUM teste dedicado antes desta sub-entrega (a logica de default/
    # None de `apenas_ativos` e exclusiva do wrapper, nao coberta pelos
    # testes existentes de `secretario_whatsapp.consultar_contatos_
    # prioritarios` em `test_secretario_whatsapp.py`) -- lacuna fechada em
    # `test_hermes_tools.py`.
    #
    # Investigacao completa desta sub-entrega: docs/autonomia/execucao.md,
    # sub-entrega 28/N.
    "consultar_contatos_prioritarios_secretario": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "total": {"type": "integer"},
                    "apenas_ativos": {"type": "boolean"},
                    "contatos_prioritarios": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "chat_id": {"type": "string"},
                                "chat_name": {"type": "string"},
                                "assunto": {"type": "string"},
                                "o_que_precisa_saber": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["ativo", "concluido", "expirado", "cancelado"],
                                },
                                "valido_ate": {"type": "string"},
                                "resumo_estruturado": {"type": ["string", "null"]},
                                "informacao_obtida": {"type": ["boolean", "null"]},
                                "criado_em": {"type": "string"},
                                "atualizado_em": {"type": "string"},
                                "concluido_em": {"type": "string"},
                            },
                            "required": [
                                "id", "chat_id", "chat_name", "assunto",
                                "o_que_precisa_saber", "status", "valido_ate",
                                "resumo_estruturado", "informacao_obtida",
                                "criado_em", "atualizado_em",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["total", "apenas_ativos", "contatos_prioritarios"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "erro": {"type": "string"},
                    "contatos_prioritarios": {"type": "array", "maxItems": 0},
                },
                "required": ["erro", "contatos_prioritarios"],
                "additionalProperties": False,
            },
        ],
    },
    # `consultar_promocoes_autonomia_sugeridas` (P03 sub-entrega 29/N) --
    # decima terceira tool com contrato publicado. Retomada da candidata
    # descartada na sub-entrega 11/N (ver o comentario de
    # `consultar_execucoes_agente` acima) -- a objecao de entao ("modelar
    # outputSchema exigiria decidir se o contrato cobre as duas formas
    # possiveis ou so a normal, investigacao maior que aquela fatia") ja
    # nao se sustenta: o padrao `oneOf` com as duas formas COMPLETAS e
    # DISJUNTAS (sucesso/erro), usado desde `consultar_historico_acoes`
    # (sub-entrega 14/N) e mais recentemente em
    # `consultar_contatos_prioritarios_secretario` (sub-entrega 28/N,
    # entrada acima), e exatamente a decisao que faltava tomar.
    #
    # Handler (`tools/hermes_tools.py::_consultar_promocoes_autonomia_
    # sugeridas`) e passthrough puro: so resolve o default de `limite`
    # (`int(args.get("limite") or 20)`) antes de repassar a
    # `promocao_autonomia.listar_promocoes_pendentes`, que tem exatamente
    # DUAS formas de retorno, nunca uma terceira:
    #   - sucesso: `{"total": int, "promocoes": [...]}` (a consulta ao
    #     Firestore correu bem, mesmo que sem nenhum resultado)
    #   - erro: `{"total": 0, "promocoes": [], "erro": str(exc)}` -- so
    #     quando o `.stream()` da query levanta excecao (`try/except`
    #     dentro da propria funcao); `total`/`promocoes` ficam FIXOS em
    #     `0`/`[]` nesse ramo (hardcoded no `return` do `except`, nao
    #     ecoados de nenhum calculo), mesma convencao de
    #     `consultar_historico_acoes`/`buscar_arquivos_acervo`
    #     (`resultados`/`contatos_prioritarios` sempre `[]` no ramo de
    #     erro).
    #
    # Escritor da colecao `promocoes_autonomia_sugeridas`
    # (`promocao_autonomia.COL_PROMOCOES`): busca exaustiva no repositorio
    # (grep por `collection(COL_PROMOCOES)`) encontra 3 pontos de escrita,
    # mas UM UNICO ponto de CRIACAO de documento com `status="pendente"`
    # -- `registrar_sugestao_promocao` (linha ~130), chamada por sua vez de
    # UM UNICO call site em todo o repositorio (`retro_agente.py`, dentro
    # da retro semanal). Os outros 2 pontos (`decidir_promocao_autonomia`,
    # `revogar_promocao_autonomia`) so fazem `transaction.update`/`.update`
    # sobre um documento MOVENDO `status` PARA FORA de `pendente`
    # (`aceita`/`adiada`/`nunca`) ou gravando `revogado_em`/
    # `motivo_revogacao` -- nenhum dos dois grava `status="pendente"` nem
    # toca `tipo`/`amostra`/`aprovados_sem_edicao`/`taxa_sem_edicao`/
    # `sugerida_em`. Combinado com o filtro da propria QUERY de leitura
    # (`listar_promocoes_pendentes` faz `.where("status", "==",
    # STATUS_PENDENTE)`), `status` e enum fechado de UM valor
    # (`["pendente"]`) por garantia DUPLA -- da query e do unico escritor
    # de criacao -- mesma categoria ja usada para `consultar_pedidos_
    # agente` (sub-entrega 12/N).
    #
    # `amostra`/`aprovados_sem_edicao`/`taxa_sem_edicao` sao sempre os
    # valores devolvidos por `outbox_aprovacao.metricas_por_tipo` (unica
    # origem do argumento `metricas` de `registrar_sugestao_promocao`,
    # lido por completo): `amostra` e sempre `len(amostra_docs)` (int),
    # `aprovados_sem_edicao` e sempre `sum(1 for ... in amostra_docs)`
    # (int), `taxa_sem_edicao` e sempre uma DIVISAO (`sem_edicao / amostra`,
    # float) ou o literal `0.0` -- nunca outro tipo, mesmo quando o
    # documento nao tem a chave (`d.get(campo, 0)`/`d.get(campo, 0.0)` na
    # leitura cobre so o caso hipotetico de documento legado sem o campo,
    # nunca observado no unico escritor atual). `tipo` e sempre string --
    # `d.get("tipo") or doc.id`, e `doc.id` e garantido string pelo SDK do
    # Firestore quando `tipo` estiver ausente. `sugerida_em` passa pela
    # `_to_iso` PROPRIA deste modulo (mesmo corpo de
    # `agent_runs.py`/`agent_requests.py`, mas uma DUPLICATA independente,
    # mesma categoria de achado ja registrado para `consultar_pedidos_
    # agente`) -- sempre string ou `None`, nunca outro tipo.
    #
    # `erro` (ramo de erro) e `str(exc)` sobre a excecao real capturada --
    # sempre string, nunca vazio (uma excecao Python sempre tem alguma
    # representacao textual, mesmo que vazia a mensagem em si `str(exc)`
    # nunca levanta).
    "consultar_promocoes_autonomia_sugeridas": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "total": {"type": "integer"},
                    "promocoes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tipo": {"type": "string"},
                                "status": {"type": "string", "enum": ["pendente"]},
                                "amostra": {"type": "integer"},
                                "aprovados_sem_edicao": {"type": "integer"},
                                "taxa_sem_edicao": {"type": "number"},
                                "sugerida_em": {"type": ["string", "null"]},
                            },
                            "required": [
                                "tipo", "status", "amostra",
                                "aprovados_sem_edicao", "taxa_sem_edicao", "sugerida_em",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["total", "promocoes"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "erro": {"type": "string"},
                    "total": {"type": "integer"},
                    "promocoes": {"type": "array", "maxItems": 0},
                },
                "required": ["erro", "total", "promocoes"],
                "additionalProperties": False,
            },
        ],
    },
    # `obter_fila_atencao` (P03 sub-entrega 30/N) -- decima quarta tool com
    # outputSchema. Forma UNICA, sem oneOf: `atencao.coletar_fila_atencao`
    # nao tem nenhum `try/except` que devolva um ramo de erro alternativo --
    # sempre `{"total": int, "itens": [...]}`, mesma categoria de
    # `consultar_lista_compras`/`consultar_status_modo_secretario`.
    #
    # `total` e sempre `len(itens)` calculado ANTES do corte por `limite`
    # (`atencao.py:902-906`: `itens.sort(...)`, depois `"total": len(itens),
    # "itens": itens[:limite_ajustado]` -- `itens` nunca e reatribuido, so
    # fatiado na resposta) -- MESMO comportamento de
    # `consultar_promocoes_autonomia_sugeridas` (achado da 1a rodada de
    # revisao adversarial desta sub-entrega: a redacao original desta
    # mesma linha, antes da correcao, tinha essa relacao invertida --
    # dizia "apos o corte" e "diferente de"). Confirmado empiricamente com
    # `MockDb` (5 docs, `limite=2`): `total == 5`, `len(itens) == 2`. Nao
    # e uma garantia do outputSchema (`total` e so `{"type": "integer"}`,
    # sem relacao formal com `len(itens)` no schema) -- so uma nota de
    # comportamento real, para quem for consumir a tool. Cada item e
    # RECONSTRUIDO campo a campo com
    # `d.get(chave)` (nunca `doc.to_dict()` cru) -- mesma garantia de forma
    # de `consultar_promocoes_autonomia_sugeridas`, independente de quantos
    # escritores a colecao `atencao` tenha.
    #
    # Escritores da colecao (busca exaustiva, grep por `atencao.COLLECTION`/
    # `collection("atencao")` no repositorio inteiro, todos lidos por
    # completo): `atencao.py::_persistir_itens_atencao` (usada por
    # `avaliar_etapas`/`detectar_atencao_financeiro`/
    # `avaliar_rotinas_saude`/`detectar_emails_nao_entregues`),
    # `atencao_whatsapp.py::vencer_promessas` e `_processar_audio`, e
    # `secretario_whatsapp.py::registrar_investigacao_concluida_atencao` e
    # `escalar_para_atencao`. Nenhum outro ponto do repositorio cria
    # documento nessa colecao (`outbox_aprovacao.py:693` so faz `.update()`
    # de `estado`/`resolvido_em`/`desfecho`, nunca toca `tipo`/`origem`/
    # `prioridade`).
    #
    # `tipo` e enum FECHADO de 10 valores -- o unico campo desta tool que
    # aceita um parametro livre (`tipo_atencao: str` em
    # `secretario_whatsapp.escalar_para_atencao`) tem exatamente 2 call
    # sites em todo o repositorio (`secretario_whatsapp.py`, dentro do
    # proprio modulo), e os dois so passam constantes ja cobertas pelo
    # enum (`TIPO_ATENCAO_INSISTENCIA`, `TIPO_ATENCAO_ASSUNTO_SENSIVEL` ou
    # `TIPO_ATENCAO_DECISAO_FORCADA`) -- nunca uma string arbitraria. As
    # constantes `TIPO_ATENCAO_*` de `secretario_whatsapp.py` e as
    # `TIPO_SECRETARIO_*` equivalentes de `atencao.py` tem o MESMO valor
    # string (ex.: as duas resolvem para `"secretario_insistencia"`) --
    # alias, nao um par de valores divergentes.
    #
    # `origem` e enum de 8 valores, o MESMO conjunto ja validado no
    # `inputSchema` desta tool (`tools/schemas/obter_fila_atencao.json`) --
    # mas so 6 sao de fato escritos hoje (`acao`, `financeiro`, `saude`,
    # `email`, `whatsapp`, `secretario_whatsapp`; `agenda`/`repo` nao tem
    # nenhum escritor implementado ainda). Mantido nos 8 do inputSchema
    # (nao reduzido aos 6 observados) para nao criar um contrato mais
    # estreito que o proprio filtro que a tool ja aceita -- se um escritor
    # futuro usar `agenda`/`repo` (o inputSchema ja antecipa os dois), o
    # outputSchema nao ficaria desatualizado no mesmo instante. Mesmo
    # raciocinio aplicado a `prioridade` (enum de 3 -- `alta`/`media`/
    # `baixa`, as 3 constantes de `atencao.PRIORIDADE_*` -- ainda que
    # `baixa` nao tenha escritor hoje; usada em `_PRIORITY_ORDER` como
    # parte do modelo de dados). `estado` e o mesmo enum de 5 valores ja
    # no inputSchema (`aberto`/`delegado_ao_agente`/`aguardando_andre`/
    # `resolvido`/`descartado`), confirmado contra as constantes
    # `atencao.ESTADOS`.
    #
    # `acao_id`/`etapa_id`/`pessoa`/`sugestao` sao sempre chaves presentes
    # (todo escritor inclui a chave, `None` quando nao aplicavel). `prazo`/
    # `criado_em`/`atualizado_em`/`resolvido_em` passam por
    # `atencao._to_iso` na leitura -- sempre string ISO ou `None`, nunca
    # outro tipo (mesma funcao/mesma garantia de `agent_runs.py`/
    # `agent_requests.py`, ja usada em tools anteriores). `resolvido_em`/
    # `desfecho` so ganham valor quando `resolver_item` fecha o item
    # (`novo_estado` em `ESTADOS_FECHADOS`) -- e podem voltar a `None`
    # explicitamente (`outbox_aprovacao.py:693-697`, quando um descarte e
    # desfeito) -- por isso nullable, nunca ausentes como chave.
    # `evidencia` e sempre um dict (nunca `None`, `d.get("evidencia") or
    # {}` na leitura) mas o formato interno varia por tipo de item --
    # schema deliberadamente raso (`type: object`, sem `properties`),
    # mesma escolha ja usada para campos de forma variavel noutras tools
    # deste catalogo.
    #
    # CORRECAO (achado da revisao do Codex na PR desta sub-entrega, apos a
    # revisao adversarial propria): `origem`/`tipo`/`prioridade`/`titulo`/
    # `resumo`/`sugestao`/`estado` sao `d.get(chave)` SEM nenhum default --
    # ao contrario do que a redacao original deste comentario assumia
    # (\"sempre string\"/\"nunca None\", com base so nos escritores REAIS
    # de hoje), `coletar_fila_atencao` le QUALQUER documento da colecao de
    # forma generica, sem exigir nenhum desses campos -- um documento
    # esparso (sem `titulo`/`resumo`/etc, cenario ja exercitado por
    # `test_atencao.py::TestFilaAtencaoTools.test_coletar_fila_atencao_
    # ordenacao`, que grava `item-1`/`item-2`/`item-3` só com `estado`/
    # `prioridade`/`prazo`/`criado_em`) devolve `None` para todos os
    # outros campos. `id` (`doc.id`, garantido pelo SDK),
    # `chave_dedupe` (`d.get(...) or doc.id`) e `evidencia` (`d.get(...)
    # or {}`) continuam nao-nulos por terem fallback explicito -- so esses
    # 3 seguem `required` sem `null`. Os 7 campos acima (incluindo os 4
    # com enum) agora sao `["string", "null"]`, com `null` tambem
    # explicito em cada lista `enum` (JSON Schema nao trata `type` e
    # `enum` como equivalentes -- `null` so valida contra `enum` se
    # estiver LITERALMENTE na lista, mesmo com `"type": ["string",
    # "null"]` declarado ao lado).
    #
    # RISCO ACEITO, nao corrigido (SEGUNDO achado do Codex, desta vez na
    # PR do diario desta sub-entrega): a correcao acima fecha so o caso
    # "campo ausente" (`None`). `coletar_fila_atencao` nao valida nem
    # normaliza NADA do que le -- um documento com um valor PRESENTE mas
    # fora do conjunto esperado (ex.: `tipo=\"legado\"`, fora dos 10 do
    # enum; `evidencia=\"texto\"`, nao um dict -- `d.get(\"evidencia\") or
    # {}` so cai no fallback `{}` para valor FALSY, um valor truthy
    # nao-dict passa direto) violaria este outputSchema. Este schema
    # descreve a forma GARANTIDA pelos escritores rastreados hoje (busca
    # exaustiva), nao uma invariante reforcada em tempo de leitura -- um
    # documento fora desses caminhos (edicao manual no Firestore, dado
    # legado anterior a esta decisao, fixture de seed, ou bug futuro em
    # algum escritor) quebraria o contrato. Corrigir exigiria normalizar/
    # validar dentro de `coletar_fila_atencao` (mudanca de COMPORTAMENTO,
    # fora do escopo de uma fatia so-schema) ou validacao de outputSchema
    # em tempo de execucao em `mcp_server.py` (inexistente hoje para
    # NENHUMA das 14 tools deste catalogo -- limitacao estrutural do
    # catalogo inteiro, nao especifica desta tool). Mesma categoria de
    # risco ja aceita para outras tools (ex.: `consultar_lista_compras`/
    # `shopping_items`, tambem escrita por caminhos fora de
    # `tools/lista_compras.py`, ver comentario acima).
    "obter_fila_atencao": {
        "type": "object",
        "properties": {
            "total": {"type": "integer"},
            "itens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "origem": {
                            "type": ["string", "null"],
                            "enum": [
                                "acao", "whatsapp", "email", "agenda",
                                "repo", "financeiro", "saude", "secretario_whatsapp",
                                None,
                            ],
                        },
                        "tipo": {
                            "type": ["string", "null"],
                            "enum": [
                                "aguardando_terceiro_vencido", "conta_vencendo",
                                "rotina_saude_ausente", "email_nao_entregue",
                                "promessa_sem_retorno", "audio_relevante",
                                "secretario_investigacao_concluida",
                                "secretario_insistencia", "secretario_assunto_sensivel",
                                "secretario_decisao_forcada",
                                None,
                            ],
                        },
                        "prioridade": {
                            "type": ["string", "null"], "enum": ["alta", "media", "baixa", None],
                        },
                        "titulo": {"type": ["string", "null"]},
                        "resumo": {"type": ["string", "null"]},
                        "acao_id": {"type": ["string", "null"]},
                        "etapa_id": {"type": ["string", "null"]},
                        "pessoa": {"type": ["string", "null"]},
                        "prazo": {"type": ["string", "null"]},
                        "evidencia": {"type": "object"},
                        "sugestao": {"type": ["string", "null"]},
                        "estado": {
                            "type": ["string", "null"],
                            "enum": [
                                "aberto", "delegado_ao_agente", "aguardando_andre",
                                "resolvido", "descartado", None,
                            ],
                        },
                        "chave_dedupe": {"type": "string"},
                        "criado_em": {"type": ["string", "null"]},
                        "atualizado_em": {"type": ["string", "null"]},
                        "resolvido_em": {"type": ["string", "null"]},
                        "desfecho": {"type": ["string", "null"]},
                    },
                    "required": [
                        "id", "origem", "tipo", "prioridade", "titulo", "resumo",
                        "acao_id", "etapa_id", "pessoa", "prazo", "evidencia",
                        "sugestao", "estado", "chave_dedupe", "criado_em",
                        "atualizado_em", "resolvido_em", "desfecho",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["total", "itens"],
        "additionalProperties": False,
    },
    # `consultar_elevacoes_sugeridas` (P03 sub-entrega 31/N) -- decima
    # quinta tool com outputSchema. Candidata que restava da lista original
    # de 5 da sub-entrega 27/N (junto com `listar_conversas_whatsapp`),
    # descartada na sub-entrega 11/N pelo MESMO motivo que ja tinha
    # bloqueado `consultar_promocoes_autonomia_sugeridas` -- decidir se o
    # contrato cobre sucesso e erro, investigacao maior que aquela fatia.
    # Mesma retomada da sub-entrega 29/N: o padrao `oneOf` de duas formas
    # DISJUNTAS (sucesso/erro) ja esta estabelecido desde `consultar_
    # historico_acoes` (sub-entrega 14/N) e reusado repetidamente desde
    # entao (mais recente: `consultar_promocoes_autonomia_sugeridas`,
    # 29/N).
    #
    # Handler (`tools/hermes_tools.py::_consultar_elevacoes_sugeridas`) e
    # passthrough puro: so resolve o default de `limite`
    # (`int(args.get("limite") or 20)`, mesma expressao/mesmo `or` de
    # `consultar_promocoes_autonomia_sugeridas`/`obter_fila_atencao` --
    # `limite=0` explicito tambem vira `20`) antes de repassar a
    # `deteccao_subproduto.listar_pendentes`, que tem exatamente DUAS
    # formas de retorno, nunca uma terceira:
    #   - sucesso: `{"total": int, "sugestoes": [...]}` (a consulta ao
    #     Firestore correu bem, mesmo sem nenhum resultado)
    #   - erro: `{"total": 0, "sugestoes": [], "erro": str(exc)}` -- so
    #     quando o `.stream()` da query levanta excecao (`try/except`
    #     dentro da propria funcao); `total`/`sugestoes` ficam FIXOS em
    #     `0`/`[]` nesse ramo (hardcoded no `return` do `except`, nao
    #     ecoados de nenhum calculo), mesma convencao ja usada em
    #     `consultar_promocoes_autonomia_sugeridas`/`consultar_historico_
    #     acoes`/`buscar_arquivos_acervo`.
    #
    # Escritor da colecao `elevacoes_sugeridas`
    # (`deteccao_subproduto.COL_ELEVACOES`): busca exaustiva no
    # repositorio (grep por `collection(COL_ELEVACOES)`/`COL_ELEVACOES`)
    # encontra 1 UNICO ponto de CRIACAO de documento --
    # `registrar_sugestao` (linha ~693), chamada por sua vez de UM UNICO
    # call site em todo o repositorio (`_ferramenta_propor`, dentro da
    # rodada de deteccao de subproduto). Os outros usos de `COL_ELEVACOES`
    # (`decidir`/`_aplicar_decisao`) so fazem `transaction.update`/
    # `.update` sobre um documento ja existente, MOVENDO `status` PARA
    # FORA de `pendente` (`aceita`/`adiada`/`nunca`) -- nunca gravam
    # `status="pendente"` nem tocam `titulo_acao`/`nome_objetivo`/
    # `motivo_escassez`/`resumo`/`criada_em`/`concluida_em`/`antigo`.
    # Combinado com o filtro da propria QUERY de leitura
    # (`listar_pendentes` faz `.where("status", "==", STATUS_PENDENTE)`),
    # `status` NAO aparece no item lido (`listar_pendentes` nem devolve
    # esse campo por item -- so usa o filtro para selecionar os
    # documentos), entao nao ha campo `status` no schema do item, so no
    # filtro da leitura.
    #
    # `sugestao_id` e sempre `d.id` -- garantido string pelo SDK do
    # Firestore, mesmo para um documento esparso. `antigo` e sempre
    # `bool(dados.get("antigo"))` -- `bool(None)` e `False`, nunca `None`,
    # nunca outro tipo, mesmo se a chave estiver ausente.
    #
    # CORRECAO (achado da revisao do Codex na PR desta sub-entrega, mesma
    # categoria do achado ja registrado para `obter_fila_atencao` na
    # sub-entrega 30/N -- e o MESMO erro de analise: rastrear so o
    # escritor REAL de hoje, sem considerar que a funcao de LEITURA nao
    # exige nada do documento): a redacao original deste comentario
    # afirmava que `acao`/`objetivo`/`motivo_escassez`/`resumo`/
    # `criada_em` eram SEMPRE string/nunca `None`, com base so no unico
    # escritor de criacao rastreado (`registrar_sugestao`, via
    # `titulo_acao`/`nome_objetivo` sempre `str(...)`, `motivo_escassez`
    # validado por `validar_proposta` contra `MOTIVOS_ESCASSEZ`, `resumo`
    # sempre o retorno em f-string de `resumo_para_o_usuario`, `criada_em`
    # sempre o parametro `hoje`). Isso e verdade PARA ESSE escritor, mas
    # `listar_pendentes` (`deteccao_subproduto.py:1523-1554`) le QUALQUER
    # documento com `status == STATUS_PENDENTE` de forma generica --
    # `dados.get(chave)` SEM default para todos os 5 campos acima --
    # entao um documento esparso na colecao (cenario ja exercitado por
    # `test_deteccao_subproduto.py::TestOContadorNaoRecomecaDoZero::
    # test_a_rodada_leva_a_contagem_do_historico_como_piso`, que grava
    # `status=pendente` so com `task_id`/`criada_em`, sem nenhum dos
    # outros campos) devolve `None` para os campos ausentes. Corrigido
    # para `["string", "null"]` nos 5 campos (`motivo_escassez` com `null`
    # tambem explicito na propria lista `enum`, exigencia do JSON Schema),
    # com teste de regressao dedicado. `concluida_em` ja era nullable
    # (`concluida_em or None` no payload de `registrar_sugestao`) -- sem
    # mudanca. `sugestao_id`/`antigo` continuam nao-nulos (ver acima).
    #
    # RISCO ACEITO, nao corrigido (mesma categoria ja aceita para
    # `obter_fila_atencao`/`consultar_lista_compras`): a correcao acima
    # fecha so o caso "campo ausente" (`None`). `listar_pendentes` nao
    # valida nem normaliza NADA do que le -- um documento com um valor
    # PRESENTE mas fora do conjunto esperado (ex.: `motivo_escassez`
    # gravado fora do enum por um escritor futuro ou por edicao manual)
    # violaria este outputSchema. Corrigir exigiria normalizar/validar
    # dentro de `listar_pendentes` (mudanca de COMPORTAMENTO, fora do
    # escopo desta fatia) ou validacao de outputSchema em tempo de
    # execucao (inexistente hoje para as 15 tools deste catalogo).
    #
    # `erro` (ramo de erro) e `str(exc)` sobre a excecao real capturada --
    # sempre string, mesma garantia ja usada nas tools anteriores com
    # ramo de erro.
    #
    # ACHADO da revisao adversarial desta sub-entrega, nao corrigido aqui
    # (comportamento pre-existente de `listar_pendentes`, nao introduzido
    # por este outputSchema): `total` e `len(pendentes)` calculado sobre a
    # lista JA LIMITADA pela propria query Firestore (`.limit(200)`,
    # `deteccao_subproduto.py:1537`) e ANTES do corte por `limite`
    # (`pendentes[:limite]` no `return`, `pendentes` nunca reatribuido) --
    # mesma relacao total-antes-do-corte ja documentada para `obter_fila_
    # atencao`/`consultar_promocoes_autonomia_sugeridas`. A diferenca aqui:
    # se houver MAIS de 200 sugestoes pendentes na seleco (`status ==
    # STATUS_PENDENTE`), `total` fica silenciosamente TETADO em 200 (nunca
    # reflete a contagem real acima disso) -- nao e uma garantia do
    # outputSchema (`total` e so `{"type": "integer"}`, sem relacao formal
    # com `len(sugestoes)` ou com a contagem real no Firestore), so uma
    # nota de comportamento real para quem for consumir a tool. Nao
    # corrigido nesta fatia -- mudar a query e o corte e mudanca de
    # COMPORTAMENTO de `listar_pendentes`, fora do escopo de uma fatia
    # so-schema (mesmo criterio ja aplicado ao risco residual aceito de
    # `obter_fila_atencao`, sub-entrega 30/N).
    "consultar_elevacoes_sugeridas": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "total": {"type": "integer"},
                    "sugestoes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sugestao_id": {"type": "string"},
                                "acao": {"type": ["string", "null"]},
                                "objetivo": {"type": ["string", "null"]},
                                "motivo_escassez": {
                                    "type": ["string", "null"],
                                    "enum": ["repetivel", "raro", "ja_escrito", None],
                                },
                                "resumo": {"type": ["string", "null"]},
                                "criada_em": {"type": ["string", "null"]},
                                "concluida_em": {"type": ["string", "null"]},
                                "antigo": {"type": "boolean"},
                            },
                            "required": [
                                "sugestao_id", "acao", "objetivo", "motivo_escassez",
                                "resumo", "criada_em", "concluida_em", "antigo",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["total", "sugestoes"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "erro": {"type": "string"},
                    "total": {"type": "integer"},
                    "sugestoes": {"type": "array", "maxItems": 0},
                },
                "required": ["erro", "total", "sugestoes"],
                "additionalProperties": False,
            },
        ],
    },
    # `listar_conversas_whatsapp` (P03 sub-entrega 32/N) -- decima sexta
    # tool com outputSchema, e a ULTIMA candidata da lista original de 5
    # da sub-entrega 27/N (as outras 4 ja resolvidas: `consultar_
    # contatos_prioritarios_secretario` 28/N, `consultar_promocoes_
    # autonomia_sugeridas` 29/N, `obter_fila_atencao` 30/N, `consultar_
    # elevacoes_sugeridas` 31/N). `oneOf` de 2 branches (sucesso/erro) --
    # CORRIGIDO de "forma unica" apos a 1a rodada de revisao adversarial
    # desta sub-entrega achar que a redacao original estava ERRADA:
    # `whatsapp_tools.listar_conversas` NAO tem `try/except` proprio, mas
    # `limite = max(1, min(int(args.get("limite") or 60), 200))`
    # (`whatsapp_tools.py:141`) nao e protegido -- um `limite` que nao
    # parseia como inteiro (ex.: `"abc"`) levanta `ValueError` DENTRO de
    # `listar_conversas`, que propaga para o wrapper que expoe a tool
    # (`tools/hermes_tools.py::_whatsapp`), cujo `except ValueError as exc:
    # return {"erro": str(exc)}` (linha 1898-1899) converte a excecao num
    # dict REAL `{"erro": "..."}`, devolvido por `execute_tool` como
    # sucesso de chamada (nao uma excecao no proprio `execute_tool`).
    # `mcp_server._handle_tools_call` publica `structuredContent` sempre
    # que o resultado e um dict E ha `outputSchema` publicado, sem
    # distinguir erro reconhecido de sucesso -- entao esse dict `{"erro":
    # ...}` seria publicado como `structuredContent`, violando a forma
    # unica original (`additionalProperties: false` sem chave `erro`,
    # `required` exigindo as 4 chaves da forma de sucesso). Nenhum dos 3
    # testes de integracao originais capturava isso porque todos mockam
    # `mcp_server.execute_tool` diretamente, pulando a cadeia real
    # `_whatsapp` -> `listar_conversas`. `WhatsAppNaoMonitorado` continua
    # NUNCA levantada por `listar_conversas` (so por `_exigir_monitorado`,
    # nunca chamada por ela) -- confirmado de novo na correcao, entao o
    # ramo de erro tem UMA forma so, so a chave `erro` (nao a forma
    # `{"erro":..., "motivo": "chat_nao_monitorado"}` do outro `except`).
    #
    # `total` (`len(conversas)`) e `monitoradas` (`sum(1 for c in
    # conversas if c["monitorada"])`) sao sempre inteiros, mas --
    # CORRIGIDO na mesma rodada, redacao original tambem imprecisa aqui --
    # calculados sobre a lista JA FILTRADA por `apenas_monitoradas`
    # (`whatsapp_tools.py:153-154`: quando `apenas_monitoradas` e `True`,
    # o padrao quando o argumento e omitido, um chat nao monitorado nunca
    # chega a entrar em `conversas` -- o `continue` acontece ANTES do
    # `append`). Na chamada padrao (sem `apenas_monitoradas` explicito),
    # `total` conta so os chats monitorados, nunca o total real de
    # `whatsapp_chats`, e `monitoradas` sempre EQUIVALE a `total` (todo
    # item que sobrou tem `monitorada=True`) -- só com
    # `apenas_monitoradas=false` explicito os dois podem divergir. Dito
    # isso, permanece verdade que NAO ha corte por `.limit(N)` de QUERY do
    # Firestore antes dessa contagem (`whatsapp_tools.py:144-148` documenta
    # a decisao deliberada de nao limitar a leitura antes de ordenar) --
    # `limite` so corta a lista `conversas` na resposta
    # (`conversas[:limite]`), nunca afeta `total`/`monitoradas`.
    # `observacao` e sempre string -- a cadeia de expressoes ternarias em
    # `listar_conversas` (linhas 173-182) sempre resolve para um texto,
    # nunca `None`.
    #
    # Cada item de `conversas` e RECONSTRUIDO campo a campo (nao
    # `snap.to_dict()` cru): `chat_id` e sempre `str(dados.get("chat_id")
    # or snap.id)` -- `snap.id` e garantido pelo SDK do Firestore, entao
    # `chat_id` nunca e vazio nem `None`, e a coercao `str(...)` cobre
    # qualquer tipo bruto que `dados.get("chat_id")` devolva. `chat_name`
    # e `dados.get("chat_name") or chat_id`, SEM a mesma coercao `str(...)`
    # -- RISCO ACEITO, achado da 1a rodada de revisao adversarial: se um
    # documento tiver `chat_name` PRESENTE mas truthy-e-nao-string (ex.:
    # um numero, lista ou dict), o fallback por `or` nao entra em acao e o
    # valor cru passa direto, violando `{"type": "string"}`. Nenhum
    # escritor real conhecido grava isso (`chat_name` e sempre string no
    # worker Node de captura), mas a funcao de leitura nao normaliza esse
    # caso -- mesma categoria de risco ja aceita para campos de forma
    # variavel noutras tools deste catalogo (ex.: `evidencia` em
    # `obter_fila_atencao`), nao corrigido aqui por ser mudanca de
    # COMPORTAMENTO fora do escopo de uma fatia so-schema. `grupo`
    # (`bool(dados.get("is_group"))`), `monitorada` e `capturada` sao
    # sempre `bool`, nunca `None` (nenhum dos tres usa `dados.get` sem
    # `bool(...)`/expressao booleana em volta). `ultima_atividade` e o
    # UNICO campo nullable do item -- `_iso(dados.get("last_activity_ts"))`
    # devolve `None` explicitamente quando o valor bruto e `None`
    # (`_iso`, linha 120-123).
    #
    # Escritor da colecao `whatsapp_chats` (`COL_CHATS`): fora do escopo
    # desta fatia detalhar (e o worker WhatsApp em Node,
    # `services/whatsapp-capture/`, nao o codigo Python deste repositorio)
    # -- mas nao importa QUEM escreve, porque `listar_conversas` nunca
    # confia em nenhum campo do documento sem passar por um `.get(chave)
    # or default`/`bool(...)`/`_iso(...)` explicito antes de devolver
    # (exceto `chat_name`, ver risco aceito acima). Igual ao padrao ja
    # usado para `consultar_lista_compras`/`evidencia` em `obter_fila_
    # atencao`: a garantia de forma vem da FUNCAO DE LEITURA, nao do(s)
    # escritor(es).
    #
    # `erro` (ramo de erro) e sempre `str(exc)` sobre o `ValueError` real
    # capturado pelo wrapper -- mesma garantia ja usada nas tools
    # anteriores com ramo de erro.
    "listar_conversas_whatsapp": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "total": {"type": "integer"},
                    "monitoradas": {"type": "integer"},
                    "conversas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "chat_id": {"type": "string"},
                                "chat_name": {"type": "string"},
                                "grupo": {"type": "boolean"},
                                "monitorada": {"type": "boolean"},
                                "capturada": {"type": "boolean"},
                                "ultima_atividade": {"type": ["string", "null"]},
                            },
                            "required": [
                                "chat_id", "chat_name", "grupo",
                                "monitorada", "capturada", "ultima_atividade",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "observacao": {"type": "string"},
                },
                "required": ["total", "monitoradas", "conversas", "observacao"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "erro": {"type": "string"},
                },
                "required": ["erro"],
                "additionalProperties": False,
            },
        ],
    },
}


def output_schema(tool_name: str) -> dict | None:
    """`outputSchema` (protocolo MCP) para o catalogo publicado em
    `tools/list`, quando ha um contrato de dados definido e verificado para
    a tool -- P03 passo 3 ("Adicionar outputSchema, structuredContent,
    annotations e envelope aos caminhos compativeis; manter content
    legado"), a fatia que faltava depois de `annotations` (sub-entregas
    6/N e 7/N, ver `mcp_annotations` acima). `None` para qualquer tool sem
    entrada em `_OUTPUT_SCHEMAS` -- a MAIORIA do catalogo (92 das 108 tools
    hoje -- `len(registry.list_tool_names())`, nao os "106" que este
    docstring citava ate a sub-entrega 24/N, contagem ja desatualizada
    antes daquela fatia -- apos a decima sexta entrada, `listar_
    conversas_whatsapp`, sub-entrega 32/N, que esgota a lista original de
    5 candidatas da sub-entrega 27/N), deliberadamente:
    cada tool exige investigar a forma real do retorno do handler antes de
    publicar um contrato, mesma disciplina das outras funcoes deste modulo
    (nunca uma derivacao automatica ou heuristica sobre o dict de retorno).

    `mcp_server._handle_tools_call` usa esta mesma funcao para decidir se
    inclui `structuredContent` no envelope de `tools/call` -- as duas
    pontas (o schema publicado em `tools/list` e o dado publicado em
    `tools/call`) tem que vir da MESMA fonte, senao um cliente que valida
    `structuredContent` contra o `outputSchema` anunciado pode ver os dois
    divergirem com o tempo.
    """
    return _OUTPUT_SCHEMAS.get(tool_name)
