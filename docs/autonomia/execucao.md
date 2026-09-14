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
re-arquivamento).** Nenhum conteúdo foi perdido; é
uma relocação, não uma edição. Este arquivo continua sendo a fonte de
verdade para tudo a partir da sub-entrega P03 14/N em diante.

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 9979bedadf30de4fa16a548f38f8e2969c7c6062
pacote: "P03 sub-entrega 14/N -- outputSchema/structuredContent (passo 3 do plano), sexta fatia: contrato de dados publicado em tools/list e refletido em tools/call para consultar_historico_acoes, apos calculadora (sub-entrega 8/N), buscar_contato (sub-entrega 9/N), consultar_lista_compras (sub-entrega 10/N), consultar_execucoes_agente (sub-entrega 11/N) e consultar_pedidos_agente (sub-entrega 12/N) -- primeira tool do catalogo a usar `oneOf`, fechando a pendencia deixada pelas sub-entregas 12/N e 13/N"
estado: validado
inicio: "2026-09-14T12:20:00Z"
fim: "2026-09-14T13:54:00Z"
arquivos_alterados:
  - "functions/tools/registry.py (nova entrada `_OUTPUT_SCHEMAS['consultar_historico_acoes']` -- PRIMEIRO uso de `oneOf` no catalogo: sucesso `{total_retornado: int, resultados: [...], filtros: {...}}` OU erro `{erro: str, resultados: []}`, `required` disjuntos nas duas formas; item de `resultados` com 15 campos sempre presentes, `id`/`criado_em`/`plano_acao`/`acompanhamento_recente` com garantia forte de tipo, sete campos restantes crus/nao-bloqueantes; `filtros` eco dos argumentos de entrada, `query` sempre string, os quatro demais `[string, null]`)"
  - "functions/tools/hermes_tools.py (novo helper `_filtro_str_ou_none`, aplicado SO na montagem do `filtros` do retorno de `_consultar_historico_acoes` -- nunca nos parametros passados para `busca_grafo.buscar_tarefas`, ver decisoes)"
  - "functions/test_output_schema.py (11 testes novos: schema oneOf com sucesso/erro, publicacao em tools/list, tres cenarios de integracao structuredContent -- sucesso, lista vazia, erro -- paridade campo a campo contra o branch oneOf correto, e uma quinta frente nova, TestConsultarHistoricoAcoesFiltrosCoercao, com 5 testes que chamam o HANDLER REAL, nao um mock do mecanismo)"
