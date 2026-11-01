"""Legendas palavra a palavra.

Modo motion: o texto é o do roteiro (zero erro de grafia); o whisper só dá o tempo de cada palavra.
O alinhamento casa as palavras do roteiro com as reconhecidas (difflib) e interpola as que não casaram.

Modo fala (sobreposição, tutorial): o André fala livre, então o texto é o reconhecido; palavras com
confiança < 0,6 vão para a lista de revisão (nomes próprios como Ifes, SIPAC, Gaspar).

    PY legendas.py motion roteiro.json SAIDA               # usa SAIDA/narracao/falas.json (narrar.py)
    PY legendas.py fala gravacao.mp4 SAIDA [--chaves "Ifes,SIPAC,Gaspar"]

Saída no formato Caption do Remotion/HyperFrames: {text, startMs, endMs, timestampMs, confidence}, com o
espaço em branco ANTES de cada palavra. A paginação (300 ms palavra a palavra, 1200 ms frases) é do montar.mjs. Modelo: GASPAR_WHISPER_MODELO (padrão small; medium é mais exato).
"""
import difflib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

CONFIANCA_MINIMA = 0.6
CHAVES_PADRAO = ["Ifes", "SIPAC", "Gaspar", "Hermes", "PROEN", "Reditec", "MAGO"]


def _norm(p: str) -> str:
    p = unicodedata.normalize("NFKD", p.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in p if not unicodedata.combining(c)))


def _ffmpeg() -> str:
    import shutil

    if shutil.which("ffmpeg"):
        return "ffmpeg"
    import imageio_ffmpeg  # vem com a venv da tutorial-sistema

    return imageio_ffmpeg.get_ffmpeg_exe()


def transcrever(audio: Path, chaves: list[str]) -> list[dict]:
    """[{w, s, e, p}] em segundos, com probabilidade por palavra."""
    from faster_whisper import WhisperModel

    import numpy as np

    # Decodifica com o ffmpeg (o PyAV do faster-whisper briga com versões novas do av).
    bruto = subprocess.run([_ffmpeg(), "-loglevel", "error", "-i", str(audio), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                           capture_output=True, check=True).stdout
    modelo = WhisperModel(os.environ.get("GASPAR_WHISPER_MODELO", "small"), device="cpu", compute_type="int8")
    trechos, _ = modelo.transcribe(np.frombuffer(bruto, np.float32), language="pt", word_timestamps=True, vad_filter=False,
                                   initial_prompt="Vocabulário: " + ", ".join(chaves) + ".")
    return [{"w": w.word.strip(), "s": w.start, "e": w.end, "p": w.probability}
            for t in trechos for w in (t.words or []) if w.word.strip()]


def alinhar(texto: str, reconhecidas: list[dict], duracao: float) -> list[dict]:
    """Palavras do roteiro com o tempo das reconhecidas. Sem par → interpola pelo tamanho entre vizinhas."""
    palavras = texto.split()
    a = [_norm(p) for p in palavras]
    b = [_norm(r["w"]) for r in reconhecidas]
    tempos: list[tuple[float, float, float] | None] = [None] * len(palavras)
    for bloco in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_matching_blocks():
        for k in range(bloco.size):
            r = reconhecidas[bloco.b + k]
            tempos[bloco.a + k] = (r["s"], r["e"], r["p"])
    # Buracos (palavra que o whisper ouviu diferente, ex.: "Sipaque" por SIPAC): reparte o intervalo
    # entre os vizinhos casados proporcionalmente ao número de letras. Confiança fica a do vizinho × 0,9.
    i = 0
    while i < len(palavras):
        if tempos[i] is not None:
            i += 1
            continue
        j = i
        while j < len(palavras) and tempos[j] is None:
            j += 1
        ini = tempos[i - 1][1] if i > 0 else 0.0
        fim = tempos[j][0] if j < len(palavras) else max(duracao, ini + 0.3 * (j - i))
        conf = 0.9 * min([tempos[k][2] for k in (i - 1, j) if 0 <= k < len(palavras) and tempos[k]] or [0.5])
        pesos = [max(len(a[k]), 1) for k in range(i, j)]
        t = ini
        for k, peso in zip(range(i, j), pesos):
            d = (fim - ini) * peso / sum(pesos)
            tempos[k] = (t, t + d, conf)
            t += d
        i = j
    return [{"text": (" " if n else "") + p, "startMs": round(s * 1000), "endMs": round(e * 1000),
             "timestampMs": round((s + e) / 2 * 1000), "confidence": round(c, 3)}
            for n, (p, (s, e, c)) in enumerate(zip(palavras, tempos))]


def da_fala(reconhecidas: list[dict]) -> list[dict]:
    return [{"text": (" " if n else "") + r["w"], "startMs": round(r["s"] * 1000), "endMs": round(r["e"] * 1000),
             "timestampMs": round((r["s"] + r["e"]) / 2 * 1000), "confidence": round(r["p"], 3)}
            for n, r in enumerate(reconhecidas)]


def revisar(legendas: list[dict]) -> list[str]:
    return [f'{c["text"].strip()} ({c["startMs"] / 1000:.1f} s, {c["confidence"]:.2f})'
            for c in legendas if c["confidence"] < CONFIANCA_MINIMA]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    modo, entrada, saida = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    chaves = CHAVES_PADRAO
    if "--chaves" in sys.argv:
        chaves = sys.argv[sys.argv.index("--chaves") + 1].split(",")
    saida.mkdir(parents=True, exist_ok=True)
    if modo == "motion":
        falas = json.loads((saida / "narracao" / "falas.json").read_text(encoding="utf-8"))
        por_cena = []
        for f in falas:
            if not f["wav"]:
                por_cena.append([])
                continue
            leg = alinhar(f["texto"], transcrever(saida / "narracao" / f["wav"], chaves), f["segundos"])
            por_cena.append(leg)
            print(f"cena {f['i'] + 1}: {len(leg)} palavras", flush=True)
        (saida / "legendas.json").write_text(json.dumps(por_cena, ensure_ascii=False, indent=1), encoding="utf-8")
        baixas = [r for leg in por_cena for r in revisar(leg)]
    else:
        wav = saida / "fala.wav"
        subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-i", str(entrada), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                       check=True)
        leg = da_fala(transcrever(wav, chaves))
        (saida / "legendas.json").write_text(json.dumps(leg, ensure_ascii=False, indent=1), encoding="utf-8")
        baixas = revisar(leg)
    if baixas:
        print("Revisar (confiança < 0,6) — corrija em legendas.json e registre no diário da ação:")
        for b in baixas:
            print("  · " + b)


if __name__ == "__main__":
    main()
