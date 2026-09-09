# Registro de execução — plano-hermes-autonomo-2026-09-06

Um bloco por pacote (P00–P18), no formato da seção 14.2 do plano. Cada pacote novo é acrescentado ao final; nenhum bloco anterior é reescrito depois de `validado`. Sem segredos nem conteúdo privado — apenas referências a artefatos e IDs.

**Blocos P00 a P02 sub-entrega 10/N-11/N (catch-up) foram movidos para
docs/autonomia/execucao-archive-p00-a-p02sub11.md em 2026-09-09** (P02
sub-entrega 15/N) por um limite técnico real de tamanho de escrita via
Argos MCP — ver o cabeçalho do arquivo de arquivo para o motivo completo.
Nenhum conteúdo foi perdido; é uma relocação, não uma edição. Este arquivo
continua sendo a fonte de verdade para tudo a partir daqui.

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 054a748dada12fe5753c7f192ef02f7352bbe5c3
pacote: "P02 sub-entrega 12/N -- decisao_piso()/_decisao_piso_mcp protegidas contra falha em avaliar() (fail-closed em vez de propagar exceção)"
# Continuação autônoma autorizada por André ("Pode adiantar o início do
# próximo módulo para agora"), a partir do achado não-bloqueante já
# registrado desde a sub-entrega 8/N (p02-sub8-achado-nao-bloqueante-avaliar-sem-protecao):
# na época, decisao_piso() não tinha nenhum consumidor real fora dos
# testes, então o risco era teórico. Desde as sub-entregas 9/N (mcp_jobs.py)
# e 10/N (confirm_whatsapp do Telegram), decisao_piso() e _decisao_piso_mcp
# (mcp_server.py, consumidor real desde a sub-entrega 2/N) têm consumidores
# reais -- o gatilho que a pendência original previa para endereçar isto.
estado: pronto_para_revisao
inicio: "2026-09-08T17:30:00Z"
fim: "2026-09-08T18:18:16Z"
arquivos_alterados:
  - functions/autonomy/policy.py (nova função decisao_erro_avaliacao(); decisao_piso() chama avaliar() dentro de try/except)
  - functions/mcp_server.py (_decisao_piso_mcp chama autonomy_policy.avaliar() dentro de try/except, mesma correção; registrar_decisao também protegida por try/except próprio)
  - functions/test_policy.py (testes de decisao_erro_avaliacao() isolada + testes do guard em decisao_piso(), via mock.patch)
  - functions/test_mcp_server.py (testes equivalentes para _decisao_piso_mcp, achado da revisão adversarial -- ver evidências)
decisoes:
  - id: p02-sub12-deny-nao-require-approval-nem-prepare-only
    motivo: "decisao_erro_avaliacao() sempre retorna Decisao.DENY, nunca SOMENTE_PREPARACAO/PREPARE_ONLY nem REQUIRE_APPROVAL. Raciocínio (documentado na própria docstring da função): uma falha de avaliação INTERNA (exceção dentro de avaliar(), não um estado de autonomia restrito) não é a mesma coisa que \"autonomia está pausada/em preparação\" -- usar PREPARE_ONLY faria um erro interno se disfarçar de estado normal do sistema. REQUIRE_APPROVAL também foi rejeitado por ser a decisão de SUCESSO normal do piso -- usá-la para um erro faria a chamada parecer \"tudo bem, só precisa da confirmação de sempre\", escondendo que algo quebrou."
    autoridade: existente_ou_nova
  - id: p02-sub12-descoberta-veio-do-piso-nao-toca-principal
    motivo: "Descoberta ao escrever o teste de regressão (registrada honestamente, não escondida): avaliar() só acessa request.principal no ramo NÃO-piso (veio_do_piso=False) -- o ramo do piso decide sem tocar principal (só o passo 6, estado_autonomia, é consultado). Como decisao_piso()/_decisao_piso_mcp só chamam avaliar() com classe_efeito vindo de CLASSE_EFEITO_PISO, e hoje CLASSE_EFEITO_PISO tem exatamente as mesmas chaves de FLOOR_CONFIRMACAO_OBRIGATORIA (travado por novo teste, test_classe_efeito_piso_cobre_exatamente_o_floor), toda chamada por estes dois caminhos reais cai no ramo do piso -- ou seja, um principal malformado NÃO derruba avaliar() hoje por este caminho específico. Esta correção é defesa em profundidade contra as duas tabelas divergirem no futuro (são mantidas separadamente por design), não a correção de um crash ao vivo. Os testes de regressão usam mock.patch.object(avaliar, side_effect=...) em vez de um principal malformado de verdade, porque um principal malformado de verdade não reproduz a falha hoje."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "Antes da mudança: 1369/1369."
    - "Depois da mudança + achado da revisão adversarial corrigido: 1373/1373, 0 falhas, 0 erros."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre o diff dos 4 arquivos. Achado único: nenhuma cobertura de teste para a mesma correção em mcp_server.py::_decisao_piso_mcp -- todos os testes novos cobriam só autonomy.policy.decisao_piso(). Corrigido: dois testes adicionados a test_mcp_server.py::TestDecisaoPisoMcp (falha em avaliar() bloqueia com DENY; falha em avaliar() não impede registrar_decisao de ser tentado). A revisão também confirmou, de forma independente, o raciocínio de p02-sub12-descoberta-veio-do-piso-nao-toca-principal, a fail-safety pré-existente de registrar_decisao(), e a ausência de risco de regressão em quem consome PolicyDecision (callers ramificam pelo enum Decisao, nunca pelo reason_code string). Um nit cosmético (espaçamento de linha em branco) foi apontado e deliberadamente não corrigido -- sem efeito funcional, sem lint configurado para isso."
  - "4 commits verificados individualmente por hash antes de prosseguir: autonomy/policy.py (commit 4ddef30414f5b37c7bdc2c2bebe08934f2133fbc, sha 6a7b9fcd4178105e9d44bb191a3a8a3638203a18), mcp_server.py (commit fe120fceb941d666e0ecb95644c3adb3419a59c1, sha c7ee3dff1d37307702ab3072c289e75c994e6215), test_policy.py (commit 800d99b902170d84f26c8e6b28665dfb5c4f608a, sha 9ea1f66d504be068d97c2aed1a29f7526b29a9f1), test_mcp_server.py (commit 9490e05352f1fc4f1e2626059d04b028fce25689, sha d19b7534b355976217991539397d2d3f7bccc76c) -- todos batendo exatamente no primeiro envio."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: a pendência não-bloqueante registrada desde a sub-entrega 8/N (p02-sub8-achado-nao-bloqueante-avaliar-sem-protecao) -- decisao_piso()/avaliar() agora protegida contra falha de avaliação, nos dois consumidores reais (autonomy.policy.decisao_piso e mcp_server._decisao_piso_mcp)."
  - "Novo, não-bloqueante: a garantia de que um principal malformado nunca derruba avaliar() por este caminho depende inteiramente de CLASSE_EFEITO_PISO e FLOOR_CONFIRMACAO_OBRIGATORIA continuarem tendo exatamente as mesmas chaves -- travado por teste (test_classe_efeito_piso_cobre_exatamente_o_floor), mas se essa invariante um dia quebrar, o guard fail-closed desta sub-entrega passa a ser a ÚNICA proteção real contra um principal malformado quebrar decisao_piso()/_decisao_piso_mcp."
  - "Duplicação entre autonomy/policy.py::decisao_piso() e mcp_server.py::_decisao_piso_mcp permanece (pendência já registrada desde a sub-entrega 6/N) -- a correção desta sub-entrega foi aplicada duas vezes, manualmente, exatamente por causa dessa duplicação; não endereçada agora para não mexer em caminho de código sensível já testado nos dois lados."
  - "Todas as pendências já registradas nos blocos anteriores que não foram tocadas por esta sub-entrega continuam abertas: passo 1 do plano parcialmente aberto (outbox_aprovacao.py/revisao_semanal.py sem Principal), risco de bare-name-resolution nos módulos de área, validação de tipo de PolicyRequest.orcamento_restante no wrapper MCP, Mandato.classes_conteudo_permitidas texto livre sem enum fechado, Mandato.usos_na_janela_atual/orcamento_maximo sem wrapper de I/O real, bug de tipo em preparar_politica, pergunta de design sobre o default de origem_humana."
