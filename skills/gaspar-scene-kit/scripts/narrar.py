"""Narração das cenas: voz Aoede do motor da tutorial-sistema (mesma voz, estilo e cache do motion.py).

    PY narrar.py roteiro.json SAIDA    # → SAIDA/narracao/cena-<i>.wav e SAIDA/narracao/falas.json

Custo: ~US$ 0,15 por minuto de fala; o cache (chave = texto + voz) faz refazer sair de graça.
Rode com o PY da venv da tutorial-sistema (`preparar.py` devolve PY=...).
"""
import json
import sys
import wave
from pathlib import Path

ESTILO_VOZ = ("Leia em português do Brasil, com sotaque neutro, como uma apresentadora explicando um assunto a "
              "colegas de trabalho: tom calmo, claro e confiante, ritmo tranquilo, pequenas pausas entre as ideias")


def _motor() -> Path:
    achados = sorted((Path.home() / ".claude" / "skills").glob("**/tutorial-sistema/scripts/gerar_tutorial.py"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    if not achados:
        raise SystemExit("Falta a skill tutorial-sistema (scripts/gerar_tutorial.py), que tem a voz.")
    return achados[0].parent


def main():
    roteiro_arq, saida = Path(sys.argv[1]), Path(sys.argv[2])
    sys.path.insert(0, str(_motor()))
    import gerar_tutorial as gt

    gt.ESTILO = ESTILO_VOZ  # o mesmo tom do motion.py (apresentadora, não instrutora de sistema)
    roteiro = json.loads(roteiro_arq.read_text(encoding="utf-8"))
    pasta = saida / "narracao"
    pasta.mkdir(parents=True, exist_ok=True)
    falas = []
    for i, cena in enumerate(roteiro["cenas"]):
        texto = (cena.get("narracao") or "").strip()
        if not texto:
            falas.append({"i": i, "wav": None, "segundos": 0, "texto": ""})
            continue
        pcm, taxa = gt.narrar(texto, roteiro.get("pronuncia", {}), saida / "cache-voz")
        arq = pasta / f"cena-{i}.wav"
        with wave.open(str(arq), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(taxa)
            w.writeframes(pcm)
        falas.append({"i": i, "wav": arq.name, "segundos": round(len(pcm) / 2 / taxa, 3), "texto": texto})
        print(f"cena {i + 1}: {falas[-1]['segundos']:.1f} s", flush=True)
    # Só regrava se mudou: o montar.mjs refaz o alinhamento (whisper, ~40 s) quando falas.json é mais novo.
    novo, arq = json.dumps(falas, ensure_ascii=False, indent=2), pasta / "falas.json"
    if not arq.exists() or arq.read_text(encoding="utf-8") != novo:
        arq.write_text(novo, encoding="utf-8")


if __name__ == "__main__":
    main()
