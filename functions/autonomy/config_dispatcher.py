"""Configuração persistida do dispatcher do runner (P08, passos 3 e 11: flag do modo e orçamento).

Lê UM documento (`configuracoes/autonomia_dispatcher`) com `modo` ("off" | "shadow" | "ativo")
e `despachos_restantes` (inteiro >= 0) e devolve a entrada de `decidir_lote`. Fail-closed:
documento ausente, ilegível, erro de leitura, modo desconhecido ou orçamento ausente/inválido
vira `OFF` / sem orçamento (nada é enfileirado). O orçamento só vale em `ativo`; em `shadow`
não é lido como permissão. Só LEITURA: consumir o orçamento (transação) e agendar o
dispatcher ficam para sub-entrega seguinte; nada chama este módulo em produção.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autonomy.dispatcher import ModoDispatcher, modo_de_config

COLECAO_CONFIG = "configuracoes"
DOC_DISPATCHER = "autonomia_dispatcher"


@dataclass(frozen=True)
class ConfigDispatcher:
    modo: ModoDispatcher
    despachos_restantes: int | None
    motivo: str


_DESLIGADO = ConfigDispatcher(ModoDispatcher.OFF, None, "config_indisponivel")


def interpretar_config(dados: object) -> ConfigDispatcher:
    """Pura: dicionário do documento -> configuração segura."""
    if not isinstance(dados, dict):
        return _DESLIGADO
    modo = modo_de_config(dados.get("modo"))
    if modo is ModoDispatcher.OFF:
        return ConfigDispatcher(ModoDispatcher.OFF, None, "modo_off")
    bruto = dados.get("despachos_restantes")
    saldo = bruto if type(bruto) is int and bruto >= 0 else None
    if modo is ModoDispatcher.ATIVO and saldo is None:
        return ConfigDispatcher(modo, None, "orcamento_ausente_ou_invalido")
    if modo is ModoDispatcher.SHADOW:
        return ConfigDispatcher(modo, None, "sombra")
    return ConfigDispatcher(modo, saldo, "ok")


def ler_config_dispatcher(db: Any) -> ConfigDispatcher:
    """Qualquer falha de leitura devolve OFF (nunca propaga, nunca abre o despacho)."""
    try:
        snap = db.collection(COLECAO_CONFIG).document(DOC_DISPATCHER).get()
        if not snap.exists:
            return ConfigDispatcher(ModoDispatcher.OFF, None, "config_ausente")
        return interpretar_config(snap.to_dict())
    except Exception:
        return _DESLIGADO
