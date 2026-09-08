"""Testes para o trigger assíncrono de jobs MCP (mcp_jobs.py::on_mcp_job_created).

Cobre a wiring de identidade e preflight de política adicionada na P02
sub-entrega 9/N: o job sempre representa `TipoPrincipal.RUNNER_SERVICO` com
`origem_humana=False` (decisão de André — nunca DONO_INTERATIVO/CLIENTE_ASSISTIDO
só porque o uid bate com o dono), e o preflight `autonomy.policy.decisao_piso`
é chamado antes de executar a tool.

Hoje nenhuma das três tools que passam por este trigger (gerar_relatorio,
ler_documento_na_integra, buscar_e_analisar_email) está classificada em
`autonomy.policy.CLASSE_EFEITO_PISO`, então `decisao_piso` sempre devolve
`None` em produção — os testes de DENY/PREPARE_ONLY abaixo simulam uma
classificação futura (mockando `decisao_piso` diretamente) para provar que o
código de bloqueio em si está correto, já que não há hoje nenhum caminho real
para exercitá-lo.

Nenhum destes testes existia antes desta sub-entrega — não havia nenhuma
cobertura para `on_mcp_job_created` no repositório.
"""
import unittest
from unittest import mock

import mcp_jobs
from autonomy.contracts import Decisao, PolicyDecision, TipoPrincipal
from autonomy.policy import CLASSE_EFEITO_PISO


class _FakeRef:
    def __init__(self):
        self.updates = []

    def update(self, payload):
        self.updates.append(payload)


class _FakeSnap:
    def __init__(self, data, ref):
        self.exists = data is not None
        self._data = data or {}
        self.reference = ref

    def to_dict(self):
        return dict(self._data)


class _FakeEvent:
    def __init__(self, data):
        self.data = data


def _make_event(job):
    ref = _FakeRef()
    snap = _FakeSnap(job, ref)
    return _FakeEvent(snap), ref


class TestOnMcpJobCreatedIgnoraCasosForaDoEscopo(unittest.TestCase):
    def test_ignora_snapshot_com_exists_false(self):
        event, ref = _make_event(None)
        mcp_jobs.on_mcp_job_created.__wrapped__(event)
        self.assertEqual(ref.updates, [])

    def test_ignora_job_que_nao_esta_processando(self):
        event, ref = _make_event({"status": "done"})
        mcp_jobs.on_mcp_job_created.__wrapped__(event)
        self.assertEqual(ref.updates, [])


