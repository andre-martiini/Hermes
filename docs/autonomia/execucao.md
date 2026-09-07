# Registro de execução — plano-hermes-autonomo-2026-09-06

Um bloco por pacote (P00–P18), no formato da seção 14.2 do plano. Cada pacote novo é acrescentado ao final; nenhum bloco anterior é reescrito depois de `validado`. Sem segredos nem conteúdo privado — apenas referências a artefatos e IDs.

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 31d2cf959e7c755f8852001405e496382ef0b5d9
pacote: P00
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T00:53:00Z"
fim: "2026-09-07T01:10:00Z"
arquivos_alterados:
  - docs/autonomia/baseline.md (novo)
  - docs/autonomia/execucao.md (novo)
  - functions/tests_autonomy/README.md (novo, diretório de convenção)
  - tests/rules/README.md (novo, diretório de convenção)
arquivos_bloqueados:
  - path: .github/workflows/deploy.yml
    mudanca: "adicionar firestore:rules ao --only do passo de deploy"
    motivo: "GitHub 403 — PAT do Argos sem escopo workflow; requer aplicação manual"
decisoes:
  - id: p00-firestore-rules-no-deploy
    motivo: "A16/A17 do plano: firestore.rules tem restrições específicas mas o deploy nunca publica esse arquivo; correção pontual e de baixo risco preparada, mas bloqueada por permissão (ver arquivos_bloqueados) — não esperar P01 pra aplicá-la manualmente."
    autoridade: existente_ou_nova
  - id: p00-emulador-adiado
    motivo: "Testes de lógica pura não dependem de emulador; ligar Firestore Emulator só quando P01 precisar de teste de transação/concorrência real."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "npm install && npm test"
    - "python -m venv functions/venv && functions/venv/bin/pip install -r functions/requirements.txt"
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "Frontend (vitest): 248/248 passando, 20/20 arquivos"
    - "Python (unittest): 1146/1146 passando (com tentativas de rede real não bloqueadas — ver baseline.md seção 3)"
evidencias:
  - docs/autonomia/baseline.md
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Confirmar em produção se firestore.rules publicado hoje corresponde ao do repositório (não verificável deste ambiente)"
  - "Emulador Firestore: adiar para P01"
  - "tests/rules/ e functions/tests_autonomy/: diretórios criados vazios (só README), P01+ populam"
  - "APLICAR MANUALMENTE: adicionar firestore:rules ao --only de .github/workflows/deploy.yml (Argos não tem escopo workflow no PAT — ver arquivos_bloqueados)"
  - "Considerar dar escopo workflow ao PAT do Argos, ou aceitar que toda mudança de CI deste plano (P00, P01, P17) precisa de aplicação manual"
proximo_pacote: P01
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: cf1b89814b3b64f06dca5b3712fac41a809f1b58
pacote: P01 (sub-entrega 1/N — outbox_aprovacao.py)
# P01 é pacote "G" (grande); seção 8 do plano permite dividir em PRs
# sequenciais preservando a ordem interna dos passos. Esta sub-entrega cobre
# integralmente os passos 1-2 do P01 (achados A03 e A04), restritos ao
# módulo outbox_aprovacao.py. Os demais arquivos do escopo de P01
# (agent_requests.py, promocao_autonomia.py, core/idempotency.py,
# mcp_jobs.py, mcp_server.py, firestore.rules, deploy.yml — passos 3-10)
# ficam para sub-entregas seguintes, ainda dentro de P01.
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T01:15:00Z"
fim: "2026-09-07T02:40:00Z"
arquivos_alterados:
  - functions/outbox_aprovacao.py
  - functions/test_outbox_aprovacao.py
  - functions/test_promocao_autonomia.py
  - functions/atencao_whatsapp.py
  - functions/test_atencao_whatsapp.py
  - .gitignore
