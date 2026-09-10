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

Checagem de TIPO (schema `type`) foi adiada por esta sub-entrega para a
2/N — ver a docstring original de `registry.campos_obrigatorios_ausentes`
para o raciocínio completo de por que a fatia de tipo é mais arriscada.

P03 sub-entrega 4/N (adicionado depois, mesmo arquivo): implementa metade
da checagem de tipo adiada acima — só os dois tipos ESTRUTURAIS do JSON
Schema (`array`/`object`), nunca os quatro escalares
(`string`/`integer`/`number`/`boolean`). A fronteira não é arbitrária:
investigação real dos handlers (`tools/hermes_tools.py`) mostrou que campos
escalares numéricos/booleanos já são tratados com tolerância deliberada
(`int(args.get("limite") or 20)` aceita `"20"` de bom grado) — uma checagem
escalar estrita rejeitaria chamadas que hoje funcionam, exatamente o risco
que a sub-entrega 2/N tinha apontado. Os dois tipos estruturais não têm
essa tolerância: passar uma string onde `tags` (array) é esperado não gera
erro nenhum hoje (`args.get("tags") or []` resolve para a própria string
quando não-vazia) — o código segue tratando a string como se fosse a lista,
até explodir ou corromper dado silenciosamente mais adiante. Ver a
docstring de `registry.tipos_invalidos` para o levantamento completo.

Achado da revisão adversarial da 4/N: a fronteira estrutural acima não era
suficiente por si só -- `criar_acao_no_sistema` (`plano_acao`) e
`editar_plano_acao` (`novo_plano`/`plano_acao`/`etapas`) já aceitavam,
antes desta sub-entrega, uma STRING com o JSON de uma lista de etapas,
normalizada com segurança em `subtarefas.normalizar_entrada_plano`
(gatilho: incidente real de 28/08/2026). Sem uma exceção explícita, o
preflight de tipo teria bloqueado essa chamada válida -- a mesma classe de
regressão que a sub-entrega 2/N evitou para os escalares, só que
encontrada tarde demais para ser evitada por investigação prévia sozinha.
Corrigido com uma lista fechada de pares (tool, campo) com tolerância
comprovada (`registry._CAMPOS_COM_TOLERANCIA_A_STRING_JSON`), não uma
regra geral -- `editar_acao.tags`, por exemplo, continua sem essa
tolerância e continua sendo rejeitado.

P03 sub-entrega 5/N (adicionado depois, mesmo arquivo): terceira fatia da
validação de argumentos -- checa se o valor de um campo presente está
entre os permitidos pela lista `enum` que o schema declara para ele
(quando declara). Levantamento nos 105 schemas (10/09/2026) encontrou 8
propriedades de nível superior, em 8 tools, com `enum` -- todas `string`,
sem sobreposição com a checagem de tipo estrutural (que só cobre
`array`/`object`). Mesmo escopo deliberado de `tipos_invalidos`: só
propriedades de NÍVEL SUPERIOR -- o `enum` aninhado do campo `estado` de
cada etapa dentro de `plano_acao`/`etapas` fica de fora, pela mesma razão
estrutural (o campo que contém essa lista pode chegar como string JSON
bruta; validar o conteúdo aninhado viraria parser de plano, não checagem
de preflight). Ver a docstring de `registry.valores_invalidos` para o
catálogo completo.

Achados da 1ª rodada de revisão adversarial da 5/N (dois, ambos corrigidos
antes de mesclar): (1) o schema de `obter_fila_atencao.origem` estava
desatualizado -- faltava `secretario_whatsapp`, um valor real que
`atencao.ORIGENS` já lista e que `secretario_whatsapp.py` já grava em
produção, sem validação alguma no handler (`atencao.coletar_fila_atencao`
faz um filtro cru do Firestore); corrigido acrescentando o valor ao
schema. (2) 4 dos 8 handlers dos campos com `enum`
(`decidir_promocao_autonomia.decisao`, `registrar_execucao_investimento.
ativo`, `registrar_execucao_agente.status`, `solicitar_autorizacao_argos.
tipo`) já normalizam o valor recebido (`.strip().lower()`/`.upper()`/
`.strip()`) antes de comparar -- uma comparação exata aqui teria bloqueado
uma chamada com case ou espaço diferente que esses handlers aceitam hoje,
a mesma classe de regressão já encontrada na 4/N.

