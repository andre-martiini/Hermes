"""Hermes Vídeo Fase 3 — montagem com ffmpeg sobre clipes sintéticos (testsrc), sem rede."""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from video import midia, montagem


def clipe(segundos, cor="testsrc", tamanho="1280x720"):
    """MP4 sem áudio, 24 fps, como os do Veo."""
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "c.mp4"
        subprocess.run([montagem.ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i",
                        f"{cor}=size={tamanho}:rate=24:duration={segundos}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        str(arq)], check=True, capture_output=True)
        return arq.read_bytes()


def fala(segundos, taxa=24000):
    import numpy as np

    t = np.arange(int(segundos * taxa)) / taxa
    return ((np.sin(2 * np.pi * 220 * t) * 9000).astype(np.int16).tobytes(), taxa)


def sonoridade(mp4):
    """LUFS integrado medido pelo próprio ffmpeg (ebur128)."""
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "f.mp4"
        arq.write_bytes(mp4)
        proc = subprocess.run([montagem.ffmpeg_exe(), "-hide_banner", "-i", str(arq), "-af", "ebur128", "-f", "null",
                               "-"], capture_output=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", proc.stderr.decode(errors="replace"))[-1])


def fluxos(mp4):
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "f.mp4"
        arq.write_bytes(mp4)
        proc = subprocess.run([montagem.ffmpeg_exe(), "-hide_banner", "-i", str(arq)], capture_output=True)
    return proc.stderr.decode(errors="replace")


class TestTempos(unittest.TestCase):
    def test_cada_cena_depois_da_primeira_perde_um_quadro(self):
        self.assertEqual(montagem.inicios_das_cenas([4, 6, 4]), [0.0, 4.0, round(10 - 1 / 24, 4)])
        self.assertAlmostEqual(montagem.duracao_total([4, 6, 4]), 14 - 2 / 24, places=3)

    def test_srt_pula_cena_sem_texto(self):
        srt = montagem.gerar_srt(["Olá", "", "Fim"], [0, 4, 9.958], [2.5, 4, 11.2])
        self.assertEqual(srt.count("-->"), 2)
        self.assertIn("00:00:00,000 --> 00:00:02,500\nOlá", srt)
        self.assertIn("2\n00:00:09,958 --> 00:00:11,200\nFim", srt)

    def test_trilha_poe_cada_fala_no_inicio_da_cena(self):
        import numpy as np

        pcm = montagem.trilha_de_narracao([fala(1), None, fala(0.5)], [0.0, 4.0, 9.0], 10.0)
        a = np.frombuffer(pcm, dtype=np.int16)
        self.assertEqual(a.size, 240000)
        self.assertTrue(np.abs(a[:24000]).max() > 0)
        self.assertEqual(np.abs(a[24000 + 10: 9 * 24000 - 10]).max(), 0)
        self.assertTrue(np.abs(a[9 * 24000: 9 * 24000 + 12000]).max() > 0)


class TestMontagem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c4 = clipe(4)
        cls.c6 = clipe(6, "testsrc2")

    def test_duracao_final_com_tolerancia_de_um_quadro(self):
        final = montagem.montar([self.c4, self.c6, self.c4], [4, 6, 4], narracoes=[fala(3), fala(5), None])
        self.assertAlmostEqual(montagem.duracao(final), 14 - 2 / 24, delta=1 / 24 + 0.03)
        info = fluxos(final)
        self.assertIn("1280x720", info)
        self.assertIn("24 fps", info)
        self.assertIn("Audio: aac", info)

    def test_audio_normalizado_em_menos_16_lufs(self):
        final = montagem.montar([self.c4, self.c6], [4, 6], narracoes=[fala(3.5), fala(5)])
        self.assertAlmostEqual(sonoridade(final), -16, delta=1)

    def test_legenda_e_musica_com_ducking(self):
        musica = midia.pcm_para_wav(*fala(2))  # 2 s em loop
        final = montagem.montar([self.c4, self.c6], [4, 6], narracoes=[fala(3), fala(5)], textos=["Um", "Dois"],
                                legenda=True, musica=musica)
        self.assertAlmostEqual(montagem.duracao(final), 10 - 1 / 24, delta=1 / 24 + 0.03)
        self.assertAlmostEqual(sonoridade(final), -16, delta=1)

    def test_vertical_e_clipe_de_tamanho_diferente_e_normalizado(self):
        final = montagem.montar([clipe(4, tamanho="1344x768")], [4], formato="9:16")
        self.assertIn("720x1280", fluxos(final))

    def test_ultimo_quadro_vira_png_do_tamanho_do_clipe(self):
        from PIL import Image
        import io

        self.assertEqual(Image.open(io.BytesIO(montagem.ultimo_quadro(self.c4))).size, (1280, 720))

    def test_sem_narracao_nenhuma_sai_com_trilha_silenciosa(self):
        final = montagem.montar([self.c4], [4])
        self.assertIn("Audio: aac", fluxos(final))


if __name__ == "__main__":
    unittest.main()
