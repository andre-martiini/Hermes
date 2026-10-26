# Arquivo: P07 correção da revisão final (movida de execucao.md em 2026-10-26, sem alteração de conteúdo)

```yaml
pacote: "P07 correção da revisão final -- só documentação. A entrada anterior (revisão final, PR #520) declarou o P07 concluído por engano e fica REVOGADA: a revisão do Codex, chegada depois do merge, é procedente. (1) autonomy/correlacao_entregaveis.correlacionar não tem chamador em produção (passo 5 sem wiring); (2) autonomy/atencao_compromisso só é usado por followup_compromissos_sombra para copiar a próxima avaliação, sem gravar a decisão semântica na fila de atenção (passo 8 sem wiring). (3) A flag da sombra de extração é system/settings.atencao.extracao_estruturada.enabled (não atencao.extracao_sombra); as outras são atencao.cumprimento_sombra.enabled e atencao.followup_sombra.enabled."
estado: validado
inicio: "2026-10-24T20:10:00Z"
fim: "2026-10-24T20:20:00Z"
decisoes:
  - id: p07-correcao-causa
    motivo: "Fiz o merge da #520 sem esperar os comentários do Codex (só conferi os checks do CI). Passa a valer: ler reviews/comentários de bots antes de mesclar, mesmo em PR de docs."
  - id: p07-correcao-estado
    motivo: "P07 segue ABERTO. Faltam sub-entregas de wiring em sombra: correlação de entregáveis entre canais (passo 5) e escrita do item de atenção por chave/versão (passo 8), ambas atrás de flag desligada."
testes:
  resultados:
    - "Sem mudança de código; functions/ completo 4636 OK em main."
revisao_adversarial:
  - "Não aplicável (docs)."
pendencias:
  - "P07 sub 14: wiring em sombra de correlacionar (passo 5). P07 sub 15: gravação do item de atenção por chave/versão (passo 8), em sombra. Só depois, nova revisão final; ativação das sombras só com aval do André."
```
