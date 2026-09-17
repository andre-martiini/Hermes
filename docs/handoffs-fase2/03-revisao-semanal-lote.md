# PR 3 (Fase 2) — `feat(revisao-semanal): proposta de reagendamento em lote das ações atrasadas`

**Pré-requisito:** nenhum bloqueante — independente dos PRs 1 e 2 já entregues.

## Por quê

O plano (`docs/plano-evolucao-hermes-jarvis.md`, roadmap Fase 2) pede "revisão semanal com reagendamento em lote **proposto**" — a palavra "proposto" é deliberada: isto não é para reagendar sozinho. Hoje, quando uma ação passa do prazo, ela só aparece via `degradation_count` subindo (que alimenta o `_acao_e_critica` de vários detectores) — ninguém varre o plano inteiro semanalmente para arrumar a fila. O André já tem a ferramenta certa para o reagendamento em si (`preparar_reagendamento_em_lote`), só falta o gatilho periódico que identifica os candidatos e propõe.

## O que já existe (não reinventar)

- **`tools/hermes_tools.py::preparar_reagendamento_em_lote`** — já faz TUDO que a redistribuição precisa: recebe `task_ids`, `nova_data_inicio`, `estrategia` (`data_criacao`/`tipo_acao`/`alfa`), `max_por_semana` (default 5); pula fins de semana; devolve um JSON com `items` (cada um com `task_id`, `titulo`, `data_limite_original`, `nova_data_limite`) e `justificativa`. **Reusar exatamente esta função — não recalcular distribuição de datas do zero.**
- **`tools/hermes_tools.py::reagendar_acoes_em_lote`** — mostra o padrão de aplicar em uma chamada só: chama `preparar_reagendamento_em_lote` e em seguida `_via_callable("confirmarReagendamentoEmLote", _map_confirmar_reagendamento)`, que por sua vez usa `tools/callable_bridge.py::invoke_callable` para invocar a Cloud Function callable `main.py::confirmarReagendamentoEmLote` **em processo**, sem HTTP — ou seja, um job em background PODE aplicar o reagendamento de verdade, exatamente como este PR faz, só que só depois da aprovação (ver Desenho).
- **Padrão de aprovação via Telegram já estabelecido em 3 lugares diferentes** (não inventar um quarto mecanismo):
  - `whatsapp_outbox` (Fase 0) — proposta gravada num doc, notificação com botões, aplicação só no callback.
  - `scheduled_notifications` + callback `ai_notif:{id}:{useful|dismiss}` (`ai_notification_planner.py`/`hermes_core_logic.py` linha ~2399) — mesmíssima forma (doc com id, callback_data `"{prefixo}:{id}:{acao}"`, handler em `_handle_telegram_callback`).
  - `atencao_whatsapp.py::interpretar_resposta_aprovacao_whatsapp` — aprovação de rascunho respondendo no próprio WhatsApp.
- **`hermes_core_logic.py::_handle_telegram_callback`** — o dispatcher único de `callback_query`, com `elif data.startswith("prefixo:")` para cada família de botão. Novo prefixo aqui: `reagendamento_lote:`.
- **`degradation_count`** e `data_limite`/`prazo_final` — já existem em `tarefas`, alimentados por outros detectores (Fase 0). Este PR só lê.

## Desenho — o mínimo que funciona

### Novo job semanal `revisar_semana_propor_reagendamento`

`@scheduler_fn.on_schedule(schedule="15 5 * * 1", timezone="America/Sao_Paulo", ...)` — segunda-feira às 5h15, antes do `atualizar_modelos_pessoas` (5h30) e do briefing (6h45). Semanal porque é uma revisão de higiene do plano, não uma reação a evento.

