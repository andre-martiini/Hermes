"""Testes unitários para o módulo functions/agent_requests.py (PR 1, Fase 1).

Cobre:
- Lógica pura: validação de transições e montagem de payload
- Enfileiramento e atualização com proteção de concorrência (ignora se em_andamento/terminal)
- Conclusão idempotente protegida contra toque duplo (resultado vs erro)
- Listagem e contagem de pedidos pendentes
"""

from datetime import datetime, timezone
import unittest

import agent_requests as ar


class _MockDocSnap:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRef:
    def __init__(self, col, doc_id: str):
        self.col = col
        self.id = doc_id

    def get(self):
        data = self.col._docs.get(self.id)
        return _MockDocSnap(self.id, data)

    def set(self, data, merge=False):
        if merge and self.id in self.col._docs:
            self.col._docs[self.id].update(data)
        else:
            self.col._docs[self.id] = dict(data)

    def update(self, data):
        if self.id not in self.col._docs:
            raise KeyError(f"Document {self.id} does not exist")
        self.col._docs[self.id].update(data)


class _MockQuery:
    def __init__(self, col, items):
        self.col = col
        self.items = items

    def where(self, field, op, val):
        filtered = [
            (k, v) for k, v in self.items
            if op == "==" and v.get(field) == val
        ]
        return _MockQuery(self.col, filtered)

    def stream(self):
        return [_MockDocSnap(k, v) for k, v in self.items]


class _MockCollection:
    def __init__(self, db, name: str):
        self.db = db
        self.name = name
        self._docs: dict[str, dict] = {}

    def document(self, doc_id: str):
        return _MockDocRef(self, doc_id)

    def where(self, field, op, val):
        filtered = [
            (k, v) for k, v in self._docs.items()
            if op == "==" and v.get(field) == val
        ]
        return _MockQuery(self, filtered)

    def stream(self):
        return [_MockDocSnap(k, v) for k, v in self._docs.items()]


class _MockDB:
    def __init__(self):
        self._collections: dict[str, _MockCollection] = {}

    def collection(self, name: str) -> _MockCollection:
        if name not in self._collections:
            self._collections[name] = _MockCollection(self, name)
        return self._collections[name]


class TestLogicaPura(unittest.TestCase):
    def test_transicoes_validas(self):
        self.assertEqual(ar.validar_transicao(ar.STATUS_PENDENTE), (True, ""))
        self.assertEqual(ar.validar_transicao(ar.STATUS_EM_ANDAMENTO), (True, ""))

    def test_transicoes_invalidas_terminais(self):
        valido, motivo = ar.validar_transicao(ar.STATUS_CONCLUIDO)
        self.assertFalse(valido)
        self.assertIn("já decidido", motivo)

        valido, motivo = ar.validar_transicao(ar.STATUS_ERRO)
        self.assertFalse(valido)
        self.assertIn("já decidido", motivo)

    def test_transicoes_invalidas_outros(self):
        valido, motivo = ar.validar_transicao(None)
        self.assertFalse(valido)
        self.assertEqual(motivo, "Pedido não encontrado.")

        valido, motivo = ar.validar_transicao("desconhecido")
        self.assertFalse(valido)
        self.assertIn("status inválido", motivo)

    def test_montar_payload_consolidar_audio(self):
        payload = ar.montar_payload_consolidar_audio(
            chat_id="chat-123",
            chat_name="Guilherme",
            mensagem_ids=["m1", "m2"],
            acao_id="acao-99",
            item_atencao_id="at-88",
        )
        self.assertEqual(payload["chat_id"], "chat-123")
        self.assertEqual(payload["chat_name"], "Guilherme")
        self.assertEqual(payload["mensagem_ids"], ["m1", "m2"])
        self.assertEqual(payload["acao_id"], "acao-99")
        self.assertEqual(payload["item_atencao_id"], "at-88")


