# PR 2 (Fase 1) — `feat(agent-runs): observabilidade das sessoes agendadas`

**Pré-requisito:** PR 1 desta fase (`agent_requests`) mergeado. Não depende de nenhum outro PR.

## Por quê

O Eixo 6 do plano (autoaperfeiçoamento — seção 3 de `docs/plano-evolucao-hermes-jarvis.md`) precisa saber o que cada sessão agendada do Claude fez, para alimentar métricas de proatividade e a retro semanal. Hoje não existe nenhum registro: o briefing matinal e a varredura de follow-ups (rotinas do Cowork já criadas) rodam e terminam sem deixar rastro no Hermes — só o que aparece no outbox/diário/fila de atenção como efeito colateral. Isso não dá pra responder "quantas vezes a varredura rodou sem achar nada" ou "quanto tempo em média um item fica aberto antes de virar rascunho".

## Desenho — o mínimo que funciona

### Coleção `agent_runs`

Um documento por execução de qualquer rotina agendada (briefing, varredura, o futuro executor de `agent_requests`, ou qualquer uma que vier depois). Nada de schema rígido nos contadores — cada rotina registra o que faz sentido pra ela:

```
{
  rotina: "briefing_matinal" | "varredura_followups" | "executor_agent_requests" | <outro nome livre>,
  iniciado_em: <server timestamp ou ISO — ver abaixo>,
  finalizado_em: <server timestamp>,
  status: "sucesso" | "erro" | "parcial",
  resumo: "texto livre, uma ou duas frases do que a rotina fez",
  contadores: { ... },   # dict livre, ex.: {"itens_lidos": 4, "rascunhos_criados": 2}
  erro: "texto livre" | null,
}
```

### Novo módulo `functions/agent_runs.py`

Mesmo padrão de `agent_requests.py` (PR 1) e `atencao.py`: pouca lógica pura aqui porque não há decisão a validar — é essencialmente um log de eventos, não uma máquina de estados. Ainda assim, separe a função que monta o documento da que grava, para poder testar sem Firestore.

- `montar_registro(rotina, resumo, contadores=None, status="sucesso", erro=None, iniciado_em=None) -> dict`: validação simples (rotina e resumo são obrigatórios; `status` só aceita os três valores; se `status == "erro"`, `erro` é obrigatório) e monta o dict pronto para gravar. Retorna `{"erro": "..."}` se inválido — quem chama (a tool) decide o que fazer com isso.
- `registrar(db, **kwargs) -> dict`: chama `montar_registro`, se válido grava um doc novo em `agent_runs` (`add()`, id automático — não há necessidade de doc_id determinístico aqui, cada execução é um evento novo, não algo que se mescla) com `criado_em: firestore.SERVER_TIMESTAMP` além dos campos de `iniciado_em`/`finalizado_em` (que vêm como string ISO de quem chama, já que a rotina sabe seu próprio horário de início/fim — não force `iniciado_em` a ser sempre "agora"). Devolve `{"status": "ok", "run_id": ...}` ou o erro de validação.
- `listar_recentes(db, rotina: str | None = None, limite: int = 20) -> dict`: leitura, filtra por `rotina` se informado, ordena por `criado_em` decrescente (mais recente primeiro) — o oposto de `agent_requests.listar_pendentes`, que é mais antigo primeiro, porque aqui o uso é "o que aconteceu ultimamente", não "o que está esperando há mais tempo".

### Tools MCP novas

- **`registrar_execucao_agente`** (escrita, mesma categoria de `concluir_pedido_agente` do PR 1 — o próprio agente registrando o que ele mesmo fez, sem efeito em terceiro, **sem** exigir confirmação, **não** entra em `_NEEDS_CONFIRMATION` nem em `_CONFIRMACAO_OBRIGATORIA`): args `rotina`, `resumo`, `contadores` (objeto livre, opcional), `status` (opcional, padrão `"sucesso"`), `erro` (opcional, obrigatório só se `status == "erro"`).
- **`consultar_execucoes_agente`** (leitura): args `rotina` (opcional), `limite` (padrão 20, máx. 50). Chama `listar_recentes`.

Registre as duas no catálogo/schema/handler como sempre (`test_hermes_tools.py` cobre isso automaticamente).

## Travas

- `agent_runs` é só observabilidade — nenhuma lógica do sistema pode depender de ler essa coleção para decidir algo (ela não é fonte de verdade de nada, é log). Se um PR futuro quiser tomar decisão com base em execuções passadas (ex.: retro semanal sugerindo autonomia), ele lê `agent_runs`, mas a decisão em si nunca é automática — vira sugestão pro dono, como o resto do Eixo 6 já prevê.
- Grave sempre, mesmo quando `status: "erro"` — o objetivo é ver falha, não escondê-la.

## Testes

- `functions/test_agent_runs.py` (novo): `montar_registro` valida campos obrigatórios e o par `status`/`erro`; `registrar` grava e devolve `run_id`; `listar_recentes` filtra por `rotina` e ordena decrescente.
- `functions/test_hermes_tools.py`: cobertura automática das duas tools novas (já existente, só precisa que catálogo/schema/handler estejam consistentes).

Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Fora de escopo

Atualizar as rotinas agendadas já existentes (Briefing matinal, Varredura de follow-ups) para chamarem `registrar_execucao_agente` ao final **não é código deste PR** — isso é ajuste no prompt de cada rotina (`update_trigger`), feito depois que a tool existir. Quem faz esse ajuste é quem gerencia as rotinas, não o agente de desenvolvimento.

## Docs

`docs/okf/arquitetura/schema-firestore.md` (nova coleção `agent_runs`), `docs/okf/copiloto/mcp-servidor.md` (as duas tools novas), `docs/okf/log.md`.
