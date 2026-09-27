"""`editar_plano_acao` parcial por padrão, remoção explícita e reversível, e `editar_etapa`.

Relato de 27/09/2026 (André; o Claude caiu no mesmo em 26/09): a ação
0171edc9 tinha 5 etapas, a chamada mandou só a que mudava —
`novo_plano=[{"id": "fa860a98", "estado": "em_andamento", ...}]` — e a
resposta foi `OK|{..., "removidas": ["0f176a57", "cc8cbccc", "33a5d2d2",
"f9c2d7f4"]}`. Reenviar as quatro recriou as etapas com ids NOVOS, perdendo
o vínculo com o histórico e o `degradation_count`. A descrição da tool dizia
que "campos omitidos preservam o valor atual da etapa", e quem chama leu
isso — com razão — como "mande só a etapa que mudou".
"""

import json
import unittest

import subtarefas as st
from test_outbox_aprovacao import _MockDb
from tools import hermes_tools, inventory, registry, telegram_extended


def _plano_real():
    """As 5 etapas da ação 0171edc9, com os campos que o bug apagava."""
    return [
        {"id": "fa860a98", "text": "Levantar demanda", "completed": False, "estado": "pendente"},
        {"id": "0f176a57", "text": "Consultar fornecedores", "completed": False,
         "estado": "aguardando_terceiro", "aguardando_de": "Compras", "degradation_count": 4,
         "historico": [{"em": "2026-09-20", "de": "pendente"}]},
        {"id": "cc8cbccc", "text": "Montar mapa de preços", "completed": False,
         "estado": "pendente", "data_prevista": "2026-10-02"},
        {"id": "33a5d2d2", "text": "Redigir termo de referência", "completed": True, "estado": "feito"},
        {"id": "f9c2d7f4", "text": "Enviar para a CLC", "completed": False, "estado": "pendente",
         "degradation_count": 2},
    ]


# --------------------------------------------------------------------------- #
# Função pura


