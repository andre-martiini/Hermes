"""Teto do PicPay da notificacao de Pix, com o caso de 30/10/2026.

Naquele dia o Telegram mostrou "Saldo disponivel: R$ -6277.11" com teto de
R$ 5.000. A fixture reproduz o que inflava a soma (resgate da reserva,
transferencia, Pix de conta fixa, duplicata, resumo mensal sem conta, gasto pela
XP) e a virada de mes em Brasilia.

A MESMA fixture esta em `src/utils/gastoAvulso.test.ts`: o alerta do app e o
Telegram tem de dar o mesmo numero.
"""
import unittest
from datetime import datetime, timezone

import gasto_avulso as ga

SETTINGS = {"monthlyBudget": 5000, "monthlyBudgets": {"2026-08": 4529.31, "2026-09": 4848.93}}

P = "picpay"
TRANSACOES = [
    {"amount": 503.56, "date": "2026-10-28", "category": "Geral", "status": "active", "conta": P},
    {"amount": 36.99, "date": "2026-10-30T14:17:27+00:00", "category": "Geral", "google_message_id": "m1", "conta": P},
    {"amount": 79.0, "date": "2026-10-30T14:45:18+00:00", "category": "Geral", "google_message_id": "m2", "conta": P},
    {"amount": 79.0, "date": "2026-10-30T14:45:18+00:00", "category": "Geral", "google_message_id": "m2", "conta": P},  # duplicata
    {"amount": 2000, "date": "2026-10-26", "category": "Reserva", "status": "active", "conta": P},  # resgate da reserva
    {"amount": 300, "date": "2026-10-15", "category": "Transferência", "conta": P},  # para o cofrinho
    {"amount": 310, "date": "2026-10-10T12:00:00+00:00", "category": "Conta Fixa", "conta": P},
    {"amount": 999, "date": "2026-10-20", "category": "Geral", "status": "deleted", "conta": P},
    {"amount": 10, "date": "2026-10-31T23:30:00+00:00", "category": "Geral", "conta": P},  # 20:30 de 31/10 em Brasília
    {"amount": 20, "date": "2026-11-01T01:30:00+00:00", "category": "Geral", "conta": P},  # 22:30 de 31/10 em Brasília
    {"amount": 40, "date": "2026-11-01", "category": "Geral", "conta": P},  # novembro
    {"amount": 50, "date": "2026-10-01T02:00:00+00:00", "category": "Geral", "conta": P},  # 23:00 de 30/09 em Brasília
    {"amount": 200, "date": "2026-11-01T00:00:00.000Z", "category": "Geral", "conta": P},  # campo de data do app: dia 1º/11
    {"amount": 150, "date": "2026-10-12", "category": "Investimentos", "conta": P},
    {"amount": 5, "date": "2026-10-30T10:00:00+00:00", "category": "Geral", "pix_id": 7, "conta": P},
    {"amount": 5, "date": "2026-10-30T10:00:00+00:00", "category": "Geral", "pix_id": "7", "conta": P},  # mesmo Pix, outro tipo
    {"amount": 3, "date": "2026-10-29", "category": "Geral", "conta": " PicPay "},
    {"amount": 2450, "date": "2026-10-28", "category": "Geral", "conta": "xp"},  # saiu da XP: fora do teto
    {"amount": 1224.69, "date": "2026-10-28", "category": "Geral"},  # resumo mensal sem conta: fora
    {"amount": 7811.24, "date": "2026-10-28", "category": "Geral", "conta": "mista"},
]

GASTO_OUTUBRO = 65755  # 503,56 + 36,99 + 79,00 + 10,00 + 20,00 + 5,00 + 3,00
HOJE = (2026, 10, 30)  # faltam 2 dias, contando hoje


class GastoDoTeto(unittest.TestCase):
    def test_caso_real_so_picpay_sem_reserva_transferencia_conta_fixa_duplicata_e_deletado(self):
        r = ga.resumo_do_mes(TRANSACOES, SETTINGS, 2026, 10)
        self.assertEqual(r, {"gasto": GASTO_OUTUBRO, "orcamento": 500000, "saldo": 500000 - GASTO_OUTUBRO})

    def test_virada_de_mes_em_brasilia(self):
        self.assertEqual(ga.gasto_avulso_centavos(TRANSACOES, 2026, 11), 24000)
        self.assertEqual(ga.gasto_avulso_centavos(TRANSACOES, 2026, 9), 5000)

    def test_mes_brt(self):
        self.assertEqual(ga.mes_brt("2026-11-01"), (2026, 11))  # só dia: vale o dia escrito, sem fuso
        self.assertEqual(ga.mes_brt("2026-11-01T02:59:00"), (2026, 10))  # hora sem fuso é UTC
        self.assertEqual(ga.mes_brt("2026-10-31T22:00:00-03:00"), (2026, 10))
        self.assertEqual(ga.mes_brt("2026-11-01T00:30:00.123Z"), (2026, 10))
        self.assertEqual(ga.mes_brt("2026-11-01T00:00:00.000Z"), (2026, 11))  # meia-noite UTC = só o dia
        self.assertEqual(ga.mes_brt("2026-11-01T00:00:00.001Z"), (2026, 10))
        self.assertIsNone(ga.mes_brt("٢٠٢٦-10-01"))  # dígito não ASCII, como no TS
        self.assertEqual(ga.mes_brt(datetime(2026, 11, 1, 2, 0, tzinfo=timezone.utc)), (2026, 10))
        self.assertIsNone(ga.mes_brt("ontem"))
        self.assertIsNone(ga.mes_brt(None))

    def test_orcamento_do_mes_vence_o_geral_e_ausente_vira_none(self):
        self.assertEqual(ga.orcamento_centavos({**SETTINGS, "monthlyBudgets": {"2026-10": 4000}}, 2026, 10), 400000)
        self.assertEqual(ga.orcamento_centavos(SETTINGS, 2026, 9), 484893)
        self.assertIsNone(ga.orcamento_centavos({**SETTINGS, "monthlyBudgets": {"2026-10": 0}}, 2026, 10))
        r = ga.resumo_do_mes(TRANSACOES, {}, 2026, 10)
        self.assertEqual((r["orcamento"], r["saldo"]), (None, None))

    def test_texto_da_notificacao(self):
        com = ga.texto_notificacao_pix(8.9, ga.resumo_do_mes(TRANSACOES, SETTINGS, 2026, 10), HOJE)
        self.assertEqual(com, "Valor: R$ 8.90\nGasto no PicPay no mês: R$ 657.55\n"
                              "Restam R$ 4342.45 no teto (R$ 2171.22 por dia até o fim do mês)")
        estourado = ga.texto_notificacao_pix(8.9, ga.resumo_do_mes(TRANSACOES, {"monthlyBudget": 500}, 2026, 10), HOJE)
        self.assertEqual(estourado, "Valor: R$ 8.90\nGasto no PicPay no mês: R$ 657.55\nTeto do mês estourado em R$ 157.55")
        sem = ga.texto_notificacao_pix(8.9, ga.resumo_do_mes(TRANSACOES, {}, 2026, 10), HOJE)
        self.assertEqual(sem, "Valor: R$ 8.90\nGasto no PicPay no mês: R$ 657.55")

    def test_hoje_brt(self):
        self.assertEqual(ga.hoje_brt(datetime(2026, 11, 1, 2, 30, tzinfo=timezone.utc)), (2026, 10, 31))


if __name__ == "__main__":
    unittest.main()
