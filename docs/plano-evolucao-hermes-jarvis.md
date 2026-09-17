# Hermes → Jarvis: plano de evolução para proatividade e autonomia

**Data:** 03/09/2026 · **Base:** repositório `gestao-Hermes` (branch `main`, commit `77de164`) e uso real do Hermes via Claude nesta sessão.

---

## 1. Tese

O Hermes já tem o que a maioria dos "assistentes" não tem: sensores (WhatsApp capturado, Gmail, Calendar, SIPAC, portais), memória (memória global, POPs, grafo de conhecimento, diário, perfil deduzido), efetores (58+ tools MCP com gating de confirmação) e alguns primeiros reflexos proativos (resumo matinal determinístico, planejador de notificações com Claude, linker de e-mails, respostas pendentes).

O que falta para ele virar um Jarvis não é mais uma tela nem mais um modelo. É inverter o sentido da relação: hoje o André aciona o Claude, o Claude aciona o Hermes. Amanhã o Hermes percebe, decide que algo merece atenção, acorda o Claude para raciocinar e executar, e volta ao André só com a decisão que só ele pode tomar — de preferência resolvida com um toque.

A documentação do próprio repo já cravou o princípio certo: **um cérebro, um catálogo, N canais**. Este plano assume a consequência: como ~90% do uso hoje passa pelo Claude via MCP, **o Claude é o cérebro** e o Hermes vira o sistema nervoso — percepção, memória, mãos e freios. Nada aqui cria um quinto orquestrador nem um segundo catálogo.

## 2. Os cinco traços de um Jarvis, traduzidos para o Hermes

| Traço | O que significa aqui | O que já existe | O que falta |
|---|---|---|---|
| Percebe continuamente | Um lugar só onde tudo que pede atenção aparece normalizado | Sinais espalhados: `scheduled_notifications`, respostas pendentes, `elevacoes_sugeridas`, `email_action_suggestions`, `notificacoes`, degradação | **Fila de Atenção** unificada + novos detectores |
| Conhece o André | Modelo do mundo compartilhado entre Hermes e Claude | Memória global, POPs, perfil deduzido, `mcp_signals`, `hermes://voice-context` | Contexto por ação para agentes, modelo por pessoa, memória do Claude sincronizada |
| Fala primeiro | Iniciativa com critério e orçamento de interrupção | Planner diário (teto de 3/dia, feedback 👍/👎), resumo matinal | Motor **event-driven** + **sessões agendadas do Claude** com tools completas |
| Faz, com freios | Autonomia graduada; humano no circuito só onde importa | Gating de `schedule_whatsapp_message`; `preparar_*`/`confirmar_*` | **Outbox com aprovação em um toque** + níveis de autonomia por tipo de ação |
| Melhora sozinho | Aprende do próprio uso | Feedback de notificações, `registrar_correcao_procedimento`, `mcp_audit_log`, motor de simulação | Métricas de proatividade, retro semanal do agente, auto-derivação de POPs |

## 3. Eixos de evolução

### Eixo 1 — Percepção: a Fila de Atenção

Criar a coleção `atencao` como substrato único de proatividade. Cada item tem a mesma forma, venha de onde vier: `origem` (whatsapp, email, agenda, acao, repo, financeiro, saude), `tipo`, `prioridade`, `acao_vinculada`, `prazo`, `evidencia` (ids das mensagens/e-mails/commits que sustentam o item), `sugestao` (o que o Hermes acha que deve ser feito) e `estado` (aberto, delegado_ao_agente, aguardando_andre, resolvido, descartado).

Os detectores existentes passam a escrever aqui em vez de cada um ter sua fila. Novos detectores, todos determinísticos e baratos (trigger Firestore ou cron, sem LLM na detecção):

- **Promessa sem retorno.** Mensagem do André com padrão de compromisso ("vou ver e te retorno", "te aviso", "já estou vendo") sem mensagem posterior dele naquela conversa em X horas. Hoje (03/09) aconteceu duas vezes: "já estou vendo, ok?" para o Guilherme às 14:24 e o retorno só saiu perto das 15h porque o André lembrou.
- **Aguardando terceiro vencido.** Etapa do `plano_acao` em `aguardando_terceiro` com `data_prevista` passada e nenhuma mensagem nova do `aguardando_de` desde então. Caso Hesley/IFTO hoje: teste marcado para ~14h, ninguém confere se aconteceu.
- **Áudio relevante chegou.** Áudio acima de N segundos, de contato vinculado a uma ação ativa → item com sugestão "consolidar". Hoje a consolidação do áudio do Serviço Social de Piúma e a dos áudios do Guilherme só ocorreram porque o André pediu.
- **Evento de repositório.** Webhook do GitHub para repos que o André administra (Atlas, MEC-Sustentavel, gestao-proen, Hermes): PR mergeado/deploy → anota no diário da ação vinculada e sugere o próximo passo (hoje: "avisar Iris?" só existiu porque o André lembrou).
- **Reunião sem briefing.** Evento na agenda em 30 min com participantes conhecidos e sem item de preparação.

