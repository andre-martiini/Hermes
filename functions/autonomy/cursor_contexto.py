"""Cursor de contexto incremental (P06 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, passo 7 do pacote: "Implementar
contexto incremental com cursor, resumo de mudanças e invalidações. Cursor
vinculado a proprietário/escopo; não reutilizar entre usuários.").

Lógica pura -- sem I/O, mesmo padrão incremental de `autonomy/context.py`,
`memoria_suspeita.py` e `pops_mapa.py`. O segredo de assinatura é recebido
como parâmetro (quem ligar isto a `obter_contexto_operacional` decide de onde
ele vem); este módulo não lê ambiente nem Firestore.

O cursor é opaco para o cliente: `v1.<payload b64url>.<assinatura hex>`, com
payload `{o: owner_uid, e: escopo, m: marca}` e HMAC-SHA256 sobre o payload.
`marca` é um inteiro monotônico (ex.: ms de `atualizado_em` do último item
entregue). Um cursor emitido para um dono/escopo é recusado para outro --
inclusive com assinatura válida -- e qualquer adulteração é recusada. Sem
validade temporal: invalidar por correção é papel do chamador via `marca`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

_VERSAO = "v1"
_MAX_CURSOR = 2048


class CursorInvalido(ValueError):
    """Cursor malformado, adulterado ou de outro dono/escopo."""


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def _unb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _assina(segredo: bytes, payload_b64: str) -> str:
    return hmac.new(segredo, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()


def _segredo_bytes(segredo) -> bytes:
    if isinstance(segredo, str):
        segredo = segredo.encode("utf-8")
    if not isinstance(segredo, (bytes, bytearray)) or not segredo:
        raise ValueError("segredo de cursor ausente")
    return bytes(segredo)


def _texto_obrigatorio(valor, nome: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"{nome} obrigatório")
    return valor


def emitir_cursor(segredo, owner_uid: str, escopo: str, marca: int) -> str:
    owner_uid = _texto_obrigatorio(owner_uid, "owner_uid")
    escopo = _texto_obrigatorio(escopo, "escopo")
    if isinstance(marca, bool) or not isinstance(marca, int) or marca < 0:
        raise ValueError("marca deve ser inteiro >= 0")
    payload = json.dumps({"o": owner_uid, "e": escopo, "m": marca}, separators=(",", ":"), sort_keys=True)
    payload_b64 = _b64(payload.encode("utf-8"))
    cursor = f"{_VERSAO}.{payload_b64}.{_assina(_segredo_bytes(segredo), payload_b64)}"
    if len(cursor) > _MAX_CURSOR:
        raise ValueError("cursor excede o tamanho máximo (owner_uid/escopo longos demais)")
    return cursor


def validar_cursor(segredo, cursor, owner_uid: str, escopo: str) -> int:
    """Devolve a `marca` ou levanta `CursorInvalido` (sem detalhar o motivo)."""
    chave = _segredo_bytes(segredo)
    _texto_obrigatorio(owner_uid, "owner_uid")
    _texto_obrigatorio(escopo, "escopo")
    try:
        if not isinstance(cursor, str) or len(cursor) > _MAX_CURSOR:
            raise CursorInvalido("cursor inválido")
        versao, payload_b64, assinatura = cursor.split(".")
        if versao != _VERSAO:
            raise CursorInvalido("cursor inválido")
        if not hmac.compare_digest(_assina(chave, payload_b64), assinatura):
            raise CursorInvalido("cursor inválido")
        payload = json.loads(_unb64(payload_b64).decode("utf-8"))
        marca = payload["m"]
        if payload["o"] != owner_uid or payload["e"] != escopo:
            raise CursorInvalido("cursor inválido")
        if isinstance(marca, bool) or not isinstance(marca, int) or marca < 0:
            raise CursorInvalido("cursor inválido")
        return marca
    except CursorInvalido:
        raise
    except Exception as exc:  # split/base64/json/chaves ausentes
        raise CursorInvalido("cursor inválido") from exc
