"""Proposta mensal de saldo disponivel e poupanca (pedido do Andre em 01/11/2026).

O que estes testes protegem, em ordem de importancia:

1. A formula da poupanca: saldo_previsto (renda esperada - contas) menos o
   saldo disponivel decidido. E a diferenca que o Andre descreveu, e e por
   isso que a renda que ainda nao caiu (ex.: parcela de servico no meio do
   mes) entra certo sem tratamento especial -- `saldo_previsto` ja usa a
   renda esperada, nao so a recebida.
2. Idempotencia: a proposta so dispara uma vez por mes (marca atomica), e so
   quando todas as contas do mes estao pagas.
3. O outlier so avisa, nunca filtra a media sozinho.
"""
import unittest
from datetime import date
from unittest import mock

import proposta_saldo_mensal as psm


# --------------------------------------------------------------------------
# Firestore falso (create/update com caminho de ponto/set/where/stream)
# --------------------------------------------------------------------------

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

    def get(self):
        return _Snap(self, self._tabela().get(self.id))

    def set(self, dados, merge=False):
        atual = self._tabela().get(self.id, {}) if merge else {}
        self._tabela()[self.id] = {**atual, **dados}

    def update(self, dados):
        tabela = self._tabela()
        if self.id not in tabela:
            raise KeyError(f"documento {self.id} nao existe")
        atual = tabela[self.id]
        for chave, valor in dados.items():
            partes = chave.split(".")
            alvo = atual
            for p in partes[:-1]:
                alvo = alvo.setdefault(p, {})
            alvo[partes[-1]] = valor

    def create(self, dados):
        from google.api_core.exceptions import AlreadyExists
        if self.id in self._tabela():
            raise AlreadyExists("409 already exists")
        self._tabela()[self.id] = dict(dados)


class _Query:
    def __init__(self, banco, colecao, filtros=()):
        self._banco, self._colecao, self._filtros = banco, colecao, filtros

    def where(self, campo, op, valor):
        return _Query(self._banco, self._colecao, self._filtros + ((campo, op, valor),))

    def document(self, doc_id=None):
        import uuid
        return _Ref(self._banco, self._colecao, doc_id or uuid.uuid4().hex[:20])

    def stream(self):
        tabela = self._banco.get(self._colecao, {})

        def passa(d):
            for campo, op, valor in self._filtros:
                atual = d.get(campo)
                if op == "==" and atual != valor:
                    return False
                if op == ">=" and str(atual or "") < str(valor):
                    return False
            return True

        return [_Snap(_Ref(self._banco, self._colecao, i), d) for i, d in list(tabela.items()) if passa(d)]


class _Db:
    def __init__(self, colecoes=None):
        self.banco = {nome: dict(docs) for nome, docs in (colecoes or {}).items()}

    def collection(self, nome):
        return _Query(self.banco, nome)


P = "picpay"


def _tx(valor, data, categoria="Geral", **extra):
    return {"amount": valor, "date": data, "category": categoria, "conta": P, **extra}


# --------------------------------------------------------------------------
# Calculo puro
# --------------------------------------------------------------------------

class TestTodasContasPagas(unittest.TestCase):
    def test_vazio_nao_dispara(self):
        self.assertFalse(psm.todas_contas_pagas([]))

    def test_uma_nao_paga_bloqueia(self):
        self.assertFalse(psm.todas_contas_pagas([{"isPaid": True}, {"isPaid": False}]))

    def test_todas_pagas(self):
        self.assertTrue(psm.todas_contas_pagas([{"isPaid": True}, {"isPaid": True}]))


class TestMesAnterior(unittest.TestCase):
    def test_dentro_do_mesmo_ano(self):
        self.assertEqual(psm.mes_anterior(2026, 11, 1), (2026, 10))
        self.assertEqual(psm.mes_anterior(2026, 11, 3), (2026, 8))

    def test_virada_de_ano(self):
        self.assertEqual(psm.mes_anterior(2026, 1, 1), (2025, 12))
        self.assertEqual(psm.mes_anterior(2026, 2, 3), (2025, 11))


