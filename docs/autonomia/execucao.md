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
de arquivo para o relato completo.** Nenhum conteúdo foi perdido; é
uma relocação, não uma edição. Este arquivo continua sendo a fonte de
verdade para tudo a partir da sub-entrega P03 4/N em diante.

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 9215a3acfdf5b94fb9b3d9b4a11d099587ae5247
pacote: "P03 sub-entrega 4/N -- checagem de TIPO do schema no preflight de tools/call, so a fatia estrutural (array/object), deixada em aberto pela sub-entrega 2/N; escopo escalar (string/integer/number/boolean) permanece deliberadamente fora"
# inicio abaixo aproximado pelo timestamp do base_commit (merge da PR #228,
# diario da sub-entrega 3/N) -- a investigacao dos handlers/schemas e a
# implementacao local comecaram num trecho de sessao anterior a este sem
# timestamp proprio observavel por mim com precisao; nao invento um.
estado: validado
inicio: "2026-09-10T01:11:26Z"
fim: "2026-09-10T02:11:16Z"
arquivos_alterados:
  - functions/tools/registry.py (nova `tipos_invalidos(tool_name, arguments) -> list[dict]`: le o schema publicado real, so os dois tipos JSON Schema ESTRUTURAIS -- `array`->`list`, `object`->`dict` -- via `_TIPOS_JSON_PARA_PYTHON`; falha aberta na mesma filosofia de `campos_obrigatorios_ausentes`; docstring desta ultima atualizada para apontar a nova funcao em vez de so prometer "fica para sub-entrega futura". Tambem `_CAMPOS_COM_TOLERANCIA_A_STRING_JSON`, o conjunto fechado de 4 pares (tool, campo) que a checagem pula -- ver decisoes.)
  - functions/mcp_server.py (novo `_erro_tipos_invalidos`, wrapper que traduz `tipos_invalidos` para o envelope MCP; ligado em `_handle_tools_call` nos mesmos dois pontos de insercao de `_erro_campos_obrigatorios`, logo depois dela -- presenca tem prioridade quando os dois se aplicam ao mesmo payload)
  - functions/test_validacao_argumentos.py (tres classes novas -- `TestTiposInvalidos`, `TestErroTiposInvalidos`, `TestIntegracaoTiposInvalidos` -- 39 -> 42 testes no arquivo; inclui paridade contra os 105 schemas reais do catalogo e os testes da excecao de tolerancia a string JSON)
decisoes:
  - id: p03-sub4-fronteira-estrutural-array-object-nao-escalar
    motivo: "Investigacao real dos 105 schemas (`tools/schemas/*.json`: 341 propriedades, distribuicao `string:234, integer:37, array:28, number:18, boolean:17, object:7`, zero uniao de tipos em uso) e dos handlers que os consomem (`tools/hermes_tools.py`) antes de implementar, nao suposicao. Campos escalares numericos/booleanos ja sao tratados com tolerancia DELIBERADA pelo proprio handler hoje -- padrao `int(args.get('limite') or 20)` aceita `'20'` de bom grado, ~17 ocorrencias; uma checagem escalar estrita rejeitaria chamada 'meio certa' que hoje funciona, exatamente o risco que a sub-entrega 2/N identificou e adiou. Os dois tipos estruturais nao tem essa tolerancia pre-existente: `alteracoes = dict(args.get('alteracoes') or {})` (`editar_acao`) levanta `ValueError` opaco com uma string; `tags = args.get('tags') or []` (`hermes_tools.py:1052`) e pior -- string nao-vazia vira a propria `tags`, tratada como lista sem erro nenhum ali, ate corromper dado silenciosamente ou explodir mais adiante. Enum (8 propriedades) fica fora de proposito, candidato a sub-entrega futura."
    autoridade: existente_ou_nova
  - id: p03-sub4-revisao-achou-regressao-plano-como-string-json
    motivo: "Achado real da PRIMEIRA rodada de revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao): `criar_acao_no_sistema` (`plano_acao`) e `editar_plano_acao` (`novo_plano`/`plano_acao`/`etapas`) ja aceitavam, antes desta sub-entrega, uma STRING com o JSON de uma lista de etapas -- `subtarefas.normalizar_entrada_plano` (gatilho: incidente real de producao em 28/08/2026, com teste de regressao dedicado em `test_subtarefas.py::TestPlanoQueChegaComoString`) decodifica isso com seguranca antes de usar, recusando com erro claro (`PlanoInvalido`) so quando a string nao e JSON valido de lista. Sem excecao, o preflight desta sub-entrega bloquearia uma chamada valida hoje -- a mesma classe de regressao que a sub-entrega 2/N evitou para os escalares, so que encontrada tarde demais para evitar por investigacao previa sozinha. Corrigido com `_CAMPOS_COM_TOLERANCIA_A_STRING_JSON`, lista FECHADA de 4 pares (tool, campo) com tolerancia comprovada -- nao uma regra geral 'aceitar string se for JSON valido do tipo certo', que reabriria o buraco original para campos sem essa normalizacao: `editar_acao.tags`, por exemplo, continua sem tolerancia e continua sendo rejeitado (teste dedicado prova que a excecao nao se espalha)."
    autoridade: existente_ou_nova
  - id: p03-sub4-segunda-rodada-adversarial-sobre-o-fix-nao-achou-problema
    motivo: "SEGUNDA rodada de revisao adversarial, desta vez sobre o proprio fix da regressao acima (mesmo padrao usado na PR #10 do Argos, citado na skill argos-ship-feature: revisar tambem a correcao, nao so o diff original). Verificou de forma independente: `normalizar_entrada_plano` e funcao TOTAL (rejeita com erro claro qualquer valor que nao seja lista/dict/str/None, nunca crasha, mesmo passando int/bool/float diretamente -- a excecao pula a checagem de tipo para esses 4 campos independente do tipo recebido, nao so string, e isso e seguro porque o handler trata tudo); grep completo por padroes `isinstance(..., str)` + `json.loads` sobre argumento MCP em `hermes_tools.py`/`telegram_extended.py` nao achou nenhum par (tool, campo) irmao faltando na excecao; os 4 nomes de campo na excecao batem exatamente com as propriedades reais dos schemas (case-sensitive, sem typo). Nao achou nada a corrigir."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "../venv/bin/python3 -m unittest test_validacao_argumentos -v (venv persistente do clone, ja atualizada fiel a requirements.txt desde a sub-entrega 3/N)"
    - "../venv/bin/python3 -m unittest discover -s . -p 'test_*.py' (suite completa)"
  resultados:
    - "Arquivo isolado: 42/42, 0 falhas, 0 erros (39 pre-existentes da sub-entrega 2/N + 3 classes novas desta sub-entrega)."
    - "Suite completa: 1625/1625, 0 falhas, 0 erros (1601 baseline confirmado pela sub-entrega 3/N + 21 da propria 2/N/3/N + 3 novos aqui -- numero ja reflete a fidelidade de venv corrigida pela sub-entrega anterior, sem a incerteza das quatro entradas mais antigas)."
