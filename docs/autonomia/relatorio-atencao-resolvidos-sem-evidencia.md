# Relatório — itens de `atencao` resolvidos sem evidência de conclusão

**Plano:** plano-hermes-autonomo-2026-09-06, P01, passo 10.

**Escopo desta entrega:** somente investigação de código e proposta de reconciliação. Por instrução explícita do próprio passo 10 do plano ("Não fazer limpeza histórica destrutiva"), este documento **não** altera nenhum registro existente, **não** implementa o script de reconciliação proposto na seção 4, e **não** consulta dados reais de produção (este ambiente não tem credenciais para isso). `atencao.py` também não está na lista de arquivos do P01 ("Arquivos: agent_requests.py, outbox_aprovacao.py, promocao_autonomia.py, core/idempotency.py, mcp_jobs.py, mcp_server.py, firestore.rules, deploy.yml") — o passo 10 pede relatório e proposta, não implementação.

## 1. Como um item de `atencao` é criado

`functions/atencao.py` (`COLLECTION = "atencao"`, linha 31) é o único ponto de escrita, via `_persistir_itens_atencao()` (linhas 237–293), usado por todos os detectores:

- `avaliar_etapas` / `detectar_atencao_acoes` (aguardando terceiro) — linhas 111–234 e 563–626.
- `avaliar_contas_vencendo` / `detectar_atencao_financeiro` — linhas 296–451.
- `avaliar_rotinas_saude` / `detectar_atencao_saude` — linhas 454–560.
- `promessa_sem_retorno` e `audio_relevante`, em `functions/atencao_whatsapp.py` — linhas 105–201/419–464 e 209–262/467–534.

Campos do documento: `origem, tipo, prioridade, titulo, resumo, acao_id, etapa_id, pessoa, prazo, evidencia{…}, sugestao, estado, chave_dedupe, criado_em, atualizado_em, resolvido_em, desfecho`. O campo `evidencia` documenta por que o item foi **aberto** (ex.: `chat_id`, `mensagem_ids`, `bill_id`) — em nenhum dos caminhos de resolução ele é usado para registrar prova de que o item foi **fechado**.

## 2. Como um item é marcado resolvido — os dois caminhos existentes

### 2.1 Caminho manual/agente — `resolver_item()`

`functions/atencao.py`, linhas 696–762. É o backend da tool MCP `resolver_item_atencao` (`mcp__Sistema_Hermes__resolver_item_atencao`, ligada em `functions/tools/hermes_tools.py` linhas 1991–1997, schema em `functions/tools/schemas/resolver_item_atencao.json`).

Entradas: `item_id`, `estado`, `desfecho` (texto livre). A única validação para fechar o item (linhas 717–718) é que `desfecho` não seja vazio — nada mais é checado: nenhum vínculo estrutural, nenhum campo de evidência, nenhuma verificação contra sistema externo. A função grava `estado`, `atualizado_em`, `resolvido_em` (server timestamp) e o texto livre de `desfecho` (linhas 721–729), e ecoa esse mesmo texto no diário da ação vinculada (linhas 732–755).

Isto é, literalmente, "virar o status + justificativa em texto livre" — qualquer chamador (o próprio agente, numa conversa) pode resolver qualquer item de qualquer `tipo` por este caminho, sem nenhuma prova estrutural de que a ação subjacente de fato aconteceu.

### 2.2 Caminho automático — `_processar_promessa()`

`functions/atencao_whatsapp.py`, linhas 419–464. Quando uma "promessa" (mensagem própria que bate com um regex de compromisso de retorno, linhas 45–53) está `vencida` e uma mensagem `from_me` posterior satisfaz `mensagem_cumpre_promessa` (tem mídia, ou é texto simples com mais de 40 caracteres e não é ela mesma uma nova promessa — linhas 89–102), o item é automaticamente marcado `estado=resolvido`, `desfecho=f"respondeu em {hora}"` (linhas 154–157 e 459–464), sem intervenção humana.

Este caminho está ancorado numa mensagem `from_me` real capturada do WhatsApp — mas a checagem é só uma heurística de tamanho/presença de mídia. Ela nunca consulta o status de entrega em `whatsapp_outbox`.

