"""Hermes Vídeo Fase 3 — renderização (clipes em sequência, retomada, travas) e entrega, sem rede."""
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from video import midia, montagem, previa, renderizacao
from video import projeto as vp
from video.veo_provider import FakeVeoProvider
from video_fakes import FakeDb

from test_video_previa import roteiro


def mp4_de(pedido):
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "c.mp4"
        w, h = (1280, 720) if pedido.aspecto == "16:9" else (720, 1280)
        subprocess.run([montagem.ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i",
                        f"testsrc=size={w}x{h}:rate=24:duration={pedido.duracao_s}", "-c:v", "libx264",
                        "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(arq)], check=True, capture_output=True)
        return arq.read_bytes()


class Relogio:
    def __init__(self, passo=1.0):
        self.t, self.passo = 0.0, passo

    def __call__(self):
        self.t += self.passo
        return self.t


class Base(unittest.TestCase):
    def setUp(self, **roteiro_extra):
        self.db = FakeDb()
        self.srv = midia.ServicosFalsos()
        self.pid = vp.criar_projeto(self.db, "uid", roteiro(acao_id="acao-1", legenda=True, **roteiro_extra))["projeto_id"]
        r = previa.gerar_previa(self.db, self.pid, "uid", self.srv)
        assert r["status"] == "ok", r
        vp.transicionar(self.db, self.pid, vp.RENDERIZANDO)
        self.avisos = renderizacao.Avisos(falso=True)
        self.veo = FakeVeoProvider(gerar_mp4=mp4_de)

    def doc(self, sub=""):
        return self.db.docs[f"video_projetos/{self.pid}{sub}"]

    def clipes(self, ordem):
        prefixo = f"video_projetos/{self.pid}/clipes/{ordem:02d}_"
        return [v for k, v in self.db.docs.items() if k.startswith(prefixo)]

    def clipe(self, ordem):
        """O clipe da cena com a tentativa mais recente (o id leva a assinatura, não um número)."""
        return max(self.clipes(ordem), key=lambda c: c.get("tentativas") or 0)

    def render(self, execucao="exec-1", **kw):
        kw.setdefault("veo", self.veo)
        return renderizacao.renderizar(self.db, self.pid, execucao, servicos=self.srv, avisos=self.avisos,
                                       dormir=lambda s: None, **kw)


class TestCaminhoFeliz(Base):
    def test_clipes_em_sequencia_montagem_e_entrega(self):
        r = self.render()
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(self.doc()["status"], vp.CONCLUIDO)
        self.assertEqual(len(self.veo.pedidos), 3)
        self.assertEqual([p.duracao_s for p in self.veo.pedidos], [4, 6, 4])
        # Clipe 1 parte do K0; os seguintes partem do último quadro real do anterior, com Ki como fim.
        k0 = self.srv.ler(self.doc("/keyframes/K00")["gcs_uri"])
        self.assertEqual(self.veo.pedidos[0].imagem_inicio, midia.recortar_quadro(k0, "16:9"))
        self.assertNotEqual(self.veo.pedidos[1].imagem_inicio, self.srv.ler(self.doc("/keyframes/K01")["gcs_uri"]))
        self.assertEqual(self.veo.pedidos[1].imagem_fim, self.srv.ler(self.doc("/keyframes/K02")["gcs_uri"]))
        # Vídeo final: 14 s menos 2 quadros repetidos.
        final = self.srv.arquivos["drive/RSC.mp4"]
        self.assertAlmostEqual(montagem.duracao(final), 14 - 2 / 24, delta=1 / 24 + 0.03)
        self.assertAlmostEqual(self.doc()["custo_real_usd"], 0.18 + 14 * 0.05)
        self.assertEqual(self.doc()["video_link"], r["video_link"])
        self.assertEqual(self.avisos.anexados[0][0], "acao-1")
        self.assertEqual(len(self.avisos.mensagens), 1)
        self.assertIsNone(self.doc()["worker_execucao"])  # lease liberado

    def test_prompt_de_clipe_pede_movimento_sem_gente_nova(self):
        self.render()
        p = self.veo.pedidos[0].prompt
        self.assertIn("Cena: servidora lendo", p)
        self.assertIn("nenhuma pessoa nova surge", p)
        self.assertIn("Evite: logotipos", p)


class TestRetomadaENaoPagarDuasVezes(Base):
    def test_worker_derrubado_depois_do_clipe_1_retoma_sem_reenviar(self):
        def derruba(ordem):
            if ordem == 1:
                raise SystemExit("worker morto")

        with self.assertRaises(SystemExit):
            self.render(apos_clipe=derruba)
        self.assertEqual(self.doc()["status"], vp.RENDERIZANDO)
        self.assertEqual(len(self.veo.pedidos), 1)
        r = self.render(execucao="exec-2")
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(len(self.veo.pedidos), 3)  # 1 + 2: o clipe 1 não foi pago de novo
        self.assertAlmostEqual(self.doc()["custo_render_usd"], 14 * 0.05)

    def test_operacao_enviada_e_nao_terminada_e_consultada_nao_reenviada(self):
        self.veo = FakeVeoProvider(gerar_mp4=mp4_de, consultas_ate_concluir=3)
        r = self.render(relogio=Relogio(passo=10_000))  # estoura a espera logo na 1ª consulta
        self.assertEqual(r["status"], "erro")
        self.assertEqual(self.clipe(1)["status"], "submetido")
        vp.transicionar(self.db, self.pid, vp.RENDERIZANDO)  # erro → renderizando (retomar)
        r2 = self.render(execucao="exec-2")
        self.assertEqual(r2["status"], "ok", r2)
        self.assertEqual(len(self.veo.pedidos), 3)

    def test_outra_execucao_ativa_recusa(self):
        from datetime import datetime, timezone

        vp.reivindicar_execucao(self.db, self.pid, "exec-a", agora=datetime.now(timezone.utc))
        r = self.render(execucao="exec-b")
        self.assertEqual(r["status"], "recusado")
        self.assertEqual(self.veo.pedidos, [])


class TestTravas(Base):
    def test_orcamento_estourado_para_antes_de_enviar(self):
        self.doc()["orcamento_usd"] = 0.18 + 4 * 0.05 + 0.01  # cabe só o clipe 1
        r = self.render()
        self.assertEqual(r["status"], "erro")
        self.assertIn("Orçamento", r["erro"])
        self.assertEqual(len(self.veo.pedidos), 1)
        self.assertEqual(self.doc()["status"], vp.ERRO)
        self.assertEqual(len(self.avisos.mensagens), 1)

    def test_cancelado_entre_clipes_para_sem_erro(self):
        def cancela(ordem):
            vp.transicionar(self.db, self.pid, vp.CANCELADO)

        r = self.render(apos_clipe=cancela)
        self.assertEqual(r["status"], "interrompido")
        self.assertEqual(len(self.veo.pedidos), 1)
        self.assertEqual(self.doc()["status"], vp.CANCELADO)

    def test_projeto_fora_de_renderizacao_e_recusado(self):
        vp.transicionar(self.db, self.pid, vp.CANCELADO)
        self.assertEqual(self.render()["status"], "recusado")


class TestFiltroEFalhas(Base):
    def test_bloqueio_reescreve_uma_vez_e_segue(self):
        self.veo = FakeVeoProvider(gerar_mp4=mp4_de, bloquear_prompts={"marca"})
        self.db.docs[f"video_projetos/{self.pid}/cenas/03"]["descricao_visual"] = "logotipo da marca"
        r = self.render()
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(len(self.veo.pedidos), 4)  # cena 3 enviada 2× (a barrada não é cobrada)
        self.assertTrue(self.clipe(3)["reescrito"])
        self.assertAlmostEqual(self.doc()["custo_render_usd"], 14 * 0.05)

    def test_barrado_de_novo_vira_bloqueado_com_motivo(self):
        self.veo = FakeVeoProvider(gerar_mp4=mp4_de, bloquear_prompts={"cartaz proibido"})
        self.db.docs[f"video_projetos/{self.pid}/cenas/03"]["descricao_visual"] = "cartaz proibido"
        r = self.render()
        self.assertEqual(r["status"], "erro")
        self.assertEqual(self.clipe(3)["status"], "bloqueado")
        self.assertIn("Ajuste a descrição visual", self.doc()["erro"])

    def test_veo_falhando_duas_vezes_para(self):
        self.veo = FakeVeoProvider(gerar_mp4=mp4_de, falhar={"tela do sistema"})
        r = self.render()
        self.assertEqual(r["status"], "erro")
        self.assertEqual(self.clipe(2)["tentativas"], 2)


class TestAchadosDaRevisaoFase3(Base):
    """Achados da revisão adversária da Fase 3 (26/09/2026), um teste por achado."""

    def veo_com_bucket(self, **kw):
        return FakeVeoProvider(gerar_mp4=mp4_de, gravar_saida=lambda uri, dados: self.srv.arquivos.__setitem__(
            uri.removeprefix(f"gs://{midia.BUCKET}/"), dados), **kw)

    def test_registro_da_operacao_perdido_nao_paga_de_novo(self):
        self.veo = self.veo_com_bucket()
        original = renderizacao.midia.com_retentativa
        chamadas = {"n": 0}

        def falha_ao_gravar_operacao(fn, **kw):
            chamadas["n"] += 1
            if chamadas["n"] == 2:  # 1ª = envio ao Veo; 2ª = gravar o operation_name
                raise RuntimeError("Firestore DEADLINE_EXCEEDED")
            return original(fn, **kw)

        with unittest.mock.patch.object(renderizacao.midia, "com_retentativa", side_effect=falha_ao_gravar_operacao):
            r = self.render()
        self.assertEqual(r["status"], "erro")
        self.assertEqual(len(self.veo.pedidos), 1)
        self.veo.consultar_operacao("operations/fake-1")  # a Vertex termina e grava no bucket
        vp.transicionar(self.db, self.pid, vp.RENDERIZANDO)
        r2 = self.render(execucao="exec-2")
        self.assertEqual(r2["status"], "ok", r2)
        self.assertEqual(len(self.veo.pedidos), 3)  # cena 1 adotada do bucket, não reenviada
        self.assertAlmostEqual(self.doc()["custo_render_usd"], 14 * 0.05)

    def test_envio_recente_sem_operacao_espera_em_vez_de_reenviar(self):
        from datetime import datetime, timezone

        agora = datetime.now(timezone.utc)
        cid = f"01_{renderizacao.assinatura(self.doc(), self.doc('/cenas/01'), self._quadros(), None)}"
        self.db.docs[f"video_projetos/{self.pid}/clipes/{cid}"] = {"status": "enviando", "tentativas": 1,
                                                                   "enviado_em": agora, "prompt": "p"}
        r = self.render()
        self.assertEqual(r["status"], "erro")
        self.assertIn("pode estar gerando", r["erro"])
        self.assertEqual(self.veo.pedidos, [])

    def _quadros(self):
        return {int(q["indice"]): q for k, q in self.db.docs.items() if "/keyframes/" in k}

    def test_storyboard_ajustado_depois_de_erro_refaz_a_cena_e_as_seguintes(self):
        self.veo = FakeVeoProvider(gerar_mp4=mp4_de, falhar={"logotipo do Ifes"})
        self.assertEqual(self.render()["status"], "erro")  # cenas 1 e 2 prontas; a 3 falha
        previa.ajustar(self.db, self.pid, "uid", self.srv, cenas=[
            {"ordem": 1, "narracao": "Uma frase bem mais longa que a anterior para mudar a duração da cena."},
            {"ordem": 3, "descricao_visual": "prédio do campus"}])
        vp.transicionar(self.db, self.pid, vp.RENDERIZANDO)
        self.veo = FakeVeoProvider(gerar_mp4=mp4_de)
        r = self.render(execucao="exec-2")
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(len(self.veo.pedidos), 3)  # cena 1 mudou → 2 começa em outro quadro → 3 mudou
        final = self.srv.arquivos["drive/RSC.mp4"]
        cenas = [self.doc(f"/cenas/0{i}")["duracao_s"] for i in (1, 2, 3)]
        self.assertAlmostEqual(montagem.duracao(final), sum(cenas) - 2 / 24, delta=1 / 24 + 0.03)

    def test_cena_bloqueada_com_descricao_corrigida_usa_prompt_novo(self):
        self.veo = FakeVeoProvider(gerar_mp4=mp4_de, bloquear_prompts={"cartaz proibido"})
        self.db.docs[f"video_projetos/{self.pid}/cenas/03"]["descricao_visual"] = "cartaz proibido"
        self.assertEqual(self.render()["status"], "erro")
        previa.ajustar(self.db, self.pid, "uid", self.srv, cenas=[{"ordem": 3, "descricao_visual": "parede lisa"}])
        vp.transicionar(self.db, self.pid, vp.RENDERIZANDO)
        r = self.render(execucao="exec-2")
        self.assertEqual(r["status"], "ok", r)
        self.assertIn("parede lisa", self.veo.pedidos[-1].prompt)
        self.assertNotIn("Versão neutra", self.veo.pedidos[-1].prompt)

    def test_cancelado_durante_a_espera_nao_envia_a_reescrita(self):
        self.veo = FakeVeoProvider(gerar_mp4=mp4_de, bloquear_prompts={"servidora lendo"})
        original = self.veo.consultar_operacao

        def cancela_e_consulta(nome):
            vp.transicionar(self.db, self.pid, vp.CANCELADO)
            return original(nome)

        self.veo.consultar_operacao = cancela_e_consulta
        r = self.render()
        self.assertEqual(r["status"], "interrompido")
        self.assertEqual(len(self.veo.pedidos), 1)

    def test_lease_perdido_durante_a_espera_para(self):
        from unittest import mock

        with mock.patch.object(renderizacao.vp, "renovar_execucao", side_effect=[True, False]):
            self.veo = FakeVeoProvider(gerar_mp4=mp4_de, consultas_ate_concluir=3)
            r = self.render()
        self.assertEqual(r["status"], "interrompido")
        self.assertEqual(len(self.veo.pedidos), 1)

    def test_acao_inexistente_nao_derruba_a_entrega_nem_duplica_no_drive(self):
        def anexar(acao_id, **kw):
            raise KeyError("tarefas/acao-1 não existe")

        self.avisos.anexar = anexar
        r = self.render()
        self.assertEqual(r["status"], "ok", r)
        self.assertTrue(any("Não consegui anexar" in a for a in r["avisos"]))
        self.assertEqual(self.srv.publicados.count("RSC.mp4"), 1)

    def test_retomada_da_montagem_nao_publica_de_novo(self):
        from unittest import mock

        real = vp.transicionar

        def morre_antes_de_concluir(db, pid, para, **kw):
            if para == vp.CONCLUIDO:
                raise SystemExit("worker morto depois de publicar")
            return real(db, pid, para, **kw)

        with mock.patch.object(renderizacao.vp, "transicionar", side_effect=morre_antes_de_concluir):
            with self.assertRaises(SystemExit):
                self.render()
        self.assertEqual(self.doc()["status"], vp.MONTANDO)
        r = self.render(execucao="exec-2")
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(self.srv.publicados.count("RSC.mp4"), 1)

    def test_projeto_nao_renderizavel_e_recusado_sem_gastar(self):
        self.db.docs[f"video_projetos/{self.pid}/cenas/02"]["dividir"] = True
        r = self.render()
        self.assertEqual(r["status"], "recusado")
        self.assertIn("não cabe em 8 s", r["erro"])
        self.assertEqual(self.veo.pedidos, [])

    def test_clipe_ja_contado_nao_conta_de_novo(self):
        self.render()
        antes = self.doc()["custo_real_usd"]
        ctx = renderizacao._Contexto(self.db, self.db.collection("video_projetos").document(self.pid), self.pid,
                                     "exec-1", self.veo, self.srv, lambda s: None, Relogio(),
                                     lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        doc = self.db.collection(f"video_projetos/{self.pid}/clipes").document(
            next(k.rsplit("/", 1)[-1] for k in self.db.docs if "/clipes/01_" in k))
        renderizacao._concluir(ctx, doc, "gs://x", 0.2, 1, None)
        self.assertEqual(self.doc()["custo_real_usd"], antes)


class TestMusica(Base):
    def test_sem_faixa_no_bucket_sai_sem_musica_e_avisa(self):
        self.doc()["musica"] = "calmo"
        r = self.render()
        self.assertEqual(r["status"], "ok")
        self.assertTrue(any("sem música" in a for a in r["avisos"]))


if __name__ == "__main__":
    unittest.main()
