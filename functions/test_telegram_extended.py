"""P03 sub-entrega 19/N: idempotentHint por handler (passo 3 do plano),
quarta fatia -- testes de handler para as classificações de
`salvar_pop_global`, `atualizar_personalidade`, `resolver_conflito_memoria`
(IDEMPOTENTE) e `resolver_conflito_procedimento`, `editar_plano_acao`
(NAO_IDEMPOTENTE) em `functions/tools/inventory.py`.

Nenhum dos cinco tinha teste de HANDLER dedicado antes desta sub-entrega
(mesma classe de gap já vista em `strategy_tools.py` na sub-entrega 18/N) --
`tools/telegram_extended.py` só tinha cobertura de validação de argumentos
(`test_normalizador_resultados_legados.py`, `test_validacao_argumentos.py`),
nunca do comportamento real de escrita repetida.

Reaproveita o fake de Firestore com armazenamento em memória já usado e
testado por `test_outbox_aprovacao.py` (`_MockDb`) em vez de reimplementar
um novo -- mesma disciplina de "reusar, nunca reescrever" já citada no
cabeçalho de `tools/hermes_tools.py`.
"""

import unittest
from unittest import mock

from firebase_admin import firestore

from test_outbox_aprovacao import _MockDb
from tools import telegram_extended


class TestSalvarPopGlobalIdempotente(unittest.TestCase):
    """`salvar_pop_global` (P03 sub-entrega 19/N): dedup por título OU
    gatilho normalizado antes de escrever -- ver `tools/telegram_extended.py`,
    ramo `salvar_pop_global`."""

    def setUp(self):
        self.db = _MockDb()

    def _chamar(self):
        return telegram_extended.execute(
            "salvar_pop_global",
            {
                "titulo": "Como abrir processo SIPAC",
                "instrucao_sistema": "Siga o roteiro X.",
                "gatilhos": ["abrir processo", "sipac"],
            },
            self.db,
        )

    def test_repetir_mesma_chamada_atualiza_o_mesmo_pop_sem_duplicar(self):
        import json

        r1 = json.loads(self._chamar())
        r2 = json.loads(self._chamar())

        self.assertEqual(r1["status"], "saved")
        self.assertEqual(r2["status"], "updated")
        self.assertEqual(r1["pop_id"], r2["pop_id"])
        self.assertEqual(len(self.db.collection("pops_diretrizes")._docs), 1)

    def test_repetir_com_gatilho_igual_mas_titulo_diferente_ainda_converge(self):
        """Dedup também casa por INTERSEÇÃO de gatilhos, não só por título
        idêntico -- ver `existing_triggers_norm.intersection(...)`."""
        import json

        r1 = json.loads(self._chamar())
        r2 = json.loads(telegram_extended.execute(
            "salvar_pop_global",
            {
                "titulo": "Titulo bem diferente",
                "instrucao_sistema": "Outra instrução.",
                "gatilhos": ["sipac"],
            },
            self.db,
        ))

        self.assertEqual(r1["pop_id"], r2["pop_id"])
        self.assertEqual(len(self.db.collection("pops_diretrizes")._docs), 1)


class TestAtualizarPersonalidadeIdempotente(unittest.TestCase):
    """`atualizar_personalidade` (P03 sub-entrega 19/N): singleton
    `system/copilot_soul` via `.set(merge=True)`."""

    def setUp(self):
        self.db = _MockDb()

    def test_repetir_mesma_chamada_mantem_um_unico_documento(self):
        for _ in range(2):
            telegram_extended.execute(
                "atualizar_personalidade",
                {"nova_personalidade": "Seja mais direto.", "motivo": "pedido do usuário"},
                self.db,
            )

        docs = self.db.collection("system")._docs
        self.assertEqual(list(docs.keys()), ["copilot_soul"])
        self.assertEqual(docs["copilot_soul"]["content"], "Seja mais direto.")

    def test_chamadas_com_conteudo_diferente_convergem_para_o_ultimo_valor(self):
        telegram_extended.execute(
            "atualizar_personalidade", {"nova_personalidade": "Primeiro texto."}, self.db)
        telegram_extended.execute(
            "atualizar_personalidade", {"nova_personalidade": "Segundo texto."}, self.db)

        docs = self.db.collection("system")._docs
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs["copilot_soul"]["content"], "Segundo texto.")