Tools: `obter_fila_atencao(filtro)`, `resolver_item_atencao(id, desfecho)`. `obter_estado_atual` passa a devolver os N itens mais quentes — uma sessão nova do Claude sabe em uma chamada o que importa agora.

### Eixo 2 — Iniciativa: o Hermes acorda o Claude

Dois motores, com papéis distintos e complementares:

**Reflexos internos (Cloud Functions + Claude API, já existe o padrão em `ai_notification_planner.py` e `godmode.py`).** Rápidos, baratos, rodam dentro do Firebase com o executor interno `hermes_tools.py`. Evoluir o planner de "uma rodada às 6h30" para **event-driven**: `on_atencao_created` com prioridade alta decide na hora entre notificar, agrupar para o próximo ciclo ou delegar. O teto diário vira um **orçamento de interrupção** com horário de silêncio e canal por prioridade. Incluir finanças e saúde, hoje fora do escopo por falta de tools calibradas — as tools já existem no catálogo MCP (`consultar_financas_v2`, `consultar_saude`, `consultar_fatura_cartao`).

**Sessões agendadas do Claude (Cowork scheduled tasks).** Este é o maior ganho de alavancagem, e é a razão de o plano se apoiar na conexão Claude↔Hermes: uma sessão agendada acorda com o catálogo completo do Hermes **mais** Gmail, Calendar, Drive, memória do Claude, Chrome e o computador do André quando linkado. Nenhum código novo no Hermes é necessário para começar — só as tools que a sessão vai chamar. Rotinas propostas:

| Rotina | Horário | O que faz | Sai para o André |
|---|---|---|---|
| Briefing executivo | 06:45 (dias úteis) | `obter_estado_atual` + fila de atenção + Gmail + Calendar; prepara decisões, não perguntas | Uma mensagem com ≤3 decisões, cada uma respondível com um toque ou uma palavra |
| Varredura de follow-ups | 12:30 e 17:30 | Promessas sem retorno, aguardando_terceiro vencido, respostas pendentes; redige rascunhos no outbox | Lista de rascunhos prontos para aprovar |
| Executor de pedidos | a cada 2h | Lê `agent_requests` (ver abaixo) e executa: consolidar áudio, montar handoff de ação, conferir deploy, vincular e-mails | Só o que precisar de decisão |
| Revisão semanal | sexta 17:00 | Higiene do `plano_acao`, degradações, metas estratégicas paradas, proposta de reagendamento em lote (`preparar_reagendamento_em_lote`) | Um card de aprovação para o lote |
| Retro do agente | domingo 21:00 | Lê `mcp_audit_log` e feedback da semana; propõe ajustes de POP e de prompt (Eixo 6) | Sugestões para aceitar/recusar |

**A ponte entre os dois motores: `agent_requests`.** O Hermes não consegue disparar uma sessão do Cowork diretamente; o que ele pode fazer é **enfileirar trabalho** numa coleção que a próxima sessão agendada consome. Um detector que vê um áudio relevante grava `{tipo: consolidar_audio, chat_id, mensagens, acao_id}`; a sessão das 14h executa, grava o resultado no diário da ação e resolve o item da fila. O Hermes ganha mãos (as do Claude) sem reimplementar nada. Para latência menor que 2h em casos críticos, o reflexo interno pode executar com o executor local — o mesmo trabalho, ferramentas mais restritas.

### Eixo 3 — Agência com freios: do "posso enviar?" ao "aprovar com um toque"

Hoje toda sugestão proativa vira uma conversa. A troca proposta é um **outbox**: Claude ou os reflexos internos produzem rascunhos — mensagem de WhatsApp, e-mail, alteração de plano de ação, nova ação — em `outbox/{id}` com destinatário, texto e a evidência que o motivou. O André aprova por botão inline no Telegram, por resposta curta no WhatsApp para o próprio número ("ok 3") ou por card na web. O worker de WhatsApp que já existe faz o envio.

