"""Anima uma ilustração estática (imagem → vídeo no Veo 3.1 Lite da Vertex), mantendo o estilo da arte.

    PY animar.py imagem.png SEGUNDOS saida.mp4 [16:9|9:16]

Movimento discreto: elementos flutuando, leve aproximação da câmera; sem texto nem elementos novos.
Custo: US$ 0,05/s (clipes de 4, 6 ou 8 s). Credencial: GOOGLE_APPLICATION_CREDENTIALS (projeto gestao-hermes).
PY = venv da tutorial-sistema (google-genai); usa o adaptador do Hermes Vídeo (functions/video/veo_provider.py).
"""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "functions"))

PROMPT = ("Animate this illustration with subtle, smooth, continuous motion: the elements gently float and drift in "
          "place, small parts animate softly, slow camera push-in. Keep exactly the same art style, colors and "
          "composition. No new objects, no text, no people.")
NEGATIVO = "text, letters, people, hands, fast motion, morphing, flicker, scene change, camera cut"


def main():
    imagem, segundos, destino = Path(sys.argv[1]), float(sys.argv[2]), Path(sys.argv[3])
    aspecto = sys.argv[4] if len(sys.argv) > 4 else "16:9"
    from video.veo_provider import PedidoClipe, VertexVeoProvider

    dur = next((d for d in (4, 6, 8) if d >= segundos), 8)
    png = imagem.read_bytes()
    if imagem.suffix.lower() not in (".png",):
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.open(imagem).convert("RGB").save(buf, "PNG")
        png = buf.getvalue()
    veo = VertexVeoProvider()
    op = veo.gerar_clipe(PedidoClipe(modelo="veo-3.1-lite-generate-001", prompt=PROMPT, imagem_inicio=png,
                                     duracao_s=dur, aspecto=aspecto, negativo=NEGATIVO))
    while not (r := veo.consultar_operacao(op)).concluida:
        time.sleep(5)
    if r.erro or r.bloqueado:
        raise SystemExit(f"Veo: {r.erro or r.motivo_bloqueio}")
    destino.write_bytes(veo.baixar(r))
    print(f"{destino.name}: {dur} s, ~US$ {dur * 0.05:.2f}")


if __name__ == "__main__":
    main()
