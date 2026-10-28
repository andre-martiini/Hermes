"""avisar_andre: uma sessão do Claude (chat, Claude Code, Cowork) pede ao Gaspar que avise o André.

Grava um item na fila de atenção (origem `sessao`, tipo `notificacao_sessao`, prioridade alta). Quem
entrega:
- com o agente residente ligado, o canal gaspar-eventos empurra o item e o agente manda no Telegram,
  com a ação do Gaspar e os links (regra no CLAUDE.md do agente), e resolve o item;
- sem o agente, o backend avisa pelo bot antigo (`atencao.avaliar_interrupcao_atencao`, itens de
  prioridade alta, janela das 07:00 às 22:00). Por isso a `sugestao` do item fica vazia: o bot antigo a
  imprime no texto.

A ação do Gaspar (`acao_id`) e os links entram no `resumo`, porque o evento do agente só leva título,
resumo e sugestão no texto. Urgência `critica` grava `prazo` de hoje: é o "prioridade alta E prazo hoje"
que o agente já trata como crítico fora das faixas de horário.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from urllib.parse import urlparse

import atencao

ORIGEM_SESSAO = "sessao"
TIPO_NOTIFICACAO_SESSAO = "notificacao_sessao"
LIMITE_TITULO = 120
LIMITE_RESUMO = 1000
LIMITE_SESSAO = 60
LIMITE_URL = 500
MAX_LINKS = 10
URGENCIAS = ("normal", "critica")


class AvisoError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _texto(valor, limite: int, campo: str, obrigatorio: bool = False) -> str:
    texto = " ".join(str(valor or "").split()) if campo != "resumo" else str(valor or "").strip()
    if obrigatorio and not texto:
        raise AvisoError(f"{campo} e obrigatorio.")
    if len(texto) > limite:
        raise AvisoError(f"{campo} longo demais ({len(texto)} caracteres; maximo {limite}).")
    return texto


def _links(links) -> list[dict]:
    """Aceita lista de {"url", "titulo"} ou de URLs soltas. So http(s), sem espaco nem controle."""
    if not links:
        return []
    if not isinstance(links, (list, tuple)):
        raise AvisoError("links deve ser uma lista.")
    if len(links) > MAX_LINKS:
        raise AvisoError(f"links demais ({len(links)}; maximo {MAX_LINKS}).")
    saida = []
    for item in links:
        url = str(item.get("url") if isinstance(item, dict) else item or "").strip()
        titulo = " ".join(str(item.get("titulo") or "").split())[:80] if isinstance(item, dict) else ""
        partes = urlparse(url)
        if (not url or len(url) > LIMITE_URL or partes.scheme not in ("http", "https") or not partes.netloc
                or any(c.isspace() or ord(c) < 32 for c in url)):
            raise AvisoError(f"link invalido: '{url[:60]}'. Use URL http(s) completa, sem espacos (maximo {LIMITE_URL} caracteres).")
        saida.append({"url": url, "titulo": titulo})
    return saida


def _acao(db, acao_id) -> tuple[str | None, str | None, str | None]:
    """(acao_id, titulo, aviso). Ação inexistente não derruba o aviso: ele sai sem a ação, e o retorno diz."""
    acao_id = str(acao_id or "").strip()
    if not acao_id:
        return None, None, None
    snap = db.collection("tarefas").document(acao_id).get()
    if not snap.exists:
        return None, None, f"acao_id '{acao_id}' nao encontrado; avisei sem a acao."
    return acao_id, str((snap.to_dict() or {}).get("titulo") or "").strip() or None, None


def avisar(db, titulo, resumo, links=None, acao_id=None, sessao=None, urgencia=None) -> dict:
    titulo = _texto(titulo, LIMITE_TITULO, "titulo", obrigatorio=True)
    resumo = _texto(resumo, LIMITE_RESUMO, "resumo", obrigatorio=True)
    sessao = _texto(sessao, LIMITE_SESSAO, "sessao")
    urgencia = str(urgencia or "normal").strip().lower()
    if urgencia not in URGENCIAS:
        raise AvisoError("urgencia invalida. Use: normal ou critica.")
    links = _links(links)
    acao_id, acao_titulo, aviso = _acao(db, acao_id)

    linhas = [resumo]
    if acao_titulo:
        linhas.append(f"Ação do Gaspar: {acao_titulo}")
    if links:
        linhas.append("Links:")
        linhas += [f"- {l['titulo']}: {l['url']}" if l["titulo"] else f"- {l['url']}" for l in links]
    if sessao:
        linhas.append(f"Sessão: {sessao}")

    # Chave única por aviso: _persistir_itens_atencao não reabre item fechado com a mesma chave, e o
    # segundo aviso, depois de o primeiro ser resolvido, seria engolido.
    chave = f"{TIPO_NOTIFICACAO_SESSAO}:{uuid.uuid4().hex}"
    atencao._persistir_itens_atencao(db, [{
        "origem": ORIGEM_SESSAO,
        "tipo": TIPO_NOTIFICACAO_SESSAO,
        "prioridade": atencao.PRIORIDADE_ALTA,
        "titulo": titulo,
        "resumo": "\n".join(linhas),
        "acao_id": acao_id,
        "prazo": datetime.now(atencao._TZ_SP).strftime("%Y-%m-%d") if urgencia == "critica" else None,
        "evidencia": {"sessao": sessao, "links": links, "acao_titulo": acao_titulo, "urgencia": urgencia},
        "sugestao": "",
        "chave_dedupe": chave,
    }])

    gravado = db.collection(atencao.COLLECTION).document(chave).get()
    if not gravado.exists:
        raise AvisoError("nao consegui confirmar a gravacao do aviso; tente de novo.")
    resultado = {"item_id": chave, "estado": (gravado.to_dict() or {}).get("estado"), "acao": acao_titulo}
    if aviso:
        resultado["aviso"] = aviso
    return resultado
