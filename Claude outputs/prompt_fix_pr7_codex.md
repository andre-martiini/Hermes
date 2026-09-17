# Prompt — push do commit de correção no PR #7 já aberto (argos-gestor-sistemas)

Contexto: o PR #7 (`claude/plano-claude-first-argos` → `main`) já está aberto. A revisão automática do Codex nele apontou um furo lógico real no design original (a Issue e a aprovação do plano aconteciam na mesma chamada gated, então a autorização no Telegram tinha que citar um link que ainda não existia no momento de ser pedida). Outra IA (Claude, via ponte com o computador do André) já corrigiu isso — separou em dois passos — e já commitou localmente. Sua tarefa é só dar push do commit novo (a branch já existe em `origin`, não precisa criar PR novo) e responder aos dois comentários do Codex explicando a correção. Não revise nem reescreva o código — já testado (`tsc --noEmit` limpo; 51/51 testes, incluindo um novo teste de regressão para a segunda observação do Codex).

Repositório: `andre-martiini/argos-gestor-sistemas` (remote `origin`). Pasta local: `argos-gestor-sistemas-main`.

Branch: `claude/plano-claude-first-argos`, agora com 2 commits à frente de `main`: `30acb81` (já estava no PR) + `688172d` (novo, a correção).

```
cd argos-gestor-sistemas-main
git push origin claude/plano-claude-first-argos
```

Isso atualiza o PR #7 automaticamente (sem precisar de `gh pr create` de novo).

## Responder às duas observações do Codex no PR #7

Comente no PR (`gh pr comment 7 --repo andre-martiini/argos-gestor-sistemas --body "..."` ou pela interface web) algo como:

> Obrigado pela revisão — as duas observações eram reais e foram corrigidas no commit 688172d:
>
> 1. **Separar publicação de aprovação**: `proposeAndApprovePlan` foi substituída por duas operações: `proposePlan` (não-gated — publica a Issue, posta o plano, avança triage→planning, garante uma aprovação pendente) e `approvePlanDemand` (existente, inalterada — decide essa aprovação, gated por autorizacaoId). Agora existe um momento real em que a Issue com o plano publicado existe e a aprovação ainda está pendente, que é justamente o link citado no pedido de autorização no Telegram.
> 2. **Corrida na aprovação pendente**: corrigido em `approvePlanDemand` — se a transação verificar que a aprovação não está mais `pending` (decidida por outra chamada nesse intervalo), a função agora propaga 409 em vez de seguir emitindo `approval.approved` e devolvendo sucesso. Novo teste de regressão simula essa corrida.

Se preferir, resolva as duas conversas ("Resolve conversation") depois de comentar.

## Depois disso

Nada muda no que já estava combinado: revisão manual do André pelo Antigravity antes de mesclar; depois do merge, criar o lançamento manual no Firebase App Hosting (sem CI/CD neste repositório); e o primeiro teste real do fluxo em produção fica para depois.
