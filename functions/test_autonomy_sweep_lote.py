"""Testes de `autonomy/sweep_lote.py` (P08): listagem de candidatos e sweep em lote."""

import copy
import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from autonomy import pedido_repositorio as repo
from autonomy import sweep_lote as sl
from autonomy.execution import PedidoDuravel, assumir_pedido, registrar_progresso
from autonomy.requests import RequestStatus
from test_autonomy_pedido_repositorio import _Col, _Db

T0 = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


class _Doc:
    def __init__(self, doc_id):
        self.id = doc_id


class _Consulta:
    def __init__(self, db):
        self.db, self.filtro, self.n = db, None, None

    def where(self, campo, op, valor):
        assert (campo, op) == ("pedido.status", "in")
        self.filtro = valor
        return self

    def order_by(self, campo):
        assert campo == "__name__"
        return self

    def start_after(self, doc):
        self.apos = doc.id
        return self

    apos = None

    def limit(self, n):
        self.n = n
        return self

    def stream(self):
        docs = sorted(i for i, d in self.db.docs.items() if d["pedido"]["status"] in self.filtro)
        if self.apos is not None:
            docs = [i for i in docs if i > self.apos]
        return [_Doc(i) for i in docs[: self.n]]


class _ColQ(_Col):
    def where(self, campo, op, valor):
        return _Consulta(self.db).where(campo, op, valor)


class _DbQ(_Db):
    def collection(self, nome):
        self.colecoes.append(nome)
        return _ColQ(self)


def _andamento(rid, agora=T0):
    p = assumir_pedido(PedidoDuravel(rid, RequestStatus.PENDENTE), "ex-a", "run-1", agora=agora)
    return registrar_progresso(p, p.lease.lease_token, p.lease.generation, "k1", {"a": 1}, {"n": 1}, agora=agora)


class TestSweepLote(unittest.TestCase):
    def setUp(self):
        self.db = _DbQ()
        self.depois = T0 + timedelta(hours=2)

    def test_lista_so_status_varriveis_ordenados_e_respeita_limite(self):
        repo.criar_pedido(self.db, _andamento("b"))
        repo.criar_pedido(self.db, _andamento("a"))
        repo.criar_pedido(self.db, PedidoDuravel("c", RequestStatus.PENDENTE))
        self.assertEqual(sl.listar_candidatos(self.db), ["a", "b"])
        self.assertEqual(len(sl.listar_candidatos(self.db, limite=1)), 1)
        for ruim in (0, -1, True, "3", None):
            with self.assertRaises(ValueError):
                sl.listar_candidatos(self.db, limite=ruim)

    def test_varre_lote_e_so_grava_o_vencido(self):
        vencido = _andamento("a")
        repo.criar_pedido(self.db, vencido)
        repo.criar_pedido(self.db, _andamento("b", agora=self.depois))
        r = sl.varrer_candidatos(self.db, agora=self.depois)
        self.assertEqual(r.candidatos, 2)
        self.assertEqual(r.varridos, (("a", "lease_vencida"),))
        self.assertEqual(self.db.docs["a"]["revisao"], 2)
        self.assertEqual(self.db.docs["b"]["revisao"], 1)

    def test_pedido_incoerente_ou_corrompido_nao_impede_os_demais(self):
        repo.criar_pedido(self.db, _andamento("a"))
        repo.criar_pedido(self.db, _andamento("z"))
        sem_lease = repo.pedido_para_dict(_andamento("m"))
        sem_lease["lease"] = None
        self.db.docs["m"] = {"pedido": sem_lease, "revisao": 1}
        self.db.docs["x"] = {"pedido": {"status": "em_andamento"}, "revisao": 1}
        r = sl.varrer_candidatos(self.db, agora=self.depois)
        self.assertEqual(sorted(i for i, _ in r.varridos), ["a", "z"])
        self.assertEqual(sorted(i for i, _ in r.erros), ["m", "x"])

    def test_diagnosticos_agregados(self):
        repo.criar_pedido(self.db, dataclasses.replace(_andamento("a"), tentativas=3))
        r = sl.varrer_candidatos(self.db, agora=self.depois, max_tentativas=3)
        self.assertEqual([d.request_id for d in r.diagnosticos], ["a"])

    def test_pagina_ate_alcancar_vencido_atras_de_muitos_nao_vencidos(self):
        for i in range(5):
            repo.criar_pedido(self.db, _andamento(f"a{i}", agora=self.depois))
        repo.criar_pedido(self.db, _andamento("z"))
        r = sl.varrer_candidatos(self.db, agora=self.depois, limite=2)
        self.assertEqual(r.candidatos, 6)
        self.assertFalse(r.truncado)
        self.assertEqual(r.varridos, (("z", "lease_vencida"),))

    def test_teto_de_paginas_marca_truncado(self):
        for i in range(5):
            repo.criar_pedido(self.db, _andamento(f"a{i}", agora=self.depois))
        r = sl.varrer_candidatos(self.db, agora=self.depois, limite=2, max_paginas=2)
        self.assertEqual((r.candidatos, r.truncado), (4, True))
        exato = sl.varrer_candidatos(self.db, agora=self.depois, limite=5, max_paginas=1)
        self.assertEqual((exato.candidatos, exato.truncado), (5, True))  # página cheia no teto: pode haver mais

    def test_parametros_invalidos(self):
        for ruim in (0, True, "2"):
            with self.assertRaises(ValueError):
                sl.varrer_candidatos(self.db, agora=T0, max_paginas=ruim)
            with self.assertRaises(ValueError):
                sl.varrer_candidatos(self.db, agora=T0, limite=ruim)

    def test_agora_naive_recusado_e_sem_candidatos(self):
        with self.assertRaises(ValueError):
            sl.varrer_candidatos(self.db, agora=datetime(2026, 1, 1))
        r = sl.varrer_candidatos(self.db, agora=T0)
        self.assertEqual((r.candidatos, r.truncado, r.varridos, r.erros), (0, False, (), ()))


if __name__ == "__main__":
    unittest.main()
