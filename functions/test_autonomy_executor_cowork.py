import unittest
from datetime import datetime, timedelta, timezone

from autonomy.execution import PedidoDuravel
from autonomy.executor_cowork import (
    CapacidadeInsuficiente, CapacidadesExecutor, DisputaPerdida, TipoExecutor, capacidades_faltantes,
    registrar_capacidades_cowork, registrar_capacidades_runner, reservar_pedido_para_executor,
)
from autonomy.requests import RequestStatus

AGORA = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def pedido():
    return PedidoDuravel(request_id="req-1", status=RequestStatus.PENDENTE)


class TestCapacidades(unittest.TestCase):
    def test_cowork_so_tem_o_declarado(self):
        c = registrar_capacidades_cowork("rotina-8h", [" gmail ", "calendar", "gmail"])
        self.assertEqual(c.executor_id, "cowork:rotina-8h")
        self.assertEqual(c.tipo, TipoExecutor.COWORK)
        self.assertEqual(c.capacidades, frozenset({"gmail", "calendar"}))

    def test_runner_nao_herda_conectores(self):
        r = registrar_capacidades_runner("runner-1", ["firestore"])
        self.assertEqual(capacidades_faltantes(r, ["firestore", "gmail"]), ("gmail",))

    def test_texto_unico_e_itens_invalidos_recusados(self):
        for ruim in ("gmail", None, [""], [1], ["  "]):
            with self.assertRaises(ValueError):
                registrar_capacidades_cowork("x", ruim)
        with self.assertRaises(ValueError):
            capacidades_faltantes(registrar_capacidades_runner("r", []), "gmail")

    def test_prefixo_e_tipo_coerentes(self):
        with self.assertRaises(ValueError):
            CapacidadesExecutor("runner-1", TipoExecutor.COWORK, frozenset())
        with self.assertRaises(ValueError):
            registrar_capacidades_runner("cowork:x", [])
        with self.assertRaises(ValueError):
            registrar_capacidades_cowork("  ", [])
        with self.assertRaises(ValueError):
            registrar_capacidades_runner("", [])

    def test_limite_de_capacidades(self):
        with self.assertRaises(ValueError):
            registrar_capacidades_cowork("x", [f"c{i}" for i in range(201)])


class TestReserva(unittest.TestCase):
    def test_reserva_com_capacidade_usa_lease_e_run(self):
        c = registrar_capacidades_cowork("r", ["gmail"])
        p = reservar_pedido_para_executor(pedido(), c, ["gmail"], "run-1", agora=AGORA)
        self.assertEqual(p.status, RequestStatus.RESERVADO)
        self.assertEqual(p.lease.executor_id, "cowork:r")
        self.assertEqual(p.run.run_id, "run-1")

    def test_falta_capacidade_nao_toca_pedido(self):
        r = registrar_capacidades_runner("runner-1", ["firestore"])
        original = pedido()
        with self.assertRaises(CapacidadeInsuficiente) as cm:
            reservar_pedido_para_executor(original, r, ["gmail", "calendar"], "run-1", agora=AGORA)
        self.assertEqual(cm.exception.faltantes, ("calendar", "gmail"))
        self.assertEqual(original.status, RequestStatus.PENDENTE)
        self.assertIsNone(original.lease)

    def test_dois_executores_disputando_o_pedido(self):
        r = registrar_capacidades_runner("runner-1", ["firestore"])
        c = registrar_capacidades_cowork("r", ["firestore"])
        p = reservar_pedido_para_executor(pedido(), r, ["firestore"], "run-1", agora=AGORA)
        with self.assertRaises(DisputaPerdida):
            reservar_pedido_para_executor(p, c, ["firestore"], "run-2", agora=AGORA + timedelta(seconds=1))

    def test_snapshot_pendente_compartilhado_reserva_nos_dois(self):
        # pureza: a exclusão real é o CAS do wiring (documentado)
        base = pedido()
        a = reservar_pedido_para_executor(base, registrar_capacidades_runner("r1", []), [], "a", agora=AGORA)
        b = reservar_pedido_para_executor(base, registrar_capacidades_cowork("x", []), [], "b", agora=AGORA)
        self.assertEqual((a.lease.generation, b.lease.generation), (1, 1))

    def test_duracao_invalida(self):
        r = registrar_capacidades_runner("r1", [])
        for d in (float("inf"), float("nan"), 0, -1, True, "5", 10**9, 10**400):
            with self.assertRaises(ValueError):
                reservar_pedido_para_executor(pedido(), r, [], "a", agora=AGORA, duracao_segundos=d)

    def test_ids_estranhos(self):
        for ruim in ("cowork:", "cowork:  ", "a\nb", "cowork：x"):
            with self.assertRaises(ValueError):
                CapacidadesExecutor(ruim, TipoExecutor.COWORK, [])
        for ruim in ("COWORK:x", "Cowork:x", "a\nb\x00", "cowork：x"):
            with self.assertRaises(ValueError):
                registrar_capacidades_runner(ruim, [])

    def test_tipos_errados(self):
        c = registrar_capacidades_cowork("r", [])
        with self.assertRaises(TypeError):
            reservar_pedido_para_executor(None, c, [], "a", agora=AGORA)
        with self.assertRaises(TypeError):
            reservar_pedido_para_executor(pedido(), None, [], "a", agora=AGORA)

    def test_gerador_de_requisitos(self):
        c = registrar_capacidades_cowork("r", ["a"])
        p = reservar_pedido_para_executor(pedido(), c, (x for x in ["a"]), "a", agora=AGORA)
        self.assertEqual(p.status, RequestStatus.RESERVADO)

    def test_sem_requisitos_basta_estar_registrado(self):
        c = registrar_capacidades_cowork("r", [])
        p = reservar_pedido_para_executor(pedido(), c, [], "run-1", agora=AGORA)
        self.assertEqual(p.lease.executor_id, "cowork:r")


if __name__ == "__main__":
    unittest.main()
