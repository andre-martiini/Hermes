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
re-arquivamento).** Nenhum conteúdo foi perdido; é
uma relocação, não uma edição. Este arquivo continua sendo a fonte de
verdade para tudo a partir da sub-entrega P03 10/N em diante.

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 77c95bf7915573b785752ef012f2cf5458fbd4ad
pacote: "P03 sub-entrega 10/N -- outputSchema/structuredContent (passo 3 do plano), terceira fatia: contrato de dados publicado em tools/list e refletido em tools/call para consultar_lista_compras, apos calculadora (sub-entrega 8/N) e buscar_contato (sub-entrega 9/N)"
estado: validado
inicio: "2026-09-13T11:20:00Z"
fim: "2026-09-13T12:31:19Z"
arquivos_alterados:
  - "functions/tools/registry.py (nova entrada `_OUTPUT_SCHEMAS['consultar_lista_compras']` -- contrato para as 7 chaves sempre presentes no nivel superior (total/planejados/comprados/filtro/encontrados/retornados/itens) mais `truncado` opcional; item com os 7 campos sempre presentes de `_item_publico` mais `ordem` opcional; `filtro` enum fechado com os 5 valores que `lista_compras._FILTROS` resolve)"
  - "functions/test_output_schema.py (5 testes novos: schema com campos obrigatorios/opcionais corretos, publicacao em tools/list, sucesso com structuredContent igual ao content, filtro invalido -- caminho real de erro, string 'ERRO|...' -- nunca leva structuredContent, e paridade campo a campo contra o schema publicado)"
decisoes:
  - id: p03-sub10-consultar-lista-compras-candidata-outputschema
    motivo: "Candidata escolhida apos levantar no inventario todas as tools LEITURA, sem rede, sem dado sensivel (necessidade_de_rede=False, dados_sensiveis=False): consultar_lista_compras, obter_portal_compras_publico, consultar_elevacoes_sugeridas, consultar_promocoes_autonomia_sugeridas, obter_projeto_bolsas_publico, consultar_pedidos_agente, consultar_execucoes_agente, consultar_politica, simular_politica, preparar_politica, entre outras. `consultar_politica` foi investigada e descartada primeiro: `_consultar_politica` (tools/hermes_tools.py) faz `json.dumps(...)` e devolve STRING, nao dict -- mesmo motivo pelo qual `consultar_saude` foi descartada na sub-entrega 9/N (contrato anunciado nunca teria structuredContent cumprido). `consultar_lista_compras` (backed por tools/lista_compras.py::consultar/_item_publico) foi escolhida por devolver dict cru com forma fixa e por `_item_publico` forcar `str()`/`bool()` em cada campo do item antes de devolver -- garantia de tipo mais forte que a de buscar_contato (que passa campos direto do documento do Firestore sem coercao) na PROPRIA funcao, ainda que nao a mais forte do catalogo (calculadora forca tipo em TODO campo sem excecao; consultar_lista_compras tem uma excecao, o campo opcional `ordem`, sem coercao em _item_publico). As demais candidatas do levantamento nao foram investigadas em profundidade nesta sub-entrega -- ficam como candidatas para a proxima fatia."
    autoridade: existente_ou_nova
  - id: p03-sub10-seis-rodadas-de-revisao-adversarial-sobre-um-comentario
    motivo: "A implementacao executavel (o JSON Schema em si, tipos/required/enum/additionalProperties) nunca mudou apos a 1a rodada -- todas as 5 correcoes subsequentes foram no COMENTARIO explicativo acima de `_OUTPUT_SCHEMAS['consultar_lista_compras']`, sobre quais caminhos de codigo alem de tools/lista_compras.py tambem tocam a colecao Firestore shopping_items (relevante porque `ordem`, unico campo do item sem coercao de tipo em `_item_publico`, depende disso). Rodada 1 (Agent tool, general-purpose, sem contexto): achou que o comentario original chamava tools/lista_compras.py de 'unico ponto de escrita/leitura' da colecao -- falso, tools/telegram_extended.py tambem le/escreve direto (obter_portal_compras_publico/mutar_portal_compras_publico). Corrigido. Rodada 2, sobre a correcao: confirmou a correcao 1 verdadeira, mas achou um overclaiming DIFERENTE -- um comentario em test_output_schema.py dizia que consultar_lista_compras tinha 'a garantia de tipo mais forte das tres' tools, quando calculadora e mais forte (zero excecoes vs. uma). Corrigido para comparacao pairwise precisa. Rodada 3: achou que a correcao 1 citou ERRADO qual duplicacao tools/inventory.py documenta -- atribuiu a duplicacao security_portals.py/tools/telegram_extended.py a uma nota do inventario que na verdade fala de outra coisa (mutar_portal_compras_publico vs. mutar_lista_compras). Corrigido. Rodada 4: achou que a propria contagem 'tres caminhos reais' (ja reescrita duas vezes) ainda estava incompleta -- o FRONTEND web (ShoppingListTool.tsx/index.tsx) tambem escreve na colecao via SDK do Firebase, direto do navegador. Nenhuma tentativa de enumeracao exaustiva resistiu a rodada seguinte achando mais um caminho -- decisao: parar de tentar enumerar todos os caminhos no comentario, reescrever para declarar honestamente que uma auditoria completa esta fora de escopo, que `ordem` foi checado como sempre inteiro so nos caminhos efetivamente inspecionados, e que isso e risco aceito e nao-bloqueante (mesmo tratamento ja dado ao risco equivalente de buscar_contato/perfil_pessoas na sub-entrega 9/N). Rodada 5, sobre essa reescrita: confirmou que a nova redacao nao overclaima mais contagem de caminhos, mas achou uma inconsistencia textual pequena (o historico dizia 'as tres primeiras rodadas', quando na real ja eram quatro rodadas com achado ate ali) -- aproveitada para remover o historico narrativo detalhado do comentario de codigo (nao e o lugar certo para uma narrativa de revisao; fica so a conclusao atual, com referencia a esta PR/entrada de diario para o historico). Rodada 6: nao achou nada -- criterio de parada atingido (escalar so enquanto uma rodada acha algo real)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo, clonado publicamente via git clone do repositorio)"
    - "python3 -m unittest test_output_schema -v (arquivo isolado)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, antes -- via git stash -- e depois de cada rodada de correcao)"
  resultados:
    - "Baseline (origin/main antes desta sub-entrega, confirmado via git stash para isolar do working tree local): 1834/1834, 0 falhas, 0 erros -- confirma o numero ja registrado pela sub-entrega 9/N."
    - "Arquivo isolado test_output_schema.py apos a implementacao: 24/24, 0 falhas, 0 erros."
    - "Suite completa apos a implementacao e as 5 rodadas de correcao textual: 1839/1839, 0 falhas, 0 erros, sem regressao (1834 baseline + 5 novos)."