Isso resolve três coisas de uma vez: mantém o humano no circuito exatamente onde ele é insubstituível (efeito em terceiros), reduz o custo da decisão a um toque, e elimina a fricção observada hoje em que a mensagem ao Guilherme, já aprovada em conversa, não pôde ser enviada pela sessão e teve que ser copiada à mão.

Níveis de autonomia, definidos por tipo de efeito e ajustáveis em `system/mcp_access` sem deploy:

| Nível | Exemplos | Regra |
|---|---|---|
| Autônomo | Registrar no diário; consolidar áudio; vincular e-mail/commit a ação com match determinístico; atualizar `data_prevista` de etapa com evidência; criar item na fila | Executa e informa depois (ou nem informa, se rotineiro) |
| Um toque | Mensagem a terceiro; criar ação; reagendar em lote; criar rascunho de e-mail; marcar etapa como feita sem evidência | Vai para o outbox; André aprova/edita/descarta |
| Nunca sozinho | Movimentar dinheiro; excluir; alterar objetivo estratégico | Só por pedido explícito em conversa, com prévia |

A promoção entre níveis é uma decisão do André, mas o sistema sugere (Eixo 6): "os últimos 20 rascunhos de confirmação de reunião foram aprovados sem edição — automatizar?".

### Eixo 4 — Memória e modelo do mundo compartilhados

Há duas memórias hoje: a do Hermes e a do Claude (arquivos de memória por usuário). O Hermes deve ser a **memória canônica**: o que o Claude aprende em conversa entra por `salvar_memoria_global`, e o que o Hermes sabe volta ao Claude por um resource ampliado — `hermes://contexto-agente` com persona, POPs sempre ativos, pessoas-chave, ações críticas e convenções dos repositórios. Uma sessão nova do Claude começa com o mesmo contexto que a anterior terminou.

Duas peças novas:

**`contexto_agente` por ação.** Um campo auto-mantido em cada ação crítica: o que é, quem são as pessoas, onde está o código (repo, branch, porta do dev server), últimas decisões e travas. Hoje isso é um documento de handoff escrito à mão a cada troca de agente (o da investigação do MEC-Sustentável tinha uma página). Com o campo, `obter_acao(id)` é o handoff. O reflexo que o mantém é o `on_tarefa_written` + registro de diário: cada decisão registrada atualiza o resumo.

**Modelo por pessoa.** Para cada contato relevante: como o André fala com ela (registro, saudação, formalidade — derivado das próprias mensagens do André), tempo típico de resposta, promessas em aberto nos dois sentidos, ações em que aparece. Alimenta o detector de promessas, o redator de rascunhos e o briefing ("Hesley costuma responder em 2h; está há 6h sem responder").

### Eixo 5 — Presença: estar onde o André está

Telegram continua sendo o canal de sistema (botões inline, baixo custo). Mas o André vive no WhatsApp: o worker de captura já lê tudo; passar a **enviar para o próprio número** transforma o WhatsApp em canal de notificação e aprovação, sem app novo. Voz permanece como canal fino sobre o mesmo catálogo, como a proposta vocal já definiu — nenhum cérebro paralelo. As sessões agendadas do Claude somam push no celular quando terminam com algo relevante.

### Eixo 6 — Autoaperfeiçoamento

O ciclo de feedback já existe em pedaços (👍/👎 nas notificações, `registrar_correcao_procedimento`, `elevacoes_sugeridas`, `deteccao_subproduto`). Fechar o ciclo:

- **Métricas de proatividade**, gravadas em `agent_runs` por sessão/rodada: itens da fila abertos vs. resolvidos sem o André iniciar conversa; taxa de aprovação de rascunhos sem edição; tempo entre item criado e resolvido; notificações dispensadas por tipo.
- **Retro semanal do agente**: a sessão de domingo lê essas métricas e o `mcp_audit_log`, identifica sequências repetidas de tools (candidatas a POP), sugestões sempre dispensadas (candidatas a desligar) e rascunhos sempre aprovados sem edição (candidatas a autonomia). Devolve propostas; o André aceita ou recusa.
- **Regressão de comportamento proativo** no motor de simulação existente (`functions/simulation`): cenários como "áudio de contato vinculado chega" ou "promessa sem retorno há 5h" com o desfecho esperado, para que mudanças nos detectores não silenciem o sistema sem ninguém notar — o mesmo risco que `mcp_signals.py` já documentou para o perfil.

## 4. Fundação técnica (habilitadores)

