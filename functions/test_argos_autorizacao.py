"""Testes para o mecanismo de autorização via Telegram do conector Claude-Argos.

Mesmo padrão de test_outbox_aprovacao.py: mock simples de Firestore, sem rede
real e sem depender de emulador. Cobre:
- Lógica pura (transição de decisão, montagem de card)
- Ciclo solicitar -> decidir (aprovar/recusar) -> consumir
- Proteção contra toque duplo no callback do Telegram (already_decided)
- Proteção contra uso duplo da autorização no lado do Argos (already_used)
- Expiração preguiçosa de solicitação vencida sem decisão
"""

import datetime
from datetime import timezone, timedelta
import unittest
from unittest import mock

import argos_autorizacao as aa


# --------------------------------------------------------------------------
# Mock simples de Firestore (mesmo padrão de test_outbox_aprovacao.py)
# --------------------------------------------------------------------------

class _MockDocSnap:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRef:
    def __init__(self, col, doc_id: str):
        self.col = col
        self.id = doc_id

    def get(self, transaction=None):
        data = self.col._docs.get(self.id)
        return _MockDocSnap(self.id, data)

    def set(self, data, merge=False):
        if merge and self.id in self.col._docs:
            self.col._docs[self.id].update(data)
        else:
            self.col._docs[self.id] = dict(data)

    def update(self, data):
        if self.id not in self.col._docs:
            raise KeyError(f"Doc {self.id} does not exist")
        self.col._docs[self.id].update(data)


class _MockCollection:
    def __init__(self, db, name: str):
        self.db = db
        self.name = name
        self._docs: dict[str, dict] = {}
        self._id_counter = 1

    def document(self, doc_id: str | None = None):
        if not doc_id:
            doc_id = f"mock-doc-{self._id_counter}"
            self._id_counter += 1
        return _MockDocRef(self, doc_id)


class _MockTransaction:
    def __init__(self, db):
        self.db = db
        self._id = b"mock-tx-id"
        self._read_only = False
        self._max_attempts = 5

    def get(self, ref):
        return ref.get(transaction=self)

    def update(self, ref, data):
        ref.update(data)


class _MockDb:
    def __init__(self):
        self._cols: dict[str, _MockCollection] = {}

    def collection(self, name: str):
        if name not in self._cols:
            self._cols[name] = _MockCollection(self, name)
        return self._cols[name]

    def transaction(self):
        return _MockTransaction(self)


# --------------------------------------------------------------------------
# Lógica pura
# --------------------------------------------------------------------------

class TestLogicaPura(unittest.TestCase):
    def test_validar_transicao_decisao(self):
        ok, msg = aa.validar_transicao_decisao(aa.STATUS_AGUARDANDO)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

        for status in [aa.STATUS_APROVADO, aa.STATUS_RECUSADO, aa.STATUS_EXPIRADO, aa.STATUS_USADO]:
            ok, msg = aa.validar_transicao_decisao(status)
            self.assertFalse(ok)
            self.assertIn("já decidida", msg)

        ok, msg = aa.validar_transicao_decisao(None)
        self.assertFalse(ok)
        self.assertIn("não encontrada", msg)

    def test_montar_card_telegram_autorizacao(self):
        corpo, botoes = aa.montar_card_telegram_autorizacao(
            tipo="approve-plan",
            sistema_id="mapa-de-precos-para-contratacoes-publicas",
            demanda_id="DEV-2026-0001",
            resumo="Aprovar plano de testes automatizados para privateEvidence.ts",
            solicitacao_id="sol-1",
        )
        self.assertIn("Aprovar plano", corpo)
        self.assertIn("mapa-de-precos-para-contratacoes-publicas", corpo)
        self.assertIn("DEV-2026-0001", corpo)
        self.assertIn("testes automatizados", corpo)

        self.assertEqual(len(botoes), 1)
        row = botoes[0]
        self.assertEqual(len(row), 2)
        self.assertEqual(row[0]["callback_data"], "argos_auth:sol-1:aprovar")
        self.assertEqual(row[1]["callback_data"], "argos_auth:sol-1:recusar")

    def test_montar_card_escapa_html(self):
        corpo, _ = aa.montar_card_telegram_autorizacao("enqueue-job", "s", "d", "<script>x</script>", "sol-2")
        self.assertNotIn("<script>", corpo)


