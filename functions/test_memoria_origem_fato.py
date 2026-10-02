"""Testes para P06 sub-entrega 1/N (docs/plano-hermes-autonomo-2026-09-06.md,
pacote P06, passo 1): `main._save_memory_node` passa a gravar `origem_fato`
em todo fato novo, e `autonomy.context.origem_fato_de_leitura` normaliza a
leitura de fatos antigos (sem o campo) para `legacy_unknown`.

Mock de Firestore reaproveitado de `test_outbox_aprovacao._MockDb` (mesmo
padrão de `test_telegram_extended.py`), sem reimplementar um segundo mock.
`get_embedding`/`_find_similar_memory_nodes` são mockados para isolar o
campo de proveniência do resto da lógica de similaridade/dedup, que já tem
seu próprio escopo e não foi alterada por esta sub-entrega.
"""

import unittest
from unittest import mock

from test_outbox_aprovacao import _MockDb

import main
from autonomy.context import (
    DECLARACAO_HUMANA,
    FONTE_EXTERNA,
    INFERENCIA_AGENTE,
    LEGADO_DESCONHECIDO,
    ORIGENS_FATO_NOVO,
    ORIGENS_FATO_VALIDAS,
    origem_fato_de_leitura,
    origem_fato_para_canal_de_salvar_memoria,
    origem_fato_para_salvar_memoria,
)
from tools import hermes_tools
from tools.tool_context import ToolContext


def _patch_embedding_e_similares(candidatos=None):
    """Contexto que isola `_save_memory_node` da geração real de embedding e
    da busca de similares (vector search do Firestore, não suportada pelo
    mock) -- nada aqui testa a lógica de similaridade/dedup, já coberta (ou
    não) em outro lugar; só o campo `origem_fato`."""
    return mock.patch.multiple(
        main,
        get_embedding=mock.DEFAULT,
        _find_similar_memory_nodes=mock.DEFAULT,
    )


class TestSaveMemoryNodeGravaOrigemFato(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()

    def test_fato_novo_grava_declaracao_humana(self):
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = []
            resultado = main._save_memory_node(
                db=self.db,
                api_key="fake-key",
                fato="André prefere reuniões pela manhã.",
                categoria="preferencia",
            )

        self.assertEqual(resultado["status"], "saved")
        doc = self.db.collection("knowledge_nodes")._docs[resultado["memory_id"]]
        self.assertEqual(doc["origem_fato"], DECLARACAO_HUMANA)

    def test_resolver_conflito_substituir_pelo_novo_grava_declaracao_humana(self):
        self.db.collection("knowledge_nodes").document("mem-1").set({
            "texto_memoria": "fato original",
        })

        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            resultado = main._save_memory_node(
                db=self.db,
                api_key="fake-key",
                fato="fato corrigido pelo usuário",
                categoria="fato_isolado",
                force_update_id="mem-1",
            )

        self.assertEqual(resultado["status"], "updated")
        doc = self.db.collection("knowledge_nodes")._docs["mem-1"]
        self.assertEqual(doc["origem_fato"], DECLARACAO_HUMANA)
        # `_find_similar_memory_nodes` não deveria nem ser chamada no caminho
        # de force_update_id -- ele não busca similares, atualiza o ID dado.
        mocks["_find_similar_memory_nodes"].assert_not_called()

    def test_duplicado_nao_reescreve_origem_fato_do_no_existente(self):
        """O merge de 'duplicado' só atualiza metadados de observação; não
        deve sobrescrever a proveniência original do nó já existente."""
        self.db.collection("knowledge_nodes").document("mem-existente").set({
            "texto_memoria": "fato ja conhecido",
            "tipo": "preferencia",
            "origem_fato": FONTE_EXTERNA,
        })

        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-existente",
                "similarity": 0.999,
                "data": {"texto_memoria": "fato ja conhecido", "tipo": "preferencia"},
            }]
            resultado = main._save_memory_node(
                db=self.db,
                api_key="fake-key",
                fato="fato ja conhecido",
                categoria="preferencia",
            )

        self.assertEqual(resultado["status"], "ignored")
        self.assertEqual(resultado["reason"], "duplicate")
        doc = self.db.collection("knowledge_nodes")._docs["mem-existente"]
        self.assertEqual(doc["origem_fato"], FONTE_EXTERNA)


