"""Testes das funções puras do módulo WhatsApp Cloud API (sem I/O de rede/Firestore)."""
import hashlib
import hmac
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from whatsapp_cloud import (
    parse_batch_trigger,
    _verify_meta_signature,
    _guess_extension,
    _normalize_wa_number,
)


class TestParseBatchTrigger(unittest.TestCase):
    def test_hash_prefix(self):
        self.assertEqual(parse_batch_trigger("#resumo"), (True, None))

    def test_bare_word_case_insensitive(self):
        self.assertEqual(parse_batch_trigger("Resumo"), (True, None))

    def test_accented_variant(self):
        self.assertEqual(parse_batch_trigger("résumo"), (True, None))

    def test_extra_instruction_preserves_accents(self):
        self.assertEqual(parse_batch_trigger("#RESUMO focar nas datas"), (True, "focar nas datas"))
        self.assertEqual(parse_batch_trigger("resumo: só o essencial"), (True, "só o essencial"))

    def test_regular_message_is_not_trigger(self):
        self.assertEqual(parse_batch_trigger("oi tudo bem"), (False, None))

    def test_empty_text_is_not_trigger(self):
        self.assertEqual(parse_batch_trigger(""), (False, None))
        self.assertEqual(parse_batch_trigger(None), (False, None))

    def test_word_boundary_avoids_false_positive(self):
        # "resumod" não deve casar como gatilho (evita prefixo acidental).
        self.assertEqual(parse_batch_trigger("resumod agora"), (False, None))


class TestVerifyMetaSignature(unittest.TestCase):
    def setUp(self):
        self.secret = "shh"
        self.body = b'{"a":1}'
        self.valid_sig = "sha256=" + hmac.new(self.secret.encode(), self.body, hashlib.sha256).hexdigest()

    def test_valid_signature(self):
        self.assertTrue(_verify_meta_signature(self.body, self.valid_sig, self.secret))

    def test_invalid_signature(self):
        self.assertFalse(_verify_meta_signature(self.body, "sha256=deadbeef", self.secret))

    def test_missing_header(self):
        self.assertFalse(_verify_meta_signature(self.body, None, self.secret))

    def test_missing_secret(self):
        self.assertFalse(_verify_meta_signature(self.body, self.valid_sig, ""))

    def test_wrong_algo_prefix(self):
        self.assertFalse(_verify_meta_signature(self.body, "sha1=whatever", self.secret))


class TestGuessExtension(unittest.TestCase):
    def test_known_audio_mime(self):
        self.assertEqual(_guess_extension("audio/ogg; codecs=opus", "audio"), "ogg")

    def test_known_video_mime(self):
        self.assertEqual(_guess_extension("video/mp4", "video"), "mp4")

    def test_unknown_mime_falls_back_by_kind(self):
        self.assertEqual(_guess_extension(None, "audio"), "ogg")
        self.assertEqual(_guess_extension("weird/type", "video"), "mp4")


class TestNormalizeWaNumber(unittest.TestCase):
    def test_strips_formatting(self):
        self.assertEqual(_normalize_wa_number("+55 (27) 99999-9999"), "5527999999999")

    def test_none_becomes_empty_string(self):
        self.assertEqual(_normalize_wa_number(None), "")


if __name__ == "__main__":
    unittest.main()
