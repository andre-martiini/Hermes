"""Testes do detector e da fila de atenção (functions/atencao.py)."""

from datetime import date, datetime, timezone
import unittest
from unittest.mock import MagicMock, patch
import uuid

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from atencao import (
    COLLECTION,
    ESTADO_ABERTO,
    ESTADO_DELEGADO,
    ESTADO_DESCARTADO,
    ESTADO_RESOLVIDO,
    PRIORIDADE_ALTA,
    PRIORIDADE_MEDIA,
    PRIORIDADE_BAIXA,
    TIPO_AGUARDANDO_TERCEIRO_VENCIDO,
    TIPO_CONTA_VENCENDO,
    TIPO_ROTINA_SAUDE_AUSENTE,
    avaliar_etapas,
    avaliar_contas_vencendo,
    detectar_atencao_financeiro,
    avaliar_rotinas_saude,
    detectar_atencao_saude,
    coletar_fila_atencao,
    resolver_item,
    mapear_origem_categoria_notificacao,
    dentro_janela_permitida,
    esta_na_janela_silencio,
    avaliar_interrupcao_atencao,
    detectar_atencao_acoes,
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
    def __init__(self, docs, filters=None):
        self.docs = docs
        self.filters = filters or []

    def where(self, field, op, val):
        new_filters = list(self.filters)
        new_filters.append((field, op, val))
        return MockQuery(self.docs, new_filters)

    def stream(self):
        filtered = []
        for d in self.docs:
            data = d.to_dict()
            match = True
            for field, op, val in self.filters:
                if op == "==" and data.get(field) != val:
                    match = False
                    break
                elif op == ">=" and not (data.get(field) is not None and data.get(field) >= val):
                    match = False
                    break
                elif op == "<=" and not (data.get(field) is not None and data.get(field) <= val):
                    match = False
                    break
                elif op == "in" and data.get(field) not in val:
                    match = False
                    break
            if match:
                filtered.append(d)
        return filtered

    def document(self, wanted=None):
        if wanted is None:
            auto_id = f"mock-doc-{uuid.uuid4().hex[:8]}"
            new_doc = MockDoc(auto_id, {})
            self.docs.append(new_doc)
            return new_doc
        existing = next((d for d in self.docs if d.id == wanted), None)
        if existing is not None:
            return existing
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


class TestAguardandoTerceiroVencido(unittest.TestCase):
    def setUp(self):
        self.hoje = date(2026, 9, 3)

    def test_etapa_vencida_gera_item(self):
        tarefas = [
            {
                "id": "task-1",
                "titulo": "Renovar Alvará",
                "status": "em andamento",
                "data_limite": "2026-09-01",
                "plano_acao": [
                    {
                        "id": "step-1",
                        "texto": "Aguardar retorno do setor financeiro",
                        "estado": "aguardando_terceiro",
                        "aguardando_de": "Financeiro",
                        "data_prevista": "2026-09-01",
                    }
                ],
            }
        ]

        itens = avaliar_etapas(tarefas, self.hoje)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["origem"], "acao")
        self.assertEqual(item["tipo"], TIPO_AGUARDANDO_TERCEIRO_VENCIDO)
        self.assertEqual(item["prioridade"], PRIORIDADE_MEDIA)
        self.assertEqual(item["acao_id"], "task-1")
        self.assertEqual(item["etapa_id"], "step-1")
        self.assertEqual(item["pessoa"], "Financeiro")
        self.assertEqual(item["titulo"], "Financeiro deveria ter respondido sobre: Aguardar retorno do setor financeiro")
        self.assertEqual(item["sugestao"], "Cobrar Financeiro ou reagendar a etapa")
        self.assertEqual(item["estado"], ESTADO_ABERTO)
        self.assertEqual(item["chave_dedupe"], "aguardando_terceiro_vencido:task-1:step-1")

    def test_etapa_vencida_com_resposta_do_terceiro_nao_gera(self):
        chat_id = "5527999999999@c.us"
        tarefas = [
            {
                "id": "task-1",
                "titulo": "Pedido de Compras",
                "status": "em andamento",
                "whatsapp_vinculos": [{"chat_id": chat_id}],
                "plano_acao": [
                    {
                        "id": "step-1",
                        "texto": "Aguardar orçamento do fornecedor",
                        "estado": "aguardando_terceiro",
                        "aguardando_de": "Fornecedor",
                        "data_prevista": "2026-09-01",
                    }
                ],
            }
        ]

        # Resposta recebida após data_prevista
        respostas = {
            chat_id: [
                {"timestamp": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc), "from_me": False}
            ]
        }

        itens = avaliar_etapas(tarefas, self.hoje, respostas_por_chat=respostas)
        self.assertEqual(len(itens), 0, "Não deve gerar item se o terceiro já respondeu após a data prevista")

    def test_resposta_anterior_a_data_prevista_nao_suprime_alerta(self):
        chat_id = "5527999999999@c.us"
        tarefas = [
            {
                "id": "task-1",
                "titulo": "Pedido de Compras",
                "status": "em andamento",
                "whatsapp_vinculos": [{"chat_id": chat_id}],
                "plano_acao": [
                    {
                        "id": "step-1",
                        "texto": "Aguardar orçamento do fornecedor",
                        "estado": "aguardando_terceiro",
                        "aguardando_de": "Fornecedor",
                        "data_prevista": "2026-09-01",
                    }
                ],
            }
        ]

        # Resposta antiga (antes da data prevista) não conta como resposta à cobrança
        respostas = {
            chat_id: [
                {"timestamp": datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc), "from_me": False}
            ]
        }

        itens = avaliar_etapas(tarefas, self.hoje, respostas_por_chat=respostas)
        self.assertEqual(len(itens), 1)

    def test_etapa_nao_vencida_nao_gera(self):
        tarefas = [
            {
                "id": "task-2",
                "titulo": "Projeto Alfa",
                "status": "em andamento",
                "plano_acao": [
                    {
                        "id": "step-2",
                        "texto": "Aguardar aprovação",
                        "estado": "aguardando_terceiro",
                        "aguardando_de": "Diretoria",
                        "data_prevista": "2026-09-05",
                    },
                    {
                        "id": "step-3",
                        "texto": "Aguardar documento",
                        "estado": "aguardando_terceiro",
                        "aguardando_de": "RH",
                        "data_prevista": "2026-09-03",
                    },
                ],
            }
        ]

        itens = avaliar_etapas(tarefas, self.hoje)
        self.assertEqual(len(itens), 0)

    def test_acao_concluida_ignorada(self):
        tarefas = [
            {
                "id": "task-3",
                "titulo": "Ação Antiga Concluída",
                "status": "concluida",
                "plano_acao": [
                    {
                        "id": "step-3",
                        "texto": "Aguardar parecer",
                        "estado": "aguardando_terceiro",
                        "aguardando_de": "Jurídico",
                        "data_prevista": "2026-08-01",
                    }
                ],
            },
            {
                "id": "task-4",
                "titulo": "Ação Cancelada",
                "status": "cancelada",
                "plano_acao": [
                    {
                        "id": "step-4",
                        "texto": "Aguardar retorno",
                        "estado": "aguardando_terceiro",
                        "aguardando_de": "TI",
                        "data_prevista": "2026-08-01",
                    }
                ],
            },
        ]

        itens = avaliar_etapas(tarefas, self.hoje)
        self.assertEqual(len(itens), 0)

    def test_rodar_duas_vezes_gera_mesma_chave_dedupe(self):
        tarefa = {
            "id": "task-5",
            "titulo": "Homologação de Fornecedor",
            "status": "em andamento",
            "plano_acao": [
                {
                    "id": "step-5",
                    "texto": "Aguardar certidão",
                    "estado": "aguardando_terceiro",
                    "aguardando_de": "Cartório",
                    "data_prevista": "2026-08-20",
                }
            ],
        }

        rodada1 = avaliar_etapas([tarefa], self.hoje)
        rodada2 = avaliar_etapas([tarefa], self.hoje)

        self.assertEqual(len(rodada1), 1)
        self.assertEqual(len(rodada2), 1)
        self.assertEqual(rodada1[0]["chave_dedupe"], rodada2[0]["chave_dedupe"])
        self.assertEqual(rodada1[0]["chave_dedupe"], "aguardando_terceiro_vencido:task-5:step-5")

    def test_prioridade_alta_para_acao_critica(self):
        tarefa_degradada = {
            "id": "task-critica-1",
            "titulo": "Ação Muito Atrasada",
            "status": "em andamento",
            "degradation_count": 3,
            "plano_acao": [
                {
                    "id": "step-c1",
                    "texto": "Aguardar resposta",
                    "estado": "aguardando_terceiro",
                    "aguardando_de": "Chefe",
                    "data_prevista": "2026-08-30",
                }
            ],
        }

        tarefa_prazo_duro = {
            "id": "task-critica-2",
            "titulo": "Ação com Prazo Final Iminente",
            "status": "em andamento",
            "prazo_final": "2026-09-04",
            "plano_acao": [
                {
                    "id": "step-c2",
                    "texto": "Aguardar parecer",
                    "estado": "aguardando_terceiro",
                    "aguardando_de": "Perito",
                    "data_prevista": "2026-08-30",
                }
            ],
        }

        itens1 = avaliar_etapas([tarefa_degradada], self.hoje)
        self.assertEqual(itens1[0]["prioridade"], PRIORIDADE_ALTA)

        itens2 = avaliar_etapas([tarefa_prazo_duro], self.hoje)
        self.assertEqual(itens2[0]["prioridade"], PRIORIDADE_ALTA)


