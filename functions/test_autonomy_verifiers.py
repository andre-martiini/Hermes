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

    def test_pendente_quando_versao_declarada_so_de_um_lado(self):
        # Achado de revisao adversarial (Codex, PR #353, P1): versao
        # esperada declarada mas releitura nao trouxe nenhuma -- evidencia
        # de versao incompleta, nao pode virar ACEITO so porque os campos
        # (por acaso) conferem.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={"status": "feito"},
            versao_esperada=2,
            versao_releitura=None,
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)

    def test_aceito_quando_versao_da_releitura_e_maior_e_campos_corretos(self):
        # Versao MAIOR que a esperada (avanco concorrente) nao e
        # curto-circuitada -- com os campos corretos, ainda chega a ACEITO.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={"status": "feito"},
            versao_esperada=2,
            versao_releitura=5,
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.ACEITO)

    def test_versao_zero_e_zero_nao_e_tratada_como_ausente(self):
        # 0 e falsy em Python, mas as checagens usam `is None`, nao
        # truthiness -- versao_esperada=0 e versao_releitura=0 devem ser
        # tratadas como "as duas presentes e iguais", nao como ausencia.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={"status": "feito"},
            versao_esperada=0,
            versao_releitura=0,
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.ACEITO)

    def test_pendente_quando_versao_maior_mas_campo_alterado_ausente(self):
        # Versao MAIOR que a esperada nao contradiz nada por si só -- um
        # campo alterado simplesmente AUSENTE da releitura (nao contradito,
        # so sem evidencia) ainda deve cair em PENDENTE por ausencia, nunca
        # ACEITO nem REFUTADO.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={},
            versao_esperada=2,
            versao_releitura=5,
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)
        self.assertIn("status", resultado.detalhes["campos_alterados_ausentes"])

    def test_refutado_quando_versao_da_releitura_e_maior_mas_campo_contradiz(self):
        # Achado de revisao adversarial (Codex, PR #353, P2): sob versao
        # monotonica, uma releitura MAIS NOVA que a esperada nao e um
        # snapshot velho -- se ela tambem contradiz um campo esperado, isso
        # e uma refutacao real (sobrescrita por outra operacao), nao deve
        # ficar escondida atras de "versao nao confere" -> PENDENTE.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={"status": "outra-coisa"},
            versao_esperada=2,
            versao_releitura=5,
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)

    def test_refutado_quando_campo_preservado_mudou(self):
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={"titulo": "Preparar reunião"},
            campos_releitura={"status": "feito", "titulo": "TÍTULO ALTERADO SEM QUERER"},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)
        self.assertIn("titulo", resultado.detalhes["campos_preservados_violados"])

    def test_pendente_quando_campo_preservado_ausente_na_releitura(self):
        # Campo ausente é "ainda não sabemos", não "não mudou" -- não pode
        # produzir REFUTADO por si só (não há evidência de violação), mas
        # também não pode virar ACEITO por omissão: não há NENHUMA
        # evidência de que este campo sobreviveu à escrita.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={"titulo": "Preparar reunião"},
            campos_releitura={"status": "feito"},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)
        self.assertIn("titulo", resultado.detalhes["campos_preservados_ausentes"])

    def test_refutado_tem_prioridade_sobre_pendente_quando_ambos_ocorrem(self):
        # Um campo preservado violado (evidência definitiva de efeito
        # colateral) e, ao mesmo tempo, um campo alterado ausente (mera
        # lacuna) -- o erro comprovado não deve ficar escondido atrás de
        # "falta dado" só porque outra parte da releitura também está
        # incompleta.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={"titulo": "Preparar reunião"},
            campos_releitura={"titulo": "TÍTULO ALTERADO SEM QUERER"},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)
        self.assertIn("titulo", resultado.detalhes["campos_preservados_violados"])

    def test_refutado_reporta_preservado_violado_e_alterado_divergente_juntos(self):
        # Um campo preservado violado E um campo alterado divergente ao
        # mesmo tempo (nenhum dos dois ausente) -- ambos devem aparecer no
        # mesmo resultado REFUTADO, não só o primeiro encontrado.
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={"titulo": "Preparar reunião"},
            campos_releitura={"status": "pendente", "titulo": "TÍTULO ALTERADO SEM QUERER"},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)
        self.assertIn("titulo", resultado.detalhes["campos_preservados_violados"])
        self.assertIn("status", resultado.detalhes["campos_divergentes"])

    def test_pendente_quando_campo_alterado_ausente_na_releitura(self):
        evidencia = EvidenciaAtualizacaoTarefa(
            campos_alterados_esperados={"status": "feito"},
            campos_preservados_esperados={},
            campos_releitura={},
        )
        resultado = verificar_atualizacao_tarefa(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)
        self.assertIn("status", resultado.detalhes["campos_alterados_ausentes"])

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

    def test_refutado_quando_referencia_e_so_espaco_em_branco(self):
        # "   " é truthy em Python (`not "   "` é False) -- não pode
        # passar como referência válida só por não ser uma string vazia.
        evidencia = EvidenciaConsolidacaoAudio(
            job_concluido=True,
            referencia_consolidacao="   ",
            ids_solicitados=frozenset({"audio-1"}),
            ids_cobertos=frozenset({"audio-1"}),
        )
        resultado = verificar_consolidacao_audio(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)

    def test_refutado_quando_cobertura_parcial_com_job_concluido(self):
        # Achado de revisao adversarial (Codex, PR #353): o produtor real
        # (whatsapp_consolidation.py) so grava status="completed" DEPOIS de
        # marcar toda cobertura -- um job concluido com IDs faltantes nunca
        # vai ganhar cobertura nova depois. PENDENTE faria um pedido esperar
        # para sempre; o desfecho certo e REFUTADO (definitivamente
        # incompleto), nao uma lacuna temporaria.
        evidencia = EvidenciaConsolidacaoAudio(
            job_concluido=True,
            referencia_consolidacao="consolidacao-42",
            ids_solicitados=frozenset({"audio-1", "audio-2"}),
            ids_cobertos=frozenset({"audio-1"}),
        )
        resultado = verificar_consolidacao_audio(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.REFUTADO)
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

    def test_refutado_quando_referencia_e_so_espaco_em_branco(self):
        evidencia = EvidenciaArtefatoBriefing(
            artefato_persistido=True,
            referencia_artefato="   ",
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

    def test_pendente_quando_destino_confirmado_ausente(self):
        # Diferente de destino DIVERGENTE (erro real, REFUTADO): aqui não
        # há NENHUM dado de destino ainda -- um recibo mais completo pode
        # chegar depois e preencher isso, então é PENDENTE, não REFUTADO.
        evidencia = EvidenciaEnvioWhatsApp(
            recibo_do_worker=True,
            destino_esperado="+5511900000000",
            destino_confirmado=None,
            provider_message_id="wamid.abc",
        )
        resultado = verificar_envio_whatsapp(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)

    def test_pendente_quando_destino_confirmado_e_so_espaco_em_branco(self):
        evidencia = EvidenciaEnvioWhatsApp(
            recibo_do_worker=True,
            destino_esperado="+5511900000000",
            destino_confirmado="   ",
            provider_message_id="wamid.abc",
        )
        resultado = verificar_envio_whatsapp(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)

    def test_pendente_quando_provider_message_id_e_so_espaco_em_branco(self):
        evidencia = EvidenciaEnvioWhatsApp(
            recibo_do_worker=True,
            destino_esperado="+5511900000000",
            destino_confirmado="+5511900000000",
            provider_message_id="   ",
        )
        resultado = verificar_envio_whatsapp(evidencia)
        self.assertEqual(resultado.resultado, ResultadoVerificacao.PENDENTE)

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
