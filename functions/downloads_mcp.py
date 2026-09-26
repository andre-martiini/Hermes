"""Download de arquivo do Storage pela própria origem do MCP.

Par do `/mcp/upload/<token>` (`tools/anexar_arquivo.receber_upload`): há
ambiente de cliente — o Claude na nuvem, atrás de um proxy de egresso — que
bloqueia `firebasestorage.googleapis.com` e `storage.googleapis.com`. A origem
do Hermes (`gestao-hermes.firebaseapp.com`) é necessariamente alcançável, porque
é por ela que o MCP conversa; então o arquivo sai por lá:

    GET https://gestao-hermes.firebaseapp.com/mcp/download/<token>

O `token` é a credencial: 192 bits, opaco, preso a UM caminho do Storage
gravado na criação, válido por 24 h. Não há listagem nem caminho vindo da URL —
quem não tem o token não chega a arquivo nenhum. Mesmo modelo de uma URL
assinada de leitura, sem precisar de `signBlob`.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

COLECAO = "downloads_mcp"
TTL_HORAS = 24
ORIGEM_MCP = "https://gestao-hermes.firebaseapp.com"
# Só estes prefixos do bucket podem ganhar link: defesa extra caso um chamador
# futuro passe um caminho vindo de fora.
PREFIXOS_PERMITIDOS = ("imagens_geradas/",)


def criar_link(db, *, uid: str | None, caminho: str, nome: str, mime: str,
               agora: datetime | None = None) -> str:
    if not caminho.startswith(PREFIXOS_PERMITIDOS):
        raise ValueError(f"caminho fora dos prefixos de download: {caminho!r}")
    agora = agora or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(24)
    db.collection(COLECAO).document(token).set({
        "uid": uid,
        "caminho": caminho,
        "nome": nome,
        "mime": mime,
        "criado_em": agora.isoformat(),
        "expira_em": (agora + timedelta(hours=TTL_HORAS)).isoformat(),
    })
    return f"{ORIGEM_MCP}/mcp/download/{token}"


def resolver(db, token: str, agora: datetime | None = None) -> dict:
    """{"caminho", "nome", "mime"} do token, ou {"erro", "status"} (404 desconhecido, 410 expirado)."""
    if not token or len(token) > 64:
        return {"erro": "Link de download desconhecido.", "status": 404}
    snap = db.collection(COLECAO).document(token).get()
    if not snap.exists:
        return {"erro": "Link de download desconhecido.", "status": 404}
    dados = snap.to_dict() or {}
    agora = agora or datetime.now(timezone.utc)
    if dados.get("expira_em", "") < agora.isoformat():
        return {"erro": "Link de download expirado (vale 24 h). Gere a imagem de novo ou use o link do Drive.",
                "status": 410}
    caminho = dados.get("caminho") or ""
    if not caminho.startswith(PREFIXOS_PERMITIDOS):
        return {"erro": "Link de download desconhecido.", "status": 404}
    return {"caminho": caminho, "nome": dados.get("nome") or caminho.rsplit("/", 1)[-1],
            "mime": dados.get("mime") or "application/octet-stream"}


def servir(db, bucket, token: str) -> tuple[bytes | None, int, dict]:
    """(corpo, status, headers). Erro sai como texto curto."""
    alvo = resolver(db, token)
    if "erro" in alvo:
        return alvo["erro"].encode("utf-8"), alvo["status"], {"Content-Type": "text/plain; charset=utf-8",
                                                               "Cache-Control": "no-store"}
    blob = bucket.blob(alvo["caminho"])
    try:
        corpo = blob.download_as_bytes()
    except Exception as exc:  # noqa: BLE001 — objeto apagado do bucket
        print(f"[downloads_mcp] Falha ao ler {alvo['caminho']}: {exc}")
        return b"Arquivo indisponivel.", 404, {"Content-Type": "text/plain; charset=utf-8",
                                                "Cache-Control": "no-store"}
    from urllib.parse import quote

    nome = alvo["nome"]
    ascii_ = nome.encode("ascii", "ignore").decode().replace('"', "") or "arquivo"
    return corpo, 200, {
        "Content-Type": alvo["mime"],
        # Cabeçalho HTTP é latin-1: nome com acento vai em `filename*` (RFC 5987).
        "Content-Disposition": f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(nome)}",
        # O Hosting fica na frente da function: sem isto a CDN guardaria o
        # arquivo e o serviria depois de o token expirar.
        "Cache-Control": "private, no-store",
    }
