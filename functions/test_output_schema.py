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
`tools/registry.py`) -- e `consultar_lista_compras` (sub-entrega 10/N):
terceira tool, mais segura que `buscar_contato` quanto à garantia de tipo
NA PRÓPRIA FUNÇÃO (não a mais forte das três: `calculadora` força `str()`
em TODO campo sem exceção; `consultar_lista_compras` tem uma exceção sem
coerção, o campo opcional `ordem`), porque `tools/lista_compras.py::_item_publico`
força `str()`/`bool()` nos demais campos do item antes de devolver -- mas
a coleção `shopping_items` também é lida/escrita por outros caminhos, risco
aceito e não-bloqueante (ver comentário de `_OUTPUT_SCHEMAS` em
`tools/registry.py`, e o diário desta sub-entrega para o histórico
completo da revisão adversarial que motivou essa redação) -- e
`consultar_execucoes_agente` (sub-entrega 11/N): quarta tool, com a
garantia de tipo mais forte do grupo até aqui, porque a coleção que ela lê
(`agent_runs`) tem um único escritor em todo o repositório
(`agent_runs.registrar`), que sempre valida os campos obrigatórios antes
de gravar (`agent_runs.montar_registro`) -- ver comentário de
`_OUTPUT_SCHEMAS` em `tools/registry.py` para o levantamento completo,
incluindo as duas candidatas descartadas por terem formato alternativo de
erro.

Três frentes:
1. `TestOutputSchema` -- a função pura em `tools/registry.py`, incluindo
   paridade com TODO o catálogo real (não amostra): nenhuma tool além de
   `calculadora`, `buscar_contato`, `consultar_lista_compras` e
   `consultar_execucoes_agente` tem contrato publicado hoje.
2. `TestHandleToolsListOutputSchema` -- ponta a ponta via
   `mcp_server._handle_tools_list()`: `outputSchema` chega no catálogo
   publicado só para essas quatro tools.
