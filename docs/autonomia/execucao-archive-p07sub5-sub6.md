# Arquivo: P07 sub-entregas 5/N e 6/N (movidas de execucao.md em 2026-10-23, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 5/N -- passo 3 (parte pura): functions/autonomy/compromissos_chat.py. Registro imutável (tupla de Compromisso) com vários compromissos independentes por chat (chave chat__msg__indice) e substituição só por relação explícita: substituir(registro, antigo, novo) exige mesmo chat, ambos abertos, chaves distintas e nunca cria ciclo. Registro revalidado em profundidade a cada chamada (tipos exatos, chaves únicas, chave == chave_compromisso, estado/substituido_por coerentes, sem ciclo, sem mutar objetos do chamador); só ValueError. Sem I/O e sem wiring; fila antiga e A06 não alteradas."
estado: validado
inicio: "2026-10-22T13:50:00Z"
fim: "2026-10-22T14:40:00Z"
decisoes:
  - id: p07-sub5-substituicao-explicita
    motivo: "Nunca por semelhança de texto nem entre chats; antigo vira 'substituido' com substituido_por; cadeia A->B->C permitida, ciclo recusado."
  - id: p07-sub5-triagem
    motivo: "Nenhuma PR aberta no início do disparo de 11h BRT; branches claude/gaspar-agente-* recentes são de outra linha de trabalho (já mescladas) e não foram tocadas."
testes:
  resultados:
    - "functions/ completo ANTES 4517 OK (head de main); test_autonomy_compromissos_chat 20 OK (novo arquivo); DEPOIS 4537 OK (head final)."
revisao_adversarial:
  - "Rodada 1: registro sem validação profunda (chave incoerente, duplicadas, estado inválido, subclasses). Rodada 2: ciclo em registro montado à mão, chave só por prefixo, str exata. Rodada 3: abrir() com subtipos hostis (exceção não-ValueError). Rodada 4: estado hostil. Rodada 5: revalidação contornável por __post_init__ de instância e atributo apagado. Rodada 6: validação mutava o objeto do chamador (strip). Todos corrigidos. Rodada 7: não achou nada."
pendencias:
  - "P07 passos 2 (extração estruturada, sombra), 5; wiring em atencao_whatsapp somente com flag/sombra."
```


---

```yaml
pacote: "P07 sub-entrega 6/N -- passo 4 (parte pura): functions/autonomy/prazo_followup.py. planejar_acompanhamento(prazo, enviado_em, horas_resposta, fuso) -> Acompanhamento(verificar_em UTC sem microssegundos, origem, vinculante, amostra). Prazo expresso com data é vinculante e só é acompanhado após a meia-noite seguinte no fuso do dono; sem ele, o momento de olhar de novo é ESTIMATIVA (p75 do histórico de horas de resposta do contato, amostra mínima 5, limitada a 1-168h, nunca vinculante) ou padrão de 24h. Natureza/data inválidas, histórico ruim (bool, nan, <=0, não lista/tupla), fuso inválido e entradas hostis viram só ValueError. Sem I/O e sem wiring; fila antiga e A06 não alteradas."
estado: validado
inicio: "2026-10-22T16:48:00Z"
fim: "2026-10-22T17:30:00Z"
decisoes:
  - id: p07-sub6-triagem
    motivo: "PR #495 (briefing 5h desligável, outra linha de trabalho; limpa, CI verde, flag padrão ligado, Codex sem achados) mesclada. Nenhuma PR da linha de autonomia aberta; nenhuma execução paralela."
  - id: p07-sub6-arquivo-execucao
    motivo: "execucao.md arquivado (blocos P07 sub 2 e 3 -> execucao-archive-p07sub2-sub3.md)."
  - id: p07-sub6-prazo-vencido
    motivo: "Prazo expresso anterior à promessa é recusado (ValueError) em vez de gerar acompanhamento no passado; quem chamar decide o tratamento."
testes:
  resultados:
    - "functions/ completo ANTES 4542 OK (CI de main após #495); com o módulo novo (versão inicial) 4549 OK (188s); test_autonomy_prazo_followup 10 OK na versão final; DEPOIS 4552 OK (193s, head final)."
revisao_adversarial:
  - "Rodada 1: OverflowError com int enorme, Prazo.data não-date, natureza/iterável/tzinfo hostis, bytearray aceito. Corrigido. Rodada 2: microssegundos no resultado, fim do dia com hora repetida (fold), data datetime aceita. Corrigido (meia-noite seguinte no fuso, truncamento, tipo date exato). Rodada 3: não achei nada."
pendencias:
  - "P07 passo 2 (extração estruturada, sombra), passo 5 (correlação entre canais); wiring em atencao_whatsapp somente com flag/sombra."
```
