"""Autorização do worker do runner (P08 do plano de autonomia, passo 2).

Função pura: decide se uma chamada HTTP vinda do Cloud Tasks pode executar o
runner, a partir de claims de um token OIDC JÁ verificado (assinatura e
expiração conferidas pelo wiring, ex.: `google.oauth2.id_token`) e dos
cabeçalhos da tarefa. SEM I/O nem relógio escondido; fail-closed.

- só a identidade de serviço configurada (e-mail verificado) é aceita;
- `aud` precisa ser exatamente a URL configurada do worker;
- `iss` precisa ser o emissor do Google;
- `exp` é conferido de novo contra `agora` (defesa em profundidade);
- o cabeçalho `X-CloudTasks-QueueName` precisa ser a fila configurada (o
  Cloud Tasks o define e o remove de chamadas externas);
- config incompleta ou de tipo errado nunca autoriza.

O motivo da recusa é um código curto e fixo: nunca ecoa conteúdo do token.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

EMISSORES_GOOGLE = frozenset({"https://accounts.google.com", "accounts.google.com"})
HEADER_FILA = "x-cloudtasks-queuename"


@dataclass(frozen=True)
class ConfigWorker:
    service_account_email: str
    audience: str
    fila: str


@dataclass(frozen=True)
class DecisaoAuth:
    autorizado: bool
    motivo: str


def _negar(motivo: str) -> DecisaoAuth:
    return DecisaoAuth(False, motivo)


def _texto(valor: object) -> bool:
    return isinstance(valor, str) and bool(valor.strip()) and valor == valor.strip()


def autorizar_chamada_worker(
    claims: object,
    headers: object,
    config: object,
    agora: datetime,
) -> DecisaoAuth:
    if not isinstance(agora, datetime) or agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("agora deve ser datetime com fuso.")
    if not isinstance(config, ConfigWorker) or not all(
        _texto(v) for v in (config.service_account_email, config.audience, config.fila)
    ):
        return _negar("config_invalida")
    if not isinstance(claims, Mapping) or not claims:
        return _negar("sem_token")
    iss = claims.get("iss")
    if not isinstance(iss, str) or iss not in EMISSORES_GOOGLE:
        return _negar("emissor_invalido")
    if claims.get("aud") != config.audience:
        return _negar("audience_invalida")
    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        return _negar("exp_invalido")
    try:
        finito = math.isfinite(exp)
    except OverflowError:  # inteiro gigante não converte para float
        finito = False
    if not finito:
        return _negar("exp_invalido")
    if exp <= agora.astimezone(timezone.utc).timestamp():
        return _negar("token_expirado")
    if claims.get("email_verified") is not True:
        return _negar("email_nao_verificado")
    email = claims.get("email")
    if not isinstance(email, str) or not email.isascii() or email.lower() != config.service_account_email.lower():
        return _negar("identidade_nao_permitida")
    if not isinstance(headers, Mapping):
        return _negar("sem_cabecalhos")
    fila = None
    for chave, valor in headers.items():
        if isinstance(chave, str) and chave.lower() == HEADER_FILA:
            fila = valor
            break
    if fila != config.fila:
        return _negar("fila_invalida")
    return DecisaoAuth(True, "autorizado")
