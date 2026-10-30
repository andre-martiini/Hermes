"""Repositório Firestore do pedido durável (P08, passo 4: persistência/CAS).

Camada fina de I/O sobre `autonomy.pedido_serializacao`: o documento do
pedido vive em `autonomy_pedidos/{request_id}` como
`{"pedido": <pedido_para_dict>, "revisao": int}`. Toda mudança é um
read-modify-write numa transação do Firestore (CAS pelo próprio mecanismo
transacional): duas escritas concorrentes nunca se sobrescrevem -- a perdedora
é reexecutada sobre o estado novo. Nada aqui é chamado por produção ainda
(shadow/off): o wiring do worker virá numa sub-entrega seguinte.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from firebase_admin import firestore

from autonomy.execution import PedidoDuravel
from autonomy.pedido_serializacao import pedido_de_dict, pedido_para_dict, run_para_dict
from autonomy.runs import AgentRun

COLECAO_PEDIDOS = "autonomy_pedidos"
SUBCOLECAO_RUNS_ENCERRADOS = "runs_encerrados"


class PedidoJaExiste(Exception):
    """`criar_pedido` sobre um request_id que já tem documento."""


class PedidoNaoEncontrado(LookupError):
    """`atualizar_pedido` sobre um request_id sem documento."""


class PedidoCorrompido(ValueError):
    """Documento existente que a leitura estrita recusa."""


def _validar_request_id(request_id: Any) -> str:
    if not isinstance(request_id, str) or not request_id.strip() or "/" in request_id:
        raise ValueError("request_id deve ser str não vazia sem '/'.")
    if request_id != request_id.strip():
        raise ValueError("request_id não pode ter espaços nas pontas.")
    # Ids que o Firestore real recusa com InvalidArgument (o duplo de teste não).
    if (
        request_id in (".", "..")
        or _RESERVADO.match(request_id)
        or not _utf8_valido(request_id)
        or len(request_id.encode("utf-8")) > 1500
        or any(ord(c) < 32 or ord(c) == 127 for c in request_id)
    ):
        raise ValueError("request_id recusado pelo Firestore (reservado, longo ou com controle).")
    return request_id


_RESERVADO = re.compile(r"^__.*__$", re.DOTALL)
_INT64 = 2**63
_MAX_PROFUNDIDADE = 20


def _utf8_valido(texto: str) -> bool:
    try:
        texto.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _validar_para_firestore(
    valor: Any, nivel: str = "pedido", profundidade: int = 1, em_lista: bool = False
) -> None:
    """Regras do Firestore que o JSON puro do domínio não cobre: int64,
    chaves de mapa vazias/`__x__`/longas, UTF-8 válido e no máximo 20 níveis
    de mapa. Falha aqui (ValueError claro), não como erro opaco do cliente
    no meio da transação. (Limite de 1 MiB por documento: fora de escopo.)"""
    if isinstance(valor, dict):
        if profundidade > _MAX_PROFUNDIDADE:
            raise ValueError(f"{nivel}: mapas aninhados além de {_MAX_PROFUNDIDADE} níveis.")
        for chave, sub in valor.items():
            if (
                chave == ""
                or _RESERVADO.match(chave)
                or not _utf8_valido(chave)
                or len(chave.encode("utf-8")) > 1500
            ):
                raise ValueError(f"{nivel}: chave {chave!r} recusada pelo Firestore.")
            _validar_para_firestore(sub, f"{nivel}.{chave}", profundidade + 1, False)
    elif isinstance(valor, list):
        if em_lista:
            raise ValueError(f"{nivel}: array dentro de array não é aceito pelo Firestore.")
        for i, sub in enumerate(valor):
            _validar_para_firestore(sub, f"{nivel}[{i}]", profundidade, True)
    elif isinstance(valor, str):
        if not _utf8_valido(valor):
            raise ValueError(f"{nivel}: texto com surrogate solitário.")
    elif isinstance(valor, int) and not isinstance(valor, bool):
        if not -_INT64 <= valor < _INT64:
            raise ValueError(f"{nivel}: inteiro fora de int64.")


def _exigir_transacao(db: Any) -> Any:
    if not hasattr(db, "transaction"):
        raise RuntimeError("Backend Firestore sem suporte a transação; escrita do pedido recusada.")
    return db.transaction()


def _ref(db: Any, request_id: str) -> Any:
    return db.collection(COLECAO_PEDIDOS).document(request_id)


def _revisao_de(dados: dict[str, Any]) -> int:
    revisao = dados.get("revisao")
    if isinstance(revisao, bool) or not isinstance(revisao, int) or revisao < 1:
        raise PedidoCorrompido("revisao ausente ou inválida.")
    return revisao


def _ler_dados(snap: Any, request_id: str) -> tuple[PedidoDuravel, int]:
    dados = snap.to_dict() or {}
    if set(dados) != {"pedido", "revisao"}:
        raise PedidoCorrompido("documento com chaves inesperadas ou ausentes.")
    revisao = _revisao_de(dados)
    try:
        pedido = pedido_de_dict(dados["pedido"])
    except ValueError as exc:
        raise PedidoCorrompido(str(exc)) from exc
    if pedido.request_id != request_id:
        raise PedidoCorrompido("request_id do documento diverge do id.")
    return pedido, revisao


def ler_pedido(db: Any, request_id: str) -> PedidoDuravel | None:
    """Lê o pedido (None se não existe). Documento ilegível -> PedidoCorrompido."""
    request_id = _validar_request_id(request_id)
    snap = _ref(db, request_id).get()
    if not snap.exists:
        return None
    return _ler_dados(snap, request_id)[0]


def criar_pedido(db: Any, pedido: PedidoDuravel) -> None:
    """Grava um pedido novo; PedidoJaExiste se o id já tem documento."""
    if not isinstance(pedido, PedidoDuravel):
        raise TypeError("pedido deve ser PedidoDuravel.")
    request_id = _validar_request_id(pedido.request_id)
    doc = {"pedido": pedido_para_dict(pedido), "revisao": 1}
    _validar_para_firestore(doc["pedido"])
    ref = _ref(db, request_id)
    tx = _exigir_transacao(db)

    @firestore.transactional
    def _exec(transaction):
        if ref.get(transaction=transaction).exists:
            raise PedidoJaExiste(request_id)
        transaction.set(ref, doc)

    _exec(tx)


def atualizar_pedido(
    db: Any,
    request_id: str,
    transformar: Callable[[PedidoDuravel], PedidoDuravel],
    run_encerrado: Callable[[], AgentRun | None] | None = None,
) -> PedidoDuravel:
    """Read-modify-write transacional. `transformar` deve ser PURA: o
    Firestore a reexecuta sobre o estado novo quando há contenção. Se ela
    levanta, nada é gravado e a exceção sobe. Devolve o pedido gravado.

    `run_encerrado` (opcional) é chamado logo após `transformar`, na mesma
    transação, e devolve o run antigo fechado que a transição deixou de
    guardar no pedido (ex.: `acordar_espera_externa`); ele é gravado em
    `autonomy_pedidos/{id}/runs_encerrados/{run_id}` junto com o pedido
    (atômico), sem o que ficaria ativo para sempre. Só é gravado se o pedido
    também mudou."""
    request_id = _validar_request_id(request_id)
    if not callable(transformar):
        raise TypeError("transformar deve ser callable.")
    ref = _ref(db, request_id)
    tx = _exigir_transacao(db)

    @firestore.transactional
    def _exec(transaction):
        snap = ref.get(transaction=transaction)
        if not snap.exists:
            raise PedidoNaoEncontrado(request_id)
        atual, revisao = _ler_dados(snap, request_id)
        novo = transformar(atual)
        if not isinstance(novo, PedidoDuravel):
            raise TypeError("transformar deve devolver PedidoDuravel.")
        if novo.request_id != request_id:
            raise ValueError("transformar não pode mudar o request_id.")
        doc = pedido_para_dict(novo)
        _validar_para_firestore(doc)
        if doc != pedido_para_dict(atual):
            transaction.set(ref, {"pedido": doc, "revisao": revisao + 1})
            antigo = run_encerrado() if run_encerrado is not None else None
            if antigo is not None:
                if not isinstance(antigo, AgentRun) or antigo.request_id != request_id:
                    raise ValueError("run_encerrado deve ser AgentRun do mesmo request_id.")
                doc_run = run_para_dict(antigo)
                _validar_para_firestore(doc_run, "run_encerrado")
                transaction.set(
                    ref.collection(SUBCOLECAO_RUNS_ENCERRADOS).document(_validar_request_id(antigo.run_id)),
                    doc_run,
                )
        return novo

    return _exec(tx)
