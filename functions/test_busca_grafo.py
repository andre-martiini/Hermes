import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.busca_grafo import _matches_filters, buscar_tarefas


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(self, docs, fail=False):
        self._docs = docs
        self._fail = fail

    def where(self, filter=None):
        return self

    def limit(self, _n):
        return self

    def stream(self):
        if self._fail:
            raise Exception("The query requires an index")
        return iter(self._docs)


class _FakeCollection(_FakeQuery):
    pass


class _FakeDb:
    def __init__(self, docs, fail_primary=False):
        self._docs = docs
        self._fail_primary = fail_primary
        self._calls = 0

    def collection(self, _name):
        self._calls += 1
        return _FakeCollection(self._docs, fail=self._fail_primary and self._calls == 1)


class TestBuscaGrafo(unittest.TestCase):
    def test_matches_filters_aplica_filtros_em_memoria(self):
        data = {
            "titulo": "Revisao de documentacao de alunos deferidos",
            "descricao": "Assistencia estudantil",
            "status": "em andamento",
            "area_tematica": "ASSISTENCIA",
            "data_limite": "2026-04-22",
            "data_criacao": "2026-04-20T10:00:00Z",
        }
        self.assertTrue(
            _matches_filters(
                data,
                termos=["revisao", "alunos"],
                match_mode="all",
                area_tematica="ASSISTENCIA",
                data_limite_inicio="2026-04-01",
                data_limite_fim="2026-04-30",
                status="em andamento",
                corte_str="2026-01-01T00:00:00Z",
            )
        )

    def test_buscar_tarefas_faz_fallback_quando_indice_esta_ausente(self):
        docs = [
            _FakeDoc(
                "task-1",
                {
                    "titulo": "Revisao de documentacao de alunos deferidos",
                    "descricao": "Assistencia estudantil",
                    "status": "em andamento",
                    "area_tematica": "ASSISTENCIA",
                    "data_limite": "2026-04-22",
                    "data_criacao": "2026-04-20T10:00:00Z",
                },
            ),
            _FakeDoc(
                "task-2",
                {
                    "titulo": "Outra tarefa",
                    "descricao": "Sem relacao",
                    "status": "concluida",
                    "area_tematica": "GERAL",
                    "data_limite": "2026-04-10",
                    "data_criacao": "2026-04-10T10:00:00Z",
                },
            ),
        ]

        import tools.busca_grafo as busca_grafo

        original_client = busca_grafo.firestore.Client
        try:
            busca_grafo.firestore.Client = lambda: _FakeDb(docs, fail_primary=True)
            result = buscar_tarefas(
                "revisao documentacao",
                area_tematica="ASSISTENCIA",
                data_limite_inicio="2026-04-01",
                data_limite_fim="2026-04-30",
                status="em andamento",
            )
        finally:
            busca_grafo.firestore.Client = original_client

        self.assertIsNone(result["erro"])
        self.assertEqual(len(result["resultados"]), 1)
        self.assertEqual(result["resultados"][0]["id"], "task-1")
        self.assertIn("fallback local", result.get("aviso", "").lower())

    def test_buscar_tarefas_encontra_acao_com_termos_aproximados(self):
        docs = [
            _FakeDoc(
                "task-target",
                {
                    "titulo": "Publicação de Dispensa Eletrônica: Locação de Mobiliário e Som para Eventos (processo 23543.000286/2026-39)",
                    "descricao": "Contratação por dispensa para estrutura de eventos.",
                    "status": "em andamento",
                    "area_tematica": "COMPRAS",
                    "processo_sei": "23543.000286/2026-39",
                    "data_criacao": "2026-04-20T10:00:00Z",
                },
            ),
            _FakeDoc(
                "task-distractor",
                {
                    "titulo": "Contratação de limpeza predial",
                    "descricao": "Serviço continuado para manutenção.",
                    "status": "em andamento",
                    "area_tematica": "SERVICOS",
                    "data_criacao": "2026-04-21T10:00:00Z",
                },
            ),
        ]

        import tools.busca_grafo as busca_grafo

        original_client = busca_grafo.firestore.Client
        try:
            busca_grafo.firestore.Client = lambda: _FakeDb(docs)
            result = buscar_tarefas(
                "Por favor, busque a ação relacionada à contratação de imobiliário para som e eventos",
                match_mode="all",
                limite=5,
            )
        finally:
            busca_grafo.firestore.Client = original_client

        self.assertIsNone(result["erro"])
        self.assertGreaterEqual(len(result["resultados"]), 1)
        self.assertEqual(result["resultados"][0]["id"], "task-target")

    def test_buscar_tarefas_encontra_por_frase_curta_som_eventos(self):
        docs = [
            _FakeDoc(
                "task-target",
                {
                    "titulo": "Publicação de Dispensa Eletrônica: Locação de Mobiliário e Som para Eventos",
                    "status": "em andamento",
                    "data_criacao": "2026-04-20T10:00:00Z",
                },
            )
        ]

        import tools.busca_grafo as busca_grafo

        original_client = busca_grafo.firestore.Client
        try:
            busca_grafo.firestore.Client = lambda: _FakeDb(docs)
            result = buscar_tarefas("som eventos", match_mode="all", limite=5)
        finally:
            busca_grafo.firestore.Client = original_client

        self.assertIsNone(result["erro"])
        self.assertEqual(result["resultados"][0]["id"], "task-target")

    def test_buscar_tarefas_numero_processo_prioriza_identificador_exato(self):
        docs = [
            _FakeDoc(
                "task-target",
                {
                    "titulo": "Locação de Mobiliário e Som para Eventos",
                    "processo_sei": "23543.000286/2026-39",
                    "status": "em andamento",
                    "data_criacao": "2026-04-20T10:00:00Z",
                },
            ),
            _FakeDoc(
                "task-similar-process",
                {
                    "titulo": "Trabalhar no Processo de Chaveiro",
                    "processo_sei": "23543.000056/2026-70",
                    "status": "em andamento",
                    "data_criacao": "2026-04-21T10:00:00Z",
                },
            ),
        ]

        import tools.busca_grafo as busca_grafo

        original_client = busca_grafo.firestore.Client
        try:
            busca_grafo.firestore.Client = lambda: _FakeDb(docs)
            result = buscar_tarefas("23543.000286/2026-39", match_mode="all", limite=5)
        finally:
            busca_grafo.firestore.Client = original_client

        self.assertIsNone(result["erro"])
        self.assertEqual([r["id"] for r in result["resultados"]], ["task-target"])

    def test_buscar_tarefas_relaxa_filtro_de_data_nao_mencionado(self):
        docs = [
            _FakeDoc(
                "task-target",
                {
                    "titulo": "Publicação de Dispensa Eletrônica: Locação de Mobiliário e Som para Eventos",
                    "status": "em andamento",
                    "area_tematica": "COMPRAS",
                    "data_criacao": "2026-04-20T10:00:00Z",
                },
            )
        ]

        import tools.busca_grafo as busca_grafo

        original_client = busca_grafo.firestore.Client
        try:
            busca_grafo.firestore.Client = lambda: _FakeDb(docs)
            result = buscar_tarefas(
                "contratação de imobiliário para som e eventos",
                match_mode="all",
                data_limite_inicio="2025-01-01",
                data_limite_fim="2026-12-31",
                limite=5,
            )
        finally:
            busca_grafo.firestore.Client = original_client

        self.assertIsNone(result["erro"])
        self.assertEqual(result["resultados"][0]["id"], "task-target")
        self.assertIn("prazo ignorado por nao constar na query", result.get("aviso", ""))