class TestSalvarMemoriaGlobalPorCanal(unittest.TestCase):
    """`salvar_memoria_global` (tools/hermes_tools.py::_salvar_memoria_global)
    é o MESMO código para o servidor MCP (canal="mcp") e para o copiloto web
    (canal="web") -- mas os dois têm um contrato de texto DIFERENTE para
    quando acionar a tool (ver autonomy/context.py). Achado real da 1a
    rodada de revisão adversarial: a 1a versão desta sub-entrega gravava
    `DECLARACAO_HUMANA` para os dois canais, ignorando essa diferença.

    Achado real do Codex (revisão automática da PR): mesmo no canal "web", o
    USUÁRIO pode afirmar um fato literalmente -- o canal sozinho não
    distingue isso de uma inferência do próprio modelo. `usuario_afirmou_diretamente`
    é o parâmetro novo que resolve isso (ver `origem_fato_para_salvar_memoria`)."""

    def setUp(self):
        self.db = _MockDb()

    def _chamar(self, canal, usuario_afirmou_diretamente=None):
        ctx = ToolContext(canal=canal, _db=self.db, _gemini_key="fake-key")
        args = {"fato": "um fato qualquer", "categoria": "fato_isolado"}
        if usuario_afirmou_diretamente is not None:
            args["usuario_afirmou_diretamente"] = usuario_afirmou_diretamente
        with mock.patch.object(
            main, "_classify_memory_candidate",
            return_value={"should_save": True, "reason": "ok", "confidence": 0.9,
                          "normalized_category": "fato_isolado"},
        ), _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = []
            resultado_json = hermes_tools._salvar_memoria_global(ctx, args)
        import json as _json
        resultado = _json.loads(resultado_json)
        doc = self.db.collection("knowledge_nodes")._docs[resultado["memory_id"]]
        return doc

    def test_canal_mcp_grava_declaracao_humana(self):
        doc = self._chamar("mcp")
        self.assertEqual(doc["origem_fato"], DECLARACAO_HUMANA)

    def test_canal_web_sem_afirmacao_grava_inferencia_agente(self):
        doc = self._chamar("web")
        self.assertEqual(doc["origem_fato"], INFERENCIA_AGENTE)

    def test_canal_web_com_usuario_afirmou_diretamente_grava_declaracao_humana(self):
        """Cenário exato do achado do Codex: usuário diz 'prefiro reuniões de
        manhã' no copiloto web; o modelo passa usuario_afirmou_diretamente=True."""
        doc = self._chamar("web", usuario_afirmou_diretamente=True)
        self.assertEqual(doc["origem_fato"], DECLARACAO_HUMANA)

    def test_canal_web_com_usuario_afirmou_diretamente_false_explicito_grava_inferencia_agente(self):
        doc = self._chamar("web", usuario_afirmou_diretamente=False)
        self.assertEqual(doc["origem_fato"], INFERENCIA_AGENTE)

    def test_canal_desconhecido_tambem_grava_inferencia_agente(self):
        """Um canal futuro, não auditado, nunca deve herdar silenciosamente a
        afirmação mais forte (DECLARACAO_HUMANA) -- ver docstring de
        `origem_fato_para_canal_de_salvar_memoria`."""
        doc = self._chamar("algum_canal_novo_do_futuro")
        self.assertEqual(doc["origem_fato"], INFERENCIA_AGENTE)


