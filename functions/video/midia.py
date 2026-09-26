"""Serviços de mídia da prévia: narração (TTS), quadro-chave (imagem), arquivos.

`Servicos` é a fronteira com o mundo pago/externo. A prévia (`previa.py`) só
conhece esta interface, e os testes usam `ServicosFalsos`, sem rede nem custo.

Decisões medidas (26/09/2026, Vertex AI):
- TTS `gemini-2.5-flash-tts` devolve PCM 16 bits mono 24 kHz (`audio/L16;rate=24000`)
  com ~0,27 s de silêncio no início e ~0,14 s no fim; o silêncio é aparado antes
  de medir, porque é a fala que precisa caber no clipe.
- A imagem de `gemini-2.5-flash-image` sai em 1344×768 para "16:9"; o Veo põe faixas
  pretas se o quadro não tiver a proporção exata, então todo quadro é recortado
  para 1280×720 (ou 720×1280) antes de ser gravado.
"""
from __future__ import annotations

import io
import re
import subprocess
import wave
from dataclasses import dataclass

TAMANHO_QUADRO = {"16:9": (1280, 720), "9:16": (720, 1280)}
LIMIAR_SILENCIO = 0.02  # fração do fundo de escala (RMS em janelas de 20 ms)
MARGEM_SILENCIO_S = 0.05


# --- áudio (puro) ---------------------------------------------------------------------

def taxa_do_mime(mime: str | None, padrao: int = 24000) -> int:
    m = re.search(r"rate=(\d+)", mime or "")
    return int(m.group(1)) if m else padrao


def duracao_pcm(pcm: bytes, taxa: int) -> float:
    return len(pcm) / (2 * taxa)


def aparar_silencio(pcm: bytes, taxa: int) -> bytes:
    """Corta o silêncio das pontas (mantém 50 ms de margem). PCM 16 bits mono."""
    import numpy as np

    pcm = pcm[: len(pcm) // 2 * 2]  # byte solto no fim quebraria o frombuffer de int16
    amostras = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if amostras.size == 0:
        return pcm
    janela = max(int(taxa * 0.02), 1)
    rms = np.sqrt(np.convolve(amostras ** 2, np.ones(janela) / janela, mode="same"))
    fala = np.where(rms > LIMIAR_SILENCIO * 32768)[0]
    if fala.size == 0:
        return b""
    margem = int(taxa * MARGEM_SILENCIO_S)
    ini = max(int(fala[0]) - margem, 0)
    fim = min(int(fala[-1]) + margem, amostras.size)
    return amostras[ini:fim].astype(np.int16).tobytes()


def silencio_pcm(segundos: float, taxa: int) -> bytes:
    return b"\x00\x00" * int(round(segundos * taxa))


def pcm_para_wav(pcm: bytes, taxa: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm)
    return buf.getvalue()


def wav_para_pcm(dados: bytes) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(dados)) as w:
        return w.readframes(w.getnframes()), w.getframerate()


def wav_para_mp3(dados_wav: bytes) -> bytes:
    """MP3 pelo ffmpeg empacotado no `imageio-ffmpeg` (já nas dependências das functions)."""
    import imageio_ffmpeg

    proc = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-f", "wav", "-i", "pipe:0",
         "-codec:a", "libmp3lame", "-q:a", "4", "-f", "mp3", "pipe:1"],
        input=dados_wav, capture_output=True, check=True,
    )
    return proc.stdout


# --- imagem (puro) --------------------------------------------------------------------

