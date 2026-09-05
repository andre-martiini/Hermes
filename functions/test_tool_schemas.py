"""Garante que a requisição montada para o Gemini no fluxo do Telegram é válida.

O sintoma que estes testes cobrem é o `400 INVALID_ARGUMENT — "Request contains
an invalid argument."`, que a API devolve sem apontar o campo recusado. Nenhum
teste aqui usa rede: eles inspecionam o payload antes do envio.
"""
import ast
import inspect
import json
import unittest
from unittest import mock

from google.genai import types

import hermes_core_logic as core


class _FakeApiClient:
    vertexai = False


class _FakeClient:
    """Suficiente para `FunctionDeclaration.from_callable`, que só lê `vertexai`."""
    vertexai = False
    _api_client = _FakeApiClient()


def _stub_das_ferramentas_do_telegram():
    """Recria as ferramentas do Telegram como funções de topo.

    Elas são definidas dentro de `_process_telegram_message` (closures sobre `db`
    e sobre a sessão), então o teste reconstrói stubs com a MESMA assinatura e o
    MESMO docstring a partir da AST — que é exatamente o que o SDK lê para gerar
    o schema.
    """
    fonte = inspect.getsource(core)
    arvore = ast.parse(fonte)
    nomes = _nomes_das_ferramentas(arvore)
    stubs = {}
    for no in ast.walk(arvore):
        if not isinstance(no, ast.FunctionDef) or no.name not in nomes or no.name in stubs:
            continue
        corpo = [
            ast.Expr(value=ast.Constant(value=ast.get_docstring(no) or "")),
            ast.Return(value=ast.Constant(value="ok")),
        ]
        stub = ast.FunctionDef(
            name=no.name,
            args=no.args,
            body=corpo,
            decorator_list=[],
            returns=None,
            type_params=[],
        )
        modulo = ast.Module(body=[stub], type_ignores=[])
        ast.fix_missing_locations(modulo)
        escopo = {}
        exec(compile(modulo, "<stub>", "exec"), escopo)  # noqa: S102 - stub controlado
        stubs[no.name] = escopo[no.name]
    faltando = [n for n in nomes if n not in stubs]
    assert not faltando, f"ferramentas não encontradas no módulo: {faltando}"
    return [stubs[n] for n in nomes]


def _nomes_das_ferramentas(arvore):
    """Lê a `tools_list` declarada em hermes_core_logic (fonte da verdade)."""
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign) and any(
            isinstance(alvo, ast.Name) and alvo.id == "tools_list" for alvo in no.targets
        ):
            if isinstance(no.value, ast.List):
                return [e.id for e in no.value.elts if isinstance(e, ast.Name)]
    raise AssertionError("tools_list não encontrada em hermes_core_logic")


def _percorre(schema, caminho="parameters"):
    if not isinstance(schema, dict):
        return
    yield caminho, schema
    for chave, valor in (schema.get("properties") or {}).items():
        yield from _percorre(valor, f"{caminho}.{chave}")
    if isinstance(schema.get("items"), dict):
        yield from _percorre(schema["items"], f"{caminho}[]")
    for chave in ("any_of", "anyOf"):
        for i, valor in enumerate(schema.get(chave) or []):
            yield from _percorre(valor, f"{caminho}|{chave}{i}")


