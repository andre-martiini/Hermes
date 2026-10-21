import unittest
from datetime import date

from autonomy import commitments as c


class ClassificarTest(unittest.TestCase):
    def test_corpus_sintetico_sem_erros(self):
        r = c.avaliar()
        self.assertEqual(r["erros"], [])
        self.assertEqual(r["por_classe"][c.PROMESSA]["precisao"], 1.0)

    def test_promessa_com_confirmacao_nunca_firme(self):
        r = c.classificar_mensagem("Vou te enviar hoje, pode ser?")
        self.assertIn(r.classe, (c.PERGUNTA, c.INTENCAO_VAGA))
        self.assertTrue(r.incerta)

    def test_pode_deixar_fora_de_contexto(self):
        for t in ("Pode deixar em branco", "Pode deixar de lado"):
            self.assertNotEqual(c.classificar_mensagem(t).classe, c.PROMESSA)
        self.assertEqual(c.classificar_mensagem("Pode deixar que eu envio").classe, c.PROMESSA)

    def test_nenhum_adversarial_vira_promessa_firme(self):
        for t, esperado in c.CASOS_SINTETICOS:
            if esperado != c.PROMESSA:
                r = c.classificar_mensagem(t)
                self.assertFalse(r.classe == c.PROMESSA and not r.incerta, t)

    def test_hedges_nao_sao_firmes(self):
        for t in ("Te mando amanhã, se possível", "Te envio amanhã desde que aprovem",
                  "Vou te mandar amanhã, depende do chefe", "Te envio amanhã, se Deus quiser",
                  "Provavelmente te envio amanhã", "Será que te envio amanhã",
                  "Te envio quando você me mandar", "Te mando amanhã ou depois",
                  "Te envio dia 30/02", "Se eu não enviar até amanhã, me cobra"):
            r = c.classificar_mensagem(t, date(2026, 10, 21))
            self.assertFalse(r.classe == c.PROMESSA and not r.incerta, t)

    def test_promessas_obvias_continuam_firmes(self):
        for t in ("Como combinado, te envio amanhã",
                  "Te envio amanhã",
                  "Pode deixar que eu envio", "Vou te mandar hoje"):
            r = c.classificar_mensagem(t)
            self.assertEqual((r.classe, r.incerta), (c.PROMESSA, False), t)

    def test_hoje_invalido_nao_lanca(self):
        for h in ("2026-10-21", 5, None, object()):
            self.assertEqual(c.classificar_mensagem("Te envio amanhã", h).classe, c.PROMESSA)
            self.assertIsNone(c.extrair_prazo_expresso("amanhã", h).data)

    def test_hedges_rodada3(self):
        for t in ("Te envio amanhã se o chefe aprovar", "Te mando assim que aprovarem",
                  "Te envio quando o Joao liberar", "Te mando amanhã, exceto se travar",
                  "Vou te mandar amanhã, eu acho", "Te envio amanhã, imagino",
                  "Te envio amanhã kkk", "Te mando amanhã ou na segunda",
                  "Pode deixar que o João te manda", "Ela disse que te envio amanhã",
                  "Te aviso", "Te mando um abraço", "Te passo o contato do João",
                  "Vou te mandar o que sobrou", "Pode deixar, ele envia"):
            r = c.classificar_mensagem(t, date(2026, 10, 21))
            self.assertFalse(r.classe == c.PROMESSA and not r.incerta, t)

    def test_hedges_rodada4(self):
        h = date(2026, 10, 21)
        for t in ("N vou te enviar hoje", "Ñ vou te mandar hoje", "Num vou te enviar hoje",
                  "N te envio hoje", "Envio em anexo a planilha", "Te envio em anexo o documento",
                  "Eu passo em casa depois", "Vou passar no mercado", "Vou passar mal amanhã",
                  "Vou mandar bem na prova", "Vou retornar pra casa amanhã", "Vou responder que sim",
                  "Te falo a verdade, o filme é ótimo", "Te mando o meu carinho",
                  "Pode deixar, a Maria resolve", "Deixa comigo, o Pedro resolve", "Pode deixar.",
                  "Te mando amanhã, acho", "Te envio amanhã, a princípio", "Te envio amanhã, possivelmente",
                  "Faço o possível, te envio amanhã", "Te envio amanhã, sujeito a aprovação",
                  "Te envio amanhã, pode ser", "Falei que vou te enviar amanhã"):
            r = c.classificar_mensagem(t, h)
            self.assertFalse(r.classe == c.PROMESSA and not r.incerta, t)

    def test_prazo_relativo_ou_multiplo_sem_data(self):
        h = date(2026, 10, 21)
        for t in ("Te envio na sexta da próxima semana", "Te envio até sexta da semana que vem",
                  "Vou te enviar o relatório para a reunião de amanhã", "Vou te enviar o balanço de hoje",
                  "Te envio o A hoje e o B na sexta"):
            self.assertIsNone(c.extrair_prazo_expresso(t, h).data, t)

    def test_firmeza_por_lista_branca(self):
        h = date(2026, 10, 21)
        for t in ("Aguardando o João, te envio amanhã", "Te envio amanhã, sem certeza",
                  "Te envio amanhã, estou sem internet", "Te envio amanhã rs",
                  "Te envio amanhã, pendente de aprovação", "Te envio amanhã, pode atrasar",
                  "Acredito que te envio amanhã", "Te envio o relatório ontem",
                  "Te envio hoje, 80% de chance", "Te envio amanhã, tô sem o arquivo"):
            r = c.classificar_mensagem(t, h)
            self.assertFalse(r.classe == c.PROMESSA and not r.incerta, t)
        for t in ("Te envio o relatório amanhã", "Vou te mandar a planilha ainda hoje",
                  "Pode deixar que eu envio", "Vou te mandar hoje", "Te envio amanhã, obrigado"):
            r = c.classificar_mensagem(t, h)
            self.assertEqual((r.classe, r.incerta), (c.PROMESSA, False), t)

    def test_prazo_nao_vira_data_do_objeto(self):
        h = date(2026, 10, 21)
        self.assertIsNone(c.extrair_prazo_expresso("Te envio o relatório do dia 25/10", h))
        self.assertIsNone(c.extrair_prazo_expresso("Te envio a ata na quarta", h))
        self.assertIsNone(c.extrair_prazo_expresso("Te envio hoje 22/10", h).data)
        self.assertEqual(c.extrair_prazo_expresso("Te envio até 25/10", h).data, date(2026, 10, 25))

    def test_rodada6_ruido_e_dia_n(self):
        h = date(2026, 10, 21)
        for t in ("Te envio hoje?!", "Te envio hoje 🙄", "Te envio amanhã 😂", "Te envio hoje？"):
            r = c.classificar_mensagem(t, h)
            self.assertFalse(r.classe == c.PROMESSA and not r.incerta, t)
        for t in ("Te envio hoje dia 22", "Te envio amanhã dia 23"):
            self.assertIsNone(c.extrair_prazo_expresso(t, h).data, t)

    def test_codex_pr480(self):
        h = date(2026, 10, 21)
        self.assertEqual(c.extrair_prazo_expresso("entrego na sexta", h).data, date(2026, 10, 23))
        for t in ("Não te envio hoje?", "Não posso te mandar amanhã?"):
            r = c.classificar_mensagem(t, h)
            self.assertEqual((r.classe, r.incerta), (c.PERGUNTA, True), t)
        for t in ("Te envio uma planilha amanhã", "Vou te mandar um relatório hoje"):
            r = c.classificar_mensagem(t, h)
            self.assertEqual(r.classe, c.PROMESSA, t)
        for t in ("Te mando um abraço", "Te mando um beijo", "Vou te mandar um oi",
                  "Te aviso um dia desses", "Te respondo um momento"):
            r = c.classificar_mensagem(t)
            self.assertFalse(r.classe == c.PROMESSA and not r.incerta, t)

    def test_texto_grande(self):
        r = c.classificar_mensagem("a " * 500000)
        self.assertEqual(r.classe, c.NAO_RELACIONADA)

    def test_invisiveis(self):
        for ch in ("\u00ad", "\ufeff", "\u200b"):
            self.assertEqual(c.classificar_mensagem(f"te en{ch}vio amanhã").classe, c.PROMESSA)

    def test_vaga_vence_promessa(self):
        r = c.classificar_mensagem("Vou tentar te enviar amanhã")
        self.assertEqual(r.classe, c.INTENCAO_VAGA)
        self.assertTrue(r.incerta)

    def test_negacao_vence_promessa(self):
        self.assertEqual(c.classificar_mensagem("Não vou te enviar mais").classe, c.CANCELAMENTO)

    def test_pergunta_com_promessa_continua_pergunta(self):
        self.assertEqual(c.classificar_mensagem("Posso te mandar amanhã?").classe, c.PERGUNTA)

    def test_mensagem_longa_nao_relacionada_nao_e_promessa_nem_cumprimento(self):
        r = c.classificar_mensagem("Ontem foi um dia longo, almocei com o pessoal e voltei tarde")
        self.assertEqual(r.classe, c.NAO_RELACIONADA)

    def test_entradas_invalidas(self):
        for v in (None, 3, "", "   ", b"x", ["a"]):
            self.assertEqual(c.classificar_mensagem(v).classe, c.NAO_RELACIONADA)

    def test_acento_e_caixa(self):
        self.assertEqual(c.classificar_mensagem("TE ENVIO AMANHÃ").classe, c.PROMESSA)

    def test_caractere_invisivel(self):
        self.assertEqual(c.classificar_mensagem("te en​vio amanhã").classe, c.PROMESSA)


