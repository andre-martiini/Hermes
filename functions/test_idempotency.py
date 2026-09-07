"""Testes unitários para core/idempotency.py (deduplicação transacional por
chave, com reserva/conclusão separadas).

Cobre o achado do plano de autonomia (P01 passo 4): uma falha real na
verificação transacional nunca pode virar "pode processar" silenciosamente —
a exceção deve propagar para o chamador decidir (ver functions/main.py::
githubWebhook, que responde 503 nesse caso em vez de anotar o evento).

Cobre também o achado do Codex na PR #188: se o commit da reserva for
ambíguo (cliente recebe timeout, mas o Firestore já escreveu o sentinela no
servidor), tratar "documento existe" como "já processado" descartaria o
evento em silêncio numa reentrega, mesmo que o processamento de fato nunca
tenha rodado. A correção separa reserva de conclusão e nunca trata uma
reserva recente sem conclusão como sucesso (True) nem como duplicata
(False) — levanta ReservaEmAndamentoError, reaproveitando o mesmo contrato
de "erro recuperável sem efeito" já usado para falha real de transação.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

import core.idempotency as idem


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
        return _MockDocSnap(self.id, self.col._docs.get(self.id))

    def set(self, data, merge=False):
        if merge and self.id in self.col._docs:
            self.col._docs[self.id].update(data)
        else:
            self.col._docs[self.id] = dict(data)


class _MockCollection:
    def __init__(self):
        self._docs: dict[str, dict] = {}

    def document(self, doc_id: str):
        return _MockDocRef(self, doc_id)


class _MockTransaction:
    def __init__(self):
        self._read_only = False
        self._id = b"mock-tx-id"
        self._max_attempts = 5

    def get(self, doc_ref):
        return doc_ref.get()

    def set(self, doc_ref, data, merge=False):
        doc_ref.set(data, merge=merge)

    def _rollback(self):
        pass

    def _commit(self):
        pass

    def _clean_up(self):
        # Espelha google.cloud.firestore_v1.transaction.Transaction._clean_up:
        # o decorator @firestore.transactional chama isso antes de cada
        # tentativa, então precisa existir para o mock ser um double fiel.
        self._id = None

    def _begin(self, retry_id=None):
        # Espelha Transaction._begin: marca a transação como "em andamento"
        # (in_progress checa self._id is not None) sem round-trip de rede.
        self._id = retry_id or b"mock-tx-id"


class _MockDb:
    def __init__(self):
        self._collections: dict[str, _MockCollection] = {}

    def collection(self, name: str) -> _MockCollection:
        if name not in self._collections:
            self._collections[name] = _MockCollection()
        return self._collections[name]

    def transaction(self):
        return _MockTransaction()


class TestCheckAndRegister(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()

    def test_update_id_vazio_ou_none_e_sempre_novo_sem_tocar_firestore(self):
        self.assertTrue(idem.check_and_register(self.db, None))
        self.assertTrue(idem.check_and_register(self.db, ""))
        # Nenhuma chamada chegou a criar a coleção/documento.
        self.assertEqual(self.db.collection("idempotency")._docs, {})

    def test_chave_nova_registra_como_reservado_e_retorna_true(self):
        resultado = idem.check_and_register(self.db, "delivery-1")
        self.assertTrue(resultado)
        doc = self.db.collection("idempotency")._docs.get("delivery-1")
        self.assertIsNotNone(doc)
        self.assertEqual(doc["status"], idem.STATUS_RESERVADO)
        self.assertIn("reserved_at", doc)
        self.assertIn("expires_at", doc)

    def test_reserva_recente_levanta_reserva_em_andamento_sem_reescrever(self):
        """O ponto central do fix ao achado do Codex: uma reserva recente
        NUNCA vira True (sucesso) nem False (duplicata) — levanta
        ReservaEmAndamentoError, para o chamador nunca responder 200 a um
        evento que não foi processado de verdade."""
        idem.check_and_register(self.db, "delivery-2")
        doc_antes = dict(self.db.collection("idempotency")._docs["delivery-2"])

        with self.assertRaises(idem.ReservaEmAndamentoError):
            idem.check_and_register(self.db, "delivery-2")

        # Nada foi reescrito pela tentativa que encontrou a reserva em pé.
        self.assertEqual(self.db.collection("idempotency")._docs["delivery-2"], doc_antes)

    def test_reserva_expirada_permite_reprocessar(self):
        """Uma reserva sem conclusão, mesmo que exista o documento, não pode
        bloquear reentregas para sempre — só enquanto puder plausivelmente
        estar em andamento."""
        col = self.db.collection("idempotency")
        agora = datetime.now(timezone.utc)
        col._docs["delivery-velha"] = {
            "status": idem.STATUS_RESERVADO,
            "reserved_at": agora - idem.RESERVA_EXPIRA_APOS - timedelta(seconds=1),
        }

        resultado = idem.check_and_register(self.db, "delivery-velha")
        self.assertTrue(resultado)
        # A reserva foi renovada (novo reserved_at), não apagada.
        doc = col._docs["delivery-velha"]
        self.assertEqual(doc["status"], idem.STATUS_RESERVADO)
        self.assertGreater(doc["reserved_at"], agora - idem.RESERVA_EXPIRA_APOS)

    def test_documento_legado_sem_status_e_tratado_como_reserva_expirada(self):
        """Compatibilidade com um sentinela do formato antigo (sem 'status'
        nem 'reserved_at') — não deve travar para sempre nem quebrar."""
        col = self.db.collection("idempotency")
        col._docs["delivery-legado"] = {"expires_at": datetime.now(timezone.utc)}

        resultado = idem.check_and_register(self.db, "delivery-legado")
        self.assertTrue(resultado)

    def test_falha_real_da_transacao_propaga_excecao_sem_registrar(self):
        """Achado do plano (P01 passo 4): erro na verificação nunca vira
        'pode processar' silenciosamente — a exceção deve propagar para o
        chamador decidir (ex.: responder erro HTTP para reentrega)."""

        class _TransacaoQuebrada(_MockTransaction):
            def _begin(self, retry_id=None):
                raise RuntimeError("Firestore indisponível (simulado)")

        class _DbTransacaoQuebrada(_MockDb):
            def transaction(self):
                return _TransacaoQuebrada()

        db_quebrado = _DbTransacaoQuebrada()
        with self.assertRaises(RuntimeError):
            idem.check_and_register(db_quebrado, "delivery-3")

        # Nada foi registrado: nem sucesso nem duplicata, estado inalterado.
        self.assertEqual(db_quebrado.collection("idempotency")._docs, {})

    def test_db_sem_suporte_a_transacao_propaga_excecao(self):
        class _DbSemTransacao:
            def collection(self, name):
                return _MockCollection()

        with self.assertRaises(AttributeError):
            idem.check_and_register(_DbSemTransacao(), "delivery-4")


class TestMarkComplete(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()

    def test_mark_complete_bloqueia_reentrega_mesmo_apos_reserva_expirar(self):
        """O ponto central do fix: uma vez CONCLUÍDO, nem uma reentrega
        muito depois da janela de expiração da reserva deve reprocessar."""
        idem.check_and_register(self.db, "delivery-5")
        idem.mark_complete(self.db, "delivery-5")

        col = self.db.collection("idempotency")
        doc = col._docs["delivery-5"]
        self.assertEqual(doc["status"], idem.STATUS_CONCLUIDO)
        self.assertIn("completed_at", doc)

        # Mesmo "voltando no tempo" a reserva original, o status concluído
        # já vence antes de olhar reserved_at.
        doc["reserved_at"] = datetime.now(timezone.utc) - idem.RESERVA_EXPIRA_APOS * 10

        resultado = idem.check_and_register(self.db, "delivery-5")
        self.assertFalse(resultado)

    def test_mark_complete_de_chave_vazia_nao_toca_firestore(self):
        idem.mark_complete(self.db, None)
        idem.mark_complete(self.db, "")
        self.assertEqual(self.db.collection("idempotency")._docs, {})

    def test_mark_complete_preserva_reserved_at_original(self):
        idem.check_and_register(self.db, "delivery-6")
        doc_com_reserva = dict(self.db.collection("idempotency")._docs["delivery-6"])

        idem.mark_complete(self.db, "delivery-6")
        doc_final = self.db.collection("idempotency")._docs["delivery-6"]
        self.assertEqual(doc_final["reserved_at"], doc_com_reserva["reserved_at"])

    def test_mark_complete_sem_reserva_previa_nao_quebra(self):
        """mark_complete numa chave que nunca passou por check_and_register
        (sem reserva prévia) não deve lançar — cria o documento só com
        status/completed_at. Não é um caminho normal de uso (o chamador
        sempre chama check_and_register antes), mas não pode quebrar."""
        idem.mark_complete(self.db, "delivery-orfa")
        doc = self.db.collection("idempotency")._docs["delivery-orfa"]
        self.assertEqual(doc["status"], idem.STATUS_CONCLUIDO)
        self.assertIn("completed_at", doc)
        self.assertNotIn("reserved_at", doc)


if __name__ == "__main__":
    unittest.main()
