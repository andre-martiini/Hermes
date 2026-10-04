"""Visão de atividade (PR 4 do plano "confirmação verificada").

- seção do briefing: Falhas primeiro, O que o Gaspar fez, O que espera você,
  O que pode ser desfeito; cabe em 4096 caracteres; dados escapados;
- fila de WhatsApp -> agent_runs: um registro por mensagem, reversível só
  enquanto não saiu, sem destinatário nem texto;
- briefing e relatório de custos registram a própria execução e se o Telegram
  confirmou o envio; a falha da seção não impede o briefing.
"""

import datetime
import sys
import types
import unittest
import zoneinfo
from unittest import mock

import agent_runs
import cost_report
import daily_morning_briefing
import visao_atividade as va

SP = zoneinfo.ZoneInfo("America/Sao_Paulo")


def _run(rotina, resumo, **extra):
    return {"id": extra.pop("id", rotina), "rotina": rotina, "resumo": resumo, "status": extra.pop("status", "sucesso"),
            "contadores": extra.pop("contadores", {}), "erro": extra.pop("erro", None), **extra}


class TestJanela(unittest.TestCase):
    def test_comeca_as_19h_do_dia_anterior(self):
        agora = datetime.datetime(2026, 10, 2, 5, 0, tzinfo=SP)
        self.assertEqual(va.inicio_janela(agora), datetime.datetime(2026, 10, 1, 19, 0, tzinfo=SP))


class TestMontarSecao(unittest.TestCase):
    def test_blocos_na_ordem_com_falhas_primeiro(self):
        runs = [
            _run("relatorio_diario_custos", "Relatório de custos de 2026-10-01 enviado"),
            _run("fila_whatsapp", "x", contadores={"enviado": 1}),
            _run("fila_whatsapp", "x", contadores={"enviado": 1}),
            _run("fila_whatsapp", "x", contadores={"cancelado": 1}),
            _run("varredura", "falhou", status="erro", erro="BigQuery fora"),
            _run("fila_whatsapp", "WhatsApp na fila de envio (outbox o9)", contadores={"na_fila": 1},
                 reversivel=True, como_desfazer="cancelar_envio_whatsapp(job_id=o9)"),
            _run("pgd", "22 registros", aguarda_usuario=True, motivo_espera="aprovar o dia 28/09"),
        ]
        atencao = [{"titulo": "Responder a Gabriela", "sugestao": "explicar o item 4"}]
        texto = va.montar_secao(runs, atencao)
        ordem = [texto.index(t) for t in ("Falhas", "O que o Gaspar fez", "O que espera você",
                                         "O que pode ser desfeito")]
        self.assertEqual(ordem, sorted(ordem))
        self.assertIn("varredura: BigQuery fora", texto)
        self.assertIn("WhatsApp: 2 enviados, 1 na fila, 1 cancelado", texto)
        self.assertIn("Relatório de custos de 2026-10-01 enviado", texto)
        self.assertIn("aprovar o dia 28/09", texto)
        self.assertIn("Responder a Gabriela — explicar o item 4", texto)
        self.assertIn("WhatsApp na fila de envio (outbox o9) — cancelar_envio_whatsapp(job_id=o9)", texto)

    def test_estado_falhou_tambem_e_falha(self):
        texto = va.montar_secao([_run("x", "não confirmado", estado_verificado="falhou")], [])
        self.assertIn("Falhas", texto)
        self.assertNotIn("O que o Gaspar fez", texto)

    def test_sem_nada(self):
        self.assertIn("Nada registrado desde as 19h de ontem", va.montar_secao([], []))

    def test_o_proprio_briefing_nao_aparece(self):
        self.assertNotIn("Briefing enviado", va.montar_secao([_run("briefing_matinal_acoes", "Briefing enviado")], []))

    def test_texto_vindo_dos_registros_e_escapado(self):
        texto = va.montar_secao([_run("x", "<script>alert(1)</script> & cia")], [])
        self.assertIn("&lt;script&gt;", texto)
        self.assertNotIn("<script>", texto)

    def test_rotina_repetida_vira_uma_linha(self):
        texto = va.montar_secao([_run("varredura", "3 itens", id="a"), _run("varredura", "2 itens", id="b")], [])
        self.assertIn("varredura: 2 execuções — a última: 3 itens", texto)

    def test_cabe_no_limite_e_avisa_o_que_ficou_de_fora(self):
        runs = [_run(f"r{i}", "x" * 150, id=f"r{i}", aguarda_usuario=True, motivo_espera="y" * 150,
                     reversivel=True, como_desfazer="z" * 100) for i in range(60)]
        for limite in (4096, 1500, 300):
            with self.subTest(limite=limite):
                texto = va.montar_secao(runs, [], limite)
                self.assertLessEqual(len(texto), limite)
        self.assertIn("+55 itens", va.montar_secao(runs, [], 4096))


