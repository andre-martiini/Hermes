"""Telemetria de custo do Firestore: conta leituras e escritas por Cloud Function.

Contexto (DEV-2026-0003, Issue #203): Firestore Read Ops foi o maior item da
fatura de agosto/2026 (26,5 M leituras em 30 dias, ~885 mil/dia) e a fatura
não diz QUEM lê. Este módulo intercepta os métodos do SDK que geram operações
cobradas e acumula contadores em memória, agregando por:

- ``services.<k_service>`` — nome do serviço Cloud Run (= nome da function,
  variável ``K_SERVICE`` do gen2);
- ``collections.<colecao_raiz>`` — coleção de primeiro nível do caminho.

Os contadores são descarregados (``flush``) em UM ``set(merge=True)`` com
``Increment`` no documento ``system_usage/firestore/daily/{YYYY-MM-DD}``,
no máximo a cada ``FLUSH_INTERVAL_S`` segundos ou ``FLUSH_OPS_THRESHOLD``
operações por instância — ou seja, o custo da própria telemetria é de
~1 escrita/minuto por instância ativa, contra as ~83 mil escritas/dia atuais.

Regras de contagem (espelham a cobrança do Firestore):
- ``DocumentReference.get`` → 1 leitura, exista o documento ou não;
- ``Query.stream`` (cobre ``Query.get``, ``CollectionReference.stream/get``)
  → 1 leitura por documento devolvido, mínimo 1 por consulta;
- ``Client.get_all`` (cobre ``Transaction.get/get_all``) → 1 leitura por
  referência;
- ``DocumentReference.set/update/delete/create`` (cobre
  ``CollectionReference.add``) → 1 escrita cada;
- ``WriteBatch.commit`` e ``Transaction._commit`` (usado por
  ``@transactional``) → 1 escrita por operação do lote, atribuída à coleção
  de cada documento.

O que NÃO é medido: leituras do frontend (110 listeners ``onSnapshot``) e das
functions Node — a diferença entre o total faturado e a soma aqui medida é a
estimativa desses dois. Escritas do próprio ``flush`` são excluídas.

Desligar: ``HERMES_FIRESTORE_METRICS=0``. O hook nunca deixa uma exceção
própria escapar para o código de negócio — em caso de erro interno, apenas
não conta.
"""

from __future__ import annotations

import atexit
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

FLUSH_INTERVAL_S = int(os.environ.get("HERMES_FIRESTORE_METRICS_FLUSH_S", "60"))
FLUSH_OPS_THRESHOLD = int(os.environ.get("HERMES_FIRESTORE_METRICS_FLUSH_OPS", "2000"))
USAGE_DOC = ("system_usage", "firestore")
DAILY_SUBCOLLECTION = "daily"

_lock = threading.RLock()
_internal = threading.local()  # marca operações do próprio flush (não contadas)
_installed = False
_state: dict[str, Any] = {
    "reads": 0,
    "writes": 0,
    "queries": 0,
    "collections": {},  # nome -> {"reads": n, "writes": n}
    "pending_ops": 0,
    "last_flush": time.monotonic(),
}
_client_factory = None  # injetável nos testes


# --------------------------------------------------------------------------- #
# Identificação e sanitização
# --------------------------------------------------------------------------- #
def service_name() -> str:
    """Nome da function em execução (serviço Cloud Run gen2)."""
    raw = (
        os.environ.get("K_SERVICE")
        or os.environ.get("FUNCTION_TARGET")
        or os.environ.get("FUNCTION_NAME")
        or "unknown"
    )
    return safe_key(raw)


def safe_key(value: Any) -> str:
    """Chave segura para campo Firestore (sem pontos, hifens, barras...)."""
    key = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "unknown")).strip("_")
    return (key or "unknown")[:80]


