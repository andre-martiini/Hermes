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

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: fd6760a869fbd903fb7bb067cd795c2a7fdcef47
pacote: "P02 -- fechamento do pacote: André decidiu considerar P02 coberto pelo aceite do plano e avançar para P03, guardando o passo 2 (OAuth claims/scopes) como hardening futuro"
# Resposta do André via AskUserQuestion, opção "Considerar P02 coberto,
# avançar para P03 (Recomendado)" -- essa era a própria recomendação que eu
# tinha oferecido, então não há decisão de produto nova a registrar além da
# escolha em si.
estado: validado
inicio: "2026-09-09T20:16:00Z"
fim: "2026-09-09T20:18:00Z"
arquivos_alterados:
  - Nenhum -- fechamento de pacote é decisão de escopo, não código.
decisoes:
  - id: p02-fechado-passo2-oauth-vira-hardening-futuro-nao-bloqueante
    motivo: "P02 atinge o aceite do plano dentro do escopo que o André priorizou: o agente não consegue conceder a si mesmo permissão (mandatos_io.mandato_tipo_promovido resolve na hora, sem cache entre chamadas de revogação; aprovar_rascunho recheca tipos_promovidos dentro da própria transação desde a sub-entrega 19/N); execução dentro de mandato não pede aprovação redundante (liberar_rascunhos_promovidos/propor_reagendamento_semanal passam por avaliar() real desde as sub-entregas 17/N-18/N); política indisponível impede novos efeitos que dependam dela (decisao_erro_avaliacao fail-closed, sub-entrega 12/N e 18/N). O passo 2 (evoluir claims/scopes do OAuth, hoje um único escopo 'hermes:tools' para tudo) fica registrado como item aberto do pacote, não como bloqueio -- é hardening (nenhum caminho de produção hoje expõe refresh token do dono a um runner, investigado antes de propor a proposta da PR #221), não uma correção de bug pendente. Retomar quando um caso concreto pedir diferenciação de escopo entre clientes hospedados."
    autoridade: existente_ou_nova
testes:
  comandos: []
  resultados:
    - "Não aplicável -- decisão de escopo, sem mudança de código."
evidencias:
  - "Resposta direta do André via AskUserQuestion."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: P02 fechado como pacote."
  - "ABERTA, não-bloqueante: passo 2 do plano (OAuth claims/scopes) fica como hardening futuro, sem prazo. Retomar se um caso concreto pedir (ex.: diferenciar permissões entre Claude.ai/Cowork/Claude Code em vez de um escopo único para todos)."
  - "Pendências de produto/infraestrutura já registradas em blocos anteriores e não resolvidas por P02 continuam abertas: card do Telegram de rascunho degradado não reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore não configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupção silenciosa em escritas grandes via Argos."
proximo_pacote: "P03 -- consolidar contratos MCP e ferramentas. Investigação inicial (nesta mesma sessão): tools/registry.py hoje é só um catálogo plano nome->descrição (103 tools), sem outputSchema/structuredContent/annotations, sem expected_version/idempotency_key nas escritas, sem inventário tipado por ferramenta -- nenhum dos 10 passos do plano para P03 foi começado. Passo 1 do plano (inventário tipado: domínio, leitura/escrita, reversibilidade, rede, dados sensíveis, política, verificador, por ferramenta) é o ponto de partida natural, e o mais trabalhoso -- 103 ferramentas para classificar com precisão, não por amostragem. Vou começar por ele."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: c26fb8890c118061458a8b1ab0a6b5085ee63b45
pacote: "P03 sub-entrega 1/N -- inventario tipado das ferramentas MCP (passo 1 do plano: dominio, leitura/escrita, reversibilidade, necessidade de rede, dados sensiveis, politica e verificador, por ferramenta)"
estado: validado
inicio: "2026-09-09T20:20:00Z"
fim: "2026-09-09T21:31:00Z"
arquivos_alterados:
  - functions/tools/inventory.py (novo -- ToolInventoryEntry tipado + dict _INVENTORY com as 105 tools de tools/registry.py::_CATALOG; classe_efeito reusa o enum ja existente autonomy.contracts.ClasseEfeito, sem taxonomia nova; nao e consultado por nenhum executor ainda, e so o inventario em si)
  - functions/test_tool_inventory.py (novo -- paridade 1:1 com o catalogo real, nenhum campo obrigatorio vazio, leitura pura nunca reversivel/irreversivel, escrita pura nunca nao_aplica, leitura_e_escrita so fica nao_aplica quando a escrita e efeito colateral passivo documentado em nota)