class TestEditarPlanoParcial(unittest.TestCase):

    def test_mandar_uma_de_cinco_preserva_as_outras_quatro(self):
        atual = _plano_real()
        ed = st.editar_plano(atual, [{"id": "fa860a98", "text": "Levantar demanda",
                                      "estado": "em_andamento"}])
        self.assertEqual([p["id"] for p in ed.plano], [p["id"] for p in atual])
        self.assertEqual(ed.plano[0]["estado"], "em_andamento")
        # As não citadas saem byte a byte iguais.
        self.assertEqual(ed.plano[1:], atual[1:])
        self.assertEqual(ed.removidas, [])
        self.assertEqual(st.diferencas(atual, ed.plano),
                         {"alteradas": {"fa860a98": {"estado": ["pendente", "em_andamento"]}}})

    def test_etapa_so_com_id_e_estado_mantem_o_texto(self):
        ed = st.editar_plano(_plano_real(), [{"id": "cc8cbccc", "estado": "feito"}])
        self.assertEqual(ed.plano[2]["text"], "Montar mapa de preços")
        self.assertTrue(ed.plano[2]["completed"])
        self.assertEqual(ed.plano[2]["data_prevista"], "2026-10-02")

    def test_etapa_nova_entra_no_fim(self):
        ed = st.editar_plano(_plano_real(), [{"text": "Publicar o aviso de dispensa"}])
        self.assertEqual(len(ed.plano), 6)
        self.assertEqual(ed.plano[-1]["text"], "Publicar o aviso de dispensa")

    def test_texto_igual_normalizado_sem_id_atualiza_em_vez_de_duplicar(self):
        ed = st.editar_plano(_plano_real(), [{"text": "  consultar   FORNECEDORES ",
                                              "estado": "em_andamento"}])
        self.assertEqual(len(ed.plano), 5)
        self.assertEqual(ed.plano[1]["id"], "0f176a57")
        self.assertEqual(ed.plano[1]["estado"], "em_andamento")
        self.assertEqual(ed.plano[1]["degradation_count"], 4)

    def test_acento_nao_impede_o_casamento(self):
        ed = st.editar_plano(_plano_real(), [{"text": "Montar mapa de precos", "estado": "feito"}])
        self.assertEqual(len(ed.plano), 5)
        self.assertEqual(ed.plano[2]["id"], "cc8cbccc")

    def test_texto_so_parecido_vira_etapa_nova_e_nao_sobrescreve(self):
        """Revisão do PR #370: com >=85%, "Revisar parte 2" sobrescrevia "Revisar
        parte 1" (feita) em silêncio, sem ir para a lixeira."""
        atual = [{"id": "a", "text": "Revisar parte 1", "completed": True, "estado": "feito"},
                 {"id": "b", "text": "Outra", "completed": False, "estado": "pendente"}]
        ed = st.editar_plano(atual, [{"text": "Revisar parte 2"}])
        self.assertEqual(ed.plano[:2], atual)
        self.assertEqual(ed.plano[2]["text"], "Revisar parte 2")
        self.assertEqual(ed.plano[2]["estado"], "pendente")
        self.assertNotIn(ed.plano[2]["id"], ("a", "b"))
        self.assertEqual(ed.removidas, [])

    def test_etapa_feita_nao_e_alvo_de_casamento_por_texto_no_parcial(self):
        atual = [{"id": "a", "text": "Revisar parte 1", "completed": True, "estado": "feito"}]
        ed = st.editar_plano(atual, [{"text": "Revisar parte 1", "estado": "pendente"}])
        self.assertEqual(len(ed.plano), 2)
        self.assertEqual(ed.plano[0], atual[0])

    def test_id_desconhecido_com_texto_e_etapa_nova_com_esse_id(self):
        ed = st.editar_plano(_plano_real(), [{"id": "novo123", "text": "Consultar fornecedores"}])
        self.assertEqual(len(ed.plano), 6)
        self.assertEqual(ed.plano[-1]["id"], "novo123")
        self.assertEqual(ed.plano[1], _plano_real()[1])

    def test_id_desconhecido_repetido_nao_gera_ids_duplicados(self):
        ed = st.editar_plano(_plano_real(), [{"id": "x1", "text": "Uma"}, {"id": "x1", "text": "Duas"}])
        ids = [p["id"] for p in ed.plano]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ed.plano[-2]["id"], "x1")

    def test_remover_depois_de_texto_parecido_nao_perde_nada(self):
        """Revisão do PR #370: [{text: "Revisar parte 2"}, {id: a, remover}] mesclava o
        texto novo em `a` e depois removia `a` — o texto novo sumia."""
        atual = [{"id": "a", "text": "Revisar parte 1", "completed": False, "estado": "pendente"},
                 {"id": "b", "text": "Outra", "completed": False, "estado": "pendente"}]
        for lista in ([{"text": "Revisar parte 1"}, {"id": "a", "remover": True}],
                      [{"text": "Revisar parte 2"}, {"id": "a", "remover": True}]):
            with self.subTest(lista=lista):
                ed = st.editar_plano(atual, lista)
                self.assertEqual([p["text"] for p in ed.plano], ["Outra", lista[0]["text"]])
                self.assertNotEqual(ed.plano[1]["id"], "a")
                self.assertEqual([r["id"] for r in ed.removidas], ["a"])
                self.assertEqual(ed.removidas[0]["etapa"], atual[0])

    def test_remover_e_editar_o_mesmo_id_na_mesma_chamada_e_erro(self):
        for lista in ([{"id": "cc8cbccc", "estado": "feito"}, {"id": "cc8cbccc", "remover": True}],
                      [{"id": "cc8cbccc", "remover": True}, {"id": "cc8cbccc", "estado": "feito"}]):
            with self.subTest(lista=lista), self.assertRaises(st.PlanoInvalido):
                st.editar_plano(_plano_real(), lista)

    def test_duas_remocoes_por_texto_igual_tiram_duas_etapas(self):
        atual = [{"id": "a", "text": "Ligar"}, {"id": "b", "text": "ligar "}, {"id": "c", "text": "Outra"}]
        ed = st.editar_plano(atual, [{"text": "Ligar", "remover": True}, {"text": "LIGAR", "remover": True}])
        self.assertEqual([p["id"] for p in ed.plano], ["c"])
        self.assertEqual([r["id"] for r in ed.removidas], ["a", "b"])

    def test_remocao_por_texto_continua_exigindo_texto_exato(self):
        with self.assertRaises(st.PlanoInvalido):
            st.editar_plano([{"id": "a", "text": "Ligar para o setor"}], [{"text": "Ligar pro setor", "remover": True}])

    def test_remover_id_que_ja_esta_na_lixeira_e_repeticao_sem_efeito(self):
        lixeira = [{"id": "zz", "etapa": {"id": "zz", "text": "Velha"}, "posicao": 0, "removida_em": "x"}]
        ed = st.editar_plano(_plano_real(), [{"id": "zz", "remover": True}], etapas_removidas=lixeira)
        self.assertEqual(ed.plano, _plano_real())
        self.assertEqual(ed.removidas, [])
        self.assertEqual(ed.ja_removidas, ["zz"])

    def test_remover_explicito_tira_a_etapa_e_guarda_ela_inteira(self):
        atual = _plano_real()
        ed = st.editar_plano(atual, [{"id": "0f176a57", "remover": True}])
        self.assertEqual([p["id"] for p in ed.plano], ["fa860a98", "cc8cbccc", "33a5d2d2", "f9c2d7f4"])
        self.assertEqual(len(ed.removidas), 1)
        self.assertEqual(ed.removidas[0]["etapa"], atual[1])
        self.assertTrue(ed.removidas[0]["explicita"])
        self.assertEqual(ed.removidas_sem_pedido, [])
        self.assertEqual(st.diferencas(atual, ed.plano)["removidas"], ["0f176a57"])

    def test_remover_false_nao_e_gravado_na_etapa(self):
        ed = st.editar_plano(_plano_real(), [{"text": "Etapa nova", "remover": False},
                                             {"id": "fa860a98", "remover": False, "estado": "feito"}])
        self.assertNotIn("remover", ed.plano[-1])
        self.assertNotIn("remover", ed.plano[0])
        self.assertEqual(ed.removidas, [])

    def test_remover_id_desconhecido_e_recusado(self):
        with self.assertRaises(st.PlanoInvalido):
            st.editar_plano(_plano_real(), [{"id": "naoexiste", "remover": True}])

    def test_id_desconhecido_sem_texto_e_recusado(self):
        with self.assertRaises(st.PlanoInvalido):
            st.editar_plano(_plano_real(), [{"id": "naoexiste", "estado": "feito"}])

    def test_modo_invalido_e_recusado(self):
        with self.assertRaises(st.PlanoInvalido):
            st.editar_plano(_plano_real(), [{"id": "fa860a98"}], modo="tudo")


