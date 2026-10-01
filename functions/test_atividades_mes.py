"""consultar_atividades_mes: o dia a dia do mes para o registro da execucao do PGD."""

import types
import unittest
from datetime import datetime, timezone

from tools import atividades_mes as am


def _tarefa(tid, titulo, area="CLC", diario=(), status="em andamento", conclusao=None, processo=None):
    return {"id": tid, "titulo": titulo, "area_tematica": area, "status": status, "processo_sei": processo,
            "data_conclusao": conclusao, "acompanhamento": [{"data": d, "nota": n} for d, n in diario]}


def _dia(resultado, data):
    return next((d for d in resultado["dias"] if d["data"] == data), None)


class TestDataLocal(unittest.TestCase):
    def test_nota_das_22h_de_brasilia_fica_no_mesmo_dia(self):
        # 01:30 UTC de 16/09 = 22:30 de 15/09 em Brasília.
        self.assertEqual(am.data_local("2026-09-16T01:30:00+00:00"), "2026-09-15")
        self.assertEqual(am.data_local("2026-09-16T01:30:00Z"), "2026-09-15")
        self.assertEqual(am.data_local(datetime(2026, 9, 16, 1, 30, tzinfo=timezone.utc)), "2026-09-15")

    def test_so_data_e_vazio(self):
        self.assertEqual(am.data_local("2026-09-15"), "2026-09-15")
        self.assertIsNone(am.data_local(None))
        self.assertIsNone(am.data_local(""))


class TestFeriados(unittest.TestCase):
    def test_fixos_e_moveis_de_2026(self):
        f = am.feriados_nacionais(2026)
        self.assertEqual(f["2026-09-07"], ("Independência do Brasil", "feriado"))
        self.assertEqual(f["2026-11-20"][1], "feriado")
        self.assertEqual(f["2026-04-03"], ("Sexta-feira Santa", "feriado"))      # Páscoa em 05/04/2026
        self.assertEqual(f["2026-02-16"], ("Carnaval", "ponto_facultativo"))
        self.assertEqual(f["2026-06-04"], ("Corpus Christi", "ponto_facultativo"))


