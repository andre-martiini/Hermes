"""Testes para a unificação do motor Telegram legado de memória (P06 do
plano de autonomia, docs/plano-hermes-autonomo-2026-09-06.md, pendência
registrada em `autonomy/context.py` na sub-entrega que introduziu
`origem_fato`): `telegram_message_tools.py::salvar_memoria_global` escrevia
DIRETO em `knowledge_nodes` com um esquema próprio e divergente
(`fato`/`categoria`/`origem`, sem embedding, sem dedup, sem `origem_fato`),
bypassando `main._save_memory_node` -- o mesmo caminho que os canais MCP/web
já usam. Esta sub-entrega unifica os dois.

Três efeitos testados aqui:
1. `telegram_message_tools.py::salvar_memoria_global` passa a delegar para
   `main._save_memory_node`, com `origem_fato="inferencia_agente"` (canal
   "telegram" não exige afirmação literal do usuário, mesmo contrato do
   canal "web" -- ver `autonomy.context.origem_fato_para_canal_de_salvar_memoria`).
2. `telegram_handlers_core.py::_fato_e_categoria_de_memoria` (extraída do
   bloco "MEMÓRIA GLOBAL ATIVA" do system prompt do Telegram) passa a
   reconhecer tanto o esquema legado (`fato`/`categoria`) quanto o canônico
   (`texto_memoria`/`tipo`) -- antes só reconhecia o legado, então ficava
   cega para qualquer memória salva pelos canais MCP/web.
3. `status="conflict"` de `_save_memory_node` (achado de revisão
   adversarial independente sobre o efeito 1: o Telegram não tem o fluxo de
   confirmação que web/MCP usam para esse status, então sem tratamento o
   fato novo seria descartado em silêncio) é resolvido automaticamente a
   favor do fato mais recente, via `force_update_id` -- mesma operação que
   `resolver_conflito_memoria` faz sob confirmação humana no outro canal.

Mock de Firestore reaproveitado de `test_outbox_aprovacao._MockDb` (mesmo
padrão de `test_memoria_origem_fato.py`), sem reimplementar um segundo mock.
`get_embedding`/`_find_similar_memory_nodes` são mockados para isolar o
caminho de proveniência/esquema do resto da lógica de similaridade/dedup,
já coberta em `test_memoria_origem_fato.py` e não alterada por esta
sub-entrega.
"""

import json
import unittest
from unittest import mock

from test_outbox_aprovacao import _MockDb

import main
import telegram_message_tools as tmt
from autonomy.context import INFERENCIA_AGENTE
from telegram_handlers_core import _fato_e_categoria_de_memoria


def _patch_embedding_e_similares():
    return mock.patch.multiple(
        main,
        get_embedding=mock.DEFAULT,
        _find_similar_memory_nodes=mock.DEFAULT,
    )


def _closure_salvar_memoria_global(db):
    """Constrói os 21 closures do Telegram e devolve só `salvar_memoria_global`
    -- mesmo padrão de `test_telegram_peso.py::TestFerramentaDoGemini`."""
    ferramentas = {
        f.__name__: f
        for f in tmt.build_telegram_tool_closures(db, {}, "geral", None, None, False, False, ["GERAL"])
    }
    return ferramentas["salvar_memoria_global"]


