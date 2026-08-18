# REVISÃO — Status do desenvolvimento

> **Escrito somente pela sessão de desenvolvimento.** A sessão revisora **lê** este arquivo e **não escreve**
> nele. Os achados chegam por `REVISAO-INBOX.md`.
>
> Acrescente blocos novos **no topo**, logo abaixo desta linha. Não apague o histórico.

---

## Como preencher

Copie o modelo abaixo a cada checkpoint. Os dois campos que mais importam para o revisor são
**`Estável para revisão`** e **`Telas afetadas`** — é o que evita revisão em cima de código pela metade e o
que faz a revisão ir direto ao ponto.

```markdown
## CHECKPOINT — AAAA-MM-DD HH:MM

**Estável para revisão:** sim | não (ainda editando)
**Fase:** <qual fase do escopo>
**Arquivos alterados:** <lista>
**Telas afetadas:** <onde olhar, com o caminho na interface>
**Precisa de deploy:** não | sim (Cloud Functions / índices / regras)

### Achados endereçados
| ID | Estado | Nota |
|---|---|---|
| A1 | RESOLVIDO | <o que foi feito> |
| A6 | NÃO PROCEDE | <por quê> |
| F1 | ADIADO | <motivo e para quando> |

### Fora da lista
<mudanças que não vieram de nenhum achado — o revisor não sabe que existem se não estiverem aqui>

### Dúvidas para o revisor
<perguntas, decisões de produto em aberto, trade-offs que você quer validar>
```

**Sobre `NÃO PROCEDE`:** é uma resposta legítima e esperada. O revisor enxerga o app rodando, não o código —
ele erra. Se um achado estiver tecnicamente errado, marque assim com a justificativa; ele não será reaberto
sem evidência nova.

---

## CHECKPOINT — 2026-08-17 07:25 — data do último registro de peso no Dashboard

**Estável para revisão:** sim
**Fase:** pedido direto do André, fora da fila do inbox (vigia já encerrado)
**Arquivos alterados:** `DashboardView.tsx`
**Telas afetadas:** Dashboard, card "Saúde & Telemetria" — tile de peso
**Precisa de deploy:** não, só frontend — commitado, buildado local e pushado sem esperar o GitHub Actions

"Último registro: 95,7 kg" não dizia se era de ontem ou do mês passado. Adicionado `formatRegisteredWhen()`:
mostra "hoje" / "ontem" / "DD/MM" para datas mais antigas, ao lado do valor — reaproveitando
`latestRawDate`, que `computeWeightHeadline` já retornava (só não estava sendo exibido). `tsc` e
`npm run build` locais limpos antes do commit (`f2cda6a`).

### Fora da lista
Nenhuma.

---

## ✅ CONFIRMADO — 2026-08-17 06:29 — pode encerrar o vigia

Recebido: N22, `adjustment_rule` e os 11 testes fechados do seu lado também (rodou a suíte num sandbox
próprio, 11/11 — obrigado por conferir de novo, independente). **Concordo que é um bom ponto de parada.**

Os três itens que restam são exatamente os que você listou, e nenhum dos três precisa de mim agora:
- **B4** — só um evento clínico real destrava, e não vou simular isso.
- **"Maior intervalo sem caminhar"** — passivo, aparece sozinho no primeiro dia com 2+ blocos.
- **Narrativa do N22 + auditoria do N14** — domingo 23/08, 19:00 BRT.

**Pode encerrar o vigia.** Do meu lado o `/loop` de 10 minutos continua rodando (baixo custo, só lê o arquivo
e confirma "sem novidade" quando não há nada) — não preciso que você continue revisando em paralelo por
enquanto. Se o André pedir algo novo ou eu precisar de outro par de olhos, escrevo aqui de novo.

---

## 🏁 FILA ZERADA — 2026-08-17 06:26 — nada mais para o desenvolvimento fazer por enquanto

**Deploy do commit `716cd03` confirmado** (`Deploy Firebase` ✓, 7m5s). Com isso, **todo item endereçável da
fila que estava listada no `REVISAO-INBOX.md` foi implementado, testado e implantado**: N19 (resto), N14
Fases 2 e 3, N20, N21, N22, N23, N24, N25, N26, N27, `adjustment_rule` no `types.ts`, e o teste das 6 regras
de decisão.

**O que resta não é trabalho pendente, é espera:**
- **B4** — dedupe do alerta de sinal vermelho — só é observável num evento clínico real; não posso simular
  isso com segurança nem faz sentido forçar.
- **A verificação visual de N25/N26/N27** — já pedida no seu lado, ainda não confirmada no inbox.
- **O relatório da Semana 34** (próximo domingo, 23/08) — é a próxima vez que dá pra ver a narrativa do
  Gemini rodando com os números pré-formatados do N22 na prática, e não antes disso.

**Não é necessário continuar checando este arquivo a cada passada enquanto não houver achado novo.** Se
algo novo aparecer no `REVISAO-INBOX.md` — um pedido do André, um bug encontrado na verificação visual, ou
a checagem do relatório de domingo — eu processo normalmente. Até lá, sessão de desenvolvimento em espera.

---

## CHECKPOINT — 2026-08-17 06:18 — N22, `adjustment_rule` no contrato, e os 6 testes sintéticos

**Estável para revisão:** sim
**Fase:** N22 (formatação de número) + os dois itens de manutenção que sobraram na fila (`adjustment_rule`,
teste das 6 regras)
**Arquivos alterados:** `HealthView.tsx`, `types.ts`, `functions/health_weekly_report.py`,
`functions/test_health_weekly_report.py` (novo)
**Telas afetadas:** aba "Relatório" do módulo Saúde (tile "Dor manhã/noite") — a narrativa do Gemini só muda
de verdade no próximo relatório (domingo que vem), já que o de hoje já foi gerado
**Precisa de deploy:** sim (Cloud Function, o prompt mudou) — disparado, acompanhando em background

### N22 — os dois lados do descompasso

**Tile:** "Dor manhã/noite" na aba Relatório usava interpolação crua (`${card.pain_evening_avg}`), por isso
saía "3.8" com ponto. Troquei para `toFixed(1).replace('.', ',')`, igual ao resto da tela.

**Narrativa:** o modelo recebia o `card` inteiro como JSON cru (`checkin_adherence: 0.14`) e escrevia
"0,14" — número certo, formato que ninguém usa para aderência. Adicionei `_format_card_for_display()` em
`health_weekly_report.py`: converte o card inteiro pra texto pronto antes de montar o prompt — `"14%"`,
`"3,8/10"`, `"38,1 km"`, `"ainda não dá para dizer"` para `null` (isso também fecha, de vez, a imprecisão que
você e eu já tínhamos discutido e decidido não valer achado — agora o modelo recebe a frase literal, não só o
comportamento observável bate). **O `card` numérico que vai pro Firestore continua intacto** — só o prompt
usa a versão formatada; a UI segue formatando os próprios tiles a partir do card cru, como sempre fez.
Testei `_format_card_for_display()` isolado contra os valores reais do card de ontem (`checkin_adherence:
0.14`, `pain_evening_avg: 3.8`) — saiu `"14%"` e `"3,8/10"`, exatamente o formato esperado.

### `adjustment_rule` no `types.ts`

`HealthWeeklyReportAdjustmentRule` — união das 7 chaves possíveis (`sinal_vermelho` · `reduzir_carga` ·
`poucos_dados` · `aderencia` · `cortar_kcal` · `aumentar_kcal` · `manter`), campo opcional em
`HealthWeeklyReport` (ausente nos relatórios da Fase 1, antes de a Fase 2 existir).

### Teste das 6 regras — o que você pediu, incluindo o caso que mais importa

`functions/test_health_weekly_report.py`, 11 testes com cards sintéticos. O que interessa de verdade:
`test_4c_criterio_mais_importante_aderencia_baixa_nunca_corta_caloria` — card com `weight_delta >= 0` nas
duas semanas (dispararia `cortar_kcal` sozinho) **e** `checkin_adherence` alta o bastante pra passar o
primeiro filtro, mas `strength_done = 1`. Resultado: `aderencia`, nunca `cortar_kcal`. Rodei os 11 —
passaram todos, incluindo um de precedência que não estava no seu pedido mas achei que valia (radicular
descendo vence poucos_dados quando os dois coincidem).

### Testado

`tsc --noEmit` limpo, `npm run build` local sem erro, `functions/venv/Scripts/python.exe -c "import main"`
limpo, os 11 testes sintéticos passando, `_format_card_for_display` conferido manualmente contra os valores
reais do card de ontem.

### Achados endereçados
| ID | Estado | Nota |
|---|---|---|
| N22 | RESOLVIDO | Tile com vírgula; narrativa recebe texto pré-formatado, não número cru |
| `adjustment_rule` | RESOLVIDO | Promovido ao `types.ts`, tipado como união das 7 chaves |
| Teste das 6 regras | RESOLVIDO | 11 testes, incluindo o de precedência aderência-vs-corte-calórico |

### Fora da lista
Um teste de precedência a mais (radicular descendo vs. poucos dados) que não estava pedido — achei barato e
relevante o bastante pra incluir junto.

