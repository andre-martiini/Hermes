"""Conserta, antes de executar, os enganos de argumento que o Claude repete no MCP.

Medido no `mcp_audit_log` de 05 a 14/10/2026: o ID da ação chegou como `id`,
`acao_id` ou `tarefa_id` em `obter_acao` e `registrar_no_diario` (10 erros), e
`pessoa_id` chegou como o texto "null" (2). Só move um apelido quando a tool
declara o nome certo e não declara o apelido, para nunca mudar o sentido de um
argumento que a tool usa de verdade.
"""

_ALVOS_ID_ACAO = ("task_id", "task_id_alvo")
_APELIDOS_ID_ACAO = ("id", "acao_id", "tarefa_id", "taskId", "acaoId", "id_acao")
_TEXTOS_NULOS = {"null", "none", "undefined"}


def _e_id(chave: str) -> bool:
    return chave == "id" or chave.endswith("_id")


def normalizar(argumentos: dict, propriedades: dict) -> tuple[dict, list[str]]:
    """Devolve os argumentos consertados e a lista do que foi ajustado."""
    saida = dict(argumentos)
    ajustes: list[str] = []

    for chave in list(saida):
        valor = saida[chave]
        if _e_id(chave) and isinstance(valor, str) and valor.strip().lower() in _TEXTOS_NULOS:
            del saida[chave]
            ajustes.append(f"{chave}='{valor}' removido")

    alvo = next((a for a in _ALVOS_ID_ACAO if a in propriedades), None)
    if alvo and not saida.get(alvo):
        for apelido in _APELIDOS_ID_ACAO:
            if apelido in propriedades or not saida.get(apelido):
                continue
            saida[alvo] = saida.pop(apelido)
            ajustes.append(f"{apelido}->{alvo}")
            break

    return saida, ajustes