**Nenhum outro caminho** grava `atencao.estado = "resolvido"` (confirmado via busca por `ESTADO_RESOLVIDO` e `"estado": "resolvido"` em todo `functions/`).

## 3. Evidência de envio já existente, mas não referenciada pela resolução de `atencao`

`functions/outbox_aprovacao.py` (linhas 18–26) já define os status `pending/sent/failed/...` da coleção `whatsapp_outbox`. `functions/tools/schedule_whatsapp_message.py` enfileira sempre com `status="pending"` (linha 57) — o próprio docstring do arquivo (linhas 9–17) documenta um incidente real anterior em que o agente afirmou falsamente ter entregado uma mensagem, o que motivou essa separação enfileirar/confirmar. O worker local `services/whatsapp-capture/index.js` grava `status:'sent', sent_at, wa_message_id` só após confirmação real de entrega (~linhas 1005–1010) ou `status:'failed'` em caso de erro (~linhas 935–937, 1024–1029). `functions/tools/whatsapp_tools.py::consultar_envio()` (linha 356+) já expõe essa informação.

Ou seja: já existe uma fonte de evidência de entrega pronta e confiável — ela simplesmente não é consultada por nenhum dos dois caminhos de resolução de `atencao` descritos acima.

## 4. Não existe reconciliação hoje

Busca em `functions/`, `scripts/` e `docs/` não encontrou nenhum script ou consulta que compare `atencao.estado == "resolvido"` contra `whatsapp_outbox` ou qualquer outra evidência. Os scripts `scripts/reconcile_*.py` existentes são todos de reconciliação financeira, sem relação com `atencao`.

## 5. Risco

Qualquer turno do agente pode chamar `resolver_item_atencao(item_id, estado="resolvido", desfecho="respondeu no WhatsApp")` imediatamente após apenas **enfileirar** (não confirmar) um envio — sem nenhuma checagem estrutural — reproduzindo exatamente a mesma falha de confirmação falsa que `schedule_whatsapp_message.py` já precisou corrigir para a própria tool de envio (ver seção 3). O caminho automático (2.2) é mais bem ancorado (depende de uma mensagem real capturada), mas ainda assim não verifica entrega, só heurística de conteúdo.

Isto não é evidência de que registros históricos estejam de fato incorretos — é a identificação de uma lacuna estrutural que **permitiria** esse tipo de falso "resolvido" sem deixar rastro para auditoria posterior.

## 6. Proposta de reconciliação (não destrutiva, não implementada nesta entrega)

1. Adicionar um campo opcional `evidencia_resolucao {outbox_id, wa_message_id, verificado}` aos documentos de `atencao`, e um parâmetro opcional `evidencia_resolucao_id` na tool `resolver_item_atencao`. Quando o chamador informar um `outbox_id`, `resolver_item()` consultaria esse documento e gravaria se `status == "sent"` no momento da resolução — **sem nunca bloquear a resolução na ausência desse campo** (existem resoluções legítimas sem relação com WhatsApp, ex. financeiro, saúde).
2. Um novo script somente-leitura, ex. `scripts/reportar_atencao_resolvidos_sem_evidencia.py`: consulta `atencao` com `estado == "resolvido"` e `resolvido_em` dentro dos últimos N dias; para itens de `tipo` em `{promessa_sem_retorno, aguardando_terceiro_vencido}` (ou `desfecho` batendo com palavras-chave de "respondi"/"resolvido no WhatsApp"), procura um `whatsapp_outbox` correspondente com `status == "sent"` próximo de `resolvido_em`; emite um relatório (CSV/markdown) dos itens sem esse vínculo, **apenas para revisão manual do André** — sem reverter, apagar ou reescrever `estado` automaticamente.
3. Qualquer rollback ou correção de um registro histórico específico que essa revisão manual decidir necessária deve ser feita item a item, por decisão explícita do André, documentada como as demais decisões deste plano — nunca como limpeza em lote automatizada.

## 7. Status desta entrega

Investigação e proposta concluídas (passo 10 do P01). Implementação do campo `evidencia_resolucao` e do script de relatório fica como trabalho futuro, fora do escopo de arquivos do P01 — candidato natural a um pacote posterior focado em `atencao.py`/detecção de atenção, ou a uma sub-entrega dedicada caso o André priorize antes disso.
