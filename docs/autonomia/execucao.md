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
  - id: p02-sub2-decisao-piso-mcp-fail-closed-em-ctx-db
    motivo: "_decisao_piso_mcp(ctx, nome, argumentos) chama autonomy_policy.estado_autonomia_atual(ctx.db) e autonomy_policy.registrar_decisao(ctx.db, ...). Cada uma dessas chamadas tem try/except PRÓPRIO em volta (não confiando só no try/except interno das duas funções de policy.py), porque ctx.db é uma property lazy que inicializa firestore.client() sob demanda e é avaliada como ARGUMENTO da chamada — ou seja, ANTES de entrar no corpo de estado_autonomia_atual/registrar_decisao, fora do try/except que existe dentro delas. Sem essa camada extra, uma falha na própria inicialização do Firestore (não só uma falha de leitura do documento) propagaria e derrubaria a chamada MCP inteira com um erro interno opaco (-32000), em vez do tratamento gracioso que o resto do arquivo já dá a falha de Firestore. Falha em resolver estado cai em SOMENTE_PREPARACAO (fail closed); falha em registrar a decisão só loga e segue (auditoria nunca derruba a chamada)."
    autoridade: existente_ou_nova
  - id: p02-sub2-achado-adversarial-bypass-confirmed-true-sem-hook
    motivo: "ACHADO DE SEGURANÇA da revisão adversarial desta sub-entrega, pré-existente no código (não introduzido por esta sub-entrega, mas dentro do escopo que ela deveria fechar): em _handle_tools_call, o ramo `if _exige_confirmacao(name) and confirmed is True:` sem confirmation_id caía em `if preview_tool(name, ctx, arguments) is not None: bloqueia` — e tools/hermes_tools.py::preview() só implementa hook para pausar_conversa e schedule_whatsapp_message, devolvendo None para as outras três do piso (criar_rascunho_email, registrar_aporte_investimento, registrar_execucao_investimento). Ou seja, uma ÚNICA chamada tools/call com _confirmed=true e SEM _confirmation_id executava essas três tools DIRETO — sem nunca criar uma confirmação real, sem nunca passar por _decisao_piso_mcp (só chamado no ramo de CRIAÇÃO de confirmação, no elif irmão), e sem o 'sim' explícito que o comentário de _CONFIRMACAO_OBRIGATORIA promete ser inegociável para o piso. As duas tools de investimento não têm desfazer nenhum — é o mesmo tipo de efeito que a decisão p01-a04 (sub-entrega anterior) tratou como crítico em outro contexto. CORRIGIDO: bloco novo, restrito ao piso hardcoded (autonomy_policy.FLOOR_CONFIRMACAO_OBRIGATORIA), que recusa esse atalho ANTES mesmo de checar o hook de prévia, sempre exigindo confirmation_id de uma confirmação real e persistida. Tools de confirmação obrigatória só por config (fora do piso, via system/mcp_access.confirm_tools) mantêm a compatibilidade legada de sempre, sem mudança — o fechamento foi deliberadamente restrito ao piso, não ampliado por analogia."
    autoridade: existente_ou_nova
  - id: p02-sub2-fix-firebase-app-nao-inicializado-em-teste
    motivo: "A primeira versão de _decisao_piso_mcp (antes do try/except descrito acima) derrubava 3 testes pré-existentes de test_hermes_tools.py (TestCamadaJsonRpc::test_destinatario_desconhecido_nao_cria_confirmacao, test_gate_inclui_preview_quando_a_tool_oferece_hook, test_gating_do_canal_barra_antes_de_executar) com 'The default Firebase app does not exist.' — esses testes mockavam _criar_confirmacao/preview_tool mas nunca precisavam de um app Firebase real até o preflight passar a existir. Diagnosticado com um script de reprodução isolado: mesmo com estado_autonomia_atual mockada, ctx.db (o argumento) já tentava firestore.client() de verdade antes da função mockada ser chamada. Corrigido em duas camadas: (1) o try/except em ctx.db descrito na decisão acima; (2) o helper _gating() de test_hermes_tools.py passou a mockar também firebase_admin.firestore.client (retornando um MagicMock) e autonomy_policy.registrar_decisao, além de estado_autonomia_atual (fixada em ATIVO, o estado real de produção hoje, já que system/autonomy_state ainda não é escrito por nada)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_policy test_contracts test_mcp_server test_hermes_tools test_mcp_oauth -v"
  resultados:
    - "Python (unittest, suíte completa): 1261/1261 passando (99 da sub-entrega 1/N + 16 testes novos de test_mcp_server.py + 3 testes pré-existentes de test_hermes_tools.py corrigidos pelo fix de Firebase app; 0 regressões)"
    - "test_mcp_server.py (arquivo novo — mcp_server.py não tinha nenhum teste próprio antes desta sub-entrega): 16/16 (_principal_mcp, _decisao_piso_mcp para os 4 estados de autonomia, mapeamento DENY/PREPARE_ONLY/ALLOW em _handle_tools_call, e 6 testes de regressão do achado de segurança provando ponta a ponta contra o dispatch real que as 3 tools do piso sem hook NUNCA executam sem confirmation_id)"
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação): encontrou o achado de bypass do _confirmed=true sem hook (único achado real) — verificado por inspeção direta do código real, não aceito às cegas. Fix aplicado e a MESMA revisão re-verificou com uma bateria mais agressiva de tentativas de exploit (21 checagens adicionais, todas passaram) mais um traço ponta a ponta do fluxo legítimo (criar→confirmar→executar→replay) contra um Firestore falso mínimo, confirmando fechamento do bypass e preservação do comportamento legítimo/anti-adulteração."
  - "PR #192 (https://github.com/andre-martiini/Hermes/pull/192) — mesma PR aberta desde a sub-entrega 1/N (branch claude/p02-autonomy-policy-contracts); commits desta sub-entrega adicionados ao mesmo branch. @codex review pedido novamente ao final desta sub-entrega."
  - "Polling do @codex review desta sub-entrega (comentário #5573256853, ~16:11 UTC): tentativa de verificação via GitHub REST API falhou nesta sessão com 'GitHub access to this repository is not enabled for this session' (mecanismo de gate que exige uma ferramenta add_repo indisponível neste ambiente — achado técnico novo, não presente em sessões anteriores). Tentativa alternativa via WebFetch na URL da PR trouxe conteúdo desatualizado/cacheado (o comentário mais recente retornado datava de 14:53:55 UTC, ANTERIOR ao próprio comentário #5573256853 desta sub-entrega — inclusive reapresentou o achado antigo de origem_humana das rodadas 3/5, já registrado como pendência acima, o que confirma que não era resposta nova). Sem via confiável de leitura automatizada disponível e com mais de 5 minutos decorridos sem confirmação, a rodada foi tratada como exaurida por esta sessão, sem aceitar nem rejeitar nenhum achado novo às cegas. Se o Codex responder mais tarde (assincronamente), a resposta será revisada quando lida — por leitura direta do André ou por uma via de leitura automatizada que venha a funcionar — antes de qualquer fechamento definitivo desta sub-entrega."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Recomendação explícita da revisão adversarial desta sub-entrega, registrada e não escondida: o mesmo tipo de gap (tool de confirmação obrigatória sem hook de prévia executando via _confirmed=true sem confirmation_id) ainda é teoricamente possível para uma tool adicionada só por config (system/mcp_access.confirm_tools), fora do piso hardcoded — o fechamento desta sub-entrega foi deliberadamente restrito ao piso. Hoje não há tool nesse estado em produção (nenhuma tool configurável sem hook foi identificada), mas é uma lacuna de design que vale endereçar quando o passo 7 do plano (tools consultar/simular/preparar_politica) ou uma futura sub-entrega tratar de tools configuráveis via política."
  - "P02 segue MATERIALMENTE em aberto — auditoria contra o texto verbatim do plano (passos 1-9, seção 'Unificar identidade e política de autonomia') mostra que sub-entregas 1/N e 2/N cobrem só o passo 9 (registrar decisões), o passo 6 (preflight obrigatório) parcialmente — só canal MCP, só piso hardcoded, chamadas internas de módulo NÃO passam pela política ainda —, o passo 5 (preservar as 5 confirmações), e metade do passo 4 (modelar políticas/decisões; falta 'importar configuração existente e apresentar diferenças antes de ativar permissões novas'). Passos claramente NÃO endereçados ainda: passo 1 (taxonomia completa de principals span todos os canais — só o canal MCP tem _principal_mcp; tools/tool_context.py, mcp_oauth.py, web, Telegram e voz seguem sem o modelo de identidade unificado), passo 2 (evolução de claims/scopes OAuth com validação de issuer/audience/subject/expiração/cliente), passo 3 (vínculo autenticado executor→capacidades), passo 7 (as 3 tools MCP consultar_politica/simular_politica/preparar_politica — as funções PURAS já existem em policy.py com testes, mas não são expostas como tools MCP; candidata natural para a sub-entrega 3/N por ser a de menor risco/maior reaproveitamento), passo 8 (revalidar versão, revogação, escopo E ORÇAMENTO no despacho — orcamento_restante existe no contrato mas não é lido em lugar nenhum)."
  - "Decisão de design a levar ao André quando o PACOTE P02 inteiro estiver completo (não antes — mantido da sub-entrega 1/N, ainda não é hora): o gate de origem_humana nos defaults da matriz PREPARACAO_INTERNA/ESCRITA_INTERNA_REVERSIVEL, reforçado pelas rodadas 3 e 5 do Codex (exige também eh_dono()) — a pergunta de fundo ainda vale: origem_humana deveria mesmo ter default True no contrato? Esta sub-entrega reforça a resposta prática (o único canal religado até agora, _principal_mcp, passa origem_humana=True explicitamente e é sempre eh_dono()==True), mas não fecha a pergunta de design para canais futuros que ainda vão precisar decidir isso por conta própria (rotina_cowork, runner_servico)."
  - "Todas as pendências já registradas no bloco da sub-entrega 1/N que não foram tocadas nesta sub-entrega continuam abertas: orcamento_restante não lido, Mandato.classes_conteudo_permitidas ainda é texto livre sem enum fechado, Mandato.usos_na_janela_atual sem wrapper de I/O real, canais além de MCP (web/Telegram/voz) não consultam autonomy.policy."
