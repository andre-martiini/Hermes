"""Testes do cursor composto (ingested_at, doc_id) de `triage_whatsapp_messages`
(whatsapp_ingest.py) -- P05, continuação da sub-entrega 7/N/8/N (idempotência
do produtor de reenvio de Telegram já corrigida; este arquivo cobre a
pendência de PRIORIDADE (a) registrada no diário: a colisão por milissegundo
em `ingested_at` que o antigo recuo de 1 microssegundo não conseguia
resolver por completo).

`triage_whatsapp_messages` nunca teve teste dedicado (é mockada em todos os
outros arquivos que a referenciam -- test_sync_custos.py, test_gmail_sync_webhook.py,
test_whatsapp_ingest_outbox.py) -- em vez de montar um fake de Firestore
cobrindo o pipeline inteiro (IA, settings, digest, sugestão), este arquivo
testa em isolamento as duas peças PURAS que carregam a correção:
`_next_cursor_after_batch` (a lógica de posição -- onde mora o bug e a
correção) e `_messages_query` (a construção da consulta -- onde mora a
migração automática do cursor antigo para o novo)."""

import unittest
from datetime import datetime, timedelta, timezone

from whatsapp_ingest import _messages_query, _next_cursor_after_batch

_T0 = datetime(2026, 9, 30, 12, 0, 0, 0, tzinfo=timezone.utc)


class _FakeDoc:
    """DocumentSnapshot mínimo: só `.id` e `.to_dict()`, o único subconjunto
    que `_next_cursor_after_batch` usa."""

    def __init__(self, doc_id: str, ingested_at: datetime):
        self.id = doc_id
        self._data = {"ingested_at": ingested_at}

    def to_dict(self):
        return self._data


class TestNextCursorAfterBatch(unittest.TestCase):
    def test_lote_vazio_devolve_none(self):
        self.assertIsNone(_next_cursor_after_batch([], set()))

    def test_sem_retencao_avanca_para_o_ultimo_documento_do_lote(self):
        docs = [
            _FakeDoc("a", _T0),
            _FakeDoc("b", _T0 + timedelta(milliseconds=1)),
            _FakeDoc("c", _T0 + timedelta(milliseconds=2)),
        ]
        self.assertEqual(
            _next_cursor_after_batch(docs, set()),
            (_T0 + timedelta(milliseconds=2), "c"),
        )

    def test_retencao_no_meio_do_lote_avanca_so_ate_o_documento_anterior(self):
        docs = [
            _FakeDoc("a", _T0),
            _FakeDoc("b", _T0 + timedelta(milliseconds=1)),  # retido
            _FakeDoc("c", _T0 + timedelta(milliseconds=2)),
        ]
        self.assertEqual(
            _next_cursor_after_batch(docs, {"b"}),
            (_T0, "a"),
        )

    def test_retencao_no_primeiro_documento_nao_avanca_nada(self):
        docs = [
            _FakeDoc("a", _T0),  # retido -- primeiro do lote
            _FakeDoc("b", _T0 + timedelta(milliseconds=1)),
        ]
        self.assertIsNone(_next_cursor_after_batch(docs, {"a"}))

    def test_colisao_de_milissegundo_entre_janelas_diferentes_nao_reintroduz_a_ja_processada(self):
        """Cenário exato do risco residual documentado na sub-entrega P05 7/N/8/N
        (PR #384): duas mensagens de CONVERSAS DIFERENTES com o mesmo `ingested_at`
        (granularidade de milissegundo do worker de captura). A mensagem "b"
        (chat retido, ex.: mídia pendente) precisa continuar elegível na próxima
        passada: o cursor deve ficar exatamente em "a" (o documento anterior a
        "b" na ordem que o Firestore devolveu), nunca em "b" nem em "c" -- "c" já
        foi processada com sucesso nesta passada e não pode ser relida."""
        docs = [
            _FakeDoc("a", _T0 - timedelta(milliseconds=1)),
            _FakeDoc("b", _T0),  # retido (ex.: mídia pendente do chat vinculado)
            _FakeDoc("c", _T0),  # MESMO milissegundo de "b", chat diferente, já processado
        ]
        self.assertEqual(
            _next_cursor_after_batch(docs, {"b"}),
            (_T0 - timedelta(milliseconds=1), "a"),
        )

    def test_multiplas_retencoes_usa_a_mais_antiga(self):
        docs = [
            _FakeDoc("a", _T0),
            _FakeDoc("b", _T0 + timedelta(milliseconds=1)),  # retido, mais antigo
            _FakeDoc("c", _T0 + timedelta(milliseconds=2)),
            _FakeDoc("d", _T0 + timedelta(milliseconds=3)),  # também retido
        ]
        self.assertEqual(
            _next_cursor_after_batch(docs, {"b", "d"}),
            (_T0, "a"),
        )

    def test_held_ids_sem_correspondencia_no_lote_cai_para_o_ultimo_documento(self):
        # Defensivo: nunca deveria acontecer em produção (held_ids sempre vem de
        # mensagens do próprio lote, ver chamador em triage_whatsapp_messages),
        # mas não deve quebrar se acontecer.
        docs = [_FakeDoc("a", _T0), _FakeDoc("b", _T0 + timedelta(milliseconds=1))]
        self.assertEqual(
            _next_cursor_after_batch(docs, {"nao-existe-no-lote"}),
            (_T0 + timedelta(milliseconds=1), "b"),
        )


class _RecordingQuery:
    """Recorder mínimo para verificar a construção da consulta em
    `_messages_query` -- não precisa executar nada, só registrar a sequência
    de chamadas encadeadas (mesmo espírito de um double de teste, mas sem
    simular dados: `_next_cursor_after_batch` já cobre a lógica de posição)."""

    def __init__(self, calls: list):
        self._calls = calls

    def order_by(self, field):
        self._calls.append(("order_by", field))
        return self

    def where(self, field, op, value):
        self._calls.append(("where", field, op, value))
        return self

    def start_after(self, cursor):
        self._calls.append(("start_after", tuple(cursor)))
        return self


class TestMessagesQuery(unittest.TestCase):
    def test_sem_doc_id_usa_filtro_por_intervalo_legado(self):
        """Cursor antigo (gravado antes desta correção, só com
        `last_processed_at`) ou primeira execução -- migração automática, sem
        script: cai para o filtro de sempre, sem `start_after`."""
        calls: list = []
        _messages_query(_RecordingQuery(calls), _T0, None)
        self.assertEqual(
            calls,
            [
                ("order_by", "ingested_at"),
                ("order_by", "__name__"),
                ("where", "ingested_at", ">", _T0),
            ],
        )

    def test_com_doc_id_usa_start_after_composto_sem_filtro_where(self):
        calls: list = []
        _messages_query(_RecordingQuery(calls), _T0, "doc-123")
        self.assertEqual(
            calls,
            [
                ("order_by", "ingested_at"),
                ("order_by", "__name__"),
                ("start_after", (_T0, "doc-123")),
            ],
        )

    def test_doc_id_vazio_e_tratado_como_ausente(self):
        # Defensivo: string vazia é falsy, mesma checagem de `if since_doc_id`
        # usada por triage_whatsapp_messages para decidir o modo do cursor.
        calls: list = []
        _messages_query(_RecordingQuery(calls), _T0, "")
        self.assertEqual(
            calls,
            [
                ("order_by", "ingested_at"),
                ("order_by", "__name__"),
                ("where", "ingested_at", ">", _T0),
            ],
        )


if __name__ == "__main__":
    unittest.main()
