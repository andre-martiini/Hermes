"""Testes de `autonomy/pedido_repositorio.py` (P08): persistência transacional do pedido."""

import copy
import dataclasses
import unittest

from autonomy import pedido_repositorio as repo
from datetime import datetime, timezone

from autonomy.execution import PedidoDuravel, assumir_pedido, registrar_progresso
from autonomy.requests import RequestStatus
from test_autonomy_pedido_serializacao import _completo

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


class _Snap:
    def __init__(self, data):
        self._data = copy.deepcopy(data)
        self.exists = data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else {}


class _Ref:
    def __init__(self, db, doc_id):
        self.db, self.id = db, doc_id

    def get(self, transaction=None):
        return _Snap(self.db.docs.get(self.id))

    def set(self, data):
        self.db.docs[self.id] = copy.deepcopy(data)


class _Col:
    def __init__(self, db):
        self.db = db

    def document(self, doc_id):
        return _Ref(self.db, doc_id)


class _Tx:
    """Duplo fiel o bastante para o decorator real @firestore.transactional."""

    def __init__(self, db):
        self.db = db
        self._read_only = False
        self._id = b"tx"
        self._max_attempts = 5
        self.escritas = []

    def set(self, ref, data):
        self.escritas.append((ref, data))

    def _rollback(self):
        self.escritas = []

    def _commit(self):
        for ref, data in self.escritas:
            ref.set(data)
        self.escritas = []

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or b"tx"


class _Db:
    def __init__(self):
        self.docs = {}
        self.colecoes = []

    def collection(self, nome):
        self.colecoes.append(nome)
        return _Col(self)

    def transaction(self):
        return _Tx(self)


class _DbSemTx:
    def collection(self, nome):
        return _Col(_Db())