A correção inicial do achado (2) tornou `valores_invalidos` tolerante a
case/espaço para QUALQUER campo com `enum` -- e a 2ª rodada de revisão
adversarial (feita sobre a correção, não sobre o diff original, mesmo
padrão de duas rodadas estabelecido na 4/N) achou que essa tolerância
geral era, ela mesma, uma regressão nova e pior: `obter_fila_atencao`
(`estado`/`origem`) não tem handler tolerante -- `coletar_fila_atencao`
usa o valor cru num filtro `==` do Firestore. Com tolerância geral,
`estado="ABERTO"` passaria pelo preflight e devolveria SILENCIOSAMENTE
zero itens (o filtro não bate com o valor armazenado, sempre minúsculo),
sem erro nenhum -- pior que o excesso de rigor original, porque troca um
erro claro por um resultado vazio indistinguível de "nada pendente".
Corrigido tornando a tolerância uma lista FECHADA de pares (tool, campo)
com tolerância comprovada no próprio handler (ver
`registry._CAMPOS_COM_ENUM_TOLERANTE_A_CASE`), mesmo padrão de
`_CAMPOS_COM_TOLERANCIA_A_STRING_JSON` -- nunca uma tolerância geral.

Este arquivo tem nove frentes (três da sub-entrega 2/N, três da 4/N, três
da 5/N, mesmo padrão cada):
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
4. `TestTiposInvalidos` — a função pura `registry.tipos_invalidos`,
   incluindo paridade (para TODO schema real que declara algum campo
   `array`/`object`, um valor do tipo errado nesse campo tem de ser
   detectado, e o tipo certo nunca é falso positivo) e os testes da
   exceção `_CAMPOS_COM_TOLERANCIA_A_STRING_JSON` encontrada na revisão
   adversarial -- inclusive um teste provando que a exceção NÃO se
   espalha para outros campos array/object sem essa tolerância real.
5. `TestErroTiposInvalidos` — o wrapper `mcp_server._erro_tipos_invalidos`.
6. `TestIntegracaoTiposInvalidos` — ponta a ponta via `_handle_tools_call`,
   mesmos dois pontos de inserção da checagem de presença, mesma exclusão
   do reenvio `_confirmed=true`, e a regressão da exceção
   (`plano_acao` como string JSON chegando a `preview_tool`).
7. `TestValoresInvalidos` — a função pura `registry.valores_invalidos`,
   incluindo paridade (para TODO schema real que declara `enum` numa
   propriedade de nível superior) e um teste provando que o `enum`
   aninhado de `plano_acao`/`etapas` fica fora do escopo.
8. `TestErroValoresInvalidos` — o wrapper `mcp_server._erro_valores_invalidos`.
9. `TestIntegracaoValoresInvalidos` — ponta a ponta via `_handle_tools_call`,
   mesmos dois pontos de inserção, incluindo a prova de que campo ausente e
   tipo inválido têm prioridade sobre valor inválido no mesmo payload.
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


