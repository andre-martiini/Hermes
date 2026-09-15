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
estado: validado
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
  - "PR #269 aberta (https://github.com/andre-martiini/Hermes/pull/269), com o relato completo das 5 rodadas de revisao e dos testes no corpo. MESCLADA pelo Andre (confirmado pela tarefa agendada de avanco autonomo de 15/09/2026, commit 99f754c em main, antes mesmo do diario desta sub-entrega -- PR #270 -- ter sido mesclado; ver bloco da sub-entrega 17/N para a confirmacao completa)."
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
proximo_pacote: "P03 -- PR #269 MESCLADA pelo Andre (commit 99f754c em main). Sub-entrega 17/N (bloco seguinte abaixo) ja avancou mais uma fatia de idempotentHint para 9 tools adicionais. NOTA DE PROCESSO: PR #264 continua aberta e precisa ser fechada manualmente pelo Andre (sem tool de fechamento via Argos) -- ver pendencias."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 5e0082a9f8dd7bc064da58a0b9f8240cfee90f25
pacote: "P03 sub-entrega 17/N -- idempotentHint por handler (passo 3 do plano), segunda fatia: campo `idempotencia` classificado por leitura direta do handler real para mais 9 tools (2 IDEMPOTENTE, 7 NAO_IDEMPOTENTE), sem mudanca na logica de emissao de tools/registry.py::mcp_annotations() (ja existente desde a sub-entrega 16/N, so o docstring foi atualizado) -- escolhida entre as opcoes deixadas pela sub-entrega 16/N (fatia envelope, catalogo novo para outputSchema, ou perguntar ao Andre sobre P04); confirmado no inicio desta execucao que a PR #269 (sub-entrega 16/N) ja tinha sido mesclada pelo Andre (commit 99f754c em main), entao esta fatia partiu de main atualizado, sem branch pendente"
estado: pronto_para_revisao
inicio: "2026-09-15T11:07:00Z"
fim: "2026-09-15T12:05:00Z"
arquivos_alterados:
  - "functions/tools/inventory.py (campo `idempotencia` populado para 9 tools: IDEMPOTENTE -- registrar_saude (upsert por dia+campo: `_gravar_por_data` consulta antes de escrever para peso/cintura; ID deterministico `COL_LOGS.document(dia)` com `merge=True` para dor/sono/calorias), consultar_investimentos (dedup permanente por tag `investimentos-decisao-{mes}` em investimentos_sync.py antes de criar a acao de rebalanceamento); NAO_IDEMPOTENTE -- registrar_transacao_financeira_publica, registrar_item_financeiro_v2, registrar_interacao_contato (todas: `.document()` com ID automatico + `.set()` incondicional, sem dedup), pausar_conversa (idempotency_key e o mcp_confirmation_id, que muda a cada confirmacao MCP -- repetir via nova confirmacao enfileira uma segunda mensagem real de WhatsApp), criar_rascunho_email (Gmail drafts().create() sem chave de idempotencia), registrar_aporte_investimento (docstring do proprio modulo: acumula ao repetir), registrar_execucao_investimento (posicao final nao muda, mas cada chamada grava uma 2a linha nao-apagavel no log de movimentos do servico externo))"
  - "functions/tools/registry.py (docstring de mcp_annotations() atualizado: contagem 9->18 tools investigadas desde 16/N+17/N, ~50->~41 restantes, nova secao descrevendo a fatia 17/N incluindo o caveat de concorrencia nao-atomica de registrar_saude/consultar_investimentos -- nenhuma mudanca na logica de emissao, ja existente desde 16/N)"
  - "functions/test_registrar_saude.py (+1 teste: test_dor_repetida_mesmo_valor_atualiza_mcp_checked_at -- prova que repetir a MESMA chamada de dor_* mantem o valor observavel igual mas muda mcp_checked_at, achado da 1a rodada de revisao adversarial)"
  - "functions/test_pausar_conversa.py (+1 teste: test_duas_confirmacoes_separadas_nao_deduplicam -- prova que duas confirmacoes MCP distintas com os mesmos argumentos de negocio geram duas tentativas reais de envio, nao dedup)"
  - "functions/test_mcp_annotations.py (5 testes existentes corrigidos porque usavam criar_rascunho_email/consultar_investimentos como exemplos de tool 'ainda nao investigada' -- trocados por criar_rascunho_whatsapp, que continua sem classificacao; 2 listas parametrizadas (IDEMPOTENTE/NAO_IDEMPOTENTE) estendidas com as 9 tools novas; +1 teste novo para o caso leitura_e_escrita+IDEMPOTENTE de consultar_investimentos, separado do loop de exact-match que passou a cobrir so as 2 tools leitura_e_escrita ainda sem classificacao)"
