"""Testes da guarda do modelo por pessoa (P06 passo 9)."""

import copy
import json
import unittest

from autonomy.modelo_pessoa_guarda import categorias_proibidas, sanear_modelo_interacao
from main import parse_resposta_modelo_pessoa, construir_prompt_modelo_pessoa


class TestCategoriasProibidas(unittest.TestCase):
    def test_texto_limpo(self):
        self.assertEqual(categorias_proibidas("formal, trata por Dr."), [])
        self.assertEqual(categorias_proibidas("costuma responder em ~2h no dia útil"), [])

    def test_nao_string_ou_vazio(self):
        for v in (None, 3, "", "   ", ["saúde"], {"a": 1}):
            self.assertEqual(categorias_proibidas(v), [])

    def test_categorias(self):
        casos = {
            "saude": "está em tratamento médico por depressão",
            "religiao": "é evangélica e não responde aos domingos",
            "politica": "é bolsonarista",
            "orientacao_sexual": "é homossexual",
            "origem_etnica": "pessoa negra",
            "deficiencia": "é cadeirante",
            "sindical": "é sindicalizado",
            "financeiro_judicial": "está endividado",
            "acesso_por_perfil": "tem permissão para aprovar pagamentos",
        }
        for cat, texto in casos.items():
            self.assertIn(cat, categorias_proibidas(texto), texto)

    def test_acento_e_caixa(self):
        self.assertIn("saude", categorias_proibidas("DEPRESSÃO"))
        self.assertIn("religiao", categorias_proibidas("Católica"))

    def test_flexoes_e_vocabulario(self):
        for texto in ("pessoas negras", "os judeus", "homossexuais", "lésbicas", "deprimido",
                      "está doente", "poderá liberar pagamentos", "podem assinar transferências", "diabetes", "TDAH",
                      "licença médica", "surdez", "esquerdista", "vota no PT", "filiado ao sindicato", "sindicalista",
                      "devedor", "está devendo", "budista", "testemunha de Jeová",
                      "bolsonarismo", "transexual", "gays", "vota no PT", "é crente de verdade", "tem covid",
                      "pode liberar pagamentos", "gаy", "pessoa trans", "foi preso", "pode aprovar pagamentos", "pode acessar a folha de pagamento", "autorizado a assinar pagamentos",
                      "é negro", "homem negro", "é pardo", "tem permissão para aprovar pagamento", "nível de acesso total"):
            self.assertTrue(categorias_proibidas(texto), texto)

    def test_caractere_invisivel(self):
        self.assertIn("saude", categorias_proibidas("d\u200boença"))

    def test_sem_falso_positivo_comum(self):
        for texto in ("reunião do partido de pagamentos", "dúvida sobre a raça do cachorro",
                      "enviou o diagnóstico do sistema", "relatório de psicologia",
                      "acesso a planilha enviado", "autorizou a enviar relatório",
                      "pedido de autorização para viagem", "cobrar o antecedentes",
                      "tratamento cordial e formal", "atualizar processo SIPAC",
                      "terapia ocupacional da turma", "voto em separado", "votou no conselho",
                      "vício de forma no edital", "dívida ativa da instituição", "sindicato dos servidores reunião",
                      "pastoral", "igreja matriz endereço", "cadastro de gestante", "deficiência no serviço",
                      "negro de fumo", "pode receber o material", "pode decidir depois", "processo criminal do edital",
                      "caneta azul e preta", "Joao e Negro Ltda", "a tinta é negra", "o toner é negro", "senhor negro Ltda", "o diretor pode aprovar o contrato de licitação",
                      "o fiscal pode acessar o sistema financeiro do Ifes", "autorizado a assinar o contrato pela reitoria", "pode acessar o link", "Rodovia Trans-Amazônica", "consulta ao Serasa para pesquisa de preços",
                      "a porta e de esquerda", "o relatório é do PL 2338", "durante a covid o contrato foi suspenso",
                      "o servidor esta internado no sistema", "estou crente que vai dar certo", "o setor tem acesso ao SIPAC",
                      "tem poderes para representar", "cadeira de rodas para o campus", "o processo esta preso na CLC"):
            self.assertEqual(categorias_proibidas(texto), [], texto)

    def test_tipos_invalidos_descartados(self):
        s, d = sanear_modelo_interacao({"registro": {"t": "doença"}, "acoes_recentes": [{"t": "x"}, "a"]})
        self.assertIsNone(s["registro"])
        self.assertEqual(s["acoes_recentes"], ["a"])
        self.assertEqual(len(d), 2)

    def test_fronteira_de_palavra(self):
        self.assertEqual(categorias_proibidas("sempre diz que o gaysers"), [])
        self.assertEqual(categorias_proibidas("hivernal"), [])


