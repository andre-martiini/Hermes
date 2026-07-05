import datetime
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from firebase_admin import firestore
from firebase_functions import scheduler_fn, options


def _last_day_of_month(ref: datetime.datetime) -> int:
    next_month = ref.replace(day=1) + datetime.timedelta(days=32)
    return (next_month.replace(day=1) - datetime.timedelta(days=1)).day


@scheduler_fn.on_schedule(
    schedule="10 0 * * *",  # Todo dia à 00:10
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
def gerar_acoes_recorrentes_mensais(event: scheduler_fn.ScheduledEvent):
    from main import get_db
    db = get_db()
    sp_tz = zoneinfo.ZoneInfo("America/Sao_Paulo")
    now_sp = datetime.datetime.now(sp_tz)
    today_str = now_sp.strftime("%Y-%m-%d")
    current_month = now_sp.strftime("%Y-%m")
    last_day = _last_day_of_month(now_sp)

    templates = db.collection("tarefas").where(
        filter=firestore.FieldFilter("recorrencia.ativo", "==", True)
    ).get()

    created_count = 0
    for template_doc in templates:
        template_data = template_doc.to_dict()
        recorrencia = template_data.get("recorrencia") or {}
        dia_do_mes = recorrencia.get("dia_do_mes")
        if not dia_do_mes:
            continue

        # Dias que não existem no mês corrente (ex.: 31 em abril) caem no último dia do mês
        effective_day = min(int(dia_do_mes), last_day)
        if now_sp.day != effective_day:
            continue
        if recorrencia.get("ultima_geracao") == current_month:
            continue

        new_task = {
            "titulo": template_data.get("titulo", ""),
            "projeto": template_data.get("projeto", ""),
            "area_tematica": template_data.get("area_tematica", ""),
            "data_inicio": today_str,
            "data_limite": today_str,
            "status": "em andamento",
            "contabilizar_meta": template_data.get("contabilizar_meta", False),
            "data_criacao": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "acompanhamento": [],
            "entregas_relacionadas": [],
            "origem": template_data.get("origem", "manual"),
        }
        for optional_field in ("tags", "descricao", "tipo_acao", "horario_inicio", "horario_fim"):
            if template_data.get(optional_field):
                new_task[optional_field] = template_data[optional_field]

        db.collection("tarefas").add(new_task)
        template_doc.reference.update({"recorrencia.ultima_geracao": current_month})
        created_count += 1
        print(f"[Recorrência Mensal] Gerada nova instância de '{new_task['titulo']}' a partir do template {template_doc.id}.")

    if created_count == 0:
        print(f"[Recorrência Mensal] Nenhuma ação recorrente para gerar em {today_str}.")
