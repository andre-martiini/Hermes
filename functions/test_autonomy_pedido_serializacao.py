"""Testes de `autonomy/pedido_serializacao.py` (P08): pedido <-> documento, puro."""

import copy
import dataclasses
import json
import unittest
from datetime import datetime, timedelta, timezone

from autonomy.execution import PedidoDuravel, assumir_pedido, registrar_progresso
from autonomy.ledger import registrar_resultado
from autonomy.pedido_serializacao import pedido_de_dict, pedido_para_dict
from autonomy.requests import RequestStatus
from autonomy.runs import AgentRunStatus

T0 = datetime(2026, 10, 29, 12, 0, 0, 123456, tzinfo=timezone.utc)


def _completo():
    p = assumir_pedido(PedidoDuravel("req-1", RequestStatus.PENDENTE), "ex-a", "run-1", agora=T0)
    p = registrar_progresso(
        p, p.lease.lease_token, p.lease.generation, "k1", {"a": 1}, {"passo": 1, "l": [1, {"x": None}]}, agora=T0
    )
    entrada = registrar_resultado(p.ledger_entry, {"ok": True, "itens": [1, 2]}, agora=T0)
    return dataclasses.replace(
        p,
        ledger_entry=entrada,
        tentativas=2,
        pausas=1,
        condicao_espera="resposta",
        proximo_tentativa_em=T0 + timedelta(hours=1),
    )


