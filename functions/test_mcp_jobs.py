"""Testes para o trigger assíncrono de jobs MCP (mcp_jobs.py::on_mcp_job_created).

Cobre duas gerações de mudança:

- P02 sub-entrega 9/N: a wiring de identidade e preflight de política -- o job
  sempre representa `TipoPrincipal.RUNNER_SERVICO` com `origem_humana=False`
  (decisão de André — nunca DONO_INTERATIVO/CLIENTE_ASSISTIDO só porque o uid
  bate com o dono), e o preflight `autonomy.policy.decisao_piso` é chamado
  antes de executar a tool.
- P01 sub-entrega 5/N (achado A10): reivindicação transacional sobre o estado
  ATUAL do documento (não o snapshot do evento, que pode estar desatualizado
  diante de entrega duplicada do gatilho), normalização do estado de erro
  (inclusive quando a tool devolve uma mensagem de erro sem levantar exceção
  -- "falso sucesso"), resultado estruturado preservado quando cabe no limite
  de tamanho, e `expira_em` como Timestamp em vez de inteiro Unix.

Hoje nenhuma das três tools que passam por este trigger (gerar_relatorio,
ler_documento_na_integra, buscar_e_analisar_email) está classificada em
`autonomy.policy.CLASSE_EFEITO_PISO`, então `decisao_piso` sempre devolve
`None` em produção — os testes de DENY/PREPARE_ONLY abaixo simulam uma
classificação futura (mockando `decisao_piso` diretamente) para provar que o
código de bloqueio em si está correto, já que não há hoje nenhum caminho real
para exercitá-lo.
"""
import datetime as dt
import unittest
from unittest import mock

import mcp_jobs
from autonomy.contracts import Decisao, PolicyDecision, TipoPrincipal
from autonomy.policy import CLASSE_EFEITO_PISO


# ---------------------------------------------------------------------------
# Doubles fiéis do protocolo real do Firestore (mesmo padrão já usado em
# test_idempotency.py/test_agent_requests.py/test_outbox_aprovacao.py):
# implementam o suficiente de Transaction/DocumentReference/DocumentSnapshot
# para que o decorator real `@firestore.transactional` exercite o mesmo
# caminho de código de produção.
# ---------------------------------------------------------------------------


class _MockDocSnap:
    def __init__(self, doc_id, data, ref=None):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None
        self.reference = ref

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRef:
    """Identidade por caminho (col + doc_id), não por instância Python: o
    código de produção agora constrói `ref` a partir de `db.collection(...).
    document(...)` (não mais de `snap.reference` -- ver comentário em
    mcp_jobs.py::on_mcp_job_created), então cada chamada gera um objeto NOVO
    apontando para o mesmo documento. `.updates` fica guardado na coleção,
    por doc_id, para continuar visível ao teste independentemente de qual
    instância de `_MockDocRef` recebeu a escrita -- mesma semântica do
    Firestore real, onde referências são objetos de valor baratos."""

    def __init__(self, col, doc_id):
        self.col = col
        self.id = doc_id

    @property
    def updates(self):
        return self.col._updates.setdefault(self.id, [])

    def get(self, transaction=None):
        # Sempre lê o estado ATUAL de `col._docs` -- é isso que permite aos
        # testes simular uma mudança de estado entre a captura do evento e a
        # execução do gatilho (a lacuna que a reivindicação transacional
        # existe para fechar). `transaction` é aceito só para casar a
        # assinatura real; o double não isola leituras por transação.
        data = self.col._docs.get(self.id)
        return _MockDocSnap(self.id, data, self)

    def update(self, data):
        self.updates.append(dict(data))
        if self.id not in self.col._docs:
            self.col._docs[self.id] = {}
        self.col._docs[self.id].update(data)


class _MockCollection:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self._docs: dict[str, dict] = {}
        self._updates: dict[str, list] = {}

    def document(self, doc_id):
        return _MockDocRef(self, doc_id)


