"""Sinal de ATIVIDADE OPERACIONAL do usuario a partir das chamadas de tool do
canal MCP.

Ate a sub-entrega que introduziu `ai_profile.atividade_operacional`, esse
sinal caia direto em `ai_profile.historico_deduzido` — o MESMO campo que
`askCopilotoHermes` alimenta com o texto literal do prompt do usuario
(`main.py::_save_user_profile_signal`). Isso misturava declaracao humana ("o
usuario disse que prefere X") com atividade de rotina ("o agente buscou X a
pedido do usuario"), e a segunda e muito mais frequente: consulta de rotina
afogava declaracao real de preferencia no mesmo historico que volta como
contexto de "perfil do usuario" (achado A07, plano-hermes-autonomo-2026-09-06,
pacote P06 passo 3).

Este modulo grava em `ai_profile.atividade_operacional`
(`salvar_atividade_operacional`, abaixo), trilha separada de
`historico_deduzido`: continua disponivel como contexto para o resource
`hermes://voice-context` (`copilot_context.py::_format_user_profile`), mas
nunca rotulada como preferencia. Nao ha um "prompt do usuario" numa chamada de
tool, mas os argumentos carregam a intencao (o que ele mandou buscar, o titulo
do que mandou criar), e e disso que a frase e derivada.

`salvar_atividade_operacional` vive neste modulo (e nao em main.py, ao lado de
`_save_user_profile_signal`) por limite operacional do pipeline de escrita no
repositorio nesta sub-entrega: functions/main.py tem ~729.000 caracteres,
acima do teto de 200.000 caracteres por escrita de `argos_escrever_arquivo_repositorio`
(escrita e sempre do arquivo inteiro, nao e patch) -- nao da para reescreve-lo
nesta rotina. Le `main._iso_now_utc` por import tardio dentro da funcao (mesmo
principio ja usado por tools/telegram_extended.py:552, que importa `main` como
`main_mod` e chama `main_mod._iso_now_utc()` tambem de forma tardia), sem
precisar editar main.py.

Deliberadamente conservador: so tools cujo argumento e, de fato, algo que o
usuario disse. Chamada exploratoria do agente (calculadora, leitura de contexto,
consulta de job) nao vira sinal — inflar a trilha com ruido e pior do que
deixa-la curta, porque ela entra no prompt de toda conversa seguinte.
"""

from __future__ import annotations

import threading

# tool -> (argumento que carrega a intencao, molde da frase)
_INTENCAO_POR_TOOL: dict[str, tuple[str, str]] = {
    "consultar_historico_acoes": ("query", "buscou acoes: {}"),
    "buscar_arquivos_acervo": ("query", "buscou no acervo: {}"),
    "buscar_conversas_whatsapp": ("query", "buscou no WhatsApp: {}"),
    "buscar_contato": ("termo", "buscou contato: {}"),
    "pesquisar_internet": ("query", "pesquisou na internet: {}"),
    "ler_pagina_web": ("url", "mandou ler a pagina: {}"),
    "criar_acao_no_sistema": ("titulo", "criou acao: {}"),
    "registrar_no_diario": ("nota", "registrou no diario: {}"),
    "salvar_memoria_global": ("fato", "salvou memoria: {}"),
    "salvar_pop_global": ("titulo", "salvou POP: {}"),
    "gerar_relatorio": ("titulo", "pediu relatorio: {}"),
    "gerar_imagem": ("prompt", "pediu imagem: {}"),
    "criar_objetivo_estrategico": ("objetivoMacro", "criou objetivo estrategico: {}"),
    "consultar_processo_sipac": ("numero_processo", "consultou processo SIPAC {}"),
    "ler_documento_na_integra": ("query_especifica", "perguntou a um documento: {}"),
    "buscar_e_analisar_email": ("query", "buscou e-mails: {}"),
    "schedule_whatsapp_message": ("message", "mandou WhatsApp: {}"),
}

# Tools sem argumento de texto livre, mas cuja simples chamada ja diz o assunto.
_INTENCAO_SEM_ARGUMENTO: dict[str, str] = {
    "consultar_agenda": "consultou a agenda",
    "consultar_financas_v2": "consultou o financeiro",
    "consultar_saude": "consultou os dados de saude",
    "consultar_dados_cadastrais": "consultou os dados cadastrais",
    "obter_portal_financeiro_publico": "consultou o portal financeiro publico",
    "obter_portal_compras_publico": "consultou o portal de compras publico",
}

_MAX_CHARS = 180


def sinal_de_intencao(tool: str, arguments: dict | None) -> str | None:
    """Frase curta descrevendo o que o usuario pediu, ou None se a tool nao diz nada."""
    arguments = arguments or {}

    par = _INTENCAO_POR_TOOL.get(tool)
    if par:
        campo, molde = par
        valor = str(arguments.get(campo) or "").strip()
        if not valor:
            return None
        valor = " ".join(valor.split())
        if len(valor) > _MAX_CHARS:
            valor = valor[: _MAX_CHARS - 3] + "..."
        return molde.format(valor)

    return _INTENCAO_SEM_ARGUMENTO.get(tool)


