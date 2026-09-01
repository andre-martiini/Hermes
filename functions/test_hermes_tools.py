"""Contrato entre o catalogo de tools, os schemas JSON e os executores.

O modo de falha que estes testes cobrem e especifico do MCP: o cliente (Claude,
cliente de voz) le `tools/list` e monta a chamada a partir do `inputSchema`. Se
o schema declara um parametro que o executor nao le — ou se o executor le um que
o schema nao declara — a tool falha em producao com um erro que nao aponta a
causa. A checagem e estatica (AST), sem rede e sem Firestore.
"""

import ast
import contextlib
import json
import os
import unittest

from tools import hermes_tools, registry

_HERMES_TOOLS_PATH = os.path.join(os.path.dirname(__file__), "tools", "hermes_tools.py")


def _chaves_lidas_por_funcao() -> dict[str, set[str]]:
    """Mapeia cada funcao de `hermes_tools` -> chaves que ela le de `args`."""
    with open(_HERMES_TOOLS_PATH, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    usos: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        chaves = set()
        for n in ast.walk(node):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "get"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "args"
                and n.args
                and isinstance(n.args[0], ast.Constant)
            ):
                chaves.add(n.args[0].value)
        if chaves:
            usos[node.name] = chaves
    return usos


class TestCatalogoConsistente(unittest.TestCase):
    def test_toda_tool_habilitada_tem_handler(self):
        for nome in registry.list_mcp_enabled_tools():
            self.assertTrue(
                hermes_tools.has_tool(nome),
                f"'{nome}' esta em list_mcp_enabled_tools mas nao tem handler",
            )

    def test_toda_tool_habilitada_tem_schema(self):
        for nome in registry.list_mcp_enabled_tools():
            self.assertTrue(registry.has_schema(nome), f"'{nome}' nao tem schema em tools/schemas/")

    def test_schema_declara_o_proprio_nome(self):
        for nome in registry.list_mcp_enabled_tools():
            self.assertEqual(registry.get_schema(nome).get("name"), nome)

    def test_todo_handler_do_catalogo_esta_habilitado(self):
        """Handler + entrada no catalogo + schema => tem de aparecer em tools/list.

        Sem isto, adicionar um executor e esquecer de expo-lo passa despercebido.
        """
        habilitadas = set(registry.list_mcp_enabled_tools())
        for nome in hermes_tools.list_tools():
            if nome in registry._CATALOG and registry.has_schema(nome):
                self.assertIn(nome, habilitadas, f"'{nome}' tem handler e schema mas nao e exposta")


class TestArgumentosBatemComSchema(unittest.TestCase):
    """Um argumento lido pelo executor mas ausente do schema e sempre None.

    O cliente MCP nao tem como saber que aquele parametro existe, entao o caminho
    de codigo correspondente vira codigo morto silencioso — foi assim que
    `criar_acao_no_sistema` ficou sem expor recorrencia por meses.
    """

    def test_chaves_lidas_estao_no_schema(self):
        usos = _chaves_lidas_por_funcao()
        for nome in registry.list_mcp_enabled_tools():
            handler = hermes_tools._HANDLERS[nome]
            fname = getattr(handler, "__name__", "")
            # Handlers gerados por fabrica (`_via_telegram`, `_strategy`, ...) se
            # chamam "handler" e repassam `args` inteiro — nada a conferir.
            if fname == "handler":
                continue
            chaves = usos.get(fname, set())
            if not chaves:
                continue
            props = set(registry.get_schema(nome).get("parameters", {}).get("properties", {}))
            faltando = sorted(chaves - props)
            self.assertFalse(
                faltando,
                f"'{nome}' le {faltando} de args, mas o schema nao declara esses parametros",
            )