class TestTiposInvalidos(unittest.TestCase):
    """`registry.tipos_invalidos` isolada, sem tocar o dispatch. Cobre só a
    fatia estrutural (`array`/`object`) -- ver docstring da função para o
    porquê dos quatro tipos escalares ficarem de fora."""

    def test_todos_os_tipos_estruturais_corretos_devolve_lista_vazia(self):
        self.assertEqual(
            registry.tipos_invalidos(
                "editar_acao",
                {"task_id": "t1", "tags": ["urgente"], "alteracoes": {"status": "feito"}},
            ),
            [],
        )

    def test_array_recebendo_string_e_detectado(self):
        # O caso motivador desta sub-entrega: `tags` é `array`; uma string
        # não-vazia no lugar de lista hoje passa direto para o handler
        # (`args.get("tags") or []` resolve para a própria string) e é
        # tratada como se já fosse a lista, sem erro nenhum ali.
        self.assertEqual(
            registry.tipos_invalidos("editar_acao", {"task_id": "t1", "tags": "urgente"}),
            [{"campo": "tags", "esperado": "array", "recebido": "str"}],
        )

    def test_object_recebendo_string_e_detectado(self):
        # Segundo caso motivador: `alteracoes` é `object`; uma string no
        # lugar de dict hoje levanta um `ValueError` opaco lá dentro do
        # handler (`dict(args.get("alteracoes") or {})`).
        self.assertEqual(
            registry.tipos_invalidos(
                "editar_acao", {"task_id": "t1", "alteracoes": "não é um dict"}
            ),
            [{"campo": "alteracoes", "esperado": "object", "recebido": "str"}],
        )

    def test_campo_ausente_nao_e_acusado_aqui(self):
        # Ausência é responsabilidade de `campos_obrigatorios_ausentes`, não
        # desta função -- mesmo que o campo ausente seja array/object.
        self.assertEqual(registry.tipos_invalidos("editar_acao", {"task_id": "t1"}), [])

    def test_campo_none_nao_e_acusado_aqui(self):
        self.assertEqual(
            registry.tipos_invalidos("editar_acao", {"task_id": "t1", "tags": None}), []
        )

    def test_campo_escalar_com_tipo_errado_nao_e_acusado_deliberadamente(self):
        # `consultar_lista_compras` tem `limite` (integer); uma string no
        # lugar de int NÃO deve ser sinalizada por esta função -- é
        # exatamente a tolerância que os handlers já têm hoje
        # (`int(args.get("limite") or 20)` aceita "20" de bom grado).
        schema = registry.get_schema("consultar_lista_compras")
        propriedades = schema.get("parameters", {}).get("properties") or {}
        campos_integer = [c for c, s in propriedades.items() if s.get("type") == "integer"]
        self.assertTrue(campos_integer, "schema de teste precisa de pelo menos um campo integer")
        campo = campos_integer[0]
        self.assertEqual(
            registry.tipos_invalidos("consultar_lista_compras", {campo: "não é um int"}), []
        )

    def test_array_recebendo_lista_vazia_nao_e_erro(self):
        self.assertEqual(
            registry.tipos_invalidos("editar_acao", {"task_id": "t1", "tags": []}), []
        )

    def test_object_recebendo_dict_vazio_nao_e_erro(self):
        self.assertEqual(
            registry.tipos_invalidos("editar_acao", {"task_id": "t1", "alteracoes": {}}), []
        )

    def test_multiplos_campos_com_tipo_invalido_sao_todos_listados(self):
        problemas = registry.tipos_invalidos(
            "editar_acao",
            {"task_id": "t1", "tags": "errado", "alteracoes": "também errado"},
        )
        self.assertEqual(
            {p["campo"] for p in problemas}, {"tags", "alteracoes"}
        )

    def test_tool_inexistente_falha_aberta(self):
        self.assertEqual(
            registry.tipos_invalidos("tool_que_nao_existe_de_verdade", {"x": "y"}), []
        )

    def test_tool_sem_properties_no_schema_nunca_acusa_nada(self):
        self.assertEqual(registry.tipos_invalidos("obter_estado_atual", {"x": "y"}), [])

    def test_paridade_com_todos_os_schemas_reais_do_catalogo(self):
        # Para todo schema real que declara algum campo array/object: um
        # valor do tipo certo nunca é falso positivo, e um valor do tipo
        # errado (uma string, que não é nem lista nem dict) é sempre
        # detectado -- não só nos exemplos escolhidos a dedo acima. Exceção
        # explícita: os pares (tool, campo) com tolerância a string JSON
        # comprovada (ver `registry._CAMPOS_COM_TOLERANCIA_A_STRING_JSON`,
        # achado da revisão adversarial) ficam de fora deste "tipo_errado"
        # -- têm teste dedicado em `test_campos_com_tolerancia_a_string_json_
        # sao_ignorados_deliberadamente` logo abaixo.
        excecoes = registry._CAMPOS_COM_TOLERANCIA_A_STRING_JSON
        for nome in sorted(registry.list_tool_names()):
            schema = registry.get_schema(nome)
            propriedades = (schema.get("parameters") or {}).get("properties") or {}
            for campo, prop_schema in propriedades.items():
                tipo = prop_schema.get("type") if isinstance(prop_schema, dict) else None
                if tipo not in ("array", "object"):
                    continue
                with self.subTest(tool=nome, campo=campo, caso="tipo_certo"):
                    valor_certo = [] if tipo == "array" else {}
                    self.assertEqual(
                        registry.tipos_invalidos(nome, {campo: valor_certo}), []
                    )
                if (nome, campo) in excecoes:
                    continue
                with self.subTest(tool=nome, campo=campo, caso="tipo_errado"):
                    problemas = registry.tipos_invalidos(nome, {campo: "uma string qualquer"})
                    self.assertEqual(
                        [p for p in problemas if p["campo"] == campo],
                        [{"campo": campo, "esperado": tipo, "recebido": "str"}],
                    )

    def test_campos_com_tolerancia_a_string_json_sao_ignorados_deliberadamente(self):
        # Achado da revisão adversarial desta sub-entrega: `criar_acao_no_
        # sistema` (`plano_acao`) e `editar_plano_acao` (`novo_plano`,
        # `plano_acao`, `etapas`) já aceitam uma string com o JSON de uma
        # lista de etapas e a decodificam com segurança em
        # `subtarefas.normalizar_entrada_plano` -- sem esta exceção, este
        # preflight bloquearia uma chamada válida hoje. Uma string que nem
        # é JSON de lista também não é sinalizada AQUI (o handler recusa
        # com uma mensagem própria e mais específica, via `PlanoInvalido`).
        self.assertEqual(
            registry.tipos_invalidos(
                "criar_acao_no_sistema", {"plano_acao": '["Baixar as propostas"]'}
            ),
            [],
        )
        self.assertEqual(
            registry.tipos_invalidos(
                "criar_acao_no_sistema", {"plano_acao": "nem json e"}
            ),
            [],
        )
        for campo in ("novo_plano", "plano_acao", "etapas"):
            with self.subTest(campo=campo):
                self.assertEqual(
                    registry.tipos_invalidos(
                        "editar_plano_acao", {"task_id": "t1", campo: '[{"text": "x"}]'}
                    ),
                    [],
                )

    def test_tolerancia_a_string_json_nao_se_espalha_para_outros_campos(self):
        # A exceção é uma lista fechada de pares (tool, campo) -- não uma
        # regra geral "string que parece JSON vale". `editar_acao.tags` não
        # tem essa normalização no handler (`args.get("tags") or []`, sem
        # parse); uma string aqui teria de continuar sendo rejeitada, senão
        # o preflight reabriria exatamente o buraco que motivou esta
        # sub-entrega (string tratada silenciosamente como se fosse lista).
        self.assertEqual(
            registry.tipos_invalidos("editar_acao", {"task_id": "t1", "tags": '["urgente"]'}),
            [{"campo": "tags", "esperado": "array", "recebido": "str"}],
        )