proximo_pacote: "P02 (sub-entrega 3/N — candidata: passo 7 do plano, expor consultar_politica/simular_politica/preparar_politica de autonomy/policy.py como tools MCP, reaproveitando as funções puras já existentes e testadas)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 0e332f0c7aaacba09927ba0eccf37e743fcd28c0
pacote: "P02 (sub-entrega 3/N — tools MCP de política: consultar/simular/preparar)"
# Continuação de P02 (pacote "G", seção 8 do plano). Cobre o passo 7
# ("expor consultar_politica/simular_politica/preparar_politica como tools
# MCP"), a candidata de menor risco identificada no bloco da sub-entrega 2/N:
# as três funções já existiam PURAS e testadas em autonomy/policy.py desde a
# sub-entrega 1/N (test_policy.py), sem nenhum canal expô-las. Esta
# sub-entrega adiciona só wrappers finos em tools/hermes_tools.py (parsing de
# args, validação de forma, tradução de erro para a convenção ERRO| do
# arquivo) — nenhuma lógica de decisão nova, o motor de autonomy/policy.py
# não foi alterado.
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T16:20:00Z"
fim: "2026-09-07T17:05:00Z"
arquivos_alterados:
  - functions/tools/registry.py
  - functions/tools/hermes_tools.py
  - functions/tools/schemas/consultar_politica.json (novo)
  - functions/tools/schemas/simular_politica.json (novo)
  - functions/tools/schemas/preparar_politica.json (novo)
  - functions/test_hermes_tools.py
  - functions/test_mcp_server.py
  - docs/autonomia/execucao.md