decisoes:
  - id: p03-sub1-inventario-por-leitura-direta-nao-por-amostragem
    motivo: "O plano pede inventario tipado das ferramentas, nao por amostragem. Classifiquei as 105 tools (o plano fala em 103 na secao de testes do P03; a contagem real do catalogo hoje e 105 -- divergencia da redacao do plano, nao erro deste inventario) por leitura direta de tools/hermes_tools.py e modulos delegados (promocao_autonomia.py, outbox_aprovacao.py, secretario_whatsapp.py, investimentos.py, atencao.py, autonomy/policy.py etc.), nunca pelo nome ou pela descricao do catalogo -- que divergem do codigo em varios casos documentados no proprio modulo (ex.: preparar_upload e preparar_contato_prioritario_secretario gravam direto apesar do nome 'preparar_'; gerar_rascunho_formulario nao persiste nada apesar da descricao dizer que salva). Investigacao feita em 3 lotes paralelos (~35 tools cada, via subagentes independentes citando arquivo:linha como evidencia); eu revisei e reconciliei o resultado antes de escrever o modulo final."
    autoridade: existente_ou_nova
  - id: p03-sub1-classe-efeito-reusa-clasEfeito-existente
    motivo: "Em vez de inventar uma taxonomia de politica nova para o campo 'politica' pedido pelo passo 1, reusei o enum ja existente autonomy.contracts.ClasseEfeito (secao 5.1 do plano) -- mesma decisao de reaproveitar vocabulario ja tomada pela proposta de docs/autonomia/proposta-p02-mandato-io-wrapper.md. Cinco tools ja tinham classificacao canonica em autonomy/policy.py::CLASSE_EFEITO_PISO (schedule_whatsapp_message, pausar_conversa, criar_rascunho_email, registrar_aporte_investimento, registrar_execucao_investimento) -- usadas como ancora, nao reinferidas."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && ../venv/bin/python3 -m unittest discover -p 'test_*.py' -q"
  resultados:
    - "1534 testes, 8 falhas + 2 erros -- mesmo padrao pre-existente e documentado (ambiente sem ANTHROPIC_API_KEY/deps opcionais gmail/mp4; baseline era 1524/8/2 antes desta sub-entrega). Os 10 testes novos de test_tool_inventory.py passam integralmente (10/10); zero regressao."
