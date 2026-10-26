import unittest
from datetime import datetime, timedelta, timezone

from autonomy.runner import (
    ChamadaFerramenta, Concluir, ErroModelo, Esperar, LimitesRunner,
    ResultadoFerramenta, SaidaPlanner, StatusRunner, TipoErroModelo, executar_lote,
)

PERM = frozenset({"ler", "gravar"})


class Fake:
    def __init__(self, saidas):
        self.saidas = list(saidas)
        self.chamadas = 0

    def planejar(self, contexto, historico):
        self.chamadas += 1
        s = self.saidas.pop(0)
        if isinstance(s, Exception):
            raise s
        return s


class Exec:
    def __init__(self, falha=False):
        self.vistas = []
        self.falha = falha

    def executar(self, c):
        self.vistas.append(c.nome)
        if self.falha:
            raise RuntimeError("x")
        return ResultadoFerramenta(ok=True)


def lote(*nomes, tokens=10):
    return SaidaPlanner(chamadas=tuple(ChamadaFerramenta(n) for n in nomes), tokens=tokens)


class RunnerTest(unittest.TestCase):
    def rodar(self, saidas, executor=None, limites=None, agora=None):
        kw = {"agora": agora} if agora else {}
        return executar_lote(Fake(saidas), executor or Exec(), {}, PERM, limites, **kw)

    def test_conclui_apos_ferramentas(self):
        ex = Exec()
        r = self.rodar([lote("ler", "gravar"), SaidaPlanner(desfecho=Concluir("ok"))], ex)
        self.assertEqual(r.status, StatusRunner.CONCLUIDO)
        self.assertEqual(ex.vistas, ["ler", "gravar"])
        self.assertEqual((r.rodadas, r.ferramentas), (2, 2))

    def test_esperar_termina_sem_bloquear(self):
        r = self.rodar([SaidaPlanner(desfecho=Esperar("resposta do fornecedor"))])
        self.assertEqual(r.status, StatusRunner.AGUARDANDO)
        self.assertEqual(r.espera.condicao, "resposta do fornecedor")

    def test_limite_rodadas_pausa_nunca_conclui(self):
        r = self.rodar([lote("ler")] * 5, limites=LimitesRunner(max_rodadas=3))
        self.assertEqual((r.status, r.motivo), (StatusRunner.PAUSADO_LIMITE, "rodadas"))
        self.assertEqual(len(r.historico), 3)

    def test_limite_ferramentas_antes_de_executar(self):
        ex = Exec()
        r = self.rodar([lote("ler", "ler"), lote("ler", "ler")], ex, LimitesRunner(max_ferramentas=3))
        self.assertEqual((r.status, r.motivo), (StatusRunner.PAUSADO_LIMITE, "ferramentas"))
        self.assertEqual(len(ex.vistas), 2)

    def test_limite_tokens(self):
        r = self.rodar([lote("ler", tokens=100)] * 3, limites=LimitesRunner(max_tokens=100))
        self.assertEqual((r.status, r.motivo), (StatusRunner.PAUSADO_LIMITE, "tokens"))

    def test_limite_duracao(self):
        t = [datetime(2026, 1, 1, tzinfo=timezone.utc)]

        def agora():
            t[0] += timedelta(seconds=100)
            return t[0]

        r = self.rodar([lote("ler")] * 5, limites=LimitesRunner(max_duracao_segundos=250), agora=agora)
        self.assertEqual((r.status, r.motivo), (StatusRunner.PAUSADO_LIMITE, "duracao"))

    def test_erros_do_modelo(self):
        for tipo, esperado in [
            (TipoErroModelo.RATE_LIMIT, StatusRunner.RETENTAR),
            (TipoErroModelo.INDISPONIVEL, StatusRunner.RETENTAR),
            (TipoErroModelo.TIMEOUT, StatusRunner.RETENTAR),
            (TipoErroModelo.RECUSA, StatusRunner.FALHA),
            (TipoErroModelo.CONTEXTO_EXCEDIDO, StatusRunner.FALHA),
        ]:
            r = self.rodar([ErroModelo(tipo)])
            self.assertEqual(r.status, esperado, tipo)
            self.assertEqual(r.erro_modelo.tipo, tipo)

    def test_excecao_do_planner_vira_retentar(self):
        r = self.rodar([RuntimeError("boom")])
        self.assertEqual(r.status, StatusRunner.RETENTAR)

    def test_ferramenta_desconhecida_nao_executa_e_falha_na_reincidencia(self):
        ex = Exec()
        r = self.rodar([lote("apagar_tudo"), lote("apagar_tudo")], ex)
        self.assertEqual(r.status, StatusRunner.FALHA)
        self.assertEqual(ex.vistas, [])
        self.assertIn("ferramenta_desconhecida", r.motivo)

    def test_saida_invalida_recuperavel(self):
        r = self.rodar(["lixo", SaidaPlanner(desfecho=Concluir())])
        self.assertEqual(r.status, StatusRunner.CONCLUIDO)
        self.assertEqual(r.historico[0]["tipo"], "saida_invalida")

    def test_saidas_malformadas(self):
        casos = [
            SaidaPlanner(),
            SaidaPlanner(chamadas=(ChamadaFerramenta("ler"),), desfecho=Concluir()),
            SaidaPlanner(desfecho="x"),
            SaidaPlanner(chamadas=("ler",)),
            SaidaPlanner(chamadas=(ChamadaFerramenta("ler"),), tokens=-1),
        ]
        for c in casos:
            r = self.rodar([c, c])
            self.assertEqual(r.status, StatusRunner.FALHA, c)

    def test_excecao_do_executor_vira_erro_no_historico(self):
        r = self.rodar([lote("ler"), SaidaPlanner(desfecho=Concluir())], Exec(falha=True))
        self.assertEqual(r.status, StatusRunner.CONCLUIDO)
        self.assertFalse(r.historico[0]["ok"])

    def test_allowlist_str_rejeitada(self):
        with self.assertRaises(TypeError):
            executar_lote(Fake([]), Exec(), {}, "ler")

    def test_lote_maior_que_teto_falha_sem_executar(self):
        ex = Exec()
        r = self.rodar([lote("ler", "ler", "ler")], ex, LimitesRunner(max_ferramentas=2))
        self.assertEqual((r.status, r.motivo), (StatusRunner.FALHA, "lote_excede_max_ferramentas"))

    def test_erro_modelo_tipo_str_nao_levanta(self):
        r = self.rodar([ErroModelo("rate_limit")])
        self.assertEqual(r.status, StatusRunner.FALHA)

    def test_chamadas_gerador_rejeitadas(self):
        s = SaidaPlanner(chamadas=(c for c in [ChamadaFerramenta("ler")]))
        r = self.rodar([s, s])
        self.assertEqual(r.status, StatusRunner.FALHA)

    def test_tokens_estourados_nao_executam_ferramenta(self):
        ex = Exec()
        r = self.rodar([lote("ler", tokens=1000)], ex, LimitesRunner(max_tokens=100))
        self.assertEqual((r.status, r.motivo), (StatusRunner.PAUSADO_LIMITE, "tokens"))
        self.assertEqual(ex.vistas, [])

    def test_duracao_dentro_do_lote(self):
        t = [0]
        ag = lambda: datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=t[0])

        class Lento(Exec):
            def executar(self, c):
                t[0] += 100
                return super().executar(c)

        ex = Lento()
        r = self.rodar([lote(*["ler"] * 10)], ex, LimitesRunner(max_duracao_segundos=150), agora=ag)
        self.assertEqual((r.status, r.motivo), (StatusRunner.PAUSADO_LIMITE, "duracao"))
        self.assertEqual(len(ex.vistas), 2)

    def test_espera_sem_condicao_invalida(self):
        s = SaidaPlanner(desfecho=Esperar(None))
        self.assertEqual(self.rodar([s, s]).status, StatusRunner.FALHA)

    def test_limites_validados(self):
        for kw in ({"max_rodadas": 0}, {"max_tokens": True}, {"max_duracao_segundos": 0},
                   {"max_duracao_segundos": float("inf")}, {"max_duracao_segundos": 1e20}, {"max_duracao_segundos": 1e-7}):
            with self.assertRaises(ValueError):
                LimitesRunner(**kw)

    def test_retomada_com_historico_inicial(self):
        h = ({"tipo": "ferramenta", "nome": "ler", "ok": True, "erro": ""},)
        r = executar_lote(Fake([SaidaPlanner(desfecho=Concluir())]), Exec(), {}, PERM, historico_inicial=h)
        self.assertEqual(r.historico, h)


if __name__ == "__main__":
    unittest.main()
