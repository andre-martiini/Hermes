"""Contrato entre o catalogo de tools, os schemas JSON e os executores.

O modo de falha que estes testes cobrem e especifico do MCP: o cliente (Claude,
cliente de voz) le `tools/list` e monta a chamada a partir do `inputSchema`. Se
o schema declara um parametro que o executor nao le — ou se o executor le um que
o schema nao declara — a tool falha em producao com um erro que nao aponta a
causa. A checagem e estatica (AST), sem rede e sem Firestore.
"""

import ast
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

    def test_whatsapp_exige_confirmacao(self):
        """Unica tool com gating no canal MCP, por decisao explicita do dono."""
        resp = self._post({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {
                "name": "schedule_whatsapp_message",
                "arguments": {"contact_number": "+5527999999999", "message": "oi"},
            },
        })
        payload = json.loads(resp.get_data(as_text=True))
        conteudo = json.loads(payload["result"]["content"][0]["text"])
        self.assertEqual(conteudo["status"], "confirmation_required")

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
        self.assertTrue(por_nome["schedule_whatsapp_message"]["needsConfirmation"])
        self.assertFalse(por_nome["criar_acao_no_sistema"]["needsConfirmation"])
        self.assertTrue(por_nome["criar_acao_no_sistema"]["mutates"])
        self.assertFalse(por_nome["consultar_saude"]["mutates"])

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


if __name__ == "__main__":
    unittest.main()