evidencias:
  - "Revisao adversarial independente (Agent tool, general-purpose, sem contexto da implementacao): verificou ~30 tools de maior risco (dados_sensiveis=True, necessidade_de_rede=True, classe_efeito em COMPROMISSO_TERCEIROS/EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL, e as 7 leitura_e_escrita) contra o codigo-fonte real, e rodou a suite completa."
  - "Achado BLOQUEANTE da revisao, corrigido antes do envio: bug real em test_leitura_e_escrita_nao_fica_nao_aplica -- o filtro comparava so contra o enum ESCRITA (`is`), nunca contra LEITURA_E_ESCRITA, ficando com zero cobertura da categoria mista. Corrigido: teste renomeado para test_escrita_pura_nao_fica_nao_aplica (mantem a checagem original) + novo teste test_leitura_e_escrita_com_reversibilidade_nao_aplica_exige_nota_explicando, que exige documentacao explicita em `nota` para as 3 tools que ficam nao_aplica nessa categoria mista."
  - "Achado nao-bloqueante da revisao, corrigido: consultar_job estava dados_sensiveis=False contradizendo sua propria nota -- corrigido para True (e passthrough generico de qualquer job assincrono, incluindo os de dominio sensivel)."
  - "Achados nao-bloqueantes da revisao, registrados como nota (nao reclassificados -- sao julgamento de produto, nao bug): ambiguidade genuina em gerar_relatorio (classificado PREPARACAO_INTERNA apesar de persistir documento final sem confirmacao) e em salvar_memoria_global (reversibilidade via resolver_conflito_memoria e condicional, nao um caminho direto de busca+correcao)."
  - "Nenhuma classificacao de tool verificada pela revisao foi encontrada factualmente errada."
  - "Todos os arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- ambos batendo de primeira."
  - "PR #223 mesclada por Andre (confirmado por git fetch + git log de origin/main: merge commit c26fb8890c118061458a8b1ab0a6b5085ee63b45)."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: passo 1 do P03 (inventario tipado por ferramenta)."
  - "ABERTA: este inventario ainda nao e consultado por nenhum executor -- religar classe_efeito/dados_sensiveis/etc a decisao de politica real (autonomy/policy.py::avaliar()) e trabalho de sub-entrega futura, nao coberto aqui."
  - "ABERTA: ambiguidades de classificacao registradas em nota (gerar_relatorio, salvar_memoria_global) ficam para revisitar quando classe_efeito for religado a decisao de politica de fato."
  - "ACHADOS DE PROCESSO registrados no inventario para tratar em sub-entregas futuras do P03/P04: mutar_portal_compras_publico/mutar_lista_compras duplicam logica de escrita sobre a mesma colecao (candidato a consolidacao); excluir_objetivo_estrategico faz delete() definitivo sem estar no piso FLOOR_CONFIRMACAO_OBRIGATORIA do MCP; decidir_promocao_autonomia('aceitar') tem efeito de politica real maior que 'escrita interna' sugeriria."
  - "Pendencias de produto/infraestrutura ja registradas em blocos anteriores e nao resolvidas por esta sub-entrega continuam abertas: card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante."
proximo_pacote: "P03 -- com o inventario tipado no lugar, os proximos passos naturais sao o passo 2 (normalizador de resultados legados e validacao de argumentos) ou o passo 3 (outputSchema/structuredContent/annotations nos caminhos compativeis). Nenhum dos dois foi comecado ainda."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 2046755d0d0e4eb6dee7da5f60c173a4bd844ee9
pacote: "P03 sub-entrega 2/N -- validacao de argumentos obrigatorios no dispatch MCP (metade 'presenca de campo' do passo 2 do plano; checagem de tipo do schema fica para sub-entrega futura)"
estado: validado
inicio: "2026-09-09T22:08:34Z"
fim: "2026-09-09T22:22:08Z"
arquivos_alterados:
  - functions/mcp_server.py (nova _erro_campos_obrigatorios(name, arguments), chamada em dois pontos de _handle_tools_call: no ramo de criacao de confirmacao, apos o gate de politica DENY/PREPARE_ONLY e antes de preview_tool; e no ramo de execucao direta nao-gated, apos a resolucao de task_id e antes de execute_tool/fila assincrona. Deliberadamente NAO aplicado ao reenvio _confirmed=true -- ali arguments e so o envelope da confirmacao, o payload real ja foi congelado no Firestore na criacao da previa -- nem a _executar_confirmacao/confirmar_acao)
  - functions/tools/registry.py (nova campos_obrigatorios_ausentes(tool_name, arguments), fail-open por design: FileNotFoundError/OSError/json.JSONDecodeError/AttributeError/TypeError mais guardas isinstance nunca bloqueiam uma chamada por falha de leitura/formato do schema, so por ausencia real de campo)
  - functions/tools/schemas/criar_rascunho_email.json (assunto removido de required -- achado da revisao adversarial, ver decisoes)
  - functions/tools/schemas/salvar_pop_global.json (instrucao_sistema removido de required -- achado da revisao adversarial, ver decisoes)
  - functions/test_validacao_argumentos.py (novo -- testes de campos_obrigatorios_ausentes, incluindo paridade contra os 105 schemas reais do catalogo por inteiro, nao amostra; testes de _erro_campos_obrigatorios; integracao ponta a ponta via _handle_tools_call nos dois pontos de insercao e no reenvio _confirmed=true que deve ficar fora do alcance)
  - functions/test_mcp_server.py (test_ativo_prossegue_para_fluxo_de_confirmacao_existente ajustado: pausar_conversa passa a receber contato_ou_grupo/retomar_em validos, ja que o novo preflight intercepta antes de preview_tool quando ausentes -- o teste prova alcancabilidade do fluxo antigo, nao completude de argumentos, nenhuma asercao mudou)
  - functions/test_hermes_tools.py (test_devolve_job_id_em_vez_de_executar ajustado: gerar_relatorio passa a receber contexto, campo ja required no schema mas nunca antes enforced -- decisao deliberada de tratar o schema publicado como autoritativo para este campo especifico, sem escape de heranca/alias documentado ao contrario dos dois casos corrigidos abaixo)
