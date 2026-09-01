import os
import sys
import unittest
from unittest.mock import Mock

from googleapiclient.errors import HttpError
from httplib2 import Response

# `hermes_cli.py` esta na RAIZ do repositorio, nao em `functions/`. Rodando os
# testes de dentro de `functions/` — que e como o CI os roda — a raiz nao esta no
# path e o import abaixo falha na carga do modulo, derrubando o arquivo inteiro
# antes de qualquer teste. E o mesmo formato do erro que deixou a `main` sem
# deploy em 30/08: arquivo na raiz que a ferramenta nao enxerga.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hermes_cli  # noqa: E402


def http_error(status):
    return HttpError(Response({"status": str(status)}), b"{}")


class HermesCliCalendarTest(unittest.TestCase):
    def test_calendar_fallback_is_dedicated_not_primary(self):
        db = Mock()
        snap = db.collection.return_value.document.return_value.get.return_value
        snap.exists = False

        self.assertEqual(
            hermes_cli.get_target_calendar_id(db),
            hermes_cli.DEFAULT_GOOGLE_CALENDAR_ID,
        )
        self.assertNotEqual(hermes_cli.get_target_calendar_id(db), "primary")

    def test_calendar_configuration_overrides_fallback(self):
        db = Mock()
        snap = db.collection.return_value.document.return_value.get.return_value
        snap.exists = True
        snap.to_dict.return_value = {"googleCalendarId": "acoes-configuradas"}

        self.assertEqual(hermes_cli.get_target_calendar_id(db), "acoes-configuradas")

    def test_event_id_is_stable_and_matches_cloud_contract(self):
        task_id = "e099c993-c3d1-49f3-8"
        self.assertEqual(
            hermes_cli.build_task_calendar_event_id(task_id),
            "hermes0200912d1e0c59c1afa39101c77e22a6",
        )

    def test_wrong_calendar_id_converges_to_deterministic_event(self):
        api = Mock()
        events = api.events.return_value
        events.update.return_value.execute.side_effect = http_error(404)
        events.insert.return_value.execute.side_effect = http_error(409)
        expected_id = hermes_cli.build_task_calendar_event_id("task-1")
        events.get.return_value.execute.return_value = {"id": expected_id}

        result = hermes_cli.upsert_task_calendar_event(
            api, "acoes-hermes", "task-1", "id-de-outro-calendario", {"summary": "Tarefa"}
        )

        self.assertEqual(result["id"], expected_id)
        events.insert.assert_called_once_with(
            calendarId="acoes-hermes",
            body={"summary": "Tarefa", "id": expected_id},
        )
        events.get.assert_called_once_with(calendarId="acoes-hermes", eventId=expected_id)

    def test_new_event_is_inserted_only_in_target_calendar(self):
        api = Mock()
        events = api.events.return_value
        expected_id = hermes_cli.build_task_calendar_event_id("task-2")
        events.insert.return_value.execute.return_value = {"id": expected_id}

        result = hermes_cli.upsert_task_calendar_event(
            api, "acoes-hermes", "task-2", None, {"summary": "Tarefa"}
        )

        self.assertEqual(result["id"], expected_id)
        events.update.assert_not_called()
        events.insert.assert_called_once_with(
            calendarId="acoes-hermes",
            body={"summary": "Tarefa", "id": expected_id},
        )


if __name__ == "__main__":
    unittest.main()
