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
P01 7/N, também preventivamente: o bloco novo somado ao arquivo ativo já
passava do limiar de ~50KB que a sub-entrega P01 5/N registrou como
arriscado, e desta vez os dois blocos mais antigos foram movidos juntos
para dar mais folga antes do próximo corte. Ver o cabeçalho de cada
arquivo de arquivo para o relato completo.** Nenhum conteúdo foi perdido;
é uma relocação, não uma edição. Este arquivo continua sendo a fonte de
verdade para tudo a partir da sub-entrega P01 5/N em diante.

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: f97978b90132ae9e6431000eff0a1c43bfeb691d
pacote: "P01 sub-entrega 5/N -- core/idempotency.py (passo 4 do plano): erro de idempotência em caminho com efeito vira resultado recuperável sem efeito, não mais 'permite processamento' silenciosamente"
# Continuação autônoma autorizada por André ("PR 212 mesclado. Pode
# prosseguir."). Escolhido exatamente o passo nomeado como recomendação no
# proximo_pacote da entrega anterior (P01 passo 4, core/idempotency.py).
#
# Achado técnico NOVO nesta sub-entrega, bloqueante para o caminho normal de
# envio: o único callsite real de check_and_register (githubWebhook, em
# functions/main.py) fica dentro de um arquivo de 683664 bytes -- acima do
# limite de 200000 bytes que o conector Argos aplica tanto para leitura
# (argos_ler_arquivo_repositorio) quanto para escrita
# (argos_escrever_arquivo_repositorio, que só aceita substituição integral do
# arquivo, nunca patch/diff). Confirmado ao vivo: a tentativa de leitura foi
# recusada pelo próprio Argos com erro explícito (413, "excede o limite de
# 200000 bytes"). Diferente do limite de saída de 64000 tokens que afetou
# este próprio execucao.md na sub-entrega 15/N de P02 (resolvido arquivando
# conteúdo antigo), este é um limite do CONECTOR Argos sobre UM arquivo de
# produção grande demais -- não há como dividir main.py em pedaços menores
# só para esta sub-entrega sem um refactor real, fora de escopo.
#
# Levado ao André via AskUserQuestion (4 opções: aplicar o diff manualmente,
# dividir main.py em módulos menores, pausar a sub-entrega, ou habilitar
# push local). Ele escolheu aplicar manualmente -- recebeu o diff exato (15
# linhas) e commitou direto na branch remota (commit 6ec1137cf). Confirmado
# por git fetch + diff que o commit dele bate byte a byte com o diff que eu
# tinha gerado localmente (mesmo blob sha do main.py, c8a05f3f2...) antes de
# eu prosseguir com os dois arquivos de teste restantes.
#
# NOVO achado nesta própria correção (não do trabalho de engenharia acima,
# mas do processo de registro): a primeira tentativa de gravar este bloco em
# execucao.md (então com 85701 bytes) derrubou silenciosamente o bloco P02
# sub-entrega 17/N durante a retranscrição manual, sem erro explícito da
# API. Uma tentativa de correção juntando tudo num arquivo de arquivo só
# (159725 bytes) estourou o limite de saída de 64000 tokens. Recuperado
# movendo os blocos P02 sub-entrega 12/N-16/N para um segundo arquivo de
# arquivo (execucao-archive-p02-sub12-a-sub16.md) por script, não
# retranscrição -- ver o cabeçalho deste arquivo e o do novo arquivo de
# arquivo para o relato completo.
estado: pronto_para_revisao
inicio: "2026-09-09T11:58:00Z"
fim: "2026-09-09T12:16:00Z"
arquivos_alterados:
  - functions/core/idempotency.py (check_and_register reescrita: retorna enum de string RESULTADO_NOVO/RESULTADO_DUPLICADO/RESULTADO_ERRO_CONFIGURACAO/RESULTADO_ERRO_TRANSACAO em vez de bool; falha de transação ou backend sem suporte a transação nunca mais retornam True/"permite processamento")
  - functions/main.py (githubWebhook: trata os 2 resultados de erro com HTTP 503, sem processar o evento -- aplicado manualmente por André, commit 6ec1137cf, verificado byte a byte contra o diff gerado)
  - functions/test_github_webhook.py (testes existentes atualizados para o novo contrato de enum; 2 testes novos cobrindo o caminho 503 para cada tipo de erro)
  - functions/test_idempotency.py (novo -- não existia cobertura dedicada para core/idempotency.py antes desta sub-entrega; 8 testes: novo/duplicado/ausente/aceita-int, e 4 no não-fallback para processamento silencioso em erro)
