"""Relatório de memória suspeita (P06 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, passo 10 do pacote: "Fazer
relatório de memória suspeita; saneamento histórico exige revisão por
evidência, sem apagar todos os dados antigos.").

Lógica pura -- sem I/O, mesmo padrão incremental de `autonomy/context.py` e
`autonomy/temporal.py`: classificação primeiro, testável sem Firestore. Este
módulo SÓ LÊ dicts de `knowledge_nodes` já lidos e devolve sinais com a
evidência que os motivou; não decide nem executa nenhuma correção. Apagar,
rebaixar ou superar um fato continua sendo decisão humana sobre a evidência
do relatório (aceite do passo 10), nunca efeito colateral daqui.

## Sinais

- `SEM_PROVENIENCIA`: `origem_fato` ausente/inválida (lida como
  `legacy_unknown`). Apenas um sinal de revisão: o plano manda ler memória
  antiga com essa origem, não descartá-la nem dar-lhe confiança retroativa.
- `INFERENCIA_COMO_REGRA_GLOBAL`: `origem_fato=inferencia_agente` gravada
  como `tipo=regra_global` -- o modelo concluiu sozinho uma regra de
  alcance global, sem confirmação humana registrada.
- `TELEMETRIA_COMO_FATO`: `origem_fato=telemetria_uso` com `tipo` de memória
  (`regra_global`/`fato_isolado`) -- passo 3: consulta de rotina não deve virar
  preferência pessoal.
- `SUPERADA_SEM_SUCESSOR`: `memoria_status=superada` sem `superada_por`; a
  relação `supersedes` ficou sem lineage verificável.
- `POSSIVEL_INJECAO`: o texto contém instrução dirigida ao modelo
  ("ignore as instruções anteriores" e similares) -- um documento externo
  não pode virar POP/regra (testes do pacote). Heurística barata e
  conservadora; um falso positivo só gera uma linha a revisar.

Sinais de documentos `superada` são reportados apenas como
`SUPERADA_SEM_SUCESSOR`: um fato já histórico não é mais candidato a
contaminar contexto, então os demais sinais seriam ruído.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from autonomy.context import (
    INFERENCIA_AGENTE,
    LEGADO_DESCONHECIDO,
    TELEMETRIA_USO,
    origem_fato_de_leitura,
)
from autonomy.temporal import STATUS_SUPERADA, memoria_status_de_leitura

SEM_PROVENIENCIA = "sem_proveniencia"
INFERENCIA_COMO_REGRA_GLOBAL = "inferencia_como_regra_global"
TELEMETRIA_COMO_FATO = "telemetria_como_fato"
SUPERADA_SEM_SUCESSOR = "superada_sem_sucessor"
POSSIVEL_INJECAO = "possivel_injecao"

SINAIS = (
    SEM_PROVENIENCIA,
    INFERENCIA_COMO_REGRA_GLOBAL,
    TELEMETRIA_COMO_FATO,
    SUPERADA_SEM_SUCESSOR,
    POSSIVEL_INJECAO,
)

_TIPOS_MEMORIA = frozenset({"regra_global", "fato_isolado"})
_MAX_TRECHO = 120

_PADROES_INJECAO = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignor(e|ar|em)\s+(todas\s+)?(as\s+)?(instru[cç][õo]es|regras|ordens)\s+(anteriores|acima|pr[eé]vias)",
        r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above)\s+(instructions|rules)",
        r"(desconsidere|esque[cç]a)\s+(tudo|as\s+instru[cç][õo]es|o\s+que)\s+(acima|anterior|foi\s+dito)",
        r"\bsystem\s*prompt\b",
        r"voc[eê]\s+(agora\s+)?(deve|precisa)\s+obedecer",
    )
)


@dataclass(frozen=True)
class SinalSuspeita:
    """Um sinal de revisão sobre UM documento, com a evidência que o motivou
    (nome do campo e valor/trecho observado) para que a revisão humana não
    dependa de reabrir o documento."""

    sinal: str
    campo: str
    evidencia: str


@dataclass(frozen=True)
class MemoriaSuspeita:
    doc_id: str
    sinais: tuple[SinalSuspeita, ...]


def _texto_do_fato(doc: dict) -> str:
    for chave in ("texto_memoria", "resumo", "fato"):
        valor = doc.get(chave)
        if isinstance(valor, str) and valor.strip():
            return valor
    return ""


def _trecho(texto: str) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= _MAX_TRECHO else texto[: _MAX_TRECHO - 1] + "…"


def sinais_de_memoria_suspeita(doc: dict | None) -> tuple[SinalSuspeita, ...]:
    """Sinais de um documento de `knowledge_nodes`. Nunca lança: campo ausente
    ou de tipo inesperado vira ausência de sinal (ou `SEM_PROVENIENCIA`),
    nunca exceção -- um relatório não deve falhar por um documento torto."""
    if not isinstance(doc, dict) or not doc:
        return ()

    if memoria_status_de_leitura(doc) == STATUS_SUPERADA:
        sucessor = doc.get("superada_por")
        if not (isinstance(sucessor, str) and sucessor.strip()):
            return (SinalSuspeita(SUPERADA_SEM_SUCESSOR, "superada_por", "ausente"),)
        return ()

    sinais: list[SinalSuspeita] = []
    origem = origem_fato_de_leitura(doc)
    tipo = doc.get("tipo")
    tipo = tipo if isinstance(tipo, str) else ""

    if origem == LEGADO_DESCONHECIDO:
        sinais.append(SinalSuspeita(SEM_PROVENIENCIA, "origem_fato", LEGADO_DESCONHECIDO))
    elif origem == INFERENCIA_AGENTE and tipo == "regra_global":
        sinais.append(SinalSuspeita(INFERENCIA_COMO_REGRA_GLOBAL, "tipo", f"{origem}/{tipo}"))
    elif origem == TELEMETRIA_USO and tipo in _TIPOS_MEMORIA:
        sinais.append(SinalSuspeita(TELEMETRIA_COMO_FATO, "tipo", f"{origem}/{tipo}"))

    texto = _texto_do_fato(doc)
    if texto and any(p.search(texto) for p in _PADROES_INJECAO):
        sinais.append(SinalSuspeita(POSSIVEL_INJECAO, "texto_memoria", _trecho(texto)))

    return tuple(sinais)


def relatorio_memoria_suspeita(
    documentos: Iterable[tuple[str, dict | None]],
) -> tuple[MemoriaSuspeita, ...]:
    """Relatório sobre pares `(doc_id, dict)`: só entram documentos com ao
    menos um sinal, na ordem recebida. Não altera nenhum documento."""
    achados = []
    for doc_id, doc in documentos:
        sinais = sinais_de_memoria_suspeita(doc)
        if sinais:
            achados.append(MemoriaSuspeita(doc_id=str(doc_id), sinais=sinais))
    return tuple(achados)


def contagem_por_sinal(relatorio: Iterable[MemoriaSuspeita]) -> dict[str, int]:
    """Totais por sinal (todos os sinais de `SINAIS`, inclusive os zerados)."""
    totais = {s: 0 for s in SINAIS}
    for item in relatorio:
        for sinal in item.sinais:
            totais[sinal.sinal] += 1
    return totais