evidencias:
  - "Seis rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou das rodadas anteriores) -- ver decisoes para o relato completo e honesto de cada achado. Nenhuma rodada encontrou problema na logica executavel do schema (tipos/required/enum/additionalProperties) nem nos testes -- todos os achados foram sobre precisao factual do texto explicativo (overclaiming de quantos caminhos de codigo tocam a colecao shopping_items, e uma citacao errada de qual nota do inventario documenta qual duplicacao)."
  - "Teste de paridade (TestOutputSchema::test_paridade_tres_tools_tem_output_schema_hoje) cobre TODAS as tools reais do catalogo (registry.list_tool_names(), 106 hoje), nao so as tres escolhidas a dedo."
  - "Os 2 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 2 batendo de primeira, sem drift de whitespace nem corrupcao."
  - "Sanity check do PR: changed_files=2, additions=248, deletions=19 no retorno de argos_criar_pr_repositorio -- bate exatamente com git diff --stat rodado localmente contra o commit-base (77c95bf) antes de abrir o PR."
  - "PR #256 aberta (https://github.com/andre-martiini/Hermes/pull/256), com o relato completo das 6 rodadas no corpo -- AINDA NAO MESCLADA, aguardando revisao e merge manual do Andre. Esta propria entrada de diario e o 9o arquivo de arquivo (execucao-archive-p03sub6-a-sub7.md) vao numa segunda commit desta mesma branch/PR, apos o codigo+testes."
  - "CONTEXTO OPERACIONAL: o disparo agendado anterior de hoje (13/09/2026, manha) nao conseguiu avancar porque o conector Argos MCP estava indisponivel para aquela sessao (enabledInChat=false) -- ficou registrado so como atualizacao do Blueprint da Autonomia via leitura publica (git clone/git log, sem escrita), sem nenhuma sub-entrega nova. O usuario reativou o Argos e pediu para tentar novamente; esta sessao confirmou o acesso restaurado (ListConnectors -> enabledInChat=true) e seguiu com este trabalho."
  - "CONFIRMACAO POSTERIOR (13/09/2026, tarefa agendada de avanco autonomo, ao iniciar a sub-entrega 11/N): PR #256 mesclada pelo Andre -- confirmado por `git clone` publico do repositorio + `git log --oneline origin/main`, merge commit `12ff309d6389a321283821c309ea9e7be3e83f42` presente na historia de `main` (mensagem: \"P03 sub-entrega 10/N: outputSchema/structuredContent para consultar_lista_compras (#256)\"). Estado desta entrada atualizado de `pronto_para_revisao` para `validado` nesta mesma sessao, sem reescrever nenhum outro campo do bloco -- mesmo padrao ja usado nas sub-entregas 8/N e 9/N."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por confirmacao posterior (ver evidencias): PR #256 mesclada; esta entrada passou de pronto_para_revisao para validado."
  - "PROCESSO, novo (achado indireto das rodadas 4-5 de revisao adversarial desta sub-entrega): um comentario de codigo que tenta enumerar EXAUSTIVAMENTE todos os caminhos que tocam um recurso compartilhado (ex.: uma colecao Firestore) e uma armadilha -- cada tentativa de fechar a lista foi refutada pela rodada seguinte achando mais um caminho (2 reescritas, 3 caminhos descobertos ao longo do processo: tools/telegram_extended.py, security_portals.py, frontend web). A partir desta sub-entrega, quando um comentario precisar registrar que um recurso tem OUTROS escritores alem do investigado, a redacao correta e declarar isso como fato conhecido e nao-exaustivo (dar 1-2 exemplos concretos, dizer explicitamente que uma auditoria completa esta fora de escopo) em vez de tentar contar/nomear todos -- mesmo espirito ja usado para pendencias tipo 'ha ~10 pontos de escrita, nenhum auditado' (buscar_contato, sub-entrega 9/N), que nunca tentou ser uma lista fechada e por isso nunca precisou ser corrigida por contagem incompleta."
  - "PROCESSO, novo: uma narrativa detalhada rodada-a-rodada de revisao adversarial NAO deve morar dentro de um comentario de codigo permanente -- e material de PR body/diario, nao de fonte. Tentar manter as duas coisas sincronizadas (o comentario tentando resumir seu proprio historico de correcao) e o que gerou a inconsistencia '3 vs 4 rodadas' que a rodada 5 encontrou. O comentario final em tools/registry.py ficou só com a CONCLUSAO atual mais uma referencia a esta PR/entrada para o historico -- nao com o historico embutido."
  - "ABERTA, nova, NAO-bloqueante (aceita conscientemente, ver decisoes): o campo `ordem` de cada item de consultar_lista_compras nao tem coercao de tipo em `_item_publico`, e a colecao shopping_items tem pelo menos 3 outros escritores conhecidos (tools/telegram_extended.py, security_portals.py, frontend web) alem de tools/lista_compras.py -- nenhum dos inspecionados grava `ordem` hoje, mas isso nao e uma auditoria completa da colecao. Mesma categoria e mesmo tratamento do risco de tipo de buscar_contato/perfil_pessoas (sub-entrega 9/N)."
  - "ABERTA, deliberadamente: outputSchema para as demais ~103 tools do catalogo continua fora de escopo -- candidatas ja levantadas nesta sub-entrega e ainda nao investigadas em profundidade: obter_portal_compras_publico, consultar_elevacoes_sugeridas, consultar_promocoes_autonomia_sugeridas, obter_projeto_bolsas_publico, consultar_pedidos_agente, consultar_execucoes_agente, simular_politica, preparar_politica. `consultar_politica` INVESTIGADA E DESCARTADA (handler serializa para string via json.dumps antes de devolver -- mesmo motivo de consultar_saude na sub-entrega 9/N)."
  - "ABERTA, deliberadamente (herdada da sub-entrega 7/N): idempotentHint continua fora de escopo -- precisa de investigacao dedicada por HANDLER, nenhum campo do inventario atual registra isso."
  - "ABERTA: a fatia `envelope` do passo 3 do plano (alem de outputSchema/structuredContent/annotations, ja cobertos em parte) nao foi investigada nesta sub-entrega."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante; inconsistencia de criterio nao-bloqueante em 5 das 7 tools sem dominio_rede classificado (sub-entrega 7/N); estrutura de _item_publico de mutar_portal_compras_publico/security_portals.py duplicada com mutar_lista_compras (achado ja documentado em tools/inventory.py antes desta sub-entrega, nao criado por ela)."
