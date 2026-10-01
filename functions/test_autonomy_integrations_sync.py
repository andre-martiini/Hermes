"""Testes de `autonomy/integrations_sync.py` — leitores puros dos docs de
sync já existentes hoje (P05, continuação do passo 8: "Substituir zeros de
fallback por status de fonte...", achado A09). Sem I/O: todo doc é um dict
fabricado no teste, nunca uma leitura real do Firestore.

Cobre: `_extrair_instante` (datetime nativo tz-aware/naive, string ISO com/
sem "Z", string ISO naive, valores inválidos), os 4 leitores por integração
(`saude_calendar`, `saude_contacts`, `saude_gmail`, `saude_whatsapp`) nos
casos doc ausente/vazio, saudável, degradado, indisponível por frescor e
indisponível por erro explícito, `saude_sem_sincronizacao_persistida`, a
tabela `LIMITES_POR_INTEGRACAO` (sanidade: degradado < indisponível para
todas as 4 integrações mapeadas), e a preferência de `saude_calendar` pelo
heartbeat próprio `last_calendar_success_at` sobre o `last_success`
compartilhado com `sync_gmail_bills_callable` (fallback só durante a
transição para um doc ainda sem o campo novo)."""

import unittest
from datetime import datetime, timedelta, timezone

from autonomy.integrations import IntegrationStatus
from autonomy.integrations_sync import (
    ERRO_SEM_MENSAGEM,
    LIMITES_POR_INTEGRACAO,
    TOLERANCIA_RELOGIO_SEGUNDOS,
    _extrair_instante,
    _sem_referencia_futura,
    saude_calendar,
    saude_contacts,
    saude_gmail,
    saude_sem_sincronizacao_persistida,
    saude_whatsapp,
)

_AGORA = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)


class TestExtrairInstante(unittest.TestCase):
    def test_datetime_tz_aware_passa_direto(self):
        valor = _AGORA - timedelta(minutes=5)
        self.assertEqual(_extrair_instante(valor), valor)

    def test_datetime_naive_assume_utc(self):
        naive = datetime(2026, 9, 28, 11, 55, 0)
        resultado = _extrair_instante(naive)
        self.assertEqual(resultado, naive.replace(tzinfo=timezone.utc))

    def test_string_iso_com_offset(self):
        resultado = _extrair_instante("2026-09-28T11:55:00+00:00")
        self.assertEqual(resultado, _AGORA - timedelta(minutes=5))

    def test_string_iso_com_sufixo_z(self):
        resultado = _extrair_instante("2026-09-28T11:55:00Z")
        self.assertEqual(resultado, _AGORA - timedelta(minutes=5))

    def test_string_iso_naive_assume_utc(self):
        resultado = _extrair_instante("2026-09-28T11:55:00")
        self.assertEqual(resultado, _AGORA - timedelta(minutes=5))

    def test_string_vazia_devolve_none(self):
        self.assertIsNone(_extrair_instante(""))
        self.assertIsNone(_extrair_instante("   "))

    def test_string_ilegivel_devolve_none(self):
        self.assertIsNone(_extrair_instante("não é uma data"))

    def test_none_devolve_none(self):
        self.assertIsNone(_extrair_instante(None))

    def test_tipo_inesperado_devolve_none(self):
        self.assertIsNone(_extrair_instante(12345))
        self.assertIsNone(_extrair_instante(["2026-09-28T11:55:00Z"]))


class TestSemReferenciaFutura(unittest.TestCase):
    def test_referencia_passada_passa_direto(self):
        referencia = _AGORA - timedelta(minutes=5)
        self.assertEqual(_sem_referencia_futura(referencia, _AGORA), referencia)

    def test_referencia_igual_ao_heartbeat_passa_direto(self):
        self.assertEqual(_sem_referencia_futura(_AGORA, _AGORA), _AGORA)

    def test_referencia_futura_dentro_da_tolerancia_e_cortada_no_heartbeat(self):
        futura = _AGORA + timedelta(seconds=30)
        self.assertEqual(_sem_referencia_futura(futura, _AGORA), _AGORA)

    def test_referencia_futura_exatamente_no_limite_da_tolerancia_e_cortada(self):
        futura = _AGORA + timedelta(seconds=TOLERANCIA_RELOGIO_SEGUNDOS)
        self.assertEqual(_sem_referencia_futura(futura, _AGORA), _AGORA)

    def test_referencia_futura_alem_da_tolerancia_e_descartada(self):
        # Achado real da 2ª rodada de revisão adversarial: cortar SEM limite
        # mascararia um timestamp corrompido (ex.: anos no futuro) como
        # "acabou de sincronizar" -- acima da tolerância a referência vira
        # None (o leitor cai para UNKNOWN), não um clamp.
        futura = _AGORA + timedelta(seconds=TOLERANCIA_RELOGIO_SEGUNDOS + 1)
        self.assertIsNone(_sem_referencia_futura(futura, _AGORA))

    def test_referencia_anos_no_futuro_e_descartada(self):
        futura = _AGORA.replace(year=_AGORA.year + 5)
        self.assertIsNone(_sem_referencia_futura(futura, _AGORA))

    def test_none_passa_direto(self):
        self.assertIsNone(_sem_referencia_futura(None, _AGORA))


