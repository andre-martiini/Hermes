```yaml
pacote: "P07 revisão final do pacote (2ª) + correção da flag da sombra de extração: conferência dos 8 passos com chamador em produção (sob flag/sombra) por agente sem contexto; flag system/settings.atencao.extracao_estruturada.enabled passa a exigir booleano True (antes strings como 'false'/'0' ligavam a extração, igual às outras 3 sombras que já usavam 'is True')."
estado: validado
inicio: "2026-10-26T13:50:00Z"
fim: "2026-10-26T14:30:00Z"
decisoes:
  - id: p07-final2-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela da linha de autonomia no disparo das 11h BRT."
  - id: p07-final2-passos
    motivo: "Passos 1-8 têm chamador em produção sob flag desligada/sombra (extracao_compromissos_sombra, correlacao_, cumprimento_, followup_compromissos_sombra, via atencao_whatsapp). Nenhuma sombra envia mensagem nem fecha atenção real; escrita só em coleções *_sombra. Testes exigidos (almoço, 'vou tentar') existem."
  - id: p07-final2-substituir
    motivo: "REVISADA após achado do Codex: o passo 3 NÃO fica atendido; P07 permanece pendente. Registro original: compromissos_chat.substituir segue sem chamador: a extração não emite sinal de substituição e o contrato proíbe inventar relação por semelhança. Passo 3 atendido por independência de múltiplos compromissos + capacidade de substituição explícita pronta para quando houver sinal. Decisão: não criar sinal de modelo agora."
  - id: p07-final2-a06
    motivo: "O fechamento por comprimento (>40 caracteres) em atencao_whatsapp segue ativo em produção; a troca pelo avaliador novo depende de ligar as sombras e medir precisão com dados reais (portão de ativação do André). Reversão do plano não exige removê-lo antes disso."
  - id: p07-final2-arquivo
    motivo: "execucao.md acima de ~50KB: blocos P07 sub 15 e sub 16 arquivados em execucao-archive-p07sub15.md e execucao-archive-p07sub16.md."
testes:
  resultados:
    - "functions/ completo ANTES 4664 OK (main 882b6e5); DEPOIS 4664 OK (teste existente estendido com valores não booleanos)."
revisao_adversarial:
  - "Revisão final (agente sem contexto): chamadores dos 8 passos confirmados; 1 achado real (flag da extração aceitava string/int truthy) -> corrigido. Rodada sobre o diff: não achou nada."
pendencias:
  - "P07 PENDENTE (achado do Codex na PR 537, verificado): o passo 3 exige relação de substituição explícita; compromissos_chat.substituir não tem chamador e o registro de compromissos recomeça vazio a cada mensagem (não persiste entre mensagens). Próxima sub-entrega: persistir o registro por chat (sombra) e definir o sinal de substituição (ou declarar o passo atendido por decisão do André); só então pacote_concluido: P07. Ativação das sombras só com aval do André."
```
