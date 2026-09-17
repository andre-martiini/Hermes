# PR 1 da Fase 3 — Tipo e rastreio de edição no outbox de WhatsApp

Fundação de dados para a promoção de autonomia (Eixo 3 do plano). Sem isso
não dá para medir "os últimos N rascunhos de tipo X foram aprovados sem
edição" — hoje o outbox não sabe o tipo do rascunho nem se ele foi editado
antes de aprovado. Este PR não cria nenhuma lógica de promoção ainda — só a
base de dados e a métrica. Contexto completo da leitura do código em
`00-visao-geral.md`.

## O que muda em `functions/outbox_aprovacao.py`

**1. Campo `tipo` em `criar_rascunho`.** Novo parâmetro `tipo: str`,
persistido no payload do documento junto com os campos que já existem
(`to_number`, `content`, `status`, `motivo`, `acao_id`, `item_atencao_id`,
`origem`). Não force um enum fechado agora — quem decide o vocabulário de
tipos é quem chama a tool (hoje, o Claude em sessão), porque só há um mês de
uso real e a categorização vai emergir do uso, não de uma lista inventada
aqui. Trate `tipo` como opcional com default `"outro"` para não quebrar
chamadas existentes que ainda não passam esse argumento.

**2. Campo `foi_editado` (bool, default `False`).**
`aplicar_edicao_rascunho` deve setar `foi_editado: True` no mesmo `update()`
que já grava o novo texto — hoje essa função só grava `content` e devolve o
status para `STATUS_AGUARDANDO`, sem deixar rastro de que houve edição.
Importante: se o rascunho for editado mais de uma vez antes de aprovado,
`foi_editado` continua `True` (é um "alguma vez foi editado", não um
contador).

**3. Nova função `metricas_por_tipo(db, tipo: str, limite: int = 20) ->
dict`.** Lógica pura, no mesmo padrão das outras funções do arquivo (ex.
`avaliar_expirados`): busca os últimos `limite` documentos com aquele `tipo`
e `status` em (`pending`, `sent`) — ou seja, já decididos e aprovados, não
os ainda `aguardando_aprovacao` nem os `descartado`/`expirado` (descarte e
expiração não são "editado ou não", são outra decisão) — ordenados por
`aprovado_em` decrescente. Devolve:

```python
{
    "tipo": tipo,
    "amostra": <int>,               # quantos documentos entraram na conta (pode ser < limite)
    "aprovados_sem_edicao": <int>,
    "taxa_sem_edicao": <float>,      # aprovados_sem_edicao / amostra, ou 0.0 se amostra == 0
}
```

Sem chamada de rede nem dependência de Gemini — é só uma query e uma conta,
para poder testar com o `MockDb`/`MockQuery` que já existe em
`test_atencao.py` (mesmo padrão de reuso do PR 5, `test_regressao_proatividade.py`),
sem duplicar fixture.

## O que muda em `tools/hermes_tools.py` e no schema

`criar_rascunho_whatsapp` (linha ~470) precisa repassar `args.get("tipo")`
para `criar_rascunho`. Adicionar `tipo` (string, opcional) ao schema
`tools/schemas/criar_rascunho_whatsapp.json` com uma descrição que oriente o
Claude a escolher um rótulo curto e estável (ex. `confirmacao_reuniao`,
`retorno_promessa`, `cobranca_terceiro`) em vez de texto livre variável a
cada chamada — a métrica só funciona se o mesmo tipo de situação usar
sempre o mesmo rótulo.

## Testes (`functions/test_outbox_aprovacao.py`, arquivo já existe — estender)

- `criar_rascunho` grava `tipo` corretamente (com e sem o argumento, testando
  o default `"outro"`).
- `aplicar_edicao_rascunho` seta `foi_editado=True`; um rascunho nunca
  editado mantém `foi_editado=False` após `aprovar_rascunho`.
- `metricas_por_tipo`: cenário com amostra mista (alguns editados, alguns
  não, um `descartado` e um `aguardando_aprovacao` no meio, que devem ficar
  de fora da conta) confirmando `amostra`, `aprovados_sem_edicao` e
  `taxa_sem_edicao` corretos; cenário com `amostra == 0` devolvendo
  `taxa_sem_edicao == 0.0` sem `ZeroDivisionError`.

## Fora de escopo deste PR

Nenhuma proposta de promoção de autonomia, nenhuma mudança em
`retro_agente.py`, nenhuma mudança em `system/mcp_access`. Isso é o PR 2
("promocao-autonomia"), cujo handoff vem depois que este mergear e a
métrica estiver rodando de verdade — assim o PR 2 já nasce sabendo se
`taxa_sem_edicao` está se comportando como esperado com dado real.
