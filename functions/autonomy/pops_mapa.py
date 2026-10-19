"""Mapa de POPs ativos (P06 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, passo 8 do pacote: "Manter um mapa
de POPs ativos completo e carregamento por pertinência; não deixar
restrições críticas dependerem da seleção de cinco textos.").

Lógica pura -- sem I/O, mesmo padrão incremental de `autonomy/context.py` e
`autonomy/memoria_suspeita.py`. Recebe dicts de `pops_diretrizes` já lidos
(`{"id": ..., **campos}`) e os ids dos POPs que o carregamento por
pertinência (`main._match_pop_directives`: sempre ativos + até 3 por gatilho)
efetivamente injetou no prompt. Devolve o mapa COMPLETO com o que ficou de
fora, para que um POP existente porém não carregado seja visível (título e
gatilhos) em vez de silenciosamente inexistente.

Este módulo não altera o carregamento nem grava nada; ligar o mapa ao
contexto (`obter_contexto_operacional`, passo 6) é sub-entrega seguinte.
Só a instrução de um POP é política; título e gatilhos do mapa são rótulos e
devem ser tratados como dado, não como instrução.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class EntradaPop:
    id: str
    titulo: str
    sempre_ativo: bool
    n_gatilhos: int
    carregado: bool
    alcancavel: bool


@dataclass(frozen=True)
class MapaPops:
    entradas: tuple[EntradaPop, ...]
    sem_instrucao: tuple[str, ...]
    ignorados: int

    @property
    def nao_carregados(self) -> tuple[EntradaPop, ...]:
        return tuple(e for e in self.entradas if not e.carregado)

    @property
    def sempre_ativos_nao_carregados(self) -> tuple[EntradaPop, ...]:
        return tuple(e for e in self.nao_carregados if e.sempre_ativo)


def _texto(valor) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _conta_gatilhos(gatilhos) -> int:
    # Como o matcher: cada gatilho é `str(gatilho)` normalizado; vazio não conta.
    if not isinstance(gatilhos, list):
        return 0
    return sum(1 for g in gatilhos if _normaliza(str(g)))


def _normaliza(texto: str) -> str:
    # Cópia de main._normalize_pop_text (main.py não é importável sem efeitos).
    bruto = unicodedata.normalize("NFKD", texto.strip().lower())
    sem_acento = "".join(c for c in bruto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", sem_acento)).strip()


def montar_mapa_pops(pops, ids_carregados) -> MapaPops:
    """Mapa de todos os POPs com instrução, marcando os já carregados.

    - POP sem `id` textual (comparado cru, como o matcher) ou que não é dict
      é contado em `ignorados`; id repetido vale a
      primeira ocorrência e as demais entram em `ignorados` (ids de documento
      do Firestore são únicos; só entrada manual repete).
    - `alcancavel`: sempre ativo ou com ao menos um gatilho útil; um POP
      não sempre ativo sem gatilho nunca é carregado por pertinência.
    - POP sem `instrucao_sistema` não é carregável (o matcher o descarta);
      fica em `sem_instrucao` e não entra em `entradas`.
    - `sempre_ativo` só vale com `True` literal, como no matcher.
    - Ordem estável: sempre ativos primeiro, depois por id.
    """
    carregados = {i for i in (ids_carregados or ()) if isinstance(i, str)}
    entradas: list[EntradaPop] = []
    sem_instrucao: list[str] = []
    ignorados = 0
    vistos: set[str] = set()
    for pop in pops or ():
        pop_id = pop.get("id") if isinstance(pop, dict) else None
        if not isinstance(pop_id, str) or not pop_id.strip() or pop_id in vistos:
            ignorados += 1
            continue
        vistos.add(pop_id)
        if not _texto(pop.get("instrucao_sistema")):
            sem_instrucao.append(pop_id)
            continue
        n_gatilhos = _conta_gatilhos(pop.get("gatilhos"))
        sempre_ativo = pop.get("sempre_ativo") is True
        entradas.append(
            EntradaPop(
                id=pop_id,
                titulo=_texto(pop.get("titulo")) or pop_id,
                sempre_ativo=sempre_ativo,
                n_gatilhos=n_gatilhos,
                carregado=pop_id in carregados,
                alcancavel=sempre_ativo or n_gatilhos > 0,
            )
        )
    entradas.sort(key=lambda e: (not e.sempre_ativo, e.id))
    return MapaPops(tuple(entradas), tuple(sorted(sem_instrucao)), ignorados)
