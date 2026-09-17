# Prompt — push + PR: avançar plan-approved → ready-for-execution sem passo manual (argos-gestor-sistemas)

Contexto: durante o primeiro teste real de ponta a ponta do fluxo "Claude First" (demanda DEV-2026-0002), ficou claro que, depois do plano aprovado (`plan-approved`), não existia nenhuma tool do conector Claude para avançar a demanda para `ready-for-execution` — só dava para fazer isso mudando o label manualmente no GitHub (que dispara o webhook) ou direto no console. O André pediu para isso ficar automático nas próximas vezes. Outra IA (Claude, via ponte com o computador do André) implementou, testou e commitou localmente. Sua tarefa é só dar push da branch nova e abrir o PR. Não revise nem reescreva o código — já testado (`tsc --noEmit` limpo; `claude-connector.test.ts` 57/57 — 15 tools MCP no total agora —, `devflow.test.ts` 7/7, `github-webhook.test.ts` + `devflow-worker.test.ts` 5/5, sem regressão). O revisor do PR é o próprio André, manualmente, pelo Google Antigravity — não aprove nem faça merge.

Repositório: `andre-martiini/argos-gestor-sistemas` (remote `origin`). Pasta local: `argos-gestor-sistemas-main`.

Branch: `claude/marcar-pronto-para-execucao` (commit `84b2059`, criada a partir do commit já mesclado em `main` no PR #8 — merge commit `b9aa8fa`).

```
cd argos-gestor-sistemas-main
git push -u origin claude/marcar-pronto-para-execucao
gh pr create --base main --head claude/marcar-pronto-para-execucao \
  --title "feat(claude): avançar plan-approved para ready-for-execution sem passo manual" \
  --body "Nova operação advanceToReadyForExecution (MCP argos_marcar_pronto_para_execucao / REST POST .../ready-for-execution): avança a demanda de plan-approved (ou preparing) para ready-for-execution e sincroniza o label no GitHub, sem exigir autorizacaoId. NÃO é portão humano — as decisões humanas de verdade já aconteceram em approvePlanDemand (aprovar o plano) e voltam a acontecer em enqueueDemandJob (autorizar o enfileiramento); este passo intermediário é só bookkeeping de estado/label, sem efeito irreversível. Motivado por um gap real encontrado ao testar a DEV-2026-0002 em produção: não havia como chegar em ready-for-execution pelo conector, só mudando o label manualmente no GitHub ou pelo console. Reaproveita isValidDevFlowTransition/labelForState/replaceGithubStatusLabel; inclui a mesma proteção contra corrida (transação com verificação de estado fresco) adicionada em approvePlanDemand no PR #7. tsc --noEmit limpo; claude-connector.test.ts 57/57 (15 tools MCP no total agora), devflow.test.ts 7/7, github-webhook.test.ts + devflow-worker.test.ts 5/5 — sem regressão."
```

Se `gh` não estiver disponível/autenticado, abra o PR pela interface web do GitHub com o mesmo título e corpo.

## Depois de mesclar

Mesmo padrão de sempre: revisão manual do André pelo Antigravity antes de mesclar; depois do merge, como o `argos-gestor-sistemas` (Firebase App Hosting) não tem CI/CD, é preciso criar um novo lançamento manualmente no console (Lançamentos → Criar lançamento → Link do GitHub → branch `main` → Commit mais recente → Criar) e confirmar que o rollout ficou "Atual" apontando para o commit do merge. Só depois disso o teste de ponta a ponta da DEV-2026-0002 pode avançar para `ready-for-execution` e, na sequência, testar `argos_enfileirar_execucao` pela primeira vez.
