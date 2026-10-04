"""PR 5 do plano "confirmação verificada": as demais rotinas e as escritas
em ações passam a deixar registro em agent_runs.

- `agent_runs.instrumentada`: cada execução de rotina agendada vira registro
  (run_id por dia), com erro quando a rotina estoura; sem banco, a rotina roda.
- as 12 rotinas agendadas restantes estão decoradas;
- escrita conferida em ação (web, Telegram, MCP) vira registro `escritas_<canal>`
  ligado ao resultado pelo run_id;
- o briefing mostra essas edições numa linha por canal;
- a instrução do MCP pede ao Claude que registre as próprias tarefas longas.
"""

import datetime
import pathlib
import sys
import types
import unittest
from unittest import mock

import agent_runs
import trava_confirmacao as tc
import visao_atividade as va
from verificacao import ResultadoOperacao

RAIZ = pathlib.Path(__file__).parent

ROTINAS = [
    ("daily_reset_job.py", "daily_wip_reset_and_degradation"),
    ("monthly_recurring_actions.py", "gerar_acoes_recorrentes_mensais"),
    ("morning_summary.py", "gerar_resumo_matinal"),
    ("revisao_semanal.py", "revisar_semana_propor_reagendamento"),
    ("health_calendar_sync.py", "sincronizar_eventos_saude_agenda"),
    ("investimentos_sync.py", "sincronizar_investimentos_pos_decisao"),
    ("health_weekly_summary.py", "verificar_reavaliacoes_saude"),
    ("health_weekly_summary.py", "gerar_resumo_semanal_saude"),
    ("health_weekly_report.py", "gerar_relatorio_semanal_saude"),
    ("retro_agente.py", "retro_semanal_agente"),
    ("personal_diary.py", "gerar_diario_pessoal"),
    ("personal_diary.py", "consolidar_personalidade"),
]


class TestDecoradorInstrumentada(unittest.TestCase):
    def _rodar(self, fn, db="db"):
        falso_main = types.SimpleNamespace(get_db=lambda: db)
        with mock.patch.dict(sys.modules, {"main": falso_main}), \
                mock.patch.object(agent_runs, "registrar", return_value={"status": "ok"}) as registrar:
            try:
                return fn(None), registrar
            except Exception as exc:  # noqa: BLE001
                return exc, registrar

    def test_sucesso_registra_com_run_id_do_dia_e_devolve_o_resultado(self):
        @agent_runs.instrumentada("rotina_x")
        def rotina(event):
            return 42

        valor, registrar = self._rodar(rotina)
        self.assertEqual(valor, 42)
        kw = registrar.call_args.kwargs
        self.assertEqual((kw["rotina"], kw["status"], kw["origem"]), ("rotina_x", "sucesso", "agendada"))
        self.assertRegex(kw["run_id"], r"^rotina_x:\d{4}-\d{2}-\d{2}$")
        self.assertEqual(registrar.call_args.args, ("db",))

    def test_erro_registra_e_continua_propagando(self):
        @agent_runs.instrumentada("rotina_x")
        def rotina(event):
            raise RuntimeError("BigQuery fora")

        exc, registrar = self._rodar(rotina)
        self.assertIsInstance(exc, RuntimeError)
        kw = registrar.call_args.kwargs
        self.assertEqual(kw["status"], "erro")
        self.assertIn("BigQuery fora", kw["erro"])

    def test_sem_banco_a_rotina_roda_igual(self):
        @agent_runs.instrumentada("rotina_x")
        def rotina(event):
            return "rodou"

        def quebra():
            raise RuntimeError("sem credencial")

        falso_main = types.SimpleNamespace(get_db=quebra)
        with mock.patch.dict(sys.modules, {"main": falso_main}), \
                mock.patch.object(agent_runs, "registrar") as registrar:
            self.assertEqual(rotina(None), "rodou")
        registrar.assert_not_called()

    def test_preserva_nome_para_o_deploy_achar_a_funcao(self):
        @agent_runs.instrumentada("rotina_x")
        def minha_rotina(event):
            return None

        self.assertEqual(minha_rotina.__name__, "minha_rotina")


class TestRotinasDecoradas(unittest.TestCase):
    def test_as_doze_rotinas_estao_instrumentadas(self):
        for arquivo, fn in ROTINAS:
            with self.subTest(fn=fn):
                fonte = (RAIZ / arquivo).read_text(encoding="utf-8").replace("\r\n", "\n")
                self.assertIn(f'@instrumentada("{fn}")\ndef {fn}(', fonte)
                self.assertIn("from agent_runs import instrumentada", fonte)

    def test_briefing_e_custos_nao_sao_registrados_em_dobro(self):
        """Os dois já registram por dentro (PR 4), com o envio confirmado."""
        for arquivo in ("daily_morning_briefing.py", "cost_report.py"):
            with self.subTest(arquivo=arquivo):
                self.assertNotIn("@instrumentada(", (RAIZ / arquivo).read_text(encoding="utf-8"))


