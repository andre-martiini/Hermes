"""Inventário tipado de ferramentas MCP — P03 passo 1 do plano de autonomia
(docs/plano-hermes-autonomo-2026-09-06.md, "P03 — Consolidar contratos MCP e
ferramentas"): "criar inventário tipado por ferramenta: domínios,
leitura/escrita, reversibilidade, necessidade de rede, dados sensíveis,
política e verificador".

Este módulo não decide nada e não é consultado por nenhum executor ainda —
é só o inventário em si (o "o que cada ferramenta é", não "o que fazer a
respeito"). Ligar isso à decisão de política real (ex.: `classe_efeito` como
entrada de `autonomy/policy.py::avaliar()` por ferramenta, em vez de o
chamador montar `PolicyRequest.classe_efeito` à mão) é trabalho de uma
sub-entrega futura deste mesmo pacote — ver docs/autonomia/execucao.md.

## Metodologia

Cada uma das 105 tools de `tools/registry.py::_CATALOG` foi classificada pela
LEITURA DIRETA da implementação real (não pelo nome nem pela descrição do
catálogo, que divergem do código em vários casos documentados abaixo) —
`tools/hermes_tools.py` e, quando o handler delega, o módulo especializado
correspondente (`promocao_autonomia.py`, `outbox_aprovacao.py`,
`secretario_whatsapp.py`, `investimentos.py`, `atencao.py`,
`autonomy/policy.py`, etc.). O plano fala em "103" ferramentas na seção de
testes do P03; a contagem real do catálogo hoje é 105 — divergência da
redação do plano, não um erro deste inventário.

`classe_efeito` usa o enum já existente `autonomy.contracts.ClasseEfeito`
(seção 5.1 do plano) em vez de uma taxonomia nova — mesma decisão de
reaproveitar vocabulário já tomada pela proposta de
`docs/autonomia/proposta-p02-mandato-io-wrapper.md`. Duas tools
(`registrar_aporte_investimento`, `registrar_execucao_investimento`,
`schedule_whatsapp_message`, `pausar_conversa`, `criar_rascunho_email`) já
tinham classificação canônica em `autonomy/policy.py::CLASSE_EFEITO_PISO` —
usada aqui como âncora, não reinferida.

`autonomy/verifiers.py` (P04 do plano) ainda não existe — o campo
`verificador` descreve o que HOJE, na prática, confere (ou não) o efeito de
cada tool; "nenhum" é uma resposta honesta e frequente, não uma lacuna deste
inventário.

## Achados relevantes (não corrigidos aqui — registro para P03/P04)

- **`_NEEDS_CONFIRMATION` (tools/registry.py) não equivale a "escreve"**: é o
  metadado `mutates` do protocolo MCP, propositalmente conservador. Tools que
  não persistem nada por si mesmas (ex. `preparar_vinculo_contatos`,
  `preparar_atualizacao_contato`) aparecem lá porque o FLUXO que iniciam leva
  a uma mutação depois — não porque a própria chamada grava algo. Por isso
  este inventário não assume paridade entre os dois conjuntos.
- Tools cujo NOME sugere "preparar" (sem persistir) mas que na verdade
  gravam direto: `preparar_upload` (grava `uploads_pendentes`) e
  `preparar_contato_prioritario_secretario` (grava direto em
  `system_secretario_prioritarios`, sem segunda chamada de confirmação).
- `gerar_rascunho_formulario` não persiste nada, ao contrário do que a
  descrição do catálogo ("...e salva no sistema") sugere.
- `consultar_contatos_prioritarios_secretario` e `consultar_autorizacao_argos`
  têm efeito colateral de escrita (expiração passiva) dentro de uma leitura.
- `excluir_objetivo_estrategico` faz `delete()` definitivo mas não está no
  piso `FLOOR_CONFIRMACAO_OBRIGATORIA` do MCP — única tool de exclusão
  institucional sem exigência estrutural de dupla confirmação no canal MCP.
- `mutar_portal_compras_publico` e `mutar_lista_compras` escrevem na mesma
  coleção (`shopping_items`) por dois caminhos de código independentes —
  candidato a consolidação.
- `decidir_promocao_autonomia("aceitar")` tem efeito de política real
  (remove a exigência de aprovação humana prévia para uma categoria inteira
  de mensagens WhatsApp autônomas), maior que "escrita interna" sugeriria.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from autonomy.contracts import ClasseEfeito


class LeituraEscrita(str, Enum):
    LEITURA = "leitura"
    ESCRITA = "escrita"
    LEITURA_E_ESCRITA = "leitura_e_escrita"


class Reversibilidade(str, Enum):
    REVERSIVEL = "reversivel"
    IRREVERSIVEL = "irreversivel"
    NAO_APLICA = "nao_aplica"


class DominioRede(str, Enum):
    """Classificação complementar a `necessidade_de_rede`, só para as tools
    com `necessidade_de_rede=True` -- P03 sub-entrega 7/N, para sustentar
    `openWorldHint` do protocolo MCP (ver `tools/registry.py::mcp_annotations`).
    `necessidade_de_rede` sozinho NÃO diferencia "fala com um sistema externo
    fechado e conhecido" (a agenda do próprio dono) de "fala com um sistema
    externo imprevisível" (a web aberta) -- por isso um campo novo, não uma
    derivação automática do texto livre de `rede_servico`."""

    FECHADO = "fechado"  # domínio conhecido e limitado -- conta/serviço do próprio dono, ou chamada de IA interna
    ABERTO = "aberto"  # conteúdo externo arbitrário/imprevisível -- busca na web, URL arbitrária


class Idempotencia(str, Enum):
    """Se repetir a chamada com os MESMOS argumentos tem efeito adicional no
    ambiente -- P03 sub-entrega 16/N, para sustentar `idempotentHint` do
    protocolo MCP (ver `tools/registry.py::mcp_annotations`). Investigado por
    HANDLER (não inferido de outro campo do inventário): `reversibilidade` é
    sobre "dá para desfazer depois", `idempotencia` é sobre "repetir agora
    muda algo além da primeira vez" -- as duas perguntas têm respostas
    independentes (ex.: `concluir_pedido_agente` é IRREVERSIVEL e
    IDEMPOTENTE ao mesmo tempo: a transição é definitiva, mas chamar de novo
    com o mesmo `request_id` não sobrescreve nada, só devolve
    `already_decided`).

    Só atribuído a tools com `leitura_escrita != LEITURA` -- a especificação
    MCP só considera o hint significativo quando `readOnlyHint` é `false`
    (mesma convenção já usada para `destructiveHint`, ver
    `registry.mcp_annotations`): leitura pura não tem efeito nenhum a
    repetir, então o hint seria vazio de conteúdo ali."""

    IDEMPOTENTE = "idempotente"
    NAO_IDEMPOTENTE = "nao_idempotente"


@dataclass(frozen=True)
class ToolInventoryEntry:
    """Uma linha do inventário — ver docstring do módulo para os 7 campos
    pedidos pelo passo 1 do P03. `rede_servico`/`dados_sensiveis_categoria`
    são o "qual" complementar dos dois campos booleanos. `dominio_rede` é o
    "qual" complementar de `necessidade_de_rede`, ver `DominioRede`.
    `idempotencia` (P03 sub-entrega 16/N) é independente dos outros seis --
    ver `Idempotencia`."""

    dominio: str
    leitura_escrita: LeituraEscrita
    reversibilidade: Reversibilidade
    necessidade_de_rede: bool
    dados_sensiveis: bool
    classe_efeito: ClasseEfeito
    verificador: str
    rede_servico: str | None = None
    dados_sensiveis_categoria: str | None = None
    nota: str | None = None
    dominio_rede: DominioRede | None = None
    idempotencia: Idempotencia | None = None


_L = LeituraEscrita
_R = Reversibilidade
_C = ClasseEfeito
_I = Idempotencia

_INVENTORY: dict[str, ToolInventoryEntry] = {
    "consultar_historico_acoes": ToolInventoryEntry(
        "acoes_tarefas", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA,
        "nenhum — chamador pode reconsultar com outro filtro se insuficiente",
    ),
    "buscar_arquivos_acervo": ToolInventoryEntry(
        "acervo_documentos", _L.LEITURA, _R.NAO_APLICA, True, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum — score de similaridade não é conferido contra relevância real",
        rede_servico="Gemini (embedding da query)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="documentos do Acervo Global, potencialmente pessoais/institucionais",
    ),
    "buscar_conversas_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.LEITURA, _R.NAO_APLICA, True, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum",
        rede_servico="Gemini (embedding) + busca vetorial Firestore",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="conteúdo de conversas privadas de terceiros",
    ),
    "pesquisar_internet": ToolInventoryEntry(
        "utilitario", _L.LEITURA, _R.NAO_APLICA, True, False, _C.OBSERVACAO_AUTORIZADA,
        "nenhum — resposta da API de busca não é checada", rede_servico="API Tavily",
        dominio_rede=DominioRede.ABERTO,
    ),
    "ler_pagina_web": ToolInventoryEntry(
        "utilitario", _L.LEITURA, _R.NAO_APLICA, True, False, _C.OBSERVACAO_AUTORIZADA,
        "nenhum", rede_servico="proxy r.jina.ai",
        dominio_rede=DominioRede.ABERTO,
    ),
    "consultar_agenda": ToolInventoryEntry(
        "agenda", _L.LEITURA, _R.NAO_APLICA, True, False, _C.OBSERVACAO_AUTORIZADA,
        "nenhum", rede_servico="Google Calendar",
        dominio_rede=DominioRede.FECHADO,
    ),
    "encontrar_slot_livre": ToolInventoryEntry(
        "agenda", _L.LEITURA, _R.NAO_APLICA, True, False, _C.OBSERVACAO_AUTORIZADA,
        "nenhum", rede_servico="Google Calendar",
        dominio_rede=DominioRede.FECHADO,
    ),
    "criar_acao_no_sistema": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, True, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum dedicado — dedup evita duplicata; reconsulta via obter_acao",
        rede_servico="Google Calendar (checagem de conflito) + Gemini condicional (embedding se houver texto-fonte)",
        dominio_rede=DominioRede.FECHADO,
        idempotencia=_I.IDEMPOTENTE,
        nota="idempotente via `claim_action_dedup_slot` (main.py): chave (titulo, data_limite, "
        "horario_inicio) reivindicada atomicamente, repetir com a mesma chave devolve "
        "'OK|{task_id}' da acao ja criada em vez de duplicar -- mas só dentro da janela de "
        "ttl_minutes=15 do slot; repetir a mesma chamada depois desse intervalo cria uma acao "
        "nova (P03 sub-entrega 16/N)",
    ),
    "agendar_lembrete_acao": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — não confirma que o lembrete foi de fato entregue no horário",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="handler real (tools/telegram_extended.py::execute, ramo 'agendar_lembrete_acao') monta "
        "um `new_reminder` com `uuid.uuid4()` novo e faz `append` na lista `reminders` em TODA "
        "chamada, sem checar se já existe um lembrete igual -- repetir com os mesmos argumentos "
        "cria um segundo lembrete duplicado, não devolve o mesmo (P03 sub-entrega 16/N)",
    ),
    "salvar_memoria_global": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.ESCRITA, _R.REVERSIVEL, True, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum determinístico — o próprio filtro de retenção é um LLM",
        rede_servico="Gemini (classificador de retenção + embedding)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="fato pessoal do usuário ou de terceiro, sem filtro de categoria",
        idempotencia=_I.IDEMPOTENTE,
        nota="reversível via resolver_conflito_memoria — mas só na prática quando uma gravação futura for "
        "detectada como similar o bastante para abrir um conflito; não há tool neste catálogo para buscar "
        "e corrigir uma memória específica sob demanda (achado da revisão adversarial desta sub-entrega). "
        "Idempotente por similaridade, não por chave exata (P03 sub-entrega 16/N): "
        "`_save_memory_node` (main.py) busca os 3 nós mais similares por embedding e, acima de "
        "MEMORY_SIMILARITY_DUPLICATE_THRESHOLD=0.965, devolve status='ignored'/reason='duplicate' em "
        "vez de criar um nó novo -- repetir o MESMO `fato` NÃO produz o mesmo embedding, ao contrário "
        "do que uma leitura apressada sugeriria (3ª rodada de revisão adversarial desta sub-entrega, "
        "achado real): `_save_memory_node` embeda o fato para GRAVAR com "
        "task_type='RETRIEVAL_DOCUMENT', mas `_find_similar_memory_nodes` (chamada na repetição) embeda "
        "o MESMO texto para BUSCAR com task_type='RETRIEVAL_QUERY' -- os dois vetores são diferentes "
        "por design (par assimétrico de embeddings de recuperação). A proteção real contra duplicata "
        "tem duas camadas: a similaridade cruzada (query vs. document) do MESMO texto tende a ficar "
        "bem alta em modelos de recuperação bem treinados, o suficiente para passar do piso "
        "MEMORY_SIMILARITY_CREATE_THRESHOLD=0.90 (não demonstrado numericamente aqui, apenas plausível "
        "pelo desenho do par assimétrico) -- e SÓ DEPOIS disso o fallback de texto exato "
        "(`best_text == fato_norm`) garante o 'duplicate' mesmo se a similaridade cruzada ficar abaixo "
        "de 0.965. Se a similaridade cruzada do MESMO texto cair abaixo de 0.90, o candidato nem entra "
        "na comparação e um nó novo é criado -- risco residual não-bloqueante, sem teste de handler "
        "para descartá-lo (ver GAP CONHECIDO abaixo). O classificador de retenção (LLM, chamado antes "
        "da busca de similaridade) pode variar entre chamadas, mas em NENHUM dos dois "
        "resultados possíveis (should_save=False -> ignored/retention_filter; should_save=True -> "
        "busca de similaridade protege contra duplicata, sujeita ao risco acima) o handler persiste "
        "duas vezes por si só -- risco residual adicional, não-bloqueante, só para duas chamadas quase "
        "simultâneas, antes do primeiro nó ficar indexado para busca vetorial (condição de corrida não "
        "observada, não demonstrada). Repetir "
        "não é um no-op puro: no ramo 'duplicate', `_save_memory_node` ainda faz `ref.set(..., "
        "merge=True)` no nó existente, atualizando `data_atualizacao`/`ultima_sessao_id`/"
        "`ultimo_usuario_id`/`ultimo_fato_observado` a cada chamada -- mesmo padrão de metadado "
        "auxiliar sempre atualizado já aceito em `dispensar_resposta_pendente` (`dispensado_em`), não "
        "cria um segundo nó nem duplica o fato em si. GAP CONHECIDO (2ª rodada de revisão adversarial "
        "desta sub-entrega): ao contrário de `criar_acao_no_sistema` (test_action_dedup_slot.py) e "
        "`dispensar_resposta_pendente` (test_inbox_pendentes.py), esta classificação não tem teste de "
        "HANDLER dedicado -- exigiria mockar embedding (Gemini) e o classificador de retenção (LLM), "
        "sem nenhum precedente de mock nesse formato na suíte hoje; apoiada só em leitura de código, "
        "registrado aqui em vez de omitido",
    ),
    "registrar_correcao_procedimento": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum na própria tool",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="reversível via resolver_conflito_procedimento. Não idempotente (P03 sub-entrega 19/N): "
        "`tools/hermes_tools.py::registrar_correcao_procedimento` gera `_corr_id = uuid4()[:12]` e faz "
        "`.set()` incondicional em `correcoes_pendentes/{_corr_id}` a cada chamada, sem nenhuma checagem de "
        "dedup por título/área -- repetir a MESMA correção cria um SEGUNDO documento pendente distinto, que "
        "o Motor de Evolução processaria duas vezes.",
    ),
    "buscar_e_analisar_email": ToolInventoryEntry(
        "email", _L.LEITURA, _R.NAO_APLICA, True, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum", rede_servico="Gmail API",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="conteúdo de e-mails e anexos",
    ),
    "obter_contexto_tela": ToolInventoryEntry(
        "acoes_tarefas", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum",
    ),
    "ler_documento_na_integra": ToolInventoryEntry(
        "acervo_documentos", _L.LEITURA, _R.NAO_APLICA, True, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum — resposta do Gemini não é conferida contra o documento original",
        rede_servico="Google Drive (download) + Gemini",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="documento arbitrário do Drive do usuário",
    ),
    "salvar_pop_global": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum",
        idempotencia=_I.IDEMPOTENTE,
        nota="handler real é `tools/telegram_extended.py::execute`, ramo 'salvar_pop_global' -- a closure "
        "homônima em main.py é uma implementação independente para o copiloto web, não usada pelo servidor "
        "MCP (comentário explícito no próprio código: 'esta função é independente da salvar_pop_global "
        "embutida em main.py'). Idempotente (P03 sub-entrega 19/N): antes de escrever, varre "
        "`pops_diretrizes` por título OU gatilho normalizado já existente -- se achar, faz `.set(merge=True)` "
        "no MESMO doc (só `updated_at` muda); só cria doc novo quando NENHUM POP existente casa por título "
        "ou gatilho. Repetir a MESMA chamada acha o POP recém-criado por título e converge. Caveat: a "
        "varredura é consulta-depois-escreve sem exclusão mútua atômica (mesmo espírito do caveat já aceito "
        "em `registrar_saude`/`consultar_investimentos`, sub-entrega 17/N) -- duas chamadas genuinamente "
        "concorrentes poderiam ambas não achar nada e criar dois POPs.",
    ),
    "resolver_conflito_memoria": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.ESCRITA, _R.REVERSIVEL, True, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum", rede_servico="Gemini (embedding), só quando decisão=substituir_pelo_novo",
        dominio_rede=DominioRede.FECHADO,
        idempotencia=_I.IDEMPOTENTE,
        nota="handler real é `tools/telegram_extended.py::execute`, ramo 'resolver_conflito_memoria' (mesma "
        "ressalva de fonte única de salvar_pop_global/atualizar_personalidade). Idempotente (P03 sub-entrega "
        "19/N): os dois ramos de decisão escrevem por ID JÁ CONHECIDO (`memoria_id`), nunca geram ID novo -- "
        "`manter_existente` faz `.set(merge=True)` direto no doc; `substituir_pelo_novo` delega a "
        "`main.py::_save_memory_node` com `force_update_id=memoria_id`, mesmo padrão de convergência-por-ID "
        "já aceito em `editar_objetivo_estrategico` (sub-entrega 18/N) -- diferente de `salvar_memoria_global` "
        "(sem ID conhecido de antemão, dedup por similaridade de embedding), aqui não há ambiguidade de "
        "embedding assimétrico porque o ID já veio resolvido pelo próprio card do conflito.",
    ),
    "atualizar_personalidade": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — grava direto sem revisão",
        idempotencia=_I.IDEMPOTENTE,
        nota="handler real é `tools/telegram_extended.py::execute`, ramo 'atualizar_personalidade' (mesma "
        "ressalva de fonte única já registrada em `salvar_pop_global`: a closure em main.py é a versão "
        "independente do copiloto web). Idempotente (P03 sub-entrega 19/N): grava sempre no MESMO documento "
        "singleton `system/copilot_soul` via `.set(merge=True)` -- repetir a MESMA chamada produz o mesmo "
        "`content`/`last_reason` persistidos, só `updated_at` muda.",
    ),
    "resolver_conflito_procedimento": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.LEITURA_E_ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "a exigência de confirmar_contrato=True na chamada é o único verificador pré-escrita",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="sem confirmar_contrato é só preview textual (leitura); versão antiga vira backup, não é apagada. "
        "Não idempotente (P03 sub-entrega 19/N): com `confirmar_contrato=True`, `tools/telegram_extended.py::"
        "execute` arquiva o procedimento atual (`status: arquivado_backup`) e cria um documento NOVO com "
        "`uuid4()[:12]` em `conhecimento_mestre` -- repetir a MESMA chamada (mesmo já arquivado) cria um "
        "SEGUNDO procedimento 'evoluído' distinto a cada vez, sem dedup. O ramo `confirmar_contrato=False` "
        "isolado, se chamado repetidamente, seria idempotente (só leitura) -- mas a tool inteira, como "
        "definida pelo contrato de dois passos, não é: o efeito real (a escrita) está no segundo passo, que "
        "não converge.",
    ),
    "editar_plano_acao": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "salvaguardas pré-escrita (plano degenerado, plano esvaziado) bloqueiam gravações claramente erradas",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="handler real é `tools/telegram_extended.py::execute`, ramo 'editar_plano_acao'. "
        "`subtarefas.mesclar_plano` em si converge (mesclar o mesmo `novo_plano` produz o mesmo "
        "`plano_final`), mas o handler faz `task_ref.update` com `firestore.ArrayUnion([{data, nota}])` em "
        "`acompanhamento`, INCONDICIONALMENTE, em toda chamada bem-sucedida -- mesmo padrão de append "
        "incondicional já aceito em `editar_acao` (sub-entrega 16/N) e `pausar_conversa`/`registrar_execucao_"
        "investimento` (sub-entrega 17/N). Não idempotente (P03 sub-entrega 19/N).",
    ),
    "preparar_edicao_acao": ToolInventoryEntry(
        "acoes_tarefas", _L.LEITURA, _R.NAO_APLICA, False, False, _C.PREPARACAO_INTERNA,
        "não aplicável — aplicação real é confirmar_edicao_acao",
    ),
    "preparar_edicao_em_lote": ToolInventoryEntry(
        "acoes_tarefas", _L.LEITURA, _R.NAO_APLICA, False, False, _C.PREPARACAO_INTERNA,
        "não aplicável — aplicação real é confirmar_edicao_em_lote",
    ),
    "gerar_relatorio": ToolInventoryEntry(
        "utilitario", _L.ESCRITA, _R.REVERSIVEL, True, False, _C.PREPARACAO_INTERNA,
        "nenhum — texto do LLM é gravado sem conferência de qualidade",
        rede_servico="Gemini (múltiplas chamadas: esqueleto + cada seção)",
        dominio_rede=DominioRede.FECHADO,
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="classificação PREPARACAO_INTERNA discutível: ao contrário de preparar_edicao_acao (que é "
        "LEITURA/NAO_APLICA, sem persistir nada até confirmar_edicao_acao), esta tool já persiste um "
        "documento final em relatorios/{id} sem passo de confirmação — mais perto de ESCRITA_INTERNA_"
        "REVERSIVEL. Mantido PREPARACAO_INTERNA por ser conteúdo interno de baixo risco sem contato com "
        "terceiro, mas é ambiguidade genuína a revisitar quando classe_efeito for religada à decisão de "
        "política de fato (achado da revisão adversarial desta sub-entrega). Não idempotente (P03 "
        "sub-entrega 19/N): handler real é `tools/telegram_extended.py::execute`, ramo 'gerar_relatorio' -- "
        "gera `report_id = uuid4()[:16]` e faz `.set()` incondicional em `relatorios/{report_id}`, sem dedup "
        "por título/contexto; repetir o MESMO pedido cria um SEGUNDO relatório com ID novo (e conteúdo "
        "potencialmente diferente, já que a síntese do LLM não é determinística).",
    ),
    "gerar_rascunho_formulario": ToolInventoryEntry(
        "utilitario", _L.LEITURA, _R.NAO_APLICA, False, False, _C.PREPARACAO_INTERNA, "nenhum",
        nota="não persiste nada, ao contrário do que a descrição do catálogo sugere",
    ),
    "obter_portal_financeiro_publico": ToolInventoryEntry(
        "financas_publicas_portal", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum", dados_sensiveis_categoria="financeiro",
    ),
    "registrar_transacao_financeira_publica": ToolInventoryEntry(
        "financas_publicas_portal", _L.ESCRITA, _R.IRREVERSIVEL, False, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — grava sem checar duplicidade/fonte", dados_sensiveis_categoria="financeiro",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="sem tool de exclusão/correção neste catálogo; a leitura já trata status==deleted, indício de que esse "
        "caminho existe fora do MCP. Não idempotente (P03 sub-entrega 17/N): o handler real "
        "(tools/telegram_extended.py::execute, ramo 'registrar_transacao_financeira_publica') cria "
        "`db.collection('finance_transactions').document()` com ID automático e faz `.set()` incondicional em "
        "toda chamada, sem checar description/amount repetidos -- repetir com os mesmos argumentos cria uma "
        "segunda transação, não devolve a mesma.",
    ),
    "obter_portal_compras_publico": ToolInventoryEntry(
        "compras", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum",
    ),
    "mutar_portal_compras_publico": ToolInventoryEntry(
        "compras", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL, "nenhum",
        nota="duplica lógica de escrita com mutar_lista_compras sobre a mesma coleção shopping_items — "
        "candidato a consolidação. Idempotência investigada e deixada SEM classificação (P03 sub-entrega "
        "19/N): despacha por `acao` interno -- `toggle_planned`/`toggle_purchased` fazem "
        "`ref.update({\"isPlanned\": not bool(...)})`, um TOGGLE de verdade (cada chamada tem efeito "
        "DIFERENTE da anterior, viola idempotência por definição), enquanto `update_quantity`/"
        "`clear_planning`/`finalize` convergem -- mesmo problema de múltiplos ramos com comportamentos "
        "opostos já aceito para `gerenciar_item_estrategico` (sub-entrega 18/N): um hint único mentiria "
        "para pelo menos um ramo.",
    ),
    "mutar_lista_compras": ToolInventoryEntry(
        "compras", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "consultar_lista_compras foi desenhada para reconferir o efeito ('fecha o ciclo', docstring do módulo)",
        nota="idempotência investigada e deixada SEM classificação (P03 sub-entrega 19/N): despacha por "
        "`acao` interno (`criar` gera ID novo sempre -- NAO_IDEMPOTENTE; `atualizar` sobrescreve por ID -- "
        "provável IDEMPOTENTE; `remover` provavelmente erra 'já removido' na repetição, mesma ambiguidade "
        "de `revogar_promocao_autonomia`; `import_batch`/`limpar_planejamento` não investigados a fundo "
        "nesta sub-entrega) -- mesmo problema de múltiplos ramos já aceito para `mutar_portal_compras_"
        "publico` acima e `gerenciar_item_estrategico` (sub-entrega 18/N).",
    ),
    "consultar_lista_compras": ToolInventoryEntry(
        "compras", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA,
        "ela própria é o verificador de mutar_lista_compras",
    ),
    "consultar_elevacoes_sugeridas": ToolInventoryEntry(
        "estrategico", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum",
    ),
    "decidir_elevacao": ToolInventoryEntry(
        "estrategico", _L.ESCRITA, _R.IRREVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — mudança de status não é reconferida",
        nota="irreversível só para a decisão 'nunca' (permanente por desenho); 'aceitar'/'adiar' são "
        "revisáveis. Idempotência investigada e deixada SEM classificação (P03 sub-entrega 19/N): "
        "`deteccao_subproduto.py::decidir` já é transação Firestore falha-fechada -- a segunda chamada não "
        "escreve de novo -- mas devolve só `{\"ok\": False, \"erro\": \"texto livre\"}`, sem um status "
        "estruturado tipo 'já decidido' que distinga isso de um erro genuíno; mesma ambiguidade "
        "resposta-muda-mas-ambiente-não já aceita para `revogar_promocao_autonomia` (sub-entrega 16/N).",
    ),
    "consultar_promocoes_autonomia_sugeridas": ToolInventoryEntry(
        "autonomia_politica", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum",
    ),
    "decidir_promocao_autonomia": ToolInventoryEntry(
        "autonomia_politica", _L.ESCRITA, _R.IRREVERSIVEL, False, False, _C.COORDENACAO_LIMITADA,
        "nenhum — a promoção passa a valer imediatamente; revogar_promocao_autonomia é o único caminho de volta",
        nota="irreversível só para 'nunca'; 'aceitar' é revisável via revogar_promocao_autonomia. "
        "Efeito real de 'aceitar': remove a exigência de aprovação humana prévia no Telegram para uma "
        "categoria inteira de mensagens WhatsApp autônomas dali em diante — risco maior do que 'escrita "
        "interna' sugeriria, por isso COORDENACAO_LIMITADA e não ESCRITA_INTERNA_REVERSIVEL. Idempotência "
        "investigada e deixada SEM classificação (P03 sub-entrega 19/N): `promocao_autonomia.py::decidir_"
        "promocao_autonomia` também falha-fechado na repetição (ambiente não muda), mas devolve só "
        "`{\"ok\": False, \"erro\": \"texto livre\"}` sem status estruturado -- mesma ambiguidade de "
        "`decidir_elevacao` acima.",
    ),
    "revogar_promocao_autonomia": ToolInventoryEntry(
        "autonomia_politica", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum", nota="oposto de baixo risco de decidir_promocao_autonomia — reduzir autonomia é sempre seguro",
    ),
    "obter_projeto_bolsas_publico": ToolInventoryEntry(
        "bolsas_portal", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum",
    ),
    "registrar_inscricao_bolsa_publica": ToolInventoryEntry(
        "bolsas_portal", _L.ESCRITA, _R.IRREVERSIVEL, False, True, _C.COMPROMISSO_TERCEIROS,
        "nenhum — resultado nunca é reconferido",
        dados_sensiveis_categoria="CPF, RG, e-mail, telefone de terceiro",
    ),
    "consultar_financas_v2": ToolInventoryEntry(
        "financas_pessoais", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "implícito — chamador pode reconsultar", dados_sensiveis_categoria="financeiro pessoal",
    ),
    "registrar_item_financeiro_v2": ToolInventoryEntry(
        "financas_pessoais", _L.ESCRITA, _R.IRREVERSIVEL, False, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — ao contrário de registrar_saude, não é idempotente por dia",
        dados_sensiveis_categoria="financeiro pessoal",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="sempre cria doc novo; nenhuma tool deste catálogo edita/exclui um lançamento. Não idempotente "
        "(P03 sub-entrega 17/N): as 3 ramificações de `tipo` (renda/obrigacao_fixa/transacao_avulsa) em "
        "tools/telegram_extended.py::execute usam `db.collection(...).document()` com ID automático + `.set()` "
        "incondicional, mesmo padrão nas três -- repetir cria um lançamento novo em vez de devolver o existente.",
    ),
    "calculadora": ToolInventoryEntry(
        "utilitario", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA,
        "nenhum necessário — determinístico, recomputável pelo chamador",
    ),
    "schedule_whatsapp_message": ToolInventoryEntry(
        "whatsapp", _L.ESCRITA, _R.IRREVERSIVEL, False, True, _C.COMPROMISSO_TERCEIROS,
        "nenhum aqui — consultar_envio_whatsapp seria o verificador real da entrega",
        dados_sensiveis_categoria="destinatário e conteúdo de terceiro",
        nota="classificação COMPROMISSO_TERCEIROS já existe em autonomy/policy.py::CLASSE_EFEITO_PISO; "
        "só enfileira em whatsapp_outbox — quem entrega é um worker separado, não esta chamada",
    ),
    "criar_rascunho_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.ESCRITA, _R.IRREVERSIVEL, True, True, _C.COMPROMISSO_TERCEIROS,
        "o card do Telegram é o verificador humano; para tipos promovidos, só a janela de cancelamento",
        rede_servico="Telegram Bot API (notifica o dono)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="destinatário e conteúdo de terceiro",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="irreversível só para tipos promovidos (liberam sozinhos ao fim da janela de cancelamento, sem "
        "nova confirmação); outros tipos são revisáveis via descartar_rascunho_whatsapp. Classificado "
        "IRREVERSIVEL ao nível da tool (mesma convenção de decidir_elevacao/decidir_promocao_autonomia para "
        "a mesma forma de nuance -- 'irreversível só para um subconjunto') -- achado da revisão adversarial "
        "de P03 sub-entrega 6/N: a classificação original (REVERSIVEL) divergia dessa convenção e produzia "
        "destructiveHint=False enganoso em tools/registry.py::mcp_annotations para o caso de risco real "
        "(tipo promovido). Não idempotente (P03 sub-entrega 19/N): `outbox_aprovacao.py::criar_rascunho` faz "
        "`db.collection('whatsapp_outbox').document()` (ID automático) + `.set()` incondicional, sem dedup "
        "por destinatário/mensagem/motivo -- repetir a MESMA chamada cria um SEGUNDO rascunho distinto, "
        "dispara um SEGUNDO card no Telegram e, se o tipo já estiver promovido para autonomia, pode liberar "
        "uma SEGUNDA mensagem real de WhatsApp sozinho ao fim da janela.",
    ),
    "listar_rascunhos_pendentes": ToolInventoryEntry(
        "whatsapp", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA, "nenhum",
        dados_sensiveis_categoria="destinatário/trecho de mensagens pendentes",
    ),
    "aprovar_rascunho_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.ESCRITA, _R.IRREVERSIVEL, True, True, _C.COMPROMISSO_TERCEIROS,
        "transação Firestore garante exclusão mútua com liberação automática; não verifica entrega",
        rede_servico="Telegram (edit_message do card)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="destinatário e conteúdo de terceiro",
    ),
    "descartar_rascunho_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.ESCRITA, _R.REVERSIVEL, True, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "transação Firestore revalida status antes de escrever",
        rede_servico="Telegram (edit_message condicional)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="destinatário e conteúdo de terceiro",
    ),
    "cancelar_envio_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.ESCRITA, _R.REVERSIVEL, True, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "transação Firestore revalida status antes de escrever — a mesma disputa que "
        "claimOutboxMessage (services/whatsapp-capture/index.js) resolve do lado do worker",
        rede_servico="Telegram (edit_message condicional)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="destinatário e conteúdo de terceiro",
        idempotencia=_I.IDEMPOTENTE,
        nota="cancelar um job já 'canceled' devolve status 'already_canceled' sem nova escrita "
        "(a transação lê o status atual e recusa antes do tx.update); só aceita a partir de "
        "'pending' ou 'notified' (validar_transicao_cancelamento em outbox_aprovacao.py) — "
        "qualquer outro status (sent, failed, aguardando_aprovacao, ...) é recusado com erro.",
    ),
    "solicitar_autorizacao_argos": ToolInventoryEntry(
        "argos_autorizacao", _L.ESCRITA, _R.IRREVERSIVEL, True, False, _C.COORDENACAO_LIMITADA,
        "nenhum — consultar_autorizacao_argos é chamado depois, manualmente",
        rede_servico="Telegram Bot API", nota="sem tool de cancelamento; só expira sozinha por tempo",
        dominio_rede=DominioRede.FECHADO,
    ),
    "consultar_autorizacao_argos": ToolInventoryEntry(
        "argos_autorizacao", _L.LEITURA_E_ESCRITA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA,
        "ela própria é o verificador informal que outra tool deveria chamar antes de agir no Argos",
        nota="escrita é efeito colateral passivo (expira item já vencido durante a leitura), não o "
        "propósito da tool — por isso nao_aplica em vez de reversivel/irreversivel",
    ),
    "consumir_autorizacao_argos": ToolInventoryEntry(
        "argos_autorizacao", _L.ESCRITA, _R.IRREVERSIVEL, False, False, _C.COORDENACAO_LIMITADA,
        "nenhum — falta o 'recibo do Argos correlacionado' que o próprio plano (seção 4.6) já aponta como lacuna",
        nota="uso único por desenho — nunca autoriza duas vezes",
    ),
    "confirmar_acao": ToolInventoryEntry(
        "confirmacao_mcp", _L.LEITURA_E_ESCRITA, _R.IRREVERSIVEL, True, True,
        _C.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
        "o claim atômico (create) evita dupla execução — verificador estrutural real; não confere se o "
        "efeito desejado de fato ocorreu",
        rede_servico="variável — o da tool delegada (Firestore-only, Gmail, ou o serviço externo de investimentos)",
        dados_sensiveis_categoria="variável — a da tool delegada (hoje sempre destinatário/conteúdo de "
        "terceiro ou financeiro, nunca dado neutro)",
        nota="gate genérico: delega para a tool do piso originalmente pedida (hoje: schedule_whatsapp_message, "
        "pausar_conversa, criar_rascunho_email, registrar_aporte_investimento, registrar_execucao_investimento). "
        "Os campos acima refletem o pior caso do piso atual (financeiro), não uma execução fixa — a "
        "classificação real de cada chamada é a da tool delegada, idempotência incluída (não investigada "
        "nesta sub-entrega, P03 sub-entrega 19/N, por depender do gate MCP e da tool delegada em cada "
        "chamada, fora do escopo de uma leitura direta de handler único). O claim atômico (create) do "
        "próprio gate evita RE-EXECUÇÃO da MESMA confirmação (retry de rede) -- mas uma NOVA confirmação "
        "para o mesmo pedido do usuário gera um `mcp_confirmation_id` diferente e delega de novo, mesmo "
        "caveat já aceito em `pausar_conversa` (sub-entrega 17/N).",
    ),
    "pausar_conversa": ToolInventoryEntry(
        "whatsapp", _L.ESCRITA, _R.IRREVERSIVEL, False, True, _C.COMPROMISSO_TERCEIROS, "nenhum",
        dados_sensiveis_categoria="conversa com terceiro",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="classificação COMPROMISSO_TERCEIROS já existe em autonomy/policy.py::CLASSE_EFEITO_PISO. Não "
        "idempotente (P03 sub-entrega 17/N): `pausar()` (tools/pausar_conversa.py) chama "
        "`schedule_whatsapp_message(..., idempotency_key=ctx.mcp_confirmation_id)` -- o dedup só protege "
        "reenvio dentro da MESMA confirmação MCP (retry de rede), não uma segunda chamada da tool com os "
        "mesmos argumentos através de uma NOVA confirmação, que gera um `mcp_confirmation_id` diferente e "
        "portanto uma segunda mensagem real de WhatsApp enfileirada -- por si só já desqualifica idempotentHint; "
        "quando há ação vinculada (task and task_ref, não sempre), `task_ref.update` também grava "
        "`firestore.ArrayUnion` em `acompanhamento` (nota nova com timestamp novo) a cada chamada bem-sucedida "
        "nesse caminho -- mesmo padrão de não idempotência já usado para `editar_acao` (sub-entrega 16/N).",
    ),
    "criar_rascunho_email": ToolInventoryEntry(
        "email", _L.LEITURA_E_ESCRITA, _R.IRREVERSIVEL, True, True, _C.COMPROMISSO_TERCEIROS,
        "devolve draft_id + link — verificador mínimo existe, raro no inventário",
        rede_servico="Gmail API (drafts.create, threads.get, getProfile)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="destinatário e conteúdo de terceiro",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="classificação COMPROMISSO_TERCEIROS já existe em autonomy/policy.py::CLASSE_EFEITO_PISO, apesar "
        "da descrição do catálogo dizer 'nunca envia'; nenhuma tool exclui um rascunho Gmail já criado. Não "
        "idempotente (P03 sub-entrega 17/N): `tools/criar_rascunho_email.py::criar` chama "
        "`service.users().drafts().create(...)` sem nenhuma chave de idempotência passada à API do Gmail -- "
        "repetir com os mesmos argumentos cria um segundo rascunho com `draft_id` novo, e se `acao_id` estiver "
        "presente também grava um segundo `firestore.ArrayUnion` em `acompanhamento`.",
    ),
    "buscar_contato": ToolInventoryEntry(
        "contatos", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA, "nenhum necessário",
        dados_sensiveis_categoria="nome, telefone, e-mail, whatsapp_chat_id de terceiros",
    ),
    "preparar_vinculo_contatos": ToolInventoryEntry(
        "contatos", _L.LEITURA, _R.NAO_APLICA, False, True, _C.PREPARACAO_INTERNA,
        "não aplicável — sem confirmar_vinculo_contatos no MCP; aplicação real só existe na UI web",
        dados_sensiveis_categoria="dados pessoais de contato",
    ),
    "preparar_atualizacao_contato": ToolInventoryEntry(
        "contatos", _L.LEITURA, _R.NAO_APLICA, False, True, _C.PREPARACAO_INTERNA,
        "não aplicável — mesma lacuna: sem contraparte de confirmação no MCP",
        dados_sensiveis_categoria="dados pessoais de contato",
    ),
    "registrar_interacao_contato": ToolInventoryEntry(
        "contatos", _L.ESCRITA, _R.IRREVERSIVEL, False, True, _C.ESCRITA_INTERNA_REVERSIVEL, "nenhum",
        dados_sensiveis_categoria="histórico de interação com terceiro",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="sem tool de edição/remoção de uma interação já registrada. Não idempotente (P03 sub-entrega "
        "17/N): `tools/hermes_tools.py::registrar_interacao_contato` usa "
        "`ctx.db.collection('interacoes_pessoas').document()` (ID automático) + `.set()` incondicional -- sem "
        "chave de dedup, repetir com os mesmos argumentos cria uma segunda interação.",
    ),
    "consultar_saude": ToolInventoryEntry(
        "saude", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA, "nenhum necessário",
        dados_sensiveis_categoria="saúde",
    ),
    "registrar_saude": ToolInventoryEntry(
        "saude", _L.ESCRITA, _R.REVERSIVEL, False, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum automático, mas upsert idempotente por dia+campo permite correção via nova chamada",
        dados_sensiveis_categoria="saúde",
        idempotencia=_I.IDEMPOTENTE,
        nota="idempotente por dia+campo (P03 sub-entrega 17/N): peso/cintura usam `_gravar_por_data` "
        "(tools/registrar_saude.py) -- consulta o doc do dia ANTES de escrever, atualiza em vez de duplicar "
        "(coberto por test_registrar_saude.py::test_peso_duas_vezes_nao_duplica); dor/sono/calorias usam ID "
        "determinístico (`COL_LOGS.document(dia)`) com `.set(merge=True)`. Caveat 1 (encontrado nesta "
        "sub-entrega): quando algum `dor_*` está presente, `log_updates['pain']` inclui `mcp_checked_at` com "
        "timestamp NOVO a cada chamada -- o valor gravado muda mesmo repetindo os mesmos argumentos. Corrigido "
        "na 1ª rodada de revisão adversarial: NÃO é escrita-apenas como a versão inicial desta nota afirmava -- "
        "`health_tools.py::build_health_summary` reencaminha o dict `pain` inteiro (mcp_checked_at incluso) "
        "para `consultar_saude`/Godmode, então É observável por um cliente MCP; é inerte (nenhuma rotina, "
        "decisão ou valor de negócio lê especificamente esse campo), mas 'nunca lido' era impreciso. Caveat 2 "
        "(idem): nem `_gravar_por_data` nem o `.set(merge=True)` por data usam exclusão mútua atômica (ao "
        "contrário de `claim_action_dedup_slot`, usado por `criar_acao_no_sistema`) -- é consulta-depois-escreve; "
        "duas chamadas genuinamente CONCORRENTES (não um retry sequencial após resposta) poderiam, em teoria, "
        "ambas passarem pela checagem antes de qualquer uma gravar. Nenhum dos dois caveats muda a classificação "
        "-- mesmo espírito do caveat de TTL em `criar_acao_no_sistema` (sub-entrega 16/N): documentado para "
        "nenhum cliente MCP assumir garantia mais forte do que a tool de fato oferece.",
    ),
    "consultar_dados_cadastrais": ToolInventoryEntry(
        "dados_cadastrais", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum necessário",
        dados_sensiveis_categoria="documentos, família, carreira, dados bancários, plano de saúde",
    ),
    "registrar_no_diario": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.IRREVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL, "nenhum",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="o plano (seção 5.1) usa 'diário factual' como exemplo textual de escrita reversível, mas "
        "nenhuma tool deste catálogo remove uma entrada já escrita (ArrayUnion) — reversibilidade é "
        "conceitual, não uma capacidade real hoje. Não idempotente (P03 sub-entrega 16/N): cada "
        "chamada monta `entry` com `datetime.now(timezone.utc)` novo e faz `ArrayUnion([entry])` -- "
        "repetir com a mesma nota acrescenta uma segunda linha ao diário, nunca substitui a primeira",
    ),
    "gerar_imagem": ToolInventoryEntry(
        "utilitario", _L.ESCRITA, _R.IRREVERSIVEL, True, False, _C.PREPARACAO_INTERNA,
        "nenhum — não confere se a imagem corresponde ao prompt nem se a URL segue acessível",
        rede_servico="Gemini (geração) + Google Cloud Storage (upload)",
        dominio_rede=DominioRede.FECHADO,
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="upload permanente no bucket público; sem tool de exclusão. Não idempotente (P03 sub-entrega "
        "19/N): `tools/hermes_tools.py::gerar_imagem` nomeia o blob com `uuid4().hex[:8]` e faz "
        "`upload_from_string` incondicional a cada chamada -- repetir o MESMO prompt gera uma SEGUNDA "
        "imagem persistida com URL distinta. Efeito adicional a mais, sem relação com o upload: "
        "`check_and_increment_limit` (gemini_cost_controls.py) incrementa um contador diário de cota ANTES "
        "da geração, em toda chamada que passa da checagem -- outro estado que muda a cada repetição, mesmo "
        "que a imagem em si falhasse depois.",
    ),
    "preparar_reagendamento_em_lote": ToolInventoryEntry(
        "acoes_tarefas", _L.LEITURA, _R.NAO_APLICA, False, False, _C.PREPARACAO_INTERNA,
        "não aplicável — confirmar_reagendamento_em_lote aplica",
    ),
    "preparar_remocao_horarios_em_lote": ToolInventoryEntry(
        "acoes_tarefas", _L.LEITURA, _R.NAO_APLICA, False, False, _C.PREPARACAO_INTERNA,
        "não aplicável — sem confirmar_* dedicado neste catálogo; aplicação real só existe na UI web",
    ),
    "criar_objetivo_estrategico": ToolInventoryEntry(
        "estrategico", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum automático; corrigível via editar_objetivo_estrategico",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="`strategy_tools.criar_objetivo_estrategico` sempre grava em "
        "`db.collection('estrategia_pessoal').document()` (ID automático do Firestore) -- repetir a MESMA "
        "chamada cria um SEGUNDO objetivo estratégico distinto, nunca devolve o já existente (P03 "
        "sub-entrega 18/N)",
    ),
    "editar_objetivo_estrategico": ToolInventoryEntry(
        "estrategico", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL, "nenhum",
        idempotencia=_I.IDEMPOTENTE,
        nota="`strategy_tools.editar_objetivo_estrategico` faz `ref.update(updates)` num objetivo já "
        "existente identificado por `objetivo_id` -- `updates` é recomputado deterministicamente a partir "
        "dos argumentos a cada chamada (mesmos argumentos -> mesmo dict), sem nenhum append/ArrayUnion; "
        "repetir grava os mesmos valores de negócio de novo. Único campo que muda a cada chamada é "
        "`timestamp` (SERVER_TIMESTAMP), não lido por nenhuma decisão/rotina (confirmado por busca no "
        "código) -- mesmo espírito do caveat de `mcp_checked_at` já aceito em `registrar_saude` (P03 "
        "sub-entrega 17/N) (P03 sub-entrega 18/N)",
    ),
    "gerenciar_item_estrategico": ToolInventoryEntry(
        "estrategico", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "transação Firestore evita perda de escrita concorrente; não verifica o resultado semanticamente",
        nota="idempotência investigada e deixada SEM classificação (P03 sub-entrega 18/N): o comportamento "
        "depende do parâmetro `acao` (`adicionar`/`editar`/`remover`/`concluir`), interno a esta única tool "
        "-- `adicionar` gera `novo_id_estrategia()` novo a cada chamada (NAO_IDEMPOTENTE, cria um segundo "
        "item); `editar` sobrescreve a descrição do mesmo item por `item_id` (IDEMPOTENTE); `remover` erra "
        "na segunda chamada porque o item já não está mais na lista (mesma ambiguidade de "
        "`revogar_promocao_autonomia`); `concluir` regrava `dataConclusao` com um timestamp NOVO a cada "
        "chamada -- efeito adicional real, não só inerte. Um hint único não descreveria os quatro ramos "
        "honestamente -- um hint errado é pior que a omissão.",
    ),
    "excluir_objetivo_estrategico": ToolInventoryEntry(
        "estrategico", _L.ESCRITA, _R.IRREVERSIVEL, False, False,
        _C.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
        "nenhum",
        nota="delete() definitivo, sem soft-delete nem tool de restauração — 'exclusão definitiva' é exemplo "
        "textual desta classe na matriz do plano (seção 5.1). ACHADO: apesar disso, esta tool não está no "
        "piso FLOOR_CONFIRMACAO_OBRIGATORIA do MCP — hoje uma sessão MCP pode excluir um objetivo estratégico "
        "numa única chamada, sem segunda confirmação estrutural. Idempotência investigada e deixada SEM "
        "classificação (P03 sub-entrega 18/N): `ref.delete()` em si não tem efeito adicional se repetido, "
        "mas o HANDLER (`carregar_objetivo_estrategico`, fail-closed) já barra a segunda chamada antes de "
        "chegar em `delete()` -- devolve `status=error/objetivo_nao_encontrado` em vez de um 'já excluído' "
        "gracioso, a mesma ambiguidade resposta-muda-mas-ambiente-não já aceita para "
        "`revogar_promocao_autonomia` (sub-entrega 16/N): um hint errado é pior que a omissão.",
    ),
    "consultar_processo_sipac": ToolInventoryEntry(
        "sipac", _L.LEITURA, _R.NAO_APLICA, True, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum — confia no scrape; falha vira erro explícito, não 'processo vazio'",
        rede_servico="scraper SIPAC via Cloud Function Node (scrapeSIPACProcess)",
        dados_sensiveis_categoria="nomes de interessados do processo",
    ),
    "acompanhar_processo_sipac": ToolInventoryEntry(
        "sipac", _L.LEITURA_E_ESCRITA, _R.REVERSIVEL, True, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum", rede_servico="mesmo scraper SIPAC",
        dados_sensiveis_categoria="nomes de interessados do processo",
        nota="liga/desliga flag de monitoramento; chamar de novo com acompanhar=False desfaz",
    ),
    "confirmar_edicao_acao": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "devolve campos_alterados com o que de fato foi gravado (pode divergir do pedido) — verificador "
        "real, raro neste inventário",
    ),
    "confirmar_edicao_em_lote": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "mais fraco que a versão singular — devolve só count, não os campos aplicados por item",
    ),
    "confirmar_reagendamento_em_lote": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "mesmo padrão fraco — só count, sem confirmação por item das novas datas aplicadas",
    ),
    "consultar_job": ToolInventoryEntry(
        "utilitario", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "confere só uid do chamador contra o dono do job; não audita se o resultado corresponde ao pedido",
        dados_sensiveis_categoria="variável — passthrough genérico do resultado de qualquer uma das "
        "_ASYNC_TOOLS (tools/registry.py), duas das quais já são dados_sensiveis=True neste inventário "
        "(buscar_e_analisar_email, ler_documento_na_integra)",
        nota="mesmo padrão de 'pior caso do delegado' usado em confirmar_acao",
    ),
    "editar_acao": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum automático — devolve campos_alterados; reconferência via obter_acao é opcional",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="o `set` dos campos em `alteracoes` é idempotente isoladamente (mesmo valor produz o "
        "mesmo estado), mas o handler delega para `main.py::confirmarEdicaoAcao`, que monta seu "
        "PRÓPRIO `diary_entry` (com `now_iso` novo) e faz `ArrayUnion([diary_entry])` em TODA chamada "
        "bem-sucedida, incondicionalmente -- não só quando `motivo`/`motivo_adiamento` está presente "
        "(correção da 4ª rodada de revisão adversarial desta sub-entrega: a redação anterior atribuía "
        "a não idempotência só ao caminho opcional de `motivo`). Repetir a MESMA chamada com os MESMOS "
        "`alteracoes`, mesmo sem `motivo`, já acrescenta uma nova linha ao diário a cada vez -- essa é "
        "a razão primária. `motivo_adiamento`/`motivo`, quando presente, aciona um SEGUNDO append "
        "separado (inline em tools/hermes_tools.py, mesmo padrão ArrayUnion, mas não uma chamada "
        "literal a `registrar_no_diario`) -- soma-se ao primeiro, não é a única causa (P03 sub-entrega "
        "16/N)",
    ),
    "editar_acoes_em_lote": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum automático",
    ),
    "reagendar_acoes_em_lote": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum automático — devolve contagem, sem reconferência",
    ),
    "obter_estado_atual": ToolInventoryEntry(
        "utilitario", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum — falhas de subcomponentes viram listas/contadores zero sem diferenciar de 'vazio real'",
        dados_sensiveis_categoria="agrega medições de saúde do dia (peso, cintura)",
    ),
    "listar_respostas_pendentes": ToolInventoryEntry(
        "whatsapp", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA, "nenhum",
        dados_sensiveis_categoria="remetente/trecho de conversas de terceiros",
    ),
    "dispensar_resposta_pendente": ToolInventoryEntry(
        "whatsapp", _L.ESCRITA, _R.IRREVERSIVEL, False, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — motivo é texto livre do chamador, sem validação de conteúdo",
        dados_sensiveis_categoria="pode referenciar contato/conversa de terceiro",
        idempotencia=_I.IDEMPOTENTE,
        nota="sem caminho de volta -- não há tool de undispensar; dispensa vale só para o "
             "trecho/snippet atual (fingerprint no item_id), não para a conversa/thread inteira. "
             "Idempotente (P03 sub-entrega 16/N): `inbox_pendentes.dispensar` grava com "
             "`.document(item_id).set(...)`, ID determinístico igual ao próprio item_id -- repetir "
             "com o mesmo item_id/motivo sobrescreve o mesmo documento (só `dispensado_em` muda), "
             "nunca cria um segundo registro nem duplica o efeito de 'não reaparecer na fila'",
    ),
    "obter_acao": ToolInventoryEntry(
        "acoes_tarefas", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum necessário",
    ),
    "anexar_arquivo": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, True, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "confere sha256/tamanho/md5 antes de gravar (conforme a via); reverte o upload no Drive se a "
        "vinculação à tarefa falhar",
        rede_servico="Google Drive sempre; Gmail API ou URL arbitrária conforme a origem",
        dados_sensiveis_categoria="pode ser comprovante/documento pessoal (prestação de contas, recibo)",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="reversível via remover_anexo. NAO_IDEMPOTENTE (P03 sub-entrega 18/N): "
        "`tools/anexar_arquivo.py::anexar` sempre cria um arquivo NOVO no Drive (`service.files().create()`, "
        "ID novo do Google a cada chamada) e um item novo no pool (`uuid.uuid4()[:8]`) -- repetir a MESMA "
        "chamada sobe o mesmo conteúdo duas vezes, como dois anexos distintos, nunca devolve o já existente",
    ),
    "atualizar_arquivo_drive": ToolInventoryEntry(
        "utilitario", _L.ESCRITA, _R.REVERSIVEL, True, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "confere o md5 devolvido pelo Drive (arquivo de texto) ou que o Doc não ficou vazio após a "
        "conversão; recusa conteúdo vazio, tipo não suportado, arquivo na lixeira, arquivo sem permissão "
        "de edição, arquivo que não é do dono e conteúdo com menos de 40% do tamanho atual (reescrita "
        "incompleta) antes de gravar; com esperado_modificado_em recusa se o arquivo foi modificado depois "
        "da leitura de quem chama (concorrência otimista); o conteúdo não vai para o mcp_audit_log (só "
        "tamanho e sha256)",
        rede_servico="Google Drive (conta do próprio dono)",
        dados_sensiveis_categoria="qualquer documento do Drive do dono",
        nota="reversível: a versão anterior fica no histórico de versões do PRÓPRIO arquivo (Arquivo > Histórico "
        "de versões). Só Google Docs e arquivos de texto; Planilha, Apresentação, PDF, imagem e .docx são "
        "recusados. IDEMPOTENTE no estado do arquivo (repetir a mesma chamada deixa o mesmo conteúdo), embora o "
        "Drive possa registrar uma revisão a mais no histórico.",
        dominio_rede=DominioRede.FECHADO,
        idempotencia=_I.IDEMPOTENTE,
    ),
    "preparar_upload": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, True, False, _C.PREPARACAO_INTERNA,
        "conferência real (tamanho/sha256) acontece na chamada seguinte, dentro de anexar_arquivo",
        rede_servico="Google Cloud IAM signBlob (URL assinada)",
        dominio_rede=DominioRede.FECHADO,
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="grava doc em uploads_pendentes apesar do nome sugerir só preparo em memória; token de uso "
        "único, expira em 15 min, nada é aplicado a nenhuma tarefa por esta chamada. NAO_IDEMPOTENTE (P03 "
        "sub-entrega 18/N): `token = f\"upl-{secrets.token_urlsafe(16)}\"` é gerado novo a cada chamada -- "
        "repetir a MESMA chamada devolve uma URL assinada e um token DIFERENTES, nunca o mesmo",
    ),
    "remover_anexo": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.IRREVERSIVEL, True, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — devolve só um booleano de lixeira, sem confirmar que era o anexo certo",
        rede_servico="Google Drive (mover para lixeira)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="documento anexado",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="sem tool para restaurar o vínculo exato; arquivo vai para a lixeira do Drive (recuperável por "
        "30 dias fora do Hermes). NAO_IDEMPOTENTE (P03 sub-entrega 18/N): todo sucesso faz `ArrayUnion` de "
        "uma nova nota de retificação com timestamp novo em `acompanhamento`; além disso, repetir a MESMA "
        "chamada depois do item já removido do `pool_dados` devolve erro ('não está no pool'), não um "
        "sucesso silencioso",
    ),
    "consultar_fatura_cartao": ToolInventoryEntry(
        "financas_pessoais", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA, "nenhum",
        dados_sensiveis_categoria="financeiro",
    ),
    "consultar_compromissos_futuros": ToolInventoryEntry(
        "financas_pessoais", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum — projeção determinística sobre dados já gravados", dados_sensiveis_categoria="financeiro",
    ),
    "listar_conversas_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA, "nenhum",
        dados_sensiveis_categoria="nomes/ids de conversas",
    ),
    "sincronizar_conversas_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.ESCRITA, _R.REVERSIVEL, False, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "consultar novamente com o request_id até status=done; então relistar as conversas",
        dados_sensiveis_categoria="nomes/ids de conversas",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="sem request_id cria um novo pedido em whatsapp_chats_sync_requests a cada chamada; com "
        "request_id apenas consulta o pedido existente. O efeito é uma atualização recuperável do "
        "catálogo local, sem enviar mensagem nem alterar conteúdo de conversa.",
    ),
    "ler_mensagens_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "allowlist de chat monitorado é o único portão, não uma verificação de resultado",
        dados_sensiveis_categoria="conteúdo literal de mensagens de terceiros",
    ),
    "consolidar_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.ESCRITA, _R.IRREVERSIVEL, True, True, _C.PREPARACAO_INTERNA,
        "nenhum automático da qualidade da síntese; implícito: releitura do transcript literal",
        rede_servico="Groq/Whisper (áudio) e Gemini (vídeo + síntese), via trigger assíncrono disparado pelo handler",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="conteúdo de conversas de terceiros",
        nota="handler síncrono só grava doc 'queued'; sem tool para desfazer uma consolidação",
    ),
    "ler_consolidacao_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA, "nenhum",
        dados_sensiveis_categoria="conteúdo de conversas de terceiros",
    ),
    "consultar_envio_whatsapp": ToolInventoryEntry(
        "whatsapp", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "ela mesma é o verificador de schedule_whatsapp_message ('enfileirar não é enviar')",
        dados_sensiveis_categoria="número de destino e trecho da mensagem",
    ),
    "consultar_investimentos": ToolInventoryEntry(
        "investimentos", _L.LEITURA_E_ESCRITA, _R.NAO_APLICA, True, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum quanto à exatidão da carteira externa — Hermes repassa a resposta sem conferência própria",
        rede_servico="serviço externo decisao-investimentos (Cloud Run, yfinance + SGS/Bacen)",
        dados_sensiveis_categoria="financeiro",
        idempotencia=_I.IDEMPOTENTE,
        nota="escrita é efeito colateral condicional e idempotente (dedupe por tag, só quando a decisão "
        "externa mudou), não o propósito da tool — por isso nao_aplica em vez de reversivel/irreversivel. "
        "Idempotente (P03 sub-entrega 17/N): `investimentos_sync.sincronizar_decisao_investimentos` "
        "consulta `tarefas` por `tags array_contains 'investimentos-decisao-{mes}'` ANTES de criar -- se já "
        "existe, devolve `status: ja_existe` sem gravar de novo; sem TTL/janela de expiração (dedup permanente "
        "por mês), diferente do caveat de `criar_acao_no_sistema`. Coberto por "
        "test_investimentos_sync.py::test_idempotencia_nao_duplica_acao. Caveat (achado da revisão adversarial "
        "desta sub-entrega): a checagem não usa exclusão mútua atômica (`create()`/transação, como "
        "`claim_action_dedup_slot`) -- é consulta-depois-escreve; duas chamadas genuinamente CONCORRENTES "
        "(não um retry sequencial após resposta) poderiam, em teoria, ambas passar pela checagem antes de "
        "qualquer uma criar a ação, duplicando-a. Não corrigido nesta fatia, só documentado.",
    ),
    "registrar_aporte_investimento": ToolInventoryEntry(
        "investimentos", _L.ESCRITA, _R.IRREVERSIVEL, True, True,
        _C.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
        "nenhum automático — timeout/5xx marca escrita_ambigua; instrução é reconsultar via "
        "consultar_investimentos, nunca repetir",
        rede_servico="POST ao serviço externo decisao-investimentos", dados_sensiveis_categoria="financeiro",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="classificação canônica em autonomy/policy.py::CLASSE_EFEITO_PISO; soma ao aporte total externo, "
        "sem endpoint de estorno. Não idempotente (P03 sub-entrega 17/N): a docstring do próprio "
        "`investimentos.registrar_aporte` é explícita -- 'Não é idempotente do lado do serviço: chamar duas "
        "vezes com R$ 500 registra R$ 1.000' -- repetir ACUMULA, não converge para o mesmo estado.",
    ),
    "registrar_execucao_investimento": ToolInventoryEntry(
        "investimentos", _L.ESCRITA, _R.REVERSIVEL, True, True,
        _C.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
        "mesmo padrão do aporte — reconsulta manual via consultar_investimentos é o único caminho",
        rede_servico="POST ao serviço externo decisao-investimentos", dados_sensiveis_categoria="financeiro",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="classificação canônica em autonomy/policy.py::CLASSE_EFEITO_PISO; declarativo (repetir não "
        "acumula posição), mas grava uma 2ª linha no log de movimentos, não apagável. Não idempotente (P03 "
        "sub-entrega 17/N): apesar de a posição final da carteira não mudar numa repetição "
        "(`investimentos.confirmar_execucao` é declarativo), a própria docstring do módulo confirma que cada "
        "chamada 'grava uma segunda linha no log de movimentos' -- um efeito adicional real e persistente (não "
        "apagável), que desqualifica idempotentHint mesmo com o estado principal convergindo; mesmo critério "
        "que classificou `editar_acao` como não idempotente por um append incondicional (sub-entrega 16/N), "
        "aqui aplicado a um serviço externo em vez do Firestore próprio.",
    ),
    "obter_fila_atencao": ToolInventoryEntry(
        "atencao_fila", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA, "nenhum",
        dados_sensiveis_categoria="itens podem ter origem em WhatsApp de terceiro",
    ),
    "resolver_item_atencao": ToolInventoryEntry(
        "atencao_fila", _L.ESCRITA, _R.IRREVERSIVEL, False, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — desfecho é texto livre do chamador, sem validação de conteúdo",
        dados_sensiveis_categoria="pode referenciar contato/conversa de terceiro",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="sem caminho de volta a 'aberto' por esta tool. Não idempotente (P03 sub-entrega 16/N): "
        "o `.update()` do próprio item de atenção converge para o mesmo estado, mas quando o item "
        "tem `acao_id` e `desfecho` (obrigatório para resolver/descartar), `atencao.resolver_item` "
        "chama `registrar_no_diario` -- que acrescenta uma nova linha ao diário da ação a cada "
        "chamada, sem checar se a nota já existe",
    ),
    "consultar_pedidos_agente": ToolInventoryEntry(
        "autonomia_pedidos_agente", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum",
    ),
    "concluir_pedido_agente": ToolInventoryEntry(
        "autonomia_pedidos_agente", _L.ESCRITA, _R.IRREVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "transação Firestore impede duas conclusões concorrentes; não confere se resultado/erro é "
        "factualmente correto",
        idempotencia=_I.IDEMPOTENTE,
        nota="transição terminal, sem tool de reabertura. Idempotente por desenho, não só por "
        "observação (P03 sub-entrega 16/N): `agent_requests.concluir` já documenta 'É idempotente' "
        "na própria docstring -- `validar_transicao` recusa qualquer transição a partir de um "
        "status já terminal e devolve `status='already_decided'` sem tocar no registro existente, "
        "dentro de uma transação Firestore (protege inclusive contra duas chamadas concorrentes)",
    ),
    "registrar_execucao_agente": ToolInventoryEntry(
        "autonomia_pedidos_agente", _L.ESCRITA, _R.IRREVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — grava o que o chamador declarar, sem contraprova",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="log append-only. Não idempotente (P03 sub-entrega 16/N): `agent_runs.registrar` sempre "
        "faz `col.add(payload)` -- Firestore gera um ID novo a cada chamada, sem chave de dedup "
        "nenhuma; repetir os mesmos argumentos cria um segundo registro de execução distinto",
    ),
    "consultar_execucoes_agente": ToolInventoryEntry(
        "autonomia_pedidos_agente", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum",
    ),
    "preparar_contato_prioritario_secretario": ToolInventoryEntry(
        "whatsapp_secretario", _L.ESCRITA, _R.REVERSIVEL, False, True, _C.COORDENACAO_LIMITADA,
        "nenhum — resolução de contato pode ambiguar e nada revalida depois",
        dados_sensiveis_categoria="nome/telefone/assunto de terceiro",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="grava direto no Firestore apesar do nome 'preparar_'; não há segunda chamada de confirmação "
        "como nas demais preparar_*; reversível via cancelar_contato_prioritario_secretario. "
        "NAO_IDEMPOTENTE (P03 sub-entrega 18/N): `valido_ate` é recalculado a partir de 'agora' a cada "
        "chamada (estende o prazo do briefing a cada repetição), `criado_em` é regravado com um timestamp "
        "NOVO em vez de preservar o original, e a conversa vinculada é resetada por completo "
        "(`historico_mensagens=[]`, `trocas_count=0`, `estado=EM_ATENDIMENTO`) em TODA chamada bem-sucedida",
    ),
    "consultar_contatos_prioritarios_secretario": ToolInventoryEntry(
        "whatsapp_secretario", _L.LEITURA_E_ESCRITA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "expiração por validade é o único mecanismo automático, aplicado na própria leitura",
        dados_sensiveis_categoria="dados de contato prioritário",
        nota="escrita é efeito colateral passivo (expira item já vencido durante a leitura), não o "
        "propósito da tool — por isso nao_aplica em vez de reversivel/irreversivel",
    ),
    "cancelar_contato_prioritario_secretario": ToolInventoryEntry(
        "whatsapp_secretario", _L.ESCRITA, _R.REVERSIVEL, False, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum", dados_sensiveis_categoria="dados de contato prioritário",
        idempotencia=_I.IDEMPOTENTE,
        nota="`secretario_whatsapp.cancelar_contato_prioritario` faz `.update({'status': CANCELADO, "
        "'atualizado_em': SERVER_TIMESTAMP})` sobre o mesmo doc encontrado por chat_id, sem checar o status "
        "atual antes -- repetir a MESMA chamada devolve sucesso de novo e mantém `status=CANCELADO` (nenhum "
        "outro campo de negócio muda); só `atualizado_em` bate um timestamp novo a cada chamada, não lido "
        "por nenhuma decisão/rotina (mesmo espírito do caveat de `mcp_checked_at`, sub-entrega 17/N) (P03 "
        "sub-entrega 18/N)",
    ),
    "ativar_modo_secretario": ToolInventoryEntry(
        "whatsapp_secretario", _L.ESCRITA, _R.REVERSIVEL, False, True, _C.COORDENACAO_LIMITADA,
        "nenhum — reconferência via consultar_status_modo_secretario é opcional",
        dados_sensiveis_categoria="allowlist de contatos terceiros",
        idempotencia=_I.NAO_IDEMPOTENTE,
        nota="só grava system/settings — nenhuma chamada à infra de envio do WhatsApp acontece nesta tool; "
        "reversível via desativar_modo_secretario. NAO_IDEMPOTENTE (P03 sub-entrega 18/N): quando "
        "`duracao_horas` é informado, `desativa_em` é recalculado a partir de 'agora' a cada chamada -- "
        "repetir a MESMA chamada mais tarde ESTENDE o prazo de desativação automática, um efeito real no "
        "ambiente, não só cosmético (quando `duracao_horas` é omitido o efeito converge, mas a classificação "
        "cobre a tool como um todo, lado conservador). `orientacoes` (texto livre do dono, até 2000 caracteres) entra no prompt do secretário abaixo dos guardrails fixos e NUNCA os revoga; com `salvar_como_padrao` grava o padrão em `whatsapp_secretario.orientacoes`, senão só vale nesta ativação. "
        "`escopo_contatos` ('individuais'/'grupos'/'todos'/'nenhum') liga um escopo universal aditivo à "
        "`chats_allowlist` explícita (grupo continua exigindo menção ao André mesmo sob escopo); `ativa_em`/"
        "`desativa_em` (ISO 8601 absolutos) definem uma janela com início e fim arbitrários, checada "
        "passivamente na leitura (`obter_config_secretario`) igual ao `desativa_em` calculado por `duracao_horas` — sem cron novo.",
    ),
    "desativar_modo_secretario": ToolInventoryEntry(
        "whatsapp_secretario", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — desligar é sempre seguro/imediato por design",
        idempotencia=_I.IDEMPOTENTE,
        nota="`secretario_whatsapp.desativar_modo_secretario` sempre grava `enabled=False, desativa_em=None` "
        "-- sem nenhum campo variável por chamada (nem timestamp), repetir a MESMA chamada produz exatamente "
        "o mesmo estado persistido todas as vezes (P03 sub-entrega 18/N)",
    ),
    "consultar_status_modo_secretario": ToolInventoryEntry(
        "whatsapp_secretario", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum necessário — expiração passiva aplicada na própria leitura",
        dados_sensiveis_categoria="nomes resolvidos de contatos na allowlist",
    ),
    "consultar_politica": ToolInventoryEntry(
        "autonomia_politica", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA,
        "nenhum necessário — função pura, sem mutação (conforme docstring do próprio módulo)",
    ),
    "simular_politica": ToolInventoryEntry(
        "autonomia_politica", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA,
        "ela mesma é o verificador de uma mudança de política antes de aplicá-la; nada garante que o "
        "cenário simulado reflete os pedidos reais futuros",
    ),
    "preparar_politica": ToolInventoryEntry(
        "autonomia_politica", _L.LEITURA, _R.NAO_APLICA, False, False, _C.PREPARACAO_INTERNA,
        "nenhum — o diff explicitamente exige um caminho de confirmação real que P04 ainda não implementa",
        nota="calcula diff contra uma versão base; não persiste nada",
    ),
}

del _L, _R, _C


def get_inventory_entry(tool_name: str) -> ToolInventoryEntry | None:
    return _INVENTORY.get(tool_name)


def list_inventory() -> dict[str, ToolInventoryEntry]:
    return dict(_INVENTORY)
