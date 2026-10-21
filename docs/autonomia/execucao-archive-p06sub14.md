# Arquivo: P06 sub-entrega 14/N e correção pós-merge (movidas de execucao.md em 2026-10-21, sem alteração de conteúdo)

```yaml
pacote: "P06 sub-entrega 14/N -- passo 7, cursor incremental ligado a obter_contexto_operacional (functions/tools/obter_contexto_operacional.py + schema). Segredo vem do ambiente (CONTEXT_CURSOR_SECRET) e o dono de ctx.user_uid; sem um dos dois, o contexto sai completo sem cursor (lacuna se o cliente enviou desde_cursor). Com cursor ativo a resposta traz `cursor` (autonomy.cursor_contexto, escopo contexto_operacional) e, com desde_cursor válido, `mudancas` (pendências/resultados novos ou alterados), calculadas sobre leitura ampla (100 pendências / 50 runs) enquanto a exibição segue limite_contexto. Cursor só avança se a leitura não atingiu o teto e o total é válido; senão devolve o recebido + lacuna. Marca com folga de 10s e comparação >=."
estado: validado
inicio: "2026-10-20T19:50:00Z"
fim: "2026-10-20T21:00:00Z"
decisoes:
  - id: p06-sub14-segredo-por-ambiente
    motivo: "Origem do segredo era a pendência aberta; default seguro e reversível: variável de ambiente CONTEXT_CURSOR_SECRET. Sem ela o recurso fica desligado (flag de desligamento natural), nada muda para os clientes atuais."
  - id: p06-sub14-triagem
    motivo: "Nenhuma PR aberta no início do disparo. execucao.md arquivado (blocos P06 sub 8 e 9 -> execucao-archive-p06sub8-sub9.md)."
testes:
  resultados:
    - "functions/ completo ANTES 4407 OK (202s, head de main); test_obter_contexto_operacional 34 OK; DEPOIS 4425 OK (195s) no head final."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): reais corrigidos -- cursor avançava com listas truncadas, borda > sem folga de relógio, carimbo ilegível ignorado quando outro era legível, ValueError na emissão."
  - "Rodada 2: reais corrigidos -- len==limite tratado como corte; falha só de regras bloqueava cursor."
  - "Rodada 3: real corrigido -- truncamento pelo limite exibido tornava o cursor inútil; mudancas agora sobre leitura ampla; total ausente tratado como truncado. Rodada 4: não achou nada."
pendencias:
  - "Configurar CONTEXT_CURSOR_SECRET no ambiente das Functions para ligar o incremental (André); similaridade vetorial real (precisa do índice vetorial)."
```

---

```yaml
pacote: "P06 sub-entrega 14/N (correção pós-merge) -- achado P2 do Codex na PR #478 (postado ~1 min antes do merge e não visto: a espera olhou reviews e checks, não review comments): com >=50 execuções em agent_runs o cursor nunca avançava. Agora o truncamento só conta com marca válida; runs só truncam se a mais antiga lida (criado_em desc) ainda é posterior à marca; primeira chamada sempre emite cursor. Limitação documentada e vira lacuna: execução antiga (fora das 50 mais recentes) alterada depois do cursor pode não aparecer em mudancas."
estado: validado
inicio: "2026-10-20T20:16:00Z"
fim: "2026-10-20T20:50:00Z"
decisoes:
  - id: p06-sub14-fix-aceita-limitacao-runs-antigas
    motivo: "Cobrir runs antigas finalizadas depois exigiria índice/query por finalizado_em; custo desproporcional agora. Preferido avançar o cursor com lacuna explícita a congelá-lo para sempre (inutiliza o recurso)."
  - id: p06-processo-checar-review-comments
    motivo: "Antes de mesclar, conferir também get_review_comments (não só reviews e check runs)."
testes:
  resultados:
    - "functions/ completo ANTES 4425 OK (main com #478); test_obter_contexto_operacional 36 OK; DEPOIS 4427 OK (190s)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): real -- run antiga finalizada depois da marca fora da janela; tratado com lacuna + documentação (decisão acima). Demais pontos sem achado."
pendencias:
  - "Ligar CONTEXT_CURSOR_SECRET (André); similaridade vetorial real."
```