class TestErroTiposInvalidos(unittest.TestCase):
    """`mcp_server._erro_tipos_invalidos`: tradução para a resposta MCP."""

    def test_none_quando_tipos_corretos(self):
        self.assertIsNone(
            mcp_server._erro_tipos_invalidos(
                "editar_acao", {"task_id": "t1", "tags": ["a"]}
            )
        )

    def test_none_quando_nenhum_campo_estrutural_presente(self):
        self.assertIsNone(mcp_server._erro_tipos_invalidos("editar_acao", {"task_id": "t1"}))

    def test_resposta_de_erro_quando_tipo_invalido(self):
        resultado = mcp_server._erro_tipos_invalidos(
            "editar_acao", {"task_id": "t1", "tags": "errado"}
        )
        self.assertIsNotNone(resultado)
        self.assertTrue(resultado["isError"])
        self.assertEqual(resultado["resultType"], "complete")
        texto = resultado["content"][0]["text"]
        self.assertIn("tags", texto)
        self.assertIn("array", texto)
        self.assertIn("str", texto)

    def test_tool_sem_properties_nunca_gera_erro(self):
        self.assertIsNone(mcp_server._erro_tipos_invalidos("obter_estado_atual", {"x": "y"}))


class TestIntegracaoTiposInvalidos(unittest.TestCase):
    """Ponta a ponta via `_handle_tools_call`, mesmos dois pontos de
    inserção da checagem de presença -- a checagem de tipo roda logo
    depois, então um campo com tipo inválido também nunca chega a
    `preview_tool`/`execute_tool`."""

    def setUp(self):
        patcher = patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_tool_nao_gated_com_tipo_invalido_nunca_chega_a_execute_tool(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool") as mock_execute:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "editar_acao",
                    "arguments": {"task_id": "t1", "tags": "deveria ser lista"},
                },
                ctx=_ctx(),
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado["isError"])
        self.assertIn("tags", resultado["content"][0]["text"])

    def test_tool_nao_gated_com_tipos_corretos_chega_a_execute_tool(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool", return_value={"ok": True}) as mock_execute:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "editar_acao",
                    "arguments": {"task_id": "t1", "tags": ["urgente"]},
                },
                ctx=_ctx(),
            )
        mock_execute.assert_called_once()
        self.assertFalse(resultado.get("isError", False))

    def test_tool_gated_primeira_chamada_com_tipo_invalido_nunca_chega_a_preview(self):
        # `criar_rascunho_email` exige confirmação; `para` é `array`.
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(mcp_server, "_decisao_piso_mcp", return_value=None), \
             patch.object(mcp_server, "preview_tool") as mock_preview:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "criar_rascunho_email",
                    "arguments": {"corpo": "Corpo", "para": "não é uma lista"},
                },
                ctx=_ctx(),
            )
        mock_preview.assert_not_called()
        self.assertTrue(resultado["isError"])
        self.assertIn("para", resultado["content"][0]["text"])

    def test_campo_ausente_tem_prioridade_sobre_tipo_invalido_no_mesmo_payload(self):
        # `_erro_campos_obrigatorios` roda primeiro -- se `corpo` (required)
        # está ausente E `para` (array) tem tipo errado, a mensagem devolvida
        # é a de campo ausente, não a de tipo. Prova a ordem de chamada em
        # `_handle_tools_call`, não só o comportamento de cada função isolada.
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool") as mock_execute:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "criar_rascunho_email",
                    "arguments": {"para": "não é uma lista"},
                },
                ctx=_ctx(),
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado["isError"])
        texto = resultado["content"][0]["text"]
        self.assertIn("corpo", texto)
        self.assertIn("obrigatório", texto)

    def test_plano_como_string_json_chega_a_preview_sem_ser_bloqueado_pelo_preflight(self):
        # Regressão pega pela revisão adversarial desta sub-entrega: sem a
        # exceção em `registry._CAMPOS_COM_TOLERANCIA_A_STRING_JSON`, este
        # preflight bloquearia `criar_acao_no_sistema` com `plano_acao`
        # como string JSON -- uma chamada que `subtarefas.
        # normalizar_entrada_plano` já trata com segurança hoje.
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(mcp_server, "_decisao_piso_mcp", return_value=None), \
             patch.object(
                 mcp_server, "preview_tool", side_effect=RuntimeError("sentinela")
             ) as mock_preview:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "criar_acao_no_sistema",
                    "arguments": {
                        "titulo": "Título",
                        "area_tematica": "geral",
                        "data_limite": "2026-09-20",
                        "plano_acao": '["Baixar as propostas"]',
                    },
                },
                ctx=_ctx(),
            )
        mock_preview.assert_called_once()
        self.assertIn("sentinela", resultado["content"][0]["text"])

    def test_reenvio_confirmed_true_nao_passa_pela_checagem_de_tipo(self):
        # Mesma exclusão deliberada da checagem de presença (ver teste
        # análogo em `TestIntegracaoHandleToolsCall`): no reenvio
        # `_confirmed=true`, `arguments` é só o envelope da confirmação.
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


