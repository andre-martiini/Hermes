```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 5621eb5a6b1f7de36b4c331ffbca1fd148f61b33
pacote: "P02 (sub-entrega 4/N — orçamento no mandato, passo 8 do plano, parcial)"
# Antes de iniciar: a rodada de review do @codex sobre a sub-entrega 3/N
# (comentário https://github.com/andre-martiini/Hermes/pull/192#issuecomment-5573743251,
# postado ~17:09 UTC) foi tratada como exaurida sem resposta confirmável —
# GitHub REST API continuou bloqueada ("GitHub access to this repository is
# not enabled for this session"), e um WebFetch fresco em
# https://github.com/andre-martiini/Hermes/pull/192 (17:14 UTC, mais de 5min
# depois do comentário) ainda retornou conteúdo desatualizado (comentário de
# 14:53:55 UTC, sem nada após 17:09 UTC) — mesma limitação de cache já
# documentada nas sub-entregas anteriores. Seguiu-se para esta sub-entrega
# sem esperar 5 horas (regra de espera é entre PACOTES, não entre
# sub-entregas do mesmo pacote).
#
# Escopo: fecha o passo 8 do plano ("revalidar versão, revogação, escopo e
# orçamento no despacho") NA DIMENSÃO ORÇAMENTO apenas — versão (base_version
# em preparar_politica), revogação (Mandato.revogado) e escopo
# (destinatarios_recursos/classes_conteudo_permitidas) já eram revalidados a
# cada chamada de mandato_cobre()/avaliar() desde a sub-entrega 1/N (função
# pura, sem cache — cada chamada resolve tudo de novo). O que faltava,
# documentado explicitamente como pendência desde a sub-entrega 1/N (achado
# da revisão adversarial da 4ª rodada do Codex, PR #191), era orçamento:
# PolicyRequest.orcamento_restante existia no contrato mas não era lido em
# lugar nenhum de autonomy/policy.py. Escopo deliberadamente pequeno: só o
# motor puro (Mandato.orcamento_maximo + checagem em mandato_cobre()) —
# mandatos persistidos continuam sem nenhuma fonte real (sub-entrega futura),
# então este fix não é alcançável hoje por nenhum canal MCP, mesma situação
# em que limite_por_janela esteve até ser fechado.
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T17:17:00Z"
fim: "2026-09-07T17:35:00Z"
arquivos_alterados:
  - functions/autonomy/contracts.py
  - functions/autonomy/policy.py
  - functions/test_policy.py
  - functions/test_contracts.py
  - docs/autonomia/execucao.md
decisoes:
  - id: p02-sub4-orcamento-maximo-opt-in-por-mandato
    motivo: "Mandato.orcamento_maximo é opcional (default None) e opt-in: um mandato só precisa declarar teto quando a finalidade tem dimensão financeira de verdade (ex.: 'consumir até o teto aprovado', seção 5.3 do plano) — mandatos puramente não-financeiros (ex.: 'cobrar confirmação de recebimento') não são afetados pela checagem nova. Mesma divisão de responsabilidade já usada para limite_por_janela/usos_na_janela_atual: o tipo só declara o teto, um wrapper com I/O ainda não implementado resolve o saldo real (consumo até agora vs. teto) e preenche PolicyRequest.orcamento_restante antes de incluir o mandato em mandatos_aplicaveis."
    autoridade: existente_ou_nova
  - id: p02-sub4-achado-adversarial-nan-bypassa-fail-closed
    motivo: "Achado real da revisão adversarial, verificado por reprodução direta antes de aceitar: a primeira versão da checagem usava 'if request.orcamento_restante <= 0: return False'. float('nan') faz TODA comparação (<=, <, >, >=, ==) retornar False em Python — então nan <= 0 é False, e nan is None também é False, então um saldo NaN não caía em nenhum dos dois `return False` e passava como se fosse um saldo positivo válido, exatamente o oposto do fail-closed que a checagem existe para garantir. Corrigido para 'if not (request.orcamento_restante > 0): return False', que rejeita NaN corretamente (nan > 0 já é False, a negação vira True). O revisor confirmou o caminho de entrada real hoje: json.loads aceita o token NaN por padrão (json.loads('{\"x\": NaN}') funciona), e tools/hermes_tools.py:2202 (_principal_simulado) repassa pedido.get('orcamento_restante') para PolicyRequest sem validar tipo — então um pedido de simular_politica via MCP com \"orcamento_restante\": NaN chega em mandato_cobre() sem alteração. Blast radius hoje é limitado (simular_politica é só leitura/simulação, e nenhum canal real popula mandatos_aplicaveis ainda), mas seria um bypass real assim que um wrapper de resolução de orçamento for implementado."
    autoridade: existente_ou_nova
  - id: p02-sub4-achado-adversarial-doc-summary-incompleto
    motivo: "Achado da revisão adversarial, nitpick: a frase-resumo no topo da docstring de mandato_cobre() ('Um mandato cobre um pedido se: não revogado, ainda válido, dentro do limite de uso da janela...') não mencionava orçamento entre as condições, embora a checagem detalhada estivesse descrita um parágrafo abaixo — corrigido, orçamento agora tem seu próprio parágrafo logo após a frase-resumo, referenciando onde o gap foi fechado."
    autoridade: existente_ou_nova
  - id: p02-sub4-achado-adversarial-teste-default-faltando
    motivo: "Achado da revisão adversarial, nitpick: test_contracts.py::TestDefaultsDeContrato testava os defaults de Mandato (revogado, valido_ate, limite_por_janela, usos_na_janela_atual) mas não tinha sido estendido com orcamento_maximo — adicionado self.assertIsNone(m.orcamento_maximo), mesmo padrão dos irmãos."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_policy test_contracts -v"
  resultados:
    - "Python (unittest, suíte completa): 1286/1286 passando (1280 anteriores da sub-entrega 3/N + 6 testes novos em TestMandatoCobre — test_policy.py: saldo desconhecido, esgotado (0.0), negativo, NaN, positivo, sem teto declarado —, contagem conferida por AST, não de memória; 0 regressões). Suíte completa rodada antes E depois da correção do achado NaN, para confirmar que o fix não quebrou nada."
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação, instruído a ler o código real, rodar a suíte de verdade e reproduzir achados por execução, não só inspeção): encontrou os 4 achados listados acima (1 bug real, 1 gap de validação de tipo pré-existente registrado como pendência, 2 nitpicks de documentação/teste), todos verificados manualmente contra o código atual antes de aceitar (achado NaN reproduzido diretamente: nan <= 0 e nan is None ambos False)."
  - "PR #192 (https://github.com/andre-martiini/Hermes/pull/192) — mesma PR aberta desde a sub-entrega 1/N (branch claude/p02-autonomy-policy-contracts); commits desta sub-entrega adicionados ao mesmo branch. Comentário https://github.com/andre-martiini/Hermes/pull/192#issuecomment-5574002387 documenta esta sub-entrega (achados, arquivos alterados, contagem de testes); @codex review pedido novamente ao final."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Validação de tipo de PolicyRequest.orcamento_restante no wrapper MCP (tools/hermes_tools.py:2202, _principal_simulado) não foi adicionada nesta sub-entrega — mesma folga que missao/sensibilidade já têm hoje (não é regressão desta sub-entrega, é um gap pré-existente que esta sub-entrega apenas tornou operacionalmente relevante pela primeira vez). Um valor não numérico levanta TypeError, capturado pelo except Exception amplo ao redor de simular_politica (degrada para mensagem de erro, não crash) — mas não impede um NaN especificamente (numérico, sem levantar exceção) de escapar até mandato_cobre(), onde a checagem desta sub-entrega agora trata corretamente. Corrigir a validação de tipo no wrapper fica para quando hermes_tools.py for revisitado por outro motivo, mesmo raciocínio de escopo já aplicado ao bug de tipo em preparar_politica na sub-entrega 3/N."
  - "P02 segue MATERIALMENTE em aberto — dos passos 1-9 do plano (seção 'Unificar identidade e política de autonomia'), esta sub-entrega fecha a dimensão orçamento do passo 8. Ainda não endereçados: passo 1 (taxonomia completa de principals span todos os canais — só o canal MCP tem _principal_mcp desde a sub-entrega 2/N; tools/tool_context.py, mcp_oauth.py, web, Telegram e voz seguem sem o modelo de identidade unificado), passo 2 (evolução de claims/scopes OAuth), passo 3 (vínculo autenticado executor→capacidades), passo 8 nas outras três dimensões — versão/revogação/escopo já são revalidados a cada chamada da função pura (sem cache), mas isso só importa de verdade quando houver um canal real chamando avaliar()/mandato_cobre() fora de teste, o que ainda não existe."
  - "Decisão de design a levar ao André quando o PACOTE P02 inteiro estiver completo (não antes — mantido das sub-entregas 1/N, 2/N e 3/N, ainda não é hora): o gate de origem_humana nos defaults da matriz PREPARACAO_INTERNA/ESCRITA_INTERNA_REVERSIVEL (rodadas 3 e 5 do Codex, exige também eh_dono()) — a pergunta de fundo ainda vale: origem_humana deveria mesmo ter default True no contrato? Esta sub-entrega não toca nisso."
  - "Todas as pendências já registradas nos blocos das sub-entregas 1/N, 2/N e 3/N que não foram tocadas nesta sub-entrega continuam abertas: Mandato.classes_conteudo_permitidas ainda é texto livre sem enum fechado, Mandato.usos_na_janela_atual sem wrapper de I/O real (mesma situação agora de Mandato.orcamento_maximo — declarado mas sem nada que resolva o saldo real), canais além de MCP (web/Telegram/voz) não consultam autonomy.policy, o bug de tipo em autonomy/policy.py::preparar_politica (contornado na wrapper, não corrigido no motor) segue latente."
proximo_pacote: "P02 (sub-entrega 5/N — candidata a decidir: passo 1, taxonomia de principals nos demais canais, ou seguir fechando o passo 8 nas outras dimensões quando houver um canal real consumindo avaliar())"
```

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 5621eb5a6b1f7de36b4c331ffbca1fd148f61b33
pacote: "P02 (sub-entrega 5/N — principal_de() compartilhado, passo 1 do plano, parcial)"
# Antes de iniciar: a rodada de review do @codex sobre a sub-entrega 4/N
# (comentário https://github.com/andre-martiini/Hermes/pull/192#issuecomment-5574002387,
# postado ~17:38-17:40 UTC) foi tratada como exaurida sem resposta
# confirmável após DUAS checagens (17:44 e 17:49 UTC) — GitHub REST API
# continuou bloqueada ("GitHub access to this repository is not enabled
# for this session"), e a segunda checagem por WebFetch retornou
# timestamps no FUTURO (eventos às 17:53/17:56 UTC quando a própria
# checagem era às 17:49 UTC) — sinal inequívoco de que o conteúdo não é
# confiável (cache desatualizado misdatado, ou extração garantida errada
# pelo modelo pequeno do WebFetch), descartado sem virar achado. Seguiu-se
# para esta sub-entrega sem esperar 5 horas (regra de espera é entre
# PACOTES, não entre sub-entregas do mesmo pacote).
#
# Escopo: avança o passo 1 do plano ("definir principals distintos... span
# todos os canais") sem tentar religar nenhum canal novo de uma vez — algo
# que exigiria decidir o TipoPrincipal correto de Telegram,
# outbox_aprovacao.py, revisao_semanal.py e mcp_jobs.py, cada um com
# ambiguidades genuínas não investigadas a fundo ainda. Em vez disso,
# extraída para tools/tool_context.py::principal_de() a lógica que já
# existia hardcoded em mcp_server.py::_principal_mcp (uid/canal ->
# Principal, default de origem_humana por tipo) — puramente aditivo/
# refactor, sem mudança de comportamento no único canal já religado (MCP),
# preparando o terreno para os canais futuros sem decidir por eles agora.
estado: pronto_para_revisao
# Estados: nao_iniciado, em_execucao, pronto_para_revisao,
# validado, publicado, ativo, bloqueado, opt_in
inicio: "2026-09-07T17:49:00Z"
fim: "2026-09-07T18:08:00Z"
arquivos_alterados:
  - functions/tools/tool_context.py
  - functions/mcp_server.py
  - functions/test_tool_context.py (novo)
  - functions/atencao.py
  - functions/test_atencao.py
