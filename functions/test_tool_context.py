"""Testes de `tools/tool_context.py::principal_de` (P02 sub-entrega 5/N,
docs/autonomia/execucao.md).

`principal_de` é a extração, para reuso entre canais, da lógica que
`mcp_server.py::_principal_mcp` já tinha (introduzida na sub-entrega 2/N):
construir o `Principal` (autonomy/contracts.py) de uma chamada a partir de um
`ToolContext` e do TIPO de principal que o chamador já sabe que representa —
nunca inferido de `ctx.canal` sozinho. `test_mcp_server.py::TestPrincipalMcp`
já cobre que `_principal_mcp` continua produzindo o mesmo resultado depois do
refactor; este arquivo cobre a função compartilhada em si, incluindo os casos
que `_principal_mcp` (fixo em CLIENTE_ASSISTIDO) não exercita: os outros
quatro tipos de `TipoPrincipal` e o override explícito de `origem_humana`.
"""

import unittest

from autonomy.contracts import Principal, TipoPrincipal
from tools.tool_context import ToolContext, principal_de


class TestPrincipalDeDefaultDeOrigemHumana(unittest.TestCase):
    """Sem `origem_humana` explícito, o default é por TIPO — mesmo
    raciocínio de `tools/hermes_tools.py::_principal_simulado`."""

    def test_dono_interativo_default_origem_humana_true(self):
        ctx = ToolContext(user_uid="u1", canal="web")
        p = principal_de(ctx, TipoPrincipal.DONO_INTERATIVO)
        self.assertIs(p.origem_humana, True)
        self.assertTrue(p.eh_dono())

    def test_cliente_assistido_default_origem_humana_true(self):
        ctx = ToolContext(user_uid="u1", canal="mcp")
        p = principal_de(ctx, TipoPrincipal.CLIENTE_ASSISTIDO)
        self.assertIs(p.origem_humana, True)
        self.assertTrue(p.eh_dono())

    def test_rotina_cowork_default_origem_humana_false(self):
        ctx = ToolContext(user_uid=None, canal="cowork")
        p = principal_de(ctx, TipoPrincipal.ROTINA_COWORK)
        self.assertIs(p.origem_humana, False)
        self.assertFalse(p.eh_dono())

    def test_runner_servico_default_origem_humana_false(self):
        ctx = ToolContext(user_uid=None, canal="mcp")
        p = principal_de(ctx, TipoPrincipal.RUNNER_SERVICO)
        self.assertIs(p.origem_humana, False)
        self.assertFalse(p.eh_dono())
        # Achado documentado na docstring de `principal_de`: o MESMO texto de
        # canal ("mcp") produz tipos diferentes dependendo de quem chama —
        # aqui RUNNER_SERVICO (ex.: mcp_jobs.py), não CLIENTE_ASSISTIDO.
        self.assertEqual(p.canal, "mcp")

    def test_terceiro_portal_default_origem_humana_false(self):
        ctx = ToolContext(user_uid=None, canal="web")
        p = principal_de(ctx, TipoPrincipal.TERCEIRO_PORTAL)
        self.assertIs(p.origem_humana, False)
        self.assertFalse(p.eh_dono())


class TestPrincipalDeOverrideExplicito(unittest.TestCase):
    def test_origem_humana_explicita_sobrepoe_default_do_tipo(self):
        # Um runner de serviço disparado manualmente com o dono observando o
        # log é o caso deliberadamente coberto pelo parâmetro nomeado.
        ctx = ToolContext(user_uid="u1", canal="mcp")
        p = principal_de(ctx, TipoPrincipal.RUNNER_SERVICO, origem_humana=True)
        self.assertIs(p.origem_humana, True)

    def test_dono_interativo_pode_ser_marcado_como_nao_humano(self):
        ctx = ToolContext(user_uid="u1", canal="web")
        p = principal_de(ctx, TipoPrincipal.DONO_INTERATIVO, origem_humana=False)
        self.assertIs(p.origem_humana, False)


class TestPrincipalDePassthrough(unittest.TestCase):
    """uid e canal vêm do `ToolContext` sem alteração; o retorno é sempre um
    `Principal` de verdade (não um dict/proxy)."""

    def test_uid_e_canal_vem_do_contexto(self):
        ctx = ToolContext(user_uid="uid-xyz", canal="telegram")
        p = principal_de(ctx, TipoPrincipal.DONO_INTERATIVO)
        self.assertIsInstance(p, Principal)
        self.assertEqual(p.uid, "uid-xyz")
        self.assertEqual(p.canal, "telegram")

    def test_uid_none_e_preservado(self):
        ctx = ToolContext(user_uid=None, canal="mcp")
        p = principal_de(ctx, TipoPrincipal.RUNNER_SERVICO)
        self.assertIsNone(p.uid)


if __name__ == "__main__":
    unittest.main()
