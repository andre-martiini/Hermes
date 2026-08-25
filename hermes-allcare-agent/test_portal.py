import unittest
from datetime import date

from portal import PortalClient, PortalError, current_period


class Response:
    def __init__(self, *, payload=None, url="", content=b"", ok=True, status_code=200):
        self.payload = payload
        self.url = url
        self.content = content
        self.ok = ok
        self.status_code = status_code

    def json(self):
        return self.payload


class Session:
    def __init__(self, responses):
        self.headers = {}
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


class PortalTests(unittest.TestCase):
    def test_period_includes_next_month(self):
        self.assertEqual(current_period(date(2026, 12, 1)), ("12/2026", "01/2027"))

    def test_login_selects_expected_active_plan(self):
        session = Session([
            Response(url="https://beneficiario.allcare.com.br/"),
            Response(payload={"retorno": {"dadosAtivarBenef": [
                {"ind_situacao": "A", "nome_plano_cartao": "OUTRO", "cod_usuario": 1},
                {"ind_situacao": "A", "nome_plano_cartao": "Participativo Estadual Adesão Enfermaria", "cod_usuario": 2},
            ]}}),
            Response(url="https://beneficiario.allcare.com.br/TSNMVC/HomePortalBeneficiario"),
        ])
        profile = PortalClient(session).login(
            "12345678901", "secret", "PARTICIPATIVO ESTADUAL ADESAO"
        )
        self.assertEqual(profile["cod_usuario"], 2)
        self.assertEqual(session.calls[2][2]["data"]["usuario"], "2")

    def test_login_does_not_store_password_in_headers(self):
        session = Session([
            Response(url="https://beneficiario.allcare.com.br/"),
            Response(payload={"retorno": {"dadosAtivarBenef": [{
                "ind_situacao": "A", "nome_plano_cartao": "Participativo Estadual Adesão", "cod_usuario": 2,
            }]}}),
            Response(url="https://beneficiario.allcare.com.br/TSNMVC/HomePortalBeneficiario"),
        ])
        PortalClient(session).login("12345678901", "secret", "PARTICIPATIVO ESTADUAL ADESAO")
        self.assertNotIn("secret", repr(session.headers))

    def test_empty_profiles_mean_rejected_credentials(self):
        session = Session([
            Response(url="https://beneficiario.allcare.com.br/"),
            Response(payload={"retorno": {"dadosAtivarBenef": []}}),
        ])
        with self.assertRaisesRegex(PortalError, "credenciais_rejeitadas"):
            PortalClient(session).login("12345678901", "wrong", "PLANO")

    def test_download_requires_pdf_signature(self):
        session = Session([
            Response(payload=["SUCESSO", "", "boleto", "pdf"]),
            Response(content=b"not a pdf"),
        ])
        with self.assertRaisesRegex(PortalError, "arquivo_do_boleto_invalido"):
            PortalClient(session).download_bill({"num_seq_cobranca": "1", "cod_ts": "2"})


if __name__ == "__main__":
    unittest.main()
