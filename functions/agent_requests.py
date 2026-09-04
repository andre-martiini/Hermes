"""Fila de trabalho autônomo do Hermes (agent_requests).

Enfileira tarefas autônomas (que não precisam de decisão prévia do dono)
para serem executadas pela próxima sessão agendada do Claude (ex.: consolidação de áudios).
Mantém estrita separação entre lógica pura e I/O com Firestore.
"""

from __future__ import annotations

import datetime
from firebase_admin import firestore

COLLECTION = "agent_requests"

TIPO_CONSOLIDAR_AUDIO = "consolidar_audio"

STATUS_PENDENTE = "pendente"
STATUS_EM_ANDAMENTO = "em_andamento"
STATUS_CONCLUIDO = "concluido"
STATUS_ERRO = "erro"

STATUS_TERMINAIS = {STATUS_CONCLUIDO, STATUS_ERRO}


# ---------------------------------------------------------------------------
# Lógica pura (testável sem Firestore / I/O)
# ---------------------------------------------------------------------------


def validar_transicao(status_atual: str | None) -> tuple[bool, str]:
    """Valida se o pedido pode transicionar para concluído ou erro.

    Só aceita concluir/errar a partir de 'pendente' ou 'em_andamento'.
    'concluido' e 'erro' são terminais (não regridem nem se sobrescrevem).
    """
    if status_atual in (STATUS_PENDENTE, STATUS_EM_ANDAMENTO):
        return True, ""
    if status_atual is None:
        return False, "Pedido não encontrado."
    if status_atual in STATUS_TERMINAIS:
        return False, f"já decidido (status atual: {status_atual})"
    return False, f"status inválido: {status_atual}"


def montar_payload_consolidar_audio(
    chat_id: str,
    chat_name: str,
    mensagem_ids: list[str],
    acao_id: str | None = None,
    item_atencao_id: str | None = None,
) -> dict:
    """Monta o payload padronizado para pedidos do tipo consolidar_audio."""
    return {
        "chat_id": str(chat_id or "").strip(),
        "chat_name": str(chat_name or "").strip(),
        "mensagem_ids": list(mensagem_ids or []),
        "acao_id": str(acao_id).strip() if acao_id else None,
        "item_atencao_id": str(item_atencao_id).strip() if item_atencao_id else None,
    }


def _to_iso(dt: object) -> str | None:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


# ---------------------------------------------------------------------------
# Operações Firestore (I/O)
# ---------------------------------------------------------------------------


def enfileirar_ou_atualizar(
    db,
    doc_id: str,
    tipo: str,
    payload: dict,
    origem: str,
    acao_id: str | None = None,
    item_atencao_id: str | None = None,
) -> dict:
    """Cria um novo pedido ou atualiza um pedido existente se ainda estiver pendente.

    Se o pedido já existir e estiver em_andamento, concluido ou erro, NÃO mexe
    para evitar concorrência com o executor.
    """
    doc_id = str(doc_id or "").strip()
    if not doc_id:
        return {"erro": "doc_id é obrigatório."}

    doc_ref = db.collection(COLLECTION).document(doc_id)
    snap = doc_ref.get()

    if not snap.exists:
        data = {
            "tipo": tipo,
            "status": STATUS_PENDENTE,
            "payload": payload,
            "origem": origem,
            "item_atencao_id": item_atencao_id,
            "acao_id": acao_id,
            "criado_em": firestore.SERVER_TIMESTAMP,
            "atualizado_em": firestore.SERVER_TIMESTAMP,
            "processado_em": None,
            "resultado": None,
            "erro": None,
        }
        doc_ref.set(data)
        return {"status": "enfileirado", "doc_id": doc_id}

    existente = snap.to_dict() or {}
    status = existente.get("status")

    if status == STATUS_PENDENTE:
        update_data = {
            "payload": payload,
            "atualizado_em": firestore.SERVER_TIMESTAMP,
        }
        if acao_id is not None:
            update_data["acao_id"] = acao_id
        if item_atencao_id is not None:
            update_data["item_atencao_id"] = item_atencao_id
        doc_ref.update(update_data)
        return {"status": "atualizado", "doc_id": doc_id}

    return {
        "status": "ignorado",
        "motivo": f"status atual '{status}' nao permite atualizacao",
        "doc_id": doc_id,
    }


def listar_pendentes(db, tipo: str | None = None, limite: int = 20) -> dict:
    """Lista pedidos em status 'pendente', opcionalmente filtrando por tipo.

    Ordena por criado_em crescente (mais antigo primeiro).
    """
    limite_ajustado = max(1, min(int(limite or 20), 50))
    query = db.collection(COLLECTION).where("status", "==", STATUS_PENDENTE)
    if tipo:
        query = query.where("tipo", "==", str(tipo).strip())

    docs = list(query.stream())
    pedidos: list[dict] = []

    for doc in docs:
        d = doc.to_dict() or {}
        pedidos.append({
            "id": doc.id,
            "tipo": d.get("tipo"),
            "status": d.get("status"),
            "payload": d.get("payload") or {},
            "origem": d.get("origem"),
            "item_atencao_id": d.get("item_atencao_id"),
            "acao_id": d.get("acao_id"),
            "criado_em": _to_iso(d.get("criado_em")),
            "atualizado_em": _to_iso(d.get("atualizado_em")),
        })

    def _sort_key(x: dict) -> str:
        return x.get("criado_em") or ""

    pedidos.sort(key=_sort_key)
    return {
        "total": len(pedidos),
        "pedidos": pedidos[:limite_ajustado],
    }


def contar_pendentes(db, tipo: str | None = None) -> int:
    """Contagem rápida de pedidos pendentes para o resumo de estado."""
    query = db.collection(COLLECTION).where("status", "==", STATUS_PENDENTE)
    if tipo:
        query = query.where("tipo", "==", str(tipo).strip())
    return len(list(query.stream()))


def concluir(
    db,
    request_id: str,
    resultado: str | None = None,
    erro: str | None = None,
) -> dict:
    """Conclui ou registra erro em um pedido de trabalho autônomo.

    Exige exatamente um entre resultado e erro.
    É idempotente: se o pedido já estiver terminal, devolve status 'already_decided'
    sem sobrescrever o registro existente.
    """
    request_id = str(request_id or "").strip()
    if not request_id:
        return {"erro": "request_id é obrigatório."}

    tem_res = resultado is not None and str(resultado).strip() != ""
    tem_err = erro is not None and str(erro).strip() != ""

    if (tem_res and tem_err) or (not tem_res and not tem_err):
        return {"erro": "Informe exatamente um entre 'resultado' e 'erro'."}

    doc_ref = db.collection(COLLECTION).document(request_id)
    snap = doc_ref.get()
    if not snap.exists:
        return {"status": "not_found", "erro": f"Pedido '{request_id}' não encontrado."}

    data = snap.to_dict() or {}
    status_atual = data.get("status")

    valido, motivo = validar_transicao(status_atual)
    if not valido:
        return {
            "status": "already_decided",
            "estado_atual": status_atual,
            "erro": f"Pedido {motivo}",
            "dados": data,
        }

    novo_status = STATUS_CONCLUIDO if tem_res else STATUS_ERRO
    update_data = {
        "status": novo_status,
        "processado_em": firestore.SERVER_TIMESTAMP,
        "atualizado_em": firestore.SERVER_TIMESTAMP,
        "resultado": str(resultado).strip() if tem_res else None,
        "erro": str(erro).strip() if tem_err else None,
    }
    doc_ref.update(update_data)
    return {
        "status": "ok",
        "request_id": request_id,
        "novo_status": novo_status,
    }
