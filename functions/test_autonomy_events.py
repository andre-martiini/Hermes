"""Testes de `autonomy/events.py` — só lógica pura, sem I/O (P05 sub-entrega
1/N: passos 1-2 do pacote, "Definir envelope único..." e "Manter fonte
original e produzir evento com ID determinístico").

Cobre: determinismo de `calcular_event_id` (mesma entrada -> mesmo ID,
qualquer campo diferente -> ID diferente), consistência forçada entre
`EventEnvelope.event_id` e seus próprios campos, exigência de datetime
timezone-aware, e o catálogo de `CategoriaEvento` (as 8 categorias do passo
1, verbatim).
"""

import unittest
from datetime import datetime, timezone

from autonomy.events import (
    CategoriaEvento,
    EventEnvelope,
    calcular_event_id,
    montar_evento,
)

_AGORA = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)
_ANTES = datetime(2026, 9, 28, 11, 55, 0, tzinfo=timezone.utc)


class TestCategoriaEvento(unittest.TestCase):
    def test_oito_categorias_do_passo_1_do_pacote(self):
        # "mensagens, agenda, tarefa, documento, SIPAC, transcrição,
        # finanças e eventos de repositório já suportados" -- 8 categorias.
        self.assertEqual(len(CategoriaEvento), 8)
        valores = {c.value for c in CategoriaEvento}
        self.assertEqual(
            valores,
            {
                "mensagem",
                "agenda",
                "tarefa",
                "documento",
                "sipac",
                "transcricao",
                "financas",
                "repositorio",
            },
        )


class TestCalcularEventId(unittest.TestCase):
    def test_e_deterministico(self):
        id1 = calcular_event_id(
            CategoriaEvento.MENSAGEM, "whatsapp_messages", "msg-1", {"texto": "oi"}
        )
        id2 = calcular_event_id(
            CategoriaEvento.MENSAGEM, "whatsapp_messages", "msg-1", {"texto": "oi"}
        )
        self.assertEqual(id1, id2)

    def test_ordem_das_chaves_do_payload_nao_importa(self):
        # hash_canonico já ordena chaves -- este teste garante que
        # calcular_event_id não reintroduz sensibilidade à ordem por cima.
        id1 = calcular_event_id(
            CategoriaEvento.TAREFA, "tarefas", "t-1", {"a": 1, "b": 2}
        )
        id2 = calcular_event_id(
            CategoriaEvento.TAREFA, "tarefas", "t-1", {"b": 2, "a": 1}
        )
        self.assertEqual(id1, id2)

    def test_categoria_diferente_muda_o_id(self):
        base = calcular_event_id(CategoriaEvento.TAREFA, "col", "doc-1", {"x": 1})
        outro = calcular_event_id(CategoriaEvento.AGENDA, "col", "doc-1", {"x": 1})
        self.assertNotEqual(base, outro)

    def test_fonte_colecao_diferente_muda_o_id(self):
        base = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "doc-1", {"x": 1})
        outro = calcular_event_id(CategoriaEvento.TAREFA, "outras_tarefas", "doc-1", {"x": 1})
        self.assertNotEqual(base, outro)

    def test_fonte_doc_id_diferente_muda_o_id(self):
        base = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "doc-1", {"x": 1})
        outro = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "doc-2", {"x": 1})
        self.assertNotEqual(base, outro)

    def test_payload_diferente_muda_o_id(self):
        base = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "doc-1", {"x": 1})
        outro = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "doc-1", {"x": 2})
        self.assertNotEqual(base, outro)

    def test_payload_vazio_nao_quebra(self):
        # Payload vazio é uma decisão legítima de quem chama (ver docstring
        # de calcular_event_id) -- não deste módulo impor não-vacuidade.
        event_id = calcular_event_id(CategoriaEvento.REPOSITORIO, "col", "doc-1", {})
        self.assertIsInstance(event_id, str)
        self.assertTrue(event_id)

    def test_payload_nao_serializavel_levanta_typeerror(self):
        class NaoSerializavel:
            pass

        with self.assertRaises(TypeError):
            calcular_event_id(
                CategoriaEvento.DOCUMENTO, "col", "doc-1", {"x": NaoSerializavel()}
            )


