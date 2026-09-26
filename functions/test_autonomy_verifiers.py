"""Testes de `autonomy/verifiers.py` -- só lógica pura, sem I/O (P04 do
plano de autonomia, docs/plano-hermes-autonomo-2026-09-06.md, passo 8 do
pacote: "Implementar verificadores determinísticos das primeiras operações:
tarefa, artefato, consolidação e outbox").
"""

import unittest

from autonomy.verifiers import (
    EvidenciaArtefatoBriefing,
    EvidenciaAtualizacaoTarefa,
    EvidenciaConsolidacaoAudio,
    EvidenciaEnvioWhatsApp,
    ResultadoVerificacao,
    verificar_artefato_briefing,
    verificar_atualizacao_tarefa,
    verificar_consolidacao_audio,
    verificar_envio_whatsapp,
)


class TestVerificarAtualizacaoTarefa(unittest.TestCase):
    def test_aceito_quando_tudo_confere(self):
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={"titulo": "Preparar reunião"},
            campos_releitura={"status": "feito", "titulo": "Preparar reunião", "id": "acao-1"},
            versao_esperada=2,
            versao_releitura=2,
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.ACEITO)

    def test_aceito_sem_versionamento(self):
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={"status": "feito"},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.ACEITO)

    def test_pendente_quando_versao_da_releitura_nao_confere(self):
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={"status": "feito"},
            versao_esperada=2,
            versao_releitura=1,
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)

    def test_refutado_quando_campo_preservado_mudou(self):
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={"titulo": "Preparar reunião"},
            campos_releitura={"status": "feito", "titulo": "TÍTULO ALTERADO SEM QUERER"},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)
        self.assertIn("titulo", resultado.detalhes["campos_preservados_violados"])

    def test_campo_preservado_ausente_na_releitura_nao_bloqueia_aceite(self):
        # Campo ausente é "ainda não sabemos", não "não mudou" -- não pode
        # produzir REFUTADO por si só.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={"titulo": "Preparar reunião"},
            campos_releitura={"status": "feito"},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        # Nenhuma violação de preservação detectada (ausência não conta);
        # a alteração está completa -- resultado deve ser ACEITO.
        self.assertEqual(resultado.resultado, ResultadoVerificacao.ACEITO)

    def test_pendente_quando_campo_alterado_ausente_na_releitura(self):
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)
        self.assertIn("status", resultado.detalhes["campos_ausentes"])

    def test_refutado_quando_campo_alterado_diverge(self):
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={"status": "pendente"},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)
        self.assertIn("status", resultado.detalhes["campos_divergentes"])

    def test_versao_prevalece_sobre_divergencia_de_campo(self):
        # Releitura desatualizada (versão antiga) não deve ser lida como
        # REFUTADO só porque um campo ainda tem o valor antigo -- a
        # checagem de versão vem primeiro.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={"status": "pendente"},
            versao_esperada=2,
            versao_releitura=1,
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)

    def test_valor_none_real_e_distinto_de_ausente(self):
        # Um campo pode legitimamente ter sido limpo para None -- isso deve
        # ser tratado como presente-e-correto, não como ausente.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"data_prevista": None},
            campos_preservados_esperados={},
            campos_releitura={"data_prevista": None},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.ACEITO)


class TestVerificarConsolidacaoAudio(unittest.TestCase):
    def test_pendente_quando_job_nao_concluiu(self):
        evidencia = EvidenciaConsolidacaoAudio(
            job_concluido=False,
            referencia_consolidacao=None,
            ids_solicitados=frozenset({"audio-1"}),
            ids_cobertos=frozenset(),
        )
        resultado = verificar_consolidacao_audio(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)

    def test_refutado_quando_concluido_sem_referencia(self):
        evidencia = EvidenciaConsolidacaoAudio(
            job_concluido=True,
            referencia_consolidacao=None,
            ids_solicitados=frozenset({"audio-1"}),
            ids_cobertos=frozenset({"audio-1"}),
        )
        resultado = verificar_consolidacao_audio(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)

    def test_pendente_quando_cobertura_parcial(self):
        evidencia = EvidenciaConsolidacaoAudio(
            job_concluido=True,
            referencia_consolidacao="consolidacao-42",
            ids_solicitados=frozenset({"audio-1", "audio-2"}),
            ids_cobertos=frozenset({"audio-1"}),
        )
        resultado = verificar_consolidacao_audio(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)
        self.assertEqual(resultado.detalhes["ids_faltantes"], ["audio-2"])

    def test_aceito_quando_cobertura_completa(self):
        evidencia = EvidenciaConsolidacaoAudio(
            job_concluido=True,
            referencia_consolidacao="consolidacao-42",
            ids_solicitados=frozenset({"audio-1", "audio-2"}),
            ids_cobertos=frozenset({"audio-1", "audio-2", "audio-3"}),
        )
        resultado = verificar_consolidacao_audio(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.ACEITO)

    def test_dez_reentregas_do_mesmo_evento_permanecem_aceito_idempotente(self):
        # F04, aceite: "dez reentregas do mesmo evento não criam dez
        # consolidações" -- este verificador não CRIA nada (não é
        # responsabilidade dele), mas deve devolver o mesmo ACEITO estável
        # para a mesma evidência repetida, nunca degradar o resultado.
        evidencia = EvidenciaConsolidacaoAudio(
            job_concluido=True,
            referencia_consolidacao="consolidacao-42",
            ids_solicitados=frozenset({"audio-1"}),
            ids_cobertos=frozenset({"audio-1"}),
        )
        resultados = {verificar_consolidacao_audio(evidencia).resultado for _ in range(10)}
        self.assertEqual(resultados, {ResultadoVerificacao.ACEITO})


