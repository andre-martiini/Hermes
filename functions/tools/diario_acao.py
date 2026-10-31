"""Excluir uma entrada do diario de bordo de uma acao (`tarefas/{id}.acompanhamento`).

Ate 28/10/2026 so havia `registrar_no_diario` (ArrayUnion): entrada errada so se anulava
por nota complementar. A entrada e achada pelo `data` exato que `obter_acao` devolve
(ISO UTC com microssegundos). Antes de remover, a copia vai para a subcolecao
`diario_removido` da propria acao, que serve de auditoria e permite recuperar.
"""
from __future__ import annotations

from datetime import datetime, timezone

from firebase_admin import firestore


def excluir_entrada(db, task_id, data) -> dict:
    task_id, data = str(task_id or "").strip(), str(data or "").strip()
    if not task_id or not data:
        return {"erro": "Informe task_id e data (o campo `data` da entrada, como em obter_acao)."}
    ref = db.collection("tarefas").document(task_id)
    snap = ref.get()
    if not snap.exists:
        return {"erro": f"Tarefa '{task_id}' não encontrada."}
    entrada = next((e for e in (snap.to_dict() or {}).get("acompanhamento") or []
                    if isinstance(e, dict) and e.get("data") == data), None)
    if entrada is None:
        return {"erro": f"Nenhuma entrada com data '{data}' no diário de {task_id}."}
    ref.collection("diario_removido").add(
        {"entrada": entrada, "removida_em": datetime.now(timezone.utc).isoformat()})
    ref.update({"acompanhamento": firestore.ArrayRemove([entrada])})
    return {"status": "excluida", "task_id": task_id, "data": data,
            "nota": str(entrada.get("nota") or "")[:200], "reversivel": True}
