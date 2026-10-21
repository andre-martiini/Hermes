# Arquivo: P06 sub-entregas 10/N e 11/N (movidas de execucao.md em 2026-10-21, sem alteração de conteúdo; ambas `estado: validado`)

```yaml
pacote: "P06 sub-entrega 10/N -- passo 5 (parte pura), recuperação por relevância, validade e autoridade: functions/autonomy/recuperacao.py. recuperar(documentos, consulta, entidades, similaridades, agora, limite) ordena documentos de knowledge_nodes por (frase exata + lexical + entidade + vetorial informada) x peso de autoridade da origem_fato (declaração humana 1.0 > fonte externa 0.7 > resumo derivado 0.5 > inferência 0.3 > legacy_unknown 0.2, com aviso_legado). Descarta com razão: superada, telemetria_uso, validade expirada/futura, sem texto, sem relevância (autoridade nunca cria relevância). Sem I/O, sem wiring em main.py nem tool nova."
estado: validado
inicio: "2026-10-19T16:50:00Z"
fim: "2026-10-19T17:30:00Z"
decisoes:
  - id: p06-sub10-so-logica-pura
    motivo: "Mesmo padrão incremental das sub-entregas 5-9; consultar_memoria_contextual/obter_contexto_operacional (passo 6) exigem contrato P03 e decisão de onde vem a similaridade vetorial."
  - id: p06-sub10-validade-so-data
    motivo: "validade_fim só com data (string de 10 chars ou date) vale até o fim desse dia (inclusivo); validade_inicio só com data vale desde 00:00 UTC. Validade ilegível nunca descarta (fail-open documentado)."
  - id: p06-sub10-triagem
    motivo: "Nenhuma PR aberta no início do disparo; nada a mesclar/fechar. execucao.md arquivado em execucao-archive-p05sub19-p06sub5.md (estava em ~50KB)."
testes:
  resultados:
    - "functions/ completo ANTES 4330 OK (201s); test_recuperacao 16 OK (novo arquivo); DEPOIS 4346 OK (196s) no head final."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): reais corrigidos -- casamento por substring sem fronteira de palavra (ana/Mariana), validade com date/'z'/naive, similaridades não-dict, documentos malformados sumindo sem registro; testes fracos reforçados (pesos numéricos, desempate contra ordem alfabética, fronteira validade_inicio, clamp)."
  - "Codex (PR #473): P2 real -- similaridade fora de 0..1 era clampada a relevância máxima; agora é ignorada (teste cobre 5, -0.1, 1.01, inf)."
  - "Rodada 2 (agente sem contexto): validade só-data expirava no início do dia (agora fim do dia), entidades None/str malformadas (agora ignoradas), lacunas de teste (campos resumo/fato, ordem superada x telemetria, ids de malformados) corrigidas. Sem outro achado."
pendencias:
  - "Passo 6 (obter_contexto_operacional/consultar_memoria_contextual consumindo recuperar + cursor_contexto), passo 9 (modelo por pessoa); busca vetorial real continua fora do módulo."

---
pacote: "P06 sub-entrega 11/N -- passo 6 (parte de leitura), tool MCP SOMENTE LEITURA consultar_memoria_contextual (functions/tools/consultar_memoria_contextual.py) sobre autonomy.recuperacao.recuperar. Varre knowledge_nodes paginado (até 5000), mantém só os top-`limite` globais, devolve fatos com origem_fato, motivos, validade, trecho (400 chars, dado não confiável) e legado_sem_proveniencia, mais descartados_por_razao e lacunas (varredura truncada / nenhum fato). Registrada em registry/inventory/schema, fora do canal de voz. Sem busca vetorial, sem cursor e sem obter_contexto_operacional (precisam de índice vetorial e de segredo de assinatura)."
estado: validado
inicio: "2026-10-19T19:50:00Z"
fim: "2026-10-19T20:35:00Z"
decisoes:
  - id: p06-sub11-sem-cursor-nem-vetorial
    motivo: "O cursor exige segredo de assinatura (origem ainda indefinida) e a similaridade vetorial exige o índice; a tool entra só com busca exata+lexical+entidade+autoridade, aditiva e reversível."
  - id: p06-sub11-triagem
    motivo: "Única PR aberta (#474, Dashboard/resumo do dia, avulsa do André, atualizada há <60 min) não é desta linha: não tocada."
testes:
  resultados:
    - "functions/ completo ANTES 4346 OK (registro da sub-entrega 10/N, head de main); test_consultar_memoria_contextual 19 OK (novo arquivo); DEPOIS 4365 OK (263s) no head final."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): real corrigido -- campo `id` no corpo do doc sobrescrevia o id do snapshot (KeyError derrubava a consulta inteira ou doc sumia como malformado); args não-dict agora vira erro de entrada; 7 testes novos (merge intercalado entre páginas, descartados somados, fronteira de truncamento, erro na 2ª página, embedding fora da saída, datetime)."
  - "Rodada 2 (agente sem contexto) sobre a correção: nada achado de real; só imprecisão de documentação do schema (corrigida)."
pendencias:
  - "Passo 6 restante (obter_contexto_operacional, contexto incremental com cursor assinado -- decidir origem do segredo -- e similaridade vetorial real), passo 9 (modelo por pessoa)."
```
