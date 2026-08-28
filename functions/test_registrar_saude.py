"""Escrita no modulo Saude.

Duas coisas justificam estes testes acima das outras:

1. **Idempotencia por dia.** Retorno ambiguo faz quem chama repetir a chamada.
   Foi assim que um plano de acao virou 994 etapas de um caractere em 28/08 —
   tres tentativas seguidas. Peso registrado duas vezes tem de atualizar, nunca
   duplicar, senao a media de sete dias passa a contar o mesmo dia duas vezes.

2. **Recusa de valor implausivel.** Um numero errado no historico contamina a
   media e a projecao da meta, e ninguem procura por ele. O custo de recusar e
   uma nova chamada; o de aceitar e um dado falso que nunca mais e questionado.

O criterio de aceite do pedido esta em `TestGravaELeDeVolta`: depois da escrita,
`consultar_saude` daquele dia reflete o valor.
"""

import unittest
from datetime import date, timedelta

from tools import registrar_saude as rs

HOJE = date.today().isoformat()
AMANHA = (date.today() + timedelta(days=1)).isoformat()


class _Doc:
    def __init__(self, colecao, id_, dados=None):
        self._col = colecao
        self.id = id_
        self.reference = self
        self.exists = dados is not None
        self._d = dados

    def to_dict(self):
        return dict(self._d) if self._d else {}

    def get(self):
        return _Doc(self._col, self.id, self._col.dados.get(self.id))

    def set(self, valores, merge=False):
        atual = self._col.dados.get(self.id) if merge else None
        self._col.dados[self.id] = {**(atual or {}), **valores}


class _Query:
    def __init__(self, colecao, pares):
        self._col, self._pares = colecao, pares

    def where(self, campo, op, valor):
        return _Query(self._col, [p for p in self._pares if p[1].get(campo) == valor])

    def limit(self, n):
        return _Query(self._col, self._pares[:n])

    def stream(self):
        return [_Doc(self._col, i, d) for i, d in self._pares]


class _Colecao:
    def __init__(self, dados=None):
        self.dados = dict(dados or {})
        self._seq = 0

    def where(self, *a):
        return _Query(self, list(self.dados.items())).where(*a)

    def stream(self):
        return _Query(self, list(self.dados.items())).stream()

    def document(self, doc_id=None):
        if doc_id is None:
            self._seq += 1
            doc_id = f"auto{self._seq}"
        return _Doc(self, doc_id, self.dados.get(doc_id))


class _Db:
    def __init__(self):
        self.cols = {}

    def collection(self, nome):
        return self.cols.setdefault(nome, _Colecao())


class _Ctx:
    def __init__(self):
        self.db = _Db()
        self.user_uid = "uid"


class TestIdempotencia(unittest.TestCase):
    """Registrar de novo atualiza; nunca cria um segundo registro do mesmo dia."""

    def test_peso_duas_vezes_nao_duplica(self):
        ctx = _Ctx()
        rs.registrar(ctx, {"peso": 93.7})
        rs.registrar(ctx, {"peso": 93.4})
        pesos = ctx.db.cols[rs.COL_PESOS].dados
        self.assertEqual(len(pesos), 1, "criou um segundo registro para o mesmo dia")
        self.assertEqual(list(pesos.values())[0]["weight"], 93.4)

    def test_dor_manha_e_noite_convivem_no_mesmo_dia(self):
        """Escrever a dor da noite não pode apagar a da manhã."""
        ctx = _Ctx()
        rs.registrar(ctx, {"dor_manha": 3})
        rs.registrar(ctx, {"dor_noite": 5})
        dor = ctx.db.cols[rs.COL_LOGS].dados[HOJE]["pain"]
        self.assertEqual((dor["morning"], dor["evening"]), (3, 5))

    def test_escrita_preserva_campos_que_nao_toca(self):
        ctx = _Ctx()
        ctx.db.cols[rs.COL_LOGS] = _Colecao({HOJE: {
            "walkBlocks": [{"distance": 2.6}], "pain": {"morning": 4}}})
        rs.registrar(ctx, {"dor_noite": 6})
        doc = ctx.db.cols[rs.COL_LOGS].dados[HOJE]
        self.assertEqual(doc["walkBlocks"], [{"distance": 2.6}], "apagou a caminhada")
        self.assertEqual(doc["pain"]["morning"], 4, "apagou a dor da manhã")


