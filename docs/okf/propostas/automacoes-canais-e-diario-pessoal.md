---
type: proposta
title: Hermes como ponto focal — automações por canal, ingestão de WhatsApp e diário pessoal
description: Análise de viabilidade e plano de implementação para três eixos — generalizar o padrão de sugestão-confirmação (validado no vínculo e-mail↔ação) para os demais canais, ingerir mensagens do WhatsApp como conhecimento, e gerar um diário pessoal diário em primeira pessoa que alimente uma inteligência de personalidade.
tags: [hermes, okf, proposta, whatsapp, telegram, sipac, calendar, diario, personalidade, automacao]
timestamp: 2026-08-08T18:00:00-03:00
---

# Hermes como ponto focal — automações por canal, ingestão de WhatsApp e diário pessoal

Três eixos pedidos pelo usuário, na sequência: (1) novas automações a partir dos canais de comunicação, no espírito do vínculo e-mail↔ação recém-implementado; (2) ingestão das mensagens de WhatsApp como conhecimento do Hermes; (3) um diário pessoal gerado a partir de todas as interações, escrito em primeira pessoa ("como se fosse eu escrevendo"), que sirva de base para o Hermes entender a personalidade do usuário.

**Veredito geral: os três são viáveis, e se encaixam.** O padrão validado no e-mail (sinal → análise IA → sugestão persistida → confirmação no Telegram/web → efeito no sistema) generaliza para os demais canais. O WhatsApp já tem metade da infraestrutura pronta — e a outra metade documentada mas nunca construída. E toda a matéria-prima do diário pessoal já é registrada hoje, espalhada em ~10 coleções; falta só o agregador e o redator.

---

## 0. O que a investigação revelou (estado real do sistema)

### Inventário de canais de entrada

| Canal | Mecanismo | Processamento IA hoje | Situação |
|---|---|---|---|
| **E-mail (Gmail)** | Polling 30 min (`run_full_sync`) | Pix (regex), boletos (Gemini), **vínculo e-mail↔ação** (recém-mergeado) | ✅ Completo |
| **Telegram** | Webhook → `telegram_inbound` → copiloto | Chat completo, check-ins de saúde, cartões de confirmação | ✅ É o canal conversacional e a superfície de confirmação |
| **WhatsApp (entrada)** | Worker local `whatsapp-web.js` → `whatsapp_messages` | **Nenhum — coleção write-only, ninguém lê** | ⚠️ Meio construído |
| **WhatsApp (saída)** | `whatsapp_outbox` | — | 🐛 Dois despachantes em corrida (ver §2.1) |
| **Google Calendar** | Sync 30 min → `google_calendar_events` | Nenhum (só sync reverso de horários) | ✅ Dados fluem, sem inteligência |
| **SIPAC** | Scraper Node a cada 2h → `sipac_processos` | Nenhum (diff determinístico → notificação) | ✅ Funciona, não toca as ações |
| **Monitor de Páginas** | Scheduler 30 min → `paginas_monitoradas` | Gemini avalia se a mudança avança o `objetivo` | ✅ Já usa IA, não toca as ações |
| **Voz (bridge)** | Gemini Live (telefone/navegador) | Tool-calling completo | ✅ Transcritos caem em `sessoes_copiloto` só no canal navegador |
| **Acervo Global (Drive)** | Scheduler 15 min | Vetorização RAG | ✅ Completo |

### Achados críticos

