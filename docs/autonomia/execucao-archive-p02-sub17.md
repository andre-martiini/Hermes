# Registro de execução (arquivo) — plano-hermes-autonomo-2026-09-06 — P02 sub-entrega 17/N

Arquivo do bloco P02 sub-entrega 17/N, movido para cá em 2026-09-09 (durante
a sub-entrega P01 6/N, mcp_jobs.py). Motivo: o arquivo ativo
(docs/autonomia/execucao.md, então com 49259 bytes) somado ao novo bloco
desta sub-entrega (12609 bytes) chegaria a 61868 bytes -- acima do limiar de
~50KB que a própria sub-entrega P01 5/N registrou como arriscado para uma
escrita confiável via Argos MCP (ver a decisão
p01-sub5-corrupcao-silenciosa-na-retranscricao-e-arquivamento-preventivo nos
blocos de P01 sub-entrega 5/N, ainda no arquivo ativo). Em vez de esperar o
problema se repetir, o bloco mais antigo do arquivo ativo (P02 sub-entrega
17/N) foi movido preventivamente para este arquivo NOVO e separado -- mesmo
raciocínio já registrado no cabeçalho de
execucao-archive-p02-sub12-a-sub16.md: cada escrita via Argos precisa
reenviar o arquivo inteiro (sem diff/patch), então um arquivo de arquivo que
só cresce eventualmente fica grande demais para qualquer escrita futura o
tocar, mesmo só para adicionar uma nota -- por isso um arquivo de arquivo
novo, não mais conteúdo anexado a um dos dois já existentes
(execucao-archive-p00-a-p02sub11.md ou execucao-archive-p02-sub12-a-sub16.md,
nenhum dos dois tocado nesta operação). Nenhum conteúdo foi perdido -- o
bloco abaixo é cópia byte-a-byte do arquivo ativo de antes deste terceiro
corte, extraída por script (não retranscrita à mão), com hash conferido
antes e depois do envio. O arquivo ativo (docs/autonomia/execucao.md)
continua sendo a fonte de verdade a partir da sub-entrega P01 3/N em diante.

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

