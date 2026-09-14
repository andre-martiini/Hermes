# Prompt — push: correções sobre a revisão do Codex na PR #10 (argos-gestor-sistemas)

Contexto: a PR #10 (`claude/conector-escrita-repositorio` → `main`, andre-martiini/argos-gestor-sistemas) recebeu 2 comentários do Codex. Ambos procedentes — já corrigidos e commitados localmente, com uma rodada de revisão adversarial por sub-agente (que encontrou e corrigiu uma falha na primeira tentativa da correção #1, ver abaixo). Só falta dar push do commit novo — a PR já existe e é atualizada automaticamente, sem precisar abrir PR nova.

Não revise nem reescreva o código. `tsc --noEmit` limpo; `claude-connector.test.ts` 69/69 (66 anteriores + 3 novos); `devflow.test.ts` 9/9; `github-webhook.test.ts` 1/1; `devflow-worker.test.ts` 4/4 — sem regressão. Revisor humano é o André, manualmente — não aprove nem faça merge.

Repositório: `andre-martiini/argos-gestor-sistemas` (remote `origin`). Pasta local: `argos-gestor-sistemas-main`.

Branch: `claude/conector-escrita-repositorio`, agora com 1 commit novo em cima do `22891f6` já publicado na PR #10: `9536c0d` — "fix(claude): endereça revisão do Codex no PR #10 (branch protegido real + content omitido)".

Resumo do que o commit novo corrige:
1. `writeRepoFile` só recusava escrita direta em `'main'` fixo — repositórios cujo branch padrão real fosse `master`/`develop`/etc. ficavam sem proteção. Agora consulta o `default_branch` real via GitHub API e recusa escrita nele; falha FECHADA (502) se não conseguir confirmar (a primeira tentativa dessa correção caía de volta para `'main'` em caso de erro de rede, o que reabria o mesmo buraco — a revisão adversarial encontrou isso antes deste commit).
2. A rota REST `PUT /systems/:id/repo/file` convertia `content` omitido/nulo em string vazia antes da validação, deixando passar como válida uma requisição malformada sem o campo `content` (arquivo ficaria vazio). Agora passa o valor bruto adiante; a validação existente do core rejeita com 400, mantendo `content: ''` explícito como válido.

```
cd argos-gestor-sistemas-main
git push origin claude/conector-escrita-repositorio
```

Se pedir força ou mostrar não-fast-forward, pare e avise — não é esperado (o commit novo é só um cima do que já está publicado). Não precisa `gh pr create`: a PR #10 já existe e mostra o commit novo automaticamente após o push.

## Depois do push

Nada além do já combinado na PR #10: revisão manual do André, merge manual, lançamento manual no Firebase App Hosting. O escopo do `GITHUB_PAT` já foi ajustado pelo André.
