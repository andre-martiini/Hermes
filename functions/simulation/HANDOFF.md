# Handoff — Simulação de Empresa de Agentes (trabalho local)

Documento para você retomar o desenvolvimento da "empresa de agentes" na sua
máquina. Tudo que está descrito aqui **já foi mergeado** (PR #85) e está no
`main`.

---

## 1. Como pegar o código

```bash
git checkout main
git pull origin main
cd functions
```

O pacote vive em **`functions/simulation/`**. Não precisa de credenciais nem de
deploy para rodar/testar — é tudo offline.

```bash
# Rodar os testes (9, cobrindo os 3 portões)
python -m unittest test_simulation -v

# Ver o "escritório" trabalhando em texto
python -m simulation.demo "Decidir juridicamente a renegociacao do contrato de compras, assinar e avisar a equipe"
```

Python 3.11. Os módulos só usam stdlib; o engine importa `tools.registry` (do
próprio Hermes) para reusar o catálogo real de ferramentas e a regra de aprovação.

---

## 2. O que já está pronto

Uma **camada lógica** completa e isolada: agentes organizados como empresa
executam ações do Hermes num namespace paralelo (`simulation/`), em **dry-run**
(nada toca produção).

### Arquivos
| Arquivo | Papel |
|---|---|
| `models.py` | Dados: `Agent`, `Task`, `Branch`, `SimEvent`, `Approval`, `Handoff`, `Simulation` + enums |
| `roles.py` | Setores e roster padrão (CEO Atena + 7 setores), cada um com ferramentas reais |
| `orchestrator.py` | O "CEO": decompõe objetivo→tarefas. Planner heurístico (offline) + seam Gemini Pro |
| `engine.py` | Loop: atribuição, os 3 portões, stream de eventos |
| `store.py` | `InMemoryStore` (testes) e `FirestoreSimulationStore` (prefixo travado em `simulation/`) |
| `demo.py` | Runner de linha de comando |
| `test_simulation.py` | (em `functions/`) 9 testes end-to-end |
| `README.md` | Documentação de arquitetura + contrato de eventos |

### Os 3 portões (decisões de design já fechadas com você)
1. **Aprovação** — ação sensível (`tools.registry.needs_confirmation`) pausa e
   gera `Approval`. Você decide: `engine.resolve_approval(id, approved=True/False)`.
2. **Decisão ramificada** — `Task(kind="decision")` com `branches`. **O agente
   escolhe sozinho**, exceto em nós críticos (`executor_type="human"`), que viram
   handoff de decisão (só humano). Ramo escolhido ativa; os outros viram `skipped`.
3. **Handoff humano** — `executor_type="human"`: a tarefa estaciona em
   `awaiting_human`. **Pausa e devolve resultado**:
   `engine.resolve_handoff(id, result=...)` (ou `chosen_branch_id=...`). Retoma de
   onde parou.

### Gatilhos
- `engine.start(goal)` — objetivo em texto livre.
- `engine.start_from_action(action_dict)` — **ativa os agentes sobre uma Tarefa
  real do Hermes** (lê `plano_de_acao` como esqueleto; passos "só humano" já
  nascem como handoff). A ação real é só lida.
- Modo: `mode="live"` (palco) ou `mode="background"` (bastidores).

---

## 3. Trecho de exemplo para começar a mexer

```python
from simulation import SimulationEngine, InMemoryStore

eng = SimulationEngine(store=InMemoryStore())
eng.start("Decidir a estrategia geral e assinar o contrato")
eng.run_until_idle()                       # roda até parar (esperando humanos)

for h in eng.store.list_pending_handoffs():
    print(h.kind, "->", eng.store.get_task(h.task_id).title)
    eng.resolve_handoff(h.id, result="feito")   # você no papel de humano
for a in eng.store.list_pending_approvals():
    eng.resolve_approval(a.id, approved=True)    # você no papel de presidente

eng.run_until_idle()
print(eng.store.get_sim().status)          # 'done'
for e in eng.store.list_events():
    print(e.type, e.message)
```

---

## 4. Próximos passos sugeridos (em ordem de menor risco)

1. **Gemini Pro como CEO/decider** (backend, sem frontend)
   - Em `orchestrator.py`, ligar `make_gemini_planner(api_key)` no lugar do
     heurístico. Já tem fallback resiliente — se o Gemini falhar, cai no heurístico.
   - Criar um `decider` que use Gemini para escolher o ramo (hoje
     `first_branch_decider` pega o primeiro). Passar via
     `SimulationEngine(decider=...)`.
   - Modelo: usar `GEMINI_PRO_MODEL` de `gemini_cost_controls.py`.

2. **Persistência real + endpoints** (para testar no sistema deployado)
   - Trocar `InMemoryStore` por `FirestoreSimulationStore(sim_id)`.
   - Criar callables em `functions/main.py` (`@https_fn.on_call()`):
     `runSimulation`, `resolveSimulationApproval`, `resolveSimulationHandoff`,
     `getSimulationState`. Frontend chama via `httpsCallable`.
   - "Tela" provisória = Firestore Console na coleção `simulation/`.

3. **Camada gráfica (o escritório)**
   - View React/Tailwind que assina os eventos (`SimEvent`) e anima bonecos por
     setor. Estado visual vem de `Agent.status`
     (`idle | working | waiting_approval | blocked`).
   - Contrato de eventos completo no `README.md` (tabela de `type`).

---

## 5. Limitações conscientes / gotchas

- **Decisões aninhadas** (um ramo que abre outra decisão) ainda **não cascateiam
  a poda** — os planos gerados hoje são de um nível. Reforçar ao ir pro Gemini.
- **Contenção de recurso é real e proposital:** há 1 agente por setor. Se duas
  tarefas do mesmo setor estão prontas, uma espera. Para paralelismo, adicione
  mais agentes ao roster em `roles.py` (o engine já suporta N por setor).
- **`FirestoreSimulationStore` não é testado** (é seam para o futuro). Ele já
  remonta `Branch` aninhado ao ler, mas valide antes de confiar em produção.
- **Execução é dry-run.** `dry_run_executor` só simula. Execução real das
  ferramentas é um seam (`executor=` no engine) — fazer com cuidado e sempre com
  os portões ligados.
- Dependências são satisfeitas por qualquer estado **terminal**
  (`done/skipped/rejected/failed`) — é o que evita que ramos podados travem a
  consolidação final.

---

## 6. Onde isto se encaixa no Hermes

- Ações dos agentes = `functions/tools/registry.py` (catálogo real).
- Aprovação = `_NEEDS_CONFIRMATION` do mesmo registry.
- Setores = áreas temáticas (FINANCEIRO, RH, TI, AQUISIÇÕES, ...).
- Modelos Gemini = `functions/gemini_cost_controls.py` (`GEMINI_PRO_MODEL`).

Bom trabalho! Qualquer dúvida, o `README.md` do pacote tem o detalhe de
arquitetura e o contrato de eventos.
