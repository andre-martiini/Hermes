"""
phone_utils.py — Funções utilitárias de extração e normalização de telefones e WhatsApp chat IDs.

Regra canônica para matching de contato ↔ WhatsApp:
- last8(value): últimos 8 dígitos do telefone (espelha contact_merge_utils.py:148 e ContactsView.tsx:223-227).
- chat_id_last8(chat_id): extrai os últimos 8 dígitos do número em um chat individual (@c.us); retorna "" para grupos (@g.us) ou formatos inválidos.

Nota de arquitetura:
Existem 4 normalizações pontuais de telefone em trechos legados da codebase
(ex.: contact_merge_utils, ContactsView, etc.). Elas são mantidas intocadas por segurança;
este módulo concentra a regra canônica para o subsistema de vínculo com WhatsApp.
"""

import re


def last8(value: str | None) -> str:
    """
    Extrai os últimos 8 dígitos de um número de telefone ou string qualquer.
    Retorna '' se houver menos de 8 dígitos.
    """
    if not value:
        return ""
    digits = re.sub(r"\D", "", str(value))
    return digits[-8:] if len(digits) >= 8 else ""


def chat_id_last8(chat_id: str | None) -> str:
    """
    Extrai os últimos 8 dígitos do identificador de um chat individual de WhatsApp (@c.us).
    Retorna '' para grupos (@g.us), formatos desconhecidos ou strings inválidas.
    """
    if not chat_id:
        return ""
    chat_str = str(chat_id).strip()
    if not chat_str.endswith("@c.us"):
        return ""
    number_part = chat_str.split("@", 1)[0]
    return last8(number_part)

def whatsapp_chat_last8(chat_id: str | None, contact_number: str | None = None) -> str:
    """Ultimos 8 digitos do telefone de um chat individual, venha de onde vier.

    Ate 2026 o proprio `chat_id` carregava o numero (`5527999999999@c.us`), e
    extrair dali bastava. O WhatsApp migrou os contatos individuais para `@lid`
    — um identificador que **nao deriva do telefone**. Na varredura de
    27/08/2026 havia 450 chats `@lid` e apenas 2 `@c.us`, um deles a conta do
    sistema: comparar os digitos de um `@lid` com um telefone real nao casava
    nada, e o vinculo automatico rendia zero.

    O numero passou a ser resolvido pelo worker (`chat.getContact()`) e gravado
    em `whatsapp_chats.contact_number`. Esta funcao prefere esse campo e mantem
    o `@c.us` como caminho legado, para os chats antigos continuarem casando.
    """
    do_campo = last8(contact_number)
    if do_campo:
        return do_campo
    return chat_id_last8(chat_id)
