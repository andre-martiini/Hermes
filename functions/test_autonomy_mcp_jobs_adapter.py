"""Testes de `autonomy/mcp_jobs_adapter.py` — só lógica pura, sem I/O (P04
passo 6 do pacote: "Unificar o ciclo de jobs MCP através de adaptador ao
protocolo, preservando job_id e sem fundir coleções cegamente").

Cobre a tradução do vocabulário bruto de um documento `mcp_jobs`
(status "processing"/"done"/"error" + `reivindicado_em`) para
`autonomy.requests.RequestStatus`, e a projeção compacta
`resumo_protocolo_de_job`.
"""

import unittest

from autonomy.mcp_jobs_adapter import (
    StatusMcpJobDesconhecido,
    request_status_de_job,
    resumo_protocolo_de_job,
)
from autonomy.requests import RequestStatus


class TestRequestStatusDeJob(unittest.TestCase):
    def test_processing_sem_reivindicacao_e_pendente(self):
        self.assertEqual(
            request_status_de_job({"status": "processing"}),
            RequestStatus.PENDENTE,
        )

    def test_processing_com_reivindicado_em_none_explicito_e_pendente(self):
        self.assertEqual(
            request_status_de_job({"status": "processing", "reivindicado_em": None}),
            RequestStatus.PENDENTE,
        )

    def test_processing_reivindicado_e_em_andamento(self):
        self.assertEqual(
            request_status_de_job(
                {"status": "processing", "reivindicado_em": "qualquer-valor-truthy"}
            ),
            RequestStatus.EM_ANDAMENTO,
        )

    def test_processing_reivindicado_por_timestamp_do_servidor_e_em_andamento(self):
        # reivindicado_em normalmente é um firestore.SERVER_TIMESTAMP já
        # resolvido para um Timestamp real na leitura -- qualquer valor
        # não-None conta, o tipo exato não importa para a tradução.
        self.assertEqual(
            request_status_de_job({"status": "processing", "reivindicado_em": 12345}),
            RequestStatus.EM_ANDAMENTO,
        )

    def test_done_e_concluido(self):
        self.assertEqual(
            request_status_de_job({"status": "done", "resultado": "ok"}),
            RequestStatus.CONCLUIDO,
        )

    def test_done_e_concluido_mesmo_sem_reivindicado_em(self):
        # Documento real sempre tem reivindicado_em depois de "done" (o
        # trigger só grava "done" depois de reivindicar), mas a tradução não
        # depende disso -- "done"/"error" decidem sozinhos, sem olhar o
        # booleano de reivindicação.
        self.assertEqual(
            request_status_de_job({"status": "done"}),
            RequestStatus.CONCLUIDO,
        )

    def test_error_e_falha_final(self):
        self.assertEqual(
            request_status_de_job({"status": "error", "erro": "algo quebrou"}),
            RequestStatus.FALHA_FINAL,
        )

    def test_error_nunca_e_erro_legado(self):
        # ERRO_LEGADO é só para normalizar leitura do formato legado de
        # agent_requests.py -- um job MCP não é esse formato.
        self.assertNotEqual(
            request_status_de_job({"status": "error"}),
            RequestStatus.ERRO_LEGADO,
        )

    def test_status_desconhecido_levanta(self):
        with self.assertRaises(StatusMcpJobDesconhecido):
            request_status_de_job({"status": "cancelado"})

    def test_status_ausente_levanta(self):
        with self.assertRaises(StatusMcpJobDesconhecido):
            request_status_de_job({})

    def test_dados_none_levanta(self):
        with self.assertRaises(StatusMcpJobDesconhecido):
            request_status_de_job(None)

    def test_status_desconhecido_preserva_valor_bruto_na_excecao(self):
        try:
            request_status_de_job({"status": "pausado"})
            self.fail("deveria ter levantado StatusMcpJobDesconhecido")
        except StatusMcpJobDesconhecido as exc:
            self.assertEqual(exc.status_bruto, "pausado")


class TestResumoProtocoloDeJob(unittest.TestCase):
    def test_preserva_job_id_exatamente(self):
        resumo = resumo_protocolo_de_job(
            "mcpjob-abc123", {"status": "processing", "tool": "gerar_relatorio"}
        )
        self.assertEqual(resumo["job_id"], "mcpjob-abc123")

    def test_campos_basicos(self):
        resumo = resumo_protocolo_de_job(
            "mcpjob-abc123",
            {"status": "done", "tool": "gerar_relatorio", "resultado": "texto"},
        )
        self.assertEqual(resumo["origem"], "mcp_jobs")
        self.assertEqual(resumo["request_status"], RequestStatus.CONCLUIDO.value)
        self.assertEqual(resumo["status_mcp_original"], "done")
        self.assertEqual(resumo["tool"], "gerar_relatorio")
        # Não deve reexpor o resultado -- este resumo é só o vocabulário de
        # estado, não substitui mcp_jobs.ler_job para o conteúdo.
        self.assertNotIn("resultado", resumo)

    def test_job_id_vazio_levanta(self):
        with self.assertRaises(ValueError):
            resumo_protocolo_de_job("", {"status": "processing"})

    def test_job_id_none_levanta(self):
        with self.assertRaises(ValueError):
            resumo_protocolo_de_job(None, {"status": "processing"})

    def test_job_id_com_espacos_e_normalizado(self):
        resumo = resumo_protocolo_de_job("  mcpjob-xyz  ", {"status": "done"})
        self.assertEqual(resumo["job_id"], "mcpjob-xyz")

    def test_propaga_status_desconhecido(self):
        with self.assertRaises(StatusMcpJobDesconhecido):
            resumo_protocolo_de_job("mcpjob-abc", {"status": "algo_invalido"})

    def test_status_mcp_original_preservado_mesmo_em_falha(self):
        resumo = resumo_protocolo_de_job("mcpjob-abc", {"status": "error", "erro": "x"})
        self.assertEqual(resumo["status_mcp_original"], "error")
        self.assertEqual(resumo["request_status"], RequestStatus.FALHA_FINAL.value)


if __name__ == "__main__":
    unittest.main()
