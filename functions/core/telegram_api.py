from typing import Optional

import requests as _requests


def send_message(
    token: str,
    chat_id: str | int,
    text: str,
    parse_mode: str = "HTML",
) -> Optional[int]:
    """Envia mensagem e retorna o message_id, ou None em caso de falha."""
    if len(text) > 4096:
        text = text[:4090] + "\n..."
    resp = _requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
        timeout=30,
    )
    if resp.ok:
        return resp.json().get("result", {}).get("message_id")
    print(f"[Telegram] sendMessage failed: {resp.status_code} {resp.text[:300]}")
    return None


def edit_message(
    token: str,
    chat_id: str | int,
    message_id: int,
    text: str,
    parse_mode: str = "HTML",
) -> bool:
    if len(text) > 4096:
        text = text[:4090] + "\n..."
    resp = _requests.post(
        f"https://api.telegram.org/bot{token}/editMessageText",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        },
        timeout=30,
    )
    return resp.ok


def send_chat_action(token: str, chat_id: str | int, action: str):
    try:
        _requests.post(
            f"https://api.telegram.org/bot{token}/sendChatAction",
            json={"chat_id": chat_id, "action": action},
            timeout=5,
        )
    except Exception:
        pass
