import json
import unittest
from datetime import timedelta

from autonomy.runner import StatusRunner
from autonomy.worker_http import MAX_CORPO_BYTES, processar_chamada_worker
from test_autonomy_worker_auth import AGORA, CFG, claims

HDR = {"Authorization": "Bearer tok", "X-CloudTasks-QueueName": "runner-fila"}
CORPO = json.dumps({"request_id": "req-1"}).encode()


class Exec:
    def __init__(self, ret=StatusRunner.CONCLUIDO, exc=None):
        self.ret, self.exc, self.chamadas = ret, exc, []

    def __call__(self, rid):
        self.chamadas.append(rid)
        if self.exc:
            raise self.exc
        return self.ret


def chamar(headers=HDR, corpo=CORPO, verificar=None, ex=None, cfg=CFG):
    ex = ex or Exec()
    verificar = verificar or (lambda t: claims())
    return processar_chamada_worker(headers, corpo, cfg, AGORA, verificar, ex), ex


class TestWorkerHttp(unittest.TestCase):
    def test_ok_executa_com_request_id(self):
        r, ex = chamar()
        self.assertEqual((r.status_http, r.codigo), (200, "concluido"))
        self.assertEqual(ex.chamadas, ["req-1"])

    def test_status_do_runner(self):
        for st, http in [(StatusRunner.AGUARDANDO, 200), (StatusRunner.PAUSADO_LIMITE, 200),
                         (StatusRunner.FALHA, 200), (StatusRunner.RETENTAR, 503)]:
            r, _ = chamar(ex=Exec(st))
            self.assertEqual(r.status_http, http, st)

    def test_sem_token_nao_executa(self):
        for h in [{}, {"Authorization": "Basic x"}, {"Authorization": "Bearer "},
                  {"Authorization": "Bearer  x"}, None, "x"]:
            r, ex = chamar(headers=h)
            self.assertEqual(r.status_http, 401, h)
            self.assertEqual(ex.chamadas, [])

    def test_token_invalido_e_excecao_na_verificacao(self):
        def ruim(_):
            raise ValueError("segredo-do-token")
        r, ex = chamar(verificar=ruim)
        self.assertEqual((r.status_http, r.codigo), (401, "token_invalido"))
        self.assertNotIn("segredo", r.codigo)
        self.assertEqual(ex.chamadas, [])

    def test_nao_autorizado_nao_le_corpo_nem_executa(self):
        r, ex = chamar(verificar=lambda t: claims(aud="outra"), corpo=b"lixo")
        self.assertEqual((r.status_http, r.codigo), (403, "audience_invalida"))
        self.assertEqual(ex.chamadas, [])
        r, _ = chamar(headers={"Authorization": "Bearer t"})
        self.assertEqual(r.codigo, "fila_invalida")
        r, _ = chamar(verificar=lambda t: claims(exp=(AGORA - timedelta(1)).timestamp()))
        self.assertEqual(r.codigo, "token_expirado")

    def test_corpo_invalido(self):
        for c in [None, b"", b"{", b"[]", b'{"request_id":1}', b'{"request_id":"a/b"}',
                  b'{"request_id":" a"}', b'{"request_id":"a","x":1}', b"{}",
                  b'\xff', b"x" * (MAX_CORPO_BYTES + 1), '{"request_id":"é"}', 5]:
            r, ex = chamar(corpo=c)
            self.assertEqual((r.status_http, r.codigo), (400, "corpo_invalido"), c)
            self.assertEqual(ex.chamadas, [])

    def test_corpo_str_ascii_ok(self):
        r, ex = chamar(corpo='{"request_id":"r2"}')
        self.assertEqual(r.status_http, 200)
        self.assertEqual(ex.chamadas, ["r2"])

    def test_excecao_da_execucao_nao_vaza(self):
        r, _ = chamar(ex=Exec(exc=RuntimeError("senha123")))
        self.assertEqual((r.status_http, r.codigo), (500, "erro_execucao"))

    def test_status_invalido(self):
        r, _ = chamar(ex=Exec(ret="concluido"))
        self.assertEqual((r.status_http, r.codigo), (500, "status_invalido"))

    def test_config_invalida_nega(self):
        from autonomy.worker_auth import ConfigWorker
        r, ex = chamar(cfg=ConfigWorker("", "", ""))
        self.assertEqual(r.status_http, 403)
        self.assertEqual(ex.chamadas, [])

    def test_hostis_e_agora_ingenuo(self):
        from collections.abc import Mapping
        from datetime import datetime

        class Ruim(Mapping):
            def __getitem__(s, k): raise KeyError
            def __iter__(s): raise RuntimeError("x")
            def __len__(s): return 1
        r, ex = chamar(headers=Ruim())
        self.assertEqual(r.status_http, 401)

        class Claims(dict):
            def get(s, *a): raise ZeroDivisionError
        r, ex = chamar(verificar=lambda t: Claims(a=1))
        self.assertEqual((r.status_http, ex.chamadas), (403, []))
        chamadas = []
        with self.assertRaises(ValueError):
            processar_chamada_worker(HDR, CORPO, CFG, datetime(2026, 1, 1),
                                     lambda t: chamadas.append(t), Exec())
        self.assertEqual(chamadas, [])

    def test_sem_bearer_nao_verifica_e_id_nao_ascii(self):
        vistos = []
        processar_chamada_worker({}, CORPO, CFG, AGORA, lambda t: vistos.append(t), Exec())
        self.assertEqual(vistos, [])
        for c in [b'{"request_id":"\\u00e9"}', bytearray(b'{"request_id":"\xc3\xa9"}')]:
            r, ex = chamar(corpo=c)
            self.assertEqual((r.status_http, ex.chamadas), (400, []), c)
        r, _ = chamar(corpo=bytearray(CORPO))
        self.assertEqual(r.status_http, 200)
        r, _ = chamar(ex=Exec(ret=None))
        self.assertEqual(r.codigo, "status_invalido")


if __name__ == "__main__":
    unittest.main()
