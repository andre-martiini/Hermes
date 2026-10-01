"""Testes do SEGUNDO escritor real do outbox de eventos (P05, passo 3 do
pacote): `email_action_linker.py::_montar_evento_outbox_sugestao`, usada por
`queue_and_maybe_send_suggestion` (ponto de entrada compartilhado de todos os
produtores de sinal -- SIPAC, Calendar, WhatsApp, Monitor de Páginas) para
emitir um evento junto com a gravação da sugestão nova, na mesma transação
Firestore (`event_outbox.registrar_evento_outbox_transacional`, já coberto
por test_event_outbox.py). O primeiro escritor foi o digest de WhatsApp
(whatsapp_ingest.py, P05 sub-entrega 6/N; ver test_whatsapp_ingest_outbox.py
para o mesmo padrão de teste da função pura de montagem).

Três classes de teste:
- `TestMontarEventoOutboxSugestao`: só a função pura (sem Firestore).
- `TestQueueAndMaybeSendSuggestionEmiteEvento`: ponta a ponta com
  `MockDb`/`MockTransaction` (test_atencao.py, estendido nesta sub-entrega
  para suportar o protocolo de transação que `@firestore.transactional`
  exige) -- confirma que a sugestão nova E a entrada de outbox são gravadas
  juntas para os canais mapeados, e que um canal sem categoria (ex. "pagina")
  continua gravando só a sugestão, exatamente como antes desta sub-entrega.
- `TestGravarSugestaoSeAindaNaoExiste`/`TestCorridaDeCriacaoDetectada`: achado
  real de revisão automática do Codex (PR #398) sobre a 1a versão desta
  sub-entrega -- sem reler `doc_ref` DENTRO da transação, 2 chamadas
  concorrentes para o MESMO `suggestion_id` novo podiam ambas commitar,
  gravando 2 entradas de outbox para a mesma sugestão (pior do que o
  `doc_ref.set()` direto de antes, que era só last-write-wins sem
  bookkeeping duplicado). Ver `_gravar_sugestao_se_ainda_nao_existe` em
  email_action_linker.py para o design da correção.
"""

import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, '.')

from test_atencao import MockDb

import email_action_linker
from autonomy.events import CategoriaEvento
from email_action_linker import (
    _SugestaoJaExistenteError,
    _gravar_sugestao_se_ainda_nao_existe,
    _montar_evento_outbox_sugestao,
    queue_and_maybe_send_suggestion,
)

_AGORA = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
TASK = {"id": "task-1", "titulo": "Processo X", "status": "em_andamento", "is_standby": False}


class TestMontarEventoOutboxSugestao(unittest.TestCase):
    def test_canal_sem_categoria_mapeada_devolve_none(self):
        evento = _montar_evento_outbox_sugestao("pagina_1", "pagina", TASK, "Página X", "", _AGORA)
        self.assertIsNone(evento)

    def test_canal_sipac_usa_categoria_sipac(self):
        evento = _montar_evento_outbox_sugestao("sipac_123", "sipac", TASK, "Processo 123", "", _AGORA)
        self.assertEqual(evento.categoria, CategoriaEvento.SIPAC)

    def test_canal_calendar_usa_categoria_agenda(self):
        evento = _montar_evento_outbox_sugestao("calendar_evt-1", "calendar", TASK, "Reunião X", "", _AGORA)
        self.assertEqual(evento.categoria, CategoriaEvento.AGENDA)

    def test_canal_whatsapp_usa_categoria_mensagem(self):
        evento = _montar_evento_outbox_sugestao("whatsapp_digest-1", "whatsapp", TASK, "Chat X", "", _AGORA)
        self.assertEqual(evento.categoria, CategoriaEvento.MENSAGEM)

    def test_fonte_colecao_e_doc_id(self):
        evento = _montar_evento_outbox_sugestao("sipac_123", "sipac", TASK, "Processo 123", "", _AGORA)
        self.assertEqual(evento.fonte_colecao, "email_action_suggestions")
        self.assertEqual(evento.fonte_doc_id, "sipac_123")

    def test_payload_identificador_tem_task_id_e_titulo_sinal(self):
        evento = _montar_evento_outbox_sugestao("sipac_123", "sipac", TASK, "Processo 123", "", _AGORA)
        self.assertEqual(evento.payload_identificador["task_id"], "task-1")
        self.assertEqual(evento.payload_identificador["titulo_sinal"], "Processo 123")

    def test_metadata_tem_canal_e_origem_sinal(self):
        evento = _montar_evento_outbox_sugestao("sipac_123", "sipac", TASK, "Processo 123", "2 notificações", _AGORA)
        self.assertEqual(evento.metadata["canal"], "sipac")
        self.assertEqual(evento.metadata["origem_sinal"], "2 notificações")

    def test_occurred_at_e_ingested_at_usam_agora(self):
        evento = _montar_evento_outbox_sugestao("sipac_123", "sipac", TASK, "Processo 123", "", _AGORA)
        self.assertEqual(evento.occurred_at, _AGORA)
        self.assertEqual(evento.ingested_at, _AGORA)


