# Arquivo: P07 sub-entrega 17/N (movida de execucao.md em 2026-10-26, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 17/N -- prazo expresso na sombra de acompanhamento (passo 4): followup_compromissos_sombra._acompanhamento passa a extrair o prazo expresso do texto da promessa (autonomy.commitments.extrair_prazo_expresso, determinístico, dia local America/Sao_Paulo de prometido_em) e a entregá-lo a planejar_acompanhamento; prazo expresso com data vence no fim do dia prometido (origem prazo_expresso). Se o planejador recusar o prazo, cai na estimativa e grava acompanhamento_prazo_descartado=true. Mesma flag da sombra de follow-up (padrão DESLIGADO); só números/datas, nunca texto."
estado: validado
inicio: "2026-10-25T19:48:00Z"
fim: "2026-10-25T20:20:00Z"
decisoes:
  - id: p07-sub17-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela da linha de autonomia no disparo das 17h BRT."
  - id: p07-sub17-fonte-do-prazo
    motivo: "A extração estruturada em sombra não guarda prazo (só concordância) e o texto não é gravado; usa-se a seleção barata sobre promessa.texto, que já alimenta a promessa. Ler o prazo do modelo exigiria gravar dado novo da extração: fora do escopo."
  - id: p07-sub17-prazo-distante
    motivo: "Sem teto para prazos distantes (ex.: ano digitado errado) -- prazo expresso é vinculante por contrato; só polui o delta da métrica, que não é agregada ainda. Limitação declarada."
  - id: p07-sub17-arquivo
    motivo: "execucao.md em 49925 bytes: bloco P07 sub 14 arquivado em execucao-archive-p07sub14.md."
testes:
  resultados:
    - "functions/ completo ANTES 4657 OK (diário); DEPOIS 4660 OK (+3 em test_followup_compromissos_sombra; fixture PROMESSA sem prazo para manter os testes de estimativa)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): nenhum bug; verificou fuso/dia, prometido_em naive (acompanhamento_erro), overflow (cai na estimativa), texto não-string. Achado menor: sem teto para prazo distante (limitação acima). Sem rodada 2: lógica pura, achado só afeta métrica."
pendencias:
  - "P07: ativação das sombras (extração, cumprimento, correlação, follow-up) só com aval do André e medição de precisão antes de qualquer fechamento automático; depois, nova revisão final do pacote (pacote_concluido: P07)."
```