### Dúvidas para o revisor
Nenhuma decisão pessoal do André pendente. Com isto, a fila do inbox que você tinha listado como "toda P2,
nada quebrado" fica endereçada por completo — só resta o B4, que segue aguardando um evento real de sinal
vermelho para ser observável (não é algo que eu consiga forçar ou testar sinteticamente sem risco).

---

## CHECKPOINT — 2026-08-17 06:01 — N25, N26 e N27: peso em linha, gráfico da carga cresce, caminhada segmentada

**Estável para revisão:** sim
**Fase:** N25 (formato do sparkline de peso), N26 (faixa vazia na Carga Semanal), N27 (blocos de caminhada
no gráfico do Dashboard)
**Arquivos alterados:** `DashboardView.tsx`
**Telas afetadas:** Dashboard — cartão "Saúde & Telemetria" (sparkline de peso e de caminhada) e cartão
"Carga Semanal de Trabalho" (gráfico de barras)
**Precisa de deploy:** não é Cloud Function, é só frontend — **commitei, buildei local e pushei sem esperar
o GitHub Actions terminar**, conforme combinado agora. Aviso aqui se o build local tivesse falhado; não
falhou.

### O que mudou

**N25:** o sparkline de peso desenhava barras com base diferente de zero — 0,7 kg de ruído (água/sal) virava
uns 30% de diferença de altura, ensinando exatamente o hábito que o relatório semanal tenta desfazer (olhar
a média de 7 dias, nunca o registro isolado). Troquei para linha: `MiniSparkline` ganhou `variant="line"`,
plotando a **média móvel de 7 dias** (mesmo limiar de 4 pontos que o `computeWeightHeadline` já usa no tile
de cima, pra não inventar critério novo) como a série principal, com os registros brutos do dia como
pontinhos claros de fundo. Sem dado suficiente, cai em "Ainda não dá para dizer" em vez de desenhar uma linha
com ruído. Caminhada e dor continuam como barra — são quantidade diária com zero real, o problema era só o
peso.

**N26:** o `h-full` do commit anterior esticou o cartão mas o gráfico de barras da Carga Semanal ficava em
altura fixa (`h-40`/`h-32`), sobrando a mesma faixa vazia só que agora *dentro* do cartão em vez de embaixo
dele. Troquei a cadeia inteira para `flex-1` (conteúdo → grid → barra), então o gráfico agora ocupa a altura
de verdade — era a opção que o revisor preferia entre as duas que ele sugeriu.

**N27:** o Dashboard grava blocos de caminhada (o botão "Registrar" já faz isso desde sempre) mas só exibia
distância total — a métrica que o próprio N17 tinha diagnosticado como insuficiente. `MiniSparkline` ganhou
`segmentsFor`: quando presente, cada bloco do dia vira um segmento empilhado na mesma barra, mesma cor,
separados por um vão de ~1,5px — barra listrada = dia bem distribuído (o alvo), inteiriça = tudo de uma vez.
O rótulo virou "X km · Y blocos". "Maior intervalo sem caminhar" fica só no módulo, como o achado pedia.

### Testado

`@babel/parser` (mesmo parser do Vite) limpo, `tsc --noEmit` sem erro novo, **`npm run build` local completo
e sem erro** antes do commit — não só o `tsc` desta vez.

### Achados endereçados
| ID | Estado | Nota |
|---|---|---|
| N25 | RESOLVIDO | Linha + média móvel de 7 dias + pontos de fundo, mesmo limiar do tile |
| N26 | RESOLVIDO | Gráfico cresce com `flex-1` em vez de sobrar vão vazio |
| N27 | RESOLVIDO | Barra segmentada por bloco, rótulo "X km · Y blocos" |

### Fora da lista
Nenhuma mudança fora do que foi pedido.

### Dúvidas para o revisor
Nenhuma decisão pessoal do André pendente aqui. Como sempre, não consigo confirmar visualmente (login do
Google) — código e build estão limpos, mas a leitura real do gráfico de peso em linha e da barra listrada de
caminhada depende do seu olho.

---

## CHECKPOINT — 2026-08-17 05:37 — N23 e N24: Dashboard trocado, sparklines novos, limiares corrigidos

**Estável para revisão:** sim
**Fase:** N23 (trocar colunas + gráficos) e N24 (limiares pós-N17) do Dashboard
**Arquivos alterados:** `DashboardView.tsx`
**Telas afetadas:** Dashboard (tela inicial) — "Resumo Financeiro" agora na coluna direita estreita,
"Saúde & Telemetria" em largura total abaixo de "Carga Semanal de Trabalho"
**Precisa de deploy:** sim (frontend) — commit `648f333` já pushado; **ainda não disparei o deploy**, ver nota
sobre o dev server abaixo

### O que mudou

**N23:** troquei as colunas exatamente como pedido — Financeiro estreito à direita, Saúde em largura total.
O cartão de saúde ganhou dois gráficos novos (peso e caminhada), ao lado do de dor que já existia, os três
como sparklines compactos (`MiniSparkline`, componente novo: sem eixo, sem grade, só o valor mais recente
rotulado) na mesma janela de 7 dias corridos — troquei a lógica de "últimos 7 registros com dado" (que podia
espalhar datas de forma desalinhada entre peso/caminhada/dor) por "últimos 7 dias do calendário", pra garantir
que os três realmente se leem em conjunto, como você pediu. Os dois botões "Registrar" continuam do mesmo
tamanho — não encolhi.

**N24:** o cartão usava `walkGradientColor`/`walkMetIdeal`/`walkMetMinimum`, um modelo de duas cores com
`walkingIdealKm ?? 8` — exatamente o que você mediu como divergente do módulo Saúde. Troquei pela mesma
lógica de faixa normal + bônus + exceção de dia de crise (`isCrisisToday` a partir de `pain.crisis` do dia),
com `walkingIdealKm ?? 6` batendo com o default do `HealthView.tsx`. Não importei o componente `WalkGoalBar`
do módulo Saúde diretamente — ele usa os tokens de cor MD3 (`bg-primary-container`, `text-on-surface` etc.)
que só resolvem dentro do wrapper CSS do módulo Saúde; importá-lo cru quebraria a estética no Dashboard, que
usa outra paleta (slate/roxo/mono). Reescrevi a mesma lógica de decisão (crise/bônus/mínimo) com as classes
Tailwind nativas do Dashboard — mesmos números e mesma regra, visual consistente com o resto da tela.

### Um bug que vale registrar — TypeScript não pegou, só o parser real do Babel

Na hora de mover os cartões de coluna, contei os `<div>` fechados de cabeça e errei por um: sobrou um
`</div>` a mais fechando o wrapper que devia continuar aberto para envolver o cartão de largura total, o que
quebrava o parse. **`tsc --noEmit` não acusou nada** — rodei duas vezes, incluindo depois da reestruturação
inteira, e ficou limpo nas duas. Só descobri porque o dev server real (`vite:react-babel`) rejeitou o módulo
com "Unexpected token, expected ','" e o console do navegador mostrou erro 500 ao vivo. Corrigi contando via
`@babel/parser` num script Node direto (`babel.parse(code, {plugins: ['jsx','typescript']})`), que reproduz
exatamente o parser que o Vite usa — bisseção manual por regex de `<div>`/`</div>` não funciona nesse arquivo
porque o conteúdo tem comparações (`day.count > 0`) dentro de atributos JSX, e o `>` solto confunde qualquer
contagem ingênua. **Lição para os dois:** `tsc --noEmit` limpo não é garantia de JSX bem formado — depois de
mexer estruturalmente numa árvore grande, vale checar o HTTP real do módulo no dev server (ou parsear com
Babel direto) antes de considerar terminado.

### Não consegui verificar visualmente — mesmo motivo de sempre

Sem as credenciais do André para o login do Google, não passo da tela de entrada em `localhost:3001` — isso
sempre foi seu lado do trabalho ao longo de toda a revisão. Confirmei que o app carrega até a tela de login
sem crash (nada de tela branca), que o módulo compila (HTTP 200 em `/DashboardView.tsx`) e que o parser real
aceita o arquivo — mas o layout de fato (colunas, sparklines, cores do badge de caminhada) ainda não foi
visto por ninguém. Preciso que você confirme visualmente antes de eu considerar N23/N24 resolvidos de
verdade.

**Ainda não disparei o deploy de produção** — só empurrei o commit pro GitHub. Vou aguardar sua primeira
passada no dev server antes de mandar pra produção, já que é mais barato corrigir algo visual agora do que
depois de um deploy.

### Achados endereçados
| ID | Estado | Nota |
|---|---|---|
| N23 | EM ANDAMENTO | Código pronto e no dev server; aguardando sua verificação visual antes do deploy |
| N24 | EM ANDAMENTO | Mesma coisa — limiares corrigidos, mas quero seus olhos no badge/barra antes de fechar |

### Fora da lista
Nenhuma mudança fora do que foi pedido.

### Dúvidas para o revisor
Nenhuma decisão pessoal do André pendente. Só peço a verificação visual de N23/N24 antes do deploy — veja a
nota acima sobre o bug que o `tsc` não pegou; quero um segundo par de olhos antes de considerar pronto.

---

## CHECKPOINT — 2026-08-16 19:07 — ESTREIA: relatório semanal gerado com sucesso, Fases 1/2/3 confirmadas ao vivo

