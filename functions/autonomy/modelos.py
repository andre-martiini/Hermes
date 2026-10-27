"""Seleção de modelo por configuração validada e custo por tarifa versionada
(P08 do plano de autonomia, passos 8 e 9).

Lógica pura, sem I/O: a configuração (modelos validados na conta + tarifas)
vem do wiring e é conferida aqui. Regras do contrato:

- nenhum alias móvel explícito (`latest`, `alias`, `default`) é aceito, e id
  algum vale só porque consta no código: o id precisa estar na lista validada
  da conta (a garantia de que é um snapshot fixo vem dessa validação, não do
  formato do id), ter tarifa versionada e a validação não pode estar vencida;
- rotação de modelo: dado o conjunto de modelos indisponíveis, escolhe-se o
  próximo da ordem de preferência do papel; sem nenhum, resultado tipado de
  erro (nunca um modelo "padrão" escondido);
- custo real por chamada em `Decimal`, incluindo leitura/escrita de cache de
  prompt, para medir o ganho do cache (passo 9). Preços NÃO são embutidos:
  chegam na configuração da conta.
"""

from __future__ import annotations

import re
from types import MappingProxyType
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, InvalidOperation
from enum import Enum
from typing import Iterable, Mapping

_ID_MODELO = re.compile(r"claude-[a-z0-9][a-z0-9.\-]{2,60}")
_ALIAS_MOVEL = re.compile(r"(^|[-.])(latest|alias|default)([-.]|$)")
_ROLE = re.compile(r"[a-z][a-z0-9_]{0,39}")
_MILHAO = Decimal(1_000_000)
_CTX = Context(prec=60)  # independe do contexto global do chamador
_TOKENS_MAX = 10**12
_PRECO_MAX = Decimal(1_000_000)  # USD por milhão de tokens; evita expoentes absurdos
_PRECO_MIN_EXP = -12
VALIDADE_MAXIMA_DIAS = 90
TOLERANCIA_RELOGIO = timedelta(minutes=5)  # validação "no futuro" além disso = config suspeita


class ErroConfigModelos(ValueError):
    """Configuração de modelos inválida (falha ao carregar, nunca em silêncio)."""


class MotivoSelecao(str, Enum):
    PAPEL_DESCONHECIDO = "papel_desconhecido"
    VALIDACAO_VENCIDA = "validacao_vencida"
    TODOS_INDISPONIVEIS = "todos_indisponiveis"


def id_modelo_valido(modelo_id: object) -> bool:
    return (
        isinstance(modelo_id, str)
        and _ID_MODELO.fullmatch(modelo_id) is not None
        and _ALIAS_MOVEL.search(modelo_id) is None
    )


def _datetime_com_fuso(valor: object) -> bool:
    return isinstance(valor, datetime) and valor.utcoffset() is not None


def _preco(valor: object, nome: str) -> Decimal:
    if isinstance(valor, bool) or not isinstance(valor, (int, str, Decimal)):
        raise ErroConfigModelos(f"{nome}: use int, str ou Decimal (float perde precisão)")
    try:
        d = Decimal(valor)
    except InvalidOperation as exc:
        raise ErroConfigModelos(f"{nome}: valor inválido") from exc
    if not d.is_finite() or d < 0 or d > _PRECO_MAX or d.as_tuple().exponent < _PRECO_MIN_EXP:
        raise ErroConfigModelos(f"{nome}: deve ser finito, >= 0, <= {_PRECO_MAX} e com até 12 casas")
    return _CTX.plus(d)  # normaliza -0 sem depender do contexto global


@dataclass(frozen=True)
class TarifaModelo:
    """Preço por milhão de tokens, em USD, de uma versão da tabela da conta."""

    modelo_id: str
    versao: str
    entrada: Decimal
    saida: Decimal
    cache_leitura: Decimal
    cache_escrita: Decimal

    def __post_init__(self) -> None:
        if not id_modelo_valido(self.modelo_id):
            raise ErroConfigModelos("tarifa: modelo_id inválido ou alias móvel")
        if not isinstance(self.versao, str) or not self.versao.strip():
            raise ErroConfigModelos("tarifa: versao obrigatória")
        for nome in ("entrada", "saida", "cache_leitura", "cache_escrita"):
            object.__setattr__(self, nome, _preco(getattr(self, nome), nome))


