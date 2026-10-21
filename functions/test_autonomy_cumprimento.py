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
        self.assertTrue(fecha(avaliar_cumprimento(self.P, "Segue o relatório", True, "Relatorio_final.pdf")))

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


if __name__ == "__main__":
    unittest.main()
