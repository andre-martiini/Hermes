"""Saneamento do financeiro: conciliacao de Pix, total da fatura e projecao.

Casos reais de 2026 que estes testes guardam:
- um Pix de R$ 29,04 para uma padaria virou a "Fatura Elo" de setembro, porque
  "elo" casava com "CIELO", a instituicao da maquininha;
- a correcao pelo PDF da fatura procurava o card no mes seguinte (1-12 x 0-11);
- a projecao de parcelas somava todas as faturas importadas (R$ 20.642 x 4.729).
"""

import unittest
from datetime import datetime, timezone

import conciliacao_pix as cp
import fatura_cartao as fc

SNIPPET_PADARIA = (
    "Pagamento realizado via Pix Você fez um Pix para PADARIA E CONFEITARIA VIX LTDA "
    "Valor enviado R$ 29,04 Detalhes do pagamento Data e hora 27/09/2026 às 19:21 "
    "Instituição CIELO IP SA ID da transação"
)

RUBRICAS = [
    {"id": "elo", "full_desc": "Fatura Elo"},
    {"id": "xp", "full_desc": "Fatura XP"},
    {"id": "tim", "full_desc": "Tim celular"},
    {"id": "seguro", "full_desc": "Seguro do carro"},
    {"id": "fisio", "full_desc": "Elevar Fisio"},
    {"id": "plano", "full_desc": "Allcare plano de saúde"},
    {"id": "copart", "full_desc": "Allcare (coparticipação)"},
    {"id": "natacao", "full_desc": "Natação do Alexandre"},
]


class TestRecebedor(unittest.TestCase):
    def test_extrai_o_nome_de_quem_recebeu(self):
        self.assertEqual(cp.extrair_recebedor(SNIPPET_PADARIA), "PADARIA E CONFEITARIA VIX LTDA")

    def test_formato_da_xp(self):
        snippet = ("Seu Pix foi realizado Olá, Andre, O seu Pix enviado para Lorena Rabelo Feriane, "
                   "descrito abaixo, foi realizado com sucesso. Confira só: R$ 310,00 Valor enviado")
        self.assertEqual(cp.extrair_recebedor(snippet), "Lorena Rabelo Feriane")

    def test_sem_padrao_de_pix_nao_tem_recebedor(self):
        self.assertIsNone(cp.extrair_recebedor("Pagamento Recebido @fulano pagou você R$ 25,00"))


class TestNaoEComprovante(unittest.TestCase):
    def test_email_do_github_do_pr_573(self):
        # "Re: [andre-martiini/Hermes] ... causa do −R$ 6.277" virou um "Pix" de R$ 6.277 em 30/10/2026.
        self.assertTrue(cp.nao_e_comprovante('"André" <notifications@github.com>'))

    def test_comprovantes_e_encaminhamentos_passam(self):
        self.assertFalse(cp.nao_e_comprovante("Google Pay <payments-noreply@google.com>"))
        self.assertFalse(cp.nao_e_comprovante("PicPay <naoresponda@picpay.com>"))
        self.assertFalse(cp.nao_e_comprovante("André <andre.martiini@gmail.com>"))  # "Fwd: Pix realizado"
        self.assertFalse(cp.nao_e_comprovante(None))


