# Simulação de Empresa de Agentes (ambiente paralelo)

Backend de um **ambiente paralelo** onde agentes de IA, organizados como uma
empresa (diretoria + setores), executam as **ações que o Hermes já expõe** —
sem nunca tocar nos dados reais de produção.

Esta é a **camada lógica**. A camada gráfica (o "escritório" com os bonequinhos)
é construída por cima do stream de eventos descrito abaixo.

## Princípios de isolamento

- **Namespace travado:** toda escrita persistente acontece apenas sob
  `simulation/{sim_id}/...` (ver `FirestoreSimulationStore`). Nada de produção.
- **Dry-run por padrão:** o executor padrão (`dry_run_executor`) **não** chama
  ferramentas reais — apenas simula o resultado. Execução real é um seam futuro.
- **Humano no loop:** ver os três portões abaixo.

## Os três portões (decisão / aprovação / handoff humano)

Tarefas complexas têm vários caminhos, e nem tudo pode ser delegado a um agente.
O engine distingue **três** tipos de ponto de controle:

| Portão | Quem faz o trabalho | Quem decide | Modelo |
|---|---|---|---|
| **Aprovação** | o agente | humano valida (sim/não) | `Approval` |
| **Decisão / ramificação** | — | agente *ou* humano escolhe o caminho | `Task(kind=decision)` + `Branch[]` |
| **Handoff humano** | **só o humano** | a pessoa executa/decide e devolve | `Handoff` |

- **Aprovação:** ações sensíveis (registry real `needs_confirmation`) param e geram
  um `Approval`. Resolva com `engine.resolve_approval(id, approved=True/False)`.
- **Decisão:** um `Task(kind=decision)` tem `branches`. Por padrão o **agente
  escolhe** (decider plugável; offline pega o primeiro ramo). Se o nó for
  marcado `executor_type=human` (nó crítico), ele vira um `Handoff(kind=decision)`
  e **só um humano** escolhe. O ramo escolhido é ativado; os outros viram `skipped`.
- **Handoff humano (`executor_type=human`):** o agente reconhece que não pode
  produzir o resultado (assinar, decisão jurídica/política) e **estaciona** a
  tarefa como `awaiting_human`. A pessoa faz e devolve via
  `engine.resolve_handoff(id, result=...)` (ou `chosen_branch_id=...` numa decisão).
  O fluxo retoma de onde parou.

Guarda-corpos: dependências são satisfeitas por qualquer estado **terminal**
(`done/skipped/rejected/failed`), então ramos podados nunca travam a consolidação;
`run_until_idle(max_ticks)` evita loops infinitos.

## Disparando a simulação

- `engine.start(goal)` — a partir de um objetivo em texto livre.
- `engine.start_from_action(action)` — **ativa os agentes sobre uma Tarefa real
  do Hermes** (lê o `plano_de_acao` como esqueleto; passos com cara de "só humano"
  já nascem como handoff). A ação real é só lida; nada é escrito de volta nela.

Modo: `start(..., mode="live")` (palco, UI anima em tempo real) ou
`mode="background"` (bastidores, roda sozinho e só persiste). Mesma lógica, só
muda quem dirige o loop.

## Mapeamento para o Hermes existente

| Conceito da empresa | De onde vem no Hermes |
|---|---|
| Ações dos funcionários | `functions/tools/registry.py` (catálogo real) |
| Orquestrador / CEO | `orchestrator.py` (heurístico offline ou Gemini Pro) |
| Aprovação do presidente | `_NEEDS_CONFIRMATION` do registry |
| Setores | `roles.py` → áreas (FINANCEIRO, RH, TI, AQUISIÇÕES, ...) |
| Trabalho em paralelo | engine atribui tarefas a agentes ociosos por setor |

## Arquitetura

```
objetivo ──► orchestrator.plan() ──► [Tarefas por setor]
                                           │
                              engine.tick() (loop)
                                           │
          ┌────────────────────────────────┼───────────────────────────┐
          ▼                                ▼                            ▼
   atribui a agente             ação sensível? ──► Approval        ação normal
   ocioso do setor                  (PARA, espera                  ──► executa
                                     presidente)                      (dry-run)
                                           │
                          resolve_approval(approved) ──► executa / rejeita
                                           │
                                   emite SimEvents ──► (camada gráfica)
```

## Contrato de eventos (para a camada gráfica)

A UI do "escritório" deve renderizar `SimEvent`s (ver `models.py`). Tipos:

| `type` | Significado (o que o boneco faz na tela) |
|---|---|
| `sim_started` | Objetivo entra; CEO aparece (`data.mode`, `data.source_action_id`) |
| `plan_ready` | Tarefas distribuídas pelas salas dos setores |
| `agent_assigned` | Boneco pega a tarefa e vai para a mesa |
| `approval_requested` | Boneco levanta a mão / luz amarela; espera o presidente |
| `approval_granted` / `approval_denied` | Presidente decide; boneco volta a agir |
| `decision_made` | Nó de decisão resolvido; caminho escolhido acende |
| `branch_pruned` | Caminho descartado some/apaga |
| `handoff_requested` | Boneco escala para um humano (passo só-humano) |
| `handoff_done` | Humano devolveu o resultado; fluxo retoma |
| `task_done` | Boneco conclui (✓) e fica ocioso |
| `sim_done` | Empresa encerra o ciclo |

Cada evento traz `agent_id`, `task_id`, `message` e `data`. O estado visual de
cada boneco vem de `Agent.status`: `idle | working | waiting_approval | blocked`
(`blocked` = esperando um humano resolver um handoff).

## Como rodar

```bash
cd functions

# Testes (offline, sem credenciais)
python -m unittest test_simulation -v

# Demo: ver o "diário do escritório" em texto
python -m simulation.demo "Reduzir custos e renegociar compras com fornecedores"
```

## Próximos passos sugeridos

1. **Camada gráfica:** View React (`SimulacaoView` / "Escritório") que assina os
   eventos e anima os personagens por setor.
2. **Gemini Pro como CEO:** ligar `make_gemini_planner(api_key)` para planos mais
   ricos (fallback heurístico já garante que nunca trava).
3. **Cloud Function + Firestore real:** trocar `InMemoryStore` por
   `FirestoreSimulationStore` para a UI ler em tempo real via listeners.
4. **Múltiplos agentes por setor:** já suportado pelo engine — basta adicionar
   mais agentes ao roster em `roles.py`.
