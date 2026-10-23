import unittest

from autonomy import extracao_estruturada as ex
from autonomy.commitments import PROMESSA, INTENCAO_VAGA, classificar_mensagem


def _s(*itens):
    return {"compromissos": list(itens)}


def _i(classe, objeto, evidencia):
    return {"classe": classe, "objeto": objeto, "evidencia": evidencia}


class ExtracaoEstruturadaTest(unittest.TestCase):
    def test_promessa_firme_com_evidencia_literal(self):
        r = ex.validar_extracao("Te envio a planilha amanhã", _s(_i("promessa", "planilha", "Te envio a planilha")))
        self.assertEqual((r[0].classe, r[0].incerta), (PROMESSA, False))

    def test_intencao_vaga_nao_vira_certeza(self):
        r = ex.validar_extracao("Vou tentar mandar a planilha", _s(_i("promessa", "planilha", "mandar a planilha")))
        self.assertEqual((r[0].classe, r[0].incerta), (INTENCAO_VAGA, True))

    def test_evidencia_inventada_recusada(self):
        with self.assertRaises(ValueError):
            ex.validar_extracao("Bom dia", _s(_i("promessa", "x", "te envio o relatório")))

    def test_saida_malformada(self):
        for ruim in (None, [], {}, {"compromissos": "x"}, _s(5), _s(_i("xx", "a", "Bom")), _s(_i("promessa", "", "Bom"))):
            with self.assertRaises(ValueError):
                ex.validar_extracao("Bom dia", ruim)

    def test_limite_e_duplicata(self):
        m = "Envio a planilha e o relatório"
        r = ex.validar_extracao(m, _s(_i("promessa", "planilha", "Envio a planilha"), _i("promessa", "Planilha", "Envio a planilha")))
        self.assertEqual(len(r), 1)
        with self.assertRaises(ValueError):
            ex.validar_extracao(m, _s(*[_i("promessa", f"o{n}", "Envio") for n in range(6)]))

    def test_evidencia_so_invisivel_e_promessa_sem_base(self):
        for ev in ("\u200b", "\u0301"):
            with self.assertRaises(ValueError):
                ex.validar_extracao("Bom dia", _s(_i("promessa", "x", ev)))
        r = ex.validar_extracao("ok obrigado", _s(_i("promessa", "ok", "ok")))
        self.assertTrue(r[0].incerta)

    def test_sombra_entradas_invalidas(self):
        b = classificar_mensagem("Te envio a planilha amanhã")
        for ruim in (None, 5, "abc", iter([]), [{"classe": "promessa"}],
                     [ex.CompromissoExtraido("promessa", "a", "b", 0)],
                     [ex.CompromissoExtraido(1, "a", "b", False)]):
            with self.assertRaises(ValueError):
                ex.comparar_sombra(b, ruim)

    def test_invisiveis_e_cautela_em_toda_classe(self):
        for ev in ("\u3164", ".", "\x00", "a"):
            with self.assertRaises(ValueError):
                ex.validar_extracao("Te envio o relatório " + ev, _s(_i("promessa", "relatório", ev)))
        r = ex.validar_extracao("Posso te mandar amanhã?", _s(_i("entrega_parcial", "envio", "te mandar")))
        self.assertEqual((r[0].classe, r[0].incerta), ("pergunta", True))
        from autonomy.commitments import Classificacao
        for ruim in (Classificacao("zzz", "", False), Classificacao(PROMESSA, "", None)):
            with self.assertRaises(ValueError):
                ex.comparar_sombra(ruim, ())

    def test_rodada3_preenchedor_e_incerteza_da_base(self):
        with self.assertRaises(ValueError):
            ex.validar_extracao("\u3164\u3164 te envio o relatorio", _s(_i("promessa", "\u3164\u3164", "\u3164\u3164")))
        with self.assertRaises(ValueError):
            ex.validar_extracao("te envio o relatorio", _s(_i("promessa", "\u00b2\u00b2", "re")))
        m = "Quem sabe te envio o relatorio"
        base = classificar_mensagem(m)
        r = ex.validar_extracao(m, _s(_i(base.classe, "relatorio", "te envio")))
        self.assertEqual((r[0].classe, r[0].incerta), (base.classe, base.incerta))

    def test_hangul_uma_silaba_nao_conta_como_dois(self):
        with self.assertRaises(ValueError):
            ex.validar_extracao("te envio \uac00", _s(_i("promessa", "\uac01", "\uac00")))

    def test_incerteza_herdada_em_qualquer_classe_coincidente(self):
        m = "Já enviei a primeira parte, falta o resto"
        base = classificar_mensagem(m)
        r = ex.validar_extracao(m, _s(_i(base.classe, "relatorio", "primeira parte")))
        self.assertEqual((r[0].classe, r[0].incerta), (base.classe, base.incerta))

    def test_divergencia_da_base_e_sempre_incerta(self):
        for m, cls, ev in (("Te envio o relatório amanhã ontem", "entrega_parcial", "te envio"),
                           ("Segue a primeira parte, o resto te mando amanhã", "nao_relacionada", "primeira parte")):
            r = ex.validar_extracao(m, _s(_i(cls, "relatorio", ev)))
            self.assertTrue(r[0].incerta, m)

    def test_clausulas_independentes_nao_se_contaminam(self):
        m = "Não vou enviar o relatório. Te envio a planilha amanhã."
        r = ex.validar_extracao(m, _s(_i("cancelamento", "relatorio", "Não vou enviar o relatório"),
                                      _i("promessa", "planilha", "Te envio a planilha amanhã")))
        self.assertEqual([(e.classe, e.objeto) for e in r], [("cancelamento", "relatorio"), ("promessa", "planilha")])
        self.assertFalse(r[1].incerta)

    def test_ressalva_orfa_na_frase_vizinha_mantem_cautela(self):
        for m in ("Vou te enviar o relatório amanhã. Mas só se der.", "Vou te enviar o relatório amanhã. Cancela, desisti."):
            r = ex.validar_extracao(m, _s(_i("promessa", "relatorio", "Vou te enviar o relatório amanhã")))
            self.assertTrue(r[0].incerta, m)
            self.assertNotEqual((r[0].classe, r[0].incerta), (PROMESSA, False))

    def test_item_espurio_de_evidencia_curta_nao_libera_ressalva_orfa(self):
        m = "Vou te enviar o relatório amanhã. Mas só se der."
        for ev, obj in (("se", "ab"), ("só", "ab"), ("Mas só se der.", "ab")):
            r = ex.validar_extracao(m, _s(_i("promessa", "relatorio", "Vou te enviar o relatório amanhã."),
                                          _i("promessa", obj, ev)))
            self.assertTrue(r[0].incerta, ev)

    def test_duplicata_incerta_contamina_independente_da_ordem(self):
        m = "Te envio a planilha amanhã. A planilha do mês passado tem erro."
        a = _i("promessa", "planilha", "Te envio a planilha amanhã")
        b = _i("promessa", "planilha", "A planilha do mês passado tem erro")
        for ordem in ((a, b), (b, a)):
            r = ex.validar_extracao(m, _s(*ordem))
            self.assertEqual(len(r), 1)
            self.assertTrue(r[0].incerta)

    def test_gatilho_da_ressalva_deve_estar_na_evidencia_do_outro_item(self):
        m = "Te envio a planilha amanhã. Só se der, e o relatório também."
        r = ex.validar_extracao(m, _s(_i("promessa", "planilha", "Te envio a planilha amanhã"),
                                      _i("promessa", "relatório", "e o relatório também")))
        self.assertTrue(r[0].incerta)

    def test_mensagem_grande_demais(self):
        with self.assertRaises(ValueError):
            ex.validar_extracao("a. " * 5000, _s(_i("promessa", "ab", "a.")))

    def test_negacao_nao_reconhecida_e_pergunta_independente(self):
        for m in ("Te envio o relatório amanhã. Não vou conseguir.", "Te envio o relatório amanhã. Não."):
            r = ex.validar_extracao(m, _s(_i("promessa", "relatorio", "Te envio o relatório amanhã")))
            self.assertTrue(r[0].incerta, m)
        m = "Você pode enviar o relatório? Te envio a planilha amanhã."
        r = ex.validar_extracao(m, _s(_i("pergunta", "relatorio", "Você pode enviar o relatório"),
                                      _i("promessa", "planilha", "Te envio a planilha amanhã")))
        self.assertEqual((r[1].classe, r[1].incerta), ("promessa", False))

    def test_rodada12_vizinha_nao_libera_mesmo_objeto_nem_duvida_residual(self):
        casos = (
            ("Te envio a planilha amanhã. Não vou enviar a planilha.", "Te envio a planilha amanhã", "planilha",
             ("cancelamento", "planilha", "Não vou enviar a planilha")),
            ("Te envio a planilha amanhã. Preciso do arquivo. Te envio o relatório se der.", "Te envio a planilha amanhã", "planilha",
             ("promessa", "relatório", "Te envio o relatório se der")),
        )
        for m, ev, obj, outro in casos:
            r = ex.validar_extracao(m, _s(_i("promessa", obj, ev), _i(outro[0], outro[1], outro[2])))
            self.assertTrue(r[0].incerta, m)

    def test_rodada13_anafora_nao_libera(self):
        for m, outro in (("Te envio o relatório amanhã. Esquece isso.", ("cancelamento", "isso", "Esquece isso")),
                         ("Te envio o relatório amanhã. Não vou mais enviar.", ("cancelamento", "enviar", "Não vou mais enviar")),
                         ("Te envio o relatório amanhã. Mas não sei se vou conseguir.", ("intencao_vaga", "conseguir", "Mas não sei se vou conseguir"))):
            r = ex.validar_extracao(m, _s(_i("promessa", "relatorio", "Te envio o relatório amanhã"), _i(*outro)))
            self.assertTrue(r[0].incerta, m)

    def test_rodada14_mesmo_entregavel_em_outra_flexao(self):
        for m, obj in (("Te envio o relatório amanhã. Não vou mais enviar o relatório.", "relatórios"),
                       ("Te envio o relatório amanhã. Não vou mais enviar o relatório.", "relatório mensal"),
                       ("Te envio os relatórios amanhã. Não vou mais enviar o relatório.", "relatórios")):
            ev = "Te envio os relatórios amanhã" if "os relat" in m else "Te envio o relatório amanhã"
            r = ex.validar_extracao(m, _s(_i("promessa", obj, ev),
                                          _i("cancelamento", "relatório", "Não vou mais enviar o relatório")))
            self.assertTrue(r[0].incerta, (m, obj))

    def test_rodada15_plural_oes(self):
        m = "Vou enviar a versão amanhã. Não vou enviar a planilha nem as versões."
        r = ex.validar_extracao(m, _s(_i("promessa", "versão", "Vou enviar a versão amanhã"),
                                      _i("cancelamento", "planilha", "Não vou enviar a planilha nem as versões")))
        self.assertTrue(r[0].incerta)

    def test_sombra(self):
        m = "Te envio a planilha amanhã"
        r = ex.validar_extracao(m, _s(_i("promessa", "planilha", "Te envio a planilha")))
        self.assertTrue(ex.comparar_sombra(classificar_mensagem(m), r)["concorda"])
        with self.assertRaises(ValueError):
            ex.comparar_sombra("x", r)


if __name__ == "__main__":
    unittest.main()
