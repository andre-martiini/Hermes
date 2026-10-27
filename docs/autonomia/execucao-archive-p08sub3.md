---

```yaml
pacote: "P08 sub-entrega 3/N -- seleção de modelo por configuração validada e custo por tarifa versionada (autonomy/modelos.py, passos 8-9): ConfigModelos (papel -> ids em ordem de preferência, imutável, cada id com TarifaModelo versionada, validação da conta vence em 90 dias, sem aliases latest/alias/default), selecionar_modelo com rotação por indisponíveis e erro tipado (papel desconhecido / validação vencida / todos indisponíveis, nunca modelo padrão escondido), custo_chamada em Decimal com leitura/escrita de cache e taxa_acerto_cache. Preços não embutidos: chegam da configuração da conta. Sem I/O (shadow/off, passo 11)."
estado: validado
inicio: "2026-10-27T14:30:00Z"
fim: "2026-10-27T15:10:00Z"
decisoes:
  - id: p08-sub3-triagem
    motivo: "Nenhuma PR da linha de autonomia aberta (a única aberta, #541 painel do dia, é de outra origem e não trivial: ignorada); nenhuma execução paralela."
  - id: p08-sub3-id-sem-data
    motivo: "Não exigi sufixo de data no id: os ids da conta (ex.: claude-opus-5-5) não têm; a garantia de snapshot fixo vem da lista validada + tarifa + validade de 90 dias. Só aliases explícitos (latest/alias/default, separador - ou .) são barrados."
  - id: p08-sub3-arquivo
    motivo: "execucao.md no limite de ~50KB: bloco P07 sub 19 arquivado em execucao-archive-p07sub19.md."
testes:
  resultados:
    - "functions/ completo ANTES 4713 OK (diário, P08 sub 2); DEPOIS 4741 OK (+28 em test_autonomy_modelos)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): achados reais (indisponiveis str virava caracteres; config mutável; validado_em no futuro nunca vencia; exceções não tipadas; set sem ordem; tzinfo sem offset; tarifa sem tipo; contexto Decimal global) -> corrigidos. Codex na PR: 1 achado P2 (itens não-str de indisponíveis ignorados) -> corrigido. Rodada 2 sobre a correção: 5 achados (preço/taxa ainda dependiam do contexto global; agora inválido só checado se papel existisse + OverflowError; custo sem validar tarifa/teto de tokens; indisponíveis não-str ignorados; config não hasheável) -> corrigidos e cobertos por teste. Achado de id sem data: recusado (ver decisão). Sem rodada 3: correções pequenas, lógica pura, cobertas por teste."
pendencias:
  - "P08: wiring (worker HTTP autenticado, Cloud Tasks, reserva/lease via autonomy.execution aplicando a DecisaoContinuacao, cliente Claude real consumindo ConfigModelos, adaptador Cowork, dispatcher shadow/off). P07: decisão do André sobre o sinal de substituição."
```
