"""Briefing das 5h no Telegram (daily_morning_briefing): ação em stand-by não
aparece em "Ações programadas", mesmo com data de hoje."""

import datetime
import sys
import types
import unittest
import zoneinfo
from unittest import mock

import daily_morning_briefing


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


class _Db:
    def __init__(self, tarefas):
        self._tarefas = [_Doc(i, d) for i, d in tarefas.items()]

    def collection(self, nome):
        assert nome == "tarefas", nome
        return _Consulta(self._tarefas)


class TestBriefing(unittest.TestCase):
    def test_stand_by_fica_fora_das_acoes_programadas(self):
        hoje = datetime.datetime.now(zoneinfo.ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
        db = _Db({
            "pausada": {"titulo": "Pausada hoje", "status": "stand-by", "data_limite": hoje},
            "ativa": {"titulo": "Ativa hoje", "status": "em andamento", "data_limite": hoje},
        })
        enviar = mock.Mock()
        falso_main = types.SimpleNamespace(
            get_db=lambda: db,
            get_calendar_service=lambda: None,
            get_target_calendar_id=lambda _db: "cal",
            _resolve_default_telegram_chat_id=lambda _db: "123",
            _get_telegram_token=lambda _db: "token",
            _send_telegram_message=enviar,
        )
        modulos = {
            "main": falso_main,
            "hermes_calendar_tools": types.SimpleNamespace(consultar_eventos=lambda *a, **k: []),
            "investimentos_sync": types.SimpleNamespace(sincronizar_decisao_investimentos=lambda _db: None),
        }
        with mock.patch.dict(sys.modules, modulos):
            fn = getattr(daily_morning_briefing.briefing_matinal_acoes, "__wrapped__",
                         daily_morning_briefing.briefing_matinal_acoes)
            fn(None)
        mensagem = enviar.call_args.args[2]
        self.assertIn("Ativa hoje", mensagem)
        self.assertNotIn("Pausada hoje", mensagem)


if __name__ == "__main__":
    unittest.main()
