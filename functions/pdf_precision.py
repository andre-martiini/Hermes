from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_GEMINI_TEXT_PROMPT = (
    "Extraia o texto legivel deste PDF para indexacao e consulta no Hermes. "
    "Preserve a estrutura em Markdown quando possivel, incluindo titulos, listas e tabelas. "
    "Se o documento precisar de OCR, execute OCR. "
    "Retorne apenas o texto extraido, sem comentarios."
)


def is_pdf_mime_type(filename: str | None, mime_type: str | None) -> bool:
    filename = (filename or "").lower()
    mime_type = (mime_type or "").lower()
    return filename.endswith(".pdf") or mime_type == "application/pdf" or mime_type.endswith("/pdf")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _local_cli_script() -> Path | None:
    candidates = [
        _repo_root() / "automations" / "pdf_inspector_runner" / "node_modules" / "@firecrawl" / "pdf-inspector" / "bin" / "pdf-inspector.mjs",
        Path.cwd() / "automations" / "pdf_inspector_runner" / "node_modules" / "@firecrawl" / "pdf-inspector" / "bin" / "pdf-inspector.mjs",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _run_local_pdf_inspector(file_bytes: bytes, filename: str) -> dict[str, Any]:
    node_path = shutil.which("node")
    cli_script = _local_cli_script()
    if not node_path or cli_script is None:
        return {
            "available": False,
            "action": "fallback_to_gemini",
            "reason": "local_runtime_unavailable",
        }

    suffix = Path(filename or "documento.pdf").suffix or ".pdf"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        process = subprocess.run(
            [node_path, str(cli_script), temp_path, "--json"],
            capture_output=True,
            text=True,
            timeout=90,
            cwd=str(_repo_root()),
            check=False,
        )
        if process.returncode != 0:
            return {
                "available": True,
                "action": "fallback_to_gemini",
                "reason": "local_cli_error",
                "stderr": (process.stderr or "").strip(),
            }

        data = json.loads(process.stdout or "{}")
        pdf_type = str(data.get("pdfType") or "").strip()
        markdown = data.get("markdown")
        ocr_pages = data.get("pagesNeedingOcr") or []
        has_encoding_issues = bool(data.get("hasEncodingIssues"))

        result = {
            "available": True,
            "action": "use_local_markdown",
            "reason": None,
            "source": "pdf-inspector",
            "pdf_type": pdf_type,
            "markdown": markdown,
            "ocr_required_pages": ocr_pages,
            "page_count": data.get("pageCount"),
            "confidence": data.get("confidence"),
            "pages_with_tables": data.get("pagesWithTables") or [],
            "pages_with_columns": data.get("pagesWithColumns") or [],
            "has_encoding_issues": has_encoding_issues,
        }

        if has_encoding_issues:
            result["action"] = "force_full_ocr"
            result["reason"] = "broken_font_encoding"
            result["markdown"] = None
            return result

        if pdf_type in {"Scanned", "ImageBased"}:
            result["action"] = "fallback_to_gemini"
            result["reason"] = "non_text_pdf"
            result["markdown"] = None
            return result

        if ocr_pages:
            result["action"] = "hybrid_merge"
            result["reason"] = "partial_ocr_required"

        return result
    except subprocess.TimeoutExpired:
        return {
            "available": True,
            "action": "fallback_to_gemini",
            "reason": "local_timeout",
        }
    except Exception as exc:
        return {
            "available": True,
            "action": "fallback_to_gemini",
            "reason": "local_exception",
            "error": str(exc),
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _extract_with_pdfplumber(file_bytes: bytes, max_pages: int | None = None) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = pdf.pages[:max_pages] if max_pages else pdf.pages
        return "\n\n".join(page.extract_text() or "" for page in pages).strip()


def _extract_with_gemini(file_bytes: bytes, api_key: str, prompt: str | None = None) -> str:
    from google import genai
    from gemini_cost_controls import GEMINI_DOCUMENT_MODEL, generate_content_logged

    client = genai.Client(api_key=api_key)
    response = generate_content_logged(
        client,
        model=GEMINI_DOCUMENT_MODEL,
        contents=[
            {"mime_type": "application/pdf", "data": file_bytes},
            prompt or DEFAULT_GEMINI_TEXT_PROMPT,
        ],
        feature="pdf_precision.gemini_ocr",
    )
    return (response.text or "").strip()


def _build_pdf_subset_bytes(file_bytes: bytes, zero_index_pages: list[int]) -> bytes:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(file_bytes))
    writer = PdfWriter()
    for page_index in sorted({page for page in zero_index_pages if page >= 0}):
        if page_index < len(reader.pages):
            writer.add_page(reader.pages[page_index])

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _extract_selected_pages_with_gemini(
    file_bytes: bytes,
    filename: str,
    api_key: str,
    zero_index_pages: list[int],
) -> dict[int, str]:
    page_texts: dict[int, str] = {}
    for page_index in sorted({page for page in zero_index_pages if page >= 0}):
        subset_bytes = _build_pdf_subset_bytes(file_bytes, [page_index])
        prompt = (
            f"Extraia o texto da página {page_index + 1} do PDF '{filename}'. "
            "Retorne apenas o texto legível dessa página, preservando títulos, listas, colunas e tabelas em Markdown quando possível. "
            "Não inclua comentários."
        )
        page_text = _extract_with_gemini(subset_bytes, api_key, prompt)
        if page_text:
            page_texts[page_index] = page_text.strip()
    return page_texts


def _merge_local_markdown_with_page_ocr(markdown: str, page_ocr_map: dict[int, str]) -> str:
    base = (markdown or "").strip()
    if not page_ocr_map:
        return base

    supplements = []
    for page_index in sorted(page_ocr_map):
        page_text = (page_ocr_map.get(page_index) or "").strip()
        if not page_text:
            continue
        supplements.append(
            f"## OCR Suplementar - Pagina {page_index + 1}\n\n{page_text}"
        )

    if not supplements:
        return base

    if base:
        return f"{base}\n\n---\n\n" + "\n\n---\n\n".join(supplements)
    return "\n\n---\n\n".join(supplements)


def extract_pdf_text_with_fallback(
    file_bytes: bytes,
    filename: str,
    *,
    api_key: str | None = None,
    allow_gemini_fallback: bool = False,
    gemini_prompt: str | None = None,
    allow_pdfplumber_fallback: bool = True,
    max_pages: int | None = None,
) -> dict[str, Any]:
    local_result = _run_local_pdf_inspector(file_bytes, filename)
    action = local_result.get("action")
    markdown = (local_result.get("markdown") or "").strip()

    if action == "hybrid_merge" and markdown:
        ocr_pages = [int(page) for page in (local_result.get("ocr_required_pages") or [])]
        if api_key and ocr_pages:
            try:
                page_ocr_map = _extract_selected_pages_with_gemini(file_bytes, filename, api_key, ocr_pages)
                merged_text = _merge_local_markdown_with_page_ocr(markdown, page_ocr_map)
                local_result = dict(local_result)
                local_result["hybrid_ocr_pages_completed"] = sorted(page_ocr_map)
                local_result["hybrid_ocr_pages_missing"] = [page for page in ocr_pages if page not in page_ocr_map]
                return {
                    "success": True,
                    "text": merged_text,
                    "strategy": "hybrid_merge",
                    "metadata": local_result,
                }
            except Exception as exc:
                local_result = dict(local_result)
                local_result["hybrid_ocr_error"] = str(exc)

        return {
            "success": True,
            "text": markdown,
            "strategy": "hybrid_merge",
            "metadata": local_result,
        }

    if action == "use_local_markdown" and markdown:
        return {
            "success": True,
            "text": markdown,
            "strategy": action,
            "metadata": local_result,
        }

    if allow_gemini_fallback and api_key and action in {"fallback_to_gemini", "force_full_ocr"}:
        try:
            gemini_text = _extract_with_gemini(file_bytes, api_key, gemini_prompt)
            if gemini_text:
                return {
                    "success": True,
                    "text": gemini_text,
                    "strategy": "gemini_fallback",
                    "metadata": local_result,
                }
        except Exception as exc:
            local_result = dict(local_result)
            local_result["gemini_fallback_error"] = str(exc)

    if allow_pdfplumber_fallback and action not in {"force_full_ocr"}:
        try:
            plumber_text = _extract_with_pdfplumber(file_bytes, max_pages=max_pages)
            if plumber_text:
                return {
                    "success": True,
                    "text": plumber_text,
                    "strategy": "pdfplumber_fallback",
                    "metadata": local_result,
                }
        except Exception as exc:
            local_result = dict(local_result)
            local_result["pdfplumber_fallback_error"] = str(exc)

    return {
        "success": False,
        "text": "",
        "strategy": "none",
        "metadata": local_result,
    }
