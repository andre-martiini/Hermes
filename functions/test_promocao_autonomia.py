"""Testes unitários para o motor de promoção de autonomia (functions/promocao_autonomia.py).

Cobre:
- Avaliação temporal da janela de cancelamento (avaliar_liberacao_promovidos)
- Criação de rascunhos promovidos (aguardando_janela) vs regulares (aguardando_aprovacao)
- Liberação periódica de rascunhos com janela vencida (liberar_rascunhos_promovidos)
- Cancelamento manual de rascunho em aguardando_janela via descartar_rascunho
- Descoberta de tipos elegíveis com filtros de amostra, taxa, tipos promovidos, pendentes, nunca e adiadas
- Decisão sobre promoção (aceitar -> grava em mcp_access; adiar/nunca -> não promove)
- Listagem de sugestões pendentes
- Chamadas via tools MCP hermes_tools
- Hook determinístico no retro semanal do agente
"""

from __future__ import annotations

import datetime
from datetime import timezone, timedelta
import unittest
from unittest import mock

import outbox_aprovacao as oa
import promocao_autonomia as pa


# ---------------------------------------------------------------------------
# Fixture / Mocks do Firestore
# ---------------------------------------------------------------------------

class _MockDocSnap:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None
        self.reference = None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRef:
    def __init__(self, col, doc_id: str):
        self.col = col
        self.id = doc_id

    def get(self, transaction=None):
        data = self.col._docs.get(self.id)
        snap = _MockDocSnap(self.id, data)
        snap.reference = self
        return snap

    def set(self, data, merge=False):
        if merge and self.id in self.col._docs:
            self.col._docs[self.id].update(data)
        else:
            self.col._docs[self.id] = dict(data)

    def update(self, data):
        if self.id not in self.col._docs:
            raise KeyError(f"Doc {self.id} does not exist")
        self.col._docs[self.id].update(data)

    def delete(self):
        self.col._docs.pop(self.id, None)


class _MockQuery:
    def __init__(self, col, items):
        self.col = col
        self.items = items

    def where(self, field, op, val):
        if op == "==":
            filtered = [(k, v) for k, v in self.items if v.get(field) == val]
        elif op == "in":
            filtered = [(k, v) for k, v in self.items if v.get(field) in val]
        elif op == ">=":
            filtered = [(k, v) for k, v in self.items if (v.get(field) is not None and v.get(field) >= val)]
        elif op == "<=":
            filtered = [(k, v) for k, v in self.items if (v.get(field) is not None and v.get(field) <= val)]
        else:
            filtered = []
        return _MockQuery(self.col, filtered)

    def order_by(self, field, direction=None):
        reverse = (
            direction == "DESCENDING"
            or getattr(direction, "name", "") == "DESCENDING"
            or str(direction) == "DESCENDING"
            or direction == -1
            or (hasattr(firestore, "Query") and direction == getattr(firestore.Query, "DESCENDING", "DESCENDING"))
        )
        sorted_items = sorted(
            self.items,
            key=lambda x: str(x[1].get(field) or ""),
            reverse=reverse,
        )
        return _MockQuery(self.col, sorted_items)

    def limit(self, n: int):
        return _MockQuery(self.col, self.items[:n])

    def stream(self):
        snaps = []
        for k, v in self.items:
            snap = _MockDocSnap(k, v)
            snap.reference = _MockDocRef(self.col, k)
            snaps.append(snap)
        return snaps


