"""Serialização do pedido durável (P08, wiring de persistência, passo 4).

Funções puras, sem I/O: `pedido_para_dict` devolve um dict só com tipos que o
Firestore e o JSON aceitam (str, int, bool, None, dict, list; instantes em
ISO-8601 UTC) e `pedido_de_dict` reconstrói o `PedidoDuravel` validando tudo.
O wiring de persistência (CAS por geração/status) grava e lê este documento.

- Tolerante na escrita, estrito na leitura: documento com chave desconhecida
  ou ausente, tipo errado (`bool` onde se espera `int`), instante sem fuso ou
  status desconhecido levanta `ValueError`. Nunca preenche valor por padrão
  silenciosamente: um pedido lido pela metade poderia reabrir um efeito já
  feito.
- `resultado` e `dados` de checkpoint saem como `dict`/`list` mutáveis (a
  forma imutável do domínio não existe no documento) e voltam congelados
  pelos próprios construtores.
- Round-trip: `pedido_de_dict(pedido_para_dict(p)) == p` para todo pedido
  válido (instantes comparam iguais mesmo normalizados para UTC).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

from autonomy.execution import PedidoDuravel
from autonomy.ledger import Checkpoint, LedgerEntry, _serializar_canonico
from autonomy.requests import Lease, RequestStatus
from autonomy.runs import AgentRun, AgentRunStatus

VERSAO_SCHEMA = 1

_CHAVES_PEDIDO = frozenset({
    "versao", "request_id", "status", "lease", "ledger_entry", "run",
    "tentativas", "proximo_tentativa_em", "pausas", "condicao_espera",
})
_CHAVES_LEASE = frozenset({"lease_token", "generation", "executor_id", "expires_at"})
_CHAVES_LEDGER = frozenset({
    "idempotency_key", "payload_hash", "criado_em", "checkpoints",
    "resultado", "resultado_registrado_em",
})
_CHAVES_CHECKPOINT = frozenset({"sequencia", "dados", "criado_em"})
_CHAVES_RUN = frozenset({
    "run_id", "request_id", "executor_id", "lease_token", "generation",
    "status", "iniciado_em", "finalizado_em", "resultado",
})


def _json_mutavel(valor: Any) -> Any:
    """Cópia profunda em dict/list/escalares (descongela MappingProxyType/tuple)."""
    return json.loads(_serializar_canonico(valor))


def _instante_para_str(valor: datetime | None) -> str | None:
    if valor is None:
        return None
    return valor.astimezone(timezone.utc).isoformat()


def _exigir_mapa(valor: Any, nome: str, chaves: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(valor, Mapping):
        raise ValueError(f"{nome}: esperado objeto, recebido {type(valor).__name__}.")
    if any(not isinstance(k, str) for k in valor):
        raise ValueError(f"{nome}: chaves devem ser str.")
    faltando = chaves - set(valor)
    extras = set(valor) - chaves
    if faltando or extras:
        raise ValueError(
            f"{nome}: chaves inválidas (faltando={sorted(faltando)}, extras={sorted(extras)})."
        )
    return valor


def _exigir_str(valor: Any, nome: str) -> str:
    if not isinstance(valor, str):
        raise ValueError(f"{nome}: esperado str.")
    return valor


def _exigir_int(valor: Any, nome: str) -> int:
    if type(valor) is not int:
        raise ValueError(f"{nome}: esperado int.")
    return valor


def _instante_de_str(valor: Any, nome: str) -> datetime:
    if not isinstance(valor, str):
        raise ValueError(f"{nome}: esperado instante ISO-8601 em str.")
    try:
        dt = datetime.fromisoformat(valor)
    except ValueError as exc:
        raise ValueError(f"{nome}: instante inválido.") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{nome}: instante sem fuso.")
    return dt


def _instante_opcional(valor: Any, nome: str) -> datetime | None:
    return None if valor is None else _instante_de_str(valor, nome)


def _json_puro(valor: Any, nome: str) -> Any:
    """Valida que o valor lido é JSON puro (sem NaN/Infinity) e o devolve."""
    try:
        return json.loads(json.dumps(valor, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{nome}: valor não é JSON puro.") from exc


def pedido_para_dict(pedido: PedidoDuravel) -> dict[str, Any]:
    if not isinstance(pedido, PedidoDuravel):
        raise TypeError("pedido deve ser PedidoDuravel.")
    lease = pedido.lease
    entrada = pedido.ledger_entry
    run = pedido.run
    return {
        "versao": VERSAO_SCHEMA,
        "request_id": pedido.request_id,
        "status": RequestStatus(pedido.status).value,
        "lease": None if lease is None else {
            "lease_token": lease.lease_token,
            "generation": lease.generation,
            "executor_id": lease.executor_id,
            "expires_at": _instante_para_str(lease.expires_at),
        },
        "ledger_entry": None if entrada is None else {
            "idempotency_key": entrada.idempotency_key,
            "payload_hash": entrada.payload_hash,
            "criado_em": _instante_para_str(entrada.criado_em),
            "checkpoints": [
                {
                    "sequencia": c.sequencia,
                    "dados": _json_mutavel(c.dados),
                    "criado_em": _instante_para_str(c.criado_em),
                }
                for c in entrada.checkpoints
            ],
            "resultado": _json_mutavel(entrada.resultado),
            "resultado_registrado_em": _instante_para_str(entrada.resultado_registrado_em),
        },
        "run": None if run is None else {
            "run_id": run.run_id,
            "request_id": run.request_id,
            "executor_id": run.executor_id,
            "lease_token": run.lease_token,
            "generation": run.generation,
            "status": AgentRunStatus(run.status).value,
            "iniciado_em": _instante_para_str(run.iniciado_em),
            "finalizado_em": _instante_para_str(run.finalizado_em),
            "resultado": _json_mutavel(run.resultado),
        },
        "tentativas": pedido.tentativas,
        "proximo_tentativa_em": _instante_para_str(pedido.proximo_tentativa_em),
        "pausas": pedido.pausas,
        "condicao_espera": pedido.condicao_espera,
    }


def _lease_de_dict(d: Any) -> Lease:
    m = _exigir_mapa(d, "lease", _CHAVES_LEASE)
    return Lease(
        lease_token=_exigir_str(m["lease_token"], "lease.lease_token"),
        generation=_exigir_int(m["generation"], "lease.generation"),
        executor_id=_exigir_str(m["executor_id"], "lease.executor_id"),
        expires_at=_instante_de_str(m["expires_at"], "lease.expires_at"),
    )


def _ledger_de_dict(d: Any) -> LedgerEntry:
    m = _exigir_mapa(d, "ledger_entry", _CHAVES_LEDGER)
    cps = m["checkpoints"]
    if not isinstance(cps, list):
        raise ValueError("ledger_entry.checkpoints: esperado lista.")
    checkpoints = []
    for i, c in enumerate(cps):
        mc = _exigir_mapa(c, f"checkpoints[{i}]", _CHAVES_CHECKPOINT)
        if not isinstance(mc["dados"], Mapping):
            raise ValueError(f"checkpoints[{i}].dados: esperado objeto.")
        checkpoints.append(Checkpoint(
            sequencia=_exigir_int(mc["sequencia"], f"checkpoints[{i}].sequencia"),
            dados=_json_puro(mc["dados"], f"checkpoints[{i}].dados"),
            criado_em=_instante_de_str(mc["criado_em"], f"checkpoints[{i}].criado_em"),
        ))
    return LedgerEntry(
        idempotency_key=_exigir_str(m["idempotency_key"], "ledger_entry.idempotency_key"),
        payload_hash=_exigir_str(m["payload_hash"], "ledger_entry.payload_hash"),
        criado_em=_instante_de_str(m["criado_em"], "ledger_entry.criado_em"),
        checkpoints=tuple(checkpoints),
        resultado=_json_puro(m["resultado"], "ledger_entry.resultado"),
        resultado_registrado_em=_instante_opcional(
            m["resultado_registrado_em"], "ledger_entry.resultado_registrado_em"
        ),
    )


def _run_de_dict(d: Any) -> AgentRun:
    m = _exigir_mapa(d, "run", _CHAVES_RUN)
    try:
        status = AgentRunStatus(_exigir_str(m["status"], "run.status"))
    except ValueError as exc:
        raise ValueError("run.status: desconhecido.") from exc
    return AgentRun(
        run_id=_exigir_str(m["run_id"], "run.run_id"),
        request_id=_exigir_str(m["request_id"], "run.request_id"),
        executor_id=_exigir_str(m["executor_id"], "run.executor_id"),
        lease_token=_exigir_str(m["lease_token"], "run.lease_token"),
        generation=_exigir_int(m["generation"], "run.generation"),
        status=status,
        iniciado_em=_instante_de_str(m["iniciado_em"], "run.iniciado_em"),
        finalizado_em=_instante_opcional(m["finalizado_em"], "run.finalizado_em"),
        resultado=_json_puro(m["resultado"], "run.resultado"),
    )


def pedido_de_dict(documento: Any) -> PedidoDuravel:
    m = _exigir_mapa(documento, "pedido", _CHAVES_PEDIDO)
    if _exigir_int(m["versao"], "versao") != VERSAO_SCHEMA:
        raise ValueError("versao: schema não suportado.")
    try:
        status = RequestStatus(_exigir_str(m["status"], "status"))
    except ValueError as exc:
        raise ValueError("status: desconhecido.") from exc
    return PedidoDuravel(
        request_id=_exigir_str(m["request_id"], "request_id"),
        status=status,
        lease=None if m["lease"] is None else _lease_de_dict(m["lease"]),
        ledger_entry=None if m["ledger_entry"] is None else _ledger_de_dict(m["ledger_entry"]),
        run=None if m["run"] is None else _run_de_dict(m["run"]),
        tentativas=_exigir_int(m["tentativas"], "tentativas"),
        proximo_tentativa_em=_instante_opcional(m["proximo_tentativa_em"], "proximo_tentativa_em"),
        pausas=_exigir_int(m["pausas"], "pausas"),
        condicao_espera=_exigir_str(m["condicao_espera"], "condicao_espera"),
    )
