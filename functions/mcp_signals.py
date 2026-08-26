"""Sinal de intencao do usuario a partir das chamadas de tool do canal MCP.

`ai_profile.historico_deduzido` guarda as ultimas coisas que o usuario pediu, e
volta como contexto para o copiloto e para o resource `hermes://voice-context`.
Quem alimentava esse campo era `askCopilotoHermes`, numa thread, com o texto do
prompt (`main.py::_save_user_profile_signal`).

Com a interacao migrando para clientes MCP, aquele caminho para de ser exercido
e o perfil congela — sem erro, sem log, so envelhecendo. Este modulo recupera o
sinal do outro lado: nao ha um "prompt do usuario" numa chamada de tool, mas os
argumentos carregam a intencao (o que ele mandou buscar, o titulo do que mandou
criar), e e disso que a frase e derivada.

Deliberadamente conservador: so tools cujo argumento e, de fato, algo que o
usuario disse. Chamada exploratoria do agente (calculadora, leitura de contexto,
consulta de job) nao vira sinal — inflar o historico com ruido e pior do que
deixa-lo curto, porque ele entra no prompt de toda conversa seguinte.
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


def registrar(uid: str | None, tool: str, arguments: dict | None, task_id: str | None = None) -> None:
    """Grava o sinal no perfil, sem bloquear a resposta da tool.

    Em thread e best-effort pelo mesmo motivo do audit log: perfil e telemetria,
    nao podem transformar uma falha de escrita em falha da chamada.
    """
    if not uid:
        return

    texto = sinal_de_intencao(tool, arguments)
    if not texto:
        return

    def _gravar():
        try:
            from firebase_admin import firestore

            from main import _save_user_profile_signal

            _save_user_profile_signal(firestore.client(), uid, texto, task_id, None)
        except Exception as exc:  # noqa: BLE001
            print(f"[mcp_signals] Falha ao registrar sinal (tool={tool}): {exc}")

    threading.Thread(target=_gravar, daemon=True).start()
