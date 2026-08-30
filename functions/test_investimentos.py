"""Testes da integracao com o servico de decisao de investimentos.

Nenhum teste aqui usa rede: a sessao autenticada e substituida por um duble que
registra o que foi chamado. O que se verifica nao e "a chamada funciona" — isso
so o servico real responde — e sim as regras que este lado impoe: validacao
antes de gastar uma requisicao, traducao do estado "carteira nao registrada", e
principalmente que NENHUMA escrita e reenviada sozinha.

Esse ultimo ponto e o que justifica o arquivo. `POST /carteira/aporte` soma ao
`aporte_total` e o servico nao tem estorno: um reenvio automatico depois de um
timeout — onde a primeira requisicao pode ter chegado — dobraria o valor
registrado sem erro nenhum aparecer.
"""
import sys
import unittest
from unittest import mock

sys.path.insert(0, ".")

import investimentos  # noqa: E402
from tools import hermes_tools  # noqa: E402
from tools.tool_context import ToolContext  # noqa: E402


class _Resposta:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("sem corpo JSON")
        return self._json


class _SessaoFalsa:
    """Registra cada requisicao. `erro` levanta; `respostas` sao consumidas em ordem."""

    def __init__(self, respostas=None, erro=None):
        self.chamadas = []
        self.respostas = list(respostas or [])
        self.erro = erro

    def request(self, metodo, url, params=None, timeout=None):
        self.chamadas.append({"metodo": metodo, "url": url, "params": params, "timeout": timeout})
        if self.erro is not None:
            raise self.erro
        return self.respostas.pop(0) if self.respostas else _Resposta(200, {})


def _com_sessao(sessao):
    return mock.patch.object(investimentos, "_sessao_autenticada", lambda: sessao)


CTX = ToolContext(user_uid="uid-de-teste")


class EscritaNuncaERepetida(unittest.TestCase):
    """O ponto central: falha em escrita nao vira retry."""

    def test_timeout_em_aporte_faz_uma_tentativa_so(self):
        sessao = _SessaoFalsa(erro=TimeoutError("estourou"))
        with _com_sessao(sessao):
            resultado = investimentos.registrar_aporte(500.0)
        self.assertEqual(len(sessao.chamadas), 1, "a escrita foi reenviada")
        self.assertTrue(resultado.get("escrita_ambigua"))
        self.assertIn("NAO repita", resultado["erro"])

    def test_erro_5xx_em_aporte_tambem_e_ambiguo(self):
        # 500 pode ter acontecido DEPOIS da gravacao — quem chama nao pode
        # assumir que nada foi gravado.
        sessao = _SessaoFalsa([_Resposta(500, text="boom")])
        with _com_sessao(sessao):
            resultado = investimentos.registrar_aporte(500.0)
        self.assertTrue(resultado.get("escrita_ambigua"))

    def test_422_nao_e_ambiguo(self):
        # 422 e o servico recusando o dado: nada foi gravado, e dizer "pode ter
        # sido" mandaria o usuario conferir a toa.
        sessao = _SessaoFalsa([_Resposta(422, {"detail": "valor deve ser > 0"})])
        with _com_sessao(sessao):
            resultado = investimentos.confirmar_execucao("CDI", valor=10.0)
        self.assertNotIn("escrita_ambigua", resultado)
        self.assertIn("valor deve ser > 0", resultado["erro"])

    def test_falha_de_leitura_nao_e_marcada_como_ambigua(self):
        sessao = _SessaoFalsa(erro=TimeoutError("estourou"))
        with _com_sessao(sessao):
            resultado = investimentos.carteira()
        self.assertNotIn("escrita_ambigua", resultado)


class ValidacaoAntesDaRede(unittest.TestCase):
    """Argumento invalido nao gasta requisicao — e nem chega ao servico."""

    def test_aporte_zero_nao_chama_o_servico(self):
        sessao = _SessaoFalsa()
        with _com_sessao(sessao):
            resultado = investimentos.registrar_aporte(0)
        self.assertEqual(sessao.chamadas, [])
        self.assertIn("erro", resultado)

    def test_ativo_desconhecido_nao_chama_o_servico(self):
        sessao = _SessaoFalsa()
        with _com_sessao(sessao):
            resultado = investimentos.confirmar_execucao("PETR4", quantidade=1, preco=2)
        self.assertEqual(sessao.chamadas, [])
        self.assertIn("PETR4", resultado["erro"])

    def test_cdi_sem_valor_e_recusado(self):
        sessao = _SessaoFalsa()
        with _com_sessao(sessao):
            resultado = investimentos.confirmar_execucao("CDI")
        self.assertEqual(sessao.chamadas, [])
        self.assertIn("valor", resultado["erro"])

    def test_etf_sem_preco_e_recusado(self):
        sessao = _SessaoFalsa()
        with _com_sessao(sessao):
            resultado = investimentos.confirmar_execucao("BOVA11", quantidade=7)
        self.assertEqual(sessao.chamadas, [])
        self.assertIn("preco", resultado["erro"])

    def test_parametros_vao_como_query_string(self):
        # O FastAPI do outro lado declara os campos como Query, nao corpo JSON:
        # mandar body faria o servico responder 422 por campo ausente.
        sessao = _SessaoFalsa([_Resposta(200, {"status": "ok"})])
        with _com_sessao(sessao):
            investimentos.confirmar_execucao("bova11", quantidade=7, preco=139.5, caixa=0)
        enviado = sessao.chamadas[0]["params"]
        self.assertEqual(enviado["ativo"], "BOVA11")
        self.assertEqual(enviado["quantidade"], 7.0)
        self.assertEqual(enviado["preco"], 139.5)
        self.assertEqual(enviado["caixa"], 0.0)
        self.assertNotIn("valor", enviado)