decisoes:
  - id: p03-sub14-oneof-primeira-vez-no-catalogo
    motivo: "consultar_historico_acoes (tools/hermes_tools.py::_consultar_historico_acoes, sobre tools/busca_grafo.py::buscar_tarefas) tem duas formas de nivel superior com required DISJUNTOS -- sucesso (total_retornado/resultados/filtros) ou erro (erro/resultados, sempre lista vazia hardcoded pelo proprio handler, independente do que buscar_tarefas devolveu em erro). Decidido usar oneOf com as duas formas COMPLETAS (cada uma com seu proprio required/additionalProperties:False) em vez de uma forma unica com tudo fora de required -- a alternativa aceitaria hibridos invalidos (erro e filtros juntos) que o handler real nunca produz. Fecha a pendencia das sub-entregas 12/N e 13/N."
    autoridade: existente_ou_nova
  - id: p03-sub14-achado-rodada1-filtros-tipo-nao-coagido
    motivo: "1a rodada de revisao adversarial (Agent tool, general-purpose, sem contexto): achou que area_tematica/status/data_limite_inicio/data_limite_fim (ecoados em filtros) eram args.get(campo) CRU, sem coercao -- um chamador MCP mandando area_tematica:5 ou status:[\"a\",\"b\"] (o schema de tools/list nao valida tipo escalar em runtime) fazia esse valor vazar sem coercao, violando o [string,null] declarado. Reproduzido de verdade, nao hipotetico. Corrigido com _filtro_str_ou_none."
    autoridade: existente_ou_nova
  - id: p03-sub14-achado-rodada2-coercao-nao-pode-tocar-busca
    motivo: "2a rodada de revisao adversarial, sobre a correcao da rodada 1: a 1a versao do fix aplicava _filtro_str_ou_none tambem aos parametros passados para buscar_tarefas, o que mudaria comportamento de busca real -- valores falsy-mas-nao-None (False, []) viram string TRUTHY (\"False\", \"[]\") apos str(), e varios pontos de busca_grafo.py (_matches_filters, o gate antes da query ao Firestore) decidem por truthiness pura da MESMA variavel se aplicam um filtro. Confirmado ao vivo: buscar_tarefas(\"\", status=False) ia de 2 resultados (comportamento correto hoje) para 0 depois da troca. Corrigido: a coercao fica SO na montagem do filtros de saida, os parametros de busca continuam recebendo os valores crus originais -- ver TestConsultarHistoricoAcoesFiltrosCoercao.test_busca_recebe_valores_crus_nao_coagidos."
    autoridade: existente_ou_nova
  - id: p03-sub14-rodadas-3-e-4-correcoes-de-comentario
    motivo: "3a rodada achou 4 imprecisoes factuais no comentario/docstring (nao na logica): contagem de campos errada (14 em vez de 15 chaves de _formatar_resultado), alegacao de que um valor truthy nao-string em descricao/notas/sintese_demanda sempre levantaria TypeError (falso para sequencias -- list/tuple/bytes/range sobrevivem ao slice silenciosamente, so escalares nao-fatiaveis levantam), referencia a nome de teste que nao batia com o nome real, e contagem desatualizada de tools sem schema (101 das 106, deveria ser 100 das 106 apos esta sexta entrada). 4a rodada achou mais uma: o comentario dizia que os sete campos crus usam data.get(campo, \"\"), mas titulo usa data.get(\"titulo\", \"sem titulo\"). Todas corrigidas no proprio comentario, forward-only."
    autoridade: existente_ou_nova
  - id: p03-sub14-rodada5-sem-achado-parada
    motivo: "5a rodada de revisao adversarial (Agent tool, general-purpose, sem contexto de nenhuma rodada anterior), releitura fresca de todo o diff: nao achou nada novo. Criterio de parada atingido (escalar so enquanto uma rodada acha algo real; a 5a nao achou nada, relatado aqui como resultado valido)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo, clonado publicamente via git clone do repositorio)"
    - "python3 -m unittest test_output_schema -v (arquivo isolado)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, antes e depois da implementacao, e novamente apos cada uma das 5 rodadas de revisao/correcao)"
    - "Verificacao de nao-vacuidade (2x): reversao temporaria de cada correcao (coercao do filtros; isolamento da coercao dos parametros de busca), rodando os testes de regressao correspondentes isoladamente, seguida de restauracao e nova rodada da suite completa"
  resultados:
    - "Baseline (origin/main, commit 9979bed, PR #259 ja mesclada): 1859/1859, 0 falhas, 0 erros."
    - "Arquivo isolado test_output_schema.py apos a implementacao completa (schema oneOf + as duas correcoes de comportamento + as correcoes de comentario): 45/45, 0 falhas, 0 erros."
    - "Suite completa apos toda a implementacao e as 5 rodadas de revisao: 1870/1870, 0 falhas, 0 erros, sem regressao (1859 baseline + 11 novos)."
    - "Verificacao de nao-vacuidade 1 (coercao do filtros): com a correcao revertida (_filtro_str_ou_none virando identidade), 2 dos 4 testes de TestConsultarHistoricoAcoesFiltrosCoercao FALHARAM exatamente como esperado; com a correcao restaurada, os 4 voltaram a passar."
    - "Verificacao de nao-vacuidade 2 (isolamento da coercao dos parametros de busca): com a coercao reaplicada tambem aos parametros de busca (reproduzindo a 1a versao do fix, achado da rodada 2), test_busca_recebe_valores_crus_nao_coagidos FALHOU exatamente como esperado (`'[]' != []`); com o isolamento restaurado, voltou a passar."
    - "Suite completa rodada tambem contra um checkout publico real do branch remoto (git clone -b claude/p03-sub14-output-schema-historico-acoes), nao so o arquivo local editado: 1870/1870."
