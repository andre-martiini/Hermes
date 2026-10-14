"""Botões do Modo Objetivo no Telegram (`objwa:{objetivo_id}:{ação}`).

- resp: a próxima mensagem do André vira a resposta à pergunta do Gaspar;
- retomar: volta a conduzir depois de uma pausa;
- mais30: mais 30 minutos de prazo;
- fim: encerra o objetivo.
"""

from telegram_utils import _answer_callback_query, _arm_free_text_capture, _save_session, _send_telegram_message

CAPTURA_RESPOSTA = "pending_objetivo_resposta"


def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id, _persist_callback_turn,
           _pending_web_card, _clear_pending_web_card) -> bool:
    if not data.startswith("objwa:"):
        return False
    import objetivos_whatsapp

    partes = data.split(":")
    objetivo_id = partes[1] if len(partes) > 1 else ""
    acao = partes[2] if len(partes) > 2 else ""
    if not objetivo_id or acao not in ("resp", "retomar", "mais30", "fim"):
        _answer_callback_query(token, query_id, "Ação não reconhecida.")
        return True

    if acao == "resp":
        _arm_free_text_capture(session, CAPTURA_RESPOSTA, objetivo_id)
        _save_session(db, chat_id, session)
        _answer_callback_query(token, query_id, "Me manda a resposta.")
        texto = "✍️ Me manda a resposta para eu seguir a conversa."
        _persist_callback_turn(f"Botão: responder objetivo {objetivo_id}", texto)
        _send_telegram_message(token, chat_id, texto)
        return True

    if acao == "fim":
        res = objetivos_whatsapp.encerrar(db, objetivo_id, "encerrado pelo André no Telegram")
        aviso = "Objetivo encerrado." if not res.get("erro") else res["erro"]
    else:
        res = objetivos_whatsapp.responder_do_dono(db, objetivo_id, estender_min=30 if acao == "mais30" else None)
        aviso = ("Retomei a conversa." if acao == "retomar" else "Mais 30 minutos.") if not res.get("erro") else res["erro"]
    _answer_callback_query(token, query_id, aviso[:190])
    _persist_callback_turn(f"Botão: {acao} objetivo {objetivo_id}", aviso)
    return True
