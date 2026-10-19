"""`consultar_memoria_contextual` -- P06 sub-entrega 11/N."""

import unittest
from types import SimpleNamespace

from tools import consultar_memoria_contextual as cmc
from tools import hermes_tools


class _Snap:
    def __init__(self, id, dados):
        self.id, self._d = id, dados

    def to_dict(self):
        return self._d


class _Q:
    def __init__(self, snaps):
        self.snaps, self.n, self.depois = snaps, None, None

    def order_by(self, *_):
        return self

    def limit(self, n):
        self.n = n
        return self

    def start_after(self, snap):
        self.depois = snap.id
        return self

    def stream(self):
        docs = self.snaps
        if self.depois is not None:
            docs = [s for s in docs if s.id > self.depois]
        return iter(docs[: self.n])

    def __getattr__(self, nome):
        raise AssertionError(f"chamada proibida: {nome}")


class _Db:
    def __init__(self, snaps):
        self.q = _Q(snaps)

    def collection(self, nome):
        assert nome == "knowledge_nodes"
        return self.q


def _ctx(*docs):
    return SimpleNamespace(db=_Db([_Snap(i, d) for i, d in docs]))


HUMANO = {"texto_memoria": "Prefiro reuniões às terças com Mariana", "origem_fato": "declaracao_humana"}
LEGADO = {"texto_memoria": "Prefiro reuniões às terças com Mariana"}