evidencias:
  - "5 rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou de rodadas anteriores) -- ver decisoes para o relato completo e honesto de cada achado. 3 rodadas acharam algo real (1: vazamento de tipo no filtros; 2: coercao vazando para o comportamento de busca; 3: quatro imprecisoes de comentario), 1 achou mais uma imprecisao de comentario (rodada 4), a ultima (5) nao achou nada -- parada aqui, conforme a disciplina."
  - "Sanity check do PR: changed_files=3, additions=651, deletions=27 no retorno de argos_criar_pr_repositorio -- bate exatamente com os 3 arquivos deliberadamente alterados (registry.py, hermes_tools.py, test_output_schema.py), nenhum arquivo extra ou nao intencional no diff."
  - "Os 3 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio (delegado a um subagente dedicado, com as mesmas instrucoes de integridade desta skill) com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 3 batendo de primeira. Verificacao adicional, independente do proprio retorno do Argos: git fetch do branch remoto (refspec explicito) + git diff/hash comparando cada arquivo contra origin/<branch> -- diff vazio, identico byte a byte nos 3 arquivos. Suite completa tambem rodada contra um checkout publico real do branch remoto, 1870/1870."
  - "PR #262 aberta (https://github.com/andre-martiini/Hermes/pull/262), com o relato completo das 5 rodadas de revisao e das duas verificacoes de nao-vacuidade no corpo."
  - "CONFIRMACAO POSTERIOR (14/09/2026, mesma sessao, ao corrigir o registro deste diario apos um incidente de processo -- ver pendencias): PR #262 mesclada pelo Andre -- confirmado por `git fetch`/`git log --oneline origin/main`, commit `b60bcc5af21372bd76278745b88b2ee089b5f878` presente na historia de `main` (mensagem: \"P03 sub-entrega 14/N: outputSchema/structuredContent para consultar_historico_acoes (primeiro oneOf do catalogo) (#262)\"). Estado desta entrada atualizado de `pronto_para_revisao` para `validado` nesta mesma sessao, sem reescrever nenhum outro campo do bloco -- mesmo padrao ja usado nas sub-entregas 8/N a 12/N."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por confirmacao posterior (ver evidencias): PR #262 mesclada; esta entrada passou de pronto_para_revisao para validado."
  - "RESOLVIDO, incidente de processo registrado para o historico: o registro deste diario no Argos teve 3 tentativas. Um subagente que eu tinha instruido apenas a escrever e verificar este arquivo abriu, sem autorizacao, duas PRs (nao pedidas): PR #263 (da branch com uma escrita anterior que expos uma flakiness real do conector Argos em escritas grandes -- silenciosamente derrubava algumas ocorrencias de `\\\"` em tentativas diferentes do MESMO conteudo -- e deixou um arquivo de diagnostico esquecido, docs/autonomia/_escape_test.md) e PR #264 (de uma segunda branch, com o bug de escaping de fato manifestado, quebrando o parsing YAML de varios blocos). As duas foram comentadas pedindo para o Andre fechar sem mesclar, e uma terceira PR limpa e verificada byte a byte (#265) foi aberta a partir de uma branch nova. O Andre mesclou a PR #263 antes de ver os comentarios -- o conteudo dela (verificado aqui: o hash bate com a versao que a investigacao ja tinha confirmado limpa antes do bug de flakiness aparecer nas tentativas seguintes) NAO esta corrompido, so desatualizado (estado `pronto_para_revisao` em vez de `validado`, sem a confirmacao de merge da PR #262, sem a nota sobre a PR #260 e sem o aviso de tamanho do arquivo). Este bloco aqui e a CORRECAO, escrita direto sobre o main atual (pos-#263), sem reescrever nenhum campo alem de `estado`/`evidencias`/`pendencias`. PR #264 continua aberta e deve ser fechada sem mesclar (tem o bug de escaping de verdade). O arquivo de diagnostico `docs/autonomia/_escape_test.md`, que entrou em main via a PR #263, e inofensivo (so um comentario dizendo que e um artefato de diagnostico esquecido) mas nao deveria estar la -- fica registrado aqui para o Andre remover manualmente se quiser um diff limpo, ja que nao ha tool de exclusao de arquivo disponivel via Argos."
  - "ABERTA, nova: PR #260 (\"fix(knowledge_graph): cache de perfil_pessoas no fallback\") foi mesclada em main na mesma janela desta sub-entrega, por fora deste plano -- so registrado aqui para o historico, sem relacao com esta sub-entrega nem necessidade de acao."
  - "ABERTA, deliberadamente: outputSchema para as demais ~100 tools do catalogo continua fora de escopo. Candidatas levantadas nas sub-entregas 12/N-13/N e ainda nao investigadas a fundo: obter_acao (23 campos, maioria sem coercao, duas formas de erro diferentes), preparar_edicao_acao, preparar_edicao_em_lote, gerar_rascunho_formulario, preparar_reagendamento_em_lote, preparar_remocao_horarios_em_lote -- lista nao fechada, ponto de partida para a proxima fatia."
  - "ABERTA, deliberadamente (herdada da sub-entrega 7/N): idempotentHint continua fora de escopo -- precisa de investigacao dedicada por HANDLER, nenhum campo do inventario atual registra isso."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante; inconsistencia de criterio nao-bloqueante em 5 das 7 tools sem dominio_rede classificado (sub-entrega 7/N); campo `ordem` de consultar_lista_compras sem coercao de tipo, colecao shopping_items com multiplos escritores nao auditados (sub-entrega 10/N); duplicacao de `_to_iso` entre agent_requests.py e agent_runs.py (sub-entrega 12/N); lacuna de structuredContent nos caminhos de _text_result fora de confirmar_acao (heranca das sub-entregas 8/N-13/N)."