class TestOnMcpJobCreatedPrincipalEPreflight(unittest.TestCase):
    def _job(self, **overrides):
        job = {
            "status": "processing",
            "tool": "gerar_relatorio",
            "uid": "dono-uid",
            "job_id": "job-teste",
            "session_id": "sess-1",
            "task_id": None,
            "arguments": {"tipo": "financeiro"},
        }
        job.update(overrides)
        return job

    def test_principal_e_sempre_runner_servico_sem_humano_presente(self):
        """P02 passo 1 / decisão de André: este canal nunca é DONO_INTERATIVO
        ou CLIENTE_ASSISTIDO, mesmo que uid seja o do dono — é um job
        assíncrono, sem garantia de sessão acompanhada."""
        event, ref = _make_event(self._job())
        capturado = {}

        def fake_decisao_piso(db, principal, nome, argumentos):
            capturado["principal"] = principal
            capturado["nome"] = nome
            capturado["argumentos"] = argumentos
            return None  # tool não classificada no piso -> segue normalmente

        with mock.patch("mcp_jobs._db", return_value=object()), \
             mock.patch("autonomy.policy.decisao_piso", side_effect=fake_decisao_piso), \
             mock.patch("tools.hermes_tools.execute", return_value={"ok": True}) as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        principal = capturado["principal"]
        self.assertEqual(principal.tipo, TipoPrincipal.RUNNER_SERVICO)
        self.assertFalse(principal.origem_humana)
        self.assertEqual(principal.uid, "dono-uid")
        self.assertEqual(principal.canal, "mcp")
        self.assertEqual(capturado["nome"], "gerar_relatorio")
        self.assertEqual(capturado["argumentos"], {"tipo": "financeiro"})
        execute_mock.assert_called_once()
        self.assertEqual(ref.updates[-1]["status"], "done")

    def test_allow_prossegue_e_grava_resultado(self):
        decisao = PolicyDecision(
            decision=Decisao.ALLOW, policy_id="p", policy_version=1, reason_code="ok",
        )
        event, ref = _make_event(self._job(job_id="job-allow"))
        with mock.patch("mcp_jobs._db", return_value=object()), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute", return_value={"ok": True}) as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_called_once()
        self.assertEqual(ref.updates[-1]["status"], "done")

    def test_deny_bloqueia_execucao_sem_chamar_execute(self):
        decisao = PolicyDecision(
            decision=Decisao.DENY, policy_id="p", policy_version=1,
            reason_code="teste_deny", motivo_legivel="Bloqueado no teste.",
        )
        event, ref = _make_event(self._job(job_id="job-deny"))
        with mock.patch("mcp_jobs._db", return_value=object()), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        self.assertEqual(ref.updates[-1]["status"], "error")
        self.assertIn("Bloqueado no teste.", ref.updates[-1]["erro"])
        self.assertEqual(
            ref.updates[-1]["bloqueio_politica"],
            {"decision": "deny", "reason_code": "teste_deny"},
        )

    def test_prepare_only_bloqueia_execucao_sem_chamar_execute(self):
        decisao = PolicyDecision(
            decision=Decisao.PREPARE_ONLY, policy_id="p", policy_version=1,
            reason_code="teste_prepare", motivo_legivel="Somente preparação no teste.",
        )
        event, ref = _make_event(self._job(job_id="job-prepare"))
        with mock.patch("mcp_jobs._db", return_value=object()), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        self.assertEqual(ref.updates[-1]["status"], "error")
        self.assertIn("somente-preparação", ref.updates[-1]["erro"])
        self.assertEqual(ref.updates[-1]["bloqueio_politica"]["decision"], "prepare_only")

    def test_require_approval_bloqueia_execucao_sem_chamar_execute(self):
        """Achado da revisão adversarial (P02 sub-entrega 9/N): sem este
        teste, um `REQUIRE_APPROVAL` cairia no fluxo de execução direta —
        diferente de mcp_server.py, este trigger não tem nenhum mecanismo de
        confirmação para satisfazer o "requer aprovação", então precisa
        bloquear, não deixar passar."""
        decisao = PolicyDecision(
            decision=Decisao.REQUIRE_APPROVAL, policy_id="p", policy_version=1,
            reason_code="teste_approval",
        )
        event, ref = _make_event(self._job(job_id="job-approval"))
        with mock.patch("mcp_jobs._db", return_value=object()), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        self.assertEqual(ref.updates[-1]["status"], "error")
        self.assertIn("mecanismo de confirmação", ref.updates[-1]["erro"])
        self.assertEqual(ref.updates[-1]["bloqueio_politica"]["decision"], "require_approval")

    def test_defer_bloqueia_execucao_sem_chamar_execute(self):
        decisao = PolicyDecision(
            decision=Decisao.DEFER, policy_id="p", policy_version=1,
            reason_code="teste_defer",
        )
        event, ref = _make_event(self._job(job_id="job-defer"))
        with mock.patch("mcp_jobs._db", return_value=object()), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        self.assertEqual(ref.updates[-1]["status"], "error")
        self.assertEqual(ref.updates[-1]["bloqueio_politica"]["decision"], "defer")


class TestClasseEfeitoPisoNaoCobreTresToolsAssincronas(unittest.TestCase):
    """Fixa a premissa que torna o preflight desta sub-entrega um no-op hoje
    (achado da revisão adversarial: sem isto, uma futura classificação em
    `CLASSE_EFEITO_PISO` mudaria o comportamento de `on_mcp_job_created` sem
    NENHUM teste avisando)."""

    def test_tools_assincronas_nao_classificadas_no_piso_hoje(self):
        for nome in ("gerar_relatorio", "ler_documento_na_integra", "buscar_e_analisar_email"):
            self.assertIsNone(CLASSE_EFEITO_PISO.get(nome))


if __name__ == "__main__":
    unittest.main()