class TestMediaGastosAvulsos(unittest.TestCase):
    def test_media_dos_3_meses_fechados(self):
        transacoes = [
            _tx(100.0, "2026-08-10"),
            _tx(200.0, "2026-09-10"),
            _tx(300.0, "2026-10-10"),
        ]
        # Proposta feita em novembro: média de ago+set+out = (100+200+300)/3 = 200.
        self.assertEqual(psm.media_gastos_avulsos_centavos(transacoes, 2026, 11), 20000)

    def test_mes_sem_gasto_entra_como_zero_na_media(self):
        transacoes = [_tx(300.0, "2026-10-10")]
        self.assertEqual(psm.media_gastos_avulsos_centavos(transacoes, 2026, 11), 10000)  # (0+0+300)/3


class TestMaiorOutlier(unittest.TestCase):
    def test_gasto_desproporcional_e_apontado(self):
        transacoes = [
            _tx(50.0, "2026-10-05"),
            _tx(50.0, "2026-10-10"),
            _tx(500.0, "2026-10-15", descricao="hotel", description="Hotel da viagem"),
        ]
        outlier = psm.maior_outlier(transacoes, 2026, 10)
        self.assertEqual(outlier, {"descricao": "Hotel da viagem", "valor_centavos": 50000})

    def test_unico_lancamento_nao_e_outlier(self):
        self.assertIsNone(psm.maior_outlier([_tx(500.0, "2026-10-15")], 2026, 10))

    def test_gasto_proporcional_nao_e_outlier(self):
        transacoes = [_tx(60.0, "2026-10-05"), _tx(40.0, "2026-10-10")]
        self.assertIsNone(psm.maior_outlier(transacoes, 2026, 10))

    def test_mes_sem_gasto_nenhum(self):
        self.assertIsNone(psm.maior_outlier([], 2026, 10))


class TestCalcularPoupanca(unittest.TestCase):
    def test_diferenca_simples(self):
        self.assertEqual(psm.calcular_poupanca_centavos(1000000, 500000), 500000)

    def test_saldo_disponivel_maior_que_a_sobra_da_poupanca_negativa(self):
        self.assertEqual(psm.calcular_poupanca_centavos(100000, 150000), -50000)


class TestTextoEBotoes(unittest.TestCase):
    def test_texto_sem_outlier(self):
        texto = psm.texto_proposta(11, 1000000, 500000, None)
        self.assertIn("novembro", texto)
        self.assertIn("R$ 10000.00", texto)
        self.assertIn("R$ 5000.00", texto)  # saldo disponível
        self.assertIn("R$ 5000.00", texto)  # poupança (mesmo valor neste exemplo)
        self.assertNotIn("entrou nessa", texto)

    def test_texto_com_outlier(self):
        texto = psm.texto_proposta(10, 1000000, 500000, {"descricao": "Hotel", "valor_centavos": 50000})
        self.assertIn("R$ 500.00", texto)
        self.assertIn("Hotel", texto)
        self.assertIn("entrou nessa", texto)

    def test_teclado_tem_confirmar_e_ajustar(self):
        botoes = psm.teclado_proposta("2026-11")
        self.assertEqual(botoes, [[
            {"text": "✅ Confirmar", "callback_data": "saldomes:2026-11:ok"},
            {"text": "✏️ Ajustar", "callback_data": "saldomes:2026-11:ajustar"},
        ]])


# --------------------------------------------------------------------------
# Integracao com Firestore / Telegram
# --------------------------------------------------------------------------

