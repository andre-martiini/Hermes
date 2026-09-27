"""Testes das Fatias 2 (Calendar) e 3 (Drive/acervo) da sincronização por webhook
(google_push_watch.py, ação Hermes e7fe01f4). Tudo com fakes: Firestore em memória e serviços do
Google falsos -- nenhuma credencial real."""

from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import google_push_watch as gpw

AGORA = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def create(self, data):
        if self._key in self._store:
            raise RuntimeError("already exists")
        self._store[self._key] = dict(data)

    def get(self, transaction=None):
        self._store.setdefault('__leituras__', []).append(self._key)
        return _Snap(self._store.get(self._key))

    def set(self, data, merge=False):
        if merge and self._key in self._store:
            self._store[self._key].update(data)
        else:
            self._store[self._key] = dict(data)

    def update(self, data):
        doc = self._store.setdefault(self._key, {})
        for caminho, valor in data.items():
            partes = caminho.split('.')
            alvo = doc
            for p in partes[:-1]:
                alvo = alvo.setdefault(p, {})
            alvo[partes[-1]] = valor

    def delete(self):
        self._store.pop(self._key, None)


class _Collection:
    def __init__(self, store):
        self._store = store

    def document(self, key):
        return _DocRef(self._store, key)


class _Db:
    def __init__(self):
        self.dados: dict[str, dict] = {}

    def collection(self, name):
        return _Collection(self.dados.setdefault(name, {}))

    def system(self, doc_id):
        return self.dados.setdefault('system', {}).get(doc_id)


class _FakeTx:
    def set(self, ref, data, merge=False):
        ref.set(data, merge=merge)

    def update(self, ref, data):
        ref.update(data)


def _transacao_fake(db, fn):
    return fn(_FakeTx())


