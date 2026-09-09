"""Testes da validação de argumentos obrigatórios no dispatch MCP.

P03 passo 2 do plano de autonomia (docs/plano-hermes-autonomo-2026-09-06.md):
"implementar normalizador de resultados legados e validação de argumentos".
Esta sub-entrega cobre só a primeira metade, e dela só a fatia mais segura:
um preflight que rejeita, com uma mensagem clara, uma chamada `tools/call`
que já não inclui um campo que o próprio schema publicado (`tools/list`)
marca como `required` — hoje isso não existe em lugar nenhum do dispatch
(`mcp_server.py::_handle_tools_call` chama `execute_tool(name, arguments,
ctx)` sem validar nada contra o schema; `tools/hermes_tools.py::execute()`
é só `_HANDLERS[name](ctx, arguments or {})`, sem checagem alguma). O
resultado hoje é inconsistente por handler: alguns checam um campo vazio e
devolvem uma string livre `"ERRO|..."`, outros fazem algo como
`int(args.get("limite") or 20)` sem tratar exceção (vira um `{"erro":
str(exc)}` opaco via o `except Exception` de `_handle_tools_call`), outros
não checam nada e ficam sujeitos ao que a camada de baixo fizer com um dado
incompleto.

Checagem de TIPO (schema `type`) fica para uma sub-entrega futura — ver a
docstring de `registry.campos_obrigatorios_ausentes` para o raciocínio
completo de por que a fatia de tipo é mais arriscada e foi deixada de fora
aqui.

Este arquivo tem três frentes:
1. `TestCamposObrigatoriosAusentes` — a função pura em `tools/registry.py`,
   incluindo uma verificação de paridade contra TODOS os schemas reais do
   catálogo (não só alguns exemplos escolhidos a dedo).
2. `TestErroCamposObrigatorios` — o wrapper de `mcp_server.py` que traduz a
   lista de campos ausentes na resposta MCP pronta para devolver.
3. `TestIntegracaoHandleToolsCall` — prova ponta a ponta que uma chamada
   com campo obrigatório ausente nunca chega a `preview_tool`/`execute_tool`
   nos dois pontos reais do dispatch, e que os caminhos que devem ficar
   fora do alcance desta checagem (reenvio `_confirmed=true`) continuam
   funcionando exatamente como antes.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import mcp_server
from tools import registry
from tools.tool_context import ToolContext


def _ctx(uid: str = "dono-uid") -> ToolContext:
    return ToolContext(user_uid=uid, canal="mcp", _db=object())


class TestCamposObrigatoriosAusentes(unittest.TestCase):
    """`registry.campos_obrigatorios_ausentes` isolada, sem tocar o dispatch."""

    def test_todos_os_campos_presentes_devolve_lista_vazia(self):
        self.assertEqual(
            registry.campos_obrigatorios_ausentes(
                "acompanhar_processo_sipac",
                {"numero_processo": "123", "acompanhar": True},
            ),
            [],
        )

    def test_campo_obrigatorio_faltando_a_chave(self):
        self.assertEqual(
            registry.campos_obrigatorios_ausentes("acompanhar_processo_sipac", {}),
            ["numero_processo"],
        )

    def test_campo_obrigatorio_presente_mas_none_conta_como_ausente(self):
        self.assertEqual(
            registry.campos_obrigatorios_ausentes(
                "acompanhar_processo_sipac", {"numero_processo": None}
            ),
            ["numero_processo"],
        )

    def test_valor_falsy_mas_valido_nao_conta_como_ausente(self):
        # `acompanhar` (bool, não obrigatório) não deveria nunca ser marcado;
        # o campo obrigatório do teste (`numero_processo`) recebe string
        # vazia -- isso ainda É uma chave presente (não None), então esta
        # sub-entrega (só presença, não tipo/conteúdo) não rejeita.
        self.assertEqual(
            registry.campos_obrigatorios_ausentes(
                "acompanhar_processo_sipac", {"numero_processo": "", "acompanhar": False}
            ),
            [],
        )

    def test_tool_sem_required_no_schema_nunca_acusa_nada(self):
        self.assertEqual(registry.campos_obrigatorios_ausentes("obter_estado_atual", {}), [])
        self.assertEqual(
            registry.campos_obrigatorios_ausentes("consultar_dados_cadastrais", {}), []
        )

    def test_tool_inexistente_falha_aberta(self):
        # Schema ausente não pode virar um bloqueio novo por conta própria —
        # mesma filosofia de `_handle_tools_list` ao omitir (não derrubar)
        # uma tool com schema quebrado.
        self.assertEqual(
            registry.campos_obrigatorios_ausentes("tool_que_nao_existe_de_verdade", {}), []
        )

    def test_multiplos_campos_obrigatorios_ausentes_sao_todos_listados(self):
        ausentes = registry.campos_obrigatorios_ausentes("acompanhar_processo_sipac", {})
        self.assertEqual(set(ausentes), {"numero_processo"})

    def test_criar_rascunho_email_nao_exige_assunto_por_causa_da_heranca_de_thread(self):
        # Achado da revisão adversarial desta sub-entrega: o schema original
        # marcava `assunto` como `required`, mas o próprio schema documenta
        # que ele "pode ficar vazio ao responder uma thread" — e o handler
        # (`tools/criar_rascunho_email.py:77-79`) de fato herda o assunto da
        # thread e só rejeita se, mesmo assim, ficar vazio. Marcar `assunto`
        # como obrigatório no schema rejeitava essa chamada válida antes de
        # o handler sequer ter a chance de fazer a herança. `corpo` continua
        # exigido -- não tem herança nem valor default no handler.
        self.assertEqual(
            registry.campos_obrigatorios_ausentes(
                "criar_rascunho_email",
                {"responder_a_thread_id": "thread-1", "corpo": "Resposta"},
            ),
            [],
        )
        self.assertEqual(
            registry.campos_obrigatorios_ausentes("criar_rascunho_email", {}),
            ["corpo"],
        )

    def test_salvar_pop_global_nao_exige_instrucao_sistema_quando_alias_presente(self):
        # Mesmo achado, segundo caso: o schema documenta `instrucao`/
        # `conteudo` como "apelido de instrucao_sistema", e o handler
        # (`tools/telegram_extended.py:195-196`) resolve os três por `or`
        # antes de checar se ficou vazio. `instrucao_sistema` sozinho não
        # pode continuar `required` sem contradizer o próprio schema.
        self.assertEqual(
            registry.campos_obrigatorios_ausentes(
                "salvar_pop_global",
                {"titulo": "X", "gatilhos": ["y"], "instrucao": "faça isso"},
            ),
            [],
        )
        self.assertEqual(
            set(registry.campos_obrigatorios_ausentes("salvar_pop_global", {})),
            {"titulo", "gatilhos"},
        )

    def test_paridade_com_todos_os_schemas_reais_do_catalogo(self):
        # Não por amostragem: para cada tool do catálogo real, chamar com
        # `{}` deve devolver exatamente o `required` declarado no schema
        # (quando não vazio) -- prova que a função lê o schema publicado de
        # verdade, não uma cópia própria que pode divergir com o tempo.
        for nome in sorted(registry.list_tool_names()):
            with self.subTest(tool=nome):
                schema = registry.get_schema(nome)
                required = schema.get("parameters", {}).get("required") or []
                ausentes = registry.campos_obrigatorios_ausentes(nome, {})
                self.assertEqual(set(ausentes), set(required))


class TestErroCamposObrigatorios(unittest.TestCase):
    """`mcp_server._erro_campos_obrigatorios`: tradução para a resposta MCP."""

    def test_none_quando_argumentos_completos(self):
        self.assertIsNone(
            mcp_server._erro_campos_obrigatorios(
                "acompanhar_processo_sipac", {"numero_processo": "123"}
            )
        )

    def test_resposta_de_erro_quando_argumento_ausente(self):
        resultado = mcp_server._erro_campos_obrigatorios("acompanhar_processo_sipac", {})
        self.assertIsNotNone(resultado)
        self.assertTrue(resultado["isError"])
        self.assertEqual(resultado["resultType"], "complete")
        texto = resultado["content"][0]["text"]
        self.assertIn("numero_processo", texto)

    def test_tool_sem_required_nunca_gera_erro(self):
        self.assertIsNone(mcp_server._erro_campos_obrigatorios("obter_estado_atual", {}))


class TestIntegracaoHandleToolsCall(unittest.TestCase):
    """Ponta a ponta via `_handle_tools_call`, nos dois pontos reais do
    dispatch onde `arguments` é o payload de negócio completo."""

    def setUp(self):
        patcher = patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_tool_nao_gated_com_campo_obrigatorio_ausente_nunca_chega_a_execute_tool(self):
        # `consultar_processo_sipac` não exige confirmação e tem
        # `numero_processo` como obrigatório.
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool") as mock_execute:
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_processo_sipac", "arguments": {}}, ctx=_ctx()
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado["isError"])
        self.assertIn("numero_processo", resultado["content"][0]["text"])

    def test_tool_nao_gated_com_argumentos_completos_chega_a_execute_tool(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool", return_value={"ok": True}) as mock_execute:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "consultar_processo_sipac",
                    "arguments": {"numero_processo": "23000.000001/2026-00"},
                },
                ctx=_ctx(),
            )
        mock_execute.assert_called_once()
        self.assertFalse(resultado.get("isError", False))

    def test_tool_gated_primeira_chamada_com_campo_ausente_nunca_chega_a_preview(self):
        # `criar_rascunho_email` exige confirmação; `corpo` é obrigatório
        # (sem herança/default no handler, ao contrário de `assunto`).
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(mcp_server, "_decisao_piso_mcp", return_value=None), \
             patch.object(mcp_server, "preview_tool") as mock_preview:
            resultado = mcp_server._handle_tools_call(
                {"name": "criar_rascunho_email", "arguments": {"assunto": "Oi"}}, ctx=_ctx()
            )
        mock_preview.assert_not_called()
        self.assertTrue(resultado["isError"])
        self.assertIn("corpo", resultado["content"][0]["text"])
        self.assertIn("corpo", resultado["content"][0]["text"])

    def test_tool_gated_primeira_chamada_com_argumentos_completos_chega_a_preview(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(mcp_server, "_decisao_piso_mcp", return_value=None), \
             patch.object(
                 mcp_server, "preview_tool", side_effect=RuntimeError("sentinela")
             ) as mock_preview:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "criar_rascunho_email",
                    "arguments": {"assunto": "Oi", "corpo": "Corpo do email"},
                },
                ctx=_ctx(),
            )
        mock_preview.assert_called_once()
        self.assertTrue(resultado["isError"])
        self.assertIn("sentinela", resultado["content"][0]["text"])

    def test_reenvio_confirmed_true_nao_passa_pela_checagem_mesmo_com_payload_incompleto(self):
        # Deliberado (ver docstring de `_erro_campos_obrigatorios`): no
        # reenvio `_confirmed=true` + `_confirmation_id`, `arguments` é só o
        # envelope da confirmação -- os campos de negócio reais já foram
        # congelados no Firestore quando a prévia foi criada. Validar de
        # novo aqui rejeitaria TODO reenvio de qualquer tool com campo
        # obrigatório, quebrando o fluxo de confirmação inteiro.
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(
                 mcp_server, "_executar_confirmacao", return_value={"ok": True}
             ) as mock_executar:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "criar_rascunho_email",
                    "arguments": {"_confirmed": True, "_confirmation_id": "conf-1"},
                },
                ctx=_ctx(),
            )
        mock_executar.assert_called_once()
        self.assertFalse(resultado.get("isError", False))


if __name__ == "__main__":
    unittest.main()
