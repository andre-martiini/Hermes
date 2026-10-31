"""Testes de `consumir_orcamento` (P08, passo 11): baixa transacional, tudo ou nada, fail-closed."""

import copy
import unittest

from autonomy import config_dispatcher as cd


class _Snap:
    def __init__(self, dados):
        self._d, self.exists = dados, dados is not None

    def to_dict(self):
        return copy.deepcopy(self._d) if self._d is not None else {}


class _Ref:
    def __init__(self, db):
        self.db = db

    def get(self, transaction=None):
        return _Snap(self.db.dados)


class _Tx:
    def __init__(self, db):
        self.db, self._read_only, self._id, self._max_attempts, self.esc = db, False, b"tx", 5, []

    def update(self, ref, campos):
        self.esc.append(campos)

    def _rollback(self):
        self.esc = []

    def _commit(self):
        for c in self.esc:
            self.db.dados.update(c)
        self.esc = []

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or b"tx"


class _Db:
    def __init__(self, dados, erro=None):
        self.dados, self.erro, self.caminho = dados, erro, []

    def collection(self, n):
        self.caminho.append(n)
        return self

    def document(self, n):
        self.caminho.append(n)
        return _Ref(self)

    def transaction(self):
        if self.erro:
            raise self.erro
        return _Tx(self)


class _DbSemTx:
    def collection(self, n):
        raise AssertionError("não deve tocar o banco")


class ConsumirOrcamentoTest(unittest.TestCase):
    def test_baixa_e_persiste(self):
        db = _Db({"modo": "ativo", "despachos_restantes": 5})
        self.assertEqual(cd.consumir_orcamento(db, 2), 2)
        self.assertEqual(db.dados["despachos_restantes"], 3)
        self.assertEqual(db.caminho, ["configuracoes", "autonomia_dispatcher"])

    def test_padrao_um_e_chega_a_zero_sem_negativar(self):
        db = _Db({"modo": "ativo", "despachos_restantes": 1})
        self.assertEqual(cd.consumir_orcamento(db), 1)
        self.assertEqual(cd.consumir_orcamento(db), 0)
        self.assertEqual(db.dados["despachos_restantes"], 0)

    def test_tudo_ou_nada_se_saldo_insuficiente(self):
        db = _Db({"modo": "ativo", "despachos_restantes": 2})
        self.assertEqual(cd.consumir_orcamento(db, 3), 0)
        self.assertEqual(db.dados["despachos_restantes"], 2)

    def test_so_ativo_consome(self):
        for modo in ("shadow", "off", "ligado", None):
            db = _Db({"modo": modo, "despachos_restantes": 5})
            self.assertEqual(cd.consumir_orcamento(db), 0, modo)
            self.assertEqual(db.dados["despachos_restantes"], 5)

    def test_saldo_invalido_ou_documento_ausente(self):
        for bruto in (None, -1, True, "3", 2.0):
            d = {"modo": "ativo"} if bruto is None else {"modo": "ativo", "despachos_restantes": bruto}
            self.assertEqual(cd.consumir_orcamento(_Db(d)), 0, bruto)
        self.assertEqual(cd.consumir_orcamento(_Db(None)), 0)

    def test_quantidade_invalida_nao_toca_o_banco(self):
        for q in (0, -1, True, 1.0, "1", None):
            self.assertEqual(cd.consumir_orcamento(_DbSemTx(), q), 0, q)

    def test_backend_sem_transacao_e_erro_do_firestore(self):
        self.assertEqual(cd.consumir_orcamento(object()), 0)
        db = _Db({"modo": "ativo", "despachos_restantes": 5}, erro=RuntimeError("boom"))
        self.assertEqual(cd.consumir_orcamento(db), 0)
        self.assertEqual(db.dados["despachos_restantes"], 5)


if __name__ == "__main__":
    unittest.main()


class DevolverOrcamentoTest(unittest.TestCase):
    def test_estorna_apos_baixa(self):
        db = _Db({"modo": "ativo", "despachos_restantes": 5})
        self.assertEqual(cd.consumir_orcamento(db, 2), 2)
        self.assertEqual(cd.devolver_orcamento(db, 2), 2)
        self.assertEqual(db.dados["despachos_restantes"], 5)

    def test_so_ativo_com_saldo_valido_estorna(self):
        for d in ({"modo": "shadow", "despachos_restantes": 5}, {"modo": "ativo"}, {"modo": "ativo", "despachos_restantes": -1}, None):
            db = _Db(d)
            self.assertEqual(cd.devolver_orcamento(db), 0, d)

    def test_quantidade_invalida_ou_sem_transacao_ou_erro(self):
        for ruim in (0, -1, True, "1", 1.0):
            self.assertEqual(cd.devolver_orcamento(_DbSemTx(), ruim), 0)
        self.assertEqual(cd.devolver_orcamento(_DbSemTx()), 0)
        self.assertEqual(cd.devolver_orcamento(_Db({"modo": "ativo", "despachos_restantes": 1}, erro=RuntimeError("x"))), 0)
