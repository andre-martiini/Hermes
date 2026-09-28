"""Testes de `autonomy/events.py` — só lógica pura, sem I/O (P05 sub-entrega
1/N: passos 1-2 do pacote, "Definir envelope único..." e "Manter fonte
original e produzir evento com ID determinístico").

Cobre: determinismo de `calcular_event_id` (mesma entrada -> mesmo ID,
qualquer campo diferente -> ID diferente, incluindo occurred_at),
consistência forçada entre `EventEnvelope.event_id` e seus próprios campos,
exigência de datetime timezone-aware, e o catálogo de `CategoriaEvento` (as
8 categorias do passo 1, verbatim).
"""

import unittest
from datetime import datetime, timedelta, timezone

from autonomy.events import (
    CategoriaEvento,
    EventEnvelope,
    calcular_event_id,
    montar_evento,
)

_AGORA = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)
_ANTES = datetime(2026, 9, 28, 11, 55, 0, tzinfo=timezone.utc)
_DEPOIS = datetime(2026, 9, 28, 13, 30, 0, tzinfo=timezone.utc)


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
            CategoriaEvento.MENSAGEM, "whatsapp_messages", "msg-1", {"texto": "oi"}, _ANTES
        )
        id2 = calcular_event_id(
            CategoriaEvento.MENSAGEM, "whatsapp_messages", "msg-1", {"texto": "oi"}, _ANTES
        )
        self.assertEqual(id1, id2)

    def test_ordem_das_chaves_do_payload_nao_importa(self):
        # hash_canonico já ordena chaves -- este teste garante que
        # calcular_event_id não reintroduz sensibilidade à ordem por cima.
        id1 = calcular_event_id(
            CategoriaEvento.TAREFA, "tarefas", "t-1", {"a": 1, "b": 2}, _ANTES
        )
        id2 = calcular_event_id(
            CategoriaEvento.TAREFA, "tarefas", "t-1", {"b": 2, "a": 1}, _ANTES
        )
        self.assertEqual(id1, id2)

    def test_categoria_diferente_muda_o_id(self):
        base = calcular_event_id(CategoriaEvento.TAREFA, "col", "doc-1", {"x": 1}, _ANTES)
        outro = calcular_event_id(CategoriaEvento.AGENDA, "col", "doc-1", {"x": 1}, _ANTES)
        self.assertNotEqual(base, outro)

    def test_fonte_colecao_diferente_muda_o_id(self):
        base = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "doc-1", {"x": 1}, _ANTES)
        outro = calcular_event_id(
            CategoriaEvento.TAREFA, "outras_tarefas", "doc-1", {"x": 1}, _ANTES
        )
        self.assertNotEqual(base, outro)

    def test_fonte_doc_id_diferente_muda_o_id(self):
        base = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "doc-1", {"x": 1}, _ANTES)
        outro = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "doc-2", {"x": 1}, _ANTES)
        self.assertNotEqual(base, outro)

    def test_payload_diferente_muda_o_id(self):
        base = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "doc-1", {"x": 1}, _ANTES)
        outro = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "doc-1", {"x": 2}, _ANTES)
        self.assertNotEqual(base, outro)

    def test_occurred_at_diferente_muda_o_id(self):
        # Achado real de revisão automática do Codex (P2) na PR #373: uma
        # fonte mutável que revisita o MESMO payload_identificador (ex.:
        # tarefa que volta a um status anterior) precisa produzir um
        # event_id DIFERENTE quando a ocorrência é genuinamente outra --
        # occurred_at é o que distingue as duas nesse cenário.
        base = calcular_event_id(
            CategoriaEvento.TAREFA, "tarefas", "t-1", {"status": "em_andamento"}, _ANTES
        )
        outro = calcular_event_id(
            CategoriaEvento.TAREFA, "tarefas", "t-1", {"status": "em_andamento"}, _DEPOIS
        )
        self.assertNotEqual(base, outro)

    def test_mesmo_occurred_at_preserva_dedup_de_reentrega(self):
        # O reverso do teste acima: uma REENTREGA de verdade do MESMO
        # evento de origem (mesmo occurred_at, porque é a mesma ocorrência
        # no mundo real) continua produzindo o MESMO event_id -- a garantia
        # de dedup por reentrega (passo 4) não foi enfraquecida pela
        # correção do achado do Codex.
        id1 = calcular_event_id(
            CategoriaEvento.TAREFA, "tarefas", "t-1", {"status": "em_andamento"}, _ANTES
        )
        id2 = calcular_event_id(
            CategoriaEvento.TAREFA, "tarefas", "t-1", {"status": "em_andamento"}, _ANTES
        )
        self.assertEqual(id1, id2)

    def test_mesmo_instante_com_offsets_diferentes_produz_mesmo_id(self):
        # Achado real de revisão adversarial sobre a correção do achado do
        # Codex: datetime.isoformat() cru preserva o offset original, então
        # o MESMO instante real representado com offsets diferentes
        # (ex.: horário local +02:00 vs. UTC) produzia hashes diferentes --
        # quebraria dedup de reentrega para uma fonte que não normaliza
        # sempre para o mesmo offset. occurred_at precisa ser normalizado
        # para UTC antes de entrar no hash.
        em_utc = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)
        mesmo_instante_offset_2 = datetime(
            2026, 9, 28, 14, 0, 0, tzinfo=timezone(timedelta(hours=2))
        )
        self.assertEqual(em_utc, mesmo_instante_offset_2)  # mesmo instante real
        self.assertNotEqual(em_utc.isoformat(), mesmo_instante_offset_2.isoformat())

        id1 = calcular_event_id(CategoriaEvento.TAREFA, "tarefas", "t-1", {"x": 1}, em_utc)
        id2 = calcular_event_id(
            CategoriaEvento.TAREFA, "tarefas", "t-1", {"x": 1}, mesmo_instante_offset_2
        )
        self.assertEqual(id1, id2)

    def test_payload_vazio_nao_quebra(self):
        # Payload vazio é uma decisão legítima de quem chama (ver docstring
        # de calcular_event_id) -- não deste módulo impor não-vacuidade.
        event_id = calcular_event_id(CategoriaEvento.REPOSITORIO, "col", "doc-1", {}, _ANTES)
        self.assertIsInstance(event_id, str)
        self.assertTrue(event_id)

    def test_payload_nao_serializavel_levanta_typeerror(self):
        class NaoSerializavel:
            pass

        with self.assertRaises(TypeError):
            calcular_event_id(
                CategoriaEvento.DOCUMENTO, "col", "doc-1", {"x": NaoSerializavel()}, _ANTES
            )

    def test_occurred_at_naive_levanta_valueerror(self):
        with self.assertRaises(ValueError):
            calcular_event_id(
                CategoriaEvento.DOCUMENTO,
                "col",
                "doc-1",
                {"x": 1},
                datetime(2026, 9, 28, 11, 0, 0),  # sem tzinfo
            )

    def test_dois_pontos_em_fonte_colecao_nao_colide_com_fonte_doc_id_vizinho(self):
        # Achado real da 1a rodada de revisão adversarial: concatenar
        # fonte_colecao/fonte_doc_id com ":" faz um ":" DENTRO de um dos dois
        # campos deslocar a fronteira e colidir com o campo vizinho. Ambos os
        # pares abaixo são fontes logicamente DISTINTAS e devem produzir
        # event_id DIFERENTE.
        id1 = calcular_event_id(
            CategoriaEvento.MENSAGEM, "whatsapp", "messages:msg-1", {"x": 1}, _ANTES
        )
        id2 = calcular_event_id(
            CategoriaEvento.MENSAGEM, "whatsapp:messages", "msg-1", {"x": 1}, _ANTES
        )
        self.assertNotEqual(id1, id2)


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
            CategoriaEvento.SIPAC,
            "sipac_processos",
            "proc-123",
            {"status": "tramitando"},
            _ANTES,
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

    def test_ingested_at_diferente_nao_muda_event_id(self):
        # ingested_at é "quando ESTE processo viu o evento" -- varia a cada
        # reprocessamento/replay do MESMO evento de origem, então não pode
        # participar da identidade (ao contrário de occurred_at).
        evento1 = montar_evento(
            categoria=CategoriaEvento.TAREFA,
            fonte_colecao="tarefas",
            fonte_doc_id="t-9",
            payload_identificador={"status": "concluida"},
            occurred_at=_ANTES,
            ingested_at=_AGORA,
        )
        evento2 = montar_evento(
            categoria=CategoriaEvento.TAREFA,
            fonte_colecao="tarefas",
            fonte_doc_id="t-9",
            payload_identificador={"status": "concluida"},
            occurred_at=_ANTES,
            ingested_at=_DEPOIS,
        )
        self.assertEqual(evento1.event_id, evento2.event_id)

    def test_tarefa_que_volta_a_status_anterior_produz_event_id_diferente(self):
        # Cenário exato do achado do Codex: mesma tarefa, mesmo status,
        # revisitado numa ocorrência posterior genuinamente diferente.
        primeira_ocorrencia = montar_evento(
            categoria=CategoriaEvento.TAREFA,
            fonte_colecao="tarefas",
            fonte_doc_id="t-42",
            payload_identificador={"status": "em_andamento"},
            occurred_at=_ANTES,
            ingested_at=_ANTES,
        )
        segunda_ocorrencia = montar_evento(
            categoria=CategoriaEvento.TAREFA,
            fonte_colecao="tarefas",
            fonte_doc_id="t-42",
            payload_identificador={"status": "em_andamento"},
            occurred_at=_DEPOIS,
            ingested_at=_DEPOIS,
        )
        self.assertNotEqual(primeira_ocorrencia.event_id, segunda_ocorrencia.event_id)


