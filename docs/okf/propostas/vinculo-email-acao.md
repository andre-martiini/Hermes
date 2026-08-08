---
type: proposta
title: Vínculo automático de e-mails a ações com confirmação via Telegram
description: Análise de viabilidade e plano de implementação para o Hermes investigar cada e-mail recebido, identificar relação com ações em andamento ou em stand-by e propor, via Telegram, atualizar a ação e registrar o e-mail no diário de bordo.
tags: [hermes, okf, proposta, gmail, telegram, tarefas, diario-de-bordo]
timestamp: 2026-08-08T00:00:00-03:00
---

# Vínculo automático de e-mails a ações com confirmação via Telegram

**Ideia original:** o Hermes deve investigar cada e-mail recebido e identificar se ele tem relação com alguma ação em andamento ou em stand-by. Ao identificar a relação, envia mensagem no Telegram dando a opção de atualizar a ação e registrar o e-mail no diário de bordo.

**Veredito de viabilidade: alta.** Todos os blocos de construção já existem no sistema — polling do Gmail a cada 30 min, escrita no diário de bordo via `ArrayUnion`, envio proativo no Telegram com botões inline e roteamento de callbacks. O que falta é exatamente a peça nova: um classificador que relacione e-mail ↔ ação. Nenhuma infraestrutura nova (Pub/Sub, webhook do Gmail, embeddings de tarefas) é necessária para o MVP.

## 1. O que o repositório já oferece (verificado no código)

| Bloco | Onde está | Situação |
|---|---|---|
| Ingestão de e-mails | `run_full_sync` (`functions/main.py:2302`), disparado por `scheduled_sync` (30 min) e `on_sync_request` | Polling via `messages().list()`; não há watch/push do Gmail |
| Processamento por e-mail hoje | `sync_pix_emails` (main.py:1574, só regex) e `sync_boletos_gmail` (main.py:2009, 1 chamada Gemini/e-mail) | São colheitadeiras de escopo estreito; **não existe classificador genérico de e-mails** |
| Ações com status | Coleção `tarefas`, `status: 'em andamento' | 'stand-by' | 'concluído'` (`types.ts:3`) | Atenção: o banco tem variantes (`standby`, `stand by`, `cgby`) — ver `isStandbyStatus` em `src/utils/helpers.tsx:169` |
| Diário de bordo | Campo `acompanhamento[]` (`{data, nota}`, `types.ts:13-16`), append via `firestore.ArrayUnion` — padrão canônico em `registrar_no_diario` (`main.py:9277`) | Pronto para reuso |
| Telegram proativo com botões | `_send_telegram_message_raw_with_keyboard` (`main.py:6181`); padrão "doc-ID no callback_data" usado por `ai_notification_planner.py:400-420` | Pronto para reuso; `callback_data` ≤ 64 bytes |
| Roteamento de callbacks | `_handle_telegram_callback` (`hermes_core_logic.py:1723-2235`), cadeia `if/elif` por prefixo | Basta um novo ramo `elif` |
| Gatilho de e-mail por ação (manual) | `functions/email_trigger_handler.py` + UI em `Modals.tsx` | **Código morto**: `process_email_triggers` não tem nenhum callsite — a feature existe na UI mas nunca roda |

Três achados relevantes da investigação que moldam o desenho:

1. **`process_email_triggers` nunca é chamado.** A funcionalidade de "gatilho de e-mail" configurável por ação (remetente/palavras-chave) está completa no backend e na UI, mas `run_full_sync` não a invoca. A ideia desta proposta é uma generalização dela (matching por IA em vez de regras manuais, e com confirmação humana em vez de atualização automática). A Fase 3 decide o destino desse código.
2. **O ledger de deduplicação atual é frágil.** `system/processed_emails` é um único documento com array de IDs, escrito pelos dois caminhos com tetos diferentes (1000 vs 500) e truncamento de `set` não ordenado. O novo fluxo **não deve** reusar esse ledger; cada e-mail analisado vira um documento próprio (dedupe por ID de documento).
3. **A chamada Gemini do caminho de boletos não passa pela telemetria de custo** (`generate_content_logged`). O novo fluxo deve usar a telemetria desde o dia 1.

## 2. Melhorias sobre a ideia original

A ideia é boa como está; estas melhorias a tornam mais útil e mais segura:

1. **Confirmação com três saídas, não duas.** Além de "atualizar" e "ignorar", oferecer a ação intermediária "só registrar no diário" (sem mexer em status). E quando a ação estiver em stand-by, o botão principal vira "registrar + reativar" — o e-mail chegando é frequentemente o evento pelo qual a ação estava esperando (é exatamente o caso de uso do `email_trigger` morto).
2. **Nota de diário rica, não só "e-mail recebido".** A IA já leu o e-mail; a nota proposta deve conter remetente, assunto, um resumo de 1-3 frases do que o e-mail significa **para aquela ação**, e o link profundo do Gmail (`https://mail.google.com/mail/u/0/#all/{msgId}`). Isso transforma o diário num histórico auditável de correspondência.
3. **Toda análise vira registro auditável.** Cada e-mail analisado gera um documento (mesmo com veredito "sem relação"), servindo de dedupe, auditoria e base para a Fase 2 (aprendizado com feedback: cada "ignorar" é um sinal para calibrar o limiar).
4. **Limiar de confiança + teto de mensagens.** Só notificar acima de um limiar configurável (padrão 0,6) e no máximo N sugestões por passada, para o Telegram não virar spam de falso-positivo. Com histórico de feedback acumulado, a Fase 2 pode habilitar auto-aplicação para confiança ≥ 0,9.
5. **Silenciar por ação.** Um campo `email_link_optout` na tarefa permite dizer "não vincule e-mails a esta ação" (ex.: ações que geram muito ruído de newsletters institucionais).