class TestRegistrarEscrita(unittest.TestCase):
    def _res(self, estado="verificado", alvo="tarefas/t1", motivo=None):
        return ResultadoOperacao(estado, "editar_plano_acao", alvo, motivo=motivo)

    def test_escrita_verificada_em_acao_vira_registro_e_liga_o_run_id(self):
        res = self._res()
        with mock.patch.object(agent_runs, "registrar", return_value={"status": "ok"}) as registrar:
            tc.registrar_escrita("db", "mcp", res)
        kw = registrar.call_args.kwargs
        self.assertEqual((kw["rotina"], kw["origem"], kw["estado_verificado"]), ("escritas_mcp", "mcp", "verificado"))
        self.assertEqual(kw["acoes_afetadas"], ["t1"])
        self.assertEqual(res.run_id, kw["run_id"])

    def test_falha_vira_erro_com_o_motivo(self):
        res = self._res("falhou", motivo="a etapa não aparece")
        with mock.patch.object(agent_runs, "registrar", return_value={"status": "ok"}) as registrar:
            tc.registrar_escrita("db", "telegram", res)
        kw = registrar.call_args.kwargs
        self.assertEqual((kw["status"], kw["erro"], kw["origem"]), ("erro", "a etapa não aparece", "telegram"))

    def test_pendente_ou_fora_de_acoes_nao_registra(self):
        for res in (ResultadoOperacao("pendente", "x", "proposta"), self._res(alvo="knowledge_nodes/m1")):
            with self.subTest(alvo=res.alvo), mock.patch.object(agent_runs, "registrar") as registrar:
                tc.registrar_escrita("db", "web", res)
            registrar.assert_not_called()

    def test_registro_recusado_ou_quebrado_nao_atrapalha(self):
        for efeito in ({"return_value": {"erro": "resumo é obrigatório."}}, {"side_effect": RuntimeError("fora")}):
            res = self._res()
            with self.subTest(efeito=list(efeito)), mock.patch.object(agent_runs, "registrar", **efeito):
                tc.registrar_escrita("db", "mcp", res)
            self.assertIsNone(res.run_id)

    def test_verificar_ferramenta_com_canal_registra_e_anota_o_run_id(self):
        resultado = '{"status": "ok", "task_id": "t1", "titulo": "T"}'
        from test_registrar_saude import _Db

        db = _Db()
        db.collection("tarefas").dados["t1"] = {"acompanhamento": [{"nota": "ok"}]}
        with mock.patch.object(agent_runs, "registrar", return_value={"status": "ok"}):
            res = tc.verificar_ferramenta(db, "registrar_no_diario", {"nota": "ok"}, resultado, canal="mcp")
        self.assertTrue(res.run_id.startswith("escrita_mcp_"))
        self.assertIn('"run_id": "escrita_mcp_', tc.anotar_resultado(resultado, res))

    def test_sem_canal_nao_registra(self):
        from test_registrar_saude import _Db

        db = _Db()
        db.collection("tarefas").dados["t1"] = {"acompanhamento": [{"nota": "ok"}]}
        with mock.patch.object(agent_runs, "registrar") as registrar:
            tc.verificar_ferramenta(db, "registrar_no_diario", {"nota": "ok"},
                                    '{"status": "ok", "task_id": "t1"}')
        registrar.assert_not_called()

    def test_os_tres_lacos_passam_o_canal(self):
        def fonte(arquivo):
            return (RAIZ / arquivo).read_text(encoding="utf-8")

        self.assertIn('verificacao = verificar_ferramenta(db, fc.name, kwargs, result_text, canal="telegram")',
                      fonte("telegram_utils.py"))
        self.assertIn('canal="telegram" if str(session_id or "").startswith("telegram_") else "web")', fonte("main.py"))
        self.assertIn('verificar_ferramenta(ctx.db, nome, args, resultado, canal="mcp")', fonte("trava_confirmacao.py"))


class TestBriefingMostraAsEdicoes(unittest.TestCase):
    def test_edicoes_viram_uma_linha_por_canal(self):
        runs = [
            {"rotina": "escritas_mcp", "resumo": "x", "status": "sucesso", "acoes_afetadas": ["a1"]},
            {"rotina": "escritas_mcp", "resumo": "x", "status": "sucesso", "acoes_afetadas": ["a2"]},
            {"rotina": "escritas_mcp", "resumo": "x", "status": "sucesso", "acoes_afetadas": ["a2"]},
            {"rotina": "escritas_telegram", "resumo": "x", "status": "sucesso", "acoes_afetadas": ["a3"]},
        ]
        texto = va.montar_secao(runs, [])
        self.assertIn("Ações editadas pelo Claude (MCP): 3 edições em 2 ações", texto)
        self.assertIn("Ações editadas pelo Telegram: 1 edição", texto)


class TestInstrucaoDoMcp(unittest.TestCase):
    def test_pede_registro_das_tarefas_longas(self):
        import mcp_server

        texto = mcp_server._INSTRUCTIONS
        for termo in ("registrar_execucao_agente", "UMA linha", "run_id", "aguarda_usuario", "reversivel",
                      "briefing das 05:00"):
            self.assertIn(termo, texto, termo)


if __name__ == "__main__":
    unittest.main()
