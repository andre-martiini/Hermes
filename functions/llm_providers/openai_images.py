"""Geração e edição de imagens pela API da OpenAI (GPT Image).

Só fala com a API: escolhe o tamanho, chama `images.generate`/`images.edit`,
decodifica o base64 da resposta e calcula o custo a partir do `usage`. Onde a
imagem fica (Storage, Drive, ação) e o teto diário são de `imagens_geradas.py`.

O custo é por token, em três faixas (texto de entrada, imagem de entrada e
imagem de saída); a de saída domina. A tabela abaixo é telemetria — a cobrança
de verdade é a do painel da OpenAI. Os IDs dos modelos vêm de variáveis de
ambiente porque mudam rápido (três gerações entre dez/2025 e set/2026).
"""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# Nome curto aceito pela tool -> ID do modelo na API.
MODELOS_CURTOS = ("flare", "sunburst", "gpt-image-2")


def id_do_modelo(curto: str | None) -> str:
    curto = (curto or "flare").strip()
    if curto == "sunburst":
        return os.environ.get("OPENAI_IMAGE_MODEL_PREMIUM", "gpt-image-2.5-sunburst")
    if curto == "gpt-image-2":
        return "gpt-image-2"
    return os.environ.get("OPENAI_IMAGE_MODEL_DEFAULT", "gpt-image-2.5-flare")


# US$ por 1M tokens (página de preços da OpenAI, set/2026). Modelo fora da
# tabela (ID novo vindo de env) cai no preço da geração 2.5, o mais alto.
PRECOS_USD_POR_MTOK: dict[str, dict[str, float]] = {
    "gpt-image-2.5-flare": {"texto": 5.0, "imagem_entrada": 8.0, "imagem_saida": 30.0},
    "gpt-image-2.5-sunburst": {"texto": 5.0, "imagem_entrada": 8.0, "imagem_saida": 30.0},
    "gpt-image-2": {"texto": 5.0, "imagem_entrada": 4.0, "imagem_saida": 15.0},
}
_PRECO_PADRAO = PRECOS_USD_POR_MTOK["gpt-image-2.5-flare"]


def _preco(modelo: str) -> dict[str, float]:
    if modelo in PRECOS_USD_POR_MTOK:
        return PRECOS_USD_POR_MTOK[modelo]
    for chave, preco in PRECOS_USD_POR_MTOK.items():
        if modelo.startswith(chave):  # snapshots datados, ex.: gpt-image-2.5-sunburst-2026-09-08
            return preco
    return _PRECO_PADRAO


PROPORCOES = ("1:1", "16:9", "4:3", "3:4", "9:16")

# A geração 2.5 aceita tamanho livre (lados múltiplos de 16, 0,65 a 8,3 MP):
# usa a proporção exata, perto de 1,3–1,5 MP. Os demais só os três fixos.
_TAMANHO_EXATO = {
    "1:1": "1024x1024",
    "16:9": "1536x864",
    "9:16": "864x1536",
    "4:3": "1408x1056",
    "3:4": "1056x1408",
}
_TAMANHO_FIXO = {
    "1:1": "1024x1024",
    "16:9": "1536x1024",
    "4:3": "1536x1024",
    "9:16": "1024x1536",
    "3:4": "1024x1536",
}


def aceita_tamanho_livre(modelo: str) -> bool:
    return modelo.startswith("gpt-image-2.5")


def tamanho_para(proporcao: str | None, modelo: str) -> str:
    proporcao = proporcao if proporcao in PROPORCOES else "1:1"
    tabela = _TAMANHO_EXATO if aceita_tamanho_livre(modelo) else _TAMANHO_FIXO
    return tabela[proporcao]


# Estimativa ANTES da chamada, só para o teto diário. Conservadora (acima das
# medições publicadas: ~US$ 0,013 médio e ~0,053 alto em 1024x1024); o custo
# gravado depois é o do `usage` real.
_USD_POR_MP = {"low": 0.01, "medium": 0.03, "high": 0.08, "xhigh": 0.16, "max": 0.30, "auto": 0.08}
_USD_POR_REFERENCIA = 0.02


