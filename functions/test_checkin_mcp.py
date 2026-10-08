"""Check-in de saude por entrevista MCP: o que `registrar_saude` grava com os
campos do check-in tem de ficar igual ao que o Telegram grava (paineis e diario
leem esses campos), e `anotar_no_diario` tem de gravar a nota no formato da
tela Diario Pessoal, sem apagar o que ja existe. Sem rede e sem Firestore."""

import unittest
from datetime import date, timedelta
from unittest import mock

import telegram_utils
from test_registrar_saude import HOJE, _Colecao, _Ctx, _Doc
from tools import anotar_no_diario as diario
from tools import hermes_tools
from tools import registrar_saude as rs

ONTEM = (date.fromisoformat(HOJE) - timedelta(days=1)).isoformat()


def _log(ctx, dia=HOJE):
    return ctx.db.cols[rs.COL_LOGS].dados[dia]


class _Union(list):
    """ArrayUnion falso; o `_Doc.set` do fake mescla raso, entao `_set_com_union` resolve."""


_set_original = _Doc.set


def _set_com_union(self, valores, merge=False):
    atual = (self._col.dados.get(self.id) or {}) if merge else {}
    valores = {k: list(atual.get(k) or []) + [x for x in v if x not in (atual.get(k) or [])]
               if isinstance(v, _Union) else v for k, v in valores.items()}
    _set_original(self, valores, merge)


class TestCamposDoCheckin(unittest.TestCase):
    def test_opcoes_iguais_as_do_telegram(self):
        self.assertEqual(rs._OPCOES_RADICULAR, [v for v, _ in telegram_utils._HEALTH_RADICULAR_LOCATIONS])
        self.assertEqual(rs._OPCOES_TERAPIA, [v for v, _ in telegram_utils._HEALTH_THERAPY_MODALITIES])
        self.assertEqual(rs._OPCOES_GATILHO, [v for v, _ in telegram_utils._HEALTH_TRIGGER_TYPES])

    def test_grava_nos_campos_e_formatos_do_telegram(self):
        ctx = _Ctx()
        r = rs.registrar(ctx, {
            "bem_estar": 7, "radicular_local": "coxa", "treino_forca": True,
            "terapia": ["pilates"], "alimentacao": "parcial", "proteina": False,
            "medicacao": "nada", "gatilhos": ["estresse"],
        })
        self.assertEqual(r["status"], "completed")
        doc = _log(ctx)
        self.assertEqual(doc["wellbeing"], 7)
        self.assertEqual(doc["radicular"], {"location": "coxa"})
        self.assertEqual(doc["strength"], {"done": True})
        self.assertEqual(doc["therapy"], ["pilates"])
        self.assertEqual(doc["nutrition"], {"plan": "parcial", "proteinTarget": False})
        self.assertEqual(doc["meds"], {"pregabalina": False, "dipirona": 0, "adorlan": 0, "fexofenadina": False})
        self.assertEqual(doc["triggers"], {"types": ["estresse"]})

    def test_nenhum_vira_lista_vazia_como_no_telegram(self):
        ctx = _Ctx()
        rs.registrar(ctx, {"terapia": ["nenhuma"], "gatilhos": "nenhum"})
        self.assertEqual((_log(ctx)["therapy"], _log(ctx)["triggers"]["types"]), ([], []))

    def test_preserva_subcampos_que_o_painel_grava(self):
        ctx = _Ctx()
        ctx.db.cols[rs.COL_LOGS] = _Colecao({HOJE: {
            "radicular": {"location": "pe", "side": "direito", "intensity": 4},
            "strength": {"done": False, "block": "A"},
            "triggers": {"types": [], "note": "viagem"},
            "entrySource": "painel"}})
        rs.registrar(ctx, {"radicular_local": "joelho", "treino_forca": True, "gatilhos": ["outro"]})
        doc = _log(ctx)
        self.assertEqual(doc["radicular"], {"location": "joelho", "side": "direito", "intensity": 4})
        self.assertEqual(doc["strength"], {"done": True, "block": "A"})
        self.assertEqual(doc["triggers"], {"types": ["outro"], "note": "viagem"})
        self.assertEqual(doc["entrySource"], "painel")

    def test_medicacao_igual_ontem_copia_o_dia_anterior(self):
        ctx = _Ctx()
        meds = {"pregabalina": True, "dipirona": 2, "adorlan": 0, "fexofenadina": False}
        ctx.db.cols[rs.COL_LOGS] = _Colecao({ONTEM: {"meds": meds}})
        rs.registrar(ctx, {"medicacao": "igual_ontem"})
        self.assertEqual(_log(ctx)["meds"], meds)

    def test_opcao_invalida_e_recusada_sem_gravar(self):
        for args in ({"radicular_local": "ombro"}, {"terapia": ["yoga"]}, {"alimentacao": "talvez"},
                     {"medicacao": "dipirona"}, {"gatilhos": ["chuva"]}, {"bem_estar": 11},
                     {"caminhada_km": 0}, {"caminhada_min": 30}):
            with self.subTest(args=args):
                ctx = _Ctx()
                r = rs.registrar(ctx, args)
                self.assertIn("erro", r)
                self.assertFalse(r["aplicado"])
                self.assertNotIn(rs.COL_LOGS, ctx.db.cols)


