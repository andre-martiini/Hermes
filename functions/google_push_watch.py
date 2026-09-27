"""Sincronização por webhook do Google Calendar e do Drive (acervo) -- Fatias 2 e 3 da ação
Hermes e7fe01f4 ("Sincronização por Webhook (Gmail/Calendar/Drive)"). A Fatia 1 (Gmail, via
Pub/Sub) está em main.py (`on_gmail_watch_notification`, `renovar_gmail_watch`).

Calendar e Drive entregam push notification por HTTPS direto (canal `web_hook`), sem tópico
Pub/Sub -- nada de infraestrutura nova de GCP (a conta de deploy do CI não cria tópicos). Os dois
caminhos ficam DESLIGADOS por padrão, atrás de flags em `system/settings`:

- `calendar_watch.enabled` (+ `calendar_watch.url`, a URL pública de `on_calendar_push`);
- `drive_watch.enabled` (+ `drive_watch.url`, a URL pública de `on_drive_push`).

Com o flag desligado o endpoint responde 200 sem fazer nada e o renovador não registra canal.

Calendar (`on_calendar_push`): um canal `events.watch()` por agenda lida pelo sync
(`get_sync_calendar_ids`: 'primary' + a agenda do Hermes). A notificação só diz "algo mudou nesta
agenda"; o endpoint então:

1. valida canal + token (segredo aleatório por instalação em `system/calendar_watch.channel_token`,
   comparado com `hmac.compare_digest`) -- qualquer outra coisa recebe 403 sem tocar em API do
   Google;
2. ignora a notificação `sync` (handshake de criação do canal);
3. ignora enquanto `system/sync` estiver `processing`/`requested` -- é o que corta o LOOP: o push
   do próprio sync (`sync_google_tasks_push`) faz `events().update()` em todo evento de ação com
   horário a cada rodada, e cada update gera uma notificação. Sem isto, cada sync pediria outro;
4. lista só o que mudou desde o último cursor (`events.list(updatedMin=...)`) e descarta os ecos
   do próprio Hermes: evento criado pelo Hermes (`hermes_task_id`) cuja agenda não faria a
   sincronia inversa agir (mesma condição de `sync_google_calendar`);
5. sobrando mudança real, pede um sync SÓ DE AGENDA pelo mesmo caminho do `on_tarefa_written`
   (`system/sync.status = 'requested'`, `requested_scope = 'calendar'` -> `on_sync_request`), com
   debounce de 60 s e teto de pedidos por hora. O sync nunca roda dentro do request.

Drive (`on_drive_push`): um canal `files.watch()` na Pasta de Deságue (`drop_folder_id`) -- e não
`changes.watch()`, que notificaria QUALQUER alteração em qualquer arquivo do Drive do André (cada
autosave de um Google Docs). Para pasta, o Drive manda `X-Goog-Changed: children` quando entra ou
sai arquivo; só isso dispara `executar_monitoramento_acervo_global` (debounce de 60 s, lock próprio
`drive_acervo_lock`, compartilhado com o cron de 30 min). O canal de arquivo expira em no máximo
1 dia, por isso o renovador do Drive roda a cada 12 h.

Os crons de sempre continuam como rede de segurança: `scheduled_sync` (60 min) e
`monitorar_acervo_global` (30 min). Mudança que chegar enquanto um sync roda, ou que cair no
debounce, espera no máximo até eles.
"""

from __future__ import annotations

import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from firebase_functions import https_fn, options, scheduler_fn

CALENDAR_WATCH_DOC_ID = 'calendar_watch'
DRIVE_WATCH_DOC_ID = 'drive_watch'
DRIVE_ACERVO_LOCK_DOC_ID = 'drive_acervo_lock'

CALENDAR_PUSH_FUNCTION_NAME = 'on_calendar_push'
DRIVE_PUSH_FUNCTION_NAME = 'on_drive_push'
# Sem set_global_options(region=...) no projeto: as funções HTTPS ficam na região padrão.
FUNCTION_REGION_PADRAO = 'us-central1'

