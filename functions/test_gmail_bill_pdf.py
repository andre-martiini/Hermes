import io
import os
import sys
import unittest

from pypdf import PdfReader, PdfWriter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gmail_bill_pdf import (
    is_gemini_invalid_argument,
    prepare_pdf_for_gemini,
    validate_bill_payload,
)


def _pdf_bytes(*, password=None):
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    if password is not None:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class TestPreparePdfForGemini(unittest.TestCase):
    def test_accepts_regular_pdf(self):
        original = _pdf_bytes()
        prepared, reason = prepare_pdf_for_gemini(original)
        self.assertEqual(prepared, original)
        self.assertIsNone(reason)

    def test_rewrites_pdf_encrypted_with_empty_password(self):
        prepared, reason = prepare_pdf_for_gemini(_pdf_bytes(password=""))
        self.assertIsNotNone(prepared)
        self.assertIsNone(reason)
        self.assertFalse(PdfReader(io.BytesIO(prepared)).is_encrypted)

    def test_rejects_password_protected_pdf(self):
        prepared, reason = prepare_pdf_for_gemini(_pdf_bytes(password="segredo"))
        self.assertIsNone(prepared)
        self.assertEqual(reason, "pdf_protegido_por_senha")

    def test_opens_password_protected_pdf_with_registered_password(self):
        prepared, reason = prepare_pdf_for_gemini(
            _pdf_bytes(password="segredo"),
            passwords=["incorreta", "segredo"],
        )
        self.assertIsNotNone(prepared)
        self.assertIsNone(reason)
        self.assertFalse(PdfReader(io.BytesIO(prepared)).is_encrypted)

    def test_rejects_non_pdf_and_empty_content(self):
        self.assertEqual(prepare_pdf_for_gemini(b""), (None, "pdf_vazio"))
        self.assertEqual(prepare_pdf_for_gemini(b"html"), (None, "arquivo_nao_e_pdf"))

    def test_recognizes_invalid_argument(self):
        self.assertTrue(is_gemini_invalid_argument(Exception("400 INVALID_ARGUMENT")))
        self.assertFalse(is_gemini_invalid_argument(Exception("503 UNAVAILABLE")))

    def test_rejects_null_due_date_without_raising(self):
        payload, reason = validate_bill_payload({
            "description": "Conta",
            "amount": 10,
            "due_date": None,
        })
        self.assertIsNone(payload)
        self.assertEqual(reason, "vencimento_ausente")

    def test_normalizes_valid_bill_payload(self):
        payload, reason = validate_bill_payload({
            "description": "  Conta  ",
            "amount": "10.50",
            "due_date": "2026-08-30",
        })
        self.assertIsNone(reason)
        self.assertEqual(payload["description"], "Conta")
        self.assertEqual(payload["amount"], 10.5)


if __name__ == "__main__":
    unittest.main()
