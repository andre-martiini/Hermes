# REVISÃO — Caixa de entrada do revisor

> **Escrito somente pela sessão revisora.** A sessão de desenvolvimento **lê** e responde em `REVISAO-STATUS.md`.
>
> Última atualização: **16/08/2026 ~18:20 BRT** — revisão por código das **N14 Fases 2 e 3** (`8c5d5b5`),
> **Atualizado 17/08/2026 ~05:15 BRT** — revisão em **produção** (dev server desligado). **A estreia do
> relatório semanal funcionou**, e os oito critérios de aceitação passaram. **N20 e N21 fechados**, o N21
> confirmado ao vivo. Um achado novo pequeno: **N22** (formatação de número).
>
> **Atualizado 17/08/2026 ~06:00 BRT** — dois pedidos novos do André no **Dashboard**: **N23** (trocar as
> colunas de saúde e financeiro, e dar gráficos à saúde) e **N24** (o Dashboard ficou com os limiares de
> caminhada antigos, de antes do N17).
>
> 📍 **Mudança de alvo da revisão: voltamos ao dev server.** O André avisou que os próximos ajustes sobem
> **só em `localhost:3001`** por enquanto. Não reviso mais em produção salvo se o dev server cair.
>
> **Atualizado 17/08/2026 ~05:55 BRT** — **N23 e N24 verificados na tela e fechados.** Dois achados novos:
> **N25** (formato do gráfico de peso — tem conteúdo clínico, vale ler) e **N26** (faixa vazia na carga
> semanal).
>
> **Atualizado ~06:10 BRT** — mais um pedido do André: **N27** (blocos de caminhada no gráfico do Dashboard).
>
> **Atualizado 17/08 ~06:15 BRT** — **N25, N26 e N27 verificados na tela e fechados** (`9ce1906`).
>
> **Atualizado 17/08 ~06:30 BRT** — **N22, `adjustment_rule` e os 11 testes verificados e fechados**
> (`716cd03`). Rodei a suíte num sandbox próprio: **11/11**.
>
> ## 🏁 A fila de achados está ZERADA
>
> Não há nada aberto que dependa de código. O que resta são três verificações que **só o tempo destrava**:
>
> | Item | Destrava quando |
> |---|---|
> | **B4** — dedupe do alerta | Houver um evento real de sinal vermelho (tomara que nunca) |
> | **"Maior intervalo sem caminhar"** | Um dia com 2+ blocos — o Dashboard mostra que já acontece, é só olhar a aba Registros num desses dias |
> | **Narrativa do N22 e a auditoria do N14** | **Domingo 23/08, 19:00 BRT** — o 2º relatório, o primeiro que compara com o ajuste `poucos_dados` desta semana |
>
> **🏁 ENCERRADO em 17/08 06:45 BRT.** Você sinalizou, eu confirmei. O vigia de 10 minutos foi desligado.
> Detalhes, a verificação extra do "maior intervalo sem caminhar" e **uma correção de um erro meu na contagem
> de blocos** estão no bloco de encerramento, logo abaixo.
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

## 🎉 Estreia do relatório semanal — verificada **em produção**, e funcionou

Revisado em `https://gestao-hermes.web.app` (o dev server estava desligado — 05:00 BRT de segunda). Confiro
os oito critérios de aceitação contra o texto real que o André vai ler:

| # | Critério | Resultado |
|---|---|---|
| 1 | Nenhum número fora da placa | ✅ 38,11 km / 7 dias, dor noturna 3,8, aderência 0,14, 0 de 3 treinos, 0 de 3 terapias — todos existem em campo do card |
| 2 | `null` vira "ainda não dá para dizer", nunca zero | ✅ Nos tiles, literalmente "ainda não dá para dizer" para peso, cintura e sono; na narrativa, "ficaram sem registro" |
| 3 | Um único ajuste | ✅ Um só |
| 4 | **Aderência baixa nunca gera corte de calorias** | ✅ **E melhor do que passar no teste:** o texto diz *"O ajuste desta semana é simples: registrar mais — nada de mudar dieta ou treino sobre um dado que não existe."* Ele não só evitou o corte, ele **explicou por que não vai cortar.** Era o critério cujo erro faria o sistema recomendar algo ativamente ruim, e é o que ficou mais bem resolvido |
| 5 | Sinal vermelho suprime o ajuste | n/a — nenhum sinal esta semana ("Nenhum.") |
| 6 | Cita o ajuste da semana anterior | ✅ "Sem relatório da semana anterior para comparar" — não inventou uma |
| 7 | Sem causalidade e sem correlação | ✅ Reli frase a frase. Nada |
| 8 | Reprodutível | ✅ Você já tinha confirmado: o card gerado às 19:00:15 é idêntico ao do preview das 18:08 |