# Calendar: canal de 7 dias, renovado 1x/dia quando faltar menos de 2 dias.
CALENDAR_WATCH_TTL_S = 7 * 24 * 3600
CALENDAR_RENOVAR_ANTES_S = 2 * 24 * 3600
# Drive (files.watch): a API aceita no máximo 1 dia; renovador a cada 12 h, renova com < 14 h.
DRIVE_WATCH_TTL_S = 24 * 3600
DRIVE_RENOVAR_ANTES_S = 14 * 3600

DEBOUNCE_S = 60
# Recuo do cursor do delta do Calendar (relógio do Google x relógio da função).
CALENDAR_MARGEM_DELTA_S = 30
# Sem cursor (canal novo): olha só os últimos 5 min.
CALENDAR_JANELA_INICIAL_S = 5 * 60
CALENDAR_DELTA_MAX_PAGINAS = 4
# Acima disso, não lê tarefa por tarefa: trata como mudança real (na dúvida, sincroniza).
CALENDAR_MAX_EVENTOS_HERMES_CHECADOS = 50
# Disjuntor: no máximo N pedidos de sync por hora vindos do webhook (se o filtro de eco falhar
# de um jeito não previsto, o pior caso fica limitado; o cron de 60 min segue cobrindo).
CALENDAR_MAX_PEDIDOS_POR_HORA = 20

_ESTADOS_SYNC_OCUPADO = ('processing', 'requested')


# ── utilitários ─────────────────────────────────────────────────────────────────────────────

def _get_db():
    from firebase_admin import firestore
    return firestore.client()


def _agora_utc(agora=None) -> datetime:
    return agora or datetime.now(timezone.utc)


def _parse_iso(valor) -> datetime | None:
    """ISO 8601 -> datetime UTC-aware. Sem fuso é tratado como UTC (run_full_sync grava
    `last_success` com datetime.now() ingênuo; a função roda em UTC)."""
    if isinstance(valor, datetime):
        dt = valor
    elif isinstance(valor, str) and valor.strip():
        try:
            dt = datetime.fromisoformat(valor.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _expiracao_dt(valor) -> datetime | None:
    """`expiration` das APIs do Google vem em milissegundos desde a época (string ou int)."""
    try:
        ms = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000.0, timezone.utc)


def _expira_em_breve(expiracao, agora: datetime, antecedencia_s: int) -> bool:
    dt = _expiracao_dt(expiracao)
    return dt is None or (dt - agora).total_seconds() < antecedencia_s


def _headers_normalizados(headers) -> dict:
    """Cabeçalhos com chave minúscula (Flask já é case-insensitive; dict de teste não)."""
    try:
        itens = headers.items()
    except AttributeError:
        return {}
    return {str(k).lower(): (v if isinstance(v, str) else str(v)) for k, v in itens}


def token_confere(esperado, recebido) -> bool:
    """Comparação em tempo constante; vazio/ausente de qualquer lado nunca confere."""
    if not isinstance(esperado, str) or not isinstance(recebido, str):
        return False
    if not esperado or not recebido:
        return False
    return hmac.compare_digest(esperado.encode('utf-8'), recebido.encode('utf-8'))


def _ler_settings(db) -> dict:
    try:
        doc = db.collection('system').document('settings').get()
        return (doc.to_dict() or {}) if doc.exists else {}
    except Exception as exc:
        print(f"[PUSH] Falha ao ler system/settings: {exc}")
        return {}


def _cfg(settings: dict, chave: str) -> dict:
    cfg = (settings or {}).get(chave)
    return cfg if isinstance(cfg, dict) else {}


def calendar_watch_habilitado(settings: dict) -> bool:
    return bool(_cfg(settings, 'calendar_watch').get('enabled', False))


def drive_watch_habilitado(settings: dict) -> bool:
    return bool(_cfg(settings, 'drive_watch').get('enabled', False))


def url_do_endpoint(settings: dict, chave: str, nome_funcao: str) -> tuple[str, str]:
    """URL pública do endpoint: `system/settings.<chave>.url` (preferida -- o André copia do
    console depois do deploy) ou, na falta dela, a URL padrão cloudfunctions.net da região
    padrão. Devolve (url, origem)."""
    url = _cfg(settings, chave).get('url')
    if isinstance(url, str) and url.strip().startswith('https://'):
        return url.strip(), 'settings'
    projeto = os.environ.get('GCLOUD_PROJECT') or 'gestao-hermes'
    return f"https://{FUNCTION_REGION_PADRAO}-{projeto}.cloudfunctions.net/{nome_funcao}", 'derivada'


