# Arquivo: P06 sub-entregas 6/N e 7/N (movidas de execucao.md em 2026-10-20, sem alteração de conteúdo; ambas `estado: validado`)

```yaml
pacote: "P06 sub-entrega 6/N -- passo 10, varredura SOMENTE LEITURA de knowledge_nodes: autonomy.memoria_suspeita.varrer_knowledge_nodes(db) pagina por order_by('__name__') + start_after (padrão de mcp_jobs), limita a max_documentos (5000) e devolve ResultadoVarredura(relatorio, documentos_lidos, truncado). Não grava; erro de leitura propaga. Sem wiring em main.py nem tool nova (destino do relatório segue como sub-entrega seguinte)."
estado: validado
inicio: "2026-10-18T17:00:00Z"
fim: "2026-10-18T17:40:00Z"
decisoes:
  - id: p06-sub6-sem-tool-nova
    motivo: "Expor como tool MCP exigiria contrato P03 (annotations, outputSchema, idempotência) e decisão de produto sobre o destino (fila de atenção vs. tool); mantida função de biblioteca testada, sem efeito em produção."
  - id: p06-sub6-diario-arquivado
    motivo: "execucao.md passava de 61KB; bloco P06 sub-entrega 3/N movido para execucao-archive-p06sub3-consolidado.md."
testes:
  resultados:
    - "functions/ completo ANTES 4174 OK, DEPOIS 4185 OK no head final (+11 testes de varredura; test_memoria_suspeita 44 OK)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): código de produção sem bug; lacunas de teste (max_documentos não múltiplo da página, relatório com documento None) -- corrigidas com 3 testes. Codex (PR #465): P2 real -- a varredura retinha todos os documentos (embeddings de 768 floats) até o fim; corrigido classificando cada página na hora e retendo só os achados. Rodada 2 (agente sem contexto): código sem bug; teste de retenção fraco, reforçado com weakref (mutação que retém documentos derruba 2 testes)."
pendencias:
  - "Destino do relatório (fila de atenção ou tool somente leitura) e passo 9 (modelo por pessoa)."

---
pacote: "P06 sub-entrega 7/N -- passo 10, destino do relatório: tool MCP SOMENTE LEITURA consultar_memoria_suspeita (functions/tools/consultar_memoria_suspeita.py) sobre varrer_knowledge_nodes. Devolve documentos_lidos, truncado, total_com_sinais, contagem_por_sinal, achados (doc_id + sinal/campo/evidência) limitados por `limite` (1-200, padrão 50) e `aviso` de que a evidência é dado não confiável. Registrada em registry/inventory/schema; erro de leitura devolve {erro} sem relatório parcial. Nada é apagado, rebaixado ou superado."
estado: validado
inicio: "2026-10-18T19:50:00Z"
fim: "2026-10-18T20:15:00Z"
decisoes:
  - id: p06-sub7-tool-leitura
    motivo: "Default seguro entre fila de atenção (escreve) e tool (lê): tool somente leitura, sem efeito em produção além de leituras de Firestore sob demanda do próprio usuário."
  - id: p06-sub7-sem-cursor
    motivo: "Teto de 5000 documentos por chamada sem cursor (achado da revisão): `truncado` sinaliza o corte; paginação por cursor fica para quando knowledge_nodes se aproximar do teto. Não está em _TOOLS_LONGAS (varredura ~25 páginas, bem abaixo do timeout)."
  - id: p06-sub7-triagem-pr466
    motivo: "PR #466 (Live Ideas, avulsa do André, aberta há minutos) não é desta linha: não tocada."
testes:
  resultados:
    - "functions/ completo ANTES 4185 OK, DEPOIS 4190 OK (+5 em test_consultar_memoria_suspeita; 4193 OK após a revisão adversarial; +1 teste do achado do Codex)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): sem bug de contrato nem escrita; reais corrigidos: evidência com possível injeção sem aviso, limite com bool/inf, teste de somente leitura que só mockava a varredura (agora fake de db que proíbe qualquer método de escrita). Cap sem cursor e custo documentados nas decisões."
  - "Codex (PR #467): P2 real -- a tool entraria no canal de voz (is_voice_enabled); adicionada a _VOICE_EXCLUDED com teste."
pendencias:
  - "Passo 9 (modelo por pessoa); passos 5-8 (recuperação, obter_contexto_operacional/consultar_memoria_contextual, cursor, mapa de POPs)."

---
```