class TestToolSchemas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ferramentas = _stub_das_ferramentas_do_telegram()
        cls.tools = core._build_gemini_tools(_FakeClient(), types, cls.ferramentas)
        assert len(cls.tools) == 1 and getattr(cls.tools[0], "function_declarations", None), (
            "a conversão caiu no fallback de callables — o SDK mudou de API"
        )
        cls.declaracoes = cls.tools[0].function_declarations

    def _schemas(self):
        for decl in self.declaracoes:
            if decl.parameters is None:
                continue
            dados = decl.parameters.model_dump(mode="json", exclude_none=True)
            for caminho, schema in _percorre(dados):
                yield decl.name, caminho, schema

    def test_todas_as_ferramentas_declaradas(self):
        self.assertEqual(len(self.declaracoes), len(self.ferramentas))
        self.assertIn("criar_acao_no_sistema", [d.name for d in self.declaracoes])

    def test_secretario_presente_no_payload_gemini_e_no_mcp(self):
        import mcp_server

        nomes = {d.name for d in self.declaracoes}
        with mock.patch.object(mcp_server, "_access_config", return_value={"confirm_tools": set()}):
            mcp = {t["name"]: t for t in mcp_server._handle_tools_list()["tools"]}
        for nome in ("ativar_modo_secretario", "desativar_modo_secretario", "consultar_status_modo_secretario"):
            self.assertIn(nome, nomes)
            self.assertIn(nome, mcp)
            self.assertFalse(mcp[nome]["_meta"]["needsConfirmation"])

    def test_secretario_aceita_contatos_e_duracao_opcionais(self):
        decl = next(d for d in self.declaracoes if d.name == "ativar_modo_secretario")
        self.assertFalse(decl.parameters.required)
        self.assertEqual(decl.parameters.properties["contatos"].type, types.Type.ARRAY)
        self.assertEqual(decl.parameters.properties["contatos"].items.type, types.Type.STRING)
        self.assertEqual(decl.parameters.properties["duracao_horas"].type, types.Type.NUMBER)

    def test_sem_object_sem_properties(self):
        """OBJECT sem `properties` é o schema gerado para um parâmetro `dict`."""
        for nome, caminho, schema in self._schemas():
            if str(schema.get("type", "")).upper().endswith("OBJECT"):
                self.assertTrue(
                    schema.get("properties"),
                    f"{nome}: {caminho} é OBJECT sem properties",
                )

    def test_sem_campo_default(self):
        for nome, caminho, schema in self._schemas():
            self.assertNotIn("default", schema, f"{nome}: {caminho} carrega 'default'")

    def test_required_reflete_a_assinatura(self):
        por_nome = {getattr(f, "__name__", ""): f for f in self.ferramentas}
        for decl in self.declaracoes:
            if decl.parameters is None:
                continue
            obrigatorios = list(decl.parameters.required or [])
            sig = inspect.signature(por_nome[decl.name])
            for nome_param in obrigatorios:
                self.assertIs(
                    sig.parameters[nome_param].default,
                    inspect.Parameter.empty,
                    f"{decl.name}: '{nome_param}' tem valor padrão e não pode ser obrigatório",
                )

    def test_edicao_em_lote_descreve_os_campos(self):
        decl = next(d for d in self.declaracoes if d.name == "editar_acoes_em_lote")
        dados = decl.parameters.model_dump(mode="json", exclude_none=True)
        item = dados["properties"]["itens"]["items"]
        self.assertIn("task_id", item["properties"])
        self.assertIn("data_limite", item["properties"]["alteracoes"]["properties"])
        self.assertEqual(dados.get("required"), ["itens"])


