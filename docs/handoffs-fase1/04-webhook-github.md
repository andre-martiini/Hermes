# PR 4 (Fase 1) — `feat(github): webhook para diario da acao`

**Pré-requisito:** nenhum desta fase — pode ser feito a qualquer momento, em paralelo com o PR 5.

## Por quê

O Eixo 1 do plano (`docs/plano-evolucao-hermes-jarvis.md`, seção 3) lista "Evento de repositório" como um dos detectores que faltam: hoje, quando uma PR é mergeada num repo que o André administra (Atlas, MEC-Sustentavel, gestao-proen, o próprio Hermes), ninguém anota isso em lugar nenhum — só entra no diário da ação se ele lembrar de contar pro Claude depois. O critério de pronto da Fase 1 é direto: "um push/merge num repositório administrado por ele vira entrada no diário da ação certa" — sem ele precisar lembrar.

## Desenho — o mínimo que funciona

Só toca `functions/main.py` (nenhum módulo novo). Um receptor HTTP que verifica assinatura, decide se o evento importa, acha a(s) ação(ões) vinculada(s) ao repositório e anota no `acompanhamento` da tarefa — mesmo campo que `registrar_no_diario` já usa (`tarefas/{id}.acompanhamento`, `firestore.ArrayUnion([{data, nota}])`, ver `tools/hermes_tools.py:registrar_no_diario`).

### Vínculo repositório → ação (novo campo, mesmo padrão de `whatsapp_vinculos`)

`tarefas` ganha um campo `github_repos_vinculados: string[]` — lista de `"owner/repo"` (ex.: `"andre-martiini/Atlas"`) vinculados manualmente à ação, exatamente como `whatsapp_vinculos[]` já vincula contatos/grupos de WhatsApp (mesmo espírito de matching determinístico, documentado em `docs/okf/integracoes/whatsapp.md` §3 — não precisa copiar o mecanismo, só o princípio: campo simples, preenchido manualmente, sem tool nova pra isso). Preenchimento é manual por enquanto (editar a tarefa direto no Firestore ou via frontend, se o campo já for editável — não crie tool nova nem UI nesta PR). Documente no PR como preencher.

Uma tarefa pode ter zero, um ou vários repos vinculados; um repo pode estar vinculado a mais de uma tarefa (raro, mas não trate como erro — anote em todas). Repo sem nenhuma tarefa vinculada: ignore silenciosamente (`print` de log, sem erro).

### Segredo do webhook (mesmo padrão de `system/api_keys.telegram_bot_token`)

Novo campo `system/api_keys.github_webhook_secret` (fallback `os.environ.get("GITHUB_WEBHOOK_SECRET")`, mesmo padrão de `_get_telegram_token`/`_get_api_keys` em `hermes_core_logic.py`). Esse é o "secret" que você configura no GitHub ao criar o webhook em cada repositório (Settings → Webhooks → Secret). Documente no PR como preencher e como cadastrar o webhook no GitHub (Content type `application/json`, eventos `Pull requests` e `Pushes`, a URL da function).

**Falha fechada:** se o segredo não estiver configurado, a function recusa todo request (500, log claro) em vez de aceitar sem verificar — nunca processe payload não assinado.

### Verificação de assinatura

GitHub manda `X-Hub-Signature-256: sha256=<hexdigest>` calculado com HMAC-SHA256 sobre o **corpo bruto** da requisição (bytes, antes do parse JSON) usando o secret acima. Calcule com `hmac.new(segredo.encode(), corpo_bruto, hashlib.sha256).hexdigest()` e compare com `hmac.compare_digest` (nunca `==` — timing attack). Assinatura ausente ou inválida → `401`, não processa nada.

Trate `X-GitHub-Event: ping` (evento único que o GitHub manda ao cadastrar o webhook) devolvendo `200` direto, sem mais lógica — senão o cadastro do webhook aparece como falho no GitHub.

### Deduplicação (reaproveita `core/idempotency.py`, já existe)

