"""De onde vem cada renda: o salario do Ifes, servicos ou outras.

A categoria nao serve para achar o salario: "Renda Principal" tambem guarda
diarias (Facto), servicos pequenos (Reforco Positivo), reembolso (ChatGPT do
projeto) e restituicao do IRPF, e ha lancamentos com "Renda principal" em
minusculas. O salario e o lancamento "Remuneracao IFES" (em mar/2026,
"Ifes Remuneracao"), reconhecido pelo nome.
"""
from __future__ import annotations

import re
import unicodedata

CATEGORIAS_SERVICO = {"servico particular", "bolsa"}


def _normalizar(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).split())


def e_salario_ifes(renda: dict) -> bool:
    palavras = set(_normalizar(renda.get("description")).split())
    return {"remuneracao", "ifes"} <= palavras


def fonte(renda: dict) -> str:
    if e_salario_ifes(renda):
        return "ifes"
    if _normalizar(renda.get("category")) in CATEGORIAS_SERVICO:
        return "servicos"
    return "outras"
