import asyncio
import base64
import contextlib
import json
import logging
import os
import re
import time
import unicodedata
from urllib.parse import urlparse

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import audioop
import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse
from google import genai
from google.genai import types
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

import hermes_mcp
import task_tools
from context import build_voice_context
from database import BrowserAuthError, verify_browser_id_token
from tools import GEMINI_TOOL_DECLARATIONS, UI_TOOL_NAMES, call_tool

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("hermes_voice_bridge")

app = FastAPI(title="Hermes Voice Bridge")

LOCAL_TZ = ZoneInfo(os.getenv("HERMES_TIMEZONE", "America/Sao_Paulo"))
_WEEKDAY_NAMES_PT = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]

TWILIO_SAMPLE_RATE = 8000
GEMINI_SAMPLE_RATE = 24000
SAMPLE_WIDTH_BYTES = 2
DEFAULT_VOICE_MAX_SESSION_SECONDS = 300


def _data_context_block() -> str:
    # Calculado em Python (nunca confie no modelo para aritmetica de
    # calendario/dia-da-semana — ele erra "segunda-feira e dia X" com
    # frequencia). Da uma tabela pronta dos proximos 7 dias para ele so
    # copiar a data correspondente ao dia da semana pedido pelo usuario.
    now = datetime.now(LOCAL_TZ)
    lines = [
        "## DATA E HORA ATUAIS (fonte de verdade — NUNCA calcule dia da semana de cabeca, so copie desta tabela)",
        f"- agora: {_WEEKDAY_NAMES_PT[now.weekday()]}, {now.strftime('%Y-%m-%d %H:%M')} ({LOCAL_TZ.key})",
    ]
    for offset in range(0, 8):
        day = now + timedelta(days=offset)
        weekday_name = _WEEKDAY_NAMES_PT[day.weekday()]
        prefix = "hoje, " if offset == 0 else "amanha, " if offset == 1 else ""
        lines.append(f"- {prefix}{weekday_name}: {day.strftime('%Y-%m-%d')}")
    return "\n".join(lines)