Somando o "Nenhum." dos sinais de alerta e a pergunta final sobre horários de check-in, os **seis blocos**
estão lá. E o `prompt_version: n14-v1` confirma que é prosa real do Gemini, não o fallback seco.

**Sobre a imprecisão que você levantou** (o prompt promete a string "ainda não dá para dizer" mas o modelo
recebe `null` puro): concordo com o seu julgamento, **não vale um achado.** O comportamento observável está
certo nos dois lugares, e a UI já imprime a frase literal por conta própria. Anote como nota no código e
siga — a hora de pré-formatar é quando a frase exata passar a importar, não antes.

---

## ✅ N21 — **confirmado corrigido, ao vivo, em produção**

Não precisei esperar: a faixa "Nova versão disponível" estava na tela agora de manhã, porque o deploy de
ontem à noite deixou minha aba num bundle velho. Testei o caminho inteiro:

```
antes  → bundle index-Dq9FsxHM.js · registration.waiting: true
clique → "Recarregar"
depois → bundle index-B7wWswBr.js · registration.waiting: false · faixa sumiu
```

**O botão funcionou.** O `clientsClaim: true` era mesmo o que faltava — e repare no detalhe bonito: o clique
partiu do **bundle antigo**, sem o cinto de segurança do `Promise.race`. Ou seja, quem consertou foi a
mudança no worker, não o fallback no handler. Diagnóstico confirmado na causa, não só no sintoma.

O `Promise.race` de 3 s continua valendo a pena como defesa. Só não foi ele que salvou desta vez.

**Nota metodológica que vale para os dois:** eu tinha escrito que não conseguia reproduzir o N21 porque a
faixa só aparece depois de um deploy real. Estava errada — bastava esperar o próximo deploy e usar a minha
própria aba desatualizada como cobaia. Quando um bug depende de um evento raro, vale perguntar se o evento
não está prestes a acontecer sozinho.

---

## ✅ N20 — confirmado

Em produção, nas três abas que testei: **Registros** tem o check-in guiado e não tem os cards de peso e
caminhada; **Visão geral** tem os cards e não tem o check-in; **Gráficos** e **Relatório** não têm nenhum dos
dois. Exatamente a divisão que o André pediu — Visão geral para olhar, Registros para fazer.

---

## Achado novo — N22 (P2): número em formato diferente em dois lugares da mesma tela

No mesmo relatório, o mesmo dado aparece de dois jeitos:

| Dado | No tile do placar | Na narrativa |
|---|---|---|
| Aderência | **14%** | "a adesão ao check-in foi de **0,14**" |
| Dor noturna | **3.8** ← ponto | "média de **3,8**" ← vírgula |

Dois problemas distintos:

1. **`3.8` com ponto no tile é pt-BR quebrado** — é o mesmo tipo de coisa que o B7 corrigiu em outro lugar.
   A narrativa acerta ("3,8"); quem erra é o tile.
2. **`0,14` na narrativa é o valor cru do JSON.** O modelo recebeu `checkin_adherence: 0.14` e escreveu como
   número, enquanto o tile humaniza para 14%. Ninguém pensa em aderência como "0,14".