proximo_pacote: "P03 -- ver bloco da sub-entrega 11/N (PR #257, aguardando merge do Andre) para o proximo passo apos ela."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 12ff309d6389a321283821c309ea9e7be3e83f42
pacote: "P03 sub-entrega 11/N -- outputSchema/structuredContent (passo 3 do plano), quarta fatia: contrato de dados publicado em tools/list e refletido em tools/call para consultar_execucoes_agente, apos calculadora (sub-entrega 8/N), buscar_contato (sub-entrega 9/N) e consultar_lista_compras (sub-entrega 10/N, confirmada mesclada nesta mesma execucao -- ver bloco anterior, agora arquivado em execucao-archive-p03sub8-a-sub9.md junto com os blocos 8/N e 9/N)"
estado: validado
inicio: "2026-09-13T15:00:00Z"
fim: "2026-09-13T15:23:14Z"
arquivos_alterados:
  - "functions/tools/registry.py (nova entrada `_OUTPUT_SCHEMAS['consultar_execucoes_agente']` -- contrato para `{total: int, runs: [...]}`; item com 9 campos sempre presentes (id/rotina/status/resumo/contadores/erro/iniciado_em/finalizado_em/criado_em), `status` como enum fechado (sucesso/erro/parcial), `contadores` com contrato solto (`type: object`, sem `properties` aninhado), `erro`/`iniciado_em`/`finalizado_em`/`criado_em` como `[string, null]`)"
  - "functions/test_output_schema.py (6 testes novos: schema com campos obrigatorios corretos incluindo enum de status e tipos nullable, publicacao em tools/list, sucesso com structuredContent igual ao content, lista vazia tambem leva structuredContent, e paridade campo a campo contra o schema publicado)"
