# Arquivo: bloco "P08 sub-entrega 17/N" movido de execucao.md em 2026-11-01.

---

```yaml
pacote: "P08 sub-entrega 17/N -- configuração persistida do dispatcher (autonomy/config_dispatcher.py, passos 3 e 11, flag do modo e orçamento de despachos): ler_config_dispatcher(db) lê configuracoes/autonomia_dispatcher (modo off|shadow|ativo, despachos_restantes) e devolve ConfigDispatcher para decidir_lote. Fail-closed: documento ausente, erro de leitura, modo desconhecido ou orçamento ausente/inválido (bool, float, str, negativo) = OFF/sem orçamento; shadow nunca carrega orçamento. Só leitura; consumir orçamento e agendar ficam para depois. Nada chama o módulo em produção (shadow/off)."
estado: validado
inicio: "2026-10-31T13:45:00Z"
fim: "2026-10-31T14:05:00Z"
decisoes:
  - id: p08-sub17-triagem
    motivo: "PRs abertas #572, #565, #561 e #556 são de outra linha (melhorias): nenhuma tocada. Nenhuma PR da autonomia pendente; nenhuma execução paralela da linha."
  - id: p08-sub17-arquivo
    motivo: "execucao.md acima de ~50KB: bloco P08 sub 14 arquivado em execucao-archive-p08sub14.md."
  - id: p08-sub17-escopo
    motivo: "Fora de escopo: transação de consumo do orçamento, agendamento do dispatcher, Cloud Tasks real, worker HTTP."
testes:
  resultados:
    - "functions/ completo ANTES 5140 OK (main); DEPOIS 5147 OK (183s; 7 testes novos em test_autonomy_config_dispatcher)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): não achei nada. Observação para o wiring: proteger decidir_lote com try (item que não seja PedidoDuravel levanta TypeError). Codex na PR #579: 1 achado P2 real (ATIVO com orçamento inválido devolvia modo ATIVO, contra o contrato fail-closed); agora devolve OFF; teste assertando o modo. Rodada 2 (focada na correção, agente sem contexto, somente leitura): não achei nada. Não verificado contra Firestore real."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real, consumo transacional do orçamento, FALHA_FINAL por reconciliação, AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), espera sem lease, cliente Claude real com ConfigModelos, cache de prompt, IAM mínimo)."
```