evidencias:
  - "Analise programatica completa dos 105 schemas em tools/schemas/*.json (contagem exata de propriedades por tipo, confirmacao de zero uniao de tipos em uso) antes de decidir o escopo, nao amostragem."
  - "Duas rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao): a primeira achou a regressao do plano-como-string-json (ver decisoes); a segunda, sobre o fix em si, nao achou problema -- confirmou a funcao total de `normalizar_entrada_plano`, a ausencia de caso irmao faltando via grep completo, e a exatidao dos nomes de campo contra os schemas reais."
  - "Teste de paridade (`TestTiposInvalidos::test_paridade_com_todos_os_schemas_reais_do_catalogo`) cobre TODOS os 105 schemas reais, nao so os exemplos escolhidos a dedo -- para todo campo array/object declarado, valor certo nunca e falso positivo e valor errado (exceto os 4 pares da excecao) e sempre detectado."
  - "Todos os 3 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 3 batendo de primeira, sem drift de whitespace nem corrupcao."
  - "PR #229 aberta, revisada (as duas rodadas acima) e mesclada por Andre ('mesclado, pode prosseguir'), confirmado por git fetch + git log de origin/main: merge commit 79e19afb2."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: checagem de tipo do schema, fatia estrutural (array/object) -- a pendencia aberta explicitamente pela sub-entrega 2/N."
  - "ABERTA, deliberadamente: checagem de tipo ESCALAR (string/integer/number/boolean) permanece fora de escopo -- handlers reais toleram coercao (`int('20')`) de proposito; so revisitar se um caso concreto mostrar que essa tolerancia virou problema real, nao por simetria com a fatia estrutural."
  - "ABERTA, nova candidata: validacao de `enum` (8 propriedades no catalogo declaram enum hoje) nao e coberta por nenhuma das duas checagens -- candidata a sub-entrega futura, nao investigada a fundo ainda."
  - "ABERTA: passo 3 do plano (outputSchema/structuredContent/annotations nos caminhos compativeis) continua sem cobertura."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante."
