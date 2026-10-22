"""Item de atenção por compromisso/versão (P07 do plano de autonomia, passo 8).

Lógica pura -- sem I/O e sem wiring. Converte a decisão de
`followup_guard.revalidar_followup` em um registro idempotente, endereçado por
chave de compromisso + versão, com a próxima avaliação. Quem grava (futuro,
atrás de flag/sombra) usa `deve_gravar` para não regredir versão nem duplicar.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from autonomy.followup_guard import ADIAR, ENVIAR, SUPRIMIR, DecisaoFollowup

ADIAR_HORAS = 4
ESTADO_ABERTO = "aberto"
ESTADO_ENCERRADO = "encerrado"
ESTADO_ENVIADO = "enviado"
ESTADOS = (ESTADO_ABERTO, ESTADO_ENCERRADO, ESTADO_ENVIADO)
ESTADOS_TERMINAIS = (ESTADO_ENCERRADO, ESTADO_ENVIADO)


def _agora_utc(agora) -> datetime:
    if not isinstance(agora, datetime) or agora.utcoffset() is None:
        raise ValueError("agora deve ser datetime com fuso")
    try:
        return agora.astimezone(timezone.utc).replace(microsecond=0)
    except OverflowError:
        raise ValueError("agora fora do intervalo") from None


def _versao(versao) -> int:
    if isinstance(versao, bool) or not isinstance(versao, int) or versao < 1:
        raise ValueError("versao deve ser inteiro >= 1")
    return versao


def id_item_atencao(chave: str, versao: int) -> str:
    if not isinstance(chave, str) or not re.fullmatch(r"[^\s/]+", chave):
        raise ValueError("chave obrigatória, sem espaço nem barra")
    return f"{chave}__v{_versao(versao)}"


def proxima_avaliacao(decisao: DecisaoFollowup, agora) -> datetime | None:
    """ENVIAR: já elegível. ADIAR: reavalia depois. SUPRIMIR: nunca."""
    base = _agora_utc(agora)
    if not isinstance(decisao, DecisaoFollowup) or not isinstance(decisao.motivo, str):
        raise ValueError("decisão inválida")
    try:
        if decisao.acao == ENVIAR:
            return base
        if decisao.acao == ADIAR:
            return base + timedelta(hours=ADIAR_HORAS)
    except OverflowError:
        raise ValueError("agora fora do intervalo") from None
    if decisao.acao == SUPRIMIR:
        return None
    raise ValueError("decisão desconhecida")


def montar_item_atencao(chave: str, versao: int, decisao: DecisaoFollowup, agora) -> dict:
    proxima = proxima_avaliacao(decisao, agora)
    return {
        "id": id_item_atencao(chave, versao),
        "chave_compromisso": chave,
        "versao": versao,
        "acao": decisao.acao,
        "motivo": decisao.motivo,
        "estado": ESTADO_ENCERRADO if proxima is None else ESTADO_ABERTO,
        "avaliado_em": _agora_utc(agora).isoformat(),
        "proxima_avaliacao": proxima.isoformat() if proxima else None,
    }


def marcar_enviado(item: dict, agora) -> dict:
    """Estado terminal depois do envio: o item deixa de ser elegível.
    Só um item aberto com ação ENVIAR pode ser marcado."""
    try:
        _validar(item)
    except (KeyError, TypeError) as exc:
        raise ValueError("item malformado") from exc
    if item["estado"] != ESTADO_ABERTO or item["acao"] != ENVIAR:
        raise ValueError("só item aberto com ação enviar vira enviado")
    quando = max(_agora_utc(agora), datetime.fromisoformat(item["avaliado_em"]).astimezone(timezone.utc))
    return {**item, "estado": ESTADO_ENVIADO, "avaliado_em": quando.isoformat(),
            "proxima_avaliacao": None}


def _validar(item) -> tuple[str, int, datetime, datetime | None]:
    if not isinstance(item, dict):
        raise ValueError("item inválido")
    versao = _versao(item["versao"])
    if item["id"] != id_item_atencao(item["chave_compromisso"], versao):
        raise ValueError("id não confere")
    if item["estado"] not in ESTADOS or item["acao"] not in (ENVIAR, ADIAR, SUPRIMIR):
        raise ValueError("estado ou ação desconhecidos")
    if not isinstance(item["motivo"], str):
        raise ValueError("motivo inválido")
    avaliado = datetime.fromisoformat(item["avaliado_em"])
    proxima = item["proxima_avaliacao"]
    proxima = None if proxima is None else datetime.fromisoformat(proxima)
    if avaliado.utcoffset() is None or (proxima is not None and proxima.utcoffset() is None):
        raise ValueError("datas sem fuso")
    estado, acao = item["estado"], item["acao"]
    coerente = (
        (estado == ESTADO_ABERTO and acao in (ENVIAR, ADIAR) and proxima is not None)
        or (estado == ESTADO_ENCERRADO and acao == SUPRIMIR and proxima is None)
        or (estado == ESTADO_ENVIADO and acao == ENVIAR and proxima is None)
    )
    if not coerente:
        raise ValueError("estado, ação e próxima avaliação incoerentes")
    return item["chave_compromisso"], versao, avaliado, proxima


def deve_gravar(existente: dict | None, novo: dict) -> bool:
    """Idempotência: não regride versão, não aceita avaliação mais antiga,
    não reabre item terminal da mesma versão e renova o agendamento quando a
    mesma decisão volta com `proxima_avaliacao` maior. Item malformado: False."""
    try:
        chave, versao, avaliado, proxima = _validar(novo)
        if existente is None:
            return True
        e_chave, e_versao, e_avaliado, e_proxima = _validar(existente)
        if e_chave != chave:
            return False
        if versao != e_versao:
            return versao > e_versao
        if existente["estado"] in ESTADOS_TERMINAIS or avaliado < e_avaliado:
            return False
        if (existente["estado"], existente["acao"], existente["motivo"]) != (
            novo["estado"], novo["acao"], novo["motivo"]
        ):
            return True
        return proxima is not None and (e_proxima is None or proxima > e_proxima)
    except (KeyError, TypeError, ValueError):
        return False
