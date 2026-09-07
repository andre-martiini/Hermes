"""Testes unitários para mcp_jobs.py (execução assíncrona de tools longas do
canal MCP via gatilho do Firestore).

Cobre o achado do plano de autonomia (P01 passo 5-6, achado A10):

1. Reentrega do evento do gatilho não pode rodar a mesma tool duas vezes —
   `_claim` usa leitura+escrita transacional (fresca, não o snapshot do
   evento) para garantir que só uma execução prossiga por job.
2. Um claim abandonado (execução anterior morreu sem concluir) não é
   reprocessado automaticamente — é marcado como erro, porque a tool pode
   não ser idempotente.
3. O resultado da tool é classificado como erro (não sucesso) quando indica
   erro pela convenção já usada em mcp_server.py (dict com `erro` truthy,
   ou string `ERRO|.../⚠️...`).
4. `expira_em` é gravado como datetime timezone-aware, não inteiro Unix
   (compatibilidade com TTL do Firestore).
5. `ler_job` preserva o contrato público de três valores (`processing` /
   `done` / `error`) mesmo com o novo estado interno `em_execucao`.

Cobre também o achado do Codex na PR #189 (P1): encontrar um claim
`em_execucao` ainda dentro de `CLAIM_EXPIRA_APOS` deve LEVANTAR
`ClaimAindaValidoError`, não devolver None em silêncio — devolver None
silenciosamente faria `on_mcp_job_created` retornar normalmente, e o Cloud
Functions registraria essa invocação como bem-sucedida mesmo que a tool
nunca tenha rodado para aquele job (ver docstring de `mcp_jobs.py` para o
cenário completo: commit ambíguo do claim + entrega duplicada do Pub/Sub
chegando enquanto o claim ainda parece válido).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

import mcp_jobs


class _MockDocSnap:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRef:
    def __init__(self, col, doc_id: str):
        self.col = col
        self.id = doc_id
        self.reference = self

    def get(self, transaction=None):
        return _MockDocSnap(self.id, self.col._docs.get(self.id))

    def set(self, data, merge=False):
        if merge and self.id in self.col._docs:
            self.col._docs[self.id].update(data)
        else:
            self.col._docs[self.id] = dict(data)

    def update(self, data):
        if self.id not in self.col._docs:
            raise Exception(f"documento '{self.id}' nao existe (update exige doc existente)")
        self.col._docs[self.id].update(data)


class _MockCollection:
    def __init__(self):
        self._docs: dict[str, dict] = {}

    def document(self, doc_id: str):
        return _MockDocRef(self, doc_id)


class _MockTransaction:
    def __init__(self):
        self._id = b"mock-tx-id"
        self._max_attempts = 5
        self._read_only = False

    def get(self, doc_ref):
        return doc_ref.get()

    def set(self, doc_ref, data, merge=False):
        doc_ref.set(data, merge=merge)

    def update(self, doc_ref, data):
        doc_ref.update(data)

    def _rollback(self):
        pass

    def _commit(self):
        pass

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or b"mock-tx-id"


class _MockDb:
    def __init__(self):
        self._collections: dict[str, _MockCollection] = {}

    def collection(self, name: str) -> _MockCollection:
        if name not in self._collections:
            self._collections[name] = _MockCollection()
        return self._collections[name]

    def transaction(self):
        return _MockTransaction()


def _job_basico(**overrides) -> dict:
    dados = {
        "job_id": "mcpjob-1",
        "uid": "user-1",
        "tool": "gerar_relatorio",
        "arguments": {},
        "session_id": None,
        "task_id": None,
        "status": mcp_jobs.STATUS_PROCESSING,
        "criado_em": 0,
    }
    dados.update(overrides)
    return dados


class TestResultadoIndicaErro(unittest.TestCase):
    def test_dict_com_erro_truthy(self):
        self.assertEqual(mcp_jobs._resultado_indica_erro({"erro": "deu ruim"}), "deu ruim")

    def test_dict_com_erro_vazio_nao_e_erro(self):
        self.assertIsNone(mcp_jobs._resultado_indica_erro({"erro": ""}))
        self.assertIsNone(mcp_jobs._resultado_indica_erro({"ok": True}))

    def test_string_prefixo_erro(self):
        self.assertEqual(
            mcp_jobs._resultado_indica_erro("ERRO|algo quebrou"),
            "ERRO|algo quebrou",
        )

    def test_string_prefixo_alerta(self):
        self.assertEqual(
            mcp_jobs._resultado_indica_erro("⚠️ atenção parcial"),
            "⚠️ atenção parcial",
        )

    def test_string_normal_nao_e_erro(self):
        self.assertIsNone(mcp_jobs._resultado_indica_erro("tudo certo"))

    def test_outros_tipos_nao_sao_erro(self):
        self.assertIsNone(mcp_jobs._resultado_indica_erro(["ok"]))
        self.assertIsNone(mcp_jobs._resultado_indica_erro(None))


class TestClaim(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()
        self.col = self.db.collection(mcp_jobs.COLECAO)

    def test_claim_ganha_quando_status_processing(self):
        self.col._docs["job-1"] = _job_basico()
        ref = self.col.document("job-1")

        dados = mcp_jobs._claim(self.db, ref)

        self.assertIsNotNone(dados)
        self.assertEqual(dados["status"], mcp_jobs.STATUS_PROCESSING)  # snapshot pre-claim devolvido
        doc = self.col._docs["job-1"]
        self.assertEqual(doc["status"], mcp_jobs.STATUS_EM_EXECUCAO)
        self.assertIn("claimed_em", doc)
        self.assertIsInstance(doc["claimed_em"], datetime)

    def test_claim_concorrente_apenas_um_ganha(self):
        """Duas 'invocações' tentando o claim da mesma entrega duplicada de
        evento — só a primeira deve prosseguir; a segunda encontra
        em_execucao recente e LEVANTA ClaimAindaValidoError (achado do
        Codex na PR #189: não pode devolver None em silêncio aqui, ou a
        invocação seria registrada como bem-sucedida sem a tool ter
        rodado), sem tocar o documento."""
        self.col._docs["job-2"] = _job_basico()
        ref = self.col.document("job-2")

        primeira = mcp_jobs._claim(self.db, ref)
        doc_apos_primeira = dict(self.col._docs["job-2"])

        with self.assertRaises(mcp_jobs.ClaimAindaValidoError):
            mcp_jobs._claim(self.db, ref)

        self.assertIsNotNone(primeira)
        # Documento não foi alterado pela segunda tentativa.
        self.assertEqual(self.col._docs["job-2"], doc_apos_primeira)

    def test_claim_ja_done_nao_prossegue(self):
        self.col._docs["job-3"] = _job_basico(status=mcp_jobs.STATUS_DONE, resultado="ok")
        ref = self.col.document("job-3")

        self.assertIsNone(mcp_jobs._claim(self.db, ref))
        # Documento intocado.
        self.assertEqual(self.col._docs["job-3"]["status"], mcp_jobs.STATUS_DONE)

    def test_claim_ja_error_nao_prossegue(self):
        self.col._docs["job-4"] = _job_basico(status=mcp_jobs.STATUS_ERROR, erro="x")
        ref = self.col.document("job-4")

        self.assertIsNone(mcp_jobs._claim(self.db, ref))
        self.assertEqual(self.col._docs["job-4"]["status"], mcp_jobs.STATUS_ERROR)

    def test_claim_expirado_marca_error_sem_reprocessar(self):
        """Achado central do plano: claim abandonado (execução anterior
        morreu sem concluir) não deve ser retomado automaticamente — a tool
        pode não ser idempotente. Marca error, não relança a tool."""
        agora = datetime.now(timezone.utc)
        self.col._docs["job-5"] = _job_basico(
            status=mcp_jobs.STATUS_EM_EXECUCAO,
            claimed_em=agora - mcp_jobs.CLAIM_EXPIRA_APOS - timedelta(seconds=1),
        )
        ref = self.col.document("job-5")

        resultado = mcp_jobs._claim(self.db, ref)

        self.assertIsNone(resultado)
        doc = self.col._docs["job-5"]
        self.assertEqual(doc["status"], mcp_jobs.STATUS_ERROR)
        self.assertIn("abandonada", doc["erro"])
        self.assertIsInstance(doc["expira_em"], datetime)

    def test_claim_em_execucao_recente_levanta_sem_alterar_documento(self):
        """Achado do Codex na PR #189: um claim jovem é ambíguo (tentativa
        irmã em andamento, ou claim órfão de uma tentativa que já morreu) —
        levanta ClaimAindaValidoError em vez de devolver None em silêncio,
        para a invocação nunca ser registrada como sucesso sem a tool ter
        rodado. O documento não é tocado (a transação não escreveu nada
        antes de levantar)."""
        agora = datetime.now(timezone.utc)
        self.col._docs["job-6"] = _job_basico(
            status=mcp_jobs.STATUS_EM_EXECUCAO,
            claimed_em=agora - timedelta(seconds=10),
        )
        ref = self.col.document("job-6")
        doc_antes = dict(self.col._docs["job-6"])

        with self.assertRaises(mcp_jobs.ClaimAindaValidoError):
            mcp_jobs._claim(self.db, ref)

        self.assertEqual(self.col._docs["job-6"], doc_antes)

    def test_claim_documento_inexistente_devolve_none(self):
        ref = self.col.document("job-fantasma")
        self.assertIsNone(mcp_jobs._claim(self.db, ref))

    def test_claim_em_execucao_sem_claimed_em_e_tratado_como_abandonado(self):
        """Documento em em_execucao sem claimed_em (ou com tipo inesperado,
        ex.: legado/corrompido) não pode travar o job para sempre — cai no
        mesmo caminho de 'abandonado', não é tratado como reserva válida."""
        self.col._docs["job-7"] = _job_basico(status=mcp_jobs.STATUS_EM_EXECUCAO)
        ref = self.col.document("job-7")

        self.assertIsNone(mcp_jobs._claim(self.db, ref))
        self.assertEqual(self.col._docs["job-7"]["status"], mcp_jobs.STATUS_ERROR)


class TestInvarianteClaimVsTimeout(unittest.TestCase):
    def test_claim_expira_apos_excede_timeout_do_gatilho(self):
        """CLAIM_EXPIRA_APOS precisa ser estritamente maior que o timeout_sec
        do gatilho — é essa relação que garante que um claim 'abandonado'
        não pode na verdade ainda estar em execução (ver docstring do
        módulo). Os dois valores vêm da mesma constante _TIMEOUT_SEC, então
        isto também serve de guarda contra uma mudança futura desalinhar
        os dois sem querer."""
        self.assertGreater(
            mcp_jobs.CLAIM_EXPIRA_APOS.total_seconds(),
            mcp_jobs._TIMEOUT_SEC,
        )


class TestOnMcpJobCreated(unittest.TestCase):
    """Cobertura leve do wrapper do gatilho em si (não só das funções
    internas _claim/_executar_job) — achado do review adversarial: o
    'unwrapping' do evento (event.data None/inexistente) não tinha teste.

    Chama `.__wrapped__` (o `@_functools.wraps` do decorator do firebase
    functions expõe a função original) em vez do trigger decorado
    diretamente — o decorator espera um `CloudEvent` bruto do framework,
    não o objeto `Event` já tipado, e não há como montar um CloudEvent
    fiel sem subir toda a maquinaria do framework. Nenhum outro trigger
    do repositório (ex.: on_whatsapp_message_atencao) testa essa camada
    decorada; isto cobre só a lógica própria do wrapper (extrair
    snap/ref, delegar a _claim/_executar_job)."""

    class _FakeEvent:
        def __init__(self, data):
            self.data = data

    def setUp(self):
        self.db_patcher = patch("mcp_jobs._db")
        mock_db_fn = self.db_patcher.start()
        self.db = _MockDb()
        mock_db_fn.return_value = self.db
        self.addCleanup(self.db_patcher.stop)
        self.col = self.db.collection(mcp_jobs.COLECAO)

    def test_event_sem_data_nao_quebra(self):
        mcp_jobs.on_mcp_job_created.__wrapped__(self._FakeEvent(data=None))  # não deve lançar

    def test_event_com_snapshot_inexistente_nao_quebra(self):
        snap = _MockDocSnap("job-fantasma", None)
        snap.reference = self.col.document("job-fantasma")
        mcp_jobs.on_mcp_job_created.__wrapped__(self._FakeEvent(data=snap))  # não deve lançar

    def test_event_com_job_valido_executa_e_grava_done(self):
        self.col._docs["job-evt"] = _job_basico(status=mcp_jobs.STATUS_PROCESSING)
        snap = _MockDocSnap("job-evt", self.col._docs["job-evt"])
        snap.reference = self.col.document("job-evt")

        with patch("tools.hermes_tools.execute", return_value={"ok": True}):
            mcp_jobs.on_mcp_job_created.__wrapped__(self._FakeEvent(data=snap))

        self.assertEqual(self.col._docs["job-evt"]["status"], mcp_jobs.STATUS_DONE)

    def test_event_reentrega_de_job_ja_em_execucao_nao_roda_tool_de_novo(self):
        """O cenário central do achado A10: uma entrega duplicada do MESMO
        evento (job já claimeado por uma invocação anterior recente) não
        deve rodar a tool de novo. Achado do Codex na PR #189: essa
        invocação também não pode retornar normalmente (silenciosamente
        'com sucesso') — deve levantar ClaimAindaValidoError, propagada por
        _claim através do wrapper do gatilho sem tratamento (nenhum
        try/except em on_mcp_job_created ao redor de _claim)."""
        agora = datetime.now(timezone.utc)
        self.col._docs["job-dup"] = _job_basico(
            status=mcp_jobs.STATUS_EM_EXECUCAO,
            claimed_em=agora - timedelta(seconds=5),
        )
        snap = _MockDocSnap("job-dup", self.col._docs["job-dup"])
        snap.reference = self.col.document("job-dup")

        with patch("tools.hermes_tools.execute") as mock_execute:
            with self.assertRaises(mcp_jobs.ClaimAindaValidoError):
                mcp_jobs.on_mcp_job_created.__wrapped__(self._FakeEvent(data=snap))

        mock_execute.assert_not_called()
        # Estado não foi alterado pela entrega duplicada.
        self.assertEqual(self.col._docs["job-dup"]["status"], mcp_jobs.STATUS_EM_EXECUCAO)


class TestExecutarJob(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()
        self.col = self.db.collection(mcp_jobs.COLECAO)
        self.col._docs["job-x"] = _job_basico(status=mcp_jobs.STATUS_EM_EXECUCAO)
        self.ref = self.col.document("job-x")

    def test_sucesso_grava_done(self):
        with patch("tools.hermes_tools.execute", return_value={"ok": True}):
            mcp_jobs._executar_job(self.db, self.ref, self.col._docs["job-x"])

        doc = self.col._docs["job-x"]
        self.assertEqual(doc["status"], mcp_jobs.STATUS_DONE)
        self.assertIn("resultado", doc)
        self.assertFalse(doc["truncado"])
        self.assertIsInstance(doc["expira_em"], datetime)

    def test_resultado_dict_com_erro_grava_error_nao_done(self):
        """Achado do plano: 'não há falso done quando handler relata
        erro'."""
        with patch("tools.hermes_tools.execute", return_value={"erro": "falhou no meio"}):
            mcp_jobs._executar_job(self.db, self.ref, self.col._docs["job-x"])

        doc = self.col._docs["job-x"]
        self.assertEqual(doc["status"], mcp_jobs.STATUS_ERROR)
        self.assertEqual(doc["erro"], "falhou no meio")
        self.assertNotIn("resultado", doc)
        self.assertIsInstance(doc["expira_em"], datetime)

    def test_resultado_string_erro_grava_error(self):
        with patch("tools.hermes_tools.execute", return_value="ERRO|tool nao encontrada"):
            mcp_jobs._executar_job(self.db, self.ref, self.col._docs["job-x"])

        doc = self.col._docs["job-x"]
        self.assertEqual(doc["status"], mcp_jobs.STATUS_ERROR)
        self.assertEqual(doc["erro"], "ERRO|tool nao encontrada")

    def test_excecao_da_tool_grava_error(self):
        with patch("tools.hermes_tools.execute", side_effect=RuntimeError("bum")):
            mcp_jobs._executar_job(self.db, self.ref, self.col._docs["job-x"])

        doc = self.col._docs["job-x"]
        self.assertEqual(doc["status"], mcp_jobs.STATUS_ERROR)
        self.assertEqual(doc["erro"], "bum")
        self.assertIsInstance(doc["expira_em"], datetime)

    def test_resultado_grande_e_truncado(self):
        texto_grande = "x" * (mcp_jobs._MAX_RESULTADO_CHARS + 500)
        with patch("tools.hermes_tools.execute", return_value=texto_grande):
            mcp_jobs._executar_job(self.db, self.ref, self.col._docs["job-x"])

        doc = self.col._docs["job-x"]
        self.assertEqual(doc["status"], mcp_jobs.STATUS_DONE)
        self.assertTrue(doc["truncado"])
        self.assertLessEqual(len(doc["resultado"]), mcp_jobs._MAX_RESULTADO_CHARS + 100)

    def test_resultado_string_normal_nao_e_marcado_como_erro(self):
        with patch("tools.hermes_tools.execute", return_value="tudo certo por aqui"):
            mcp_jobs._executar_job(self.db, self.ref, self.col._docs["job-x"])

        doc = self.col._docs["job-x"]
        self.assertEqual(doc["status"], mcp_jobs.STATUS_DONE)
        self.assertEqual(doc["resultado"], "tudo certo por aqui")


