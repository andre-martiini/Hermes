"""Testes de `autonomy/outbox.py` — só lógica pura, sem I/O (P05 sub-entrega
5/N: passo 3 do pacote, "outbox de eventos com dispatcher reconciliável").

Cobre: construção de uma entrada nova, consistência forçada entre
`entry_id` e `evento.event_id`, elegibilidade de despacho
(`pronta_para_despachar`), as duas transições de sucesso/falha
(`registrar_sucesso`/`registrar_falha`), o avanço de `disponivel_em` pelo
backoff reusado de `autonomy.requests`, o limite de tentativas até
`FALHA_FINAL`, e a recusa de transicionar uma entrada já terminal.
"""

import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from autonomy.events import CategoriaEvento, montar_evento
from autonomy.outbox import (
    EstadoOutbox,
    EstadoOutboxTerminal,
    OutboxEntry,
    criar_entrada,
    pronta_para_despachar,
    registrar_falha,
    registrar_sucesso,
)
from autonomy.requests import BACKOFF_BASE_SEGUNDOS

_AGORA = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


class _RngFixo:
    """Mesmo fake mínimo de `test_autonomy_requests.py` para jitter
    determinístico."""

    def __init__(self, valor: float):
        self._valor = valor

    def uniform(self, a: float, b: float) -> float:
        return self._valor


def _evento(occurred_at: datetime = _AGORA, doc_id: str = "msg-1"):
    return montar_evento(
        CategoriaEvento.MENSAGEM,
        "whatsapp_messages",
        doc_id,
        {"texto": "oi"},
        occurred_at=occurred_at,
        ingested_at=_AGORA,
    )


class TestCriarEntrada(unittest.TestCase):
    def test_estado_inicial(self):
        entrada = criar_entrada(_evento(), _AGORA)
        self.assertEqual(entrada.estado, EstadoOutbox.PENDENTE)
        self.assertEqual(entrada.tentativas, 0)
        self.assertEqual(entrada.criado_em, _AGORA)
        self.assertEqual(entrada.disponivel_em, _AGORA)
        self.assertIsNone(entrada.ultima_tentativa_em)
        self.assertIsNone(entrada.ultimo_erro)

    def test_entry_id_reusa_event_id(self):
        evento = _evento()
        entrada = criar_entrada(evento, _AGORA)
        self.assertEqual(entrada.entry_id, evento.event_id)

    def test_agora_naive_e_erro(self):
        with self.assertRaises(ValueError):
            criar_entrada(_evento(), datetime(2026, 9, 29, 12, 0, 0))


class TestOutboxEntryPostInit(unittest.TestCase):
    def test_entry_id_divergente_do_evento_e_erro(self):
        evento = _evento()
        with self.assertRaises(ValueError):
            OutboxEntry(
                entry_id="outro-id",
                evento=evento,
                estado=EstadoOutbox.PENDENTE,
                tentativas=0,
                criado_em=_AGORA,
                disponivel_em=_AGORA,
            )

    def test_tentativas_negativas_e_erro(self):
        evento = _evento()
        with self.assertRaises(ValueError):
            OutboxEntry(
                entry_id=evento.event_id,
                evento=evento,
                estado=EstadoOutbox.PENDENTE,
                tentativas=-1,
                criado_em=_AGORA,
                disponivel_em=_AGORA,
            )

    def test_criado_em_naive_e_erro(self):
        evento = _evento()
        with self.assertRaises(ValueError):
            OutboxEntry(
                entry_id=evento.event_id,
                evento=evento,
                estado=EstadoOutbox.PENDENTE,
                tentativas=0,
                criado_em=datetime(2026, 9, 29, 12, 0, 0),
                disponivel_em=_AGORA,
            )

    def test_disponivel_em_naive_e_erro(self):
        # Achado real de revisão adversarial independente: a checagem de
        # disponivel_em não era exercida isoladamente (só em conjunto com
        # criado_em, via criar_entrada()) -- este teste passa criado_em
        # tz-aware e disponivel_em naive para provar que a checagem em
        # __post_init__ dispara para ESTE campo especificamente.
        evento = _evento()
        with self.assertRaises(ValueError):
            OutboxEntry(
                entry_id=evento.event_id,
                evento=evento,
                estado=EstadoOutbox.PENDENTE,
                tentativas=0,
                criado_em=_AGORA,
                disponivel_em=datetime(2026, 9, 29, 12, 0, 0),
            )

    def test_ultima_tentativa_em_naive_e_erro(self):
        evento = _evento()
        with self.assertRaises(ValueError):
            OutboxEntry(
                entry_id=evento.event_id,
                evento=evento,
                estado=EstadoOutbox.PENDENTE,
                tentativas=0,
                criado_em=_AGORA,
                disponivel_em=_AGORA,
                ultima_tentativa_em=datetime(2026, 9, 29, 12, 0, 0),
            )

    def test_disponivel_em_antes_de_criado_em_e_erro(self):
        evento = _evento()
        with self.assertRaises(ValueError):
            OutboxEntry(
                entry_id=evento.event_id,
                evento=evento,
                estado=EstadoOutbox.PENDENTE,
                tentativas=0,
                criado_em=_AGORA,
                disponivel_em=_AGORA - timedelta(days=1),
            )

    def test_estado_fora_do_enum_e_erro(self):
        evento = _evento()
        with self.assertRaises(ValueError):
            OutboxEntry(
                entry_id=evento.event_id,
                evento=evento,
                estado="pendente",  # string crua, não o membro do enum
                tentativas=0,
                criado_em=_AGORA,
                disponivel_em=_AGORA,
            )

    def test_e_imutavel(self):
        entrada = criar_entrada(_evento(), _AGORA)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            entrada.tentativas = 5


