"""obter_estado_atual (MCP) resumido por padrão.

Medido em 04/10/2026: a ferramenta respondia por 31% de todo o texto que o MCP
devolvia ao Claude, ~73 mil caracteres por chamada, e é a primeira chamada de
toda conversa. O resumo mantém as chaves e encurta o conteúdo; `detalhe=
"completo"` devolve tudo como antes.
"""

import copy
import json
import unittest
from unittest.mock import MagicMock, patch

from tools import estado_resumido as er


def _acao(i, n_esperas=6):
    return {
        "id": f"a{i}", "titulo": f"Ação {i}", "status": "em andamento",
        "subtarefa_do_dia": {"id": "e1", "texto": "x" * 400, "estado": "pendente", "degradation_count": 3},
        "proximo_passo": {"id": "e2", "texto": "y" * 400},
        "aguardando_terceiro": [{"id": f"w{j}", "texto": "z" * 300, "aguardando_de": f"Pessoa {j}",
                                 "data_prevista": "2026-09-14"} for j in range(n_esperas)],
    }


def _estado():
    return {
        "data": "2026-10-05",
        "hoje": {"avanco": [_acao(i) for i in range(13)], "atrasadas": [_acao(20)], "continuo": []},
        "foco": [_acao(30)],
        "fila_atencao": [{"id": f"at{i}", "titulo": "Responder a Gabriela", "resumo": "r" * 500,
                          "sugestao": "s" * 500, "evidencia": {"mensagem_ids": ["m" * 40] * 5},
                          "chave_dedupe": "k" * 60, "criado_em": "2026-10-01T10:00:00",
                          "atualizado_em": "2026-10-02T10:00:00", "resolvido_em": None, "desfecho": None,
                          "estado": "aberto", "prioridade": "alta", "acao_id": "a1"} for i in range(10)],
        "pops_ativos": [{"id": "p1", "titulo": "Fuso", "instrucao_sistema": "regra " * 300}],
        "ontem": {"diario": {"texto": "d" * 3000}, "concluidas": [{"id": "c1"}]},
        "respostas_pendentes": {"itens": [{"id": "wa:1", "trecho": "oi"}]},
    }


def _tam(x):
    return len(json.dumps(x, ensure_ascii=False))


