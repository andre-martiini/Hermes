import datetime
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from firebase_functions import scheduler_fn, options

_LIMITE_TELEGRAM = 4096

_DIAS_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


@scheduler_fn.on_schedule(
    schedule="0 5 * * *",  # Todos os dias às 5:00
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
def briefing_matinal_acoes(event: scheduler_fn.ScheduledEvent):
    """Envia via Telegram, todo dia às 5h, um resumo das ações e compromissos do
    dia e do que o Gaspar fez desde as 19h de ontem. A própria execução fica em
    agent_runs, com a confirmação (ou não) do envio."""
    from main import get_db
    from agent_runs import registrar_execucao

    db = get_db()
    sp_tz = zoneinfo.ZoneInfo("America/Sao_Paulo")
    now_sp = datetime.datetime.now(sp_tz)
    today_str = now_sp.strftime("%Y-%m-%d")
    with registrar_execucao(db, "briefing_matinal_acoes", run_id=f"briefing_matinal_acoes:{today_str}") as run:
        _briefing(db, now_sp, run)


def _briefing(db, now_sp, run):
    from main import (
        get_calendar_service,
        get_target_calendar_id,
        _resolve_default_telegram_chat_id,
        _get_telegram_token,
        _send_telegram_message,
    )
    from hermes_calendar_tools import consultar_eventos
    from visao_atividade import secao_atividade

    today_str = now_sp.strftime("%Y-%m-%d")
    dia_semana = _DIAS_SEMANA[now_sp.weekday()]
    data_fmt = now_sp.strftime("%d/%m/%Y")

    print(f"[BriefingMatinal] Gerando resumo para {today_str}.")

    # Sincroniza decisao de investimentos de forma transparente se houver troca no mes
    try:
        import investimentos_sync

        investimentos_sync.sincronizar_decisao_investimentos(db)
    except Exception as exc_sync:
        print(f"[BriefingMatinal] Sincronizacao de investimentos ignorada: {exc_sync}")

    tarefas_hoje = []
    try:
        docs = (
            db.collection("tarefas")
            .where("data_limite", "==", today_str)
            .where("status", "==", "em andamento")
            .get()
        )
        tarefas_hoje = [d.to_dict() for d in docs]
        tarefas_hoje.sort(key=lambda t: t.get("horario_inicio") or "99:99")
    except Exception as exc:
        print(f"[BriefingMatinal] Falha ao buscar tarefas: {exc}")

    eventos_hoje = []
    try:
        service = get_calendar_service()
        calendar_id = get_target_calendar_id(db)
        eventos_hoje = consultar_eventos(service, calendar_id, today_str, today_str)
    except Exception as exc:
        print(f"[BriefingMatinal] Falha ao buscar agenda: {exc}")

    lines = ["☀️ <b>Bom dia, André!</b>", f"Hoje é {dia_semana}, {data_fmt}."]

    if not tarefas_hoje and not eventos_hoje:
        lines.append("\nNenhuma ação ou compromisso programado para hoje. Dia livre!")
    else:
        if tarefas_hoje:
            lines.append("\n🗒️ <b>Ações programadas:</b>")
            for t in tarefas_hoje:
                titulo = t.get("titulo") or "(sem título)"
                horario = t.get("horario_inicio")
                prefixo = f"{horario} — " if horario else ""
                lines.append(f"• {prefixo}{titulo}")

        if eventos_hoje:
            lines.append("\n📅 <b>Compromissos na agenda:</b>")
            for ev in eventos_hoje:
                inicio = ev.get("inicio") or "dia inteiro"
                fim = f"–{ev['fim']}" if ev.get("fim") else ""
                lines.append(f"• {inicio}{fim} — {ev.get('titulo')}")

    fechamento = "\nBom trabalho! 💪" if (tarefas_hoje or eventos_hoje) else ""
    base = "\n".join(lines)
    try:
        secao = secao_atividade(db, now_sp, limite=_LIMITE_TELEGRAM - len(base) - len(fechamento) - 3)
    except Exception as exc:
        print(f"[BriefingMatinal] Seção de atividade indisponível: {exc}")
        run.parcial(f"seção de atividade indisponível: {exc}")
        secao = ""
    message = base + (f"\n\n{secao}" if secao else "") + (f"\n{fechamento}" if fechamento else "")
    run.contar(tarefas=len(tarefas_hoje), eventos=len(eventos_hoje))

    chat_id = _resolve_default_telegram_chat_id(db)
    if not chat_id:
        print("[BriefingMatinal] Nenhum chat_id do Telegram configurado.")
        run.falhou("nenhum chat do Telegram configurado")
        return

    try:
        enviado = _send_telegram_message(_get_telegram_token(db), chat_id, message)
    except Exception as exc:
        print(f"[BriefingMatinal] Falha ao enviar Telegram: {exc}")
        enviado = None
    run.contar(enviado=1 if enviado else 0)
    if enviado:
        run.verificado("verificado")
        run.resumo(f"Briefing enviado: {len(tarefas_hoje)} ações, {len(eventos_hoje)} compromissos")
    else:
        run.verificado("falhou")
        run.falhou("o Telegram não confirmou o envio do briefing")
