"""Validação de PDFs recebidos pela sincronização de boletos do Gmail."""

from __future__ import annotations

import io
from datetime import date
from typing import Any, Iterable


def prepare_pdf_for_gemini(
    file_bytes: bytes,
    passwords: Iterable[str] | None = None,
) -> tuple[bytes | None, str | None]:
    """Retorna um PDF seguro para envio ao Gemini ou o motivo do fallback textual.

    O Gemini responde ``400 INVALID_ARGUMENT`` para PDFs criptografados. Alguns
    arquivos são apenas encapsulados com senha vazia; esses são descriptografados
    e regravados. Arquivos protegidos por senha real não podem ser analisados sem
    credenciais e, portanto, devem cair no assunto/snippet do e-mail.
    """
    if not file_bytes:
        return None, "pdf_vazio"
    if not file_bytes.lstrip().startswith(b"%PDF-"):
        return None, "arquivo_nao_e_pdf"

    try:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(file_bytes), strict=False)
        if reader.is_encrypted:
            decrypted_reader = None
            candidates = [""]
            candidates.extend(password for password in (passwords or []) if isinstance(password, str) and password)
            for candidate in dict.fromkeys(candidates):
                try:
                    candidate_reader = PdfReader(io.BytesIO(file_bytes), strict=False)
                    if candidate_reader.decrypt(candidate):
                        decrypted_reader = candidate_reader
                        break
                except Exception:
                    continue
            if decrypted_reader is None:
                return None, "pdf_protegido_por_senha"
            reader = decrypted_reader

            writer = PdfWriter()
            writer.append_pages_from_reader(reader)
            output = io.BytesIO()
            writer.write(output)
            file_bytes = output.getvalue()
            reader = PdfReader(io.BytesIO(file_bytes), strict=False)

        if len(reader.pages) == 0:
            return None, "pdf_sem_paginas"
    except Exception:
        return None, "pdf_invalido"

    return file_bytes, None


def is_gemini_invalid_argument(exc: Exception) -> bool:
    """Reconhece o erro genérico usado pelo Gemini para anexos inválidos."""
    message = str(exc).upper()
    return "INVALID_ARGUMENT" in message or "INVALID ARGUMENT" in message


def validate_bill_payload(payload: Any) -> tuple[dict | None, str | None]:
    """Normaliza a resposta da IA sem deixar campos nulos quebrarem o sync."""
    if not isinstance(payload, dict):
        return None, "resposta_nao_e_objeto"
    if payload.get("error"):
        return None, str(payload["error"])

    description = str(payload.get("description") or "").strip()
    due_date = payload.get("due_date")
    if not description:
        return None, "descricao_ausente"
    if not isinstance(due_date, str) or not due_date.strip():
        return None, "vencimento_ausente"
    try:
        date.fromisoformat(due_date.strip())
    except ValueError:
        return None, "vencimento_invalido"

    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        return None, "valor_ausente_ou_invalido"
    if amount <= 0:
        return None, "valor_nao_positivo"

    normalized = dict(payload)
    normalized["description"] = description
    normalized["due_date"] = due_date.strip()
    normalized["amount"] = amount
    return normalized, None