GitHub reenvia a entrega se não receber `200` a tempo, e o dono pode reenviar manualmente pela UI do GitHub. Use `core.idempotency.check_and_register(db, delivery_id)` com `delivery_id = req.headers.get("X-GitHub-Delivery")` **logo após validar a assinatura** — se vier `False` (já processado), devolva `200` sem anotar de novo no diário.

### Quais eventos viram entrada no diário

Só dois, deliberadamente pouco por enquanto:

- **`pull_request`** com `action == "closed"` e `pull_request.merged == True` → nota: algo como `[GitHub] PR #{number} mergeada em {repo}: "{title}" — {html_url}`.
- **`push`** para o branch default do repo (`ref == f"refs/heads/{repository.default_branch}"`) com pelo menos 1 commit → nota: algo como `[GitHub] Push em {repo} ({branch}), {N} commit(s) — último: "{head_commit.message, só a primeira linha}" — {compare url}`.

Qualquer outro `X-GitHub-Event` (issues, comentários, etc.) ou `pull_request`/`push` que não bata nos critérios acima: ignora, devolve `200`, não anota nada. Separe isso numa função pura (`tipo evento + payload -> dict normalizado | None`) pra poder testar sem Firestore nem request HTTP de verdade.

### A Cloud Function

Mesmo padrão de `telegramWebhook` (`hermes_core_logic.py`): `@https_fn.on_request`, sempre responde rápido, nunca deixa exceção não tratada estourar sem resposta. Passos: valida assinatura → trata `ping` → dedupe por `X-GitHub-Delivery` → normaliza o evento (função pura) → se `None`, `200` e acabou → busca tarefas com `github_repos_vinculados` contendo o repo (`array_contains`) → para cada uma, `ArrayUnion` no `acompanhamento` → `200`.

## Travas

- Nunca envie nada a terceiro a partir daqui — é só anotação no diário da própria ação. "Sugerir o próximo passo" (mencionado no plano) fica fora desta PR — ver Fora de escopo.
- Não crie um novo tipo de envelope estruturado pro frontend (`REPO::JSON::{...}`, ver `src/utils/diaryEntries.ts`) — isso mexeria em frontend, fora do escopo declarado desta PR (só `functions/main.py`). A nota entra como texto livre mesmo, com a URL da PR/commit dentro do próprio texto.
- Falha ao anotar em uma tarefa vinculada não pode derrubar as outras (repo vinculado a 2+ tarefas) — isole por tarefa (`try/except` por iteração), como os detectores de `atencao_whatsapp.py` já fazem entre si.

## Testes

- Funções puras testáveis sem Firestore: verificação de assinatura (HMAC batendo e não batendo), normalização de evento (PR mergeada casa, PR fechada sem merge não casa, push no default branch casa, push em outro branch não casa, push sem commits não casa, evento de tipo desconhecido não casa).
- Teste leve do fluxo completo com Firestore fake: repo vinculado a 1 tarefa → aparece no `acompanhamento`; repo vinculado a 0 tarefas → não quebra; `X-GitHub-Delivery` repetido → não duplica a entrada; assinatura inválida → `401` e nada é gravado.

Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Fora de escopo

- "Sugerir o próximo passo" (ex.: rascunho de mensagem tipo "avisar a Iris?") fica de fora — isso teria que passar por outbox/aprovação (Eixo 3) e por uma decisão de quem avisar, que este PR não tem como inferir do payload do GitHub. Se isso vier depois, é PR à parte.
- UI ou tool para editar `github_repos_vinculados` — o campo é preenchido manualmente por enquanto.
- Suporte a outros eventos do GitHub (issues, releases, deploys via Actions) — só `pull_request` (merge) e `push` (default branch) nesta PR.

## Docs

`docs/okf/arquitetura/schema-firestore.md` (novo campo `tarefas.github_repos_vinculados[]` e `system/api_keys.github_webhook_secret`), `docs/okf/copiloto/mcp-servidor.md` só se fizer sentido citar o webhook lá (não é tool MCP, então pode ser só uma nota), `docs/okf/log.md`. Inclua no PR o passo a passo de configuração do webhook no GitHub (secret, eventos, content-type) — sem isso ninguém mais além de você sabe como ligar.