class TestRubricaDoRecebedor(unittest.TestCase):
    def test_padaria_paga_na_cielo_nao_e_fatura_elo(self):
        recebedor = cp.extrair_recebedor(SNIPPET_PADARIA)
        self.assertIsNone(cp.rubrica_do_recebedor(recebedor, RUBRICAS))

    def test_instituicao_fora_do_nome_nao_conta(self):
        self.assertIsNone(cp.rubrica_do_recebedor(None, RUBRICAS))

    def test_palavra_inteira_casa(self):
        self.assertEqual(cp.rubrica_do_recebedor("TIM S A", RUBRICAS)["id"], "tim")
        self.assertEqual(cp.rubrica_do_recebedor("ELEVAR FISIOTERAPIA LTDA", RUBRICAS)["id"], "fisio")

    def test_pedaco_de_palavra_nao_casa(self):
        # "carro" dentro de "carrossel", "tim" dentro de "otimo"
        self.assertIsNone(cp.rubrica_do_recebedor("CARROSSEL KIDS", RUBRICAS))
        self.assertIsNone(cp.rubrica_do_recebedor("OTIMO MERCADO", RUBRICAS))

    def test_acento_nao_atrapalha(self):
        self.assertEqual(cp.rubrica_do_recebedor("ESCOLA DE NATACAO MAR", RUBRICAS)["id"], "natacao")

    def test_ambiguidade_nao_concilia(self):
        # As duas contas da Allcare casam com o mesmo recebedor.
        self.assertIsNone(cp.rubrica_do_recebedor("ALLCARE ADMINISTRADORA", RUBRICAS))

    def test_conta_paga_a_uma_pessoa_cadastrada(self):
        rubricas = RUBRICAS + [{"id": "fisio2", "full_desc": "Fisioterapia",
                                "pix_recebedor": "Lorena Rabelo Feriane"}]
        self.assertEqual(cp.rubrica_do_recebedor("LORENA RABELO FERIANE", rubricas)["id"], "fisio2")

    def test_nome_parcial_da_pessoa_nao_basta(self):
        rubricas = [{"id": "fisio2", "full_desc": "Fisioterapia", "pix_recebedor": "Lorena Rabelo Feriane"}]
        self.assertIsNone(cp.rubrica_do_recebedor("LORENA SOUZA", rubricas))

    def test_palavra_generica_nao_identifica(self):
        self.assertEqual(cp.palavras_chave("Fatura Elo"), ["elo"])
        self.assertIsNone(cp.rubrica_do_recebedor("FATURA DIGITAL SA", RUBRICAS))


class TestBaixaDaConta(unittest.TestCase):
    def _baixa(self, conta, valor):
        return cp.baixa_da_conta(conta, valor, data_iso="2026-09-27T22:22:01+00:00",
                                 msg_id="m1", pix_id="E1")

    def test_valor_diferente_nao_baixa(self):
        self.assertIsNone(self._baixa({"amount": 5721.28, "isPaid": False}, 29.04))

    def test_valor_que_bate_baixa_sem_trocar_o_valor(self):
        campos = self._baixa({"amount": 300.0, "isPaid": False}, 300.4)
        self.assertTrue(campos["isPaid"])
        self.assertEqual(campos["valor_pago"], 300.4)
        self.assertNotIn("amount", campos)

    def test_conta_sem_valor_recebe_o_do_pix(self):
        campos = self._baixa({"amount": 0, "isPaid": False}, 150.0)
        self.assertEqual(campos["amount"], 150.0)

    def test_conta_ja_paga_nao_e_baixada_de_novo(self):
        self.assertIsNone(self._baixa({"amount": 50.0, "isPaid": True}, 50.0))

    def test_id_da_conta_e_o_mesmo_da_tela(self):
        self.assertEqual(cp.id_da_conta("rub1", 2026, 8), "rub1_2026_8")


class _Doc:
    def __init__(self, doc_id, dados, alteracoes):
        self.id = doc_id
        self._dados = dados
        self.reference = self
        self._alteracoes = alteracoes

    def to_dict(self):
        return dict(self._dados)

    def update(self, campos):
        self._alteracoes.append((self.id, campos))


class _Query:
    def __init__(self, docs):
        self._docs = docs

    def where(self, campo, op, valor):
        assert op == "=="
        return _Query([d for d in self._docs if d._dados.get(campo) == valor])

    def limit(self, _n):
        return self

    def stream(self):
        return list(self._docs)


class _Db:
    def __init__(self, colecoes):
        self.alteracoes = []
        self._colecoes = {
            nome: [_Doc(f"{nome}-{i}", d, self.alteracoes) for i, d in enumerate(docs)]
            for nome, docs in colecoes.items()
        }

    def collection(self, nome):
        return _Query(self._colecoes.get(nome, []))


