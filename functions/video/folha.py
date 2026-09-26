"""Folha de contato do storyboard: os quadros K0..KN numa grade, com a cena entre eles.

A cena i vai de K(i-1) a K(i). Cada célula mostra o quadro Ki; abaixo dele vão a
duração e o começo da narração da cena que TERMINA nele (K0 é só o início).
"""
from __future__ import annotations

import io
import textwrap

COLUNAS = 4
LARGURA_CELULA = 360
MARGEM = 16
LINHAS_TEXTO = 3


def _fonte(tamanho: int):
    from PIL import ImageFont

    for nome in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def montar(quadros: list[bytes], cenas: list[dict], formato: str, titulo: str) -> bytes:
    """`quadros[k]` = PNG de Kk (len = len(cenas)+1); `cenas` com ordem, duracao_s, narracao."""
    from PIL import Image, ImageDraw

    proporcao = 720 / 1280 if formato == "16:9" else 1280 / 720
    alt_img = round(LARGURA_CELULA * proporcao)
    alt_texto = 22 + LINHAS_TEXTO * 18
    alt_celula = alt_img + alt_texto
    linhas = (len(quadros) + COLUNAS - 1) // COLUNAS
    largura = COLUNAS * LARGURA_CELULA + (COLUNAS + 1) * MARGEM
    topo = 56
    altura = topo + linhas * (alt_celula + MARGEM) + MARGEM

    folha = Image.new("RGB", (largura, altura), (248, 248, 246))
    d = ImageDraw.Draw(folha)
    d.text((MARGEM, 16), titulo, fill=(20, 20, 20), font=_fonte(22))
    f_rotulo, f_texto = _fonte(16), _fonte(14)

    for k, png in enumerate(quadros):
        lin, col = divmod(k, COLUNAS)
        x = MARGEM + col * (LARGURA_CELULA + MARGEM)
        y = topo + lin * (alt_celula + MARGEM)
        img = Image.open(io.BytesIO(png)).convert("RGB").resize((LARGURA_CELULA, alt_img))
        folha.paste(img, (x, y))
        d.rectangle((x, y, x + 52, y + 26), fill=(20, 20, 20))
        d.text((x + 8, y + 4), f"K{k}", fill=(255, 255, 255), font=f_rotulo)
        if k == 0:
            legenda = "Início do vídeo"
        else:
            cena = cenas[k - 1]
            narracao = cena.get("narracao") or "(sem narração)"
            legenda = f"Cena {cena.get('ordem', k)} · {cena.get('duracao_s', '?')} s — {narracao}"
        linhas_txt = textwrap.wrap(legenda, width=44)[:LINHAS_TEXTO]
        for i, linha in enumerate(linhas_txt):
            d.text((x, y + alt_img + 6 + i * 18), linha, fill=(40, 40, 40), font=f_texto)

    out = io.BytesIO()
    folha.save(out, format="PNG", optimize=True)
    return out.getvalue()