class ConsultarMemoriaContextualTest(unittest.TestCase):
    def test_exige_consulta_ou_entidades(self):
        self.assertEqual(set(cmc.consultar(_ctx(), {})), {"erro"})
        self.assertEqual(set(cmc.consultar(_ctx(), {"consulta": "  ", "entidades": [1, ""]})), {"erro"})

    def test_autoridade_ordena_e_legado_avisa(self):
        r = cmc.consultar(_ctx(("a", LEGADO), ("b", HUMANO)), {"consulta": "reuniões terças"})
        self.assertEqual([f["doc_id"] for f in r["fatos"]], ["b", "a"])
        self.assertFalse(r["fatos"][0]["legado_sem_proveniencia"])
        self.assertTrue(r["fatos"][1]["legado_sem_proveniencia"])
        self.assertEqual(r["documentos_lidos"], 2)
        self.assertEqual(r["lacunas"], [])
        self.assertIn("nunca ordem", r["aviso"])

    def test_descartados_contados_por_razao_e_telemetria_fora(self):
        tel = {"texto_memoria": "reuniões terças", "origem_fato": "telemetria_uso"}
        sup = {"texto_memoria": "reuniões terças", "memoria_status": "superada"}
        r = cmc.consultar(_ctx(("t", tel), ("s", sup), ("h", HUMANO)), {"consulta": "reuniões"})
        self.assertEqual([f["doc_id"] for f in r["fatos"]], ["h"])
        self.assertEqual(r["descartados_por_razao"], {"superada": 1, "telemetria_nao_e_fato": 1})

    def test_sem_resultado_vira_lacuna(self):
        r = cmc.consultar(_ctx(("a", HUMANO)), {"consulta": "futebol"})
        self.assertEqual(r["fatos"], [])
        self.assertEqual(r["lacunas"], ["nenhum fato pertinente encontrado"])

    def test_limite_vale_entre_paginas(self):
        docs = [(f"d{i:03d}", {"texto_memoria": "reunião terça", "origem_fato": "declaracao_humana"}) for i in range(450)]
        r = cmc.consultar(_ctx(*docs), {"consulta": "reunião", "limite": 3})
        self.assertEqual(r["documentos_lidos"], 450)
        self.assertEqual([f["doc_id"] for f in r["fatos"]], ["d000", "d001", "d002"])

    def test_melhor_de_pagina_posterior_entra(self):
        docs = [(f"d{i:03d}", {"texto_memoria": "reunião", "origem_fato": "fonte_externa"}) for i in range(250)]
        docs.append(("z999", {"texto_memoria": "reunião", "origem_fato": "declaracao_humana"}))
        r = cmc.consultar(_ctx(*docs), {"consulta": "reunião", "limite": 1})
        self.assertEqual(r["fatos"][0]["doc_id"], "z999")

    def test_truncamento_sinalizado(self):
        antigo = cmc.MAX_DOCUMENTOS_VARREDURA
        cmc.MAX_DOCUMENTOS_VARREDURA = 2
        try:
            docs = [(f"d{i}", HUMANO) for i in range(3)]
            r = cmc.consultar(_ctx(*docs), {"consulta": "reuniões"})
        finally:
            cmc.MAX_DOCUMENTOS_VARREDURA = antigo
        self.assertTrue(r["truncado"])
        self.assertEqual(r["documentos_lidos"], 2)
        self.assertTrue(any("truncada" in l for l in r["lacunas"]))

    def test_trecho_limitado_e_validade_serializavel(self):
        doc = {"texto_memoria": "reunião " + "x" * 1000, "validade_fim": "2999-01-01"}
        f = cmc.consultar(_ctx(("a", doc)), {"consulta": "reunião"})["fatos"][0]
        self.assertEqual(len(f["trecho"]), cmc.TRECHO_MAX)
        self.assertEqual(f["validade_fim"], "2999-01-01")

    def test_entidade_sozinha_basta(self):
        r = cmc.consultar(_ctx(("a", HUMANO)), {"entidades": ["Mariana"]})
        self.assertEqual(r["fatos"][0]["motivos"], ["entidade"])

    def test_id_do_snapshot_prevalece_sobre_campo_id_do_corpo(self):
        for corpo_id in ("outro", 5):
            doc = {**HUMANO, "id": corpo_id}
            r = cmc.consultar(_ctx(("a", doc)), {"consulta": "reuniões"})
            self.assertNotIn("erro", r)
            self.assertEqual([f["doc_id"] for f in r["fatos"]], ["a"])

    def test_args_nao_dict_vira_erro_de_entrada(self):
        for a in (["x"], "x", 5, None):
            self.assertEqual(set(cmc.consultar(_ctx(), a)), {"erro"})

    def test_merge_com_vencedores_intercalados_entre_paginas(self):
        docs = []
        for i in range(450):
            origem = "declaracao_humana" if i in (10, 210, 410) else "fonte_externa"
            docs.append((f"d{i:03d}", {"texto_memoria": "reunião", "origem_fato": origem}))
        r = cmc.consultar(_ctx(*docs), {"consulta": "reunião", "limite": 4})
        self.assertEqual([f["doc_id"] for f in r["fatos"]], ["d010", "d210", "d410", "d000"])

    def test_descartados_somam_entre_paginas(self):
        docs = [(f"d{i:03d}", {"texto_memoria": "x", "memoria_status": "superada"}) for i in range(450)]
        r = cmc.consultar(_ctx(*docs), {"consulta": "reunião"})
        self.assertEqual(r["descartados_por_razao"], {"superada": 450})

    def test_total_igual_ao_maximo_nao_trunca(self):
        antigo = cmc.MAX_DOCUMENTOS_VARREDURA
        cmc.MAX_DOCUMENTOS_VARREDURA = 3
        try:
            r = cmc.consultar(_ctx(*[(f"d{i}", HUMANO) for i in range(3)]), {"consulta": "reuniões"})
        finally:
            cmc.MAX_DOCUMENTOS_VARREDURA = antigo
        self.assertFalse(r["truncado"])
        self.assertEqual(r["documentos_lidos"], 3)

    def test_saida_nao_vaza_embedding_e_aceita_datetime(self):
        from datetime import datetime, timezone
        doc = {**HUMANO, "embedding": [0.1] * 768, "validade_fim": datetime(2999, 1, 1, tzinfo=timezone.utc)}
        r = cmc.consultar(_ctx(("a", doc)), {"consulta": "reuniões"})
        self.assertNotIn("embedding", str(r))
        self.assertEqual(r["fatos"][0]["validade_fim"], "2999-01-01T00:00:00+00:00")

    def test_erro_na_segunda_pagina_nao_vira_parcial(self):
        ctx = _ctx(*[(f"d{i:03d}", HUMANO) for i in range(250)])
        original = ctx.db.q.stream
        chamadas = []
        def stream():
            chamadas.append(1)
            if len(chamadas) == 2:
                raise RuntimeError("falha")
            return original()
        ctx.db.q.stream = stream
        r = cmc.consultar(ctx, {"consulta": "reuniões"})
        self.assertEqual(set(r), {"erro"})

    def test_limite_invalido(self):
        for v, esperado in ((None, 10), ("x", 10), (True, 10), (0, 10), (-3, 1), (999, 50), (float("inf"), 10)):
            self.assertEqual(cmc._limite(v), esperado, v)

    def test_erro_de_leitura_nao_vira_parcial(self):
        class Ruim:
            def collection(self, _):
                raise RuntimeError("segredo-interno")
        r = cmc.consultar(SimpleNamespace(db=Ruim()), {"consulta": "x y z"})
        self.assertEqual(set(r), {"erro"})
        self.assertNotIn("segredo-interno", r["erro"])

    def test_fora_do_canal_de_voz_e_handler_registrado(self):
        from tools import registry
        self.assertFalse(registry.is_voice_enabled("consultar_memoria_contextual"))
        self.assertIn("consultar_memoria_contextual", hermes_tools._HANDLERS)
        r = hermes_tools._HANDLERS["consultar_memoria_contextual"](_ctx(("a", HUMANO)), {"consulta": "reuniões"})
        self.assertEqual(r["fatos"][0]["doc_id"], "a")


if __name__ == "__main__":
    unittest.main()