decisoes:
  - id: p02-sub5-principal-de-tipo-sempre-explicito
    motivo: "principal_de(ctx, tipo, *, origem_humana=None) exige tipo como argumento explícito do CHAMADOR, nunca inferido de ctx.canal sozinho. Achado que motivou essa escolha de design: canal=\"mcp\" é usado tanto por mcp_server.py (cliente MCP hospedado, dono acompanhando em tempo real -> CLIENTE_ASSISTIDO) quanto por mcp_jobs.py::on_mcp_job_created (job assíncrono de Firestore continuando uma tool longa depois que o request HTTP original já terminou, sem garantia de que o dono ainda está olhando) -- um resolvedor por texto de canal teria classificado os dois da mesma forma, escondendo exatamente a distinção que TipoPrincipal existe para preservar. mcp_jobs.py hoje não constrói Principal nenhum (não foi religado nesta sub-entrega) -- o achado é preventivo, documentado na docstring da função para quem for religar esse canal depois."
    autoridade: existente_ou_nova
  - id: p02-sub5-principal-mcp-delega-sem-mudar-comportamento
    motivo: "mcp_server.py::_principal_mcp passa a delegar para principal_de(ctx, TipoPrincipal.CLIENTE_ASSISTIDO, origem_humana=True) -- mesmo nome, mesma assinatura, mesma docstring (com um parágrafo novo explicando a delegação). test_mcp_server.py::TestPrincipalMcp, já existente e não alterado nesta sub-entrega, prova que o resultado não mudou. Verificado pela revisão adversarial rodando a suíte real, não só lendo o código."
    autoridade: existente_ou_nova
  - id: p02-sub5-achado-incidental-toolcontext-db-errado-em-atencao
    motivo: "Achado incidental da revisão adversarial (fora do diff revisado, encontrado ao rastrear futuros call sites de principal_de): atencao.py::resolver_item, chamado sem ctx explícito (o caso comum) e com acao_id preenchido, construía ToolContext(db=db, ...) -- campo errado, o dataclass usa _db (db só existe como property de leitura). ToolContext(db=db, ...) levantava TypeError ANTES de chamar registrar_no_diario, engolido em silêncio pelo except Exception ao redor -- todo desfecho resolvido com acao_id preenchido, chamado sem ctx explícito, perdia a nota no diário da ação sem nenhum sinal de erro. Reproduzido diretamente antes de aceitar (ToolContext(db=object()) -> TypeError). Corrigido para _db=db, com teste de regressão que falhava antes do fix (test_resolver_item_com_acao_id_registra_no_diario). Pré-existente, não introduzido por esta sub-entrega; consertado por ser pequeno, bem entendido e diretamente relevante ao escopo (mesmo arquivo citado como futuro call site de principal_de)."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && venv/bin/python -m unittest discover -s . -p 'test_*.py'"
    - "cd functions && venv/bin/python -m unittest test_tool_context test_mcp_server test_atencao -v"
  resultados:
    - "Python (unittest, suíte completa): 1296/1296 passando (1286 anteriores da sub-entrega 4/N + 9 testes novos em test_tool_context.py -- default de origem_humana por tipo para os 5 TipoPrincipal, override explícito, passthrough de uid/canal -- + 1 teste de regressão em test_atencao.py; contagem conferida por AST, não de memória; 0 regressões)."
