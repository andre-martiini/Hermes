# Registro de execução (arquivo) — plano-hermes-autonomo-2026-09-06 — P01 sub-entrega 3/N a 4/N

Arquivo dos blocos P01 sub-entrega 3/N e 4/N, movidos para cá em 2026-09-09
(durante a sub-entrega P01 7/N, mcp_server.py -- claim de confirmação
abandonado). Motivo: o arquivo ativo (docs/autonomia/execucao.md, então com
46087 bytes) somado ao novo bloco desta sub-entrega (9965 bytes) chegaria a
56052 bytes -- acima do limiar de ~50KB que a sub-entrega P01 5/N registrou
como arriscado para uma escrita confiável via Argos MCP (ver a decisão
p01-sub5-corrupcao-silenciosa-na-retranscricao-e-arquivamento-preventivo,
ainda no arquivo ativo). Em vez de arquivar só o bloco mínimo necessário e
repetir esta operação na sub-entrega seguinte, os dois blocos mais antigos
do arquivo ativo (P01 sub-entrega 3/N e 4/N) foram movidos juntos para este
arquivo NOVO e separado -- mesmo raciocínio já registrado nos cabeçalhos de
execucao-archive-p02-sub12-a-sub16.md e execucao-archive-p02-sub17.md: cada
escrita via Argos precisa reenviar o arquivo inteiro (sem diff/patch),
então um arquivo de arquivo que só cresce eventualmente fica grande demais
para qualquer escrita futura o tocar, mesmo só para adicionar uma nota --
por isso um arquivo de arquivo novo a cada corte, nunca conteúdo anexado a
um dos arquivos de arquivo já existentes (nenhum dos três anteriores foi
tocado nesta operação). Nenhum conteúdo foi perdido -- os blocos abaixo são
cópia byte-a-byte do arquivo ativo de antes deste quarto corte, extraída
por script (não retranscrita à mão), com hash conferido antes e depois do
envio. O arquivo ativo (docs/autonomia/execucao.md) continua sendo a fonte
de verdade a partir da sub-entrega P01 5/N em diante.

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
