"""Correlação de entregáveis entre canais (P07 do plano de autonomia, passo 5).

Lógica pura -- sem I/O e sem wiring. Liga um compromisso a evidências de
entrega vindas de WhatsApp, Gmail, tarefa ou documento. ID explícito em comum
(arquivo do Drive, thread, tarefa) é vínculo firme; coincidência só de objeto
prometido (planilha, relatório...) é evidência semântica e SEMPRE incerta:
quem consome mantém o compromisso pendente. Nunca encerra nada sozinha.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from autonomy.cumprimento import _combinante_estranha, _objetos
from autonomy.commitments import _normalizar

CANAIS = ("whatsapp", "gmail", "tarefa", "documento")
VINCULO_ID = "id"
VINCULO_SEMANTICO = "semantico"
_MAX_IDS = 50
_MAX_TEXTO = 600


@dataclass(frozen=True)
class Evidencia:
    canal: str
    ref: str
    nome: str = ""
    ids: tuple = ()


@dataclass(frozen=True)
class Vinculo:
    ref: str
    canal: str
    tipo: str
    incerta: bool
    motivo: str


def _texto(valor, nome, limite=_MAX_TEXTO):
    if type(valor) is not str or len(valor) > limite or _combinante_estranha(valor):
        raise ValueError(f"{nome} inválido")
    return valor


def _ids(valor, nome) -> frozenset:
    if type(valor) not in (list, tuple, set, frozenset) or len(valor) > _MAX_IDS:
        raise ValueError(f"{nome} deve ser coleção pequena de textos")
    saida = set()
    for i in valor:
        if type(i) is not str or not i.strip() or len(i) > 200 or not i.isprintable():
            raise ValueError(f"{nome} contém id inválido")
        saida.add(i.strip())
    return frozenset(saida)


def correlacionar(promessa, evidencias, ids_compromisso=()) -> tuple[Vinculo, ...]:
    """Vínculos entre `promessa` e `evidencias` (sequência de `Evidencia`).

    ID em comum -> `id`, firme. Mesmo objeto prometido no nome da evidência,
    sem ID em comum -> `semantico`, incerta. Evidência sem nenhum dos dois não
    aparece. Só ValueError para entradas inválidas."""
    prom = _normalizar(_texto(promessa, "promessa"))
    meus = _ids(ids_compromisso, "ids_compromisso")
    if type(evidencias) not in (list, tuple) or len(evidencias) > 200:
        raise ValueError("evidencias deve ser lista ou tupla")
    objetos = _objetos(prom)
    saida = []
    for ev in evidencias:
        if type(ev) is not Evidencia:
            raise ValueError("evidência deve ser Evidencia")
        if ev.canal not in CANAIS:
            raise ValueError("canal inválido")
        ref = _texto(ev.ref, "ref", 200)
        if not ref.strip():
            raise ValueError("ref inválido")
        nome = re.sub(r"[_.\-]+", " ", _normalizar(_texto(ev.nome, "nome")))
        if meus & _ids(ev.ids, "ids"):
            saida.append(Vinculo(ref, ev.canal, VINCULO_ID, False, "id_em_comum"))
        elif objetos and objetos & _objetos(nome):
            saida.append(Vinculo(ref, ev.canal, VINCULO_SEMANTICO, True, "objeto_prometido"))
    return tuple(saida)


def vinculo_firme(vinculos) -> bool:
    """True só se houver ao menos um vínculo por ID e nenhum incerto o contradiz."""
    return any(v.tipo == VINCULO_ID and not v.incerta for v in vinculos)
