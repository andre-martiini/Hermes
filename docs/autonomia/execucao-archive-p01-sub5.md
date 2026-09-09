# Registro de execução (arquivo) — plano-hermes-autonomo-2026-09-06 — P01 sub-entrega 5/N

Arquivo do bloco P01 sub-entrega 5/N, movido para cá em 2026-09-09 (durante
a sub-entrega P01 8/N, reconciliação de registro dos passos 7/8/10).
Motivo: o arquivo ativo (docs/autonomia/execucao.md, então com 37668 bytes)
somado ao novo bloco desta sub-entrega (12229 bytes) chegaria a 49897 bytes
-- no limiar de ~50KB que a sub-entrega P01 5/N (o próprio bloco movido
aqui) registrou como arriscado para uma escrita confiável via Argos MCP.
O bloco mais antigo do arquivo ativo foi movido preventivamente para este
arquivo NOVO e separado -- mesmo raciocínio já registrado nos cabeçalhos
dos arquivos de arquivo anteriores: cada escrita via Argos precisa
reenviar o arquivo inteiro (sem diff/patch), então um arquivo de arquivo
que só cresce eventualmente fica grande demais para qualquer escrita
futura o tocar, mesmo só para adicionar uma nota -- por isso um arquivo de
arquivo novo a cada corte, nunca conteúdo anexado a um dos arquivos de
arquivo já existentes (nenhum dos quatro anteriores foi tocado nesta
operação). Nenhum conteúdo foi perdido -- o bloco abaixo é cópia
byte-a-byte do arquivo ativo de antes deste quinto corte, extraída por
script (não retranscrita à mão), com hash conferido antes e depois do
envio. O arquivo ativo (docs/autonomia/execucao.md) continua sendo a
fonte de verdade a partir da sub-entrega P01 6/N em diante.

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
