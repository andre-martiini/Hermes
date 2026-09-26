"""Callbacks do Telegram - espelho semanal do perfil pessoal

Depois de gravar um perfil novo, `consolidar_personalidade`
(personal_diary.py) manda "🪞 O que percebi em você esta semana" com dois
botões:

- "✏️ Corrigir" (`perfil:fix`): marca a sessão com `pending_perfil_ajuste`
  (mesmo padrão de `pending_diary_edit` do "✍️ Ajustar" do diário, e armar
  um limpa os outros — `_arm_free_text_capture`); a próxima
  mensagem livre vira a correção, gravada por
  `personal_diary.registrar_ajuste_personalidade` em
  telegram_message_deterministic.py.
- "👍 Está certo" (`perfil:ok`): só agradece.

Mesmo contrato dos demais `telegram_callbacks_*`: `handle(...)` devolve True
quando tratou o callback; o dispatcher em telegram_handlers_core.py monta a
resposta HTTP.

ATENCAO para mock.patch em testes: os nomes livres (`_answer_callback_query`,
`_send_telegram_message`, `_save_session`) são resolvidos pelo namespace DESTE
módulo.
"""
from datetime import datetime, timezone

from personal_diary import PERFIL_CALLBACK_CORRIGIR, PERFIL_CALLBACK_OK
from telegram_utils import (
    _answer_callback_query,
    _arm_free_text_capture,
    _save_session,
    _send_telegram_message,
)

PENDING_KEY = "pending_perfil_ajuste"
PEDIDO_CORRECAO = (
    "✏️ Me conta o que não bate no que eu percebi. "
    "Sua próxima mensagem vira a correção — ela pesa mais do que qualquer impressão minha."
)


def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id, _persist_callback_turn, _pending_web_card, _clear_pending_web_card) -> bool:
    """Trata perfil:fix / perfil:ok. Retorna True se tratou."""
    if data == PERFIL_CALLBACK_CORRIGIR:
        _arm_free_text_capture(session, PENDING_KEY, datetime.now(timezone.utc).isoformat())
        _save_session(db, chat_id, session)
        _answer_callback_query(token, query_id, "Me conta o que corrigir.")
        _persist_callback_turn("Botão: corrigir perfil pessoal", PEDIDO_CORRECAO)
        _send_telegram_message(token, chat_id, PEDIDO_CORRECAO)
        return True

    if data == PERFIL_CALLBACK_OK:
        _answer_callback_query(token, query_id, "Valeu! Sigo com essa leitura.")
        _persist_callback_turn("Botão: perfil pessoal está certo", "Valeu! Sigo com essa leitura.")
        return True

    return False
