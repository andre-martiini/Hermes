# Arquivo: bloco P08 sub 5 (movido de execucao.md em 2026-10-28)

```yaml
pacote: "P08 sub-entrega 5/N -- dispatcher shadow/off (autonomy/dispatcher.py, passos 3 e 11): função pura decidir_despacho/decidir_lote. Modo OFF é o padrão e o destino de config inválida (fail-closed); SHADOW devolve nome/payload da tarefa que seria enfileirada sem enfileirar; ATIVO só enfileira com orçamento de despachos inteiro positivo (sem orçamento, nada). Payload só com request_id (conteúdo vem do banco após autenticar); nome de tarefa sha256 por pedido+tentativa. Elegibilidade espelha assumir_pedido (transição válida para RESERVADO, lease expirada, retentativa só após proximo_tentativa_em). Lote deduplica request_id e consome orçamento por ENFILEIRAR. Sem I/O, sem Cloud Tasks."
estado: validado
inicio: "2026-10-27T20:00:00Z"
fim: "2026-10-27T20:40:00Z"
decisoes:
  - id: p08-sub5-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela da linha de autonomia no disparo das 17h BRT."
  - id: p08-sub5-nome-reutilizado
    motivo: "Achado do Codex (P2): RESERVADO->PENDENTE não incrementa tentativas, então o nome se repetiria e o Cloud Tasks recusa nomes de tarefas já executadas por horas (ALREADY_EXISTS), deixando o pedido sem tarefa. Corrigido: o nome inclui a geração da lease (monotônica, cresce a cada reserva). ALREADY_EXISTS passa a significar duplicata real."
  - id: p08-sub5-arquivo
    motivo: "execucao.md no limite de ~50KB: bloco P08 sub 3 arquivado em execucao-archive-p08sub3.md."
testes:
  resultados:
    - "functions/ completo ANTES 4847 OK (diário, P08 sub 4); DEPOIS 4862 OK (+15 em test_autonomy_dispatcher, incluindo o caso da geração no nome)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): 3 achados reais (status str crua ignorava backoff por usar 'is'; tentativas não-inteira gerava nome inválido; pedido repetido no lote gastava orçamento duas vezes) -> corrigidos e cobertos por teste. Rodada 2 sobre a correção: não achou nada (só desvio cosmético: motivo duplicado_no_lote em modo OFF, ação igual). Codex na PR: 1 achado P2 (nome reutilizado após liberar reserva) -> corrigido com a geração da lease no nome e coberto por teste; mudança de uma linha, sem nova rodada."
pendencias:
  - "P08: wiring (worker HTTP autenticado, Cloud Tasks real tratando ALREADY_EXISTS como duplicata, reserva/lease via autonomy.execution com CAS aplicando a DecisaoContinuacao, cliente Claude real consumindo ConfigModelos, cache de prompt (passo 9), leitura da flag do modo e do orçamento de despachos)."
```
