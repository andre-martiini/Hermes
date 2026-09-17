# PR 4 (Fase 2) — `feat(retro-agente): retro semanal de execuções, com proposta de ajuste de POP quando houver padrão concreto`

**Pré-requisito:** nenhum bloqueante — independente dos PRs 1-3 já entregues.

## Por quê

O plano (`docs/plano-evolucao-hermes-jarvis.md`, Eixo 6, "Autoaperfeiçoamento") pede métricas de proatividade e retro semanal do agente, com ajustes de POP/prompt propostos a partir do que realmente aconteceu — não de achismo. O sistema já registra dois rastros de execução (`agent_runs`, `mcp_audit_log`); ninguém ainda olha os dois juntos, uma vez por semana, para achar padrão.

## O que já existe (não reinventar)

- **`agent_runs.py`** (Fase 1, PR #158) — coleção `agent_runs`, gravada via `registrar_execucao_agente` ao fim de cada rotina agendada do Claude (briefing, varredura de follow-ups etc.). Schema: `rotina`, `resumo`, `status` (`sucesso`\|`erro`\|`parcial`), `contadores` (dict livre), `erro`, `iniciado_em`, `finalizado_em`, `criado_em`. `agent_runs.listar_recentes(db, rotina=None, limite=20)` já existe — **reusar esta função** (ou uma variante com filtro de data, ver Desenho) em vez de escrever uma nova query.
- **`mcp_server.py::_audit_log`** — grava em `mcp_audit_log` a CADA chamada de tool via MCP: `uid`, `tool`, `arguments`, `latency_ms`, `timestamp`. **Achado importante:** o `is_error` já é calculado em `_handle_tools_call` (linha ~703, `is_error = bool(result.get("erro")) if isinstance(result, dict) else _looks_like_error(result)`) mas **não é passado para `_audit_log`** — hoje é impossível saber, pela auditoria, se uma chamada de tool falhou. Sem esse campo, "retro" não consegue calcular taxa de erro por tool, só volume e latência. Este PR faz a extensão mínima: adicionar o parâmetro `is_error: bool = False` a `_audit_log` e passá-lo nos 4 pontos de chamada (linha ~605, ~626, ~699, ~723) usando o `is_error` que cada um já calcula (o de `job longo`, linha ~699, não tem resultado ainda — mantém `is_error=False`, é só o enfileiramento do job). **Aditivo puro: não muda nenhum comportamento existente, só acrescenta um campo novo aos documentos futuros.**
- **`correcoes_pendentes` + Motor de Evolução Autônoma (`main.py::processar_correcoes_pendentes`, `every 60 minutes`)** — **este é o mecanismo de proposta de POP que já existe, não inventar um novo.** Hoje alimentado por `registrar_correcao_procedimento` (tool do Copiloto, quando o André corrige um procedimento em conversa). Schema do doc: `id`, `area_tematica`, `titulo_procedimento`, `correcao_descrita`, `novo_conteudo_proposto`, `justificativa_usuario`, `status: "pendente"`, `data_criacao`, `session_id`, `task_id`. O motor já lê essa fila, valida por consenso web (Tavily, mín. 5 fontes) e refina com Gemini antes de persistir em `conhecimento_mestre` — **isto já É a validação assíncrona que qualquer proposta de ajuste de POP precisa; este PR só precisa escrever nessa fila, nunca aplicar direto.**
- **`gemini_cost_controls.py::generate_content_logged`** e `GEMINI_STRUCTURED_MODEL` — mesmo caminho de custo controlado usado por `contexto_agente`/`modelo_pessoa`.

## Desenho — o mínimo que funciona

### Extensão mínima em `mcp_server.py` (pré-requisito interno deste PR)

`_audit_log(*, uid, tool, arguments, latency_ms, is_error: bool = False)` — grava `is_error` no payload. Atualizar as 4 chamadas existentes para passar o `is_error` que já está em escopo em cada uma (`False` explícito onde o resultado ainda não existe).

### Novo job semanal `retro_semanal_agente` (`functions/retro_agente.py`)

`@scheduler_fn.on_schedule(schedule="0 20 * * 0", timezone="America/Sao_Paulo", ...)` — domingo às 20h (depois do `detectar_subproduto_semanal`, que já roda às 18h de domingo com a mesma justificativa: "a semana já aconteceu, cabe folga antes da próxima"; antes da revisão semanal de reagendamento de segunda 5h15).

1. Calcula a janela: últimos 7 dias corridos até agora.
2. Consulta `agent_runs` no período (filtro por `criado_em >= cutoff`, reaproveitando o padrão de leitura de `agent_runs.listar_recentes` ou uma query direta equivalente) e agrega por `rotina`: total, contagem por `status`, até 3 mensagens de `erro` distintas mais recentes.
3. Consulta `mcp_audit_log` no mesmo período e agrega por `tool`: contagem de chamadas, latência média/máxima, contagem de `is_error=True` (campo novo).
4. **Sinal insuficiente → silêncio:** se não houver nenhum documento de `agent_runs` no período, encerra sem persistir nem notificar (não há o que retrospectar).
5. Monta um texto-fonte SÓ com os agregados (nunca o payload bruto de `arguments`/`resumo` completos — o texto é curto e já resumido, mantendo o prompt barato e sem vazar dados sensíveis de argumentos de tool).
6. Chama Gemini (`generate_content_logged`, `feature="retro_agente"`, `model=GEMINI_STRUCTURED_MODEL`) com um prompt que pede: um resumo de 2-3 frases da semana, e — **regra inegociável, mesmo espírito do `contexto_agente`/`modelo_pessoa`** — uma proposta de ajuste de POP **somente se houver um padrão concreto e repetido** (ex.: a mesma rotina falhando ≥3 vezes com o mesmo tipo de erro, ou uma tool com taxa de erro muito acima da média das demais). Sem padrão claro, o campo de proposta vem `null` — nunca forçar uma sugestão genérica só para preencher o campo.
7. Parse defensivo idêntico ao já usado (regex de objeto JSON, fallback de cerca markdown, campo de proposta ausente ou inválido → `null`).
8. Grava o retro em `retros_agente/{id}` (nova coleção): `periodo_inicio`, `periodo_fim`, `resumo`, `metricas` (os agregados brutos do passo 2-3, para série histórica), `proposta_pop` (o que foi ou não proposto), `criado_em`.
9. **Se e somente se** houve proposta concreta: grava um novo doc em `correcoes_pendentes` com o MESMO schema que `registrar_correcao_procedimento` já usa (`area_tematica`, `titulo_procedimento`, `correcao_descrita`, `novo_conteudo_proposto`, `justificativa_usuario` = o resumo da evidência que embasou a proposta, `status: "pendente"`, `data_criacao`, `session_id: ""`, `task_id: ""`) — o Motor de Evolução (já existente, roda de hora em hora) assume a partir daí; este PR não implementa validação nem aplicação.
10. Envia UMA mensagem Telegram informativa (sem botões — nada aqui é aplicado direto, então não há o que aprovar/descartar neste PR): resumo de 2-3 frases +, se houve proposta, uma linha dizendo que uma proposta de ajuste de POP foi registrada e está em validação pelo Motor de Evolução.

## Travas

- **Nunca aplicar ajuste de POP diretamente** — este PR só escreve em `correcoes_pendentes`; quem valida e aplica é o Motor de Evolução que já existe, sem nenhuma mudança nele.
- **Nunca propor ajuste sem padrão concreto e repetido** — silêncio (campo `null`) é o resultado padrão correto na maioria das semanas.
- **Extensão de `_audit_log` é aditiva** — nenhum código existente que lê `mcp_audit_log` pode quebrar por causa do campo novo; documentos antigos simplesmente não o têm (tratar ausência como `False`/desconhecido na agregação).
- Texto-fonte do prompt usa só agregados, nunca o conteúdo bruto de `arguments` de chamadas de tool (pode conter dado sensível).
- Sem `agent_runs` no período, não roda o resto do pipeline (sem Gemini, sem persistência, sem notificação).

## Testes

- `_audit_log` grava `is_error` corretamente nos 4 call sites (mock, verificar o payload).
- Agregação de `agent_runs` por rotina/status com múltiplos documentos, incluindo mensagens de erro distintas limitadas a 3.
- Agregação de `mcp_audit_log` por tool com contagem, latência e taxa de erro.
- Sem `agent_runs` no período → não persiste, não chama Gemini, não notifica.
- Parse da resposta do Gemini: com proposta concreta, sem proposta (`null`), resposta cercada em markdown, resposta inválida.
- Com proposta concreta → grava em `retros_agente` E em `correcoes_pendentes` com o schema correto; sem proposta → grava só em `retros_agente`.
- Mensagem Telegram única, com e sem menção à proposta.

Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Fora de escopo

- Qualquer mudança no Motor de Evolução (`processar_correcoes_pendentes`) ou no fluxo de validação por consenso web — continua exatamente como está.
- Aplicar a proposta de POP sem passar pelo Motor de Evolução.
- Retro por rotina individual sob demanda (fica pull, via MCP, se algum dia for pedido) — este PR é só o job semanal automático.
- Dashboards ou visualizações de `retros_agente` — é só a coleção de histórico; consumo visual fica para depois, se for pedido.

## Docs

`docs/okf/arquitetura/schema-firestore.md` (novo campo `mcp_audit_log.is_error`, nova coleção `retros_agente`), `docs/okf/log.md`.
