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
        self.assertIn("Último instante da cena 1: servidora lendo", self.srv.imagens[1][0])
        # Sem a descrição da cena seguinte no mesmo quadro (virava a personagem duas vezes).
        self.assertNotIn("tela do sistema", self.srv.imagens[1][0])
        self.assertIn("Cada pessoa aparece no máximo uma vez", self.srv.imagens[1][0])
        # A bíblia vale só para quem a cena menciona, e a referência não é composição a copiar.
        self.assertIn("quem não é mencionado não aparece", self.srv.imagens[1][0])
        self.assertIn("NÃO copie a composição", self.srv.imagens[1][0])
        self.assertNotIn("NÃO copie a composição", self.srv.imagens[0][0])  # K0 não tem referência
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


class TestAchadosDaRevisaoFase2(Base):
    """Achados da revisão adversária da Fase 2 (26/09/2026), um teste por achado."""

    def test_narracao_recusada_nao_descarta_as_outras_nem_paga_de_novo(self):
        self.srv._falhar_fala = {"passos"}  # recusa só a cena 2
        r = self.previa()
        self.assertEqual(r["status"], "ok")
        self.assertTrue(any(f.startswith("cena 2") for f in r["falhas"]))
        self.assertAlmostEqual(self.doc()["custo_real_usd"], 0.17)  # 1 narração + 4 quadros
        self.assertFalse(r["renderizavel"])
        self.srv._falhar_fala = set()
        r2 = self.previa()
        self.assertEqual(r2["narracoes_geradas"], 1)  # só a cena 2; a 1 não é paga de novo
        self.assertAlmostEqual(self.doc()["custo_real_usd"], 0.18)

    def test_mesma_instrucao_de_quadro_duas_vezes_nao_paga_de_novo(self):
        self.previa()
        previa.ajustar(self.db, self.pid, "uid", self.srv, quadros=[{"indice": 2, "instrucao": "mais aberta"}])
        antes = len(self.srv.imagens)
        r = previa.ajustar(self.db, self.pid, "uid", self.srv, quadros=[{"indice": 2, "instrucao": "mais aberta"}])
        self.assertIn("Nada mudou", r["mensagem"])
        self.assertEqual(len(self.srv.imagens), antes)

    def test_instrucao_antiga_nao_volta_quando_a_descricao_muda(self):
        self.previa()
        previa.ajustar(self.db, self.pid, "uid", self.srv, quadros=[{"indice": 2, "instrucao": "mais aberta"}])
        previa.ajustar(self.db, self.pid, "uid", self.srv, cenas=[{"ordem": 2, "descricao_visual": "gráfico"}])
        self.assertNotIn("mais aberta", self.srv.imagens[-1][0])

    def test_teto_acumulado_de_previas_do_projeto(self):
        from video import estimativa

        self.previa()  # 0,18
        precos = estimativa.mesclar_precos({"teto_previa_projeto_usd": 0.2})
        r = previa.ajustar(self.db, self.pid, "uid", self.srv, quadros=[{"indice": 1, "instrucao": "x"}],
                           precos=precos)
        self.assertEqual(r["status"], "recusado")
        self.assertIn("Ajustes salvos", r["erro"])
        self.assertIn("teto de US$ 0.20 em prévias por projeto", r["erro"])
        # O ajuste ficou salvo: repetir, já com teto maior, gera (não responde "Nada mudou").
        r2 = previa.ajustar(self.db, self.pid, "uid", self.srv, quadros=[{"indice": 1, "instrucao": "x"}])
        self.assertEqual(r2["status"], "ok")
        self.assertEqual(r2["quadros_gerados"], 1)

    def test_narracao_removida_vira_silencio_e_clipe_de_4s(self):
        self.previa()
        r = previa.ajustar(self.db, self.pid, "uid", self.srv, cenas=[{"ordem": 2, "narracao": ""}])
        self.assertEqual(r["cenas"][1]["duracao_s"], 4)
        cena2 = self.doc("/cenas/02")
        self.assertIsNone(cena2["audio_gcs"])
        cenas = sorted((s.to_dict() for s in self.db.collection(f"video_projetos/{self.pid}/cenas").stream()),
                       key=lambda c: c["ordem"])
        pcm, taxa = previa._linha_do_tempo(cenas, self.srv)
        trecho = pcm[4 * taxa * 2: 8 * taxa * 2]  # cena 2 ocupa 4 s depois da cena 1
        self.assertEqual(trecho.count(b"\x00"), len(trecho))

    def test_null_nao_apaga_texto(self):
        self.previa()
        r = previa.ajustar(self.db, self.pid, "uid", self.srv,
                           cenas=[{"ordem": 2, "narracao": None, "descricao_visual": None, "prompt_video": "zoom"}])
        self.assertEqual(r["status"], "ok")
        self.assertTrue(self.doc("/cenas/02")["narracao"].startswith("Veja agora"))
        self.assertEqual(self.doc("/cenas/02")["descricao_visual"], "tela do sistema")
        self.assertEqual(r["quadros_gerados"], 0)

    def test_custo_registrado_item_a_item_mesmo_quando_cai_no_meio(self):
        original = self.srv.salvar

        def salvar(caminho, dados, mime):
            if "K02" in caminho:
                raise RuntimeError("bucket fora")
            return original(caminho, dados, mime)

        with mock.patch.object(self.srv, "salvar", side_effect=salvar):
            r = self.previa()
        # K2 foi gerada (paga) mas não gravada: entra como falha, com custo.
        self.assertTrue(any("K2" in f for f in r["falhas"]))
        self.assertAlmostEqual(self.doc()["custo_real_usd"], 0.18)
        self.assertAlmostEqual(self.doc()["custo_previa_usd"], 0.18)

    def test_objeto_apagado_pelo_bucket_e_refeito(self):
        self.previa()
        for caminho in list(self.srv.arquivos):
            if "K01" in caminho or "/audio/01" in caminho:
                del self.srv.arquivos[caminho]
        r = self.previa()
        self.assertEqual(r["status"], "ok")
        self.assertEqual((r["narracoes_geradas"], r["quadros_gerados"]), (1, 1))

    def test_prazo_do_job_para_e_a_proxima_chamada_continua(self):
        r = self.previa(prazo_s=0)
        self.assertEqual(r["status"], "parcial")
        self.assertEqual(self.doc()["status"], vp.ERRO)
        self.assertAlmostEqual(self.doc()["custo_real_usd"], 0.02)  # as narrações saíram e foram cobradas
        r2 = self.previa()
        self.assertEqual(r2["status"], "ok")
        self.assertEqual((r2["narracoes_geradas"], r2["quadros_gerados"]), (0, 4))

    def test_cancelado_durante_a_previa_nao_vira_excecao(self):
        original = previa._publicar

        def cancela_e_publica(*a, **k):
            vp.transicionar(self.db, self.pid, vp.CANCELADO)
            return original(*a, **k)

        with mock.patch.object(previa, "_publicar", side_effect=cancela_e_publica):
            r = self.previa()
        self.assertEqual(r["status"], "erro")
        self.assertEqual(self.doc()["status"], vp.CANCELADO)

    def test_indice_booleano_ou_fracionario_e_recusado(self):
        self.previa()
        r = previa.ajustar(self.db, self.pid, "uid", self.srv,
                           quadros=[{"indice": True, "instrucao": "x"}, {"indice": 1.9, "instrucao": "y"}])
        self.assertEqual(r["status"], "invalido")
        self.assertEqual(len(r["erros"]), 2)

    def test_estimativa_acima_do_teto_nao_rebaixa_o_orcamento(self):
        from video import estimativa

        orcamento = self.doc()["orcamento_usd"]
        r = self.previa(precos=estimativa.mesclar_precos({"teto_projeto_usd": 0.5}))
        self.assertFalse(r["renderizavel"])
        self.assertEqual(self.doc()["orcamento_usd"], orcamento)

    def test_pcm_de_tamanho_impar_nao_quebra(self):
        self.assertEqual(midia.aparar_silencio(b"\x00\x00\x00", 24000), b"")


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

    def test_retentativa_so_para_erro_passageiro(self):
        esperas = []

        class Cota(Exception):
            code = 429

        chamadas = iter([Cota("RESOURCE_EXHAUSTED"), Cota("RESOURCE_EXHAUSTED"), "ok"])

        def chamada():
            r = next(chamadas)
            if isinstance(r, Exception):
                raise r
            return r

        self.assertEqual(midia.com_retentativa(chamada, dormir=esperas.append), "ok")
        self.assertEqual(esperas, [5, 15])
        with self.assertRaises(ValueError):  # erro de verdade não é repetido
            midia.com_retentativa(lambda: (_ for _ in ()).throw(ValueError("prompt inválido")),
                                  dormir=esperas.append)
        self.assertEqual(esperas, [5, 15])

    def test_retentativa_desiste_depois_das_esperas(self):
        class Cota(Exception):
            code = 429

        esperas = []

        def sempre_cota():
            raise Cota("RESOURCE_EXHAUSTED")

        with self.assertRaises(Cota):
            midia.com_retentativa(sempre_cota, dormir=esperas.append)
        self.assertEqual(esperas, [5, 15, 30])

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
