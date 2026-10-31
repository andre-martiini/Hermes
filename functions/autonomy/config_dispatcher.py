"""Configuração persistida do dispatcher do runner (P08, passos 3 e 11: flag do modo e orçamento).

Lê UM documento (`configuracoes/autonomia_dispatcher`) com `modo` ("off" | "shadow" | "ativo")
e `despachos_restantes` (inteiro >= 0) e devolve a entrada de `decidir_lote`. Fail-closed:
documento ausente, ilegível, erro de leitura, modo desconhecido ou orçamento ausente/inválido
vira `OFF` / sem orçamento (nada é enfileirado). O orçamento só vale em `ativo`; em `shadow`
não é lido como permissão. `consumir_orcamento` baixa o saldo numa transação (tudo ou nada,
só em `ativo`, nunca abaixo de zero); agendar o dispatcher fica para sub-entrega seguinte.
Nada chama este módulo em produção.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from firebase_admin import firestore

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
        return ConfigDispatcher(ModoDispatcher.OFF, None, "orcamento_ausente_ou_invalido")
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


def consumir_orcamento(db: Any, quantidade: int = 1) -> int:
    """Baixa `quantidade` de `despachos_restantes` numa transação; devolve quanto foi concedido.

    Tudo ou nada: concede `quantidade` ou 0 (nunca parcial). Concede 0, sem gravar, se o modo
    não é `ativo`, o saldo é inválido/insuficiente, `quantidade` é inválida (bool, não int, < 1)
    ou o backend não tem transação. Qualquer falha do Firestore também devolve 0 (fail-closed:
    sem confirmação da baixa, nada é despachado). Chamar ANTES de enfileirar.
    """
    if type(quantidade) is not int or quantidade < 1:
        return 0
    try:
        if not hasattr(db, "transaction"):
            return 0
        ref = db.collection(COLECAO_CONFIG).document(DOC_DISPATCHER)
        tx = db.transaction()

        @firestore.transactional
        def _exec(transaction):
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                return 0
            cfg = interpretar_config(snap.to_dict())
            if cfg.modo is not ModoDispatcher.ATIVO or cfg.despachos_restantes is None:
                return 0
            if cfg.despachos_restantes < quantidade:
                return 0
            transaction.update(ref, {"despachos_restantes": cfg.despachos_restantes - quantidade})
            return quantidade

        return _exec(tx)
    except Exception:
        return 0
