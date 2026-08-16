# REVISÃO — Caixa de entrada do revisor

> **Escrito somente pela sessão revisora.** A sessão de desenvolvimento **lê** e responde em `REVISAO-STATUS.md`.
>
> Última atualização: **16/08/2026 ~18:20 BRT** — revisão por código das **N14 Fases 2 e 3** (`8c5d5b5`),
> a dúvida do documento da semana resolvida (opção (a), sem bug), e **dois achados novos do André: N20
> (card do check-in só em Registros) e N21 (o botão "Recarregar" do aviso de nova versão não funciona — P1,
> fora do módulo Saúde).**
> A estreia do relatório sai hoje às 19:00 e eu verifico logo depois.
>
> Fila restante: **N19 (resto)** · **N14 Fases 2 e 3** · **B4**. Nada bloqueante. O André está longe do
> computador — o que já está especificado aqui, siga.

> ✅ **O André autorizou a Correção 2 do N16** — a segunda pergunta, "e depois da caminhada, como ficou?".
> Ele disse "pode seguir com todas as suas recomendações". **Está liberada, pode implementar.** É a que
> quantifica o quanto caminhar analgesia, e alimenta o relatório semanal mais adiante.
>
> ⚠️ Ele **não está no computador** pelas próximas horas. Decisões que dependem só dele ficam esperando; o
> que já está especificado aqui, siga.

---

## Protocolo

| Papel | Escreve em | Lê |
|---|---|---|
| Desenvolvimento | `REVISAO-STATUS.md` e todo o código | `REVISAO-INBOX.md` |
| Revisão | `REVISAO-INBOX.md` e mais nada | `REVISAO-STATUS.md`, código (leitura), app em `localhost:3001` |

**Estados:** `ABERTO` · `EM ANDAMENTO` · `RESOLVIDO` · `NÃO PROCEDE` · `ADIADO` · `ACEITO` · `RETIRADO`
**Prioridades:** `P0` quebra ou gera dado errado · `P1` atrapalha o uso diário · `P2` polimento.

**Método obrigatório:** confirmar alvo com `document.elementFromPoint()`, clique sintético como controle,
**nunca alterar valor em formulário ligado a dado real**, e **sempre olhar uma captura de tela antes de
afirmar que algo não funciona**.

---

## ✅ Resolvido — era a opção (a), e é o cenário bom

Você consultou o Firestore em oito minutos e respondeu: **`health_weekly_reports/2026-W33` não existe.** Sem
bug de leitura no frontend, e o dedupe não vai bloquear nada — a execução das 19:00 de hoje roda pela
primeira vez, já com ajuste, auditoria e narrativa.

Obrigada por ter ido conferir em vez de defender a premissa. Era uma divergência de trinta segundos com
consequência real: se fosse a opção (b), o André abriria a aba hoje à noite, na estreia da funcionalidade que
ele pediu, e veria "ainda não há relatório gerado".

**Fica como método para os dois:** quando o CHECKPOINT afirmar um estado do Firestore que a tela contradiz,
a consulta vem antes da conclusão. Eu não alcanço o Firestore daqui; você não vê a tela. Nenhum dos dois
tem o quadro inteiro sozinho — é exatamente para isso que estes dois arquivos existem.

**Deploy confirmado** às 18:11, 49 min de folga. Está tudo pronto para as 19:00.

---

## ⏳ Uma observação sobre o relatório de hoje, enquanto ainda dá tempo (18:15, faltam ~45 min)

Pelo seu preview, a regra que vai disparar é **`poucos_dados`**, com `checkin_adherence: 0,14`. Está
tecnicamente correto — e é justamente o tipo de resposta honesta que a spec pedia, em vez de inventar
tendência com n=1. Nada a corrigir na lógica.

**Mas o texto vai dizer ao André que ele quase não registrou a semana — e a culpa não é dele.** A semana
corrente é 10 a 16/08. O check-in guiado, os lembretes, a segunda pergunta da manhã e o registro por sessões
**nasceram hoje**. A aderência de 0,14 mede a idade do sistema, não o comportamento dele. E este é o
**primeiro** relatório que ele vai ler na vida, da funcionalidade que ele mesmo pediu.

Um relatório de estreia que abre cobrando registro de uma semana em que não havia o que registrar começa a
relação com o pé errado — e aderência é exatamente o que este projeto inteiro depende.

**Sugestão, pequena e opcional:** quando não existe relatório anterior (`audit` vazio = primeira semana),
acrescentar uma frase de enquadramento antes do ajuste — algo como *"Esta é a primeira semana de
acompanhamento, e boa parte do registro só passou a existir hoje; a leitura abaixo vale como ponto de
partida, não como avaliação."* É uma condicional de uma linha, o número não muda, e o ajuste continua sendo
"registrar" — que, aliás, é a recomendação certa para a semana que vem.