class TestVerificarArtefatoBriefing(unittest.TestCase):
    def test_refutado_quando_nao_persistido(self):
        evidencia = EvidenciaArtefatoBriefing(
            artefato_persistido=False,
            referencia_artefato=None,
            secoes_exigidas=frozenset({"contexto"}),
            secoes_presentes=frozenset({"contexto"}),
        )
        resultado = verificar_artefato_briefing(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)

    def test_refutado_quando_persistido_mas_sem_referencia(self):
        evidencia = EvidenciaArtefatoBriefing(
            artefato_persistido=True,
            referencia_artefato="",
            secoes_exigidas=frozenset(),
            secoes_presentes=frozenset(),
        )
        resultado = verificar_artefato_briefing(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)

    def test_refutado_quando_secao_obrigatoria_ausente(self):
        evidencia = EvidenciaArtefatoBriefing(
            artefato_persistido=True,
            referencia_artefato="briefing-1",
            secoes_exigidas=frozenset({"contexto", "mudancas", "decisoes", "fontes"}),
            secoes_presentes=frozenset({"contexto", "mudancas"}),
        )
        resultado = verificar_artefato_briefing(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)
        self.assertEqual(
            sorted(resultado.detalhes["secoes_faltantes"]), ["decisoes", "fontes"]
        )

    def test_pendente_quando_fonte_citada_inacessivel(self):
        evidencia = EvidenciaArtefatoBriefing(
            artefato_persistido=True,
            referencia_artefato="briefing-1",
            secoes_exigidas=frozenset({"contexto"}),
            secoes_presentes=frozenset({"contexto"}),
            referencias_fontes=frozenset({"sipac://processo-1", "gmail://thread-1"}),
            referencias_acessiveis=frozenset({"sipac://processo-1"}),
        )
        resultado = verificar_artefato_briefing(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)
        self.assertEqual(resultado.detalhes["referencias_inacessiveis"], ["gmail://thread-1"])

    def test_aceito_quando_completo_e_todas_fontes_acessiveis(self):
        evidencia = EvidenciaArtefatoBriefing(
            artefato_persistido=True,
            referencia_artefato="briefing-1",
            secoes_exigidas=frozenset({"contexto", "decisoes"}),
            secoes_presentes=frozenset({"contexto", "decisoes", "extra"}),
            referencias_fontes=frozenset({"sipac://processo-1"}),
            referencias_acessiveis=frozenset({"sipac://processo-1"}),
        )
        resultado = verificar_artefato_briefing(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.ACEITO)

    def test_aceito_sem_nenhuma_fonte_citada(self):
        evidencia = EvidenciaArtefatoBriefing(
            artefato_persistido=True,
            referencia_artefato="briefing-1",
            secoes_exigidas=frozenset({"contexto"}),
            secoes_presentes=frozenset({"contexto"}),
        )
        resultado = verificar_artefato_briefing(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.ACEITO)


class TestVerificarEnvioWhatsApp(unittest.TestCase):
    def test_pendente_sem_recibo_do_worker(self):
        # Achado A03: aprovação/pending não comprovam envio.
        evidencia = EvidenciaEnvioWhatsApp(
            recibo_do_worker=False,
            destino_esperado="+5511900000000",
            destino_confirmado=None,
            provider_message_id=None,
        )
        resultado = verificar_envio_whatsapp(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)

    def test_refutado_quando_destino_diverge(self):
        evidencia = EvidenciaEnvioWhatsApp(
            recibo_do_worker=True,
            destino_esperado="+5511900000000",
            destino_confirmado="+5511911111111",
            provider_message_id="wamid.abc",
        )
        resultado = verificar_envio_whatsapp(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)

    def test_refutado_quando_destino_confirmado_ausente(self):
        evidencia = EvidenciaEnvioWhatsApp(
            recibo_do_worker=True,
            destino_esperado="+5511900000000",
            destino_confirmado=None,
            provider_message_id="wamid.abc",
        )
        resultado = verificar_envio_whatsapp(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)

    def test_pendente_quando_sem_provider_message_id(self):
        evidencia = EvidenciaEnvioWhatsApp(
            recibo_do_worker=True,
            destino_esperado="+5511900000000",
            destino_confirmado="+5511900000000",
            provider_message_id=None,
        )
        resultado = verificar_envio_whatsapp(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)

    def test_aceito_quando_recibo_destino_e_id_presentes(self):
        evidencia = EvidenciaEnvioWhatsApp(
            recibo_do_worker=True,
            destino_esperado="+5511900000000",
            destino_confirmado="+5511900000000",
            provider_message_id="wamid.abc",
        )
        resultado = verificar_envio_whatsapp(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.ACEITO)


class TestVerificacaoResultadoAceito(unittest.TestCase):
    def test_metodo_aceito_reflete_o_enum(self):
        evidencia = EvidenciaEnvioWhatsApp(
            recibo_do_worker=True,
            destino_esperado="+5511900000000",
            destino_confirmado="+5511900000000",
            provider_message_id="wamid.abc",
        )
        resultado = verificar_envio_whatsapp(evidencia)
        self.assertTrue(resultado.aceito())

        evidencia_pendente = EvidenciaEnvioWhatsApp(
            recibo_do_worker=False,
            destino_esperado="+5511900000000",
            destino_confirmado=None,
            provider_message_id=None,
        )
        self.assertFalse(verificar_envio_whatsapp(evidencia_pendente).aceito())


if __name__ == "__main__":
    unittest.main()
