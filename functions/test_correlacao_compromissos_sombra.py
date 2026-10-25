"""Testes da sombra de correlação (functions/correlacao_compromissos_sombra.py)."""

import unittest
from datetime import datetime, timezone

import correlacao_compromissos_sombra as ccs
from test_extracao_compromissos_sombra import _DB

AGORA = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)
PROMESSA = {"_doc_id": "c1_m1", "texto": "Vou te enviar a planilha amanhã"}


def _db(ligada=True):
    db = _DB()
    db.dados[("system", "settings")] = {"atencao": {"correlacao_sombra": {"enabled": ligada}}}
    return db


def _msg(**campos):
    base = {"from_me": True, "chat_id": "c1", "wa_message_id": "m2", "media": {"filename": "planilha_notas.xlsx"}}
    base.update(campos)
    return base


class CorrelacaoSombraTest(unittest.TestCase):
    def test_desligada_por_padrao(self):
        db = _DB()
        self.assertIsNone(ccs.registrar(db, _msg(), PROMESSA, "nenhuma", AGORA))
        self.assertEqual(db.escritas, [])

    def test_so_semantico_sem_gravar_nome(self):
        db = _db()
        r = ccs.registrar(db, _msg(), PROMESSA, "nenhuma", AGORA)
        self.assertEqual(r["resultado"], "so_semantico")
        self.assertFalse(r["firme"])
        self.assertNotIn("planilha_notas", repr(db.em(ccs.SOMBRA_COLLECTION)))

    def test_id_em_comum_e_firme(self):
        p = dict(PROMESSA, ids_entregavel=["drive:1"])
        r = ccs.registrar(_db(), _msg(media={"filename": "x.pdf", "ids": ["drive:1"]}), p, "nenhuma", AGORA)
        self.assertEqual(r["resultado"], "vinculo_firme")

    def test_sem_vinculo(self):
        r = ccs.registrar(_db(), _msg(media={"filename": "foto.jpg"}), PROMESSA, "nenhuma", AGORA)
        self.assertEqual(r["resultado"], "sem_vinculo")

    def test_reentrega_nao_duplica(self):
        db = _db()
        ccs.registrar(db, _msg(), PROMESSA, "nenhuma", AGORA)
        self.assertIsNone(ccs.registrar(db, _msg(), PROMESSA, "nenhuma", AGORA))
        self.assertEqual(len(db.em(ccs.SOMBRA_COLLECTION)), 1)

    def test_ignora_sem_promessa_sem_midia_grupo_e_flag_nao_booleana(self):
        db = _db()
        self.assertIsNone(ccs.registrar(db, _msg(), None, AGORA))
        self.assertIsNone(ccs.registrar(db, _msg(media=None), PROMESSA, "nenhuma", AGORA))
        self.assertIsNone(ccs.registrar(db, _msg(is_group=True), PROMESSA, "nenhuma", AGORA))
        self.assertIsNone(ccs.registrar(db, _msg(from_me=False), PROMESSA, "nenhuma", AGORA))
        db2 = _DB()
        db2.dados[("system", "settings")] = {"atencao": {"correlacao_sombra": {"enabled": "true"}}}
        self.assertIsNone(ccs.registrar(db2, _msg(), PROMESSA, "nenhuma", AGORA))

    def test_promessa_longa_conta_como_fora_do_contrato(self):
        p = dict(PROMESSA, texto="vou enviar a planilha " + "x" * 700)
        r = ccs.registrar(_db(), _msg(), p, "nenhuma", AGORA)
        self.assertEqual(r["motivo_nao_avaliavel"], "fora_do_contrato")

    def test_acao_criar_nao_correlaciona(self):
        self.assertIsNone(ccs.registrar(_db(), _msg(), PROMESSA, "criar", AGORA))

    def test_nao_avaliavel_separado(self):
        r = ccs.registrar(_db(), _msg(media={"mimeType": "a"}), PROMESSA, "nenhuma", AGORA)
        self.assertEqual((r["resultado"], r["motivo_nao_avaliavel"]), ("nao_avaliavel", "midia_sem_nome"))
        r = ccs.registrar(_db(), _msg(), dict(PROMESSA, texto="te retorno amanhã"), "nenhuma", AGORA)
        self.assertEqual(r["motivo_nao_avaliavel"], "promessa_sem_objeto")
        r = ccs.registrar(_db(), _msg(), dict(PROMESSA, texto=None), "nenhuma", AGORA)
        self.assertEqual(r["motivo_nao_avaliavel"], "promessa_sem_objeto")