class TestSchemasBemFormados(unittest.TestCase):
    def test_required_existe_em_properties(self):
        for nome in registry.list_mcp_enabled_tools():
            params = registry.get_schema(nome).get("parameters", {})
            props = set(params.get("properties", {}))
            for req in params.get("required", []):
                self.assertIn(req, props, f"'{nome}': '{req}' e obrigatorio mas nao esta em properties")

    def test_arrays_declaram_items(self):
        """Um `array` sem `items` e recusado por parte dos clientes MCP."""
        for nome in registry.list_mcp_enabled_tools():
            props = registry.get_schema(nome).get("parameters", {}).get("properties", {})
            for chave, prop in props.items():
                if prop.get("type") == "array":
                    self.assertIn("items", prop, f"'{nome}.{chave}' e array sem 'items'")

    def test_schemas_sao_json_valido_e_utf8(self):
        pasta = os.path.join(os.path.dirname(__file__), "tools", "schemas")
        for arquivo in os.listdir(pasta):
            if arquivo.endswith(".json"):
                with open(os.path.join(pasta, arquivo), encoding="utf-8") as f:
                    json.load(f)


class TestExecucao(unittest.TestCase):
    def test_tool_desconhecida_levanta(self):
        from tools.tool_context import ToolContext

        with self.assertRaises(hermes_tools.ToolNotAvailable):
            hermes_tools.execute("tool_que_nao_existe", {}, ToolContext())

    def test_calculadora_nao_toca_firestore(self):
        """Tool pura: prova que o ToolContext nao materializa `db` sem necessidade."""
        from tools.tool_context import ToolContext

        ctx = ToolContext()
        res = hermes_tools.execute("calculadora", {"expressao": "2 + 3 * 4"}, ctx)
        self.assertEqual(res["resultado"], "14")
        self.assertIsNone(ctx._db, "ToolContext materializou o cliente Firestore sem precisar")

    def test_calculadora_bloqueia_nome_nao_permitido(self):
        from tools.tool_context import ToolContext

        res = hermes_tools.execute("calculadora", {"expressao": "__import__('os')"}, ToolContext())
        self.assertIn("erro", res)


class TestVoz(unittest.TestCase):
    def test_tools_excluidas_da_voz_nao_aparecem(self):
        for nome in registry._VOICE_EXCLUDED:
            if nome in registry.list_mcp_enabled_tools():
                self.assertFalse(registry.is_voice_enabled(nome))

    def test_voz_e_subconjunto_do_mcp(self):
        for nome in registry.list_mcp_enabled_tools():
            if registry.is_voice_enabled(nome):
                self.assertTrue(registry.is_mcp_enabled(nome))


try:
    import mcp_server
except ImportError:  # firebase_functions so existe no venv de deploy
    mcp_server = None


class _FakeRequest:
    """So o que `mcpServer` realmente le do request."""

    def __init__(self, body=None, method="POST", headers=None, path="/mcp"):
        self.method = method
        self.path = path
        self.headers = headers or {"Authorization": "Bearer fake"}
        self._body = body

    def get_json(self, silent=False):
        return self._body