def _main():
    """main.py só é importado depois da validação do canal (e só no caminho que precisa dele)."""
    import main
    return main


# ── Calendar: filtro de eco ────────────────────────────────────────────────────────────────

def _hermes_task_id(evento: dict) -> str | None:
    privado = ((evento or {}).get('extendedProperties') or {}).get('private') or {}
    valor = privado.get('hermes_task_id')
    return valor if isinstance(valor, str) and valor.strip() else None


def _evento_do_hermes(evento: dict) -> bool:
    """Criado por sync_google_tasks_push: id determinístico `hermes<hex>` e/ou marca
    extendedProperties.private.hermes_task_id."""
    return bool(_hermes_task_id(evento)) or str((evento or {}).get('id') or '').startswith('hermes')


def mudanca_relevante_calendar(evento: dict, tarefa: dict | None, extrair_agenda, is_iso_after) -> bool:
    """True quando o evento alterado pede um sync. Espelha a sincronia inversa de
    sync_google_calendar: evento do Hermes só importa se for mais novo que a tarefa E trouxer
    data/horário diferente -- é exatamente o caso em que o sync mexeria na tarefa. Tudo o mais
    (update do próprio push, evento de ação apagado pelo Hermes) é eco.

    Evento que não é do Hermes (reunião, compromisso) sempre é relevante: alimenta
    google_calendar_events, que a agenda e as tools consultam."""
    if not _evento_do_hermes(evento):
        return True
    if (evento or {}).get('status') == 'cancelled':
        # O push apaga o evento quando a ação é concluída/excluída/perde o horário.
        return False
    if not _hermes_task_id(evento) or tarefa is None:
        # Evento com cara de Hermes mas sem tarefa conhecida: conservador, sincroniza.
        return True
    agenda = extrair_agenda(evento)
    if not agenda:
        return False
    if not is_iso_after(evento.get('updated', ''), tarefa.get('data_atualizacao', '')):
        return False
    local_data = tarefa.get('data_limite') or tarefa.get('data_inicio')
    return (
        local_data != agenda.get('data_limite')
        or tarefa.get('horario_inicio') != agenda.get('horario_inicio')
        or tarefa.get('horario_fim') != agenda.get('horario_fim')
    )


def _delta_calendar(cs, calendar_id: str, desde: datetime) -> list | None:
    """Eventos da agenda alterados (inclusive apagados) desde `desde`. None quando não dá para
    calcular (erro da API, mudança demais) -- o chamador trata como mudança real."""
    try:
        itens: list = []
        page_token = None
        for _ in range(CALENDAR_DELTA_MAX_PAGINAS):
            kwargs = {
                'calendarId': calendar_id,
                'updatedMin': _rfc3339(desde),
                'showDeleted': True,
                'maxResults': 250,
                'fields': 'nextPageToken,items(id,status,updated,start,end,extendedProperties)',
            }
            if page_token:
                kwargs['pageToken'] = page_token
            resposta = cs.events().list(**kwargs).execute()
            itens.extend(resposta.get('items') or [])
            page_token = resposta.get('nextPageToken')
            if not page_token:
                return itens
        return None
    except Exception as exc:
        print(f"[CAL-PUSH] events.list do delta falhou ({calendar_id}): {exc}")
        return None


def _ha_mudanca_real(db, eventos: list, extrair_agenda, is_iso_after) -> bool:
    ids_tarefa = []
    for ev in eventos:
        if not _evento_do_hermes(ev):
            return True
        tid = _hermes_task_id(ev)
        if tid and ev.get('status') != 'cancelled':
            ids_tarefa.append(tid)
    if len(set(ids_tarefa)) > CALENDAR_MAX_EVENTOS_HERMES_CHECADOS:
        return True
    tarefas: dict = {}
    for tid in set(ids_tarefa):
        try:
            snap = db.collection('tarefas').document(tid).get()
            tarefas[tid] = (snap.to_dict() or {}) if snap.exists else None
        except Exception as exc:
            print(f"[CAL-PUSH] Falha ao ler tarefa {tid}: {exc}")
            return True
    return any(
        mudanca_relevante_calendar(ev, tarefas.get(_hermes_task_id(ev) or ''), extrair_agenda, is_iso_after)
        for ev in eventos
    )


