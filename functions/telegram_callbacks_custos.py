"""Callbacks do Telegram - relatório diário de custos (resumo <-> detalhe)

O `relatorio_diario_custos` (cost_report.py) envia um resumo curto com o botão
"📋 Ver detalhes" (`custos:det:<dia>`). Tocar no botão edita a MESMA mensagem
para o relatório completo, com "↩️ Resumo" (`custos:res:<dia>`) para voltar.
Os dois textos vêm de `system_reports/custos_<dia>`, gravado no envio — por
isso o botão funciona dias depois, sem recalcular nada (nem BigQuery).

Mesmo contrato dos demais `telegram_callbacks_*`: `handle(...)` devolve True
quando tratou o callback; o dispatcher em telegram_handlers_core.py monta a
resposta HTTP.

ATENCAO para mock.patch em testes: os nomes livres (`_answer_callback_query`,
`_edit_message_text`) são resolvidos pelo namespace DESTE módulo.
"""
import html
import re

import requests as _requests

import cost_report
from telegram_utils import _answer_callback_query, _neutralize_hidden_links


def _edit_message_text(token: str, chat_id, message_id, text: str, inline_keyboard: list) -> bool:
    """editMessageText (HTML) trocando também o teclado inline.

    Se o Telegram recusar o HTML, tenta de novo em texto puro — mesmo fallback
    de `_send_telegram_message_with_keyboard`. "message is not modified"
    (toque duplo no mesmo botão) conta como sucesso.
    """
    text = _neutralize_hidden_links(text)
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": inline_keyboard},
    }
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    try:
        resp = _requests.post(url, json=payload, timeout=30)
        if resp.ok or "message is not modified" in (resp.text or ""):
            return True
        print(f"[CustosCallback] editMessageText falhou: {resp.status_code} {resp.text[:300]}")
        payload.pop("parse_mode")
        payload["text"] = html.unescape(re.sub(r"<[^>]+>", "", text))[:4096]
        retry = _requests.post(url, json=payload, timeout=30)
        return bool(retry.ok)
    except Exception as exc:
        print(f"[CustosCallback] editMessageText erro: {exc}")
        return False


def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id, _persist_callback_turn, _pending_web_card, _clear_pending_web_card) -> bool:
    """Trata custos:det:<dia> / custos:res:<dia>. Retorna True se tratou."""
    if not data.startswith(cost_report.CALLBACK_PREFIX):
        return False

    parsed = cost_report.parse_callback(data)
    message_id = (message or {}).get("message_id")
    if not parsed or not message_id:
        _answer_callback_query(token, query_id, "Botão inválido.")
        return True

    modo, dia = parsed
    try:
        relatorio = cost_report.carregar_relatorio(db, dia)
    except Exception as exc:
        print(f"[CustosCallback] Falha ao ler relatório de {dia}: {exc}")
        relatorio = None
    if not relatorio:
        _answer_callback_query(token, query_id, f"Relatório de custos de {dia} não está mais disponível.")
        return True

    if modo == "det":
        texto, teclado = relatorio["detalhe"], cost_report.detail_keyboard(dia)
    else:
        texto, teclado = relatorio["resumo"], cost_report.summary_keyboard(dia)

    if _edit_message_text(token, chat_id, message_id, texto, teclado):
        _answer_callback_query(token, query_id)
    else:
        _answer_callback_query(token, query_id, "Não consegui atualizar a mensagem.")
    return True