class TestSaudeCalendar(unittest.TestCase):
    def test_doc_none_e_unknown(self):
        saude = saude_calendar(None, _AGORA)
        self.assertEqual(saude.integration, "calendar")
        self.assertEqual(saude.status, IntegrationStatus.UNKNOWN)
        self.assertIsNone(saude.last_success_at)
        self.assertIsNone(saude.error_code)

    def test_doc_vazio_e_unknown(self):
        self.assertEqual(saude_calendar({}, _AGORA).status, IntegrationStatus.UNKNOWN)

    def test_sync_recente_e_healthy(self):
        doc = {"status": "completed", "last_success": (_AGORA - timedelta(minutes=10)).isoformat()}
        saude = saude_calendar(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 600.0)

    def test_sync_last_success_naive_tratado_como_utc(self):
        # system/sync.last_success é gravado com datetime.now().isoformat(), sem
        # timezone.utc -- ao contrário de finished_at/started_at do mesmo doc.
        naive_iso = (_AGORA - timedelta(minutes=10)).replace(tzinfo=None).isoformat()
        doc = {"status": "completed", "last_success": naive_iso}
        saude = saude_calendar(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 600.0)

    def test_sync_parado_ha_3_horas_e_degraded(self):
        doc = {"status": "completed", "last_success": (_AGORA - timedelta(hours=3)).isoformat()}
        self.assertEqual(saude_calendar(doc, _AGORA).status, IntegrationStatus.DEGRADED)

    def test_sync_parado_ha_7_horas_e_unavailable_por_frescor(self):
        doc = {"status": "completed", "last_success": (_AGORA - timedelta(hours=7)).isoformat()}
        saude = saude_calendar(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNAVAILABLE)
        self.assertIsNone(saude.error_code)

    def test_status_error_com_mensagem_vira_unavailable_por_erro(self):
        doc = {
            "status": "error",
            "last_success": (_AGORA - timedelta(minutes=5)).isoformat(),
            "error_message": "Falha ao chamar a API do Calendar",
        }
        saude = saude_calendar(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNAVAILABLE)
        self.assertEqual(saude.error_code, "Falha ao chamar a API do Calendar")

    def test_status_error_sem_mensagem_usa_fallback(self):
        doc = {"status": "error", "last_success": (_AGORA - timedelta(minutes=5)).isoformat()}
        saude = saude_calendar(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNAVAILABLE)
        self.assertEqual(saude.error_code, ERRO_SEM_MENSAGEM)

    def test_status_error_com_mensagem_em_branco_usa_fallback(self):
        doc = {"status": "error", "error_message": "   "}
        self.assertEqual(saude_calendar(doc, _AGORA).error_code, ERRO_SEM_MENSAGEM)

    def test_status_processing_sem_error_code_usa_so_frescor(self):
        doc = {"status": "processing", "last_success": (_AGORA - timedelta(minutes=1)).isoformat()}
        saude = saude_calendar(doc, _AGORA)
        self.assertIsNone(saude.error_code)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)

    def test_finished_at_nao_e_usado_como_referencia(self):
        # finished_at também é gravado em status == "error" -- não deve ser
        # usado no lugar de last_success (ver docstring de saude_calendar).
        doc = {
            "status": "completed",
            "finished_at": _AGORA.isoformat(),
            "last_success": (_AGORA - timedelta(hours=7)).isoformat(),
        }
        self.assertEqual(saude_calendar(doc, _AGORA).status, IntegrationStatus.UNAVAILABLE)

    def test_last_success_ligeiramente_no_futuro_nao_levanta_e_vira_healthy(self):
        # Achado real de revisão adversarial independente (P05 sub-entrega
        # 3/N): heartbeat_at é normalmente capturado pelo chamador ANTES de
        # buscar o doc no Firestore -- um sync que termina no meio dessa
        # janela (ou desvio de relógio) produz last_success > heartbeat_at, o
        # que sem o clamp de _sem_referencia_futura levantaria ValueError em
        # vez de devolver um IntegrationHealth.
        doc = {"status": "completed", "last_success": (_AGORA + timedelta(seconds=5)).isoformat()}
        saude = saude_calendar(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 0.0)

    def test_last_success_muito_no_futuro_nao_levanta_e_vira_unknown(self):
        # Além da tolerância de relógio -- não é mascarado como HEALTHY.
        doc = {
            "status": "completed",
            "last_success": (_AGORA + timedelta(seconds=TOLERANCIA_RELOGIO_SEGUNDOS + 1)).isoformat(),
        }
        saude = saude_calendar(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNKNOWN)
        self.assertIsNone(saude.lag_seconds)

    def test_lag_exatamente_no_limite_degradado_ainda_e_healthy(self):
        limite_degradado, _ = LIMITES_POR_INTEGRACAO["calendar"]
        doc = {"status": "completed", "last_success": (_AGORA - timedelta(seconds=limite_degradado)).isoformat()}
        self.assertEqual(saude_calendar(doc, _AGORA).status, IntegrationStatus.HEALTHY)

    def test_lag_um_segundo_acima_do_limite_degradado_ja_e_degraded(self):
        limite_degradado, _ = LIMITES_POR_INTEGRACAO["calendar"]
        doc = {
            "status": "completed",
            "last_success": (_AGORA - timedelta(seconds=limite_degradado + 1)).isoformat(),
        }
        self.assertEqual(saude_calendar(doc, _AGORA).status, IntegrationStatus.DEGRADED)

    def test_lag_exatamente_no_limite_indisponivel_ainda_e_degraded(self):
        _, limite_indisponivel = LIMITES_POR_INTEGRACAO["calendar"]
        doc = {"status": "completed", "last_success": (_AGORA - timedelta(seconds=limite_indisponivel)).isoformat()}
        self.assertEqual(saude_calendar(doc, _AGORA).status, IntegrationStatus.DEGRADED)

    def test_lag_um_segundo_acima_do_limite_indisponivel_ja_e_unavailable(self):
        _, limite_indisponivel = LIMITES_POR_INTEGRACAO["calendar"]
        doc = {
            "status": "completed",
            "last_success": (_AGORA - timedelta(seconds=limite_indisponivel + 1)).isoformat(),
        }
        self.assertEqual(saude_calendar(doc, _AGORA).status, IntegrationStatus.UNAVAILABLE)

    def test_prefere_last_calendar_success_at_quando_presente(self):
        # Campo novo, escrito por run_full_sync logo após o passo Calendar/Tasks
        # (ver main.py) -- é a referência de frescor preferida.
        doc = {
            "status": "completed",
            "last_calendar_success_at": (_AGORA - timedelta(minutes=10)).isoformat(),
            "last_success": (_AGORA - timedelta(hours=7)).isoformat(),
        }
        saude = saude_calendar(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 600.0)

    def test_refresh_de_last_success_por_boletos_do_gmail_nao_mascara_calendar_parado(self):
        # Achado real do Codex (comment_id=4131386963): sync_gmail_bills_callable
        # também grava last_success em system/sync, sem nenhuma sincronização de
        # Calendar envolvida -- com last_calendar_success_at presente e antigo,
        # esse refresh alheio não deve mais mascarar um Calendar genuinamente
        # parado como saudável.
        doc = {
            "status": "completed",
            "last_calendar_success_at": (_AGORA - timedelta(hours=7)).isoformat(),
            "last_success": (_AGORA - timedelta(minutes=1)).isoformat(),  # refresh de boletos, não de Calendar
        }
        saude = saude_calendar(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNAVAILABLE)

    def test_doc_legado_sem_last_calendar_success_at_cai_para_last_success(self):
        # Período de transição entre o deploy desta sub-entrega e a primeira
        # rodada de sync seguinte -- doc antigo, ainda sem o campo novo.
        doc = {"status": "completed", "last_success": (_AGORA - timedelta(minutes=10)).isoformat()}
        saude = saude_calendar(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 600.0)