def pedir_sync_agenda(db, watch_ref, watch_data: dict, agora: datetime) -> str:
    """Pede um sync só de agenda (mesmo contrato de _pedir_sync_por_mudanca_de_agenda em
    main.py: `on_sync_request` atende `status='requested'` + `requested_scope='calendar'`).
    Devolve 'solicitado', 'sync_em_andamento', 'debounce' ou 'limite_por_hora'."""
    sync_ref = db.collection('system').document('sync')
    sync_data = sync_ref.get().to_dict() or {}
    if sync_data.get('status') in _ESTADOS_SYNC_OCUPADO:
        return 'sync_em_andamento'

    ultimo = _parse_iso(watch_data.get('ultimo_pedido_sync_em'))
    if ultimo and (agora - ultimo).total_seconds() < DEBOUNCE_S:
        return 'debounce'

    inicio_janela = _parse_iso(watch_data.get('pedidos_janela_inicio'))
    pedidos = int(watch_data.get('pedidos_na_janela') or 0)
    if not inicio_janela or (agora - inicio_janela).total_seconds() >= 3600:
        inicio_janela, pedidos = agora, 0
    if pedidos >= CALENDAR_MAX_PEDIDOS_POR_HORA:
        print(f"[CAL-PUSH] Teto de {CALENDAR_MAX_PEDIDOS_POR_HORA} pedidos de sync/hora atingido; fica para o cron.")
        return 'limite_por_hora'

    sync_ref.set({
        'status': 'requested',
        'requested_scope': 'calendar',
        'requested_at': _iso(agora),
        'last_trigger': 'calendar-push',
    }, merge=True)
    watch_ref.set({
        'ultimo_pedido_sync_em': _iso(agora),
        'pedidos_janela_inicio': _iso(inicio_janela),
        'pedidos_na_janela': pedidos + 1,
    }, merge=True)
    return 'solicitado'


def processar_notificacao_calendar(db, headers, *, agora=None, calendar_service_factory=None,
                                   extrair_agenda=None, is_iso_after=None) -> tuple[int, dict]:
    """Núcleo de on_calendar_push, sem Flask. Devolve (status_http, detalhe)."""
    agora = _agora_utc(agora)
    h = _headers_normalizados(headers)
    settings = _ler_settings(db)
    if not calendar_watch_habilitado(settings):
        return 200, {'motivo': 'desligado'}

    channel_id = h.get('x-goog-channel-id', '')
    token = h.get('x-goog-channel-token', '')
    if not channel_id or not token:
        return 403, {'motivo': 'sem_credencial'}
    watch_ref = db.collection('system').document(CALENDAR_WATCH_DOC_ID)
    try:
        watch_doc = watch_ref.get()
        watch_data = (watch_doc.to_dict() or {}) if watch_doc.exists else {}
    except Exception as exc:
        print(f"[CAL-PUSH] Falha ao ler system/{CALENDAR_WATCH_DOC_ID}: {exc}")
        return 500, {'motivo': 'erro_leitura'}
    canal = (watch_data.get('canais') or {}).get(channel_id)
    if not isinstance(canal, dict) or not token_confere(watch_data.get('channel_token'), token):
        return 403, {'motivo': 'canal_ou_token_invalido'}
    resource_id = h.get('x-goog-resource-id', '')
    if resource_id and canal.get('resource_id') and resource_id != canal.get('resource_id'):
        return 403, {'motivo': 'resource_id_invalido'}

    estado = h.get('x-goog-resource-state', '')
    if estado == 'sync':
        return 200, {'motivo': 'sync_ignorado'}

    try:
        sync_data = db.collection('system').document('sync').get().to_dict() or {}
    except Exception as exc:
        print(f"[CAL-PUSH] Falha ao ler system/sync: {exc}")
        sync_data = {}
    if sync_data.get('status') in _ESTADOS_SYNC_OCUPADO:
        # O sync que está rodando/pendente já vai ler a agenda; e as notificações que chegam
        # agora são, na maioria, eco do próprio push dele.
        return 200, {'motivo': 'sync_em_andamento'}

    # Janela do delta: do cursor do canal (recuado pela margem) ou do fim do último sync, o que
    # for mais recente -- o que mudou antes disso o sync já leu (ou foi eco do push dele).
    candidatos = []
    cursor = _parse_iso(canal.get('ultimo_delta_em'))
    if cursor:
        candidatos.append(cursor - timedelta(seconds=CALENDAR_MARGEM_DELTA_S))
    fim_sync = _parse_iso(sync_data.get('last_success'))
    if fim_sync:
        candidatos.append(fim_sync)
    desde = max(candidatos) if candidatos else agora - timedelta(seconds=CALENDAR_JANELA_INICIAL_S)

    relevante = True
    try:
        m = None
        if calendar_service_factory is None or extrair_agenda is None or is_iso_after is None:
            m = _main()
        cs = (calendar_service_factory or m.get_calendar_service)()
        eventos = _delta_calendar(cs, canal.get('calendar_id') or 'primary', desde)
        if eventos is not None:
            relevante = _ha_mudanca_real(
                db, eventos,
                extrair_agenda or m.extract_schedule_from_calendar_event,
                is_iso_after or m.is_iso_after,
            )
    except Exception as exc:
        print(f"[CAL-PUSH] Delta indisponível ({exc}); tratando como mudança real.")
        relevante = True

    if not relevante:
        _avancar_cursor_calendar(watch_ref, channel_id, agora)
        return 200, {'motivo': 'eco'}

    resultado = pedir_sync_agenda(db, watch_ref, watch_data, agora)
    if resultado == 'solicitado':
        _avancar_cursor_calendar(watch_ref, channel_id, agora)
    return 200, {'motivo': resultado}


