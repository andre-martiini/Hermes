# Arquivo: P07 sub-entrega 9/N (movida de execucao.md em 2026-10-24, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 9/N -- passo 2 (wiring em sombra): functions/extracao_compromissos_sombra.py, chamado no fim de on_whatsapp_message_atencao (isolado em try/except, depois de resposta_esperada). Atrás de system/settings.atencao.extracao_estruturada.enabled (padrão DESLIGADO = reversão). Só mensagem from_me de chat individual, fora do bot, em que a seleção barata (classificar_mensagem) achou candidato; chama o modelo leve, valida com validar_extracao e grava em extracao_compromissos_sombra apenas ids, classes e concordância (comparar_sombra) -- nunca o texto. Não altera promessas_abertas, fila de atenção nem A06. Custo contido por max_por_dia (padrão 200; contador incrementado antes de ler, dia em America/Sao_Paulo) e dedupe por doc já existente (reentrega do gatilho)."
estado: validado
inicio: "2026-10-23T13:45:00Z"
fim: "2026-10-23T14:40:00Z"
decisoes:
  - id: p07-sub9-triagem
    motivo: "Nenhuma PR aberta no início do disparo das 14h BRT; nenhuma execução paralela da linha de autonomia."
  - id: p07-sub9-arquivo-execucao
    motivo: "execucao.md arquivado (blocos P07 sub 5 e 6 -> execucao-archive-p07sub5-sub6.md)."
  - id: p07-sub9-limitacoes
    motivo: "Aceitas por ser sombra desligada por padrão: dedupe não atômico (duas entregas simultâneas do mesmo evento podem contar em dobro avaliadas/concordam); client Gemini sem timeout próprio (bloco roda por último no gatilho, após os demais detectores); ValueError do SDK conta como saida_invalida; cerca ```JSON em maiúsculas conta como saida_invalida. Reabrir antes de ligar a flag."
testes:
  resultados:
    - "functions/ completo ANTES 4582 OK (P07 sub 8); test_extracao_compromissos_sombra 7 OK (novo); DEPOIS 4589 OK (head final, após o ajuste do Codex; teste novo de idade da mensagem)."
revisao_adversarial:
  - "Rodada 1: contador lido-depois-incrementado (limite furável), reentrega duplicando chamada/métrica, bloco antes de resposta_esperada, dia UTC no contador. Corrigido (incremento antes de ler, dedupe por documento, bloco por último, fuso local). Rodada 2: prazos relativos usavam data UTC (dia errado entre 21h e 24h) -> corrigido com hoje local; dedupe concorrente não atômico aceito (ver limitações). Não houve rodada 3 sobre a correção do fuso (troca de uma linha, coberta pela suíte). Codex (P2) na PR: mensagem antiga do bot restaurada por backfill escapava da marca de 6h -> só mensagens com timestamp entre -5min e 1h são avaliadas (IDADE_MAX); teste novo."
pendencias:
  - "P07: suíte F02 com limiar de precisão da seção 11 (medir com dados da sombra); wiring de correlação/cumprimento/prazo na fila de atenção somente com flag/sombra; revisão final do pacote para pacote_concluido: P07."
```