def estimar_usd(*, modelo: str, tamanho: str, qualidade: str, n: int, referencias: int = 0) -> float:
    largura, altura = (int(x) for x in tamanho.split("x"))
    mp = largura * altura / 1_048_576
    fator = _preco(modelo)["imagem_saida"] / _PRECO_PADRAO["imagem_saida"]
    por_imagem = _USD_POR_MP.get(qualidade, _USD_POR_MP["high"]) * mp * fator
    return round(por_imagem * n + _USD_POR_REFERENCIA * referencias, 4)


# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------

_MENSAGENS = {
    "limite": "A OpenAI recusou por excesso de pedidos por minuto (limite do nível da conta). Tente de novo em um minuto.",
    "sem_credito": "A conta da OpenAI está sem crédito ou atingiu o teto de gasto. Recarregue em platform.openai.com > Billing.",
    "verificacao": ("Os modelos GPT Image exigem a verificação da organização na OpenAI. Faça em "
                    "platform.openai.com > Settings > Organization > General (Verify Organization) e tente de novo."),
    "moderacao": "A OpenAI recusou o pedido pela política de conteúdo. Reformule o pedido; não há nova tentativa automática.",
    "timeout": "A OpenAI não respondeu a tempo. Peça de novo (ou use qualidade menor).",
    "indisponivel": "A API de imagens da OpenAI está fora do ar ou instável agora.",
    "chave": "A chave da OpenAI (system/api_keys.openai_api_key) foi recusada. Confira a chave no painel da OpenAI.",
    "configuracao": "Chave da OpenAI não configurada (system/api_keys.openai_api_key).",
    "resposta": "A OpenAI respondeu sem imagem.",
}


class ErroImagem(Exception):
    def __init__(self, tipo: str, detalhe: str = ""):
        self.tipo = tipo
        self.detalhe = detalhe
        texto = _MENSAGENS.get(tipo, "Falha na API de imagens da OpenAI.")
        super().__init__(f"{texto} ({detalhe})" if detalhe and tipo in ("outro", "resposta") else texto)


def classificar(exc: Exception) -> ErroImagem:
    if isinstance(exc, ErroImagem):
        return exc
    status = getattr(exc, "status_code", None)
    corpo = getattr(exc, "body", None)
    detalhe = corpo.get("error", corpo) if isinstance(corpo, dict) else None
    codigo = str(detalhe.get("code") or "") if isinstance(detalhe, dict) else ""
    texto = f"{codigo} {exc}".lower()
    nome = type(exc).__name__

    if "moderation" in texto or "safety system" in texto or "content_policy" in texto:
        return ErroImagem("moderacao", str(exc)[:300])
    if "insufficient_quota" in texto or "billing" in texto:
        return ErroImagem("sem_credito", str(exc)[:300])
    if status == 429 or nome == "RateLimitError":
        return ErroImagem("limite", str(exc)[:300])
    if "verif" in texto and "organization" in texto:
        return ErroImagem("verificacao", str(exc)[:300])
    if status == 401 or nome == "AuthenticationError":
        return ErroImagem("chave", str(exc)[:300])
    if nome == "APITimeoutError":
        return ErroImagem("timeout", str(exc)[:300])
    if nome == "APIConnectionError" or (isinstance(status, int) and status >= 500):
        return ErroImagem("indisponivel", str(exc)[:300])
    return ErroImagem("outro", str(exc)[:300])


# Só o 429 de ritmo volta a tentar; crédito, moderação e verificação não mudam esperando.
_ESPERAS_429 = (5, 15, 30)


def _com_retentativa(chamada: Callable[[], Any], espera: Callable[[float], None]) -> Any:
    for tentativa in range(len(_ESPERAS_429) + 1):
        try:
            return chamada()
        except Exception as exc:  # noqa: BLE001
            erro = classificar(exc)
            if erro.tipo != "limite" or tentativa == len(_ESPERAS_429):
                raise erro from exc
            espera(_ESPERAS_429[tentativa])
    raise ErroImagem("limite")  # inalcançável


# --------------------------------------------------------------------------
# Chamadas
# --------------------------------------------------------------------------

@dataclass
class Resultado:
    modelo: str
    imagens: list[bytes]
    prompts_revisados: list[str | None]
    tokens: dict[str, int] = field(default_factory=dict)
    custo_usd: float = 0.0


