"""Hermes Vídeo Fase 4 — renderizar, refazer cena e cancelar; piso de confirmação; uso no relatório."""
import json
import unittest
from datetime import date, datetime, timezone
from unittest import mock

from video import comandos, midia, previa, renderizacao, uso
from video import projeto as vp
from video.veo_provider import FakeVeoProvider
from video_fakes import FakeDb

from test_video_previa import roteiro
from test_video_renderizacao import mp4_de

AGORA = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.srv = midia.ServicosFalsos()
        self.pid = vp.criar_projeto(self.db, "uid", roteiro(acao_id="acao-1"))["projeto_id"]
        assert previa.gerar_previa(self.db, self.pid, "uid", self.srv)["status"] == "ok"
        self.disparos = []

    def disparar(self, pid):
        self.disparos.append(pid)
        return f"operations/exec-{len(self.disparos)}"

    def doc(self, sub=""):
        return self.db.docs[f"video_projetos/{self.pid}{sub}"]

    def worker(self, execucao="exec-w"):
        self.veo = getattr(self, "veo", None) or FakeVeoProvider(gerar_mp4=mp4_de)
        return renderizacao.renderizar(self.db, self.pid, execucao, veo=self.veo, servicos=self.srv,
                                       avisos=renderizacao.Avisos(falso=True), dormir=lambda s: None)


class TestRenderizar(Base):
    def test_previa_da_confirmacao_mostra_custo_e_nao_gasta(self):
        p = comandos.avaliar_renderizacao(self.db, "uid", self.pid, agora=AGORA)
        self.assertEqual(p["status"], "confirmation_required")
        self.assertEqual(p["segundos_video"], 14)
        self.assertAlmostEqual(p["custo_clipes_a_gerar_usd"], 0.7)
        self.assertGreater(p["custo_maximo_desta_renderizacao_usd"], 0.7)
        self.assertEqual(p["teto_mensal_usd"], 30.0)
        self.assertEqual(self.doc()["status"], vp.AGUARDANDO_STORYBOARD)
        self.assertEqual(self.disparos, [])

    def test_sim_leva_a_renderizando_e_dispara_o_worker(self):
        r = comandos.renderizar(self.db, "uid", self.pid, self.disparar, agora=AGORA)
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(self.doc()["status"], vp.RENDERIZANDO)
        self.assertEqual(self.disparos, [self.pid])
        self.assertEqual(self.doc()["worker_disparo"], "operations/exec-1")

    def test_repetir_enquanto_renderiza_e_recusado_sem_disparar_de_novo(self):
        comandos.renderizar(self.db, "uid", self.pid, self.disparar, agora=AGORA)
        r = comandos.renderizar(self.db, "uid", self.pid, self.disparar, agora=AGORA)
        self.assertEqual(r["status"], "recusado")
        self.assertEqual(len(self.disparos), 1)

    def test_worker_que_nao_dispara_devolve_o_projeto_a_erro(self):
        def falha(pid):
            raise RuntimeError("job não existe")

        r = comandos.renderizar(self.db, "uid", self.pid, falha, agora=AGORA)
        self.assertEqual(r["status"], "erro")
        self.assertEqual(self.doc()["status"], vp.ERRO)
        # Depois do deploy, o mesmo comando retoma a partir do erro.
        self.assertEqual(comandos.renderizar(self.db, "uid", self.pid, self.disparar, agora=AGORA)["status"], "ok")

    def test_teto_mensal(self):
        ref, dia = uso.ref_dia(self.db, AGORA)
        self.db.docs[f"system_usage/video/daily/{dia}"]["estimated_usd"] = 29.9  # a prévia já gravou o dia
        with self.assertRaises(comandos.Recusado) as ctx:
            comandos.avaliar_renderizacao(self.db, "uid", self.pid, agora=AGORA)
        self.assertIn("Teto mensal", str(ctx.exception))

    def test_gasto_do_mes_soma_so_o_mes_corrente(self):
        base = "system_usage/video/daily/"
        self.db.docs = {k: v for k, v in self.db.docs.items() if not k.startswith(base)}
        self.db.docs[base + "2026-09-01"] = {"estimated_usd": 2.5}
        self.db.docs[base + "2026-09-26"] = {"estimated_usd": 1.0}
        self.db.docs[base + "2026-08-31"] = {"estimated_usd": 50}
        self.assertEqual(comandos.gasto_do_mes(self.db, AGORA), 3.5)

    def test_previa_incompleta_ou_estado_errado_recusa(self):
        self.db.docs[f"video_projetos/{self.pid}/keyframes/K02"]["pendente"] = True
        with self.assertRaises(comandos.Recusado):
            comandos.avaliar_renderizacao(self.db, "uid", self.pid, agora=AGORA)
        with self.assertRaises(comandos.Recusado):
            comandos.avaliar_renderizacao(self.db, "outro", self.pid, agora=AGORA)

    def test_orcamento_que_nao_cobre_os_clipes_recusa(self):
        self.doc()["orcamento_usd"] = self.doc()["custo_real_usd"] + 0.3  # clipes custam 0,70
        with self.assertRaises(comandos.Recusado) as ctx:
            comandos.avaliar_renderizacao(self.db, "uid", self.pid, agora=AGORA)
        self.assertIn("pararia no meio", str(ctx.exception))