**Estável para revisão:** sim
**Fase:** N14 — verificação real da execução agendada das 19:00 BRT
**Arquivos alterados:** nenhum (só consulta ao Firestore)
**Telas afetadas:** aba "Relatório" do módulo Saúde deve mostrar o conteúdo abaixo agora
**Precisa de deploy:** não

**`health_weekly_reports/2026-W33` existe, gerado às 19:00:15 BRT (`generated_at` UTC bate exatamente com o
horário do gatilho, 15s de atraso). Sucesso completo — as três fases funcionaram juntas, ao vivo, na
estreia.**

### O que confirmei, campo a campo

- **`card`:** idêntico ao que o `preview_weekly_report.py` já tinha mostrado às 18:08 — `weight_avg7: null`,
  `checkin_adherence: 0.14`, `km_total: 38.11`, `km_days: 7`, `strength_done: 0/3`, `therapy_done: 0/3`,
  `radicular_trend: sem_dado`. Reprodutível, como pedia o critério 8.
- **`adjustment_rule`: `"poucos_dados"`** — exatamente a regra esperada, confirmada contra dado real de novo.
- **`adjustment`:** o texto seco da Fase 2, igual ao que testamos no preview.
- **`audit`: `null`** — correto, é o primeiro relatório da história, não há semana anterior para comparar.
- **`prompt_version`: `"n14-v1"`** — **o Gemini respondeu.** Não caiu no fallback seco; a narrativa que está
  no campo `text` é a prosa real do modelo, a parte que eu não tinha como testar antes de hoje.
- **`text`:** seis blocos reconhecíveis (o que aconteceu, o número que importa, o ajuste, "Nenhum" para
  sinais de alerta, "Sem relatório da semana anterior para comparar" para a auditoria, e a pergunta final
  sobre horários de check-in). Todos os números citados batem com o `card` — km total, dor noturna média,
  aderência, treino e terapia. Nenhuma causa afirmada, nenhuma correlação, um único ajuste.

### Uma imprecisão pequena, não bloqueante, para registrar

O prompt da Fase 3 instrui o modelo a manter literalmente "ainda não dá para dizer" quando um campo chega
`null` — mas eu passo o `card` como JSON puro pro modelo, com `null` de verdade, nunca essa string pronta.
O modelo se saiu bem mesmo assim (escreveu "ficaram sem registro" para peso/cintura/dor matinal/sono — não
inventou número nem zero, então o critério 2 continua satisfeito), mas o enunciado do prompt promete uma
frase exata que ele nunca recebe pronta. Se algum dia a frase literal importar (ex.: para casar com o texto
da UI), o jeito certo é pré-formatar os campos `null` do card como a string antes de montar o prompt. Não
mexo agora — funcionando como está.

### Achados endereçados
| ID | Estado | Nota |
|---|---|---|
| N14 (geração real) | RESOLVIDO | Documento gerado às 19:00:15 BRT, `prompt_version: n14-v1` — narrativa real do Gemini, não fallback |

### Fora da lista
Nenhuma.

### Dúvidas para o revisor
Nenhuma decisão pessoal do André pendente. Fica ao seu critério decidir se vale abrir um achado P2 para a
imprecisão do "ainda não dá para dizer" acima, ou só anotar como nota — não achei que justificasse prioridade
maior dado que o resultado prático já está correto.

---

## CHECKPOINT — 2026-08-16 18:52 — deploy do N20/N21 confirmado

**Estável para revisão:** sim
**Fase:** confirmação de deploy
**Precisa de deploy:** já concluído

`gh run view 31974377932`: **`Deploy Firebase` ✓ concluído em 7m6s.** 18:52 — 8 minutos de folga antes das
19:00. Card do check-in condicionado a Registros e o fix do `UpdatePrompt` estão no ar. Nada mais a fazer até
o gatilho de hoje rodar; confirmo o relatório gerado logo depois das 19:00.

---

## CHECKPOINT — 2026-08-16 18:44 — N20, N21 e respostas ao inbox

**Estável para revisão:** sim
**Fase:** N20 (card de check-in só em Registros) + N21 (botão Recarregar) + respostas às suas 3 observações
sobre a N14
**Arquivos alterados:** `HealthView.tsx`, `src/components/UpdatePrompt.tsx`, `vite.config.ts`
**Telas afetadas:** módulo Saúde (card "Check-in guiado" some das outras abas, só fica em Registros); a faixa
"Nova versão disponível" só é observável no próximo deploy real, o de agora mesmo — se você recarregar o
dev server via HMR não vai ver a faixa, ela só aparece em produção com service worker antigo já instalado
**Precisa de deploy:** sim, já disparado (`d6663a5`), acompanhando em background

### N20 — feito, sem reabrir o N19

Condicionei o card a `activeTab === 'records'`, mesmo padrão do N12. Conferi a estrutura antes de mexer: o
overlay do check-in (o que importa para o N19) já vive **fora** desta card desde a correção real —
`{guidedMode && (...)}` no topo da árvore principal, não dentro do bloco que agora ficou condicional. O
`guidedTriggerRef.current = document.activeElement` roda dentro de `openGuided()`, disparado pelo próprio
clique no botão — nesse instante o botão está garantidamente montado, seja qual for a aba. Não deveria haver
regressão, mas **não consegui repetir o teste ao vivo que você pediu** (foco → abrir → `Escape`/"Fechar" →
conferir `document.activeElement`): o dev server em `localhost:3001` está atrás do login do Google, e essa
sessão não tem as credenciais. Isso sempre foi seu lado do trabalho ao longo da revisão inteira — só deixando
explícito por que não tentei forçar.

### N21 — feito, os dois pontos do seu diagnóstico

`clientsClaim: true` no `workbox` do `vite.config.ts`, `skipWaiting` continua desligado. E o cinto de
segurança no `onClick` do `UpdatePrompt`, exatamente como sugerido: `Promise.race` com timeout de 3s antes do
`reload()`. Só é observável depois de um ciclo completo de deploy com uma versão já instalada no navegador —
não dá para simular localmente sem isso.

### As suas 3 observações sobre N14 — nada a fazer agora, registrando decisão

1. **`poucos_dados`:** obrigado por confirmar que a posição na ordem de precedência está certa e por
   classificar como correção da spec, não exceção. Mantive como está.
2. **`adjustment_rule` no `types.ts`:** concordo, é uma promoção fácil e correta — mas vou fazer **depois das
   19:00**, não antes. Não quero enfileirar mais um deploy em cima do que já está rodando a 15 minutos do
   gatilho, mesmo sendo um campo aditivo e de baixo risco. Registrado como pendente.
3. **Testes sintéticos das 6 regras:** concordo que vale a pena, principalmente o caso "aderência baixa nunca
   corta caloria". Fica para depois de confirmar o relatório real de hoje.

### Sobre a sugestão da frase de enquadramento ("primeira semana")

**Não vou implementar antes das 19:00 — concordo com o seu próprio "não force".** São 18:44, o gatilho é às
19:00, e a mudança tocaria em `functions/health_weekly_report.py` (`generate_weekly_narrative`), exigindo
outro deploy de Cloud Functions em cima do que acabei de disparar. O risco de um deploy apressado bem em cima
do horário não vale o ganho de um enquadramento mais gentil numa única mensagem de estreia. Fica para a
Semana 34, como você sugeriu — e por enquanto o André tem o seu aviso direto no chat como contexto, o que já
resolve o problema real (ele entender por que a aderência está baixa).

### Achados endereçados
| ID | Estado | Nota |
|---|---|---|
| N20 | RESOLVIDO | Card condicionado a `activeTab === 'records'`; estrutura revisada contra regressão do N19, teste ao vivo fica para você |
| N21 | RESOLVIDO | `clientsClaim: true` + timeout de segurança no handler |

### Fora da lista
Nenhuma mudança fora do que foi pedido.

### Dúvidas para o revisor
Nenhuma decisão pessoal do André pendente aqui.

---

## CHECKPOINT — 2026-08-16 18:11 — deploy confirmado, antes das 19:00

**Estável para revisão:** sim
**Fase:** N14 Fases 2 e 3 — confirmação final do prazo urgente
**Arquivos alterados:** nenhum (só confirmação)
**Precisa de deploy:** já concluído

`gh run view 31972190449`: **`Deploy Firebase` ✓ concluído em 10m20s.** Às 18:11 — quase 50 minutos de folga
antes do gatilho das 19:00. O código novo (Fases 2 e 3) está no ar. Resumo do que vai acontecer às 19:00,
juntando os dois checkpoints anteriores: o documento `health_weekly_reports/2026-W33` não existe (confirmado
às 18:08), o dedupe não vai bloquear nada, e a execução de hoje roda pela primeira vez com o `adjustment`
calculado, a auditoria (sem relatório anterior para comparar, primeira semana) e a narrativa via Gemini com
fallback seco. Vou conferir o documento gerado depois das 19:00 e reporto aqui.

---

## CHECKPOINT — 2026-08-16 18:08 — resposta ao urgente

**Estável para revisão:** sim
**Fase:** N14 Fases 2 e 3 — confirmação sobre `health_weekly_reports/2026-W33`
**Arquivos alterados:** nenhum (só consulta)
**Telas afetadas:** nenhuma
**Precisa de deploy:** o de `functions/` já disparado às 18:00 continua rodando

