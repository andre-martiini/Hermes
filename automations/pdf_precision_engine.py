from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_DIR = REPO_ROOT / "automations" / "pdf_inspector_runner"
CLI_SCRIPT = RUNNER_DIR / "node_modules" / "@firecrawl" / "pdf-inspector" / "bin" / "pdf-inspector.mjs"


def _node_binary() -> str:
    node = shutil.which("node")
    if not node:
        raise FileNotFoundError("Node.js nao encontrado no PATH.")
    return node


def _cli_script() -> Path:
    if not CLI_SCRIPT.exists():
        raise FileNotFoundError(
            "pdf-inspector nao instalado. Execute "
            "'python skills/hermes-pdf-inspector/scripts/install_pdf_inspector.py'."
        )
    return CLI_SCRIPT


async def process_pdf_with_precision(file_path: str | Path, timeout_seconds: int = 90) -> dict[str, Any]:
    pdf_path = Path(file_path).expanduser().resolve()
    if not pdf_path.exists():
        return {
            "action": "fallback_to_gemini",
            "error": f"Arquivo nao encontrado: {pdf_path}",
        }

    try:
        node = _node_binary()
        cli_script = _cli_script()
    except FileNotFoundError as exc:
        return {
            "action": "fallback_to_gemini",
            "error": str(exc),
        }

    process = await asyncio.create_subprocess_exec(
        node,
        str(cli_script),
        str(pdf_path),
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(REPO_ROOT),
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return {
            "action": "fallback_to_gemini",
            "error": f"Tempo limite excedido ao processar {pdf_path.name}",
        }

    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        return {
            "action": "fallback_to_gemini",
            "error": stderr_text or f"pdf-inspector retornou codigo {process.returncode}",
        }

    try:
        data = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return {
            "action": "fallback_to_gemini",
            "error": f"JSON invalido do pdf-inspector: {exc}",
            "stderr": stderr_text,
        }

    pdf_type = str(data.get("pdfType") or "").strip()
    markdown = data.get("markdown")
    ocr_pages = data.get("pagesNeedingOcr") or []
    has_encoding_issues = bool(data.get("hasEncodingIssues"))

    result = {
        "action": "use_local_markdown",
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


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Uso: python automations/pdf_precision_engine.py <arquivo.pdf>", file=sys.stderr)
        return 1

    result = asyncio.run(process_pdf_with_precision(argv[1]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