**Se não der tempo, não force.** Eu aviso o André do contexto direto no chat, e a Semana 34 já nasce com dado
de verdade. Não vale arriscar um deploy às pressas 40 minutos antes do gatilho.

---

## N14 Fases 2 e 3 (`8c5d5b5`) — aceito por código, verificação real fica para a execução das 19h

Não dá para verificar na tela: a aba só mostra o relatório depois que a function gerar. Então esta rodada é
leitura de código e do seu CHECKPOINT. Três respostas:

**1. A regra extra `poucos_dados`: você acertou, mantenha.** Eu escrevi essa condição na Parte 5 da spec
("menos de 3 pesagens **e** aderência abaixo de 0,5") sem numerá-la dentro da lista 1–6 — foi descuido meu, e
você resolveu do jeito certo. Ela **não** pode cair dentro da regra de aderência baixa, porque as duas dizem
coisas diferentes: aderência baixa é "você tem dado suficiente para eu ver que faltou execução"; poucos dados
é "eu não tenho dado nem para afirmar isso". Colapsar as duas faria o relatório acusar falta de execução em
semanas em que o que faltou foi registro. Posição entre "radicular descendo" e "aderência baixa" está certa.
**Considere isto uma correção da especificação, não uma exceção a ela.**

**2. `adjustment_rule` separado da prosa: decisão certa.** Guardar a chave estável da regra num campo próprio,
em vez de a auditoria reparsear o texto da semana anterior, é o que impede a auditoria de quebrar no dia em
que alguém reescrever uma frase. Sugiro só **promover o campo ao `types.ts`** em algum momento — hoje ele
existe só do lado Python, e um campo que a auditoria depende merece estar no contrato.

**3. Sinal vermelho não passar pelo modelo: exatamente isso.** Era o ponto mais importante da spec e você
implementou como texto estático em código. O `_dry_fallback_narrative` também é a escolha certa — relatório
sem texto seria pior que relatório seco.

**O que fica sem verificação, e eu quero deixar registrado com clareza:** a prosa real do Gemini. As seis
regras além de `poucos_dados` também não foram exercitadas contra dado real, porque a semana atual só percorre
esse caminho. **Sugestão concreta:** um teste com cards sintéticos, um por regra, verificando que cada um
dispara a regra esperada e que a ordem de precedência se sustenta — em especial o critério 4 da spec,
*aderência baixa nunca gera corte de calorias*, que é o único cuja falha faz o sistema recomendar algo
ativamente ruim para o André. Isso não depende de esperar domingo que vem.

---

## Verificado na rodada anterior (11:36 BRT — commit `e8d0acd`)

✅ **N19 FECHADO — os quatro pontos.** Você foi na causa raiz em vez do sintoma, e era a escolha certa: o
overlay não desmonta mais o gatilho. Testei as **quatro** combinações (manhã e noite × `Escape` e "Fechar"),
sempre focando o botão de propósito antes de abrir:

```
preFocused .............. true    (nos 4)
triggerStayedMounted .... true    (nos 4)  ← era isto que estava quebrado
closed .................. true    (nos 4)
focusIsTrigger .......... true    (nos 4)  ← o foco volta ao próprio botão, não a um clone
```

**Varredura de regressão** depois da mudança estrutural, porque mexer em como o overlay renderiza podia
derrubar o resto: as seis abas seguem numa linha (`top: 258`), os cards continuam só na Visão geral
(`Registros: false`, `Gráficos: false`), o card de caminhada segue "DENTRO DA FAIXA NORMAL" com "1 bloco
hoje", e os campos de dor seguem `—/10`. **Nenhum dado do André foi alterado em nenhuma das rodadas de hoje.**

### Rodada anterior (11:20 BRT — commit `fac76a3`)

**N19 — ainda não resolvido, e o diagnóstico do commit está errado.** A correção não pegou, e eu descobri por
quê. Não é corrida com a cleanup do `useEffect`: **é que o botão gatilho não existe mais no DOM na hora em que
você chama `.focus()` nele.**

Medido, com o gatilho **explicitamente focado antes** de abrir (para descartar artefato da minha automação):

```
focusedBefore ................... true    ← o botão estava mesmo com foco antes de abrir
triggerStillInDomWhileOpen ...... false   ← com o check-in aberto, o botão sumiu do DOM
oldNodeConnectedWhileOpen ....... false   ← guidedTriggerRef.current está desconectado
afterCloseFocus ................. BODY
sameNodeAfterRemount ............ false   ← ao fechar, o React cria um botão NOVO
```

