# PR 1 (Fase 2) — `feat(pessoas): modelo_interacao auto-mantido em perfil_pessoas`

**Pré-requisito:** nenhum — Fase 1 está completa (5/5 PRs mergeados) e este é o primeiro PR da Fase 2 ("Reflexos") do plano de evolução Hermes→Jarvis.

## Por quê

O plano (`docs/plano-evolucao-hermes-jarvis.md`, Eixo 4, "Modelo por pessoa") descreve um perfil comportamental auto-mantido por contato: como o André fala com essa pessoa, tempo típico de resposta dela, e em quais ações ela aparece. Isso alimenta três coisas que ainda fazemos de cabeça hoje: o redator de rascunhos de WhatsApp (para acertar o tom), o briefing matinal ("Fulano costuma responder em 2h; está há 6h sem responder") e o detector de promessas sem retorno (Fase 0, já existe).

## O que já existe (não reinventar)

- `perfil_pessoas/{id}` — coleção de contatos, com `nome`, `whatsapp_chat_id`, `tags`, `origem`. Já tem tools de leitura/escrita (`buscar_contato`, `preparar_atualizacao_contato`, `registrar_interacao_contato` em `tools/hermes_tools.py`).
- `interacoes_pessoas` — já é o histórico de interações por pessoa, alimentado por dois lugares: `registrar_interacao_contato` (tipo `mencao_copiloto`, quando o Copiloto menciona a pessoa) e `knowledge_graph.py::on_tarefa_written_extract_people` (tipo `mencao_tarefa`/`mencao_diario`, quando o extrator de pessoas acha o nome dela numa tarefa/diário). Cada doc tem `pessoa_id`, `tarefa_id` (quando aplicável), `tipo`, `data`, `descricao`. **Esta coleção já é a fonte de "ações em que a pessoa aparece" — não precisa de um novo campo de vínculo.**
- `whatsapp_messages` — mensagens indexadas por `chat_id`, `timestamp`, `from_me`, `content` (ver uso em `inbox_pendentes.py` e `atencao.py`).
- `generate_content_logged` (`gemini_cost_controls.py`) e `GEMINI_STRUCTURED_MODEL` — mesmo caminho de custo controlado usado pelo `contexto_agente` (PR 5 da Fase 1) e pelo extrator de pessoas.

## Desenho — o mínimo que funciona

### Novo campo `perfil_pessoas.modelo_interacao`

Dict, mesmo espírito do `contexto_agente`:

```
{
  registro: "descrição curta do tom/formalidade que o André usa com essa pessoa (ex: 'formal, trata por Dr.', 'informal, brincam bastante')" | null,
  tempo_resposta_tipico: "descrição textual (ex: 'costuma responder em ~2h durante o dia útil')" | null,
  acoes_recentes: ["título da ação (id)", ...],
  atualizado_em: <ISO>,
}
```

**Regra inegociável do prompt (mesma do `contexto_agente`):** nunca inventar `registro` ou `tempo_resposta_tipico` se o texto-fonte não tiver sinal suficiente — melhor `null` do que um palpite. Poucas mensagens ou nenhuma troca bidirecional → `null` nesses dois campos, não uma generalização vazia tipo "cordial".

### Por que NÃO é um trigger `on_document_written` (diferente do `contexto_agente`)

`contexto_agente` reage a escrita de UMA tarefa. Aqui o sinal está espalhado em `whatsapp_messages` (potencialmente centenas de mensagens por contato) — reagir a cada mensagem individual chamaria o Gemini a cada mensagem nova, sem necessidade e caro. O padrão certo aqui é o mesmo do `ai_notification_planner_daily`: **job agendado** (`@scheduler_fn.on_schedule`), rodando 1x/dia fora do horário de pico (sugestão: 5h30, antes do briefing das 6h45 mencionado no plano).

### Job diário `atualizar_modelos_pessoas`

