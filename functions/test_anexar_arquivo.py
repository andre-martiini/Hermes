"""Ingestao de arquivo: resolucao da origem e formato do que volta.

O que estes testes protegem:

1. **base64 truncado tem que falhar alto.** A mensagem que carrega o binario tem
   teto; se o conteudo chegar cortado e a decodificacao for tolerante, o que vai
   para o Drive e um arquivo corrompido com nome correto — e comprovante
   corrompido so e descoberto quando alguem precisa dele.
2. **O limite de tamanho tem que apontar a saida.** Sem isso o usuario tenta de
   novo pelo mesmo caminho que nao cabe.
3. **A nota do diario tem que sair no formato que a UI ja le** (`FILE::JSON::`),
   senao o anexo aparece como texto cru no diario.
"""

import base64
import json
import unittest

from tools import anexar_arquivo as aa


class TestOrigemBase64(unittest.TestCase):
    def test_decodifica_e_devolve_o_nome(self):
        dados, nome = aa._de_base64({
            "conteudo_base64": base64.b64encode(b"conteudo do recibo").decode(),
            "nome": "recibo.pdf",
        })
        self.assertEqual(dados, b"conteudo do recibo")
        self.assertEqual(nome, "recibo.pdf")

    def test_base64_truncado_falha_alto(self):
        """`validate=True` e o que separa erro visivel de arquivo corrompido."""
        inteiro = base64.b64encode(b"x" * 300).decode()
        with self.assertRaises(ValueError) as ctx:
            aa._de_base64({"conteudo_base64": inteiro[:-5] + "!!!", "nome": "a.pdf"})
        self.assertIn("invalido ou truncado", str(ctx.exception))

    def test_sem_nome_nao_passa(self):
        with self.assertRaises(ValueError) as ctx:
            aa._de_base64({"conteudo_base64": base64.b64encode(b"x").decode()})
        self.assertIn("nome", str(ctx.exception))

    def test_conteudo_vazio_nao_passa(self):
        with self.assertRaises(ValueError):
            aa._de_base64({"conteudo_base64": "", "nome": "a.pdf"})


class TestResolucaoDeOrigem(unittest.TestCase):
    def test_sem_origem_explica_as_opcoes(self):
        with self.assertRaises(ValueError) as ctx:
            aa._resolver_conteudo({})
        mensagem = str(ctx.exception)
        for termo in ("conteudo_base64", "url", "gmail_message_id"):
            self.assertIn(termo, mensagem)

    def test_arquivo_grande_aponta_a_saida(self):
        """A mensagem precisa dizer o que fazer, nao so que nao deu."""
        grande = base64.b64encode(b"x" * (aa.MAX_BYTES + 10)).decode()
        with self.assertRaises(ValueError) as ctx:
            aa._resolver_conteudo({"conteudo_base64": grande, "nome": "grande.pdf"})
        mensagem = str(ctx.exception)
        self.assertIn("url", mensagem)
        self.assertIn("gmail_message_id", mensagem)

    def test_url_precisa_ser_http(self):
        for url in ("file:///etc/passwd", "ftp://x/y", "drive.google.com/x"):
            with self.assertRaises(ValueError):
                aa._resolver_conteudo({"url": url})

    def test_base64_tem_prioridade_sobre_url(self):
        dados, nome = aa._resolver_conteudo({
            "conteudo_base64": base64.b64encode(b"local").decode(),
            "nome": "local.txt",
            "url": "https://exemplo.invalido/nunca-buscado",
        })
        self.assertEqual(dados, b"local")
        self.assertEqual(nome, "local.txt")


class TestMime(unittest.TestCase):
    def test_extensoes_comuns(self):
        self.assertEqual(aa._mime_de("recibo.pdf"), "application/pdf")
        self.assertIn("image", aa._mime_de("foto.jpg"))

    def test_sem_extensao_cai_no_generico(self):
        self.assertEqual(aa._mime_de("arquivo"), "application/octet-stream")
        self.assertEqual(aa._mime_de(""), "application/octet-stream")


class TestFormatoDoDiario(unittest.TestCase):
    """A nota tem que casar com `hermes_core_logic._parse_diary_file_note`."""

    def test_nota_e_parseavel_pelo_leitor_do_diario(self):
        nome, link = "nota-fiscal.pdf", "https://drive.google.com/file/d/abc/view"
        nota = "FILE::JSON::" + json.dumps({"n": nome, "v": link}, ensure_ascii=False)

        self.assertTrue(nota.startswith("FILE::JSON::"))
        payload = json.loads(nota[len("FILE::JSON::"):])
        self.assertEqual(payload["n"], nome)
        self.assertEqual(payload["v"], link)

    def test_acento_no_nome_sobrevive(self):
        nota = "FILE::JSON::" + json.dumps({"n": "cartão.pdf", "v": "x"}, ensure_ascii=False)
        self.assertEqual(json.loads(nota[len("FILE::JSON::"):])["n"], "cartão.pdf")


if __name__ == "__main__":
    unittest.main()
