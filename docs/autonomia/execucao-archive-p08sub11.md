```yaml
pacote: "P08 sub-entrega 11/N -- serialização do pedido durável (autonomy/pedido_serializacao.py, passo 4, base do wiring de persistência): funções puras pedido_para_dict / pedido_de_dict. Documento só com tipos JSON/Firestore (instantes ISO UTC), leitura estrita (ValueError para chave ausente/extra, bool como int, instante sem fuso, status desconhecido, chave não-str aninhada, tupla, vazios em lease/ledger, sequencia de checkpoint não crescente, resultado sem resultado_registrado_em, lease.generation<1, run de outro pedido ou ativo divergente da lease, limites do domínio como checkpoint grande). pedido_para_dict relê o que produz e recusa o que a leitura recusaria. NaN no resultado faz round-trip. Sem I/O (shadow/off)."
estado: validado
inicio: "2026-10-29T13:52:00Z"
fim: "2026-10-29T15:10:00Z"
decisoes:
  - id: p08-sub11-triagem
    motivo: "PRs abertas: #561 (melhorias, atualizada há <60 min = execução paralela) e #556 (excluir_entrada_diario, outra linha, apaga dados e pede aval do André): nenhuma tocada. Nenhuma PR da autonomia pendente."
  - id: p08-sub11-arquivo
    motivo: "execucao.md no limite de ~50KB: bloco P08 sub 8 arquivado em execucao-archive-p08sub8.md."
  - id: p08-sub11-escopo
    motivo: "Fora de escopo, deliberado: limites do Firestore (int64, array em array, surrogates, 1MiB), ZoneInfo em hora ambígua (PEP 495), espaços nas pontas (normalizados pelos construtores), limites de quantidade/bytes de checkpoints na leitura, e checkpoint_dados não-dict aceito pelo domínio (a escrita agora recusa). Checagem finalizado_em >= iniciado_em removida: o domínio aceita agora anterior ao da reserva e a escrita não pode recusar o que ele aceitou."
testes:
  resultados:
    - "functions/ completo ANTES 4950 OK (diário, P08 sub 10); DEPOIS 4976 OK (suíte completa, antes da remoção da checagem finalizado_em; depois dela, rodados de novo os 144 testes de serializacao/execution/runner_aplicacao/sweep: OK). O restante vem de merges de outras linhas."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): achados reais corrigidos -- leitura levantava CheckpointMuitoGrande/RecursionError em vez de ValueError, NaN gravava e não lia, chave não-str aninhada perdia dado, instante extremo estourava OverflowError. Rodada 2: fuzz de 1386 casos sem exceção fora de ValueError; escrita passou a reler o documento (checkpoint não-dict), coerência ledger/lease. Rodada 3: vazios em lease_token (permitia passar no fencing) e coerência do run corrigidos. Rodada 4 (focada nas checagens novas): 1 falso positivo real -- finalizado_em < iniciado_em vindo de relógio atrasado era recusado na escrita; checagem removida e coberta por teste. Sem rodada adicional após a remoção (só tira uma checagem). Codex na PR #562: 1 achado P2 real -- run ativo com lease null era aceito (pedido encalhado, fencing falha sem lease); corrigido e coberto por teste. Rodada 5 (focada na correção do Codex, agente sem contexto, somente leitura): não achei nada -- nenhum fluxo do domínio produz run ativo com lease None."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real, repositório Firestore com CAS usando pedido_para_dict/pedido_de_dict e chamando decidir_continuacao + aplicar_decisao_continuacao, sweep, acordar_espera_externa e reconciliar_resultado_desconhecido persistindo também o run antigo, FALHA_FINAL por reconciliação, AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), cliente Claude real com ConfigModelos, cache de prompt, flag do modo e orçamento de despachos, IAM mínimo)."
```
