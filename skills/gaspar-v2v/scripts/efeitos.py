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
    """Recebe quadros RGB e grava MP4 com o áudio do vídeo original."""

    def __init__(self, destino: Path, audio_de: Path):
        self.p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                   "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio_de), "-map", "0:v",
                                   "-map", "1:a?", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
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
        base_options=BaseOptions(model_asset_path=str(MODELOS_MP / "hand_landmarker.task")), running_mode=modo, num_hands=1))
    rostos = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODELOS_MP / "face_landmarker.task")), running_mode=modo, num_faces=1))
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


if __name__ == "__main__":
    main()
