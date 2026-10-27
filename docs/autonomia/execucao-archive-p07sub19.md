```yaml
pacote: "P07 sub-entrega 19/N -- registro de compromissos persistido por chat em sombra (passo 3, achado do Codex na PR 537): extracao_compromissos_sombra carrega o registro do chat de compromissos_chat_sombra/{chat_id}, abre as promessas firmes novas contra ele (chave repetida = reprocessamento, sem erro falso) e persiste só {chave, estado} por ArrayUnion (idempotente, sem perda em mensagens concorrentes; nunca texto; teto de 200 por chat). Falha de leitura/escrita vira flag no resumo (registro_chat_ilegivel/erro/cheio), nunca derruba o gatilho. Mesma flag da sombra de extração (padrão DESLIGADO)."
estado: validado
inicio: "2026-10-26T16:45:00Z"
fim: "2026-10-26T17:40:00Z"
decisoes:
  - id: p07-sub19-triagem
    motivo: "Nenhuma PR aberta e nenhuma execução paralela da linha de autonomia no disparo das 14h BRT."
  - id: p07-sub19-texto
    motivo: "O registro não guarda texto (princípio das sombras); ao reler, o Compromisso volta com marcador fixo 'texto nao gravado'. Suficiente para chave/estado/substituição."
  - id: p07-sub19-substituicao
    motivo: "Persistência entregue; o SINAL de substituição explícita continua inexistente e NÃO foi inventado (contrato proíbe relação por semelhança). Decisão do André pendente: (a) autorizar um sinal de modelo na extração ou (b) declarar o passo 3 atendido por independência + persistência. Sem isso pacote_concluido: P07 não é declarado."
  - id: p07-sub19-arquivo
    motivo: "execucao.md acima de ~50KB: bloco P07 sub 17 arquivado em execucao-archive-p07sub17.md."
testes:
  resultados:
    - "functions/ completo ANTES 4664 OK (main 79bbae2); DEPOIS 4671 OK (+7 em test_extracao_compromissos_sombra)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): 2 achados reais (leitura do registro só capturava exceções de dado, não de Firestore; criado_em no elemento do ArrayUnion duplicava chaves e deixava o chat ilegível) -> corrigidos. Rodada 2: 1 achado (reprocessar a mesma mensagem dava erro falso e zerava chaves) -> corrigido. Rodada 3 sobre a correção: não achou nada."
pendencias:
  - "P07 PENDENTE só pela decisão do André sobre o sinal de substituição (acima). Ativação das sombras só com aval do André. Se a decisão for (b), registrar e declarar pacote_concluido: P07; o próximo é o P08 (runner Claude, shadow/off)."
```
