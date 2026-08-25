---
type: reference
title: Servidor MCP do Hermes
description: Como o catálogo de tools do Hermes é exposto por MCP, o que está disponível, o modelo de segurança e como conectar um cliente (Claude Code, cliente de voz).
resource: functions/mcp_server.py
tags: [hermes, okf, copiloto, mcp, tools, integracao]
timestamp: 2026-08-25T00:00:00-03:00
---

# Servidor MCP do Hermes

O Hermes expõe seu catálogo de tools por [MCP](https://modelcontextprotocol.io),
para que clientes externos — Claude Code, o cliente de voz local, futuras
automações — operem o sistema com as **mesmas** ferramentas do copiloto web, em
vez de cada canal reimplementar as suas.

> **Princípio:** um cérebro, um catálogo, N canais. O servidor MCP não é um
> orquestrador novo; é a porta de entrada para o catálogo que já existe.

## O que está exposto

**53 tools**, todo o catálogo de `functions/tools/registry.py` que tem executor e
schema. `tools/list` publica exatamente o que é chamável — uma tool sem handler
ou sem schema simplesmente não aparece, em vez de falhar na chamada.

Cobre: busca de ações e acervo, agenda, criação e edição de ações (individual e
em lote), diário de bordo, memória global e POPs, contatos, finanças, saúde,
dados cadastrais, portais públicos, WhatsApp, e-mail, SIPAC, objetivos
estratégicos, relatórios e geração de imagem.

Um resource também é publicado: `hermes://voice-context`, com persona, perfil do
usuário e memórias recentes — para um cliente externo compor seu system prompt
com o mesmo contexto que o copiloto web usa.

### O par preparar/confirmar

As tools `preparar_*` **não gravam nada**: montam uma proposta que a UI do Hermes
renderiza como card de confirmação. Quem grava é a callable correspondente,
acionada quando o usuário clica em confirmar.

Um cliente MCP não tem esse card. Por isso as contrapartes de gravação também são
tools: `confirmar_edicao_acao`, `confirmar_edicao_em_lote` e
`confirmar_reagendamento_em_lote`. O fluxo correto por MCP é sempre em dois
passos — preparar, mostrar ao usuário, confirmar. Sem isso a proposta preparada
morre no ar.

## Modelo de segurança

Três camadas, todas obrigatórias:

1. **Firebase ID Token** no header `Authorization: Bearer <token>`, verificado
   server-side com o Admin SDK.
2. **Allowlist de UID** em `system/mcp_access.allowed_uids` (ou na env var
   `HERMES_MCP_ALLOWED_UIDS`). Sem uid configurado em nenhum dos dois, **o acesso
   é negado** — o padrão é fail closed.
3. **Gating de confirmação**, hoje aplicado a **uma** tool:
   `schedule_whatsapp_message`. Ela recusa a primeira chamada e devolve
   `status: confirmation_required`; só executa quando a chamada é repetida com
   `arguments._confirmed = true`.

Além disso: rate limit de 60 chamadas/minuto por UID e log de auditoria de toda
chamada em `mcp_audit_log` (uid, tool, argumentos, latência).

### Por que só o WhatsApp

Decisão do dono do sistema em 2026-08-25: as demais tools que gravam rodam sem a
dupla ida e volta, porque o cliente MCP já pede permissão por chamada — exigir
`_confirmed` em tudo adicionaria atrito sem adicionar um humano ao circuito. O
envio de WhatsApp ficou de fora por ser o único efeito que **manda mensagem em
nome do usuário para terceiros** e não dá para desfazer de dentro do Hermes.

O `_meta` de cada tool em `tools/list` distingue as duas coisas:

- `needsConfirmation` — se **este canal** exige a dupla chamada
- `mutates` — se a tool grava (vem de `registry._NEEDS_CONFIRMATION`), independente
  do gating; um cliente pode querer pedir aprovação mesmo onde o servidor não exige

`registry._NEEDS_CONFIRMATION` continua valendo integralmente para o copiloto web e
para o motor de simulação — a mudança é só de canal.

**Para reapertar sem deploy:** grave a lista desejada em
`system/mcp_access.confirm_tools`. Ela sobrepõe o padrão do código, inclusive para
voltar a exigir confirmação em tudo:

```
system/mcp_access
  allowed_uids: ["<uid>"]
  confirm_tools: ["schedule_whatsapp_message", "registrar_item_financeiro_v2", ...]
```

Sem o campo, vale o padrão de `mcp_server._CONFIRMACAO_PADRAO`.

## Conectar o Claude Code

O servidor autentica com ID Token, que vale 1 hora. Em vez de colar um token que
expira no meio do dia, use o `headersHelper` — o Claude Code roda o script na hora
de conectar:

```bash
claude mcp add-json hermes '{"type":"http","url":"https://us-central1-gestao-hermes.cloudfunctions.net/mcpServer","headersHelper":"python C:/Users/T-GAMER/Documents/gestao-Hermes/scripts/hermes_mcp_headers.py"}'
```

O script (`scripts/hermes_mcp_headers.py`) assina um custom token com a chave de
service account local, troca por um ID token no Firebase Auth e imprime o header.
O token **não é gravado em disco** — é gerado, impresso e esquecido.

Verificar a conexão:

```bash
claude mcp get hermes
```

**Limite conhecido:** o ID token vale 1 hora. Numa sessão mais longa que isso as
chamadas passam a falhar com `-32001` até o servidor ser reconectado no cliente.
Não há como esticar isso com ID Token do Firebase; a saída definitiva é o servidor
aceitar OAuth (ver "Cowork" abaixo).

### Diagnóstico rápido

```bash
curl -s https://us-central1-gestao-hermes.cloudfunctions.net/mcpServer
```

O `GET` é um health-check sem autenticação e responde nome, versão e versão do
protocolo. Se ele responde e a conexão mesmo assim falha, o problema é token ou
allowlist — `-32001` é token inválido/expirado, `-32002` é uid fora da allowlist.

## Claude Cowork e outras superfícies hospedadas

As superfícies hospedadas (Claude.ai, Desktop, mobile, Cowork) **não aceitam** um
header montado localmente: não há `headersHelper` lá. Elas suportam `oauth_dcr`,
`oauth_cimd`, `oauth_anthropic_creds`, `static_headers` (beta, entrado por admin
de organização) ou `none`.

Ou seja, para expor o Hermes ao Cowork falta uma camada OAuth 2.1 no servidor:
metadata RFC 9728, resposta `401` com `WWW-Authenticate: Bearer resource_metadata=...`,
PKCE S256, e `/register` (DCR) ou CIMD. É o item mais caro da lista e não bloqueia
o uso pelo Claude Code. Atalho viável quando for a hora: pôr um IdP que já faz DCR
(Auth0, Stytch, WorkOS) na frente da função, em vez de escrever o authorization
server à mão.

## Como as tools chegam ao MCP

`functions/tools/hermes_tools.py` é o executor: cada handler recebe um
`ToolContext` explícito (`db`, `user_uid`, `session_id`, `task_id`) em vez de
capturar o escopo de um request. A regra é sempre reusar, nunca reescrever:

| Origem | Tools | Duplicação |
|---|---|---|
| Delegação a `tools/telegram_extended.py` | 20 | nenhuma |
| Delegação a módulos dedicados (`strategy_tools`, `health_tools`, `busca_grafo`, ...) | 16 | nenhuma |
| Delegação a callables existentes via `tools/callable_bridge.py` | 3 | nenhuma |
| Lógica extraída das closures de `askCopilotoHermes` | 14 | nenhuma — as closures passaram a delegar (ver abaixo) |

### Adicionar uma tool nova

Três coisas, sempre juntas — o teste `test_hermes_tools.py` falha se faltar alguma:

1. handler em `tools/hermes_tools.py::_HANDLERS`
2. entrada em `tools/registry.py::_CATALOG`
3. schema em `tools/schemas/<nome>.json`

Se a tool grava algo, adicione também em `registry._NEEDS_CONFIRMATION`.

## Convergência do `main.py` — não há duplicação

As tools do copiloto web viviam como *closures* dentro de `askCopilotoHermes`
(`functions/main.py`), presas ao escopo do request. **21 delas foram convergidas**:
o corpo virou uma chamada a `hermes_tools`, removendo 837 linhas de lógica que
existiriam em duas cópias. Não há um segundo catálogo — há um executor e dois
canais chamando ele.

O que ficou preservado byte a byte: **assinatura e docstring** de cada closure. O
SDK do Gemini gera a declaração da função a partir delas, então alterá-las mudaria
o schema que o modelo vê. Um teste de AST comparou as 56 closures antes e depois e
confirmou zero diferença nesses dois campos.

Um helper `_ctx()` dentro de `askCopilotoHermes` monta o `ToolContext` a cada
chamada — e não uma vez — porque `session_id` e `task_id_scoped` são reatribuídos
ao longo da requisição e uma instância única congelaria valores obsoletos.

Duas tools recebem argumento extra no canal web, e por isso os handlers os aceitam:

- `pesquisar_internet(ctx, args, prompt_gate=prompt)` — o copiloto web só permite
  a busca se o prompt do usuário mencionar internet/URL; canais onde a escolha da
  tool já é explícita passam `None` e o portão fica desligado.
- `criar_acao_no_sistema(ctx, args, areas_validas=..., artefatos_pendentes_vinculo=...)`
  — o web app já tem ambos carregados no request; o MCP recarrega as áreas do
  Firestore e não tem anexos pendentes.

**Duas closures ficaram de fora, deliberadamente:** `consultar_historico_acoes` e
`buscar_arquivos_acervo`. Elas não são wrappers — formatam a saída como um bloco de
texto com instruções anti-alucinação ("use EXCLUSIVAMENTE os campos abaixo, não use
RAG") dirigidas ao Gemini. O executor MCP devolve estrutura, que é o que um cliente
MCP quer. A lógica de busca em si (`tools/busca_grafo`, `tools/busca_acervo`) já é
compartilhada; só a apresentação difere, e é assim que deve ser.

## Arquivos

| Arquivo | Papel |
|---|---|
| `functions/mcp_server.py` | Cloud Function `mcpServer`: JSON-RPC, auth, allowlist, rate limit, auditoria |
| `functions/tools/hermes_tools.py` | Executor do catálogo fora do copiloto web |
| `functions/tools/tool_context.py` | `ToolContext` — estado que as tools precisam, com construção preguiçosa |
| `functions/tools/callable_bridge.py` | Invoca callables `@https_fn.on_call` de dentro do backend |
| `functions/tools/registry.py` | Catálogo, schemas, gating de confirmação, habilitação MCP/voz |
| `functions/copilot_context.py` | Monta o resource `hermes://voice-context` |
| `functions/test_hermes_tools.py` | Contrato catálogo ↔ schema ↔ executor + camada JSON-RPC |
| `scripts/hermes_mcp_headers.py` | Gera o header de autenticação para o `headersHelper` |