class TestRepositorioPedido(unittest.TestCase):
    def setUp(self):
        self.db = _Db()

    def test_criar_e_ler_round_trip(self):
        p = _completo()
        repo.criar_pedido(self.db, p)
        self.assertEqual(repo.ler_pedido(self.db, "req-1"), p)
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)
        self.assertEqual(set(self.db.colecoes), {repo.COLECAO_PEDIDOS})

    def test_ler_inexistente_devolve_none(self):
        self.assertIsNone(repo.ler_pedido(self.db, "nao-existe"))

    def test_criar_duplicado_recusa_e_preserva_o_original(self):
        p = _completo()
        repo.criar_pedido(self.db, p)
        outro = dataclasses.replace(p, tentativas=9)
        with self.assertRaises(repo.PedidoJaExiste):
            repo.criar_pedido(self.db, outro)
        self.assertEqual(repo.ler_pedido(self.db, "req-1"), p)

    def test_atualizar_grava_e_incrementa_revisao(self):
        repo.criar_pedido(self.db, _completo())
        novo = repo.atualizar_pedido(self.db, "req-1", lambda p: dataclasses.replace(p, tentativas=7))
        self.assertEqual(novo.tentativas, 7)
        self.assertEqual(repo.ler_pedido(self.db, "req-1").tentativas, 7)
        self.assertEqual(self.db.docs["req-1"]["revisao"], 2)

    def test_atualizar_sem_mudanca_nao_escreve(self):
        repo.criar_pedido(self.db, _completo())
        repo.atualizar_pedido(self.db, "req-1", lambda p: p)
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)

    def test_atualizar_inexistente(self):
        with self.assertRaises(repo.PedidoNaoEncontrado):
            repo.atualizar_pedido(self.db, "x", lambda p: p)
        self.assertEqual(self.db.docs, {})

    def test_transformar_que_levanta_nao_grava(self):
        repo.criar_pedido(self.db, _completo())

        def ruim(p):
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            repo.atualizar_pedido(self.db, "req-1", ruim)
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)

    def test_transformar_com_retorno_invalido_ou_outro_id(self):
        repo.criar_pedido(self.db, _completo())
        with self.assertRaises(TypeError):
            repo.atualizar_pedido(self.db, "req-1", lambda p: {"x": 1})
        with self.assertRaises(ValueError):
            repo.atualizar_pedido(self.db, "req-1", lambda p: dataclasses.replace(p, request_id="outro"))
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)

    def test_documento_corrompido_vira_pedido_corrompido(self):
        repo.criar_pedido(self.db, _completo())
        base = copy.deepcopy(self.db.docs["req-1"])
        casos = []
        d = copy.deepcopy(base); d["extra"] = 1; casos.append(d)
        d = copy.deepcopy(base); d["revisao"] = 0; casos.append(d)
        d = copy.deepcopy(base); d["revisao"] = True; casos.append(d)
        d = copy.deepcopy(base); d["pedido"]["status"] = "inventado"; casos.append(d)
        d = copy.deepcopy(base); d["pedido"]["request_id"] = "outro"; casos.append(d)
        d = copy.deepcopy(base); d["pedido"] = "lixo"; casos.append(d)
        for d in casos:
            self.db.docs["req-1"] = d
            with self.assertRaises(repo.PedidoCorrompido):
                repo.ler_pedido(self.db, "req-1")
            with self.assertRaises(repo.PedidoCorrompido):
                repo.atualizar_pedido(self.db, "req-1", lambda p: p)

    def test_request_id_invalido(self):
        for rid in ("", " a", "a/b", None, 3, ".", "..", "__x__", "a\x00b", "a" * 1501, "a\ud800"):
            with self.assertRaises(ValueError):
                repo.ler_pedido(self.db, rid)
            with self.assertRaises(ValueError):
                repo.atualizar_pedido(self.db, rid, lambda p: p)
        with self.assertRaises(ValueError):
            repo.criar_pedido(self.db, PedidoDuravel("a/b", RequestStatus.PENDENTE))

    def test_dados_que_o_firestore_recusa_nao_sao_gravados(self):
        p = assumir_pedido(PedidoDuravel("req-g", RequestStatus.PENDENTE), "ex", "run", agora=T0)
        p = registrar_progresso(
            p, p.lease.lease_token, p.lease.generation, "k", {"a": 1}, {"x": 2**70}, agora=T0
        )
        with self.assertRaises(ValueError):
            repo.criar_pedido(self.db, p)
        self.assertEqual(self.db.docs, {})
        # montagem direta do documento: o validador é função pura
        for valor in ({"x": 2**70}, {"": 1}, {"a": {"__b__": 1}}, {"l": [{"": 1}]}, {"n": -(2**63) - 1}, {"l": [[1]]}, {"l": [{"m": [[]]}]}):
            with self.assertRaises(ValueError):
                repo._validar_para_firestore(valor)
        fundo = {}
        for _ in range(25):
            fundo = {"a": fundo}
        for valor in (fundo, {"a": "\ud800"}, {"\ud800": 1}, {"k" * 1501: 1}):
            with self.assertRaises(ValueError):
                repo._validar_para_firestore(valor)
        raso = {}
        for _ in range(18):
            raso = {"a": raso}
        repo._validar_para_firestore(raso)
        repo._validar_para_firestore({"a": [1, {"b": 2**63 - 1, "c": True, "l": [1, 2]}], "d": -(2**63)})
        repo.criar_pedido(self.db, _completo())  # o pedido normal passa

    def test_criar_tipo_errado_e_transformar_nao_callable(self):
        with self.assertRaises(TypeError):
            repo.criar_pedido(self.db, {"request_id": "x"})
        with self.assertRaises(TypeError):
            repo.atualizar_pedido(self.db, "x", "nao-callable")

    def test_backend_sem_transacao_recusa(self):
        with self.assertRaises(RuntimeError):
            repo.criar_pedido(_DbSemTx(), _completo())
        with self.assertRaises(RuntimeError):
            repo.atualizar_pedido(_DbSemTx(), "req-1", lambda p: p)


if __name__ == "__main__":
    unittest.main()