class TestSerializacaoPedido(unittest.TestCase):
    def test_round_trip_pedido_minimo(self):
        p = PedidoDuravel("req-9", RequestStatus.PENDENTE)
        self.assertEqual(pedido_de_dict(pedido_para_dict(p)), p)

    def test_round_trip_pedido_completo_via_json(self):
        p = _completo()
        doc = json.loads(json.dumps(pedido_para_dict(p)))
        self.assertEqual(pedido_de_dict(doc), p)

    def test_documento_so_tem_tipos_json_mutaveis(self):
        doc = pedido_para_dict(_completo())
        json.dumps(doc, allow_nan=False)
        self.assertIsInstance(doc["ledger_entry"]["resultado"], dict)
        self.assertIsInstance(doc["ledger_entry"]["checkpoints"][0]["dados"], dict)
        self.assertEqual(doc["status"], _completo().status.value)

    def test_instante_com_outro_fuso_vira_utc_e_volta_igual(self):
        fuso = timezone(timedelta(hours=-3))
        p = dataclasses.replace(
            PedidoDuravel("r", RequestStatus.RETENTATIVA_AGENDADA),
            proximo_tentativa_em=T0.astimezone(fuso),
        )
        doc = pedido_para_dict(p)
        self.assertTrue(doc["proximo_tentativa_em"].endswith("+00:00"))
        self.assertEqual(pedido_de_dict(doc).proximo_tentativa_em, T0)

    def test_status_cru_str_e_aceito_na_escrita(self):
        p = dataclasses.replace(PedidoDuravel("r", RequestStatus.PENDENTE), status="pendente")
        self.assertEqual(pedido_para_dict(p)["status"], "pendente")

    def test_run_status_preservado(self):
        p = _completo()
        doc = pedido_para_dict(p)
        self.assertEqual(pedido_de_dict(doc).run.status, AgentRunStatus.EM_ANDAMENTO)
        self.assertEqual(doc["run"]["status"], "em_andamento")

    def test_escrita_recusa_tipo_errado(self):
        with self.assertRaises(TypeError):
            pedido_para_dict({"request_id": "x"})

    def test_leitura_recusa_nao_mapa(self):
        for ruim in (None, [], "x", 3):
            with self.assertRaises(ValueError):
                pedido_de_dict(ruim)

    def test_leitura_recusa_chave_ausente_e_extra(self):
        base = pedido_para_dict(_completo())
        for chave in list(base):
            d = copy.deepcopy(base)
            del d[chave]
            with self.assertRaises(ValueError, msg=chave):
                pedido_de_dict(d)
        d = copy.deepcopy(base)
        d["extra"] = 1
        with self.assertRaises(ValueError):
            pedido_de_dict(d)

    def test_leitura_recusa_chave_ausente_e_extra_aninhada(self):
        for caminho in (("lease",), ("ledger_entry",), ("run",), ("ledger_entry", "checkpoints", 0)):
            for alvo in ("remover", "extra"):
                d = copy.deepcopy(pedido_para_dict(_completo()))
                no = d
                for k in caminho:
                    no = no[k]
                if alvo == "remover":
                    del no[next(iter(no))]
                else:
                    no["extra"] = 1
                with self.assertRaises(ValueError, msg=(caminho, alvo)):
                    pedido_de_dict(d)

    def test_leitura_recusa_versao_e_status_invalidos(self):
        for campo, valor in (("versao", 2), ("versao", True), ("versao", "1"), ("status", "inexistente"), ("status", 3)):
            d = pedido_para_dict(_completo())
            d[campo] = valor
            with self.assertRaises(ValueError, msg=(campo, valor)):
                pedido_de_dict(d)

    def test_leitura_recusa_bool_como_int(self):
        for caminho in (("tentativas",), ("pausas",), ("lease", "generation"), ("run", "generation")):
            d = pedido_para_dict(_completo())
            no = d
            for k in caminho[:-1]:
                no = no[k]
            no[caminho[-1]] = True
            with self.assertRaises(ValueError, msg=caminho):
                pedido_de_dict(d)

    def test_leitura_recusa_instante_sem_fuso_ou_invalido(self):
        for ruim in ("2026-10-29T12:00:00", "ontem", 123, ""):
            d = pedido_para_dict(_completo())
            d["lease"]["expires_at"] = ruim
            with self.assertRaises(ValueError, msg=ruim):
                pedido_de_dict(d)

    def test_nan_no_resultado_faz_round_trip(self):
        p = _completo()
        p = dataclasses.replace(p, ledger_entry=registrar_resultado(
            dataclasses.replace(p.ledger_entry, resultado=None, resultado_registrado_em=None),
            {"x": float("nan")}, agora=T0))
        lido = pedido_de_dict(pedido_para_dict(p))
        self.assertNotEqual(lido.ledger_entry.resultado["x"], lido.ledger_entry.resultado["x"])

    def test_leitura_recusa_chave_nao_str_aninhada_e_tupla(self):
        for ruim in ({1: "a", "1": "b"}, {"t": (1, 2)}):
            d = pedido_para_dict(_completo())
            d["ledger_entry"]["resultado"] = ruim
            with self.assertRaises(ValueError, msg=ruim):
                pedido_de_dict(d)

    def test_leitura_so_levanta_valueerror_em_limites_do_dominio(self):
        d = pedido_para_dict(_completo())
        d["ledger_entry"]["checkpoints"][0]["dados"] = {"x": "a" * 70000}
        with self.assertRaises(ValueError):
            pedido_de_dict(d)
        v = []
        for _ in range(100000):
            v = [v]
        d = pedido_para_dict(_completo())
        d["ledger_entry"]["resultado"] = v
        with self.assertRaises(ValueError):
            pedido_de_dict(d)

    def test_leitura_recusa_run_de_outro_pedido(self):
        d = pedido_para_dict(_completo())
        d["run"]["request_id"] = "outro"
        with self.assertRaises(ValueError):
            pedido_de_dict(d)

    def test_escrita_instante_extremo_levanta_valueerror(self):
        p = dataclasses.replace(
            PedidoDuravel("r", RequestStatus.RETENTATIVA_AGENDADA),
            proximo_tentativa_em=datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=3))),
        )
        with self.assertRaises(ValueError):
            pedido_para_dict(p)

    def test_leitura_recusa_json_nao_puro_em_resultado(self):
        d = pedido_para_dict(_completo())
        d["ledger_entry"]["resultado"] = {"x": object()}
        with self.assertRaises(ValueError):
            pedido_de_dict(d)

    def test_leitura_recusa_checkpoints_nao_lista_e_dados_nao_objeto(self):
        d = pedido_para_dict(_completo())
        d["ledger_entry"]["checkpoints"] = {}
        with self.assertRaises(ValueError):
            pedido_de_dict(d)
        d = pedido_para_dict(_completo())
        d["ledger_entry"]["checkpoints"][0]["dados"] = [1]
        with self.assertRaises(ValueError):
            pedido_de_dict(d)

    def test_leitura_recusa_dominio_invalido_com_valueerror(self):
        d = pedido_para_dict(_completo())
        d["tentativas"] = -1
        with self.assertRaises(ValueError):
            pedido_de_dict(d)
        d = pedido_para_dict(_completo())
        d["request_id"] = "  "
        with self.assertRaises(ValueError):
            pedido_de_dict(d)

    def test_documento_nao_compartilha_estado_com_o_pedido(self):
        p = _completo()
        doc = pedido_para_dict(p)
        doc["ledger_entry"]["resultado"]["ok"] = False
        self.assertTrue(p.ledger_entry.resultado["ok"])


if __name__ == "__main__":
    unittest.main()
