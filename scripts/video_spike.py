"""Hermes Vídeo — Fase 0: teste das premissas do Veo 3.1 (descartável, fora de produção).

Responde, com chamadas reais e gasto controlado, o que o plano deixou em aberto:
IDs exatos dos modelos, `lastFrame` no Lite, `generateAudio=false`, latência, e se
dois clipes encadeados por quadro-chave (K0→K1, K1→K2) emendam sem salto.

Etapas (rodar uma de cada vez, na ordem):

    python scripts/video_spike.py listar                      # custo zero
    python scripts/video_spike.py quadros                     # ~US$ 0,12 (3 imagens)
    python scripts/video_spike.py clipes --modelo lite        # ~US$ 0,40 (2 × 4 s)
    python scripts/video_spike.py clipes --modelo fast        # ~US$ 0,80–1,20 (2 × 4 s)
    python scripts/video_spike.py emendas                     # custo zero (analisa os MP4)

Provedor: `--provedor vertex` (padrão) usa a service account de
GOOGLE_APPLICATION_CREDENTIALS; `--provedor gemini` usa GEMINI_API_KEY.
Tudo sai em `--saida` (padrão: ./video_spike_out), com `relatorio.json` acumulando
o resultado de cada etapa.

Trava de gasto: cada etapa recusa rodar se o custo estimado acumulado no
relatório passar de `--teto-usd` (padrão US$ 5, o limite combinado com o André).
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJETO = "gestao-hermes"
LOCAL = "us-central1"

# Preços de referência do plano (US$). A Fase 0 existe para confirmar estes números
# no billing; aqui só servem para a trava de gasto e para a tabela final.
PRECO_IMAGEM = 0.04
PRECO_SEGUNDO = {"lite": 0.05, "fast": 0.15}

MODELO_IMAGEM_PADRAO = "gemini-2.5-flash-image"
ESTILO = (
    "Ilustração digital estilo flat 2D, paleta azul-petróleo e laranja suave, "
    "iluminação difusa, sem texto na imagem. Personagem: servidora pública de meia-idade, "
    "cabelo curto grisalho, óculos redondos, blazer azul-marinho, crachá no peito."
)
CENAS = [
    "Ela está sentada à mesa de um escritório, lendo uma pasta de documentos, câmera em plano médio.",
    "Ela se levanta da mesa segurando a pasta e sorri, câmera no mesmo plano médio.",
    "Ela caminha até a janela do escritório e olha para fora, câmera acompanha em plano médio.",
]
MOVIMENTO = [
    "A servidora termina de ler, fecha a pasta e começa a se levantar da cadeira. Movimento suave e natural, câmera fixa.",
    "A servidora caminha com a pasta até a janela e para olhando para fora. Câmera acompanha lentamente.",
]


def agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def carregar_relatorio(saida: Path) -> dict:
    arq = saida / "relatorio.json"
    if arq.exists():
        return json.loads(arq.read_text(encoding="utf-8"))
    return {"criado_em": agora(), "etapas": {}, "custo_estimado_usd": 0.0}


def salvar_relatorio(saida: Path, rel: dict):
    (saida / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")


def checar_teto(rel: dict, custo_da_etapa: float, teto: float):
    total = rel.get("custo_estimado_usd", 0.0) + custo_da_etapa
    if total > teto:
        sys.exit(f"Recusado: custo estimado acumulado US$ {total:.2f} passaria do teto de US$ {teto:.2f}.")


def cliente(provedor: str):
    from google import genai

    if provedor == "vertex":
        from google.oauth2 import service_account

        caminho = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not caminho:
            sys.exit("Defina GOOGLE_APPLICATION_CREDENTIALS com a service account.")
        cred = service_account.Credentials.from_service_account_file(
            caminho, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return genai.Client(vertexai=True, project=PROJETO, location=LOCAL, credentials=cred)
    chave = os.environ.get("GEMINI_API_KEY")
    if not chave:
        sys.exit("Defina GEMINI_API_KEY.")
    return genai.Client(api_key=chave)


# --- listar ---------------------------------------------------------------------------

def etapa_listar(cli, args, rel):
    nomes = []
    for m in cli.models.list():
        nome = getattr(m, "name", "") or ""
        if re.search(r"veo|image|tts|imagen", nome, re.I):
            nomes.append({
                "nome": nome,
                "acoes": list(getattr(m, "supported_actions", None) or []),
                "descricao": (getattr(m, "description", "") or "")[:120],
            })
    nomes.sort(key=lambda x: x["nome"])
    for n in nomes:
        print(f"{n['nome']:60s} {','.join(n['acoes'])}")
    if not nomes:
        print("Nenhum modelo de vídeo/imagem/TTS listado — a listagem da Vertex só traz modelos "
              "publicados que o projeto enxerga; teste os IDs direto com `clipes --id ...`.")
    rel["etapas"][f"listar_{args.provedor}"] = {"em": agora(), "modelos": nomes}


# --- quadros-chave --------------------------------------------------------------------

def gerar_imagem(cli, modelo, prompt, referencias, aspecto):
    from google.genai import types

    partes = [types.Part.from_bytes(data=r, mime_type="image/png") for r in referencias]
    partes.append(types.Part.from_text(text=prompt))
    t0 = time.monotonic()
    resp = cli.models.generate_content(
        model=modelo,
        contents=[types.Content(role="user", parts=partes)],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspecto),
        ),
    )
    for parte in resp.candidates[0].content.parts:
        if getattr(parte, "inline_data", None) and parte.inline_data.data:
            return parte.inline_data.data, time.monotonic() - t0
    raise RuntimeError(f"Modelo não devolveu imagem: {resp}")


def etapa_quadros(cli, args, rel):
    checar_teto(rel, PRECO_IMAGEM * len(CENAS), args.teto_usd)
    registros = []
    anterior = None
    for i, cena in enumerate(CENAS):
        prompt = f"{ESTILO}\n\nQuadro {i}: {cena}"
        if anterior is not None:
            prompt += ("\nMantenha EXATAMENTE a mesma personagem, roupa, cenário e estilo da imagem "
                       "de referência; mude só a pose e o enquadramento descritos.")
        dados, seg = gerar_imagem(cli, args.modelo_imagem, prompt, [anterior] if anterior else [], "16:9")
        arq = args.saida / f"K{i}.png"
        arq.write_bytes(dados)
        anterior = dados
        registros.append({"quadro": f"K{i}", "arquivo": arq.name, "segundos": round(seg, 1)})
        print(f"K{i}: {arq} ({seg:.1f}s)")
    rel["custo_estimado_usd"] = round(rel.get("custo_estimado_usd", 0.0) + PRECO_IMAGEM * len(CENAS), 3)
    rel["etapas"]["quadros"] = {"em": agora(), "modelo": args.modelo_imagem, "provedor": args.provedor,
                                "quadros": registros}


# --- clipes ---------------------------------------------------------------------------

def imagem(arq: Path):
    from google.genai import types

    return types.Image(image_bytes=arq.read_bytes(), mime_type="image/png")


def gerar_clipe(cli, modelo_id, prompt, inicio: Path, fim: Path, duracao, audio_off: bool):
    from google.genai import types

    cfg = dict(number_of_videos=1, duration_seconds=duracao, aspect_ratio="16:9", resolution="720p",
               last_frame=imagem(fim))
    if audio_off:
        cfg["generate_audio"] = False
    t0 = time.monotonic()
    op = cli.models.generate_videos(model=modelo_id, prompt=prompt, image=imagem(inicio),
                                    config=types.GenerateVideosConfig(**cfg))
    espera = 10
    while not op.done:
        time.sleep(espera)
        espera = min(espera + 5, 30)
        op = cli.operations.get(op)
    latencia = time.monotonic() - t0
    if op.error:
        raise RuntimeError(f"operação falhou: {op.error}")
    resp = op.response or op.result
    videos = getattr(resp, "generated_videos", None) or []
    if not videos:
        motivo = getattr(resp, "rai_media_filtered_reasons", None)
        raise RuntimeError(f"sem vídeo na resposta (filtro? {motivo})")
    return videos[0].video, latencia, op.name


def etapa_clipes(cli, args, rel):
    modelo_id = args.id or rel.get("ids", {}).get(args.modelo)
    if not modelo_id:
        sys.exit(f"Informe --id para o modelo '{args.modelo}' (veja a etapa listar).")
    for k in ("K0.png", "K1.png", "K2.png"):
        if not (args.saida / k).exists():
            sys.exit(f"Falta {k}: rode a etapa quadros antes.")
    custo = PRECO_SEGUNDO[args.modelo] * args.duracao * 2
    checar_teto(rel, custo, args.teto_usd)

    resultados = []
    for i in range(2):
        inicio, fim = args.saida / f"K{i}.png", args.saida / f"K{i + 1}.png"
        prompt = f"{ESTILO}\n\n{MOVIMENTO[i]}"
        tentativa = {"clipe": f"K{i}->K{i + 1}", "modelo": modelo_id, "duracao_s": args.duracao}
        audio_off = True
        try:
            video, lat, op_nome = gerar_clipe(cli, modelo_id, prompt, inicio, fim, args.duracao, audio_off)
        except Exception as exc:  # noqa: BLE001 - spike: registrar e tentar a alternativa
            texto = str(exc)
            tentativa["erro_com_audio_off"] = texto[:500]
            if re.search(r"generate_?audio|generateAudio", texto, re.I):
                audio_off = False
                video, lat, op_nome = gerar_clipe(cli, modelo_id, prompt, inicio, fim, args.duracao, False)
            else:
                resultados.append(tentativa)
                rel["etapas"][f"clipes_{args.modelo}"] = {"em": agora(), "resultados": resultados}
                salvar_relatorio(args.saida, rel)
                raise
        arq = args.saida / f"clipe_{args.modelo}_{i}.mp4"
        if getattr(video, "video_bytes", None):
            arq.write_bytes(video.video_bytes)
        else:
            cli.files.download(file=video)
            video.save(str(arq))
        tentativa.update({"arquivo": arq.name, "latencia_s": round(lat, 1), "operacao": op_nome,
                          "audio_desligado_aceito": audio_off, "last_frame_aceito": True})
        resultados.append(tentativa)
        print(f"{tentativa['clipe']}: {arq} em {lat:.0f}s (áudio off aceito: {audio_off})")
    rel.setdefault("ids", {})[args.modelo] = modelo_id
    rel["custo_estimado_usd"] = round(rel.get("custo_estimado_usd", 0.0) + custo, 3)
    rel["etapas"][f"clipes_{args.modelo}"] = {"em": agora(), "provedor": args.provedor, "resultados": resultados}


# --- emendas --------------------------------------------------------------------------

def ffmpeg_exe():
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def quadro(arq: Path, ultimo: bool, destino: Path):
    import subprocess

    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error"]
    cmd += ["-sseof", "-0.1", "-i", str(arq), "-update", "1"] if ultimo else ["-i", str(arq), "-frames:v", "1"]
    subprocess.run(cmd + [str(destino)], check=True)
    return destino


def diferenca(a: Path, b: Path) -> float:
    """Diferença média absoluta por pixel (0–255) entre dois quadros do mesmo tamanho."""
    import numpy as np
    from PIL import Image

    ia = np.asarray(Image.open(a).convert("RGB"), dtype=np.float32)
    ib = np.asarray(Image.open(b).convert("RGB").resize(Image.open(a).size), dtype=np.float32)
    return float(np.abs(ia - ib).mean())


def etapa_emendas(cli, args, rel):
    import subprocess

    saida = {}
    for modelo in ("lite", "fast"):
        c0, c1 = args.saida / f"clipe_{modelo}_0.mp4", args.saida / f"clipe_{modelo}_1.mp4"
        if not (c0.exists() and c1.exists()):
            continue
        fim0 = quadro(c0, True, args.saida / f"{modelo}_fim0.png")
        ini1 = quadro(c1, False, args.saida / f"{modelo}_ini1.png")
        ini0 = quadro(c0, False, args.saida / f"{modelo}_ini0.png")
        # Referência: o quanto o 1º quadro do clipe bate com K0 (o Veo respeita o `image`?)
        # e o quanto o último bate com K1 (respeita o `lastFrame`?).
        saida[modelo] = {
            "emenda_fim0_vs_ini1": round(diferenca(fim0, ini1), 2),
            "ini0_vs_K0": round(diferenca(ini0, args.saida / "K0.png"), 2),
            "fim0_vs_K1": round(diferenca(fim0, args.saida / "K1.png"), 2),
        }
        emendado = args.saida / f"emendado_{modelo}.mp4"
        filtro = "[0:v]setpts=PTS-STARTPTS[a];[1:v]trim=start_frame=1,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1[v]"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(c0), "-i", str(c1),
                        "-filter_complex", filtro, "-map", "[v]", "-an", str(emendado)], check=True)
        saida[modelo]["emendado"] = emendado.name
        print(modelo, saida[modelo])
    rel["etapas"]["emendas"] = {"em": agora(), "metrica": "diferença média absoluta por pixel, 0–255", **saida}


ETAPAS = {"listar": etapa_listar, "quadros": etapa_quadros, "clipes": etapa_clipes, "emendas": etapa_emendas}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("etapa", choices=list(ETAPAS))
    ap.add_argument("--provedor", choices=["vertex", "gemini"], default="vertex")
    ap.add_argument("--modelo", choices=["lite", "fast"], default="lite")
    ap.add_argument("--id", help="ID exato do modelo Veo (sobrepõe o que estiver no relatório)")
    ap.add_argument("--modelo-imagem", default=MODELO_IMAGEM_PADRAO)
    ap.add_argument("--duracao", type=int, default=4, choices=[4, 6, 8])
    ap.add_argument("--teto-usd", type=float, default=5.0)
    ap.add_argument("--saida", type=Path, default=Path("video_spike_out"))
    args = ap.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)

    rel = carregar_relatorio(args.saida)
    cli = None if args.etapa == "emendas" else cliente(args.provedor)
    try:
        ETAPAS[args.etapa](cli, args, rel)
    finally:
        salvar_relatorio(args.saida, rel)
    print(f"Custo estimado acumulado: US$ {rel['custo_estimado_usd']:.2f} — relatório em {args.saida / 'relatorio.json'}")


if __name__ == "__main__":
    main()
