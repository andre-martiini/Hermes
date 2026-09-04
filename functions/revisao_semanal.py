"""Revisão semanal de ações atrasadas — propõe reagendamento em lote distribuído
por dias úteis com aprovação humana em 1 toque via Telegram.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from firebase_admin import firestore
from firebase_functions import scheduler_fn, options

_TZ_SP = zoneinfo.ZoneInfo("America/Sao_Paulo")
COLLECTION_PROPOSTAS = "reagendamentos_propostos"


def eh_tarefa_atrasada(tarefa: dict, hoje_str: str) -> bool:
    """Verifica se a ação está ativa/stand-by e com data_limite ou prazo_final anterior a hoje."""
    if not isinstance(tarefa, dict):
        return False
    status = str(tarefa.get("status") or "").strip().lower()
    if status not in ("em andamento", "stand-by"):
        return False

    data_limite = str(tarefa.get("data_limite") or "").strip()
    prazo_final = str(tarefa.get("prazo_final") or "").strip()
    alvo = data_limite or prazo_final
    if not alvo or len(alvo) < 10:
        return False

    return alvo[:10] < hoje_str


def propor_reagendamento_semanal(db, now: datetime | None = None) -> dict:
    """Varre tarefas atrasadas e gera proposta de reagendamento em lote para aprovação no Telegram."""
    from tools.hermes_tools import ToolContext, preparar_reagendamento_em_lote
    from main import _resolve_default_telegram_chat_id, _send_telegram_message_raw_with_keyboard

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=_TZ_SP)

    now_sp = now.astimezone(_TZ_SP)
    today_str = now_sp.strftime("%Y-%m-%d")

    # 1. Trava de proposta única em aberto
    pendentes_stream = (
        db.collection(COLLECTION_PROPOSTAS)
        .where("status", "==", "pending")
        .limit(1)
        .stream()
    )
    pendentes = list(pendentes_stream)
    if pendentes:
        doc_id = getattr(pendentes[0], "id", "pendente")
        print(f"[RevisaoSemanal] Proposta pendente ja existente ({doc_id}); pulando nova proposta.")
        return {"status": "pulado_ja_existe_pendente", "proposta_id": doc_id}

    # 2. Consulta tarefas ativas/stand-by com data_limite ou prazo_final anterior a hoje
    candidatas_ids = []
    try:
        for doc in db.collection("tarefas").stream():
            d = doc.to_dict() or {}
            if eh_tarefa_atrasada(d, today_str):
                candidatas_ids.append(doc.id)
    except Exception as exc:
        print(f"[RevisaoSemanal] Falha ao consultar tarefas atrasadas: {exc}")
        return {"status": "erro", "erro": str(exc)}

    # 3. Silêncio é o resultado padrão correto quando não há atrasadas
    if not candidatas_ids:
        print("[RevisaoSemanal] Nenhuma ação atrasada encontrada; silêncio é o padrão.")
        return {"status": "nenhuma_candidata", "candidatas": 0}

    # 4. Chama preparar_reagendamento_em_lote com defaults da função
    ctx = ToolContext(_db=db, user_uid=None)
    args = {
        "task_ids": candidatas_ids,
        "nova_data_inicio": today_str,
        "estrategia": "data_criacao",
        "max_por_semana": 5,
        "justificativa": f"Revisão semanal: redistribuição de ações atrasadas a partir de {today_str}.",
    }

    try:
        res_raw = preparar_reagendamento_em_lote(ctx, args)
        if isinstance(res_raw, str) and res_raw.startswith("ERRO|"):
            print(f"[RevisaoSemanal] Falha ao preparar reagendamento em lote: {res_raw}")
            return {"status": "erro_preparacao", "erro": res_raw}

        dados_proposta = json.loads(res_raw) if isinstance(res_raw, str) else res_raw
        items = dados_proposta.get("items") or []
        if not items:
            print("[RevisaoSemanal] Preparação retornou lista vazia de items.")
            return {"status": "sem_items", "candidatas": len(candidatas_ids)}
    except Exception as exc:
        print(f"[RevisaoSemanal] Exceção ao preparar reagendamento: {exc}")
        return {"status": "erro_preparacao", "erro": str(exc)}

    # 5. Grava a proposta em reagendamentos_propostos/{id}
    try:
        doc_ref = db.collection(COLLECTION_PROPOSTAS).document()
        payload_proposta = {
            "items": items,
            "justificativa": dados_proposta.get("justificativa"),
            "status": "pending",
            "criado_em": firestore.SERVER_TIMESTAMP,
            "total_acoes": len(items),
            "nova_data_inicio": today_str,
        }
        doc_ref.set(payload_proposta)
        proposta_id = doc_ref.id
    except Exception as exc:
        print(f"[RevisaoSemanal] Falha ao persistir proposta de reagendamento: {exc}")
        return {"status": "erro_persistencia", "erro": str(exc)}

    # 6. Envia UMA mensagem no Telegram resumindo e com botões inline
    chat_id = _resolve_default_telegram_chat_id(db)
    if not chat_id:
        print(f"[RevisaoSemanal] Nenhum telegram chat_id configurado; proposta {proposta_id} gravada mas não notificada.")
        return {"status": "ok", "proposta_id": proposta_id, "telegram_sent": False}

    total_acoes = len(items)
    amostra = "\n".join(f"• {it.get('titulo', 'Sem título')}" for it in items[:3])
    if total_acoes > 3:
        amostra += f"\n• ... e mais {total_acoes - 3} ação(ões)"

    text = (
        f"📅 Revisão Semanal — Reagendamento em Lote Proposto\n\n"
        f"Identifiquei {total_acoes} ação(ões) com prazo vencido para redistribuição na semana de {today_str}:\n\n"
        f"{amostra}\n\n"
        f"Deseja aplicar a redistribuição sugerida nos próximos dias úteis?"
    )

    keyboard = [[
        {"text": "✅ Aplicar tudo", "callback_data": f"reagendamento_lote:{proposta_id}:aplicar"},
        {"text": "❌ Descartar", "callback_data": f"reagendamento_lote:{proposta_id}:descartar"},
    ]]

    sent = False
    try:
        sent = _send_telegram_message_raw_with_keyboard(db, chat_id, text, keyboard)
    except Exception as exc:
        print(f"[RevisaoSemanal] Falha ao enviar notificação Telegram: {exc}")

    return {
        "status": "ok",
        "proposta_id": proposta_id,
        "total_acoes": total_acoes,
        "telegram_sent": bool(sent),
    }


@scheduler_fn.on_schedule(
    schedule="15 5 * * 1",  # Toda segunda-feira às 5:15
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=180,
)
def revisar_semana_propor_reagendamento(event: scheduler_fn.ScheduledEvent):
    """Executa a revisão semanal e propõe reagendamento em lote das ações atrasadas."""
    from main import get_db

    db = get_db()
    propor_reagendamento_semanal(db)