class TestCorrecaoPelaFatura(unittest.TestCase):
    def setUp(self):
        self.db = _Db({"fixed_bills": [
            {"description": "Fatura Elo", "month": 8, "year": 2026, "amount": 29.04},
            {"description": "Fatura Elo", "month": 9, "year": 2026, "amount": 3814.14},
            {"description": "Elevar Fisio", "month": 8, "year": 2026, "amount": 310.0},
        ]})
        self.resumo = {"mes": 9, "ano": 2026, "total": 5721.28, "fatura_id": "elo-caixa-2026-09",
                       "divergencia_total": 0.0, "soma_total": 5721.28}

    def test_fatura_de_setembro_corrige_o_card_de_setembro(self):
        r = fc.corrigir_fixed_bill(self.db, "elo-caixa", self.resumo)
        self.assertTrue(r["corrigido"])
        self.assertEqual(self.db.alteracoes, [("fixed_bills-0", self.db.alteracoes[0][1])])
        self.assertEqual(self.db.alteracoes[0][1]["amount"], 5721.28)
        self.assertEqual(self.db.alteracoes[0][1]["amount_anterior"], 29.04)

    def test_nao_corrige_conta_com_pedaco_do_nome_do_cartao(self):
        db = _Db({"fixed_bills": [{"description": "Cielo maquininha", "month": 8, "year": 2026, "amount": 10.0}]})
        fc.corrigir_fixed_bill(db, "elo-caixa", self.resumo)
        self.assertEqual(db.alteracoes, [])


class TestBoletoNaoTrocaOTotalDaFatura(unittest.TestCase):
    def test_total_vindo_da_fatura_fica(self):
        campos = {"amount": 29.04, "barcode": "123"}
        saida = fc.campos_do_boleto_no_card(campos, {"amount_origem": "fatura_cartao"})
        self.assertNotIn("amount", saida)
        self.assertEqual(saida["barcode"], "123")

    def test_card_comum_recebe_o_valor_do_boleto(self):
        campos = {"amount": 174.89}
        self.assertEqual(fc.campos_do_boleto_no_card(campos, {}), campos)


def _item(competencia, valor, atual, total, estabelecimento="LOJA", cartao="elo-caixa"):
    return {"competencia": competencia, "valor": valor, "parcela_atual": atual,
            "parcela_total": total, "parcelado": True, "estabelecimento": estabelecimento,
            "cartao": cartao, "fatura_id": f"{cartao}-{competencia}"}


class TestProjecaoSoDaFaturaMaisRecente(unittest.TestCase):
    def setUp(self):
        self.ano = datetime.now(timezone.utc).year + 2

    def _db(self, itens):
        return _Db({fc.COL_ITENS: itens})

    def test_a_mesma_compra_em_duas_faturas_conta_uma_vez(self):
        db = self._db([
            _item(f"{self.ano}-01", 100.0, 3, 5),
            _item(f"{self.ano}-02", 100.0, 4, 5),
        ])
        meses = fc.projetar_parcelas(db)["meses"]
        self.assertEqual([(m["competencia"], m["total"]) for m in meses],
                         [(f"{self.ano}-03", 100.0)])

    def test_cada_cartao_usa_a_propria_fatura_mais_recente(self):
        db = self._db([
            _item(f"{self.ano}-01", 100.0, 1, 3, cartao="elo-caixa"),
            _item(f"{self.ano}-02", 100.0, 2, 3, cartao="elo-caixa"),
            _item(f"{self.ano}-01", 40.0, 1, 2, cartao="xp"),
        ])
        p = fc.projetar_parcelas(db)
        totais = {m["competencia"]: m["total"] for m in p["meses"]}
        self.assertEqual(totais, {f"{self.ano}-02": 40.0, f"{self.ano}-03": 100.0})
        self.assertEqual(p["base"], {"elo-caixa": f"fatura {self.ano}-02", "xp": f"fatura {self.ano}-01"})

    def test_item_antigo_sem_cartao_usa_o_id_da_fatura(self):
        item = _item(f"{self.ano}-01", 100.0, 1, 2)
        del item["cartao"]
        self.assertEqual(fc._cartao_do_item(item), "elo-caixa")


if __name__ == "__main__":
    unittest.main()
