import unittest

from autonomy import compromissos_chat as cc


class CompromissosChatTest(unittest.TestCase):
    def _dois(self):
        r = cc.abrir((), "c1", "m1", 0, "envio o relatório")
        return cc.abrir(r, "c1", "m2", 0, "envio a planilha")

    def test_duas_promessas_permanecem_independentes(self):
        r = self._dois()
        self.assertEqual(len(cc.ativos(r, "c1")), 2)

    def test_mesmo_texto_em_mensagens_diferentes_nao_colide(self):
        r = cc.abrir((), "c1", "m1", 0, "envio")
        r = cc.abrir(r, "c1", "m1", 1, "envio")
        self.assertEqual(len(cc.ativos(r, "c1")), 2)

    def test_chave_repetida_recusada(self):
        with self.assertRaises(ValueError):
            cc.abrir(self._dois(), "c1", "m1", 0, "outra coisa")

    def test_texto_vazio_recusado(self):
        with self.assertRaises(ValueError):
            cc.abrir((), "c1", "m1", 0, "  ")

    def test_substituir_so_afeta_o_antigo(self):
        r = cc.abrir(self._dois(), "c1", "m3", 0, "envio o relatório revisado")
        r = cc.substituir(r, "c1__m1__0", "c1__m3__0")
        chaves = {c.chave for c in cc.ativos(r, "c1")}
        self.assertEqual(chaves, {"c1__m2__0", "c1__m3__0"})
        antigo = [c for c in r if c.chave == "c1__m1__0"][0]
        self.assertEqual(antigo.substituido_por, "c1__m3__0")

    def test_substituir_nao_atravessa_chats(self):
        r = cc.abrir(self._dois(), "c2", "m9", 0, "envio")
        with self.assertRaises(ValueError):
            cc.substituir(r, "c1__m1__0", "c2__m9__0")

    def test_substituir_si_mesmo_inexistente_e_ja_substituido(self):
        r = cc.abrir(self._dois(), "c1", "m3", 0, "novo")
        with self.assertRaises(ValueError):
            cc.substituir(r, "c1__m1__0", "c1__m1__0")
        with self.assertRaises(ValueError):
            cc.substituir(r, "c1__m1__0", "c1__zz__0")
        r2 = cc.substituir(r, "c1__m1__0", "c1__m3__0")
        with self.assertRaises(ValueError):
            cc.substituir(r2, "c1__m1__0", "c1__m2__0")
        with self.assertRaises(ValueError):
            cc.substituir(r2, "c1__m2__0", "c1__m1__0")  # novo já substituído

    def test_ciclo_impossivel(self):
        r = cc.substituir(self._dois(), "c1__m1__0", "c1__m2__0")
        with self.assertRaises(ValueError):
            cc.substituir(r, "c1__m2__0", "c1__m1__0")

    def test_registro_malformado(self):
        with self.assertRaises(ValueError):
            cc.ativos([1], "c1")
        with self.assertRaises(ValueError):
            cc.abrir(None, "c1", "m1", 0, "x")

    def test_registro_incoerente_recusado(self):
        C = cc.Compromisso
        with self.assertRaises(ValueError):
            cc.ativos((C("a", "c1", "x"),), "c1")  # chave sem prefixo do chat
        with self.assertRaises(ValueError):
            cc.ativos((C("c1__m1__0", "c1", "x"), C("c1__m1__0", "c1", "y")), "c1")
        with self.assertRaises(ValueError):
            C("c1__a__0", "c1", "x", "qualquer")
        with self.assertRaises(ValueError):
            C("c1__a__0", "c1", "x", cc.SUBSTITUIDO, "c1__a__0")
        with self.assertRaises(ValueError):
            C("c1__a__0", "c1", "x", cc.ABERTO, "c1__b__0")
        with self.assertRaises(ValueError):
            cc.ativos((C("c1__a__0", "c1", "x", cc.SUBSTITUIDO, "c1__z__0"),), "c1")
        with self.assertRaises(ValueError):
            C("c1__a__0", "c1", "\u200b")

    def test_ciclo_em_registro_construido_a_mao(self):
        C, S = cc.Compromisso, cc.SUBSTITUIDO
        r = (C("c1__a__0", "c1", "x", S, "c1__b__0"), C("c1__b__0", "c1", "y", S, "c1__a__0"))
        with self.assertRaises(ValueError):
            cc.ativos(r, "c1")
        r3 = (
            C("c1__a__0", "c1", "x", S, "c1__b__0"),
            C("c1__b__0", "c1", "y", S, "c1__c__0"),
            C("c1__c__0", "c1", "z", S, "c1__a__0"),
        )
        with self.assertRaises(ValueError):
            cc.ativos(r3, "c1")

    def test_chave_exata_e_str_exata(self):
        C = cc.Compromisso
        for chave, chat in (("c1__", "c1"), ("__a", ""), ("a__b__m__0", "a"), ("c1__m__x", "c1"), ("c1__m__-1", "c1")):
            with self.assertRaises(ValueError):
                C(chave, chat, "x")

        class Sx(str):
            pass
        with self.assertRaises(ValueError):
            C(Sx("c1__a__0"), "c1", "x")
        self.assertEqual(C("c1__a__0", "c1", " x ").texto, "x")

    def test_tipos_estritos(self):
        class T(tuple):
            pass
        with self.assertRaises(ValueError):
            cc.abrir(T(), "c1", "m1", 0, "x")
        with self.assertRaises(ValueError):
            cc.abrir((), "c1", "m1", 0, None)
        with self.assertRaises(ValueError):
            cc.ativos((), 5)
        with self.assertRaises(ValueError):
            cc.substituir(self._dois(), None, "c1__m2__0")
        with self.assertRaises(ValueError):
            cc.substituir([], "a", "b")

    def test_texto_normalizado_e_cadeia(self):
        r = cc.abrir((), "c1", "m1", 0, " x ")
        self.assertEqual(r[0].texto, "x")
        r = cc.abrir(r, "c1", "m2", 0, "y")
        r = cc.abrir(r, "c1", "m3", 0, "z")
        r = cc.substituir(r, "c1__m1__0", "c1__m2__0")
        r = cc.substituir(r, "c1__m2__0", "c1__m3__0")
        self.assertEqual([c.chave for c in cc.ativos(r, "c1")], ["c1__m3__0"])

    def test_isolamento_entre_chats_em_ativos(self):
        r = cc.abrir(self._dois(), "c2", "m1", 0, "w")
        self.assertEqual(len(cc.ativos(r, "c2")), 1)
        self.assertEqual(len(cc.ativos(r, "c1")), 2)

    def test_imutavel(self):
        r = self._dois()
        antes = tuple(r)
        cc.substituir(r, "c1__m1__0", "c1__m2__0")
        self.assertEqual(r, antes)
        with self.assertRaises(Exception):
            r[0].estado = cc.SUBSTITUIDO


if __name__ == "__main__":
    unittest.main()
