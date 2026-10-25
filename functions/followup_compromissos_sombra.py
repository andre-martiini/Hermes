"""Revalidação de follow-up -- wiring em modo sombra (P07, passos 4, 7-8).

Quando `vencer_promessas` vence uma promessa e a flag
`system/settings.atencao.followup_sombra.enabled` (padrão desligada) está
ligada, roda `autonomy.followup_guard.revalidar_followup` sobre o contexto real
do chat (mensagens posteriores, rascunho pendente no outbox, estado do item de
atenção) e grava em `followup_compromissos_sombra` só ids, a decisão nova e a
divergência em relação ao fluxo antigo (que sempre alerta o dono). Nunca grava
texto, nunca altera promessas nem a fila de atenção (o item por chave/versão
do passo 8 vai para `atencao_compromissos_sombra`, coleção própria), nunca envia nada: mede
quantos alertas do A07 o guarda novo suprimiria ou adiaria antes de qualquer
troca. Sem chamada de modelo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from autonomy.commitments import extrair_prazo_expresso
from autonomy.atencao_compromisso import deve_gravar, montar_item_atencao
from autonomy.prazo_followup import planejar_acompanhamento
from autonomy.followup_guard import ADIAR, ENVIAR, ESTADOS_ATENCAO_FECHADOS, SUPRIMIR, revalidar_followup

_FUSO = ZoneInfo("America/Sao_Paulo")
SOMBRA_COLLECTION = "followup_compromissos_sombra"
CONTADORES_COLLECTION = "followup_compromissos_sombra_contadores"
ITENS_COLLECTION = "atencao_compromissos_sombra"  # item por chave+versão (passo 8), fora da fila real
LIMITE_MENSAGENS = 200
LIMITE_HISTORICO = 200
# Respostas do bot saem pela conta do dono (from_me) e o registro que as identifica expira em 6h,
# então não dá para separá-las no histórico: latências abaixo disto são tratadas como automáticas.
MIN_HORAS_RESPOSTA = 2 / 60
MAX_HORAS_RESPOSTA = 168.0  # respostas mais lentas que uma semana não são "resposta" do mesmo assunto
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
        .order_by("timestamp", direction="DESCENDING")  # direção do índice composto implantado
        .limit(LIMITE_MENSAGENS)
        .stream()
    )
    return [d.to_dict() or {} for d in docs]


def _historico(db, chat_id: str, antes: datetime) -> list[dict]:
    docs = (
        db.collection("whatsapp_messages")
        .where("chat_id", "==", chat_id)
        .where("timestamp", "<", antes)
        .order_by("timestamp", direction="DESCENDING")
        .limit(LIMITE_HISTORICO)
        .stream()
    )
    return [d.to_dict() or {} for d in docs]


def horas_de_resposta(mensagens: list[dict]) -> list[float]:
    """Horas entre cada mensagem recebida e a próxima do dono no mesmo chat
    (só a primeira resposta após uma sequência de recebidas)."""
    validas = [m for m in mensagens if isinstance(m.get("timestamp"), datetime) and m["timestamp"].utcoffset() is not None]
    validas.sort(key=lambda m: m["timestamp"])
    saida, pendente = [], None
    for m in validas:
        if m.get("from_me") is True:
            if pendente is not None:
                horas = (m["timestamp"] - pendente).total_seconds() / 3600
                if MIN_HORAS_RESPOSTA <= horas <= MAX_HORAS_RESPOSTA:
                    saida.append(horas)
                pendente = None
        elif pendente is None:
            pendente = m["timestamp"]
    return saida


def _acompanhamento(db, promessa: dict, chat_id: str, prometido_em: datetime) -> dict:
    """Passo 4: quando o planejador novo olharia de novo, contra o `vence_em` fixo
    do fluxo antigo. O prazo expresso vem da seleção barata sobre o texto da promessa
    (`extrair_prazo_expresso`, determinístico, sem modelo); prazo inutilizável
    (anterior à promessa) cai na estimativa e é contado em `acompanhamento_prazo_descartado`."""
    descartado = False
    try:
        horas = horas_de_resposta(_historico(db, chat_id, prometido_em))
        prazo = extrair_prazo_expresso(promessa.get("texto") or "", prometido_em.astimezone(_FUSO).date())
        try:
            plano = planejar_acompanhamento(prazo, prometido_em, horas)
        except ValueError:
            if prazo is None:
                raise
            descartado = True
            plano = planejar_acompanhamento(None, prometido_em, horas)
    except Exception:  # medição auxiliar nunca derruba a sombra
        return {"acompanhamento_erro": True}
    saida = {
        "acompanhamento_origem": plano.origem,
        "acompanhamento_verificar_em": plano.verificar_em.isoformat(),
        "acompanhamento_amostra": plano.amostra,
    }
    if descartado:
        saida["acompanhamento_prazo_descartado"] = True
    vence_em = promessa.get("vence_em")
    if isinstance(vence_em, datetime) and vence_em.utcoffset() is not None:
        saida["acompanhamento_delta_horas"] = round((plano.verificar_em - vence_em).total_seconds() / 3600, 2)
    return saida


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
    item = montar_item_atencao(doc_id, 1, decisao, agora)
    proxima = item["proxima_avaliacao"]
    resumo = {
        "promessa_doc_id": doc_id,
        "chat_id": chat_id,
        "modo": "sombra",
        "criado_em": agora.isoformat(),
        "acao_nova": decisao.acao,
        "motivo": decisao.motivo,
        "proxima_avaliacao": proxima,
        **_acompanhamento(db, promessa, chat_id, prometido_em),
        # item já fechado pelo dono: o fluxo antigo não alerta, então não há divergência a medir
        "divergencia": "nenhum_alerta" if estado_atencao in ESTADOS_ATENCAO_FECHADOS else DIVERGENCIAS[decisao.acao],
    }
    ref.set(resumo)
    from firebase_admin import firestore

    db.collection(CONTADORES_COLLECTION).document(resumo["criado_em"][:10]).set(
        {"avaliadas": firestore.Increment(1), resumo["divergencia"]: firestore.Increment(1)},
        merge=True,
    )
    # por último: se falhar, o resumo e os contadores (que a reentrega não refaz) já estão gravados
    item_ref = db.collection(ITENS_COLLECTION).document(item["id"])
    existente = item_ref.get()
    if deve_gravar((existente.to_dict() or None) if existente.exists else None, item):
        item_ref.set({**item, "modo": "sombra"})
    return resumo