decisoes:
  - id: p03-sub11-consultar-execucoes-agente-garantia-de-tipo-mais-forte-ate-agora
    motivo: "Levantei as candidatas de leitura simples ja mapeadas pela sub-entrega 10/N (obter_portal_compras_publico, consultar_elevacoes_sugeridas, consultar_promocoes_autonomia_sugeridas, obter_projeto_bolsas_publico, consultar_pedidos_agente, consultar_execucoes_agente) e investiguei os handlers reais de tres delas. `consultar_execucoes_agente` (backed por agent_runs.py::listar_recentes) foi escolhida por ter a garantia de tipo mais forte encontrada ate agora no catalogo: a colecao Firestore que ela le (`agent_runs`) tem UM UNICO ESCRITOR em todo o repositorio -- `agent_runs.registrar`, chamado so pela tool `registrar_execucao_agente` -- e esse escritor SEMPRE passa por `agent_runs.montar_registro` antes de gravar, que valida cada campo (rotina/resumo nao podem ser vazios, status tem que estar no enum de 3 valores, contadores so e aceito se for dict ou None) e devolve so {'erro': ...} sem chamar col.add(...) quando algum campo obrigatorio falha -- nunca grava um documento fora dessa forma. Confirmado por busca exaustiva no repositorio: nenhum outro arquivo escreve na colecao agent_runs (retro_agente.py, o unico outro modulo que a menciona, so LE). Diferente de buscar_contato/perfil_pessoas e consultar_lista_compras/shopping_items (sub-entregas 9/N e 10/N), aqui nao ha varios pontos de escrita nao auditados -- ha exatamente um, e ele valida antes de gravar."
    autoridade: existente_ou_nova
  - id: p03-sub11-duas-candidatas-descartadas-por-formato-alternativo-de-erro
    motivo: "`consultar_elevacoes_sugeridas`/deteccao_subproduto.listar_pendentes e `consultar_promocoes_autonomia_sugeridas`/promocao_autonomia.listar_promocoes_pendentes foram investigadas e descartadas nesta sub-entrega: as duas tem um formato ALTERNATIVO de erro ({'total': 0, 'sugestoes'|'promocoes': [], 'erro': str(exc)}) quando a consulta ao Firestore falha (try/except ao redor da query) -- modelar outputSchema pra elas exigiria decidir se o contrato cobre as duas formas possiveis ou so a normal, investigacao maior que esta fatia. agent_runs.listar_recentes nao tem esse formato alternativo (sem try/except ao redor da query -- uma falha de consulta propaga como excecao nao tratada, fora do escopo de outputSchema, mesmo tratamento generico de qualquer handler sem try/except)."
    autoridade: existente_ou_nova
  - id: p03-sub11-contadores-contrato-solto-mesmo-espirito-de-modelo-interacao
    motivo: "`contadores` e um dict livre passado por quem chama `registrar_execucao_agente` (contagens especificas de cada rotina, ex.: acoes_atrasadas, tentativas), sem forma fixa entre rotinas diferentes -- por isso fica com contrato solto (`type: object`, sem `properties` aninhado), mesmo espirito ja usado para `modelo_interacao` em buscar_contato (sub-entrega 9/N). erro/iniciado_em/finalizado_em/criado_em ficam `[string, null]`: `_to_iso` (agent_runs.py) sempre devolve string ou None, nunca outro tipo; finalizado_em e criado_em sao sempre preenchidos pelo proprio `registrar` quando ausentes (firestore.SERVER_TIMESTAMP), entao na pratica nunca chegam None por um caminho de escrita atual -- o null fica so como precaucao contra documento legado sem o campo, nunca observado."
    autoridade: existente_ou_nova
  - id: p03-sub11-primeira-rodada-nao-achou-nada
    motivo: "UNICA rodada de revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao), verificando por leitura direta do codigo-fonte (nao confiando nos comentarios do diff): a alegacao de escritor unico de agent_runs (confirmado, inclusive checando firestore.rules para descartar escrita direta do cliente -- agent_runs esta na lista de colecoes negadas por completo); a exatidao do schema contra agent_runs.listar_recentes (confirmado, os 9 campos batem exatamente); se a tool fica fora de _CONFIRMACAO_OBRIGATORIA/_ASYNC_TOOLS (confirmado, passa pelo caminho direto que leva structuredContent); a qualidade dos testes novos (confirmado, nao vazios); e as duas candidatas descartadas terem mesmo o formato alternativo de erro alegado (confirmado, lendo os dois handlers). Resultado: nao achou nada real -- parada aqui, conforme a disciplina (escalar so enquanto uma rodada acha algo real; 'nao achou nada' e resultado valido, nao inventado pra parecer completo)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo, clonado publicamente via git clone do repositorio)"
    - "python3 -m unittest test_output_schema -v (arquivo isolado)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, antes e depois da implementacao)"
  resultados:
    - "Baseline (origin/main antes desta sub-entrega, confirmado por git clone publico incluindo a PR #256 ja mesclada): 1839/1839, 0 falhas, 0 erros -- confirma o numero ja registrado pela sub-entrega 10/N."
    - "Arquivo isolado test_output_schema.py apos a implementacao: 29/29, 0 falhas, 0 erros."
    - "Suite completa apos a implementacao: 1844/1844, 0 falhas, 0 erros, sem regressao (1839 baseline + 5 novos)."