class TestSecaoAtividade(unittest.TestCase):
    def test_le_a_janela_completa_e_a_fila_aberta(self):
        agora = datetime.datetime(2026, 10, 2, 5, 0, tzinfo=SP)
        with mock.patch.object(agent_runs, "listar_recentes", return_value={"total": 0, "runs": []}) as listar, \
                mock.patch("atencao.coletar_fila_atencao", return_value={"total": 0, "itens": []}) as fila:
            va.secao_atividade("db", agora)
        kw = listar.call_args.kwargs
        self.assertEqual(kw["desde"], va.inicio_janela(agora))
        self.assertTrue(kw["completo"])
        self.assertEqual(fila.call_args.kwargs["estado"], "aberto")

    def test_fila_de_atencao_fora_nao_derruba_a_secao(self):
        with mock.patch.object(agent_runs, "listar_recentes", return_value={"total": 0, "runs": [_run("x", "ok")]}), \
                mock.patch("atencao.coletar_fila_atencao", side_effect=RuntimeError("fora")):
            self.assertIn("ok", va.secao_atividade("db", datetime.datetime.now(SP)))


class TestRegistroOutbox(unittest.TestCase):
    PESSOAL = {"to_number": "5527999990000", "content": "Oi Gabriela, segue o item 4", "destino_pedido": "Gabriela"}

    def test_aguardando_aprovacao_espera_o_usuario_e_pode_ser_descartado(self):
        args = va.registro_outbox("o1", {"status": "aguardando_aprovacao", "acao_id": "a1", **self.PESSOAL})
        self.assertEqual(args["run_id"], "whatsapp_outbox:o1")
        self.assertTrue(args["aguarda_usuario"])
        self.assertIn("descartar_rascunho_whatsapp(outbox_id=o1)", args["como_desfazer"])
        self.assertEqual(args["acoes_afetadas"], ["a1"])
        self.assertEqual(args["estado_verificado"], "pendente")

    def test_pendente_pode_ser_cancelado_e_enviado_nao(self):
        self.assertIn("cancelar_envio_whatsapp", va.registro_outbox("o1", {"status": "pending"})["como_desfazer"])
        enviado = va.registro_outbox("o1", {"status": "sent"})
        self.assertNotIn("reversivel", enviado)
        self.assertEqual(enviado["estado_verificado"], "verificado")
        self.assertEqual(enviado["contadores"], {"enviado": 1})

    def test_falha_vira_erro(self):
        args = va.registro_outbox("o1", {"status": "failed", "error_message": "worker offline"})
        self.assertEqual((args["status"], args["estado_verificado"], args["erro"]), ("erro", "falhou", "worker offline"))

    def test_estado_transitorio_nao_registra(self):
        self.assertIsNone(va.registro_outbox("o1", {"status": "sending"}))

    def test_nao_leva_destinatario_nem_texto(self):
        for status in ("aguardando_aprovacao", "pending", "sent", "failed", "canceled"):
            with self.subTest(status=status):
                args = va.registro_outbox("o1", {"status": status, **self.PESSOAL})
                registro = agent_runs.montar_registro(**{k: v for k, v in args.items() if k != "run_id"})
                texto = repr(registro)
                for valor in self.PESSOAL.values():
                    self.assertNotIn(valor, texto)

    def test_registro_e_aceito_pelo_agent_runs(self):
        for status in ("aguardando_aprovacao", "aguardando_janela", "pending", "notified", "sent", "failed",
                       "canceled", "descartado", "expirado"):
            with self.subTest(status=status):
                args = va.registro_outbox("o1", {"status": status})
                registro = agent_runs.montar_registro(**{k: v for k, v in args.items() if k != "run_id"})
                self.assertIn("rotina", registro, registro)


