

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 9922fd6f29cfc7f5fba9a5b854379f3ff2db82f2
pacote: "P01 (sub-entrega 4/N — mcp_jobs.py)"
# Continuação da divisão do pacote "G" P01 (seção 8 do plano). Cobre os
# passos 5-6 (achado A10) em functions/mcp_jobs.py — execução assíncrona das
# tools longas do canal MCP via gatilho Firestore. PR #189, empilhada sobre
# claude/p01-agent-requests-idempotencia (PR #188, ainda pronto_para_revisao).
# Sem espera de 90 minutos em relação às sub-entregas anteriores: mesmo
# pacote "G", decisão já registrada nos blocos anteriores.
estado: pronto_para_revisao
inicio: "2026-09-07T04:20:00Z"
fim: "2026-09-07T04:46:00Z"
arquivos_alterados:
  - functions/mcp_jobs.py
  - functions/test_mcp_jobs.py (novo)
decisoes:
  - id: p01-a10-mcp-jobs-claim-transacional
    motivo: "Achado A10, passo 5: on_mcp_job_created (gatilho Firestore, at-least-once) podia rodar a mesma tool duas vezes numa reentrega do evento, porque a checagem de status usava o snapshot do próprio evento (potencialmente desatualizado) em vez de uma leitura fresca. Corrigido com _claim(db, ref): leitura+escrita transacional (@firestore.transactional) que só deixa UMA execução prosseguir por job, usando o campo status como sentinela (processing → em_execucao). Mesma ideia de core/idempotency.py (sub-entregas 3/N-3.2/N), adaptada: aqui é claim de execução de um job interno, não deduplicação por chave externa de webhook."
    autoridade: existente_ou_nova
  - id: p01-a10-mcp-jobs-classificacao-erro-resultado
    motivo: "Achado A10, passo 6: o resultado da tool era gravado como done sempre que execute() retornava sem lançar exceção, mesmo quando o próprio resultado indicava erro (dict com chave 'erro' truthy, ou string começando com 'ERRO|'/'⚠️' — convenção já usada no caminho síncrono de mcp_server.py, não inventada aqui). Corrigido com _resultado_indica_erro(), que classifica como error em vez de done nesse caso — sem isso ler_job devolvia um 'sucesso' que não era, contrariando o critério de aceite do plano ('não há falso done quando handler relata erro')."
    autoridade: existente_ou_nova
  - id: p01-a10-mcp-jobs-expira-em-datetime
    motivo: "Achado A10: expira_em era gravado como inteiro Unix (int(time.time()) + TTL), que o TTL do Firestore não reconhece (precisa Timestamp/datetime, não número). Corrigido nos dois pontos de escrita (_claim, ao marcar claim abandonado como error; _executar_job, nos caminhos done e error) para datetime timezone-aware."
    autoridade: existente_ou_nova
  - id: p01-a10-mcp-jobs-claim-abandonado-sem-retry-automatico
    motivo: "Instrução explícita do plano (P01 passo 6): handler cujo efeito pode não ser idempotente não deve ser retentado automaticamente. Um claim em em_execucao mais velho que CLAIM_EXPIRA_APOS (600s) é tratado como abandonado (execução anterior morreu sem concluir — crash, timeout) e marcado error, nunca reprocessado automaticamente pela tentativa que encontrou o claim vencido; decisão de tentar de novo fica manual. CLAIM_EXPIRA_APOS (600s) deliberadamente excede o timeout_sec do gatilho (540s): o Cloud Functions mata a execução com segurança nessa marca, então qualquer execução ainda 'em andamento' aos 600s já foi encerrada à força pela plataforma — não é margem arbitrária, é garantia."
    autoridade: existente_ou_nova
  - id: p01-a10-mcp-jobs-timeout-e-claim-mesma-constante
    motivo: "Achado da revisão adversarial: CLAIM_EXPIRA_APOS e o timeout_sec do gatilho eram dois números soltos sem vínculo no código — uma mudança futura em um sem atualizar o outro podia quebrar em silêncio a garantia de segurança (600 > 540) descrita na decisão anterior. Corrigido antes de publicar: os dois agora derivam de uma única constante _TIMEOUT_SEC (540), com uma asserção no import (assert CLAIM_EXPIRA_APOS > timedelta(seconds=_TIMEOUT_SEC)) e um teste dedicado (TestInvarianteClaimVsTimeout) garantindo a relação."
    autoridade: existente_ou_nova
  - id: p01-a10-mcp-jobs-ler-job-not-found-restaurado
    motivo: "Achado da revisão adversarial: a reescrita inicial de ler_job() havia colapsado o status distinto 'not_found' (job inexistente ou de outro uid — mesma resposta para os dois, para não vazar existência a quem está adivinhando job_id) em 'error' genérico, e removido a guarda de job_id vazio que existia no código original. Nenhum caller de produção (só tools/hermes_tools.py::_consultar_job, um passthrough puro para a tool MCP) fazia match exaustivo nesse valor, mas era uma mudança de contrato público não solicitada e não documentada — restaurado para bater exatamente com o comportamento pré-existente antes de publicar, não deixado como divergência silenciosa."
    autoridade: existente_ou_nova
  - id: p01-a10-mcp-jobs-reaper-fora-de-escopo
    motivo: "Achado da revisão adversarial, aceito como limitação documentada e não corrigido: a recuperação de um claim abandonado só roda quando uma NOVA entrega do evento do gatilho chega para o mesmo documento — 'at-least-once' garante pelo menos uma entrega bem-sucedida, não uma redisparada por crash. Se a instância que detém o claim morrer sem que o Cloud Functions redispare o evento, o job fica em_execucao indefinidamente (ler_job reporta 'processing' para sempre; expira_em só é gravado nos caminhos terminais, então o TTL do Firestore também não recupera esse caso). Resolver isso de verdade exigiria uma função agendada (reaper) varrendo em_execucao vencidos — fora do escopo do achado A10 tal como descrito no plano (dedupe de reentrega e classificação de erro), registrado aqui como candidato a pacote futuro, não como bug desta sub-entrega. Estritamente melhor que o código anterior, que não tinha proteção nenhuma contra reexecução por reentrega."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest test_mcp_jobs -v"
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "test_mcp_jobs (novo arquivo): 32/32 — claim ganho/recusado/concorrente, claim expirado marca error sem reprocessar, claim sem claimed_em tratado como abandonado, invariante CLAIM_EXPIRA_APOS > _TIMEOUT_SEC, classificação de erro (dict/string/exceção), truncamento de resultado grande, contrato de ler_job (not_found/processing/done/error, uid errado, job_id vazio), e o wrapper on_mcp_job_created em si (event.data None/inexistente, execução normal, reentrega de job já em_execucao não roda a tool de novo)"
    - "Python (unittest, suíte completa): 1207/1207 passando (1175 anteriores + 32 novos; 0 regressões)"
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação): leu mcp_jobs.py, test_mcp_jobs.py e mcp_server.py (para comparar a convenção de classificação de erro), rastreou o protocolo real de transação/retry no código-fonte instalado de google.cloud.firestore_v1 (confirmou que uma transação concorrente perdedora recebe Aborted e é retentada pelo wrapper real, relendo estado fresco), e rodou a suíte de testes. Achados reais, todos endereçados antes de publicar (ver decisões p01-a10-mcp-jobs-timeout-e-claim-mesma-constante e p01-a10-mcp-jobs-ler-job-not-found-restaurado) ou aceitos e documentados explicitamente como fora de escopo (ver decisão p01-a10-mcp-jobs-reaper-fora-de-escopo, e a nota sobre o campo erro ser sempre string — já era o contrato antes desta sub-entrega, só estendido ao novo caminho de resultado-que-indica-erro)."
  - "Achados de qualidade de teste da própria revisão, também endereçados: o mock de transação original não cobria claimed_em ausente/tipo inesperado (adicionado test_claim_em_execucao_sem_claimed_em_e_tratado_como_abandonado) e o wrapper decorado on_mcp_job_created não tinha nenhuma cobertura direta (adicionado TestOnMcpJobCreated, chamando .__wrapped__ para contornar a exigência de CloudEvent bruto do decorator do firebase-functions — nenhum outro trigger do repositório testa essa camada decorada, então isto é cobertura nova, não um padrão quebrado)."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Limitação aceita, não corrigida (ver decisão p01-a10-mcp-jobs-reaper-fora-de-escopo): sem uma função agendada (reaper), um claim cuja instância morre sem o Cloud Functions redisparar o evento fica em_execucao indefinidamente. Candidato a P04 (durabilidade de execução) ou sub-entrega dedicada, não bloqueia esta entrega."
  - "Mesmo bloqueio já registrado nas sub-entregas 3/N-3.2/N: functions/main.py e functions/test_github_webhook.py seguem sem publicar (limite de 200k caracteres do Argos)."
  - "IMPORTANTE PARA DECISÃO DE MERGE (já registrada na sub-entrega 3.2/N, segue valendo): mesclar a PR #188 antes de main.py ser desbloqueado muda o comportamento de produção da deduplicação de webhook — ver pendência completa no bloco da sub-entrega 3.2/N. Não afeta diretamente esta PR #189 (mcp_jobs.py é um módulo independente, sem chamador em main.py), mas ambas as PRs seguem empilhadas na mesma cadeia e a decisão de merge de uma pode afetar a ordem de merge da outra."
  - "P01 segue em aberto: firestore.rules (achado A16, passos 7-8), deploy.yml (achado A17, passo 9, já bloqueado por permissão — ver P00), e o relatório de reconciliação do passo 10, ainda não iniciados."