evidencias:
  - "Uma rodada de revisao adversarial independente (Agent tool, general-purpose, sem contexto da implementacao) -- nao achou nada real, ver decisoes para o relato completo. Verificou por leitura direta do codigo-fonte a alegacao de escritor unico de agent_runs (incluindo checagem de firestore.rules), a exatidao do schema, a ligacao em mcp_server.py e a qualidade dos testes; rodou a suite isolada e outras relacionadas (test_agent_runs, test_retro_agente), tudo verde."
  - "Teste de paridade (TestOutputSchema::test_paridade_quatro_tools_tem_output_schema_hoje) cobre TODAS as tools reais do catalogo (registry.list_tool_names(), 106 hoje), nao so as quatro escolhidas a dedo."
  - "Os 2 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 2 batendo de primeira, sem drift de whitespace nem corrupcao. Verificacao adicional, mais forte que o hash isolado do proprio Argos: git fetch do branch remoto + git show FETCH_HEAD:<path> comparado byte a byte (diff) contra o arquivo local -- identico para os 2 arquivos."
  - "Sanity check do PR: changed_files=2, additions=239, deletions=16 no retorno de argos_criar_pr_repositorio -- bate exatamente com git diff --stat main FETCH_HEAD rodado localmente antes de abrir o PR."
  - "PR #257 aberta (https://github.com/andre-martiini/Hermes/pull/257), com o relato completo da revisao adversarial no corpo -- AINDA NAO MESCLADA, aguardando revisao e merge manual do Andre."
  - "CONFIRMACAO POSTERIOR (13/09/2026, tarefa agendada de avanco autonomo, ao iniciar a sub-entrega 12/N): PR #257 mesclada pelo Andre -- confirmado por `git clone` publico do repositorio + `git log --oneline origin/main`, merge commit `914a89c` presente na historia de `main` (mensagem: \"P03 sub-entrega 11/N: outputSchema/structuredContent para consultar_execucoes_agente (#257)\"). Estado desta entrada atualizado de `pronto_para_revisao` para `validado` nesta mesma sessao, sem reescrever nenhum outro campo do bloco -- mesmo padrao ja usado nas sub-entregas 8/N, 9/N e 10/N."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por confirmacao posterior (ver evidencias): PR #257 mesclada; esta entrada passou de pronto_para_revisao para validado."
  - "ABERTA, herdada das sub-entregas 8/N-10/N: structuredContent so chega no caminho de EXECUCAO DIRETA de _handle_tools_call, nao nos caminhos que usam _text_result. consultar_execucoes_agente nao esta em _CONFIRMACAO_OBRIGATORIA nem em _ASYNC_TOOLS hoje, mas o mesmo risco de configuracao futura via Firestore (system/mcp_access.confirm_tools) documentado para as tres tools anteriores se aplica aqui tambem."
  - "ABERTA, deliberadamente: outputSchema para as demais ~101 tools do catalogo (calculadora, buscar_contato, consultar_lista_compras e consultar_execucoes_agente ja cobertas) continua fora de escopo -- candidatas ja investigadas e descartadas nesta sub-entrega: consultar_elevacoes_sugeridas e consultar_promocoes_autonomia_sugeridas (formato alternativo de erro, ver decisoes). Candidatas ainda nao investigadas: obter_portal_compras_publico, obter_projeto_bolsas_publico, consultar_pedidos_agente (mesma familia de agent_requests, mas com varios escritores na colecao -- atencao_whatsapp.py, mcp_jobs.py, agent_requests.py -- ao contrario do escritor unico de agent_runs), simular_politica, preparar_politica."
  - "ABERTA, deliberadamente (herdada da sub-entrega 7/N): idempotentHint continua fora de escopo -- precisa de investigacao dedicada por HANDLER, nenhum campo do inventario atual registra isso."
  - "ABERTA: a fatia `envelope` do passo 3 do plano (alem de outputSchema/structuredContent/annotations, ja cobertos em parte) nao foi investigada nesta sub-entrega."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante; inconsistencia de criterio nao-bloqueante em 5 das 7 tools sem dominio_rede classificado (sub-entrega 7/N); campo `ordem` de consultar_lista_compras sem coercao de tipo, colecao shopping_items com multiplos escritores nao auditados (sub-entrega 10/N)."
