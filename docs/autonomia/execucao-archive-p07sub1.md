# Arquivo: P07 sub-entrega 1/N (movida de execucao.md em 2026-10-22, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 1/N -- passos 1, 2 e 4 (parte pura): functions/autonomy/commitments.py. Corpus sintético em português (promessa, intenção vaga, pergunta, cancelamento, entrega parcial, não relacionada + casos adversariais), classificar_mensagem (seleção barata, ordem de cautela: negação/condição/dúvida vencem promessa; pergunta com promessa nunca firme), firmeza por LISTA BRANCA (_firme_estrito) além do léxico de hedge, extrair_prazo_expresso (natureza 'expresso', data só quando inequívoca; sem data para prazo relativo/múltiplo/negado/data do objeto), chave_compromisso (vários por chat), avaliar() com precisão/revocação. Sem I/O e sem wiring: atencao_whatsapp.mensagem_cumpre_promessa (A06, fechamento por comprimento) NÃO foi alterado."
estado: validado
inicio: "2026-10-21T13:50:00Z"
fim: "2026-10-21T14:30:00Z"
decisoes:
  - id: p07-sub1-precisao-sobre-revocacao
    motivo: "Lexico de hedge é infinito (6 rodadas adversariais acharam variações novas a cada vez). Decisão estrutural: promessa só é firme (incerta=False) se passar uma lista branca estrita (cláusula curta, demais cláusulas neutras, sem palavra de conteúdo antes da frase de promessa); o resto vira incerta. Perde recall de propósito -- alinhado ao aceite do plano (incertos ficam pendentes, não são encerrados)."
  - id: p07-sub1-so-selecao
    motivo: "Esta sub-entrega é só seleção/vocabulário; extração estruturada com evidências (passo 2 LLM), avaliador de cumprimento e wiring ficam para as próximas. Consumidor deve checar classe==promessa E incerta==False."
  - id: p07-sub1-merge-pr480
    motivo: "PR #480 (aberta 11:22Z, sem execução paralela no disparo de 14h): main mesclado, rodadas 7-8, correções, suíte e merge pela regra de autoridade plena; módulo puro sem wiring, reversível."
  - id: p07-sub1-triagem
    motivo: "Nenhuma PR aberta no início do disparo. execucao.md arquivado (blocos P06 sub 10 e 11 -> execucao-archive-p06sub10-sub11.md)."
testes:
  resultados:
    - "functions/ completo ANTES 4427 OK (head de main); test_autonomy_commitments 35 OK (novo arquivo); DEPOIS 4462 OK (243s) após correções do Codex; no disparo de 14h: com main mesclado 4465 OK; head final 4467 OK (238s), test_autonomy_commitments 37 OK."
revisao_adversarial:
  - "Rodadas 1-5 (agentes sem contexto): reais corrigidos -- negação ampla/abreviada, condicionais e dúvidas, 'pode deixar' fora de contexto, pergunta com promessa, regressões de falso hedge, datas inventadas (dd/mm do objeto, 29/02, ano de 3 dígitos, data passada, prazos relativos/múltiplos), colisão de chave, hoje inválido. Rodada 5 mostrou que o design por lista negra não fecha; trocado por lista branca de firmeza. Rodada 6: achou que a lista branca ainda aceita 1 palavra de conteúdo arbitrária ('Te envio hoje difícil'), entrega parcial/terceiro sem marcador e tom irônico; corrigidos: conteúdo <=1, pontuação/emoji/'?!' -> incerta, 'dia N' sem mês -> sem data, hora validada. Codex na PR #480 (3 P2 reais, corrigidos): prazo 'na/no <dia>' em frase curta (<=5 palavras), pergunta com negação não é cancelamento firme, um/uma aceitos só antes de objeto documental (rodada adversarial focada achou 'um beijo/um dia desses' na 1ª versão, corrigido). Rodadas 7-8 (disparo de 21/10 14h, agentes sem contexto): reais corrigidos -- cancelamento firme virava certeza em negação do gatilho ("não desisti"), adiamento ("não posso hoje, amanhã envio"), sujeito terceiro, objeto parcial/prazo ("a tempo", "o anexo") e verbos genéricos; agora CANCELAMENTO só é incerta=False se a mensagem INTEIRA casa uma fórmula curta ancorada de desistência (_CANCEL_FIRME: "não vou mais enviar", "esquece isso", "pode deixar quieto"...), senão incerta=True; prazo: mesmo dia da semana sem data, fração d/m + plural não é data, duas datas d/m = múltiplo. Limite estrutural remanescente (hedge por gíria de 1 palavra) NÃO fechável por regex; aceito por design (incerta=False = nenhum hedge detectado; módulo sem wiring). A lista branca de cancelamento foi estreitada até restar só fórmula sem referente variável."
pendencias:
  - "Decidido no disparo de 21/10 14h: módulo mesclado como seletor puro sem wiring; incerta=False = nenhum hedge detectado, a firmeza real virá da extração estruturada (LLM, sombra) + política."
  - "P07 passos 2 (extração estruturada com evidências, modo sombra), 3, 5, 6, 7, 8; wiring em atencao_whatsapp somente com flag/sombra."
```
