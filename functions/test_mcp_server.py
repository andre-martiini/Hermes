"""Testes do preflight de `autonomy.policy` no servidor MCP (P02 sub-entrega
2/N, docs/autonomia/execucao.md).

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
"""

import unittest
from unittest.mock import MagicMock, patch

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

    def test_tool_confirm_gated_so_por_config_mantem_compatibilidade_antiga(self):
        # Fora do piso hardcoded (só por `system/mcp_access.confirm_tools`):
        # a compatibilidade legada ("_confirmed=true bem sucedido quando a
        # tool não tem hook") continua exatamente como era — o fechamento
        # desta correção é deliberadamente restrito ao piso, não ampliado
        # por analogia a tools fora dele.
        ctx = _ctx()
        with patch.object(
            mcp_server, "_access_config", return_value={"confirm_tools": {"tool_admin_extra"}}
        ), patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), patch.object(
            mcp_server, "execute_tool", return_value={"ok": True}
        ) as mock_execute, patch.object(mcp_server, "preview_tool", return_value=None):
            resultado = mcp_server._handle_tools_call(
                self._params("tool_admin_extra"), ctx=ctx
            )
        mock_execute.assert_called_once()
        self.assertFalse(resultado.get("isError", False))


if __name__ == "__main__":
    unittest.main()
