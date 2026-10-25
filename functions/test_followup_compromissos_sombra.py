"""Testes da sombra de follow-up (functions/followup_compromissos_sombra.py)."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import atencao_whatsapp
import followup_compromissos_sombra as fcs
from test_extracao_compromissos_sombra import _DB

PROMETIDO = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
AGORA = PROMETIDO + timedelta(hours=30)
CHAVE = "promessa_sem_retorno:c1:m1"
PROMESSA = {"_doc_id": "c1_m1", "chat_id": "c1", "mensagem_id": "m1",
            "texto": "Vou te enviar a planilha amanhã", "prometido_em": PROMETIDO, "estado": "aberta"}
PROPRIA = {"from_me": True, "wa_message_id": "m1", "timestamp": PROMETIDO, "content": PROMESSA["texto"]}


def _db(ligada=True, estado_atencao=None):
    db = _DB()
    db.dados[("system", "settings")] = {"atencao": {"followup_sombra": {"enabled": ligada}}}
    if estado_atencao:
        db.dados[("atencao", CHAVE)] = {"estado": estado_atencao}
    return db


def _rodar(db, mensagens=(PROPRIA,), rascunho=False, historico=(), promessa=PROMESSA):
    with mock.patch.object(fcs, "_mensagens", return_value=list(mensagens)), \
         mock.patch.object(fcs, "_historico", return_value=list(historico)), \
         mock.patch("secretario_whatsapp.eh_mensagem_do_bot", side_effect=lambda m, _db: m.get("bot", False)), \
         mock.patch.object(fcs, "_rascunho_pendente", return_value=rascunho):
        return fcs.registrar(db, promessa, CHAVE, AGORA)


class FollowupSombraTest(unittest.TestCase):
    def test_desligada_por_padrao(self):
        db = _DB()
        self.assertIsNone(_rodar(db))
        self.assertEqual(db.escritas, [])

    def test_flag_nao_booleana_nao_liga(self):
        db = _db()
        db.dados[("system", "settings")] = {"atencao": {"followup_sombra": {"enabled": "true"}}}
        self.assertIsNone(_rodar(db))

    def test_sem_impedimento_ambos_alertam(self):
        r = _rodar(_db())
        self.assertEqual((r["acao_nova"], r["divergencia"]), ("enviar", "ambos_alertam"))

    def test_dono_ja_tratou_suprime(self):
        r = _rodar(_db(estado_atencao="resolvido"))
        self.assertEqual((r["motivo"], r["divergencia"]), ("dono_ja_tratou", "nenhum_alerta"))
        self.assertIsNone(r["proxima_avaliacao"])

    def test_rascunho_existente_suprime(self):
        r = _rodar(_db(), rascunho=True)
        self.assertEqual(r["motivo"], "rascunho_existente")

    def test_intervencao_humana_adia(self):
        outra = {"from_me": True, "wa_message_id": "m9", "timestamp": PROMETIDO + timedelta(hours=2), "content": "ok"}
        r = _rodar(_db(), mensagens=[PROPRIA, outra])
        self.assertEqual((r["motivo"], r["divergencia"]), ("intervencao_humana", "so_novo_adia"))
        self.assertIsNotNone(r["proxima_avaliacao"])

    def test_mensagem_do_bot_nao_e_intervencao_humana(self):
        bot = {"from_me": True, "bot": True, "wa_message_id": "m9", "timestamp": PROMETIDO + timedelta(hours=2),
               "content": "resposta do secretário"}
        r = _rodar(_db(), mensagens=[PROPRIA, bot])
        self.assertEqual(r["divergencia"], "ambos_alertam")

    def test_cumprimento_firme_suprime(self):
        envio = {"from_me": True, "wa_message_id": "m9", "timestamp": PROMETIDO + timedelta(hours=2),
                 "content": "Segue a planilha"}
        r = _rodar(_db(), mensagens=[PROPRIA, envio])
        self.assertEqual(r["motivo"], "ja_cumprido")

    def test_acompanhamento_padrao_sem_historico(self):
        promessa = {**PROMESSA, "vence_em": PROMETIDO + timedelta(hours=48)}
        r = _rodar(_db(), promessa=promessa)
        self.assertEqual(r["acompanhamento_origem"], "padrao")
        self.assertEqual(r["acompanhamento_amostra"], 0)
        self.assertEqual(r["acompanhamento_delta_horas"], -24.0)

    def test_acompanhamento_usa_historico_do_contato(self):
        hist = []
        for i in range(6):
            base = PROMETIDO - timedelta(days=i + 1)
            hist.append({"from_me": False, "timestamp": base})
            hist.append({"from_me": True, "timestamp": base + timedelta(hours=3)})
        r = _rodar(_db(), historico=hist)
        self.assertEqual((r["acompanhamento_origem"], r["acompanhamento_amostra"]), ("historico_contato", 6))
        self.assertNotIn("acompanhamento_delta_horas", r)  # promessa sem vence_em

    def test_respostas_automaticas_rapidas_nao_entram_no_historico(self):
        hist = []
        for i in range(6):
            base = PROMETIDO - timedelta(days=i + 1)
            hist.append({"from_me": False, "timestamp": base})
            hist.append({"from_me": True, "timestamp": base + timedelta(seconds=30)})
        r = _rodar(_db(), historico=hist)
        self.assertEqual((r["acompanhamento_origem"], r["acompanhamento_amostra"]), ("padrao", 0))

    def test_falha_do_acompanhamento_nao_derruba_o_resumo(self):
        with mock.patch.object(fcs, "planejar_acompanhamento", side_effect=RuntimeError("x")):
            r = _rodar(_db())
        self.assertTrue(r["acompanhamento_erro"])
        self.assertEqual(r["divergencia"], "ambos_alertam")

    def test_horas_de_resposta(self):
        t0 = PROMETIDO
        msgs = [
            {"from_me": False, "timestamp": t0}, {"from_me": False, "timestamp": t0 + timedelta(hours=1)},
            {"from_me": True, "timestamp": t0 + timedelta(hours=4)}, {"from_me": True, "timestamp": t0 + timedelta(hours=5)},
            {"from_me": False, "timestamp": t0 + timedelta(days=30)}, {"from_me": True, "timestamp": t0 + timedelta(days=40)},
            {"from_me": True, "timestamp": None},
        ]
        self.assertEqual(fcs.horas_de_resposta(msgs), [4.0])

    def test_nunca_grava_texto(self):
        db = _db()
        _rodar(db)
        self.assertNotIn("planilha", str(db.em(fcs.SOMBRA_COLLECTION)))

    def test_grava_item_por_chave_e_versao_em_colecao_propria(self):
        db = _db()
        _rodar(db)
        itens = db.em(fcs.ITENS_COLLECTION)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0][1], "c1_m1__v1")
        item = itens[0][2]
        self.assertEqual((item["acao"], item["estado"], item["modo"]), ("enviar", "aberto", "sombra"))
        self.assertNotIn("planilha", str(item))
        self.assertEqual(db.em("atencao"), [])  # nunca toca a fila real

    def test_item_suprimido_nasce_encerrado(self):
        db = _db(estado_atencao="resolvido")
        _rodar(db)
        item = db.em(fcs.ITENS_COLLECTION)[0][2]
        self.assertEqual((item["estado"], item["proxima_avaliacao"]), ("encerrado", None))

    def test_item_existente_terminal_nao_e_reaberto(self):
        db = _db()
        db.dados[(fcs.ITENS_COLLECTION, "c1_m1__v1")] = {
            "id": "c1_m1__v1", "chave_compromisso": "c1_m1", "versao": 1, "acao": "enviar",
            "motivo": "x", "estado": "enviado", "avaliado_em": AGORA.isoformat(), "proxima_avaliacao": None}
        _rodar(db)
        self.assertEqual(db.em(fcs.ITENS_COLLECTION), [])

    def test_reentrega_nao_duplica(self):
        db = _db()
        _rodar(db)
        self.assertIsNone(_rodar(db))
        self.assertEqual(len(db.em(fcs.SOMBRA_COLLECTION)), 1)
        self.assertEqual(len(db.em(fcs.ITENS_COLLECTION)), 1)

    def test_promessa_sem_identidade_ignorada(self):
        db = _db()
        self.assertIsNone(fcs.registrar(db, {**PROMESSA, "_doc_id": ""}, CHAVE, AGORA))
        self.assertIsNone(fcs.registrar(db, {**PROMESSA, "prometido_em": None}, CHAVE, AGORA))
        self.assertIsNone(fcs.registrar(db, PROMESSA, "", AGORA))

    def test_consultas_usam_chat_e_chave(self):
        db = mock.MagicMock()
        fcs._mensagens(db, "c1", PROMETIDO)
        fcs._rascunho_pendente(db, CHAVE)
        chamadas = str(db.mock_calls)
        for esperado in ("'chat_id', '==', 'c1'", "order_by('timestamp', direction='DESCENDING')", "'item_atencao_id', '==', 'promessa_sem_retorno:c1:m1'"):
            self.assertIn(esperado, chamadas)


class VencerPromessasIntegracaoTest(unittest.TestCase):
    def test_falha_da_sombra_nao_derruba_o_vencimento(self):
        promessa = {**PROMESSA, "vence_em": PROMETIDO + timedelta(hours=24)}
        item_ref = mock.MagicMock()
        item_ref.get.return_value.exists = False
        promessas_ref = mock.MagicMock()
        db = mock.MagicMock()
        db.collection.side_effect = lambda n: promessas_ref if n == atencao_whatsapp.PROMESSAS_COLLECTION else mock.MagicMock(
            document=mock.Mock(return_value=item_ref))
        doc = mock.Mock(id="c1_m1")
        doc.to_dict.return_value = {k: v for k, v in promessa.items() if k != "_doc_id"}
        promessas_ref.where.return_value.stream.return_value = [doc]
        with mock.patch("main.get_db", return_value=db), \
             mock.patch.object(atencao_whatsapp, "_flag_promessa", return_value=(True, 24)), \
             mock.patch.object(fcs, "registrar", side_effect=RuntimeError("boom")):
            atencao_whatsapp.vencer_promessas.__wrapped__() if hasattr(atencao_whatsapp.vencer_promessas, "__wrapped__") else atencao_whatsapp.vencer_promessas()
        promessas_ref.document.return_value.update.assert_called_once_with({"estado": "vencida"})


if __name__ == "__main__":
    unittest.main()
