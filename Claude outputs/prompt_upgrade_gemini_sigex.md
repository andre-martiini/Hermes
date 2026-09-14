# Prompt — push + PR: atualizar modelo Gemini Flash de 3.7 para 3.8 (gestao-sigex)

Contexto: mudança aprovada no plano da demanda DEV-2026-0002 (Argos DevFlow). Outra IA (Claude, via ponte com o computador do André) já aplicou a mudança e commitou localmente. Sua tarefa é só dar push da branch nova e abrir o PR. Não revise nem reescreva o código — mudança de 2 linhas, revisada manualmente antes do commit; `tsc --noEmit` na raiz do projeto não aponta nenhum erro novo (os 2 erros pré-existentes que aparecem são em `functions/src/index.ts`, módulos do Cloud Functions não instalados nesse ambiente, sem relação com esta mudança). Não existe suíte de testes automatizados neste repositório. O revisor do PR é o próprio André (ou o Claude, a critério dele) — não aprove nem faça merge.

Repositório: `andre-martiini/gestao-sigex` (remote `origin`). Pasta local: `sigex-gestao`.

Branch: `claude/upgrade-gemini-flash-3.8` (commit `181f460`, criada a partir de `main` no commit `a0daf77`). Um único arquivo alterado: `lib/gemini.ts`.

Observação: o working tree local tem uma quantidade grande de arquivos com diffs de puro fim-de-linha (CRLF/LF, sem mudança de conteúdo) não relacionados a esta tarefa — não commitados, não staged, e não fazem parte deste commit/branch. Ignore-os.

```
cd sigex-gestao
git push -u origin claude/upgrade-gemini-flash-3.8
gh pr create --base main --head claude/upgrade-gemini-flash-3.8 \
  --title "feat(gemini): atualizar modelo Flash de gemini-3.7-flash para gemini-3.8-flash" \
  --body "Atualiza MODELOS_GEMINI (entrada Flash) de gemini-3.7-flash para gemini-3.8-flash e adiciona gemini-3.7-flash a MODELOS_LEGADOS, mapeando para gemini-3.8-flash, para que configurações gravadas antes da atualização continuem funcionando. Mudança correspondente ao plano aprovado da demanda DEV-2026-0002 (Argos DevFlow). tsc --noEmit na raiz sem novos erros; sem suíte de testes automatizados neste repositório."
```

Se `gh` não estiver disponível/autenticado, abra o PR pela interface web do GitHub com o mesmo título e corpo.

## Depois de mesclar

Este repositório usa Firebase Hosting (não App Hosting como o argos-gestor-sistemas) — não há `.github/workflows` nem `apphosting.yaml`. Não sei ainda qual é o processo de deploy real (`firebase deploy` manual, alguma automação externa, etc.) — isso precisa ser confirmado com o André antes de considerar a mudança em produção. Depois do merge, avise que o PR foi mesclado e pergunte a ele como o deploy deste repositório normalmente acontece.