def _build_system_instruction() -> str:
    data_context = _data_context_block()
    hermes_context = _safe_voice_context()
    if not _requires_voice_password():
        return f"""
Voce e o copiloto de voz do sistema Hermes.

A sessao ja foi autenticada pelo ambiente local do usuario. Voce pode responder
perguntas sobre dados internos do Hermes e acionar ferramentas quando necessario.

Suas respostas devem ser curtas, diretas e naturais, otimizadas para audicao por
voz. Evite listas longas, markdown, links extensos e detalhes desnecessarios.

Para perguntas sobre tarefas/acoes em uma data especifica (hoje, amanha,
atrasadas, ou um periodo entre datas), SEMPRE prefira as ferramentas exatas
buscar_tarefas_pendentes_hoje, buscar_tarefas_amanha, buscar_tarefas_atrasadas
ou buscar_tarefas_por_periodo — elas filtram pela data_limite exata no banco e
sao a fonte de verdade para contagem. NAO use consultar_historico_acoes (busca
por texto aproximado) para contar ou listar tarefas de uma data: ela e uma
busca fuzzy e pode retornar resultados incompletos, levando a contagens
erradas. Use consultar_historico_acoes so quando a pergunta for sobre um termo,
assunto ou numero de processo, nao sobre uma data.

Quando o usuario mencionar um dia da semana (segunda, terca, sexta que vem
etc.) para reagendar ou criar algo, SEMPRE traduza para a data YYYY-MM-DD
usando a tabela em "DATA E HORA ATUAIS" no topo deste prompt — nunca calcule
de cabeca.

Quando uma ferramenta de busca retornar o campo total_encontrado, use ESSE
numero ao dizer quantas tarefas existem — a lista 'tarefas' pode vir cortada
pelo limite (nesse caso truncado=true).

Ao listar tarefas em voz alta, use SOMENTE os titulos exatos presentes na
lista 'tarefas' da resposta da ferramenta mais recente. NUNCA misture com
tarefas de uma pergunta anterior, NUNCA complete a lista de memoria e NUNCA
cite uma tarefa que voce nao tem certeza absoluta que veio da resposta da
ferramenta desta chamada especifica. Se a lista vier vazia, diga que nao ha
tarefas — nao invente nenhuma.

Sempre que decidir acionar uma ferramenta do banco de dados, voce DEVE dizer:
"Aguarde um instante, estou verificando os dados" ANTES de executar a funcao.

NUNCA diga que uma acao foi feita (salva, alterada, reagendada, adiada,
concluida, registrada) sem ter chamado a ferramenta correspondente e recebido
de volta um resultado de sucesso (status "ok", sem campo "erro"). Se a
ferramenta retornar erro, informe o erro ao usuario em vez de fingir que deu
certo. Se nao existir ferramenta para o que o usuario pediu, diga claramente
que voce nao consegue fazer isso agora.

{data_context}

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

Para perguntas sobre tarefas/acoes em uma data especifica (hoje, amanha,
atrasadas, ou um periodo entre datas), SEMPRE prefira as ferramentas exatas
buscar_tarefas_pendentes_hoje, buscar_tarefas_amanha, buscar_tarefas_atrasadas
ou buscar_tarefas_por_periodo — elas filtram pela data_limite exata no banco e
sao a fonte de verdade para contagem. NAO use consultar_historico_acoes (busca
por texto aproximado) para contar ou listar tarefas de uma data: ela e uma
busca fuzzy e pode retornar resultados incompletos, levando a contagens
erradas. Use consultar_historico_acoes so quando a pergunta for sobre um termo,
assunto ou numero de processo, nao sobre uma data.

Quando o usuario mencionar um dia da semana (segunda, terca, sexta que vem
etc.) para reagendar ou criar algo, SEMPRE traduza para a data YYYY-MM-DD
usando a tabela em "DATA E HORA ATUAIS" no topo deste prompt — nunca calcule
de cabeca.

Quando uma ferramenta de busca retornar o campo total_encontrado, use ESSE
numero ao dizer quantas tarefas existem — a lista 'tarefas' pode vir cortada
pelo limite (nesse caso truncado=true).

Ao listar tarefas em voz alta, use SOMENTE os titulos exatos presentes na
lista 'tarefas' da resposta da ferramenta mais recente. NUNCA misture com
tarefas de uma pergunta anterior, NUNCA complete a lista de memoria e NUNCA
cite uma tarefa que voce nao tem certeza absoluta que veio da resposta da
ferramenta desta chamada especifica. Se a lista vier vazia, diga que nao ha
tarefas — nao invente nenhuma.

Sempre que decidir acionar uma ferramenta do banco de dados, voce DEVE dizer:
"Aguarde um instante, estou verificando os dados" ANTES de executar a funcao.

NUNCA diga que uma acao foi feita (salva, alterada, reagendada, adiada,
concluida, registrada) sem ter chamado a ferramenta correspondente e recebido
de volta um resultado de sucesso (status "ok", sem campo "erro"). Se a
ferramenta retornar erro, informe o erro ao usuario em vez de fingir que deu
certo. Se nao existir ferramenta para o que o usuario pediu, diga claramente
que voce nao consegue fazer isso agora.

{data_context}

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
        configured = int(os.getenv("HERMES_VOICE_MAX_SESSION_SECONDS", str(DEFAULT_VOICE_MAX_SESSION_SECONDS)))
    except (TypeError, ValueError):
        configured = DEFAULT_VOICE_MAX_SESSION_SECONDS
    # O Gemini Live tambem impoe um limite de duracao do lado do provedor (por
    # volta de 15 min sem session resumption) e manda um GoAway pouco antes de
    # fechar a conexao a força. Se o nosso timer local disparar exatamente no
    # mesmo instante (ou depois), o servidor as vezes vence a corrida e a
    # sessao morre com uma excecao feia em vez do encerramento gracioso normal.
    # Uma margem de seguranca garante que SEMPRE fechamos primeiro.
    return max(60, configured - 60)


async def _stop_voice_session_after(stop_event: asyncio.Event) -> None:
    seconds = _voice_max_session_seconds()
    if seconds <= 0:
        await stop_event.wait()
        return
    await asyncio.sleep(seconds)
    stop_event.set()
    logger.info("Voice session max duration reached (%ss)", seconds)


def _voice_max_idle_seconds() -> int:
    try:
        return int(os.getenv("HERMES_VOICE_MAX_IDLE_SECONDS", "90"))
    except (TypeError, ValueError):
        return 90


def _allowed_browser_origins() -> set[str]:
    raw = os.getenv("HERMES_VOICE_ALLOWED_ORIGINS", "").strip()
    origins = {o.strip() for o in raw.split(",") if o.strip()}
    origins.update(
        {
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:5175",
            "http://127.0.0.1:5175",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://localhost:8765",
            "http://127.0.0.1:8765",
            "https://gestao-hermes.web.app",
            "https://gestao-hermes.firebaseapp.com",
        }
    )
    return origins


def _is_local_origin(origin: str | None) -> bool:
    return bool(origin) and (
        origin.startswith("http://localhost:")
        or origin.startswith("http://127.0.0.1:")
        or origin.startswith("https://localhost:")
        or origin.startswith("https://127.0.0.1:")
    )


class _ActivityTracker:
    """Marca a ultima vez que houve audio indo ou vindo, para o watchdog de
    inatividade poder encerrar sessoes esquecidas com o microfone aberto."""

    def __init__(self) -> None:
        self.last = time.monotonic()

    def touch(self) -> None:
        self.last = time.monotonic()


async def _stop_voice_session_after_idle(activity: "_ActivityTracker", stop_event: asyncio.Event) -> None:
    idle_limit = _voice_max_idle_seconds()
    if idle_limit <= 0:
        await stop_event.wait()
        return
    while not stop_event.is_set():
        await asyncio.sleep(5)
        if stop_event.is_set():
            return
        if time.monotonic() - activity.last >= idle_limit:
            stop_event.set()
            logger.info("Voice session idle timeout reached (%ss)", idle_limit)
            return


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
    origin = websocket.headers.get("origin")
    if origin not in _allowed_browser_origins() and not _is_local_origin(origin):
        logger.warning("Rejected browser voice stream from disallowed origin: %s", origin)
        await websocket.close(code=1008)
        return

    await websocket.accept()
    stop_event = asyncio.Event()
    activity = _ActivityTracker()

    logger.info("Browser voice stream connected")

    try:
        # Handshake de autenticacao: a primeira mensagem PRECISA ser o Firebase
        # ID Token do usuario, validado contra a mesma whitelist do servidor
        # MCP (system/mcp_access.allowed_uids). So depois disso abrimos a sessao
        # Gemini Live — ela custa dinheiro por minuto, entao nao vale abrir
        # antes de saber que quem esta do outro lado tem permissao.
        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("Browser voice stream timed out waiting for auth message")
            await websocket.close(code=1008)
            return

        try:
            auth_message = json.loads(raw_auth)
        except json.JSONDecodeError:
            await websocket.close(code=1003)
            return

        id_token = (
            auth_message.get("id_token") or auth_message.get("token")
            if auth_message.get("type") == "auth"
            else None
        )
        if not id_token:
            await websocket.send_json(
                {"type": "error", "message": "Primeira mensagem deve ser {type: 'auth', id_token: ...}."}
            )
            await websocket.close(code=1008)
            return

        try:
            uid = verify_browser_id_token(id_token)
        except BrowserAuthError as exc:
            logger.warning("Browser voice stream auth failed: %s", exc)
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=1008)
            return

        logger.info("Browser voice stream authenticated for uid=%s", uid)
        auth_event = asyncio.Event()
        auth_event.set()  # autenticacao ja resolvida via Firebase ID Token, nao por senha falada

        # Sessao pode nascer dentro de uma acao (drawer do copiloto): o
        # frontend manda o task_id no handshake e a sessao ganha contexto e
        # ferramentas de escrita daquela acao.
        session_task_id = str(auth_message.get("task_id") or "").strip() or None
        task_context = ""
        if session_task_id:
            try:
                task_context = await asyncio.to_thread(task_tools.build_task_context, session_task_id)
                logger.info("Voice session scoped to task %s", session_task_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao montar contexto da acao %s: %s", session_task_id, exc)

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            logger.error("GEMINI_API_KEY is not configured")
            await websocket.send_json(
                {"type": "error", "message": "GEMINI_API_KEY nao configurada."}
            )
            await websocket.close(code=1011)
            return

        # Tools auditadas do MCP + contexto do copiloto, com o token do proprio
        # usuario. Falha aqui nao derruba a sessao: segue so com as tools locais.
        mcp_declarations: list[dict] = []
        mcp_context = ""
        try:
            mcp_declarations = await asyncio.to_thread(hermes_mcp.list_tools, id_token)
            mcp_context = await asyncio.to_thread(hermes_mcp.read_voice_context, id_token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP indisponivel para a sessao de voz (%s); seguindo so com tools locais", exc)
        mcp_tool_names = hermes_mcp.tool_names(mcp_declarations)

        client = genai.Client(api_key=gemini_api_key)
        model = os.getenv(
            "GEMINI_LIVE_MODEL",
            "gemini-3.1-flash-live-preview",
        )

        async with client.aio.live.connect(
            model=model,
            config=_gemini_live_config(
                mcp_declarations + task_tools.TASK_TOOL_DECLARATIONS,
                (mcp_context + ("\n\n" + task_context if task_context else "")).strip(),
            ),
        ) as session:
            await websocket.send_json(
                {"type": "status", "message": "Sessao Gemini Live iniciada."}
            )

            browser_task = asyncio.create_task(
                _forward_browser_audio_to_gemini(
                    websocket=websocket,
                    session=session,
                    stop_event=stop_event,
                    activity=activity,
                )
            )
            gemini_task = asyncio.create_task(
                _forward_gemini_audio_to_browser(
                    websocket=websocket,
                    session=session,
                    stop_event=stop_event,
                    auth_event=auth_event,
                    activity=activity,
                    mcp_tool_names=mcp_tool_names,
                    id_token=id_token,
                    session_task_id=session_task_id,
                )
            )
            timer_task = asyncio.create_task(_stop_voice_session_after(stop_event))
            idle_task = asyncio.create_task(_stop_voice_session_after_idle(activity, stop_event))

            done, pending = await asyncio.wait(
                {browser_task, gemini_task, timer_task, idle_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if timer_task in done or idle_task in done:
                reason = "limite de duracao" if timer_task in done else "inatividade"
                with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                    await websocket.send_json(
                        {"type": "status", "message": f"Sessao de voz encerrada por {reason}."}
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
    except Exception as exc:
        logger.exception("Unexpected browser voice stream failure")
        # GoAway/1008 do provedor: a conversa foi encerrada pelo lado do Gemini
        # (limite de duracao) no meio de uma acao. As acoes ja confirmadas por
        # ferramentas ANTES do encerramento foram salvas normalmente — so a
        # resposta falada final e que pode ter sido cortada. Mensagem clara em
        # vez do "falha inesperada" generico, para nao parecer que nada salvou.
        is_goaway = "GoAway" in str(exc) or "1008" in str(exc)
        message = (
            "A sessao de voz atingiu o limite de duracao do provedor e foi encerrada. "
            "Acoes ja confirmadas antes disso foram salvas normalmente — reconecte para continuar."
            if is_goaway
            else "Falha inesperada na sessao de voz."
        )
        with contextlib.suppress(RuntimeError):
            await websocket.send_json({"type": "error", "message": message})
            await websocket.close(code=1011)


def _gemini_live_config(
    extra_declarations: list[dict] | None = None,
    extra_context: str = "",
) -> dict:
    # GEMINI_TOOL_DECLARATIONS e [{"function_declarations": [...]}]; as tools
    # extras (MCP) entram no mesmo bloco para o Gemini ver um catalogo unico.
    merged_declarations = list(GEMINI_TOOL_DECLARATIONS[0]["function_declarations"])
    if extra_declarations:
        merged_declarations.extend(extra_declarations)

    system_instruction = _build_system_instruction()
    if extra_context:
        system_instruction += "\n\n[CONTEXTO ADICIONAL DO COPILOTO]\n" + extra_context

    return {
        "response_modalities": ["AUDIO"],
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {
                    "voice_name": os.getenv("GEMINI_VOICE_NAME", "Charon")
                }
            },
            # Trava o idioma da sessao: sem isso a transcricao de entrada
            # ocasionalmente deriva para ingles ou degenera em repeticao.
            "language_code": os.getenv("GEMINI_VOICE_LANGUAGE", "pt-BR"),
        },
        "tools": [{"function_declarations": merged_declarations}],
        "system_instruction": system_instruction,
        "input_audio_transcription": {},
        "output_audio_transcription": {},
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
                    websocket=websocket,
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
    activity: "_ActivityTracker",
) -> None:
    while not stop_event.is_set():
        raw_message = await websocket.receive_text()
        message = json.loads(raw_message)
        message_type = message.get("type")

        if message_type == "stop":
            stop_event.set()
            break

        if message_type == "ui_context":
            ctx = message.get("context") or {}
            active_module = ctx.get("activeModule", "")
            view_mode = ctx.get("viewMode", "")
            selected_task = ctx.get("selectedTask")
            active_tool = ctx.get("activeFerramenta")

            context_lines = [
                f"[SISTEMA - TELA ATUAL DO USUÁRIO]: O usuário está navegando no Hermes (Módulo: '{active_module}', Visão: '{view_mode}')."
            ]

            if selected_task:
                task_details = [
                    f"AÇÃO/TAREFA ABERTA NA TELA DO USUÁRIO AGORA:\n"
                    f"- ID: {selected_task.get('id')}\n"
                    f"- Título: {selected_task.get('titulo')}\n"
                    f"- Área Temática: {selected_task.get('area_tematica')}\n"
                    f"- Status: {selected_task.get('status')}\n"
                    f"- Prioridade: {selected_task.get('prioridade')}\n"
                    f"- Prazo: {selected_task.get('data_limite')}\n"
                    f"- Responsável: {selected_task.get('responsavel')}\n"
                    f"- Processo SEI: {selected_task.get('processo_sei') or 'Nenhum'}\n"
                    f"- Descrição/Notas: {selected_task.get('descricao') or 'Sem descrição'}\n"
                    f"- Solução/Resumo: {selected_task.get('solucao_sugerida') or 'Sem resumo'}"
                ]

                pool_dados = selected_task.get("pool_dados") or []
                if pool_dados:
                    pool_items_str = "\n".join(
                        f"  * [{item.get('tipo', 'anexo')}] {item.get('nome')}: {item.get('valor')} "
                        f"{f'({item.get('resumo')})' if item.get('resumo') else ''}"
                        for item in pool_dados
                    )
                    task_details.append(f"ARQUIVOS, DOCUMENTOS E LINKS ANEXADOS À AÇÃO ({len(pool_dados)}):\n{pool_items_str}")

                plano_acao = selected_task.get("plano_acao") or []
                if plano_acao:
                    plano_str = "\n".join(
                        f"  * [{'X' if item.get('concluido') else ' '}] {item.get('item')} "
                        f"{f'(Resp: {item.get('responsavel')})' if item.get('responsavel') else ''}"
                        for item in plano_acao
                    )
                    task_details.append(f"PLANO DE AÇÃO E SUBTAREFAS ({len(plano_acao)} passos):\n{plano_str}")

                acompanhamento = selected_task.get("acompanhamento") or []
                if acompanhamento:
                    acomp_str = "\n".join(
                        f"  * [{item.get('data', '')}] {item.get('nota')} "
                        f"{f'({item.get('autor')})' if item.get('autor') else ''}"
                        for item in acompanhamento
                    )
                    task_details.append(f"HISTÓRICO DE ACOMPANHAMENTO RECENTE:\n{acomp_str}")

                context_lines.append("\n\n".join(task_details))
            elif active_tool:
                context_lines.append(f"FERRAMENTA ABERTA NA TELA AGORA: '{active_tool}'.")

            context_prompt = "\n\n".join(context_lines)
            logger.info("Updating Gemini Live UI context: module=%s, task=%s", active_module, selected_task.get('titulo') if selected_task else None)
            try:
                await session.send(input=context_prompt)
            except Exception as exc:
                logger.warning("Falha ao enviar ui_context para session: %s", exc)
            continue

        if message_type != "audio":
            logger.debug("Unhandled browser voice message: %s", message_type)
            continue

        payload = message.get("payload")
        if not payload:
            continue

        # Nao marca atividade aqui: com o mic continuamente aberto, cada frame
        # de audio (mesmo silencio) contaria como atividade e o watchdog de
        # inatividade nunca dispararia. Atividade real e medida no caminho de
        # retorno (transcricoes e respostas do Gemini).
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
    activity: "_ActivityTracker",
    mcp_tool_names: set[str] | None = None,
    id_token: str | None = None,
    session_task_id: str | None = None,
) -> None:
    # auth_event ja chega sempre "set" aqui — a autenticacao do canal navegador
    # acontece via Firebase ID Token antes da sessao Gemini Live ser aberta
    # (ver browser_voice_stream), diferente do canal Twilio que usa senha falada.
    #
    # session.receive() encerra a cada fim de turno (dai o while). Um ciclo que
    # termina SEM entregar nenhuma mensagem indica que a sessao Gemini morreu
    # do lado do provedor (limite interno de duracao, GoAway etc.) — sem essa
    # deteccao o loop giraria em vazio para sempre e o navegador ficaria com a
    # UI "ao vivo" porem muda.
    empty_cycles = 0
    while not stop_event.is_set():
        received_any = False
        async for response in session.receive():
            received_any = True
            if stop_event.is_set():
                break

            activity.touch()

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
                    mcp_tool_names=mcp_tool_names,
                    id_token=id_token,
                    session_task_id=session_task_id,
                    websocket=websocket,
                )
                continue

            input_transcript = _extract_input_transcript(response)
            if input_transcript:
                await websocket.send_json({"type": "input_transcript", "text": input_transcript})

            output_transcript = _extract_output_transcript(response)
            if output_transcript:
                await websocket.send_json({"type": "output_transcript", "text": output_transcript})

            server_content = getattr(response, "server_content", None)

            # Barge-in nativo do Gemini Live: o VAD do servidor detectou fala
            # real do usuario e interrompeu a geracao. Avisa o navegador para
            # descartar o audio ja enfileirado — e o unico corte de reproducao
            # confiavel (o corte local por energia de microfone foi removido
            # porque som de alto-falante vazando para o mic disparava falso).
            if bool(getattr(server_content, "interrupted", False)):
                await websocket.send_json({"type": "interrupted"})

            model_turn = getattr(server_content, "model_turn", None)
            parts = getattr(model_turn, "parts", None) or []

            turn_complete = bool(getattr(server_content, "turn_complete", False))
            if turn_complete:
                await websocket.send_json({"type": "turn_complete"})

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

        if received_any:
            empty_cycles = 0
        else:
            empty_cycles += 1
            if empty_cycles >= 3:
                logger.info("Gemini Live session ended upstream; closing browser voice stream")
                with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "A sessao de voz expirou do lado do provedor. Clique no botao de voz para reconectar.",
                        }
                    )
                stop_event.set()
                break
            await asyncio.sleep(0.2)


async def _handle_gemini_tool_call(
    *,
    session,
    tool_call,
    auth_event: asyncio.Event,
    mcp_tool_names: set[str] | None = None,
    id_token: str | None = None,
    session_task_id: str | None = None,
    websocket: WebSocket | None = None,
) -> None:
    function_responses = []
    mcp_tool_names = mcp_tool_names or set()

    for function_call in getattr(tool_call, "function_calls", []) or []:
        name = getattr(function_call, "name", "")
        args = getattr(function_call, "args", None) or {}
        function_id = getattr(function_call, "id", None)

        logger.info("Gemini requested tool call: %s", name)
        if not auth_event.is_set():
            logger.warning("Blocked unauthenticated Gemini tool call: %s", name)
            result = {
                "erro": "A ligacao ainda nao foi autenticada pela senha falada. Ferramenta bloqueada."
            }
        elif name in UI_TOOL_NAMES:
            if websocket:
                try:
                    await websocket.send_json({
                        "type": "ui_command",
                        "command": name,
                        "params": dict(args),
                    })
                except Exception as exc:
                    logger.warning("Falha ao enviar ui_command pelo websocket: %s", exc)
            result = {
                "status": "sucesso",
                "instrucao_resposta": "SILENCIO: O comando de navegacao foi executado com sucesso e a notificacao visual ja foi exibida na tela do usuario. NAO FALE NADA, NAO DIGA 'aguarde um instante' e NAO DIGA que esta navegando. Permaneca em silencio absoluto.",
                "mensagem": f"Comando de interface '{name}' executado silenciosamente.",
            }
        elif name in task_tools.TASK_TOOL_NAMES:
            # Tools de acao (diario, plano) — escrevem no Firestore; o task_id
            # da sessao entra como padrao quando o modelo nao informa um.
            result = await asyncio.to_thread(task_tools.call_task_tool, name, dict(args), session_task_id)
        elif name in mcp_tool_names and id_token:
            # Tool auditada do servidor MCP, executada com o token do usuario
            # da sessao (mantem audit log e whitelist do MCP). Em thread para
            # nao bloquear o streaming de audio durante a chamada HTTP.
            result = await asyncio.to_thread(hermes_mcp.call_tool, name, dict(args), id_token)
        else:
            result = await asyncio.to_thread(call_tool, name, dict(args))

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
    return _extract_transcript(response, "input_transcription")


def _extract_output_transcript(response) -> str:
    return _extract_transcript(response, "output_transcription")


def _extract_transcript(response, field: str) -> str:
    candidates = []

    server_content = getattr(response, "server_content", None)
    candidates.extend(
        [
            getattr(server_content, field, None),
            getattr(server_content, f"{field}_result", None),
        ]
    )

    candidates.extend(
        [
            getattr(response, field, None),
            getattr(response, f"{field}_result", None),
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
