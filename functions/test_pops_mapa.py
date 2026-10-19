"""Testes de P06 sub-entrega 8/N (passo 8): mapa de POPs ativos."""

import unittest

from autonomy import pops_mapa as pm


def _pop(pop_id, **campos):
    base = {"id": pop_id, "titulo": f"POP {pop_id}", "instrucao_sistema": "faça X", "gatilhos": ["a", "b"]}
    base.update(campos)
    return base


class TestMapa(unittest.TestCase):
    def test_marca_carregados_e_lista_nao_carregados(self):
        mapa = pm.montar_mapa_pops([_pop("p1"), _pop("p2"), _pop("p3")], ["p2"])
        self.assertEqual([e.id for e in mapa.nao_carregados], ["p1", "p3"])
        self.assertTrue(next(e for e in mapa.entradas if e.id == "p2").carregado)

    def test_sempre_ativo_primeiro_e_so_com_true_literal(self):
        mapa = pm.montar_mapa_pops(
            [_pop("a"), _pop("b", sempre_ativo=True), _pop("c", sempre_ativo="true"), _pop("d", sempre_ativo=1)],
            [],
        )
        self.assertEqual([e.id for e in mapa.entradas], ["b", "a", "c", "d"])
        self.assertEqual([e.id for e in mapa.sempre_ativos_nao_carregados], ["b"])

    def test_sem_instrucao_nao_entra_no_mapa(self):
        mapa = pm.montar_mapa_pops([_pop("p1", instrucao_sistema="  "), _pop("p2", instrucao_sistema=None), _pop("p3")], [])
        self.assertEqual([e.id for e in mapa.entradas], ["p3"])
        self.assertEqual(mapa.sem_instrucao, ("p1", "p2"))

    def test_entradas_invalidas_e_duplicadas_sao_contadas(self):
        mapa = pm.montar_mapa_pops([None, "x", {"titulo": "sem id"}, {"id": 5}, _pop("p1"), _pop("p1")], [])
        self.assertEqual(mapa.ignorados, 5)  
        self.assertEqual(len(mapa.entradas), 1)

    def test_titulo_ausente_usa_id_e_gatilhos_invalidos_contam_zero(self):
        mapa = pm.montar_mapa_pops([_pop("p1", titulo=None, gatilhos="texto"), _pop("p2", gatilhos=["x", "", 3, " y "])], [])
        por_id = {e.id: e for e in mapa.entradas}
        self.assertEqual(por_id["p1"].titulo, "p1")
        self.assertEqual(por_id["p1"].n_gatilhos, 0)
        self.assertEqual(por_id["p2"].n_gatilhos, 3)

    def test_gatilho_so_de_pontuacao_ou_acento_normaliza_como_matcher(self):
        mapa = pm.montar_mapa_pops([_pop("a", gatilhos=["?", "...", "!!"]), _pop("b", gatilhos=[None, "Ação"])], [])
        por_id = {e.id: e for e in mapa.entradas}
        self.assertEqual((por_id["a"].n_gatilhos, por_id["a"].alcancavel), (0, False))
        self.assertEqual(por_id["b"].n_gatilhos, 2)

    def test_id_em_branco_e_ignorado(self):
        mapa = pm.montar_mapa_pops([_pop(""), _pop("  ")], [])
        self.assertEqual((len(mapa.entradas), mapa.ignorados), (0, 2))

    def test_id_repetido_sem_instrucao_conta_uma_vez(self):
        mapa = pm.montar_mapa_pops([_pop("p1", instrucao_sistema=""), _pop("p1", instrucao_sistema=""), _pop("p1")], [])
        self.assertEqual((mapa.sem_instrucao, mapa.entradas, mapa.ignorados), (("p1",), (), 2))

    def test_alcancavel_so_com_sempre_ativo_ou_gatilho_util(self):
        mapa = pm.montar_mapa_pops(
            [_pop("a", gatilhos=[]), _pop("b", gatilhos="x"), _pop("c", gatilhos=[" "]), _pop("d", sempre_ativo=True, gatilhos=[]), _pop("e")],
            [],
        )
        self.assertEqual({e.id: e.alcancavel for e in mapa.entradas}, {"a": False, "b": False, "c": False, "d": True, "e": True})

    def test_id_com_espaco_casa_com_id_carregado_cru(self):
        mapa = pm.montar_mapa_pops([_pop(" p1")], [" p1"])
        self.assertTrue(mapa.entradas[0].carregado)

    def test_sempre_ativo_carregado_nao_e_nao_carregado(self):
        mapa = pm.montar_mapa_pops([_pop("a", sempre_ativo=True), _pop("b", sempre_ativo=True), _pop("c")], ["a"])
        self.assertEqual([e.id for e in mapa.nao_carregados], ["b", "c"])
        self.assertEqual([e.id for e in mapa.sempre_ativos_nao_carregados], ["b"])

    def test_ordem_estavel_com_ids_fora_de_ordem(self):
        mapa = pm.montar_mapa_pops(
            [_pop("z"), _pop("m", sempre_ativo=True), _pop("a"), _pop("b", sempre_ativo=True), _pop("y", instrucao_sistema=""), _pop("x", instrucao_sistema="")],
            [],
        )
        self.assertEqual([e.id for e in mapa.entradas], ["b", "m", "a", "z"])
        self.assertEqual(mapa.sem_instrucao, ("x", "y"))

    def test_id_repetido_vale_a_primeira_ocorrencia(self):
        mapa = pm.montar_mapa_pops([_pop("p1", titulo="primeiro"), _pop("p1", titulo="segundo")], [])
        self.assertEqual(mapa.entradas[0].titulo, "primeiro")

    def test_titulo_em_branco_e_espacos_sao_aparados(self):
        mapa = pm.montar_mapa_pops([_pop("p1", titulo="  ")], [])
        self.assertEqual(mapa.entradas[0].titulo, "p1")
        mapa = pm.montar_mapa_pops([_pop("p2", titulo="  Titulo  ")], [])
        self.assertEqual(mapa.entradas[0].titulo, "Titulo")

    def test_ids_carregados_invalidos_sao_ignorados(self):
        mapa = pm.montar_mapa_pops([_pop("p1")], [None, 1, ["p1"]])
        self.assertFalse(mapa.entradas[0].carregado)

    def test_entradas_vazias(self):
        mapa = pm.montar_mapa_pops(None, None)
        self.assertEqual((mapa.entradas, mapa.sem_instrucao, mapa.ignorados), ((), (), 0))

    def test_nao_altera_entrada(self):
        pops = [_pop("p1")]
        copia = [dict(p) for p in pops]
        pm.montar_mapa_pops(pops, ["p1"])
        self.assertEqual(pops, copia)


if __name__ == "__main__":
    unittest.main()
