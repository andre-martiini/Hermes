# Prompt — push do commit de correção no PR #9 já aberto (argos-gestor-sistemas)

Contexto: o PR #9 (`claude/marcar-pronto-para-execucao` → `main`) já está aberto. A revisão automática do Codex nele apontou um bug real: `advanceToReadyForExecution` trocava o label no GitHub para "pronto para execução" ANTES de confirmar a escrita no Firestore pela transação (CAS). Se outra chamada mudasse o estado da demanda nesse intervalo (por exemplo, bloqueando a demanda) e a CAS falhasse, o label já estaria errado — e o webhook do GitHub poderia sincronizar esse label de volta, desfazendo silenciosamente a decisão concorrente. Outra IA (Claude, via ponte com o computador do André) já corrigiu isso — o label só é sincronizado depois que a transação confirma sucesso — e já commitou localmente. Sua tarefa é só dar push do commit novo (a branch já existe em `origin`, não precisa criar PR novo) e responder ao comentário do Codex explicando a correção. Não revise nem reescreva o código — já testado (`tsc --noEmit` limpo; `claude-connector.test.ts` 57/57, incluindo um novo assert de regressão para essa observação; `devflow.test.ts` 7/7; `github-webhook.test.ts` + `devflow-worker.test.ts` 5/5, sem regressão).

Repositório: `andre-martiini/argos-gestor-sistemas` (remote `origin`). Pasta local: `argos-gestor-sistemas-main`.

Branch: `claude/marcar-pronto-para-execucao`, agora com 2 commits à frente de `main`: `84b2059` (já estava no PR) + `a3b1b52` (novo, a correção).

```
cd argos-gestor-sistemas-main
git push origin claude/marcar-pronto-para-execucao
```

Isso atualiza o PR #9 automaticamente (sem precisar de `gh pr create` de novo).

## Responder ao comentário do Codex no PR #9

Comente no PR (`gh pr comment 9 --repo andre-martiini/argos-gestor-sistemas --body "..."` ou pela interface web) algo como:

> Obrigado pela revisão — a observação era real e foi corrigida no commit a3b1b52:
>
> A chamada a `replaceStatusLabel` foi movida para depois da transação com verificação de estado fresco (CAS). Antes, se a CAS falhasse (outra chamada mudou o estado da demanda nesse intervalo — por exemplo, bloqueando-a), o label no GitHub já teria sido trocado para "pronto para execução", e o webhook poderia sincronizar esse label de volta, desfazendo silenciosamente a decisão concorrente. Agora, se `applied` for `false`, a função lança 409 antes de tocar em qualquer label — nenhum efeito colateral externo acontece numa CAS que falha. Novo assert no teste de regressão confirma `spy.labels` vazio nesse caminho.

Se preferir, resolva a conversa ("Resolve conversation") depois de comentar.

## Depois disso

Nada muda no que já estava combinado: revisão manual do André pelo Antigravity antes de mesclar; depois do merge, criar o lançamento manual no Firebase App Hosting (sem CI/CD neste repositório); e o teste de ponta a ponta da DEV-2026-0002 (avançar para ready-for-execution e testar `argos_enfileirar_execucao`) fica para depois do deploy confirmado.
