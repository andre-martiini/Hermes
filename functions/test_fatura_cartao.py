"""Extracao e projecao da fatura de cartao.

O que estes testes protegem, em ordem de importancia:

1. A **projecao de parcelas** — e o unico numero aqui que a fatura sozinha nao
   da, e errar nele produz um resultado plausivel e falso: o usuario acredita
   que tem folga que nao tem.
2. A **fronteira de correcao** de `fixed_bills`. Ate agosto/2026 os valores foram
   lancados a mao e ja estao pagos; sobrescrever apaga trabalho correto.
3. A **idempotencia** dos itens: reextrair a mesma fatura tem que atualizar, nao
   duplicar, senao todo re-sync dobra o gasto do mes.
"""

import json
import unittest
from datetime import datetime, timezone

import fatura_cartao as fc


class _FakeDoc:
    def __init__(self, dados):
        self._dados = dados

    def to_dict(self):
        return dict(self._dados)


class _FakeQuery:
    """Suficiente para o encadeamento `where(...).limit(...).stream()`."""

    def __init__(self, docs):
        self._docs = docs

    def where(self, campo, op, valor):
        def bate(d):
            atual = d.get(campo)
            if op == "==":
                return atual == valor
            if op == ">=":
                return str(atual or "") >= str(valor)
            raise AssertionError(f"operador nao previsto no fake: {op}")
        return _FakeQuery([d for d in self._docs if bate(d)])

    def limit(self, _n):
        return self

    def stream(self):
        return [_FakeDoc(d) for d in self._docs]


class _FakeDb:
    def __init__(self, itens):
        self._itens = itens

    def collection(self, nome):
        return _FakeQuery(self._itens if nome == fc.COL_ITENS else [])


def _item(**kw):
    base = {
        "competencia": "2026-09", "ano": 2026, "mes": 9,
        "estabelecimento": "LOJA", "valor": 100.0,
        "parcela_atual": None, "parcela_total": None, "parcelado": False,
    }
    base.update(kw)
    return base


class TestFronteiraDeCorrecao(unittest.TestCase):
    def test_nao_corrige_o_que_foi_lancado_a_mao(self):
        for mes, ano in ((8, 2026), (7, 2026), (1, 2026), (12, 2025)):
            self.assertFalse(fc.pode_corrigir_fixed_bill(mes, ano), f"{mes}/{ano}")

    def test_corrige_de_setembro_em_diante(self):
        for mes, ano in ((9, 2026), (10, 2026), (1, 2027)):
            self.assertTrue(fc.pode_corrigir_fixed_bill(mes, ano), f"{mes}/{ano}")

    def test_competencia_ausente_nao_corrige(self):
        self.assertFalse(fc.pode_corrigir_fixed_bill(None, 2026))
        self.assertFalse(fc.pode_corrigir_fixed_bill(9, None))


class TestRemetente(unittest.TestCase):
    def test_reconhece_a_caixa(self):
        self.assertEqual(
            fc.e_fatura_de_cartao("Cartões CAIXA <cartoescaixa@aplicacao.caixa.gov.br>"),
            "elo-caixa")

    def test_ignora_outros_boletos(self):
        for remetente in ("fatura@xpi.com.br", "boleto@allcaregestoradesaude.com.br", None, ""):
            self.assertIsNone(fc.e_fatura_de_cartao(remetente), remetente)


class TestProjecaoDeParcelas(unittest.TestCase):
    """`atual/total` numa competencia implica `total - atual` parcelas a vir."""

    def setUp(self):
        self.futuro = datetime.now(timezone.utc).year + 2

    def test_conta_as_parcelas_restantes(self):
        db = _FakeDb([_item(competencia=f"{self.futuro}-01", valor=200.0,
                            parcela_atual=1, parcela_total=4, parcelado=True)])
        meses = fc.projetar_parcelas(db)["meses"]
        # 1/4 paga em janeiro deixa 2, 3 e 4 — tres meses seguintes.
        self.assertEqual([m["competencia"] for m in meses],
                         [f"{self.futuro}-02", f"{self.futuro}-03", f"{self.futuro}-04"])
        self.assertTrue(all(m["total"] == 200.0 for m in meses))

    def test_ultima_parcela_nao_projeta_nada(self):
        db = _FakeDb([_item(competencia=f"{self.futuro}-01", parcela_atual=12,
                            parcela_total=12, parcelado=True)])
        self.assertEqual(fc.projetar_parcelas(db)["meses"], [])

    def test_soma_parcelas_de_compras_diferentes_no_mesmo_mes(self):
        db = _FakeDb([
            _item(competencia=f"{self.futuro}-01", estabelecimento="A", valor=100.0,
                  parcela_atual=1, parcela_total=3, parcelado=True),
            _item(competencia=f"{self.futuro}-01", estabelecimento="B", valor=50.0,
                  parcela_atual=1, parcela_total=2, parcelado=True),
        ])
        meses = {m["competencia"]: m for m in fc.projetar_parcelas(db)["meses"]}
        self.assertEqual(meses[f"{self.futuro}-02"]["total"], 150.0)
        self.assertEqual(meses[f"{self.futuro}-03"]["total"], 100.0)

    def test_vira_o_ano_corretamente(self):
        db = _FakeDb([_item(competencia=f"{self.futuro}-11", valor=80.0,
                            parcela_atual=1, parcela_total=4, parcelado=True)])
        self.assertEqual([m["competencia"] for m in fc.projetar_parcelas(db)["meses"]],
                         [f"{self.futuro}-12", f"{self.futuro + 1}-01", f"{self.futuro + 1}-02"])

    def test_ignora_mes_ja_passado(self):
        """Parcela de fatura antiga cujo vencimento ja aconteceu nao e compromisso."""
        db = _FakeDb([_item(competencia="2020-01", valor=90.0,
                            parcela_atual=1, parcela_total=3, parcelado=True)])
        self.assertEqual(fc.projetar_parcelas(db)["meses"], [])

    def test_compra_a_vista_nao_entra(self):
        db = _FakeDb([_item(competencia=f"{self.futuro}-01", valor=500.0)])
        self.assertEqual(fc.projetar_parcelas(db)["meses"], [])

    def test_total_comprometido_e_a_soma_dos_meses(self):
        db = _FakeDb([_item(competencia=f"{self.futuro}-01", valor=100.0,
                            parcela_atual=1, parcela_total=3, parcelado=True)])
        p = fc.projetar_parcelas(db)
        self.assertEqual(p["total_comprometido"], sum(m["total"] for m in p["meses"]))
        self.assertEqual(p["total_comprometido"], 200.0)


