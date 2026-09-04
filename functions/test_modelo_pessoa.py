"""Testes unitários para modelo_interacao em perfil_pessoas (PR 1 da Fase 2)."""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
import json

from main import (
    tem_sinal_suficiente,
    montar_texto_fonte_modelo_pessoa,
    calcular_hash_modelo_pessoa,
    construir_prompt_modelo_pessoa,
    parse_resposta_modelo_pessoa,
    processar_modelo_pessoa,
    executar_atualizacao_modelos_pessoas,
    GEMINI_STRUCTURED_MODEL,
)
from tools.hermes_tools import _buscar_contato, ToolContext


class TestTemSinalSuficiente(unittest.TestCase):
    """Testes da função pura de decisão de sinal suficiente."""

    def test_sem_mensagens_sem_interacoes(self):
        self.assertFalse(tem_sinal_suficiente(0, 0))

    def test_poucas_mensagens_sem_interacoes(self):
        self.assertFalse(tem_sinal_suficiente(5, 0))
        self.assertFalse(tem_sinal_suficiente(1, 0))

    def test_mensagens_suficientes_sem_interacoes(self):
        self.assertTrue(tem_sinal_suficiente(6, 0))
        self.assertTrue(tem_sinal_suficiente(20, 0))

    def test_sem_mensagens_com_interacao(self):
        self.assertTrue(tem_sinal_suficiente(0, 1))
        self.assertTrue(tem_sinal_suficiente(0, 5))

    def test_poucas_mensagens_com_interacao(self):
        self.assertTrue(tem_sinal_suficiente(3, 1))

    def test_valores_none_e_invalidos(self):
        self.assertFalse(tem_sinal_suficiente(None, None))
        self.assertFalse(tem_sinal_suficiente("inv", "inv"))
        self.assertTrue(tem_sinal_suficiente("10", 0))

    def test_parametros_customizados(self):
        self.assertFalse(tem_sinal_suficiente(8, 1, min_mensagens=10, min_interacoes=2))
        self.assertTrue(tem_sinal_suficiente(10, 1, min_mensagens=10, min_interacoes=2))
        self.assertTrue(tem_sinal_suficiente(2, 2, min_mensagens=10, min_interacoes=2))


class TestMontarTextoFonteModeloPessoa(unittest.TestCase):
    """Testes da montagem de texto fonte consolidado."""

    def test_mensagens_e_interacoes_completas(self):
        mensagens = [
            {"from_me": False, "content": "Olá André, tudo bem?", "timestamp": "2026-09-01T10:00:00Z"},
            {"from_me": True, "content": "Tudo ótimo, Carlos! Já estou vendo aquele relatório.", "timestamp": "2026-09-01T10:05:00Z"},
        ]
        interacoes = [
            {"data": "2026-09-02", "tarefa_id": "task123", "descricao": "Discutiu alinhamento da auditoria"},
            {"data": "2026-09-03", "descricao": "Reunião de alinhamento geral"},
        ]
        tarefas_map = {"task123": "Auditoria MEC"}

        texto = montar_texto_fonte_modelo_pessoa("Carlos Silva", mensagens, interacoes, tarefas_map)
        self.assertIn("Pessoa: Carlos Silva", texto)
        self.assertIn("Carlos Silva: Olá André, tudo bem?", texto)
        self.assertIn("André: Tudo ótimo, Carlos!", texto)
        self.assertIn("Ação: Auditoria MEC (task123) — Discutiu alinhamento", texto)
        self.assertIn("Reunião de alinhamento geral", texto)

    def test_mensagens_vazias_e_interacoes_vazias(self):
        texto = montar_texto_fonte_modelo_pessoa("Maria", [], [])
        self.assertIn("Pessoa: Maria", texto)
        self.assertIn("Nenhuma mensagem de WhatsApp encontrada.", texto)
        self.assertIn("Nenhuma interação recente registrada.", texto)

    def test_mensagens_com_transcricao_audio(self):
        mensagens = [
            {"from_me": False, "content": "", "transcription_text": "Áudio dizendo que aprovou a nota técnica.", "timestamp": None}
        ]
        texto = montar_texto_fonte_modelo_pessoa("Beatriz", mensagens, [])
        self.assertIn("Beatriz: Áudio dizendo que aprovou a nota técnica.", texto)

    def test_contato_sem_nome(self):
        texto = montar_texto_fonte_modelo_pessoa("", [], [])
        self.assertIn("Pessoa: Contato", texto)