proximo_pacote: "P01 (sub-entrega 5/N ou conclusão dos passos 7-10)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 9922fd6f29cfc7f5fba9a5b854379f3ff2db82f2
pacote: "P01 (sub-entrega 4.1/N — resposta ao achado do Codex na PR #189)"
# Não é uma nova sub-entrega de escopo do plano; é a resposta ao ciclo de
# revisão da sub-entrega 4/N (PR #189, ainda pronto_para_revisao, não
# reescrita — só complementada aqui por ser um bloco novo). Mesmos arquivos
# (functions/mcp_jobs.py, functions/test_mcp_jobs.py), dois commits novos
# na mesma branch (claude/p01-mcp-jobs-reentrega-claim), seguindo a
# orientação da skill de shipping para responder a comentários de revisão
# (mesmo padrão já usado nas sub-entregas 3.1/N e 3.2/N para a PR #188).
estado: pronto_para_revisao
inicio: "2026-09-07T04:55:00Z"
fim: "2026-09-07T05:14:00Z"
arquivos_alterados:
  - functions/mcp_jobs.py
  - functions/test_mcp_jobs.py
decisoes:
  - id: p01-codex-claim-jovem-levanta-em-vez-de-devolver-none
    motivo: "Achado real do Codex na PR #189 (P1, 'Avoid acknowledging retries for an orphaned fresh claim'): _claim() (sub-entrega 4/N) devolvia None em silêncio ao encontrar um claim em_execucao ainda dentro de CLAIM_EXPIRA_APOS — e on_mcp_job_created então retornava normalmente, o que o Cloud Functions registra como invocação BEM-SUCEDIDA mesmo que a tool nunca tenha rodado para aquele job. Cenário: a transação que grava o claim comita no servidor mas a resposta se perde para o cliente (commit ambíguo — mesma classe de problema já corrigida em core/idempotency.py nas sub-entregas 3/N-3.1/N); a invocação que fazia essa gravação nunca chega a chamar _executar_job. Se uma entrega duplicada do MESMO evento (Pub/Sub at-least-once) chegar enquanto o claim ainda está 'jovem' — justamente a entrega mais provável de acontecer, por corrida de ack, não depois de CLAIM_EXPIRA_APOS — ela encontrava em_execucao recente e retornava sucesso sem a tool ter sido executada por ninguém. Corrigido: esse ramo agora levanta ClaimAindaValidoError (nova exceção, mesmo precedente de ReservaEmAndamentoError em core/idempotency.py) em vez de devolver None — a invocação falha visivelmente nos logs/métricas do Cloud Functions em vez de mentir."
    autoridade: existente_ou_nova
  - id: p01-codex-retry-false-hardcoded-para-firestore-trigger
    motivo: "Autocorreção feita ao investigar o achado do Codex (não veio de nenhum revisor): a documentação anterior do módulo (sub-entrega 4/N) atribuía a duplicidade de entrega a uma política de retry-em-caso-de-erro do Cloud Functions/Eventarc. Verificado lendo o código-fonte instalado de firebase_functions.options: FirestoreOptions (classe usada por on_document_created) NÃO herda de EventHandlerOptions e não expõe nenhum campo retry — seu próprio _endpoint() grava retry=False de forma incondicional. Ou seja, para este gatilho específico, uma invocação que FALHA nunca é redisparada automaticamente pela plataforma — não é uma configuração ausente, é estruturalmente impossível nesta versão da lib. A duplicidade de entrega que este módulo protege vem da semântica at-least-once do Pub/Sub por trás do Eventarc (pode entregar o MESMO evento mais de uma vez mesmo após sucesso), não de retry-em-erro. Docstring do módulo corrigida para essa atribuição correta — isso também significa que levantar ClaimAindaValidoError (decisão anterior) NÃO desencadeia sozinho uma nova tentativa; só uma entrega duplicada independente do mesmo evento pode recuperar o job, ver limitação aceita já registrada na sub-entrega 4/N."
    autoridade: existente_ou_nova
  - id: p01-codex-claim-idade-na-mensagem-em-vez-de-janela-de-graca
    motivo: "Achado da segunda revisão adversarial (dedicada a esta correção, não à sub-entrega 4/N original): levantar ClaimAindaValidoError para TODO claim jovem também captura o caso benigno — uma tentativa irmã genuinamente em andamento com sucesso —, fazendo essa invocação redundante (mas inofensiva) aparecer como falha nos logs/métricas junto com o caso realmente órfão, sem diferenciação. Considerado e rejeitado: uma 'janela de graça' separada (só levantar se o claim tiver mais que alguns segundos) — exigiria um segundo limiar arbitrário sem dado real sobre a distribuição de tempo das entregas duplicadas do Pub/Sub neste projeto, ao contrário de CLAIM_EXPIRA_APOS (derivado de _TIMEOUT_SEC, não inventado). Em vez disso: a mensagem da exceção agora inclui a idade real do claim (segundos desde claimed_em), para quem investigar um erro nos logs distinguir na hora um claim de poucos segundos (provável duplicata benigna) de um de vários minutos (provável órfão) sem o código precisar adivinhar um limiar. Custo aceito: ruído ocasional nos logs para o caso benigno; benefício: nunca mais perder silenciosamente o único sinal de um claim genuinamente órfão."
    autoridade: existente_ou_nova
  - id: p01-mcp-jobs-drift-transcricao-corrigido-antes-de-prosseguir
    motivo: "Falha de processo própria, não achado de revisor: a verificação obrigatória por hash (git hash-object local vs. sha devolvido pelo Argos, exigida pela skill de shipping) pegou uma divergência real no primeiro envio de test_mcp_jobs.py — uma palavra extra ('já') inserida por engano numa docstring de comentário durante a transcrição do arquivo para a chamada da tool (sha local 251cfe0... vs. sha remoto 353ed60...). Sem código afetado (só texto de docstring), mas a skill é explícita que qualquer divergência de transcrição deve ser corrigida antes de prosseguir, não descartada como cosmética. Corrigido baixando o conteúdo publicado, aplicando a correção pontual por script (não retype manual, para não introduzir um segundo drift), confirmando hash idêntico ao local ANTES de reenviar, e publicando um commit de correção dedicado (f0642d2) explicando o motivo. Registrado aqui para reforçar por que a verificação de hash pós-escrita nunca pode ser pulada, mesmo para uma mudança aparentemente pequena."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest test_mcp_jobs -v"
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "test_mcp_jobs: 32/32 — 3 testes atualizados para esperar ClaimAindaValidoError em vez de None no ramo de claim jovem (test_claim_concorrente_apenas_um_ganha, test_claim_em_execucao_recente_levanta_sem_alterar_documento — renomeado de _nao_prossegue_nem_altera —, e test_event_reentrega_de_job_ja_em_execucao_nao_roda_tool_de_novo); nenhum teste assert sobre o texto da mensagem da exceção, então a inclusão da idade do claim na mensagem (decisão p01-codex-claim-idade-na-mensagem-em-vez-de-janela-de-graca) não exigiu mudança adicional de teste"
    - "Python (unittest, suíte completa): 1207/1207 passando (mesmo total da sub-entrega 4/N — 0 regressões, 0 testes novos nesta rodada além dos 3 já recontados acima)"
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio, dedicada especificamente à resposta ao Codex — distinta da revisão da sub-entrega 4/N original): verificou que os testes atualizados não são vácuos revertendo o fix localmente, confirmando que os 3 testes falham sem ele, e restaurando o código; verificou de forma independente, relendo o código-fonte instalado, que (a) o rollback da transação ao levantar dentro de _txn não deixa nenhum estado parcial gravado, (b) a exceção propaga limpa através do wrapper não-decorado do gatilho (nenhum try/except em on_mcp_job_created ao redor de _claim), e (c) retry=False é de fato hardcoded para FirestoreOptions, não apenas o default. Não encontrou nenhum bug bloqueante; achado único foi o ruído de log para o caso benigno (ver decisão p01-codex-claim-idade-na-mensagem-em-vez-de-janela-de-graca)."
  - "Verificação de hash pós-escrita (git hash-object local vs. sha do Argos) pegou uma divergência de transcrição real antes de ela ficar para trás no histórico — ver decisão p01-mcp-jobs-drift-transcricao-corrigido-antes-de-prosseguir. Commits publicados na branch claude/p01-mcp-jobs-reentrega-claim: 93f78606 (mcp_jobs.py), e68d6ce7 (test_mcp_jobs.py, com o drift), f0642d26 (correção do drift, hash final confirmado idêntico ao local)."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Mesma limitação aceita da sub-entrega 4/N (não fechada por este fix, só deixada de ser mascarada como sucesso — ver decisão p01-codex-retry-false-hardcoded-para-firestore-trigger): sem uma função agendada (reaper), a recuperação de um claim genuinamente abandonado ainda depende de uma entrega duplicada tardia do mesmo evento chegar depois de CLAIM_EXPIRA_APOS. Candidato a P04, não bloqueia esta entrega."
  - "Mesmo bloqueio já registrado nas sub-entregas 3/N-4/N: functions/main.py e functions/test_github_webhook.py seguem sem publicar (limite de 200k caracteres do Argos)."
  - "IMPORTANTE PARA DECISÃO DE MERGE (já registrada na sub-entrega 3.2/N, segue valendo): mesclar a PR #188 antes de main.py ser desbloqueado muda o comportamento de produção da deduplicação de webhook. Não afeta diretamente a PR #189, mas ambas seguem empilhadas na mesma cadeia."
  - "P01 segue em aberto: firestore.rules (achado A16, passos 7-8), deploy.yml (achado A17, passo 9, já bloqueado por permissão — ver P00), e o relatório de reconciliação do passo 10, ainda não iniciados. Falta ainda postar @codex review na PR #189 e aguardar/esgotar novo ciclo de comentários (protocolo padrão de 3min/5min) antes de seguir para os passos 7-10."
