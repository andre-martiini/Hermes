# Arquivo: bloco "P08 sub-entrega 13/N" movido de execucao.md em 2026-10-30.

---

```yaml
pacote: "P08 sub-entrega 13/N -- sweep persistido de um pedido (autonomy/sweep_persistido.py, passo 4, wiring de persistência): decidir_varredura (pura) escolhe lease_vencida / retentativa_promovida / espera_vencida pelo status e varrer_pedido(db, request_id, agora) grava via atualizar_pedido (agora resolvido uma vez fora da transação; nada a varrer = nada gravado; diagnóstico devolvido é o da gravação que valeu). Estado incoerente (RESERVADO/EM_ANDAMENTO sem lease, retentativa sem horário, espera/verificação sem lease) sobe ValueError sem gravar. Nada chama o módulo em produção (shadow/off)."
estado: validado
inicio: "2026-10-30T10:50:00Z"
fim: "2026-10-30T11:25:00Z"
decisoes:
  - id: p08-sub13-triagem
    motivo: "PRs abertas: #565 (email/melhorias), #561 (finanças, muda saldo) e #556 (excluir_entrada_diario, apaga dados, pede aval do André): outra linha, nenhuma tocada. Nenhuma PR da autonomia pendente nem execução paralela."
  - id: p08-sub13-arquivo
    motivo: "execucao.md acima de ~50KB: bloco P08 sub 10 arquivado em execucao-archive-p08sub10.md."
  - id: p08-sub13-sem-lease
    motivo: "Espera/verificação SEM lease continua ValueError (contrato validado de varrer_espera_vencida, com teste próprio); não alterado aqui. Fixado por teste em sweep_persistido. Nada no domínio hoje cria AGUARDANDO_EXTERNO sem lease; decidir no wiring se o criador deve sempre manter lease."
  - id: p08-sub13-escopo
    motivo: "Fora de escopo: listar pedidos candidatos (consulta status+lease), persistir a fila de diagnóstico, agendamento do sweep."
testes:
  resultados:
    - "functions/ completo ANTES 4991 OK (diário, P08 sub 12); DEPOIS 4999 OK (suíte completa; 8 testes novos em test_autonomy_sweep_persistido, depois +1 do achado: 9 novos, rodados com test_autonomy_sweep: 38 OK)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): 1 achado de confiança média -- espera/verificação sem lease levanta ValueError a cada passada. Decisão: é o contrato validado do sweep puro (não alterado); fixado por teste e registrado como pendência do wiring. Limites, fuso, não-escrita e diagnóstico verificados sem bug. Sem rodada 2: nenhuma mudança de código após a rodada (só teste)."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real, listagem de candidatos + persistência da fila de diagnóstico ao redor de varrer_pedido, usar atualizar_pedido com decidir_continuacao + aplicar_decisao_continuacao, acordar_espera_externa e reconciliar_resultado_desconhecido persistindo também o run antigo, FALHA_FINAL por reconciliação, AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), espera sem lease (decidir se o criador sempre mantém lease), cliente Claude real com ConfigModelos, cache de prompt, flag do modo e orçamento de despachos, IAM mínimo)."
```
