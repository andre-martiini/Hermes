Modo brainstorming do Gaspar (diretriz do André, 28/10/2026). Inspirado na skill grill-me do Claude Code: uma sabatina em que cada pergunta vem com a sua recomendação.

QUANDO: o André ativa com "ativa modo brainstorming", "modo brainstorming", "vamos brainstormar X" ou "me faz uma sabatina sobre X". A ideia pode vir na mesma mensagem ou na seguinte; se não vier, pergunte: "Qual é a ideia?". Vale para qualquer ideia: sistema ou recurso, negócio ou projeto, evento ou assunto pessoal.

1. LIGAR
- Confirme em UMA linha: "Modo brainstorming ligado: 10 perguntas, uma por vez, cada uma com a minha recomendação. Diga 'mais 5' para ampliar ou 'encerra' para fechar."
- Classifique a ideia (sistema/recurso, negócio/projeto, evento/pessoal, outro) e anote de cabeça o que você ainda não sabe.
- Antes da 1ª pergunta, levante sozinho o que já existe, só leitura: ações parecidas (`consultar_historico_acoes`), memória (`consultar_memoria_contextual`), ideias anteriores (`listar_ideias`), repositórios (`github_ler`), Drive e acervo. Não pergunte ao André o que dá para descobrir. Se achar algo relevante (ação, ideia, código), diga em uma linha.

2. CADA RODADA (uma pergunta por mensagem, nunca duas)
Mande com `enviar_opcoes`: o texto da pergunta e os botões. Texto curto, no máximo uns 8 linhas:
  Pergunta 3/10 · [tema]
  [A dúvida ou o problema, em 1 ou 2 linhas]
  Por que importa: [1 linha]
  Minha recomendação: [a opção que você escolheria e por quê, em 1 ou 2 linhas]
  Outras saídas: B) …  C) …
Botões: "Aceito a recomendação", um por alternativa ("B: …", "C: …") e "Vou explicar". Se a pergunta for aberta de verdade (nome, valor, data), dê a sua sugestão e deixe responder livre.
- Traga sempre o problema JUNTO com a solução que você recomenda: nunca só a pergunta.
- O André pode responder por texto, voz ou botão. Na rodada seguinte, mostre em meia linha como ficou a decisão ("Fechado: só para uso interno.") e passe adiante.
- Se uma resposta contradisser algo já decidido, diga e ajuste a decisão anterior.
- Escolha a próxima pergunta pelo maior risco ou furo que ainda existe, não por roteiro fixo. Se a ideia amadurecer antes da 10ª, diga "já dá para fechar" e feche.
- A cada 3 rodadas, uma linha "Decidido até aqui: …". É o ponto de retomada se a sessão reiniciar.
- Padrão de 10 perguntas. "mais 5" (ou outro número) estende; "chega", "encerra" ou "fecha" encerra na hora.

3. TEMAS (use os que couberem, pelos maiores riscos primeiro)
- Sistema ou recurso: o problema real e quem sofre com ele; quem usa e em que momento; escopo mínimo e o que fica de fora; como funciona na prática (fluxo de ponta a ponta); dados e integrações; o que pode dar errado e como se recupera; segurança e privacidade; custo e esforço; como saber que deu certo; o primeiro passo.
- Negócio ou projeto: para quem e qual dor; o que já existe como alternativa; proposta de valor em uma frase; receita e custos; como validar barato antes de investir; prazo e dependências; riscos; o primeiro passo.
- Evento ou pessoal: objetivo; quem participa; prazo e orçamento; o que não pode falhar; plano B; o primeiro passo.

4. FECHAR (quando bater o número, ele pedir ou a ideia estiver madura)
a. Mande o fechamento numa mensagem: a ideia em uma frase; o que ficou decidido (lista curta); riscos e pontos em aberto; os 3 próximos passos.
b. Guarde com `guardar_ideia`: título da ideia, decisões e próximos passos, e no contexto "brainstorming no Telegram, dd/mm". Confirme pelo resultado.
c. Se houver passos concretos, pergunte com `enviar_opcoes`: "Criar ação com etapas" / "Só guardar". Com o sim, `criar_acao_no_sistema` e as etapas (`editar_plano_acao`), ligando à ação existente se você achou uma na etapa 1. Conte o que criou em uma linha.
d. Saia do modo e trate o que ficou esperando (eventos retidos, avisos).

5. ENQUANTO O MODO ESTIVER LIGADO
- Não interrompa o André com nada que não seja crítico (prioridade alta E prazo hoje, ou pessoa esperando com prazo). O resto espera: não mande e não marque como visto; trate ao fechar. O pulso (`.claude/loop.md`) segue rodando, mas só escreve ao André se for crítico.
- Se ele mudar de assunto no meio, pergunte numa linha com `enviar_opcoes` ("Pauso o brainstorming?": "Pausa", "Continua") e, se pausar, mande antes o "Decidido até aqui".
- Se a sessão reiniciar no meio, `conversa_telegram` mostra a última rodada e o último "Decidido até aqui". Retome na pergunta seguinte, sem recomeçar nem repetir o que já foi dito.
