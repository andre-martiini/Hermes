# Arquivo: P06 sub-entregas 12/N e 13/N (movidas de execucao.md em 2026-10-21, sem alteração de conteúdo)

```yaml
pacote: "P06 sub-entrega 12/N -- passo 6 (parte de leitura, 2/2), tool MCP SOMENTE LEITURA obter_contexto_operacional (functions/tools/obter_contexto_operacional.py): pendências abertas (atencao.coletar_fila_atencao), últimos resultados de rotinas (agent_runs.listar_recentes) e POPs (pops_diretrizes via autonomy.pops_mapa) -- sempre ativos com instrução inteira, os demais só título/n_gatilhos. Cada fonte é lida isolada: falha vira fontes[nome]='falhou (...)' + lacunas, sem derrubar as outras. Registrada em registry/inventory/schema, fora do canal de voz."
estado: validado
inicio: "2026-10-20T10:50:00Z"
fim: "2026-10-20T11:20:00Z"
decisoes:
  - id: p06-sub12-sem-cursor
    motivo: "Cursor incremental (passo 7) segue pendente: exige segredo de assinatura de origem indefinida; a tool é aditiva e reversível."
  - id: p06-sub12-instrucao-inteira
    motivo: "Achado da revisão: cortar a instrução de POP sempre ativo em 400 chars entregaria restrição crítica pela metade como se completa; instrução vai inteira (o sistema já a injeta inteira), demais textos cortados em 400."
  - id: p06-sub12-triagem
    motivo: "Nenhuma PR aberta no início do disparo; nada a mesclar/fechar. execucao.md arquivado (blocos P06 sub 6 e 7)."
testes:
  resultados:
    - "functions/ completo ANTES 4365 OK (head de main, registro da sub 11/N); test_obter_contexto_operacional 13 OK (novo arquivo); DEPOIS 4390 OK (222s) no head final (test_obter_contexto_operacional 16 OK)."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): reais corrigidos -- instrução de POP truncada sem lacuna, finalizado_em preenchido com criado_em em execução em andamento, valores não-string passando sem limite; testes de POP malformado, sempre_ativo truthy e limite reforçados."
  - "Rodadas 2 e 3 (agentes sem contexto): reais corrigidos -- id de POP repetido (primeira ocorrência, como o mapa), id não hashável derrubando todas as regras, campos não-string sem limite, total inválido; sem outro achado nas correções. Rodada 4: não achou nada."
pendencias:
  - "Passo 7 (cursor assinado + contexto incremental), similaridade vetorial real, passo 9 (modelo por pessoa)."

---
pacote: "P06 sub-entrega 13/N -- passo 9, guarda do modelo por pessoa: functions/autonomy/modelo_pessoa_guarda.py (puro). sanear_modelo_interacao descarta, campo a campo, texto do modelo_interacao (gerado por LLM) que infira traço sensível (saúde, religião, política, orientação sexual, etnia, deficiência, sindical, financeiro/judicial) ou acesso por perfil, devolvendo os descartes (campo/categoria, sem o texto). Ligado em main.parse_resposta_modelo_pessoa; regra 3 nova no prompt de geração. Nenhum código usa modelo_interacao para conceder acesso (só leitura em buscar_contato)."
estado: validado
inicio: "2026-10-20T13:50:00Z"
fim: "2026-10-20T14:40:00Z"
decisoes:
  - id: p06-sub13-melhor-esforco
    motivo: "Lista de termos é defesa em profundidade, não exaustiva; a barreira primária é o prompt. Termos ambíguos com uso administrativo comum (voto em colegiado, vício de forma, dívida ativa, sindicato, igreja/pastoral, 'tem acesso', trans solto, Serasa/SPC) ficam de fora de propósito para não apagar conteúdo legítimo."
  - id: p06-sub13-triagem
    motivo: "Nenhuma PR aberta no início do disparo; nada a mesclar/fechar."
testes:
  resultados:
    - "functions/ completo ANTES 4390 OK (217s, head de main); test_modelo_pessoa_guarda 17 OK (novo arquivo) + test_modelo_pessoa sem regressão; DEPOIS 4406 OK (219s) no head final."
revisao_adversarial:
  - "Rodada 1 (agente sem contexto): reais corrigidos -- flexões/vocabulário, caractere invisível Cf, falsos positivos (partido, raça, acesso a, autorização), tipos não-string."
  - "Rodada 2: reais corrigidos -- falsos positivos de vot*, vício, dívida, sindicato, processo criminal, igreja/pastor; verbos de permissão; vocabulário extra; homóglifos cirílicos/gregos."
  - "Rodada 3: reais corrigidos -- falsos positivos de 'e preta/pardo', trans solto, Serasa/SPC, 'e de esquerda', PL, covid, internado, crente, tem acesso, cadeira de rodas, esta preso (todos removidos/estreitados, só reduz descartes). Codex (PR #477): P1 real (modelos já gravados escapavam da guarda pelo early-return do hash; agora também sanados na leitura de buscar_contato) + 2 P2 (acesso e etnia, padrões ampliados). Rodada 4 (agente sem contexto): falsos positivos novos (pode aprovar contrato, a tinta é negra, senhor negro Ltda) corrigidos exigindo sujeito pessoal (ele/ela/contato/pessoa ou início do texto) e removendo o objeto contrato de autorizado-a; sem regressão em _buscar_contato."
pendencias:
  - "Passo 7 (cursor assinado + contexto incremental; origem do segredo indefinida), similaridade vetorial real."
```
