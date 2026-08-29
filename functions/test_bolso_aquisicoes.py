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


class TestEmpateDePrioridade(unittest.TestCase):
    """A porta que a fixture nao olhava.

    Duas metas de mesma `priority` ficavam na ordem de ENTRADA da lista, e os
    dois lados recebem a lista de fontes diferentes: o MCP monta do Firestore, a
    tela monta do snapshot. Com o bolso cobrindo so uma das duas, cada lado
    diria que uma diferente cabe — divergencia entre linguagens outra vez, sem
    nenhum teste reclamar.

    O mesmo caso esta no arquivo espelho.
    """

    SETTINGS = {"emergencyReserveCurrent": 0, "emergencyReserveTarget": 0,
                "investmentReserveCurrent": 1000}

    def _cabe(self, metas):
        r = ba.resumo(metas, self.SETTINGS, [])
        return {m["id"]: m["cabe_na_fila"] for m in r["metas"]}

    def test_a_ordem_de_entrada_nao_muda_quem_cabe(self):
        metas = [{"id": "z", "targetAmount": 600, "priority": 2, "status": "active"},
                 {"id": "a", "targetAmount": 600, "priority": 2, "status": "active"}]
        self.assertEqual(self._cabe(metas), self._cabe(list(reversed(metas))))

    def test_o_desempate_e_pelo_id_e_e_estavel(self):
        metas = [{"id": "z", "targetAmount": 600, "priority": 2, "status": "active"},
                 {"id": "a", "targetAmount": 600, "priority": 2, "status": "active"}]
        self.assertEqual(self._cabe(metas), {"a": True, "z": False})

    def test_caixa_mista_desempata_por_ordinal(self):
        """O caso que `localeCompare` errava do outro lado.

        O JavaScript poe 'a' antes de 'B' com `localeCompare`; o Python poe 'B'
        antes de 'a'. Id do Firestore mistura as duas caixas, entao com o bolso
        cobrindo so uma das metas cada lado apontaria uma diferente. Os MESMOS
        ids e numeros estao no arquivo espelho.
        """
        metas = [{"id": "a1", "targetAmount": 600, "priority": 2, "status": "active"},
                 {"id": "B1", "targetAmount": 600, "priority": 2, "status": "active"}]
        self.assertEqual(self._cabe(metas), {"B1": True, "a1": False})

    def test_a_ordem_devolvida_e_a_ordem_em_que_a_fila_foi_avaliada(self):
        """Quem consome nao precisa reordenar — e nao deve."""
        metas = [{"id": "a1", "targetAmount": 600, "priority": 2, "status": "active"},
                 {"id": "B1", "targetAmount": 600, "priority": 2, "status": "active"},
                 {"id": "z", "targetAmount": 600, "priority": 1, "status": "active"}]
        r = ba.resumo(metas, self.SETTINGS, [])
        self.assertEqual([m["id"] for m in r["metas"]], ["z", "B1", "a1"])

    def test_prioridade_invalida_nao_derruba_a_ordenacao(self):
        """`priority` gravado como None ou string nao pode levantar TypeError.

        O `consultar_financas_v2` tinha um `goals.sort(key=lambda x:
        x.get("priority", 99))` proprio, antes de chamar este modulo. O default
        do `get` nao pega `priority: None` — a chave existe — e comparar None
        com int derruba a tool inteira. `_ordem` coage e cai para 99; o sort de
        fora foi removido, e este teste fixa a razao de a ordenacao viver aqui.
        """
        metas = [{"id": "nan", "targetAmount": 600, "priority": "NaN", "status": "active"},
                 {"id": "vazio", "targetAmount": 600, "priority": "", "status": "active"},
                 {"id": "alta", "targetAmount": 600, "priority": "alta", "status": "active"},
                 {"id": "inf", "targetAmount": 600, "priority": "Infinity", "status": "active"},
                 {"id": "nulo", "targetAmount": 600, "priority": None, "status": "active"},
                 {"id": "um", "targetAmount": 600, "priority": 1, "status": "active"}]
        r = ba.resumo(metas, self.SETTINGS, [])
        self.assertEqual([m["id"] for m in r["metas"]],
                         ["um", "alta", "inf", "nan", "nulo", "vazio"])

    def test_prioridade_ausente_vai_para_o_fim(self):
        metas = [{"id": "sem", "targetAmount": 600, "status": "active"},
                 {"id": "com", "targetAmount": 600, "priority": 1, "status": "active"}]
        self.assertEqual(self._cabe(metas), {"com": True, "sem": False})


class TestDinheiroNaoEFloat(unittest.TestCase):
    """Os dois jeitos de a aritmetica reintroduzir a divergencia entre linguagens.

    Estes casos existem no arquivo espelho com os MESMOS numeros. Se um lado
    mudar de convencao, o outro quebra.
    """

    def test_fronteira_exata_nao_vira_nao_cabe(self):
        """0,10 + 0,70 da 0.7999999999999999 em float; a meta de 0,80 cabe."""
        settings = {"emergencyReserveCurrent": 0, "emergencyReserveTarget": 0,
                    "investmentReserveCurrent": 0.1}
        contas = [{"category": "Poupança", "amount": 0.7, "isPaid": True}]
        metas = [{"id": "x", "targetAmount": 0.8, "priority": 1, "status": "active"}]
        r = ba.resumo(metas, settings, contas)
        self.assertEqual(r["bolso_aquisicoes"], 0.8)
        self.assertEqual(r["metas"][0]["cobertura_pct"], 100.0)
        self.assertTrue(r["metas"][0]["cabe_na_fila"])
        self.assertEqual(r["itens_que_cabem_no_bolso"], 1)

    def test_empate_no_arredondamento_vai_para_cima(self):
        """`round` do Python iria para PAR e o JavaScript para cima: 12,25 -> 12,3."""
        settings = {"emergencyReserveCurrent": 0, "emergencyReserveTarget": 0,
                    "investmentReserveCurrent": 49}
        metas = [{"id": "x", "targetAmount": 400, "priority": 1, "status": "active"}]
        r = ba.resumo(metas, settings, [])
        self.assertEqual(r["metas"][0]["cobertura_pct"], 12.3)

    def test_centavos_arredondam_meio_para_cima(self):
        self.assertEqual(ba.centavos(0.005), 1)
        self.assertEqual(ba.centavos(0.015), 2)


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
