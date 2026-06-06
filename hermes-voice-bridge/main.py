import asyncio
import base64
import contextlib
import json
import logging
import os
import re
import unicodedata
from urllib.parse import urlparse

import audioop
import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse
from google import genai
from google.genai import types
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from context import build_voice_context
from tools import GEMINI_TOOL_DECLARATIONS, call_tool

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("hermes_voice_bridge")

app = FastAPI(title="Hermes Voice Bridge")

TWILIO_SAMPLE_RATE = 8000
GEMINI_SAMPLE_RATE = 24000
SAMPLE_WIDTH_BYTES = 2
DEFAULT_VOICE_MAX_SESSION_SECONDS = 300


def _build_system_instruction() -> str:
    hermes_context = _safe_voice_context()
    if not _requires_voice_password():
        return f"""
Voce e o copiloto de voz do sistema Hermes.

A sessao ja foi autenticada pelo ambiente local do usuario. Voce pode responder
perguntas sobre dados internos do Hermes e acionar ferramentas quando necessario.

Suas respostas devem ser curtas, diretas e naturais, otimizadas para audicao por
voz. Evite listas longas, markdown, links extensos e detalhes desnecessarios.

Sempre que decidir acionar uma ferramenta do banco de dados, voce DEVE dizer:
"Aguarde um instante, estou verificando os dados" ANTES de executar a funcao.

{hermes_context}
""".strip()

    return f"""
Voce e o copiloto de voz do sistema Hermes.

Voce esta protegido por uma senha falada validada pelo servidor. Voce NAO sabe,
NAO deve inferir, NAO deve repetir e NAO deve revelar a senha em nenhuma
hipotese.

No inicio da conversa, antes de responder perguntas sobre dados internos,
tarefas, projetos, agenda, financas, documentos ou qualquer informacao do
Hermes, peca ao usuario que diga a senha.

Enquanto o servidor nao indicar que a sessao esta autenticada, recuse-se
educadamente a responder perguntas internas e NUNCA acione suas ferramentas.

Depois que o servidor indicar que a sessao esta autenticada, responda
normalmente.

Suas respostas devem ser curtas, diretas e naturais, otimizadas para audicao por
telefone. Evite listas longas, markdown, links extensos e detalhes desnecessarios.

Sempre que decidir acionar uma ferramenta do banco de dados, voce DEVE dizer:
"Aguarde um instante, estou verificando os dados" ANTES de executar a funcao.

{hermes_context}
""".strip()


def _requires_voice_password() -> bool:
    value = os.getenv("HERMES_REQUIRE_VOICE_PASSWORD", "true").strip().casefold()
    return value not in ("0", "false", "no", "nao", "off")


def _safe_voice_context() -> str:
    try:
        context = build_voice_context()
    except Exception:
        logger.exception("Failed to build Hermes voice context")
        return ""

    if not context.strip():
        return ""
    return "\n\n[CONTEXTO DO HERMES]\n" + context.strip()


