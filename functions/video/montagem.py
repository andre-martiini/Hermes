"""Montagem do vídeo final com ffmpeg (functions e worker usam o mesmo código).

Os clipes são gerados em sequência: o clipe i começa no ÚLTIMO QUADRO REAL do
clipe i-1 (decisão da Fase 0 — o Lite não chega ao `lastFrame` pedido, então
emendar por quadro-chave deixava salto). Com isso o 1º quadro do clipe i repete o
último do anterior e é descartado na concatenação; cada cena depois da primeira
dura 1 quadro a menos, e os tempos da narração e da legenda usam essas durações
reais.

ffmpeg: o do `imageio-ffmpeg` (já nas dependências das functions; o worker também
o usa). Ele tem libx264, libass (legenda), loudnorm e sidechaincompress.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

FPS = 24
QUADRO_S = 1 / FPS
LUFS_ALVO = -16
MUSICA_DB = -18
TAMANHO = {"16:9": (1280, 720), "9:16": (720, 1280)}


def ffmpeg_exe() -> str:
    """`FFMPEG_BIN` (o worker aponta para o ffmpeg do Debian, com fontconfig e as fontes
    DejaVu da legenda); fora dele, o binário do `imageio-ffmpeg`."""
    import os

    if os.environ.get("FFMPEG_BIN"):
        return os.environ["FFMPEG_BIN"]
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _rodar(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run([ffmpeg_exe(), "-hide_banner", "-y", *args], cwd=cwd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou ({proc.returncode}): {proc.stderr.decode(errors='replace')[-800:]}")
    return proc


def duracao(mp4: bytes) -> float:
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "v.mp4"
        arq.write_bytes(mp4)
        proc = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(arq)], capture_output=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", proc.stderr.decode(errors="replace"))
    if not m:
        raise RuntimeError("Não consegui ler a duração do vídeo.")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def ultimo_quadro(mp4: bytes) -> bytes:
    """PNG do último quadro — o ponto de partida do clipe seguinte."""
    with tempfile.TemporaryDirectory() as tmp:
        ent, sai = Path(tmp) / "c.mp4", Path(tmp) / "q.png"
        ent.write_bytes(mp4)
        _rodar(["-sseof", "-0.25", "-i", str(ent), "-update", "1", "-frames:v", "99", str(sai)])
        return sai.read_bytes()


def inicios_das_cenas(duracoes: list[float]) -> list[float]:
    """Início de cada cena no vídeo final: a partir da 2ª, cada clipe perde o 1º quadro."""
    inicios, t = [], 0.0
    for i, d in enumerate(duracoes):
        inicios.append(round(t, 4))
        t += d - (QUADRO_S if i > 0 else 0)
    return inicios


def duracao_total(duracoes: list[float]) -> float:
    return round(sum(duracoes) - QUADRO_S * max(len(duracoes) - 1, 0), 4)


def _tempo_srt(s: float) -> str:
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    seg, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{seg:02d},{ms:03d}"


def gerar_srt(textos: list[str], inicios: list[float], fins: list[float]) -> str:
    blocos, n = [], 0
    for texto, ini, fim in zip(textos, inicios, fins):
        if not (texto or "").strip() or fim <= ini:
            continue
        n += 1
        blocos.append(f"{n}\n{_tempo_srt(ini)} --> {_tempo_srt(fim)}\n{texto.strip()}\n")
    return "\n".join(blocos)


def trilha_de_narracao(narracoes: list[tuple[bytes, int] | None], inicios: list[float], total_s: float,
                       taxa: int = 24000) -> bytes:
    """PCM 16 bits mono com cada narração começando no início da sua cena."""
    import numpy as np

    trilha = np.zeros(int(round(total_s * taxa)), dtype=np.int16)
    for narr, ini in zip(narracoes, inicios):
        if not narr:
            continue
        pcm, t = narr
        if t != taxa:
            raise ValueError(f"Narração a {t} Hz; a montagem espera {taxa} Hz.")
        a = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype=np.int16)
        pos = int(round(ini * taxa))
        fim = min(pos + a.size, trilha.size)
        if fim > pos:
            trilha[pos:fim] = a[: fim - pos]
    return trilha.tobytes()


def montar(clipes: list[bytes], duracoes: list[float], *, formato: str = "16:9",
           narracoes: list[tuple[bytes, int] | None] | None = None, textos: list[str] | None = None,
           legenda: bool = False, musica: bytes | None = None, taxa: int = 24000) -> bytes:
    """Clipes (MP4 sem áudio) + narração + música opcional + legenda → MP4 final."""
    from video import midia

    n = len(clipes)
    if n == 0 or n != len(duracoes):
        raise ValueError("Precisa de um clipe por cena, com a duração de cada um.")
    narracoes = narracoes or [None] * n
    textos = textos or [""] * n
    w, h = TAMANHO[formato]
    inicios = inicios_das_cenas(duracoes)
    total = duracao_total(duracoes)

    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        entradas = []
        for i, c in enumerate(clipes):
            (pasta / f"c{i}.mp4").write_bytes(c)
            entradas += ["-i", f"c{i}.mp4"]
        (pasta / "narr.wav").write_bytes(midia.pcm_para_wav(trilha_de_narracao(narracoes, inicios, total, taxa), taxa))
        entradas += ["-i", "narr.wav"]
        i_narr = n
        filtros = []
        for i in range(n):
            corte = ",trim=start_frame=1" if i > 0 else ""
            filtros.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                           f"fps={FPS},setsar=1,format=yuv420p{corte},setpts=PTS-STARTPTS[v{i}]")
        filtros.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vcat]")
        if legenda:
            fins = [ini + (len(narr[0]) / (2 * narr[1]) if narr else 0) for ini, narr in zip(inicios, narracoes)]
            (pasta / "legenda.srt").write_text(gerar_srt(textos, inicios, fins), encoding="utf-8")
            tam = 22 if formato == "16:9" else 14
            filtros.append(f"[vcat]subtitles=legenda.srt:force_style='FontName=DejaVu Sans,Fontsize={tam},"
                           f"Outline=2,MarginV=28'[vout]")
        else:
            filtros.append("[vcat]null[vout]")
        fala = f"[{i_narr}:a]aformat=sample_rates=48000:channel_layouts=stereo"
        if musica:
            (pasta / "musica.audio").write_bytes(musica)
            entradas += ["-stream_loop", "-1", "-i", "musica.audio"]
            filtros.append(f"{fala},asplit=2[fala][chave]")
            filtros.append(f"[{n + 1}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                           f"volume={MUSICA_DB}dB,atrim=0:{total}[mus]")
            filtros.append("[mus][chave]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[musd]")
            filtros.append("[fala][musd]amix=inputs=2:duration=first:normalize=0[mix]")
            filtros.append(f"[mix]loudnorm=I={LUFS_ALVO}:TP=-1.5:LRA=11,aresample=48000[aout]")
        elif any(narracoes):
            filtros.append(f"{fala},loudnorm=I={LUFS_ALVO}:TP=-1.5:LRA=11,aresample=48000[aout]")
        else:
            filtros.append(f"{fala}[aout]")  # só silêncio: nada a normalizar
        _rodar([*entradas, "-filter_complex", ";".join(filtros), "-map", "[vout]", "-map", "[aout]",
                "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "final.mp4"],
               cwd=str(pasta))
        return (pasta / "final.mp4").read_bytes()