class PrazoTest(unittest.TestCase):
    hoje = date(2026, 10, 21)  # quarta

    def test_amanha(self):
        p = c.extrair_prazo_expresso("te envio amanhã", self.hoje)
        self.assertEqual((p.natureza, p.data), (c.PRAZO_EXPRESSO, date(2026, 10, 22)))

    def test_hoje_e_depois_de_amanha(self):
        self.assertEqual(c.extrair_prazo_expresso("ainda hoje", self.hoje).data, self.hoje)
        self.assertEqual(c.extrair_prazo_expresso("depois de amanhã", self.hoje).data, date(2026, 10, 23))

    def test_ate_sexta(self):
        self.assertEqual(c.extrair_prazo_expresso("até sexta", self.hoje).data, date(2026, 10, 23))

    def test_mesmo_dia_da_semana_vai_para_proxima(self):
        self.assertEqual(c.extrair_prazo_expresso("até quarta", self.hoje).data, date(2026, 10, 28))

    def test_dd_mm_passado_vira_ano_seguinte_e_invalido_ignora(self):
        self.assertIsNone(c.extrair_prazo_expresso("dia 5/3", self.hoje))
        self.assertIsNone(c.extrair_prazo_expresso("até 5/6/126", self.hoje))
        self.assertEqual(c.extrair_prazo_expresso("dia 5/12", self.hoje).data, date(2026, 12, 5))
        self.assertIsNone(c.extrair_prazo_expresso("dia 31/02", self.hoje))

    def test_data_so_com_contexto_e_com_ano(self):
        self.assertIsNone(c.extrair_prazo_expresso("versão 1/2 do doc", self.hoje))
        self.assertIsNone(c.extrair_prazo_expresso("1/2 hora", self.hoje))
        self.assertEqual(c.extrair_prazo_expresso("dia 10/10/2026", date(2026, 10, 1)).data, date(2026, 10, 10))

    def test_29_fev(self):
        self.assertIsNone(c.extrair_prazo_expresso("dia 29/02", date(2027, 2, 28)))
        self.assertEqual(c.extrair_prazo_expresso("dia 29/02", date(2028, 2, 1)).data, date(2028, 2, 29))

    def test_overflow_e_negacao_e_horas(self):
        self.assertIsNone(c.extrair_prazo_expresso("amanhã", date.max))
        self.assertIsNone(c.extrair_prazo_expresso("hoje não, amanhã", self.hoje))
        self.assertIsNone(c.extrair_prazo_expresso("às 25h", self.hoje))
        self.assertIsNone(c.extrair_prazo_expresso("antes de amanhã", self.hoje).data)

    def test_sem_hoje_sem_data(self):
        p = c.extrair_prazo_expresso("amanhã")
        self.assertIsNotNone(p)
        self.assertIsNone(p.data)

    def test_sem_prazo(self):
        self.assertIsNone(c.extrair_prazo_expresso("em breve"))
        self.assertIsNone(c.extrair_prazo_expresso(None))


class ChaveTest(unittest.TestCase):
    def test_chave(self):
        self.assertEqual(c.chave_compromisso("c1", "m1", 1), "c1__m1__1")

    def test_invalidos(self):
        for args in (("a ", "b"), ("a\n", "b"), ("a_", "b"), ("a", "_b"), ("a", "b__c"), ("a__b", "c"), ("c", "m", True), (1, 2), ("", "m"), ("c", ""), ("c", "m", -1), ("c", "m", "0"), (None, "m")):
            with self.assertRaises(ValueError):
                c.chave_compromisso(*args)


if __name__ == "__main__":
    unittest.main()
