"""Perfil das metas: o esperado de hoje e o estado de cada indicador.

Relançamento de 30/10/2026: três metas com ciclo de 3 meses (02/11/2026 a
30/01/2027) e marcos em 30/11, 30/12 e 30/01. A meta passa a ter `ciclo`,
`linhaBase` e `indicadores`, e cada marco pode ter `dataAlvo` e `esperado`
(mapa chave do indicador -> número). Daqui sai, para cada indicador, quanto se
esperava que estivesse HOJE e se ele está no perfil, atrasado ou adiantado.

Módulo puro: sem Firestore. **Anda junto com `src/utils/perfilEstrategia.ts`**:
a mesma regra vale na tela e no MCP, e os testes dos dois lados leem o MESMO
arquivo de fixture (`src/utils/perfilEstrategia.fixture.json`). Se um lado mudar
sem o outro, um dos dois testes quebra.

Por que não reaproveita `healthAnalytics.ts`: lá a trajetória é regressão sobre
as pesagens e projeção da data de chegada; aqui é o contrário, o valor esperado
numa data a partir de marcos datados. E `HealthSettings.marcos` são pesos sem
data. Não há regra em comum para não duplicar.

Contas em inteiros (centésimos da unidade; para dinheiro, centavos), com o
arredondamento meio-para-cima escrito à mão, igual nos dois lados: float e o
`round` de cada linguagem dariam números diferentes na tela e no MCP.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from bolso_aquisicoes import centavos, numero

SENTIDOS = ("menor_melhor", "maior_melhor")
FONTES = ("peso", "cintura", "guardado_acumulado", "manual")
UNIDADES_DINHEIRO = ("r$", "brl", "reais")
# Ordem de gravidade: o estado da meta é o pior dos seus indicadores e marcos.
GRAVIDADE = {"adiantado": 0, "no_perfil": 1, "sem_dado": 2, "atrasado": 3}

_DIA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def dia(valor) -> date | None:
    """YYYY-MM-DD (com ou sem hora depois) lido pelo texto; inválido é None."""
    achado = _DIA.match(str(valor or ""))
    if not achado:
        return None
    try:
        return date(int(achado.group(1)), int(achado.group(2)), int(achado.group(3)))
    except ValueError:
        return None


def hoje_brasilia(agora: datetime | None = None) -> str:
    """A data de hoje em Brasília. Às 22h de Brasília já é o dia seguinte em UTC."""
    from zoneinfo import ZoneInfo

    instante = agora or datetime.now(ZoneInfo("UTC"))
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=ZoneInfo("UTC"))
    return instante.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")


def id_legado(tipo: str, indice: int, descricao: str) -> str:
    """Id estável para marco ou indicador legado gravado como texto puro.

    Antes, cada leitura sorteava um id novo, e quem lia (o Claude, pelo MCP) não
    conseguia editar nem remover o item: o id lido já não existia na chamada
    seguinte. Hash FNV-1a de 32 bits da posição e do texto: o mesmo item tem o
    mesmo id em toda leitura e é esse id que fica gravado na primeira escrita.
    """
    h = 0x811C9DC5
    for byte in f"{indice}|{descricao}".encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{tipo}-legado-{h:08x}"


def _div_arred(n: int, d: int) -> int:
    """n / d arredondado meio-para-longe-do-zero, em inteiros (d > 0)."""
    sinal = -1 if n < 0 else 1
    return sinal * ((abs(n) * 2 + d) // (2 * d))


_MAX_CENTESIMOS = 9007199254740991  # o mesmo teto de bolso_aquisicoes.centavos


def _centesimos(valor) -> int | None:
    """Valor em centésimos; ilegível ou fora do teto é None (sem dado), nunca zero.

    `centavos()` devolve 0 acima do teto, o que aqui viraria "adiantado" num
    indicador menor_melhor; por isso o teto é conferido antes.
    """
    if valor is None or isinstance(valor, bool):
        return None
    n = numero(valor, None)
    if n is None or abs(n) * 100 > _MAX_CENTESIMOS:
        return None
    return centavos(valor)


def _hoje(hoje) -> date:
    d = dia(hoje)
    if d is None:
        raise ValueError(f"hoje deve ser YYYY-MM-DD, veio {hoje!r}.")
    return d


def _numerico(marco: dict, chaves: set) -> bool:
    """Marco com valor esperado para algum indicador da meta; o resto é qualitativo."""
    esperado = marco.get("esperado")
    return isinstance(esperado, dict) and any(k in chaves for k in esperado)


def e_dinheiro(indicador: dict) -> bool:
    return (str(indicador.get("unidade") or "").strip().lower() in UNIDADES_DINHEIRO
            or indicador.get("fonte") == "guardado_acumulado")


def _saida(valor: int | None, dinheiro: bool):
    """Dinheiro sai em centavos inteiros; o resto, na unidade, com duas casas."""
    if valor is None:
        return None
    return valor if dinheiro else valor / 100


def _marcos(meta: dict) -> list[dict]:
    marcos = [m for m in meta.get("marcos") or [] if isinstance(m, dict) and dia(m.get("dataAlvo"))]
    return sorted(marcos, key=lambda m: dia(m["dataAlvo"]))


def _valor_do_marco(marco: dict, chave: str) -> int | None:
    esperado = marco.get("esperado")
    return _centesimos(esperado.get(chave)) if isinstance(esperado, dict) else None


def pontos(meta: dict, indicador: dict) -> list[tuple[date, int]]:
    """Trajetória do indicador: linha de base, marcos com valor e, se faltar, o alvo final no fim do ciclo."""
    chave = indicador.get("chave")
    ciclo = meta.get("ciclo") if isinstance(meta.get("ciclo"), dict) else {}
    base = meta.get("linhaBase") if isinstance(meta.get("linhaBase"), dict) else {}
    por_dia: dict[date, int] = {}

    dia_base = dia(base.get("data")) or dia(ciclo.get("inicio"))
    valores_base = base.get("valores") if isinstance(base.get("valores"), dict) else {}
    valor_base = _centesimos(valores_base.get(chave))
    if valor_base is None:
        valor_base = _centesimos(indicador.get("inicial"))
    if dia_base and valor_base is not None:
        por_dia[dia_base] = valor_base

    for marco in _marcos(meta):
        valor = _valor_do_marco(marco, chave)
        if valor is not None:
            por_dia[dia(marco["dataAlvo"])] = valor  # marco na mesma data vence a linha de base

    fim, alvo = dia(ciclo.get("fim")), _centesimos(indicador.get("alvoFinal"))
    if fim and alvo is not None and (not por_dia or fim > max(por_dia)):
        por_dia[fim] = alvo
    return sorted(por_dia.items())


def esperado_em(meta: dict, indicador: dict, quando: str) -> int | None:
    """Esperado (em centésimos) numa data: interpolação linear entre os pontos.

    Antes do primeiro ponto vale o primeiro (o inicial); depois do último, o último.
    """
    trajetoria = pontos(meta, indicador)
    alvo = dia(quando)
    if not trajetoria or alvo is None:
        return None
    if alvo <= trajetoria[0][0]:
        return trajetoria[0][1]
    for (d0, v0), (d1, v1) in zip(trajetoria, trajetoria[1:]):
        if alvo <= d1:
            return v0 + _div_arred((v1 - v0) * (alvo - d0).days, (d1 - d0).days)
    return trajetoria[-1][1]


def _melhor_ou_igual(atual: int, referencia: int, sentido: str) -> bool:
    return atual >= referencia if sentido == "maior_melhor" else atual <= referencia


def avaliar_indicador(meta: dict, indicador: dict, atual, hoje: str) -> dict:
    chave = indicador.get("chave")
    sentido = indicador.get("sentido") if indicador.get("sentido") in SENTIDOS else "menor_melhor"
    dinheiro = e_dinheiro(indicador)
    hoje_d = _hoje(hoje)
    atual_c = _centesimos(atual)
    esperado = esperado_em(meta, indicador, hoje)
    proximo = next(((m, _valor_do_marco(m, chave)) for m in _marcos(meta)
                    if dia(m["dataAlvo"]) > hoje_d and _valor_do_marco(m, chave) is not None), None)

    if atual_c is None:
        estado = "sem_dado"  # ninguém mede: nunca devolver zero no lugar
    elif esperado is None:
        estado = None  # sem trajetória, não há perfil para comparar
    elif proximo and _melhor_ou_igual(atual_c, proximo[1], sentido):
        estado = "adiantado"
    elif _melhor_ou_igual(atual_c, esperado, sentido):
        estado = "no_perfil"
    else:
        estado = "atrasado"

    return {
        "chave": chave,
        "rotulo": indicador.get("rotulo") or chave,
        "unidade": indicador.get("unidade") or "",
        "fonte": indicador.get("fonte") if indicador.get("fonte") in FONTES else "manual",
        "sentido": sentido,
        "em_centavos": dinheiro,
        "atual": _saida(atual_c, dinheiro),
        "esperado_hoje": _saida(esperado, dinheiro),
        "proximo_marco": ({"data": dia(proximo[0]["dataAlvo"]).isoformat(),
                           "valor": _saida(proximo[1], dinheiro)} if proximo else None),
        "estado": estado,
    }


def avaliar_marco_sem_numero(marco: dict, hoje: str) -> dict:
    """Marco qualitativo: atrasado se a data passou e ele não foi concluído."""
    alvo = dia(marco.get("dataAlvo"))
    atrasado = bool(alvo and alvo < _hoje(hoje) and not marco.get("concluido"))
    return {"id": marco.get("id"), "descricao": marco.get("descricao") or "",
            "dataAlvo": alvo.isoformat() if alvo else None, "concluido": bool(marco.get("concluido")),
            "estado": "atrasado" if atrasado else "no_perfil"}


def avaliar_meta(meta: dict, atuais: dict, hoje: str) -> dict:
    """Perfil da meta: cada indicador, os marcos sem número, o próximo marco e o pior estado."""
    hoje_d = _hoje(hoje)
    validos = [ind for ind in meta.get("indicadores") or [] if isinstance(ind, dict) and ind.get("chave")]
    chaves = {ind["chave"] for ind in validos}
    indicadores = [avaliar_indicador(meta, ind, atuais.get(ind["chave"]), hoje) for ind in validos]
    sem_numero = [avaliar_marco_sem_numero(m, hoje) for m in _marcos(meta) if not _numerico(m, chaves)]
    estados = [i["estado"] for i in indicadores if i["estado"]] + [m["estado"] for m in sem_numero]
    proximo = next((m for m in _marcos(meta) if dia(m["dataAlvo"]) >= hoje_d and not m.get("concluido")), None)
    return {
        "estado": max(estados, key=GRAVIDADE.__getitem__) if estados else None,
        "indicadores": indicadores,
        "marcos_sem_numero": sem_numero,
        "proximo_marco": ({"data": dia(proximo["dataAlvo"]).isoformat(), "descricao": proximo.get("descricao") or ""}
                          if proximo else None),
    }