class TestResumirEstado(unittest.TestCase):
    def test_mantem_as_chaves_e_corta_bem(self):
        original = _estado()
        res = er.resumir_estado(original)
        self.assertLessEqual(set(original), set(res))
        self.assertLess(_tam(res), _tam(original) * 0.5)

    def test_ate_duas_esperas_por_acao_com_o_total(self):
        acao = er.resumir_estado(_estado())["hoje"]["avanco"][0]
        self.assertEqual(len(acao["aguardando_terceiro"]), 2)
        self.assertEqual(acao["aguardando_terceiro_total"], 6)
        self.assertEqual(acao["aguardando_terceiro"][0]["aguardando_de"], "Pessoa 0")
        self.assertLessEqual(len(acao["aguardando_terceiro"][0]["texto"]), er.TEXTO_ESPERA)

    def test_etapa_do_dia_e_proximo_passo_cortados(self):
        acao = er.resumir_estado(_estado())["hoje"]["avanco"][1]
        self.assertEqual(len(acao["subtarefa_do_dia"]["texto"]), er.TEXTO_ETAPA)
        self.assertTrue(acao["subtarefa_do_dia"]["texto"].endswith("…"))
        self.assertNotIn("degradation_count", acao["subtarefa_do_dia"])
        self.assertEqual(acao["subtarefa_do_dia"]["id"], "e1")
        self.assertEqual(len(acao["proximo_passo"]["texto"]), er.TEXTO_ETAPA)

    def test_foco_tambem_resumido(self):
        self.assertEqual(len(er.resumir_estado(_estado())["foco"][0]["aguardando_terceiro"]), 2)

    def test_fila_de_atencao_sem_campos_internos(self):
        item = er.resumir_estado(_estado())["fila_atencao"][0]
        for campo in er._CAMPOS_INTERNOS_ATENCAO:
            self.assertNotIn(campo, item)
        self.assertEqual((item["id"], item["prioridade"], item["acao_id"]), ("at0", "alta", "a1"))
        self.assertEqual(len(item["resumo"]), er.TEXTO_ATENCAO)

    def test_pops_ficam_inteiros(self):
        original = _estado()
        self.assertEqual(er.resumir_estado(original)["pops_ativos"], original["pops_ativos"])

    def test_diario_de_ontem_cortado(self):
        self.assertEqual(len(er.resumir_estado(_estado())["ontem"]["diario"]["texto"]), er.TEXTO_DIARIO)

    def test_texto_curto_nao_muda(self):
        estado = {"hoje": {"avanco": [{"id": "a", "subtarefa_do_dia": {"texto": "curto"},
                                       "aguardando_terceiro": []}]}}
        acao = er.resumir_estado(estado)["hoje"]["avanco"][0]
        self.assertEqual(acao["subtarefa_do_dia"]["texto"], "curto")
        self.assertNotIn("aguardando_terceiro_total", acao)

    def test_campos_vazios_e_redundantes_saem(self):
        acao = {"id": "a", "titulo": "T", "horario_inicio": None, "prazo_final": None, "cobrar": False,
                "herdada": True, "execution_lane": "avanco", "atrasada": True, "degradation_count": 0,
                "subtarefa_do_dia": {"id": "e1", "texto": "t", "aguardando_de": None},
                "proximo_passo": {"id": "e1", "texto": "t"}, "aguardando_terceiro": []}
        curta = er.resumir_estado({"hoje": {"avanco": [acao]}})["hoje"]["avanco"][0]
        self.assertEqual(curta, {"id": "a", "titulo": "T", "herdada": True, "atrasada": True,
                                 "subtarefa_do_dia": {"id": "e1", "texto": "t"}})

    def test_lista_de_atrasadas_vira_referencia(self):
        """Toda ação atrasada já está inteira na lista da faixa dela (morning_summary
        põe o mesmo item nas duas listas)."""
        estado = _estado()
        res = er.resumir_estado(estado)["hoje"]
        self.assertEqual(res["atrasadas"], [{"id": "a20", "titulo": "Ação 20"}])

    def test_proximo_passo_diferente_da_etapa_do_dia_fica(self):
        acao = {"id": "a", "subtarefa_do_dia": {"id": "e1", "texto": "t"}, "proximo_passo": {"id": "e2", "texto": "u"}}
        self.assertIn("proximo_passo", er.resumir_estado({"hoje": {"avanco": [acao]}})["hoje"]["avanco"][0])

    def test_contagem_de_adiamento_maior_que_zero_fica(self):
        acao = {"id": "a", "degradation_count": 2}
        self.assertEqual(er.resumir_estado({"hoje": {"avanco": [acao]}})["hoje"]["avanco"][0]["degradation_count"], 2)

    def test_nao_altera_o_original(self):
        original = _estado()
        copia = copy.deepcopy(original)
        er.resumir_estado(original)
        self.assertEqual(original, copia)

    def test_avisa_que_esta_resumido_e_como_abrir(self):
        res = er.resumir_estado(_estado())
        self.assertEqual(res["detalhe"], "auto")
        self.assertIn("obter_acao", res["observacao"])
        self.assertIn("detalhe='completo'", res["observacao"])


class TestHandler(unittest.TestCase):
    def _chamar(self, args):
        from tools import hermes_tools
        from tools.tool_context import ToolContext

        with patch("morning_summary.build_morning_summary", return_value=_estado()), \
                patch("atencao.coletar_fila_atencao",
                      return_value={"itens": _estado()["fila_atencao"], "total": 10}):
            return hermes_tools.obter_estado_atual(ToolContext(_db=MagicMock()), args)

    def test_padrao_e_resumido(self):
        res = self._chamar({})
        self.assertEqual(res["detalhe"], "auto")
        self.assertEqual(len(res["hoje"]["avanco"][0]["aguardando_terceiro"]), 2)
        self.assertNotIn("evidencia", res["fila_atencao"][0])

    def test_completo_devolve_tudo(self):
        res = self._chamar({"detalhe": "completo"})
        self.assertNotIn("detalhe", res)
        self.assertEqual(len(res["hoje"]["avanco"][0]["aguardando_terceiro"]), 6)
        self.assertIn("evidencia", res["fila_atencao"][0])

    def test_schema_de_entrada_publica_detalhe(self):
        import pathlib

        schema = json.loads((pathlib.Path(__file__).parent / "tools/schemas/obter_estado_atual.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(schema["parameters"]["properties"]["detalhe"]["enum"], ["auto", "completo"])

    def test_valor_invalido_de_detalhe_e_recusado_no_preflight(self):
        from tools import registry

        self.assertTrue(registry.valores_invalidos("obter_estado_atual", {"detalhe": "tudo"}))
        self.assertFalse(registry.valores_invalidos("obter_estado_atual", {"detalhe": "completo"}))


if __name__ == "__main__":
    unittest.main()
