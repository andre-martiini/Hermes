# Registro de execução — plano-hermes-autonomo-2026-09-06

Um bloco por pacote (P00–P18), no formato da seção 14.2 do plano. Cada pacote novo é acrescentado ao final; nenhum bloco anterior é reescrito depois de `validado`. Sem segredos nem conteúdo privado — apenas referências a artefatos e IDs.

**Blocos P00 a P02 sub-entrega 11/N foram movidos para
docs/autonomia/execucao-archive-p00-a-p02sub11.md em 2026-09-09 (P02
sub-entrega 15/N); blocos P02 sub-entrega 12/N a 16/N foram movidos para
o mesmo arquivo também em 2026-09-09, durante a correção da sub-entrega
P01 5/N (uma escrita anterior tinha derrubado silenciosamente um bloco
inteiro na retranscrição manual de um arquivo de 85701 bytes) — ver o
cabeçalho do arquivo de arquivo para o relato completo.** Nenhum conteúdo
foi perdido; é uma relocação, não uma edição. Este arquivo continua sendo
a fonte de verdade para tudo a partir daqui.

---

```yaml
plano: plano-hermes-autonomo-2026-09-06
base_commit: 54a873131cddf8ab6d5d6d700edff0c5680cbb61
pacote: "P02 sub-entrega 17/N -- autonomy/mandatos_io.py (wrapper de I/O de Mandato) religando liberar_rascunhos_promovidos() ao motor de política real (avaliar()/mandato_cobre()), não mais só o interruptor global de EstadoAutonomia"
# Esta sub-entrega é a continuação direta da pendência central deixada
# aberta pela sub-entrega 15/N (id
# p02-sub15-preflight-estado-autonomia-em-vez-de-decisao-piso-completo): o
# wrapper de I/O que resolve um Mandato real a partir do Firestore, sem o
# qual decisao_piso()/avaliar() não podia ser chamado de verdade em
# liberar_rascunhos_promovidos sem desligar por completo o envio autônomo.
#
# Essa pendência tinha duas perguntas de PRODUTO em aberto (que mandatos
# existem hoje na prática para o Hermes; que categorias de conteúdo o
# Hermes pode usar para falar com terceiros sem confirmação humana por
# instância) que esta sessão NÃO decidiu sozinha. André pediu uma PROPOSTA
# ("me faça uma proposta para estas duas questões"), entregue via PR #208
# (docs/autonomia/proposta-p02-mandato-io-wrapper.md): investigação
# encontrou que as duas perguntas já tinham resposta em produção, só não
# modelada como Mandato -- system/mcp_access.tipos_promovidos (escrito por
# promocao_autonomia.decidir_promocao_autonomia, um mandato de fato
# data-driven e já supervisionado por decisão explícita do André) já É,
# na prática, um mandato por classe de conteúdo. Proposta central: ligar
# Mandato a esse mecanismo já vivo, não inventar taxonomia nova. Duas
# decisões de escopo ficaram para o André (não resolvidas sozinha): (1)
# destinatarios_recursos -- "*" (qualquer destinatário, preserva
# comportamento atual) ou lista fechada por tipo; (2) valido_ate -- (a)
# janela rolante automática, (b) perguntar prazo ao aceitar promoção, ou
# (c) revalidação periódica pela taxa de aprovação. André respondeu em
# 09/09/2026: "pode seguir com suas recomendações, e qualquer
# destinatário" -- aprovando "*" e a opção (a) (janela rolante), ambas
# minhas recomendações na proposta. Esta sub-entrega implementa
# exatamente o que a proposta descrevia em "Se aprovado, o que eu
# implementaria a seguir".
estado: pronto_para_revisao
inicio: "2026-09-09T09:10:00Z"
fim: "2026-09-09T09:50:00Z"
arquivos_alterados:
  - functions/autonomy/mandatos_io.py (novo -- mandato_tipo_promovido() resolve um Mandato a partir de system/mcp_access.tipos_promovidos, com valido_ate em janela rolante e destinatarios_recursos=("*",), por decisão do André)
  - functions/outbox_aprovacao.py (liberar_rascunhos_promovidos religado a avaliar()/mandato_cobre() de verdade por rascunho, com cache por tipo dentro da chamada; novo helper _degradar_rascunho_promovido_sem_mandato, transacional, para quando o mandato não cobre mais na hora da liberação)
  - functions/test_mandatos_io.py (novo -- 14 testes)
  - functions/test_outbox_aprovacao.py (preflight existente ganha semeadura de tipos_promovidos nos testes de caminho feliz + 8 testes novos: mandato ainda cobre, tipo nunca promovido, tipo revogado entre criação e liberação, cache por tipo, tipo "outro" não derruba o lote, degrade transacional não sobrescreve descarte concorrente, degrade funciona/não funciona sem suporte a transação)
  - functions/test_promocao_autonomia.py (1 teste ajustado para semear tipos_promovidos; mock ganha .add() para registrar_decisao)
decisoes:
  - id: p02-sub17-mandato-io-liga-tipos-promovidos-nao-inventa-taxonomia
    motivo: "Ver docs/autonomia/proposta-p02-mandato-io-wrapper.md para o raciocínio completo e a tabela de mapeamento campo-a-campo. Resumo: mandato_tipo_promovido(db, tipo) lê system/mcp_access.tipos_promovidos NA HORA da chamada (não confia em nenhum dado decidido no passado) e constrói mandato_id=f'tipo_promovido:{tipo}', finalidade=f'envio_promovido:{tipo}' (identificador estável, não frase livre), classes_conteudo_permitidas=(tipo,), destinatarios_recursos=('*',) e valido_ate=agora+60 dias (janela rolante, recalculada a cada chamada, nunca persistida) -- as duas últimas por decisão explícita do André em 09/09/2026, seguindo minha recomendação na proposta. limite_por_janela/orcamento_maximo/horario_permitido_* ficam None (sem dado real por trás hoje) -- autonomy.policy.mandato_cobre() já trata None nesses campos como 'sem restrição adicional', não como dado ausente que precisaria falhar fechado (essas checagens só disparam quando o campo está DECLARADO). origem_autorizacao tenta uma referência legível (data de decidir_promocao_autonomia, se disponível; genérica caso contrário) -- não-crítico, nunca afeta se o mandato cobre."
    autoridade: existente_ou_nova
  - id: p02-sub17-liberar_rascunhos_promovidos-reavalia-mandato-na-hora
    motivo: "Antes desta sub-entrega, liberar_rascunhos_promovidos confiava no status aguardando_janela do próprio documento -- decidido no PASSADO, na criação do rascunho (criar_rascunho verificando tipos_promovidos naquele momento). Agora, cada rascunho pronto para liberar passa por autonomy.policy.avaliar() de verdade, com PolicyRequest.classe_efeito=COMPROMISSO_TERCEIROS, missao=f'envio_promovido:{tipo}', sensibilidade=tipo, principal=Principal(tipo=RUNNER_SERVICO) (worker sem sessão interativa -- 'nunca deve conseguir conceder a si mesmo uma permissão', contracts.py), e mandatos_aplicaveis=(mandato_tipo_promovido(db, tipo),) se houver. Fecha a janela em que o André revoga um tipo de tipos_promovidos DEPOIS de um rascunho já ter sido criado como promovido mas ANTES de a janela de cancelamento vencer -- sem esta reavaliação, o rascunho seria enviado mesmo já não estando mais coberto por mandato nenhum. Cache de Mandato por tipo dentro de uma única chamada (não entre chamadas) evita reler Firestore uma vez por rascunho quando vários do mesmo tipo estão prontos no mesmo ciclo -- confirmado por teste com spy (test_dois_rascunhos_mesmo_tipo_reusa_mandato_cacheado)."
    autoridade: existente_ou_nova
  - id: p02-sub17-mandato-nao-cobre-degrada-para-manual-nao-envia-nem-descarta
    motivo: "Quando avaliar() não retorna ALLOW (tipo revogado, ou qualquer outro motivo que o motor decida diferente), o rascunho volta para STATUS_AGUARDANDO (aprovação manual) em vez de ser enviado ou descartado silenciosamente -- mesmo padrão já usado em criar_rascunho para 'falha_entrega_card_telegram'. Preserva o rascunho (o dono ainda pode aprovar manualmente se quiser) em vez de perdê-lo, e nunca envia sem cobertura de mandato."
    autoridade: existente_ou_nova
  - id: p02-sub17-achado-bloqueante-outro-tratado-como-nao-promovido
    motivo: "Achado BLOQUEANTE da revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação): Mandato.__post_init__ (contracts.py, desde a sub-entrega 15/N) levanta ValueError quando classes_conteudo_permitidas contém 'outro' -- e 'outro' é o DEFAULT de tipo para todo rascunho sem tipo explícito (outbox_aprovacao.criar_rascunho, tools/hermes_tools.py). promocao_autonomia.tipos_elegiveis_para_promocao() não exclui 'outro' da varredura por volume/taxa de aprovação -- um humano pode legitimamente aceitar essa promoção via decidir_promocao_autonomia(db, 'outro', 'aceitar'), ação já suportada sem validação extra ali. Sem guard, mandato_tipo_promovido('outro') levantava sem ninguém capturar no chamador, derrubando o LOTE INTEIRO de liberar_rascunhos_promovidos -- nenhum rascunho daquele ciclo seria processado, nem os de tipos diferentes e válidos, e o mesmo erro se repetiria em todo ciclo seguinte até intervenção manual no Firestore. Corrigido: mandato_tipo_promovido captura ValueError da construção do Mandato e retorna None (trata como 'não promovido de verdade' -- consistente com o próprio contrato da função e com a seção 5.3 do plano). Verificado com reprodução ao vivo antes da correção (dois rascunhos, um tipo='outro' promovido, outro tipo válido promovido, ambos no mesmo lote -- o segundo nunca era alcançado) e teste de regressão depois (test_tipo_outro_promovido_nao_derruba_o_lote_e_degrada_so_esse_rascunho). Segunda rodada de revisão (agente novo, sem contexto da primeira) confirmou a correção completa: único ponto de produção que constrói Mandato(...), catch escopado só a ValueError, nenhuma outra validação em __post_init__ escaparia."
    autoridade: existente_ou_nova
  - id: p02-sub17-achado-should-fix-degradar-e-transacional
    motivo: "Achado should-fix da mesma revisão adversarial: a primeira versão do degrade fazia um db.collection(...).update() cru, sem transação nem revalidação de status -- descartar_rascunho() (acionado por um humano tocando 'Cancelar' no Telegram) já documenta que precisa ser transacional para exclusão mútua com liberar_rascunhos_promovidos (achado A04, sub-entrega anterior a esta). Entre a consulta em query.stream() no topo de liberar_rascunhos_promovidos e o degrade alcançar um documento específico -- intervalo alargado por esta própria sub-entrega, que agora faz leituras extras + escrita em policy_decisions por rascunho antes de chegar lá -- um humano podia cancelar via Telegram nesse meio-tempo, e o .update() cru sobrescreveria STATUS_DESCARTADO de volta para aguardando_aprovacao, ressuscitando silenciosamente um rascunho que o dono já tinha descartado -- violando o 'veto humano inegociável' que avaliar_liberacao_promovidos documenta. Corrigido: novo helper _degradar_rascunho_promovido_sem_mandato, transacional (mesmo padrão de aprovar_rascunho/descartar_rascunho), relê o status DENTRO da transação e só escreve se ainda for aguardando_janela; caso contrário é no-op (defere para o caminho concorrente que já decidiu). Testado isoladamente (test_degradar_e_transacional_nao_sobrescreve_descarte_concorrente: semeia um doc já descartado, confirma que o helper não o toca) e no caminho feliz. Segunda rodada de revisão confirmou: relê dentro da transação (não usa o dict cacheado do loop externo), revalidação de status correta, caminhos sem-suporte-a-transação/falha-de-transação não propagam exceção."
    autoridade: existente_ou_nova
testes:
  comandos:
    - "cd functions && ../venv/bin/python3 -m unittest discover -p 'test_*.py' -q"
  resultados:
    - "Antes desta sub-entrega (main pós-merge da PR #207/DEV-2026-0003 relatório de custos, commit 81088ba44): 1420 testes, 8 falhas + 2 erros -- confirmados PRÉ-EXISTENTES (ambiente sem ANTHROPIC_API_KEY/deps opcionais para gmail/mp4; test_deteccao_subproduto.py, test_gmail_bill_pdf, test_mp4_repair), não relacionados a esta sub-entrega."
    - "Depois desta sub-entrega: 1442 testes (22 novos: 14 em test_mandatos_io.py, 8 em test_outbox_aprovacao.py), mesmas 8 falhas + 2 erros pré-existentes, zero regressão nova."
evidencias:
  - "Revisão adversarial independente (Agent tool, general-purpose, sem contexto da implementação) sobre o diff completo (mandatos_io.py, outbox_aprovacao.py, test_mandatos_io.py, e os arquivos de teste existentes referenciados). Traçou os casos 'ainda promovido'/'não mais promovido' à mão por avaliar()/mandato_cobre(), confirmou a fiação de missao/finalidade/sensibilidade/classe_efeito/destinos correta e bem testada. Dois achados reais: 1 bloqueante ('outro' derruba o lote inteiro), 1 should-fix (degrade não-transacional resssuscita descarte concorrente) -- ver as duas decisões acima para os detalhes completos. Rodou a suíte de verdade (não só leu código), e escreveu/rodou scripts standalone para reproduzir os dois achados ao vivo antes de reportar."
  - "Segunda rodada de revisão adversarial (mesmo tipo de agente, instância nova, sem contexto da primeira revisão nem da implementação original -- só recebeu a descrição dos dois achados e o diff já corrigido) verificou os dois fixes de forma independente: confirmou por grep que mandatos_io.py é o único ponto de produção que constrói Mandato(...), raciocinou pelo código antigo (sem acesso a ele, só à descrição) que os testes novos de fato falhariam sob o comportamento pré-fix, e rodou a suíte completa de novo. Veredito: 'fixes verified'."
  - "Suíte completa rodada antes (via git stash temporário para isolar a contagem exata da base, depois git stash pop para restaurar) e depois; ver testes.resultados acima."
  - "Todos os arquivos desta sub-entrega (mandatos_io.py, outbox_aprovacao.py, test_mandatos_io.py, test_outbox_aprovacao.py, test_promocao_autonomia.py, e este próprio bloco de execucao.md) enviados via mcp__Argos__argos_escrever_arquivo_repositorio com verificação de hash local (git hash-object) contra o sha retornado pelo Argos em cada arquivo, antes de abrir a PR."
migracao:
  dry_run: null
  executada: false
flags:
  antes: {}
  depois: {}
pendencias:
  - "RESOLVIDO por esta entrada: wrapper de I/O de Mandato, pendência central desde a sub-entrega 1/N, reafirmada como a peça faltante na sub-entrega 15/N (decisão p02-sub15-preflight-estado-autonomia-em-vez-de-decisao-piso-completo)."
  - "RESOLVIDO PARCIALMENTE: liberar_rascunhos_promovidos (outbox_aprovacao.py) agora usa avaliar()/mandato_cobre() de verdade por rascunho -- revisao_semanal.py::propor_reagendamento_semanal continua só no interruptor global de EstadoAutonomia (não envia nada a terceiros por si só, é sempre uma proposta que aguarda toque humano antes de qualquer efeito real -- risco estrutural menor que o de liberar_rascunhos_promovidos, deliberadamente fora do escopo desta sub-entrega; religar também é trabalho direto se/quando fizer sentido)."
  - "Mandato.usos_na_janela_atual e orcamento_maximo continuam sem wrapper de I/O real -- mandato_tipo_promovido não os popula (decisão consciente, documentada na proposta: tipos promovidos não têm hoje nenhuma fonte de dados real para contagem-por-janela nem orçamento; popular esses campos exigiria decidir de onde viria esse dado, uma pergunta de produto nova, não resolvida aqui)."
  - "forma_revogacao do Mandato é hoje só descritiva ('remover de system/mcp_access.tipos_promovidos') -- não existe tool dedicada para revogar um tipo já promovido, só edição direta do documento Firestore. Se isso virar uso frequente (André revogando tipos com regularidade), vale criar uma tool revogar_promocao_autonomia análoga a decidir_promocao_autonomia."
  - "Achado nitpick da revisão adversarial, não corrigido (não-bloqueante, considerado aceitável): o card do Telegram de um rascunho degradado continua mostrando o texto/botão de 'envio automático, toque para cancelar' já enviado antes do degrade -- não é reeditado para refletir que agora precisa de aprovação manual de verdade. O rascunho continua descobrível via listar_rascunhos_pendentes/contar_pendentes e eventualmente expira em 48h via expirar_rascunhos_pendentes (não é um buraco negro silencioso), mas não há notificação nova ao André nesse momento. Se degrades por revogação de tipo se tornarem frequentes na prática, vale reenviar um card novo (padrão montar_card_telegram) nesse ponto."
  - "Todas as pendências já registradas em blocos anteriores que não foram tocadas por esta sub-entrega continuam abertas: risco de bare-name-resolution nos módulos de área, dependência de CLASSE_EFEITO_PISO/FLOOR_CONFIRMACAO_OBRIGATORIA continuarem com as mesmas chaves (travado por teste, não garantia estrutural -- a PR #206, ainda aberta no momento desta sub-entrega, torna isso estrutural; ver docs/autonomia/execucao.md quando/se mergeada)."
proximo_pacote: "P02 -- com o wrapper de Mandato e liberar_rascunhos_promovidos religados, a extensão natural é religar revisao_semanal.py::propor_reagendamento_semanal ao mesmo padrão (hoje só o interruptor global) e considerar se/quando criar a tool de revogação explícita de tipo promovido. Nenhuma das duas é urgente -- proponho aguardar sinal do André sobre o que priorizar a seguir, em vez de escolher sozinha mais uma vez em sequência."
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
    motivo: "Achado de infraestrutura, não de produto: functions/main.py (683664 bytes) está acima do limite de 200000 bytes que argos_ler_arquivo_repositorio e argos_escrever_arquivo_repositorio aplicam -- confirmado ao vivo pela recusa 413 do próprio Argos na tentativa de leitura. Isso bloqueia QUALQUER edição futura a main.py pelo caminho normal desta sessão (Argos MCP), não só esta. Não tentei contornar via push local (fora da diretriz padrão desta sessão, sem credencial configurada) nem tentei dividir main.py sozinha (refactor real, fora de escopo, decisão de arquitetura que não me cabe tomar sozinho). Levado ao André via pergunta direta com 4 opções; ele escolheu aplicar o diff manualmente desta vez. Fica como pendência de infraestrutura para o André decidir se/quando quiser resolver de raiz (dividir main.py em módulos menores, ou uma ferramenta Argos com suporte a patch/diff para arquivos grandes)."
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
