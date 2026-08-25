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
Não há como esticar isso com ID Token do Firebase.

O caminho OAuth (abaixo) não tem esse limite — ele renova sozinho pelo refresh
token. O Claude Code também fala OAuth: para usá-lo em vez do `headersHelper`,
adicione o servidor sem `headersHelper` e ele negocia o fluxo por conta própria,
abrindo o consentimento no navegador.

### Diagnóstico rápido

```bash
curl -s https://gestao-hermes.web.app/mcp/health
```

Health-check sem autenticação: responde nome, versão e versão do protocolo. Se ele
responde e a conexão mesmo assim falha, o problema é token ou allowlist —
`-32001` é token inválido/expirado, `-32002` é uid fora da allowlist.

Para conferir a cadeia de discovery do OAuth:

```bash
curl -si https://gestao-hermes.web.app/mcp | head -3
```

Tem que ser `401` com `www-authenticate`. Um `200` aqui significa que o desafio de
autenticação está escondido e nenhum cliente OAuth vai conseguir conectar.

## Claude Cowork e outras superfícies hospedadas

As superfícies hospedadas (Claude.ai, Desktop, mobile, Cowork) não têm
`headersHelper` — elas autenticam por OAuth. `functions/mcp_oauth.py` implementa
o authorization server: OAuth 2.0 com Dynamic Client Registration e PKCE S256.

**Para conectar:** em *Customize → Connectors → Add custom connector*, informe a
URL exatamente assim:

```
https://gestao-hermes.web.app/mcp
```

Não preencha Client ID nem Client Secret — o DCR registra o cliente sozinho. O
Claude abre a página de consentimento, você entra com a mesma conta Google do
Hermes, e pronto. Contas fora de `system/mcp_access.allowed_uids` são recusadas
com `access_denied`.

> A URL precisa bater **exatamente** com o campo `resource` do protected resource
> metadata, incluindo o path. Uma barra a mais no fim já quebra a validação.

### Por que a URL do OAuth não é a da Cloud Function

Esta foi a lição cara. A primeira versão manteve o MCP em
`cloudfunctions.net/mcpServer` e pôs só o OAuth no Hosting, apontando o
`resource_metadata` do `401` para lá — o que a especificação permite.

**Não funcionou.** A tentativa de conectar pelo Cowork falhou no registro e os
logs mostraram o motivo: *nenhuma requisição chegou ao servidor*. O cliente
procura o discovery **antes** de receber o `401` que traria o ponteiro, e na
origem `cloudfunctions.net` todo caminho `/.well-known/*` devolve 404 do Google
Frontend — o primeiro segmento do path é o nome da função, então ele procura uma
função chamada `.well-known` e nunca invoca código nosso. Nem aparece nos logs.

Agora MCP e OAuth atendem na **mesma origem** (`gestao-hermes.web.app`), que é a
recomendação explícita da documentação de conectores. Todo caminho de sondagem do
RFC 9728 resolve, com ou sem o ponteiro.

A URL direta da função continua valendo, e é o que o Claude Code usa com
`headersHelper`: um rewrite do Hosting corta em **60s**, contra 300s da função
direta, e tools como `gerar_relatorio` e `ler_documento_na_integra` passam disso.
Ambas as URLs são aceitas como audiência do token.

O `401` — em `GET` e em `POST` — sempre responde:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer resource_metadata="https://gestao-hermes.web.app/.well-known/oauth-protected-resource"
```

Esse header é obrigatório: o Claude **ignora** `WWW-Authenticate` numa resposta
`200`. Por isso o `GET` na raiz também devolve `401` — antes ele respondia `200`
com o health-check em qualquer path, o que escondia o desafio de autenticação. O
health-check mudou para `/mcp/health`.

### Rotas e armazenamento

| Rota (no Hosting) | Papel |
|---|---|
| `/.well-known/oauth-protected-resource` | RFC 9728 — diz onde fica o AS |
| `/.well-known/oauth-authorization-server` | RFC 8414 — endpoints e `code_challenge_methods_supported: ["S256"]` |
| `/oauth/register` | DCR (RFC 7591), corpo em JSON |
| `/oauth/authorize` | GET serve a página de consentimento; POST recebe o ID token do login e devolve o `code` |
| `/oauth/token` | `authorization_code` e `refresh_token`, corpo form-urlencoded |

Coleções: `mcp_oauth_clients` (registros do DCR), `mcp_oauth_codes` e
`mcp_oauth_refresh` (ambos guardados **só como hash SHA-256** — quem ler o banco
não reconstrói um token utilizável). O segredo de assinatura fica em
`system/mcp_oauth.signing_secret`, gerado na primeira execução; `system/**` é
negado a todo mundo nas firestore.rules, só o Admin SDK alcança.

### Decisões que valem registrar

**O access token é próprio, não um Firebase ID token repassado.** É um JWT HS256
com `aud` fixado no recurso MCP e validade de 1h. Repassar o par de tokens do
Firebase seria mais simples, mas entregaria ao cliente a identidade inteira do
usuário, com refresh de longa duração e sem escopo. O token próprio é limitado a
este recurso e revogável isoladamente.

**Refresh token rotaciona a cada uso.** O DCR registra o Claude como cliente
público, e a especificação de autorização do MCP adota a exigência do OAuth 2.1
de rotacionar nesse caso. O antigo é apagado no mesmo request que emite o novo.

**Erros seguem o RFC 6749 à risca.** `invalid_grant` para refresh token morto —
um código custom faz o Claude falhar em silêncio em vez de reautenticar.

**Redirect URI compara exato, exceto loopback.** O Claude Code é cliente nativo e
usa `http://localhost:<porta efêmera>/callback` (RFC 8252), então a porta é
ignorada para `localhost` e `127.0.0.1`. As superfícies hospedadas usam sempre
`https://claude.ai/api/mcp/auth_callback`, que casa exatamente.

**A config do app web vem do Firestore.** A página de consentimento precisa dela
para o login com Google, e lê `public_configs/firebase_web` em vez de trazer a
config escrita no backend — que criaria mais uma cópia do padrão `AIza...` num
repositório público. `scripts/seed_mcp_oauth_config.py` copia de `firebase.ts`,
que continua sendo a fonte única.

### Os dois canais convivem

`mcpServer` aceita as duas credenciais, nesta ordem: access token OAuth (validado
localmente por HMAC, sem I/O) e, se não for um, Firebase ID Token. O Claude Code
com `headersHelper` continua funcionando exatamente como antes.

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
| `functions/mcp_oauth.py` | Cloud Function `mcpOAuth`: authorization server OAuth 2.1 (DCR, PKCE S256, discovery) |
| `functions/test_mcp_oauth.py` | Contrato do discovery, PKCE, redirect URIs, tokens e o desafio `401` |
| `scripts/seed_mcp_oauth_config.py` | Copia a config do app web de `firebase.ts` para `public_configs/firebase_web` |
| `functions/tools/hermes_tools.py` | Executor do catálogo fora do copiloto web |
| `functions/tools/tool_context.py` | `ToolContext` — estado que as tools precisam, com construção preguiçosa |
| `functions/tools/callable_bridge.py` | Invoca callables `@https_fn.on_call` de dentro do backend |
| `functions/tools/registry.py` | Catálogo, schemas, gating de confirmação, habilitação MCP/voz |
| `functions/copilot_context.py` | Monta o resource `hermes://voice-context` |
| `functions/test_hermes_tools.py` | Contrato catálogo ↔ schema ↔ executor + camada JSON-RPC |
| `scripts/hermes_mcp_headers.py` | Gera o header de autenticação para o `headersHelper` |