class TestValoresInvalidos(unittest.TestCase):
    """`registry.valores_invalidos` isolada, sem tocar o dispatch. Cobre só
    `enum` de propriedades de nível superior -- ver docstring da função
    para o porquê de `enum` aninhado (ex.: `estado` de cada etapa dentro de
    `plano_acao`/`etapas`) ficar fora."""

    def test_valor_permitido_devolve_lista_vazia(self):
        self.assertEqual(
            registry.valores_invalidos(
                "decidir_promocao_autonomia", {"tipo": "x", "decisao": "aceitar"}
            ),
            [],
        )

    def test_valor_fora_do_enum_e_detectado(self):
        self.assertEqual(
            registry.valores_invalidos(
                "decidir_promocao_autonomia", {"tipo": "x", "decisao": "talvez"}
            ),
            [{
                "campo": "decisao",
                "esperado": ["aceitar", "adiar", "nunca"],
                "recebido": "talvez",
            }],
        )

    def test_campo_ausente_nao_e_acusado_aqui(self):
        # Ausência é responsabilidade de `campos_obrigatorios_ausentes`, não
        # desta função.
        self.assertEqual(
            registry.valores_invalidos("decidir_promocao_autonomia", {"tipo": "x"}), []
        )

    def test_campo_none_nao_e_acusado_aqui(self):
        self.assertEqual(
            registry.valores_invalidos(
                "decidir_promocao_autonomia", {"tipo": "x", "decisao": None}
            ),
            [],
        )

    def test_campo_sem_enum_declarado_nunca_e_acusado(self):
        # `tipo` (nesta tool) não declara `enum` -- qualquer string vale
        # para esta função (pode ser inválido por outro motivo, mas isso
        # não é responsabilidade desta checagem).
        self.assertEqual(
            registry.valores_invalidos(
                "decidir_promocao_autonomia",
                {"tipo": "qualquer coisa mesmo", "decisao": "aceitar"},
            ),
            [],
        )

    def test_multiplos_campos_com_enum_invalido_sao_todos_listados(self):
        problemas = registry.valores_invalidos(
            "obter_fila_atencao", {"estado": "estado_doido", "origem": "origem_doida"}
        )
        self.assertEqual({p["campo"] for p in problemas}, {"estado", "origem"})

    def test_tool_inexistente_falha_aberta(self):
        self.assertEqual(
            registry.valores_invalidos("tool_que_nao_existe_de_verdade", {"x": "y"}), []
        )

    def test_tool_sem_properties_no_schema_nunca_acusa_nada(self):
        self.assertEqual(registry.valores_invalidos("obter_estado_atual", {"x": "y"}), [])

    def test_origem_secretario_whatsapp_e_aceita(self):
        # Achado da revisão adversarial: o schema de `origem` estava
        # desatualizado -- `secretario_whatsapp` é um valor real, gravado
        # em produção por `secretario_whatsapp.py`
        # (`ORIGEM_SECRETARIO = "secretario_whatsapp"`), sem validação
        # alguma no handler (`atencao.coletar_fila_atencao` é um filtro cru
        # do Firestore). Corrigido acrescentando o valor ao schema.
        self.assertEqual(
            registry.valores_invalidos("obter_fila_atencao", {"origem": "secretario_whatsapp"}),
            [],
        )

    def test_valor_com_case_ou_espaco_diferente_e_tolerado_quando_handler_normaliza(self):
        # Achado da revisão adversarial: 4 dos 8 handlers já normalizam
        # (`.strip().lower()`/`.upper()`/`.strip()`) antes de comparar --
        # uma checagem exata aqui bloquearia uma chamada que o handler
        # aceita hoje.
        self.assertEqual(
            registry.valores_invalidos(
                "decidir_promocao_autonomia", {"tipo": "x", "decisao": "Aceitar"}
            ),
            [],
        )
        self.assertEqual(
            registry.valores_invalidos(
                "registrar_execucao_investimento", {"ativo": "bova11"}
            ),
            [],
        )
        self.assertEqual(
            registry.valores_invalidos(
                "registrar_execucao_agente",
                {"rotina": "x", "resumo": "y", "status": "SUCESSO"},
            ),
            [],
        )
        self.assertEqual(
            registry.valores_invalidos(
                "solicitar_autorizacao_argos",
                {
                    "tipo": " approve-plan ",
                    "sistema_id": "s",
                    "demanda_id": "d",
                    "resumo": "r",
                },
            ),
            [],
        )

    def test_tolerancia_a_case_nao_aceita_valor_genuinamente_invalido(self):
        # A tolerância é só de forma (case/espaço), não abre a lista --
        # um valor que não corresponde a NENHUM permitido, nem depois de
        # normalizado, continua acusado.
        self.assertEqual(
            registry.valores_invalidos(
                "decidir_promocao_autonomia", {"tipo": "x", "decisao": "  Talvez  "}
            ),
            [{
                "campo": "decisao",
                "esperado": ["aceitar", "adiar", "nunca"],
                "recebido": "  Talvez  ",
            }],
        )

    def test_tolerancia_a_case_nao_se_espalha_para_campos_sem_handler_tolerante(self):
        # Achado da 2ª rodada de revisão adversarial (sobre a correção do
        # achado anterior, não sobre o diff original): uma tolerância GERAL
        # a case/espaço seria pior que o problema que corrigia --
        # `obter_fila_atencao` não normaliza nada (`coletar_fila_atencao`
        # usa o valor cru num filtro `==` do Firestore); um valor mal
        # formatado passaria pelo preflight e devolveria silenciosamente
        # zero itens, sem erro algum. A tolerância é uma lista FECHADA
        # (`registry._CAMPOS_COM_ENUM_TOLERANTE_A_CASE`) -- não se espalha
        # para campos fora dela, mesmo que também tenham `enum`.
        self.assertEqual(
            registry.valores_invalidos("obter_fila_atencao", {"estado": "ABERTO"}),
            [{
                "campo": "estado",
                "esperado": [
                    "aberto", "delegado_ao_agente", "aguardando_andre",
                    "resolvido", "descartado",
                ],
                "recebido": "ABERTO",
            }],
        )
        self.assertEqual(
            registry.valores_invalidos("obter_fila_atencao", {"origem": "WhatsApp"}),
            [{
                "campo": "origem",
                "esperado": [
                    "acao", "whatsapp", "email", "agenda", "repo",
                    "financeiro", "saude", "secretario_whatsapp",
                ],
                "recebido": "WhatsApp",
            }],
        )
        self.assertEqual(
            registry.valores_invalidos(
                "resolver_item_atencao", {"item_id": "i1", "estado": "Resolvido"}
            ),
            [{
                "campo": "estado",
                "esperado": [
                    "delegado_ao_agente", "aguardando_andre", "resolvido", "descartado",
                ],
                "recebido": "Resolvido",
            }],
        )

    def test_tolerancia_a_case_nao_vaza_por_nome_de_campo_igual_em_outra_tool(self):
        # Achado da 3ª rodada de revisão (sobre a correção da 2ª): a exceção
        # é chave (tool, campo), não só campo. `registrar_item_financeiro_v2`
        # tem um campo `tipo` com `enum` -- mesmo nome do campo tolerante de
        # `solicitar_autorizacao_argos.tipo` -- e precisa continuar em modo
        # exato, sem "vazar" a tolerância por coincidência de nome.
        self.assertEqual(
            registry.valores_invalidos(
                "registrar_item_financeiro_v2",
                {"tipo": "RENDA", "descricao": "x", "valor": 1},
            ),
            [{
                "campo": "tipo",
                "esperado": ["renda", "obrigacao_fixa", "transacao_avulsa"],
                "recebido": "RENDA",
            }],
        )

    def test_tolerancia_a_case_nao_afeta_valor_nao_string(self):
        # Só compara de forma tolerante quando o valor recebido é `str` --
        # um `int`/`bool` é comparado só pela forma exata, sem o viés de
        # `True == 1`/`False == 0` do Python afetar enum não-string.
        self.assertEqual(
            registry.valores_invalidos("decidir_promocao_autonomia", {"tipo": "x", "decisao": True}),
            [{
                "campo": "decisao",
                "esperado": ["aceitar", "adiar", "nunca"],
                "recebido": True,
            }],
        )

    def test_enum_aninhado_em_plano_acao_fica_fora_do_escopo(self):
        # O `enum` do campo `estado` de cada etapa dentro de `plano_acao`
        # está aninhado no schema de item do array, não é uma propriedade
        # de nível superior -- fora do escopo desta função (ver docstring
        # de `registry.valores_invalidos`).
        self.assertEqual(
            registry.valores_invalidos(
                "criar_acao_no_sistema",
                {"plano_acao": [{"texto": "x", "estado": "valor_doido_que_nao_existe"}]},
            ),
            [],
        )

    def test_paridade_com_todos_os_schemas_reais_do_catalogo(self):
        # Para todo schema real que declara `enum` numa propriedade de
        # nível superior: um valor do próprio enum nunca é falso positivo,
        # e um valor fora dele é sempre detectado -- não só nos exemplos
        # escolhidos a dedo acima.
        sentinela = "valor-fora-do-enum-que-nao-existe-nunca"
        for nome in sorted(registry.list_tool_names()):
            schema = registry.get_schema(nome)
            propriedades = (schema.get("parameters") or {}).get("properties") or {}
            for campo, prop_schema in propriedades.items():
                if not isinstance(prop_schema, dict):
                    continue
                valores_permitidos = prop_schema.get("enum")
                if not isinstance(valores_permitidos, list) or not valores_permitidos:
                    continue
                with self.subTest(tool=nome, campo=campo, caso="valor_certo"):
                    self.assertEqual(
                        registry.valores_invalidos(nome, {campo: valores_permitidos[0]}), []
                    )
                with self.subTest(tool=nome, campo=campo, caso="valor_errado"):
                    problemas = registry.valores_invalidos(nome, {campo: sentinela})
                    self.assertEqual(
                        [p for p in problemas if p["campo"] == campo],
                        [{
                            "campo": campo,
                            "esperado": valores_permitidos,
                            "recebido": sentinela,
                        }],
                    )


