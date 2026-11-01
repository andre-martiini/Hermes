import struct
import unittest
from unittest import mock

from test_video_fal import _DbEscrita
from video import dublagem


class _Resp:
    def __init__(self, ok=True, json=None, content=b"", status=200, text="", headers=None):
        self.ok, self._j, self.content, self.status_code, self.text = ok, json or {}, content, status, text
        self.headers = headers or {}

    def json(self):
        return self._j


class _Http:
    def __init__(self, estados):
        self.estados, self.posts = list(estados), []

    def post(self, url, **kw):
        self.posts.append(kw)
        return _Resp(json={"dubbing_id": "dub123"})

    def get(self, url, **kw):
        if url.endswith("/audio/en"):
            return _Resp(content=b"MP4", headers={"content-type": "video/mp4"})
        return _Resp(json={"status": self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]})


def _mp4(segundos, escala=1000):
    """MP4 mínimo com só o átomo mvhd (versão 0)."""
    corpo = b"\x00\x00\x00\x00" + struct.pack(">II", 0, 0) + struct.pack(">II", escala, int(segundos * escala))
    return b"\x00\x00\x00\x00ftypisom" + struct.pack(">I", 8 + len(corpo)) + b"mvhd" + corpo


class TestDublagem(unittest.TestCase):
    def _rodar(self, args, estados=("dubbing", "dubbed"), dados=b"v", nome="clipe.mp4"):
        db = _DbEscrita({"system/api_keys": {"elevenlabs_api_key": "k"}})
        http, consumidos = _Http(estados), []
        with mock.patch("tools.anexar_arquivo._resolver_conteudo", return_value=(dados, nome)), \
                mock.patch("tools.anexar_arquivo.consumir_upload_token", side_effect=lambda c, t: consumidos.append(t)), \
                mock.patch("tools.anexar_arquivo.assinar", return_value="https://assinada/dub123-en.mp4"), \
                mock.patch("google.cloud.storage.Client"):
            r = dublagem.executar_tool(db, "u", args, http=http, dormir=lambda s: None)
        return r, http, db, consumidos

    def test_dubla_e_devolve_url(self):
        r, http, db, consumidos = self._rodar({"idioma": "en", "upload_token": "upl-1", "segundos": 28.5, "task_id": "t"})
        self.assertEqual(r["status"], "COMPLETED")
        self.assertEqual(r["urls"], ["https://assinada/dub123-en.mp4"])
        self.assertEqual(r["custo_estimado_usd"], 0.24)
        self.assertEqual(http.posts[0]["data"]["watermark"], "false")
        self.assertEqual(consumidos, ["upl-1"])
        self.assertEqual(db.gravados["eleven-dub123"]["status"], "COMPLETED")

    def test_acima_do_teto_nao_gasta(self):
        r, http, _, _ = self._rodar({"idioma": "en", "drive_file_id": "d", "segundos": 900})
        self.assertEqual(r["status"], "confirmation_required")
        self.assertEqual(http.posts, [])

    def test_sem_duracao_ou_fonte_recusa(self):
        self.assertIn("segundos", self._rodar({"idioma": "en", "drive_file_id": "d"})[0]["erro"])
        self.assertIn("exatamente um", self._rodar({"idioma": "en", "segundos": 5})[0]["erro"])

    def test_falha_da_elevenlabs(self):
        r, *_ = self._rodar({"idioma": "en", "drive_file_id": "d", "segundos": 10}, estados=("failed",))
        self.assertIn("falhou", r["erro"])

    def test_duracao_lida_do_arquivo(self):
        self.assertAlmostEqual(dublagem.duracao_mp4(_mp4(28.5)), 28.5)
        self.assertIsNone(dublagem.duracao_mp4(b"nada"))

    def test_teto_vale_a_duracao_real_mesmo_declarando_menos(self):
        r, http, _, _ = self._rodar({"idioma": "en", "drive_file_id": "d", "segundos": 60}, dados=_mp4(1200))
        self.assertEqual(r["status"], "confirmation_required")
        self.assertEqual(r["custo_estimado_usd"], 10.0)
        self.assertEqual(http.posts, [])

    def test_retomada_de_id_alheio_ou_invalido_recusa(self):
        self.assertIn("desconhecido", self._rodar({"dubbing_id": "abc12345"})[0]["erro"])
        self.assertIn("inválido", self._rodar({"dubbing_id": "../../v1/history"})[0]["erro"])

    def test_nome_saneado(self):
        _, http, _, _ = self._rodar({"idioma": "en", "drive_file_id": "d", "segundos": 5}, nome="aula/../final #1.mp4")
        self.assertEqual(http.posts[0]["files"]["file"][0], "final__1.mp4")

    def test_envio_que_cai_na_rede_nao_estoura(self):
        db = _DbEscrita({"system/api_keys": {"elevenlabs_api_key": "k"}})

        class Caido(_Http):
            def post(self, url, **kw):
                raise TimeoutError("lento")

        with mock.patch("tools.anexar_arquivo._resolver_conteudo", return_value=(b"v", "c.mp4")):
            r = dublagem.executar_tool(db, "u", {"idioma": "en", "drive_file_id": "d", "segundos": 5}, http=Caido([]))
        self.assertIn("pagar duas vezes", r["erro"])


if __name__ == "__main__":
    unittest.main()