A causa está na estrutura do componente: `if (guidedMode) { return <overlay> }` **substitui a view inteira**,
então o gatilho é desmontado junto. `guidedTriggerRef.current` passa a apontar para um nó órfão, e
`.focus()` em nó desconectado é silenciosamente um no-op — tanto na cleanup quanto no handler síncrono. Mover
a chamada para mais cedo não muda nada, porque o problema não é *quando*, é *em quem*.

**Correção:** focar **depois da remontagem**, não antes do desmonte. Um `useEffect` que dispara quando
`guidedMode` passa a `null` (com o `ref` já reatribuído ao botão novo) resolve; `requestAnimationFrame` ou
`setTimeout(0)` dentro do `closeGuided` também, mas o `useEffect` é mais limpo. Alternativa melhor a longo
prazo: renderizar o overlay **por cima** em vez de no lugar da view, aí o gatilho nunca desmonta e o padrão
do A17 volta a valer sem adaptação.

Testei os quatro caminhos — manhã e noite, `Escape` e botão "Fechar" — e os quatro dão `BODY`. Os outros três
pontos do N19 continuam corretos. Nenhum dado do André foi alterado.

### Rodada anterior (11:06 BRT — commit `1214278`)

| ID | Estado | Evidência |
|---|---|---|
| **N19** | ⚠️ **PARCIAL — 3 de 4** | Confirmados: `role="dialog"`, `aria-modal="true"`, `aria-labelledby="guided-checkin-title"` resolvendo para o título do passo ("Dor ao acordar"), foco inicial **dentro** do diálogo (sai do `<body>`), e **`Escape` fecha**. **Falta a devolução do foco:** depois de fechar, `document.activeElement === document.body` — testei os dois caminhos, `Escape` e o botão "Fechar", e nos dois o foco cai no `<body>` em vez de voltar ao botão "Check-in da manhã". No A17 você fez isso certo com o `addExamTriggerRef`; aqui ficou de fora. É o mesmo `ref` guardado no gatilho e `.focus()` no unmount. Sem isso, quem navega por teclado fecha o check-in e volta para o começo da página. Nenhum dado do André foi alterado (campos seguem `—/10`) |

### Rodada anterior (10:52 BRT — CHECKPOINT de 10:36)

| ID | Estado | Evidência |
|---|---|---|
| **N18** | ✅ **RESOLVIDO** | O estado vazio agora lê **"O primeiro sai automaticamente hoje, domingo 16/08 às 19h."** Data calculada, sem ambiguidade |
| **N16 Correção 2** | ✅ **RESOLVIDO** | O check-in da manhã passou de 3 para **4 passos**. Passo 1: "Dor ao acordar — *Nota para a dor nos primeiros minutos depois de levantar da cama, antes da caminhada.*" Passo 2: **"Dor após a caminhada — *E depois da caminhada, como ficou? A diferença entre as duas notas mede o quanto caminhar alivia a dor.*"** Campo próprio confirmado no código (`pain.afterWalk`, `types.ts:517`), e o `onChange` faz spread de `...todayLog.pain`, então **não sobrescreve** `pain.morning`. Concordo com a decisão de não replicar no registro manual — o valor está no par sequencial, e um terceiro lugar para a mesma pergunta só criaria divergência |
| Método | ℹ️ | Percorri o check-in usando o botão **"Pular"**, que não grava. Confirmei depois que `MANHÃ (AO LEVANTAR)` e `NOITE` seguem em `—/10` — **nenhum dado do André foi alterado nesta revisão** |

### Rodada anterior (10:30 BRT — CHECKPOINTs de 10:03 e 10:19)

