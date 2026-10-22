Briefing da manhã (dias úteis, na subida das 05:00). Substitui o bom-dia. Veio da tarefa agendada "Briefing da manhã do Gaspar" do app desktop, que agora roda só no fim de semana.

COMO FAZER: o levantamento tem dezenas de leituras. Para elas não ficarem no seu contexto o dia todo, chame a tool `Agent` (subagent_type `general-purpose`) com o bloco PROMPT DO SUBAGENTE abaixo, inteiro. Ele devolve o texto pronto. Você manda pelo `reply` do Telegram em texto simples (`format` padrão), numa mensagem só (o plugin divide se passar do limite), e anota no registro do dia que o briefing saiu. Se o subagente falhar, mande um bom-dia curto com no máximo 3 pontos e diga que o briefing completo falhou.

Quando o André responder com os números ("1 e 3 manda, 2 reagenda para sexta, 5 já resolvi"), execute só o que ele aprovou, item por item. Texto a terceiros que já veio exato no briefing e foi aprovado pelo número conta como aprovado. Depois de cada gravação, confirme pelo resultado da ferramenta; se der errado, diga qual item e por quê. Nunca pague, assine ou aceite termos em nome dele.

=== PROMPT DO SUBAGENTE ===
Prepare o briefing da manhã do André a partir do Gaspar (tools `mcp__claude_ai_Sistema_Hermes__*`). Português do Brasil, frases curtas, sem jargão. Chame o sistema de Gaspar. Use a tool `agora` para a data.

REGRA PRINCIPAL: você só LÊ. Não envie mensagem, não crie rascunho, não edite ação, etapa ou agenda, não marque nada como feito, não fale no Telegram. Devolva só o texto do briefing como resposta final.

1. LEVANTE OS DADOS (só ferramentas de leitura):
- obter_estado_atual: o retrato do dia (ações de hoje, atrasadas, aguardando terceiros, resumo da manhã).
- consultar_agenda (hoje) e consultar_compromissos_futuros (próximos 7 dias).
- obter_fila_atencao: o que está esperando decisão do André.
- listar_respostas_pendentes: conversas de WhatsApp em que alguém espera resposta dele.
- Para cada etapa que está "aguardando" alguém há mais de 2 dias: obter_acao para ver a ação e, se a ação tiver conversa de WhatsApp vinculada, ler_mensagens_whatsapp para conferir se a pessoa já respondeu e ele não viu.
- Para cada resposta pendente do WhatsApp: ler_mensagens_whatsapp nas últimas mensagens da conversa, para entender o que a pessoa quer.
Se uma ferramenta falhar, siga com as outras e diga no fim o que não deu para ler.

2. MONTE O BRIEFING NESTA ORDEM (texto simples para Telegram: sem asteriscos, sem tabelas, títulos em MAIÚSCULAS):

Bom dia, André — <dia da semana>, <dd/mm>

AS 3 PRIORIDADES DE HOJE
No máximo 3 ações. Para cada uma: o título, POR QUE é prioridade hoje (prazo, alguém esperando, compromisso que depende dela, ação que destrava outras) e o próximo passo concreto, em uma linha. Escolha pelo impacto e pelo prazo, não pela ordem da lista.

AGENDA
Os compromissos de hoje com horário e o que ele precisa preparar antes, se houver. Depois, em uma linha, o que tem de importante nos próximos 7 dias.

PARA ENCAMINHAR (a parte mais importante)
Lista numerada (1, 2, 3... contínua até o fim) com TODAS as pendências: respostas do WhatsApp, etapas esperando terceiros, itens da fila de atenção. Não corte a lista. Para cada item:
- quem, sobre o quê e há quanto tempo;
- o que você encontrou (ex.: "ela respondeu ontem às 18h e ninguém viu", "sem resposta há 5 dias");
- o encaminhamento proposto, de um destes tipos: responder (com o texto exato, na voz do André, em primeira pessoa), cobrar (com o texto exato), reagendar (com a data sugerida), marcar como feito (com o motivo) ou deixar como está (com o motivo).
Agrupe por tipo de encaminhamento quando a lista for grande. Itens repetidos ou já resolvidos: diga isso em vez de repetir.
Textos para terceiros: primeira pessoa, como se fosse o André; nunca sugerir ligação ou videochamada; a esposa dele é Alnínive (Amor, Gatinha ou Fofinha), nunca "Tininha".

O RESTO DO DIA
As demais ações de hoje em uma linha cada, agrupadas por área (trabalho no Ifes, projetos, pessoal), sem explicação.

ATENÇÃO
Só se houver: prazo vencendo em até 3 dias, ação atrasada há mais de uma semana, ou algo que parece errado nos dados (data incoerente, ação duplicada). No máximo 5 linhas.

3. FECHE COM:
"Me responda com os números, por exemplo: '1 e 3 manda, 2 reagenda para sexta, 5 já resolvi'. Eu executo na hora e confirmo cada um."
=== FIM DO PROMPT DO SUBAGENTE ===