class TestSaudeContacts(unittest.TestCase):
    def test_doc_none_e_unknown(self):
        self.assertEqual(saude_contacts(None, _AGORA).status, IntegrationStatus.UNKNOWN)

    def test_execucao_recente_e_healthy(self):
        doc = {"ultima_execucao": (_AGORA - timedelta(hours=1)).isoformat()}
        self.assertEqual(saude_contacts(doc, _AGORA).status, IntegrationStatus.HEALTHY)

    def test_execucao_a_5h59_ainda_e_healthy_dado_o_intervalo_minimo_de_6h(self):
        # _contatos_devem_rodar só deixa rodar de novo depois de 6h -- 5h59 de
        # idade é normal, não degradação.
        doc = {"ultima_execucao": (_AGORA - timedelta(hours=5, minutes=59)).isoformat()}
        self.assertEqual(saude_contacts(doc, _AGORA).status, IntegrationStatus.HEALTHY)

    def test_execucao_ha_20_horas_e_degraded(self):
        doc = {"ultima_execucao": (_AGORA - timedelta(hours=20)).isoformat()}
        self.assertEqual(saude_contacts(doc, _AGORA).status, IntegrationStatus.DEGRADED)

    def test_execucao_ha_49_horas_e_unavailable(self):
        doc = {"ultima_execucao": (_AGORA - timedelta(hours=49)).isoformat()}
        self.assertEqual(saude_contacts(doc, _AGORA).status, IntegrationStatus.UNAVAILABLE)

    def test_error_code_e_sempre_none(self):
        doc = {"ultima_execucao": (_AGORA - timedelta(hours=49)).isoformat(), "status": "error"}
        # sync_contatos não tem campo de status/erro -- uma chave "status"
        # estranha no dict não deve ser interpretada como erro.
        self.assertIsNone(saude_contacts(doc, _AGORA).error_code)

    def test_lag_exatamente_no_limite_degradado_ainda_e_healthy(self):
        limite_degradado, _ = LIMITES_POR_INTEGRACAO["contacts"]
        doc = {"ultima_execucao": (_AGORA - timedelta(seconds=limite_degradado)).isoformat()}
        self.assertEqual(saude_contacts(doc, _AGORA).status, IntegrationStatus.HEALTHY)

    def test_lag_exatamente_no_limite_indisponivel_ainda_e_degraded(self):
        _, limite_indisponivel = LIMITES_POR_INTEGRACAO["contacts"]
        doc = {"ultima_execucao": (_AGORA - timedelta(seconds=limite_indisponivel)).isoformat()}
        self.assertEqual(saude_contacts(doc, _AGORA).status, IntegrationStatus.DEGRADED)

    def test_ultima_execucao_ligeiramente_no_futuro_nao_levanta_e_vira_healthy(self):
        doc = {"ultima_execucao": (_AGORA + timedelta(seconds=5)).isoformat()}
        saude = saude_contacts(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 0.0)

    def test_ultima_execucao_muito_no_futuro_nao_levanta_e_vira_unknown(self):
        doc = {"ultima_execucao": (_AGORA + timedelta(seconds=TOLERANCIA_RELOGIO_SEGUNDOS + 1)).isoformat()}
        saude = saude_contacts(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNKNOWN)
        self.assertIsNone(saude.lag_seconds)