class TestProntaParaDespachar(unittest.TestCase):
    def test_pendente_e_disponivel_agora_e_elegivel(self):
        entrada = criar_entrada(_evento(), _AGORA)
        self.assertTrue(pronta_para_despachar(entrada, _AGORA))

    def test_pendente_e_disponivel_no_passado_e_elegivel(self):
        entrada = criar_entrada(_evento(), _AGORA)
        self.assertTrue(pronta_para_despachar(entrada, _AGORA + timedelta(minutes=1)))

    def test_pendente_mas_ainda_nao_disponivel_nao_e_elegivel(self):
        entrada = criar_entrada(_evento(), _AGORA)
        entrada_com_backoff = registrar_falha(
            entrada, _AGORA, "timeout", rng=_RngFixo(0.0)
        )
        self.assertFalse(pronta_para_despachar(entrada_com_backoff, _AGORA))

    def test_estado_terminal_nunca_e_elegivel(self):
        entrada = criar_entrada(_evento(), _AGORA)
        enviada = registrar_sucesso(entrada, _AGORA)
        # disponivel_em não avançou (ainda == _AGORA), mas ENVIADO nunca é
        # elegível.
        self.assertFalse(pronta_para_despachar(enviada, _AGORA + timedelta(days=1)))


class TestRegistrarSucesso(unittest.TestCase):
    def test_transiciona_para_enviado(self):
        entrada = criar_entrada(_evento(), _AGORA)
        depois = timedelta(minutes=5)
        enviada = registrar_sucesso(entrada, _AGORA + depois)
        self.assertEqual(enviada.estado, EstadoOutbox.ENVIADO)
        self.assertEqual(enviada.ultima_tentativa_em, _AGORA + depois)
        # Nenhum outro campo muda.
        self.assertEqual(enviada.tentativas, 0)
        self.assertEqual(enviada.entry_id, entrada.entry_id)

    def test_entrada_original_nao_e_mutada(self):
        entrada = criar_entrada(_evento(), _AGORA)
        registrar_sucesso(entrada, _AGORA)
        self.assertEqual(entrada.estado, EstadoOutbox.PENDENTE)

    def test_ja_enviado_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        enviada = registrar_sucesso(entrada, _AGORA)
        with self.assertRaises(EstadoOutboxTerminal):
            registrar_sucesso(enviada, _AGORA)

    def test_ja_em_falha_final_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        falha1 = registrar_falha(entrada, _AGORA, "e1", max_tentativas=1, rng=_RngFixo(0.0))
        self.assertEqual(falha1.estado, EstadoOutbox.FALHA_FINAL)
        with self.assertRaises(EstadoOutboxTerminal):
            registrar_sucesso(falha1, _AGORA)

    def test_agora_naive_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        with self.assertRaises(ValueError):
            registrar_sucesso(entrada, datetime(2026, 9, 29, 12, 0, 0))


