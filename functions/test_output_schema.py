"""Testes de `registry.output_schema` e da sua ligação a `tools/list`
(`mcp_server._handle_tools_list`) e a `structuredContent` em `tools/call`
(`mcp_server._handle_tools_call`).

P03 passo 3 do plano de autonomia (docs/plano-hermes-autonomo-2026-09-06.md):
"Adicionar outputSchema, structuredContent, annotations e envelope aos
caminhos compatíveis; manter content legado". `annotations` já estava
coberto (sub-entregas 6/N e 7/N, ver test_mcp_annotations.py); esta
sub-entrega cobre a fatia `outputSchema`/`structuredContent`, começando
com `calculadora` (sub-entrega 8/N) -- pura, determinística, sem rede nem
Firestore, sempre um dict achatado com exatamente duas formas possíveis
(sucesso ou erro de cálculo, nunca as duas juntas nem um terceiro campo --
ver docstring de `registry.output_schema` e o corpo de
`tools/hermes_tools.py::_calculadora`) -- e acrescentando `buscar_contato`
(sub-entrega 9/N) -- também pura leitura, sem rede, com exatamente duas
formas no nível superior (termo vazio ou sucesso), cujo item de
`candidatos` é montado inteiramente a mão dentro da própria função, exceto
`modelo_interacao` (sempre `None` ou dict, mas com conteúdo gerado por LLM
sem a mesma garantia estrutural -- ver comentário de `_OUTPUT_SCHEMAS` em
`tools/registry.py`).

Três frentes:
1. `TestOutputSchema` -- a função pura em `tools/registry.py`, incluindo
   paridade com TODO o catálogo real (não amostra): nenhuma tool além de
   `calculadora` e `buscar_contato` tem contrato publicado hoje.
2. `TestHandleToolsListOutputSchema` -- ponta a ponta via
   `mcp_server._handle_tools_list()`: `outputSchema` chega no catálogo
   publicado só para essas duas tools.
3. `TestIntegracaoHandleToolsCallStructuredContent` -- ponta a ponta via
   `mcp_server._handle_tools_call`: `structuredContent` chega no envelope
   de `tools/call` para `calculadora` (execução real, pura) e para
   `buscar_contato` (executor mockado -- a função real depende de
   Firestore, então o teste cobre o MECANISMO, não a correção interna de
   `_buscar_contato`, mesmo padrão já usado para `consultar_processo_sipac`
   abaixo), é sempre IGUAL ao dict que `content[0].text` serializa (mesma
   fonte, nunca diverge), bate com o `outputSchema` publicado campo a
   campo, e nunca aparece para uma tool sem contrato publicado -- nem
   quando o resultado real também é um dict, nem quando o executor levanta
   uma exceção não tratada por ele mesmo.
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

    def test_buscar_contato_tem_schema_com_candidatos_obrigatorio(self):
        schema = registry.output_schema("buscar_contato")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["candidatos"])
        self.assertEqual(set(schema["properties"].keys()), {"erro", "candidatos"})
        self.assertFalse(schema["additionalProperties"])

        item = schema["properties"]["candidatos"]["items"]
        self.assertEqual(
            set(item["properties"].keys()),
            {"pessoa_id", "nome", "email", "telefone", "whatsapp_chat_id",
             "tags", "modelo_interacao", "score"},
        )
        self.assertEqual(
            set(item["required"]),
            {"pessoa_id", "nome", "email", "telefone", "whatsapp_chat_id",
             "tags", "modelo_interacao", "score"},
        )
        # modelo_interacao é sempre uma das 8 chaves presentes no dict
        # construído por `_buscar_contato` (mesmo quando o valor é None) --
        # por isso está em required como as outras 7, ao contrário de
        # "erro" no nível superior, que fica de fato ausente em sucesso.
        self.assertIn("modelo_interacao", item["required"])
        self.assertFalse(item["additionalProperties"])
        # modelo_interacao é sempre None ou dict (confirmado em
        # main.py::parse_resposta_modelo_pessoa), mas o CONTEÚDO desse dict
        # é gerado por LLM e não tem a mesma garantia estrutural do resto
        # do item -- por isso só o tipo externo é declarado, sem
        # `properties`/`additionalProperties` aninhado.
        self.assertEqual(item["properties"]["modelo_interacao"]["type"], ["object", "null"])
        # tags vem direto de `data.get("tags", [])`, sem normalização de
        # elemento -- deliberadamente sem `items` aninhado, mesmo motivo.
        self.assertEqual(item["properties"]["tags"], {"type": "array"})

    def test_paridade_calculadora_e_buscar_contato_tem_output_schema_hoje(self):
        # Não por amostragem: para TODA tool do catálogo real (106 hoje),
        # output_schema devolve algo só para calculadora e buscar_contato --
        # prova que a lista fechada não vazou para nenhuma outra tool por
        # engano.
        com_schema = {"calculadora", "buscar_contato"}
        for nome in registry.list_tool_names():
            with self.subTest(tool=nome):
                if nome in com_schema:
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

    def test_buscar_contato_publica_output_schema(self):
        self.assertIn("outputSchema", self.catalogo["buscar_contato"])
        self.assertEqual(
            self.catalogo["buscar_contato"]["outputSchema"], registry.output_schema("buscar_contato")
        )

    def test_nenhuma_outra_tool_publicada_tem_output_schema(self):
        esperadas = {"calculadora", "buscar_contato"}
        com_schema = [
            nome for nome, tool in self.catalogo.items()
            if nome not in esperadas and "outputSchema" in tool
        ]
        self.assertEqual(com_schema, [], f"Tools publicadas com outputSchema inesperado: {com_schema}")

    def test_output_schema_nao_interfere_no_resto_do_tool_entry(self):
        # Campo aditivo -- annotations (sub-entregas 6/N-7/N) e _meta
        # (anteriores ao P03) continuam presentes e corretos ao lado dele.
        for nome in ("calculadora", "buscar_contato"):
            with self.subTest(tool=nome):
                tool = self.catalogo[nome]
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

    def test_buscar_contato_sucesso_leva_structured_content_igual_ao_content(self):
        # `_buscar_contato` real depende de Firestore (ctx.db.collection(...)
        # .stream()); o executor é mockado aqui com uma forma real que a
        # função produz (ver `tools/hermes_tools.py::_buscar_contato`), para
        # testar o MECANISMO de ligação outputSchema/structuredContent, não
        # a lógica de busca em si -- mesmo padrão de
        # `test_tool_sem_output_schema_nunca_leva_structured_content_mesmo_com_dict`
        # abaixo, que também mocka `execute_tool` para uma tool real.
        esperado = {
            "candidatos": [
                {
                    "pessoa_id": "abc123",
                    "nome": "Fulano de Tal",
                    "email": "fulano@example.com",
                    "telefone": "+55 27 99999-0000",
                    "whatsapp_chat_id": "5527999990000@s.whatsapp.net",
                    "tags": ["fornecedor"],
                    "modelo_interacao": None,
                    "score": 1.0,
                }
            ]
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "buscar_contato", "arguments": {"termo": "fulano"}}, ctx=_ctx()
            )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_buscar_contato_termo_vazio_tambem_leva_structured_content(self):
        esperado = {"erro": "Termo de busca vazio.", "candidatos": []}
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "buscar_contato", "arguments": {"termo": ""}}, ctx=_ctx()
            )
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)

    def test_buscar_contato_structured_content_bate_com_o_output_schema_publicado(self):
        schema = registry.output_schema("buscar_contato")
        propriedades = schema["properties"]
        candidato_props = propriedades["candidatos"]["items"]["properties"]
        mock_retorno = {
            "candidatos": [
                {
                    "pessoa_id": "abc123",
                    "nome": "Fulano de Tal",
                    "email": "fulano@example.com",
                    "telefone": "",
                    "whatsapp_chat_id": "",
                    "tags": [],
                    "modelo_interacao": {"registro": "informal", "acoes_recentes": []},
                    "score": 0.8,
                }
            ]
        }
        with patch.object(mcp_server, "execute_tool", return_value=mock_retorno):
            resultado = mcp_server._handle_tools_call(
                {"name": "buscar_contato", "arguments": {"termo": "fulano"}}, ctx=_ctx()
            )
        estruturado = resultado["structuredContent"]
        for campo in schema["required"]:
            self.assertIn(campo, estruturado)
        for campo in estruturado:
            self.assertIn(campo, propriedades, f"campo '{campo}' fora do outputSchema")
        for candidato in estruturado["candidatos"]:
            for campo in candidato:
                self.assertIn(campo, candidato_props, f"campo '{campo}' fora do item declarado")

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