class _MockTransaction:
    """Double fiel do protocolo real (google.cloud.firestore_v1.transaction.
    Transaction): implementa _begin/_clean_up/_commit/_rollback/_max_attempts/
    _read_only para que o decorator @firestore.transactional real exercite o
    mesmo caminho de código de produção, mesmo padrão já usado em
    test_idempotency.py/test_agent_requests.py/test_outbox_aprovacao.py."""

    def __init__(self):
        self._read_only = False
        self._id = b"mock-tx-id"
        self._max_attempts = 5

    def get(self, doc_ref):
        return doc_ref.get()

    def update(self, doc_ref, data):
        doc_ref.update(data)

    def set(self, doc_ref, data, merge=False):
        if doc_ref.id not in doc_ref.col._docs:
            doc_ref.col._docs[doc_ref.id] = {}
        if merge:
            doc_ref.col._docs[doc_ref.id].update(data)
        else:
            doc_ref.col._docs[doc_ref.id] = dict(data)

    def _rollback(self):
        pass

    def _commit(self):
        pass

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or b"mock-tx-id"


class _MockDB:
    def __init__(self):
        self._collections: dict[str, _MockCollection] = {}

    def collection(self, name: str) -> _MockCollection:
        if name not in self._collections:
            self._collections[name] = _MockCollection(self, name)
        return self._collections[name]

    def transaction(self):
        return _MockTransaction()


class _BrokenMockTransaction(_MockTransaction):
    """Simula falha real de transação (ex.: Firestore indisponível ao iniciar
    a transação). Falha em ``_begin`` -- antes de qualquer leitura/escrita --
    para provar que nenhuma escrita desprotegida acontece como fallback."""

    def _begin(self, retry_id=None):
        raise RuntimeError("Firestore indisponível (simulado)")


class _MockDBTransacaoQuebrada(_MockDB):
    def transaction(self):
        return _BrokenMockTransaction()


class _MockDBSemTransacao:
    """Mock de DB que não implementa .transaction() -- simula um backend sem
    suporte a transação real (achado A04, reaplicado aqui na P01 sub-entrega
    5/N: não deve haver fallback para leitura/escrita desprotegida)."""

    def __init__(self, real_db: _MockDB):
        self._real = real_db

    def collection(self, name):
        return self._real.collection(name)


def _make_event(db, job, job_id="job-teste"):
    """Cria o job em `db` (refletindo o que `criar_job` grava) e devolve um
    evento cujo `.data` é o snapshot capturado NAQUELE MOMENTO -- igual ao
    que o gatilho real recebe. Um teste pode mutar `ref.col._docs[job_id]`
    depois de chamar isto para simular uma mudança de estado ocorrida entre a
    captura do evento e a execução do gatilho."""
    ref = db.collection(mcp_jobs.COLECAO).document(job_id)
    if job is not None:
        ref.col._docs[job_id] = dict(job)
    snap = _MockDocSnap(job_id, job, ref)
    event = type("_FakeEvent", (), {})()
    event.data = snap
    return event, ref


class TestOnMcpJobCreatedIgnoraCasosForaDoEscopo(unittest.TestCase):
    def test_ignora_snapshot_com_exists_false(self):
        db = _MockDB()
        event, ref = _make_event(db, None)
        mcp_jobs.on_mcp_job_created.__wrapped__(event)
        self.assertEqual(ref.updates, [])

    def test_ignora_job_que_nao_esta_processando(self):
        db = _MockDB()
        event, ref = _make_event(db, {"status": "done"})
        with mock.patch("mcp_jobs._db", return_value=db):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)
        self.assertEqual(ref.updates, [])