## 3. Desenho da solução

### 3.1 Fluxo

```
scheduled_sync (30 min) → run_full_sync
  └─ link_emails_to_actions(db, gmail, sync_ref, logs)     [NOVO — functions/email_action_linker.py]
       1. Gmail: q = "newer_than:2d -category:promotions -category:social", maxResults ~20
       2. skip se já existe doc email_action_suggestions/{msgId}   (dedupe por doc, não por array)
       3. monta o elenco de candidatas: tarefas com status ativo/stand-by (com aliases),
          sem email_link_optout, compactadas (título, projeto, área, tags, 2 últimas notas do diário)
       4. 1 chamada gemini-3.5-flash-lite por e-mail (via generate_content_logged,
          feature="email_action_linker") → JSON {related, task_id, confidence, resumo, nota_sugerida}
       5. related=false ou confidence < limiar → grava doc status="no_match" e encerra
       6. senão → grava doc status="pending" + envia Telegram com botões inline
                                     │
Telegram (usuário toca botão) → telegramWebhook → _handle_telegram_callback
  └─ ramo "emlink:{msgId}:{ok|on|no}"                      [NOVO — hermes_core_logic.py ~2230]
       ok → ArrayUnion no acompanhamento da tarefa
       on → idem + status: 'em andamento' (reativação de stand-by)
       no → marca dismissed (sinal de feedback)
       sempre: atualiza o doc da sugestão, responde o callback e edita a mensagem
```

### 3.2 Nova coleção: `email_action_suggestions`

ID do documento = ID da mensagem do Gmail (dedupe estrutural). Campos:

```
google_message_id, subject, sender, snippet, internal_date,
analyzed_at, model, related (bool), confidence (0-1),
task_id, task_titulo,                 -- candidata escolhida (se related)
resumo, nota_sugerida, reativar_sugerido (bool),
status: 'no_match' | 'pending' | 'applied' | 'applied_reactivated' | 'dismissed' | 'expired',
telegram_sent (bool), applied_at, decided_at
```

Consultas simples (por `status`), sem necessidade de índice composto nem vetorial. Sugestões `pending` com mais de 7 dias são marcadas `expired` na passada seguinte (o callback também recusa agir sobre doc não-`pending`, então botão velho não causa dano).

### 3.3 Matching: LLM com elenco compacto, sem embeddings

As `tarefas` **não são vetorizadas** hoje (a busca de ações é por palavra-chave ponderada, `functions/tools/busca_grafo.py:78-93`). Para um mailbox pessoal com dezenas de ações ativas, a abordagem mais simples e barata é apresentar ao `gemini-3.5-flash-lite` o e-mail (assunto + remetente + corpo truncado a ~4k chars) e o elenco compacto de todas as ações candidatas (~40-80 tokens cada), pedindo JSON estrito. Uma chamada por e-mail, sem infraestrutura nova.

Se o elenco crescer demais (> ~60 ações ativas), pré-filtrar com o scoring lexical de `busca_grafo` e enviar só as top 15 — decisão adiável, medida em produção pelo tamanho do prompt na telemetria.

Embeddings de tarefas (colunas novas, backfill, índice vetorial) ficam explicitamente **fora** do MVP: custo de engenharia alto para ganho incerto neste volume.

### 3.4 Telegram

Mensagem (padrão B — estado no Firestore, doc-ID no callback):

```
📧 E-mail relacionado a uma ação

De: {sender}
Assunto: {subject}

Ação: {task_titulo} ({status})
{resumo}

Nota proposta para o diário:
"{nota_sugerida}"
```

Botões (`callback_data` ≤ 64 bytes; `emlink:` + msgId de 16 hex + `:xx` ≈ 26 bytes ✓):

- `emlink:{msgId}:ok` → ✅ Registrar no diário
- `emlink:{msgId}:on` → 🔄 Registrar + reativar (só quando a ação está em stand-by)
- `emlink:{msgId}:no` → ❌ Ignorar

Nota gravada no diário:

```
[📧 Hermes] E-mail vinculado — De: {sender}
Assunto: {subject}
{resumo}
Gmail: https://mail.google.com/mail/u/0/#all/{msgId}
```

### 3.5 Configuração e guarda-corpos

Documento `system/settings`, chave `email_action_linker`:

- `enabled` (bool, padrão `false` até validar em produção)
- `min_confidence` (padrão 0,6)
- `max_llm_calls_per_pass` (padrão 10) e `max_suggestions_per_pass` (padrão 5 — excedente vira `no_match` com flag `throttled` para reanálise futura, evitando rajada no Telegram)
- `lookback` (padrão `2d`)

