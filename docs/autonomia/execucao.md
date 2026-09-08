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
base_commit: cf1b89814b3b64f06dca5b3712fac41a809f1b58
pacote: P02 (sub-entrega 1/N — identidade e política unificadas)
# P02 é pacote "G" (grande, seção 8 do plano); esta sub-entrega cobre só a
# introdução do módulo puro functions/autonomy/ (contracts.py + policy.py):
# os tipos do modelo unificado de identidade (Principal/TipoPrincipal),
# o motor de decisão (avaliar/mandato_cobre/estado_autonomia_atual) e o
# "piso" de confirmação obrigatória (FLOOR_CONFIRMACAO_OBRIGATORIA), ainda
# não consultado por nenhum canal real. A sub-entrega 2/N religa
# tool_context.py/mcp_server.py para consultar esse motor como preflight.
estado: em_execucao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
# em_execucao porque a PR que carrega o conteúdo completo desta sub-entrega
# (rodadas 2-4 de correção) ainda não foi mesclada — ver seção "PR #191
# mesclada cedo demais" abaixo.
inicio: "2026-09-07T00:53:00Z"
fim: null
arquivos_alterados:
  - functions/autonomy/__init__.py (novo)
  - functions/autonomy/contracts.py (novo)
  - functions/autonomy/policy.py (novo)
  - functions/test_contracts.py (novo)
  - functions/test_policy.py (novo)