proximo_pacote: "P03 -- aguardando merge da PR #257 (outputSchema/structuredContent para consultar_execucoes_agente). Depois de mesclada: mais uma fatia pequena de outputSchema para uma das candidatas ja levantadas (obter_portal_compras_publico, obter_projeto_bolsas_publico, consultar_pedidos_agente, simular_politica, preparar_politica), ou a investigacao dedicada de idempotentHint por handler, ou perguntar ao Andre se prefere avancar direto para P04 (pedidos duraveis/lease/ledger) dado que o passo 2 do P03 ja esta totalmente fechado e o passo 3 tem quatro fatias reais entregues -- a cargo da execucao autonoma agendada, salvo nova prioridade do Andre."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 97c067ae1df22e7ee347d9791da39dfa01792acc
pacote: "P03 sub-entrega 12/N -- outputSchema/structuredContent (passo 3 do plano), quinta fatia: contrato de dados publicado em tools/list e refletido em tools/call para consultar_pedidos_agente, apos calculadora (sub-entrega 8/N), buscar_contato (sub-entrega 9/N), consultar_lista_compras (sub-entrega 10/N) e consultar_execucoes_agente (sub-entrega 11/N, confirmada mesclada nesta mesma execucao -- ver bloco anterior)"
estado: pronto_para_revisao
inicio: "2026-09-13T19:15:00Z"
fim: "2026-09-13T19:45:00Z"
arquivos_alterados:
  - "functions/tools/registry.py (nova entrada `_OUTPUT_SCHEMAS['consultar_pedidos_agente']` -- contrato para `{total: int, pedidos: [...]}`; item com 9 campos sempre presentes (id/tipo/status/payload/origem/item_atencao_id/acao_id/criado_em/atualizado_em); `status` enum fechado de UM valor (`[\"pendente\"]`, garantido pelo proprio filtro da query, nao por escritor unico); `payload` com contrato solto (`type: object`); `tipo`/`origem` como `string` solta, deliberadamente NAO enum; `item_atencao_id`/`acao_id`/`criado_em`/`atualizado_em` como `[string, null]`)"
  - "functions/test_output_schema.py (5 testes novos: schema com campos obrigatorios corretos incluindo enum de status de um valor e contrato solto de payload, publicacao em tools/list, sucesso com structuredContent igual ao content, lista vazia tambem leva structuredContent, e paridade campo a campo contra o schema publicado)"
