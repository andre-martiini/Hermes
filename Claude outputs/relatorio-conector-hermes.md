# Relatório: Conector Sistema Hermes — Ferramentas Disponíveis

**Data:** 06/09/2026
**Servidor MCP:** `Sistema_Hermes`
**Total de ferramentas:** 101

## Visão geral

O Hermes é o sistema de gestão pessoal e profissional do André: ações e tarefas, agenda, finanças, saúde, contatos, acervo de documentos e memória de longo prazo. O conector expõe 101 ferramentas MCP que dão a um agente de IA acesso de leitura e escrita a esses módulos. Abaixo, cada ferramenta agrupada por área funcional, com uma explicação breve do que faz.

Convenção de nomes: ferramentas `consultar_*`/`obter_*`/`listar_*`/`buscar_*` são leitura; `criar_*`/`registrar_*`/`editar_*` costumam gravar direto; `preparar_*` monta uma proposta sem gravar (exige um `confirmar_*` depois); campos `_confirmation_id`/`_confirmed` indicam uma prévia que precisa de confirmação explícita antes do efeito real.

---

## 1. Estado do dia e fila de atenção

| Ferramenta | O que faz |
|---|---|
| `obter_estado_atual` | Panorama do dia numa chamada só: ações de hoje, herdadas do dia anterior, críticas, agenda, janelas livres e pendências. Ponto de partida de uma sessão. |
| `obter_fila_atencao` | Lista itens que pedem decisão ou acompanhamento (retorno de terceiro vencido, promessa pendente etc.), com filtro por estado e origem. |
| `resolver_item_atencao` | Resolve, descarta ou delega um item da fila de atenção, com desfecho registrado. |

## 2. Ações e tarefas

| Ferramenta | O que faz |
|---|---|
| `criar_acao_no_sistema` | Cria uma nova ação/tarefa (título, área temática, data, recorrência, plano de ação inicial, tags). |
| `obter_acao` | Devolve uma ação específica por completo e sem truncamento (título, descrição, plano, anexos, diário). |
| `obter_contexto_tela` | Contexto completo de uma tarefa: diário, plano e arquivos disponíveis. |
| `consultar_historico_acoes` | Busca ações/tarefas/projetos por frase natural, sinônimos ou número de processo, com filtros de status/área/data. |
| `editar_acao` | Edita uma ação diretamente (título, data, status, notas etc.), sem passo de preparação. |
| `editar_acoes_em_lote` | Edita várias ações de uma vez, diretamente. |
| `registrar_no_diario` | Registra uma entrada livre no diário de bordo de uma ação. |
| `agendar_lembrete_acao` | Agenda um lembrete para uma ação existente. |

## 3. Planos de ação e operações em lote (com prévia)

| Ferramenta | O que faz |
|---|---|
| `editar_plano_acao` | Atualiza o plano de etapas de uma tarefa — inclui marcar etapa como em andamento/aguardando terceiro/feita. |
| `preparar_edicao_acao` | Monta uma proposta de edição de uma ação, sem gravar. |
| `confirmar_edicao_acao` | Aplica a edição montada por `preparar_edicao_acao`. |
| `preparar_edicao_em_lote` | Monta proposta de edição de campos para várias ações, sem gravar. |
| `confirmar_edicao_em_lote` | Aplica a edição em lote montada por `preparar_edicao_em_lote`. |
| `preparar_reagendamento_em_lote` | Monta proposta de redistribuição de várias ações por dias úteis, sem gravar. |
| `preparar_remocao_horarios_em_lote` | Monta proposta de remoção de horários de várias ações, sem gravar. |
| `confirmar_reagendamento_em_lote` | Aplica o reagendamento/remoção de horários montado pelas duas anteriores. |
| `reagendar_acoes_em_lote` | Redistribui ações por dias úteis e já aplica a mudança diretamente (sem prévia). |

## 4. Agenda (Google Calendar)

| Ferramenta | O que faz |
|---|---|
| `consultar_agenda` | Consulta eventos e compromissos num intervalo de datas. |
| `encontrar_slot_livre` | Encontra o próximo horário livre a partir de uma data, para uma duração desejada. |

## 5. Objetivos estratégicos, elevações e promoção de autonomia

| Ferramenta | O que faz |
|---|---|
| `criar_objetivo_estrategico` | Cria um objetivo estratégico (pilar, meta, diretrizes, indicadores, marcos). |
| `editar_objetivo_estrategico` | Edita campos de um objetivo estratégico existente. |
| `excluir_objetivo_estrategico` | Exclui definitivamente um objetivo estratégico. |
| `gerenciar_item_estrategico` | Adiciona, edita, remove ou conclui um indicador ou marco de um objetivo. |
| `consultar_elevacoes_sugeridas` | Lista sugestões de "elevação": trabalho já feito que pode virar um ativo com um passo a mais. |
| `decidir_elevacao` | Aplica a decisão do usuário sobre uma elevação sugerida (aceitar/adiar/nunca). |
| `consultar_promocoes_autonomia_sugeridas` | Lista sugestões de promover um tipo de rascunho WhatsApp para envio autônomo. |
| `decidir_promocao_autonomia` | Aplica a decisão sobre uma promoção de autonomia sugerida. |

