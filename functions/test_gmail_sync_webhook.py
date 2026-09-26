"""Testes da sincronização de Gmail via webhook (Pub/Sub), decomposta de `run_full_sync` em
24/09/2026 (ação Hermes e7fe01f4-6b7b-4789-8, DEV-2026-0003): antes `run_full_sync` chamava
`sync_pix_emails`/`sync_boletos_gmail`/`link_emails_to_actions` a cada ciclo de 60min, junto com
Calendar/Tasks/Contacts/Drive/Allcare/WhatsApp. Agora esse trabalho roda por conta própria,
disparado por um webhook real (`on_gmail_watch_notification`, via `users.watch()`) ou por uma
rede de segurança de baixa frequência (`gmail_sync_safety_net`, sempre ativa independente do
webhook) -- `run_full_sync` não toca mais Gmail.

Os 3 disparadores decorados (`on_gmail_watch_notification`, `gmail_sync_safety_net`,
`renovar_gmail_watch_diario`) são mantidos deliberadamente finos (mesmo padrão já usado por
`scheduled_sync`/`on_sync_request`, que também não têm teste direto): toda a lógica real vive em
`_executar_sync_gmail_com_lock`/`gmail_watch_habilitado`/`renovar_gmail_watch`, testadas abaixo
como funções puras. Os disparadores são testados via `inspect.unwrap` (mesma técnica já usada em
test_hermes_tools.py para `@https_fn.on_call`) -- os decorators de pubsub/scheduler do Firebase
Functions envolvem a função original numa camada que exige um CloudEvent bem formado; unwrap
devolve a função original diretamente chamável.
"""

from __future__ import annotations

import inspect
import unittest
from unittest import mock

import main


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
        return _Snap(self._store.get(self._key))

    def set(self, data, merge=False):
        if merge and self._key in self._store:
            self._store[self._key].update(data)
        else:
            self._store[self._key] = dict(data)

    def update(self, data):
        self._store.setdefault(self._key, {}).update(data)

    def delete(self):
        self._store.pop(self._key, None)


class _Collection:
    def __init__(self, store):
        self._store = store

    def document(self, key):
        return _DocRef(self._store, key)

    def stream(self):
        return []


class _Db:
    def __init__(self):
        self._collections: dict[str, dict] = {}

    def collection(self, name):
        return _Collection(self._collections.setdefault(name, {}))

    def doc_data(self, collection, key):
        return self._collections.get(collection, {}).get(key)


class TestLocksComDocIdCustomizado(unittest.TestCase):
    """`acquire_sync_lock`/`release_sync_lock` ganharam `lock_doc_id` (24/09/2026) para o
    sync de Gmail ter um lock próprio, nunca o do run_full_sync -- uma rodada geral de até
    15min não pode travar a reação a um e-mail novo, nem vice-versa."""

    def test_lock_padrao_preserva_comportamento_atual(self):
        db = _Db()
        self.assertTrue(main.acquire_sync_lock(db, "run-1"))
        self.assertFalse(main.acquire_sync_lock(db, "run-2"))
        main.release_sync_lock(db, "run-1")
        self.assertTrue(main.acquire_sync_lock(db, "run-3"))

    def test_lock_do_gmail_e_independente_do_lock_principal(self):
        db = _Db()
        self.assertTrue(main.acquire_sync_lock(db, "run-1"))
        self.assertTrue(main.acquire_sync_lock(db, "gmail-1", lock_doc_id=main.GMAIL_SYNC_LOCK_DOC_ID))
        # O lock geral ainda ocupado por run-1 não é afetado pelo lock do Gmail.
        self.assertFalse(main.acquire_sync_lock(db, "run-2"))
        main.release_sync_lock(db, "gmail-1", lock_doc_id=main.GMAIL_SYNC_LOCK_DOC_ID)
        self.assertIsNone(db.doc_data("system", main.GMAIL_SYNC_LOCK_DOC_ID))
        self.assertIsNotNone(db.doc_data("system", main.SYNC_LOCK_DOC_ID))

    def test_release_so_libera_se_o_owner_bate(self):
        db = _Db()
        main.acquire_sync_lock(db, "dono-real", lock_doc_id=main.GMAIL_SYNC_LOCK_DOC_ID)
        main.release_sync_lock(db, "outro-dono", lock_doc_id=main.GMAIL_SYNC_LOCK_DOC_ID)
        self.assertIsNotNone(db.doc_data("system", main.GMAIL_SYNC_LOCK_DOC_ID))