class TestEnfileirarOuAtualizar(unittest.TestCase):
    def setUp(self):
        self.db = _MockDB()

    def test_enfileirar_novo_pedido(self):
        res = ar.enfileirar_ou_atualizar(
            self.db,
            doc_id="req-1",
            tipo=ar.TIPO_CONSOLIDAR_AUDIO,
            payload={"chat_id": "c1", "mensagem_ids": ["m1"]},
            origem="atencao_whatsapp.audio_relevante",
            acao_id="acao-1",
            item_atencao_id="at-1",
        )
        self.assertEqual(res["status"], "enfileirado")
        self.assertEqual(res["doc_id"], "req-1")

        snap = self.db.collection(ar.COLLECTION).document("req-1").get()
        self.assertTrue(snap.exists)
        d = snap.to_dict()
        self.assertEqual(d["tipo"], ar.TIPO_CONSOLIDAR_AUDIO)
        self.assertEqual(d["status"], ar.STATUS_PENDENTE)
        self.assertEqual(d["payload"]["mensagem_ids"], ["m1"])
        self.assertEqual(d["origem"], "atencao_whatsapp.audio_relevante")

    def test_atualizar_pedido_pendente_faz_merge(self):
        # Enfileira o primeiro
        ar.enfileirar_ou_atualizar(
            self.db,
            doc_id="req-seq",
            tipo=ar.TIPO_CONSOLIDAR_AUDIO,
            payload={"chat_id": "c1", "mensagem_ids": ["m1"]},
            origem="atencao_whatsapp.audio_relevante",
        )

        # Chega o segundo áudio mesclado
        res = ar.enfileirar_ou_atualizar(
            self.db,
            doc_id="req-seq",
            tipo=ar.TIPO_CONSOLIDAR_AUDIO,
            payload={"chat_id": "c1", "mensagem_ids": ["m1", "m2"]},
            origem="atencao_whatsapp.audio_relevante",
        )
        self.assertEqual(res["status"], "atualizado")

        snap = self.db.collection(ar.COLLECTION).document("req-seq").get()
        d = snap.to_dict()
        self.assertEqual(d["status"], ar.STATUS_PENDENTE)
        self.assertEqual(d["payload"]["mensagem_ids"], ["m1", "m2"])

    def test_nao_mexe_se_em_andamento(self):
        # Doc já em andamento pelo executor
        col = self.db.collection(ar.COLLECTION)
        col._docs["req-running"] = {
            "status": ar.STATUS_EM_ANDAMENTO,
            "tipo": ar.TIPO_CONSOLIDAR_AUDIO,
            "payload": {"mensagem_ids": ["m1"]},
        }

        res = ar.enfileirar_ou_atualizar(
            self.db,
            doc_id="req-running",
            tipo=ar.TIPO_CONSOLIDAR_AUDIO,
            payload={"mensagem_ids": ["m1", "m2"]},
            origem="atencao_whatsapp.audio_relevante",
        )
        self.assertEqual(res["status"], "ignorado")
        self.assertIn("em_andamento", res["motivo"])

        # Payload não foi alterado
        d = col.document("req-running").get().to_dict()
        self.assertEqual(d["payload"]["mensagem_ids"], ["m1"])

    def test_nao_mexe_se_concluido_ou_erro(self):
        col = self.db.collection(ar.COLLECTION)
        col._docs["req-done"] = {
            "status": ar.STATUS_CONCLUIDO,
            "tipo": ar.TIPO_CONSOLIDAR_AUDIO,
            "resultado": "Audio consolidado no diario",
            "payload": {"mensagem_ids": ["m1"]},
        }

        res = ar.enfileirar_ou_atualizar(
            self.db,
            doc_id="req-done",
            tipo=ar.TIPO_CONSOLIDAR_AUDIO,
            payload={"mensagem_ids": ["m1", "m2"]},
            origem="atencao_whatsapp.audio_relevante",
        )
        self.assertEqual(res["status"], "ignorado")
        d = col.document("req-done").get().to_dict()
        self.assertEqual(d["payload"]["mensagem_ids"], ["m1"])