class TestCalcularHashEConstruirPrompt(unittest.TestCase):
    """Testes de hash e prompt do modelo de pessoa."""

    def test_calcular_hash_deterministico(self):
        h1 = calcular_hash_modelo_pessoa("Texto 1")
        h2 = calcular_hash_modelo_pessoa("Texto 1")
        h3 = calcular_hash_modelo_pessoa("Texto 2")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_construir_prompt_regras_inegociaveis(self):
        prompt = construir_prompt_modelo_pessoa("Dr. Roberto", "Algum texto fonte")
        self.assertIn("Dr. Roberto", prompt)
        self.assertIn("NUNCA INVENTE OU SUPONHA", prompt)
        self.assertIn('"registro": null', prompt)
        self.assertIn('"tempo_resposta_tipico": null', prompt)
        self.assertIn('"acoes_recentes"', prompt)
        self.assertIn("ESTRITAMENTE com o objeto JSON válido", prompt)


class TestParseRespostaModeloPessoa(unittest.TestCase):
    """Testes do parser defensivo de resposta do LLM."""

    def test_json_limpo(self):
        raw = json.dumps({
            "registro": "formal, trata por Dr. Roberto",
            "tempo_resposta_tipico": "costuma responder em ~1h durante o horário comercial",
            "acoes_recentes": ["Auditoria MEC (task123)", "Renovação de Termo (task456)"]
        })
        res = parse_resposta_modelo_pessoa(raw)
        self.assertIsNotNone(res)
        self.assertEqual(res["registro"], "formal, trata por Dr. Roberto")
        self.assertEqual(res["tempo_resposta_tipico"], "costuma responder em ~1h durante o horário comercial")
        self.assertEqual(len(res["acoes_recentes"]), 2)
        self.assertIn("atualizado_em", res)

    def test_json_com_cercas_markdown(self):
        raw = """```json
{
  "registro": "informal, brincam bastante",
  "tempo_resposta_tipico": null,
  "acoes_recentes": []
}
```"""
        res = parse_resposta_modelo_pessoa(raw)
        self.assertIsNotNone(res)
        self.assertEqual(res["registro"], "informal, brincam bastante")
        self.assertIsNone(res["tempo_resposta_tipico"])
        self.assertEqual(res["acoes_recentes"], [])

    def test_json_com_texto_ao_redor(self):
        raw = """Aqui está a análise:
{
  "registro": null,
  "tempo_resposta_tipico": null,
  "acoes_recentes": []
}
Espero ter ajudado!"""
        res = parse_resposta_modelo_pessoa(raw)
        self.assertIsNotNone(res)
        self.assertIsNone(res["registro"])
        self.assertIsNone(res["tempo_resposta_tipico"])
        self.assertEqual(res["acoes_recentes"], [])

    def test_sanitizacao_variantes_nulas(self):
        raw = json.dumps({
            "registro": "None",
            "tempo_resposta_tipico": "N/A",
            "acoes_recentes": ["Ação 1", "", "  ", None]
        })
        res = parse_resposta_modelo_pessoa(raw)
        self.assertIsNotNone(res)
        self.assertIsNone(res["registro"])
        self.assertIsNone(res["tempo_resposta_tipico"])
        self.assertEqual(res["acoes_recentes"], ["Ação 1"])

    def test_respostas_invalidas_ou_vazias(self):
        self.assertIsNone(parse_resposta_modelo_pessoa(None))
        self.assertIsNone(parse_resposta_modelo_pessoa(""))
        self.assertIsNone(parse_resposta_modelo_pessoa("   "))
        self.assertIsNone(parse_resposta_modelo_pessoa("não é um json"))
        self.assertIsNone(parse_resposta_modelo_pessoa("[1, 2, 3]"))