class _MockCollection:
    def __init__(self, db, name: str):
        self.db = db
        self.name = name
        self._docs: dict[str, dict] = {}
        self._id_counter = 1

    def document(self, doc_id: str | None = None):
        if not doc_id:
            doc_id = f"mock-doc-{self._id_counter}"
            self._id_counter += 1
        return _MockDocRef(self, doc_id)

    def where(self, field, op, val):
        if op == "==":
            filtered = [(k, v) for k, v in self._docs.items() if v.get(field) == val]
        elif op == "in":
            filtered = [(k, v) for k, v in self._docs.items() if v.get(field) in val]
        elif op == ">=":
            filtered = [(k, v) for k, v in self._docs.items() if (v.get(field) is not None and v.get(field) >= val)]
        elif op == "<=":
            filtered = [(k, v) for k, v in self._docs.items() if (v.get(field) is not None and v.get(field) <= val)]
        else:
            filtered = []
        return _MockQuery(self, filtered)

    def order_by(self, field, direction=None):
        reverse = (
            direction == "DESCENDING"
            or getattr(direction, "name", "") == "DESCENDING"
            or str(direction) == "DESCENDING"
            or direction == -1
            or (hasattr(firestore, "Query") and direction == getattr(firestore.Query, "DESCENDING", "DESCENDING"))
        )
        sorted_items = sorted(
            list(self._docs.items()),
            key=lambda x: str(x[1].get(field) or ""),
            reverse=reverse,
        )
        return _MockQuery(self, sorted_items)

    def limit(self, n: int):
        return _MockQuery(self, list(self._docs.items())[:n])

    def stream(self):
        snaps = []
        for k, v in self._docs.items():
            snap = _MockDocSnap(k, v)
            snap.reference = _MockDocRef(self, k)
            snaps.append(snap)
        return snaps


class _MockTransaction:
    def __init__(self):
        pass

    def get(self, doc_ref):
        return doc_ref.get()

    def update(self, doc_ref, data):
        doc_ref.update(data)

    def set(self, doc_ref, data, merge=False):
        doc_ref.set(data, merge=merge)

    def update(self, doc_ref, data):
        doc_ref.update(data)


class _MockDb:
    def __init__(self):
        self._collections: dict[str, _MockCollection] = {}

    def collection(self, name: str):
        if name not in self._collections:
            self._collections[name] = _MockCollection(self, name)
        return self._collections[name]

    def transaction(self):
        return _MockTransaction()


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

class TestAvaliarLiberacaoPromovidos(unittest.TestCase):
    """Testes de lógica pura da função avaliar_liberacao_promovidos."""

    def test_filtra_apenas_aguardando_janela_com_prazo_vencido_e_telegram_entregue(self):
        agora = datetime.datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
        rascunhos = [
            # Vencido há 2 min com card Telegram entregue -> deve liberar
            {
                "id": "r1",
                "status": oa.STATUS_AGUARDANDO_JANELA,
                "envio_liberado_em": agora - timedelta(minutes=2),
                "telegram_message_id": 100,
            },
            # Ainda dentro da janela (vence daqui a 5 min) -> não libera
            {
                "id": "r2",
                "status": oa.STATUS_AGUARDANDO_JANELA,
                "envio_liberado_em": agora + timedelta(minutes=5),
                "telegram_message_id": 101,
            },
            # Status aguardando_aprovacao comum (mesmo que com timestamp antigo) -> não libera
            {
                "id": "r3",
                "status": oa.STATUS_AGUARDANDO,
                "envio_liberado_em": agora - timedelta(minutes=10),
                "telegram_message_id": 102,
            },
            # Status descartado -> não libera
            {
                "id": "r4",
                "status": oa.STATUS_DESCARTADO,
                "envio_liberado_em": agora - timedelta(minutes=1),
                "telegram_message_id": 103,
            },
        ]

        prontos = oa.avaliar_liberacao_promovidos(rascunhos, agora)
        self.assertEqual(prontos, ["r1"])

    def test_nao_libera_se_card_telegram_nao_entregue(self):
        """Veto humano inegociável: não libera automaticamente se o dono não recebeu o botão Cancelar."""
        agora = datetime.datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
        rascunhos = [
            {
                "id": "r_sem_tg",
                "status": oa.STATUS_AGUARDANDO_JANELA,
                "envio_liberado_em": agora - timedelta(minutes=2),
                # telegram_message_id ausente
            },
        ]
        prontos = oa.avaliar_liberacao_promovidos(rascunhos, agora)
        self.assertEqual(prontos, [])

    def test_trata_envio_liberado_em_em_string_iso(self):
        agora = datetime.datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
        rascunhos = [
            {
                "id": "r_iso",
                "status": oa.STATUS_AGUARDANDO_JANELA,
                "envio_liberado_em": "2026-09-04T14:50:00+00:00",
                "telegram_message_id": 105,
            },
        ]
        prontos = oa.avaliar_liberacao_promovidos(rascunhos, agora)
        self.assertEqual(prontos, ["r_iso"])


