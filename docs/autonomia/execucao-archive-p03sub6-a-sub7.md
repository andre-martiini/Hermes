# Arquivo de execução — P03 sub-entrega 6/N a 7/N

Blocos movidos de docs/autonomia/execucao.md em 13/09/2026, durante a tarefa agendada de avanço do plano de autonomia, preventivamente, ao acrescentar a entrada da sub-entrega P03 10/N (outputSchema/structuredContent para consultar_lista_compras) — o arquivo ativo ficaria acima de ~50KB sem re-arquivamento desde o oitavo arquivo de arquivo (execucao-archive-p03sub4-a-sub5.md). Nenhum conteúdo foi alterado — relocação, não edição. Cobre: P03 sub-entrega 6/N (annotations MCP — readOnlyHint/destructiveHint) e sub-entrega 7/N (annotations MCP — openWorldHint via novo campo dominio_rede no inventário).

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
