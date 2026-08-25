import base64
import unittest

from allcare_bill import (
    AllcareBillError,
    extract_allcare_tracking_url,
    is_allcare_bill_sender,
)


class AllcareBillTests(unittest.TestCase):
    def test_recognizes_only_official_sender(self):
        self.assertTrue(is_allcare_bill_sender("Boletos Allcare <boleto@allcaregestoradesaude.com.br>"))
        self.assertFalse(is_allcare_bill_sender("boleto@allcare.example"))

    def test_extracts_official_tracking_link_from_nested_html(self):
        html = (
            '<a href="https://example.com/ignorar">x</a>'
            '<a href="https://url1651.allcaregestoradesaude.com.br/ls/click?upn=abc&amp;x=1">boleto</a>'
        )
        encoded = base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")
        payload = {"parts": [{"mimeType": "text/html", "body": {"data": encoded}}]}
        self.assertEqual(
            extract_allcare_tracking_url(payload),
            "https://url1651.allcaregestoradesaude.com.br/ls/click?upn=abc&x=1",
        )

    def test_accepts_official_http_tracking_link(self):
        html = '<a href="http://url1651.allcaregestoradesaude.com.br/ls/click?upn=abc">boleto</a>'
        encoded = base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")
        self.assertEqual(
            extract_allcare_tracking_url({"mimeType": "text/html", "body": {"data": encoded}}),
            "http://url1651.allcaregestoradesaude.com.br/ls/click?upn=abc",
        )

    def test_rejects_non_official_link(self):
        html = '<a href="https://attacker.example/ls/click?upn=abc">boleto</a>'
        encoded = base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")
        with self.assertRaises(AllcareBillError):
            extract_allcare_tracking_url({"mimeType": "text/html", "body": {"data": encoded}})


if __name__ == "__main__":
    unittest.main()
