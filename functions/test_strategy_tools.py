"""Testes unitários para o CRUD de objetivos estratégicos (functions/strategy_tools.py).

Este módulo não tinha NENHUM teste dedicado antes desta sub-entrega (P03
sub-entrega 18/N, idempotentHint por handler) -- os testes abaixo cobrem
especificamente as duas classificações novas de `criar_objetivo_estrategico`
(NAO_IDEMPOTENTE) e `editar_objetivo_estrategico` (IDEMPOTENTE), com uma
prova por handler real, não só leitura de código (ver `tools/inventory.py`
para a evidência completa de cada classificação).
"""

from __future__ import annotations

import unittest

from firebase_admin import firestore

import strategy_tools as st


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
        return _MockDocSnap(self.id, self.col._docs.get(self.id))

    def set(self, data, merge=False):
        if merge and self.id in self.col._docs:
            self.col._docs[self.id].update(data)
        else:
            self.col._docs[self.id] = dict(data)

    def update(self, data):
        if self.id not in self.col._docs:
            self.col._docs[self.id] = {}
        self.col._docs[self.id].update(data)

    def delete(self):
        self.col._docs.pop(self.id, None)


class _MockCollection:
    def __init__(self, name: str):
        self.name = name
        self._docs: dict[str, dict] = {}
        self._id_counter = 1

    def document(self, doc_id: str | None = None):
        if not doc_id:
            doc_id = f"mock-doc-{self._id_counter}"
            self._id_counter += 1
        return _MockDocRef(self, doc_id)


class _MockDb:
    def __init__(self):
        self._cols: dict[str, _MockCollection] = {}

    def collection(self, name: str):
        if name not in self._cols:
            self._cols[name] = _MockCollection(name)
        return self._cols[name]


class TestCriarObjetivoEstrategicoNaoIdempotente(unittest.TestCase):
    """NAO_IDEMPOTENTE (P03 sub-entrega 18/N): `ref = db.collection(...).document()`
    (ID automático) -- repetir a MESMA chamada cria um SEGUNDO objetivo, nunca
    devolve o já existente."""

    def setUp(self):
        self.db = _MockDb()

    def test_repetir_mesma_chamada_cria_dois_objetivos_distintos(self):
        args = dict(
            db=self.db, user_uid="uid-1", objetivoMacro="Aprender espanhol",
            pilar="intelectual", diretrizes=["praticar 20min/dia"],
        )
        res1 = st.criar_objetivo_estrategico(**args)
        res2 = st.criar_objetivo_estrategico(**args)

        self.assertEqual(res1["status"], "created")
        self.assertEqual(res2["status"], "created")
        self.assertNotEqual(res1["objetivo_id"], res2["objetivo_id"])
        self.assertEqual(len(self.db.collection("estrategia_pessoal")._docs), 2)


class TestEditarObjetivoEstrategicoIdempotente(unittest.TestCase):
    """IDEMPOTENTE (P03 sub-entrega 18/N): `ref.update(updates)` recomputa os
    mesmos valores de negócio a partir dos mesmos argumentos -- repetir não
    tem efeito adicional (fora o timestamp, inerte, não lido por decisão
    nenhuma)."""

    def setUp(self):
        self.db = _MockDb()
        self.objetivo_id = "obj-1"
        self.db.collection("estrategia_pessoal").document(self.objetivo_id).set({
            "userId": "uid-1",
            "pilar": "carreira",
            "objetivoMacro": "Título original",
            "tipoMeta": "relativa_qualitativa",
            "status": "ativo",
            "diretrizesDerivadas": ["diretriz A"],
            "indicadoresSucesso": [],
            "marcos": [],
        })

    def test_repetir_mesma_edicao_produz_os_mesmos_valores_de_negocio(self):
        args = dict(
            db=self.db, user_uid="uid-1", objetivo_id=self.objetivo_id,
            objetivoMacro="Título revisado", status="revisar",
        )
        res1 = st.editar_objetivo_estrategico(**args)
        doc_apos_1 = self.db.collection("estrategia_pessoal").document(self.objetivo_id).get().to_dict()

        res2 = st.editar_objetivo_estrategico(**args)
        doc_apos_2 = self.db.collection("estrategia_pessoal").document(self.objetivo_id).get().to_dict()

        self.assertEqual(res1["status"], "updated")
        self.assertEqual(res2["status"], "updated")
        self.assertEqual(sorted(res1["campos_alterados"]), sorted(res2["campos_alterados"]))
        # Compara os valores de negócio (exclui `timestamp`, o único campo que
        # muda a cada chamada -- inerte, ver nota da classificação).
        for campo in ("objetivoMacro", "status", "pilar", "diretrizesDerivadas"):
            self.assertEqual(doc_apos_1[campo], doc_apos_2[campo])

    def test_repetir_nao_acumula_nem_duplica_diretrizes(self):
        args = dict(
            db=self.db, user_uid="uid-1", objetivo_id=self.objetivo_id,
            diretrizes=["diretriz X", "diretriz Y"],
        )
        st.editar_objetivo_estrategico(**args)
        st.editar_objetivo_estrategico(**args)
        doc = self.db.collection("estrategia_pessoal").document(self.objetivo_id).get().to_dict()
        self.assertEqual(doc["diretrizesDerivadas"], ["diretriz X", "diretriz Y"])


if __name__ == "__main__":
    unittest.main()
