"""Testes para P06 sub-entregas 2/N e 3/N (docs/plano-hermes-autonomo-2026-09-06.md,
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

P06 sub-entrega 3/N fecha a LIMITAÇÃO CONHECIDA documentada pela 2/N (ver
pendência em docs/autonomia/execucao.md): o `memory_id` de um conflito
devolvido por `salvar_memoria_global` passa a ser persistido em
`session["pending_confirmations"]["memoria_conflito"]`, e
`resolver_conflito_memoria` passa a aceitar `memoria_id` omitido, caindo
nesse valor pendente. `TestTelegramConflitoDeMemoriaPersistenteEntreTurnos`
cobre o ciclo completo (conflito -> pendência gravada -> resolução sem
repassar o id -> pendência limpa), e `TestTelegramResolverConflitoMemoriaReal`
foi estendida com o mesmo fallback isoladamente. 3 rodadas de revisão
adversarial interna encontraram, cada uma, um achado real sobre essa mesma
3/N (pendência apagada mesmo em falha; "ignored" tratado como sucesso;
corrupção com dois conflitos concorrentes) -- os testes correspondentes
estão anotados com qual rodada os motivou. Uma 4ª rodada interna não achou
nada (critério de parada atingido), mas o revisor automático Codex, na
própria PR aberta, encontrou mais 1 achado real (não coberto pelas 4
rodadas internas): `categoria="fato_isolado"` passado explicitamente pelo
modelo era indistinguível do valor omitido (mesmo valor do default
antigo) e podia ser sobrescrito sem necessidade pelo fallback de
pendente -- corrigido trocando o default do parâmetro para `""` (mesmo
sentinela de "omitido" de `fato_atualizado`) e só aplicando o default real
"fato_isolado" depois do fallback; `test_categoria_explicita_fato_isolado_prevalece_sobre_pendente`
e `test_categoria_omitida_sem_pendente_cai_no_default_fato_isolado` cobrem
esse achado, e uma 5ª rodada de revisão adversarial interna (focada só
nesse fix) não achou nada de novo.
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


def _extrair_closure_resolver_conflito_memoria(db, session):
    """Mesma técnica de extração acima, para `resolver_conflito_memoria`.

    P06 sub-entrega 3/N: diferente da versão original (testada antes só com
    `namespace = {"db": db}`), este closure agora também referencia
    `session` (fallback de `memoria_id` pendente) -- precisa entrar no
    namespace, senão a extração reproduz um `NameError` que nunca ocorre em
    produção (lá `session` sempre está em escopo, capturado pela factory
    `build_telegram_tool_closures`)."""
    arvore = ast.parse(inspect.getsource(telegram_message_tools.build_telegram_tool_closures))
    no = next(
        n for n in arvore.body[0].body
        if isinstance(n, ast.FunctionDef) and n.name == "resolver_conflito_memoria"
    )
    modulo = ast.Module(body=[no], type_ignores=[])
    namespace = {"db": db, "session": session, "json": json}
    exec(
        compile(ast.fix_missing_locations(modulo), "<closure-resolver-conflito-memoria-telegram-real>", "exec"),
        namespace,
    )
    return namespace["resolver_conflito_memoria"]


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

    def test_conflito_grava_memoria_id_em_pending_confirmations_da_sessao(self):
        """P06 sub-entrega 3/N: `main._save_memory_node` devolve
        `{"status": "conflict", "memory_id": ...}` (confirmado lendo o
        branch real) quando o fato novo é parecido, mas não igual, a um nó
        já existente -- `_find_similar_memory_nodes` com similaridade entre
        os dois limiares reproduz exatamente esse caminho, sem mockar o
        resultado de `_save_memory_node` diretamente (preserva a cobertura
        da lógica real de decisão saved/ignored/conflict)."""
        self.db.collection("knowledge_nodes").document("mem-parecido").set({
            "texto_memoria": "André prefere reuniões pela manhã.",
            "tipo": "preferencia",
        })
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-parecido",
                "similarity": 0.9,  # entre CREATE e DUPLICATE: dispara conflict, não ignored.
                "data": self.db.collection("knowledge_nodes")._docs["mem-parecido"],
            }]
            resultado_json = self.salvar_memoria_global(
                "André prefere reuniões à tarde.", "preferencia"
            )

        resultado = json.loads(resultado_json)
        self.assertEqual(resultado["status"], "conflict")
        self.assertEqual(resultado["memory_id"], "mem-parecido")

        pendente = self.session["pending_confirmations"]["memoria_conflito"]
        self.assertEqual(pendente["memoria_id"], "mem-parecido")
        self.assertEqual(pendente["fato"], "André prefere reuniões à tarde.")
        self.assertEqual(pendente["categoria"], "preferencia")
        # Não deve interferir no mecanismo de teclado inline dos outros
        # fluxos de confirmação (acao/financeiro/whatsapp) -- conflito de
        # memória não tem teclado, o modelo resolve por texto.
        self.assertNotIn("_pending_confirm_type", self.session)

    def test_status_diferente_de_conflict_nao_grava_pendencia(self):
        """saved/ignored/error não devem criar uma pendência de conflito --
        só o status "conflict" tem um memory_id que precisa sobreviver entre
        turnos."""
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = []
            self.salvar_memoria_global("fato qualquer, sem similar nenhum", "fato_isolado")

        self.assertNotIn("pending_confirmations", self.session)


class TestTelegramResolverConflitoMemoriaReal(unittest.TestCase):
    """Cobre a DELEGAÇÃO do closure `resolver_conflito_memoria` (motor
    Telegram) para `tools.telegram_extended.execute` -- a lógica de
    resolução em si já é testada em
    test_telegram_extended.py::TestResolverConflitoMemoriaIdempotente --
    e, desde a P06 sub-entrega 3/N, o fallback de `memoria_id` para a
    pendência de sessão gravada por `salvar_memoria_global`."""

    def setUp(self):
        self.db = _MockDb()
        self.session = {"chat_id": "123456789"}
        self.resolver_conflito_memoria = _extrair_closure_resolver_conflito_memoria(
            self.db, self.session
        )

    def test_delega_para_execute_com_os_slots_certos(self):
        # Chamadas por kwargs -- mesma forma que a invocação real
        # (`telegram_utils.py::_execute_tool_call` sempre chama `fn(**kwargs)`,
        # nunca posicional; e desde esta sub-entrega `decisao` passou a
        # vir ANTES de `memoria_id` na assinatura, ver comentário do closure).
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "kept_existing"})
            resultado = self.resolver_conflito_memoria(decisao="manter_existente", memoria_id="mem-1")

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
                decisao="substituir_pelo_novo", memoria_id="mem-2",
                fato_atualizado="fato corrigido", categoria="preferencia",
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

    def test_memoria_id_omitido_usa_pendente_da_sessao(self):
        """P06 sub-entrega 3/N: o caso central da limitação fechada -- o
        modelo chama a tool sem repassar `memoria_id` nenhum (esqueceu, ou
        nunca o viu de novo no histórico), e o closure recupera o id do
        conflito pendente gravado por `salvar_memoria_global`."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memoria_id": "mem-pendente", "fato": "x", "categoria": "fato_isolado"},
        }
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "kept_existing"})
            resultado = self.resolver_conflito_memoria(decisao="manter_existente")

        # `fato_atualizado` também cai no fallback pendente quando omitido
        # (achado real da 2ª rodada de revisão, ver fix em
        # resolver_conflito_memoria) -- aqui é "x" só porque é o valor de
        # preenchimento do fixture pendente, não o foco deste teste (que é o
        # fallback de `memoria_id`); coberto isoladamente em
        # `test_substituir_pelo_novo_sem_fato_atualizado_usa_o_fato_pendente_contra_o_execute_real`.
        mock_execute.assert_called_once_with(
            "resolver_conflito_memoria",
            {
                "memoria_id": "mem-pendente",
                "decisao": "manter_existente",
                "fato_atualizado": "x",
                "categoria": "fato_isolado",
            },
            self.db,
        )
        self.assertEqual(json.loads(resultado)["status"], "resolved")
        # Resolvida: a pendência não deve sobreviver para o próximo turno.
        self.assertNotIn("memoria_conflito", self.session["pending_confirmations"])

    def test_memoria_id_explicito_prevalece_sobre_pendente(self):
        """Quando o modelo INFORMA um memoria_id (ex.: recuperou o conflito
        chamando salvar_memoria_global de novo), ele prevalece -- o fallback
        só cobre a AUSÊNCIA, nunca sobrescreve uma escolha explícita."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memoria_id": "mem-pendente-antigo", "fato": "x", "categoria": "fato_isolado"},
        }
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "kept_existing"})
            self.resolver_conflito_memoria(decisao="manter_existente", memoria_id="mem-explicito-novo")

        # `fato_atualizado`/`categoria` NÃO caem no fallback do pendente
        # aqui -- achado real da 3ª rodada de revisão adversarial: o
        # pendente é de um `memoria_id` DIFERENTE ("mem-pendente-antigo"),
        # então usar o `fato`/`categoria` dele para resolver
        # "mem-explicito-novo" gravaria dado de um conflito errado no nó de
        # memória errado (corrupção silenciosa, confirmada por execução
        # real contra `_save_memory_node`). O fallback só se aplica quando
        # `pendente.get("memoria_id") == memoria_id` (ver `pendente_corresponde`
        # em `resolver_conflito_memoria`).
        mock_execute.assert_called_once_with(
            "resolver_conflito_memoria",
            {
                "memoria_id": "mem-explicito-novo",
                "decisao": "manter_existente",
                "fato_atualizado": "",
                "categoria": "fato_isolado",
            },
            self.db,
        )
        # memoria_id explícito != pendente -- a pendência (de um OUTRO
        # conflito) não é apagada; pode ainda estar à espera de resolução.
        self.assertIn("memoria_conflito", self.session["pending_confirmations"])

    def test_categoria_explicita_fato_isolado_prevalece_sobre_pendente(self):
        """Achado real do revisor automático Codex na própria PR desta
        sub-entrega (não de uma das 4 rodadas de revisão adversarial
        interna, que já tinham encerrado quando o comentário chegou):
        `categoria` tinha default "fato_isolado" (igual ao valor literal),
        então um valor explícito do modelo igual ao default era
        indistinguível de uma omissão -- o fallback de pendente sobrescrevia
        uma escolha explícita do modelo sem necessidade. Aqui o pendente
        (mesmo memoria_id) tem categoria "preferencia", mas o modelo passa
        "fato_isolado" explicitamente -- deve prevalecer, nunca ser trocado
        pelo "preferencia" do pendente."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memoria_id": "mem-1", "fato": "x", "categoria": "preferencia"},
        }
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "replaced_existing"})
            self.resolver_conflito_memoria(
                decisao="substituir_pelo_novo",
                memoria_id="mem-1",
                fato_atualizado="fato novo",
                categoria="fato_isolado",
            )

        mock_execute.assert_called_once_with(
            "resolver_conflito_memoria",
            {
                "memoria_id": "mem-1",
                "decisao": "substituir_pelo_novo",
                "fato_atualizado": "fato novo",
                "categoria": "fato_isolado",
            },
            self.db,
        )

    def test_categoria_omitida_sem_pendente_cai_no_default_fato_isolado(self):
        """Sem `categoria` e sem pendente (ou pendente sem campo
        `categoria`), o comportamento de sempre se mantém: default
        "fato_isolado" -- o novo sentinela "" só troca COMO o default é
        aplicado (depois do fallback de pendente, não antes), nunca o
        valor final num caso sem pendente."""
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "kept_existing"})
            self.resolver_conflito_memoria(decisao="manter_existente", memoria_id="mem-1")

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

    def test_sem_memoria_id_e_sem_pendente_devolve_erro_sem_chamar_execute(self):
        """Sem fallback disponível, a chamada não pode seguir para
        `execute()` com memoria_id vazio -- isso gravaria/atualizaria um
        documento Firestore com ID vazio silenciosamente. Erro controlado,
        mesmo padrão de `gemini_api_key_nao_configurada` em
        `salvar_memoria_global`."""
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            resultado_json = self.resolver_conflito_memoria(decisao="manter_existente")

        mock_execute.assert_not_called()
        resultado = json.loads(resultado_json)
        self.assertEqual(resultado["status"], "error")
        self.assertEqual(resultado["reason"], "memoria_id_ausente_sem_conflito_pendente")

    def test_pendente_so_e_removido_quando_corresponde_ao_id_resolvido(self):
        """Mesmo quando o memoria_id explícito é igual ao pendente (modelo
        repetiu o id corretamente), a pendência deve ser limpa -- não só no
        caminho de fallback (omitido)."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memoria_id": "mem-1", "fato": "x", "categoria": "fato_isolado"},
        }
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({"status": "resolved", "decision": "kept_existing"})
            self.resolver_conflito_memoria(decisao="manter_existente", memoria_id="mem-1")

        self.assertNotIn("memoria_conflito", self.session["pending_confirmations"])

    def test_resolucao_com_decisao_invalida_nao_limpa_a_pendencia(self):
        """Achado real da revisão adversarial desta sub-entrega: a 1ª versão
        apagava a pendência só porque o memoria_id coincidia, mesmo quando
        `execute()` devolvia uma falha real (decisão vazia/inválida cai em
        `ERRO|{"status":"error","reason":"decisao_invalida"}` em
        `tools/telegram_extended.py`, sem resolver nada no Firestore). Sem
        este guard, o fato do usuário ficava preso sem solução automática:
        o conflito nunca era resolvido, mas o fallback que permitiria
        tentar de novo sem repassar o memoria_id era destruído de qualquer
        forma."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memoria_id": "mem-1", "fato": "x", "categoria": "fato_isolado"},
        }
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = "ERRO|" + json.dumps({"status": "error", "reason": "decisao_invalida"})
            resultado = self.resolver_conflito_memoria(decisao="decisao_que_nao_existe", memoria_id="mem-1")

        self.assertTrue(resultado.startswith("ERRO|"))
        self.assertIn("memoria_conflito", self.session["pending_confirmations"])
        self.assertEqual(self.session["pending_confirmations"]["memoria_conflito"]["memoria_id"], "mem-1")

    def test_resolucao_com_status_error_generico_nao_limpa_a_pendencia(self):
        """Mesma proteção do teste acima, para o outro formato de falha que
        `_save_memory_node(force_update_id=...)` pode devolver sem o prefixo
        `ERRO|` -- `{"status": "error", "reason": "memory_not_found", ...}`
        (ver `main.py::_save_memory_node`, branch `force_update_id` com
        `snap.exists` falso)."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memoria_id": "mem-1", "fato": "x", "categoria": "fato_isolado"},
        }
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({
                "status": "error", "reason": "memory_not_found", "memory_id": "mem-1",
            })
            resultado = self.resolver_conflito_memoria(decisao="substituir_pelo_novo", memoria_id="mem-1")

        self.assertEqual(json.loads(resultado)["status"], "error")
        self.assertIn("memoria_conflito", self.session["pending_confirmations"])

    def test_resolucao_com_status_ignored_nao_limpa_a_pendencia(self):
        """Achado real da 2ª rodada de revisão adversarial desta sub-entrega:
        `resolvido_com_sucesso` checava só `status != "error"`, então um
        `{"status": "ignored", "reason": "empty_fact"}` -- devolvido por
        `_save_memory_node(force_update_id=...)` quando `fato_atualizado`
        chega vazio (ver `main.py`, checagem de `fato` vazio ANTES de
        `force_update_id`) -- era tratado como sucesso e apagava a
        pendência sem nada ter sido gravado no Firestore. Teste unitário
        isolado (execute mockado) do guard adicionado; o caminho completo
        sem mock, incluindo o fallback que normalmente evita este "ignored"
        na prática, está em
        `test_substituir_pelo_novo_sem_fato_atualizado_usa_o_fato_pendente_contra_o_execute_real`."""
        self.session["pending_confirmations"] = {
            "memoria_conflito": {"memoria_id": "mem-1", "fato": "x", "categoria": "fato_isolado"},
        }
        with mock.patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = json.dumps({
                "status": "ignored", "reason": "empty_fact", "decision": "replaced_existing",
            })
            resultado = self.resolver_conflito_memoria(
                decisao="substituir_pelo_novo", memoria_id="mem-1", fato_atualizado="algo",
            )

        self.assertEqual(json.loads(resultado)["status"], "ignored")
        self.assertIn("memoria_conflito", self.session["pending_confirmations"])
        self.assertEqual(self.session["pending_confirmations"]["memoria_conflito"]["memoria_id"], "mem-1")


class TestTelegramConflitoDeMemoriaPersistenteEntreTurnos(unittest.TestCase):
    """Ciclo completo ponta a ponta (P06 sub-entrega 3/N), com a MESMA
    instância de `session` entre os dois closures -- reproduz o que
    `telegram_handlers_core.py` preserva de fato entre turnos (todo o dict
    `session["pending_confirmations"]`, não campos avulsos), sem precisar
    montar o pipeline completo de `_process_telegram_message`."""

    def setUp(self):
        self.db = _MockDb()
        self.session = {"chat_id": "123456789"}
        self.salvar_memoria_global = _extrair_closure_salvar_memoria_global(
            self.db, self.session, lambda _db: {"gemini_api_key": "fake-key"}
        )
        self.resolver_conflito_memoria = _extrair_closure_resolver_conflito_memoria(
            self.db, self.session
        )

    def test_conflito_depois_resolvido_sem_o_modelo_repassar_memoria_id(self):
        self.db.collection("knowledge_nodes").document("mem-parecido").set({
            "texto_memoria": "André prefere reuniões pela manhã.",
            "tipo": "preferencia",
        })
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-parecido",
                "similarity": 0.9,
                "data": self.db.collection("knowledge_nodes")._docs["mem-parecido"],
            }]
            resultado_conflito = json.loads(
                self.salvar_memoria_global("André prefere reuniões à tarde.", "preferencia")
            )
        self.assertEqual(resultado_conflito["status"], "conflict")

        # "Próximo turno": o modelo só sabe a decisão do usuário (ex.: "pode
        # manter o antigo"), sem o memoria_id opaco -- exatamente o cenário
        # que a LIMITAÇÃO CONHECIDA da sub-entrega 2/N descrevia.
        with mock.patch.object(main, "_save_memory_node") as mock_save:
            resultado_resolvido = json.loads(
                self.resolver_conflito_memoria(decisao="manter_existente")
            )
        mock_save.assert_not_called()  # manter_existente não chama _save_memory_node.
        self.assertEqual(resultado_resolvido["status"], "resolved")
        self.assertEqual(resultado_resolvido["decision"], "kept_existing")
        self.assertEqual(resultado_resolvido["memory_id"], "mem-parecido")
        self.assertNotIn("memoria_conflito", self.session.get("pending_confirmations", {}))

    def test_substituir_pelo_novo_sem_fato_atualizado_usa_o_fato_pendente_contra_o_execute_real(self):
        """Achado real da 2ª rodada de revisão adversarial desta sub-entrega:
        chamar `resolver_conflito_memoria(decisao="substituir_pelo_novo")` sem
        `fato_atualizado` (plausível -- tem default "" e não é obrigatório no
        schema real do Gemini) acionava, contra o `_save_memory_node` e o
        `execute()` REAIS (sem mock de nenhum dos dois), o branch de
        `fato` vazio em `main.py::_save_memory_node` -- checado ANTES de
        `force_update_id` -- que devolve `{"status":"ignored",
        "reason":"empty_fact"}` sem gravar nada no Firestore. Como a versão
        anterior só excluía `status == "error"` da checagem de sucesso, a
        pendência era apagada mesmo assim, perdendo o fato do usuário e o
        `memoria_id` que permitiria tentar de novo. Este teste roda o
        caminho completo e real (nenhum `mock.patch` em `_save_memory_node`
        nem em `execute`) para confirmar que o fallback novo resolve isso de
        fato, não só na superfície do closure Telegram."""
        self.db.collection("knowledge_nodes").document("mem-parecido").set({
            "texto_memoria": "André prefere reuniões pela manhã.",
            "tipo": "preferencia",
        })
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-parecido",
                "similarity": 0.9,
                "data": self.db.collection("knowledge_nodes")._docs["mem-parecido"],
            }]
            resultado_conflito = json.loads(
                self.salvar_memoria_global("André prefere reuniões à tarde.", "preferencia")
            )
        self.assertEqual(resultado_conflito["status"], "conflict")
        self.assertEqual(
            self.session["pending_confirmations"]["memoria_conflito"]["fato"],
            "André prefere reuniões à tarde.",
        )

        # "Próximo turno": o modelo decide substituir, mas não repassa
        # `fato_atualizado` (nem `memoria_id`) -- execute() e
        # _save_memory_node reais, sem mock, só embedding/similaridade
        # isolados (mesmo motivo de sempre: não há vector search no mock).
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            resultado_resolvido = json.loads(
                self.resolver_conflito_memoria(decisao="substituir_pelo_novo")
            )

        self.assertEqual(resultado_resolvido["status"], "updated")
        self.assertEqual(resultado_resolvido["decision"], "replaced_existing")
        self.assertEqual(resultado_resolvido["memory_id"], "mem-parecido")

        doc_final = self.db.collection("knowledge_nodes")._docs["mem-parecido"]
        self.assertEqual(doc_final["texto_memoria"], "André prefere reuniões à tarde.")
        self.assertNotIn("memoria_conflito", self.session.get("pending_confirmations", {}))

    def test_substituir_pelo_novo_com_decisao_invalida_nao_perde_a_pendencia(self):
        """Contraponto de regressão: `decisao` inválida continua caindo em
        `{"status":"error","reason":"decisao_invalida"}` (prefixado
        "ERRO|") e a pendência deve seguir intacta -- a correção do achado
        de `fato_atualizado` vazio não deve afetar este caminho, já coberto
        pela 1ª rodada de revisão (`test_resolucao_com_decisao_invalida_nao_limpa_a_pendencia`
        em `TestTelegramResolverConflitoMemoriaReal`); repetido aqui contra o
        `execute()` real ponta a ponta para fechar a mesma lacuna de
        cobertura apontada pela 2ª rodada (nenhum teste de
        `TestTelegramConflitoDeMemoriaPersistenteEntreTurnos` cobria
        `substituir_pelo_novo` sem mock)."""
        self.db.collection("knowledge_nodes").document("mem-parecido").set({
            "texto_memoria": "André prefere reuniões pela manhã.",
            "tipo": "preferencia",
        })
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-parecido",
                "similarity": 0.9,
                "data": self.db.collection("knowledge_nodes")._docs["mem-parecido"],
            }]
            self.salvar_memoria_global("André prefere reuniões à tarde.", "preferencia")

        resultado_resolvido = self.resolver_conflito_memoria(decisao="decisao_inexistente")
        self.assertTrue(resultado_resolvido.startswith("ERRO|"))

        doc_final = self.db.collection("knowledge_nodes")._docs["mem-parecido"]
        self.assertEqual(doc_final["texto_memoria"], "André prefere reuniões pela manhã.")
        self.assertIn("memoria_conflito", self.session.get("pending_confirmations", {}))
        self.assertEqual(
            self.session["pending_confirmations"]["memoria_conflito"]["memoria_id"],
            "mem-parecido",
        )

    def test_dois_conflitos_em_sequencia_resolver_o_antigo_nao_usa_o_fato_do_mais_novo(self):
        """Achado real da 3ª rodada de revisão adversarial desta sub-entrega:
        `session["pending_confirmations"]["memoria_conflito"]` é um slot
        ÚNICO por sessão -- se o conflito B ocorre antes de o conflito A ser
        resolvido, `salvar_memoria_global` sobrescreve o pendente da sessão
        com os dados de B. Resolver A depois, passando `memoria_id="mem-A"`
        explicitamente mas SEM `fato_atualizado` (mesmo cenário plausível
        do achado da 2ª rodada), não pode usar o `fato`/`categoria` de B
        (o único que resta no slot) -- isso gravaria o fato ERRADO no nó de
        memória de A. O fallback só vale quando `pendente.get("memoria_id")
        == memoria_id` (ver `pendente_corresponde` em
        `resolver_conflito_memoria`); fora disso, `fato_atualizado` vazio
        deve resultar em `{"status":"ignored","reason":"empty_fact"}` (sem
        gravar nada), nunca em gravar o texto do outro conflito."""
        self.db.collection("knowledge_nodes").document("mem-A").set({
            "texto_memoria": "Texto original A (antigo).",
            "tipo": "preferencia",
        })
        self.db.collection("knowledge_nodes").document("mem-B").set({
            "texto_memoria": "Texto original B (recente).",
            "tipo": "preferencia",
        })

        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-A",
                "similarity": 0.9,
                "data": self.db.collection("knowledge_nodes")._docs["mem-A"],
            }]
            resultado_a = json.loads(
                self.salvar_memoria_global("Fato NOVO A (correto p/ mem-A).", "preferencia")
            )
        self.assertEqual(resultado_a["status"], "conflict")
        self.assertEqual(resultado_a["memory_id"], "mem-A")

        # Conflito B ocorre ANTES de A ser resolvido -- sobrescreve o slot
        # único de pendência da sessão.
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-B",
                "similarity": 0.9,
                "data": self.db.collection("knowledge_nodes")._docs["mem-B"],
            }]
            resultado_b = json.loads(
                self.salvar_memoria_global("Fato NOVO B (nada a ver com A).", "fato_isolado")
            )
        self.assertEqual(resultado_b["status"], "conflict")
        self.assertEqual(resultado_b["memory_id"], "mem-B")
        self.assertEqual(
            self.session["pending_confirmations"]["memoria_conflito"]["memoria_id"], "mem-B",
        )

        # Resolve A explicitamente (recupera o id de algum jeito fora da
        # sessão, ex.: repetiu a chamada a salvar_memoria_global), mas sem
        # repassar fato_atualizado -- não deve "herdar" o fato de B.
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            resultado_resolver_a = json.loads(
                self.resolver_conflito_memoria(decisao="substituir_pelo_novo", memoria_id="mem-A")
            )

        self.assertEqual(resultado_resolver_a["status"], "ignored")
        self.assertEqual(resultado_resolver_a["reason"], "empty_fact")

        doc_a_final = self.db.collection("knowledge_nodes")._docs["mem-A"]
        doc_b_final = self.db.collection("knowledge_nodes")._docs["mem-B"]
        # mem-A não foi tocado -- nem com o texto certo (não repassado) nem,
        # pior, com o texto errado de B.
        self.assertEqual(doc_a_final["texto_memoria"], "Texto original A (antigo).")
        self.assertEqual(doc_b_final["texto_memoria"], "Texto original B (recente).")
        # Pendência de B (o único slot) continua intacta -- resolver A sem
        # sucesso real não pode apagar a pendência de um conflito diferente.
        self.assertEqual(
            self.session["pending_confirmations"]["memoria_conflito"]["memoria_id"], "mem-B",
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