decisoes:
  - id: p01-a03-desfecho-fila-nao-envio
    motivo: "A03: aprovar_rascunho() só transiciona o rascunho para 'pending' (enfileirado); quem envia de fato é um worker assíncrono separado. O parâmetro desfecho passado a resolver_item() dizia 'mensagem aprovada e enviada' (sem qualificador), uma alegação de entrega que o código não garante. Corrigido para 'mensagem aprovada e enviada para a fila', igual ao texto já usado na nota de diário, na mensagem do Telegram e no retorno final da própria função (essas três já estavam corretas; só o desfecho estava divergente)."
    autoridade: existente_ou_nova
  - id: p01-a04-remover-fallback-nao-transacional
    motivo: "A04: aprovar_rascunho() e descartar_rascunho() caíam para uma escrita não protegida (get + validate + update sem transação) sempre que a transação atômica falhasse por QUALQUER motivo — inclusive falha real de produção (ex.: Aborted após esgotar tentativas, Firestore indisponível), não só incompatibilidade de mock em teste. Isso reabre a condição de corrida com liberar_rascunhos_promovidos que a transação existe para prevenir. Fallback removido nas duas funções: sem suporte a transação (hasattr(db,'transaction') falso) retorna erro_configuracao; falha real da transação retorna erro_transacao. Nenhum caminho escreve em whatsapp_outbox fora da transação. Os 5 pontos de chamada em produção (hermes_core_logic.py callback do Telegram, tools/hermes_tools.py, atencao_whatsapp.py, liberar_rascunhos_promovidos) foram lidos e confirmados seguros para os novos status — nenhum faz match exaustivo de status."
    autoridade: existente_ou_nova
  - id: p01-mock-transaction-protocolo-real
    motivo: "Causa raiz encontrada por leitura do código-fonte instalado de google.cloud.firestore_v1.transaction: o decorator @firestore.transactional (_Transactional._pre_commit) chama transaction._clean_up() e transaction._begin(retry_id=...) antes de cada tentativa. Os test doubles _MockTransaction em test_outbox_aprovacao.py e test_promocao_autonomia.py não implementavam esses dois métodos, então testes que exercitavam o decorator real (não os que faziam patch de firestore.transactional para identidade) quebravam com AttributeError — e é por isso que o fallback não-transacional existia e 'funcionava' nos testes. Adicionados _clean_up/_begin nos dois mocks, espelhando a semântica real (in_progress checa self._id is not None). Também removido, em TestAprovacaoTransicao (test_outbox_aprovacao.py) e TestLiberacaoECancelamento (test_promocao_autonomia.py), o patch de firestore.transactional para identidade que bypassava o decorator real — agora esses testes exercitam o mesmo caminho de código da produção."
    autoridade: existente_ou_nova
  - id: p01-gitignore-functions-venv
    motivo: "Achado operacional do P00 (não do plano): functions/venv/ não estava coberto por nenhum padrão do .gitignore (só hermes-voice-client/.venv/ e afins). git add -A acidental nesse diretório já aconteceu uma vez nesta sessão. Adicionada uma linha ao .gitignore; risco mínimo, sem relação funcional com o resto desta sub-entrega."
    autoridade: existente_ou_nova
  - id: p01-codex-atencao-whatsapp-notifica-falha
    motivo: "Comentário do Codex na PR #186 (P1): _processar_aprovacao_outbox (atencao_whatsapp.py), um handler Firestore on_document_created sem retry automático, descartava em silêncio os novos status erro_transacao/erro_configuracao de aprovar_rascunho/descartar_rascunho — se o dono mandasse 'cancela' no self-chat do WhatsApp e a transação falhasse de verdade, o comando era dado por processado, o rascunho não mudava de estado, e liberar_rascunhos_promovidos podia enviá-lo mesmo assim, contrariando o que o dono pediu. Corrigido com _alertar_se_falha_outbox: nos dois status de erro, loga com o outbox_id e notifica o dono pelo Telegram (reaproveitando os helpers que outbox_aprovacao.py já usa) dizendo que o comando não foi processado e que o card no Telegram continua válido para retry. É uma correção de visibilidade, não estrutural: se a própria notificação do Telegram falhar (mesma indisponibilidade de fundo, por exemplo), o dono não recebe sinal algum e o cenário do Codex volta a valer sem aviso — registrado como limite conhecido, não fechado nesta sub-entrega."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_outbox_aprovacao -v"
    - "cd functions && venv/bin/python -m unittest test_promocao_autonomia -v"
    - "cd functions && venv/bin/python -m unittest test_atencao_whatsapp -v"
  resultados:
    - "Python (unittest, suíte completa): 1153/1153 passando (1146 anteriores + 4 do fix A03/A04 + 3 do fix do achado do Codex; 0 regressões)"
    - "test_outbox_aprovacao: 37/37 (4 novos: 2 cenários de erro_transacao, 2 de erro_configuracao, cobrindo aprovar e descartar)"
    - "test_promocao_autonomia: 25/25, incluindo os testes de cancelamento/liberação agora exercitando o decorator @firestore.transactional real"
    - "test_atencao_whatsapp: 35/35 (3 novos: notifica no erro_transacao, não notifica em sucesso, não notifica em already_decided)"
    - "Frontend (npm test): não reexecutado nesta sub-entrega — nenhum arquivo de frontend foi alterado"
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação) do fix A03/A04: verificou ausência de caminho de escrita desprotegida remanescente, segurança de todos os 5 pontos de chamada para os novos status, fidelidade do mock ao protocolo real (via leitura do código-fonte da lib instalada), não-vacuidade dos testes novos (raciocinado contra o código pré-mudança), isolamento da mudança de texto (grep no repo inteiro), e ausência de arquivos inesperados no diff. Veredito: seguro para publicar."
  - "Achado adicional da revisão do fix A03/A04 (não corrigido nesta sub-entrega, registrado abaixo): o mesmo padrão de fallback não-transacional do A04 ainda existe, sem correção, em promocao_autonomia.py:228 (decidir_promocao_autonomia) e em argos_autorizacao.py:242,348 — este último fora da lista de arquivos do P01 no plano."
  - "Revisão adversarial independente do fix do achado do Codex (_alertar_se_falha_outbox): confirmou wiring correto nos 3 caminhos (aprovar/descartar/editar), assinaturas de import corretas (comparadas linha a linha com o uso já existente em outbox_aprovacao.py), sem risco de notificação duplicada ou falso positivo (os 5 status possíveis de aprovar/descartar foram enumerados), sem risco novo de timeout no handler Firestore (mesmo padrão síncrono de chamada ao Telegram já usado hoje dentro do mesmo trigger), e testes não-vacuos (mocks batem exatamente com os imports tardios usados dentro da função). Veredito: correção correta e bem testada, porém é mitigação de visibilidade — não fecha estruturalmente a corrida que o Codex descreveu (ver decisão p01-codex-atencao-whatsapp-notifica-falha)."
  - "Achado adicional dessa segunda revisão (fora de escopo, registrado abaixo): aplicar_edicao_rascunho (o caminho 'editar' via WhatsApp) nunca usou transação — é um get+update simples, sem a proteção do achado A04 que aprovar_rascunho/descartar_rascunho ganharam nesta sub-entrega. Ou seja, a corrida com liberar_rascunhos_promovidos que o Codex descreveu permanece genuinamente aberta para o comando de edição especificamente, não só para os casos raros de falha de transação em aprovar/descartar."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "P01 segue em aberto: passos 3-10 (agent_requests.py, promocao_autonomia.py — decidir_promocao_autonomia, core/idempotency.py, mcp_jobs.py, mcp_server.py, firestore.rules — achado A16, deploy.yml — achado A17) ainda não iniciados; viram sub-entregas seguintes desta mesma sessão, sem esperar 90 minutos entre sub-entregas de um mesmo pacote (o intervalo de 90 minutos combinado com André se aplica entre pacotes P01→P02 etc., não entre sub-PRs de divisão de um pacote 'G' — ver seção 8 do plano)."
  - "firestore.rules (achado A16) e o ajuste correspondente em deploy.yml (achado A17) permanecem sem correção — ver PR anterior (P00) para o texto exato do bloqueio de permissão do PAT do Argos, que também vai valer para o passo 9 de P01."
  - "achado do mesmo padrão de A04 encontrado (não corrigido) em promocao_autonomia.py:228 e argos_autorizacao.py:242,348 — candidatos a sub-entregas seguintes de P01 ou registro à parte, a decidir quando chegar a esse arquivo no escopo do plano."
  - "aplicar_edicao_rascunho (outbox_aprovacao.py) não tem proteção transacional nenhuma (nem a versão antiga com fallback, nem a nova com erro explícito) — candidato a correção em sub-entrega seguinte de P01, mesmo padrão do A04 aplicado a aprovar/descartar."
  - "A notificação de falha por Telegram (_alertar_se_falha_outbox) é mitigação, não correção estrutural: se o próprio envio ao Telegram falhar, o dono não é avisado e o cenário original do Codex (rascunho enviado apesar do cancelamento) volta a valer sem sinal nenhum. Registrado como limite conhecido; um mecanismo mais forte (retry da transação, ou um estado explícito 'cancelamento pendente' que liberar_rascunhos_promovidos respeite) ficaria para P04 (durabilidade de execução) ou uma sub-entrega dedicada de P01."
