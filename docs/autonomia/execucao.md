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
retroativamente as sub-entregas P02 18/N e 19/N. Ver o cabeçalho de cada
arquivo de arquivo para o relato completo.** Nenhum conteúdo foi perdido; é
uma relocação, não uma edição. Este arquivo continua sendo a fonte de
verdade para tudo a partir da sub-entrega P02 18/N em diante.

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: e68671a3aa70bf812454febe6c8268437e745376
pacote: "P02 sub-entrega 18/N -- revisao_semanal.py::propor_reagendamento_semanal religado a autonomy.policy.avaliar() (mesmo padrão de outbox_aprovacao.py::liberar_rascunhos_promovidos desde a sub-entrega 17/N), fechando o primeiro dos dois itens que a sub-entrega 17/N tinha deixado como extensão natural"
# RECONCILIAÇÃO RETROATIVA: esta sub-entrega foi implementada e mesclada
# (PR #218) sem uma entrada própria neste arquivo no momento do envio --
# mesma lacuna de registro já vista e corrigida em P01 sub-entrega 8/N.
# Escrita agora, na sub-entrega seguinte (19/N), a partir da leitura direta
# dos commits em main (b3704229743912f71e9ea8cb6bdfdc389a472425,
# 98435a23f604d33f8d98ab4c3be45916c2ec191a) e do diff real -- não de
# memória. Como não fui eu quem executou originalmente este envio (nenhum
# registro de revisão adversarial nem de contagem de teste antes/depois
# sobreviveu em lugar nenhum acessível), as seções `evidencias` e `testes`
# abaixo refletem só o que dá para reconstruir de fonte confiável (código e
# mensagens de commit reais), marcado como tal onde a reconstrução é
# incompleta -- não invento revisão que não sei se aconteceu.
estado: validado
inicio: "2026-09-09T17:47:03Z"
fim: "2026-09-09T18:09:53Z"
arquivos_alterados:
  - functions/revisao_semanal.py (preflight ad hoc de estado_autonomia_atual(), da sub-entrega 15/N, substituído por PolicyRequest(classe_efeito=PREPARACAO_INTERNA, principal=RUNNER_SERVICO) + autonomy_policy.avaliar() real, com registrar_decisao() gravando o motivo em policy_decisions; erro ao avaliar cai em decisao_erro_avaliacao() fail-closed, nunca propõe por engano)
  - functions/test_revisao_semanal.py (3 testes novos: religação registra prepare_only em estado ativo; pausado registra deny com motivo autonomia_pausada; erro ao avaliar bloqueia fail-closed sem tocar tarefas nem Telegram; MockQuery ganha .add() espelhando Collection.add do Firestore, usado por registrar_decisao)