class TestEditarPlanoSubstituir(unittest.TestCase):

    def test_reordenar_com_a_lista_inteira_funciona(self):
        atual = _plano_real()
        nova_ordem = [{"id": p["id"]} for p in reversed(atual)]
        ed = st.editar_plano(atual, nova_ordem, modo="substituir")
        self.assertEqual([p["id"] for p in ed.plano], [p["id"] for p in reversed(atual)])
        self.assertEqual(ed.removidas, [])
        self.assertEqual(ed.plano[3]["degradation_count"], 4)
        self.assertEqual(st.diferencas(atual, ed.plano), {"ordem_alterada": True})

    def test_etapa_omitida_e_removida_sem_pedido(self):
        ed = st.editar_plano(_plano_real(), [{"id": "fa860a98"}], modo="substituir")
        self.assertEqual([p["id"] for p in ed.plano], ["fa860a98"])
        self.assertEqual(sorted(r["id"] for r in ed.removidas_sem_pedido),
                         sorted(["0f176a57", "cc8cbccc", "33a5d2d2", "f9c2d7f4"]))

    def test_remover_explicito_no_substituir_nao_conta_como_sem_pedido(self):
        atual = _plano_real()
        lista = [{"id": p["id"]} for p in atual]
        lista[4] = {"id": "f9c2d7f4", "remover": True}
        ed = st.editar_plano(atual, lista, modo="substituir")
        self.assertEqual(len(ed.plano), 4)
        self.assertEqual([r["id"] for r in ed.removidas], ["f9c2d7f4"])
        self.assertEqual(ed.removidas_sem_pedido, [])

    def test_duas_etapas_novas_parecidas_com_a_mesma_nao_viram_uma(self):
        atual = [{"id": "a1", "text": "Revisar o edital", "completed": False}]
        ed = st.editar_plano(atual, [{"text": "Revisar o edital"}, {"text": "Revisar o edita"}],
                             modo="substituir")
        self.assertEqual(len(ed.plano), 2)
        self.assertEqual(len({p["id"] for p in ed.plano}), 2)


