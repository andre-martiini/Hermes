# Arquivo: bloco "P08 sub-entrega 16/N" movido de execucao.md em 2026-10-31.

---

```yaml
pacote: "P08 sub-entrega 16/N -- reconciliação persistida de resultado desconhecido (autonomy/reconciliar_persistido.py, passo 5, wiring de persistência): reconciliar_pedido(db, request_id, efeito_ocorreu, agora, executor_id, run_id, continuar_em, duracao_segundos) liga reconciliar_resultado_desconhecido a atualizar_pedido (run_encerrado), no molde de acordar_pedido: pedido e run antigo fechado por timeout (se ainda ativo) gravados na MESMA transação em runs_encerrados/{run_id}. run_id validado como id do Firestore antes da transação quando efeito_ocorreu=True. Reaproveita ResultadoDespertar; sem mudança em módulo existente. Nada chama o módulo em produção (shadow/off)."
estado: validado
inicio: "2026-10-30T19:48:00Z"
fim: "2026-10-30T20:20:00Z"
decisoes:
  - id: p08-sub16-triagem
    motivo: "PRs abertas #572, #565, #561 e #556 são de outra linha (melhorias/finanças/email/MCP): nenhuma tocada. Nenhuma PR da autonomia pendente; nenhuma execução paralela (última branch claude/ de autonomia há mais de 2h)."
  - id: p08-sub16-arquivo
    motivo: "execucao.md acima de ~50KB: bloco P08 sub 13 arquivado em execucao-archive-p08sub13.md."
  - id: p08-sub16-escopo
    motivo: "Fora de escopo: FALHA_FINAL por reconciliação (exige fencing do ledger), worker HTTP, Cloud Tasks, agendamento."
testes:
  resultados:
    - "functions/ completo ANTES 5107 OK (diário, P08 sub 15); DEPOIS 5122 OK (205s; 10 testes novos em test_autonomy_reconciliar_persistido; o restante vem de merges de outras linhas)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): não achei nada. Codex na PR #574: 1 achado P2 real que a rodada 1 não pegou -- o run já terminal deixado pelo sweep em pedido.run sumia ao ser substituído pelo run do verificador (efeito_ocorreu=True), pois a função pura devolve antigo=None; agora atual.run é arquivado quando o run novo o substitui; coberto por teste. Rodada 2 (focada na correção, agente sem contexto, somente leitura): não achei nada. Não verificado contra Firestore real."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real, FALHA_FINAL por reconciliação, AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), espera sem lease, cliente Claude real com ConfigModelos, cache de prompt, flag do modo e orçamento de despachos, IAM mínimo)."
```