decisoes:
  - id: p02-sub3-wrappers-finos-sobre-motor-puro
    motivo: "consultar_politica/simular_politica/preparar_politica em tools/hermes_tools.py são wrappers finos: consultar e simular são leitura pura (nenhum toca ctx.db — provado em test_nenhum_toca_firestore_sem_precisar), preparar só calcula um diff e nunca persiste (mesmo contrato já documentado na docstring de autonomy.policy.preparar_politica desde a sub-entrega 1/N). simular_politica constrói um Principal/PolicyRequest HIPOTÉTICO inteiramente a partir do que o chamador declarou no pedido — diferente de mcp_server._principal_mcp (sub-entrega 2/N), que reflete o principal REAL do canal autenticado — porque o propósito da tool é justamente explorar cenários de outros tipos de principal (rotina_cowork, runner_servico, ...), não só o do canal MCP atual."
    autoridade: existente_ou_nova
  - id: p02-sub3-achado-adversarial-bool-coercao-origem-humana
    motivo: "Achado real da revisão adversarial, verificado por reprodução direta antes de aceitar: bool(\"false\") é True em Python (truthiness de string não vazia, não parsing de JSON) — um pedido de simular_politica com origem_humana=\"false\" (erro plausível de um cliente MCP montando o JSON à mão, já que o schema declara boolean mas nada impede o cliente de mandar string) inverteria SILENCIOSAMENTE o resultado da simulação: reproduzido com origem_humana=\"false\" (string) => decision=allow, e o mesmo pedido com origem_humana=False (bool) => decision=prepare_only. É o oposto exato do que a tool existe para evitar (mostrar o efeito real de um cenário antes de propô-lo de verdade). Corrigido em _principal_simulado: origem_humana que não é None nem bool levanta ValueError explícito em vez de ser coagido por bool(...)."
    autoridade: existente_ou_nova
  - id: p02-sub3-achado-adversarial-string-iterada-como-lista
    motivo: "Achado real da revisão adversarial: autonomy.policy.preparar_politica() faz set(politica_proposta.get(\"ferramentas_com_confirmacao_obrigatoria\", atual)) sem checar o tipo — uma STRING passada em vez de lista (erro plausível: \"ferramentas_com_confirmacao_obrigatoria\": \"pausar_conversa\" em vez de [...]) é iterada caractere por caractere pelo set(), e o diff resultante (\"remover as 5 tools reais do piso, adicionar um bando de letras soltas\") sai como se fosse válido — exatamente no único tool cujo propósito é proteger o piso de confirmação obrigatória de uma mudança não revisada. A função pura em si NÃO foi alterada (fora do escopo desta sub-entrega mexer no motor — ver pendências abaixo); a validação de forma (lista de strings) foi adicionada em _preparar_politica, ANTES de chamar o motor puro, então o bug de tipo do motor continua latente mas inalcançável por este caminho de entrada."
    autoridade: existente_ou_nova
  - id: p02-sub3-achado-adversarial-iserror-nao-marcado
    motivo: "Achado real da revisão adversarial, o mais sério dos quatro por afetar o SINAL do protocolo, não só o conteúdo: tanto o lote inválido de simular_politica quanto a base_version desatualizada de preparar_politica (a salvaguarda central da tool, o que impede sobrescrever uma proposta concorrente não vista) retornavam um json.dumps(...) — uma STRING contendo uma chave \"erro\" dentro — mas mcp_server._handle_tools_call só deriva isError=True de um dict com .get(\"erro\"), ou de uma string com o prefixo ERRO| (via _looks_like_error). Uma string JSON com \"erro\" dentro não bate em nenhum dos dois mecanismos: o payload virava uma resposta \"bem-sucedida\" do ponto de vista do protocolo MCP, para uma chamada que na prática não fez o que foi pedido. Corrigido prefixando ambas as respostas com ERRO| (mantendo o payload estruturado, ex. pedidos_invalidos, depois do prefixo). Testado em dois níveis: no wrapper (test_hermes_tools.py, checando o prefixo na string) e no dispatch real (test_mcp_server.py::TestFerramentasDePoliticaViaMcp, checando isError em _handle_tools_call — o ponto onde um cliente MCP de verdade observaria a diferença, por recomendação explícita do próprio revisor)."
    autoridade: existente_ou_nova
  - id: p02-sub3-achado-adversarial-typeerror-argumentos-resolvidos
    motivo: "Achado real da revisão adversarial: argumentos_resolvidos (campo livre do pedido de simular_politica, usado só para registro/hash, não validado) quando não-mapeável (ex.: um inteiro) fazia dict(argumentos_resolvidos) levantar TypeError — não capturado pelo except (ValueError, KeyError) original do laço que processa cada pedido do lote, escapando cru até hermes_tools.execute() em vez de virar um erro por índice como os demais campos inválidos do mesmo pedido. Corrigido com checagem de isinstance(..., dict) explícita em _policy_request_simulado, mais TypeError adicionado ao except do laço como defesa em profundidade."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_policy test_contracts test_mcp_server test_hermes_tools test_mcp_oauth -v"
  resultados:
    - "Python (unittest, suíte completa): 1280/1280 passando (1261 anteriores da sub-entrega 2/N + 19 testes novos: 15 em TestFerramentasDePolitica — test_hermes_tools.py — e 4 em TestFerramentasDePoliticaViaMcp — test_mcp_server.py, contagem conferida por AST, não de memória; 0 regressões)"
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação, instruído a rodar a suíte real e reproduzir achados com execução de código, não só inspeção): encontrou os 4 achados reais listados acima, todos verificados contra o conteúdo real dos arquivos antes de aceitar (achado #1 reproduzido com origem_humana=\"false\" vs False produzindo decisões diferentes para o mesmo pedido)."
  - "PR #192 (https://github.com/andre-martiini/Hermes/pull/192) — mesma PR aberta desde a sub-entrega 1/N (branch claude/p02-autonomy-policy-contracts); commits desta sub-entrega adicionados ao mesmo branch. Comentário https://github.com/andre-martiini/Hermes/pull/192#issuecomment-5573743251 documenta esta sub-entrega (os 4 achados, arquivos alterados, contagem de testes); @codex review pedido novamente ao final."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "O bug de tipo em autonomy/policy.py::preparar_politica (set() iterando string caractere por caractere quando ferramentas_com_confirmacao_obrigatoria não é lista — achado adversarial #2 acima) foi CONTORNADO na wrapper (_preparar_politica valida a forma antes de chamar o motor), NÃO corrigido na função pura — o motor em si continua aceitando o mesmo input malformado se chamado diretamente (ex.: de um teste, ou de um futuro segundo chamador que não passe pela wrapper). Corrigir a função pura fica para quando autonomy/policy.py for revisitado por outro motivo, para não misturar escopo."
  - "P02 segue MATERIALMENTE em aberto — dos passos 1-9 do plano (seção 'Unificar identidade e política de autonomia'), esta sub-entrega fecha o passo 7. Ainda não endereçados: passo 1 (taxonomia completa de principals span todos os canais — só o canal MCP tem _principal_mcp desde a sub-entrega 2/N; tools/tool_context.py, mcp_oauth.py, web, Telegram e voz seguem sem o modelo de identidade unificado), passo 2 (evolução de claims/scopes OAuth com validação de issuer/audience/subject/expiração/cliente), passo 3 (vínculo autenticado executor→capacidades), passo 8 (revalidar versão, revogação, escopo E ORÇAMENTO no despacho — orcamento_restante existe no contrato desde a sub-entrega 1/N mas não é lido em lugar nenhum, nem pelas tools novas desta sub-entrega — simular_politica aceita orcamento_restante no pedido só para repassar ao motor, que já o ignora)."
  - "Decisão de design a levar ao André quando o PACOTE P02 inteiro estiver completo (não antes — mantido das sub-entregas 1/N e 2/N, ainda não é hora): o gate de origem_humana nos defaults da matriz PREPARACAO_INTERNA/ESCRITA_INTERNA_REVERSIVEL (rodadas 3 e 5 do Codex, exige também eh_dono()) — a pergunta de fundo ainda vale: origem_humana deveria mesmo ter default True no contrato? Esta sub-entrega não muda essa resposta (simular_politica expõe o campo para o CHAMADOR declarar explicitamente por tipo de principal simulado, mas não altera o default do dataclass Principal em si)."
  - "Todas as pendências já registradas nos blocos das sub-entregas 1/N e 2/N que não foram tocadas nesta sub-entrega continuam abertas: Mandato.classes_conteudo_permitidas ainda é texto livre sem enum fechado, Mandato.usos_na_janela_atual sem wrapper de I/O real, canais além de MCP (web/Telegram/voz) não consultam autonomy.policy, o mesmo padrão de gap de confirmação sem hook para tools configuráveis só por system/mcp_access.confirm_tools (fora do piso hardcoded) segue teoricamente possível."
proximo_pacote: "P02 (sub-entrega 4/N — candidata a decidir: passo 1, taxonomia de principals nos demais canais, ou passo 8, leitura de orcamento_restante no despacho)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 5621eb5a6b1f7de36b4c331ffbca1fd148f61b33
pacote: "P02 (sub-entrega 4/N — orçamento no mandato, passo 8 do plano, parcial)"
# Antes de iniciar: a rodada de review do @codex sobre a sub-entrega 3/N
# (comentário https://github.com/andre-martiini/Hermes/pull/192#issuecomment-5573743251,
# postado ~17:09 UTC) foi tratada como exaurida sem resposta confirmável —
# GitHub REST API continuou bloqueada ("GitHub access to this repository is
# not enabled for this session"), e um WebFetch fresco em
# https://github.com/andre-martiini/Hermes/pull/192 (17:14 UTC, mais de 5min
# depois do comentário) ainda retornou conteúdo desatualizado (comentário de
# 14:53:55 UTC, sem nada após 17:09 UTC) — mesma limitação de cache já
# documentada nas sub-entregas anteriores. Seguiu-se para esta sub-entrega
# sem esperar 5 horas (regra de espera é entre PACOTES, não entre
# sub-entregas do mesmo pacote).
#
# Escopo: fecha o passo 8 do plano ("revalidar versão, revogação, escopo e
# orçamento no despacho") NA DIMENSÃO ORÇAMENTO apenas — versão (base_version
# em preparar_politica), revogação (Mandato.revogado) e escopo
# (destinatarios_recursos/classes_conteudo_permitidas) já eram revalidados a
# cada chamada de mandato_cobre()/avaliar() desde a sub-entrega 1/N (função
# pura, sem cache — cada chamada resolve tudo de novo). O que faltava,
# documentado explicitamente como pendência desde a sub-entrega 1/N (achado
# da revisão adversarial da 4ª rodada do Codex, PR #191), era orçamento:
# PolicyRequest.orcamento_restante existia no contrato mas não era lido em
# lugar nenhum de autonomy/policy.py. Escopo deliberadamente pequeno: só o
# motor puro (Mandato.orcamento_maximo + checagem em mandato_cobre()) —
# mandatos persistidos continuam sem nenhuma fonte real (sub-entrega futura),
# então este fix não é alcançável hoje por nenhum canal MCP, mesma situação
# em que limite_por_janela esteve até ser fechado.
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T17:17:00Z"
fim: "2026-09-07T17:35:00Z"
arquivos_alterados:
  - functions/autonomy/contracts.py
  - functions/autonomy/policy.py
  - functions/test_policy.py
  - functions/test_contracts.py
  - docs/autonomia/execucao.md
decisoes:
  - id: p02-sub4-orcamento-maximo-opt-in-por-mandato
    motivo: "Mandato.orcamento_maximo é opcional (default None) e opt-in: um mandato só precisa declarar teto quando a finalidade tem dimensão financeira de verdade (ex.: 'consumir até o teto aprovado', seção 5.3 do plano) — mandatos puramente não-financeiros (ex.: 'cobrar confirmação de recebimento') não são afetados pela checagem nova. Mesma divisão de responsabilidade já usada para limite_por_janela/usos_na_janela_atual: o tipo só declara o teto, um wrapper com I/O ainda não implementado resolve o saldo real (consumo até agora vs. teto) e preenche PolicyRequest.orcamento_restante antes de incluir o mandato em mandatos_aplicaveis."
    autoridade: existente_ou_nova
  - id: p02-sub4-achado-adversarial-nan-bypassa-fail-closed
    motivo: "Achado real da revisão adversarial, verificado por reprodução direta antes de aceitar: a primeira versão da checagem usava 'if request.orcamento_restante <= 0: return False'. float('nan') faz TODA comparação (<=, <, >, >=, ==) retornar False em Python — então nan <= 0 é False, e nan is None também é False, então um saldo NaN não caía em nenhum dos dois `return False` e passava como se fosse um saldo positivo válido, exatamente o oposto do fail-closed que a checagem existe para garantir. Corrigido para 'if not (request.orcamento_restante > 0): return False', que rejeita NaN corretamente (nan > 0 já é False, a negação vira True). O revisor confirmou o caminho de entrada real hoje: json.loads aceita o token NaN por padrão (json.loads('{\"x\": NaN}') funciona), e tools/hermes_tools.py:2202 (_principal_simulado) repassa pedido.get('orcamento_restante') para PolicyRequest sem validar tipo — então um pedido de simular_politica via MCP com \"orcamento_restante\": NaN chega em mandato_cobre() sem alteração. Blast radius hoje é limitado (simular_politica é só leitura/simulação, e nenhum canal real popula mandatos_aplicaveis ainda), mas seria um bypass real assim que um wrapper de resolução de orçamento for implementado."
    autoridade: existente_ou_nova
  - id: p02-sub4-achado-adversarial-doc-summary-incompleto
    motivo: "Achado da revisão adversarial, nitpick: a frase-resumo no topo da docstring de mandato_cobre() ('Um mandato cobre um pedido se: não revogado, ainda válido, dentro do limite de uso da janela...') não mencionava orçamento entre as condições, embora a checagem detalhada estivesse descrita um parágrafo abaixo — corrigido, orçamento agora tem seu próprio parágrafo logo após a frase-resumo, referenciando onde o gap foi fechado."
    autoridade: existente_ou_nova
  - id: p02-sub4-achado-adversarial-teste-default-faltando
    motivo: "Achado da revisão adversarial, nitpick: test_contracts.py::TestDefaultsDeContrato testava os defaults de Mandato (revogado, valido_ate, limite_por_janela, usos_na_janela_atual) mas não tinha sido estendido com orcamento_maximo — adicionado self.assertIsNone(m.orcamento_maximo), mesmo padrão dos irmãos."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_policy test_contracts -v"
  resultados:
    - "Python (unittest, suíte completa): 1286/1286 passando (1280 anteriores da sub-entrega 3/N + 6 testes novos em TestMandatoCobre — test_policy.py: saldo desconhecido, esgotado (0.0), negativo, NaN, positivo, sem teto declarado —, contagem conferida por AST, não de memória; 0 regressões). Suíte completa rodada antes E depois da correção do achado NaN, para confirmar que o fix não quebrou nada."
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação, instruído a ler o código real, rodar a suíte de verdade e reproduzir achados por execução, não só inspeção): encontrou os 4 achados listados acima (1 bug real, 1 gap de validação de tipo pré-existente registrado como pendência, 2 nitpicks de documentação/teste), todos verificados manualmente contra o código atual antes de aceitar (achado NaN reproduzido diretamente: nan <= 0 e nan is None ambos False)."
  - "PR #192 (https://github.com/andre-martiini/Hermes/pull/192) — mesma PR aberta desde a sub-entrega 1/N (branch claude/p02-autonomy-policy-contracts); commits desta sub-entrega adicionados ao mesmo branch. Comentário https://github.com/andre-martiini/Hermes/pull/192#issuecomment-5574002387 documenta esta sub-entrega (achados, arquivos alterados, contagem de testes); @codex review pedido novamente ao final."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Validação de tipo de PolicyRequest.orcamento_restante no wrapper MCP (tools/hermes_tools.py:2202, _principal_simulado) não foi adicionada nesta sub-entrega — mesma folga que missao/sensibilidade já têm hoje (não é regressão desta sub-entrega, é um gap pré-existente que esta sub-entrega apenas tornou operacionalmente relevante pela primeira vez). Um valor não numérico levanta TypeError, capturado pelo except Exception amplo ao redor de simular_politica (degrada para mensagem de erro, não crash) — mas não impede um NaN especificamente (numérico, sem levantar exceção) de escapar até mandato_cobre(), onde a checagem desta sub-entrega agora trata corretamente. Corrigir a validação de tipo no wrapper fica para quando hermes_tools.py for revisitado por outro motivo, mesmo raciocínio de escopo já aplicado ao bug de tipo em preparar_politica na sub-entrega 3/N."
  - "P02 segue MATERIALMENTE em aberto — dos passos 1-9 do plano (seção 'Unificar identidade e política de autonomia'), esta sub-entrega fecha a dimensão orçamento do passo 8. Ainda não endereçados: passo 1 (taxonomia completa de principals span todos os canais — só o canal MCP tem _principal_mcp desde a sub-entrega 2/N; tools/tool_context.py, mcp_oauth.py, web, Telegram e voz seguem sem o modelo de identidade unificado), passo 2 (evolução de claims/scopes OAuth), passo 3 (vínculo autenticado executor→capacidades), passo 8 nas outras três dimensões — versão/revogação/escopo já são revalidados a cada chamada da função pura (sem cache), mas isso só importa de verdade quando houver um canal real chamando avaliar()/mandato_cobre() fora de teste, o que ainda não existe."
  - "Decisão de design a levar ao André quando o PACOTE P02 inteiro estiver completo (não antes — mantido das sub-entregas 1/N, 2/N e 3/N, ainda não é hora): o gate de origem_humana nos defaults da matriz PREPARACAO_INTERNA/ESCRITA_INTERNA_REVERSIVEL (rodadas 3 e 5 do Codex, exige também eh_dono()) — a pergunta de fundo ainda vale: origem_humana deveria mesmo ter default True no contrato? Esta sub-entrega não toca nisso."
  - "Todas as pendências já registradas nos blocos das sub-entregas 1/N, 2/N e 3/N que não foram tocadas nesta sub-entrega continuam abertas: Mandato.classes_conteudo_permitidas ainda é texto livre sem enum fechado, Mandato.usos_na_janela_atual sem wrapper de I/O real (mesma situação agora de Mandato.orcamento_maximo — declarado mas sem nada que resolva o saldo real), canais além de MCP (web/Telegram/voz) não consultam autonomy.policy, o bug de tipo em autonomy/policy.py::preparar_politica (contornado na wrapper, não corrigido no motor) segue latente."