class TestSaudeGmail(unittest.TestCase):
    def test_doc_none_e_unknown(self):
        self.assertEqual(saude_gmail(None, _AGORA).status, IntegrationStatus.UNKNOWN)

    def test_completed_recente_e_healthy(self):
        doc = {"status": "completed", "last_success": (_AGORA - timedelta(minutes=30)).isoformat()}
        self.assertEqual(saude_gmail(doc, _AGORA).status, IntegrationStatus.HEALTHY)

    def test_status_error_vira_unavailable_por_erro(self):
        doc = {"status": "error", "error_message": "GoogleAuthRevokedError"}
        saude = saude_gmail(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNAVAILABLE)
        self.assertEqual(saude.error_code, "GoogleAuthRevokedError")

    def test_status_partial_nao_vira_error_code(self):
        # "partial" não conta como sucesso (last_success não avança), mas
        # também não é um error_code -- a frescor sozinha decide o status.
        doc = {
            "status": "partial",
            "etapas_com_erro": ["sync_pix_emails"],
            "last_success": (_AGORA - timedelta(minutes=10)).isoformat(),
        }
        saude = saude_gmail(doc, _AGORA)
        self.assertIsNone(saude.error_code)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)

    def test_partial_com_last_success_antigo_degrada_pela_frescor(self):
        doc = {
            "status": "partial",
            "etapas_com_erro": ["sync_pix_emails"],
            "last_success": (_AGORA - timedelta(hours=6)).isoformat(),
        }
        saude = saude_gmail(doc, _AGORA)
        self.assertIsNone(saude.error_code)
        self.assertEqual(saude.status, IntegrationStatus.DEGRADED)

    def test_last_success_ja_e_tz_aware_no_doc_real(self):
        # ao contrário de system/sync, system/gmail_sync.last_success já é
        # gravado com datetime.now(timezone.utc).isoformat().
        doc = {"status": "completed", "last_success": _AGORA.isoformat()}
        saude = saude_gmail(doc, _AGORA)
        self.assertEqual(saude.lag_seconds, 0.0)

    def test_status_error_sem_mensagem_usa_fallback(self):
        doc = {"status": "error"}
        self.assertEqual(saude_gmail(doc, _AGORA).error_code, ERRO_SEM_MENSAGEM)

    def test_status_error_com_mensagem_em_branco_usa_fallback(self):
        doc = {"status": "error", "error_message": "   "}
        self.assertEqual(saude_gmail(doc, _AGORA).error_code, ERRO_SEM_MENSAGEM)

    def test_lag_exatamente_no_limite_degradado_ainda_e_healthy(self):
        limite_degradado, _ = LIMITES_POR_INTEGRACAO["gmail"]
        doc = {"status": "completed", "last_success": (_AGORA - timedelta(seconds=limite_degradado)).isoformat()}
        self.assertEqual(saude_gmail(doc, _AGORA).status, IntegrationStatus.HEALTHY)

    def test_lag_exatamente_no_limite_indisponivel_ainda_e_degraded(self):
        _, limite_indisponivel = LIMITES_POR_INTEGRACAO["gmail"]
        doc = {"status": "completed", "last_success": (_AGORA - timedelta(seconds=limite_indisponivel)).isoformat()}
        self.assertEqual(saude_gmail(doc, _AGORA).status, IntegrationStatus.DEGRADED)

    def test_last_success_ligeiramente_no_futuro_nao_levanta_e_vira_healthy(self):
        doc = {"status": "completed", "last_success": (_AGORA + timedelta(seconds=5)).isoformat()}
        saude = saude_gmail(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 0.0)

    def test_last_success_muito_no_futuro_nao_levanta_e_vira_unknown(self):
        doc = {
            "status": "completed",
            "last_success": (_AGORA + timedelta(seconds=TOLERANCIA_RELOGIO_SEGUNDOS + 1)).isoformat(),
        }
        saude = saude_gmail(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNKNOWN)
        self.assertIsNone(saude.lag_seconds)


