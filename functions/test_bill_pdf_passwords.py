import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bill_pdf_passwords import find_password_config, list_password_configs, normalize_sender


class _Snapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return self._data


class _Db:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def collection(self, name):
        self.collection_name = name
        return SimpleNamespace(stream=lambda: iter(self._snapshots))


class TestBillPdfPasswordConfigs(unittest.TestCase):
    def setUp(self):
        self.db = _Db([
            _Snapshot("tim", {
                "active": True,
                "label": "Tim celular",
                "rubric_id": "rubric-tim",
                "senders": ["Tim <CONTATIM@FATURATIM.COM.BR>"],
                "secret_id": "bill-pdf-password-tim",
            }),
            _Snapshot("invalid", {
                "active": True,
                "secret_id": "../../invalid",
                "senders": ["bad@example.com"],
            }),
        ])

    def test_normalizes_sender_address(self):
        self.assertEqual(normalize_sender("Tim <CONTATIM@FATURATIM.COM.BR>"), "contatim@faturatim.com.br")

    def test_lists_only_safe_configs(self):
        configs = list_password_configs(self.db)
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["id"], "tim")

    def test_matches_config_by_normalized_sender(self):
        config = find_password_config(self.db, "TIM <contatim@faturatim.com.br>")
        self.assertIsNotNone(config)
        self.assertEqual(config["rubric_id"], "rubric-tim")


if __name__ == "__main__":
    unittest.main()
