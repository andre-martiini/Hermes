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
        self.assertEqual(fal.estimar_custo("fal-ai/kling-video/o3/standard/video-to-video/edit", segundos=5), 0.63)

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

                    def get(self_inner):
                        return _Snap(db.gravados.get(d))
                return _D()
        return _C()


class TestTool(unittest.TestCase):
    KLING = "fal-ai/kling-video/o3/standard/video-to-video/edit"

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

    def test_duracao_da_entrada_conta_no_custo(self):
        db = _DbEscrita({"system/api_keys": {"fal_key": "k"}})
        r = fal.executar_tool(db, "u", {"modelo": self.KLING, "entrada": {"duration": 60}, "segundos": 10},
                              http=lambda *a, **k: self.fail("não pode enviar"))
        self.assertEqual((r["status"], r["custo_estimado_usd"]), ("confirmation_required", 7.56))

    def test_custo_real_pela_duracao_gerada(self):
        db = _DbEscrita({"system/api_keys": {"fal_key": "k"}})

        def http(metodo, url, api_key, corpo=None):
            if metodo == "POST":
                return {"request_id": "r1", "status_url": "s", "response_url": "r"}
            return {"status": "COMPLETED"} if url == "s" else {"video": {"url": "https://v", "duration": 10}}
        r = fal.executar_tool(db, "u", {"modelo": self.KLING, "entrada": {}, "segundos": 5}, http=http, dormir=lambda s: None)
        self.assertEqual(r["custo_real_usd"], 1.26)
        self.assertIn("alerta_custo", r)

    def test_falha_passageira_nao_vira_falha_e_retoma_sem_cobrar(self):
        db = _DbEscrita({"system/api_keys": {"fal_key": "k"}})
        estado = {"consultas": 0}

        def http(metodo, url, api_key, corpo=None):
            if metodo == "POST":
                return {"request_id": "r2", "status_url": "s", "response_url": "r"}
            if url == "s":
                estado["consultas"] += 1
                if estado["consultas"] <= 2:
                    raise fal.ErroFal("timeout")
                return {"status": "COMPLETED"}
            return {"images": [{"url": "https://i"}]}
        r = fal.executar_tool(db, "u", {"modelo": "fal-ai/flux/schnell", "entrada": {}}, http=http, dormir=lambda s: None)
        self.assertEqual(r["status"], "COMPLETED")

        t = iter(range(0, 10_000, 100))
        pendente = fal.executar_tool(db, "u", {"modelo": "fal-ai/flux/schnell", "entrada": {}},
                                     http=lambda m, u, k, c=None: {"request_id": "r3", "status_url": "s3", "response_url": "r3"}
                                     if m == "POST" else {"status": "IN_PROGRESS"},
                                     dormir=lambda s: None, relogio=lambda: next(t))
        self.assertIn("job_fal=r3", pendente["mensagem"])
        posts = []

        def http2(m, u, k, c=None):
            posts.append(m)
            return {"status": "COMPLETED"} if u == "s3" else {"images": [{"url": "https://ok"}]}
        r = fal.executar_tool(db, "u", {"job_fal": "r3"}, http=http2, dormir=lambda s: None)
        self.assertEqual((r["status"], r["urls"], "POST" in posts), ("COMPLETED", ["https://ok"], False))

    def test_tabela_invalida_vira_erro(self):
        db = _DbEscrita({"system/api_keys": {"fal_key": "k"}, "config/precos_fal": {"fal-ai/novo": {"usd": 0.1}}})
        self.assertIn("erro", fal.executar_tool(db, "u", {"modelo": "fal-ai/novo", "entrada": {}}))

    def test_entrada_invalida(self):
        self.assertIn("erro", fal.executar_tool(_DbEscrita({}), "u", {"modelo": "", "entrada": {}}))


if __name__ == "__main__":
    unittest.main()