def _avancar_cursor_calendar(watch_ref, channel_id: str, agora: datetime) -> None:
    try:
        watch_ref.update({f'canais.{channel_id}.ultimo_delta_em': _iso(agora),
                          'last_notification_at': _iso(agora)})
    except Exception as exc:
        print(f"[CAL-PUSH] Falha ao avançar cursor do canal {channel_id}: {exc}")


# ── Calendar: registro/renovação ───────────────────────────────────────────────────────────

def renovar_calendar_watch(db, service, *, agora=None, calendar_ids=None, forcar=False) -> dict:
    """Registra/renova um canal events.watch() por agenda sincronizada. Só age se faltar canal,
    a URL/lista de agendas mudou ou algum canal expira em menos de CALENDAR_RENOVAR_ANTES_S.
    Cria o canal novo antes de parar o antigo (channels.stop); agenda cuja renovação falhar
    mantém o canal antigo. Sem efeito com system/settings.calendar_watch.enabled desligado."""
    agora = _agora_utc(agora)
    settings = _ler_settings(db)
    if not calendar_watch_habilitado(settings):
        return {'habilitado': False, 'renovado': False}

    watch_ref = db.collection('system').document(CALENDAR_WATCH_DOC_ID)
    try:
        doc = watch_ref.get()
        data = (doc.to_dict() or {}) if doc.exists else {}
        if calendar_ids is None:
            calendar_ids = _main().get_sync_calendar_ids(db)
    except Exception as exc:
        print(f"[CAL-WATCH] Falha ao preparar renovação: {exc}")
        return {'habilitado': True, 'renovado': False, 'erro': str(exc)}

    url, origem = url_do_endpoint(settings, 'calendar_watch', CALENDAR_PUSH_FUNCTION_NAME)
    canais_atuais = {cid: c for cid, c in (data.get('canais') or {}).items() if isinstance(c, dict)}
    por_agenda = {c.get('calendar_id'): (cid, c) for cid, c in canais_atuais.items()}

    precisa = (
        forcar
        or url != data.get('url')
        or set(calendar_ids) != set(por_agenda)
        or any(_expira_em_breve(c.get('expiration'), agora, CALENDAR_RENOVAR_ANTES_S) for c in canais_atuais.values())
    )
    if not precisa:
        return {'habilitado': True, 'renovado': False, 'motivo': 'em_dia'}

    token = data.get('channel_token') or secrets.token_urlsafe(32)
    novos: dict = {}
    parar: list = []
    erros: dict = {}
    for calendar_id in calendar_ids:
        anterior = por_agenda.get(calendar_id)
        channel_id = uuid.uuid4().hex
        try:
            resposta = service.events().watch(calendarId=calendar_id, body={
                'id': channel_id,
                'type': 'web_hook',
                'address': url,
                'token': token,
                'params': {'ttl': str(CALENDAR_WATCH_TTL_S)},
            }).execute()
            novos[channel_id] = {
                'calendar_id': calendar_id,
                'resource_id': resposta.get('resourceId'),
                'expiration': str(resposta.get('expiration') or ''),
                'criado_em': _iso(agora),
                'ultimo_delta_em': (anterior[1].get('ultimo_delta_em') if anterior else None) or _iso(agora),
            }
            if anterior:
                parar.append(anterior)
        except Exception as exc:
            erros[calendar_id] = str(exc)
            print(f"[CAL-WATCH] Falha ao registrar canal da agenda {calendar_id}: {exc}")
            if anterior:
                novos[anterior[0]] = anterior[1]
    for calendar_id, anterior in por_agenda.items():
        if calendar_id not in calendar_ids:
            parar.append(anterior)

    try:
        watch_ref.set({
            'channel_token': token,
            'url': url,
            'url_origem': origem,
            'watch_active': bool(novos),
            'last_renewed_at': _iso(agora),
            'erros': erros,
        }, merge=True)
        # update (e não set com merge) para SUBSTITUIR o mapa: canal parado não pode sobrar.
        watch_ref.update({'canais': novos})
    except Exception as exc:
        print(f"[CAL-WATCH] Falha ao gravar canais: {exc}")
        return {'habilitado': True, 'renovado': False, 'erro': str(exc)}

    parados = _parar_canais(service, parar, '[CAL-WATCH]')
    return {'habilitado': True, 'renovado': bool(set(novos) - set(canais_atuais)),
            'canais': len(novos), 'parados': parados, 'erros': erros}


