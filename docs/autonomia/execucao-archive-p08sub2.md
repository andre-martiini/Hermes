---

```yaml
pacote: "P08 sub-entrega 2/N -- decisão de continuação do runner (autonomy/runner_continuacao.py, passos 4-7): função pura decidir_continuacao traduz o ResultadoRunner no próximo estado do pedido a partir de EM_ANDAMENTO. CONCLUIDO -> VERIFICANDO (nunca fecha direto); AGUARDANDO -> AGUARDANDO_EXTERNO sem continuação imediata (horário sem fuso/tipo errado vira espera sem horário, com UTC); PAUSADO_LIMITE -> RETENTATIVA_AGENDADA em 60 s com teto de 20 pausas (não gasta tentativa); RETENTAR -> backoff de requests.calcular_backoff_segundos até DEFAULT_MAX_TENTATIVAS, depois FALHA_FINAL; FALHA/entrada inválida -> FALHA_FINAL. Soma de tempo em UTC (DST). Sem I/O, sem Cloud Tasks (shadow/off, passo 11)."
estado: validado
inicio: "2026-10-27T10:50:00Z"
fim: "2026-10-27T11:20:00Z"
decisoes:
  - id: p08-sub2-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela da linha de autonomia no disparo das 8h BRT."
  - id: p08-sub2-verificar
    motivo: "Sucesso do runner vai para VERIFICANDO (passo 4, 'verificar'); só o verificador conclui o pedido."
  - id: p08-sub2-pausas
    motivo: "Pausa por limite não consome tentativa de erro, mas tem teto próprio (20) para não girar para sempre."
  - id: p08-sub2-arquivo
    motivo: "execucao.md acima de ~50KB: bloco P07 revisão final (2ª) arquivado em execucao-archive-p07final2.md."
testes:
  resultados:
    - "functions/ completo ANTES 4696 OK (diário, P08 sub 1; main 8cfa553); DEPOIS 4713 OK (+17 em test_autonomy_runner_continuacao)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): 3 achados (soma de timedelta sem normalizar para UTC com fuso de DST; OverflowError em agora no limite do calendário; AGUARDANDO sem espera) -> corrigidos. Rodada 2 sobre a correção: 2 achados (acordar_em de tipo errado vazava como continuar_em; OverflowError na normalização fora do try) -> corrigidos. Sem rodada 3 (correções de uma linha, cobertas por teste, lógica pura)."
pendencias:
  - "P08: wiring (worker HTTP autenticado, Cloud Tasks, reserva/lease via autonomy.execution aplicando a DecisaoContinuacao, cliente Claude real com tarifas versionadas e cache de prompt, adaptador Cowork, dispatcher shadow/off). P07: decisão do André sobre o sinal de substituição."
```