class TimeoutPorContexto(unittest.TestCase):
    """A leitura de fundo do copiloto nao pode esperar um cold start inteiro."""

    def test_leitura_a_pedido_usa_o_teto_generoso(self):
        sessao = _SessaoFalsa([_Resposta(200, {})])
        with _com_sessao(sessao):
            investimentos.carteira()
        self.assertEqual(sessao.chamadas[0]["timeout"], investimentos.TIMEOUT_LEITURA)

    def test_leitura_de_contexto_usa_teto_curto(self):
        sessao = _SessaoFalsa([_Resposta(200, {})])
        with _com_sessao(sessao):
            investimentos.carteira(timeout=investimentos.TIMEOUT_CONTEXTO)
        self.assertEqual(sessao.chamadas[0]["timeout"], investimentos.TIMEOUT_CONTEXTO)
        self.assertLess(investimentos.TIMEOUT_CONTEXTO, investimentos.TIMEOUT_LEITURA)


class TraducaoDoEstadoInicial(unittest.TestCase):
    def test_carteira_nao_registrada_nao_e_erro(self):
        sessao = _SessaoFalsa([_Resposta(200, {
            "status": "carteira não registrada",
            "dica": "registre o primeiro aporte:  .\\carteira.ps1 aporte <valor>",
        })])
        with _com_sessao(sessao):
            resultado = hermes_tools.execute("consultar_investimentos", {}, CTX)
        self.assertNotIn("erro", resultado)
        self.assertFalse(resultado["carteira_registrada"])
        # A dica original manda rodar um script PowerShell do OUTRO repositorio,
        # que nao existe para quem fala com o Hermes.
        self.assertNotIn("carteira.ps1", str(resultado))
        self.assertIn("registrar_aporte_investimento", resultado["observacao"])

    def test_aviso_reescrito_ainda_e_lido_como_nao_registrada(self):
        # O discriminador e a ausencia de `valor_total`. Se fosse o texto de
        # `status`, uma reescrita do lado de la faria o Hermes tratar "sem
        # carteira" como se fosse um resumo valido.
        sessao = _SessaoFalsa([_Resposta(200, {"status": "nenhum aporte ainda"})])
        with _com_sessao(sessao):
            resultado = hermes_tools.execute("consultar_investimentos", {}, CTX)
        self.assertFalse(resultado["carteira_registrada"])

    def test_falha_de_rede_chega_como_erro_e_nao_como_carteira_vazia(self):
        # Confundir os dois faria o copiloto dizer "voce ainda nao investiu"
        # quando o servico so estava fora do ar.
        sessao = _SessaoFalsa(erro=TimeoutError("estourou"))
        with _com_sessao(sessao):
            resultado = hermes_tools.execute("consultar_investimentos", {}, CTX)
        self.assertIn("erro", resultado)
        self.assertNotIn("carteira_registrada", resultado)

    def test_carteira_registrada_passa_o_resumo_adiante(self):
        resumo = {"posicao": "BOVA11", "valor_total": 1043.2, "aporte_total": 1000.0,
                  "rendimento": 0.0432, "cdi_no_periodo": 0.011}
        sessao = _SessaoFalsa([_Resposta(200, dict(resumo))])
        with _com_sessao(sessao):
            resultado = hermes_tools.execute("consultar_investimentos", {}, CTX)
        self.assertTrue(resultado["carteira_registrada"])
        for campo, valor in resumo.items():
            self.assertEqual(resultado[campo], valor)