class TestLixeira(unittest.TestCase):

    def _remover(self, modo="parcial"):
        atual = _plano_real()
        ed = st.editar_plano(atual, [{"id": "0f176a57", "remover": True}], modo=modo)
        return ed.plano, st.atualizar_lixeira([], ed, "2026-09-27T12:00:00+00:00")

    def test_lixeira_guarda_id_etapa_posicao_e_data(self):
        _, lixeira = self._remover()
        self.assertEqual(len(lixeira), 1)
        self.assertEqual(lixeira[0]["id"], "0f176a57")
        self.assertEqual(lixeira[0]["posicao"], 1)
        self.assertEqual(lixeira[0]["removida_em"], "2026-09-27T12:00:00+00:00")
        self.assertEqual(lixeira[0]["etapa"]["degradation_count"], 4)

    def test_restaurar_true_restaura_com_id_e_campos_originais_na_posicao(self):
        plano, lixeira = self._remover()
        ed = st.editar_plano(plano, [{"id": "0f176a57", "restaurar": True}], etapas_removidas=lixeira)
        self.assertEqual([p["id"] for p in ed.plano],
                         ["fa860a98", "0f176a57", "cc8cbccc", "33a5d2d2", "f9c2d7f4"])
        restaurada = ed.plano[1]
        self.assertEqual(restaurada["degradation_count"], 4)
        self.assertEqual(restaurada["aguardando_de"], "Compras")
        self.assertEqual(restaurada["historico"], [{"em": "2026-09-20", "de": "pendente"}])
        self.assertEqual(ed.restauradas, ["0f176a57"])
        self.assertNotIn("restaurar", restaurada)
        self.assertEqual(st.atualizar_lixeira(lixeira, ed, "x"), [])

    def test_id_da_lixeira_sem_restaurar_nem_texto_e_erro(self):
        plano, lixeira = self._remover()
        with self.assertRaisesRegex(st.PlanoInvalido, "0f176a57 está na lixeira"):
            st.editar_plano(plano, [{"id": "0f176a57", "estado": "feito"}], etapas_removidas=lixeira)

    def test_id_da_lixeira_com_texto_restaura(self):
        plano, lixeira = self._remover()
        ed = st.editar_plano(plano, [{"id": "0f176a57", "text": "Consultar fornecedores"}],
                             etapas_removidas=lixeira)
        self.assertEqual(ed.restauradas, ["0f176a57"])

    def test_restaurar_id_fora_da_lixeira_e_erro(self):
        with self.assertRaises(st.PlanoInvalido):
            st.editar_plano(_plano_real(), [{"id": "naoexiste", "restaurar": True}])

    def test_restaurar_aplica_os_campos_enviados(self):
        plano, lixeira = self._remover()
        ed = st.editar_plano(plano, [{"id": "0f176a57", "restaurar": True, "estado": "feito"}],
                             etapas_removidas=lixeira)
        self.assertEqual(ed.plano[1]["estado"], "feito")
        self.assertEqual(ed.plano[1]["degradation_count"], 4)

    def test_lixeira_tem_teto(self):
        lixeira = [{"id": f"x{i}", "etapa": {"id": f"x{i}", "text": "t"}, "posicao": 0,
                    "removida_em": "antes"} for i in range(st.LIMITE_ETAPAS_REMOVIDAS)]
        ed = st.editar_plano(_plano_real(), [{"id": "0f176a57", "remover": True}])
        nova = st.atualizar_lixeira(lixeira, ed, "agora")
        self.assertEqual(len(nova), st.LIMITE_ETAPAS_REMOVIDAS)
        self.assertEqual(nova[-1]["id"], "0f176a57")
        self.assertNotIn("x0", [e["id"] for e in nova])


# --------------------------------------------------------------------------- #
# Handler (tools/telegram_extended.py), sobre o Firestore falso


class _BaseHandler(unittest.TestCase):
    TASK = "0171edc9-30c5-4d9e-b"

    def setUp(self):
        self.db = _MockDb()
        self.db.collection("tarefas").document(self.TASK).set({
            "titulo": "Dispensa", "plano_acao": _plano_real()})

    def _doc(self):
        return self.db.collection("tarefas")._docs[self.TASK]

    def _plano(self):
        return self._doc()["plano_acao"]

    def _editar(self, **slots):
        return telegram_extended.execute(
            "editar_plano_acao", {"task_id": self.TASK, "justificativa_diario": "teste", **slots}, self.db)