class TestErroValoresInvalidos(unittest.TestCase):
    """`mcp_server._erro_valores_invalidos`: tradução para a resposta MCP."""

    def test_none_quando_valores_corretos(self):
        self.assertIsNone(
            mcp_server._erro_valores_invalidos(
                "decidir_promocao_autonomia", {"tipo": "x", "decisao": "aceitar"}
            )
        )

    def test_none_quando_nenhum_campo_com_enum_presente(self):
        self.assertIsNone(
            mcp_server._erro_valores_invalidos("decidir_promocao_autonomia", {"tipo": "x"})
        )

    def test_resposta_de_erro_quando_valor_invalido(self):
        resultado = mcp_server._erro_valores_invalidos(
            "decidir_promocao_autonomia", {"tipo": "x", "decisao": "talvez"}
        )
        self.assertIsNotNone(resultado)
        self.assertTrue(resultado["isError"])
        self.assertEqual(resultado["resultType"], "complete")
        texto = resultado["content"][0]["text"]
        self.assertIn("decisao", texto)
        self.assertIn("talvez", texto)
        self.assertIn("aceitar", texto)

    def test_tool_sem_properties_nunca_gera_erro(self):
        self.assertIsNone(mcp_server._erro_valores_invalidos("obter_estado_atual", {"x": "y"}))


