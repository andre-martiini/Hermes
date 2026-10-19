# Arquivo: P05 sub-entrega 19/N (conclusão) e P06 sub-entrega 5/N

Movidos de execucao.md em 2026-10-19 pela tarefa agendada de avanço autônomo (P06 sub-entrega 10/N), preventivamente: arquivo ativo em ~50KB. Ambos com `estado: validado`; conteúdo inalterado.

```yaml
pacote: "P05 sub-entrega 19/N (conclusão) -- PR #429 atualizada com main em sessão Claude Code cloud com git completo (conector GitHub): merge de origin/main na branch claude/p05-sub19-reconciliacao-outbox-wiring, conflitos só nos 2 arquivos de diário (resolvidos tomando a versão de main; o arquivo execucao-archive-p05sub18.md de main já existia), atencao.py e event_outbox.py mesclaram sem conflito. Linha `from event_outbox import varrer_outbox_travado` registrada em functions/main.py (pendência crítica do bloco original da sub-entrega 19/N, antes impossível por limite de tamanho da tool de escrita do Argos). Removido também functions/_scratch_nbsp_test.py (arquivo vazio esquecido em main desde 17/10)."
estado: validado
inicio: "2026-10-18T13:00:00Z"
fim: "2026-10-18T13:30:00Z"
decisoes:
  - id: p05-sub19-main-py-registrado-via-git-direto
    motivo: "Sessão com clone git completo e conector GitHub permite editar main.py (~725KB) com patch de 6 linhas, sem a limitação da tool argos_escrever_arquivo_repositorio."
    autoridade: andre-solicitou-na-sessao-de-18-10-2026
testes:
  resultados:
    - "functions/ completo, rodado de dentro de functions/: 4140 testes, OK (inclui test_event_outbox e test_atencao: 71 OK)."
    - "Fechamento em 2026-10-18 (14h UTC): functions/ completo ANTES 4140 OK, DEPOIS 4141 OK (+1 teste de regressão da precondição); test_event_outbox 24 OK. Checks do GitHub verdes no head a03e7bb. PR #429 MESCLADA (merge commit 7ecd1e8)."
revisao_adversarial:
  - "Rodada 1 (foco no merge com main, linha em main.py e efeito de registrar a scheduled function): achado REAL -- varrer_outbox_travado_core gravava com update() incondicional sobre snapshot possivelmente antigo, podendo sobrescrever estado/tentativas de entrada reivindicada ou concluída por outro worker (latente: nenhum consumidor real chama iniciar_despacho ainda). Corrigido com precondição last_update_time (db.write_option) e FailedPrecondition tratado como 'pular'."
  - "Rodada 2: código de produção correto; teste novo era fraco (passaria sem a precondição). Reforçado: o fake registra o option recebido e levanta FailedPrecondition se não bater; mutação (remover a precondição) agora derruba 2 testes."
  - "Rodada 3: não achou nada."
pendencias:
  - "Verificar no próximo deploy que a scheduled function varrer_outbox_travado (a cada 15 min) foi publicada e roda sem erro; reconciliação só toca outbox_eventos em em_processamento com lease vencida."

---
pacote: "P06 sub-entrega 5/N -- passo 10 (relatório de memória suspeita), parte pura: functions/autonomy/memoria_suspeita.py. Sem I/O e sem tocar em main.py: dado um documento de knowledge_nodes, devolve sinais com evidência (campo + trecho) para REVISÃO HUMANA -- nunca apaga, rebaixa nem supera nada (aceite do passo 10: saneamento só por revisão com evidência). Sinais: sem_proveniencia (legacy_unknown), inferencia_como_regra_global, telemetria_como_fato, superada_sem_sucessor, possivel_injecao (padrões estritos de ordem ao modelo, em todos os campos de texto lidos por consumidores reais; NFKC + remoção de caracteres Unicode Cf; negação colada ao padrão não conta). Documento superada também é varrido por injeção porque main._build_memory_context injeta texto sem filtrar memoria_status."
estado: validado
inicio: "2026-10-18T14:20:00Z"
fim: "2026-10-18T15:10:00Z"
decisoes:
  - id: p06-sub5-so-logica-pura
    motivo: "Mesmo padrão incremental de context.py/temporal.py: classificação testável sem Firestore primeiro. A consulta real (varredura paginada de knowledge_nodes) e a exposição como tool/relatório ficam para sub-entrega seguinte, que também decide o destino do relatório."
  - id: p06-sub5-falso-positivo-aceito
    motivo: "Frases legítimas de regra com negação não colada ('você não deve ignorar as instruções anteriores') ou de revogação ('ignorar as regras anteriores') ainda geram uma linha a revisar; custo aceito (relatório é para revisão humana), documentado no módulo."
testes:
  resultados:
    - "test_memoria_suspeita: 33 testes OK (novo arquivo). functions/ completo ANTES 4141 OK, DEPOIS 4173 OK no head 9bfbfc9 (+ 1 teste adicionado depois, 4174 esperado no head final; só testes/docstring mudaram entre os dois)."
revisao_adversarial:
  - "Rodada 1: injeção só no primeiro campo; evidência com campo errado; falsos positivos (system prompt solto, 'deve obedecer'); testes que sobreviviam a mutações -- corrigidos."
  - "Rodada 2: evidência truncada sem conter o casamento; superada não varrida; negação; unicode; doc_id não-string -- corrigidos."
  - "Rodada 3: negação mascarando injeção em outra linha/meio de palavra; variantes com possessivo; caracteres Cf -- corrigidos."
  - "Rodada 4: só falso positivo já aceito (negação com auxiliar). Sem achado real."
  - "PR #463 MESCLADA em 2026-10-18 (merge commit 64205c8); checks do GitHub verdes no head 2ed4a91; thread do Codex resolvida."
  - "Codex (PR #463): P2 real -- remover caractere Cf colava palavras (ignore\u200bas) e escondia a injeção; corrigido varrendo as duas variantes (removido e trocado por espaço). Revisão adversarial focada: só lacuna de teste (variante removida e negação com Cf), corrigida; limitação residual documentada (Cf dentro da palavra E no lugar do espaço)."
pendencias:
  - "Sub-entrega seguinte do passo 10: varredura paginada real de knowledge_nodes + destino do relatório (fila de atenção ou tool somente leitura)."

---
```
