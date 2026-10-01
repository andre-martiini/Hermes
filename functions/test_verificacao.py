"""Contrato da confirmação verificada (functions/verificacao.py).

Sucesso só existe depois de reler o documento gravado, e a frase dita ao
usuário sai do valor RELIDO. Origem: em 28 e 30/09/2026 o Gemini do Telegram
disse "peso registrado" sem ter gravado nada.
"""

import unittest
from unittest import mock

import verificacao as v
from test_registrar_saude import _Db
from tools import registrar_saude as rs


def _db_com(colecao, doc_id, dados):
    db = _Db()
    db.collection(colecao).dados[doc_id] = dict(dados)
    return db


class TestVerificarEscrita(unittest.TestCase):
    def test_documento_igual_ao_esperado_fica_verificado(self):
        db = _db_com("health_weights", "abc", {"date": "2026-10-01", "weight": 94.4, "extra": 1})
        res = v.verificar_escrita(db, "health_weights/abc", {"date": "2026-10-01", "weight": 94.4}, "registrar_peso")
        self.assertEqual(res.estado, "verificado")
        self.assertEqual(res.valor_relido, {"date": "2026-10-01", "weight": 94.4})
        self.assertEqual(res.alvo, "health_weights/abc")

    def test_valor_divergente_falha_com_o_campo_no_motivo(self):
        db = _db_com("health_weights", "abc", {"date": "2026-10-01", "weight": 90.0})
        res = v.verificar_escrita(db, "health_weights/abc", {"date": "2026-10-01", "weight": 94.4})
        self.assertEqual(res.estado, "falhou")
        self.assertIn("weight relido 90", res.motivo)
        self.assertEqual(res.valor_relido["weight"], 90.0)

    def test_documento_ausente_falha(self):
        res = v.verificar_escrita(_Db(), "health_weights/sumiu", {"weight": 94.4})
        self.assertEqual(res.estado, "falhou")
        self.assertIn("não aparece", res.motivo)

    def test_erro_ao_reler_vira_falha_e_nao_excecao(self):
        db = mock.Mock()
        db.collection.return_value.document.return_value.get.side_effect = RuntimeError("firestore fora")
        res = v.verificar_escrita(db, "health_weights/abc", {"weight": 94.4})
        self.assertEqual(res.estado, "falhou")
        self.assertIn("firestore fora", res.motivo)

    def test_caminho_invalido_vira_falha(self):
        self.assertEqual(v.verificar_escrita(_Db(), "health_weights", {"weight": 1}).estado, "falhou")


class TestResultadoOperacao(unittest.TestCase):
    def test_falhou_exige_motivo(self):
        with self.assertRaises(ValueError):
            v.ResultadoOperacao("falhou", "registrar_peso", "health_weights")

    def test_estado_fora_dos_tres_e_recusado(self):
        with self.assertRaises(ValueError):
            v.ResultadoOperacao("enviado", "registrar_peso", "x")


class TestMontarConfirmacao(unittest.TestCase):
    def test_sucesso_usa_o_valor_relido_e_nao_o_esperado(self):
        res = v.ResultadoOperacao("verificado", "registrar_peso", "health_weights/abc",
                                  valor_esperado={"date": "2026-10-01", "weight": 1.0},
                                  valor_relido={"date": "2026-10-01", "weight": 94.4})
        self.assertEqual(v.montar_confirmacao(res), "Peso registrado: 94,4 kg em 01/10/2026.")

    def test_falha_diz_o_motivo_e_nao_diz_registrado(self):
        texto = v.montar_confirmacao(v.falhou("registrar_peso", "health_weights", "sem rede. Nada foi gravado."))
        self.assertEqual(texto, "Não consegui registrar o peso: sem rede. Nada foi gravado.")

    def test_pendente_nao_e_apresentado_como_feito(self):
        res = v.ResultadoOperacao("pendente", "enviar_whatsapp", "whatsapp_outbox/x")
        self.assertEqual(v.montar_confirmacao(res), "Aceito, aguardando conclusão.")


class TestGravarPesoVerificado(unittest.TestCase):
    def test_grava_e_rele_o_mesmo_documento(self):
        db = _Db()
        res = rs.gravar_peso_verificado(db, "94,4")
        self.assertTrue(res.ok)
        doc_id = res.alvo.split("/")[1]
        self.assertEqual(db.cols[rs.COL_PESOS].dados[doc_id]["weight"], 94.4)

    def test_fora_da_faixa_nao_grava(self):
        for valor in (12, 900, "1200"):
            with self.subTest(valor=valor):
                db = _Db()
                res = rs.gravar_peso_verificado(db, valor)
                self.assertEqual(res.estado, "falhou")
                self.assertIn("fora da faixa", res.motivo)
                self.assertNotIn(rs.COL_PESOS, db.cols)

    def test_falha_ao_gravar_vira_falhou(self):
        with mock.patch.object(rs, "_gravar_por_data", side_effect=RuntimeError("permissão negada")):
            res = rs.gravar_peso_verificado(_Db(), 94.4)
        self.assertEqual(res.estado, "falhou")
        self.assertIn("permissão negada", res.motivo)
        self.assertIn("Nada foi gravado", res.motivo)

    def test_releitura_divergente_vira_falhou(self):
        def grava_outro_valor(db, colecao, dia, campo, valor):
            db.collection(colecao).dados["x"] = {"date": dia, campo: valor - 4}
            return f"{colecao}/x"

        with mock.patch.object(rs, "_gravar_por_data", side_effect=grava_outro_valor):
            res = rs.gravar_peso_verificado(_Db(), 94.4)
        self.assertEqual(res.estado, "falhou")
        self.assertIn("não confere", res.motivo)

    def test_mcp_registrar_saude_passa_pela_mesma_escrita(self):
        with mock.patch.object(rs, "gravar_peso_verificado",
                               return_value=v.falhou("registrar_peso", rs.COL_PESOS, "releitura falhou")) as g:
            r = rs.registrar(mock.Mock(db=_Db()), {"peso": 94.4})
        g.assert_called_once()
        self.assertEqual(r["erro"], "releitura falhou")
        self.assertFalse(r["aplicado"])


if __name__ == "__main__":
    unittest.main()
