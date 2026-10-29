```yaml
pacote: "P08 sub-entrega 9/N -- acordar espera externa (autonomy/runner_aplicacao.py, passo 5): função pura acordar_espera_externa(pedido, executor_id, run_id, agora, duracao_segundos, por_evento). Retoma AGUARDANDO_EXTERNO num worker novo: exige lease anterior vencida (nunca toma reserva válida), emite lease nova com geração+1 (fencing: token antigo perde o direito), fecha o run antigo por timeout (devolvido ao chamador para persistir), abre run novo EM_ANDAMENTO com run_id inédito, preserva ledger/tentativas/pausas e limpa condicao_espera/proximo_tentativa_em. Antes de proximo_tentativa_em só com por_evento=True. Sem I/O (shadow/off)."
estado: validado
inicio: "2026-10-28T19:48:00Z"
fim: "2026-10-28T20:10:00Z"
decisoes:
  - id: p08-sub9-triagem
    motivo: "Única PR aberta (#552, correção de OAuth do MCP, outra linha, sensível à segurança, revisão em andamento): não tocada. Nenhuma PR da autonomia pendente."
  - id: p08-sub9-arquivo
    motivo: "execucao.md no limite de ~50KB: bloco P08 sub 6 arquivado em execucao-archive-p08sub6.md."
  - id: p08-sub9-cas
    motivo: "Exclusão mútua entre dois despertares (ou despertar x sweep) sobre o mesmo snapshot é do wiring (compare-and-swap em generation/status); documentado na docstring."
testes:
  resultados:
    - "functions/ completo ANTES 4902 OK (diário, P08 sub 8); DEPOIS 4912 OK (+9 em test_autonomy_runner_aplicacao; o restante vem de merges de outras linhas)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): nenhum bug alcançável; 2 observações de baixo risco, ambas tratadas (run_id repetido agora recusado, com teste; CAS do wiring documentado). Codex na PR #553: 1 achado P2 real -- a checagem de run_id repetido não normalizava espaços como AgentRun faz (\" run-1 \" passava e colidia); corrigido (compara o id normalizado) e coberto por teste. Correção de uma linha, sem rodada adversarial adicional."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real tratando ALREADY_EXISTS, persistência/CAS chamando decidir_continuacao + aplicar_decisao_continuacao, o sweep e acordar_espera_externa persistindo também o run antigo fechado, RESULTADO_DESCONHECIDO sem saída no sweep (reconciliação), AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), cliente Claude real com ConfigModelos, cache de prompt, flag do modo e orçamento de despachos, IAM mínimo)."
```
