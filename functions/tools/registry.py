import json
import os

from tools.inventory import (
    DominioRede,
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
    "ativar_modo_secretario": "Ativa o Modo Secretário no WhatsApp com contatos autorizados e duração opcional",
    "desativar_modo_secretario": "Desativa imediatamente o Modo Secretário no WhatsApp",
    "consultar_status_modo_secretario": "Consulta o status atual do Modo Secretário (ativo, contatos na allowlist e expiração)",
    # Motor de política de autonomia (P02 passo 7, autonomy/policy.py) — leitura
    # e simulação, nunca aplicação direta: `preparar_politica` só devolve um
    # diff, nunca persiste nada sozinho.
    "consultar_politica": "Consulta a política de autonomia vigente para um escopo: permissões, limites, versão e origem",
    "simular_politica": "Avalia um lote de pedidos hipotéticos contra a política de autonomia, sem aplicar nada",
    "preparar_politica": "Prepara uma proposta de mudança na política de autonomia contra uma versão base, devolvendo um diff explícito",
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
    # Aprovação e descarte de rascunhos de WhatsApp via Cowork
    "aprovar_rascunho_whatsapp",
    "descartar_rascunho_whatsapp",
    # Portao de autorizacao Telegram para o conector Claude-Argos: as duas que
    # mutam estado (pedir e consumir); consultar e so leitura, fica de fora.
    "solicitar_autorizacao_argos",
    "consumir_autorizacao_argos",
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
    `openWorldHint`) para o catalogo publicado em `tools/list` -- P03 passo 3
    do plano de autonomia ("Adicionar outputSchema, structuredContent,
    annotations e envelope aos caminhos compativeis"). `readOnlyHint`/
    `destructiveHint` vieram da sub-entrega 6/N; `openWorldHint`, desta
    sub-entrega 7/N. `outputSchema`/`structuredContent`/envelope seguem fora
    de escopo -- exigem definir um contrato de dados por tool, ver
    docs/autonomia/execucao.md.

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

    `idempotentHint` continua inteiramente fora de escopo: pede saber, por
    HANDLER, se chamar de novo com os MESMOS argumentos tem efeito
    adicional (ex.: `criar_acao_no_sistema` dedupla por titulo/data;
    `agendar_lembrete_acao` nao dedupla nada) -- nenhum campo do inventario
    atual registra isso (nem `dominio_rede`, que e sobre O QUE a tool
    alcança pela rede, nao sobre REPETIR a chamada sem custo); precisaria de
    investigacao dedicada por handler, do mesmo porte da sub-entrega 1/N,
    candidata a uma sub-entrega futura propria.

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
    if entry.dominio_rede == DominioRede.FECHADO:
        annotations["openWorldHint"] = False
    elif entry.dominio_rede == DominioRede.ABERTO:
        annotations["openWorldHint"] = True
    return annotations
