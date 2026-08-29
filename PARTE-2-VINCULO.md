# Parte 2 — Vínculo entre ação e objetivo (CONGELADA até 15/10)

> **Nada nesta lista deve ser implementado antes de 15/10/2026.** O documento existe para que a
> discussão não precise ser reaberta do zero daqui a duas semanas: as decisões já tomadas estão
> registradas aqui, com o porquê. Quem retomar deve ler a premissa do item (b) antes de estimar
> qualquer coisa — ela muda o tamanho do trabalho.

## Onde isto se encaixa

O documento de estratégia tinha três partes. Duas já foram entregues:

- **Parte 1 — indicador de saúde lendo a fonte real** (PR #130, mesclado). O percentual de uma meta
  com `metrica_fonte` passa a vir da medida gravada, e "sem fonte" é `null`, nunca `0%` — um objetivo
  sem fonte não pode parecer um objetivo fracassado.
- **Parte 3 — detector de subproduto** (PR #131). O trabalho já feito que rende um ativo, proposto
  com teto mensal, e a decisão em `decidir_elevacao` (aceitar / adiar / nunca).

Esta é a **Parte 2**, e é a que fica de fora até 15/10.

## Regra transversal (já em vigor, vale para todos os itens abaixo)

Objetivo com **`gerida_por_acoes: false` nunca entra** em recurso de vínculo, sugestão ou elevação.
O corte é **pela flag, não pelo nome do pilar** — pilar é rótulo e muda; a flag é o que o sistema
consulta. Isto já está implementado em `deteccao_subproduto.objetivos_elegiveis` e em
`strategy_tools`, e qualquer item desta lista herda a regra sem renegociação: um objetivo servido
por dado (peso, cintura) não é servido por ação, e oferecê-lo como destino de vínculo é convidar o
usuário a mentir para o próprio painel.

## Os quatro itens

### (c) Relatório com "não vinculado" em primeira classe — **fazer primeiro**

Um relatório que mostra só o que está vinculado mede o próprio viés. "Não vinculado" precisa ser uma
faixa visível e contada, não a ausência de linha: é ela que diz se o vínculo está funcionando ou se
está sendo preenchido por obrigação.

Vem primeiro porque é **leitura pura**: não altera nenhum documento, não depende da unificação da
criação, e é o que dá a base de comparação para medir se (a) e (b) melhoraram alguma coisa. Fazer o
vínculo antes do relatório é ficar sem o "antes".

### (a) Vínculo retroativo em lote — **segundo**

Passar pelas ações que já existem e vinculá-las aos objetivos que servem. Duas restrições que já
foram decididas:

- **"Nenhum objetivo" é resposta legítima e comum.** Não é estado de erro, não é pendência a ser
  zerada. Forçar vínculo faz a estratégia parar de discriminar — se tudo serve a alguma coisa,
  o painel não informa mais nada.
- **Nada de casamento automático por semelhança.** Vale aqui o mesmo critério que fechou a discussão
  na lista de compras: casar por proximidade de texto erra feio e erra em silêncio. O lote propõe,
  o usuário decide.

Cada vínculo carrega **uma frase de justificativa** — por que esta ação serve este objetivo. Sem ela
o vínculo vira um id e ninguém sabe, três meses depois, se ainda faz sentido.

### (b) Vínculo no nascimento — **por último, e só depois da unificação**

> **PREMISSA DO ITEM, registrada a pedido do André:** não existe *um* caminho de criação de ação no
> Hermes — existem **quatro reimplementações**:
>
> 1. o handler compartilhado (`functions/tools/hermes_tools.py`);
> 2. o adaptador do copiloto web (`functions/main.py`, dentro de `askCopilotoHermes`);
> 3. a callable legada do Telegram (`functions/hermes_core_logic.py`);
> 4. o fluxo de confirmação do Telegram (`propor_acao_para_confirmacao` + o callback `confirm_acao`,
>    que monta um **terceiro documento** por conta própria).
>
> **Este item não deve começar adicionando um campo em quatro lugares. Deve começar unificando a
> criação.** Senão a gente paga esse pedágio para sempre: cada campo novo passa a custar quatro
> edições e três chances de esquecer uma.
>
> Isto não é teoria. Nesta mesma série de PRs o erro aconteceu **duas vezes** — campo novo que
> chegava por uma porta e sumia nas outras, em silêncio, sem erro nenhum. Foi por isso que o
> `estrategia_objetivo_id` **saiu** de `criar_acao_no_sistema` no PR #131: enquanto a criação estiver
> quadruplicada, vincular é um `editar_acao` explícito depois da criação, que é caminho único e
> sempre vale.

Ou seja: a ordem de trabalho dentro de (b) é **unificar a criação primeiro, vincular no nascimento
depois**. Se a unificação não couber, (b) não começa — o vínculo continua sendo o segundo passo, que
funciona.

### (d) Peso do esforço por materialidade

Nem toda ação vinculada contribui igual. Uma ação de quinze minutos e um projeto de três meses
vinculados ao mesmo objetivo não podem contar o mesmo, ou o progresso vira contagem de linhas.

É o item de menor urgência dos quatro e o mais fácil de errar: qualquer peso automático é um palpite
com cara de medida. Só faz sentido depois de (c) ter dado alguma base real sobre a distribuição.

## Ordem preferida

```
(c) relatório  →  (a) vínculo retroativo  →  (b) unificação da criação  →  (b) vínculo no nascimento
                                                                          →  (d) peso por materialidade
```

## Fora desta lista, e também parado

**Fechamento de marcos.** O André concordou com o parecer e vai **auditar os 8 marcos existentes
primeiro**, classificando-os em três grupos antes de qualquer mudança de comportamento.
**Não implementar nada** de fechamento de marco até essa auditoria voltar — o desenho depende do que
a auditoria encontrar, e implementar antes é escolher o desenho no escuro.

## Verificações em produção

As duas verificações de produção pendentes (indicador de saúde lendo a medida real, e a fila de
elevações aparecendo no resumo matinal) **são do André e ele as faz**. Não são tarefas desta lista.
