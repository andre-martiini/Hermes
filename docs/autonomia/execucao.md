# Registro de execução — plano-hermes-autonomo-2026-09-06

Um bloco por pacote (P00–P18), no formato da seção 14.2 do plano. Cada pacote novo é acrescentado ao final; nenhum bloco anterior é reescrito depois de `validado`. Sem segredos nem conteúdo privado — apenas referências a artefatos e IDs.

**Blocos P00 a P02 sub-entrega 11/N foram movidos para
docs/autonomia/execucao-archive-p00-a-p02sub11.md em 2026-09-09 (P02
sub-entrega 15/N). Blocos P02 sub-entrega 12/N a 16/N foram movidos, em
2026-09-09 também, para um SEGUNDO arquivo de arquivo,
docs/autonomia/execucao-archive-p02-sub12-a-sub16.md — durante a correção
da sub-entrega P01 5/N, depois que uma escrita anterior derrubou
silenciosamente o bloco P02 sub-entrega 17/N na retranscrição manual de
um arquivo de 85701 bytes, e uma tentativa de reenviar tudo somado num
arquivo de arquivo só (159725 bytes) falhou por limite de saída (64000
tokens). O bloco P02 sub-entrega 17/N foi movido, também em 2026-09-09,
para um TERCEIRO arquivo de arquivo,
docs/autonomia/execucao-archive-p02-sub17.md — durante a sub-entrega P01
6/N, preventivamente. Os blocos P01 sub-entrega 3/N e 4/N foram movidos,
ainda em 2026-09-09, para um QUARTO arquivo de arquivo,
docs/autonomia/execucao-archive-p01-sub3-a-sub4.md — durante a sub-entrega
P01 7/N, também preventivamente. O bloco P01 sub-entrega 5/N foi movido,
ainda em 2026-09-09, para um QUINTO arquivo de arquivo,
docs/autonomia/execucao-archive-p01-sub5.md — durante a sub-entrega P01
8/N, preventivamente pelo mesmo motivo. Os blocos P01 sub-entrega 6/N a
9/N (fechamento do pacote) foram movidos, ainda em 2026-09-09, para um
SEXTO arquivo de arquivo, docs/autonomia/execucao-archive-p01-sub6-a-sub9.md
— durante a sub-entrega P02 19/N, preventivamente, ao registrar
retroativamente as sub-entregas P02 18/N e 19/N. Os blocos P02
sub-entrega 18/N a P03 sub-entrega 3/N foram movidos, em 2026-09-12, para
um SÉTIMO arquivo de arquivo,
docs/autonomia/execucao-archive-p02sub18-a-p03sub3.md — pela tarefa
agendada de avanço autônomo, ao registrar retroativamente a sub-entrega
P03 7/N, preventivamente (o arquivo ativo tinha passado de ~50KB sem
re-arquivamento desde o sexto arquivo). Ver o cabeçalho de cada arquivo
de arquivo para o relato completo. Os blocos P03 sub-entrega 4/N e 5/N foram
movidos, em 12/09/2026, para um OITAVO arquivo de arquivo,
docs/autonomia/execucao-archive-p03sub4-a-sub5.md — pela tarefa agendada de
avanço autônomo, ao acrescentar a entrada da sub-entrega P03 8/N,
preventivamente (o arquivo ativo passaria de ~50KB ao acrescentar essa
entrada sem re-arquivamento). Os blocos P03 sub-entrega 6/N e 7/N foram
movidos, em 13/09/2026, para um NONO arquivo de arquivo,
docs/autonomia/execucao-archive-p03sub6-a-sub7.md — pela tarefa agendada de
avanço autônomo, ao acrescentar a entrada da sub-entrega P03 10/N,
preventivamente (mesmo motivo). Os blocos P03 sub-entrega 8/N e 9/N foram
movidos, também em 13/09/2026, para um DÉCIMO arquivo de arquivo,
docs/autonomia/execucao-archive-p03sub8-a-sub9.md — pela tarefa agendada de
avanço autônomo, ao acrescentar a entrada da sub-entrega P03 11/N
(o arquivo ativo passaria de ~50KB ao acrescentar essa entrada sem
re-arquivamento). Os blocos P03 sub-entrega 10/N e 11/N foram movidos, em
14/09/2026, para um DÉCIMO PRIMEIRO arquivo de arquivo,
docs/autonomia/execucao-archive-p03sub10-a-sub11.md — pela tarefa agendada de
avanço autônomo, ao acrescentar a entrada da sub-entrega P03 13/N
(o arquivo ativo passaria de ~50KB ao acrescentar essa entrada sem
re-arquivamento). O bloco P03 sub-entrega 12/N foi movido, também em
14/09/2026, para um DÉCIMO SEGUNDO arquivo de arquivo,
docs/autonomia/execucao-archive-p03sub12.md — durante a correção do
registro do diário da sub-entrega 14/N (incidente de processo: um
subagente sem autorização abriu duas PRs indevidas para este mesmo
registro, uma delas mesclada pelo André antes da correção chegar — ver a
entrada da sub-entrega 14/N para o relato completo), preventivamente
(o arquivo ativo chegaria perto de ~50KB com as correções necessárias
sem re-arquivamento). O bloco P03 sub-entrega 13/N foi movido, em
14/09/2026, para um DÉCIMO TERCEIRO arquivo de arquivo,
docs/autonomia/execucao-archive-p03sub13.md — pela tarefa agendada de
avanço autônomo, ao acrescentar a entrada da sub-entrega P03 15/N
(o arquivo ativo passaria de ~50KB ao acrescentar essa entrada sem
re-arquivamento). Os blocos P03 sub-entrega 14/N e 15/N foram movidos,
também em 14/09/2026, para um DÉCIMO QUARTO arquivo de arquivo,
docs/autonomia/execucao-archive-p03sub14-a-sub15.md — pela tarefa
agendada de avanço autônomo, ao acrescentar a entrada da sub-entrega
P03 16/N (o arquivo ativo chegaria a 48157 bytes, perto do limite de
~50KB, sem re-arquivamento).** Nenhum conteúdo foi perdido; é
uma relocação, não uma edição. Este arquivo continua sendo a fonte de
verdade para tudo a partir da sub-entrega P03 16/N em diante.

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: d06d3c5fb0bff02ffd44b8ff136da078fa72e595
pacote: "P03 sub-entrega 16/N -- idempotentHint por handler (passo 3 do plano), primeira fatia: campo `idempotencia` classificado por leitura direta do handler real para 9 tools (4 IDEMPOTENTE, 5 NAO_IDEMPOTENTE), wired em tools/registry.py::mcp_annotations() -- fecha a pendencia deixada em aberto desde a sub-entrega 7/N (\"precisa de investigacao dedicada por HANDLER, do mesmo porte da sub-entrega 1/N\"), escolhida entre as tres opcoes deixadas pela sub-entrega 15/N (outra fatia de outputSchema exigiria levantamento novo do catalogo; idempotentHint ja tinha 9 sub-entregas de adiamento; P04 ficou para depois desta fatia)"
estado: pronto_para_revisao
inicio: "2026-09-14T18:20:00Z"
fim: "2026-09-14T21:05:35Z"
arquivos_alterados:
  - "functions/tools/inventory.py (novo enum `Idempotencia` (IDEMPOTENTE/NAO_IDEMPOTENTE) + campo `idempotencia: Idempotencia | None` em `ToolInventoryEntry`, populado para 9 tools: IDEMPOTENTE -- criar_acao_no_sistema (dedup por chave exata via claim_action_dedup_slot, TTL 15min), salvar_memoria_global (dedup por similaridade de embedding, task_type assimetrico RETRIEVAL_DOCUMENT/RETRIEVAL_QUERY), dispensar_resposta_pendente (.set() com ID deterministico), concluir_pedido_agente (transacao Firestore, already_decided); NAO_IDEMPOTENTE -- agendar_lembrete_acao, registrar_no_diario, editar_acao, resolver_item_atencao, registrar_execucao_agente (todas por append/ArrayUnion/col.add() sem chave de dedup))"
  - "functions/tools/registry.py (`mcp_annotations()` emite `idempotentHint` quando `readOnlyHint=False` E `entry.idempotencia` classificado; docstring da funcao reescrita para descrever a nova fatia, incluindo o caveat de TTL de criar_acao_no_sistema)"
  - "functions/test_action_dedup_slot.py (NOVO, 7 testes: testes diretos de main.py::claim_action_dedup_slot/store_action_dedup_result/release_action_dedup_slot -- mecanismo que zero teste cobria antes desta sub-entrega, achado da 2a rodada de revisao adversarial; prova as duas metades da classificacao de criar_acao_no_sistema -- dedup dentro da janela de TTL, ausencia de dedup fora dela)"
  - "functions/test_inbox_pendentes.py (+1 teste: dispensar() chamado duas vezes com o mesmo item_id nao duplica documento, sustenta a classificacao IDEMPOTENTE de dispensar_resposta_pendente)"
  - "functions/test_mcp_annotations.py (testes de paridade estendidos para idempotentHint; casos individuais IDEMPOTENTE/NAO_IDEMPOTENTE; ponta a ponta via tools/list; teste antigo test_annotations_nunca_leva_idempotent_hint substituido por dois testes mais precisos)"
  - "functions/test_tool_inventory.py (+3 testes de consistencia para o campo idempotencia: enum valido ou ausente, nunca classificado para leitura pura, sempre exige nota explicando a evidencia)"
