# Prompt — push + PR da correção "is:issue" na busca de Issue (argos-gestor-sistemas)

Contexto: bug pré-existente (não relacionado ao fluxo Claude First) encontrado por outra IA (Claude, via ponte com o computador do André) ao testar de ponta a ponta a demanda DEV-2026-0002 em produção. A API de busca do GitHub (`/search/issues`) passou a exigir `is:issue` ou `is:pull-request` na query — sem isso ela responde 422. Isso quebrava `findGithubIssueByMarker`, usada sempre que uma demanda partindo de `triage` precisa publicar sua Issue pela primeira vez. Já corrigido e commitado localmente. Sua tarefa é só dar push da branch nova e abrir o PR. Não revise nem reescreva o código — já testado (`tsc --noEmit` limpo; `devflow.test.ts` 7/7, `claude-connector.test.ts` 51/51, `github-webhook.test.ts` 1/1, sem regressão). O revisor do PR é o próprio André, manualmente, pelo Google Antigravity — não aprove nem faça merge.

Repositório: `andre-martiini/argos-gestor-sistemas` (remote `origin`). Pasta local: `argos-gestor-sistemas-main`.

Branch: `claude/fix-github-search-is-issue` (commit `c7d57dc`, criada a partir do commit `688172d` — que é o mesmo conteúdo já mesclado em `main` no PR #7, merge commit `3d286c9`). Um único arquivo alterado: `src/server/devflow.ts`, uma linha.

```
cd argos-gestor-sistemas-main
git push -u origin claude/fix-github-search-is-issue
gh pr create --base main --head claude/fix-github-search-is-issue \
  --title "fix(devflow): incluir is:issue na busca de Issue existente no GitHub" \
  --body "A API de busca do GitHub (/search/issues) passou a exigir que a query inclua is:issue ou is:pull-request — sem isso ela responde 422 (\"Query must include 'is:issue' or 'is:pull-request'\"). findGithubIssueByMarker fazia essa busca sem o qualificador, então toda demanda que precisasse publicar uma Issue pela primeira vez (partindo de triage) quebrava. Bug pré-existente, não relacionado ao fluxo Claude First (PR #7) — encontrado ao testar de ponta a ponta a DEV-2026-0002 em produção. tsc --noEmit limpo; devflow.test.ts 7/7, claude-connector.test.ts 51/51, github-webhook.test.ts 1/1 — sem regressão."
```

Se `gh` não estiver disponível/autenticado, abra o PR pela interface web do GitHub com o mesmo título e corpo.

## Depois de mesclar

Mesmo padrão de sempre: revisão manual do André pelo Antigravity antes de mesclar; depois do merge, como o `argos-gestor-sistemas` (Firebase App Hosting) não tem CI/CD, é preciso criar um novo lançamento manualmente no console (Lançamentos → Criar lançamento → Link do GitHub → branch `main` → Commit mais recente → Criar) e confirmar que o rollout ficou "Atual" apontando para o commit do merge. Só depois disso o teste de ponta a ponta da DEV-2026-0002 pode ser retomado.