proximo_pacote: "P02 (sub-entrega 5/N — candidata a decidir: passo 1, taxonomia de principals nos demais canais, ou seguir fechando o passo 8 nas outras dimensões quando houver um canal real consumindo avaliar())"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 5621eb5a6b1f7de36b4c331ffbca1fd148f61b33
pacote: "P02 (sub-entrega 5/N — principal_de() compartilhado, passo 1 do plano, parcial)"
# Antes de iniciar: a rodada de review do @codex sobre a sub-entrega 4/N
# (comentário https://github.com/andre-martiini/Hermes/pull/192#issuecomment-5574002387,
# postado ~17:38-17:40 UTC) foi tratada como exaurida sem resposta
# confirmável após DUAS checagens (17:44 e 17:49 UTC) — GitHub REST API
# continuou bloqueada ("GitHub access to this repository is not enabled
# for this session"), e a segunda checagem por WebFetch retornou
# timestamps no FUTURO (eventos às 17:53/17:56 UTC quando a própria
# checagem era às 17:49 UTC) — sinal inequívoco de que o conteúdo não é
# confiável (cache desatualizado misdatado, ou extração garantida errada
# pelo modelo pequeno do WebFetch), descartado sem virar achado. Seguiu-se
# para esta sub-entrega sem esperar 5 horas (regra de espera é entre
# PACOTES, não entre sub-entregas do mesmo pacote).
#
# Escopo: avança o passo 1 do plano ("definir principals distintos... span
# todos os canais") sem tentar religar nenhum canal novo de uma vez — algo
# que exigiria decidir o TipoPrincipal correto de Telegram,
# outbox_aprovacao.py, revisao_semanal.py e mcp_jobs.py, cada um com
# ambiguidades genuínas não investigadas a fundo ainda. Em vez disso,
# extraída para tools/tool_context.py::principal_de() a lógica que já
# existia hardcoded em mcp_server.py::_principal_mcp (uid/canal ->
# Principal, default de origem_humana por tipo) — puramente aditivo/
# refactor, sem mudança de comportamento no único canal já religado (MCP),
# preparando o terreno para os canais futuros sem decidir por eles agora.
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T17:49:00Z"
fim: "2026-09-07T18:08:00Z"
arquivos_alterados:
  - functions/tools/tool_context.py
  - functions/mcp_server.py
  - functions/test_tool_context.py (novo)
  - functions/atencao.py
  - functions/test_atencao.py
