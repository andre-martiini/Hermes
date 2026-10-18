"""`consultar_memoria_suspeita` -- P06 sub-entrega 7/N."""

import unittest
from types import SimpleNamespace
from unittest import mock

from autonomy import memoria_suspeita as ms
from tools import consultar_memoria_suspeita as cms
from tools import hermes_tools


def _resultado(n_achados=3, truncado=False, lidos=10):
    rel = tuple(
        ms.MemoriaSuspeita(
            doc_id=f"d{i}",
            sinais=(ms.SinalSuspeita("sem_proveniencia", "origem_fato", "ausente"),),
        )
        for i in range(n_achados)
    )
    return ms.ResultadoVarredura(relatorio=rel, documentos_lidos=lidos, truncado=truncado)


class ConsultarMemoriaSuspeitaTest(unittest.TestCase):
    def _chamar(self, args, resultado):
        with mock.patch.object(ms, "varrer_knowledge_nodes", return_value=resultado):
            return cms.consultar(SimpleNamespace(db=object()), args)

    def test_devolve_totais_contagem_e_achados(self):
        r = self._chamar({}, _resultado(3, truncado=True, lidos=10))
        self.assertEqual(r["documentos_lidos"], 10)
        self.assertTrue(r["truncado"])
        self.assertEqual(r["total_com_sinais"], 3)
        self.assertEqual(r["contagem_por_sinal"]["sem_proveniencia"], 3)
        self.assertEqual(r["omitidos"], 0)
        self.assertEqual(r["achados"][0], {
            "doc_id": "d0",
            "sinais": [{"sinal": "sem_proveniencia", "campo": "origem_fato", "evidencia": "ausente"}],
        })

    def test_limite_corta_achados_e_conta_omitidos(self):
        r = self._chamar({"limite": 2}, _resultado(5))
        self.assertEqual(len(r["achados"]), 2)
        self.assertEqual(r["omitidos"], 3)
        self.assertEqual(r["total_com_sinais"], 5)

    def test_limite_invalido_ou_extremo(self):
        self.assertEqual(cms._limite(None), 50)
        self.assertEqual(cms._limite("abc"), 50)
        self.assertEqual(cms._limite(0), 50)
        self.assertEqual(cms._limite(-5), 1)
        self.assertEqual(cms._limite(10_000), 200)

    def test_erro_de_leitura_nao_vira_relatorio_parcial(self):
        with mock.patch.object(ms, "varrer_knowledge_nodes", side_effect=RuntimeError("segredo-interno")):
            r = cms.consultar(SimpleNamespace(db=object()), {})
        self.assertEqual(set(r), {"erro"})
        self.assertNotIn("segredo-interno", r["erro"])

    def test_limite_bool_e_infinito_viram_padrao(self):
        self.assertEqual(cms._limite(True), 50)
        self.assertEqual(cms._limite(float("inf")), 50)

    def test_resposta_traz_aviso_de_conteudo_nao_confiavel(self):
        self.assertIn("nunca ordem", self._chamar({}, _resultado(0))["aviso"])

    def test_varredura_real_so_le(self):
        class Q:
            def __init__(self, docs): self.docs, self.n = docs, 0
            def order_by(self, *_): return self
            def limit(self, n): self.n = n; return self
            def start_after(self, _): return self
            def stream(self): return iter(self.docs[: self.n])
            def __getattr__(self, nome):
                raise AssertionError(f"chamada proibida: {nome}")
        class Snap:
            id = "d1"
            def to_dict(self): return {"texto": "x"}
        class Db:
            def collection(self, _): return Q([Snap()])
        r = cms.consultar(SimpleNamespace(db=Db()), {})
        self.assertEqual(r["documentos_lidos"], 1)
        self.assertNotIn("erro", r)

    def test_handler_registrado_e_sem_escrita(self):
        self.assertIn("consultar_memoria_suspeita", hermes_tools._HANDLERS)
        with mock.patch.object(ms, "varrer_knowledge_nodes", return_value=_resultado(1)) as v:
            r = hermes_tools._HANDLERS["consultar_memoria_suspeita"](SimpleNamespace(db="DB"), {})
        v.assert_called_once_with("DB")
        self.assertEqual(r["total_com_sinais"], 1)


if __name__ == "__main__":
    unittest.main()
