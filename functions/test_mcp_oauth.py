"""Contrato do authorization server OAuth 2.1 do Hermes.

Os modos de falha cobertos aqui sao os que o cliente nao consegue diagnosticar:
metadata sem um campo obrigatorio faz a conexao morrer em "Couldn't reach the
MCP server", e um codigo de erro fora do RFC 6749 faz o refresh falhar em
silencio ate a sessao expirar. Nada aqui usa rede ou Firestore.
"""

import base64
import hashlib
import json
import unittest
from unittest import mock

import mcp_oauth
import mcp_server

_SEGREDO_DE_TESTE = "segredo-fixo-para-teste-nao-usado-em-producao"


def _pkce(verifier: str) -> str:
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")


class TestDiscovery(unittest.TestCase):
    """Campos que o cliente le antes de qualquer autenticacao."""

    def test_resource_bate_com_a_url_do_mcp(self):
        """O `resource` tem de ser a URL exata que o usuario digita no cliente."""
        prm = mcp_oauth.protected_resource_metadata()
        self.assertEqual(prm["resource"], mcp_oauth.MCP_RESOURCE)
        self.assertTrue(prm["resource"].startswith("https://"))

    def test_prm_aponta_para_o_authorization_server(self):
        prm = mcp_oauth.protected_resource_metadata()
        self.assertEqual(prm["authorization_servers"], [mcp_oauth.ISSUER])

    def test_as_metadata_anuncia_s256(self):
        """Obrigatorio: clientes conformes conferem isto antes de iniciar o fluxo."""
        meta = mcp_oauth.authorization_server_metadata()
        self.assertEqual(meta["code_challenge_methods_supported"], ["S256"])

    def test_as_metadata_tem_os_campos_obrigatorios(self):
        meta = mcp_oauth.authorization_server_metadata()
        for campo in ("issuer", "authorization_endpoint", "token_endpoint",
                      "registration_endpoint", "response_types_supported",
                      "grant_types_supported", "token_endpoint_auth_methods_supported"):
            self.assertIn(campo, meta, f"metadata sem '{campo}'")

    def test_issuer_bate_com_os_endpoints(self):
        """Um endpoint em outra origem quebra a validacao de issuer do cliente."""
        meta = mcp_oauth.authorization_server_metadata()
        for chave in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):
            self.assertTrue(meta[chave].startswith(meta["issuer"] + "/"), chave)

    def test_dcr_anunciado_como_cliente_publico(self):
        """DCR registra o Claude como cliente publico; o PKCE substitui o segredo."""
        meta = mcp_oauth.authorization_server_metadata()
        self.assertIn("none", meta["token_endpoint_auth_methods_supported"])
        self.assertIn("refresh_token", meta["grant_types_supported"])


class TestPkce(unittest.TestCase):
    def test_verifier_correto(self):
        v = "um-verifier-suficientemente-longo-para-o-teste-1234567890"
        self.assertTrue(mcp_oauth._verificar_pkce(v, _pkce(v)))

    def test_verifier_errado(self):
        v = "um-verifier-suficientemente-longo-para-o-teste-1234567890"
        self.assertFalse(mcp_oauth._verificar_pkce("outro-verifier-qualquer", _pkce(v)))

    def test_challenge_vazio_nao_passa(self):
        self.assertFalse(mcp_oauth._verificar_pkce("qualquer-coisa", ""))

    def test_challenge_sem_padding_base64url(self):
        """O challenge do RFC 7636 e base64url SEM '='; com padding nao casaria."""
        v = "verifier-de-teste-para-conferir-o-padding-aqui-ok"
        self.assertNotIn("=", _pkce(v))
        self.assertTrue(mcp_oauth._verificar_pkce(v, _pkce(v)))


class TestRedirectUri(unittest.TestCase):
    """Loopback com porta efemera e o caso do Claude Code (RFC 8252)."""

    HOSPEDADA = "https://claude.ai/api/mcp/auth_callback"
    LOOPBACK = ["http://localhost/callback", "http://127.0.0.1/callback"]

    def test_superficie_hospedada_casa_exatamente(self):
        self.assertTrue(mcp_oauth._redirect_permitido([self.HOSPEDADA], self.HOSPEDADA))

    def test_loopback_ignora_a_porta(self):
        for pedida in ("http://localhost:3118/callback", "http://127.0.0.1:51234/callback"):
            self.assertTrue(mcp_oauth._redirect_permitido(self.LOOPBACK, pedida), pedida)

    def test_loopback_com_outro_path_e_recusado(self):
        self.assertFalse(
            mcp_oauth._redirect_permitido(self.LOOPBACK, "http://localhost:3118/roubado"))

    def test_host_externo_e_recusado(self):
        for pedida in ("https://evil.example.com/callback",
                       "http://evil.example.com/callback"):
            self.assertFalse(mcp_oauth._redirect_permitido(self.LOOPBACK, pedida), pedida)

    def test_https_em_loopback_nao_afrouxa_a_regra(self):
        """A excecao de porta vale so para http em loopback."""
        self.assertFalse(
            mcp_oauth._redirect_permitido(self.LOOPBACK, "https://localhost:3118/callback"))

    def test_nada_registrado_recusa_tudo(self):
        self.assertFalse(mcp_oauth._redirect_permitido([], self.HOSPEDADA))


