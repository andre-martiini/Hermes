"""Categorias dos lancamentos do cartao (regras por estabelecimento, aplicadas na leitura).

Os nomes de estabelecimento sao reais, tirados das faturas de 2025-2026.
"""

import unittest
from unittest import mock

import categorias_cartao as cc
import fatura_cartao
from test_importar_fatura import _Db


def _cat(nome, regras=None):
    return cc.classificar(nome, regras if regras is not None else cc.carregar_regras(_Db()))


class TestClassificacao(unittest.TestCase):
    def test_casos_reais(self):
        casos = {
            "Uber UBER TRIP HELP UBER SAO PAULO": "Transporte",
            "ANTHROPIC* CLAUDE SUB": "IA e software",
            "DL GOOGLE CLOUD CGNF6": "IA e software",
            "TYPESAFE AI, INC.": "IA e software",
            "SUPERMERCADO PERIM VITORIA": "Mercado",
            "DROGASIL3655": "Saúde e farmácia",
            "IRON ACADEMIA VITORIA": "Esporte e educação",
            "DL GOOGLE Disney": "Assinaturas e apps",
        }
        for nome, esperada in casos.items():
            self.assertEqual(_cat(nome)["categoria"], esperada, nome)

    def test_especifica_vence_a_plataforma(self):
        # Ar-condicionado comprado pela Amazon e casa, nao "compras online".
        self.assertEqual(_cat("AMAZONMKTPLC FRIOVIXCO SERRA")["categoria"], "Casa e construção")
        self.assertEqual(_cat("AMAZON BR SAO PAULO")["categoria"], "Compras online")
        # "dl google" generico perde para "google cloud".
        self.assertEqual(_cat("DL GOOGLE CLOUD")["categoria"], "IA e software")

    def test_ia_e_software_e_misto(self):
        self.assertEqual(_cat("OPENAI *CHATGPT SUBSCR")["natureza"], "misto")
        self.assertEqual(_cat("Uber UBER TRIP")["natureza"], "pessoal")

    def test_so_palavra_inteira(self):
        self.assertEqual(_cat("SUPERUBERX LTDA")["categoria"], cc.SEM_CATEGORIA)

    def test_sem_regra(self):
        r = _cat("EmilyDaSilvaAlves")
        self.assertEqual((r["categoria"], r["natureza"]), (cc.SEM_CATEGORIA, None))


class TestRegrasDoDono(unittest.TestCase):
    def test_definir_cria_regra_e_vale_mais_que_a_padrao(self):
        db = _Db()
        cc.definir(db, "Emily da Silva", "Serviços e taxas")
        self.assertEqual(_cat("EMILY DA SILVA ALVES", cc.carregar_regras(db))["categoria"], "Serviços e taxas")
        cc.definir(db, "openai", "IA e software", "projeto")
        self.assertEqual(_cat("OPENAI *CHATGPT", cc.carregar_regras(db))["natureza"], "projeto")

    def test_regra_do_dono_vence_mesmo_curta(self):
        db = _Db()
        cc.definir(db, "trip", "Viagem e lazer")
        self.assertEqual(_cat("Uber UBER TRIP", cc.carregar_regras(db))["categoria"], "Viagem e lazer")

    def test_remover_desliga_inclusive_a_padrao(self):
        db = _Db()
        cc.remover(db, "uber")
        self.assertEqual(_cat("Uber UBER TRIP", cc.carregar_regras(db))["categoria"], cc.SEM_CATEGORIA)
        cc.definir(db, "uber", "Transporte")
        self.assertEqual(_cat("Uber UBER TRIP", cc.carregar_regras(db))["categoria"], "Transporte")

    def test_validacoes(self):
        with self.assertRaisesRegex(ValueError, "3 letras"):
            cc.definir(_Db(), "ab", "Mercado")
        with self.assertRaisesRegex(ValueError, "Natureza"):
            cc.definir(_Db(), "uber", "Transporte", "empresa")
        with self.assertRaisesRegex(ValueError, "categoria"):
            cc.definir(_Db(), "uber", " ")


def _itens(db):
    db.banco[fatura_cartao.COL_ITENS] = {
        "a": {"tipo": "compra", "cartao": "elo-caixa", "fatura_id": "elo-caixa-2026-10", "competencia": "2026-10",
              "data": "2026-09-10", "estabelecimento": "Uber UBER TRIP", "valor": 30.0},
        "b": {"tipo": "compra", "cartao": "xp", "fatura_id": "xp-2026-10", "competencia": "2026-10",
              "data": "2026-09-07", "estabelecimento": "ANTHROPIC* CLAUDE SUB", "valor": 901.09},
        "c": {"tipo": "compra", "cartao": "elo-caixa", "fatura_id": "elo-caixa-2026-10", "competencia": "2026-10",
              "data": "2026-09-12", "estabelecimento": "EmilyDaSilvaAlves", "valor": 650.0},
        "d": {"tipo": "encargo", "cartao": "elo-caixa", "fatura_id": "elo-caixa-2026-10", "competencia": "2026-10",
              "data": "2026-09-12", "estabelecimento": "IOF", "valor": 3.0},
    }
    return db


