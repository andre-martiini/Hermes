"""Testes da sombra de cumprimento (functions/cumprimento_compromissos_sombra.py)."""

import unittest
from datetime import datetime, timezone

import cumprimento_compromissos_sombra as ccs
from test_extracao_compromissos_sombra import _DB

AGORA = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)
PROMESSA = {"_doc_id": "c1_m1", "texto": "Vou te enviar a planilha amanhã", "estado": "aberta"}


def _db(ligada=True):
    db = _DB()
    db.dados[("system", "settings")] = {"atencao": {"cumprimento_sombra": {"enabled": ligada}}}
    return db


def _msg(**campos):
    base = {"from_me": True, "chat_id": "c1", "wa_message_id": "m2", "content": "ok"}
    base.update(campos)
    return base


class CumprimentoSombraTest(unittest.TestCase):
    def test_desligada_por_padrao(self):
        db = _DB()
        self.assertIsNone(ccs.registrar(db, _msg(), PROMESSA, "nenhuma", AGORA))
        self.assertEqual(db.escritas, [])

    def test_so_antigo_fecha_texto_longo_sobre_outro_assunto(self):
        db = _db()
        texto = "Hoje almocei muito bem, o restaurante novo é ótimo e recomendo."
        r = ccs.registrar(db, _msg(content=texto), PROMESSA, "cumprir", AGORA)
        self.assertEqual(r["divergencia"], "so_antigo_fecha")
        self.assertTrue(r["antigo_fecha"])
        gravado = db.em(ccs.SOMBRA_COLLECTION)[0][2]
        self.assertNotIn(texto, str(gravado))

    def test_ambos_fecham(self):
        db = _db()
        r = ccs.registrar(db, _msg(content="Segue a planilha"), PROMESSA, "cumprir", AGORA)
        self.assertEqual(r["divergencia"], "ambos_fecham")

    def test_ambos_mantem(self):
        r = ccs.registrar(_db(), _msg(content="ok"), PROMESSA, "nenhuma", AGORA)
        self.assertEqual(r["divergencia"], "ambos_mantem")

    def test_reentrega_nao_duplica(self):
        db = _db()
        ccs.registrar(db, _msg(), PROMESSA, "nenhuma", AGORA)
        self.assertIsNone(ccs.registrar(db, _msg(), PROMESSA, "nenhuma", AGORA))
        self.assertEqual(len(db.em(ccs.SOMBRA_COLLECTION)), 1)

    def test_ignora_sem_promessa_criar_grupo_e_flag_nao_booleana(self):
        db = _db()
        self.assertIsNone(ccs.registrar(db, _msg(), None, "nenhuma", AGORA))
        self.assertIsNone(ccs.registrar(db, _msg(), PROMESSA, "criar", AGORA))
        self.assertIsNone(ccs.registrar(db, _msg(is_group=True), PROMESSA, "nenhuma", AGORA))
        self.assertIsNone(ccs.registrar(db, _msg(from_me=False), PROMESSA, "nenhuma", AGORA))
        db.dados[("system", "settings")] = {"atencao": {"cumprimento_sombra": {"enabled": "false"}}}
        self.assertIsNone(ccs.registrar(db, _msg(), PROMESSA, "nenhuma", AGORA))

    def test_midia_sozinha_antigo_fecha_novo_nao(self):
        r = ccs.registrar(_db(), _msg(content="", media={"filename": "foto.jpg"}), PROMESSA, "cumprir", AGORA)
        self.assertEqual(r["divergencia"], "so_antigo_fecha")


if __name__ == "__main__":
    unittest.main()