proximo_pacote: "P03 -- PR #262 (outputSchema/oneOf para consultar_historico_acoes) ja mesclada pelo Andre. A proxima execucao agendada deve escolher entre (a) outputSchema para obter_acao (unica candidata restante do levantamento das sub-entregas 12/N-13/N, mais trabalhosa -- 23 campos, duas formas de erro); (b) a investigacao dedicada de idempotentHint por handler (fora de escopo ha 7 sub-entregas); ou (c) perguntar ao Andre se prefere avancar direto para P04 (pedidos duraveis/lease/ledger), dado que o passo 2 do P03 esta totalmente fechado e o passo 3 ja tem seis fatias de outputSchema mais a fatia envelope entregues -- a cargo da execucao autonoma agendada, salvo nova prioridade do Andre. NOTA DE TAMANHO: este arquivo esta perto de ~50KB apos este bloco -- a proxima sub-entrega a acrescentar um bloco novo deve arquivar entradas antigas (ver cabecalho do arquivo para o padrao) ANTES de escrever, pelo mesmo motivo preventivo ja usado nas rodadas anteriores de arquivamento. NOTA DE PROCESSO: PR #264, aberta por engano na correcao deste diario, continua aberta com um bug real de escaping YAML -- deve ser fechada sem mesclar (ver pendencias)."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: a68d55466410260eed41622a1f36f500b598da27
pacote: "P03 sub-entrega 15/N -- outputSchema/structuredContent (passo 3 do plano), setima fatia: contrato de dados publicado em tools/list e refletido em tools/call para obter_acao, apos calculadora (8/N), buscar_contato (9/N), consultar_lista_compras (10/N), consultar_execucoes_agente (11/N), consultar_pedidos_agente (12/N) e consultar_historico_acoes (14/N) -- candidata mais trabalhosa levantada nas sub-entregas 12/N-13/N (23-24 campos, duas formas de erro)"
estado: pronto_para_revisao
inicio: "2026-09-14T16:00:00Z"
fim: "2026-09-14T17:52:21Z"
arquivos_alterados:
  - "functions/tools/registry.py (`_OUTPUT_SCHEMAS['obter_acao']` -- oneOf com 2 ramos: sucesso (24 campos de nivel superior, o maior contrato do catalogo ate agora) e erro (`erro` obrigatorio, `status` opcional -- colapsa os 2 `return` de erro reais do handler, que diferem so pela presenca desse campo). Docstring de `output_schema` atualizada: 99 das 106 tools sem contrato, apos a setima entrada.)"
  - "functions/test_output_schema.py (6 testes novos/ajustados: `test_obter_acao_tem_schema_oneof_sucesso_e_erro` (forma completa do schema), `test_paridade_sete_tools_tem_output_schema_hoje` (renomeado de 'seis' para 'sete', substitui o antigo teste de paridade), `test_obter_acao_publica_output_schema` + ajuste de `test_nenhuma_outra_tool_publicada_tem_output_schema`/`test_output_schema_nao_interfere_no_resto_do_tool_entry` (ponta a ponta via tools/list), `test_obter_acao_sucesso_leva_structured_content_igual_ao_content`/`test_obter_acao_nao_encontrada_tambem_leva_structured_content`/`test_obter_acao_sem_task_id_tambem_leva_structured_content`/`test_obter_acao_structured_content_bate_com_o_output_schema_publicado` (ponta a ponta via tools/call, executor mockado); `test_tool_sem_contrato_devolve_none` perdeu `obter_acao` da lista de tools sem schema)"