def top_collection(ref: Any) -> str:
    """Coleção de primeiro nível de um DocumentReference/CollectionReference/Query."""
    try:
        path = getattr(ref, "_path", None)
        if path is None:
            parent = getattr(ref, "_parent", None)  # Query -> CollectionReference
            path = getattr(parent, "_path", None)
        if path is None:
            return "unknown"
        if isinstance(path, str):
            return safe_key(path.split("/")[0])
        return safe_key(path[0]) if len(path) else "unknown"
    except Exception:
        return "unknown"


# --------------------------------------------------------------------------- #
# Contagem
# --------------------------------------------------------------------------- #
def _is_internal() -> bool:
    return bool(getattr(_internal, "active", False))


def _bump(kind: str, collection: str, n: int = 1) -> None:
    if n <= 0 or _is_internal():
        return
    with _lock:
        _state[kind] = _state.get(kind, 0) + n
        col = _state["collections"].setdefault(collection, {"reads": 0, "writes": 0})
        if kind in ("reads", "writes"):
            col[kind] += n
        _state["pending_ops"] += n
        due = (
            _state["pending_ops"] >= FLUSH_OPS_THRESHOLD
            or (time.monotonic() - _state["last_flush"]) >= FLUSH_INTERVAL_S
        )
    if due:
        flush()


def count_read(ref: Any, n: int = 1) -> None:
    _bump("reads", top_collection(ref), n)


def count_write(ref: Any, n: int = 1) -> None:
    _bump("writes", top_collection(ref), n)


def count_query(ref: Any) -> None:
    _bump("queries", top_collection(ref), 1)


def snapshot() -> dict[str, Any]:
    """Cópia dos contadores acumulados desde o último flush (para testes/depuração)."""
    with _lock:
        return {
            "reads": _state["reads"],
            "writes": _state["writes"],
            "queries": _state["queries"],
            "collections": {k: dict(v) for k, v in _state["collections"].items()},
            "pending_ops": _state["pending_ops"],
        }


def _reset_locked() -> dict[str, Any]:
    data = {
        "reads": _state["reads"],
        "writes": _state["writes"],
        "queries": _state["queries"],
        "collections": _state["collections"],
    }
    _state["reads"] = _state["writes"] = _state["queries"] = 0
    _state["collections"] = {}
    _state["pending_ops"] = 0
    _state["last_flush"] = time.monotonic()
    return data


# --------------------------------------------------------------------------- #
# Flush
# --------------------------------------------------------------------------- #
def build_flush_payload(data: dict[str, Any], service: str, now: datetime) -> dict[str, Any]:
    """Monta o payload de Increment para ``set(merge=True)``.

    Estrutura do documento diário::

        total:       {reads, writes, queries}
        services:    {<function>: {reads, writes, queries}}
        collections: {<colecao>: {reads, writes}}
        updated_at:  ISO-8601
    """
    from google.cloud.firestore_v1 import Increment

    payload: dict[str, Any] = {
        "total": {
            "reads": Increment(int(data["reads"])),
            "writes": Increment(int(data["writes"])),
            "queries": Increment(int(data["queries"])),
        },
        "services": {
            service: {
                "reads": Increment(int(data["reads"])),
                "writes": Increment(int(data["writes"])),
                "queries": Increment(int(data["queries"])),
            }
        },
        "updated_at": now.isoformat(),
    }
    collections = {}
    for name, counts in (data.get("collections") or {}).items():
        collections[safe_key(name)] = {
            "reads": Increment(int(counts.get("reads", 0))),
            "writes": Increment(int(counts.get("writes", 0))),
        }
    if collections:
        payload["collections"] = collections
    return payload


def _get_client():
    if _client_factory is not None:
        return _client_factory()
    from firebase_admin import firestore

    return firestore.client()


