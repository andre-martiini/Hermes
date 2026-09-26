"""Hermes Vídeo — estimativa de custo, durações de clipe e preços vindos de config."""
import unittest

from video import estimativa as est


class TestDuracaoClipe(unittest.TestCase):
    def test_arredonda_para_o_menor_clipe_que_cabe_o_audio_com_folga(self):
        self.assertEqual(est.duracao_clipe(3.0), 4)
        self.assertEqual(est.duracao_clipe(3.8), 6)  # 3,8 + 0,3 passa de 4
        self.assertEqual(est.duracao_clipe(5.1), 6)
        self.assertEqual(est.duracao_clipe(7.7), 8)

    def test_audio_longo_demais_pede_divisao_da_cena(self):
        self.assertIsNone(est.duracao_clipe(7.9))

    def test_sem_narracao_vira_clipe_minimo(self):
        self.assertEqual(est.duracao_clipe(0), 4)

    def test_fala_estimada_por_ritmo_de_referencia(self):
        self.assertAlmostEqual(est.duracao_fala_estimada("um dois três quatro cinco"), 2.5)
        self.assertEqual(est.contar_palavras("Não mudou, Gabriela — a folha só grava."), 7)


class TestEstimativa(unittest.TestCase):
    def test_um_minuto_no_modo_padrao_bate_com_o_plano(self):
        # 8 cenas, 64 s de clipe: 64×0,05 + 9 quadros×0,04 + 8 TTS×0,01 = 3,64 → ×1,3 = 4,73
        r = est.estimar([8] * 8)
        self.assertEqual(r["modelo_video"], "veo-3.1-lite-generate-001")
        self.assertEqual(r["segundos_video"], 64)
        self.assertEqual(r["custo_estimado_usd"], 4.73)
        self.assertEqual(r["custo_previa_usd"], 0.44)
        self.assertEqual(r["teto_projeto_usd"], 7.1)  # 4,73 × 1,5 (abaixo do teto de 20)

    def test_modo_final_usa_o_fast(self):
        r = est.estimar([8] * 8, modo="final")
        self.assertEqual(r["modelo_video"], "veo-3.1-fast-generate-001")
        self.assertEqual(r["custo_video_usd"], 9.6)

    def test_teto_do_projeto_limitado_a_20(self):
        r = est.estimar([8] * 15, modo="final")
        self.assertEqual(r["teto_projeto_usd"], 20.0)

    def test_tempo_de_renderizacao_sequencial(self):
        self.assertEqual(est.estimar([4] * 8)["tempo_renderizacao_min"], 8)  # 8 × 55 s

    def test_modelo_sem_preco_e_recusado(self):
        precos = est.mesclar_precos({"modelos": {"padrao": "veo-9-inexistente"}})
        with self.assertRaises(ValueError):
            est.estimar([4], precos=precos)


class TestPrecosDeConfig(unittest.TestCase):
    def test_config_sobrescreve_so_o_que_traz(self):
        precos = est.mesclar_precos({
            "video_por_segundo": {"veo-3.1-lite-generate-001": {"720p": 0.06}},
            "margem_retrabalho": 1.0,
        })
        self.assertEqual(precos["video_por_segundo"]["veo-3.1-lite-generate-001"]["720p"], 0.06)
        self.assertEqual(precos["video_por_segundo"]["veo-3.1-fast-generate-001"]["720p"], 0.15)
        self.assertEqual(precos["margem_retrabalho"], 1.0)
        self.assertEqual(precos["teto_mensal_usd"], 30.0)
        self.assertEqual(est.estimar([4], precos=precos)["custo_video_usd"], 0.24)

    def test_mesclar_nao_altera_os_padroes(self):
        est.mesclar_precos({"imagem": 9.0, "modelos": {"padrao": "x"}})
        self.assertEqual(est.PRECOS_PADRAO["imagem"], 0.04)
        self.assertEqual(est.PRECOS_PADRAO["modelos"]["padrao"], "veo-3.1-lite-generate-001")


if __name__ == "__main__":
    unittest.main()