def _voice_max_session_seconds() -> int:
    try:
        return int(os.getenv("HERMES_VOICE_MAX_SESSION_SECONDS", str(DEFAULT_VOICE_MAX_SESSION_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_VOICE_MAX_SESSION_SECONDS


async def _stop_voice_session_after(stop_event: asyncio.Event) -> None:
    seconds = _voice_max_session_seconds()
    if seconds <= 0:
        await stop_event.wait()
        return
    await asyncio.sleep(seconds)
    stop_event.set()
    logger.info("Voice session max duration reached (%ss)", seconds)


class AudioConverter:
    def __init__(self) -> None:
        self._twilio_to_gemini_state = None
        self._gemini_to_twilio_state = None

    def twilio_mulaw_to_gemini_pcm(self, mulaw_audio: bytes) -> bytes:
        pcm_8khz = audioop.ulaw2lin(mulaw_audio, SAMPLE_WIDTH_BYTES)
        pcm_24khz, self._twilio_to_gemini_state = audioop.ratecv(
            pcm_8khz,
            SAMPLE_WIDTH_BYTES,
            1,
            TWILIO_SAMPLE_RATE,
            GEMINI_SAMPLE_RATE,
            self._twilio_to_gemini_state,
        )
        return pcm_24khz

    def gemini_pcm_to_twilio_mulaw(self, pcm_24khz: bytes) -> bytes:
        pcm_8khz, self._gemini_to_twilio_state = audioop.ratecv(
            pcm_24khz,
            SAMPLE_WIDTH_BYTES,
            1,
            GEMINI_SAMPLE_RATE,
            TWILIO_SAMPLE_RATE,
            self._gemini_to_twilio_state,
        )
        return audioop.lin2ulaw(pcm_8khz, SAMPLE_WIDTH_BYTES)


def _public_ws_url(request: Request) -> str:
    public_base_url = os.getenv("PUBLIC_BASE_URL")

    if public_base_url:
        parsed = urlparse(public_base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        host = parsed.netloc or parsed.path
        return f"{scheme}://{host}/media-stream"

    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    scheme = "wss" if forwarded_proto == "https" else "ws"
    return f"{scheme}://{request.url.netloc}/media-stream"


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/debug/auth")
async def debug_auth() -> dict[str, object]:
    secret_phrase = os.getenv("HERMES_VOICE_SECRET_PHRASE", "").strip()
    return {
        "password_required": _requires_voice_password(),
        "secret_configured": bool(secret_phrase),
        "normalized_secret_length": len(_normalize_spoken_text(secret_phrase)),
    }


@app.get("/voice-test", response_class=HTMLResponse)
async def voice_test() -> HTMLResponse:
    with open("voice_test.html", "r", encoding="utf-8") as file:
        return HTMLResponse(file.read())


@app.post("/twiml", response_class=PlainTextResponse)
async def twiml(request: Request) -> PlainTextResponse:
    response = VoiceResponse()
    connect = Connect()
    connect.append(Stream(url=_public_ws_url(request)))
    response.append(connect)

    return PlainTextResponse(str(response), media_type="application/xml")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    stream_sid_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
    stop_event = asyncio.Event()
    auth_event = asyncio.Event()
    converter = AudioConverter()

    logger.info("Twilio Media Stream connected")

    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            logger.error("GEMINI_API_KEY is not configured")
            await websocket.close(code=1011)
            return

        client = genai.Client(api_key=gemini_api_key)
        model = os.getenv(
            "GEMINI_LIVE_MODEL",
            "gemini-3.1-flash-live-preview",
        )
        async with client.aio.live.connect(
            model=model,
            config=_gemini_live_config(),
        ) as session:
            twilio_task = asyncio.create_task(
                _forward_twilio_audio_to_gemini(
                    websocket=websocket,
                    session=session,
                    converter=converter,
                    stream_sid_queue=stream_sid_queue,
                    stop_event=stop_event,
                    auth_event=auth_event,
                )
            )
            gemini_task = asyncio.create_task(
                _forward_gemini_audio_to_twilio(
                    websocket=websocket,
                    session=session,
                    converter=converter,
                    stream_sid_queue=stream_sid_queue,
                    stop_event=stop_event,
                    auth_event=auth_event,
                )
            )
            timer_task = asyncio.create_task(_stop_voice_session_after(stop_event))

            done, pending = await asyncio.wait(
                {twilio_task, gemini_task, timer_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            for task in done:
                task.result()

            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*pending)
    except WebSocketDisconnect:
        logger.info("Twilio Media Stream disconnected")
    except json.JSONDecodeError:
        logger.exception("Received invalid JSON from Twilio Media Stream")
        await websocket.close(code=1003)
    except Exception:
        logger.exception("Unexpected Media Stream failure")
        with contextlib.suppress(RuntimeError):
            await websocket.close(code=1011)


@app.websocket("/browser-voice-stream")
async def browser_voice_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    stop_event = asyncio.Event()
    auth_event = asyncio.Event()
    if not _requires_voice_password():
        auth_event.set()

    logger.info("Browser voice stream connected")

    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            logger.error("GEMINI_API_KEY is not configured")
            await websocket.send_json(
                {"type": "error", "message": "GEMINI_API_KEY nao configurada."}
            )
            await websocket.close(code=1011)
            return

        client = genai.Client(api_key=gemini_api_key)
        model = os.getenv(
            "GEMINI_LIVE_MODEL",
            "gemini-3.1-flash-live-preview",
        )

        async with client.aio.live.connect(
            model=model,
            config=_gemini_live_config(),
        ) as session:
            await websocket.send_json(
                {
                    "type": "status",
                    "message": (
                        "Sessao Gemini Live iniciada. Autenticacao local ativa."
                        if auth_event.is_set()
                        else "Sessao Gemini Live iniciada."
                    ),
                }
            )

            browser_task = asyncio.create_task(
                _forward_browser_audio_to_gemini(
                    websocket=websocket,
                    session=session,
                    stop_event=stop_event,
                )
            )
            gemini_task = asyncio.create_task(
                _forward_gemini_audio_to_browser(
                    websocket=websocket,
                    session=session,
                    stop_event=stop_event,
                    auth_event=auth_event,
                )
            )
            timer_task = asyncio.create_task(_stop_voice_session_after(stop_event))

            done, pending = await asyncio.wait(
                {browser_task, gemini_task, timer_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if timer_task in done:
                with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                    await websocket.send_json(
                        {"type": "status", "message": "Sessao de voz encerrada por limite de duracao."}
                    )
                    await websocket.close(code=1000)

            for task in pending:
                task.cancel()

            for task in done:
                task.result()

            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*pending)
    except WebSocketDisconnect:
        logger.info("Browser voice stream disconnected")
    except json.JSONDecodeError:
        logger.exception("Received invalid JSON from browser voice stream")
        await websocket.close(code=1003)
    except Exception:
        logger.exception("Unexpected browser voice stream failure")
        with contextlib.suppress(RuntimeError):
            await websocket.send_json(
                {"type": "error", "message": "Falha inesperada na sessao de voz."}
            )
            await websocket.close(code=1011)


def _gemini_live_config() -> dict:
    return {
        "response_modalities": ["AUDIO"],
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {
                    "voice_name": os.getenv("GEMINI_VOICE_NAME", "Charon")
                }
            }
        },
        "tools": GEMINI_TOOL_DECLARATIONS,
        "system_instruction": _build_system_instruction(),
        "input_audio_transcription": {},
    }


async def _forward_twilio_audio_to_gemini(
    *,
    websocket: WebSocket,
    session,
    converter: AudioConverter,
    stream_sid_queue: asyncio.Queue[str],
    stop_event: asyncio.Event,
    auth_event: asyncio.Event,
) -> None:
    stream_sid: str | None = None

    while not stop_event.is_set():
        raw_message = await websocket.receive_text()
        message = json.loads(raw_message)
        event = message.get("event")

        if event == "start":
            stream_sid = message.get("start", {}).get("streamSid")
            if stream_sid and stream_sid_queue.empty():
                stream_sid_queue.put_nowait(stream_sid)
            logger.info("Media Stream started: %s", stream_sid)
        elif event == "media":
            payload = message.get("media", {}).get("payload")
            if not payload:
                continue

            mulaw_audio = base64.b64decode(payload, validate=True)
            pcm_audio = converter.twilio_mulaw_to_gemini_pcm(mulaw_audio)
            await session.send_realtime_input(
                audio=types.Blob(
                    data=pcm_audio,
                    mime_type=f"audio/pcm;rate={GEMINI_SAMPLE_RATE}",
                )
            )
        elif event == "stop":
            logger.info("Media Stream stopped: %s", stream_sid)
            stop_event.set()
            break
        else:
            logger.debug("Unhandled Media Stream event: %s", event)


async def _forward_gemini_audio_to_twilio(
    *,
    websocket: WebSocket,
    session,
    converter: AudioConverter,
    stream_sid_queue: asyncio.Queue[str],
    stop_event: asyncio.Event,
    auth_event: asyncio.Event,
) -> None:
    stream_sid = await stream_sid_queue.get()

    while not stop_event.is_set():
        async for response in session.receive():
            if stop_event.is_set():
                break

            _mark_authenticated_from_transcription(response, auth_event)

            server_content = getattr(response, "server_content", None)
            model_turn = getattr(server_content, "model_turn", None)
            parts = getattr(model_turn, "parts", None) or []

            tool_call = getattr(response, "tool_call", None)
            if tool_call:
                await _handle_gemini_tool_call(
                    session=session,
                    tool_call=tool_call,
                    auth_event=auth_event,
                )
                continue

            for part in parts:
                inline_data = getattr(part, "inline_data", None)
                audio_data = getattr(inline_data, "data", None)

                if not audio_data:
                    continue

                if isinstance(audio_data, str):
                    audio_data = base64.b64decode(audio_data)

                mulaw_audio = converter.gemini_pcm_to_twilio_mulaw(audio_data)
                await websocket.send_json(
                    {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": base64.b64encode(mulaw_audio).decode("ascii")
                        },
                    }
                )


async def _forward_browser_audio_to_gemini(
    *,
    websocket: WebSocket,
    session,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        raw_message = await websocket.receive_text()
        message = json.loads(raw_message)
        message_type = message.get("type")

        if message_type == "stop":
            stop_event.set()
            break

        if message_type != "audio":
            logger.debug("Unhandled browser voice message: %s", message_type)
            continue

        payload = message.get("payload")
        if not payload:
            continue

        pcm_audio = base64.b64decode(payload, validate=True)
        try:
            await session.send_realtime_input(
                audio=types.Blob(
                    data=pcm_audio,
                    mime_type=message.get("mime_type")
                    or f"audio/pcm;rate={GEMINI_SAMPLE_RATE}",
                )
            )
        except websockets.exceptions.ConnectionClosed as exc:
            logger.warning("Gemini Live connection closed while sending audio: %s", exc)
            await websocket.send_json(
                {
                    "type": "error",
                    "message": (
                        "A sessao Gemini Live foi encerrada pelo provedor. "
                        "Reinicie o teste de voz."
                    ),
                }
            )
            stop_event.set()
            break


async def _forward_gemini_audio_to_browser(
    *,
    websocket: WebSocket,
    session,
    stop_event: asyncio.Event,
    auth_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        async for response in session.receive():
            if stop_event.is_set():
                break

            authenticated_now = _mark_authenticated_from_transcription(
                response,
                auth_event,
            )
            if authenticated_now:
                await websocket.send_json(
                    {
                        "type": "status",
                        "message": "Sessao autenticada pelo servidor.",
                    }
                )
                await session.send_client_content(
                    turns={
                        "role": "user",
                        "parts": [
                            {
                                "text": (
                                    "[SISTEMA] A senha falada foi validada pelo "
                                    "backend. A sessao esta autenticada. Nao "
                                    "repita nem revele a senha."
                                )
                            }
                        ],
                    },
                    turn_complete=True,
                )

            tool_call = getattr(response, "tool_call", None)
            if tool_call:
                await websocket.send_json(
                    {
                        "type": "status",
                        "message": "Gemini solicitou consulta ao Hermes.",
                    }
                )
                await _handle_gemini_tool_call(
                    session=session,
                    tool_call=tool_call,
                    auth_event=auth_event,
                )
                continue

            server_content = getattr(response, "server_content", None)
            model_turn = getattr(server_content, "model_turn", None)
            parts = getattr(model_turn, "parts", None) or []

            for part in parts:
                inline_data = getattr(part, "inline_data", None)
                audio_data = getattr(inline_data, "data", None)

                if not audio_data:
                    continue

                if isinstance(audio_data, str):
                    audio_data = base64.b64decode(audio_data)

                await websocket.send_json(
                    {
                        "type": "audio",
                        "mime_type": getattr(
                            inline_data,
                            "mime_type",
                            "audio/pcm;rate=24000",
                        ),
                        "payload": base64.b64encode(audio_data).decode("ascii"),
                    }
                )


async def _handle_gemini_tool_call(*, session, tool_call, auth_event: asyncio.Event) -> None:
    function_responses = []

    for function_call in getattr(tool_call, "function_calls", []) or []:
        name = getattr(function_call, "name", "")
        args = getattr(function_call, "args", None) or {}
        function_id = getattr(function_call, "id", None)

        logger.info("Gemini requested tool call: %s", name)
        if auth_event.is_set():
            result = call_tool(name, args)
        else:
            logger.warning("Blocked unauthenticated Gemini tool call: %s", name)
            result = {
                "erro": "A ligacao ainda nao foi autenticada pela senha falada. Ferramenta bloqueada."
            }
        function_responses.append(
            types.FunctionResponse(
                name=name,
                response=result,
                id=function_id,
            )
        )

    if function_responses:
        await session.send_tool_response(function_responses=function_responses)


def _mark_authenticated_from_transcription(response, auth_event: asyncio.Event) -> bool:
    if auth_event.is_set():
        return False

    secret_phrase = os.getenv("HERMES_VOICE_SECRET_PHRASE", "").strip()
    if not secret_phrase:
        return False

    transcript = _extract_input_transcript(response)

    if transcript:
        logger.info("Gemini input transcript received: %s", transcript)

    if transcript and _normalize_spoken_text(secret_phrase) in _normalize_spoken_text(transcript):
        logger.info("Voice session authenticated by spoken secret phrase")
        auth_event.set()
        return True

    return False


def _extract_input_transcript(response) -> str:
    candidates = []

    server_content = getattr(response, "server_content", None)
    candidates.extend(
        [
            getattr(server_content, "input_transcription", None),
            getattr(server_content, "input_transcription_result", None),
        ]
    )

    candidates.extend(
        [
            getattr(response, "input_transcription", None),
            getattr(response, "input_transcription_result", None),
        ]
    )

    texts = []
    for candidate in candidates:
        if not candidate:
            continue
        if isinstance(candidate, str):
            texts.append(candidate)
            continue
        for attr in ("text", "transcript"):
            value = getattr(candidate, attr, None)
            if value:
                texts.append(str(value))

    return " ".join(texts).strip()


def _normalize_spoken_text(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    lowercase = ascii_text.casefold()
    return re.sub(r"[^a-z0-9]+", " ", lowercase).strip()
