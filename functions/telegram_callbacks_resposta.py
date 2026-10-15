"""Botões do aviso de resposta esperada (`respesp:{aviso_id}:{feito|ok|nao}`)."""

from telegram_utils import _answer_callback_query


def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id, _persist_callback_turn,
           _pending_web_card, _clear_pending_web_card) -> bool:
    if not data.startswith("respesp:"):
        return False
    import resposta_esperada_avisos

    partes = data.split(":")
    aviso_id = partes[1] if len(partes) > 1 else ""
    acao = partes[2] if len(partes) > 2 else ""
    texto = resposta_esperada_avisos.tratar_botao(db, aviso_id, acao) if aviso_id else "Ação não reconhecida."
    _answer_callback_query(token, query_id, texto[:190])
    _persist_callback_turn(f"Botão: {acao} aviso de resposta {aviso_id}", texto)
    return True