class TestQueueAndMaybeSendSuggestionEmiteEvento(unittest.TestCase):
    def _call(self, canal, suggestion_id="sug-1"):
        db = MockDb({"email_action_suggestions": {}})
        queue_and_maybe_send_suggestion(
            db,
            suggestion_id,
            canal=canal,
            task=TASK,
            titulo_sinal="Sinal X",
        )
        return db

    def test_canal_sipac_grava_sugestao_e_entrada_de_outbox_juntas(self):
        db = self._call("sipac")
        suggestion_doc = db.collection("email_action_suggestions").document("sug-1")
        self.assertTrue(suggestion_doc.exists)
        outbox_docs = db.collection("outbox_eventos").docs
        self.assertEqual(len(outbox_docs), 1)
        self.assertEqual(outbox_docs[0].to_dict()["categoria"], "sipac")
        self.assertEqual(outbox_docs[0].to_dict()["fonte_doc_id"], "sug-1")

    def test_canal_calendar_grava_entrada_de_outbox(self):
        db = self._call("calendar")
        outbox_docs = db.collection("outbox_eventos").docs
        self.assertEqual(len(outbox_docs), 1)
        self.assertEqual(outbox_docs[0].to_dict()["categoria"], "agenda")

    def test_canal_whatsapp_grava_entrada_de_outbox(self):
        db = self._call("whatsapp")
        outbox_docs = db.collection("outbox_eventos").docs
        self.assertEqual(len(outbox_docs), 1)
        self.assertEqual(outbox_docs[0].to_dict()["categoria"], "mensagem")

    def test_canal_sem_categoria_mapeada_nao_grava_outbox(self):
        db = self._call("pagina")
        suggestion_doc = db.collection("email_action_suggestions").document("sug-1")
        self.assertTrue(suggestion_doc.exists, "a sugestão em si continua sendo gravada normalmente")
        outbox_docs = db.collection("outbox_eventos").docs
        self.assertEqual(outbox_docs, [], "canal sem categoria mapeada não deve gerar entrada de outbox")

    def test_reenvio_de_sugestao_existente_nao_gera_nova_entrada_de_outbox(self):
        db = MockDb({
            "email_action_suggestions": {
                "sug-1": {
                    "canal": "sipac",
                    "task_id": "task-1",
                    "status": "pending",
                    "telegram_sent": False,
                }
            }
        })
        queue_and_maybe_send_suggestion(
            db, "sug-1", canal="sipac", task=TASK, titulo_sinal="Sinal X",
        )
        outbox_docs = db.collection("outbox_eventos").docs
        self.assertEqual(outbox_docs, [], "doc já existente entra pelo ramo de reenvio, nunca monta evento novo")


class _FakeDocRefRace:
    """Double mínimo (sem MockDb inteiro) para testar `_gravar_sugestao_se_ainda_nao_existe`
    isoladamente -- só precisa de `.get(transaction=...)`/`.set(...)`."""

    def __init__(self, exists):
        self._exists = exists
        self.set_calls = []

    def get(self, transaction=None):
        return SimpleNamespace(exists=self._exists)

    def set(self, data, merge=False):
        self.set_calls.append(data)


class _FakeTransaction:
    def set(self, doc_ref, data, merge=False):
        doc_ref.set(data, merge=merge)