class TestCaminhada(unittest.TestCase):
    def test_vira_walk_block_que_o_painel_soma(self):
        ctx = _Ctx()
        ctx.db.cols[rs.COL_LOGS] = _Colecao({HOJE: {"walkBlocks": [{"id": "walk_1", "distance": 2.0, "source": "web"}]}})
        rs.registrar(ctx, {"caminhada_km": "3,5", "caminhada_min": 40})
        blocos = _log(ctx)["walkBlocks"]
        self.assertEqual(blocos[0], {"id": "walk_1", "distance": 2.0, "source": "web"})
        self.assertEqual({k: blocos[1][k] for k in ("id", "distance", "minutes", "source")},
                         {"id": f"walk_mcp_{HOJE}", "distance": 3.5, "minutes": 40, "source": "mcp"})
        self.assertRegex(blocos[1]["time"], r"^\d\d:\d\d$")

    def test_repetir_substitui_nao_duplica(self):
        ctx = _Ctx()
        rs.registrar(ctx, {"caminhada_km": 3})
        rs.registrar(ctx, {"caminhada_km": 4.2})
        blocos = _log(ctx)["walkBlocks"]
        self.assertEqual([b["distance"] for b in blocos], [4.2])


class TestAnotarNoDiario(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(diario.firestore, "ArrayUnion", side_effect=_Union),
                  mock.patch.object(_Doc, "set", _set_com_union)):
            p.start()
            self.addCleanup(p.stop)

    def test_acrescenta_no_formato_da_ui_sem_sobrescrever(self):
        ctx = _Ctx()
        ctx.db.cols[diario.COLECAO] = _Colecao({HOJE: {
            "data": HOJE, "texto": "diario ja gerado", "notas_manuais": [{"texto": "antes", "em": "x"}]}})
        r = hermes_tools.execute("anotar_no_diario", {"texto": "  Dia pesado, dormi mal.  ", "origem": "checkin_manha"}, ctx)
        self.assertEqual(r["status"], "completed")
        doc = ctx.db.cols[diario.COLECAO].dados[HOJE]
        self.assertEqual(doc["texto"], "diario ja gerado")
        self.assertEqual(len(doc["notas_manuais"]), 2)
        nota = doc["notas_manuais"][1]
        self.assertEqual((nota["texto"], nota["origem"]), ("Dia pesado, dormi mal.", "checkin_manha"))
        self.assertRegex(nota["em"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")

    def test_data_explicita(self):
        ctx = _Ctx()
        diario.anotar(ctx.db, "ontem foi bom", data=ONTEM)
        self.assertEqual(ctx.db.cols[diario.COLECAO].dados[ONTEM]["data"], ONTEM)

    def test_erros_prefixados_e_nada_gravado(self):
        ctx = _Ctx()
        for args in ({"texto": "   "}, {"texto": "x" * 4001}, {"texto": "ok", "data": "08/10/2026"}):
            with self.subTest(args=args):
                self.assertTrue(hermes_tools.execute("anotar_no_diario", args, ctx).startswith("ERRO|"))
        self.assertNotIn(diario.COLECAO, ctx.db.cols)

    def test_gerador_do_diario_le_a_nota(self):
        """`personal_diary._collect_diary_material` le `notas_manuais[].texto`."""
        ctx = _Ctx()
        diario.anotar(ctx.db, "nota do check-in")
        notas = ctx.db.cols[diario.COLECAO].dados[HOJE]["notas_manuais"]
        self.assertEqual([str(n.get("texto")).strip() for n in notas if isinstance(n, dict)], ["nota do check-in"])


if __name__ == "__main__":
    unittest.main()