def salvar_atividade_operacional(db, uid: str | None, activity_text: str, task_id: str | None, system_id: str | None) -> None:
    """Grava sinal de ATIVIDADE OPERACIONAL (uso de ferramenta/consulta de
    rotina via canal MCP) em trilha própria, `ai_profile.atividade_operacional`
    -- separada de `historico_deduzido`, reservado ao que o usuário de fato
    declarou (achado A07 / plano-hermes-autonomo-2026-09-06.md, pacote P06,
    passo 3: "parar de transformar consultas de rotina em preferência
    pessoal; registrar atividade operacional em trilha própria").

    Mesmo formato de entrada de `main.py::_save_user_profile_signal`
    (texto/taskId/systemId/at, deduplicado contra a última entrada, mantidas
    as 10 mais recentes), mas em campo e função PRÓPRIOS -- nunca escreve
    nem lê `historico_deduzido`, `last_task_id` ou `last_system_id` (campos
    da trilha humana; ver docstring do módulo para o motivo de viver aqui
    em vez de main.py).

    A escrita usa `update()` com field paths pontilhados
    (`ai_profile.atividade_operacional`, `ai_profile.updated_at`) em vez de
    reler o mapa `ai_profile` inteiro e regravá-lo com `set(merge=True)`:
    como `_save_user_profile_signal` (main.py) grava em paralelo, em thread
    própria e sem transação, um `set({"ai_profile": {...mapa completo...}},
    merge=True)` feito a partir de uma leitura obsoleta sobrescreveria de
    volta QUALQUER campo que o outro escritor tenha incluído no seu próprio
    mapa completo (o merge do Firestore é por field-path explicitado no
    payload, não "só os campos que mudaram de fato") -- as duas trilhas
    voltariam a se apagar mutuamente sob concorrência, exatamente o defeito
    que esta sub-entrega existe para fechar, só que na forma de perda de
    dado em vez de contaminação semântica (achado de revisão adversarial
    desta sub-entrega). Usar field paths dedicados faz esta função tocar
    *apenas* os dois campos que lhe pertencem, sem depender do estado lido
    de `historico_deduzido`/`last_task_id`/`last_system_id` para nada --
    então mesmo que a leitura esteja obsoleta quanto a esses campos, a
    escrita não os repete nem os sobrescreve.

    Isso fecha o risco NESTE sentido (esta função nunca mais pode apagar o
    que a trilha humana gravou). O sentido inverso -- `main.py` ainda grava
    o mapa `ai_profile` inteiro a partir de uma leitura própria, podendo
    teoricamente sobrescrever `atividade_operacional` com um valor obsoleto
    -- continua aberto nesta sub-entrega: `main.py` tem ~729.000 caracteres,
    acima do teto de 200.000 caracteres de `argos_escrever_arquivo_repositorio`,
    então não há como convertê-lo para o mesmo padrão de field path nesta
    rotina (mesma limitação operacional descrita no docstring do módulo).
    Risco residual, unidirecional, registrado como LIMITAÇÃO CONHECIDA para
    uma sub-entrega futura que viabilize editar main.py em partes (ex.: um
    mecanismo de patch, ou separação do arquivo).
    """
    if not uid or not activity_text:
        return

    from firebase_admin import firestore

    from main import _iso_now_utc

    profile_ref = db.collection("usuarios").document(uid)
    doc = profile_ref.get()
    ai_profile = dict((doc.to_dict() or {}).get("ai_profile") or {})
    atividade = list(ai_profile.get("atividade_operacional") or [])
    snippet = activity_text.strip().replace("\n", " ")
    if len(snippet) > 180:
        snippet = snippet[:177] + "..."
    entry = {
        "texto": snippet,
        "taskId": task_id or None,
        "systemId": system_id or None,
        "at": _iso_now_utc(),
    }
    if not atividade or atividade[-1].get("texto") != entry["texto"]:
        atividade.append(entry)
    nova_lista = atividade[-10:]

    if doc.exists:
        # update() com field paths: toca só estes dois campos, nunca
        # historico_deduzido/last_task_id/last_system_id (ver docstring).
        profile_ref.update({
            "ai_profile.atividade_operacional": nova_lista,
            "ai_profile.updated_at": firestore.SERVER_TIMESTAMP,
        })
    else:
        # Documento ainda nao existe: nao ha concorrencia possivel com um
        # escritor que tambem dependeria do mesmo documento inexistente, e
        # update() falharia com NOT_FOUND -- set(merge=True) e seguro aqui.
        profile_ref.set({
            "ai_profile": {
                "atividade_operacional": nova_lista,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
        }, merge=True)


def registrar(uid: str | None, tool: str, arguments: dict | None, task_id: str | None = None) -> None:
    """Grava o sinal no perfil, sem bloquear a resposta da tool.

    Em thread e best-effort pelo mesmo motivo do audit log: perfil e telemetria,
    nao podem transformar uma falha de escrita em falha da chamada.
    """
    if not uid:
        return

    # Fora da nuvem (testes, scripts) nao grava: o perfil de producao recebia
    # sinais falsos quando um teste rodava sozinho, sem o bloqueio de credencial.
    from auditoria_mcp import em_producao

    if not em_producao():
        return

    texto = sinal_de_intencao(tool, arguments)
    if not texto:
        return

    def _gravar():
        try:
            from firebase_admin import firestore

            salvar_atividade_operacional(firestore.client(), uid, texto, task_id, None)
        except Exception as exc:  # noqa: BLE001
            print(f"[mcp_signals] Falha ao registrar sinal (tool={tool}): {exc}")

    threading.Thread(target=_gravar, daemon=True).start()