def flush() -> bool:
    """Grava os contadores acumulados. Retorna True se houve algo a gravar."""
    with _lock:
        if _state["pending_ops"] <= 0:
            _state["last_flush"] = time.monotonic()
            return False
        data = _reset_locked()
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    _internal.active = True
    try:
        db = _get_client()
        ref = (
            db.collection(USAGE_DOC[0])
            .document(USAGE_DOC[1])
            .collection(DAILY_SUBCOLLECTION)
            .document(day)
        )
        ref.set(build_flush_payload(data, service_name(), now), merge=True)
        return True
    except Exception as exc:  # telemetria nunca derruba a function
        print(f"[FirestoreMetrics] falha no flush ({service_name()}): {exc}")
        # devolve os contadores para tentar de novo no próximo ciclo
        with _lock:
            _state["reads"] += data["reads"]
            _state["writes"] += data["writes"]
            _state["queries"] += data["queries"]
            for name, counts in data["collections"].items():
                col = _state["collections"].setdefault(name, {"reads": 0, "writes": 0})
                col["reads"] += counts["reads"]
                col["writes"] += counts["writes"]
            _state["pending_ops"] += data["reads"] + data["writes"] + data["queries"]
        return False
    finally:
        _internal.active = False


# --------------------------------------------------------------------------- #
# Interceptação do SDK
# --------------------------------------------------------------------------- #
class _CountingStream:
    """Envelopa o StreamGenerator do SDK contando cada documento devolvido.

    Delegação transparente de atributos (``get_explain_metrics`` etc.) para o
    gerador original. Garante o mínimo de 1 leitura por consulta, como cobra o
    Firestore, mesmo quando a consulta não devolve nada.
    """

    def __init__(self, inner: Any, ref: Any):
        self._inner = inner
        self._ref = ref
        self._yielded = 0
        self._closed = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = next(self._inner)
        except StopIteration:
            self._finish()
            raise
        self._yielded += 1
        count_read(self._ref, 1)
        return item

    def _finish(self) -> None:
        if not self._closed:
            self._closed = True
            if self._yielded == 0:
                count_read(self._ref, 1)

    def close(self) -> None:
        self._finish()
        close = getattr(self._inner, "close", None)
        if callable(close):
            close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _wrap_doc_get(original):
    def get(self, *args, **kwargs):
        try:
            count_read(self, 1)
        except Exception:
            pass
        return original(self, *args, **kwargs)

    get.__wrapped_by_firestore_metrics__ = True
    return get


