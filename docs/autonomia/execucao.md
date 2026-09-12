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
entrada sem re-arquivamento).** Nenhum conteúdo foi perdido; é
uma relocação, não uma edição. Este arquivo continua sendo a fonte de
verdade para tudo a partir da sub-entrega P03 6/N em diante.

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

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 1cdbf7e74d0617cd0ea6ab61616897d7e97b5307
pacote: "P03 sub-entrega 8/N -- outputSchema/structuredContent (passo 3 do plano), fatia inicial: contrato de dados publicado em tools/list e refletido em tools/call, so para calculadora (candidato de menor risco -- pura, deterministica, sem rede nem Firestore)"
estado: pronto_para_revisao
inicio: "2026-09-12T15:00:00Z"
fim: "2026-09-12T15:51:52Z"
arquivos_alterados:
  - "functions/tools/registry.py (nova `_OUTPUT_SCHEMAS` -- lista FECHADA, mesmo padrao de `_CAMPOS_COM_TOLERANCIA_A_STRING_JSON`/`_CAMPOS_COM_ENUM_TOLERANTE_A_CASE` ja existentes neste arquivo -- e nova `output_schema(tool_name) -> dict | None`, hoje so com entrada para `calculadora`: `{expressao: str (obrigatorio), resultado: str, erro: str}`, `additionalProperties: false`)"
  - "functions/mcp_server.py (`_handle_tools_list` publica `outputSchema` no objeto Tool quando `registry.output_schema(name)` existe, campo opcional omitido -- nao null -- quando ausente, mesma convencao de `annotations`; `_handle_tools_call` inclui `structuredContent` no envelope de `tools/call` quando o executor devolveu um dict E a tool tem outputSchema publicado, reconstruido do `text` ja serializado com `json.dumps(..., default=str)` -- nunca do dict cru do executor -- ver decisoes)"
  - "functions/test_output_schema.py (novo -- 14 testes em 3 classes: TestOutputSchema com paridade contra as 105 tools reais do catalogo, TestHandleToolsListOutputSchema ponta a ponta em tools/list, TestIntegracaoHandleToolsCallStructuredContent ponta a ponta em tools/call incluindo o teste de nao-vacuidade do achado da revisao adversarial)"
