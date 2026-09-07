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
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_outbox_aprovacao -v"
    - "cd functions && venv/bin/python -m unittest test_promocao_autonomia -v"
  resultados:
    - "Python (unittest, suíte completa): 1150/1150 passando (1146 anteriores + 4 testes novos; 0 regressões)"
    - "test_outbox_aprovacao: 37/37 (4 novos: 2 cenários de erro_transacao, 2 de erro_configuracao, cobrindo aprovar e descartar)"
    - "test_promocao_autonomia: 25/25, incluindo os testes de cancelamento/liberação agora exercitando o decorator @firestore.transactional real"
    - "Frontend (npm test): não reexecutado nesta sub-entrega — nenhum arquivo de frontend foi alterado"
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação): verificou ausência de caminho de escrita desprotegida remanescente, segurança de todos os 5 pontos de chamada para os novos status, fidelidade do mock ao protocolo real (via leitura do código-fonte da lib instalada), não-vacuidade dos testes novos (raciocinado contra o código pré-mudança), isolamento da mudança de texto (grep no repo inteiro), e ausência de arquivos inesperados no diff. Veredito: seguro para publicar."
  - "Achado adicional da revisão (não corrigido nesta sub-entrega, registrado para sub-entregas seguintes de P01): o mesmo padrão de fallback não-transacional do A04 ainda existe, sem correção, em promocao_autonomia.py:228 (decidir_promocao_autonomia) e em argos_autorizacao.py:242,348 — este último fora da lista de arquivos do P01 no plano."
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
proximo_pacote: "P01 (sub-entrega 2/N)"
```