class TestCriarRascunhoPromovido(unittest.TestCase):
    """Testes de criação de rascunho com tipo promovido vs regular."""

    def setUp(self):
        self.db = _MockDb()
        # Mock do destinatário WhatsApp e do envio Telegram
        self.dest_patch = mock.patch(
            "tools.hermes_tools._destinatario_whatsapp_previa",
            return_value={"encontrado": True, "nome": "Lucas", "chat_id": "5527999991111@c.us"},
        )
        self.tg_patch = mock.patch(
            "hermes_core_logic._send_telegram_message_with_keyboard",
            return_value=999,
        )
        self.tok_patch = mock.patch("hermes_core_logic._get_telegram_token", return_value="tok")
        self.chat_patch = mock.patch("main._resolve_default_telegram_chat_id", return_value="123")
        self.dest_patch.start()
        self.tg_patch.start()
        self.tok_patch.start()
        self.chat_patch.start()

    def tearDown(self):
        self.dest_patch.stop()
        self.tg_patch.stop()
        self.tok_patch.stop()
        self.chat_patch.stop()

    def test_tipo_nao_promovido_cria_com_status_aguardando_aprovacao(self):
        res = oa.criar_rascunho(
            self.db,
            contact_number="+5527999991111",
            message="Mensagem normal",
            motivo="Aviso",
            tipo="outro",
        )
        self.assertEqual(res["status"], oa.STATUS_AGUARDANDO)
        self.assertIn("O rascunho foi para aprovação do dono", res["instrucao"])
        doc = self.db.collection(oa.COLLECTION)._docs[res["outbox_id"]]
        self.assertEqual(doc["status"], oa.STATUS_AGUARDANDO)
        self.assertNotIn("envio_liberado_em", doc)

    def test_tipo_promovido_cria_com_aguardando_janela_e_botao_cancelar(self):
        # Cadastra o tipo em system/mcp_access.tipos_promovidos
        self.db.collection("system")._docs["mcp_access"] = {
            "tipos_promovidos": ["confirmacao_reuniao"],
            "janela_cancelamento_min": 15,
        }

        res = oa.criar_rascunho(
            self.db,
            contact_number="+5527999991111",
            message="Sua reunião está confirmada amanhã às 10h.",
            motivo="Confirmação",
            tipo="confirmacao_reuniao",
        )
        self.assertEqual(res["status"], oa.STATUS_AGUARDANDO_JANELA)
        self.assertIn("Tipo promovido", res["instrucao"])
        self.assertIn("15 min", res["instrucao"])
        self.assertTrue(res["telegram_notificado"])
        self.assertIsNotNone(res.get("envio_liberado_em"))

        doc = self.db.collection(oa.COLLECTION)._docs[res["outbox_id"]]
        self.assertEqual(doc["status"], oa.STATUS_AGUARDANDO_JANELA)
        self.assertIsNotNone(doc.get("envio_liberado_em"))

    def test_tipo_promovido_sem_telegram_degrada_para_aguardando_aprovacao(self):
        # Cadastra o tipo em system/mcp_access.tipos_promovidos
        self.db.collection("system")._docs["mcp_access"] = {
            "tipos_promovidos": ["confirmacao_reuniao"],
            "janela_cancelamento_min": 15,
        }
        with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value=None):
            res = oa.criar_rascunho(
                self.db,
                contact_number="+5527999991111",
                message="Sua reunião está confirmada amanhã às 10h.",
                motivo="Confirmação",
                tipo="confirmacao_reuniao",
            )
            self.assertEqual(res["status"], oa.STATUS_AGUARDANDO)
            self.assertFalse(res["telegram_notificado"])
            self.assertIn("Degradado para aprovação manual", res["instrucao"])
            doc = self.db.collection(oa.COLLECTION)._docs[res["outbox_id"]]
            self.assertEqual(doc["status"], oa.STATUS_AGUARDANDO)
            self.assertIsNone(doc.get("envio_liberado_em"))