1. **`whatsapp_messages` é um depósito morto.** O worker (`services/whatsapp-capture/index.js`) grava toda mensagem *recebida* (nunca as enviadas — usa `message` e não `message_create`), mas **nenhuma Cloud Function, trigger ou tela lê a coleção**. O "Assistente WhatsApp" descrito em `docs/okf/integracoes/whatsapp.md` (busca com Gemini, tool `search_whatsapp_messages`, `WhatsAppAssistantTool.tsx`) **nunca foi construído** — existem apenas helpers órfãos em `security_portals.py:121-213` que referenciam campos que o worker nem grava (`chat_name`, `media.url`).
2. **O worker de captura tem defeitos estruturais**: não grava a identidade do chat/grupo (impossível saber de qual conversa veio uma mensagem de grupo); o ID do documento embute o relógio de ingestão (`Timestamp.now() + '_' + wa_id`), então qualquer redelivery duplica a mensagem; mídia é baixada e descartada; áudios ficam com `transcription_text: null` para sempre; sem reconexão/alerta ao cair.
3. **Corrida no envio**: `dispatch_scheduled_whatsapp_messages` (CF, a cada 1 min, envia card no Telegram com link `wa.me` e marca `notified`) e o cron do worker Node (envia de verdade via `client.sendMessage`) disputam os mesmos docs `pending` — quem chega primeiro rouba o documento do outro.
4. **Não existe nenhum resumo diário pessoal.** O que há: briefing matinal templado (05:00, sem LLM), resumo da virada do dia (00:00, contadores), relatório de custo Gemini (20:30). Nada agrega o dia vivido.
5. **O "perfil de IA" atual não aprende personalidade.** `usuarios/{uid}.ai_profile.historico_deduzido` é literalmente as últimas 10 perguntas do usuário truncadas em 180 chars (`_save_user_profile_signal`, `main.py:5655`). Mas é lido por **três consumidores** (copiloto web, Godmode, voice bridge) — ou seja, qualquer perfil real gravado ali se propaga para todas as superfícies de uma vez.
6. **A matéria-prima do diário já existe, por dia**: `acompanhamento[]` das tarefas (com timestamps), `data_conclusao`, `health_exercise_logs/{YYYY-MM-DD}` (exercícios, dor, sono, caminhadas), `health_weights`, `finance_transactions`, `google_calendar_events`, `sessoes_copiloto/*/mensagens` (todo o histórico conversacional, sem TTL), `interacoes_pessoas`, `notificacoes` e o feedback 👍/👎 de `scheduled_notifications` (o único sinal explícito de preferência que o usuário já dá).
7. **Lacuna de atribuição de canal**: só os turnos do Telegram gravam `source` nas mensagens de `sessoes_copiloto`; web, drawer e voz não gravam nada — vale corrigir (é barato) para o diário saber por onde cada interação aconteceu.

---

## 1. Eixo 1 — Generalizar o padrão "sinal → sugestão → confirmação" para os demais canais

### 1.1 A tese

O vínculo e-mail↔ação criou quatro peças reutilizáveis: (a) análise IA com elenco compacto de ações candidatas; (b) doc de sugestão auditável com dedupe estrutural; (c) cartão Telegram com botões e callback dedicado; (d) `apply_suggestion` transacional que escreve no diário de bordo. **Nada nisso é específico de e-mail.** A proposta é extrair um módulo comum e plugar novos produtores de sinal.

### 1.2 Refatoração: `functions/action_link_core.py`

- Generalizar a coleção: `email_action_suggestions` ganha um campo `canal` (`email` | `whatsapp` | `sipac` | `calendar` | `pagina`) — docs existentes sem o campo são tratados como `email` (migração zero). Renomear a coleção não vale o custo; documentar que o nome é histórico. ID do doc continua sendo o ID natural do sinal no canal (dedupe estrutural): mensagem Gmail, mensagem WhatsApp, `{processo}_{snapshot_hash}`, `{calendar_id}__{event_id}`.
- `apply_suggestion` transacional, o ramo `emlink:` do callback e o painel web `EmailLinkSuggestionsPanel` passam a ser agnósticos de canal (o cartão e a nota de diário ganham um ícone/prefixo por canal). O envelope rico de diário ganha o tipo genérico já existente `EMAIL` mantido para e-mail e um tipo `SIGNAL` (ou reusar `LINK`) para os demais — decisão de detalhe na implementação.

### 1.3 Novos produtores, em ordem de custo-benefício

**a) SIPAC↔ação (alta precisão, sem LLM no matching) — o melhor custo-benefício do sistema.**
`tarefas.processo_sei` já existe e `sipac_processos` já detecta mudanças com `snapshot_hash` + resumo determinístico (`buildSipacChangeSummary`). Hoje isso vira só uma notificação genérica. Proposta: quando `scheduledSipacSync` detectar mudança, procurar ações ativas com o mesmo `processo_sei` — **match determinístico por chave, sem IA** — e propor via cartão: "Processo X movimentou (nova unidade / novo documento). Registrar no diário da ação Y? Reativar?". Opcional: uma chamada flash-lite só para redigir a nota (o matching não depende dela).