class TestFilaAtencaoTools(unittest.TestCase):
    def test_coletar_fila_atencao_ordenacao(self):
        db = MockDb({
            COLLECTION: {
                "item-1": {
                    "estado": "aberto",
                    "prioridade": "media",
                    "prazo": "2026-09-02",
                    "criado_em": "2026-09-01T10:00:00",
                },
                "item-2": {
                    "estado": "aberto",
                    "prioridade": "alta",
                    "prazo": "2026-09-05",
                    "criado_em": "2026-09-01T09:00:00",
                },
                "item-3": {
                    "estado": "aberto",
                    "prioridade": "alta",
                    "prazo": "2026-09-01",
                    "criado_em": "2026-09-01T08:00:00",
                },
                "item-fechado": {
                    "estado": "resolvido",
                    "prioridade": "alta",
                    "prazo": "2026-08-01",
                },
            }
        })

        res = coletar_fila_atencao(db, estado="aberto")
        self.assertEqual(res["total"], 3)
        # Ordem esperada: alta(prazo 2026-09-01), alta(prazo 2026-09-05), media(prazo 2026-09-02)
        self.assertEqual([x["id"] for x in res["itens"]], ["item-3", "item-2", "item-1"])

    def test_resolver_item_not_found(self):
        db = MockDb({COLLECTION: {}})
        res = resolver_item(db, "inexistente", ESTADO_RESOLVIDO, "Resolvido")
        self.assertEqual(res.get("status"), "not_found")
        self.assertIn("não encontrado", res.get("erro", ""))

    def test_resolver_item_exige_desfecho(self):
        db = MockDb({
            COLLECTION: {
                "item-1": {"estado": "aberto", "titulo": "Teste"}
            }
        })
        res = resolver_item(db, "item-1", ESTADO_RESOLVIDO, "")
        self.assertIn("Desfecho é obrigatório", res.get("erro", ""))

    def test_resolver_item_sucesso(self):
        db = MockDb({
            COLLECTION: {
                "item-1": {
                    "estado": "aberto",
                    "titulo": "Cobrança de certidão",
                    "acao_id": None,
                }
            }
        })
        res = resolver_item(db, "item-1", ESTADO_RESOLVIDO, "Cartório respondeu")
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("estado"), ESTADO_RESOLVIDO)
        self.assertEqual(res.get("desfecho"), "Cartório respondeu")
        # Verifica persistência no mock doc
        doc = db.collection(COLLECTION).document("item-1")
        self.assertEqual(doc.to_dict()["estado"], ESTADO_RESOLVIDO)
        self.assertEqual(doc.to_dict()["desfecho"], "Cartório respondeu")


