#!/usr/bin/env python3
"""Popula `public_configs/firebase_web` a partir de firebase.ts.

A pagina de consentimento do OAuth (`mcp_oauth.py`) precisa da config do app web
para fazer o login com Google. Ela le esse documento em vez de trazer a config
escrita no codigo do backend — que criaria mais uma copia do padrao `AIza...`
num repositorio publico, exatamente o que os scanners de chave sinalizam.

`firebase.ts` continua sendo a fonte unica; este script so copia de la.

Uso:
    python scripts/seed_mcp_oauth_config.py [--dry-run]
"""

from __future__ import annotations

import json
import os
import re
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CAMPOS = (
    "apiKey", "authDomain", "projectId",
    "storageBucket", "messagingSenderId", "appId",
)


def ler_config_de_firebase_ts() -> dict:
    caminho = os.path.join(_RAIZ, "firebase.ts")
    with open(caminho, encoding="utf-8") as f:
        fonte = f.read()

    bloco = re.search(r"const firebaseConfig\s*=\s*\{(.*?)\}", fonte, re.S)
    if not bloco:
        raise SystemExit(f"Nao encontrei `const firebaseConfig` em {caminho}")

    config = {}
    for chave, valor in re.findall(
        r"""(\w+)\s*:\s*["']([^"']+)["']""", bloco.group(1)
    ):
        if chave in _CAMPOS:
            config[chave] = valor

    faltando = [c for c in _CAMPOS if c not in config]
    if faltando:
        raise SystemExit(f"Campos ausentes em firebaseConfig: {faltando}")
    return config


def main() -> None:
    config = ler_config_de_firebase_ts()
    # A chave nao e segredo, mas nao ha razao para imprimi-la no terminal.
    visivel = {**config, "apiKey": config["apiKey"][:10] + "..."}
    print(json.dumps(visivel, indent=2, ensure_ascii=False))

    if "--dry-run" in sys.argv:
        print("\n[dry-run] nada gravado.")
        return

    import firebase_admin
    from firebase_admin import credentials, firestore

    chave = os.environ.get("HERMES_SERVICE_ACCOUNT") or os.path.join(
        _RAIZ, "firebase_service_account_key.json"
    )
    if not os.path.exists(chave):
        raise SystemExit(f"Service account nao encontrada em {chave}")

    try:
        app = firebase_admin.get_app("hermes-seed-oauth")
    except ValueError:
        app = firebase_admin.initialize_app(
            credentials.Certificate(chave), name="hermes-seed-oauth"
        )

    firestore.client(app).collection("public_configs").document("firebase_web").set(
        config, merge=True
    )
    print("\ngravado em public_configs/firebase_web")


if __name__ == "__main__":
    main()