@mock.patch.object(mcp_oauth, "_signing_secret", lambda: _SEGREDO_DE_TESTE)
class TestAccessToken(unittest.TestCase):
    def test_ida_e_volta(self):
        token = mcp_oauth.emitir_access_token(
            "uid-1", "cliente-1", mcp_oauth.SCOPE_PADRAO, mcp_oauth.MCP_RESOURCE)
        claims = mcp_oauth.validar_access_token(token)
        self.assertIsNotNone(claims)
        self.assertEqual(claims["sub"], "uid-1")
        self.assertEqual(claims["aud"], mcp_oauth.MCP_RESOURCE)
        self.assertEqual(claims["iss"], mcp_oauth.ISSUER)

    def test_audience_errada_e_recusada(self):
        """Token emitido para outro recurso nao pode abrir o MCP."""
        token = mcp_oauth.emitir_access_token(
            "uid-1", "cliente-1", mcp_oauth.SCOPE_PADRAO, "https://outro.example.com/mcp")
        self.assertIsNone(mcp_oauth.validar_access_token(token))

    def test_assinatura_de_outro_segredo_e_recusada(self):
        import jwt

        forjado = jwt.encode(
            {"iss": mcp_oauth.ISSUER, "sub": "invasor",
             "aud": mcp_oauth.MCP_RESOURCE, "exp": 9999999999},
            "segredo-do-atacante-com-mais-de-32-bytes-para-nao-gerar-warning",
            algorithm="HS256")
        self.assertIsNone(mcp_oauth.validar_access_token(forjado))

    def test_token_expirado_e_recusado(self):
        import jwt

        vencido = jwt.encode(
            {"iss": mcp_oauth.ISSUER, "sub": "uid-1",
             "aud": mcp_oauth.MCP_RESOURCE, "exp": 1000000000},
            _SEGREDO_DE_TESTE, algorithm="HS256")
        self.assertIsNone(mcp_oauth.validar_access_token(vencido))

    def test_lixo_nao_derruba_a_validacao(self):
        for entrada in ("", "nao-e-um-jwt", "a.b.c"):
            self.assertIsNone(mcp_oauth.validar_access_token(entrada))


class TestErrosRfc6749(unittest.TestCase):
    def test_codigo_de_erro_no_corpo(self):
        resp = mcp_oauth._erro_oauth("invalid_grant", "detalhe")
        corpo = json.loads(resp.get_data(as_text=True))
        self.assertEqual(corpo["error"], "invalid_grant")
        self.assertIn("error_description", corpo)

    def test_grant_desconhecido(self):
        """`unsupported_grant_type` e o codigo do RFC; um custom quebra o cliente."""
        class _Req:
            form = None
            def get_json(self, silent=False):
                return {"grant_type": "senha_magica", "client_id": "c"}

        corpo = json.loads(mcp_oauth._handle_token(_Req()).get_data(as_text=True))
        self.assertEqual(corpo["error"], "unsupported_grant_type")


class TestDesafio401(unittest.TestCase):
    """Sem este header no 401, o Claude nunca descobre o authorization server."""

    def test_401_carrega_www_authenticate(self):
        resp = mcp_server._json_rpc_error(1, -32001, "sem token")
        self.assertEqual(resp.status_code, 401)
        desafio = resp.headers.get("WWW-Authenticate", "")
        self.assertTrue(desafio.startswith("Bearer "), desafio)
        self.assertIn("resource_metadata=", desafio)

    def test_resource_metadata_aponta_para_o_prm_servido(self):
        desafio = mcp_server._json_rpc_error(1, -32001, "x").headers["WWW-Authenticate"]
        self.assertIn(mcp_server._RESOURCE_METADATA_URL, desafio)
        self.assertTrue(mcp_server._RESOURCE_METADATA_URL.startswith(mcp_oauth.ISSUER + "/"))

    def test_prm_e_servido_na_url_anunciada(self):
        """A URL do desafio tem de ser uma rota que o roteador de fato atende."""
        caminho = mcp_server._RESOURCE_METADATA_URL[len(mcp_oauth.ISSUER):]
        self.assertTrue(caminho.endswith("/.well-known/oauth-protected-resource"))

    def test_403_nao_carrega_desafio(self):
        """UID conhecido mas fora da allowlist: reautenticar nao resolve."""
        resp = mcp_server._json_rpc_error(1, -32002, "nao autorizado")
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn("WWW-Authenticate", resp.headers)


class TestRoteamento(unittest.TestCase):
    class _Req:
        def __init__(self, path, method="GET"):
            self.path, self.method = path, method
            self.form = None
            self.args = {}
        def get_json(self, silent=False):
            return {}

    def setUp(self):
        import inspect
        self.handler = inspect.unwrap(mcp_oauth.mcpOAuth)

    def test_discovery_responde_sem_autenticacao(self):
        for caminho, chave in (
            ("/.well-known/oauth-protected-resource", "resource"),
            ("/.well-known/oauth-authorization-server", "issuer"),
        ):
            resp = self.handler(self._Req(caminho))
            self.assertEqual(resp.status_code, 200, caminho)
            self.assertIn(chave, json.loads(resp.get_data(as_text=True)))

    def test_discovery_com_barra_final(self):
        resp = self.handler(self._Req("/.well-known/oauth-authorization-server/"))
        self.assertEqual(resp.status_code, 200)

    def test_rota_desconhecida_404(self):
        resp = self.handler(self._Req("/oauth/inexistente"))
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