Custo estimado: ~30-60 e-mails/dia × 1 chamada flash-lite com prompt de 2-4k tokens ≈ **centavos por mês**, todo logado em `system_usage/gemini/daily/*` via `generate_content_logged`.

## 4. Plano de implementação

### Fase 1 — MVP (backend puro, sem UI web)

1. **`functions/email_action_linker.py` (novo)** — `link_emails_to_actions(db, service, sync_ref, logs)` com os passos 1-6 do fluxo acima. Reusa `get_gmail_service` já resolvido em `run_full_sync`, extração de corpo nos moldes de `email_trigger_handler.py` (MIME walk + html2text), e `generate_content_logged` de `gemini_cost_controls.py`.
2. **Hook no sync** — chamada em `run_full_sync` (`main.py`, após `sync_boletos_gmail`, ~linha 2350), protegida por try/except próprio para nunca derrubar o sync financeiro.
3. **Query de candidatas** — `tarefas` com `status in [aliases de 'em andamento' e 'stand-by']` (reusar o mapa de aliases de `functions/tools/busca_grafo.py:97-108`), excluindo `email_link_optout == true`.
4. **Envio Telegram** — `_send_telegram_message_raw_with_keyboard` (`main.py:6181`), chat resolvido por `_resolve_default_telegram_chat_id`.
5. **Ramo de callback** — novo `elif data.startswith("emlink:")` em `_handle_telegram_callback` (`hermes_core_logic.py`, junto aos demais, ~linha 2230): valida doc `pending`, aplica (`ArrayUnion` no `acompanhamento`; em `on`, também `status: 'em andamento'` — sem tocar `data_conclusao`, seguindo o acoplamento de `main.py:12000-12003`), atualiza o doc, `_answer_callback_query` e edita a mensagem para refletir o desfecho (remove os botões).
6. **Flag + docs** — configuração em `system/settings`; atualizar `schema-firestore.md` (nova coleção + campo `email_link_optout`), `cloud-functions.md` (novo passo do sync) e `log.md`, conforme os gatilhos de `manutencao.md`.

Critérios de aceite da Fase 1: e-mail novo relacionado a uma ação gera exatamente uma sugestão no Telegram; tocar "Registrar" cria a entrada no diário visível no `DiarioBordoUI`; tocar de novo no mesmo botão não duplica; e-mail sem relação não notifica mas fica auditado como `no_match`; sync financeiro intacto mesmo com o linker falhando.

### Fase 2 — Refinamento (após ~2 semanas de uso real)

- **Calibração pelo feedback**: relatório simples de precisão (applied vs dismissed por faixa de confiança) para ajustar `min_confidence`.
- **Auto-aplicação opcional** para confiança ≥ 0,9, com nota marcada `[📧 Hermes · auto]` e notificação informativa (sem botões de confirmação, só "desfazer").
- **Entrada rica no diário**: novo tipo `EMAIL` no formato `TYPE::JSON::` de `src/utils/diaryEntries.ts`, com chip dedicado no `DiarioBordoUI` (ícone, remetente, link).
- **Toggle "silenciar e-mails" na UI da ação** (grava `email_link_optout`).
- **Fila de pendências na web**: listar sugestões `pending`/`expired` em alguma view para decidir pelo navegador o que expirou no Telegram.

### Fase 3 — Unificação com o `email_trigger` morto

Decidir o destino de `email_trigger_handler.py`: (a) **aposentar** — o linker por IA cobre o caso de uso com menos configuração manual (recomendado se a precisão da Fase 1 for boa); ou (b) **reviver como via de alta precisão** — regras manuais por ação alimentando o mesmo pipeline de sugestão/confirmação (em vez da atualização automática original). Em ambos os casos, remover ou reaproveitar a UI de configuração em `Modals.tsx` para não expor uma feature fantasma.

## 5. Riscos e pontos de atenção

| Risco | Mitigação |
|---|---|
| Falso-positivo atualizando ação errada | Confirmação humana no MVP; limiar; auto-aplicação só na Fase 2 com histórico |
| Spam no Telegram | Teto de sugestões por passada; limiar; opt-out por ação; categorias promo/social excluídas na query |
| Status inconsistentes no banco (`standby`, `cgby`…) | Query com o mapa de aliases existente; nunca comparar string exata |
| Botão tocado dias depois (sessão Telegram expira em 30 min) | Padrão doc-ID no callback (sem sessão); doc não-`pending` recusa a ação com toast explicativo |
| Corrida com `sync_pix_emails`/`sync_boletos_gmail` (que arquivam e-mails) | Query própria por `newer_than` (não `in:inbox`); dedupe próprio por doc; e-mails financeiros normalmente resultam em `no_match` |
| Custo Gemini invisível | `generate_content_logged` com `feature="email_action_linker"` desde o dia 1 (ao contrário do caminho de boletos atual) |
| Estouro de contexto com muitas ações ativas | Elenco compacto; pré-filtro lexical via `busca_grafo` se > ~60 candidatas |
