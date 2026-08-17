"""Testa as 6 regras de decisao do N14 Fase 2 (build_weekly_adjustment) contra
cards sinteticos -- um por regra, checando qual dispara e se a ordem de
precedencia se sustenta.

So a regra 'poucos_dados' tinha sido exercitada contra dado real ate agora
(era a unica que a semana corrente disparava). Pedido do revisor no
REVISAO-INBOX.md: "um teste com cards sinteticos, um por regra... em especial
o criterio 4 da spec, aderencia baixa nunca gera corte de calorias, que e o
unico cuja falha faz o sistema recomendar algo ativamente ruim para o Andre."

Uso: functions/venv/Scripts/python.exe functions/test_health_weekly_report.py
"""
import sys
import unittest

sys.path.insert(0, '.')

from health_weekly_report import build_weekly_adjustment


def _base_card(**overrides):
    card = {
        "week_start": "2026-08-10",
        "week_end": "2026-08-16",
        "weight_avg7": 90.0,
        "weight_delta": 0.0,
        "waist": {"value": None, "delta": None},
        "km_total": 30.0,
        "km_days": 6,
        "pain_morning_avg": 3.0,
        "pain_evening_avg": 3.0,
        "radicular_trend": "estável",
        "strength_done": 3,
        "strength_planned": 3,
        "therapy_done": 1,
        "therapy_planned": 1,
        "checkin_adherence": 0.9,
        "sleep_avg": 4.0,
    }
    card.update(overrides)
    return card


def _log(**overrides):
    log = {"pain": {"morning": 3, "evening": 3}, "radicular": {}}
    log.update(overrides)
    return log


class TestSixRules(unittest.TestCase):
    def test_1_sinal_vermelho_ganha_de_tudo(self):
        """Sinal vermelho tem que vencer mesmo quando outras regras tambem
        casariam (radicular descendo + sinal vermelho no mesmo card)."""
        card = _base_card(radicular_trend="descendo")
        week_logs = {"2026-08-12": _log(radicular={"location": "pe"})}
        result = build_weekly_adjustment(week_logs, card, None)
        self.assertEqual(result["rule"], "sinal_vermelho")
        self.assertIsNone(result["text"])

    def test_2_radicular_descendo(self):
        card = _base_card(radicular_trend="descendo")
        result = build_weekly_adjustment({}, card, None)
        self.assertEqual(result["rule"], "reduzir_carga")
        self.assertIn("Reduzir carga", result["text"])

    def test_3_poucos_dados(self):
        card = _base_card(weight_avg7=None, checkin_adherence=0.28)
        result = build_weekly_adjustment({}, card, None)
        self.assertEqual(result["rule"], "poucos_dados")
        self.assertIn("registrar mais", result["text"])

    def test_4_aderencia_baixa_por_checkin(self):
        card = _base_card(checkin_adherence=0.4)
        result = build_weekly_adjustment({}, card, None)
        self.assertEqual(result["rule"], "aderencia")

    def test_4b_aderencia_baixa_por_treino(self):
        card = _base_card(strength_done=1, checkin_adherence=0.9)
        result = build_weekly_adjustment({}, card, None)
        self.assertEqual(result["rule"], "aderencia")

    def test_4c_criterio_mais_importante_aderencia_baixa_nunca_corta_caloria(self):
        """O teste que mais importa: mesmo com weight_delta >= 0 nas duas
        semanas (condicao que sozinha dispararia 'cortar_kcal') e aderencia ao
        checkin alta o bastante para passar o primeiro filtro, se o treino de
        forca ficou abaixo de 2 sessoes, a regra tem que ser 'aderencia' --
        nunca 'cortar_kcal'. Falhar aqui significa o sistema recomendando
        corte de caloria numa semana em que a prescricao nao foi seguida."""
        card = _base_card(weight_delta=0.3, checkin_adherence=0.85, strength_done=1)
        prev_card = _base_card(weight_delta=0.2)
        result = build_weekly_adjustment({}, card, prev_card)
        self.assertEqual(result["rule"], "aderencia")
        self.assertNotEqual(result["rule"], "cortar_kcal")

    def test_5_cortar_kcal(self):
        card = _base_card(weight_delta=0.2, checkin_adherence=0.85, strength_done=3)
        prev_card = _base_card(weight_delta=0.1)
        result = build_weekly_adjustment({}, card, prev_card)
        self.assertEqual(result["rule"], "cortar_kcal")

    def test_5b_cortar_kcal_nao_dispara_sem_duas_semanas_seguidas(self):
        """weight_delta >= 0 so nesta semana, semana anterior negativa --
        nao pode cortar caloria com uma unica semana de sinal."""
        card = _base_card(weight_delta=0.2, checkin_adherence=0.85, strength_done=3)
        prev_card = _base_card(weight_delta=-0.3)
        result = build_weekly_adjustment({}, card, prev_card)
        self.assertNotEqual(result["rule"], "cortar_kcal")
        self.assertEqual(result["rule"], "manter")

    def test_6_aumentar_kcal(self):
        card = _base_card(weight_delta=-1.5, checkin_adherence=0.85, strength_done=3)
        prev_card = _base_card(weight_delta=-1.4)
        result = build_weekly_adjustment({}, card, prev_card)
        self.assertEqual(result["rule"], "aumentar_kcal")

    def test_7_manter(self):
        card = _base_card(weight_delta=0.1, checkin_adherence=0.85, strength_done=3)
        prev_card = _base_card(weight_delta=-0.1)
        result = build_weekly_adjustment({}, card, prev_card)
        self.assertEqual(result["rule"], "manter")

    def test_precedencia_radicular_descendo_antes_de_poucos_dados(self):
        """Sintoma piorando importa mais do que a falta de dado -- se os dois
        casos coincidem, quem vence e o radicular."""
        card = _base_card(radicular_trend="descendo", weight_avg7=None, checkin_adherence=0.3)
        result = build_weekly_adjustment({}, card, None)
        self.assertEqual(result["rule"], "reduzir_carga")


if __name__ == '__main__':
    unittest.main()