class TestConcluir(unittest.TestCase):
    def setUp(self):
        self.db = _MockDB()

    def test_concluir_com_resultado_sucesso(self):
        col = self.db.collection(ar.COLLECTION)
        col._docs["req-1"] = {
            "status": ar.STATUS_PENDENTE,
            "tipo": ar.TIPO_CONSOLIDAR_AUDIO,
        }

        res = ar.concluir(self.db, "req-1", resultado="Consolidado com 2 achados")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["novo_status"], ar.STATUS_CONCLUIDO)

        snap = col.document("req-1").get()
        d = snap.to_dict()
        self.assertEqual(d["status"], ar.STATUS_CONCLUIDO)
        self.assertEqual(d["resultado"], "Consolidado com 2 achados")
        self.assertIsNone(d["erro"])

    def test_concluir_com_erro(self):
        col = self.db.collection(ar.COLLECTION)
        col._docs["req-2"] = {
            "status": ar.STATUS_EM_ANDAMENTO,
            "tipo": ar.TIPO_CONSOLIDAR_AUDIO,
        }

        res = ar.concluir(self.db, "req-2", erro="Falha ao transcrever: arquivo corrompido")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["novo_status"], ar.STATUS_ERRO)

        snap = col.document("req-2").get()
        d = snap.to_dict()
        self.assertEqual(d["status"], ar.STATUS_ERRO)
        self.assertEqual(d["erro"], "Falha ao transcrever: arquivo corrompido")
        self.assertIsNone(d["resultado"])

    def test_exige_exatamente_um_de_resultado_ou_erro(self):
        col = self.db.collection(ar.COLLECTION)
        col._docs["req-3"] = {"status": ar.STATUS_PENDENTE}

        # Ambos preenchidos
        res1 = ar.concluir(self.db, "req-3", resultado="ok", erro="falhou")
        self.assertIn("erro", res1)

        # Nenhum preenchido
        res2 = ar.concluir(self.db, "req-3")
        self.assertIn("erro", res2)

    def test_idempotencia_toque_duplo(self):
        col = self.db.collection(ar.COLLECTION)
        col._docs["req-4"] = {
            "status": ar.STATUS_CONCLUIDO,
            "resultado": "Primeiro resultado gravado",
        }

        # Segunda tentativa não sobrescreve
        res = ar.concluir(self.db, "req-4", resultado="Segundo resultado que seria duplicado")
        self.assertEqual(res["status"], "already_decided")
        self.assertEqual(res["estado_atual"], ar.STATUS_CONCLUIDO)

        d = col.document("req-4").get().to_dict()
        self.assertEqual(d["resultado"], "Primeiro resultado gravado")

    def test_pedido_inexistente(self):
        res = ar.concluir(self.db, "req-inexistente", resultado="algo")
        self.assertEqual(res["status"], "not_found")


class TestListarEContar(unittest.TestCase):
    def setUp(self):
        self.db = _MockDB()
        col = self.db.collection(ar.COLLECTION)
        col._docs["r1"] = {
            "status": ar.STATUS_PENDENTE,
            "tipo": ar.TIPO_CONSOLIDAR_AUDIO,
            "criado_em": datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc),
        }
        col._docs["r2"] = {
            "status": ar.STATUS_PENDENTE,
            "tipo": "outro_tipo",
            "criado_em": datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc),
        }
        col._docs["r3"] = {
            "status": ar.STATUS_CONCLUIDO,
            "tipo": ar.TIPO_CONSOLIDAR_AUDIO,
            "criado_em": datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc),
        }

    def test_listar_pendentes_ordenado(self):
        res = ar.listar_pendentes(self.db)
        self.assertEqual(res["total"], 2)
        # Mais antigo primeiro: r2 (9h) antes de r1 (10h)
        self.assertEqual(res["pedidos"][0]["id"], "r2")
        self.assertEqual(res["pedidos"][1]["id"], "r1")

    def test_listar_pendentes_com_filtro_tipo(self):
        res = ar.listar_pendentes(self.db, tipo=ar.TIPO_CONSOLIDAR_AUDIO)
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["pedidos"][0]["id"], "r1")

    def test_contar_pendentes(self):
        self.assertEqual(ar.contar_pendentes(self.db), 2)
        self.assertEqual(ar.contar_pendentes(self.db, tipo=ar.TIPO_CONSOLIDAR_AUDIO), 1)


if __name__ == "__main__":
    unittest.main()
