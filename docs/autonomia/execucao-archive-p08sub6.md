# Arquivo: bloco P08 sub 6 (movido de execucao.md em 2026-10-28)

```yaml
pacote: "P08 sub-entrega 6/N -- autorização do worker (autonomy/worker_auth.py, passo 2): função pura autorizar_chamada_worker(claims, headers, config, agora). Claims OIDC já verificados pelo wiring; exige emissor Google, audience exata do worker, exp futuro e finito, e-mail verificado ASCII igual à conta de serviço configurada e cabeçalho X-CloudTasks-QueueName igual à fila configurada. Fail-closed (config inválida/tipos hostis nunca autorizam); motivo é código fixo que não ecoa o token. Sem I/O (shadow/off)."
estado: validado
inicio: "2026-10-28T10:49:00Z"
fim: "2026-10-28T11:30:00Z"
decisoes:
  - id: p08-sub6-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela da linha de autonomia no disparo das 8h BRT."
  - id: p08-sub6-verificacao-token
    motivo: "A verificação criptográfica do JWT (assinatura/exp) fica no wiring (google.oauth2.id_token); a função só decide sobre claims, com exp conferido de novo como defesa em profundidade."
  - id: p08-sub6-arquivo
    motivo: "execucao.md no limite de ~50KB: bloco P08 sub 4 arquivado em execucao-archive-p08sub4.md."
testes:
  resultados:
    - "functions/ completo ANTES 4862 OK (diário, P08 sub 5; main atual 4863); DEPOIS 4872 OK (+9 em test_autonomy_worker_auth)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): 1 achado real (iss não hashable levantava TypeError) e 2 menores (e-mail com U+212A casava via lower(); exp=inf nunca expirava) -> corrigidos e cobertos por teste. Codex na PR: 1 achado P2 (exp inteiro gigante, 10**1000, estourava OverflowError em math.isfinite -- regressão da minha correção) -> corrigido com try/except e coberto por teste. Sem rodada 2: lógica pura, correções de poucas linhas cobertas por teste."
pendencias:
  - "P08: wiring (worker HTTP verificando o JWT e chamando autorizar_chamada_worker, Cloud Tasks real tratando ALREADY_EXISTS como duplicata, reserva/lease via autonomy.execution com CAS aplicando a DecisaoContinuacao, cliente Claude real consumindo ConfigModelos, leitura da flag do modo e do orçamento de despachos, IAM mínimo da conta de serviço)."
```
