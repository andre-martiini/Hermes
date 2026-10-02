"""Testes de `autonomy/outbox.py` — só lógica pura, sem I/O (P05 sub-entrega
5/N: passo 3 do pacote, "outbox de eventos com dispatcher reconciliável";
P05 sub-entrega 17/N: passo 10 do pacote, reconciliação periódica).

Cobre: construção de uma entrada nova, consistência forçada entre
`entry_id` e `evento.event_id`, elegibilidade de despacho
(`pronta_para_despachar`), as duas transições de sucesso/falha
(`registrar_sucesso`/`registrar_falha`), o avanço de `disponivel_em` pelo
backoff reusado de `autonomy.requests`, o limite de tentativas até
`FALHA_FINAL`, a recusa de transicionar uma entrada já terminal, o estado
intermediário `EM_PROCESSAMENTO` com lease (`iniciar_despacho`) e a
reconciliação de lease vencida (`varrer_lease_vencida_outbox`).
"""

import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from autonomy.events import CategoriaEvento, montar_evento
from autonomy.outbox import (
    DiagnosticoOutbox,
    EstadoOutbox,
    EstadoOutboxTerminal,
    LeaseInvalidaOutbox,
    OutboxEntry,
    ResultadoSweepOutbox,
    criar_entrada,
    iniciar_despacho,
    pronta_para_despachar,
    registrar_falha,
    registrar_sucesso,
    varrer_lease_vencida_outbox,
)
from autonomy.requests import BACKOFF_BASE_SEGUNDOS, DEFAULT_LEASE_SEGUNDOS, lease_expirada

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

    def test_em_processamento_sem_lease_e_erro(self):
        evento = _evento()
        with self.assertRaises(ValueError):
            OutboxEntry(
                entry_id=evento.event_id,
                evento=evento,
                estado=EstadoOutbox.EM_PROCESSAMENTO,
                tentativas=0,
                criado_em=_AGORA,
                disponivel_em=_AGORA,
                lease=None,
            )


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
        # Corte e "> max_tentativas", nao ">=" -- com max_tentativas=1 a 1a
        # falha ainda concede 1 retentativa (PENDENTE); so a 2a falha (a
        # max_tentativas+1-esima) vira FALHA_FINAL.
        falha1 = registrar_falha(entrada, _AGORA, "e1", max_tentativas=1, rng=_RngFixo(0.0))
        self.assertEqual(falha1.estado, EstadoOutbox.PENDENTE)
        falha2 = registrar_falha(falha1, _AGORA, "e2", max_tentativas=1, rng=_RngFixo(0.0))
        self.assertEqual(falha2.estado, EstadoOutbox.FALHA_FINAL)
        with self.assertRaises(EstadoOutboxTerminal):
            registrar_sucesso(falha2, _AGORA)

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

    def test_terceira_falha_ainda_concede_o_terceiro_patamar(self):
        # Achado real de revisao automatica do Codex (P2) nesta sub-entrega:
        # o corte precisa ser "> max_tentativas", nao ">=" -- com
        # max_tentativas=3 (padrao), a 3a falha AINDA agenda o patamar de 20
        # minutos (BACKOFF_BASE_SEGUNDOS[2]) em vez de desistir direto,
        # senao o patamar de 20 min documentado nunca seria usado. Mesmo
        # achado/correcao ja aplicados a autonomy.sweep (PR #344).
        entrada = criar_entrada(_evento(), _AGORA)
        falha1 = registrar_falha(entrada, _AGORA, "e1", rng=_RngFixo(0.0))
        falha2 = registrar_falha(falha1, _AGORA, "e2", rng=_RngFixo(0.0))
        falha3 = registrar_falha(falha2, _AGORA, "e3", rng=_RngFixo(0.0))
        self.assertEqual(falha3.estado, EstadoOutbox.PENDENTE)
        self.assertEqual(falha3.tentativas, 3)
        self.assertEqual(
            falha3.disponivel_em, _AGORA + timedelta(seconds=BACKOFF_BASE_SEGUNDOS[2])
        )

    def test_quarta_falha_com_max_tentativas_padrao_vira_falha_final(self):
        entrada = criar_entrada(_evento(), _AGORA)
        falha1 = registrar_falha(entrada, _AGORA, "e1", rng=_RngFixo(0.0))
        falha2 = registrar_falha(falha1, _AGORA, "e2", rng=_RngFixo(0.0))
        falha3 = registrar_falha(falha2, _AGORA, "e3", rng=_RngFixo(0.0))
        falha4 = registrar_falha(falha3, _AGORA, "e4", rng=_RngFixo(0.0))
        self.assertEqual(falha4.estado, EstadoOutbox.FALHA_FINAL)
        self.assertEqual(falha4.tentativas, 4)
        self.assertEqual(falha4.ultimo_erro, "e4")
        # FALHA_FINAL não agenda mais retentativa -- disponivel_em congela.
        self.assertEqual(falha4.disponivel_em, falha3.disponivel_em)

    def test_max_tentativas_customizado_um_concede_uma_retentativa_depois_falha_final(self):
        entrada = criar_entrada(_evento(), _AGORA)
        falha1 = registrar_falha(entrada, _AGORA, "e1", max_tentativas=1, rng=_RngFixo(0.0))
        self.assertEqual(falha1.estado, EstadoOutbox.PENDENTE)
        self.assertEqual(falha1.tentativas, 1)
        falha2 = registrar_falha(falha1, _AGORA, "e2", max_tentativas=1, rng=_RngFixo(0.0))
        self.assertEqual(falha2.estado, EstadoOutbox.FALHA_FINAL)
        self.assertEqual(falha2.tentativas, 2)

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
        falha2 = registrar_falha(falha1, _AGORA, "e2", max_tentativas=1, rng=_RngFixo(0.0))
        self.assertEqual(falha2.estado, EstadoOutbox.FALHA_FINAL)
        with self.assertRaises(EstadoOutboxTerminal):
            registrar_falha(falha2, _AGORA, "e3", max_tentativas=1)

    def test_agora_naive_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        with self.assertRaises(ValueError):
            registrar_falha(entrada, datetime(2026, 9, 29, 12, 0, 0), "e1")

    def test_entrada_original_nao_e_mutada(self):
        entrada = criar_entrada(_evento(), _AGORA)
        registrar_falha(entrada, _AGORA, "e1", rng=_RngFixo(0.0))
        self.assertEqual(entrada.tentativas, 0)
        self.assertEqual(entrada.estado, EstadoOutbox.PENDENTE)


