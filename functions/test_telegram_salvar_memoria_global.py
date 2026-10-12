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

`TestTelegramSalvarMemoriaGlobalConflitoGravaPendingConfirmations` cobre a
mudança da P06 sub-entrega 3/N: quando `_save_memory_node` devolve
"conflict", `salvar_memoria_global` agora grava o conflito em
`session["pending_confirmations"]["memoria_conflito"]` (mesmo mecanismo de
`propor_lancamento_financeiro`) em vez de depender só do modelo repassar
`memoria_id` numa 2ª chamada de ferramenta -- fecha a LIMITAÇÃO CONHECIDA
registrada pela sub-entrega 2/N. A resolução por botão em si (callbacks
`confirm_memoria_manter`/`confirm_memoria_substituir`) é testada em
`test_telegram_callbacks_confirmacoes_memoria.py`, não aqui -- este arquivo
cobre só o closure que GRAVA a pendência, não quem a CONSOME.
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


class TestTelegramSalvarMemoriaGlobalConflitoGravaPendingConfirmations(unittest.TestCase):
    """P06 sub-entrega 3/N: `salvar_memoria_global` passa a gravar o
    conflito em `session['pending_confirmations']['memoria_conflito']`
    quando `_save_memory_node` devolve status "conflict" -- fecha a
    limitação cross-turn do `memoria_id` registrada pela sub-entrega 2/N
    (ver comentário do closure em telegram_message_tools.py). A resolução
    por botão em si é testada em
    test_telegram_callbacks_confirmacoes_memoria.py, não aqui."""

    def setUp(self):
        self.db = _MockDb()
        self.session = {"chat_id": "123456789"}
        self.salvar_memoria_global = _extrair_closure_salvar_memoria_global(
            self.db, self.session, lambda _db: {"gemini_api_key": "fake-key"}
        )

    def test_conflito_grava_pending_confirmations_com_os_campos_certos(self):
        # "categoria" (parâmetro, fato NOVO proposto) e "categoria_existente"
        # (campo do resultado, fato que SERIA mantido) propositalmente
        # diferentes -- achado real de revisão adversarial independente
        # desta sub-entrega: um teste anterior usava o mesmo valor nos dois
        # lugares e não conseguia detectar os dois campos sendo trocados
        # entre si.
        conflito = {
            "status": "conflict",
            "memory_id": "mem-existente-1",
            "categoria_existente": "fato_isolado",
            "existing_text": "André prefere almoçar depois das 13h.",
            "similarity": 0.91,
            "proposed_text": "André prefere almoçar depois das 13h30.",
        }
        with mock.patch.object(main, "_save_memory_node", return_value=conflito):
            resultado_json = self.salvar_memoria_global(
                "André prefere almoçar depois das 13h30.", "preferencia"
            )

        resultado = json.loads(resultado_json)
        self.assertEqual(resultado["status"], "conflict")

        pendente = self.session.get("pending_confirmations", {}).get("memoria_conflito")
        self.assertIsNotNone(pendente)
        self.assertEqual(pendente["memory_id"], "mem-existente-1")
        self.assertEqual(pendente["fato_atualizado"], "André prefere almoçar depois das 13h30.")
        self.assertEqual(pendente["categoria"], "preferencia")
        self.assertEqual(pendente["categoria_existente"], "fato_isolado")
        self.assertEqual(pendente["existing_text"], "André prefere almoçar depois das 13h.")
        self.assertEqual(self.session.get("_pending_confirm_type"), "memoria_conflito")

    def test_conflito_sem_categoria_existente_usa_fallback_neutro_nao_a_categoria_do_fato_novo(self):
        """Achado real de uma 2ª rodada de revisão adversarial: a 1ª versão
        deste fallback usava `categoria` (a do fato NOVO, descartado na
        decisão "manter_existente") quando `categoria_existente` estava
        ausente -- reintroduzindo o mesmo erro semântico que esse campo
        foi criado para evitar. O fallback correto é neutro
        ("fato_isolado"), nunca a categoria do fato novo."""
        conflito = {
            "status": "conflict",
            "memory_id": "mem-existente-3",
            "existing_text": "texto antigo",
            "proposed_text": "texto novo",
        }
        with mock.patch.object(main, "_save_memory_node", return_value=conflito):
            self.salvar_memoria_global("texto novo", "preferencia")

        pendente = self.session["pending_confirmations"]["memoria_conflito"]
        self.assertEqual(pendente["categoria_existente"], "fato_isolado")
        self.assertNotEqual(pendente["categoria_existente"], "preferencia")

    def test_conflito_sem_proposed_text_usa_o_fato_original_como_fallback(self):
        """`_save_memory_node` sempre devolve `proposed_text` no ramo
        "conflict" real (ver main.py), mas o closure não deve depender só
        disso -- se um mock/stub devolver o campo vazio ou ausente, o fato
        originalmente passado para `salvar_memoria_global` ainda deve ser
        usado como `fato_atualizado` pendente."""
        conflito = {
            "status": "conflict",
            "memory_id": "mem-existente-2",
            "existing_text": "texto antigo",
            "proposed_text": "",
        }
        with mock.patch.object(main, "_save_memory_node", return_value=conflito):
            self.salvar_memoria_global("fato novo proposto", "fato_isolado")

        pendente = self.session["pending_confirmations"]["memoria_conflito"]
        self.assertEqual(pendente["fato_atualizado"], "fato novo proposto")

    def test_status_saved_sem_conflito_nao_grava_nenhuma_pendencia(self):
        """Caminho feliz (sem conflito) não deve tocar
        pending_confirmations -- só o ramo "conflict" grava a pendência
        nova desta sub-entrega."""
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = []
            self.salvar_memoria_global("fato qualquer sem conflito", "fato_isolado")

        self.assertNotIn("pending_confirmations", self.session)
        self.assertNotIn("_pending_confirm_type", self.session)

    def test_status_ignored_duplicado_nao_grava_nenhuma_pendencia(self):
        self.db.collection("knowledge_nodes").document("mem-existente").set({
            "texto_memoria": "fato repetido",
        })
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-existente",
                "similarity": 0.99,
                "data": self.db.collection("knowledge_nodes")._docs["mem-existente"],
            }]
            self.salvar_memoria_global("fato repetido", "fato_isolado")

        self.assertNotIn("pending_confirmations", self.session)

    def test_status_error_nao_grava_nenhuma_pendencia(self):
        with mock.patch.object(main, "_save_memory_node", side_effect=RuntimeError("boom")):
            self.salvar_memoria_global("fato qualquer", "fato_isolado")

        self.assertNotIn("pending_confirmations", self.session)


