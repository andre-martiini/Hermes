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


@dataclass(frozen=True)
class ToolInventoryEntry:
    """Uma linha do inventário — ver docstring do módulo para os 7 campos
    pedidos pelo passo 1 do P03. `rede_servico`/`dados_sensiveis_categoria`
    são o "qual" complementar dos dois campos booleanos. `dominio_rede` é o
    "qual" complementar de `necessidade_de_rede`, ver `DominioRede`."""

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


_L = LeituraEscrita
_R = Reversibilidade
_C = ClasseEfeito

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
    ),
    "agendar_lembrete_acao": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — não confirma que o lembrete foi de fato entregue no horário",
    ),
    "salvar_memoria_global": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.ESCRITA, _R.REVERSIVEL, True, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum determinístico — o próprio filtro de retenção é um LLM",
        rede_servico="Gemini (classificador de retenção + embedding)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="fato pessoal do usuário ou de terceiro, sem filtro de categoria",
        nota="reversível via resolver_conflito_memoria — mas só na prática quando uma gravação futura for "
        "detectada como similar o bastante para abrir um conflito; não há tool neste catálogo para buscar "
        "e corrigir uma memória específica sob demanda (achado da revisão adversarial desta sub-entrega)",
    ),
    "registrar_correcao_procedimento": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum na própria tool", nota="reversível via resolver_conflito_procedimento",
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
    ),
    "resolver_conflito_memoria": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.ESCRITA, _R.REVERSIVEL, True, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum", rede_servico="Gemini (embedding), só quando decisão=substituir_pelo_novo",
        dominio_rede=DominioRede.FECHADO,
    ),
    "atualizar_personalidade": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — grava direto sem revisão",
    ),
    "resolver_conflito_procedimento": ToolInventoryEntry(
        "memoria_e_procedimentos", _L.LEITURA_E_ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "a exigência de confirmar_contrato=True na chamada é o único verificador pré-escrita",
        nota="sem confirmar_contrato é só preview textual (leitura); versão antiga vira backup, não é apagada",
    ),
    "editar_plano_acao": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "salvaguardas pré-escrita (plano degenerado, plano esvaziado) bloqueiam gravações claramente erradas",
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
        nota="classificação PREPARACAO_INTERNA discutível: ao contrário de preparar_edicao_acao (que é "
        "LEITURA/NAO_APLICA, sem persistir nada até confirmar_edicao_acao), esta tool já persiste um "
        "documento final em relatorios/{id} sem passo de confirmação — mais perto de ESCRITA_INTERNA_"
        "REVERSIVEL. Mantido PREPARACAO_INTERNA por ser conteúdo interno de baixo risco sem contato com "
        "terceiro, mas é ambiguidade genuína a revisitar quando classe_efeito for religada à decisão de "
        "política de fato (achado da revisão adversarial desta sub-entrega).",
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
        nota="sem tool de exclusão/correção neste catálogo; a leitura já trata status==deleted, indício de que esse caminho existe fora do MCP",
    ),
    "obter_portal_compras_publico": ToolInventoryEntry(
        "compras", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum",
    ),
    "mutar_portal_compras_publico": ToolInventoryEntry(
        "compras", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL, "nenhum",
        nota="duplica lógica de escrita com mutar_lista_compras sobre a mesma coleção shopping_items — candidato a consolidação",
    ),
    "mutar_lista_compras": ToolInventoryEntry(
        "compras", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "consultar_lista_compras foi desenhada para reconferir o efeito ('fecha o ciclo', docstring do módulo)",
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
        nota="irreversível só para a decisão 'nunca' (permanente por desenho); 'aceitar'/'adiar' são revisáveis",
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
        "interna' sugeriria, por isso COORDENACAO_LIMITADA e não ESCRITA_INTERNA_REVERSIVEL.",
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
        nota="sempre cria doc novo; nenhuma tool deste catálogo edita/exclui um lançamento",
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
        nota="irreversível só para tipos promovidos (liberam sozinhos ao fim da janela de cancelamento, sem "
        "nova confirmação); outros tipos são revisáveis via descartar_rascunho_whatsapp. Classificado "
        "IRREVERSIVEL ao nível da tool (mesma convenção de decidir_elevacao/decidir_promocao_autonomia para "
        "a mesma forma de nuance -- 'irreversível só para um subconjunto') -- achado da revisão adversarial "
        "de P03 sub-entrega 6/N: a classificação original (REVERSIVEL) divergia dessa convenção e produzia "
        "destructiveHint=False enganoso em tools/registry.py::mcp_annotations para o caso de risco real "
        "(tipo promovido).",
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
        "classificação real de cada chamada é a da tool delegada.",
    ),
    "pausar_conversa": ToolInventoryEntry(
        "whatsapp", _L.ESCRITA, _R.IRREVERSIVEL, False, True, _C.COMPROMISSO_TERCEIROS, "nenhum",
        dados_sensiveis_categoria="conversa com terceiro",
        nota="classificação COMPROMISSO_TERCEIROS já existe em autonomy/policy.py::CLASSE_EFEITO_PISO",
    ),
    "criar_rascunho_email": ToolInventoryEntry(
        "email", _L.LEITURA_E_ESCRITA, _R.IRREVERSIVEL, True, True, _C.COMPROMISSO_TERCEIROS,
        "devolve draft_id + link — verificador mínimo existe, raro no inventário",
        rede_servico="Gmail API (drafts.create, threads.get, getProfile)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="destinatário e conteúdo de terceiro",
        nota="classificação COMPROMISSO_TERCEIROS já existe em autonomy/policy.py::CLASSE_EFEITO_PISO, apesar "
        "da descrição do catálogo dizer 'nunca envia'; nenhuma tool exclui um rascunho Gmail já criado",
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
        nota="sem tool de edição/remoção de uma interação já registrada",
    ),
    "consultar_saude": ToolInventoryEntry(
        "saude", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA, "nenhum necessário",
        dados_sensiveis_categoria="saúde",
    ),
    "registrar_saude": ToolInventoryEntry(
        "saude", _L.ESCRITA, _R.REVERSIVEL, False, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum automático, mas upsert idempotente por dia+campo permite correção via nova chamada",
        dados_sensiveis_categoria="saúde",
    ),
    "consultar_dados_cadastrais": ToolInventoryEntry(
        "dados_cadastrais", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA,
        "nenhum necessário",
        dados_sensiveis_categoria="documentos, família, carreira, dados bancários, plano de saúde",
    ),
    "registrar_no_diario": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.IRREVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL, "nenhum",
        nota="o plano (seção 5.1) usa 'diário factual' como exemplo textual de escrita reversível, mas "
        "nenhuma tool deste catálogo remove uma entrada já escrita (ArrayUnion) — reversibilidade é "
        "conceitual, não uma capacidade real hoje",
    ),
    "gerar_imagem": ToolInventoryEntry(
        "utilitario", _L.ESCRITA, _R.IRREVERSIVEL, True, False, _C.PREPARACAO_INTERNA,
        "nenhum — não confere se a imagem corresponde ao prompt nem se a URL segue acessível",
        rede_servico="Gemini (geração) + Google Cloud Storage (upload)",
        dominio_rede=DominioRede.FECHADO,
        nota="upload permanente no bucket público; sem tool de exclusão",
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
    ),
    "editar_objetivo_estrategico": ToolInventoryEntry(
        "estrategico", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL, "nenhum",
    ),
    "gerenciar_item_estrategico": ToolInventoryEntry(
        "estrategico", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "transação Firestore evita perda de escrita concorrente; não verifica o resultado semanticamente",
    ),
    "excluir_objetivo_estrategico": ToolInventoryEntry(
        "estrategico", _L.ESCRITA, _R.IRREVERSIVEL, False, False,
        _C.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
        "nenhum",
        nota="delete() definitivo, sem soft-delete nem tool de restauração — 'exclusão definitiva' é exemplo "
        "textual desta classe na matriz do plano (seção 5.1). ACHADO: apesar disso, esta tool não está no "
        "piso FLOOR_CONFIRMACAO_OBRIGATORIA do MCP — hoje uma sessão MCP pode excluir um objetivo estratégico "
        "numa única chamada, sem segunda confirmação estrutural.",
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
        nota="sem caminho de volta -- não há tool de undispensar; dispensa vale só para o "
             "trecho/snippet atual (fingerprint no item_id), não para a conversa/thread inteira",
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
        nota="reversível via remover_anexo",
    ),
    "preparar_upload": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.REVERSIVEL, True, False, _C.PREPARACAO_INTERNA,
        "conferência real (tamanho/sha256) acontece na chamada seguinte, dentro de anexar_arquivo",
        rede_servico="Google Cloud IAM signBlob (URL assinada)",
        dominio_rede=DominioRede.FECHADO,
        nota="grava doc em uploads_pendentes apesar do nome sugerir só preparo em memória; token de uso "
        "único, expira em 15 min, nada é aplicado a nenhuma tarefa por esta chamada",
    ),
    "remover_anexo": ToolInventoryEntry(
        "acoes_tarefas", _L.ESCRITA, _R.IRREVERSIVEL, True, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — devolve só um booleano de lixeira, sem confirmar que era o anexo certo",
        rede_servico="Google Drive (mover para lixeira)",
        dominio_rede=DominioRede.FECHADO,
        dados_sensiveis_categoria="documento anexado",
        nota="sem tool para restaurar o vínculo exato; arquivo vai para a lixeira do Drive (recuperável por "
        "30 dias fora do Hermes)",
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
        nota="escrita é efeito colateral condicional e idempotente (dedupe por tag, só quando a decisão "
        "externa mudou), não o propósito da tool — por isso nao_aplica em vez de reversivel/irreversivel",
    ),
    "registrar_aporte_investimento": ToolInventoryEntry(
        "investimentos", _L.ESCRITA, _R.IRREVERSIVEL, True, True,
        _C.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
        "nenhum automático — timeout/5xx marca escrita_ambigua; instrução é reconsultar via "
        "consultar_investimentos, nunca repetir",
        rede_servico="POST ao serviço externo decisao-investimentos", dados_sensiveis_categoria="financeiro",
        nota="classificação canônica em autonomy/policy.py::CLASSE_EFEITO_PISO; soma ao aporte total externo, "
        "sem endpoint de estorno",
    ),
    "registrar_execucao_investimento": ToolInventoryEntry(
        "investimentos", _L.ESCRITA, _R.REVERSIVEL, True, True,
        _C.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
        "mesmo padrão do aporte — reconsulta manual via consultar_investimentos é o único caminho",
        rede_servico="POST ao serviço externo decisao-investimentos", dados_sensiveis_categoria="financeiro",
        nota="classificação canônica em autonomy/policy.py::CLASSE_EFEITO_PISO; declarativo (repetir não "
        "acumula posição), mas grava uma 2ª linha no log de movimentos, não apagável",
    ),
    "obter_fila_atencao": ToolInventoryEntry(
        "atencao_fila", _L.LEITURA, _R.NAO_APLICA, False, True, _C.OBSERVACAO_AUTORIZADA, "nenhum",
        dados_sensiveis_categoria="itens podem ter origem em WhatsApp de terceiro",
    ),
    "resolver_item_atencao": ToolInventoryEntry(
        "atencao_fila", _L.ESCRITA, _R.IRREVERSIVEL, False, True, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — desfecho é texto livre do chamador, sem validação de conteúdo",
        dados_sensiveis_categoria="pode referenciar contato/conversa de terceiro",
        nota="sem caminho de volta a 'aberto' por esta tool",
    ),
    "consultar_pedidos_agente": ToolInventoryEntry(
        "autonomia_pedidos_agente", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum",
    ),
    "concluir_pedido_agente": ToolInventoryEntry(
        "autonomia_pedidos_agente", _L.ESCRITA, _R.IRREVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "transação Firestore impede duas conclusões concorrentes; não confere se resultado/erro é "
        "factualmente correto",
        nota="transição terminal, sem tool de reabertura",
    ),
    "registrar_execucao_agente": ToolInventoryEntry(
        "autonomia_pedidos_agente", _L.ESCRITA, _R.IRREVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — grava o que o chamador declarar, sem contraprova", nota="log append-only",
    ),
    "consultar_execucoes_agente": ToolInventoryEntry(
        "autonomia_pedidos_agente", _L.LEITURA, _R.NAO_APLICA, False, False, _C.OBSERVACAO_AUTORIZADA, "nenhum",
    ),
    "preparar_contato_prioritario_secretario": ToolInventoryEntry(
        "whatsapp_secretario", _L.ESCRITA, _R.REVERSIVEL, False, True, _C.COORDENACAO_LIMITADA,
        "nenhum — resolução de contato pode ambiguar e nada revalida depois",
        dados_sensiveis_categoria="nome/telefone/assunto de terceiro",
        nota="grava direto no Firestore apesar do nome 'preparar_'; não há segunda chamada de confirmação "
        "como nas demais preparar_*; reversível via cancelar_contato_prioritario_secretario",
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
    ),
    "ativar_modo_secretario": ToolInventoryEntry(
        "whatsapp_secretario", _L.ESCRITA, _R.REVERSIVEL, False, True, _C.COORDENACAO_LIMITADA,
        "nenhum — reconferência via consultar_status_modo_secretario é opcional",
        dados_sensiveis_categoria="allowlist de contatos terceiros",
        nota="só grava system/settings — nenhuma chamada à infra de envio do WhatsApp acontece nesta tool; "
        "reversível via desativar_modo_secretario",
    ),
    "desativar_modo_secretario": ToolInventoryEntry(
        "whatsapp_secretario", _L.ESCRITA, _R.REVERSIVEL, False, False, _C.ESCRITA_INTERNA_REVERSIVEL,
        "nenhum — desligar é sempre seguro/imediato por design",
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