proximo_pacote: "P03 -- passo 2 do plano agora completo em toda a extensao que foi decidida cobrir (presenca + tipo estrutural); resta o passo 3 (outputSchema/structuredContent/annotations), mais as duas pendencias novas nao-bloqueantes desta entrada (enum, tipo escalar sob demanda). Vale perguntar ao Andre qual priorizar a seguir."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 422e13017433100edf4e509ce9882377ee14a1e4
pacote: "P03 sub-entrega 5/N -- checagem de VALOR (enum) do schema no preflight de tools/call, a candidata nova apontada como pendencia aberta pela sub-entrega 4/N; escolhida em vez do passo 3 do plano (outputSchema/structuredContent/annotations) por recomendacao propria, apos o Andre delegar explicitamente a decisao de prioridade ('com relacao a decisao, gostaria que voce seguisse a sua propria recomendacao')"
# inicio abaixo aproximado pelo timestamp do base_commit (merge da PR #230,
# diario da sub-entrega 4/N) -- a implementacao local comecou num trecho de
# sessao anterior a este sem timestamp proprio observavel por mim com
# precisao; nao invento um. Registro escrito apos o merge da PR #231
# confirmado por git fetch + git log de origin/main (nunca presumido da
# mensagem do Andre sozinha -- "pull request mesclado, pode conseguir
# conforme sua recomendacao", provavel transcricao por voz de "PR foi
# mesclado, pode seguir conforme sua recomendacao").
estado: validado
inicio: "2026-09-10T10:54:20Z"
fim: "2026-09-10T11:40:00Z"
arquivos_alterados:
  - functions/tools/registry.py (nova `valores_invalidos(tool_name, arguments) -> list[dict]`: cobre so propriedades de NIVEL SUPERIOR que declaram `enum` nao vazio -- 8 propriedades em 8 tools no catalogo de 105 schemas, todas `string`, sem sobreposicao com `tipos_invalidos` -- mesma fronteira estrutural da sub-entrega 4/N, mesmo fail-open. Tambem `_CAMPOS_COM_ENUM_TOLERANTE_A_CASE`, conjunto FECHADO de 4 pares (tool, campo) com tolerancia a case/espaco comprovada no handler, e `_bate_algum_valor_permitido`, o helper de comparacao -- ver decisoes.)
  - functions/mcp_server.py (novo `_erro_valores_invalidos`, wrapper que traduz `valores_invalidos` para o envelope MCP; ligado em `_handle_tools_call` nos mesmos dois pontos de insercao das duas checagens anteriores, logo depois de `_erro_tipos_invalidos` -- presenca, depois tipo, depois valor, nessa ordem, quando mais de uma se aplica ao mesmo payload)
  - functions/tools/schemas/obter_fila_atencao.json (enum de `origem` corrigido -- faltava `secretario_whatsapp`, achado da revisao adversarial, ver decisoes)
  - functions/test_validacao_argumentos.py (tres classes novas -- `TestValoresInvalidos`, `TestErroValoresInvalidos`, `TestIntegracaoValoresInvalidos` -- 42 -> 68 testes no arquivo; inclui paridade contra os 105 schemas reais do catalogo e os testes das tres rodadas de revisao adversarial)
