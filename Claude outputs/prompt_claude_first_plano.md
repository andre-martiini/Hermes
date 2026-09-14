# Prompt — push + PR do fluxo "Claude First" de propor e aprovar plano (argos-gestor-sistemas)

Contexto: o código abaixo já foi implementado, testado e commitado localmente por outra IA (Claude, via ponte com o computador do André), rodando num ambiente sem credencial de git push. Sua tarefa é só aplicar o que já está pronto: dar push na branch e abrir o Pull Request. Não revise nem reescreva o código — isso já foi testado (`tsc --noEmit` limpo; 49/49 testes em `claude-connector.test.ts`, sem regressão em `devflow.test.ts`, `github-webhook.test.ts` e `devflow-worker.test.ts`). O revisor do PR é o próprio André, manualmente, pelo Google Antigravity — não aprove nem faça merge.

Repositório: `andre-martiini/argos-gestor-sistemas` (remote `origin`). Pasta local: `argos-gestor-sistemas-main`.

Branch: `claude/plano-claude-first-argos` (commit `30acb81`, baseada em `origin/main` no commit `364afb0` — já inclui as 4 frentes do conector Claude-Argos que estavam mescladas até agora).

```
cd argos-gestor-sistemas-main
git push -u origin claude/plano-claude-first-argos
gh pr create --base main --head claude/plano-claude-first-argos \
  --title "feat(claude): fluxo Claude First para propor e aprovar plano em um passo" \
  --body "Nova operação argos_propor_e_aprovar_plano (MCP) / POST .../propose-and-approve-plan (REST): a partir de triage, planning ou plan-review, publica a Issue da demanda se ainda não existir, posta o plano em Markdown como comentário na Issue e já aprova o plano, movendo a demanda direto para plan-approved — sem um estágio separado de revisão do plano. A aprovação humana passa a ser a própria decisão no Telegram (Hermes), tomada depois de ver o link da Issue com o plano completo. Continua exigindo autorizacaoId como trilha de auditoria, no mesmo padrão de approvePlanDemand e enqueueDemandJob. triage não tem aresta direta para plan-approved no grafo de VALID_TRANSITIONS (só triage → planning); a nova operação valida a cadeia triage → planning → plan-approved sem persistir o estado intermediário, evitando um round-trip extra pelo webhook do GitHub a cada chamada. tsc --noEmit limpo; 49/49 testes em claude-connector.test.ts (14 tools MCP no total agora), sem regressão nos demais arquivos de teste."
```

Se `gh` não estiver disponível/autenticado, abra o PR pela interface web do GitHub com o mesmo título e corpo.

## Depois de mesclar

Diferente do gestao-Hermes, o argos-gestor-sistemas (Firebase App Hosting) **não tem CI/CD nem redeploy automático em push para `main`** — é preciso criar um novo "lançamento" manualmente no console do Firebase App Hosting depois do merge (Lançamentos → Criar lançamento → Link do GitHub → branch `main` → Commit mais recente → Criar). Sem esse passo, o código mesclado não entra em produção. Confirme no console que o rollout ficou "Atual" apontando para o commit do merge.

Depois do deploy confirmado, ainda falta o primeiro teste real do novo fluxo em produção (Claude escreve o plano de verdade, chama `argos_propor_e_aprovar_plano`, pede autorização no Telegram com um resumo linkando a Issue, o André aprova) — isso fica para o André e o Claude testarem juntos depois, não faz parte deste handoff.
