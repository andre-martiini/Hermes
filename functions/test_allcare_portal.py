import unittest
from datetime import date

from allcare_portal import (
    AllcarePortalError,
    current_portal_period,
    parse_brl_amount,
    parse_portal_date,
    select_active_profile,
)


class AllcarePortalTests(unittest.TestCase):
    def test_parses_portal_fields(self):
        self.assertEqual(parse_brl_amount("3.069,76"), 3069.76)
        self.assertEqual(parse_portal_date("10/09/2026"), date(2026, 9, 10))

    def test_selects_named_active_profile(self):
        payload = {"retorno": {"dadosAtivarBenef": [
            {"ind_situacao": "I", "nome_plano_cartao": "Participativo Estadual Adesão", "cod_usuario": 1},
            {"ind_situacao": "A", "nome_plano_cartao": "PARTICIPATIVO ESTADUAL ADESÃO ENFERMARIA", "cod_usuario": 2},
        ]}}
        self.assertEqual(select_active_profile(payload)["cod_usuario"], 2)

    def test_rejects_missing_active_profile(self):
        with self.assertRaises(AllcarePortalError):
            select_active_profile({"retorno": {"dadosAtivarBenef": []}})

    def test_current_period_includes_next_month(self):
        self.assertEqual(current_portal_period(date(2026, 12, 20)), ("12/2026", "01/2027"))


if __name__ == "__main__":
    unittest.main()