**b) WhatsApp↔ação (mesmo desenho do e-mail).**
Depende da Fase 0 do Eixo 2 (worker corrigido + triagem). Mensagens triadas como "relevantes" passam pelo mesmo analisador do e-mail (elenco de ações candidatas → JSON com task_id/confiança/nota). Diferenças: a unidade de análise é uma **janela de conversa** (as mensagens de um chat desde a última passada), não uma mensagem isolada; e o limiar deve começar mais alto (conversa é mais ruidosa que e-mail).

**c) Calendar → diário de bordo (fechamento de reunião).**
Sinal: evento com fim nos últimos N minutos cujo título casa com uma ação (via matching lexical `busca_grafo`, que já existe) ou vinculado por `tarefas.google_calendar_id` (chave direta). Cartão: "A reunião 'X' terminou. Registrar resultado no diário da ação Y?" — com a opção de responder por texto/áudio no Telegram (o `lock:` de contexto já existe para isso). É o empurrão que transforma reunião em registro.

**d) Monitor de Páginas → diário de bordo.**
O monitor já tem IA e já tem um campo `objetivo`. Basta adicionar um campo opcional `task_id` ao doc de `paginas_monitoradas` (UI: seletor de ação no `MonitorPaginasTool`) e, quando `avanca_objetivo=true`, rotear pelo pipeline de sugestão em vez de mandar Telegram avulso.

**O que NÃO fazer**: automação a partir do Telegram (ele é a superfície de comando/confirmação, não uma fonte a ser garimpada) e ingestão de RSS/notícias (não existe hoje e nenhuma dessas dores pede isso — evitar escopo novo).

---

## 2. Eixo 2 — Ingestão de WhatsApp como conhecimento

### 2.1 Fase 0 — consertar a fundação (pré-requisito de tudo)

No worker `services/whatsapp-capture/index.js`:
1. **ID idempotente**: doc ID = `{chat_id}_{wa_message_id}` (remover o timestamp de ingestão do ID). Elimina duplicatas em redelivery/restart.
2. **Identidade do chat**: gravar `chat_id`, `chat_name`, `is_group`, `author_name` (autor ≠ chat em grupos). Sem isso não há filtro por conversa nem digest por contato.
3. **Mensagens enviadas**: escutar também `message_create` (com flag `from_me: true`) — uma conversa só faz sentido com os dois lados.
4. **Allowlist de chats** (privacidade, decisão de produto): `system/settings.whatsapp_ingest.chats_allowlist` — capturar (ou ao menos *processar*) apenas conversas explicitamente habilitadas. Capturar tudo de todos os grupos é ruído, custo e exposição desnecessária.
5. **Transcrição de áudio**: no backend (não no worker), job que pega mensagens `ptt/audio` sem transcrição — a infraestrutura Groq Whisper + fallback Gemini **já existe** no pipeline de transcrição do Telegram; reusar. (Exige o worker passar a subir a mídia para o Storage em vez de descartá-la — mudança pequena, o download já acontece.)
6. **Resiliência**: reconexão automática + alerta no Telegram quando a sessão cair (hoje cai silenciosamente e fica zumbi).
7. **Corrida do outbox**: definir um dono. Recomendação: flag `system/settings.whatsapp_auto_send_enabled` — quando `true` (worker rodando), a CF `dispatch_scheduled_whatsapp_messages` ignora a fila e o worker envia de verdade; quando `false`, vale o comportamento atual (card no Telegram com link `wa.me`). O worker pode manter um heartbeat (`system/whatsapp_worker.last_seen`) para a CF decidir sozinha.

Limitações a aceitar e documentar: o worker roda na máquina local (whatsapp-web.js não é implantável em Cloud Functions), exige re-pareamento por QR ocasionalmente, e é uma automação não-oficial sujeita a quebras — o desenho deve degradar graciosamente (tudo continua funcionando sem WhatsApp quando o worker está fora).

### 2.2 Fase 1 — triagem e roteamento

Job agendado (a cada 15-30 min, ou pendurado no `run_full_sync`), com cursor próprio (`system/whatsapp_ingest.last_processed_at`):
1. Ler mensagens novas dos chats da allowlist; agrupar por chat em **janelas de conversa**.
2. Pré-filtro barato sem IA: ignorar janelas só-mídia, muito curtas, ou de chats mudos.
3. Uma chamada flash-lite por janela: `{relevancia: acao|financeiro|conhecimento|pessoal|ruido, resumo, task_id?, confianca}` — com o elenco de ações candidatas do Eixo 1 no prompt.
4. Roteamento: `acao` → pipeline de sugestão (cartão de confirmação, §1.3b); `financeiro` → cartão de confirmação financeiro que já existe no Telegram; `conhecimento`/`pessoal` → digest diário (Fase 2). Tudo auditado na coleção de sugestões com `canal: whatsapp`.

