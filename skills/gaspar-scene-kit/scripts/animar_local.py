"""Animação local de uma ilustração (sem Veo, grátis): leve aproximação e balanço da câmera, brilho pulsante e
partículas de luz subindo. Fallback oficial do `"animar": true` quando o Veo não está disponível (ou com
`--animacao local` no montar.mjs); o resumo do montar avisa que não foi o Veo.

    PY animar_local.py imagem.png SEGUNDOS saida.mp4 [16:9|9:16]
"""
import math
import subprocess
import sys

import cv2
import numpy as np

img_p, dur, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
FPS = 30
W, H = (720, 1280) if len(sys.argv) > 4 and sys.argv[4] == "9:16" else (1280, 720)
_img = cv2.imread(img_p)
_s = max(W / _img.shape[1], H / _img.shape[0])  # cobre o quadro sem distorcer
_img = cv2.resize(_img, (math.ceil(_img.shape[1] * _s), math.ceil(_img.shape[0] * _s)), interpolation=cv2.INTER_AREA)
_y, _x = (_img.shape[0] - H) // 2, (_img.shape[1] - W) // 2
base = _img[_y:_y + H, _x:_x + W].astype(np.float32)
rng = np.random.default_rng(7)

def sprite(n=48):
    y, x = np.mgrid[-1:1:n*1j, -1:1:n*1j]
    r = np.sqrt(x*x + y*y)
    return np.clip(1 - r, 0, 1) ** 2.2
SP = sprite()
def cruz(n=64):
    y, x = np.mgrid[-1:1:n*1j, -1:1:n*1j]
    a = np.exp(-(np.abs(x) * 14)) * np.exp(-(np.abs(y) * 2.6)) + np.exp(-(np.abs(y) * 14)) * np.exp(-(np.abs(x) * 2.6))
    return np.clip(a, 0, 1)
CR = cruz()
CORES = [(70, 190, 255), (150, 215, 255), (235, 240, 255)]  # BGR: âmbar, ciano claro, branco quente

N = 110
P = [{"b": rng.uniform(-4.5, dur), "L": rng.uniform(2.6, 4.6), "x": rng.normal(0.5 * W, 80), "y": rng.normal(0.56 * H, 22),
      "vy": rng.uniform(55, 130), "sw": rng.uniform(8, 28), "f": rng.uniform(0.5, 1.2), "ph": rng.uniform(0, 6.28),
      "r": rng.uniform(2.0, 5.0), "c": CORES[int(rng.choice(3, p=[0.55, 0.3, 0.15]))]} for _ in range(N)]
ESTRELAS = [(0.339, 0.196), (0.778, 0.342), (0.182, 0.434), (0.225, 0.679), (0.806, 0.606)]

def blit(frame, spr, cx, cy, size, color, gain):
    s = int(max(2, size))
    if s < 2: return
    sp = cv2.resize(spr, (s, s), interpolation=cv2.INTER_LINEAR)
    x0, y0 = int(cx - s / 2), int(cy - s / 2)
    x1, y1 = x0 + s, y0 + s
    if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H: return
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0c, y0c, x1c, y1c = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    sub = sp[sy0:sy0 + (y1c - y0c), sx0:sx0 + (x1c - x0c)]
    frame[y0c:y1c, x0c:x1c] += sub[..., None] * np.array(color, np.float32) * gain

gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
glow_r = np.sqrt(((gx - 0.5 * W) / (0.30 * W)) ** 2 + ((gy - 0.52 * H) / (0.26 * W)) ** 2)
glow = np.clip(1 - glow_r, 0, 1) ** 2

n = int(dur * FPS)
p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                      "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
for i in range(n):
    t = i / FPS
    z = 1.0 + 0.06 * (t / dur)
    dy = 5 * math.sin(2 * math.pi * t / 4.0)
    dx = 3 * math.sin(2 * math.pi * t / 5.5 + 1)
    M = np.array([[z, 0, (1 - z) * W / 2 + dx], [0, z, (1 - z) * H / 2 + dy]], np.float32)
    fr = cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    pulso = 0.5 + 0.5 * math.sin(2 * math.pi * t / 2.6)
    fr += glow[..., None] * np.array((60, 150, 255), np.float32) * (0.10 + 0.10 * pulso)
    for q in P:
        age = t - q["b"]
        if not 0 <= age <= q["L"]: continue
        env = math.sin(math.pi * age / q["L"]) ** 0.8
        cx = q["x"] + q["sw"] * math.sin(2 * math.pi * q["f"] * age + q["ph"])
        cy = q["y"] - q["vy"] * age
        cxz, cyz = (cx - W / 2) * z + W / 2 + dx, (cy - H / 2) * z + H / 2 + dy
        blit(fr, SP, cxz, cyz, q["r"] * 5.5, q["c"], 0.95 * env)
    for k, (fx, fy) in enumerate(ESTRELAS):
        tw = 0.30 + 0.70 * (0.5 + 0.5 * math.sin(2 * math.pi * (0.45 + 0.1 * k) * t + k * 1.7))
        cx, cy = (fx * W - W / 2) * z + W / 2 + dx, (fy * H - H / 2) * z + H / 2 + dy
        blit(fr, CR, cx, cy, 46 + 14 * tw, (190, 225, 255), 0.85 * tw)
    p.stdin.write(np.clip(fr, 0, 255).astype(np.uint8).tobytes())
p.stdin.close(); p.wait()
print(out, n, "quadros")