decisoes:
  - id: p02-sub5-principal-de-tipo-sempre-explicito
    motivo: "principal_de(ctx, tipo, *, origem_humana=None) exige tipo como argumento explícito do CHAMADOR, nunca inferido de ctx.canal sozinho. Achado que motivou essa escolha de design: canal=\"mcp\" é usado tanto por mcp_server.py (cliente MCP hospedado, dono acompanhando em tempo real -> CLIENTE_ASSISTIDO) quanto por mcp_jobs.py::on_mcp_job_created (job assíncrono de Firestore continuando uma tool longa depois que o request HTTP original já terminou, sem garantia de que o dono ainda está olhando) -- um resolvedor por texto de canal teria classificado os dois da mesma forma, escondendo exatamente a distinção que TipoPrincipal existe para preservar. mcp_jobs.py hoje não constrói Principal nenhum (não foi religado nesta sub-entrega) -- o achado é preventivo, documentado na docstring da função para quem for religar esse canal depois."
    autoridade: existente_ou_nova
  - id: p02-sub5-principal-mcp-delega-sem-mudar-comportamento
    motivo: "mcp_server.py::_principal_mcp passa a delegar para principal_de(ctx, TipoPrincipal.CLIENTE_ASSISTIDO, origem_humana=True) -- mesmo nome, mesma assinatura, mesma docstring (com um parágrafo novo explicando a delegação). test_mcp_server.py::TestPrincipalMcp, já existente e não alterado nesta sub-entrega, prova que o resultado não mudou. Verificado pela revisão adversarial rodando a suíte real, não só lendo o código."
    autoridade: existente_ou_nova
  - id: p02-sub5-achado-incidental-toolcontext-db-errado-em-atencao
    motivo: "Achado incidental da revisão adversarial (fora do diff revisado, encontrado ao rastrear futuros call sites de principal_de): atencao.py::resolver_item, chamado sem ctx explícito (o caso comum) e com acao_id preenchido, construía ToolContext(db=db, ...) -- campo errado, o dataclass usa _db (db só existe como property de leitura). ToolContext(db=db, ...) levantava TypeError ANTES de chamar registrar_no_diario, engolido em silêncio pelo except Exception ao redor -- todo desfecho resolvido com acao_id preenchido, chamado sem ctx explícito, perdia a nota no diário da ação sem nenhum sinal de erro. Reproduzido diretamente antes de aceitar (ToolContext(db=object()) -> TypeError). Corrigido para _db=db, com teste de regressão que falhava antes do fix (test_resolver_item_com_acao_id_registra_no_diario). Pré-existente, não introduzido por esta sub-entrega; consertado por ser pequeno, bem entendido e diretamente relevante ao escopo (mesmo arquivo citado como futuro call site de principal_de)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_tool_context test_mcp_server test_atencao -v"
  resultados:
    - "Python (unittest, suíte completa): 1296/1296 passando (1286 anteriores da sub-entrega 4/N + 9 testes novos em test_tool_context.py -- default de origem_humana por tipo para os 5 TipoPrincipal, override explícito, passthrough de uid/canal -- + 1 teste de regressão em test_atencao.py; contagem conferida por AST, não de memória; 0 regressões)."
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação, instruído a ler o diff real, rodar a suíte de verdade e verificar cada claim por execução, não só inspeção): nenhum defeito encontrado no diff revisado -- confirmou a lógica de principal_de correta (incluindo o caso origem_humana=False explícito para DONO_INTERATIVO, provado seguro por leitura de autonomy/policy.py::_decisao_padrao_por_classe -- o override só pode degradar para PREPARE_ONLY/REQUIRE_APPROVAL, nunca conceder ALLOW indevido, porque eh_dono() depende só de tipo), verificou a claim do mcp_jobs.py lendo o arquivo real, checou ausência de ciclo de import (autonomy/contracts.py e autonomy/policy.py não importam nada de tools/, confirmado por execução direta), e confirmou que os 9 testes novos exercitam a função real sem mocks tautológicos. Rodou a suíte completa: 1295/1295 (antes do fix incidental de atencao.py) e 1296/1296 (depois). Achado incidental (fora do diff, ver decisão acima) verificado por reprodução direta antes de ser aceito e corrigido."
  - "PR #192 (https://github.com/andre-martiini/Hermes/pull/192) -- mesma PR aberta desde a sub-entrega 1/N (branch claude/p02-autonomy-policy-contracts); commits desta sub-entrega adicionados ao mesmo branch. Comentário https://github.com/andre-martiini/Hermes/pull/192#issuecomment-5574275337 documenta esta sub-entrega (escopo, achado incidental, contagem de testes); @codex review pedido novamente ao final."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Passo 1 do plano segue MATERIALMENTE em aberto: só o canal MCP constrói Principal e passa pelo preflight de política. Telegram (hermes_core_logic.py, closures de ativar/desativar/consultar modo secretário), outbox_aprovacao.py, revisao_semanal.py e mcp_jobs.py continuam sem construir Principal nenhum. Decidir o TipoPrincipal correto de cada um fica para sub-entrega futura -- alguns são genuinamente ambíguos (ex.: mcp_jobs.py::on_mcp_job_created é sempre RUNNER_SERVICO, ou depende de quanto tempo passou desde o request HTTP original que criou o job?) e podem precisar de input do André em vez de decisão unilateral."
  - "Religar esses canais no preflight de autonomy.policy.avaliar() é o passo 6 do plano, sequenciado ainda mais adiante -- deliberadamente não tentado nesta sub-entrega, mesmo tendo o mecanismo (principal_de) pronto para uso."
  - "P02 segue MATERIALMENTE em aberto nos passos 2 (evolução de claims/scopes OAuth), 3 (vínculo autenticado executor->capacidades), e nas dimensões restantes do passo 8 (só orçamento foi fechado, na sub-entrega 4/N; versão/revogação/escopo já são revalidados a cada chamada da função pura, mas isso só importa de verdade quando um canal real chamar avaliar()/mandato_cobre() fora de teste)."
  - "Decisão de design a levar ao André quando o PACOTE P02 inteiro estiver completo (não antes -- mantido das sub-entregas 1/N a 4/N, ainda não é hora): o gate de origem_humana nos defaults da matriz PREPARACAO_INTERNA/ESCRITA_INTERNA_REVERSIVEL (rodadas 3 e 5 do Codex, exige também eh_dono()) -- a pergunta de fundo ainda vale: origem_humana deveria mesmo ter default True no contrato? Esta sub-entrega não toca nisso."
  - "Todas as pendências já registradas nos blocos das sub-entregas 1/N a 4/N que não foram tocadas nesta sub-entrega continuam abertas: validação de tipo de PolicyRequest.orcamento_restante no wrapper MCP (tools/hermes_tools.py, _principal_simulado), Mandato.classes_conteudo_permitidas ainda texto livre sem enum fechado, Mandato.usos_na_janela_atual e Mandato.orcamento_maximo sem wrapper de I/O real, o bug de tipo em autonomy/policy.py::preparar_politica (contornado na wrapper, não corrigido no motor) segue latente."
