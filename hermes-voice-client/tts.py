"""Text-to-speech local via Piper. Sintetiza frase a frase (para o primeiro
audio comecar a tocar o quanto antes) e devolve PCM16 + sample rate.

Na primeira execucao baixa automaticamente o modelo de voz configurado
(PIPER_VOICE) para PIPER_VOICE_DIR — é um download unico de algumas dezenas
de MB, requer internet nessa primeira vez.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from piper import PiperVoice
from piper.download_voices import download_voice

_voice: PiperVoice | None = None


def _voice_dir() -> Path:
    configured = os.environ.get("PIPER_VOICE_DIR", str(Path(__file__).parent / "voices"))
    directory = Path(configured)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _get_voice() -> PiperVoice:
    global _voice
    if _voice is not None:
        return _voice

    voice_name = os.environ.get("PIPER_VOICE", "pt_BR-faber-medium")
    voice_dir = _voice_dir()
    model_path = voice_dir / f"{voice_name}.onnx"
    config_path = voice_dir / f"{voice_name}.onnx.json"

    if not model_path.exists() or not config_path.exists():
        print(f"[tts] Baixando voz Piper '{voice_name}' em {voice_dir} (1a execucao)...")
        download_voice(voice_name, voice_dir)
        print("[tts] Download concluido.")

    use_cuda = os.environ.get("PIPER_USE_CUDA", "false").strip().lower() in ("1", "true", "yes")
    _voice = PiperVoice.load(model_path, config_path, use_cuda=use_cuda)
    return _voice


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def synthesize_sentence(text: str) -> tuple[bytes, int]:
    """Retorna (pcm16_bytes, sample_rate); (b"", 0) se o texto for vazio."""
    text = (text or "").strip()
    if not text:
        return b"", 0

    voice = _get_voice()
    chunks = list(voice.synthesize(text))
    if not chunks:
        return b"", 0

    sample_rate = chunks[0].sample_rate
    pcm = b"".join(chunk.audio_int16_bytes for chunk in chunks)
    return pcm, sample_rate
