"""Tools de leitura da transcrição ao vivo (functions/tools/transcricao_ao_vivo_tools.py)."""
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import transcricao_ao_vivo as tav
from fake_firestore_transcricao import FakeDb, em_transacao_falsa
from tools import transcricao_ao_vivo_tools as tools
from tools.tool_context import ToolContext

INICIO = datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)


class _Base(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.agora = INICIO
        relogio = lambda: self.agora  # noqa: E731
        for p in (mock.patch.object(tav, "_em_transacao", em_transacao_falsa),
                  mock.patch.object(tav, "_agora", relogio),
                  mock.patch.object(tools, "_agora", relogio)):
            p.start()
            self.addCleanup(p.stop)
        self.ctx = ToolContext(user_uid="uid-dono", _db=self.db)
        self.lotes = 0

    def iniciar(self, sessao_id, titulo="Webinário"):
        tav.processar(self.db, "uid-dono", {"acao": "iniciar", "sessao_id": sessao_id, "titulo": titulo})

    def falar(self, sessao_id, *textos, falante="Reunião"):
        """Um lote com um trecho por texto, gravado no `self.agora` atual."""
        self.lotes += 1
        base = self.db.docs[f"{tav.COLECAO}/{sessao_id}"]["ultimo_seq"]
        trechos = [{"texto": t, "falante": falante, "t_inicio": base + i, "t_fim": base + i + 1}
                   for i, t in enumerate(textos)]
        r = tav.processar(self.db, "u", {"acao": "anexar", "sessao_id": sessao_id,
                                         "lote_id": f"lote-{self.lotes:010d}", "base_seq": base, "trechos": trechos})
        self.assertEqual(r["status"], "gravado")

    def encerrar(self, sessao_id):
        tav.processar(self.db, "u", {"acao": "encerrar", "sessao_id": sessao_id})

    def ler(self, **args):
        return tools.ler(self.ctx, args)


class TestListar(_Base):
    def test_ativas_mais_recente_primeiro_e_sem_abandonadas(self):
        self.iniciar("sessao-antiga-01", "Antiga")
        self.agora += timedelta(minutes=40)
        self.iniciar("sessao-ativa-001", "Ativa A")
        self.agora += timedelta(minutes=1)
        self.iniciar("sessao-ativa-002", "Ativa B")
        self.falar("sessao-ativa-002", "olá")
        self.iniciar("sessao-fim-0001", "Encerrada")
        self.encerrar("sessao-fim-0001")
        self.agora += timedelta(seconds=20)

        r = tools.listar(self.ctx, {})
        self.assertTrue(r["apenas_ativas"])
        self.assertEqual([s["sessao_id"] for s in r["sessoes"]], ["sessao-ativa-002", "sessao-ativa-001"])
        b = r["sessoes"][0]
        self.assertEqual(b["estado"], "ao_vivo")
        self.assertEqual(b["ultimo_seq"], 1)
        self.assertEqual(b["segundos_desde_ultimo_trecho"], 20)
        self.assertFalse(b["sem_sinal"])
        self.assertEqual(b["iniciada_em"], "2026-10-19T10:41:00-03:00")
        self.assertIsNone(r["sessoes"][1]["segundos_desde_ultimo_trecho"])
        self.assertIn("apos_seq", r["orientacao"])

    def test_todas_inclui_encerradas(self):
        self.iniciar("sessao-fim-0001", "Encerrada")
        self.encerrar("sessao-fim-0001")
        self.assertEqual(tools.listar(self.ctx, {})["sessoes"], [])
        r = tools.listar(self.ctx, {"apenas_ativas": False})
        self.assertEqual(r["sessoes"][0]["estado"], "encerrada")
        self.assertEqual(tools.listar(self.ctx, {"apenas_ativas": "false"})["total"], 1)

    def test_sem_sinal_depois_de_dois_minutos(self):
        self.iniciar("sessao-ativa-001")
        self.agora += timedelta(seconds=tools.SEM_SINAL_S + 1)
        self.assertTrue(tools.listar(self.ctx, {})["sessoes"][0]["sem_sinal"])

    def test_limite(self):
        for i in range(5):
            self.iniciar(f"sessao-ativa-{i:03d}")
        self.assertEqual(len(tools.listar(self.ctx, {"limite": 2})["sessoes"]), 2)
        self.assertEqual(len(tools.listar(self.ctx, {"limite": "x"})["sessoes"]), 5)

    def test_vazia_orienta(self):
        r = tools.listar(self.ctx, {})
        self.assertEqual(r["total"], 0)
        self.assertIn("Reuniões em Tempo Real", r["orientacao"])


class TestLerCursor(_Base):
    def setUp(self):
        super().setUp()
        self.iniciar("sessao-ativa-001")
        self.falar("sessao-ativa-001", "um", "dois")
        self.falar("sessao-ativa-001", "três", falante="Você")

    def test_le_desde_o_inicio_e_depois_so_o_novo(self):
        r = self.ler(sessao_id="sessao-ativa-001")
        self.assertEqual([t["seq"] for t in r["trechos"]], [1, 2, 3])
        self.assertEqual(r["trechos"][2], {"seq": 3, "t_inicio": 2.0, "t_fim": 3.0, "falante": "Você", "texto": "três"})
        self.assertEqual((r["proximo_seq"], r["ultimo_seq"], r["truncado"]), (3, 3, False))
        self.assertEqual(r["estado"], "ao_vivo")
        self.assertIn("apos_seq=3", r["orientacao"])

        vazio = self.ler(sessao_id="sessao-ativa-001", apos_seq=3)
        self.assertEqual((vazio["trechos"], vazio["proximo_seq"], vazio["truncado"]), ([], 3, False))

        self.agora += timedelta(seconds=10)
        self.falar("sessao-ativa-001", "quatro")
        novo = self.ler(sessao_id="sessao-ativa-001", apos_seq=3)
        self.assertEqual([t["texto"] for t in novo["trechos"]], ["quatro"])
        self.assertEqual(novo["proximo_seq"], 4)

    def test_idempotente(self):
        a = self.ler(sessao_id="sessao-ativa-001", apos_seq=1)
        b = self.ler(sessao_id="sessao-ativa-001", apos_seq=1)
        self.assertEqual(a, b)
        self.assertEqual([t["seq"] for t in a["trechos"]], [2, 3])

    def test_mais_recente_ativa_e_padrao(self):
        self.agora += timedelta(seconds=5)
        self.iniciar("sessao-ativa-002", "Outra")
        self.falar("sessao-ativa-002", "da outra")
        self.assertEqual(self.ler()["sessao_id"], "sessao-ativa-002")
        self.assertEqual(self.ler(sessao_id="mais_recente_ativa")["trechos"][0]["texto"], "da outra")

    def test_sem_sessao_ativa(self):
        self.encerrar("sessao-ativa-001")
        r = self.ler()
        self.assertIn("erro", r)
        self.assertIn("apenas_ativas=false", r["orientacao"])

    def test_inexistente_e_id_com_barra(self):
        self.assertIn("erro", self.ler(sessao_id="nao-existe-000"))
        self.assertIn("erro", self.ler(sessao_id="a/b"))

    def test_cursor_alem_do_fim_nao_quebra(self):
        r = self.ler(sessao_id="sessao-ativa-001", apos_seq=99)
        self.assertEqual((r["trechos"], r["proximo_seq"], r["truncado"]), ([], 99, False))

    def test_cursor_invalido_vira_inicio(self):
        r = self.ler(sessao_id="sessao-ativa-001", apos_seq="abc")
        self.assertEqual(len(r["trechos"]), 3)
        r = self.ler(sessao_id="sessao-ativa-001", apos_seq=-5)
        self.assertEqual(len(r["trechos"]), 3)

    def test_atraso_e_sem_sinal(self):
        self.agora += timedelta(seconds=25)
        r = self.ler(sessao_id="sessao-ativa-001", apos_seq=3)
        self.assertEqual(r["atraso_segundos"], 25)
        self.assertFalse(r["sem_sinal"])
        self.agora += timedelta(seconds=tools.SEM_SINAL_S)
        r = self.ler(sessao_id="sessao-ativa-001", apos_seq=3)
        self.assertTrue(r["sem_sinal"])
        self.assertIn("parou de mandar sinal", r["orientacao"])


class TestTruncamento(_Base):
    def setUp(self):
        super().setUp()
        self.iniciar("sessao-longa-001")
        self.falar("sessao-longa-001", *[f"{i:02d}" + "x" * 498 for i in range(30)])  # 30 trechos de 500

    def test_corta_em_trecho_inteiro_e_continua_pelo_cursor(self):
        r = self.ler(sessao_id="sessao-longa-001", max_caracteres=2000)
        self.assertEqual([t["seq"] for t in r["trechos"]], [1, 2, 3, 4])
        self.assertTrue(r["truncado"])
        self.assertEqual(r["proximo_seq"], 4)
        self.assertEqual(r["caracteres"], 2000)
        self.assertIn("apos_seq=4", r["orientacao"])

        vistos, cursor = [], 0
        for _ in range(20):  # sem avanço do cursor, o teste falha em vez de travar
            r = self.ler(sessao_id="sessao-longa-001", apos_seq=cursor, max_caracteres=2000)
            vistos += [t["seq"] for t in r["trechos"]]
            cursor = r["proximo_seq"]
            if not r["truncado"]:
                break
        self.assertFalse(r["truncado"])
        self.assertEqual(vistos, list(range(1, 31)))

    def test_padrao_12000_e_limites(self):
        r = self.ler(sessao_id="sessao-longa-001")
        self.assertEqual(len(r["trechos"]), 24)
        r = self.ler(sessao_id="sessao-longa-001", max_caracteres=10)  # sobe para o mínimo de 1000
        self.assertEqual(len(r["trechos"]), 2)
        r = self.ler(sessao_id="sessao-longa-001", max_caracteres=10**9)
        self.assertEqual(len(r["trechos"]), 30)
        self.assertFalse(r["truncado"])

    def test_trecho_maior_que_o_teto_vem_sozinho(self):
        self.iniciar("sessao-grande-01")
        self.falar("sessao-grande-01", "y" * 3500, "z")
        r = self.ler(sessao_id="sessao-grande-01", max_caracteres=1000)
        self.assertEqual([t["seq"] for t in r["trechos"]], [1])
        self.assertTrue(r["truncado"])


class TestUltimosMinutos(_Base):
    def setUp(self):
        super().setUp()
        self.iniciar("sessao-ativa-001")
        for i in range(6):  # um lote por minuto, de 13:00 a 13:05
            self.falar("sessao-ativa-001", f"minuto {i}")
            self.agora += timedelta(minutes=1)
        # agora = 13:06

    def test_so_o_final(self):
        r = self.ler(sessao_id="sessao-ativa-001", ultimos_minutos=3)
        self.assertEqual([t["texto"] for t in r["trechos"]], ["minuto 3", "minuto 4", "minuto 5"])
        self.assertEqual(r["apos_seq"], 3)

    def test_apos_seq_tem_prioridade(self):
        r = self.ler(sessao_id="sessao-ativa-001", ultimos_minutos=3, apos_seq=1)
        self.assertEqual(r["trechos"][0]["seq"], 2)

    def test_janela_sem_trecho_nao_devolve_nada_e_aponta_o_fim(self):
        self.agora += timedelta(minutes=30)
        r = self.ler(sessao_id="sessao-ativa-001", ultimos_minutos=5)
        self.assertEqual((r["trechos"], r["proximo_seq"]), ([], 6))


class TestEncerrada(_Base):
    def test_le_depois_de_encerrar(self):
        self.iniciar("sessao-ativa-001")
        self.falar("sessao-ativa-001", "um", "dois")
        r1 = self.ler(sessao_id="sessao-ativa-001", apos_seq=1)
        self.encerrar("sessao-ativa-001")
        self.agora += timedelta(hours=3)
        r2 = self.ler(sessao_id="sessao-ativa-001", apos_seq=1)
        self.assertEqual(r2["estado"], "encerrada")
        self.assertEqual(r2["trechos"], r1["trechos"])
        self.assertFalse(r2["sem_sinal"])
        self.assertIn("encerrada", r2["orientacao"])
        self.assertEqual(self.ler(sessao_id="sessao-ativa-001", apos_seq=2)["trechos"], [])


class TestRegistro(unittest.TestCase):
    def test_tools_registradas_e_so_leitura(self):
        from autonomy import policy
        from tools import hermes_tools, inventory, registry

        for nome in ("listar_transcricoes_ao_vivo", "ler_transcricao_ao_vivo"):
            self.assertIn(nome, hermes_tools._HANDLERS)
            self.assertIn(nome, registry._CATALOG)
            entrada = inventory._INVENTORY[nome]
            self.assertEqual(entrada.leitura_escrita, inventory.LeituraEscrita.LEITURA)
            self.assertFalse(entrada.necessidade_de_rede)
            caminho = os.path.join(os.path.dirname(__file__), "tools", "schemas", f"{nome}.json")
            with open(caminho, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["name"], nome)
            self.assertNotIn(nome, policy.FLOOR_CONFIRMACAO_OBRIGATORIA)
        self.assertIn("ler_transcricao_ao_vivo", registry._VOICE_EXCLUDED)

    def test_execute_pelo_despachante(self):
        from tools import hermes_tools

        db = FakeDb()
        with mock.patch.object(tav, "_em_transacao", em_transacao_falsa):
            tav.processar(db, "u", {"acao": "iniciar", "sessao_id": "sessao-ativa-001"})
        ctx = ToolContext(user_uid="uid-dono", _db=db)
        r = hermes_tools.execute("ler_transcricao_ao_vivo", {"sessao_id": "sessao-ativa-001"}, ctx)
        self.assertEqual(r["sessao_id"], "sessao-ativa-001")
        self.assertEqual(r["trechos"], [])
        r = hermes_tools.execute("listar_transcricoes_ao_vivo", {}, ctx)
        self.assertEqual(r["total"], 1)


if __name__ == "__main__":
    unittest.main()
