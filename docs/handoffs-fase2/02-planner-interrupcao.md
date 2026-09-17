# PR 2 (Fase 2) — `feat(atencao): notificação event-driven para itens de alta prioridade, com orçamento de interrupção unificado`

**Pré-requisito:** nenhum bloqueante — independente do PR 1 (modelo_interacao). Pode ser feito em paralelo ou depois, tanto faz.

## Por quê

O plano (`docs/plano-evolucao-hermes-jarvis.md`, Eixo 2 e roadmap Fase 2) pede um "planner event-driven com orçamento de interrupção e escopo em finanças/saúde". Hoje o `ai_notification_planner_daily` roda 1x/dia (6h30, cron) e só olha `tarefas`/`estrategia_pessoal` — um item de alta prioridade que aparece na fila de atenção às 10h só vira notificação (se virar) no dia seguinte às 6h30. Isso não é aceitável para o que a fila de atenção já classifica como `prioridade: alta` (ex.: promessa vencida a um contato vinculado a uma ação crítica).

## O que já existe (não reinventar)

- **`atencao.py`** — a fila de atenção (Fase 0). Já tem `prioridade` (`alta`/`media`/`baixa`), `estado` (`aberto`/`delegado_ao_agente`/`aguardando_andre`/`resolvido`/`descartado`) e **`ORIGENS` já inclui `"financeiro"` e `"saude"`** (linha 18) — o schema já foi desenhado para esses domínios, só não existe detector que os popule ainda. Itens são criados por dois caminhos: `detectar_atencao_acoes` (cron a cada 30 min, ações) e `atencao_whatsapp.py::on_whatsapp_message_atencao` (trigger `on_document_written` em `whatsapp_messages`, promessas/áudio — já é event-driven do lado da **detecção**).
- **`ai_notification_planner.py`** — já tem tudo que "orçamento de interrupção" precisa, só que hoje só é usado 1x/dia:
  - `_reserve_and_create_notification(db, today_str, doc_ref, payload)` — reserva atômica (transação Firestore) contra o contador diário em `system_usage/ai_planner_notifications/daily/{today}`, com teto `AI_PLANNER_MAX_DAILY_NOTIFICATIONS` (hoje 3). **Este É o orçamento de interrupção — não criar um segundo mecanismo de teto.**
  - `AI_PLANNER_WINDOW_START`/`AI_PLANNER_WINDOW_END` (07:00–22:00) — **isto já é o "horário de silêncio"** do plano, só que hoje só é validado dentro de `propor_notificacao` (chamada pela LLM). Precisa virar uma checagem reutilizável fora desse contexto.
  - `scheduled_notifications` (coleção) + `dispatch_pending_ai_notifications(db, now)` — o envio de fato ao Telegram, com botões 👍/👎, **já roda a cada 1 minuto** dentro de `check_and_send_reminders` (`main.py`, `@scheduler_fn.on_schedule(schedule="every 1 minutes", ...)`, seção "4." do corpo da função, linha ~3760). **Isto já é o caminho "quase em tempo real" — não precisa de um novo mecanismo de envio.**
- **Conclusão da pesquisa:** a peça que falta não é orçamento, nem janela de silêncio, nem envio — é só a **decisão de reagir a um item de alta prioridade assim que ele aparece**, em vez de esperar o cron das 6h30. E como o item de `atencao` já chega com `titulo`/`resumo`/`sugestao` prontos (o detector que o criou já fez esse trabalho), **não precisa de uma nova chamada a LLM neste PR** — só uma ponte determinística entre "item alta prioridade e ainda não avaliado" e "gravar em `scheduled_notifications` respeitando teto e janela".

## Desenho — o mínimo que funciona

### Por que um *sweep* a cada 1 min, e não um trigger `on_document_written` em `atencao/{itemId}`

Cogitei um trigger no estilo do `contexto_agente`, mas `detectar_atencao_acoes` já escreve em `atencao` a cada 30 min via `.set(payload, merge=True)` mesmo quando nada relevante mudou (reafirma o item aberto) — um trigger por documento dispararia nesses merges redundantes e nas transições de `resolver_item` (`resolvido`/`descartado`), exigindo lógica de diff cuidadosa só pra filtrar ruído. Uma *query* periódica (`estado == "aberto"` AND `prioridade == "alta"`, filtrando em memória quem ainda não tem o novo campo `avaliado_interrupcao_em`) já ignora esse ruído de graça: só pega item genuinamente novo-e-não-avaliado, independente de quantas vezes o doc foi reescrito. E rodando a cada 1 minuto dentro do `check_and_send_reminders` que **já existe**, o item entra na fila de notificação até 1 minuto depois de criado — sem Cloud Function nova, sem custo de infra adicional.

### Novo campo `atencao.avaliado_interrupcao_em`

Timestamp gravado a primeira vez que o sweep avalia o item (independente do resultado — notificou ou não por falta de orçamento). É o dedupe: sem isso, o mesmo item seria reavaliado a cada minuto para sempre. **Exceção:** se o item foi pulado só por estar fora da janela de silêncio, **não grava o campo** — deixa para o próprio sweep do próximo minuto tentar de novo (naturalmente, sem lógica extra, o item vira notificação assim que a janela abrir, o mais tardar 1 min depois).

### Função `avaliar_interrupcao_atencao(db, now)` (novo, em `atencao.py`)