def recortar_quadro(png: bytes, formato: str) -> bytes:
    """Recorte central na proporção exata e redimensiona para 1280×720 / 720×1280."""
    from PIL import Image

    largura, altura = TAMANHO_QUADRO[formato]
    img = Image.open(io.BytesIO(png)).convert("RGB")
    alvo = largura / altura
    w, h = img.size
    if w / h > alvo:
        novo_w = round(h * alvo)
        esq = (w - novo_w) // 2
        img = img.crop((esq, 0, esq + novo_w, h))
    elif w / h < alvo:
        novo_h = round(w / alvo)
        topo = (h - novo_h) // 2
        img = img.crop((0, topo, w, topo + novo_h))
    img = img.resize((largura, altura), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


# --- serviços -------------------------------------------------------------------------

@dataclass
class Fala:
    pcm: bytes
    taxa: int


class Servicos:
    """Fronteira com o que custa dinheiro ou sai da função."""

    def gerar_fala(self, texto: str, voz: dict, modelo: str) -> Fala:
        raise NotImplementedError

    def gerar_imagem(self, prompt: str, referencias: list[bytes], formato: str, modelo: str) -> bytes:
        raise NotImplementedError

    def salvar(self, caminho: str, dados: bytes, mime: str) -> str:
        """Grava no bucket de trabalho e devolve o `gs://` do objeto."""
        raise NotImplementedError

    def ler(self, uri: str) -> bytes:
        raise NotImplementedError

    def existe(self, uri: str) -> bool:
        """O bucket apaga `tmp/` em 30 dias: um checkpoint pode apontar para um objeto que sumiu."""
        raise NotImplementedError

    def publicar(self, nome: str, dados: bytes, mime: str) -> dict:
        """Publica um arquivo para o usuário ver (Drive) → {"id", "link"}."""
        raise NotImplementedError


BUCKET = "gestao-hermes-video"
PASTA_DRIVE = "Hermes Vídeo"

# Prévia real de 26/09/2026: `gemini-2.5-flash-image` na Vertex devolveu 429
# RESOURCE_EXHAUSTED em rajadas (cota compartilhada), inclusive na 1ª chamada.
# 429/503 são passageiros e não são cobrados: esperar e tentar de novo.
ESPERAS_RETENTATIVA_S = (5, 15, 30)


def _passageiro(exc: Exception) -> bool:
    codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return codigo in (429, 503) or "RESOURCE_EXHAUSTED" in str(exc) or "UNAVAILABLE" in str(exc)


def com_retentativa(chamada, *, esperas=ESPERAS_RETENTATIVA_S, dormir=None):
    import time

    dormir = dormir or time.sleep
    for espera in (*esperas, None):
        try:
            return chamada()
        except Exception as exc:  # noqa: BLE001
            if espera is None or not _passageiro(exc):
                raise
            dormir(espera)


class ServicosVertex(Servicos):
    def __init__(self, db, projeto: str = "gestao-hermes", local: str = "us-central1", cliente=None):
        if cliente is None:
            from google import genai

            cliente = genai.Client(vertexai=True, project=projeto, location=local)
        self._cli = cliente
        self._db = db
        self._bucket = None
        self._drive = None
        self._pasta = None

    def gerar_fala(self, texto: str, voz: dict, modelo: str) -> Fala:
        from google.genai import types

        estilo = (voz or {}).get("estilo") or "neutro e claro"
        resp = com_retentativa(lambda: self._cli.models.generate_content(
            model=modelo,
            contents=f"Leia em português do Brasil, em tom {estilo}: {texto}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=(voz or {}).get("nome") or "Kore"))),
            ),
        ))
        dados = resp.candidates[0].content.parts[0].inline_data
        return Fala(pcm=dados.data, taxa=taxa_do_mime(dados.mime_type))

    def gerar_imagem(self, prompt: str, referencias: list[bytes], formato: str, modelo: str) -> bytes:
        from google.genai import types

        partes = [types.Part.from_bytes(data=r, mime_type="image/png") for r in referencias]
        partes.append(types.Part.from_text(text=prompt))
        resp = com_retentativa(lambda: self._cli.models.generate_content(
            model=modelo,
            contents=[types.Content(role="user", parts=partes)],
            config=types.GenerateContentConfig(response_modalities=["IMAGE"],
                                               image_config=types.ImageConfig(aspect_ratio=formato)),
        ))
        for parte in resp.candidates[0].content.parts:
            if getattr(parte, "inline_data", None) and parte.inline_data.data:
                return parte.inline_data.data
        raise RuntimeError("O modelo de imagem não devolveu imagem (filtro de segurança?).")

    def _bkt(self):
        if self._bucket is None:
            from google.cloud import storage

            self._bucket = storage.Client().bucket(BUCKET)
        return self._bucket

    def salvar(self, caminho: str, dados: bytes, mime: str) -> str:
        self._bkt().blob(caminho).upload_from_string(dados, content_type=mime)
        return f"gs://{BUCKET}/{caminho}"

    def _caminho(self, uri: str) -> str:
        bucket, _, caminho = uri.removeprefix("gs://").partition("/")
        if bucket != BUCKET:
            raise ValueError(f"URI fora do bucket do Hermes Vídeo: {uri}")
        return caminho

    def ler(self, uri: str) -> bytes:
        return self._bkt().blob(self._caminho(uri)).download_as_bytes()

    def existe(self, uri: str) -> bool:
        return self._bkt().blob(self._caminho(uri)).exists()

    def _servico_drive(self):
        if self._drive is None:
            from main import get_drive_service

            self._drive = get_drive_service()
        return self._drive

    def _pasta_drive(self):
        """Pasta "Hermes Vídeo" dentro da pasta raiz do Hermes (system/config.googleDriveFolderId)."""
        if self._pasta is not None:
            return self._pasta or None
        svc = self._servico_drive()
        cfg = self._db.collection("system").document("config").get()
        raiz = (cfg.to_dict() or {}).get("googleDriveFolderId") if cfg.exists else None
        def literal(valor: str) -> str:  # escape da linguagem de consulta do Drive
            return str(valor).replace("\\", "\\\\").replace("'", "\\'")

        consulta = (f"name = '{literal(PASTA_DRIVE)}' and mimeType = 'application/vnd.google-apps.folder' "
                    "and trashed = false" + (f" and '{literal(raiz)}' in parents" if raiz else ""))
        achadas = svc.files().list(q=consulta, fields="files(id)", pageSize=1).execute().get("files", [])
        if achadas:
            self._pasta = achadas[0]["id"]
        else:
            corpo = {"name": PASTA_DRIVE, "mimeType": "application/vnd.google-apps.folder"}
            if raiz:
                corpo["parents"] = [raiz]
            self._pasta = svc.files().create(body=corpo, fields="id").execute()["id"]
        return self._pasta

    def publicar(self, nome: str, dados: bytes, mime: str) -> dict:
        from googleapiclient.http import MediaIoBaseUpload

        svc = self._servico_drive()
        corpo = {"name": nome}
        pasta = self._pasta_drive()
        if pasta:
            corpo["parents"] = [pasta]
        arq = svc.files().create(body=corpo, media_body=MediaIoBaseUpload(io.BytesIO(dados), mimetype=mime),
                                 fields="id, webViewLink").execute()
        return {"id": arq["id"], "link": arq.get("webViewLink")}