def _wrap_query_stream(original):
    def stream(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        try:
            count_query(self)
            return _CountingStream(result, self)
        except Exception:
            return result

    stream.__wrapped_by_firestore_metrics__ = True
    return stream


def _wrap_client_get_all(original):
    def get_all(self, references, *args, **kwargs):
        try:
            refs = list(references)
        except Exception:
            return original(self, references, *args, **kwargs)
        try:
            for ref in refs:
                count_read(ref, 1)
        except Exception:
            pass
        return original(self, refs, *args, **kwargs)

    get_all.__wrapped_by_firestore_metrics__ = True
    return get_all


def _wrap_doc_write(original):
    def write(self, *args, **kwargs):
        try:
            count_write(self, 1)
        except Exception:
            pass
        return original(self, *args, **kwargs)

    write.__wrapped_by_firestore_metrics__ = True
    return write


def _wrap_batch_commit(original):
    def commit(self, *args, **kwargs):
        try:
            _count_batch_writes(self)
        except Exception:
            pass
        return original(self, *args, **kwargs)

    commit.__wrapped_by_firestore_metrics__ = True
    return commit


def _count_batch_writes(batch: Any) -> None:
    """Conta as escritas de um lote/transação, atribuídas por coleção.

    ``_document_references`` (caminho -> referência) permite atribuir cada
    documento à sua coleção raiz; ``_write_pbs`` é a quantidade cobrada (um
    documento pode ter mais de uma escrita no mesmo lote).
    """
    pbs = getattr(batch, "_write_pbs", None) or []
    total = len(pbs)
    if not total:
        return
    refs = list((getattr(batch, "_document_references", None) or {}).values())
    if not refs:
        _bump("writes", "batch", total)
        return
    per_ref = max(1, total // len(refs))
    remaining = total
    for i, ref in enumerate(refs):
        n = remaining if i == len(refs) - 1 else per_ref
        remaining -= n
        if n > 0:
            count_write(ref, n)


def install() -> bool:
    """Instala os hooks no SDK (idempotente). Retorna True se ativo."""
    global _installed
    if _installed:
        return True
    if os.environ.get("HERMES_FIRESTORE_METRICS", "1") == "0":
        return False
    try:
        from google.cloud.firestore_v1 import Client, DocumentReference, Query, Transaction, WriteBatch
    except Exception as exc:
        print(f"[FirestoreMetrics] SDK indisponível, hook não instalado: {exc}")
        return False

    def _patch(cls, name, wrapper):
        current = getattr(cls, name)
        if getattr(current, "__wrapped_by_firestore_metrics__", False):
            return
        setattr(cls, name, wrapper(current))

    _patch(DocumentReference, "get", _wrap_doc_get)
    _patch(Query, "stream", _wrap_query_stream)
    _patch(Client, "get_all", _wrap_client_get_all)
    for name in ("set", "update", "delete", "create"):
        _patch(DocumentReference, name, _wrap_doc_write)
    _patch(WriteBatch, "commit", _wrap_batch_commit)
    # O decorador @transactional não chama .commit(): usa Transaction._commit().
    if hasattr(Transaction, "_commit"):
        _patch(Transaction, "_commit", _wrap_batch_commit)

    atexit.register(_flush_quiet)
    _start_background_flusher()
    _installed = True
    return True


def _flush_quiet() -> None:
    try:
        flush()
    except Exception:
        pass


def _start_background_flusher() -> None:
    """Thread daemon que descarrega contadores parados (instância ociosa)."""

    def loop():
        while True:
            time.sleep(max(15, FLUSH_INTERVAL_S // 2))
            with _lock:
                due = (
                    _state["pending_ops"] > 0
                    and (time.monotonic() - _state["last_flush"]) >= FLUSH_INTERVAL_S
                )
            if due:
                _flush_quiet()

    t = threading.Thread(target=loop, name="firestore-metrics-flusher", daemon=True)
    t.start()


# --------------------------------------------------------------------------- #
# Leitura agregada (usada pelo relatório diário — PR 1)
# --------------------------------------------------------------------------- #
def read_daily_usage(db, day: str) -> dict[str, Any] | None:
    """Lê ``system_usage/firestore/daily/{day}`` e devolve o dict ou None."""
    snap = (
        db.collection(USAGE_DOC[0])
        .document(USAGE_DOC[1])
        .collection(DAILY_SUBCOLLECTION)
        .document(day)
        .get()
    )
    if not getattr(snap, "exists", False):
        return None
    return snap.to_dict() or {}


def format_daily_summary(data: dict[str, Any], top_n: int = 6) -> list[str]:
    """Linhas prontas para o Telegram (HTML) com os maiores consumidores."""
    total = data.get("total") or {}
    lines = [
        f"Firestore medido (backend): {int(total.get('reads') or 0):,} leituras | "
        f"{int(total.get('writes') or 0):,} escritas | {int(total.get('queries') or 0):,} consultas".replace(",", "."),
    ]
    services = data.get("services") or {}
    if services:
        lines.append("Top functions por leitura:")
        ranked = sorted(services.items(), key=lambda kv: -int((kv[1] or {}).get("reads") or 0))[:top_n]
        for name, counts in ranked:
            lines.append(
                f"  • {name}: {int((counts or {}).get('reads') or 0):,} L / "
                f"{int((counts or {}).get('writes') or 0):,} E".replace(",", ".")
            )
    collections = data.get("collections") or {}
    if collections:
        lines.append("Top coleções por leitura:")
        ranked = sorted(collections.items(), key=lambda kv: -int((kv[1] or {}).get("reads") or 0))[:top_n]
        for name, counts in ranked:
            lines.append(f"  • {name}: {int((counts or {}).get('reads') or 0):,} L".replace(",", "."))
    return lines
