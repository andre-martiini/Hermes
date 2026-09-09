"""Testes unitários para functions/core/idempotency.py (P01 passo 4).

Cobre:
- update_id novo é registrado e retorna RESULTADO_NOVO
- update_id já registrado retorna RESULTADO_DUPLICADO sem sobrescrever
- update_id ausente/vazio retorna RESULTADO_NOVO direto (nada a deduplicar)
- Falha de transação ou backend sem suporte a transação NUNCA "permitem
  processamento" silenciosamente -- retornam RESULTADO_ERRO_TRANSACAO /
  RESULTADO_ERRO_CONFIGURACAO, e nenhum documento é escrito nesse caminho.
"""

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
        data = self.col._docs.get(self.id)
        return _MockDocSnap(self.id, data)

    def set(self, data, merge=False):
        if merge and self.id in self.col._docs:
            self.col._docs[self.id].update(data)
        else:
            self.col._docs[self.id] = dict(data)


class _MockCollection:
    def __init__(self, db, name: str):
        self.db = db
        self.name = name
        self._docs: dict[str, dict] = {}

    def document(self, doc_id: str):
        return _MockDocRef(self, doc_id)


class _MockTransaction:
    """Double fiel do protocolo real (google.cloud.firestore_v1.transaction.
    Transaction): implementa _begin/_clean_up/_commit/_rollback/_max_attempts/
    _read_only para que o decorator @firestore.transactional real exercite o
    mesmo caminho de código de produção, mesmo padrão já usado em
    test_outbox_aprovacao.py/test_promocao_autonomia.py/test_agent_requests.py."""

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
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or b"mock-tx-id"


class _MockDB:
    def __init__(self):
        self._collections: dict[str, _MockCollection] = {}

    def collection(self, name: str) -> _MockCollection:
        if name not in self._collections:
            self._collections[name] = _MockCollection(self, name)
        return self._collections[name]

    def transaction(self):
        return _MockTransaction()


class _BrokenMockTransaction(_MockTransaction):
    """Simula falha real de transação (ex.: Firestore indisponível ao iniciar
    a transação). Falha em ``_begin`` -- antes de qualquer leitura/escrita --
    para provar que nenhuma escrita desprotegida acontece como fallback."""

    def _begin(self, retry_id=None):
        raise RuntimeError("Firestore indisponível (simulado)")


class _MockDBTransacaoQuebrada(_MockDB):
    def transaction(self):
        return _BrokenMockTransaction()


class _MockDBSemTransacao:
    """Mock de DB que não implementa .transaction() -- simula um backend sem
    suporte a transação real."""

    def __init__(self, real_db: _MockDB):
        self._real = real_db

    def collection(self, name):
        return self._real.collection(name)


class TestCheckAndRegister(unittest.TestCase):
    def setUp(self):
        self.db = _MockDB()

    def test_update_id_novo_registra_e_retorna_novo(self):
        resultado = idem.check_and_register(self.db, "delivery-1")
        self.assertEqual(resultado, idem.RESULTADO_NOVO)
        doc = self.db.collection("idempotency")._docs.get("delivery-1")
        self.assertIsNotNone(doc)
        self.assertIn("expires_at", doc)

    def test_update_id_repetido_retorna_duplicado_sem_sobrescrever(self):
        idem.check_and_register(self.db, "delivery-2")
        doc_antes = dict(self.db.collection("idempotency")._docs["delivery-2"])

        resultado = idem.check_and_register(self.db, "delivery-2")

        self.assertEqual(resultado, idem.RESULTADO_DUPLICADO)
        doc_depois = self.db.collection("idempotency")._docs["delivery-2"]
        self.assertEqual(doc_antes, doc_depois)

    def test_update_id_ausente_retorna_novo_sem_tocar_o_banco(self):
        self.assertEqual(idem.check_and_register(self.db, None), idem.RESULTADO_NOVO)
        self.assertEqual(idem.check_and_register(self.db, ""), idem.RESULTADO_NOVO)
        self.assertEqual(self.db.collection("idempotency")._docs, {})

    def test_update_id_aceita_int(self):
        resultado = idem.check_and_register(self.db, 12345)
        self.assertEqual(resultado, idem.RESULTADO_NOVO)
        self.assertIn("12345", self.db.collection("idempotency")._docs)


class TestSemFallbackParaProcessamentoSilencioso(unittest.TestCase):
    """Achado do plano P01 passo 4: erro de idempotência em caminho com
    efeito não pode 'permitir processamento' silenciosamente."""

    def test_falha_de_transacao_retorna_erro_nao_novo(self):
        db_quebrado = _MockDBTransacaoQuebrada()
        resultado = idem.check_and_register(db_quebrado, "delivery-falha")
        self.assertEqual(resultado, idem.RESULTADO_ERRO_TRANSACAO)
        self.assertNotEqual(resultado, idem.RESULTADO_NOVO)

    def test_falha_de_transacao_nao_registra_documento(self):
        db_quebrado = _MockDBTransacaoQuebrada()
        idem.check_and_register(db_quebrado, "delivery-falha-2")
        # A escrita nunca chega a acontecer -- _begin falha antes de tudo.
        self.assertEqual(db_quebrado.collection("idempotency")._docs, {})

    def test_sem_suporte_a_transacao_retorna_erro_configuracao_nao_novo(self):
        db_real = _MockDB()
        db_sem_tx = _MockDBSemTransacao(db_real)
        resultado = idem.check_and_register(db_sem_tx, "delivery-sem-tx")
        self.assertEqual(resultado, idem.RESULTADO_ERRO_CONFIGURACAO)
        self.assertNotEqual(resultado, idem.RESULTADO_NOVO)
        self.assertEqual(db_real.collection("idempotency")._docs, {})

    def test_falha_apos_delivery_ja_registrado_no_retry_nao_reprocessa(self):
        """Verifica que uma falha de transação num retry NÃO reabre a porta:
        mesmo que o update_id já esteja registrado, uma falha de infra na
        tentativa seguinte retorna erro (não novo, não duplicado-com-sucesso)
        -- o chamador não deve nunca inferir 'novo' de um erro."""
        db_real = _MockDB()
        idem.check_and_register(db_real, "delivery-3")  # registra normalmente

        db_quebrado = _MockDBTransacaoQuebrada()
        # Mesma coleção/documento já populados, mas agora a transação falha.
        db_quebrado._collections["idempotency"] = db_real.collection("idempotency")

        resultado = idem.check_and_register(db_quebrado, "delivery-3")
        self.assertEqual(resultado, idem.RESULTADO_ERRO_TRANSACAO)


if __name__ == "__main__":
    unittest.main()
