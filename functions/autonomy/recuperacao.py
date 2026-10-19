"""Recuperação de memória por relevância, validade e autoridade (P06 do plano
de autonomia, docs/plano-hermes-autonomo-2026-09-06.md, passo 5 do pacote:
"Recuperar por entidades, objetivo, relevância, validade e autoridade da
fonte; combinar busca exata, lexical e vetorial disponível.").

Lógica pura -- sem I/O, mesmo padrão incremental de `autonomy/context.py`,
`autonomy/temporal.py` e `autonomy/memoria_suspeita.py`. Recebe documentos de
`knowledge_nodes` já lidos (`{"id": ..., **campos}`) e, opcionalmente, as
similaridades vetoriais já calculadas por quem consulta o índice. Devolve os
candidatos ordenados com os motivos de cada pontuação e a lista dos
descartados com a razão -- para que `obter_contexto_operacional` /
`consultar_memoria_contextual` (passo 6, sub-entrega seguinte) possam mostrar
fontes e lacunas em vez de esconder o que ficou de fora.

Regras (todas conservadoras; nada aqui grava ou apaga):
- Descartados: `memoria_status` superada; `validade_fim` já passada;
  `validade_inicio` ainda no futuro; origem `telemetria_uso` (passo 3: uso
  não é fato nem preferência); documento sem texto legível.
- Autoridade da fonte multiplica a relevância: declaração humana > fonte
  externa > resumo derivado > inferência do agente > legado sem proveniência.
  Fato `legacy_unknown` não ganha confiança retrospectiva: peso baixo e
  `aviso_legado=True`.
- Relevância soma: frase exata da consulta (maior), termos da consulta
  (lexical, fração dos termos presentes), entidades citadas e similaridade
  vetorial informada (0..1; valores inválidos são ignorados).
- Sem nenhum sinal de relevância o candidato é descartado
  (`sem_relevancia`), por mais autoritativa que seja a origem: autoridade
  nunca cria relevância sozinha.
- O texto do documento é dado, não instrução: o módulo só o compara.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from autonomy.context import (
    DECLARACAO_HUMANA,
    FONTE_EXTERNA,
    INFERENCIA_AGENTE,
    LEGADO_DESCONHECIDO,
    RESUMO_DERIVADO,
    TELEMETRIA_USO,
    origem_fato_de_leitura,
)
from autonomy.temporal import STATUS_SUPERADA, memoria_status_de_leitura

_UM_SEGUNDO = timedelta(seconds=1)
_CAMPOS_TEXTO = ("texto_memoria", "resumo", "fato", "titulo")

PESO_AUTORIDADE = {
    DECLARACAO_HUMANA: 1.0,
    FONTE_EXTERNA: 0.7,
    RESUMO_DERIVADO: 0.5,
    INFERENCIA_AGENTE: 0.3,
    LEGADO_DESCONHECIDO: 0.2,
}

PONTOS_FRASE_EXATA = 3.0
PONTOS_LEXICAL = 2.0
PONTOS_ENTIDADE = 1.0
PONTOS_VETORIAL = 2.0

_STOPWORDS = frozenset(
    "a o as os um uma uns umas de do da dos das em no na nos nas por para com "
    "sem e ou que se ao aos como mais mas ja ser foi e eh sao".split()
)


@dataclass(frozen=True)
class Recuperado:
    doc_id: str
    pontuacao: float
    origem_fato: str
    motivos: tuple[str, ...]
    aviso_legado: bool


@dataclass(frozen=True)
class Descartado:
    doc_id: str
    razao: str


@dataclass(frozen=True)
class ResultadoRecuperacao:
    recuperados: tuple[Recuperado, ...]
    descartados: tuple[Descartado, ...]


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c
        for c in unicodedata.normalize("NFKD", texto.casefold())
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", sem_acento)).strip()


def _termos(texto: str) -> set[str]:
    return {t for t in _normalizar(texto).split() if t not in _STOPWORDS and len(t) > 1}


def _texto_do_documento(doc: dict) -> str:
    partes = [doc[c] for c in _CAMPOS_TEXTO if isinstance(doc.get(c), str) and doc[c].strip()]
    return " ".join(partes)


def _instante(valor, padrao: datetime, fim_do_dia: bool = False) -> datetime | None:
    """Converte `validade_*` (ISO 8601 em string) em datetime com fuso UTC.
    Valor ausente -> `None`; valor presente mas ilegível -> `padrao`, que o
    chamador escolhe de forma a NÃO excluir o documento por dado corrompido
    (a validade só descarta quando é claramente legível)."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        dt = valor
    elif isinstance(valor, date):
        dt = datetime(valor.year, valor.month, valor.day)
        if fim_do_dia:
            dt += timedelta(days=1)
    elif isinstance(valor, str):
        try:
            texto = valor.strip()
            dt = datetime.fromisoformat(texto.replace("Z", "+00:00").replace("z", "+00:00"))
            if fim_do_dia and len(texto) == 10:
                dt += timedelta(days=1)
        except ValueError:
            return padrao
    else:
        return padrao
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _similaridade_valida(valor) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    if not math.isfinite(valor):
        return None
    return float(valor) if 0.0 <= valor <= 1.0 else None