class ServicosFalsos(Servicos):
    """Sem rede: fala = tom de 440 Hz com a duração do ritmo de referência; imagem = PNG liso."""

    def __init__(self, *, segundos_por_palavra: float = 0.5, falhar_imagem_em: set[int] | None = None,
                 falhar_fala_com: set[str] | None = None):
        self.falas: list[str] = []
        self.imagens: list[tuple[str, int]] = []
        self.arquivos: dict[str, bytes] = {}
        self.publicados: list[str] = []
        self._spp = segundos_por_palavra
        self._falhar = falhar_imagem_em or set()
        self._falhar_fala = falhar_fala_com or set()
        self._chamadas_imagem = 0

    def gerar_fala(self, texto, voz, modelo):
        import numpy as np

        if any(t in texto for t in self._falhar_fala):
            raise RuntimeError("TTS recusou (simulado)")
        self.falas.append(texto)
        taxa = 24000
        seg = max(len(texto.split()) * self._spp, 0.1)
        t = np.arange(int(seg * taxa)) / taxa
        tom = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16).tobytes()
        pausa = silencio_pcm(0.25, taxa)
        return Fala(pcm=pausa + tom + pausa, taxa=taxa)

    def gerar_imagem(self, prompt, referencias, formato, modelo):
        from PIL import Image

        n = self._chamadas_imagem  # posição da chamada (falhas contam), não das imagens geradas
        self._chamadas_imagem += 1
        if n in self._falhar:
            raise RuntimeError("filtro simulado")
        self.imagens.append((prompt, len(referencias)))
        buf = io.BytesIO()
        Image.new("RGB", (1344, 768) if formato == "16:9" else (768, 1344), (n * 20 % 255, 90, 120)).save(buf, "PNG")
        return buf.getvalue()

    def salvar(self, caminho, dados, mime):
        self.arquivos[caminho] = dados
        return f"gs://{BUCKET}/{caminho}"

    def ler(self, uri):
        return self.arquivos[uri.removeprefix(f"gs://{BUCKET}/")]

    def existe(self, uri):
        return uri.removeprefix(f"gs://{BUCKET}/") in self.arquivos

    def publicar(self, nome, dados, mime):
        self.publicados.append(nome)
        return {"id": f"drive-{len(self.publicados)}", "link": f"https://drive.example/{nome}"}
