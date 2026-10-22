import unittest

from autonomy import correlacao_entregaveis as ce
from autonomy.correlacao_entregaveis import Evidencia


class CorrelacaoTest(unittest.TestCase):
    def test_id_em_comum_atravessa_canais_e_e_firme(self):
        v = ce.correlacionar(
            "mando a planilha amanhã",
            [Evidencia("gmail", "m1", "x.pdf", ("drive:1",)), Evidencia("whatsapp", "w1", "", ("outro",))],
            ["drive:1"],
        )
        self.assertEqual([(x.ref, x.tipo, x.incerta) for x in v], [("m1", ce.VINCULO_ID, False)])
        self.assertTrue(ce.vinculo_firme(v))

    def test_so_objeto_e_semantico_e_incerto(self):
        v = ce.correlacionar("envio o relatório", [Evidencia("documento", "d1", "Relatorio_final.docx")])
        self.assertEqual(len(v), 1)
        self.assertTrue(v[0].incerta)
        self.assertFalse(ce.vinculo_firme(v))

    def test_objeto_diferente_ou_sem_objeto_nao_vincula(self):
        self.assertEqual(ce.correlacionar("envio o relatório", [Evidencia("gmail", "m", "foto.jpg")]), ())
        self.assertEqual(ce.correlacionar("te retorno amanhã", [Evidencia("gmail", "m", "planilha.xlsx")]), ())

    def test_entradas_invalidas_viram_valueerror(self):
        ev = Evidencia("gmail", "m")
        for args in [(1, [ev]), ("a", "x"), ("a", [ev], "abc"), ("a", [("gmail", "m")]), ("a", [ev], [1])]:
            with self.assertRaises(ValueError):
                ce.correlacionar(*args)
        class C(str):
            __eq__ = lambda s, o: True
            __hash__ = str.__hash__

        V = ce.Vinculo

        class S(str):
            def __eq__(s, o):
                raise RuntimeError("x")
            __hash__ = str.__hash__

        incompleto = V("r", "gmail", "id", False, "m")
        object.__delattr__(incompleto, "motivo")
        with self.assertRaises(ValueError):
            ce.vinculo_firme([incompleto])
        with self.assertRaises(ValueError):
            ce.vinculo_firme([V("r", "gmail", S("id"), False, "m")])
        for bad in (None, [1], [V("", "sms", "id", False, "")], [V("r", "gmail", "id", 0, "x")],
                    [V("r", "gmail", "semantico", False, "x")], [V("r", "gmail", "id", True, "x")],
                    [V("r", "sms", "id", False, "x")], [V("r", "gmail", "zzz", True, "x")]):
            with self.assertRaises(ValueError):
                ce.vinculo_firme(bad)
        for e in [Evidencia(C("zzz"), "m"), Evidencia("gmail", "a\nb"), Evidencia("gmail", " x "),
                  Evidencia("sms", "m"), Evidencia("gmail", " "), Evidencia("gmail", "m", ids=[1]),
                  Evidencia("gmail", "m", "a̶b")]:
            with self.assertRaises(ValueError):
                ce.correlacionar("a", [e])


if __name__ == "__main__":
    unittest.main()