def recuperar(
    documentos,
    *,
    consulta: str = "",
    entidades=(),
    similaridades: dict | None = None,
    agora: datetime | None = None,
    limite: int = 10,
) -> ResultadoRecuperacao:
    """Ordena `documentos` (iterável de dicts com `id`) por
    relevância x autoridade. `limite` (>= 1) corta só os recuperados; os
    descartados são sempre todos listados. Empates ordenam por `doc_id`
    para resultado determinístico."""
    if isinstance(limite, bool) or not isinstance(limite, int) or limite < 1:
        raise ValueError("limite deve ser inteiro >= 1")
    agora = agora or datetime.now(timezone.utc)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    consulta = consulta if isinstance(consulta, str) else ""
    frase = _normalizar(consulta)
    termos_consulta = _termos(consulta)
    if isinstance(entidades, str) or not hasattr(entidades, "__iter__"):
        entidades = ()
    nomes = [
        n for n in (_normalizar(e) for e in entidades if isinstance(e, str)) if n
    ]
    similaridades = similaridades if isinstance(similaridades, dict) else {}

    recuperados: list[Recuperado] = []
    descartados: list[Descartado] = []
    for doc in documentos:
        if not isinstance(doc, dict) or not isinstance(doc.get("id"), str):
            descartados.append(Descartado(str(doc.get("id")) if isinstance(doc, dict) else "?", "documento_malformado"))
            continue
        doc_id = doc["id"]
        origem = origem_fato_de_leitura(doc)
        if memoria_status_de_leitura(doc) == STATUS_SUPERADA:
            descartados.append(Descartado(doc_id, "superada"))
            continue
        if origem == TELEMETRIA_USO:
            descartados.append(Descartado(doc_id, "telemetria_nao_e_fato"))
            continue
        fim = _instante(doc.get("validade_fim"), agora + _UM_SEGUNDO, fim_do_dia=True)
        if fim is not None and fim <= agora:
            descartados.append(Descartado(doc_id, "validade_expirada"))
            continue
        inicio = _instante(doc.get("validade_inicio"), agora - _UM_SEGUNDO)
        if inicio is not None and inicio > agora:
            descartados.append(Descartado(doc_id, "validade_futura"))
            continue
        texto = _normalizar(_texto_do_documento(doc))
        if not texto:
            descartados.append(Descartado(doc_id, "sem_texto"))
            continue

        pontos = 0.0
        motivos: list[str] = []
        texto_cercado = f" {texto} "
        if frase and len(frase) > 2 and f" {frase} " in texto_cercado:
            pontos += PONTOS_FRASE_EXATA
            motivos.append("frase_exata")
        if termos_consulta:
            presentes = termos_consulta & set(texto.split())
            if presentes:
                pontos += PONTOS_LEXICAL * len(presentes) / len(termos_consulta)
                motivos.append("lexical")
        casadas = [n for n in nomes if f" {n} " in texto_cercado]
        if casadas:
            pontos += PONTOS_ENTIDADE * len(casadas) / len(nomes)
            motivos.append("entidade")
        sim = _similaridade_valida(similaridades.get(doc_id))
        if sim:
            pontos += PONTOS_VETORIAL * sim
            motivos.append("vetorial")
        if pontos <= 0:
            descartados.append(Descartado(doc_id, "sem_relevancia"))
            continue
        recuperados.append(
            Recuperado(
                doc_id=doc_id,
                pontuacao=round(pontos * PESO_AUTORIDADE.get(origem, PESO_AUTORIDADE[LEGADO_DESCONHECIDO]), 6),
                origem_fato=origem,
                motivos=tuple(motivos),
                aviso_legado=origem == LEGADO_DESCONHECIDO,
            )
        )
    recuperados.sort(key=lambda r: (-r.pontuacao, r.doc_id))
    return ResultadoRecuperacao(tuple(recuperados[:limite]), tuple(descartados))