### 2.3 Fase 2 — conhecimento consultável

1. **Digest diário por chat**: 1 doc `whatsapp_digests/{YYYY-MM-DD}_{chat_id}` com resumo gerado (`resumo`, `topicos[]`, `pendencias[]`, `pessoas[]`) + `embedding` (Vector 768, mesmo padrão do resto). Indexar o **digest**, não mensagem a mensagem — mensagens cruas são ruidosas demais para RAG e caras demais para embeddar individualmente.
2. **Registro por pessoa**: para contatos que existem em `perfil_pessoas`, gravar `interacoes_pessoas` com novo `tipo: 'whatsapp'` — enriquece o `generate_contact_summary` que já lê essa coleção.
3. **Tool do copiloto** `buscar_conversas_whatsapp(query, periodo?)`: busca vetorial nos digests + leitura das mensagens cruas do trecho encontrado. Registrar no `registry.py` (é o "Assistente WhatsApp" que a documentação promete, construído sobre dados que agora existem). Atualizar `whatsapp.md` para refletir a realidade.

---

## 3. Eixo 3 — Diário pessoal e inteligência de personalidade

### 3.1 O produto

Um registro por dia, escrito **em primeira pessoa, na voz do usuário** — não um relatório frio ("3 tarefas concluídas"), mas um diário ("Hoje finalmente destravei o processo da CLC que estava me incomodando desde terça; a caminhada ficou pela metade porque a reunião atrasou..."). Gerado à noite, entregue no Telegram para leitura/ajuste, navegável no app, e vetorizado para consulta retrospectiva.

### 3.2 Fontes (todas já existem)

Para o dia D: entradas de `acompanhamento[]` datadas em D (varrendo `tarefas` com `data_atualizacao >= D`); tarefas concluídas (`data_conclusao` em D) e criadas em D; `health_exercise_logs/{D}` (exercícios, caminhadas, dor, sono); peso do dia; `finance_transactions`/`income_entries` de D; `google_calendar_events` de D; mensagens de `sessoes_copiloto` com `timestamp` em D (sessões via índice `userId+lastMessageAt`); `interacoes_pessoas` de D; feedback dado em `scheduled_notifications`; e, quando o Eixo 2 existir, os `whatsapp_digests` de D. Aproveitar para a correção barata: gravar `source` nos turnos de web/drawer/voz (hoje só Telegram grava), para o diário poder dizer *por onde* o dia aconteceu.

### 3.3 Geração

Nova função agendada `gerar_diario_pessoal` (21:30 BRT, configurável):
1. Coletor determinístico monta o "material do dia" estruturado (sem IA).
2. Se o dia estiver vazio (viagem, fim de semana off), gravar doc mínimo `sem_material: true` e não chamar o LLM.
3. Uma chamada de modelo **balanceado/frontier** (aqui vale pagar por qualidade de escrita — é 1 chamada/dia) com: material do dia + persona (`system/copilot_soul` + `ai_profile`) + os 3 diários anteriores (continuidade narrativa e de voz) + instruções de tom: escrever *como* o usuário, não *sobre* ele; não inventar sentimentos — quando inferir estado emocional a partir dos dados (ex.: dia com dor lombar alta + muitas reuniões), marcar como impressão, não como fato.
4. Gravar `diario_pessoal/{YYYY-MM-DD}`: `{texto, destaques[], fontes: {acoes: n, saude: bool, financeiro: n, conversas: n, ...}, embedding (Vector 768), gerado_em, modelo, editado: false}`.
5. Entregar no Telegram (texto + botões "✍️ Ajustar" / "👍 Ok"). "Ajustar" tranca o contexto da sessão no diário do dia e a resposta livre do usuário vira revisão (o mecanismo de `lock:` de contexto já existe). **Edições do usuário são o sinal de personalidade mais valioso do sistema** — guardar o diff (`texto_original`).

### 3.4 Consumo

- **View no app** (fase 2 do eixo): linha do tempo dos diários, com edição.
- **Tool do copiloto** `consultar_diario_pessoal(query|data)`: busca vetorial nos diários — habilita "como eu estava me sentindo em março?", "quando foi que resolvi aquilo da bolsa?".
- **Contexto**: o diário de ontem entra no briefing matinal (05:00) — continuidade entre dias.