class TestReivindicacaoTransacional(unittest.TestCase):
    """P01 sub-entrega 5/N (achado A10, item 1): o gatilho decide com base no
    estado ATUAL do documento, não no snapshot capturado no momento do
    evento."""

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

    def test_ignora_evento_duplicado_quando_job_ja_foi_reivindicado(self):
        """Núcleo do achado: gatilhos do Firestore são "ao menos uma vez".
        Se, entre a criação do evento e esta execução, outra invocação do
        MESMO evento já reivindicou e concluiu o job, reexecutar a tool seria
        um efeito duplicado (ex.: dois relatórios gerados, duas buscas de
        e-mail). O snapshot do evento ainda diz 'processing' -- só a leitura
        transacional do estado atual revela que já não é mais."""
        db = _MockDB()
        event, ref = _make_event(db, self._job())
        # Simula que outra invocação já reivindicou e concluiu o job entre a
        # captura do evento (ainda 'processing' em `event.data`) e esta.
        ref.col._docs[ref.id]["status"] = "done"
        ref.col._docs[ref.id]["resultado"] = "resultado da primeira invocação"

        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso") as decisao_mock, \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        decisao_mock.assert_not_called()
        self.assertEqual(ref.updates, [])
        self.assertEqual(ref.col._docs[ref.id]["resultado"], "resultado da primeira invocação")

    def test_ignora_evento_duplicado_quando_ja_reivindicado_mas_ainda_processando(self):
        """Mesma proteção quando a primeira invocação já reivindicou (marcou
        `reivindicado_em`) mas ainda não terminou -- não só quando já
        terminou. Sem checar `reivindicado_em`, duas invocações concorrentes
        do mesmo evento poderiam reivindicar as duas, já que o `status` só
        muda para 'done'/'error' no final."""
        db = _MockDB()
        event, ref = _make_event(db, self._job())
        ref.col._docs[ref.id]["reivindicado_em"] = "já-reivindicado"

        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso") as decisao_mock, \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        decisao_mock.assert_not_called()
        self.assertEqual(ref.updates, [])

    def test_reivindica_e_marca_reivindicado_em_antes_de_executar(self):
        decisao = PolicyDecision(decision=Decisao.ALLOW, policy_id="p", policy_version=1, reason_code="ok")
        db = _MockDB()
        event, ref = _make_event(db, self._job())

        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute", return_value="Relatório ok."):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        self.assertIn("reivindicado_em", ref.updates[0])
        self.assertEqual(ref.updates[-1]["status"], "done")

    def test_backend_sem_suporte_a_transacao_recusa_sem_executar(self):
        db_real = _MockDB()
        event, ref = _make_event(db_real, self._job())
        db_sem_txn = _MockDBSemTransacao(db_real)

        with mock.patch("mcp_jobs._db", return_value=db_sem_txn), \
             mock.patch("autonomy.policy.decisao_piso") as decisao_mock, \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        decisao_mock.assert_not_called()
        self.assertEqual(ref.updates[-1]["status"], "error")
        self.assertEqual(ref.updates[-1]["erro_tipo"], mcp_jobs.ERRO_TIPO_CONFIGURACAO)

    def test_falha_real_de_transacao_nao_escreve_nada(self):
        """Achado A04 reaplicado: quando a transação em si falha (ex.:
        Firestore indisponível), não há fallback para escrita desprotegida
        -- o job fica sem nenhuma escrita, visível como 'ainda processando'
        no próximo poll, em vez de arriscar sobrescrever uma reivindicação
        concorrente."""
        db = _MockDBTransacaoQuebrada()
        event, ref = _make_event(db, self._job())

        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso") as decisao_mock, \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        decisao_mock.assert_not_called()
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
        db = _MockDB()
        event, ref = _make_event(db, self._job())
        capturado = {}

        def fake_decisao_piso(db_arg, principal, nome, argumentos):
            capturado["principal"] = principal
            capturado["nome"] = nome
            capturado["argumentos"] = argumentos
            return None  # tool não classificada no piso -> segue normalmente

        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", side_effect=fake_decisao_piso), \
             mock.patch("tools.hermes_tools.execute", return_value="Relatório pronto.") as execute_mock:
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
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-allow"), job_id="job-allow")
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute", return_value="Relatório pronto.") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_called_once()
        self.assertEqual(ref.updates[-1]["status"], "done")

    def test_deny_bloqueia_execucao_sem_chamar_execute(self):
        decisao = PolicyDecision(
            decision=Decisao.DENY, policy_id="p", policy_version=1,
            reason_code="teste_deny", motivo_legivel="Bloqueado no teste.",
        )
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-deny"), job_id="job-deny")
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        self.assertEqual(ref.updates[-1]["status"], "error")
        self.assertIn("Bloqueado no teste.", ref.updates[-1]["erro"])
        self.assertEqual(ref.updates[-1]["erro_tipo"], mcp_jobs.ERRO_TIPO_POLITICA)
        self.assertEqual(
            ref.updates[-1]["bloqueio_politica"],
            {"decision": "deny", "reason_code": "teste_deny"},
        )

    def test_prepare_only_bloqueia_execucao_sem_chamar_execute(self):
        decisao = PolicyDecision(
            decision=Decisao.PREPARE_ONLY, policy_id="p", policy_version=1,
            reason_code="teste_prepare", motivo_legivel="Somente preparação no teste.",
        )
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-prepare"), job_id="job-prepare")
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        self.assertEqual(ref.updates[-1]["status"], "error")
        self.assertIn("somente-preparação", ref.updates[-1]["erro"])
        self.assertEqual(ref.updates[-1]["bloqueio_politica"]["decision"], "prepare_only")
        self.assertEqual(ref.updates[-1]["erro_tipo"], mcp_jobs.ERRO_TIPO_POLITICA)

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
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-approval"), job_id="job-approval")
        with mock.patch("mcp_jobs._db", return_value=db), \
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
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-defer"), job_id="job-defer")
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute") as execute_mock:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        execute_mock.assert_not_called()
        self.assertEqual(ref.updates[-1]["status"], "error")
        self.assertEqual(ref.updates[-1]["bloqueio_politica"]["decision"], "defer")


