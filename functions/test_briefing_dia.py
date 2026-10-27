"""`briefing_dia/{data}` e as tools `registrar_briefing_dia`, `obter_briefing_dia`
e `resolver_item_briefing`.

O que protege:
- o "Feito" do André nunca é desfeito pelo agente que atualiza o briefing
  durante o dia (falha silenciosa: o item volta para a tela sem aviso);
- briefing meio-gravado nunca existe (um item inválido recusa tudo);
- cada item aponta para a origem, senão a tela não consegue escondê-lo quando
  a origem é resolvida;
- nenhum número calculável é gravado.
"""

import unittest

import briefing_dia as bd
from test_outbox_aprovacao import _MockDb
from tools import hermes_tools, inventory, registry
from tools.tool_context import ToolContext

DIA = "2026-10-27"


def _decidir(**over):
    base = {"id": "d1", "quem": "Enfermaria", "texto": "TR, itens 21, 26 e 28: converter para UNIDADE",
            "recomendacao": "É o que o diário recomenda.", "tag": "hoje",
            "origem": "fila_atencao", "ref": "atencao-123"}
    base.update(over)
    return base


def _briefing(**over):
    base = {
        "data": DIA,
        "hoje": [{"acao_id": "sisp", "motivo": "prazo 31/10"}],
        "decidir": [_decidir(), _decidir(id="d2", quem="Hildo", origem="whatsapp", ref="5527999@c.us", tag="")],
        "eu_faco": [{"acao_id": "sisp", "texto": "Ler o relatório e montar a versão executiva em rascunho"}],
        "preparo": [{"dia": "2026-10-28", "texto": "retirar o carro na Localiza, 9h"}],
        "fora_da_agenda": [{"titulo": "Conselho de Escola — EMEF", "inicio": "13:50", "fim": None,
                            "motivo": "reunião que não está na agenda"}],
        "avisos": [{"tipo": "nao_li", "texto": "Não li hoje: e-mail e SIGFAPES."}],
        "menores": 2,
    }
    base.update(over)
    return base