decisoes:
  - id: p03-sub17-escopo-9-de-41-restantes
    motivo: "Das ~50 tools de escrita/leitura_e_escrita deixadas pendentes pela sub-entrega 16/N, escolhido um segundo lote de 9 com evidencia solida e sem ambiguidade genuina -- mesmo padrao incremental ja usado para dominio_rede (sub-entrega 7/N) e para a propria fatia 1 de idempotentHint (16/N). Priorizadas tools de dominios com nota do inventario ja citando comportamento de repeticao (financas, investimentos, saude) e tools de efeito real sobre terceiro (pausar_conversa, criar_rascunho_email), deixando ~41 tools para fatias futuras."
    autoridade: existente_ou_nova
  - id: p03-sub17-registrar-execucao-investimento-nao-idempotente-apesar-de-posicao-convergir
    motivo: "investimentos.confirmar_execucao() e declarativo -- repetir NAO acumula posicao, ao contrario do aporte. Mesmo assim classificado NAO_IDEMPOTENTE: a propria docstring do modulo confirma que cada chamada 'grava uma segunda linha no log de movimentos', um efeito adicional real e persistente (nao apagavel) no servico externo. Mesmo criterio ja usado para editar_acao (sub-entrega 16/N): um append incondicional desqualifica idempotentHint mesmo quando o estado principal converge."
    autoridade: existente_ou_nova
  - id: p03-sub17-achado-rodada1-caveat-concorrencia-nao-documentado
    motivo: "1a rodada de revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao): achou que registrar_saude (peso/cintura via _gravar_por_data) e consultar_investimentos (dedup por tag em investimentos_sync.py) usam o padrao consulta-depois-escreve SEM exclusao mutua atomica (diferente de claim_action_dedup_slot, que usa create() como exclusao mutua de verdade) -- duas chamadas GENUINAMENTE CONCORRENTES (nao um retry sequencial apos resposta) poderiam, em teoria, ambas passar pela checagem antes de qualquer uma escrever, duplicando o registro/acao. Corrigido: caveat documentado nas notas de ambas as tools, classificacao IDEMPOTENTE mantida (mesmo espirito do caveat de TTL ja aceito em criar_acao_no_sistema) -- nao corrigido no codigo nesta fatia, so documentado."
    autoridade: existente_ou_nova
  - id: p03-sub17-achado-rodada1-pausar-conversa-overstatement
    motivo: "1a rodada de revisao adversarial: achou que a nota de pausar_conversa dizia que o append ArrayUnion em acompanhamento acontece 'em toda chamada bem-sucedida' -- na verdade tools/pausar_conversa.py so faz essa atualizacao quando ha acao vinculada (`if task and task_ref`), nao sempre. Corrigido para linguagem condicional; nao muda a classificacao NAO_IDEMPOTENTE (o reenvio real de WhatsApp via idempotency_key escopado por confirmacao ja e evidencia suficiente por si so)."
    autoridade: existente_ou_nova
  - id: p03-sub17-achado-rodada1-mcp-checked-at-nao-e-escrita-apenas
    motivo: "1a rodada de revisao adversarial: achou que a nota de registrar_saude alegava que o campo mcp_checked_at (dentro de pain, gravado a cada chamada de dor_* com timestamp novo) e 'escrita-apenas' (nunca lido) -- FALSO. health_tools.py::build_health_summary reencaminha o dict `pain` inteiro (mcp_checked_at incluso) para consultar_saude/Godmode, entao E observavel por um cliente MCP. Nota corrigida para reconhecer a observabilidade, mas mantendo o campo como inerte (nenhuma rotina/decisao/valor de negocio le especificamente mcp_checked_at) -- classificacao IDEMPOTENTE mantida, mesmo espirito do caveat de TTL ja aceito em criar_acao_no_sistema."
    autoridade: existente_ou_nova
  - id: p03-sub17-rodada2-achado-cosmetico-idempotencia-duplicada-na-nota
    motivo: "2a rodada de revisao adversarial (sobre as correcoes da rodada 1, sem contexto de nenhuma rodada anterior): confirmou as 3 correcoes da rodada 1 como corretas, e achou 1 problema cosmetico -- a nota de consultar_investimentos repetia textualmente 'idempotencia=IDEMPOTENTE (P03 sub-entrega 17/N)' dentro da propria string, duplicando o kwarg real `idempotencia=_I.IDEMPOTENTE`, que tambem estava fora de ordem (depois de `nota=`, nao antes, ao contrario de todas as outras 8 entradas tocadas nesta fatia). Corrigido: kwarg reordenado antes de `nota=`, prosa da nota reescrita sem repetir o nome do campo Python."
    autoridade: existente_ou_nova
  - id: p03-sub17-rodada3-sem-achado-parada
    motivo: "3a rodada de revisao adversarial (Agent tool, general-purpose, sem contexto de nenhuma rodada anterior): releu o diff inteiro do zero, re-derivou as 9 classificacoes independentemente (sem confiar nas rodadas anteriores), reconferiu a correcao cosmetica da rodada 2, e recontou programaticamente os totais do docstring de tools/registry.py (59 tools elegiveis, 18 classificadas, 41 restantes -- bateu com a prosa). Nao achou nada novo. Criterio de parada atingido -- relatado aqui como resultado valido, sem inventar achado para parecer completo."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo, clonado via git clone do repositorio)"
    - "python3 -m unittest test_registrar_saude test_pausar_conversa test_mcp_annotations test_tool_inventory test_investimentos_sync test_investimentos -v (arquivos isolados, repetido apos cada rodada de correcao)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, baseline antes da implementacao e depois de cada rodada de revisao)"
  resultados:
    - "Baseline (origin/main, commit 5e0082a, PR #269 e #270 ja mescladas): 1910/1910, 0 falhas, 0 erros."
    - "Arquivos isolados apos a implementacao completa + as 3 rodadas de revisao/correcao: 102/102, 0 falhas, 0 erros (test_registrar_saude + test_pausar_conversa + test_mcp_annotations + test_tool_inventory + test_investimentos_sync + test_investimentos)."
    - "Suite completa apos toda a implementacao e as 3 rodadas de revisao: 1913/1913, 0 falhas, 0 erros, sem regressao (1910 baseline + 3 novos)."
