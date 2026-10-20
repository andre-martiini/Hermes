# Arquivo: P06 sub-entregas 8/N e 9/N (movidas de execucao.md em 2026-10-20, sem alteração de conteúdo; ambas `estado: validado`)

```yaml
pacote: "P06 sub-entrega 8/N -- passo 8, mapa de POPs (parte pura): functions/autonomy/pops_mapa.py. montar_mapa_pops(pops, ids_carregados) devolve todos os POPs com instrução marcando carregado/alcançável (sempre ativo ou com gatilho útil), os sem instrução e os ignorados. Sem I/O, sem wiring em main.py (o carregamento atual -- sempre ativos + 3 por gatilho -- não muda)."
estado: validado
inicio: "2026-10-19T10:50:00Z"
fim: "2026-10-19T11:20:00Z"
decisoes:
  - id: p06-sub8-so-logica-pura
    motivo: "Mesmo padrão incremental de context.py/memoria_suspeita.py. Ligar o mapa a obter_contexto_operacional (passo 6) e decidir se o teto de 3 POPs por gatilho muda ficam para sub-entrega seguinte, com decisão de produto."
  - id: p06-sub8-semantica-do-matcher
    motivo: "Mapa espelha main._match_pop_directives: id comparado cru, sempre_ativo só com True literal, gatilho contado como str(); id repetido vale a primeira ocorrência (demais em ignorados)."
  - id: p06-sub8-triagem
    motivo: "Nenhuma PR aberta no início do disparo; nada a mesclar/fechar."
testes:
  resultados:
    - "functions/ completo ANTES 4249 OK (207s); test_pops_mapa 14 OK (novo arquivo); DEPOIS 4258 OK (+9 testes de test_pops_mapa; 4255 OK antes da rodada 3 de correções)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): id com espaço divergia do matcher, n_gatilhos divergia (str()), POP inalcançável não sinalizado, testes fracos contra mutações -- corrigidos (campo alcancavel, 6 testes novos)."
  - "Rodadas 2 e 3: gatilho só de pontuação (normalização do matcher), POP sem gatilho; restaram só bordas de id duplicado (impossível no Firestore) -- política única documentada (primeira ocorrência, demais ignoradas). Sem bug no caso normal."
pendencias:
  - "Passos 5-7 (recuperação, obter_contexto_operacional/consultar_memoria_contextual, cursor) e passo 9 (modelo por pessoa); ligar o mapa ao contexto."

---
pacote: "P06 sub-entrega 9/N -- passo 7 (parte pura), cursor de contexto incremental: functions/autonomy/cursor_contexto.py. emitir_cursor/validar_cursor produzem cursor opaco assinado (HMAC-SHA256) vinculado a owner_uid + escopo + marca monotônica; outro dono/escopo, outro segredo, adulteração, versão ou formato inválidos levantam CursorInvalido. Segredo por parâmetro, sem I/O, sem wiring em main.py nem tool nova."
estado: validado
inicio: "2026-10-19T13:50:00Z"
fim: "2026-10-19T14:15:00Z"
decisoes:
  - id: p06-sub9-so-logica-pura
    motivo: "Mesmo padrão incremental das sub-entregas 6-8; ligar o cursor a obter_contexto_operacional (passo 6) exige contrato P03 e decisão de onde vem o segredo."
  - id: p06-sub9-triagem
    motivo: "PR #469 (Transcrição ao vivo 1/3, avulsa do André, aberta há minutos, cria Cloud Function nova e pede 'não mesclar automaticamente') não é desta linha: não tocada."
testes:
  resultados:
    - "functions/ completo ANTES 4258 OK; test_cursor_contexto 15 OK (novo arquivo); DEPOIS 4273 OK (+15)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): sem bypass de vínculo/forja. Reais corrigidos: emitir aceitava cursor que validar recusaria (limite de 2048) -- agora ValueError; testes do limite e do ValueError do chamador adicionados."
pendencias:
  - "Passos 5-6 (recuperação, obter_contexto_operacional/consultar_memoria_contextual, que consumirão este cursor) e passo 9 (modelo por pessoa)."

---
```