class TestVerificarEPropor(unittest.TestCase):
    def _db_com_contas_pagas(self):
        db = _Db({
            "fixed_bills": {
                "c1": {"description": "Conta 1", "amount": 100.0, "month": 10, "year": 2026, "isPaid": True},
            },
            "income_entries": {
                "r1": {"description": "Renda", "amount": 5000.0, "month": 10, "year": 2026, "status": "active"},
            },
            "finance_transactions": {
                "t1": _tx(200.0, "2026-08-10"),
                "t2": _tx(300.0, "2026-09-10"),
                "t3": _tx(400.0, "2026-10-10"),
            },
        })
        return db

    def test_dispara_quando_tudo_pago_e_registra_a_marca(self):
        db = self._db_com_contas_pagas()
        with mock.patch("telegram_utils._send_telegram_message_with_keyboard") as enviar:
            psm.verificar_e_propor(db, "tok", "chat1", date(2026, 11, 15))
        enviar.assert_called_once()
        marca = db.banco[psm.COLLECTION_MARCA]["2026-11"]
        self.assertEqual(marca["saldo_previsto_centavos"], 490000)  # 5000 - 100
        self.assertEqual(marca["saldo_disponivel_proposto_centavos"], 30000)  # média 200/300/400
        self.assertFalse(marca["decidido"])

    def test_nao_dispara_sem_todas_as_contas_pagas(self):
        db = self._db_com_contas_pagas()
        db.banco["fixed_bills"]["c2"] = {"description": "Conta 2", "amount": 50.0,
                                          "month": 10, "year": 2026, "isPaid": False}
        with mock.patch("telegram_utils._send_telegram_message_with_keyboard") as enviar:
            psm.verificar_e_propor(db, "tok", "chat1", date(2026, 11, 15))
        enviar.assert_not_called()
        self.assertNotIn(psm.COLLECTION_MARCA, db.banco)

    def test_nao_dispara_de_novo_no_mesmo_mes(self):
        db = self._db_com_contas_pagas()
        with mock.patch("telegram_utils._send_telegram_message_with_keyboard") as enviar:
            psm.verificar_e_propor(db, "tok", "chat1", date(2026, 11, 15))
            psm.verificar_e_propor(db, "tok", "chat1", date(2026, 11, 20))
        enviar.assert_called_once()

    def test_sem_chat_id_nao_faz_nada(self):
        db = self._db_com_contas_pagas()
        with mock.patch("telegram_utils._send_telegram_message_with_keyboard") as enviar:
            psm.verificar_e_propor(db, "tok", None, date(2026, 11, 15))
        enviar.assert_not_called()
        self.assertNotIn(psm.COLLECTION_MARCA, db.banco)


class TestRegistrarDecisao(unittest.TestCase):
    def test_grava_teto_e_poupanca(self):
        db = _Db({"finance_settings": {"config": {"monthlyBudget": 5000}}})
        resultado = psm.registrar_decisao(db, 2026, 11, 500000, 1000000)
        self.assertEqual(resultado, {"saldo_disponivel": 5000.0, "poupanca": 5000.0,
                                      "poupanca_id": resultado["poupanca_id"]})
        config = db.banco["finance_settings"]["config"]
        self.assertEqual(config["monthlyBudgets"]["2026-11"], 5000.0)
        self.assertEqual(config["monthlyBudget"], 5000)  # outros campos preservados

        poupanca = db.banco["fixed_bills"][resultado["poupanca_id"]]
        self.assertEqual(poupanca["category"], "Poupança")
        self.assertEqual(poupanca["amount"], 5000.0)
        self.assertTrue(poupanca["isPaid"])
        self.assertEqual((poupanca["month"], poupanca["year"]), (10, 2026))