decisoes:
  - id: p03-sub15-oneof-erro-unico-nao-tres-ramos
    motivo: "obter_acao (tools/hermes_tools.py::obter_acao) tem 3 `return` no total, nao 2: `{\"erro\": \"Informe task_id.\"}` (sem task_id, nem proprio nem de ctx.task_id), `{\"erro\": \"...\", \"status\": \"not_found\"}` (doc inexistente), e a forma de sucesso. Investigado se isso justificava oneOf de 3 ramos (como as duas formas de erro de fato tem `required` diferentes -- uma so tem `erro`, a outra tem `erro`+`status`). Decidido que NAO: a diferenca entre as duas e so a PRESENCA OPCIONAL de um campo com um unico valor possivel (`status: \"not_found\"`), o mesmo padrao ja usado para campo condicional dentro de UM ramo (`truncado` em consultar_lista_compras), nao um formato alternativo genuino como o `oneOf` de consultar_historico_acoes (sub-entrega 14/N) modela. Um erro com `status` fora de `required` aceita as duas formas reais sem aceitar nenhuma hibrida que o handler nao produz (nunca ha um terceiro valor de status, nem status sem erro)."
    autoridade: existente_ou_nova
  - id: p03-sub15-oito-fontes-de-plano-acao-investigadas
    motivo: "plano_acao (a parte mais trabalhosa desta sub-entrega): busca exaustiva por escritas de `\"plano_acao\":` na colecao `tarefas` encontrou 8 pontos (main.py, telegram_utils.py, telegram_callbacks_confirmacoes.py, telegram_message_tools.py x2, tools/pausar_conversa.py, tools/hermes_tools.py, tools/telegram_extended.py, investimentos_sync.py) -- 7 deles chamam `subtarefas.converter_plano` ou `subtarefas.mesclar_plano`, que SEMPRE terminam em `subtarefas.normalizar` antes de persistir (garantindo `id` string nao-vazia, `estado` num dos 4 valores de `ESTADOS`, `aguardando_de` string ate 200 chars quando presente, `degradation_count` int quando presente). O OITAVO, `tools/pausar_conversa.py`, monta a etapa de pausa a mao (bypassa `normalizar`), mas os valores literais que grava (`id` via `uuid.uuid4()[:8]`, `estado=\"aguardando_terceiro\"`, `aguardando_de=\"André\"`) batem com os mesmos tipos -- documentado como caminho paralelo, nao generalizado como 'todo escritor passa por normalizar'."
    autoridade: existente_ou_nova
  - id: p03-sub15-id-etapa-nullable-por-risco-legado
    motivo: "`id` da etapa e `i.get(\"id\")` CRU dentro do proprio `obter_acao`, sem passar por `estado_de`/`texto_de` (que tem garantia forte independente de quem escreveu, inclusive para documento legado sem `estado`). Documento anterior a `subtarefas.py` (2026-08-26, ver docstring do modulo: \"subtarefa era texto com marcador de concluida\") pode ter etapa em formato dict sem `id` nenhum, nunca tocada por `mesclar_plano`/`converter_plano` desde entao -- por isso `id` da etapa tem `null` no tipo, diferente do `id` de nivel superior (`snap.id`, sempre garantido pelo SDK do Firestore). Mesma categoria de risco (nao demonstrado, so nao descartado) aplicada tambem a `nome`/`link` dos anexos, por precaucao contra item de `pool_dados` anterior aos 4 escritores encontrados."
    autoridade: existente_ou_nova
  - id: p03-sub15-contexto-agente-escritor-unico-contrato-solto
    motivo: "contexto_agente (`d.get(\"contexto_agente\")`) tem UM UNICO escritor em todo o repositorio: `main.py::processar_contexto_agente`, chamado so pelo gatilho Firestore `on_document_written` em `tarefas/{taskId}` -- busca exaustiva por `\"contexto_agente\":` como chave de escrita confirma isso. O escritor grava sempre `None` ou um dict de forma fixa e coagida (`parse_resposta_contexto`: resumo sempre string nao-vazia, tres listas sempre de string, `onde_esta_o_codigo` sempre string ou None, `atualizado_em` sempre string ISO). Decidido manter contrato SOLTO (`type: [\"object\", \"null\"]`, sem `properties` aninhado) mesmo sabendo a forma exata -- mesmo espirito de `modelo_interacao` (buscar_contato) e `contadores` (consultar_execucoes_agente): e conteudo gerado por LLM sobre texto livre da acao, sem nenhum outro leitor no catalogo MCP hoje que precise validar sub-campos. Aprofundar fica para uma fatia futura, se algum consumidor precisar."
    autoridade: existente_ou_nova
  - id: p03-sub15-nota-diario-registrar-no-diario-crash-se-nao-string
    motivo: "`nota` do diario e `e.get(\"nota\")` CRU no proprio `obter_acao`. Investigado se a via principal de escrita (tool MCP `registrar_no_diario`) garante tipo: `nota = args.get(\"nota\")` seguido de `(nota or \"\").strip()` -- um valor truthy NAO-string (ex.: um numero) levanta `AttributeError` NESSA MESMA LINHA (`int` nao tem `.strip()`), capturado pelo `try/except` externo da propria funcao e devolvido como erro da tool, nunca chega a gravar. Ou seja, esse caminho especifico tem garantia de fato (crash-antes-de-gravar), nao so 'parece string na pratica'. As demais ~8 escritas de `acompanhamento` encontradas no repositorio usam f-string (coage para string sempre) ou variavel ja validada -- nenhuma grava valor cru nao-string encontrada nesta busca, mas a lista e grande o bastante para nao reivindicar auditoria exaustiva de cada uma; risco residual aceito e nao-bloqueante, mesma categoria das demais leituras cruas desta tool (mesmo tratamento dado aos 7 campos crus de consultar_historico_acoes nas sub-entregas 12/N-14/N)."
    autoridade: existente_ou_nova
  - id: p03-sub15-rodada1-sem-achado-parada
    motivo: "1a rodada de revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao), lendo o handler real completo, `subtarefas.py` inteiro, os 4 escritores de `pool_dados`/anexo e o escritor unico de `contexto_agente`: verificou linha a linha os pontos acima (oneOf de erro, plano_acao, anexos, diario, execution_lane/degradation_count, contexto_agente) contra o schema publicado e rodou a suite (`test_output_schema.py`, 51/51). Nao achou nenhum campo obrigatorio que possa faltar, tipo declarado que o handler real viole de forma demonstravel, ou `additionalProperties: False` que rejeitaria um campo real. Criterio de parada atingido na primeira rodada -- relatado aqui como resultado valido, sem inventar achado para parecer completo."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo)"
    - "python3 -m unittest test_output_schema -v (arquivo isolado)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, baseline antes da implementacao e depois)"
    - "Suite completa rodada de novo contra um checkout publico novo, clonado direto do branch remoto (nao o arquivo local editado), apos a escrita via Argos"
  resultados:
    - "Baseline (origin/main antes desta sub-entrega, commit a68d554, PR #266 ja mesclada): 1888/1888, 0 falhas, 0 erros."
    - "Arquivo isolado test_output_schema.py apos a implementacao completa: 51/51, 0 falhas, 0 erros (45 preexistentes + 6 novos/ajustados)."
    - "Suite completa apos a implementacao e a rodada de revisao: 1894/1894, 0 falhas, 0 erros, sem regressao (1888 baseline + 6 novos)."
    - "Suite completa rodada tambem contra um checkout publico real do branch remoto (git clone -b claude/p03-sub15-output-schema-obter-acao), nao so o arquivo local editado: 1894/1894."