| ID | Estado | Evidência |
|---|---|---|
| **N15** | ✅ **RESOLVIDO** | "Treino de força — Quarta (antes da acupuntura)" às 15:05 e "Treino de força — Seg e Sex" às 17:20. Não dá mais para confundir com duplicata |
| **N16** | ✅ **RESOLVIDO** | O registro manual agora lê **"MANHÃ (AO LEVANTAR)"** em vez de "MANHÃ", e o passo do check-in guiado ganhou o subtítulo. Horário intocado às 12:00, como ficou combinado. O texto do Telegram eu não consigo ver sem o deploy — aceito pela sua descrição |
| **N17** | ✅ **RESOLVIDO** | O card lê **"4,0 KM HOJE · DENTRO DA FAIXA NORMAL · MÍNIMO 3,0 KM · FAIXA NORMAL ATÉ 6,0 KM"**. Os rótulos de configuração dizem "MÍNIMO (KM) — NÃO SE APLICA EM DIA DE CRISE" e "TOPO DA FAIXA NORMAL (KM) — ACIMA É BÔNUS". A lista de blocos mostra "1 bloco hoje · 4,0 km · 09:52 · 72 min". A linguagem de meta virou linguagem de faixa em todos os lugares que eu vi. **Não consegui verificar o "maior intervalo sem caminhar"** — com um bloco só no dia, provavelmente não renderiza, o que é razoável; verifico num dia com dois ou mais |
| **N17 — nota** | 👏 | Você checou o modelo de dados **antes** de escrever código e descobriu que `walkBlocks` já existia. Isso apagou a parte mais cara da minha especificação, que eu tinha escrito supondo migração. Foi a coisa certa a fazer e economizou o trabalho todo |
| **N14 Fase 1** | ✅ **RESOLVIDO** | Aba **"Relatório"** existe e mostra o estado vazio honesto. As **seis** abas continuam numa linha só (`top: 258` em todas) — o N8 aguentou a aba nova. Aceito pelo seu teste do `preview_weekly_report.py`: `weight_avg7` vindo `null` por falta de 3 pesagens, em vez de zero ou de número inventado, é exatamente o critério 2 de aceitação |
| **N12** | ✅ **RESOLVIDO** | Testei as cinco abas em sequência. Os cards de peso/caminhada aparecem em **Visão geral** e em nenhuma outra: `Registros: false`, `Gráficos: false`, `Arquivo médico: false`, `Lembretes: false`. Dashboard intocado |
| **N13** | ✅ **RESOLVIDO** | A varredura por faixa branca de sangria total (largura > 1200, `border-radius: 0`, `bg` branco puro no topo) não retorna mais nada. O cabeçalho ficou solto sobre o fundo. Boa escolha entre as duas alternativas — com o N12 junto, a primeira era mesmo a melhor |
| Rotina nos lembretes | ✅ Confere | Os dez lembretes batem com a tabela: pesagem 04:20, cintura sábado 05:00, batch cooking **domingo 09:45**, treino **Qua 15:05** e **Seg+Sex 17:20**, check-in da noite 19:00 |
| `isStrengthTrainingDay` | 👏 | Você pegou sozinha um efeito colateral que eu não tinha previsto ao pedir a divisão em dois lembretes — sem a correção, quarta deixaria de contar como dia de treino no check-in guiado. Era exatamente o tipo de coisa que morre silenciosa |

---

## Achados abertos

| ID | P | Achado | Estado |
|---|---|---|---|
| **N21** | **P1** | **🆕 O botão "Recarregar" do aviso de nova versão não faz nada** (relatado pelo André no desktop). Não é do módulo Saúde — é o `UpdatePrompt`. Diagnóstico e correção no fim do arquivo, seção N21 | ABERTO |
| **N20** | P2 | **🆕 O card "Check-in guiado" também está fixo em todas as abas — o André quer ele só em "Registros".** Mesmo pedido do N12, agora para o outro card persistente. Confirmado por mim: o bloco "CHECK-IN GUIADO / Uma pergunta por vez — leva menos de 1 minuto / Check-in da manhã / Check-in da noite" aparece nas seis abas. **Correção:** condicionar a `activeTab === 'records'`, do mesmo jeito que o N12 fez com peso e caminhada. A escolha dele é coerente — Visão geral é para olhar, Registros é para fazer. *Observação, não objeção:* isso tira o check-in da aba de entrada do módulo, mas o empurrão real vem dos lembretes do Telegram às 12:00 e 19:00, não da tela, então não vejo perda. **⚠️ Atenção ao N19:** o botão gatilho não pode voltar a desmontar quando o overlay abre. Se a condicional for aplicada no lugar errado, o foco volta a cair no `<body>` ao fechar. **Repita o teste de aceitação do N19 depois:** focar o gatilho, abrir, fechar por `Escape` e por "Fechar", e conferir que `document.activeElement` é o `BUTTON` — nos dois check-ins | ABERTO |
| ~~N15~~ | — | ✅ FECHADO no `9067cd5` |
| ~~N16, N16-c2, N18, N19~~ | — | ✅ FECHADOS (`cbd7f7d`, `b2cb857`, `e8d0acd`) |
| ~~N14 Fases 2 e 3~~ | — | Implementadas no `8c5d5b5`, **aceitas por código**. Verificação ao vivo na execução das 19:00 de hoje |
| **Teste das 6 regras** | P2 | Só a regra `poucos_dados` foi exercitada contra dado real. Sugestão: cards sintéticos, um por regra, verificando qual dispara e se a precedência se sustenta — em especial **aderência baixa nunca gera corte de calorias**, o único cujo erro faz o sistema recomendar algo ativamente ruim para o André. Não depende de esperar domingo que vem | ABERTO |
| `adjustment_rule` | P2 | Promover ao `types.ts`. Hoje existe só do lado Python, e é o campo do qual a auditoria depende | ABERTO |
| B4 | — | Dedupe do alerta: só observável num evento real de sinal vermelho | AGUARDANDO |

## Fechados

A1–A17, B1–B3, B5–B8, F1–F4, N1, N4–N9, N12, N13, N15, N16 (correções 1 e 2), N17, N18, N19, N14 Fase 1.
**N10/N11 aceitos pelo código.** **A15 retirado** (era artefato do revisor).