@unittest.skipIf(mcp_server is None, "firebase_functions indisponivel fora do venv de deploy")
class TestCamadaJsonRpc(unittest.TestCase):
    """Handshake do Streamable HTTP.

    O bug que estes testes travam: responder um erro JSON-RPC a uma notificacao.
    `notifications/initialized` chega sem `id` logo apos o `initialize`, e um
    cliente estrito derruba a conexao ao receber corpo onde nao devia haver.
    """

    def setUp(self):
        import inspect

        self.handler = inspect.unwrap(mcp_server.mcpServer)
        self._auth_original = mcp_server._authenticate
        self._rate_original = mcp_server._check_rate_limit
        mcp_server._authenticate = lambda req: "uid-de-teste"
        mcp_server._check_rate_limit = lambda uid: None

    def tearDown(self):
        mcp_server._authenticate = self._auth_original
        mcp_server._check_rate_limit = self._rate_original

    def _post(self, body):
        return self.handler(_FakeRequest(body))

    def test_notificacao_responde_202_sem_corpo(self):
        resp = self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.get_data(as_text=True), "")

    def test_notificacao_desconhecida_tambem_e_202(self):
        resp = self._post({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}})
        self.assertEqual(resp.status_code, 202)

    def test_initialize_responde_com_id(self):
        resp = self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        payload = json.loads(resp.get_data(as_text=True))
        self.assertEqual(payload["id"], 1)
        self.assertEqual(payload["result"]["serverInfo"]["name"], "hermes-mcp")

    def test_ping_responde_vazio(self):
        resp = self._post({"jsonrpc": "2.0", "id": 7, "method": "ping"})
        payload = json.loads(resp.get_data(as_text=True))
        self.assertEqual(payload["result"], {})

    def test_metodo_desconhecido_com_id_vira_erro(self):
        resp = self._post({"jsonrpc": "2.0", "id": 2, "method": "nao/existe"})
        payload = json.loads(resp.get_data(as_text=True))
        self.assertEqual(payload["error"]["code"], -32601)

    def test_resources_templates_list_vazio(self):
        resp = self._post({"jsonrpc": "2.0", "id": 3, "method": "resources/templates/list"})
        payload = json.loads(resp.get_data(as_text=True))
        self.assertEqual(payload["result"], {"resourceTemplates": []})

    def test_tools_list_publica_o_catalogo(self):
        resp = self._post({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        payload = json.loads(resp.get_data(as_text=True))
        nomes = {t["name"] for t in payload["result"]["tools"]}
        self.assertIn("consultar_historico_acoes", nomes)
        self.assertIn("criar_acao_no_sistema", nomes)
        self.assertEqual(len(nomes), len(registry.list_mcp_enabled_tools()))

    @contextlib.contextmanager
    def _gating(self, tools):
        """Fixa a politica de confirmacao do canal durante o teste.

        Antes isto vinha do Firestore de producao, e o teste virou refem de uma
        configuracao que o dono pode mudar a qualquer hora — como mudou em
        27/08/2026. Pior: com o gating desligado, o teste passava a exercitar o
        caminho de ENVIO de verdade, e o que evitou uma mensagem enfileirada foi
        um argumento obrigatorio faltando na chamada. Sorte, nao desenho.
        """
        anterior = mcp_server._access_cache
        mcp_server._access_cache = {
            "uids": {"*"},
            "confirm_tools": set(tools),
            "expires_at": float("inf"),
        }
        try:
            yield
        finally:
            mcp_server._access_cache = anterior

    def test_gating_do_canal_barra_antes_de_executar(self):
        """Com a tool na politica, a chamada para na confirmacao — nao envia nada."""
        from unittest import mock
        with self._gating({"schedule_whatsapp_message"}), mock.patch.object(
            mcp_server, "_criar_confirmacao", return_value="confirmacao-1"
        ):
            resp = self._post({
                "jsonrpc": "2.0", "id": 5, "method": "tools/call",
                "params": {
                    "name": "schedule_whatsapp_message",
                    "arguments": {"contact_number": "+5527999999999", "message": "oi",
                                  "scheduled_time": "2030-01-01T12:00:00"},
                },
            })
        payload = json.loads(resp.get_data(as_text=True))
        conteudo = json.loads(payload["result"]["content"][0]["text"])
        self.assertEqual(conteudo["status"], "confirmation_required")

    def test_gate_inclui_preview_quando_a_tool_oferece_hook(self):
        from unittest import mock
        with self._gating({"pausar_conversa"}), mock.patch.object(
            mcp_server, "preview_tool", return_value={"status": "aguardando_confirmacao", "mensagem": "texto exato"}
        ) as preview, mock.patch.object(mcp_server, "_criar_confirmacao", return_value="confirmacao-2"):
            resp = self._post({
                "jsonrpc": "2.0", "id": 55, "method": "tools/call",
                "params": {"name": "pausar_conversa", "arguments": {"contato_ou_grupo": "Gabriela", "retomar_em": "amanha_manha"}},
            })
        content = json.loads(json.loads(resp.get_data(as_text=True))["result"]["content"][0]["text"])
        self.assertEqual(content["status"], "aguardando_confirmacao")
        self.assertEqual(content["preview"]["mensagem"], "texto exato")
        self.assertEqual(content["confirmation_id"], "confirmacao-2")
        preview.assert_called_once()

    def test_confirmada_reutiliza_argumentos_e_previa_persistidos(self):
        from datetime import datetime, timezone
        from unittest import mock
        approved = {
            "arguments": {"contato_ou_grupo": "Gabriela", "retomar_em": "amanha_manha"},
            "preview": {"mensagem": "texto aprovado"},
            "created_at": datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        }
        with mock.patch.object(mcp_server, "_ler_confirmacao", return_value=approved) as read, \
             mock.patch.object(mcp_server, "execute_tool", return_value={"ok": True}) as execute:
            resp = self._post({
                "jsonrpc": "2.0", "id": 56, "method": "tools/call",
                "params": {"name": "pausar_conversa", "arguments": {
                    "contato_ou_grupo": "Gabriela", "retomar_em": "amanha_manha",
                    "_confirmed": True, "_confirmation_id": "confirmacao-2",
                }},
            })
        self.assertFalse(json.loads(resp.get_data(as_text=True))["result"]["isError"])
        self.assertEqual(read.call_args.args[2], {"contato_ou_grupo": "Gabriela", "retomar_em": "amanha_manha"})
        self.assertEqual(execute.call_args.args[1], approved["arguments"])

    def test_politica_vazia_nao_desliga_envios_obrigatorios(self):
        """Configuração viva pode adicionar gates, nunca remover envios externos."""
        with self._gating(set()):
            self.assertTrue(mcp_server._exige_confirmacao("schedule_whatsapp_message"))
            self.assertTrue(mcp_server._exige_confirmacao("pausar_conversa"))
        with self._gating({"schedule_whatsapp_message"}):
            self.assertTrue(mcp_server._exige_confirmacao("schedule_whatsapp_message"))

    def test_demais_tools_mutantes_nao_pedem_dupla_chamada(self):
        """`criar_acao_no_sistema` grava, mas o gating do canal esta desligado.

        O humano no circuito e o pedido de permissao do cliente MCP. Se este
        teste passar a falhar, alguem religou o gating — o que e legitimo, mas
        deve ser deliberado.
        """
        self.assertFalse(mcp_server._exige_confirmacao("criar_acao_no_sistema"))
        self.assertTrue(registry.needs_confirmation("criar_acao_no_sistema"))

    def test_meta_separa_gating_de_mutacao(self):
        resp = self._post({"jsonrpc": "2.0", "id": 8, "method": "tools/list"})
        payload = json.loads(resp.get_data(as_text=True))
        por_nome = {t["name"]: t["_meta"] for t in payload["result"]["tools"]}
        # `needsConfirmation` reflete a politica viva do canal, que o dono muda
        # sem deploy; o que este teste trava e a distincao entre gating e mutacao,
        # nao o valor de uma configuracao.
        self.assertFalse(por_nome["criar_acao_no_sistema"]["needsConfirmation"])
        self.assertTrue(por_nome["criar_acao_no_sistema"]["mutates"])
        self.assertFalse(por_nome["consultar_saude"]["mutates"])
        # Envio de WhatsApp continua marcado como mutante independente do gating —
        # e o que faz o cliente pedir permissao mesmo com a politica vazia.
        self.assertTrue(por_nome["schedule_whatsapp_message"]["mutates"])

    def test_tool_pura_executa(self):
        resp = self._post({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "calculadora", "arguments": {"expressao": "7*6"}},
        })
        payload = json.loads(resp.get_data(as_text=True))
        self.assertFalse(payload["result"]["isError"])
        self.assertIn("42", payload["result"]["content"][0]["text"])

    def test_body_nao_objeto_e_recusado(self):
        resp = self._post([{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])
        payload = json.loads(resp.get_data(as_text=True))
        self.assertEqual(payload["error"]["code"], -32600)

    def test_delete_encerra_sessao_sem_erro(self):
        resp = self.handler(_FakeRequest(method="DELETE"))
        self.assertEqual(resp.status_code, 204)


class TestSinalDeIntencao(unittest.TestCase):
    """`ai_profile.historico_deduzido` entra no prompt de toda conversa seguinte.

    Por isso ele so pode receber o que o usuario de fato pediu. Encher de passo
    intermediario do agente degrada o contexto em vez de enriquecer — e degrada
    em silencio, porque nada falha.
    """

    def setUp(self):
        import mcp_signals

        self.sinal = mcp_signals.sinal_de_intencao

    def test_argumento_do_usuario_vira_frase(self):
        self.assertEqual(
            self.sinal("consultar_historico_acoes", {"query": "PDP capacitacao"}),
            "buscou acoes: PDP capacitacao")
        self.assertEqual(
            self.sinal("criar_acao_no_sistema", {"titulo": "Enviar declaracao"}),
            "criou acao: Enviar declaracao")

    def test_tool_sem_texto_livre_ainda_diz_o_assunto(self):
        self.assertEqual(self.sinal("consultar_agenda", {}), "consultou a agenda")

    def test_passo_intermediario_do_agente_nao_vira_sinal(self):
        for tool, args in (("calculadora", {"expressao": "2+2"}),
                           ("consultar_job", {"job_id": "x"}),
                           ("obter_contexto_tela", {"task_id": "t1"})):
            self.assertIsNone(self.sinal(tool, args), tool)

    def test_consultar_job_nunca_gera_sinal(self):
        """Polling repetido inundaria o historico com a mesma entrada."""
        self.assertIsNone(self.sinal("consultar_job", {"job_id": "abc"}))

    def test_argumento_vazio_nao_gera_sinal(self):
        self.assertIsNone(self.sinal("consultar_historico_acoes", {"query": "   "}))
        self.assertIsNone(self.sinal("criar_acao_no_sistema", {}))

    def test_texto_longo_e_truncado(self):
        texto = self.sinal("registrar_no_diario", {"nota": "x" * 500})
        self.assertLessEqual(len(texto), 220)
        self.assertTrue(texto.endswith("..."))

    def test_toda_tool_com_sinal_existe_no_catalogo(self):
        import mcp_signals

        conhecidas = set(registry._CATALOG)
        for tool in set(mcp_signals._INTENCAO_POR_TOOL) | set(mcp_signals._INTENCAO_SEM_ARGUMENTO):
            self.assertIn(tool, conhecidas, f"'{tool}' saiu do catalogo e o sinal ficou orfao")


@unittest.skipIf(mcp_server is None, "firebase_functions indisponivel fora do venv de deploy")
class TestToolsLongas(unittest.TestCase):
    """Tools acima de um minuto nao podem rodar dentro do request.

    Pela URL do Hosting — a que Cowork, Desktop e celular usam — o corte e 60s, e
    o cliente recebe erro de gateway sem explicacao.
    """

    def setUp(self):
        import inspect

        self.handler = inspect.unwrap(mcp_server.mcpServer)
        self._auth = mcp_server._authenticate
        self._rate = mcp_server._check_rate_limit
        mcp_server._authenticate = lambda req: "uid-de-teste"
        mcp_server._check_rate_limit = lambda uid: None

    def tearDown(self):
        mcp_server._authenticate = self._auth
        mcp_server._check_rate_limit = self._rate

    def test_sao_um_subconjunto_das_async_do_registry(self):
        self.assertTrue(mcp_server._TOOLS_LONGAS <= registry._ASYNC_TOOLS)

    def test_tem_contraparte_para_buscar_o_resultado(self):
        self.assertIn("consultar_job", registry.list_mcp_enabled_tools())

    def test_devolve_job_id_em_vez_de_executar(self):
        from unittest import mock

        with mock.patch("mcp_jobs.criar_job", return_value="mcpjob-teste") as criar:
            resp = self.handler(_FakeRequest({
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "gerar_relatorio",
                           "arguments": {"titulo": "Relatorio X", "tipo": "executivo"}},
            }))
        payload = json.loads(resp.get_data(as_text=True))
        conteudo = json.loads(payload["result"]["content"][0]["text"])
        self.assertEqual(conteudo["status"], "processing")
        self.assertEqual(conteudo["job_id"], "mcpjob-teste")
        self.assertFalse(payload["result"]["isError"])
        criar.assert_called_once()

    def test_tool_curta_continua_sincrona(self):
        resp = self.handler(_FakeRequest({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "calculadora", "arguments": {"expressao": "3*3"}},
        }))
        payload = json.loads(resp.get_data(as_text=True))
        self.assertIn("9", payload["result"]["content"][0]["text"])