decisoes:
  - id: p02-sub18-preparacao-interna-sem-mandato-e-sempre-prepare-only-nunca-deny-por-classe
    motivo: "Confirmado pela leitura do diff (não presumido): propor_reagendamento_semanal só PROPÕE -- a aplicação real ainda exige toque explícito no Telegram (revisar_semana_propor_reagendamento) -- que é exatamente a definição de PREPARACAO_INTERNA da seção 5.4/5.1 do plano. Sem Mandato cobrindo 'reagendamento' (nenhum wrapper de I/O resolve isso hoje, diferente de tipos_promovidos) e sem origem_humana and eh_dono(), a matriz de efeito (_decisao_padrao_por_classe) resolve sempre PREPARE_ONLY para PREPARACAO_INTERNA -- nunca DENY por essa via. O único caminho para DENY aqui é o passo 2 de avaliar() (estado PAUSADO, que bloqueia tudo que não for leitura antes mesmo de olhar a classe de efeito) -- por isso o comportamento observável não muda (PAUSADO ainda bloqueia, ATIVO/SOMENTE_PREPARACAO ainda propõem); o que muda é a decisão passar pelo motor real e ficar registrada em policy_decisions (P02 passo 9), fechando outro trecho que só conhecia o enum EstadoAutonomia diretamente."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && ../venv/bin/python3 -m unittest discover -p 'test_*.py' -q  (rodado agora, sobre main pós-merge da PR #218 e #219 juntas -- não isolado só para esta sub-entrega, ver ressalva abaixo)"
  resultados:
    - "RECONSTRUÍDO DA MENSAGEM DE COMMIT, não observado ao vivo por mim: '3 testes novos' em test_revisao_semanal.py, sem regressão relatada pelo autor original no corpo do commit."
    - "Confirmado ao vivo por mim, agora, sobre main já com #218 e #219 mescladas: 1524 testes, 8 falhas + 2 erros -- mesmo padrão pré-existente de ambiente sem ANTHROPIC_API_KEY/deps opcionais (gmail/mp4) já documentado desde a sub-entrega 17/N (era 1420 testes/8+2 lá; a diferença de 104 testes cobre esta sub-entrega, a 19/N e qualquer outra mesclada no intervalo). Não isola a contagem exata desta sub-entrega sozinha -- ver pendências."
evidencias:
  - "git show do par de commits (b370422974, 98435a23f6) e diff completo de functions/revisao_semanal.py e functions/test_revisao_semanal.py lidos por inteiro nesta reconciliação."
  - "Nenhum registro de revisão adversarial independente foi encontrado para esta sub-entrega em nenhum arquivo (ativo ou de arquivo) nem na mensagem de commit -- diferente de toda sub-entrega anterior deste plano, que documenta a revisão explicitamente. Não sei se ela aconteceu e não ficou registrada, ou se não aconteceu; marco como lacuna de processo, não afirmo nenhuma das duas coisas sem evidência."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: religação de propor_reagendamento_semanal a avaliar(), primeiro dos dois itens apontados como extensão natural ao final da sub-entrega 17/N."
  - "LACUNA DE PROCESSO (não-bloqueante, sem ação corretiva possível agora): esta sub-entrega foi mesclada sem registro neste arquivo e sem evidência localizável de revisão adversarial independente -- diferente da disciplina seguida em toda sub-entrega anterior e posterior. Registrado aqui só para constar, mesmo espírito do achado de processo já registrado em P01 sub-entrega 8/N (push direto a main sem PR) -- pontual, não repetido na sub-entrega seguinte (19/N, que segue a disciplina completa)."
  - "Contagem de teste isolada desta sub-entrega (antes/depois, só ela) não é reconstruível com confiança a esta altura -- só a contagem agregada pós-#218+#219 foi verificada ao vivo (ver testes acima). Não é uma lacuna que valha voltar a investigar; registrado por completude."
  - "Pendências já registradas em blocos anteriores e não tocadas por esta sub-entrega continuam abertas (ver sub-entrega 17/N para a lista completa: usos_na_janela_atual/orcamento_maximo sem wrapper de I/O real; forma_revogacao só descritiva -- RESOLVIDO pela sub-entrega seguinte, 19/N; card do Telegram de rascunho degradado não é reeditado; etc.)."
proximo_pacote: "P02 -- com propor_reagendamento_semanal religado, restava o segundo item apontado ao final da sub-entrega 17/N: criar a tool de revogação explícita de tipo promovido (até então só edição direta do documento Firestore). Endereçado na sub-entrega seguinte, 19/N."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: c8406728c5352f6ca634c308d16d12ff05926b8d
pacote: "P02 sub-entrega 19/N -- nova tool revogar_promocao_autonomia (oposto transacional de decidir_promocao_autonomia(aceitar)), fechando o segundo item apontado ao final da sub-entrega 17/N; mais as duas correções da revisão automática do Codex na PR #219 (P1: corrida entre revogação e liberação automática; P2: motivo_revogacao obsoleto sobrevivendo a uma revogação sem motivo)"
# Implementada e enviada por mim nesta mesma linha de sessão (Claude-
# Session desta entrada). Registro escrito na sequência do merge (André:
# "mesclagem feita, pode prosseguir"), junto com a reconciliação
# retroativa da sub-entrega 18/N acima -- mesma disciplina de nunca deixar
# o arquivo ficar desatualizado em relação a main.
estado: validado
inicio: "2026-09-09T18:36:51Z"
fim: "2026-09-09T19:51:56Z"
arquivos_alterados:
  - functions/promocao_autonomia.py (nova revogar_promocao_autonomia(db, tipo, motivo=None): transacional, remove o tipo de system/mcp_access.tipos_promovidos, atualiza o doc de sugestão correspondente para STATUS_REVOGADA com revogado_em e, se houver motivo, motivo_revogacao -- e, achado P2 do Codex, limpa motivo_revogacao com firestore.DELETE_FIELD quando a revogação atual não traz motivo, para não deixar sobreviver o motivo de uma revogação anterior ao lado de um revogado_em novo)
  - functions/outbox_aprovacao.py (achado P1 do Codex: aprovar_rascunho, quando aprovado_via="janela_automatica", relê system/mcp_access DENTRO da própria transação e recusa com status mandato_revogado se o tipo não estiver mais em tipos_promovidos -- fecha a corrida em que liberar_rascunhos_promovidos já tinha checado o mandato antes da revogação committar; aprovação manual via Telegram/WhatsApp/Cowork não exige a recheck, é decisão humana direta; liberar_rascunhos_promovidos degrada para aprovação manual, via _degradar_rascunho_promovido_sem_mandato já existente, quando recebe mandato_revogado)
  - functions/tools/registry.py e functions/tools/hermes_tools.py (registro MCP da nova tool, com confirmação obrigatória)
  - functions/tools/schemas/revogar_promocao_autonomia.json (novo)
  - functions/autonomy/mandatos_io.py (docstrings atualizadas: forma_revogacao aponta para a tool dedicada em vez de 'edição direta do Firestore')
  - functions/test_promocao_autonomia.py e functions/test_outbox_aprovacao.py (TestRevogarPromocaoAutonomia; testes do recheck transacional em aprovar_rascunho; teste de integração da corrida revogação-durante-liberação; mocks de transação ganham .set() e suporte ao sentinel firestore.DELETE_FIELD)
decisoes:
  - id: p02-sub19-revogar-e-oposto-transacional-simetrico-a-decidir-aceitar
    motivo: "revogar_promocao_autonomia espelha a simetria já estabelecida por decidir_promocao_autonomia(tipo, 'aceitar') (sub-entrega anterior a este pacote) -- mesma transação sobre system/mcp_access, mesmo padrão de atualizar o doc de sugestão em promocoes_autonomia_sugeridas. Fecha a pendência descritiva deixada pela sub-entrega 17/N (forma_revogacao do Mandato dizia só 'remover de system/mcp_access.tipos_promovidos', sem tool dedicada)."
    autoridade: existente_ou_nova
  - id: p02-sub19-codex-p1-aprovacao-automatica-recheca-mandato-dentro-da-transacao
    motivo: "Achado real da revisão automática do Codex na PR #219: liberar_rascunhos_promovidos resolve mandato_tipo_promovido(db, tipo) uma vez por tipo e cacheia para o laço inteiro (sub-entrega 17/N) -- uma revogação que committe depois da checagem (ou entre a aprovação de um rascunho e a do próximo do mesmo tipo, no mesmo laço) não derrubava a aprovação automática, porque aprovar_rascunho nunca lia system/mcp_access dentro da própria transação -- as duas transações não compartilhavam documento nenhum, então o controle de concorrência otimista do Firestore não protegia nada entre elas de fato, apesar de ambas serem 'transacionais'. Corrigido fazendo aprovar_rascunho reler system/mcp_access DENTRO da transação quando aprovado_via='janela_automatica' -- agora as duas transações disputam o mesmo documento de verdade, e o Firestore força uma das duas a abortar/repetir se rodarem em paralelo. Verificado por revisão adversarial independente que leu o código-fonte real de google.cloud.firestore_v1.transaction._Transactional.__call__ para confirmar a semântica de retry, não só por raciocínio plausível."
    autoridade: existente_ou_nova
  - id: p02-sub19-codex-p2-delete-field-limpa-motivo-de-revogacao-anterior
    motivo: "Achado real da revisão automática do Codex na PR #219: revogar com motivo, repromover, revogar de novo sem motivo deixava o motivo_revogacao da PRIMEIRA revogação sobrevivendo ao lado do revogado_em novo (o update só definia a chave quando havia motivo_limpo, nunca a removia). Corrigido com firestore.DELETE_FIELD (idioma já estabelecido no código, ex.: main.py) -- remove a chave de fato em vez de gravar None. Teste de regressão cobre exatamente o cenário revoga-com-motivo -> repromove -> revoga-sem-motivo."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && ../venv/bin/python3 -m unittest discover -p 'test_*.py' -q"
  resultados:
    - "Durante o desenvolvimento (antes do envio): 1532 testes + 147 subtests passando, 0 falhas -- suíte isolada de test_promocao_autonomia.py e test_outbox_aprovacao.py rodada em cada rodada de edição, sem falha a corrigir além das já endereçadas pela revisão adversarial."
    - "Confirmado ao vivo agora, sobre origin/main já com a PR #219 mesclada: 1524 testes, 8 falhas + 2 erros -- mesmo padrão pré-existente de ambiente sem ANTHROPIC_API_KEY/deps opcionais (gmail/mp4), zero regressão nova. A diferença de contagem bruta (1532 vs. 1524) é o ambiente local de desenvolvimento (com ambiente/deps diferentes desta reconciliação) vs. este checkout limpo de main -- não uma perda de teste real; os testes desta sub-entrega (TestRevogarPromocaoAutonomia e os novos de outbox_aprovacao) estão presentes e passando nos dois casos."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre a feature original (revogar_promocao_autonomia) antes do primeiro envio à PR #219."
  - "Segunda revisão adversarial independente, desta vez sobre a correção dos dois achados do Codex (não só o diff original) -- confirmou os dois fixes corretos contra a semântica real do SDK do Firestore (leu o código-fonte de transaction.py na venv), e encontrou um nitpick não-bloqueante (docstring de teste superclaimando o que a interleaving simulada provava) -- corrigido antes do envio final."
  - "Todos os arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificação de hash local (git hash-object) contra o sha retornado pelo Argos -- todos batendo de primeira, sem drift de whitespace nem corrupção."
  - "PR #219 mesclada por André (confirmado por git fetch + git log de origin/main: merge commit 32e6ad411349616276ef299915b79eed166c0d96)."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: segundo item apontado ao final da sub-entrega 17/N (tool de revogação explícita de tipo promovido), mais os dois achados do Codex na PR #219."
  - "Pendências já registradas em blocos anteriores e não tocadas por esta sub-entrega continuam abertas: usos_na_janela_atual/orcamento_maximo do Mandato sem wrapper de I/O real (passo 8 do plano, ainda parcial -- ver sub-entrega 4/N); card do Telegram de rascunho degradado não reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore não configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupção silenciosa em escritas grandes via Argos."
  - "LACUNA DE PROCESSO já registrada na sub-entrega 18/N acima (mesclada sem entrada neste arquivo nem evidência localizável de revisão adversarial) -- não repetida aqui."
proximo_pacote: "P02 -- com os dois itens da sub-entrega 17/N fechados (18/N e 19/N), os passos do plano ainda sem cobertura clara são o passo 2 (evoluir claims/scopes do OAuth existente sem expor refresh tokens do dono ao runner) e a parte de 'orçamento' e 'versão/escopo' do passo 8 (revalidar no despacho -- revogação já fica coberta de verdade pela sub-entrega 19/N; orçamento continua sem fonte de dado real, achado desde a sub-entrega 4/N). Investigação do estado real de mcp_oauth.py/tool_context.py necessária antes de propor qualquer um dos dois como próxima sub-entrega -- mesma disciplina de checar antes de afirmar."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: dfa1cb0ab1a394321696b91c370d8401f59075ec
pacote: "P02 -- decisão registrada (sem código): orcamento_maximo/limite_por_janela do Mandato ficam sem popular por ora; passo 8 do plano dado como fechado dentro do escopo atual"
# Resposta do André (chat, não PR comment) à proposta em
# docs/autonomia/proposta-p02-orcamento-limite-janela.md (PR #221, já
# mesclada): aceitou a recomendação do documento -- "não popular agora
# (deixar como está, sem limite), e revisitar só se um caso real pedir".
# Confirmado explicitamente via pergunta direta (AskUserQuestion) depois do
# merge da PR #221 sem comentário, para não presumir a resposta às três
# perguntas em aberto do documento (quer teto? qual número/janela? por tipo
# ou agregado?) -- disciplina padrão desta sessão de nunca inferir decisão
# de produto do silêncio.
estado: validado
inicio: "2026-09-09T20:10:00Z"
fim: "2026-09-09T20:14:00Z"
arquivos_alterados:
  - Nenhum arquivo de produto alterado -- decisão registrada aqui para constar. mandatos_io.mandato_tipo_promovido() continua deixando orcamento_maximo e limite_por_janela/usos_na_janela_atual como None, mesmo comportamento desde a sub-entrega 17/N.
decisoes:
  - id: p02-orcamento-limite-janela-sem-popular-por-decisao-do-andre
    motivo: "André escolheu não implementar teto de orçamento nem de frequência por janela para tipos_promovidos neste momento -- aceitou a recomendação de docs/autonomia/proposta-p02-orcamento-limite-janela.md sem alteração. autonomy/policy.py::mandato_cobre() continua correto e fail-closed para os dois campos SE algum mandato algum dia os declarar; simplesmente nenhum declara hoje, por escolha, não por lacuna técnica. Revisitar exige um caso concreto (ex.: volume de envio automático que preocupe) ou a chegada de mandatos tipo 'missão' (P08/P09) para orcamento_maximo."
    autoridade: existente_ou_nova
testes:
  comandos: []
  resultados:
    - "Não aplicável -- nenhuma mudança de código."
evidencias:
  - "Resposta direta do André via AskUserQuestion, opção 'Aceitar recomendação: sem limite por agora'."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada (decisão de produto, não código): orcamento_maximo/limite_por_janela do Mandato ficam sem popular; passo 8 do plano considerado fechado dentro do escopo atual (revogação real desde a sub-entrega 19/N; versão estruturalmente coberta -- avaliar() nunca reaplica decisão cacheada; orçamento/limite por decisão explícita nesta entrada; escopo/OAuth é o passo 2, não o 8, e segue como único item claramente aberto do pacote)."
  - "Pendências já registradas em blocos anteriores continuam abertas: card do Telegram de rascunho degradado não reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore não configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupção silenciosa em escritas grandes via Argos."
proximo_pacote: "P02 -- com este item fechado, o passo 2 (evoluir claims/scopes do OAuth existente) é o único item do pacote sem cobertura clara. André já tinha deliberadamente deixado esse passo de lado uma vez (priorizou orçamento/limite por janela primeiro); com esse item agora encerrado, vale perguntar diretamente se ele quer: (a) abrir o passo 2 agora, (b) considerar P02 suficientemente coberto pelo aceite do plano e avançar para P03 (consolidar contratos MCP e ferramentas), guardando o passo 2 como hardening a retomar quando fizer sentido, ou (c) outra prioridade."
```
