"""Testes de `autonomy/contracts.py` — só tipos, sem I/O.

Cobre: `Principal.eh_dono()` para os cinco tipos, serialização de
`PolicyDecision.to_dict()` (enum -> valor, datetime -> isoformat, None
preservado), e que os defaults de `PolicyRequest`/`Mandato` não mudam sem
querer (regressão de contrato, já que outros módulos dependem desses
defaults).
"""

import unittest
from datetime import datetime, timezone

from autonomy.contracts import (
    ClasseEfeito,
    Decisao,
    EstadoAutonomia,
    Mandato,
    Principal,
    PolicyDecision,
    PolicyRequest,
    TipoPrincipal,
)


class TestPrincipalEhDono(unittest.TestCase):
    def test_dono_interativo_eh_dono(self):
        p = Principal(uid="u1", tipo=TipoPrincipal.DONO_INTERATIVO, canal="web")
        self.assertTrue(p.eh_dono())

    def test_cliente_assistido_eh_dono(self):
        p = Principal(uid="u1", tipo=TipoPrincipal.CLIENTE_ASSISTIDO, canal="mcp")
        self.assertTrue(p.eh_dono())

    def test_rotina_cowork_nao_eh_dono(self):
        p = Principal(uid=None, tipo=TipoPrincipal.ROTINA_COWORK, canal="mcp", origem_humana=False)
        self.assertFalse(p.eh_dono())

    def test_runner_servico_nao_eh_dono(self):
        p = Principal(uid=None, tipo=TipoPrincipal.RUNNER_SERVICO, canal="mcp", origem_humana=False)
        self.assertFalse(p.eh_dono())

    def test_terceiro_portal_nao_eh_dono(self):
        p = Principal(uid=None, tipo=TipoPrincipal.TERCEIRO_PORTAL, canal="web")
        self.assertFalse(p.eh_dono())


class TestPolicyDecisionToDict(unittest.TestCase):
    def test_serializa_enum_como_valor(self):
        d = PolicyDecision(
            decision=Decisao.ALLOW,
            policy_id="p1",
            policy_version=1,
            reason_code="ok",
        )
        self.assertEqual(d.to_dict()["decision"], "allow")

    def test_serializa_datetime_como_isoformat(self):
        quando = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
        d = PolicyDecision(
            decision=Decisao.REQUIRE_APPROVAL,
            policy_id="p1",
            policy_version=1,
            reason_code="ok",
            expires_at=quando,
        )
        self.assertEqual(d.to_dict()["expires_at"], quando.isoformat())

    def test_expires_at_none_permanece_none(self):
        d = PolicyDecision(decision=Decisao.DENY, policy_id="p1", policy_version=1, reason_code="x")
        self.assertIsNone(d.to_dict()["expires_at"])

    def test_constraints_checked_vira_lista(self):
        d = PolicyDecision(
            decision=Decisao.ALLOW, policy_id="p1", policy_version=1, reason_code="x",
            constraints_checked=("a", "b"),
        )
        self.assertEqual(d.to_dict()["constraints_checked"], ["a", "b"])


class TestDefaultsDeContrato(unittest.TestCase):
    """Regressão: outros módulos (policy.py) dependem destes defaults; uma
    mudança silenciosa aqui muda comportamento sem revisão explícita."""

    def test_policy_request_estado_autonomia_default_ativo(self):
        req = PolicyRequest(
            principal=Principal(uid="u1", tipo=TipoPrincipal.DONO_INTERATIVO, canal="web"),
            ferramenta="qualquer_tool",
            classe_efeito=ClasseEfeito.OBSERVACAO_AUTORIZADA,
        )
        self.assertEqual(req.estado_autonomia, EstadoAutonomia.ATIVO)
        self.assertEqual(req.mandatos_aplicaveis, ())
        self.assertEqual(req.argumentos_resolvidos, {})

    def test_mandato_revogado_default_false(self):
        m = Mandato(
            mandato_id="m1",
            finalidade="teste",
            destinatarios_recursos=("*",),
            classes_conteudo_permitidas=("geral",),
        )
        self.assertFalse(m.revogado)
        self.assertIsNone(m.valido_ate)
        self.assertIsNone(m.limite_por_janela)
        self.assertIsNone(m.usos_na_janela_atual)


if __name__ == "__main__":
    unittest.main()
