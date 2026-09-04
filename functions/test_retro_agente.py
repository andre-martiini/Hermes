"""Testes unitários da retrospectiva semanal do agente e auditoria MCP (PR 4 da Fase 2)."""

from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import MagicMock, patch
import uuid

from retro_agente import (
    COLLECTION_CORRECOES,
    COLLECTION_RETROS,
    _extrair_json_obj,
    _parse_dt,
    coletar_metricas_semana,
    construir_prompt_retro,
    executar_retro_semanal,
    formatar_texto_agregado,
)


class MockDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = self

    def to_dict(self):
        return dict(self._data or {})

    def get(self):
        return self

    def update(self, fields):
        if self._data is not None:
            self._data.update(fields)

    def set(self, fields, merge=False):
        if self._data is None:
            self._data = {}
        if merge:
            self._data.update(fields)
        else:
            self._data = dict(fields)
        self.exists = True


class MockQuery:
    def __init__(self, docs, filters=None, limit_val=None):
        self.docs = docs
        self.filters = filters or []
        self.limit_val = limit_val

    def where(self, field, op, val):
        new_filters = list(self.filters)
        new_filters.append((field, op, val))
        return MockQuery(self.docs, new_filters, self.limit_val)

    def limit(self, val):
        return MockQuery(self.docs, self.filters, limit_val=val)

    def stream(self):
        filtered = []
        for d in self.docs:
            data = d.to_dict()
            match = True
            for field, op, val in self.filters:
                doc_val = data.get(field)
                if op == "==" and doc_val != val:
                    match = False
                    break
                elif op == ">=" and (doc_val is None or doc_val < val):
                    match = False
                    break
            if match:
                filtered.append(d)
        if self.limit_val is not None:
            filtered = filtered[:self.limit_val]
        return filtered

    def get(self):
        return self.stream()

    def add(self, data):
        auto_id = f"auto-{uuid.uuid4().hex[:8]}"
        doc = MockDoc(auto_id, dict(data))
        self.docs.append(doc)
        return (None, doc)

    def document(self, wanted=None):
        if wanted is None:
            auto_id = f"auto-{uuid.uuid4().hex[:8]}"
            doc = MockDoc(auto_id, {})
            self.docs.append(doc)
            return doc
        for d in self.docs:
            if d.id == wanted:
                return d
        new_doc = MockDoc(wanted, None)
        self.docs.append(new_doc)
        return new_doc


class MockDb:
    def __init__(self, data=None):
        self.data = data if data is not None else {}
        self._collections = {}

    def collection(self, name):
        if name not in self._collections:
            docs = [MockDoc(k, v) for k, v in self.data.get(name, {}).items()]
            self._collections[name] = MockQuery(docs)
        return self._collections[name]


