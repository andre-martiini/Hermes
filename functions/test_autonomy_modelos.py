import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from autonomy.modelos import (
    ConfigModelos, ErroConfigModelos, ErroSelecao, ModeloEscolhido, MotivoSelecao,
    TarifaModelo, VALIDADE_MAXIMA_DIAS, custo_chamada, id_modelo_valido, selecionar_modelo,
    taxa_acerto_cache,
)

AGORA = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
A, B = "claude-opus-5-5", "claude-sonnet-5-5"


def tarifa(mid, **kw):
    base = dict(modelo_id=mid, versao="2026-10", entrada="10", saida="50", cache_leitura="1", cache_escrita="12.5")
    base.update(kw)
    return TarifaModelo(**base)


def config(**kw):
    base = dict(
        papeis={"planner": (A, B)},
        tarifas={A: tarifa(A), B: tarifa(B, entrada="3", saida="15")},
        validado_em=AGORA - timedelta(days=1),
    )
    base.update(kw)
    return ConfigModelos(**base)


class IdModeloTest(unittest.TestCase):
    def test_aceita_ids_versionados_e_rejeita_alias_movel(self):
        self.assertTrue(id_modelo_valido(A))
        for ruim in ("claude-latest", "claude-opus-latest", "claude-sonnet.latest", "claude-a.default", "gpt-5", "claude-", "", None, 5, "claude-opus-5-5 ", "CLAUDE-x-1"):
            self.assertFalse(id_modelo_valido(ruim), ruim)


class ConfigTest(unittest.TestCase):
    def test_config_valida(self):
        self.assertEqual(config().papeis["planner"], (A, B))

    def test_modelo_sem_tarifa_ou_com_tarifa_trocada_falha(self):
        with self.assertRaises(ErroConfigModelos):
            config(tarifas={A: tarifa(A)})
        with self.assertRaises(ErroConfigModelos):
            config(tarifas={A: tarifa(A), B: tarifa(A)})

    def test_papel_ruim(self):
        for papeis in ({}, {"planner": ()}, {"planner": (A, A)}, {"planner": A}, {"Planner X": (A,)}, {"planner": ("claude-latest",)}):
            with self.assertRaises(ErroConfigModelos, msg=papeis):
                config(papeis=papeis)

    def test_validado_em_sem_fuso(self):
        with self.assertRaises(ErroConfigModelos):
            config(validado_em=datetime(2026, 10, 1))

    def test_tarifa_rejeita_float_negativo_nan_e_bool(self):
        for v in (0.1, -1, "nan", "inf", True, "abc", None):
            with self.assertRaises(ErroConfigModelos, msg=v):
                tarifa(A, entrada=v)
        with self.assertRaises(ErroConfigModelos):
            tarifa(A, versao=" ")
        with self.assertRaises(ErroConfigModelos):
            tarifa("claude-latest")

    def test_config_nao_aceita_mutacao_posterior_do_dicionario_original(self):
        papeis = {"planner": [A]}
        c = config(papeis=papeis)
        papeis["planner"].append("claude-latest")
        self.assertEqual(c.papeis["planner"], (A,))


