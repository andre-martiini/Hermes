"""Testes de `autonomy/enfileirador_cloud_tasks.py` (P08): tarefa montada, idempotência e fail-closed."""

import json
import unittest

from autonomy.ciclo_dispatcher import JaDespachado
from autonomy.enfileirador_cloud_tasks import ConfigCloudTasks, criar_enfileirador


class AlreadyExists(Exception):
    pass


class _Cli:
    def __init__(self, erro=None):
        self.chamadas, self.erro = [], erro

    def create_task(self, request):
        self.chamadas.append(request)
        if self.erro:
            raise self.erro


CFG = ConfigCloudTasks("proj", "us-central1", "runner", "https://w.example/run", "sa@proj.iam.gserviceaccount.com")


class TestEnfileirador(unittest.TestCase):
    def test_monta_tarefa(self):
        cli = _Cli()
        criar_enfileirador(cli, CFG)("runner-abc-t0-g0", {"request_id": "r1"})
        req = cli.chamadas[0]
        self.assertEqual(req["parent"], "projects/proj/locations/us-central1/queues/runner")
        t = req["task"]
        self.assertEqual(t["name"], req["parent"] + "/tasks/runner-abc-t0-g0")
        h = t["http_request"]
        self.assertEqual(h["url"], CFG.url_worker)
        self.assertEqual(h["oidc_token"]["audience"], CFG.url_worker)
        self.assertEqual(h["oidc_token"]["service_account_email"], CFG.service_account_email)
        self.assertEqual(json.loads(h["body"]), {"request_id": "r1"})

    def test_request_id_com_espaco_interno_vale(self):
        cli = _Cli()
        criar_enfileirador(cli, CFG)("n1", {"request_id": "pedido do cliente 1"})
        self.assertEqual(json.loads(cli.chamadas[0]["task"]["http_request"]["body"]),
                         {"request_id": "pedido do cliente 1"})

    def test_duplicata_vira_ja_despachado(self):
        with self.assertRaises(JaDespachado):
            criar_enfileirador(_Cli(AlreadyExists()), CFG)("n1", {"request_id": "r"})

    def test_outra_falha_propaga(self):
        with self.assertRaises(RuntimeError):
            criar_enfileirador(_Cli(RuntimeError("x")), CFG)("n1", {"request_id": "r"})

    def test_entradas_invalidas_nao_enviam(self):
        cli = _Cli()
        enf = criar_enfileirador(cli, CFG)
        for nome, p in (("a/b", {"request_id": "r"}), ("", {"request_id": "r"}), ("ok", {}),
                        ("ok\n", {"request_id": "r"}), ("ok", {"request_id": "r\n"}),
                        ("ok", {"request_id": "r", "x": "y"}), ("ok", {"request_id": " "}), ("ok", {"request_id": "a/b"}), (1, {"request_id": "r"})):
            with self.assertRaises(ValueError):
                enf(nome, p)
        self.assertEqual(cli.chamadas, [])

    def test_config_invalida(self):
        for cfg in (None, ConfigCloudTasks("", "r", "f", "https://w", "sa"),
                    ConfigCloudTasks("p", "r", "f", "http://w", "sa"),
                    ConfigCloudTasks("p", "r", "f/x", "https://w", "sa"),
                    ConfigCloudTasks("p x", "r", "f", "https://w", "sa"),
                    ConfigCloudTasks("p", "r", "f", "https://", "sa"),
                    ConfigCloudTasks("p", "r", "f", "https://w y", "sa")):
            with self.assertRaises(ValueError):
                criar_enfileirador(_Cli(), cfg)
        with self.assertRaises(ValueError):
            criar_enfileirador(object(), CFG)

    def test_integra_com_ciclo(self):
        # a assinatura é a que executar_ciclo chama: enfileirar(nome, dict)
        cli = _Cli()
        criar_enfileirador(cli, CFG)("runner-x-t1-g2", dict((("request_id", "r9"),)))
        self.assertEqual(len(cli.chamadas), 1)


if __name__ == "__main__":
    unittest.main()