# --------------------------------------------------------------------------
# solicitar_autorizacao
# --------------------------------------------------------------------------

class TestSolicitarAutorizacao(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()

    def test_valida_campos_obrigatorios(self):
        self.assertIn("erro", aa.solicitar_autorizacao(self.db, "tipo-invalido", "s", "d", "r"))
        self.assertIn("erro", aa.solicitar_autorizacao(self.db, "approve-plan", "", "d", "r"))
        self.assertIn("erro", aa.solicitar_autorizacao(self.db, "approve-plan", "s", "", "r"))
        self.assertIn("erro", aa.solicitar_autorizacao(self.db, "approve-plan", "s", "d", ""))

    def test_cria_solicitacao_e_envia_card(self):
        with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value=555) as mock_send, \
             mock.patch("hermes_core_logic._get_telegram_token", return_value="tok"), \
             mock.patch("main._resolve_default_telegram_chat_id", return_value="123"):
            res = aa.solicitar_autorizacao(self.db, "approve-plan", "sistema-x", "DEV-1", "Resumo do que muda")
        self.assertEqual(res["status"], aa.STATUS_AGUARDANDO)
        self.assertTrue(res["telegram_notificado"])
        mock_send.assert_called_once()
        doc = self.db.collection(aa.COLLECTION)._docs[res["solicitacao_id"]]
        self.assertEqual(doc["status"], aa.STATUS_AGUARDANDO)
        self.assertEqual(doc["telegram_message_id"], 555)

    def test_cria_solicitacao_mesmo_sem_telegram_configurado(self):
        with mock.patch("hermes_core_logic._get_telegram_token", return_value=None):
            res = aa.solicitar_autorizacao(self.db, "approve-plan", "sistema-x", "DEV-1", "Resumo")
        self.assertEqual(res["status"], aa.STATUS_AGUARDANDO)
        self.assertFalse(res["telegram_notificado"])
        self.assertIn("solicitacao_id", res)


# --------------------------------------------------------------------------
# decidir_autorizacao (callback do Telegram)
# --------------------------------------------------------------------------

class TestDecidirAutorizacao(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()
        self.col = self.db.collection(aa.COLLECTION)
        self.tx_patch = mock.patch("firebase_admin.firestore.transactional", side_effect=lambda fn: fn)
        self.tx_patch.start()
        self.addCleanup(self.tx_patch.stop)

    def test_aprovar_transiciona_e_edita_mensagem(self):
        self.col._docs["sol-1"] = {
            "tipo": "approve-plan", "sistema_id": "s", "demanda_id": "DEV-1",
            "status": aa.STATUS_AGUARDANDO, "telegram_message_id": 999,
        }
        with mock.patch("core.telegram_api.edit_message", return_value=True) as mock_edit:
            res = aa.decidir_autorizacao(self.db, "sol-1", "aprovar", telegram_token="tok", chat_id="123")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["decisao"], aa.STATUS_APROVADO)
        self.assertEqual(self.col._docs["sol-1"]["status"], aa.STATUS_APROVADO)
        mock_edit.assert_called_once()
        self.assertIn("Autorizado", mock_edit.call_args[0][3])

    def test_recusar_transiciona(self):
        self.col._docs["sol-2"] = {
            "tipo": "enqueue-job", "sistema_id": "s", "demanda_id": "DEV-2", "status": aa.STATUS_AGUARDANDO,
        }
        res = aa.decidir_autorizacao(self.db, "sol-2", "recusar")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(self.col._docs["sol-2"]["status"], aa.STATUS_RECUSADO)

    def test_toque_duplo_nao_muda_decisao(self):
        self.col._docs["sol-3"] = {"tipo": "approve-plan", "status": aa.STATUS_AGUARDANDO}
        res1 = aa.decidir_autorizacao(self.db, "sol-3", "aprovar")
        self.assertEqual(res1["status"], "ok")
        res2 = aa.decidir_autorizacao(self.db, "sol-3", "recusar")
        self.assertEqual(res2["status"], "already_decided")
        # a segunda tentativa (recusar) não sobrescreve a primeira decisão (aprovado)
        self.assertEqual(self.col._docs["sol-3"]["status"], aa.STATUS_APROVADO)

    def test_solicitacao_inexistente(self):
        res = aa.decidir_autorizacao(self.db, "nao-existe", "aprovar")
        self.assertEqual(res["status"], "not_found")

    def test_decisao_invalida(self):
        self.col._docs["sol-4"] = {"status": aa.STATUS_AGUARDANDO}
        res = aa.decidir_autorizacao(self.db, "sol-4", "talvez")
        self.assertEqual(res["status"], "erro")