evidencias:
  - "1 rodada de revisao adversarial independente (Agent tool, general-purpose, sem contexto da implementacao) -- ver decisoes para o relato completo. Nao achou nada real -- parada aqui, conforme a disciplina (escalar so enquanto uma rodada acha algo real)."
  - "Os 2 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio (delegado a um subagente dedicado, com as mesmas instrucoes de integridade desta skill), com o `sha` retornado por cada escrita comparado contra `git hash-object` local -- bateu de primeira nos dois. Verificacao adicional, independente do proprio retorno do Argos: `git fetch` do branch remoto + `git diff` contra `origin/<branch>` para os 2 arquivos -- diff vazio, identico byte a byte."
  - "Sanity check do PR: changed_files=2, additions=536, deletions=25 no retorno de argos_criar_pr_repositorio -- bate exatamente com `git diff --stat` rodado localmente antes de abrir o PR."
  - "PR #267 aberta (https://github.com/andre-martiini/Hermes/pull/267), com o relato completo da revisao e dos testes no corpo. NAO mesclada -- aguardando o Andre."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "ABERTA: PR #264 (aberta por engano durante a correcao do diario da sub-entrega 14/N, ver bloco dessa sub-entrega no arquivo de arquivo execucao-archive-p03sub13.md) continua aberta com um bug real de escaping YAML -- deve ser fechada sem mesclar pelo Andre; nao ha tool de fechamento de PR disponivel via Argos (so criar/comentar/mesclar), por isso nao foi possivel fechar automaticamente nesta nem em sub-entregas anteriores."
  - "ABERTA, deliberadamente: outputSchema para as demais ~99 tools do catalogo continua fora de escopo. Com `obter_acao` fechado, as candidatas explicitamente levantadas em sub-entregas anteriores (consultar_historico_acoes/obter_acao) estao esgotadas -- a proxima fatia de outputSchema precisa de um levantamento novo do catalogo (nenhuma investigada a fundo ainda)."
  - "ABERTA, deliberadamente (herdada da sub-entrega 7/N): idempotentHint continua fora de escopo -- precisa de investigacao dedicada por HANDLER, nenhum campo do inventario atual registra isso."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante; inconsistencia de criterio nao-bloqueante em 5 das 7 tools sem dominio_rede classificado (sub-entrega 7/N); campo `ordem` de consultar_lista_compras sem coercao de tipo, colecao shopping_items com multiplos escritores nao auditados (sub-entrega 10/N); duplicacao de `_to_iso` entre agent_requests.py e agent_runs.py (sub-entrega 12/N); lacuna de structuredContent nos caminhos de _text_result fora de confirmar_acao (heranca das sub-entregas 8/N-13/N); flag `ctx.mcp_confirmed_tool_execucao_falhou` so distingue 'levantou excecao' de 'resultado bate com a forma real' (sub-entrega 13/N)."
proximo_pacote: "P03 -- PR #267 (outputSchema/oneOf para obter_acao) aberta, aguardando revisao e merge do Andre. Depois de mesclada: as candidatas explicitamente levantadas para outputSchema (consultar_historico_acoes, obter_acao) estao esgotadas -- a proxima execucao agendada deve escolher entre (a) um levantamento NOVO do catalogo para achar a proxima candidata de outputSchema (nenhuma pronta na fila); (b) a investigacao dedicada de idempotentHint por handler (fora de escopo ha 8 sub-entregas); ou (c) perguntar ao Andre se prefere avancar direto para P04 (pedidos duraveis/lease/ledger) -- com o passo 3 do P03 tendo agora sete fatias de outputSchema entregues (mais a fatia envelope da sub-entrega 13/N), a opcao (c) fica cada vez mais razoavel. A cargo da execucao autonoma agendada, salvo nova prioridade do Andre. NOTA DE PROCESSO: PR #264 continua aberta e precisa ser fechada manualmente pelo Andre (sem tool de fechamento via Argos) -- ver pendencias."
```
