"""Importacao da fatura de cartao por arquivo (CSV do app da XP, PDF do Elo).

O CSV de teste e o arquivo real exportado do app da XP para a fatura que
venceu em 05/10/2026 (compras de R$ 1.315,98, igual a conta "Fatura XP").
"""

import unittest

import fatura_cartao
import importar_fatura as imp

CSV_XP = (
    "﻿Data;Estabelecimento;Portador;Valor;Parcela\r\n"
    "01/09/2026;Pagamentos Validos Normais;ANDRE MARTINI;R$ -817,65;-\r\n"
    "04/09/2026;ANTHROPIC;ANDRE MARTINI;R$ 3,50;-\r\n"
    "04/09/2026;ANTHROPIC;ANDRE MARTINI;R$ 100,00;-\r\n"
    "06/09/2026;GOOGLE TELECINE;ANDRE MARTINI;R$ 29,90;-\r\n"
    "07/09/2026;ANTHROPIC* CLAUDE SUB;ANDRE MARTINI;R$ 901,09;-\r\n"
    "07/09/2026;ANTHROPIC* CLAUDE SUB;ANDRE MARTINI;R$ 31,54;-\r\n"
    "09/09/2026;GOOGLE CLOUD NWBKZL;ANDRE MARTINI;R$ 100,00;-\r\n"
    "16/09/2026;GOOGLE CLOUD 2XMFQB;ANDRE MARTINI;R$ 100,00;-\r\n"
    "18/09/2026;JET PATINETES;ANDRE MARTINI;R$ 9,05;-\r\n"
    "21/09/2026;DM*SPOTIFY P4720;ANDRE MARTINI;R$ 40,90;-\r\n"
)


# --- banco em memoria com o que fatura_cartao.salvar usa ---------------------

class _Snap:
    def __init__(self, ref, dados):
        self.reference = ref
        self.id = ref.id
        self._dados = dados

    @property
    def exists(self):
        return self._dados is not None

    def to_dict(self):
        return dict(self._dados) if self._dados is not None else None


class _Ref:
    def __init__(self, banco, colecao, doc_id):
        self._banco, self._colecao, self.id = banco, colecao, doc_id

    def _tabela(self):
        return self._banco.setdefault(self._colecao, {})

    def set(self, dados, merge=False):
        atual = self._tabela().get(self.id, {}) if merge else {}
        self._tabela()[self.id] = {**atual, **dados}

    def update(self, dados):
        self._tabela()[self.id].update(dados)

    def delete(self):
        self._tabela().pop(self.id, None)

    def get(self):
        return _Snap(self, self._tabela().get(self.id))


class _Query:
    def __init__(self, banco, colecao, filtros=()):
        self._banco, self._colecao, self._filtros = banco, colecao, filtros

    def where(self, campo, op, valor):
        assert op == "=="
        return _Query(self._banco, self._colecao, self._filtros + ((campo, valor),))

    def limit(self, _n):
        return self

    def document(self, doc_id=None):
        import uuid

        return _Ref(self._banco, self._colecao, doc_id or uuid.uuid4().hex[:20])

    def stream(self):
        tabela = self._banco.get(self._colecao, {})
        return [_Snap(_Ref(self._banco, self._colecao, i), d) for i, d in list(tabela.items())
                if all(d.get(c) == v for c, v in self._filtros)]


class _Lote:
    def __init__(self):
        self._ops = []

    def set(self, ref, dados, merge=False):
        self._ops.append(lambda: ref.set(dados, merge=merge))

    def delete(self, ref):
        self._ops.append(ref.delete)

    def commit(self):
        for op in self._ops:
            op()


class _Db:
    def __init__(self, colecoes=None):
        self.banco = {nome: dict(docs) for nome, docs in (colecoes or {}).items()}

    def collection(self, nome):
        return _Query(self.banco, nome)

    def batch(self):
        return _Lote()


def _conta_xp(valor):
    return {"fixed_bills": {"xp-out": {"description": "Fatura XP", "month": 9, "year": 2026, "amount": valor}}}


