"""Efeitos sobre a gravação do André que NÃO tocam no rosto dele.

1. Efeito ancorado na mão (qualquer elemento: fogo, magia, holograma, raio, logo): rastreio MediaPipe Hands,
   elemento sobre fundo preto composto em modo screen + brilho na cena. Liga quando a mão sobe.
2. Transformação (qualquer roupa/estilo por texto): a IA gera a versão transformada e o rosto ORIGINAL
   volta por cima (máscara do contorno do rosto pelo MediaPipe Face, borda suave, cor ajustada).

    PY efeitos.py rastrear  video.mp4 SAIDA                          # SAIDA/rastro.json (grátis)
    PY efeitos.py elemento  "descrição do elemento" SAIDA            # SAIDA/elemento.mp4 (~US$ 0,25)
    PY efeitos.py mao       video.mp4 elemento.mp4 SAIDA [--cor 255,140,40] [--escala 2.8]
                            [--gatilho visivel|acima] [--de 1.8 --ate 4.5] [--dedos-na-frente]
    PY efeitos.py transformar video.mp4 "prompt" SAIDA [--ref ref.png] [--modelo kling-pro] [--aprovado-ate X]
    PY efeitos.py dublar    video.mp4 en SAIDA [--lipsync]           # voz do André em outro idioma (boca sincronizada opcional)
    PY efeitos.py reframe   aula-16x9.mp4 reel.mp4                   # vertical seguindo o rosto, sem IA
    PY efeitos.py recortar  video.mp4 SAIDA/pessoa.webm [--rapido]   # pessoa com alfa suave (RVM), grátis
    PY efeitos.py cenario   video.mp4 fundo.png|"prompt" SAIDA [--ate 4 --transicao 0.4 --zoom 1.06]
    PY efeitos.py folha-recorte video.mp4 SAIDA                      # recorte sobre preto/branco/azul + métricas

PY = venv da tutorial-sistema com mediapipe; os comandos que chamam o fal usam também a pasta functions do
Hermes (credencial em GOOGLE_APPLICATION_CREDENTIALS). Áudio: sempre o original.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[3]
MODELOS_MP = Path.home() / ".tutorial-sistema" / "modelos"
URL_MP = "https://storage.googleapis.com/mediapipe-models/{0}/{0}/float16/1/{0}.task"


def modelo_mp(nome: str) -> str:
    """hand_landmarker / face_landmarker: cópia local, senão a do repositório (skills/gaspar-v2v/modelos, para
    ambiente sem acesso ao storage do Google), senão baixa do endereço oficial."""
    for p in (MODELOS_MP / f"{nome}.task", Path(__file__).resolve().parents[1] / "modelos" / f"{nome}.task"):
        if p.exists():
            return str(p)
    import urllib.request

    MODELOS_MP.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(URL_MP.format(nome), MODELOS_MP / f"{nome}.task")
    return str(MODELOS_MP / f"{nome}.task")
W, H, FPS = 1080, 1920, 30
PALMA = (0, 5, 9, 13, 17)


# ---------------------------------------------------------------- vídeo quadro a quadro

def quadros(video: Path, w: int = W, h: int = H):
    """Gera quadros RGB uint8 (h, w, 3) já endireitados (rotação do celular) e a 30 fps."""
    p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", str(video), "-vf",
                          f"fps={FPS},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
    p.wait()


class Gravador:
    """Recebe quadros RGB e grava MP4 com o áudio do vídeo original (inteiro: celular grava o áudio um pouco
    mais longo que o vídeo, e o último quadro se estende até o fim dele)."""

    def __init__(self, destino: Path, audio_de: Path):
        self.p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                   "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio_de), "-map", "0:v",
                                   "-map", "1:a?", "-vf", "tpad=stop_mode=clone:stop_duration=2", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
                                   "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                                   str(destino)], stdin=subprocess.PIPE)

    def __call__(self, q: np.ndarray):
        self.p.stdin.write(np.ascontiguousarray(q, np.uint8).tobytes())

    def fechar(self):
        self.p.stdin.close()
        self.p.wait()


# ---------------------------------------------------------------- rastreio

def rastrear(video: Path, pasta: Path) -> list[dict]:
    """Por quadro: {"mao": [[x,y]*21] | None, "rosto": [[x,y]*478] | None}, em pixels. Com cache."""
    arq = pasta / "rastro.json"
    if arq.exists() and arq.stat().st_mtime > video.stat().st_mtime:
        return json.loads(arq.read_text())
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    modo = vision.RunningMode.VIDEO
    maos = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=modelo_mp("hand_landmarker")), running_mode=modo, num_hands=1))
    rostos = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=modelo_mp("face_landmarker")), running_mode=modo, num_faces=1))
    rastro = []
    for k, q in enumerate(quadros(video)):
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(q))
        ms = int(k * 1000 / FPS)
        m, r = maos.detect_for_video(img, ms), rostos.detect_for_video(img, ms)
        px = lambda pts: [[round(p.x * W, 1), round(p.y * H, 1)] for p in pts]
        rastro.append({"mao": px(m.hand_landmarks[0]) if m.hand_landmarks else None,
                       "rosto": px(r.face_landmarks[0]) if r.face_landmarks else None})
    pasta.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(rastro))
    return rastro


def ancoras_mao(rastro: list[dict], *, gatilho: str = "visivel", limiar_y: float = 0.62, janela=None,
                suave: float = 0.35, rampa: int = 8) -> list[dict]:
    """Por quadro: centro da palma, tamanho da mão e intensidade 0–1 do efeito.

    gatilho: "visivel" (mão detectada), "acima" (palma acima de `limiar_y`, fração da altura) ou "janela"
    (`janela` = (de_s, ate_s), com a mão detectada). Acende/apaga em `rampa` quadros; posição e tamanho
    suavizados (média exponencial) para não tremer.
    """
    saida, pos, tam, inten = [], None, None, 0.0
    for f in rastro:
        mao = f["mao"]
        if mao:
            pts = np.array(mao)
            centro = pts[list(PALMA)].mean(0)
            t = float(np.linalg.norm(pts[9] - pts[0]))
            pos = centro if pos is None else pos + suave * (centro - pos)
            tam = t if tam is None else tam + suave * (t - tam)
            k = len(saida) / FPS
            alvo = {"visivel": 1.0, "acima": float(centro[1] < limiar_y * H),
                    "janela": float(bool(janela) and janela[0] <= k <= janela[1])}[gatilho]
        else:
            alvo = 0.0
        inten = min(1.0, inten + 1 / rampa) if alvo > inten else max(0.0, inten - 1 / rampa)
        saida.append({"pos": None if pos is None else pos.tolist(), "tam": tam, "inten": round(inten, 3)})
    return saida


# ---------------------------------------------------------------- 1. efeito na mão

# Ossos da mão (MediaPipe Hands) para desenhar a máscara dos dedos.
OSSOS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
         (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]


def mascara_mao(pontos, tam: float) -> np.ndarray:
    """Máscara 0–1 da mão: palma preenchida + dedos como traços grossos, borda suave."""
    from PIL import Image, ImageDraw, ImageFilter

    p = [tuple(x) for x in pontos]
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    d.polygon([p[i] for i in (0, 1, 5, 9, 13, 17)], fill=255)
    larg = max(8, int(tam * 0.2))
    for a, b in OSSOS:
        d.line([p[a], p[b]], fill=255, width=larg)
    for x, y in p:
        d.ellipse((x - larg / 2, y - larg / 2, x + larg / 2, y + larg / 2), fill=255)
    return np.asarray(m.filter(ImageFilter.GaussianBlur(3)), np.float32)[..., None] / 255.0


def _brilho(cor: np.ndarray, centro, raio: float) -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d2 = ((xx - centro[0]) ** 2 + (yy - centro[1]) ** 2) / (raio * raio)
    return np.exp(-d2)[..., None] * cor[None, None, :]


def efeito_mao(video: Path, elemento: Path, destino: Path, pasta: Path, *, cor=(255, 140, 40),
               escala: float = 2.8, subida: float = 0.9, brilho: float = 0.35, gatilho: str = "visivel",
               janela=None, dedos_na_frente: bool = False) -> Path:
    """Compõe `elemento` (vídeo com fundo preto; preto = transparente em modo screen) acima da palma.

    escala: largura do elemento em múltiplos do tamanho da mão. subida: quanto o elemento sobe acima do
    centro da palma (em tamanhos de mão). brilho: luz da cor do efeito na cena (rosto, parede).
    """
    rastro = rastrear(video, pasta)
    ancoras = ancoras_mao(rastro, gatilho=gatilho, janela=janela)
    elem = list(quadros(elemento, 512, 512))  # ponytail: elemento todo na memória; um clipe curto (~4 s) cabe
    cor = np.array(cor, np.float32) / 255.0
    grav = Gravador(destino, video)
    for k, q in enumerate(quadros(video)):
        a = ancoras[k] if k < len(ancoras) else ancoras[-1]
        out = q.astype(np.float32) / 255.0
        if a["inten"] > 0 and a["pos"]:
            lado = int(np.clip(a["tam"] * escala, 160, 0.5 * W))  # mão perto da lente não vira fogo gigante
            e = elem[k % len(elem)]
            e = np.asarray(_redim(e, lado), np.float32) / 255.0 * a["inten"]
            cx, cy = a["pos"][0], a["pos"][1] - min(a["tam"], lado / escala) * subida
            x0, y0 = int(cx - lado / 2), int(cy - lado * 0.75)
            antes = out.copy()
            out = _screen(out, e, x0, y0)
            mao = rastro[k]["mao"] if k < len(rastro) else None
            if dedos_na_frente and mao:
                # A mão (já iluminada abaixo) fica na frente da chama.
                m = mascara_mao(mao, a["tam"])
                out = out * (1 - m) + antes * m
            # Luz do efeito na cena: halo forte perto da mão, fraco no resto (rosto e parede "acendem").
            luz = _brilho(cor, (cx, cy), lado * 0.9) * brilho * a["inten"] + cor * 0.04 * a["inten"]
            out = 1 - (1 - out) * (1 - luz)
        grav(np.clip(out * 255, 0, 255).astype(np.uint8))
    grav.fechar()
    return destino


def _redim(img: np.ndarray, lado: int) -> np.ndarray:
    from PIL import Image

    return np.array(Image.fromarray(img).resize((lado, lado), Image.BILINEAR))


def _screen(base: np.ndarray, e: np.ndarray, x0: int, y0: int) -> np.ndarray:
    h, w = e.shape[:2]
    bx0, by0, bx1, by1 = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if bx0 >= bx1 or by0 >= by1:
        return base
    sub = e[by0 - y0:by1 - y0, bx0 - x0:bx1 - x0]
    reg = base[by0:by1, bx0:bx1]
    # Transparência pelo brilho do próprio elemento (preto = 0): a chama fica saturada até sobre parede
    # branca, onde o screen puro a lavaria; o screen por cima mantém o miolo luminoso.
    alfa = np.clip(sub.max(-1, keepdims=True) * 1.8, 0, 1)
    base[by0:by1, bx0:bx1] = 1 - (1 - (reg * (1 - alfa) + sub * alfa)) * (1 - sub * 0.5)
    return base


# ---------------------------------------------------------------- 2. transformação com rosto original

# Contorno do rosto no Face Mesh (478 pontos), em ordem.
OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176,
        149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]


def mascara_rosto(pontos, *, recuo_testa: float = 0.18, borda: int = 13) -> np.ndarray:
    """Máscara 0–1 do rosto (oval do Face Mesh), recuada na testa para o chapéu poder cobri-la, borda suave."""
    from PIL import Image, ImageDraw, ImageFilter

    pts = np.array(pontos)[OVAL]
    topo, queixo = pts[:, 1].min(), pts[:, 1].max()
    pts[:, 1] = np.maximum(pts[:, 1], topo + recuo_testa * (queixo - topo))
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in pts], fill=255)
    m = m.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(borda))
    return np.asarray(m, np.float32)[..., None] / 255.0


def casar_cor(rosto: np.ndarray, gerado: np.ndarray, m: np.ndarray) -> np.ndarray:
    """Ajusta média/desvio do rosto original ao entorno do rosto no quadro gerado (faixa da borda)."""
    faixa = (m[..., 0] > 0.05) & (m[..., 0] < 0.6)
    if faixa.sum() < 50:
        return rosto
    a, b = rosto[faixa], gerado[faixa]
    ganho = np.clip((b.std(0) + 1e-3) / (a.std(0) + 1e-3), 0.85, 1.15)
    return np.clip((rosto - a.mean(0)) * ganho + b.mean(0), 0, 1)


def devolver_rosto(original: Path, gerado: Path, destino: Path, pasta: Path, *, recuo_testa: float = 0.18) -> Path:
    """Cola o rosto original sobre o vídeo gerado.

    O modelo devolve outra duração/fps e mexe um pouco a cabeça: cada quadro gerado k usa o quadro original
    proporcional, e o rosto original é deslocado até o nariz da cabeça gerada (rastreio dos dois vídeos).
    """
    ro = rastrear(original, pasta)
    rg = rastrear(gerado, pasta / "gerado")
    orig = list(quadros(original))  # ponytail: trecho curto (≤ 10 s) cabe na memória
    nariz = lambda f: np.array(f["rosto"][1]) if f and f["rosto"] else None
    grav = Gravador(destino, original)
    ultimo = desloc = None
    for k, g in enumerate(quadros(gerado)):
        j = min(len(orig) - 1, round(k * (len(orig) - 1) / max(1, len(rg) - 1)))
        fo, fg = (ro[j] if j < len(ro) else None), (rg[k] if k < len(rg) else None)
        if fo and fo["rosto"]:
            ultimo = fo["rosto"]
        if nariz(fo) is not None and nariz(fg) is not None:
            desloc = nariz(fg) - nariz(fo)
        if ultimo is None:
            grav(g)
            continue
        dx, dy = (0, 0) if desloc is None else (int(round(desloc[0])), int(round(desloc[1])))
        pts = (np.array(ultimo) + [dx, dy]).tolist()
        o = np.roll(np.roll(orig[j], dy, axis=0), dx, axis=1).astype(np.float32) / 255.0
        gg = g.astype(np.float32) / 255.0
        m = mascara_rosto(pts, recuo_testa=recuo_testa)
        grav(np.clip((casar_cor(o, gg, m) * m + gg * (1 - m)) * 255, 0, 255).astype(np.uint8))
    grav.fechar()
    return destino


def transformar(video: Path, texto: str, pasta: Path, *, ref: Path | None, modelo: str, aprovado: float,
                task_id: str | None) -> Path:
    """IA gera a versão transformada (roupa/estilo); depois o rosto original volta por cima."""
    sys.path.insert(0, str(RAIZ / "functions"))
    sys.path.insert(0, str(Path(__file__).parent))
    import urllib.request

    from v2v import publicar, rodar_fal

    ids = {"kling-pro": "fal-ai/kling-video/o3/pro/video-to-video/edit",
           "kling": "fal-ai/kling-video/o3/standard/video-to-video/edit"}
    pasta.mkdir(parents=True, exist_ok=True)
    gerado = pasta / "gerado.mp4"
    if not gerado.exists():
        entrada_v = pasta / "entrada.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-an", "-vf",
                        f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                        "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", str(entrada_v)], check=True)
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", str(entrada_v)]).decode())
        entrada = {"prompt": ("In @Video1: keep the person's face, head position, expressions, lip movements, gestures "
                              f"and camera framing exactly the same. {texto}"
                              + (" Use @Image1 as the reference for the outfit." if ref else "")),
                   "video_url": publicar(entrada_v, f"efeitos/{pasta.name}/entrada.mp4"), "keep_audio": False}
        if ref:
            entrada["image_urls"] = [publicar(ref, f"efeitos/{pasta.name}/{ref.name}")]
        r = rodar_fal(ids[modelo], entrada, segundos=dur, task_id=task_id, aprovado=aprovado,
                      pendente=pasta / "gerado.job")
        urllib.request.urlretrieve(r["urls"][0], gerado)
        print(f"gerado: US$ {r['custo_real_usd']:.2f}")
    return devolver_rosto(video, gerado, pasta / "transformado.mp4", pasta)


def gerar_elemento(descricao: str, pasta: Path, task_id: str | None) -> Path:
    """Elemento animado isolado sobre fundo PRETO (para modo screen): imagem no fal + 4 s no Veo Lite."""
    sys.path.insert(0, str(RAIZ / "functions"))
    sys.path.insert(0, str(Path(__file__).parent))
    import urllib.request

    from v2v import rodar_fal
    from video.veo_provider import PedidoClipe, VertexVeoProvider

    pasta.mkdir(parents=True, exist_ok=True)
    png = pasta / "elemento.png"
    texto = (f"{descricao}, centered, isolated on a pure solid black background (#000000), nothing else in the frame, "
             "no hands, no people, no text, glowing, high contrast")
    if not png.exists():
        r = rodar_fal("fal-ai/nano-banana", {"prompt": texto, "aspect_ratio": "1:1", "num_images": 1}, task_id=task_id)
        urllib.request.urlretrieve(r["urls"][0], png)
    veo = VertexVeoProvider()
    op = veo.gerar_clipe(PedidoClipe(modelo="veo-3.1-lite-generate-001", imagem_inicio=png.read_bytes(), duracao_s=4,
                                     prompt=texto + ". Static camera. The effect animates and flickers in place, "
                                            "background stays pure black.", aspecto="16:9",
                                     negativo="hands, people, background objects, text, camera movement"))
    import time

    while not (res := veo.consultar_operacao(op)).concluida:
        time.sleep(5)
    if res.erro or res.bloqueado:
        raise SystemExit(f"Veo: {res.erro or res.motivo_bloqueio}")
    bruto = pasta / "elemento-bruto.mp4"
    bruto.write_bytes(veo.baixar(res))
    # Recorta o quadrado central e afunda o preto (o que não é efeito vira 0 no modo screen).
    destino = pasta / "elemento.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(bruto), "-vf",
                    "crop=ih:ih,scale=512:512,curves=all='0/0 0.12/0 1/1'", "-an", "-c:v", "libx264", "-crf", "16",
                    "-pix_fmt", "yuv420p", str(destino)], check=True)
    print("elemento: ~US$ 0,24 (imagem US$ 0,04 + Veo Lite 4 s US$ 0,20)")
    return destino


# ---------------------------------------------------------------- 3. dublagem com lip-sync só na boca

def _chave_eleven() -> str:
    from google.cloud import firestore

    d = firestore.Client(project="gestao-hermes").collection("system").document("api_keys").get().to_dict() or {}
    if not d.get("elevenlabs_api_key"):
        raise SystemExit("Sem elevenlabs_api_key em system/api_keys.")
    return d["elevenlabs_api_key"]


def dublar_audio(video: Path, idioma: str, pasta: Path) -> Path:
    """Dublagem do ElevenLabs com a voz do próprio André (clonagem automática do falante; autorizada por ele
    em 01/11/2026). Devolve o áudio dublado (wav). Custa créditos do ElevenLabs."""
    import time

    import requests

    destino = pasta / f"dub-{idioma}.wav"
    if destino.exists():
        return destino
    url, cab = "https://api.elevenlabs.io/v1/dubbing", {"xi-api-key": _chave_eleven()}
    with open(video, "rb") as f:
        r = requests.post(url, headers=cab, files={"file": (video.name, f, "video/mp4")}, timeout=600,
                          data={"source_lang": "pt", "target_lang": idioma, "num_speakers": "1", "watermark": "false",
                                "name": f"gaspar-{pasta.name}-{idioma}"})
    if not r.ok:
        raise SystemExit(f"ElevenLabs recusou a dublagem ({r.status_code}): {r.text[:400]}")
    dub_id = r.json()["dubbing_id"]
    (pasta / f"dub-{idioma}.id").write_text(dub_id)
    while True:
        st = requests.get(f"{url}/{dub_id}", headers=cab, timeout=60).json()
        if st.get("status") == "dubbed":
            break
        if st.get("status") == "failed":
            raise SystemExit(f"ElevenLabs falhou: {st.get('error')}")
        time.sleep(10)
    media = pasta / f"dub-{idioma}.mp4"
    media.write_bytes(requests.get(f"{url}/{dub_id}/audio/{idioma}", headers=cab, timeout=600).content)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(media), "-vn", "-ac", "1", "-ar", "48000",
                    str(destino)], check=True)
    return destino


def mascara_boca(pontos, *, borda: int = 15) -> np.ndarray:
    """Parte de baixo do rosto (do nariz ao queixo, dentro do oval): boca e mandíbula mexem juntas."""
    from PIL import Image, ImageDraw, ImageFilter

    pts = np.array(pontos)
    corte = pts[2][1]  # logo abaixo da ponta do nariz
    oval = [tuple(p) for p in pts[OVAL] if p[1] >= corte]
    oval = sorted(oval, key=lambda p: np.arctan2(p[1] - pts[13][1], p[0] - pts[13][0]))
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon([(pts[234][0], corte), *oval, (pts[454][0], corte)], fill=255)
    return np.asarray(m.filter(ImageFilter.GaussianBlur(borda)), np.float32)[..., None] / 255.0


def devolver_exceto_boca(original: Path, sincronizado: Path, audio: Path, destino: Path, pasta: Path) -> Path:
    """Quadro final = original em tudo, menos a parte de baixo do rosto, que vem do lip-sync."""
    rs = rastrear(sincronizado, pasta / "sync")
    orig = list(quadros(original))
    grav = Gravador(destino, audio)
    ultimo = None
    for k, sq in enumerate(quadros(sincronizado)):
        j = min(len(orig) - 1, k)  # o lip-sync preserva o tempo do vídeo de entrada
        f = rs[k] if k < len(rs) else None
        ultimo = (f or {}).get("rosto") or ultimo
        if ultimo is None:
            grav(orig[j])
            continue
        m = mascara_boca(ultimo)
        o, g = orig[j].astype(np.float32) / 255.0, sq.astype(np.float32) / 255.0
        grav(np.clip((casar_cor(g, o, m) * m + o * (1 - m)) * 255, 0, 255).astype(np.uint8))
    grav.fechar()
    return destino


def dublar(video: Path, idioma: str, pasta: Path, *, task_id: str | None, aprovado: float,
           lipsync: bool = False) -> Path:
    """Padrão: vídeo original + áudio dublado (só créditos do ElevenLabs). `lipsync=True`: a boca acompanha o
    novo idioma (Sync no fal, ~US$ 0,08/s) — para momentos especiais, por ser caro."""
    pasta.mkdir(parents=True, exist_ok=True)
    if not lipsync:
        audio = dublar_audio(video, idioma, pasta)
        destino = pasta / f"dublado-{idioma}.mp4"
        # O vídeo manda na duração: áudio dublado mais curto ganha silêncio no fim, nunca corta a imagem.
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v",
                        "-map", "1:a", "-c:v", "copy", "-af", "apad", "-c:a", "aac", "-b:a", "192k", "-shortest",
                        "-movflags", "+faststart", str(destino)], check=True)
        return destino
    sys.path.insert(0, str(RAIZ / "functions"))
    sys.path.insert(0, str(Path(__file__).parent))
    import urllib.request

    from v2v import publicar, rodar_fal

    pasta.mkdir(parents=True, exist_ok=True)
    audio = dublar_audio(video, idioma, pasta)
    base = pasta / "base30.mp4"
    if not base.exists():
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-an", "-vf",
                        f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                        "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", str(base)], check=True)
    sinc = pasta / f"sync-{idioma}.mp4"
    if not sinc.exists():
        m4a = pasta / f"dub-{idioma}.m4a"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(audio), "-c:a", "aac", str(m4a)], check=True)
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                             "csv=p=0", str(base)]).decode())
        r = rodar_fal("fal-ai/sync-lipsync/v2/pro",
                      {"video_url": publicar(base, f"efeitos/{pasta.name}/base30.mp4"),
                       "audio_url": publicar(m4a, f"efeitos/{pasta.name}/{m4a.name}"), "sync_mode": "cut_off"},
                      segundos=dur, task_id=task_id, aprovado=aprovado, pendente=pasta / f"sync-{idioma}.job")
        urllib.request.urlretrieve(r["urls"][0], sinc)
        print(f"lip-sync: US$ {r['custo_real_usd']:.2f}")
    return devolver_exceto_boca(base, sinc, audio, pasta / f"dublado-{idioma}-lipsync.mp4", pasta)


# ---------------------------------------------------------------- 4. reframe 16:9 → 9:16 seguindo o rosto

def reframe(video: Path, destino: Path, *, suave: float = 0.06, folga: float = 0.04) -> Path:
    """Corte vertical que acompanha o rosto (MediaPipe), sem gerar nada: os pixels são os originais.

    suave: inércia da câmera virtual (menor = mais calma); folga: o rosto pode andar essa fração da largura
    sem a câmera se mexer (evita "respirar" a cada movimento).
    """
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    w0, h0 = (int(x) for x in subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
         str(video)]).decode().strip().split(","))
    if h0 >= w0:
        raise SystemExit("O vídeo já é vertical.")
    largura = int(h0 * 9 / 16) // 2 * 2
    rostos = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=modelo_mp("face_landmarker")),
        running_mode=vision.RunningMode.VIDEO, num_faces=1))
    grav = Gravador(destino, video)
    cx = None
    for k, q in enumerate(quadros(video, w0, h0)):
        r = rostos.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(q)),
                                    int(k * 1000 / FPS))
        alvo = r.face_landmarks[0][1].x * w0 if r.face_landmarks else (cx or w0 / 2)
        cx = alvo if cx is None else (cx + suave * (alvo - cx) if abs(alvo - cx) > folga * w0 else cx)
        x0 = int(np.clip(cx - largura / 2, 0, w0 - largura))
        grav(_redim_ret(q[:, x0:x0 + largura], W, H))
    grav.fechar()
    return destino


def _redim_ret(img: np.ndarray, w: int, h: int) -> np.ndarray:
    from PIL import Image

    return np.array(Image.fromarray(np.ascontiguousarray(img)).resize((w, h), Image.LANCZOS))


# ---------------------------------------------------------------- 4. recorte (alfa suave) e troca de cenário
#
# Robust Video Matting (ONNX, pesos nos releases do GitHub; recorrente = estável entre quadros) dá o alfa
# contínuo e a cor do primeiro plano já descontaminada (sem a parede branca no cabelo). Depois: furos internos
# pequenos fechados, rosto sempre opaco, alfa estabilizado no tempo e borda externa suavizada. Escolha
# registrada em 01/11/2026: resnet50 (cabelo mais inteiro que o mobilenetv3, ~2,7 quadros/s na CPU).

URL_RVM = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/{}.onnx"
FURO_MAX = 0.02  # furo interno menor que 2% do quadro é erro do modelo; maior é vão real (braço na cintura)


def _rvm(nome: str):
    import onnxruntime as ort

    arq = MODELOS_MP / f"{nome}.onnx"
    if not arq.exists():
        import urllib.request

        MODELOS_MP.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL_RVM.format(nome), arq)
    return ort.InferenceSession(str(arq), providers=["CPUExecutionProvider"])


def nucleo_rosto(pontos) -> np.ndarray:
    """Oval do rosto (MediaPipe) recuada 12 px: ali o alfa é sempre 1."""
    import cv2

    m = np.zeros((H, W), np.uint8)
    if pontos:
        oval = np.array([pontos[i] for i in OVAL], np.int32)
        cv2.fillPoly(m, [oval], 1)
        m = cv2.erode(m, np.ones((25, 25), np.uint8))
    return m.astype(bool)


def furos_internos(a: np.ndarray, topo_rosto: float = 0) -> np.ndarray:
    """Furos internos pequenos (< FURO_MAX do quadro), do topo do rosto para baixo e cercados de pessoa sólida
    (alfa médio ≥ 0,85 em volta): erro do modelo (pescoço, alça, orelha). Acima do rosto, ou dentro da borda
    semitransparente (cabelo), são vãos reais e ficam transparentes."""
    from scipy.ndimage import binary_dilation, binary_fill_holes, find_objects, label

    solido = a > 0.5
    rot, n = label(binary_fill_holes(solido) & ~solido)
    if not n:
        return np.zeros_like(solido)
    areas = np.bincount(rot.ravel())
    ok = []
    for k, sl in enumerate(find_objects(rot), 1):
        if areas[k] >= FURO_MAX * a.size or sl[0].start < topo_rosto:
            continue
        y0, y1 = max(0, sl[0].start - 5), sl[0].stop + 5
        x0, x1 = max(0, sl[1].start - 5), sl[1].stop + 5
        furo = rot[y0:y1, x0:x1] == k
        anel = binary_dilation(furo, iterations=4) & ~furo
        if a[y0:y1, x0:x1][anel].mean() >= 0.85:
            ok.append(k)
    return np.isin(rot, ok)


def refinar_alfa(a: np.ndarray, anterior: np.ndarray | None, nucleo: np.ndarray | None = None,
                 topo_rosto: float = 0) -> np.ndarray:
    """Alfa do modelo → alfa final (float 0–1): sem furo interno, rosto opaco, sem cintilação, borda suave."""
    import cv2

    a = np.where(furos_internos(a, topo_rosto), 1.0, a)
    if anterior is not None:  # média só onde mudou pouco: borda parada não cintila, movimento rápido não borra
        a = np.where(np.abs(a - anterior) < 0.25, 0.55 * a + 0.45 * anterior, a)
    a = np.maximum(a, cv2.GaussianBlur(a, (0, 0), 1.6) * (a > 0.02))  # suaviza só para fora: não encolhe
    a = cv2.GaussianBlur(a, (0, 0), 0.8)
    if nucleo is not None:
        a[nucleo] = 1.0
    return np.clip(a, 0, 1).astype(np.float32)


def recortar(video: Path, destino: Path, pasta: Path, *, modelo: str = "rvm_resnet50_fp32", reducao: float = 0.25) -> Path:
    """Pessoa com alfa suave (WebM VP9 com alfa, 1080×1920, 30 fps). Com cache pelo horário do vídeo."""
    if destino.exists() and destino.stat().st_mtime > video.stat().st_mtime:
        return destino
    sess = _rvm(modelo)
    rastro = rastrear(video, pasta)
    rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
    ds = np.array([reducao], np.float32)
    destino.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "8M",
                          "-deadline", "good", "-cpu-used", "5", "-row-mt", "1", "-auto-alt-ref", "0", str(destino)],
                         stdin=subprocess.PIPE)
    ant = None
    for k, q in enumerate(quadros(video)):
        src = (q.astype(np.float32) / 255).transpose(2, 0, 1)[None]
        fgr, pha, *rec = sess.run(None, {"src": src, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2], "r4i": rec[3],
                                         "downsample_ratio": ds})
        rosto = rastro[k]["rosto"] if k < len(rastro) else None
        topo = min(p[1] for p in rosto) if rosto else 0
        a = ant = refinar_alfa(pha[0, 0], ant, nucleo_rosto(rosto), topo)
        # Cor: pixel original só no miolo opaco; em toda borda/vão, a cor descontaminada do modelo (sem a parede).
        w = np.clip((a - 0.97) / 0.03, 0, 1)[..., None]
        cor = q * w + fgr[0].transpose(1, 2, 0) * 255 * (1 - w)
        p.stdin.write(np.dstack([np.clip(cor, 0, 255), a * 255]).astype(np.uint8).tobytes())
    p.stdin.close()
    p.wait()
    return destino


def quadros_rgba(webm: Path):
    """Quadros RGBA float 0–1 do recorte (o decodificador libvpx é o que lê o alfa)."""
    p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-c:v", "libvpx-vp9", "-i", str(webm), "-f", "rawvideo",
                          "-pix_fmt", "rgba", "-"], stdout=subprocess.PIPE)
    n = W * H * 4
    while len(b := p.stdout.read(n)) == n:
        yield np.frombuffer(b, np.uint8).reshape(H, W, 4).astype(np.float32) / 255
    p.wait()


def compor(rgba: np.ndarray, fundo: np.ndarray, fundo_desf: np.ndarray, *, wrap: float = 0.18) -> np.ndarray:
    """Pessoa sobre o fundo (float 0–1) com light wrap: a borda de dentro pega um pouco da luz do cenário."""
    import cv2

    a = rgba[..., 3:4]
    borda = np.clip(1 - cv2.GaussianBlur(rgba[..., 3], (0, 0), 6), 0, 1)[..., None] * a
    pessoa = rgba[..., :3] * (1 - wrap * borda) + fundo_desf * wrap * borda
    return pessoa * a + fundo * (1 - a)


CINTILACAO_MAX = 0.05  # referência: 0,041 neste pipeline no clipe de teste de 01/11/2026 (sem cintilação visível)


def medir_recorte(alfas: list[np.ndarray], topos: list[float] | None = None) -> dict:
    """furos: área (px) do maior furo interno do rosto para baixo (tem de ser 0). cintilacao: variação média do
    alfa na borda entre quadros seguidos, descontado o movimento da silhueta (limite CINTILACAO_MAX)."""
    furo = 0
    for k, a in enumerate(alfas):
        furo = max(furo, int(furos_internos(a, topos[k] if topos else 0).sum()))
    cint = []
    for a0, a1 in zip(alfas, alfas[1:]):
        borda = ((a0 > 0.05) & (a0 < 0.95)) | ((a1 > 0.05) & (a1 < 0.95))
        if borda.any():
            mov = abs(float((a1 > 0.5).mean() - (a0 > 0.5).mean())) * 20  # silhueta que se mexe muda a borda de verdade
            cint.append(max(0.0, float(np.abs(a1 - a0)[borda].mean()) - mov))
    return {"furos_px": furo, "cintilacao": round(float(np.mean(cint)) if cint else 0.0, 4)}


def franja_clara(comp: np.ndarray, a: np.ndarray, fundo: np.ndarray) -> float:
    """Quanto a borda do recorte é mais clara que o cenário em volta (0–1 de luminância; aviso acima de 0,25)."""
    import cv2

    lum = lambda x: x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    borda = (a > 0.1) & (a < 0.9)
    anel = cv2.dilate((a > 0.1).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & (a <= 0.02)
    if not borda.any() or not anel.any():
        return 0.0
    return round(float(lum(comp)[borda].mean() - lum(fundo)[anel].mean()), 3)


def cenario(video: Path, fundo: str, pasta: Path, *, ate: float = 4.0, transicao: float = 0.4, zoom: float = 1.06,
            task_id: str | None = None) -> Path:
    """Troca o cenário nos primeiros `ate` s (pessoa recortada sobre `fundo` com aproximação lenta) e volta ao
    vídeo original numa fusão de `transicao` s. `fundo`: imagem/vídeo ou um texto (gera no nano-banana 9:16)."""
    import cv2

    pasta.mkdir(parents=True, exist_ok=True)
    if not Path(fundo).exists():
        sys.path.insert(0, str(RAIZ / "functions"))
        sys.path.insert(0, str(Path(__file__).parent))
        import urllib.request

        from v2v import rodar_fal

        png = pasta / "fundo.png"
        if not png.exists():
            r = rodar_fal("fal-ai/nano-banana", {"prompt": f"{fundo}, no people, vertical 9:16, soft depth of field",
                                                 "aspect_ratio": "9:16", "num_images": 1}, task_id=task_id)
            urllib.request.urlretrieve(r["urls"][0], png)
        fundo = str(png)
    pessoa = recortar(video, pasta / "pessoa.webm", pasta)
    base = cv2.cvtColor(cv2.imread(fundo), cv2.COLOR_BGR2RGB)
    s = max(W / base.shape[1], H / base.shape[0])
    base = cv2.resize(base, (round(base.shape[1] * s), round(base.shape[0] * s)), interpolation=cv2.INTER_AREA)
    y0, x0 = (base.shape[0] - H) // 2, (base.shape[1] - W) // 2
    base = base[y0:y0 + H, x0:x0 + W].astype(np.float32) / 255
    destino = pasta / "cenario.mp4"
    grav = Gravador(destino, video)
    franjas = []
    for k, (q, rgba) in enumerate(zip(quadros(video), quadros_rgba(pessoa))):
        t = k / FPS
        if t >= ate + transicao:
            grav(q)
            continue
        z = 1 + (zoom - 1) * min(1.0, t / max(ate, 0.1))
        M = np.float32([[z, 0, (1 - z) * W / 2], [0, z, (1 - z) * H / 2]])
        fd = cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        comp = compor(rgba, fd, cv2.GaussianBlur(fd, (0, 0), 18))
        if k % 15 == 0:
            franjas.append(franja_clara(comp, rgba[..., 3], fd))
        f = 0.0 if t < ate else (t - ate) / transicao
        grav(np.clip((comp * (1 - f) + q / 255 * f) * 255, 0, 255).astype(np.uint8))
    grav.fechar()
    pior = max(franjas, default=0.0)
    print(f"cenário: {destino} (franja clara máx. {pior:.2f}{' — AVISO: borda clara visível' if pior > 0.25 else ''})")
    return destino


def folha_recorte(video: Path, pasta: Path, *, instantes=(0.8, 2.8, 3.5, 12.0, 20.0)) -> Path:
    """Critério de aceite: o recorte sobre preto, branco e azul saturado em quadros fixos + métricas."""
    import cv2

    pessoa = recortar(video, pasta / "pessoa.webm", pasta)
    rastro = rastrear(video, pasta)
    alvo = {round(t * FPS) for t in instantes}
    linhas, alfas, topos = [], [], []
    for k, rgba in enumerate(quadros_rgba(pessoa)):
        if k <= 150:  # 0–5 s: o trecho da troca de cenário
            alfas.append(rgba[..., 3])
            r = rastro[k]["rosto"] if k < len(rastro) else None
            topos.append(min(p[1] for p in r) if r else 0)
        if k in alvo:
            cores = [np.zeros(3), np.ones(3), np.array([20, 40, 230]) / 255]
            linhas.append(np.hstack([cv2.resize(compor(rgba, np.broadcast_to(c, rgba[..., :3].shape).astype(np.float32),
                                                       np.broadcast_to(c, rgba[..., :3].shape).astype(np.float32)), (360, 640))
                                     for c in cores]))
    folha = pasta / "folha-recorte.jpg"
    cv2.imwrite(str(folha), cv2.cvtColor((np.vstack(linhas) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    m = medir_recorte(alfas, topos)
    (pasta / "recorte-metricas.json").write_text(json.dumps(m))
    print(f"{folha} — furos {m['furos_px']} px, cintilação {m['cintilacao']} (limite {CINTILACAO_MAX})")
    return folha


def main():
    cmd = sys.argv[1]
    opc = lambda nome, padrao=None: sys.argv[sys.argv.index(nome) + 1] if nome in sys.argv else padrao
    if cmd == "rastrear":
        r = rastrear(Path(sys.argv[2]), Path(sys.argv[3]))
        print(f"{len(r)} quadros; mão em {sum(1 for f in r if f['mao'])}, rosto em {sum(1 for f in r if f['rosto'])}")
    elif cmd == "elemento":
        print(gerar_elemento(sys.argv[2], Path(sys.argv[3]), opc("--task")))
    elif cmd == "mao":
        cor = tuple(int(c) for c in opc("--cor", "255,140,40").split(","))
        janela = (float(opc("--de")), float(opc("--ate"))) if opc("--de") else None
        print(efeito_mao(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]) / "efeito-mao.mp4", Path(sys.argv[4]),
                         cor=cor, escala=float(opc("--escala", 2.8)), janela=janela,
                         gatilho="janela" if janela else opc("--gatilho", "visivel"),
                         dedos_na_frente="--dedos-na-frente" in sys.argv))
    elif cmd == "transformar":
        print(transformar(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), ref=Path(opc("--ref")) if opc("--ref") else None,
                          modelo=opc("--modelo", "kling-pro"), aprovado=float(opc("--aprovado-ate", 0)), task_id=opc("--task")))


    if cmd == "recortar":
        print(recortar(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[3]).parent,
                       modelo="rvm_mobilenetv3_fp32" if "--rapido" in sys.argv else "rvm_resnet50_fp32"))
    if cmd == "cenario":
        print(cenario(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), ate=float(opc("--ate", 4)),
                      transicao=float(opc("--transicao", 0.4)), zoom=float(opc("--zoom", 1.06)), task_id=opc("--task")))
    if cmd == "folha-recorte":
        print(folha_recorte(Path(sys.argv[2]), Path(sys.argv[3])))
    if cmd == "reframe":
        print(reframe(Path(sys.argv[2]), Path(sys.argv[3])))
    if cmd == "dublar":
        print(dublar(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), task_id=opc("--task"),
                     aprovado=float(opc("--aprovado-ate", 0)), lipsync="--lipsync" in sys.argv))


if __name__ == "__main__":
    main()
