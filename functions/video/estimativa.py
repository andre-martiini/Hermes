"""Preços, durações e estimativa de custo do Hermes Vídeo.

Os preços ficam em `config/video_precos` (Firestore) porque mudam de mês para mês;
`PRECOS_PADRAO` é só o ponto de partida quando o documento não existe ou não traz
um campo. Os valores abaixo são os da Fase 0 (26/09/2026) e ainda precisam ser
conferidos no export de billing — até lá, o custo "real" gravado pelo worker é
este mesmo preço vezes os segundos gerados.

Duração: o Veo 3.1 só gera clipes de 4, 6 ou 8 s. A narração de cada cena define
a duração do clipe (menor valor que caiba o áudio + folga); narração que passa de
7,7 s não cabe em clipe nenhum e a cena precisa ser dividida.
"""
from __future__ import annotations

import copy
import math
import re

DURACOES_CLIPE = (4, 6, 8)
FOLGA_AUDIO_S = 0.3
PALAVRAS_POR_SEGUNDO = 2.5

# Fase 0: clipe de 4 s levou ~52 s nos dois modelos. Serve para prever o tempo de
# renderização, que é sequencial (cada clipe parte do último quadro real do
# anterior — decisão da Fase 0, porque o Lite não chegou ao `lastFrame` pedido).
LATENCIA_CLIPE_S = 55

PRECOS_PADRAO: dict = {
    "modelos": {
        "padrao": "veo-3.1-lite-generate-001",
        "final": "veo-3.1-fast-generate-001",
    },
    # US$ por segundo de vídeo gerado, por modelo e resolução.
    "video_por_segundo": {
        "veo-3.1-lite-generate-001": {"720p": 0.05},
        "veo-3.1-fast-generate-001": {"720p": 0.15, "1080p": 0.15},
    },
    "imagem": 0.04,
    "modelo_imagem": "gemini-2.5-flash-image",
    "tts_por_cena": 0.01,
    "modelo_tts": "gemini-2.5-flash-tts",
    "margem_retrabalho": 1.3,
    "fator_teto_projeto": 1.5,
    "teto_projeto_usd": 20.0,
    "teto_mensal_usd": 30.0,
    "teto_previa_usd": 1.0,
    "paralelismo": 1,
}


def mesclar_precos(config: dict | None) -> dict:
    """`PRECOS_PADRAO` com o que vier de `config/video_precos` por cima (um nível de profundidade)."""
    precos = copy.deepcopy(PRECOS_PADRAO)
    for chave, valor in (config or {}).items():
        if isinstance(valor, dict) and isinstance(precos.get(chave), dict):
            for sub, subvalor in valor.items():
                if isinstance(subvalor, dict) and isinstance(precos[chave].get(sub), dict):
                    precos[chave][sub].update(subvalor)
                else:
                    precos[chave][sub] = subvalor
        else:
            precos[chave] = valor
    return precos


def carregar_precos(db) -> dict:
    snap = db.collection("config").document("video_precos").get()
    return mesclar_precos(snap.to_dict() if snap.exists else None)


def contar_palavras(texto: str) -> int:
    return len(re.findall(r"\w+", texto or "", flags=re.UNICODE))


def duracao_fala_estimada(texto: str) -> float:
    """Segundos de narração previstos pelo ritmo de referência (~2,5 palavras/s em pt-BR)."""
    return contar_palavras(texto) / PALAVRAS_POR_SEGUNDO


def duracao_clipe(audio_s: float) -> int | None:
    """Menor clipe (4, 6 ou 8 s) em que cabe `audio_s` + folga; `None` = cena precisa ser dividida."""
    necessario = max(float(audio_s or 0), 0.0) + FOLGA_AUDIO_S
    for d in DURACOES_CLIPE:
        if necessario <= d:
            return d
    return None


def modelo_do_modo(modo: str, precos: dict) -> str:
    return precos["modelos"].get(modo) or precos["modelos"]["padrao"]


def preco_segundo(modelo: str, resolucao: str, precos: dict) -> float:
    tabela = precos["video_por_segundo"].get(modelo) or {}
    if resolucao in tabela:
        return float(tabela[resolucao])
    if tabela:
        return float(max(tabela.values()))
    raise ValueError(f"Sem preço configurado para o modelo {modelo!r}.")


def estimar(duracoes_s: list[int], *, modo: str = "padrao", resolucao: str = "720p",
            precos: dict | None = None) -> dict:
    """Custo e tempo previstos para um projeto com clipes de `duracoes_s` segundos.

    A margem de retrabalho cobre refações de cena; o teto do projeto (trava de
    gasto do worker) é `fator_teto_projeto` × a estimativa, limitado a
    `teto_projeto_usd`.
    """
    precos = precos or PRECOS_PADRAO
    modelo = modelo_do_modo(modo, precos)
    segundos = int(sum(duracoes_s))
    n_cenas = len(duracoes_s)
    custo_video = segundos * preco_segundo(modelo, resolucao, precos)
    custo_quadros = (n_cenas + 1) * float(precos["imagem"]) if n_cenas else 0.0
    custo_tts = n_cenas * float(precos["tts_por_cena"])
    base = custo_video + custo_quadros + custo_tts
    com_margem = base * float(precos["margem_retrabalho"])
    teto_com_folga = com_margem * float(precos["fator_teto_projeto"])
    teto = min(teto_com_folga, float(precos["teto_projeto_usd"]))
    return {
        "modelo_video": modelo,
        "resolucao": resolucao,
        "cenas": n_cenas,
        "segundos_video": segundos,
        "custo_video_usd": round(custo_video, 2),
        "custo_quadros_usd": round(custo_quadros, 2),
        "custo_tts_usd": round(custo_tts, 2),
        "custo_previa_usd": round(custo_quadros + custo_tts, 2),
        "custo_estimado_usd": round(com_margem, 2),
        "teto_projeto_usd": round(teto, 2),
        # O teto absoluto cortou parte da folga de refações (1,5× a estimativa).
        "folga_teto_reduzida": teto < teto_com_folga,
        "tempo_renderizacao_min": math.ceil(n_cenas * LATENCIA_CLIPE_S / 60) if n_cenas else 0,
    }