class TestArquivos(unittest.TestCase):
    """Entrada de arquivo por upload_token/drive_file_id: o Hermes resolve, publica e assina (Gaspar Vídeo v2)."""

    def _rodar(self, arquivos, entrada=None):
        from unittest import mock

        db = _DbEscrita({"system/api_keys": {"fal_key": "k"}})
        enviados, consumidos = [], []

        def http(metodo, url, api_key, corpo=None):
            if metodo == "POST":
                enviados.append(corpo)
                return {"request_id": "r9", "status_url": "s", "response_url": "r"}
            return {"status": "COMPLETED"} if url == "s" else {"video": {"url": "https://cdn/v.mp4"}}

        blob = mock.MagicMock()
        cliente = mock.MagicMock()
        cliente.return_value.bucket.return_value.blob.return_value = blob
        with mock.patch("tools.anexar_arquivo._resolver_conteudo", return_value=(b"mp4", "clipe.mp4")) as res, \
                mock.patch("tools.anexar_arquivo.assinar", return_value="https://assinada/clipe.mp4"), \
                mock.patch("tools.anexar_arquivo.consumir_upload_token", side_effect=lambda ctx, t: consumidos.append(t)), \
                mock.patch("google.cloud.storage.Client", cliente):
            r = fal.executar_tool(db, "u", {"modelo": TestTool.KLING, "entrada": entrada or {"prompt": "p"}, "segundos": 5,
                                            "arquivos": arquivos}, http=http, dormir=lambda s: None)
        return r, enviados, consumidos, res, blob

    def test_upload_token_vira_url_assinada_e_e_consumido(self):
        r, enviados, consumidos, res, blob = self._rodar({"video_url": {"upload_token": "upl-1"}})
        self.assertEqual(r["status"], "COMPLETED")
        self.assertEqual(enviados[0]["video_url"], "https://assinada/clipe.mp4")
        self.assertEqual(consumidos, ["upl-1"])
        blob.upload_from_string.assert_called_once()
        self.assertEqual(res.call_args[0][1], {"upload_token": "upl-1"})

    def test_drive_em_campo_de_lista(self):
        r, enviados, consumidos, _, _ = self._rodar({"image_urls": {"drive_file_id": "d1"}})
        self.assertEqual(enviados[0]["image_urls"], ["https://assinada/clipe.mp4"])
        self.assertEqual(consumidos, [])

    def test_referencia_ambigua_recusa_sem_gastar(self):
        r, enviados, _, _, _ = self._rodar({"video_url": {"upload_token": "a", "drive_file_id": "b"}})
        self.assertIn("exatamente um", r["erro"])
        self.assertEqual(enviados, [])

    def test_som_de_ambiente_tem_preco(self):
        self.assertEqual(fal.estimar_custo("fal-ai/elevenlabs/sound-effects/v2", segundos=20), 0.04)


class TestArquivosFalhas(unittest.TestCase):
    def test_falha_ao_assinar_vira_erro_e_apaga_o_publicado(self):
        from unittest import mock

        db = _DbEscrita({"system/api_keys": {"fal_key": "k"}})
        blob = mock.MagicMock()
        cliente = mock.MagicMock()
        cliente.return_value.bucket.return_value.blob.return_value = blob
        with mock.patch("tools.anexar_arquivo._resolver_conteudo", return_value=(b"x", "a/../b c.mp4")), \
                mock.patch("tools.anexar_arquivo.assinar", side_effect=ValueError("sem IAM")), \
                mock.patch("google.cloud.storage.Client", cliente):
            r = fal.executar_tool(db, "u", {"modelo": TestTool.KLING, "entrada": {}, "segundos": 5,
                                            "arquivos": {"video_url": {"drive_file_id": "d"}}}, http=lambda *a, **k: 1 / 0)
        self.assertIn("não consegui publicar", r["erro"])
        blob.delete.assert_called_once()
        self.assertTrue(cliente.return_value.bucket.return_value.blob.call_args[0][0].endswith("/b_c.mp4"))
