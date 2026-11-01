"""Gera a biblioteca de SFX do kit no ElevenLabs (text_to_sound_effects). Roda uma vez; nomes estáveis.

    PY gerar_sfx.py [--refazer nome1,nome2]     # → assets/sfx/<nome>.mp3 (≤ 0,8 s)

Chave: ELEVENLABS_API_KEY ou o campo `elevenlabs_api_key` de system/api_keys (Firestore, com a conta de
serviço do Hermes em GOOGLE_APPLICATION_CREDENTIALS). Rode com o python da venv das functions do Hermes.
Custo: créditos do ElevenLabs, ~20 sons de 0,5–0,8 s.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent / "assets" / "sfx"

# nome estável → (descrição para o modelo, duração em s). O mínimo da API é 0,5 s.
SONS = {
    "whoosh-curto": ("short soft airy whoosh, clean UI motion graphics transition, no music", 0.5),
    "whoosh-longo": ("smooth airy whoosh sweeping left to right, clean motion graphics, no music", 0.8),
    "pop": ("soft clean UI pop, bubble-like, satisfying, no reverb", 0.5),
    "pop-2": ("subtle muted pop, light UI element appearing, no reverb", 0.5),
    "tick": ("single crisp short mechanical counter tick, very short, dry", 0.5),
    "tick-2": ("single soft digital tick, number counter, very short, dry", 0.5),
    "riser": ("short airy riser building tension, clean, ends abruptly", 0.8),
    "impacto-suave": ("soft deep low impact thump, cinematic but gentle, short tail", 0.8),
    "click": ("clean mouse click, crisp, dry, single", 0.5),
    "click-2": ("soft UI tap click, gentle, dry, single", 0.5),
    "swipe": ("quick paper-like swipe swoosh, UI card sliding, short", 0.5),
    "swoosh-subindo": ("short upward swoosh, light and airy, motion graphics", 0.6),
    "glitch-leve": ("very short subtle digital glitch, tech UI, clean", 0.5),
    "sino": ("single gentle bright notification bell ding, short decay", 0.8),
    "ding-suave": ("soft warm chime ding, positive confirmation, short decay", 0.8),
    "brilho": ("short magical shimmer sparkle, subtle, clean", 0.8),
    "thud": ("muted soft wooden thud, short, dry", 0.5),
    "bolha": ("single small water bubble blip, playful, short", 0.5),
    "ar": ("gentle air puff transition, soft, short", 0.5),
    "confirma": ("two-note soft positive UI confirmation chime, short", 0.8),
}


def chave() -> str:
    if os.environ.get("ELEVENLABS_API_KEY"):
        return os.environ["ELEVENLABS_API_KEY"]
    from google.cloud import firestore

    doc = firestore.Client(project="gestao-hermes").collection("system").document("api_keys").get().to_dict() or {}
    if not doc.get("elevenlabs_api_key"):
        raise SystemExit("Sem elevenlabs_api_key em system/api_keys.")
    return doc["elevenlabs_api_key"]


def gerar(api_key: str, texto: str, segundos: float) -> bytes:
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128",
        data=json.dumps({"text": texto, "duration_seconds": segundos, "prompt_influence": 0.6}).encode(),
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    refazer = set(sys.argv[sys.argv.index("--refazer") + 1].split(",")) if "--refazer" in sys.argv else set()
    PASTA.mkdir(parents=True, exist_ok=True)
    api_key = chave()
    for nome, (texto, seg) in SONS.items():
        arq = PASTA / f"{nome}.mp3"
        if arq.exists() and nome not in refazer:
            continue
        arq.write_bytes(gerar(api_key, texto, seg))
        print(f"{nome}: {arq.stat().st_size // 1024} KB", flush=True)


if __name__ == "__main__":
    main()
