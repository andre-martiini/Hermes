# Proposta: `limite_por_janela`/`usos_na_janela_atual` e `orcamento_maximo` do `Mandato` (passo 8 do plano, parte final)

Documento de proposta, não de execução — não é uma sub-entrega de código, não altera `docs/autonomia/execucao.md`. André pediu para priorizar "orçamento/revalidação no despacho" entre os itens abertos de P02; este documento existe para ele decidir os dois pontos abaixo antes de eu implementar, mesmo padrão de `proposta-p02-mandato-io-wrapper.md` (sub-entrega 17/N).

## O que já está pronto, e o que falta

`autonomy/policy.py::mandato_cobre()` já trata os dois campos corretamente e falha fechado (confirmado lendo o código, não por suposição): um `Mandato` com `limite_por_janela` declarado só cobre se `usos_na_janela_atual` tiver sido RESOLVIDO e ainda estiver abaixo do limite; um `Mandato` com `orcamento_maximo` declarado só cobre se `PolicyRequest.orcamento_restante` tiver sido resolvido e ainda restar saldo positivo (inclusive tratando `NaN` corretamente, achado de uma revisão adversarial anterior). Isso já é código testado, em produção, desde a sub-entrega 4/N.

O que falta é só o lado de leitura: o único wrapper real de `Mandato` que existe hoje, `autonomy/mandatos_io.py::mandato_tipo_promovido()` (usado por `liberar_rascunhos_promovidos` e por `propor_reagendamento_semanal`), deixa os dois campos deliberadamente como `None` — decisão já registrada na sub-entrega 17/N ("tipos promovidos hoje não têm dimensão financeira conhecida"; sem contagem por janela). `None` não é bug: `mandato_cobre()` trata isso como "este mandato não declara essa restrição", não como falha. Mas também significa que hoje nenhum mandato em produção tem orçamento nem limite por janela de fato — a proteção existe no motor, mas está dormente.

## Ponto 1 — `orcamento_maximo`: minha recomendação é não popular para `tipos_promovidos`

O único mandato real hoje é sobre ENVIO DE WHATSAPP (`tipos_promovidos`), não sobre uma missão que consome tokens/API paga. Não encontrei nenhuma dimensão financeira já rastreada para um envio de WhatsApp específico — `whatsapp_outbox` não guarda custo por mensagem. O exemplo do plano que fala em orçamento (seção 5.3: *"Preparar briefings... consumir até o teto aprovado"*) descreve uma MISSÃO delegada (P08/P09) com custo de LLM/execução real — não um envio de mensagem.

Recomendo deixar `orcamento_maximo` como `None` para `tipos_promovidos` (comportamento atual, sem mudança) e revisitar quando P08/P09 introduzir mandatos do tipo "missão", que é onde a noção de teto de orçamento faz sentido de verdade e já existe alguma medição de custo (seção 11.1 do plano). Só pergunto para não presumir: existe alguma dimensão de custo por envio (ex.: tarifa por mensagem de template do WhatsApp Business API) que eu não esteja vendo?

## Ponto 2 — `limite_por_janela`/`usos_na_janela_atual`: aqui a decisão é genuinamente sua

Esta É a peça do plano que bate com o segundo exemplo da seção 5.3 (*"no máximo uma vez por compromisso a cada dois dias úteis"*) — um limite de frequência por tipo de envio automático. Diferente do orçamento, aqui uma fonte de dado real existe: contar envios de um `tipo` já enviados (`whatsapp_outbox`, status de envio confirmado) numa janela de dias.

Três perguntas, nesta ordem:

1. **Você quer um teto de frequência nos envios automáticos por tipo, ou prefere manter sem limite (como é hoje) agora que a revogação já é transacional de verdade (sub-entrega 19/N) e cobre a corrida com a liberação automática?** Sem um caso concreto de "isso mandou volume demais", um teto arbitrário corre o risco de bloquear um dia legítimo de muita atividade (ex.: `confirmacao_reuniao` num dia com várias reuniões).
2. Se quiser um teto: **qual número e qual janela** (ex.: "no máximo 20 `confirmacao_reuniao` por dia", "no máximo 100 por semana")? Não tenho como propor um número sozinho sem inventar um volume que você não me deu.
3. Isso deveria ser **por tipo individual** (cada `tipo` promovido com seu próprio teto) ou **um teto agregado** somando todos os tipos promovidos? A proposta original da sub-entrega 17/N modela por tipo (`mandato_id=f"tipo_promovido:{tipo}"`), então um teto por tipo é o caminho de menor atrito — um agregado exigiria um mandato "guarda-chuva" novo, fora do desenho atual.

Minha recomendação, se quiser uma resposta rápida: não popular agora (deixar como está, sem limite), e revisitar só se um caso real pedir — mesmo espírito da recomendação (a) da proposta anterior sobre `valido_ate`, que você já aprovou. Mas a decisão é sua, não uma correção técnica objetiva.

## Nota sobre "revalidar versão/escopo no despacho" (resto do passo 8)

Verificado, não presumido: `autonomy.policy.avaliar()` roda por completo, com o código ATUAL do motor, a cada despacho — nunca existe uma decisão pré-computada e cacheada sendo reaproveitada depois. Não há hoje um caminho onde uma decisão "antiga" (de uma versão anterior da política) seja aplicada sem reavaliação. Por isso considero a parte de "versão" deste passo já estruturalmente coberta, sem pendência de código. "Escopo" fica fora deste documento — você já indicou que quer deixar OAuth/claims (passo 2) de lado por ora.

## Se aprovado, o que eu implementaria a seguir

Só depois da sua resposta às três perguntas do Ponto 2 (e à pergunta do Ponto 1, se houver dimensão de custo que eu não vi): estender `mandatos_io.mandato_tipo_promovido()` para contar envios reais em `whatsapp_outbox` por `tipo` numa janela, populando `limite_por_janela`/`usos_na_janela_atual` (se você quiser um teto) — mesmo padrão de sub-entrega técnica das anteriores (implementação + testes + revisão adversarial + PR na branch de feature, nunca em main direto, merge continua manual seu).