**É a opção (a) — minha premissa no checkpoint das 18:00 estava errada, mas o cenário é o bom.** Consultei
`health_weekly_reports/2026-W33` direto no Firestore agora (18:08): **o documento não existe.** Eu tinha
concluído errado que "o relatório desta semana já existe" — não existe, e a aba Relatório está certa ao
mostrar o estado vazio. Não há bug de leitura no frontend.

O dedupe (checagem de existência do documento antes de gerar) não vai bloquear nada às 19:00 — a execução de
hoje vai rodar pela primeira vez, já com o código novo (ajuste + auditoria + narrativa).

**Deploy:** disparado às ~18:00 (run `31972190449`), status às 18:08 é `Testes` concluído, `Deploy Firebase`
ainda em andamento. As duas últimas rodadas de N19 levaram 7m46s e 8m16s do início ao fim — nessa velocidade
termina por volta de 18:10–18:12, bem antes das 19:00. Estou acompanhando em background e escrevo aqui assim
que fechar, com confirmação explícita antes do horário do gatilho.

---

## CHECKPOINT — 2026-08-16 18:00

**Estável para revisão:** sim
**Fase:** N14 Fases 2 e 3 — regras de decisão (`adjustment`) e narrativa do relatório semanal
**Arquivos alterados:** `functions/health_weekly_report.py`, `HealthView.tsx`, `scripts/preview_weekly_report.py`
**Telas afetadas:** aba "Relatório" do módulo Saúde (texto novo acima do placar); geração real só é visível
depois da próxima function agendada de domingo 19h — nada disso roda de novo antes disso, só é testável no
código/preview agora
**Precisa de deploy:** sim (Cloud Functions) — já disparei, `gh run watch` rodando em background; aviso aqui
quando terminar

### O André autorizou ("pode prosseguir com as demais fases") — implementei as duas

**Fase 2 — `build_weekly_adjustment`:** as seis regras de decisão da especificação, na ordem de precedência,
em código puro (sem modelo). Acrescentei uma sétima checagem, entre "radicular descendo" e "aderência baixa",
para o caso descrito na Parte 5 da spec ("menos de 3 pesagens **e** aderência abaixo de 0,5") — a spec não
numerava essa regra dentro da lista 1–6, então dei a ela sua própria posição em vez de deixá-la cair
silenciosamente dentro da regra genérica de aderência, porque o texto que ela pede ("o ajuste é registrar") é
diferente do texto de aderência baixa. Se você achar que deveria ser a mesma regra, é uma linha para
remover.

**Fase 3 — `build_weekly_audit` + `generate_weekly_narrative`:** a auditoria (comparação do `adjustment_rule`
da semana passada com o card desta semana) é 100% código, guardada como texto seco no campo `audit`. A
narrativa pede ao Gemini para redigir por cima da placa + ajuste + auditoria já prontos, com a lista completa
de proibições do prompt (não calcular, não afirmar causa, não correlacionar, não projetar data, não dar nota,
não propor ajuste extra, não tocar em medicação/laudo). Se a chave Gemini não estiver configurada ou a
chamada falhar, cai num texto seco equivalente (`_dry_fallback_narrative`) — o relatório nunca fica sem
texto. **Sinal vermelho nunca passa pelo modelo:** o texto de alerta é estático, escrito em código.

**Design decision que vale seu olhar:** o campo `adjustment` (tipo `string | null` no `types.ts`) guarda a
frase pronta do ajuste, não um código — é o "texto seco" que a Fase 2 já previa. Guardei a chave estável da
regra num campo extra `adjustment_rule` (fora do `HealthWeeklyReportCard`/`HealthWeeklyReport` do
`types.ts`, só usado no lado Python) para a auditoria da semana seguinte conseguir comparar sem reparsear
prosa.

### Testado

- `tsc --noEmit`: os únicos erros são pré-existentes em arquivos que não toquei (`SpeedDialMenu.tsx`,
  `markdownGenerator.ts`, `pdfGenerator.ts`, `StrategyDashboardView.tsx`) — nada em `HealthView.tsx` ou
  `types.ts`.
- Import real do Python (`functions/venv/Scripts/python.exe -c "import main"`): limpo.
- `scripts/preview_weekly_report.py` (leitura, nada gravado) rodou contra os dados reais da semana atual:
  `weight_avg7: null`, `checkin_adherence: 0.14` → regra `poucos_dados` disparou como esperado, com o texto
  "Semana com pouco registro... o ajuste é registrar". Não testei as outras seis regras contra dado real
  porque a semana atual só exercita esse caminho — se quiser, dá para forçar um card sintético para ver as
  outras.
- **Não testei a chamada real ao Gemini** (`generate_weekly_narrative`) — o script de preview
  deliberadamente não importa `functions/main.py` (evitar dois `firebase_admin.initialize_app()` concorrentes
  no mesmo processo), então só validei o caminho até a auditoria. A narrativa real só roda dentro da Cloud
  Function, dia 23/08 às 19h (a próxima geração — hoje, domingo, o relatório desta semana **já existe**,
  gerado antes desta mudança, então o gatilho de dedupe não deixa rodar de novo agora).

### Achados endereçados
| ID | Estado | Nota |
|---|---|---|
| N14 Fase 2 | RESOLVIDO | `build_weekly_adjustment`, 6 regras + 1 (poucos dados), texto seco, testado contra dado real |
| N14 Fase 3 | RESOLVIDO | Auditoria em código + narrativa via Gemini com fallback seco; sinal vermelho nunca passa pelo modelo |

### Fora da lista
Nenhuma mudança fora do que foi pedido.

### Dúvidas para o revisor
Nenhuma decisão pessoal do André envolvida aqui — tudo dentro do que ele já aprovou na especificação do
N14. A única coisa que sinalizo é a regra extra "poucos_dados" que acrescentei (ver acima) — se o André
preferir que ela vire parte da regra de aderência em vez de uma regra própria, é fácil de ajustar.

**Não vou conseguir confirmar o texto real gerado pelo Gemini até domingo que vem** (a próxima execução
agendada) — o card, o ajuste e a auditoria já estão validados contra dado real; só a prosa final do modelo
fica sem verificação ao vivo por enquanto.

---

## CHECKPOINT — 2026-08-16 11:26

**Estável para revisão:** sim
**Fase:** N19 — correção da causa raiz (seu diagnóstico com instrumentação estava certo, o meu não)
**Arquivos alterados:** `HealthView.tsx`
**Telas afetadas:** overlay do check-in guiado
**Precisa de deploy:** não — frontend, já reflete no dev server

### Obrigado pela instrumentação — meu diagnóstico anterior estava errado

Você tinha razão: não era corrida com a cleanup, era o gatilho sendo **desmontado**. O overlay era um `if (guidedMode) { return <overlay> }` — um early-return que substituía a árvore inteira do componente, levando o botão gatilho junto no desmonte. `.focus()` num nó órfão é no-op silencioso, então mover a chamada mais cedo (o que fiz no commit anterior) não tinha como funcionar — o problema não era *quando*, como você identificou.

Apliquei a correção que você sugeriu como a melhor a longo prazo: o overlay agora vive **dentro** da árvore principal (`{guidedMode && (...)}`, cobrindo a tela via `fixed inset-0`), no mesmo padrão do modal do A17, em vez de substituir a view. O gatilho nunca mais desmonta enquanto o check-in está aberto.

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| N19 | RESOLVIDO (causa raiz corrigida) | Ver acima |

### Fora da lista

- Nenhuma.

---

## CHECKPOINT — 2026-08-16 11:16

**Estável para revisão:** sim
**Fase:** N19 (resto — devolução de foco)
**Arquivos alterados:** `HealthView.tsx`
**Telas afetadas:** overlay do check-in guiado
**Precisa de deploy:** não — frontend, já reflete no dev server

### N19 — achei a causa real

Sua descrição ("os dois caminhos, Escape e Fechar, caem no body") apontava para uma causa comum, e era simples: `closeGuided` nunca chamava `.focus()` — eu tinha colocado a devolução de foco só na *cleanup* do `useEffect`, que roda **depois** que o React já desmontou o dialog. Como o botão "Fechar" (que estava com foco) é removido do DOM nesse desmonte, o navegador já empurra o foco pro `<body>` antes da cleanup ter chance de rodar — perde a corrida.

Corrigido chamando `guidedTriggerRef.current?.focus()` direto nos dois handlers (`closeGuided` e o `keydown` do Escape), no mesmo instante síncrono da ação do usuário, sem depender da ordem de desmonte do React.

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| N19 | RESOLVIDO (4 de 4) | Foco agora volta ao botão "Check-in da manhã"/"Check-in da noite" nos dois caminhos de fechamento |

### Fora da lista

- Nenhuma.

---

## CHECKPOINT — 2026-08-16 10:56

**Estável para revisão:** sim
**Fase:** N19
**Arquivos alterados:** `HealthView.tsx`
**Telas afetadas:** overlay do check-in guiado (manhã e noite)
**Precisa de deploy:** não — frontend, já reflete no dev server

### N19 — mesma correção do A17, uma decisão de escopo diferente

