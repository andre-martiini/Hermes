# Arquivo: P07 sub-entrega 11/N (movida de execucao.md em 2026-10-24, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 11/N -- wiring em sombra do avaliador de cumprimento: functions/cumprimento_compromissos_sombra.py, chamado em _processar_promessa (atencao_whatsapp.py) logo após decidir_acao_mensagem_from_me, isolado em try/except. Atrás de system/settings.atencao.cumprimento_sombra.enabled (padrão DESLIGADO, exige True booleano = reversão). Para toda mensagem from_me de chat individual com promessa aberta/vencida (decisão antiga cumprir ou nenhuma), compara o fechamento do A06 (comprimento) com autonomy.cumprimento.avaliar_cumprimento e grava em cumprimento_compromissos_sombra só ids, estado novo, incerta e divergencia (nao_avaliavel | ambos_fecham | so_antigo_fecha | so_novo_fecha | ambos_mantem) -- nunca texto nem evidência. Contadores diários em cumprimento_compromissos_sombra_contadores. Sem chamada de modelo. Não altera promessas, fila de atenção nem A06."
estado: validado
inicio: "2026-10-23T19:45:00Z"
fim: "2026-10-23T20:20:00Z"
decisoes:
  - id: p07-sub11-triagem
    motivo: "Nenhuma PR aberta no início do disparo das 17h BRT; nenhuma execução paralela da linha de autonomia."
  - id: p07-sub11-arquivo-execucao
    motivo: "execucao.md arquivado (bloco P07 sub 8 -> execucao-archive-p07sub8.md)."
  - id: p07-sub11-limitacoes
    motivo: "Aceitas por ser sombra desligada por padrão: dedupe check-then-set não atômico (entregas simultâneas podem contar em dobro); contador gravado depois do documento (falha do contador subconta a amostra); ids com barra fariam o Firestore recusar o path (ids do WhatsApp não têm barra). Reabrir antes de ligar a flag."
testes:
  resultados:
    - "functions/ completo ANTES 4600 OK (P07 sub 10); test_cumprimento_compromissos_sombra 11 OK (novo); DEPOIS 4611 OK (head final, após os ajustes do Codex)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): não achou defeito que altere o fluxo antigo ou grave texto; só os três menores acima, aceitos. Codex na PR: (P1) promessas do A06 ("te retorno amanhã") não têm objeto documental e (P2) a captura do WhatsApp não grava media.filename, então o veredito novo nunca fecharia e a métrica não mediria nada -> campos avaliavel/motivo_nao_avaliavel (promessa_sem_objeto | midia_sem_nome) e divergencia nao_avaliavel à parte; 2 testes novos. Rodada 2 (focada): mídia só com nome correto sem texto e vereditos firmes em promessa sem objeto eram classificados como nao_avaliavel indevidamente ou enviesavam a métrica -> nao_avaliavel só quando o veredito é incerto por promessa_sem_objeto/anexo_nao_confere; 2 testes novos. Rodada 3 não feita (correção de uma condição, coberta por testes)."
pendencias:
  - "P07: a sombra de cumprimento só mede promessas com objeto documental e mídia nomeada; para medir o A06 real é preciso capturar media.filename (services/whatsapp-capture) ou usar a extração estruturada da sub 9; wiring de prazo/follow-up (revalidar_followup + atencao_compromisso) na fila de atenção somente com flag/sombra; medir precisão com dados reais da sombra antes de qualquer fechamento automático; revisão final do pacote para pacote_concluido: P07."
```