class TestHandlerEditarPlanoAcao(_BaseHandler):

    def test_caso_real_uma_de_cinco_nao_apaga_as_outras(self):
        r = self._editar(novo_plano=[{"id": "fa860a98", "text": "Levantar demanda",
                                      "estado": "em_andamento"}])
        self.assertEqual(r, 'OK|{"alteradas": {"fa860a98": {"estado": ["pendente", "em_andamento"]}}}')
        self.assertEqual([p["id"] for p in self._plano()],
                         ["fa860a98", "0f176a57", "cc8cbccc", "33a5d2d2", "f9c2d7f4"])
        self.assertEqual(self._plano()[1]["degradation_count"], 4)
        self.assertNotIn("etapas_removidas", self._doc())

    def test_lista_vazia_no_parcial_e_recusada(self):
        r = self._editar(novo_plano=[])
        self.assertTrue(r.startswith("ERRO|novo_plano veio vazio"), r)
        self.assertEqual(self._plano(), _plano_real())

    def test_remover_explicito_aparece_em_removidas_e_vai_para_a_lixeira(self):
        r = self._editar(novo_plano=[{"id": "33a5d2d2", "remover": True}])
        self.assertTrue(r.startswith("OK|"), r)
        self.assertEqual(json.loads(r[3:])["removidas"], ["33a5d2d2"])
        self.assertNotIn("33a5d2d2", [p["id"] for p in self._plano()])
        self.assertEqual([e["id"] for e in self._doc()["etapas_removidas"]], ["33a5d2d2"])
        nota = self._doc()["acompanhamento"].values[0]["nota"]
        self.assertIn("33a5d2d2", nota)
        self.assertIn("Redigir termo de referência", nota)

    def test_substituir_sem_confirmacao_e_recusado_listando_e_sem_gravar(self):
        r = self._editar(modo="substituir", novo_plano=[{"id": "fa860a98"}])
        self.assertTrue(r.startswith("ERRO|Nada foi gravado"), r)
        for eid, texto in (("0f176a57", "Consultar fornecedores"), ("cc8cbccc", "Montar mapa de preços"),
                           ("33a5d2d2", "Redigir termo"), ("f9c2d7f4", "Enviar para a CLC")):
            self.assertIn(eid, r)
            self.assertIn(texto, r)
        self.assertEqual(self._plano(), _plano_real())
        self.assertNotIn("acompanhamento", self._doc())
        self.assertNotIn("confirmar_remocao=true", r)
        self.assertIn('"remover": true', r)

    def test_substituir_com_confirmacao_remove(self):
        r = self._editar(modo="substituir", confirmar_remocao=True,
                         novo_plano=[{"id": "fa860a98"}, {"id": "0f176a57"}])
        self.assertTrue(r.startswith("OK|"), r)
        self.assertEqual(sorted(json.loads(r[3:])["removidas"]), ["33a5d2d2", "cc8cbccc", "f9c2d7f4"])
        self.assertEqual([p["id"] for p in self._plano()], ["fa860a98", "0f176a57"])
        self.assertEqual(len(self._doc()["etapas_removidas"]), 3)

    def test_confirmar_remocao_como_string_false_nao_confirma(self):
        r = self._editar(modo="substituir", confirmar_remocao="false", novo_plano=[{"id": "fa860a98"}])
        self.assertTrue(r.startswith("ERRO|"), r)
        self.assertEqual(self._plano(), _plano_real())

    def test_reordenar_com_substituir_sem_remover_nao_pede_confirmacao(self):
        ordem = ["f9c2d7f4", "33a5d2d2", "cc8cbccc", "0f176a57", "fa860a98"]
        r = self._editar(modo="substituir", novo_plano=[{"id": e} for e in ordem])
        self.assertEqual(r, 'OK|{"ordem_alterada": true}')
        self.assertEqual([p["id"] for p in self._plano()], ordem)
        self.assertEqual(self._plano()[3]["degradation_count"], 4)

    def test_etapa_removida_volta_com_id_e_campos_originais(self):
        self._editar(novo_plano=[{"id": "0f176a57", "remover": True}])
        r = self._editar(novo_plano=[{"id": "0f176a57", "text": "Consultar fornecedores"}])
        self.assertEqual(json.loads(r[3:]), {"restauradas": ["0f176a57"]})
        self.assertEqual(self._plano(), _plano_real()[:1] + [st.normalizar(_plano_real()[1])]
                         + _plano_real()[2:])
        self.assertEqual(self._plano()[1]["degradation_count"], 4)
        self.assertEqual(self._plano()[1]["historico"], [{"em": "2026-09-20", "de": "pendente"}])
        self.assertEqual(self._doc()["etapas_removidas"], [])

    def test_esvaziar_continua_exigindo_confirmar_esvaziar(self):
        r = self._editar(modo="substituir", confirmar_remocao=True, novo_plano=[])
        self.assertTrue(r.startswith("ERRO|A alteracao apagaria"), r)
        self.assertEqual(self._plano(), _plano_real())

    def test_modo_invalido(self):
        r = self._editar(modo="tudo", novo_plano=[{"id": "fa860a98"}])
        self.assertTrue(r.startswith("ERRO|modo"), r)