proximo_pacote: "P02 (sub-entrega 6/N -- candidata a decidir: continuar o passo 1 decidindo o TipoPrincipal de um canal específico, ou avançar os passos 2/3 do plano quando houver mais clareza sobre OAuth/claims)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 0242516a0560adafa2fc89690ca6219c423b618a
pacote: "P02 (sub-entrega 6/N -- decisao_piso() compartilhado, passo 6 do plano, parcial)"
# NOTA DE PROCESSO: este bloco documenta retroativamente uma sub-entrega cujo
# código já estava no branch (commits 12da7dbae e 426167193) mas cuja entrada
# em execucao.md nunca chegou a ser enviada -- o próprio commit de testes já
# dizia "ver docstring e execucao.md", mas o registro aqui não aconteceu antes
# da sessão ser compactada/interrompida. Escrito agora, na sub-entrega 7/N,
# por leitura direta dos commits e diffs reais (git show), não de memória --
# nenhuma decisão nova é tomada aqui, só o registro que faltou.
#
# Escopo: extrai para autonomy/policy.py::decisao_piso(db, principal, nome,
# argumentos) a lógica que mcp_server.py::_decisao_piso_mcp já tinha desde a
# sub-entrega 2/N (estado_autonomia_atual + PolicyRequest + avaliar +
# registrar_decisao num único ponto), para reuso por qualquer canal futuro --
# passo 6 do plano ("inserir preflight obrigatório no executor de domínio").
# mcp_server.py NÃO foi religado para usar esta função nova (continua com sua
# própria _decisao_piso_mcp, que lida com ctx.db como property lazy que pode
# falhar na própria inicialização -- diferença documentada na docstring da
# função nova). O candidato natural de segundo consumidor real -- fechar
# schedule_whatsapp_message do Telegram (hermes_core_logic.py) com o mesmo
# preflight -- chegou a ser implementado e testado nesta sub-entrega, mas foi
# REVERTIDO por um bloqueio operacional descoberto aqui (ver decisão abaixo).
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T18:57:31Z"
fim: "2026-09-07T19:04:17Z"
arquivos_alterados:
  - functions/autonomy/policy.py
  - functions/test_policy.py
decisoes:
  - id: p02-sub6-decisao-piso-compartilhada
    motivo: "decisao_piso(db, principal, nome, argumentos) orquestra estado_autonomia_atual() + PolicyRequest + avaliar() + registrar_decisao() num único ponto reutilizável por qualquer canal, extraído da lógica que mcp_server.py::_decisao_piso_mcp já tinha desde a sub-entrega 2/N. Retorna None quando nome não está em CLASSE_EFEITO_PISO, mesmo contrato de _decisao_piso_mcp. A duplicação entre as duas funções foi mantida deliberadamente (mcp_server.py não foi religado para usar a nova) para não mexer num caminho de código sensível já testado só para eliminar duplicação -- registrado como pendência abaixo."
    autoridade: existente_ou_nova
  - id: p02-sub6-telegram-wiring-revertido-limite-argos
    motivo: "Achado operacional real, não de lógica: hermes_core_logic.py sozinho, sem NENHUMA mudança desta sub-entrega, já tem 276257 caracteres -- acima do limite de 200000 de mcp__Argos__argos_escrever_arquivo_repositorio.conteudo (a API de escrita do Argos exige o arquivo INTEIRO, não um diff/patch). Esse arquivo é estruturalmente inalcançável por este mecanismo de shipping, para QUALQUER mudança, não só a desta sub-entrega -- não é um problema desta sub-entrega especificamente, é um teto estrutural do canal Telegram inteiro enquanto ele viver nesse arquivo. O wiring de schedule_whatsapp_message -> decisao_piso() foi implementado e testado localmente, depois revertido (não enviado) porque não havia como enviá-lo. decisao_piso() em si não depende de hermes_core_logic.py e foi entregue mesmo assim, pronta para quando esse arquivo puder ser alcançado (extrair os handlers de Telegram para um módulo menor, ou uma via de escrita que aceite diffs)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "Python (unittest, suíte completa): 1302/1302 passando (1296 anteriores da sub-entrega 5/N + 6 testes novos em TestDecisaoPiso -- test_policy.py: fora-do-piso sem tocar Firestore, ativo -> REQUIRE_APPROVAL + registra, pausado -> DENY, somente_preparacao -> PREPARE_ONLY, falha ao ler estado não propaga, falha ao registrar não propaga; 0 regressões), conforme mensagem do commit 426167193."
evidencias:
  - "Commits 12da7dbae (função) e 426167193 (testes) no branch claude/p02-autonomy-policy-contracts, lidos integralmente via git show para escrever este registro retroativo -- não há relato de revisão adversarial independente para esta sub-entrega especificamente, porque este registro foi escrito depois do fato, por uma sessão que não estava presente durante a implementação original. Fica como lacuna honesta: se uma revisão adversarial dedicada a este diff específico ainda não rodou, ela é candidata pendente, não algo a fingir que já aconteceu."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Duplicação entre autonomy/policy.py::decisao_piso() (nova) e mcp_server.py::_decisao_piso_mcp (sub-entrega 2/N) não foi eliminada -- mcp_server.py continua com sua própria implementação. Unificar fica para quando o canal MCP for revisitado por outro motivo, ou quando um segundo canal real (Telegram ou outro) começar a usar decisao_piso() e a duplicação passar a doer de verdade."
  - "hermes_core_logic.py (276257 caracteres) é estruturalmente inalcançável por mcp__Argos__argos_escrever_arquivo_repositorio (limite de 200000 caracteres, escrita é arquivo inteiro, não diff) -- isso bloqueia não só o wiring de decisao_piso() no Telegram, mas QUALQUER mudança futura nesse arquivo por este mecanismo de shipping. Vale levar ao André como achado operacional (não é decisão de design do plano, é uma limitação de ferramenta) -- candidatos: extrair handlers de Telegram para um módulo menor, ou uma via de escrita que aceite diff/patch."
  - "Não há revisão adversarial independente registrada para o diff desta sub-entrega especificamente (ver evidências acima) -- se ainda não rodou, é candidata a rodar antes do pacote P02 ser dado como fechado."
  - "Passo 1 do plano segue MATERIALMENTE em aberto: só o canal MCP constrói Principal e passa pelo preflight (desde a sub-entrega 2/N). Telegram, outbox_aprovacao.py, revisao_semanal.py e mcp_jobs.py continuam sem construir Principal nenhum -- e o Telegram especificamente agora tem o bloqueio de tamanho de arquivo acima, além da ambiguidade de tipo já registrada na sub-entrega 5/N."
  - "Todas as pendências já registradas nos blocos das sub-entregas 1/N a 5/N que não foram tocadas nesta sub-entrega continuam abertas: validação de tipo de PolicyRequest.orcamento_restante no wrapper MCP, Mandato.classes_conteudo_permitidas texto livre sem enum fechado, Mandato.usos_na_janela_atual e Mandato.orcamento_maximo sem wrapper de I/O real, o bug de tipo em autonomy/policy.py::preparar_politica (contornado na wrapper, não corrigido no motor), a pergunta de design sobre o default de origem_humana (levar ao André só ao fim do pacote inteiro)."
