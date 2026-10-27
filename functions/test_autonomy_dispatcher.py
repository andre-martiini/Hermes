import unittest
from datetime import datetime, timedelta, timezone

from autonomy.dispatcher import (
    AcaoDespacho, ModoDispatcher, decidir_despacho, decidir_lote, modo_de_config, nome_tarefa,
)
from autonomy.execution import PedidoDuravel
from autonomy.requests import Lease, RequestStatus

AGORA = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def pedido(rid="req-1", status=RequestStatus.PENDENTE, **kw):
    return PedidoDuravel(request_id=rid, status=status, **kw)


class TestModo(unittest.TestCase):
    def test_invalido_vira_off(self):
        for v in (None, "", "ligado", 1, True, [], "  OFF "):
            self.assertIs(modo_de_config(v), ModoDispatcher.OFF)
        self.assertIs(modo_de_config(" Shadow "), ModoDispatcher.SHADOW)
        self.assertIs(modo_de_config("ATIVO"), ModoDispatcher.ATIVO)


class TestDecisao(unittest.TestCase):
    def test_off_nao_faz_nada(self):
        d = decidir_despacho(pedido(), "off", AGORA, 10)
        self.assertIs(d.acao, AcaoDespacho.NAO_DESPACHAR)
        self.assertEqual(d.nome_tarefa, "")

    def test_sombra_calcula_sem_enfileirar(self):
        d = decidir_despacho(pedido(), "shadow", AGORA)
        self.assertIs(d.acao, AcaoDespacho.REGISTRAR_SOMBRA)
        self.assertEqual(d.payload, (("request_id", "req-1"),))
        self.assertEqual(d.nome_tarefa, nome_tarefa("req-1", 0))

    def test_ativo_exige_orcamento(self):
        for orc in (None, 0, -1, True, "3", 1.5):
            d = decidir_despacho(pedido(), "ativo", AGORA, orc)
            self.assertIs(d.acao, AcaoDespacho.NAO_DESPACHAR)
            self.assertEqual(d.motivo, "sem_orcamento")
        d = decidir_despacho(pedido(), "ativo", AGORA, 1)
        self.assertIs(d.acao, AcaoDespacho.ENFILEIRAR)

    def test_status_nao_despachavel(self):
        for st in (RequestStatus.CONCLUIDO, RequestStatus.EM_ANDAMENTO, RequestStatus.AGUARDANDO_EXTERNO,
                   RequestStatus.RESERVADO, RequestStatus.FALHA_FINAL):
            d = decidir_despacho(pedido(status=st), "ativo", AGORA, 5)
            self.assertEqual(d.motivo, "status_nao_despachavel", st)

    def test_lease_ativa_bloqueia_expirada_libera(self):
        ativa = Lease("t", 1, "r", AGORA + timedelta(minutes=1))
        vencida = Lease("t", 1, "r", AGORA - timedelta(minutes=1))
        self.assertEqual(decidir_despacho(pedido(lease=ativa), "ativo", AGORA, 1).motivo, "lease_ativa")
        self.assertIs(decidir_despacho(pedido(lease=vencida), "ativo", AGORA, 1).acao, AcaoDespacho.ENFILEIRAR)

    def test_retentativa_so_depois_do_horario(self):
        p = pedido(status=RequestStatus.RETENTATIVA_AGENDADA, proximo_tentativa_em=AGORA + timedelta(seconds=5))
        self.assertEqual(decidir_despacho(p, "ativo", AGORA, 1).motivo, "retentativa_futura")
        self.assertIs(decidir_despacho(p, "ativo", AGORA + timedelta(seconds=5), 1).acao, AcaoDespacho.ENFILEIRAR)
        sem = pedido(status=RequestStatus.RETENTATIVA_AGENDADA)
        self.assertIs(decidir_despacho(sem, "ativo", AGORA, 1).acao, AcaoDespacho.ENFILEIRAR)

    def test_nome_estavel_valido_e_por_tentativa(self):
        self.assertEqual(nome_tarefa("a/b c", 2), nome_tarefa("a/b c", 2))
        self.assertNotEqual(nome_tarefa("a", 0), nome_tarefa("a", 1))
        self.assertNotEqual(nome_tarefa("a", 0), nome_tarefa("b", 0))
        self.assertRegex(nome_tarefa("ç/ ?" * 300, 3), r"^[A-Za-z0-9_-]{1,500}$")

    def test_entrada_invalida(self):
        with self.assertRaises(TypeError):
            decidir_despacho("req", "off", AGORA)
        with self.assertRaises(ValueError):
            decidir_despacho(pedido(), "off", datetime(2026, 1, 1))


class TestAchadosRevisao(unittest.TestCase):
    def test_status_str_crua_respeita_backoff(self):
        p = PedidoDuravel("a", "retentativa_agendada", proximo_tentativa_em=AGORA + timedelta(hours=1))
        self.assertEqual(decidir_despacho(p, "ativo", AGORA, 1).motivo, "retentativa_futura")
        self.assertEqual(decidir_despacho(PedidoDuravel("a", "lixo"), "ativo", AGORA, 1).motivo,
                         "status_nao_despachavel")

    def test_tentativas_nao_inteiras(self):
        for ruim in (1.5, True):
            d = decidir_despacho(pedido(tentativas=ruim), "ativo", AGORA, 1)
            self.assertEqual(d.motivo, "tentativas_invalidas")

    def test_duplicata_no_lote_nao_gasta_orcamento(self):
        p = pedido("a")
        ds = decidir_lote([p, p, pedido("b")], "ativo", AGORA, 2)
        self.assertEqual([d.acao for d in ds], [
            AcaoDespacho.ENFILEIRAR, AcaoDespacho.NAO_DESPACHAR, AcaoDespacho.ENFILEIRAR])


class TestLote(unittest.TestCase):
    def test_orcamento_e_consumido_em_ordem(self):
        ps = [pedido("a"), pedido("b", status=RequestStatus.CONCLUIDO), pedido("c"), pedido("d")]
        ds = decidir_lote(ps, "ativo", AGORA, 2)
        self.assertEqual([d.acao for d in ds], [
            AcaoDespacho.ENFILEIRAR, AcaoDespacho.NAO_DESPACHAR, AcaoDespacho.ENFILEIRAR, AcaoDespacho.NAO_DESPACHAR,
        ])
        self.assertEqual(ds[3].motivo, "sem_orcamento")

    def test_sombra_nao_consome(self):
        ds = decidir_lote([pedido("a"), pedido("b")], "shadow", AGORA, 0)
        self.assertTrue(all(d.acao is AcaoDespacho.REGISTRAR_SOMBRA for d in ds))


if __name__ == "__main__":
    unittest.main()