decisoes:
  - id: p03-sub8-calculadora-primeira-tool-com-outputschema
    motivo: "outputSchema exige definir um CONTRATO DE DADOS por tool -- ao contrario de `annotations` (sub-entregas 6/N-7/N), que deriva de campos ja classificados no inventario para as 105 tools de uma vez, nao ha atalho generico aqui: serializar qualquer dict de retorno como 'o schema' seria publicar um contrato inventado, nunca verificado contra a forma real do resultado. `calculadora` escolhida como primeira por ser o candidato de menor risco do catalogo -- pura, deterministica, sem rede nem Firestore (inventario: necessidade_de_rede=False, verificador='deterministico, recomputavel pelo chamador'), sempre devolve um dict achatado com EXATAMENTE duas formas possiveis (sucesso: expressao+resultado; falha: expressao+erro), nunca as duas juntas, nunca um terceiro campo. Nao exigiu investigar comportamento assincrono, paginacao nem variacao de forma por argumento -- ao contrario da maioria das outras ~104 tools do catalogo, que ficam deliberadamente de fora por enquanto."
    autoridade: existente_ou_nova
  - id: p03-sub8-primeira-rodada-achou-crash-latente-no-mecanismo-geral
    motivo: "PRIMEIRA rodada de revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao), achado real ANTES de qualquer coisa ir pro Argos: a implementacao original fazia `estruturado = result` (o dict cru do executor) em vez de derivar de `text` (que ja passa por `json.dumps(..., default=str)`). O envelope inteiro (incluindo `structuredContent`) e reserializado mais abaixo na pilha, em `_json_response`, via `json.dumps(payload, ensure_ascii=False)` -- SEM `default=str` e FORA de qualquer try/except que proteja o cliente de um erro cru. Para `calculadora` isso nunca falha hoje (o handler ja forca `str()` em tudo), mas o MECANISMO GERAL que esta sub-entrega introduz ficaria com um bug latente: a proxima tool a ganhar outputSchema cujo handler devolvesse um valor nao-JSON-nativo (datetime, Timestamp do Firestore, Decimal -- comuns neste catalogo) quebraria essa serializacao final com um TypeError nao tratado. Corrigido: `estruturado` passou a vir de `json.loads(text)`, nunca do `result` cru. Comprovado nao-vacuo empiricamente (mesmo padrao usado na PR #10 do Argos): revertendo o fix localmente, o novo teste `test_valor_nao_serializavel_no_dict_nao_quebra_structured_content` falha de verdade (`AssertionError: datetime.date(2026, 9, 12) != '2026-09-12'`); com o fix, passa."
    autoridade: existente_ou_nova
  - id: p03-sub8-segunda-rodada-sobre-o-fix-achou-escopo-largo-demais
    motivo: "SEGUNDA rodada de revisao adversarial, sobre o fix da primeira (mesmo padrao das sub-entregas 4/N-6/N e da PR #219/#10 do Argos): achou que a guarda `isinstance(result, dict)` sozinha fazia o round-trip `json.dumps`->`json.loads` rodar em TODA chamada de tool que devolve dict (a maioria das 105 do catalogo), nao so `calculadora` -- CPU gasta sem necessidade nas outras ~104, so pra descartar o resultado logo depois porque `registry.output_schema(name)` e None pra elas. Corrigido: guarda passou a `isinstance(result, dict) and registry.output_schema(name)`, e o check redundante mais abaixo (que checava `output_schema` de novo antes de anexar `structuredContent` ao envelope) foi simplificado para so `estruturado is not None`, ja que a segunda condicao ficou implicita na primeira."
    autoridade: existente_ou_nova
  - id: p03-sub8-terceira-rodada-sobre-o-segundo-fix-nao-achou-nada
    motivo: "TERCEIRA rodada de revisao adversarial, sobre o fix da segunda: percorreu explicitamente todos os caminhos possiveis de `_handle_tools_call` (sucesso com/sem schema, erro-dict com/sem schema, resultado string, excecao do executor, ToolNotAvailable) e confirmou cada um correto; confirmou que `registry.output_schema` deixou de ser chamado de forma redundante dentro da mesma funcao; confirmou que o teste que cobre 'tool sem outputSchema mas resultado e dict' (`test_tool_sem_output_schema_nunca_leva_structured_content_mesmo_com_dict`) de fato exercita o caminho corrigido, nao uma suposicao datada. Nao achou nada -- parada aqui, conforme a disciplina (escalar so enquanto uma rodada acha algo real; 'nao achou nada' e resultado valido, nao inventado pra parecer completo)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "python3 -m venv + pip install -r requirements.txt (ambiente limpo, clonado via credenciais do sandbox -- primeira vez nesta sessao que a suite completa roda de fato, nao so os arquivos do escopo)"
    - "python3 -m unittest test_output_schema -v (arquivo isolado)"
    - "python3 -m unittest discover -s . -p 'test_*.py' -q (suite completa, antes e depois de cada rodada de correcao)"
  resultados:
    - "Baseline (antes de qualquer mudanca desta sub-entrega, clone limpo de origin/main): 1815/1815, 0 falhas, 0 erros -- confirma o numero ja registrado pela sub-entrega 7/N."
    - "Arquivo isolado test_output_schema.py: 14/14, 0 falhas, 0 erros."
    - "Suite completa apos a implementacao e as 3 rodadas de correcao: 1829/1829, 0 falhas, 0 erros, sem regressao (1815 baseline + 14 novos)."