class TestProcessarModeloPessoa(unittest.TestCase):
    """Testes do fluxo de processamento de uma pessoa individual."""

    def test_pessoa_sem_chat_id(self):
        db = MagicMock()
        res = processar_modelo_pessoa(db, "p1", {"nome": "Sem Chat", "whatsapp_chat_id": ""})
        self.assertFalse(res)
        db.collection.assert_not_called()

    def test_pessoa_baixo_sinal(self):
        db = MagicMock()
        # Mock de 2 mensagens e 0 interacoes
        mock_msg_stream = [MagicMock(to_dict=lambda: {"from_me": False, "content": "Oi", "timestamp": datetime.now(timezone.utc)}) for _ in range(2)]
        mock_inter_stream = []

        def mock_collection(col_name):
            col = MagicMock()
            if col_name == "whatsapp_messages":
                col.where.return_value.order_by.return_value.limit.return_value.stream.return_value = mock_msg_stream
            elif col_name == "interacoes_pessoas":
                col.where.return_value.limit.return_value.stream.return_value = mock_inter_stream
            return col

        db.collection = mock_collection

        res = processar_modelo_pessoa(db, "p1", {"nome": "Pouco Sinal", "whatsapp_chat_id": "5527999@c.us"})
        self.assertFalse(res)

    def test_pessoa_hash_inalterado(self):
        db = MagicMock()
        now = datetime.now(timezone.utc)
        mock_msg_stream = [
            MagicMock(to_dict=lambda i=i: {"from_me": False, "content": f"Msg {i}", "timestamp": now})
            for i in range(8)
        ]
        mock_inter_stream = []

        def mock_collection(col_name):
            col = MagicMock()
            if col_name == "whatsapp_messages":
                col.where.return_value.order_by.return_value.limit.return_value.stream.return_value = mock_msg_stream
            elif col_name == "interacoes_pessoas":
                col.where.return_value.limit.return_value.stream.return_value = mock_inter_stream
            return col

        db.collection = mock_collection

        # Calcula o hash esperado
        msgs = [{"from_me": False, "content": f"Msg {i}", "timestamp": now} for i in range(8)]
        texto = montar_texto_fonte_modelo_pessoa("João", list(reversed(msgs)), [])
        expected_hash = calcular_hash_modelo_pessoa(texto)

        res = processar_modelo_pessoa(
            db,
            "p1",
            {"nome": "João", "whatsapp_chat_id": "5527999@c.us", "last_processed_modelo_hash": expected_hash},
        )
        self.assertFalse(res)

    @patch("main.generate_content_logged")
    def test_chamada_gemini_sucesso(self, mock_generate):
        db = MagicMock()
        now = datetime.now(timezone.utc)
        mock_msg_stream = [
            MagicMock(to_dict=lambda: {"from_me": False, "content": f"Msg {i}", "timestamp": now})
            for i in range(8)
        ]
        mock_inter_stream = []

        perfil_doc_mock = MagicMock()

        def mock_collection(col_name):
            col = MagicMock()
            if col_name == "whatsapp_messages":
                col.where.return_value.order_by.return_value.limit.return_value.stream.return_value = mock_msg_stream
            elif col_name == "interacoes_pessoas":
                col.where.return_value.limit.return_value.stream.return_value = mock_inter_stream
            elif col_name == "perfil_pessoas":
                col.document.return_value = perfil_doc_mock
            return col

        db.collection = mock_collection

        fake_resp = MagicMock()
        fake_resp.text = json.dumps({
            "registro": "cordial e direto",
            "tempo_resposta_tipico": "responde no mesmo dia",
            "acoes_recentes": []
        })
        mock_generate.return_value = fake_resp

        client = MagicMock()
        res = processar_modelo_pessoa(
            db,
            "p1",
            {"nome": "João", "whatsapp_chat_id": "5527999@c.us"},
            client=client
        )

        self.assertTrue(res)
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args[1]
        self.assertEqual(call_kwargs["feature"], "modelo_pessoa")
        self.assertEqual(call_kwargs["model"], GEMINI_STRUCTURED_MODEL)

        perfil_doc_mock.update.assert_called_once()
        update_data = perfil_doc_mock.update.call_args[0][0]
        self.assertIn("modelo_interacao", update_data)
        self.assertIn("last_processed_modelo_hash", update_data)
        self.assertEqual(update_data["modelo_interacao"]["registro"], "cordial e direto")

    @patch("main.generate_content_logged")
    def test_chamada_gemini_parse_falho_grava_somente_hash(self, mock_generate):
        db = MagicMock()
        now = datetime.now(timezone.utc)
        mock_msg_stream = [
            MagicMock(to_dict=lambda: {"from_me": False, "content": f"Msg {i}", "timestamp": now})
            for i in range(8)
        ]
        mock_inter_stream = []

        perfil_doc_mock = MagicMock()

        def mock_collection(col_name):
            col = MagicMock()
            if col_name == "whatsapp_messages":
                col.where.return_value.order_by.return_value.limit.return_value.stream.return_value = mock_msg_stream
            elif col_name == "interacoes_pessoas":
                col.where.return_value.limit.return_value.stream.return_value = mock_inter_stream
            elif col_name == "perfil_pessoas":
                col.document.return_value = perfil_doc_mock
            return col

        db.collection = mock_collection

        fake_resp = MagicMock()
        fake_resp.text = "Erro ou texto não estruturado"
        mock_generate.return_value = fake_resp

        client = MagicMock()
        res = processar_modelo_pessoa(
            db,
            "p1",
            {"nome": "João", "whatsapp_chat_id": "5527999@c.us"},
            client=client
        )

        self.assertFalse(res)
        perfil_doc_mock.update.assert_called_once()
        update_data = perfil_doc_mock.update.call_args[0][0]
        self.assertNotIn("modelo_interacao", update_data)
        self.assertIn("last_processed_modelo_hash", update_data)

    @patch("main.generate_content_logged")
    def test_chamada_gemini_excecao(self, mock_generate):
        db = MagicMock()
        now = datetime.now(timezone.utc)
        mock_msg_stream = [
            MagicMock(to_dict=lambda: {"from_me": False, "content": f"Msg {i}", "timestamp": now})
            for i in range(8)
        ]

        def mock_collection(col_name):
            col = MagicMock()
            if col_name == "whatsapp_messages":
                col.where.return_value.order_by.return_value.limit.return_value.stream.return_value = mock_msg_stream
            elif col_name == "interacoes_pessoas":
                col.where.return_value.limit.return_value.stream.return_value = []
            return col

        db.collection = mock_collection

        mock_generate.side_effect = RuntimeError("Falha de rede na API")

        client = MagicMock()
        res = processar_modelo_pessoa(
            db,
            "p1",
            {"nome": "João", "whatsapp_chat_id": "5527999@c.us"},
            client=client
        )
        self.assertFalse(res)


