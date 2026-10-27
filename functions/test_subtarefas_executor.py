"""Campo `executor` da etapa: quem faz, como, e quem fixou.

O que protege: a marca nunca some em silêncio e a escolha do André nunca é
desfeita pelo agente. Os dois são falhas silenciosas — a etapa continua lá,
só que sem a etiqueta ou com a etiqueta trocada.
"""

import unittest

import morning_summary
import subtarefas as st
from test_morning_summary import HOJE, _acoes, _tarefa
from test_outbox_aprovacao import _MockDb
from tools import hermes_tools, telegram_extended
from tools.tool_context import ToolContext


def _plano():
    return [
        {"id": "a1", "text": "Ler o relatório", "completed": False, "estado": "pendente",
         "executor": "agente", "executor_como": "Ler e montar a versão executiva",
         "executor_definido_por": "agente"},
        {"id": "a2", "text": "Mandar a mensagem ao Gustavo", "completed": False, "estado": "pendente",
         "executor": "agente_aprovado", "executor_definido_por": "agente"},
        {"id": "a3", "text": "Assinar o despacho", "completed": False, "estado": "pendente"},
        {"id": "a4", "text": "Conferir o SIGFAPES", "completed": False, "estado": "pendente",
         "executor": "humano", "executor_definido_por": "usuario"},
        {"id": "a5", "text": "Arquivar", "completed": True, "estado": "feito", "executor": "agente",
         "executor_definido_por": "agente"},
    ]


class TestLeitura(unittest.TestCase):

    def test_ausente_e_desconhecido_leem_como_humano(self):
        self.assertEqual(st.executor_de({"text": "x"}), "humano")
        self.assertEqual(st.executor_de({"executor": "claude"}), "humano")
        self.assertEqual(st.executor_de({"executor": None}), "humano")
        self.assertEqual(st.executor_de("texto puro"), "humano")

    def test_os_tres_valores_validos(self):
        for valor in ("agente", "agente_aprovado", "humano"):
            self.assertEqual(st.executor_de({"executor": valor}), valor)
        self.assertEqual(st.executor_de({"executor": " AGENTE "}), "agente")

    def test_contagem_so_conta_etapa_em_aberto_do_agente_e_do_agente_aprovado(self):
        # a1 (agente) + a2 (agente_aprovado); a3 humano, a4 humano, a5 feita.
        self.assertEqual(st.contar_para_agente(_plano()), 2)

    def test_contagem_muda_quando_a_etapa_e_concluida(self):
        plano = _plano()
        plano[0] = {**plano[0], "estado": "feito", "completed": True}
        self.assertEqual(st.contar_para_agente(plano), 1)

    def test_contagem_ignora_etapa_sem_texto_e_plano_vazio(self):
        self.assertEqual(st.contar_para_agente(None), 0)
        self.assertEqual(st.contar_para_agente([{"id": "z", "text": "", "executor": "agente"}]), 0)


class TestNormalizar(unittest.TestCase):

    def test_valor_desconhecido_vira_humano(self):
        self.assertEqual(st.normalizar({"text": "x", "executor": "claude"})["executor"], "humano")

    def test_ausente_continua_ausente(self):
        norm = st.normalizar({"text": "x"})
        for campo in ("executor", "executor_como", "executor_definido_por"):
            self.assertNotIn(campo, norm)

    def test_humano_explicito_fica_gravado(self):
        self.assertEqual(st.normalizar({"text": "x", "executor": "humano"})["executor"], "humano")

    def test_os_tres_campos_sobrevivem_a_normalizacao(self):
        norm = st.normalizar(_plano()[0])
        self.assertEqual(norm["executor"], "agente")
        self.assertEqual(norm["executor_como"], "Ler e montar a versão executiva")
        self.assertEqual(norm["executor_definido_por"], "agente")

    def test_executor_como_e_cortado_em_140(self):
        norm = st.normalizar({"text": "x", "executor": "agente", "executor_como": "a" * 200})
        self.assertEqual(len(norm["executor_como"]), 140)

    def test_marca_de_autoria_invalida_e_descartada(self):
        norm = st.normalizar({"text": "x", "executor": "agente", "executor_definido_por": "claude"})
        self.assertNotIn("executor_definido_por", norm)

    def test_converter_plano_marca_o_agente_e_ignora_marca_enviada(self):
        plano = st.converter_plano([
            {"text": "Redigir", "executor": "agente_aprovado", "executor_definido_por": "usuario"},
            "Passo simples",
        ])
        self.assertEqual(plano[0]["executor"], "agente_aprovado")
        self.assertEqual(plano[0]["executor_definido_por"], "agente")
        self.assertNotIn("executor", plano[1])