class TestRegistrarFalha(unittest.TestCase):
    def test_primeira_falha_permanece_pendente_com_backoff(self):
        entrada = criar_entrada(_evento(), _AGORA)
        depois = registrar_falha(entrada, _AGORA, "timeout", rng=_RngFixo(0.0))
        self.assertEqual(depois.estado, EstadoOutbox.PENDENTE)
        self.assertEqual(depois.tentativas, 1)
        self.assertEqual(depois.ultimo_erro, "timeout")
        self.assertEqual(depois.ultima_tentativa_em, _AGORA)
        self.assertEqual(
            depois.disponivel_em, _AGORA + timedelta(seconds=BACKOFF_BASE_SEGUNDOS[0])
        )

    def test_segunda_falha_usa_segundo_patamar(self):
        entrada = criar_entrada(_evento(), _AGORA)
        falha1 = registrar_falha(entrada, _AGORA, "e1", rng=_RngFixo(0.0))
        falha2 = registrar_falha(falha1, _AGORA, "e2", rng=_RngFixo(0.0))
        self.assertEqual(falha2.estado, EstadoOutbox.PENDENTE)
        self.assertEqual(falha2.tentativas, 2)
        self.assertEqual(
            falha2.disponivel_em, _AGORA + timedelta(seconds=BACKOFF_BASE_SEGUNDOS[1])
        )

    def test_atinge_max_tentativas_padrao_vira_falha_final(self):
        entrada = criar_entrada(_evento(), _AGORA)
        falha1 = registrar_falha(entrada, _AGORA, "e1", rng=_RngFixo(0.0))
        falha2 = registrar_falha(falha1, _AGORA, "e2", rng=_RngFixo(0.0))
        falha3 = registrar_falha(falha2, _AGORA, "e3", rng=_RngFixo(0.0))
        self.assertEqual(falha3.estado, EstadoOutbox.FALHA_FINAL)
        self.assertEqual(falha3.tentativas, 3)
        self.assertEqual(falha3.ultimo_erro, "e3")
        # FALHA_FINAL não agenda mais retentativa -- disponivel_em congela.
        self.assertEqual(falha3.disponivel_em, falha2.disponivel_em)

    def test_max_tentativas_customizado_um_falha_direto_para_final(self):
        entrada = criar_entrada(_evento(), _AGORA)
        falha = registrar_falha(entrada, _AGORA, "e1", max_tentativas=1, rng=_RngFixo(0.0))
        self.assertEqual(falha.estado, EstadoOutbox.FALHA_FINAL)
        self.assertEqual(falha.tentativas, 1)

    def test_max_tentativas_menor_que_um_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        with self.assertRaises(ValueError):
            registrar_falha(entrada, _AGORA, "e1", max_tentativas=0)

    def test_ja_enviado_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        enviada = registrar_sucesso(entrada, _AGORA)
        with self.assertRaises(EstadoOutboxTerminal):
            registrar_falha(enviada, _AGORA, "e1")

    def test_ja_em_falha_final_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        falha1 = registrar_falha(entrada, _AGORA, "e1", max_tentativas=1, rng=_RngFixo(0.0))
        with self.assertRaises(EstadoOutboxTerminal):
            registrar_falha(falha1, _AGORA, "e2", max_tentativas=1)

    def test_agora_naive_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        with self.assertRaises(ValueError):
            registrar_falha(entrada, datetime(2026, 9, 29, 12, 0, 0), "e1")

    def test_entrada_original_nao_e_mutada(self):
        entrada = criar_entrada(_evento(), _AGORA)
        registrar_falha(entrada, _AGORA, "e1", rng=_RngFixo(0.0))
        self.assertEqual(entrada.tentativas, 0)
        self.assertEqual(entrada.estado, EstadoOutbox.PENDENTE)


if __name__ == "__main__":
    unittest.main()