class TestIdempotencia(unittest.TestCase):
    def test_mesmo_item_gera_mesmo_id(self):
        item = {"data": "2026-09-03", "estabelecimento": "PADARIA", "valor": 12.5}
        self.assertEqual(fc._id_do_item("2026-09", item, 0),
                         fc._id_do_item("2026-09", item, 0))

    def test_compra_repetida_no_mesmo_dia_nao_colide(self):
        """Dois cafes iguais no mesmo dia sao dois lancamentos, nao um."""
        item = {"data": "2026-09-03", "estabelecimento": "CAFE", "valor": 9.0}
        self.assertNotEqual(fc._id_do_item("2026-09", item, 0),
                            fc._id_do_item("2026-09", item, 1))

    def test_competencias_diferentes_nao_colidem(self):
        item = {"data": "2026-09-03", "estabelecimento": "X", "valor": 10.0}
        self.assertNotEqual(fc._id_do_item("2026-09", item, 0),
                            fc._id_do_item("2026-10", item, 0))


class TestNormalizacao(unittest.TestCase):
    def test_competencia_cai_para_o_vencimento(self):
        self.assertEqual(fc._competencia_valida(None, "2026-09-15"), "2026-09")

    def test_vencimento_tem_prioridade_sobre_o_modelo(self):
        """O vencimento e impresso; a competencia o modelo infere — e erra.

        Duas faturas identicas (mesmos 77 lancamentos, mesmo vencimento
        2025-09-05) viraram 2025-08 e 2025-09 porque o modelo alternou entre mes
        de referencia e de fechamento. Derivar do vencimento colapsa as duas no
        documento certo.
        """
        self.assertEqual(fc._competencia_valida("2025-08", "2025-09-05"), "2025-09")
        self.assertEqual(fc._competencia_valida("2026-09", "2026-10-15"), "2026-10")

    def test_sem_vencimento_usa_o_que_o_modelo_deu(self):
        self.assertEqual(fc._competencia_valida("2026-09", None), "2026-09")

    def test_valores_em_formato_brasileiro(self):
        self.assertEqual(fc._num("1.234,56"), 1234.56)
        self.assertEqual(fc._num(1234.56), 1234.56)
        self.assertIsNone(fc._num(""))
        self.assertIsNone(fc._num("abc"))

    def test_estorno_negativo_e_preservado(self):
        self.assertEqual(fc._num(-45.9), -45.9)


class TestClassificacaoDeLinhas(unittest.TestCase):
    """Linha de saldo nao e compra.

    O prompt manda ignora-las e o modelo nao obedece de forma confiavel: numa
    fatura real vieram "TOTAL DA FATURA ANTERIOR" (+17.943) e "OBRIGADO PELO
    PAGAMENTO" (-17.943). Somam zero no total, mas na analise por
    estabelecimento apareceriam como o maior gasto do mes.
    """

    def test_linhas_de_saldo_sao_ajuste(self):
        for texto in ("TOTAL DA FATURA ANTERIOR", "SALDO ANTERIOR",
                      "OBRIGADO PELO PAGAMENTO", "PAGAMENTO EFETUADO",
                      "JUROS DE MORA", "IOF", "ENCARGOS DE ATRASO"):
            self.assertEqual(fc.classificar(texto), "ajuste", texto)

    def test_compra_de_verdade_e_compra(self):
        for texto in ("OBRAMAX", "CVC VITORIA", "MP MERCADOLIVRE",
                      "OPENAI *CHATGPT SUBSCR", "POSTO IPIRANGA"):
            self.assertEqual(fc.classificar(texto), "compra", texto)

    def test_estabelecimento_vazio_nao_quebra(self):
        self.assertEqual(fc.classificar(""), "compra")
        self.assertEqual(fc.classificar(None), "compra")


class TestPromptDeExtracao(unittest.TestCase):
    def test_pede_parcelamento_explicitamente(self):
        """Sem parcela_atual/parcela_total nao ha projecao possivel."""
        self.assertIn("parcela_atual", fc._PROMPT)
        self.assertIn("parcela_total", fc._PROMPT)

    def test_manda_nao_agrupar(self):
        """Somar itens iguais destruiria a analise por estabelecimento."""
        self.assertIn("Não agrupe", fc._PROMPT)

    def test_modelo_de_resposta_e_json_valido(self):
        inicio = fc._PROMPT.index('{\n  "cabecalho"')
        fim = fc._PROMPT.index("}\nSe o documento")
        json.loads(fc._PROMPT[inicio:fim + 1])


if __name__ == "__main__":
    unittest.main()
