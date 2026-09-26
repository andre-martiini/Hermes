"""Testes da redução de custo do run_full_sync (26/09/2026).

Medido pelo próprio firestore_metrics: scheduled_sync ~100k leituras/~50k escritas por dia
mesmo em dia calmo, on_sync_request 17k-130k leituras/7k-94k escritas. Cobre:
- logs do sync gravados em system/sync de forma espaçada (cada gravação ali reinvocava
  on_sync_request, 1 GB, só para sair);
- sync de contatos sem regravar contato inalterado e no máximo a cada 6h;
- sync de agenda sem regravar evento inalterado e sem reler a janela para a limpeza;
- monitoramento do acervo fora do run_full_sync (fica só no cron próprio);
- mudança de horário de ação pedindo sync só de agenda, e a escrita da sincronia inversa
  do próprio sync não pedindo outro sync;
- detector de WhatsApp lendo só a resposta mais recente de cada chat;
- reaproveitamento da leitura de 'tarefas' pelo vínculo calendar-ação e pela triagem de
  WhatsApp.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import main
import atencao
import email_action_linker


# --------------------------------------------------------------------------- fakes


class _Snap:
    def __init__(self, store, key, data):
        self._store = store
        self.id = key
        self._data = data
        self.exists = data is not None
        self.reference = _DocRef(store, key)

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, store, key, log=None):
        self._store = store
        self.id = key
        self._log = log if log is not None else store.setdefault("__log__", [])

    def create(self, data):
        if self.id in self._store:
            raise RuntimeError("already exists")
        self._store[self.id] = dict(data)

    def get(self, transaction=None):
        return _Snap(self._store, self.id, self._store.get(self.id))

    def set(self, data, merge=False):
        self._log.append(("set", self.id, dict(data)))
        if merge and self.id in self._store:
            self._store[self.id].update(data)
        else:
            self._store[self.id] = dict(data)

    def update(self, data):
        self._log.append(("update", self.id, dict(data)))
        self._store.setdefault(self.id, {}).update(data)

    def delete(self):
        self._log.append(("delete", self.id, None))
        self._store.pop(self.id, None)


class _Query:
    def __init__(self, store, filtros=None):
        self._store = store
        self._filtros = filtros or []

    def where(self, campo, op, valor):
        return _Query(self._store, self._filtros + [(campo, op, valor)])

    def stream(self):
        self._store.setdefault("__reads__", []).append(list(self._filtros))
        out = []
        for key, data in list(self._store.items()):
            if key.startswith("__"):
                continue
            ok = True
            for campo, op, valor in self._filtros:
                v = data.get(campo)
                if op == "==" and v != valor:
                    ok = False
                elif op == ">=" and not (v is not None and v >= valor):
                    ok = False
                elif op == "<=" and not (v is not None and v <= valor):
                    ok = False
            if ok:
                out.append(_Snap(self._store, key, data))
        return out


class _Collection(_Query):
    def document(self, key=None):
        return _DocRef(self._store, key or f"auto-{len(self._store)}")


class _Db:
    def __init__(self, data=None):
        self._collections = {nome: dict(docs) for nome, docs in (data or {}).items()}

    def collection(self, nome):
        return _Collection(self._collections.setdefault(nome, {}))

    def store(self, nome):
        return self._collections.setdefault(nome, {})

    def ops(self, nome):
        return [op for op in self.store(nome).get("__log__", [])]


# --------------------------------------------------------------------------- 4. logs espaçados


class _RefGravador:
    def __init__(self):
        self.chamadas = []

    def update(self, payload):
        self.chamadas.append(("update", dict(payload)))

    def set(self, payload, merge=False):
        self.chamadas.append(("set", dict(payload)))

    def get(self):
        return "snap"


class TestSyncRefComLogsEspacados(unittest.TestCase):
    def setUp(self):
        self.agora = [1000.0]
        self.ref = _RefGravador()
        self.proxy = main._SyncRefComLogsEspacados(self.ref, intervalo_s=15, relogio=lambda: self.agora[0])

    def test_logs_seguidos_viram_uma_gravacao_por_intervalo(self):
        logs = []
        for i in range(20):
            main.log_to_firestore(self.proxy, logs, f"linha {i}", True)
        # A primeira grava (nenhuma gravação antes); as 19 seguintes, dentro dos 15 s, não.
        self.assertEqual(len(self.ref.chamadas), 1)
        self.agora[0] += 16
        main.log_to_firestore(self.proxy, logs, "linha depois do intervalo", True)
        self.assertEqual(len(self.ref.chamadas), 2)
        # A gravação leva a lista inteira acumulada em memória.
        self.assertEqual(len(self.ref.chamadas[-1][1]["logs"]), 21)

    def test_set_com_logs_reinicia_o_intervalo(self):
        logs = ["inicio"]
        self.proxy.set({"status": "processing", "logs": logs}, merge=True)
        main.log_to_firestore(self.proxy, logs, "logo depois do set", True)
        self.assertEqual([c[0] for c in self.ref.chamadas], ["set"])

    def test_linha_de_erro_grava_na_hora(self):
        logs = ["inicio"]
        self.proxy.set({"logs": logs})
        with mock.patch("main.emit_notification_backend"):
            main.log_to_firestore(self.proxy, logs, "[CAL-LINK][ERRO] falhou", True)
        self.assertEqual([c[0] for c in self.ref.chamadas], ["set", "update"])

    def test_update_com_outros_campos_passa_direto(self):
        self.proxy.set({"logs": []})
        self.proxy.update({"status": "completed", "logs": []})
        self.assertEqual([c[0] for c in self.ref.chamadas], ["set", "update"])

    def test_outros_atributos_delegados(self):
        self.assertEqual(self.proxy.get(), "snap")


# --------------------------------------------------------------------------- run_full_sync


class _Patches:
    """Isola o run_full_sync das APIs externas; devolve os mocks por nome."""

    def __init__(self, db):
        self.db = db
        self._cms = {
            "get_db": mock.patch("main.get_db", return_value=db),
            "ts": mock.patch("main.get_tasks_service", return_value="ts"),
            "gs": mock.patch("main.get_gmail_service", return_value="gs"),
            "cs": mock.patch("main.get_calendar_service", return_value="cs"),
            "cal": mock.patch("main.sync_google_calendar", return_value={}),
            "push": mock.patch("main.sync_google_tasks_push"),
            "pull": mock.patch("main.sync_google_tasks_pull"),
            "contatos": mock.patch("main.sync_google_contacts_internal", return_value={"added": 0}),
            "acervo": mock.patch("main.executar_monitoramento_acervo_global"),
            "allcare": mock.patch("main.sync_allcare_portal_bills"),
            "cal_link": mock.patch("email_action_linker.link_calendar_events_to_actions"),
            "atencao": mock.patch("atencao.detectar_aguardando_terceiro_vencido"),
            "resp": mock.patch("resposta_esperada.reconstruir_indice", return_value={"gravado": False}),
            "wa": mock.patch("whatsapp_ingest.triage_whatsapp_messages"),
        }
        self.m = {}

    def __enter__(self):
        for nome, cm in self._cms.items():
            self.m[nome] = cm.__enter__()
        return self.m

    def __exit__(self, *exc):
        for cm in reversed(list(self._cms.values())):
            cm.__exit__(*exc)
        return False


class TestRunFullSyncEscopos(unittest.TestCase):
    def test_escopo_completo_roda_tudo_menos_acervo(self):
        db = _Db()
        with _Patches(db) as m:
            self.assertTrue(main.run_full_sync("scheduled"))
        m["acervo"].assert_not_called()
        for nome in ("cal", "push", "pull", "contatos", "allcare", "cal_link", "atencao", "resp", "wa"):
            m[nome].assert_called_once()
        # A leitura de 'tarefas' do passo é repassada ao vínculo calendar-ação e à triagem.
        self.assertIn("tarefas_docs", m["cal_link"].call_args.kwargs)
        self.assertIn("tarefas_docs", m["wa"].call_args.kwargs)
        # Execução de contatos registrada para o intervalo de 6h.
        self.assertIn("ultima_execucao", db.store("system")[main.CONTACTS_SYNC_STATE_DOC_ID])

    def test_escopo_agenda_pula_contatos_allcare_e_whatsapp(self):
        db = _Db()
        with _Patches(db) as m:
            self.assertTrue(main.run_full_sync("firestore-request:agenda", scope=main.SYNC_SCOPE_CALENDAR))
        for nome in ("cal", "push", "pull", "cal_link", "atencao", "resp"):
            m[nome].assert_called_once()
        for nome in ("contatos", "allcare", "wa", "acervo", "gs"):
            m[nome].assert_not_called()

    def test_contatos_pulados_se_rodaram_ha_menos_de_6h(self):
        recente = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        db = _Db({"system": {main.CONTACTS_SYNC_STATE_DOC_ID: {"ultima_execucao": recente}}})
        with _Patches(db) as m:
            main.run_full_sync("scheduled")
        m["contatos"].assert_not_called()
        m["allcare"].assert_called_once()

    def test_contatos_rodam_se_passaram_6h(self):
        antigo = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
        db = _Db({"system": {main.CONTACTS_SYNC_STATE_DOC_ID: {"ultima_execucao": antigo}}})
        with _Patches(db) as m:
            main.run_full_sync("scheduled")
        m["contatos"].assert_called_once()

    def test_pedido_manual_forca_contatos(self):
        recente = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        db = _Db({"system": {main.CONTACTS_SYNC_STATE_DOC_ID: {"ultima_execucao": recente}}})
        with _Patches(db) as m:
            main._atender_pedido_de_sync({"status": "requested"})
        m["contatos"].assert_called_once()

    def test_falha_nos_contatos_nao_registra_execucao(self):
        db = _Db()
        with _Patches(db) as m:
            m["contatos"].return_value = None
            main.run_full_sync("scheduled")
        self.assertNotIn(main.CONTACTS_SYNC_STATE_DOC_ID, db.store("system"))

    def test_repasse_pedido_por_acao_roda_so_agenda(self):
        db = _Db()
        passos = []

        def cal(*a, **k):
            passos.append("cal")
            if len(passos) == 1:
                # Durante o 1º passo, uma ação muda de horário: fica enfileirado um pedido só de agenda.
                main.queue_sync_request(db, "task-schedule-change", scope=main.SYNC_SCOPE_CALENDAR)
            return {}

        with _Patches(db) as m:
            m["cal"].side_effect = cal
            main.run_full_sync("scheduled")
        self.assertEqual(len(passos), 2)
        m["contatos"].assert_called_once()  # só no 1º passo
        m["allcare"].assert_called_once()   # 2º passo foi só de agenda
        m["wa"].assert_called_once()

    def test_repasse_com_pedido_completo_enfileirado_roda_tudo(self):
        db = _Db()
        passos = []

        def cal(*a, **k):
            passos.append("cal")
            if len(passos) == 1:
                main.queue_sync_request(db, "sync-busy:scheduled")
            return {}

        with _Patches(db) as m:
            m["cal"].side_effect = cal
            main.run_full_sync("firestore-request:agenda", scope=main.SYNC_SCOPE_CALENDAR)
        self.assertEqual(len(passos), 2)
        m["allcare"].assert_called_once()
        m["wa"].assert_called_once()

    def test_pedido_de_agenda_e_roteado_com_escopo_de_agenda(self):
        with mock.patch("main.run_full_sync") as m_run:
            main._atender_pedido_de_sync({"status": "requested", "requested_scope": "calendar"})
        m_run.assert_called_once_with("firestore-request:agenda", scope=main.SYNC_SCOPE_CALENDAR)

    def test_run_full_sync_limpa_o_escopo_pedido(self):
        db = _Db({"system": {"sync": {"status": "requested", "requested_scope": "calendar"}}})
        with _Patches(db):
            main.run_full_sync("firestore-request:agenda", scope=main.SYNC_SCOPE_CALENDAR)
        self.assertIsNone(db.store("system")["sync"].get("requested_scope"))
        self.assertEqual(db.store("system")["sync"]["status"], "completed")


class TestQueueSyncRequest(unittest.TestCase):
    def test_pedido_completo_marca_pending_full_request(self):
        db = _Db()
        main.queue_sync_request(db, "x")
        self.assertTrue(db.store("system")["sync"]["pending_full_request"])

    def test_pedido_de_agenda_nao_rebaixa_pedido_completo(self):
        db = _Db()
        main.queue_sync_request(db, "x")
        main.queue_sync_request(db, "y", scope=main.SYNC_SCOPE_CALENDAR)
        self.assertTrue(db.store("system")["sync"]["pending_full_request"])


# --------------------------------------------------------------------------- 5. on_tarefa_written


class TestPedidoDeSyncPorMudancaDeAgenda(unittest.TestCase):
    def test_mudanca_de_horario_pede_sync_so_de_agenda(self):
        db = _Db({"system": {"sync": {"status": "completed"}}})
        pediu = main._pedir_sync_por_mudanca_de_agenda(db, {"horario_inicio": "10:00"}, {"horario_inicio": "11:00"})
        self.assertTrue(pediu)
        sync = db.store("system")["sync"]
        self.assertEqual(sync["status"], "requested")
        self.assertEqual(sync["requested_scope"], main.SYNC_SCOPE_CALENDAR)

    def test_sem_mudanca_de_agenda_nao_pede(self):
        db = _Db({"system": {"sync": {"status": "completed"}}})
        self.assertFalse(main._pedir_sync_por_mudanca_de_agenda(db, {"titulo": "a"}, {"titulo": "b"}))
        self.assertEqual(db.store("system")["sync"]["status"], "completed")

    def test_sync_em_andamento_enfileira_pedido_de_agenda(self):
        db = _Db({"system": {"sync": {"status": "processing"}}})
        main._pedir_sync_por_mudanca_de_agenda(db, {"data_limite": "2026-09-01"}, {"data_limite": "2026-09-02"})
        sync = db.store("system")["sync"]
        self.assertEqual(sync["status"], "processing")
        self.assertTrue(sync["pending_request"])
        self.assertNotIn("pending_full_request", sync)

    def test_escrita_da_sincronia_inversa_nao_pede_sync(self):
        db = _Db({"system": {"sync": {"status": "completed"}}})
        schedule = {"data_inicio": "2026-09-30", "data_limite": "2026-09-30", "horario_inicio": "14:00", "horario_fim": "15:00"}
        before = {"data_limite": "2026-09-29", "horario_inicio": "10:00", "horario_fim": "11:00"}
        after = {**before, **schedule, main.CAL_SYNC_MARKER_FIELD: main._marcador_sincronia_inversa(schedule)}
        self.assertFalse(main._pedir_sync_por_mudanca_de_agenda(db, before, after))
        self.assertEqual(db.store("system")["sync"]["status"], "completed")

    def test_edicao_do_usuario_depois_da_sincronia_inversa_pede_sync(self):
        """A marca antiga continua no documento, mas não mudou nesta escrita."""
        db = _Db({"system": {"sync": {"status": "completed"}}})
        schedule = {"data_limite": "2026-09-30", "horario_inicio": "14:00", "horario_fim": "15:00"}
        marca = main._marcador_sincronia_inversa(schedule)
        before = {**schedule, main.CAL_SYNC_MARKER_FIELD: marca}
        after = {**before, "horario_inicio": "16:00", "horario_fim": "17:00"}
        self.assertTrue(main._pedir_sync_por_mudanca_de_agenda(db, before, after))

    def test_marca_que_nao_bate_com_o_horario_gravado_pede_sync(self):
        db = _Db({"system": {"sync": {"status": "completed"}}})
        marca = main._marcador_sincronia_inversa({"data_limite": "2026-09-30", "horario_inicio": "14:00", "horario_fim": "15:00"})
        after = {"data_limite": "2026-09-30", "horario_inicio": "18:00", "horario_fim": "19:00", main.CAL_SYNC_MARKER_FIELD: marca}
        self.assertTrue(main._pedir_sync_por_mudanca_de_agenda(db, {"horario_inicio": "10:00"}, after))


# --------------------------------------------------------------------------- 2. agenda


def _evento(event_id, titulo, inicio, fim, updated="2026-01-01T00:00:00Z"):
    return {
        "id": event_id,
        "summary": titulo,
        "start": {"dateTime": inicio},
        "end": {"dateTime": fim},
        "updated": updated,
    }


class _CalendarService:
    def __init__(self, eventos):
        self._eventos = eventos

    def events(self):
        return self

    def list(self, **kwargs):
        return self

    def execute(self):
        return {"items": self._eventos}


class TestSyncGoogleCalendarSemRegravar(unittest.TestCase):
    def _rodar(self, db, eventos, tarefas_docs=None):
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.get_sync_calendar_ids", return_value=["cal"]), \
             mock.patch("main.emit_notification_backend"):
            return main.sync_google_calendar(_CalendarService(eventos), _RefGravador(), [], tarefas_docs=tarefas_docs or [])

    def _datas(self):
        agora = datetime.now(timezone.utc)
        ini = (agora + timedelta(days=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        fim = (agora + timedelta(days=1, hours=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return ini, fim

    def test_evento_inalterado_nao_e_regravado_e_apagado_e_removido(self):
        ini, fim = self._datas()
        db = _Db({"google_calendar_events": {
            "cal__e1": {"google_id": "e1", "calendar_id": "cal", "titulo": "Reunião", "data_inicio": ini,
                        "data_fim": fim, "criado_pelo_hermes": False, "last_sync": "antigo", "extra": "preservado"},
            "cal__apagado": {"google_id": "apagado", "calendar_id": "cal", "titulo": "X", "data_inicio": ini,
                             "data_fim": fim, "criado_pelo_hermes": False},
        }})
        self._rodar(db, [_evento("e1", "Reunião", ini, fim)])
        ops = db.ops("google_calendar_events")
        self.assertEqual(ops, [("delete", "cal__apagado", None)])
        self.assertEqual(db.store("google_calendar_events")["cal__e1"]["last_sync"], "antigo")
        # Uma única leitura da janela (antes: uma para nada e outra para a limpeza).
        self.assertEqual(len(db.store("google_calendar_events")["__reads__"]), 1)

    def test_evento_alterado_ou_novo_e_gravado(self):
        ini, fim = self._datas()
        db = _Db({"google_calendar_events": {
            "cal__e1": {"google_id": "e1", "calendar_id": "cal", "titulo": "Antigo", "data_inicio": ini,
                        "data_fim": fim, "criado_pelo_hermes": False, "extra": "preservado"},
        }})
        self._rodar(db, [_evento("e1", "Novo título", ini, fim), _evento("e2", "Outro", ini, fim)])
        gravados = sorted(op[1] for op in db.ops("google_calendar_events") if op[0] == "set")
        self.assertEqual(gravados, ["cal__e1", "cal__e2"])
        e1 = db.store("google_calendar_events")["cal__e1"]
        self.assertEqual(e1["titulo"], "Novo título")
        self.assertEqual(e1["extra"], "preservado")
        self.assertIn("last_sync", e1)

    def test_sincronia_inversa_grava_marca_na_tarefa(self):
        ini, fim = self._datas()
        db = _Db({"tarefas": {"t1": {"titulo": "Ação", "google_calendar_id": "e1", "data_limite": "2020-01-01",
                                      "horario_inicio": "08:00", "horario_fim": "09:00",
                                      "data_atualizacao": "2020-01-01T00:00:00"}}})
        tarefas_docs = db.collection("tarefas").stream()
        self._rodar(db, [_evento("e1", "Ação", ini, fim, updated=datetime.now(timezone.utc).isoformat())], tarefas_docs)
        tarefa = db.store("tarefas")["t1"]
        marca = tarefa.get(main.CAL_SYNC_MARKER_FIELD)
        self.assertIsInstance(marca, dict)
        self.assertEqual(marca["horario_inicio"], tarefa["horario_inicio"])
        # E essa mesma escrita não pede outro sync.
        before = {"data_limite": "2020-01-01", "horario_inicio": "08:00", "horario_fim": "09:00"}
        self.assertTrue(main._escrita_da_sincronia_inversa(before, tarefa))


# --------------------------------------------------------------------------- 1. contatos


class _People:
    def __init__(self, conexoes):
        self._conexoes = conexoes

    def people(self):
        return self

    def connections(self):
        return self

    def list(self, **kwargs):
        return self

    def execute(self):
        return {"connections": self._conexoes}


def _pessoa(resource, nome, etag, email=""):
    p = {"resourceName": resource, "metadata": {"sources": [{"etag": etag}]}, "names": [{"displayName": nome}]}
    if email:
        p["emailAddresses"] = [{"value": email}]
    return p


class TestSyncContatosSemRegravar(unittest.TestCase):
    def _rodar(self, db, conexoes):
        perfis = db.collection("perfil_pessoas").stream()
        with mock.patch("main.get_google_creds"), \
             mock.patch("googleapiclient.discovery.build", return_value=_People(conexoes)), \
             mock.patch("main.stream_collection_resilient", return_value=perfis):
            return main.sync_google_contacts_internal(db, None, None)

    def test_contato_inalterado_nao_e_regravado(self):
        db = _Db({"perfil_pessoas": {"p1": {
            "nome": "Ana", "email": "ana@x.com", "google_contact_id": "people/c1", "google_etag": "E1",
            "tags": ["Contatos do Google"], "avatar_color": "bg-x", "avatar_initials": "A",
            "data_atualizacao": "antiga",
        }}})
        stats = self._rodar(db, [_pessoa("people/c1", "Ana", "E1", "ana@x.com")])
        self.assertEqual(db.ops("perfil_pessoas"), [])
        self.assertEqual(stats["merged"], 1)
        self.assertEqual(stats["unchanged"], 1)
        self.assertEqual(db.store("perfil_pessoas")["p1"]["data_atualizacao"], "antiga")

    def test_etag_diferente_regrava(self):
        db = _Db({"perfil_pessoas": {"p1": {
            "nome": "Ana", "email": "ana@x.com", "google_contact_id": "people/c1", "google_etag": "E1",
            "tags": ["Contatos do Google"], "avatar_color": "bg-x", "avatar_initials": "A",
        }}})
        stats = self._rodar(db, [_pessoa("people/c1", "Ana", "E2", "ana@x.com")])
        ops = db.ops("perfil_pessoas")
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0][2]["google_etag"], "E2")
        self.assertIn("data_atualizacao", ops[0][2])
        self.assertEqual(stats["unchanged"], 0)

    def test_tag_ausente_regrava_sem_mutar_a_lista_original(self):
        tags_originais = ["Cliente"]
        db = _Db({"perfil_pessoas": {"p1": {
            "nome": "Ana", "email": "ana@x.com", "google_contact_id": "people/c1", "google_etag": "E1",
            "tags": tags_originais, "avatar_color": "bg-x", "avatar_initials": "A",
        }}})
        self._rodar(db, [_pessoa("people/c1", "Ana", "E1", "ana@x.com")])
        ops = db.ops("perfil_pessoas")
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0][2]["tags"], ["Cliente", "Contatos do Google"])


# --------------------------------------------------------------------------- 6. WhatsApp


class _QueryOrdenavel:
    def __init__(self, docs, falhar_ordenado=False):
        self._docs = docs
        self._falhar = falhar_ordenado
        self.consultas = []

    def collection(self, _nome):
        return self

    def where(self, *_a):
        return self

    def order_by(self, campo, direction=None):
        self.consultas.append(("order_by", campo, direction))
        return _Limitada(self, self._docs, self._falhar)

    def stream(self):
        self.consultas.append(("completa",))
        return list(self._docs)


class _Limitada:
    def __init__(self, pai, docs, falhar):
        self._pai, self._docs, self._falhar, self._n = pai, docs, falhar, None

    def limit(self, n):
        self._n = n
        return self

    def stream(self):
        if self._falhar:
            raise RuntimeError("FailedPrecondition: The query requires an index")
        self._pai.consultas.append(("limitada", self._n))
        return sorted(self._docs, key=lambda d: d.to_dict()["timestamp"], reverse=True)[: self._n]


class _Msg:
    def __init__(self, ts):
        self._ts = ts

    def to_dict(self):
        return {"timestamp": self._ts}


class TestRespostasRecebidasDoChat(unittest.TestCase):
    def test_le_so_a_mais_recente(self):
        docs = [_Msg(datetime(2026, 9, d, tzinfo=timezone.utc)) for d in (1, 20, 5)]
        db = _QueryOrdenavel(docs)
        msgs = atencao._respostas_recebidas_do_chat(db, "chat")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].to_dict()["timestamp"].day, 20)
        self.assertIn(("order_by", "timestamp", "DESCENDING"), db.consultas)
        self.assertNotIn(("completa",), db.consultas)

    def test_sem_indice_cai_na_consulta_completa(self):
        docs = [_Msg(datetime(2026, 9, d, tzinfo=timezone.utc)) for d in (1, 20)]
        db = _QueryOrdenavel(docs, falhar_ordenado=True)
        msgs = atencao._respostas_recebidas_do_chat(db, "chat")
        self.assertEqual(len(msgs), 2)
        self.assertIn(("completa",), db.consultas)

    def test_resultado_da_avaliacao_e_o_mesmo_com_so_a_mais_recente(self):
        """avaliar_etapas só pergunta se existe resposta com data >= data_prevista: olhar a
        mais recente dá o mesmo resultado que olhar todas."""
        hoje = datetime(2026, 9, 26).date()
        tarefa = {
            "id": "t1", "titulo": "Ação", "status": "em andamento",
            "whatsapp_vinculos": [{"chat_id": "chat"}],
            "plano_acao": [{"id": "s1", "texto": "Aguardar", "estado": "aguardando_terceiro",
                            "aguardando_de": "Fulano", "data_prevista": "2026-09-10"}],
        }
        todas = [{"timestamp": datetime(2026, 9, d, tzinfo=timezone.utc), "from_me": False} for d in (1, 15, 3)]
        mais_recente = [max(todas, key=lambda m: m["timestamp"])]
        r_todas = atencao.avaliar_etapas([tarefa], hoje, {"chat": todas})
        r_uma = atencao.avaliar_etapas([tarefa], hoje, {"chat": mais_recente})
        self.assertEqual(r_todas, r_uma)
        self.assertEqual(r_todas, [])  # respondeu depois da data prevista
        antigas = [m for m in todas if m["timestamp"].day < 10]
        r_antigas = atencao.avaliar_etapas([tarefa], hoje, {"chat": antigas})
        self.assertEqual(len(r_antigas), 1)  # só respostas anteriores: etapa segue vencida
        self.assertEqual(
            r_antigas,
            atencao.avaliar_etapas([tarefa], hoje, {"chat": [max(antigas, key=lambda m: m["timestamp"])]}),
        )


# --------------------------------------------------------------------------- 7. leitura de tarefas


class TestCandidatasReaproveitamLeitura(unittest.TestCase):
    def test_usa_os_snapshots_recebidos_sem_ler_a_colecao(self):
        db = _Db({"tarefas": {"t1": {"titulo": "Ação", "status": "em andamento"}}})
        snaps = db.collection("tarefas").stream()
        db.store("tarefas").pop("__reads__", None)
        email_action_linker._load_candidate_tasks(db, snaps)
        self.assertNotIn("__reads__", db.store("tarefas"))

    def test_sem_snapshots_le_a_colecao_como_antes(self):
        db = _Db({"tarefas": {"t1": {"titulo": "Ação", "status": "em andamento"}}})
        email_action_linker._load_candidate_tasks(db)
        self.assertIn("__reads__", db.store("tarefas"))


if __name__ == "__main__":
    unittest.main()