class TestHandlerEditarEtapa(_BaseHandler):

    def _etapa(self, **slots):
        return telegram_extended.execute("editar_etapa", {"task_id": self.TASK, **slots}, self.db)

    def test_muda_so_a_etapa_pedida(self):
        r = self._etapa(etapa_id="cc8cbccc", estado="aguardando_terceiro", aguardando_de="Setor X")
        self.assertTrue(r.startswith("OK|"), r)
        plano = self._plano()
        self.assertEqual(plano[2]["estado"], "aguardando_terceiro")
        self.assertEqual(plano[2]["aguardando_de"], "Setor X")
        self.assertEqual(plano[2]["data_prevista"], "2026-10-02")
        self.assertEqual(plano[2]["text"], "Montar mapa de preços")
        self.assertEqual(plano[:2] + plano[3:], _plano_real()[:2] + _plano_real()[3:])
        # Sem justificativa, o diário registra o que mudou.
        self.assertIn("Montar mapa de preços", self._doc()["acompanhamento"].values[0]["nota"])

    def test_null_apaga_a_data(self):
        r = self._etapa(etapa_id="cc8cbccc", data_prevista=None)
        self.assertIn('"data_prevista": ["2026-10-02", null]', r)
        self.assertNotIn("data_prevista", self._plano()[2])

    def test_etapa_id_desconhecido_e_erro_listando_as_existentes(self):
        r = self._etapa(etapa_id="naoexiste", estado="feito")
        self.assertTrue(r.startswith("ERRO|Etapa 'naoexiste' não existe"), r)
        self.assertIn("fa860a98", r)
        self.assertEqual(self._plano(), _plano_real())

    def test_etapa_removida_orienta_a_restaurar(self):
        self._editar(novo_plano=[{"id": "0f176a57", "remover": True}])
        r = self._etapa(etapa_id="0f176a57", estado="feito")
        self.assertTrue(r.startswith('ERRO|Etapa 0f176a57 está na lixeira; para restaurar envie '
                                     '{"id": "0f176a57", "restaurar": true}'), r)
        self.assertNotIn("0f176a57", [p["id"] for p in self._plano()])

    def test_estado_invalido_e_recusado(self):
        r = self._etapa(etapa_id="cc8cbccc", estado="concluida")
        self.assertTrue(r.startswith("ERRO|estado"), r)
        self.assertEqual(self._plano(), _plano_real())

    def test_sem_campo_para_mudar_e_erro(self):
        self.assertTrue(self._etapa(etapa_id="cc8cbccc").startswith("ERRO|Nada para mudar"))

    def test_tarefa_inexistente(self):
        r = telegram_extended.execute("editar_etapa", {"task_id": "nao", "etapa_id": "x", "estado": "feito"},
                                      self.db)
        self.assertTrue(r.startswith("ERRO|Tarefa"), r)


class TestPlanoAtualLegado(unittest.TestCase):
    """O plano gravado passa por normalização antes da edição."""

    def test_etapa_em_texto_puro_vira_dict_com_id_e_nao_some(self):
        ed = st.editar_plano(["Passo antigo", {"id": "b", "text": "Outro"}],
                             [{"id": "b", "estado": "feito"}])
        self.assertEqual([p["text"] for p in ed.plano], ["Passo antigo", "Outro"])
        self.assertTrue(ed.plano[0]["id"])
        self.assertEqual(ed.base[0]["id"], ed.plano[0]["id"])
        self.assertEqual(st.diferencas(ed.base, ed.plano),
                         {"alteradas": {"b": {"estado": ["pendente", "feito"]}}})

    def test_plano_gravado_como_uma_string_nao_vira_caracteres(self):
        ed = st.editar_plano("Fazer a coisa inteira", [{"text": "Segundo passo"}])
        self.assertEqual([p["text"] for p in ed.plano], ["Fazer a coisa inteira", "Segundo passo"])

    def test_plano_gravado_como_json_de_lista(self):
        ed = st.editar_plano('["Um", "Dois"]', [{"text": "Tres"}])
        self.assertEqual([p["text"] for p in ed.plano], ["Um", "Dois", "Tres"])

    def test_substituir_etapa_sem_texto_passa_pela_confirmacao_e_lixeira(self):
        atual = [{"id": "a", "text": "A"}, {"id": "z", "nota": "sem texto"}]
        ed = st.editar_plano(atual, [{"id": "a"}], modo="substituir")
        self.assertEqual([r["id"] for r in ed.removidas_sem_pedido], ["z"])
        lixeira = st.atualizar_lixeira([], ed, "agora")
        self.assertEqual(lixeira[0]["etapa"], {"id": "z", "nota": "sem texto"})

    def test_parcial_mantem_etapa_sem_texto(self):
        atual = [{"id": "a", "text": "A"}, {"id": "z", "nota": "sem texto"}]
        ed = st.editar_plano(atual, [{"id": "a", "estado": "feito"}])
        self.assertEqual(ed.plano[1], {"id": "z", "nota": "sem texto"})
        self.assertEqual(ed.removidas, [])