class TestRefazerCena(Base):
    def setUp(self):
        super().setUp()
        comandos.renderizar(self.db, "uid", self.pid, self.disparar, agora=AGORA)
        assert self.worker()["status"] == "ok"
        self.enviados = len(self.veo.pedidos)

    def test_refaz_so_a_cena_pedida_com_a_instrucao(self):
        p = comandos.avaliar_refacao(self.db, "uid", self.pid, 2, instrucao="câmera mais aberta", agora=AGORA)
        self.assertEqual(p["cenas_refeitas"], [2])
        self.assertAlmostEqual(p["custo_usd"], 0.3)
        self.assertIn("salto pequeno", p["aviso"])
        r = comandos.refazer_cena(self.db, "uid", self.pid, 2, self.disparar, instrucao="câmera mais aberta",
                                  agora=AGORA)
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(self.doc()["status"], vp.RENDERIZANDO)
        self.assertIsNone(self.doc()["video_drive_id"])
        self.assertTrue(self.doc()["video_link_anterior"])
        self.assertEqual(self.worker("exec-2")["status"], "ok")
        self.assertEqual(len(self.veo.pedidos) - self.enviados, 1)  # só a cena 2
        self.assertIn("Ajuste pedido: câmera mais aberta", self.veo.pedidos[-1].prompt)
        self.assertEqual(self.srv.publicados.count("RSC.mp4"), 2)

    def test_refazer_seguintes_refaz_da_cena_ate_o_fim(self):
        r = comandos.refazer_cena(self.db, "uid", self.pid, 2, self.disparar, refazer_seguintes=True, agora=AGORA)
        self.assertEqual(r["status"], "ok", r)
        self.worker("exec-2")
        self.assertEqual(len(self.veo.pedidos) - self.enviados, 2)  # cenas 2 e 3

    def test_so_com_video_concluido_e_cena_existente(self):
        with self.assertRaises(comandos.Recusado):
            comandos.avaliar_refacao(self.db, "uid", self.pid, 9, agora=AGORA)
        comandos.refazer_cena(self.db, "uid", self.pid, 1, self.disparar, agora=AGORA)
        r = comandos.refazer_cena(self.db, "uid", self.pid, 1, self.disparar, agora=AGORA)  # ainda renderizando
        self.assertEqual(r["status"], "recusado")
        self.assertEqual(self.doc("/cenas/01")["refacao"], 1)

    def test_orcamento_do_projeto_limita_refacoes(self):
        self.doc()["orcamento_usd"] = self.doc()["custo_real_usd"] + 0.1
        with self.assertRaises(comandos.Recusado) as ctx:
            comandos.avaliar_refacao(self.db, "uid", self.pid, 2, agora=AGORA)
        self.assertIn("Orçamento do projeto", str(ctx.exception))


class TestCancelar(Base):
    def test_cancelar_e_idempotente(self):
        r = comandos.cancelar(self.db, "uid", self.pid, motivo="desisti")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(self.doc()["cancelado_motivo"], "desisti")
        self.assertIn("Já estava", comandos.cancelar(self.db, "uid", self.pid)["mensagem"])

    def test_cancelar_renderizando_avisa_que_para_antes_do_proximo_clipe(self):
        comandos.renderizar(self.db, "uid", self.pid, self.disparar, agora=AGORA)
        self.assertIn("antes do próximo clipe", comandos.cancelar(self.db, "uid", self.pid)["mensagem"])
        self.assertEqual(self.worker()["status"], "recusado")

    def test_projeto_de_outro_usuario(self):
        self.assertEqual(comandos.cancelar(self.db, "outro", self.pid)["status"], "nao_encontrado")