class TestPreservacao(unittest.TestCase):
    """Nenhuma gravação de plano pode apagar a marca."""

    def test_editar_estado_preserva_os_tres_campos(self):
        ed = st.editar_plano(_plano(), [{"id": "a1", "estado": "em_andamento"}])
        a1 = ed.plano[0]
        self.assertEqual(a1["estado"], "em_andamento")
        self.assertEqual((a1["executor"], a1["executor_como"], a1["executor_definido_por"]),
                         ("agente", "Ler e montar a versão executiva", "agente"))

    def test_reordenar_com_substituir_preserva(self):
        ordem = ["a5", "a4", "a3", "a2", "a1"]
        ed = st.editar_plano(_plano(), [{"id": i} for i in ordem], modo="substituir")
        por_id = {p["id"]: p for p in ed.plano}
        self.assertEqual(por_id["a1"]["executor_como"], "Ler e montar a versão executiva")
        self.assertEqual(por_id["a4"]["executor"], "humano")
        self.assertEqual(por_id["a4"]["executor_definido_por"], "usuario")

    def test_restaurar_da_lixeira_preserva(self):
        removida = {"id": "a1", "etapa": _plano()[0], "posicao": 0}
        ed = st.editar_plano(_plano()[1:], [{"id": "a1", "restaurar": True}], etapas_removidas=[removida])
        restaurada = next(p for p in ed.plano if p["id"] == "a1")
        self.assertEqual(restaurada["executor"], "agente")
        self.assertEqual(restaurada["executor_como"], "Ler e montar a versão executiva")

    def test_agente_define_o_executor_de_etapa_sem_marca(self):
        ed = st.editar_plano(_plano(), [{"id": "a3", "executor": "agente_aprovado",
                                         "executor_como": "Preparar o despacho"}])
        a3 = ed.plano[2]
        self.assertEqual(a3["executor"], "agente_aprovado")
        self.assertEqual(a3["executor_definido_por"], "agente")
        self.assertEqual(st.diferencas(_plano(), ed.plano)["alteradas"]["a3"]["executor"],
                         [None, "agente_aprovado"])

    def test_executor_como_null_apaga(self):
        ed = st.editar_plano(_plano(), [{"id": "a1", "executor_como": None}])
        self.assertNotIn("executor_como", ed.plano[0])
        self.assertEqual(ed.plano[0]["executor"], "agente")

    def test_etapa_nova_com_executor_fica_marcada_como_do_agente(self):
        ed = st.editar_plano(_plano(), [{"text": "Pesquisar preços", "executor": "agente"}])
        nova = ed.plano[-1]
        self.assertEqual((nova["executor"], nova["executor_definido_por"]), ("agente", "agente"))

    def test_agente_nao_escolhe_a_marca_de_autoria(self):
        ed = st.editar_plano(_plano(), [{"id": "a3", "executor": "agente",
                                         "executor_definido_por": "usuario"}])
        self.assertEqual(ed.plano[2]["executor_definido_por"], "agente")