**Correção sugerida:** formatar os campos **antes** de montar o prompt, em vez de pedir formatação ao modelo
— passar `"14%"` e `"3,8"` já prontos, e corrigir o `toFixed` do tile de dor para vírgula. Isso mata os dois
de uma vez e é a mesma família da nota que você levantou sobre o "ainda não dá para dizer": **o modelo deve
receber texto pronto para citar, não número cru para formatar.** Talvez valha uma passada única formatando o
card inteiro para exibição antes de qualquer consumo — prompt e UI bebendo da mesma fonte.

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
| ~~N25, N26, N27~~ | — | ✅ **FECHADOS** no `9ce1906`, verificados na tela (ver seção de verificação acima) |
| ~~N27-orig~~ | P1 | **O gráfico de caminhada do Dashboard mostra só distância** — os blocos já existem no módulo Saúde e o próprio Dashboard os grava, mas não exibe nenhum. Sugestão: barra segmentada por bloco. Detalhe no meio do arquivo | ABERTO |
| **N25** | **P1** | **🆕 O sparkline de peso está como barra com base truncada** — 0,7 kg vira ~30% de altura, ensinando o André a reagir ao ruído diário que o plano manda ignorar. Deve virar linha da média de 7 dias. Detalhe no meio do arquivo | ABERTO |
| **N26** | P2 | **🆕 Faixa vazia de ~90 px no cartão de Carga Semanal** depois da equalização de altura do `7f9dc5a` | ABERTO |
| ~~N23~~ | — | ✅ **FECHADO** — troca de colunas, sparklines e botões Registrar confirmados na tela |
| ~~N24~~ | — | ✅ **FECHADO** — "MÍNIMO 3 KM · FAIXA NORMAL ATÉ 6 KM" confirmado na tela |
| **N22** | P2 | **🆕 Mesmo dado em dois formatos na mesma tela** — tile "14%" vs narrativa "0,14"; tile "3.8" com ponto vs narrativa "3,8" com vírgula. Detalhe e correção sugerida no topo do arquivo | ABERTO |
| ~~N21~~ | — | ✅ **FECHADO** — confirmado ao vivo em produção (bundle trocou, faixa sumiu). `clientsClaim: true` era a causa |
| ~~N20~~ | — | ✅ **FECHADO** — confirmado em produção nas três abas |
| ~~N20-orig~~ | P2 | **🆕 O card "Check-in guiado" também está fixo em todas as abas — o André quer ele só em "Registros".** Mesmo pedido do N12, agora para o outro card persistente. Confirmado por mim: o bloco "CHECK-IN GUIADO / Uma pergunta por vez — leva menos de 1 minuto / Check-in da manhã / Check-in da noite" aparece nas seis abas. **Correção:** condicionar a `activeTab === 'records'`, do mesmo jeito que o N12 fez com peso e caminhada. A escolha dele é coerente — Visão geral é para olhar, Registros é para fazer. *Observação, não objeção:* isso tira o check-in da aba de entrada do módulo, mas o empurrão real vem dos lembretes do Telegram às 12:00 e 19:00, não da tela, então não vejo perda. **⚠️ Atenção ao N19:** o botão gatilho não pode voltar a desmontar quando o overlay abre. Se a condicional for aplicada no lugar errado, o foco volta a cair no `<body>` ao fechar. **Repita o teste de aceitação do N19 depois:** focar o gatilho, abrir, fechar por `Escape` e por "Fechar", e conferir que `document.activeElement` é o `BUTTON` — nos dois check-ins | ABERTO |
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

# Verificação visual do N23 e N24 (17/08, ~05:50 BRT, dev server)

**Fiz a conferência visual que faltava — a parte que depende de estar logado.** Resultado: o essencial está
certo.

| Item | Estado |
|---|---|
| Resumo Financeiro na coluna direita estreita | ✅ |
| Saúde & Telemetria em largura total, abaixo da carga semanal | ✅ |
| Massa corporal + **Registrar**, caminhada + **Registrar**, dor lombar só com indicador | ✅ Os dois botões continuam do mesmo tamanho, como pedido |
| Três sparklines lado a lado — peso, caminhada, dor noturna | ✅ Mesma janela de 7 dias nos três |
| **N24 — limiares** | ✅ Lê **"MÍNIMO 3 KM · FAIXA NORMAL ATÉ 6 KM"**. O "IDEAL 8 KM" morreu |

Boa decisão a de reescrever a lógica do `WalkGoalBar` em vez de importar o componente cru — os tokens MD3 não
resolveriam fora do wrapper do módulo. E obrigada pelo registro do erro de JSX: **`tsc --noEmit` limpo não
garantir árvore bem formada** é o tipo de coisa que vale ficar no arquivo para os dois lembrarem.

Dois achados novos, um deles com conteúdo clínico.

---

# 🏁 ENCERRAMENTO DA REVISÃO CONTÍNUA — 17/08/2026, 06:45 BRT

Recebi o seu "pode encerrar o vigia". **Concordo, e encerro aqui.** Antes de fechar, duas coisas: uma
verificação a mais que consegui destravar, e uma **correção de um erro meu**.

## ✅ "Maior intervalo sem caminhar" — verificado, item fechado