class TestSaudeWhatsapp(unittest.TestCase):
    def test_doc_none_e_unknown(self):
        self.assertEqual(saude_whatsapp(None, _AGORA).status, IntegrationStatus.UNKNOWN)

    def test_cursor_como_datetime_nativo_tz_aware(self):
        doc = {"last_processed_at": _AGORA - timedelta(minutes=15)}
        saude = saude_whatsapp(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 900.0)

    def test_cursor_como_datetime_naive_assume_utc(self):
        doc = {"last_processed_at": (_AGORA - timedelta(minutes=15)).replace(tzinfo=None)}
        saude = saude_whatsapp(doc, _AGORA)
        self.assertEqual(saude.lag_seconds, 900.0)

    def test_cursor_antigo_e_unavailable(self):
        doc = {"last_processed_at": _AGORA - timedelta(hours=8)}
        self.assertEqual(saude_whatsapp(doc, _AGORA).status, IntegrationStatus.UNAVAILABLE)

    def test_error_code_e_sempre_none(self):
        # system/whatsapp_ingest não tem campo de status/erro -- uma chave
        # "status" estranha no dict não deve ser interpretada como erro
        # (mesmo teste de TestSaudeContacts.test_error_code_e_sempre_none,
        # reforçado por revisão adversarial independente: a versão anterior
        # deste teste não injetava nenhuma chave além de last_processed_at,
        # então não conseguia detectar essa classe de bug).
        doc = {"last_processed_at": _AGORA - timedelta(hours=8), "status": "error", "error_message": "boom"}
        self.assertIsNone(saude_whatsapp(doc, _AGORA).error_code)

    def test_cursor_ligeiramente_no_futuro_nao_levanta_e_vira_healthy(self):
        doc = {"last_processed_at": _AGORA + timedelta(seconds=5)}
        saude = saude_whatsapp(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 0.0)

    def test_cursor_muito_no_futuro_nao_levanta_e_vira_unknown(self):
        doc = {"last_processed_at": _AGORA + timedelta(seconds=TOLERANCIA_RELOGIO_SEGUNDOS + 1)}
        saude = saude_whatsapp(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNKNOWN)
        self.assertIsNone(saude.lag_seconds)

    def test_lag_exatamente_no_limite_degradado_ainda_e_healthy(self):
        limite_degradado, _ = LIMITES_POR_INTEGRACAO["whatsapp"]
        doc = {"last_processed_at": _AGORA - timedelta(seconds=limite_degradado)}
        self.assertEqual(saude_whatsapp(doc, _AGORA).status, IntegrationStatus.HEALTHY)

    def test_lag_exatamente_no_limite_indisponivel_ainda_e_degraded(self):
        _, limite_indisponivel = LIMITES_POR_INTEGRACAO["whatsapp"]
        doc = {"last_processed_at": _AGORA - timedelta(seconds=limite_indisponivel)}
        self.assertEqual(saude_whatsapp(doc, _AGORA).status, IntegrationStatus.DEGRADED)

    def test_query_success_recente_e_healthy_mesmo_com_cursor_de_dados_antigo(self):
        # Cenário central da correção: conta legitimamente ociosa (ninguém manda
        # mensagem nova há dias -- cursor de dados bem além do limite indisponível),
        # mas a consulta do polling horário continua tendo êxito
        # (`last_query_success_at` recente) -- antes desta sub-entrega, isso era
        # reportado como UNAVAILABLE.
        doc = {
            "last_processed_at": _AGORA - timedelta(days=3),
            "last_query_success_at": _AGORA - timedelta(minutes=10),
        }
        saude = saude_whatsapp(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 600.0)

    def test_query_success_ausente_cai_para_cursor_de_dados_legado(self):
        # Doc gravado antes desta sub-entrega (sem last_query_success_at ainda) --
        # migração automática, mesmo espírito do cursor composto de _messages_query.
        doc = {"last_processed_at": _AGORA - timedelta(minutes=5)}
        saude = saude_whatsapp(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 300.0)

    def test_query_success_antigo_sem_cursor_de_dados_e_unavailable(self):
        doc = {"last_query_success_at": _AGORA - timedelta(hours=8)}
        self.assertEqual(saude_whatsapp(doc, _AGORA).status, IntegrationStatus.UNAVAILABLE)

    def test_query_success_muito_no_futuro_nao_levanta_e_vira_unknown(self):
        doc = {"last_query_success_at": _AGORA + timedelta(seconds=TOLERANCIA_RELOGIO_SEGUNDOS + 1)}
        saude = saude_whatsapp(doc, _AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNKNOWN)
        self.assertIsNone(saude.lag_seconds)


