```yaml
pacote: "P08 sub-entrega 8/N -- sweep de espera/verificação vencida (autonomy/sweep.py, passo 5-6): nova varrer_espera_vencida: AGUARDANDO_EXTERNO (com lease vencida E horário de acordar alcançado/ausente) ou VERIFICANDO (lease vencida) -> RESULTADO_DESCONHECIDO (única saída do grafo sem lease; reconciliação via VERIFICANDO), sem reexecutar (retentar VERIFICANDO às cegas poderia duplicar efeitos), sem incrementar tentativas, condicao_espera preservada, run ativo fechado por timeout, diagnóstico devolvido. Lease vencida ANTES do horário de acordar é espera normal e levanta ValueError. Sem I/O (shadow/off)."
estado: validado
inicio: "2026-10-28T16:47:00Z"
fim: "2026-10-28T17:35:00Z"
decisoes:
  - id: p08-sub8-triagem
    motivo: "Única PR aberta (#547, melhorias, outra linha) estava trivial, sem conflito e com CI verde: mesclada. Nenhuma PR da autonomia pendente."
  - id: p08-sub8-arquivo
    motivo: "execucao.md no limite de ~50KB: bloco P08 sub 5 arquivado em execucao-archive-p08sub5.md."
  - id: p08-sub8-espera
    motivo: "Escolha segura sem decisão de produto: espera externa que ninguém acordou vira RESULTADO_DESCONHECIDO (reconciliar), nunca retentativa automática. AGUARDANDO_APROVACAO segue fora de escopo (prazo de espera humana é decisão do André)."
testes:
  resultados:
    - "functions/ completo ANTES 4890 OK (diário, P08 sub 7); DEPOIS 4902 OK (+8 em test_autonomy_sweep; o restante vem de merges de outras linhas)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto, somente leitura): não achou nada. Codex na PR #550: 1 achado P1 real -- a 1a versão mandava VERIFICANDO vencido a RETENTATIVA_AGENDADA, o que reexecutaria o pedido e poderia duplicar efeito já feito; corrigido (VERIFICANDO vencido vai a RESULTADO_DESCONHECIDO, varrer_lease_vencida volta a recusá-lo) e coberto por teste. Rodada 2 (agente sem contexto, focada na correção): não achou nada (2 nits de documentação, 1 aplicado)."
pendencias:
  - "P08: wiring (worker HTTP verificando JWT, Cloud Tasks real tratando ALREADY_EXISTS, persistência/CAS chamando decidir_continuacao + aplicar_decisao_continuacao e o sweep, renovar lease ao acordar de AGUARDANDO_EXTERNO, RESULTADO_DESCONHECIDO sem saída no sweep (reconciliação), AGUARDANDO_APROVACAO vencida (prazo a definir pelo André), cliente Claude real com ConfigModelos, cache de prompt, flag do modo e orçamento de despachos, IAM mínimo)."
```
