# Handoff — sessão Claude Code (web, remota) → sessão local, 17/09/2026

Continuação da ação Hermes **"Custos Hermes — PR 3: Cortes Guiados Pelos Dados"** (id `b066fbd2-8552-4321-b`) e da avaliação do Jev (TypeSafe) para o Hermes. O diário e o plano de ação dessa tarefa no Hermes são a fonte de verdade — este arquivo é só um resumo pra retomar rápido numa sessão local.

Handoff anterior (entrada desta sessão): `Claude outputs/prompt_jev_typesafe_integracao.md` (sessão Cowork, 17/09).

## O que esta sessão fez

**Dívida técnica secundária (resolvida):**
1. PR #279 (memória de `check_and_send_reminders`, 1GB→256MB): já estava aberta e **mesclada** pelo André antes desta sessão começar — nada a fazer.
2. PR #280 aberta: https://github.com/andre-martiini/Hermes/pull/280 (dedupe da leitura de `tarefas` + cadência 30→60min). A branch original `claude/pr3-dedupe-sync-cadencia` tinha 16 commits de outras sessões misturados (reuniões, dashboard, P03 sub-entregas) — isolei o commit certo (`c044cbf`) via `git cherry-pick` sobre o `main` atual, numa branch nova (`claude/pr3-dedupe-sync-cadencia-v2`), sem tocar a branch original. 84/84 testes reconferidos (`test_atencao`, `test_atencao_whatsapp`, `test_sync`). **Aguardando revisão/merge do André.**

**Avaliação do Jev (TypeSafe) — só pesquisa, nada implementado:**

Reverifiquei a documentação oficial na fonte (docs.typesafe.ai) e reconferi os 5 candidatos de integração contra o código real do Hermes. Achados relevantes:

- Import correto do SDK Python: `from typesafe_sdk import Choice, Noul, Score, TypeSafeClient` (não `typesafe_sdk.questions`, como o material anterior supunha). Também existe `AsyncTypeSafeClient`.
- Rate limits: 250.000 tokens/s e 1.200 req/min por conta (podem mudar sem aviso). Contexto: 64k tokens total (state+questions), 32k para state + maior pergunta.
- **Risco de conteúdo adversarial:** a doc oficial ("jev-1.13 jaggedness") avisa que o `state` não é tratado como hostil por padrão — texto adversarial pode manipular a resposta. Importa mais pro candidato 3 (guardrail) e pros que classificam texto de terceiro direto (1 e 2). Outras jaggedness: leitura literal (escrever o critério exato, não a intenção implícita), datas não são comparadas de forma confiável em código do modelo, contagem/matemática não são o forte do Jev.
- **Correção 1:** `outbox_aprovacao.py::criar_rascunho` tem **3 caminhos**, não 1 — `envio_imediato=True` sai sem aprovação nenhuma hoje (é o mais exposto dos três, não só o caminho de "tipo promovido" como o material anterior sugeria).
- **Correção 2 (importante):** `contact_merge_utils.py` **já tem** um detector de duplicatas — `find_and_notify_duplicate_contacts(db)`, chamado por job proativo em `main.py:3794`, compara por telefone/e-mail/heurística crua de nome. A proposta do candidato 5 não é uma feature nova, é upgrade de um detector heurístico existente (troca a heurística por um `Score` de 3 níveis do Jev, padrão do cookbook `entity_alignment.md`).
- Candidatos 1, 2 e 4 batem com o resumo da sessão anterior sem imprecisão relevante.

**Recomendação dada:** candidato 1 (`inbox_pendentes.py`, classificador de rótulo fechado) continua sendo o melhor primeiro passo — rótulos fechados e já auditados, infraestrutura de cache/orçamento já existe, blast radius baixo mesmo se o Jev errar ou receber conteúdo adversarial (não dispara ação autônoma, só um rótulo de triagem). Segunda opção, se o André preferir algo com impacto de custo mais visível: candidato 3 (guardrail no outbox), priorizando o caminho `envio_imediato` que hoje não tem rede de segurança nenhuma.

**Bloqueio conhecido:** `TYPESAFE_API_KEY` ainda não foi gerada. André vai gerar em console.typesafe.ai e guardar num arquivo `.env` local (raiz do repo ou `functions/.env` — já cobertos pelo `.gitignore`, linha 27). **Não colar a chave em nenhum arquivo `.md` de `Claude outputs/` ou `docs/`** — esses arquivos são versionados e vão para commits normalmente.

## Pendências para a sessão local

- [ ] Revisar e mesclar a PR #280 (ou pedir ajuste, se algo não bater)
- [ ] Avaliar separadamente os 16 commits não relacionados que sobraram na branch `claude/pr3-dedupe-sync-cadencia` original (reuniões, dashboard, P03 sub-entregas 18/19) — podem precisar de PRs próprias, não tratado nesta sessão
- [ ] Decidir com o André qual candidato do Jev priorizar (1, 3, ou outro)
- [ ] Depois de gerar a `TYPESAFE_API_KEY`: prototipar localmente (script solto, sem tocar produção) comparando Jev vs. Gemini nas mensagens reais/sintéticas do candidato escolhido
- [ ] Só depois disso, abrir PR de verdade com testes

## Como sincronizar o repositório local

```bash
git fetch origin
git checkout main && git pull origin main                    # traz a PR #279 já mesclada
git fetch origin claude/pr3-dedupe-sync-cadencia-v2           # branch da PR #280, se quiser revisar localmente
git checkout claude/processar-prompt-anexo-txe3tn 2>/dev/null || git checkout -b claude/processar-prompt-anexo-txe3tn origin/claude/processar-prompt-anexo-txe3tn
git pull origin claude/processar-prompt-anexo-txe3tn         # traz este handoff (docs/handoff-sessao-claudecode-2026-09-17.md)
```

Ref: ação Hermes `b066fbd2-8552-4321-b` (Custos Hermes — PR 3). Diário e plano de ação da tarefa têm o detalhe completo de cada achado, linha a linha do código.
