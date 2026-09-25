"""Virada do dia (daily_reset_job): só ações em andamento são arrastadas para hoje.

Arrastar a data de uma ação em stand-by a punha no resumo e no briefing do dia
como se estivesse ativa.
"""

import datetime
import sys
import types
import unittest
import zoneinfo
from unittest import mock

import daily_reset_job


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.reference = doc_id

    def to_dict(self):
        return dict(self._data)


class _Consulta:
    """Filtra em memória com os operadores que as rotinas usam."""

    def __init__(self, docs):
        self._docs = docs

    def where(self, field=None, op=None, value=None, filter=None):
        if filter is not None:
            field, op, value = filter.field_path, filter.op_string, filter.value

        def fica(doc):
            atual = doc.to_dict().get(field)
            if op == "==":
                return atual == value
            if op == "in":
                return atual in value
            raise AssertionError(f"operador não suportado no fake: {op}")

        return _Consulta([d for d in self._docs if fica(d)])

    def get(self):
        return list(self._docs)


class _Lote:
    def __init__(self):
        self.atualizacoes = {}
        self.gravado = False

    def update(self, ref, dados):
        self.atualizacoes[ref] = dados

    def commit(self):
        self.gravado = True


class _Settings:
    exists = False

    def to_dict(self):
        return {}


class _Db:
    def __init__(self, tarefas):
        self._tarefas = [_Doc(i, d) for i, d in tarefas.items()]
        self.lote = _Lote()

    def collection(self, nome):
        if nome == "tarefas":
            return _Consulta(self._tarefas)
        return types.SimpleNamespace(document=lambda _id: types.SimpleNamespace(get=lambda: _Settings()))

    def batch(self):
        return self.lote


class TestVirada(unittest.TestCase):
    def _rodar(self, tarefas):
        db = _Db(tarefas)
        falso_main = types.SimpleNamespace(get_db=lambda: db, _send_telegram_message_raw=mock.Mock())
        with mock.patch.dict(sys.modules, {"main": falso_main}):
            fn = getattr(daily_reset_job.daily_wip_reset_and_degradation, "__wrapped__",
                         daily_reset_job.daily_wip_reset_and_degradation)
            fn(None)
        return db.lote

    def test_stand_by_vencida_nao_e_arrastada_para_hoje(self):
        base = {"titulo": "X", "data_limite": "2020-01-01", "data_inicio": "2020-01-01", "plano_acao": []}
        lote = self._rodar({
            "pausada": {**base, "status": "stand-by"},
            "ativa": {**base, "status": "em andamento"},
        })
        hoje = datetime.datetime.now(zoneinfo.ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
        self.assertNotIn("pausada", lote.atualizacoes)
        self.assertEqual(lote.atualizacoes["ativa"]["data_limite"], hoje)
        self.assertTrue(lote.gravado)


if __name__ == "__main__":
    unittest.main()