class TestLiberacaoECancelamento(unittest.TestCase):
    """Testes de liberação periódica de promovidos e cancelamento via descarte."""

    def setUp(self):
        self.db = _MockDb()
        self.tx_patch = mock.patch("firebase_admin.firestore.transactional", side_effect=lambda fn: fn)
        self.tx_patch.start()
        self.addCleanup(self.tx_patch.stop)
        self.outbox = self.db.collection(oa.COLLECTION)

    def test_liberar_rascunhos_promovidos_so_libera_vencidos(self):
        agora = datetime.datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
        self.outbox._docs["vencido"] = {
            "status": oa.STATUS_AGUARDANDO_JANELA,
            "destinatario_nome": "Lucas",
            "content": "Msg 1",
            "tipo": "confirmacao_reuniao",
            "envio_liberado_em": agora - timedelta(minutes=1),
            "telegram_message_id": 999,
        }
        self.outbox._docs["dentro_janela"] = {
            "status": oa.STATUS_AGUARDANDO_JANELA,
            "destinatario_nome": "Marcos",
            "content": "Msg 2",
            "tipo": "confirmacao_reuniao",
            "envio_liberado_em": agora + timedelta(minutes=5),
            "telegram_message_id": 1000,
        }

        liberados = oa.liberar_rascunhos_promovidos(self.db, agora=agora)
        self.assertEqual(liberados, 1)

        doc_v = self.outbox._docs["vencido"]
        self.assertEqual(doc_v["status"], oa.STATUS_PENDING)
        self.assertEqual(doc_v["aprovado_via"], "janela_automatica")

        doc_j = self.outbox._docs["dentro_janela"]
        self.assertEqual(doc_j["status"], oa.STATUS_AGUARDANDO_JANELA)

    def test_liberar_rascunhos_promovidos_ignora_vencido_sem_telegram(self):
        agora = datetime.datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
        self.outbox._docs["vencido_sem_tg"] = {
            "status": oa.STATUS_AGUARDANDO_JANELA,
            "destinatario_nome": "Lucas",
            "content": "Msg sem tg",
            "tipo": "confirmacao_reuniao",
            "envio_liberado_em": agora - timedelta(minutes=1),
            # sem telegram_message_id
        }
        liberados = oa.liberar_rascunhos_promovidos(self.db, agora=agora)
        self.assertEqual(liberados, 0)
        self.assertEqual(self.outbox._docs["vencido_sem_tg"]["status"], oa.STATUS_AGUARDANDO_JANELA)

    def test_cancelamento_via_descartar_rascunho_funciona_em_aguardando_janela(self):
        self.outbox._docs["promovido_para_cancelar"] = {
            "status": oa.STATUS_AGUARDANDO_JANELA,
            "destinatario_nome": "Lucas",
            "content": "Texto a cancelar",
            "tipo": "confirmacao_reuniao",
            "item_atencao_id": "item-123",
        }
        self.db.collection("atencao")._docs["item-123"] = {
            "estado": "resolvido",
            "titulo": "Item vinculado",
        }

        res = oa.descartar_rascunho(self.db, outbox_id="promovido_para_cancelar")
        self.assertEqual(res["status"], "ok")

        doc = self.outbox._docs["promovido_para_cancelar"]
        self.assertEqual(doc["status"], oa.STATUS_DESCARTADO)

        # Item de atenção reaberto
        item = self.db.collection("atencao")._docs["item-123"]
        self.assertEqual(item["estado"], "aberto")

    def test_cancelamento_atomico_rejeita_se_ja_aprovado_na_corrida(self):
        self.outbox._docs["corrida_doc"] = {
            "status": oa.STATUS_PENDING,
            "destinatario_nome": "Lucas",
            "content": "Texto já aprovado",
            "tipo": "confirmacao_reuniao",
        }
        res = oa.descartar_rascunho(self.db, outbox_id="corrida_doc")
        self.assertEqual(res["status"], "already_decided")
        self.assertEqual(self.outbox._docs["corrida_doc"]["status"], oa.STATUS_PENDING)


