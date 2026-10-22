# Arquivo: P07 sub-entrega 2/N e 3/N (movidas de execucao.md em 2026-10-22, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 2/N -- passo 6 (parte pura): functions/autonomy/cumprimento.py. avaliar_cumprimento(promessa, mensagem, tem_midia, nome_anexo) -> cumprido/parcial/nao_cumpre/incerto. Gramática fechada (lista branca) em promessa, mensagem e nome do anexo: só 'cumprido' firme (incerta=False) se a mensagem é inteira marca de entrega + exatamente os objetos prometidos, a promessa é verbo de envio + objetos singulares + prazo simples, e, com mídia, o nome do anexo é só os objetos + extensão. Negação, pergunta, hedge, nova promessa, parcial, objeto diferente/incompleto, mídia sozinha, texto longo sobre outro assunto e marcas combinantes estranhas nunca fecham. Sem I/O e sem wiring; mensagem_cumpre_promessa (A06) NÃO alterada."
estado: validado
inicio: "2026-10-21T16:48:00Z"
fim: "2026-10-21T18:10:00Z"
decisoes:
  - id: p07-sub2-precisao-sobre-revocacao
    motivo: "Mesma decisão da sub 1: lista negra de qualificadores não fecha (rodadas 1-4 acharam variações novas a cada vez); trocado por gramática fechada. Perde recall de propósito; incerto mantém o compromisso pendente."
  - id: p07-sub2-arquivo-execucao
    motivo: "execucao.md arquivado (blocos P06 sub 12 e 13 -> execucao-archive-p06sub12-sub13.md)."
  - id: p07-sub2-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela no início do disparo de 17h; trabalho feito na branch designada claude/lucid-allen-nl4cc3."
testes:
  resultados:
    - "functions/ completo ANTES 4467 OK (head de main, conforme P07 sub 1); DEPOIS 4486 OK (240s, head final); test_autonomy_cumprimento 19 OK (novo arquivo)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): entrega parcial por palavras não cobertas, qualificadores (em branco/errada/rascunho), destinatário/dono, dois objetos com só um entregue, objeto igual com conteúdo diferente, mídia sem conferir nome. Corrigido com lista branca na mensagem e nome do anexo."
  - "Rodada 2: nome do anexo com palavras extras e fórmula truncada ('segue o relatório e'). Corrigido (anexo = objetos + extensão; mensagem começa na marca e termina em objeto)."
  - "Rodada 3: objeto prometido fora do vocabulário, plural/número, qualificador na promessa, exclusão/alternativa, texto não latino. Corrigido com lista branca também na promessa."
  - "Rodada 4: promessa truncada, marcas combinantes (tachado), tokens soltos/repetidos e pontuação repetida. Corrigido com gramática fechada por regex fullmatch, rejeição de Mn estranhas e pontuação única final. Limitação aceita: plural na mensagem ('segue o relatórios') casa o objeto singular."
  - "Rodada 5: texto sem mídia fechava mesmo falando em anexo/objeto só-arquivo (foto, print, pdf, anexo) e mensagem sem limite de tamanho. Corrigido: sem tem_midia -> incerto; mensagem >600 chars -> nao_cumpre."
  - "Rodada 6: 'arquivo' também é só-arquivo (corrigido). Aceito por design: planilha/documento/etc. como texto sem mídia ainda fecham; o consumidor futuro (sem wiring agora) deve exigir evidência de anexo; nenhuma outra burla achada."
  - "Codex na PR #482 (P2 real, corrigido): marca combinante em pré-composto (U+1E69) escapava da checagem; agora confere original e NFD. Rodada 7: U+0340/0341/0344 viram acento permitido só no NFD; agora o original também é conferido. Rodada 8: não achou nada."
pendencias:
  - "P07 passos 2 (extração estruturada, sombra), 3, 5, 7, 8; wiring em atencao_whatsapp somente com flag/sombra."

---

```yaml
pacote: "P07 sub-entrega 3/N -- passo 7 (parte pura): functions/autonomy/followup_guard.py. revalidar_followup(compromisso, contexto) -> ENVIAR/ADIAR/SUPRIMIR com motivo. Ordem: compromisso encerrado -> atenção já fechada pelo dono -> rascunho pendente -> mensagem posterior do dono (cumprimento firme via avaliar_cumprimento suprime; senão adia) -> mensagem posterior da contraparte (adia) -> ENVIAR. Contexto malformado, estado de atenção desconhecido, fuso inválido ou qualquer exceção -> ADIAR (nunca envia na dúvida). Sem I/O e sem wiring; fila antiga e A06 não alteradas."
estado: validado
inicio: "2026-10-21T19:45:00Z"
fim: "2026-10-21T21:00:00Z"
decisoes:
  - id: p07-sub3-adiar-sobre-enviar
    motivo: "Só ENVIAR dispara follow-up; qualquer dúvida adia. delegado_ao_agente/aguardando_andre adiam; estados desconhecidos adiam; 'adiado' deixou de ser tratado como fechado."
  - id: p07-sub3-tempo
    motivo: "Mensagens com timestamp >= prometido_em (truncado em segundos, normalizado em UTC) contam como posteriores, exceto a própria promessa (from_me, wa_message_id str não vazio == mensagem_id)."
  - id: p07-sub3-arquivo-execucao
    motivo: "execucao.md arquivado (blocos P06 sub 14 e correção -> execucao-archive-p06sub14.md)."
  - id: p07-sub3-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela no início do disparo de 17h."
testes:
  resultados:
    - "functions/ completo ANTES 4486 OK (head de main, conforme P07 sub 2); test_autonomy_followup_guard 18 OK (novo arquivo); DEPOIS 4504 OK (296s, head final)."
revisao_adversarial:
  - "Rodada 1: estado_atencao desconhecido, timestamp igual, tzinfo sem offset, falta de rede de segurança. Corrigido. Rodada 2: microssegundos e id vazio/da contraparte. Corrigido. Rodada 3: dobra de horário de verão (tzinfo compartilhado). Corrigido normalizando para UTC. Rodada 4: só ADIAR conservador em datetime extremo (OverflowError no astimezone); movido para dentro do try. Codex na PR #483 (P2 real, corrigido): estado_atencao ausente do contexto virava ENVIAR; agora a chave é obrigatória. Rodada 5: texto do compromisso obrigatório. Rodada 6: própria promessa só no mesmo instante; vencimento documentado como responsabilidade do chamador. Rodada 7: não achou nada."
pendencias:
  - "P07 passos 2 (extração estruturada, sombra), 3, 5, 8; wiring em atencao_whatsapp somente com flag/sombra."
```