class TestConsultaComCategorias(unittest.TestCase):
    def test_categorias_somam_o_total(self):
        r = fatura_cartao.consultar(_itens(_Db()), competencia="2026-10")
        self.assertEqual(round(sum(c["total"] for c in r["por_categoria"]), 2), r["total_gasto"])
        self.assertEqual(r["total_gasto"], 1581.09)
        self.assertEqual(r["por_natureza"], {"pessoal": 30.0, "misto": 901.09, "sem natureza": 650.0})
        self.assertEqual(r["sem_categoria"], [{"estabelecimento": "EmilyDaSilvaAlves", "total": 650.0, "lancamentos": 1}])

    def test_cada_lancamento_traz_a_categoria(self):
        r = fatura_cartao.consultar(_itens(_Db()), competencia="2026-10")
        uber = next(i for i in r["lancamentos"] if i["estabelecimento"].startswith("Uber"))
        self.assertEqual((uber["categoria"], uber["natureza"]), ("Transporte", "pessoal"))

    def test_filtro_por_categoria(self):
        r = fatura_cartao.consultar(_itens(_Db()), competencia="2026-10", categoria="ia e software")
        self.assertEqual((r["total_gasto"], r["total_lancamentos"]), (901.09, 1))

    def test_regra_nova_vale_para_fatura_antiga(self):
        db = _itens(_Db())
        cc.definir(db, "emilydasilvaalves", "Serviços e taxas")
        r = fatura_cartao.consultar(db, competencia="2026-10")
        self.assertEqual(r["sem_categoria"], [])


class TestFerramenta(unittest.TestCase):
    def _chamar(self, db, **args):
        from tools import hermes_tools

        ctx = mock.Mock()
        ctx.db = db
        return hermes_tools.gerenciar_categorias_cartao(ctx, args)

    def test_listar(self):
        r = self._chamar(_Db(), acao="listar")
        self.assertIn("IA e software", r["categorias"])
        self.assertIn("uber", r["regras_por_categoria"]["Transporte"])

    def test_definir_confirma_relendo(self):
        r = self._chamar(_Db(), acao="definir", padrao="Emily da Silva", categoria="Serviços e taxas")
        self.assertEqual(r["estado"], "verificado")
        self.assertEqual(r["regra"]["padrao"], "emily da silva")

    def test_erros_viram_mensagem(self):
        self.assertIn("padrao", self._chamar(_Db(), acao="definir", categoria="Mercado")["erro"])
        self.assertIn("Natureza", self._chamar(_Db(), acao="definir", padrao="uber", categoria="T",
                                               natureza="x")["erro"])
        self.assertIn("Acao desconhecida", self._chamar(_Db(), acao="apagar", padrao="uber")["erro"])


if __name__ == "__main__":
    unittest.main()


class TestReleituraQueNaoBate(unittest.TestCase):
    def test_vira_erro(self):
        from tools import hermes_tools

        ctx = mock.Mock()
        ctx.db = _Db()
        with mock.patch.object(cc, "definir", return_value={"ativo": True, "categoria": "Outra"}):
            r = hermes_tools.gerenciar_categorias_cartao(
                ctx, {"acao": "definir", "padrao": "uber", "categoria": "Transporte"})
        self.assertIn("nao foi confirmada", r["erro"])


class TestFeira(unittest.TestCase):
    """Feira do Centro de Vitoria: sabado de manha, bancas com nome de pessoa."""

    SABADO, DOMINGO, QUARTA = "2026-10-24", "2026-10-25", "2026-10-21"

    def _lanc(self, nome, valor, data, db=None):
        return cc.classificar_lancamento({"estabelecimento": nome, "valor": valor, "data": data},
                                         cc.carregar_regras(db or _Db()))

    def test_bancas_confirmadas_por_regra_em_qualquer_dia(self):
        self.assertEqual(self._lanc("CECILIAERPFONTAIN", 38.5, self.QUARTA)["categoria"], "Feira")
        self.assertEqual(self._lanc("VALDECI ANTONIO ZAHN Domingos Mart", 22.4, self.QUARTA)["categoria"], "Feira")

    def test_compra_pequena_sem_regra_no_fim_de_semana_e_feira_inferida(self):
        for data in (self.SABADO, self.DOMINGO):
            r = self._lanc("IVO BREMENKAMP FERREIR", 18.5, data)
            self.assertEqual(r["categoria"], "Feira")
            self.assertIn("inferida", r)

    def test_dia_de_semana_nao_infere(self):
        self.assertEqual(self._lanc("IVO BREMENKAMP FERREIR", 18.5, self.QUARTA)["categoria"], cc.SEM_CATEGORIA)

    def test_compra_grande_nao_infere(self):
        self.assertEqual(self._lanc("EmilyDaSilvaAlves", 650.0, self.DOMINGO)["categoria"], cc.SEM_CATEGORIA)

    def test_loja_de_artes_nao_e_feira(self):
        self.assertEqual(self._lanc("JB ARTESANATOS", 40.0, self.SABADO)["categoria"], cc.SEM_CATEGORIA)
        self.assertEqual(self._lanc("DBN ARTES LTDA", 100.0, self.SABADO)["categoria"], cc.SEM_CATEGORIA)

    def test_regra_vence_a_inferencia(self):
        self.assertEqual(self._lanc("Uber UBER TRIP", 20.0, self.SABADO)["categoria"], "Transporte")
        self.assertEqual(self._lanc("338 S VITORIA ES", 149.95, self.SABADO)["categoria"], "Vestuário e calçados")
        db = _Db()
        cc.definir(db, "ivo bremenkamp", "Restaurantes e lanches")
        r = self._lanc("IVO BREMENKAMP FERREIR", 18.5, self.SABADO, db)
        self.assertEqual(r["categoria"], "Restaurantes e lanches")
        self.assertNotIn("inferida", r)

    def test_data_ruim_nao_quebra(self):
        self.assertEqual(self._lanc("FULANO", 10.0, None)["categoria"], cc.SEM_CATEGORIA)