class TestTiposElegiveisParaPromocao(unittest.TestCase):
    """Testes de descoberta de tipos elegíveis para promoção de autonomia."""

    def setUp(self):
        self.db = _MockDb()
        self.outbox = self.db.collection("whatsapp_outbox")

    def test_amostra_insuficiente_nao_fica_elegivel(self):
        agora = datetime.datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        # 5 rascunhos (menor que o mínimo de 8)
        for i in range(5):
            self.outbox._docs[f"doc_{i}"] = {
                "tipo": "aviso_agenda",
                "status": oa.STATUS_SENT,
                "foi_editado": False,
                "aprovado_em": agora - timedelta(hours=i),
            }

        elegiveis = pa.tipos_elegiveis_para_promocao(self.db, amostra_minima=8, taxa_minima=0.9)
        self.assertEqual(len(elegiveis), 0)

    def test_taxa_sem_edicao_baixa_nao_fica_elegivel(self):
        agora = datetime.datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        # 10 rascunhos: 3 sem edição e 7 com edição (30% < 90%)
        for i in range(10):
            self.outbox._docs[f"doc_{i}"] = {
                "tipo": "cobranca_terceiro",
                "status": oa.STATUS_SENT,
                "foi_editado": (i >= 3),
                "aprovado_em": agora - timedelta(hours=i),
            }

        elegiveis = pa.tipos_elegiveis_para_promocao(self.db, amostra_minima=8, taxa_minima=0.9)
        self.assertEqual(len(elegiveis), 0)

    def test_tipo_ja_promovido_em_mcp_access_e_excluido(self):
        agora = datetime.datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        # 10 rascunhos perfeitos (100% sem edição)
        for i in range(10):
            self.outbox._docs[f"doc_{i}"] = {
                "tipo": "confirmacao_reuniao",
                "status": oa.STATUS_SENT,
                "foi_editado": False,
                "aprovado_em": agora - timedelta(hours=i),
            }

        self.db.collection("system")._docs["mcp_access"] = {
            "tipos_promovidos": ["confirmacao_reuniao"]
        }

        elegiveis = pa.tipos_elegiveis_para_promocao(self.db, amostra_minima=8, taxa_minima=0.9)
        self.assertEqual(len(elegiveis), 0)

    def test_tipo_com_sugestao_pendente_ou_nunca_e_excluido(self):
        agora = datetime.datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        for i in range(10):
            self.outbox._docs[f"doc_{i}"] = {
                "tipo": "retorno_promessa",
                "status": oa.STATUS_SENT,
                "foi_editado": False,
                "aprovado_em": agora - timedelta(hours=i),
            }

        # Sugestão pendente existente
        self.db.collection(pa.COL_PROMOCOES)._docs["retorno_promessa"] = {
            "status": pa.STATUS_PENDENTE,
        }

        elegiveis = pa.tipos_elegiveis_para_promocao(self.db, amostra_minima=8, taxa_minima=0.9)
        self.assertEqual(len(elegiveis), 0)

        # Se for "nunca", também continua excluído
        self.db.collection(pa.COL_PROMOCOES)._docs["retorno_promessa"]["status"] = pa.STATUS_NUNCA
        elegiveis = pa.tipos_elegiveis_para_promocao(self.db, amostra_minima=8, taxa_minima=0.9)
        self.assertEqual(len(elegiveis), 0)

    def test_tipo_com_sugestao_adiada_e_reavaliado_e_aprovado(self):
        agora = datetime.datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        for i in range(10):
            self.outbox._docs[f"doc_{i}"] = {
                "tipo": "retorno_promessa",
                "status": oa.STATUS_SENT,
                "foi_editado": False,
                "aprovado_em": agora - timedelta(hours=i),
            }

        # Sugestão anterior foi "adiada"
        self.db.collection(pa.COL_PROMOCOES)._docs["retorno_promessa"] = {
            "status": pa.STATUS_ADIADA,
        }

        elegiveis = pa.tipos_elegiveis_para_promocao(self.db, amostra_minima=8, taxa_minima=0.9)
        self.assertEqual(len(elegiveis), 1)
        self.assertEqual(elegiveis[0]["tipo"], "retorno_promessa")
        self.assertEqual(elegiveis[0]["metricas"]["taxa_sem_edicao"], 1.0)

    def test_ordena_por_recencia_ao_limitar_janela_recente(self):
        """Garante que a janela pega os mais recentes por created_at decrescente."""
        agora = datetime.datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        # 10 rascunhos antigos de um tipo descontinuado
        for i in range(10):
            self.outbox._docs[f"velho_{i}"] = {
                "tipo": "tipo_antigo",
                "status": oa.STATUS_SENT,
                "foi_editado": False,
                "created_at": (agora - timedelta(days=30, hours=i)).isoformat(),
                "aprovado_em": agora - timedelta(days=30, hours=i),
            }
        # 10 rascunhos recentes de um tipo ativo
        for i in range(10):
            self.outbox._docs[f"novo_{i}"] = {
                "tipo": "tipo_recente",
                "status": oa.STATUS_SENT,
                "foi_editado": False,
                "created_at": (agora - timedelta(hours=i)).isoformat(),
                "aprovado_em": agora - timedelta(hours=i),
            }

        # Com janela_recente=10, deve selecionar os 10 novos e ignorar os 10 velhos
        elegiveis = pa.tipos_elegiveis_para_promocao(
            self.db, amostra_minima=8, taxa_minima=0.9, janela_recente=10
        )
        tipos = [e["tipo"] for e in elegiveis]
        self.assertIn("tipo_recente", tipos)
        self.assertNotIn("tipo_antigo", tipos)