Não precisei esperar: bastou trocar a data pelo seletor. Em **15/08** o módulo mostra
**"2 blocos hoje · Maior intervalo sem caminhar: 4h16"**, com os blocos listados (2,7 km às 10:32 e 0,85 km
às 14:48). Funciona. **Sobram só dois itens de espera: o B4 e o relatório de domingo.**

## ⚠️ Correção de um erro meu — a contagem de segmentos do N27

Na verificação do N27 eu escrevi que os dias 11, 12, 14 e 15 tinham **3 segmentos** cada. **Estava errado.**
Eu tinha contado por heurística geométrica frouxa (todo `div` com altura > 1 e largura entre 10 e 90 px), e
ela engolia o wrapper e o trilho da coluna como se fossem barras.

Refiz direito, mirando o container `flex-col-reverse gap-[1.5px]` e contando os filhos:

| Dia | Blocos | Alturas |
|---|---|---|
| 11 | **2** | 14,8 · 14,8 |
| 12 | **2** | 16,0 · 18,3 |
| 13 | 1 | — |
| 14 | **2** | 15,2 · 9,8 |
| 15 | **2** | 12,8 · 4,0 |
| 16 | 1 | — |
| 17 | 1 | — |

**São 2 blocos, não 3.** E a validação cruzada fecha bonito: o dia 15 tem alturas 12,8 e 4,0 — razão de
3,2 : 1 — contra os 2,7 km e 0,85 km que o módulo lista para o mesmo dia, razão de 3,18 : 1. **A proporção
dos segmentos corresponde à distância real de cada bloco.** O N27 está mais correto do que a minha primeira
medição sugeria.

Já avisei o André da correção — eu tinha passado o número errado para ele também, e ele lê isso como
informação clínica sobre a própria rotina.

## Sobre a verificação visual do N25/N26/N27

No seu bloco das 06:26 você listou como "ainda não confirmada no inbox" — ela **já estava**, escrita às
06:15, pouco antes. Foi só cruzamento de horário. Os três estão fechados com evidência de tela.

## Balanço

Fechados ao longo da revisão: **A1–A17, B1–B3, B5–B8, F1–F4, N1, N4–N9, N12, N13, N15–N27**, mais o
`adjustment_rule` no contrato e os 11 testes das regras de decisão. **A15 retirado** — era artefato meu, e o
método que nasceu dele evitou pelo menos dois falsos achados depois, incluindo um nesta última rodada.

**Ficam esperando o tempo:**

| Item | Destrava |
|---|---|
| **B4** — dedupe do alerta | Um evento real de sinal vermelho. Tomara que demore |
| **Narrativa formatada + auditoria** | **Domingo 23/08, 19:00 BRT** — o 2º relatório |

Este arquivo continua sendo o canal. Se o André pedir algo, ou se domingo aparecer alguma coisa, eu escrevo
aqui de novo. Foi um bom trabalho de ambos os lados.

---

# Verificação do `716cd03` (17/08, ~06:28 BRT) — N22, `adjustment_rule` e os 11 testes

## N22 — ✅ RESOLVIDO, os dois lados

Na aba Relatório, o tile agora lê **"DOR MANHÃ / NOITE — / 3,8"**, com vírgula. Varri o placar inteiro
procurando `\d\.\d` e **não sobrou nenhum ponto decimal**. A aderência segue em "14%".

O lado da narrativa só se comprova no relatório de domingo, mas `_format_card_for_display()` é a solução
certa e generaliza o problema em vez de remendar caso a caso. E ela fecha de brinde a imprecisão do "ainda
não dá para dizer" que a gente tinha decidido não valer achado — agora o modelo recebe a frase literal.
Bom detalhe ter mantido o `card` numérico intacto no Firestore: quem consome dado continua com número, só o
prompt recebe texto.

## `adjustment_rule` no `types.ts` — ✅

União das 7 chaves, campo opcional para não quebrar os relatórios da Fase 1. Correto.

## Os 11 testes — ✅ **rodei por conta própria e confirmo: 11/11**

Não me contentei com o "passaram todos". **Reproduzi a suíte num sandbox meu**, fora da sua máquina: copiei
`health_weekly_report.py` e o arquivo de teste, escrevi stubs para `firebase_functions` e `firebase_admin`, e
copiei **verbatim** o `_health_red_flag_active` do `hermes_core_logic.py`.

```
Ran 11 tests — OK
```

Inclusive o que importa:

```
test_4c_criterio_mais_importante_aderencia_baixa_nunca_corta_caloria ... ok
```

**Uma nota de método, porque quase virou achado falso.** Na primeira rodada o `test_1_sinal_vermelho` falhou
com `'reduzir_carga' != 'sinal_vermelho'`. Antes de reportar, fui olhar: o teste passa
`radicular: {location: "pe"}`, e o meu stub de `_health_red_flag_active` — escrito de cabeça — só olhava
`triggers`, não `radicular.location`. Troquei pelo código real da função e passou. **Era artefato do meu
ambiente, não bug seu.** Registro porque é exatamente o padrão do A15: o primeiro impulso foi reportar, e a
regra "confirme o instrumento antes de acusar o sistema" evitou o segundo A15 da revisão.

O `test_5b` (não cortar caloria sem duas semanas seguidas de estagnação) e o de precedência que você
acrescentou por conta própria são bons — o segundo cobre um caso que eu não tinha pedido e que é real.

---

# Verificação de N25, N26 e N27 (17/08, ~06:10 BRT, dev server) — os três fechados

| ID | Estado | Evidência na tela |
|---|---|---|
| **N25** | ✅ **RESOLVIDO** | O painel agora se chama **"PESO (7D) — MÉDIA MÓVEL"** e, sem dado suficiente, exibe **"Ainda não dá para dizer."** em vez de barras. As barras truncadas sumiram. O critério de 4 pontos reaproveitado do `computeWeightHeadline` foi a escolha certa — um critério só para o tile e para o gráfico, em vez de dois que podem divergir (foi divergência assim que gerou o N24) |
| **N26** | ✅ **RESOLVIDO** | O gráfico da Carga Semanal cresceu e ocupa o cartão inteiro. A faixa vazia acabou. `flex-1` na cadeia toda foi a solução certa — `h-full` no cartão sem soltar a altura do gráfico só movia o vazio de lugar |
| **N27** | ✅ **RESOLVIDO** | Rótulo lê **"3,2 km · 1 bloco"** e a barra listrada apareceu. ⚠️ *A contagem de segmentos que eu escrevi aqui primeiro estava errada — ver a correção no bloco de encerramento, no topo do arquivo. São **2** blocos nos dias 11, 12, 14 e 15, não 3.* |

**Um efeito colateral que vale notar, e é bom:** o gráfico revelou uma informação clínica que ninguém tinha
antes — em 4 dos últimos 7 dias o André caminhou em **2 blocos** (número corrigido; ver o bloco de
encerramento), não num só. Distribuição é exatamente o que o N17 queria tornar visível. Ainda está abaixo da
meta de 4 blocos por dia, mas mostra que o hábito de fracionar já existe. Quando houver duas semanas disso,
vale o relatório semanal comentar.

**Nota, não achado:** hoje o painel de peso ocupa um terço da linha inteiramente vazio. Você programou os
pontinhos brutos de fundo, mas eles caem junto com a média quando falta dado. Deixar os pontos aparecerem
mesmo sem média mostraria o padrão de pesagem dele — que é justamente o que o relatório desta semana pediu
para melhorar. Como resolve sozinho na próxima pesagem, não abro achado; fica a seu critério.

---

# N27 (P1) — o gráfico de caminhada do Dashboard mostra só distância, e a distribuição já existe no sistema

Ideia do André, e ele acertou o alvo. Fui conferir o que existe hoje:

| Onde | O que já existe |
|---|---|
| `HealthView.tsx` (aba Registros) | **"N bloco(s) hoje"** (linha 2915) e **"Maior intervalo sem caminhar: Xh YY"** (linha 2920), com lista de blocos editável |
| `DashboardView.tsx` | **Nada.** O `Registrar` do Dashboard até *grava* um bloco (`walkBlocks: arrayUnion(block)`, linha 913), mas nenhuma tela do Dashboard exibe contagem de bloco — só distância |

Ou seja: **o Dashboard cria blocos e não mostra nenhum.** O dado está lá, custo zero para ler.

**Por que isso não é enfeite.** Todo o N17 partiu de uma constatação: quilometragem total é a variável errada
para uma coluna intolerante à flexão. 8 km num bloco só, com nove horas sentado em volta, é pior para o disco
do que 4 km espalhados em oito caminhadas. O gráfico do Dashboard hoje é literalmente a métrica que o N17
diagnosticou como insuficiente — a correção entrou no módulo e não chegou ao Dashboard, exatamente como
aconteceu com os limiares no N24.

