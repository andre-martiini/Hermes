import unittest

from video import fal


class _Snap:
    def __init__(self, dados):
        self.exists = dados is not None
        self._d = dados

    def to_dict(self):
        return self._d


class _Db:
    def __init__(self, docs):
        self.docs = docs

    def collection(self, c):
        db = self

        class _C:
            def document(self, d):
                class _D:
                    def get(self_inner):
                        return _Snap(db.docs.get(f"{c}/{d}"))
                return _D()
        return _C()


class TestEstimativa(unittest.TestCase):
    def test_kling_o3_std_5s(self):
        self.assertEqual(fal.estimar_custo("fal-ai/kling-video/o3/standard/video-edit", segundos=5), 0.63)

    def test_imagem_e_modelo_sem_preco(self):
        self.assertEqual(fal.estimar_custo("fal-ai/flux/schnell"), 0.003)
        with self.assertRaises(fal.ErroFal):
            fal.estimar_custo("fal-ai/inexistente", segundos=5)
        with self.assertRaises(fal.ErroFal):
            fal.estimar_custo("fal-ai/wan-vace-apps/video-edit")  # por segundo, sem duração

    def test_config_sobrescreve_por_modelo(self):
        db = _Db({"config/precos_fal": {"fal-ai/flux/schnell": {"usd": 0.004}}})
        tabela = fal.precos(db)
        self.assertEqual(tabela["fal-ai/flux/schnell"]["usd"], 0.004)
        self.assertEqual(tabela["fal-ai/flux/schnell"]["unidade"], "imagem")
        self.assertEqual(fal.precos(_Db({}))["fal-ai/flux/schnell"]["usd"], 0.003)

    def test_chave_do_firestore(self):
        self.assertEqual(fal.chave(_Db({"system/api_keys": {"fal_key": "k"}})), "k")


class TestFila(unittest.TestCase):
    def test_executar_e_consultar(self):
        chamadas = []

        def http(metodo, url, api_key, corpo=None):
            chamadas.append((metodo, url))
            if metodo == "POST":
                return {"request_id": "r1", "status_url": "https://q/s", "response_url": "https://q/r"}
            if url == "https://q/s":
                return {"status": "COMPLETED"}
            return {"images": [{"url": "https://cdn/x.png"}]}

        job = fal.executar("fal-ai/flux/schnell", {"prompt": "p"}, "k", http=http)
        self.assertEqual(chamadas[0], ("POST", "https://queue.fal.run/fal-ai/flux/schnell"))
        r = fal.consultar(job, "k", http=http)
        self.assertEqual(r["status"], "COMPLETED")
        self.assertEqual(fal.urls_do_resultado(r["resultado"]), ["https://cdn/x.png"])

    def test_falha_e_pendente(self):
        self.assertEqual(fal.consultar({"status_url": "s", "response_url": "r"}, "k",
                                       http=lambda *a, **k: {"status": "IN_QUEUE"})["status"], "IN_QUEUE")
        r = fal.consultar({"status_url": "s", "response_url": "r"}, "k",
                          http=lambda *a, **k: {"status": "COMPLETED", "error": "nsfw", "error_type": "safety"})
        self.assertEqual(r["status"], "FAILED")
        self.assertIn("safety", r["erro"])


class _DbEscrita(_Db):
    def __init__(self, docs):
        super().__init__(docs)
        self.gravados = {}

    def collection(self, c):
        if c != fal.COLECAO_JOBS:
            return super().collection(c)
        db = self

        class _C:
            def document(self, d):
                class _D:
                    def set(self_inner, dados):
                        db.gravados[d] = dict(dados)

                    def update(self_inner, dados):
                        db.gravados[d].update(dados)
                return _D()
        return _C()


class TestTool(unittest.TestCase):
    KLING = "fal-ai/kling-video/o3/standard/video-edit"

    def _http_ok(self, metodo, url, api_key, corpo=None):
        if metodo == "POST":
            return {"request_id": "r9", "status_url": "s", "response_url": "r"}
        return {"status": "COMPLETED"} if url == "s" else {"video": {"url": "https://cdn/v.mp4"}}

    def test_acima_do_teto_nao_gasta_sem_aprovacao(self):
        db = _DbEscrita({"system/api_keys": {"fal_key": "k"}})
        chamou = []
        r = fal.executar_tool(db, "u", {"modelo": self.KLING, "entrada": {"prompt": "p"}, "segundos": 45},
                              http=lambda *a, **k: chamou.append(a))
        self.assertEqual(r["status"], "confirmation_required")
        self.assertEqual(r["custo_estimado_usd"], 5.67)
        self.assertEqual(chamou, [])
        self.assertEqual(db.gravados, {})

    def test_aprovado_roda_e_registra(self):
        db = _DbEscrita({"system/api_keys": {"fal_key": "k"}})
        r = fal.executar_tool(db, "u", {"modelo": self.KLING, "entrada": {"prompt": "p"}, "segundos": 45,
                                        "aprovado_ate_usd": 5.67, "task_id": "t1"},
                              http=self._http_ok, dormir=lambda s: None)
        self.assertEqual(r["status"], "COMPLETED")
        self.assertEqual(r["urls"], ["https://cdn/v.mp4"])
        job = db.gravados["r9"]
        self.assertEqual((job["status"], job["custo_real_usd"], job["task_id"], job["uid"]), ("COMPLETED", 5.67, "t1", "u"))

    def test_abaixo_do_teto_roda_direto(self):
        db = _DbEscrita({"system/api_keys": {"fal_key": "k"}})
        r = fal.executar_tool(db, "u", {"modelo": self.KLING, "entrada": {}, "segundos": 5},
                              http=self._http_ok, dormir=lambda s: None)
        self.assertEqual((r["status"], r["custo_estimado_usd"]), ("COMPLETED", 0.63))

    def test_entrada_invalida(self):
        self.assertIn("erro", fal.executar_tool(_DbEscrita({}), "u", {"modelo": "", "entrada": {}}))


if __name__ == "__main__":
    unittest.main()
