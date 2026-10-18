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
        self.assertEqual(gravado["criado"], {".sv": "timestamp"})  # hora do servidor do Firebase

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

    def test_resposta_malformada_vira_indisponivel(self):
        malformadas = ({"corpo": "{}"}, {"status": 200, "corpo": "nao e json"},
                       {"status": 200, "corpo": "[1]"}, {"status": "x", "corpo": "{}"})
        for r in malformadas:
            self.dados["gaspar/respostas/abc"] = r
            with mock.patch.object(liveideas.uuid, "uuid4", return_value=mock.Mock(hex="abc")):
                with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
                    liveideas.comando(self.raiz, "listar", {}, espera_s=1)
            self.assertEqual(e.exception.mensagem, "o notebook devolveu uma resposta inválida")
            self.assertNotIn("gaspar/respostas/abc", self.dados)

    def test_erro_de_rede_vira_indisponivel(self):
        with mock.patch.object(RefFalsa, "get", side_effect=OSError("detalhe interno")):
            with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
                liveideas.comando(self.raiz, "listar", {})
        self.assertEqual(e.exception.mensagem, liveideas.MSG_REDE)
        self.assertNotIn("detalhe interno", str(e.exception))

    def test_set_que_estoura_o_prazo_tenta_retirar_o_comando(self):
        def set_e_cai(ref, valor):  # o servidor gravou, mas a resposta do set não chegou a tempo
            ref.dados[ref.caminho] = valor
            raise TimeoutError("prazo")
        with mock.patch.object(RefFalsa, "set", set_e_cai):
            with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
                liveideas.comando(self.raiz, "listar", {}, espera_s=1)
        self.assertEqual(e.exception.mensagem, liveideas.MSG_REDE)
        self.assertFalse([c for c in self.dados if c.startswith("gaspar/")])

    def test_corpo_grande_demais_tem_frase_propria_e_nao_grava(self):
        with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
            liveideas.comando(self.raiz, "gerar", {"tipo": "mapa", "texto": "x" * 200000})
        self.assertEqual(e.exception.mensagem, "o texto é grande demais para mandar ao Live Ideas "
                                               "(limite de cerca de 200.000 caracteres)")
        self.assertFalse([c for c in self.dados if c.startswith("gaspar/")])
        # o limite é o do JSON inteiro, contado como no Firebase (emoji conta 2)
        with self.assertRaises(liveideas.LiveIdeasIndisponivel):
            liveideas.comando(self.raiz, "gerar", {"texto": "😀" * 99995})

    def test_corpo_que_nao_vira_json_tem_erro_claro(self):
        for corpo in ({"texto": object()}, {"x": float("nan")}):
            with self.subTest(corpo=corpo):
                with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
                    liveideas.comando(self.raiz, "gerar", corpo)
                self.assertEqual(e.exception.mensagem, liveideas.MSG_CORPO_INVALIDO)
                self.assertNotEqual(e.exception.mensagem, liveideas.MSG_REDE)
        self.assertFalse([c for c in self.dados if c.startswith("gaspar/")])

    def test_delete_que_falha_nao_esconde_sem_resposta(self):
        with mock.patch.object(RefFalsa, "delete", side_effect=OSError("rede")):
            with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
                liveideas.comando(self.raiz, "listar", {}, espera_s=0.1)
        self.assertEqual(e.exception.mensagem, liveideas.MSG_SEM_RESPOSTA)


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

    def test_credencial_invalida_nao_vaza_o_segredo(self):
        segredo = "-----BEGIN PRIVATE KEY-----SEGREDO"
        conta = {"type": "service_account", "private_key": segredo}
        casos = {
            "dupla codificacao": json.dumps(json.dumps(conta)),
            "lista": json.dumps([conta]),
            "json quebrado": json.dumps(conta)[:-1],
        }
        for nome, texto in casos.items():
            with self.subTest(nome):
                with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
                    liveideas.banco_liveideas(FirestoreFalso({"liveideas_conta_servico": texto}))
                self.assertNotIn("SEGREDO", str(e.exception))
                self.assertNotIn("SEGREDO", e.exception.mensagem)
                self.assertEqual(e.exception.mensagem, liveideas.MSG_JSON_INVALIDO)
        # Certificate() falhando com texto que contém a chave
        fs = FirestoreFalso({"liveideas_conta_servico": json.dumps(conta)})
        with mock.patch.object(liveideas.credentials, "Certificate", side_effect=OSError(segredo)):
            with self.assertRaises(liveideas.LiveIdeasIndisponivel) as e:
                liveideas.banco_liveideas(fs)
        self.assertNotIn("SEGREDO", str(e.exception))
        self.assertEqual(e.exception.mensagem, liveideas.MSG_CREDENCIAL_RECUSADA)
        self.assertTrue(e.exception.__suppress_context__)

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
            "httpTimeout": 5,
        }, name="liveideas")
        self.assertEqual(ref.call_args.kwargs["app"], "app")

    def test_duas_chamadas_simultaneas_criam_o_app_uma_vez_so(self):
        fs = FirestoreFalso({"liveideas_conta_servico": json.dumps({"type": "service_account"})})
        criados = []

        def inicializar(cred, opcoes, name):
            if criados:
                raise ValueError(f"The default Firebase app already exists: {name}")
            threading.Event().wait(0.05)  # janela para a outra thread entrar
            criados.append(name)
            return "app"
        saidas = []
        with mock.patch.object(liveideas.credentials, "Certificate", return_value="cred"),              mock.patch.object(liveideas.firebase_admin, "initialize_app", side_effect=inicializar),              mock.patch.object(liveideas.rtdb, "reference", return_value="raiz"):
            def chamar():
                try:
                    saidas.append(liveideas.banco_liveideas(fs))
                except liveideas.LiveIdeasIndisponivel as exc:
                    saidas.append(exc.mensagem)
            ts = [threading.Thread(target=chamar) for _ in range(2)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        self.assertEqual(saidas, ["raiz", "raiz"])
        self.assertEqual(criados, ["liveideas"])

    def test_app_que_ja_existe_e_reaproveitado_e_nao_vira_credencial_recusada(self):
        fs = FirestoreFalso({"liveideas_conta_servico": json.dumps({"type": "service_account"})})
        with mock.patch.object(liveideas.credentials, "Certificate", return_value="cred"),              mock.patch.object(liveideas.firebase_admin, "get_app", side_effect=[ValueError("sem app"), "app"]),              mock.patch.object(liveideas.firebase_admin, "initialize_app",
                               side_effect=ValueError("The Firebase app liveideas already exists")),              mock.patch.object(liveideas.rtdb, "reference", return_value="raiz") as ref:
            self.assertEqual(liveideas.banco_liveideas(fs), "raiz")
        self.assertEqual(ref.call_args.kwargs["app"], "app")
        liveideas._apps.clear()
        with mock.patch.object(liveideas.firebase_admin, "get_app", return_value="app"),              mock.patch.object(liveideas.firebase_admin, "initialize_app") as ini,              mock.patch.object(liveideas.rtdb, "reference", return_value="raiz"):
            self.assertEqual(liveideas.banco_liveideas(FirestoreFalso(None)), "raiz")
        ini.assert_not_called()  # o app da instância já existe: nem lê o cofre


if __name__ == "__main__":
    unittest.main()
