# PR 2 — `feat(atencao): fila de atencao, tools e detector aguardando_terceiro vencido`

## Por quê

Hoje os sinais que pedem atenção do dono estão espalhados em coleções e formatos diferentes: `scheduled_notifications` (planejador de IA), `inbox_pendentes` (respostas pendentes), `elevacoes_sugeridas`, `email_action_suggestions`, `notificacoes`. Um agente que acorda numa sessão nova precisa de várias chamadas e de conhecimento sobre cada formato para saber o que importa agora. Este PR cria **um lugar só**, com **uma forma só**, e o primeiro detector que escreve nele.

Este PR **não** migra os detectores existentes — eles continuam escrevendo onde escrevem. A migração fica para depois, quando a fila tiver provado o formato.

## Coleção `atencao`

Um documento por item. Campos:

| Campo | Tipo | Notas |
|---|---|---|
| `origem` | string | `acao`, `whatsapp`, `email`, `agenda`, `repo`, `financeiro`, `saude` |
| `tipo` | string | Identificador estável do detector. Neste PR: `aguardando_terceiro_vencido` |
| `prioridade` | string | `alta`, `media`, `baixa` |
| `titulo` | string | Uma linha, legível pelo dono |
| `resumo` | string | Até ~400 caracteres, sem markdown |
| `acao_id` | string ou null | `tarefas/{id}` vinculada |
| `etapa_id` | string ou null | id do passo do `plano_acao`, quando houver |
| `pessoa` | string ou null | Quem está envolvido (`aguardando_de`, autor da mensagem) |
| `prazo` | timestamp ou null | Data que motivou o item |
| `evidencia` | map | Ids que sustentam o item: `{acao_id, etapa_id, chat_id, mensagem_ids: []}` — só ids, nunca conteúdo copiado |
| `sugestao` | string | O que o detector acha que deve ser feito (texto curto; o Claude decide) |
| `estado` | string | `aberto`, `delegado_ao_agente`, `aguardando_andre`, `resolvido`, `descartado` |
| `chave_dedupe` | string | Ver abaixo |
| `criado_em`, `atualizado_em` | timestamp | Server timestamp |
| `resolvido_em`, `desfecho` | timestamp / string | Preenchidos por `resolver_item_atencao` |

**Dedupe:** o id do documento é `chave_dedupe`, montada pelo detector de forma determinística (ex.: `aguardando_terceiro_vencido:{acao_id}:{etapa_id}`). Rodar o detector de novo faz `set(..., merge=True)` no mesmo doc e **não** cria item duplicado. Um item `resolvido`/`descartado` não é reaberto pelo detector a menos que o dado de origem tenha mudado (para `aguardando_terceiro_vencido`: a `data_prevista` da etapa mudou para outra data também vencida).

## Detector `aguardando_terceiro_vencido`

Arquivo novo: `functions/atencao.py`. Cloud Function `detectar_atencao_acoes`, Scheduler a cada 30 min, `timezone="America/Sao_Paulo"`, atrás da flag `system/settings.atencao.aguardando_terceiro.enabled` (padrão desligado). Siga o padrão de `ai_notification_planner.py` (`@scheduler_fn.on_schedule`, leitura de flag antes de qualquer trabalho).

Regra, toda determinística:

1. Varrer `tarefas` com status ativo (use os mesmos aliases de `inbox_pendentes._ACTIVE_STATUS_ALIASES` e `_STANDBY_STATUS_ALIASES` para não inventar uma terceira lista).
2. Para cada passo do `plano_acao` com `estado == "aguardando_terceiro"` e `data_prevista` (resolvida por `subtarefas.data_prevista_de`, como `obter_acao` faz) anterior a **hoje** no fuso de São Paulo:
3. Criar/atualizar item: `origem="acao"`, `prioridade="alta"` se a ação for crítica (reuse o critério que `morning_summary.build_morning_summary` já usa para "críticas"), senão `"media"`; `pessoa = aguardando_de`; `titulo = "{aguardando_de} deveria ter respondido sobre: {texto da etapa}"`; `sugestao = "Cobrar {aguardando_de} ou reagendar a etapa"`.
4. Se existir vínculo `tarefas.whatsapp_vinculos` e houver mensagem em `whatsapp_messages` daquele chat com `timestamp >= data_prevista` e `from_me == false`, **não** criar o item (a pessoa respondeu; quem avalia se resolveu é o dono). Registre isso num comentário: é a única inteligência do detector e é o que evita o ruído mais óbvio.