class TestGatilhoOutbox(unittest.TestCase):
    def _evento(self, antes, depois):
        def snap(dados):
            if dados is None:
                return None
            return types.SimpleNamespace(exists=True, to_dict=lambda: dict(dados))

        return types.SimpleNamespace(data=types.SimpleNamespace(before=snap(antes), after=snap(depois)),
                                     params={"outbox_id": "o1"})

    def _chamar(self, antes, depois):
        fn = getattr(va.on_whatsapp_outbox_escrito, "__wrapped__", va.on_whatsapp_outbox_escrito)
        with mock.patch.dict(sys.modules, {"main": types.SimpleNamespace(get_db=lambda: "db")}), \
                mock.patch.object(agent_runs, "registrar") as registrar:
            fn(self._evento(antes, depois))
        return registrar

    def test_mudanca_de_status_registra(self):
        registrar = self._chamar({"status": "pending"}, {"status": "sent"})
        self.assertEqual(registrar.call_args.args, ("db",))
        self.assertEqual(registrar.call_args.kwargs["run_id"], "whatsapp_outbox:o1")

    def test_criacao_registra(self):
        self.assertTrue(self._chamar(None, {"status": "aguardando_aprovacao"}).called)

    def test_sem_mudanca_de_status_nao_registra(self):
        self.assertFalse(self._chamar({"status": "pending", "attempts": 1}, {"status": "pending", "attempts": 2}).called)

    def test_exclusao_nao_registra(self):
        self.assertFalse(self._chamar({"status": "pending"}, None).called)


def _falso_main(db, enviar):
    return types.SimpleNamespace(
        get_db=lambda: db, get_calendar_service=lambda: None, get_target_calendar_id=lambda _db: "cal",
        _resolve_default_telegram_chat_id=lambda _db: "123", _get_telegram_token=lambda _db: "token",
        _send_telegram_message=enviar)


class _DbTarefas:
    def collection(self, nome):
        return self

    def where(self, *a, **k):
        return self

    def get(self):
        return []


class TestBriefingRegistraAExecucao(unittest.TestCase):
    def _rodar(self, enviar, secao=None, secao_erro=None):
        modulos = {
            "main": _falso_main(_DbTarefas(), enviar),
            "hermes_calendar_tools": types.SimpleNamespace(consultar_eventos=lambda *a, **k: []),
            "investimentos_sync": types.SimpleNamespace(sincronizar_decisao_investimentos=lambda _db: None),
        }
        secao_mock = mock.Mock(return_value=secao or "🤖 <b>O que o Gaspar fez</b>\n• teste",
                               side_effect=secao_erro)
        with mock.patch.dict(sys.modules, modulos), mock.patch.object(va, "secao_atividade", secao_mock), \
                mock.patch.object(agent_runs, "registrar") as registrar:
            fn = getattr(daily_morning_briefing.briefing_matinal_acoes, "__wrapped__",
                         daily_morning_briefing.briefing_matinal_acoes)
            fn(None)
        self.secao_mock = secao_mock
        return registrar.call_args.kwargs

    def test_limite_dado_a_secao_deixa_espaco_para_o_resto_da_mensagem(self):
        enviar = mock.Mock(return_value=1)
        self._rodar(enviar, secao="S")
        resto = len(enviar.call_args.args[2]) - len("S")
        self.assertLessEqual(self.secao_mock.call_args.kwargs["limite"] + resto, 4096)

    def test_envio_confirmado(self):
        enviar = mock.Mock(return_value=987)
        reg = self._rodar(enviar)
        self.assertIn("O que o Gaspar fez", enviar.call_args.args[2])
        self.assertEqual((reg["status"], reg["estado_verificado"]), ("sucesso", "verificado"))
        self.assertEqual(reg["contadores"]["enviado"], 1)
        self.assertTrue(reg["run_id"].startswith("briefing_matinal_acoes:"))

    def test_envio_nao_confirmado_vira_erro(self):
        reg = self._rodar(mock.Mock(return_value=None))
        self.assertEqual((reg["status"], reg["estado_verificado"]), ("erro", "falhou"))
        self.assertIn("não confirmou", reg["erro"])

    def test_secao_quebrada_nao_impede_o_briefing(self):
        enviar = mock.Mock(return_value=1)
        reg = self._rodar(enviar, secao_erro=RuntimeError("agent_runs fora"))
        self.assertIn("Bom dia", enviar.call_args.args[2])
        self.assertEqual(reg["status"], "parcial")
        self.assertIn("seção de atividade indisponível", reg["erro"])

    def test_mensagem_cabe_no_telegram_com_secao_real(self):
        enviar = mock.Mock(return_value=1)
        runs = [_run(f"r{i}", "x" * 300, id=f"r{i}") for i in range(50)]
        modulos = {
            "main": _falso_main(_DbTarefas(), enviar),
            "hermes_calendar_tools": types.SimpleNamespace(consultar_eventos=lambda *a, **k: []),
            "investimentos_sync": types.SimpleNamespace(sincronizar_decisao_investimentos=lambda _db: None),
        }
        with mock.patch.dict(sys.modules, modulos), \
                mock.patch.object(agent_runs, "listar_recentes", return_value={"total": 50, "runs": runs}), \
                mock.patch("atencao.coletar_fila_atencao", return_value={"itens": []}), \
                mock.patch.object(agent_runs, "registrar"):
            fn = getattr(daily_morning_briefing.briefing_matinal_acoes, "__wrapped__",
                         daily_morning_briefing.briefing_matinal_acoes)
            fn(None)
        self.assertLessEqual(len(enviar.call_args.args[2]), 4096)