# --------------------------------------------------------------------------
# consultar_autorizacao
# --------------------------------------------------------------------------

class TestConsultarAutorizacao(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()
        self.col = self.db.collection(aa.COLLECTION)

    def test_consulta_simples(self):
        self.col._docs["sol-1"] = {
            "tipo": "approve-plan", "sistema_id": "s", "demanda_id": "d", "resumo": "r",
            "status": aa.STATUS_APROVADO,
        }
        res = aa.consultar_autorizacao(self.db, "sol-1")
        self.assertEqual(res["status"], aa.STATUS_APROVADO)
        self.assertEqual(res["sistema_id"], "s")

    def test_inexistente(self):
        res = aa.consultar_autorizacao(self.db, "nao-existe")
        self.assertEqual(res["status"], "not_found")

    def test_expira_preguicosamente_solicitacao_vencida(self):
        vencida_em = datetime.datetime.now(timezone.utc) - timedelta(minutes=1)
        self.col._docs["sol-2"] = {"status": aa.STATUS_AGUARDANDO, "expira_em": vencida_em}
        res = aa.consultar_autorizacao(self.db, "sol-2")
        self.assertEqual(res["status"], aa.STATUS_EXPIRADO)
        self.assertEqual(self.col._docs["sol-2"]["status"], aa.STATUS_EXPIRADO)

    def test_nao_expira_solicitacao_dentro_do_prazo(self):
        futuro = datetime.datetime.now(timezone.utc) + timedelta(minutes=10)
        self.col._docs["sol-3"] = {"status": aa.STATUS_AGUARDANDO, "expira_em": futuro}
        res = aa.consultar_autorizacao(self.db, "sol-3")
        self.assertEqual(res["status"], aa.STATUS_AGUARDANDO)


# --------------------------------------------------------------------------
# consumir_autorizacao (uso único)
# --------------------------------------------------------------------------

class TestConsumirAutorizacao(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()
        self.col = self.db.collection(aa.COLLECTION)
        self.tx_patch = mock.patch("firebase_admin.firestore.transactional", side_effect=lambda fn: fn)
        self.tx_patch.start()
        self.addCleanup(self.tx_patch.stop)

    def test_consome_autorizacao_aprovada(self):
        self.col._docs["sol-1"] = {"status": aa.STATUS_APROVADO}
        res = aa.consumir_autorizacao(self.db, "sol-1")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(self.col._docs["sol-1"]["status"], aa.STATUS_USADO)

    def test_segunda_chamada_nao_reconsome(self):
        self.col._docs["sol-1"] = {"status": aa.STATUS_APROVADO}
        aa.consumir_autorizacao(self.db, "sol-1")
        res2 = aa.consumir_autorizacao(self.db, "sol-1")
        self.assertEqual(res2["status"], "already_used")

    def test_recusa_dentro_da_prazo_nao_pode_ser_consumida(self):
        self.col._docs["sol-2"] = {"status": aa.STATUS_RECUSADO}
        res = aa.consumir_autorizacao(self.db, "sol-2")
        self.assertEqual(res["status"], "not_approved")

    def test_aguardando_decisao_nao_pode_ser_consumida(self):
        self.col._docs["sol-3"] = {"status": aa.STATUS_AGUARDANDO}
        res = aa.consumir_autorizacao(self.db, "sol-3")
        self.assertEqual(res["status"], "not_approved")

    def test_inexistente(self):
        res = aa.consumir_autorizacao(self.db, "nao-existe")
        self.assertEqual(res["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