if __name__ == "__main__":
    unittest.main()


class TestBuscaMaisRapida(unittest.TestCase):
    """Otimização de 04/10/2026: a mediana da busca no MCP tinha subido de 9 para 14 s
    (p90 de 63 s). O tempo ia na comparação aproximada de palavras, repetida milhões
    de vezes, e numa segunda leitura completa que o handler fazia quando nada vinha."""

    def test_razao_memorizada_da_o_mesmo_valor_do_sequencematcher(self):
        from difflib import SequenceMatcher

        import tools.busca_grafo as bg

        for a, b in (("contratacao", "contratação"), ("licitacao", "licitacoes"), ("sipac", "sigrh"), ("abc", "abc")):
            with self.subTest(a=a, b=b):
                self.assertEqual(bg._razao(a, b), SequenceMatcher(None, a, b).ratio())

    def test_comparacao_repetida_nao_e_recalculada(self):
        import tools.busca_grafo as bg

        bg._razao.cache_clear()
        bg._razao("licitacao", "licitacoes")
        bg._razao("licitacao", "licitacoes")
        self.assertEqual(bg._razao.cache_info().hits, 1)

    def test_handler_le_a_colecao_uma_vez_so_quando_nada_e_encontrado(self):
        """buscar_tarefas já tenta "any" e relaxa filtros por dentro; o handler não
        repete a busca inteira (que relia as ~800 ações do Firestore)."""
        from unittest.mock import patch

        from tools import hermes_tools
        from tools.tool_context import ToolContext

        with patch("tools.busca_grafo.buscar_tarefas", return_value={"resultados": [], "erro": None}) as buscar:
            hermes_tools._consultar_historico_acoes(ToolContext(), {"query": "termo inexistente qualquer"})
        self.assertEqual(buscar.call_count, 1)
        self.assertEqual(buscar.call_args.kwargs["match_mode"], "all")

    def test_buscar_tarefas_com_all_ja_amplia_para_any_por_dentro(self):
        import tools.busca_grafo as busca_grafo

        docs = [_FakeDoc("t1", {"titulo": "Contratação de som", "status": "em andamento",
                                "data_criacao": "2026-09-01T10:00:00Z"})]
        original_client = busca_grafo.firestore.Client
        try:
            busca_grafo.firestore.Client = lambda: _FakeDb(docs)
            result = buscar_tarefas("som inexistentepalavra", match_mode="all", limite=5)
        finally:
            busca_grafo.firestore.Client = original_client
        self.assertEqual([r["id"] for r in result["resultados"]], ["t1"])
        self.assertIn("busca ampliada any", result.get("aviso", ""))
