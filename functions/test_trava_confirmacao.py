"""Trava de confirmação (PR 2 do plano "confirmação verificada").

Nenhuma resposta diz "registrei/criei/agendei" sem uma escrita relida no mesmo
turno. Começa só registrando os casos (modo "registrar"); o modo "bloquear"
substitui o texto.
"""

import json
import unittest
from unittest import mock

import trava_confirmacao as tc
from test_registrar_saude import _Colecao, _Db
from verificacao import ResultadoOperacao


class _ColecaoAdd(_Colecao):
    def add(self, dados):
        ref = self.document()
        ref.set(dados)
        return None, ref


class _DbAdd(_Db):
    def collection(self, nome):
        return self.cols.setdefault(nome, _ColecaoAdd())


def _db_modo(modo=None, verbos=None):
    db = _DbAdd()
    cfg = {}
    if modo:
        cfg["modo"] = modo
    if verbos:
        cfg["verbos"] = verbos
    db.collection("system").dados["settings"] = {"trava_confirmacao": cfg} if cfg else {}
    return db


def _casos(db):
    return list(db.cols[tc.COLECAO_LOG].dados.values()) if tc.COLECAO_LOG in db.cols else []


class _SemCache(unittest.TestCase):
    def setUp(self):
        tc._CACHE_CFG.update(em=0.0, valor=None)


class TestVerbos(_SemCache):
    def test_acha_verbos_de_conclusao(self):
        self.assertEqual(tc.verbos_de_conclusao("Pronto, registrei o peso e criei a ação."), ["registrei", "criei"])
        self.assertEqual(tc.verbos_de_conclusao("Conclui a etapa 3."), ["concluí"])
        self.assertEqual(tc.verbos_de_conclusao("EXCLUÍ o lembrete."), ["excluí"])

    def test_ignora_negados_e_outros_tempos(self):
        for texto in ("Não registrei nada ainda.", "Ainda não enviei a mensagem.", "nunca criei essa ação",
                      "Quer que eu registre?", "Vou agendar amanhã.", "Você registrou ontem.", ""):
            with self.subTest(texto=texto):
                self.assertEqual(tc.verbos_de_conclusao(texto), [])

    def test_nao_confunde_parte_de_palavra(self):
        self.assertEqual(tc.verbos_de_conclusao("criei" + "ssimo"), [])


class TestAplicarTrava(_SemCache):
    def test_sem_verbo_passa(self):
        db = _db_modo()
        self.assertEqual(tc.aplicar_trava(db, "Sua agenda tem 2 reuniões.", []), "Sua agenda tem 2 reuniões.")
        self.assertEqual(_casos(db), [])

    def test_verbo_com_escrita_verificada_passa(self):
        db = _db_modo("bloquear")
        chamadas = [{"name": "criar_acao_no_sistema", "estado": "verificado"}]
        self.assertEqual(tc.aplicar_trava(db, "Criei a ação.", chamadas), "Criei a ação.")
        self.assertEqual(_casos(db), [])

    def test_modo_registrar_nao_muda_o_texto_mas_registra(self):
        db = _db_modo()
        texto = "Pronto! Registrei sua consulta de amanhã às 10h. Mais algo?"
        self.assertEqual(tc.aplicar_trava(db, texto, [{"name": "consultar_agenda"}], canal="telegram"), texto)
        [caso] = _casos(db)
        self.assertEqual(caso["modo"], "registrar")
        self.assertFalse(caso["substituida"])
        self.assertEqual(caso["verbos"], ["registrei"])
        self.assertEqual(caso["canal"], "telegram")
        self.assertEqual(caso["trecho"], "Registrei sua consulta de amanhã às 10h.")
        self.assertEqual(caso["ferramentas"], [{"nome": "consultar_agenda", "estado": None}])
        self.assertGreater(caso["expira_em"], caso["criado_em"])

    def test_modo_bloquear_substitui_sem_nenhuma_escrita(self):
        db = _db_modo("bloquear")
        self.assertEqual(tc.aplicar_trava(db, "Agendei sua consulta.", []), tc.MENSAGEM_SEM_ACAO)
        self.assertTrue(_casos(db)[0]["substituida"])

    def test_modo_bloquear_com_falha_diz_o_motivo(self):
        db = _db_modo("bloquear")
        falha = ResultadoOperacao("falhou", "criar_acao_no_sistema", "tarefas", motivo="sem permissão").to_dict()
        texto = tc.aplicar_trava(db, "Criei a ação.", [{"name": "criar_acao_no_sistema", "estado": "falhou",
                                                         "resultado": falha}])
        self.assertEqual(texto, "Não consegui concluir a operação: sem permissão")

    def test_proposta_pendente_nao_conta_como_feito(self):
        db = _db_modo("bloquear")
        chamadas = [{"name": "propor_acao_para_confirmacao", "estado": "pendente"}]
        self.assertEqual(tc.aplicar_trava(db, "Criei a ação para você.", chamadas), tc.MENSAGEM_SEM_ACAO)

    def test_modo_desligado_nao_faz_nada(self):
        db = _db_modo("desligado")
        self.assertEqual(tc.aplicar_trava(db, "Registrei.", []), "Registrei.")
        self.assertEqual(_casos(db), [])

    def test_verbos_configuraveis(self):
        db = _db_modo("bloquear", verbos=["finalizei"])
        self.assertEqual(tc.aplicar_trava(db, "Registrei.", []), "Registrei.")
        tc._CACHE_CFG.update(em=0.0, valor=None)
        self.assertEqual(tc.aplicar_trava(db, "Finalizei.", []), tc.MENSAGEM_SEM_ACAO)

    def test_modo_invalido_vira_registrar(self):
        db = _db_modo("qualquer")
        self.assertEqual(tc.config(db)["modo"], "registrar")

    def test_falha_ao_registrar_caso_nao_derruba_a_resposta(self):
        db = _db_modo()
        with mock.patch.object(db, "collection", side_effect=[db.cols["system"], RuntimeError("fora")]):
            self.assertEqual(tc.aplicar_trava(db, "Registrei.", []), "Registrei.")


