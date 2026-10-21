"""`obter_contexto_operacional` -- P06 sub-entrega 12/N."""

import unittest
from types import SimpleNamespace
from unittest import mock

from tools import hermes_tools
from tools import obter_contexto_operacional as oco


class _Snap:
    def __init__(self, id, dados):
        self.id, self._d = id, dados

    def to_dict(self):
        return self._d


class _Pops:
    def __init__(self, snaps):
        self.snaps = snaps

    def stream(self):
        return iter(self.snaps)

    def __getattr__(self, nome):
        raise AssertionError(f"chamada proibida: {nome}")


class _Db:
    def __init__(self, pops):
        self.pops = _Pops(pops)

    def collection(self, nome):
        assert nome == "pops_diretrizes"
        return self.pops


def _ctx(*pops):
    return SimpleNamespace(db=_Db([_Snap(i, d) for i, d in pops]))


FILA = {"total": 3, "itens": [
    {"id": "a1", "origem": "whatsapp", "tipo": "follow_up", "prioridade": "alta",
     "titulo": "T" * 600, "resumo": "r", "prazo": "2026-10-21", "acao_id": "x", "evidencia": {"k": 1}},
    {"id": "a2", "titulo": "t2"},
]}
RUNS = {"total": 1, "runs": [{"id": "r1", "rotina": "briefing", "status": "erro", "resumo": "s",
                              "erro": "boom", "criado_em": "c", "finalizado_em": None}]}
POPS = [
    ("p1", {"titulo": "Nunca enviar sem aprovar", "instrucao_sistema": "  Sempre peça aprovação.  ", "sempre_ativo": True}),
    ("p2", {"titulo": "Finanças", "instrucao_sistema": "x", "gatilhos": ["fatura", "cartão"]}),
    ("p3", {"titulo": "Vazio", "instrucao_sistema": "  "}),
]


def _patches(fila=FILA, runs=RUNS):
    return (mock.patch("atencao.coletar_fila_atencao", return_value=fila),
            mock.patch("agent_runs.listar_recentes", return_value=runs))


FILA2 = {"total": 2, "itens": FILA["itens"]}


