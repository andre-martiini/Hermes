import unittest
from unittest import mock

from test_video_fal import _DbEscrita
from video import dublagem


class _Resp:
    def __init__(self, ok=True, json=None, content=b"", status=200, text=""):
        self.ok, self._j, self.content, self.status_code, self.text = ok, json or {}, content, status, text

    def json(self):
        return self._j


class _Http:
    def __init__(self, estados):
        self.estados, self.posts = list(estados), []

    def post(self, url, **kw):
        self.posts.append(kw)
        return _Resp(json={"dubbing_id": "d1"})

    def get(self, url, **kw):
        if url.endswith("/audio/en"):
            return _Resp(content=b"MP4")
        return _Resp(json={"status": self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]})


class TestDublagem(unittest.TestCase):
    def _rodar(self, args, estados=("dubbing", "dubbed")):
        db = _DbEscrita({"system/api_keys": {"elevenlabs_api_key": "k"}})
        http, consumidos = _Http(estados), []
        with mock.patch("tools.anexar_arquivo._resolver_conteudo", return_value=(b"v", "clipe.mp4")), \
                mock.patch("tools.anexar_arquivo.consumir_upload_token", side_effect=lambda c, t: consumidos.append(t)), \
                mock.patch("tools.anexar_arquivo.assinar", return_value="https://assinada/d1-en.mp4"), \
                mock.patch("google.cloud.storage.Client"):
            r = dublagem.executar_tool(db, "u", args, http=http, dormir=lambda s: None)
        return r, http, db, consumidos

    def test_dubla_e_devolve_url(self):
        r, http, db, consumidos = self._rodar({"idioma": "en", "upload_token": "upl-1", "segundos": 28.5, "task_id": "t"})
        self.assertEqual(r["status"], "COMPLETED")
        self.assertEqual(r["urls"], ["https://assinada/d1-en.mp4"])
        self.assertEqual(r["custo_estimado_usd"], 0.24)
        self.assertEqual(http.posts[0]["data"]["watermark"], "false")
        self.assertEqual(consumidos, ["upl-1"])
        self.assertEqual(db.gravados["eleven-d1"]["status"], "COMPLETED")

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


if __name__ == "__main__":
    unittest.main()