1. Query `db.collection("atencao").where("estado", "==", "aberto").where("prioridade", "==", "alta")` (conjunto pequeno por natureza — só itens realmente urgentes chegam com `prioridade: alta`).
2. Filtra em memória quem não tem `avaliado_interrupcao_em` setado.
3. Para cada candidato (isolado em `try/except` — um item com erro não pode travar os demais, mesmo princípio do `processar_modelo_pessoa`):
   a. Checa janela de silêncio: horário atual (America/Sao_Paulo) dentro de `AI_PLANNER_WINDOW_START`–`AI_PLANNER_WINDOW_END`? Se não, pula sem marcar `avaliado_interrupcao_em` (retry automático no próximo minuto).
   b. Se dentro da janela: monta `titulo`/`mensagem` a partir dos campos que o item já tem (`item["titulo"]`, `item["resumo"]`, `item.get("sugestao")` como complemento opcional) — **sem chamar LLM**, o detector que criou o item já fez essa síntese.
   c. Mapeia `origem` → `categoria` de `scheduled_notifications`: `"acao"` → `"acoes"`; qualquer outra origem (inclusive `"financeiro"`/`"saude"`, hoje sem detector) → `"geral"` (fallback seguro, não quebra se `_CATEGORY_ICONS` não tiver a chave).
   d. Chama `_reserve_and_create_notification(db, today_str, doc_ref, payload)` (importado de `ai_notification_planner.py`) com `send_at=now` — o mesmo teto diário do planner de 6h30, sem contador separado. `source: "atencao_interrupcao"` no payload (não `"ai_planner"`, para não confundir com as propostas da LLM ao consultar `consultar_notificacoes_recentes`).
   e. Grava `avaliado_interrupcao_em=firestore.SERVER_TIMESTAMP` no doc de `atencao` (reservou ou não — orçamento estourado também conta como avaliado; o item continua visível normalmente na fila via `coletar_fila_atencao`, só não gera push ativo).

### Ponto de chamada

Em `main.py::check_and_send_reminders`, na mesma seção "4." que já chama `dispatch_pending_ai_notifications`/`dispatch_scheduled_whatsapp_messages` (linha ~3762), adicionar:

```python
from atencao import avaliar_interrupcao_atencao
avaliar_interrupcao_atencao(db, now)
```

dentro do mesmo bloco `try/except` (ou um próprio, se preferir isolar falhas desta função das duas existentes — decisão de implementação, ambas ok).

## Travas

- **Não criar um segundo contador/teto** — reusar `_reserve_and_create_notification` e o mesmo documento `system_usage/ai_planner_notifications/daily/{today}`. O orçamento de interrupção é UM só, compartilhado entre o planner diário e este sweep.
- **Não chamar LLM neste sweep** — o item de `atencao` já chega pré-sintetizado pelo detector que o criou. Adicionar uma chamada de LLM a uma função que roda a cada 1 minuto seria caro e desnecessário.
- **Não reabrir nem alterar `estado`/`prioridade` do item de `atencao`** — este PR só lê e grava `avaliado_interrupcao_em`; mão única, igual ao PR 1.
- Item pulado por janela de silêncio nunca pode ficar marcado como avaliado — senão nunca mais notifica.
- Falha ao processar um item não pode interromper os demais nem o resto do `check_and_send_reminders`.

## Testes

- `avaliar_interrupcao_atencao` com item `prioridade: alta`, `estado: aberto`, sem `avaliado_interrupcao_em`, dentro da janela → chama `_reserve_and_create_notification` e grava `avaliado_interrupcao_em`.
- Mesmo item fora da janela de silêncio → não chama `_reserve_and_create_notification`, não grava `avaliado_interrupcao_em`.
- Item com `avaliado_interrupcao_em` já setado → ignorado (nem entra na query em memória, ou é filtrado).
- Orçamento diário já esgotado (`_reserve_and_create_notification` retorna `False`) → ainda assim grava `avaliado_interrupcao_em` (não fica reavaliando o resto do dia).
- Mapeamento de categoria: `origem="acao"` → `"acoes"`; `origem="financeiro"` (mesmo sem detector real, simular no teste) → `"geral"`, sem quebrar.
- Isolamento de falha: um item lançando exceção não impede o processamento dos demais.
- `prioridade: media`/`baixa` nunca entra na query (ou é ignorado se entrar por engano).

Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Fora de escopo

- **Detectores de `atencao` para os domínios `financeiro`/`saude`** — este PR só faz a ponte "item de alta prioridade → notificação rápida" funcionar para QUALQUER origem, incluindo essas duas, no momento em que existirem. Construir os detectores de fato (que exigiriam ferramentas de leitura calibradas para finanças/saúde, hoje só existentes no MCP interativo — `consultar_financas_v2`/`consultar_saude` — não adaptadas para uso em background) é trabalho de um PR futuro, fora da Fase 2 se necessário.
- Personalizar `_CATEGORY_ICONS` para `financeiro`/`saude` — sem detector ativo, seria código morto agora; adicionar quando o primeiro detector desses domínios existir.
- Qualquer mudança em `ai_notification_planner_daily` (o cron das 6h30) — continua rodando exatamente como está, olhando tarefas/metas estratégicas 1x/dia. Este PR é aditivo, não substitui o planner diário.
- Ajustar o teto diário (`AI_PLANNER_MAX_DAILY_NOTIFICATIONS=3`) ou a janela (`07:00–22:00`) — usar os valores que já existem.

## Docs

`docs/okf/arquitetura/schema-firestore.md` (novo campo `atencao.avaliado_interrupcao_em`), `docs/okf/log.md`.