class TestCsvDaXp(unittest.TestCase):
    def test_reconhece_o_formato(self):
        self.assertTrue(imp.e_csv_da_xp(CSV_XP))
        self.assertFalse(imp.e_csv_da_xp("Data,Descricao,Valor\n"))

    def test_vencimento_vem_do_nome_do_arquivo(self):
        self.assertEqual(imp.vencimento_do_nome("Fatura2026-10-05.csv"), "2026-10-05")
        self.assertIsNone(imp.vencimento_do_nome("fatura.csv"))

    def test_pagamento_vai_para_o_cabecalho(self):
        dados = imp.ler_csv_xp(CSV_XP, "2026-10-05")
        self.assertEqual(len(dados["itens"]), 9)
        self.assertEqual(dados["cabecalho"]["total"], 1315.98)
        self.assertEqual(dados["cabecalho"]["pagamentos"], 817.65)
        self.assertNotIn("Pagamentos Validos Normais", [i["estabelecimento"] for i in dados["itens"]])

    def test_datas_e_valores_em_formato_brasileiro(self):
        item = imp.ler_csv_xp(CSV_XP, "2026-10-05")["itens"][3]
        self.assertEqual((item["data"], item["valor"]), ("2026-09-07", 901.09))
        self.assertEqual(imp._valor_br("R$ 1.234,56"), 1234.56)

    def test_parcela(self):
        self.assertEqual(imp._parcela("2/5"), (2, 5))
        self.assertEqual(imp._parcela("Parcela 3 de 10"), (3, 10))
        self.assertEqual(imp._parcela("-"), (None, None))

    def test_estorno_negativo_continua_lancamento(self):
        csv = CSV_XP + "22/09/2026;ESTORNO SPOTIFY;ANDRE MARTINI;R$ -40,90;-\r\n"
        dados = imp.ler_csv_xp(csv, "2026-10-05")
        self.assertEqual(dados["itens"][-1]["valor"], -40.9)
        self.assertEqual(dados["cabecalho"]["total"], 1275.08)


class TestImportarCsv(unittest.TestCase):
    def test_grava_relê_e_confere(self):
        db = _Db(_conta_xp(1315.98))
        r = imp.importar(db, CSV_XP.encode("utf-8"), "Fatura2026-10-05.csv")
        self.assertEqual(r["estado"], "verificado")
        self.assertEqual((r["fatura_id"], r["total"], r["lancamentos"]), ("xp-2026-10", 1315.98, 9))
        self.assertTrue(r["confere_com_a_soma"])
        cabecalho = db.banco[fatura_cartao.COL_FATURAS]["xp-2026-10"]
        self.assertEqual(cabecalho["pagamentos"], 817.65)

    def test_acerta_a_conta_do_mes_certo(self):
        db = _Db(_conta_xp(1000.0))
        r = imp.importar(db, CSV_XP.encode("utf-8"), "Fatura2026-10-05.csv")
        self.assertTrue(r["conta_do_mes"]["corrigida"])
        conta = db.banco["fixed_bills"]["xp-out"]
        self.assertEqual((conta["amount"], conta["amount_anterior"]), (1315.98, 1000.0))

    def test_reimportar_substitui(self):
        db = _Db(_conta_xp(1315.98))
        imp.importar(db, CSV_XP.encode("utf-8"), "Fatura2026-10-05.csv")
        r = imp.importar(db, CSV_XP.encode("utf-8"), "Fatura2026-10-05.csv")
        self.assertEqual(r["lancamentos"], 9)
        self.assertEqual(len(db.banco[fatura_cartao.COL_ITENS]), 9)

    def test_csv_sem_data_no_nome_pede_vencimento(self):
        with self.assertRaisesRegex(ValueError, "vencimento"):
            imp.importar(_Db(), CSV_XP.encode("utf-8"), "fatura.csv")
        r = imp.importar(_Db(), CSV_XP.encode("utf-8"), "fatura.csv", vencimento="2026-10-05")
        self.assertEqual(r["competencia"], "2026-10")

    def test_origem_fica_no_cabecalho(self):
        db = _Db()
        imp.importar(db, CSV_XP.encode("utf-8"), "Fatura2026-10-05.csv",
                     origem={"arquivo": "Fatura2026-10-05.csv", "drive_file_id": "abc"})
        cabecalho = db.banco[fatura_cartao.COL_FATURAS]["xp-2026-10"]
        self.assertEqual((cabecalho["origem"], cabecalho["drive_file_id"]), ("arquivo", "abc"))


class TestImportarPdf(unittest.TestCase):
    EXTRAIDO = {
        "cabecalho": {"total": 3814.14, "vencimento": "2026-10-05", "competencia": "2026-10"},
        "itens": [
            {"data": "2026-09-01", "estabelecimento": "TOTAL DA FATURA ANTERIOR", "valor": 5721.28},
            {"data": "2026-09-01", "estabelecimento": "OBRIGADO PELO PAGAMENTO", "valor": -5721.28},
            {"data": "2026-09-10", "estabelecimento": "LOJA A", "valor": 3624.14},
            {"data": "2026-09-12", "estabelecimento": "LOJA B", "valor": 190.0,
             "parcela_atual": 1, "parcela_total": 2},
        ],
    }

    def test_pdf_vai_para_o_elo_por_padrao(self):
        chamado = {}

        def ler(pdf, cartao):
            chamado["cartao"] = cartao
            return {k: dict(v) if isinstance(v, dict) else list(v) for k, v in self.EXTRAIDO.items()}

        db = _Db({"fixed_bills": {"elo-out": {"description": "Fatura Elo", "month": 9, "year": 2026,
                                               "amount": 3814.14}}})
        r = imp.importar(db, b"%PDF-1.4 ...", "fatura.pdf", extrair_pdf_fn=ler)
        self.assertEqual(chamado["cartao"], "elo-caixa")
        self.assertEqual((r["estado"], r["fatura_id"], r["total"]), ("verificado", "elo-caixa-2026-10", 3814.14))
        self.assertTrue(r["confere_com_a_soma"])

    def test_sem_leitor_de_pdf_e_erro_claro(self):
        with self.assertRaisesRegex(ValueError, "PDF"):
            imp.importar(_Db(), b"%PDF-1.4", "f.pdf")


