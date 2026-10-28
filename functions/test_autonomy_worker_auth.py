import unittest
from datetime import datetime, timedelta, timezone

from autonomy.worker_auth import ConfigWorker, autorizar_chamada_worker

AGORA = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
CFG = ConfigWorker("runner@proj.iam.gserviceaccount.com", "https://w.example/run", "runner-fila")


def claims(**kw):
    base = {
        "iss": "https://accounts.google.com",
        "aud": CFG.audience,
        "exp": (AGORA + timedelta(minutes=5)).timestamp(),
        "email": CFG.service_account_email,
        "email_verified": True,
    }
    base.update(kw)
    return base


HDR = {"X-CloudTasks-QueueName": "runner-fila"}


class TestAuthWorker(unittest.TestCase):
    def test_ok(self):
        d = autorizar_chamada_worker(claims(), HDR, CFG, AGORA)
        self.assertTrue(d.autorizado)

    def test_header_case_insensitive_e_email_case(self):
        d = autorizar_chamada_worker(
            claims(email=CFG.service_account_email.upper()), {"x-cloudtasks-queuename": "runner-fila"}, CFG, AGORA)
        self.assertTrue(d.autorizado)

    def test_recusas(self):
        casos = {
            "emissor_invalido": claims(iss="https://evil.example"),
            "audience_invalida": claims(aud="https://outro"),
            "token_expirado": claims(exp=AGORA.timestamp()),
            "exp_invalido": claims(exp="9999999999"),
            "email_nao_verificado": claims(email_verified="true"),
            "identidade_nao_permitida": claims(email="outro@proj.iam.gserviceaccount.com"),
        }
        for motivo, c in casos.items():
            d = autorizar_chamada_worker(c, HDR, CFG, AGORA)
            self.assertFalse(d.autorizado, motivo)
            self.assertEqual(d.motivo, motivo)

    def test_exp_bool_nan(self):
        for exp in (True, float("nan"), float("inf"), 10**1000, -10**1000, None):
            self.assertEqual(autorizar_chamada_worker(claims(exp=exp), HDR, CFG, AGORA).motivo, "exp_invalido")

    def test_sem_token_ou_cabecalho(self):
        for c in (None, {}, "tok", []):
            self.assertEqual(autorizar_chamada_worker(c, HDR, CFG, AGORA).motivo, "sem_token")
        self.assertEqual(autorizar_chamada_worker(claims(), None, CFG, AGORA).motivo, "sem_cabecalhos")
        self.assertEqual(autorizar_chamada_worker(claims(), {}, CFG, AGORA).motivo, "fila_invalida")
        self.assertEqual(
            autorizar_chamada_worker(claims(), {"X-CloudTasks-QueueName": "outra"}, CFG, AGORA).motivo,
            "fila_invalida")

    def test_config_invalida_nunca_autoriza(self):
        for cfg in (None, ConfigWorker("", CFG.audience, "f"), ConfigWorker("a@b", " x", "f"),
                    ConfigWorker("a@b", "u", None)):
            d = autorizar_chamada_worker(claims(), HDR, cfg, AGORA)
            self.assertEqual((d.autorizado, d.motivo), (False, "config_invalida"))

    def test_tipos_hostis_e_unicode(self):
        for iss in (["a"], {}):
            self.assertEqual(autorizar_chamada_worker(claims(iss=iss), HDR, CFG, AGORA).motivo, "emissor_invalido")
        cfg = ConfigWorker("k@x.com", CFG.audience, "runner-fila")
        d = autorizar_chamada_worker(claims(email="\u212a@x.com"), HDR, cfg, AGORA)
        self.assertEqual(d.motivo, "identidade_nao_permitida")

    def test_motivo_nao_ecoa_token(self):
        d = autorizar_chamada_worker(claims(email="segredo@x"), HDR, CFG, AGORA)
        self.assertNotIn("segredo", d.motivo)

    def test_agora_sem_fuso(self):
        with self.assertRaises(ValueError):
            autorizar_chamada_worker(claims(), HDR, CFG, datetime(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