class TestIniciarDespacho(unittest.TestCase):
    def test_transiciona_para_em_processamento_com_lease_nova(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        self.assertEqual(em_processamento.estado, EstadoOutbox.EM_PROCESSAMENTO)
        self.assertIsNotNone(em_processamento.lease)
        self.assertEqual(em_processamento.lease.executor_id, "executor-1")
        self.assertEqual(em_processamento.lease.generation, 1)
        self.assertEqual(
            em_processamento.lease.expires_at,
            _AGORA + timedelta(seconds=DEFAULT_LEASE_SEGUNDOS),
        )
        # Nenhum outro campo muda.
        self.assertEqual(em_processamento.tentativas, 0)
        self.assertEqual(em_processamento.entry_id, entrada.entry_id)

    def test_entrada_original_nao_e_mutada(self):
        entrada = criar_entrada(_evento(), _AGORA)
        iniciar_despacho(entrada, "executor-1", _AGORA)
        self.assertEqual(entrada.estado, EstadoOutbox.PENDENTE)
        self.assertIsNone(entrada.lease)

    def test_duracao_customizada(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA, duracao_segundos=30)
        self.assertEqual(
            em_processamento.lease.expires_at, _AGORA + timedelta(seconds=30)
        )

    def test_reassumir_depois_de_devolvida_ao_pendente_incrementa_geracao(self):
        entrada = criar_entrada(_evento(), _AGORA)
        primeira = iniciar_despacho(entrada, "executor-1", _AGORA)
        resultado = varrer_lease_vencida_outbox(
            primeira, _AGORA + timedelta(seconds=DEFAULT_LEASE_SEGUNDOS), rng=_RngFixo(0.0)
        )
        self.assertEqual(resultado.entrada.estado, EstadoOutbox.PENDENTE)
        agora_depois = resultado.entrada.disponivel_em
        segunda = iniciar_despacho(resultado.entrada, "executor-2", agora_depois)
        self.assertEqual(segunda.lease.generation, 2)
        self.assertEqual(segunda.lease.executor_id, "executor-2")

    def test_nao_pendente_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        enviada = registrar_sucesso(entrada, _AGORA)
        with self.assertRaises(ValueError):
            iniciar_despacho(enviada, "executor-1", _AGORA)

    def test_ainda_nao_disponivel_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        com_backoff = registrar_falha(entrada, _AGORA, "timeout", rng=_RngFixo(0.0))
        with self.assertRaises(ValueError):
            iniciar_despacho(com_backoff, "executor-1", _AGORA)

    def test_ja_em_processamento_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        # estado não é PENDENTE -> pronta_para_despachar recusa, mesmo que a
        # lease já emitida ainda esteja bem dentro do prazo.
        with self.assertRaises(ValueError):
            iniciar_despacho(em_processamento, "executor-2", _AGORA)

    def test_agora_naive_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        with self.assertRaises(ValueError):
            iniciar_despacho(entrada, "executor-1", datetime(2026, 9, 29, 12, 0, 0))

    def test_reassumir_depois_de_registrar_falha_nao_espera_lease_antiga_vencer(self):
        # Achado real de revisão adversarial independente (1a rodada): uma
        # versão anterior de iniciar_despacho recusava reassumir uma entrada
        # PENDENTE sempre que `entrada.lease` ainda não tinha expirado --
        # mas registrar_falha() devolve EM_PROCESSAMENTO para PENDENTE sem
        # jamais invalidar a lease anterior (ela só vence sozinha depois de
        # DEFAULT_LEASE_SEGUNDOS, bem mais que o backoff curto do 1o
        # patamar). Isso bloqueava a retentativa até a lease antiga vencer
        # por conta própria, ignorando o backoff calculado. Este teste prova
        # que iniciar_despacho aceita a retentativa assim que
        # disponivel_em chega, mesmo com a lease antiga tecnicamente ainda
        # "válida" (expires_at no futuro).
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        falhou = registrar_falha(
            em_processamento,
            _AGORA,
            "timeout",
            rng=_RngFixo(0.0),
            lease_token=em_processamento.lease.lease_token,
            generation=em_processamento.lease.generation,
        )
        self.assertEqual(falhou.estado, EstadoOutbox.PENDENTE)
        # A lease antiga ainda não expirou (duração padrão >> backoff do
        # 1o patamar) -- prova que o cenário do achado é real.
        self.assertFalse(lease_expirada(falhou.lease, agora=falhou.disponivel_em))

        retentativa = iniciar_despacho(falhou, "executor-1", falhou.disponivel_em)
        self.assertEqual(retentativa.estado, EstadoOutbox.EM_PROCESSAMENTO)
        self.assertEqual(retentativa.lease.generation, 2)


class TestVarrerLeaseVencidaOutbox(unittest.TestCase):
    def test_lease_vencida_primeira_vez_volta_para_pendente_com_backoff(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        agora_depois = _AGORA + timedelta(seconds=DEFAULT_LEASE_SEGUNDOS + 1)
        resultado = varrer_lease_vencida_outbox(em_processamento, agora_depois, rng=_RngFixo(0.0))
        self.assertIsInstance(resultado, ResultadoSweepOutbox)
        self.assertEqual(resultado.entrada.estado, EstadoOutbox.PENDENTE)
        self.assertEqual(resultado.entrada.tentativas, 1)
        self.assertEqual(
            resultado.entrada.disponivel_em,
            agora_depois + timedelta(seconds=BACKOFF_BASE_SEGUNDOS[0]),
        )
        self.assertIsNone(resultado.diagnostico)
        # Lease é preservada (fencing para a próxima geração).
        self.assertIsNotNone(resultado.entrada.lease)
        self.assertEqual(resultado.entrada.lease.generation, 1)

    def test_esgota_tentativas_vira_falha_final_com_diagnostico(self):
        # max_tentativas=1 concede 1 retentativa (volta para PENDENTE na 1a
        # lease vencida) -- só a 2a lease vencida (a max_tentativas+1-ésima)
        # desiste, mesma semântica de registrar_falha/autonomy.sweep.
        entrada = criar_entrada(_evento(), _AGORA)
        em1 = iniciar_despacho(entrada, "executor-1", _AGORA)
        venceu1 = _AGORA + timedelta(seconds=DEFAULT_LEASE_SEGUNDOS + 1)
        r1 = varrer_lease_vencida_outbox(em1, venceu1, max_tentativas=1, rng=_RngFixo(0.0))
        self.assertEqual(r1.entrada.estado, EstadoOutbox.PENDENTE)
        self.assertIsNone(r1.diagnostico)

        em2 = iniciar_despacho(r1.entrada, "executor-1", r1.entrada.disponivel_em)
        venceu2 = em2.lease.expires_at + timedelta(seconds=1)
        resultado = varrer_lease_vencida_outbox(em2, venceu2, max_tentativas=1, rng=_RngFixo(0.0))
        self.assertEqual(resultado.entrada.estado, EstadoOutbox.FALHA_FINAL)
        self.assertIsNotNone(resultado.diagnostico)
        self.assertIsInstance(resultado.diagnostico, DiagnosticoOutbox)
        self.assertEqual(resultado.diagnostico.entry_id, entrada.entry_id)
        self.assertEqual(resultado.diagnostico.tentativas, 2)
        self.assertEqual(resultado.diagnostico.estado_anterior, EstadoOutbox.EM_PROCESSAMENTO)

    def test_terceira_lease_vencida_ainda_concede_o_terceiro_patamar(self):
        # Mesmo achado/correção de off-by-one já aplicado a registrar_falha
        # e autonomy.sweep: o corte é "> max_tentativas", não ">=".
        entrada = criar_entrada(_evento(), _AGORA)
        em1 = iniciar_despacho(entrada, "executor-1", _AGORA)
        venceu1 = _AGORA + timedelta(seconds=DEFAULT_LEASE_SEGUNDOS + 1)
        r1 = varrer_lease_vencida_outbox(em1, venceu1, rng=_RngFixo(0.0))
        em2 = iniciar_despacho(r1.entrada, "executor-1", r1.entrada.disponivel_em)
        venceu2 = em2.lease.expires_at + timedelta(seconds=1)
        r2 = varrer_lease_vencida_outbox(em2, venceu2, rng=_RngFixo(0.0))
        em3 = iniciar_despacho(r2.entrada, "executor-1", r2.entrada.disponivel_em)
        venceu3 = em3.lease.expires_at + timedelta(seconds=1)
        r3 = varrer_lease_vencida_outbox(em3, venceu3, rng=_RngFixo(0.0))
        self.assertEqual(r3.entrada.estado, EstadoOutbox.PENDENTE)
        self.assertEqual(r3.entrada.tentativas, 3)
        self.assertEqual(
            r3.entrada.disponivel_em, venceu3 + timedelta(seconds=BACKOFF_BASE_SEGUNDOS[2])
        )
        self.assertIsNone(r3.diagnostico)

    def test_nao_em_processamento_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        with self.assertRaises(ValueError):
            varrer_lease_vencida_outbox(entrada, _AGORA)

    def test_lease_ainda_valida_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        with self.assertRaises(ValueError):
            varrer_lease_vencida_outbox(em_processamento, _AGORA)

    def test_max_tentativas_menor_que_um_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        agora_depois = _AGORA + timedelta(seconds=DEFAULT_LEASE_SEGUNDOS + 1)
        with self.assertRaises(ValueError):
            varrer_lease_vencida_outbox(em_processamento, agora_depois, max_tentativas=0)

    def test_estado_terminal_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        enviada = registrar_sucesso(entrada, _AGORA)
        with self.assertRaises(ValueError):
            varrer_lease_vencida_outbox(enviada, _AGORA)

    def test_agora_naive_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        with self.assertRaises(ValueError):
            varrer_lease_vencida_outbox(em_processamento, datetime(2026, 9, 29, 12, 0, 0))

    def test_entrada_original_nao_e_mutada(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        agora_depois = _AGORA + timedelta(seconds=DEFAULT_LEASE_SEGUNDOS + 1)
        varrer_lease_vencida_outbox(em_processamento, agora_depois, rng=_RngFixo(0.0))
        self.assertEqual(em_processamento.estado, EstadoOutbox.EM_PROCESSAMENTO)


class TestRegistrarSucessoFalhaAPartirDeEmProcessamento(unittest.TestCase):
    """`registrar_sucesso`/`registrar_falha` continuam aceitando a entrada
    tanto a partir de PENDENTE (dispatcher simples, comportamento já coberto
    acima, sem nenhuma credencial) quanto a partir de EM_PROCESSAMENTO
    (dispatcher que usou `iniciar_despacho`, agora EXIGINDO `lease_token`/
    `generation` corretos -- achado real de revisão automática do Codex,
    P1, nesta mesma PR: ver `LeaseInvalidaOutbox`)."""

    def test_registrar_sucesso_a_partir_de_em_processamento_com_credencial_correta(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        enviada = registrar_sucesso(
            em_processamento,
            _AGORA + timedelta(seconds=1),
            lease_token=em_processamento.lease.lease_token,
            generation=em_processamento.lease.generation,
        )
        self.assertEqual(enviada.estado, EstadoOutbox.ENVIADO)
        # Lease preservada mesmo em estado terminal (histórico, sem uso
        # futuro -- ver docstring de OutboxEntry.lease).
        self.assertIsNotNone(enviada.lease)

    def test_registrar_falha_a_partir_de_em_processamento_com_credencial_correta(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        depois = registrar_falha(
            em_processamento,
            _AGORA + timedelta(seconds=1),
            "erro-x",
            rng=_RngFixo(0.0),
            lease_token=em_processamento.lease.lease_token,
            generation=em_processamento.lease.generation,
        )
        self.assertEqual(depois.estado, EstadoOutbox.PENDENTE)
        self.assertEqual(depois.tentativas, 1)
        self.assertIsNotNone(depois.lease)

    def test_registrar_sucesso_sem_credencial_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        with self.assertRaises(LeaseInvalidaOutbox):
            registrar_sucesso(em_processamento, _AGORA + timedelta(seconds=1))

    def test_registrar_falha_sem_credencial_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        with self.assertRaises(LeaseInvalidaOutbox):
            registrar_falha(em_processamento, _AGORA + timedelta(seconds=1), "erro-x")

    def test_registrar_sucesso_com_token_errado_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        with self.assertRaises(LeaseInvalidaOutbox):
            registrar_sucesso(
                em_processamento,
                _AGORA + timedelta(seconds=1),
                lease_token="token-errado",
                generation=em_processamento.lease.generation,
            )

    def test_registrar_sucesso_com_geracao_errada_e_erro(self):
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        with self.assertRaises(LeaseInvalidaOutbox):
            registrar_sucesso(
                em_processamento,
                _AGORA + timedelta(seconds=1),
                lease_token=em_processamento.lease.lease_token,
                generation=99,
            )

    def test_executor_zumbi_com_geracao_antiga_nao_consegue_concluir_apos_reatribuicao(self):
        # Cenario do achado do Codex: executor A perde a lease (sweep
        # reatribui a entrada ao executor B, geracao 2); A, atrasado, tenta
        # reportar sucesso com sua propria geracao antiga (1) -- deve ser
        # recusado, mesmo que A ainda tenha uma copia da entrada em memoria.
        entrada = criar_entrada(_evento(), _AGORA)
        presa_do_executor_a = iniciar_despacho(entrada, "executor-a", _AGORA)
        venceu = _AGORA + timedelta(seconds=DEFAULT_LEASE_SEGUNDOS + 1)
        sweep = varrer_lease_vencida_outbox(presa_do_executor_a, venceu, rng=_RngFixo(0.0))
        entrada_reatribuivel = sweep.entrada
        assumida_pelo_executor_b = iniciar_despacho(
            entrada_reatribuivel, "executor-b", entrada_reatribuivel.disponivel_em
        )
        self.assertEqual(assumida_pelo_executor_b.lease.generation, 2)

        # executor A, zumbi, ainda tenta concluir com a geracao 1 antiga --
        # mesmo apresentando o token certo da SUA propria lease (que ja nao
        # e mais a atual), a geracao nao bate com a entrada atual (gen 2).
        with self.assertRaises(LeaseInvalidaOutbox):
            registrar_sucesso(
                assumida_pelo_executor_b,
                entrada_reatribuivel.disponivel_em,
                lease_token=presa_do_executor_a.lease.lease_token,
                generation=presa_do_executor_a.lease.generation,
            )

    def test_estado_pendente_nao_exige_nem_valida_credencial(self):
        # Caminho do dispatcher simples (sem iniciar_despacho) -- nenhuma
        # lease em jogo, nenhuma credencial exigida, mesmo com uma lease
        # ANTIGA presa na entrada (preservada por registrar_falha).
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        pendente_com_lease_antiga = registrar_falha(
            em_processamento,
            _AGORA,
            "e1",
            rng=_RngFixo(0.0),
            lease_token=em_processamento.lease.lease_token,
            generation=em_processamento.lease.generation,
        )
        self.assertEqual(pendente_com_lease_antiga.estado, EstadoOutbox.PENDENTE)
        self.assertIsNotNone(pendente_com_lease_antiga.lease)
        # Sem passar lease_token/generation nenhum -- nao deveria levantar.
        enviada = registrar_sucesso(pendente_com_lease_antiga, pendente_com_lease_antiga.disponivel_em)
        self.assertEqual(enviada.estado, EstadoOutbox.ENVIADO)


if __name__ == "__main__":
    unittest.main()