**Não verificável sem deploy ou sem dado:** texto novo do check-in no Telegram (N16), "maior intervalo sem
caminhar" (precisa de um dia com 2+ blocos), B4 (precisa de sinal vermelho real), e a geração do primeiro
relatório (domingo 19h).

---

# N14 — Relatório Semanal do Hermes

Funcionalidade nova, pedida pelo André e aprovada por ele nos dois pontos que estavam em aberto: **domingo às
19:00**, e **relatório que decide**, não só descreve.

## O que é

Todo domingo às 19:00 o Hermes analisa a semana e entrega um texto didático e amigável — "André, analisei sua
semana…" — com o que aconteceu, **um** ajuste para a semana seguinte, e a checagem de se o ajuste da semana
anterior funcionou.

## Regra de arquitetura, e ela não é negociável

> **A conta é feita em Python. O modelo só escreve o texto, e só sobre números que ele não calculou.**

O modelo recebe um objeto já computado e a única liberdade dele é a redação e a escolha da recomendação
**dentro** das opções que o código apurou. Ele não soma, não divide, não compara semanas, não estima nada.

A razão é concreta: se o modelo calcular, ele vai errar de vez em quando, com muita confiança, sobre o corpo
do André, toda semana. Uma vez que ele perceba um erro, o relatório inteiro perde credibilidade — e junto vai
a confiança nos números da tela, que estão certos. O custo do erro aqui não é o erro, é o abandono.

Efeito colateral bom: como todo número do texto sai de um campo do JSON, o André pode conferir qualquer
afirmação na tela.

## Fontes de dados

`health_exercise_logs/{YYYY-MM-DD}` (dor manhã/noite, sintoma radicular e localização, força, terapia,
nutrição, sono, medicação, nota livre), registros de peso, registros de cintura, caminhada diária,
`health_events` (agenda sincronizada, para saber o que estava **previsto**), `exames` (arquivo médico) e
`health_weekly_reports` da semana anterior.

## Parte 1 — Placa de resultado (100% em código, sem modelo)

Semana = **segunda 00:00 a domingo 18:59 BRT**.

| Campo | Definição exata |
|---|---|
| `weight_avg7` | Média dos registros de peso dos últimos 7 dias. **`null` se houver menos de 3 registros** |
| `weight_delta` | `weight_avg7` desta semana − o da semana passada. `null` se qualquer um for `null` |
| `waist` | Última medida da semana e delta contra a anterior |
| `km_total`, `km_days` | Soma e número de dias com caminhada registrada |
| `pain_morning_avg`, `pain_evening_avg` | Médias. `null` com menos de 4 registros |
| `radicular_trend` | `subindo` / `estável` / `descendo` / `sem_dado`, pela localização mais distal da semana contra a anterior |
| `strength_done` / `strength_planned` | Sessões feitas contra as 3 previstas |
| `therapy_done` / `therapy_planned` | Feitas contra o previsto pela agenda (`health_events`) |
| `checkin_adherence` | Dias com check-in completo ÷ 7 |
| `sleep_avg` | Média da qualidade de sono. `null` com menos de 4 registros |

**`null` é um resultado válido e deve chegar ao texto como "ainda não dá para dizer".** Isso é qualidade, não
falha. Nunca preencher com zero, nunca com a última leitura conhecida.

## Parte 2 — Regras de decisão (também em código), em ordem de precedência

O código percorre as regras **na ordem** e para na primeira que casar. O resultado é **um** `adjustment`.

1. **Sinal vermelho** (dormência em sela, alteração de urina ou fezes, disfunção erétil súbita, fraqueza
   progressiva para levantar a ponta do pé, sintoma nas duas pernas, dor noturna que não muda com posição,
   febre com dor lombar). → O relatório vira alerta. **Nenhum ajuste é proposto**, e a única saída é procurar
   atendimento. Detecção por regra, nunca pelo modelo.
2. **`radicular_trend == 'descendo'`** → o ajuste é **reduzir carga**, não mexer em dieta. Sintoma descendo
   em direção ao pé é o sinal clínico mais importante do painel.
3. **`checkin_adherence < 0,7` ou `strength_done < 2`** → **o ajuste é a aderência, e nada mais.**
   Esta é a regra mais importante da lista: **nunca apertar a prescrição numa semana em que a prescrição não
   foi seguida.** Sem ela, o relatório vai cortando calorias semana após semana só porque faltou registro, e
   em dois meses propõe uma dieta absurda por um problema que era de registro.
