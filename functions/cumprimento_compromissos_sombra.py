"""Cumprimento de compromissos -- wiring em modo sombra (P07, passos 6-7).

Quando uma mensagem from_me chega num chat com promessa aberta/vencida e a
flag `system/settings.atencao.cumprimento_sombra.enabled` (padrão desligada)
está ligada, compara o fechamento antigo (A06, `decisao["acao"] == "cumprir"`,
por comprimento) com o veredito de `autonomy.cumprimento.avaliar_cumprimento`
e grava só ids, classes e a divergência em `cumprimento_compromissos_sombra`.
Nunca grava texto, nunca altera promessas nem a fila de atenção: serve para
medir quantos fechamentos do A06 o avaliador novo não confirmaria, antes de
qualquer troca. Lógica local, sem chamada de modelo.
"""

from __future__ import annotations

from datetime import datetime, timezone

from autonomy.cumprimento import CUMPRIDO, avaliar_cumprimento

SOMBRA_COLLECTION = "cumprimento_compromissos_sombra"
CONTADORES_COLLECTION = "cumprimento_compromissos_sombra_contadores"


def _habilitado(db) -> bool:
    doc = db.collection("system").document("settings").get()
    settings = (doc.to_dict() if doc.exists else {}) or {}
    cfg = (settings.get("atencao") or {}).get("cumprimento_sombra") or {}
    return cfg.get("enabled", False) is True


def classificar(antigo_fecha: bool, novo_fecha: bool) -> str:
    if antigo_fecha and novo_fecha:
        return "ambos_fecham"
    if antigo_fecha:
        return "so_antigo_fecha"  # possível falso fechamento do A06
    if novo_fecha:
        return "so_novo_fecha"
    return "ambos_mantem"


def registrar(db, mensagem: dict, promessa: dict | None, acao_antiga: str, agora: datetime | None = None) -> dict | None:
    """Chamado após a decisão antiga. Devolve o resumo gravado ou None."""
    if promessa is None or acao_antiga not in ("cumprir", "nenhuma"):
        return None
    if not mensagem.get("from_me") or mensagem.get("is_group"):
        return None
    msg_id = str(mensagem.get("wa_message_id") or mensagem.get("id") or "")
    doc_promessa = str(promessa.get("_doc_id") or "")
    if not msg_id or not doc_promessa or not _habilitado(db):
        return None
    ref = db.collection(SOMBRA_COLLECTION).document(f"{doc_promessa}_{msg_id}")
    if ref.get().exists:  # reentrega do gatilho
        return None
    media = mensagem.get("media")
    nome = media.get("filename") if isinstance(media, dict) else ""
    r = avaliar_cumprimento(
        promessa.get("texto"), mensagem.get("content"), bool(media),
        nome if isinstance(nome, str) else "",
    )
    novo_fecha = r.estado == CUMPRIDO and not r.incerta
    resumo = {
        "promessa_doc_id": doc_promessa,
        "message_doc_id": msg_id,
        "chat_id": str(mensagem.get("chat_id") or ""),
        "modo": "sombra",
        "criado_em": (agora or datetime.now(timezone.utc)).isoformat(),
        "antigo_fecha": acao_antiga == "cumprir",
        "novo_estado": r.estado,
        "novo_incerta": r.incerta,
        "divergencia": classificar(acao_antiga == "cumprir", novo_fecha),
    }
    ref.set(resumo)
    from firebase_admin import firestore

    db.collection(CONTADORES_COLLECTION).document(resumo["criado_em"][:10]).set(
        {"avaliadas": firestore.Increment(1), resumo["divergencia"]: firestore.Increment(1)},
        merge=True,
    )
    return resumo
