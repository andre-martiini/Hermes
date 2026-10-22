Pulso do Gaspar (marco 1: sem canal de eventos, este pulso faz o papel dele).

1. `consultar_pedidos_agente`: trate os pendentes (ex.: consolidar_audio → `consolidar_whatsapp` + `registrar_no_diario` + `concluir_pedido_agente`).
2. `obter_fila_atencao(estado=aberto)`: para cada item que você ainda não tratou hoje, decida tratar, avisar o André ou esperar.
3. `listar_conversas_whatsapp`: olhe só as conversas com `ultima_atividade` depois do pulso anterior; se a última mensagem não for do André, leia com `ler_mensagens_whatsapp` e decida como na seção Eventos do CLAUDE.md.
4. Respeite as janelas protegidas. Se nada mudou, não escreva nada para o André.
5. No fim, atualize `registrar_execucao_agente` (run_id `gaspar-agente:AAAA-MM-DD`, origem `autonoma`) e os contadores do dia. A gravação substitui a anterior: o `resumo` cobre o DIA inteiro (contagens e ids dos itens já avisados, nunca texto de mensagem).