decisoes:
  - id: p03-sub5-escopo-so-nivel-superior-mesmo-padrao-estrutural-da-sub4
    motivo: "Levantamento nos 105 schemas (10/09/2026) encontrou 8 propriedades de nivel superior, em 8 tools, com `enum` -- todas `string`, sem sobreposicao com a checagem de tipo estrutural (que so cobre `array`/`object`). Mesmo escopo deliberado de `tipos_invalidos`: so propriedades de NIVEL SUPERIOR -- o `enum` aninhado do campo `estado` de cada etapa dentro de `plano_acao`/`etapas` fica de fora, pela mesma razao estrutural (o campo que contem essa lista pode chegar como string JSON bruta; validar o conteudo aninhado viraria parser de plano, nao checagem de preflight)."
    autoridade: existente_ou_nova
  - id: p03-sub5-primeira-rodada-achou-schema-desatualizado-e-necessidade-de-tolerancia
    motivo: "PRIMEIRA rodada de revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao), dois achados reais antes de qualquer coisa ir pro Argos: (1) o schema de `obter_fila_atencao.origem` estava desatualizado -- faltava `secretario_whatsapp`, valor real que `atencao.ORIGENS` ja lista e que `secretario_whatsapp.py` ja grava em producao (`ORIGEM_SECRETARIO = 'secretario_whatsapp'`), com o handler (`atencao.coletar_fila_atencao`) fazendo um filtro cru do Firestore sem validacao alguma -- o preflight novo teria passado a rejeitar uma chamada hoje valida; corrigido acrescentando o valor ao schema. (2) 4 dos 8 handlers dos campos com `enum` (`decidir_promocao_autonomia.decisao`, `registrar_execucao_investimento.ativo`, `registrar_execucao_agente.status`, `solicitar_autorizacao_argos.tipo`) ja normalizam o valor recebido (`.strip().lower()`/`.upper()`/`.strip()`) antes de comparar -- uma comparacao exata bloquearia uma chamada com case ou espaco diferente que esses handlers aceitam hoje, mesma classe de regressao ja encontrada na sub-entrega 4/N (string JSON em `plano_acao`)."
    autoridade: existente_ou_nova
  - id: p03-sub5-segunda-rodada-sobre-o-fix-achou-regressao-pior-que-o-original
    motivo: "A correcao inicial do achado (2) tornou `valores_invalidos` tolerante a case/espaco para QUALQUER campo com `enum`. SEGUNDA rodada de revisao adversarial, desta vez dispatchada sobre essa correcao (nao sobre o diff original, mesmo padrao de duas rodadas ja usado nas sub-entregas 2/N e 4/N e na PR #219 do Argos): achou que essa tolerancia geral era, ela mesma, uma regressao nova e PIOR que o excesso de rigor original -- `obter_fila_atencao` (`estado`/`origem`) nao tem handler tolerante, `coletar_fila_atencao` usa o valor cru num filtro `==` do Firestore. Com tolerancia geral, `estado='ABERTO'` passaria pelo preflight e devolveria SILENCIOSAMENTE zero itens (o filtro nao bate com o valor armazenado, sempre minusculo), sem erro nenhum -- troca um erro claro por um resultado vazio indistinguivel de 'nada pendente'. Corrigido substituindo a tolerancia geral por `_CAMPOS_COM_ENUM_TOLERANTE_A_CASE`, lista FECHADA de 4 pares (tool, campo) com tolerancia comprovada no proprio handler -- mesmo padrao de `_CAMPOS_COM_TOLERANCIA_A_STRING_JSON` da sub-entrega 4/N, nunca uma regra geral."
    autoridade: existente_ou_nova
  - id: p03-sub5-terceira-rodada-sobre-o-segundo-fix-nao-achou-bug-so-lacuna-de-teste
    motivo: "TERCEIRA rodada de revisao adversarial, sobre a segunda correcao (a lista fechada), nao achou bug -- confirmou que a excecao e chave `(tool_name, campo)`, nao so campo, sem risco de vazar entre campos de mesmo nome em tools diferentes -- mas apontou uma lacuna de cobertura: nenhum teste provava explicitamente que `registrar_item_financeiro_v2.tipo` continua em modo exato apesar de compartilhar o nome do campo com o `solicitar_autorizacao_argos.tipo` tolerante. Corrigido acrescentando `test_tolerancia_a_case_nao_vaza_por_nome_de_campo_igual_em_outra_tool`. Nenhuma quarta rodada foi necessaria -- a disciplina de escalar rodadas so continua enquanto uma rodada acha algo real; esta nao achou."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "../venv/bin/python3 -m unittest test_validacao_argumentos -v (venv persistente do clone, fiel a requirements.txt desde a sub-entrega 3/N)"
    - "../venv/bin/python3 -m unittest discover -s . -p 'test_*.py' (suite completa)"
  resultados:
    - "Arquivo isolado: 68/68, 0 falhas, 0 erros (42 pre-existentes das sub-entregas 2/N e 4/N + 26 novos desta sub-entrega, distribuidos em TestValoresInvalidos/TestErroValoresInvalidos/TestIntegracaoValoresInvalidos)."
    - "Suite completa: 1651/1651, 0 falhas, 0 erros, sem regressao (1625 baseline confirmado pela sub-entrega 4/N + 26 novos aqui)."
evidencias:
  - "Levantamento programatico dos 105 schemas em tools/schemas/*.json (8 propriedades de nivel superior com `enum`, em 8 tools, todas `string`) antes de decidir o escopo, nao amostragem."
  - "Tres rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou das rodadas anteriores): a primeira achou o schema desatualizado e a necessidade de tolerancia a case/espaco; a segunda, sobre o fix da primeira, achou que a tolerancia geral era uma regressao nova e pior (silencio em `obter_fila_atencao`); a terceira, sobre o fix da segunda, nao achou bug -- so uma lacuna de cobertura de teste, fechada em seguida."
  - "Teste de paridade (`TestValoresInvalidos::test_paridade_com_todos_os_schemas_reais_do_catalogo`) cobre TODAS as 8 propriedades reais com `enum` no catalogo, nao so os exemplos escolhidos a dedo -- para cada uma, o primeiro valor permitido nunca e falso positivo e um valor sentinela fora do enum e sempre detectado."
  - "Todos os 4 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 4 batendo de primeira, sem drift de whitespace nem corrupcao."
  - "PR #231 aberta, com o relato completo das tres rodadas no corpo, e mesclada por Andre ('pull request mesclado, pode conseguir conforme sua recomendacao'), confirmado por git fetch + git log de origin/main: merge commit cbec822562abd719a31ca8742a2e78586502e602."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: checagem de valor (enum), a candidata nova apontada como pendencia aberta pela sub-entrega 4/N."
  - "ABERTA, deliberadamente: checagem de tipo ESCALAR (string/integer/number/boolean) continua fora de escopo -- so revisitar se um caso concreto mostrar que a tolerancia atual dos handlers virou problema real."
  - "ABERTA: passo 3 do plano (outputSchema/structuredContent/annotations nos caminhos compativeis) continua sem cobertura -- unico item claramente pendente do P03 depois desta entrada."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante."
