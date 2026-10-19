"""liveideas_ler com incluir_transcricao (cursor apos_seq, teto e estado)."""
import unittest

from test_liveideas_tools import LINK_P, PROC, REUN, Base
from tools import hermes_tools
from tools import liveideas_tools as lt

LINK_R = f"https://liveideas.web.app/#/ler/r/{REUN}"


class LerTranscricaoTest(Base):
    def setUp(self):
        super().setUp()
        self.linhas = [{"seq": i, "t": f"00:00:{i:02d}", "falante": "Falante A", "texto": f"fala {i:02d} " + "x" * 492}
                       for i in range(1, 11)]  # 10 falas de 500 caracteres
        self.estado = "ao_vivo"
        self.respostas["ler"] = self._notebook

    def _notebook(self, corpo):
        """Como o notebook atualizado: linhas inteiras depois de `apos`, até `max`."""
        saida = {"texto": "diagrama", "link": LINK_R, "titulo": "Webinário", "tipo": "fluxo"}
        tr = corpo.get("transcricao")
        if tr is not None:
            trechos, usados = [], 0
            for linha in self.linhas:
                if linha["seq"] <= tr["apos"]:
                    continue
                if trechos and usados + len(linha["texto"]) > tr["max"]:
                    break
                trechos.append(linha)
                usados += len(linha["texto"])
            proximo = trechos[-1]["seq"] if trechos else tr["apos"]
            saida["transcricao"] = {"trechos": trechos, "proximo_seq": proximo, "ultimo_seq": self.linhas[-1]["seq"],
                                    "truncado": proximo < self.linhas[-1]["seq"], "estado": self.estado}
        return 200, saida

    def ler(self, **args):
        return hermes_tools.execute("liveideas_ler", {"reuniao_id": REUN, **args}, self.ctx)

    def test_sem_pedido_nada_muda(self):
        r = self.ler()
        self.assertEqual(r, {"texto": "diagrama", "link": LINK_R, "titulo": "Webinário", "tipo": "fluxo"})
        self.assertEqual(self.chamadas, [("ler", {"reuniao": REUN})])

    def test_false_explicito_nao_pede(self):
        for valor in (False, "false", None, "nao", {"x": 1}, [1]):
            self.ler(incluir_transcricao=valor, apos_seq=3)
        self.assertEqual(self.chamadas, [("ler", {"reuniao": REUN})] * 6)

    def test_cursor_e_teto(self):
        r = self.ler(incluir_transcricao=True, max_caracteres_transcricao=2000)
        self.assertEqual(self.chamadas, [("ler", {"reuniao": REUN, "transcricao": {"apos": 0, "max": 2000}})])
        tr = r["transcricao"]
        self.assertEqual([t["seq"] for t in tr["trechos"]], [1, 2, 3, 4])
        self.assertEqual((tr["proximo_seq"], tr["ultimo_seq"], tr["truncado"], tr["estado"]), (4, 10, True, "ao_vivo"))
        self.assertIn("apos_seq=4", tr["orientacao"])
        self.assertEqual(r["texto"], "diagrama")

        vistos, cursor = [], 0
        for _ in range(10):
            tr = self.ler(incluir_transcricao=True, apos_seq=cursor, max_caracteres_transcricao=2000)["transcricao"]
            vistos += [t["seq"] for t in tr["trechos"]]
            cursor = tr["proximo_seq"]
            if not tr["truncado"]:
                break
        self.assertEqual(vistos, list(range(1, 11)))
        self.assertIn("~30 s", tr["orientacao"])

    def test_padrao_e_limites(self):
        self.ler(incluir_transcricao=True)
        self.ler(incluir_transcricao="true", apos_seq="x", max_caracteres_transcricao=5)
        self.ler(incluir_transcricao=True, apos_seq=-3, max_caracteres_transcricao=10**9)
        self.assertEqual([c[1]["transcricao"] for c in self.chamadas],
                         [{"apos": 0, "max": 12000}, {"apos": 0, "max": 1000}, {"apos": 0, "max": 50000}])

    def test_teto_reaplicado_no_gaspar(self):
        """Notebook que ignora o teto (ou com defeito) não estoura a conversa nem repete o que já foi lido."""
        self.respostas["ler"] = (200, {"texto": "d", "transcricao": {
            "trechos": self.linhas, "proximo_seq": 10, "ultimo_seq": 10, "truncado": False, "estado": "ao_vivo"}})
        tr = self.ler(incluir_transcricao=True, apos_seq=2, max_caracteres_transcricao=1000)["transcricao"]
        self.assertEqual([t["seq"] for t in tr["trechos"]], [3, 4])
        self.assertEqual((tr["proximo_seq"], tr["truncado"]), (4, True))

    def test_encerrada(self):
        self.estado = "encerrada"
        tr = self.ler(incluir_transcricao=True, apos_seq=10)["transcricao"]
        self.assertEqual((tr["trechos"], tr["proximo_seq"], tr["truncado"], tr["estado"]), ([], 10, False, "encerrada"))
        self.assertIn("encerrada", tr["orientacao"])

    def test_notebook_antigo_avisa(self):
        self.respostas["ler"] = (200, {"texto": "d", "link": LINK_R})
        r = self.ler(incluir_transcricao=True)
        self.assertEqual(r["texto"], "d")
        self.assertIn("atualizar-servidor.ps1", r["transcricao"]["erro"])

    def test_transcricao_nao_vaza_sem_pedido(self):
        self.respostas["ler"] = (200, {"texto": "d", "transcricao": {"trechos": self.linhas}})
        self.assertNotIn("transcricao", self.ler())

    def test_processo_recusa_sem_chamar(self):
        self.respostas["ler"] = (200, {"texto": "t", "link": LINK_P})
        r = hermes_tools.execute("liveideas_ler", {"processo_id": PROC, "incluir_transcricao": True}, self.ctx)
        self.assertIn("erro", r)
        self.assertEqual(self.chamadas, [])

    def test_estado_desconhecido_vira_encerrada(self):
        self.estado = "outro"
        self.assertEqual(self.ler(incluir_transcricao=True)["transcricao"]["estado"], "encerrada")

    def test_schema_tem_os_parametros(self):
        import json
        import os

        with open(os.path.join(os.path.dirname(__file__), "tools", "schemas", "liveideas_ler.json"), encoding="utf-8") as f:
            props = json.load(f)["parameters"]["properties"]
        for campo in ("incluir_transcricao", "apos_seq", "max_caracteres_transcricao"):
            self.assertIn(campo, props)
        self.assertEqual(lt.TRANSCRICAO_MAX_PADRAO, 12000)


if __name__ == "__main__":
    unittest.main()