class TestRelatorioDeCustosRegistraAExecucao(unittest.TestCase):
    def _rodar(self, enviar_resultado=55, montar_erro=None):
        import telegram_utils

        falso_main = types.SimpleNamespace(get_db=lambda: "db", _resolve_default_telegram_chat_id=lambda _db: "123")
        textos = {"dia": "2026-10-01", "resumo": "r", "detalhe": "d"}
        with mock.patch.dict(sys.modules, {"main": falso_main}), \
                mock.patch.object(cost_report, "gerar_relatorios_custos", return_value=textos,
                                  side_effect=montar_erro), \
                mock.patch.object(cost_report, "salvar_relatorio"), \
                mock.patch.object(telegram_utils, "_get_telegram_token", return_value="t"), \
                mock.patch.object(telegram_utils, "_send_telegram_message_with_keyboard",
                                  return_value=enviar_resultado), \
                mock.patch.object(agent_runs, "registrar") as registrar:
            fn = getattr(cost_report.relatorio_diario_custos, "__wrapped__", cost_report.relatorio_diario_custos)
            fn(None)
        return registrar.call_args.kwargs

    def test_enviado(self):
        reg = self._rodar()
        self.assertEqual((reg["status"], reg["estado_verificado"]), ("sucesso", "verificado"))
        self.assertEqual(reg["resumo"], "Relatório de custos de 2026-10-01 enviado")

    def test_nao_confirmado(self):
        self.assertEqual(self._rodar(enviar_resultado=None)["status"], "erro")

    def test_falha_ao_montar(self):
        reg = self._rodar(montar_erro=RuntimeError("BigQuery fora"))
        self.assertEqual(reg["status"], "erro")
        self.assertIn("BigQuery fora", reg["erro"])


if __name__ == "__main__":
    unittest.main()


class TestAjustesDaPrevia(unittest.TestCase):
    """Prévia de 04/10 com dados reais: o "+N" contava só os 10 itens lidos da fila
    (havia 25 abertos) e os títulos da fila de atenção passavam de 200 caracteres."""

    def test_mais_n_conta_os_itens_que_nem_foram_lidos(self):
        atencao = [{"titulo": f"Item {i}"} for i in range(10)]
        texto = va.montar_secao([], atencao, atencao_total=25)
        self.assertIn("+20 itens", texto)

    def test_sem_total_conta_so_a_lista(self):
        texto = va.montar_secao([], [{"titulo": f"Item {i}"} for i in range(7)])
        self.assertIn("+2 itens", texto)

    def test_linha_longa_e_cortada_sem_partir_entidade(self):
        titulo = "Audio de Gabriela na conversa vinculada a 'Ciclo Sispnaes' " + "x" * 300
        linha = va._e(titulo)
        self.assertTrue(linha.endswith("…"))
        self.assertLessEqual(len(linha.replace("&#x27;", "'")), va.LINHA_MAX)
        self.assertNotRegex(linha, r"&[#a-z0-9]*…$")

    def test_secao_le_o_total_da_fila(self):
        fila = {"itens": [{"titulo": f"Item {i}"} for i in range(10)], "total": 25}
        with mock.patch.object(agent_runs, "listar_recentes", return_value={"total": 0, "runs": []}), \
                mock.patch("atencao.coletar_fila_atencao", return_value=fila):
            self.assertIn("+20 itens", va.secao_atividade("db", datetime.datetime.now(SP)))
