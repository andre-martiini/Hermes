"""Autorização via Telegram para decisões do Argos (aprovar plano | enfileirar execução).

Mesmo padrão de `outbox_aprovacao.py` (card com botões inline, decisão em um
toque, transição atômica no Firestore), mas genérico para uma DECISÃO do
Argos, não uma mensagem de WhatsApp. Não reaproveita `outbox_aprovacao.py`
nem o substitui — modelam coisas diferentes.

O conector Claude↔Argos (argos-gestor-sistemas-main) tem, de propósito, DUAS
operações que não verifica sozinho: aprovar o plano de uma demanda e
enfileirar sua execução. Este módulo é a peça que faz o André decidir isso
pelo Telegram antes de qualquer uma das duas ser chamada — o portão humano
continua existindo, só muda de canal (do navegador para o Telegram).

Este módulo NÃO chama o Argos. Ele só administra a decisão do André. Quem
chama o Argos depois de ver 'aprovado' aqui é o agente (Claude, via a ponte
Cowork) — a ligação entre os dois é procedural, do mesmo jeito que o sistema
já confia nisso para `schedule_whatsapp_message`. Os dois backends (Argos e
Hermes) vivem em projetos GCP diferentes (argos-gestor-sistemas e
gestao-hermes), então não há verificação cruzada barata — daí o desenho de
uso único (`consumir_autorizacao`) em vez de uma trava mais forte.
"""

from __future__ import annotations

import datetime
from datetime import timezone
import html

from firebase_admin import firestore

COLLECTION = "argos_authorization_requests"

STATUS_AGUARDANDO = "aguardando_decisao"
STATUS_APROVADO = "aprovado"
STATUS_RECUSADO = "recusado"
STATUS_EXPIRADO = "expirado"
STATUS_USADO = "usado"

TIPOS_VALIDOS = {"approve-plan", "enqueue-job"}

_ROTULO_TIPO = {
    "approve-plan": "Aprovar plano",
    "enqueue-job": "Enfileirar execução",
}

DEFAULT_MINUTOS_EXPIRACAO = 30


# ---------------------------------------------------------------------------
# Lógica pura (separada de Firestore / rede para testes unitários)
# ---------------------------------------------------------------------------

def _to_iso(val) -> str | None:
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def validar_transicao_decisao(status_atual: str | None) -> tuple[bool, str]:
    """Valida se a solicitação pode transicionar para aprovado/recusado."""
    if status_atual == STATUS_AGUARDANDO:
        return True, ""
    if status_atual is None:
        return False, "Solicitação não encontrada."
    return False, f"já decidida (status atual: {status_atual})"


def montar_card_telegram_autorizacao(
    tipo: str,
    sistema_id: str,
    demanda_id: str,
    resumo: str,
    solicitacao_id: str,
) -> tuple[str, list[list[dict]]]:
    """Monta o texto e os botões inline do card de autorização no Telegram."""
    rotulo = _ROTULO_TIPO.get(tipo, tipo)
    corpo = (
        f"🔐 <b>Autorização solicitada — Argos</b>\n"
        f"Ação: <b>{html.escape(str(rotulo))}</b>\n"
        f"Sistema: {html.escape(str(sistema_id))}\n"
        f"Demanda: {html.escape(str(demanda_id))}\n\n"
        f"{html.escape(str(resumo or '').strip())}"
    )
    botoes = [
        [
            {"text": "✅ Autorizar", "callback_data": f"argos_auth:{solicitacao_id}:aprovar"},
            {"text": "❌ Recusar", "callback_data": f"argos_auth:{solicitacao_id}:recusar"},
        ]
    ]
    return corpo, botoes


def _expirar_se_vencida(doc_ref, data: dict, agora: datetime.datetime) -> dict:
    """Expira preguiçosamente uma solicitação vencida ainda em aguardando_decisao.

    Não depende de um job periódico: qualquer leitura (consultar_autorizacao)
    ou tentativa de decisão feita depois do prazo já resolve o estado certo.
    """
    if data.get("status") != STATUS_AGUARDANDO:
        return data
    expira_em = data.get("expira_em")
    if expira_em is None:
        return data
    try:
        vencida = agora > expira_em
    except TypeError:
        vencida = False
    if vencida:
        doc_ref.update({"status": STATUS_EXPIRADO})
        data = {**data, "status": STATUS_EXPIRADO}
    return data


# ---------------------------------------------------------------------------
# Firestore + Telegram
# ---------------------------------------------------------------------------