class TestAuditLogInMcpServer(unittest.TestCase):
    def test_audit_log_adiciona_is_error(self):
        from mcp_server import _audit_log

        mock_db = MockDb()
        with patch("mcp_server.firestore.client", return_value=mock_db):
            _audit_log(
                uid="user123",
                tool="consultar_acao",
                arguments={"id": "abc"},
                latency_ms=125.4,
                is_error=True,
            )

        col = mock_db.collection("mcp_audit_log")
        docs = col.stream()
        self.assertEqual(len(docs), 1)
        data = docs[0].to_dict()
        self.assertEqual(data["uid"], "user123")
        self.assertEqual(data["tool"], "consultar_acao")
        self.assertEqual(data["is_error"], True)
        self.assertEqual(data["latency_ms"], 125.4)

    def test_audit_log_is_error_default_false(self):
        from mcp_server import _audit_log

        mock_db = MockDb()
        with patch("mcp_server.firestore.client", return_value=mock_db):
            _audit_log(
                uid="user123",
                tool="consultar_acao",
                arguments={"id": "abc"},
                latency_ms=80.0,
            )

        col = mock_db.collection("mcp_audit_log")
        docs = col.stream()
        self.assertEqual(len(docs), 1)
        data = docs[0].to_dict()
        self.assertEqual(data["is_error"], False)

    def test_handle_tools_call_passa_is_error_normal(self):
        import mcp_server
        from mcp_server import _handle_tools_call

        ctx = MagicMock()
        ctx.user_uid = "u1"
        ctx.session_id = "s1"
        ctx.task_id = "t1"

        with patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), \
             patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             patch.object(mcp_server, "execute_tool", return_value={"erro": "Falha de banco"}), \
             patch.object(mcp_server, "_audit_log") as mock_log:

            res = _handle_tools_call({"name": "minha_tool", "arguments": {}}, ctx=ctx)
            self.assertTrue(res["isError"])
            mock_log.assert_called_once()
            _, kwargs = mock_log.call_args
            self.assertEqual(kwargs.get("tool"), "minha_tool")
            self.assertEqual(kwargs.get("is_error"), True)

    def test_handle_tools_call_passa_is_error_confirmar_acao(self):
        import mcp_server
        from mcp_server import _handle_tools_call

        ctx = MagicMock()
        ctx.user_uid = "u1"

        def fake_exec(c, cid, **kwargs):
            c.mcp_confirmed_tool = "criar_acao"
            c.mcp_confirmed_arguments = {"titulo": "Nova"}
            return {"ok": True}

        with patch.object(mcp_server, "_executar_confirmacao", side_effect=fake_exec), \
             patch.object(mcp_server, "_audit_log") as mock_log:

            res = _handle_tools_call({"name": "confirmar_acao", "arguments": {"confirmation_id": "c1"}}, ctx=ctx)
            self.assertFalse(res["isError"])
            mock_log.assert_called_once()
            _, kwargs = mock_log.call_args
            self.assertEqual(kwargs.get("tool"), "criar_acao")
            self.assertEqual(kwargs.get("is_error"), False)

    def test_handle_tools_call_passa_is_error_confirmar_com_erro(self):
        import mcp_server
        from mcp_server import _handle_tools_call

        ctx = MagicMock()
        ctx.user_uid = "u1"

        def fake_exec(c, cid, **kwargs):
            c.mcp_confirmed_tool = "criar_acao"
            c.mcp_confirmed_arguments = {"titulo": "Nova"}
            return {"erro": "Ação duplicada"}

        with patch.object(mcp_server, "_executar_confirmacao", side_effect=fake_exec), \
             patch.object(mcp_server, "_audit_log") as mock_log:

            res = _handle_tools_call({"name": "confirmar_acao", "arguments": {"confirmation_id": "c1"}}, ctx=ctx)
            self.assertTrue(res["isError"])
            mock_log.assert_called_once()
            _, kwargs = mock_log.call_args
            self.assertEqual(kwargs.get("tool"), "criar_acao")
            self.assertEqual(kwargs.get("is_error"), True)

    def test_handle_tools_call_passa_is_error_false_tool_longa(self):
        import mcp_server
        from mcp_server import _handle_tools_call

        ctx = MagicMock()
        ctx.user_uid = "u1"
        ctx.session_id = "s1"
        ctx.task_id = "t1"

        with patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), \
             patch.object(mcp_server, "_TOOLS_LONGAS", {"processar_audio_longo"}), \
             patch("mcp_jobs.criar_job", return_value="job123"), \
             patch.object(mcp_server, "_audit_log") as mock_log:

            res = _handle_tools_call({"name": "processar_audio_longo", "arguments": {}}, ctx=ctx)
            self.assertFalse(res["isError"])
            mock_log.assert_called_once()
            _, kwargs = mock_log.call_args
            self.assertEqual(kwargs.get("tool"), "processar_audio_longo")
            self.assertEqual(kwargs.get("is_error"), False)
            self.assertEqual(kwargs.get("latency_ms"), 0.0)


