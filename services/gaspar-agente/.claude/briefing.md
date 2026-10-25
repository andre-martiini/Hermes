Briefing da manhã (todos os dias, às 05:00). Veio da tarefa agendada "Briefing da manhã do Gaspar" do app desktop, que foi desativada quando o agente passou a rodar 24 h.

COMO FAZER: o levantamento tem dezenas de leituras. Para elas não ficarem no seu contexto o dia todo, chame a tool `Agent` (subagent_type `general-purpose`) com o bloco PROMPT DO SUBAGENTE abaixo, inteiro. Ele devolve o texto pronto. Você manda pelo `reply` do Telegram em texto simples (`format` padrão), numa mensagem só (o plugin divide se passar do limite), e anota no registro do dia que o briefing saiu. Se o subagente falhar, mande um bom-dia curto com no máximo 3 pontos e diga que o briefing completo falhou.

Mande ao André só a parte antes de "=== TEXTOS ==="; guarde os textos para quando ele escolher o item. Logo depois do briefing, se houver a seção EU FAÇO, mande a proposta com `enviar_opcoes` (formato do CLAUDE.md, opções "Sim, faz", "Alterar", "Não").

Quando o André responder com os números ("1 cobra, 3 reagenda sexta, 5 já resolvi"), execute o que não envia nada a terceiros. Para cada item que manda mensagem, mostre o texto exato e o destinatário com `enviar_opcoes` ("Envia", "Alterar", "Não"): só o "Envia" autoriza. Depois de cada gravação, confirme pelo resultado da ferramenta; se der errado, diga qual item e por quê. Nunca pague, assine ou aceite termos em nome dele.

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

2. MONTE O BRIEFING CURTO (diretriz do André, 25/10: cabe numa tela de celular, até uns 1.200 caracteres). Texto simples para Telegram: sem asteriscos, sem tabelas, títulos em MAIÚSCULAS com o emoji indicado, e uma linha em branco entre as seções. Cada item é UMA linha. Corte tudo que não pede nada dele hoje.

Bom dia, André — <dia da semana>, <dd/mm>

🎯 HOJE
No máximo 3 prioridades, uma linha cada: "<título> — <próximo passo>". O porquê só se não for óbvio, em 3 a 5 palavras.

📅 AGENDA
Uma linha com os horários de hoje. Uma linha com até 3 itens dos próximos dias que pedem preparo antes (o resto ele vê na agenda).

✋ DECIDIR
Lista numerada, no máximo 6 itens, só o que pede decisão ou ação dele: "<n>. <quem/assunto>, <situação em poucas palavras> → <proposta: cobrar segunda, responder, reagendar para X, marcar feito>". NÃO escreva aqui o texto para terceiros; ele sai quando o André escolher o item. Fora da lista: tudo que é "deixar como está", depende de outro item ou de terceiro, ou já foi decidido. Se houver mais de 6, junte o resto numa linha "e mais N menores (peça 'resto')".

🤖 EU FAÇO
Uma linha, a melhor proposta do que o agente consegue adiantar sozinho (rascunho, evento, pesquisa e resumo, documento no Drive, etapas, conversa no Modo Objetivo): "<ação>: eu <o que faço e o que ele recebe>". Nada que pague, assine, aceite termos ou decida por ele. Sem proposta boa, omita.

⚠️ ATENÇÃO
Só prazo que vence em até 3 dias ou dado que parece errado. No máximo 2 linhas. O que não deu para ler vai numa linha final curta ("Não li: SIGFAPES, e-mail").

Não inclua: o resto das ações do dia, rotinas pessoais (check-ins, pesagem, refeições), itens repetidos.

3. FECHE COM uma linha: "Responda com os números (ex.: '1 cobra, 3 reagenda sexta')."

Devolva também, DEPOIS do briefing e separado pela linha "=== TEXTOS ===", o texto exato proposto para cada item do DECIDIR que envolve mensagem a terceiro (número do item e texto; primeira pessoa, como se fosse o André; nunca sugerir ligação ou videochamada; a esposa dele é Alnínive, Amor, Gatinha ou Fofinha, nunca "Tininha"). Essa parte não vai para o André.
=== FIM DO PROMPT DO SUBAGENTE ===
