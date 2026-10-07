"""Ideias soltas (tela Brainstorming do app web), gravadas e lidas pelo MCP.

Mesma colecao e mesmo formato que `index.tsx::handleAddTextIdea` grava:
`text`, `timestamp` (ISO UTC com milissegundos e "Z", como `toISOString()` do
JS -- a tela ordena por `localeCompare` dessa string, entao o formato tem de
ser identico) e `status`. Documento sem `status` conta como ativo, igual a tela
(`status !== 'archived'`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from tools.lista_compras import normalize_name

COLECAO = "brainstorm_ideas"
LIMITE_TEXTO = 4000
_STATUS = ("active", "archived", "todas")
_LIMITE_PADRAO = 20
_LIMITE_MAXIMO = 100


class IdeiasError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def guardar(db, texto, contexto=None) -> dict:
    texto = str(texto or "").strip()
    if not texto:
        raise IdeiasError("Texto da ideia vazio.")
    contexto = str(contexto or "").strip()
    if contexto:
        texto = f"{texto}\nContexto: {contexto}"
    if len(texto) > LIMITE_TEXTO:
        raise IdeiasError(f"Ideia longa demais ({len(texto)} caracteres; maximo {LIMITE_TEXTO}).")

    timestamp = _agora_iso()
    ref = db.collection(COLECAO).document()
    ref.set({"text": texto, "timestamp": timestamp, "status": "active", "origem": "mcp"})
    return {"id": ref.id, "texto": texto, "timestamp": timestamp}


def listar(db, busca=None, status=None, limite=None) -> dict:
    status = str(status or "active").strip().lower()
    if status not in _STATUS:
        raise IdeiasError("Status invalido. Use: active, archived ou todas.")
    try:
        teto = _LIMITE_PADRAO if limite is None else int(limite)
    except (TypeError, ValueError):
        raise IdeiasError("Limite deve ser um numero inteiro.")
    teto = min(max(1, teto), _LIMITE_MAXIMO)

    termo = normalize_name(busca or "")
    ideias = []
    for snap in db.collection(COLECAO).stream():
        dados = snap.to_dict() or {}
        st = "archived" if dados.get("status") == "archived" else "active"
        if status != "todas" and st != status:
            continue
        texto = str(dados.get("text") or "")
        if termo and termo not in normalize_name(texto):
            continue
        ideias.append({"id": snap.id, "texto": texto, "data": str(dados.get("timestamp") or ""), "status": st})

    ideias.sort(key=lambda i: i["data"], reverse=True)
    return {"total": len(ideias), "retornados": min(len(ideias), teto), "ideias": ideias[:teto]}
