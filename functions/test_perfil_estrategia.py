"""Perfil das metas. A fixture é a MESMA de `src/utils/perfilEstrategia.test.ts`."""
import json
import os
import unittest
from datetime import datetime

import perfil_estrategia as pe

_FIXTURE = os.path.join(os.path.dirname(__file__), "..", "src", "utils", "perfilEstrategia.fixture.json")
with open(_FIXTURE, encoding="utf-8") as arquivo:
    F = json.load(arquivo)


class TestFixtureCompartilhada(unittest.TestCase):
    def test_casos(self):
        for caso in F["casos"]:
            with self.subTest(caso["nome"]):
                r = pe.avaliar_meta(F["metas"][caso["meta"]], caso["atuais"], caso["hoje"])
                self.assertEqual(r["estado"], caso["estado"])
                self.assertEqual((r["proximo_marco"] or {}).get("data"), caso["proximo_marco"])
                por_chave = {i["chave"]: i for i in r["indicadores"]}
                if "indicadores" in caso:
                    self.assertEqual(sorted(por_chave), sorted(caso["indicadores"]))
                for chave, esperado in caso.get("indicadores", {}).items():
                    obtido = por_chave[chave]
                    self.assertEqual(obtido["esperado_hoje"], esperado["esperado_hoje"])
                    self.assertEqual(obtido["estado"], esperado["estado"])
                    if "atual" in esperado:
                        self.assertEqual(obtido["atual"], esperado["atual"])
                    if "proximo_valor" in esperado:
                        self.assertEqual((obtido["proximo_marco"] or {}).get("valor"), esperado["proximo_valor"])
                if "marcos_sem_numero" in caso:
                    self.assertEqual({m["id"]: m["estado"] for m in r["marcos_sem_numero"]}, caso["marcos_sem_numero"])

    def test_hoje_em_brasilia_na_virada_utc(self):
        for caso in F["hoje_brasilia"]:
            agora = datetime.fromisoformat(caso["utc"].replace("Z", "+00:00"))
            self.assertEqual(pe.hoje_brasilia(agora), caso["hoje"])

    def test_hoje_invalido_e_recusado(self):
        for hoje in F["hoje_invalido"]:
            with self.subTest(hoje), self.assertRaises(ValueError):
                pe.avaliar_meta(F["metas"]["saude"], {"peso": 90}, hoje)

    def test_guardado_acumulado_mesma_regra_do_bolso(self):
        from bolso_aquisicoes import guardado_acumulado

        g = F["guardado_acumulado"]
        for caso in g["casos"]:
            with self.subTest(caso["desde"]):
                self.assertEqual(guardado_acumulado(g["contas"], caso["desde"]), caso["centavos"])
        self.assertEqual(guardado_acumulado([], "2026-11-02"), 0)  # outubro sem poupança: zero, não "sem dado"

    def test_id_legado_estavel(self):
        for caso in F["id_legado"]:
            self.assertEqual(pe.id_legado(caso["tipo"], caso["indice"], caso["descricao"]), caso["id"])


class TestRegras(unittest.TestCase):
    def test_dinheiro_sai_em_centavos_inteiros(self):
        r = pe.avaliar_meta(F["metas"]["financeira"], {"guardado": "1234.565"}, "2026-12-15")
        guardado = r["indicadores"][0]
        self.assertIsInstance(guardado["atual"], int)
        self.assertIsInstance(guardado["esperado_hoje"], int)
        self.assertEqual(guardado["atual"], 123457)  # meio-para-cima, como bolso_aquisicoes.centavos

    def test_valor_ilegivel_e_sem_dado_e_nao_zero(self):
        for ruim in (None, "", "abc", "NaN", True):
            with self.subTest(ruim):
                r = pe.avaliar_meta(F["metas"]["saude"], {"peso": ruim, "cintura": 107}, "2026-12-15")
                self.assertEqual((r["indicadores"][0]["estado"], r["indicadores"][0]["atual"]), ("sem_dado", None))

    def test_data_com_hora_e_lida_pelo_texto(self):
        meta = dict(F["metas"]["saude"], ciclo={"inicio": "2026-11-02T00:00:00.000Z", "fim": "2027-01-30"})
        self.assertEqual(pe.esperado_em(meta, meta["indicadores"][0], "2026-12-15T23:59:00-03:00"), 9080)

    def test_alvo_final_fecha_o_ciclo_sem_marco_com_numero(self):
        meta = {"ciclo": {"inicio": "2026-11-02", "fim": "2027-01-30"},
                "indicadores": [{"chave": "peso", "inicial": 93.4, "alvoFinal": 88}]}
        self.assertEqual(pe.esperado_em(meta, meta["indicadores"][0], "2027-01-30"), 8800)
        self.assertEqual(pe.esperado_em(meta, meta["indicadores"][0], "2026-11-02"), 9340)

    def test_sem_trajetoria_nao_avalia(self):
        meta = {"indicadores": [{"chave": "peso"}]}
        r = pe.avaliar_meta(meta, {"peso": 90}, "2026-12-15")
        self.assertEqual((r["indicadores"][0]["estado"], r["estado"]), (None, None))


if __name__ == "__main__":
    unittest.main()
