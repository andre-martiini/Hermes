"""Causa do erro no `mcp_audit_log`, gravação só na nuvem, argumentos consertados,
falha de job contada uma vez e a retro separando falha real de recusa.

Os casos vêm do `mcp_audit_log` real de 05 a 14/10/2026.
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import auditoria_mcp
import mcp_argumentos
import mcp_jobs
import mcp_server
from dados_cadastrais import get_dados_cadastrais
from retro_agente import coletar_metricas_semana, formatar_texto_agregado
from test_mcp_jobs import _MockDB, _make_event
from test_retro_agente import MockDb
from tools.tool_context import ToolContext

NA_NUVEM = {"K_SERVICE": "mcpserver"}


def _sem_nuvem():
    ambiente = {k: v for k, v in os.environ.items() if k not in ("K_SERVICE", "FUNCTION_TARGET")}
    return mock.patch.dict(os.environ, ambiente, clear=True)


class TestClassificarErro(unittest.TestCase):
    def _c(self, tool, resultado=None, excecao=None):
        return auditoria_mcp.classificar_erro(tool, resultado, excecao)

    def test_excecao_e_falha_real(self):
        c = self._c("obter_acao", excecao=RuntimeError("Firestore fora do ar"))
        self.assertEqual(c, {"erro_tipo": "excecao", "erro_resumo": "Firestore fora do ar", "recusa_esperada": False})

    def test_id_inexistente_e_recusa(self):
        self.assertEqual(self._c("consultar_job", {"erro": "Job 'x' nao encontrado.", "status": "not_found"})["erro_tipo"],
                         "nao_encontrado")
        c = self._c("registrar_no_diario", "ERRO|Tarefa 'c31c7282' nao encontrada.")
        self.assertEqual((c["erro_tipo"], c["recusa_esperada"]), ("nao_encontrado", True))
        self.assertEqual(c["erro_resumo"], "Tarefa 'c31c7282' nao encontrada.")

    def test_erro_dentro_de_json_no_texto(self):
        c = self._c("consultar_dados_cadastrais",
                    'ERRO|{"error": "Seção \'formação\' não encontrada.", "secoes_disponiveis": ["formacao"]}')
        self.assertEqual(c["erro_tipo"], "nao_encontrado")
        self.assertEqual(c["erro_resumo"], "Seção 'formação' não encontrada.")

    def test_argumento_errado_e_recusa(self):
        c = self._c("registrar_no_diario", "ERRO|Sem tarefa ativa. Informe o ID da tarefa onde registrar.")
        self.assertEqual((c["erro_tipo"], c["recusa_esperada"]), ("argumentos", True))

    def test_job_que_falhou_consultado_de_novo_e_recusa(self):
        c = self._c("consultar_job", {"status": "error", "erro": "boom", "erro_tipo": "excecao"})
        self.assertEqual((c["erro_tipo"], c["recusa_esperada"]), ("job_com_falha", True))

    def test_envio_de_whatsapp_que_falhou_e_falha_real(self):
        c = self._c("consultar_envio_whatsapp",
                    {"status": "failed", "erro": "Attempted to use detached Frame 'A45E'."})
        self.assertEqual((c["erro_tipo"], c["recusa_esperada"]), ("envio_com_falha", False))

    def test_arquivo_alterado_depois_da_leitura_e_conflito(self):
        c = self._c("atualizar_arquivo_drive", {"erro": "O arquivo foi modificado depois da sua leitura (...)"})
        self.assertEqual((c["erro_tipo"], c["recusa_esperada"]), ("conflito", True))

    def test_bloqueio_de_politica_e_recusa(self):
        c = self._c("video_renderizar", {"erro": "x", "bloqueio_politica": {"decision": "deny"}})
        self.assertEqual((c["erro_tipo"], c["recusa_esperada"]), ("politica", True))

    def test_site_externo_e_falha_mas_marcada_como_externa(self):
        c = self._c("ler_pagina_web", {"erro": "Timeout ao acessar a página"})
        self.assertEqual((c["erro_tipo"], c["recusa_esperada"]), ("externo", False))

    def test_erro_desconhecido_e_falha_da_tool(self):
        c = self._c("criar_rascunho_whatsapp", {"erro": "boom inesperado"})
        self.assertEqual((c["erro_tipo"], c["recusa_esperada"]), ("resultado_tool", False))

    def test_resumo_esconde_numero_longo_e_tem_teto(self):
        c = self._c("criar_rascunho_whatsapp", {"erro": "Contato +5527999263355 sem WhatsApp. " + "x" * 400})
        self.assertIn("<número>", c["erro_resumo"])
        self.assertNotIn("5527999263355", c["erro_resumo"])
        self.assertEqual(len(c["erro_resumo"]), 200)


class TestGravaSoNaNuvem(unittest.TestCase):
    def test_fora_da_nuvem_sem_banco_injetado_nao_toca_a_producao(self):
        with _sem_nuvem(), mock.patch("firebase_admin.firestore.client", side_effect=AssertionError("produção")):
            self.assertIsNone(auditoria_mcp.destino(None))
            mcp_server._audit_log(uid="dono-uid", tool="calculadora", arguments={}, latency_ms=1.0, is_error=True)

    def test_banco_injetado_recebe_o_registro(self):
        db = mock.MagicMock()
        with _sem_nuvem():
            mcp_server._audit_log(uid="u", tool="t", arguments={}, latency_ms=1.0, db=db)
        db.collection.assert_called_with("mcp_audit_log")
        db.collection.return_value.add.assert_called_once()

    def test_na_nuvem_usa_o_firestore(self):
        db = mock.MagicMock()
        with mock.patch.dict(os.environ, NA_NUVEM), mock.patch("firebase_admin.firestore.client", return_value=db):
            self.assertIs(auditoria_mcp.destino(None), db)

    def test_sinal_de_intencao_nao_grava_fora_da_nuvem(self):
        import mcp_signals

        self.assertTrue(mcp_signals.sinal_de_intencao("consultar_historico_acoes", {"query": "licitação"}))
        with _sem_nuvem(), mock.patch("mcp_signals.threading.Thread", side_effect=AssertionError("gravou")):
            mcp_signals.registrar("dono-uid", "consultar_historico_acoes", {"query": "licitação"})


class TestNormalizarArgumentos(unittest.TestCase):
    PROPS_OBTER = {"task_id": {}, "limite_diario": {}}

    def test_apelido_do_id_da_acao_vira_task_id(self):
        for apelido in ("id", "acao_id", "tarefa_id"):
            saida, ajustes = mcp_argumentos.normalizar({apelido: "e10ef3ca"}, self.PROPS_OBTER)
            self.assertEqual(saida, {"task_id": "e10ef3ca"})
            self.assertEqual(ajustes, [f"{apelido}->task_id"])

    def test_registrar_no_diario_usa_task_id_alvo(self):
        saida, _ = mcp_argumentos.normalizar({"nota": "n", "acao_id": "0285fd7b"}, {"nota": {}, "task_id_alvo": {}})
        self.assertEqual(saida, {"nota": "n", "task_id_alvo": "0285fd7b"})

    def test_nao_mexe_quando_a_tool_declara_o_apelido(self):
        props = {"acao_id": {}, "task_id": {}}
        saida, ajustes = mcp_argumentos.normalizar({"acao_id": "a1"}, props)
        self.assertEqual((saida, ajustes), ({"acao_id": "a1"}, []))

    def test_nao_sobrescreve_task_id_ja_informado(self):
        saida, ajustes = mcp_argumentos.normalizar({"task_id": "certo", "id": "outro"}, self.PROPS_OBTER)
        self.assertEqual(saida["task_id"], "certo")
        self.assertEqual(ajustes, [])

    def test_texto_null_em_id_vira_ausente(self):
        saida, ajustes = mcp_argumentos.normalizar({"pessoa_id": "null", "nome": "Plenotel"},
                                                   {"pessoa_id": {}, "nome": {}})
        self.assertEqual(saida, {"nome": "Plenotel"})
        self.assertEqual(ajustes, ["pessoa_id='null' removido"])

    def test_texto_null_fora_de_id_fica(self):
        saida, ajustes = mcp_argumentos.normalizar({"nota": "null"}, {"nota": {}})
        self.assertEqual((saida, ajustes), ({"nota": "null"}, []))


class TestHandleToolsCall(unittest.TestCase):
    def _chamar(self, nome, argumentos, **execute):
        db = mock.MagicMock()
        with mock.patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), \
             mock.patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
             mock.patch.object(mcp_server, "execute_tool", **execute) as execute_tool:
            mcp_server._handle_tools_call({"name": nome, "arguments": argumentos},
                                          ctx=ToolContext(user_uid="u", canal="mcp", _db=db))
        registro = db.collection.return_value.add.call_args.args[0]
        return execute_tool, registro

    def test_id_com_nome_errado_chega_certo_e_fica_registrado(self):
        execute_tool, registro = self._chamar("obter_acao", {"id": "e10ef3ca"}, return_value={"id": "e10ef3ca"})
        self.assertEqual(execute_tool.call_args.args[1], {"task_id": "e10ef3ca"})
        self.assertEqual(registro["argumentos_ajustados"], ["id->task_id"])
        self.assertFalse(registro["is_error"])
        self.assertNotIn("erro_tipo", registro)

    def test_erro_grava_tipo_resumo_e_recusa(self):
        _, registro = self._chamar("consultar_job", {"job_id": "x"},
                                   return_value={"erro": "Job 'x' nao encontrado.", "status": "not_found"})
        self.assertTrue(registro["is_error"])
        self.assertEqual(registro["erro_tipo"], "nao_encontrado")
        self.assertEqual(registro["erro_resumo"], "Job 'x' nao encontrado.")
        self.assertTrue(registro["recusa_esperada"])
        self.assertNotIn("argumentos_ajustados", registro)

    def test_excecao_grava_falha_real(self):
        _, registro = self._chamar("obter_acao", {"task_id": "a"}, side_effect=RuntimeError("boom"))
        self.assertEqual((registro["erro_tipo"], registro["recusa_esperada"]), ("excecao", False))


class TestDicaDeOutraFerramenta(unittest.TestCase):
    def test_id_de_consolidacao_aponta_a_ferramenta_certa(self):
        db = _MockDB()
        db.collection("whatsapp_consolidacoes")._docs["2NJKYlgk"] = {"status": "done"}
        with mock.patch("mcp_jobs._db", return_value=db):
            r = mcp_jobs.ler_job("u", "2NJKYlgk")
        self.assertEqual(r["status"], "not_found")
        self.assertIn("ler_consolidacao_whatsapp(job_id='2NJKYlgk')", r["erro"])

    def test_id_de_sincronizacao_aponta_a_ferramenta_certa(self):
        db = _MockDB()
        db.collection("whatsapp_chats_sync_requests")._docs["49hUSq3y"] = {"status": "error"}
        with mock.patch("mcp_jobs._db", return_value=db):
            r = mcp_jobs.ler_job("u", "49hUSq3y")
        self.assertIn("sincronizar_conversas_whatsapp(request_id='49hUSq3y')", r["erro"])

    def test_id_desconhecido_sem_dica(self):
        with mock.patch("mcp_jobs._db", return_value=_MockDB()):
            r = mcp_jobs.ler_job("u", "nada")
        self.assertEqual(r["erro"], "Job 'nada' nao encontrado.")


class TestFalhaDeJobContadaUmaVez(unittest.TestCase):
    def test_excecao_no_job_registra_uma_falha(self):
        from autonomy.contracts import Decisao, PolicyDecision

        db = _MockDB()
        job = {"status": "processing", "tool": "gerar_relatorio", "uid": "dono", "job_id": "j1",
               "session_id": None, "task_id": None, "arguments": {}}
        event, _ = _make_event(db, job, job_id="j1")
        permitido = PolicyDecision(decision=Decisao.ALLOW, policy_id="p", policy_version=1, reason_code="ok")
        with mock.patch("mcp_jobs._db", return_value=db), \
             mock.patch("autonomy.policy.decisao_piso", return_value=permitido), \
             mock.patch("tools.hermes_tools.execute", side_effect=RuntimeError("boom")), \
             mock.patch("auditoria_mcp.registrar_falha_job") as registrar:
            mcp_jobs.on_mcp_job_created.__wrapped__(event)
        registrar.assert_called_once_with(db, uid="dono", tool="gerar_relatorio", job_id="j1",
                                          erro="boom", erro_tipo=mcp_jobs.ERRO_TIPO_EXCECAO)

    def test_job_travado_registra_uma_falha(self):
        from test_mcp_jobs import _FakeSweepDb

        agora = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
        db = _FakeSweepDb({"j2": {"status": "processing", "tool": "gerar_imagem", "uid": "dono",
                                  "reivindicado_em": agora - timedelta(seconds=mcp_jobs.LIMIAR_TRAVADO_SEC + 1)}})
        with mock.patch("auditoria_mcp.registrar_falha_job") as registrar:
            mcp_jobs.sweep_mcp_jobs_travados_core(db, agora=agora)
        registrar.assert_called_once()
        self.assertEqual(registrar.call_args.kwargs["erro_tipo"], mcp_jobs.ERRO_TIPO_TRAVADO)
        self.assertEqual(registrar.call_args.kwargs["tool"], "gerar_imagem")

    def test_registro_da_falha_do_job(self):
        db = mock.MagicMock()
        auditoria_mcp.registrar_falha_job(db, uid="dono", tool="gerar_relatorio", job_id="j1",
                                          erro="boom", erro_tipo="excecao")
        registro = db.collection.return_value.add.call_args.args[0]
        self.assertEqual(registro["origem"], "job")
        self.assertTrue(registro["is_error"])
        self.assertEqual((registro["erro_tipo"], registro["recusa_esperada"]), ("excecao", False))
        auditoria_mcp.registrar_falha_job(db, uid="dono", tool="t", job_id="j", erro="x", erro_tipo="politica")
        self.assertTrue(db.collection.return_value.add.call_args.args[0]["recusa_esperada"])


class TestRetroSeparaFalhaDeRecusa(unittest.TestCase):
    AGORA = datetime(2026, 10, 18, 23, 0, tzinfo=timezone.utc)

    def _log(self, horas, tool, ms, **extra):
        return {"tool": tool, "latency_ms": ms, "timestamp": (self.AGORA - timedelta(hours=horas)).isoformat(),
                "is_error": bool(extra.get("erro_tipo")) or extra.pop("is_error", False), **extra}

    def _metricas(self):
        entradas = [self._log(1, "obter_acao", ms) for ms in range(10, 200, 10)]  # 19 chamadas sem erro
        entradas += [
            self._log(2, "obter_acao", 900, erro_tipo="nao_encontrado", erro_resumo="Tarefa 'x' nao encontrada.",
                      recusa_esperada=True),
            self._log(3, "obter_acao", 950, erro_tipo="excecao", erro_resumo="boom", recusa_esperada=False),
            self._log(4, "gerar_relatorio", 0),
            self._log(4, "gerar_relatorio", 0, origem="job", erro_tipo="excecao", erro_resumo="falhou",
                      recusa_esperada=False),
            self._log(5, "calculadora", 5, is_error=True),  # registro antigo, sem causa
        ]
        db = MockDb({"agent_runs": {}, "mcp_audit_log": {f"a{i}": e for i, e in enumerate(entradas)}})
        return coletar_metricas_semana(db, self.AGORA)[1]

    def test_totais(self):
        m = self._metricas()
        self.assertEqual(m["total_calls"], 23)  # a entrada do job não é chamada nova
        self.assertEqual((m["total_falhas"], m["total_recusas"]), (3, 1))

    def test_por_tool_com_p95_e_erros_frequentes(self):
        obter = self._metricas()["tools"]["obter_acao"]
        self.assertEqual((obter["total"], obter["falhas"], obter["recusas"]), (21, 1, 1))
        self.assertEqual(obter["latencia_p50_ms"], 110.0)
        self.assertEqual(obter["latencia_p95_ms"], 900.0)
        self.assertEqual(obter["latencia_max_ms"], 950.0)
        tipos = {(e["tipo"], e["recusa"]) for e in obter["erros_frequentes"]}
        self.assertEqual(tipos, {("nao_encontrado", True), ("excecao", False)})

    def test_falha_do_job_conta_na_tool(self):
        relatorio = self._metricas()["tools"]["gerar_relatorio"]
        self.assertEqual((relatorio["total"], relatorio["falhas"]), (1, 1))

    def test_registro_sem_causa_conta_como_falha(self):
        calc = self._metricas()["tools"]["calculadora"]
        self.assertEqual(calc["falhas"], 1)
        self.assertEqual(calc["erros_frequentes"][0]["tipo"], "sem_causa_registrada")

    def test_texto_para_o_gemini_separa_falha_de_recusa(self):
        texto = formatar_texto_agregado("i", "f", {"total_runs": 0, "rotinas": {}}, self._metricas())
        self.assertIn("Falhas reais: 3", texto)
        self.assertIn("Recusas esperadas", texto)
        self.assertIn("p95 900.0ms", texto)
        self.assertIn("recusa nao_encontrado (1x): Tarefa 'x' nao encontrada.", texto)


class TestSecaoDeDadosCadastraisComAcento(unittest.TestCase):
    def test_formacao_com_acento_acha_a_secao(self):
        db = MockDb({"usuarios": {"u": {"dados_cadastrais": {"formacao": {"graduacao": "x"}, "contato": {}}}}})
        self.assertEqual(get_dados_cadastrais(db, "u", "formação"), {"formacao": {"graduacao": "x"}})
        self.assertEqual(get_dados_cadastrais(db, "u", "Formação")["formacao"], {"graduacao": "x"})
        self.assertIn("error", get_dados_cadastrais(db, "u", "família"))


if __name__ == "__main__":
    unittest.main()
