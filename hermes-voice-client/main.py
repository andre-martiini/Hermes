"""Cliente de voz local do Hermes — servidor FastAPI que serve a UI (forma de
onda + chat) em localhost e faz a ponte entre o navegador (audio/texto) e o
orquestrador local (STT -> Gemini + MCP -> TTS).

Rodar com: uvicorn main:app --port 8765
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Precisa rodar antes de importar stt/tts/orchestrator: esses modulos (ou
# modulos que eles importam) leem variaveis de ambiente na primeira vez que
# sao usados, e orchestrator.py tem uma leitura em nivel de modulo
# (GEMINI_MODEL) que so ve o .env se ele ja tiver sido carregado.
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import stt
import tts
from orchestrator import VoiceSession

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Hermes Voice Client")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Audio minimo considerado valido (~0.15s a 16kHz/16bit mono) — evita mandar
# ruido de clique curto do push-to-talk para o whisper.
_MIN_UTTERANCE_BYTES = 4800

# O servidor so escuta em loopback, mas WebSocket nao segue same-origin policy:
# qualquer aba aberta no navegador do usuario pode tentar abrir
# ws://127.0.0.1:<porta>/ws e usar o refresh token guardado no keyring para
# falar com o MCP do Hermes. Rejeitamos handshakes cuja Origin nao seja a
# propria UI local servida por este processo.
def _allowed_ws_origins() -> set[str]:
    port = os.environ.get("PORT", "8765")
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin not in _allowed_ws_origins():
        await websocket.close(code=1008)
        return

    await websocket.accept()

    gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_api_key:
        await websocket.send_json({
            "type": "error",
            "message": "GEMINI_API_KEY nao configurada no .env local do hermes-voice-client.",
        })
        await websocket.close(code=1011)
        return

    loop = asyncio.get_event_loop()

    def status_cb(message: str) -> None:
        async def _send() -> None:
            try:
                await websocket.send_json({"type": "status", "message": message})
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(_send(), loop)

    session = VoiceSession(gemini_api_key=gemini_api_key, status_cb=status_cb)

    recording_buffer = bytearray()
    is_recording = False

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            text_payload = message.get("text")
            if text_payload is not None:
                try:
                    payload = json.loads(text_payload)
                except ValueError:
                    continue

                msg_type = payload.get("type")
                if msg_type == "mic_start":
                    recording_buffer = bytearray()
                    is_recording = True
                elif msg_type == "mic_stop":
                    is_recording = False
                    pcm_bytes = bytes(recording_buffer)
                    recording_buffer = bytearray()
                    await _handle_utterance_audio(websocket, session, loop, pcm_bytes)
                elif msg_type == "text_message":
                    text = str(payload.get("text") or "").strip()
                    if text:
                        await _handle_utterance_text(websocket, session, loop, text)

            bytes_payload = message.get("bytes")
            if bytes_payload is not None and is_recording:
                recording_buffer.extend(bytes_payload)

    except WebSocketDisconnect:
        pass


async def _handle_utterance_audio(websocket: WebSocket, session: VoiceSession, loop, pcm_bytes: bytes) -> None:
    if len(pcm_bytes) < _MIN_UTTERANCE_BYTES:
        await websocket.send_json({"type": "status", "message": "Audio muito curto, ignorado."})
        return

    await websocket.send_json({"type": "status", "message": "Transcrevendo..."})
    try:
        text = await loop.run_in_executor(None, stt.transcribe_pcm16, pcm_bytes)
    except Exception as exc:  # noqa: BLE001
        await websocket.send_json({"type": "error", "message": f"Falha na transcricao: {exc}"})
        return

    if not text:
        await websocket.send_json({"type": "status", "message": "Nao entendi, tente novamente."})
        return

    await websocket.send_json({"type": "user_transcript", "text": text})
    await _handle_utterance_text(websocket, session, loop, text)


async def _handle_utterance_text(websocket: WebSocket, session: VoiceSession, loop, text: str) -> None:
    try:
        response_text = await loop.run_in_executor(None, session.handle_user_text, text)
    except Exception as exc:  # noqa: BLE001
        await websocket.send_json({"type": "error", "message": f"Falha ao processar: {exc}"})
        return

    response_text = response_text or "Nao consegui gerar uma resposta agora."
    await websocket.send_json({"type": "assistant_text", "text": response_text})
    await _speak(websocket, loop, response_text)


async def _speak(websocket: WebSocket, loop, text: str) -> None:
    sentences = tts.split_sentences(text)
    if not sentences:
        return

    for sentence in sentences:
        try:
            pcm_bytes, sample_rate = await loop.run_in_executor(None, tts.synthesize_sentence, sentence)
        except Exception as exc:  # noqa: BLE001
            print(f"[main] Falha na sintese de voz: {exc}")
            continue
        if not pcm_bytes:
            continue
        await websocket.send_json({"type": "assistant_audio_start", "sampleRate": sample_rate})
        await websocket.send_bytes(pcm_bytes)

    await websocket.send_json({"type": "assistant_audio_end"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8765")), reload=False)
