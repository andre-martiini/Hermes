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
  conservadora (ver `_PADROES_INJECAO`); um falso positivo só gera uma linha a revisar. Todos os campos de texto lidos por consumidores reais são varridos, e a evidência aponta o campo de onde veio o trecho.

Documentos `superada` reportam `SUPERADA_SEM_SUCESSOR` e `POSSIVEL_INJECAO`
(`main._build_memory_context` ainda injeta texto sem filtrar `memoria_status`);
os demais sinais seriam ruído num fato já histórico.
"""

from __future__ import annotations

import re
import unicodedata
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

# Campos de texto que algum consumidor real injeta em prompt
# (`main.py::_find_similar_memory_nodes` lê texto_memoria/resumo/titulo;
# `copilot_context.py` lê texto_memoria/fato/resumo): TODOS são varridos,
# não só o primeiro preenchido.
_CAMPOS_TEXTO = ("texto_memoria", "resumo", "fato", "titulo")

# Padrões deliberadamente restritos a instruções dirigidas ao modelo. Frases
# como "você deve obedecer ao regulamento" ou a simples menção a "system
# prompt" são texto legítimo comum e NÃO são padrões; já "ignore as
# instruções anteriores" pode aparecer em texto legítimo sobre editais --
# aceito como falso positivo barato (uma linha a revisar), documentado acima.
_PADROES_INJECAO = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignor(e|ar|em)\s+(todas\s+)?(as\s+)?(suas?\s+)?(instru[cç][õo]es|regras|ordens)\s+(anteriores|acima|pr[eé]vias)",
        r"(ignore|disregard|forget)\s+(all\s+|any\s+)?((the|your|my)\s+)?(previous|prior|above)\s+(instructions|rules)",
        r"(ignore|disregard|forget)\s+(all\s+|any\s+)?((the|your|my)\s+)?(instructions|rules)\s+(above|before)",
        r"(desconsidere|esque[cç]a)\s+(tudo|as\s+instru[cç][õo]es)(\s+o\s+que)?\s+(acima|anterior|foi\s+dito|eu\s+disse|eu\s+falei)",
        r"\b(reveal|revele|mostre)\s+(o\s+|seu\s+|sua\s+|your\s+|the\s+)?system\s*prompt\b",
    )
)


# Negação imediatamente antes do padrão ("não ignore as instruções
# anteriores") é uma regra legítima, não uma ordem ao modelo.
# Só espaço/tab entre a negação e o padrão (uma quebra de linha separa
# frases) e fronteira de palavra antes ("whenever" não é "never").
_NEGACAO_ANTES = re.compile(r"\b(n[aã]o|nunca|jamais|do\s+not|don't|never)[ \t]+$", re.IGNORECASE)


def _variantes(texto: str) -> tuple[str, str]:
    """NFKC + caracteres de formatação (categoria Unicode Cf: largura zero,
    marcas bidi etc.) removidos OU trocados por espaço. As duas variantes
    são varridas: remover cola "ignore\u200bas" em "ignoreas", e trocar por
    espaço separaria "ig\u200bnore" em "ig nore" -- cada ofuscação só é
    desfeita por uma das duas. Limitação conhecida e aceita (o relatório é
    heurística para revisão humana, não barreira): Cf DENTRO da palavra e no
    lugar do espaço ao mesmo tempo ("ig\u200bnore\u200bas") escapa das duas."""
    normalizado = unicodedata.normalize("NFKC", texto)
    removido = "".join(c for c in normalizado if unicodedata.category(c) != "Cf")
    espaco = "".join(" " if unicodedata.category(c) == "Cf" else c for c in normalizado)
    return removido, espaco


def _trecho_do_padrao(texto: str) -> str | None:
    """Trecho (janela centrada no primeiro casamento não negado) ou None."""
    for variante in _variantes(texto):
        for padrao in _PADROES_INJECAO:
            for m in padrao.finditer(variante):
                if _NEGACAO_ANTES.search(variante[max(0, m.start() - 20) : m.start()]):
                    continue
                ini = max(0, m.start() - _MAX_TRECHO // 4)
                return _trecho(variante[ini : ini + _MAX_TRECHO * 2])
    return None


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


def _trecho(texto: str) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= _MAX_TRECHO else texto[: _MAX_TRECHO - 1] + "…"


def _sinais_de_injecao(doc: dict) -> list[SinalSuspeita]:
    achados = []
    for campo in _CAMPOS_TEXTO:
        texto = doc.get(campo)
        if not isinstance(texto, str):
            continue
        trecho = _trecho_do_padrao(texto)
        if trecho is not None:
            achados.append(SinalSuspeita(POSSIVEL_INJECAO, campo, trecho))
    return achados


def sinais_de_memoria_suspeita(doc: dict | None) -> tuple[SinalSuspeita, ...]:
    """Sinais de um documento de `knowledge_nodes`. Nunca lança: campo ausente
    ou de tipo inesperado vira ausência de sinal (ou `SEM_PROVENIENCIA`),
    nunca exceção -- um relatório não deve falhar por um documento torto."""
    if not isinstance(doc, dict) or not doc:
        return ()

    sinais: list[SinalSuspeita] = []
    if memoria_status_de_leitura(doc) == STATUS_SUPERADA:
        sucessor = doc.get("superada_por")
        if not (isinstance(sucessor, str) and sucessor.strip()):
            sinais.append(SinalSuspeita(SUPERADA_SEM_SUCESSOR, "superada_por", "ausente"))
        # Só a injeção é varrida em fato superado: `main._build_memory_context`
        # ainda injeta texto sem filtrar `memoria_status`.
        sinais.extend(_sinais_de_injecao(doc))
        return tuple(sinais)

    origem = origem_fato_de_leitura(doc)
    tipo = doc.get("tipo")
    tipo = tipo if isinstance(tipo, str) else ""

    if origem == LEGADO_DESCONHECIDO:
        sinais.append(SinalSuspeita(SEM_PROVENIENCIA, "origem_fato", LEGADO_DESCONHECIDO))
    elif origem == INFERENCIA_AGENTE and tipo == "regra_global":
        sinais.append(SinalSuspeita(INFERENCIA_COMO_REGRA_GLOBAL, "tipo", f"{origem}/{tipo}"))
    elif origem == TELEMETRIA_USO and tipo in _TIPOS_MEMORIA:
        sinais.append(SinalSuspeita(TELEMETRIA_COMO_FATO, "tipo", f"{origem}/{tipo}"))

    sinais.extend(_sinais_de_injecao(doc))
    return tuple(sinais)


def relatorio_memoria_suspeita(
    documentos: Iterable[tuple[str, dict | None]],
) -> tuple[MemoriaSuspeita, ...]:
    """Relatório sobre pares `(doc_id, dict)`: só entram documentos com ao
    menos um sinal, na ordem recebida. Não altera nenhum documento."""
    achados = []
    for item in documentos:
        try:
            doc_id, doc = item
        except (TypeError, ValueError):
            continue  # item torto: o relatório não falha por um documento
        if not isinstance(doc_id, str):
            continue
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


COLECAO_KNOWLEDGE_NODES = "knowledge_nodes"
TAMANHO_PAGINA_VARREDURA = 200
MAX_DOCUMENTOS_VARREDURA = 5000


@dataclass(frozen=True)
class ResultadoVarredura:
    relatorio: tuple[MemoriaSuspeita, ...]
    documentos_lidos: int
    truncado: bool  # parou em `max_documentos` com ainda haver páginas


def varrer_knowledge_nodes(
    db,
    *,
    tamanho_pagina: int = TAMANHO_PAGINA_VARREDURA,
    max_documentos: int = MAX_DOCUMENTOS_VARREDURA,
) -> ResultadoVarredura:
    """Varredura SOMENTE LEITURA de `knowledge_nodes`, paginada por
    `order_by("__name__")` + `start_after(ultimo_doc)` (mesmo padrão de
    `mcp_jobs`), limitada a `max_documentos`. Nunca grava. Um erro de leitura
    propaga: relatório parcial silencioso esconderia memória suspeita."""
    if tamanho_pagina < 1 or max_documentos < 1:
        raise ValueError("tamanho_pagina e max_documentos devem ser >= 1")
    consulta_base = db.collection(COLECAO_KNOWLEDGE_NODES).order_by("__name__")
    lidos = 0
    cursor = None
    achados: list[MemoriaSuspeita] = []
    truncado = False
    while True:
        if lidos >= max_documentos:
            sonda = consulta_base.limit(1)
            if cursor is not None:
                sonda = sonda.start_after(cursor)
            truncado = bool(list(sonda.stream()))
            break
        limite = min(tamanho_pagina, max_documentos - lidos)
        pagina = consulta_base.limit(limite)
        if cursor is not None:
            pagina = pagina.start_after(cursor)
        snaps = list(pagina.stream())
        if not snaps:
            break
        # Classifica a página na hora e descarta os documentos (embeddings de
        # 768 floats): só os achados ficam retidos, memória limitada a uma página.
        achados.extend(relatorio_memoria_suspeita((snap.id, snap.to_dict()) for snap in snaps))
        lidos += len(snaps)
        cursor = snaps[-1]
        if len(snaps) < limite:
            break
    return ResultadoVarredura(
        relatorio=tuple(achados),
        documentos_lidos=lidos,
        truncado=truncado,
    )