proximo_pacote: "P01 (sub-entrega 2/N)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 090a9e585846170da7ea917e276d346fdc320684
pacote: P01 (sub-entrega 2/N — promocao_autonomia.py)
# Continuação da divisão do pacote "G" P01 (seção 8 do plano). Sub-entrega 1
# (PR #186) cobriu outbox_aprovacao.py (passos 1-2) e, como correção de um
# achado do Codex sobre o mesmo PR, atencao_whatsapp.py. Esta sub-entrega
# fecha uma pendência registrada no bloco anterior: o mesmo padrão do achado
# A04 (fallback não transacional após falha real de transação) encontrado em
# promocao_autonomia.py::decidir_promocao_autonomia pela revisão adversarial
# da sub-entrega 1. promocao_autonomia.py consta na lista de arquivos do P01
# no plano. Sem espera de 90 minutos em relação à sub-entrega 1: o intervalo
# combinado com André vale entre pacotes (P01→P02), não entre sub-entregas do
# mesmo pacote "G" — decisão já registrada no bloco anterior.
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T02:32:00Z"
fim: "2026-09-07T02:43:00Z"
arquivos_alterados:
  - functions/promocao_autonomia.py
  - functions/test_promocao_autonomia.py
decisoes:
  - id: p01-a04-promocao-autonomia-remover-fallback
    motivo: "Mesmo achado A04 já corrigido em outbox_aprovacao.py::aprovar_rascunho/descartar_rascunho (sub-entrega 1), agora em decidir_promocao_autonomia(): a função caía para uma escrita get+update não protegida sempre que a transação falhasse por qualquer motivo real (não só incompatibilidade de mock). Duas decisões concorrentes sobre o mesmo tipo (ex.: 'aceitar' e 'nunca' quase simultâneos vindos de dois cliques no Telegram) podiam ambas ler status pendente e ambas escrever. Fallback removido: sem suporte a transação, ou falha real da transação, retorna {'ok': False, 'erro': ...} em vez de escrever fora da transação. Único chamador de produção (tools/hermes_tools.py::_decidir_promocao_autonomia) é um passthrough puro para a tool MCP, confirmado sem match exaustivo de status que isso quebraria."
    autoridade: existente_ou_nova
  - id: p01-promocao-autonomia-mocks-protocolo-real
    motivo: "Consistência com a correção já aplicada em TestLiberacaoECancelamento (sub-entrega 1): removido o patch de identidade em firebase_admin.firestore.transactional que ainda restava em TestDecidirPromocaoAutonomia e TestListarPromocoesPendentesETools — o _MockTransaction do arquivo já implementa o protocolo real (_clean_up/_begin/_commit/_rollback/_max_attempts/_read_only) desde a sub-entrega 1, então esse patch só estava mascarando a exercitação do decorator real nessas duas classes especificamente."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_promocao_autonomia -v"
  resultados:
    - "Python (unittest, suíte completa): 1155/1155 passando (1153 anteriores + 2 testes novos; 0 regressões)"
    - "test_promocao_autonomia: 27/27 (2 novos: falha real de transação e ausência de suporte a transação, ambos provando que nada é escrito fora da transação)"
    - "Frontend (npm test): não reexecutado nesta sub-entrega — nenhum arquivo de frontend foi alterado"
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação): confirmou que a correção fecha a corrida (rastreada até o código-fonte instalado de google.cloud.firestore_v1.transaction), que o _MockTransaction é fiel ao protocolo real, que os 2 testes novos são não-vácuos (falhariam sob o código antigo), que o único chamador de produção não quebra, e que nenhuma outra instância do mesmo padrão A04 resta em promocao_autonomia.py. Veredito: seguro para publicar."
  - "Achado da própria revisão (corrigido nesta sub-entrega, não deixado pendente): TestListarPromocoesPendentesETools.setUp() ainda tinha o patch de identidade em firestore.transactional, inconsistente com as outras duas classes já corrigidas — removido antes de publicar."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "P01 segue em aberto: agent_requests.py (passo 3), core/idempotency.py (passo 4), mcp_jobs.py (passos 5-6), firestore.rules (achado A16, passos 7-8), deploy.yml (achado A17, passo 9, bloqueado por permissão — ver P00), e o relatório de reconciliação do passo 10, ainda não iniciados."
  - "achado do mesmo padrão de A04 em argos_autorizacao.py:242,348 permanece fora do escopo de P01 (esse arquivo não consta na lista de arquivos do pacote no plano) — candidato a registro à parte ou a um pacote futuro."
  - "aplicar_edicao_rascunho (outbox_aprovacao.py) e a notificação de falha por Telegram em atencao_whatsapp.py seguem como pendências já registradas no bloco da sub-entrega 1, ainda não fechadas."