class TestAvaliarInterrupcaoAtencao(unittest.TestCase):
    def setUp(self):
        self.tz_sp = zoneinfo.ZoneInfo("America/Sao_Paulo")

    def test_mapear_origem_categoria_notificacao(self):
        self.assertEqual(mapear_origem_categoria_notificacao("acao"), "acoes")
        self.assertEqual(mapear_origem_categoria_notificacao("ACAO"), "acoes")
        self.assertEqual(mapear_origem_categoria_notificacao(" whatsapp "), "geral")
        self.assertEqual(mapear_origem_categoria_notificacao("email"), "geral")
        self.assertEqual(mapear_origem_categoria_notificacao("financeiro"), "geral")
        self.assertEqual(mapear_origem_categoria_notificacao("saude"), "geral")
        self.assertEqual(mapear_origem_categoria_notificacao("agenda"), "geral")
        self.assertEqual(mapear_origem_categoria_notificacao("repo"), "geral")
        self.assertEqual(mapear_origem_categoria_notificacao(None), "geral")
        self.assertEqual(mapear_origem_categoria_notificacao(""), "geral")

    def test_dentro_janela_permitida(self):
        # Limites exatos
        self.assertTrue(dentro_janela_permitida("07:00"))
        self.assertTrue(dentro_janela_permitida("22:00"))
        self.assertTrue(dentro_janela_permitida("10:30"))
        self.assertTrue(dentro_janela_permitida("15:45"))

        # Fora da janela
        self.assertFalse(dentro_janela_permitida("06:59"))
        self.assertFalse(dentro_janela_permitida("22:01"))
        self.assertFalse(dentro_janela_permitida("00:00"))
        self.assertFalse(dentro_janela_permitida("05:30"))
        self.assertFalse(dentro_janela_permitida("23:59"))

        # Com datetime aware em SP
        dt_dentro_sp = datetime(2026, 9, 4, 10, 30, tzinfo=self.tz_sp)
        dt_fora_sp = datetime(2026, 9, 4, 5, 30, tzinfo=self.tz_sp)
        self.assertTrue(dentro_janela_permitida(dt_dentro_sp))
        self.assertFalse(dentro_janela_permitida(dt_fora_sp))

        # Com datetime naive (assume SP)
        self.assertTrue(dentro_janela_permitida(datetime(2026, 9, 4, 14, 0)))
        self.assertFalse(dentro_janela_permitida(datetime(2026, 9, 4, 3, 0)))

        # Inválidos
        self.assertFalse(dentro_janela_permitida(None))
        self.assertFalse(dentro_janela_permitida(123))

        # Alias esta_na_janela_silencio
        self.assertEqual(esta_na_janela_silencio("10:00"), dentro_janela_permitida("10:00"))
        self.assertEqual(esta_na_janela_silencio("05:00"), dentro_janela_permitida("05:00"))

    @patch("atencao._reserve_and_create_notification")
    def test_avaliar_interrupcao_sucesso_dentro_janela(self, mock_reserve):
        mock_reserve.return_value = True

        db = MockDb({
            COLLECTION: {
                "item-1": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": "acao",
                    "titulo": "Promessa crítica vencida",
                    "resumo": "Contato Alexandre sem retorno",
                    "sugestao": "Cobrar por áudio",
                }
            }
        })

        now = datetime(2026, 9, 4, 10, 30, tzinfo=self.tz_sp)
        res = avaliar_interrupcao_atencao(db, now=now)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["candidatos"], 1)
        self.assertEqual(res["avaliados"], 1)
        self.assertEqual(res["notificados"], 1)
        self.assertEqual(res["pulados_janela"], 0)

        mock_reserve.assert_called_once()
        args, _ = mock_reserve.call_args
        _, today_str, notif_ref, payload = args

        self.assertEqual(today_str, "2026-09-04")
        self.assertEqual(payload["title"], "Promessa crítica vencida")
        self.assertIn("Contato Alexandre sem retorno", payload["message"])
        self.assertIn("Sugestão: Cobrar por áudio", payload["message"])
        self.assertEqual(payload["category"], "acoes")
        self.assertEqual(payload["source"], "atencao_interrupcao")
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["send_at"], now)
        self.assertEqual(payload["atencao_id"], "item-1")

        # Verifica que gravou avaliado_interrupcao_em no documento
        doc = db.collection(COLLECTION).document("item-1")
        self.assertIsNotNone(doc.to_dict().get("avaliado_interrupcao_em"))

    @patch("atencao._reserve_and_create_notification")
    def test_avaliar_interrupcao_fora_da_janela_pula_sem_marcar(self, mock_reserve):
        db = MockDb({
            COLLECTION: {
                "item-1": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": "acao",
                    "titulo": "Promessa vencida",
                    "resumo": "Contato sem retorno",
                }
            }
        })

        # 05:30 da manhã — fora da janela 07:00 a 22:00
        now = datetime(2026, 9, 4, 5, 30, tzinfo=self.tz_sp)
        res = avaliar_interrupcao_atencao(db, now=now)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["candidatos"], 1)
        self.assertEqual(res["avaliados"], 0)
        self.assertEqual(res["notificados"], 0)
        self.assertEqual(res["pulados_janela"], 1)

        mock_reserve.assert_not_called()

        # Inegociável: item NÃO pode ter avaliado_interrupcao_em gravado para permitir retry
        doc = db.collection(COLLECTION).document("item-1")
        self.assertIsNone(doc.to_dict().get("avaliado_interrupcao_em"))

    @patch("atencao._reserve_and_create_notification")
    def test_avaliar_interrupcao_item_ja_avaliado_ignorado(self, mock_reserve):
        db = MockDb({
            COLLECTION: {
                "item-ja-visto": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": "acao",
                    "titulo": "Item anterior",
                    "avaliado_interrupcao_em": "2026-09-04T08:00:00",
                }
            }
        })

        now = datetime(2026, 9, 4, 11, 0, tzinfo=self.tz_sp)
        res = avaliar_interrupcao_atencao(db, now=now)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["candidatos"], 0)
        self.assertEqual(res["avaliados"], 0)
        self.assertEqual(res["notificados"], 0)
        mock_reserve.assert_not_called()

    @patch("atencao._reserve_and_create_notification")
    def test_avaliar_interrupcao_orcamento_esgotado_marca_avaliado(self, mock_reserve):
        # Orçamento de 3 notificações diárias já atingido
        mock_reserve.return_value = False

        db = MockDb({
            COLLECTION: {
                "item-1": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": "acao",
                    "titulo": "Promessa urgente",
                    "resumo": "Cobrar hoje",
                }
            }
        })

        now = datetime(2026, 9, 4, 14, 0, tzinfo=self.tz_sp)
        res = avaliar_interrupcao_atencao(db, now=now)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["candidatos"], 1)
        self.assertEqual(res["avaliados"], 1)
        self.assertEqual(res["notificados"], 0)

        mock_reserve.assert_called_once()
        # Item não reservou, mas DEVE ser marcado como avaliado para não reavaliar o resto do dia
        doc = db.collection(COLLECTION).document("item-1")
        self.assertIsNotNone(doc.to_dict().get("avaliado_interrupcao_em"))

    @patch("atencao._reserve_and_create_notification")
    def test_avaliar_interrupcao_mapeamento_origens(self, mock_reserve):
        mock_reserve.return_value = True

        db = MockDb({
            COLLECTION: {
                "item-fin": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": "financeiro",
                    "titulo": "Boleto vencendo",
                    "resumo": "Aluguel vence hoje",
                },
                "item-sau": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": "saude",
                    "titulo": "Medicação em atraso",
                    "resumo": "Dose da manhã",
                },
            }
        })

        now = datetime(2026, 9, 4, 12, 0, tzinfo=self.tz_sp)
        res = avaliar_interrupcao_atencao(db, now=now)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["candidatos"], 2)
        self.assertEqual(res["avaliados"], 2)
        self.assertEqual(res["notificados"], 2)

        self.assertEqual(mock_reserve.call_count, 2)
        categories = [call[0][3]["category"] for call in mock_reserve.call_args_list]
        self.assertEqual(categories, ["geral", "geral"])

    @patch("atencao._reserve_and_create_notification")
    def test_avaliar_interrupcao_isolamento_de_falha(self, mock_reserve):
        mock_reserve.return_value = True

        db = MockDb({
            COLLECTION: {
                "item-erro": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": "acao",
                    "titulo": "Item com problema",
                },
                "item-ok": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": "acao",
                    "titulo": "Item que passa",
                },
            }
        })

        doc_erro = db.collection(COLLECTION).document("item-erro")

        def _explode(*args, **kwargs):
            raise RuntimeError("Erro simulado no documento")

        doc_erro.update = _explode

        now = datetime(2026, 9, 4, 10, 0, tzinfo=self.tz_sp)
        res = avaliar_interrupcao_atencao(db, now=now)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["candidatos"], 2)
        self.assertEqual(res["avaliados"], 1)
        self.assertEqual(res["notificados"], 2)  # Tentou notificar ambos, o segundo persistiu update
        doc_ok = db.collection(COLLECTION).document("item-ok")
        self.assertIsNotNone(doc_ok.to_dict().get("avaliado_interrupcao_em"))

    @patch("atencao._reserve_and_create_notification")
    def test_avaliar_interrupcao_ignora_prioridade_media_ou_baixa(self, mock_reserve):
        db = MockDb({
            COLLECTION: {
                "item-media": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_MEDIA,
                    "origem": "acao",
                    "titulo": "Item médio",
                },
                "item-baixa": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_BAIXA,
                    "origem": "acao",
                    "titulo": "Item baixo",
                },
            }
        })

        now = datetime(2026, 9, 4, 10, 0, tzinfo=self.tz_sp)
        res = avaliar_interrupcao_atencao(db, now=now)

        self.assertEqual(res["candidatos"], 0)
        self.assertEqual(res["avaliados"], 0)
        self.assertEqual(res["notificados"], 0)
        mock_reserve.assert_not_called()

    @patch("atencao._reserve_and_create_notification")
    def test_avaliar_interrupcao_ignora_itens_fechados(self, mock_reserve):
        db = MockDb({
            COLLECTION: {
                "item-resolvido": {
                    "estado": ESTADO_RESOLVIDO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": "acao",
                    "titulo": "Item resolvido",
                },
                "item-descartado": {
                    "estado": ESTADO_DESCARTADO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": "acao",
                    "titulo": "Item descartado",
                },
            }
        })

        now = datetime(2026, 9, 4, 10, 0, tzinfo=self.tz_sp)
        res = avaliar_interrupcao_atencao(db, now=now)

        self.assertEqual(res["candidatos"], 0)
        self.assertEqual(res["avaliados"], 0)
        self.assertEqual(res["notificados"], 0)
        mock_reserve.assert_not_called()

    @patch("atencao._reserve_and_create_notification")
    def test_avaliar_interrupcao_fallback_titulo_e_mensagem(self, mock_reserve):
        mock_reserve.return_value = True

        db = MockDb({
            COLLECTION: {
                "item-sem-texto": {
                    "estado": ESTADO_ABERTO,
                    "prioridade": PRIORIDADE_ALTA,
                    "origem": None,
                    "titulo": None,
                    "resumo": None,
                    "sugestao": None,
                }
            }
        })

        now = datetime(2026, 9, 4, 10, 0, tzinfo=self.tz_sp)
        res = avaliar_interrupcao_atencao(db, now=now)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["avaliados"], 1)
        self.assertEqual(res["notificados"], 1)

        args, _ = mock_reserve.call_args
        payload = args[3]
        self.assertTrue(len(payload["title"]) > 0)
        self.assertTrue(len(payload["message"]) > 0)
        self.assertEqual(payload["category"], "geral")