class TestDecidirPromocaoAutonomia(unittest.TestCase):
    """Testes de transição de decisão (aceitar, adiar, nunca)."""

    def setUp(self):
        self.db = _MockDb()
        self.tx_patch = mock.patch("firebase_admin.firestore.transactional", side_effect=lambda fn: fn)
        self.tx_patch.start()
        self.addCleanup(self.tx_patch.stop)
        self.promocoes = self.db.collection(pa.COL_PROMOCOES)
        self.promocoes._docs["confirmacao_reuniao"] = {
            "tipo": "confirmacao_reuniao",
            "status": pa.STATUS_PENDENTE,
            "amostra": 10,
            "taxa_sem_edicao": 0.95,
        }

    def test_decisao_invalida_retorna_erro(self):
        res = pa.decidir_promocao_autonomia(self.db, tipo="confirmacao_reuniao", decisao="talvez")
        self.assertFalse(res["ok"])
        self.assertIn("Decisão inválida", res["erro"])

    def test_decisao_tipo_inexistente_retorna_erro(self):
        res = pa.decidir_promocao_autonomia(self.db, tipo="inexistente", decisao="aceitar")
        self.assertFalse(res["ok"])
        self.assertIn("não encontrada", res["erro"])

    def test_aceitar_promove_tipo_e_insere_em_mcp_access(self):
        res = pa.decidir_promocao_autonomia(self.db, tipo="confirmacao_reuniao", decisao="aceitar")
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], pa.STATUS_ACEITA)

        # Verifica documento de promoção
        sug = self.promocoes._docs["confirmacao_reuniao"]
        self.assertEqual(sug["status"], pa.STATUS_ACEITA)
        self.assertEqual(sug["decisao"], "aceitar")

        # Verifica persistência em system/mcp_access
        mcp = self.db.collection("system")._docs["mcp_access"]
        self.assertIn("confirmacao_reuniao", mcp["tipos_promovidos"])

    def test_adiar_mantem_fora_de_mcp_access(self):
        res = pa.decidir_promocao_autonomia(self.db, tipo="confirmacao_reuniao", decisao="adiar")
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], pa.STATUS_ADIADA)

        mcp_docs = self.db.collection("system")._docs
        self.assertTrue("mcp_access" not in mcp_docs or "confirmacao_reuniao" not in mcp_docs["mcp_access"].get("tipos_promovidos", []))

    def test_nunca_mantem_fora_de_mcp_access(self):
        res = pa.decidir_promocao_autonomia(self.db, tipo="confirmacao_reuniao", decisao="nunca")
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], pa.STATUS_NUNCA)

        mcp_docs = self.db.collection("system")._docs
        self.assertTrue("mcp_access" not in mcp_docs or "confirmacao_reuniao" not in mcp_docs["mcp_access"].get("tipos_promovidos", []))

    def test_tentar_decidir_sugestao_ja_decidida_retorna_erro(self):
        pa.decidir_promocao_autonomia(self.db, tipo="confirmacao_reuniao", decisao="aceitar")
        res_repetida = pa.decidir_promocao_autonomia(self.db, tipo="confirmacao_reuniao", decisao="aceitar")
        self.assertFalse(res_repetida["ok"])
        self.assertIn("já estava decidida", res_repetida["erro"])