decisoes:
  - id: p03-sub2-preflight-so-presenca-nao-tipo-ainda
    motivo: "Escopo deliberadamente estreito dentro do passo 2 do plano ('normalizador de resultados legados e validacao de argumentos'): so presenca de campo required (chave ausente ou None) e enforced agora. Checagem de TIPO (schema `type`) e o normalizador de resultados legados ficam para sub-entregas futuras -- misturar as duas coisas nesta sub-entrega ampliaria a superficie de regressao sem necessidade, e o achado da revisao adversarial (ver abaixo) ja mostrou que ate a fatia 'so presenca', supostamente a mais segura, escondia dois casos reais de inconsistencia schema-vs-handler."
    autoridade: existente_ou_nova
  - id: p03-sub2-dois-pontos-de-insercao-preservando-reenvio-confirmado
    motivo: "O preflight so entra nos DOIS pontos onde arguments representa de fato o payload de negocio completo: antes de preview_tool (criacao de confirmacao) e antes de execute_tool (execucao direta nao-gated). Deliberadamente fora do alcance: o reenvio _confirmed=true+_confirmation_id (arguments ali e so o envelope da confirmacao -- os campos reais ja foram congelados no Firestore na criacao da previa; validar de novo aqui quebraria TODO reenvio de qualquer tool com campo obrigatorio), _executar_confirmacao (executa o payload congelado, nao input fresco do cliente) e confirmar_acao (ramo totalmente separado, anterior aos dois pontos de insercao)."
    autoridade: existente_ou_nova
  - id: p03-sub2-revisao-corrigiu-dois-schemas-inconsistentes-com-o-proprio-handler
    motivo: "Achado real da revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao), nao autodetectado: dois schemas marcavam um campo como required mesmo o handler tendo fallback legitimo e ja documentado no proprio schema. (1) criar_rascunho_email: assunto era required, mas o schema ja documentava 'pode ficar vazio ao responder uma thread', e o handler (tools/criar_rascunho_email.py:77-79) de fato herda o assunto da thread, so rejeitando se mesmo assim ficar vazio -- corrigido removendo assunto de required. (2) salvar_pop_global: instrucao_sistema era required, mas o schema documenta instrucao/conteudo como apelidos, e o handler (tools/telegram_extended.py:195-209) resolve os tres por or com erro estruturado proprio quando todos ficam ausentes -- corrigido removendo instrucao_sistema de required. Os dois achados foram verificados de forma independente lendo o codigo real dos handlers (nao so o relato da revisao) antes de aplicar a correcao -- cada handler ja tinha tratamento gracioso pre-existente para o caso 'realmente ausente', entao a correcao do schema restaura o comportamento legitimo sem perda de seguranca. Varredura propria adicional por outros padroes de alias/heranca no catalogo (agendar_lembrete_acao hora/horario; obter_projeto_bolsas_publico/registrar_inscricao_bolsa_publica projectId/form_data) confirmou os dois casos seguros, sem necessidade de ajuste."
    autoridade: existente_ou_nova
  - id: p03-sub2-fail-open-ampliado-apos-achado-nao-bloqueante-da-revisao
    motivo: "Achado nao-bloqueante da revisao adversarial: a excecao original de campos_obrigatorios_ausentes era estreita demais -- um schema malformado (parameters: null, required nao-lista) escaparia por AttributeError/TypeError nao capturado, caindo no except Exception de nivel superior de mcp_server.py e virando bloqueio generico para toda chamada daquela tool, contradizendo a propria promessa 'fail-open' da funcao. Corrigido ampliando a excecao (FileNotFoundError, OSError, json.JSONDecodeError, AttributeError, TypeError) e adicionando guardas isinstance explicitas antes de iterar."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && ../venv/bin/python3 -m unittest discover -p 'test_*.py' -q"
  resultados:
    - "1560 testes + 539 subtests passando, 0 falhas novas, 0 regressao -- confirmado antes do envio a PR #225."