class TestRecusas(unittest.TestCase):
    def test_arquivo_qualquer(self):
        with self.assertRaisesRegex(ValueError, "nao e PDF"):
            imp.importar(_Db(), b"ola mundo", "nota.txt")

    def test_cartao_desconhecido(self):
        with self.assertRaisesRegex(ValueError, "Cartao desconhecido"):
            imp.importar(_Db(), CSV_XP.encode("utf-8"), "Fatura2026-10-05.csv", cartao="nubank")

    def test_releitura_que_nao_bate_vira_falha(self):
        db = _Db()
        original = imp.reler
        imp.reler = lambda _db, _id: {"total": 1.0, "vencimento": None, "confiavel": False, "lancamentos": 0}
        try:
            r = imp.importar(db, CSV_XP.encode("utf-8"), "Fatura2026-10-05.csv")
        finally:
            imp.reler = original
        self.assertEqual(r["estado"], "falhou")


if __name__ == "__main__":
    unittest.main()


class TestHandlerMcp(unittest.TestCase):
    def _chamar(self, dados, nome, **args):
        from unittest import mock

        from tools import hermes_tools

        ctx = mock.Mock()
        ctx.db = _Db(_conta_xp(1315.98))
        with mock.patch("tools.anexar_arquivo._do_drive", return_value=(dados, nome)):
            return hermes_tools.importar_fatura_cartao(ctx, {"drive_file_id": "abc", **args})

    def test_sucesso_devolve_o_relido(self):
        r = self._chamar(CSV_XP.encode("utf-8"), "Fatura2026-10-05.csv")
        self.assertNotIn("erro", r)
        self.assertEqual((r["estado"], r["total"]), ("verificado", 1315.98))

    def test_arquivo_invalido_vira_erro(self):
        r = self._chamar(b"ola", "nota.txt")
        self.assertIn("nao e PDF", r["erro"])

    def test_falha_de_releitura_vira_erro(self):
        from unittest import mock

        with mock.patch.object(imp, "reler", return_value={"total": 0, "vencimento": None,
                                                             "confiavel": False, "lancamentos": 0}):
            r = self._chamar(CSV_XP.encode("utf-8"), "Fatura2026-10-05.csv")
        self.assertIn("nao confirmada", r["erro"])


class TestConsultaSeparaOsCartoes(unittest.TestCase):
    def setUp(self):
        self.db = _Db()
        imp.importar(self.db, CSV_XP.encode("utf-8"), "Fatura2026-10-05.csv")
        self.db.banco[fatura_cartao.COL_ITENS]["elo1"] = {
            "tipo": "compra", "cartao": "elo-caixa", "fatura_id": "elo-caixa-2026-10",
            "competencia": "2026-10", "data": "2026-09-10", "estabelecimento": "LOJA", "valor": 50.0}

    def test_total_por_cartao(self):
        r = fatura_cartao.consultar(self.db, competencia="2026-10")
        self.assertEqual(r["por_cartao"], {"xp": 1315.98, "elo-caixa": 50.0})

    def test_filtro_por_cartao(self):
        r = fatura_cartao.consultar(self.db, competencia="2026-10", cartao="elo-caixa")
        self.assertEqual((r["total_gasto"], r["total_lancamentos"]), (50.0, 1))


class TestSenhaIndisponivel(unittest.TestCase):
    def test_segue_sem_senha(self):
        from unittest import mock

        with mock.patch("bill_pdf_passwords.find_password_config", return_value={"secret_id": "s"}), \
             mock.patch("bill_pdf_passwords.read_password_secret", side_effect=PermissionError("403")):
            self.assertEqual(imp._senhas_do_cartao(_Db(), "elo-caixa"), [])

    def test_usa_a_senha_quando_ha(self):
        from unittest import mock

        with mock.patch("bill_pdf_passwords.find_password_config", return_value={"secret_id": "s"}), \
             mock.patch("bill_pdf_passwords.read_password_secret", return_value="1234"):
            self.assertEqual(imp._senhas_do_cartao(_Db(), "elo-caixa"), ["1234"])