class TestColetaEMetricas(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 7, 20, 0, 0, tzinfo=timezone.utc)

    def test_coleta_agent_runs_e_agrupamento(self):
        rec1 = (self.now - timedelta(days=2)).isoformat()
        rec2 = (self.now - timedelta(days=3)).isoformat()
        rec3 = (self.now - timedelta(days=4)).isoformat()
        rec_antigo = (self.now - timedelta(days=10)).isoformat()

        dados = {
            "agent_runs": {
                "r1": {"rotina": "briefing_matinal", "status": "sucesso", "criado_em": rec1},
                "r2": {"rotina": "briefing_matinal", "status": "erro", "erro": "Timeout de rede", "criado_em": rec2},
                "r3": {"rotina": "briefing_matinal", "status": "erro", "erro": "Timeout de rede", "criado_em": rec3},
                "r4": {"rotina": "briefing_matinal", "status": "erro", "erro": "Chave expirada", "criado_em": rec3},
                "r_fora": {"rotina": "briefing_matinal", "status": "erro", "erro": "Antigo", "criado_em": rec_antigo},
            },
            "mcp_audit_log": {
                "a1": {"tool": "buscar_acao", "latency_ms": 100, "is_error": False, "timestamp": rec1},
                "a2": {"tool": "buscar_acao", "latency_ms": 200, "is_error": True, "timestamp": rec2},
                "a3": {"tool": "criar_acao", "latency_ms": 300, "timestamp": rec3},  # sem is_error (legado)
                "a_fora": {"tool": "buscar_acao", "latency_ms": 50, "is_error": True, "timestamp": rec_antigo},
            }
        }

        db = MockDb(dados)
        met_runs, met_tools = coletar_metricas_semana(db, self.now)

        self.assertEqual(met_runs["total_runs"], 4)
        self.assertEqual(met_runs["total_erros"], 3)
        rotina_briefing = met_runs["rotinas"]["briefing_matinal"]
        self.assertEqual(rotina_briefing["total"], 4)
        self.assertEqual(rotina_briefing["status"]["sucesso"], 1)
        self.assertEqual(rotina_briefing["status"]["erro"], 3)
        # Unique errors limited to 3
        self.assertIn("Timeout de rede", rotina_briefing["erros"])
        self.assertIn("Chave expirada", rotina_briefing["erros"])
        self.assertEqual(len(rotina_briefing["erros"]), 2)

        self.assertEqual(met_tools["total_calls"], 3)
        self.assertEqual(met_tools["total_erros"], 1)
        buscar = met_tools["tools"]["buscar_acao"]
        self.assertEqual(buscar["total"], 2)
        self.assertEqual(buscar["erros"], 1)
        self.assertEqual(buscar["taxa_erro"], 0.5)
        self.assertEqual(buscar["latencia_media_ms"], 150.0)
        self.assertEqual(buscar["latencia_max_ms"], 200.0)

        criar = met_tools["tools"]["criar_acao"]
        self.assertEqual(criar["total"], 1)
        self.assertEqual(criar["erros"], 0)
        self.assertEqual(criar["taxa_erro"], 0.0)

    def test_formatar_texto_agregado_sem_argumentos_brutos(self):
        met_runs = {
            "total_runs": 5,
            "total_erros": 1,
            "rotinas": {
                "varredura_followups": {
                    "total": 5,
                    "status": {"sucesso": 4, "erro": 1},
                    "erros": ["API indisponível"],
                }
            }
        }
        met_tools = {
            "total_calls": 10,
            "total_erros": 2,
            "tools": {
                "obter_acao": {
                    "total": 10,
                    "erros": 2,
                    "taxa_erro": 0.2,
                    "latencia_media_ms": 85.0,
                    "latencia_max_ms": 150.0,
                }
            }
        }
        texto = formatar_texto_agregado("2026-08-31T00:00:00", "2026-09-07T00:00:00", met_runs, met_tools)
        self.assertIn("ROTINAS AGENDADAS DO AGENTE", texto)
        self.assertIn("varredura_followups", texto)
        self.assertIn("API indisponível", texto)
        self.assertIn("obter_acao: 10 chamadas", texto)
        self.assertNotIn("arguments", texto)
        self.assertNotIn("payload", texto)