def cliente(db, *, timeout: float = 300.0):
    """Mesma chave do A/B do Luna (`system/api_keys.openai_api_key`); env como alternativa."""
    chave = None
    try:
        snap = db.collection("system").document("api_keys").get()
        if snap.exists:
            chave = (snap.to_dict() or {}).get("openai_api_key")
    except Exception as exc:  # noqa: BLE001
        print(f"[openai_images] Falha ao ler system/api_keys: {exc}")
    chave = chave or os.environ.get("OPENAI_API_KEY")
    if not chave:
        raise ErroImagem("configuracao")
    import openai

    # Sem retry do SDK: o 429 é tratado aqui, e os demais erros não melhoram repetindo.
    return openai.OpenAI(api_key=chave, timeout=timeout, max_retries=0)


def _campo(obj: Any, nome: str, padrao: Any = None) -> Any:
    if obj is None:
        return padrao
    if isinstance(obj, dict):
        return obj.get(nome, padrao)
    return getattr(obj, nome, padrao)


def tokens_de(usage: Any) -> dict[str, int]:
    """Separa as três faixas cobradas. Sem o detalhamento, todo o input conta como texto."""
    entrada = int(_campo(usage, "input_tokens", 0) or 0)
    det_in = _campo(usage, "input_tokens_details")
    imagem_entrada = int(_campo(det_in, "image_tokens", 0) or 0)
    texto = int(_campo(det_in, "text_tokens", entrada - imagem_entrada) or 0)
    saida = int(_campo(usage, "output_tokens", 0) or 0)
    det_out = _campo(usage, "output_tokens_details")
    imagem_saida = int(_campo(det_out, "image_tokens", saida) or 0) if det_out is not None else saida
    return {"texto": texto, "imagem_entrada": imagem_entrada, "imagem_saida": imagem_saida}


def custo_usd(modelo: str, tokens: dict[str, int]) -> float:
    preco = _preco(modelo)
    total = sum(tokens.get(faixa, 0) * preco[faixa] for faixa in ("texto", "imagem_entrada", "imagem_saida"))
    return round(total / 1_000_000, 6)


def _resultado(resp: Any, modelo: str) -> Resultado:
    imagens, revisados = [], []
    for item in _campo(resp, "data", None) or []:
        b64 = _campo(item, "b64_json")
        if not b64:
            continue
        imagens.append(base64.b64decode(b64))
        revisados.append(_campo(item, "revised_prompt"))
    if not imagens:
        raise ErroImagem("resposta", "data vazio")
    tokens = tokens_de(_campo(resp, "usage"))
    return Resultado(modelo=modelo, imagens=imagens, prompts_revisados=revisados,
                     tokens=tokens, custo_usd=custo_usd(modelo, tokens))


def _comuns(*, qualidade: str, fundo: str, formato: str, n: int, tamanho: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"size": tamanho, "quality": qualidade, "n": n, "output_format": formato}
    if fundo in ("transparent", "opaque"):
        kwargs["background"] = fundo
    return kwargs


def gerar(client, *, modelo: str, prompt: str, tamanho: str, qualidade: str = "medium",
          fundo: str = "auto", formato: str = "png", n: int = 1,
          espera: Callable[[float], None] = time.sleep) -> Resultado:
    kwargs = _comuns(qualidade=qualidade, fundo=fundo, formato=formato, n=n, tamanho=tamanho)
    kwargs["moderation"] = "auto"
    resp = _com_retentativa(lambda: client.images.generate(model=modelo, prompt=prompt, **kwargs), espera)
    return _resultado(resp, modelo)


def editar(client, *, modelo: str, prompt: str, imagens: list[tuple[str, bytes, str]],
           mascara: tuple[str, bytes, str] | None = None, tamanho: str, qualidade: str = "medium",
           fundo: str = "auto", formato: str = "png", n: int = 1,
           espera: Callable[[float], None] = time.sleep) -> Resultado:
    """`imagens` e `mascara` como tuplas (nome, bytes, mime), o formato de arquivo do SDK."""
    kwargs = _comuns(qualidade=qualidade, fundo=fundo, formato=formato, n=n, tamanho=tamanho)
    if mascara is not None:
        kwargs["mask"] = mascara
    entrada = imagens if len(imagens) > 1 else imagens[0]
    resp = _com_retentativa(lambda: client.images.edit(model=modelo, prompt=prompt, image=entrada, **kwargs), espera)
    return _resultado(resp, modelo)