class NumerosVindosDoModelo(unittest.TestCase):
    """Os argumentos chegam de um LLM: podem vir como texto."""

    def test_valor_em_texto_numerico_e_aceito(self):
        sessao = _SessaoFalsa([_Resposta(200, {"status": "aporte registrado"})])
        with _com_sessao(sessao):
            hermes_tools.execute("registrar_aporte_investimento", {"valor": "500.50"}, CTX)
        self.assertEqual(sessao.chamadas[0]["params"]["valor"], 500.5)

    def test_valor_com_moeda_e_recusado_em_vez_de_virar_zero(self):
        # `numero()` devolve o padrao para o que nao casa com a gramatica. Se o
        # padrao vazasse como 0, um "R$ 500" viraria aporte de zero gravado em
        # silencio: aqui ele tem de parar antes da rede.
        sessao = _SessaoFalsa()
        with _com_sessao(sessao):
            resultado = hermes_tools.execute(
                "registrar_aporte_investimento", {"valor": "R$ 500,00"}, CTX
            )
        self.assertEqual(sessao.chamadas, [])
        self.assertIn("erro", resultado)
        self.assertIn("R$ 500,00", resultado["erro"])

    def test_caixa_zero_e_valido_e_diferente_de_ausente(self):
        # Zero significa "nao sobrou nada"; ausente significa "mantenha o
        # caixa anterior". Tratar um como o outro muda o estado da carteira.
        sessao = _SessaoFalsa([_Resposta(200, {})])
        with _com_sessao(sessao):
            hermes_tools.execute("registrar_execucao_investimento", {
                "ativo": "IVVB11", "quantidade": 3, "preco": 100, "caixa": 0,
            }, CTX)
        self.assertEqual(sessao.chamadas[0]["params"]["caixa"], 0.0)

    def test_caixa_ilegivel_nao_vira_zero(self):
        # Zero e valido para `caixa`, entao um padrao de 0.0 na leitura faria
        # lixo passar como "nao sobrou nada" — mudando o estado da carteira sem
        # ninguem ver. O sentinela negativo existe exatamente para isto.
        sessao = _SessaoFalsa()
        with _com_sessao(sessao):
            resultado = hermes_tools.execute("registrar_execucao_investimento", {
                "ativo": "IVVB11", "quantidade": 3, "preco": 100, "caixa": "sobrou pouco",
            }, CTX)
        self.assertEqual(sessao.chamadas, [])
        self.assertIn("erro", resultado)

    def test_caixa_negativo_e_recusado(self):
        sessao = _SessaoFalsa()
        with _com_sessao(sessao):
            resultado = hermes_tools.execute("registrar_execucao_investimento", {
                "ativo": "IVVB11", "quantidade": 3, "preco": 100, "caixa": -5,
            }, CTX)
        self.assertEqual(sessao.chamadas, [])
        self.assertIn("erro", resultado)


class CredencialRecusada(unittest.TestCase):
    def test_401_aponta_o_que_conferir(self):
        sessao = _SessaoFalsa([_Resposta(401, text="Unauthorized")])
        with _com_sessao(sessao):
            resultado = investimentos.carteira()
        self.assertIn("run.invoker", resultado["erro"])
        self.assertIn(investimentos.SA_INVOKER, resultado["erro"])


class GatingDoCanalMCP(unittest.TestCase):
    """A dupla chamada tem de valer mesmo com a politica do canal vazia.

    O dono esvaziou `system/mcp_access.confirm_tools` em 27/08/2026 para o envio
    de WhatsApp funcionar. Como o campo EXISTE como lista, ele substitui
    `_CONFIRMACAO_PADRAO` inteiro — entao registrar as tools la nao gatearia
    nada. Estar em `registry._NEEDS_CONFIRMATION` tampouco: aquele conjunto so
    alimenta o metadado `mutates`.
    """

    ESCRITAS = ("registrar_aporte_investimento", "registrar_execucao_investimento")

    def setUp(self):
        import mcp_server

        self.mcp = mcp_server
        self._cache_anterior = mcp_server._access_cache
        mcp_server._access_cache = {
            "uids": {"*"}, "confirm_tools": set(), "expires_at": float("inf"),
        }

    def tearDown(self):
        self.mcp._access_cache = self._cache_anterior

    def test_escritas_exigem_confirmacao_com_politica_vazia(self):
        for nome in self.ESCRITAS:
            with self.subTest(tool=nome):
                self.assertTrue(self.mcp._exige_confirmacao(nome))

    def test_leitura_nao_exige_confirmacao(self):
        self.assertFalse(self.mcp._exige_confirmacao("consultar_investimentos"))

    def test_o_piso_e_aditivo_e_nao_regateia_o_resto(self):
        # A decisao do repositorio para as demais tools mutantes e que o humano
        # no circuito e o pedido de permissao do cliente MCP. O piso nao pode
        # reverter isso pelas costas.
        self.assertFalse(self.mcp._exige_confirmacao("criar_acao_no_sistema"))
        self.assertFalse(self.mcp._exige_confirmacao("editar_acao"))

    def test_registry_marca_as_escritas_como_mutantes(self):
        from tools import registry

        for nome in self.ESCRITAS:
            with self.subTest(tool=nome):
                self.assertTrue(registry.needs_confirmation(nome))


class NadaEscreveNoFirestore(unittest.TestCase):
    def test_o_modulo_nao_toca_no_firestore(self):
        """O contrato com o outro sistema e a API HTTP, e so ela.

        As colecoes `decisao_investimentos_*` sao do servico, que mantem
        invariantes (aporte acumulado, primeira data, log de movimentos) que uma
        escrita por fora quebraria sem erro visivel.
        """
        with open("investimentos.py", encoding="utf-8") as f:
            fonte = f.read()
        for proibido in ("firestore", "firebase_admin", "decisao_investimentos_"):
            self.assertNotIn(
                proibido, fonte.split('"""', 2)[2],
                f"`{proibido}` aparece no codigo de investimentos.py",
            )


if __name__ == "__main__":
    unittest.main()
