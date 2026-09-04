"""Testes de regressão dos detectores proativos da fila de atenção.

Garante que os 3 cenários críticos de proatividade (áudio relevante vinculado a
ação crítica, promessa sem retorno há 5h e etapa aguardando terceiro vencida)
liguem o gatilho real de cada detector ao desfecho observável (interrupção
disparada ou presença correta na fila normal sem interrupção indevida).

Reutiliza MockDb/MockDoc/MockQuery de test_atencao.py sem duplicar fixtures.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import unittest
from unittest.mock import patch

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

_TZ_SP = zoneinfo.ZoneInfo("America/Sao_Paulo")

from atencao import (
    COLLECTION,
    ESTADO_ABERTO,
    PRIORIDADE_ALTA,
    PRIORIDADE_MEDIA,
    TIPO_AGUARDANDO_TERCEIRO_VENCIDO,
    avaliar_etapas,
    avaliar_interrupcao_atencao,
    coletar_fila_atencao,
)
from atencao_whatsapp import (
    ESTADO_PROMESSA_ABERTA,
    TIPO_AUDIO_RELEVANTE,
    TIPO_PROMESSA_SEM_RETORNO,
    avaliar_audio,
    avaliar_promessas_vencidas,
)
from test_atencao import MockDb


class TestRegressaoProatividade(unittest.TestCase):
    """Cenários de regressão ligando o gatilho real ao desfecho observável."""

    @patch("atencao._reserve_and_create_notification")
    def test_cenario_audio_relevante_contato_vinculado_dispara_interrupcao(self, mock_reserve):
        """Cenário 1: Áudio de contato vinculado a ação crítica gera item de prioridade alta

        e o sweep de interrupção dispara notificação para o Telegram.
        """
        mock_reserve.return_value = True

        agora = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)
        mensagem = {
            "from_me": False,
            "message_type": "ptt",
            "chat_id": "5511999999999@s.whatsapp.net",
            "chat_name": "Cliente Estratégico",
            "wa_message_id": "wa-audio-001",
            "author_name": "Carlos Diretor",
            "timestamp": agora,
            "media": {"duration_seconds": 45},
        }
        contexto = {
            "chat_vinculado": True,
            "acao": {
                "id": "acao-critica-1",
                "titulo": "Auditoria de Compliance",
                "degradation_count": 3,
            },
        }

        # 1. Detector puro avalia áudio e decide relevância + prioridade
        item_audio = avaliar_audio(mensagem, contexto)
        self.assertIsNotNone(item_audio)
        self.assertEqual(item_audio["tipo"], TIPO_AUDIO_RELEVANTE)
        self.assertEqual(item_audio["prioridade"], PRIORIDADE_ALTA)
        self.assertEqual(item_audio["acao_id"], "acao-critica-1")
        self.assertEqual(item_audio["pessoa"], "Carlos Diretor")
        self.assertIn("Carlos Diretor", item_audio["titulo"])
        self.assertIn("Auditoria de Compliance", item_audio["titulo"])
        self.assertEqual(
            item_audio["chave_dedupe"],
            f"{TIPO_AUDIO_RELEVANTE}:5511999999999@s.whatsapp.net:wa-audio-001",
        )

        # 2. Persistência na fila de atenção em estado aberto
        item_para_db = dict(item_audio)
        item_para_db["estado"] = ESTADO_ABERTO
        item_id = "item-audio-regressao-1"
        db = MockDb({
            COLLECTION: {
                item_id: item_para_db,
            }
        })

        # 3. Sweep de interrupção (dentro da janela de silêncio: 14:00 SP)
        horario_sp = datetime(2026, 9, 4, 14, 0, tzinfo=_TZ_SP)
        res = avaliar_interrupcao_atencao(db, now=horario_sp)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["candidatos"], 1)
        self.assertEqual(res["avaliados"], 1)
        self.assertEqual(res["notificados"], 1)
        self.assertEqual(res["pulados_janela"], 0)

        # 4. Desfecho observável: notificação de fato disparada para o Telegram
        mock_reserve.assert_called_once()
        args, _ = mock_reserve.call_args
        passed_today_str = args[1]
        passed_payload = args[3]
        self.assertEqual(passed_today_str, "2026-09-04")
        self.assertEqual(passed_payload["title"], item_audio["titulo"][:120])
        self.assertIn(item_audio["resumo"], passed_payload["message"])
        self.assertEqual(passed_payload["category"], "geral")
        self.assertEqual(passed_payload["source"], "atencao_interrupcao")
        self.assertEqual(passed_payload["atencao_id"], item_id)

        # 5. Trava de deduplicação no documento de atenção
        doc = db.collection(COLLECTION).document(item_id).to_dict()
        self.assertIsNotNone(doc.get("avaliado_interrupcao_em"))

    @patch("atencao._reserve_and_create_notification")
    def test_cenario_promessa_sem_retorno_5h_dispara_interrupcao(self, mock_reserve):
        """Cenário 2: Promessa em aberto sem retorno há 5h gera item de prioridade alta

        e o sweep de interrupção dispara notificação para o Telegram.
        """
        mock_reserve.return_value = True

        agora = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
        prometido_em = agora - timedelta(hours=5)
        vence_em = agora - timedelta(hours=1)
        promessa = {
            "chat_id": "5511888888888@s.whatsapp.net",
            "chat_name": "Parceiro Logístico",
            "mensagem_id": "wa-promessa-002",
            "texto": "Vou ver e te retorno",
            "prometido_em": prometido_em,
            "vence_em": vence_em,
            "estado": ESTADO_PROMESSA_ABERTA,
            "acao_id": "acao-logistica-2",
        }

        # 1. Detector puro avalia promessas vencidas
        itens = avaliar_promessas_vencidas([promessa], agora)
        self.assertEqual(len(itens), 1)
        item_promessa = itens[0]
        self.assertEqual(item_promessa["tipo"], TIPO_PROMESSA_SEM_RETORNO)
        self.assertEqual(item_promessa["prioridade"], PRIORIDADE_ALTA)
        self.assertIn("ha 5h", item_promessa["titulo"])
        self.assertIn("Parceiro Logístico", item_promessa["titulo"])
        self.assertEqual(
            item_promessa["chave_dedupe"],
            f"{TIPO_PROMESSA_SEM_RETORNO}:5511888888888@s.whatsapp.net:wa-promessa-002",
        )

        # 2. Persistência na fila de atenção em estado aberto
        item_para_db = dict(item_promessa)
        item_para_db["estado"] = ESTADO_ABERTO
        item_id = "item-promessa-regressao-2"
        db = MockDb({
            COLLECTION: {
                item_id: item_para_db,
            }
        })

        # 3. Sweep de interrupção (15:00 SP, dentro da janela)
        horario_sp = datetime(2026, 9, 4, 15, 0, tzinfo=_TZ_SP)
        res = avaliar_interrupcao_atencao(db, now=horario_sp)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["candidatos"], 1)
        self.assertEqual(res["avaliados"], 1)
        self.assertEqual(res["notificados"], 1)

        # 4. Desfecho observável: notificação disparada com dados da promessa
        mock_reserve.assert_called_once()
        args, _ = mock_reserve.call_args
        passed_payload = args[3]
        self.assertEqual(passed_payload["title"], item_promessa["titulo"][:120])
        self.assertIn("Parceiro Logístico", passed_payload["title"])
        self.assertIn("ha 5h", passed_payload["title"])
        self.assertEqual(passed_payload["category"], "geral")
        self.assertEqual(passed_payload["source"], "atencao_interrupcao")
        self.assertEqual(passed_payload["atencao_id"], item_id)

        # 5. Trava de deduplicação no documento de atenção
        doc = db.collection(COLLECTION).document(item_id).to_dict()
        self.assertIsNotNone(doc.get("avaliado_interrupcao_em"))

    @patch("atencao._reserve_and_create_notification")
    def test_cenario_aguardando_terceiro_vencido_fica_na_fila_sem_interromper(self, mock_reserve):
        """Cenário 3: Etapa aguardando terceiro vencida gera item de prioridade média,

        que entra na fila normal para briefing/varredura mas NUNCA dispara interrupção.
        Trava contra duas regressões opostas:
        (a) Promoção acidental para prioridade alta interrompendo o usuário sem necessidade;
        (b) Quebra na detecção fazendo o item sumir até da fila normal de atenção.
        """
        hoje = date(2026, 9, 4)
        tarefa = {
            "id": "tarefa-fornecedor-3",
            "titulo": "Aquisição de Servidores",
            "status": "em andamento",
            "degradation_count": 0,
            "data_limite": "2026-09-15",
            "plano_acao": [
                {
                    "id": "etapa-301",
                    "texto": "Aguardar cotação formal de hardware",
                    "estado": "aguardando_terceiro",
                    "aguardando_de": "Dell Enterprise",
                    "data_prevista": "2026-09-01",
                }
            ],
        }

        # 1. Detector puro avalia etapa vencida aguardando terceiro
        itens = avaliar_etapas([tarefa], hoje)
        self.assertEqual(len(itens), 1)
        item_etapa = itens[0]
        self.assertEqual(item_etapa["tipo"], TIPO_AGUARDANDO_TERCEIRO_VENCIDO)
        self.assertEqual(item_etapa["prioridade"], PRIORIDADE_MEDIA)
        self.assertEqual(item_etapa["estado"], ESTADO_ABERTO)
        self.assertEqual(item_etapa["pessoa"], "Dell Enterprise")
        self.assertEqual(item_etapa["acao_id"], "tarefa-fornecedor-3")
        self.assertEqual(item_etapa["etapa_id"], "etapa-301")

        # 2. Persistência no MockDb
        item_id = "item-etapa-regressao-3"
        db = MockDb({
            COLLECTION: {
                item_id: dict(item_etapa),
            }
        })

        # 3. Presença observável na fila de atenção normal (para briefing/varredura)
        res_fila = coletar_fila_atencao(db)
        self.assertEqual(res_fila["total"], 1)
        self.assertEqual(len(res_fila["itens"]), 1)
        fila_item = res_fila["itens"][0]
        self.assertEqual(fila_item["id"], item_id)
        self.assertEqual(fila_item["tipo"], TIPO_AGUARDANDO_TERCEIRO_VENCIDO)
        self.assertEqual(fila_item["prioridade"], PRIORIDADE_MEDIA)
        self.assertEqual(fila_item["pessoa"], "Dell Enterprise")
        self.assertEqual(fila_item["acao_id"], "tarefa-fornecedor-3")

        # 4. No MESMO MockDb, verificar que o sweep de interrupção NÃO interrompe
        horario_sp = datetime(2026, 9, 4, 14, 0, tzinfo=_TZ_SP)
        res_interrupcao = avaliar_interrupcao_atencao(db, now=horario_sp)

        self.assertEqual(res_interrupcao["status"], "ok")
        self.assertEqual(res_interrupcao["candidatos"], 0)
        self.assertEqual(res_interrupcao["avaliados"], 0)
        self.assertEqual(res_interrupcao["notificados"], 0)
        mock_reserve.assert_not_called()

        # 5. O documento permanece intacto para a rotina diária (sem avaliado_interrupcao_em)
        doc = db.collection(COLLECTION).document(item_id).to_dict()
        self.assertIsNone(doc.get("avaliado_interrupcao_em"))
        self.assertEqual(doc.get("estado"), ESTADO_ABERTO)


if __name__ == "__main__":
    unittest.main()
