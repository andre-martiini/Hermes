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


def validar_extracao(mensagem, saida, hoje=None) -> tuple[CompromissoExtraido, ...]:
    """`saida` = {"compromissos": [{classe, objeto, evidencia}, ...]}."""
    if type(mensagem) is not str or not mensagem.strip():
        raise ValueError("mensagem inválida")
    if type(saida) is not dict or type(saida.get("compromissos")) is not list:
        raise ValueError("saída sem lista de compromissos")
    itens = saida["compromissos"]
    if len(itens) > MAX_COMPROMISSOS:
        raise ValueError("compromissos demais")
    base = classificar_mensagem(mensagem, hoje)
    texto_n = _normalizar(mensagem)
    vistos = set()
    resultado = []
    for item in itens:
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
        if classe == base.classe:
            incerta = base.incerta  # modelo concorda com a base: herda a dúvida dela
        elif base.classe in _CAUTELA:
            classe, incerta = base.classe, True  # modelo não afrouxa cautela em nenhuma classe
        elif classe == PROMESSA and (base.classe in _CAUTELA or base.incerta):
            classe, incerta = (base.classe if base.classe in _CAUTELA else INTENCAO_VAGA), True
        elif classe == PROMESSA and base.classe != PROMESSA:
            incerta = True  # a seleção barata não viu promessa: modelo sozinho não firma
        chave = (classe, _normalizar(objeto))
        if chave in vistos:
            continue
        vistos.add(chave)
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
