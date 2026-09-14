# Fase 3 — Autonomia graduada: visão geral e correções de leitura

A Fase 3, pelo roadmap (seção 5 do plano), tem três entregas: (1) promoção de
tipos de rascunho de "um toque" para "autônomo" com base em métricas, (2) voz
como canal fino sobre o mesmo catálogo, (3) auto-POPs. Diferente das Fases 0-2,
o plano não dá uma janela fechada ("a partir do mês 4") — trato como um
primeiro pacote de PRs, com mais PRs possíveis depois, conforme uso real gerar
dado.

Antes de escopar, fui direto ao código para não repetir o mesmo erro que o
handoff do PR 5 evitou (forçar `functions/simulation/` onde não cabia) —
desta vez ao contrário: quase reusei mecanismos existentes que pareciam
óbvios pelo nome, mas não são. Três achados mudam a leitura literal do plano:

**1. `correcoes_pendentes` / `processar_correcoes_pendentes` não é uma fila
genérica de "sistema sugere, André decide".** É o "Motor de Evolução
Autônoma": espera especificamente `titulo_procedimento`, `area_tematica`,
`novo_conteudo_proposto`, `justificativa_usuario`, roda verificação de
compliance via consenso web (Tavily, mín. 5 fontes) e grava a versão final em
`conhecimento_mestre` (base de POPs). O PR 165 (retro_agente.py) usa isso
corretamente, porque a proposta dele É um ajuste de POP. Promoção de nível de
autonomia de um tipo de rascunho não é um POP e não deveria passar pela
verificação de compliance legal — forçar essa ligação seria o mesmo
acoplamento artificial que o handoff do PR 5 recusou fazer com
`functions/simulation/`. A Fase 3 precisa do próprio canal de sugestão,
estruturalmente parecido com `elevacoes_sugeridas`/`decidir_elevacao`
(`deteccao_subproduto.py` — sugestão de elevar ação a objetivo estratégico):
uma coleção de sugestões simples + uma tool de decisão, sem verificação de
compliance no meio.

**2. O outbox (`whatsapp_outbox`, `outbox_aprovacao.py`) hoje é
WhatsApp-específico e tem um único ponto de criação**: a tool
`criar_rascunho_whatsapp` (`tools/hermes_tools.py`), chamada pelo Claude em
sessão (ao vivo ou agendada) — não há detector automático dos Cloud Functions
criando rascunho diretamente. Os campos hoje são `to_number`, `content`,
`status`, `motivo` (texto livre), `acao_id`, `item_atencao_id`, `origem`
(session_id de quem criou). Não existe nenhum campo estruturado de "tipo" de
rascunho, nem rastro de se o rascunho foi editado antes de aprovado —
`aplicar_edicao_rascunho` só atualiza o texto e devolve o status para
`aguardando_aprovacao`, sem marcar que houve edição. Sem isso, a frase do
plano ("os últimos 20 rascunhos de confirmação de reunião foram aprovados
sem edição") não tem como ser calculada hoje. Essa é a fundação que falta
antes de qualquer proposta de promoção — é o PR 1 desta fase.

**3. O canal de voz (`hermes-voice-client/`, `hermes-voice-bridge/`) já
segue exatamente o princípio "canal fino sobre o mesmo catálogo"** — o
`orchestrator.py` chama o mesmo `functions/mcp_server.py` via `mcp_client.py`
autenticado por Firebase ID Token, sem lógica própria de negócio. O registro
de tools (`tools/registry.py`) já computa `is_voice_enabled(tool)` por tool
(mcp-habilitada e fora de uma lista pequena de exclusão — formulário,
imagem, relatório longo, lote, escrita de dinheiro) e o servidor já devolve
esse campo em `tools/list` (`voiceEnabled`, `mcp_server.py:584`). O
`README.md` do cliente de voz diz que só 4 tools funcionam hoje
(`consultar_historico_acoes`, `buscar_arquivos_acervo`, `buscar_contato`,
`calculadora`), mas isso parece desatualizado: `tools/hermes_tools.py` já
tem 69 handlers reais registrados, e o `orchestrator.py` (`_build_gemini_tools`
chamado a partir de `mcp_client.list_tools()`) passa **todas** as tools que
`tools/list` devolve para o Gemini, sem filtrar por `voiceEnabled` — ou seja,
o cliente nem está usando o campo que o servidor já calcula certo. O gap real
não é "construir canal de voz", é "o cliente ainda não confia no campo que o
servidor já expõe". Isso é o PR 3.

**Auto-POPs (a terceira entrega) já está substancialmente entregue pelo PR
165** (Fase 2) — o retro semanal do agente já propõe ajuste de POP quando há
padrão concreto repetido, pelo canal certo (`correcoes_pendentes`). Não há
PR novo aqui a menos que o uso real revele uma lacuna específica depois que
o retro rodar algumas semanas.

## PRs desta primeira leva

1. **`outbox-tipo-e-edicao`** (fundação de dados) — adiciona `tipo` e
   `foi_editado` ao outbox de WhatsApp, mais uma função de agregação por
   tipo. Handoff: `01-outbox-tipo-e-edicao.md`.
2. **`promocao-autonomia`** (a definir após o PR 1 mergear) — nova coleção
   de sugestão de promoção de nível de autonomia por tipo (padrão
   `elevacoes_sugeridas`, não `correcoes_pendentes`), lida no retro semanal
   do agente (`retro_agente.py`) usando as métricas do PR 1, e uma tool de
   decisão (`decidir_promocao_autonomia`, espelhando `decidir_elevacao`).
   Ao aceitar, grava um flag por tipo em `system/mcp_access` (o doc que o
   próprio plano já cita como configurável sem deploy) que a criação de
   rascunho consulta para pular a aprovação quando o tipo já foi promovido.
3. **`voz-canal-real`** (a definir após o PR 2 mergear) — filtra
   `orchestrator.py` pelo campo `voiceEnabled` que o servidor já devolve,
   revalida o canal de voz com o catálogo real (bem maior que os 4 tools
   documentados), atualiza o `README.md` do cliente de voz com o resultado
   real, e confirma que a fila de atenção e a decisão de aprovação do outbox
   já são alcançáveis por voz (não estão na lista de exclusão).

Handoffs são entregues um de cada vez, como nas Fases 1 e 2 — o PR 1 já está
pronto em `01-outbox-tipo-e-edicao.md`; os PRs 2 e 3 serão detalhados quando
o anterior mergear e for verificado.
