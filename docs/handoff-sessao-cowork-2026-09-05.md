# Handoff — Sessão Cowork (André ↔ Claude ↔ Dev), 05/09/2026

Este arquivo existe pra uma sessão nova do Claude (Cowork) retomar exatamente de onde esta parou. Abra com acesso à pasta `gestao-Hermes` e peça para o Claude ler este arquivo + `docs/dev-sync.md`.

## Papel do Claude neste fluxo

- Claude atua como arquiteto/revisor do Hermes (assistente pessoal do André). O código é escrito por um agente de desenvolvimento separado ("Antigravity"/dev), não pelo Claude.
- A coordenação entre Claude e dev é 100% assíncrona, via `docs/dev-sync.md` no repo (branch `main`). Protocolo: cada lado só escreve na própria seção (`## Mensagens do Claude` / `## Mensagens do Dev`), mensagem mais recente sempre no topo, histórico nunca é apagado. O bloco `## Estado atual` no topo do arquivo diz de quem é a vez (`aguardando: claude` ou `dev`).
- Cadência combinada: dev confere o arquivo a cada ~5 min enquanto `aguardando: claude`; Claude confere a cada ~20-30 min enquanto `aguardando: dev` (já automatizado — ver "Tarefas agendadas" abaixo).
- **Regra de ouro, seguida à risca a sessão inteira:** nunca aceitar o relato do dev de olhos fechados. Sempre abrir os arquivos citados, contar testes um a um, checar `git log`/`HEAD`/`packed-refs`, e só then aprovar ou reportar ao André. Essa desconfiança saudável já pegou pelo menos uma discrepância de contagem de testes ao longo da sessão.

## Onde as coisas estão agora

**PR #171 — Modo Secretário no WhatsApp (MVP) — mergeado na `main`**, commit `aa8244322e6083332bdaca2f0931a24169ec873d`. Verificado linha a linha (não só no relato do dev): toggle + allowlist em `system/settings.whatsapp_secretario`, assinatura obrigatória `**Hermes Bot:**`, assimetria de agenda (ocupado informa factualmente / livre nunca confirma), teto de 2 trocas com escalonamento pra fila `atencao`, proteção de dados financeiro/saúde (sempre escalado, nunca respondido pelo bot), envio sempre via janela de cancelamento do outbox (`outbox_aprovacao.py`). 13 testes em `functions/test_secretario_whatsapp.py`, contados um a um. `docs/okf/log.md` já tem a entrada correspondente.

**Duas frentes novas abertas com o dev agora, ambas `aguardando: dev` em `docs/dev-sync.md`** (escopo completo já escrito lá, não precisa duplicar — só ler o topo do arquivo):

- **(A) Ativação self-service do Modo Secretário — prioridade.** Motivada por: hoje não existe nenhuma forma do André (ou do Claude em sessão) ligar/desligar o modo sozinho — só via Console, mesma limitação de outras flags do projeto. Pedido: tools MCP novas (`ativar_modo_secretario`, `desativar_modo_secretario`, `consultar_status_modo_secretario`) pra eu poder ligar na hora quando o André pedir numa conversa; editor na tela de Settings como caminho alternativo (`getAutomationSettings`/`updateAutomationSettings`, `functions/main.py:~13649`); e refino do comportamento em grupo — hoje todo grupo é ignorado (`functions/secretario_whatsapp.py:437`), o pedido é: grupo só entra em ação se estiver na allowlist E o André for mencionado naquela mensagem específica (reaproveitando os campos `mentions_andre`/`mentioned_ids` que já existem no pipeline, ver `functions/inbox_pendentes.py:177-181` e `:322-335`).
- **(B) Seção 3.3 do plano — investigação completa com contato prioritário pré-avisado.** Plano completo em `docs/modo-secretario-hermes.md` (seção 3.3). Quando o André avisa de antemão quem é a pessoa e o que precisa saber da resposta dela, o Hermes conduz a conversa ativamente (não um recado genérico) e ao final apresenta um resumo estruturado. Pedido: nova tool `preparar_contato_prioritario_secretario` (+ `consultar_.../cancelar_...`), coleção `secretario_contatos_prioritarios/{chat_id}`, teto de trocas maior só pra esse caso (`max_trocas_prioritario`, sugestão 6), nova tool de conclusão da investigação (`concluir_investigacao_prioritaria`) que gera item na fila `atencao` com o resumo pronto. Todos os guardrails do MVP (agenda, dados sensíveis, envio via outbox) continuam valendo sem exceção.