- **Conexão MCP estável.** OAuth com refresh já resolve o limite de 1h; garantir que sessões agendadas autentiquem sem intervenção.
- **Consertar `listar_conversas_whatsapp`.** O campo `ultima_atividade` veio defasado hoje (mostrava a noite anterior com mensagens novas existindo). Triagem proativa depende desse campo estar certo.
- **`obter_estado_atual` como porta única**: incluir fila de atenção, `agent_requests` pendentes e itens do outbox aguardando aprovação.
- **Custo sob controle.** Detectores sem LLM; reflexos com modelo leve; raciocínio pesado só nas sessões agendadas. Orçamento por rotina, reportado no relatório diário de custo que já existe.
- **Segurança.** `agent_requests` e outbox só do UID permitido; aprovações autenticadas (whitelist de chat_id no Telegram, número próprio no WhatsApp, Firebase Auth na web); tudo em `mcp_audit_log`.
- **Observabilidade.** `agent_runs` com resumo de cada sessão agendada: o que leu, o que enfileirou, o que enviou ao André.

## 5. Roadmap

| Fase | Janela | Entregas | Como saber que funcionou |
|---|---|---|---|
| **0 — Fundação** | Semanas 1–2 | Coleção `atencao` + 3 detectores (promessa sem retorno, aguardando_terceiro vencido, áudio relevante); tools `obter_fila_atencao`/`resolver_item_atencao`; outbox mínimo com aprovação por Telegram; duas rotinas agendadas do Claude (briefing 06:45, varredura 17:30); correção do `ultima_atividade` | O André recebe pela manhã decisões prontas, e à tarde rascunhos para aprovar, sem ter aberto conversa |
| **1 — Mãos** | Semanas 3–6 | `agent_requests` + executor a cada 2h; consolidação automática de áudios; `contexto_agente` nas ações críticas; webhook GitHub → diário da ação; envio ao próprio WhatsApp; `agent_runs` e métricas básicas | Áudios relevantes chegam já consolidados; um agente novo continua uma ação crítica só com `obter_acao` |
| **2 — Reflexos** | Semanas 7–12 | Planner event-driven com orçamento de interrupção e escopo em finanças/saúde; revisão semanal com reagendamento em lote proposto; modelo por pessoa; retro do agente; cenários de regressão no simulador | ≥50% dos itens da fila resolvidos sem o André iniciar; taxa de dispensa de notificações caindo semana a semana |
| **3 — Autonomia graduada** | A partir do mês 4 | Promoção de tipos de rascunho de "um toque" para "autônomo" com base em métricas; voz como canal fino sobre o mesmo catálogo; auto-POPs | O André aprova políticas, não mensagens |

## 6. Como o dia de hoje teria sido

13:50 — chega o áudio do Guilherme. O detector vê contato vinculado à ação MEC-Sustentável e enfileira consolidação; o reflexo interno transcreve e cria o item "Guilherme reportou 2 achados no painel" com resumo e evidência. 14:24 — "já estou vendo, ok?" vira uma promessa aberta. 14:30 — a sessão agendada lê o item, confere o repositório (a correção já estava na working tree), roda os testes e devolve ao André: "correção do dev externo confirmada, 10/10 testes; quer que eu redija o retorno?". O André diz sim; o rascunho vai ao outbox; ele toca em Enviar. 15:00 — o item Hesley (`aguardando_terceiro`, previsto 14h) está vencido sem mensagem nova: "o teste do AnyDesk aconteceu?". 11:10 — PR #39 do Atlas mergeado: o webhook anota no diário da ação do CadÚnico e coloca no outbox o rascunho para a Iris. Em nenhum momento o André precisou lembrar de algo; precisou apenas decidir.

## 7. O que este plano não propõe

Não cria um novo orquestrador nem um segundo catálogo de tools. Não substitui o Telegram. Não dá autonomia para mensagens a terceiros sem aprovação — muda o custo da aprovação, não a sua existência. Não depende de infraestrutura nova: Firestore, Cloud Functions, o worker de WhatsApp e as sessões agendadas do Claude já existem.

## 8. Critérios de sucesso (o "teste Jarvis")

1. O dia começa com decisões prontas, não com perguntas do André ao sistema.
2. Metade ou mais dos itens que pedem atenção são resolvidos sem que o André inicie uma conversa.
3. Nenhuma mensagem a terceiro sai sem aprovação — e aprovar custa um toque.
4. Qualquer agente novo, em sessão zerada, continua qualquer ação crítica só com `obter_estado_atual` e `obter_acao`.
5. O sistema propõe, toda semana, pelo menos uma melhoria em si mesmo baseada em dado — e o André só precisa aceitar ou recusar.