decisoes:
  - id: p01-sub5-idempotency-erro-vira-resultado-recuperavel-sem-efeito
    motivo: "Passo 4 do plano fechado: 'erro em caminho com efeito' (Firestore indisponível, ou backend de teste sem suporte a transação) deixa de retornar True (permitir processamento) e passa a retornar um dos dois resultados de erro explícitos -- RESULTADO_ERRO_CONFIGURACAO (sem hasattr(db, 'transaction')) e RESULTADO_ERRO_TRANSACAO (falha real da transação). Em nenhum dos dois casos o documento de idempotência é escrito. O único chamador real (githubWebhook) responde 503 nesses casos -- não processa o evento agora (evita duplicar a anotação no diário de tarefas vinculadas se a causa raiz for uma entrega repetida coincidindo com uma falha transitória do Firestore) e sinaliza falha explícita para a entrega poder ser repetida depois (redelivery manual ou automática do GitHub), em vez de responder 200 como se tivesse sido tratada."
    autoridade: existente_ou_nova
  - id: p01-sub5-limite-200kb-do-conector-argos-bloqueia-edicao-de-main-py
    motivo: "Achado de infraestrutura, não de produto: functions/main.py (683664 bytes) está acima do limite de 200000 bytes que argos_ler_arquivo_repositorio e argos_escrever_arquivo_repositorio aplicam -- confirmado ao vivo pela recusa 413 do próprio Argos na tentativa de leitura. Isso bloqueia QUALQUER edição futura a main.py pelo caminho normal desta sessão (Argos MCP), não só esta. Não tentei contornar via push local (fora da diretriz padrão desta sessão, sem credencial configurada) nem tentei dividir main.py sozinho (refactor real, fora de escopo, decisão de arquitetura que não me cabe tomar sozinho). Levado ao André via pergunta direta com 4 opções; ele escolheu aplicar o diff manualmente desta vez. Fica como pendência de infraestrutura para o André decidir se/quando quiser resolver de raiz (dividir main.py em módulos menores, ou uma ferramenta Argos com suporte a patch/diff para arquivos grandes)."
    autoridade: existente_ou_nova
  - id: p01-sub5-corrupcao-silenciosa-na-retranscricao-e-arquivamento-preventivo
    motivo: "Achado de processo, descoberto ao verificar esta própria entrada por hash e diff (disciplina padrão desta sessão) em vez de confiar no retorno bem-sucedido do Argos: o primeiro envio deste bloco (arquivo então com 85701 bytes) retornou sha e status de sucesso, mas o conteúdo realmente commitado tinha 69596 bytes -- faltava o bloco inteiro da sub-entrega P02 17/N (~16KB), derrubado silenciosamente durante a retranscrição manual do conteúdo completo para a chamada de escrita, sem nenhum erro da API. Diferente do caso da sub-entrega 15/N (que falhou com erro explícito de limite de tokens), este caso passou despercebido se não fosse a verificação por hash. Corrigido em duas etapas: (1) reconstrução do conteúdo correto por script local (fatiar o arquivo por byte, não retranscrever), verificada por hash antes de qualquer envio; (2) como uma tentativa de reenviar tudo somado (arquivo de arquivo + blocos movidos, 159725 bytes) também falhou, desta vez com erro explícito de limite de saída (64000 tokens), os blocos P02 sub-entrega 12/N-16/N foram para um SEGUNDO arquivo de arquivo novo em vez de anexados ao existente -- ver decisão do cabeçalho de execucao-archive-p02-sub12-a-sub16.md. Lição para sessões futuras, já registrada lá: acima de ~50KB, uma escrita via Argos não é confiável só por retornar sucesso -- verificar por hash E por diff de conteúdo (não só sha) é necessário, e arquivar preventivamente perto desse tamanho evita o problema em vez de reagir a ele."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && ../venv/bin/python3 -m unittest discover -p 'test_*.py' -q"
  resultados:
    - "Antes desta sub-entrega (main pós-merge da PR #212, commit f97978b90): 1473 testes, 8 falhas + 2 erros -- confirmados PRÉ-EXISTENTES (mesmos de sempre: test_deteccao_subproduto.py, test_gmail_bill_pdf, test_mp4_repair)."
    - "Depois desta sub-entrega (com o main.py exatamente como o André commitou, verificado por git fetch): 1483 testes (10 novos: 8 em test_idempotency.py, 2 em test_github_webhook.py), mesmas 8 falhas + 2 erros pré-existentes, zero regressão nova."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre o diff completo (antes do André aplicar main.py manualmente -- revisou o diff de main.py como texto, não como arquivo lido via Argos). Veredito explícito: 'safe to ship'. Verificou contra o código-fonte real da biblioteca google-cloud-firestore instalada que o mock de Transaction em test_idempotency.py é fiel ao protocolo real. Confirmou empiricamente que os testes pegam a regressão de verdade: reintroduziu deliberadamente o bug antigo (retornar RESULTADO_NOVO em vez de erro) e viu exatamente os 3 testes esperados falharem, depois restaurou o fix. Dois achados não-bloqueantes, nenhum corrigido (ambos aceitos como característica inerente ao design, não regressão): (1) update_id int 0 (falsy) seria tratado como 'nada a deduplicar' -- inalcançável hoje (delivery_id do GitHub é sempre string não vazia), comportamento inalterado do código original; (2) por o registro de idempotência e o efeito (anotar no diário) serem dois passos não-transacionais separados, um resultado ambíguo de commit (escrita no Firestore bem-sucedida no servidor mas cliente vê timeout) pode em teoria descartar permanentemente um evento -- inerente à decisão do próprio passo 4 do plano (preferir descartar/exigir retry a duplicar silenciosamente), e webhooks de repositório do GitHub não são reentregues automaticamente por padrão (confirmado via docs.github.com/webhooks/using-webhooks/handling-failed-webhook-deliveries)."
  - "Após o André aplicar main.py manualmente (commit 6ec1137cf): confirmado por git fetch + git diff que o conteúdo bate byte a byte com o diff que eu tinha preparado (mesmo blob sha c8a05f3f2... do main.py que eu já tinha verificado localmente antes do bloqueio do Argos). Suíte completa rodada de novo contra o main.py real dele (não uma simulação) antes de enviar os 2 arquivos de teste restantes -- ver testes.resultados acima."
  - "Todos os arquivos possíveis de enviar via Argos (idempotency.py, test_github_webhook.py, test_idempotency.py) enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificação de hash local (git hash-object) contra o sha retornado, batendo exatamente. main.py foi commitado manualmente por André diretamente na branch remota, verificado por leitura via git fetch (não pelo Argos, que recusa o arquivo)."
  - "A corrupção silenciosa desta própria entrada em execucao.md (ver decisão p01-sub5-corrupcao-silenciosa-na-retranscricao-e-arquivamento-preventivo) foi diagnosticada por git fetch + diff byte a byte entre o commit remoto e o conteúdo local já verificado por hash antes do envio -- a mesma disciplina de verificação já usada para os arquivos de código, agora comprovadamente necessária também para este próprio arquivo de registro."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: passo 4 de P01 (erro de idempotência em caminho com efeito vira resultado recuperável sem efeito)."
  - "NOVA, de infraestrutura: functions/main.py (683664 bytes) excede o limite de 200000 bytes do conector Argos para leitura E escrita -- bloqueia qualquer edição futura a main.py pelo caminho normal (Argos MCP) desta sessão, não só a desta sub-entrega. Duas saídas possíveis, nenhuma decidida ainda: dividir main.py em módulos menores (refactor real), ou uma ferramenta Argos com suporte a leitura/escrita parcial (patch/diff) para arquivos grandes. Por ora, a saída usada foi o André aplicar o diff manualmente -- funciona, mas não escala para edições maiores em main.py."
  - "NOVA, de processo: escritas via Argos acima de ~50KB podem retornar sucesso (sha válido) mesmo tendo derrubado conteúdo silenciosamente na retranscrição -- ver decisão p01-sub5-corrupcao-silenciosa-na-retranscricao-e-arquivamento-preventivo. Verificação por hash sozinha não basta quando a própria retranscrição é a fonte do erro (o hash bate com o que foi de fato enviado, não com o que deveria ter sido enviado); é preciso comparar o TAMANHO esperado contra o retornado como primeiro sinal, e diff de conteúdo para confirmar."
  - "P01 passos 5-10 do plano continuam abertos: mcp_jobs (reivindicação sobre leitura atual, estado de erro normalizado), claim de confirmação abandonado, regras Firestore/deploy.yml (mesmo bloqueio de PAT sem escopo workflow já registrado para P00), relatório de reconciliação final do pacote."
  - "Todas as pendências já registradas nos blocos anteriores que não foram tocadas por esta sub-entrega continuam abertas (ver blocos de P01/P02 acima)."