evidencias:
  - "Tres rodadas de revisao adversarial independente (Agent tool, general-purpose, cada uma sem contexto da implementacao ou das rodadas anteriores): a primeira achou o bug latente de serializacao no mecanismo geral (ver decisoes); a segunda, sobre o fix da primeira, achou que o escopo do round-trip json.dumps/json.loads era mais largo que o pretendido; a terceira, sobre o fix da segunda, nao achou nada."
  - "Teste de nao-vacuidade: o teste que prova a correcao do achado da 1a rodada foi executado tambem SEM o fix (revertido localmente por 1 linha), confirmando que falha de verdade nesse caso e so passa com a correcao aplicada -- nao e um teste vazio."
  - "Teste de paridade (TestOutputSchema::test_paridade_apenas_calculadora_tem_output_schema_hoje) cobre TODAS as tools reais do catalogo (registry.list_tool_names()), nao so calculadora escolhida a dedo -- confirma que a lista fechada nao vazou para nenhuma outra tool."
  - "Todos os 3 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- os 3 batendo de primeira, sem drift de whitespace nem corrupcao. Verificacao adicional, mais forte que o hash isolado do proprio Argos: git fetch do branch remoto (refspec explicito) + git show origin/<branch>:<path> | git hash-object --stdin comparado ao arquivo local, para os 3 arquivos -- identico."
  - "Sanity check do PR: changed_files=3, additions=355, deletions=1 no retorno de argos_criar_pr_repositorio -- bate exatamente com git diff --stat main origin/<branch> rodado localmente antes de abrir o PR, sem arquivo extra nem reconstrucao acidental."
  - "PR #251 aberta (https://github.com/andre-martiini/Hermes/pull/251), com o relato completo das 3 rodadas no corpo -- AINDA NAO MESCLADA, aguardando revisao e merge manual do Andre."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "ABERTA: PR #251 aguardando merge do Andre -- esta entrada esta em pronto_para_revisao, nao validado; uma execucao futura desta tarefa agendada deve conferir se foi mesclada (git fetch + git log de origin/main) e atualizar estado/evidencias/merge_commit aqui, sem reescrever um bloco ja validado."
  - "ABERTA, nova (achado da 1a rodada de revisao adversarial, aceito como limitacao deliberada por enquanto): `structuredContent` so chega no caminho de EXECUCAO DIRETA de `_handle_tools_call` -- nao chega nos caminhos que usam `_text_result` (confirmacao pendente/negada, job assincrono, `confirmar_acao`). `calculadora` nunca passa por eles hoje (nao esta em `_CONFIRMACAO_OBRIGATORIA` nem em `_ASYNC_TOOLS`), mas `_exige_confirmacao` tambem consulta `system/mcp_access.confirm_tools` em runtime (Firestore) -- se um dia alguem configurar `calculadora` la, as chamadas sairiam sem `structuredContent` mesmo com outputSchema continuando anunciado em tools/list. Fechar isso direito exigiria levar `structuredContent` para dentro de `_text_result`, usada por fluxos bem mais amplos que so calculadora -- fora do escopo desta fatia pequena."
  - "ABERTA, deliberadamente: outputSchema para as demais ~104 tools do catalogo continua fora de escopo -- cada uma exige investigar a forma real do handler antes de publicar um contrato, mesma disciplina das outras excecoes fechadas deste modulo. Candidatas naturais para a proxima fatia: tools de leitura simples com forma de retorno ja estavel (ex.: consultar_saude, obter_acao)."
  - "ABERTA, deliberadamente (herdada da sub-entrega 7/N): idempotentHint continua fora de escopo -- precisa de investigacao dedicada por HANDLER, nenhum campo do inventario atual registra isso."
  - "ABERTA: a fatia `envelope` do passo 3 do plano (alem de outputSchema/structuredContent/annotations, ja cobertos em parte) nao foi investigada nesta sub-entrega."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante; inconsistencia de criterio nao-bloqueante em 5 das 7 tools sem dominio_rede classificado (sub-entrega 7/N)."
proximo_pacote: "P03 -- aguardando merge da PR #251 (outputSchema/structuredContent para calculadora). Depois de mesclada: uma fatia pequena adicional de outputSchema para outro subconjunto reduzido de tools de leitura simples, ou a investigacao dedicada de idempotentHint por handler, ou perguntar ao Andre se ele prefere avancar direto para P04 (pedidos duraveis/lease/ledger) dado que o passo 2 do P03 ja esta totalmente fechado e o passo 3 tem uma primeira fatia real em revisao -- a cargo da execucao autonoma agendada, salvo nova prioridade do Andre."
```