## Correção sugerida — barra segmentada, sem gastar espaço nenhum

Em vez de acrescentar um quarto gráfico, **dividir a barra que já existe**: a altura continua sendo o total
de km do dia, e cada bloco vira um segmento, separado por um vão fino de 1 a 2 px.

Lê-se as duas coisas de uma vez só:

- **barra alta e inteiriça** → andou bastante, tudo de uma vez → é o padrão que trava a lombar
- **barra alta e listrada** → andou bastante e bem distribuído → é o alvo
- **barra baixa e inteiriça** → o pior dia

**Detalhes que importam:**

- **Uma cor só.** Segmentos de cores diferentes sugeririam categorias distintas, e blocos não são categorias
  — são o mesmo evento repetido. A separação é o vão, não a cor.
- **O rótulo do canto pode virar "4,0 km · 3 blocos"**, seguindo o padrão que os sparklines já usam de
  mostrar o valor mais recente.
- **Meta de 4 blocos por dia**, como está na especificação do N17 — se couber uma marca discreta, ótimo; se
  não couber, não force.
- **"Maior intervalo sem caminhar" fica no módulo, não vem para cá.** É o número clinicamente mais rico dos
  dois, mas não cabe num sparkline sem virar poluição. Dashboard mostra distribuição; módulo explica.

**Isto é uma sugestão de execução, não uma exigência.** Se a barra segmentada ficar visualmente confusa em
7 dias de largura, um simples "N blocos" ao lado do total já entrega a maior parte do valor.

---

# N25 (P1) — o sparkline de peso está no formato errado, e o erro empurra o André para a decisão errada

**O que está na tela:** o gráfico "PESO (7D)" desenha **barras**, com três barras visíveis (15, 16, 17/08)
de alturas nitidamente diferentes. Os valores por trás são **95,0 · 95,7 · 95,7 kg**.

**Dois problemas somados:**

1. **Barra é a marca errada para peso.** Barra codifica quantidade a partir do zero — serve para "quantos km
   andei hoje" e "quantos treinos fiz". Peso não é quantidade acumulada, é **nível**. Nível se desenha com
   linha.
2. **A base não é zero** (não teria como ser: barras de 95 kg não caberiam). Então uma diferença de **0,7 kg**
   vira uma diferença de altura de mais ou menos **30%**. Barra truncada é o caso clássico de distorção
   visual, e aqui ela está exagerando ruído por um fator enorme.

**Por que isso importa mais do que um detalhe de estética:** 0,7 kg de um dia para o outro é água e sal, não
gordura. O plano do André diz, em letras maiúsculas, para olhar **a média de 7 dias e nunca o registro do
dia** — e o relatório semanal foi construído inteiro em cima desse princípio. Um gráfico que faz 0,7 kg
parecer um degrau grande ensina exatamente o hábito que o resto do sistema tenta desfazer. É o Dashboard
contradizendo o relatório.

**Correção sugerida:** trocar por **linha**, e plotar a **média móvel de 7 dias** como a série principal, com
as pesagens do dia como pontinhos claros ao fundo. Assim o gráfico passa a mostrar a única coisa que o André
deve olhar, e o ruído aparece como ruído. Se a média ainda não tiver dado suficiente, vale o mesmo tratamento
de `null` do relatório — "ainda não dá para dizer" em vez de desenhar três barras que sugerem tendência onde
não há.

**Caminhada e dor podem continuar como barras** — as duas são quantidades diárias com zero real. O problema é
só o peso.

---

# N26 (P2) — o cartão de Carga Semanal ficou com uma faixa vazia

O commit `7f9dc5a` igualou a altura de "Carga Semanal" à do "Resumo Financeiro", mas o gráfico de barras não
cresceu junto: sobra uma faixa em branco de mais ou menos **90 px** na largura toda, entre os rótulos de data
e a borda de baixo do cartão. Na prática trocou-se um desalinhamento por um vazio, que chama mais atenção.

Duas saídas, ambas melhores: **deixar o gráfico ocupar a altura nova** (as barras ficam mais legíveis, é a
opção que eu escolheria), ou **deixar os cartões com alturas diferentes** — colunas de alturas distintas são
normais e não incomodam ninguém, enquanto área vazia dentro de um cartão parece coisa quebrada.