class TestEventEnvelopePostInit(unittest.TestCase):
    def _evento_valido_kwargs(self):
        payload = {"x": 1}
        return dict(
            event_id=calcular_event_id(
                CategoriaEvento.MENSAGEM, "col", "doc-1", payload, _ANTES
            ),
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

    def test_event_id_calculado_com_occurred_at_diferente_e_rejeitado(self):
        # event_id calculado para _DEPOIS, mas o envelope construído com
        # occurred_at=_ANTES -- __post_init__ precisa recalcular usando o
        # occurred_at DO ENVELOPE, não aceitar qualquer hash bem-formado.
        kwargs = self._evento_valido_kwargs()
        kwargs["event_id"] = calcular_event_id(
            CategoriaEvento.MENSAGEM, "col", "doc-1", {"x": 1}, _DEPOIS
        )
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

    def test_payload_identificador_congelado_nao_aceita_mutacao_direta(self):
        # Achado real da 1a rodada de revisão adversarial: frozen=True só
        # impede reatribuir o ATRIBUTO, não mutar o dict que ele aponta.
        # payload_identificador precisa ser um tipo que RECUSA
        # item-assignment (MappingProxyType), não só "seja um dict que a
        # gente promete não mutar".
        evento = EventEnvelope(**self._evento_valido_kwargs())
        with self.assertRaises(TypeError):
            evento.payload_identificador["x"] = 999

    def test_mutar_dict_do_chamador_depois_de_montar_evento_nao_afeta_envelope(self):
        payload_do_chamador = {"y": 1}
        evento = montar_evento(
            categoria=CategoriaEvento.TAREFA,
            fonte_colecao="tarefas",
            fonte_doc_id="t-1",
            payload_identificador=payload_do_chamador,
            occurred_at=_ANTES,
            ingested_at=_AGORA,
        )
        payload_do_chamador["y"] = 999
        payload_do_chamador["novo"] = "vazamento"
        self.assertEqual(dict(evento.payload_identificador), {"y": 1})
        # A garantia central do módulo continua válida mesmo após a
        # tentativa de mutação externa.
        self.assertEqual(
            evento.event_id,
            calcular_event_id(
                CategoriaEvento.TAREFA,
                "tarefas",
                "t-1",
                evento.payload_identificador,
                evento.occurred_at,
            ),
        )

    def test_mutar_dict_aninhado_do_chamador_nao_vaza_para_o_envelope(self):
        # Cópia rasa (dict(payload_identificador)) não bastaria aqui -- um
        # dict ANINHADO dentro do payload continuaria compartilhado com o
        # chamador. _snapshot_json precisa congelar recursivamente.
        aninhado = {"inner": 1}
        payload_do_chamador = {"a": aninhado}
        evento = montar_evento(
            categoria=CategoriaEvento.DOCUMENTO,
            fonte_colecao="conhecimento",
            fonte_doc_id="doc-1",
            payload_identificador=payload_do_chamador,
            occurred_at=_ANTES,
            ingested_at=_AGORA,
        )
        aninhado["inner"] = 999
        self.assertEqual(dict(evento.payload_identificador["a"]), {"inner": 1})


if __name__ == "__main__":
    unittest.main()
