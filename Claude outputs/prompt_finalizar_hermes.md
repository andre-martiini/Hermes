# Prompt — últimos ajustes para o gate de autorização entrar em produção no Hermes

Contexto: as 4 frentes do conector Claude-Argos já estão prontas. As 3 primeiras (leitura de repositório, escrita de issues, allowlist "*") e o lado Argos da quarta (gate de autorização) já estão em produção. Falta só o lado Hermes da quarta frente chegar em `main` e ser implantado. Repositório: `gestao-Hermes`. Pasta local: `gestao-Hermes`.

## Situação atual

O código do gate (módulo `functions/argos_autorizacao.py` + as 3 tools MCP + o fio no dispatcher do Telegram) já está mesclado — mas na branch `codex/secretario-telegram-tools` (commit `628822a`, via PR #181), não em `main`. Essa branch é trabalho de outra IA (Codex) e ainda não tem PR mesclado em `main`.

```
cd gestao-Hermes
git fetch origin
git merge-base --is-ancestor origin/codex/secretario-telegram-tools origin/main && echo "ja mesclado" || echo "ainda nao mesclado"
```

## Passo 1 — checar se a branch do Codex está pronta

```
gh pr list --repo andre-martiini/gestao-Hermes --head codex/secretario-telegram-tools --state all
```

- **Se existir um PR aberto, com os testes passando (CI verde) e sem sinal de trabalho ainda em andamento**: pode mesclar em `main` (merge commit, sem squash, sem rebase, sem force-push):
  ```
  gh pr merge <numero-do-PR> --repo andre-martiini/gestao-Hermes --merge
  ```
  Isso traz o gate de autorização junto automaticamente, porque já está mesclado dentro dessa branch.

- **Se não houver PR, se o CI estiver falhando, ou se houver qualquer sinal de que o Codex ainda está trabalhando nela ativamente**: NÃO mescle por conta própria. Isso não está autorizado neste pedido — é uma decisão do André sobre o trabalho de outra IA, não sobre o gate de autorização. Volte e avise, com o estado exato encontrado (existe PR? qual o número? CI verde ou vermelho? há commits mais recentes do que `af7ee16`?).

  Alternativa, só se o André pedir depois de ver esse aviso: trazer só o gate de autorização para `main` sem depender da branch do Codex, via cherry-pick dos dois commits do gate (`46c8743` e, se necessário, resolver conflitos manualmente) numa branch nova a partir de `main`, e abrir PR só com isso.

## Passo 2 — confirmar o deploy automático

Diferente do argos-gestor-sistemas (App Hosting, sem CI), o gestao-Hermes tem deploy automático via GitHub Actions (`.github/workflows/deploy.yml`), disparado a cada push em `main`, com um gate de testes antes do deploy. Depois que o merge do Passo 1 acontecer:

```
gh run list --repo andre-martiini/gestao-Hermes --workflow=deploy.yml --limit 3
```

Confirme que o run mais recente (o disparado pelo merge) terminou com sucesso. Se falhar, não tente corrigir por conta própria — reporte o log do passo que falhou.

## Depois disso

Com o deploy do Hermes confirmado, as 4 frentes do conector Claude-Argos estarão de ponta a ponta em produção. Ainda falta o primeiro teste real do fluxo completo (autorizar pelo Telegram → aprovar plano/enfileirar execução no Argos) — isso fica para o André e o Claude testarem juntos depois, não faz parte deste ajuste.