class _Base(unittest.TestCase):
    """Cache de validação zerado e transação do Firestore trocada por uma execução direta."""

    def setUp(self):
        gpw.limpar_cache()
        patcher = mock.patch.object(gpw, '_executar_transacao', side_effect=_transacao_fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(gpw.limpar_cache)


def _leituras(db, doc_id):
    return db.dados.get('system', {}).get('__leituras__', []).count(doc_id)


class _Exec:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class _FakeCalendar:
    def __init__(self, itens=None, falhar_list=False, falhar_watch_em=()):
        self.itens = itens or []
        self.falhar_list = falhar_list
        self.falhar_watch_em = set(falhar_watch_em)
        self.watch_calls = []
        self.stop_calls = []
        self.list_calls = []

    def events(self):
        return self

    def channels(self):
        return self

    def list(self, **kwargs):
        self.list_calls.append(kwargs)

        def _run():
            if self.falhar_list:
                raise RuntimeError("API fora")
            return {'items': list(self.itens)}
        return _Exec(_run)

    def watch(self, calendarId=None, body=None, **kwargs):
        self.watch_calls.append((calendarId, body))

        def _run():
            if calendarId in self.falhar_watch_em:
                raise RuntimeError("watch negado")
            exp = int((AGORA + timedelta(days=7)).timestamp() * 1000)
            return {'resourceId': f'res-{calendarId}', 'expiration': str(exp), 'id': body['id']}
        return _Exec(_run)

    def stop(self, body=None):
        self.stop_calls.append(body)
        return _Exec(lambda: {})


class _FakeDrive:
    def __init__(self, falhar=False):
        self.falhar = falhar
        self.watch_calls = []
        self.stop_calls = []

    def files(self):
        return self

    def channels(self):
        return self

    def watch(self, fileId=None, body=None, **kwargs):
        self.watch_calls.append((fileId, body, kwargs))

        def _run():
            if self.falhar:
                raise RuntimeError("sem permissão")
            return {'resourceId': 'res-pasta', 'expiration': str(body['expiration'])}
        return _Exec(_run)

    def stop(self, body=None):
        self.stop_calls.append(body)
        return _Exec(lambda: {})


def _extrair_agenda(evento):
    ini = (evento.get('start') or {}).get('dateTime')
    fim = (evento.get('end') or {}).get('dateTime')
    if not ini:
        return None
    return {'data_limite': ini[:10], 'horario_inicio': ini[11:16], 'horario_fim': fim[11:16] if fim else None}


def _is_iso_after(a, b):
    return (a or '') > (b or '')


def _exp_ms(delta: timedelta) -> str:
    return str(int((AGORA + delta).timestamp() * 1000))


def _db_calendar(enabled=True, canais=None, token='segredo-certo', sync=None):
    db = _Db()
    db.collection('system').document('settings').set({
        'calendar_watch': {'enabled': enabled, 'url': 'https://exemplo.test/on_calendar_push'},
    })
    if canais is None:
        canais = {'canal1': {'calendar_id': 'primary', 'resource_id': 'res-primary',
                             'expiration': _exp_ms(timedelta(days=5)),
                             'ultimo_delta_em': (AGORA - timedelta(minutes=10)).isoformat()}}
    db.collection('system').document('calendar_watch').set(
        {'channel_token': token, 'canais': canais, 'url': 'https://exemplo.test/on_calendar_push'})
    db.collection('system').document('sync').set(sync or {'status': 'completed'})
    return db


def _headers(canal='canal1', token='segredo-certo', estado='exists', **extra):
    h = {'X-Goog-Channel-ID': canal, 'X-Goog-Channel-Token': token, 'X-Goog-Resource-State': estado,
         'X-Goog-Resource-ID': 'res-primary', 'X-Goog-Message-Number': '7'}
    h.update(extra)
    return {k: v for k, v in h.items() if v is not None}


class TestTokenConfere(_Base):
    def test_vazios_e_diferentes_nao_conferem(self):
        self.assertFalse(gpw.token_confere('abc', ''))
        self.assertFalse(gpw.token_confere('', ''))
        self.assertFalse(gpw.token_confere(None, 'abc'))
        self.assertFalse(gpw.token_confere('abc', 'abd'))
        self.assertTrue(gpw.token_confere('abc', 'abc'))

    def test_usa_compare_digest(self):
        with mock.patch.object(gpw.hmac, 'compare_digest', wraps=gpw.hmac.compare_digest) as cd:
            gpw.token_confere('abc', 'abc')
        cd.assert_called_once()


class TestCalendarPush(_Base):
    def _processar(self, db, headers, cal=None, **kw):
        cal = cal if cal is not None else _FakeCalendar()
        return gpw.processar_notificacao_calendar(
            db, headers, agora=kw.pop('agora', AGORA), calendar_service_factory=lambda: cal,
            extrair_agenda=_extrair_agenda, is_iso_after=_is_iso_after, **kw)

    def test_flag_desligado_e_noop_200_para_canal_valido(self):
        db = _db_calendar(enabled=False)
        cal = _FakeCalendar(itens=[{'id': 'reuniao1', 'status': 'confirmed'}])
        status, det = self._processar(db, _headers(), cal)
        self.assertEqual((status, det['motivo']), (200, 'desligado'))
        self.assertEqual(cal.list_calls, [])
        self.assertEqual(db.system('sync')['status'], 'completed')

    def test_flag_desligado_nao_se_revela_para_requisicao_forjada(self):
        db = _db_calendar(enabled=False)
        status, _ = self._processar(db, _headers(token='errado'))
        self.assertEqual(status, 403)

    def test_token_ausente_errado_e_canal_desconhecido_recebem_403(self):
        db = _db_calendar()
        cal = _FakeCalendar()
        for headers in (_headers(token=None), _headers(token='errado'), _headers(canal='outro'),
                        _headers(canal=None), _headers(**{'X-Goog-Resource-ID': None})):
            status, _ = self._processar(db, headers, cal)
            self.assertEqual(status, 403, headers)
        self.assertEqual(cal.list_calls, [], "403 não pode chegar à API do Google")

    def test_resource_id_diferente_recebe_403(self):
        db = _db_calendar()
        status, det = self._processar(db, _headers(**{'X-Goog-Resource-ID': 'res-de-outro'}))
        self.assertEqual(status, 403)

    def test_entrada_zumbi_sem_calendar_id_ou_resource_id_recebe_403(self):
        for canal in ({'resource_id': 'res-primary'}, {'calendar_id': 'primary'},
                      {'ultimo_delta_em': AGORA.isoformat()}):
            gpw.limpar_cache()
            db = _db_calendar(canais={'canal1': canal})
            cal = _FakeCalendar(itens=[{'id': 'reuniao1'}])
            status, _ = self._processar(db, _headers(), cal)
            self.assertEqual(status, 403, canal)
            self.assertEqual(cal.list_calls, [])

    def test_janela_comeca_no_fim_de_sync_que_terminou_em_erro(self):
        db = _db_calendar(sync={'status': 'error', 'last_success': '2026-09-27T09:00:00',
                                'finished_at': '2026-09-27T11:58:30+00:00'})
        cal = _FakeCalendar(itens=[])
        self._processar(db, _headers(), cal)
        self.assertEqual(cal.list_calls[0]['updatedMin'], '2026-09-27T11:58:30Z')

    def test_sync_que_terminou_em_erro_ha_menos_de_15_min_nao_gera_pedido(self):
        db = _db_calendar(sync={'status': 'error', 'finished_at': (AGORA - timedelta(minutes=14)).isoformat()})
        cal = _FakeCalendar(itens=[{'id': 'reuniao1'}])
        with mock.patch('builtins.print') as p:
            status, det = self._processar(db, _headers(), cal)
        self.assertEqual((status, det['motivo']), (200, 'erro_recente'))
        self.assertEqual(db.system('sync')['status'], 'error')
        self.assertTrue(any('terminou em erro' in str(c) for c in p.call_args_list))

    def test_sync_que_terminou_em_erro_ha_mais_de_15_min_libera_pedido(self):
        db = _db_calendar(sync={'status': 'error', 'finished_at': (AGORA - timedelta(minutes=16)).isoformat()})
        _, det = self._processar(db, _headers(), _FakeCalendar(itens=[{'id': 'reuniao1'}]))
        self.assertEqual(det['motivo'], 'solicitado')
        self.assertEqual(db.system('sync')['status'], 'requested')

    def test_cursor_nao_avanca_nem_recria_canal_removido(self):
        db = _db_calendar()
        self.assertFalse(gpw._avancar_cursor_calendar(db, 'canal-que-nao-existe', AGORA))
        self.assertNotIn('canal-que-nao-existe', db.system('calendar_watch')['canais'])
        self.assertTrue(gpw._avancar_cursor_calendar(db, 'canal1', AGORA))

    def test_corpo_da_resposta_nao_revela_flag(self):
        fn = inspect.unwrap(gpw.on_calendar_push)
        db = _db_calendar(enabled=False)
        with mock.patch.object(gpw, '_get_db', return_value=db):
            r_ok = fn(mock.Mock(method='POST', headers=_headers()))
            r_forjada = fn(mock.Mock(method='POST', headers=_headers(token='errado')))
        self.assertEqual((r_ok.status_code, r_ok.get_data(as_text=True)), (200, 'ok'))
        self.assertEqual((r_forjada.status_code, r_forjada.get_data(as_text=True)), (403, 'forbidden'))

    def test_notificacao_sync_ignorada(self):
        db = _db_calendar()
        cal = _FakeCalendar(itens=[{'id': 'reuniao1'}])
        status, det = self._processar(db, _headers(estado='sync'), cal)
        self.assertEqual((status, det['motivo']), (200, 'sync_ignorado'))
        self.assertEqual(cal.list_calls, [])
        self.assertEqual(db.system('sync')['status'], 'completed')

    def test_mudanca_real_pede_sync_de_agenda_e_avanca_cursor(self):
        db = _db_calendar()
        cal = _FakeCalendar(itens=[{'id': 'reuniao1', 'status': 'confirmed', 'updated': '2026-09-27T11:59:00Z'}])
        status, det = self._processar(db, _headers(), cal)
        self.assertEqual((status, det['motivo']), (200, 'solicitado'))
        sync = db.system('sync')
        self.assertEqual(sync['status'], 'requested')
        self.assertEqual(sync['requested_scope'], 'calendar')
        watch = db.system('calendar_watch')
        self.assertEqual(watch['canais']['canal1']['ultimo_delta_em'], AGORA.isoformat())
        self.assertEqual(watch['pedidos_na_janela'], 1)
        # Janela do delta = cursor - margem, com eventos apagados.
        chamada = cal.list_calls[0]
        self.assertEqual(chamada['calendarId'], 'primary')
        self.assertTrue(chamada['showDeleted'])
        self.assertEqual(chamada['updatedMin'], '2026-09-27T11:49:30Z')

    def test_ignora_enquanto_sync_roda_ou_esta_pendente(self):
        for status_sync in ('processing', 'requested'):
            db = _db_calendar(sync={'status': status_sync})
            cal = _FakeCalendar(itens=[{'id': 'reuniao1'}])
            status, det = self._processar(db, _headers(), cal)
            self.assertEqual((status, det['motivo']), (200, 'sync_em_andamento'))
            self.assertEqual(cal.list_calls, [])
            self.assertEqual(db.system('sync'), {'status': status_sync})

    def test_janela_comeca_no_fim_do_ultimo_sync_quando_mais_recente(self):
        db = _db_calendar(sync={'status': 'completed', 'last_success': '2026-09-27T11:58:00'})
        cal = _FakeCalendar(itens=[])
        status, det = self._processar(db, _headers(), cal)
        self.assertEqual(cal.list_calls[0]['updatedMin'], '2026-09-27T11:58:00Z')
        self.assertEqual(det['motivo'], 'eco')

    def test_eco_do_push_do_hermes_nao_pede_sync(self):
        db = _db_calendar()
        db.collection('tarefas').document('t1').set({
            'data_limite': '2026-09-28', 'horario_inicio': '09:00', 'horario_fim': '10:00',
            'data_atualizacao': '2026-09-27T10:00:00'})
        evento = {'id': 'hermesabc', 'status': 'confirmed', 'updated': '2026-09-27T11:59:00Z',
                  'start': {'dateTime': '2026-09-28T09:00:00-03:00'}, 'end': {'dateTime': '2026-09-28T10:00:00-03:00'},
                  'extendedProperties': {'private': {'hermes_task_id': 't1'}}}
        apagado = {'id': 'hermesdef', 'status': 'cancelled'}
        status, det = self._processar(db, _headers(), _FakeCalendar(itens=[evento, apagado]))
        self.assertEqual((status, det['motivo']), (200, 'eco'))
        self.assertEqual(db.system('sync')['status'], 'completed')
        self.assertEqual(db.system('calendar_watch')['canais']['canal1']['ultimo_delta_em'], AGORA.isoformat())

    def test_evento_do_hermes_movido_na_agenda_pede_sync(self):
        db = _db_calendar()
        db.collection('tarefas').document('t1').set({
            'data_limite': '2026-09-28', 'horario_inicio': '09:00', 'horario_fim': '10:00',
            'data_atualizacao': '2026-09-27T10:00:00'})
        evento = {'id': 'hermesabc', 'status': 'confirmed', 'updated': '2026-09-27T11:59:00Z',
                  'start': {'dateTime': '2026-09-28T14:00:00-03:00'}, 'end': {'dateTime': '2026-09-28T15:00:00-03:00'},
                  'extendedProperties': {'private': {'hermes_task_id': 't1'}}}
        status, det = self._processar(db, _headers(), _FakeCalendar(itens=[evento]))
        self.assertEqual(det['motivo'], 'solicitado')

    def test_debounce_nao_pede_de_novo_nem_avanca_cursor(self):
        db = _db_calendar()
        db.collection('system').document('calendar_watch').set(
            {'ultimo_pedido_sync_em': (AGORA - timedelta(seconds=30)).isoformat()}, merge=True)
        cursor_antes = db.system('calendar_watch')['canais']['canal1']['ultimo_delta_em']
        status, det = self._processar(db, _headers(), _FakeCalendar(itens=[{'id': 'reuniao1'}]))
        self.assertEqual((status, det['motivo']), (200, 'debounce'))
        self.assertEqual(db.system('sync')['status'], 'completed')
        self.assertEqual(db.system('calendar_watch')['canais']['canal1']['ultimo_delta_em'], cursor_antes)

    def test_depois_do_debounce_pede_de_novo(self):
        db = _db_calendar()
        db.collection('system').document('calendar_watch').set(
            {'ultimo_pedido_sync_em': (AGORA - timedelta(seconds=61)).isoformat()}, merge=True)
        _, det = self._processar(db, _headers(), _FakeCalendar(itens=[{'id': 'reuniao1'}]))
        self.assertEqual(det['motivo'], 'solicitado')

    def test_teto_de_pedidos_por_hora(self):
        db = _db_calendar()
        db.collection('system').document('calendar_watch').set({
            'pedidos_janela_inicio': (AGORA - timedelta(minutes=20)).isoformat(),
            'pedidos_na_janela': gpw.CALENDAR_MAX_PEDIDOS_POR_HORA}, merge=True)
        _, det = self._processar(db, _headers(), _FakeCalendar(itens=[{'id': 'reuniao1'}]))
        self.assertEqual(det['motivo'], 'limite_por_hora')
        self.assertEqual(db.system('sync')['status'], 'completed')

    def test_erro_da_api_no_delta_degrada_para_pedir_sync(self):
        db = _db_calendar()
        _, det = self._processar(db, _headers(), _FakeCalendar(falhar_list=True))
        self.assertEqual(det['motivo'], 'solicitado')

    def test_erro_ao_montar_servico_degrada_para_pedir_sync(self):
        db = _db_calendar()

        def _quebra():
            raise RuntimeError("credencial revogada")
        status, det = gpw.processar_notificacao_calendar(
            db, _headers(), agora=AGORA, calendar_service_factory=_quebra,
            extrair_agenda=_extrair_agenda, is_iso_after=_is_iso_after)
        self.assertEqual((status, det['motivo']), (200, 'solicitado'))

    def test_endpoint_so_aceita_post_e_nunca_devolve_5xx_por_erro_interno(self):
        fn = inspect.unwrap(gpw.on_calendar_push)
        req = mock.Mock(method='GET', headers={})
        self.assertEqual(fn(req).status_code, 405)
        req = mock.Mock(method='POST', headers=_headers())
        with mock.patch.object(gpw, '_get_db', side_effect=RuntimeError('firestore fora')):
            self.assertEqual(fn(req).status_code, 200)
        db = _db_calendar()
        with mock.patch.object(gpw, '_get_db', return_value=db):
            self.assertEqual(fn(mock.Mock(method='POST', headers=_headers(token='errado'))).status_code, 403)


class TestPedirSyncAgenda(_Base):
    def test_nao_rebaixa_pedido_completo_nem_mexe_em_sync_rodando(self):
        for sync in ({'status': 'requested'}, {'status': 'requested', 'requested_scope': 'full'},
                     {'status': 'requested', 'requested_scope': 'calendar'}, {'status': 'processing'}):
            db = _db_calendar(sync=dict(sync))
            resultado = gpw.pedir_sync_agenda(db, AGORA)
            self.assertIn(resultado, ('ja_solicitado', 'sync_em_andamento'))
            self.assertEqual(db.system('sync'), sync)
            self.assertNotIn('ultimo_pedido_sync_em', db.system('calendar_watch'))

    def test_pedido_usa_transacao(self):
        db = _db_calendar()
        self.assertEqual(gpw.pedir_sync_agenda(db, AGORA), 'solicitado')
        gpw._executar_transacao.assert_called()


class TestCacheDeValidacao(_Base):
    def test_requisicoes_forjadas_nao_custam_leitura_a_cada_uma(self):
        db = _db_calendar()
        with mock.patch.object(gpw.time, 'monotonic', return_value=1000.0):
            for _ in range(10):
                status, _ = gpw.processar_notificacao_calendar(db, _headers(token='errado'), agora=AGORA)
                self.assertEqual(status, 403)
        self.assertEqual(_leituras(db, 'calendar_watch'), 1)
        self.assertEqual(_leituras(db, 'settings'), 0)

    def test_canal_novo_de_outra_instancia_e_reconhecido_apos_releitura(self):
        db = _db_calendar()
        cal = _FakeCalendar(itens=[])
        kw = dict(calendar_service_factory=lambda: cal, extrair_agenda=_extrair_agenda, is_iso_after=_is_iso_after)
        with mock.patch.object(gpw.time, 'monotonic', return_value=1000.0):
            self.assertEqual(gpw.processar_notificacao_calendar(db, _headers(), agora=AGORA, **kw)[0], 200)
        # Renovação em outra instância troca o canal.
        watch = db.system('calendar_watch')
        watch['canais'] = {'canal2': {'calendar_id': 'primary', 'resource_id': 'res-primary'}}
        with mock.patch.object(gpw.time, 'monotonic', return_value=1001.0):
            self.assertEqual(gpw.processar_notificacao_calendar(db, _headers(canal='canal2'), agora=AGORA, **kw)[0], 403)
        with mock.patch.object(gpw.time, 'monotonic', return_value=1006.0):
            self.assertEqual(gpw.processar_notificacao_calendar(db, _headers(canal='canal2'), agora=AGORA, **kw)[0], 200)

    def test_log_de_recusa_limitado(self):
        with mock.patch('builtins.print') as p:
            for t in (0.0, 10.0, 20.0):
                gpw._logar_recusa('[X]', 'canal_ou_token_invalido', relogio=lambda t=t: t)
            self.assertEqual(p.call_count, 1)
            gpw._logar_recusa('[X]', 'canal_ou_token_invalido', relogio=lambda: 61.0)
        self.assertEqual(p.call_count, 2)
        self.assertIn('+2', str(p.call_args_list[-1]))


class TestRenovarCalendarWatch(_Base):
    def test_entrada_zumbi_e_descartada_e_stop_nunca_vai_sem_resource_id(self):
        db = _db_calendar(canais={
            'canal1': {'calendar_id': 'primary', 'resource_id': 'r1', 'expiration': _exp_ms(timedelta(days=5))},
            'zumbi': {'ultimo_delta_em': AGORA.isoformat()},
            'zumbi2': {'resource_id': 'r-z'},
        })
        cal = _FakeCalendar()
        r = gpw.renovar_calendar_watch(db, cal, agora=AGORA, calendar_ids=['primary'])
        canais = db.system('calendar_watch')['canais']
        self.assertNotIn('zumbi', canais)
        self.assertNotIn('zumbi2', canais)
        self.assertIn('canal1', canais, "canal em dia continua; só os zumbis saem")
        self.assertEqual(cal.watch_calls, [])
        self.assertEqual(cal.stop_calls, [{'id': 'zumbi2', 'resourceId': 'r-z'}])
        self.assertFalse(r['renovado'])

    def test_flag_desligado_nao_registra(self):
        db = _db_calendar(enabled=False, canais={})
        cal = _FakeCalendar()
        r = gpw.renovar_calendar_watch(db, cal, agora=AGORA, calendar_ids=['primary'])
        self.assertEqual(r, {'habilitado': False, 'renovado': False})
        self.assertEqual(cal.watch_calls, [])

    def test_primeiro_registro_cria_um_canal_por_agenda_com_token_novo(self):
        db = _db_calendar(canais={}, token=None)
        cal = _FakeCalendar()
        r = gpw.renovar_calendar_watch(db, cal, agora=AGORA, calendar_ids=['primary', 'hermes@group'])
        self.assertTrue(r['renovado'])
        self.assertEqual([c for c, _ in cal.watch_calls], ['primary', 'hermes@group'])
        watch = db.system('calendar_watch')
        token = watch['channel_token']
        self.assertGreaterEqual(len(token), 32)
        for _, body in cal.watch_calls:
            self.assertEqual(body['type'], 'web_hook')
            self.assertEqual(body['address'], 'https://exemplo.test/on_calendar_push')
            self.assertEqual(body['token'], token)
            self.assertEqual(body['params'], {'ttl': str(gpw.CALENDAR_WATCH_TTL_S)})
        self.assertEqual(len(watch['canais']), 2)
        canal = watch['canais'][cal.watch_calls[0][1]['id']]
        self.assertEqual(canal['calendar_id'], 'primary')
        self.assertEqual(canal['resource_id'], 'res-primary')
        self.assertTrue(canal['expiration'])
        self.assertEqual(watch['url_origem'], 'settings')
        self.assertEqual(cal.stop_calls, [])

    def test_em_dia_nao_renova(self):
        db = _db_calendar()  # canal1 expira em 5 dias
        cal = _FakeCalendar()
        r = gpw.renovar_calendar_watch(db, cal, agora=AGORA, calendar_ids=['primary'])
        self.assertEqual(r['motivo'], 'em_dia')
        self.assertEqual(cal.watch_calls, [])

    def test_perto_de_expirar_renova_para_o_antigo_e_mantem_token_e_cursor(self):
        db = _db_calendar(canais={'canal1': {'calendar_id': 'primary', 'resource_id': 'res-velho',
                                             'expiration': _exp_ms(timedelta(hours=30)),
                                             'ultimo_delta_em': '2026-09-27T11:00:00+00:00'}})
        cal = _FakeCalendar()
        r = gpw.renovar_calendar_watch(db, cal, agora=AGORA, calendar_ids=['primary'])
        self.assertTrue(r['renovado'])
        watch = db.system('calendar_watch')
        self.assertEqual(watch['channel_token'], 'segredo-certo')
        self.assertNotIn('canal1', watch['canais'])
        (novo,) = watch['canais'].values()
        self.assertEqual(novo['ultimo_delta_em'], '2026-09-27T11:00:00+00:00')
        self.assertEqual(cal.stop_calls, [{'id': 'canal1', 'resourceId': 'res-velho'}])

    def test_falha_numa_agenda_mantem_canal_antigo_dela(self):
        db = _db_calendar(canais={'canal1': {'calendar_id': 'primary', 'resource_id': 'res-velho',
                                             'expiration': _exp_ms(timedelta(hours=1))}})
        cal = _FakeCalendar(falhar_watch_em={'primary'})
        r = gpw.renovar_calendar_watch(db, cal, agora=AGORA, calendar_ids=['primary', 'hermes@group'])
        watch = db.system('calendar_watch')
        self.assertIn('canal1', watch['canais'])
        self.assertEqual(len(watch['canais']), 2)
        self.assertIn('primary', r['erros'])
        self.assertEqual(cal.stop_calls, [])

    def test_agenda_que_saiu_do_sync_tem_canal_parado(self):
        db = _db_calendar(canais={
            'canal1': {'calendar_id': 'primary', 'resource_id': 'r1', 'expiration': _exp_ms(timedelta(days=5))},
            'canal2': {'calendar_id': 'antiga@group', 'resource_id': 'r2', 'expiration': _exp_ms(timedelta(days=5))},
        })
        cal = _FakeCalendar()
        gpw.renovar_calendar_watch(db, cal, agora=AGORA, calendar_ids=['primary'])
        self.assertIn({'id': 'canal2', 'resourceId': 'r2'}, cal.stop_calls)
        self.assertNotIn('canal2', db.system('calendar_watch')['canais'])

    def test_url_sem_config_usa_derivada(self):
        settings = {'calendar_watch': {'enabled': True}}
        url, origem = gpw.url_do_endpoint(settings, 'calendar_watch', 'on_calendar_push')
        self.assertEqual(origem, 'derivada')
        self.assertTrue(url.startswith('https://us-central1-') and url.endswith('/on_calendar_push'))

    def test_renovador_agendado_nao_monta_credencial_com_flag_desligado(self):
        db = _db_calendar(enabled=False)
        fn = inspect.unwrap(gpw.renovar_calendar_watch_diario)
        with mock.patch.object(gpw, '_get_db', return_value=db), \
                mock.patch.object(gpw, '_main') as m:
            fn(None)
        m.assert_not_called()

    def test_renovador_agendado_degrada_com_credencial_revogada(self):
        db = _db_calendar()
        fake_main = mock.Mock()
        fake_main.get_calendar_service.side_effect = RuntimeError('invalid_grant')
        fake_main._mensagem_erro_sync.return_value = 'ERRO GOOGLE AUTH'
        fn = inspect.unwrap(gpw.renovar_calendar_watch_diario)
        with mock.patch.object(gpw, '_get_db', return_value=db), \
                mock.patch.object(gpw, '_main', return_value=fake_main):
            fn(None)  # não levanta
        fake_main._mensagem_erro_sync.assert_called_once()


def _db_drive(enabled=True, watch=None):
    db = _Db()
    db.collection('system').document('settings').set({
        'drop_folder_id': 'pasta123',
        'drive_watch': {'enabled': enabled, 'url': 'https://exemplo.test/on_drive_push'},
    })
    if watch is None:
        watch = {'channel_id': 'dcanal', 'channel_token': 'tok-drive', 'resource_id': 'res-pasta',
                 'folder_id': 'pasta123', 'url': 'https://exemplo.test/on_drive_push',
                 'expiration': _exp_ms(timedelta(hours=20))}
    db.collection('system').document('drive_watch').set(watch)
    return db


def _h_drive(canal='dcanal', token='tok-drive', estado='update', changed='children'):
    h = {'X-Goog-Channel-ID': canal, 'X-Goog-Channel-Token': token, 'X-Goog-Resource-State': estado,
         'X-Goog-Resource-ID': 'res-pasta', 'X-Goog-Changed': changed}
    return {k: v for k, v in h.items() if v is not None}


class _LockMain:
    """main falso só com o lock (mesma semântica de acquire_sync_lock/release_sync_lock)."""

    def __init__(self, db):
        self.db = db
        self.acquires = []

    def acquire_sync_lock(self, db, owner_id, lock_doc_id=None):
        self.acquires.append(lock_doc_id)
        ref = db.collection('system').document(lock_doc_id)
        if ref.get().exists:
            return False
        ref.create({'owner_id': owner_id})
        return True

    def release_sync_lock(self, db, owner_id, lock_doc_id=None):
        ref = db.collection('system').document(lock_doc_id)
        if (ref.get().to_dict() or {}).get('owner_id') == owner_id:
            ref.delete()


class TestDrivePush(_Base):
    def setUp(self):
        super().setUp()
        self.execucoes = []

    def _executar(self):
        self.execucoes.append(1)
        return {'novos': 1, 'reprocessados': 0, 'erro': None}

    def _processar(self, db, headers, agora=AGORA):
        lock_main = _LockMain(db)
        with mock.patch.object(gpw, '_main', return_value=lock_main):
            r = gpw.processar_notificacao_drive(db, headers, agora=agora, executar=self._executar)
        return r, lock_main

    def test_flag_desligado_e_noop(self):
        db = _db_drive(enabled=False)
        (status, det), _ = self._processar(db, _h_drive())
        self.assertEqual((status, det['motivo']), (200, 'desligado'))
        (status, _), _ = self._processar(db, _h_drive(token='errado'))
        self.assertEqual(status, 403)
        self.assertEqual(self.execucoes, [])

    def test_doc_sem_resource_id_e_zumbi(self):
        db = _db_drive(watch={'channel_id': 'dcanal', 'channel_token': 'tok-drive'})
        (status, _), _ = self._processar(db, _h_drive())
        self.assertEqual(status, 403)

    def test_token_ou_canal_invalido_403(self):
        db = _db_drive()
        for h in (_h_drive(token=None), _h_drive(token='errado'), _h_drive(canal='outro'), _h_drive(canal=None),
                  _h_drive(canal='dcanal-ç', token='tok-drive-ç')):
            (status, _), _ = self._processar(db, h)
            self.assertEqual(status, 403, h)
        self.assertEqual(self.execucoes, [])

    def test_sync_e_mudanca_sem_children_ignorados(self):
        db = _db_drive()
        (status, det), _ = self._processar(db, _h_drive(estado='sync', changed=None))
        self.assertEqual(det['motivo'], 'sync_ignorado')
        (status, det), _ = self._processar(db, _h_drive(changed='properties,permissions'))
        self.assertEqual(det['motivo'], 'sem_arquivo_novo')
        self.assertEqual(self.execucoes, [])

    def test_arquivo_novo_roda_varredura_sob_lock_e_registra(self):
        db = _db_drive()
        (status, det), lock_main = self._processar(db, _h_drive())
        self.assertEqual((status, det['motivo']), (200, 'executado'))
        self.assertEqual(self.execucoes, [1])
        self.assertEqual(lock_main.acquires, [gpw.DRIVE_ACERVO_LOCK_DOC_ID])
        self.assertIsNone(db.system(gpw.DRIVE_ACERVO_LOCK_DOC_ID), "lock liberado")
        watch = db.system('drive_watch')
        self.assertEqual(watch['ultima_varredura_em'], AGORA.isoformat())
        self.assertEqual(watch['ultimo_resultado']['novos'], 1)

    def test_debounce(self):
        db = _db_drive()
        self._processar(db, _h_drive())
        (status, det), _ = self._processar(db, _h_drive(), agora=AGORA + timedelta(seconds=30))
        self.assertEqual(det['motivo'], 'debounce')
        self._processar(db, _h_drive(), agora=AGORA + timedelta(seconds=61))
        self.assertEqual(self.execucoes, [1, 1])

    def test_lock_ocupado_nao_roda(self):
        db = _db_drive()
        db.collection('system').document(gpw.DRIVE_ACERVO_LOCK_DOC_ID).set({'owner_id': 'cron'})
        (status, det), _ = self._processar(db, _h_drive())
        self.assertEqual((status, det['motivo']), (200, 'lock_ocupado'))
        self.assertEqual(self.execucoes, [])

    def test_erro_na_varredura_responde_200_e_libera_lock(self):
        db = _db_drive()

        def _quebra():
            raise RuntimeError('Drive fora')
        lock_main = _LockMain(db)
        with mock.patch.object(gpw, '_main', return_value=lock_main):
            status, det = gpw.processar_notificacao_drive(db, _h_drive(), agora=AGORA, executar=_quebra)
        self.assertEqual((status, det['motivo']), (200, 'erro'))
        self.assertIsNone(db.system(gpw.DRIVE_ACERVO_LOCK_DOC_ID))
        self.assertIn('Drive fora', db.system('drive_watch')['last_erro'])


class TestRenovarDriveWatch(_Base):
    def test_flag_desligado_nao_registra(self):
        db = _db_drive(enabled=False)
        ds = _FakeDrive()
        self.assertEqual(gpw.renovar_drive_watch(db, ds, agora=AGORA), {'habilitado': False, 'renovado': False})
        self.assertEqual(ds.watch_calls, [])

    def test_primeiro_registro(self):
        db = _db_drive(watch={})
        ds = _FakeDrive()
        r = gpw.renovar_drive_watch(db, ds, agora=AGORA)
        self.assertTrue(r['renovado'])
        (file_id, body, kwargs), = ds.watch_calls
        self.assertEqual(file_id, 'pasta123')
        self.assertTrue(kwargs.get('supportsAllDrives'))
        watch = db.system('drive_watch')
        self.assertEqual(body['token'], watch['channel_token'])
        self.assertEqual(body['id'], watch['channel_id'])
        self.assertEqual(body['address'], 'https://exemplo.test/on_drive_push')
        self.assertEqual(body['expiration'], int((AGORA + timedelta(hours=23)).timestamp() * 1000))
        self.assertEqual(watch['resource_id'], 'res-pasta')
        self.assertEqual(watch['folder_id'], 'pasta123')
        self.assertEqual(ds.stop_calls, [])

    def test_canal_anterior_sem_resource_id_nao_chama_stop(self):
        db = _db_drive(watch={'channel_id': 'dcanal', 'channel_token': 'tok-drive'})
        ds = _FakeDrive()
        self.assertTrue(gpw.renovar_drive_watch(db, ds, agora=AGORA)['renovado'])
        self.assertEqual(ds.stop_calls, [])

    def test_em_dia_nao_renova(self):
        db = _db_drive()  # expira em 20 h
        ds = _FakeDrive()
        self.assertEqual(gpw.renovar_drive_watch(db, ds, agora=AGORA)['motivo'], 'em_dia')
        self.assertEqual(ds.watch_calls, [])

    def test_perto_de_expirar_renova_e_para_o_antigo(self):
        db = _db_drive()
        ds = _FakeDrive()
        r = gpw.renovar_drive_watch(db, ds, agora=AGORA + timedelta(hours=8))  # faltam 12 h
        self.assertTrue(r['renovado'])
        watch = db.system('drive_watch')
        self.assertNotEqual(watch['channel_id'], 'dcanal')
        self.assertEqual(watch['channel_token'], 'tok-drive')
        self.assertEqual(ds.stop_calls, [{'id': 'dcanal', 'resourceId': 'res-pasta'}])

    def test_falha_no_watch_preserva_canal_atual_e_registra_erro(self):
        db = _db_drive()
        ds = _FakeDrive(falhar=True)
        r = gpw.renovar_drive_watch(db, ds, agora=AGORA, forcar=True)
        self.assertFalse(r['renovado'])
        watch = db.system('drive_watch')
        self.assertEqual(watch['channel_id'], 'dcanal')
        self.assertIn('sem permissão', watch['last_erro'])
        self.assertEqual(ds.stop_calls, [])


class TestCronAcervoUsaLock(_Base):
    def test_cron_pula_quando_webhook_segura_o_lock(self):
        import knowledge_graph
        db = _Db()
        db.collection('system').document(gpw.DRIVE_ACERVO_LOCK_DOC_ID).set({'owner_id': 'webhook'})
        chamadas = []
        with mock.patch.object(knowledge_graph, '_get_db', return_value=db), \
                mock.patch.object(gpw, '_main', return_value=_LockMain(db)), \
                mock.patch.object(knowledge_graph, 'executar_monitoramento_acervo_global',
                                  side_effect=lambda: chamadas.append(1)):
            inspect.unwrap(knowledge_graph.monitorar_acervo_global)(None)
        self.assertEqual(chamadas, [])


if __name__ == '__main__':
    unittest.main()
