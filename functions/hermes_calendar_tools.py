"""Shared Google Calendar utilities for Hermes LLM tools.

All functions accept calendar_service and calendar_id as explicit parameters so
both main.py (web/copiloto) and hermes_core_logic.py (Telegram) can reuse them
without duplicating auth logic.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ_NAME = "America/Sao_Paulo"
WORK_START_HOUR = 8   # 08:00
WORK_END_HOUR = 19    # 19:00
DEFAULT_DURATION_MIN = 30
SEARCH_WINDOW_DAYS = 7
SLOT_STEP_MIN = 15    # granularity for cursor jumps when scanning free slots


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tz_offset_str(tz: ZoneInfo) -> str:
    """Returns the current UTC offset as ±HH:MM (e.g. '-03:00')."""
    total = int(datetime.now(tz).utcoffset().total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    h, m = divmod(total // 60, 60)
    return f"{sign}{h:02d}:{m:02d}"


def _to_local_dt(dt_str: str, tz: ZoneInfo) -> datetime | None:
    if not dt_str or "T" not in dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(tz)
    except (ValueError, TypeError):
        return None


def _hhmm_to_min(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _min_to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ---------------------------------------------------------------------------
# Core: query calendar
# ---------------------------------------------------------------------------

def consultar_eventos(
    calendar_service,
    calendar_id: str,
    data_inicio: str,
    data_fim: str,
) -> list[dict]:
    """Returns a simplified list of events between data_inicio and data_fim (YYYY-MM-DD inclusive).

    Each entry: {titulo, data, inicio (HH:MM|None), fim (HH:MM|None), hermes_id, calendar_event_id}
    """
    tz = ZoneInfo(TZ_NAME)
    offset = _tz_offset_str(tz)
    t_min = f"{data_inicio}T00:00:00{offset}"
    t_max = f"{data_fim}T23:59:59{offset}"

    events: list[dict] = []
    page_token = None
    while True:
        kwargs = dict(
            calendarId=calendar_id,
            timeMin=t_min,
            timeMax=t_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
        )
        if page_token:
            kwargs["pageToken"] = page_token

        result = calendar_service.events().list(**kwargs).execute()

        for ev in result.get("items", []):
            start = ev.get("start", {})
            end = ev.get("end", {})
            start_str = start.get("dateTime") or start.get("date", "")
            end_str = end.get("dateTime") or end.get("date", "")
            start_local = _to_local_dt(start_str, tz)
            end_local = _to_local_dt(end_str, tz)
            hermes_id = (
                (ev.get("extendedProperties") or {})
                .get("private", {})
                .get("hermes_task_id")
            )
            events.append({
                "titulo": ev.get("summary", "(sem título)"),
                "data": start_local.strftime("%Y-%m-%d") if start_local else start_str[:10],
                "inicio": start_local.strftime("%H:%M") if start_local else None,
                "fim": end_local.strftime("%H:%M") if end_local else None,
                "hermes_id": hermes_id,
                "calendar_event_id": ev.get("id"),
            })

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return events


def consultar_eventos_multi(
    calendar_service,
    calendar_ids,
    data_inicio: str,
    data_fim: str,
) -> tuple[list[dict], list[str]]:
    """Eventos de VARIAS agendas, unidos e ordenados. Devolve (eventos, falhas).

    Existe porque consultar uma agenda so era o mesmo que nao consultar. Ate
    28/08/2026 `consultar_agenda` e `encontrar_slot_livre` liam apenas a agenda
    dedicada do Hermes (`...@group.calendar.google.com`), onde estao somente os
    eventos que o proprio Hermes cria. Os compromissos reais do dono vivem na
    `primary`.

    O efeito era pior que uma falha: a semana de 31/08 a 06/09 tinha 35
    compromissos e a consulta devolvia 1 — o unico criado pelo Hermes. Uma
    agenda que responde "vazio" leva a conclusoes opostas as de uma que responde
    "nao sei", e foi assim que uma reuniao existente foi reportada ao dono como
    inexistente.

    As falhas voltam separadas de proposito: quem responde ao usuario precisa
    distinguir "nao ha compromissos" de "nao consegui ver os compromissos".
    Uma agenda que falhe nao derruba a consulta.
    """
    vistos: set = set()
    eventos: list[dict] = []
    falhas: list[str] = []

    for cid in (calendar_ids or []):
        if not cid:
            continue
        try:
            for ev in consultar_eventos(calendar_service, cid, data_inicio, data_fim):
                # Um mesmo compromisso pode estar em mais de uma agenda (convite
                # aceito, agenda compartilhada). A chave e o que o usuario
                # enxerga, nao o id, que difere entre agendas.
                chave = (ev.get("data"), ev.get("inicio"), ev.get("fim"),
                         (ev.get("titulo") or "").strip().lower())
                if chave in vistos:
                    continue
                vistos.add(chave)
                ev["calendar_id"] = cid
                eventos.append(ev)
        except Exception as exc:  # noqa: BLE001
            falhas.append(f"{cid}: {exc}")

    eventos.sort(key=lambda e: (e.get("data") or "", e.get("inicio") or ""))
    return eventos, falhas


def formatar_eventos_para_llm(
    events: list[dict],
    *,
    periodo: tuple[str, str] | None = None,
    agendas: list[str] | None = None,
    falhas: list[str] | None = None,
) -> str:
    """Formata a lista para o LLM, dizendo o que foi de fato consultado.

    O rodape com fonte, intervalo e numero de agendas existe porque "nenhum
    evento" e "nao consegui ler a agenda" levam a decisoes opostas, e ate
    28/08/2026 as duas coisas saiam com o mesmo texto. Sem ele, quem le nao tem
    como saber se o dia esta livre ou se a consulta e que estava cega.
    """
    lines: list[str] = []
    if not events:
        lines.append("Nenhum evento encontrado no período.")
    else:
        lines.append("EVENTOS NA AGENDA:")
    for ev in events:
        inicio = ev["inicio"] or "dia inteiro"
        fim_str = f"–{ev['fim']}" if ev["fim"] else ""
        tag = " [HERMES]" if ev["hermes_id"] else ""
        lines.append(f"• {ev['data']} {inicio}{fim_str} — {ev['titulo']}{tag}")

    rodape: list[str] = []
    if periodo:
        rodape.append(f"período consultado: {periodo[0]} a {periodo[1]}")
    if agendas:
        rodape.append(f"{len(agendas)} agenda(s) do Google consultada(s)")
    if falhas:
        rodape.append(
            f"ATENÇÃO: {len(falhas)} agenda(s) NÃO puderam ser lidas "
            f"({'; '.join(falhas)[:200]}) — a lista acima pode estar incompleta; "
            "não trate como agenda vazia")
    if rodape:
        lines.append("")
        lines.append("(fonte: API do Google Calendar; " + "; ".join(rodape) + ")")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def verificar_conflito(
    calendar_service,
    calendar_id: str,
    data: str,
    h_inicio: str,
    h_fim: str,
) -> list[dict]:
    """Returns events that overlap with the given (data, h_inicio, h_fim) slot."""
    events = consultar_eventos(calendar_service, calendar_id, data, data)
    slot_s = _hhmm_to_min(h_inicio)
    slot_e = _hhmm_to_min(h_fim)
    return [
        ev for ev in events
        if ev["inicio"] and ev["fim"]
        and slot_s < _hhmm_to_min(ev["fim"])
        and slot_e > _hhmm_to_min(ev["inicio"])
    ]


# ---------------------------------------------------------------------------
# Free-slot finder
# ---------------------------------------------------------------------------

def encontrar_proximo_slot(
    calendar_service,
    calendar_id: str,
    a_partir_de: str,
    duracao_min: int = DEFAULT_DURATION_MIN,
) -> dict | None:
    """Finds the first free slot of duracao_min minutes within SEARCH_WINDOW_DAYS from a_partir_de.

    Restricts search to WORK_START_HOUR–WORK_END_HOUR.
    Returns {"data": "YYYY-MM-DD", "horario_inicio": "HH:MM", "horario_fim": "HH:MM"} or None.
    """
    try:
        start_date = date.fromisoformat(a_partir_de)
    except ValueError:
        start_date = date.today()

    end_date = start_date + timedelta(days=SEARCH_WINDOW_DAYS)
    # `calendar_id` aceita uma agenda ou varias. Com uma so, o slot era calculado
    # sobre um calendario que continha apenas eventos do proprio Hermes — quase
    # tudo parecia livre, e a ferramenta propunha trabalho por cima de
    # compromisso real. Era o mais perigoso dos dois defeitos de 28/08/2026.
    ids = [calendar_id] if isinstance(calendar_id, str) else list(calendar_id or [])
    all_events, _falhas = consultar_eventos_multi(
        calendar_service, ids, start_date.isoformat(), end_date.isoformat()
    )

    events_by_date: dict[str, list] = defaultdict(list)
    for ev in all_events:
        if ev["data"] and ev["inicio"] and ev["fim"]:
            events_by_date[ev["data"]].append(ev)

    work_start = WORK_START_HOUR * 60
    work_end = WORK_END_HOUR * 60

    for offset in range(SEARCH_WINDOW_DAYS + 1):
        current_date = (start_date + timedelta(days=offset)).isoformat()
        day_events = sorted(
            events_by_date[current_date],
            key=lambda e: _hhmm_to_min(e["inicio"]),
        )

        cursor = work_start
        while cursor + duracao_min <= work_end:
            slot_s = cursor
            slot_e = cursor + duracao_min
            blocking = next(
                (ev for ev in day_events
                 if slot_s < _hhmm_to_min(ev["fim"]) and slot_e > _hhmm_to_min(ev["inicio"])),
                None,
            )
            if blocking is None:
                return {
                    "data": current_date,
                    "horario_inicio": _min_to_hhmm(slot_s),
                    "horario_fim": _min_to_hhmm(slot_e),
                }
            # Jump cursor past the blocking event, snapped to SLOT_STEP_MIN
            ev_end = _hhmm_to_min(blocking["fim"])
            cursor = ((ev_end + SLOT_STEP_MIN - 1) // SLOT_STEP_MIN) * SLOT_STEP_MIN

    return None


# ---------------------------------------------------------------------------
# Silent rescheduler (Postergação Contínua)
# ---------------------------------------------------------------------------

def reagendar_acoes_hermes(
    db,
    calendar_service,
    calendar_id: str,
    data: str,
    h_inicio: str,
    h_fim: str,
) -> list[str]:
    """Silently pushes any Hermes-owned actions that conflict with (data, h_inicio, h_fim)
    to the next available slot within the valid window.

    Returns the titles of rescheduled actions (for optional logging).
    """
    conflicts = verificar_conflito(calendar_service, calendar_id, data, h_inicio, h_fim)
    hermes_conflicts = [ev for ev in conflicts if ev.get("hermes_id")]

    rescheduled: list[str] = []
    for ev in hermes_conflicts:
        task_id = ev["hermes_id"]
        try:
            next_date = (date.fromisoformat(data) + timedelta(days=1)).isoformat()
        except ValueError:
            continue

        if ev["inicio"] and ev["fim"]:
            dur = _hhmm_to_min(ev["fim"]) - _hhmm_to_min(ev["inicio"])
        else:
            dur = DEFAULT_DURATION_MIN
        dur = max(dur, DEFAULT_DURATION_MIN)

        new_slot = encontrar_proximo_slot(calendar_service, calendar_id, next_date, dur)
        if new_slot:
            db.collection("tarefas").document(task_id).update({
                "data_limite": new_slot["data"],
                "horario_inicio": new_slot["horario_inicio"],
                "horario_fim": new_slot["horario_fim"],
                "sync_status": "new",
                "data_atualizacao": datetime.now(timezone.utc).isoformat(),
            })
            rescheduled.append(ev["titulo"])

    return rescheduled
