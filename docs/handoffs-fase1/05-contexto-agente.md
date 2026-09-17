# PR 5 (Fase 1) — `feat(acoes): contexto_agente auto-mantido em acoes criticas`

**Pré-requisito:** nenhum desta fase — pode ser feito em paralelo com o PR 4. Este é o último PR da Fase 1: depois dele mergeado, o critério de pronto do pacote inteiro (`docs/handoffs-fase1/00-leia-primeiro.md`) fica completo.

## Por quê

Hoje, quando uma ação crítica troca de agente (uma sessão nova do Claude, ou o Antigravity assumindo algo que a sessão anterior deixou pela metade), alguém escreve um documento de handoff à mão — o do MEC-Sustentável tinha uma página. O plano (`docs/plano-evolucao-hermes-jarvis.md`, seção 3, "contexto_agente por ação") propõe substituir isso por um campo auto-mantido: `obter_acao(id)` vira o próprio handoff, sem ninguém precisar escrever nada.

## O que é "ação crítica"

Não é um conceito novo — já existe e já é usado hoje em `inbox_pendentes.py` (`_item`, linha ~298):

```python
critica = (task["execution_lane"] == "critica") or (task["degradation_count"] >= 3)
```

Reaproveite exatamente esse critério — não invente outro. `execution_lane == "critica"` é um valor que já é aceito no campo mesmo sem ninguém escrever nele ainda hoje (comentário no próprio arquivo: "o estado atual não possui a lane 'critica' como valor canônico; aceita-a caso seja introduzida"); `degradation_count >= 3` é a mesma régua que o resumo matinal já usa para classificar degradação como crítica.

## Desenho — o mínimo que funciona

### Novo campo `tarefas.contexto_agente`

Dict, não texto livre solto (facilita tanto o consumo por `obter_acao` quanto uma extensão futura por campo):

```
{
  resumo: "o que é a ação, 1-3 frases",
  pessoas_chave: ["nome (papel/contexto)", ...],
  onde_esta_o_codigo: "repo, branch, porta do dev server — só o que estiver mencionado no texto-fonte" | null,
  ultimas_decisoes: ["decisão 1", "decisão 2", ...],
  travas: ["bloqueio 1", ...] | [],
  atualizado_em: <ISO>,
}
```

**Regra inegociável do prompt:** instrua o Gemini explicitamente a nunca inventar informação ausente — se o texto-fonte não menciona repo/branch/porta, o campo correspondente fica `null`/vazio, não um palpite. Este campo vira a fonte que um agente novo vai confiar sem verificar; um dado inventado aqui é pior que campo vazio, porque parece confiável e não é.

### Trigger que mantém o campo (mesmo padrão de `on_tarefa_written_extract_people`, `knowledge_graph.py`)

Não é lógica pura de decisão determinística como os detectores de `atencao_whatsapp.py` — aqui há sempre uma chamada de LLM pra sintetizar texto não estruturado (diário) em resumo. Siga o padrão que já existe e já funciona nesse mesmo arquivo para extração de pessoas, é o precedente mais próximo do que esta PR precisa fazer:

