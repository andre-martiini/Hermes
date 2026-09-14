# Modo Secretário — Relatório Inicial da Ideia

**Data:** 05/09/2026
**Origem:** discussão entre André e Claude (Cowork), a partir de uma ideia do André
**Status:** **aprovado para desenvolvimento imediato** — próxima etapa a ser trabalhada pelo dev, via protocolo `docs/dev-sync.md`. (Deixa de ser "rascunho de conceito"; ver seção 8 para a análise de viabilidade e as decisões de MVP tomadas antes de abrir a etapa.)

## 1. Contexto

O Hermes já lê e envia mensagens de WhatsApp em nome do André, mas hoje toda mensagem enviada passa por confirmação manual dele antes de sair (fluxo `schedule_whatsapp_message` → `confirmar_acao`).

A ideia surgiu de uma necessidade concreta: quando o André está em reunião (ou indisponível por qualquer motivo), ele gostaria que o Hermes atendesse quem escreve no WhatsApp como um secretário atenderia — não apenas com uma mensagem padrão de "estou ocupado", mas entendendo o assunto, fazendo perguntas de esclarecimento e só o interrompendo quando necessário.

Isso se encaixa diretamente na Fase 3 do plano Hermes→Jarvis ("Autonomia graduada"), que já está em andamento — em especial no PR `outbox-tipo-e-edicao` (#167, aguardando merge) e no mecanismo `avaliar_interrupcao_atencao` da Fase 2.

## 2. Objetivo

Permitir que o Hermes converse com terceiros no WhatsApp em nome do André durante períodos de indisponibilidade, coletando informação e resolvendo o que for de baixo risco sozinho, sem nunca comprometê-lo com uma decisão, uma confirmação ou uma promessa que só ele pode dar.

## 3. Regras de comportamento

### 3.1 Identidade sempre visível

Toda mensagem enviada pelo Hermes nesse modo começa com o identificador em negrito, seguido de dois-pontos:

```
**Hermes Bot:** [mensagem]
```

Isso se repete em **todas** as mensagens da conversa, não só na primeira — o objetivo é que a pessoa do outro lado nunca esqueça que está falando com o assistente, mesmo numa troca de várias mensagens.

### 3.2 Pedidos de agenda/compromisso

Quando alguém pede para marcar algo em um dia ou horário específico, o Hermes consulta a agenda real do André:

- **Se ele estiver ocupado** naquele horário: o Hermes pode informar isso diretamente (ex.: "nesse dia ele estará em [compromisso] das Xh às Yh"). É informação factual, sem risco de comprometê-lo.
- **Se ele estiver livre**: o Hermes **não confirma disponibilidade nem fecha o compromisso**. Apenas informa que vai repassar o recado, e o André decide e confirma pessoalmente depois.

Essa assimetria é o núcleo da segurança do modelo: negar/informar é seguro, confirmar/aceitar não é — porque comprometeria a agenda dele sem seu conhecimento.

### 3.3 Contato prioritário pré-avisado

Quando o André sabe de antemão que está esperando resposta de alguém específico sobre um assunto específico, ele avisa o Hermes com antecedência: quem é a pessoa e o que precisa saber da resposta dela.

Se esse contato escrever durante o período de indisponibilidade, o Hermes não trata a mensagem como recado genérico: conduz a conversa buscando ativamente as informações combinadas, e ao final apresenta ao André um resumo do que a pessoa trouxe.

## 4. Fronteira de autonomia: entender vs. decidir

| Ação | Autonomia | Justificativa |
|---|---|---|
| Perguntar para entender melhor o assunto | Autônoma | Não compromete o André, só reúne contexto |
| Informar que ele está ocupado/indisponível | Autônoma | Fato verificável na agenda, sem risco |
| Anotar recado e resumir para o André | Autônoma | É o objetivo central do modo |
| Confirmar disponibilidade/fechar compromisso | Fica com o André | Compromete a agenda dele sem ele saber |
| Tomar posição, prometer prazo, decidir algo em nome dele | Fica com o André | Risco de mal-entendido ou compromisso indevido |

Essa fronteira segue o mesmo princípio da "autonomia graduada" já adotado no Hermes: começar restrito ao que é seguro, e promover para autônomo conforme a métrica de acerto justificar.

## 5. O que exige mudança de código (não é só uma skill)

Uma skill do Claude sozinha não é suficiente, porque não dá presença contínua no WhatsApp nem guarda estado entre mensagens de sessões diferentes. É necessário trabalho no backend do próprio Hermes (Cloud Functions / webhook):

- Ativação/desativação do modo (toggle manual, ou vinculado a eventos da agenda).
- Estado de conversa por contato — saber que já está "no meio" de uma investigação com aquela pessoa específica.
- Aplicação do prefixo `**Hermes Bot:**` em toda mensagem de saída do outbox nesse modo.
- Integração com a consulta de agenda no momento de gerar a resposta.
- Uso do `avaliar_interrupcao_atencao` (já existente, Fase 2) como critério de quando escalar para o André em vez de continuar sozinho.

## 6. O que pode ser resolvido com uma skill/prompt

A camada de raciocínio — como o Hermes já delega ~90% das decisões ao Claude via MCP — pode ser justamente as regras da seção 3 e a tabela da seção 4, entregues como instrução ao Claude no momento em que o Hermes o aciona para decidir como responder. Ou seja: a skill é o "cérebro" da decisão; o código é o que faz essa decisão entrar e sair do WhatsApp na hora certa.

## 7. Pontos em aberto da rodada de ideia original

- Como o modo é ativado: comando explícito do André, ou detecção automática por evento de agenda (reunião marcada)?
- Escopo de contatos: todas as conversas monitoradas, ou uma lista restrita para começar?
- O que fazer quando a pessoa insiste em obter uma decisão imediata e o Hermes não pode dar?
- Definir um MVP mínimo (por exemplo: só a assinatura + a regra de agenda) antes de partir para a investigação conversacional completa da seção 3.3.

## 8. Análise de viabilidade e decisões de MVP (Claude, 05/09/2026)

Antes de abrir a etapa de desenvolvimento, levantei diretamente no código (`functions/`) o que já existe e o que falta, para responder aos pontos em aberto da seção 7 com uma proposta concreta em vez de deixá-los todos para o dev decidir do zero.

### 8.1 O que já existe e pode ser reaproveitado

- **Outbox com janela de cancelamento** (`functions/outbox_aprovacao.py`, mecanismo de `tipos_promovidos`/`aguardando_janela`): já é autonomia graduada com veto humano garantido — é o caminho certo para o envio das respostas do modo secretário, em vez de inventar um autoenvio sem veto.
- **Consulta de agenda multi-calendário** (`functions/hermes_calendar_tools.py`, `consultar_agenda`/`encontrar_slot_livre`): barata, sem LLM, já cobre a regra da seção 3.2 (checar livre/ocupado num horário).
- **`avaliar_interrupcao_atencao`** (`functions/atencao.py:800-899`) + `scheduled_notifications`/Telegram: já é o canal de escalação para o André. Dá para reaproveitar com uma `origem` nova em vez de criar um canal paralelo.
- **Precedente de LLM acionado pelo backend sem sessão interativa**: `functions/ai_notification_planner.py` já invoca um LLM fora de uma sessão MCP (o planejador proativo das 6h30). Isso resolve a maior dúvida técnica — como o Hermes decide o que responder a uma mensagem recebida sem um humano com sessão aberta — sem precisar inventar infraestrutura nova do zero.

### 8.2 O que não existe e precisa ser criado

- Não existe hoje nenhum gatilho que chame um LLM em reação a uma mensagem recebida no WhatsApp — os triggers atuais em `functions/atencao_whatsapp.py` são detectores determinísticos (regex de promessa, duração de áudio), não uma decisão de resposta.
- Não existe estado de conversa por contato (nada como "investigação em andamento com este chat entre mensagens"). Precisa de uma coleção nova.
- Não existe flag nem allowlist específica do modo secretário em `system/settings` — dá para seguir o mesmo padrão de `whatsapp_ingest.chats_allowlist`, mas é campo novo.
- Não existe detecção automática de "André entrou em reunião" (não há webhook de calendário hoje) — ativação por enquanto só pode ser manual.

### 8.3 Decisões de MVP para os pontos em aberto da seção 7

1. **Ativação:** toggle manual e global (`system/settings.whatsapp_secretario.enabled`, padrão `false`). Detecção automática por evento de agenda fica para uma etapa futura — não há infraestrutura de webhook de calendário hoje.
2. **Escopo de contatos:** allowlist explícita (`system/settings.whatsapp_secretario.chats_allowlist`), mesmo padrão do `whatsapp_ingest` — não abre para todas as conversas de saída de uma vez.
3. **Insistência da pessoa:** depois de 2 trocas sem resolver (número sugerido, ajustável), o Hermes para de investigar e informa que vai repassar o recado — nunca entra em loop tentando "resolver" sozinho.
4. **MVP mínimo (primeira PR):** seção 3.1 (assinatura) + seção 3.2 (regra de agenda) + escalação quando a pessoa tenta forçar uma decisão/confirmação. A investigação conversacional completa da seção 3.3 (e o contato prioritário pré-avisado) fica para uma segunda PR, depois que a primeira estiver validada em produção.

### 8.4 Guardrail não negociável

O envio das respostas do modo secretário passa pelo mesmo mecanismo de janela de cancelamento (`aguardando_janela`/`tipos_promovidos`) que já existe no outbox — nunca um autoenvio sem veto humano. E, seguindo o mesmo cuidado já adotado nos detectores de financeiro/saúde nesta fase do projeto, o modo secretário nunca deve mencionar, resumir ou responder com qualquer dado financeiro ou de saúde do André, não importa o que a pessoa pergunte — isso é sempre escalado para o André, nunca respondido pelo bot.
