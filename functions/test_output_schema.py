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
erro -- e `consultar_pedidos_agente` (sub-entrega 12/N): quinta tool,
backed por `agent_requests.listar_pendentes`, cuja coleção (`agent_requests`)
também tem um único ponto de criação de documento em todo o repositório
(`atencao_whatsapp.py`, via `agent_requests.enfileirar_ou_atualizar`) --
ver comentário de `_OUTPUT_SCHEMAS` em `tools/registry.py`, que também
corrige uma pendência registrada incorretamente na sub-entrega 11/N sobre
"vários escritores" nesta coleção -- e `consultar_historico_acoes`
(sub-entrega 14/N): sexta tool, e a PRIMEIRA com `oneOf` -- ao contrário
das cinco anteriores (uma forma só, com campos às vezes ausentes), o
handler (`tools/hermes_tools.py::_consultar_historico_acoes`, sobre
`tools/busca_grafo.py::buscar_tarefas`) tem duas formas de nível superior
com conjuntos de campos obrigatórios DISJUNTOS -- sucesso
(`total_retornado`/`resultados`/`filtros`) ou erro (`erro`/`resultados`,
sempre lista vazia) -- ver comentário de `_OUTPUT_SCHEMAS` em
`tools/registry.py` para o levantamento completo, incluindo por que
`oneOf` (nunca usado neste catálogo até esta sub-entrega, pendência
deixada pelas sub-entregas 12/N e 13/N) foi escolhido em vez de uma forma
única com tudo fora de `required` -- e `obter_acao` (sub-entrega 15/N):
sétima tool, e a com mais campos de nível superior até agora (24).
Também usa `oneOf`, mas por um motivo diferente de
`consultar_historico_acoes`: o handler
(`tools/hermes_tools.py::obter_acao`) tem 3 `return`, não 2 -- a
diferença entre os dois caminhos de erro é só a presença opcional do
campo `status` (sempre `"not_found"` quando aparece), então os dois
colapsam num único branch de erro com `status` fora de `required` -- ver
comentário de `_OUTPUT_SCHEMAS` em `tools/registry.py` para o
levantamento completo, incluindo as 8 fontes de escrita de `plano_acao` e
os 4 escritores de `pool_dados`/anexo investigados nesta sub-entrega -- e
`listar_rascunhos_pendentes` (sub-entrega 24/N): oitava tool, backed por
`outbox_aprovacao.listar_rascunhos`, com uma forma so (sem `oneOf`) e
`status` enum de 2 valores pela MESMA garantia de
`consultar_pedidos_agente` (filtro da propria query, nao "escritor
unico" -- a colecao `whatsapp_outbox` tem varios). Achado desta
sub-entrega: `telegram_message_id` e `["integer", "null"]`, nao string --
vem de `message_id` da API do Telegram (sempre inteiro), confirmado
tambem pela fixture `"telegram_message_id": 999` ja existente em
`test_outbox_aprovacao.py` -- ver comentario de `_OUTPUT_SCHEMAS` em
`tools/registry.py` para o levantamento completo dos pontos de criacao e
atualizacao de documento investigados -- e `consultar_job`
(sub-entrega 25/N): nona tool, backed por `mcp_jobs.ler_job` (passthrough
puro de `tools/hermes_tools.py::_consultar_job`), e a com MAIS branches de
`oneOf` ate agora (4, contra 2 de `consultar_historico_acoes`/`obter_acao`)
-- `mcp_jobs.py` e o UNICO escritor da colecao `mcp_jobs` em todo o
repositorio (ao contrario de `whatsapp_outbox`, sub-entrega 24/N), o que
tornou viavel enumerar os 4 pontos de escrita de `status` por completo (so
`"processing"`/`"done"`/`"error"` sao gravados). Achado desta sub-entrega,
nao corrigido: o campo `truncado` (gravado pelo trigger
`on_mcp_job_created` junto com `resultado`) nunca e copiado de volta por
`ler_job` -- ver comentario de `_OUTPUT_SCHEMAS` em `tools/registry.py`
para o levantamento completo, incluindo por que `resultado` (branch
"done") e documentado como `string` HOJE como um contrato de SNAPSHOT
sobre as 3 tools atuais de `_TOOLS_LONGAS`, nao uma garantia estrutural --
e `buscar_arquivos_acervo` (sub-entrega 26/N): decima tool, backed por
`tools/busca_acervo.py::buscar_acervo` (wrapper fino em
`tools/hermes_tools.py::_buscar_arquivos_acervo`), com `oneOf` de 2
branches (erro/sucesso) pela mesma forma de `consultar_historico_acoes`.
ACHADO desta sub-entrega: o campo `origem` de cada item NAO e sempre
string -- um dos 3 escritores da colecao `indice_artefatos` (anexo do
Copiloto, `main.py`) grava um DICT, nao string, entao o schema declara
`["string", "object"]`; e o campo `distancia` e uma GARANTIA ESTRUTURAL de
`null` sempre (`find_nearest` nunca recebe `distance_result_field`, e
`DocumentSnapshot` da biblioteca `google-cloud-firestore` 2.28.0 nunca tem
esse atributo) -- ver comentario de `_OUTPUT_SCHEMAS` em
`tools/registry.py` para o levantamento completo dos 3 escritores e por
que nenhum teste dedicado existia para esta tool antes desta sub-entrega
(lacuna fechada em `test_hermes_tools.py`).

Cinco frentes:
1. `TestOutputSchema` -- a função pura em `tools/registry.py`, incluindo
   paridade com TODO o catálogo real (não amostra): nenhuma tool além de
   `calculadora`, `buscar_contato`, `consultar_lista_compras`,
   `consultar_execucoes_agente`, `consultar_pedidos_agente`,
   `consultar_historico_acoes`, `obter_acao`,
   `listar_rascunhos_pendentes`, `consultar_job` e `buscar_arquivos_acervo`
   tem contrato publicado hoje.
2. `TestHandleToolsListOutputSchema` -- ponta a ponta via
   `mcp_server._handle_tools_list()`: `outputSchema` chega no catálogo
   publicado só para essas dez tools.
3. `TestIntegracaoHandleToolsCallStructuredContent` -- ponta a ponta via
   `mcp_server._handle_tools_call`: `structuredContent` chega no envelope
   de `tools/call` para `calculadora` (execução real, pura) e para
   `buscar_contato`/`consultar_lista_compras`/`consultar_execucoes_agente`/
   `consultar_pedidos_agente`/`consultar_historico_acoes`/`obter_acao`/
   `listar_rascunhos_pendentes`/`consultar_job`/`buscar_arquivos_acervo`
   (executor mockado -- as nove dependem de Firestore, então o teste cobre
   o MECANISMO, não a correção interna dos handlers, mesmo padrão já usado
   para `consultar_processo_sipac` abaixo), é sempre IGUAL ao dict que
   `content[0].text` serializa (mesma fonte, nunca diverge), bate com o
   `outputSchema` publicado campo a campo (para `consultar_historico_acoes`,
   `obter_acao`, `consultar_job` e `buscar_arquivos_acervo`, contra o
   branch `oneOf` correspondente à forma retornada), e nunca aparece para
   uma tool sem contrato publicado -- nem
   quando o resultado real também é um dict, nem quando o executor levanta
   uma exceção não tratada por ele mesmo, nem quando o handler devolve uma
   string crua de erro (caminho real de `consultar_lista_compras` para
   filtro inválido, ver `tools/hermes_tools.py::_consultar_lista_compras`).
4. `TestConsultarHistoricoAcoesFiltrosCoercao` -- exercita o HANDLER REAL
   (`hermes_tools._consultar_historico_acoes`, com
   `busca_grafo.buscar_tarefas` mockado, não `execute_tool` inteiro como
   na frente 3): regressão do achado de revisão adversarial da
   sub-entrega 14/N -- antes da correção, `area_tematica`/`status`/
   `data_limite_inicio`/`data_limite_fim` saíam do handler com o tipo cru
   que o chamador MCP mandasse (o schema publicado em `tools/list` não
   valida tipo escalar em runtime -- ver `registry.tipos_invalidos`),
   violando o `["string", "null"]` que o próprio `outputSchema` desta
   sub-entrega declara para eles.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import mcp_server
from tools import hermes_tools, registry
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
        # docstring de registry.output_schema). consultar_historico_acoes
        # (14/N) e obter_acao (15/N) ganharam contrato e saíram desta lista
        # -- ver test_consultar_historico_acoes_tem_schema_oneof_sucesso_e_erro
        # e test_obter_acao_tem_schema_oneof_sucesso_e_erro.
        for nome in ("criar_acao_no_sistema", "obter_estado_atual"):
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

    def test_consultar_pedidos_agente_tem_schema_com_campos_obrigatorios(self):
        schema = registry.output_schema("consultar_pedidos_agente")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["total", "pedidos"])
        self.assertEqual(set(schema["properties"].keys()), {"total", "pedidos"})
        self.assertFalse(schema["additionalProperties"])

        item = schema["properties"]["pedidos"]["items"]
        campos_item = {
            "id", "tipo", "status", "payload", "origem",
            "item_atencao_id", "acao_id", "criado_em", "atualizado_em",
        }
        # Todos os 9 campos são sempre chaves presentes no dict construído
        # por `agent_requests.listar_pendentes` (literal único, sem chave
        # condicional -- ao contrário de `truncado` em
        # consultar_lista_compras ou `erro` no nível superior de
        # buscar_contato).
        self.assertEqual(set(item["properties"].keys()), campos_item)
        self.assertEqual(set(item["required"]), campos_item)
        self.assertFalse(item["additionalProperties"])
        # status é enum de UM valor -- não por "só um escritor" (garantia
        # mais fraca, usada para justificar `tipo`/`origem` como string
        # solta), e sim porque a própria query de listar_pendentes filtra
        # por `status == "pendente"`: nenhum outro valor pode aparecer no
        # resultado, não importa quantos escritores a coleção tenha.
        self.assertEqual(item["properties"]["status"]["enum"], ["pendente"])
        # payload é um dict livre (conceitualmente por `tipo`, só um tipo
        # implementado hoje) -- deliberadamente sem "properties" aninhado,
        # mesmo espírito de `contadores` (consultar_execucoes_agente) e
        # `modelo_interacao` (buscar_contato).
        self.assertEqual(item["properties"]["payload"], {"type": "object"})
        # tipo/origem ficam string solta (não enum), ao contrário de
        # status: a garantia de valor único hoje vem só de "um único
        # escritor", não de um filtro de query -- um enum quebraria no dia
        # em que um segundo tipo de pedido aparecer.
        self.assertEqual(item["properties"]["tipo"], {"type": "string"})
        self.assertEqual(item["properties"]["origem"], {"type": "string"})
        # item_atencao_id/acao_id (nível superior) e criado_em/atualizado_em
        # são nullable -- sem coerção de tipo no ponto de leitura.
        for campo in ("item_atencao_id", "acao_id", "criado_em", "atualizado_em"):
            with self.subTest(campo=campo):
                self.assertEqual(item["properties"][campo]["type"], ["string", "null"])

    def test_consultar_historico_acoes_tem_schema_oneof_sucesso_e_erro(self):
        schema = registry.output_schema("consultar_historico_acoes")
        self.assertIsNotNone(schema)
        # Único schema do catálogo hoje que usa `oneOf` no nível superior --
        # sucesso e erro são duas formas com `required` DISJUNTOS, não uma
        # forma única com campos condicionalmente ausentes (ver comentário
        # de `_OUTPUT_SCHEMAS` em `tools/registry.py`).
        self.assertEqual(set(schema.keys()), {"oneOf"})
        self.assertEqual(len(schema["oneOf"]), 2)
        sucesso, erro = schema["oneOf"]

        self.assertEqual(sucesso["type"], "object")
        self.assertEqual(
            set(sucesso["required"]), {"total_retornado", "resultados", "filtros"}
        )
        self.assertEqual(
            set(sucesso["properties"].keys()), {"total_retornado", "resultados", "filtros"}
        )
        self.assertFalse(sucesso["additionalProperties"])

        item = sucesso["properties"]["resultados"]["items"]
        campos_item = {
            "id", "titulo", "status", "tipo_acao", "responsavel", "criado_em",
            "area", "data_limite", "processo_sei", "tags", "descricao", "notas",
            "sintese_demanda", "plano_acao", "acompanhamento_recente",
        }
        # Os 15 campos são sempre chaves presentes no dict literal montado
        # por `busca_grafo._formatar_resultado` -- nenhuma condicional.
        self.assertEqual(set(item["properties"].keys()), campos_item)
        self.assertEqual(set(item["required"]), campos_item)
        self.assertFalse(item["additionalProperties"])
        # plano_acao/acompanhamento_recente são as únicas listas com `items`
        # tipado (`string`) -- construídas por _formatar_resultado só
        # anexando strings formatadas, garantia de tipo tão forte quanto
        # criado_em; tags fica array solto (mesmo espírito de buscar_contato).
        self.assertEqual(item["properties"]["plano_acao"], {"type": "array", "items": {"type": "string"}})
        self.assertEqual(
            item["properties"]["acompanhamento_recente"],
            {"type": "array", "items": {"type": "string"}},
        )
        self.assertEqual(item["properties"]["tags"], {"type": "array"})

        filtros = sucesso["properties"]["filtros"]
        campos_filtros = {
            "query", "area_tematica", "status", "data_limite_inicio", "data_limite_fim",
        }
        self.assertEqual(set(filtros["properties"].keys()), campos_filtros)
        self.assertEqual(set(filtros["required"]), campos_filtros)
        self.assertFalse(filtros["additionalProperties"])
        # query é sempre string (str(args.get("query") or "")); os outros
        # quatro são args.get(campo) cru -- None quando o chamador omite.
        self.assertEqual(filtros["properties"]["query"], {"type": "string"})
        for campo in ("area_tematica", "status", "data_limite_inicio", "data_limite_fim"):
            with self.subTest(campo=campo):
                self.assertEqual(filtros["properties"][campo]["type"], ["string", "null"])

        self.assertEqual(erro["type"], "object")
        self.assertEqual(set(erro["required"]), {"erro", "resultados"})
        self.assertEqual(set(erro["properties"].keys()), {"erro", "resultados"})
        self.assertFalse(erro["additionalProperties"])
        self.assertEqual(erro["properties"]["erro"], {"type": "string"})
        # resultados no ramo de erro é SEMPRE lista vazia -- hardcoded pelo
        # próprio handler, não o que buscar_tarefas devolveu em erro.
        self.assertEqual(erro["properties"]["resultados"], {"type": "array", "maxItems": 0})

    def test_obter_acao_tem_schema_oneof_sucesso_e_erro(self):
        schema = registry.output_schema("obter_acao")
        self.assertIsNotNone(schema)
        # oneOf pelo mesmo motivo estrutural de consultar_historico_acoes
        # (sucesso e erro são formas com required disjuntos), mas aqui os
        # DOIS retornos de erro do handler (task_id ausente / ação não
        # encontrada) colapsam num único branch -- a diferença entre eles é
        # só a presença opcional de "status", não um segundo formato.
        self.assertEqual(set(schema.keys()), {"oneOf"})
        self.assertEqual(len(schema["oneOf"]), 2)
        sucesso, erro = schema["oneOf"]

        self.assertEqual(sucesso["type"], "object")
        campos_sucesso = {
            "id", "titulo", "descricao", "notas", "status", "area_tematica",
            "projeto", "data_limite", "data_inicio", "prazo_final",
            "horario_inicio", "horario_fim", "tags", "execution_lane",
            "degradation_count", "estrategia_objetivo_id", "contexto_agente",
            "plano_acao", "etapas_feitas", "etapas_totais", "anexos",
            "diario", "diario_total", "observacao",
        }
        self.assertEqual(set(sucesso["properties"].keys()), campos_sucesso)
        # Os 24 campos são sempre chaves presentes no dict literal montado
        # por `obter_acao` -- nenhuma condicional no nível superior (ao
        # contrário do item de `plano_acao`/`anexos`, ver abaixo).
        self.assertEqual(set(sucesso["required"]), campos_sucesso)
        self.assertFalse(sucesso["additionalProperties"])

        # execution_lane/degradation_count são os únicos dois campos com
        # coerção garantida pela própria função (subtarefas.derivar_lane
        # sempre str, subtarefas.degradacao_da_acao sempre int) -- os
        # demais campos "crus" da coleção `tarefas` (mesma coleção que
        # consultar_historico_acoes lê) são nullable aqui porque
        # `d.get(campo)` não tem valor padrão.
        self.assertEqual(sucesso["properties"]["execution_lane"], {"type": "string"})
        self.assertEqual(sucesso["properties"]["degradation_count"], {"type": "integer"})
        for campo in (
            "titulo", "status", "area_tematica", "projeto", "data_limite",
            "data_inicio", "prazo_final", "horario_inicio", "horario_fim",
            "estrategia_objetivo_id",
        ):
            with self.subTest(campo=campo):
                self.assertEqual(sucesso["properties"][campo]["type"], ["string", "null"])
        # descricao/notas usam `or ""` (sempre string, nunca null).
        for campo in ("descricao", "notas"):
            with self.subTest(campo=campo):
                self.assertEqual(sucesso["properties"][campo], {"type": "string"})
        self.assertEqual(sucesso["properties"]["tags"], {"type": "array"})
        # contexto_agente tem um único escritor (gatilho Firestore
        # processar_contexto_agente) com forma fixa, mas fica com contrato
        # solto de propósito -- mesmo espírito de modelo_interacao
        # (buscar_contato) e contadores (consultar_execucoes_agente).
        self.assertEqual(sucesso["properties"]["contexto_agente"], {"type": ["object", "null"]})

        etapa = sucesso["properties"]["plano_acao"]["items"]
        self.assertEqual(
            set(etapa["properties"].keys()),
            {"id", "texto", "estado", "data_prevista", "aguardando_de", "degradation_count"},
        )
        # aguardando_de/degradation_count só aparecem quando truthy no item
        # de origem -- por isso fora de required, ao contrário dos outros 4.
        self.assertEqual(set(etapa["required"]), {"id", "texto", "estado", "data_prevista"})
        self.assertFalse(etapa["additionalProperties"])
        self.assertEqual(etapa["properties"]["texto"], {"type": "string"})
        self.assertEqual(
            set(etapa["properties"]["estado"]["enum"]),
            {"pendente", "em_andamento", "aguardando_terceiro", "feito"},
        )
        # id da etapa é `i.get("id")` cru, sem passar por subtarefas.*_de --
        # documento legado de antes de subtarefas.py pode não ter a chave.
        self.assertEqual(etapa["properties"]["id"]["type"], ["string", "null"])
        self.assertEqual(etapa["properties"]["data_prevista"]["type"], ["string", "null"])

        anexo = sucesso["properties"]["anexos"]["items"]
        self.assertEqual(set(anexo["properties"].keys()), {"nome", "link", "drive_file_id"})
        self.assertEqual(set(anexo["required"]), {"nome", "link", "drive_file_id"})
        self.assertFalse(anexo["additionalProperties"])
        for campo in ("nome", "link", "drive_file_id"):
            with self.subTest(campo=campo):
                self.assertEqual(anexo["properties"][campo]["type"], ["string", "null"])

        diario_item = sucesso["properties"]["diario"]["items"]
        self.assertEqual(set(diario_item["properties"].keys()), {"data", "nota"})
        self.assertEqual(set(diario_item["required"]), {"data", "nota"})
        self.assertFalse(diario_item["additionalProperties"])
        # data é `str(e.get("data"))` sem "or" -- sempre string, mesmo para
        # None (viraria a string literal "None").
        self.assertEqual(diario_item["properties"]["data"], {"type": "string"})
        self.assertEqual(diario_item["properties"]["nota"]["type"], ["string", "null"])

        self.assertEqual(erro["type"], "object")
        self.assertEqual(set(erro["properties"].keys()), {"erro", "status"})
        # status só aparece na forma "não encontrada" -- por isso fora de
        # required, ao contrário de "erro", presente nos dois retornos.
        self.assertEqual(set(erro["required"]), {"erro"})
        self.assertFalse(erro["additionalProperties"])
        self.assertEqual(erro["properties"]["erro"], {"type": "string"})
        self.assertEqual(erro["properties"]["status"], {"type": "string", "enum": ["not_found"]})

    def test_listar_rascunhos_pendentes_tem_schema_com_campos_obrigatorios(self):
        schema = registry.output_schema("listar_rascunhos_pendentes")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["total", "rascunhos"])
        self.assertEqual(set(schema["properties"].keys()), {"total", "rascunhos"})
        self.assertFalse(schema["additionalProperties"])

        item = schema["properties"]["rascunhos"]["items"]
        campos_item = {
            "id", "status", "destinatario_nome", "to_number", "motivo",
            "trecho", "acao_id", "item_atencao_id", "origem", "tipo",
            "foi_editado", "envio_liberado_em", "criado_em",
            "telegram_message_id",
        }
        # Os 14 campos são sempre chaves presentes no dict construído por
        # `outbox_aprovacao.listar_rascunhos` (literal único, sem chave
        # condicional).
        self.assertEqual(set(item["properties"].keys()), campos_item)
        self.assertEqual(set(item["required"]), campos_item)
        self.assertFalse(item["additionalProperties"])
        # status é enum de 2 valores pelo filtro da própria query
        # (`.where("status", "in", [...])`), não por "escritor único" --
        # a coleção whatsapp_outbox tem vários escritores.
        self.assertEqual(
            item["properties"]["status"]["enum"],
            ["aguardando_aprovacao", "aguardando_janela"],
        )
        # foi_editado/trecho são coagidos na PRÓPRIA leitura
        # (bool(...)/str(...)[:120]), garantia mais forte que "sem tipo
        # cru vazando" -- por isso sem null.
        self.assertEqual(item["properties"]["foi_editado"], {"type": "boolean"})
        self.assertEqual(item["properties"]["trecho"], {"type": "string"})
        # telegram_message_id é o achado desta sub-entrega: inteiro (id do
        # Telegram), não string como os dois campos de data abaixo.
        self.assertEqual(item["properties"]["telegram_message_id"]["type"], ["integer", "null"])
        for campo in ("envio_liberado_em", "criado_em"):
            with self.subTest(campo=campo):
                self.assertEqual(item["properties"][campo]["type"], ["string", "null"])
        for campo in ("acao_id", "item_atencao_id"):
            with self.subTest(campo=campo):
                self.assertEqual(item["properties"][campo]["type"], ["string", "null"])
        # Achado de revisão Codex nesta PR: destinatario_nome/to_number/
        # motivo/origem são lidos com d.get(campo) CRU em
        # outbox_aprovacao.listar_rascunhos (sem segundo argumento, ao
        # contrário de tipo -- d.get("tipo", "outro")) -- um documento sem
        # esses campos (formato legado, edição manual) leria None. Por
        # isso nullable, ao contrário de tipo/trecho/foi_editado, que têm
        # garantia mais forte (default ou coerção no próprio ponto de
        # leitura).
        for campo in ("destinatario_nome", "to_number", "motivo", "origem"):
            with self.subTest(campo=campo):
                self.assertEqual(item["properties"][campo]["type"], ["string", "null"])
        self.assertEqual(item["properties"]["tipo"], {"type": "string"})

    def test_consultar_job_tem_schema_com_quatro_branches(self):
        schema = registry.output_schema("consultar_job")
        self.assertIsNotNone(schema)
        self.assertEqual(set(schema.keys()), {"oneOf"})
        # 4 branches: o maior número deste catálogo até agora (mais que os
        # 2 de consultar_historico_acoes/obter_acao) -- `ler_job` tem 5
        # `return`, mas os dois primeiros (sem job_id / não encontrado)
        # colapsam num único branch de erro com `status` opcional, mesmo
        # padrão de `obter_acao`.
        self.assertEqual(len(schema["oneOf"]), 4)
        erro, done, error, processing = schema["oneOf"]

        self.assertEqual(erro["type"], "object")
        self.assertEqual(erro["required"], ["erro"])
        self.assertEqual(set(erro["properties"].keys()), {"erro", "status"})
        self.assertEqual(erro["properties"]["status"], {"const": "not_found"})
        self.assertFalse(erro["additionalProperties"])

        self.assertEqual(done["required"], ["job_id", "tool", "status", "resultado"])
        self.assertEqual(done["properties"]["status"], {"const": "done"})
        # resultado é contrato de SNAPSHOT (as 3 tools de _TOOLS_LONGAS
        # hoje sempre devolvem string) -- ver comentário de
        # _OUTPUT_SCHEMAS para o caveat completo.
        self.assertEqual(done["properties"]["resultado"], {"type": "string"})
        self.assertFalse(done["additionalProperties"])

        self.assertEqual(error["required"], ["job_id", "tool", "status", "erro"])
        self.assertEqual(error["properties"]["status"], {"const": "error"})
        # erro_tipo/bloqueio_politica ficam FORA de required -- ler_job só
        # copia quando presentes no documento (achado: hoje as 4 escritas
        # de status=error sempre gravam erro_tipo, mas o leitor não
        # garante isso para jobs antigos).
        self.assertNotIn("erro_tipo", error["required"])
        self.assertNotIn("bloqueio_politica", error["required"])
        self.assertEqual(
            error["properties"]["erro_tipo"]["enum"],
            ["politica", "resultado_tool", "excecao", "erro_configuracao"],
        )
        # reason_code SEM null -- achado da 1a rodada de revisão
        # adversarial: `PolicyDecision.reason_code` é tipado `str` (nunca
        # `str | None`) e os 4 pontos de construção em `autonomy/policy.py`
        # sempre passam literal de string.
        self.assertEqual(
            error["properties"]["bloqueio_politica"]["properties"]["reason_code"],
            {"type": "string"},
        )
        self.assertFalse(error["additionalProperties"])

        self.assertEqual(processing["required"], ["job_id", "tool", "status", "mensagem"])
        self.assertEqual(processing["properties"]["status"], {"const": "processing"})
        self.assertFalse(processing["additionalProperties"])

    def test_buscar_arquivos_acervo_tem_schema_oneof_sucesso_e_erro(self):
        schema = registry.output_schema("buscar_arquivos_acervo")
        self.assertIsNotNone(schema)
        self.assertEqual(set(schema.keys()), {"oneOf"})
        self.assertEqual(len(schema["oneOf"]), 2)
        sucesso, erro = schema["oneOf"]

        self.assertEqual(sucesso["required"], ["total_retornado", "resultados"])
        self.assertFalse(sucesso["additionalProperties"])
        item = sucesso["properties"]["resultados"]["items"]
        self.assertEqual(
            set(item["properties"].keys()),
            {"id", "titulo", "trecho", "fonte", "url_drive", "task_id", "origem", "distancia"},
        )
        self.assertEqual(item["required"], list(item["properties"].keys()))
        self.assertFalse(item["additionalProperties"])
        # task_id pode faltar no documento (`data.get("task_id")` sem
        # default) -- nullable.
        self.assertEqual(item["properties"]["task_id"], {"type": ["string", "null"]})
        # ACHADO desta sub-entrega: um dos 3 escritores de `indice_
        # artefatos` (anexo do Copiloto) grava `origem` como dict, não
        # string -- ver comentário de `_OUTPUT_SCHEMAS`.
        self.assertEqual(item["properties"]["origem"], {"type": ["string", "object"]})
        # distancia é garantia ESTRUTURAL de null: `find_nearest` nunca
        # recebe `distance_result_field` neste código, e `DocumentSnapshot`
        # nunca tem esse atributo na biblioteca instalada.
        self.assertEqual(item["properties"]["distancia"], {"type": "null"})

        self.assertEqual(erro["required"], ["erro", "resultados"])
        self.assertEqual(erro["properties"]["resultados"], {"type": "array", "maxItems": 0})
        self.assertFalse(erro["additionalProperties"])

    def test_paridade_dez_tools_tem_output_schema_hoje(self):
        # Não por amostragem: para TODA tool do catálogo real (108 hoje --
        # `len(registry.list_tool_names())`; achado da revisão adversarial
        # da sub-entrega 25/N: "106" estava desatualizado desde antes
        # dela), output_schema devolve algo só para calculadora,
        # buscar_contato, consultar_lista_compras,
        # consultar_execucoes_agente, consultar_pedidos_agente,
        # consultar_historico_acoes, obter_acao, listar_rascunhos_pendentes,
        # consultar_job e buscar_arquivos_acervo -- prova que a lista
        # fechada não vazou para nenhuma outra tool por engano.
        com_schema = {
            "calculadora", "buscar_contato", "consultar_lista_compras",
            "consultar_execucoes_agente", "consultar_pedidos_agente",
            "consultar_historico_acoes", "obter_acao",
            "listar_rascunhos_pendentes", "consultar_job", "buscar_arquivos_acervo",
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

    def test_consultar_pedidos_agente_publica_output_schema(self):
        self.assertIn("outputSchema", self.catalogo["consultar_pedidos_agente"])
        self.assertEqual(
            self.catalogo["consultar_pedidos_agente"]["outputSchema"],
            registry.output_schema("consultar_pedidos_agente"),
        )

    def test_consultar_historico_acoes_publica_output_schema(self):
        self.assertIn("outputSchema", self.catalogo["consultar_historico_acoes"])
        self.assertEqual(
            self.catalogo["consultar_historico_acoes"]["outputSchema"],
            registry.output_schema("consultar_historico_acoes"),
        )
        # oneOf chega intacto no catálogo publicado, não achatado nem
        # reduzido a uma das duas formas.
        self.assertIn("oneOf", self.catalogo["consultar_historico_acoes"]["outputSchema"])

    def test_obter_acao_publica_output_schema(self):
        self.assertIn("outputSchema", self.catalogo["obter_acao"])
        self.assertEqual(
            self.catalogo["obter_acao"]["outputSchema"],
            registry.output_schema("obter_acao"),
        )
        # oneOf chega intacto no catálogo publicado, não achatado nem
        # reduzido a uma das duas formas.
        self.assertIn("oneOf", self.catalogo["obter_acao"]["outputSchema"])

    def test_listar_rascunhos_pendentes_publica_output_schema(self):
        self.assertIn("outputSchema", self.catalogo["listar_rascunhos_pendentes"])
        self.assertEqual(
            self.catalogo["listar_rascunhos_pendentes"]["outputSchema"],
            registry.output_schema("listar_rascunhos_pendentes"),
        )

    def test_consultar_job_publica_output_schema(self):
        self.assertIn("outputSchema", self.catalogo["consultar_job"])
        self.assertEqual(
            self.catalogo["consultar_job"]["outputSchema"],
            registry.output_schema("consultar_job"),
        )
        # oneOf chega intacto no catálogo publicado, não achatado nem
        # reduzido a uma das quatro formas.
        self.assertIn("oneOf", self.catalogo["consultar_job"]["outputSchema"])
        self.assertEqual(len(self.catalogo["consultar_job"]["outputSchema"]["oneOf"]), 4)

    def test_buscar_arquivos_acervo_publica_output_schema(self):
        self.assertIn("outputSchema", self.catalogo["buscar_arquivos_acervo"])
        self.assertEqual(
            self.catalogo["buscar_arquivos_acervo"]["outputSchema"],
            registry.output_schema("buscar_arquivos_acervo"),
        )
        self.assertIn("oneOf", self.catalogo["buscar_arquivos_acervo"]["outputSchema"])
        self.assertEqual(len(self.catalogo["buscar_arquivos_acervo"]["outputSchema"]["oneOf"]), 2)

    def test_nenhuma_outra_tool_publicada_tem_output_schema(self):
        esperadas = {
            "calculadora", "buscar_contato", "consultar_lista_compras",
            "consultar_execucoes_agente", "consultar_pedidos_agente",
            "consultar_historico_acoes", "obter_acao",
            "listar_rascunhos_pendentes", "consultar_job", "buscar_arquivos_acervo",
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
            "consultar_execucoes_agente", "consultar_pedidos_agente",
            "consultar_historico_acoes", "obter_acao",
            "listar_rascunhos_pendentes", "consultar_job", "buscar_arquivos_acervo",
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

    def test_consultar_pedidos_agente_sucesso_leva_structured_content_igual_ao_content(self):
        # `agent_requests.listar_pendentes` real depende de Firestore
        # (`ctx.db.collection("agent_requests")...`); o executor é mockado
        # aqui com uma forma real que a função produz (ver
        # `agent_requests.py`), mesmo padrão de
        # buscar_contato/consultar_lista_compras/consultar_execucoes_agente
        # acima -- testa o MECANISMO, não a lógica de consulta em si.
        esperado = {
            "total": 1,
            "pedidos": [
                {
                    "id": "consolidar_audio:item-1",
                    "tipo": "consolidar_audio",
                    "status": "pendente",
                    "payload": {
                        "chat_id": "5511999999999@c.us",
                        "chat_name": "Fulano",
                        "mensagem_ids": ["wamid-1", "wamid-2"],
                        "acao_id": None,
                        "item_atencao_id": "item-1",
                    },
                    "origem": "atencao_whatsapp.audio_relevante",
                    "item_atencao_id": "item-1",
                    "acao_id": None,
                    "criado_em": "2026-09-13T18:00:00+00:00",
                    "atualizado_em": "2026-09-13T18:00:00+00:00",
                },
            ],
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_pedidos_agente", "arguments": {}}, ctx=_ctx()
            )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_consultar_pedidos_agente_lista_vazia_tambem_leva_structured_content(self):
        esperado = {"total": 0, "pedidos": []}
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_pedidos_agente", "arguments": {"tipo": "consolidar_audio"}},
                ctx=_ctx(),
            )
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)

    def test_consultar_pedidos_agente_structured_content_bate_com_o_output_schema_publicado(self):
        schema = registry.output_schema("consultar_pedidos_agente")
        propriedades = schema["properties"]
        item_props = propriedades["pedidos"]["items"]["properties"]
        mock_retorno = {
            "total": 1,
            "pedidos": [
                {
                    "id": "consolidar_audio:item-2",
                    "tipo": "consolidar_audio",
                    "status": "pendente",
                    "payload": {
                        "chat_id": "5511988888888@c.us",
                        "chat_name": "Ciclana",
                        "mensagem_ids": ["wamid-3"],
                        "acao_id": "acao-9",
                        "item_atencao_id": "item-2",
                    },
                    "origem": "atencao_whatsapp.audio_relevante",
                    "item_atencao_id": "item-2",
                    "acao_id": "acao-9",
                    "criado_em": "2026-09-13T18:05:00+00:00",
                    "atualizado_em": "2026-09-13T18:05:00+00:00",
                },
            ],
        }
        with patch.object(mcp_server, "execute_tool", return_value=mock_retorno):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_pedidos_agente", "arguments": {}}, ctx=_ctx()
            )
        estruturado = resultado["structuredContent"]
        for campo in schema["required"]:
            self.assertIn(campo, estruturado)
        for campo in estruturado:
            self.assertIn(campo, propriedades, f"campo '{campo}' fora do outputSchema")
        for pedido in estruturado["pedidos"]:
            for campo in pedido:
                self.assertIn(campo, item_props, f"campo '{campo}' fora do item declarado")

    def test_consultar_historico_acoes_sucesso_leva_structured_content_igual_ao_content(self):
        # `busca_grafo.buscar_tarefas` real depende de Firestore
        # (`firestore.Client()...`); o executor é mockado aqui com uma forma
        # real que `_consultar_historico_acoes` produz no caminho de sucesso
        # (ver `tools/hermes_tools.py::_consultar_historico_acoes` e
        # `tools/busca_grafo.py::_formatar_resultado`), mesmo padrão de
        # buscar_contato/consultar_lista_compras/consultar_execucoes_agente/
        # consultar_pedidos_agente acima -- testa o MECANISMO, não a lógica
        # de busca/ranqueamento em si.
        esperado = {
            "total_retornado": 1,
            "resultados": [
                {
                    "id": "acao-1",
                    "titulo": "Contratação de mobiliário para som e eventos",
                    "status": "em andamento",
                    "tipo_acao": "processo",
                    "responsavel": "André",
                    "criado_em": "2026-08-01",
                    "area": "FINANCEIRO",
                    "data_limite": "2026-09-30",
                    "processo_sei": "23543.000286/2026-39",
                    "tags": ["compras", "eventos"],
                    "descricao": "Aquisição de mobiliário para eventos institucionais.",
                    "notas": "Aguardando parecer jurídico.",
                    "sintese_demanda": "Mobiliário para auditório.",
                    "plano_acao": ["✓ Elaborar TR", "○ Publicar edital"],
                    "acompanhamento_recente": ["[2026-09-01] TR enviado para revisão"],
                },
            ],
            "filtros": {
                "query": "mobiliário eventos",
                "area_tematica": None,
                "status": None,
                "data_limite_inicio": None,
                "data_limite_fim": None,
            },
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_historico_acoes", "arguments": {"query": "mobiliário eventos"}},
                ctx=_ctx(),
            )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_consultar_historico_acoes_lista_vazia_tambem_leva_structured_content(self):
        esperado = {
            "total_retornado": 0,
            "resultados": [],
            "filtros": {
                "query": "termo sem correspondência",
                "area_tematica": "TI",
                "status": "concluída",
                "data_limite_inicio": "2026-01-01",
                "data_limite_fim": "2026-12-31",
            },
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "consultar_historico_acoes",
                    "arguments": {"query": "termo sem correspondência"},
                },
                ctx=_ctx(),
            )
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)

    def test_consultar_historico_acoes_erro_tambem_leva_structured_content(self):
        # Caminho real de erro: `buscar_tarefas` devolve `erro` (falha na
        # consulta base ao Firestore, ou exceção capturada dentro dela
        # mesma) -- `_consultar_historico_acoes` propaga como
        # `{"erro": ..., "resultados": []}`, a SEGUNDA forma do `oneOf`.
        # Ainda é um dict, então ainda leva structuredContent -- ao
        # contrário de `consultar_lista_compras` com filtro inválido, cujo
        # erro real é uma STRING "ERRO|...", não um dict.
        esperado = {
            "erro": "[ERRO BuscaGrafo] ServiceUnavailable: Firestore indisponível",
            "resultados": [],
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_historico_acoes", "arguments": {"query": "qualquer coisa"}},
                ctx=_ctx(),
            )
        self.assertTrue(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_consultar_historico_acoes_structured_content_bate_com_o_output_schema_publicado(self):
        # Paridade campo a campo contra o branch `oneOf` correspondente à
        # forma efetivamente devolvida (sucesso ou erro) -- diferente das
        # tools anteriores (uma forma só), aqui escolher o branch errado
        # deixaria passar um campo que não pertence a NENHUMA das duas
        # formas reais.
        schema = registry.output_schema("consultar_historico_acoes")
        sucesso_schema, erro_schema = schema["oneOf"]

        mock_sucesso = {
            "total_retornado": 1,
            "resultados": [
                {
                    "id": "acao-2",
                    "titulo": "Relatório financeiro",
                    "status": "concluída",
                    "tipo_acao": "tarefa",
                    "responsavel": "André",
                    "criado_em": "2026-07-15",
                    "area": "FINANCEIRO",
                    "data_limite": "2026-07-30",
                    "processo_sei": "",
                    "tags": [],
                    "descricao": "",
                    "notas": "",
                    "sintese_demanda": "",
                    "plano_acao": [],
                    "acompanhamento_recente": [],
                },
            ],
            "filtros": {
                "query": "relatório financeiro",
                "area_tematica": "FINANCEIRO",
                "status": None,
                "data_limite_inicio": None,
                "data_limite_fim": None,
            },
        }
        with patch.object(mcp_server, "execute_tool", return_value=mock_sucesso):
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "consultar_historico_acoes",
                    "arguments": {"query": "relatório financeiro"},
                },
                ctx=_ctx(),
            )
        estruturado = resultado["structuredContent"]
        item_props = sucesso_schema["properties"]["resultados"]["items"]["properties"]
        for campo in sucesso_schema["required"]:
            self.assertIn(campo, estruturado)
        for campo in estruturado:
            self.assertIn(
                campo, sucesso_schema["properties"],
                f"campo '{campo}' fora do branch de sucesso do outputSchema",
            )
        for item in estruturado["resultados"]:
            for campo in item:
                self.assertIn(campo, item_props, f"campo '{campo}' fora do item declarado")

        mock_erro = {"erro": "[ERRO TECNICO BuscaGrafo] Timeout: ...", "resultados": []}
        with patch.object(mcp_server, "execute_tool", return_value=mock_erro):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_historico_acoes", "arguments": {"query": "x"}}, ctx=_ctx()
            )
        estruturado = resultado["structuredContent"]
        for campo in erro_schema["required"]:
            self.assertIn(campo, estruturado)
        for campo in estruturado:
            self.assertIn(
                campo, erro_schema["properties"],
                f"campo '{campo}' fora do branch de erro do outputSchema",
            )

    def test_obter_acao_sucesso_leva_structured_content_igual_ao_content(self):
        # `obter_acao` real depende de Firestore
        # (`ctx.db.collection("tarefas").document(task_id).get()`); o
        # executor é mockado aqui com uma forma real que o handler produz
        # (ver `tools/hermes_tools.py::obter_acao`), mesmo padrão das tools
        # acima -- testa o MECANISMO, não a lógica de leitura em si.
        esperado = {
            "id": "acao-3",
            "titulo": "Renovar certificado SSL",
            "descricao": "Certificado vence em 30 dias.",
            "notas": "",
            "status": "em andamento",
            "area_tematica": "TI",
            "projeto": None,
            "data_limite": "2026-10-01",
            "data_inicio": None,
            "prazo_final": None,
            "horario_inicio": None,
            "horario_fim": None,
            "tags": ["infra"],
            "execution_lane": "avanco",
            "degradation_count": 0,
            "estrategia_objetivo_id": None,
            "contexto_agente": None,
            "plano_acao": [
                {"id": "abc12345", "texto": "Gerar CSR", "estado": "feito", "data_prevista": None},
            ],
            "etapas_feitas": 1,
            "etapas_totais": 1,
            "anexos": [],
            "diario": [{"data": "2026-09-01T00:00:00+00:00", "nota": "Iniciado"}],
            "diario_total": 1,
            "observacao": "Campos completos, sem truncamento.",
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "obter_acao", "arguments": {"task_id": "acao-3"}}, ctx=_ctx()
            )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_obter_acao_nao_encontrada_tambem_leva_structured_content(self):
        # Segunda forma do branch de erro: "status" presente.
        esperado = {"erro": "Acao 'inexistente' nao encontrada.", "status": "not_found"}
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "obter_acao", "arguments": {"task_id": "inexistente"}}, ctx=_ctx()
            )
        self.assertTrue(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_obter_acao_sem_task_id_tambem_leva_structured_content(self):
        # Primeira forma do branch de erro: "status" AUSENTE (a diferença
        # entre os dois retornos de erro do handler é só essa presença
        # opcional -- por isso um único branch de erro no oneOf, não dois).
        esperado = {"erro": "Informe task_id."}
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "obter_acao", "arguments": {}}, ctx=_ctx()
            )
        self.assertTrue(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertNotIn("status", resultado["structuredContent"])

    def test_obter_acao_structured_content_bate_com_o_output_schema_publicado(self):
        # Paridade campo a campo contra o branch `oneOf` correspondente à
        # forma efetivamente devolvida (sucesso ou erro), mesmo padrão de
        # consultar_historico_acoes acima.
        schema = registry.output_schema("obter_acao")
        sucesso_schema, erro_schema = schema["oneOf"]

        mock_sucesso = {
            "id": "acao-4",
            "titulo": None,
            "descricao": "",
            "notas": "",
            "status": None,
            "area_tematica": None,
            "projeto": None,
            "data_limite": None,
            "data_inicio": None,
            "prazo_final": None,
            "horario_inicio": None,
            "horario_fim": None,
            "tags": [],
            "execution_lane": "continuo",
            "degradation_count": 0,
            "estrategia_objetivo_id": None,
            "contexto_agente": {
                "resumo": "Migração de servidor em andamento.",
                "pessoas_chave": [],
                "onde_esta_o_codigo": None,
                "ultimas_decisoes": [],
                "travas": [],
                "atualizado_em": "2026-09-01T00:00:00+00:00",
            },
            "plano_acao": [
                {
                    "id": None,
                    "texto": "Etapa legada sem id",
                    "estado": "aguardando_terceiro",
                    "data_prevista": "2026-09-20",
                    "aguardando_de": "André",
                    "degradation_count": 2,
                },
            ],
            "etapas_feitas": 0,
            "etapas_totais": 1,
            "anexos": [
                {"nome": None, "link": None, "drive_file_id": None},
            ],
            "diario": [{"data": "None", "nota": None}],
            "diario_total": 1,
            "observacao": "Campos completos, sem truncamento.",
        }
        with patch.object(mcp_server, "execute_tool", return_value=mock_sucesso):
            resultado = mcp_server._handle_tools_call(
                {"name": "obter_acao", "arguments": {"task_id": "acao-4"}}, ctx=_ctx()
            )
        estruturado = resultado["structuredContent"]
        etapa_props = sucesso_schema["properties"]["plano_acao"]["items"]["properties"]
        anexo_props = sucesso_schema["properties"]["anexos"]["items"]["properties"]
        for campo in sucesso_schema["required"]:
            self.assertIn(campo, estruturado)
        for campo in estruturado:
            self.assertIn(
                campo, sucesso_schema["properties"],
                f"campo '{campo}' fora do branch de sucesso do outputSchema",
            )
        for etapa in estruturado["plano_acao"]:
            for campo in etapa:
                self.assertIn(campo, etapa_props, f"campo '{campo}' fora da etapa declarada")
        for anexo in estruturado["anexos"]:
            for campo in anexo:
                self.assertIn(campo, anexo_props, f"campo '{campo}' fora do anexo declarado")

        mock_erro = {"erro": "Acao 'x' nao encontrada.", "status": "not_found"}
        with patch.object(mcp_server, "execute_tool", return_value=mock_erro):
            resultado = mcp_server._handle_tools_call(
                {"name": "obter_acao", "arguments": {"task_id": "x"}}, ctx=_ctx()
            )
        estruturado = resultado["structuredContent"]
        for campo in erro_schema["required"]:
            self.assertIn(campo, estruturado)
        for campo in estruturado:
            self.assertIn(
                campo, erro_schema["properties"],
                f"campo '{campo}' fora do branch de erro do outputSchema",
            )

    def test_listar_rascunhos_pendentes_sucesso_leva_structured_content_igual_ao_content(self):
        # `outbox_aprovacao.listar_rascunhos` real depende de Firestore
        # (`ctx.db.collection("whatsapp_outbox")...`); o executor é
        # mockado aqui com uma forma real que a função produz (ver
        # `outbox_aprovacao.py`), mesmo padrão das demais tools acima --
        # testa o MECANISMO, não a lógica de consulta em si.
        esperado = {
            "total": 1,
            "rascunhos": [
                {
                    "id": "r_promovido",
                    "status": "aguardando_janela",
                    "destinatario_nome": "Carla",
                    "to_number": "5511999999999@c.us",
                    "motivo": "Confirmação de reunião",
                    "trecho": "Olá Carla, confirma a reunião de amanhã?",
                    "acao_id": None,
                    "item_atencao_id": None,
                    "origem": "claude",
                    "tipo": "confirmacao_reuniao",
                    "foi_editado": False,
                    "envio_liberado_em": "2026-09-23T14:08:00+00:00",
                    "criado_em": "2026-09-23T14:00:00+00:00",
                    "telegram_message_id": 4242,
                },
            ],
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "listar_rascunhos_pendentes", "arguments": {}}, ctx=_ctx()
            )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_listar_rascunhos_pendentes_lista_vazia_tambem_leva_structured_content(self):
        esperado = {"total": 0, "rascunhos": []}
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "listar_rascunhos_pendentes", "arguments": {"limite": 5}},
                ctx=_ctx(),
            )
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)

    def test_listar_rascunhos_pendentes_structured_content_bate_com_o_output_schema_publicado(self):
        schema = registry.output_schema("listar_rascunhos_pendentes")
        propriedades = schema["properties"]
        item_props = propriedades["rascunhos"]["items"]["properties"]
        # telegram_message_id ausente (envio ao Telegram falhou ou não
        # havia token/chat configurado) -- vira `None` no dict, não some
        # da resposta (mesmo padrão de acao_id/item_atencao_id ausentes).
        mock_retorno = {
            "total": 1,
            "rascunhos": [
                {
                    "id": "r_regular",
                    "status": "aguardando_aprovacao",
                    "destinatario_nome": "Pedro",
                    "to_number": "5511988888888@c.us",
                    "motivo": "Aviso urgente",
                    "trecho": "Mensagem regular sem promoção",
                    "acao_id": "acao-9",
                    "item_atencao_id": "item-2",
                    "origem": "atencao_whatsapp",
                    "tipo": "outro",
                    "foi_editado": True,
                    "envio_liberado_em": None,
                    "criado_em": "2026-09-23T13:00:00+00:00",
                    "telegram_message_id": None,
                },
            ],
        }
        with patch.object(mcp_server, "execute_tool", return_value=mock_retorno):
            resultado = mcp_server._handle_tools_call(
                {"name": "listar_rascunhos_pendentes", "arguments": {}}, ctx=_ctx()
            )
        estruturado = resultado["structuredContent"]
        for campo in schema["required"]:
            self.assertIn(campo, estruturado)
        for campo in estruturado:
            self.assertIn(campo, propriedades, f"campo '{campo}' fora do outputSchema")
        for rascunho in estruturado["rascunhos"]:
            for campo in rascunho:
                self.assertIn(campo, item_props, f"campo '{campo}' fora do item declarado")

    def test_consultar_job_sem_job_id_leva_structured_content(self):
        # `mcp_jobs.ler_job`, ramo 1: sem `job_id`, checagem antes de
        # qualquer leitura ao Firestore -- só `erro`, sem `status`.
        esperado = {"erro": "job_id obrigatorio."}
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_job", "arguments": {"job_id": ""}}, ctx=_ctx()
            )
        self.assertTrue(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertNotIn("status", resultado["structuredContent"])

    def test_consultar_job_nao_encontrado_leva_structured_content(self):
        # Ramo 2: job inexistente OU uid divergente -- MESMA resposta para
        # os dois casos (deliberado, ver comentário de `_OUTPUT_SCHEMAS`).
        esperado = {"erro": "Job 'mcpjob-xyz' nao encontrado.", "status": "not_found"}
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_job", "arguments": {"job_id": "mcpjob-xyz"}}, ctx=_ctx()
            )
        self.assertTrue(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)

    def test_consultar_job_done_leva_structured_content_igual_ao_content(self):
        # Ramo 3: `status == "done"`. `resultado` string -- as 3 únicas
        # tools de `_TOOLS_LONGAS` hoje sempre devolvem string (ver
        # comentário de `_OUTPUT_SCHEMAS`).
        esperado = {
            "job_id": "mcpjob-abc123",
            "tool": "gerar_relatorio",
            "status": "done",
            "resultado": '{"report_id": "r1", "titulo": "X", "secoes": ["A"], "status": "gerado"}',
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_job", "arguments": {"job_id": "mcpjob-abc123"}}, ctx=_ctx()
            )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_consultar_job_error_leva_structured_content(self):
        # Ramo 4: `status == "error"`, com os dois campos opcionais
        # (`erro_tipo`/`bloqueio_politica`) presentes -- caso do bloqueio
        # pela política de autonomia, único caminho que grava
        # `bloqueio_politica`.
        esperado = {
            "job_id": "mcpjob-blocked",
            "tool": "buscar_e_analisar_email",
            "status": "error",
            "erro": "Ação bloqueada pela política de autonomia vigente.",
            "erro_tipo": "politica",
            "bloqueio_politica": {"decision": "deny", "reason_code": "fora_do_escopo"},
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_job", "arguments": {"job_id": "mcpjob-blocked"}}, ctx=_ctx()
            )
        self.assertTrue(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)

    def test_consultar_job_processing_leva_structured_content(self):
        # Ramo 5 (único `status` alcançável fora de done/error/not_found):
        # `"processing"`, com `mensagem` literal fixa do próprio `ler_job`.
        esperado = {
            "job_id": "mcpjob-ongoing",
            "tool": "ler_documento_na_integra",
            "status": "processing",
            "mensagem": "Ainda processando. Consulte de novo em alguns segundos com o mesmo job_id.",
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "consultar_job", "arguments": {"job_id": "mcpjob-ongoing"}}, ctx=_ctx()
            )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)

    def test_consultar_job_structured_content_bate_com_o_output_schema_publicado(self):
        # Paridade campo a campo contra o branch `oneOf` correspondente à
        # forma efetivamente devolvida, mesmo padrão de
        # `consultar_historico_acoes`/`obter_acao` acima -- aqui com 4
        # branches em vez de 2, então localiza o branch pelo valor de
        # `status` (ou a ausência dele, para o ramo sem `job_id`).
        schema = registry.output_schema("consultar_job")
        branches_por_status = {}
        for branch in schema["oneOf"]:
            status_prop = branch["properties"].get("status")
            # O branch de erro tem `status` OPCIONAL (mesmo padrão de
            # `obter_acao`): serve tanto para "not_found" quanto para o
            # ramo sem `job_id`, que não tem `status` nenhum -- registra
            # o mesmo branch sob as duas chaves quando `status` não é
            # `required` nele.
            if status_prop and "status" not in branch.get("required", []):
                branches_por_status[status_prop["const"]] = branch
                branches_por_status[None] = branch
            elif status_prop:
                branches_por_status[status_prop["const"]] = branch
            else:
                branches_por_status[None] = branch

        casos = [
            {"erro": "job_id obrigatorio."},
            {"erro": "Job 'x' nao encontrado.", "status": "not_found"},
            {"job_id": "j1", "tool": "gerar_relatorio", "status": "done", "resultado": "texto"},
            {
                "job_id": "j2", "tool": "gerar_relatorio", "status": "error",
                "erro": "falhou", "erro_tipo": "excecao",
            },
            {"job_id": "j3", "tool": "gerar_relatorio", "status": "processing", "mensagem": "..."},
        ]
        for mock_retorno in casos:
            with self.subTest(status=mock_retorno.get("status")):
                with patch.object(mcp_server, "execute_tool", return_value=mock_retorno):
                    resultado = mcp_server._handle_tools_call(
                        {"name": "consultar_job", "arguments": {"job_id": "x"}}, ctx=_ctx()
                    )
                estruturado = resultado["structuredContent"]
                branch = branches_por_status[mock_retorno.get("status")]
                for campo in branch["required"]:
                    self.assertIn(campo, estruturado)
                for campo in estruturado:
                    self.assertIn(
                        campo, branch["properties"],
                        f"campo '{campo}' fora do branch de status={mock_retorno.get('status')!r}",
                    )

    def test_buscar_arquivos_acervo_sucesso_leva_structured_content_igual_ao_content(self):
        # `buscar_arquivos_acervo` real depende de embedding (Gemini) e
        # Firestore (`find_nearest`); o executor é mockado aqui com uma
        # forma real que o handler produz (ver
        # `tools/hermes_tools.py::_buscar_arquivos_acervo`), mesmo padrão
        # das tools acima -- testa o MECANISMO, não a busca vetorial em si.
        esperado = {
            "total_retornado": 1,
            "resultados": [{
                "id": "art-1",
                "titulo": "Manual de Onboarding",
                "trecho": "Resumo executivo do manual.",
                "fonte": "Drive",
                "url_drive": "https://drive.google.com/file/d/abc/view",
                "task_id": "acao-9",
                "origem": "acervo",
                "distancia": None,
            }],
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "buscar_arquivos_acervo", "arguments": {"query": "onboarding"}}, ctx=_ctx()
            )
        self.assertFalse(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertEqual(json.loads(resultado["content"][0]["text"]), esperado)

    def test_buscar_arquivos_acervo_com_origem_dict_leva_structured_content(self):
        # ACHADO desta sub-entrega: um dos 3 escritores de `indice_
        # artefatos` (anexo do Copiloto) grava `origem` como dict -- o
        # envelope não normaliza nem rejeita, repassa como veio.
        esperado = {
            "total_retornado": 1,
            "resultados": [{
                "id": "art-2",
                "titulo": "sem título",
                "trecho": "",
                "fonte": "",
                "url_drive": "",
                "task_id": None,
                "origem": {"modulo": "copiloto", "id_origem": "sessao-1"},
                "distancia": None,
            }],
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "buscar_arquivos_acervo", "arguments": {"query": "x"}}, ctx=_ctx()
            )
        self.assertFalse(resultado["isError"])
        self.assertEqual(resultado["structuredContent"], esperado)
        self.assertIsInstance(resultado["structuredContent"]["resultados"][0]["origem"], dict)

    def test_buscar_arquivos_acervo_erro_tambem_leva_structured_content(self):
        esperado = {
            "erro": "[ERRO TÉCNICO FindNearest] ValueError: falhou",
            "resultados": [],
        }
        with patch.object(mcp_server, "execute_tool", return_value=esperado):
            resultado = mcp_server._handle_tools_call(
                {"name": "buscar_arquivos_acervo", "arguments": {"query": "x"}}, ctx=_ctx()
            )
        self.assertTrue(resultado["isError"])
        self.assertIn("structuredContent", resultado)
        self.assertEqual(resultado["structuredContent"], esperado)

    def test_buscar_arquivos_acervo_structured_content_bate_com_o_output_schema_publicado(self):
        # Paridade campo a campo contra o branch `oneOf` correspondente à
        # forma efetivamente devolvida, mesmo padrão de
        # `consultar_historico_acoes`/`obter_acao` acima.
        schema = registry.output_schema("buscar_arquivos_acervo")
        sucesso_schema, erro_schema = schema["oneOf"]

        mock_sucesso = {
            "total_retornado": 1,
            "resultados": [{
                "id": "art-3",
                "titulo": "T",
                "trecho": "R",
                "fonte": "F",
                "url_drive": "",
                "task_id": None,
                "origem": "acervo",
                "distancia": None,
            }],
        }
        with patch.object(mcp_server, "execute_tool", return_value=mock_sucesso):
            resultado = mcp_server._handle_tools_call(
                {"name": "buscar_arquivos_acervo", "arguments": {"query": "x"}}, ctx=_ctx()
            )
        estruturado = resultado["structuredContent"]
        self.assertEqual(set(estruturado.keys()), set(sucesso_schema["properties"].keys()))
        item_schema = sucesso_schema["properties"]["resultados"]["items"]
        self.assertEqual(
            set(estruturado["resultados"][0].keys()), set(item_schema["properties"].keys()),
        )

        mock_erro = {"erro": "falhou", "resultados": []}
        with patch.object(mcp_server, "execute_tool", return_value=mock_erro):
            resultado = mcp_server._handle_tools_call(
                {"name": "buscar_arquivos_acervo", "arguments": {"query": "x"}}, ctx=_ctx()
            )
        estruturado = resultado["structuredContent"]
        self.assertEqual(set(estruturado.keys()), set(erro_schema["properties"].keys()))

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