1. Novo trigger `@firestore_fn.on_document_written(document="tarefas/{taskId}")` em `functions/main.py` (função própria, isolada das outras — nunca uma falha aqui pode impedir `on_tarefa_written`, `on_tarefa_written_extract_people` ou `on_processo_updated` de rodar, e vice-versa).
2. Ignora tarefa com `area_tematica == "SISTEMAS"` (mesmo filtro do extrator de pessoas) e ignora tarefa que não é crítica pelo critério acima — nesse caso nem chama o Gemini (economia; não é reflexo barato como os outros, custa uma chamada de LLM).
3. Monta `full_text` a partir de título, descrição, `plano_acao` (texto das etapas) e as últimas N entradas do diário (`acompanhamento`, N generoso o bastante pra cobrir decisões recentes — 20 é razoável, mesma ordem de grandeza do `limite_diario` padrão de `obter_acao`).
4. Hash de dedupe igual ao `last_processed_people_hash`: grave `last_processed_contexto_hash` e não rechame o Gemini se o hash não mudou desde a última vez (evita reprocessar em toda escrita irrelevante da tarefa, ex.: só um campo de agenda mudou).
5. Chame o Gemini via `generate_content_logged` (`gemini_cost_controls.py`) — não a chamada crua ao client como o extrator de pessoas faz; esta é uma tool nova, comece já no caminho com telemetria de custo. Use `feature="contexto_agente"` (tag nova) e o mesmo `GEMINI_STRUCTURED_MODEL` usado pelas outras extrações estruturadas do arquivo.
6. Parse da resposta: mesmo padrão defensivo do extrator de pessoas — tenta regex de objeto JSON primeiro, cai para strip de cerca de código markdown se não achar. Se o parse falhar ou vier vazio, não grave nada (mantenha o `contexto_agente` anterior, se houver) e apenas grave o hash pra não tentar de novo até o conteúdo mudar.
7. Grave `contexto_agente` (o dict) e `last_processed_contexto_hash` na própria tarefa via `update()`.

### `obter_acao` inclui o campo (uma linha)

Em `functions/tools/hermes_tools.py::obter_acao`, adicione `"contexto_agente": d.get("contexto_agente")` ao dict de retorno (tarefa não-crítica ou ainda não processada: vem `None`, e tudo bem — o resto da resposta de `obter_acao` já é completo o suficiente pra essas).

## Travas

- Mão única: o diário e o `plano_acao` são a fonte de verdade; `contexto_agente` é derivado deles, nunca o contrário. Este PR nunca escreve em `acompanhamento` nem em `plano_acao` a partir do resumo.
- Falha ao gerar o resumo (Gemini fora do ar, parse falhou, API key ausente) nunca pode impedir a escrita normal da tarefa — o trigger roda depois da escrita (`on_document_written`), então isso já é estrutural, mas garanta que a função em si não propague exceção pro Firebase (log e retorna, como o extrator de pessoas já faz).
- Não gaste chamada de Gemini em tarefa não-crítica — o filtro do passo 2 vem antes de qualquer I/O de LLM.
- Não mude a definição de "o que é ação crítica" em nenhum outro lugar do sistema (UI pra marcar `execution_lane: critica` manualmente, por exemplo) — fora desta PR.

## Testes

- Função pura de decisão "é crítica?" (mesmo critério de `inbox_pendentes.py`) testável isolada.
- Montagem do `full_text` e do hash: testável sem Firestore nem Gemini.
- Parse da resposta do Gemini (JSON limpo, JSON com cerca de código markdown, resposta vazia, resposta inválida) — mock da chamada, sem rede de verdade.
- Teste leve confirmando que tarefa não-crítica ou `area_tematica == "SISTEMAS"` não chama o Gemini (evita custo de teste e documenta a trava).
- `test_hermes_tools.py`: `obter_acao` inclui `contexto_agente` quando presente e `None` quando ausente.

Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Fora de escopo

- UI ou tool pra marcar uma ação como crítica manualmente — a lane já existe, só não tem escritor hoje; dar um escritor a ela é discussão separada.
- Editar `contexto_agente` manualmente via tool MCP — é só leitura (dentro de `obter_acao`), gerado e mantido pelo trigger.
- Rodar isso para ações não-críticas, mesmo que "seria bom ter" — o critério de pronto da fase pede especificamente ações críticas.

## Docs

`docs/okf/arquitetura/schema-firestore.md` (novo campo `tarefas.contexto_agente` e `tarefas.last_processed_contexto_hash`), `docs/okf/copiloto/mcp-servidor.md` (nota de que `obter_acao` agora devolve `contexto_agente` quando a ação é crítica), `docs/okf/log.md`.

---

Com este PR mergeado e verificado, a Fase 1 do plano está completa (critério de pronto do pacote, `00-leia-primeiro.md`). Aviso quando chegar lá — o próximo passo é planejar os handoffs da Fase 2.