proximo_pacote: "P02 (sub-entrega 7/N -- ver bloco seguinte)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 426167193ebf4004dfc20c278a3e4db4f1c5ba1f
pacote: "P02 (sub-entrega 7/N -- fecha o atalho de bypass de confirmação para tools gated só por config, passo 6 do plano; inclui correção de um incidente de shipping desta mesma sub-entrega)"
# Esta sub-entrega tem duas partes, registradas juntas porque a segunda
# corrige um erro cometido ao entregar a primeira, na mesma sessão de
# trabalho -- princípio "reconhecido, não escondido" do plano (não há
# nenhuma tentativa de separar isso num registro mais discreto).
#
# PARTE 1 -- a mudança pretendida: a sub-entrega 2/N tinha fechado o atalho
# de bypass de confirmação (_confirmed=true sem _confirmation_id executando
# direto, sem nunca passar por preflight nem criar confirmação real) só para
# o piso hardcoded (FLOOR_CONFIRMACAO_OBRIGATORIA), e tinha registrado
# EXPLICITAMENTE como pendência que o mesmo gap continuava teoricamente
# possível para uma tool exigindo confirmação só por config
# (system/mcp_access.confirm_tools, fora do piso) sem hook de prévia. Esta
# sub-entrega fecha esse mesmo atalho também para tools de confirmação só
# por config -- mesma garantia do piso, sem mais exceção "legada". Hoje
# system/mcp_access.confirm_tools está vazio em produção (achado já
# registrado desde antes: contorno do WhatsApp de 27/08/2026), então esta
# mudança não altera nenhum comportamento observável hoje -- só fecha a
# lacuna teórica para quando alguém configurar uma tool assim no futuro.
#
# PARTE 2 -- o incidente e a correção: ao entregar a Parte 1 (rotulada, por
# engano, "sub-entrega 4/N"), o commit foi construído sobre uma base git
# local desatualizada. O clone local usado nesta sessão não tinha o fetch
# refspec configurado para esta branch (`git config --get-all
# remote.origin.fetch` só cobria main e claude/p00-baseline-ambiente-seguro)
# -- então `git fetch origin claude/p02-autonomy-policy-contracts` buscava
# os objetos do branch mas NUNCA atualizava
# refs/remotes/origin/claude/p02-autonomy-policy-contracts, e `git log
# origin/claude/p02-autonomy-policy-contracts` continuava mostrando a
# sub-entrega 3/N como ponta, não importa quantas vezes o fetch fosse
# repetido. Na realidade a branch já tinha avançado 7 commits (as
# sub-entregas 4/N real -- orçamento no mandato --, 5/N e 6/N, registradas
# nos blocos acima). O envio da Parte 1 via
# mcp__Argos__argos_escrever_arquivo_repositorio (que resolve o sha atual no
# servidor, então o COMMIT em si ficou corretamente encadeado depois do
# commit real mais recente da branch) enviou um CONTEÚDO baseado na versão
# desatualizada do arquivo -- uma sobrescrita de arquivo inteiro que
# reverteu, sem que eu percebesse na hora, a delegação de
# mcp_server.py::_principal_mcp() para tools.tool_context.principal_de()
# introduzida pela sub-entrega 5/N (import e corpo da função voltaram à
# forma anterior a ela). Só foi descoberto porque o campo `parents` da
# resposta do Argos trazia um sha pai diferente do esperado, o que motivou
# investigação. Diagnóstico confirmado com `git ls-remote origin <branch>`
# (que ignora refs locais e mostra a ponta real) e `git diff` entre o commit
# anterior ao meu e o meu.
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T19:56:38Z"
fim: "2026-09-07T20:14:00Z"
arquivos_alterados:
  - functions/mcp_server.py
  - functions/test_mcp_server.py
  - docs/autonomia/execucao.md
decisoes:
  - id: p02-sub7-fecha-atalho-bypass-config
    motivo: "Mesma classe do achado fechado para o piso na sub-entrega 2/N: uma tool de confirmação obrigatória só por config (system/mcp_access.confirm_tools, fora do piso hardcoded) que também não tem hook de prévia (preview_tool devolve None) caía no mesmo atalho -- _confirmed=true sem _confirmation_id executava direto, sem nunca criar uma confirmação real nem passar por qualquer preflight de política. Fechado: TODA tool que exige confirmação (piso ou config) sempre exige o confirmation_id de uma confirmação real, hook de prévia ou não. Testado nos dois níveis (bloqueio sem confirmation_id e caminho legítimo com confirmation_id real ainda funcionando) em TestPisoSemHookNaoBurlaConfirmacaoComConfirmedTrue."
    autoridade: existente_ou_nova
  - id: p02-sub7-incidente-base-local-desatualizada
    motivo: "Ver nota no topo do bloco (PARTE 2) para o diagnóstico completo. Correção aplicada: (1) restaurada a delegação _principal_mcp() -> tools.tool_context.principal_de() (import e corpo/docstring), mesmo comportamento observável -- provado por TestPrincipalMcp, sem alteração de expectativa; (2) preservada integralmente a mudança pretendida da Parte 1; (3) fetch local corrigido com refspec explícito por branch (`git fetch origin +refs/heads/<branch>:refs/remotes/origin/<branch>`), e `git ls-remote` passa a ser o método de verificação da ponta real antes de qualquer leitura de base neste branch daqui em diante -- a lição de fundo: hash-verificar o upload de um arquivo (disciplina já seguida, sha conferido em cada escrita) prova que o CONTEÚDO chegou fiel, mas não prova que a BASE local de onde ele foi lido/editado estava atualizada; as duas verificações são independentes e a segunda faltou aqui."
    autoridade: existente_ou_nova
  - id: p02-sub7-renumeracao-4n-para-7n
    motivo: "A Parte 1 foi originalmente rotulada 'sub-entrega 4/N' -- rótulo já ocupado pela sub-entrega real de orçamento no mandato (passo 8), que eu não enxergava por causa do mesmo problema de fetch descrito acima. Corrigido para 7/N (próximo número livre após 6/N) nos comentários de mcp_server.py e test_mcp_server.py e no registro deste arquivo."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_mcp_server -v"
  resultados:
    - "Python (unittest, suíte completa): 1304/1304 passando (1302 da sub-entrega 6/N + 2 testes novos: bloqueio sem confirmation_id e caminho legítimo com confirmation_id real, para tool gated só por config sem hook; 0 regressões). Suíte rodada sobre a árvore local sincronizada com a ponta real da branch (verificada por git ls-remote) + esta correção -- não sobre a base desatualizada que causou o incidente."
    - "test_mcp_server -v: 22/22, incluindo TestPrincipalMcp (prova que a delegação restaurada não muda o resultado)."