proximo_pacote: "P03 -- com presenca, tipo estrutural e valor (enum) cobertos, resta so o passo 3 do plano (outputSchema/structuredContent/annotations nos caminhos compativeis) para o passo 2 do P03 ser considerado totalmente fechado em relacao ao levantamento original. Proxima sub-entrega natural, salvo nova prioridade do Andre."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 78d111e6b905d515a327a68542830887ca701845
pacote: "P03 sub-entrega 6/N -- passo 3 do plano (outputSchema/structuredContent/annotations/envelope), fatia inicial: campo `annotations` do protocolo MCP (`readOnlyHint`/`destructiveHint`) publicado em `tools/list`, derivado do inventario tipado da sub-entrega 1/N. Escolhida por recomendacao propria apos o Andre delegar a decisao de prioridade de novo ('esta mesclado pode prosseguir')."
estado: validado
inicio: "2026-09-10T11:45:00Z"
fim: "2026-09-10T12:20:00Z"
arquivos_alterados:
  - functions/tools/registry.py (nova `mcp_annotations(tool_name) -> dict` -- `readOnlyHint` de `leitura_escrita == LEITURA`; quando nao read-only, `destructiveHint` de `reversibilidade == IRREVERSIVEL` -- tratando `NAO_APLICA` como `REVERSIVEL` (False), ja que as 3 entradas `NAO_APLICA` em `LEITURA_E_ESCRITA` tem escrita passiva/idempotente, nunca o proposito da tool. Fail-open -- `{}` em `(AttributeError, TypeError)` ou tool sem entrada no inventario. `destructiveHint` OMITIDO, nao `False`, quando `readOnlyHint=true` -- so e significativo quando falso, por especificacao.)
  - functions/mcp_server.py (`_handle_tools_list` acrescenta `annotations` a cada tool publicada, so quando o dict nao e vazio -- aditivo, `_meta` needsConfirmation/mutates/voiceEnabled inalterado)
  - functions/tools/inventory.py (correcao de classificacao de `criar_rascunho_whatsapp`, REVERSIVEL -> IRREVERSIVEL -- achado da revisao adversarial, ver decisoes)
  - functions/test_mcp_annotations.py (novo -- 13 testes / 111+ subtestes -- `TestMcpAnnotations` cobre paridade completa, nao amostrada, contra as 105 entradas reais do inventario; `TestHandleToolsListAnnotations` cobre a ligacao ponta a ponta via `_handle_tools_list`)
decisoes:
  - id: p03-sub6-escopo-so-readonly-e-destructive-hint
    motivo: "P03 passo 3 pede outputSchema/structuredContent/annotations/envelope -- quatro pecas. Esta sub-entrega cobre so `annotations`, e dela so `readOnlyHint`/`destructiveHint`: sao os dois unicos hints que o inventario tipado da sub-entrega 1/N sustenta com confianca (leitura_escrita e reversibilidade, campos ja classificados por leitura direta da implementacao). `idempotentHint`/`openWorldHint` ficam de fora deliberadamente -- nenhum campo do inventario atual sustenta os dois, e um hint errado e pior que a omissao (a propria especificacao MCP ja assume o lado cauteloso -- destructiveHint/openWorldHint default true -- para quem nao declara ToolAnnotations). outputSchema/structuredContent/envelope seguem inteiramente fora: cada um exige um contrato de dados por tool, escopo maior e futuro."
    autoridade: existente_ou_nova
  - id: p03-sub6-primeira-rodada-achou-classificacao-inconsistente-em-criar_rascunho_whatsapp
    motivo: "PRIMEIRA rodada de revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao), um achado real antes de qualquer coisa ir pro Argos: `criar_rascunho_whatsapp` em tools/inventory.py estava classificada REVERSIVEL, apesar da propria nota ja dizer 'reversivel ... exceto tipos promovidos (liberam sozinhos apos a janela)' -- confirmado rastreando outbox_aprovacao.py: para tipos promovidos, o rascunho se entrega sozinho a um terceiro, irreversivelmente, sem nova confirmacao. Duas tools no mesmo arquivo com a MESMA forma de nuance (decidir_elevacao, decidir_promocao_autonomia) ja tratavam isso classificando a tool inteira como IRREVERSIVEL -- o lado conservador; a classificacao antiga de criar_rascunho_whatsapp divergia dessa convencao propria do arquivo e produzia destructiveHint=False enganoso via mcp_annotations, justamente no caso de risco real."
    autoridade: existente_ou_nova
  - id: p03-sub6-segunda-rodada-sobre-o-fix-nao-achou-bug-confirmou-sem-irmaos
    motivo: "SEGUNDA rodada de revisao adversarial, dispatchada sobre a correcao em si (nao o diff original, mesmo padrao das sub-entregas 2/N, 4/N, 5/N e da PR #219/#10 do Argos): confirmou consistencia interna do ajuste e, via varredura COMPLETA das 105 entradas do inventario (nao amostragem), confirmou que nenhuma outra entrada tem a mesma inconsistencia latente -- so 3 entradas tem a nuance 'irreversivel so para um subconjunto', e as tres ja ficam consistentemente IRREVERSIVEL apos esta correcao. Sinalizou salvar_memoria_global como um formato diferente, pre-existente e ja autodocumentado (nao acionavel, fora de escopo). Nenhum bug adicional -- sem necessidade de terceira rodada (criterio de parada ja estabelecido: so escalar enquanto uma rodada acha algo real)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "../venv/bin/python3 -m unittest test_mcp_annotations test_tool_inventory -v (venv persistente do clone)"
    - "../venv/bin/python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa)"
  resultados:
    - "test_mcp_annotations.py + test_tool_inventory.py isolados: 23 testes, OK."
    - "Suite completa: 1664/1664, 0 falhas, 0 erros, sem regressao (1651 baseline confirmado pela sub-entrega 5/N + 13 novos aqui)."
