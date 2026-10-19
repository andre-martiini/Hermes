"""Persistência incremental da transcrição ao vivo (functions/transcricao_ao_vivo.py)."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import transcricao_ao_vivo as tav
from fake_firestore_transcricao import FakeDb, em_transacao_falsa

SESSAO = "sessao-teste-0001"


def _trecho(texto, falante="Reunião", t_inicio=0, t_fim=1):
    return {"texto": texto, "falante": falante, "t_inicio": t_inicio, "t_fim": t_fim}


class _Base(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.agora = datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)
        patches = [
            mock.patch.object(tav, "_em_transacao", em_transacao_falsa),
            mock.patch.object(tav, "_agora", lambda: self.agora),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def sessao(self):
        return self.db.docs[f"{tav.COLECAO}/{SESSAO}"]

    def trechos(self):
        prefixo = f"{tav.COLECAO}/{SESSAO}/{tav.SUBCOLECAO}/"
        return [d for c, d in sorted(self.db.docs.items()) if c.startswith(prefixo)]

    def iniciar(self, **extra):
        return tav.processar(self.db, "uid-dono", {"acao": "iniciar", "sessao_id": SESSAO, **extra})

    def anexar(self, lote, base, *trechos):
        return tav.processar(self.db, "uid-dono", {
            "acao": "anexar", "sessao_id": SESSAO, "lote_id": lote, "base_seq": base, "trechos": list(trechos)})


class TestIniciar(_Base):
    def test_cria_sessao_ao_vivo(self):
        r = self.iniciar(titulo="  Webinário   IA ", terceiros_presentes=True, url="https://youtu.be/x")
        self.assertEqual(r, {"status": "criada", "sessao_id": SESSAO, "ultimo_seq": 0, "estado": "ao_vivo"})
        s = self.sessao()
        self.assertEqual(s["titulo"], "Webinário IA")
        self.assertEqual(s["estado"], "ao_vivo")
        self.assertEqual(s["ultimo_seq"], 0)
        self.assertEqual(s["uid"], "uid-dono")
        self.assertEqual(s["fonte"], "reunioes_gaspar")
        self.assertEqual(s["url"], "https://youtu.be/x")
        self.assertTrue(s["terceiros_presentes"])
        self.assertEqual(s["iniciada_em"], self.agora)

    def test_repetir_nao_recria_nem_zera(self):
        self.iniciar(titulo="A")
        self.anexar("lote-000000001", 0, _trecho("oi"))
        r = self.iniciar(titulo="B")
        self.assertEqual(r["status"], "ja_existia")
        self.assertEqual(r["ultimo_seq"], 1)
        self.assertEqual(self.sessao()["titulo"], "A")

    def test_url_que_nao_e_http_some(self):
        self.iniciar(url="javascript:alert(1)")
        self.assertIsNone(self.sessao()["url"])

    def test_id_invalido(self):
        for ruim in ("", "curto", "com/barra-123456", "x" * 65):
            with self.assertRaises(tav.ErroTranscricao):
                tav.processar(self.db, "u", {"acao": "iniciar", "sessao_id": ruim})


class TestAnexar(_Base):
    def setUp(self):
        super().setUp()
        self.iniciar()

    def test_seq_continuo_entre_lotes(self):
        r1 = self.anexar("lote-000000001", 0, _trecho("um", t_inicio=1, t_fim=2), _trecho("dois", "Você", 2, 3))
        self.agora += timedelta(seconds=10)
        r2 = self.anexar("lote-000000002", 2, _trecho("três"))
        self.assertEqual((r1["status"], r1["ultimo_seq"]), ("gravado", 2))
        self.assertEqual((r2["status"], r2["ultimo_seq"]), ("gravado", 3))
        self.assertEqual([(t["seq"], t["texto"]) for t in self.trechos()], [(1, "um"), (2, "dois"), (3, "três")])
        self.assertEqual(self.trechos()[1]["falante"], "Você")
        self.assertEqual(self.sessao()["ultimo_seq"], 3)
        self.assertEqual(self.sessao()["total_caracteres"], len("um") + len("dois") + len("três"))
        self.assertEqual(self.sessao()["ultimo_trecho_em"], self.agora)
        self.assertEqual(self.trechos()[2]["criado_em"], self.agora)

    def test_id_do_documento_e_o_seq(self):
        self.anexar("lote-000000001", 0, _trecho("um"))
        self.assertIn(f"{tav.COLECAO}/{SESSAO}/trechos/00000001", self.db.docs)

    def test_mesmo_lote_reenviado_nao_duplica(self):
        self.anexar("lote-000000001", 0, _trecho("um"))
        r = self.anexar("lote-000000001", 0, _trecho("um"))
        self.assertEqual(r, {"status": "ja_gravado", "ultimo_seq": 1})
        self.assertEqual(len(self.trechos()), 1)

    def test_base_errada_e_conflito_sem_gravar(self):
        self.anexar("lote-000000001", 0, _trecho("um"))
        r = self.anexar("lote-000000002", 0, _trecho("outro"))
        self.assertEqual(r, {"status": "conflito", "ultimo_seq": 1})
        self.assertEqual(len(self.trechos()), 1)

    def test_trecho_vazio_nao_ocupa_seq(self):
        r = self.anexar("lote-000000001", 0, _trecho("   "), _trecho("vale"))
        self.assertEqual(r["ultimo_seq"], 1)
        self.assertEqual(self.trechos()[0]["texto"], "vale")

    def test_tempos_limpos(self):
        self.anexar("lote-000000001", 0, {"texto": "a", "t_inicio": 9, "t_fim": 3},
                    {"texto": "b", "t_inicio": -5, "t_fim": float("nan")}, {"texto": "c", "t_inicio": True})
        t = self.trechos()
        self.assertEqual((t[0]["t_inicio"], t[0]["t_fim"]), (3.0, 9.0))
        self.assertEqual((t[1]["t_inicio"], t[1]["t_fim"]), (0.0, 0.0))
        self.assertEqual(t[2]["t_inicio"], 0.0)
        self.assertIsNone(t[2]["falante"])

    def test_sinal_de_vida_so_atualiza(self):
        self.anexar("lote-000000001", 0, _trecho("um"))
        trecho_em = self.sessao()["ultimo_trecho_em"]
        self.agora += timedelta(seconds=30)
        r = tav.processar(self.db, "u", {"acao": "anexar", "sessao_id": SESSAO, "trechos": []})
        self.assertEqual(r, {"status": "vivo", "ultimo_seq": 1, "estado": "ao_vivo"})
        self.assertEqual(self.sessao()["atualizada_em"], self.agora)
        self.assertEqual(self.sessao()["ultimo_trecho_em"], trecho_em)

    def test_lote_invalido_recusado_inteiro(self):
        casos = [
            "não é lista",
            [_trecho("ok"), "texto solto"],
            [_trecho("ok"), {"falante": "x"}],
            [_trecho("x" * (tav.MAX_TEXTO_TRECHO + 1))],
            [_trecho("x")] * (tav.MAX_TRECHOS_POR_LOTE + 1),
            [_trecho("x" * 3000)] * 21,
        ]
        for trechos in casos:
            with self.assertRaises(tav.ErroTranscricao):
                tav.processar(self.db, "u", {"acao": "anexar", "sessao_id": SESSAO, "lote_id": "lote-000000009",
                                             "base_seq": 0, "trechos": trechos})
        self.assertEqual(self.trechos(), [])
        self.assertEqual(self.sessao()["ultimo_seq"], 0)

    def test_base_seq_invalido(self):
        for base in (-1, "0", True, None, 1.0):
            with self.assertRaises(tav.ErroTranscricao):
                self.anexar("lote-000000001", base, _trecho("um"))

    def test_sessao_inexistente(self):
        with self.assertRaises(tav.ErroTranscricao) as ctx:
            tav.processar(self.db, "u", {"acao": "anexar", "sessao_id": "nao-existe-123", "lote_id": "lote-000000001",
                                         "base_seq": 0, "trechos": [_trecho("x")]})
        self.assertEqual(ctx.exception.codigo, "not-found")

    def test_falha_no_meio_nao_grava_nada(self):
        original = tav.id_trecho

        def explode(seq):
            if seq == 2:
                raise RuntimeError("falhou no meio")
            return original(seq)

        with mock.patch.object(tav, "id_trecho", explode), self.assertRaises(RuntimeError):
            self.anexar("lote-000000001", 0, _trecho("um"), _trecho("dois"))
        self.assertEqual(self.trechos(), [])
        self.assertEqual(self.sessao()["ultimo_seq"], 0)


class TestEncerrar(_Base):
    def setUp(self):
        super().setUp()
        self.iniciar()
        self.anexar("lote-000000001", 0, _trecho("um"))

    def test_encerra_e_e_idempotente(self):
        self.agora += timedelta(minutes=5)
        r = tav.processar(self.db, "u", {"acao": "encerrar", "sessao_id": SESSAO})
        self.assertEqual(r, {"status": "encerrada", "ultimo_seq": 1})
        self.assertEqual(self.sessao()["estado"], "encerrada")
        self.assertEqual(self.sessao()["encerrada_em"], self.agora)
        quando = self.agora
        self.agora += timedelta(minutes=5)
        r2 = tav.processar(self.db, "u", {"acao": "encerrar", "sessao_id": SESSAO})
        self.assertEqual(r2["status"], "ja_encerrada")
        self.assertEqual(self.sessao()["encerrada_em"], quando)

    def test_depois_de_encerrar_nao_aceita_texto_novo(self):
        tav.processar(self.db, "u", {"acao": "encerrar", "sessao_id": SESSAO})
        with self.assertRaises(tav.ErroTranscricao) as ctx:
            self.anexar("lote-000000002", 1, _trecho("tarde demais"))
        self.assertEqual(ctx.exception.codigo, "failed-precondition")
        self.assertEqual(len(self.trechos()), 1)

    def test_reenvio_do_ultimo_lote_depois_de_encerrar_ainda_e_reconhecido(self):
        tav.processar(self.db, "u", {"acao": "encerrar", "sessao_id": SESSAO})
        r = self.anexar("lote-000000001", 0, _trecho("um"))
        self.assertEqual(r["status"], "ja_gravado")

    def test_sinal_de_vida_nao_mexe_na_sessao_encerrada(self):
        tav.processar(self.db, "u", {"acao": "encerrar", "sessao_id": SESSAO})
        antes = self.sessao()["atualizada_em"]
        self.agora += timedelta(minutes=1)
        r = tav.processar(self.db, "u", {"acao": "anexar", "sessao_id": SESSAO, "trechos": []})
        self.assertEqual(r["estado"], "encerrada")
        self.assertEqual(self.sessao()["atualizada_em"], antes)

    def test_vincular_titulo_e_reuniao(self):
        tav.processar(self.db, "u", {"acao": "encerrar", "sessao_id": SESSAO})
        r = tav.processar(self.db, "u", {"acao": "vincular", "sessao_id": SESSAO, "titulo": "Painel PLS",
                                         "reuniao_id": "AbCdEf123456"})
        self.assertEqual(r["status"], "vinculada")
        self.assertEqual(self.sessao()["titulo"], "Painel PLS")
        self.assertEqual(self.sessao()["reuniao_id"], "AbCdEf123456")


class TestCallable(_Base):
    def test_acao_desconhecida(self):
        with self.assertRaises(tav.ErroTranscricao):
            tav.processar(self.db, "u", {"acao": "apagar", "sessao_id": SESSAO})

    def test_registrada_no_main(self):
        import ast
        import os

        with open(os.path.join(os.path.dirname(__file__), "main.py"), encoding="utf-8") as f:
            arvore = ast.parse(f.read())
        nomes = {a.name for n in arvore.body if isinstance(n, ast.ImportFrom) and n.module == "transcricao_ao_vivo"
                 for a in n.names}
        self.assertIn("transcricaoAoVivo", nomes)

    def _req(self, email, verificado=True):
        req = mock.Mock()
        req.auth = mock.Mock(uid="uid-x", token={"email": email, "email_verified": verificado})
        req.data = {"acao": "iniciar", "sessao_id": SESSAO}
        return req

    def test_exige_o_dono(self):
        from firebase_functions import https_fn

        with mock.patch("main.get_db", return_value=self.db):
            for req in (self._req("outro@example.com"), self._req("andre.martiini@gmail.com", False)):
                with self.assertRaises(https_fn.HttpsError):
                    tav.atender(req)
            self.assertNotIn(f"{tav.COLECAO}/{SESSAO}", self.db.docs)
            r = tav.atender(self._req("andre.martiini@gmail.com"))
        self.assertEqual(r["status"], "criada")
        self.assertEqual(self.sessao()["uid"], "uid-x")

    def test_erro_vira_https_error(self):
        from firebase_functions import https_fn

        req = self._req("andre.martiini@gmail.com")
        req.data = {"acao": "anexar", "sessao_id": "nao-existe-123", "lote_id": "lote-000000001",
                    "base_seq": 0, "trechos": [_trecho("x")]}
        with mock.patch("main.get_db", return_value=self.db), self.assertRaises(https_fn.HttpsError) as ctx:
            tav.atender(req)
        self.assertEqual(ctx.exception.code, https_fn.FunctionsErrorCode.NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