proximo_pacote: "P01 (sub-entrega 3/N)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 7782388d8958d017d4832031a9492359ebade9c8
pacote: P01 (sub-entrega 3/N — agent_requests.py e core/idempotency.py)
# Continuação da divisão do pacote "G" P01 (seção 8 do plano). Cobre o passo
# 3 (agent_requests.py — achado A01: enfileirar_ou_atualizar/concluir liam e
# escreviam fora de transação) e o passo 4 (core/idempotency.py — falha na
# verificação de idempotência não pode virar "pode processar" silenciosamente).
# Descobriu um bloqueio de infraestrutura genuinamente novo (ver
# arquivos_bloqueados): main.py excede o limite de tamanho da escrita via
# Argos, então a parte do passo 4 que amarra core/idempotency.py ao único
# chamador de produção (githubWebhook) fica pendente de aplicação manual ou
# de uma solução de infraestrutura — ver decisão p01-idempotency-main-py-bloqueado.
# Sem espera de 90 minutos em relação à sub-entrega 2: mesmo pacote "G",
# decisão já registrada nos blocos anteriores.
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T03:05:00Z"
fim: "2026-09-07T03:15:00Z"
arquivos_alterados:
  - functions/agent_requests.py
  - functions/test_agent_requests.py
  - functions/core/idempotency.py
  - functions/test_idempotency.py (novo)
  - functions/test_atencao_whatsapp.py
arquivos_bloqueados:
  - path: functions/main.py
    mudanca: "githubWebhook: capturar a exceção de core.idempotency.check_and_register e responder 503 (sem processar o evento) em vez de deixá-la propagar sem tratamento — texto exato já pronto localmente, só não publicado."
    motivo: "functions/main.py tem 681.703 caracteres; a ferramenta de escrita do Argos (argos_escrever_arquivo_repositorio) limita o parâmetro conteudo a 200.000 caracteres e só aceita substituição integral do arquivo (não há modo patch/diff). Não há como publicar NENHUMA mudança em main.py por esse caminho, por menor que seja, enquanto o arquivo permanecer acima desse limite — não é específico desta mudança."