decisoes:
  - id: p03-sub12-consultar-pedidos-agente-candidata-outputschema
    motivo: "Das candidatas ja levantadas e ainda nao investigadas na sub-entrega 11/N (obter_portal_compras_publico, obter_projeto_bolsas_publico, consultar_pedidos_agente, simular_politica, preparar_politica), quatro foram investigadas e descartadas nesta sub-entrega por devolverem STRING (json.dumps) em vez de dict, mesmo motivo de consultar_politica na sub-entrega 10/N: obter_portal_compras_publico e obter_projeto_bolsas_publico (tools/telegram_extended.py, ambas `return json.dumps(...)`), e simular_politica/preparar_politica (tools/hermes_tools.py::_simular_politica/_preparar_politica, sempre `json.dumps(...)` mesmo no caminho de sucesso). consultar_pedidos_agente (backed por agent_requests.py::listar_pendentes) foi escolhida por devolver dict cru com forma fixa -- unica sobrevivente das cinco candidatas restantes."
    autoridade: existente_ou_nova
  - id: p03-sub12-correcao-pendencia-11N-varios-escritores
    motivo: "A pendencia registrada no bloco da sub-entrega 11/N (acima) descrevia agent_requests como tendo 'varios escritores (atencao_whatsapp.py, mcp_jobs.py, agent_requests.py)'. Busca exaustiva nesta sub-entrega (grep por collection(\"agent_requests\"), por COLLECTION do proprio modulo e por agent_requests.enfileirar_ou_atualizar em todo o repositorio) encontrou UM UNICO ponto de criacao de documento -- atencao_whatsapp.py, fluxo audio_relevante -- e confirmou que mcp_jobs.py so MENCIONA agent_requests.py em comentarios de comparacao de padrao de transacao Firestore, nunca escreve na colecao. O bloco 11/N nao e reescrito (nunca esteve validado quando este achado surgiu, mas a correcao mora aqui, forward-only, no mesmo espirito ja estabelecido pela sub-entrega 10/N de nao reescrever registros anteriores para corrigir precisao factual). Esta garantia de escritor unico e o que sustenta o restante do schema desta sub-entrega (status, tipo, origem, payload)."
    autoridade: existente_ou_nova
  - id: p03-sub12-status-enum-por-filtro-de-query-nao-por-escritor
    motivo: "status fica enum fechado de UM valor (['pendente']) por uma garantia estruturalmente diferente e mais forte que 'escritor unico': e o proprio filtro da query em listar_pendentes (`.where(\"status\", \"==\", STATUS_PENDENTE)`), que nunca deixa passar outro valor no resultado independente de quantos escritores a colecao tiver algum dia. Ja tipo/origem ficam como `string` solta, NAO enum, porque a garantia de valor unico para eles vem so de 'existe um unico escritor hoje' (mais fraca) -- um enum de um valor quebraria no dia em que um segundo tipo de pedido autonomo for implementado (o proprio design do modulo antecipa isso: 'Enfileira tarefas autonomas... ex.: consolidacao de audios', no singular de um exemplo, nao uma lista fechada). payload fica com contrato solto (`type: object`, sem properties aninhado) pelo mesmo motivo de tipo -- e conceitualmente por-tipo, mesmo tendo forma totalmente coagida hoje (montar_payload_consolidar_audio forca str()/list() em cada campo)."
    autoridade: existente_ou_nova
  - id: p03-sub12-tres-rodadas-de-revisao-adversarial
    motivo: "Rodada 1 (Agent tool, general-purpose, sem contexto): confirmou a maior parte do comentario/schema, mas achou um overclaiming real -- o comentario dizia que criado_em/atualizado_em usam 'a mesma _to_iso de agent_runs.py', quando na verdade agent_requests.py define uma funcao _to_iso PROPRIA (funcionalmente identica, mas uma duplicata, nao importada de la). Corrigido. Rodada 2, sobre essa correcao: confirmou a correcao verdadeira (duas definicoes separadas, corpos identicos), mas achou que o texto corrigido introduziu um problema NOVO -- afirmava 'DUAS RODADAS DE REVISAO ADVERSARIAL... (relato completo)' dentro do proprio comentario de codigo, uma alegacao de conclusao de processo escrita ANTES de a rodada 2 (que a apontou) ter de fato terminado -- o mesmo tipo de overclaiming da sub-entrega 10/N (uma narrativa rodada-a-rodada dentro de um comentario permanente), so que sobre o proprio processo de revisao em vez de sobre uma colecao Firestore. Corrigido: o comentario passou a so apontar para este diario/PR para o historico completo, sem fixar quantidade de rodadas nem alegar conclusao. Rodada 3, sobre essa segunda correcao: confirmou que a nova redacao nao afirma mais quantidade de rodadas nem conclusao prematura, verificou que o precedente citado (sub-entrega 10/N, sobre narrativa nao pertencer a comentario de codigo) e real e foi citado com precisao, re-confirmou a paridade schema/dict e a suite completa -- nao achou nada novo. Criterio de parada atingido (escalar so enquanto uma rodada acha algo real; a rodada 3 nao achou nada)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo, clonado publicamente via git clone do repositorio)"
    - "python3 -m unittest test_output_schema -v (arquivo isolado)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, antes -- via git stash -- e depois da implementacao, e novamente apos o rebase para o commit-base atualizado 97c067a quando main avancou com um commit nao relacionado durante esta mesma sessao)"
  resultados:
    - "Baseline no commit-base original (914a89c, antes de main avancar): 1844/1844, 0 falhas, 0 erros -- confirma o numero ja registrado pela sub-entrega 11/N."
    - "Baseline reconfirmado apos main avancar para 97c067a (commit nao relacionado, 'automations: inicializador oculto para o servidor de automacoes PGD/ponto', mesclado por fora deste plano durante esta mesma janela de execucao): 1844/1844, 0 falhas, 0 erros -- sem mudanca, confirma que o commit nao relacionado nao afeta esta suite."
    - "Arquivo isolado test_output_schema.py apos a implementacao: 34/34, 0 falhas, 0 erros."
    - "Suite completa apos a implementacao (contra o commit-base atualizado 97c067a): 1849/1849, 0 falhas, 0 erros, sem regressao (1844 baseline + 5 novos)."