def _parar_canais(service, canais: list, prefixo: str) -> int:
    parados = 0
    for channel_id, canal in canais:
        try:
            service.channels().stop(body={'id': channel_id, 'resourceId': canal.get('resource_id')}).execute()
            parados += 1
        except Exception as exc:
            # Canal já expirado/parado: 404 é normal. Ele expira sozinho de qualquer jeito.
            print(f"{prefixo} channels.stop de {channel_id} falhou (ignorado): {exc}")
    return parados


# ── Drive: registro/renovação e notificação ────────────────────────────────────────────────

def renovar_drive_watch(db, service, *, agora=None, forcar=False) -> dict:
    """Registra/renova o canal files.watch() da Pasta de Deságue (system/settings.drop_folder_id).
    Sem efeito com system/settings.drive_watch.enabled desligado."""
    agora = _agora_utc(agora)
    settings = _ler_settings(db)
    if not drive_watch_habilitado(settings):
        return {'habilitado': False, 'renovado': False}
    folder_id = settings.get('drop_folder_id') or ''
    if not folder_id:
        return {'habilitado': True, 'renovado': False, 'erro': 'drop_folder_id não configurado'}

    watch_ref = db.collection('system').document(DRIVE_WATCH_DOC_ID)
    try:
        doc = watch_ref.get()
        data = (doc.to_dict() or {}) if doc.exists else {}
    except Exception as exc:
        return {'habilitado': True, 'renovado': False, 'erro': str(exc)}

    url, origem = url_do_endpoint(settings, 'drive_watch', DRIVE_PUSH_FUNCTION_NAME)
    precisa = (
        forcar
        or not data.get('channel_id')
        or url != data.get('url')
        or folder_id != data.get('folder_id')
        or _expira_em_breve(data.get('expiration'), agora, DRIVE_RENOVAR_ANTES_S)
    )
    if not precisa:
        return {'habilitado': True, 'renovado': False, 'motivo': 'em_dia'}

    token = data.get('channel_token') or secrets.token_urlsafe(32)
    channel_id = uuid.uuid4().hex
    expiracao_ms = int((agora + timedelta(seconds=DRIVE_WATCH_TTL_S)).timestamp() * 1000)
    try:
        resposta = service.files().watch(fileId=folder_id, supportsAllDrives=True, body={
            'id': channel_id,
            'type': 'web_hook',
            'address': url,
            'token': token,
            'expiration': expiracao_ms,
        }).execute()
    except Exception as exc:
        print(f"[DRIVE-WATCH] Falha ao registrar canal: {exc}")
        try:
            watch_ref.set({'last_erro': str(exc), 'last_erro_em': _iso(agora)}, merge=True)
        except Exception:
            pass
        return {'habilitado': True, 'renovado': False, 'erro': str(exc)}

    anterior = (data.get('channel_id'), {'resource_id': data.get('resource_id')}) if data.get('channel_id') else None
    try:
        watch_ref.set({
            'channel_token': token,
            'channel_id': channel_id,
            'resource_id': resposta.get('resourceId'),
            'expiration': str(resposta.get('expiration') or expiracao_ms),
            'folder_id': folder_id,
            'url': url,
            'url_origem': origem,
            'watch_active': True,
            'last_renewed_at': _iso(agora),
            'last_erro': None,
        }, merge=True)
    except Exception as exc:
        print(f"[DRIVE-WATCH] Falha ao gravar canal: {exc}")
        return {'habilitado': True, 'renovado': False, 'erro': str(exc)}
    parados = _parar_canais(service, [anterior], '[DRIVE-WATCH]') if anterior else 0
    return {'habilitado': True, 'renovado': True, 'parados': parados, 'expiration': resposta.get('expiration')}


