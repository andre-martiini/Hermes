"""Testes de P06 sub-entrega 9/N (passo 7): cursor de contexto assinado."""

import unittest

from autonomy import cursor_contexto as cc

SEG = b"segredo-de-teste"


class TestCursor(unittest.TestCase):
    def test_ida_e_volta(self):
        c = cc.emitir_cursor(SEG, "u1", "global", 1234)
        self.assertEqual(cc.validar_cursor(SEG, c, "u1", "global"), 1234)

    def test_marca_zero_vale(self):
        c = cc.emitir_cursor(SEG, "u1", "global", 0)
        self.assertEqual(cc.validar_cursor(SEG, c, "u1", "global"), 0)

    def test_recusa_outro_dono(self):
        c = cc.emitir_cursor(SEG, "u1", "global", 5)
        with self.assertRaises(cc.CursorInvalido):
            cc.validar_cursor(SEG, c, "u2", "global")

    def test_recusa_outro_escopo(self):
        c = cc.emitir_cursor(SEG, "u1", "missao:a", 5)
        with self.assertRaises(cc.CursorInvalido):
            cc.validar_cursor(SEG, c, "u1", "missao:b")

    def test_recusa_outro_segredo(self):
        c = cc.emitir_cursor(SEG, "u1", "global", 5)
        with self.assertRaises(cc.CursorInvalido):
            cc.validar_cursor(b"outro", c, "u1", "global")

    def test_recusa_adulteracao_do_payload(self):
        v, p, s = cc.emitir_cursor(SEG, "u1", "global", 5).split(".")
        forjado = cc._b64(b'{"e":"global","m":999,"o":"u1"}')
        with self.assertRaises(cc.CursorInvalido):
            cc.validar_cursor(SEG, f"{v}.{forjado}.{s}", "u1", "global")

    def test_recusa_versao_e_formato(self):
        c = cc.emitir_cursor(SEG, "u1", "global", 5)
        for ruim in ["", "x", "v1.a", "v2." + c.split(".", 1)[1], c + ".extra", None, 7, "v1..", "a" * 5000]:
            with self.subTest(ruim=ruim):
                with self.assertRaises(cc.CursorInvalido):
                    cc.validar_cursor(SEG, ruim, "u1", "global")

    def test_marca_invalida_assinada_e_recusada(self):
        for m in ('"5"', "true", "-1", "1.5", "null"):
            with self.subTest(m=m):
                p = cc._b64(('{"e":"g","m":%s,"o":"u"}' % m).encode())
                c = f"v1.{p}.{cc._assina(SEG, p)}"
                with self.assertRaises(cc.CursorInvalido):
                    cc.validar_cursor(SEG, c, "u", "g")

    def test_payload_sem_campos_assinado_e_recusado(self):
        p = cc._b64(b'{"m":1}')
        with self.assertRaises(cc.CursorInvalido):
            cc.validar_cursor(SEG, f"v1.{p}.{cc._assina(SEG, p)}", "u", "g")

    def test_emitir_valida_entradas(self):
        for args in [(SEG, "", "g", 1), (SEG, "u", " ", 1), (SEG, "u", "g", -1), (SEG, "u", "g", True), (SEG, "u", "g", "1"), (None, "u", "g", 1), (b"", "u", "g", 1)]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    cc.emitir_cursor(*args)

    def test_validar_sem_segredo_nao_aceita(self):
        c = cc.emitir_cursor(SEG, "u1", "g", 1)
        with self.assertRaises(ValueError):
            cc.validar_cursor(b"", c, "u1", "g")

    def test_dono_com_ponto_nao_colide(self):
        c = cc.emitir_cursor(SEG, "a.b", "c", 1)
        with self.assertRaises(cc.CursorInvalido):
            cc.validar_cursor(SEG, c, "a", "b.c")
        self.assertEqual(cc.validar_cursor(SEG, c, "a.b", "c"), 1)

    def test_emitir_recusa_cursor_que_nao_validaria(self):
        with self.assertRaises(ValueError):
            cc.emitir_cursor(SEG, "u" * 2000, "g", 1)

    def test_validar_recusa_assinado_acima_do_limite(self):
        p = cc._b64(('{"e":"g","m":1,"o":"%s"}' % ("u" * 2000)).encode())
        c = f"v1.{p}.{cc._assina(SEG, p)}"
        self.assertGreater(len(c), cc._MAX_CURSOR)
        with self.assertRaises(cc.CursorInvalido):
            cc.validar_cursor(SEG, c, "u" * 2000, "g")

    def test_validar_erro_do_chamador_e_value_error_nao_cursor_invalido(self):
        c = cc.emitir_cursor(SEG, "u", "g", 1)
        for o, e in [("", "g"), ("u", ""), (None, "g"), ("u", 3)]:
            with self.subTest(o=o, e=e):
                with self.assertRaises(ValueError) as cm:
                    cc.validar_cursor(SEG, c, o, e)
                self.assertNotIsInstance(cm.exception, cc.CursorInvalido)


if __name__ == "__main__":
    unittest.main()
