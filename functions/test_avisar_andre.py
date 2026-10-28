"""avisar_andre: o aviso de uma sessão do Claude vira item da fila de atenção, com a ação do
Gaspar e os links no texto que o agente (ou o bot antigo) entrega. Sem rede e sem Firestore."""

import unittest
from datetime import datetime

import atencao
from test_secretario_whatsapp import _MockDb
from tools import avisar_andre, hermes_tools
from tools.tool_context import ToolContext


def _ctx(db):
    return ToolContext(_db=db)


def _itens(db):
    return [d.to_dict() for d in db.collection(atencao.COLLECTION).stream()]


class TestAvisar(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()
        self.db.collection("tarefas").document("acao-1").set({"titulo": "Tutoriais do Sistema X"})

    def test_grava_item_de_prioridade_alta_com_sugestao_vazia(self):
        r = avisar_andre.avisar(self.db, "Vídeos prontos", "Os 4 vídeos foram gerados.", sessao="Claude Code")
        (item,) = _itens(self.db)
        self.assertEqual((item["origem"], item["tipo"]), ("sessao", "notificacao_sessao"))
        self.assertEqual((item["prioridade"], item["estado"]), (atencao.PRIORIDADE_ALTA, atencao.ESTADO_ABERTO))
        # O bot antigo imprime a sugestao no texto: vazia, para o aviso sair limpo sem o agente.
        self.assertEqual(item["sugestao"], "")
        self.assertEqual(item["resumo"], "Os 4 vídeos foram gerados.\nSessão: Claude Code")
        self.assertIsNone(item["prazo_origem"])
        self.assertEqual(r["item_id"], item["chave_dedupe"])
        self.assertEqual(r["estado"], atencao.ESTADO_ABERTO)

    def test_acao_do_gaspar_entra_no_campo_e_no_texto(self):
        r = avisar_andre.avisar(self.db, "Vídeos prontos", "Prontos.", acao_id="acao-1")
        (item,) = _itens(self.db)
        self.assertEqual(item["acao_id"], "acao-1")
        self.assertIn("Ação do Gaspar: Tutoriais do Sistema X", item["resumo"])
        self.assertEqual(item["evidencia"]["acao_titulo"], "Tutoriais do Sistema X")
        self.assertEqual(r["acao"], "Tutoriais do Sistema X")
        self.assertNotIn("aviso", r)

    def test_sem_acao_o_texto_nao_menciona_acao(self):
        avisar_andre.avisar(self.db, "Deploy falhou", "2 testes quebraram.")
        (item,) = _itens(self.db)
        self.assertIsNone(item["acao_id"])
        self.assertNotIn("Ação do Gaspar", item["resumo"])

    def test_acao_inexistente_nao_derruba_o_aviso(self):
        r = avisar_andre.avisar(self.db, "Vídeos prontos", "Prontos.", acao_id="nao-existe")
        (item,) = _itens(self.db)
        self.assertIsNone(item["acao_id"])
        self.assertNotIn("Ação do Gaspar", item["resumo"])
        self.assertIn("nao-existe", r["aviso"])

    def test_links_entram_no_texto_com_e_sem_titulo(self):
        avisar_andre.avisar(self.db, "Vídeos prontos", "Prontos.", links=[
            {"url": "https://drive.google.com/a", "titulo": "Vídeo 1 - Login"},
            {"url": "https://drive.google.com/b"},
            "http://exemplo.com/c",
        ])
        (item,) = _itens(self.db)
        self.assertEqual(item["resumo"].splitlines()[1:], [
            "Links:",
            "- Vídeo 1 - Login: https://drive.google.com/a",
            "- https://drive.google.com/b",
            "- http://exemplo.com/c",
        ])
        self.assertEqual(len(item["evidencia"]["links"]), 3)

    def test_urgencia_critica_grava_prazo_de_hoje(self):
        hoje = datetime.now(atencao._TZ_SP).strftime("%Y-%m-%d")
        avisar_andre.avisar(self.db, "Preciso de você", "Travou.", urgencia="critica")
        avisar_andre.avisar(self.db, "Prontos", "Ok.")
        criticos = {i["titulo"]: i["prazo_origem"] for i in _itens(self.db)}
        self.assertEqual(criticos, {"Preciso de você": hoje, "Prontos": None})

    def test_segundo_aviso_nao_e_engolido_nem_depois_de_resolver_o_primeiro(self):
        a = avisar_andre.avisar(self.db, "Prontos", "Ok.")
        b = avisar_andre.avisar(self.db, "Prontos", "Ok.")
        self.assertNotEqual(a["item_id"], b["item_id"])
        # `_persistir_itens_atencao` não reabre item fechado com a mesma chave: com chave única, o
        # aviso seguinte nasce aberto mesmo com o anterior já resolvido.
        self.db.collection(atencao.COLLECTION).document(a["item_id"]).update({"estado": atencao.ESTADO_RESOLVIDO})
        c = avisar_andre.avisar(self.db, "Prontos", "Ok.")
        self.assertEqual(c["estado"], atencao.ESTADO_ABERTO)
        self.assertEqual(len(_itens(self.db)), 3)


class TestValidacao(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()

    def _erro(self, **args):
        resposta = hermes_tools.execute("avisar_andre", args, _ctx(self.db))
        self.assertTrue(str(resposta).startswith("ERRO|"), resposta)
        self.assertEqual(_itens(self.db), [], "aviso invalido nao pode gravar nada")

    def test_titulo_e_resumo_obrigatorios_e_com_limite(self):
        self._erro(titulo="   ", resumo="x")
        self._erro(titulo="x", resumo="  ")
        self._erro(titulo="x" * (avisar_andre.LIMITE_TITULO + 1), resumo="x")
        self._erro(titulo="x", resumo="x" * (avisar_andre.LIMITE_RESUMO + 1))
        self._erro(titulo="x", resumo="x", sessao="s" * (avisar_andre.LIMITE_SESSAO + 1))

    def test_urgencia_invalida(self):
        self._erro(titulo="x", resumo="x", urgencia="urgentissima")

    def test_link_invalido_barra_o_aviso_inteiro(self):
        for url in ("javascript:alert(1)", "drive.google.com/a", "https://", "https://a.com/com espaco",
                    "https://a.com/" + "x" * avisar_andre.LIMITE_URL, "ftp://a.com/x", ""):
            with self.subTest(url=url):
                self._erro(titulo="x", resumo="x", links=[{"url": url}])

    def test_links_demais_e_formato_errado(self):
        self._erro(titulo="x", resumo="x", links=["https://a.com/%d" % i for i in range(avisar_andre.MAX_LINKS + 1)])
        self._erro(titulo="x", resumo="x", links="https://a.com")

    def test_handler_devolve_o_resultado_quando_valido(self):
        r = hermes_tools.execute("avisar_andre", {"titulo": "Prontos", "resumo": "Ok."}, _ctx(self.db))
        self.assertEqual(r["estado"], atencao.ESTADO_ABERTO)


if __name__ == "__main__":
    unittest.main()
