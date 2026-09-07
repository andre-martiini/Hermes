"""Testes unitários para core/idempotency.py (deduplicação transacional por chave).

Cobre o achado do plano de autonomia (P01 passo 4): uma falha real na
verificação transacional nunca pode virar "pode processar" silenciosamente —
a exceção deve propagar para o chamador decidir (ver functions/main.py::
githubWebhook, que responde 503 nesse caso em vez de anotar o evento).
"""

from __future__ import annotations

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

    def test_chave_nova_registra_e_retorna_true(self):
        resultado = idem.check_and_register(self.db, "delivery-1")
        self.assertTrue(resultado)
        doc = self.db.collection("idempotency")._docs.get("delivery-1")
        self.assertIsNotNone(doc)
        self.assertIn("expires_at", doc)

    def test_chave_repetida_retorna_false_sem_reescrever(self):
        idem.check_and_register(self.db, "delivery-2")
        doc_antes = dict(self.db.collection("idempotency")._docs["delivery-2"])

        resultado = idem.check_and_register(self.db, "delivery-2")
        self.assertFalse(resultado)
        self.assertEqual(self.db.collection("idempotency")._docs["delivery-2"], doc_antes)

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


if __name__ == "__main__":
    unittest.main()
