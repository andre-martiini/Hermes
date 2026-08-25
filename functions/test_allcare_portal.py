import unittest
from datetime import date

from allcare_portal import (
    AllcarePortalClient,
    AllcarePortalError,
    current_portal_period,
    parse_brl_amount,
    parse_portal_date,
    select_active_profile,
)


class FakeResponse:
    def __init__(self, *, payload=None, url="", text="", ok=True, status_code=200):
        self._payload = payload
        self.url = url
        self.text = text
        self.ok = ok
        self.status_code = status_code

    def json(self):
        return self._payload


class RecordingSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/Account/ValidarBeneficiario"):
            return FakeResponse(payload={"retorno": {"dadosAtivarBenef": [{
                "ind_situacao": "A",
                "nome_plano_cartao": "PARTICIPATIVO ESTADUAL ADESÃO ENFERMARIA",
                "cod_usuario": 2,
            }]}})
        if "/Account/AutenticarBeneficiario/" in url:
            return FakeResponse(
                url="https://beneficiario.allcare.com.br/TSNMVC/HomePortalBeneficiario",
                text="Sair",
            )
        return FakeResponse(url=url, text="login")


class AllcarePortalTests(unittest.TestCase):
    def test_login_uses_ajax_only_for_profile_validation(self):
        session = RecordingSession()
        client = AllcarePortalClient(session)

        client.login("12345678901", "secret")

        validation_headers = session.calls[0][2]["headers"]
        authentication_headers = session.calls[1][2]["headers"]
        self.assertEqual(validation_headers["X-Requested-With"], "XMLHttpRequest")
        self.assertNotIn("X-Requested-With", authentication_headers)
        self.assertNotIn("X-Requested-With", session.headers)

    def test_http_error_identifies_only_the_safe_stage(self):
        session = RecordingSession()
        session.request = lambda *args, **kwargs: FakeResponse(ok=False, status_code=400)
        client = AllcarePortalClient(session)

        with self.assertRaisesRegex(AllcarePortalError, "portal_http_400_validacao"):
            client.login("12345678901", "secret")

    def test_login_does_not_open_blocked_home_page(self):
        session = RecordingSession()
        client = AllcarePortalClient(session)

        client.login("12345678901", "secret")

        self.assertEqual(len(session.calls), 2)
        self.assertTrue(session.calls[0][1].endswith("/Account/ValidarBeneficiario"))

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
