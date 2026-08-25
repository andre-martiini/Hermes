"""Invoca Cloud Functions callable (`@https_fn.on_call`) de dentro do backend.

Generaliza o padrao que ja existia em `main.py::on_copilot_job_created`: uma
callable decorada com `@https_fn.on_call` empilha duas camadas preservadas por
`functools.wraps` (o wrapper de CORS e o `on_call_wrapped`), ambas esperando uma
requisicao HTTP bruta. `inspect.unwrap` percorre a cadeia de `__wrapped__` ate a
funcao original, que so precisa de um objeto com `.data` e `.auth`.

Isso permite expor callables ja existentes (confirmarEdicaoAcao,
confirmarEdicaoEmLote, ...) por outros canais — MCP inclusive — sem reimplementar
a logica delas nem mover codigo de `main.py`.
"""

from __future__ import annotations

import inspect


class CallableAuth:
    def __init__(self, uid: str | None, token: dict | None = None):
        self.uid = uid
        self.token = token or {}


class CallableRequestShim:
    """Suficiente para uma callable que le apenas `.data` e `.auth`.

    Callables que tocam `req.rawRequest` (headers, IP, App Check) nao sao
    invocaveis por aqui — o chamador deve conferir antes de expor uma callable
    nova por este caminho.
    """

    def __init__(self, data: dict, uid: str | None, token: dict | None = None):
        self.data = data or {}
        self.auth = CallableAuth(uid, token) if uid else None


def invoke_callable(fn, data: dict, *, uid: str | None, token: dict | None = None):
    """Executa a funcao original por tras de uma callable `@https_fn.on_call`.

    Levanta o que a callable levantar — inclusive `https_fn.HttpsError`, que o
    chamador deve traduzir para o protocolo do seu canal.
    """
    core_fn = inspect.unwrap(fn)
    return core_fn(CallableRequestShim(data, uid, token))
