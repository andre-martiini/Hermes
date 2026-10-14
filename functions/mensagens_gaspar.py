"""Reconhece as mensagens que o próprio Gaspar mandou no WhatsApp em nome do André.

O Modo Secretário e o Modo Objetivo escrevem em primeira pessoa, pela conta do
André, sem assinatura (decisão do dono, 14/10/2026). A resposta volta capturada
como `from_me`, igual a uma mensagem que o André digitou; sem este registro o
sistema acharia que o André assumiu a conversa a cada resposta do Gaspar.

O registro é gravado ANTES do envio (na criação do rascunho de envio imediato ou
na aprovação), então o eco sempre o encontra. A chave é só o texto: o eco pode
chegar com outro id de chat (`@lid` em vez de `@c.us`), e duas mensagens iguais
em poucos minutos, uma do André e outra do Gaspar, é caso desprezível.
"""

import hashlib
from datetime import datetime, timedelta, timezone

COLECAO = "whatsapp_enviados_gaspar"
ORIGENS_AUTONOMAS = frozenset({"secretario_whatsapp", "objetivo_whatsapp"})
_VALIDADE = timedelta(hours=6)


def _chave(texto: str) -> str:
    normalizado = " ".join(str(texto or "").split())
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()[:40]


def registrar(db, texto: str, *, origem: str, chat_id: str = "", ref_id: str | None = None) -> None:
    if not str(texto or "").strip():
        return
    agora = datetime.now(timezone.utc)
    try:
        db.collection(COLECAO).document(_chave(texto)).set({
            "origem": origem,
            "chat_id": chat_id,
            "ref_id": ref_id,
            "registrado_em": agora,
            "expira_em": agora + _VALIDADE,
        })
    except Exception as exc:  # noqa: BLE001 — sem o registro o pior caso é pausar por engano
        print(f"[MensagensGaspar] Falha ao registrar envio: {exc}")


def encontrar(db, mensagem: dict) -> dict | None:
    """O registro do envio do Gaspar que gerou esta mensagem `from_me`, se houver."""
    if not mensagem.get("from_me"):
        return None
    texto = mensagem.get("content") or mensagem.get("text") or ""
    if not str(texto).strip():
        return None
    try:
        snap = db.collection(COLECAO).document(_chave(texto)).get()
    except Exception as exc:  # noqa: BLE001
        print(f"[MensagensGaspar] Falha ao consultar registro: {exc}")
        return None
    dados = snap.to_dict() if snap.exists else None
    if not isinstance(dados, dict) or not dados.get("origem"):
        return None
    expira = dados.get("expira_em")
    if isinstance(expira, datetime) and expira < datetime.now(timezone.utc):
        return None
    return dados


def eh_do_gaspar(db, mensagem: dict) -> bool:
    return encontrar(db, mensagem) is not None