class TestUsoNoRelatorio(Base):
    def test_previa_e_render_registram_o_uso_do_dia(self):
        comandos.renderizar(self.db, "uid", self.pid, self.disparar, agora=AGORA)
        self.worker()
        dias = [v for k, v in self.db.docs.items() if k.startswith("system_usage/video/daily/")]
        self.assertEqual(len(dias), 1)
        d = dias[0]
        self.assertAlmostEqual(d["estimated_usd"], 0.18 + 0.7)
        self.assertEqual(d["itens"], {"narracao": 2, "quadro": 4, "clipe": 3})
        self.assertEqual(d["calls"], 9)

    def test_linha_video_no_relatorio(self):
        import cost_report

        linhas = cost_report.format_ai_block(None, None, 5.0, date(2026, 9, 26),
                                             video={"estimated_usd": 0.88, "itens": {"clipe": 3, "quadro": 4}})
        self.assertIn("  • Vídeo: US$ 0.88 (~R$ 4,40) | 3 clipes, 4 quadros", linhas)
        self.assertFalse(any("Vídeo" in l for l in cost_report.format_ai_block(None, None, 5.0, date(2026, 9, 26))))


class TestAchadosDaRevisaoFase4(Base):
    """Achados da revisão adversária da Fase 4 (26/09/2026), um teste por achado."""

    def test_teto_mensal_reserva_renderizacoes_em_andamento(self):
        from video import estimativa

        outro = vp.criar_projeto(self.db, "uid", roteiro())["projeto_id"]
        previa.gerar_previa(self.db, outro, "uid", self.srv)
        comandos.renderizar(self.db, "uid", outro, self.disparar, agora=AGORA)  # ainda rodando: nada gravado
        reservado = comandos.reservado_em_andamento(self.db, "uid", exceto=self.pid)
        self.assertGreater(reservado, 0.7)
        gasto = comandos.gasto_do_mes(self.db, AGORA)
        meu_max = self.doc()["orcamento_usd"] - self.doc()["custo_real_usd"]
        precos = estimativa.mesclar_precos({"teto_mensal_usd": gasto + meu_max + reservado / 2})
        with self.assertRaises(comandos.Recusado) as ctx:
            comandos.avaliar_renderizacao(self.db, "uid", self.pid, precos=precos, agora=AGORA)
        self.assertIn("em andamento", str(ctx.exception))

    def test_sim_para_uma_previa_que_mudou_e_recusado(self):
        aprovado = comandos.avaliar_renderizacao(self.db, "uid", self.pid, agora=AGORA)
        previa.ajustar(self.db, self.pid, "uid", self.srv, cenas=[
            {"ordem": 1, "narracao": "Uma frase bem mais longa que a anterior para mudar a duração da cena."}])
        r = comandos.renderizar(self.db, "uid", self.pid, self.disparar, aprovado=aprovado, agora=AGORA)
        self.assertEqual(r["status"], "recusado")
        self.assertIn("mudou desde a prévia", r["erro"])
        self.assertEqual(self.disparos, [])

    def test_erro_vindo_da_previa_nao_deixa_renderizar(self):
        with mock.patch.object(self.srv, "publicar", side_effect=RuntimeError("Drive 500")):
            previa.ajustar(self.db, self.pid, "uid", self.srv, quadros=[{"indice": 1, "instrucao": "mais luz"}])
        self.assertEqual(self.doc()["status"], vp.ERRO)
        with self.assertRaises(comandos.Recusado) as ctx:
            comandos.avaliar_renderizacao(self.db, "uid", self.pid, agora=AGORA)
        self.assertIn("storyboard aprovável", str(ctx.exception))

    def test_worker_desatualizado_recusa_com_instrucao_de_deploy(self):
        comandos.renderizar(self.db, "uid", self.pid, self.disparar, agora=AGORA)
        self.doc()["worker_min_versao"] = renderizacao.VERSAO_WORKER + 1
        r = self.worker()
        self.assertEqual(r["status"], "recusado")
        self.assertIn("deploy_video_worker.bat", r["erro"])

    def test_worker_parado_pode_ser_retomado_e_ativo_nao(self):
        from datetime import timedelta

        comandos.renderizar(self.db, "uid", self.pid, self.disparar, agora=AGORA)
        with self.assertRaises(comandos.Recusado):  # acabou de ser pedido
            comandos.avaliar_renderizacao(self.db, "uid", self.pid, agora=AGORA + timedelta(minutes=5))
        depois = AGORA + timedelta(minutes=20)  # nenhum worker pegou o projeto
        p = comandos.avaliar_renderizacao(self.db, "uid", self.pid, agora=depois)
        self.assertTrue(p["retomada"])
        r = comandos.renderizar(self.db, "uid", self.pid, self.disparar, aprovado=p, agora=depois)
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(len(self.disparos), 2)
        self.assertEqual(self.doc()["status"], vp.RENDERIZANDO)

    def test_timeout_no_disparo_e_incerto_nao_erro(self):
        class Timeout(Exception):
            pass

        def lento(pid):
            raise Timeout("Read timed out")

        r = comandos.renderizar(self.db, "uid", self.pid, lento, agora=AGORA)
        self.assertEqual(r["status"], "incerto")
        self.assertEqual(self.doc()["status"], vp.RENDERIZANDO)

    def test_retomada_so_cobra_os_clipes_que_faltam(self):
        comandos.renderizar(self.db, "uid", self.pid, self.disparar, agora=AGORA)
        self.veo = FakeVeoProvider(gerar_mp4=mp4_de, falhar={"logotipo do Ifes"})
        self.worker()  # cenas 1 e 2 prontas, 3 falhou
        p = comandos.avaliar_renderizacao(self.db, "uid", self.pid, agora=AGORA)
        self.assertEqual(p["clipes_a_gerar"], [3])
        self.assertAlmostEqual(p["custo_clipes_a_gerar_usd"], 0.2)

    def test_cancelar_e_irreversivel_e_fora_da_voz(self):
        from tools import registry

        self.assertTrue(registry.mcp_annotations("video_cancelar")["destructiveHint"])
        self.assertFalse(registry.is_voice_enabled("video_cancelar"))


