# Arquivo: P07 sub-entrega 4/N (movida de execucao.md em 2026-10-23, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 4/N -- passo 8 (parte pura): functions/autonomy/atencao_compromisso.py. montar_item_atencao(chave, versao, decisao, agora) converte a decisão de followup_guard em item de atenção endereçado por chave+versão (id <chave>__v<N>) com próxima avaliação (ENVIAR=agora, ADIAR=+4h, SUPRIMIR=nenhuma/encerrado). deve_gravar(existente, novo) dá idempotência: não regride versão, não aceita avaliação mais antiga, não reabre item terminal (encerrado/enviado), permite aberto->enviado e renova o agendamento quando a mesma decisão volta com proxima_avaliacao maior, recusa itens malformados/incoerentes. marcar_enviado só aceita item aberto/ENVIAR e não retrocede avaliado_em. Datas extremas e entradas ruins viram ValueError. Sem I/O e sem wiring; fila antiga e A06 não alteradas."
estado: validado
inicio: "2026-10-22T10:50:00Z"
fim: "2026-10-22T11:20:00Z"
decisoes:
  - id: p07-sub4-estado-enviado
    motivo: "Revisor apontou que ENVIAR repetido ficaria elegível para sempre sem estado terminal; adicionado estado 'enviado' (marcar_enviado) e coerência estado/ação/proxima validada."
  - id: p07-sub4-arquivo-execucao
    motivo: "execucao.md arquivado (bloco P07 sub 1 -> execucao-archive-p07sub1.md)."
  - id: p07-sub4-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela no início do disparo de 8h BRT."
testes:
  resultados:
    - "functions/ completo ANTES 4504 OK (head de main, conforme P07 sub 3); test_autonomy_atencao_compromisso 10 OK (novo arquivo); DEPOIS 4514 OK (219s, head final)."
revisao_adversarial:
  - "Rodada 1: ADIAR repetido não renovava proxima_avaliacao, avaliação antiga sobrescrevia nova, validação fraca do existente, chave com '/', exceções fora de ValueError. Corrigido. Rodada 2: transição aberto->enviado recusada, OverflowError em agora, itens incoerentes aceitos. Corrigido. Rodada 3: marcar_enviado com agora anterior ao avaliado_em. Corrigido (max). Rodada 4: OverflowError em avaliado_em extremo. Corrigido em _validar. Rodada 5: não achou nada."
pendencias:
  - "P07 passos 2 (extração estruturada, sombra), 3, 5; wiring em atencao_whatsapp somente com flag/sombra."
```
