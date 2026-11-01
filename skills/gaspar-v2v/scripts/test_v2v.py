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
