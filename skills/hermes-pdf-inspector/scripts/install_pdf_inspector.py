from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


EXPECTED_VERSION = "1.2.0"
REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_DIR = REPO_ROOT / "automations" / "pdf_inspector_runner"
PACKAGE_JSON = RUNNER_DIR / "package.json"


def ensure_node() -> str:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise SystemExit("Node.js e npm sao obrigatorios para instalar o pdf-inspector local.")
    return npm


def ensure_package_manifest() -> None:
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    if PACKAGE_JSON.exists():
        return

    package_data = {
        "name": "hermes-pdf-inspector-runner",
        "private": True,
        "type": "module",
        "dependencies": {
            "@firecrawl/pdf-inspector": EXPECTED_VERSION,
        },
    }
    PACKAGE_JSON.write_text(json.dumps(package_data, indent=2) + "\n", encoding="utf-8")


def npm_install(npm_path: str) -> None:
    subprocess.run(
        [npm_path, "install", "--no-fund", "--no-audit"],
        cwd=RUNNER_DIR,
        check=True,
    )


def verify_install() -> None:
    cli_path = RUNNER_DIR / "node_modules" / "@firecrawl" / "pdf-inspector" / "bin" / "pdf-inspector.mjs"
    if not cli_path.exists():
        raise SystemExit(f"Instalacao concluida sem CLI esperada: {cli_path}")


def main() -> int:
    npm_path = ensure_node()
    ensure_package_manifest()
    npm_install(npm_path)
    verify_install()
    print(f"pdf-inspector {EXPECTED_VERSION} pronto em {RUNNER_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

