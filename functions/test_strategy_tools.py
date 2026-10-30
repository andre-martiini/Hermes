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

    def where(self, campo, op, valor):
        assert op == "=="
        filtrado = _MockCollection(self.name)
        filtrado._docs = {k: v for k, v in self._docs.items() if v.get(campo) == valor}
        return filtrado

    def stream(self):
        return [_MockDocSnap(k, v) for k, v in self._docs.items()]


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


def _objetivo_com_marcos():
    return {
        "userId": "uid-1", "objetivoMacro": "Saúde", "pilar": "saude", "status": "ativo",
        "tipoMeta": "absoluta", "diretrizesDerivadas": ["d"],
        "metricaAlvo": {"valorInicial": 93.4, "valorAtual": 93.4, "valorObjetivo": 88, "unidade": "kg", "fonte": "peso"},
        "marcos": [
            "Marco legado em texto",
            {"id": "m1", "descricao": "91,7 kg", "concluido": False, "registros": [],
             "dataAlvo": "2026-11-30", "esperado": {"peso": 91.7, "cintura": 108}, "campo_futuro": "não some"},
        ],
    }


class TestItemPreservaCamposDoPerfil(unittest.TestCase):
    """A2: recompor o marco só com os campos antigos apagava `dataAlvo` e `esperado`."""

    def _m1(self, lista):
        return next(m for m in lista if m["id"] == "m1")

    def test_editar_concluir_e_adicionar_outro_nao_apagam_data_alvo_nem_esperado(self):
        data = _objetivo_com_marcos()
        for acao, extra in (("editar", {"descricao": "91,7 kg (revisto)"}), ("concluir", {})):
            lista, r = st.aplicar_item(data, "marco", acao, item_id="m1", **extra)
            m1 = self._m1(lista)
            self.assertEqual((m1["dataAlvo"], m1["esperado"], m1["campo_futuro"]),
                             ("2026-11-30", {"peso": 91.7, "cintura": 108}, "não some"), acao)
        lista, _ = st.aplicar_item(data, "marco", "adicionar", descricao="Outro")
        self.assertEqual(self._m1(lista)["esperado"], {"peso": 91.7, "cintura": 108})

    def test_adicionar_e_editar_aceitam_data_alvo_e_esperado(self):
        data = _objetivo_com_marcos()
        lista, r = st.aplicar_item(data, "marco", "adicionar", descricao="89,9 kg", dataAlvo="2026-12-30",
                                   esperado={"peso": "89.9", "cintura": 106})
        novo = next(m for m in lista if m["id"] == r["item_id"])
        self.assertEqual((novo["dataAlvo"], novo["esperado"]), ("2026-12-30", {"peso": 89.9, "cintura": 106.0}))

        lista, _ = st.aplicar_item(data, "marco", "editar", item_id="m1", dataAlvo="2026-12-01")
        self.assertEqual((self._m1(lista)["dataAlvo"], self._m1(lista)["descricao"]), ("2026-12-01", "91,7 kg"))
        lista, _ = st.aplicar_item(data, "marco", "editar", item_id="m1", dataAlvo="", esperado={})
        self.assertNotIn("dataAlvo", self._m1(lista))
        self.assertNotIn("esperado", self._m1(lista))

    def test_valores_invalidos_sao_recusados_sem_gravar(self):
        data = _objetivo_com_marcos()
        for extra, motivo in (({"dataAlvo": "30/11/2026"}, "dataAlvo_invalida"),
                              ({"dataAlvo": "2026-02-30"}, "dataAlvo_invalida"),
                              ({"esperado": {"peso": "abc"}}, "esperado_invalido"),
                              ({"esperado": [91.7]}, "esperado_invalido"),
                              ({}, "nada_para_editar")):
            lista, r = st.aplicar_item(data, "marco", "editar", item_id="m1", **extra)
            self.assertIsNone(lista)
            self.assertEqual(r["reason"], motivo)
        lista, r = st.aplicar_item(data, "indicador", "adicionar", descricao="x", dataAlvo="2026-11-30")
        self.assertEqual((lista, r["reason"]), (None, "dataAlvo_e_esperado_so_em_marco"))

    def test_editar_esperado_mescla_por_indicador(self):
        lista, _ = st.aplicar_item(_objetivo_com_marcos(), "marco", "editar", item_id="m1", esperado={"peso": 91.5})
        self.assertEqual(self._m1(lista)["esperado"], {"peso": 91.5, "cintura": 108})

    def test_indicador_aceita_data_e_esperado_vazios_como_nao_enviados(self):
        data = {**_objetivo_com_marcos(), "indicadoresSucesso": [{"id": "i1", "descricao": "a", "concluido": False}]}
        lista, r = st.aplicar_item(data, "indicador", "editar", item_id="i1", descricao="b", dataAlvo="", esperado={})
        self.assertEqual((lista[0]["descricao"], "dataAlvo" in lista[0]), ("b", False))

    def test_id_legado_de_descricao_que_nao_e_texto_bate_com_a_tela(self):
        # Só texto entra no hash; a tela (itensEstrategia.ts) faz o mesmo.
        self.assertEqual(st.normalizar_item({"descricao": 1.0}, "marco", 0)["id"], st.id_legado("marco", 0, ""))

    def test_marco_legado_tem_id_estavel_e_editavel(self):
        data = _objetivo_com_marcos()
        id_lido = st.normalizar_item(data["marcos"][0], "marco", 0)["id"]
        self.assertEqual(id_lido, st.normalizar_item(data["marcos"][0], "marco", 0)["id"])
        lista, r = st.aplicar_item(data, "marco", "editar", item_id=id_lido, dataAlvo="2026-11-30")
        self.assertEqual((lista[0]["id"], lista[0]["dataAlvo"]), (id_lido, "2026-11-30"))
        # Depois de gravado, o legado vira dict com o MESMO id, e a leitura seguinte o acha.
        data["marcos"] = lista
        lista, r = st.aplicar_item(data, "marco", "remover", item_id=id_lido)
        self.assertEqual([m["id"] for m in lista], ["m1"])