class TestCopilotoPlanoCompleto(_BaseHandler):
    """`copiloto=True` (copiloto web): o prompt dele manda o plano inteiro."""

    def _copiloto(self, lista, **extra):
        return telegram_extended.editar_plano_da_tarefa(
            self.db, {"task_id": self.TASK, "novo_plano": lista, "justificativa_diario": "t", **extra},
            origem="Copiloto Gaspar", copiloto=True)

    def test_reenvio_que_cobre_todas_as_etapas_reordena(self):
        ordem = ["f9c2d7f4", "33a5d2d2", "cc8cbccc", "0f176a57", "fa860a98"]
        r = self._copiloto([{"id": e} for e in ordem])
        self.assertEqual(r, 'OK|{"ordem_alterada": true}')
        self.assertEqual([p["id"] for p in self._plano()], ordem)

    def test_lista_longa_com_etapa_nova_segue_parcial_e_nao_e_recusada(self):
        lista = [{"id": "fa860a98"}, {"id": "0f176a57"}, {"id": "cc8cbccc"}, {"id": "33a5d2d2"},
                 {"text": "Etapa nova"}]
        r = self._copiloto(lista)
        self.assertEqual(json.loads(r[3:])["adicionadas"], [self._plano()[-1]["id"]])
        self.assertEqual([p["id"] for p in self._plano()][:5],
                         ["fa860a98", "0f176a57", "cc8cbccc", "33a5d2d2", "f9c2d7f4"])

    def test_omitir_etapa_sem_mais_nada_devolve_aviso_e_nao_grava(self):
        r = self._copiloto([{"id": "fa860a98"}, {"id": "0f176a57"}, {"id": "cc8cbccc"}, {"id": "33a5d2d2"}])
        self.assertTrue(r.startswith("AVISO|Nada mudou"), r)
        self.assertIn('"remover": true', r)
        self.assertNotIn("confirmar_remocao", r)
        self.assertEqual(self._plano(), _plano_real())
        self.assertNotIn("acompanhamento", self._doc())

    def test_remover_explicito_funciona_no_copiloto(self):
        r = self._copiloto([{"id": "f9c2d7f4", "remover": True}])
        self.assertEqual(json.loads(r[3:])["removidas"], ["f9c2d7f4"])

    def test_substituir_com_confirmacao_explicita_remove(self):
        r = self._copiloto([{"id": "fa860a98"}, {"id": "0f176a57"}, {"id": "cc8cbccc"}, {"id": "33a5d2d2"}],
                           modo="substituir", confirmar_remocao=True)
        self.assertEqual(json.loads(r[3:])["removidas"], ["f9c2d7f4"])

    def test_lista_curta_continua_parcial(self):
        r = self._copiloto([{"id": "fa860a98", "estado": "feito"}])
        self.assertTrue(r.startswith('OK|{"alteradas"'), r)
        self.assertEqual(len(self._plano()), 5)


class TestIdempotencia(_BaseHandler):

    def test_chamada_sem_mudanca_nao_grava_nem_diario(self):
        r = self._editar(novo_plano=[{"id": "fa860a98", "estado": "pendente"}])
        self.assertEqual(r, "OK|Nenhuma etapa mudou: os valores enviados já eram os atuais.")
        self.assertNotIn("acompanhamento", self._doc())
        self.assertNotIn("data_atualizacao", self._doc())

    def test_remover_duas_vezes_a_segunda_e_ja_removidas_sem_escrita(self):
        self._editar(novo_plano=[{"id": "f9c2d7f4", "remover": True}])
        diario = self._doc()["acompanhamento"]
        r = self._editar(novo_plano=[{"id": "f9c2d7f4", "remover": True}])
        self.assertEqual(r, 'OK|{"ja_removidas": ["f9c2d7f4"]}')
        self.assertIs(self._doc()["acompanhamento"], diario)
        self.assertEqual(len(self._doc()["etapas_removidas"]), 1)


