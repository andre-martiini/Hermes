"""Testes de `registry.output_schema` e da sua ligação a `tools/list`
(`mcp_server._handle_tools_list`) e a `structuredContent` em `tools/call`
(`mcp_server._handle_tools_call`).

P03 passo 3 do plano de autonomia (docs/plano-hermes-autonomo-2026-09-06.md):
"Adicionar outputSchema, structuredContent, annotations e envelope aos
caminhos compatíveis; manter content legado". `annotations` já estava
coberto (sub-entregas 6/N e 7/N, ver test_mcp_annotations.py); esta
sub-entrega cobre a fatia `outputSchema`/`structuredContent`, começando
com UMA tool só: `calculadora` -- pura, determinística, sem rede nem
Firestore, sempre um dict achatado com exatamente duas formas possíveis
(sucesso ou erro de cálculo, nunca as duas juntas nem um terceiro campo --
ver docstring de `registry.output_schema` e o corpo de
`tools/hermes_tools.py::_calculadora`).

Três frentes:
1. `TestOutputSchema` -- a função pura em `tools/registry.py`, incluindo
   paridade com TODO o catálogo real (não amostra): nenhuma tool além de
   `calculadora` tem contrato publicado hoje.
2. `TestHandleToolsListOutputSchema` -- ponta a ponta via
   `mcp_server._handle_tools_list()`: `outputSchema` chega no catálogo
   publicado só para `calculadora`.
3. `TestIntegracaoHandleToolsCallStructuredContent` -- ponta a ponta via
   `mcp_server._handle_tools_call`: `structuredContent` chega no envelope
   de `tools/call` para `calculadora` (sucesso e erro de cálculo
   reconhecido pelo próprio executor), é sempre IGUAL ao dict que
   `content[0].text` serializa (mesma fonte, nunca diverge), bate com o
   `outputSchema` publicado campo a campo, e nunca aparece para uma tool
   sem contrato publicado -- nem quando o resultado real também é um dict,
   nem quando o executor levanta uma exceção não tratada por ele mesmo.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import mcp_server
from tools import registry
from tools.tool_context import ToolContext


def _ctx(uid: str = "dono-uid") -> ToolContext:
    return ToolContext(user_uid=uid, canal="mcp", _db=object())


class TestOutputSchema(unittest.TestCase):
    def test_calculadora_tem_schema_com_expressao_obrigatoria(self):
        schema = registry.output_schema("calculadora")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["expressao"])
        self.assertEqual(set(schema["properties"].keys()), {"expressao", "resultado", "erro"})
        self.assertFalse(schema["additionalProperties"])

    def test_tool_sem_contrato_devolve_none(self):
        # Nenhuma outra tool do catálogo tem outputSchema publicado ainda --
        # lista deliberadamente fechada, uma tool investigada por vez (ver
        # docstring de registry.output_schema).
        for nome in ("consultar_historico_acoes", "criar_acao_no_sistema", "obter_estado_atual"):
            with self.subTest(tool=nome):
                self.assertIsNone(registry.output_schema(nome))

    def test_tool_inexistente_devolve_none(self):
        self.assertIsNone(registry.output_schema("tool_que_nao_existe_de_verdade"))

    def test_paridade_apenas_calculadora_tem_output_schema_hoje(self):
        # Não por amostragem: para TODA tool do catálogo real (105 hoje),
        # output_schema devolve algo só para calculadora -- prova que a
        # lista fechada não vazou para nenhuma outra tool por engano.
        for nome in registry.list_tool_names():
            with self.subTest(tool=nome):
                if nome == "calculadora":
                    self.assertIsNotNone(registry.output_schema(nome))
                else:
                    self.assertIsNone(registry.output_schema(nome))


class TestHandleToolsListOutputSchema(unittest.TestCase):
    def setUp(self):
        self.catalogo = {t["name"]: t for t in mcp_server._handle_tools_list()["tools"]}

    def test_calculadora_publica_output_schema(self):
        self.assertIn("outputSchema", self.catalogo["calculadora"])
        self.assertEqual(
            self.catalogo["calculadora"]["outputSchema"], registry.output_schema("calculadora")
        )

    def test_nenhuma_outra_tool_publicada_tem_output_schema(self):
        com_schema = [
            nome for nome, tool in self.catalogo.items()
            if nome != "calculadora" and "outputSchema" in tool
        ]
        self.assertEqual(com_schema, [], f"Tools publicadas com outputSchema inesperado: {com_schema}")

    def test_output_schema_nao_interfere_no_resto_do_tool_entry(self):
        # Campo aditivo -- annotations (sub-entregas 6/N-7/N) e _meta
        # (anteriores ao P03) continuam presentes e corretos ao lado dele.
        tool = self.catalogo["calculadora"]
        self.assertIn("_meta", tool)
        self.assertIn("inputSchema", tool)
        self.assertIn("annotations", tool)
        self.assertIn("outputSchema", tool)


class TestIntegracaoHandleToolsCallStructuredContent(unittest.TestCase):
    def setUp(self):
        patcher_confirmacao = patch.object(mcp_server, "_exige_confirmacao", return_value=False)
        self.addCleanup(patcher_confirmacao.stop)
        patcher_confirmacao.start()
        patcher_mcp_enabled = patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True)
        self.addCleanup(patcher_mcp_enabled.stop)
        patcher_mcp_enabled.start()

    def test_calculadora_sucesso_leva_structured_content_igual_ao_content(self):
        resultado = mcp_server._handle_tools_call(
            {"name": "calculadora", "arguments": {"expressao": "2 + 2"}}, ctx=_ctx()
        )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        esperado = {"expressao": "2 + 2", "resultado": "4"}
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_calculadora_erro_de_calculo_tambem_leva_structured_content(self):
        # Erro RECONHECIDO pelo próprio executor (`_calculadora` captura a
        # exceção internamente e devolve {"erro": ...} em vez de propagar)
        # -- isError=True, mas o resultado ainda é um dict na mesma forma
        # do schema (sem "resultado", com "erro").
        resultado = mcp_server._handle_tools_call(
            {"name": "calculadora", "arguments": {"expressao": "1 / 0"}}, ctx=_ctx()
        )
        self.assertTrue(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"]["expressao"], "1 / 0")
        self.assertIn("erro", resultado["structuredContent"])
        self.assertNotIn("resultado", resultado["structuredContent"])
        self.assertEqual(json.loads(resultado["content"][0]["text"]), resultado["structuredContent"])

    def test_structured_content_bate_com_o_output_schema_publicado(self):
        # Paridade campo a campo contra o outputSchema real publicado em
        # tools/list -- não hardcoda a forma esperada aqui, lê do próprio
        # contrato, para as duas formas possíveis de calculadora.
        schema = registry.output_schema("calculadora")
        propriedades = schema["properties"]
        obrigatorios = schema["required"]
        for expressao in ("2 + 2", "1 / 0"):
            with self.subTest(expressao=expressao):
                resultado = mcp_server._handle_tools_call(
                    {"name": "calculadora", "arguments": {"expressao": expressao}}, ctx=_ctx()
                )
                estruturado = resultado["structuredContent"]
                for campo in obrigatorios:
                    self.assertIn(campo, estruturado)
                for campo, valor in estruturado.items():
                    self.assertIn(
                        campo, propriedades,
                        f"campo '{campo}' fora do outputSchema (additionalProperties=False)",
                    )
                    self.assertIsInstance(valor, str)  # todas as propriedades declaradas sao "type": "string"

    def test_tool_sem_output_schema_nunca_leva_structured_content_mesmo_com_dict(self):
        # `consultar_processo_sipac` não tem outputSchema publicado; mesmo
        # quando o executor devolve um dict de verdade, o envelope não
        # inventa um structuredContent sem contrato correspondente.
        with patch.object(mcp_server, "execute_tool", return_value={"ok": True}):
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "consultar_processo_sipac",
                    "arguments": {"numero_processo": "23000.000001/2026-00"},
                },
                ctx=_ctx(),
            )
        self.assertNotIn("structuredContent", resultado)

    def test_excecao_nao_tratada_pelo_executor_nunca_leva_structured_content(self):
        # Diferente do caso "erro de cálculo" acima (tratado dentro de
        # _calculadora): uma exceção que ESCAPA do executor cai no bloco
        # `except Exception` de _handle_tools_call, que nunca inventa um
        # dict ad-hoc como structuredContent.
        with patch.object(mcp_server, "execute_tool", side_effect=RuntimeError("sentinela")):
            resultado = mcp_server._handle_tools_call(
                {"name": "calculadora", "arguments": {"expressao": "2 + 2"}}, ctx=_ctx()
            )
        self.assertTrue(resultado["isError"])
        self.assertNotIn("structuredContent", resultado)

    def test_resultado_string_nunca_leva_structured_content(self):
        # Muitos handlers devolvem string crua (ex.: "ERRO|..." ou texto
        # formatado) em vez de dict -- structuredContent exige um dict real
        # do executor, nunca é reconstruído fazendo parse da string.
        with patch.object(mcp_server, "execute_tool", return_value="ERRO|alguma coisa"):
            resultado = mcp_server._handle_tools_call(
                {"name": "calculadora", "arguments": {"expressao": "2 + 2"}}, ctx=_ctx()
            )
        self.assertNotIn("structuredContent", resultado)

    def test_valor_nao_serializavel_no_dict_nao_quebra_structured_content(self):
        # Achado da revisão adversarial desta sub-entrega: `structuredContent`
        # tem que vir do MESMO `json.dumps(..., default=str)` que já protege
        # `content`, nunca do dict cru do executor -- senão uma tool futura
        # com outputSchema e um valor não-JSON-nativo (datetime, Timestamp do
        # Firestore, Decimal -- comuns em outros handlers deste catálogo)
        # quebraria a serialização final do envelope inteiro
        # (`mcp_server._json_response` não usa `default=str`, e fica fora de
        # qualquer try/except que proteja o cliente de um 500 cru). Para
        # `calculadora` isso não acontece na prática hoje (o handler real já
        # força `str()` em tudo), mas o MECANISMO GERAL precisa ser seguro
        # para a próxima tool que ganhar outputSchema -- daí o mock aqui, com
        # um dict que a implementação real de `_calculadora` nunca produz.
        import datetime

        with patch.object(
            mcp_server, "execute_tool",
            return_value={"expressao": "2 + 2", "resultado": datetime.date(2026, 9, 12)},
        ):
            resultado = mcp_server._handle_tools_call(
                {"name": "calculadora", "arguments": {"expressao": "2 + 2"}}, ctx=_ctx()
            )
        self.assertIn("structuredContent", resultado)
        # O valor não-nativo virou string (via default=str no json.dumps que
        # produz `text`), nunca propagado como objeto Python cru.
        self.assertEqual(resultado["structuredContent"]["resultado"], "2026-09-12")
        self.assertIsInstance(resultado["structuredContent"]["resultado"], str)
        # Prova final: o envelope inteiro tem que ser de fato serializável
        # para JSON sem `default=str` -- a mesma chamada que
        # `mcp_server._json_response` faz na resposta HTTP real.
        json.dumps(resultado, ensure_ascii=False)
