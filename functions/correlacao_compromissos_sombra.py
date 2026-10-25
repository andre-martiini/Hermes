"""Correlação de entregáveis -- wiring em modo sombra (P07, passo 5).

Quando uma mensagem from_me com anexo chega num chat com promessa aberta/vencida
e a flag `system/settings.atencao.correlacao_sombra.enabled` (padrão desligada)
está ligada, roda `autonomy.correlacao_entregaveis.correlacionar` entre a
promessa e o anexo (canal WhatsApp) e grava em `correlacao_compromissos_sombra`
só ids, canais, tipo do vínculo e contagens -- nunca texto nem nome de arquivo.
Nunca altera promessas nem a fila de atenção. Outros canais (Gmail, tarefa,
documento) entram depois como novas `Evidencia`; hoje só o WhatsApp tem fonte.
Lógica local, sem chamada de modelo.
"""

from __future__ import annotations

from datetime import datetime, timezone

from autonomy.commitments import _normalizar
from autonomy.correlacao_entregaveis import Evidencia, correlacionar, vinculo_firme
from autonomy.cumprimento import _objetos

SOMBRA_COLLECTION = "correlacao_compromissos_sombra"
CONTADORES_COLLECTION = "correlacao_compromissos_sombra_contadores"


def _habilitado(db) -> bool:
    doc = db.collection("system").document("settings").get()
    settings = (doc.to_dict() if doc.exists else {}) or {}
    cfg = (settings.get("atencao") or {}).get("correlacao_sombra") or {}
    return cfg.get("enabled", False) is True


def _ids(valor) -> tuple:
    if not isinstance(valor, (list, tuple)):
        return ()
    return tuple(i for i in valor if isinstance(i, str) and i.strip() and len(i) <= 200 and i.isprintable())[:50]


def registrar(db, mensagem: dict, promessa: dict | None, acao_antiga: str, agora: datetime | None = None) -> dict | None:
    """Chamado após a decisão antiga. Devolve o resumo gravado ou None."""
    if promessa is None or acao_antiga not in ("cumprir", "nenhuma") or not mensagem.get("from_me") or mensagem.get("is_group"):
        return None
    media = mensagem.get("media")
    if not isinstance(media, dict):
        return None
    msg_id = str(mensagem.get("wa_message_id") or mensagem.get("id") or "")
    doc_promessa = str(promessa.get("_doc_id") or "")
    if not msg_id or not doc_promessa or not _habilitado(db):
        return None
    ref = db.collection(SOMBRA_COLLECTION).document(f"{doc_promessa}_{msg_id}")
    if ref.get().exists:  # reentrega do gatilho
        return None
    nome = media.get("filename")
    evidencia = Evidencia("whatsapp", msg_id, nome if isinstance(nome, str) else "", _ids(media.get("ids")))
    texto = promessa.get("texto") if isinstance(promessa.get("texto"), str) else ""
    vinculos, motivo = (), None
    try:
        # sem objeto documental ou sem nome de anexo não há o que casar: medir à parte, não como "sem vínculo"
        if not _objetos(_normalizar(texto)) and not _ids(promessa.get("ids_entregavel")):
            motivo = "promessa_sem_objeto"
        elif not evidencia.nome and not evidencia.ids:
            motivo = "midia_sem_nome"
        else:
            vinculos = correlacionar(texto, [evidencia], _ids(promessa.get("ids_entregavel")))
    except ValueError:
        motivo = "fora_do_contrato"  # texto/nome longo demais ou inválido
    firme = vinculo_firme(vinculos)
    resumo = {
        "promessa_doc_id": doc_promessa,
        "message_doc_id": msg_id,
        "chat_id": str(mensagem.get("chat_id") or ""),
        "modo": "sombra",
        "criado_em": (agora or datetime.now(timezone.utc)).isoformat(),
        "canais": sorted({v.canal for v in vinculos}),
        "vinculos": len(vinculos),
        "firme": firme,
        "motivo_nao_avaliavel": motivo,
        "resultado": "nao_avaliavel" if motivo else ("vinculo_firme" if firme else ("so_semantico" if vinculos else "sem_vinculo")),
    }
    ref.set(resumo)
    from firebase_admin import firestore

    db.collection(CONTADORES_COLLECTION).document(resumo["criado_em"][:10]).set(
        {"avaliadas": firestore.Increment(1), resumo["resultado"]: firestore.Increment(1)},
        merge=True,
    )
    return resumo