decisoes:
  - id: p01-a01-agent-requests-transacional
    motivo: "A01: enfileirar_ou_atualizar() fazia get() seguido de set()/update() fora de transação; uma chamada concorrente a concluir() podia decidir o status do pedido entre a leitura e a escrita daqui (ex.: enfileirar_ou_atualizar lê 'pendente', concluir() termina o pedido nesse meio-tempo, e enfileirar_ou_atualizar ainda assim sobrescreve payload/timestamps de um pedido que virou terminal — ou o inverso). Mesmo achado, mesma direção do fix já aplicado a outbox_aprovacao.py e promocao_autonomia.py nas sub-entregas 1-2: leitura e escrita de cada função agora acontecem dentro de uma única transação atômica (@firestore.transactional); falha real da transação retorna {'erro': ...} em vez de cair para escrita fora de transação. Escopo deliberadamente restrito ao que o passo 3 do plano pede ('transformar enfileiramento/conclusão legados em transições condicionais') — o protocolo completo de lease/geração/heartbeat descrito na seção 4.5 do plano fica para P04, não é implementado aqui."
    autoridade: existente_ou_nova
  - id: p01-idempotency-check-and-register-propaga-excecao
    motivo: "P01 passo 4: core/idempotency.py::check_and_register capturava qualquer exceção da verificação transacional e retornava True — ou seja, uma falha real (Firestore indisponível, contenção esgotando tentativas) virava silenciosamente 'trate como novo, pode processar', arriscando duplicar exatamente o efeito que a idempotência existe para evitar. Corrigido: a exceção agora propaga para o chamador. O único chamador de produção é functions/main.py::githubWebhook (confirmado por grep no repo inteiro); o texto que captura essa exceção e responde 503 sem processar o evento está pronto localmente mas não foi publicado nesta sub-entrega — ver arquivos_bloqueados. Mesmo sem essa amarração publicada, a correção já muda o comportamento em produção hoje: o call site atual (sem try/except) deixa a exceção subir sem tratamento pela função HTTP, e o runtime padrão do Cloud Functions (Python, 2ª geração) responde 5xx automaticamente a uma exceção não tratada — o achado central (nunca converter falha de idempotência em permissão de processar) já fica fechado; o que falta é só a resposta 503 explícita com log específico, mais limpa que o 500 genérico do runtime."
    autoridade: existente_ou_nova
  - id: p01-idempotency-main-py-bloqueado
    motivo: "Descoberta operacional nesta sub-entrega, não um achado do plano: qualquer mudança em functions/main.py (16.184 linhas, 681.703 caracteres) é impossível de publicar via argos_escrever_arquivo_repositorio, cujo parâmetro conteudo tem limite de 200.000 caracteres e não aceita patch/diff — só substituição integral. Isso não é específico deste fix; bloqueia TODA futura mudança em main.py enquanto ele permanecer deste tamanho, o que é provável de recorrer em pacotes futuros do plano (main.py concentra a maior parte das Cloud Functions do Hermes). Três caminhos possíveis, nenhum decidido: (1) uma nova tool no Argos MCP que aceite diff/patch em vez de conteúdo integral; (2) aumentar o limite de conteúdo da tool atual, se não houver uma razão de fundo para o teto de 200.000; (3) dividir main.py em módulos menores — mudança estrutural maior, fora do escopo de uma sub-entrega, mas que resolveria o problema de raiz e ajudaria a legibilidade/revisão independente do limite da ferramenta. Registrado para André decidir; não bloqueia a continuidade do plano porque o achado de segurança em si (check_and_register) já está fechado (ver decisão anterior) — só a resposta HTTP explícita fica pendente."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_agent_requests -v"
    - "cd functions && venv/bin/python -m unittest test_idempotency -v"
    - "cd functions && venv/bin/python -m unittest test_atencao_whatsapp -v"
  resultados:
    - "Python (unittest, suíte completa): 1166/1166 passando (1155 anteriores + 7 de agent_requests.py + 4 de test_idempotency.py, novo; 0 regressões)"
    - "test_agent_requests: 21/21 (7 novos: 3 de enfileirar_ou_atualizar — new/update com falha de transação, sem suporte a transação — e 2 de concluir, com os mesmos dois cenários, mais os 2 já existentes de cada função revalidados sob o novo caminho transacional)"
    - "test_idempotency: 4/4, novo arquivo — chave nova, chave repetida, falha real de transação propaga exceção, ausência de suporte a transação propaga exceção"
    - "test_atencao_whatsapp: 35/35 (0 novos; mocks atualizados para o protocolo de transação real, sem o que o teste de TestHookAgentRequests quebraria contra o novo enfileirar_ou_atualizar transacional)"
    - "Não incluído nesta sub-entrega: um teste novo para o caminho 503 de githubWebhook (test_github_webhook.py) já foi escrito localmente, mas fica sem publicar até main.py poder ser atualizado — publicá-lo sozinho faria o teste falhar contra o main.py real, que ainda não tem a captura da exceção."
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação): confirmou, por leitura do código-fonte instalado de google.cloud.firestore_v1.transaction, que @firestore.transactional limpa e reinicia o estado da transação a cada tentativa (sem escrita parcial vazando entre retries), que só exceptions.Aborted é retentado automaticamente (qualquer outra propaga na hora, batendo com o except Exception externo), que o caminho 503 de githubWebhook (quando aplicado) retorna antes de qualquer escrita, e que core/idempotency.py não engole mais nenhuma exceção. Veredito: a correção transacional é correta e fecha a corrida pretendida."
  - "Achado da própria revisão (corrigido nesta sub-entrega, não deixado pendente): faltava um teste provando que uma falha de transação ao ATUALIZAR um pedido pendente já existente (não só ao criar um novo) deixa o documento intocado em enfileirar_ou_atualizar — adicionado test_transacao_falha_ao_atualizar_pedido_existente_nao_corrompe."
  - "Achado da própria revisão (aceito como conhecido, não corrigido): o except Exception ao redor de _exec(transaction) em enfileirar_ou_atualizar/concluir captura qualquer exceção, não só falhas de contenção/transação — um bug não relacionado a concorrência dentro de _exec seria reportado com a mesma mensagem de 'falha ao enfileirar/atualizar de forma atômica', o que pode confundir uma investigação futura. Comportamento ainda seguro (sempre falha fechado, sem corrupção), só a mensagem de log é potencialmente enganosa; mesmo padrão já usado em outbox_aprovacao.py e promocao_autonomia.py nas sub-entregas anteriores, então não é uma regressão introduzida aqui."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "BLOQUEADO (ver arquivos_bloqueados e decisão p01-idempotency-main-py-bloqueado): aplicar manualmente em functions/main.py, dentro de githubWebhook, a captura da exceção de core.idempotency.check_and_register com resposta 503 (texto pronto, não publicado); depois disso, publicar o teste correspondente já escrito em test_github_webhook.py (test_falha_idempotencia_retorna_503_sem_anotar)."
  - "O mesmo bloqueio de tamanho de main.py deve recorrer em pacotes futuros do plano — vale decidir entre André e a próxima sessão qual dos três caminhos (nova tool de diff no Argos, aumento do limite atual, ou dividir main.py em módulos) seguir antes que isso vire um padrão de 'sempre aplicar manualmente' para um arquivo tão central."
  - "P01 segue em aberto: mcp_jobs.py (passos 5-6), firestore.rules (achado A16, passos 7-8), deploy.yml (achado A17, passo 9, já bloqueado por permissão — ver P00), e o relatório de reconciliação do passo 10, ainda não iniciados."
  - "achado do mesmo padrão de A04 em argos_autorizacao.py:242,348, aplicar_edicao_rascunho sem proteção transacional, e a notificação de falha por Telegram como mitigação não estrutural seguem como pendências já registradas nos blocos anteriores, ainda não fechadas."