class TestIntegracaoValoresInvalidos(unittest.TestCase):
    """Ponta a ponta via `_handle_tools_call`, mesmos dois pontos de
    inserção das checagens de presença e tipo -- a checagem de valor roda
    por último, então um campo com valor fora do enum também nunca chega a
    `preview_tool`/`execute_tool`."""

    def setUp(self):
        patcher = patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_tool_nao_gated_com_valor_invalido_nunca_chega_a_execute_tool(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool") as mock_execute:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "decidir_promocao_autonomia",
                    "arguments": {"tipo": "x", "decisao": "talvez"},
                },
                ctx=_ctx(),
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado["isError"])
        self.assertIn("decisao", resultado["content"][0]["text"])

    def test_tool_nao_gated_com_valor_correto_chega_a_execute_tool(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool", return_value={"ok": True}) as mock_execute:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "decidir_promocao_autonomia",
                    "arguments": {"tipo": "x", "decisao": "aceitar"},
                },
                ctx=_ctx(),
            )
        mock_execute.assert_called_once()
        self.assertFalse(resultado.get("isError", False))

    def test_tool_gated_primeira_chamada_com_valor_invalido_nunca_chega_a_preview(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(mcp_server, "_decisao_piso_mcp", return_value=None), \
             patch.object(mcp_server, "preview_tool") as mock_preview:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "resolver_item_atencao",
                    "arguments": {"item_id": "item-1", "estado": "estado_doido"},
                },
                ctx=_ctx(),
            )
        mock_preview.assert_not_called()
        self.assertTrue(resultado["isError"])
        self.assertIn("estado", resultado["content"][0]["text"])

    def test_campo_ausente_tem_prioridade_sobre_valor_invalido_no_mesmo_payload(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool") as mock_execute:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "decidir_promocao_autonomia",
                    "arguments": {"decisao": "talvez"},
                },
                ctx=_ctx(),
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado["isError"])
        texto = resultado["content"][0]["text"]
        self.assertIn("tipo", texto)
        self.assertIn("obrigatório", texto)

    def test_tipo_invalido_tem_prioridade_sobre_valor_invalido_no_mesmo_payload(self):
        # `registrar_execucao_agente` tem `contadores` (object) e `status`
        # (enum) -- os dois errados no mesmo payload; `_erro_tipos_invalidos`
        # roda antes de `_erro_valores_invalidos`, então a mensagem devolvida
        # é a de tipo, não a de valor.
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool") as mock_execute:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "registrar_execucao_agente",
                    "arguments": {
                        "rotina": "cron-x",
                        "resumo": "ok",
                        "contadores": "não é um dict",
                        "status": "estado_doido",
                    },
                },
                ctx=_ctx(),
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado["isError"])
        self.assertIn("contadores", resultado["content"][0]["text"])

    def test_reenvio_confirmed_true_continua_fora_do_alcance_desta_checagem(self):
        # Mesma exclusão deliberada das duas checagens anteriores: no
        # reenvio `_confirmed=true`, `arguments` é só o envelope da
        # confirmação, não o payload de negócio.
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(
                 mcp_server, "_executar_confirmacao", return_value={"ok": True}
             ) as mock_executar:
            resultado = mcp_server._handle_tools_call(
                {
                    "name": "resolver_item_atencao",
                    "arguments": {"_confirmed": True, "_confirmation_id": "conf-1"},
                },
                ctx=_ctx(),
            )
        mock_executar.assert_called_once()
        self.assertFalse(resultado.get("isError", False))


if __name__ == "__main__":
    unittest.main()