class TestSanearModelo(unittest.TestCase):
    def test_limpo_intacto(self):
        m = {"registro": "informal", "tempo_resposta_tipico": "~2h",
             "acoes_recentes": ["Enviar relatório (a1)"], "atualizado_em": "x"}
        s, d = sanear_modelo_interacao(m)
        self.assertEqual(s, m)
        self.assertEqual(d, [])

    def test_descarta_campos_e_itens(self):
        m = {"registro": "formal, mas é católico praticante",
             "tempo_resposta_tipico": "~2h",
             "acoes_recentes": ["Consulta de tratamento médico (a1)", "Enviar relatório (a2)"],
             "atualizado_em": "x"}
        orig = copy.deepcopy(m)
        s, d = sanear_modelo_interacao(m)
        self.assertEqual(m, orig)  # não muta
        self.assertIsNone(s["registro"])
        self.assertEqual(s["tempo_resposta_tipico"], "~2h")
        self.assertEqual(s["acoes_recentes"], ["Enviar relatório (a2)"])
        self.assertEqual(s["atualizado_em"], "x")
        self.assertIn({"campo": "registro", "categorias": ["religiao"]}, d)
        self.assertIn({"campo": "acoes_recentes", "indice": 0, "categorias": ["saude"]}, d)

    def test_entrada_nao_dict(self):
        for v in (None, "x", [1]):
            s, d = sanear_modelo_interacao(v)
            self.assertIs(s, v)
            self.assertEqual(d, [])

    def test_acoes_nao_lista_preservada(self):
        s, d = sanear_modelo_interacao({"acoes_recentes": "texto"})
        self.assertEqual(s["acoes_recentes"], "texto")


class TestIntegracaoParse(unittest.TestCase):
    def test_parse_descarta_sensivel(self):
        raw = json.dumps({
            "registro": "informal; pessoa com depressão",
            "tempo_resposta_tipico": "responde em ~1h",
            "acoes_recentes": ["Pagar boleto (b1)"],
        })
        r = parse_resposta_modelo_pessoa(raw)
        self.assertIsNone(r["registro"])
        self.assertEqual(r["tempo_resposta_tipico"], "responde em ~1h")
        self.assertEqual(r["acoes_recentes"], ["Pagar boleto (b1)"])
        self.assertIn("atualizado_em", r)

    def test_parse_limpo_igual_ao_anterior(self):
        r = parse_resposta_modelo_pessoa(json.dumps({"registro": "formal", "tempo_resposta_tipico": None, "acoes_recentes": []}))
        self.assertEqual(r["registro"], "formal")
        self.assertIsNone(r["tempo_resposta_tipico"])

    def test_prompt_proibe_inferencia_sensivel(self):
        p = construir_prompt_modelo_pessoa("Ana", "texto")
        self.assertIn("NUNCA infira saúde, religião", p)
        self.assertIn("nível de acesso", p)


if __name__ == "__main__":
    unittest.main()


class TestLeituraBuscarContato(unittest.TestCase):
    def test_modelo_armazenado_sensivel_e_saneado_na_leitura(self):
        from unittest.mock import MagicMock
        from tools.hermes_tools import _buscar_contato, ToolContext
        doc = MagicMock()
        doc.id = "p1"
        doc.to_dict.return_value = {
            "nome": "Ana", "whatsapp_chat_id": "c",
            "modelo_interacao": {"registro": "formal; é evangélica", "tempo_resposta_tipico": "~2h", "acoes_recentes": []},
        }
        db = MagicMock()
        db.collection.return_value.stream.return_value = [doc]
        res = _buscar_contato(ToolContext(_db=db, user_uid="u", task_id="t"), {"termo": "ana"})
        modelo = res["candidatos"][0]["modelo_interacao"]
        self.assertIsNone(modelo["registro"])
        self.assertEqual(modelo["tempo_resposta_tipico"], "~2h")