proximo_pacote: "P02 -- a decidir com André: religar outbox_aprovacao.py/revisao_semanal.py a Principal/decisao_piso() (passo 1 do plano, escopo há duas sub-entregas deliberadamente deixado de fora), resolver a duplicação entre decisao_piso() e _decisao_piso_mcp, ou revisitar a lista de pendências acumuladas para levar ao André antes de mais trabalho autônomo."
```


---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: aa4254d08837b49f2ac7100a4bc165e2fad0a21d
pacote: P02
estado: pronto_para_revisao
inicio: "2026-09-08T18:30:00Z"
fim: "2026-09-08T19:53:00Z"
arquivos_alterados:
  - functions/autonomy/policy.py (docstring de decisao_piso() registra a delegação; sem mudança funcional)
  - functions/mcp_server.py (_decisao_piso_mcp delega para autonomy_policy.decisao_piso() no caminho feliz)
  - functions/test_mcp_server.py (2 testes novos: a delegação em si e o fallback quando ctx.db falha)
decisoes:
  - id: p02-sub13-delegacao-decisao-piso
    motivo: "Duplicação registrada desde a sub-entrega 6/N e que custou aplicar a correção fail-closed da sub-entrega 12/N duas vezes, manualmente. _decisao_piso_mcp agora delega para autonomy_policy.decisao_piso(db, principal, nome, argumentos) no caminho feliz (quando ctx.db resolve sem lançar). A única razão legítima para _decisao_piso_mcp continuar existindo como função própria: ctx.db é uma property lazy que pode lançar na própria inicialização (ex.: \"The default Firebase app does not exist\") -- falha que decisao_piso() não precisa tratar, já que recebe db como argumento já resolvido."
    autoridade: existente_ou_nova
  - id: p02-sub13-simplificacao-fallback-ctx-db
    motivo: "Quando ctx.db falha, o código antigo fazia uma segunda tentativa condenada de ctx.db dentro do próprio try/except de registrar_decisao (sempre falhando de forma idêntica, nunca produzindo registro). O código novo pula essa segunda tentativa -- simplificação inofensiva, documentada e coberta por test_ctx_db_indisponivel_cai_em_somente_preparacao_sem_registrar."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover"
  resultado: "1369 -> 1371 (baseline pré-refatoração medido diretamente via git stash, não o número documentado antes; refatoração acrescentou exatamente 2 testes, sem outra oscilação)"
evidencias:
  - "Revisão adversarial independente (subagente general-purpose sem contexto da implementação, dispatado antes do PR): nenhum problema bloqueante encontrado; confirmado que todo caminho de _decisao_piso_mcp termina em DENY/PREPARE_ONLY/REQUIRE_APPROVAL, nunca ALLOW nu."
  - "3 commits verificados individualmente por hash antes de prosseguir: autonomy/policy.py (commit e6a37c8f96dfcb98e8eddb043307e82e0d2e4609, sha f2e16910a1bdf564901c7718f3595af4b7c2e8ce), mcp_server.py (commit c8b4e892453412b6940e192fda68c859b7dd098e, sha f1e55b931618cae21a2244dd73913cb581dc9392), test_mcp_server.py (commit 4e78fd1bdae9b250c01ea0ed818018c621f9e13f, sha 732dcc20d377719401b2f69518b981898b01f621) -- todos batendo exatamente no primeiro envio, cadeia de parents conferida."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: a duplicação entre autonomy/policy.py::decisao_piso() e mcp_server.py::_decisao_piso_mcp, registrada desde a sub-entrega 6/N."
  - "Todas as pendências já registradas nos blocos anteriores que não foram tocadas por esta sub-entrega continuam abertas: passo 1 do plano parcialmente aberto (outbox_aprovacao.py/revisao_semanal.py sem Principal), risco de bare-name-resolution nos módulos de área, validação de tipo de PolicyRequest.orcamento_restante no wrapper MCP, Mandato.classes_conteudo_permitidas texto livre sem enum fechado, Mandato.usos_na_janela_atual/orcamento_maximo sem wrapper de I/O real, bug de tipo em preparar_politica, pergunta de design sobre o default de origem_humana, dependência de CLASSE_EFEITO_PISO/FLOOR_CONFIRMACAO_OBRIGATORIA continuarem com as mesmas chaves (travado por teste, mas não uma garantia estrutural)."
proximo_pacote: "P02 -- a decidir com André: religar outbox_aprovacao.py/revisao_semanal.py a Principal/decisao_piso() (passo 1 do plano, escopo há várias sub-entregas deliberadamente deixado de fora -- decisão de produto/design, não só engenharia), ou revisitar a lista de pendências acumuladas para levar ao André antes de mais trabalho autônomo."
```


---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 9bf088faf0cf24033872f134b1376fca265ce2e6
pacote: "P02 sub-entrega 14/N -- validação de tipo no motor de política: preparar_politica() (motor puro) e orcamento_restante (wrapper MCP de simular_politica)"
# Continuação autônoma autorizada por André ("Mantenha a criação dos
# próximos módulos com intervalo de 1 hora, por favor.") -- disparada por
# lembrete agendado 1h após o envio da sub-entrega 13/N. Escolhida entre as
# pendências acumuladas por serem as duas únicas puramente de engenharia
# (sem decisão de produto/design pendente), ambas já tinham a correção
# adiada explicitamente "para quando autonomy/policy.py ou hermes_tools.py
# forem revisitados por outro motivo" -- este é esse motivo.
estado: pronto_para_revisao
inicio: "2026-09-08T21:30:00Z"
fim: "2026-09-08T22:20:00Z"
arquivos_alterados:
  - functions/autonomy/policy.py (preparar_politica() agora valida o tipo de ferramentas_com_confirmacao_obrigatoria antes de construir o set(), em vez de confiar só na validação da wrapper MCP)
  - functions/tools/hermes_tools.py (_policy_request_simulado valida orcamento_restante é numérico antes de construir o PolicyRequest, reportando erro por índice em vez de abortar o lote inteiro)
  - functions/test_policy.py (6 testes novos em TestPrepararPolitica)
  - functions/test_hermes_tools.py (3 testes novos em TestFerramentasDePolitica)
decisoes:
  - id: p02-sub14-preparar-politica-corrige-o-motor-nao-so-a-wrapper
    motivo: "Achado real da revisão adversarial da sub-entrega 3/N (registrado, nunca corrigido no motor até agora): `set(politica_proposta.get(\"ferramentas_com_confirmacao_obrigatoria\", atual))` sem checar tipo -- uma STRING em vez de lista é iterada caractere por caractere pelo set(), produzindo um diff que parece válido (\"remover as 5 tools reais do piso, adicionar um bando de letras soltas\") sem erro nenhum, exatamente na função cujo propósito é proteger o piso de confirmação obrigatória. A wrapper MCP (_preparar_politica) já validava antes de chamar o motor desde a sub-entrega 3/N -- essa defesa continua no lugar, inalterada. Esta sub-entrega fecha o motor puro também, para qualquer chamador direto (teste, script, futuro segundo consumidor) que não passe pela wrapper. Aceita list/tuple/set/frozenset de strings (não só list) -- nenhum chamador real depende do tipo específico da coleção de entrada, e o retorno é sempre uma lista ordenada independente do tipo recebido."
    autoridade: existente_ou_nova
  - id: p02-sub14-none-explicito-tratado-igual-a-ausente
    motivo: "Achado da revisão adversarial desta própria sub-entrega: chave PRESENTE com valor None (ex.: {\"ferramentas_com_confirmacao_obrigatoria\": None}) é um caso diferente de chave ausente para dict.get(chave, default) -- o default só vale quando a chave não existe. Antes desta correção, isso levantaria TypeError dentro de set(None), mascarado pelo except Exception amplo da wrapper MCP. Agora os dois casos (ausente e None explícito) usam o piso atual, sem erro -- coberto por teste novo."
    autoridade: existente_ou_nova
  - id: p02-sub14-orcamento-restante-erro-por-indice-nao-por-lote
    motivo: "Gap pré-existente, registrado desde a sub-entrega 4/N (não é regressão desta correção, é o fechamento dela): orcamento_restante vindo de um pedido de simular_politica chegava intacto até mandato_cobre() (autonomy/policy.py, não alterado nesta sub-entrega), onde a comparação `orcamento_restante > 0` levanta TypeError para um valor não numérico -- capturado só pelo except Exception amplo em torno da chamada em lote a autonomy_policy.simular_politica(pedidos), que fica FORA do loop por-pedido. Um único pedido inválido no meio de um lote abortava a simulação inteira com mensagem genérica, em vez de ser reportado por índice como os demais campos (argumentos_resolvidos, origem_humana, já corrigidos em sub-entregas anteriores). Validação adicionada em _policy_request_simulado, levantando ValueError capturado pelo try/except por-índice já existente em _simular_politica. bool excluído explicitamente do isinstance (int, float) -- é subclasse de int em Python, mas orcamento_restante=true não é um saldo numérico válido."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "Antes desta sub-entrega (main pós-merge da sub-entrega 13/N, commit 9bf088faf): 1371/1371."
    - "Depois desta sub-entrega, incluindo os 2 testes extras pedidos pela revisão adversarial (lista vazia, None explícito): 1380/1380, 0 falhas, 0 erros."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre o diff dos 4 arquivos. Veredito: nenhum achado bloqueante. Confirmado por grep que preparar_politica() só é chamado pela wrapper MCP e por testes (tuple/set/frozenset só alcançáveis por um chamador Python direto, nunca via protocolo MCP/JSON, onde arrays sempre desserializam como list); confirmado que mcp_server.py nunca popula orcamento_restante a partir de input externo (fica no default None do dataclass), então _policy_request_simulado é o único ponto que precisava da validação. 3 achados não-bloqueantes endereçados antes de prosseguir: (1) este registro em execucao.md -- estava faltando no diff original submetido à revisão; (2) comentário em hermes_tools.py citava 'sub-entrega 5/N' em vez de 'sub-entrega 4/N' para a origem da pendência -- corrigido; (3) faltavam testes para lista vazia e None explícito -- 2 testes adicionados (ver decisão p02-sub14-none-explicito-tratado-igual-a-ausente acima; lista vazia já era o comportamento correto pré-existente, só não estava testado)."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: o bug de tipo em autonomy/policy.py::preparar_politica, registrado desde a sub-entrega 3/N (motor puro corrigido; a validação da wrapper MCP permanece como defesa em profundidade, não removida)."
  - "RESOLVIDO por esta entrada: validação de tipo de PolicyRequest.orcamento_restante no wrapper MCP, registrada desde a sub-entrega 4/N."
  - "Todas as pendências já registradas nos blocos anteriores que não foram tocadas por esta sub-entrega continuam abertas: passo 1 do plano parcialmente aberto (outbox_aprovacao.py/revisao_semanal.py sem Principal -- decisão de produto/design, não só engenharia), risco de bare-name-resolution nos módulos de área, Mandato.classes_conteudo_permitidas texto livre sem enum fechado, Mandato.usos_na_janela_atual/orcamento_maximo sem wrapper de I/O real, pergunta de design sobre o default de origem_humana, dependência de CLASSE_EFEITO_PISO/FLOOR_CONFIRMACAO_OBRIGATORIA continuarem com as mesmas chaves (travado por teste, mas não uma garantia estrutural)."
