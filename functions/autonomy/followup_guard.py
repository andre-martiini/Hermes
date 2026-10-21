"""Revalidação antes de follow-up (P07 do plano de autonomia, passo 7).

Lógica pura -- sem I/O e sem wiring. Antes de qualquer follow-up automático de
um compromisso, confere (nesta ordem de cautela): estado do compromisso, item
de atenção já tratado pelo dono, rascunho existente, intervenção humana
posterior e novo dado da contraparte. Na dúvida (contexto ausente ou
malformado) NUNCA envia: adia.

Reaproveita `autonomy/cumprimento.py` para saber se a intervenção humana já
cumpriu a promessa. Só o cumprimento firme suprime; qualquer outra
intervenção apenas adia para o dono/avaliador revisar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from autonomy.cumprimento import CUMPRIDO, avaliar_cumprimento

ENVIAR = "enviar"
ADIAR = "adiar"
SUPRIMIR = "suprimir"

ESTADOS_COMPROMISSO_ATIVOS = ("aberta", "vencida")
ESTADOS_ATENCAO_FECHADOS = ("resolvido", "descartado")
ESTADOS_ATENCAO_EM_TRATAMENTO = ("delegado_ao_agente", "aguardando_andre")
ESTADOS_ATENCAO_ABERTOS = (None, "aberto")


@dataclass(frozen=True)
class DecisaoFollowup:
    acao: str
    motivo: str


def _dt(valor) -> datetime | None:
    if not isinstance(valor, datetime):
        return None
    try:
        if valor.utcoffset() is None:
            return None
        return valor.astimezone(timezone.utc)
    except Exception:
        return None


def revalidar_followup(compromisso, contexto) -> DecisaoFollowup:
    """Rede de segurança: qualquer exceção inesperada adia, nunca envia."""
    try:
        return _revalidar(compromisso, contexto)
    except Exception:
        return DecisaoFollowup(ADIAR, "erro_interno")


def _revalidar(compromisso, contexto) -> DecisaoFollowup:
    """`compromisso`: dict com `texto`, `prometido_em` (datetime com fuso) e
    `estado`. `contexto`: dict com `mensagens` (lista de dicts com `from_me`,
    `timestamp`, `content`, `media` -- mensagens do chat, qualquer ordem),
    `rascunho_pendente` (bool) e `estado_atencao` (str ou None). Mensagens
    com timestamp >= `prometido_em` contam como posteriores (resolução de
    segundos), exceto a própria promessa (`wa_message_id` == `mensagem_id` no
    mesmo instante). Vencimento (`vence_em` <= agora) NÃO é checado aqui: é
    do chamador, e `prometido_em` deve ser o horário da mensagem da promessa.
    Retorna ENVIAR só quando nada impede; o resto é SUPRIMIR ou ADIAR."""
    if not isinstance(compromisso, dict) or not isinstance(contexto, dict):
        return DecisaoFollowup(ADIAR, "contexto_invalido")
    estado = compromisso.get("estado")
    if not isinstance(estado, str) or estado not in ESTADOS_COMPROMISSO_ATIVOS:
        return DecisaoFollowup(SUPRIMIR, "compromisso_encerrado")
    prometido_em = _dt(compromisso.get("prometido_em"))
    mensagens = contexto.get("mensagens")
    if (
        prometido_em is None
        or not isinstance(mensagens, list)
        or not isinstance(compromisso.get("texto"), str)
    ):
        return DecisaoFollowup(ADIAR, "contexto_invalido")
    if not isinstance(contexto.get("rascunho_pendente"), bool):
        return DecisaoFollowup(ADIAR, "contexto_invalido")

    if "estado_atencao" not in contexto:
        return DecisaoFollowup(ADIAR, "contexto_invalido")
    estado_atencao = contexto["estado_atencao"]
    if estado_atencao is not None and not isinstance(estado_atencao, str):
        return DecisaoFollowup(ADIAR, "contexto_invalido")
    if estado_atencao in ESTADOS_ATENCAO_FECHADOS:
        return DecisaoFollowup(SUPRIMIR, "dono_ja_tratou")
    if estado_atencao in ESTADOS_ATENCAO_EM_TRATAMENTO:
        return DecisaoFollowup(ADIAR, "atencao_em_tratamento")
    if estado_atencao not in ESTADOS_ATENCAO_ABERTOS:
        return DecisaoFollowup(ADIAR, "contexto_invalido")
    if contexto["rascunho_pendente"]:
        return DecisaoFollowup(SUPRIMIR, "rascunho_existente")

    base = prometido_em.replace(microsecond=0)
    posteriores = []
    for m in mensagens:
        if not isinstance(m, dict):
            return DecisaoFollowup(ADIAR, "contexto_invalido")
        ts = _dt(m.get("timestamp"))
        if ts is None or not isinstance(m.get("from_me"), bool):
            return DecisaoFollowup(ADIAR, "contexto_invalido")
        wa_id = m.get("wa_message_id")
        propria = (
            m["from_me"]
            and isinstance(wa_id, str) and wa_id != ""
            and wa_id == compromisso.get("mensagem_id")
            and ts.replace(microsecond=0) == base
        )
        if ts.replace(microsecond=0) >= base and not propria:
            posteriores.append((ts, m))
    posteriores.sort(key=lambda par: par[0])

    do_dono = [m for _, m in posteriores if m["from_me"]]
    for m in do_dono:
        media = m.get("media")
        nome = media.get("filename") if isinstance(media, dict) else ""
        r = avaliar_cumprimento(
            compromisso.get("texto"), m.get("content"), bool(media),
            nome if isinstance(nome, str) else "",
        )
        if r.estado == CUMPRIDO and not r.incerta:
            return DecisaoFollowup(SUPRIMIR, "ja_cumprido")
    if do_dono:
        return DecisaoFollowup(ADIAR, "intervencao_humana")
    if any(not m["from_me"] for _, m in posteriores):
        return DecisaoFollowup(ADIAR, "novo_dado_da_contraparte")
    return DecisaoFollowup(ENVIAR, "sem_impedimento")