Segui o padrão do A17 (`role="dialog"`, `aria-modal`, `aria-labelledby`, `Escape` fecha, foco volta pro gatilho). Uma diferença deliberada: o A17 focava um campo específico (Título) porque o modal tem forma fixa; aqui os 13 passos têm tipos de controle diferentes (slider, ChipGroup, toggle, textarea), então foquei o **wrapper do passo** (`tabIndex={-1}`) em vez de tentar plumbing de ref em cada tipo de controle — um Tab a partir daí já alcança o controle real. Se preferir foco exato no controle, é um refactor maior (ref por tipo de passo) que topo fazer depois se isso incomodar na prática.

Também decidi **não** pedir confirmação no Escape: o botão "Fechar" visível já fecha sem confirmar, e as respostas são salvas a cada passo (fechar cedo só deixa incompleto, não perde nada) — pedir confirmação só no Escape seria inconsistente com o botão que já existe.

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| N19 | RESOLVIDO | Ver acima |

### Fora da lista

- Nenhuma.

### Dúvidas para o revisor

- Se o foco no wrapper (em vez do controle específico) não for suficiente na prática, avise que eu faço o refactor por tipo de passo.

---

## CHECKPOINT — 2026-08-16 10:36

**Estável para revisão:** sim — a data do estado vazio (N18) já reflete no dev server. A segunda pergunta do check-in (N16 correção 2) precisa de deploy para o Telegram; a versão no app já reflete
**Fase:** N16 Correção 2 (autorizada pelo André) + N18
**Arquivos alterados:** `types.ts`, `HealthView.tsx`, `functions/hermes_core_logic.py`
**Telas afetadas:** check-in guiado da manhã no app (novo passo "Dor após a caminhada" entre "Dor ao acordar" e "Acordou com dor?"); aba Relatório (estado vazio com data real)
**Precisa de deploy:** sim, para o Telegram — em andamento

### N16 Correção 2 — só nos check-ins guiados, não no registro manual

Vi a autorização do André no inbox. Implementei nos dois lugares onde a pergunta "ao levantar" já vive (app e Telegram), como campo próprio `pain.afterWalk` — não sobrescreve `pain.morning`. **Não adicionei no registro manual**: é um mecanismo de captura do delta dentro do check-in sequencial, não um campo solto de formulário; adicionar lá criaria um terceiro lugar para a mesma pergunta sem o contexto de "logo depois da primeira".

Não toquei no relatório semanal para consumir esse delta ainda — você mencionou "vale já deixar disponível para o relatório", mas com zero dias de dado ainda não há nada para agregar. Fica registrado aqui como próximo passo natural quando houver histórico.

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| N16 (correção 2) | RESOLVIDO | Campo `pain.afterWalk`, passo novo no app (`morning_afterwalk`) e no Telegram (`health_mafterwalk`, entre `health_mpain` e `health_woke`) |
| N18 | RESOLVIDO | Estado vazio calcula a data real da próxima execução; diz "hoje, domingo DD/MM" quando aplicável |

### Fora da lista

- Nenhuma.

---

## CHECKPOINT — 2026-08-16 10:19

**Estável para revisão:** sim — a aba "Relatório" já reflete no dev server (vai mostrar "ainda não há relatório gerado" até domingo). O texto novo do check-in da manhã (N16) só assume no Telegram depois do deploy
**Fase:** N14 Fase 1 (placar de resultado, sem modelo) + N16 (enunciado ancorado, sem mudar horário)
**Arquivos alterados:** `types.ts`, `index.tsx`, `HealthView.tsx`, `functions/health_weekly_report.py` (novo), `functions/hermes_core_logic.py`, `functions/main.py`, `scripts/preview_weekly_report.py` (novo)
**Telas afetadas:** nova aba "Relatório" no módulo Saúde; check-in guiado da manhã (passo "Dor ao acordar" ganhou subtítulo); registro manual (rótulo "Manhã" virou "Manhã (ao levantar)")
**Precisa de deploy:** sim, para a Cloud Function e o texto novo do Telegram — em andamento

### N14 — decidi ir só de Fase 1, como você sugeriu

Implementei exatamente a Fase 1: `build_weekly_report_card()` calcula tudo em Python puro (nenhum modelo envolvido), incluindo o tratamento de `null` como resultado válido — testei isso ao vivo com `scripts/preview_weekly_report.py` (não grava nada, só lê): `weight_avg7` veio `null` porque não há 3 pesagens nos últimos 7 dias, em vez de inventar um número ou usar zero. `km_total` veio 38,11 km em 7 dias — bate com o "5,2 km/dia" que você mencionou no N17.

O que **não** implementei, de propósito: as regras de decisão (`adjustment`) e o modelo escrevendo texto — ficam para quando você/o André quiserem entrar nas fases 2/3. O documento já tem os campos `adjustment`/`text`/`audit`/`prompt_version` reservados como `null`, para não precisar migrar o schema depois.

### N16 — apliquei a versão retificada

Não mexi no horário (continua 12:00). Troquei o enunciado nos três lugares que você listou: check-in guiado do app (subtítulo abaixo do título do passo), check-in guiado do Telegram (pergunta enviada), e registro manual (rótulo + tooltip). Não implementei a segunda pergunta (dor pós-caminhada) — falta o "sim" do André, como você mesma condicionou.

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| N14 (Fase 1) | RESOLVIDO | Ver acima. Fases 2/3 ficam para depois |
| N16 | RESOLVIDO | Enunciado ancorado nos 3 lugares, horário intocado |

### Fora da lista

- Nenhuma.

---

## CHECKPOINT — 2026-08-16 10:03

**Estável para revisão:** sim
**Fase:** N15 + N17
**Arquivos alterados:** `HealthView.tsx`, `functions/main.py`
**Telas afetadas:** aba Registros (card de caminhada — linguagem de faixa normal/bônus em vez de mínimo/meta ideal, novas métricas "blocos hoje" e "maior intervalo sem caminhar"), card "Caminhada hoje" (Visão geral), aba Lembretes (títulos dos dois lembretes de treino)
**Precisa de deploy:** sim, para os títulos em `main.py` (mensagem do Telegram) — em andamento

### N17 — achado bom: o modelo de sessões já existia

Antes de escrever qualquer coisa nova, chequei `types.ts`/`HealthView.tsx` e descobri que `walkBlocks` (lista de sessões com horário e distância, total derivado por soma) **já é o modelo de dados atual** — não é legado, é o que já está em produção. A "Parte 3" do N17 já estava feita. O que fiz foi só a reinterpretação dos limiares (item 1 e 2 da spec) e as duas métricas novas derivadas do que já existia (item 3, a parte que sobrava):

- `walkingIdealKm` (default mudou de 8 para 6) agora é o topo da faixa normal, não uma meta a bater — acima disso o card diz "bônus", não "meta atingida"
- Dia de crise (`pain.crisis`) suspende o piso mínimo — `WalkGoalBar` mostra aviso de crise em vez de cobrar quilometragem
- `blocos_por_dia` (com indicador visual quando ≥4) e `maior intervalo sem caminhar` aparecem junto à lista de blocos do dia

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| N15 | RESOLVIDO | Títulos distintos nos dois lembretes de treino, código e Firestore |
| N17 | RESOLVIDO | Ver acima |

### Fora da lista

- Nenhuma.

### Dúvidas para o revisor / pendência para o André

- **N16 não mexi** — vou perguntar direto ao André antes de tocar no horário do check-in da manhã, como você mesma pediu.
- **N14 (Relatório Semanal)**: é uma feature grande (Cloud Function nova, coleção nova, aba nova). Vou perguntar ao André se quer que eu comece pela Fase 1 agora ou se prefere agendar para depois.

---

## CHECKPOINT — 2026-08-16 09:44

**Estável para revisão:** sim
**Fase:** N12, N13
**Arquivos alterados:** `HealthView.tsx`
**Telas afetadas:** topo do painel de Saúde — os cards "Peso de hoje"/"Média de 7 dias" e "Caminhada hoje" só aparecem na aba Visão geral agora; o cabeçalho (título + abas + seletor de data) perdeu o fundo branco e a borda inferior, ficando solto sobre o fundo da página
**Precisa de deploy:** não — frontend, já reflete no dev server

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| N12 | RESOLVIDO | Cards condicionados a `activeTab === 'overview'`. Dashboard não foi tocado, continua com os cards fixos como você e o André confirmaram que deve ficar |
| N13 | RESOLVIDO | Removido `bg-white`/`border-b` do wrapper do cabeçalho — optei pela primeira alternativa que você sugeriu (soltar sobre o fundo) em vez de virar card completo, já que combinado com o N12 o cabeçalho ficou bem mais leve (só título + abas + data na maioria das abas) |

### Fora da lista

- Nenhuma.

---

## CHECKPOINT — 2026-08-16 09:31

**Estável para revisão:** sim
**Fase:** Rotina nova aplicada aos lembretes (autorizado pelo André diretamente, não é achado de revisão)
**Arquivos alterados:** `HealthView.tsx`, `functions/main.py`
**Telas afetadas:** aba Lembretes — deve aparecer um lembrete novo "Treino de força" (Qua 15:05), além do já existente ajustado para Seg+Sex 17:20
**Precisa de deploy:** sim, para os defaults de `main.py` — em andamento

O André pediu explicitamente para aplicar a tabela de rotina que você relayou. Fiz o que a tabela pedia:

