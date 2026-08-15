"""Sincronizacao de eventos da Google Agenda com o modulo Saude do Hermes (N1).

Roda diariamente, le os calendarios configurados (primary + o calendario
dedicado do Hermes, via get_sync_calendar_ids), classifica cada evento por
palavra-chave no titulo, e espelha os que baterem para a colecao
health_events com source='calendar' e externalId=<id do evento na agenda>
para dedupe. Nunca cria, edita ou apaga eventos com source='manual' ou
'exam' — so mexe nos que ele mesmo criou.

A janela de sincronizacao e limitada (passado recente + futuro proximo) para
manter o custo baixo e para que a limpeza de marcadores obsoletos (evento
cancelado/apagado na agenda, ou titulo editado para nao bater mais em
nenhuma palavra-chave) nao precise varrer o historico inteiro.
"""

from datetime import datetime, timedelta, timezone

from firebase_functions import scheduler_fn, options

SYNC_WINDOW_PAST_DAYS = 14
SYNC_WINDOW_FUTURE_DAYS = 60

# (palavras-chave, HealthEventType) — checadas em ordem, case-insensitive,
# substring simples no titulo do evento da agenda.
_KEYWORD_TYPE_MAP = [
    (('fisioterapia', 'fisio'), 'fisioterapia'),
    (('pilates', 'acupuntura', 'rpg'), 'modalidade_terapeutica'),
    (
        ('ortoped', 'consulta', 'retorno', 'dr.', 'dra.', 'médic', 'medic',
         'exame', 'ressonânc', 'ressonanc', 'raio-x', 'raio x', 'tomografia', 'ultrassom'),
        'consulta_medica',
    ),
]


def _classify(titulo: str):
    lower = (titulo or '').lower()
    for keywords, tipo in _KEYWORD_TYPE_MAP:
        if any(kw in lower for kw in keywords):
            return tipo
    return None


@scheduler_fn.on_schedule(
    schedule="0 6 * * *",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
)
def sincronizar_eventos_saude_agenda(event: scheduler_fn.ScheduledEvent = None) -> None:
    """Agendada diariamente 6h BRT — espelha eventos de saude da Google Agenda para health_events."""
    from main import get_db, get_calendar_service, get_sync_calendar_ids
    from hermes_calendar_tools import consultar_eventos

    db = get_db()
    hoje = datetime.now(timezone.utc)
    data_inicio = (hoje - timedelta(days=SYNC_WINDOW_PAST_DAYS)).strftime('%Y-%m-%d')
    data_fim = (hoje + timedelta(days=SYNC_WINDOW_FUTURE_DAYS)).strftime('%Y-%m-%d')

    try:
        service = get_calendar_service()
        calendar_ids = get_sync_calendar_ids(db)
        eventos_agenda = []
        for calendar_id in calendar_ids:
            eventos_agenda.extend(consultar_eventos(service, calendar_id, data_inicio, data_fim))
    except Exception as exc:
        print(f"[SaudeCalendarSync] Falha ao ler a Google Agenda: {exc}")
        return

    matched_external_ids = set()
    synced = 0
    for ev in eventos_agenda:
        tipo = _classify(ev.get('titulo', ''))
        external_id = ev.get('calendar_event_id')
        data = ev.get('data')
        if not tipo or not external_id or not data:
            continue
        matched_external_ids.add(external_id)

        payload = {
            'date': data,
            'type': tipo,
            'label': ev.get('titulo', ''),
            'source': 'calendar',
            'externalId': external_id,
        }
        try:
            existing = list(
                db.collection('health_events')
                .where('externalId', '==', external_id)
                .limit(1)
                .stream()
            )
            if existing:
                existing[0].reference.set(payload, merge=True)
            else:
                db.collection('health_events').add(payload)
            synced += 1
        except Exception as exc:
            print(f"[SaudeCalendarSync] Falha ao gravar evento {external_id}: {exc}")

    # Remove marcadores de calendario cujo evento de origem sumiu (cancelado/apagado)
    # ou deixou de bater com uma palavra-chave nesta janela. Nunca toca em
    # source='manual' ou 'exam'.
    removed = 0
    try:
        stale = (
            db.collection('health_events')
            .where('source', '==', 'calendar')
            .where('date', '>=', data_inicio)
            .where('date', '<=', data_fim)
            .stream()
        )
        for doc in stale:
            doc_data = doc.to_dict() or {}
            if doc_data.get('externalId') not in matched_external_ids:
                doc.reference.delete()
                removed += 1
    except Exception as exc:
        print(f"[SaudeCalendarSync] Falha na limpeza de marcadores obsoletos: {exc}")

    print(f"[SaudeCalendarSync] {synced} evento(s) de saude sincronizado(s), {removed} obsoleto(s) removido(s).")