class TestMontarMes(unittest.TestCase):
    def setUp(self):
        self.tarefas = [
            _tarefa("a1", "Pregão de material de enfermaria", diario=[
                ("2026-09-01T13:00:00+00:00", "Conferi as propostas dos itens 24 e 33."),
                ("2026-09-02T01:30:00+00:00", "Mandei o parecer à pregoeira."),          # 22h30 de 01/09
                ("2026-09-01T14:00:00+00:00", "[Copiloto Gaspar] Ação editada via card de confirmação. Campos alterados: status."),
            ], processo="23543.000431/2023-39"),
            _tarefa("a2", "Auxílio estudantil de setembro", area="ASSISTÊNCIA ESTUDANTIL", diario=[
                ("2026-09-03T12:00:00+00:00", "Validei a folha do campus."),
            ], status="concluído", conclusao="2026-09-04T18:00:00+00:00"),
            _tarefa("p1", "Reforma da casa", area="FAMÍLIA", diario=[("2026-09-01T12:00:00+00:00", "Orçamento do pintor.")]),
            _tarefa("x1", "Ação excluída", diario=[("2026-09-01T12:00:00+00:00", "não conta")], status="excluído"),
            _tarefa("o1", "De outro mês", diario=[("2026-08-31T12:00:00+00:00", "agosto")]),
        ]

    def test_agrupa_por_dia_no_fuso_de_brasilia_e_ignora_nota_automatica(self):
        r = am.montar_mes(self.tarefas, "2026-09")
        a1 = next(a for a in _dia(r, "2026-09-01")["atividades"] if a["acao_id"] == "a1")
        self.assertEqual(a1["notas"], ["Conferi as propostas dos itens 24 e 33.", "Mandei o parecer à pregoeira."])
        self.assertEqual(a1["total_notas"], 2)
        self.assertEqual(a1["processo_sei"], "23543.000431/2023-39")
        self.assertEqual(_dia(r, "2026-09-02")["atividades"], [])

    def test_familia_excluida_e_status_excluido_fora(self):
        r = am.montar_mes(self.tarefas, "2026-09")
        ids = {a["acao_id"] for d in r["dias"] for a in d["atividades"]}
        self.assertEqual(ids, {"a1", "a2"})
        self.assertEqual(r["acoes_no_mes"], 2)

    def test_conclusao_no_mes_marca_o_dia(self):
        r = am.montar_mes(self.tarefas, "2026-09")
        a2 = _dia(r, "2026-09-04")["atividades"][0]
        self.assertTrue(a2["concluida_no_dia"])
        self.assertEqual(a2["notas"], [])

    def test_feriado_em_dia_de_semana_aparece_e_nao_e_util(self):
        r = am.montar_mes(self.tarefas, "2026-09")
        d = _dia(r, "2026-09-07")
        self.assertFalse(d["util"])
        self.assertEqual(d["feriado"]["nome"], "Independência do Brasil")
        self.assertNotIn("2026-09-07", r["dias_uteis_sem_atividade"])

    def test_fim_de_semana_sem_atividade_some_e_dias_uteis_vazios_sao_listados(self):
        r = am.montar_mes(self.tarefas, "2026-09")
        self.assertIsNone(_dia(r, "2026-09-05"))                    # sábado sem nada
        self.assertIn("2026-09-02", r["dias_uteis_sem_atividade"])  # quarta sem nada
        self.assertNotIn("2026-09-01", r["dias_uteis_sem_atividade"])

    def test_areas_restringem(self):
        r = am.montar_mes(self.tarefas, "2026-09", areas=["assistência estudantil"])
        ids = {a["acao_id"] for d in r["dias"] for a in d["atividades"]}
        self.assertEqual(ids, {"a2"})
        self.assertIn("2026-09-01", r["dias_uteis_sem_atividade"])

    def test_recorte_de_dias(self):
        r = am.montar_mes(self.tarefas, "2026-09", de=3, ate=4)
        self.assertEqual([d["data"] for d in r["dias"]], ["2026-09-03", "2026-09-04"])
        self.assertEqual(r["periodo"], "2026-09-03 a 2026-09-04")

    def test_sem_notas_traz_so_contagem(self):
        r = am.montar_mes(self.tarefas, "2026-09", com_notas=False)
        a1 = next(a for a in _dia(r, "2026-09-01")["atividades"] if a["acao_id"] == "a1")
        self.assertNotIn("notas", a1)
        self.assertEqual(a1["total_notas"], 2)

    def test_limite_de_notas_por_acao_e_dia_e_corte_do_texto(self):
        muitas = [("2026-09-10T12:00:00+00:00", f"nota {i} " + "x" * 400) for i in range(7)]
        r = am.montar_mes([_tarefa("m1", "Muita coisa", diario=muitas)], "2026-09")
        item = _dia(r, "2026-09-10")["atividades"][0]
        self.assertEqual(len(item["notas"]), am.MAX_NOTAS_POR_ACAO_DIA)
        self.assertEqual(item["total_notas"], 7)
        self.assertTrue(all(len(n) <= am.MAX_CHARS_NOTA for n in item["notas"]))
        self.assertTrue(item["notas"][0].endswith("…"))


class TestConsultar(unittest.TestCase):
    def _ctx(self, tarefas):
        snaps = [types.SimpleNamespace(id=t["id"], to_dict=lambda t=t: {k: v for k, v in t.items() if k != "id"})
                 for t in tarefas]
        db = types.SimpleNamespace(collection=lambda nome: types.SimpleNamespace(stream=lambda: snaps))
        return types.SimpleNamespace(db=db)

    def test_le_tarefas_e_aplica_o_padrao_de_familia(self):
        ctx = self._ctx([_tarefa("p1", "Casa", area="FAMÍLIA", diario=[("2026-09-01T12:00:00+00:00", "x")])])
        r = am.consultar(ctx, {"mes": "2026-09"})
        self.assertEqual(r["acoes_no_mes"], 0)
        self.assertEqual(r["areas_excluidas"], ["FAMÍLIA"])

    def test_argumentos_invalidos(self):
        ctx = self._ctx([])
        self.assertIn("erro", am.consultar(ctx, {"mes": "09/2026"}))
        self.assertIn("erro", am.consultar(ctx, {"mes": "2026-13"}))
        self.assertIn("erro", am.consultar(ctx, {"mes": "2026-09", "areas": "CLC"}))
        self.assertIn("erro", am.consultar(ctx, {"mes": "2026-09", "dia_inicio": 10, "dia_fim": 5}))
        self.assertIn("erro", am.consultar(ctx, {"mes": "2026-09", "dia_inicio": "x"}))

    def test_despachante_do_mcp_chega_na_tool(self):
        from tools import hermes_tools
        r = hermes_tools.execute("consultar_atividades_mes", {"mes": "2026-09", "com_notas": False}, self._ctx([]))
        self.assertEqual(r["mes"], "2026-09")


if __name__ == "__main__":
    unittest.main()
