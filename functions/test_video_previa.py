"""Hermes Vídeo Fase 2 — prévia do storyboard (narração, quadros-chave, folha de contato)."""
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from video import midia, previa
from video import projeto as vp
from video_fakes import FakeDb


def roteiro(**extra):
    base = {
        "titulo": "RSC",
        "biblia": {"estilo": "flat 2D", "personagens": ["servidora de óculos"], "evitar": "logotipos"},
        "cenas": [
            {"narracao": "O RSC reconhece o que você sabe.", "descricao_visual": "servidora lendo"},  # 7 pal.
            {"narracao": "Veja agora como pedir o reconhecimento em três passos bem simples.",  # 11 pal.
             "descricao_visual": "tela do sistema"},
            {"narracao": "", "descricao_visual": "logotipo do Ifes"},
        ],
    }
    base.update(extra)
    return base


def tamanho_png(dados):
    from PIL import Image

    return Image.open(io.BytesIO(dados)).size


class Base(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.srv = midia.ServicosFalsos()  # 0,5 s por palavra + 0,25 s de silêncio em cada ponta
        self.pid = vp.criar_projeto(self.db, "uid", roteiro())["projeto_id"]

    def doc(self, sub=""):
        return self.db.docs[f"video_projetos/{self.pid}{sub}"]

    def previa(self, **kw):
        return previa.gerar_previa(self.db, self.pid, "uid", self.srv, **kw)


class TestPreviaCompleta(Base):
    def test_gera_narracoes_quadros_folha_e_mp3(self):
        r = self.previa()
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(self.doc()["status"], vp.AGUARDANDO_STORYBOARD)
        # A cena sem narração não chama o TTS; 3 cenas = 4 quadros (K0..K3).
        self.assertEqual(len(self.srv.falas), 2)
        self.assertEqual(len(self.srv.imagens), 4)
        # Silêncio aparado: 7 palavras = 3,5 s de fala → 4 s; 11 = 5,5 s → 6 s.
        self.assertEqual([c["duracao_s"] for c in r["cenas"]], [4, 6, 4])
        self.assertAlmostEqual(r["cenas"][0]["fala_s"], 3.6, delta=0.1)
        self.assertEqual(self.srv.publicados, ["RSC — storyboard v1.png", "RSC — narração v1.mp3"])
        self.assertTrue(r["folha_contato"]["link"])
        self.assertAlmostEqual(r["gasto_desta_previa_usd"], 0.18)  # 2 × 0,01 + 4 × 0,04
        self.assertAlmostEqual(self.doc()["custo_real_usd"], 0.18)
        self.assertEqual(r["estimativa"]["segundos_video"], 14)

    def test_quadros_saem_no_tamanho_exato_e_encadeados(self):
        self.previa()
        for k in range(4):
            q = self.doc(f"/keyframes/K{k:02d}")
            self.assertEqual(tamanho_png(self.srv.ler(q["gcs_uri"])), (1280, 720))
        refs = [n for _, n in self.srv.imagens]
        self.assertEqual(refs, [0, 1, 2, 2])  # K1 usa K0; K2 e K3 usam o anterior + K0
        self.assertIn("Quadro final da cena 1", self.srv.imagens[1][0])
        self.assertIn("também abre a cena seguinte", self.srv.imagens[1][0])
        self.assertIn("Evite: logotipos", self.srv.imagens[0][0])

    def test_vertical_sai_720x1280(self):
        pid = vp.criar_projeto(self.db, "uid", roteiro(formato="9:16"))["projeto_id"]
        previa.gerar_previa(self.db, pid, "uid", self.srv)
        q = self.db.docs[f"video_projetos/{pid}/keyframes/K00"]
        self.assertEqual(tamanho_png(self.srv.ler(q["gcs_uri"])), (720, 1280))

    def test_repetir_sem_mudancas_nao_gasta_de_novo(self):
        self.previa()
        r = self.previa()
        self.assertEqual(r["status"], "ok")
        self.assertEqual((len(self.srv.falas), len(self.srv.imagens)), (2, 4))
        self.assertEqual(r["gasto_desta_previa_usd"], 0.0)
        self.assertEqual(r["previa_versao"], 2)

    def test_linha_do_tempo_ocupa_a_duracao_de_cada_clipe(self):
        self.previa()
        cenas = sorted((s.to_dict() for s in self.db.collection(f"video_projetos/{self.pid}/cenas").stream()),
                       key=lambda c: c["ordem"])
        pcm, taxa = previa._linha_do_tempo(cenas, self.srv)
        self.assertEqual(len(pcm) / (2 * taxa), 14.0)


class TestAjustes(Base):
    def setUp(self):
        super().setUp()
        self.previa()
        self.falas0, self.imgs0 = len(self.srv.falas), len(self.srv.imagens)

    def ajustar(self, **kw):
        return previa.ajustar(self.db, self.pid, "uid", self.srv, **kw)

    def novas(self):
        return len(self.srv.falas) - self.falas0, len(self.srv.imagens) - self.imgs0

    def test_nova_narracao_refaz_so_o_audio_da_cena(self):
        r = self.ajustar(cenas=[{"ordem": 2, "narracao": "Peça em três passos."}])
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(self.novas(), (1, 0))
        self.assertEqual(self.doc("/cenas/02")["versao"], 2)
        self.assertEqual(r["cenas"][1]["duracao_s"], 4)

    def test_mesmo_ajuste_de_novo_nao_muda_nada(self):
        self.ajustar(cenas=[{"ordem": 2, "narracao": "Peça em três passos."}])
        r = self.ajustar(cenas=[{"ordem": 2, "narracao": "Peça em três passos."}])
        self.assertIn("Nada mudou", r["mensagem"])
        self.assertEqual(self.novas(), (1, 0))

    def test_nova_descricao_da_cena_1_refaz_k0_e_k1(self):
        self.ajustar(cenas=[{"ordem": 1, "descricao_visual": "servidora ao telefone"}])
        self.assertEqual(self.novas(), (0, 2))
        self.assertEqual(self.doc("/keyframes/K00")["versao"], 2)
        self.assertEqual(self.doc("/keyframes/K01")["versao"], 2)
        self.assertEqual(self.doc("/keyframes/K02")["versao"], 1)

    def test_instrucao_para_um_quadro_refaz_so_ele(self):
        self.ajustar(quadros=[{"indice": 2, "instrucao": "câmera mais aberta"}])
        self.assertEqual(self.novas(), (0, 1))
        self.assertIn("Ajuste pedido: câmera mais aberta", self.srv.imagens[-1][0])

    def test_ajuste_invalido_nao_grava_nem_gasta(self):
        r = self.ajustar(cenas=[{"ordem": 9, "narracao": "x"}], quadros=[{"indice": 7, "instrucao": "y"}])
        self.assertEqual(r["status"], "invalido")
        self.assertEqual(len(r["erros"]), 2)
        self.assertEqual(self.novas(), (0, 0))

    def test_ajuste_fora_do_storyboard_e_recusado(self):
        vp.transicionar(self.db, self.pid, vp.RENDERIZANDO)
        self.assertEqual(self.ajustar(cenas=[{"ordem": 1, "narracao": "x"}])["status"], "recusado")


class TestTravasEFalhas(Base):
    def test_previa_acima_do_teto_nao_gasta_nada(self):
        from video import estimativa

        precos = estimativa.mesclar_precos({"teto_previa_usd": 0.05})
        r = self.previa(precos=precos)
        self.assertEqual(r["status"], "recusado")
        self.assertIn("acima do teto", r["erro"])
        self.assertEqual((len(self.srv.falas), len(self.srv.imagens)), (0, 0))
        self.assertEqual(self.doc()["status"], vp.ROTEIRO)

    def test_quadro_recusado_nao_derruba_a_previa_e_e_refeito_depois(self):
        self.srv = midia.ServicosFalsos(falhar_imagem_em={2})
        r = self.previa()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(len(r["falhas"]), 1)
        self.assertTrue(self.doc("/keyframes/K02")["pendente"])
        self.assertAlmostEqual(r["gasto_desta_previa_usd"], 0.14)  # quadro recusado não é cobrado
        r2 = self.previa()
        self.assertEqual(r2["falhas"], [])
        self.assertEqual(r2["quadros_gerados"], 1)

    def test_narracao_longa_demais_e_sinalizada(self):
        pid = vp.criar_projeto(self.db, "uid", roteiro(cenas=[
            {"narracao": " ".join(["p"] * 15), "descricao_visual": "x"}]))["projeto_id"]
        # 15 palavras × 0,6 s = 9 s de fala: não cabe em 8 s.
        r = previa.gerar_previa(self.db, pid, "uid", midia.ServicosFalsos(segundos_por_palavra=0.6))
        self.assertTrue(r["cenas"][0]["dividir"])
        self.assertTrue(any("encurte o texto" in a for a in r["avisos"]))

    def test_falha_no_meio_leva_a_erro_e_a_nova_previa_retoma(self):
        with mock.patch.object(self.srv, "publicar", side_effect=RuntimeError("Drive fora")):
            r = self.previa()
        self.assertEqual(r["status"], "erro")
        self.assertEqual(self.doc()["status"], vp.ERRO)
        self.assertIn("Drive fora", self.doc()["erro"])
        self.assertAlmostEqual(self.doc()["custo_real_usd"], 0.18)
        r2 = self.previa()
        self.assertEqual(r2["status"], "ok")
        self.assertEqual(r2["gasto_desta_previa_usd"], 0.0)  # checkpoints: nada foi pago de novo

    def test_duas_previas_ao_mesmo_tempo(self):
        agora = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        self.doc().update({"status": vp.PREVIA_GERANDO, "previa_iniciada_em": agora})
        r = self.previa(agora=agora + timedelta(minutes=3))
        self.assertEqual(r["status"], "recusado")
        self.assertEqual(len(self.srv.falas), 0)
        # Job morto: passados 10 min, outra prévia assume.
        self.assertEqual(self.previa(agora=agora + timedelta(minutes=11))["status"], "ok")

    def test_projeto_de_outro_usuario(self):
        self.assertEqual(previa.gerar_previa(self.db, self.pid, "outro", self.srv)["status"], "nao_encontrado")
        self.assertEqual(previa.ajustar(self.db, self.pid, "outro", self.srv)["status"], "nao_encontrado")


class TestMidiaPura(unittest.TestCase):
    def test_recorte_central_para_16_9_e_9_16(self):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (1344, 768)).save(buf, "PNG")
        self.assertEqual(tamanho_png(midia.recortar_quadro(buf.getvalue(), "16:9")), (1280, 720))
        self.assertEqual(tamanho_png(midia.recortar_quadro(buf.getvalue(), "9:16")), (720, 1280))

    def test_aparar_silencio_das_pontas(self):
        fala = midia.ServicosFalsos().gerar_fala("um dois", {}, "m")
        self.assertAlmostEqual(midia.duracao_pcm(fala.pcm, fala.taxa), 1.5, places=2)
        aparado = midia.aparar_silencio(fala.pcm, fala.taxa)
        self.assertAlmostEqual(midia.duracao_pcm(aparado, fala.taxa), 1.1, delta=0.03)  # 1,0 s + 2 × 50 ms

    def test_so_silencio_vira_vazio(self):
        self.assertEqual(midia.aparar_silencio(midia.silencio_pcm(1, 24000), 24000), b"")

    def test_taxa_do_mime_do_tts(self):
        self.assertEqual(midia.taxa_do_mime("audio/L16;codec=pcm;rate=24000"), 24000)

    def test_wav_ida_e_volta_e_mp3(self):
        pcm = midia.ServicosFalsos().gerar_fala("teste de som", {}, "m").pcm
        wav = midia.pcm_para_wav(pcm, 24000)
        self.assertEqual(midia.wav_para_pcm(wav), (pcm, 24000))
        mp3 = midia.wav_para_mp3(wav)
        self.assertGreater(len(mp3), 100)
        self.assertTrue(mp3[:3] == b"ID3" or mp3[0] == 0xFF)