class TestOrigemFatoParaCanalDeSalvarMemoria(unittest.TestCase):
    def test_mcp_e_declaracao_humana(self):
        self.assertEqual(origem_fato_para_canal_de_salvar_memoria("mcp"), DECLARACAO_HUMANA)

    def test_web_e_inferencia_agente(self):
        self.assertEqual(origem_fato_para_canal_de_salvar_memoria("web"), INFERENCIA_AGENTE)

    def test_none_e_inferencia_agente(self):
        self.assertEqual(origem_fato_para_canal_de_salvar_memoria(None), INFERENCIA_AGENTE)


class TestOrigemFatoParaSalvarMemoria(unittest.TestCase):
    """`origem_fato_para_salvar_memoria` combina canal + o parâmetro
    `usuario_afirmou_diretamente` que o modelo preenche a cada chamada --
    adicionado em resposta ao achado real do Codex (ver docstring do módulo)."""

    def test_usuario_afirmou_diretamente_vence_qualquer_canal(self):
        for canal in ("web", "mcp", None, "algum_canal_futuro"):
            with self.subTest(canal=canal):
                self.assertEqual(
                    origem_fato_para_salvar_memoria(canal, True), DECLARACAO_HUMANA
                )

    def test_sem_afirmacao_cai_no_fallback_por_canal(self):
        self.assertEqual(
            origem_fato_para_salvar_memoria("mcp", False), DECLARACAO_HUMANA
        )
        self.assertEqual(
            origem_fato_para_salvar_memoria("web", False), INFERENCIA_AGENTE
        )

    def test_parametro_omitido_usa_default_false(self):
        self.assertEqual(origem_fato_para_salvar_memoria("web"), INFERENCIA_AGENTE)
        self.assertEqual(origem_fato_para_salvar_memoria("mcp"), DECLARACAO_HUMANA)


class TestOrigemFatoDeLeitura(unittest.TestCase):
    def test_documento_sem_campo_e_legado(self):
        self.assertEqual(origem_fato_de_leitura({"texto_memoria": "x"}), LEGADO_DESCONHECIDO)

    def test_documento_none_e_legado(self):
        self.assertEqual(origem_fato_de_leitura(None), LEGADO_DESCONHECIDO)

    def test_documento_vazio_e_legado(self):
        self.assertEqual(origem_fato_de_leitura({}), LEGADO_DESCONHECIDO)

    def test_valor_conhecido_e_preservado(self):
        for origem in ORIGENS_FATO_NOVO:
            with self.subTest(origem=origem):
                self.assertEqual(
                    origem_fato_de_leitura({"origem_fato": origem}), origem
                )

    def test_valor_desconhecido_vira_legado(self):
        self.assertEqual(
            origem_fato_de_leitura({"origem_fato": "categoria_inventada_no_futuro"}),
            LEGADO_DESCONHECIDO,
        )

    def test_legado_desconhecido_esta_entre_os_validos(self):
        self.assertIn(LEGADO_DESCONHECIDO, ORIGENS_FATO_VALIDAS)
        for origem in ORIGENS_FATO_NOVO:
            self.assertIn(origem, ORIGENS_FATO_VALIDAS)

    def test_valor_tipo_lista_nao_lanca_e_e_legado(self):
        """Achado real da 1a rodada de revisão adversarial: `valor in
        ORIGENS_FATO_VALIDAS` sozinho lança `TypeError: unhashable type`
        para uma lista -- Firestore aceita qualquer tipo em `origem_fato`,
        então um documento corrompido/malformado não pode derrubar a
        leitura."""
        self.assertEqual(
            origem_fato_de_leitura({"origem_fato": ["x"]}), LEGADO_DESCONHECIDO
        )

    def test_valor_tipo_dict_nao_lanca_e_e_legado(self):
        self.assertEqual(
            origem_fato_de_leitura({"origem_fato": {"a": 1}}), LEGADO_DESCONHECIDO
        )

    def test_valor_tipo_numero_nao_lanca_e_e_legado(self):
        self.assertEqual(
            origem_fato_de_leitura({"origem_fato": 123}), LEGADO_DESCONHECIDO
        )


if __name__ == "__main__":
    unittest.main()