evidencias:
  - "Tres rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou das rodadas anteriores) -- ver decisoes para o relato completo e honesto de cada achado. Nenhuma rodada encontrou problema na logica executavel do schema (tipos/required/enum/additionalProperties) nem nos testes -- os dois achados reais (rodadas 1 e 2) foram sobre precisao factual do texto explicativo do comentario de codigo."
  - "Teste de paridade (TestOutputSchema::test_paridade_cinco_tools_tem_output_schema_hoje) cobre TODAS as tools reais do catalogo (registry.list_tool_names(), 106 hoje), nao so as cinco escolhidas a dedo."
  - "Os 2 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 2 batendo de primeira, sem drift de whitespace nem corrupcao. Verificacao adicional, mais forte que o hash isolado do proprio Argos: git fetch do branch remoto (refspec explicito) + git diff contra origin/<branch> para os 2 arquivos -- diff vazio, identico byte a byte. Suite completa tambem rodada contra o checkout real do branch remoto (nao so o arquivo local editado), 1849/1849."
  - "Branch criada a partir de main (nao havia PR aberta nao mesclada desta linha de trabalho no momento: a sub-entrega 11/N ja tinha sido mesclada, PR #257); main avancou de 914a89c para 97c067a entre a criacao do branch e a escrita dos arquivos (commit nao relacionado a este plano) -- resolvido com git reset --hard origin/main local + reaplicacao das mudancas (git stash/pop), sem impacto no branch remoto ja criado a partir do commit mais antigo (a escrita via Argos usa o HEAD atual do branch, nao o commit de criacao)."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "ABERTA: PR desta sub-entrega ainda nao aberta no momento em que este bloco foi escrito (o diario e commitado ANTES da chamada a argos_criar_pr_repositorio, mesmo padrao das sub-entregas anteriores) -- uma execucao futura deve conferir se foi mesclada e atualizar estado/evidencias aqui, sem reescrever um bloco ja validado."
  - "ABERTA, herdada das sub-entregas 8/N-11/N: structuredContent so chega no caminho de EXECUCAO DIRETA de _handle_tools_call, nao nos caminhos que usam _text_result. consultar_pedidos_agente nao esta em _CONFIRMACAO_OBRIGATORIA nem em _ASYNC_TOOLS hoje, mas o mesmo risco de configuracao futura via Firestore (system/mcp_access.confirm_tools) documentado para as quatro tools anteriores se aplica aqui tambem."
  - "ABERTA, deliberadamente: outputSchema para as demais ~101 tools do catalogo continua fora de escopo. Das cinco candidatas que a sub-entrega 11/N tinha deixado para investigar (obter_portal_compras_publico, obter_projeto_bolsas_publico, consultar_pedidos_agente, simular_politica, preparar_politica), as quatro restantes apos esta sub-entrega (obter_portal_compras_publico, obter_projeto_bolsas_publico, simular_politica, preparar_politica) foram INVESTIGADAS E DESCARTADAS aqui -- todas devolvem string via json.dumps, nunca dict (ver decisoes). Levantamento automatico simples (grep no inventario por leitura_escrita=LEITURA + necessidade_de_rede=False + dados_sensiveis=False, sem investigar cada handler a fundo -- portanto NAO exaustivo, buscar_contato por exemplo tem dados_sensiveis=True e ainda assim ja foi coberta) aponta candidatas ainda inteiramente nao-investigadas: consultar_historico_acoes, obter_contexto_tela, preparar_edicao_acao, preparar_edicao_em_lote, gerar_rascunho_formulario, preparar_reagendamento_em_lote, preparar_remocao_horarios_em_lote, obter_acao -- nenhuma teve o handler real lido nesta sub-entrega, ficam como ponto de partida (nao lista fechada) para a proxima fatia."
  - "ABERTA, deliberadamente (herdada da sub-entrega 7/N): idempotentHint continua fora de escopo -- precisa de investigacao dedicada por HANDLER, nenhum campo do inventario atual registra isso."
  - "ABERTA: a fatia `envelope` do passo 3 do plano (alem de outputSchema/structuredContent/annotations, ja cobertos em parte) nao foi investigada nesta sub-entrega."
  - "ABERTA, nova, NAO-bloqueante: agent_requests.py e agent_runs.py tem cada um a sua PROPRIA funcao `_to_iso`, funcionalmente identica (mesmo corpo), mas duplicada -- oportunidade de refatoracao (extrair para um modulo utilitario compartilhado) fora do escopo desta fatia de contrato, que so documenta o fato para nao overclaimar acoplamento que nao existe (achado da 1a rodada de revisao adversarial desta sub-entrega)."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante; inconsistencia de criterio nao-bloqueante em 5 das 7 tools sem dominio_rede classificado (sub-entrega 7/N); campo `ordem` de consultar_lista_compras sem coercao de tipo, colecao shopping_items com multiplos escritores nao auditados (sub-entrega 10/N)."
proximo_pacote: "P03 -- aguardando merge da PR desta sub-entrega (outputSchema/structuredContent para consultar_pedidos_agente). Depois de mesclada, candidatas para outputSchema ficam mais escassas e mais trabalhosas (as cinco fatias faceis ja levantadas explicitamente foram todas cobertas ou descartadas) -- a proxima execucao agendada deve escolher entre: (a) investigar do zero uma das oito candidatas do levantamento automatico nao-exaustivo acima (consultar_historico_acoes, obter_contexto_tela, preparar_edicao_acao, preparar_edicao_em_lote, gerar_rascunho_formulario, preparar_reagendamento_em_lote, preparar_remocao_horarios_em_lote, obter_acao), lendo cada handler real antes de escolher; (b) a investigacao dedicada de idempotentHint por handler (fora de escopo ha 5 sub-entregas); (c) a fatia `envelope` do passo 3; ou (d) perguntar ao Andre se prefere avancar direto para P04 (pedidos duraveis/lease/ledger), dado que o passo 2 do P03 esta totalmente fechado e o passo 3 ja tem cinco fatias reais de outputSchema entregues -- a cargo da execucao autonoma agendada, salvo nova prioridade do Andre."
```
