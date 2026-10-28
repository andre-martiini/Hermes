# Arquivo: bloco P08 sub 4 (movido de execucao.md em 2026-10-28)

```yaml
pacote: "P08 sub-entrega 4/N -- adaptador de consumo Cowork (autonomy/executor_cowork.py, passo 10): CapacidadesExecutor (runner_servico ou cowork, ids 'cowork:<rotina>' reservados ao Cowork, regex de id, só capacidades DECLARADAS -- nunca herdadas entre tipos), capacidades_faltantes e reservar_pedido_para_executor (checagem prévia de capacidade sem tocar o pedido; depois a MESMA reserva de assumir_pedido: lease, geração, run). Perder a disputa vira DisputaPerdida; faltar capacidade vira CapacidadeInsuficiente. Sem I/O (shadow/off, passo 11)."
estado: validado
inicio: "2026-10-27T17:00:00Z"
fim: "2026-10-27T17:40:00Z"
decisoes:
  - id: p08-sub4-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela da linha de autonomia no disparo das 14h BRT."
  - id: p08-sub4-cas
    motivo: "Função pura: dois executores partindo do MESMO snapshot pendente reservam ambos em memória; a exclusão real é compare-and-set por geração/status na gravação (wiring Firestore). Documentado na docstring e coberto por teste."
  - id: p08-sub4-arquivo
    motivo: "execucao.md no limite de ~50KB: bloco P08 sub 2 arquivado em execucao-archive-p08sub2.md."
testes:
  resultados:
    - "functions/ completo DEPOIS 4847 OK (inclui +14 em test_autonomy_executor_cowork). ANTES: 4741 no diário (P08 sub 3); main atual rende 4833 (4847-14), pois PRs #541/#542 acrescentaram testes depois."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): achados reais (id vazio após prefixo, runner com 'COWORK:'/unicode/controles, duracao_segundos inf/nan, tipos errados sem TypeError, disputa sem exceção própria, faltantes mutável) -> corrigidos e cobertos por teste; snapshot concorrente documentado. Rodada 2 sobre a correção: 2 achados menores (int gigante vazava OverflowError na checagem de duração -> corrigido com checagem de faixa só; DisputaPerdida também cobre retentativa antes da hora -> documentado). Sem rodada 3: lógica pura, correções de uma linha cobertas por teste."
pendencias:
  - "P08: wiring (worker HTTP autenticado, Cloud Tasks, reserva/lease via autonomy.execution com CAS aplicando a DecisaoContinuacao, cliente Claude real consumindo ConfigModelos, cache de prompt (passo 9), dispatcher shadow/off). Confirmar que os ids reais de runners cabem no regex [A-Za-z0-9_.:-]{1,100}."
```
