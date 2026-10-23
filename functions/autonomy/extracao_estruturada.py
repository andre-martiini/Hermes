"""Extração estruturada de compromissos com evidências (P07 do plano de
autonomia, passo 2) -- parte pura, modo sombra.

Valida a saída (já decodificada) de um modelo de extração contra a mensagem
original. Sem I/O, sem chamada de modelo e sem wiring; `atencao_whatsapp` e
A06 não são alterados.

Princípio: o modelo só pode ACRESCENTAR detalhe, nunca afrouxar a cautela da
seleção barata. Cada compromisso exige evidência literal na mensagem; se o
classificador barato vê cancelamento, intenção vaga ou pergunta, o resultado
fica nessa classe com `incerta=True`, mesmo que o modelo diga `promessa`.
Saída malformada vira só ValueError (quem consome cai na seleção barata).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from autonomy.commitments import (
    CANCELAMENTO,
    CLASSES,
    INTENCAO_VAGA,
    PERGUNTA,
    PROMESSA,
    Classificacao,
    _normalizar,
    classificar_mensagem,
)

MAX_COMPROMISSOS = 5
MAX_MENSAGEM = 8000
_MAX_CAMPO = 200
_CAUTELA = (CANCELAMENTO, INTENCAO_VAGA, PERGUNTA)


@dataclass(frozen=True)
class CompromissoExtraido:
    classe: str
    objeto: str
    evidencia: str
    incerta: bool


_PREENCHEDORES = frozenset("\u115f\u1160\u3164\uffa0")


def _visivel(c: str) -> bool:
    return (c.isalpha() or c.isdecimal()) and c not in _PREENCHEDORES


def _texto(valor, campo: str) -> str:
    if type(valor) is not str:
        raise ValueError(f"{campo} deve ser texto")
    valor = valor.strip()
    if not valor or len(valor) > _MAX_CAMPO or sum(_visivel(c) for c in unicodedata.normalize("NFC", _normalizar(valor))) < 2:
        raise ValueError(f"{campo} vazio ou longo demais")
    return valor


def _cautelosa(c: Classificacao) -> bool:
    return c.classe in _CAUTELA or c.incerta


def _explica(frase_n: str, gatilho_n: str, outras: list) -> bool:
    """Outro item explica a frase cautelosa se a evidência dele cobre a maior
    parte dela, inclui o gatilho da ressalva e o objeto dele consta nela
    (evidência trivial como 'se' não)."""
    nucleo = frase_n.strip(" .!?;\n")
    return any(
        ev in frase_n and len(ev) * 10 >= len(nucleo) * 6 and obj in frase_n
        and (not gatilho_n or gatilho_n in ev)
        for ev, obj in outras
    )


def _base_do_item(mensagem: str, evidencia_n: str, outras: list, hoje, base_global: Classificacao) -> Classificacao:
    """Seleção barata na sentença que contém a evidência. A sentença só isola
    o item quando toda frase cautelosa vizinha é evidência de OUTRO compromisso
    extraído; ressalva órfã ("E. Mas só se der.") mantém a base da mensagem
    inteira. Evidência em zero ou várias sentenças: mensagem inteira."""
    sentencas = [t for t in re.split(r"(?<=[.!?;\n])\s+", mensagem) if t.strip()]
    achadas = [t for t in sentencas if evidencia_n in _normalizar(t)]
    if len(achadas) != 1:
        return base_global
    propria = achadas[0]
    vizinhas = 0
    for t in sentencas:
        if t is propria:
            continue
        c = classificar_mensagem(t, hoje)
        vizinhas += _cautelosa(c)
        if _cautelosa(c) and not _explica(_normalizar(t), _normalizar(c.evidencia).strip(" .!?;\n"), outras):
            return base_global
    if _cautelosa(base_global) and not vizinhas:
        return base_global  # a dúvida da mensagem não está numa frase vizinha identificável
    return classificar_mensagem(propria, hoje)


def validar_extracao(mensagem, saida, hoje=None) -> tuple[CompromissoExtraido, ...]:
    """`saida` = {"compromissos": [{classe, objeto, evidencia}, ...]}."""
    if type(mensagem) is not str or not mensagem.strip() or len(mensagem) > MAX_MENSAGEM:
        raise ValueError("mensagem inválida")
    if type(saida) is not dict or type(saida.get("compromissos")) is not list:
        raise ValueError("saída sem lista de compromissos")
    itens = saida["compromissos"]
    if len(itens) > MAX_COMPROMISSOS:
        raise ValueError("compromissos demais")
    base_global = classificar_mensagem(mensagem, hoje)
    texto_n = _normalizar(mensagem)
    vistos = {}
    pares_n = [
        (_normalizar(it.get("evidencia")), _normalizar(it.get("objeto")))
        if type(it) is dict and type(it.get("evidencia")) is str and type(it.get("objeto")) is str
        else ("", "")
        for it in itens
    ]
    resultado = []
    for pos, item in enumerate(itens):
        if type(item) is not dict:
            raise ValueError("compromisso malformado")
        classe = item.get("classe")
        if type(classe) is not str or classe not in CLASSES:
            raise ValueError("classe desconhecida")
        objeto = _texto(item.get("objeto"), "objeto")
        evidencia = _texto(item.get("evidencia"), "evidencia")
        if _normalizar(evidencia) not in texto_n:
            raise ValueError("evidência não consta na mensagem")
        incerta = False
        outras = [par for n, par in enumerate(pares_n) if n != pos and par[0] and par[1]]
        base = _base_do_item(mensagem, _normalizar(evidencia), outras, hoje, base_global)
        if classe == base.classe:
            incerta = base.incerta  # modelo concorda com a base: herda a dúvida dela
        elif base.classe in _CAUTELA:
            classe, incerta = base.classe, True  # modelo não afrouxa cautela em nenhuma classe
        elif classe == PROMESSA and base.incerta:
            classe, incerta = INTENCAO_VAGA, True
        else:
            incerta = True  # divergiu da seleção barata: modelo sozinho não firma nem apaga dúvida
        chave = (classe, _normalizar(objeto))
        if chave in vistos:
            if incerta:  # duplicata incerta contamina a já aceita, independente da ordem
                n = vistos[chave]
                resultado[n] = CompromissoExtraido(classe, resultado[n].objeto, resultado[n].evidencia, True)
            continue
        vistos[chave] = len(resultado)
        resultado.append(CompromissoExtraido(classe, objeto, evidencia, incerta))
    return tuple(resultado)


def comparar_sombra(base: Classificacao, extraidos) -> dict:
    """Concordância entre seleção barata e extração (para métricas em sombra)."""
    if (
        type(base) is not Classificacao
        or type(base.classe) is not str
        or base.classe not in CLASSES
        or type(base.incerta) is not bool
    ):
        raise ValueError("base inválida")
    if not isinstance(extraidos, (tuple, list)):
        raise ValueError("extraidos deve ser tupla ou lista")
    extraidos = tuple(extraidos)
    for e in extraidos:
        if (
            type(e) is not CompromissoExtraido
            or type(e.classe) is not str
            or e.classe not in CLASSES
            or type(e.incerta) is not bool
        ):
            raise ValueError("extraído inválido")
    classes = {e.classe for e in extraidos}
    firme_modelo = any(e.classe == PROMESSA and not e.incerta for e in extraidos)
    firme_base = base.classe == PROMESSA and not base.incerta
    return {
        "concorda": firme_modelo == firme_base,
        "modelo_firme": firme_modelo,
        "base_firme": firme_base,
        "classes_modelo": sorted(classes),
    }