class TestSaudeSemSincronizacaoPersistida(unittest.TestCase):
    def test_sipac_e_sempre_unknown(self):
        saude = saude_sem_sincronizacao_persistida("sipac", _AGORA)
        self.assertEqual(saude.integration, "sipac")
        self.assertEqual(saude.status, IntegrationStatus.UNKNOWN)
        self.assertIsNone(saude.error_code)
        self.assertIsNone(saude.last_success_at)

    def test_financas_e_repositorio_tambem(self):
        for nome in ("financas", "repositorio"):
            with self.subTest(integration=nome):
                self.assertEqual(
                    saude_sem_sincronizacao_persistida(nome, _AGORA).status,
                    IntegrationStatus.UNKNOWN,
                )


class TestLimitesPorIntegracao(unittest.TestCase):
    def test_quatro_integracoes_mapeadas(self):
        self.assertEqual(set(LIMITES_POR_INTEGRACAO), {"calendar", "contacts", "gmail", "whatsapp"})

    def test_degradado_menor_que_indisponivel_em_todas(self):
        for integracao, (degradado, indisponivel) in LIMITES_POR_INTEGRACAO.items():
            with self.subTest(integration=integracao):
                self.assertGreater(degradado, 0)
                self.assertLess(degradado, indisponivel)


if __name__ == "__main__":
    unittest.main()
