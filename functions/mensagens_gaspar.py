"""Reconhece as mensagens que o próprio Gaspar mandou no WhatsApp em nome do André.

O Modo Secretário e o Modo Objetivo (as mensagens totalmente autônomas) escrevem pela conta
do André e, desde 28/10/2026 (decisão do dono, que revoga a primeira pessoa sem assinatura
de 14/10), com o prefixo de identificação PREFIXO_IDENTIFICACAO, que o código acrescenta no
ponto de saída de cada modo. A mensagem que o agente manda com o sim do André (envio normal,
encaminhamento) NÃO se identifica: sai em primeira pessoa, como ele (decisão de 29/10);
`schedule_whatsapp_message(como_assistente=True)` existe, mas ninguém o usa. A resposta volta
capturada como `from_me`, igual a uma mensagem que o André digitou; sem este registro o
sistema acharia que o André assumiu a conversa a cada resposta do Gaspar.

O registro é gravado ANTES do envio (na criação do rascunho de envio imediato ou
na aprovação), então o eco sempre o encontra. A chave é só o texto: o eco pode
chegar com outro id de chat (`@lid` em vez de `@c.us`), e duas mensagens iguais
em poucos minutos, uma do André e outra do Gaspar, é caso desprezível.
"""

import hashlib
import re
from datetime import datetime, timedelta, timezone

COLECAO = "whatsapp_enviados_gaspar"
ORIGENS_AUTONOMAS = frozenset({"secretario_whatsapp", "objetivo_whatsapp"})
_VALIDADE = timedelta(hours=6)

# Toda mensagem do Gaspar a terceiros começa com este prefixo, que o código acrescenta (decisão do
# dono, 28/10/2026: o Gaspar precisa se identificar como bot, não falar como o André).
PREFIXO_IDENTIFICACAO = "*Gaspar Bot (assistente virtual do André):*"
# Reconhece o prefixo e as assinaturas antigas ("**Gaspar Bot:**", antes "**Hermes Bot:**"),
# inclusive com descrição entre parênteses: `secretario_whatsapp.eh_mensagem_do_bot` a usa no eco
# `from_me` e `sem_assinatura` a remove se o modelo a escrever (o código põe o prefixo uma vez só).
# "Gaspar" sem "Bot" só conta com os dois-pontos: Gaspar também é nome de gente, e uma
# mensagem do André que comece com "Gaspar, ..." não pode ser lida como do bot.
_RE_ASSINATURA_BOT = re.compile(
    r"^\*{0,2}\s*(?:(?:Hermes|Gaspar) Bot(?:\s*\([^)\n]{0,60}\))?(?:\s*(?::|\*{1,2}\s*:))?"
    r"|Gaspar\s*(?::|\*{1,2}\s*:))\*{0,2}\s*",
    re.IGNORECASE,
)


def sem_assinatura(texto: str) -> str:
    """Tira o prefixo de identificação e as assinaturas antigas ("**Gaspar Bot:**" e variações), se o modelo as escrever."""
    return _RE_ASSINATURA_BOT.sub("", str(texto or "").strip()).strip()


def com_identificacao(texto: str) -> str:
    """O texto como vai ao contato: PREFIXO_IDENTIFICACAO, quebra de linha e a mensagem, uma vez só."""
    return f"{PREFIXO_IDENTIFICACAO}\n{sem_assinatura(texto)}"


def _chave(texto: str) -> str:
    normalizado = " ".join(str(texto or "").split())
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()[:40]


def registrar(db, texto: str, *, origem: str, chat_id: str = "", ref_id: str | None = None) -> None:
    if not str(texto or "").strip():
        return
    agora = datetime.now(timezone.utc)
    try:
        db.collection(COLECAO).document(_chave(texto)).set({
            "origem": origem,
            "chat_id": chat_id,
            "ref_id": ref_id,
            "registrado_em": agora,
            "expira_em": agora + _VALIDADE,
        })
    except Exception as exc:  # noqa: BLE001 — sem o registro o pior caso é pausar por engano
        print(f"[MensagensGaspar] Falha ao registrar envio: {exc}")


def encontrar(db, mensagem: dict) -> dict | None:
    """O registro do envio do Gaspar que gerou esta mensagem `from_me`, se houver."""
    if not mensagem.get("from_me"):
        return None
    texto = mensagem.get("content") or mensagem.get("text") or ""
    if not str(texto).strip():
        return None
    try:
        snap = db.collection(COLECAO).document(_chave(texto)).get()
    except Exception as exc:  # noqa: BLE001
        print(f"[MensagensGaspar] Falha ao consultar registro: {exc}")
        return None
    dados = snap.to_dict() if snap.exists else None
    if not isinstance(dados, dict) or not dados.get("origem"):
        return None
    expira = dados.get("expira_em")
    if isinstance(expira, datetime) and expira < datetime.now(timezone.utc):
        return None
    return dados


def eh_do_gaspar(db, mensagem: dict) -> bool:
    return encontrar(db, mensagem) is not None
