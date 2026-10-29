```yaml
pacote: "P08 sub-entrega 7/N -- aplicação da decisão de continuação (autonomy/runner_aplicacao.py, passos 4-7): função pura aplicar_decisao_continuacao(pedido, lease_token, generation, decisao, agora). Fencing + transição validada a partir de EM_ANDAMENTO. VERIFICANDO/AGUARDANDO_EXTERNO mantêm lease e run (espera guarda condição e horário); RETENTATIVA_AGENDADA fecha o run como falha, libera a lease (expira em agora) e grava contadores/proximo_tentativa_em; FALHA_FINAL sela o ledger via registrar_resultado_observado (sem ledger, só fecha o run). Contadores nunca regridem. PedidoDuravel ganha pausas e condicao_espera (default, compatível); registrar_progresso limpa condicao_espera/proximo_tentativa_em ao retomar. Sem I/O (shadow/off)."
estado: validado
inicio: "2026-10-28T13:54:00Z"
fim: "2026-10-28T14:25:00Z"
decisoes:
  - id: p08-sub7-triagem
    motivo: "Única PR aberta (#547, melhorias) é de outra linha e estava ativa há 2 min: não tocada. Nenhuma PR da autonomia pendente."
  - id: p08-sub7-arquivo
    motivo: "execucao.md no limite de ~50KB: bloco P08 sub 1 arquivado em execucao-archive-p08sub1.md."
testes:
  resultados:
    - "functions/ completo ANTES 4872 OK (diário, P08 sub 6); DEPOIS 4890 OK (+18 em test_autonomy_runner_aplicacao)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): 4 achados (status como string crua contornava a máquina de estados; contadores podiam regredir; continuar_em não-datetime dava AttributeError; condicao_espera obsoleta após retomar) -> corrigidos e cobertos por teste; lease vencida em AGUARDANDO_EXTERNO sem saída no sweep é lacuna já documentada em autonomy.sweep, registrada em pendencias. Rodada 2: sem bug alcançável; 1 resíduo menor (proximo_tentativa_em após retomar) corrigido em uma linha."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real tratando ALREADY_EXISTS, persistência/CAS chamando decidir_continuacao + aplicar_decisao_continuacao, renovar lease ao acordar de AGUARDANDO_EXTERNO e tratar vencimento de lease em VERIFICANDO/AGUARDANDO_* no sweep, cliente Claude real com ConfigModelos, cache de prompt, flag do modo e orçamento de despachos, IAM mínimo)."
```
