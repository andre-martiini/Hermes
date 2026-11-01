"""Tratador HTTP do worker do runner (P08 do plano de autonomia, passos 2, 3 e 5).

Função pura: recebe cabeçalhos e corpo crus, autentica e devolve o status
HTTP que o Cloud Tasks vai interpretar. SEM I/O nem relógio escondido: a
verificação criptográfica do token (`verificar_token`, ex.: `google.oauth2.
id_token`) e a execução (`executar(request_id)`) são injetadas. Nada chama
este módulo em produção (shadow/off).

Ordem fail-closed: token -> claims -> `autorizar_chamada_worker` -> corpo ->
execução. Só DEPOIS de autenticar o corpo é lido; o corpo carrega apenas
`request_id` (o conteúdo vem do banco, passo 3). O worker termina logo
(passo 5): `executar` devolve um status tipado, nunca espera humano.

Atenção: o Cloud Tasks reenvia QUALQUER resposta não-2xx até o limite de
tentativas da fila (400/401/403/500 também); só 200 encerra a tarefa.

Status HTTP: 200 = nada a repetir (concluído, aguardando, pausado, falha
final); 503 = retentar (o Cloud Tasks reenvia); 401/403 = não autenticado/
autorizado; 400 = corpo inválido; 500 = exceção inesperada. Mensagens são
códigos fixos: nunca ecoam token, corpo nem texto de exceção.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from autonomy.pedido_repositorio import _validar_id_documento
from autonomy.runner import StatusRunner
from autonomy.worker_auth import ConfigWorker, autorizar_chamada_worker

MAX_CORPO_BYTES = 4096


@dataclass(frozen=True)
class RespostaWorker:
    status_http: int
    codigo: str


def _resp(status: int, codigo: str) -> RespostaWorker:
    return RespostaWorker(status, codigo)


def _bearer(headers: Mapping[Any, Any]) -> str | None:
    for chave, valor in headers.items():
        if isinstance(chave, str) and chave.lower() == "authorization":
            if isinstance(valor, str) and valor.startswith("Bearer "):
                token = valor[len("Bearer "):]
                if token and token == token.strip():
                    return token
            return None
    return None


def _request_id(corpo: object) -> str | None:
    if isinstance(corpo, str):
        corpo = corpo.encode("utf-8", errors="strict") if corpo.isascii() else None
    if not isinstance(corpo, (bytes, bytearray)) or not corpo or len(corpo) > MAX_CORPO_BYTES:
        return None
    try:
        dados = json.loads(bytes(corpo).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(dados, dict) or set(dados) != {"request_id"}:
        return None
    try:
        rid = _validar_id_documento(dados["request_id"], "request_id")
    except ValueError:
        return None
    return rid if rid.isascii() else None  # ids do dispatcher são ASCII; mesma regra para qualquer forma do JSON


def processar_chamada_worker(
    headers: object,
    corpo: object,
    config: ConfigWorker,
    agora: datetime,
    verificar_token: Callable[[str], Mapping[str, Any]],
    executar: Callable[[str], StatusRunner],
) -> RespostaWorker:
    if not isinstance(agora, datetime) or agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("agora deve ser datetime com fuso.")  # bug do chamador, antes de verificar o token
    if not isinstance(headers, Mapping):
        return _resp(401, "sem_token")
    try:
        token = _bearer(headers)
    except Exception:  # noqa: BLE001 - cabeçalhos hostis
        return _resp(401, "sem_token")
    if token is None:
        return _resp(401, "sem_token")
    try:
        claims = verificar_token(token)
    except Exception:  # noqa: BLE001 - qualquer falha de verificação nega
        return _resp(401, "token_invalido")
    try:
        decisao = autorizar_chamada_worker(claims, headers, config, agora)
    except Exception:  # noqa: BLE001 - claims/config hostis negam
        return _resp(403, "autorizacao_invalida")
    if not decisao.autorizado:
        return _resp(403, decisao.motivo)
    request_id = _request_id(corpo)
    if request_id is None:
        return _resp(400, "corpo_invalido")
    try:
        status = executar(request_id)
    except Exception:  # noqa: BLE001 - texto da exceção nunca vaza
        return _resp(500, "erro_execucao")
    if not isinstance(status, StatusRunner):
        return _resp(500, "status_invalido")
    if status is StatusRunner.RETENTAR:
        return _resp(503, "retentar")
    return _resp(200, status.value)
