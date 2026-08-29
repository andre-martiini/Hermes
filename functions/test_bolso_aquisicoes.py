"""A regra do bolso de aquisicoes, com os numeros reais do caso que a expos.

A fixture NAO e inventada: e o estado de 29/08/2026, em que a tela mostrava
bicicleta 48,4%, T-Cross 3,9% e os dois ar-condicionados a 100%, enquanto o
`consultar_financas_v2` devolvia 2.827,38, 0, 0 e 2.827,38 — um campo gravado
que so era atualizado quando a meta era editada.

A MESMA fixture esta em `src/utils/bolsoAquisicoes.test.ts`. Se as duas
implementacoes divergirem, um dos dois lados quebra — que e a unica defesa
possivel quando a regra precisa existir em duas linguagens.
"""
import unittest

import bolso_aquisicoes as ba

BOLSO = 3870.97

SETTINGS = {
    "emergencyReserveCurrent": 10000,
    "emergencyReserveTarget": 10000,
    "investmentReserveCurrent": 3870.97,
}

CONTAS = []

METAS = [
    {"id": "bike", "name": "Bicicleta", "targetAmount": 8000, "priority": 1,
     "status": "active", "currentAmount": 0},
    {"id": "ar_quarto", "name": "Ar-condicionado do quarto", "targetAmount": 2000,
     "priority": 3, "status": "active", "currentAmount": 2827.38},
    {"id": "ar_escritorio", "name": "Ar-condicionado do escritorio", "targetAmount": 2000,
     "priority": 4, "status": "active", "currentAmount": 0},
    {"id": "tcross", "name": "T-Cross", "targetAmount": 100000, "priority": 5,
     "status": "active", "currentAmount": 2827.38},
]


class TestOBolso(unittest.TestCase):
    def test_o_bolso_e_a_reserva_de_investimento(self):
        self.assertAlmostEqual(ba.bolso(SETTINGS, CONTAS), BOLSO, places=2)

    def test_poupanca_do_mes_entra_so_com_a_emergencia_completa(self):
        """Poupanca com emergencia incompleta esta indo para a emergencia."""
        contas = [{"category": "Poupança", "amount": 500, "isPaid": True}]
        cheia = ba.bolso(SETTINGS, contas)
        vazia = ba.bolso({**SETTINGS, "emergencyReserveCurrent": 1}, contas)
        self.assertAlmostEqual(cheia, BOLSO + 500, places=2)
        self.assertAlmostEqual(vazia, BOLSO, places=2)

    def test_poupanca_nao_paga_nao_entra(self):
        contas = [{"category": "Poupança", "amount": 500, "isPaid": False}]
        self.assertAlmostEqual(ba.bolso(SETTINGS, contas), BOLSO, places=2)


class TestACoberturaBateComATela(unittest.TestCase):
    """Os quatro numeros que a tela mostrava, e que o MCP contradizia."""

    def _pct(self, meta_id):
        r = ba.resumo(METAS, SETTINGS, CONTAS)
        return next(m["cobertura_pct"] for m in r["metas"] if m["id"] == meta_id)

    def test_bicicleta_48_4(self):
        self.assertEqual(self._pct("bike"), 48.4)

    def test_tcross_3_9(self):
        self.assertEqual(self._pct("tcross"), 3.9)

    def test_os_dois_ar_condicionados_batem_no_teto(self):
        self.assertEqual(self._pct("ar_quarto"), 100.0)
        self.assertEqual(self._pct("ar_escritorio"), 100.0)

    def test_o_valor_gravado_e_ignorado(self):
        """Era ele que divergia; agora nao entra na conta de meta ativa."""
        com_lixo = [{**m, "currentAmount": 99999} for m in METAS]
        r = ba.resumo(com_lixo, SETTINGS, CONTAS)
        self.assertEqual({m["id"]: m["currentAmount"] for m in r["metas"]},
                         {"bike": BOLSO, "ar_quarto": 2000.0,
                          "ar_escritorio": 2000.0, "tcross": BOLSO})

    def test_meta_concluida_preserva_o_que_custou(self):
        """Nao e projecao do bolso de hoje — e o que ela custou quando fechou."""
        concluida = [{"id": "x", "targetAmount": 500, "priority": 1,
                      "status": "completed", "currentAmount": 480}]
        r = ba.resumo(concluida, SETTINGS, CONTAS)
        self.assertEqual(r["metas"][0]["currentAmount"], 480)


class TestAsCoberturasNaoSaoSomaveis(unittest.TestCase):
    """O defeito que dois itens a 100% ao mesmo tempo escondem.

    2.000 + 2.000 = 4.000, e o bolso tem 3.870,97 — faltam 129,03. Com dois
    itens ja engana; com seis ou sete desejos pequenos vira convite a estourar
    o bolso sem perceber.
    """

    def test_os_dois_ar_condicionados_nao_cabem_juntos(self):
        r = ba.resumo(METAS, SETTINGS, CONTAS)
        cabe = {m["id"]: m["cabe_na_fila"] for m in r["metas"]}
        self.assertEqual(cabe["ar_quarto"], False)
        self.assertEqual(cabe["ar_escritorio"], False)

    def test_a_fila_respeita_a_prioridade(self):
        """O unico uso real que o campo `priority` ganha."""
        metas = [
            {"id": "b", "targetAmount": 3000, "priority": 2, "status": "active"},
            {"id": "a", "targetAmount": 500, "priority": 1, "status": "active"},
            {"id": "c", "targetAmount": 500, "priority": 3, "status": "active"},
        ]
        r = ba.resumo(metas, SETTINGS, CONTAS)
        cabe = {m["id"]: m["cabe_na_fila"] for m in r["metas"]}
        # 500 + 3000 = 3500 cabe; somando 500 daria 4000, que estoura.
        self.assertEqual(cabe, {"a": True, "b": True, "c": False})
        self.assertEqual(r["itens_que_cabem_no_bolso"], 2)

    def test_o_bolso_vem_em_campo_proprio(self):
        """Antes so dava para inferir pelas coberturas."""
        self.assertEqual(ba.resumo(METAS, SETTINGS, CONTAS)["bolso_aquisicoes"], BOLSO)


if __name__ == "__main__":
    unittest.main()