proximo_pacote: "P01 (sub-entrega 4/N)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 7782388d8958d017d4832031a9492359ebade9c8
pacote: "P01 (sub-entrega 3.1/N — resposta ao achado do Codex na PR #188)"
# Não é uma nova sub-entrega de escopo do plano; é a resposta ao ciclo de
# revisão da sub-entrega 3/N (PR #188, ainda pronto_para_revisao, não
# reescrita — só complementada aqui por ser um bloco novo). Mesmos arquivos
# (functions/core/idempotency.py, functions/test_idempotency.py), commit novo
# na mesma branch (claude/p01-agent-requests-idempotencia), seguindo a
# orientação da skill de shipping para responder a comentários de revisão.
estado: pronto_para_revisao
inicio: "2026-09-07T03:20:00Z"
fim: "2026-09-07T03:55:00Z"
arquivos_alterados:
  - functions/core/idempotency.py
  - functions/test_idempotency.py
decisoes:
  - id: p01-codex-preserva-eventos-apos-commit-ambiguo
    motivo: "Achado real do Codex na PR #188 (não rubber-stamp): check_and_register (sub-entrega 3/N) usava um único sentinela — 'documento existe' = 'já processado, pular'. Se o COMMIT da transação que cria esse sentinela for ambíguo (cliente recebe timeout/erro, mas o Firestore já escreveu no servidor), uma reentrega legítima do GitHub encontraria o sentinela e pularia o evento para sempre, mesmo que o processamento de fato nunca tenha rodado — perda silenciosa e permanente de evento. Corrigido separando o sentinela em dois estados: RESERVADO (tentativa começou) e CONCLUIDO (efeito terminou de verdade, via novo mark_complete()). Só CONCLUIDO é duplicata; RESERVADO recente levanta ReservaEmAndamentoError (nem sucesso nem duplicata); RESERVADO expirado (RESERVA_EXPIRA_APOS=5min) permite retomar."
    autoridade: existente_ou_nova
  - id: p01-idempotency-tri-state-string-rejeitado
    motivo: "Primeira tentativa de fix fez check_and_register devolver uma de três strings (novo/duplicata/em_andamento) em vez de bool. Identificado ANTES de publicar, por raciocínio próprio sobre o call site de produção: o main.py HOJE implantado faz `if not check_and_register(...)`, e `not \"qualquer string não-vazia\"` é sempre False em Python — ou seja, TODA entrega (mesmo duplicata genuína) passaria a ser tratada como nova, desligando silenciosamente a deduplicação inteira do webhook assim que esta PR fosse mergeada, já que main.py não pode ser editado no mesmo lote (ver bloqueio de tamanho, sub-entrega 3/N). Revertido para bool + uma exceção nova (ReservaEmAndamentoError) para o terceiro caso — compatível de verdade com o contrato bool já implantado, com zero edição adicional de main.py necessária para a correção ter efeito de segurança (uma exceção não capturada nunca vira 200, ver decisão seguinte)."
    autoridade: existente_ou_nova
  - id: p01-idempotency-docstring-corrigida-pos-revisao
    motivo: "A revisão adversarial final (design bool+exceção) apontou que a docstring de ReservaEmAndamentoError afirmava existir um `except Exception` no chamador (main.py) já capturando a exceção — falso: `git show HEAD:functions/main.py` confirma que a chamada a check_and_register lá não tem NENHUM try/except ao redor. Verificado o comportamento real: uma exceção não capturada sobe até o crash_handler do functions_framework (500 via error handler registrado em flask, nunca 200) — ou seja, a correção já é segura em produção mesmo sem essa edição de main.py, só não é tão 'limpa' (500 genérico com o texto da exceção no corpo, em vez de um 503 específico e logado) quanto ficaria com o rascunho local de main.py aplicado. Docstring corrigida para descrever esse caminho real em vez do caminho que só existe no rascunho bloqueado."
    autoridade: existente_ou_nova
  - id: p01-idempotency-fencing-token-aceito-como-latente
    motivo: "Achado da revisão adversarial: mark_complete() não é transacional e não verifica se está completando a MESMA reserva que check_and_register concedeu (sem fencing token) — em teoria, se uma tentativa ficasse presa por mais de RESERVA_EXPIRA_APOS (5min) e só então terminasse e chamasse mark_complete, poderia finalizar incorretamente a reserva de uma tentativa seguinte que já tinha retomado o processamento. Aceito como limitação latente, não corrigido: o timeout configurado da função (githubWebhook) fica bem abaixo de 5 minutos, então uma tentativa presa é encerrada pelo runtime antes de chegar a esse ponto — mesmo precedente de decisão usado para o protocolo de lease do P04 (aceitar uma janela teórica não explorável nas condições operacionais atuais, documentar, não bloquear a entrega)."
    autoridade: existente_ou_nova
  - id: p01-anotar-eventos-nao-idempotente-mantido-best-effort
    motivo: "A revisão adversarial sugeriu (no rascunho local de main.py, ainda bloqueado) só chamar mark_complete quando anotar_evento_github_em_tarefas não tiver nenhuma falha parcial. Rejeitado deliberadamente: anotar_evento_github_em_tarefas já trata falha por tarefa como best-effort (uma tarefa falhar não derruba as outras, achado já aceito em sub-entrega anterior) e NÃO é idempotente — se mark_complete ficasse condicionado a zero falhas, uma reentrega subsequente reprocessaria TODAS as tarefas do evento, inclusive as que já tinham sido anotadas com sucesso na tentativa anterior, duplicando anotações. Manter mark_complete incondicional ao término da chamada (independente de falhas parciais internas) é estritamente melhor dado que o efeito interno já não é idempotente — consistente com a decisão de design já tomada para essa função. Registrado aqui para não reabrir a discussão sem essa nota."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest test_idempotency test_github_webhook -v"
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "Python (unittest, suíte completa): 1175/1175 passando (1166 da sub-entrega 3/N + 9 novos de test_idempotency.py reescrito para o design reserva/conclusão; 0 regressões)"
    - "test_idempotency: 9/9 (reserva recente levanta ReservaEmAndamentoError sem reescrever; reserva expirada permite reprocessar; documento legado sem status tratado como reserva expirada; mark_complete bloqueia reentrega mesmo após a reserva expirar; mark_complete preserva reserved_at original; mark_complete numa chave sem reserva prévia não quebra — achado da revisão; mais os 3 já existentes revalidados sob o novo design)"
    - "test_github_webhook: 16/16 no rascunho local (ainda não publicado — mesmo bloqueio de main.py da sub-entrega 3/N)"
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio, dedicada a este design final — as duas revisões anteriores foram sobre designs já superados: a original de sentinela único e a intermediária tri-state) — leu o diff local completo contra origin/main, o código-fonte instalado de google.cloud.firestore_v1.transaction (confirmou que só google.api_core.exceptions.Aborted é retentado automaticamente pelo decorator, e que uma exceção levantada dentro da função decorada nunca é retentada), e o código-fonte instalado de functions_framework/flask (confirmou o caminho até crash_handler/500). Achados: a imprecisão de docstring (corrigida, ver decisão), a ausência de fencing token em mark_complete (aceita como latente, ver decisão), e a sugestão sobre anotar_evento_github_em_tarefas não-idempotente (rejeitada com justificativa, ver decisão). Verificou como sólido: a lógica de arbitragem entre reservas concorrentes via retry de Aborted, a ordem correta dos except no rascunho de main.py (ReservaEmAndamentoError antes do Exception genérico, sem sombreamento), e o uso correto de merge=True+SERVER_TIMESTAMP em mark_complete."
  - "Autocorreção antes de publicar (não veio de nenhum revisor, achado por raciocínio próprio sobre o call site de produção real): o design tri-state por string teria desligado silenciosamente toda a deduplicação do webhook GitHub em produção assim que mergeado — ver decisão p01-idempotency-tri-state-string-rejeitado. Nenhum código desse design chegou a ser publicado."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Mesmo bloqueio já registrado na sub-entrega 3/N: functions/main.py (agora ~682KB, ligeiramente maior) e functions/test_github_webhook.py seguem sem publicar, à espera de uma das três soluções já propostas para o limite de escrita do Argos (nova tool de diff, aumento do limite, ou divisão de main.py em módulos)."
  - "Limitação latente aceita (ver decisão p01-idempotency-fencing-token-aceito-como-latente): se este módulo (core/idempotency.py) vier a ser reusado por um chamador com tempo de execução não necessariamente bem abaixo de RESERVA_EXPIRA_APOS (5min) — o docstring já cita 'update_id de bot' como exemplo genérico — reavaliar a necessidade de um fencing token antes de reusar."
  - "P01 segue em aberto: mcp_jobs.py (passos 5-6), firestore.rules (achado A16, passos 7-8), deploy.yml (achado A17, passo 9, já bloqueado por permissão — ver P00), e o relatório de reconciliação do passo 10, ainda não iniciados."