1. **Trava de proposta única em aberto:** se já existe um doc em `reagendamentos_propostos` com `status == "pending"`, o job não cria um segundo — só loga e sai. (Evita empilhar propostas conflitantes se o André não respondeu a de semana passada; ver "Fora de escopo" sobre reenvio.)
2. Consulta `tarefas` com `status in ("em andamento", "stand-by")` e `data_limite` (ou `prazo_final`, o que estiver preenchido) **anterior a hoje** — estas são as candidatas a reagendar. Sem essas duas condições, não é candidata (não mexer em ação sem prazo, nem em ação já em dia).
3. Se não houver candidatas, não cria proposta nem notifica — silêncio é o padrão correto (mesmo princípio do `ai_notification_planner`).
4. Chama `preparar_reagendamento_em_lote` (import direto da função em `tools/hermes_tools.py`, com um `ToolContext` mínimo — mesmo padrão usado internamente por outras rotinas agendadas que chamam tools) com `task_ids` = as candidatas, `nova_data_inicio` = a próxima segunda-feira (ou hoje, se hoje já for dia útil e a função já lida com isso — reaproveitar a lógica de `_next_weekday` que a própria função já tem), `estrategia="data_criacao"`, `max_por_semana=5` (os defaults da função — não reinventar esse número).
5. Grava a proposta em `reagendamentos_propostos/{id}` (nova coleção, schema igual ao dict que `preparar_reagendamento_em_lote` devolve, mais `status: "pending"`, `criado_em`).
6. Envia UMA mensagem no Telegram (nunca uma por tarefa) resumindo: quantas ações, para qual semana, título das 3 primeiras como amostra — com botões `✅ Aplicar tudo` (`callback_data: reagendamento_lote:{id}:aplicar`) e `❌ Descartar` (`callback_data: reagendamento_lote:{id}:descartar`), reusando `_send_telegram_message_raw_with_keyboard`.

### Novo callback `reagendamento_lote:` em `hermes_core_logic.py::_handle_telegram_callback`

Mesmo formato do `ai_notif:` (linha ~2399): `parts = data.split(":")`, `proposta_id`, `acao` (`aplicar`/`descartar`).

- `aplicar`: lê `reagendamentos_propostos/{id}` (se `status != "pending"`, responde "já processada" e sai — dedupe contra duplo clique); chama `_via_callable`-style `invoke_callable(main.confirmarReagendamentoEmLote, {"items": ..., "justificativa": ...}, ...)` com os `items` gravados no doc (não reconsultar `tarefas` — usar exatamente o que foi proposto, para o que o André aprovou ser o que é aplicado); marca `status: "aplicado"`, `aplicado_em`.
- `descartar`: marca `status: "descartado"`, sem side effect nas tarefas.
- Toast de confirmação via `_answer_callback_query`, igual aos demais callbacks.

## Travas

- **Nunca aplicar sem o toque explícito no botão** — o job só propõe; a aplicação de verdade só acontece dentro do handler do callback, nunca dentro do job agendado.
- **Não reconsultar `tarefas` no momento do `aplicar`** — usar os `items` congelados no documento da proposta (o que o André viu no Telegram é o que é aplicado, mesmo que algo tenha mudado nas tarefas entre a proposta e o clique).
- Não criar segunda proposta enquanto houver uma `pending` — evita conflito de duas distribuições de datas sobre as mesmas tarefas.
- Não incluir ação sem `data_limite`/`prazo_final`, nem ação já em dia — só candidatas genuinamente atrasadas.
- Silêncio é o resultado padrão correto quando não há atrasadas.

## Testes

- Job sem candidatas (nenhuma tarefa atrasada) → não cria proposta, não notifica.
- Job com candidatas → chama `preparar_reagendamento_em_lote` com os `task_ids` corretos, grava doc `pending`, envia 1 mensagem com os 2 botões.
- Job com proposta `pending` já existente → não cria uma segunda, apenas loga.
- Callback `aplicar` com proposta `pending` → chama a aplicação com os itens do documento (mock), marca `status: "aplicado"`.
- Callback `aplicar` com proposta já `aplicado`/`descartado` → não reaplica, responde "já processada".
- Callback `descartar` → marca `status: "descartado"`, nenhuma chamada de aplicação.

Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Fora de escopo

- Reenviar/lembrar automaticamente uma proposta `pending` sem resposta há muito tempo — fica para uma iteração futura (mesmo princípio da "válvula de segurança" do dev-sync: se ficar pendente por dias, o job seguinte só constata e não insiste).
- Qualquer edição parcial da proposta pelo André (aceitar 8 de 10 itens) — hoje é tudo ou nada (`Aplicar tudo`/`Descartar`); edição granular fica para a UI web existente (`preparar_reagendamento_em_lote` + card de confirmação), que continua funcionando em paralelo sem mudança.
- Mudar `max_por_semana`, a estratégia de ordenação ou a lógica de distribuição de datas — usar exatamente o que `preparar_reagendamento_em_lote` já faz.

## Docs

`docs/okf/arquitetura/schema-firestore.md` (nova coleção `reagendamentos_propostos`), `docs/okf/log.md`.