proximo_pacote: "P01 (sub-entrega 5/N ou conclusão dos passos 7-10, após esgotar o ciclo de revisão do Codex na PR #189)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 9922fd6f29cfc7f5fba9a5b854379f3ff2db82f2
pacote: "P01 (sub-entrega 4.2/N — segunda rodada do Codex na PR #189: recuperação de claim vencido na leitura)"
# Não é uma nova sub-entrega de escopo do plano; é a resposta a uma SEGUNDA
# rodada de comentário do Codex, chegada 3 minutos após o @codex review
# postado ao final da sub-entrega 4.1/N (protocolo padrão de checagem
# combinado com André). Mesmos arquivos (functions/mcp_jobs.py,
# functions/test_mcp_jobs.py), dois commits novos na mesma branch
# (claude/p01-mcp-jobs-reentrega-claim).
estado: pronto_para_revisao
inicio: "2026-09-07T05:24:00Z"
fim: "2026-09-07T05:39:00Z"
arquivos_alterados:
  - functions/mcp_jobs.py
  - functions/test_mcp_jobs.py
decisoes:
  - id: p01-codex-reaper-leve-na-leitura-de-ler-job
    motivo: "Achado real do Codex na PR #189 (P1, segunda rodada, 'Add recovery instead of only raising for orphaned claims'): levantar ClaimAindaValidoError (sub-entrega 4.1/N) torna a falha visível nos logs, mas sozinho NÃO recupera o job — sem uma entrega duplicada tardia e independente do mesmo evento (não garantida, já que retry=False é hardcoded para este gatilho — achado confirmado na própria correção que motivou este achado), o job ficava em_execucao para sempre do ponto de vista de quem consulta via ler_job. Investigado o uso real do protocolo MCP (grep em mcp_server.py): o servidor já INSTRUI explicitamente o cliente MCP a chamar consultar_job/ler_job repetidamente enquanto o job estiver 'processing' ('Chame consultar_job com este job_id em alguns segundos... se ainda estiver processing, consulte de novo'). Ou seja, a consulta em loop já é o padrão de uso real, não uma suposição. Corrigido: ler_job() agora chama uma nova função _reaproveitar_claim_vencido_na_leitura(db, ref) sempre que encontra um job em_execucao — ela reexecuta, dentro de uma NOVA transação, a mesma checagem de expiração que _claim() já faz (mesmo limiar CLAIM_EXPIRA_APOS, mesma garantia de segurança de que a plataforma já matou a execução original), e marca error se o claim ainda estiver vencido no momento da consulta. Isso fecha a lacuna sem precisar de uma função agendada (reaper) nova — a própria consulta do cliente é o mecanismo de recuperação."
    autoridade: existente_ou_nova
  - id: p01-mcp-jobs-dados-claim-abandonado-extraido
    motivo: "Refatoração feita ao implementar a decisão anterior, para evitar duplicação: os campos gravados ao marcar um claim vencido como abandonado (status=error, mensagem, concluido_em, expira_em) agora vêm de uma única função _dados_claim_abandonado(agora), chamada tanto por _claim() (entrega duplicada do evento encontra o claim vencido) quanto por _reaproveitar_claim_vencido_na_leitura() (consulta de ler_job encontra o claim vencido). Antes desta extração, os dois caminhos teriam o mesmo dict escrito duas vezes de forma independente — risco real de uma mudança futura (ex.: ajustar o texto da mensagem de erro) atualizar um caminho e esquecer o outro, silenciosamente. Comportamento de _claim() preservado exatamente (mesmo dict, agora vindo da função compartilhada)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest test_mcp_jobs -v"
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "test_mcp_jobs: 38/38 (32 anteriores + 5 novos em TestReaproveitarClaimVencidoNaLeitura — claim vencido marca error e devolve dados atualizados, claim jovem não altera documento, claim sem claimed_em tratado como vencido, corrida com status já resolvido não sobrescreve, documento inexistente devolve None — + 1 novo em TestLerJob cobrindo a integração via ler_job; test_status_em_execucao_normaliza_para_processing ajustado para usar claimed_em recente, já que um claim sem claimed_em válido agora é corretamente reaproveitado como abandonado — mesmo tratamento que _claim() já dava a esse caso, comportamento correto e não uma regressão)"
    - "Python (unittest, suíte completa): 1213/1213 passando (1207 da sub-entrega 4/N + 6 novos; 0 regressões)"
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio, dedicada especificamente a esta correção): traçou o protocolo real de transação do google.cloud.firestore_v1 instalado (commits são validados por concorrência otimista no servidor; uma transação perdedora recebe Aborted e é automaticamente retentada com leitura fresca — duas escritas concorrentes, ex. uma entrega duplicada tardia no ramo de _claim() colidindo com uma consulta de ler_job no mesmo job, não corrompem estado, uma vence e a outra apenas relê e não faz nada); confirmou que DatetimeWithNanoseconds (o tipo real que o Firestore usa para desserializar Timestamp) é subclasse de datetime, então isinstance(claimed_em, datetime) funciona igual em dados reais e nos testes; verificou que nenhum caminho novo permite dupla execução (a função nova nunca marca em_execucao, só rebaixa um claim vencido para error); e testou empiricamente a não-vacuidade de 3 testes (dois via _reaproveitar_claim_vencido_na_leitura virar no-op, um via desligar só a chamada em ler_job), restaurando o arquivo original e reconfirmando a suíte completa (1213/1213) depois. Único achado: a frase de abertura da docstring do módulo ainda dizia 'três problemas... mais um quarto achado do Codex' quando a lista já tinha 5 itens — corrigido para 'mais dois achados do Codex, pontos 4 e 5' antes de publicar. Nenhum bug de correção encontrado. Veredito: seguro para publicar."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Limitação aceita, mais estreita que antes (ver decisão p01-codex-reaper-leve-na-leitura-de-ler-job): um claim genuinamente abandonado agora se recupera na próxima chamada a ler_job para esse job_id, não só numa entrega duplicada tardia por acaso. O que ainda não fecha é o caso em que NINGUÉM nunca mais consulta esse job_id (cliente desistiu, caiu, ou nunca chegou a perguntar) — aí o documento fica em_execucao indefinidamente no Firestore, sem limpeza automática (TTL só cobre os caminhos terminais). Resolver isso de verdade exigiria um reaper agendado independente de qualquer consulta, ou o protocolo completo de lease/heartbeat da seção 4.5 do plano — candidato a P04, não bloqueia esta entrega."
  - "Mesmo bloqueio já registrado nas sub-entregas 3/N-4.1/N: functions/main.py e functions/test_github_webhook.py seguem sem publicar (limite de 200k caracteres do Argos)."
  - "IMPORTANTE PARA DECISÃO DE MERGE (já registrada na sub-entrega 3.2/N, segue valendo): mesclar a PR #188 antes de main.py ser desbloqueado muda o comportamento de produção da deduplicação de webhook. Não afeta diretamente a PR #189, mas ambas seguem empilhadas na mesma cadeia."
  - "P01 segue em aberto: firestore.rules (achado A16, passos 7-8), deploy.yml (achado A17, passo 9, já bloqueado por permissão — ver P00), e o relatório de reconciliação do passo 10, ainda não iniciados. Falta postar @codex review de novo na PR #189 e aguardar/esgotar mais um ciclo de comentários (protocolo padrão de 3min/5min) antes de seguir para os passos 7-10."
proximo_pacote: "P01 (sub-entrega 5/N ou conclusão dos passos 7-10, após esgotar o ciclo de revisão do Codex na PR #189)"
```
