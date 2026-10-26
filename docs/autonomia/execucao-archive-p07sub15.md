# Arquivo: P07 sub-entrega 15/N (movida de execucao.md em 2026-10-26, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 15/N -- gravação em sombra do item de atenção por chave/versão (passo 8): followup_compromissos_sombra.registrar passa a gravar também o item de autonomy.atencao_compromisso (montar_item_atencao + deve_gravar) na coleção própria atencao_compromissos_sombra, id <promessa>__v1, com modo=sombra. Mesma flag da sombra de follow-up (system/settings.atencao.followup_sombra.enabled, padrão DESLIGADO). Só ids, ação, motivo constante, estado e datas -- nunca texto. A fila real (atencao) não é escrita."
estado: validado
inicio: "2026-10-25T14:00:00Z"
fim: "2026-10-25T14:25:00Z"
decisoes:
  - id: p07-sub15-colecao-propria
    motivo: "Gravar na fila real `atencao` mudaria comportamento de produção; coleção própria permite comparar o item novo com a fila antiga antes de qualquer troca."
  - id: p07-sub15-ordem
    motivo: "O item é gravado por último (depois do resumo e dos contadores). Limitação de projeto apontada na revisão: falha transitória na gravação do item não é refeita na reentrega (o resumo já existe) e gera perda esporádica de itens na medição."
  - id: p07-sub15-arquivo
    motivo: "execucao.md em 50487 bytes: bloco P07 sub 12 arquivado em execucao-archive-p07sub12.md."
testes:
  resultados:
    - "functions/ completo ANTES 4645 OK (diário); DEPOIS 4652 OK (+7 sobre o diário: 3 novos em test_followup_compromissos_sombra; o restante veio de PRs já mescladas em main)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): não achou bug; apenas a limitação de reentrega acima, de projeto."
pendencias:
  - "P07: passo 8 agora tem wiring em sombra. Falta a revisão final do pacote (pacote_concluido: P07) conferindo os 8 passos com chamadores; ativação das sombras só com aval do André."
```