class TestLeituraCompletaDoObjetivo(unittest.TestCase):
    """B1: o Claude precisa ver marcos com id, data alvo e esperado para conseguir editá-los."""

    def setUp(self):
        self.db = _MockDb()
        col = self.db.collection("estrategia_pessoal")
        col.document("saude").set(_objetivo_com_marcos())
        col.document("alheio").set({**_objetivo_com_marcos(), "userId": "outro"})
        col.document("mago").set({"userId": "uid-1", "objetivoMacro": "MAGO", "pilar": "carreira",
                                  "status": "revisar", "marcos": []})

    def test_obter_devolve_tudo_com_ids_estaveis(self):
        r1 = st.obter_objetivo_estrategico(self.db, "uid-1", "saude")
        r2 = st.obter_objetivo_estrategico(self.db, "uid-1", "saude")
        obj = r1["objetivo"]
        self.assertEqual(obj["metricaAlvo"]["fonte"], "peso")
        self.assertEqual(obj["marcos"][1]["esperado"], {"peso": 91.7, "cintura": 108})
        self.assertEqual(obj["marcos"][0]["id"], r2["objetivo"]["marcos"][0]["id"])
        self.assertNotIn("userId", obj)

    def test_obter_e_listar_sao_fail_closed(self):
        self.assertEqual(st.obter_objetivo_estrategico(self.db, "uid-1", "alheio")["status"], "error")
        self.assertEqual(st.obter_objetivo_estrategico(self.db, None, "saude")["status"], "error")
        self.assertEqual(st.listar_objetivos_estrategicos(self.db, None)["status"], "error")
        ids = [o["id"] for o in st.listar_objetivos_estrategicos(self.db, "uid-1")["objetivos"]]
        self.assertEqual(sorted(ids), ["mago", "saude"])

    def test_listar_resumido_e_por_status(self):
        r = st.listar_objetivos_estrategicos(self.db, "uid-1", completo="false", status="ativo")  # texto, como o MCP manda
        self.assertEqual(r["objetivos"], [{"id": "saude", "objetivoMacro": "Saúde", "pilar": "saude",
                                          "status": "ativo", "marcos": 2, "marcos_concluidos": 0}])


if __name__ == "__main__":
    unittest.main()
