# Arquivo: P07 sub-entrega 12/N (movida de execucao.md em 2026-10-25, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 12/N -- wiring em sombra da revalidação de follow-up: functions/followup_compromissos_sombra.py, chamado em vencer_promessas (atencao_whatsapp.py) para cada promessa que vai virar vencida, isolado em try/except. Atrás de system/settings.atencao.followup_sombra.enabled (padrão DESLIGADO, exige True booleano = reversão). Monta o contexto real (mensagens do chat desde a promessa sem as do bot, rascunho pendente no outbox por item_atencao_id, estado do item de atenção), roda autonomy.followup_guard.revalidar_followup e grava em followup_compromissos_sombra só ids, ação nova, motivo, próxima avaliação e divergencia (ambos_alertam | so_novo_adia | so_novo_suprime | nenhum_alerta) -- nunca texto. Contadores diários em followup_compromissos_sombra_contadores. Sem modelo, sem envio; promessas, fila de atenção e A07 não alteradas."
estado: validado
inicio: "2026-10-24T13:00:00Z"
fim: "2026-10-24T14:00:00Z"
decisoes:
  - id: p07-sub12-triagem
    motivo: "Nenhuma PR aberta no início do disparo das 8h BRT; nenhuma execução paralela da linha de autonomia."
  - id: p07-sub12-arquivo-execucao
    motivo: "execucao.md arquivado (bloco P07 sub 9 -> execucao-archive-p07sub9.md)."
  - id: p07-sub12-limitacoes
    motivo: "Aceitas por ser sombra desligada por padrão: contador gravado depois do documento (falha subconta; os documentos são a fonte); até ~200 leituras seriais de mensagem do bot por promessa; registro do Gaspar vale 6h (eco antigo conta como intervenção e só aumenta so_novo_adia); flag lida por promessa. Reabrir antes de ligar a flag."
testes:
  resultados:
    - "functions/ completo ANTES 4611 OK (P07 sub 11); test_followup_compromissos_sombra 13 OK (novo); DEPOIS 4624 OK (head final)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): sem defeito grave; corrigidos (a) item de atenção já fechado pelo dono distorcia a métrica -> divergencia nenhum_alerta e (b) respostas do bot contavam como intervenção humana -> filtradas com eh_mensagem_do_bot; 1 teste novo e 1 ajustado. Rodada 2 (focada nas correções): não achou nada que bloqueie; apenas as limitações acima. Codex (P2) na PR: a query de mensagens (igualdade + intervalo) pedia timestamp ascendente, mas o índice composto implantado é chat_id ASC, timestamp DESC -> order_by timestamp DESC explícito (o guarda reordena sozinho); teste ajustado."
pendencias:
  - "P07: capturar media.filename (services/whatsapp-capture) ou usar a extração estruturada para a sombra de cumprimento medir o A06 real; ligar as 3 sombras (extração, cumprimento, follow-up) só com aval do André e medir precisão antes de qualquer fechamento automático; revisão final do pacote para pacote_concluido: P07."
```
