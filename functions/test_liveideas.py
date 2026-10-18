"""Testes do cliente do canal do Live Ideas (liveideas.py), com bancos falsos."""
import json
import threading
import unittest
from unittest import mock

import liveideas


class RefFalsa:
    """Imita o suficiente de firebase_admin.db.Reference (child/get/set/delete)."""

    def __init__(self, dados, caminho=""):
        self.dados, self.caminho = dados, caminho

    def child(self, sub):
        return RefFalsa(self.dados, f"{self.caminho}/{sub}".strip("/"))

    def get(self):
        return self.dados.get(self.caminho)

    def set(self, valor):
        self.dados[self.caminho] = valor

    def delete(self):
        self.dados.pop(self.caminho, None)


class DocFalso:
    def __init__(self, dados):
        self.dados, self.exists = dados, dados is not None

    def to_dict(self):
        return self.dados


class FirestoreFalso:
    def __init__(self, api_keys):
        self.api_keys = api_keys

    def collection(self, nome):
        assert nome == "system"
        return self

    def document(self, nome):
        assert nome == "api_keys"
        return self

    def get(self):
        return DocFalso(self.api_keys)


class ComandoTest(unittest.TestCase):
    def setUp(self):
        self.dados = {"quadro/servidor/online": True}
        self.raiz = RefFalsa(self.dados)
        p = mock.patch.object(liveideas, "INTERVALO_S", 0.01)
        p.start()
        self.addCleanup(p.stop)

    def _responder(self, status=200, corpo=None):
        """Simula o notebook: assim que o comando aparece, grava a resposta."""
        def laco():
            for _ in range(200):
                ids = [c.split("/")[2] for c in list(self.dados) if c.startswith("gaspar/comandos/")]
                if ids:
                    self.dados[f"gaspar/respostas/{ids[0]}"] = {
                        "status": status, "corpo": json.dumps(corpo or {}), "em": 1}
                    return
                threading.Event().wait(0.01)
        t = threading.Thread(target=laco)
        t.start()
        self.addCleanup(t.join)

    def test_resposta_chega_e_e_apagada(self):
        self._responder(200, {"ok": True})
        status, corpo = liveideas.comando(self.raiz, "listar", {"x": 1}, espera_s=2)
        self.assertEqual((status, corpo), (200, {"ok": True}))
        self.assertFalse([c for c in self.dados if c.startswith("gaspar/respostas/")])
        gravado = next(v for c, v in self.dados.items() if c.startswith("gaspar/comandos/"))
        self.assertEqual(gravado["acao"], "listar")
        self.assertEqual(json.loads(gravado["corpo"]), {"x": 1})
        self.assertIsInstance(gravado["em"], int)

    def test_notebook_desligado_levanta_antes_de_gravar(self):
        self.dados["quadro/servidor/online"] = False
        with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
            liveideas.comando(self.raiz, "listar", {})
        self.assertEqual(e.exception.mensagem, liveideas.MSG_DESLIGADO)
        self.assertEqual(e.exception.mensagem, "o notebook do Live Ideas está desligado (ligue-o e peça de novo)")
        self.assertFalse([c for c in self.dados if c.startswith("gaspar/")])

    def test_sem_resposta_levanta_e_apaga_o_comando(self):
        with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
            liveideas.comando(self.raiz, "listar", {}, espera_s=0.2)
        self.assertEqual(e.exception.mensagem, "o notebook não respondeu; tente de novo em instantes")
        self.assertFalse([c for c in self.dados if c.startswith("gaspar/")])


class BancoTest(unittest.TestCase):
    def setUp(self):
        liveideas._apps.clear()
        self.addCleanup(liveideas._apps.clear)

    def test_credencial_ausente_tem_mensagem_clara(self):
        for chaves in (None, {}, {"liveideas_conta_servico": ""}):
            with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
                liveideas.banco_liveideas(FirestoreFalso(chaves))
            self.assertEqual(
                e.exception.mensagem,
                "falta a credencial do Live Ideas no cofre do Gaspar (system/api_keys.liveideas_conta_servico)")

    def test_app_criado_com_override_gaspar_uma_vez_so(self):
        conta = {"type": "service_account", "project_id": "x"}
        fs = FirestoreFalso({"liveideas_conta_servico": json.dumps(conta)})
        with mock.patch.object(liveideas.credentials, "Certificate", return_value="cred") as cert, \
             mock.patch.object(liveideas.firebase_admin, "initialize_app", return_value="app") as ini, \
             mock.patch.object(liveideas.rtdb, "reference", return_value="raiz") as ref:
            self.assertEqual(liveideas.banco_liveideas(fs), "raiz")
            liveideas.banco_liveideas(fs)
        cert.assert_called_once_with(conta)
        ini.assert_called_once_with("cred", {
            "databaseURL": "https://quadro-ao-vivo-andre-default-rtdb.firebaseio.com",
            "databaseAuthVariableOverride": {"uid": "gaspar"},
        }, name="liveideas")
        self.assertEqual(ref.call_args.kwargs["app"], "app")


if __name__ == "__main__":
    unittest.main()
