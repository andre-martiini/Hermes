import unittest

from v2v import distribuir_mundos, prompt, segmentar


def falas(frases):
    """[(texto, inicio_s, fim_s)] → palavras com o formato do legendas.py."""
    saida = []
    for texto, ini, fim in frases:
        ps = texto.split()
        passo = (fim - ini) / len(ps)
        for k, p in enumerate(ps):
            saida.append({"text": (" " if saida else "") + p, "startMs": round((ini + k * passo) * 1000),
                          "endMs": round((ini + (k + 1) * passo - 0.05) * 1000)})
    return saida


class TestSegmentar(unittest.TestCase):
    def test_corta_em_fim_de_frase_dentro_de_5_a_10s(self):
        p = falas([("Primeira frase curta aqui.", 0, 3.0), ("Segunda frase que vai até seis.", 3.4, 6.5),
                   ("Terceira frase longa que passa dos dez segundos.", 6.9, 11.5), ("Quarta e última.", 11.9, 14.0)])
        cortes = segmentar(p, 14.2)
        for c in cortes:
            self.assertLessEqual(c["fim"] - c["inicio"], 10.0)
        self.assertGreaterEqual(cortes[0]["fim"] - cortes[0]["inicio"], 5.0)
        self.assertAlmostEqual(cortes[0]["fim"], 6.7, places=1)  # entre "seis." e "Terceira"
        self.assertTrue(cortes[0]["texto"].endswith("seis."))
        self.assertEqual(cortes[-1]["fim"], 14.2)

    def test_nunca_corta_dentro_de_palavra(self):
        p = falas([("fala corrida sem ponto nenhum mas com algumas pausas pequenas entre as palavras ditas", 0, 22)])
        cortes = segmentar(p, 22)
        for c in cortes[:-1]:
            dentro = [w for w in p if w["startMs"] / 1000 < c["fim"] < w["endMs"] / 1000]
            self.assertEqual(dentro, [])

    def test_sobra_curta_junta_no_anterior(self):
        p = falas([("Uma frase de sete segundos inteiros aqui.", 0, 7.0), ("Fim.", 7.3, 8.0)])
        cortes = segmentar(p, 8.2)
        self.assertEqual(len(cortes), 1)

    def test_mundos_e_prompt(self):
        mundos = [{"nome": "a", "cenario": "x", "roupa": "y"}, {"nome": "b", "cenario": "z", "roupa": "w"}]
        cortes = distribuir_mundos([{"i": i} for i in range(4)], mundos)
        self.assertEqual([c["mundo"] for c in cortes], ["a", "b", "a", "b"])
        self.assertIn("@Video1", prompt(mundos[0], "fal-ai/kling-video/o3/standard/video-to-video/edit"))
        self.assertNotIn("@Video1", prompt(mundos[0], "fal-ai/wan-vace-apps/video-edit"))


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- recorte (alfa suave), Gaspar Vídeo v2
import os
from pathlib import Path

import numpy as np

from efeitos import CINTILACAO_MAX, furos_internos, medir_recorte, refinar_alfa


def _silhueta(h=200, w=120):
    a = np.zeros((h, w), np.float32)
    a[40:200, 20:100] = 1.0  # tronco/cabeça sólidos
    return a


class TestRecorte(unittest.TestCase):
    def test_furo_no_pescoco_fecha_e_vao_no_cabelo_fica(self):
        a = _silhueta()
        a[120:126, 55:61] = 0.0  # furo no pescoço (abaixo do topo do rosto)
        a[44:47, 55:58] = 0.0    # vão entre fios, acima do topo do rosto (y=60)
        r = refinar_alfa(a, None, topo_rosto=60)
        self.assertGreater(r[123, 58], 0.95)
        self.assertLess(r[45, 56], 0.6)

    def test_furo_dentro_de_borda_semitransparente_nao_conta(self):
        a = _silhueta()
        a[100:120, 90:100] = 0.55
        a[108:111, 94:96] = 0.0
        self.assertEqual(int(furos_internos(a, 0).sum()), 0)

    def test_nucleo_do_rosto_sempre_opaco_e_borda_suave(self):
        a = _silhueta()
        nucleo = np.zeros_like(a, bool)
        nucleo[60:90, 40:80] = True
        a[70:75, 50:55] = 0.3  # o modelo "duvidou" dentro do rosto
        r = refinar_alfa(a, None, nucleo, topo_rosto=60)
        self.assertTrue((r[nucleo] == 1).all())
        borda = r[150, 15:25]
        self.assertTrue(((borda > 0.02) & (borda < 0.98)).any(), "borda tem degradê")
        self.assertGreater(r[150, 22], 0.9, "suaviza para fora, sem encolher")

    def test_metricas(self):
        a = _silhueta()
        m = medir_recorte([a, a.copy()])
        self.assertEqual(m["furos_px"], 0)
        self.assertLessEqual(m["cintilacao"], CINTILACAO_MAX)

    @unittest.skipUnless(os.environ.get("GASPAR_CLIPE_TESTE"), "regressão com o clipe 1000414196.mp4 (defina GASPAR_CLIPE_TESTE)")
    def test_regressao_quadros_fixos(self):
        import cv2
        import tempfile

        from efeitos import FPS, quadros_rgba, recortar

        pasta = Path(tempfile.mkdtemp())
        webm = recortar(Path(os.environ["GASPAR_CLIPE_TESTE"]), pasta / "pessoa.webm", pasta)
        refs = {round(float(p.stem.split("-")[1]) * FPS): p for p in (Path(__file__).parents[1] / "testes" / "recorte_ref").glob("alfa-*.png")}
        for k, rgba in enumerate(quadros_rgba(webm)):
            if k in refs:
                novo = cv2.resize(rgba[..., 3], (270, 480), interpolation=cv2.INTER_AREA) > 0.5
                ref = cv2.imread(str(refs[k]), cv2.IMREAD_GRAYSCALE) > 127
                self.assertGreater((novo & ref).sum() / (novo | ref).sum(), 0.97, f"quadro {k}")
            if k > max(refs):
                break
