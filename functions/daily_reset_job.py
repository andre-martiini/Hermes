import datetime
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from firebase_admin import firestore
from firebase_functions import scheduler_fn, options

# Usar um agendador às 3 da manhã para limpar as tarefas
@scheduler_fn.on_schedule(
    schedule="0 3 * * 1-5", # Monday to Friday, 3 AM
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
def daily_wip_reset_and_degradation(event: scheduler_fn.ScheduledEvent):
    from main import get_db, _send_telegram_message_raw
    db = get_db()
    sp_tz = zoneinfo.ZoneInfo("America/Sao_Paulo")
    now_sp = datetime.datetime.now(sp_tz)

    # Calculate yesterday's date string (to avoid timezone bugs in queries, we compare the date string directly)
    yesterday = now_sp - datetime.timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    today_str = now_sp.strftime("%Y-%m-%d")

    print(f"[Daily WIP Reset] Running. Yesterday was {yesterday_str}. Today is {today_str}.")

    # Part 1: Degradation and Return to Backlog
    tasks_ref = db.collection("tarefas")

    # Query tasks that were scheduled for yesterday and are still in progress
    # We query for in-progress tasks first, then filter by date string (to avoid complex index requirements)
    in_progress_tasks = tasks_ref.where(filter=firestore.FieldFilter("status", "==", "em andamento")).get()

    batch = db.batch()
    degraded_count = 0
    critical_count = 0

    for task_doc in in_progress_tasks:
        task_data = task_doc.to_dict()

        # Check if the execution lane is 'avanco' (default is 'avanco' if missing)
        execution_lane = task_data.get("execution_lane", "avanco")
        if execution_lane != "avanco":
            continue

        due_date = task_data.get("data_limite", "")
        start_date = task_data.get("data_inicio", "")

        # If it was scheduled for yesterday (or before)
        if (due_date and due_date <= yesterday_str) or (start_date and start_date <= yesterday_str):
            # Reset dates to empty (returns to backlog)
            batch.update(task_doc.reference, {
                "data_limite": "",
                "data_inicio": "",
                "horario_inicio": None,
                "horario_fim": None,
                "status": "stand-by", # Returning to backlog makes it stand-by
                "degradation_count": firestore.Increment(1)
            })

            degraded_count += 1
            current_degradation = task_data.get("degradation_count", 0) + 1
            if current_degradation >= 3:
                critical_count += 1

    # Part 2: Wait for third-parties (SLA breached)
    waiting_tasks = tasks_ref.where(filter=firestore.FieldFilter("execution_lane", "==", "aguardando_terceiro")).where(filter=firestore.FieldFilter("status", "in", ["em andamento", "stand-by"])).get()
    sla_breach_count = 0

    for task_doc in waiting_tasks:
        task_data = task_doc.to_dict()
        sla_date = task_data.get("data_limite", "")

        if sla_date and sla_date < today_str:
            title = task_data.get("titulo", "")
            if not title.startswith("[COBRAR]"):
                title = f"[COBRAR] {title}"

            batch.update(task_doc.reference, {
                "execution_lane": "avanco",
                "data_limite": "",
                "data_inicio": "",
                "status": "stand-by",
                "titulo": title
            })
            sla_breach_count += 1

    # Commit changes
    if degraded_count > 0 or sla_breach_count > 0:
        batch.commit()
        print(f"[Daily WIP Reset] Committed. {degraded_count} degraded, {sla_breach_count} SLA breaches.")

        # Send Telegram notification
        summary = "🌞 <b>Bom dia! Triagem Matinal:</b>\n\n"
        if degraded_count > 0:
            summary += f"🔄 {degraded_count} tarefa(s) não concluídas voltaram para o Backlog.\n"
            if critical_count > 0:
                summary += f"⚠️ <b>{critical_count} atingiram nível vermelho crítico!</b> Expurgo necessário.\n"

        if sla_breach_count > 0:
            summary += f"📞 {sla_breach_count} tarefa(s) estouraram o SLA de espera e precisam de cobrança.\n"

        summary += "\nAbra o painel e puxe suas tarefas de foco do dia."

        settings_doc = db.collection("system").document("settings").get()
        chat_id = settings_doc.to_dict().get("telegram_admin_chat_id") if settings_doc.exists else None

        if chat_id:
             try:
                 _send_telegram_message_raw(db, chat_id, summary)
             except Exception as e:
                 print(f"[Daily WIP Reset] Failed to send telegram: {e}")
    else:
        print("[Daily WIP Reset] No tasks to reset.")
        # Trigger normal ritual push if needed

    # Part 3: Auto-advance non-completed tasks with past dates to today
    # Runs after Parts 1 & 2 so degraded tasks already have empty dates and are excluded naturally
    active_tasks = tasks_ref.where(
        filter=firestore.FieldFilter("status", "in", ["em andamento", "stand-by"])
    ).get()

    batch3 = db.batch()
    auto_advanced_count = 0

    for task_doc in active_tasks:
        task_data = task_doc.to_dict()
        data_limite = task_data.get("data_limite", "")
        if data_limite and data_limite not in ["-", "0000-00-00"] and data_limite < today_str:
            batch3.update(task_doc.reference, {
                "data_limite": today_str,
                "data_inicio": today_str,
                "auto_data_atualizada": True,
            })
            auto_advanced_count += 1

    if auto_advanced_count > 0:
        batch3.commit()
        print(f"[Daily WIP Reset] Auto-advanced {auto_advanced_count} task(s) to today.")
        if 'summary' in dir():
            summary += f"\n\U0001f501 {auto_advanced_count} tarefa(s) tiveram a data atualizada automaticamente para hoje."