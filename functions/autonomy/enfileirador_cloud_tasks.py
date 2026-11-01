"""Enfileirador Cloud Tasks do dispatcher (P08, passos 2 e 3): adaptador fino e testável.

`criar_enfileirador(cliente, config)` devolve o `enfileirar(nome, payload)` que `executar_ciclo`
espera. O cliente (`google.cloud.tasks_v2.CloudTasksClient` ou duplo) é INJETADO: este módulo não
importa nem cria cliente, não lê ambiente e nada o chama em produção (dispatcher em off/shadow).

- a tarefa é um POST HTTP com corpo JSON só com o `request_id` (o conteúdo é recuperado do banco
  depois de autenticar) e token OIDC da identidade de serviço, com `audience` = URL do worker, o
  que o `worker_auth` exige;
- o nome da tarefa (determinístico, vindo do dispatcher) vira o nome completo no Cloud Tasks, o que
  dá idempotência: nome repetido responde ALREADY_EXISTS, traduzido para `JaDespachado`;
- qualquer outra falha propaga (o ciclo a trata como resultado ambíguo, sem estorno);
- ALREADY_EXISTS também vale para nome recém-executado/deletado (reservado ~1h): o nome inclui
  tentativa e geração para nunca ser reutilizado num redespacho legítimo;
- config ou argumentos inválidos levantam ValueError: fail-closed, nada é enviado.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

from autonomy.ciclo_dispatcher import JaDespachado
from autonomy.pedido_repositorio import _validar_id_documento

_NOME_VALIDO = re.compile(r"^[A-Za-z0-9_-]{1,500}$")


@dataclass(frozen=True)
class ConfigCloudTasks:
    projeto: str
    regiao: str
    fila: str
    url_worker: str
    service_account_email: str


def _texto(v: object) -> bool:
    return isinstance(v, str) and bool(v) and "/" not in v and not re.search(r"\s", v)


def _ja_existe(exc: BaseException) -> bool:
    """ALREADY_EXISTS sem depender de importar google.api_core (compara pela classe/código)."""
    for cls in type(exc).__mro__:
        if cls.__name__ == "AlreadyExists":
            return True
    return getattr(exc, "grpc_status_code", None) is not None and "ALREADY_EXISTS" in str(
        getattr(exc, "grpc_status_code")
    )


def criar_enfileirador(cliente: Any, config: ConfigCloudTasks) -> Callable[[str, dict[str, str]], None]:
    if not isinstance(config, ConfigCloudTasks):
        raise ValueError("config deve ser ConfigCloudTasks.")
    for campo in ("projeto", "regiao", "fila", "service_account_email"):
        if not _texto(getattr(config, campo)):
            raise ValueError(f"config.{campo} inválido.")
    if not (isinstance(config.url_worker, str) and config.url_worker.startswith("https://")
            and not re.search(r"\s", config.url_worker) and urlparse(config.url_worker).netloc):
        raise ValueError("config.url_worker deve ser https.")
    if not callable(getattr(cliente, "create_task", None)):
        raise ValueError("cliente precisa de create_task.")
    pai = f"projects/{config.projeto}/locations/{config.regiao}/queues/{config.fila}"

    def enfileirar(nome: str, payload: dict[str, str]) -> None:
        if not isinstance(nome, str) or not _NOME_VALIDO.fullmatch(nome):
            raise ValueError("nome de tarefa inválido.")
        if not isinstance(payload, dict) or set(payload) != {"request_id"}:
            raise ValueError("payload deve ter somente request_id.")
        # Mesma regra do repositório: todo pedido persistido é enfileirável (corpo JSON escapa o resto).
        _validar_id_documento(payload["request_id"], "request_id")
        tarefa = {
            "name": f"{pai}/tasks/{nome}",
            "http_request": {
                "http_method": "POST",
                "url": config.url_worker,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"request_id": payload["request_id"]}).encode("utf-8"),
                "oidc_token": {
                    "service_account_email": config.service_account_email,
                    "audience": config.url_worker,
                },
            },
        }
        try:
            cliente.create_task(request={"parent": pai, "task": tarefa})
        except Exception as exc:
            if _ja_existe(exc):
                raise JaDespachado(nome) from exc
            raise

    return enfileirar
