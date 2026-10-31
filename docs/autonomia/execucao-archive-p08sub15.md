# Arquivo: bloco "P08 sub-entrega 15/N" movido de execucao.md em 2026-10-31.

---

```yaml
pacote: "P08 sub-entrega 15/N -- despertar persistido de espera externa (autonomy/acordar_persistido.py, passo 5, wiring de persistência): acordar_pedido(db, request_id, executor_id, run_id, agora, duracao_segundos, por_evento) liga acordar_espera_externa a atualizar_pedido, que ganhou o parâmetro opcional run_encerrado: o run antigo fechado por timeout é gravado em autonomy_pedidos/{id}/runs_encerrados/{run_id} na MESMA transação do pedido (só se o pedido mudou). run_id validado como id do Firestore antes da transação; leitura do arquivo antes de qualquer escrita; run_id já arquivado com conteúdo diferente é recusado (igual = idempotente). serializacao: run_para_dict extraído sem mudar o formato. Nada chama o módulo em produção (shadow/off)."
estado: validado
inicio: "2026-10-30T16:50:00Z"
fim: "2026-10-30T17:15:00Z"
decisoes:
  - id: p08-sub15-triagem
    motivo: "PRs abertas: #565 (email), #561 (finanças, muda saldo) e #556 (excluir_entrada_diario, apaga dados, pede aval do André): outra linha, nenhuma tocada. Nenhuma PR da autonomia pendente; nenhuma execução paralela."
  - id: p08-sub15-arquivo
    motivo: "execucao.md acima de ~50KB: bloco P08 sub 12 arquivado em execucao-archive-p08sub12.md."
  - id: p08-sub15-escopo
    motivo: "Fora de escopo: reconciliar_resultado_desconhecido persistido (mesmo molde, próxima fatia), FALHA_FINAL por reconciliação, worker HTTP, Cloud Tasks, agendamento."
testes:
  resultados:
    - "functions/ completo ANTES 5008 OK (diário, P08 sub 14); DEPOIS 5107 OK (suíte completa, 315s, após a correção do Codex; testes novos: 7 em test_autonomy_acordar_persistido + 4 em test_autonomy_pedido_repositorio; o restante vem de merges de outras linhas)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): 2 achados reais -- run_id novo sem validação de id do Firestore (pedido ficaria impossível de acordar de novo) e run_id reutilizado sobrescrevendo o arquivo; corrigidos e cobertos por teste (e a leitura do arquivo foi posta antes das escritas, exigência das transações do Firestore). Rodada 2 (focada na correção, agente sem contexto, somente leitura): não achei nada. Codex na PR #571: 1 achado P2 real -- run_id NOVO já presente no arquivo de runs encerrados travaria o despertar seguinte (conflito ao arquivá-lo); agora lido e recusado na mesma transação, antes das escritas; coberto por teste. Rodada 3 (focada na correção do Codex, agente sem contexto, somente leitura): não achei nada. Não verificado contra Firestore real."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real, reconciliar_resultado_desconhecido persistindo também o run antigo (usar run_encerrado), FALHA_FINAL por reconciliação, AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), espera sem lease, cliente Claude real com ConfigModelos, cache de prompt, flag do modo e orçamento de despachos, IAM mínimo)."
```