class TestToolsPeloMcp(unittest.TestCase):
    def setUp(self):
        from tools.tool_context import ToolContext

        self.db = FakeDb()
        self.srv = midia.ServicosFalsos()
        self.ctx = ToolContext(user_uid="uid", _db=self.db)
        self.pid = vp.criar_projeto(self.db, "uid", roteiro())["projeto_id"]
        p = mock.patch.object(midia, "ServicosVertex", return_value=self.srv)
        p.start()
        self.addCleanup(p.stop)

    def test_gerar_previa_e_ajustar_rodam_como_job_longo(self):
        import mcp_server
        from tools import registry

        for nome in ("video_gerar_previa", "video_ajustar"):
            self.assertIn(nome, mcp_server._TOOLS_LONGAS)
            self.assertIn(nome, registry._ASYNC_TOOLS)
            self.assertFalse(mcp_server._exige_confirmacao(nome))

    def test_handler_devolve_texto_json_no_sucesso_e_erro_na_falha(self):
        from tools import hermes_tools

        ok = hermes_tools.execute("video_gerar_previa", {"projeto_id": self.pid}, self.ctx)
        self.assertIsInstance(ok, str)
        self.assertEqual(json.loads(ok)["estado"], vp.AGUARDANDO_STORYBOARD)
        falha = hermes_tools.execute("video_ajustar", {"projeto_id": self.pid, "cenas": [{"ordem": 9}]}, self.ctx)
        self.assertIsInstance(falha, dict)
        self.assertIn("Cena 9 não existe", falha["erro"])


if __name__ == "__main__":
    unittest.main()