def solicitar_autorizacao(
    db,
    tipo: str,
    sistema_id: str,
    demanda_id: str,
    resumo: str,
    telegram_token: str | None = None,
    chat_id: str | int | None = None,
    minutos_expiracao: int = DEFAULT_MINUTOS_EXPIRACAO,
) -> dict:
    """Cria uma solicitação de autorização e envia o card ao Telegram do dono."""
    tipo = str(tipo or "").strip()
    sistema_id = str(sistema_id or "").strip()
    demanda_id = str(demanda_id or "").strip()
    resumo = str(resumo or "").strip()

    if tipo not in TIPOS_VALIDOS:
        return {"erro": f"tipo inválido; use um de: {', '.join(sorted(TIPOS_VALIDOS))}."}
    if not sistema_id:
        return {"erro": "sistema_id é obrigatório."}
    if not demanda_id:
        return {"erro": "demanda_id é obrigatório."}
    if not resumo:
        return {"erro": "resumo é obrigatório — descreva o que está sendo autorizado."}

    minutos_expiracao = int(minutos_expiracao or DEFAULT_MINUTOS_EXPIRACAO)
    agora_utc = datetime.datetime.now(timezone.utc)
    expira_em = agora_utc + datetime.timedelta(minutes=max(1, minutos_expiracao))

    doc_ref = db.collection(COLLECTION).document()
    solicitacao_id = doc_ref.id
    doc_ref.set({
        "tipo": tipo,
        "sistema_id": sistema_id,
        "demanda_id": demanda_id,
        "resumo": resumo,
        "status": STATUS_AGUARDANDO,
        "created_at": firestore.SERVER_TIMESTAMP,
        "expira_em": expira_em,
    })

    telegram_msg_id = None
    try:
        from hermes_core_logic import _get_telegram_token, _send_telegram_message_with_keyboard
        from main import _resolve_default_telegram_chat_id

        token = telegram_token or _get_telegram_token(db)
        target_chat = chat_id or _resolve_default_telegram_chat_id(db)
        if token and target_chat:
            card_text, card_keyboard = montar_card_telegram_autorizacao(
                tipo, sistema_id, demanda_id, resumo, solicitacao_id
            )
            telegram_msg_id = _send_telegram_message_with_keyboard(token, target_chat, card_text, card_keyboard)
            if telegram_msg_id:
                doc_ref.update({"telegram_message_id": telegram_msg_id})
    except Exception as tg_err:
        print(f"[ArgosAutorizacao] Falha ao enviar card Telegram para {solicitacao_id}: {tg_err}")

    return {
        "status": STATUS_AGUARDANDO,
        "solicitacao_id": solicitacao_id,
        "telegram_notificado": bool(telegram_msg_id),
        "expira_em": _to_iso(expira_em),
        "instrucao": (
            "Aguardando decisão do André no Telegram. Não afirme que foi autorizado; "
            "chame consultar_autorizacao_argos com este solicitacao_id até ver status "
            "'aprovado', e só então consumir_autorizacao_argos imediatamente antes de "
            "chamar o endpoint do Argos (approve-plan ou jobs) com este mesmo "
            f"solicitacao_id como autorizacaoId. Expira automaticamente após "
            f"{minutos_expiracao} min sem decisão."
        ),
    }


def decidir_autorizacao(
    db,
    solicitacao_id: str,
    decisao: str,
    telegram_token: str | None = None,
    chat_id: str | int | None = None,
    telegram_msg_id: int | None = None,
) -> dict:
    """Transição atômica de aguardando_decisao para aprovado|recusado.

    Chamada pelo callback do Telegram quando o André toca um dos botões.
    """
    solicitacao_id = str(solicitacao_id or "").strip()
    decisao = str(decisao or "").strip()
    if not solicitacao_id:
        return {"status": "erro", "erro": "solicitacao_id é obrigatório."}
    if decisao not in ("aprovar", "recusar"):
        return {"status": "erro", "erro": "decisao deve ser 'aprovar' ou 'recusar'."}

    novo_status = STATUS_APROVADO if decisao == "aprovar" else STATUS_RECUSADO
    doc_ref = db.collection(COLLECTION).document(solicitacao_id)
    agora_utc = datetime.datetime.now(timezone.utc)

    transaction_result: dict = {}
    transaction_success = False
    if hasattr(db, "transaction"):
        try:
            transaction = db.transaction()

            @firestore.transactional
            def _exec(tx):
                snap = doc_ref.get(transaction=tx)
                if not snap.exists:
                    return {"status": "not_found", "erro": f"Solicitação '{solicitacao_id}' não encontrada."}
                data = snap.to_dict() or {}
                valido, motivo = validar_transicao_decisao(data.get("status"))
                if not valido:
                    return {"status": "already_decided", "erro": f"Solicitação {motivo}", "dados": data}
                tx.update(doc_ref, {
                    "status": novo_status,
                    "decidido_em": firestore.SERVER_TIMESTAMP,
                    "decidido_via": "telegram",
                })
                return {"status": "ok", "dados": data}

            transaction_result = _exec(transaction)
            transaction_success = True
        except Exception as tx_err:
            print(f"[ArgosAutorizacao] Transação Firestore falhou ou mock sem suporte: {tx_err}")

    if not transaction_success:
        snap = doc_ref.get()
        if not snap.exists:
            return {"status": "not_found", "erro": f"Solicitação '{solicitacao_id}' não encontrada."}
        data = snap.to_dict() or {}
        valido, motivo = validar_transicao_decisao(data.get("status"))
        if not valido:
            return {"status": "already_decided", "erro": f"Solicitação {motivo}", "dados": data}
        doc_ref.update({"status": novo_status, "decidido_em": agora_utc, "decidido_via": "telegram"})
        transaction_result = {"status": "ok", "dados": data}

    if transaction_result.get("status") != "ok":
        return transaction_result

    data = transaction_result.get("dados") or {}
    rotulo = _ROTULO_TIPO.get(data.get("tipo"), data.get("tipo"))

    msg_id = telegram_msg_id or data.get("telegram_message_id")
    if msg_id:
        try:
            from core.telegram_api import edit_message
            from hermes_core_logic import _get_telegram_token
            from main import _resolve_default_telegram_chat_id

            token = telegram_token or _get_telegram_token(db)
            target_chat = chat_id or _resolve_default_telegram_chat_id(db)
            if token and target_chat:
                if novo_status == STATUS_APROVADO:
                    novo_texto = (
                        f"✅ <b>Autorizado — {html.escape(str(rotulo))}</b>\n"
                        f"Sistema: {html.escape(str(data.get('sistema_id')))}\n"
                        f"Demanda: {html.escape(str(data.get('demanda_id')))}"
                    )
                else:
                    novo_texto = (
                        f"❌ <b>Recusado — {html.escape(str(rotulo))}</b>\n"
                        f"Sistema: {html.escape(str(data.get('sistema_id')))}\n"
                        f"Demanda: {html.escape(str(data.get('demanda_id')))}"
                    )
                edit_message(token, target_chat, int(msg_id), novo_texto)
        except Exception as edit_err:
            print(f"[ArgosAutorizacao] Falha ao editar mensagem Telegram {msg_id}: {edit_err}")

    return {"status": "ok", "solicitacao_id": solicitacao_id, "decisao": novo_status}


