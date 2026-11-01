"""Gaspar V2V: o cenário e a roupa mudam, o André fica igual (rosto, gestos, voz).

    PY v2v.py preparar gravacao.mp4 mundos.json SAIDA   # áudio, transcrição, cortes → SAIDA/segments.json (grátis)
    PY v2v.py rascunho SAIDA [--task ID]                 # Wan VACE 480p (~US$ 0,05/s) → SAIDA/rascunho.mp4
    PY v2v.py final SAIDA [--pro] [--aprovado-ate 4.2]   # Kling O3 (~US$ 0,126/s) → SAIDA/final.mp4

Ordem fixa: V2V primeiro, legendas e cartões do kit depois (a IA não deforma texto). Depois do final, rode o
gaspar-scene-kit com `"gravacao": "final.mp4"` para pôr legenda e cartões por cima.

PY = python da venv das functions do Hermes (Firestore, Storage); a transcrição usa a venv da tutorial-sistema.
Cada chamada paga passa por functions/video/fal.py: teto de US$ 5 por job e registro em videoJobs.
mundos.json: [{"nome": "escritorio", "cenario": "...", "roupa": "..."}, ...] (em inglês rende mais nos modelos).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "functions"))

CORTE_MIN_S, CORTE_MAX_S, KLING_MIN_S = 5.0, 10.0, 3.0
FPS = 30
BUCKET = "gestao-hermes-video"
MODELOS = {
    "rascunho": "fal-ai/wan-vace-apps/video-edit",
    "final": "fal-ai/kling-video/o3/standard/video-to-video/edit",
    "final-pro": "fal-ai/kling-video/o3/pro/video-to-video/edit",
    "referencia": "fal-ai/nano-banana",
}
PROMPT_V2V = ("Keep the person exactly identical: same face, facial expressions, lip movements, gestures, motion "
              "and camera framing. Change the background to {cenario}. Change the clothing to {roupa}. "
              "Match the lighting on the person to the new background. Photorealistic, no text.")


# ---------------------------------------------------------------- cortes

def segmentar(palavras: list[dict], duracao: float, minimo: float = CORTE_MIN_S, maximo: float = CORTE_MAX_S) -> list[dict]:
    """Cortes de `minimo`–`maximo` s que caem no silêncio entre palavras, de preferência em fim de frase.

    `palavras`: [{text, startMs, endMs}] (legendas.py fala). Nunca corta no meio de uma palavra; o último
    trecho curto (< 3 s, mínimo do Kling) é juntado ao anterior quando cabe.
    """
    # Pontos de corte possíveis: meio do intervalo entre duas palavras, com peso para fim de frase.
    pontos = []
    for a, b in zip(palavras, palavras[1:]):
        t = (a["endMs"] + b["startMs"]) / 2000
        fim_frase = bool(re.search(r"[.!?…]$", a["text"].strip()))
        pontos.append((t, fim_frase, (b["startMs"] - a["endMs"]) / 1000))
    cortes, ini = [], 0.0
    while duracao - ini > maximo:
        janela = [p for p in pontos if ini + minimo <= p[0] <= ini + maximo]
        if janela:
            frases = [p for p in janela if p[1]]
            t = frases[-1][0] if frases else max(janela, key=lambda p: p[2])[0]
        else:
            t = ini + maximo  # fala corrida sem pausa nenhuma na janela: corta no máximo
        cortes.append((ini, t))
        ini = t
    cortes.append((ini, duracao))
    if len(cortes) > 1 and cortes[-1][1] - cortes[-1][0] < KLING_MIN_S and cortes[-1][1] - cortes[-2][0] <= maximo:
        cortes[-2:] = [(cortes[-2][0], duracao)]
    texto = lambda i, f: "".join(p["text"] for p in palavras if i <= p["startMs"] / 1000 < f).strip()
    return [{"i": n, "inicio": round(i, 3), "fim": round(f, 3), "texto": texto(i, f)} for n, (i, f) in enumerate(cortes)]


def distribuir_mundos(cortes: list[dict], mundos: list[dict]) -> list[dict]:
    """Um mundo por corte, em sequência (com 2 mundos e 4 cortes: A, B, A, B)."""
    return [{**c, "mundo": mundos[c["i"] % len(mundos)]["nome"]} for c in cortes]


def prompt(mundo: dict, modelo: str) -> str:
    p = PROMPT_V2V.format(**mundo)
    if "kling" in modelo:  # o Kling referencia as entradas por @Video1 / @Image1
        p = "In @Video1: " + p + " Use @Image1 as the reference for the setting and outfit."
    return p


# ---------------------------------------------------------------- ffmpeg

def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def duracao(arq: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                          "csv=p=0", str(arq)]).decode().strip())


def recortar(gravacao: Path, c: dict, destino: Path) -> Path:
    """Trecho mudo, 30 fps, vertical 1080×1920 (o Kling pede 720–2160 px; celular grava 120 fps)."""
    ffmpeg("-ss", f"{c['inicio']:.3f}", "-to", f"{c['fim']:.3f}", "-i", str(gravacao), "-an",
           "-vf", f"fps={FPS},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(destino))
    return destino


def remux(clipes: list[Path], cortes: list[dict], audio: Path, destino: Path) -> Path:
    """Junta os clipes gerados, cada um aparado/estendido à duração EXATA do corte, sobre o áudio original
    contínuo. Corrige modelo que regera som ou devolve clipe com duração/fps diferentes."""
    entradas, filtros = [], []
    for k, (arq, c) in enumerate(zip(clipes, cortes)):
        d = c["fim"] - c["inicio"]
        entradas += ["-i", str(arq)]
        filtros.append(f"[{k}:v]fps={FPS},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
                       f"tpad=stop_mode=clone:stop_duration={d:.3f},trim=duration={d:.3f},setpts=PTS-STARTPTS[v{k}]")
    filtros.append("".join(f"[v{k}]" for k in range(len(clipes))) + f"concat=n={len(clipes)}:v=1:a=0[v]")
    ffmpeg(*entradas, "-i", str(audio), "-filter_complex", ";".join(filtros), "-map", "[v]", "-map", f"{len(clipes)}:a",
           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", str(destino))
    return destino


# ---------------------------------------------------------------- nuvem

def _db():
    from google.cloud import firestore

    return firestore.Client(project="gestao-hermes")


def publicar(arq: Path, chave: str) -> str:
    """Sobe ao bucket do Hermes Vídeo e devolve URL assinada de 2 h (o fal baixa por ela)."""
    from datetime import timedelta

    from google.cloud import storage

    blob = storage.Client(project="gestao-hermes").bucket(BUCKET).blob(f"tmp/v2v/{chave}")
    blob.upload_from_filename(str(arq))
    return blob.generate_signed_url(version="v4", expiration=timedelta(hours=2), method="GET")


def rodar_fal(modelo: str, entrada: dict, *, segundos: float = 0, task_id: str | None = None,
              aprovado: float = 0, pendente: Path | None = None) -> dict:
    """Roda um job; se passar do tempo, grava o job_fal em `pendente` e a próxima execução só o retoma."""
    from video import fal

    if pendente and pendente.exists():
        r = fal.executar_tool(_db(), "andre-v2v", {"job_fal": pendente.read_text().strip()})
    else:
        r = fal.executar_tool(_db(), "andre-v2v", {"modelo": modelo, "entrada": entrada, "segundos": segundos,
                                                  "task_id": task_id, "aprovado_ate_usd": aprovado})
    if pendente and r.get("status") in ("IN_QUEUE", "IN_PROGRESS") and r.get("job_fal"):
        pendente.write_text(r["job_fal"])
        raise SystemExit(f"Ainda rodando no fal ({r['job_fal']}). Rode o mesmo comando de novo daqui a pouco: "
                         "ele retoma este job sem cobrar outra vez.")
    if pendente and pendente.exists() and r.get("status") in ("COMPLETED", "FAILED"):
        pendente.unlink()
    if r.get("status") == "confirmation_required":
        raise SystemExit(f"Custo US$ {r['custo_estimado_usd']:.2f} passa do teto: mostre ao André e rode de novo "
                         f"com --aprovado-ate {r['custo_estimado_usd']}.")
    if r.get("erro") or r.get("status") != "COMPLETED":
        raise SystemExit(f"fal: {r.get('erro') or r.get('mensagem')}")
    return r


def baixar(url: str, destino: Path) -> Path:
    with urllib.request.urlopen(url, timeout=300) as r:
        destino.write_bytes(r.read())
    return destino


def gerar_referencia(mundo: dict, pasta: Path, task_id: str | None) -> str:
    """Imagem do cenário/figurino (sem pessoa), uma por mundo, com cache. Devolve a URL."""
    cache = pasta / f"ref-{mundo['nome']}.json"
    if cache.exists():
        return json.loads(cache.read_text())["url"]
    r = rodar_fal(MODELOS["referencia"], {"prompt": f"Photorealistic vertical photo of {mundo['cenario']}, no people. "
                                                    f"On a mannequin in the foreground: {mundo['roupa']}.",
                                          "aspect_ratio": "9:16", "num_images": 1}, task_id=task_id)
    baixar(r["urls"][0], pasta / f"ref-{mundo['nome']}.png")
    cache.write_text(json.dumps({"url": r["urls"][0], "job": r["job_fal"]}))
    return r["urls"][0]


def rodar_v2v(etapa: str, pasta: Path, *, task_id: str | None, aprovado: float) -> list[Path]:
    seg = json.loads((pasta / "segments.json").read_text(encoding="utf-8"))
    mundos = {m["nome"]: m for m in seg["mundos"]}
    modelo = MODELOS[etapa]
    total = sum(c["fim"] - c["inicio"] for c in seg["cortes"])
    from video import fal

    custo = fal.estimar_custo(modelo, segundos=total, tabela=fal.precos(_db()))
    print(f"{etapa}: {len(seg['cortes'])} cortes, {total:.1f} s, ~US$ {custo:.2f} ({modelo})", flush=True)
    saidas = []
    for c in seg["cortes"]:
        destino = pasta / etapa / f"corte-{c['i']}.mp4"
        destino.parent.mkdir(exist_ok=True)
        if destino.exists():
            saidas.append(destino)
            continue
        mundo = mundos[c["mundo"]]
        url_video = publicar(pasta / "cortes" / f"corte-{c['i']}.mp4", f"{pasta.name}/{c['i']}.mp4")
        ref = gerar_referencia(mundo, pasta, task_id)
        d = c["fim"] - c["inicio"]
        if etapa == "rascunho":
            entrada = {"prompt": prompt(mundo, modelo), "video_url": url_video, "video_type": "human",
                       "image_urls": [ref], "resolution": "480p", "aspect_ratio": "9:16"}
        else:
            entrada = {"prompt": prompt(mundo, modelo), "video_url": url_video, "image_urls": [ref], "keep_audio": True}
        # O teto vale por job (corte); a aprovação do André cobre o vídeo todo.
        r = rodar_fal(modelo, entrada, segundos=d, task_id=task_id, aprovado=aprovado,
                      pendente=destino.with_suffix(".job"))
        baixar(r["urls"][0], destino)
        print(f"  corte {c['i'] + 1} ({c['mundo']}, {d:.1f} s): US$ {r['custo_real_usd']:.2f}", flush=True)
        saidas.append(destino)
    return saidas


# ---------------------------------------------------------------- comandos

def preparar(gravacao: Path, mundos_arq: Path, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "cortes").mkdir(exist_ok=True)
    ffmpeg("-i", str(gravacao), "-vn", "-ac", "1", "-ar", "48000", str(pasta / "audio.wav"))
    kit = Path(os.environ.get("GASPAR_SCENE_KIT") or RAIZ / "skills" / "gaspar-scene-kit")
    py_voz = os.environ.get("GASPAR_PY") or str(Path.home() / ".tutorial-sistema" / ".venv" / "Scripts" / "python.exe")
    if not (pasta / "legendas.json").exists():
        subprocess.run([py_voz, str(kit / "scripts" / "legendas.py"), "fala", str(gravacao), str(pasta)], check=True)
    palavras = json.loads((pasta / "legendas.json").read_text(encoding="utf-8"))
    mundos = json.loads(mundos_arq.read_text(encoding="utf-8"))
    cortes = distribuir_mundos(segmentar(palavras, duracao(gravacao)), mundos)
    for c in cortes:
        recortar(gravacao, c, pasta / "cortes" / f"corte-{c['i']}.mp4")
    (pasta / "segments.json").write_text(json.dumps({"gravacao": str(gravacao), "mundos": mundos, "cortes": cortes},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
    for c in cortes:
        print(f"corte {c['i'] + 1}: {c['inicio']:.1f}–{c['fim']:.1f} s [{c['mundo']}] {c['texto']}")


def main():
    cmd = sys.argv[1]
    opc = lambda nome, padrao=None: sys.argv[sys.argv.index(nome) + 1] if nome in sys.argv else padrao
    if cmd == "preparar":
        preparar(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
        return
    pasta = Path(sys.argv[2])
    etapa = "rascunho" if cmd == "rascunho" else ("final-pro" if "--pro" in sys.argv else "final")
    clipes = rodar_v2v(etapa, pasta, task_id=opc("--task"), aprovado=float(opc("--aprovado-ate", 0)))
    cortes = json.loads((pasta / "segments.json").read_text(encoding="utf-8"))["cortes"]
    saida = remux(clipes, cortes, pasta / "audio.wav", pasta / ("rascunho.mp4" if cmd == "rascunho" else "final.mp4"))
    print(f"→ {saida}")


if __name__ == "__main__":
    main()
