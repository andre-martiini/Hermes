# Arquivo: bloco "P08 sub-entrega 18/N" movido de execucao.md em 2026-11-01.

---

```yaml
pacote: "P08 sub-entrega 18/N -- consumo transacional do orçamento do dispatcher (autonomy/config_dispatcher.py, passo 11): consumir_orcamento(db, quantidade=1) baixa despachos_restantes de configuracoes/autonomia_dispatcher numa transação (@firestore.transactional, leitura e update na mesma transação), tudo ou nada, só em modo ativo, nunca abaixo de zero; devolve a quantidade concedida ou 0. Fail-closed: quantidade inválida (bool, não int, <1), backend sem transação, documento ausente/inválido, saldo insuficiente ou qualquer erro do Firestore = 0 sem conceder. Chamar ANTES de enfileirar. Nada chama o módulo em produção (shadow/off)."
estado: validado
inicio: "2026-10-31T16:47:00Z"
fim: "2026-10-31T17:15:00Z"
decisoes:
  - id: p08-sub18-triagem
    motivo: "PRs abertas #572, #565, #561 e #556 são de outra linha (melhorias): nenhuma tocada. Nenhuma PR da autonomia pendente; nenhuma execução paralela da linha."
  - id: p08-sub18-arquivo
    motivo: "execucao.md acima de ~50KB: bloco P08 sub 15 arquivado em execucao-archive-p08sub15.md."
  - id: p08-sub18-escopo
    motivo: "Fora de escopo: agendamento do dispatcher, Cloud Tasks real, worker HTTP, estorno de orçamento se o enfileiramento falhar depois da baixa (perde-se orçamento, lado seguro)."
testes:
  resultados:
    - "functions/ completo ANTES 5147 OK (diário, P08 sub 17); DEPOIS 5154 OK (247s; 7 testes novos em test_autonomy_consumo_orcamento)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): não achei nada. Observações aceitas: commit ambíguo (timeout após aplicar) perde orçamento, lado seguro; o duplo de transação dos testes acopla a atributos privados do google-cloud-firestore. Não verificado contra Firestore real."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real, FALHA_FINAL por reconciliação, AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), espera sem lease, cliente Claude real com ConfigModelos, cache de prompt, agendamento do dispatcher chamando ler_config_dispatcher + consumir_orcamento + decidir_lote, IAM mínimo)."
```