proximo_pacote: "P02 -- as pendências de engenharia autocontida (sem decisão de produto/design) estão resgatadas por ora. As restantes exigem decisão do André antes de prosseguir autonomamente: (1) religar outbox_aprovacao.py/revisao_semanal.py a Principal/decisao_piso() (passo 1 do plano) -- escopo de produto, não só técnico; (2) o default de origem_humana quando não informado; (3) se Mandato.classes_conteudo_permitidas deve virar enum fechado (taxonomia é decisão de produto) ou se basta validação técnica. Recomendação: levar a lista consolidada ao André antes de abrir mais uma sub-entrega sozinha."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 731049786a13913e70e3d1e6dfc6cd0e69dd9a2f
pacote: "P02 sub-entrega 15/N -- as três questões de design pendentes desde a sub-entrega 1/N/2/N: default de origem_humana, Mandato.classes_conteudo_permitidas texto livre, e a primeira religação real de outbox_aprovacao.py/revisao_semanal.py a autonomy/policy.py"
# André, ao ser apresentado com a lista consolidada das três pendências
# (mensagem: "sigam suas próprias recomendações... pode tomar as decisões
# que você achar mais conveniente... conforme as melhores práticas atuais"),
# autorizou decidir e prosseguir, com uma condição explícita: não afetar os
# ajustes paralelos de custos em andamento no Hermes (PR #204,
# DEV-2026-0003 -- telemetria de leituras/escritas Firestore). Confirmado
# antes de tocar em qualquer arquivo: PR #204 mergeada (commits
# a5e4c746b/9c8ed2553/9b8968cd7, merge 731049786) tocou só
# functions/firestore_metrics.py, functions/firestore_resilience.py (+16
# linhas, hook de instalação),  functions/test_firestore_metrics.py e
# docs/okf/operacoes/custos.md -- zero sobreposição com os arquivos desta
# sub-entrega. O hook de telemetria é um monkeypatch global instalado uma
# vez no carregamento das functions (main.py importa firestore_resilience),
# então nenhuma mudança nesta sub-entrega precisou (nem deveria) tocar
# nesses quatro arquivos para continuar sendo contabilizada por ele.
estado: pronto_para_revisao
inicio: "2026-09-09T00:20:00Z"
fim: "2026-09-09T00:56:00Z"
arquivos_alterados:
  - docs/autonomia/execucao.md (dividido -- ver decisão p02-sub15-execucao-md-dividido-por-limite-de-saida abaixo)
  - docs/autonomia/execucao-archive-p00-a-p02sub11.md (novo -- arquivo dos blocos P00 a P02 sub-entrega 10/N-11/N)
  - functions/autonomy/contracts.py (Principal.origem_humana: bool = True vira bool | None = None, resolvido em __post_init__ por tipo; Mandato ganha __post_init__ que rejeita "outro"/rótulo vazio em classes_conteudo_permitidas)
  - functions/autonomy/policy.py (comentário sobre o gate de origem_humana atualizado -- não é mais verdade que "nada no sistema de tipos impede" um default True incondicional; agora só um override explícito consegue)
  - functions/tools/tool_context.py (principal_de para de recalcular o default por tipo, repassa origem_humana para Principal.__post_init__ resolver)
  - functions/tools/hermes_tools.py (_principal_simulado: mesma simplificação, mantém a validação de tipo já existente para valores não-bool não-None)
  - functions/outbox_aprovacao.py (liberar_rascunhos_promovidos ganha preflight de autonomy_policy.estado_autonomia_atual -- PAUSADO e SOMENTE_PREPARACAO bloqueiam)
  - functions/revisao_semanal.py (propor_reagendamento_semanal ganha o mesmo preflight -- só PAUSADO bloqueia)
  - functions/test_contracts.py (12 testes novos: 6 do default de origem_humana por tipo, 6 da validação de classes_conteudo_permitidas)
  - functions/test_outbox_aprovacao.py (5 testes novos -- primeira cobertura de teste de liberar_rascunhos_promovidos, que não tinha nenhuma antes desta sub-entrega)
  - functions/test_revisao_semanal.py (2 testes novos: pausado bloqueia, somente_preparacao não)