decisoes:
  - id: p03-sub16-escopo-9-de-59-tools-nao-leitura
    motivo: "59 tools do catalogo sao ESCRITA ou LEITURA_E_ESCRITA (o universo elegivel -- idempotentHint so faz sentido quando readOnlyHint=False, mesma convencao ja usada para destructiveHint). Investigar as 59 de uma vez, no mesmo porte exaustivo da sub-entrega 1/N (inventario original), seria uma fatia grande e arriscada -- contra a disciplina de preferir 'uma fatia pequena e bem verificada'. Escolhido um primeiro lote de 9 com evidencia solida e sem ambiguidade genuina, deixando as ~50 restantes como pendencia explicita para fatias futuras -- mesmo padrao incremental ja usado para dominio_rede (sub-entrega 7/N, 21 de 28 tools com rede) e outputSchema (uma tool por sub-entrega desde a 8/N)."
    autoridade: existente_ou_nova
  - id: p03-sub16-revogar-promocao-autonomia-deliberadamente-fora
    motivo: "revogar_promocao_autonomia foi investigada e DESCARTADA desta fatia: repetir a chamada apos o primeiro sucesso devolve erro (tipo ja nao esta mais em tipos_promovidos), nao um 'OK' silencioso -- ambiguo se isso conta como IDEMPOTENTE (o AMBIENTE nao muda mais na segunda chamada, mas a RESPOSTA observavel muda de sucesso para erro). Mesmo criterio ja usado em dominio_rede para deixar tools genuinamente ambiguas sem classificacao (`idempotencia=None`) em vez de arriscar um hint errado -- 'um hint errado e pior que a omissao' (docstring de mcp_annotations)."
    autoridade: existente_ou_nova
  - id: p03-sub16-criar-acao-dedup-com-ttl-nao-e-idempotencia-sem-limite
    motivo: "criar_acao_no_sistema dedupla via claim_action_dedup_slot (main.py), mas o slot expira em ttl_minutes=15 (padrao). Classificado IDEMPOTENTE mesmo assim -- e o uso pretendido pelo proprio codigo (comentario no handler: 'evitar criar a mesma acao duas ou tres vezes quando o modelo chama esta tool mais de uma vez para o mesmo pedido', ou seja, a janela de retry, nao uma garantia permanente) -- mas o caveat do TTL fica explicito tanto na `nota` do inventario quanto no docstring de `mcp_annotations`, para nenhum cliente MCP inferir uma garantia mais forte do que a tool de fato oferece."
    autoridade: existente_ou_nova
  - id: p03-sub16-achado-rodada2-zero-testes-de-handler-para-idempotencia
    motivo: "2a rodada de revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao): achou que NENHUMA das 4 classificacoes IDEMPOTENTE tinha teste de HANDLER dedicado -- a classificacao inteira se apoiava em leitura de codigo, nunca em comportamento executado (claim_action_dedup_slot, em particular, nao tinha NENHUM teste em toda a suite antes desta sub-entrega). Corrigido para 2 das 4: novo functions/test_action_dedup_slot.py (7 testes) para criar_acao_no_sistema, +1 teste em test_inbox_pendentes.py para dispensar_resposta_pendente. A 3a (salvar_memoria_global) ficou com o gap DOCUMENTADO na propria nota do inventario em vez de corrigido -- mockar embedding Gemini + o classificador de retencao LLM nao tem nenhum precedente na suite hoje, e um mock construido as pressas correria o risco de nao refletir o comportamento real da API. A 4a (concluir_pedido_agente) ja tinha cobertura indireta suficiente via os testes existentes de agent_requests.py."
    autoridade: existente_ou_nova
  - id: p03-sub16-achado-rodada3-embeddings-assimetricos-nota-corrigida
    motivo: "3a rodada de revisao adversarial (sobre a correcao da rodada 2, sem contexto de nenhuma rodada anterior): achou que a nota de salvar_memoria_global alegava que repetir o MESMO fato produz 'o mesmo embedding' -- FALSO. `_save_memory_node` (main.py) embeda com task_type='RETRIEVAL_DOCUMENT' para gravar; `_find_similar_memory_nodes` (chamada na repeticao) embeda o MESMO texto com task_type='RETRIEVAL_QUERY' -- par assimetrico por desenho de modelos de recuperacao, os dois vetores nao sao identicos. Confirmado lendo `get_embedding`/`_find_similar_memory_nodes`/`_save_memory_node` linha a linha. Nota reescrita para descrever a protecao real (duas camadas: similaridade cruzada query-vs-document tipicamente alta o bastante para passar do piso de 0.90, MAIS um fallback de texto exato uma vez que esse piso e cruzado) e o risco residual honesto (se a similaridade cruzada do MESMO texto cair abaixo de 0.90, um no novo seria criado -- nao demonstrado, nao descartado, sem teste de handler para excluir)."
    autoridade: existente_ou_nova
  - id: p03-sub16-achado-rodada4-editar-acao-causa-primaria-errada
    motivo: "4a rodada de revisao adversarial (sem contexto de nenhuma rodada anterior): achou que a nota de editar_acao atribuia a nao idempotencia SO ao caminho opcional de motivo_adiamento/motivo -- mas `main.py::confirmarEdicaoAcao` (chamado por TODA chamada de editar_acao via _via_callable) ja monta seu PROPRIO diary_entry com timestamp novo e faz ArrayUnion em TODA chamada bem-sucedida, incondicionalmente, independente de motivo estar presente. A nao idempotencia existe mesmo SEM motivo. Nota corrigida para nomear o append incondicional de confirmarEdicaoAcao como razao primaria, com o append de motivo (que usa o mesmo padrao ArrayUnion mas inline em tools/hermes_tools.py, nao uma chamada literal a registrar_no_diario) como uma SEGUNDA causa adicional, nao a unica."
    autoridade: existente_ou_nova
  - id: p03-sub16-rodada5-sem-achado-parada
    motivo: "5a rodada de revisao adversarial (Agent tool, general-purpose, sem contexto de nenhuma rodada anterior): releu a correcao da rodada 4 (editar_acao) contra o codigo real, re-derivou do zero 3 das 9 classificacoes que nenhuma rodada anterior tinha re-derivado independentemente (agendar_lembrete_acao, concluir_pedido_agente, resolver_item_atencao), conferiu o caveat de TTL no docstring de mcp_annotations contra o default real de claim_action_dedup_slot, e rodou a suite completa dos 4 arquivos de teste tocados. Nao achou nada novo. Criterio de parada atingido -- relatado aqui como resultado valido, sem inventar achado para parecer completo."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo, clonado publicamente via git clone do repositorio)"
    - "python3 -m unittest test_mcp_annotations test_tool_inventory test_action_dedup_slot test_inbox_pendentes -v (arquivos isolados, repetido apos cada rodada de correcao)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, baseline antes da implementacao e depois de cada rodada de revisao)"
  resultados:
    - "Baseline (origin/main, commit d06d3c5, PR #268 ja mesclada): 1894/1894, 0 falhas, 0 erros."
    - "Arquivos isolados apos a implementacao completa + as 5 rodadas de revisao/correcao: 133/133, 0 falhas, 0 erros (test_mcp_annotations + test_tool_inventory + test_action_dedup_slot + test_inbox_pendentes)."
    - "Suite completa apos toda a implementacao e as 5 rodadas de revisao: 1910/1910, 0 falhas, 0 erros, sem regressao (1894 baseline + 16 novos)."
    - "Verificacao de nao-vacuidade da 2a rodada de revisao (fake Firestore de test_action_dedup_slot.py de fato pega um handler quebrado): claim_action_dedup_slot temporariamente alterado para sempre devolver ('proceed', None) sem dedup -- 3 dos 7 testes FALHARAM exatamente como esperado (dedup, variacao de maiuscula/espaco, concorrencia pendente); revertido com git checkout, suite voltou a 1910/1910."
