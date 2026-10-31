# Arquivo: bloco "P08 sub-entrega 14/N" movido de execucao.md em 2026-10-31.

---

```yaml
pacote: "P08 sub-entrega 14/N -- sweep em lote (autonomy/sweep_lote.py, passo 4, wiring de persistência): listar_candidatos (consulta where pedido.status in [reservado, em_andamento, retentativa_agendada, aguardando_externo, verificando] + order_by __name__) e varrer_candidatos(db, agora, limite, max_tentativas, max_paginas) paginando por cursor (start_after) e chamando varrer_pedido por pedido, com isolamento de falhas (erro vira item de erros; pedido apagado no meio é ignorado). ResultadoLote: candidatos, truncado, varridos, diagnosticos, erros. Nada chama o módulo em produção (shadow/off)."
estado: validado
inicio: "2026-10-30T14:04:00Z"
fim: "2026-10-30T14:45:00Z"
decisoes:
  - id: p08-sub14-triagem
    motivo: "PRs abertas: #565 (email), #561 (finanças, muda saldo) e #556 (excluir_entrada_diario, apaga dados, pede aval do André): outra linha, nenhuma tocada. Nenhuma PR da autonomia pendente nem execução paralela."
  - id: p08-sub14-arquivo
    motivo: "execucao.md acima de ~50KB: bloco P08 sub 11 arquivado em execucao-archive-p08sub11.md."
  - id: p08-sub14-paginacao
    motivo: "Um limit sem ordenação/cursor devolveria sempre a mesma página (pedidos com lease válida ou com erro permanente ocupariam as vagas e os vencidos atrás nunca seriam varridos). Paginação por cursor de id até esgotar ou max_paginas (padrão 10 x 100); truncado=True se o teto foi atingido com a última página cheia (falso positivo aceito quando o total é exatamente limite*max_paginas; docstring explícita). Codex (PR #568) apontou que, truncado, toda passada relia o mesmo prefixo: ResultadoLote.proximo_cursor + parâmetro apos_id permitem continuar dali (o agendamento do sweep no wiring deve repassá-lo)."
  - id: p08-sub14-max-tentativas
    motivo: "Codex: max_tentativas 0/negativo/bool faria todo candidato vencido virar CANCELADO/FALHA_FINAL de imediato; agora validado como inteiro >=1 antes do loop (efeito: não há como desligar retentativas com 0 neste módulo; o default é 3)."
  - id: p08-sub14-escopo
    motivo: "Fora de escopo: persistir a fila de diagnóstico, agendamento periódico do sweep, observabilidade de documentos cujo pedido.status é ausente/inválido (não casam com a consulta), índice do Firestore real (campo único + __name__, não verificado contra servidor real)."
testes:
  resultados:
    - "functions/ completo ANTES 4999 OK (diário, P08 sub 13); DEPOIS 5008 OK (8 testes novos em test_autonomy_sweep_lote; o restante vem de merges de outras linhas)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): 1 achado real -- starvation por limit sem ordenação/cursor, mais falta de sinal de saturação; corrigido (paginação por cursor + truncado) e coberto por teste. Rodada 2 (focada na correção): 1 achado -- truncado falso positivo quando o total é exatamente limite*max_paginas; aceito e documentado (só docstring), sem rodada adicional. Codex na PR #568: 2 achados P2 reais (cursor de continuação após passada truncada; validação de max_tentativas), corrigidos e cobertos por teste. Rodada 3 (focada na correção do Codex, agente sem contexto, somente leitura): não achei nada -- start_after({"__name__": id}) conferido contra o cliente firestore instalado. Paginação com mudança de status durante a passada, doc apagado, query contra o cliente firestore instalado e validação de parâmetros verificados sem bug. Não verificado contra Firestore real."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real, persistência da fila de diagnóstico ao redor de varrer_candidatos e agendamento do sweep, usar atualizar_pedido com decidir_continuacao + aplicar_decisao_continuacao, acordar_espera_externa e reconciliar_resultado_desconhecido persistindo também o run antigo, FALHA_FINAL por reconciliação, AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), espera sem lease, cliente Claude real com ConfigModelos, cache de prompt, flag do modo e orçamento de despachos, IAM mínimo)."
```