class TestEscolhaDoAndre(unittest.TestCase):
    """Etapa que o André corrigiu na tela (`executor_definido_por == usuario`)."""

    def test_agente_nao_sobrescreve_o_executor(self):
        with self.assertRaises(st.PlanoInvalido) as ctx:
            st.editar_plano(_plano(), [{"id": "a4", "executor": "agente"}])
        self.assertIn("fixado pelo Andre", str(ctx.exception))

    def test_agente_nao_sobrescreve_o_executor_como(self):
        plano = _plano()
        plano[3] = {**plano[3], "executor": "agente_aprovado", "executor_como": "Texto do André"}
        with self.assertRaises(st.PlanoInvalido):
            st.editar_plano(plano, [{"id": "a4", "executor_como": "Outro texto"}])

    def test_agente_nao_apaga_o_executor_como(self):
        plano = _plano()
        plano[3] = {**plano[3], "executor": "agente", "executor_como": "Texto do André"}
        with self.assertRaises(st.PlanoInvalido):
            st.editar_plano(plano, [{"id": "a4", "executor_como": None}])

    def test_agente_nao_sobrescreve_em_substituir_nem_em_etapa_restaurada(self):
        with self.assertRaises(st.PlanoInvalido):
            st.editar_plano(_plano(), [{"id": i, **({"executor": "agente"} if i == "a4" else {})}
                                       for i in ("a1", "a2", "a3", "a4", "a5")], modo="substituir")
        removida = {"id": "a4", "etapa": _plano()[3], "posicao": 3}
        with self.assertRaises(st.PlanoInvalido):
            st.editar_plano([p for p in _plano() if p["id"] != "a4"],
                            [{"id": "a4", "restaurar": True, "executor": "agente"}],
                            etapas_removidas=[removida])

    def test_reenviar_o_mesmo_valor_nao_e_sobrescrita_e_mantem_a_marca(self):
        ed = st.editar_plano(_plano(), [{"id": "a4", "executor": "humano", "estado": "em_andamento"}])
        self.assertEqual(ed.plano[3]["estado"], "em_andamento")
        self.assertEqual(ed.plano[3]["executor"], "humano")
        self.assertEqual(ed.plano[3]["executor_definido_por"], "usuario")

    def test_editar_outros_campos_da_etapa_do_andre_continua_permitido(self):
        ed = st.editar_plano(_plano(), [{"id": "a4", "data_prevista": "2026-10-30"}])
        self.assertEqual(ed.plano[3]["data_prevista"], "2026-10-30")
        self.assertEqual(ed.plano[3]["executor"], "humano")

    def test_o_usuario_pode_corrigir_e_a_marca_vira_usuario(self):
        ed = st.editar_plano(_plano(), [{"id": "a1", "executor": "humano"}], por="usuario")
        self.assertEqual((ed.plano[0]["executor"], ed.plano[0]["executor_definido_por"]),
                         ("humano", "usuario"))

    def test_o_usuario_corrige_o_que_o_proprio_usuario_fixou(self):
        ed = st.editar_plano(_plano(), [{"id": "a4", "executor": "agente"}], por="usuario")
        self.assertEqual(ed.plano[3]["executor"], "agente")


class TestValidacaoDeEntrada(unittest.TestCase):

    def test_executor_invalido_e_recusado_na_edicao(self):
        with self.assertRaises(st.PlanoInvalido) as ctx:
            st.editar_plano(_plano(), [{"id": "a3", "executor": "claude"}])
        self.assertIn("agente, agente_aprovado, humano", str(ctx.exception))

    def test_executor_invalido_em_etapa_nova_tambem(self):
        with self.assertRaises(st.PlanoInvalido):
            st.editar_plano(_plano(), [{"text": "Nova", "executor": "robo"}])

    def test_executor_como_acima_de_140_e_recusado_na_edicao(self):
        with self.assertRaises(st.PlanoInvalido) as ctx:
            st.editar_plano(_plano(), [{"id": "a3", "executor": "agente", "executor_como": "x" * 141}])
        self.assertIn("140", str(ctx.exception))


class _BaseHandler(unittest.TestCase):
    TASK = "tarefa-exec"

    def setUp(self):
        self.db = _MockDb()
        self.db.collection("tarefas").document(self.TASK).set({
            "titulo": "Sispnaes", "data_limite": HOJE, "plano_acao": _plano()})

    def _plano(self):
        return self.db.collection("tarefas")._docs[self.TASK]["plano_acao"]

    def _etapa(self, **slots):
        return telegram_extended.execute("editar_etapa", {"task_id": self.TASK, **slots}, self.db)


