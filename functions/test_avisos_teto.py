"""Avisos do teto do PicPay (pedido do André em 30/10/2026), com teto de R$ 5.000."""
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import avisos_teto as at


def _resumo(gasto_reais, orcamento_reais=5000):
    gasto, orc = round(gasto_reais * 100), (None if orcamento_reais is None else orcamento_reais * 100)
    return {"gasto": gasto, "orcamento": orc, "saldo": None if orc is None else orc - gasto}


class Marcos(unittest.TestCase):
    def test_do_maior_para_o_menor(self):
        self.assertEqual(at.marcos_atingidos(_resumo(4100)), [80, 50])
        self.assertEqual(at.marcos_atingidos(_resumo(5000)), [100, 80, 50])
        self.assertEqual(at.marcos_atingidos(_resumo(2499.99)), [])
        self.assertEqual(at.marcos_atingidos(_resumo(9000, None)), [])

    def test_textos(self):
        self.assertEqual(at.texto_marco(80, _resumo(4000), date(2026, 11, 20)),
                         "💳 Você chegou a 80% do teto do PicPay (R$ 4000.00 de R$ 5000.00). "
                         "Restam R$ 1000.00: R$ 90.90 por dia até o fim do mês.")
        self.assertEqual(at.texto_marco(100, _resumo(5200), date(2026, 11, 28)),
                         "🚨 Teto do PicPay estourado: R$ 5200.00 de R$ 5000.00 (R$ 200.00 acima), "
                         "e ainda faltam 2 dias no mês.")


class AvisosDaHora(unittest.TestCase):
    def test_ritmo_so_as_20h_e_so_quando_adiantado(self):
        # Dia 10 de 30 = 33% do mês; 2.500 = 50% do teto: passa dos 38% de folga.
        avisos = at.avisos_da_hora(_resumo(2500), date(2026, 11, 10), 20)
        self.assertEqual(avisos, [("ritmo_10", "⚠️ Você usou 50% do teto do PicPay em 33% do mês. "
                                               "Para fechar no teto: R$ 125.00 por dia nos próximos 20 dias.")])
        self.assertEqual(at.avisos_da_hora(_resumo(2500), date(2026, 11, 10), 19), [])
        self.assertEqual(at.avisos_da_hora(_resumo(1800), date(2026, 11, 10), 20), [])  # 36%: no ritmo

    def test_inicio_e_fim_do_mes(self):
        self.assertEqual(at.avisos_da_hora(_resumo(0), date(2026, 11, 1), 9)[0][0], "inicio")
        self.assertEqual(at.avisos_da_hora(_resumo(4200), date(2026, 11, 30), 20),
                         [("fim", "🐷 Fim do mês: sobraram R$ 800.00 no teto do PicPay. Mande para o cofrinho.")])
        self.assertEqual(at.avisos_da_hora(_resumo(5100), date(2026, 11, 30), 20),
                         [("fim", "Fim do mês: o teto do PicPay estourou em R$ 100.00.")])

    def test_sem_teto_nada(self):
        self.assertEqual(at.avisos_da_hora(_resumo(4000, None), date(2026, 11, 1), 9), [])


class LinhaSemanal(unittest.TestCase):
    def test_semana_e_mes(self):
        tx = [
            {"amount": 100, "date": "2026-11-15", "conta": "picpay"},  # domingo de hoje: entra
            {"amount": 50, "date": "2026-11-09", "conta": "picpay"},   # há 6 dias: entra
            {"amount": 30, "date": "2026-11-08", "conta": "picpay"},   # há 7 dias: só no mês
            {"amount": 999, "date": "2026-11-10", "conta": "xp"},
        ]
        self.assertEqual(at.linha_semanal(tx, {"monthlyBudget": 5000}, date(2026, 11, 15)),
                         "💳 Teto do PicPay: R$ 150.00 na semana, R$ 180.00 de R$ 5000.00 no mês. "
                         "Restam R$ 4820.00 (R$ 301.25 por dia).")
        self.assertIsNone(at.linha_semanal(tx, {}, date(2026, 11, 15)))


class BotaoDoPix(unittest.TestCase):
    def _clicar(self, data, existe=True):
        db = MagicMock()
        ref = db.collection.return_value.document.return_value
        ref.get.return_value.exists = existe
        with patch("telegram_callbacks_custos._edit_message_text") as editar, \
                patch("telegram_utils._answer_callback_query") as responder:
            tratou = at.handle(db, "tok", "q1", 42, data, {"message_id": 7, "text": "Pix de 350"},
                               None, None, None, None, None)
        return tratou, ref, editar, responder

    def test_transferencia_sai_do_teto(self):
        tratou, ref, editar, _ = self._clicar("pixcls:abc123:t")
        self.assertTrue(tratou)
        campos = ref.update.call_args.args[0]
        self.assertEqual((campos["category"], campos["classificado_como"]), ("Transferência", "transferência"))
        self.assertIn("Saiu do teto", editar.call_args.args[3])

    def test_gasto_mantem_a_categoria(self):
        _, ref, _, _ = self._clicar("pixcls:abc123:g")
        self.assertNotIn("category", ref.update.call_args.args[0])

    def test_outros_callbacks_e_botao_invalido(self):
        self.assertFalse(at.handle(MagicMock(), "t", "q", 1, "custos:det:x", {}, None, None, None, None, None))
        tratou, ref, _, responder = self._clicar("pixcls:abc123:z")
        self.assertTrue(tratou)
        ref.update.assert_not_called()
        self.assertEqual(responder.call_args.args[2], "Botão inválido.")


class DiarioSemNotificar(unittest.TestCase):
    def test_notificar_falso_corta_so_o_telegram(self):
        import personal_diary

        doc = MagicMock(exists=True)
        doc.to_dict.return_value = {"personal_diary": {"enabled": True, "notificar": False}}
        with patch("main._cached_doc_get", return_value=doc):
            self.assertEqual(personal_diary._load_settings(MagicMock()), {"enabled": True, "notificar": False})
        doc.to_dict.return_value = {"personal_diary": {"enabled": True}}
        with patch("main._cached_doc_get", return_value=doc):
            self.assertTrue(personal_diary._load_settings(MagicMock())["notificar"])


if __name__ == "__main__":
    unittest.main()
