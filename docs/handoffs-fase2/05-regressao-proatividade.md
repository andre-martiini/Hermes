# PR 5 (Fase 2) — `feat(regressao-proatividade): cenários de regressão dos detectores proativos, ligando gatilho real a desfecho observável`

**Pré-requisito:** nenhum bloqueante — independente dos PRs 1-4 já entregues. Último PR da Fase 2: depois deste, mergeado e verificado, a fase fecha.

## Por quê

O plano (`docs/plano-evolucao-hermes-jarvis.md`, Eixo 6) pede: "Regressão de comportamento proativo no motor de simulação existente (`functions/simulation`): cenários como 'áudio de contato vinculado chega' ou 'promessa sem retorno há 5h' com o desfecho esperado, para que mudanças nos detectores não silenciem o sistema sem ninguém notar."

## O que já existe (não reinventar) — e por que este PR não mexe em `functions/simulation/`

- **`atencao.py::avaliar_etapas`**, **`atencao_whatsapp.py::avaliar_audio`** e **`atencao_whatsapp.py::avaliar_promessas_vencidas`** — as 3 funções puras dos 3 detectores da Fase 0 (aguardando_terceiro_vencido, audio_relevante, promessa_sem_retorno). Já testadas isoladamente em `test_atencao.py`/`test_atencao_whatsapp.py`.
- **`atencao.py::avaliar_interrupcao_atencao(db, now)`** (PR 2 da Fase 2, #163) — o sweep que decide se um item de prioridade alta vira notificação de fato. Já testado em `test_atencao.py::TestAvaliarInterrupcaoAtencao` com `@patch("atencao._reserve_and_create_notification")` e um `MockDb`.
- **`MockDb`/`MockDoc`/`MockQuery`** já existem em `test_atencao.py` (linhas ~33-100) — fixture de Firestore em memória usada em todos os testes de `atencao.py`. **Reusar via `from test_atencao import MockDb, MockDoc, MockQuery`, nunca duplicar.**
- **`functions/simulation/`** (mencionado no texto do plano) — na prática, esse módulo simula uma **empresa de agentes de IA executando ações do Hermes** num namespace isolado (`simulation/{sim_id}/...`), com os três portões Approval/Decision/Handoff e um `dry_run_executor`. É um conceito totalmente diferente de "os detectores proativos continuam disparando quando deveriam" — não tem hook nenhum para eventos de WhatsApp, promessas ou etapas vencidas, e forçar essa ligação criaria acoplamento artificial sem ganho real. **Este PR não estende `functions/simulation/`.** O que realmente evita a regressão silenciosa que o Eixo 6 teme é testar a cadeia completa — do gatilho real (mensagem de áudio, promessa vencida, etapa vencida) até o desfecho que o André de fato veria (uma notificação agendada, ou a presença correta na fila) — usando o código real dos detectores, não uma reimplementação.

## Desenho — o mínimo que funciona

Novo arquivo **`functions/test_regressao_proatividade.py`** com 3 cenários nomeados, espelhando os 3 detectores da Fase 0 e os dois exemplos que o próprio plano cita. Cada cenário chama só funções públicas reais (nunca reimplementa lógica de detecção) e roda no gate padrão (`python -m unittest discover -s . -p "test_*.py"`), então qualquer PR futuro que altere um detector e quebre o desfecho esperado **quebra a CI imediatamente** — sem depender de alguém lembrar de rodar isso manualmente.

1. **`test_cenario_audio_relevante_contato_vinculado_dispara_interrupcao`**
   - Monta uma mensagem de áudio (`from_me=False`, `message_type="ptt"`) com `contexto={"chat_vinculado": True, "acao": <ação crítica>}` → `avaliar_audio(mensagem, contexto)` deve retornar item com `tipo=TIPO_AUDIO_RELEVANTE`, `prioridade=PRIORIDADE_ALTA` (só é alta porque a ação vinculada é crítica — usar uma ação que passe em `atencao._acao_e_critica`).
   - Constrói `MockDb` (importado de `test_atencao`) com esse item já em `atencao` (`estado=ESTADO_ABERTO`).
   - Com `@patch("atencao._reserve_and_create_notification")` retornando `True`, chama `avaliar_interrupcao_atencao(db, now=<horário dentro de 07:00-22:00>)`.
   - Assert: `notificados == 1`; o payload passado para `_reserve_and_create_notification` carrega o `title`/`message` do item de áudio — ou seja, o áudio realmente chegaria ao Telegram do André.

2. **`test_cenario_promessa_sem_retorno_5h_dispara_interrupcao`**
   - Monta uma promessa (`estado=ESTADO_PROMESSA_ABERTA`, `prometido_em` = agora − 5h, `vence_em` no passado) → `avaliar_promessas_vencidas([promessa], agora)` retorna item com `tipo=TIPO_PROMESSA_SEM_RETORNO`, `prioridade=PRIORIDADE_ALTA`, `titulo` citando "ha 5h" (ou valor equivalente calculado por `gerar_item_vencimento`).
   - Mesmo encadeamento pelo `avaliar_interrupcao_atencao` (item no `MockDb`, `_reserve_and_create_notification` mockado) → assert `notificados == 1`.

3. **`test_cenario_aguardando_terceiro_vencido_fica_na_fila_sem_interromper`**
   - Monta uma tarefa com etapa `estado="aguardando_terceiro"` vencida → `avaliar_etapas([tarefa], hoje)` retorna item com `tipo=TIPO_AGUARDANDO_TERCEIRO_VENCIDO`, `prioridade=PRIORIDADE_MEDIA` (comportamento já existente e correto — este item NÃO deve interromper).
   - Coloca o item no `MockDb` e chama `coletar_fila_atencao(db, ...)` → assert que o item aparece na fila com os campos esperados (contrato: chega ao André pelo briefing/varredura, não por interrupção).
   - No MESMO `MockDb`, chama `avaliar_interrupcao_atencao(db, now=...)` → assert `candidatos == 0` (a query do sweep já filtra `prioridade == alta`, então prioridade média nunca entra). Trava explícita contra duas regressões opostas: (a) uma mudança acidental que promova esse tipo a prioridade alta e passe a interromper o André sem necessidade; (b) uma mudança que quebre `avaliar_etapas` e o item pare de aparecer até na fila normal.

## Travas

- Cenários usam só as funções públicas reais dos detectores e do sweep — nunca reimplementam a lógica de decisão.
- Reusa `MockDb`/`MockDoc`/`MockQuery` de `test_atencao.py` via import — não duplica fixture.
- Não cria nenhum job novo, nenhuma coleção nova, nenhuma tool nova, nenhuma mudança em `atencao.py`/`atencao_whatsapp.py` — é puramente um arquivo de teste de regressão.
- Não estende `functions/simulation/` (motivo explicado acima).
- Roda no gate padrão de testes — nenhuma execução manual ou agendada separada.

## Testes

Os próprios 3 cenários acima são os testes deste PR (não há código de produção novo além de um arquivo de teste). Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"` (deve continuar 100% verde, agora com os 3 cenários novos inclusos).

## Fora de escopo

- Qualquer extensão de `functions/simulation/` (motor de "empresa de agentes") — este PR não o usa nem o modifica.
- Novos detectores ou mudança de comportamento dos existentes.
- Dashboards, relatórios ou exposição via tool dos cenários de regressão — ficam para depois, se forem pedidos.
- Rodar os cenários fora do gate de testes padrão (ex.: como uma tool consultável ou rotina agendada).

## Docs

Nenhuma mudança de schema (nenhuma coleção nova, nenhum campo novo). Só `docs/okf/log.md` registrando a existência do gate de regressão de proatividade e o que ele cobre.

## Ao concluir

Este é o **último PR da Fase 2**. Depois de mergeado e verificado, todos os 5 PRs da fase estarão completos — vale confirmar contra o roadmap do plano (seção 5) se o critério de pronto da Fase 2 ("≥50% dos itens da fila resolvidos sem o André iniciar; taxa de dispensa de notificações caindo semana a semana") já pode começar a ser observado, e escopar a Fase 3 ("Autonomia graduada", a partir do mês 4, seção 5 do plano) como próximo handoff.