proximo_pacote: "P01 -- próximo passo natural na ordem do plano é o passo 5 (mcp_jobs.py: reivindicação sobre leitura atual, estado de erro normalizado, resultado estruturado e timestamp de expiração). Antes de escolher sozinho, porém, vale levar ao André duas pendências novas de infraestrutura/processo como pergunta separada, não mais uma escolha de engenharia autocontida: (1) o limite de 200KB do Argos em main.py, e (2) o risco de corrupção silenciosa em escritas grandes -- ambas sobre a própria ferramenta de trabalho, não sobre o produto Hermes."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: f8a23f76cf3e108135ac8b2666de2b1182ab95d6
pacote: "P01 sub-entrega 6/N -- functions/mcp_jobs.py (passo 5 do plano): reivindicação transacional sobre leitura atual, estado de erro normalizado, resultado estruturado e expira_em como Timestamp"
# Continuação autônoma autorizada por André ("Pode cancelar esse
# acompanhamento, considere que eu já mesclei o pr e vamos prosseguir para as
# próximas etapas.") após confirmar a mesclagem da PR #213 -- verificado antes
# de aceitar como fato (git merge-base --is-ancestor contra origin/main),
# disciplina padrão desta sessão de nunca afirmar estado sem checar.
#
# Passo 5 do plano nomeia 4 problemas concretos em mcp_jobs.py::
# on_mcp_job_created, ligados ao achado A10 ("trigger usa snapshot do evento,
# grava done sem normalizador de erro e expira_em como inteiro Unix"):
#
# 1. Reivindicação sobre leitura atual: o gatilho decidia com base no
#    snapshot capturado no MOMENTO DO EVENTO (`event.data.to_dict()`), não no
#    estado atual do documento. Gatilhos do Firestore são "ao menos uma vez",
#    não "exatamente uma vez" -- o mesmo evento de criação pode invocar a
#    função mais de uma vez, e sem reivindicação a tool rodaria duas vezes
#    (dois relatórios gerados, duas buscas de e-mail). Corrigido com uma
#    transação que relê o estado atual e marca `reivindicado_em` antes de
#    prosseguir -- mesmo padrão A04 já usado em core/idempotency.py e
#    agent_requests.py (inclusive a mesma disciplina de "sem suporte a
#    transação real, recusa em vez de arriscar" e "falha real da transação,
#    nenhuma escrita desprotegida como fallback").
# 2 e 3. Estado de erro normalizado / resultado estruturado: investigação do
#    código real das três tools deste trigger (gerar_relatorio,
#    ler_documento_na_integra, buscar_e_analisar_email, em
#    tools/telegram_extended.py e tools/hermes_tools.py) mostrou que nenhuma
#    levanta exceção nem devolve um dict com "erro" quando falha -- todas
#    devolvem uma STRING de sucesso-na-forma cujo CONTEÚDO é uma mensagem de
#    erro (prefixo "⚠️", mesma convenção de mcp_server.py::_looks_like_error
#    para o caminho síncrono). O código antigo gravava isso como "done" --
#    falso sucesso, exatamente o risco citado no A10. Corrigido detectando
#    esse padrão (duplicado localmente como `_parece_mensagem_de_erro` para
#    não criar import circular com mcp_server.py) e gravando "error" com um
#    novo campo `erro_tipo` normalizado (política / resultado_tool / exceção
#    / erro_configuracao). Resultado não-string (hoje teórico para as três
#    tools, mas `execute()` é o dispatcher genérico) deixa de ser sempre
#    serializado para string JSON -- fica na forma nativa quando cabe no
#    limite de tamanho já existente.
# 4. expira_em: passou de int(time.time())+TTL para um `datetime`
#    timezone-aware (mesmo padrão de core/idempotency.py::expires_at) --
#    Firestore exige campo Timestamp para uma política de TTL funcionar;
#    configurar a política em si continua sendo passo de infraestrutura
#    separado.
#
# Achado da revisão adversarial (ver evidências): a referência do documento
# usada em toda a função deixou de vir de `event.data.reference` (snapshot
# construído por um cliente Firestore interno ao SDK de functions, separado
# do `db = _db()` usado para abrir a transação) e passou a ser reconstruída
# via `db.collection(...).document(snap.id)` -- mesma origem única para
# leitura transacional, reivindicação e todas as escritas, mesmo padrão de
# core/idempotency.py/agent_requests.py, eliminando uma dúvida legítima que a
# revisão levantou (não havia como testar contra um projeto Firestore real
# neste sandbox) em vez de deixá-la em aberto.
estado: pronto_para_revisao
inicio: "2026-09-09T14:05:00Z"
fim: "2026-09-09T14:46:00Z"
arquivos_alterados:
  - functions/mcp_jobs.py (on_mcp_job_created: reivindicação transacional via novo _reivindicar_job/_SemSuporteTransacao; detecção de resultado-em-formato-de-erro via _parece_mensagem_de_erro; _preparar_resultado preserva forma estruturada quando cabe no limite; expira_em via nova _expira_em(); quatro novas constantes ERRO_TIPO_*; ler_job passa a expor erro_tipo quando presente, campo aditivo)
  - functions/test_mcp_jobs.py (9 testes existentes adaptados ao novo fluxo transacional; 15 testes novos: reivindicação/duplicação de evento, sem-suporte-a-transação, falha real de transação, normalização de erro por prefixo/dict, resultado estruturado preservado e truncado, exceção normalizada, expira_em como datetime nos três caminhos)
