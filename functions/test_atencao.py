"""Testes do detector e da fila de atenção (functions/atencao.py)."""

from datetime import date, datetime, timezone
import unittest

from atencao import (
    COLLECTION,
    ESTADO_ABERTO,
    ESTADO_DELEGADO,
    ESTADO_DESCARTADO,
    ESTADO_RESOLVIDO,
    PRIORIDADE_ALTA,
    PRIORIDADE_MEDIA,
    TIPO_AGUARDANDO_TERCEIRO_VENCIDO,
    avaliar_etapas,
    coletar_fila_atencao,
    resolver_item,
)


class MockDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})

    def get(self):
        return self

    def update(self, fields):
        if self._data is not None:
            self._data.update(fields)


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
            if match:
                filtered.append(d)
        return filtered

    def document(self, wanted):
        return next((d for d in self.docs if d.id == wanted), MockDoc(wanted, None))


class MockDb:
    def __init__(self, data):
        self.data = data

    def collection(self, name):
        docs = [MockDoc(k, v) for k, v in self.data.get(name, {}).items()]
        return MockQuery(docs)


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


if __name__ == "__main__":
    unittest.main()