class TestExecutarAtualizacaoModelosPessoas(unittest.TestCase):
    """Testes do iterador geral com isolamento de falha."""

    @patch("main.processar_modelo_pessoa")
    def test_isolamento_falha_entre_pessoas(self, mock_processar):
        db = MagicMock()
        snap1 = MagicMock(id="p1")
        snap1.to_dict.return_value = {"nome": "Pessoa 1", "whatsapp_chat_id": "111@c.us"}
        snap2 = MagicMock(id="p2")
        snap2.to_dict.return_value = {"nome": "Pessoa 2", "whatsapp_chat_id": "222@c.us"}
        snap3 = MagicMock(id="p3")
        snap3.to_dict.return_value = {"nome": "Pessoa 3", "whatsapp_chat_id": ""}

        db.collection.return_value.stream.return_value = [snap1, snap2, snap3]

        mock_processar.side_effect = [RuntimeError("Erro inesperado"), True]

        stats = executar_atualizacao_modelos_pessoas(db)

        self.assertEqual(stats["total_analisados"], 3)
        self.assertEqual(stats["sem_chat"], 1)
        self.assertEqual(stats["erros"], 1)
        self.assertEqual(stats["atualizados"], 1)
        self.assertEqual(mock_processar.call_count, 2)


class TestBuscarContatoTool(unittest.TestCase):
    """Testes da ferramenta buscar_contato com modelo_interacao."""

    def test_buscar_contato_com_modelo_interacao(self):
        doc_mock = MagicMock()
        doc_mock.id = "p123"
        doc_mock.to_dict.return_value = {
            "nome": "Guilherme Santos",
            "email": "guilherme@example.com",
            "whatsapp_chat_id": "552799999999@c.us",
            "tags": ["mec", "dev"],
            "modelo_interacao": {
                "registro": "técnico e direto",
                "tempo_resposta_tipico": "costuma responder em ~15min",
                "acoes_recentes": ["MEC Sustentável"],
                "atualizado_em": "2026-09-04T05:00:00Z"
            }
        }

        db_mock = MagicMock()
        db_mock.collection.return_value.limit.return_value.stream.return_value = [doc_mock]

        ctx = ToolContext(_db=db_mock, user_uid="user123", task_id="t1")
        res = _buscar_contato(ctx, {"termo": "guilherme"})

        self.assertEqual(len(res["candidatos"]), 1)
        cand = res["candidatos"][0]
        self.assertIn("modelo_interacao", cand)
        self.assertEqual(cand["modelo_interacao"]["registro"], "técnico e direto")

    def test_buscar_contato_sem_modelo_interacao(self):
        doc_mock = MagicMock()
        doc_mock.id = "p456"
        doc_mock.to_dict.return_value = {
            "nome": "Iris Silva",
            "email": "iris@example.com",
            "whatsapp_chat_id": "552788888888@c.us",
            "tags": ["social"],
        }

        db_mock = MagicMock()
        db_mock.collection.return_value.limit.return_value.stream.return_value = [doc_mock]

        ctx = ToolContext(_db=db_mock, user_uid="user123", task_id="t1")
        res = _buscar_contato(ctx, {"termo": "iris"})

        self.assertEqual(len(res["candidatos"]), 1)
        cand = res["candidatos"][0]
        self.assertIn("modelo_interacao", cand)
        self.assertIsNone(cand["modelo_interacao"])


if __name__ == "__main__":
    unittest.main()
