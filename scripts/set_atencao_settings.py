#!/usr/bin/env python3
"""Configura as flags de detecção da fila de atenção (system/settings.atencao).

Uso:
    python scripts/set_atencao_settings.py --ativar-tudo
    python scripts/set_atencao_settings.py --desativar-tudo
    python scripts/set_atencao_settings.py --mostrar
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHAVE = os.environ.get(
    "HERMES_SERVICE_ACCOUNT",
    os.path.join(_RAIZ, "firebase_service_account_key.json"),
)


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(_CHAVE))
    return firestore.client()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--ativar-tudo",
        action="store_true",
        help="ativa todos os detectores da fila de atencao (financeiro, saude, promessa, audio, aguardando_terceiro)",
    )
    g.add_argument(
        "--desativar-tudo",
        action="store_true",
        help="desativa todos os detectores da fila de atencao",
    )
    g.add_argument(
        "--mostrar",
        action="store_true",
        help="mostra o estado atual das flags em system/settings.atencao",
    )
    args = p.parse_args()

    db = _db()
    alvo = db.collection("system").document("settings")
    snap = alvo.get()
    dados = snap.to_dict() or {}
    atual = dados.get("atencao") or {}

    if args.mostrar:
        print("Estado atual de system/settings.atencao:")
        print(json.dumps(atual, indent=2, default=str))
        return 0

    if args.ativar_tudo:
        novo_atencao = {
            "financeiro": {"enabled": True},
            "saude": {"enabled": True},
            "promessa_sem_retorno": {"enabled": True, "horas": 4.0},
            "audio_relevante": {"enabled": True, "segundos_min": 60},
            "aguardando_terceiro": {"enabled": True},
        }
        alvo.set({"atencao": novo_atencao}, merge=True)
        print("Flags de atencao ativadas com sucesso:")
        print(json.dumps(novo_atencao, indent=2, default=str))
        return 0

    if args.desativar_tudo:
        novo_atencao = {
            "financeiro": {"enabled": False},
            "saude": {"enabled": False},
            "promessa_sem_retorno": {"enabled": False},
            "audio_relevante": {"enabled": False},
            "aguardando_terceiro": {"enabled": False},
        }
        alvo.set({"atencao": novo_atencao}, merge=True)
        print("Flags de atencao desativadas com sucesso:")
        print(json.dumps(novo_atencao, indent=2, default=str))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
