# Arquivo: bloco "P08 sub-entrega 19/N" movido de execucao.md em 2026-11-01.

---

```yaml
pacote: "P08 sub-entrega 19/N -- ciclo do dispatcher (autonomy/ciclo_dispatcher.py, passos 3, 4 e 11): executar_ciclo(db, enfileirar, agora, limite) lê a config (off = não toca em pedidos), lê até 5 páginas (cursor por id) de pedidos PENDENTE/RETENTATIVA_AGENDADA, decide com decidir_lote e executa: shadow só devolve o que seria enfileirado; ativo baixa 1 do orçamento (consumir_orcamento) ANTES de chamar o enfileirar(nome, payload) injetado. config_dispatcher ganhou devolver_orcamento (estorno transacional, só ativo). JaDespachado (ALREADY_EXISTS) estorna a baixa; falha genérica do enfileirador não estorna (resultado ambíguo, lado seguro). Falha da consulta vira erro sem enfileirar. Nada chama o módulo em produção (shadow/off)."
estado: validado
inicio: "2026-10-31T19:48:00Z"
fim: "2026-10-31T20:30:00Z"
decisoes:
  - id: p08-sub19-triagem
    motivo: "PRs abertas #586, #585 e #561 são de outra linha (melhorias/upload/finanças): nenhuma tocada. Nenhuma PR da autonomia pendente; nenhuma execução paralela da linha."
  - id: p08-sub19-arquivo
    motivo: "execucao.md acima de ~50KB: bloco P08 sub 16 arquivado em execucao-archive-p08sub16.md."
  - id: p08-sub19-estorno
    motivo: "Achado da rodada 1 (pedido segue PENDENTE e reaparece a cada passada, drenando o orçamento): estorno em duplicata. Rodada 2 apontou que estornar em falha genérica pode deixar despacho real fora da conta: removido, orçamento fica gasto nesse caso."
  - id: p08-sub19-escopo
    motivo: "Fora de escopo: agendamento (função/scheduler), enfileirador Cloud Tasks real, worker HTTP, observabilidade de estorno que falhou, pedidos além de 5 páginas."
testes:
  resultados:
    - "functions/ completo ANTES 5159 OK (main); DEPOIS 5174 OK (214s; 15 testes novos em test_autonomy_ciclo_dispatcher e test_autonomy_consumo_orcamento)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): 4 achados reais -- vazamento de orçamento por redespacho, falha do enfileirador gastando orçamento, bloqueio de cabeça de fila (limite sem paginação), exceção da consulta escapando; corrigidos (estorno em duplicata, paginação por cursor, consulta em try, agora não-datetime = ValueError). Rodada 2 (focada na correção): nenhum bug; 2 riscos baixos: estorno em falha ambígua (corrigido: não estorna) e estorno que falha sem observabilidade (aceito, fail-closed). Codex na PR #587: 1 achado P1 real (snapshot do saldo em decidir_lote consumia a vaga de uma duplicata estornada e deixava candidatos seguintes sem despacho, fome por ids baixos); agora o teto de decidir_lote é len(pedidos) e a baixa transacional impõe o limite; teste cobre. Rodada 3 (focada na correção, agente sem contexto, somente leitura): não achei nada. Não verificado contra Firestore/Cloud Tasks reais."
pendencias:
  - "P08: wiring (agendar o ciclo, enfileirador Cloud Tasks real tratando ALREADY_EXISTS como JaDespachado, worker HTTP verificando JWT, FALHA_FINAL por reconciliação, AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), espera sem lease, cliente Claude real com ConfigModelos, cache de prompt, IAM mínimo)."
```