class TestParseRespostaGemini(unittest.TestCase):
    def test_parse_com_proposta_concreta(self):
        resp_json = json.dumps({
            "resumo": "Semana com 12 execuções e taxa de falha de 25% na rotina de varredura.",
            "proposta_pop": {
                "area_tematica": "rotinas_agente",
                "titulo_procedimento": "Retry de Timeout em Follow-ups",
                "correcao_descrita": "A rotina falhou 3 vezes consecutivas por timeout de conexão.",
                "novo_conteudo_proposto": "Aplicar retry com backoff exponencial de até 3 tentativas.",
                "justificativa": "Rotina varredura_followups falhou 3 vezes com 'Timeout de rede'."
            }
        })
        dados = _extrair_json_obj(resp_json)
        self.assertIsNotNone(dados)
        self.assertIn("resumo", dados)
        self.assertEqual(dados["proposta_pop"]["titulo_procedimento"], "Retry de Timeout em Follow-ups")

    def test_parse_sem_proposta_null(self):
        resp_json = json.dumps({
            "resumo": "Execuções estáveis durante toda a semana, sem anomalias.",
            "proposta_pop": None
        })
        dados = _extrair_json_obj(resp_json)
        self.assertIsNotNone(dados)
        self.assertIsNone(dados["proposta_pop"])

    def test_parse_com_markdown_fences(self):
        resp_fenced = "```json\n" + json.dumps({
            "resumo": "Tudo normal.",
            "proposta_pop": None
        }) + "\n```"
        dados = _extrair_json_obj(resp_fenced)
        self.assertIsNotNone(dados)
        self.assertEqual(dados["resumo"], "Tudo normal.")

    def test_parse_invalido_retorna_none(self):
        dados = _extrair_json_obj("Isso não é um json válido.")
        self.assertIsNone(dados)