class SelecaoTest(unittest.TestCase):
    def test_titular(self):
        r = selecionar_modelo(config(), "planner", AGORA)
        self.assertEqual((r.modelo_id, r.rotacionado), (A, False))

    def test_rotacao_quando_titular_indisponivel(self):
        r = selecionar_modelo(config(), "planner", AGORA, indisponiveis={A})
        self.assertIsInstance(r, ModeloEscolhido)
        self.assertEqual((r.modelo_id, r.rotacionado), (B, True))
        self.assertEqual(r.tarifa.entrada, Decimal(3))

    def test_todos_indisponiveis_e_erro_tipado_sem_padrao_escondido(self):
        r = selecionar_modelo(config(), "planner", AGORA, indisponiveis=[A, B])
        self.assertEqual(r, ErroSelecao(MotivoSelecao.TODOS_INDISPONIVEIS))

    def test_papel_desconhecido(self):
        for p in ("outro", None, 3):
            self.assertEqual(selecionar_modelo(config(), p, AGORA).motivo, MotivoSelecao.PAPEL_DESCONHECIDO)

    def test_validacao_vencida_no_limite(self):
        c = config(validado_em=AGORA - timedelta(days=VALIDADE_MAXIMA_DIAS))
        self.assertIsInstance(selecionar_modelo(c, "planner", AGORA), ModeloEscolhido)
        c = config(validado_em=AGORA - timedelta(days=VALIDADE_MAXIMA_DIAS, seconds=1))
        self.assertEqual(selecionar_modelo(c, "planner", AGORA).motivo, MotivoSelecao.VALIDACAO_VENCIDA)

    def test_validado_no_futuro_ou_agora_anterior_e_rejeitado(self):
        c = config(validado_em=AGORA + timedelta(days=3000))
        self.assertEqual(selecionar_modelo(c, "planner", AGORA).motivo, MotivoSelecao.VALIDACAO_VENCIDA)
        c = config(validado_em=AGORA + timedelta(minutes=1))
        self.assertIsInstance(selecionar_modelo(c, "planner", AGORA), ModeloEscolhido)

    def test_indisponiveis_str_ou_invalido(self):
        for ruim in (A, b"x", None, 5):
            with self.assertRaises(ValueError, msg=ruim):
                selecionar_modelo(config(), "planner", AGORA, ruim)

    def test_agora_invalido_e_erro_mesmo_com_papel_desconhecido(self):
        with self.assertRaises(ValueError):
            selecionar_modelo(config(), "outro", datetime(2026, 10, 27))
        with self.assertRaises(ValueError):
            selecionar_modelo(config(), "planner", datetime.min.replace(tzinfo=timezone(timedelta(hours=1))))

    def test_config_e_hasheavel(self):
        hash(config())

    def test_contexto_global_nao_afeta_preco_nem_taxa(self):
        import decimal
        with decimal.localcontext() as c:
            c.prec = 3
            c.traps[decimal.Inexact] = True
            self.assertEqual(tarifa(A, entrada="3.123456").entrada, Decimal("3.123456"))
            self.assertEqual(str(taxa_acerto_cache(2, 1))[:6], "0.3333")

    def test_custo_valida_tarifa_e_teto_de_tokens(self):
        with self.assertRaises(ValueError):
            custo_chamada(None, 1, 1)
        with self.assertRaises(ValueError):
            custo_chamada(tarifa(A), 10**13, 0)

    def test_config_imutavel(self):
        c = config()
        with self.assertRaises(TypeError):
            c.papeis["planner"] = ("claude-latest",)
        with self.assertRaises(TypeError):
            c.tarifas["x"] = None

    def test_config_entradas_estranhas_sao_erro_tipado(self):
        for kw in (dict(papeis=[1]), dict(tarifas=None), dict(papeis={"planner": [["x"]]}),
                   dict(papeis={"planner": {A, B}}), dict(tarifas={A: object(), B: tarifa(B)})):
            with self.assertRaises(ErroConfigModelos, msg=kw):
                config(**kw)

    def test_datetime_com_utcoffset_none_e_rejeitado(self):
        from datetime import tzinfo

        class Z(tzinfo):
            def utcoffset(self, dt): return None
            def dst(self, dt): return None
            def tzname(self, dt): return "Z"
        with self.assertRaises(ErroConfigModelos):
            config(validado_em=datetime(2026, 10, 1, tzinfo=Z()))
        with self.assertRaises(ValueError):
            selecionar_modelo(config(), "planner", datetime(2026, 10, 27, tzinfo=Z()))

    def test_agora_sem_fuso(self):
        with self.assertRaises(ValueError):
            selecionar_modelo(config(), "planner", datetime(2026, 10, 27))


class CustoTest(unittest.TestCase):
    def test_custo_com_cache(self):
        t = tarifa(A)
        # 100k entrada*10 + 10k saida*50 + 200k leitura*1 + 50k escrita*12.5 = 1e6+5e5+2e5+6.25e5 = 2.325e6 / 1e6
        self.assertEqual(custo_chamada(t, 100_000, 10_000, 200_000, 50_000), Decimal("2.325"))

    def test_expoente_absurdo_e_preco_gigante_rejeitados(self):
        for v in ("1E+999999999", "1e-999999999", "1000001", "0.0000000000001"):
            with self.assertRaises(ErroConfigModelos, msg=v):
                tarifa(A, entrada=v)

    def test_custo_independe_do_contexto_decimal_global(self):
        import decimal
        antigo = decimal.getcontext().prec
        decimal.getcontext().prec = 3
        try:
            self.assertEqual(custo_chamada(tarifa(A, entrada="1"), 123_456, 0), Decimal("0.123456"))
        finally:
            decimal.getcontext().prec = antigo

    def test_zero_e_validacao(self):
        self.assertEqual(custo_chamada(tarifa(A), 0, 0), Decimal(0))
        for args in ((-1, 0), (1.5, 0), (True, 0), (0, "1")):
            with self.assertRaises(ValueError, msg=args):
                custo_chamada(tarifa(A), *args)

    def test_taxa_acerto_cache(self):
        self.assertEqual(taxa_acerto_cache(100, 300), Decimal("0.75"))
        self.assertEqual(taxa_acerto_cache(0, 0), Decimal(0))
        self.assertEqual(taxa_acerto_cache(100, 100, 200), Decimal("0.25"))
        with self.assertRaises(ValueError):
            taxa_acerto_cache(-1, 0)


if __name__ == "__main__":
    unittest.main()
