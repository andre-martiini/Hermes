# Arquivo de execução — P03 sub-entrega 4/N a 5/N

Blocos movidos de docs/autonomia/execucao.md em 12/09/2026, durante a tarefa agendada de avanço do plano de autonomia, preventivamente, ao acrescentar a entrada da sub-entrega P03 8/N (outputSchema/structuredContent para calculadora) — o arquivo ativo ficaria acima de ~50KB sem re-arquivamento desde o sétimo arquivo de arquivo (execucao-archive-p02sub18-a-p03sub3.md). Nenhum conteúdo foi alterado — relocação, não edição. Cobre: P03 sub-entrega 4/N (checagem de TIPO estrutural array/object no preflight de tools/call) e sub-entrega 5/N (checagem de VALOR/enum no mesmo preflight).

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