class TestSalvarMemoriaGlobalTelegramUnificado(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()

    @mock.patch.object(tmt, "_get_api_keys", lambda db: {"gemini_api_key": "fake-key"})
    def test_grava_pelo_save_memory_node_com_esquema_canonico_e_origem_fato(self):
        salvar = _closure_salvar_memoria_global(self.db)

        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = []
            resultado = json.loads(salvar("Prefere reuniões de manhã", "regra"))

        self.assertEqual(resultado["status"], "saved")
        doc = self.db.collection("knowledge_nodes")._docs[resultado["memory_id"]]
        # Esquema canônico de _save_memory_node, não o esquema legado
        # (fato/categoria/origem) que esta sub-entrega substitui. "regra" ->
        # "regra_global" por _normalize_memory_category (main.py).
        self.assertEqual(doc["texto_memoria"], "Prefere reuniões de manhã")
        self.assertEqual(doc["tipo"], "regra_global")
        self.assertIn("embedding", doc)
        self.assertNotIn("fato", doc)
        self.assertNotIn("origem", doc)
        # Canal "telegram" não exige afirmação literal do usuário -- mesmo
        # contrato do canal "web" (ver autonomy/context.py).
        self.assertEqual(doc["origem_fato"], INFERENCIA_AGENTE)

    @mock.patch.object(tmt, "_get_api_keys", lambda db: {"gemini_api_key": "fake-key"})
    def test_duplicado_e_reportado_sem_criar_segundo_no(self):
        """`_save_memory_node` dedup por similaridade -- o motor legado
        anterior não tinha essa noção (cada chamada criava um nó novo)."""
        self.db.collection("knowledge_nodes").document("mem-existente").set({
            "texto_memoria": "fato ja conhecido",
            "tipo": "preferencia",
        })
        salvar = _closure_salvar_memoria_global(self.db)

        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-existente",
                "similarity": 0.999,
                "data": {"texto_memoria": "fato ja conhecido", "tipo": "preferencia"},
            }]
            resultado = json.loads(salvar("fato ja conhecido", "preferencia"))

        self.assertEqual(resultado["status"], "ignored")
        self.assertEqual(resultado["reason"], "duplicate")
        self.assertEqual(len(self.db.collection("knowledge_nodes")._docs), 1)

    @mock.patch.object(tmt, "_get_api_keys", lambda db: {"gemini_api_key": "fake-key"})
    def test_conflito_e_resolvido_automaticamente_a_favor_do_fato_novo(self):
        """Achado real de revisão adversarial independente: sem este
        tratamento, `status="conflict"` (similaridade média, nem duplicado
        nem claramente novo) faria o Telegram descartar o fato novo em
        silêncio -- o canal não tem o fluxo de confirmação que web/MCP têm
        (`resolver_conflito_memoria`, `pendingMemoryConflict` na sessão)."""
        self.db.collection("knowledge_nodes").document("mem-conflito").set({
            "texto_memoria": "prefere reunioes de manha",
            "tipo": "preferencia",
        })
        salvar = _closure_salvar_memoria_global(self.db)

        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-conflito",
                "similarity": 0.93,
                "data": {"texto_memoria": "prefere reunioes de manha", "tipo": "preferencia"},
            }]
            resultado = json.loads(salvar("nao gosta de reunioes de manha, prefere a tarde", "preferencia"))

        self.assertEqual(resultado["status"], "updated")
        self.assertEqual(resultado["conflict_resolution"], "auto_replaced_existing")
        self.assertEqual(resultado["memory_id"], "mem-conflito")
        doc = self.db.collection("knowledge_nodes")._docs["mem-conflito"]
        self.assertEqual(doc["texto_memoria"], "nao gosta de reunioes de manha, prefere a tarde")
        # Nenhum nó novo criado -- o conflito foi resolvido no mesmo nó.
        self.assertEqual(len(self.db.collection("knowledge_nodes")._docs), 1)

    @mock.patch.object(tmt, "_get_api_keys", lambda db: {"gemini_api_key": "fake-key"})
    def test_conflito_com_no_apagado_entre_as_duas_chamadas_nao_finge_sucesso(self):
        """2ª rodada de revisão adversarial independente: a 1ª chamada acha
        um conflito contra "mem-apagado", mas o nó não existe de fato no
        Firestore (ex.: apagado por uma escrita concorrente entre a 1ª
        chamada, que só buscou por similaridade de embedding, e a 2ª, que
        tenta o `force_update_id`). `_save_memory_node` com `force_update_id`
        para um doc inexistente devolve `status="error"`/`memory_not_found`
        -- `conflict_resolution` NÃO deve ser anexado a esse erro (antes
        desta correção, era anexado incondicionalmente, sugerindo falsamente
        que a substituição deu certo)."""
        salvar = _closure_salvar_memoria_global(self.db)

        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-apagado",
                "similarity": 0.93,
                "data": {"texto_memoria": "fato antigo", "tipo": "preferencia"},
            }]
            resultado = json.loads(salvar("fato novo em conflito", "preferencia"))

        self.assertEqual(resultado["status"], "error")
        self.assertEqual(resultado["reason"], "memory_not_found")
        self.assertNotIn("conflict_resolution", resultado)

    @mock.patch.object(tmt, "_get_api_keys", lambda db: {"gemini_api_key": "fake-key"})
    def test_erro_de_save_memory_node_nao_propaga_vira_json_de_erro(self):
        salvar = _closure_salvar_memoria_global(self.db)

        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].side_effect = RuntimeError("gemini indisponivel")
            resultado = json.loads(salvar("fato qualquer", "categoria"))

        self.assertEqual(resultado["status"], "error")
        self.assertIn("gemini indisponivel", resultado["reason"])


class TestFatoECategoriaDeMemoriaAceitaOsDoisEsquemas(unittest.TestCase):
    """`telegram_handlers_core.py::_fato_e_categoria_de_memoria` -- extraída
    do bloco "MEMÓRIA GLOBAL ATIVA" do system prompt do Telegram, que antes
    desta sub-entrega só lia `fato`/`categoria` (esquema legado) e por isso
    nunca exibia memórias salvas pelos canais MCP/web (esquema canônico)."""

    def test_esquema_legado_continua_funcionando(self):
        fato, cat = _fato_e_categoria_de_memoria({"fato": "gosta de café", "categoria": "preferencia"})
        self.assertEqual((fato, cat), ("gosta de café", "preferencia"))

    def test_esquema_canonico_agora_e_reconhecido(self):
        fato, cat = _fato_e_categoria_de_memoria({"texto_memoria": "gosta de café", "tipo": "preferencia"})
        self.assertEqual((fato, cat), ("gosta de café", "preferencia"))

    def test_esquema_legado_tem_prioridade_quando_os_dois_campos_existem(self):
        doc = {"fato": "versao legada", "categoria": "cat_legada",
                "texto_memoria": "versao canonica", "tipo": "cat_canonica"}
        fato, cat = _fato_e_categoria_de_memoria(doc)
        self.assertEqual((fato, cat), ("versao legada", "cat_legada"))

    def test_doc_vazio_nao_quebra(self):
        self.assertEqual(_fato_e_categoria_de_memoria({}), ("", ""))


if __name__ == "__main__":
    unittest.main()