class TestSecretarioTelegramExecucao(unittest.TestCase):
    """Executa os corpos reais das closures, isolando apenas o transporte Telegram.

    O teste de schemas acima lê a lista efetiva de ferramentas enviada ao SDK;
    aqui verificamos que as mesmas closures chegam ao handler e ao banco.
    """

    def setUp(self):
        from test_secretario_whatsapp import _MockDb

        self.db = _MockDb()
        arvore = ast.parse(inspect.getsource(core._process_telegram_message))
        nomes = {"ativar_modo_secretario", "desativar_modo_secretario", "consultar_status_modo_secretario"}
        nos = [n for n in arvore.body[0].body if isinstance(n, ast.FunctionDef) and n.name in nomes]
        self.assertEqual({n.name for n in nos}, nomes)
        modulo = ast.Module(body=nos, type_ignores=[])
        self.tools = {"db": self.db, "json": json}
        exec(compile(ast.fix_missing_locations(modulo), "<closures-secretario-reais>", "exec"), self.tools)

    def test_ativar_30_minutos_consultar_e_desativar_numero_nao_cadastrado(self):
        from datetime import datetime, timedelta, timezone
        agora = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)
        with mock.patch("secretario_whatsapp._agora_sp", return_value=agora), mock.patch(
            "tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": False}
        ):
            ativado = json.loads(self.tools["ativar_modo_secretario"](["2799826-0015"], 0.5))
            self.assertTrue(ativado["success"])
            self.assertEqual(ativado["chats_allowlist"], ["27998260015@c.us"])
            status = json.loads(self.tools["consultar_status_modo_secretario"]())
            self.assertTrue(status["enabled"])
            self.assertEqual(datetime.fromisoformat(status["desativa_em"]), agora + timedelta(minutes=30))
            with mock.patch("secretario_whatsapp._agora_sp", return_value=agora + timedelta(minutes=31)):
                self.assertFalse(json.loads(self.tools["consultar_status_modo_secretario"]())["enabled"])
            self.assertFalse(json.loads(self.tools["desativar_modo_secretario"]())["enabled"])
            self.assertFalse(json.loads(self.tools["consultar_status_modo_secretario"]())["enabled"])

    def test_ativar_sem_argumentos_preserva_allowlist(self):
        self.db.collection("system").document("settings").set({
            "whatsapp_secretario": {"enabled": False, "chats_allowlist": ["teste@c.us"]},
        })
        result = json.loads(self.tools["ativar_modo_secretario"]())
        self.assertEqual(result["chats_allowlist"], ["teste@c.us"])
        self.assertIsNone(result["desativa_em"])

    def test_falha_do_handler_nao_vira_sucesso(self):
        with mock.patch("tools.hermes_tools.execute", side_effect=RuntimeError("falha de persistência")):
            with self.assertRaisesRegex(RuntimeError, "falha de persistência"):
                self.tools["ativar_modo_secretario"]()

    def test_roundtrip_gemini_recebe_tools_e_executa_na_ordem(self):
        ferramentas = [self.tools.get(f.__name__, f) for f in _stub_das_ferramentas_do_telegram()]
        client = _FakeClient()
        client.chats = mock.Mock()
        chamadas = types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=[
            types.Part(function_call=types.FunctionCall(name="ativar_modo_secretario", args={"contatos": [], "duracao_horas": 0.5})),
            types.Part(function_call=types.FunctionCall(name="consultar_status_modo_secretario", args={})),
            types.Part(function_call=types.FunctionCall(name="desativar_modo_secretario", args={})),
        ]))])
        final = types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=[types.Part(text="Concluído")]))])
        with mock.patch("google.genai.Client", return_value=client), mock.patch.object(
            core, "send_message_logged", side_effect=[chamadas, final]
        ) as send:
            resposta = core._run_gemini_turn(
                db=self.db, gemini_key="fake", system_instruction="teste", history=[],
                user_message_parts=[types.Part(text="Teste do secretário")],
                tools_list=ferramentas, function_map={f.__name__: f for f in ferramentas},
            )
        self.assertEqual(resposta, "Concluído")
        config = client.chats.create.call_args.kwargs["config"]
        self.assertIn("ativar_modo_secretario", {d.name for d in config.tools[0].function_declarations})
        retornos = send.call_args_list[1].args[1]
        estados = [json.loads(p.function_response.response["result"])["enabled"] for p in retornos]
        self.assertEqual(estados, [True, True, False])


class TestThinkingConfig(unittest.TestCase):
    def test_familia_3_usa_thinking_level(self):
        cfg = core._thinking_config_for_model(types, "gemini-3.5-flash-lite")
        self.assertIsNotNone(cfg)
        self.assertEqual(str(cfg.thinking_level).upper().split(".")[-1], "MINIMAL")
        self.assertIsNone(cfg.thinking_budget)

    def test_familia_2_usa_thinking_budget(self):
        cfg = core._thinking_config_for_model(types, "gemini-2.5-flash-lite")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.thinking_budget, 0)
        self.assertIsNone(cfg.thinking_level)


class TestSanitizacaoDeSchema(unittest.TestCase):
    def test_object_vazio_vira_string(self):
        saneado = core._sanitize_tool_schema({"type": "OBJECT", "description": "livre"})
        self.assertEqual(saneado["type"], "STRING")
        self.assertIn("JSON", saneado["description"])

    def test_object_com_properties_preservado(self):
        original = {"type": "OBJECT", "properties": {"a": {"type": "STRING", "default": "x"}}}
        saneado = core._sanitize_tool_schema(original)
        self.assertEqual(saneado["type"], "OBJECT")
        self.assertNotIn("default", saneado["properties"]["a"])

    def test_erro_400_reconhecido(self):
        self.assertTrue(core._is_invalid_argument_error(Exception(
            "400 INVALID_ARGUMENT. {'error': {'code': 400, 'status': 'INVALID_ARGUMENT'}}"
        )))
        self.assertFalse(core._is_invalid_argument_error(Exception("503 UNAVAILABLE")))


if __name__ == "__main__":
    unittest.main()