Execução pura e testável: separe `avaliar_etapas(tarefas: list[dict], hoje: date) -> list[dict]` (sem Firestore) de `detectar_atencao_acoes` (que lê, chama e grava). Teste `avaliar_etapas` em `functions/test_atencao.py` com pelo menos: etapa vencida gera item; etapa vencida com resposta do terceiro não gera; etapa não vencida não gera; ação concluída ignorada; rodar duas vezes gera a mesma `chave_dedupe`.

## Tools

Três alterações, seguindo "Adicionar uma tool nova" em `docs/okf/copiloto/mcp-servidor.md`:

**`obter_fila_atencao`** (leitura, sem confirmação). Args: `estado` (padrão `aberto`), `origem` (opcional), `limite` (padrão 20, teto 100). Devolve `{total, itens: [...]}` com os campos acima. Ordenação: prioridade (alta→baixa), depois `prazo` ascendente, depois `criado_em`.

**`resolver_item_atencao`** (escrita — entra em `_NEEDS_CONFIRMATION`). Args: `item_id`, `estado` (um de `delegado_ao_agente`, `aguardando_andre`, `resolvido`, `descartado`), `desfecho` (texto curto, obrigatório para `resolvido` e `descartado`). Grava `estado`, `desfecho`, `resolvido_em`, `atualizado_em`. Se o item tiver `acao_id`, registra uma linha no diário da ação (`acompanhamento`) com o desfecho — reuse a função que `registrar_no_diario` usa, não reimplemente. Recusa item inexistente com `{erro, status: "not_found"}`.

**`obter_estado_atual`** (`functions/tools/hermes_tools.py`, ~linha 1638): acrescentar a chave `fila_atencao` com os até 10 itens `aberto` de maior prioridade e `fila_atencao_total`. Faça isso dentro de um `try/except` próprio, como já é feito com `pops_ativos`: a fila nunca pode derrubar o estado atual. Prefira estender `build_morning_summary` em `morning_summary.py` se for o lugar natural — mas então atualize `test_morning_summary.py`.

Schemas em `functions/tools/schemas/obter_fila_atencao.json` e `resolver_item_atencao.json`, com `description` que diga ao modelo **quando** usar (ex.: "Chame no início de uma sessão, depois de obter_estado_atual, quando quiser ver tudo que pede atenção, não só o top 10").

## Testes

- `functions/test_atencao.py` (novo) — cobre `avaliar_etapas` e a montagem da `chave_dedupe`.
- `functions/test_hermes_tools.py` já verifica catálogo ↔ schema ↔ handler; rode e garanta que passa com as duas tools novas.
- `functions/test_morning_summary.py` se `build_morning_summary` foi tocado.
- Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Firestore

- Índice: `atencao` por `estado ASC, prioridade ASC, prazo ASC` — adicionar em `firestore.indexes.json`.
- Regras: `atencao` segue o mesmo padrão das coleções internas (leitura só pelo dono autenticado; escrita só pelo Admin SDK). Confira `firestore.rules` e o commit `fix(seguranca): nega ao cliente web o acesso a colecao automations` (02/09) como referência do que foi exigido recentemente.

## Fora de escopo

Interface web para a fila; migração dos detectores existentes; qualquer notificação ao dono (a fila é consumida pelo Claude nas rotinas agendadas — o Telegram não entra aqui).

## Docs

`docs/okf/arquitetura/schema-firestore.md` (coleção `atencao`), `docs/okf/arquitetura/cloud-functions.md` (função `detectar_atencao_acoes` e seção nova "Fila de Atenção"), `docs/okf/copiloto/mcp-servidor.md` (as duas tools), `docs/okf/log.md`.
