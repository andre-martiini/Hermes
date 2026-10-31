"""Testes de `autonomy/ciclo_dispatcher.py` (P08): modos off/shadow/ativo, orçamento e isolamento."""

import unittest
from datetime import datetime, timezone
from unittest import mock

from autonomy import ciclo_dispatcher as cd
from autonomy import pedido_repositorio as repo
from autonomy.config_dispatcher import ConfigDispatcher
from autonomy.dispatcher import ModoDispatcher
from autonomy.execution import PedidoDuravel
from autonomy.requests import RequestStatus
from test_autonomy_pedido_repositorio import _Col, _Db
from test_autonomy_sweep_lote import _Consulta, _DbQ

T0 = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


class _Enf:
    def __init__(self, falhas=None):
        self.chamadas, self.falhas = [], falhas or {}

    def __call__(self, nome, payload):
        self.chamadas.append((nome, payload))
        if payload["request_id"] in self.falhas:
            raise self.falhas[payload["request_id"]]


def _cfg(modo, saldo=None, motivo="ok"):
    return ConfigDispatcher(modo, saldo, motivo)


class TestCicloDispatcher(unittest.TestCase):
    def setUp(self):
        self.db = _DbQ()
        for rid in ("a", "b", "c"):
            repo.criar_pedido(self.db, PedidoDuravel(rid, RequestStatus.PENDENTE))
        repo.criar_pedido(self.db, PedidoDuravel("z", RequestStatus.CANCELADO))
        self.db.colecoes.clear()
        self.enf = _Enf()
        self.saldo = {"v": 0}

    def _rodar(self, cfg, **kw):
        def consumir(db, q=1):
            if self.saldo["v"] >= q:
                self.saldo["v"] -= q
                return q
            return 0

        self.saldo["v"] = cfg.despachos_restantes or 0
        with mock.patch.object(cd, "ler_config_dispatcher", return_value=cfg), mock.patch.object(
            cd, "consumir_orcamento", side_effect=consumir
        ):
            return cd.executar_ciclo(self.db, self.enf, agora=T0, **kw)

    def test_off_nao_le_pedidos_nem_enfileira(self):
        r = self._rodar(_cfg(ModoDispatcher.OFF, None, "modo_off"))
        self.assertEqual((r.candidatos, r.enfileirados, self.enf.chamadas), (0, (), []))
        self.assertEqual(self.db.colecoes, [])

    def test_shadow_so_devolve_o_que_seria_enfileirado(self):
        r = self._rodar(_cfg(ModoDispatcher.SHADOW, None, "sombra"))
        self.assertEqual([i for i, _ in r.sombra], ["a", "b", "c"])
        self.assertEqual((r.enfileirados, self.enf.chamadas), ((), []))

    def test_ativo_enfileira_ate_o_orcamento_e_para(self):
        r = self._rodar(_cfg(ModoDispatcher.ATIVO, 2))
        self.assertEqual([i for i, _ in r.enfileirados], ["a", "b"])
        self.assertEqual(len(self.enf.chamadas), 2)
        self.assertEqual(self.enf.chamadas[0][1], {"request_id": "a"})
        self.assertEqual(self.saldo["v"], 0)

    def test_baixa_nao_confirmada_para_sem_enfileirar(self):
        with mock.patch.object(cd, "ler_config_dispatcher", return_value=_cfg(ModoDispatcher.ATIVO, 3)), mock.patch.object(
            cd, "consumir_orcamento", return_value=0
        ):
            r = cd.executar_ciclo(self.db, self.enf, agora=T0)
        self.assertTrue(r.sem_orcamento)
        self.assertEqual((r.enfileirados, self.enf.chamadas), ((), []))

    def test_ja_despachado_e_erro_isolados(self):
        self.enf.falhas = {"a": cd.JaDespachado(), "b": RuntimeError("boom")}
        r = self._rodar(_cfg(ModoDispatcher.ATIVO, 3))
        self.assertEqual(r.ja_despachados, ("a",))
        self.assertEqual([i for i, _ in r.enfileirados], ["c"])
        self.assertEqual(r.erros, (("b", "RuntimeError: boom"),))

    def test_pedido_ilegivel_vira_erro_e_nao_interrompe(self):
        self.db.docs["x"] = {"pedido": {"status": "pendente"}, "revisao": 1}
        r = self._rodar(_cfg(ModoDispatcher.ATIVO, 5))
        self.assertEqual([i for i, _ in r.erros], ["x"])
        self.assertEqual([i for i, _ in r.enfileirados], ["a", "b", "c"])

    def test_limite_e_agora_invalidos(self):
        for ruim in (0, True, "2", None):
            with self.assertRaises(ValueError):
                cd.executar_ciclo(self.db, self.enf, agora=T0, limite=ruim)
        with self.assertRaises(ValueError):
            cd.executar_ciclo(self.db, self.enf, agora=datetime(2026, 1, 1))

    def test_limite_corta_a_pagina(self):
        r = self._rodar(_cfg(ModoDispatcher.ATIVO, 9), limite=2)
        self.assertEqual([i for i, _ in r.enfileirados], ["a", "b"])
