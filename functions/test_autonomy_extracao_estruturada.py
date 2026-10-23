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

    def test_sombra(self):
        m = "Te envio a planilha amanhã"
        r = ex.validar_extracao(m, _s(_i("promessa", "planilha", "Te envio a planilha")))
        self.assertTrue(ex.comparar_sombra(classificar_mensagem(m), r)["concorda"])
        with self.assertRaises(ValueError):
            ex.comparar_sombra("x", r)


if __name__ == "__main__":
    unittest.main()