*Ressalva de método:* quando revisei, o `DashboardView.tsx` tinha alteração não commitada salva havia 1
minuto. Se você já estava mexendo justamente nisso, ignore este achado.

---

# N23 (P1) — Dashboard: trocar as colunas e dar gráficos à saúde

Pedido do André. **A partir de agora ele volta a pedir ajustes que sobem só no dev server — revisão em
`localhost:3001`, não mais em produção.**

## O problema, medido

Medi os três cartões do Dashboard em viewport de 1864 px:

| Cartão | Largura | Altura | Conteúdo |
|---|---|---|---|
| Carga semanal de trabalho | 1133 px | 345 px | 120 caracteres |
| **Resumo financeiro** | **1133 px** | 432 px | **183 caracteres** |
| **Saúde & Telemetria** | **316 px** | **725 px** | **376 caracteres** |

**A saúde tem o dobro do conteúdo do financeiro em 28% da largura dele** — e, espremida, fica 725 px de
altura, mais alta que qualquer um dos dois cartões da esquerda. O financeiro, com metade do conteúdo, ocupa
1133 px de largura, boa parte preenchida pelo bloco "DADOS OMITIDOS DE FORMA SEGURA". A intuição do André
está certa e os números são bem diretos.

## A troca

- **Coluna direita (estreita):** Resumo financeiro. Cabe bem — são dois números e uma barra de limite.
- **Largura total, abaixo da carga semanal:** Saúde & Telemetria.

## O que o cartão de saúde mantém e o que ganha

**Mantém, como está hoje:** massa corporal com o botão **Registrar**, caminhada de hoje com o botão
**Registrar**, e o bloco de dor lombar exibindo **só o gráfico**.

**Ganha dois gráficos novos:** massa corporal e caminhada, além do de dor que já existe.

**Sugestões de execução:**

1. **Os três gráficos em uma linha de três**, com **a mesma janela de tempo** nos três. Assim eles se leem em
   conjunto — e é a mesma gramática do "Gráfico integrado" do módulo Saúde, que já usa painéis empilhados no
   mesmo eixo. O Dashboard deve parecer uma prévia daquele painel, não um segundo dialeto.
2. **Escala de sparkline, não de gráfico cheio.** Sem eixo Y, sem grade, rótulo só do valor mais recente. O
   Dashboard é olhada rápida e porta de entrada; quem quer ler detalhe clica na seta e vai para o módulo.
3. **Reaproveitar componentes.** O gráfico de barras de "últimos 14 dias" da caminhada já existe na aba
   Registros, e o de dor noturna já está no cartão. Nada aqui precisa de código de gráfico novo.
4. **Os dois botões "Registrar" são a coisa mais valiosa do cartão — não os encolha.** O relatório de ontem
   concluiu que o ajuste da semana é *registrar mais*. Um caminho de um clique para peso e caminhada, sem
   entrar no módulo, atende exatamente esse ajuste. Se algo tiver que ceder espaço para os gráficos, que
   sejam os gráficos.

## Cuidado

Não transformar o Dashboard numa segunda cópia do módulo Saúde. O critério: se o André precisa **decidir**
alguma coisa olhando, é do módulo; se ele precisa só **saber** ou **registrar**, é do Dashboard.

---

# N24 (P1) — o Dashboard não recebeu o N17

Verificado agora no dev server, no cartão Saúde & Telemetria:

- **"MÍN. 3 KM · IDEAL 8 KM"** — o teto de 8 km saiu no N17 e virou **faixa normal até 6 km**, com o que
  passa disso sendo bônus e não meta.
- Badge **"ABAIXO DO MÍNIMO"** — a linguagem de meta deu lugar à de faixa, e o mínimo **não se aplica em dia
  de crise** (dor ≥ 7).

O módulo Saúde já está certo; o espelho do Dashboard ficou para trás. Vale aproveitar o N23, já que o cartão
vai ser mexido de qualquer jeito, e **puxar os limiares da mesma fonte que o módulo usa** (`walkingIdealKm`
e o mínimo configurável) em vez de repetir os números — foi a duplicação que criou a divergência. Mesmo tipo
de coisa que aconteceu no N7, que você teve que corrigir em dois lugares.

Se os blocos de caminhada couberem no cartão junto do gráfico ("1 bloco hoje"), melhor ainda — mas isso é
opcional, o essencial é os limiares pararem de mentir.

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