class TestAtencaoFinanceiro(unittest.TestCase):
    def setUp(self):
        self.hoje = date(2026, 9, 5)

    def test_avaliar_contas_vencendo_em_ate_3_dias(self):
        # Hoje é 05/09/2026. Conta vence dia 07/09/2026 (delta = 2 dias).
        contas = [
            {
                "id": "bill-1",
                "description": "Internet Fibra",
                "amount": 150.0,
                "due_day": 7,
                "month": 8,  # Setembro (0-based)
                "year": 2026,
                "paid": False,
            }
        ]
        itens = avaliar_contas_vencendo(contas, self.hoje)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["origem"], "financeiro")
        self.assertEqual(item["tipo"], TIPO_CONTA_VENCENDO)
        self.assertEqual(item["prioridade"], PRIORIDADE_MEDIA)
        self.assertEqual(item["prazo"], "2026-09-07")
        self.assertIn("Internet Fibra", item["titulo"])
        self.assertIn("vence em 2 dia(s)", item["titulo"])
        self.assertEqual(item["chave_dedupe"], "conta_vencendo:bill-1:2026-09-07")
        self.assertEqual(item["evidencia"]["bill_id"], "bill-1")

    def test_avaliar_contas_vence_hoje_gera_prioridade_alta(self):
        contas = [
            {
                "id": "bill-2",
                "description": "Aluguel",
                "amount": 2500.0,
                "due_day": 5,
                "month": 8,
                "year": 2026,
                "paid": False,
            }
        ]
        itens = avaliar_contas_vencendo(contas, self.hoje)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["prioridade"], PRIORIDADE_ALTA)
        self.assertIn("vence hoje", itens[0]["titulo"])

    def test_avaliar_contas_vencida_no_mes_gera_prioridade_alta(self):
        contas = [
            {
                "id": "bill-3",
                "description": "Energia",
                "amount": 320.0,
                "due_day": 2,  # venceu há 3 dias
                "month": 8,
                "year": 2026,
                "paid": False,
            }
        ]
        itens = avaliar_contas_vencendo(contas, self.hoje)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["prioridade"], PRIORIDADE_ALTA)
        self.assertIn("vencida há 3 dia(s)", itens[0]["titulo"])

    def test_avaliar_contas_ignora_pagas(self):
        contas = [
            {
                "id": "bill-4",
                "description": "Condomínio",
                "amount": 800.0,
                "due_day": 6,
                "month": 8,
                "year": 2026,
                "paid": True,
            }
        ]
        itens = avaliar_contas_vencendo(contas, self.hoje)
        self.assertEqual(len(itens), 0)

    def test_avaliar_contas_ignora_vencimento_longe(self):
        contas = [
            {
                "id": "bill-5",
                "description": "Cartão",
                "amount": 1200.0,
                "due_day": 20,
                "month": 8,
                "year": 2026,
                "paid": False,
            }
        ]
        itens = avaliar_contas_vencendo(contas, self.hoje)
        self.assertEqual(len(itens), 0)

    def test_detectar_atencao_financeiro_persiste_no_db(self):
        db = MockDb({
            "fixed_bills": {
                "bill-10": {
                    "description": "Plano de Saúde",
                    "amount": 650.0,
                    "due_day": 6,
                    "month": 8,  # Setembro (0-based)
                    "year": 2026,
                    "paid": False,
                }
            }
        })
        itens = detectar_atencao_financeiro(db, hoje=self.hoje)
        self.assertEqual(len(itens), 1)
        doc = db.collection(COLLECTION).document("conta_vencendo:bill-10:2026-09-06").get()
        self.assertTrue(doc.exists)
        self.assertEqual(doc.to_dict()["origem"], "financeiro")
        self.assertEqual(doc.to_dict()["tipo"], TIPO_CONTA_VENCENDO)