class TestMontarEvento(unittest.TestCase):
    def test_event_id_bate_com_calcular_event_id(self):
        evento = montar_evento(
            categoria=CategoriaEvento.SIPAC,
            fonte_colecao="sipac_processos",
            fonte_doc_id="proc-123",
            payload_identificador={"status": "tramitando"},
            occurred_at=_ANTES,
            ingested_at=_AGORA,
        )
        esperado = calcular_event_id(
            CategoriaEvento.SIPAC, "sipac_processos", "proc-123", {"status": "tramitando"}
        )
        self.assertEqual(evento.event_id, esperado)

    def test_occurred_at_e_ingested_at_preservados_distintos(self):
        evento = montar_evento(
            categoria=CategoriaEvento.TRANSCRICAO,
            fonte_colecao="transcricoes",
            fonte_doc_id="t-1",
            payload_identificador={"resumo": "x"},
            occurred_at=_ANTES,
            ingested_at=_AGORA,
        )
        self.assertEqual(evento.occurred_at, _ANTES)
        self.assertEqual(evento.ingested_at, _AGORA)
        self.assertNotEqual(evento.occurred_at, evento.ingested_at)

    def test_metadata_default_e_dict_vazio(self):
        evento = montar_evento(
            categoria=CategoriaEvento.FINANCAS,
            fonte_colecao="financas",
            fonte_doc_id="f-1",
            payload_identificador={"valor": 10},
            occurred_at=_ANTES,
            ingested_at=_AGORA,
        )
        self.assertEqual(evento.metadata, {})

    def test_metadata_nao_entra_no_calculo_do_event_id(self):
        # metadata é auxiliar, não identidade -- dois eventos com o mesmo
        # payload_identificador mas metadata diferente têm o MESMO event_id.
        evento1 = montar_evento(
            categoria=CategoriaEvento.AGENDA,
            fonte_colecao="agenda",
            fonte_doc_id="ev-1",
            payload_identificador={"titulo": "reunião"},
            occurred_at=_ANTES,
            ingested_at=_AGORA,
            metadata={"origem": "sync-1"},
        )
        evento2 = montar_evento(
            categoria=CategoriaEvento.AGENDA,
            fonte_colecao="agenda",
            fonte_doc_id="ev-1",
            payload_identificador={"titulo": "reunião"},
            occurred_at=_ANTES,
            ingested_at=_AGORA,
            metadata={"origem": "sync-2"},
        )
        self.assertEqual(evento1.event_id, evento2.event_id)


class TestEventEnvelopePostInit(unittest.TestCase):
    def _evento_valido_kwargs(self):
        payload = {"x": 1}
        return dict(
            event_id=calcular_event_id(CategoriaEvento.MENSAGEM, "col", "doc-1", payload),
            categoria=CategoriaEvento.MENSAGEM,
            fonte_colecao="col",
            fonte_doc_id="doc-1",
            occurred_at=_ANTES,
            ingested_at=_AGORA,
            payload_identificador=payload,
        )

    def test_construcao_direta_com_event_id_correto_funciona(self):
        EventEnvelope(**self._evento_valido_kwargs())  # não deve levantar

    def test_event_id_incompativel_levanta_valueerror(self):
        kwargs = self._evento_valido_kwargs()
        kwargs["event_id"] = "hash-forjado-que-nao-bate"
        with self.assertRaises(ValueError):
            EventEnvelope(**kwargs)

    def test_fonte_colecao_vazia_levanta_valueerror(self):
        kwargs = self._evento_valido_kwargs()
        kwargs["fonte_colecao"] = "   "
        with self.assertRaises(ValueError):
            EventEnvelope(**kwargs)

    def test_fonte_doc_id_vazio_levanta_valueerror(self):
        kwargs = self._evento_valido_kwargs()
        kwargs["fonte_doc_id"] = ""
        with self.assertRaises(ValueError):
            EventEnvelope(**kwargs)

    def test_occurred_at_naive_levanta_valueerror(self):
        kwargs = self._evento_valido_kwargs()
        kwargs["occurred_at"] = datetime(2026, 9, 28, 11, 0, 0)  # sem tzinfo
        with self.assertRaises(ValueError):
            EventEnvelope(**kwargs)

    def test_ingested_at_naive_levanta_valueerror(self):
        kwargs = self._evento_valido_kwargs()
        kwargs["ingested_at"] = datetime(2026, 9, 28, 12, 0, 0)  # sem tzinfo
        with self.assertRaises(ValueError):
            EventEnvelope(**kwargs)

    def test_envelope_e_frozen(self):
        evento = EventEnvelope(**self._evento_valido_kwargs())
        with self.assertRaises(Exception):
            evento.fonte_doc_id = "outro"


if __name__ == "__main__":
    unittest.main()