class TestRecusaValorImplausivel(unittest.TestCase):

    def test_peso_absurdo(self):
        r = rs.registrar(_Ctx(), {"peso": 937})
        self.assertFalse(r["aplicado"])
        self.assertIn("peso", r["erro"])
        self.assertIn("937", r["erro"])

    def test_dor_fora_da_escala(self):
        self.assertFalse(rs.registrar(_Ctx(), {"dor_manha": 15})["aplicado"])
        self.assertFalse(rs.registrar(_Ctx(), {"dor_noite": -1})["aplicado"])

    def test_data_no_futuro(self):
        r = rs.registrar(_Ctx(), {"peso": 93, "data": AMANHA})
        self.assertFalse(r["aplicado"])
        self.assertIn("futuro", r["erro"])

    def test_nada_e_gravado_quando_recusa(self):
        ctx = _Ctx()
        rs.registrar(ctx, {"peso": 937})
        self.assertNotIn(rs.COL_PESOS, ctx.db.cols)

    def test_texto_no_lugar_de_numero(self):
        r = rs.registrar(_Ctx(), {"peso": "noventa e tres"})
        self.assertFalse(r["aplicado"])

    def test_virgula_decimal_e_aceita(self):
        """'93,4' é como se escreve em português; recusar seria pedantismo."""
        ctx = _Ctx()
        r = rs.registrar(ctx, {"peso": "93,4"})
        self.assertEqual(r["campos_alterados"], ["peso"])
        self.assertEqual(list(ctx.db.cols[rs.COL_PESOS].dados.values())[0]["weight"], 93.4)

    def test_chamada_sem_valor_algum(self):
        r = rs.registrar(_Ctx(), {})
        self.assertFalse(r["aplicado"])
        self.assertIn("peso", r["erro"])


class TestCamposQueNaoExistem(unittest.TestCase):
    """Pedidos que não têm onde morar: recusar nomeando a alternativa.

    Gravá-los criaria campos que nenhuma tela lê — dado morto com aparência de
    registro, que é a forma mais cara de errar.
    """

    def test_passos_e_recusado_com_alternativa(self):
        r = rs.registrar(_Ctx(), {"passos": 8000})
        self.assertFalse(r["aplicado"])
        self.assertIn("caminhada", r["erro"])

    def test_sono_horas_aponta_para_qualidade(self):
        r = rs.registrar(_Ctx(), {"sono_horas": 7.5})
        self.assertIn("sono_qualidade", r["erro"])

    def test_ciatica_e_crise_apontam_para_o_checkin(self):
        self.assertIn("radicular", rs.registrar(_Ctx(), {"ciatica": True})["erro"])
        self.assertIn("triggers", rs.registrar(_Ctx(), {"crise": True})["erro"])

    def test_campo_inexistente_nao_grava_nada(self):
        ctx = _Ctx()
        rs.registrar(ctx, {"passos": 8000, "peso": 93.5})
        self.assertEqual(ctx.db.cols, {}, "gravou o peso apesar de recusar a chamada")


class TestRotinasDerivadas(unittest.TestCase):
    """Rotina cumprida não é gravada — é deduzida do dado (morning_summary)."""

    def test_peso_fecha_a_pesagem(self):
        self.assertEqual(rs.registrar(_Ctx(), {"peso": 93.5})["rotinas_concluidas"],
                         ["pesagem"])

    def test_dores_fecham_os_dois_checkins(self):
        r = rs.registrar(_Ctx(), {"dor_manha": 2, "dor_noite": 3})
        self.assertEqual(r["rotinas_concluidas"], ["checkin_manha", "checkin_noite"])

    def test_calorias_nao_fecham_rotina(self):
        self.assertEqual(rs.registrar(_Ctx(), {"calorias": 2100})["rotinas_concluidas"], [])


class TestGravaELeDeVolta(unittest.TestCase):
    """O critério de aceite do pedido: escreve, e a leitura reflete."""

    def test_peso_gravado_aparece_em_health_weights_com_a_data(self):
        ctx = _Ctx()
        rs.registrar(ctx, {"peso": 93.7, "data": "2026-08-20"})
        doc = list(ctx.db.cols[rs.COL_PESOS].dados.values())[0]
        self.assertEqual((doc["date"], doc["weight"]), ("2026-08-20", 93.7))

    def test_cintura_vai_para_health_waist_no_campo_cm(self):
        """A coleção da cintura usa `cm`, não `waist` — quem lê é o resumo semanal."""
        ctx = _Ctx()
        rs.registrar(ctx, {"cintura": 104.5})
        doc = list(ctx.db.cols[rs.COL_CINTURA].dados.values())[0]
        self.assertEqual(doc["cm"], 104.5)

    def test_dor_vai_para_o_log_do_dia_na_estrutura_do_checkin(self):
        ctx = _Ctx()
        rs.registrar(ctx, {"dor_manha": 2, "dor_pos_caminhada": 1})
        dor = ctx.db.cols[rs.COL_LOGS].dados[HOJE]["pain"]
        self.assertEqual((dor["morning"], dor["afterWalk"]), (2, 1))

    def test_sono_vai_para_sleepQuality(self):
        ctx = _Ctx()
        rs.registrar(ctx, {"sono_qualidade": 4, "acordou_com_dor": True})
        sono = ctx.db.cols[rs.COL_LOGS].dados[HOJE]["sleepQuality"]
        self.assertEqual((sono["quality"], sono["wokeInPain"]), (4, True))

    def test_retorno_traz_campos_alterados(self):
        r = rs.registrar(_Ctx(), {"peso": 93.5, "dor_noite": 3})
        self.assertEqual(r["status"], "completed")
        self.assertEqual(sorted(r["campos_alterados"]), ["dor_noite", "peso"])


if __name__ == "__main__":
    unittest.main()