Pedi ao dev pra priorizar (A) antes ou em paralelo com (B), já que é o que falta pro André conseguir testar o que já está em produção.

## Próximo passo ao retomar esta conversa

1. Ler `docs/dev-sync.md` — bloco `## Estado atual` primeiro, depois o topo de `## Mensagens do Dev`.
2. Se `aguardando: dev` e nada novo → nada a fazer, a tarefa agendada de 25 min já cobre a checagem sozinha.
3. Se o dev respondeu (bloco virou ou vai virar `aguardando: claude`) → **antes de reportar qualquer coisa ao André**, abrir os arquivos citados no relato, contar testes, checar `git log`/commit, comparar contra o escopo exato pedido em (A) e/ou (B) acima. Só depois disso escrever o veredito em `docs/dev-sync.md` (nova entrada no topo de `## Mensagens do Claude`, atualizando `## Estado atual`) e avisar o André em português, conciso.
4. Se aprovado, perguntar ao André se quer seguir para a próxima frente ou testar o que já está pronto.

## Tarefas agendadas já ativas (Cowork)

| Tarefa | Frequência | O que faz |
|---|---|---|
| `hermes-dev-sync-check` | a cada 25 min | Confere `docs/dev-sync.md`; revisa e responde ao dev quando for a vez do Claude, sempre verificando código/git em vez de confiar no relato |
| `hermes-briefing-matinal` | dias úteis, 06:45 | Resumo executivo matinal do Hermes — estado atual, fila de atenção, e-mail e agenda do dia |
| `hermes-varredura-followups` | diária, ~12:35 e ~17:xx | Varre promessas sem retorno, terceiros vencidos e e-mails pendentes; redige rascunhos no outbox para aprovação |
| `hermes-executor-agent-requests` | a cada 2h | Consome a fila `agent_requests` (ex.: consolidação de áudio) |

As duas últimas (`varredura-followups`, `executor-agent-requests`) são de fases anteriores do plano Hermes→Jarvis, não desta sessão — incluídas aqui só pra visibilidade completa.

## Pendências soltas, não relacionadas ao Modo Secretário (não esquecer, mas não são urgentes)

- **Atualizar memória `/areas/hermes.md`** — nunca foi feito nesta sessão; confirmar com o André se ainda faz sentido antes de fazer.
- **Confirmar ativação das 4 flags desligadas por padrão** (`atencao.financeiro.enabled`, `atencao.saude.enabled`, `atencao.promessa_sem_retorno.enabled`, `atencao.audio_relevante.enabled`) — pedido foi feito ao dev via `dev-sync.md` em 04/09 pra setar direto no Console; nunca confirmei se de fato foi feito.

## Arquivos-chave (contexto de código)

- `docs/dev-sync.md` — canal de coordenação com o dev, fonte da verdade do estado atual.
- `docs/modo-secretario-hermes.md` — plano completo do Modo Secretário (seções 1-8).
- `docs/plano-evolucao-hermes-jarvis.md` — plano mestre Hermes→Jarvis (fases 0-3), contexto maior.
- `docs/okf/log.md` — changelog cronológico do projeto.
- `functions/secretario_whatsapp.py`, `functions/atencao.py`, `functions/atencao_whatsapp.py`, `functions/outbox_aprovacao.py` — núcleo do Modo Secretário.
- `functions/main.py` (~L13649) — `getAutomationSettings`/`updateAutomationSettings`, whitelist de config editável pela UI.
- `functions/inbox_pendentes.py` (~L177, ~L322) — detecção de menção ao André em grupo (`mentions_andre`/`mentioned_ids`/`_andre_ids`), reaproveitada no pedido (A).
- `firestore.rules` — regra catch-all (`match /{document=**}`) já cobre coleções novas sem precisar de entrada explícita.

## Limitação técnica desta sessão

`mcp__workspace__bash` ficou indisponível a maior parte do tempo — não deu pra rodar a suíte de testes do dev localmente. Toda validação foi por leitura direta de código + estado do git (`HEAD`, `refs/heads`, `packed-refs`). Se numa sessão nova o shell estiver disponível, vale a pena rodar a suíte de verdade pelo menos uma vez para fechar essa lacuna.
