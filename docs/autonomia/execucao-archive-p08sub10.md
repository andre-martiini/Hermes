```yaml
pacote: "P08 sub-entrega 10/N -- reconciliação de RESULTADO_DESCONHECIDO (autonomy/runner_aplicacao.py): função pura reconciliar_resultado_desconhecido(pedido, efeito_ocorreu, agora, ...). Exige lease anterior vencida. efeito_ocorreu=True -> VERIFICANDO com lease geração+1 e run novo (nunca retenta: duplicaria efeito); False -> RETENTATIVA_AGENDADA com tentativas+1, continuar_em futuro obrigatório e recusa acima de DEFAULT_MAX_TENTATIVAS. Devolve (pedido, run_antigo) para o wiring persistir. Sem I/O (shadow/off)."
estado: validado
inicio: "2026-10-29T10:48:00Z"
fim: "2026-10-29T11:10:00Z"
decisoes:
  - id: p08-sub10-triagem
    motivo: "Única PR aberta (#556, excluir_entrada_diario, outra linha) apaga dados e a própria descrição pede aval do André: não tocada. Nenhuma PR da autonomia pendente."
  - id: p08-sub10-arquivo
    motivo: "execucao.md no limite de ~50KB: bloco P08 sub 7 arquivado em execucao-archive-p08sub7.md."
  - id: p08-sub10-escopo
    motivo: "FALHA_FINAL por reconciliação fica fora (selar o ledger exige fencing com lease válida); a evidência efeito_ocorreu é responsabilidade do chamador/wiring."
testes:
  resultados:
    - "functions/ completo ANTES 4912 OK (diário, P08 sub 9); DEPOIS 4950 OK (+8 em test_autonomy_runner_aplicacao; o restante vem de merges de outras linhas)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): 1 achado real -- retentativa por reconciliação contornava o teto de tentativas; corrigido (ValueError acima de DEFAULT_MAX_TENTATIVAS, também recusa tentativas bool) e coberto por teste. Rodada 2 (focada na correção): não achei nada."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real, persistência/CAS chamando decidir_continuacao + aplicar_decisao_continuacao, sweep, acordar_espera_externa e reconciliar_resultado_desconhecido persistindo também o run antigo, FALHA_FINAL por reconciliação, AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), cliente Claude real com ConfigModelos, cache de prompt, flag do modo e orçamento de despachos, IAM mínimo)."
```