@unittest.skipIf(mcp_server is None, "firebase_functions indisponivel fora do venv de deploy")
class TestInstrucoesDoServidor(unittest.TestCase):
    """`instructions` do initialize e o unico canal para o que a lista de tools nao diz.

    O ponto critico e a memoria: no copiloto web salvar um fato duravel era
    subproduto da conversa, porque o system prompt mandava. Num cliente MCP so
    acontece se algo disser para acontecer.
    """

    def setUp(self):
        self.init = mcp_server._handle_initialize({})

    def test_prompts_anunciado_nas_capabilities(self):
        self.assertIn("prompts", self.init["capabilities"])

    def test_instrui_a_gravar_memoria(self):
        self.assertIn("salvar_memoria_global", self.init["instructions"])

    def test_instrui_o_ponto_de_partida_e_o_polling(self):
        for termo in ("obter_estado_atual", "consultar_job", "editar_acao"):
            self.assertIn(termo, self.init["instructions"], termo)

    def test_prompts_get_sem_nome_e_erro_de_parametro(self):
        with self.assertRaises(mcp_server.McpError) as ctx:
            mcp_server._handle_prompts_get({})
        self.assertEqual(ctx.exception.code, -32602)


class TestEscritaDireta(unittest.TestCase):
    """As `preparar_*` existem pelo card da UI web; o canal MCP nao tem card."""

    DIRETAS = ("editar_acao", "editar_acoes_em_lote", "reagendar_acoes_em_lote")

    def test_expostas(self):
        habilitadas = set(registry.list_mcp_enabled_tools())
        for nome in self.DIRETAS:
            self.assertIn(nome, habilitadas, nome)

    def test_marcadas_como_mutantes(self):
        """Gravam sem passo intermediario — o cliente precisa saber disso."""
        for nome in self.DIRETAS:
            self.assertTrue(registry.needs_confirmation(nome), nome)

    def test_preparar_continua_existindo_para_a_web(self):
        habilitadas = set(registry.list_mcp_enabled_tools())
        for nome in ("preparar_edicao_acao", "preparar_edicao_em_lote",
                     "preparar_reagendamento_em_lote"):
            self.assertIn(nome, habilitadas, nome)

    def test_estado_atual_e_somente_leitura(self):
        self.assertIn("obter_estado_atual", registry.list_mcp_enabled_tools())
        self.assertFalse(registry.needs_confirmation("obter_estado_atual"))