class TestSyncGmailWork(unittest.TestCase):
    def test_chama_as_tres_etapas_na_ordem_com_os_argumentos_certos(self):
        chamadas = []
        db, gs, sync_ref, logs = object(), object(), object(), []
        with mock.patch("main.sync_pix_emails", side_effect=lambda *a: chamadas.append("pix")) as m_pix, \
             mock.patch("main.sync_boletos_gmail", side_effect=lambda *a: chamadas.append("boletos")) as m_bol, \
             mock.patch("email_action_linker.link_emails_to_actions", side_effect=lambda *a: chamadas.append("link")) as m_link:
            main.sync_gmail_work(db, gs, sync_ref, logs)
        m_pix.assert_called_once_with(gs, sync_ref, logs)
        m_bol.assert_called_once_with(gs, sync_ref, logs)
        m_link.assert_called_once_with(db, gs, sync_ref, logs)
        self.assertEqual(chamadas, ["pix", "boletos", "link"])

    def test_falha_no_vinculo_email_acao_e_absorvida_sem_derrubar(self):
        db = _Db()
        sync_ref = db.collection("system").document("gmail_sync")
        logs = []
        with mock.patch("main.sync_pix_emails"), mock.patch("main.sync_boletos_gmail"), \
             mock.patch("main.emit_notification_backend"), \
             mock.patch("email_action_linker.link_emails_to_actions", side_effect=RuntimeError("boom")):
            main.sync_gmail_work(db, object(), sync_ref, logs)  # não deve levantar
        self.assertTrue(any("EMAIL-LINK" in linha for linha in logs))

    def test_falha_no_sync_pix_propaga_para_o_chamador(self):
        """sync_pix_emails/sync_boletos_gmail não têm try/except próprio dentro de
        sync_gmail_work -- propagam para quem chamou (_executar_sync_gmail_com_lock ou
        run_full_sync), que decide o status geral do ciclo. Mesma semântica de antes, quando
        estavam soltos dentro de run_full_sync."""
        with mock.patch("main.sync_pix_emails", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                main.sync_gmail_work(object(), object(), object(), [])


class TestGmailWatchHabilitado(unittest.TestCase):
    def test_desligado_por_padrao(self):
        self.assertFalse(main.gmail_watch_habilitado(_Db()))

    def test_ligado_quando_configurado(self):
        db = _Db()
        db.collection("system").document("settings").set({"gmail_watch": {"enabled": True}})
        self.assertTrue(main.gmail_watch_habilitado(db))


class TestRenovarGmailWatch(unittest.TestCase):
    def _db_habilitado(self):
        db = _Db()
        db.collection("system").document("settings").set({"gmail_watch": {"enabled": True}})
        return db

    def test_desligado_nao_chama_a_api(self):
        db = _Db()
        gs = mock.Mock()
        res = main.renovar_gmail_watch(db, gs)
        self.assertEqual(res, {"habilitado": False, "renovado": False})
        gs.users.assert_not_called()

    def test_ligado_registra_o_watch_e_grava_estado(self):
        db = self._db_habilitado()
        gs = mock.Mock()
        gs.users.return_value.watch.return_value.execute.return_value = {
            "historyId": "12345", "expiration": "1999999999000",
        }
        with mock.patch.dict("os.environ", {"GCLOUD_PROJECT": "gestao-hermes-teste"}):
            res = main.renovar_gmail_watch(db, gs)
        self.assertTrue(res["renovado"])
        _, kwargs = gs.users.return_value.watch.call_args
        self.assertEqual(kwargs["userId"], "me")
        self.assertEqual(
            kwargs["body"]["topicName"],
            "projects/gestao-hermes-teste/topics/gmail-push-hermes",
        )
        estado = db.doc_data("system", main.GMAIL_WATCH_DOC_ID)
        # A renovação grava em campo próprio; `history_id` é o cursor do webhook (PR #355).
        self.assertEqual(estado["watch_history_id"], "12345")
        self.assertNotIn("history_id", estado)
        self.assertTrue(estado["watch_active"])

    def test_falha_na_api_marca_watch_active_false_sem_levantar(self):
        db = self._db_habilitado()
        gs = mock.Mock()
        gs.users.return_value.watch.return_value.execute.side_effect = RuntimeError("gmail fora do ar")
        res = main.renovar_gmail_watch(db, gs)  # não deve levantar
        self.assertFalse(res["renovado"])
        estado = db.doc_data("system", main.GMAIL_WATCH_DOC_ID)
        self.assertFalse(estado["watch_active"])


class TestExecutarSyncGmailComLock(unittest.TestCase):
    def test_sucesso_grava_status_completed_e_libera_lock(self):
        db = _Db()
        with mock.patch("main.sync_gmail_work") as m_work:
            res = main._executar_sync_gmail_com_lock(db, object(), trigger="safety_net")
        self.assertTrue(res["executado"])
        m_work.assert_called_once()
        self.assertEqual(db.doc_data("system", "gmail_sync")["status"], "completed")
        self.assertIsNone(db.doc_data("system", main.GMAIL_SYNC_LOCK_DOC_ID))

    def test_trigger_webhook_atualiza_last_notification_at(self):
        db = _Db()
        with mock.patch("main.sync_gmail_work"):
            main._executar_sync_gmail_com_lock(db, object(), trigger="webhook")
        self.assertIn("last_notification_at", db.doc_data("system", main.GMAIL_WATCH_DOC_ID))

    def test_trigger_safety_net_nao_mexe_no_estado_do_watch(self):
        db = _Db()
        with mock.patch("main.sync_gmail_work"):
            main._executar_sync_gmail_com_lock(db, object(), trigger="safety_net")
        self.assertIsNone(db.doc_data("system", main.GMAIL_WATCH_DOC_ID))

    def test_lock_ja_ocupado_nao_chama_sync_gmail_work(self):
        db = _Db()
        main.acquire_sync_lock(db, "outra-rodada", lock_doc_id=main.GMAIL_SYNC_LOCK_DOC_ID)
        with mock.patch("main.sync_gmail_work") as m_work:
            res = main._executar_sync_gmail_com_lock(db, object(), trigger="webhook")
        m_work.assert_not_called()
        self.assertFalse(res["executado"])

    def test_falha_no_sync_gmail_work_e_absorvida_e_libera_o_lock(self):
        db = _Db()
        with mock.patch("main.sync_gmail_work", side_effect=RuntimeError("boom")), \
             mock.patch("main.emit_notification_backend"):
            res = main._executar_sync_gmail_com_lock(db, object(), trigger="safety_net")  # não deve levantar
        self.assertIn("erro", res)
        self.assertEqual(db.doc_data("system", "gmail_sync")["status"], "error")
        self.assertIsNone(db.doc_data("system", main.GMAIL_SYNC_LOCK_DOC_ID))


class TestDisparadoresFinos(unittest.TestCase):
    """Os 3 disparadores decorados só delegam -- ver docstring do módulo sobre por que são
    testados via inspect.unwrap em vez de um CloudEvent/ScheduledEvent real."""

    def test_on_gmail_watch_notification_desligado_nao_executa(self):
        db = _Db()
        fn = inspect.unwrap(main.on_gmail_watch_notification)
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.get_gmail_service") as m_gs, \
             mock.patch("main._executar_sync_gmail_com_lock") as m_exec:
            fn(mock.Mock())
        m_gs.assert_not_called()
        m_exec.assert_not_called()

    def test_on_gmail_watch_notification_ligado_dispara_com_trigger_webhook(self):
        db = _Db()
        db.collection("system").document("settings").set({"gmail_watch": {"enabled": True}})
        fn = inspect.unwrap(main.on_gmail_watch_notification)
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.get_gmail_service", return_value="gs-fake"), \
             mock.patch("main._executar_sync_gmail_com_lock") as m_exec:
            fn(mock.Mock())
        m_exec.assert_called_once_with(db, "gs-fake", trigger="webhook")

    def test_on_gmail_watch_notification_credencial_revogada_nao_derruba_a_funcao(self):
        """Achado da 1ª rodada de revisão adversarial (24/09/2026): get_gmail_service() era
        chamado como argumento cru, fora de qualquer try/except -- uma GoogleAuthRevokedError
        levantava ANTES de _executar_sync_gmail_com_lock começar, virando um crash cru da
        função na plataforma em vez do status de erro gracioso que o resto do pipeline já dá.
        Achado da 2ª rodada: os testes desta classe usavam RuntimeError genérico, que NÃO bate
        em is_google_invalid_grant_error -- provavam só "não derruba", nunca o efeito real de
        marcar system/google_credentials.auth_status=reauth_required. Usa GoogleAuthRevokedError
        de verdade e confere o efeito, não só a ausência de exceção."""
        db = _Db()
        db.collection("system").document("settings").set({"gmail_watch": {"enabled": True}})
        fn = inspect.unwrap(main.on_gmail_watch_notification)
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.get_gmail_service", side_effect=main.GoogleAuthRevokedError("token has been expired or revoked")), \
             mock.patch("main._executar_sync_gmail_com_lock") as m_exec:
            fn(mock.Mock())  # não deve levantar
        m_exec.assert_not_called()
        self.assertEqual(
            db.doc_data("system", "google_credentials")["auth_status"], "reauth_required"
        )

    def test_gmail_sync_safety_net_roda_mesmo_com_webhook_desligado(self):
        db = _Db()  # gmail_watch.enabled ausente -> False
        fn = inspect.unwrap(main.gmail_sync_safety_net)
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.get_gmail_service", return_value="gs-fake"), \
             mock.patch("main._executar_sync_gmail_com_lock") as m_exec:
            fn(mock.Mock())
        m_exec.assert_called_once_with(db, "gs-fake", trigger="safety_net")

    def test_gmail_sync_safety_net_credencial_revogada_nao_derruba_a_funcao(self):
        db = _Db()
        fn = inspect.unwrap(main.gmail_sync_safety_net)
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.get_gmail_service", side_effect=main.GoogleAuthRevokedError("token has been expired or revoked")), \
             mock.patch("main._executar_sync_gmail_com_lock") as m_exec:
            fn(mock.Mock())  # não deve levantar
        m_exec.assert_not_called()
        self.assertEqual(
            db.doc_data("system", "google_credentials")["auth_status"], "reauth_required"
        )

    def test_renovar_gmail_watch_diario_delega_para_renovar_gmail_watch(self):
        fn = inspect.unwrap(main.renovar_gmail_watch_diario)
        with mock.patch("main.get_db", return_value="db-fake"), \
             mock.patch("main.get_gmail_service", return_value="gs-fake"), \
             mock.patch("main.renovar_gmail_watch") as m_renovar:
            fn(mock.Mock())
        m_renovar.assert_called_once_with("db-fake", "gs-fake")

    def test_renovar_gmail_watch_diario_credencial_revogada_nao_derruba_a_funcao(self):
        db = _Db()
        fn = inspect.unwrap(main.renovar_gmail_watch_diario)
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.get_gmail_service", side_effect=main.GoogleAuthRevokedError("token has been expired or revoked")), \
             mock.patch("main.renovar_gmail_watch") as m_renovar:
            fn(mock.Mock())  # não deve levantar
        m_renovar.assert_not_called()
        self.assertEqual(
            db.doc_data("system", "google_credentials")["auth_status"], "reauth_required"
        )


class TestRecursosDoWebhookIguaisAoSafetyNet(unittest.TestCase):
    """Os dois disparadores rodam o MESMO sync_gmail_work (~3 min: sync_pix_emails refaz uma
    chamada messages.modify por e-mail de Pix desde fev/2026). O webhook foi ao ar sem
    timeout_sec/memory (padrão de 60 s/256 MB) e a invocação foi cortada em 59,993 s: gmail_sync
    ficou preso em 'processing' e o lock preso até SYNC_LOCK_STALE_SECONDS (achado da
    verificação de ponta a ponta em produção, 24/09/2026). Lê o endpoint que o Firebase publica
    (__firebase_endpoint__), o mesmo objeto que o deploy usa -- não o decorador por texto."""

    def test_webhook_tem_o_mesmo_timeout_e_memoria_do_safety_net(self):
        webhook = main.on_gmail_watch_notification.__firebase_endpoint__
        safety_net = main.gmail_sync_safety_net.__firebase_endpoint__
        self.assertEqual(webhook.timeoutSeconds, safety_net.timeoutSeconds)
        self.assertEqual(webhook.availableMemoryMb, safety_net.availableMemoryMb)

    def test_webhook_nao_cai_no_padrao_de_60s(self):
        webhook = main.on_gmail_watch_notification.__firebase_endpoint__
        # Sem timeout_sec o Firebase deixa um Sentinel (não None) no lugar do número.
        self.assertIsInstance(
            webhook.timeoutSeconds, int, "timeout_sec não definido: cai no padrão de 60 s"
        )
        self.assertGreater(webhook.timeoutSeconds, 60)


class TestRunFullSyncNaoTocaGmail(unittest.TestCase):
    """run_full_sync não deve mais chamar sync_pix_emails/sync_boletos_gmail/
    link_emails_to_actions (extraídos para sync_gmail_work, 24/09/2026) -- mas continua
    chamando sync_allcare_portal_bills (scraping de portal externo, sem webhook possível por
    definição) e todo o resto do ciclo (Calendar, Tasks, Contacts, Drive, vínculo de reuniões,
    detectores, WhatsApp)."""

    def test_run_full_sync_pula_gmail_mas_mantem_o_resto(self):
        db = _Db()
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.get_tasks_service", return_value="ts"), \
             mock.patch("main.get_gmail_service", return_value="gs"), \
             mock.patch("main.get_calendar_service", return_value="cs"), \
             mock.patch("main.sync_google_calendar", return_value=[]) as m_cal, \
             mock.patch("main.sync_google_tasks_push") as m_tasks_push, \
             mock.patch("main.sync_google_tasks_pull") as m_tasks_pull, \
             mock.patch("main.sync_pix_emails") as m_pix, \
             mock.patch("main.sync_google_contacts_internal") as m_contacts, \
             mock.patch("main.executar_monitoramento_acervo_global") as m_acervo, \
             mock.patch("main.sync_boletos_gmail") as m_boletos, \
             mock.patch("main.sync_allcare_portal_bills") as m_allcare, \
             mock.patch("email_action_linker.link_emails_to_actions") as m_link, \
             mock.patch("email_action_linker.link_calendar_events_to_actions") as m_cal_link, \
             mock.patch("atencao.detectar_aguardando_terceiro_vencido") as m_atencao, \
             mock.patch("resposta_esperada.reconstruir_indice", return_value={"gravado": False}) as m_resp, \
             mock.patch("whatsapp_ingest.triage_whatsapp_messages") as m_wa:
            resultado = main.run_full_sync("teste")

        self.assertTrue(resultado)
        m_pix.assert_not_called()
        m_boletos.assert_not_called()
        m_link.assert_not_called()
        m_allcare.assert_called_once()
        m_cal.assert_called_once()
        m_tasks_push.assert_called_once()
        m_tasks_pull.assert_called_once()
        m_contacts.assert_called_once()
        m_acervo.assert_called_once()
        m_cal_link.assert_called_once()
        m_atencao.assert_called_once()
        m_resp.assert_called_once()
        m_wa.assert_called_once()


if __name__ == "__main__":
    unittest.main()