decisoes:
  - id: p02-sub15-origem-humana-deriva-por-tipo-no-post-init
    motivo: "Pergunta em aberto desde a sub-entrega 1/N/2/N (execucao.md, deliberadamente adiada para 'quando o pacote P02 inteiro estiver completo'): origem_humana deveria mesmo ter default True no contrato? Decisão: não. Achado ao investigar antes de decidir: TODO canal religado desde então (tools/tool_context.py::principal_de desde a sub-entrega 5/N, hermes_tools.py::_principal_simulado desde a 3/N, mcp_jobs.py, telegram_callbacks_confirmacoes.py) já convergiu independentemente para a mesma regra -- verdadeiro só para DONO_INTERATIVO/CLIENTE_ASSISTIDO, passado sempre explicitamente, nunca herdado do default do dataclass (mcp_server.py chega a comentar isso como 'cuidado deliberado'). Ou seja, a incerteza que justificava adiar a decisão (será que canais futuros vão querer outra coisa?) já foi respondida empiricamente por três sub-entregas de código real: não. Esta sub-entrega só torna estrutural (garantido por Principal.__post_init__, object.__setattr__ porque o dataclass é frozen) o que já era, na prática, o único comportamento em produção -- e consolida a lógica duplicada em tool_context.py e hermes_tools.py numa fonte única. Comportamento de todo chamador existente inalterado (todos passam valor explícito); confirmado por grep exaustivo (revisão adversarial) que não há Principal(...) construído sem origem_humana explícito em nenhum caminho de produção."
    autoridade: existente_ou_nova
  - id: p02-sub15-mandato-classes-conteudo-rejeita-outro-e-vazio-estruturalmente
    motivo: "A seção 5.3 do plano já dizia, em texto: 'Tipos outro e rótulos livres não podem habilitar envio autônomo'. Decisão: implementar essa UMA regra explícita como validação estrutural em Mandato.__post_init__ (rejeita 'outro' case-insensitive e rótulo vazio/em branco) -- não inventar a taxonomia REAL de classes de conteúdo (quais categorias de mensagem o Hermes pode enviar autonomamente a terceiros), que é decisão de produto/conteúdo, não de engenharia, e que esta sub-entrega deliberadamente deixa em aberto para o André ou uma sub-entrega futura com o input dele. Achado relevante ao investigar: outbox_aprovacao.py::criar_rascunho já tem um campo tipo (texto livre, default 'outro' há muito tempo em produção) -- é exatamente o padrão que a seção 5.3 avisa contra, mas Mandato e o tipo do rascunho ainda são dois modelos de dados desconectados (nenhum código monta um Mandato real ainda, ver pendências abaixo), então esta validação não afeta outbox_aprovacao.py nesta sub-entrega -- fecha a porta para quando os dois se conectarem."
    autoridade: existente_ou_nova
  - id: p02-sub15-preflight-estado-autonomia-em-vez-de-decisao-piso-completo
    motivo: "A pendência dizia 'religar outbox_aprovacao.py/revisao_semanal.py a Principal/decisao_piso()'. Decisão: religar ao interruptor global (autonomy_policy.estado_autonomia_atual), NÃO ao decisao_piso() completo com Mandato real -- e documentar por que o segundo não é seguro fazer nesta sub-entrega. Investigação antes de decidir: liberar_rascunhos_promovidos (outbox_aprovacao.py) é a ÚNICA função de todo o outbox que envia mensagens de WhatsApp reais a terceiros reais SEM toque humano por instância (rascunhos 'promovidos' esperam só a janela de cancelamento passar, depois aprovar_rascunho é chamado sozinho com aprovado_via='janela_automatica') -- as demais só executam depois de um toque real no Telegram, que já satisfaz a exigência de 'decisão concreta' da seção 5.1 para compromisso_terceiros. propor_reagendamento_semanal (revisao_semanal.py) é uma proposta semanal que sempre aguarda toque humano antes de qualquer efeito real. Chamar decisao_piso() de verdade em qualquer um dos dois hoje exigiria um Mandato real cobrindo a ação -- e o wrapper de I/O que resolveria um Mandato a partir do Firestore não existe (pendência registrada desde a sub-entrega 1/N, não implementada nesta). Sem mandato algum aplicável, o motor cai fail-closed (ver autonomy/policy.py, ramo COMPROMISSO_TERCEIROS/ESCRITA_INTERNA_REVERSIVEL sem mandato e sem humano presente) -- ou seja, ligar decisao_piso() de verdade agora DESLIGARIA por completo tanto o auto-envio de rascunhos promovidos quanto a proposta semanal, uma mudança de comportamento real e grande a um sistema em produção que manda WhatsApp de verdade, decidida sozinha sem o André ver. Isso não é 'pura engenharia' -- é exatamente o tipo de decisão de produto que a pendência original pedia para não tomar sozinho. O que É seguro e só reduz risco (nunca aumenta): checar o interruptor global de autonomia antes de agir. liberar_rascunhos_promovidos bloqueia em PAUSADO e SOMENTE_PREPARACAO (é o próprio envio, não preparação); propor_reagendamento_semanal só em PAUSADO (propor é preparação pela própria definição da seção 5.4 -- SOMENTE_PREPARACAO não deveria suprimir isso). Antes desta sub-entrega, pausar a autonomia globalmente NÃO impedia nenhuma das duas ações -- gap real fechado, ganho líquido de segurança sem quebrar nada existente."
    autoridade: existente_ou_nova
  - id: p02-sub15-execucao-md-dividido-por-limite-de-saida
    motivo: "Achado técnico NOVO desta sub-entrega, não relacionado às três decisões de design acima: ao tentar gravar esta própria entrada em docs/autonomia/execucao.md (que já somava 135907 bytes antes deste bloco), duas tentativas via subagente truncaram silenciosamente o conteúdo enviado ao Argos (53544 e depois 73071 de 148554 bytes esperados), e uma terceira tentativa direta falhou com erro explícito da API: 'response exceeded the 64000 output token maximum'. Causa raiz: argos_escrever_arquivo_repositorio não aceita diff/patch, só substituição integral -- o arquivo inteiro precisa ser gerado como texto de saída em uma única chamada, e o histórico acumulado de P00 a sub-14/N tinha crescido a ponto de ultrapassar esse teto assim que somado a um bloco novo de tamanho normal. Decisão: mover os blocos P00 a P02 sub-entrega 10/N-11/N (catch-up) -- os mais antigos, cujas pendências relevantes já são restatadas nos blocos mais recentes -- para docs/autonomia/execucao-archive-p00-a-p02sub11.md (cópia byte-a-byte, sem edição de conteúdo, ponto de corte escolhido no byte 116722, exatamente na fronteira entre blocos). execucao.md ativo cai de 135907 para ~19KB de histórico retido + este bloco, com folga considerável abaixo do teto. Nenhuma decisão de produto envolvida -- é manutenção de infraestrutura de registro necessária para o próprio processo de documentar sub-entregas continuar funcionando. Se o arquivo ativo voltar a se aproximar do teto no futuro, repetir o mesmo padrão (arquivar os blocos mais antigos que sobrarem)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "Antes desta sub-entrega (main pós-merge da PR #204/DEV-2026-0003, commit 731049786): 1395/1395."
    - "Depois desta sub-entrega: 1415/1415, 0 falhas, 0 erros."
    - "liberar_rascunhos_promovidos (outbox_aprovacao.py) não tinha NENHUM teste dedicado antes desta sub-entrega -- os 5 testes novos são a primeira cobertura da função inteira, não só do preflight (caminho feliz incluído)."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre o diff completo dos 9 arquivos. Veredito: nenhum achado bloqueante. Verificou por grep exaustivo em todo functions/ (não só os arquivos alterados) que não há Principal(...) nem Mandato(...) construído em produção que dependesse do comportamento antigo; confirmou que object.__setattr__ nos dois __post_init__ novos é o idiom correto para dataclass frozen; traçou os dois callers em produção (main.py e o próprio scheduler_fn) e confirmou que nenhum inspeciona o valor de retorno de liberar_rascunhos_promovidos/propor_reagendamento_semanal de um jeito que o novo early-return quebraria; confirmou que estado_autonomia_atual só retorna um dos três valores do enum, cobertos pelos dois preflights sem ramo faltando."
  - "Suíte completa rodada antes (via git stash, para isolar a contagem exata da base) e depois; ver testes.resultados acima."
  - "5 dos 9 arquivos (policy.py, outbox_aprovacao.py, hermes_tools.py, test_outbox_aprovacao.py, test_revisao_semanal.py) enviados via subagentes independentes (Agent tool) com verificação de hash local antes E depois do envio ao Argos, retry único em caso de divergência -- hermes_tools.py (100KB) precisou de 1 retry (a primeira tentativa perdeu a quebra de linha final do arquivo; a segunda bateu exatamente). Os 4 arquivos menores (contracts.py, revisao_semanal.py, tool_context.py, test_contracts.py) enviados diretamente por esta sessão, hash verificado em cada um -- todos bateram na primeira tentativa."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: pergunta de design sobre o default de origem_humana, em aberto desde a sub-entrega 1/N/2/N."
  - "RESOLVIDO PARCIALMENTE por esta entrada: Mandato.classes_conteudo_permitidas -- a regra explícita do plano ('outro'/rótulo vazio nunca habilita envio autônomo) agora é estrutural. A taxonomia REAL de classes de conteúdo continua em aberto -- decisão de produto, não desta sub-entrega."
  - "RESOLVIDO PARCIALMENTE por esta entrada: passo 1 do plano para outbox_aprovacao.py/revisao_semanal.py -- primeira religação real a autonomy/policy.py (interruptor global de EstadoAutonomia). O decisao_piso() completo com Mandato real continua NÃO ligado a esses dois arquivos -- ver decisão p02-sub15-preflight-estado-autonomia-em-vez-de-decisao-piso-completo acima para o motivo (exigiria o wrapper de I/O de Mandato, que não existe, e desligaria por completo duas funções em produção sem revisão do André)."
  - "Novo, desta sub-entrega: outbox_aprovacao.py::criar_rascunho tem um campo tipo em texto livre (default 'outro') que hoje não se conecta a Mandato.classes_conteudo_permitidas nenhum -- quando o wrapper de I/O de Mandato existir, conectar os dois é o jeito de fazer o preflight de liberar_rascunhos_promovidos usar a classificação de conteúdo de verdade, não só o interruptor global."
  - "Todas as pendências já registradas nos blocos anteriores que não foram tocadas por esta sub-entrega continuam abertas: risco de bare-name-resolution nos módulos de área, Mandato.usos_na_janela_atual/orcamento_maximo sem wrapper de I/O real, dependência de CLASSE_EFEITO_PISO/FLOOR_CONFIRMACAO_OBRIGATORIA continuarem com as mesmas chaves (travado por teste, mas não uma garantia estrutural)."
proximo_pacote: "P02 -- candidata natural: o wrapper de I/O que resolve um Mandato real a partir do Firestore (mandatos persistidos, usos_na_janela_atual, orcamento_maximo), que destrava tanto o decisao_piso() completo em outbox_aprovacao.py/revisao_semanal.py quanto a taxonomia real de classes_conteudo_permitidas. É um passo maior e com decisões de produto reais (que mandatos existem hoje na prática, quais categorias de conteúdo); recomendo trazer ao André antes de escopar."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 7931ac2d9b067a75fd00b18ad0973f284bf045a7
pacote: "P02 sub-entrega 16/N -- CLASSE_EFEITO_PISO/FLOOR_CONFIRMACAO_OBRIGATORIA: invariante estrutural, não só travada por teste"
# Continuação autônoma autorizada por André ("pr mesclado. pode continuar"),
# após a PR #205 (sub-entrega 15/N) ser mesclada em main -- confirmado por
# leitura direta de functions/autonomy/contracts.py em main (sha
# 3954ad0a7a9ec4a6afba802be61fdfb5d7b26bd9, batendo exatamente com o que a
# sub-entrega 15/N enviou), não só pela palavra do André. Escolhida entre as
# pendências acumuladas por ser a única puramente de engenharia sem decisão
# de produto pendente -- a outra candidata natural (wrapper de I/O de
# Mandato) foi deliberadamente deixada de fora desta sessão (ver
# proximo_pacote, abaixo, e a recomendação já registrada no bloco anterior:
# "recomendo trazer ao André antes de escopar" -- envolve decisões reais de
# produto, que mandatos existem hoje na prática e quais categorias de
# conteúdo, que não me cabe tomar sozinho). O outro item pendente puramente
# técnico (risco de bare-name-resolution nos módulos de área) segue sem ação
# concreta possível -- é um risco latente, "endereçar se/quando um teste
# futuro tropeçar nisso", sem um passo de engenharia definido hoje.
estado: pronto_para_revisao
inicio: "2026-09-09T08:30:00Z"
fim: "2026-09-09T08:49:00Z"
arquivos_alterados:
  - functions/autonomy/policy.py (nova função _validar_piso_consistente(), chamada no carregamento do módulo)
  - functions/test_policy.py (5 testes novos em TestValidarPisoConsistente)
decisoes:
  - id: p02-sub16-piso-invariante-estrutural-nao-so-teste
    motivo: "Pendência não-bloqueante registrada desde a sub-entrega 12/N: a garantia de que CLASSE_EFEITO_PISO e FLOOR_CONFIRMACAO_OBRIGATORIA têm exatamente as mesmas chaves -- da qual decisao_piso()/_decisao_piso_mcp dependem inteiramente para nunca chamar avaliar() com um principal malformado, ver decisao_erro_avaliacao() -- só era travada por test_policy.py::TestFloorIdenticoAoMcpServer.test_classe_efeito_piso_cobre_exatamente_o_floor. Um deploy que pulasse a suíte de testes podia deixar as duas tabelas divergirem em produção sem nenhum sinal. Decisão: extrair a checagem para uma função (_validar_piso_consistente, testável isoladamente com tabelas forjadas, sem precisar recarregar o módulo) e chamá-la uma vez no carregamento do módulo -- mesmo padrão fail-closed já usado no resto deste arquivo (decisao_erro_avaliacao()): se um dia divergirem, o import falha alto e cedo (AssertionError), em vez de deixar avaliar() correr com uma premissa quebrada. NÃO fundi as duas tabelas numa só (ex.: derivar FLOOR_CONFIRMACAO_OBRIGATORIA de CLASSE_EFEITO_PISO.keys()) -- o comentário já existente sobre FLOOR_CONFIRMACAO_OBRIGATORIA é explícito: 'ESTE CONJUNTO NÃO CRESCE POR HÁBITO (condição do dono, 02/09/2026) -- uma candidata nova exige decisão explícita, registrada aqui e em mcp_server.py'. Fundir as tabelas faria uma entrada nova em CLASSE_EFEITO_PISO (por qualquer outro motivo de documentação) crescer o piso por acidente -- exatamente o hábito que a condição do dono proíbe. Duas tabelas separadas, mantidas manualmente iguais, com a checagem agora estrutural em vez de só testada, preserva a fricção deliberada. Zero mudança de comportamento hoje -- as duas tabelas já batem; a checagem só passa a valer quando (se) um dia divergirem."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "Antes desta sub-entrega (main pós-merge da PR #205, commit 7931ac2d9): 1415/1415."
    - "Depois desta sub-entrega: 1420/1420, 0 falhas, 0 erros (5 testes novos: tabelas reais do módulo passam pela função isolada, tabelas idênticas forjadas não levantam, ferramenta extra em cada uma das duas direções levanta AssertionError citando o nome certo, tabelas vazias não levantam)."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre o diff dos 2 arquivos. Veredito: nenhum achado bloqueante. Verificou por importação direta do módulo que a checagem roda na ordem certa (sem NameError) e que as duas tabelas reais batem hoje (zero risco de crash em cold start introduzido por esta sub-entrega); confirmou por grep em todo functions/ que nenhum teste existente faz patch/reload das duas tabelas (nenhum risco de disparar a nova asserção por acidente); confirmou por leitura direta de decisao_piso() que a docstring da nova função não exagera a garantia real; rodou os 4 arquivos de teste relacionados (171 testes) para confirmar zero regressão; verificou que os testes novos são não-vácuos (uma implementação ingênua tipo 'só checa subconjunto' falharia em pelo menos um dos dois testes de assimetria). Dois nits cosméticos apontados (uma linha em branco a menos que o PEP8 recomenda antes do novo def; nenhum lint configurado no repo para isso) -- deliberadamente não corrigidos, sem efeito funcional."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: a dependência de CLASSE_EFEITO_PISO/FLOOR_CONFIRMACAO_OBRIGATORIA continuarem com as mesmas chaves, registrada desde a sub-entrega 12/N -- agora estrutural (falha no import), não só travada por teste."
  - "Todas as pendências já registradas nos blocos anteriores que não foram tocadas por esta sub-entrega continuam abertas: risco de bare-name-resolution nos módulos de área (latente, sem passo de engenharia concreto definido), Mandato.usos_na_janela_atual/orcamento_maximo sem wrapper de I/O real, taxonomia real de Mandato.classes_conteudo_permitidas (decisão de produto), outbox_aprovacao.py::criar_rascunho.tipo desconectado de Mandato.classes_conteudo_permitidas."
proximo_pacote: "P02 -- as pendências puramente de engenharia estão resgatadas por ora (nenhuma sobrou sem decisão de produto pendente). A única candidata natural que resta -- o wrapper de I/O que resolve um Mandato real a partir do Firestore -- envolve decisões reais de produto (que mandatos existem hoje na prática, quais categorias de conteúdo o Hermes pode usar autonomamente) que não me cabe escopar sozinho; será levada ao André como pergunta consolidada, não decidida por conta própria como as três da sub-entrega 15/N."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: d5538746b40e5129e606b1848cd8640a304c712a
pacote: "P01 sub-entrega 3/N -- aplicar_edicao_rascunho ganha proteção transacional (mesmo padrão A04 de aprovar_rascunho/descartar_rascunho)"
# André confirmou o merge da PR #210 (P02 sub-entrega 17/N) e pediu, antes
# de prosseguir, um relato honesto e completo de quanto falta do plano
# inteiro ("me fale o quanto falta para finalizar o plano por completo").
# Entregue o relato (P00 essencialmente completo, P01 só 20% feito --
# passos 1-2/10 --, P02 com religação real ao motor de política mas ainda
# com lacunas conhecidas, P03-P18 não iniciados). André respondeu "Perfeito,
# então vamos prosseguir" -- sem indicar qual pacote/passo especificamente.
# Interpretado, por autoridade da própria seção 14.1 do plano ("Implemente
# os pacotes na ordem das dependências... Continue o trabalho independente...
# não transforme cada passo reversível em nova confirmação"), como
# autorização para escolher o próximo passo de engenharia bem escopado e
# reversível na ordem de dependências, sem nova pergunta de confirmação.
# Escolhido: fechar P01 (o pacote menos completo, sem dependências
# pendentes de P02+) pela lacuna já identificada e registrada desde a
# sub-entrega 1/N -- aplicar_edicao_rascunho sem a mesma proteção
# transacional que aprovar_rascunho/descartar_rascunho já tinham.
estado: pronto_para_revisao
inicio: "2026-09-09T10:15:00Z"
fim: "2026-09-09T10:45:00Z"
arquivos_alterados:
  - functions/outbox_aprovacao.py (aplicar_edicao_rascunho reescrita para o padrão transacional A04 -- get()+update() incondicional vira transação Firestore que relê e revalida o status antes de escrever, reutilizando validar_transicao_aprovacao)
  - functions/test_outbox_aprovacao.py (6 testes novos: 2 em TestSemFallbackParaEscritaDesprotegida -- falha de transação e ausência de suporte a transação, sem escrita desprotegida; 3 em TestEdicao -- aguardando_janela funciona e volta para aguardando_aprovacao, rascunho já decidido recusa e não ressuscita status/conteúdo em nenhum dos 4 status terminais via subTest, rascunho inexistente retorna not_found)
decisoes:
  - id: p01-sub3-aplicar-edicao-fecha-lacuna-a04-registrada-desde-sub1
    motivo: "Pendência registrada desde a sub-entrega 1/N de P01 (achado A04, quando aprovar_rascunho e descartar_rascunho ganharam proteção transacional): aplicar_edicao_rascunho ficou de fora daquela correção porque não tinha, na época, nenhum risco de ressureição de status documentado -- só o risco genérico de condição de corrida com liberar_rascunhos_promovidos/descartar_rascunho. Ao reabrir o código nesta sub-entrega, achado mais grave que o originalmente registrado: a função fazia um update() incondicional que reescrevia status=aguardando_aprovacao SEMPRE, sem checar o status atual do documento -- uma edição tardia (sessão de Telegram/WhatsApp obsoleta, retry, clique duplo em fila) sobre um rascunho já enviado (sent), aprovado (pending) ou descartado o ressuscitava silenciosamente de volta para aguardando_aprovacao, reabrindo ao dono uma decisão que ele já tinha tomado. Corrigido com o mesmo padrão transacional já usado (e comprovado) em aprovar_rascunho/descartar_rascunho: get() dentro de uma @firestore.transactional, revalidação de status via validar_transicao_aprovacao (reutilizada, não duplicada -- é o mesmo domínio de aguardando_aprovacao/aguardando_janela que a aprovação usa), e nenhum fallback para escrita desprotegida quando a transação falha ou o backend não suporta transação (retorna erro_transacao/erro_configuracao explícito, mesmo contrato dos outros dois caminhos)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && python -m unittest discover -s . -p 'test_*.py'"
  resultados:
    - "Antes desta sub-entrega (main pós-merge da PR #210, commit d5538746b): 1463/1463, 0 falhas, 0 erros -- baseline mais limpa que a documentada na sub-entrega 17/N (as 8 falhas + 2 erros pré-existentes de lá não aparecem mais; o merge da PR #210 aparentemente absorveu correções/arquivos concorrentes de outra PR, incluindo functions/llm_usage_hooks.py e functions/test_llm_usage_hooks.py, não tocados por esta sub-entrega)."
    - "Depois desta sub-entrega: 1468/1468, 0 falhas, 0 erros -- exatamente os 5 testes novos, zero regressão."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre o diff dos 2 arquivos. Veredito: seguro para enviar. Verificou de forma empírica (via git stash do fix, rodando os testes novos contra o código ANTIGO) que test_editar_rascunho_ja_decidido_recusa_e_nao_ressuscita de fato falha sob o comportamento pré-correção -- confirma que o teste não é vácuo. Leu o código-fonte da biblioteca google-cloud-firestore instalada para confirmar que o protocolo do mock (_begin/_clean_up/_commit/_rollback/_max_attempts/_read_only) é fiel ao real, mesmo double já usado em aprovar_rascunho/descartar_rascunho. 4 achados não-bloqueantes, documentados aqui e deliberadamente não corrigidos nesta sub-entrega para manter o diff revisado idêntico ao enviado: (1) o card do Telegram de um rascunho editado-mas-depois-decidido-por-outro-caminho não é fechado/atualizado -- mesma limitação pré-existente já registrada como pendência na sub-entrega 17/N para o caso de degrade; (2) o telegram_message_id gravado após reenviar o card de edição é um doc_ref.update() solto, fora da transação -- inofensivo (é só o id da mensagem do card, não afeta status/conteúdo), mesmo padrão não-transacional já usado em criar_rascunho/aprovar_rascunho/descartar_rascunho para esse mesmo campo; (3) envio_liberado_em não é explicitamente nulado quando uma edição rebaixa aguardando_janela para aguardando_aprovacao -- nit de higiene de dado, sem efeito funcional (avaliar_liberacao_promovidos já filtra por status=aguardando_janela primeiro, então um envio_liberado_em obsoleto num doc aguardando_aprovacao nunca é lido); (4) sugestão de cobertura de teste adicional (não um bug) para o caminho de reenvio de card falhar silenciosamente durante uma edição bem-sucedida -- já coberto pelo padrão try/except existente, só faltava um teste dedicado."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: aplicar_edicao_rascunho sem proteção transacional, pendência registrada desde a sub-entrega 1/N de P01 (achado A04)."
  - "Os 4 achados não-bloqueantes da revisão adversarial desta sub-entrega, listados em evidencias acima, deliberadamente não corrigidos: (1) card Telegram não fechado quando o rascunho é decidido por outro caminho após edição; (2) telegram_message_id gravado fora da transação (inofensivo, padrão pré-existente); (3) envio_liberado_em não nulado ao rebaixar de aguardando_janela via edição (nit de higiene, sem efeito funcional); (4) nice-to-have de cobertura de teste para falha silenciosa de reenvio de card."
  - "P01 passos 3-10 do plano continuam abertos: agent_requests.py, core/idempotency.py, mcp_jobs.py, mcp_server.py, firestore.rules/deploy.yml (mesmo bloqueio de PAT sem escopo workflow já registrado para P00), e o relatório de reconciliação final do pacote."
  - "Todas as pendências já registradas nos blocos anteriores que não foram tocadas por esta sub-entrega continuam abertas (ver blocos de P02 acima)."
proximo_pacote: "P01 -- próximo passo natural na ordem do plano é o passo 3 (agent_requests.py), seguido de core/idempotency.py e mcp_jobs.py/mcp_server.py; firestore.rules/deploy.yml permanece bloqueado pelo mesmo PAT sem escopo workflow de P00. Como esta é a segunda sub-entrega consecutiva escolhida sem confirmação explícita do André sobre QUAL trabalho priorizar, meu relato a ele nomeará esse próximo passo como recomendação, não como decisão já tomada -- para não encadear escolhas unilaterais indefinidamente."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: ab537c889a90c9be08b4ffb3f6b2bd0e5a6f6f0e
pacote: "P01 sub-entrega 4/N -- agent_requests.py (passo 3 do plano): enfileiramento/conclusão legados viram transições condicionais"
# Continuação autônoma autorizada por André: os 3 PRs em aberto (#206, #208,
# #211) foram mesclados e ele disse "Pode seguir com o trabalho". Escolhido
# exatamente o passo nomeado como recomendação no proximo_pacote da entrada
# anterior (P01 passo 3, agent_requests.py) -- não uma escolha nova.
#
# Passo 3 do plano ("Transformar enfileiramento/conclusão legados em
# transições condicionais. P04 acrescentará o protocolo completo.") aplicado
# ao achado A01 (agent_requests.py: enfileirar_ou_atualizar, listar_pendentes
# e concluir; transições por leitura seguida de escrita, sem lease). Escopo
# desta sub-entrega: só a proteção transacional condicional (mesmo padrão
# A04 já usado 3x em outbox_aprovacao.py) -- NÃO o protocolo completo de
# lease/reserva/schema_version/dedupe_key da seção 4, que é explicitamente
# P04. listar_pendentes é só leitura (query), não sofre a mesma condição de
# corrida -- não tocada.
#
# concluir() é acionável em produção por mais de uma sessão via a tool MCP
# concluir_pedido_agente (tools/hermes_tools.py:2016) -- a condição de corrida
# de duas conclusões concorrentes do mesmo pedido não é hipotética.
estado: pronto_para_revisao
inicio: "2026-09-09T11:10:00Z"
fim: "2026-09-09T11:55:00Z"
arquivos_alterados:
  - functions/agent_requests.py (enfileirar_ou_atualizar e concluir reescritas para o padrão transacional A04 -- leitura+escrita dentro de uma única @firestore.transactional; sem hasattr(db, "transaction") ou falha real de transação, retorna erro_configuracao/erro_transacao explícito, nunca cai para escrita desprotegida)
  - functions/test_agent_requests.py (mock de Transaction promovido para o double fiel já usado em test_outbox_aprovacao.py/test_promocao_autonomia.py -- _begin/_clean_up/_commit/_rollback/_max_attempts/_read_only, com .set() -- e 5 testes novos em TestSemFallbackParaEscritaDesprotegida: falha de transação e ausência de suporte a transação para enfileirar_ou_atualizar (doc novo e doc existente) e para concluir)
  - functions/test_atencao_whatsapp.py (mock de DB local (usado só pelo hook de áudio) ganhou o mesmo double fiel de Transaction -- estava desatualizado e quebrava test_hook_cria_e_mescla_agent_request assim que enfileirar_ou_atualizar passou a exigir transação; 1 teste novo, test_hook_sobrevive_a_falha_protegida_de_enfileiramento, cobrindo o achado should-fix abaixo)
  - functions/atencao_whatsapp.py (hook audio_relevante: captura o retorno de enfileirar_ou_atualizar e loga quando vier erro_transacao/erro_configuracao -- achado should-fix da revisão adversarial, ver decisões)
decisoes:
  - id: p01-sub4-agent-requests-transacional-fecha-achado-a01-passo3
    motivo: "Achado A01 (fila de pedidos com transição por leitura-seguida-de-escrita, sem lease) e passo 3 do plano P01 fechados juntos: enfileirar_ou_atualizar e concluir agora usam o mesmo padrão A04 já validado 3x em outbox_aprovacao.py (aprovar_rascunho/descartar_rascunho/aplicar_edicao_rascunho) -- @firestore.transactional relê o documento dentro da transação antes de decidir, e nenhum caminho (transação indisponível, transação que falha, ou qualquer dos 3 ramos de enfileirar_ou_atualizar: doc novo, doc pendente, doc já em andamento/terminal) cai para get()+set()/update() desprotegido. listar_pendentes/contar_pendentes permanecem só leitura, fora de escopo -- não têm transição a proteger. O protocolo completo de lease/reserva com schema_version/dedupe_key/assigned_executor (seção 4 do plano) fica para P04, como o próprio passo 3 já demarca -- esta sub-entrega não antecipa esse trabalho."
    autoridade: existente_ou_nova
  - id: p01-sub4-achado-should-fix-mock-db-desatualizado-quebrava-teste-existente
    motivo: "Achado da revisão adversarial (Agent tool, general-purpose, sem contexto da implementação), categoria correção-antes-de-enviar (não um 'should-fix' documentado e adiado, mas um teste que a própria mudança quebrava): o _MockDB local de test_atencao_whatsapp.py (usado só por TestHookAgentRequests, que exercita atencao_whatsapp._processar_audio -> agent_requests.enfileirar_ou_atualizar) não implementava .transaction() nem aceitava o kwarg transaction= em DocRef.get(). Rodar a suíte completa antes de enviar pegou isso na hora: test_hook_cria_e_mescla_agent_request passou a falhar (0 docs em agent_requests em vez de 1) porque a nova exigência de transação real fazia o hook engolir um erro_configuracao em silêncio (try/except que só logava exceção levantada, e a nova implementação não levanta mais). Corrigido promovendo o mock local ao mesmo double fiel do protocolo real (_begin/_clean_up/_commit/_rollback/_max_attempts/_read_only, com .set()) já usado em test_outbox_aprovacao.py/test_promocao_autonomia.py/test_agent_requests.py."
    autoridade: existente_ou_nova
  - id: p01-sub4-achado-should-fix-hook-audio-logava-silenciosamente-falha-protegida
    motivo: "Achado should-fix da revisão adversarial: o hook audio_relevante (atencao_whatsapp.py) descartava o retorno de enfileirar_ou_atualizar por completo -- antes desta sub-entrega isso era inofensivo (a única falha possível levantava exceção e caía no except que já loga); agora que erro_transacao/erro_configuracao voltam como dict sem exceção, o try/except externo não tinha mais nada a capturar, e a falha protegida ficava completamente muda. Não bloqueante -- o revisor notou que o item de atenção já foi gravado antes do hook (linha 512), então o áudio continua visível ao dono; só a consolidação automática em segundo plano é que deixaria de ser enfileirada, sem que ninguém soubesse. Corrigido com um log explícito quando o status vier erro_transacao/erro_configuracao (sem replicar o alerta via Telegram que outbox_aprovacao já tem em _alertar_se_falha_outbox para o mesmo achado -- esse mecanismo é para comando do dono via WhatsApp que seria perdido; aqui é só enfileiramento de trabalho em segundo plano, escopo menor, não pedido por este passo do plano). Testado com test_hook_sobrevive_a_falha_protegida_de_enfileiramento (backend sem suporte a transação: hook não quebra, item de atenção é criado, nada é enfileirado)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && ../venv/bin/python3 -m unittest discover -p 'test_*.py' -q"
  resultados:
    - "Antes desta sub-entrega (main pós-merge dos PRs #206/#208/#211, commit ab537c889): 1467 testes, 8 falhas + 2 erros -- confirmados PRÉ-EXISTENTES (ambiente sem ANTHROPIC_API_KEY/deps opcionais para gmail/mp4; mesmos test_deteccao_subproduto.py::TestUltimaTentativaSempreRegistrada, test_gmail_bill_pdf, test_mp4_repair já documentados nas sub-entregas anteriores), não relacionados a esta sub-entrega. Confirmado via git stash antes de enviar."
    - "Depois desta sub-entrega: 1473 testes (6 novos: 5 em test_agent_requests.py::TestSemFallbackParaEscritaDesprotegida, 1 em test_atencao_whatsapp.py::TestHookAgentRequests), mesmas 8 falhas + 2 erros pré-existentes, zero regressão nova."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre o diff completo (agent_requests.py, test_agent_requests.py, test_atencao_whatsapp.py). Verificou contra o código-fonte real da biblioteca google-cloud-firestore instalada que o uso de tx.set()/tx.update()/doc_ref.get(transaction=tx) é fiel à API real, e que todas as leituras acontecem antes de qualquer escrita dentro de cada função transacional (exigência real do protocolo, não só do mock). Escreveu um mock de transação alternativo que só aplica escritas em _commit() (diferindo dos mocks que aplicam na hora) para simular um ciclo real de Aborted-e-retry, e confirmou que o código de produção relê corretamente no retry sem corromper dado. Rodou a suíte completa (1472 testes no momento da revisão, antes do achado do hook de áudio ser corrigido) e confirmou que as 8 falhas + 2 erros são as mesmas pré-existentes, em arquivos não relacionados. Veredito explícito: 'safe to ship'. Dois achados should-fix (ambos endereçados, ver decisões acima); nenhum achado bloqueante; um nitpick sobre os mocks de transação aplicarem escrita na hora em vez de diferir para _commit() -- mesmo padrão já usado nos outros mocks de transação do repositório (test_outbox_aprovacao.py/test_promocao_autonomia.py), não é regressão desta sub-entrega, e o revisor confirmou por script standalone que isso não mascara nenhum bug de produção."
  - "Suíte completa rodada antes (via git stash) e depois do diff completo (incluindo os 2 achados should-fix já corrigidos); ver testes.resultados acima."
  - "Todos os arquivos desta sub-entrega (agent_requests.py, test_agent_requests.py, test_atencao_whatsapp.py, atencao_whatsapp.py, e este próprio bloco de execucao.md) enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificação de hash local (git hash-object) contra o sha retornado pelo Argos em cada arquivo, antes de abrir a PR."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: achado A01 (agent_requests.py sem proteção transacional) e passo 3 de P01, ambos fechados -- só o escopo de transição condicional; o protocolo completo de lease/reserva continua para P04, como o plano já previa."
  - "P01 passos 4-10 do plano continuam abertos: idempotência com efeito (core/idempotency.py), mcp_jobs (reivindicação sobre leitura atual, estado de erro normalizado), firestore.rules/deploy.yml (mesmo bloqueio de PAT sem escopo workflow já registrado para P00), relatório de reconciliação final do pacote."
  - "Todas as pendências já registradas nos blocos anteriores que não foram tocadas por esta sub-entrega continuam abertas (ver blocos de P01/P02 acima)."
proximo_pacote: "P01 -- próximo passo natural na ordem do plano é o passo 4 (idempotência: mudar erro de idempotência em caminho com efeito para resultado recuperável sem efeito, em vez de 'permitir processamento' silenciosamente -- core/idempotency.py), seguido do passo 5 (mcp_jobs.py). Como já são várias sub-entregas seguidas escolhidas por mim seguindo a ordem do plano sem nova confirmação explícita a cada uma, vou nomear isso como recomendação no relato ao André, não como decisão já tomada."
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: f97978b90132ae9e6431000eff0a1c43bfeb691d
pacote: "P01 sub-entrega 5/N -- core/idempotency.py (passo 4 do plano): erro de idempotência em caminho com efeito vira resultado recuperável sem efeito, não mais 'permite processamento' silenciosamente"
# Continuação autônoma autorizada por André ("PR 212 mesclado. Pode
# prosseguir."). Escolhido exatamente o passo nomeado como recomendação no
# proximo_pacote da entrega anterior (P01 passo 4, core/idempotency.py).
#
# Achado técnico NOVO nesta sub-entrega, bloqueante para o caminho normal de
# envio: o único callsite real de check_and_register (githubWebhook, em
# functions/main.py) fica dentro de um arquivo de 683664 bytes -- acima do
# limite de 200000 bytes que o conector Argos aplica tanto para leitura
# (argos_ler_arquivo_repositorio) quanto para escrita
# (argos_escrever_arquivo_repositorio, que só aceita substituição integral do
# arquivo, nunca patch/diff). Confirmado ao vivo: a tentativa de leitura foi
# recusada pelo próprio Argos com erro explícito (413, "excede o limite de
# 200000 bytes"). Diferente do limite de saída de 64000 tokens que afetou
# este próprio execucao.md na sub-entrega 15/N de P02 (resolvido arquivando
# conteúdo antigo), este é um limite do CONECTOR Argos sobre UM arquivo de
# produção grande demais -- não há como dividir main.py em pedaços menores
# só para esta sub-entrega sem um refactor real, fora de escopo.
#
# Levado ao André via AskUserQuestion (4 opções: aplicar o diff manualmente,
# dividir main.py em módulos menores, pausar a sub-entrega, ou habilitar
# push local). Ele escolheu aplicar manualmente -- recebeu o diff exato (15
# linhas) e commitou direto na branch remota (commit 6ec1137cf). Confirmado
# por git fetch + diff que o commit dele bate byte a byte com o diff que eu
# tinha gerado localmente (mesmo blob sha do main.py, c8a05f3f2...) antes de
# eu prosseguir com os dois arquivos de teste restantes.
estado: pronto_para_revisao
inicio: "2026-09-09T11:58:00Z"
fim: "2026-09-09T12:16:00Z"
arquivos_alterados:
  - functions/core/idempotency.py (check_and_register reescrita: retorna enum de string RESULTADO_NOVO/RESULTADO_DUPLICADO/RESULTADO_ERRO_CONFIGURACAO/RESULTADO_ERRO_TRANSACAO em vez de bool; falha de transação ou backend sem suporte a transação nunca mais retornam True/"permite processamento")
  - functions/main.py (githubWebhook: trata os 2 resultados de erro com HTTP 503, sem processar o evento -- aplicado manualmente por André, commit 6ec1137cf, verificado byte a byte contra o diff gerado)
  - functions/test_github_webhook.py (testes existentes atualizados para o novo contrato de enum; 2 testes novos cobrindo o caminho 503 para cada tipo de erro)
  - functions/test_idempotency.py (novo -- não existia cobertura dedicada para core/idempotency.py antes desta sub-entrega; 8 testes: novo/duplicado/ausente/aceita-int, e 4 no não-fallback para processamento silencioso em erro)
decisoes:
  - id: p01-sub5-idempotency-erro-vira-resultado-recuperavel-sem-efeito
    motivo: "Passo 4 do plano fechado: 'erro em caminho com efeito' (Firestore indisponível, ou backend de teste sem suporte a transação) deixa de retornar True (permitir processamento) e passa a retornar um dos dois resultados de erro explícitos -- RESULTADO_ERRO_CONFIGURACAO (sem hasattr(db, 'transaction')) e RESULTADO_ERRO_TRANSACAO (falha real da transação). Em nenhum dos dois casos o documento de idempotência é escrito. O único chamador real (githubWebhook) responde 503 nesses casos -- não processa o evento agora (evita duplicar a anotação no diário de tarefas vinculadas se a causa raiz for uma entrega repetida coincidindo com uma falha transitória do Firestore) e sinaliza falha explícita para a entrega poder ser repetida depois (redelivery manual ou automática do GitHub), em vez de responder 200 como se tivesse sido tratada."
    autoridade: existente_ou_nova
  - id: p01-sub5-limite-200kb-do-conector-argos-bloqueia-edicao-de-main-py
    motivo: "Achado de infraestrutura, não de produto: functions/main.py (683664 bytes) está acima do limite de 200000 bytes que argos_ler_arquivo_repositorio e argos_escrever_arquivo_repositorio aplicam -- confirmado ao vivo pela recusa 413 do próprio Argos na tentativa de leitura. Isso bloqueia QUALQUER edição futura a main.py pelo caminho normal desta sessão (Argos MCP), não só esta. Não tentei contornar via push local (fora da diretriz padrão desta sessão, sem credencial configurada) nem tentei dividir main.py sozinha (refactor real, fora de escopo, decisão de arquitetura que não me cabe tomar sozinha). Levado ao André via pergunta direta com 4 opções; ele escolheu aplicar o diff manualmente desta vez. Fica como pendência de infraestrutura para o André decidir se/quando quiser resolver de raiz (dividir main.py em módulos menores, ou uma ferramenta Argos com suporte a patch/diff para arquivos grandes)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && ../venv/bin/python3 -m unittest discover -p 'test_*.py' -q"
  resultados:
    - "Antes desta sub-entrega (main pós-merge da PR #212, commit f97978b90): 1473 testes, 8 falhas + 2 erros -- confirmados PRÉ-EXISTENTES (mesmos de sempre: test_deteccao_subproduto.py, test_gmail_bill_pdf, test_mp4_repair)."
    - "Depois desta sub-entrega (com o main.py exatamente como o André commitou, verificado por git fetch): 1483 testes (10 novos: 8 em test_idempotency.py, 2 em test_github_webhook.py), mesmas 8 falhas + 2 erros pré-existentes, zero regressão nova."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre o diff completo (antes do André aplicar main.py manualmente -- revisou o diff de main.py como texto, não como arquivo lido via Argos). Veredito explícito: 'safe to ship'. Verificou contra o código-fonte real da biblioteca google-cloud-firestore instalada que o mock de Transaction em test_idempotency.py é fiel ao protocolo real. Confirmou empiricamente que os testes pegam a regressão de verdade: reintroduziu deliberadamente o bug antigo (retornar RESULTADO_NOVO em vez de erro) e viu exatamente os 3 testes esperados falharem, depois restaurou o fix. Dois achados não-bloqueantes, nenhum corrigido (ambos aceitos como característica inerente ao design, não regressão): (1) update_id int 0 (falsy) seria tratado como 'nada a deduplicar' -- inalcançável hoje (delivery_id do GitHub é sempre string não vazia), comportamento inalterado do código original; (2) por o registro de idempotência e o efeito (anotar no diário) serem dois passos não-transacionais separados, um resultado ambíguo de commit (escrita no Firestore bem-sucedida no servidor mas cliente vê timeout) pode em teoria descartar permanentemente um evento -- inerente à decisão do próprio passo 4 do plano (preferir descartar/exigir retry a duplicar silenciosamente), e webhooks de repositório do GitHub não são reentregues automaticamente por padrão (confirmado via docs.github.com/webhooks/using-webhooks/handling-failed-webhook-deliveries)."
  - "Após o André aplicar main.py manualmente (commit 6ec1137cf): confirmado por git fetch + git diff que o conteúdo bate byte a byte com o diff que eu tinha preparado (mesmo blob sha c8a05f3f2... do main.py que eu já tinha verificado localmente antes do bloqueio do Argos). Suíte completa rodada de novo contra o main.py real dele (não uma simulação) antes de enviar os 2 arquivos de teste restantes -- ver testes.resultados acima."
  - "Todos os arquivos possíveis de enviar via Argos (idempotency.py, test_github_webhook.py, test_idempotency.py) enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificação de hash local (git hash-object) contra o sha retornado, batendo exatamente. main.py foi commitado manualmente por André diretamente na branch remota, verificado por leitura via git fetch (não pelo Argos, que recusa o arquivo)."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: passo 4 de P01 (erro de idempotência em caminho com efeito vira resultado recuperável sem efeito)."
  - "NOVA, de infraestrutura: functions/main.py (683664 bytes) excede o limite de 200000 bytes do conector Argos para leitura E escrita -- bloqueia qualquer edição futura a main.py pelo caminho normal (Argos MCP) desta sessão, não só a desta sub-entrega. Duas saídas possíveis, nenhuma decidida ainda: dividir main.py em módulos menores (refactor real), ou uma ferramenta Argos com suporte a leitura/escrita parcial (patch/diff) para arquivos grandes. Por ora, a saída usada foi o André aplicar o diff manualmente -- funciona, mas não escala para edições maiores em main.py."
  - "P01 passos 5-10 do plano continuam abertos: mcp_jobs (reivindicação sobre leitura atual, estado de erro normalizado), claim de confirmação abandonado, regras Firestore/deploy.yml (mesmo bloqueio de PAT sem escopo workflow já registrado para P00), relatório de reconciliação final do pacote."
  - "Todas as pendências já registradas nos blocos anteriores que não foram tocadas por esta sub-entrega continuam abertas (ver blocos de P01/P02 acima)."
proximo_pacote: "P01 -- próximo passo natural na ordem do plano é o passo 5 (mcp_jobs.py: reivindicação sobre leitura atual, estado de erro normalizado, resultado estruturado e timestamp de expiração). Antes de escolher sozinha, porém, vale levar ao André a pendência nova de infraestrutura (limite de 200KB do Argos em main.py) como pergunta separada de arquitetura -- não é um passo de engenharia autocontido como os anteriores, é uma decisão sobre a própria ferramenta de trabalho."
```