decisoes:
  - id: p01-sub6-mcp-jobs-reivindicacao-transacional-sobre-leitura-atual
    motivo: "Passo 5 do plano, item 1: o gatilho relê o estado ATUAL do documento dentro de uma transação (status ainda 'processing' E reivindicado_em ainda ausente) antes de decidir executar, em vez de confiar no snapshot do evento. Sem suporte a transação real no backend, ou falha real da transação, não há fallback para leitura/escrita desprotegida -- mesma disciplina A04 de core/idempotency.py/agent_requests.py. Mantém o valor de `status` inalterado durante a execução (só adiciona o marcador `reivindicado_em`) por escopo mínimo: introduzir um novo valor de status intermediário exigiria revisar todo consumidor de `ler_job`/mensagens ao cliente que hoje assumem só 'processing'/'done'/'error', fora do escopo desta correção."
    autoridade: existente_ou_nova
  - id: p01-sub6-mcp-jobs-erro-normalizado-por-conteudo-nao-so-por-excecao
    motivo: "Passo 5 do plano, itens 2 e 3: as três tools deste trigger (verificadas na fonte, não por suposição) sinalizam falha no próprio texto do resultado, não por exceção nem por dict com 'erro' -- gravar 'done' nesse caso seria falso sucesso (risco citado no A10). Heurística de detecção (prefixo '⚠️'/'ERRO|' para string, chave 'erro' para dict) reproduz deliberadamente o mesmo contrato já estabelecido em mcp_server.py::_looks_like_error para o caminho síncrono, duplicado localmente em vez de importado para não criar acoplamento circular (mcp_server.py já importa mcp_jobs.criar_job). Resultado não-string passa a ser gravado na forma nativa (dict/lista) quando cabe no limite de _MAX_RESULTADO_CHARS, evitando dupla serialização para um consumidor programático -- sem alterar o comportamento hoje observável, já que as três tools reais sempre devolvem string."
    autoridade: existente_ou_nova
  - id: p01-sub6-mcp-jobs-expira-em-vira-timestamp
    motivo: "Passo 5 do plano, item 4: expira_em passa de inteiro Unix para datetime timezone-aware (mesmo padrão de core/idempotency.py::expires_at), tornando o campo elegível para uma política de TTL nativa do Firestore, que exige tipo Timestamp. A configuração da política de TTL em si (Firestore Console/gcloud) continua sendo um passo de infraestrutura separado, fora do alcance de uma mudança de código -- registrado como pendência, não resolvido aqui."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && source venv/bin/activate && python3 -m pytest test_mcp_jobs.py -q"
    - "cd functions && source venv/bin/activate && python3 -m pytest -q"
  resultados:
    - "test_mcp_jobs.py isolado: 24 testes, todos passando (9 adaptados do fluxo anterior + 15 novos)."
    - "Suíte completa: 1506 testes + 147 subtests passando, zero falha -- mesma base pré-existente da sub-entrega anterior (1483), com as 23 diferenças vindas integralmente dos testes novos/adaptados desta sub-entrega. Sem regressão em nenhum outro módulo."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação), rodando a suíte de testes ela mesma em vez de só ler o diff. Veredito explícito: 'safe to ship'. Confirmou que a reivindicação transacional é correta sob o decorator real @firestore.transactional (não só sob o double dos testes) e que os doubles em test_mcp_jobs.py implementam o protocolo real o suficiente para exercitar o mesmo caminho de produção. Um achado should-fix, não-bloqueante e PRÉ-EXISTENTE (não introduzido por esta sub-entrega, mesma lacuna já presente em mcp_server.py::_looks_like_error para o caminho síncrono): o wrapper próprio de buscar_e_analisar_email (tools/hermes_tools.py::_buscar_e_analisar_email) devolve 'Erro: {e}' (maiúscula, sem prefixo '⚠️'/'ERRO|') quando uma exceção escapa do try/except do próprio wrapper -- essa forma específica não bate com _parece_mensagem_de_erro, então um erro desse formato específico ainda gravaria 'done'. Registrado como pendência abaixo em vez de expandir a heurística além do contrato estabelecido de _looks_like_error (risco de scope creep e de introduzir falsos positivos não avaliados). Um achado 'worth verifying, not confirmed' sobre usar a referência de `event.data.reference` (cliente Firestore interno do SDK de functions) junto com uma transação aberta por outro cliente (`db = _db()`) -- resolvido eliminando a dúvida por completo em vez de deixá-la em aberto: `ref` passou a ser sempre reconstruída a partir do mesmo `db`, mesmo padrão de core/idempotency.py/agent_requests.py (ver decisão e comentário no próprio código)."
  - "Investigação da fonte real das três tools (tools/telegram_extended.py::execute para gerar_relatorio/ler_documento_na_integra, tools/hermes_tools.py::_buscar_e_analisar_email e tools/buscar_e_analisar_email.py) antes de desenhar a heurística de erro -- não presumida por convenção genérica do resto do código-base (que em outros módulos usa dict com chave 'erro'), que teria resultado numa heurística que nunca dispararia de verdade para nenhuma das três tools reais."
  - "Todos os arquivos enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificação de hash local (git hash-object) contra o sha retornado, batendo exatamente -- ambos os arquivos desta sub-entrega são pequenos (19562 e 29575 bytes), bem abaixo de qualquer limite conhecido do conector."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: passo 5 de P01 (mcp_jobs.py -- reivindicação sobre leitura atual, estado de erro normalizado, resultado estruturado, timestamp de expiração)."
  - "NOVA, de produto (não-bloqueante, achado da revisão adversarial): tools/hermes_tools.py::_buscar_e_analisar_email devolve 'Erro: {e}' (sem prefixo '⚠️'/'ERRO|') quando uma exceção escapa do try/except do próprio wrapper -- essa forma específica não é capturada por _parece_mensagem_de_erro (mcp_jobs.py) nem por _looks_like_error (mcp_server.py, mesma lacuna pré-existente no caminho síncrono). Job registraria 'done' com essa mensagem de erro no lugar do resultado nesse caso específico. Não corrigido aqui por decisão de escopo (evitar expandir a heurística além do contrato já estabelecido sem avaliação separada de falsos positivos); fica para o André decidir se normaliza o wrapper (ex.: prefixo consistente) ou amplia a heurística deliberadamente."
  - "NOVA, de infraestrutura (fora do alcance de código): expira_em agora é Timestamp, mas nenhuma política de TTL do Firestore foi configurada na coleção mcp_jobs -- isso é um passo de configuração de infraestrutura (Firestore Console/gcloud), não de código. Sem essa configuração, o campo é só um Timestamp comum; documentos concluídos continuam precisando de limpeza manual como antes."
  - "P01 passos 6-10 do plano continuam abertos: claim de confirmação abandonado, regras Firestore/deploy.yml (mesmo bloqueio de PAT sem escopo workflow já registrado para P00), relatório de reconciliação final do pacote."
  - "Pendências já registradas em blocos anteriores e não tocadas por esta sub-entrega continuam abertas (limite de 200KB do Argos em main.py; risco de corrupção silenciosa em escritas grandes -- ver blocos de P01 sub-entrega 5/N acima)."