class TestAnotarResultado(unittest.TestCase):
    def _res(self, estado="verificado"):
        if estado == "falhou":
            return ResultadoOperacao("falhou", "x", "tarefas/1", motivo="não aparece")
        return ResultadoOperacao(estado, "x", "tarefas/1")

    def test_json_continua_json(self):
        texto = tc.anotar_resultado('{"status": "saved", "id": "k1"}', self._res())
        dados = json.loads(texto)
        self.assertEqual(dados["id"], "k1")
        self.assertEqual(dados["verificacao"], {"ok": True, "estado": "verificado", "alvo": "tarefas/1"})

    def test_texto_ganha_linha(self):
        texto = tc.anotar_resultado("OK|abc", self._res("falhou"))
        self.assertTrue(texto.startswith("OK|abc\n[verificacao: "))
        self.assertIn('"motivo": "não aparece"', texto)

    def test_dict_ganha_chave(self):
        self.assertEqual(tc.anotar_resultado({"a": 1}, self._res())["verificacao"]["estado"], "verificado")

    def test_sem_verificacao_nao_muda(self):
        self.assertEqual(tc.anotar_resultado("texto", None), "texto")

    def test_proposta_nao_e_anotada_porque_o_cartao_rele_o_json(self):
        bruto = '{"task_id": "t1", "alteracoes": {"titulo": "X"}}'
        res = tc.verificar_ferramenta(_DbAdd(), "preparar_edicao_acao", {}, bruto)
        self.assertEqual(res.estado, "pendente")
        self.assertEqual(tc.anotar_resultado(bruto, res), bruto)

    def test_anotar_chamada(self):
        chamada = {"name": "x"}
        tc.anotar_chamada(chamada, self._res())
        self.assertEqual(chamada["estado"], "verificado")
        self.assertEqual(chamada["resultado"]["alvo"], "tarefas/1")


class TestVerificarFerramenta(unittest.TestCase):
    def test_leitura_nao_tem_verificacao(self):
        self.assertIsNone(tc.verificar_ferramenta(_Db(), "consultar_agenda", {}, "..."))

    def test_verificador_que_explode_vira_falhou(self):
        with mock.patch.dict(tc.VERIFICADORES, {"x": mock.Mock(side_effect=RuntimeError("bug"))}):
            res = tc.verificar_ferramenta(_Db(), "x", {}, "OK")
        self.assertEqual(res.estado, "falhou")
        self.assertIn("bug", res.motivo)


if __name__ == "__main__":
    unittest.main()


class TestLigacaoNosLacos(unittest.TestCase):
    """Os três lugares onde o copiloto executa ferramentas passam pela trava."""

    def _fonte(self, arquivo):
        with open(arquivo, encoding="utf-8") as f:
            return f.read()

    def test_copiloto_web_verifica_cada_ferramenta_e_trava_a_resposta(self):
        fonte = self._fonte("main.py")
        self.assertIn("_verif = _trava_verificar(db, fc.name, fc.args, res)", fonte)
        self.assertIn("_trava_anotar_chamada(_chamada, _verif)", fonte)
        self.assertIn("result_text = _trava_aplicar(", fonte)
        self.assertIn("+ _TRAVA_REGRA_PROMPT", fonte)

    def test_telegram_de_reserva_verifica_e_trava(self):
        self.assertIn("verificacao = verificar_ferramenta(db, fc.name, kwargs, result_text)",
                      self._fonte("telegram_utils.py"))
        self.assertIn("response_text = aplicar_trava(db, response_text", self._fonte("telegram_handlers_core.py"))

    def test_mcp_anota_execucao_direta_e_confirmada(self):
        fonte = self._fonte("mcp_server.py")
        self.assertIn("result = _trava_mcp(ctx, name, arguments, result)", fonte)
        self.assertIn("result = _trava_mcp(ctx, nome, argumentos, result)", fonte)