class TestAtencaoSaude(unittest.TestCase):
    def setUp(self):
        self.hoje = date(2026, 9, 5)

    def test_avaliar_rotinas_saude_alerta_quando_sem_registro_ha_3_dias_ou_mais(self):
        registros = {
            "ultima_pesagem": {
                "date": "2026-09-01",
                "weight": 79.2,
            }
        }
        itens = avaliar_rotinas_saude(registros, self.hoje, dias_sem_registro_alerta=3)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["origem"], "saude")
        self.assertEqual(item["tipo"], TIPO_ROTINA_SAUDE_AUSENTE)
        self.assertEqual(item["prioridade"], PRIORIDADE_MEDIA)
        self.assertIn("Pesagem não registrada há 4 dias", item["titulo"])
        self.assertEqual(item["chave_dedupe"], "saude_pesagem_ausente:2026-09-01")
        self.assertEqual(item["evidencia"]["dias_sem_pesagem"], 4)
        self.assertEqual(item["evidencia"]["ultimo_peso"], 79.2)

    def test_avaliar_rotinas_saude_silencia_quando_recente(self):
        registros = {
            "ultima_pesagem": {
                "date": "2026-09-04",
                "weight": 78.8,
            }
        }
        itens = avaliar_rotinas_saude(registros, self.hoje, dias_sem_registro_alerta=3)
        self.assertEqual(len(itens), 0)

    def test_avaliar_rotinas_saude_silencia_quando_sem_dados(self):
        self.assertEqual(avaliar_rotinas_saude({}, self.hoje), [])
        self.assertEqual(avaliar_rotinas_saude({"ultima_pesagem": {}}, self.hoje), [])

    def test_detectar_atencao_saude_persiste_no_db(self):
        db = MockDb({
            "health_weights": {
                "w-1": {
                    "date": "2026-08-30",
                    "weight": 80.0,
                },
                "w-2": {
                    "date": "2026-09-01",
                    "weight": 79.5,
                }
            }
        })
        itens = detectar_atencao_saude(db, hoje=self.hoje)
        self.assertEqual(len(itens), 1)
        doc = db.collection(COLLECTION).document("saude_pesagem_ausente:2026-09-01").get()
        self.assertTrue(doc.exists)
        self.assertEqual(doc.to_dict()["origem"], "saude")
        self.assertEqual(doc.to_dict()["tipo"], TIPO_ROTINA_SAUDE_AUSENTE)
        self.assertEqual(doc.to_dict()["evidencia"]["dias_sem_pesagem"], 4)


class TestDetectarAtencaoAcoesIntegracao(unittest.TestCase):
    @patch("atencao.detectar_atencao_financeiro")
    @patch("atencao.detectar_atencao_saude")
    @patch("main.get_db")
    def test_detectar_atencao_acoes_chama_detectores_financeiro_e_saude(
        self, mock_get_db, mock_sau, mock_fin
    ):
        mock_get_db.return_value = MockDb()
        fn = getattr(detectar_atencao_acoes, "__wrapped__", detectar_atencao_acoes)
        fn()
        mock_fin.assert_called_once()
        mock_sau.assert_called_once()


if __name__ == "__main__":
    unittest.main()