class TestConsultarHistoricoAcoesFiltrosCoercao(unittest.TestCase):
    """Regressão do achado de revisão adversarial da sub-entrega 14/N.

    Diferente de `TestIntegracaoHandleToolsCallStructuredContent` acima
    (que mocka `execute_tool` inteiro, nunca exercitando o corpo real de
    `_consultar_historico_acoes`), estes testes chamam o HANDLER REAL, só
    mockando `busca_grafo.buscar_tarefas` (a única dependência de
    Firestore dele) -- para provar que a própria função, não um mock,
    coage `area_tematica`/`status`/`data_limite_inicio`/`data_limite_fim`
    para `str`/`None` antes de ecoá-los em `filtros`, como
    `["string", "null"]` (o `outputSchema` publicado) exige.

    `test_busca_recebe_valores_crus_nao_coagidos` cobre o achado da 2a
    rodada de revisão adversarial sobre a 1a versão desta correção: a
    coerção tem que acontecer SÓ no eco de `filtros`, nunca nos parâmetros
    passados para `buscar_tarefas` -- ver docstring de
    `hermes_tools._filtro_str_ou_none` para o porquê (valor falsy-mas-não-
    None, ex. `False`/`[]`, vira string truthy, e vários pontos de
    `busca_grafo.py` decidem se aplicam um filtro por truthiness pura da
    mesma variável -- coagir cedo demais faria um filtro hoje ignorado
    passar a excluir tudo).
    """

    def test_filtros_com_tipo_nao_string_sao_coagidos_para_string(self):
        with patch(
            "tools.busca_grafo.buscar_tarefas",
            return_value={"resultados": [], "erro": None},
        ):
            resultado = hermes_tools._consultar_historico_acoes(
                _ctx(),
                {
                    "query": "x",
                    "area_tematica": 5,
                    "status": ["a", "b"],
                    "data_limite_inicio": 20260101,
                    "data_limite_fim": False,
                },
            )
        self.assertEqual(
            resultado["filtros"],
            {
                "query": "x",
                "area_tematica": "5",
                "status": "['a', 'b']",
                "data_limite_inicio": "20260101",
                "data_limite_fim": "False",
            },
        )
        for campo, valor in resultado["filtros"].items():
            with self.subTest(campo=campo):
                self.assertIsInstance(valor, str)

    def test_filtros_omitidos_continuam_none_nao_viram_string_none(self):
        # None tem que continuar None (não virar a string "None") -- só o
        # TIPO errado é coagido, a AUSÊNCIA continua ausência.
        with patch(
            "tools.busca_grafo.buscar_tarefas",
            return_value={"resultados": [], "erro": None},
        ):
            resultado = hermes_tools._consultar_historico_acoes(_ctx(), {"query": "x"})
        for campo in ("area_tematica", "status", "data_limite_inicio", "data_limite_fim"):
            with self.subTest(campo=campo):
                self.assertIsNone(resultado["filtros"][campo])

    def test_filtros_ja_string_passam_intactos(self):
        with patch(
            "tools.busca_grafo.buscar_tarefas",
            return_value={"resultados": [], "erro": None},
        ):
            resultado = hermes_tools._consultar_historico_acoes(
                _ctx(),
                {
                    "query": "x",
                    "area_tematica": "FINANCEIRO",
                    "status": "concluída",
                    "data_limite_inicio": "2026-01-01",
                    "data_limite_fim": "2026-12-31",
                },
            )
        self.assertEqual(resultado["filtros"]["area_tematica"], "FINANCEIRO")
        self.assertEqual(resultado["filtros"]["status"], "concluída")
        self.assertEqual(resultado["filtros"]["data_limite_inicio"], "2026-01-01")
        self.assertEqual(resultado["filtros"]["data_limite_fim"], "2026-12-31")

    def test_filtros_coagidos_ainda_batem_com_tipos_do_output_schema_publicado(self):
        # Prova final, sem depender de lib externa de validação de
        # JSON Schema (não usada em nenhum outro teste deste catálogo):
        # confere manualmente, campo a campo, contra o tipo declarado no
        # branch de sucesso do outputSchema publicado.
        schema = registry.output_schema("consultar_historico_acoes")
        sucesso_schema = schema["oneOf"][0]
        tipos_filtros = sucesso_schema["properties"]["filtros"]["properties"]
        with patch(
            "tools.busca_grafo.buscar_tarefas",
            return_value={"resultados": [], "erro": None},
        ):
            resultado = hermes_tools._consultar_historico_acoes(
                _ctx(), {"query": "x", "area_tematica": 5, "data_limite_fim": None}
            )
        for campo, valor in resultado["filtros"].items():
            with self.subTest(campo=campo):
                tipo_declarado = tipos_filtros[campo]["type"]
                tipos_aceitos = [tipo_declarado] if isinstance(tipo_declarado, str) else tipo_declarado
                if valor is None:
                    self.assertIn("null", tipos_aceitos)
                else:
                    self.assertIn("string", tipos_aceitos)
                    self.assertIsInstance(valor, str)

    def test_busca_recebe_valores_crus_nao_coagidos(self):
        # Achado da 2a rodada de revisão adversarial (sobre a 1a versão
        # desta correção): `status=False`/`area_tematica=[]` são FALSY, e
        # vários pontos de `busca_grafo.py` só aplicam o filtro
        # correspondente quando o valor é truthy (`if status and ...`,
        # `if area_tematica and ...`) -- exatamente para permitir que um
        # chamador mande um valor "vazio" como "sem filtro". Coagir para
        # `"False"`/`"[]"` ANTES de chamar `buscar_tarefas` tornaria esses
        # valores TRUTHY, ligando um filtro que hoje é corretamente
        # ignorado e reduzindo o resultado a zero contra uma string sem
        # sentido. Este teste prova que `buscar_tarefas` recebe os valores
        # ORIGINAIS (crus), não a versão coagida usada só no eco de
        # `filtros` -- mocka `buscar_tarefas` com um `MagicMock` (não um
        # `return_value` fixo) para inspecionar os argumentos reais da
        # chamada, ao contrário dos outros testes desta classe, que só
        # olham para o retorno.
        mock_buscar_tarefas = MagicMock(return_value={"resultados": [], "erro": None})
        with patch("tools.busca_grafo.buscar_tarefas", mock_buscar_tarefas):
            hermes_tools._consultar_historico_acoes(
                _ctx(),
                {
                    "query": "",
                    "area_tematica": [],
                    "status": False,
                    "data_limite_inicio": 0,
                    "data_limite_fim": None,
                },
            )
        self.assertEqual(mock_buscar_tarefas.call_count, 1)
        _, kwargs = mock_buscar_tarefas.call_args
        # Continuam os valores CRUS (falsy), não "[]"/"False"/"0" (truthy).
        self.assertEqual(kwargs["area_tematica"], [])
        self.assertIs(kwargs["status"], False)
        self.assertEqual(kwargs["data_limite_inicio"], 0)
        self.assertIsNone(kwargs["data_limite_fim"])