proximo_pacote: "P01 (sub-entrega 4/N)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 0d18c8a6da7a2c4bea316d6f1455757182fc5973
pacote: "P01 (sub-entrega 3.2/N — segunda rodada de comentários do Codex na PR #188)"
# Continuação do ciclo de resposta a comentários do Codex nesta mesma PR
# (sub-entregas 3/N e 3.1/N). Comentário automático não dispara em push
# simples (só em "PR opened", "marked ready" ou comentário "@codex review")
# — foi preciso comentar "@codex review" explicitamente para obter uma nova
# passada sobre os commits da sub-entrega 3.1/N. Achado real (P1), não
# rubber-stamp: consequência direta do mesmo bloqueio de main.py já
# registrado, não um bug novo em core/idempotency.py.
estado: pronto_para_revisao
inicio: "2026-09-07T04:02:00Z"
fim: "2026-09-07T04:12:00Z"
arquivos_alterados:
  - functions/core/idempotency.py
decisoes:
  - id: p01-codex-mark-complete-sem-chamador-documentado
    motivo: "Achado do Codex (P1, 'Call mark_complete after successful webhook processing'), confirmado por busca no repositório inteiro: main.py — único chamador de produção — não chama mark_complete em NENHUM caminho hoje, só check_and_register. Consequência: toda entrega processada com sucesso fica RESERVADA para sempre (nunca CONCLUIDA); reentrega dentro de RESERVA_EXPIRA_APOS (5min) ainda é barrada sem duplicar efeito (levanta ReservaEmAndamentoError), mas reentrega tardia (após a janela expirar) é tratada como nova e o efeito é reprocessado — isso agora vale para QUALQUER entrega bem-sucedida comum reentregada tardiamente, não só o caso ambíguo original que motivou a sub-entrega 3.1/N. O fix que o Codex sugere (chamar mark_complete nos dois caminhos do webhook) já existe no rascunho local de main.py desde a sub-entrega 3.1/N — não é um gap de implementação, é o MESMO bloqueio de main.py (limite de 200k caracteres do Argos) já registrado em p01-idempotency-main-py-bloqueado, só que agora com uma consequência mais precisa e mais séria do que a registrada até aqui (antes: 'falta só a resposta HTTP explícita'; agora: 'falta a peça que fecha a deduplicação de fato'). Nenhuma mudança de comportamento nesta sub-entrega — só documentação explícita no docstring do módulo, para que a lacuna não seja lida como resolvida só porque os testes unitários deste arquivo (que testam o módulo isolado, não main.py) continuam passando."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "Python (unittest, suíte completa): 1175/1175 passando (sem mudança — só docstring, nenhum teste alterado)"