### 3.5 Inteligência de personalidade

Job semanal `consolidar_personalidade` (domingo à noite):
1. Lê os diários da semana + diffs de edição + feedback 👍/👎 + estatísticas de interação (horários ativos, canais, temas recorrentes).
2. Uma chamada de modelo forte produz/atualiza `usuarios/{uid}.ai_profile.personalidade`: `{tracos[], estilo_comunicacao, valores_recorrentes, rotinas, gatilhos_de_estresse, fontes_de_energia, resumo_narrativo}` — com versionamento (`personalidade_historico[]`, últimas N versões) para o perfil poder evoluir sem perder o rastro.
3. **Propagação automática**: como copiloto web, Godmode e voice bridge já leem `ai_profile`, todos passam a conhecer a personalidade sem nenhuma mudança adicional — este é o motivo de gravar ali e não numa coleção nova.
4. O `historico_deduzido` atual (log de 10 prompts) continua como está — vira insumo do consolidador, não o perfil.

### 3.6 Guarda-corpos

Privacidade: `diario_pessoal` já nasce protegido pelas rules (`internalUser`); não espelhar o texto integral em `notificacoes`. Custo: ~32 chamadas/mês (1/dia + 4 semanais) de modelo médio/forte — poucos reais/mês, tudo via `generate_content_logged` (features `personal_diary.generate` e `personality.consolidate`). Tom: nunca prescritivo ("você deveria...") — diário registra, não aconselha; o canal de conselhos já existe (planejador de notificações). Flag `system/settings.personal_diary.enabled`.

---

## 4. Ordem de implementação recomendada

| # | Entrega | Eixo | Esforço | Por quê nesta ordem |
|---|---|---|---|---|
| 1 | **Diário pessoal MVP** (coletor + gerador + Telegram + coleção) | 3 | M | Maior valor pessoal imediato; zero infraestrutura nova; independe do WhatsApp |
| 2 | `source` nos turnos web/drawer/voz + refator `action_link_core` | 1/3 | P | Correções baratas que os demais itens consomem |
| 3 | **SIPAC↔ação** | 1 | P | Match determinístico por `processo_sei`, sem custo de IA no matching — quick win |
| 4 | **WhatsApp Fase 0** (worker: ID, chat, from_me, allowlist, resiliência, outbox) | 2 | M | Fundação; sem isso nada de WhatsApp é confiável |
| 5 | **WhatsApp Fase 1** (triagem → sugestões) | 2 | M | Liga o canal ao padrão de confirmação |
| 6 | **Calendar → diário de bordo** (fechamento de reunião) | 1 | P | Reusa o pipeline já generalizado |
| 7 | **WhatsApp Fase 2** (digests + tool de busca) + diário passa a incluir WhatsApp | 2/3 | M | Conhecimento consultável |
| 8 | **Consolidador de personalidade** (semanal) | 3 | M | Precisa de algumas semanas de diários acumulados para valer |
| 9 | Monitor de Páginas → diário de bordo; view do diário no app | 1/3 | P | Complementos |

(P = pequeno, M = médio. Cada entrega é independente e pode ser uma PR própria.)

## 5. Riscos e pontos de atenção

| Risco | Mitigação |
|---|---|
| WhatsApp: worker local cair e ninguém notar | Heartbeat + alerta Telegram; sistema degrada graciosamente sem o canal |
| WhatsApp: banimento/quebra do whatsapp-web.js | Allowlist reduz volume; aceitar como risco documentado; nada crítico depende do canal |
| Privacidade: capturar conversas de terceiros | Allowlist explícita por chat; processar só o habilitado; rules já restringem leitura ao dono |
| Diário "inventar" emoções ou soar falso | Persona + diários anteriores no prompt; inferências marcadas como impressão; edição fácil no Telegram; diffs alimentam a calibração |
| Excesso de cartões de confirmação (fadiga) | Teto global de sugestões por passada **compartilhado entre canais** no `action_link_core` (não por canal); prioridade: SIPAC > e-mail > WhatsApp > calendar |
| Custo de LLM crescer com canais | Tudo via `generate_content_logged` com feature por canal; tetos por passada; digests em vez de mensagem-a-mensagem |
| Perfil de personalidade enviesar o copiloto | Versionamento do perfil; seção separada no prompt ("impressões, não fatos"); revisável na UI |