class TestEstadoDeErroNormalizadoEResultadoEstruturado(unittest.TestCase):
    """P01 sub-entrega 5/N (achado A10, itens 2 e 3)."""

    def _job(self, **overrides):
        job = {
            "status": "processing",
            "tool": "gerar_relatorio",
            "uid": "dono-uid",
            "job_id": "job-teste",
            "session_id": "sess-1",
            "task_id": None,
            "arguments": {},
        }
        job.update(overrides)
        return job

    def _allow(self):
        return PolicyDecision(decision=Decisao.ALLOW, policy_id="p", policy_version=1, reason_code="ok")

    def test_resultado_string_com_prefixo_de_aviso_normaliza_para_error_sem_falso_sucesso(self):
        """Núcleo do achado: as três tools deste trigger sinalizam falha no
        próprio texto (prefixo "⚠️", convenção herdada do canal Telegram,
        mesmo contrato de mcp_server.py::_looks_like_error) em vez de
        levantar exceção ou devolver um dict com "erro". Sem esta checagem,
        o job virava "done" com a mensagem de erro no lugar do resultado."""
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-aviso"), job_id="job-aviso")
        resultado_tool = "⚠️ Gemini API não configurada."
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=self._allow()), \
             mock.patch("tools.hermes_tools.execute", return_value=resultado_tool):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        ultimo = ref.updates[-1]
        self.assertEqual(ultimo["status"], "error")
        self.assertEqual(ultimo["erro"], resultado_tool)
        self.assertEqual(ultimo["erro_tipo"], mcp_jobs.ERRO_TIPO_RESULTADO)

    def test_resultado_string_com_prefixo_erro_pipe_tambem_normaliza(self):
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-erro-pipe"), job_id="job-erro-pipe")
        resultado_tool = "ERRO|falha ao acessar o Drive"
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=self._allow()), \
             mock.patch("tools.hermes_tools.execute", return_value=resultado_tool):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        ultimo = ref.updates[-1]
        self.assertEqual(ultimo["status"], "error")
        self.assertEqual(ultimo["erro_tipo"], mcp_jobs.ERRO_TIPO_RESULTADO)

    def test_resultado_dict_com_chave_erro_tambem_normaliza(self):
        """Caminho defensivo: `execute()` é o dispatcher genérico usado para
        qualquer tool, então mesmo que nenhuma das três tools deste trigger
        devolva hoje um dict com "erro", o trigger não deve tratá-lo como
        sucesso se algum dia devolver."""
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-dict-erro"), job_id="job-dict-erro")
        resultado_tool = {"erro": "Documento não encontrado."}
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=self._allow()), \
             mock.patch("tools.hermes_tools.execute", return_value=resultado_tool):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        ultimo = ref.updates[-1]
        self.assertEqual(ultimo["status"], "error")
        self.assertEqual(ultimo["erro"], "Documento não encontrado.")
        self.assertEqual(ultimo["erro_tipo"], mcp_jobs.ERRO_TIPO_RESULTADO)

    def test_resultado_string_normal_continua_gravando_done(self):
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-ok"), job_id="job-ok")
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=self._allow()), \
             mock.patch("tools.hermes_tools.execute", return_value="# Relatório\n\nConteúdo normal."):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        ultimo = ref.updates[-1]
        self.assertEqual(ultimo["status"], "done")
        self.assertEqual(ultimo["resultado"], "# Relatório\n\nConteúdo normal.")
        self.assertFalse(ultimo["truncado"])

    def test_resultado_estruturado_e_gravado_no_formato_nativo_nao_como_string_json(self):
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-estruturado"), job_id="job-estruturado")
        resultado_tool = {"relatorio": {"total": 42, "itens": [1, 2, 3]}}
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=self._allow()), \
             mock.patch("tools.hermes_tools.execute", return_value=resultado_tool):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        ultimo = ref.updates[-1]
        self.assertEqual(ultimo["status"], "done")
        self.assertIsInstance(ultimo["resultado"], dict)
        self.assertEqual(ultimo["resultado"], resultado_tool)

    def test_resultado_estruturado_grande_demais_cai_para_string_truncada(self):
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-grande"), job_id="job-grande")
        resultado_tool = {"texto": "x" * (mcp_jobs._MAX_RESULTADO_CHARS + 1000)}
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=self._allow()), \
             mock.patch("tools.hermes_tools.execute", return_value=resultado_tool):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        ultimo = ref.updates[-1]
        self.assertEqual(ultimo["status"], "done")
        self.assertIsInstance(ultimo["resultado"], str)
        self.assertTrue(ultimo["truncado"])
        self.assertTrue(ultimo["resultado"].endswith("[...resultado truncado...]"))

    def test_excecao_nao_tratada_normaliza_erro_tipo(self):
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-excecao"), job_id="job-excecao")
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=self._allow()), \
             mock.patch("tools.hermes_tools.execute", side_effect=RuntimeError("boom")):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        ultimo = ref.updates[-1]
        self.assertEqual(ultimo["status"], "error")
        self.assertEqual(ultimo["erro"], "boom")
        self.assertEqual(ultimo["erro_tipo"], mcp_jobs.ERRO_TIPO_EXCECAO)


