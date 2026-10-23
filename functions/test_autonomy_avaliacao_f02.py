import unittest

from autonomy.avaliacao_f02 import (
    CASOS_F02, LIMIAR_PRECISAO, MIN_FECHADOS, CasoF02, medir_precisao_cumprimento,
)
from autonomy.correlacao_entregaveis import Evidencia, correlacionar, vinculo_firme


class AvaliacaoF02Test(unittest.TestCase):
    def test_corpus_passa_no_limiar_da_secao_11(self):
        r = medir_precisao_cumprimento()
        self.assertEqual(r["falsos_fechamentos"], [])
        self.assertGreaterEqual(r["precisao"], LIMIAR_PRECISAO)
        self.assertTrue(r["aprovado"])
        self.assertGreaterEqual(r["fechados"], 3)
        self.assertEqual(r["total"], len(CASOS_F02))

    def test_corpus_tem_positivos_e_negativos(self):
        self.assertTrue(any(c.cumpre for c in CASOS_F02))
        self.assertGreaterEqual(sum(1 for c in CASOS_F02 if not c.cumpre), 10)

    def test_falso_fechamento_reprova(self):
        # Caso rotulado "não cumpre" que o avaliador fecha derruba a precisão.
        ruim = CASOS_F02 + (CasoF02("Te envio o relatório amanhã", "Segue o relatório", False, False, ""),)
        r = medir_precisao_cumprimento(ruim)
        self.assertEqual(len(r["falsos_fechamentos"]), 1)
        self.assertFalse(r["aprovado"])
        self.assertLess(r["precisao"], LIMIAR_PRECISAO)

    def test_sem_fechamento_nao_aprova(self):
        r = medir_precisao_cumprimento((CasoF02("Te envio o relatório", "Bom dia", False, False, ""),))
        self.assertIsNone(r["precisao"])
        self.assertFalse(r["aprovado"])

    def test_amostra_pequena_nao_aprova(self):
        r = medir_precisao_cumprimento((CasoF02("Te envio o relatório", "Segue o relatório", True, False, ""),))
        self.assertEqual(r["fechados"], 1)
        self.assertLess(r["fechados"], MIN_FECHADOS)
        self.assertFalse(r["aprovado"])

    def test_so_positivos_nao_aprova(self):
        c = CasoF02("Te envio o relatório", "Segue o relatório", True, False, "")
        r = medir_precisao_cumprimento((c,) * 3)
        self.assertEqual(r["precisao"], 1.0)
        self.assertFalse(r["aprovado"])

    def test_corpus_fecha_todos_os_positivos(self):
        self.assertEqual(medir_precisao_cumprimento()["revocacao"], 1.0)

    def test_entradas_invalidas(self):
        c = CasoF02("Te envio o relatório", "Segue o relatório", True, False, "")
        for limiar in (0, -1, 0.5, 2, True, "0.9", float("nan")):
            with self.assertRaises(ValueError):
                medir_precisao_cumprimento((c,), limiar)
        def quebra():
            yield 1
            raise RuntimeError

        class Forjado(CasoF02):
            cumpre = property(lambda self: True)

        forjado = Forjado("Te envio o relatório", "Segue o relatório", False, False, "")
        for casos in (None, {"a": 1}, "abc", (forjado,) * 3,
                      (CasoF02("a", None, True, False, ""),),
                      (CasoF02("a", "b", True, "x", ""),),
                      quebra(), ("x",), (CasoF02("a", "b", "nao", False, ""),)):
            with self.assertRaises(ValueError):
                medir_precisao_cumprimento(casos)
        self.assertEqual(medir_precisao_cumprimento(iter(CASOS_F02))["total"], len(CASOS_F02))

    def test_corpus_vazio_nao_aprova(self):
        r = medir_precisao_cumprimento(())
        self.assertEqual(r["total"], 0)
        self.assertFalse(r["aprovado"])

    def test_aceite_arquivo_por_email_encerra_promessa_do_whatsapp(self):
        v = correlacionar(
            "Te mando o contrato assinado amanhã",
            [Evidencia("gmail", "msg-123", "Contrato assinado", ("DOC-7",))],
            ("DOC-7",),
        )
        self.assertTrue(vinculo_firme(v))
        self.assertEqual(v[0].canal, "gmail")

    def test_aceite_so_semantico_nao_fecha(self):
        v = correlacionar(
            "Te mando o contrato assinado amanhã",
            [Evidencia("gmail", "msg-9", "Contrato assinado", ())],
            ("DOC-7",),
        )
        self.assertFalse(vinculo_firme(v))


if __name__ == "__main__":
    unittest.main()