def executar_monitoramento_acervo_com_lock(db, trigger: str, executar=None) -> dict:
    """executar_monitoramento_acervo_global sob o lock `drive_acervo_lock`: webhook e cron nunca
    varrem a pasta ao mesmo tempo (os dois veriam o mesmo arquivo novo como inédito e criariam
    dois registros em acervo_global, com indexação em dobro)."""
    m = _main()
    run_id = uuid.uuid4().hex
    if not m.acquire_sync_lock(db, run_id, lock_doc_id=DRIVE_ACERVO_LOCK_DOC_ID):
        print(f"[ACERVO] Varredura já em andamento; rodada ({trigger}) coberta por ela.")
        return {'executado': False, 'motivo': 'lock_ocupado'}
    try:
        if executar is None:
            from knowledge_graph import executar_monitoramento_acervo_global as executar
        resultado = executar()
        return {'executado': True, 'resultado': resultado}
    finally:
        m.release_sync_lock(db, run_id, lock_doc_id=DRIVE_ACERVO_LOCK_DOC_ID)


def processar_notificacao_drive(db, headers, *, agora=None, executar=None) -> tuple[int, dict]:
    """Núcleo de on_drive_push, sem Flask. Devolve (status_http, detalhe)."""
    agora = _agora_utc(agora)
    h = _headers_normalizados(headers)
    settings = _ler_settings(db)
    if not drive_watch_habilitado(settings):
        return 200, {'motivo': 'desligado'}

    channel_id = h.get('x-goog-channel-id', '')
    token = h.get('x-goog-channel-token', '')
    if not channel_id or not token:
        return 403, {'motivo': 'sem_credencial'}
    watch_ref = db.collection('system').document(DRIVE_WATCH_DOC_ID)
    try:
        doc = watch_ref.get()
        data = (doc.to_dict() or {}) if doc.exists else {}
    except Exception as exc:
        print(f"[DRIVE-PUSH] Falha ao ler system/{DRIVE_WATCH_DOC_ID}: {exc}")
        return 500, {'motivo': 'erro_leitura'}
    if not token_confere(data.get('channel_id'), channel_id) or not token_confere(data.get('channel_token'), token):
        return 403, {'motivo': 'canal_ou_token_invalido'}
    resource_id = h.get('x-goog-resource-id', '')
    if resource_id and data.get('resource_id') and resource_id != data.get('resource_id'):
        return 403, {'motivo': 'resource_id_invalido'}

    estado = h.get('x-goog-resource-state', '')
    if estado == 'sync':
        return 200, {'motivo': 'sync_ignorado'}
    mudou = [p.strip() for p in h.get('x-goog-changed', '').split(',') if p.strip()]
    if mudou and 'children' not in mudou:
        # Renomear a pasta, mudar permissão etc.: nada a varrer.
        return 200, {'motivo': 'sem_arquivo_novo'}

    ultima = _parse_iso(data.get('ultima_varredura_em'))
    if ultima and (agora - ultima).total_seconds() < DEBOUNCE_S:
        return 200, {'motivo': 'debounce'}

    try:
        watch_ref.set({'ultima_varredura_em': _iso(agora), 'last_notification_at': _iso(agora)}, merge=True)
        resultado = executar_monitoramento_acervo_com_lock(db, 'webhook', executar=executar)
    except Exception as exc:
        # Nunca devolve 5xx por erro da varredura: o Google reenviaria a notificação em
        # backoff e o cron de 30 min cobre de qualquer jeito.
        print(f"[DRIVE-PUSH] Varredura falhou: {exc}")
        try:
            watch_ref.set({'last_erro': str(exc), 'last_erro_em': _iso(agora)}, merge=True)
        except Exception:
            pass
        return 200, {'motivo': 'erro', 'erro': str(exc)}
    try:
        watch_ref.set({'ultimo_resultado': resultado.get('resultado') or resultado}, merge=True)
    except Exception:
        pass
    return 200, {'motivo': 'executado' if resultado.get('executado') else resultado.get('motivo')}


