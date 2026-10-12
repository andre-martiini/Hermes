"""Testes para P06 sub-entrega 2/N (docs/plano-hermes-autonomo-2026-09-06.md,
pacote P06, passo 1): `telegram_message_tools.py::salvar_memoria_global`
(motor Telegram legado, fallback quando o copiloto web falha) passa a
chamar `main._save_memory_node` em vez de escrever direto em
`knowledge_nodes` com um esquema próprio -- fecha a pendência registrada em
`autonomy/context.py` pela P06 sub-entrega 1/N.

Extrai e executa o corpo REAL do closure `salvar_memoria_global` via AST +
exec, isolando só o que ele de fato captura (`db`, `session`, `json`,
`_get_api_keys`) -- mesma técnica já usada em
test_batch_edit.py::TestTelegramEditarAcoesEmLoteReal e
test_tool_schemas.py::TestSecretarioTelegramExecucao para outras closures
deste mesmo módulo, em vez de chamar `build_telegram_tool_closures`
completo (que monta 25 closures com dependências que não interessam aqui).

Mock de Firestore reaproveitado de `test_outbox_aprovacao._MockDb` (mesmo
padrão de `test_memoria_origem_fato.py`, que testa `_save_memory_node`
diretamente). `get_embedding`/`_find_similar_memory_nodes` são mockados
pelo mesmo motivo de lá: isolar o wiring deste closure (chamar
`_save_memory_node` com os parâmetros certos) da lógica de
similaridade/dedup em si, já coberta (ou não) em outro lugar.

`TestTelegramResolverConflitoMemoriaReal` cobre o segundo closure novo
desta sub-entrega, `resolver_conflito_memoria` -- achado real de revisão
adversarial independente sobre a 1ª versão desta sub-entrega: sem ele, um
status "conflict" devolvido por `_save_memory_node` (agora alcançável a
partir de `salvar_memoria_global` acima) não tinha nenhuma ferramenta deste
motor Telegram para ser resolvido. A lógica de resolução em si já existe e
já é testada em `test_telegram_extended.py::TestResolverConflitoMemoriaIdempotente`
(P03 sub-entrega 19/N) -- os testes aqui cobrem só a DELEGAÇÃO do closure
novo para `tools.telegram_extended.execute`, não reimplementam aquela
cobertura.
"""

import ast
import inspect
import json
import unittest
from unittest import mock

from test_outbox_aprovacao import _MockDb

import main
import telegram_message_tools
from autonomy.context import DECLARACAO_HUMANA, INFERENCIA_AGENTE


def _patch_embedding_e_similares():
    """Mesma função de test_memoria_origem_fato.py -- isola `_save_memory_node`
    da geração real de embedding e da busca de similares (vector search do
    Firestore, não suportada pelo mock)."""
    return mock.patch.multiple(
        main,
        get_embedding=mock.DEFAULT,
        _find_similar_memory_nodes=mock.DEFAULT,
    )


def _extrair_closure_salvar_memoria_global(db, session, get_api_keys_fn):
    """Extrai e executa só o corpo de `salvar_memoria_global` dentro de
    `build_telegram_tool_closures`, injetando os nomes livres que o closure
    de fato referencia (`db`, `session`, `json`, `_get_api_keys`) -- os
    imports locais (`from main import _save_memory_node`, `from
    autonomy.context import ...`) dentro do corpo da função resolvem contra
    os módulos reais já importados pelo processo de teste, sem precisar
    entrar no namespace."""
    arvore = ast.parse(inspect.getsource(telegram_message_tools.build_telegram_tool_closures))
    no = next(
        n for n in arvore.body[0].body
        if isinstance(n, ast.FunctionDef) and n.name == "salvar_memoria_global"
    )
    modulo = ast.Module(body=[no], type_ignores=[])
    namespace = {
        "db": db,
        "session": session,
        "json": json,
        "_get_api_keys": get_api_keys_fn,
    }
    exec(compile(ast.fix_missing_locations(modulo), "<closure-salvar-memoria-global-telegram-real>", "exec"), namespace)
    return namespace["salvar_memoria_global"]