class TestExecutarRetroSemanal(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 7, 20, 0, 0, tzinfo=timezone.utc)

    def test_silencio_quando_sem_agent_runs(self):
        db = MockDb({"agent_runs": {}, "mcp_audit_log": {}})
        mock_client = MagicMock()

        resultado = executar_retro_semanal(db, now=self.now, client=mock_client)
        self.assertEqual(resultado["status"], "silencio_sem_dados")
        mock_client.generate_content.assert_not_called()
        self.assertEqual(len(db.collection(COLLECTION_RETROS).stream()), 0)
        self.assertEqual(len(db.collection(COLLECTION_CORRECOES).stream()), 0)

    @patch("main._resolve_default_telegram_chat_id", return_value="123456")
    @patch("main._send_telegram_message_raw")
    @patch("retro_agente.generate_content_logged")
    def test_retro_com_proposta_concreta_grava_em_correcoes_pendentes(
        self,
        mock_gen_content,
        mock_send_tg,
        mock_chat_id,
    ):
        ts = (self.now - timedelta(days=1)).isoformat()
        db = MockDb({
            "agent_runs": {
                "r1": {"rotina": "briefing", "status": "erro", "erro": "Erro 500", "criado_em": ts},
                "r2": {"rotina": "briefing", "status": "erro", "erro": "Erro 500", "criado_em": ts},
                "r3": {"rotina": "briefing", "status": "erro", "erro": "Erro 500", "criado_em": ts},
            },
            "mcp_audit_log": {
                "a1": {"tool": "buscar_acao", "latency_ms": 50, "is_error": False, "timestamp": ts},
            }
        })

        mock_resp = MagicMock()
        mock_resp.text = json.dumps({
            "resumo": "O briefing matinal falhou 3 vezes consecutivas devido ao erro 500.",
            "proposta_pop": {
                "area_tematica": "rotinas_agente",
                "titulo_procedimento": "Contingência Briefing Erro 500",
                "correcao_descrita": "Breve instabilidade no endpoint gera falha fatal.",
                "novo_conteudo_proposto": "Requisitar fallback em cache local quando receber 500.",
                "justificativa": "Briefing falhou 3 vezes com Erro 500."
            }
        })
        mock_gen_content.return_value = mock_resp

        mock_client = MagicMock()
        resultado = executar_retro_semanal(db, now=self.now, client=mock_client)

        self.assertEqual(resultado["status"], "ok")
        self.assertTrue(resultado["telegram_sent"])
        self.assertIsNotNone(resultado["proposta_pop"])

        # Confere gravação em retros_agente
        retros = db.collection(COLLECTION_RETROS).stream()
        self.assertEqual(len(retros), 1)
        retro_doc = retros[0].to_dict()
        self.assertEqual(retro_doc["resumo"], "O briefing matinal falhou 3 vezes consecutivas devido ao erro 500.")
        self.assertEqual(retro_doc["metricas"]["total_runs"], 3)
        self.assertEqual(retro_doc["metricas"]["total_erros_rotinas"], 3)

        # Confere gravação em correcoes_pendentes
        corrs = db.collection(COLLECTION_CORRECOES).stream()
        self.assertEqual(len(corrs), 1)
        corr_doc = corrs[0].to_dict()
        self.assertEqual(corr_doc["titulo_procedimento"], "Contingência Briefing Erro 500")
        self.assertEqual(corr_doc["novo_conteudo_proposto"], "Requisitar fallback em cache local quando receber 500.")
        self.assertEqual(corr_doc["status"], "pendente")
        self.assertEqual(corr_doc["origem"], "retro_agente")

        # Confere mensagem Telegram informativa
        mock_send_tg.assert_called_once()
        args, _ = mock_send_tg.call_args
        msg = args[2]
        self.assertIn("Retro Semanal do Agente", msg)
        self.assertIn("Contingência Briefing Erro 500", msg)

    @patch("main._resolve_default_telegram_chat_id", return_value="123456")
    @patch("main._send_telegram_message_raw")
    @patch("retro_agente.generate_content_logged")
    def test_retro_sem_proposta_grava_apenas_em_retros_agente(
        self,
        mock_gen_content,
        mock_send_tg,
        mock_chat_id,
    ):
        ts = (self.now - timedelta(days=2)).isoformat()
        db = MockDb({
            "agent_runs": {
                "r1": {"rotina": "briefing", "status": "sucesso", "criado_em": ts},
            },
            "mcp_audit_log": {}
        })

        mock_resp = MagicMock()
        mock_resp.text = json.dumps({
            "resumo": "Semana 100% estável sem necessidade de ajustes.",
            "proposta_pop": None
        })
        mock_gen_content.return_value = mock_resp

        mock_client = MagicMock()
        resultado = executar_retro_semanal(db, now=self.now, client=mock_client)

        self.assertEqual(resultado["status"], "ok")
        self.assertIsNone(resultado["proposta_pop"])

        # Gravou em retros_agente
        self.assertEqual(len(db.collection(COLLECTION_RETROS).stream()), 1)
        # NUNCA gravou em correcoes_pendentes
        self.assertEqual(len(db.collection(COLLECTION_CORRECOES).stream()), 0)

        # Telegram enviado sem menção à proposta
        mock_send_tg.assert_called_once()
        args, _ = mock_send_tg.call_args
        msg = args[2]
        self.assertIn("Semana 100% estável", msg)
        self.assertNotIn("Uma proposta de ajuste de POP", msg)


if __name__ == "__main__":
    unittest.main()
