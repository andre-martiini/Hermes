# Painel do dia unificado — orientação para o desenvolvedor

Objetivo: uma tela só, que substitui o "Resumo do dia" (`src/views/MorningSummaryView.tsx`) e absorve o que ele tem de útil no Dashboard (`DashboardView.tsx`), mais elementos do briefing da manhã do agente. Além do layout, o trabalho inclui as mudanças de dados e de código que mantêm a tela **sempre atualizada e coerente** com o resto do Gaspar.

Design de referência: artefato "Painel do dia" no Claude Design (duas versões: horizontal 1440 px e retrato 1080 px, monitor em coluna única). O link é privado; peça ao André para compartilhar. A estrutura abaixo basta para implementar.

## 1. O que a tela mostra (ordem na versão retrato)

1. **Cabeçalho**: "Bom dia, André · terça-feira", data, "N ações hoje · M em espera".
2. **Decidir** (novo, vem do briefing): até 3 linhas visíveis, "Ver mais N" abre o resto. Cada linha: número, quem/assunto, o que fazer, recomendação em cinza, tag opcional ("hoje", "venceu ontem") e botão **Feito/Desfazer**. Rodapé: aviso de elevações sugeridas (o antigo "Avisos do sistema") com botão "Ver sugestões" que abre os cards Aceitar/Descartar.
3. **Prazos finais**: faixa discreta, como hoje.
4. **Agenda de hoje**: caixa "Próximo/Em breve/Já vai começar/Agora", aviso de conflito, linha do tempo 7h–19h com marcador "agora", faixa **Preparo** (próximos dias) e lista completa recolhível com lembretes.
5. **Ações de hoje**: faixa "O agente prepara hoje", filtro "Só o que o agente faz", legenda, ações ativas, bloco "Em espera" (compacto, ver 3.5).
6. **Carga semanal**, 7. **Caminhada** (registro), 8. **Avisos do agente** (ex.: "Não li hoje: e-mail e SIGFAPES") e links discretos para Resumo financeiro e Saúde e telemetria.

Decisões já tomadas com o André (não reabrir): sem "adiada N vezes"; sem botão "Passar ao agente" (ele trabalha em sessões por ação e pede ao agente para executar); espera fica embaixo e ativas em cima, como no Dashboard atual; barra do dia conta só ações ativas ("0 de 5"); texto "agente", não "Claude", porque qualquer IA com o conector Gaspar pode executar.

## 2. Fontes de dados — uma fonte por campo

| Bloco | Fonte | Observação |
|---|---|---|
| Ações, etapas, espera | `resumo_matinal/{hoje}` define o conjunto; `tarefas/{id}` é a fonte viva (já é assim em `DashboardView.tsx`) | Manter `onSnapshot` por tarefa. Espera = `subtarefa_do_dia.estado == aguardando_terceiro`. |
| Agenda, janelas, conflitos | agenda do dia já coletada em `functions/morning_summary.py` (`_coletar_agenda`) | Conflito é **calculado no cliente** por sobreposição de intervalos, nunca gravado. |
| Prazos finais, filas, elevações, avisos do sistema | `resumo_matinal` (`_coletar_filas`, `_coletar_avisos_do_sistema`, `_coletar_passivo_de_elevacao`) | Conferir os nomes dos campos antes de ligar. |
| Carga semanal, caminhada | já existentes no Dashboard | Sem mudança. |
| Decidir, Foco, "O agente prepara hoje", Preparo, fora da agenda, Avisos do agente | **novo documento `briefing_dia/{YYYY-MM-DD}`**, escrito pelo agente | Ver 3.2. |
| Etiquetas "Agente faz/prepara" | novo campo por etapa (3.1) | Calculado: contador de etapas para o agente nunca é gravado. |

## 3. Mudanças de código

### 3.1 Campo novo na etapa do plano de ação
- `types.ts`, `ActionPlanItem`: `executor?: 'agente' | 'agente_aprovado' | 'humano'` (ausente = `humano`) e `executor_como?: string` (uma frase, até 140 caracteres: como o agente faria). Adicionar também `executor_definido_por?: 'agente' | 'usuario'`.
- `agente`: o agente faz sozinho. `agente_aprovado`: o agente prepara e o André aprova (mensagem a terceiro, rascunho, merge). `humano`: só o André; sem etiqueta na tela.
- Espelhar em `functions/subtarefas.py` e `src/utils/subtarefas.ts` (os dois já são espelhos um do outro): normalizar valor desconhecido para `humano`; preservar o campo em `comEstado` e em qualquer gravação de plano pela tela, para não apagar a marca.
- Tools em `functions/tools/schemas/`: `editar_etapa` e `editar_plano_acao` passam a aceitar `executor` e `executor_como`; `obter_acao` e `obter_estado_atual` passam a devolver. Omitir preserva (mesma regra dos outros campos).
- Quem preenche: o agente sugere ao criar ou editar o plano; o André corrige na tela (menu pequeno na etapa). Correção do André grava `executor_definido_por: 'usuario'`, e o agente **não sobrescreve** etapa com essa marca.
- Só etapas **em aberto** (não `feito`) contam. Regra de negócio já registrada: ação que espera terceiro fica ativa, com "Aguardar X" como primeira etapa.

### 3.2 Novo documento `briefing_dia/{YYYY-MM-DD}`
Hoje o briefing das 05:00 (`services/gaspar-agente/.claude/briefing.md`) sai só como texto no Telegram. Passa a **também gravar** este documento (o texto do Telegram continua):