class TestResolverConflitoMemoriaIdempotente(unittest.TestCase):
    """`resolver_conflito_memoria` (P03 sub-entrega 19/N): os dois ramos de
    decisão escrevem por `memoria_id` já conhecido, nunca geram ID novo."""

    def setUp(self):
        self.db = _MockDb()
        self.db.collection("knowledge_nodes").document("mem-1").set({
            "texto_memoria": "fato original",
        })

    def test_manter_existente_repetido_nao_cria_segundo_documento(self):
        for _ in range(2):
            telegram_extended.execute(
                "resolver_conflito_memoria",
                {"memoria_id": "mem-1", "decisao": "manter_existente"},
                self.db,
            )

        docs = self.db.collection("knowledge_nodes")._docs
        self.assertEqual(list(docs.keys()), ["mem-1"])
        self.assertEqual(docs["mem-1"]["ultima_decisao_humana"], "manter_existente")

    def test_substituir_pelo_novo_repetido_escreve_no_mesmo_id(self):
        """`_save_memory_node` é mockado -- o que se prova aqui é que o
        HANDLER sempre passa o MESMO `force_update_id`, nunca um novo,
        independentemente de quantas vezes for chamado."""
        fake_save = mock.MagicMock(return_value={"status": "resolved", "memory_id": "mem-1"})
        with mock.patch("main._save_memory_node", fake_save), \
                mock.patch("tools.telegram_extended._get_api_keys",
                            return_value={"gemini_api_key": "fake-key"}):
            for _ in range(2):
                telegram_extended.execute(
                    "resolver_conflito_memoria",
                    {"memoria_id": "mem-1", "decisao": "substituir_pelo_novo",
                     "fato_atualizado": "fato novo"},
                    self.db,
                )

        self.assertEqual(fake_save.call_count, 2)
        ids_usados = {call.kwargs.get("force_update_id") for call in fake_save.call_args_list}
        self.assertEqual(ids_usados, {"mem-1"})


class TestResolverConflitoProcedimentoNaoIdempotente(unittest.TestCase):
    """`resolver_conflito_procedimento` (P03 sub-entrega 19/N): com
    `confirmar_contrato=True`, cria um documento NOVO (`uuid4()[:12]`) a
    cada chamada -- sem dedup contra o procedimento já arquivado."""

    def setUp(self):
        self.db = _MockDb()
        self.db.collection("conhecimento_mestre").document("proc-1").set({
            "titulo": "Procedimento X",
            "conteudo_regra": "faça Y",
            "status": "ativo",
        })

    def test_repetir_confirmar_contrato_cria_dois_procedimentos_evoluidos(self):
        args = {
            "id_procedimento": "proc-1",
            "justificativa_humana": "confirmado pelo revisor",
            "confirmar_contrato": True,
        }
        telegram_extended.execute("resolver_conflito_procedimento", args, self.db)
        telegram_extended.execute("resolver_conflito_procedimento", args, self.db)

        docs = self.db.collection("conhecimento_mestre")._docs
        # proc-1 (arquivado) + 2 documentos evoluídos novos = 3.
        self.assertEqual(len(docs), 3)
        ids_evoluidos = [k for k in docs if k != "proc-1"]
        self.assertEqual(len(set(ids_evoluidos)), 2, "cada chamada deve gerar um ID novo distinto")
        self.assertEqual(docs["proc-1"]["status"], "arquivado_backup")

    def test_sem_confirmar_contrato_e_so_preview_sem_escrever(self):
        args = {
            "id_procedimento": "proc-1",
            "justificativa_humana": "ainda avaliando",
            "confirmar_contrato": False,
        }
        resultado = telegram_extended.execute("resolver_conflito_procedimento", args, self.db)

        self.assertIn("Contrato de Entendimento", resultado)
        docs = self.db.collection("conhecimento_mestre")._docs
        self.assertEqual(list(docs.keys()), ["proc-1"])
        self.assertEqual(docs["proc-1"]["status"], "ativo")