class CursorIncrementalTest(unittest.TestCase):
    SEG = "segredo-de-teste"

    def rodar(self, args=None, uid="u1", segredo=SEG, fila=FILA2, runs=RUNS):
        ctx = SimpleNamespace(db=_Db([]), user_uid=uid)
        env = {oco.ENV_SEGREDO_CURSOR: segredo} if segredo else {}
        with mock.patch.dict("os.environ", env, clear=False), \
                mock.patch("atencao.coletar_fila_atencao", return_value=fila), \
                mock.patch("agent_runs.listar_recentes", return_value=runs):
            if not segredo:
                import os
                os.environ.pop(oco.ENV_SEGREDO_CURSOR, None)
            return oco.obter(ctx, args or {})

    def test_sem_segredo_nao_emite_cursor(self):
        r = self.rodar(segredo=None)
        self.assertNotIn("cursor", r)
        self.assertNotIn("mudancas", r)

    def test_sem_segredo_com_cursor_avisa(self):
        r = self.rodar({"desde_cursor": "x"}, segredo=None)
        self.assertTrue(any(l.startswith("cursor:") for l in r["lacunas"]))

    def test_sem_dono_nao_emite(self):
        self.assertNotIn("cursor", self.rodar(uid=None))

    def test_emite_cursor_valido_e_mudancas_so_do_novo(self):
        fila = {"total": 2, "itens": [
            {"id": "velho", "criado_em": "2020-01-01T00:00:00+00:00", "atualizado_em": "2020-01-02T00:00:00+00:00"},
            {"id": "novo", "criado_em": "2999-01-01T00:00:00+00:00"}]}
        runs = {"runs": [{"id": "rv", "criado_em": "2020-01-01T00:00:00Z", "finalizado_em": "2020-01-01T00:01:00Z"},
                         {"id": "rn", "criado_em": "2999-01-01T00:00:00Z"}]}
        primeiro = self.rodar(fila=fila, runs=runs)
        self.assertIn("cursor", primeiro)
        self.assertNotIn("mudancas", primeiro)
        r = self.rodar({"desde_cursor": primeiro["cursor"]}, fila=fila, runs=runs)
        self.assertEqual([i["id"] for i in r["mudancas"]["pendencias"]], ["novo"])
        self.assertEqual([i["id"] for i in r["mudancas"]["ultimos_resultados"]], ["rn"])
        self.assertEqual(len(r["pendencias"]["itens"]), 2)  # estado completo segue presente

    def test_carimbo_ilegivel_conta_como_mudanca(self):
        fila = {"total": 1, "itens": [{"id": "sem_data"}]}
        c = self.rodar(fila=fila)["cursor"]
        r = self.rodar({"desde_cursor": c}, fila=fila)
        self.assertEqual([i["id"] for i in r["mudancas"]["pendencias"]], ["sem_data"])

    def test_cursor_de_outro_dono_e_ignorado_com_lacuna(self):
        c = self.rodar(uid="u1")["cursor"]
        r = self.rodar({"desde_cursor": c}, uid="u2")
        self.assertNotIn("mudancas", r)
        self.assertTrue(any("inválido" in l for l in r["lacunas"]))
        self.assertEqual(len(r["pendencias"]["itens"]), 2)

    def test_cursor_adulterado_ou_nao_string_e_ignorado(self):
        for ruim in ("v1.a.b", 123, {"x": 1}, ["a"]):
            r = self.rodar({"desde_cursor": ruim})
            self.assertNotIn("mudancas", r)
            self.assertTrue(any("inválido" in l for l in r["lacunas"]))

    def test_carimbo_preenchido_ilegivel_conta_como_mudanca_mesmo_com_outro_legivel(self):
        fila = {"total": 1, "itens": [{"id": "x", "criado_em": "2020-01-01T00:00:00+00:00", "atualizado_em": "lixo"}]}
        c = self.rodar(fila=fila)["cursor"]
        r = self.rodar({"desde_cursor": c}, fila=fila)
        self.assertEqual([i["id"] for i in r["mudancas"]["pendencias"]], ["x"])

    def test_borda_igual_a_marca_conta_como_mudanca(self):
        self.assertTrue(oco._mudou_apos(1000, "1970-01-01T00:00:01+00:00"))
        self.assertFalse(oco._mudou_apos(1001, "1970-01-01T00:00:01+00:00"))

    def test_marca_tem_folga_de_relogio(self):
        from autonomy.cursor_contexto import validar_cursor
        c = self.rodar()["cursor"]
        marca = validar_cursor(self.SEG, c, "u1", oco.ESCOPO_CURSOR)
        import time
        self.assertLessEqual(marca, time.time() * 1000 - oco.MARGEM_CURSOR_MS + 5)

    def test_pendencias_acima_do_teto_de_leitura_nao_avancam_cursor_recebido(self):
        c = self.rodar()["cursor"]
        r = self.rodar({"desde_cursor": c}, fila={"total": 500, "itens": FILA["itens"]})
        self.assertEqual(r["cursor"], c)
        self.assertTrue(any("incompleta" in l for l in r["lacunas"]))

    def test_primeira_chamada_emite_cursor_mesmo_com_muitas_pendencias(self):
        self.assertIn("cursor", self.rodar(fila={"total": 500, "itens": FILA["itens"]}))

    def test_runs_no_teto_mas_todos_anteriores_a_marca_avancam_cursor(self):
        runs = {"runs": [{"id": f"r{i}", "criado_em": "2020-01-01T00:00:00Z", "finalizado_em": "2020-01-01T00:01:00Z"}
                         for i in range(oco.LEITURA_RESULTADOS)]}
        # relógio injetado e crescente: a marca é agora_ms - margem, e duas
        # chamadas no mesmo milissegundo (CI rápido) davam cursores idênticos.
        import itertools
        passo = itertools.count(1_800_000_000)
        with mock.patch("time.time", side_effect=lambda: float(next(passo))):
            c = self.rodar(runs=runs)["cursor"]
            r = self.rodar({"desde_cursor": c}, runs=runs)
        self.assertEqual(r["mudancas"]["ultimos_resultados"], [])
        self.assertNotEqual(r["cursor"], c)
        self.assertFalse(any("incompleta" in l for l in r["lacunas"]))
        self.assertTrue(any("execuções mais recentes" in l for l in r["lacunas"]))

    def test_mais_itens_que_o_limite_exibido_ainda_emite_cursor_e_mudancas_completas(self):
        runs = {"runs": [{"id": f"r{i}", "criado_em": "2020-01-01T00:00:00Z"} for i in range(30)]
                + [{"id": "novo", "criado_em": "2999-01-01T00:00:00Z"}]}
        r = self.rodar(runs=runs)
        self.assertIn("cursor", r)
        self.assertEqual(len(r["ultimos_resultados"]), 10)  # exibição segue o limite
        r2 = self.rodar({"desde_cursor": r["cursor"]}, runs=runs)
        self.assertEqual([x["id"] for x in r2["mudancas"]["ultimos_resultados"]], ["novo"])  # fora dos 10 exibidos

    def test_pendencia_alterada_alem_do_limite_exibido_aparece_em_mudancas(self):
        itens = [{"id": f"p{i}", "criado_em": "2020-01-01T00:00:00Z", "atualizado_em": "2020-01-01T00:00:00Z"} for i in range(14)]
        itens.append({"id": "alterada", "criado_em": "2020-01-01T00:00:00Z", "atualizado_em": "2999-01-01T00:00:00Z"})
        fila = {"total": 15, "itens": itens}
        c = self.rodar(fila=fila)["cursor"]
        r = self.rodar({"desde_cursor": c}, fila=fila)
        self.assertEqual([i["id"] for i in r["mudancas"]["pendencias"]], ["alterada"])
        self.assertEqual(len(r["pendencias"]["itens"]), 10)

    def test_regras_falhando_nao_bloqueia_cursor(self):
        ctx = SimpleNamespace(db=mock.Mock(), user_uid="u1")
        ctx.db.collection.side_effect = OSError("down")
        with mock.patch.dict("os.environ", {oco.ENV_SEGREDO_CURSOR: self.SEG}), \
                mock.patch("atencao.coletar_fila_atencao", return_value=FILA2), \
                mock.patch("agent_runs.listar_recentes", return_value=RUNS):
            r = oco.obter(ctx, {})
        self.assertEqual(r["fontes"]["regras"][:6], "falhou")
        self.assertIn("cursor", r)

    def test_runs_no_teto_de_leitura_nao_avancam_cursor_recebido(self):
        c = self.rodar()["cursor"]
        runs = {"runs": [{"id": f"r{i}", "criado_em": "2999-01-01T00:00:00Z"} for i in range(oco.LEITURA_RESULTADOS)]}
        r = self.rodar({"desde_cursor": c}, runs=runs)
        self.assertEqual(r["cursor"], c)
        self.assertEqual(len(r["mudancas"]["ultimos_resultados"]), oco.LEITURA_RESULTADOS)
        self.assertTrue(any("incompleta" in l for l in r["lacunas"]))

    def test_total_ausente_nao_prova_ausencia_de_corte(self):
        c = self.rodar()["cursor"]
        r = self.rodar({"desde_cursor": c}, fila={"itens": FILA["itens"]})
        self.assertEqual(r["cursor"], c)

    def test_owner_longo_demais_nao_derruba(self):
        r = self.rodar(uid="u" * 3000)
        self.assertNotIn("cursor", r)
        self.assertTrue(any("não foi possível emitir" in l for l in r["lacunas"]))

    def test_fonte_falha_nao_avanca_cursor(self):
        ctx = SimpleNamespace(db=_Db([]), user_uid="u1")
        with mock.patch.dict("os.environ", {oco.ENV_SEGREDO_CURSOR: self.SEG}), \
                mock.patch("atencao.coletar_fila_atencao", side_effect=RuntimeError("x")), \
                mock.patch("agent_runs.listar_recentes", return_value=RUNS):
            r = oco.obter(ctx, {})
        self.assertNotIn("cursor", r)


