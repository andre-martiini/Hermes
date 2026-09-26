"""Semeia `config/video_precos` com os preços padrão do Hermes Vídeo, se o documento não existir.

    python scripts/video_config.py            # mostra o que gravaria
    python scripts/video_config.py --aplicar  # grava (nunca sobrescreve um documento existente)

Depois de semeado, os preços se ajustam editando o documento no console do
Firestore — o código lê o documento por cima de `video/estimativa.PRECOS_PADRAO`.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "functions"))

from google.cloud import firestore  # noqa: E402

from video.estimativa import PRECOS_PADRAO  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    ref = firestore.Client(project="gestao-hermes").collection("config").document("video_precos")
    if ref.get().exists:
        print("config/video_precos já existe — nada a fazer (edite pelo console).")
        return
    print(json.dumps(PRECOS_PADRAO, ensure_ascii=False, indent=2))
    if args.aplicar:
        ref.create({**PRECOS_PADRAO, "origem": "scripts/video_config.py (Fase 0, 26/09/2026)"})
        print("config/video_precos criado.")
    else:
        print("(simulação — rode com --aplicar para gravar)")


if __name__ == "__main__":
    main()
