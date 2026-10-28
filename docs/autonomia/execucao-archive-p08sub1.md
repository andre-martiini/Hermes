# Arquivo: P08 sub-entrega 1/N (movido de execucao.md)

---

```yaml
pacote: "P08 sub-entrega 1/N -- núcleo puro do runner (autonomy/runner.py): interfaces PlannerModel e ToolExecutor separadas (passo 1), executar_lote (planejar -> executar -> checkpoint, termina sempre com resultado tipado; Esperar vira AGUARDANDO sem bloquear), limites de rodadas/ferramentas/tokens/duração com PAUSADO_LIMITE recuperável (nunca CONCLUIDO por limite), erros do modelo tipados (429/indisponível/timeout -> RETENTAR; recusa/contexto excedido -> FALHA), allowlist de ferramentas, saída inválida contada. Sem I/O, sem Cloud Tasks, sem Claude real: só dublês (passo 11, shadow/off)."
estado: validado
inicio: "2026-10-26T20:00:00Z"
fim: "2026-10-26T20:50:00Z"
decisoes:
  - id: p08-sub1-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela no disparo das 17h BRT. P07 segue pendente só pela decisão do André sobre o sinal de substituição; P08 depende de P04-P06 (validados), não de P07, e nasce em shadow/off, então avança sem esperar."
  - id: p08-sub1-historico
    motivo: "O histórico guarda só nome/ok/erro das ferramentas (sem dados de domínio); levar dados ao planner é decisão do wiring."
  - id: p08-sub1-lote-grande
    motivo: "Lote que sozinho excede max_ferramentas é FALHA (pausar reproduziria o mesmo plano para sempre)."
  - id: p08-sub1-arquivo
    motivo: "execucao.md perto de 50KB: bloco P07 sub 18 arquivado em execucao-archive-p07sub18.md."
testes:
  resultados:
    - "functions/ completo ANTES 4671 OK (diário, P07 sub 19); DEPOIS 4696 OK (+25 em test_autonomy_runner)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): 6 achados reais (allowlist str, lote maior que o teto em livelock, ErroModelo.tipo str, chamadas não-tupla, tokens/duração ultrapassados antes de executar) -> corrigidos. Rodada 2: 1 achado (max_duracao_segundos inf/1e20 estourava timedelta) -> corrigido. Rodada 3 sobre a correção: 1 achado menor (duração < 1 µs arredondava para 0 e pausava de imediato) -> piso de 1 ms; piso de 1 ms. Revisão do Codex na PR (2 achados P2: limites checados só depois do desfecho; texto livre do executor no histórico) -> corrigidos. Rodada 4 sobre essas correções: 1 achado (nome de ferramenta desconhecida, texto do planner, vazava no histórico/motivo) -> sanitizado; corrigido e coberto por teste; sem nova rodada (correção de uma linha reutilizando o sanitizador já revisado)."
pendencias:
  - "P08: wiring (worker HTTP autenticado, Cloud Tasks, reserva/lease via autonomy.execution, cliente Claude real com tarifas versionadas e cache de prompt, adaptador Cowork, dispatcher shadow/off). P07: decisão do André sobre o sinal de substituição."
```


# (Em 2026-10-27 o bloco "P08 sub 2" foi movido para docs/autonomia/execucao-archive-p08sub2.md.)

# (Em 2026-10-27 o bloco "P08 sub-entrega 3/N" foi movido para docs/autonomia/execucao-archive-p08sub3.md.)

# (Em 2026-10-28 o bloco "P08 sub-entrega 4/N" foi movido para docs/autonomia/execucao-archive-p08sub4.md.)