```json
{
  "data": "2026-10-27",
  "gerado_em": "timestamp",
  "hoje": [{ "acao_id": "...", "motivo": "prazo 31/10" }],
  "decidir": [{
    "id": "d1", "ordem": 1, "quem": "Enfermaria",
    "texto": "TR, itens 21, 26 e 28: converter para UNIDADE",
    "recomendacao": "É o que o diário recomenda.",
    "tag": "hoje",
    "origem": "fila_atencao | whatsapp | etapa | acao",
    "ref": "id do item de origem",
    "status": "pendente | feito | dispensado",
    "resolvido_em": null
  }],
  "eu_faco": [{ "acao_id": "...", "texto": "ler o relatório e montar a versão executiva em rascunho", "status": "proposto | aprovado | pronto | recusado" }],
  "preparo": [{ "dia": "2026-10-28", "texto": "retirar o carro na Localiza, 9h" }],
  "fora_da_agenda": [{ "titulo": "Conselho de Escola — EMEF", "inicio": "13:50", "fim": null, "motivo": "reunião que não está na agenda" }],
  "avisos": [{ "tipo": "nao_li | conversa | dado_suspeito", "texto": "Não li hoje: e-mail e SIGFAPES." }],
  "menores": 2
}
```

Tools MCP novas (esquemas em `functions/tools/schemas/`, mesmo padrão das existentes): `registrar_briefing_dia` (agente grava/atualiza o dia, com merge por `id`), `obter_briefing_dia` (leitura) e `resolver_item_briefing` (marca `feito`/`dispensado`). Atualizar `briefing.md` para chamar `registrar_briefing_dia` logo depois de montar o texto, e permitir que o agente atualize o documento durante o dia quando algo mudar.

### 3.3 Dashboard
- `DashboardView.tsx`: ligar `onSnapshot` em `briefing_dia/{hoje}` ao lado do de `resumo_matinal`; criar os blocos Decidir, Preparo, faixa "O agente prepara hoje", Avisos do agente; chip/ícone de Foco nas ações cujo id esteja em `briefing_dia.hoje`.
- A rota "Resumo do dia" (`MorningSummaryView`) passa a redirecionar para o Dashboard; manter o componente até a migração terminar, depois remover junto dos testes (`MorningSummaryView.test.tsx`).
- Botão **Feito** em Decidir grava `status` e `resolvido_em` via `resolver_item_briefing` (ou escrita direta com transação), e desfazer volta a `pendente`.

### 3.4 Agenda: efeito de proximidade
- Calculado no cliente com o relógio real (atualizar a cada 30 s). Níveis: normal (> 30 min), **atenção** (≤ 30 min: âmbar, brilho lento), **urgente** (≤ 15 min: roxo forte, pulso rápido), **agora** (dentro do compromisso: verde, "até HH:MM"). O bloco na linha do tempo recebe o mesmo destaque.
- Respeitar `prefers-reduced-motion` (só cor, sem animação). Limites 30 e 15 em constantes nomeadas.
- Evento de `fora_da_agenda` entra na linha do tempo tracejado e participa do cálculo de conflito.

### 3.5 Bloco "Em espera" compacto
Uma linha por ação: ícone de pausa, título, **ícone** de Foco (bandeira, tooltip com o motivo), relógio + nome de quem se espera, **ícone** do agente com o número de etapas, contador feitas/total e botão só com seta que abre as etapas. Nada de texto repetido nas linhas.

## 4. Coerência (o que não pode acontecer)

1. **Sem número gravado que dá para calcular**: contagem de etapas do agente, "N de M concluídas", conflitos de agenda e "em N dias" são sempre derivados na leitura.
2. **Item da IA sempre aponta para a origem** (`acao_id`, `ref`). Na renderização, se a origem já não pede nada (ação concluída, etapa feita, resposta enviada, item da fila resolvido), o item some ou aparece como feito, mesmo que o briefing ainda o liste.
3. **Mesma regra de espera em todo lugar**: `subtarefa_do_dia.estado == aguardando_terceiro` tira da lista principal e do cálculo do dia.
4. **O briefing é uma foto das 05:00**; o que é vivo (ações, agenda, filas) vem das fontes vivas. Só Decidir, Preparo, Foco e "O agente prepara" dependem do documento do briefing.
5. **Duas escritas nunca divergem**: tela e agente passam pelo mesmo contrato (`subtarefas.py`/`subtarefas.ts`), incluindo o novo `executor`.

## 5. Critérios de aceite
- Marcar etapa como `agente` pelo MCP aparece na tela sem recarregar, e o contador da ação muda.
- Etapa que o André corrigiu para `humano` continua assim depois de o agente reeditar o plano.
- Concluir uma ação ou resolver um item da fila faz o item correspondente sair de Decidir sem recarregar.
- Com `briefing_dia` ausente, a tela abre normal, sem os blocos novos e sem erro.
- Conflito de agenda e efeito de proximidade corretos em 29, 30, 15 e 14 minutos (testar com relógio injetável) e com `prefers-reduced-motion`.
- Testes: unitários do espelho `subtarefas` (py e ts) com `executor`, do contrato das tools novas, e do cálculo de proximidade/conflito.

## 6. Ordem sugerida de PRs
1. Campo `executor` (tipos, espelhos, schemas, testes).
2. `briefing_dia` + tools + ajuste de `briefing.md`.
3. Dashboard: blocos novos, agenda (proximidade e conflito), Em espera compacto.
4. Redirecionar e depois remover o Resumo do dia.
