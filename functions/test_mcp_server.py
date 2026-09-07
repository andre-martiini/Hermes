"""Testes de `mcp_server.py` — dispatch JSON-RPC do canal MCP do Hermes.

Não existia arquivo de teste chamando estes handlers DIRETAMENTE antes desta
correção (confirmado por busca no repositório: `_handle_tools_call`/
`_handle_tools_list`/`_handle_server_discover` não eram importados por
nenhum `test_*.py`) — mas rodar a suíte completa revelou que ISSO NÃO
significava zero cobertura: `test_hermes_tools.py::TestCamadaJsonRpc` já
exercitava boa parte deste dispatch de ponta a ponta, via `mcpServer()` real
(POST simulado), incluindo dois testes (`test_ping_responde_vazio`,
`test_resources_templates_list_vazio`) que comparavam o `result` inteiro por
igualdade exata — e que esta correção QUEBROU de propósito (o contrato mudou
para incluir `resultType`; os dois foram atualizados para refletir o
contrato novo, não revertidos). Vale a pena ler aquela classe também para o
quadro completo do que já era coberto. O escopo deste arquivo é
deliberadamente estreito: cobre o achado do Codex na PR #193
(07/09/2026) — `_SUPPORTED_PROTOCOL_VERSIONS` passou a incluir "2026-07-28"
(para o `server/discover` do ChatGPT), mas nenhuma resposta de `tools/call`
nem de `tools/list` levava o campo `resultType`, que a revisão 2026-07-28 do
MCP exige em todo resultado "complete". Um cliente 2026-nativo que negocia
essa versão passa a rejeitar QUALQUER resposta dessas duas chamadas por falha
de validação de schema — reproduzido ao vivo pelo dono (André) em 07/09/2026:
chamou `obter_estado_atual` e `consultar_dados_cadastrais` (esta última citada
no relato inicial como "funcionando normalmente") e as duas falharam
identicamente, confirmando que a lacuna era uniforme em todo o dispatch de
`tools/call`, não uma migração parcial de handlers específicos como a
hipótese inicial supunha.

A revisão adversarial desta correção apontou que a mesma lacuna valia para
`resources/list`, `resources/read` e `prompts/list`/`prompts/get` (mesmo
raciocínio: qualquer resultado "complete" deste dispatch precisa do campo,
não só `tools/call`/`tools/list`) — cobertos também, ver
`TestOutrosMetodosResultType`.

Não cobre o resto do dispatch (`initialize` — fica de fora por decisão
deliberada, ver comentário de escopo no topo de `mcp_server.py` — `ping` e
`resources/templates/list`, autenticação, rate limit, `_TOOLS_LONGAS`/
`mcp_jobs` de verdade) — fica para quando esse resto também precisar de rede
de segurança própria.
"""

import unittest
from unittest.mock import MagicMock, patch

import mcp_server
from tools.tool_context import ToolContext


def _ctx(uid: str = "dono-uid") -> ToolContext:
    return ToolContext(user_uid=uid, canal="mcp", _db=MagicMock())


class TestTextResultContract(unittest.TestCase):
    """`_text_result` é o construtor de resposta usado por 10 dos 11 pontos de
    retorno de `_handle_tools_call` (confirmado via AST — `ast.walk` sobre o
    corpo da função conta 11 `Return` ao todo). O 11º — sucesso/erro da
    execução normal, no fim da função — monta o dict na mão e é coberto
    separadamente abaixo, porque é justamente o ramo que reproduziu o bug
    relatado em 07/09/2026. Testar `_text_result` isoladamente é a rede de
    segurança de mais alta alavancagem contra uma regressão futura: qualquer
    mudança que tire `resultType` daqui quebra a maior parte da superfície de
    uma vez."""

    def test_sempre_inclui_resulttype_complete(self):
        for payload, is_error in [
            ({"ok": True}, False),
            ({"erro": "algo deu errado"}, True),
            ({}, False),
        ]:
            with self.subTest(payload=payload, is_error=is_error):
                r = mcp_server._text_result(payload, is_error=is_error)
                self.assertEqual(r["resultType"], "complete")
                self.assertEqual(r["isError"], is_error)

    def test_nao_altera_o_formato_de_content_existente(self):
        # Regressão: o campo novo não pode vir às custas do formato que os
        # clientes MCP já tratam (content[0].type == "text" com o payload
        # serializado em JSON dentro de .text).
        r = mcp_server._text_result({"a": 1}, is_error=False)
        self.assertEqual(r["content"][0]["type"], "text")
        self.assertIn('"a": 1', r["content"][0]["text"])