evidencias:
  - "git diff entre o commit imediatamente anterior ao meu (426167193) e o meu (c99739629, antes da correção) isolou exatamente uma reversão não intencional -- a delegação de principal_de(); nenhuma outra sub-entrega (4/N real, 5/N, 6/N) foi afetada em nenhum outro arquivo, confirmado por git diff --stat entre a base desatualizada (5621eb5a6) e a ponta real (c99739629)."
  - "git ls-remote origin claude/p02-autonomy-policy-contracts confirmou a ponta real em cada etapa da correção (antes de reescrever o arquivo, e depois de cada envio), prevenindo repetir o mesmo erro durante a própria correção."
  - "sha devolvido pelo Argos em cada envio (mcp_server.py: 23876e6082a95bbb696ff772edcf741b7feede9e; test_mcp_server.py: d979a3e31d335cf52b17ac3a78aaeb05b2137a14) conferido contra git hash-object do arquivo local antes de enviar, e o campo parents da resposta conferido contra o commit esperado -- disciplina que já existia (skill argos-ship-feature) e que, desta vez, foi o que revelou o problema (parents não batia com o esperado)."
  - "Nenhuma revisão adversarial por sub-agente independente foi despachada para o diff da Parte 1 nem para a correção da Parte 2 nesta sub-entrega -- diferente do padrão das sub-entregas 1/N-6/N. Registrado honestamente como lacuna, não escondido: a correção foi verificada por leitura direta do diff e por testes, não por um revisor sem contexto prévio. Candidata a rodar antes do pacote P02 ser dado como fechado."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Nenhuma revisão adversarial independente rodou para esta sub-entrega (ver evidências) -- diferente das sub-entregas anteriores, que sempre tiveram uma. Deveria rodar antes de considerar P02 fechado."
  - "O mesmo tipo de checagem que capturou este incidente (git ls-remote antes de ler a base) deveria virar hábito no início de qualquer sub-entrega futura desta sessão neste repositório, não só quando algo parece errado -- registrado aqui para não depender de lembrar sem reforço escrito."
  - "Duplicação entre autonomy/policy.py::decisao_piso() e mcp_server.py::_decisao_piso_mcp permanece (pendência já registrada no bloco da sub-entrega 6/N)."
  - "hermes_core_logic.py (276257 caracteres) permanece estruturalmente inalcançável por mcp__Argos__argos_escrever_arquivo_repositorio (pendência já registrada no bloco da sub-entrega 6/N) -- vale levar ao André."
  - "Passo 1 do plano segue MATERIALMENTE em aberto: só o canal MCP constrói Principal e passa pelo preflight. Telegram, outbox_aprovacao.py, revisao_semanal.py e mcp_jobs.py continuam sem construir Principal nenhum."
  - "Todas as pendências já registradas nos blocos das sub-entregas 1/N a 6/N que não foram tocadas nesta sub-entrega continuam abertas: validação de tipo de PolicyRequest.orcamento_restante no wrapper MCP, Mandato.classes_conteudo_permitidas texto livre sem enum fechado, Mandato.usos_na_janela_atual e Mandato.orcamento_maximo sem wrapper de I/O real, o bug de tipo em autonomy/policy.py::preparar_politica (contornado na wrapper, não corrigido no motor), a pergunta de design sobre o default de origem_humana (levar ao André só ao fim do pacote inteiro)."
proximo_pacote: "P02 (sub-entrega 8/N -- candidata a decidir: despachar a revisão adversarial pendente desta sub-entrega e da 6/N antes de seguir adiante, ou continuar o passo 1 decidindo o TipoPrincipal de um canal específico agora que decisao_piso() está pronto para reuso)"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: b8ce2963df329db0a9792166c3b6cadf91a667cf
pacote: "P02 (revisão adversarial retroativa das sub-entregas 6/N e 7/N -- sem mudança de código de produção)"
# Esta entrada não implementa nada novo. Ela despacha a revisão adversarial
# que os blocos das sub-entregas 6/N e 7/N já registravam como pendente --
# "deveria rodar antes de considerar P02 fechado" -- e registra o resultado.
# Escolhida como o próximo passo em vez de avançar o passo 1 do plano,
# seguindo o próprio proximo_pacote do bloco anterior.
estado: validado
inicio: "2026-09-07T20:14:00Z"
fim: "2026-09-07T20:31:42Z"
arquivos_alterados:
  - docs/autonomia/execucao.md
decisoes:
  - id: p02-sub8-revisao-6N-7N-sem-achado-bloqueante
    motivo: "Sub-agente general-purpose independente, sem contexto prévio da implementação, revisou os diffs de autonomy/policy.py::decisao_piso()+test_policy.py (sub-entrega 6/N) e mcp_server.py+test_mcp_server.py (sub-entrega 7/N, incluindo a correção do incidente de reversão acidental de principal_de()). Rodou a suíte real (1304/1304, batendo com o alegado), traçou o histórico de commits (04ed060da -> c99739629 -> c69468d9a -> de5c34e40 -> b8ce2963d) e confirmou por diff direto que (a) _principal_mcp delega para principal_de() sem perda de comportamento, (b) nenhum outro resíduo do revert acidental restou em mcp_server.py, (c) o fechamento do atalho de bypass de confirmação cobre todos os caminhos de dispatch reais (sem via paralela, sem replay via _executar_confirmacao, que já valida confirmation_id contra Firestore/uid/expiração/claim atômico). Comparou decisao_piso() e _decisao_piso_mcp() linha a linha: equivalentes, divergência de tratamento de erro é intencional e documentada. Veredito explícito: \"Pronto. Não encontrei bugs de segurança ou de lógica bloqueantes em nenhum dos dois diffs.\""
    autoridade: existente_ou_nova
  - id: p02-sub8-achado-nao-bloqueante-avaliar-sem-protecao
    motivo: "Único achado do revisor, não-bloqueante: decisao_piso() (e também _decisao_piso_mcp, já em produção desde a sub-entrega 2/N -- não é regressão desta sub-entrega) chama avaliar(request) sem try/except ao redor; um principal malformado (None, ou objeto sem .eh_dono()/.tipo) propagaria AttributeError em vez de cair em SOMENTE_PREPARACAO como o resto da função faz. Risco prático hoje é zero -- decisao_piso() não tem nenhum consumidor real fora dos próprios testes (confirmado por grep: só aparece em test_policy.py, autonomy/policy.py e execucao.md). Não corrigido agora, deliberadamente: registrado como pendência para quando um canal real passar a chamar decisao_piso() com um principal construído fora do controle do próprio módulo -- momento em que também caberia um teste de regressão dedicado."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py' (rodado pelo sub-agente revisor, ambiente venv já existente)"
  resultados:
    - "1304 passed / 0 failed / 0 erros / 0 skips -- confirma, por execução independente (não só leitura), a mesma contagem já alegada nos commits c69468d9a e de5c34e40."
evidencias:
  - "Relatório completo do sub-agente (general-purpose, dispatch via Agent tool, sem memória da implementação original) cobrindo os dois diffs -- ver decisões acima para o resumo; o relatório também confirmou ausência de ciclo/resíduo via checagem AST por definições de função duplicadas em mcp_server.py e via git diff 04ed060da..b8ce2963d --  functions/mcp_server.py isolando exatamente o fechamento do atalho de confirmação, nada mais."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: a pendência 'nenhuma revisão adversarial independente rodou' registrada nos blocos das sub-entregas 6/N e 7/N. Rodou, sem achado bloqueante (ver decisões acima)."
  - "Novo, não-bloqueante: decisao_piso()/avaliar() não protegida contra principal malformado (ver decisão p02-sub8-achado-nao-bloqueante-avaliar-sem-protecao) -- endereçar quando um canal real além dos testes passar a chamar decisao_piso()."
  - "Duplicação entre autonomy/policy.py::decisao_piso() e mcp_server.py::_decisao_piso_mcp permanece (pendência já registrada no bloco da sub-entrega 6/N) -- não tocada por esta revisão, que confirmou as duas equivalentes para os casos testados."
  - "hermes_core_logic.py (276257 caracteres) permanece estruturalmente inalcançável por mcp__Argos__argos_escrever_arquivo_repositorio (pendência já registrada no bloco da sub-entrega 6/N) -- vale levar ao André."
  - "Passo 1 do plano segue MATERIALMENTE em aberto: só o canal MCP constrói Principal e passa pelo preflight. Telegram, outbox_aprovacao.py, revisao_semanal.py e mcp_jobs.py continuam sem construir Principal nenhum."
  - "Todas as pendências já registradas nos blocos das sub-entregas 1/N a 7/N que não foram tocadas por esta revisão continuam abertas: validação de tipo de PolicyRequest.orcamento_restante no wrapper MCP, Mandato.classes_conteudo_permitidas texto livre sem enum fechado, Mandato.usos_na_janela_atual e Mandato.orcamento_maximo sem wrapper de I/O real, o bug de tipo em autonomy/policy.py::preparar_politica (contornado na wrapper, não corrigido no motor), a pergunta de design sobre o default de origem_humana (levar ao André só ao fim do pacote inteiro)."
proximo_pacote: "P02 (sub-entrega 9/N -- revisão da 6/N e 7/N concluída sem achado bloqueante; decidir entre continuar o passo 1 do plano (decidir TipoPrincipal de um canal específico e religar esse canal a decisao_piso(), já pronta para reuso), ou levar ao André agora o achado operacional da sub-entrega 6/N sobre o teto de 200000 caracteres do Argos em hermes_core_logic.py, já que não depende de mais trabalho autônomo para ser decidido)"
```