class TestIdsDuplicadosLegados(unittest.TestCase):

    def test_duplicata_ganha_id_novo_e_primeira_mantem(self):
        atual = [{"id": "d", "text": "Primeira"}, {"id": "d", "text": "Segunda"}]
        ed = st.editar_plano(atual, [{"id": "d", "estado": "feito"}])
        self.assertEqual(ed.plano[0]["id"], "d")
        self.assertEqual(ed.plano[0]["estado"], "feito")
        self.assertNotEqual(ed.plano[1]["id"], "d")
        self.assertEqual(ed.plano[1]["text"], "Segunda")

    def test_remover_as_duas_duplicatas_nao_perde_nenhuma_da_lixeira(self):
        atual = [{"id": "d", "text": "Primeira"}, {"id": "d", "text": "Segunda"}]
        ed = st.editar_plano(atual, [{"id": "d"}], modo="substituir")
        lixeira = st.atualizar_lixeira([], ed, "agora")
        self.assertEqual([e["etapa"]["text"] for e in lixeira], ["Segunda"])
        ed2 = st.editar_plano(ed.plano, [{"id": "d", "remover": True}], etapas_removidas=lixeira)
        lixeira2 = st.atualizar_lixeira(lixeira, ed2, "depois")
        self.assertEqual(sorted(e["etapa"]["text"] for e in lixeira2), ["Primeira", "Segunda"])
        self.assertEqual(len({e["id"] for e in lixeira2}), 2)


class _TxDb(_MockDb):
    def __init__(self):
        super().__init__()
        self.escritas_em_transacao = 0

    def transaction(self):
        tx = super().transaction()
        db = self
        original = tx.update

        def update(ref, data):
            db.escritas_em_transacao += 1
            original(ref, data)
        tx.update = update
        return tx


class TestTransacao(unittest.TestCase):

    def test_escrita_passa_pela_transacao(self):
        db = _TxDb()
        db.collection("tarefas").document("t").set({"plano_acao": _plano_real()})
        r = telegram_extended.execute("editar_plano_acao", {
            "task_id": "t", "novo_plano": [{"id": "fa860a98", "estado": "feito"}]}, db)
        self.assertTrue(r.startswith("OK|"), r)
        self.assertEqual(db.escritas_em_transacao, 1)
        self.assertEqual(db.collection("tarefas")._docs["t"]["plano_acao"][0]["estado"], "feito")

    def test_recusa_nao_escreve_na_transacao(self):
        db = _TxDb()
        db.collection("tarefas").document("t").set({"plano_acao": _plano_real()})
        r = telegram_extended.execute("editar_plano_acao", {
            "task_id": "t", "modo": "substituir", "novo_plano": [{"id": "fa860a98"}]}, db)
        self.assertTrue(r.startswith("ERRO|"), r)
        self.assertEqual(db.escritas_em_transacao, 0)


class TestEditarEtapaRegistrada(unittest.TestCase):
    """A tool nova precisa estar em todos os lugares que publicam o catálogo."""

    def test_catalogo_schema_handler_e_inventario(self):
        self.assertIn("editar_etapa", registry.list_tool_names())
        self.assertTrue(registry.has_schema("editar_etapa"))
        self.assertTrue(hermes_tools.has_tool("editar_etapa"))
        self.assertTrue(registry.is_mcp_enabled("editar_etapa"))
        self.assertIsNotNone(inventory.get_inventory_entry("editar_etapa"))

    def test_classificacao_igual_a_de_editar_plano_acao(self):
        for consulta in (registry.needs_confirmation, registry.is_voice_enabled, registry.is_async):
            with self.subTest(consulta=consulta.__name__):
                self.assertEqual(consulta("editar_etapa"), consulta("editar_plano_acao"))
        self.assertEqual(registry.mcp_annotations("editar_etapa"),
                         registry.mcp_annotations("editar_plano_acao"))

    def test_schema_de_editar_plano_acao_publica_modo_e_remocao(self):
        schema = registry.get_schema("editar_plano_acao")
        props = schema["parameters"]["properties"]
        self.assertEqual(props["modo"]["enum"], ["parcial", "substituir"])
        self.assertIn("confirmar_remocao", props)
        self.assertIn("remover", props["novo_plano"]["items"]["properties"])
        self.assertNotIn("required", props["novo_plano"]["items"])
        self.assertIn("SÓ as etapas enviadas", schema["description"])

    def test_required_de_editar_etapa(self):
        self.assertEqual(registry.get_required_params("editar_etapa"), ["task_id", "etapa_id"])


if __name__ == "__main__":
    unittest.main()