## 6. WhatsApp — leitura e monitoramento

| Ferramenta | O que faz |
|---|---|
| `listar_conversas_whatsapp` | Lista conversas conhecidas, indicando quais estão monitoradas. |
| `ler_mensagens_whatsapp` | Lê mensagens de uma conversa monitorada, em ordem cronológica. |
| `buscar_conversas_whatsapp` | Busca conversas indexadas por similaridade semântica (o que foi discutido). |
| `consolidar_whatsapp` | Consolida um recorte de mensagens: transcreve áudio/vídeo, monta transcript e sintetiza resumo, ações e decisões (assíncrona). |
| `ler_consolidacao_whatsapp` | Lê o resultado de uma consolidação, por job_id ou pelas mais recentes de uma conversa. |

## 7. WhatsApp — rascunhos, envio e Modo Secretário

| Ferramenta | O que faz |
|---|---|
| `criar_rascunho_whatsapp` | Cria um rascunho de mensagem e envia card de aprovação ao Telegram do André; só envia após aprovação humana. |
| `listar_rascunhos_pendentes` | Lista rascunhos aguardando aprovação no Telegram. |
| `aprovar_rascunho_whatsapp` | Aprova um rascunho pendente, liberando para entrega imediata. |
| `descartar_rascunho_whatsapp` | Descarta um rascunho pendente. |
| `consultar_envio_whatsapp` | Estado real de uma mensagem enfileirada (pending/sent/failed) — necessário antes de afirmar que algo foi entregue. |
| `schedule_whatsapp_message` | Agenda ou envia uma mensagem de WhatsApp para um contato. |
| `pausar_conversa` | Prepara e, após confirmação, enfileira uma resposta curta de pausa numa conversa, marcando quando retomar. |
| `ativar_modo_secretario` | Ativa o Modo Secretário (Hermes responde no WhatsApp em nome do André quando indisponível). |
| `desativar_modo_secretario` | Desativa o Modo Secretário imediatamente. |
| `consultar_status_modo_secretario` | Consulta se o Modo Secretário está ativo, allowlist e validade. |
| `preparar_contato_prioritario_secretario` | Registra um briefing prioritário para um contato específico durante o Modo Secretário. |
| `consultar_contatos_prioritarios_secretario` | Lista os briefings prioritários cadastrados. |
| `cancelar_contato_prioritario_secretario` | Cancela/encerra antecipadamente um briefing prioritário. |
| `listar_respostas_pendentes` | Lista respostas pendentes e permite auditar itens filtrados por ruído. |

## 8. E-mail (Gmail)

| Ferramenta | O que faz |
|---|---|
| `buscar_e_analisar_email` | Busca e analisa e-mails por query padrão do Gmail. |
| `criar_rascunho_email` | Cria um rascunho no Gmail com anexos por referência; nunca envia. |

## 9. Financeiro

| Ferramenta | O que faz |
|---|---|
| `consultar_financas_v2` | Balanço financeiro detalhado (rendas, obrigações, metas, transações) de um mês/ano. |
| `registrar_item_financeiro_v2` | Registra uma nova movimentação (renda, obrigação fixa ou transação avulsa). |
| `consultar_fatura_cartao` | Lançamentos da fatura do cartão de crédito, com total por estabelecimento. |
| `consultar_compromissos_futuros` | Projeta quanto de cada mês futuro já está comprometido por compras parceladas no cartão. |

## 10. Investimentos

| Ferramenta | O que faz |
|---|---|
| `consultar_investimentos` | Carteira de investimentos: posição, valor de mercado, caixa, total aportado, rendimento vs. CDI (só leitura). |
| `registrar_aporte_investimento` | Registra dinheiro novo enviado à corretora (soma ao total aportado). |
| `registrar_execucao_investimento` | Registra a posição resultante depois de uma ordem executada no home broker. |

## 11. Saúde

| Ferramenta | O que faz |
|---|---|
| `consultar_saude` | Consulta peso, passos, calorias, sono e dor dos últimos dias ou de uma data específica. |
| `registrar_saude` | Registra o que o usuário declarou sobre o próprio dia (peso, dor, sono, calorias) — nunca por inferência. |

## 12. Contatos

| Ferramenta | O que faz |
|---|---|
| `buscar_contato` | Busca contatos por nome, e-mail ou tag. |
| `preparar_atualizacao_contato` | Propõe criação ou atualização de um contato com base em fatos revelados na conversa (gera card de confirmação). |
| `preparar_vinculo_contatos` | Propõe vincular pessoas mencionadas a uma tarefa (gera card de confirmação). |
| `registrar_interacao_contato` | Registra uma interação histórica silenciosa no perfil de um contato, sem confirmação. |

## 13. Processos SIPAC