def consultar_autorizacao(db, solicitacao_id: str) -> dict:
    """Consulta somente-leitura do estado de uma solicitação; expira preguiçosamente se vencida."""
    solicitacao_id = str(solicitacao_id or "").strip()
    if not solicitacao_id:
        return {"erro": "solicitacao_id é obrigatório."}
    doc_ref = db.collection(COLLECTION).document(solicitacao_id)
    snap = doc_ref.get()
    if not snap.exists:
        return {"status": "not_found", "erro": f"Solicitação '{solicitacao_id}' não encontrada."}
    data = snap.to_dict() or {}
    data = _expirar_se_vencida(doc_ref, data, datetime.datetime.now(timezone.utc))
    return {
        "status": data.get("status"),
        "solicitacao_id": solicitacao_id,
        "tipo": data.get("tipo"),
        "sistema_id": data.get("sistema_id"),
        "demanda_id": data.get("demanda_id"),
        "resumo": data.get("resumo"),
        "expira_em": _to_iso(data.get("expira_em")),
    }


def consumir_autorizacao(db, solicitacao_id: str) -> dict:
    """Marca atomicamente uma autorização 'aprovado' como 'usado' — uso único.

    Chamar imediatamente antes de agir no Argos, nunca antes. Só depois disto
    devolver status 'ok' é seguro prosseguir; uma segunda chamada com o mesmo
    id devolve 'already_used', nunca autoriza duas vezes a mesma decisão.
    """
    solicitacao_id = str(solicitacao_id or "").strip()
    if not solicitacao_id:
        return {"status": "erro", "erro": "solicitacao_id é obrigatório."}
    doc_ref = db.collection(COLLECTION).document(solicitacao_id)
    agora_utc = datetime.datetime.now(timezone.utc)

    transaction_success = False
    result: dict = {}
    if hasattr(db, "transaction"):
        try:
            transaction = db.transaction()

            @firestore.transactional
            def _exec(tx):
                snap = doc_ref.get(transaction=tx)
                if not snap.exists:
                    return {"status": "not_found", "erro": f"Solicitação '{solicitacao_id}' não encontrada."}
                data = snap.to_dict() or {}
                status_atual = data.get("status")
                if status_atual == STATUS_USADO:
                    return {"status": "already_used", "erro": "Esta autorização já foi consumida."}
                if status_atual != STATUS_APROVADO:
                    return {"status": "not_approved", "erro": f"Solicitação não está aprovada (status atual: {status_atual})."}
                tx.update(doc_ref, {"status": STATUS_USADO, "usado_em": firestore.SERVER_TIMESTAMP})
                return {"status": "ok"}

            result = _exec(transaction)
            transaction_success = True
        except Exception as tx_err:
            print(f"[ArgosAutorizacao] Transação Firestore falhou ou mock sem suporte: {tx_err}")

    if not transaction_success:
        snap = doc_ref.get()
        if not snap.exists:
            return {"status": "not_found", "erro": f"Solicitação '{solicitacao_id}' não encontrada."}
        data = snap.to_dict() or {}
        status_atual = data.get("status")
        if status_atual == STATUS_USADO:
            return {"status": "already_used", "erro": "Esta autorização já foi consumida."}
        if status_atual != STATUS_APROVADO:
            return {"status": "not_approved", "erro": f"Solicitação não está aprovada (status atual: {status_atual})."}
        doc_ref.update({"status": STATUS_USADO, "usado_em": agora_utc})
        result = {"status": "ok"}

    if result.get("status") != "ok":
        return result
    return {"status": "ok", "solicitacao_id": solicitacao_id}
