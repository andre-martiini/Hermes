import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bill_pdf_passwords import (
    destroy_previous_secret_versions,
    find_password_config,
    list_password_configs,
    normalize_sender,
    save_password_secret,
)


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


class TestSavePasswordSecretVersions(unittest.TestCase):
    """Cada save cria versão nova; as antigas são destruídas (custo por versão ativa)."""

    PARENT = "projects/p/secrets/bill-pdf-password-tim"

    def _version(self, num, state="ENABLED"):
        return SimpleNamespace(name=f"{self.PARENT}/versions/{num}", state=SimpleNamespace(name=state))

    def _client(self, versions, new_num=3):
        client = MagicMock()
        client.add_secret_version.return_value = SimpleNamespace(name=f"{self.PARENT}/versions/{new_num}")
        client.list_secret_versions.return_value = iter(versions)
        return client

    def test_destroi_versoes_anteriores_e_mantem_a_nova(self):
        client = self._client([self._version(3), self._version(2), self._version(1, "DISABLED")])
        save_password_secret("p", "bill-pdf-password-tim", "segredo", client=client)

        client.add_secret_version.assert_called_once()
        self.assertEqual(client.add_secret_version.call_args.kwargs["parent"], self.PARENT)
        destruidas = [c.kwargs["request"]["name"] for c in client.destroy_secret_version.call_args_list]
        self.assertEqual(destruidas, [f"{self.PARENT}/versions/2", f"{self.PARENT}/versions/1"])

    def test_ignora_versoes_ja_destruidas(self):
        client = self._client([self._version(3), self._version(2, "DESTROYED")])
        save_password_secret("p", "bill-pdf-password-tim", "segredo", client=client)
        client.destroy_secret_version.assert_not_called()

    def test_falha_ao_listar_nao_derruba_o_save(self):
        client = self._client([])
        client.list_secret_versions.side_effect = RuntimeError("sem permissão")
        save_password_secret("p", "bill-pdf-password-tim", "segredo", client=client)
        client.add_secret_version.assert_called_once()
        client.destroy_secret_version.assert_not_called()

    def test_falha_ao_destruir_uma_versao_segue_para_as_demais(self):
        client = self._client([self._version(2), self._version(1)])
        client.destroy_secret_version.side_effect = [RuntimeError("403"), None]
        destruidas = destroy_previous_secret_versions(client, self.PARENT, f"{self.PARENT}/versions/3")
        self.assertEqual(destruidas, 1)
        self.assertEqual(client.destroy_secret_version.call_count, 2)

    def test_sem_nome_da_versao_nova_nao_destroi_nada(self):
        client = self._client([self._version(2)])
        client.add_secret_version.return_value = SimpleNamespace()
        save_password_secret("p", "bill-pdf-password-tim", "segredo", client=client)
        client.list_secret_versions.assert_not_called()
        client.destroy_secret_version.assert_not_called()

    def test_senha_invalida_nao_toca_no_secret_manager(self):
        client = self._client([])
        with self.assertRaises(ValueError):
            save_password_secret("p", "bill-pdf-password-tim", "", client=client)
        client.add_secret_version.assert_not_called()


if __name__ == "__main__":
    unittest.main()