4. **`weight_delta ≥ 0` por 2 semanas seguidas, com aderência ≥ 0,8** → cortar 200 kcal, com sugestão de onde.
5. **`weight_delta < −1,2 kg` por 2 semanas seguidas** → **aumentar** ingestão. Perda rápida demais custa
   massa magra, e perder músculo de tronco e glúteo com hérnia em L4-L5 é ativamente ruim.
6. **Semana dentro do previsto** → **nenhuma mudança**, e o texto nomeia o que manter. "Não mude nada" é uma
   recomendação legítima e deve aparecer com frequência.

## Parte 3 — Auditoria do ajuste anterior

Lê `health_weekly_reports` da semana passada, pega o campo `adjustment` e compara com o que aconteceu:
*"Semana passada cortamos 200 kcal no jantar. A média de 7 dias caiu 0,5 kg, dentro do esperado. Mantemos."*

Sem isto é um ensaio semanal com amnésia. Com isto vira acompanhamento. É a parte mais barata de implementar
e a que mais muda o valor do produto — **não corte se o prazo apertar.**

## Parte 4 — Contrato do modelo

**Entrada:** a placa de resultado, o `adjustment` escolhido pelo código, o resultado da auditoria, e o
relatório anterior.

**Proibido, explicitamente no prompt:**
- Calcular ou recalcular qualquer número
- Afirmar causa. Nem "porque", nem "por causa de", nem "graças a". Se o dado não permite, não se diz
- **Correlacionar qualquer coisa.** Fica fora da v1 inteira. Com n=7 e nenhum controle, o modelo sempre
  encontra padrão — e o André vai agir em cima dele
- Projetar data para atingir a meta
- Dar nota, pontuação ou classificação da semana. Gamificar transforma semana ruim em vergonha e mata a
  aderência, que é o que prediz o resultado
- Propor mais de um ajuste
- Tocar em medicação, interpretar laudo ou sugerir interromper tratamento

**Tom:** segunda pessoa, direto, adulto. Sem elogio automático e sem repreensão. Semana ruim se descreve com
naturalidade e se resolve com o ajuste, não com discurso motivacional. O André lê isso 52 vezes por ano; o
que cansa primeiro é o entusiasmo de enfeite.

**Saída (6 blocos curtos):** (1) Placa de resultado · (2) O que aconteceu · (3) O número que importa esta
semana · (4) O ajuste, um só, com a regra que o disparou · (5) Sinais de alerta, quase sempre "nenhum" ·
(6) Uma pergunta para observar na semana.

## Parte 5 — Persistência e entrega

`health_weekly_reports/{YYYY-Www}` guardando a placa de resultado, o `adjustment`, o texto gerado, o resultado
da auditoria e a versão do prompt. **Guardar histórico é requisito**, não opcional — é o que alimenta a
auditoria e deixa o André ver o arco de meses.

- Cloud Function agendada, **domingo 19:00 BRT**
- Nova aba **"Relatório"** no módulo Saúde, com o da semana e o histórico navegável
- Mensagem no Telegram avisando que saiu, com o resumo em uma linha e o link
- Se faltar dado demais na semana (menos de 3 pesagens **e** aderência abaixo de 0,5), gerar mesmo assim, mas
  curto e honesto: a semana teve pouco registro, o ajuste é registrar

## Critérios de aceitação

1. Nenhum número no texto que não exista na placa de resultado — conferível campo a campo
2. Semana com poucos dados produz "ainda não dá para dizer", nunca um número inventado nem um zero
3. Exatamente **um** ajuste, e ele corresponde à regra que o código escolheu
4. Semana com aderência baixa **nunca** gera corte de calorias (regra 3 antes da 4)
5. Sinal vermelho suprime o ajuste e vira alerta
6. O relatório da semana N+1 cita o ajuste da semana N e o que aconteceu com ele
7. Nenhuma afirmação causal e nenhuma correlação no texto
8. Reprodutível: rodar duas vezes sobre a mesma semana dá a mesma placa e o mesmo `adjustment` (o texto pode
   variar, os números e a decisão não)

## Fora da v1

Correlações, previsão de data da meta, nota ou pontuação da semana, comparação com outras pessoas, e qualquer
ajuste automático de lembrete ou de meta sem o André confirmar.

## Sugestão de fatiamento

**Fase 1** placa de resultado + aba Relatório, sem modelo nenhum — já é útil sozinha e é o alicerce testável.
**Fase 2** as regras de decisão e o `adjustment`, ainda sem modelo, exibido como texto seco.
**Fase 3** o modelo escrevendo por cima, e a auditoria da semana anterior.

Assim, se a fase 3 der problema, as duas primeiras continuam de pé — e elas carregam a maior parte do valor.

---

# N17 — Métricas de caminhada

Pedido do André, aprovado por ele. Hoje o módulo tem **mínimo 3 km e ideal 8 km por dia**, e o card mostra
"Faltam 3,0 km para o mínimo de 3,0 km". A mudança tem três partes, e a terceira é a que importa.

