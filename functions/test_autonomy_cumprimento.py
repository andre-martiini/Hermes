import unittest

from autonomy.cumprimento import (
    CUMPRIDO, INCERTO, NAO_CUMPRE, PARCIAL, avaliar_cumprimento,
)


def fecha(r):
    return r.estado == CUMPRIDO and not r.incerta


class AvaliarCumprimentoTest(unittest.TestCase):
    P = "Te envio o relatório amanhã"

    def test_entrega_com_objeto_cumpre(self):
        for m in ("Segue o relatório", "Enviei o relatório em anexo", "segue em anexo o relatório!"):
            self.assertTrue(fecha(avaliar_cumprimento(self.P, m)), m)

    def test_anexo_com_nome_casando_cumpre(self):
        self.assertFalse(fecha(avaliar_cumprimento(self.P, "Segue", True, "Relatorio_final.pdf")))
        self.assertFalse(fecha(avaliar_cumprimento(self.P, "Segue o relatório", True, "Relatorio_final.pdf")))
        self.assertTrue(fecha(avaliar_cumprimento(self.P, "Segue o relatório", True, "Relatorio.pdf")))

    def test_midia_sozinha_nao_fecha(self):
        r = avaliar_cumprimento(self.P, "", True)
        self.assertFalse(fecha(r))
        self.assertEqual(r.estado, INCERTO)
        self.assertFalse(fecha(avaliar_cumprimento(self.P, "Segue", True, "IMG_2231.jpg")))

    def test_mensagem_longa_sobre_almoco_nao_encerra(self):
        m = "Fui almoçar com o pessoal ontem e o restaurante estava ótimo, depois conto como foi a reunião toda"
        r = avaliar_cumprimento(self.P, m)
        self.assertEqual(r.estado, NAO_CUMPRE)
        self.assertFalse(fecha(r))

    def test_negacao_vence_entrega(self):
        for m in ("Ainda não enviei o relatório", "não consegui mandar o relatório"):
            self.assertFalse(fecha(avaliar_cumprimento(self.P, m)), m)

    def test_objeto_diferente_nao_fecha(self):
        r = avaliar_cumprimento(self.P, "Segue a planilha")
        self.assertEqual(r.estado, INCERTO)

    def test_parcial(self):
        r = avaliar_cumprimento(self.P, "Segue a primeira parte do relatório")
        self.assertEqual(r.estado, PARCIAL)
        self.assertFalse(fecha(r))

    def test_hedge_pergunta_e_futuro_nao_fecham(self):
        for m in ("Acho que enviei o relatório", "Segue o relatório, chegou?",
                  "Te mando o relatório hoje à noite", "Tentei enviar o relatório"):
            self.assertFalse(fecha(avaliar_cumprimento(self.P, m)), m)

    def test_nova_promessa_nao_cumpre(self):
        self.assertEqual(avaliar_cumprimento(self.P, "Te envio o relatório hoje").estado, NAO_CUMPRE)

    def test_promessa_sem_objeto_nao_fecha(self):
        self.assertFalse(fecha(avaliar_cumprimento("Te retorno amanhã", "Enviei")))

    def test_vazio_e_entradas_invalidas(self):
        self.assertEqual(avaliar_cumprimento(self.P, "").estado, NAO_CUMPRE)
        self.assertFalse(fecha(avaliar_cumprimento(None, None)))
        self.assertFalse(fecha(avaliar_cumprimento(123, 456)))

    def test_achados_da_revisao_adversarial_nao_fecham(self):
        P = "Vou te enviar a planilha amanhã"
        for m in (
            "segue a planilha, falta anexar o resto", "segue a planilha, parcial",
            "segue a planilha só da primeira parte", "segue a planilha, o restante amanhã",
            "segue a primeira planilha", "segue a planilha 1 de 3",
            "segue a planilha em branco", "segue a planilha errada",
            "segue a planilha rascunho", "segue a planilha (versão preliminar)",
            "mandei a planilha errada, segue a certa", "enviei a planilha para o chefe",
            "segue a planilha do João", "segue a planilha do mês passado",
            "enviei a planilha ontem", "segue a planilha. Já já te ligo",
            "segue o link da planilha", "segue o print da planilha",
        ):
            self.assertFalse(fecha(avaliar_cumprimento(P, m)), m)

    def test_dois_objetos_exigem_cobertura_total(self):
        P = "Vou mandar o contrato e a planilha amanhã"
        self.assertFalse(fecha(avaliar_cumprimento(P, "segue a planilha")))
        self.assertTrue(fecha(avaliar_cumprimento(P, "segue o contrato e a planilha")))

    def test_midia_so_fecha_com_nome_conferindo(self):
        P = "Vou mandar a planilha"
        self.assertFalse(fecha(avaliar_cumprimento(P, "segue a planilha", True, "foto.jpg")))
        self.assertFalse(fecha(avaliar_cumprimento(P, "", True, "planilha.xlsx")))
        self.assertFalse(fecha(avaliar_cumprimento(P, "segue a planilha", True, "")))
        self.assertTrue(fecha(avaliar_cumprimento(P, "segue a planilha", True, "planilha.xlsx")))

    def test_rodada2_anexo_formula_truncada_e_promessa_qualificada(self):
        P = "Vou te enviar o relatório amanhã"
        for nome in ("relatorio_errado.pdf", "rascunho_relatorio.pdf", "relatorio 2019.pdf",
                     "relatorio_e_planilha.pdf", "relatorio.pdf.exe"):
            self.assertFalse(fecha(avaliar_cumprimento(P, "segue o relatório", True, nome)), nome)
        for m in ("segue o relatório e", "mandei o relatório e o", "enviei o relatório para",
                  "segue o relatório em", "segue o relatório a o", "segue o relatório esta",
                  "segue o relatório ai"):
            self.assertFalse(fecha(avaliar_cumprimento(P, m)), m)
        for p in ("Vou enviar o relatório 2024", "Vou enviar o relatório final amanhã ao João",
                  "Não vou enviar o relatório", "Cancela, não precisa enviar o relatório",
                  "Vou enviar o relatório de março"):
            self.assertFalse(fecha(avaliar_cumprimento(p, "segue o relatório")), p)
        self.assertTrue(fecha(avaliar_cumprimento(P, "segue o relatório", True, "Relatorio.pdf")))

    def test_rodada3_promessa_lista_branca_e_texto_nao_latino(self):
        for p in ("Te mando o relatório e a nota fiscal", "Te mando o relatório e o boleto",
                  "Te mando os 3 relatórios", "Te mando os relatórios", "Te mando o relatório mensal",
                  "Te mando o novo relatório", "Te mando o relatório amanhã depois que o João aprovar",
                  "Te mando o relatório sem a planilha", "Te mando o relatório ou a planilha",
                  "Te mando o relatório em vez da planilha"):
            self.assertFalse(fecha(avaliar_cumprimento(p, "segue o relatório e a planilha")), p)
            self.assertFalse(fecha(avaliar_cumprimento(p, "segue o relatório")), p)
        P = "Te mando o relatório amanhã"
        for m in ("segue o relatório 请不要", "segue o relatório 😊"):
            self.assertFalse(fecha(avaliar_cumprimento(P, m)), m)
        for nome in ("relatorio relatorio.pdf", "relatorios.pdf"):
            self.assertFalse(fecha(avaliar_cumprimento(P, "segue o relatório", True, nome)), nome)
        self.assertTrue(fecha(avaliar_cumprimento(P, "Segue o relatório.")))

    def test_rodada4_gramatica_fechada(self):
        P = "Te mando o relatório amanhã"
        for p in ("Vou te enviar o relatório e o", "Vou mandar o relatório e a",
                  "Vou entregar o relatório amanhã e"):
            self.assertFalse(fecha(avaliar_cumprimento(p, "segue o relatório")), p)
        for m in ("s̶e̶g̶u̶e̶ o relatório", "segue o relatório̸", "segue o a relatório",
                  "segue ai ai ai o relatório", "segue em o relatório", "segue a o relatório",
                  "segue o relatório - - -", "segue o relatório ( )",
                  "segue o relatório e o relatório"):
            self.assertFalse(fecha(avaliar_cumprimento(P, m)), m)
        self.assertFalse(fecha(avaliar_cumprimento(P, "segue o relatório", True, "relatorio̶.pdf")))
        for m in ("Segue o relatório", "enviei o relatório em anexo", "Segue em anexo o relatório!"):
            self.assertTrue(fecha(avaliar_cumprimento(P, m)), m)


if __name__ == "__main__":
    unittest.main()