decisoes:
  - id: p02-revisao-adversarial-interna-original
    motivo: "Antes de qualquer rodada do Codex, a revisão adversarial interna (sub-agente sem contexto prévio) já pegou 4 achados na primeira versão de policy.py, todos corrigidos antes do primeiro envio: (1) um mandato vigente aprovava o efeito direto pulando o aperto de somente_preparação; (2) destinatario_recursos usava substring crua ('@empresa.com' cobria 'chefe@empresa.com.malicioso.net'); (3) janela de horário cruzando meia-noite (ex. 22:00-06:00) era insatisfazível; (4) falha de leitura de estado_autonomia_atual (Firestore indisponível) colapsava no mesmo default de 'documento ausente' (ATIVO) em vez de SOMENTE_PREPARACAO."
    autoridade: existente_ou_nova
  - id: p02-codex-rodada-1
    motivo: "5 achados P1/P2 na primeira revisão do Codex sobre a PR #191: limite_por_janela sem contagem resolvida era ignorado; sensibilidade ausente escapava de mandato restrito por classe de conteúdo; missão vs. finalidade do mandato não era comparada; reason_code de decisões vindas da matriz padrão alegava mandato por engano; simular_politica() conflava PREPARE_ONLY/DEFER com requer_aprovacao na contagem. Todos corrigidos; commit 23d983698 é o estado do branch logo após esta rodada."
    autoridade: existente_ou_nova
  - id: p02-codex-rodada-2
    motivo: "3 achados: piso de confirmação obrigatória não passava pelo aperto de pausado/somente_preparação; destinatarios_recursos/classes_conteudo_permitidas vazios (tupla vazia, falsy) eram tratados como 'sem restrição' em vez de 'não cobre nada'. A revisão adversarial da própria correção pegou um 3º achado nela mesma: policy_id/constraints_checked do retorno final ficavam incorretos quando a decisão vinha do piso."
    autoridade: existente_ou_nova
  - id: p02-codex-rodada-3
    motivo: "limite_por_janela declarado com usos_na_janela_atual=None (contagem desconhecida) pulava o limite; missao não informada não era comparada contra finalidade (mandato cobria pedido sem missão nenhuma); preparação interna/escrita interna reversível sem mandato viravam ALLOW incondicional — passaram a exigir Principal.origem_humana=True (dono interativo/cliente assistido em tempo real) ou caem para PREPARE_ONLY, conforme a leitura de 'mandato e orçamento válidos' da seção 5.1 do plano."
    autoridade: existente_ou_nova
  - id: p02-codex-rodada-4
    motivo: "valido_ate=None (default do contrato) cobria indefinidamente — agora falha fechado; janela de horário parcialmente configurada (só início ou só fim) pulava a restrição inteira — agora falha fechado; estado_autonomia_atual() tratava valor presente-e-falsy ('') do mesmo jeito que chave ausente, caindo em ATIVO — corrigido com sentinela (_AUSENTE = object()) para distinguir por identidade, não truthiness. A revisão adversarial desta própria rodada pegou 1 achado nela mesma: a correção da janela de horário usava 'inicio or fim' (truthiness) como guarda externa, reintroduzindo o mesmo padrão de bug (strings vazias em ambos os campos escapavam) — corrigido para 'is not None'."
    autoridade: existente_ou_nova
  - id: p02-pr-191-mesclada-cedo-demais
    motivo: "Descoberta em 2026-09-07 ~14:43 UTC: André mesclou a PR #191 em main em 2026-09-07T10:11:11-03:00, usando o commit 23d983698 — o estado do branch logo após a RODADA 1 do Codex, não depois das rodadas 2-4 que continuei a enviar ao mesmo branch nas horas seguintes (via API de escrita do Argos, sem checar se a PR ainda estava aberta). Como uma PR mesclada não aceita mais commits no mesmo merge, as rodadas 2-4 nunca chegaram a main. Isso também resolve um mistério registrado nas rodadas anteriores: o 'Reviewed commit 4965f9e923...' que o Codex citava repetidamente, e que eu tinha catalogado como SHA sintético/inexistente (checagem incompleta: git log --all de um clone que nunca tinha buscado origin/main), é na verdade o próprio commit de merge da PR #191 — o Codex estava revisando main (congelado nesse estado desde o merge) a cada chamada de @codex review, não o branch em evolução; por isso repetia achados que eu já tinha corrigido no branch mas que continuavam presentes em main. Risco real avaliado como baixo: autonomy/policy.py ainda não é consultado por nenhum canal (mcp_server.py, tool_context.py) — é exatamente o que a sub-entrega 2/N vai religar — então os gaps das rodadas 2-4 estão em main mas ainda não estão em uso por nenhum caminho real hoje. Ainda assim, precisam chegar a main antes da sub-entrega 2/N ligar o preflight de verdade. Abri a PR #192 (mesmo branch → main) carregando as rodadas 2-4 completas, com nota explicativa em #191 e pedido de @codex review em #192."
    autoridade: existente_ou_nova
  - id: p02-codex-rodada-5
    motivo: "Achado do Codex sobre a PR #192 (não #191 — já reaberto o ciclo de revisão no branch correto), verificado contra o tip real do branch (e9c6dc301c), não um commit obsoleto: _decisao_padrao_por_classe() concedia ALLOW nos ramos PREPARACAO_INTERNA e ESCRITA_INTERNA_REVERSIVEL checando só principal.origem_humana (bool, default True no contrato). O comentário no código já dizia que a exceção de baixa fricção é para 'dono interativo ou cliente assistido', mas nada no sistema de tipos impedia um Principal do tipo ROTINA_COWORK/RUNNER_SERVICO/TERCEIRO_PORTAL de ser construído com origem_humana=True — um terceiro com humano presente NO PORTAL (ele mesmo, não o dono) recebia o mesmo passe do dono interativo. Corrigido: os dois ramos agora exigem 'if principal.origem_humana and principal.eh_dono():' (eh_dono() só é True para DONO_INTERATIVO/CLIENTE_ASSISTIDO), restaurando a garantia que o comentário original já descrevia. A revisão adversarial desta correção (sub-agente independente) buscou outras ocorrências do mesmo padrão (origem_humana sem eh_dono()) no arquivo inteiro — nenhuma encontrada — e confirmou ausência de regressão nos call-sites e testes existentes."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && python -m unittest test_policy test_contracts -v"
    - "cd functions && python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "test_policy.py + test_contracts.py: 99/99 passando (97 após as 4 rodadas do Codex + 2 testes de regressão da rodada 5, gate eh_dono())"
    - "Suíte completa do repositório: sem regressão nova nos arquivos desta sub-entrega; falhas pré-existentes seguem restritas a test_deteccao_subproduto.py e loaders de test_gmail_bill_pdf/test_mp4_repair, sem relação com autonomy/"