class TestTelegramResolverConflitoMemoriaReal(unittest.TestCase):
    """Cobre a DELEGAÇÃO do closure novo `resolver_conflito_memoria`
    (motor Telegram) para `tools.telegram_extended.execute` -- a lógica de
    resolução em si já é testada em
    test_telegram_extended.py::TestResolverConflitoMemoriaIdempotente --
    e, desde a P06 sub-entrega 3/N, a limpeza de
    `session["pending_confirmations"]["memoria_conflito"]` quando este
    caminho alternativo por ferramenta resolve o MESMO conflito que o
    botão inline (`confirm_memoria_manter`/`confirm_memoria_substituir`,
    telegram_callbacks_confirmacoes.py) também resolveria -- achado real
    de revisão adversarial independente desta sub-entrega: sem essa
    limpeza, a pendência ficava órfã e o teclado reaparecia para um
    conflito já resolvido."""

    def setUp(self):
        self.db = _MockDb()
        self.session = {"chat_id": "123456789"}
        arvore = ast.parse(inspect.getsource(telegram_message_tools.build_telegram_tool_closures))
        no = next(
            n for n in arvore.body[0].body
            if isinstance(n, ast.FunctionDef) and n.name == "resolver_conflito_memoria"
        )
        modulo = ast.Module(body=[no], type_ignores=[])
        namespace = {"db": self.db, "session": self.session, "json": json}
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
        # "updated" (nunca "resolved") é o status real que
        # `tools/telegram_extended.py::execute` devolve para
        # "substituir_pelo_novo" -- propaga de
        # `main._save_memory_node(force_update_id=...)`. Usar o status
        # real aqui (em vez do "resolved" de "manter_existente") é o que
        # expôs o achado da 2ª rodada de revisão adversarial coberto em
        # `test_resolve_substituir_pelo_novo_com_status_updated_limpa_pending_confirmations`
        # abaixo -- este teste aqui continua focado só nos slots.
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "updated", "decision": "replaced_existing"})
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

    def test_resolve_a_mesma_pendencia_do_botao_limpa_pending_confirmations(self):
        """Achado real de revisão adversarial independente desta
        sub-entrega: se este caminho alternativo por ferramenta resolver o
        MESMO conflito que `salvar_memoria_global` registrou em
        `session["pending_confirmations"]["memoria_conflito"]`, a
        pendência não pode ficar órfã -- senão o teclado inline
        (`_CONFIRM_MEMORIA_KEYBOARD`) continuaria aparecendo nas respostas
        seguintes, oferecendo um botão para um conflito já resolvido."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memory_id": "mem-1", "fato_atualizado": "x", "categoria": "fato_isolado"}
        }
        self.session["_pending_confirm_type"] = "memoria_conflito"
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "kept_existing"})
            self.resolver_conflito_memoria("mem-1", "manter_existente")

        self.assertNotIn("memoria_conflito", self.session.get("pending_confirmations", {}))
        # Não usa .pop(...) de propósito (ver comentário do closure): o
        # pipeline de telegram_handlers_core.py só sincroniza
        # `_pending_confirm_type` de volta para a sessão relida do
        # Firestore quando a chave CONTINUA presente em `session` -- aqui
        # ela deve existir, com valor None, não ter sido removida.
        self.assertIn("_pending_confirm_type", self.session)
        self.assertIsNone(self.session["_pending_confirm_type"])

    def test_resolve_substituir_pelo_novo_com_status_updated_limpa_pending_confirmations(self):
        """Achado real de uma 2ª rodada de revisão adversarial
        independente: a 1ª versão deste fix só reconhecia
        `status == "resolved"` como sucesso, mas
        `tools/telegram_extended.py::execute("resolver_conflito_memoria",
        {"decisao": "substituir_pelo_novo", ...}, db)` nunca devolve
        "resolved" -- propaga o resultado de
        `main._save_memory_node(force_update_id=...)`, cujo status de
        sucesso é "updated" (ver main.py). A limpeza da pendência NUNCA
        disparava para "substituir_pelo_novo" até este teste existir."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memory_id": "mem-1", "fato_atualizado": "x", "categoria": "fato_isolado"}
        }
        self.session["_pending_confirm_type"] = "memoria_conflito"
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({
                "status": "updated", "memory_id": "mem-1", "decision": "replaced_existing",
            })
            self.resolver_conflito_memoria("mem-1", "substituir_pelo_novo", fato_atualizado="novo texto")

        self.assertNotIn("memoria_conflito", self.session.get("pending_confirmations", {}))
        self.assertIn("_pending_confirm_type", self.session)
        self.assertIsNone(self.session["_pending_confirm_type"])

    def test_resolve_memoria_id_diferente_do_pendente_nao_limpa_a_pendencia(self):
        """Dois conflitos pendentes "ao mesmo tempo" (hipotético, mas não
        impossível) não devem se apagar um ao outro -- só o `memoria_id`
        que de fato bate com o resolvido é limpo."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memory_id": "mem-DIFERENTE", "fato_atualizado": "x", "categoria": "fato_isolado"}
        }
        self.session["_pending_confirm_type"] = "memoria_conflito"
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "kept_existing"})
            self.resolver_conflito_memoria("mem-1", "manter_existente")

        self.assertIn("memoria_conflito", self.session["pending_confirmations"])
        self.assertEqual(self.session["_pending_confirm_type"], "memoria_conflito")

    def test_resultado_error_de_execute_nao_limpa_a_pendencia(self):
        """Só um "resolved" de verdade limpa a pendência -- um "error"
        (ex.: decisão inválida, memoria_id inexistente) não deve apagar o
        rascunho que o botão ainda pode resolver depois."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memory_id": "mem-1", "fato_atualizado": "x", "categoria": "fato_isolado"}
        }
        self.session["_pending_confirm_type"] = "memoria_conflito"
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "error", "reason": "memory_not_found"})
            self.resolver_conflito_memoria("mem-1", "manter_existente")

        self.assertIn("memoria_conflito", self.session["pending_confirmations"])
        self.assertEqual(self.session["_pending_confirm_type"], "memoria_conflito")

    def test_sem_pendencia_ativa_nao_lanca_e_devolve_resultado_normal(self):
        """Chamado sem nenhuma pendência na sessão (ex.: um cliente MCP,
        sem session["pending_confirmations"]) -- não deve lançar nem
        alterar nada, só devolver o resultado de `execute` normalmente."""
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "kept_existing"})
            resultado = self.resolver_conflito_memoria("mem-1", "manter_existente")

        self.assertEqual(json.loads(resultado)["status"], "resolved")
        self.assertNotIn("pending_confirmations", self.session)


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
