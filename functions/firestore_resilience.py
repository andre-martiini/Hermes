"""Políticas explícitas para streams Firestore sujeitos a interrupções."""

from __future__ import annotations

from google.api_core import exceptions as core_exceptions
from google.api_core import retry as retries


# O retry DEFAULT de google-cloud-firestore 2.28.0 tenta acessar `_retry`
# diretamente no objeto gRPC `run_query` depois de uma interrupção do stream.
# Esse atributo não existe em `_UnaryStreamMultiCallable`. Passar um Retry
# concreto evita esse caminho defeituoso e permite que Query.stream retome a
# leitura a partir do último snapshot recebido.
FIRESTORE_STREAM_RETRY = retries.Retry(
    initial=0.2,
    maximum=15.0,
    multiplier=1.5,
    predicate=retries.if_exception_type(
        core_exceptions.DeadlineExceeded,
        core_exceptions.InternalServerError,
        core_exceptions.ResourceExhausted,
        core_exceptions.ServiceUnavailable,
    ),
    timeout=180.0,
)


def stream_collection_resilient(collection_ref, *, timeout: float = 60.0):
    """Abre um stream com retry explícito, sem depender do retry GAPIC quebrado."""
    return collection_ref.stream(retry=FIRESTORE_STREAM_RETRY, timeout=timeout)