| Ferramenta | O que faz |
|---|---|
| `consultar_processo_sipac` | Consulta dados gerais, interessados, movimentações e documentos de um processo. |
| `acompanhar_processo_sipac` | Ativa ou desativa o monitoramento automático de um processo. |

## 14. Integração Argos (portão de autorização via Telegram)

| Ferramenta | O que faz |
|---|---|
| `solicitar_autorizacao_argos` | Pede ao André, por card no Telegram, autorização para aprovar um plano ou enfileirar execução no Argos. |
| `consultar_autorizacao_argos` | Consulta o estado de uma solicitação (aguardando/aprovado/recusado/expirado) — só leitura. |
| `consumir_autorizacao_argos` | Marca uma autorização aprovada como usada, imediatamente antes de agir no Argos (uso único). |

## 15. Arquivos, anexos e uploads

| Ferramenta | O que faz |
|---|---|
| `anexar_arquivo` | Anexa um arquivo a uma ação (Drive + pool de dados + diário), numa chamada. |
| `preparar_upload` | Devolve uma URL assinada para subir um arquivo local direto ao storage, sem passar pela conversa. |
| `remover_anexo` | Remove um anexo de uma ação (manda para a lixeira do Drive, tira do pool, preserva trilha no diário). |
| `buscar_arquivos_acervo` | Busca documentos e manuais no Acervo Global do Hermes. |
| `ler_documento_na_integra` | Lê um documento do Drive e responde uma pergunta exata com base no conteúdo. |
| `ler_pagina_web` | Lê e extrai o conteúdo completo de uma URL. |

## 16. Lista de compras

| Ferramenta | O que faz |
|---|---|
| `consultar_lista_compras` | Lê a lista de compras (itens, categorias, planejado/comprado). |
| `mutar_lista_compras` | Cria, atualiza, remove ou importa itens da lista de compras. |

## 17. Portais públicos

| Ferramenta | O que faz |
|---|---|
| `obter_portal_compras_publico` | Lista itens do portal público de compras. |
| `mutar_portal_compras_publico` | Executa ações simples no portal público de compras (marcar planejado/comprado, atualizar quantidade). |
| `obter_portal_financeiro_publico` | Lista transações externas do portal financeiro público. |
| `registrar_transacao_financeira_publica` | Registra uma transação externa no portal financeiro público. |
| `obter_projeto_bolsas_publico` | Consulta dados públicos de um projeto de bolsas por ID. |
| `registrar_inscricao_bolsa_publica` | Registra uma inscrição pública num projeto de bolsas. |

## 18. Memória, procedimentos (POPs) e personalidade

| Ferramenta | O que faz |
|---|---|
| `salvar_memoria_global` | Salva um fato durável ou preferência permanente na memória global do Hermes. |
| `resolver_conflito_memoria` | Resolve um conflito de memória previamente detectado (manter existente ou substituir). |
| `salvar_pop_global` | Cria ou atualiza um POP (procedimento operacional padrão) persistido, com gatilhos. |
| `registrar_correcao_procedimento` | Registra uma correção ou melhoria num procedimento existente. |
| `resolver_conflito_procedimento` | Valida ou resolve um procedimento marcado para revisão. |
| `atualizar_personalidade` | Atualiza o texto-base da personalidade dinâmica do copiloto Hermes. |

## 19. Execução autônoma do agente

| Ferramenta | O que faz |
|---|---|
| `consultar_pedidos_agente` | Lista pedidos de trabalho autônomo enfileirados para o agente executar. |
| `concluir_pedido_agente` | Conclui ou registra erro num pedido de trabalho autônomo executado. |
| `registrar_execucao_agente` | Registra a execução de uma rotina agendada (para observabilidade e métricas). |
| `consultar_execucoes_agente` | Consulta o histórico de execuções recentes dessas rotinas. |
| `consultar_job` | Busca o resultado de uma tool assíncrona (que devolveu status "processing" e um job_id). |

## 20. Utilidades gerais

| Ferramenta | O que faz |
|---|---|
| `calculadora` | Cálculos ad-hoc ou projeções hipotéticas em chat (não para processar matrizes do banco). |
| `pesquisar_internet` | Busca informações recentes na internet via Tavily. |
| `gerar_imagem` | Gera uma imagem a partir de uma descrição textual e devolve a URL pública. |
| `gerar_rascunho_formulario` | Gera um rascunho estruturado de formulário a partir de um título e perguntas. |
| `gerar_relatorio` | Gera um relatório estruturado em Markdown e salva no sistema. |
| `consultar_dados_cadastrais` | Consulta os dados cadastrais pessoais do usuário (documentos, contato, família, formação, carreira, banco, plano de saúde). |
| `confirmar_acao` | Executa uma confirmação MCP persistida (usada internamente por fluxos de prévia/confirmação de outras ferramentas), uma única vez. |

---

*Relatório gerado a partir da lista de ferramentas efetivamente carregadas do servidor MCP `Sistema_Hermes` nesta sessão.*
