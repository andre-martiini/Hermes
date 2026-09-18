"""Descricao de imagens na consolidacao do WhatsApp.

`whatsapp_consolidation` faz `ZoneInfo("America/Sao_Paulo")` no import, que exige a base
de fusos do sistema (existe no Linux da Cloud Function, nao no Windows) — por isso o
import acontece com `zoneinfo.ZoneInfo` trocado. `hermes_core_logic` (pesado) tambem e
substituido por um modulo de mentira com so o que o codigo importa dele.
"""
import sys
import types as pytypes
import unittest
from datetime import timezone
from unittest import mock


class _Bucket:
    def __init__(self, arquivos=None, falha=()):
        self.arquivos = arquivos or {}
        self.falha = set(falha)
        self.baixados = []

    def blob(self, caminho):
        bucket = self

        class _Blob:
            def download_as_bytes(self_inner):
                bucket.baixados.append(caminho)
                if caminho in bucket.falha:
                    raise RuntimeError("storage fora do ar")
                return bucket.arquivos.get(caminho, b"\xff\xd8fake")

        return _Blob()


class _Ref:
    def __init__(self):
        self.gravacoes = []

    def set(self, valores, merge=False):
        self.gravacoes.append(dict(valores))


class _Resposta:
    def __init__(self, text):
        self.text = text


def _carregar(bucket, chaves=None):
    fake_core = pytypes.ModuleType("hermes_core_logic")
    fake_core._get_hermes_storage_bucket = lambda: bucket
    fake_core._get_api_keys = lambda db=None: {"gemini_api_key": "k"} if chaves is None else chaves
    with mock.patch("zoneinfo.ZoneInfo", lambda chave: timezone.utc):
        sys.modules.pop("whatsapp_consolidation", None)
        import whatsapp_consolidation as wc
    return wc, fake_core


def _msg(id_, tipo="image", path=None, **extra):
    d = {"id": id_, "message_type": tipo, "content": "", "from_me": False,
         "author_name": "Fulano", "timestamp": None}
    if path is not None:
        d["media"] = {"storage_path": path, "sizeBytes": 1000, "mimeType": "image/jpeg"}
    d.update(extra)
    return d


class TestTranscritoComImagem(unittest.TestCase):
    def setUp(self):
        self.wc, _ = _carregar(_Bucket())

    def _linha(self, msg):
        return self.wc._build_transcript([msg]).splitlines()[-1]

    def test_descrita_vem_rotulada_como_automatica(self):
        linha = self._linha(_msg("a", image_description="Print de conversa. Texto visível: 'ok'."))
        self.assertIn("[imagem — descrição automática] Print de conversa.", linha)

    def test_legenda_fica_ao_lado_da_descricao(self):
        linha = self._linha(_msg("a", content="olha isso", image_description="Foto de uma nota fiscal."))
        self.assertTrue(linha.endswith("Foto de uma nota fiscal. — legenda: olha isso"))

    def test_placeholder_nao_ganha_rotulo_de_descricao(self):
        linha = self._linha(_msg("a", image_description="[imagem não capturada]"))
        self.assertTrue(linha.endswith(": [imagem não capturada]"))
        self.assertNotIn("descrição automática", linha)

    def test_indisponivel_tambem_e_placeholder(self):
        linha = self._linha(_msg("a", image_description="[Descrição indisponível: Timeout]"))
        self.assertNotIn("descrição automática", linha)

    def test_sem_nada_vira_imagem_sem_descricao(self):
        linha = self._linha(_msg("a"))
        self.assertTrue(linha.endswith(": [imagem sem descrição]"))

    def test_figurinha_continua_como_antes(self):
        linha = self._linha(_msg("a", tipo="sticker"))
        self.assertTrue(linha.endswith(": [sticker]"))