proximo_pacote: "P01 -- próximo passo natural é o passo 6 (claim de confirmação abandonado). Antes de escolher sozinho, vale levar ao André o achado de produto desta sub-entrega (formato de erro de buscar_e_analisar_email não capturado pela heurística) e as duas pendências de infraestrutura/processo já registradas (limite de 200KB do Argos em main.py; risco de corrupção silenciosa em escritas grandes) -- nenhuma delas bloqueia prosseguir, mas são decisões que cabem ao André, não a mim sozinho."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 9ccdd93b1f0940665b8068d787e4accfe6002288
pacote: "P01 sub-entrega 7/N -- functions/mcp_server.py (passo 6 do plano): claim de confirmação abandonado deixa de ser lido como confirmação simplesmente expirada"
# Continuação autônoma autorizada por André ("Mesclagem realizada, pode
# prosseguir.") após confirmar a mesclagem da PR #214 -- verificado antes de
# aceitar como fato (git fetch origin main + checagem de que o commit de
# merge está em origin/main), disciplina padrão desta sessão de nunca
# afirmar estado sem checar.
#
# Passo 6 do plano: "Tratar claim de confirmação abandonado: identificar
# operação iniciada e resultado incerto, sem liberar retry que possa
# duplicar efeito." Ligado em espírito ao achado A03 ("aprovação não encerra
# compromisso") e ao próprio requisito de teste de aceite do passo
# ("confirmação interrompida após claim").
#
# Bug encontrado em confirmar_acao/_executar_confirmacao: se um claim
# (mcp_confirmations/{id}/claims/execute, mutex por create() atômico do
# Firestore) é criado mas o processo cai antes de gravar executed_at/result
# (timeout ou reinício de instância), uma nova tentativa com o mesmo
# confirmation_id -- se ainda dentro de expires_at -- ficava presa para
# sempre em "em_execucao" (seguro, mas rotulado errado); se já passado
# expires_at, caía primeiro no teste de expiração (a checagem de claim vinha
# DEPOIS na ordem do código) e devolvia "Confirmação expirada; peça uma nova
# prévia" -- que na prática convida a abrir uma confirmação nova, reivindicar
# de novo e rodar a tool de novo, sem saber se o efeito da primeira tentativa
# (ex.: uma mensagem de WhatsApp) já ocorreu.
estado: pronto_para_revisao
inicio: "2026-09-09T14:50:00Z"
fim: "2026-09-09T15:40:00Z"
arquivos_alterados:
  - functions/mcp_server.py (nova constante _CLAIM_ABANDONADA_APOS = timedelta(minutes=6), entre o timeout_sec=300 da função mcpServer e o _CONFIRMACAO_TTL de 10 min; nova função _status_claim_pendente(claim_data) que decide entre "em_execucao" e "resultado_incerto" a partir de claimed_at; _executar_confirmacao reordenada -- a checagem de claim existente passa a vir ANTES da checagem de expires_at, tanto no caminho normal quanto no ramo de corrida real do except em torno de claim.create())
  - functions/test_hermes_tools.py (_ConfirmationClaim ganha .get() e passa a guardar claim_data, refletindo DocumentReference real; 5 testes novos em TestConfirmacaoPersistida: claim recente reporta em_execucao sem reexecutar, claim abandonado reporta resultado_incerto sem reexecutar, claim abandonado prevalece mesmo com confirmação já expirada, claim sem claimed_at válido não quebra e fica do lado seguro, corrida real no create() aplica a mesma regra de claim pendente)
  - functions/test_mcp_server.py (1 teste novo: resultado_incerto marca isError:true no envelope MCP devolvido por confirmar_acao via _handle_tools_call)
