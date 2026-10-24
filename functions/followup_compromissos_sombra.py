"""Revalidação de follow-up -- wiring em modo sombra (P07, passos 7-8).

Quando `vencer_promessas` vence uma promessa e a flag
`system/settings.atencao.followup_sombra.enabled` (padrão desligada) está
ligada, roda `autonomy.followup_guard.revalidar_followup` sobre o contexto real
do chat (mensagens posteriores, rascunho pendente no outbox, estado do item de
atenção) e grava em `followup_compromissos_sombra` só ids, a decisão nova e a
divergência em relação ao fluxo antigo (que sempre alerta o dono). Nunca grava
texto, nunca altera promessas nem a fila de atenção, nunca envia nada: mede
quantos alertas do A07 o guarda novo suprimiria ou adiaria antes de qualquer
troca. Sem chamada de modelo.
"""

from __future__ import annotations

from datetime import datetime, timezone

from autonomy.atencao_compromisso import montar_item_atencao
from autonomy.followup_guard import ADIAR, ENVIAR, ESTADOS_ATENCAO_FECHADOS, SUPRIMIR, revalidar_followup

SOMBRA_COLLECTION = "followup_compromissos_sombra"
CONTADORES_COLLECTION = "followup_compromissos_sombra_contadores"
LIMITE_MENSAGENS = 200
STATUS_RASCUNHO_PENDENTE = ["aguardando_aprovacao", "aguardando_janela"]
DIVERGENCIAS = {ENVIAR: "ambos_alertam", ADIAR: "so_novo_adia", SUPRIMIR: "so_novo_suprime"}


def _habilitado(db) -> bool:
    doc = db.collection("system").document("settings").get()
    settings = (doc.to_dict() if doc.exists else {}) or {}
    cfg = (settings.get("atencao") or {}).get("followup_sombra") or {}
    return cfg.get("enabled", False) is True


def _mensagens(db, chat_id: str, desde: datetime) -> list[dict]:
    docs = (
        db.collection("whatsapp_messages")
        .where("chat_id", "==", chat_id)
        .where("timestamp", ">=", desde)
        .limit(LIMITE_MENSAGENS)
        .stream()
    )
    return [d.to_dict() or {} for d in docs]


def _rascunho_pendente(db, chave_atencao: str) -> bool:
    docs = (
        db.collection("whatsapp_outbox")
        .where("item_atencao_id", "==", chave_atencao)
        .where("status", "in", STATUS_RASCUNHO_PENDENTE)
        .limit(1)
        .stream()
    )
    return any(True for _ in docs)


def registrar(db, promessa: dict, chave_atencao: str, agora: datetime | None = None) -> dict | None:
    """Chamado para cada promessa que `vencer_promessas` vai marcar vencida.
    `promessa`: dict do `promessas_abertas` com `_doc_id`. Devolve o resumo
    gravado ou None (desligada, já registrada ou promessa sem identidade)."""
    doc_id = str(promessa.get("_doc_id") or "")
    chat_id = str(promessa.get("chat_id") or "")
    prometido_em = promessa.get("prometido_em")
    if not doc_id or not chat_id or not chave_atencao or not isinstance(prometido_em, datetime):
        return None
    if not _habilitado(db):
        return None
    ref = db.collection(SOMBRA_COLLECTION).document(doc_id)
    if ref.get().exists:  # reavaliação do mesmo vencimento
        return None
    agora = agora or datetime.now(timezone.utc)

    item = db.collection("atencao").document(chave_atencao).get()
    estado_atencao = ((item.to_dict() or {}).get("estado") if item.exists else None)
    from secretario_whatsapp import eh_mensagem_do_bot

    # Respostas do bot saem pela conta do dono e voltam como from_me: não são intervenção humana.
    mensagens = [m for m in _mensagens(db, chat_id, prometido_em) if not eh_mensagem_do_bot(m, db)]
    contexto = {
        "mensagens": mensagens,
        "rascunho_pendente": _rascunho_pendente(db, chave_atencao),
        "estado_atencao": estado_atencao,
    }
    compromisso = {
        "texto": promessa.get("texto") or "",
        "prometido_em": prometido_em,
        "estado": promessa.get("estado"),
        "mensagem_id": promessa.get("mensagem_id"),
    }
    decisao = revalidar_followup(compromisso, contexto)
    proxima = montar_item_atencao(doc_id, 1, decisao, agora)["proxima_avaliacao"]
    resumo = {
        "promessa_doc_id": doc_id,
        "chat_id": chat_id,
        "modo": "sombra",
        "criado_em": agora.isoformat(),
        "acao_nova": decisao.acao,
        "motivo": decisao.motivo,
        "proxima_avaliacao": proxima,
        # item já fechado pelo dono: o fluxo antigo não alerta, então não há divergência a medir
        "divergencia": "nenhum_alerta" if estado_atencao in ESTADOS_ATENCAO_FECHADOS else DIVERGENCIAS[decisao.acao],
    }
    ref.set(resumo)
    from firebase_admin import firestore

    db.collection(CONTADORES_COLLECTION).document(resumo["criado_em"][:10]).set(
        {"avaliadas": firestore.Increment(1), resumo["divergencia"]: firestore.Increment(1)},
        merge=True,
    )
    return resumo
