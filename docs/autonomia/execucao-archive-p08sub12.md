# Arquivo: bloco "P08 sub-entrega 12/N" movido de execucao.md em 2026-10-30.

---

```yaml
pacote: "P08 sub-entrega 12/N -- repositório Firestore do pedido durável (autonomy/pedido_repositorio.py, passo 4, persistência/CAS): criar_pedido (PedidoJaExiste se já existe), ler_pedido (None se ausente) e atualizar_pedido (read-modify-write em transação do Firestore com transformar pura; sem mudança não escreve; revisão incrementada). Documento autonomy_pedidos/{request_id} = {pedido, revisao}. Leitura estrita (PedidoCorrompido). Validação das regras do Firestore antes de gravar: request_id (., .., __x__, >1500 bytes, controle, surrogate), int64, chaves vazias/__x__/longas, UTF-8, 20 níveis de mapa. Nada chama o módulo em produção (shadow/off)."
estado: validado
inicio: "2026-10-29T19:48:00Z"
fim: "2026-10-29T20:10:00Z"
decisoes:
  - id: p08-sub12-triagem
    motivo: "PRs abertas: #561 (finanças, outra linha, muda cálculo de saldo) e #556 (excluir_entrada_diario, apaga dados, pede aval do André): nenhuma tocada. Nenhuma execução paralela (branches claude/* sem atividade há >60 min). Nenhuma PR da autonomia pendente."
  - id: p08-sub12-arquivo
    motivo: "execucao.md acima de ~50KB: bloco P08 sub 9 arquivado em execucao-archive-p08sub9.md."
  - id: p08-sub12-escopo
    motivo: "Fora de escopo, deliberado: limite de 1 MiB por documento e de tamanho de string; teste contra Firestore real/emulador (o duplo de teste usa o decorator real @firestore.transactional mas não simula conflito de contenção); chamadores (worker, Cloud Tasks, sweep persistindo) ficam para o wiring."
testes:
  resultados:
    - "functions/ completo ANTES 4976 OK (diário, P08 sub 11; 4990 OK em main + 12 testes novos medidos antes da correção da rodada 1); DEPOIS 4991 OK (suíte completa também após a correção do Codex; 13 testes novos em test_autonomy_pedido_repositorio)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): 2 achados reais de validação -- request_id reservado do Firestore passava; int fora de int64 e chaves vazias/__x__ eram gravados sem validação (erro opaco dentro da transação). Corrigidos e cobertos. Rodada 2 (focada na correção): 3 achados -- profundidade de mapa >20, surrogate solitário em ids/chaves/valores, chave >1500 bytes; corrigidos e cobertos por teste. Codex na PR #564: 1 achado P2 real -- array dentro de array passava na validação; corrigido e coberto por teste. Rodada 3 (focada na correção do Codex, agente sem contexto, somente leitura): não achei nada. Não verificado contra o servidor real do Firestore (regras citadas da documentação)."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real, usar atualizar_pedido com decidir_continuacao + aplicar_decisao_continuacao, sweep persistindo, acordar_espera_externa e reconciliar_resultado_desconhecido persistindo também o run antigo, FALHA_FINAL por reconciliação, AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), cliente Claude real com ConfigModelos, cache de prompt, flag do modo e orçamento de despachos, IAM mínimo)."
```
