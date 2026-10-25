# Arquivo: P07 sub-entrega 14/N (movida de execucao.md em 2026-10-25, sem alteração de conteúdo)

```yaml
pacote: "P07 sub-entrega 14/N -- wiring em sombra da correlação de entregáveis (passo 5): functions/correlacao_compromissos_sombra.py, chamado em _processar_promessa (atencao_whatsapp.py) após a decisão antiga, isolado em try/except. Atrás de system/settings.atencao.correlacao_sombra.enabled (padrão DESLIGADO, exige True booleano = reversão). Para mensagem from_me com anexo e promessa aberta/vencida (acao_antiga cumprir|nenhuma), roda autonomy.correlacao_entregaveis.correlacionar entre a promessa e o anexo (canal WhatsApp) e grava em correlacao_compromissos_sombra só ids, canais, contagens e resultado (vinculo_firme | so_semantico | sem_vinculo | nao_avaliavel com motivo promessa_sem_objeto | midia_sem_nome | fora_do_contrato) -- nunca texto nem nome de arquivo. Contadores diários em correlacao_compromissos_sombra_contadores. Sem modelo; promessas e fila de atenção não alteradas."
estado: validado
inicio: "2026-10-25T10:45:00Z"
fim: "2026-10-25T11:20:00Z"
decisoes:
  - id: p07-sub14-so-whatsapp
    motivo: "Só o WhatsApp tem fonte de evidência hoje (media.filename, sub 13). Gmail/tarefa/documento entram depois como novas Evidencia. Nenhum código grava ids_entregavel na promessa nem media.ids, então em produção só ocorrem so_semantico, sem_vinculo e nao_avaliavel; vinculo_firme só em teste."
  - id: p07-sub14-revisao
    motivo: "Rodada 1 achou: mensagem que cria promessa nova era correlacionada com a antiga (agora só cumprir|nenhuma); casos não avaliáveis inflavam sem_vinculo (agora nao_avaliavel com motivo); promessa longa sumia sem registro (agora fora_do_contrato)."
testes:
  resultados:
    - "functions/ completo ANTES 4636 OK (diário/main); DEPOIS 4645 OK (+9 de test_correlacao_compromissos_sombra)."
revisao_adversarial:
  - "Rodada 1: 3 achados reais (acima), corrigidos. Rodada 2 sobre a correção: não achou nada. Limitações iguais às das sombras irmãs (get-then-set não transacional)."
pendencias:
  - "P07 sub 15: gravação do item de atenção por chave/versão (passo 8) em sombra. Depois, nova revisão final; ativação das sombras só com aval do André."
  - "Limitação conhecida (Codex, PR #524): mídia restaurada depois por repairMissingMedia atualiza o doc e não dispara on_document_created, então as sombras de cumprimento e correlação não medem esse caminho (viés amostral). Mesma limitação da sombra de cumprimento; corrigir exige gatilho de update idempotente, fora do escopo de uma sombra. Considerar antes de ler as medições."
```