3. `TestIntegracaoHandleToolsCallStructuredContent` -- ponta a ponta via
   `mcp_server._handle_tools_call`: `structuredContent` chega no envelope
   de `tools/call` para `calculadora` (execução real, pura) e para
   `buscar_contato`/`consultar_lista_compras`/`consultar_execucoes_agente`
   (executor mockado -- as três dependem de Firestore, então o teste cobre
   o MECANISMO, não a correção interna dos handlers, mesmo padrão já usado
   para `consultar_processo_sipac` abaixo), é sempre IGUAL ao dict que
   `content[0].text` serializa (mesma fonte, nunca diverge), bate com o
   `outputSchema` publicado campo a campo, e nunca aparece para uma tool
   sem contrato publicado -- nem quando o resultado real também é um dict,
   nem quando o executor levanta uma exceção não tratada por ele mesmo, nem
   quando o handler devolve uma string crua de erro (caminho real de
   `consultar_lista_compras` para filtro inválido, ver
   `tools/hermes_tools.py::_consultar_lista_compras`).
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

    def test_consultar_lista_compras_tem_schema_com_campos_obrigatorios(self):
        schema = registry.output_schema("consultar_lista_compras")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["type"], "object")
        self.assertEqual(
            schema["required"],
            ["total", "planejados", "comprados", "filtro", "encontrados", "retornados", "itens"],
        )
        self.assertEqual(
            set(schema["properties"].keys()),
            {"total", "planejados", "comprados", "filtro", "encontrados", "retornados",
             "itens", "truncado"},
        )
        self.assertFalse(schema["additionalProperties"])
        # truncado só aparece quando True (handler nunca escreve
        # truncado=False) -- por isso fica fora de required, ao contrário
        # das contagens de topo, que estão sempre presentes.
        self.assertNotIn("truncado", schema["required"])
        # filtro é enum fechado -- lista_compras._FILTROS já resolve
        # qualquer entrada para um destes 5 valores antes de devolver.
        self.assertEqual(
            set(schema["properties"]["filtro"]["enum"]),
            {"todos", "planejados", "comprados", "pendentes", "nao_planejados"},
        )

        item = schema["properties"]["itens"]["items"]
        self.assertEqual(
            set(item["properties"].keys()),
            {"item_id", "nome", "categoria", "quantidade", "unit",
             "isPlanned", "isPurchased", "ordem"},
        )
        self.assertEqual(
            set(item["required"]),
            {"item_id", "nome", "categoria", "quantidade", "unit", "isPlanned", "isPurchased"},
        )
        # ordem é o único campo opcional do item (só presente quando o
        # documento do Firestore tem o campo) -- por isso fica fora de
        # required, diferente dos outros 7 campos que _item_publico sempre
        # inclui.
        self.assertNotIn("ordem", item["required"])
        self.assertFalse(item["additionalProperties"])

    def test_consultar_execucoes_agente_tem_schema_com_campos_obrigatorios(self):
        schema = registry.output_schema("consultar_execucoes_agente")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["total", "runs"])
        self.assertEqual(set(schema["properties"].keys()), {"total", "runs"})
        self.assertFalse(schema["additionalProperties"])

        item = schema["properties"]["runs"]["items"]
        campos_item = {
            "id", "rotina", "status", "resumo", "contadores",
            "erro", "iniciado_em", "finalizado_em", "criado_em",
        }
        self.assertEqual(set(item["properties"].keys()), campos_item)
        # Todos os 9 campos são sempre chaves presentes no dict construído
        # por `agent_runs.listar_recentes` (mesmo quando o valor é None) --
        # nenhum é omitido condicionalmente, ao contrário de `truncado`
        # (consultar_lista_compras) ou `erro` no nível superior de
        # buscar_contato.
        self.assertEqual(set(item["required"]), campos_item)
        self.assertFalse(item["additionalProperties"])
        # status é enum fechado -- agent_runs.montar_registro só grava um
        # destes 3 valores (STATUS_VALIDOS), rejeitando a escrita antes de
        # chegar no Firestore para qualquer outro.
        self.assertEqual(
            set(item["properties"]["status"]["enum"]), {"sucesso", "erro", "parcial"}
        )
        # contadores é um dict livre passado por quem chama
        # registrar_execucao_agente, sem forma fixa entre rotinas --
        # deliberadamente sem "properties" aninhado, mesmo espírito de
        # modelo_interacao (buscar_contato).
        self.assertEqual(item["properties"]["contadores"], {"type": "object"})
        # erro/iniciado_em/finalizado_em/criado_em passam por _to_iso, que
        # só devolve string ou None -- nunca outro tipo.
        for campo in ("erro", "iniciado_em", "finalizado_em", "criado_em"):
            with self.subTest(campo=campo):
                self.assertEqual(item["properties"][campo]["type"], ["string", "null"])

    def test_paridade_quatro_tools_tem_output_schema_hoje(self):
        # Não por amostragem: para TODA tool do catálogo real (106 hoje),
        # output_schema devolve algo só para calculadora, buscar_contato,
        # consultar_lista_compras e consultar_execucoes_agente -- prova que
        # a lista fechada não vazou para nenhuma outra tool por engano.
        com_schema = {
            "calculadora", "buscar_contato", "consultar_lista_compras",
            "consultar_execucoes_agente",
        }
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

    def test_consultar_lista_compras_publica_output_schema(self):
        self.assertIn("outputSchema", self.catalogo["consultar_lista_compras"])
        self.assertEqual(
            self.catalogo["consultar_lista_compras"]["outputSchema"],
            registry.output_schema("consultar_lista_compras"),
        )

    def test_consultar_execucoes_agente_publica_output_schema(self):
        self.assertIn("outputSchema", self.catalogo["consultar_execucoes_agente"])
        self.assertEqual(
            self.catalogo["consultar_execucoes_agente"]["outputSchema"],
            registry.output_schema("consultar_execucoes_agente"),
        )

    def test_nenhuma_outra_tool_publicada_tem_output_schema(self):
        esperadas = {
            "calculadora", "buscar_contato", "consultar_lista_compras",
            "consultar_execucoes_agente",
        }
        com_schema = [
            nome for nome, tool in self.catalogo.items()
            if nome not in esperadas and "outputSchema" in tool
        ]
        self.assertEqual(com_schema, [], f"Tools publicadas com outputSchema inesperado: {com_schema}")

    def test_output_schema_nao_interfere_no_resto_do_tool_entry(self):
        # Campo aditivo -- annotations (sub-entregas 6/N-7/N) e _meta
        # (anteriores ao P03) continuam presentes e corretos ao lado dele.
        for nome in (
            "calculadora", "buscar_contato", "consultar_lista_compras",
            "consultar_execucoes_agente",
        ):
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

    def test_consultar_lista_compras_sucesso_leva_structured_content_igual_ao_content(self):
        # `_consultar_lista_compras` real depende de Firestore
        # (`ctx.db.collection("shopping_items")...`); o executor é mockado
        # aqui com uma forma real que `lista_compras.consultar` produz (ver
        # `tools/lista_compras.py::consultar`/`_item_publico`), mesmo padrão
        # de `buscar_contato` acima -- testa o MECANISMO, não a lógica de
        # filtragem/busca em si.
        esperado = {
            "total": 3,
            "planejados": 2,
            "comprados": 1,
            "filtro": "todos",
            "encontrados": 3,
            "retornados": 3,
            "itens": [
                {
                    "item_id": "abc123",
                    "nome": "leite",
                    "categoria": "Geral",
                    "quantidade": "2",
                    "unit": "un",
                    "isPlanned": True,
                    "isPurchased": False,
                    "ordem": 1,
                },
                {
                    "item_id": "def456",
                    "nome": "pao",
                    "categoria": "Padaria",
                    "quantidade": "1",
                    "unit": "un",
                    "isPlanned": True,
                    "isPurchased": True,
                },
            ],
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_lista_compras", "arguments": {}}, ctx=_ctx()
            )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_consultar_lista_compras_filtro_invalido_nunca_leva_structured_content(self):
        # Caminho real de erro de `_consultar_lista_compras`: filtro
        # inválido levanta `ListaComprasError`, capturado pelo próprio
        # handler e devolvido como STRING "ERRO|..." (não dict) -- mesmo
        # mecanismo genérico de `test_resultado_string_nunca_leva_structured_content`
        # abaixo, mas exercitado aqui com o caminho de erro real desta tool
        # específica, não um mock genérico sobre `calculadora`.
        with patch.object(mcp_server, "execute_tool", return_value="ERRO|Filtro invalido."):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_lista_compras", "arguments": {"filtro": "invalido"}}, ctx=_ctx()
            )
        self.assertNotIn("structuredContent", resultado)

    def test_consultar_lista_compras_structured_content_bate_com_o_output_schema_publicado(self):
        schema = registry.output_schema("consultar_lista_compras")
        propriedades = schema["properties"]
        item_props = propriedades["itens"]["items"]["properties"]
        mock_retorno = {
            "total": 1,
            "planejados": 0,
            "comprados": 0,
            "filtro": "nao_planejados",
            "encontrados": 1,
            "retornados": 1,
            "itens": [
                {
                    "item_id": "xyz789",
                    "nome": "sal",
                    "categoria": "Geral",
                    "quantidade": "1",
                    "unit": "un",
                    "isPlanned": False,
                    "isPurchased": False,
                },
            ],
            "truncado": True,
        }
        with patch.object(mcp_server, "execute_tool", return_value=mock_retorno):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_lista_compras", "arguments": {"filtro": "nao_planejados"}},
                ctx=_ctx(),
            )
        estruturado = resultado["structuredContent"]
        for campo in schema["required"]:
            self.assertIn(campo, estruturado)
        for campo in estruturado:
            self.assertIn(campo, propriedades, f"campo '{campo}' fora do outputSchema")
        for item in estruturado["itens"]:
            for campo in item:
                self.assertIn(campo, item_props, f"campo '{campo}' fora do item declarado")
        # truncado=True chegou intacto -- prova que o campo opcional
        # atravessa o mecanismo igual aos obrigatórios.
        self.assertTrue(estruturado["truncado"])

    def test_consultar_execucoes_agente_sucesso_leva_structured_content_igual_ao_content(self):
        # `agent_runs.listar_recentes` real depende de Firestore
        # (`ctx.db.collection("agent_runs")...`); o executor é mockado aqui
        # com uma forma real que a função produz (ver `agent_runs.py`),
        # mesmo padrão de buscar_contato/consultar_lista_compras acima --
        # testa o MECANISMO, não a lógica de consulta em si.
        esperado = {
            "total": 2,
            "runs": [
                {
                    "id": "run-1",
                    "rotina": "briefing_matinal",
                    "status": "sucesso",
                    "resumo": "Briefing enviado sem pendências.",
                    "contadores": {"acoes_atrasadas": 0},
                    "erro": None,
                    "iniciado_em": "2026-09-13T07:00:00+00:00",
                    "finalizado_em": "2026-09-13T07:00:04+00:00",
                    "criado_em": "2026-09-13T07:00:04+00:00",
                },
                {
                    "id": "run-2",
                    "rotina": "avanco_autonomo_hermes",
                    "status": "parcial",
                    "resumo": "Argos indisponível; só leitura pública.",
                    "contadores": {},
                    "erro": "conector_indisponivel",
                    "iniciado_em": "2026-09-13T11:00:00+00:00",
                    "finalizado_em": None,
                    "criado_em": "2026-09-13T11:00:00+00:00",
                },
            ],
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_execucoes_agente", "arguments": {}}, ctx=_ctx()
            )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_consultar_execucoes_agente_lista_vazia_tambem_leva_structured_content(self):
        esperado = {"total": 0, "runs": []}
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_execucoes_agente", "arguments": {"rotina": "inexistente"}},
                ctx=_ctx(),
            )
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)

    def test_consultar_execucoes_agente_structured_content_bate_com_o_output_schema_publicado(self):
        schema = registry.output_schema("consultar_execucoes_agente")
        propriedades = schema["properties"]
        item_props = propriedades["runs"]["items"]["properties"]
        mock_retorno = {
            "total": 1,
            "runs": [
                {
                    "id": "run-3",
                    "rotina": "revisao_semanal",
                    "status": "erro",
                    "resumo": "Falha ao gerar proposta.",
                    "contadores": {"tentativas": 3},
                    "erro": "timeout ao consultar politica",
                    "iniciado_em": "2026-09-13T12:00:00+00:00",
                    "finalizado_em": "2026-09-13T12:00:30+00:00",
                    "criado_em": "2026-09-13T12:00:30+00:00",
                },
            ],
        }
        with patch.object(mcp_server, "execute_tool", return_value=mock_retorno):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_execucoes_agente", "arguments": {"rotina": "revisao_semanal"}},
                ctx=_ctx(),
            )
        estruturado = resultado["structuredContent"]
        for campo in schema["required"]:
            self.assertIn(campo, estruturado)
        for campo in estruturado:
            self.assertIn(campo, propriedades, f"campo '{campo}' fora do outputSchema")
        for run in estruturado["runs"]:
            for campo in run:
                self.assertIn(campo, item_props, f"campo '{campo}' fora do item declarado")

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