class TestHandleCallback(unittest.TestCase):
    def _db_com_proposta(self, decidido=False):
        return _Db({psm.COLLECTION_MARCA: {"2026-11": {
            "ano": 2026, "mes": 11, "saldo_previsto_centavos": 1000000,
            "saldo_disponivel_proposto_centavos": 500000, "decidido": decidido,
        }}, "finance_settings": {"config": {}}})

    def _args(self, db, data, session=None):
        return dict(db=db, token="tok", query_id="q1", chat_id="chat1", data=data,
                    message={"message_id": 42}, session=session if session is not None else {},
                    copilot_session_id=None, _persist_callback_turn=lambda *a: None,
                    _pending_web_card=lambda *a: None, _clear_pending_web_card=lambda *a: None)

    def test_ignora_callback_de_outro_prefixo(self):
        self.assertFalse(psm.handle(**self._args(_Db(), "pixcls:x:g")))

    def test_confirmar_registra_e_marca_decidido(self):
        db = self._db_com_proposta()
        with mock.patch("telegram_callbacks_custos._edit_message_text") as editar, \
                mock.patch("telegram_utils._answer_callback_query") as responder:
            tratado = psm.handle(**self._args(db, "saldomes:2026-11:ok"))
        self.assertTrue(tratado)
        editar.assert_called_once()
        responder.assert_called_once()
        self.assertTrue(db.banco[psm.COLLECTION_MARCA]["2026-11"]["decidido"])
        self.assertEqual(db.banco["finance_settings"]["config"]["monthlyBudgets"]["2026-11"], 5000.0)

    def test_ajustar_arma_captura_de_texto_livre(self):
        db = self._db_com_proposta()
        session = {}
        with mock.patch("telegram_utils._answer_callback_query"), \
                mock.patch("telegram_utils._send_telegram_message") as enviar, \
                mock.patch("telegram_utils._save_session") as salvar:
            tratado = psm.handle(**self._args(db, "saldomes:2026-11:ajustar", session=session))
        self.assertTrue(tratado)
        self.assertEqual(session.get(psm.PENDING_AJUSTE), "2026-11")
        salvar.assert_called_once()
        enviar.assert_called_once()
        # Não decide nada ainda.
        self.assertFalse(db.banco[psm.COLLECTION_MARCA]["2026-11"]["decidido"])

    def test_proposta_ja_decidida_nao_faz_nada_de_novo(self):
        db = self._db_com_proposta(decidido=True)
        with mock.patch("telegram_utils._answer_callback_query") as responder:
            tratado = psm.handle(**self._args(db, "saldomes:2026-11:ok"))
        self.assertTrue(tratado)
        responder.assert_called_once()
        self.assertNotIn("monthlyBudgets", db.banco["finance_settings"]["config"])

    def test_proposta_inexistente(self):
        db = _Db()
        with mock.patch("telegram_utils._answer_callback_query") as responder:
            tratado = psm.handle(**self._args(db, "saldomes:2099-01:ok"))
        self.assertTrue(tratado)
        responder.assert_called_once()

    def test_acao_invalida(self):
        db = self._db_com_proposta()
        with mock.patch("telegram_utils._answer_callback_query") as responder:
            tratado = psm.handle(**self._args(db, "saldomes:2026-11:xyz"))
        self.assertTrue(tratado)
        responder.assert_called_once_with("tok", "q1", "Botão inválido.")


class TestAplicarAjuste(unittest.TestCase):
    def _db_com_proposta(self, decidido=False):
        return _Db({psm.COLLECTION_MARCA: {"2026-11": {
            "ano": 2026, "mes": 11, "saldo_previsto_centavos": 1000000,
            "saldo_disponivel_proposto_centavos": 500000, "decidido": decidido,
        }}, "finance_settings": {"config": {}}})

    def test_numero_simples(self):
        db = self._db_com_proposta()
        resposta = psm.aplicar_ajuste(db, "2026-11", "4500")
        self.assertIn("4500.00", resposta)
        self.assertEqual(db.banco["finance_settings"]["config"]["monthlyBudgets"]["2026-11"], 4500.0)

    def test_formato_brasileiro(self):
        db = self._db_com_proposta()
        resposta = psm.aplicar_ajuste(db, "2026-11", "R$ 4.500,00")
        self.assertIn("4500.00", resposta)

    def test_texto_sem_numero(self):
        db = self._db_com_proposta()
        resposta = psm.aplicar_ajuste(db, "2026-11", "não sei")
        self.assertIn("Não entendi", resposta)
        self.assertFalse(db.banco[psm.COLLECTION_MARCA]["2026-11"]["decidido"])

    def test_proposta_ja_decidida(self):
        db = self._db_com_proposta(decidido=True)
        resposta = psm.aplicar_ajuste(db, "2026-11", "4500")
        self.assertIn("já foi decidida", resposta)

    def test_proposta_inexistente(self):
        resposta = psm.aplicar_ajuste(_Db(), "2099-01", "4500")
        self.assertIn("não existe mais", resposta)


if __name__ == "__main__":
    unittest.main()