decisoes:
  - id: p01-sub7-claim-abandonado-nao-e-mais-lido-como-expirada
    motivo: "Passo 6 do plano fechado: a existência de um claim para o confirmation_id passa a ser verificada ANTES do teste de expires_at -- uma vez que um claim é encontrado, este confirmation_id nunca mais executa a tool, para sempre (só relata em_execucao ou resultado_incerto). _status_claim_pendente distingue os dois pelo tempo decorrido desde claimed_at contra a nova constante _CLAIM_ABANDONADA_APOS (6 min), deliberadamente entre os dois limites já existentes e documentados no próprio arquivo: acima do timeout_sec=300 (5 min) da função mcpServer -- para nunca rotular como abandonado um claim que ainda pode estar dentro do próprio limite de execução da função --, e abaixo do _CONFIRMACAO_TTL de 10 min -- para o estado ficar identificável como resultado_incerto antes que a confirmação em si pareça só expirada. Resolver de verdade (sweep de leases vencidos com resultado observado, heartbeat, geração) é o escopo maior do P04, citado explicitamente no plano; esta correção não antecipa esse framework -- só evita que o estado hoje incerto seja mal rotulado de um jeito que convide a duplicar o efeito. Uma corrida real entre a checagem de claim e o claim.create() (outra chamada toma o claim primeiro) aplica a mesma _status_claim_pendente, não um em_execucao hardcoded -- coberto por teste dedicado que simula a corrida de verdade via monkeypatch de create()."
    autoridade: existente_ou_nova
  - id: p01-sub7-achado-revisao-campo-erro-em-vez-de-message
    motivo: "Achado should-fix da revisão adversarial: resultado_incerto originalmente usava uma chave \"message\" (sem \"erro\"), então o contrato genérico de _handle_tools_call (is_err = bool(result.get(\"erro\"))) calculava isError:false -- o mesmo sinal neutro do em_execucao meramente transitório, enfraquecendo na prática a garantia de não duplicar efeito: nada impedia estruturalmente um agente chamador menos cuidadoso de ler a mensagem como um \"aguarde\" e mesmo assim abrir uma confirmação nova para a mesma ação. Corrigido movendo o texto explicativo para a chave \"erro\" -- isError:true passa a sair automaticamente do contrato genérico já existente, sem caso especial em nenhum call site. Três testes existentes ganharam asserção assertTrue(result.get(\"erro\")) e um teste novo de envelope (test_confirmar_acao_com_resultado_incerto_marca_iserror, em test_mcp_server.py) prova que isError:True propaga de fato até a resposta MCP."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && source venv/bin/activate && python3 -m pytest test_hermes_tools.py test_mcp_server.py -q"
    - "cd functions && source venv/bin/activate && python3 -m pytest -q"
  resultados:
    - "test_hermes_tools.py isolado: 95 testes, todos passando (5 novos de TestConfirmacaoPersistida entre eles)."
    - "test_hermes_tools.py + test_mcp_server.py juntos: 151 testes + 3 subtests, todos passando."
    - "Suíte completa: 1512 testes + 147 subtests passando, zero falha -- base pré-existente de 1506+147 subtests (fechada na sub-entrega anterior, P01 6/N) mais as 6 diferenças desta sub-entrega (5 em test_hermes_tools.py, 1 em test_mcp_server.py). Sem regressão em nenhum outro módulo."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre o diff completo (mcp_server.py, test_hermes_tools.py, test_mcp_server.py). Veredito explícito: seguro para enviar, com um achado should-fix (a chave \"erro\" vs \"message\", ver decisões -- endereçado antes do envio) e dois nitpicks não-bloqueantes, deliberadamente não corrigidos nesta sub-entrega: (1) um claim pendente encontrado por _executar_confirmacao não passa por _audit_log -- lacuna pré-existente, não introduzida por esta mudança, registrada abaixo como pendência de observabilidade; (2) a nova checagem de claim custa uma leitura extra do Firestore por chamada de confirmar_acao -- aceito como custo necessário para a correção, não uma regressão de desempenho relevante para o volume de chamadas deste fluxo."
  - "Suíte completa rodada antes e depois do diff (incluindo o achado should-fix já corrigido); ver testes.resultados acima. Reexecução isolada de test_hermes_tools.py e test_mcp_server.py em cada rodada de edição, sem nenhuma falha a corrigir durante o desenvolvimento desta sub-entrega."
  - "Todos os três arquivos (mcp_server.py, 68823 bytes; test_hermes_tools.py, 61781 bytes; test_mcp_server.py, 40811 bytes) enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificação de hash local (git hash-object) contra o sha retornado pelo Argos, batendo exatamente nos três -- e reconfirmado depois por git fetch da branch remota + git diff (zero diferença) e por git rev-parse dos blobs remotos contra os hashes locais, mesma disciplina de verificação por diff (não só sha) estabelecida como necessária desde a sub-entrega P01 5/N para escritas grandes."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: passo 6 de P01 (claim de confirmação abandonado deixa de ser lido como confirmação simplesmente expirada; resultado_incerto vem com isError:true)."
  - "NOVA, de observabilidade (não-bloqueante, achado da revisão adversarial, pré-existente): um claim pendente encontrado por _executar_confirmacao (em_execucao ou resultado_incerto) não passa por _audit_log -- só a execução de fato (sucesso/erro da tool) é auditada hoje. Não corrigido nesta sub-entrega por não ser parte do escopo do passo 6; fica para o André avaliar se vale ampliar o log de auditoria para incluir tentativas de reexecução barradas por claim."
  - "P01 passos 7-10 do plano continuam abertos: regras Firestore/deploy.yml (mesmo bloqueio de PAT sem escopo workflow já registrado para P00), relatório de reconciliação final do pacote."
  - "Pendências já registradas em blocos anteriores e não tocadas por esta sub-entrega continuam abertas: formato de erro de tools/hermes_tools.py::_buscar_e_analisar_email não capturado pela heurística de mcp_jobs.py (achado de produto da sub-entrega 6/N); TTL do Firestore não configurado para a coleção mcp_jobs (infraestrutura); limite de 200KB do conector Argos em functions/main.py; risco de corrupção silenciosa em escritas via Argos acima de ~50KB (ver blocos de P01 sub-entrega 5/N e 6/N)."
proximo_pacote: "P01 -- os dois itens que restam no pacote são regras Firestore/deploy.yml (bloqueado pelo mesmo PAT sem escopo workflow já registrado para P00) e o relatório de reconciliação final do pacote. Como o bloqueio de infraestrutura de regras/deploy já está registrado e não depende de mim, a recomendação natural é ir direto ao relatório de reconciliação final de P01 -- mas isso fica como recomendação a levar ao André, não decisão já tomada."
```