evidencias:
  - "Duas rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou da rodada anterior): a primeira achou a classificacao inconsistente de criar_rascunho_whatsapp antes de qualquer coisa ser enviada; a segunda, sobre a correcao, nao achou bug -- so confirmou, por varredura completa e nao amostragem, que nenhuma outra entrada do inventario tem a mesma inconsistencia."
  - "Teste de paridade (TestMcpAnnotations::test_paridade_com_todas_as_entradas_reais_do_inventario) cobre TODAS as 105 entradas reais do catalogo, nao so exemplos escolhidos a dedo."
  - "Todos os 4 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 4 batendo de primeira, sem drift de whitespace nem corrupcao. mcp_server.py (1513 linhas / 74744 bytes) lido em duas chamadas Read nao sobrepostas, borda a borda, antes do envio."
  - "PR #233 aberta, com o relato completo das duas rodadas no corpo, e mesclada por Andre ('Mesclado com sucesso, pode prosseguir para as proximas rodadas'), confirmado por git fetch + git log de origin/main: merge commit a24d7743694fefee5aaab8b3db311df5c102aceb."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: fatia `annotations` (readOnlyHint/destructiveHint) do passo 3 do P03."
  - "ABERTA, deliberadamente: `idempotentHint`/`openWorldHint` ficam fora -- precisam de investigacao dedicada por tool antes de qualquer classificacao, sem fonte de dados confiavel no inventario atual."
  - "ABERTA: `outputSchema`/`structuredContent`/envelope (as outras tres partes do passo 3 do plano) nao iniciadas -- cada uma exige definir um contrato de dados por tool, escopo bem maior."
  - "ABERTA, deliberadamente (herdada da sub-entrega 5/N): checagem de tipo ESCALAR continua fora de escopo."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidade de classificacao de gerar_relatorio; card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante."