class TestExpiraEmComoTimestamp(unittest.TestCase):
    """P01 sub-entrega 5/N (achado A10, item 4): `expira_em` precisa ser um
    tipo elegível para política de TTL do Firestore (Timestamp), não um
    inteiro Unix -- mesmo padrão de core/idempotency.py::expires_at."""

    def _job(self, **overrides):
        job = {
            "status": "processing",
            "tool": "gerar_relatorio",
            "uid": "dono-uid",
            "job_id": "job-teste",
            "session_id": "sess-1",
            "task_id": None,
            "arguments": {},
        }
        job.update(overrides)
        return job

    def test_expira_em_e_datetime_no_caminho_done(self):
        decisao = PolicyDecision(decision=Decisao.ALLOW, policy_id="p", policy_version=1, reason_code="ok")
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-ttl-done"), job_id="job-ttl-done")
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute", return_value="ok"):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        self.assertIsInstance(ref.updates[-1]["expira_em"], dt.datetime)
        self.assertIsNotNone(ref.updates[-1]["expira_em"].tzinfo)

    def test_expira_em_e_datetime_no_caminho_error_por_excecao(self):
        decisao = PolicyDecision(decision=Decisao.ALLOW, policy_id="p", policy_version=1, reason_code="ok")
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-ttl-erro"), job_id="job-ttl-erro")
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute", side_effect=RuntimeError("boom")):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        self.assertIsInstance(ref.updates[-1]["expira_em"], dt.datetime)

    def test_expira_em_e_datetime_no_caminho_bloqueado_pela_politica(self):
        decisao = PolicyDecision(
            decision=Decisao.DENY, policy_id="p", policy_version=1,
            reason_code="teste_deny", motivo_legivel="Bloqueado.",
        )
        db = _MockDB()
        event, ref = _make_event(db, self._job(job_id="job-ttl-politica"), job_id="job-ttl-politica")
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=decisao), \
             mock.patch("tools.hermes_tools.execute"):
            mcp_jobs.on_mcp_job_created.__wrapped__(event)

        self.assertIsInstance(ref.updates[-1]["expira_em"], dt.datetime)


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
