"""Check-in semanal da estratégia (A8)."""
import unittest
from datetime import date, datetime

import checkin_estrategia as ce


def _meta(objetivo, perfil, pausada=False):
    return {"objetivo": objetivo, "pausada": pausada, "perfil": perfil}


PESO_ATRASADO = {"estado": "atrasado", "proximo_marco": {"data": "2026-12-30", "descricao": "89,9 kg"},
                 "indicadores": [{"chave": "peso", "rotulo": "Peso", "atual": 91.5, "esperado_hoje": 90.8,
                                  "proximo_marco": {"data": "2026-12-30", "valor": 89.9}, "unidade": "kg",
                                  "em_centavos": False, "estado": "atrasado", "origem": "automatica"}],
                 "marcos_sem_numero": []}
GUARDADO_NO_PERFIL = {"estado": "no_perfil", "proximo_marco": None,
                      "indicadores": [{"chave": "guardado", "rotulo": "Guardado", "atual": 450000, "esperado_hoje": 450000,
                                       "proximo_marco": {"data": "2026-12-30", "valor": 600000}, "unidade": "R$",
                                       "em_centavos": True, "estado": "no_perfil", "origem": "automatica"}],
                      "marcos_sem_numero": []}
SISTEMAS_VENCIDO = {"estado": "atrasado", "proximo_marco": None, "indicadores": [],
                    "marcos_sem_numero": [{"id": "s1", "descricao": "Tabela de preços aprovada",
                                           "dataAlvo": "2026-11-30", "concluido": False, "estado": "atrasado"}]}
HOJE = date(2026, 12, 13)


class TestQuandoEnviar(unittest.TestCase):
    def test_domingo_18h_a_partir_de_08_11_e_uma_vez(self):
        cfg = ce.configuracao({})
        self.assertTrue(ce.deve_enviar(datetime(2026, 11, 8, 18, 5), cfg, False))
        self.assertFalse(ce.deve_enviar(datetime(2026, 11, 1, 18, 5), cfg, False))  # antes do primeiro
        self.assertFalse(ce.deve_enviar(datetime(2026, 11, 8, 17, 5), cfg, False))
        self.assertFalse(ce.deve_enviar(datetime(2026, 11, 9, 18, 5), cfg, False))  # segunda
        self.assertFalse(ce.deve_enviar(datetime(2026, 11, 8, 18, 5), cfg, True))   # já enviado

    def test_horario_vem_da_configuracao(self):
        cfg = ce.configuracao({"estrategia": {"checkin": {"dia_semana": 5, "hora": 9}}})
        self.assertTrue(ce.deve_enviar(datetime(2026, 11, 14, 9, 5), cfg, False))  # sábado 9h
        self.assertFalse(ce.deve_enviar(datetime(2026, 11, 15, 18, 5), cfg, False))
        self.assertFalse(ce.deve_enviar(datetime(2026, 11, 8, 18, 5), ce.configuracao({"estrategia": {"checkin": {"ativo": False}}}), False))


class TestAtivoEmTexto(unittest.TestCase):
    def test_false_em_texto_desliga(self):
        cfg = ce.configuracao({"estrategia": {"checkin": {"ativo": "false"}}})
        self.assertFalse(ce.deve_enviar(datetime(2026, 11, 8, 18, 5), cfg, False))


class TestMensagem(unittest.TestCase):
    def test_por_meta_atual_esperado_e_estado_com_um_ajuste(self):
        msg = ce.montar_mensagem([_meta("Saúde", PESO_ATRASADO), _meta("Financeira", GUARDADO_NO_PERFIL)], HOJE)
        self.assertIn("• Saúde: atrasado", msg)
        self.assertIn("Peso: 91,5 kg (esperado 90,8 kg) — atrasado", msg)
        self.assertIn("Guardado: R$ 4.500 (esperado R$ 4.500) — no perfil", msg)
        self.assertEqual(msg.count("Ajuste sugerido"), 1)
        self.assertIn("1,6 kg até 89,9 kg em 30/12", msg)

    def test_sem_atraso_nao_ha_ajuste_e_marco_vencido_vira_ajuste(self):
        self.assertNotIn("Ajuste", ce.montar_mensagem([_meta("Financeira", GUARDADO_NO_PERFIL)], HOJE))
        msg = ce.montar_mensagem([_meta("Sistemas", SISTEMAS_VENCIDO)], HOJE)
        self.assertIn("Marco vencido: Tabela de preços aprovada", msg)
        self.assertIn("'Tabela de preços aprovada' venceu em 30/11", msg)

    def test_todas_pausadas_ou_sem_perfil_nao_envia_nada(self):
        self.assertIsNone(ce.montar_mensagem([_meta("MAGO", PESO_ATRASADO, pausada=True)], HOJE))
        self.assertIsNone(ce.montar_mensagem([_meta("Legada", None)], HOJE))

    def test_nunca_sugere_ligacao_call_ou_reuniao(self):
        for metas in ([_meta("Saúde", PESO_ATRASADO)], [_meta("Sistemas", SISTEMAS_VENCIDO)]):
            self.assertIsNone(ce._PROIBIDO.search(ce.montar_mensagem(metas, HOJE)))
        self.assertTrue(ce._PROIBIDO.search("marque uma reunião"))


if __name__ == "__main__":
    unittest.main()