_PESADOS_HISTORICO = (
    "descricao", "notas", "sintese_demanda", "plano_acao", "acompanhamento_recente",
)


def _acao_completa_historico(i: int) -> dict:
    return {
        "id": f"acao-{i}", "titulo": f"Ação {i}", "status": "em andamento",
        "tipo_acao": "processo", "responsavel": "André", "criado_em": "2026-08-01",
        "area": "FINANCEIRO", "data_limite": "2026-09-30", "processo_sei": "",
        "tags": ["a"], "descricao": "d" * 600, "notas": "n" * 300,
        "sintese_demanda": "s" * 150,
        "plano_acao": [f"✓ etapa {k} " + "p" * 50 for k in range(6)],
        "acompanhamento_recente": [f"[2026-09-0{k + 1}] " + "x" * 110 for k in range(4)],
    }


class TestConsultarHistoricoAcoesDetalhe(unittest.TestCase):
    """`detalhe` (20/09/2026): descrição, notas, plano e diário são ~80% do tamanho
    da resposta; no modo `auto` só as 5 primeiras ações (as mais bem ranqueadas) vão
    completas e as demais ficam curtas.

    O cliente do Claude valida o `structuredContent` contra o `outputSchema` que
    guardou em cache do connector. A primeira versão (PR #293) tirava campos
    obrigatórios e criava `resumido`/`aviso`, e em produção a chamada voltou como
    erro de esquema. Por isso as resumidas mantêm os 15 campos, com os mesmos tipos,
    e nenhum campo novo aparece.
    """

    def _rodar(self, n: int, **args):
        itens = [_acao_completa_historico(i) for i in range(n)]
        with patch(
            "tools.busca_grafo.buscar_tarefas",
            return_value={"resultados": itens, "erro": None},
        ):
            return hermes_tools._consultar_historico_acoes(_ctx(), {"query": "x", **args})

    def test_auto_traz_as_5_primeiras_completas_e_resume_o_resto(self):
        r = self._rodar(20)
        self.assertEqual(r["total_retornado"], 20)
        for i, item in enumerate(r["resultados"][:5]):
            self.assertEqual(item, _acao_completa_historico(i))
        for i, item in enumerate(r["resultados"][5:], start=5):
            base = _acao_completa_historico(i)
            self.assertNotEqual(item, base)
            self.assertLessEqual(len(item["descricao"]), 101)
            self.assertTrue(base["descricao"].startswith(item["descricao"].rstrip("…")))
            self.assertEqual(item["notas"], "(resumido — use obter_acao)")
            self.assertEqual(item["sintese_demanda"], "(resumido — use obter_acao)")
            self.assertEqual(item["plano_acao"], ["(resumido: 6 etapa(s) — use obter_acao)"])
            self.assertEqual(
                item["acompanhamento_recente"],
                ["(resumido: 4 entrada(s) do diário — use obter_acao)"],
            )

    def test_padrao_sem_detalhe_e_igual_a_auto(self):
        self.assertEqual(self._rodar(12), self._rodar(12, detalhe="auto"))

    def test_auto_com_5_ou_menos_acoes_nao_muda_nada(self):
        for n in (0, 1, 5):
            with self.subTest(n=n):
                r = self._rodar(n)
                self.assertEqual(r["resultados"], [_acao_completa_historico(i) for i in range(n)])

    def test_resumo_resume_todas(self):
        r = self._rodar(3, detalhe="resumo")
        for item in r["resultados"]:
            self.assertEqual(item["notas"], "(resumido — use obter_acao)")

    def test_completo_devolve_tudo(self):
        r = self._rodar(20, detalhe="completo")
        self.assertEqual(r["resultados"], [_acao_completa_historico(i) for i in range(20)])

    def test_resumida_com_campos_vazios_nao_inventa_conteudo(self):
        item = {**_acao_completa_historico(0), "descricao": "curta", "notas": "", "sintese_demanda": "",
                "plano_acao": [], "acompanhamento_recente": []}
        with patch("tools.busca_grafo.buscar_tarefas", return_value={"resultados": [item], "erro": None}):
            r = hermes_tools._consultar_historico_acoes(_ctx(), {"query": "x", "detalhe": "resumo"})
        resumida = r["resultados"][0]
        self.assertEqual(resumida["descricao"], "curta")
        self.assertEqual(resumida["notas"], "")
        self.assertEqual(resumida["sintese_demanda"], "")
        self.assertEqual(resumida["plano_acao"], [])
        self.assertEqual(resumida["acompanhamento_recente"], [])

    def test_resumidas_mantem_ordem_e_campos_leves(self):
        r = self._rodar(8)
        self.assertEqual([i["id"] for i in r["resultados"]], [f"acao-{i}" for i in range(8)])
        base = _acao_completa_historico(7)
        for campo in set(base) - set(_PESADOS_HISTORICO):
            self.assertEqual(r["resultados"][7][campo], base[campo])

    def test_modo_auto_reduz_bastante_o_tamanho(self):
        completo = len(json.dumps(self._rodar(20, detalhe="completo"), ensure_ascii=False))
        auto = len(json.dumps(self._rodar(20), ensure_ascii=False))
        self.assertLess(auto, completo * 0.6)

    def test_forma_da_resposta_e_exatamente_a_do_output_schema_publicado(self):
        # Regressão do PR #293: nenhum campo novo e nenhum campo obrigatório a menos,
        # nem no topo nem nos itens, em qualquer modo.
        sucesso = registry.output_schema("consultar_historico_acoes")["oneOf"][0]
        item_schema = sucesso["properties"]["resultados"]["items"]
        tipos = {"string": str, "array": list}
        for detalhe in ("auto", "resumo", "completo"):
            r = self._rodar(8, detalhe=detalhe)
            with self.subTest(detalhe=detalhe):
                self.assertEqual(set(r), set(sucesso["properties"]))
                for item in r["resultados"]:
                    self.assertEqual(set(item), set(item_schema["required"]))
                    self.assertEqual(set(item), set(item_schema["properties"]))
                    for campo, prop in item_schema["properties"].items():
                        tipo = prop["type"]
                        self.assertIsInstance(item[campo], tipos[tipo], campo)
                        if tipo == "array" and prop.get("items", {}).get("type") == "string":
                            self.assertTrue(all(isinstance(x, str) for x in item[campo]), campo)

    def test_detalhe_entra_no_esquema_de_entrada_com_enum(self):
        params = registry.get_schema("consultar_historico_acoes")["parameters"]
        self.assertEqual(params["properties"]["detalhe"]["enum"], ["auto", "resumo", "completo"])
        self.assertNotIn("detalhe", params["required"])
        self.assertEqual(
            registry.valores_invalidos("consultar_historico_acoes", {"detalhe": "auto"}), []
        )
        self.assertTrue(
            registry.valores_invalidos("consultar_historico_acoes", {"detalhe": "tudo"})
        )