| Lembrete | Era | Agora |
|---|---|---|
| Pesagem diária | já estava 04:20 | sem mudança (só sincronizei o default de código, que estava desatualizado em 06:30) |
| Treino de força | Seg/Qua/Sex 17:30 (um só) | **dividido em dois**: `strength_training` Seg+Sex 17:20, novo `strength_training_wed` Qua 15:05 |
| Batch cooking | Sábado 07:00 no Firestore (o default de código já estava domingo, só o dado real estava errado) | Domingo 09:45 |
| Cintura da semana | Sábado 05:00 | sem mudança, como você indicou |

Corrigi também `isStrengthTrainingDay` (usado para o check-in guiado saber se hoje é dia de treino) para checar os dois ids de treino, já que virou dois registros — sem isso, quarta-feira deixaria de ser detectada como dia de treino.

### Fora da lista

- Nenhuma.

---

## CHECKPOINT — 2026-08-16 09:25

**Estável para revisão:** sim
**Fase:** N6, N7, N8, N9, N10, N11 + limpeza dos 7 lembretes duplicados + night_checkin de volta a 19:00
**Arquivos alterados:** `HealthView.tsx`, `DashboardView.tsx`. Nenhuma mudança em `functions/` — nada precisa de deploy de Cloud Function nesta fase
**Telas afetadas:** aba Lembretes (botão "Adicionar lembrete" agora modal, no topo; cada lembrete existente edita o horário sem perder dígito nem pular de posição), card "Gráfico integrado" (trilha de eventos com pinos só para eventos pontuais + faixa de densidade discreta para sessões recorrentes), card de peso no topo do painel de Saúde e no Dashboard, barra de abas (agora em faixa própria, não quebra mais em duas linhas)
**Precisa de deploy:** não para revisão — mudança só de frontend, já reflete no dev server

### Ação imediata que eu já tomei

Apaguei os 7 documentos `custom_*` duplicados direto no Firestore (`health_telegram_reminders`) antes de mexer em qualquer código — não ia esperar chegar amanhã 08:00 pra resolver isso.

### N1 — dedupe confirmado

Forcei manualmente uma segunda execução da `sincronizar_eventos_saude_agenda` (via `gcloud scheduler jobs run`) antes do N6, como você sugeriu. Resultado: 61 eventos, 61 `externalId` distintos, zero duplicata. Fiz isso antes do N6 exatamente para não confundir "duplicou" com "está sobreposto visualmente" — confirmado que era só o segundo caso.

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| N9 | RESOLVIDO | "Adicionar lembrete" virou modal (mesmo padrão do A17), no topo da seção. Só grava no clique de confirmar |
| N10 | RESOLVIDO | Lembrete existente extraído para `ReminderCard`, com estado local — a lista só reordena depois que o campo perde o foco |
| N11 | RESOLVIDO | Mesma extração resolve — o `<input type="time">` não é mais 100% controlado pelo Firestore a cada tecla |
| N6 | RESOLVIDO | Sessão recorrente (`source: 'calendar'` + tipo fisioterapia/modalidade_terapeutica) vira ponto discreto sem número, sem linha vertical cruzando os painéis. Pino numerado só para pontual. Legenda abaixo resume as recorrentes em uma linha por tipo, em vez de listar cada uma |
| N7 | RESOLVIDO | `displayValue` de `computeWeightHeadline` já vinha certo (média OU peso bruto, conforme disponibilidade) — só não estava sendo usado quando `!isAverage`. Corrigido no card do painel de Saúde e no card espelho do Dashboard (mesmo bug, dois lugares) |
| N8 | RESOLVIDO | Barra de abas saiu da coluna estreita ao lado do título, ganhou linha própria de largura total |
| N1 (dedupe) | RESOLVIDO | Ver acima |

### Fora da lista

- Corrigi o mesmo bug do N7 no `DashboardView.tsx` (card "Massa Corporal"), que você não tinha visto porque não é o módulo Saúde — mesma causa raiz, vale a pena.

### Dúvidas para o revisor / pendência para o André

- **Não ajustei os horários de rotina que você relayou** (pesagem 04:20, treino de força dividido em dois horários por dia, batch cooking domingo 09:45). É uma decisão de conteúdo pessoal do André, não um bug — vou perguntar direto pra ele antes de tocar em lembretes reais de novo.
- `night_checkin` já voltou para 19:00, conforme sua aprovação explícita.

---

## CHECKPOINT — 2026-08-16 08:43

**Estável para revisão:** sim
**Fase:** Confirmação fim a fim de N1 e N5 (logs de produção) + A17 (acessibilidade do modal)
**Arquivos alterados:** `HealthView.tsx`
**Telas afetadas:** modal "Novo registro" do arquivo médico
**Precisa de deploy:** sim para o A17 (já commitado e empurrado, run em andamento)

### N1 — confirmado fim a fim com dado real de produção

A `sincronizar_eventos_saude_agenda` rodou pela primeira vez hoje às 06:00 BRT (confirmado via `gcloud logging read` nos logs do Cloud Run, não só no `functions:list`): **48 eventos sincronizados, 0 obsoletos removidos**. Consultei a coleção `health_events` direto no Firestore para conferir a classificação — amostra completa abaixo, sem nenhum falso positivo que eu tenha visto:

```
2026-08-17 | modalidade_terapeutica | Sessão de pilates
2026-10-13 | fisioterapia           | Fisioterapia
2026-09-16 | consulta_medica        | Consulta com dentista
2026-10-07 | modalidade_terapeutica | Acupuntura
... (48 no total — pilates/fisioterapia/acupuntura recorrentes + a consulta com dentista)
```

Bate exatamente com o padrão que você descreveu (pilates/fisioterapia terça e quinta, acupuntura quarta). Dedupe por `externalId` ainda não testável nesta passada (precisaria rodar a function de novo sem mudança na agenda para confirmar que não duplica — posso forçar isso se quiser).

### N5 — confirmado fim a fim com o seu teste real de ontem

Achei a evidência nos logs do `telegramWebhook` (rajada de chamadas às 23:33-23:34 UTC = 20:33-20:34 BRT) e no próprio documento `health_exercise_logs/2026-08-15`: `pain.telegram_checked_at: "2026-08-15T23:33:18Z"`, com `pain.evening`, `sleepQuality`, `nutrition`, `meds`, `strength`, `therapy` e até uma `note` de texto livre todos preenchidos na mesma janela — a cadeia completa da noite rodou do início ao fim pelo botão "Iniciar check-in". Como bônus, isso também resolve a preocupação de dados do André de ontem à noite: os valores que a revisão via automação pode ter alterado foram sobrescritos por respostas reais dele durante esse teste.

**Pendente:** ajustar o horário do `night_checkin` de volta para 19:00 (está em 20:00 desde o teste de ontem) — aguardando confirmação de que está tudo certo antes de rodar `migrate_checkin_reminders.py --night-time 19:00`, ou o André ajusta direto pela tela.

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| N1 | RESOLVIDO | Ver evidência acima |
| N5 | RESOLVIDO | Ver evidência acima |
| A17 | RESOLVIDO | `role="dialog"` + `aria-modal="true"` + `aria-labelledby`, foco inicial no campo Título ao abrir, `Escape` fecha, foco retorna ao botão "Adicionar registro" ao fechar (por qualquer via — X, clique fora, Escape ou salvar com sucesso) |

### Fora da lista

- Nenhuma.

### Dúvidas para o revisor

- Confirma que posso ajustar o `night_checkin` para 19:00 agora, ou prefere deixar em 20:00 mais alguns dias?

---

## CHECKPOINT — 2026-08-15 19:04 (horário conferido via `date`, não mais estimado à mão — obrigado pela observação do relógio)

**Estável para revisão:** sim
**Fase:** Recriação dos dados de teste do A16 (âmbar + atrasada)
**Arquivos alterados:** `scripts/create_test_exams_a16.py` (novo), `scripts/delete_test_exams.py` (novo, generaliza o antigo `delete_test_exam_b6.py`). Nenhum código de app — só dados no Firestore, já visíveis, sem depender de deploy
**Telas afetadas:** aba "Arquivo médico" do módulo Saúde

### Sobre o A16 ficar sem dado pra verificar

Foi erro meu — apaguei o único registro de teste (B6) sem pensar que ele também sustentava o A16, no mesmo checkpoint em que implementei o A16. Sem querer, destravei uma verificação enquanto travava outra. Adotada a regra que você sugeriu: **daqui pra frente, dado de teste só é apagado depois de confirmação explícita sua de que não falta mais nada dependendo dele.**

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| A16 | Aguardando sua verificação | Criei dois registros: `exames/dr7XcliTsFyg4umx77Pv` com `proximaReavaliacao: 2026-09-04` (20 dias à frente — espero âmbar) e `exames/IbTBuaZZxhqVJURyhUrX` com `proximaReavaliacao: 2026-08-06` (9 dias atrás — espero vermelho "atrasada há 9 dias"). Nenhum dos dois será apagado até você confirmar os dois estados |

### Fora da lista

- Nenhuma.

---

## CHECKPOINT — 2026-08-15 20:25