class TestDescreverImagens(unittest.TestCase):
    def _rodar(self, messages, bucket=None, resposta="Foto de um gato.", chaves=None):
        bucket = bucket or _Bucket()
        wc, core = _carregar(bucket, chaves)
        refs = {m["id"]: _Ref() for m in messages}
        job_ref = _Ref()
        chamadas = []

        def falso_generate(client, **kw):
            chamadas.append(kw)
            if isinstance(resposta, Exception):
                raise resposta
            return _Resposta(resposta)

        with mock.patch.dict(sys.modules, {"hermes_core_logic": core}), \
             mock.patch.object(wc, "generate_content_logged", falso_generate):
            saida = wc._describe_selected_images(None, job_ref, messages, refs)
        return saida, refs, chamadas, bucket, wc

    def test_descreve_e_cacheia_em_campo_proprio(self):
        msgs = [_msg("a", path="whatsapp_media/c/a.jpeg")]
        (descritas, ignoradas), refs, chamadas, _, _ = self._rodar(msgs)
        self.assertEqual((descritas, ignoradas), (1, 0))
        self.assertEqual(msgs[0]["image_description"], "Foto de um gato.")
        gravado = refs["a"].gravacoes[0]
        self.assertEqual(gravado["image_description"], "Foto de um gato.")
        self.assertEqual(gravado["image_description_model"], "gemini-image-understanding")
        self.assertNotIn("transcription_text", gravado)
        self.assertEqual(chamadas[0]["feature"], "whatsapp_consolidation.image_description")

    def test_cache_nao_rebaixa_nem_rechama_o_gemini(self):
        msgs = [_msg("a", path="whatsapp_media/c/a.jpeg", image_description="já descrita")]
        (descritas, ignoradas), refs, chamadas, bucket, _ = self._rodar(msgs)
        self.assertEqual((descritas, ignoradas), (0, 0))
        self.assertEqual(chamadas, [])
        self.assertEqual(bucket.baixados, [])
        self.assertEqual(refs["a"].gravacoes, [])

    def test_so_imagens_sao_tocadas(self):
        msgs = [_msg("t", tipo="chat"), _msg("v", tipo="video", path="whatsapp_media/c/v.mp4"),
                _msg("s", tipo="sticker", path="whatsapp_media/c/s.webp")]
        (descritas, ignoradas), _, chamadas, _, _ = self._rodar(msgs)
        self.assertEqual((descritas, ignoradas, chamadas), (0, 0, []))
        self.assertTrue(all("image_description" not in m for m in msgs))

    def test_sem_arquivo_no_storage(self):
        msgs = [_msg("a")]
        (descritas, ignoradas), _, chamadas, _, _ = self._rodar(msgs)
        self.assertEqual((descritas, ignoradas), (0, 1))
        self.assertEqual(msgs[0]["image_description"], "[imagem não capturada]")
        self.assertEqual(chamadas, [])

    def test_formato_nao_suportado_e_ignorado(self):
        msgs = [_msg("a", path="whatsapp_media/c/a.gif")]
        (descritas, ignoradas), _, _, bucket, _ = self._rodar(msgs)
        self.assertEqual((descritas, ignoradas), (0, 1))
        self.assertIn(".gif", msgs[0]["image_description"])
        self.assertEqual(bucket.baixados, [])

    def test_arquivo_grande_demais_e_ignorado(self):
        msgs = [_msg("a", path="whatsapp_media/c/a.jpeg")]
        msgs[0]["media"]["sizeBytes"] = 50 * 1024 * 1024
        (descritas, ignoradas), _, _, bucket, _ = self._rodar(msgs)
        self.assertEqual((descritas, ignoradas), (0, 1))
        self.assertIn("excede", msgs[0]["image_description"])
        self.assertEqual(bucket.baixados, [])

    def test_falha_do_gemini_nao_e_cacheada_para_o_retry_funcionar(self):
        msgs = [_msg("a", path="whatsapp_media/c/a.jpeg")]
        (descritas, ignoradas), refs, _, _, _ = self._rodar(msgs, resposta=TimeoutError("lento"))
        self.assertEqual((descritas, ignoradas), (0, 1))
        self.assertTrue(msgs[0]["image_description"].startswith("[Descrição indisponível"))
        self.assertEqual(refs["a"].gravacoes, [])

    def test_resposta_vazia_nao_e_cacheada(self):
        msgs = [_msg("a", path="whatsapp_media/c/a.jpeg")]
        (descritas, ignoradas), refs, _, _, _ = self._rodar(msgs, resposta="   ")
        self.assertEqual((descritas, ignoradas), (0, 1))
        self.assertEqual(refs["a"].gravacoes, [])

    def test_sem_chave_do_gemini_nao_levanta(self):
        msgs = [_msg("a", path="whatsapp_media/c/a.jpeg")]
        (descritas, ignoradas), _, chamadas, _, _ = self._rodar(msgs, chaves={})
        self.assertEqual((descritas, ignoradas, chamadas), (0, 1, []))
        self.assertIn("API Key", msgs[0]["image_description"])

    def test_falha_de_download_de_uma_nao_derruba_as_outras(self):
        msgs = [_msg("a", path="whatsapp_media/c/a.jpeg"), _msg("b", path="whatsapp_media/c/b.jpeg")]
        bucket = _Bucket(falha={"whatsapp_media/c/a.jpeg"})
        (descritas, ignoradas), _, _, _, _ = self._rodar(msgs, bucket=bucket)
        self.assertEqual((descritas, ignoradas), (1, 1))
        self.assertIn("falha ao baixar", msgs[0]["image_description"])
        self.assertEqual(msgs[1]["image_description"], "Foto de um gato.")

    def test_orcamento_de_tempo_esgotado_nao_cacheia(self):
        wc, _ = _carregar(_Bucket())
        msgs = [_msg("a", path="whatsapp_media/c/a.jpeg")]
        with mock.patch.object(wc, "MAX_IMAGE_PROCESSING_SECONDS", -1):
            fake_core = pytypes.ModuleType("hermes_core_logic")
            fake_core._get_hermes_storage_bucket = lambda: _Bucket()
            refs = {"a": _Ref()}
            with mock.patch.dict(sys.modules, {"hermes_core_logic": fake_core}):
                descritas, ignoradas = wc._describe_selected_images(None, _Ref(), msgs, refs)
        self.assertEqual((descritas, ignoradas), (0, 1))
        self.assertIn("orçamento de tempo", msgs[0]["image_description"])
        self.assertEqual(refs["a"].gravacoes, [])

    def test_descricao_longa_e_cortada_e_sem_quebra_de_linha(self):
        longa = "linha\n" * 1000
        msgs = [_msg("a", path="whatsapp_media/c/a.jpeg")]
        self._rodar(msgs, resposta=longa)
        desc = msgs[0]["image_description"]
        self.assertNotIn("\n", desc)
        self.assertLessEqual(len(desc), 1500)
        self.assertTrue(desc.endswith("…"))

    def test_mime_correto_vai_para_o_gemini(self):
        msgs = [_msg("a", path="whatsapp_media/c/a.png")]
        _, _, chamadas, _, _ = self._rodar(msgs)
        parte = chamadas[0]["contents"][0]
        self.assertEqual(parte.inline_data.mime_type, "image/png")


if __name__ == "__main__":
    unittest.main()