@dataclass(frozen=True, eq=False)  # eq=False: hash por identidade (mappingproxy não é hasheável)
class ConfigModelos:
    """`papeis` mapeia papel -> ids em ordem de preferência (o 1º é o titular)."""

    papeis: Mapping[str, tuple[str, ...]]
    tarifas: Mapping[str, TarifaModelo]
    validado_em: datetime

    def __post_init__(self) -> None:
        if not _datetime_com_fuso(self.validado_em):
            raise ErroConfigModelos("validado_em deve ser datetime com fuso")
        if not isinstance(self.papeis, Mapping) or not isinstance(self.tarifas, Mapping):
            raise ErroConfigModelos("papeis e tarifas devem ser mapeamentos")
        if not all(isinstance(t, TarifaModelo) for t in self.tarifas.values()):
            raise ErroConfigModelos("tarifas devem ser TarifaModelo")
        if not self.papeis:
            raise ErroConfigModelos("ao menos um papel")
        papeis = {}
        for papel, ids in self.papeis.items():
            if not isinstance(papel, str) or _ROLE.fullmatch(papel) is None:
                raise ErroConfigModelos("nome de papel inválido")
            if not isinstance(ids, (list, tuple)):
                raise ErroConfigModelos(f"papel {papel}: lista ordenada de ids esperada")
            ids = tuple(ids)
            for mid in ids:
                if not id_modelo_valido(mid):
                    raise ErroConfigModelos(f"papel {papel}: modelo inválido ou alias móvel")
            if not ids or len(set(ids)) != len(ids):
                raise ErroConfigModelos(f"papel {papel}: lista vazia ou com repetição")
            for mid in ids:
                tarifa = self.tarifas.get(mid)
                if tarifa is None or tarifa.modelo_id != mid:
                    raise ErroConfigModelos(f"papel {papel}: modelo sem tarifa versionada")
            papeis[papel] = ids
        object.__setattr__(self, "papeis", MappingProxyType(papeis))
        object.__setattr__(self, "tarifas", MappingProxyType(dict(self.tarifas)))


@dataclass(frozen=True)
class ModeloEscolhido:
    modelo_id: str
    tarifa: TarifaModelo
    rotacionado: bool  # True quando não é o titular do papel


@dataclass(frozen=True)
class ErroSelecao:
    motivo: MotivoSelecao


def selecionar_modelo(
    config: ConfigModelos,
    papel: str,
    agora: datetime,
    indisponiveis: Iterable[str] = (),
) -> ModeloEscolhido | ErroSelecao:
    if not _datetime_com_fuso(agora):
        raise ValueError("agora deve ser datetime com fuso")
    ids = config.papeis.get(papel) if isinstance(papel, str) else None
    if ids is None:
        return ErroSelecao(MotivoSelecao.PAPEL_DESCONHECIDO)
    try:
        idade = agora.astimezone(timezone.utc) - config.validado_em.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ValueError("agora fora do intervalo suportado") from exc
    if idade > timedelta(days=VALIDADE_MAXIMA_DIAS) or idade < -TOLERANCIA_RELOGIO:
        return ErroSelecao(MotivoSelecao.VALIDACAO_VENCIDA)
    if isinstance(indisponiveis, (str, bytes)) or not isinstance(indisponiveis, Iterable):
        raise ValueError("indisponiveis deve ser uma coleção de ids")
    fora = tuple(indisponiveis)
    if not all(isinstance(i, str) for i in fora):
        raise ValueError("indisponiveis deve conter apenas ids (str)")
    fora = frozenset(fora)
    for i, mid in enumerate(ids):
        if mid not in fora:
            return ModeloEscolhido(mid, config.tarifas[mid], rotacionado=i > 0)
    return ErroSelecao(MotivoSelecao.TODOS_INDISPONIVEIS)


def _tokens(valor: object, nome: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or not 0 <= valor <= _TOKENS_MAX:
        raise ValueError(f"{nome} deve ser inteiro em [0, 10**12]")
    return valor


def custo_chamada(
    tarifa: TarifaModelo,
    entrada: int,
    saida: int,
    cache_leitura: int = 0,
    cache_escrita: int = 0,
) -> Decimal:
    """Custo em USD. `entrada` conta só tokens NÃO servidos/gravados no cache."""
    if not isinstance(tarifa, TarifaModelo):
        raise ValueError("tarifa deve ser TarifaModelo")
    ctx = _CTX
    parcelas = (
        (_tokens(entrada, "entrada"), tarifa.entrada),
        (_tokens(saida, "saida"), tarifa.saida),
        (_tokens(cache_leitura, "cache_leitura"), tarifa.cache_leitura),
        (_tokens(cache_escrita, "cache_escrita"), tarifa.cache_escrita),
    )
    total = Decimal(0)
    for n, preco in parcelas:
        total = ctx.add(total, ctx.multiply(Decimal(n), preco))
    return ctx.divide(total, _MILHAO)


def taxa_acerto_cache(entrada: int, cache_leitura: int, cache_escrita: int = 0) -> Decimal:
    """Fração dos tokens de entrada servida do cache (0 se não houve entrada)."""
    e, l, w = _tokens(entrada, "entrada"), _tokens(cache_leitura, "cache_leitura"), _tokens(cache_escrita, "cache_escrita")
    total = e + l + w
    return _CTX.divide(Decimal(l), Decimal(total)) if total else Decimal(0)