class TestRetornoNaoMenteSobreOEfeito(unittest.TestCase):
    """Os três bugs de 28/08/2026 tinham a mesma forma: retorno sem efeito.

    `editar_acao` respondia `{"erro": ""}` e não gravava nada. String vazia é
    lida como "sem erro", então quem chamou relatou ao dono que a edição tinha
    passado. Um erro sem mensagem é pior que uma exceção.
    """

    def test_erro_nunca_sai_vazio(self):
        class SemMensagem(Exception):
            def __str__(self):
                return ""

        msg = hermes_tools._mensagem_de_erro(SemMensagem(), "confirmarEdicaoAcao")
        self.assertTrue(msg.strip())
        self.assertIn("NAO foi aplicada", msg)
        self.assertIn("confirmarEdicaoAcao", msg)

    def test_httpserror_tem_a_mensagem_em_message(self):
        """`HttpsError` guarda o texto em `.message`; `str()` volta vazio."""
        class FakeHttpsError(Exception):
            def __init__(self):
                super().__init__()
                self.message = "Tarefa não encontrada."

            def __str__(self):
                return ""

        msg = hermes_tools._mensagem_de_erro(FakeHttpsError())
        self.assertIn("Tarefa não encontrada.", msg)

    def test_editar_acao_sem_campo_algum_recusa_com_orientacao(self):
        """Chamada sem `alteracoes` e sem campo solto não pode virar erro vazio."""
        r = hermes_tools.editar_acao(_CtxVazio(), {"task_id": "abc"})
        self.assertFalse(r["aplicado"])
        self.assertIn("alteracoes", r["erro"])
        self.assertIn("data_limite", r["erro"])

    def test_campo_solto_vira_alteracao(self):
        """`editar_acao(task_id=..., data_limite=...)` é a leitura natural do nome
        da tool, e era aceita em silêncio sem alterar nada."""
        capturado = {}

        def _falso(nome, mapear=None):
            def handler(ctx, args):
                capturado.update(args)
                return {"success": True}
            return handler

        original = hermes_tools._via_callable
        hermes_tools._via_callable = _falso
        try:
            r = hermes_tools.editar_acao(_CtxVazio(), {
                "task_id": "abc", "data_limite": "2026-09-01", "notas": "nota"})
        finally:
            hermes_tools._via_callable = original

        self.assertEqual(capturado["alteracoes"],
                         {"data_limite": "2026-09-01", "notas": "nota"})
        self.assertEqual(r["campos_alterados"], ["data_limite", "notas"])

    def test_campo_desconhecido_nao_entra(self):
        """Só os campos editáveis viram alteração — o resto é ruído da chamada."""
        capturado = {}

        def _falso(nome, mapear=None):
            def handler(ctx, args):
                capturado.update(args)
                return {"success": True}
            return handler

        original = hermes_tools._via_callable
        hermes_tools._via_callable = _falso
        try:
            hermes_tools.editar_acao(_CtxVazio(), {
                "task_id": "abc", "data_limite": "2026-09-01", "campo_inventado": "x"})
        finally:
            hermes_tools._via_callable = original
        self.assertEqual(capturado["alteracoes"], {"data_limite": "2026-09-01"})