class TestHandleToolsCallResultType(unittest.TestCase):
    """Exercita `_handle_tools_call` de ponta a ponta (não só `_text_result`
    isolado) para os ramos representativos do dispatch real, incluindo o
    único que NÃO passa por `_text_result`."""

    def setUp(self):
        patcher = patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_execucao_normal_com_sucesso_inclui_resulttype(self):
        # Este é o ramo exato que faltava: o retorno de sucesso/erro da
        # execução comum monta {"content", "isError"} na mão, sem passar por
        # `_text_result` — é o que o dono reproduziu ao vivo em 07/09/2026.
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool", return_value={"resultado": "ok"}), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call({"name": "obter_estado_atual", "arguments": {}}, ctx=_ctx())
        self.assertEqual(r["resultType"], "complete")
        self.assertFalse(r["isError"])

    def test_execucao_com_excecao_inclui_resulttype(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool", side_effect=RuntimeError("boom")), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call({"name": "consultar_dados_cadastrais", "arguments": {}}, ctx=_ctx())
        self.assertEqual(r["resultType"], "complete")
        self.assertTrue(r["isError"])

    def test_confirmar_acao_inclui_resulttype(self):
        with patch.object(mcp_server, "_executar_confirmacao", return_value={"status": "ok"}), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call(
                {"name": "confirmar_acao", "arguments": {"confirmation_id": "c1"}}, ctx=_ctx()
            )
        self.assertEqual(r["resultType"], "complete")

    def test_tool_exigindo_confirmacao_primeira_chamada_inclui_resulttype(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(mcp_server, "preview_tool", return_value={"resumo": "prevista"}), \
             patch.object(mcp_server, "_criar_confirmacao", return_value="conf-1"), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call({"name": "algo_sensivel", "arguments": {}}, ctx=_ctx())
        self.assertEqual(r["resultType"], "complete")
        self.assertFalse(r["isError"])

    def test_preview_com_erro_inclui_resulttype(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(mcp_server, "preview_tool", side_effect=ValueError("destino invalido")), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call({"name": "algo_sensivel", "arguments": {}}, ctx=_ctx())
        self.assertEqual(r["resultType"], "complete")
        self.assertTrue(r["isError"])

    def test_tool_longa_inclui_resulttype(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "_TOOLS_LONGAS", {"tool_demorada"}), \
             patch("mcp_jobs.criar_job", return_value="job-1"), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call({"name": "tool_demorada", "arguments": {}}, ctx=_ctx())
        self.assertEqual(r["resultType"], "complete")
        self.assertFalse(r["isError"])
        self.assertEqual(r["content"][0]["text"].count("job-1"), 1)


class TestHandleToolsListResultType(unittest.TestCase):
    def test_inclui_resulttype_ttlms_cachescope(self):
        r = mcp_server._handle_tools_list()
        self.assertEqual(r["resultType"], "complete")
        self.assertIsInstance(r["ttlMs"], int)
        self.assertGreater(r["ttlMs"], 0)
        self.assertEqual(r["cacheScope"], "public")
        self.assertTrue(r["tools"])  # catálogo real não deveria vir vazio

    def test_ttlms_e_cachescope_em_paridade_com_server_discover(self):
        # As duas respostas "catálogo" (tools/list e server/discover) usam o
        # mesmo raciocínio de cache — não há razão para divergirem, e uma
        # divergência introduzida por acidente seria difícil de notar sem
        # este teste comparando as duas diretamente.
        tools_list = mcp_server._handle_tools_list()
        discover = mcp_server._handle_server_discover({})
        self.assertEqual(tools_list["ttlMs"], discover["ttlMs"])
        self.assertEqual(tools_list["cacheScope"], discover["cacheScope"])
        self.assertEqual(tools_list["resultType"], discover["resultType"])


class TestOutrosMetodosResultType(unittest.TestCase):
    """Achado da revisão adversarial desta correção: a lacuna do Codex na PR
    #193 falava só de `tools/call`/`tools/list`, mas o mesmo raciocínio (uma
    vez que `_SUPPORTED_PROTOCOL_VERSIONS` inclui "2026-07-28", QUALQUER
    resultado "complete" deste dispatch precisa do campo) vale também para
    `resources/list`, `resources/read` e `prompts/list`/`prompts/get` — sem
    fechar esses também, a próxima chamada nova a um deles reproduziria o
    mesmo bug de novo, só que descoberto de novo do zero. `ping` e
    `resources/templates/list` também foram corrigidos (literais de uma
    linha só, direto no dispatch de `mcpServer`) mas não ganharam teste
    dedicado aqui — o risco de regressão silenciosa neles é baixo o
    suficiente (sem lógica, sem I/O) para não justificar o custo de montar
    um `https_fn.Request` mockado só para exercitar duas linhas literais;
    isso fica documentado como limitação deliberada, não como esquecimento."""

    def test_resources_list_inclui_resulttype(self):
        r = mcp_server._handle_resources_list()
        self.assertEqual(r["resultType"], "complete")
        self.assertTrue(r["resources"])

    def test_resources_read_inclui_resulttype(self):
        with patch.object(mcp_server, "firestore") as mock_firestore, \
             patch.object(mcp_server, "build_mcp_voice_context", return_value="contexto"):
            mock_firestore.client.return_value = MagicMock()
            r = mcp_server._handle_resources_read(
                {"uri": mcp_server._RESOURCE_VOICE_CONTEXT}, uid="dono-uid"
            )
        self.assertEqual(r["resultType"], "complete")
        self.assertEqual(r["contents"][0]["text"], "contexto")

    def test_prompts_list_inclui_resulttype_mesmo_sem_pops(self):
        mock_db = MagicMock()
        mock_db.collection.return_value.limit.return_value.stream.return_value = []
        with patch.object(mcp_server, "firestore") as mock_firestore:
            mock_firestore.client.return_value = mock_db
            r = mcp_server._handle_prompts_list()
        self.assertEqual(r["resultType"], "complete")
        self.assertEqual(r["prompts"], [])

    def test_prompts_get_inclui_resulttype(self):
        snap = MagicMock(exists=True)
        snap.to_dict.return_value = {"titulo": "Um POP", "instrucao_sistema": "faça x"}
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = snap
        with patch.object(mcp_server, "firestore") as mock_firestore:
            mock_firestore.client.return_value = mock_db
            r = mcp_server._handle_prompts_get({"name": "um-pop"})
        self.assertEqual(r["resultType"], "complete")
        self.assertIn("faça x", r["messages"][0]["content"]["text"])


if __name__ == "__main__":
    unittest.main()
