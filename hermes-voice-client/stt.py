"""Speech-to-text local via faster-whisper. Recebe PCM16 mono 16kHz (o mesmo
formato que o navegador envia via WebSocket) e devolve o texto transcrito."""

from __future__ import annotations

import os

import numpy as np
from faster_whisper import WhisperModel

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        size = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
        device = os.environ.get("WHISPER_DEVICE", "auto")
        compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
        print(f"[stt] Carregando faster-whisper '{size}' (device={device}, compute_type={compute_type})...")
        _model = WhisperModel(size, device=device, compute_type=compute_type)
        print("[stt] Modelo carregado.")
    return _model


def transcribe_pcm16(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    if not pcm_bytes:
        return ""

    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _info = _get_model().transcribe(audio, language="pt", vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()