class TestPisoDeConfirmacaoPeloMcp(Base):
    """video_renderizar pelo MCP: 1ª chamada = prévia com custo + confirmation_id; nada dispara sem o sim."""

    def setUp(self):
        super().setUp()
        import mcp_server
        from tools.tool_context import ToolContext

        self.mcp = mcp_server
        self.ctx = ToolContext(user_uid="uid", _db=self.db)
        p = mock.patch.object(mcp_server, "_access_config", return_value={"confirm_tools": set()})
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch("video.disparo.disparar_worker", side_effect=self.disparar)
        p.start()
        self.addCleanup(p.stop)

    def chamar(self, nome, args):
        from tools.tool_context import ToolContext

        ctx = ToolContext(user_uid="uid", _db=self.db)
        res = self.mcp._handle_tools_call({"name": nome, "arguments": args}, ctx=ctx)
        return res, json.loads(res["content"][0]["text"])

    def test_piso_exige_confirmacao_nas_duas_pagas_e_nao_no_cancelar(self):
        self.assertTrue(self.mcp._exige_confirmacao("video_renderizar"))
        self.assertTrue(self.mcp._exige_confirmacao("video_refazer_cena"))
        self.assertFalse(self.mcp._exige_confirmacao("video_cancelar"))

    def test_primeira_chamada_so_mostra_o_custo_e_o_sim_dispara(self):
        _, corpo = self.chamar("video_renderizar", {"projeto_id": self.pid})
        self.assertEqual(corpo["status"], "confirmation_required", corpo)
        self.assertIn("confirmation_id", corpo)
        self.assertAlmostEqual(corpo["preview"]["custo_clipes_a_gerar_usd"], 0.7)
        self.assertEqual(self.disparos, [])
        self.assertEqual(self.doc()["status"], vp.AGUARDANDO_STORYBOARD)
        res, feito = self.chamar("confirmar_acao", {"confirmation_id": corpo["confirmation_id"]})
        self.assertFalse(res.get("isError"), feito)
        self.assertEqual(self.disparos, [self.pid])
        self.assertEqual(self.doc()["status"], vp.RENDERIZANDO)
        _, de_novo = self.chamar("confirmar_acao", {"confirmation_id": corpo["confirmation_id"]})
        self.assertEqual(de_novo.get("status"), "ja_executada")
        self.assertEqual(len(self.disparos), 1)

    def test_confirmacao_de_uma_previa_que_mudou_nao_executa(self):
        _, corpo = self.chamar("video_renderizar", {"projeto_id": self.pid})
        previa.ajustar(self.db, self.pid, "uid", self.srv, cenas=[{"ordem": 2, "narracao": "Curto."}])
        _, feito = self.chamar("confirmar_acao", {"confirmation_id": corpo["confirmation_id"]})
        self.assertIn("mudou desde a prévia", json.dumps(feito, ensure_ascii=False))
        self.assertEqual(self.disparos, [])

    def test_previa_recusada_nao_cria_confirmacao(self):
        self.doc()["status"] = vp.ROTEIRO
        res, corpo = self.chamar("video_renderizar", {"projeto_id": self.pid})
        self.assertTrue(res.get("isError"))
        self.assertIn("storyboard aprovado", corpo["erro"])
        self.assertFalse(any(k.startswith("mcp_confirmations/") for k in self.db.docs))


if __name__ == "__main__":
    unittest.main()