evidencias:
  - "PR #191 (https://github.com/andre-martiini/Hermes/pull/191) — mesclada em main, mas só com a rodada 1 de correções; comentário de nota explicando a situação e redirecionando para #192"
  - "PR #192 (https://github.com/andre-martiini/Hermes/pull/192) — aberta, carrega as rodadas 2-5 completas; comentário https://github.com/andre-martiini/Hermes/pull/192#issuecomment-5572607248 documenta a rodada 5 (gate eh_dono()); aguardando nova resposta do Codex e merge manual do André"
  - "5 rodadas de revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação), uma por rodada de correção — pegaram 2 achados reais nas próprias correções (rodada 2: policy_id/constraints_checked; rodada 4: truthiness na janela de horário), ambos corrigidos com teste de regressão dedicado; a rodada 5 não encontrou achados adicionais"
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "PR #192 ainda não mesclada — rodada 5 de correção (gate eh_dono()) enviada e @codex review pedido de novo; resposta ainda não confirmada; merge continua manual, do André"
  - "PolicyRequest.orcamento_restante existe no contrato e é citado em comentário referenciando 'mandato e orçamento válidos' (seção 5.1), mas não é lido em nenhum ponto de mandato_cobre() nem de avaliar() — checagem de orçamento não implementada"
  - "Mandato.classes_conteudo_permitidas ainda é texto livre (tupla de strings), sem enum fechado — a seção 5.3 do plano pede que 'tipos outro e rótulos livres não possam habilitar envio autônomo', mas a validação de quais strings são aceitáveis ainda não existe"
  - "Mandato.usos_na_janela_atual ainda não tem wrapper de I/O real que resolva a contagem a partir de Firestore/histórico — só o campo e a checagem fail-closed existem; quem monta o Mandato ainda precisa preencher isso manualmente"
  - "NENHUM canal (mcp_server.py, tool_context.py, web, Telegram, voz) consulta autonomy.policy ainda — é o objeto da sub-entrega 2/N"
  - "Decisão de design a levar ao André quando o PACOTE P02 inteiro estiver completo (não antes, conforme seu pedido de só ser notificado ao fim do pacote): o gate de origem_humana nos defaults da matriz PREPARACAO_INTERNA/ESCRITA_INTERNA_REVERSIVEL (rodada 3), agora reforçado pela rodada 5 (exige também eh_dono(), não só a flag booleana) — a pergunta de fundo que ainda vale levantar é se origem_humana deveria mesmo ter default True no contrato, e como canais futuros devem defini-lo explicitamente; se tiver dúvida ou proposta melhor, ele pediu para ser avisado"
  - "Ao religar Principal de verdade na sub-entrega 2/N, cuidado deliberado necessário: Principal.origem_humana tem default True no contrato — qualquer construção de Principal para ator sem humano presente (rotina_cowork, runner_servico) precisa passar origem_humana=False explicitamente, nunca depender do default"
proximo_pacote: "P02 (sub-entrega 2/N — preflight em tool_context.py/mcp_server.py)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 8b845dd4bbd53e6495d7ab9ba1892056ce4a033f
pacote: P02 (sub-entrega 2/N — preflight real em mcp_server.py)
# Continuação de P02 (pacote "G", seção 8 do plano). Sub-entrega 1/N introduziu
# functions/autonomy/{contracts,policy}.py como módulo puro, ainda não
# consultado por nenhum canal. Esta sub-entrega religa o canal MCP
# (functions/mcp_server.py) para consultar autonomy.policy.avaliar() como
# preflight real antes de criar a prévia de confirmação dos 5 tools do piso —
# cobre o passo 6 do plano ("inserir preflight obrigatório no executor de
# domínio") só para o canal MCP, e só para o piso hardcoded, não para chamadas
# internas de módulo nem para os demais canais (web/Telegram/voz). Note-se que
# o plano nomeia functions/tools/tool_context.py entre os arquivos de P02;
# nesta sub-entrega ele foi lido mas não precisou de alteração — o Principal do
# canal MCP é montado inteiramente a partir de campos que ToolContext já tinha
# (user_uid, canal), sem precisar de campo novo.
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T14:50:00Z"
fim: "2026-09-07T16:07:00Z"
arquivos_alterados:
  - functions/mcp_server.py
  - functions/test_mcp_server.py (novo)
  - functions/test_hermes_tools.py
  - functions/test_policy.py
decisoes:
  - id: p02-sub2-fonte-unica-floor
    motivo: "_CONFIRMACAO_OBRIGATORIA em mcp_server.py deixa de ser um `set[str]` literal duplicado e vira um alias direto de autonomy_policy.FLOOR_CONFIRMACAO_OBRIGATORIA (frozenset). Antes, test_policy.py::test_floor_identico_ao_mcp_server existia só para travar as duas constantes na mesma coisa manualmente; agora esse teste é redundante com o próprio Python, mas foi mantido como trava de regressão (se alguém reintroduzir um set literal, o teste volta a pegar a divergência)."
    autoridade: existente_ou_nova
  - id: p02-sub2-principal-mcp-cliente-assistido
    motivo: "_principal_mcp(ctx) constrói o Principal do canal MCP como TipoPrincipal.CLIENTE_ASSISTIDO (não DONO_INTERATIVO, que pressupõe clique de UI por chamada; não ROTINA_COWORK/RUNNER_SERVICO, que pressupõem ausência de sessão). O servidor MCP é de acesso único (_is_uid_allowed restringe a autenticação a um só uid dono — sem uid configurado, acesso negado por padrão), então toda chamada que chega ao preflight já veio de um cliente MCP hospedado com o dono acompanhando a sessão em tempo real. origem_humana=True é passado explicitamente (nunca herdado do default do dataclass) — documenta a decisão em vez de deixá-la implícita, seguindo a pendência já registrada no bloco da sub-entrega 1/N sobre cuidado ao religar Principal de verdade."
    autoridade: existente_ou_nova