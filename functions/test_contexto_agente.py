"""Testes unitários para PR 5 (Fase 1): contexto_agente auto-mantido em ações críticas.

Cobre:
- Função pura de decisão 'é crítica?' (idêntica a inbox_pendentes.py).
- Montagem do texto fonte estruturado e cálculo de hash MD5.
- Prompt e regra inegociável de não inventar informação.
- Parse defensivo do JSON do Gemini e normalização dos campos.
- Processamento com firestore mockado, telemetria de custo e trava de tarefas não críticas/sistemas.
- Obter_acao em hermes_tools incluindo contexto_agente.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from main import (
    eh_acao_critica,
    montar_texto_fonte_contexto,
    calcular_hash_contexto,
    construir_prompt_contexto,
    parse_resposta_contexto,
    processar_contexto_agente,
    on_tarefa_written_contexto_agente,
)
from tools.hermes_tools import obter_acao


class TestEhAcaoCritica(unittest.TestCase):
    def test_vazio_ou_nulo_retorna_false(self):
        self.assertFalse(eh_acao_critica(None))
        self.assertFalse(eh_acao_critica({}))

    def test_lane_critica_retorna_true(self):
        self.assertTrue(eh_acao_critica({"execution_lane": "critica"}))
        self.assertTrue(eh_acao_critica({"execution_lane": "CRITICA"}))
        self.assertTrue(eh_acao_critica({"execution_lane": " critica "}))

    def test_degradation_count_maior_ou_igual_3_retorna_true(self):
        self.assertTrue(eh_acao_critica({"degradation_count": 3}))
        self.assertTrue(eh_acao_critica({"degradation_count": 5}))
        self.assertTrue(eh_acao_critica({"degradation_count": "4"}))

    def test_tarefa_normal_retorna_false(self):
        self.assertFalse(eh_acao_critica({"execution_lane": "padrao", "degradation_count": 0}))
        self.assertFalse(eh_acao_critica({"execution_lane": "avanco", "degradation_count": 2}))
        self.assertFalse(eh_acao_critica({"execution_lane": "continuo"}))

    def test_degradation_count_invalido_nao_explode(self):
        self.assertFalse(eh_acao_critica({"degradation_count": "nao_numerico"}))


class TestMontagemTextoEHash(unittest.TestCase):
    def test_montagem_texto_completo(self):
        task_data = {
            "titulo": "Migração do Banco de Dados",
            "descricao": "Migrar Postgres para Spanner",
            "plano_acao": [
                {"texto": "Fazer dump dos dados", "estado": "concluido"},
                {"texto": "Validar schema", "estado": "em_andamento"},
            ],
            "acompanhamento": [
                {"data": "2026-09-01", "nota": "Dump finalizado sem erros."},
                {"data": "2026-09-02", "nota": "Iniciada validação de schema."},
            ],
        }
        texto = montar_texto_fonte_contexto(task_data)
        self.assertIn("Migração do Banco de Dados", texto)
        self.assertIn("Migrar Postgres para Spanner", texto)
        self.assertIn("[concluido] Fazer dump dos dados", texto)
        self.assertIn("[em_andamento] Validar schema", texto)
        self.assertIn("[2026-09-01] Dump finalizado sem erros.", texto)
        self.assertIn("[2026-09-02] Iniciada validação de schema.", texto)

    def test_limite_diario_respeitado(self):
        task_data = {
            "titulo": "Tarefa Longa",
            "acompanhamento": [{"data": f"2026-09-{i:02d}", "nota": f"Nota {i}"} for i in range(1, 30)],
        }
        texto = montar_texto_fonte_contexto(task_data, limite_diario=20)
        self.assertNotIn("Nota 1\n", texto)
        self.assertNotIn("Nota 9\n", texto)
        self.assertIn("Nota 10", texto)
        self.assertIn("Nota 29", texto)

    def test_tarefa_sem_plano_nem_diario(self):
        task_data = {"titulo": "Simples", "descricao": "Sem mais dados"}
        texto = montar_texto_fonte_contexto(task_data)
        self.assertIn("Nenhuma etapa cadastrada.", texto)
        self.assertIn("Nenhuma anotação de diário.", texto)

    def test_hash_deterministico(self):
        t1 = "Texto 1"
        t2 = "Texto 1"
        t3 = "Texto 2"
        h1 = calcular_hash_contexto(t1)
        h2 = calcular_hash_contexto(t2)
        h3 = calcular_hash_contexto(t3)
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)


class TestPromptContexto(unittest.TestCase):
    def test_prompt_contem_regras_inegociaveis(self):
        prompt = construir_prompt_contexto("Fonte de teste")
        self.assertIn("NÃO INVENTE NADA", prompt)
        self.assertIn("onde_esta_o_codigo", prompt)
        self.assertIn("null", prompt)
        self.assertIn("Fonte de teste", prompt)


class TestParseRespostaContexto(unittest.TestCase):
    def test_parse_json_limpo(self):
        raw = json.dumps({
            "resumo": "Ação para implementar autenticação OAuth2.",
            "pessoas_chave": ["Carlos (Dev backend)", "Marina (PO)"],
            "onde_esta_o_codigo": "repo: org/auth, branch: feat/oauth2",
            "ultimas_decisoes": ["Utilizar JWT com rotação de chaves"],
            "travas": ["Aguardando liberação de credenciais no Google Cloud"],
        })
        res = parse_resposta_contexto(raw)
        self.assertIsNotNone(res)
        self.assertEqual(res["resumo"], "Ação para implementar autenticação OAuth2.")
        self.assertEqual(len(res["pessoas_chave"]), 2)
        self.assertEqual(res["onde_esta_o_codigo"], "repo: org/auth, branch: feat/oauth2")
        self.assertEqual(res["ultimas_decisoes"], ["Utilizar JWT com rotação de chaves"])
        self.assertEqual(res["travas"], ["Aguardando liberação de credenciais no Google Cloud"])
        self.assertTrue("atualizado_em" in res)

    def test_parse_json_com_cerca_markdown(self):
        raw = """```json
{
  "resumo": "Refatoração de pipelines.",
  "pessoas_chave": [],
  "onde_esta_o_codigo": null,
  "ultimas_decisoes": [],
  "travas": []
}
```"""
        res = parse_resposta_contexto(raw)
        self.assertIsNotNone(res)
        self.assertEqual(res["resumo"], "Refatoração de pipelines.")
        self.assertIsNone(res["onde_esta_o_codigo"])
        self.assertEqual(res["pessoas_chave"], [])

    def test_parse_json_com_cerca_sem_identificador(self):
        raw = """```
{
  "resumo": "Correção de bug crítico.",
  "pessoas_chave": ["Alice"],
  "onde_esta_o_codigo": "main",
  "ultimas_decisoes": [],
  "travas": []
}
```"""
        res = parse_resposta_contexto(raw)
        self.assertIsNotNone(res)
        self.assertEqual(res["resumo"], "Correção de bug crítico.")
        self.assertEqual(res["pessoas_chave"], ["Alice"])

    def test_parse_json_com_texto_ao_redor(self):
        raw = """Aqui está o resumo estruturado:
{
  "resumo": "Configuração de monitoramento.",
  "pessoas_chave": [],
  "onde_esta_o_codigo": "null",
  "ultimas_decisoes": [],
  "travas": []
}
Espero que ajude!"""
        res = parse_resposta_contexto(raw)
        self.assertIsNotNone(res)
        self.assertEqual(res["resumo"], "Configuração de monitoramento.")
        self.assertIsNone(res["onde_esta_o_codigo"])

    def test_parse_resposta_vazia_ou_invalida_retorna_none(self):
        self.assertIsNone(parse_resposta_contexto(""))
        self.assertIsNone(parse_resposta_contexto(None))
        self.assertIsNone(parse_resposta_contexto("apenas texto sem json"))
        self.assertIsNone(parse_resposta_contexto('{"pessoas_chave": []}'))  # Sem resumo

    def test_normalizacao_onde_esta_o_codigo(self):
        casos_none = ["null", "None", "N/A", "n/a", "não informado", "nao informado", "   "]
        for c in casos_none:
            raw = json.dumps({"resumo": "Teste", "onde_esta_o_codigo": c})
            res = parse_resposta_contexto(raw)
            self.assertIsNone(res["onde_esta_o_codigo"], f"Falhou para caso: {c}")


class TestProcessarContextoAgente(unittest.TestCase):
    def test_ignora_sistemas(self):
        client = MagicMock()
        db = MagicMock()
        task_data = {"area_tematica": "SISTEMAS", "execution_lane": "critica"}
        res = processar_contexto_agente(db, "t1", task_data, client=client)
        self.assertFalse(res)
        client.models.generate_content.assert_not_called()
        db.collection.assert_not_called()

    def test_ignora_nao_critica(self):
        client = MagicMock()
        db = MagicMock()
        task_data = {"execution_lane": "padrao", "degradation_count": 0}
        res = processar_contexto_agente(db, "t1", task_data, client=client)
        self.assertFalse(res)
        client.models.generate_content.assert_not_called()
        db.collection.assert_not_called()

    def test_ignora_se_hash_ja_processado(self):
        client = MagicMock()
        db = MagicMock()
        task_data = {
            "titulo": "Tarefa",
            "execution_lane": "critica",
        }
        h = calcular_hash_contexto(montar_texto_fonte_contexto(task_data))
        task_data["last_processed_contexto_hash"] = h

        res = processar_contexto_agente(db, "t1", task_data, client=client)
        self.assertFalse(res)
        client.models.generate_content.assert_not_called()
        db.collection.assert_not_called()

    @patch("main.generate_content_logged")
    def test_sucesso_chama_gemini_com_feature_e_modelo_e_atualiza_firestore(self, mock_generate):
        mock_resp = MagicMock()
        mock_resp.text = json.dumps({
            "resumo": "Ação crítica de sustentação.",
            "pessoas_chave": ["João"],
            "onde_esta_o_codigo": "main",
            "ultimas_decisoes": ["Deploy aprovado"],
            "travas": [],
        })
        mock_generate.return_value = mock_resp

        client = MagicMock()
        db = MagicMock()
        task_data = {
            "titulo": "Sustentação",
            "execution_lane": "critica",
        }

        res = processar_contexto_agente(db, "t1", task_data, client=client)
        self.assertTrue(res)

        mock_generate.assert_called_once()
        _, kwargs = mock_generate.call_args
        self.assertEqual(kwargs.get("feature"), "contexto_agente")
        self.assertEqual(kwargs.get("model"), "gemini-3.5-flash-lite")

        doc_ref = db.collection("tarefas").document("t1")
        doc_ref.update.assert_called_once()
        update_arg = doc_ref.update.call_args[0][0]
        self.assertIn("contexto_agente", update_arg)
        self.assertIn("last_processed_contexto_hash", update_arg)
        self.assertEqual(update_arg["contexto_agente"]["resumo"], "Ação crítica de sustentação.")

    @patch("main.generate_content_logged")
    def test_parse_falho_atualiza_apenas_hash_para_evitar_loop(self, mock_generate):
        mock_resp = MagicMock()
        mock_resp.text = "Texto desconexo sem json"
        mock_generate.return_value = mock_resp

        client = MagicMock()
        db = MagicMock()
        task_data = {
            "titulo": "Sustentação",
            "execution_lane": "critica",
        }

        res = processar_contexto_agente(db, "t1", task_data, client=client)
        self.assertFalse(res)

        doc_ref = db.collection("tarefas").document("t1")
        doc_ref.update.assert_called_once()
        update_arg = doc_ref.update.call_args[0][0]
        self.assertNotIn("contexto_agente", update_arg)
        self.assertIn("last_processed_contexto_hash", update_arg)

    @patch("main.get_gemini_api_key", return_value=None)
    def test_api_key_ausente_retorna_false_sem_estourar(self, mock_key):
        db = MagicMock()
        task_data = {"titulo": "Sustentação", "execution_lane": "critica"}
        res = processar_contexto_agente(db, "t1", task_data)
        self.assertFalse(res)
        db.collection.assert_not_called()

    @patch("main.generate_content_logged", side_effect=RuntimeError("Gemini indisponivel"))
    def test_excecao_gemini_retorna_false_sem_estourar(self, mock_gen):
        client = MagicMock()
        db = MagicMock()
        task_data = {"titulo": "Sustentação", "execution_lane": "critica"}
        res = processar_contexto_agente(db, "t1", task_data, client=client)
        self.assertFalse(res)
        db.collection.assert_not_called()


class TestTriggerFirestore(unittest.TestCase):
    def setUp(self):
        import inspect
        self.fn = inspect.unwrap(on_tarefa_written_contexto_agente)

    def test_trigger_tarefa_deletada_ignora(self):
        event = MagicMock()
        event.data.after = None
        # Não deve lançar exceção
        self.fn(event)

    def test_trigger_absorve_excecoes_sem_propagar(self):
        event = MagicMock()
        event.data.after.exists = True
        event.data.after.to_dict.side_effect = RuntimeError("Erro simulado")
        # Não deve lançar exceção
        self.fn(event)


class TestObterAcaoContextoAgente(unittest.TestCase):
    def test_obter_acao_inclui_contexto_agente_quando_presente(self):
        ctx = MagicMock()
        ctx.task_id = "task_critica"
        snap = MagicMock()
        snap.exists = True
        snap.id = "task_critica"
        contexto = {
            "resumo": "Ação crítica em andamento",
            "pessoas_chave": ["André"],
            "onde_esta_o_codigo": "repo/main",
            "ultimas_decisoes": ["Decisão X"],
            "travas": [],
            "atualizado_em": "2026-09-04T00:00:00Z",
        }
        snap.to_dict.return_value = {
            "titulo": "Ação Crítica",
            "contexto_agente": contexto,
        }
        ctx.db.collection("tarefas").document("task_critica").get.return_value = snap

        res = obter_acao(ctx, {"task_id": "task_critica"})
        self.assertEqual(res.get("contexto_agente"), contexto)

    def test_obter_acao_contexto_agente_none_quando_ausente(self):
        ctx = MagicMock()
        ctx.task_id = "task_normal"
        snap = MagicMock()
        snap.exists = True
        snap.id = "task_normal"
        snap.to_dict.return_value = {
            "titulo": "Ação Normal",
        }
        ctx.db.collection("tarefas").document("task_normal").get.return_value = snap

        res = obter_acao(ctx, {"task_id": "task_normal"})
        self.assertIn("contexto_agente", res)
        self.assertIsNone(res.get("contexto_agente"))


if __name__ == "__main__":
    unittest.main()