class ObterContextoOperacionalTest(unittest.TestCase):
    def rodar(self, ctx, args=None, **kw):
        a, b = _patches(**kw)
        with a as fila, b as runs:
            return oco.obter(ctx, args or {}), fila, runs

    def test_monta_as_tres_secoes(self):
        r, _, _ = self.rodar(_ctx(*POPS))
        self.assertEqual(r["fontes"], {"pendencias": "ok", "ultimos_resultados": "ok", "regras": "ok"})
        self.assertEqual(r["pendencias"]["total_aberto"], 3)
        self.assertEqual([i["id"] for i in r["pendencias"]["itens"]], ["a1", "a2"])
        self.assertNotIn("evidencia", r["pendencias"]["itens"][0])
        self.assertEqual(len(r["pendencias"]["itens"][0]["titulo"]), oco.TEXTO_MAX)
        self.assertEqual(r["ultimos_resultados"][0]["erro"], "boom")
        self.assertEqual(r["regras_sempre_ativas"], [
            {"id": "p1", "titulo": "Nunca enviar sem aprovar", "instrucao": "Sempre peça aprovação."}])
        self.assertEqual(r["regras_por_gatilho"], [
            {"id": "p2", "titulo": "Finanças", "n_gatilhos": 2, "alcancavel": True}])
        self.assertIn("dado", r["aviso"].lower())

    def test_instrucao_de_pop_sempre_ativo_nao_e_cortada(self):
        longa = "regra " * 300
        r, _, _ = self.rodar(_ctx(("p9", {"titulo": "L", "instrucao_sistema": longa, "sempre_ativo": True})))
        self.assertEqual(r["regras_sempre_ativas"][0]["instrucao"], longa.strip())

    def test_execucao_em_andamento_nao_ganha_finalizado_em(self):
        runs = {"runs": [{"id": "r", "status": "em_andamento", "criado_em": "C", "finalizado_em": None}]}
        r, _, _ = self.rodar(_ctx(), runs=runs)
        self.assertEqual((r["ultimos_resultados"][0]["criado_em"], r["ultimos_resultados"][0]["finalizado_em"]), ("C", None))

    def test_valor_nao_string_nao_vaza_objeto(self):
        fila = {"total": 1, "itens": [{"id": "a", "titulo": {"a": [1] * 999}, "resumo": ["x"] * 999}]}
        r, _, _ = self.rodar(_ctx(), fila=fila)
        self.assertEqual((r["pendencias"]["itens"][0]["titulo"], r["pendencias"]["itens"][0]["resumo"]), (None, None))

    def test_pop_malformado_e_sempre_ativo_truthy_nao_literal(self):
        r, _, _ = self.rodar(_ctx(
            ("a", {"titulo": 5, "instrucao_sistema": 7, "sempre_ativo": True}),
            ("b", {"titulo": "B", "instrucao_sistema": "ok", "sempre_ativo": "true", "gatilhos": ["g"]}),
            ("c", {"titulo": "C", "instrucao_sistema": "ok", "sempre_ativo": 1}),
        ))
        self.assertEqual(r["fontes"]["regras"], "ok")
        self.assertEqual(r["regras_sempre_ativas"], [])
        self.assertEqual([x["id"] for x in r["regras_por_gatilho"]], ["b", "c"])
        self.assertTrue(any("1 sem instrução" in l for l in r["lacunas"]))

    def test_id_repetido_usa_primeira_ocorrencia_e_nao_derruba_regras(self):
        r, _, _ = self.rodar(_ctx(
            ("d1", {"id": "x", "titulo": "A", "instrucao_sistema": "REGRA A", "sempre_ativo": True}),
            ("d2", {"id": "x", "titulo": "B"}),
        ))
        self.assertEqual(r["fontes"]["regras"], "ok")
        self.assertEqual([x["instrucao"] for x in r["regras_sempre_ativas"]], ["REGRA A"])
        self.assertTrue(any("1 POP(s) ignorado" in l for l in r["lacunas"]))

    def test_id_nao_hashavel_nao_derruba_as_regras(self):
        r, _, _ = self.rodar(_ctx(
            ("a", {"titulo": "A", "instrucao_sistema": "REGRA", "sempre_ativo": True}),
            ("b", {"id": ["x"], "instrucao_sistema": "Y"}),
        ))
        self.assertEqual(r["fontes"]["regras"], "ok")
        self.assertEqual([x["id"] for x in r["regras_sempre_ativas"]], ["a"])

    def test_campos_nao_string_e_total_invalido(self):
        fila = {"total": "muitos", "itens": [{"id": "a", "acao_id": {"x": 1}, "prazo": ["p"], "tipo": "t" * 999}]}
        runs = {"runs": [{"id": "r", "rotina": {"x": 1}, "status": ["s"], "criado_em": 5}]}
        r, _, _ = self.rodar(_ctx(), fila=fila, runs=runs)
        it = r["pendencias"]["itens"][0]
        self.assertEqual((it["acao_id"], it["prazo"], len(it["tipo"])), (None, None, oco.TEXTO_MAX))
        self.assertEqual(r["pendencias"]["total_aberto"], 1)
        self.assertEqual((r["ultimos_resultados"][0]["rotina"], r["ultimos_resultados"][0]["criado_em"]), (None, None))

    def test_lacuna_quando_ha_mais_pendencias_que_mostradas(self):
        r, _, _ = self.rodar(_ctx(*POPS))
        self.assertTrue(any("3 abertas, mostradas 2" in l for l in r["lacunas"]))

    def test_pop_sem_instrucao_vira_lacuna(self):
        r, _, _ = self.rodar(_ctx(*POPS))
        self.assertTrue(any("1 sem instrução" in l for l in r["lacunas"]))
        self.assertNotIn("p3", str(r["regras_por_gatilho"]))

    def test_fonte_que_falha_vira_lacuna_e_nao_derruba_as_outras(self):
        a = mock.patch("atencao.coletar_fila_atencao", side_effect=RuntimeError("x"))
        b = mock.patch("agent_runs.listar_recentes", return_value=RUNS)
        with a, b:
            r = oco.obter(_ctx(*POPS), {})
        self.assertEqual(r["fontes"]["pendencias"], "falhou (RuntimeError)")
        self.assertIsNone(r["pendencias"]["total_aberto"])
        self.assertEqual(r["pendencias"]["itens"], [])
        self.assertEqual(r["fontes"]["ultimos_resultados"], "ok")
        self.assertEqual(len(r["regras_sempre_ativas"]), 1)
        self.assertTrue(any(l.startswith("pendencias: leitura falhou") for l in r["lacunas"]))

    def test_falha_de_pops_deixa_regras_vazias_com_lacuna(self):
        ctx = SimpleNamespace(db=SimpleNamespace(collection=mock.Mock(side_effect=OSError("down"))))
        r, _, _ = self.rodar(ctx)
        self.assertEqual(r["fontes"]["regras"], "falhou (OSError)")
        self.assertEqual((r["regras_sempre_ativas"], r["regras_por_gatilho"]), ([], []))
        self.assertTrue(any(l.startswith("regras: leitura falhou") for l in r["lacunas"]))

    def test_limite_e_normalizado(self):
        for bruto, esperado in [(None, 10), (0, 10), (True, 10), ("abc", 10), (-5, 1), (999, 20), (7, 7), ("3", 3)]:
            _, fila, runs = self.rodar(_ctx(), {"limite_contexto": bruto})
            self.assertEqual(fila.call_args.kwargs["limite"], esperado, bruto)
            self.assertEqual(runs.call_args.kwargs["limite"], esperado, bruto)

    def test_args_nao_dict(self):
        r, _, _ = self.rodar(_ctx(), None)
        self.assertEqual(r["fontes"]["regras"], "ok")

    def test_so_leitura_fila_de_atencao_filtra_abertos(self):
        _, fila, _ = self.rodar(_ctx())
        self.assertEqual(fila.call_args.kwargs["estado"], "aberto")

    def test_registrada_como_handler_e_fora_da_voz(self):
        from tools import registry
        self.assertIn("obter_contexto_operacional", hermes_tools._HANDLERS)
        self.assertIn("obter_contexto_operacional", registry._VOICE_EXCLUDED)


if __name__ == "__main__":
    unittest.main()