class TestOQueSeAnunciaEditavelEDeFatoGravado(unittest.TestCase):
    """`_CAMPOS_EDITAVEIS` promete; a whitelist da callable e quem cumpre.

    `editar_acao` monta as alteracoes a partir de `_CAMPOS_EDITAVEIS` e repassa
    para `confirmarEdicaoAcao`, que so grava o que estiver na whitelist `_ALLOWED`
    dela. Campo que esta numa lista e nao na outra e descartado sem erro — e
    quando ele e a unica alteracao pedida, a chamada ainda responde "Nenhum campo
    valido", que aponta para o lugar errado.

    Ja aconteceu com `estrategia_objetivo_id` e com `projeto`: os dois anunciados
    ao modelo, nenhum dos dois gravavel. A checagem e estatica porque `main.py`
    nao importa fora do venv de deploy — e a divergencia e textual de qualquer
    forma, entre dois literais.
    """

    @staticmethod
    def _whitelists_do_main() -> dict[str, set[str]]:
        """Cada `_ALLOWED = {...}` de main.py, indexado pela funcao que o contem."""
        caminho = os.path.join(os.path.dirname(__file__), "main.py")
        with open(caminho, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        achados: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for n in ast.walk(node):
                if (isinstance(n, ast.Assign)
                        and len(n.targets) == 1
                        and isinstance(n.targets[0], ast.Name)
                        and n.targets[0].id == "_ALLOWED"
                        and isinstance(n.value, ast.Set)):
                    campos = {e.value for e in n.value.elts if isinstance(e, ast.Constant)}
                    achados.setdefault(node.name, set()).update(campos)
        return achados

    def test_as_duas_whitelists_do_main_foram_encontradas(self):
        """Se o literal mudar de forma, o teste avisa em vez de passar vazio."""
        achados = self._whitelists_do_main()
        self.assertIn("confirmarEdicaoAcao", achados)
        self.assertIn("confirmarEdicaoEmLote", achados)

    def test_todo_campo_anunciado_editavel_e_gravavel(self):
        achados = self._whitelists_do_main()
        for funcao in ("confirmarEdicaoAcao", "confirmarEdicaoEmLote"):
            faltando = set(hermes_tools._CAMPOS_EDITAVEIS) - achados[funcao]
            self.assertEqual(
                faltando, set(),
                f"{funcao} descarta em silencio campos que _CAMPOS_EDITAVEIS "
                f"anuncia como editaveis: {sorted(faltando)}")

    def test_editar_acao_aceita_o_vinculo_estrategico(self):
        """O segundo passo de uma elevacao aceita depende deste campo especifico."""
        self.assertIn("estrategia_objetivo_id", hermes_tools._CAMPOS_EDITAVEIS)
        for campos in self._whitelists_do_main().values():
            self.assertIn("estrategia_objetivo_id", campos)


class _CtxVazio:
    user_uid = "uid"
    session_id = None
    task_id = None
    canal = "mcp"
    db = None


if __name__ == "__main__":
    unittest.main()