# ── Cloud Functions ────────────────────────────────────────────────────────────────────────

def _resposta(status: int, detalhe: dict):
    return https_fn.Response(str(detalhe.get('motivo') or ''), status=status)


@https_fn.on_request(timeout_sec=60, memory=options.MemoryOption.MB_256)
def on_calendar_push(req: https_fn.Request) -> https_fn.Response:
    """Receptor das push notifications do Google Calendar (ver docstring do módulo)."""
    if req.method != 'POST':
        return https_fn.Response('Method Not Allowed', status=405)
    try:
        status, detalhe = processar_notificacao_calendar(_get_db(), req.headers)
    except Exception as exc:
        # 200 de propósito: 5xx faz o Google reenviar em backoff; o cron cobre a mudança.
        print(f"[CAL-PUSH] Erro inesperado: {exc}")
        status, detalhe = 200, {'motivo': 'erro'}
    if status != 200:
        print(f"[CAL-PUSH] Notificação recusada ({status}): {detalhe.get('motivo')}")
    return _resposta(status, detalhe)


@https_fn.on_request(timeout_sec=300, memory=options.MemoryOption.MB_512)
def on_drive_push(req: https_fn.Request) -> https_fn.Response:
    """Receptor das push notifications do Drive para a Pasta de Deságue."""
    if req.method != 'POST':
        return https_fn.Response('Method Not Allowed', status=405)
    try:
        status, detalhe = processar_notificacao_drive(_get_db(), req.headers)
    except Exception as exc:
        print(f"[DRIVE-PUSH] Erro inesperado: {exc}")
        status, detalhe = 200, {'motivo': 'erro'}
    if status != 200:
        print(f"[DRIVE-PUSH] Notificação recusada ({status}): {detalhe.get('motivo')}")
    return _resposta(status, detalhe)


@scheduler_fn.on_schedule(schedule="every 24 hours", timeout_sec=120, memory=options.MemoryOption.MB_256)
def renovar_calendar_watch_diario(event: scheduler_fn.ScheduledEvent) -> None:
    """Renova os canais do Calendar quando faltar menos de 2 dias para expirarem. Sem efeito
    enquanto system/settings.calendar_watch.enabled for False (nem monta credencial)."""
    db = _get_db()
    if not calendar_watch_habilitado(_ler_settings(db)):
        return
    m = _main()
    try:
        cs = m.get_calendar_service()
    except Exception as exc:
        print(f"[CAL-WATCH] {m._mensagem_erro_sync(db, exc)}")
        return
    print(f"[CAL-WATCH] {renovar_calendar_watch(db, cs)}")


@scheduler_fn.on_schedule(schedule="every 12 hours", timeout_sec=120, memory=options.MemoryOption.MB_256)
def renovar_drive_watch_periodico(event: scheduler_fn.ScheduledEvent) -> None:
    """Renova o canal do Drive (dura no máximo 1 dia). Sem efeito enquanto
    system/settings.drive_watch.enabled for False."""
    db = _get_db()
    if not drive_watch_habilitado(_ler_settings(db)):
        return
    m = _main()
    try:
        ds = m.get_drive_service()
    except Exception as exc:
        print(f"[DRIVE-WATCH] {m._mensagem_erro_sync(db, exc)}")
        return
    print(f"[DRIVE-WATCH] {renovar_drive_watch(db, ds)}")
