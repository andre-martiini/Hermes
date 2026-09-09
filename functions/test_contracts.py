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


class TestPrincipalOrigemHumanaDefaultPorTipo(unittest.TestCase):
    """P02 sub-entrega 15/N: `origem_humana` omitido não é mais `True`
    incondicional -- `Principal.__post_init__` deriva por `tipo`. Mesma
    regra que `tools/tool_context.py::principal_de` e
    `hermes_tools.py::_principal_simulado` já aplicavam por fora; agora é
    garantida pelo próprio tipo. Ver também test_tool_context.py, que cobre
    o helper por cima desta base."""

    def test_dono_interativo_omitido_e_true(self):
        p = Principal(uid="u1", tipo=TipoPrincipal.DONO_INTERATIVO, canal="web")
        self.assertIs(p.origem_humana, True)

    def test_cliente_assistido_omitido_e_true(self):
        p = Principal(uid="u1", tipo=TipoPrincipal.CLIENTE_ASSISTIDO, canal="mcp")
        self.assertIs(p.origem_humana, True)

    def test_rotina_cowork_omitido_e_false(self):
        p = Principal(uid=None, tipo=TipoPrincipal.ROTINA_COWORK, canal="cowork")
        self.assertIs(p.origem_humana, False)

    def test_runner_servico_omitido_e_false(self):
        p = Principal(uid=None, tipo=TipoPrincipal.RUNNER_SERVICO, canal="scheduler")
        self.assertIs(p.origem_humana, False)

    def test_terceiro_portal_omitido_e_false(self):
        p = Principal(uid=None, tipo=TipoPrincipal.TERCEIRO_PORTAL, canal="web")
        self.assertIs(p.origem_humana, False)

    def test_override_explicito_true_sobrepoe_tipo_nao_dono(self):
        # Caso legítimo já documentado: runner disparado manualmente com o
        # dono observando o log.
        p = Principal(uid="u1", tipo=TipoPrincipal.RUNNER_SERVICO, canal="mcp", origem_humana=True)
        self.assertIs(p.origem_humana, True)

    def test_override_explicito_false_sobrepoe_tipo_dono(self):
        p = Principal(uid="u1", tipo=TipoPrincipal.DONO_INTERATIVO, canal="web", origem_humana=False)
        self.assertIs(p.origem_humana, False)


class TestMandatoClassesConteudoPermitidasValidacao(unittest.TestCase):
    """P02 sub-entrega 15/N: seção 5.3 do plano, verbatim -- "Tipos 'outro' e
    rótulos livres não podem habilitar envio autônomo". Estrutural agora,
    não só documentado: `Mandato.__post_init__` recusa a construção."""

    def _mandato(self, classes):
        return Mandato(
            mandato_id="m1",
            finalidade="teste",
            destinatarios_recursos=("*",),
            classes_conteudo_permitidas=classes,
        )

    def test_classe_outro_e_rejeitada(self):
        with self.assertRaises(ValueError):
            self._mandato(("confirmacao_reuniao", "outro"))

    def test_classe_outro_maiuscula_tambem_e_rejeitada(self):
        with self.assertRaises(ValueError):
            self._mandato(("Outro",))

    def test_classe_em_branco_e_rejeitada(self):
        with self.assertRaises(ValueError):
            self._mandato(("confirmacao_reuniao", "   "))

    def test_classe_vazia_e_rejeitada(self):
        with self.assertRaises(ValueError):
            self._mandato(("",))

    def test_classes_reais_sao_aceitas(self):
        m = self._mandato(("confirmacao_reuniao", "cobranca_documento"))
        self.assertEqual(m.classes_conteudo_permitidas, ("confirmacao_reuniao", "cobranca_documento"))

    def test_tupla_vazia_e_aceita(self):
        # Mandato que não permite nenhuma classe -- degenerado, mas não é o
        # caso que a seção 5.3 proíbe (não há "outro" nem rótulo ali).
        m = self._mandato(())
        self.assertEqual(m.classes_conteudo_permitidas, ())


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
        self.assertIsNone(m.orcamento_maximo)


if __name__ == "__main__":
    unittest.main()