evidencias:
  - "3 rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou de rodadas anteriores) -- ver decisoes para o relato completo e honesto de cada achado. Rodada 1 achou 3 problemas reais (caveat de concorrencia nao documentado em 2 classificacoes IDEMPOTENTE; overstatement na nota de pausar_conversa; claim incorreto de 'escrita-apenas' em registrar_saude); rodada 2 confirmou as 3 correcoes e achou 1 problema cosmetico; rodada 3 nao achou nada -- parada aqui, conforme a disciplina (escalar so enquanto uma rodada acha algo real)."
  - "Sanity check do PR: changed_files=5, additions=187, deletions=31 no retorno de argos_criar_pr_repositorio -- bate exatamente com os 5 arquivos deliberadamente alterados (inventory.py, registry.py, test_registrar_saude.py, test_pausar_conversa.py, test_mcp_annotations.py) e com o `git diff --stat` local capturado antes do envio, nenhum arquivo extra ou nao intencional no diff."
  - "Os 5 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio (delegado a um subagente dedicado, com as mesmas instrucoes de integridade desta skill) com o `sha` retornado por cada escrita comparado contra `git hash-object` local -- 4 bateram de primeira; 1 (registry.py) teve mismatch detectado no primeiro envio (parafraseamento acidental de um paragrafo de docstring na transcricao manual), corrigido e reenviado com sucesso na segunda tentativa. Verificacao adicional, independente do proprio retorno do Argos: `git fetch` do branch remoto + `git diff` contra `origin/<branch>` para os 5 arquivos comparado com a arvore de trabalho local -- diff vazio, bytes identicos."
  - "PR #271 aberta (https://github.com/andre-martiini/Hermes/pull/271), com o relato completo das 3 rodadas de revisao e dos testes no corpo. NAO mesclada -- aguardando o Andre."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "ABERTA: PR #264 (aberta por engano durante a correcao do diario da sub-entrega 14/N) continua aberta com um bug real de escaping YAML -- deve ser fechada sem mesclar pelo Andre; nao ha tool de fechamento de PR disponivel via Argos."
  - "ABERTA, deliberadamente: idempotentHint para as ~41 tools de escrita/leitura_e_escrita restantes continua fora de escopo -- proxima fatia natural. Ver tambem a pendencia ja registrada no bloco 16/N sobre revogar_promocao_autonomia."
  - "ABERTA, deliberadamente: o caveat de concorrencia (consulta-depois-escreve sem exclusao mutua atomica) em registrar_saude e consultar_investimentos foi documentado mas NAO corrigido nesta fatia -- migrar para create()/transacao, como claim_action_dedup_slot, e trabalho futuro se o risco de chamadas genuinamente concorrentes (nao retry sequencial) se mostrar real na pratica."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: ver bloco P03 sub-entrega 16/N acima para a lista completa (religar inventario tipado a decisao de politica real; ambiguidades de classificacao; card do Telegram de rascunho degradado; observabilidade de claim pendente; TTL do Firestore para mcp_jobs; limite de 200KB do Argos; passo 2 do P02 como hardening futuro; inconsistencias nao-bloqueantes de sub-entregas 7/N, 10/N, 12/N, 13/N; salvar_memoria_global sem teste de handler dedicado; outputSchema para as ~99 tools restantes do catalogo)."
proximo_pacote: "P03 -- PR #271 (idempotentHint, segunda fatia de 9 tools) aberta, aguardando revisao e merge do Andre. Depois de mesclada: a proxima execucao agendada deve escolher entre (a) mais uma fatia de idempotentHint para as ~41 tools de escrita restantes (o padrao incremental mais estabelecido); (b) a fatia envelope restante do passo 3 do P03; (c) um levantamento NOVO do catalogo para retomar outputSchema (nenhuma candidata pronta na fila); ou (d) perguntar ao Andre se prefere avancar direto para P04 (pedidos duraveis/lease/ledger) -- com duas fatias de idempotentHint entregues (18 de 59 tools) e outputSchema com sete tools entregues, a opcao (d) continua cada vez mais razoavel a cada sub-entrega que passa dentro do passo 3 do P03. A cargo da execucao autonoma agendada, salvo nova prioridade do Andre. NOTA DE PROCESSO: PR #264 continua aberta e precisa ser fechada manualmente pelo Andre (sem tool de fechamento via Argos) -- ver pendencias."
```
