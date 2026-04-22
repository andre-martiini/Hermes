import json
import time
import uuid
from contextvars import ContextVar

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def generate_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def set_trace_id(trace_id: str):
    _trace_id_var.set(trace_id)


def get_trace_id() -> str:
    return _trace_id_var.get()


def log(level: str, message: str, **kwargs):
    entry = {
        "severity": level.upper(),
        "trace_id": get_trace_id(),
        "message": message,
        "ts": time.time(),
        **kwargs,
    }
    print(json.dumps(entry, ensure_ascii=False, default=str))