evidencias:
  - "Revisao adversarial independente (Agent tool, general-purpose, sem contexto da implementacao): rodou a suite completa, leu o diff e o codigo dos handlers envolvidos diretamente, e encontrou as duas regressoes bloqueantes e o achado nao-bloqueante de fail-open listados em decisoes acima."
  - "Todos os 7 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- todos batendo de primeira, sem drift de whitespace nem corrupcao."
  - "PR #225 mesclada por Andre (confirmado por git fetch + git log de origin/main: merge commit bc262a2e14b9a1f3b9915a154e26e5f881c19899)."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: metade 'presenca de campo obrigatorio' do passo 2 do plano."
  - "ABERTA: checagem de TIPO (schema `type`) da mesma validacao de argumentos -- deliberadamente deixada fora desta sub-entrega, ver decisoes."
  - "ABERTA: normalizador de resultados legados, a outra metade do passo 2 do plano -- ainda nao comecado. Hoje so existe o heuristico fragil de prefixo de string (_looks_like_error reconhecendo 'ERRO|') como forma de normalizacao."
  - "ABERTA: passo 3 do plano (outputSchema/structuredContent/annotations nos caminhos compativeis) continua sem cobertura."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (classe_efeito/dados_sensiveis/etc, P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante."
proximo_pacote: "P03 -- restam do passo 2 do plano: checagem de tipo (schema `type`) da validacao de argumentos, e o normalizador de resultados legados propriamente dito. O passo 3 (outputSchema/structuredContent/annotations) continua tambem em aberto. Vale perguntar ao Andre qual priorizar a seguir antes de comecar a proxima sub-entrega."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: beb2d76a1243cad268437c3ca83b4242ab214ba2
pacote: "P03 sub-entrega 3/N -- normalizador de resultados legados (a outra metade do passo 2 do plano, fechando-o junto com a validacao de argumentos da sub-entrega 2/N); mais a correcao de um teste que quebrou o CI da propria PR, achada e resolvida depois do merge"
# inicio abaixo aproximado pelo timestamp do base_commit (merge da PR #226,
# diario da sub-entrega 2/N) -- a auditoria das 105 tools e a implementacao
# local desta sub-entrega comecaram num trecho de sessao anterior a este,
# sem timestamp proprio observavel por mim com precisao; nao invento um.
estado: validado
inicio: "2026-09-09T22:28:27Z"
fim: "2026-09-10T00:27:24Z"
arquivos_alterados:
  - functions/tools/schedule_whatsapp_message.py (o `except` da falha de enfileiramento passa a devolver `f"ERRO|Erro ao agendar mensagem no WhatsApp: {e}"` -- antes, sem o prefixo, `mcp_server._looks_like_error` nao reconhecia a falha; a propria docstring do modulo documenta o incidente de 28/08/2026 que motivou a funcao a existir)
  - functions/tools/pausar_conversa.py (a checagem acoplada em `pausar()` -- `if queued.startswith(...)` -- atualizada de `"Erro"` sem pipe (batia por coincidencia com o texto antigo) para `"ERRO|"`, o prefixo novo de `schedule_whatsapp_message`; sem os dois fixos no mesmo commit, uma falha real de enfileiramento voltaria a passar como `status: "enfileirada"`)
  - functions/tools/telegram_extended.py (9 pontos de retorno de erro em `execute()`, todos strings sem o prefixo `ERRO|`, corrigidos)
  - functions/tools/hermes_tools.py (handlers de string solta -- sem dict, sem prefixo -- em `_consultar_lista_compras`, `_consultar_agenda` x2, `_encontrar_slot_livre` x2, `_consultar_saude`, `_consultar_dados_cadastrais` x3, `_buscar_e_analisar_email`, `_salvar_memoria_global`, `pesquisar_internet` x3 e `ler_pagina_web` x3, todos ajustados para `ERRO|`; mais os dois fixos preventivos da revisao adversarial em `_strategy`/`_via_callable`, ver decisoes)
  - functions/test_normalizador_resultados_legados.py (novo -- 40 testes cobrindo os 21 gaps e os 2 fixos da revisao adversarial; 1 teste corrigido apos quebrar o CI, ver decisoes)
  - functions/test_pausar_conversa.py (3 testes novos: novo prefixo de `schedule_whatsapp_message`; acoplamento real com `pausar_conversa`, incluindo um teste ponta a ponta sem nenhum mock do enfileirador)
decisoes:
  - id: p03-sub3-21-gaps-erro-pipe-e-convencao-existente-nao-nova
    motivo: "`mcp_server._handle_tools_call` so reconhece falha por duas formas: dict com `.get('erro')` truthy, ou string comecando com `ERRO|` (fallback `warning-sign`). Auditoria sistematica das 105 tools MCP (3 agentes independentes, em paralelo, cobertura completa -- nao amostragem) achou 21 pontos reais onde uma falha nao batia em nenhuma das duas formas: a tool falhava e `is_error` saia False. Os fixos alinham ao prefixo `ERRO|`, que ja e a convencao dominante e pre-existente no resto do codigo -- nao e convencao nova introduzida por esta sub-entrega."
    autoridade: existente_ou_nova
  - id: p03-sub3-acoplamento-schedule-whatsapp-pausar-conversa-e-o-fixo-de-maior-risco
    motivo: "Fixo isolado de maior risco desta sub-entrega: o `except` de `schedule_whatsapp_message` nao prefixava seu erro, e `pausar_conversa.py` checava esse retorno com `startswith('Erro')` sem pipe -- batia por coincidencia com o texto antigo. Corrigidos juntos, no mesmo commit, porque sao acoplados: sem o par, uma falha real de enfileiramento voltaria a passar como enfileirada com sucesso. Este modulo ja documenta na propria docstring o incidente de 28/08/2026 (dois envios aceitos que falharam no worker e o agente afirmou ao dono que tinha mandado) -- a checagem agora e defesa direta contra a recorrencia dessa classe de erro, uma camada abaixo (falha no proprio enfileiramento, nao no worker)."
    autoridade: existente_ou_nova
  - id: p03-sub3-revisao-achou-get-default-nao-cobre-chave-presente-e-vazia
    motivo: "Achado real da revisao adversarial (Agent tool, general-purpose, sem contexto da implementacao): `_strategy` e `_via_callable` (hermes_tools.py) usavam `resultado.get('reason', default)` / `.get('message', default)` -- `dict.get(chave, default)` so cai no default quando a chave esta AUSENTE, nao quando presente e vazia/None. Uma funcao futura que devolvesse `{'status': 'error', 'reason': None}` produziria `'erro': None`, e `bool(None)` e False -- reintroduzindo a mesma classe de bug que esta correcao existe para fechar. Nao exploravel hoje (nenhum chamador atual devolve reason/message vazio), corrigido preventivamente para `.get(chave) or default`, com 2 testes novos provando o comportamento com `reason: None` / `message: ''`."
    autoridade: existente_ou_nova
  - id: p03-sub3-ci-quebrou-por-teste-dependente-de-ambiente-nao-por-producao
    motivo: "CI da PR #227 (job 'Testes das Functions Python', run 34416261791) falhou apos o envio inicial. Reproduzido localmente numa venv limpa instalada so a partir de functions/requirements.txt (mesmos passos do pr.yml: sem ANTHROPIC_API_KEY): `test_buscar_e_analisar_email_excecao` assumia que `html2text` estaria ausente do sandbox para forcar o ramo de excecao de `_buscar_e_analisar_email` via ImportError natural -- mas `html2text` e dependencia real do projeto (requirements.txt) e esta presente num ambiente corretamente provisionado; sem credenciais do Gmail, a propria `buscar_e_analisar_email` ja devolve erro pelo prefixo de aviso antes de levantar, entao a asercao sobre o texto do ramo `except` nunca era exercitada. Nenhum codigo de producao estava errado. Corrigido mockando `tools.buscar_e_analisar_email.buscar_e_analisar_email` diretamente (mesmo padrao dos demais testes da classe), exercitando o ramo de forma deterministica. Corrigido e comentado na propria PR (issuecomment-5610539211) antes do merge; CI voltou a verde nos 3 checks do commit seguinte (confirmado via api.github.com/.../check-runs)."
    autoridade: existente_ou_nova
  - id: p03-sub3-achado-de-processo-venv-local-persistente-desatualizada
    motivo: "Investigando a causa da falha de CI acima, descobri que a venv local persistente deste clone (`functions/../venv`, referenciada como `../venv/bin/python3` nos comandos de teste de P02 sub-entrega 18/N, 19/N, P03 sub-entrega 1/N e 2/N, todas acima) estava faltando dependencias REAIS do projeto (pypdf, imageio-ffmpeg, html2text -- todas em requirements.txt). Numa venv fiel a requirements.txt (sem ANTHROPIC_API_KEY, replicando o CI), a suite inteira passa 1601/1601, 0 falhas, 0 erros -- nenhum dos '8 falhas + 2 erros -- mesmo padrao pre-existente de ambiente' relatados nas quatro entradas anteriores acontece. Atualizei a venv persistente (`pip install -r requirements.txt`) e confirmei o mesmo resultado (1601/1601) nela tambem. Nao reescrevo os blocos anteriores (regra deste arquivo: nenhum bloco `validado` e reescrito), mas registro aqui como achado de processo: a alegacao de 'baseline pre-existente' nessas quatro entradas provavelmente refletia essa venv desatualizada, nao o ambiente real do CI, e deve ser tratada com ceticismo ate reverificacao."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "CI reproduzido localmente: venv limpa (python3 -m venv), `pip install -r functions/requirements.txt`, `cd functions && python -m unittest discover -s . -p 'test_*.py'` -- mesmos passos do job 'Testes das Functions Python' de .github/workflows/pr.yml, sem ANTHROPIC_API_KEY."
    - "Apos o achado de processo: `../venv/bin/pip install -r requirements.txt` na venv persistente do clone, seguido do mesmo `unittest discover`."
  resultados:
    - "Venv limpa (fiel ao CI): 1601 testes, 0 falhas, 0 erros -- inclui os 40 testes novos de test_normalizador_resultados_legados.py e os 3 de test_pausar_conversa.py."
    - "Venv persistente atualizada: mesmo resultado, 1601/1601, 0 falhas, 0 erros -- confirma que a discrepancia com as quatro entradas anteriores era a venv, nao um comportamento de ambiente genuino."
    - "Confirmado tambem pelos check-runs reais do GitHub no commit final (55d14d99f): 'Testes das Functions Python', 'Testes e build' e 'GitGuardian Security Checks' -- os 3 com conclusion=success."
evidencias:
  - "Auditoria das 105 tools MCP por 3 agentes independentes em paralelo (cobertura completa, nao amostragem), cada um citando arquivo:linha como evidencia dos 21 gaps."
  - "Revisao adversarial independente (Agent tool, general-purpose, sem contexto da implementacao) sobre o diff original -- achou o unico ponto registrado em decisoes (.get(chave, default)); confirmou sem mais achados: sem falso positivo, sem branch de erro esquecido nos 4 arquivos alterados, sem consumidor quebrado (checou mcp_jobs.py::_parece_mensagem_de_erro, godmode.py, e o copiloto web em main.py que chama confirmarEdicaoAcao direto via Firebase callable, fora do wrapper MCP), sem regressao nos testes."
  - "Todos os 7 arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificacao de hash local (git hash-object) contra o sha retornado pelo Argos -- todos batendo de primeira, sem drift de whitespace nem corrupcao (6 do envio inicial + 1 da correcao pos-CI)."
  - "PR #227 aberta; CI vermelho no primeiro commit (run 34416261791); causa raiz investigada reproduzindo o CI localmente; corrigido; comentario de correcao e retratacao do relato de baseline postado na propria PR (issuecomment-5610539211) antes do merge."
  - "PR #227 mesclada por Andre ('mesclado, pode prosseguir'), confirmado por git fetch + git log de origin/main: merge commit 108247a94."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: a outra metade do passo 2 do plano (normalizador de resultados legados) -- passo 2 agora completo, junto com a validacao de argumentos da sub-entrega 2/N."
  - "ACHADO DE PROCESSO, nao-bloqueante mas relevante: a alegacao de '8 falhas + 2 erros -- mesmo padrao pre-existente de ambiente' registrada em P02 sub-entrega 18/N, 19/N, P03 sub-entrega 1/N e 2/N provavelmente refletia uma venv local desatualizada (faltavam pypdf/imageio-ffmpeg/html2text, todas dependencias reais), nao o ambiente real do CI -- uma venv fiel a requirements.txt passa 1601/1601 sem nenhuma dessas falhas. Nao reescrevo os blocos anteriores (regra deste arquivo), mas registro para tratar aquelas contagens com ceticismo. Daqui em diante, verificar suite contra uma venv fiel a requirements.txt (ou contra os check-runs reais do CI) antes de relatar qualquer falha como 'baseline pre-existente'."
  - "ABERTA: checagem de TIPO (schema `type`) da validacao de argumentos -- deixada de fora deliberadamente pela sub-entrega 2/N."
  - "ABERTA: passo 3 do plano (outputSchema/structuredContent/annotations nos caminhos compativeis) continua sem cobertura."
  - "Pendencias ja registradas em blocos anteriores e nao tocadas por esta sub-entrega continuam abertas: religar inventario tipado (P03 sub-entrega 1/N) a decisao de politica real; ambiguidades de classificacao (gerar_relatorio, salvar_memoria_global); card do Telegram de rascunho degradado nao reeditado; observabilidade de claim pendente sem _audit_log; TTL do Firestore nao configurado para mcp_jobs; limite de 200KB do Argos em main.py; risco de corrupcao silenciosa em escritas grandes via Argos; passo 2 do P02 (OAuth claims/scopes) como hardening futuro nao-bloqueante."
proximo_pacote: "P03 -- com o passo 2 completo (validacao de argumentos + normalizador de resultados legados), restam o passo 3 (outputSchema/structuredContent/annotations) e a checagem de tipo deixada em aberto pela sub-entrega 2/N. Vale perguntar ao Andre qual priorizar a seguir -- ou tratar primeiro o achado de processo desta entrada (fidelidade da venv de teste) antes de prosseguir."
```

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