proximo_pacote: "P03 passo 3 -- restam outputSchema/structuredContent/envelope, e os hints idempotentHint/openWorldHint (bloqueados por falta de fonte de dados confiavel). Proxima sub-entrega natural e provavelmente investigar idempotentHint/openWorldHint por tool, ou iniciar o contrato outputSchema para um subconjunto pequeno de tools, salvo nova prioridade do Andre."
```
---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 20a2b78513059e7c4a5c53f6fa9d3eaa99c0b7ab
pacote: "P03 sub-entrega 7/N -- openWorldHint (annotations MCP) em tools/list, via novo campo dominio_rede no inventario; passo 3 do plano, terceira fatia de annotations apos readOnlyHint/destructiveHint da sub-entrega 6/N"
# RECONCILIACAO RETROATIVA: esta sub-entrega foi implementada e mesclada
# (PR #235, merge 76e32be828ad0c9a57e580465539fd69c92558d0, em
# 10/09/2026 12h27 BRT) sem uma entrada propria neste arquivo no momento
# do envio -- a sessao daquele dia mudou de prioridade 13 segundos depois
# do merge (PR #237, inicio da demanda DEV-2026-0004, sem relacao com
# este plano) e nunca voltou a registrar. Mesma lacuna de registro ja
# vista e corrigida em P01 sub-entrega 8/N e P02 sub-entregas 18/N-19/N.
# Registrada agora, em 12/09/2026, pela tarefa agendada de avanco
# autonomo do plano.
estado: validado
inicio: "2026-09-10T13:05:07Z"
fim: "2026-09-10T15:27:13Z"
arquivos_alterados:
  - "functions/tools/inventory.py (novo enum DominioRede (FECHADO/ABERTO), campo opcional dominio_rede em ToolInventoryEntry; classificado para 21 das 28 tools com necessidade_de_rede=True -- 19 FECHADO, 2 ABERTO (pesquisar_internet, ler_pagina_web); 7 deixadas deliberadamente sem classificacao por ambiguidade real -- confirmar_acao, consultar_processo_sipac, acompanhar_processo_sipac, anexar_arquivo, e as 3 tools de investimentos)"
  - "functions/tools/registry.py (mcp_annotations passa a derivar openWorldHint -- FECHADO -> False, ABERTO -> True, None -> hint omitido/fail-open, cliente MCP cai no default cauteloso true da propria especificacao; docstring reescrita explicando por que dominio_rede != necessidade_de_rede direto)"
  - "functions/mcp_server.py (comentario de _handle_tools_list atualizado para citar openWorldHint; nenhuma mudanca de logica -- a publicacao de annotations ja estava ligada desde a sub-entrega 6/N)"
  - "functions/test_mcp_annotations.py (6 testes novos -- test_annotations_nunca_leva_idempotent_hint, test_dominio_rede_fechado_e_open_world_hint_false, test_dominio_rede_aberto_e_open_world_hint_true, test_dominio_rede_nao_classificado_omite_open_world_hint, test_dominio_aberto_chega_com_open_world_hint_true, test_dominio_ambiguo_chega_sem_open_world_hint -- em TestMcpAnnotations/TestHandleToolsListAnnotations)"
  - "functions/test_tool_inventory.py (2 testes novos -- test_dominio_rede_e_enum_valido_ou_ausente, test_dominio_rede_so_e_classificado_quando_ha_necessidade_de_rede -- paridade contra as 106 entradas reais do inventario)"
decisoes:
  - id: p03-sub7-openworldhint-de-dominio-rede-nao-de-necessidade-de-rede
    motivo: "`necessidade_de_rede` sozinho nao diferencia 'fala com um sistema externo fechado e conhecido' (a agenda do proprio dono via Google Calendar) de 'fala com um sistema externo imprevisivel' (a web aberta via pesquisar_internet). Mapear `necessidade_de_rede` direto para `openWorldHint` produziria metadado ERRADO para a maioria das tools com rede (Calendar, Gmail, Drive, Telegram, Gemini) -- pior que nao declarar nada, ja que um cliente MCP pode usar o hint para decidir se pede confirmacao extra. Por isso um campo novo (`dominio_rede`), classificado por leitura direta de cada handler, nao uma derivacao automatica de texto livre."
    autoridade: existente_ou_nova
  - id: p03-sub7-sete-tools-deliberadamente-sem-classificacao
    motivo: "`confirmar_acao` e um gate generico que delega para outra tool (sem dominio de rede proprio); `consultar_processo_sipac`/`acompanhar_processo_sipac` fazem scraping de portal institucional externo fora do controle do Hermes; `anexar_arquivo` e genuinamente misto (Drive sempre + URL arbitraria conforme a origem, fluxo `_de_url` com `urllib.request.urlopen` direto sobre URL do chamador); as 3 tools de investimentos dependem de servico externo que por sua vez busca dados de mercado (yfinance/SGS-Bacen) fora do controle direto do Hermes ou do proprio servico. Omitir e estritamente mais seguro que declarar um valor que pode estar errado."
    autoridade: existente_ou_nova
  - id: p03-sub7-revisao-adversarial-retroativa-apos-lacuna-de-processo
    motivo: "Ao contrario de praticamente toda sub-entrega anterior deste plano (2, 4, 5, 6 tem achado(s) de revisao adversarial documentado(s) em commit ou nesta propria entrada), o historico de commits da branch `claude/p03-sub7-open-world-hint` nao mostra nenhum commit do tipo 'corrige achado da revisao adversarial' -- nao ha evidencia de que uma rodada tenha rodado antes do merge. Em vez de presumir que rodou (ou inventar uma rodada retroativa fictícia), uma rodada de revisao adversarial independente (Agent tool, general-purpose, sem contexto da implementacao original) foi disparada agora, 12/09/2026, antes de registrar esta entrada -- cobrindo: (1) correcao das 21 classificacoes FECHADO/ABERTO contra o codigo real dos handlers, com atencao a tools que tocam conteudo de terceiros/arbitrario (`salvar_memoria_global`, `criar_rascunho_email`, `ler_documento_na_integra`); (2) se as 7 tools ambiguas realmente sao ambiguas; (3) lacuna de cobertura (alguma tool com necessidade_de_rede=True fora das duas listas); (4) seguranca do fail-open de `mcp_annotations`; (5) suite de testes completa. Resultado: nenhum achado real -- as 21 classificacoes conferem com o codigo real handler por handler, as 7 tools ambiguas sao genuinamente ambiguas (confirmado por leitura direta, ex.: `anexar_arquivo` tem caminho real de URL arbitraria), nenhuma tool ficou fora de cobertura (28 = 21 + 7, verificado programaticamente), e o fail-open e seguro (enum so preenchido por literal no proprio codigo-fonte, nunca desserializado de input externo). Uma observacao NAO-critica ficou registrada em pendencias."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "../venv/bin/python3 -m unittest test_mcp_annotations test_tool_inventory -v (venv persistente do clone)"
    - "../venv/bin/python3 -m unittest discover -s . -p 'test_*.py' (suite completa)"
  resultados:
    - "Arquivos do escopo isolados (verificado retroativamente em 12/09/2026): 30/30, 0 falhas, 0 erros -- inclui os 8 testes novos desta sub-entrega."
    - "Suite completa (verificado retroativamente em 12/09/2026): 1815/1815, 0 falhas, 0 erros. Nao da pra isolar com precisao o incremento desta sub-entrega dentro do total: entre a implementacao (10/09) e este registro (12/09), outra linha de trabalho sem relacao com este plano (demanda DEV-2026-0004) tambem mesclou testes novos em main -- o numero de hoje confirma ausencia de regressao, nao o delta exato desta sub-entrega isolada."
evidencias:
  - "Revisao adversarial retroativa (Agent tool, general-purpose, sem contexto da implementacao original), 12/09/2026: verificacao handler-a-handler das 21 classificacoes FECHADO/ABERTO (incluindo leitura direta de tools/hermes_tools.py, tools/telegram_extended.py, tools/criar_rascunho_email.py, tools/anexar_arquivo.py, tools/buscar_e_analisar_email.py, whatsapp_consolidation.py), confirmacao programatica de que as 28 tools com necessidade_de_rede=True se dividem exatamente em 21 classificadas + 7 ambiguas (nenhuma lacuna), e confirmacao de que o fail-open de mcp_annotations e seguro (DominioRede so populado por literal no codigo-fonte). Nenhum achado real; uma observacao nao-critica sobre criterio (ver pendencias)."
  - "Todos os 5 arquivos desta sub-entrega ja estavam mesclados em origin/main antes deste registro (PR #235) -- integridade de escrita via Argos nao se aplica retroativamente; a verificacao aqui foi de correcao funcional e de testes, nao de hash de transferencia."
  - "PR #235 mesclada por Andre, confirmado por git log de origin/main: merge commit 76e32be828ad0c9a57e580465539fd69c92558d0, 10/09/2026 12h27 BRT."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: fatia openWorldHint do passo 3 do P03 -- annotations agora cobre readOnlyHint + destructiveHint (sub6) + openWorldHint (sub7)."
  - "ABERTA, deliberadamente: idempotentHint continua fora de escopo -- precisa de investigacao dedicada por HANDLER (se repetir a chamada com os mesmos argumentos tem efeito adicional), nenhum campo do inventario atual registra isso."
  - "ABERTA: outputSchema/structuredContent/envelope (as outras tres partes do passo 3 do plano) nao iniciadas -- cada uma exige definir um contrato de dados por tool."
  - "ABERTA, nova, NAO-bloqueante (observacao da revisao retroativa): 5 das 7 tools deixadas sem dominio_rede (consultar_processo_sipac, acompanhar_processo_sipac, as 3 de investimentos) poderiam, pelo mesmo criterio aplicado a consultar_agenda/Gmail (destino de rede fixo e conhecido, independente do conteudo retornado), ser classificadas FECHADO em vez de ambiguas -- nao e erro (omitir nunca e pior que declarar errado), so uma inconsistencia de criterio defensavel, candidata a revisitar numa sub-entrega futura se fizer diferenca pratica."
  - "PROCESSO, novo: esta sub-entrega foi mesclada sem revisao adversarial documentada antes do merge -- unica excecao encontrada ao padrao do resto do plano. A partir da execucao autonoma agendada (3x/dia, iniciada em 12/09/2026), a rodada de revisao adversarial ANTES de abrir a PR volta a ser obrigatoria e deve ficar evidenciada nesta propria entrada (nao só presumida)."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante."
proximo_pacote: "P03 -- com readOnlyHint, destructiveHint e openWorldHint cobertos, resta do passo 3: outputSchema/structuredContent/envelope (nenhum iniciado) e idempotentHint (bloqueado por falta de investigacao por handler, nao por decisao). Proxima sub-entrega natural: uma fatia pequena de outputSchema para um subconjunto reduzido de tools, ou a investigacao dedicada de idempotentHint por handler -- a cargo da execucao autonoma agendada, salvo nova prioridade do Andre."
```