evidencias:
  - "Sem revisão adversarial dedicada nesta sub-entrega: mudança é documentação pura (docstring), sem alteração de comportamento ou lógica — julgada desnecessária para este escopo específico, diferente das sub-entregas 3/N e 3.1/N que mudaram comportamento real."
  - "Resposta publicada diretamente no comentário do Codex na PR #188 (via argos_comentar_issue_repositorio), reconhecendo o achado como correto, explicando o bloqueio de main.py e a consequência prática, e registrando a decisão de desbloqueio como pendente para André."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "IMPORTANTE PARA DECISÃO DE MERGE: mesclar esta PR #188 antes de main.py ser desbloqueado troca o comportamento de produção de 'sentinela único permanente, mas fail-open em falha real de transação' (o que está implantado hoje) para 'reserva com janela de 5 minutos, sem nunca alcançar CONCLUIDO' — ou seja, deduplicação deixa de ser permanente e passa a valer só dentro dessa janela até main.py poder chamar mark_complete. Continua estritamente mais seguro que hoje quanto a nunca fingir sucesso silencioso, mas reentregas legítimas e comuns que cheguem mais de 5 minutos depois da original passam a reprocessar o evento (duplicar anotação em tarefas) — um comportamento que o sentinela único antigo não tinha para o caso comum (só falhava no caso de erro real de transação, ou quando a própria tentativa original nunca terminava). Registrado explicitamente para André avaliar antes de decidir mesclar: aceitar essa janela temporariamente, ou aguardar main.py ser desbloqueado (um dos 3 caminhos já propostos) antes do merge."
  - "Mesmo bloqueio já registrado nas sub-entregas 3/N e 3.1/N: functions/main.py e functions/test_github_webhook.py seguem sem publicar."
  - "P01 segue em aberto: mcp_jobs.py (passos 5-6), firestore.rules (achado A16, passos 7-8), deploy.yml (achado A17, passo 9, já bloqueado por permissão — ver P00), e o relatório de reconciliação do passo 10, ainda não iniciados."
proximo_pacote: "P01 (sub-entrega 4/N)"
```

---

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