class TestListarPromocoesPendentesETools(unittest.TestCase):
    """Testes de listagem de sugestões e integração com hermes_tools."""

    def setUp(self):
        self.db = _MockDb()
        self.tx_patch = mock.patch("firebase_admin.firestore.transactional", side_effect=lambda fn: fn)
        self.tx_patch.start()
        self.addCleanup(self.tx_patch.stop)
        self.promocoes = self.db.collection(pa.COL_PROMOCOES)
        self.promocoes._docs["tipo1"] = {
            "tipo": "tipo1",
            "status": pa.STATUS_PENDENTE,
            "amostra": 12,
            "aprovados_sem_edicao": 11,
            "taxa_sem_edicao": 11 / 12,
            "sugerida_em": "2026-09-04T10:00:00+00:00",
        }
        self.promocoes._docs["tipo2"] = {
            "tipo": "tipo2",
            "status": pa.STATUS_ACEITA,
            "amostra": 10,
            "taxa_sem_edicao": 1.0,
            "sugerida_em": "2026-09-04T09:00:00+00:00",
        }

    def test_listar_promocoes_pendentes_retorna_apenas_pendentes(self):
        res = pa.listar_promocoes_pendentes(self.db, limite=10)
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["promocoes"][0]["tipo"], "tipo1")

    def test_tools_mcp_consultar_e_decidir(self):
        from tools.hermes_tools import ToolContext, _consultar_promocoes_autonomia_sugeridas, _decidir_promocao_autonomia
        ctx = ToolContext(_db=self.db)

        # Consulta
        res_list = _consultar_promocoes_autonomia_sugeridas(ctx, {"limite": 5})
        self.assertEqual(res_list["total"], 1)

        # Decisão
        res_dec = _decidir_promocao_autonomia(ctx, {"tipo": "tipo1", "decisao": "aceitar"})
        self.assertTrue(res_dec["ok"])
        self.assertEqual(res_dec["status"], pa.STATUS_ACEITA)


class TestHookRetroAgentePromocao(unittest.TestCase):
    """Testes do hook determinístico de promoção de autonomia dentro da retro semanal."""

    def setUp(self):
        self.db = _MockDb()

    def test_hook_limita_a_2_sugestoes_e_adiciona_aviso(self):
        from retro_agente import executar_retro_semanal

        # Simula 1 agent_run para não silenciar
        agora = datetime.datetime.now(timezone.utc)
        self.db.collection("agent_runs")._docs["run1"] = {
            "rotina": "briefing_matinal",
            "status": "sucesso",
            "criado_em": agora - timedelta(days=1),
            "iniciado_em": agora - timedelta(days=1),
            "finalizado_em": agora - timedelta(days=1) + timedelta(minutes=2),
            "duracao_ms": 120000,
        }

        # Mock de 3 tipos elegíveis para testar o limite de no máximo 2
        elegiveis_mock = [
            {"tipo": "tipo_a", "metricas": {"amostra": 10, "taxa_sem_edicao": 0.95}},
            {"tipo": "tipo_b", "metricas": {"amostra": 12, "taxa_sem_edicao": 0.92}},
            {"tipo": "tipo_c", "metricas": {"amostra": 15, "taxa_sem_edicao": 1.0}},
        ]

        with mock.patch("promocao_autonomia.tipos_elegiveis_para_promocao", return_value=elegiveis_mock), \
             mock.patch("retro_agente.generate_content_logged", return_value=(mock.MagicMock(text='{"resumo": "Semana ok", "proposta_pop": null}'), 0.001)), \
             mock.patch("main._resolve_default_telegram_chat_id", return_value=123), \
             mock.patch("main._send_telegram_message_raw") as mock_tg:

            res = executar_retro_semanal(self.db, now=agora)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(len(res["sugestoes_promocao"]), 2)
            self.assertEqual(res["sugestoes_promocao"], ["tipo_a", "tipo_b"])

            # Confere que foram gravados na coleção
            sug_col = self.db.collection(pa.COL_PROMOCOES)._docs
            self.assertIn("tipo_a", sug_col)
            self.assertIn("tipo_b", sug_col)
            self.assertNotIn("tipo_c", sug_col)

            # Confere que o Telegram foi chamado mencionando as sugestões de autonomia
            mock_tg.assert_called_once()
            _, _, sent_text = mock_tg.call_args[0]
            self.assertIn("Sugestão de autonomia", sent_text)
            self.assertIn("'tipo_a'", sent_text)
            self.assertIn("'tipo_b'", sent_text)


if __name__ == "__main__":
    unittest.main()
