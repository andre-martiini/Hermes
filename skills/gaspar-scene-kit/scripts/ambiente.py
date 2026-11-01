"""Som de ambiente (cafeteria, auditório, rua…) gerado por texto, em loop sem emenda, com cache/biblioteca.

    PY ambiente.py "prompt" SEGUNDOS        # imprime o caminho do loop (WAV 48 kHz, −14 LUFS) e o custo

Gera um trecho de até 20 s com `loop: true` (o pos.mjs repete o trecho até cobrir a cena) no ElevenLabs Sound
Effects v2 via fal (US$ 0,002/s, registrado em videoJobs); se o fal falhar, no ElevenLabs direto (créditos do
plano: ~10 por segundo). Teste comparativo de 01/11/2026 no PR do Gaspar Vídeo v2.

Biblioteca: cada som gerado fica em ~/.tutorial-sistema/ambientes/ com o prompt, o motor, a data e a licença em
catalogo.json; o mesmo prompt nunca é cobrado de novo (funciona offline depois da 1ª vez).
Credencial: GOOGLE_APPLICATION_CREDENTIALS (Firestore: chaves fal_key/elevenlabs_api_key).
"""
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
BIBLIOTECA = Path.home() / ".tutorial-sistema" / "ambientes"
TRECHO_MAX = 20.0  # o fal aceita até 22 s; a emenda do loop é do próprio modelo
LICENCA = "Gerado no ElevenLabs Sound Effects (plano pago: uso comercial permitido)"


def _gerar(prompt: str, seg: float, bruto: Path) -> tuple[str, float]:
    sys.path.insert(0, str(RAIZ / "functions"))
    sys.path.insert(0, str(RAIZ / "skills" / "gaspar-v2v" / "scripts"))
    entrada = {"text": prompt, "duration_seconds": seg, "loop": True, "prompt_influence": 0.4}
    from v2v import rodar_fal

    try:
        r = rodar_fal("fal-ai/elevenlabs/sound-effects/v2", entrada, segundos=seg)
    except (SystemExit, Exception) as e:  # noqa: BLE001 — o fal não gerou (fora do ar, sem saldo): ElevenLabs direto
        if "aprovado-ate" in str(e):  # teto de custo: nunca contornar a aprovação
            raise
        print(f"aviso: fal indisponível para o ambiente ({str(e)[:120]}); usando o ElevenLabs direto", file=sys.stderr)
    else:
        urllib.request.urlretrieve(r["urls"][0], bruto)  # já pago: se o download falhar, falha (sem gerar de novo)
        return "fal-ai/elevenlabs/sound-effects/v2", float(r.get("custo_real_usd") or seg * 0.002)
    import requests
    from efeitos import _chave_eleven

    r = requests.post("https://api.elevenlabs.io/v1/sound-generation", headers={"xi-api-key": _chave_eleven()},
                      json=entrada, timeout=180)
    r.raise_for_status()
    bruto.write_bytes(r.content)
    return "elevenlabs-direto", 0.0  # créditos do plano (≈10/s), não dólares avulsos


def ambiente(prompt: str, segundos: float) -> dict:
    seg = round(min(max(segundos, 2.0), TRECHO_MAX), 1)
    chave = hashlib.sha1(f"{prompt.strip().lower()}|{seg}|loop".encode()).hexdigest()[:12]
    BIBLIOTECA.mkdir(parents=True, exist_ok=True)
    wav = BIBLIOTECA / f"amb-{chave}.wav"
    cat_arq = BIBLIOTECA / "catalogo.json"
    catalogo = json.loads(cat_arq.read_text(encoding="utf8")) if cat_arq.exists() else {}
    if wav.exists():
        return {"arquivo": str(wav), "custo_usd": 0.0, "motor": catalogo.get(wav.name, {}).get("motor"), "cache": True}
    bruto = BIBLIOTECA / f"amb-{chave}.mp3"
    motor, custo = _gerar(prompt, seg, bruto)
    # Nível de referência fixo (−14 LUFS): o "nivel_db" do roteiro passa a ser relativo à voz.
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(bruto), "-af", "loudnorm=I=-14:TP=-2:LRA=11",
                    "-ar", "48000", "-ac", "2", str(wav)], check=True)
    bruto.unlink()
    catalogo[wav.name] = {"prompt": prompt, "segundos": seg, "loop": True, "motor": motor, "custo_usd": custo,
                          "gerado_em": time.strftime("%Y-%m-%d"), "licenca": LICENCA}
    cat_arq.write_text(json.dumps(catalogo, indent=1, ensure_ascii=False), encoding="utf8")
    return {"arquivo": str(wav), "custo_usd": custo, "motor": motor, "cache": False}


if __name__ == "__main__":
    print(json.dumps(ambiente(sys.argv[1], float(sys.argv[2])), ensure_ascii=False))
