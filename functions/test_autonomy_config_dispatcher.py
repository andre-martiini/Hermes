"""Testes de `autonomy/config_dispatcher.py` (P08): modo e orçamento persistidos, fail-closed."""

import unittest

from autonomy import config_dispatcher as cd
from autonomy.dispatcher import ModoDispatcher


class _Snap:
    def __init__(self, dados):
        self._d = dados
        self.exists = dados is not None

    def to_dict(self):
        return dict(self._d) if self._d is not None else {}


class _Doc:
    def __init__(self, dados, erro=None):
        self.dados, self.erro = dados, erro

    def get(self):
        if self.erro:
            raise self.erro
        return _Snap(self.dados)


class _Db:
    def __init__(self, dados=None, erro=None):
        self.doc, self.vistos = _Doc(dados, erro), []

    def collection(self, nome):
        self.vistos.append(nome)
        return self

    def document(self, nome):
        self.vistos.append(nome)
        return self.doc


class ConfigDispatcherTest(unittest.TestCase):
    def test_ativo_com_orcamento(self):
        c = cd.ler_config_dispatcher(_Db({"modo": "ativo", "despachos_restantes": 5}))
        self.assertEqual((c.modo, c.despachos_restantes, c.motivo), (ModoDispatcher.ATIVO, 5, "ok"))

    def test_caminho_do_documento(self):
        db = _Db({"modo": "off"})
        cd.ler_config_dispatcher(db)
        self.assertEqual(db.vistos, ["configuracoes", "autonomia_dispatcher"])

    def test_ativo_sem_orcamento_ou_invalido(self):
        for bruto in (None, -1, True, "3", 2.0):
            d = {"modo": "ativo"} if bruto is None else {"modo": "ativo", "despachos_restantes": bruto}
            c = cd.interpretar_config(d)
            self.assertIsNone(c.despachos_restantes, bruto)
            self.assertEqual(c.motivo, "orcamento_ausente_ou_invalido")

    def test_ativo_orcamento_zero(self):
        c = cd.interpretar_config({"modo": "ativo", "despachos_restantes": 0})
        self.assertEqual(c.despachos_restantes, 0)

    def test_shadow_nao_carrega_orcamento(self):
        c = cd.interpretar_config({"modo": "shadow", "despachos_restantes": 9})
        self.assertEqual((c.modo, c.despachos_restantes), (ModoDispatcher.SHADOW, None))

    def test_modo_invalido_ou_ausente_vira_off(self):
        for d in ({"modo": "ligado"}, {"modo": 1}, {}, None, [], "ativo"):
            self.assertIs(cd.interpretar_config(d).modo, ModoDispatcher.OFF, d)

    def test_documento_ausente_e_erro_de_leitura(self):
        self.assertIs(cd.ler_config_dispatcher(_Db(None)).modo, ModoDispatcher.OFF)
        c = cd.ler_config_dispatcher(_Db(erro=RuntimeError("boom")))
        self.assertEqual((c.modo, c.motivo), (ModoDispatcher.OFF, "config_indisponivel"))


if __name__ == "__main__":
    unittest.main()
