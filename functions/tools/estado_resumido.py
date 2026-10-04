"""Versão resumida da resposta do `obter_estado_atual` (MCP).

Medido em 04/10/2026: a ferramenta respondia por 31% de todo o texto que o MCP
devolvia ao Claude (63 chamadas em 14 dias, ~73 mil caracteres cada), e é a
primeira chamada de toda conversa — então esse texto é relido a cada turno.
O peso estava em dois lugares: em "hoje", cada ação trazia a lista INTEIRA de
etapas esperando terceiros e o texto completo da etapa do dia; e a fila de
atenção trazia evidências, chaves internas e datas de controle.

O resumo mantém a estrutura e encurta o conteúdo: até 2 etapas esperando por
ação, com o total; textos longos cortados; campos vazios, internos e
redundantes fora (a faixa já está no nome da lista; a lista de atrasadas vira
referência, porque cada atrasada já aparece inteira na sua faixa; o próximo
passo some quando é a própria etapa do dia). Os POPs sempre ativos ficam inteiros, porque são regras
que o Claude precisa seguir. `detalhe="completo"` devolve tudo como antes, e
`obter_acao` abre uma ação inteira.
"""

from __future__ import annotations

TEXTO_ETAPA = 160
TEXTO_ESPERA = 100
TEXTO_ATENCAO = 200
TEXTO_DIARIO = 600
MAX_ESPERAS = 2
_CAMPOS_INTERNOS_ATENCAO = ("evidencia", "chave_dedupe", "criado_em", "atualizado_em", "resolvido_em", "desfecho",
                            "estado")
_OBSERVACAO = ("Resposta resumida: até 2 etapas esperando terceiros por ação (o total vem em "
               "aguardando_terceiro_total), textos longos cortados com '…' e campos vazios omitidos "
               "(campo ausente = vazio/falso). Para o conteúdo inteiro, "
               "obter_acao(task_id) ou obter_estado_atual(detalhe='completo').")


def _cortar(texto, limite: int):
    if not isinstance(texto, str) or len(texto) <= limite:
        return texto
    return texto[: limite - 1].rstrip() + "…"


def _sem_vazios(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, False, "", [], {})}


def _etapa(etapa, limite: int = TEXTO_ETAPA):
    if not isinstance(etapa, dict):
        return _cortar(etapa, limite)
    curta = _sem_vazios({k: v for k, v in etapa.items() if k != "degradation_count"})
    for campo in ("texto", "text"):
        if campo in curta:
            curta[campo] = _cortar(curta[campo], limite)
    return curta


def _acao(item: dict) -> dict:
    if not isinstance(item, dict):
        return item
    curta = dict(item)
    if "subtarefa_do_dia" in curta:
        curta["subtarefa_do_dia"] = _etapa(curta["subtarefa_do_dia"])
    if "proximo_passo" in curta:
        curta["proximo_passo"] = _etapa(curta["proximo_passo"])
    passo, do_dia = curta.get("proximo_passo"), curta.get("subtarefa_do_dia")
    if isinstance(passo, dict) and isinstance(do_dia, dict) and passo.get("id") and passo.get("id") == do_dia.get("id"):
        curta.pop("proximo_passo")
    esperas = curta.get("aguardando_terceiro")
    if isinstance(esperas, list):
        if esperas:
            curta["aguardando_terceiro_total"] = len(esperas)
        curta["aguardando_terceiro"] = [_etapa(e, TEXTO_ESPERA) for e in esperas[:MAX_ESPERAS]]
    # A lista de faixa em que a ação está (avanco, continuo...) já diz a faixa.
    curta.pop("execution_lane", None)
    if curta.get("degradation_count") == 0:
        curta.pop("degradation_count")
    return _sem_vazios(curta)


def _lista_de_acoes(valor):
    return [_acao(i) for i in valor] if isinstance(valor, list) else valor


def resumir_estado(estado: dict) -> dict:
    """Cópia resumida; não altera o dicionário recebido."""
    if not isinstance(estado, dict):
        return estado
    resumido = dict(estado)

    hoje = resumido.get("hoje")
    if isinstance(hoje, dict):
        resumido["hoje"] = {k: _lista_de_acoes(v) for k, v in hoje.items() if k != "atrasadas"}
        if "atrasadas" in hoje:
            # Toda ação atrasada já está, inteira, na lista da faixa dela (com
            # atrasada=true); aqui basta a referência.
            resumido["hoje"]["atrasadas"] = [
                _sem_vazios({c: a.get(c) for c in ("id", "titulo", "data_limite")}) if isinstance(a, dict) else a
                for a in (hoje["atrasadas"] or [])]
    elif isinstance(hoje, list):
        resumido["hoje"] = _lista_de_acoes(hoje)
    if "foco" in resumido:
        resumido["foco"] = _lista_de_acoes(resumido["foco"])

    fila = resumido.get("fila_atencao")
    if isinstance(fila, list):
        itens = []
        for item in fila:
            if not isinstance(item, dict):
                itens.append(item)
                continue
            curto = _sem_vazios({k: v for k, v in item.items() if k not in _CAMPOS_INTERNOS_ATENCAO})
            for campo in ("resumo", "sugestao"):
                if campo in curto:
                    curto[campo] = _cortar(curto[campo], TEXTO_ATENCAO)
            itens.append(curto)
        resumido["fila_atencao"] = itens

    ontem = resumido.get("ontem")
    if isinstance(ontem, dict) and isinstance(ontem.get("diario"), dict):
        diario = dict(ontem["diario"])
        diario["texto"] = _cortar(diario.get("texto"), TEXTO_DIARIO)
        resumido["ontem"] = {**ontem, "diario": diario}

    resumido["detalhe"] = "auto"
    resumido["observacao"] = _OBSERVACAO
    return resumido