evidencias:
  - "Revisão adversarial por sub-agente independente (general-purpose, sem contexto prévio da implementação, instruído a ler o diff real, rodar a suíte de verdade e verificar cada claim por execução, não só inspeção): nenhum defeito encontrado no diff revisado -- confirmou a lógica de principal_de correta (incluindo o caso origem_humana=False explícito para DONO_INTERATIVO, provado seguro por leitura de autonomy/policy.py::_decisao_padrao_por_classe -- o override só pode degradar para PREPARE_ONLY/REQUIRE_APPROVAL, nunca conceder ALLOW indevido, porque eh_dono() depende só de tipo), verificou a claim do mcp_jobs.py lendo o arquivo real, checou ausência de ciclo de import (autonomy/contracts.py e autonomy/policy.py não importam nada de tools/, confirmado por execução direta), e confirmou que os 9 testes novos exercitam a função real sem mocks tautológicos. Rodou a suíte completa: 1295/1295 (antes do fix incidental de atencao.py) e 1296/1296 (depois). Achado incidental (fora do diff, ver decisão acima) verificado por reprodução direta antes de ser aceito e corrigido."
  - "PR #192 (https://github.com/andre-martiini/Hermes/pull/192) -- mesma PR aberta desde a sub-entrega 1/N (branch claude/p02-autonomy-policy-contracts); commits desta sub-entrega adicionados ao mesmo branch. Comentário https://github.com/andre-martiini/Hermes/pull/192#issuecomment-5574275337 documenta esta sub-entrega (escopo, achado incidental, contagem de testes); @codex review pedido novamente ao final."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "Passo 1 do plano segue MATERIALMENTE em aberto: só o canal MCP constrói Principal e passa pelo preflight de política. Telegram (hermes_core_logic.py, closures de ativar/desativar/consultar modo secretário), outbox_aprovacao.py, revisao_semanal.py e mcp_jobs.py continuam sem construir Principal nenhum. Decidir o TipoPrincipal correto de cada um fica para sub-entrega futura -- alguns são genuinamente ambíguos (ex.: mcp_jobs.py::on_mcp_job_created é sempre RUNNER_SERVICO, ou depende de quanto tempo passou desde o request HTTP original que criou o job?) e podem precisar de input do André em vez de decisão unilateral."
  - "Religar esses canais no preflight de autonomy.policy.avaliar() é o passo 6 do plano, sequenciado ainda mais adiante -- deliberadamente não tentado nesta sub-entrega, mesmo tendo o mecanismo (principal_de) pronto para uso."
  - "P02 segue MATERIALMENTE em aberto nos passos 2 (evolução de claims/scopes OAuth), 3 (vínculo autenticado executor->capacidades), e nas dimensões restantes do passo 8 (só orçamento foi fechado, na sub-entrega 4/N; versão/revogação/escopo já são revalidados a cada chamada da função pura, mas isso só importa de verdade quando um canal real chamar avaliar()/mandato_cobre() fora de teste)."
  - "Decisão de design a levar ao André quando o PACOTE P02 inteiro estiver completo (não antes -- mantido das sub-entregas 1/N a 4/N, ainda não é hora): o gate de origem_humana nos defaults da matriz PREPARACAO_INTERNA/ESCRITA_INTERNA_REVERSIVEL (rodadas 3 e 5 do Codex, exige também eh_dono()) -- a pergunta de fundo ainda vale: origem_humana deveria mesmo ter default True no contrato? Esta sub-entrega não toca nisso."
  - "Todas as pendências já registradas nos blocos das sub-entregas 1/N a 4/N que não foram tocadas nesta sub-entrega continuam abertas: validação de tipo de PolicyRequest.orcamento_restante no wrapper MCP (tools/hermes_tools.py, _principal_simulado), Mandato.classes_conteudo_permitidas ainda texto livre sem enum fechado, Mandato.usos_na_janela_atual e Mandato.orcamento_maximo sem wrapper de I/O real, o bug de tipo em autonomy/policy.py::preparar_politica (contornado na wrapper, não corrigido no motor) segue latente."
proximo_pacote: "P02 (sub-entrega 6/N -- candidata a decidir: continuar o passo 1 decidindo o TipoPrincipal de um canal específico, ou avançar os passos 2/3 do plano quando houver mais clareza sobre OAuth/claims)"
```

---
