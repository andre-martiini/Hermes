# Prompt — push + PR: escrita de código no repositório via conector Claude (argos-gestor-sistemas)

Contexto: o André decidiu que, daqui pra frente, push e abertura de PR passam a ser feitos pelo Claude diretamente através do conector Argos (chamadas de API do GitHub usando o GITHUB_PAT já guardado no servidor, nunca exposto ao Claude) — sem depender de git local nem de handoffs como este. Esta PR implementa exatamente essa capacidade (3 operações novas: criar/atualizar arquivo, criar branch, abrir PR). É meio irônico, mas verdadeiro: esta é provavelmente a ÚLTIMA vez que este tipo de handoff é necessário para uma mudança no próprio `argos-gestor-sistemas` — depois que isso for mesclado, implantado, e o GITHUB_PAT ganhar o escopo necessário (ver nota abaixo), o próprio Claude assume esse passo.

Já testado e revisado (incluindo uma revisão adversarial por sub-agente que encontrou e já corrigiu, antes deste commit, um path traversal real que teria permitido escrever em qualquer repositório acessível pelo mesmo token — corrigido com uma validação compartilhada `assertSafeRepoPath`, com testes de regressão). Não revise nem reescreva o código. `tsc --noEmit` limpo; `claude-connector.test.ts` 66/66; `devflow.test.ts` 9/9; `github-webhook.test.ts` 1/1; `devflow-worker.test.ts` 4/4 — sem regressão. O revisor humano é o próprio André, manualmente — não aprove nem faça merge.

Repositório: `andre-martiini/argos-gestor-sistemas` (remote `origin`). Pasta local: `argos-gestor-sistemas-main`.

Branch: `claude/conector-escrita-repositorio` (commit único `22891f6`), criada localmente a partir do que deveria ser o HEAD atual de `main` (equivalente a `a98ea56`, o merge da PR #9) — mas o `git fetch` não funciona neste ambiente (VM isolada sem credencial), então essa base pode estar desatualizada. **Antes de dar push, confirme que `main` de verdade não divergiu desde `a98ea56`; se tiver divergido, rebaseie a branch em cima do `main` atual antes de continuar.**

```
cd argos-gestor-sistemas-main
git fetch origin
git log --oneline origin/main -1   # confirme que bate com a98ea56, ou rebaseie se não bater
git push -u origin claude/conector-escrita-repositorio
gh pr create --base main --head claude/conector-escrita-repositorio \
  --title "feat(claude): escrita de código no repositório via conector (Contents/Git Data/Pulls API)" \
  --body "Três novas operações no conector Claude — writeRepoFile/argos_escrever_arquivo_repositorio (Contents API, cria/atualiza arquivo, recusa escrita direta em main), createRepoBranch/argos_criar_branch_repositorio (Git Data API) e createRepoPullRequest/argos_criar_pr_repositorio (Pulls API) — todas usando o GITHUB_PAT do servidor, nunca exposto ao Claude. Merge fica de fora por decisão (06/09/2026): push e PR passam a ser do Claude via este conector; merge continua clique manual do André. Revisão adversarial (sub-agente) encontrou e este commit já corrige um path traversal real (path como '../../outro-owner/outro-repo/contents/x' sobrevive ao encodeURIComponent e é colapsado pelo parser de URL do fetch, podendo redirecionar a chamada para qualquer repositório acessível pelo token) — já existia em getGithubRepoContents (leitura); corrigido nos dois pontos com assertSafeRepoPath + testes de regressão. Pré-requisito de infraestrutura fora deste PR: o GITHUB_PAT hoje só tem escopo de Issues/labels — as 3 operações só funcionam em produção depois de o token ganhar 'Contents: Read and write' e 'Pull requests: Read and write'. tsc --noEmit limpo; claude-connector.test.ts 66/66, devflow.test.ts 9/9, github-webhook.test.ts 1/1, devflow-worker.test.ts 4/4 — sem regressão."
```

Se `gh` não estiver disponível/autenticado, abra o PR pela interface web do GitHub com o mesmo título e corpo.

## Depois de mesclar

Mesmo padrão de sempre: revisão manual do André antes de mesclar (o Claude já revisou e corrigiu o que precisava); depois do merge, lançamento manual no Firebase App Hosting (sem CI/CD neste repositório) apontando pro commit do merge, e confirmar "Atual". **Adicionalmente, e só então**: o André precisa atualizar o `GITHUB_PAT` (secret do App Hosting) para incluir as permissões `Contents: Read and write` e `Pull requests: Read and write` (ideal: um fine-grained PAT escopado só aos repositórios que vão usar isso) — sem isso, as 3 novas tools respondem 403/404 do GitHub mesmo depois do deploy.