evidencias:
  - "5 rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou de rodadas anteriores) -- ver decisoes para o relato completo e honesto de cada achado. Rodada 1 sem achado; rodadas 2, 3 e 4 acharam algo real em sequencia (gap de teste de handler; embeddings assimetricos; causa primaria errada de editar_acao); rodada 5 nao achou nada -- parada aqui, conforme a disciplina (escalar so enquanto uma rodada acha algo real)."
  - "Sanity check do PR: changed_files=6, additions=483, deletions=44 no retorno de argos_criar_pr_repositorio -- bate exatamente com os 6 arquivos deliberadamente alterados (inventory.py, registry.py, test_action_dedup_slot.py [novo], test_inbox_pendentes.py, test_mcp_annotations.py, test_tool_inventory.py), nenhum arquivo extra ou nao intencional no diff."
  - "Os 6 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio (delegado a um subagente dedicado, com as mesmas instrucoes de integridade desta skill) com o `sha` retornado por cada escrita comparado contra `git hash-object` local -- bateu de primeira nos 6. Verificacao adicional, independente do proprio retorno do Argos: `git fetch` do branch remoto + `git diff` contra `origin/<branch>` comparado byte a byte com o diff local capturado antes das escritas -- identicos."
  - "PR #269 aberta (https://github.com/andre-martiini/Hermes/pull/269), com o relato completo das 5 rodadas de revisao e dos testes no corpo. NAO mesclada -- aguardando o Andre."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "ABERTA: PR #264 (aberta por engano durante a correcao do diario da sub-entrega 14/N) continua aberta com um bug real de escaping YAML -- deve ser fechada sem mesclar pelo Andre; nao ha tool de fechamento de PR disponivel via Argos."
  - "ABERTA, deliberadamente: idempotentHint para as ~50 tools de escrita/leitura_e_escrita restantes continua fora de escopo -- proxima fatia natural. revogar_promocao_autonomia foi investigada e deliberadamente deixada sem classificacao por ambiguidade genuina (ver decisoes) -- candidata a revisitar se o proprio conceito de 'idempotente com efeito colateral so na primeira chamada' for melhor definido."
  - "ABERTA, deliberadamente: salvar_memoria_global continua sem teste de HANDLER dedicado (documentado na propria nota do inventario) -- mockar embedding Gemini + o classificador de retencao LLM exigiria construir o primeiro precedente de mock desse tipo na suite; nao feito nesta sub-entrega para nao arriscar um mock que nao reflita o comportamento real da API."
  - "ABERTA, deliberadamente: outputSchema para as ~99 tools restantes do catalogo continua fora de escopo -- nenhuma investigada nesta sub-entrega (o proximo levantamento do catalogo, se essa frente for retomada, ainda esta por fazer)."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante; inconsistencia de criterio nao-bloqueante em 5 das 7 tools sem dominio_rede classificado (sub-entrega 7/N); campo `ordem` de consultar_lista_compras sem coercao de tipo, colecao shopping_items com multiplos escritores nao auditados (sub-entrega 10/N); duplicacao de `_to_iso` entre agent_requests.py e agent_runs.py (sub-entrega 12/N); lacuna de structuredContent nos caminhos de _text_result fora de confirmar_acao (heranca das sub-entregas 8/N-13/N); flag `ctx.mcp_confirmed_tool_execucao_falhou` so distingue 'levantou excecao' de 'resultado bate com a forma real' (sub-entrega 13/N)."
proximo_pacote: "P03 -- PR #269 (idempotentHint, primeira fatia de 9 tools) aberta, aguardando revisao e merge do Andre. Depois de mesclada: a proxima execucao agendada deve escolher entre (a) mais uma fatia de idempotentHint para as ~50 tools de escrita restantes; (b) um levantamento NOVO do catalogo para retomar outputSchema (nenhuma candidata pronta na fila); ou (c) perguntar ao Andre se prefere avancar direto para P04 (pedidos duraveis/lease/ledger) -- com idempotentHint tendo saido do papel nesta sub-entrega e outputSchema com sete tools entregues, a opcao (c) continua cada vez mais razoavel a cada sub-entrega que passa dentro do passo 3 do P03. A cargo da execucao autonoma agendada, salvo nova prioridade do Andre. NOTA DE PROCESSO: PR #264 continua aberta e precisa ser fechada manualmente pelo Andre (sem tool de fechamento via Argos) -- ver pendencias."
```