class TestGravarSugestaoSeAindaNaoExiste(unittest.TestCase):
    def test_grava_quando_doc_nao_existe(self):
        doc_ref = _FakeDocRefRace(exists=False)
        _gravar_sugestao_se_ainda_nao_existe(_FakeTransaction(), doc_ref, {"x": 1})
        self.assertEqual(doc_ref.set_calls, [{"x": 1}])

    def test_levanta_quando_doc_ja_existe_e_nao_grava(self):
        doc_ref = _FakeDocRefRace(exists=True)
        with self.assertRaises(_SugestaoJaExistenteError):
            _gravar_sugestao_se_ainda_nao_existe(_FakeTransaction(), doc_ref, {"x": 1})
        self.assertEqual(doc_ref.set_calls, [], "doc já existente não deve ser sobrescrito")


class TestCorridaDeCriacaoDetectada(unittest.TestCase):
    """Simula o cenário do achado do Codex (PR #398): a transação detecta
    (via `_gravar_sugestao_se_ainda_nao_existe`) que outra chamada
    concorrente já criou `suggestion_id` entre a checagem inicial (fora de
    transação) e a tentativa de commit. `MockTransaction` (test_atencao.py)
    não simula isolamento/contenção real do Firestore -- por isso o sinal é
    simulado diretamente (mock do ponto exato que detectaria a corrida em
    produção), em vez de 2 chamadas concorrentes de verdade."""

    def _simula_vencedora_e_corrida(self, transaction, doc_ref, base_doc):
        # Simula a transação concorrente que venceu a corrida: grava SEU
        # PRÓPRIO doc (conteúdo arbitrário, diferente do base_doc desta
        # chamada) diretamente no Firestore simulado, por fora desta
        # transação -- exatamente como a vencedora real teria feito.
        doc_ref.set({
            "canal": "sipac", "task_id": "task-1", "status": "pending", "telegram_sent": False,
        })
        raise _SugestaoJaExistenteError()

    def test_corrida_detectada_nao_sobrescreve_nem_duplica_outbox(self):
        db = MockDb({"email_action_suggestions": {}})
        with mock.patch(
            "email_action_linker._gravar_sugestao_se_ainda_nao_existe",
            side_effect=self._simula_vencedora_e_corrida,
        ):
            result = queue_and_maybe_send_suggestion(
                db, "sug-1", canal="sipac", task=TASK, titulo_sinal="Sinal X", chat_id=None,
            )

        self.assertEqual(result["status"], "pending")
        # `db.collection(COLECAO).document(event_id)` (dentro de registrar_evento_outbox_
        # transacional) cria um MockDoc PLACEHOLDER só por ser referenciado, mesmo sem
        # nenhum .set() -- ver MockQuery.document() em test_atencao.py. A asserção certa
        # é "nenhum doc de outbox EXISTE de verdade", não "a lista de docs está vazia".
        outbox_docs = db.collection("outbox_eventos").docs
        self.assertFalse(
            any(d.exists for d in outbox_docs),
            "transação abortada por _SugestaoJaExistenteError não deve gravar outbox de verdade",
        )
        suggestion_doc = db.collection("email_action_suggestions").document("sug-1")
        self.assertTrue(suggestion_doc.exists, "o doc da vencedora da corrida deve continuar gravado")

    def test_corrida_detectada_tenta_reenviar_telegram_se_ainda_pendente(self):
        """Se a vencedora da corrida ainda não confirmou telegram_sent (mesmo
        gap de falha parcial do achado do Codex na PR #385), a perdedora deve
        tentar reenviar o cartão sobre o doc da VENCEDORA -- mesmo
        comportamento de `_resultado_de_sugestao_existente` para qualquer
        outro caminho de "doc já existente"."""
        db = MockDb({"email_action_suggestions": {}})
        sent = []

        def send_fn(_db, chat_id, text, keyboard):
            sent.append((chat_id, text, keyboard))
            return True

        with mock.patch(
            "email_action_linker._gravar_sugestao_se_ainda_nao_existe",
            side_effect=self._simula_vencedora_e_corrida,
        ):
            result = queue_and_maybe_send_suggestion(
                db, "sug-1", canal="sipac", task=TASK, titulo_sinal="Sinal X",
                chat_id="chat-1", send_fn=send_fn,
            )

        self.assertTrue(result["telegram_sent"])
        self.assertEqual(len(sent), 1)


if __name__ == "__main__":
    unittest.main()