class _Base(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()
        self.ctx = ToolContext(_db=self.db)

    def _doc(self, dia=DIA):
        return self.db.collection("briefing_dia")._docs.get(dia)


class TestValidacao(unittest.TestCase):

    def test_briefing_completo_e_valido(self):
        secoes, erros = bd.validar(_briefing())
        self.assertEqual(erros, [])
        self.assertEqual(set(secoes), {"hoje", "decidir", "eu_faco", "preparo", "fora_da_agenda",
                                       "avisos", "menores"})

    def test_item_de_decidir_sem_origem_ou_ref_e_recusado(self):
        _, erros = bd.validar({"decidir": [{"id": "d1", "quem": "X", "texto": "Y"}]})
        self.assertTrue(any("`origem` e obrigatorio" in e for e in erros), erros)
        self.assertTrue(any("`ref` e obrigatorio" in e for e in erros), erros)

    def test_origem_invalida(self):
        _, erros = bd.validar({"decidir": [_decidir(origem="telegram")]})
        self.assertTrue(any("invalida" in e and "fila_atencao" in e for e in erros), erros)

    def test_origem_etapa_exige_acao_id(self):
        _, erros = bd.validar({"decidir": [_decidir(origem="etapa", ref="e1")]})
        self.assertTrue(any("acao_id" in e for e in erros), erros)
        secoes, erros = bd.validar({"decidir": [_decidir(origem="etapa", ref="e1", acao_id="t1")]})
        self.assertEqual(erros, [])

    def test_origem_acao_usa_o_ref_como_acao_id(self):
        secoes, erros = bd.validar({"decidir": [_decidir(origem="acao", ref="t9")]})
        self.assertEqual(erros, [])
        self.assertEqual(secoes["decidir"][0]["acao_id"], "t9")

    def test_status_nao_e_aceito_na_escrita_do_agente(self):
        secoes, _ = bd.validar({"decidir": [_decidir(status="feito", resolvido_em="x")]})
        self.assertNotIn("status", secoes["decidir"][0])
        self.assertNotIn("resolvido_em", secoes["decidir"][0])

    def test_id_repetido_na_mesma_chamada(self):
        _, erros = bd.validar({"decidir": [_decidir(), _decidir()]})
        self.assertTrue(any("repetido" in e for e in erros), erros)

    def test_preparo_exige_data_real_e_nao_grava_em_n_dias(self):
        _, erros = bd.validar({"preparo": [{"dia": "2026-02-30", "texto": "x"}]})
        self.assertTrue(any("YYYY-MM-DD" in e for e in erros), erros)
        secoes, _ = bd.validar({"preparo": [{"dia": "2026-10-28", "texto": "x", "em_dias": 1}]})
        self.assertEqual(secoes["preparo"], [{"dia": "2026-10-28", "texto": "x"}])

    def test_fora_da_agenda_valida_horas(self):
        _, erros = bd.validar({"fora_da_agenda": [{"titulo": "X", "inicio": "25:00"}]})
        self.assertTrue(any("HH:MM" in e for e in erros), erros)
        _, erros = bd.validar({"fora_da_agenda": [{"titulo": "X", "inicio": "14:00", "fim": "13:00"}]})
        self.assertTrue(any("depois de" in e for e in erros), erros)

    def test_tipo_de_aviso(self):
        _, erros = bd.validar({"avisos": [{"tipo": "outro", "texto": "x"}]})
        self.assertTrue(any("nao_li" in e for e in erros), erros)

    def test_listas_precisam_ser_listas_e_respeitar_o_teto(self):
        _, erros = bd.validar({"decidir": "d1"})
        self.assertTrue(any("LISTA" in e for e in erros), erros)
        _, erros = bd.validar({"avisos": [{"tipo": "nao_li", "texto": "x"}] * (bd.MAX_ITENS + 1)})
        self.assertTrue(any("maximo" in e for e in erros), erros)

    def test_texto_acima_do_limite_e_recusado_em_vez_de_cortado(self):
        _, erros = bd.validar({"decidir": [_decidir(texto="a" * (bd.MAX_TEXTO + 1))]})
        self.assertTrue(any("maximo" in e for e in erros), erros)

    def test_menores_inteiro_nao_negativo(self):
        _, erros = bd.validar({"menores": -1})
        self.assertTrue(erros)
        _, erros = bd.validar({"menores": True})
        self.assertTrue(erros)


class TestRegistrar(_Base):

    def test_grava_e_devolve_o_documento_relido(self):
        res = bd.registrar(self.db, _briefing())
        self.assertTrue(res["aplicado"], res)
        self.assertTrue(res["criado"])
        doc = self._doc()
        self.assertEqual(doc["data"], DIA)
        self.assertEqual([i["id"] for i in doc["decidir"]], ["d1", "d2"])
        self.assertEqual([i["ordem"] for i in doc["decidir"]], [1, 2])
        for item in doc["decidir"]:
            self.assertEqual(item["status"], "pendente")
            self.assertIsNone(item["resolvido_em"])
        self.assertEqual(doc["eu_faco"][0]["status"], "proposto")
        self.assertEqual(doc["menores"], 2)
        self.assertIn("gerado_em", doc)
        self.assertIn("atualizado_em", doc)
        self.assertEqual(res["briefing"]["decidir"][0]["origem"], "fila_atencao")

    def test_nao_grava_nenhum_numero_calculavel(self):
        bd.registrar(self.db, _briefing())
        doc = self._doc()
        proibidos = {"etapas_agente", "n_etapas", "conflito", "conflitos", "em_dias", "concluidas"}
        self.assertFalse(proibidos & set(doc))
        for lista in ("hoje", "decidir", "eu_faco", "preparo", "fora_da_agenda", "avisos"):
            for item in doc[lista]:
                self.assertFalse(proibidos & set(item), (lista, item))

    def test_data_padrao_e_hoje_em_brasilia(self):
        res = bd.registrar(self.db, {"avisos": [{"tipo": "nao_li", "texto": "x"}]})
        self.assertEqual(res["data"], bd.hoje_sp())

    def test_data_invalida_e_recusada(self):
        res = bd.registrar(self.db, {"data": "27/10/2026", "menores": 1})
        self.assertFalse(res["aplicado"])
        self.assertIn("invalida", res["erro"])

    def test_sem_secao_nenhuma_e_recusado(self):
        res = bd.registrar(self.db, {"data": DIA})
        self.assertFalse(res["aplicado"])
        self.assertIsNone(self._doc())

    def test_um_item_invalido_recusa_tudo_sem_gravar(self):
        res = bd.registrar(self.db, _briefing(avisos=[{"tipo": "xx", "texto": "y"}]))
        self.assertFalse(res["aplicado"])
        self.assertIn("nada foi gravado", res["erro"])
        self.assertIsNone(self._doc())

    def test_merge_por_id_atualiza_o_item_e_mantem_os_que_nao_vieram(self):
        bd.registrar(self.db, _briefing())
        res = bd.registrar(self.db, {"data": DIA, "decidir": [_decidir(id="d1", texto="Texto novo"),
                                                              _decidir(id="d3", quem="Raquel", ref="w9",
                                                                       origem="whatsapp")]})
        self.assertFalse(res["criado"])
        ids = [i["id"] for i in self._doc()["decidir"]]
        self.assertEqual(ids, ["d1", "d2", "d3"])
        self.assertEqual(self._doc()["decidir"][0]["texto"], "Texto novo")
        self.assertEqual(self._doc()["decidir"][2]["ordem"], 3)
        # seções não enviadas ficam como estavam
        self.assertEqual(self._doc()["preparo"][0]["texto"], "retirar o carro na Localiza, 9h")

    def test_atualizar_durante_o_dia_nao_desfaz_o_feito(self):
        bd.registrar(self.db, _briefing())
        bd.resolver_item(self.db, {"data": DIA, "id": "d1", "status": "feito"})
        resolvido_em = self._doc()["decidir"][0]["resolvido_em"]
        self.assertTrue(resolvido_em)
        # O agente reenvia o item (com o status que ele acha que vale) as 14h.
        bd.registrar(self.db, {"data": DIA, "decidir": [_decidir(id="d1", status="pendente",
                                                                  texto="Texto das 14h")]})
        d1 = self._doc()["decidir"][0]
        self.assertEqual(d1["status"], "feito")
        self.assertEqual(d1["resolvido_em"], resolvido_em)
        self.assertEqual(d1["texto"], "Texto das 14h")

    def test_gerado_em_nao_muda_na_atualizacao(self):
        bd.registrar(self.db, _briefing())
        gerado = self._doc()["gerado_em"]
        bd.registrar(self.db, {"data": DIA, "menores": 5})
        self.assertIs(self._doc()["gerado_em"], gerado)
        self.assertEqual(self._doc()["menores"], 5)

    def test_listas_foto_substituem_quando_enviadas(self):
        bd.registrar(self.db, _briefing())
        bd.registrar(self.db, {"data": DIA, "avisos": [{"tipo": "conversa", "texto": "Novo"}],
                               "hoje": []})
        self.assertEqual(self._doc()["avisos"], [{"tipo": "conversa", "texto": "Novo"}])
        self.assertEqual(self._doc()["hoje"], [])

    def test_eu_faco_mescla_por_acao_id_e_aceita_andamento(self):
        bd.registrar(self.db, _briefing())
        bd.registrar(self.db, {"data": DIA, "eu_faco": [{"acao_id": "sisp", "texto": "Pronto", "status": "pronto"}]})
        self.assertEqual(len(self._doc()["eu_faco"]), 1)
        self.assertEqual(self._doc()["eu_faco"][0]["status"], "pronto")

    def test_repetir_a_mesma_chamada_deixa_o_documento_igual(self):
        bd.registrar(self.db, _briefing())
        antes = {k: v for k, v in self._doc().items() if k != "atualizado_em"}
        bd.registrar(self.db, _briefing())
        depois = {k: v for k, v in self._doc().items() if k != "atualizado_em"}
        self.assertEqual(antes, depois)

    def test_sem_transacao_nao_ha_escrita_desprotegida(self):
        class SemTx:
            def __init__(self, real):
                self._real = real

            def collection(self, nome):
                return self._real.collection(nome)

        res = bd.registrar(SemTx(self.db), _briefing())
        self.assertFalse(res["aplicado"])
        self.assertIsNone(self._doc())


class TestObter(_Base):

    def test_ausente(self):
        res = bd.obter(self.db, {"data": DIA})
        self.assertEqual(res["existe"], False)
        self.assertNotIn("briefing", res)

    def test_devolve_o_documento_e_conta_pendentes(self):
        bd.registrar(self.db, _briefing())
        bd.resolver_item(self.db, {"data": DIA, "id": "d2", "status": "dispensado"})
        res = bd.obter(self.db, {"data": DIA})
        self.assertTrue(res["existe"])
        self.assertEqual(res["decidir_pendentes"], 1)
        self.assertEqual(res["briefing"]["decidir"][1]["status"], "dispensado")

    def test_data_invalida(self):
        self.assertIn("erro", bd.obter(self.db, {"data": "ontem"}))


class TestResolver(_Base):

    def setUp(self):
        super().setUp()
        bd.registrar(self.db, _briefing())

    def test_marca_feito_com_resolvido_em(self):
        res = bd.resolver_item(self.db, {"data": DIA, "id": "d1", "status": "feito"})
        self.assertTrue(res["aplicado"] and res["mudou"], res)
        d1 = self._doc()["decidir"][0]
        self.assertEqual(d1["status"], "feito")
        self.assertRegex(d1["resolvido_em"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertEqual(self._doc()["decidir"][1]["status"], "pendente")

    def test_dispensado(self):
        bd.resolver_item(self.db, {"data": DIA, "id": "d2", "status": "dispensado"})
        self.assertEqual(self._doc()["decidir"][1]["status"], "dispensado")

    def test_desfazer_volta_a_pendente_e_limpa_a_hora(self):
        bd.resolver_item(self.db, {"data": DIA, "id": "d1", "status": "feito"})
        bd.resolver_item(self.db, {"data": DIA, "id": "d1", "status": "pendente"})
        d1 = self._doc()["decidir"][0]
        self.assertEqual((d1["status"], d1["resolvido_em"]), ("pendente", None))

    def test_repetir_a_mesma_marca_nao_escreve_de_novo(self):
        bd.resolver_item(self.db, {"data": DIA, "id": "d1", "status": "feito"})
        primeira = self._doc()["decidir"][0]["resolvido_em"]
        res = bd.resolver_item(self.db, {"data": DIA, "id": "d1", "status": "feito"})
        self.assertFalse(res["aplicado"])
        self.assertFalse(res["mudou"])
        self.assertEqual(self._doc()["decidir"][0]["resolvido_em"], primeira)

    def test_id_inexistente_lista_os_existentes(self):
        res = bd.resolver_item(self.db, {"data": DIA, "id": "zz", "status": "feito"})
        self.assertFalse(res["aplicado"])
        self.assertIn("d1, d2", res["erro"])

    def test_status_invalido(self):
        res = bd.resolver_item(self.db, {"data": DIA, "id": "d1", "status": "concluido"})
        self.assertIn("invalido", res["erro"])
        self.assertEqual(self._doc()["decidir"][0]["status"], "pendente")

    def test_sem_briefing_no_dia(self):
        res = bd.resolver_item(self.db, {"data": "2026-01-01", "id": "d1", "status": "feito"})
        self.assertIn("Nao ha briefing", res["erro"])

    def test_nao_toca_nas_outras_secoes(self):
        antes = {k: v for k, v in self._doc().items() if k not in ("decidir", "atualizado_em")}
        bd.resolver_item(self.db, {"data": DIA, "id": "d1", "status": "feito"})
        depois = {k: v for k, v in self._doc().items() if k not in ("decidir", "atualizado_em")}
        self.assertEqual(antes, depois)


class TestRegistroNasTools(unittest.TestCase):
    """As três tools precisam estar em todos os lugares que publicam o catálogo."""

    NOMES = ("registrar_briefing_dia", "obter_briefing_dia", "resolver_item_briefing")

    def test_catalogo_handler_schema_e_inventario(self):
        for nome in self.NOMES:
            with self.subTest(tool=nome):
                self.assertIn(nome, registry.list_tool_names())
                self.assertIn(nome, hermes_tools.list_tools())
                self.assertEqual(registry.get_schema(nome)["name"], nome)
                self.assertIsNotNone(inventory.get_inventory_entry(nome))

    def test_campos_obrigatorios_do_schema(self):
        self.assertEqual(registry.campos_obrigatorios_ausentes("resolver_item_briefing", {"id": "d1"}), ["status"])
        self.assertEqual(registry.campos_obrigatorios_ausentes("registrar_briefing_dia", {}), [])
        self.assertEqual(registry.campos_obrigatorios_ausentes("obter_briefing_dia", {}), [])

    def test_schema_de_decidir_exige_origem_e_ref(self):
        itens = registry.get_schema("registrar_briefing_dia")["parameters"]["properties"]["decidir"]["items"]
        self.assertTrue({"id", "quem", "texto", "origem", "ref"} <= set(itens["required"]))
        self.assertEqual(itens["properties"]["origem"]["enum"], list(bd.ORIGENS))

    def test_leitura_nao_pede_confirmacao_e_as_escritas_sao_marcadas(self):
        mut = registry.mcp_annotations
        self.assertTrue(mut("obter_briefing_dia")["readOnlyHint"])
        self.assertFalse(mut("registrar_briefing_dia")["readOnlyHint"])
        self.assertFalse(mut("resolver_item_briefing")["readOnlyHint"])
        self.assertTrue(mut("registrar_briefing_dia")["idempotentHint"])

    def test_execucao_pela_tool_chega_ao_modulo(self):
        db = _MockDb()
        ctx = ToolContext(_db=db)
        res = hermes_tools._registrar_briefing_dia(ctx, _briefing())
        self.assertTrue(res["aplicado"], res)
        self.assertEqual(hermes_tools._obter_briefing_dia(ctx, {"data": DIA})["decidir_pendentes"], 2)
        self.assertTrue(hermes_tools._resolver_item_briefing(ctx, {"data": DIA, "id": "d1", "status": "feito"})["aplicado"])


if __name__ == "__main__":
    unittest.main()