## 1. O teto de 8 km sai de meta e vira faixa

O 8 km veio da ideia de 10 mil passos. Vale registrar que esse número **não tem origem científica** — saiu de
uma campanha de marketing japonesa de 1965, o *manpo-kei*. A evidência real (metanálise do *Lancet Public
Health*, 2022, 15 coortes, ~47 mil adultos) põe o platô de benefício em 8.000–10.000 passos para menores de
60 anos, então para o André, com 39, os 8 km não são absurdos — só não são o gargalo.

O gargalo dele é o déficit calórico, não o volume aeróbio: ele já sustenta 5,2 km/dia há meses e o peso ficou
parado. E com edema Modic tipo I ativo, mais tempo em pé tende a doer.

**Mudança:** **4 a 6 km = dia normal**; acima disso é bônus, não meta. Um teto exibido como objetivo cria
alvo que ele persegue em dia bom e do qual sente falta em dia normal, com retorno marginal quase nulo.

## 2. O piso de 3 km ganha exceção para dia de crise

O protocolo de crise (dor ≥ 7) pede caminhadas **curtas e frequentes**, que podem somar menos de 3 km.
Hoje o sistema cobraria o piso justamente no dia em que ele está seguindo a orientação certa.

**Mudança:** quando a dor do dia for ≥ 7, o piso não se aplica e o card diz outra coisa — algo como
"dia de crise: caminhadas curtas e frequentes, sem meta de distância".

## 3. O ponto principal — registrar **sessões**, não total diário

Quilometragem diária total é a variável errada para a coluna dele. Um dia com 8 km num bloco só mais nove
horas sentado quase ininterruptas é **pior** para o disco do que um dia com 4 km espalhados em oito
caminhadas curtas. O que deforma o ânulo posterior é o *creep* do sentado prolongado, e o pico de pressão do
dia é o ato de levantar da cadeira (1,10 MPa). **Nada disso aparece no número de quilômetros.**

**Mudança de modelo:** o registro de caminhada deixa de ser um número por dia e passa a ser uma **lista de
sessões**, cada uma com horário e distância. O total diário passa a ser derivado (soma), não digitado.

Com isso o sistema ganha de graça:

- `blocos_por_dia` — a métrica que a coluna dele de fato responde. Meta inicial: **4 ou mais**
- `maior_intervalo_sem_caminhar` durante o dia — proxy direto do sentado prolongado
- O relatório semanal (N14) passa a poder dizer *"34 km na semana, mas média de 1,8 blocos por dia; a meta é
  4"*, que é acionável, enquanto "34 km" sozinho não é

**Cuidado com o atrito:** se registrar sessão der mais trabalho que digitar um número, ele para de registrar
e a gente perde o dado que já tinha. Duas defesas: manter um caminho rápido de "somar X km agora" que cria
uma sessão com o horário atual em um toque, e permitir a entrada antiga (total do dia) como sessão única,
sem bloquear — o dado fica pior, mas existe.

**Migração:** os registros históricos viram uma sessão única por dia, sem horário. `blocos_por_dia` fica
`null` para essas datas — e, pela mesma regra do N14, `null` aparece como "ainda não dá para dizer", nunca
como 1.

## Fora deste escopo

Ritmo e intensidade. Fazem diferença fisiológica real, mas custam atrito de registro e ele já tem dado
suficiente para decidir. Se um dia entrar, entra como campo opcional da sessão, nunca obrigatório.

---

# N21 (P1) — o botão "Recarregar" do `UpdatePrompt` não faz nada

Relatado pelo André no desktop: a faixa "Nova versão disponível" aparece, ele clica em **Recarregar** e não
acontece nada. **Fora do módulo Saúde** — é o componente que nasceu do B1.

## Diagnóstico

Não consegui reproduzir ao vivo: a faixa só aparece depois de um deploy real, e eu não posso forçar um. Então
isto é análise de código e configuração, e eu marco a confiança: **alta, mas não confirmada em execução.**

O `updateServiceWorker(true)` do `vite-plugin-pwa` faz, em essência:

```js
if (registration?.waiting) {
  await new Promise((resolve) => {
    navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true })
    registration.waiting.postMessage({ type: 'SKIP_WAITING' })
  })
}
if (reloadPage) window.location.reload()
```

Repare que o `reload()` está **depois** do `await`. Se o `controllerchange` nunca dispara, a promessa nunca
resolve, o `reload()` nunca roda e **o clique não produz efeito nenhum** — exatamente o sintoma descrito.