class TestLerJob(unittest.TestCase):
    def setUp(self):
        self.db_patcher = patch("mcp_jobs._db")
        mock_db_fn = self.db_patcher.start()
        self.db = _MockDb()
        mock_db_fn.return_value = self.db
        self.addCleanup(self.db_patcher.stop)
        self.col = self.db.collection(mcp_jobs.COLECAO)

    def test_job_id_vazio_nao_toca_firestore(self):
        resultado = mcp_jobs.ler_job("user-1", "")
        self.assertEqual(resultado["status"], "not_found")
        self.assertEqual(self.col._docs, {})

    def test_job_nao_encontrado(self):
        resultado = mcp_jobs.ler_job("user-1", "job-inexistente")
        self.assertEqual(resultado["status"], "not_found")

    def test_uid_nao_bate_nao_vaza_job_de_outro_usuario(self):
        """Mesma resposta (not_found) tanto para job inexistente quanto para
        job de outro usuário — confirmar que o id existe vazaria
        informação para quem está tentando adivinhar."""
        self.col._docs["job-y"] = _job_basico(uid="outro-user", status=mcp_jobs.STATUS_DONE)
        resultado_outro_uid = mcp_jobs.ler_job("user-1", "job-y")
        resultado_inexistente = mcp_jobs.ler_job("user-1", "job-jamais-existiu")

        self.assertEqual(resultado_outro_uid["status"], "not_found")
        self.assertNotIn("resultado", resultado_outro_uid)
        self.assertEqual(
            set(resultado_outro_uid.keys()), set(resultado_inexistente.keys())
        )

    def test_status_processing_normal(self):
        self.col._docs["job-z"] = _job_basico(status=mcp_jobs.STATUS_PROCESSING)
        resultado = mcp_jobs.ler_job("user-1", "job-z")
        self.assertEqual(resultado["status"], "processing")

    def test_status_em_execucao_normaliza_para_processing(self):
        """Contrato público preservado: em_execucao (estado interno) deve
        aparecer como 'processing' para quem consulta de fora."""
        self.col._docs["job-w"] = _job_basico(status=mcp_jobs.STATUS_EM_EXECUCAO)
        resultado = mcp_jobs.ler_job("user-1", "job-w")
        self.assertEqual(resultado["status"], "processing")

    def test_status_done_traz_resultado(self):
        self.col._docs["job-d"] = _job_basico(status=mcp_jobs.STATUS_DONE, resultado="pronto")
        resultado = mcp_jobs.ler_job("user-1", "job-d")
        self.assertEqual(resultado["status"], "done")
        self.assertEqual(resultado["resultado"], "pronto")

    def test_status_error_traz_erro(self):
        self.col._docs["job-e"] = _job_basico(status=mcp_jobs.STATUS_ERROR, erro="quebrou")
        resultado = mcp_jobs.ler_job("user-1", "job-e")
        self.assertEqual(resultado["status"], "error")
        self.assertEqual(resultado["erro"], "quebrou")


if __name__ == "__main__":
    unittest.main()
