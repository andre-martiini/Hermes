PART_A_PLACEHOLDER
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