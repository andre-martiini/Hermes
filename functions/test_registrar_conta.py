"""`registrar_item_financeiro_v2` grava de qual conta saiu o gasto avulso.

Só `conta: "picpay"` entra no teto do mês (gasto_avulso). Conta fora da lista
é recusada em vez de gravada: um "PicPay2" ficaria fora do teto em silêncio.
"""
import json
import unittest
from unittest.mock import MagicMock

from tools.telegram_extended import execute


def _registrar(**extra):
    db = MagicMock()
    ref = db.collection.return_value.document.return_value
    ref.id = "novo"
    slots = {"tipo": "transacao_avulsa", "descricao": "Mercado", "valor": 50.0,
             "categoria": "Geral", "data": "2026-11-03", **extra}
    return execute("registrar_item_financeiro_v2", slots, db), ref


class RegistrarConta(unittest.TestCase):
    def test_grava_a_conta_normalizada(self):
        resultado, ref = _registrar(conta=" PicPay ")
        self.assertTrue(json.loads(resultado)["success"])
        self.assertEqual(ref.set.call_args.args[0]["conta"], "picpay")

    def test_sem_conta_nao_grava_o_campo(self):
        _, ref = _registrar()
        self.assertNotIn("conta", ref.set.call_args.args[0])

    def test_conta_desconhecida_e_recusada(self):
        resultado, ref = _registrar(conta="nubank")
        self.assertTrue(resultado.startswith("ERRO|"))
        ref.set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
