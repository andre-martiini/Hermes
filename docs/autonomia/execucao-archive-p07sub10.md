# Arquivo: P07 sub-entrega 10/N (movida de execucao.md em 2026-10-24, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 10/N -- suíte de avaliação F02: functions/autonomy/avaliacao_f02.py. medir_precisao_cumprimento(casos) roda avaliar_cumprimento sobre corpus sintético (CASOS_F02, 16 casos: 4 cumprimentos reais, 12 negativos -- mensagem longa sobre almoço, negação, objeto diferente/incompleto, mídia sem nome conferível, anexo sem mídia, hedge, futuro, nova promessa, cancelamento, parcial) e mede a precisão de fechamento da seção 11 (corretos/fechados automaticamente; limiar 98%). aprovado exige >=3 fechamentos, ao menos 1 caso negativo e precisão >= limiar; limiar só aceita 0.98..1; casos de tipo exato, senão ValueError. Cobre os aceites F02: arquivo por e-mail encerra promessa do WhatsApp (vínculo por ID), só semântico não fecha. Sem I/O e sem wiring; fila antiga e A06 não alteradas."
estado: validado
inicio: "2026-10-23T16:45:00Z"
fim: "2026-10-23T17:50:00Z"
decisoes:
  - id: p07-sub10-triagem
    motivo: "Nenhuma PR aberta no início do disparo das 17h BRT; nenhuma execução paralela da linha de autonomia."
  - id: p07-sub10-arquivo-execucao
    motivo: "execucao.md arquivado (bloco P07 sub 7 -> execucao-archive-p07sub7.md)."
  - id: p07-sub10-corpus-pequeno
    motivo: "Corpus sintético de 16 casos é piso de regressão, não a medição de produção: a precisão real vem dos dados da sombra (sub 9). Corpus não é deduplicado (exige má-fé do chamador)."
testes:
  resultados:
    - "functions/ completo ANTES 4589 OK (P07 sub 9); test_autonomy_avaliacao_f02 11 OK (novo); DEPOIS 4600 OK (head final)."
revisao_adversarial:
  - "Rodada 1: rótulo cumpre sem validação de tipo, limiar sem faixa, sem amostra mínima, entradas inválidas inconsistentes. Rodada 2: subclasse forjando cumpre, limiar abaixo de 98%, corpus só de positivos aprovando, exceções não-ValueError e campos sem validação. Todos corrigidos. Rodada 3: não achou nada."
pendencias:
  - "P07: wiring de correlação/cumprimento/prazo na fila de atenção somente com flag/sombra; medir precisão com dados reais da sombra antes de qualquer fechamento automático; revisão final do pacote para pacote_concluido: P07."
```