class TestTelegramSalvarMemoriaGlobalReal(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()
        self.session = {"chat_id": "123456789"}
        self.salvar_memoria_global = _extrair_closure_salvar_memoria_global(
            self.db, self.session, lambda _db: {"gemini_api_key": "fake-key"}
        )

    def test_fato_novo_passa_por_save_memory_node_com_origem_inferencia_agente(self):
        """canal "telegram" não é "mcp" -- origem_fato_para_canal_de_salvar_memoria
        devolve INFERENCIA_AGENTE (nunca DECLARACAO_HUMANA para um canal não
        auditado, ver autonomy/context.py), e não mais o esquema antigo
        (fato/categoria/origem soltos, sem origem_fato)."""
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = []
            resultado_json = self.salvar_memoria_global(
                "André prefere almoçar depois das 13h.", "preferencia"
            )

        resultado = json.loads(resultado_json)
        self.assertEqual(resultado["status"], "saved")
        self.assertIn("memory_id", resultado)

        doc = self.db.collection("knowledge_nodes")._docs[resultado["memory_id"]]
        self.assertEqual(doc["origem_fato"], INFERENCIA_AGENTE)
        self.assertNotEqual(doc["origem_fato"], DECLARACAO_HUMANA)
        # Esquema novo (via _save_memory_node) -- não mais os campos soltos
        # fato/categoria/origem do escritor direto que existia antes desta
        # sub-entrega.
        self.assertEqual(doc["texto_memoria"], "André prefere almoçar depois das 13h.")
        self.assertNotIn("fato", doc)
        self.assertNotIn("origem", doc)
        # session_id vem do chat_id da sessão do Telegram (único identificador
        # de sessão disponível neste motor -- não há uid de autenticação web).
        self.assertEqual(doc["ultima_sessao_id"], "123456789")

    def test_fato_duplicado_e_ignorado_em_vez_de_criar_um_segundo_no(self):
        """Antes desta sub-entrega, este motor não tinha NENHUMA proteção
        contra duplicata -- o mesmo fato enviado duas vezes criava dois nós.
        Com _save_memory_node, o segundo envio é reconhecido como duplicata
        do primeiro."""
        self.db.collection("knowledge_nodes").document("mem-existente").set({
            "texto_memoria": "André prefere almoçar depois das 13h.",
            "origem_fato": INFERENCIA_AGENTE,
        })
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-existente",
                "similarity": 0.99,
                "data": self.db.collection("knowledge_nodes")._docs["mem-existente"],
            }]
            resultado_json = self.salvar_memoria_global(
                "André prefere almoçar depois das 13h.", "preferencia"
            )

        resultado = json.loads(resultado_json)
        self.assertEqual(resultado["status"], "ignored")
        self.assertEqual(resultado["reason"], "duplicate")
        self.assertEqual(resultado["memory_id"], "mem-existente")

    def test_sem_chave_gemini_configurada_devolve_erro_sem_gravar_nada(self):
        salvar_memoria_global = _extrair_closure_salvar_memoria_global(
            self.db, self.session, lambda _db: {}
        )
        resultado_json = salvar_memoria_global("fato qualquer", "fato_isolado")
        resultado = json.loads(resultado_json)
        self.assertEqual(resultado["status"], "error")
        self.assertEqual(resultado["reason"], "gemini_api_key_nao_configurada")
        self.assertEqual(len(self.db.collection("knowledge_nodes")._docs), 0)

    def test_excecao_de_save_memory_node_e_convertida_em_status_error(self):
        """Mesma postura defensiva do closure original (try/except amplo em
        volta de toda a escrita) -- uma falha real (ex.: Gemini indisponível,
        Firestore fora do ar) não deve propagar e quebrar o turno do
        Telegram; o modelo recebe um status de erro legível e decide como
        comunicar isso ao usuário."""
        with mock.patch.object(main, "_save_memory_node", side_effect=RuntimeError("Firestore indisponível")):
            resultado_json = self.salvar_memoria_global("fato qualquer", "fato_isolado")

        resultado = json.loads(resultado_json)
        self.assertEqual(resultado["status"], "error")
        self.assertEqual(resultado["reason"], "Firestore indisponível")


class TestTelegramResolverConflitoMemoriaReal(unittest.TestCase):
    """Cobre só a DELEGAÇÃO do closure novo `resolver_conflito_memoria`
    (motor Telegram) para `tools.telegram_extended.execute` -- a lógica de
    resolução em si já é testada em
    test_telegram_extended.py::TestResolverConflitoMemoriaIdempotente."""

    def setUp(self):
        self.db = _MockDb()
        arvore = ast.parse(inspect.getsource(telegram_message_tools.build_telegram_tool_closures))
        no = next(
            n for n in arvore.body[0].body
            if isinstance(n, ast.FunctionDef) and n.name == "resolver_conflito_memoria"
        )
        modulo = ast.Module(body=[no], type_ignores=[])
        namespace = {"db": self.db}
        exec(
            compile(ast.fix_missing_locations(modulo), "<closure-resolver-conflito-memoria-telegram-real>", "exec"),
            namespace,
        )
        self.resolver_conflito_memoria = namespace["resolver_conflito_memoria"]

    def test_delega_para_execute_com_os_slots_certos(self):
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "kept_existing"})
            resultado = self.resolver_conflito_memoria("mem-1", "manter_existente")

        mock_execute.assert_called_once_with(
            "resolver_conflito_memoria",
            {
                "memoria_id": "mem-1",
                "decisao": "manter_existente",
                "fato_atualizado": "",
                "categoria": "fato_isolado",
            },
            self.db,
        )
        self.assertEqual(json.loads(resultado)["status"], "resolved")

    def test_argumentos_opcionais_chegam_nos_slots(self):
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "replaced_existing"})
            self.resolver_conflito_memoria(
                "mem-2", "substituir_pelo_novo", fato_atualizado="fato corrigido", categoria="preferencia",
            )

        mock_execute.assert_called_once_with(
            "resolver_conflito_memoria",
            {
                "memoria_id": "mem-2",
                "decisao": "substituir_pelo_novo",
                "fato_atualizado": "fato corrigido",
                "categoria": "preferencia",
            },
            self.db,
        )


class TestTelegramMemoriaClosuresRegistradas(unittest.TestCase):
    """`build_telegram_tool_closures` completo (sem executar nenhum corpo de
    closure -- definir uma função não executa seu corpo) só para confirmar
    que os dois closures desta sub-entrega estão de fato na lista exposta
    ao Gemini, não só definidos e esquecidos fora de `tools_list`."""

    def test_salvar_e_resolver_memoria_estao_na_lista_exposta(self):
        tools_list = telegram_message_tools.build_telegram_tool_closures(
            _MockDb(), {"chat_id": "1"}, None, None, None, None, None, [],
        )
        nomes = {fn.__name__ for fn in tools_list}
        self.assertIn("salvar_memoria_global", nomes)
        self.assertIn("resolver_conflito_memoria", nomes)


if __name__ == "__main__":
    unittest.main()