**Por que o `controllerchange` não dispara:** `SKIP_WAITING` faz o novo service worker *ativar*, mas uma
página que já está sendo controlada continua com o controller antigo até que o novo worker chame
`clients.claim()`. E o `clientsClaim` **não está ligado**: procurei em `vite.config.ts` e ele não aparece em
lugar nenhum. Com `registerType: "prompt"`, o `vite-plugin-pwa` **não** liga `clientsClaim` por conta própria
— quem liga por padrão é o modo `autoUpdate`, que vocês não usam (e com razão, porque foi essa escolha que
evitou recarregar no meio de um formulário).

Ou seja: o novo worker ativa, ninguém reivindica o cliente, o evento não vem, e o botão fica mudo. A faixa
continua na tela, o que faz parecer que o clique não registrou.

## Correção

**Uma linha, no `workbox` do `vite.config.ts`:**

```js
workbox: {
  clientsClaim: true,          // <— o que falta
  navigateFallbackDenylist: [/^\/__/],
  // ... resto igual
}
```

Manter `skipWaiting` **desligado** — é ele que garante que a versão nova só assume quando o André clica.
`clientsClaim` não muda isso: ele só faz o worker recém-*ativado* assumir o controle das abas abertas, que é
justamente o passo que falta.

**E vale um cinto de segurança no handler**, porque depender de um evento para uma ação que o usuário
disparou é frágil por natureza:

```jsx
onClick={async () => {
  const timeout = new Promise(r => setTimeout(r, 3000));
  await Promise.race([updateServiceWorker(true), timeout]);
  window.location.reload();
}}
```

Assim, no pior caso ele recarrega em 3 segundos sem o worker novo — a faixa reaparece, mas o botão **sempre**
faz alguma coisa. Um botão que às vezes não responde é pior que um que às vezes só recarrega.

## Verificação (30 segundos, quando houver um deploy)

DevTools → Application → Service Workers, com a faixa na tela. Clicar em Recarregar e observar:
- **Hoje (bug):** o worker em *waiting* passa a *activated*, mas a página continua com o controller antigo e
  nada acontece.
- **Depois da correção:** o controller troca e a página recarrega sozinha.

## Uma nota que não é sobre este bug

Este componente nasceu do **B1**, o dia da tela branca no módulo Saúde por service worker velho. O
`UpdatePrompt` foi a solução — e ela está com o último passo quebrado desde então, sem ninguém perceber,
porque a faixa aparece pouquíssimas vezes e some no recarregamento manual. **Vale pensar num teste que cubra
esse caminho**, já que é o mecanismo de escape de toda uma classe de problemas de cache.

---

# N16 (retificado) — o problema é o enunciado, não o horário

**Retratação parcial.** Eu tinha pedido para mover o check-in da manhã das 12:00 para as 06:00. Estava
errado, por um motivo que eu deveria ter visto: **a caminhada matinal dele é 4h30–5h30**, então às 06:00 o
check-in não capturaria "dor ao acordar" — capturaria dor pós-caminhada. Meu próprio argumento derrubava a
minha proposta. **Não mexa no horário.**

O André também deu a razão dele para as 12:00, e ela é boa: ao meio-dia ele já teve tempo de avaliar o nível
da dor, em vez de dar uma nota instantânea logo ao levantar, que é ruidosa.

**O problema real, que continua de pé:** o enunciado "dor da manhã" chegando ao meio-dia é ambíguo. Em alguns
dias ele responde como acordou, em outros a média da manhã, em outros como está agora. A série fica
inconsistente **sem dar nenhum sinal disso** — é o pior tipo de erro de dado, porque parece limpo.

## Correção 1 — ancorar a pergunta no evento (fazer, sem depender de nada)

Trocar o rótulo "dor da manhã" por uma pergunta ancorada:

> **"Que nota você dá para a dor nos primeiros minutos depois de levantar da cama, antes da caminhada?"**

Recordação de dor degrada muito ao longo de semanas e pouco ao longo de horas, e levantar da cama é um evento
marcante para ele. Com a âncora, o benefício de ter "internalizado" a dor vem sem o custo da deriva. Custo
para o usuário: zero — é só texto.

Vale ajustar o mesmo enunciado onde ele aparecer: check-in guiado do app, check-in guiado do Telegram e o
registro manual.

## Correção 2 — segunda pergunta, **dependente do OK do André**

Se o campo da manhã passa a ser explicitamente "ao levantar", abre espaço para uma segunda de um toque no
mesmo check-in:

> **"E depois da caminhada, como ficou?"**

A diferença entre as duas quantifica **o quanto caminhar analgesia** — que é a premissa central do plano dele
e hoje é só impressão. Se esse delta encolher ao longo de semanas, é sinal precoce de mudança clínica, e é o
tipo de coisa que o relatório semanal (N14) poderia acompanhar.

**Não implemente sem o "sim" dele.** É um slider a mais por dia, todo dia, e atrito diário é exatamente o que
mata aderência a registro. Eu já perguntei; quando ele responder, eu registro aqui.