1. Itera `perfil_pessoas` filtrando quem tem `whatsapp_chat_id` preenchido — sem chat vinculado não há sinal de tom/tempo de resposta pra extrair.
2. Para cada pessoa, filtro de custo (não gastar Gemini com contato de baixo sinal): pula se tiver menos de N mensagens no total nos últimos 90 dias (sugestão N=6) E menos de 1 entrada em `interacoes_pessoas` — nesse caso não teria material suficiente pra sintetizar nada além de `null`.
3. Monta o texto-fonte: últimas ~40 mensagens de `whatsapp_messages` (`chat_id`, ordenado por `timestamp` desc, depois invertido pra ordem cronológica) rotuladas por `from_me` (André) ou não (a pessoa), e as últimas ~10 entradas de `interacoes_pessoas` dessa pessoa (pra listar `acoes_recentes` a partir do `tarefa_id`/`descricao`).
4. Hash de dedupe igual ao `contexto_agente`/extrator de pessoas: MD5 do texto-fonte em `perfil_pessoas.last_processed_modelo_hash`; pula a chamada ao Gemini se não mudou desde ontem.
5. Chama o Gemini via `generate_content_logged` (`feature="modelo_pessoa"`, `model=GEMINI_STRUCTURED_MODEL`) com um prompt que pede exatamente o shape acima e repete a regra de nunca inventar.
6. Parse defensivo idêntico ao já usado (regex de objeto JSON, fallback de cerca markdown). Falha ou vazio → grava só o hash, mantém o `modelo_interacao` anterior se houver.
7. Grava `modelo_interacao` + `last_processed_modelo_hash` em `perfil_pessoas/{id}` via `update()`.
8. Toda a função por pessoa isolada em `try/except` — uma pessoa falhando não pode interromper o loop das demais (mesmo princípio do `anotar_evento_github_em_tarefas` da PR 4).

### `buscar_contato` inclui o campo (mesmo espírito do `obter_acao`)

Em `tools/hermes_tools.py::buscar_contato`, incluir `modelo_interacao` no dict retornado por contato, quando presente.

## Travas

- Não gaste chamada de Gemini em contato sem `whatsapp_chat_id` ou com sinal insuficiente — filtro dos passos 1-2 vem antes de qualquer I/O de LLM, mesmo princípio de custo do `contexto_agente`.
- Mão única: `whatsapp_messages` e `interacoes_pessoas` são a fonte; este PR nunca escreve nelas, só lê.
- Falha ao gerar o modelo de uma pessoa nunca pode interromper o processamento das demais nem o resto do job diário.
- Fora de escopo (ver abaixo): não tente cruzar com a fila `atencao` para achar "promessas em aberto" — o campo `pessoa` nos itens de `atencao.py` é texto livre, não uma referência a `perfil_pessoas.id`, e criar esse cruzamento direito é trabalho de outro PR, não deste.

## Testes

- Função pura de filtro "tem sinal suficiente?" (contagem de mensagens/interações) testável isolada, sem Firestore.
- Montagem do texto-fonte e do hash: testável com listas de mensagens/interações mockadas, sem Firestore nem Gemini.
- Parse da resposta do Gemini (JSON limpo, cercado, vazio, inválido) — mock da chamada.
- Teste confirmando que pessoa sem `whatsapp_chat_id` ou com sinal insuficiente não chama o Gemini.
- Teste de isolamento de falha: uma pessoa lançando exceção não impede o processamento das próximas no loop.
- `buscar_contato` inclui `modelo_interacao` quando presente e omite/`None` quando ausente.

Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Fora de escopo

- Cruzar com a fila `atencao` para contar promessas em aberto por pessoa (precisa de um vínculo `pessoa_id` que a fila ainda não tem — discussão separada, possivelmente um PR futuro da própria Fase 2).
- UI para editar `modelo_interacao` manualmente — é só leitura, gerado e mantido pelo job.
- Rodar para contatos sem WhatsApp vinculado (e-mail, por exemplo) — fica para uma extensão futura se fizer sentido.

## Docs

`docs/okf/arquitetura/schema-firestore.md` (novo campo `perfil_pessoas.modelo_interacao` e `perfil_pessoas.last_processed_modelo_hash`), `docs/okf/log.md`.