class TestEditarEtapaComExecutor(_BaseHandler):

    def test_marca_etapa_como_do_agente(self):
        r = self._etapa(etapa_id="a3", executor="agente", executor_como="Preparar o despacho")
        self.assertTrue(r.startswith("OK|"), r)
        a3 = self._plano()[2]
        self.assertEqual((a3["executor"], a3["executor_como"], a3["executor_definido_por"]),
                         ("agente", "Preparar o despacho", "agente"))

    def test_omitir_preserva(self):
        self._etapa(etapa_id="a1", estado="em_andamento")
        a1 = self._plano()[0]
        self.assertEqual((a1["executor"], a1["executor_como"]), ("agente", "Ler e montar a versão executiva"))

    def test_recusa_sobrescrever_a_etapa_do_andre_sem_gravar(self):
        antes = self._plano()
        r = self._etapa(etapa_id="a4", executor="agente")
        self.assertTrue(r.startswith("ERRO|"), r)
        self.assertIn("Nada foi gravado", r)
        self.assertEqual(self._plano(), antes)

    def test_executor_invalido_e_erro_sem_gravar(self):
        antes = self._plano()
        r = self._etapa(etapa_id="a3", executor="claude")
        self.assertTrue(r.startswith("ERRO|"), r)
        self.assertEqual(self._plano(), antes)

    def test_so_executor_conta_como_campo_para_mudar(self):
        r = self._etapa(etapa_id="a3", executor="agente")
        self.assertTrue(r.startswith("OK|"), r)

    def test_editar_plano_acao_tambem_aceita_e_recusa(self):
        ok = telegram_extended.execute("editar_plano_acao", {
            "task_id": self.TASK, "justificativa_diario": "t",
            "novo_plano": [{"id": "a3", "executor": "agente_aprovado"}]}, self.db)
        self.assertTrue(ok.startswith("OK|"), ok)
        self.assertEqual(self._plano()[2]["executor"], "agente_aprovado")
        recusa = telegram_extended.execute("editar_plano_acao", {
            "task_id": self.TASK, "justificativa_diario": "t",
            "novo_plano": [{"id": "a4", "executor": "agente"}]}, self.db)
        self.assertTrue(recusa.startswith("ERRO|"), recusa)
        self.assertEqual(self._plano()[3]["executor"], "humano")


class TestDevolucaoNasTools(_BaseHandler):

    def test_obter_acao_devolve_executor_so_onde_ha_marca(self):
        res = hermes_tools.obter_acao(ToolContext(_db=self.db), {"task_id": self.TASK})
        por_id = {e["id"]: e for e in res["plano_acao"]}
        self.assertEqual(por_id["a1"]["executor"], "agente")
        self.assertEqual(por_id["a1"]["executor_como"], "Ler e montar a versão executiva")
        self.assertEqual(por_id["a2"]["executor"], "agente_aprovado")
        self.assertNotIn("executor", por_id["a3"])
        # humano fixado pelo André: o agente precisa ver a trava.
        self.assertEqual(por_id["a4"]["executor"], "humano")
        self.assertEqual(por_id["a4"]["executor_definido_por"], "usuario")

    def test_obter_acao_respeita_o_output_schema(self):
        import jsonschema
        from tools import registry
        res = hermes_tools.obter_acao(ToolContext(_db=self.db), {"task_id": self.TASK})
        jsonschema.validate(res, registry.output_schema("obter_acao"))


class TestResumoMatinal(unittest.TestCase):

    def test_subtarefa_do_dia_e_esperas_levam_o_executor(self):
        acoes = _acoes({"t1": _tarefa(plano_acao=[
            {"id": "e1", "text": "Preparar", "completed": False, "estado": "pendente",
             "executor": "agente", "executor_como": "Preparar o rascunho"},
            {"id": "e2", "text": "Aguardar Fulano", "completed": False, "estado": "aguardando_terceiro",
             "aguardando_de": "Fulano", "executor": "agente_aprovado"},
            {"id": "e3", "text": "Humana", "completed": False, "estado": "pendente"},
        ])})
        item = next(i for lane in acoes["por_lane"].values() for i in lane if i["id"] == "t1")
        self.assertEqual(item["subtarefa_do_dia"]["executor"], "agente")
        self.assertEqual(item["subtarefa_do_dia"]["executor_como"], "Preparar o rascunho")
        self.assertEqual(item["aguardando_terceiro"][0]["executor"], "agente_aprovado")

    def test_etapa_so_do_andre_nao_leva_campo_e_nada_de_contador_gravado(self):
        acoes = _acoes({"t1": _tarefa(plano_acao=[
            {"id": "e3", "text": "Humana", "completed": False, "estado": "pendente"}])})
        item = next(i for lane in acoes["por_lane"].values() for i in lane if i["id"] == "t1")
        self.assertNotIn("executor", item["subtarefa_do_dia"])
        self.assertFalse([k for k in item if "agente" in k and k != "aguardando_terceiro"])


if __name__ == "__main__":
    unittest.main()
