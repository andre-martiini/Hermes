"""Testes do preflight de `autonomy.policy` no servidor MCP (P02 sub-entrega
2/N, docs/autonomia/execucao.md) e cobertura do contrato `resultType` do
dispatch MCP (achado do Codex na PR #193, 07/09/2026).

Este arquivo reúne duas frentes de teste para `mcp_server.py`, criadas
independentemente em duas branches sem ancestral comum para este arquivo
(main e `claude/p02-autonomy-policy-contracts`) e combinadas aqui ao
resolver o conflito de merge (add/add) entre as duas ao integrar as PRs.
Nenhuma classe, teste ou asserção de nenhuma das duas partes foi alterada
nesta combinação — só a função auxiliar `_ctx` da Parte 2 foi renomeada
para `_ctx_result_type`, para não colidir com a `_ctx` da Parte 1 (as duas
tinham o mesmo nome mas construíam o `ToolContext` de forma ligeiramente
diferente — ver cada uma abaixo).

== Parte 1 — Preflight de `autonomy.policy` (classes logo abaixo) ==
Escopo deliberadamente estreito: `mcp_server.py` não tem nenhum outro teste
(898 linhas, sem `test_mcp_server.py` antes desta sub-entrega — só
`test_mcp_oauth.py`, que cobre o módulo de OAuth, não este arquivo). Em vez
de tentar cobrir o servidor MCP inteiro nesta sub-entrega, este arquivo cobre
só o que ela ADICIONA: `_principal_mcp` (construção do `Principal` do
canal), `_decisao_piso_mcp` (o preflight em si) e o mapeamento de
`PolicyDecision` para a resposta JSON-RPC dentro de `_handle_tools_call`.

Os testes evitam Firestore real de duas formas: (1) `_decisao_piso_mcp`
chama `autonomy_policy.estado_autonomia_atual`/`autonomy_policy.
registrar_decisao` pelo nome do módulo (`mcp_server.autonomy_policy.*`), e
essas duas funções já são as únicas do motor que tocam `db` — testá-las de
verdade é responsabilidade de `test_policy.py`; aqui elas são substituídas
por dublês. (2) Quando um teste precisa de um `ToolContext` mas o caminho
sob teste nunca acessa `ctx.db` de verdade (porque as funções de I/O foram
substituídas), o `ToolContext` é construído com `_db` já preenchido por um
sentinela, para que a property `db` não tente inicializar Firebase.

== Parte 2 — Contrato `resultType` (classes no fim do arquivo, usam
`_ctx_result_type`) ==
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
quadro completo do que já era coberto. O escopo desta segunda parte é
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
from unittest.mock import MagicMock, PropertyMock, patch

import mcp_server
from autonomy.contracts import Decisao, EstadoAutonomia, PolicyDecision, TipoPrincipal
from tools.tool_context import ToolContext


def _ctx(uid="dono-uid"):
    # `_db` já preenchido com um sentinela: nada neste arquivo deve acessar
    # Firestore de verdade, então se algum código sob teste tentar (bug),
    # o sentinela (não um cliente Firestore) estoura na hora, alto e claro,
    # em vez de tentar abrir uma conexão real e travar/falhar de outro jeito.
    return ToolContext(user_uid=uid, canal="mcp", _db=object())


class TestPrincipalMcp(unittest.TestCase):
    def test_cliente_assistido_com_origem_humana_true(self):
        ctx = _ctx(uid="uid-123")
        principal = mcp_server._principal_mcp(ctx)
        self.assertEqual(principal.uid, "uid-123")
        self.assertEqual(principal.tipo, TipoPrincipal.CLIENTE_ASSISTIDO)
        self.assertEqual(principal.canal, "mcp")
        self.assertIs(principal.origem_humana, True)
        # CLIENTE_ASSISTIDO é um dos dois tipos "eh_dono()" — condição que o
        # gate de eh_dono() (rodada 5 do Codex, PR #192) depende para conceder
        # o ALLOW de baixa fricção da matriz padrão.
        self.assertTrue(principal.eh_dono())


class TestDecisaoPisoMcp(unittest.TestCase):
    def test_retorna_none_para_tool_fora_da_classificacao_do_piso(self):
        ctx = _ctx()
        with patch.object(mcp_server.autonomy_policy, "estado_autonomia_atual") as mock_estado:
            resultado = mcp_server._decisao_piso_mcp(ctx, "tool_admin_qualquer", {})
        self.assertIsNone(resultado)
        # Prova que o preflight nem tenta resolver estado/avaliar para um
        # tool que não está em CLASSE_EFEITO_PISO — não é só "decide None
        # por outro caminho", é "não entra no motor de política".
        mock_estado.assert_not_called()

    def test_ativo_produz_require_approval(self):
        ctx = _ctx()
        with patch.object(
            mcp_server.autonomy_policy, "estado_autonomia_atual", return_value=EstadoAutonomia.ATIVO
        ), patch.object(mcp_server.autonomy_policy, "registrar_decisao") as mock_registrar:
            decisao = mcp_server._decisao_piso_mcp(ctx, "pausar_conversa", {"x": 1})
        self.assertIsInstance(decisao, PolicyDecision)
        self.assertEqual(decisao.decision, Decisao.REQUIRE_APPROVAL)
        self.assertEqual(decisao.reason_code, "floor_nao_contornavel")
        mock_registrar.assert_called_once()

    def test_pausado_produz_deny(self):
        ctx = _ctx()
        with patch.object(
            mcp_server.autonomy_policy, "estado_autonomia_atual", return_value=EstadoAutonomia.PAUSADO
        ), patch.object(mcp_server.autonomy_policy, "registrar_decisao"):
            decisao = mcp_server._decisao_piso_mcp(ctx, "schedule_whatsapp_message", {})
        self.assertEqual(decisao.decision, Decisao.DENY)

    def test_somente_preparacao_produz_prepare_only(self):
        ctx = _ctx()
        with patch.object(
            mcp_server.autonomy_policy,
            "estado_autonomia_atual",
            return_value=EstadoAutonomia.SOMENTE_PREPARACAO,
        ), patch.object(mcp_server.autonomy_policy, "registrar_decisao"):
            decisao = mcp_server._decisao_piso_mcp(ctx, "criar_rascunho_email", {})
        self.assertEqual(decisao.decision, Decisao.PREPARE_ONLY)

    def test_usa_principal_cliente_assistido_no_request_avaliado(self):
        # Verifica o Principal que de fato chega em avaliar() (via
        # registrar_decisao, que recebe o mesmo PolicyRequest) — não só que
        # `_principal_mcp` por si só está correto (já coberto acima), mas
        # que `_decisao_piso_mcp` de fato usa ele para montar o pedido.
        ctx = _ctx(uid="dono-uid-xyz")
        with patch.object(
            mcp_server.autonomy_policy, "estado_autonomia_atual", return_value=EstadoAutonomia.ATIVO
        ), patch.object(mcp_server.autonomy_policy, "registrar_decisao") as mock_registrar:
            mcp_server._decisao_piso_mcp(ctx, "registrar_aporte_investimento", {"valor": 10})
        request_usado = mock_registrar.call_args.args[1]
        self.assertEqual(request_usado.principal.uid, "dono-uid-xyz")
        self.assertEqual(request_usado.principal.tipo, TipoPrincipal.CLIENTE_ASSISTIDO)
        self.assertIs(request_usado.principal.origem_humana, True)
        self.assertEqual(request_usado.ferramenta, "registrar_aporte_investimento")

    def test_falha_em_avaliar_nao_propaga_excecao_e_bloqueia_com_deny(self):
        # Mesmo fix de `autonomy.policy::decisao_piso` (P02 sub-entrega
        # 12/N), aplicado aqui: `autonomy_policy.avaliar(request)` é chamada
        # dentro de um try/except, caindo em
        # `autonomy_policy.decisao_erro_avaliacao(...)` (DENY fail-closed)
        # em vez de propagar. Mockado via `patch.object(mcp_server.
        # autonomy_policy, "avaliar", ...)` pelo mesmo motivo de
        # test_policy.py::TestDecisaoPiso::
        # test_falha_em_avaliar_nao_propaga_excecao_e_bloqueia_com_deny: o
        # ramo do piso de `avaliar()` não toca `principal` hoje (ver
        # test_policy.py::TestFloorIdenticoAoMcpServer::
        # test_classe_efeito_piso_cobre_exatamente_o_floor), então simular
        # um `principal` malformado de verdade não reproduziria a exceção —
        # o mock exercita o try/except diretamente, não uma consequência
        # indireta de dados malformados.
        ctx = _ctx()
        with patch.object(
            mcp_server.autonomy_policy, "estado_autonomia_atual", return_value=EstadoAutonomia.ATIVO
        ), patch.object(
            mcp_server.autonomy_policy, "avaliar", side_effect=AttributeError("boom")
        ), patch.object(mcp_server.autonomy_policy, "registrar_decisao") as mock_registrar:
            decisao = mcp_server._decisao_piso_mcp(ctx, "schedule_whatsapp_message", {"x": "y"})
        self.assertEqual(decisao.decision, Decisao.DENY)
        self.assertEqual(decisao.reason_code, "erro_interno_avaliacao_politica")
        # registrar_decisao ainda é tentado, mesmo com a decisão de fallback
        # (auditoria não depende de avaliar() ter tido sucesso).
        mock_registrar.assert_called_once()

    def test_falha_em_avaliar_nao_impede_registrar_decisao_de_ser_tentado(self):
        # Variante que confirma a ORDEM: mesmo quando avaliar() falha, a
        # tentativa de registrar_decisao ainda acontece com a decisão de
        # fallback (não com None nem interrompendo a função antes dela) —
        # complementa o teste acima verificando o valor passado adiante.
        ctx = _ctx()
        with patch.object(
            mcp_server.autonomy_policy, "estado_autonomia_atual", return_value=EstadoAutonomia.ATIVO
        ), patch.object(
            mcp_server.autonomy_policy, "avaliar", side_effect=RuntimeError("boom")
        ), patch.object(mcp_server.autonomy_policy, "registrar_decisao") as mock_registrar:
            decisao = mcp_server._decisao_piso_mcp(ctx, "pausar_conversa", {})
        decisao_registrada = mock_registrar.call_args.args[2]
        self.assertIs(decisao_registrada, decisao)
        self.assertEqual(decisao_registrada.decision, Decisao.DENY)

    def test_delega_para_decisao_piso_quando_ctx_db_resolve(self):
        # P02 sub-entrega 13/N: prova a delegação em si, não só um
        # comportamento indireto compatível com ela — `_decisao_piso_mcp`
        # deve chamar `autonomy_policy.decisao_piso(db, principal, nome,
        # argumentos)` exatamente uma vez, com o `db` já resolvido de
        # `ctx.db` (não a property, o valor) e o `Principal` de
        # `_principal_mcp(ctx)`, sem reimplementar o lookup de
        # classe_efeito/estado/avaliar/registrar em paralelo.
        ctx = _ctx(uid="dono-uid-delega")
        sentinela = PolicyDecision(
            decision=Decisao.REQUIRE_APPROVAL,
            policy_id="p",
            policy_version="v",
            reason_code="sentinela",
            constraints_checked=(),
            operation_hash="hash",
            motivo_legivel="sentinela de teste",
        )
        with patch.object(
            mcp_server.autonomy_policy, "decisao_piso", return_value=sentinela
        ) as mock_decisao_piso:
            resultado = mcp_server._decisao_piso_mcp(ctx, "pausar_conversa", {"x": 1})
        self.assertIs(resultado, sentinela)
        mock_decisao_piso.assert_called_once()
        args = mock_decisao_piso.call_args.args
        self.assertIs(args[0], ctx.db)
        self.assertEqual(args[1].uid, "dono-uid-delega")
        self.assertEqual(args[1].tipo, TipoPrincipal.CLIENTE_ASSISTIDO)
        self.assertEqual(args[2], "pausar_conversa")
        self.assertEqual(args[3], {"x": 1})

    def test_ctx_db_indisponivel_cai_em_somente_preparacao_sem_registrar(self):
        # P02 sub-entrega 13/N: quando a property `ctx.db` lança na própria
        # inicialização (ex.: app Firebase não existe), não há `db` para
        # delegar a `decisao_piso()` nem para registrar a decisão — o
        # fallback deve, mesmo assim, produzir uma decisão fail-closed
        # coerente com SOMENTE_PREPARACAO (mesmo resultado do código
        # anterior a esta sub-entrega), sem tentar `registrar_decisao`.
        ctx = _ctx()
        with patch.object(
            type(ctx), "db", new_callable=PropertyMock, side_effect=RuntimeError("Firebase indisponível")
        ), patch.object(mcp_server.autonomy_policy, "registrar_decisao") as mock_registrar, patch.object(
            mcp_server.autonomy_policy, "decisao_piso"
        ) as mock_decisao_piso:
            decisao = mcp_server._decisao_piso_mcp(ctx, "criar_rascunho_email", {})
        self.assertEqual(decisao.decision, Decisao.PREPARE_ONLY)
        mock_registrar.assert_not_called()
        mock_decisao_piso.assert_not_called()


class TestHandleToolsCallPreflight(unittest.TestCase):
    """Integração: `_handle_tools_call` mapeando `PolicyDecision` para a
    resposta JSON-RPC, ANTES de qualquer prévia de confirmação ser criada."""

    def _params(self, nome, argumentos=None):
        return {"name": nome, "arguments": argumentos or {}}

    def test_bloqueia_tool_do_piso_quando_autonomia_pausada_sem_chamar_preview(self):
        ctx = _ctx()
        with patch.object(
            mcp_server.autonomy_policy, "estado_autonomia_atual", return_value=EstadoAutonomia.PAUSADO
        ), patch.object(mcp_server.autonomy_policy, "registrar_decisao"), patch.object(
            mcp_server.registry, "is_mcp_enabled", return_value=True
        ), patch.object(mcp_server, "preview_tool") as mock_preview:
            resultado = mcp_server._handle_tools_call(
                self._params("pausar_conversa"), ctx=ctx
            )
        mock_preview.assert_not_called()
        conteudo = resultado["content"][0]["text"]
        self.assertTrue(resultado.get("isError"))
        self.assertIn("denied", conteudo)

    def test_prepare_only_quando_somente_preparacao_sem_chamar_preview(self):
        ctx = _ctx()
        with patch.object(
            mcp_server.autonomy_policy,
            "estado_autonomia_atual",
            return_value=EstadoAutonomia.SOMENTE_PREPARACAO,
        ), patch.object(mcp_server.autonomy_policy, "registrar_decisao"), patch.object(
            mcp_server.registry, "is_mcp_enabled", return_value=True
        ), patch.object(mcp_server, "preview_tool") as mock_preview:
            resultado = mcp_server._handle_tools_call(
                self._params("criar_rascunho_email"), ctx=ctx
            )
        mock_preview.assert_not_called()
        self.assertFalse(resultado.get("isError", False))
        conteudo = resultado["content"][0]["text"]
        self.assertIn("prepare_only", conteudo)

    def test_ativo_prossegue_para_fluxo_de_confirmacao_existente(self):
        # Não recria toda a criação de confirmação (Firestore) — só prova
        # que o controle chega até `preview_tool`, o primeiro passo do fluxo
        # antigo, inalterado. Um `RuntimeError` sentinela de dentro do
        # `preview_tool` mockado é capturado pelo `except Exception` que já
        # existe nesse trecho e vira `{"erro": ...}` — evidência de que o
        # fluxo antigo foi mesmo alcançado, sem precisar simular Firestore.
        ctx = _ctx()
        with patch.object(
            mcp_server.autonomy_policy, "estado_autonomia_atual", return_value=EstadoAutonomia.ATIVO
        ), patch.object(mcp_server.autonomy_policy, "registrar_decisao"), patch.object(
            mcp_server.registry, "is_mcp_enabled", return_value=True
        ), patch.object(
            mcp_server, "preview_tool", side_effect=RuntimeError("sentinela-fluxo-antigo")
        ) as mock_preview:
            resultado = mcp_server._handle_tools_call(
                self._params("pausar_conversa"), ctx=ctx
            )
        mock_preview.assert_called_once()
        self.assertTrue(resultado.get("isError"))
        self.assertIn("sentinela-fluxo-antigo", resultado["content"][0]["text"])

    def test_tool_confirm_gated_so_por_config_nao_chama_motor_de_politica(self):
        # Um tool que exige confirmação só via `system/mcp_access.confirm_tools`
        # (não está no piso hardcoded) não tem `classe_efeito` conhecida —
        # `_decisao_piso_mcp` retorna None e o fluxo antigo roda inalterado,
        # sem nunca consultar `estado_autonomia_atual`.
        ctx = _ctx()
        with patch.object(
            mcp_server, "_access_config", return_value={"confirm_tools": {"tool_admin_extra"}}
        ), patch.object(mcp_server.autonomy_policy, "estado_autonomia_atual") as mock_estado, patch.object(
            mcp_server.registry, "is_mcp_enabled", return_value=True
        ), patch.object(
            mcp_server, "preview_tool", side_effect=RuntimeError("sentinela-fluxo-antigo")
        ) as mock_preview:
            resultado = mcp_server._handle_tools_call(
                self._params("tool_admin_extra"), ctx=ctx
            )
        mock_estado.assert_not_called()
        mock_preview.assert_called_once()
        self.assertIn("sentinela-fluxo-antigo", resultado["content"][0]["text"])


class TestPisoSemHookNaoBurlaConfirmacaoComConfirmedTrue(unittest.TestCase):
    """Achado da revisão adversarial desta sub-entrega (P02 sub-entrega 2/N):
    `criar_rascunho_email`, `registrar_aporte_investimento` e
    `registrar_execucao_investimento` não têm hook de prévia
    (`tools/hermes_tools.py::preview()` devolve `None` para as três). Antes
    da correção, uma ÚNICA chamada `tools/call` com `_confirmed=true` e SEM
    `_confirmation_id` executava essas três tools direto — sem nunca criar
    uma confirmação real, sem nunca passar por `_decisao_piso_mcp` (só
    chamado no ramo de CRIAÇÃO de confirmação), e sem o "sim" explícito que
    o piso promete ser inegociável. Provado ponta a ponta contra o dispatch
    real (`execute_tool`), não só contra o texto do erro — a prova que
    importa é que a tool NUNCA RODA, não só que a resposta parece um erro.
    """

    def _params(self, nome, confirmed=True, confirmation_id=None, argumentos=None):
        args = dict(argumentos or {})
        args["_confirmed"] = confirmed
        if confirmation_id is not None:
            args["_confirmation_id"] = confirmation_id
        return {"name": nome, "arguments": args}

    def test_registrar_aporte_investimento_bloqueado_sem_confirmation_id(self):
        ctx = _ctx()
        with patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), patch.object(
            mcp_server, "execute_tool"
        ) as mock_execute, patch.object(mcp_server, "preview_tool") as mock_preview:
            resultado = mcp_server._handle_tools_call(
                self._params("registrar_aporte_investimento", argumentos={"valor": 100}),
                ctx=ctx,
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado.get("isError"))
        self.assertIn("confirmation_id", resultado["content"][0]["text"])
        # Nem sequer chega a checar hook de prévia — bloqueado antes disso,
        # só por estar no piso.
        mock_preview.assert_not_called()

    def test_registrar_execucao_investimento_bloqueado_sem_confirmation_id(self):
        ctx = _ctx()
        with patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), patch.object(
            mcp_server, "execute_tool"
        ) as mock_execute:
            resultado = mcp_server._handle_tools_call(
                self._params("registrar_execucao_investimento", argumentos={"ativo": "X"}),
                ctx=ctx,
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado.get("isError"))

    def test_criar_rascunho_email_bloqueado_sem_confirmation_id(self):
        ctx = _ctx()
        with patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), patch.object(
            mcp_server, "execute_tool"
        ) as mock_execute:
            resultado = mcp_server._handle_tools_call(
                self._params("criar_rascunho_email"), ctx=ctx
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado.get("isError"))

    def test_confirmation_id_real_ainda_funciona_para_tool_do_piso_sem_hook(self):
        # A correção não deve quebrar o caminho LEGÍTIMO: confirmation_id de
        # uma confirmação real e persistida ainda executa normalmente — só o
        # atalho sem confirmation_id é que fica fechado.
        ctx = _ctx()
        with patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), patch.object(
            mcp_server, "_executar_confirmacao", return_value={"ok": True}
        ) as mock_executar:
            resultado = mcp_server._handle_tools_call(
                self._params(
                    "registrar_aporte_investimento",
                    confirmation_id="confirmacao-real-123",
                    argumentos={"valor": 100},
                ),
                ctx=ctx,
            )
        mock_executar.assert_called_once()
        self.assertFalse(resultado.get("isError", False))

    def test_pausar_conversa_com_hook_continua_pedindo_confirmation_id_como_antes(self):
        # `pausar_conversa` TEM hook de prévia — já era bloqueada antes desta
        # correção (preview_tool(...) is not None). Continua bloqueada, só
        # que agora pela mesma razão nova (está no piso) chega primeiro —
        # o comportamento observável para quem chama não muda.
        ctx = _ctx()
        with patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), patch.object(
            mcp_server, "execute_tool"
        ) as mock_execute, patch.object(
            mcp_server, "preview_tool", return_value={"status": "aguardando_confirmacao"}
        ) as mock_preview:
            resultado = mcp_server._handle_tools_call(
                self._params("pausar_conversa"), ctx=ctx
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado.get("isError"))
        # Bloqueado pelo novo gate do piso, ANTES de sequer consultar o hook
        # de prévia (redundante para tools do piso, mas não regressivo).
        mock_preview.assert_not_called()

    def test_tool_confirm_gated_so_por_config_tambem_exige_confirmation_id(self):
        # Fora do piso hardcoded (só por `system/mcp_access.confirm_tools`):
        # ATUALIZADO na sub-entrega 7/N — a "compatibilidade legada"
        # ("_confirmed=true bem sucedido quando a tool não tem hook") foi
        # deliberadamente fechada aqui também, mesma lacuna de governança já
        # fechada para o piso na sub-entrega 2/N (ver docstring da classe).
        # A sub-entrega 2/N tinha restringido o fechamento só ao piso e
        # registrado esta mesma lacuna como pendência explícita em
        # docs/autonomia/execucao.md ("vale endereçar quando uma futura
        # sub-entrega tratar de tools configuráveis via política") — este é
        # aquele endereçamento. Não é ampliação por analogia do PISO (que
        # continua sendo só os 5 nomes fixos); é o fechamento do MESMO atalho
        # de bypass para qualquer tool que `_exige_confirmacao()` cubra.
        ctx = _ctx()
        with patch.object(
            mcp_server, "_access_config", return_value={"confirm_tools": {"tool_admin_extra"}}
        ), patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), patch.object(
            mcp_server, "execute_tool", return_value={"ok": True}
        ) as mock_execute, patch.object(mcp_server, "preview_tool", return_value=None):
            resultado = mcp_server._handle_tools_call(
                self._params("tool_admin_extra"), ctx=ctx
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado.get("isError"))
        self.assertIn("confirmation_id", resultado["content"][0]["text"])

    def test_tool_confirm_gated_so_por_config_com_confirmation_id_real_ainda_funciona(self):
        # O caminho legítimo (confirmation_id de uma confirmação real e
        # persistida) continua funcionando normalmente para tools de
        # confirmação só por config — só o atalho sem confirmation_id fica
        # fechado, mesmo padrão já provado para o piso acima.
        ctx = _ctx()
        with patch.object(
            mcp_server, "_access_config", return_value={"confirm_tools": {"tool_admin_extra"}}
        ), patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), patch.object(
            mcp_server, "_executar_confirmacao", return_value={"ok": True}
        ) as mock_executar:
            resultado = mcp_server._handle_tools_call(
                self._params("tool_admin_extra", confirmation_id="confirmacao-real-456"),
                ctx=ctx,
            )
        mock_executar.assert_called_once()
        self.assertFalse(resultado.get("isError", False))

    def test_tool_confirm_gated_so_por_config_com_hook_continua_bloqueada_como_antes(self):
        # Tool de confirmação só por config QUE TEM hook de prévia: já era
        # bloqueada antes desta sub-entrega (preview_tool(...) is not None);
        # continua bloqueada agora, comportamento observável inalterado.
        ctx = _ctx()
        with patch.object(
            mcp_server, "_access_config", return_value={"confirm_tools": {"tool_admin_extra"}}
        ), patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), patch.object(
            mcp_server, "execute_tool"
        ) as mock_execute, patch.object(
            mcp_server, "preview_tool", return_value={"status": "aguardando_confirmacao"}
        ):
            resultado = mcp_server._handle_tools_call(
                self._params("tool_admin_extra"), ctx=ctx
            )
        mock_execute.assert_not_called()
        self.assertTrue(resultado.get("isError"))


class TestFerramentasDePoliticaViaMcp(unittest.TestCase):
    """P02 sub-entrega 3/N: consultar_politica/simular_politica/preparar_politica
    não estão em `CLASSE_EFEITO_PISO` nem em `confirm_tools` por padrão —
    `_exige_confirmacao` é `False` para as três, então passam direto pelo
    fluxo genérico de execução deste método (`execute_tool`), sem preflight
    de política nem prévia de confirmação.

    Achado da revisão adversarial desta sub-entrega: as duas respostas de
    erro mais comuns dessas tools (lote de `simular_politica` com pedido
    inválido; `preparar_politica` com `base_version` desatualizada — a
    salvaguarda central da tool) eram serializadas como uma string JSON
    plana, sem o prefixo `ERRO|` que `_looks_like_error` reconhece — o
    protocolo MCP via `isError` reportava sucesso para uma chamada que, na
    prática, não fez o que foi pedido. Os testes abaixo provam a correção
    no ponto onde um cliente MCP real observaria a diferença: o `isError`
    devolvido por `_handle_tools_call`, não só o texto interno da resposta.
    """

    def _params(self, nome, argumentos=None):
        return {"name": nome, "arguments": argumentos or {}}

    def test_simular_politica_lote_invalido_marca_iserror(self):
        ctx = _ctx()
        resultado = mcp_server._handle_tools_call(
            self._params("simular_politica", {"pedidos": [
                {"ferramenta": "tool_sem_classe_efeito_conhecida"},
            ]}),
            ctx=ctx,
        )
        self.assertTrue(resultado.get("isError"))
        self.assertIn("pedidos_invalidos", resultado["content"][0]["text"])

    def test_simular_politica_lote_valido_nao_marca_iserror(self):
        ctx = _ctx()
        resultado = mcp_server._handle_tools_call(
            self._params("simular_politica", {"pedidos": [
                {"ferramenta": "pausar_conversa"},
            ]}),
            ctx=ctx,
        )
        self.assertFalse(resultado.get("isError", False))

    def test_preparar_politica_versao_base_errada_marca_iserror(self):
        ctx = _ctx()
        resultado = mcp_server._handle_tools_call(
            self._params("preparar_politica", {"politica_proposta": {}, "base_version": 999}),
            ctx=ctx,
        )
        self.assertTrue(resultado.get("isError"))
        self.assertIn("não bate", resultado["content"][0]["text"])

    def test_preparar_politica_valida_nao_marca_iserror(self):
        ctx = _ctx()
        resultado = mcp_server._handle_tools_call(
            self._params("preparar_politica", {
                "politica_proposta": {},
                "base_version": mcp_server.autonomy_policy._POLICY_VERSION_PADRAO,
            }),
            ctx=ctx,
        )
        self.assertFalse(resultado.get("isError", False))


def _ctx_result_type(uid: str = "dono-uid") -> ToolContext:
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
            r = mcp_server._handle_tools_call({"name": "obter_estado_atual", "arguments": {}}, ctx=_ctx_result_type())
        self.assertEqual(r["resultType"], "complete")
        self.assertFalse(r["isError"])

    def test_execucao_com_excecao_inclui_resulttype(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool", side_effect=RuntimeError("boom")), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call({"name": "consultar_dados_cadastrais", "arguments": {}}, ctx=_ctx_result_type())
        self.assertEqual(r["resultType"], "complete")
        self.assertTrue(r["isError"])

    def test_confirmar_acao_inclui_resulttype(self):
        with patch.object(mcp_server, "_executar_confirmacao", return_value={"status": "ok"}), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call(
                {"name": "confirmar_acao", "arguments": {"confirmation_id": "c1"}}, ctx=_ctx_result_type()
            )
        self.assertEqual(r["resultType"], "complete")

    def test_tool_exigindo_confirmacao_primeira_chamada_inclui_resulttype(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(mcp_server, "preview_tool", return_value={"resumo": "prevista"}), \
             patch.object(mcp_server, "_criar_confirmacao", return_value="conf-1"), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call({"name": "algo_sensivel", "arguments": {}}, ctx=_ctx_result_type())
        self.assertEqual(r["resultType"], "complete")
        self.assertFalse(r["isError"])

    def test_preview_com_erro_inclui_resulttype(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=True), \
             patch.object(mcp_server, "preview_tool", side_effect=ValueError("destino invalido")), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call({"name": "algo_sensivel", "arguments": {}}, ctx=_ctx_result_type())
        self.assertEqual(r["resultType"], "complete")
        self.assertTrue(r["isError"])

    def test_tool_longa_inclui_resulttype(self):
        with patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "_TOOLS_LONGAS", {"tool_demorada"}), \
             patch("mcp_jobs.criar_job", return_value="job-1"), \
             patch.object(mcp_server, "_audit_log"):
            r = mcp_server._handle_tools_call({"name": "tool_demorada", "arguments": {}}, ctx=_ctx_result_type())
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