class TestEditarPlanoAcaoNaoIdempotente(unittest.TestCase):
    """`editar_plano_acao` (P03 sub-entrega 19/N): `subtarefas.mesclar_plano`
    em si converge, mas o handler acrescenta um `ArrayUnion` incondicional
    em `acompanhamento` a cada chamada bem-sucedida -- mesmo padrão de
    `editar_acao` (sub-entrega 16/N)."""

    def setUp(self):
        self.db = _MockDb()
        self.db.collection("tarefas").document("tarefa-1").set({
            "titulo": "Organizar evento",
            "plano_acao": [],
        })

    def _editar(self):
        return telegram_extended.execute(
            "editar_plano_acao",
            {
                "task_id": "tarefa-1",
                "novo_plano": ["Reservar auditório"],
                "justificativa_diario": "plano inicial",
            },
            self.db,
        )

    def test_repetir_a_mesma_edicao_acrescenta_entrada_nova_no_diario_cada_vez(self):
        r1 = self._editar()
        doc_apos_1 = dict(self.db.collection("tarefas")._docs["tarefa-1"])
        acompanhamento_1 = doc_apos_1["acompanhamento"]

        # A 2ª chamada precisa achar o plano já mesclado como `plano_atual`,
        # exatamente como o handler real faz (lê o doc de novo a cada chamada).
        self.db.collection("tarefas").document("tarefa-1").set(
            {"plano_acao": doc_apos_1.get("plano_acao", [])}, merge=True)

        r2 = self._editar()
        doc_apos_2 = dict(self.db.collection("tarefas")._docs["tarefa-1"])
        acompanhamento_2 = doc_apos_2["acompanhamento"]

        self.assertEqual(r1, "OK")
        self.assertEqual(r2, "OK")
        self.assertIsInstance(acompanhamento_1, firestore.ArrayUnion)
        self.assertIsInstance(acompanhamento_2, firestore.ArrayUnion)
        # Cada chamada monta o SEU PRÓPRIO ArrayUnion com uma entrada nova
        # (nota+timestamp) -- não é o mesmo objeto reaproveitado, e não há
        # nenhuma checagem que pule a 2ª escrita.
        self.assertEqual(len(acompanhamento_1.values), 1)
        self.assertEqual(len(acompanhamento_2.values), 1)
        # O plano final (conteúdo de negócio) converge -- só o diário cresce.
        self.assertEqual(
            [item["text"] for item in doc_apos_1["plano_acao"]],
            [item["text"] for item in doc_apos_2["plano_acao"]],
        )


class TestGerarRelatorioNaoIdempotente(unittest.TestCase):
    """`gerar_relatorio` (P03 sub-entrega 19/N): `report_id = uuid4()[:16]`
    e `.set()` incondicional em `relatorios/{report_id}`, sem dedup por
    título/contexto -- repetir o MESMO pedido cria um SEGUNDO relatório."""

    def setUp(self):
        self.db = _MockDb()
        self.db.collection("system").document("api_keys").set({"gemini_api_key": "fake-key"})

    def test_repetir_o_mesmo_pedido_gera_dois_relatorios_distintos(self):
        skeleton_resp = mock.MagicMock(text='{"secoes": ["Sumário Executivo", "Conclusão e Recomendações"]}')
        secao_resp = mock.MagicMock(text="Conteúdo da seção.")

        with mock.patch("tools.telegram_extended.generate_content_logged",
                          side_effect=[skeleton_resp, secao_resp, secao_resp,
                                       skeleton_resp, secao_resp, secao_resp]):
            r1 = telegram_extended.execute(
                "gerar_relatorio",
                {"titulo": "Fechamento de Setembro", "tipo": "executivo", "contexto": "dados do mês"},
                self.db,
            )
            r2 = telegram_extended.execute(
                "gerar_relatorio",
                {"titulo": "Fechamento de Setembro", "tipo": "executivo", "contexto": "dados do mês"},
                self.db,
            )

        import json

        id1 = json.loads(r1)["report_id"]
        id2 = json.loads(r2)["report_id"]
        self.assertNotEqual(id1, id2)
        self.assertEqual(len(self.db.collection("relatorios")._docs), 2)


if __name__ == "__main__":
    unittest.main()