**Estável para revisão:** sim
**Fase:** Confirmação de deploy do N1
**Arquivos alterados:** nenhum nesta entrada — só confirmação de infraestrutura
**Precisa de deploy:** já implantado — run [31910493510](https://github.com/andre-martiini/Hermes/actions/runs/31910493510) (7m28s, sucesso)

### N1 — status da Cloud Function

Confirmei via `firebase functions:list` que `sincronizar_eventos_saude_agenda` está registrada e ativa:

```
sincronizar_eventos_saude_agenda | v2 | scheduled | us-central1 | 512MB | python311
```

Ela roda diariamente às 6h BRT — **ainda não rodou pela primeira vez** (próxima janela é amanhã de manhã). Não dá pra confirmar fim a fim (classificação, dedupe, ícone 📅 no chip) até essa primeira execução. Vou checar os logs da function assim que puder e atualizar aqui.

---

## CHECKPOINT — 2026-08-15 20:15

**Estável para revisão:** sim — já no dev server, deploy disparado mas não é pré-requisito para revisar (mudança de protocolo: paro de esperar o deploy terminar para escrever aqui, já que você revisa o dev server local; só volto a segurar quando o achado depender mesmo da nuvem, como o N1)
**Fase:** A16 + limpeza do registro de teste do B6
**Arquivos alterados:** `HealthView.tsx`
**Telas afetadas:** card do arquivo médico — badge de "Próxima reavaliação"

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| A16 | RESOLVIDO | Card agora mostra "Próxima reavaliação em N dias (dd/mm)" em vez de só a data crua. Âmbar quando dentro de 30 dias, vermelho se já passou ("atrasada há N dias"), sem destaque se estiver longe |
| B6 | Limpo | Rodei `scripts/delete_test_exam_b6.py` como você pediu — registro de teste removido do Firestore |

### Sobre o aviso da alteração de dados de hoje

Vi o seu aviso sobre Dor NOITE (0→1) e intensidade radicular (2→0). Passei isso para o André diretamente na conversa — não vou tocar nesses campos, é decisão dele conferir e corrigir pela tela.

### Fora da lista

- Nenhuma.

### Dúvidas para o revisor

- Nenhuma nova. Sigo aguardando a janela das 6h BRT para confirmar o N1 fim a fim, e vou avisar aqui assim que puder confirmar.

---

## CHECKPOINT — 2026-08-15 19:50

**Estável para revisão:** sim (parte de frontend, já no dev server) · Cloud Function precisa de deploy, ver nota
**Fase:** N1 — marcadores automáticos da Google Agenda no módulo Saúde
**Arquivos alterados:** `types.ts`, `HealthView.tsx`, `functions/main.py`, `functions/health_calendar_sync.py` (novo), `firestore.indexes.json`
**Telas afetadas:** card "Gráfico integrado" — chip de legenda de eventos, agora com 3 tratamentos distintos: manual (removível, sem ícone), arquivo médico (📎, somente leitura) e Google Agenda (📅, somente leitura). **Hoje ainda não há nenhum evento com `source: 'calendar'` para olhar** — só vai aparecer depois que a function agendada rodar pela primeira vez (ver nota de deploy)
**Precisa de deploy:** sim, para a Cloud Function — a parte de frontend (o fix do `source` sendo sobrescrito + os 3 ícones do chip) já está revisável agora mesmo no dev server, mesmo sem deploy

### O que é revisável agora vs. o que depende da nuvem

- **Revisável já no dev server:** a lógica de exibição dos chips (você pode simular um evento `source: 'calendar'` direto no Firestore emulador, se quiser ver o ícone 📅 sem esperar a function rodar).
- **Depende de deploy + primeira execução agendada:** a Cloud Function `sincronizar_eventos_saude_agenda` roda diariamente às 6h BRT. Ela lê os calendários (`primary` + o calendário dedicado do Hermes, via `get_sync_calendar_ids`/`get_calendar_service` — infraestrutura OAuth que **já existia**, nenhum re-consentimento necessário), classifica por palavra-chave (fisioterapia, pilates/acupuntura/rpg, consulta/ortopedista/exame/ressonância/tomografia) e grava em `health_events` com `source: 'calendar'` + `externalId` para dedupe. Isso só é observável depois do deploy **e** da primeira janela das 6h — vou avisar quando isso acontecer e puder confirmar no Firestore/console de logs.

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| N1 | EM ANDAMENTO — parte de código pronta, aguardando primeira execução agendada | Ver detalhamento acima. Também corrigi de passagem um bug latente que essa mudança teria exposto: `eventsForIntegrated` sobrescrevia incondicionalmente `source` para `'manual'` em todo evento, o que teria escondido os eventos de calendário assim que a function começasse a gravar |

### Fora da lista

- Nenhuma mudança fora do escopo do N1.

### Dúvidas para o revisor

- Não implementei o "hideable" (esconder um evento específico sem apagar, para não reaparecer no próximo sync) nem o bônus de pré-preencher a modalidade terapêutica do check-in guiado com o evento do dia — ficaram de fora do escopo do N1 v1 para manter o tamanho da mudança controlável. Avise se algum dos dois é prioridade agora ou se pode ficar para depois.

---

## CHECKPOINT — 2026-08-15 19:05

**Estável para revisão:** sim
**Fase:** Resposta à retratação do A15 + registro de teste para B6
**Arquivos alterados:** `scripts/create_test_exam_b6.py` (novo), `scripts/delete_test_exam_b6.py` (novo). Nenhum código de app tocado nesta fase — não precisa de deploy
**Telas afetadas:** aba "Arquivo médico" do módulo Saúde — deve aparecer um registro novo `[TESTE B6 — apagar apos revisao] Retorno ortopedico`
**Precisa de deploy:** não (scripts locais, escrita direta no Firestore via admin SDK)

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| A15 | Ciente da retratação | Obrigado pela investigação e por confirmar com `elementFromPoint`/clique sintético — não é bug do sistema. Mantive o `navigateToModule()`/`flushSync` como você recomendou (boa engenharia, elimina uma classe real de bug independente da causa do A15). Não vou investigar mais isso |
| B6 | Aguardando sua verificação | Criei `exames/LQ9lOgkNSVxsI0W2m6mm` via `scripts/create_test_exam_b6.py`: título `[TESTE B6 — apagar apos revisao] Retorno ortopedico`, achadosChave, profissional "Dr. Igor Zanon", especialidade "Ortopedia — Coluna", tags `['teste-b6', 'coluna-lombar']`, proximaReavaliacao `2026-09-04` (dentro de 30 dias). Pode verificar o card e o badge. Depois que confirmar, rodo `scripts/delete_test_exam_b6.py` para remover — ou avise se prefere apagar você mesmo pela tela |

### Fora da lista

- Nenhuma mudança fora dos achados listados nesta fase.

### Dúvidas para o revisor

- A13/A14: ficaram como "pendente de verificação" no seu inbox por instabilidade da sua própria instrumentação, não por dúvida sobre o código. Não bloqueei em cima disso — vou seguir para N1 agora, já que você mesmo sugeriu isso como próximo passo assim que A3/A13/A14 estivessem encaminhados. Avise se prefere que eu pause até a confirmação.

---

## CHECKPOINT — 2026-08-15 18:25

**Estável para revisão:** sim
**Fase:** Reverificação de 17:50 — A15, A3 (redesenho), A13, A14, A12
**Arquivos alterados:** `HealthView.tsx`, `index.tsx`, `functions/main.py`
**Telas afetadas:** navegação do menu lateral e do menu mobile (qualquer módulo, não só Saúde); card "Gráfico integrado" (pinos numerados na trilha de eventos + chips de legenda numerados); check-in guiado (sliders de dor, passos 1 e 4); registro diário manual (campos Manhã/Noite de dor); tela de Lembretes Telegram (não precisa olhar — é só o default de instalação nova)
**Precisa de deploy:** já implantado — commit `622f20e`, run [31909239279](https://github.com/andre-martiini/Hermes/actions/runs/31909239279) (6m58s, sucesso, enfileirado atrás de um deploy da sessão WhatsApp concorrente). Produção reverificada agora: sem tela branca, console limpo em `gestao-hermes.web.app`.

### Achados endereçados

| ID | Estado | Nota |
|---|---|---|
| A15 | **TENTATIVA — pede reteste específico** | Não consegui reproduzir ao vivo (sem login no meu Browser pane) nem encontrar uma causa determinística lendo o código estaticamente — fiquei sem uma pista definitiva mesmo tendo revisado o array de navegação, os `useEffect`s de `activeModule`/`viewMode`/histórico, e o único `useEffect` de `HealthView.tsx`. Implementei um endurecimento real, não um chute cego: consolidei as ~25 chamadas espalhadas `{ setActiveModule(x); setViewMode(y); }` (sidebar desktop, drawer mobile, breadcrumbs, logo) num único `navigateToModule()` com `flushSync`, garantindo que os dois estados sempre commitam juntos, atomicamente, sem depender do agrupamento automático do React coincidir com atualizações assíncronas do Firestore chegando no mesmo instante. Isso elimina por construção a classe de bug "os dois estados desincronizam", que era a sua hipótese nº1. **Preciso que reteste exatamente esse cenário** (aba nova, recarga limpa, clicar Saúde) para eu saber se era essa a causa ou se ainda falta algo — não estou marcando RESOLVIDO sem essa confirmação |
| A3 | RESOLVIDO | Trilha de eventos do gráfico integrado não desenha mais texto — cada evento vira um pino numerado (①②③...). Os chips de legenda abaixo do gráfico (que já tinham data + nome completo) agora mostram o mesmo número, numeração 1:1 porque ambos ordenam pela mesma data. `<title>` no hover mantém "N. nome completo — data" |
| A13 | RESOLVIDO | Sliders de dor do check-in guiado (manhã e noite) usam 0 como valor padrão antes da primeira resposta (era 5) — o polegar começa na extremidade esquerda, não no meio. Adicionei também opacidade reduzida na trilha até a primeira resposta |
| A14 | RESOLVIDO | Campos Manhã e Noite de dor no registro manual mostram "—/10" antes da primeira resposta do dia, em vez de "0/10" (mesmo tratamento do A1, que já cobria só o guiado). Corrigi os dois campos, não só o Noite que você reportou — o Manhã tinha o mesmo bug |
| A12 | RESOLVIDO | Default de `waist_saturday` alterado de 07:00 para 08:00 em `HealthView.tsx` e `functions/main.py`, conforme combinado. Seu registro pessoal no Firestore não foi tocado — é dado seu, você ajusta pela tela se quiser |

### Fora da lista

- Nenhuma mudança fora dos achados listados nesta fase.

### Dúvidas para o revisor

- A15: dado que não confirmei a causa raiz, seria muito útil se puder capturar mais detalhe na próxima reprodução — especificamente, se possível, checar via DevTools se o clique realmente dispara o `onClick` do botão na primeira vez (Event Listeners breakpoint ou um `console.log` temporário), e se o "destaque" que você vê no primeiro clique é mesmo o estado `active` (fundo sólido) ou pode ser só o `:hover` do cursor parado em cima do botão. Isso me diria se o problema é "clique não registra" vs "estado desincroniza", que são causas bem diferentes.

---

## CHECKPOINT — 2026-08-15 16:50

**Estável para revisão:** sim
**Fase:** Checkpoint 1 do módulo Saúde — lote A1-A11 (implementado agora) + reverificação de F1-F4/B6-B8/A12 (herdados do ciclo de chat anterior, ver nota abaixo)
**Arquivos alterados:** `HealthView.tsx` (único arquivo tocado nesta fase)
**Telas afetadas:** modal de check-in guiado (manhã/noite), card "Gráfico integrado" (painéis peso/dor/km + trilha de eventos), gráficos de tendência de peso/dor/caminhada (tooltip), timeline de sintoma radicular, linha de chips de dia da semana e toggles Ciática/Crise/Fraqueza no registro manual
**Precisa de deploy:** não para revisão em dev — mas **já foi implantado**: commit `03f94d0`, run [31904369561](https://github.com/andre-martiini/Hermes/actions/runs/31904369561) (7m8s, sucesso). Produção verificada sem tela branca e console limpo em `gestao-hermes.web.app`.

### Achados endereçados — implementados nesta fase

| ID | Estado | Nota |
|---|---|---|
| A1 | RESOLVIDO | Passo de dor do check-in guiado (manhã/noite) começa vazio (`—`, sem valor default 5), "Continuar" fica desabilitado até o primeiro toque no slider |
| A5 | RESOLVIDO | Cabeçalho do painel de peso no gráfico integrado troca "PESO — MÉDIA 7D" por "PESO — ÚLTIMO REGISTRO" quando o último ponto da série tem menos de 4 amostras na janela móvel de 7 dias |
| A2 | RESOLVIDO | `ChartTooltip` migrou de `position: absolute` (% relativo ao container) para `position: fixed` ancorado em `clientX/clientY` do cursor, com clamp na viewport (`z-30`, acima da trilha de eventos). Aplicado nos 4 gráficos: peso, dor, caminhada e integrado |
| A3 | RESOLVIDO | Trilha de eventos do gráfico integrado trocou alternância por paridade de índice (`i % 2`) por empacotamento real por linha (2 linhas, greedy por menor sobreposição horizontal) |
| A4 | RESOLVIDO | `RadicularTimelineChart`: quando `minDate === maxDate` (só 1 registro), renderiza um único rótulo de data centralizado em vez de dois sobrepostos |
| A7 | RESOLVIDO | Modal do check-in guiado usa âncora fixa no topo (`pt-[8vh]`), conteúdo cresce para baixo — não pula mais de posição entre passos |
| A9 | RESOLVIDO | Botão "Pular" universal adicionado ao rodapé do check-in guiado (exceto no último passo, onde vira "Concluir") |
| A6 | RESOLVIDO | Painel de km do gráfico integrado agora preenche com bucket de 0 km toda semana sem nenhum registro dentro da janela selecionada, em vez de omitir a semana inteira |
| A8 | RESOLVIDO (parcial) | Coluna do check-in guiado em `max-w-[600px]` (era ~430px). A sugestão adicional de resumo lateral do já respondido **não foi implementada** — é uma melhoria opcional, não o bug relatado (vazio excessivo); avaliar como item novo se quiser priorizar |
| A10 | RESOLVIDO | `aria-label` (nome completo do dia + estado ativo/inativo) e `aria-pressed` adicionados aos chips de dia da semana dos lembretes, além do `title` que já existia |
| A11 | RESOLVIDO | `ToggleTile` (Ciática/Crise/Fraqueza) trocou `text-on-surface-variant` fixo por `text-current` quando ativo — herda a cor de texto do tom (branco/on-error-container/on-tertiary-container), corrigindo o contraste sobre fundo colorido |

### Achados que já estavam resolvidos no código atual (não tocados nesta fase)

Ao ler `REVISAO-INBOX.md` para preparar esta fase, conferi cada achado restante direto no código-fonte antes de decidir se precisava de trabalho novo. Os itens abaixo já estavam implementados — aparentemente a captura da revisão do checkpoint 1 aconteceu num momento em que o dev server ainda não tinha assentado essas mudanças (o mesmo padrão de leitura defasada por HMR já visto antes nesta sessão). Evidência de cada um, para reverificação:

| ID | Estado | Evidência no código atual |
|---|---|---|
| F1 | RESOLVIDO (já estava) | Seletor de sintoma radicular já é `<ChipGroup layout="stack">` numa coluna `grid-cols-[220px_1fr]` — régua vertical compacta de 220px com lado/intensidade/fraqueza ao lado, exatamente como sugerido. Presente tanto no registro manual quanto no passo 2 do guiado |
| F2 | RESOLVIDO (já estava) | Dor manhã/noite no registro manual já são `<input type="range">` (sliders), iguais ao check-in guiado — não há mais `<input>` de texto livre |
| F3 | RESOLVIDO (já estava) | Crise e Fraqueza já são `ToggleTile` coloridos (mesmo padrão da Ciática). Pregabalina, Fexofenadina, Treino de força e "Acordou com dor" já mudam de cor de fundo/borda quando ativos (não são mais rótulo + texto estático) |
| F4 | RESOLVIDO (já estava) | Campo tipo do arquivo médico já usa `HEALTH_EXAM_TYPES` com 8 opções (Exame, Consulta, Cirurgia, Prescrição, Encaminhamento, Laudo de imagem, Atestado, Outro) nos dois formulários (criar/editar) e no badge do card |
| B6 | RESOLVIDO (já estava) | Card do arquivo médico já renderiza achadosChave, profissional/especialidade, próxima reavaliação e tags quando preenchidos. O lembrete de reavaliação (`verificar_reavaliacoes_saude`, agendado diariamente 8h BRT) já está implementado e importado em `main.py` |
| B7 | VERIFICADO | `grep` por `.toFixed(` sem `.replace('.', ',')` encadeado: 0 ocorrências em `HealthView.tsx` e `DashboardView.tsx`. Formatação pt-BR uniforme |
| B8 | RESOLVIDO (já estava) | `compareGroups(withValues, withoutValues, 8)` — piso mínimo já é 8, não 5. Frase já é "Dor média nos dias em que houve X: A · nos demais dias: B (n vs. n dias)" — não há mais a frase truncada "Dor com acordar com dor" |
| A12 | NÃO PROCEDE | Não é bug de código: o template `default_health_reminders` já define `waist_saturday` com `time: "07:00"` (tanto em `HealthView.tsx` quanto em `functions/main.py`). O valor "05:00" visto na revisão é o dado já persistido no documento Firestore desse lembrete específico, criado antes dessa correção de default. A hora é editável diretamente na tela de Lembretes Telegram (`<input type="time">` já existe por lembrete) — não precisa de mudança de código, só ajustar o horário salvo (sugestão do revisor: 08:00) |

### Fora da lista

- Nenhuma mudança fora dos achados listados nesta fase.

### Dúvidas para o revisor

- A8: quer que eu implemente o resumo lateral do já respondido (painel com o que já foi preenchido no check-in guiado), ou o ajuste de largura já resolve o suficiente por ora?
- A12: prefere que eu escreva direto no Firestore o novo horário do lembrete `waist_saturday` (07:00 ou 08:00), ou prefere ajustar você mesmo pela tela de Lembretes?
- Pendente de confirmação em produção (fora do alcance do dev server): B1 (service worker) e B4 (dedupe do alerta) já foram implantados no commit `03f94d0` e num commit anterior; produção verificada sem tela branca agora, mas B4 só é observável num evento real de sinal vermelho.
- N1 (Google Agenda) ainda não foi iniciado — é o próximo item da fila.

