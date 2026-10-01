import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import investimentos_sync
import subtarefas

_AREAS = "hermes_core_logic.carregar_areas_tematicas_validas"


class TestInvestimentosSync(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.collection_mock = MagicMock()
        self.mock_db.collection.return_value = self.collection_mock

    @patch("investimentos.carteira")
    def test_sem_troca_nao_cria_acao(self, mock_carteira):
        mock_carteira.return_value = {
            "posicao": "BOVA11",
            "decisao_vigente": {
                "mes": "2026-09",
                "nova_posicao": "BOVA11",
                "posicao_anterior": "BOVA11",
                "trocou": False,
            },
        }

        res = investimentos_sync.sincronizar_decisao_investimentos(self.mock_db)
        self.assertEqual(res["status"], "sem_troca")
        self.assertEqual(res["mes"], "2026-09")
        # Nenhuma escrita no Firestore
        self.collection_mock.document.assert_not_called()

    @patch(_AREAS, return_value=["GERAL", "NÃO CLASSIFICADA", "SIGEX"])
    @patch("investimentos.carteira")
    def test_trocou_true_cria_acao_com_etapas(self, mock_carteira, _areas):
        mock_carteira.return_value = {
            "posicao": "BOVA11",
            "decisao_vigente": {
                "mes": "2026-10",
                "nova_posicao": "IVVB11",
                "posicao_anterior": "BOVA11",
                "trocou": True,
                "mensagem": "Vender BOVA11 e comprar IVVB11",
                "justificativa": "IVVB11 superou BOVA11 nos últimos 12 meses",
                "ordens": [
                    {"passo": 1, "operacao": "vender", "ativo": "BOVA11", "quantidade": 6.0, "texto": "Vender 6 cotas de BOVA11"},
                    {"passo": 2, "operacao": "comprar", "ativo": "IVVB11", "quantidade": 2.0, "texto": "Comprar 2 cotas de IVVB11"},
                    {"passo": 3, "operacao": "confirmar", "ativo": "IVVB11", "texto": "Confirmar no Gaspar via tool registrar_execucao_investimento(ativo='IVVB11', quantidade=2)"},
                ],
            },
        }

        # Simula que não há documento existente para este mês
        query_mock = MagicMock()
        self.collection_mock.where.return_value = query_mock
        query_mock.limit.return_value = query_mock
        query_mock.get.return_value = []

        doc_ref_mock = MagicMock()
        self.collection_mock.document.return_value = doc_ref_mock

        res = investimentos_sync.sincronizar_decisao_investimentos(self.mock_db)
        self.assertEqual(res["status"], "acao_criada")
        self.assertEqual(res["mes"], "2026-10")
        self.assertEqual(res["ordens"], 3)

        # Verifica dados gravados na tarefa
        doc_ref_mock.set.assert_called_once()
        salvo = doc_ref_mock.set.call_args[0][0]

        self.assertIn("BOVA11 → IVVB11", salvo["titulo"])
        # "FINANCAS" nao e area valida: cai em GERAL, como no caminho normal.
        self.assertEqual(salvo["area_tematica"], "GERAL")
        self.assertIn("investimentos-decisao-2026-10", salvo["tags"])
        self.assertEqual(salvo["status"], "em andamento")
        self.assertEqual(len(salvo["plano_acao"]), 3)

        # Última etapa deve instruir confirmação via tool MCP
        ultima_etapa = salvo["plano_acao"][-1]
        self.assertIn("registrar_execucao_investimento", subtarefas.texto_de(ultima_etapa))

    @patch("investimentos.carteira")
    def test_idempotencia_nao_duplica_acao(self, mock_carteira):
        mock_carteira.return_value = {
            "posicao": "BOVA11",
            "decisao_vigente": {
                "mes": "2026-10",
                "nova_posicao": "IVVB11",
                "posicao_anterior": "BOVA11",
                "trocou": True,
            },
        }

        # Simula que já existe um documento com essa tag
        doc_existente = MagicMock()
        doc_existente.id = "tarefa-123"
        doc_existente.to_dict.return_value = {"titulo": "Executar rebalanceamento..."}

        query_mock = MagicMock()
        self.collection_mock.where.return_value = query_mock
        query_mock.limit.return_value = query_mock
        query_mock.get.return_value = [doc_existente]

        res = investimentos_sync.sincronizar_decisao_investimentos(self.mock_db)
        self.assertEqual(res["status"], "ja_existe")
        self.assertEqual(res["task_id"], "tarefa-123")
        self.collection_mock.document.assert_not_called()

    @patch(_AREAS, return_value=["GERAL", "NÃO CLASSIFICADA", "FINANÇAS"])
    @patch("investimentos.carteira")
    def test_area_de_financas_e_usada_quando_existe(self, mock_carteira, _areas):
        mock_carteira.return_value = {
            "posicao": "BOVA11",
            "decisao_vigente": {"mes": "2026-11", "nova_posicao": "IVVB11",
                                "posicao_anterior": "BOVA11", "trocou": True},
        }
        query_mock = MagicMock()
        self.collection_mock.where.return_value = query_mock
        query_mock.limit.return_value = query_mock
        query_mock.get.return_value = []
        doc_ref_mock = MagicMock()
        self.collection_mock.document.return_value = doc_ref_mock

        investimentos_sync.sincronizar_decisao_investimentos(self.mock_db)
        self.assertEqual(doc_ref_mock.set.call_args[0][0]["area_tematica"], "FINANÇAS")

    @patch("investimentos.carteira")
    def test_troca_ja_executada_nao_cria_acao(self, mock_carteira):
        """A carteira ja esta na posicao nova: o servico manda ordens vazias e a acao
        pediria para refazer o que ja foi feito."""
        mock_carteira.return_value = {
            "posicao": "IVVB11",
            "decisao_vigente": {"mes": "2026-11", "nova_posicao": "IVVB11",
                                "posicao_anterior": "BOVA11", "trocou": True, "ordens": []},
        }
        query_mock = MagicMock()
        self.collection_mock.where.return_value = query_mock
        query_mock.limit.return_value = query_mock
        query_mock.get.return_value = []

        res = investimentos_sync.sincronizar_decisao_investimentos(self.mock_db)
        self.assertEqual(res["status"], "ja_executada")
        self.collection_mock.document.assert_not_called()

    def test_rodada_pos_decisao_no_dia_1_depois_das_06h(self):
        """O briefing das 05h ainda ve a decisao do mes anterior."""
        gatilho = investimentos_sync.sincronizar_investimentos_pos_decisao.__firebase_endpoint__.scheduleTrigger
        self.assertEqual(gatilho["schedule"], "30 7 1 * *")
        self.assertEqual(gatilho["timeZone"], "America/Sao_Paulo")

    def test_rodada_pos_decisao_chama_o_sync_com_o_banco(self):
        fn = investimentos_sync.sincronizar_investimentos_pos_decisao
        fn = getattr(fn, "__wrapped__", fn)
        db = object()
        with patch.dict(sys.modules, {"main": types.SimpleNamespace(get_db=lambda: db)}), \
                patch.object(investimentos_sync, "sincronizar_decisao_investimentos",
                             return_value={"status": "sem_troca"}) as sync:
            fn(None)
        sync.assert_called_once_with(db)

    def test_rotina_exportada_no_main_para_o_deploy(self):
        import main
        self.assertIs(main.sincronizar_investimentos_pos_decisao,
                      investimentos_sync.sincronizar_investimentos_pos_decisao)

    @patch("investimentos.carteira")
    def test_erro_de_comunicacao_trata_graciosamente(self, mock_carteira):
        mock_carteira.return_value = {"erro": "Timeout no servico"}

        res = investimentos_sync.sincronizar_decisao_investimentos(self.mock_db)
        self.assertEqual(res["status"], "erro")
        self.assertEqual(res["detalhe"], "Timeout no servico")


if __name__ == "__main__":
    unittest.main()
