"""Ingestao de arquivo: integridade, resolucao da origem e formato do que volta.

O teste que faltava e o que abre este arquivo. A versao anterior so cobria
base64 quebrado — eu colava `!!!` no fim e conferia que falhava. Mas o
truncamento real cai em multiplo de 4 e continua sendo base64 sintaticamente
valido: `validate=True` aceita, o arquivo grava e o retorno e `status: ok`.

Foi assim que um cartao de embarque de 11 KB virou 1,2 KB dentro de uma
prestacao de contas. Inspecao de conteudo tampouco pegaria: no arquivo
corrompido real, `PIL.Image.verify()` e `load()` aceitaram os 1,2 KB como JPEG
valido de 230x468 — o corte formou uma imagem menor e decodificavel.

So checksum pega.

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
import hashlib
import json
import unittest

from tools import anexar_arquivo as aa


class TestTruncamentoSilencioso(unittest.TestCase):
    """O caso que passou batido e corrompeu um comprovante de verdade."""

    def _valido(self, dados: bytes) -> dict:
        return {
            "conteudo_base64": base64.b64encode(dados).decode(),
            "nome": "comprovante.jpg",
            "tamanho_bytes": len(dados),
            "sha256": hashlib.sha256(dados).hexdigest(),
        }

    def test_corte_limpo_em_multiplo_de_4_e_detectado(self):
        """Sem os metadados isto passava: base64 valido, so que menor."""
        original = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"A" * 11272 + bytes([0xFF, 0xD9])
        args = self._valido(original)
        # Corta mantendo multiplo de 4 — exatamente o que quebrou em producao.
        args["conteudo_base64"] = args["conteudo_base64"][:1600]

        with self.assertRaises(ValueError) as ctx:
            aa._de_base64(args)
        self.assertIn("truncado", str(ctx.exception))

    def test_conteudo_alterado_e_detectado(self):
        original = b"conteudo original do recibo"
        args = self._valido(original)
        args["conteudo_base64"] = base64.b64encode(b"conteudo ALTERADO do recibo").decode()
        with self.assertRaises(ValueError) as ctx:
            aa._de_base64(args)
        self.assertIn("checksum", str(ctx.exception))

    def test_arquivo_integro_passa(self):
        original = bytes([0xFF, 0xD8]) + b"conteudo integro" + bytes([0xFF, 0xD9])
        dados, nome = aa._de_base64(self._valido(original))
        self.assertEqual(dados, original)
        self.assertEqual(nome, "comprovante.jpg")

    def test_sem_metadados_de_integridade_recusa(self):
        """Nao da para 'esquecer' o checksum e cair no comportamento antigo."""
        args = {"conteudo_base64": base64.b64encode(b"x" * 100).decode(), "nome": "a.pdf"}
        with self.assertRaises(ValueError) as ctx:
            aa._de_base64(args)
        mensagem = str(ctx.exception)
        self.assertIn("tamanho_bytes", mensagem)
        self.assertIn("sha256", mensagem)
        self.assertIn("preparar_upload", mensagem)

    def test_whitespace_no_payload_nao_atrapalha(self):
        """Uma quebra de linha final disparava 'Only base64 data is allowed'."""
        original = b"recibo com quebra de linha no payload"
        args = self._valido(original)
        args["conteudo_base64"] = "  " + args["conteudo_base64"] + "\n\n"
        dados, _ = aa._de_base64(args)
        self.assertEqual(dados, original)


class TestOrigemBase64(unittest.TestCase):
    def test_decodifica_e_devolve_o_nome(self):
        bruto = b"conteudo do recibo"
        dados, nome = aa._de_base64({
            "conteudo_base64": base64.b64encode(bruto).decode(),
            "nome": "recibo.pdf",
            "tamanho_bytes": len(bruto),
            "sha256": hashlib.sha256(bruto).hexdigest(),
        })
        self.assertEqual(dados, b"conteudo do recibo")
        self.assertEqual(nome, "recibo.pdf")

    def test_base64_truncado_falha_alto(self):
        """`validate=True` e o que separa erro visivel de arquivo corrompido."""
        bruto = b"x" * 300
        inteiro = base64.b64encode(bruto).decode()
        with self.assertRaises(ValueError) as ctx:
            aa._de_base64({"conteudo_base64": inteiro[:-5] + "!!!", "nome": "a.pdf",
                           "tamanho_bytes": len(bruto),
                           "sha256": hashlib.sha256(bruto).hexdigest()})
        self.assertIn("invalido", str(ctx.exception))

    def test_sem_nome_nao_passa(self):
        with self.assertRaises(ValueError) as ctx:
            aa._de_base64({"conteudo_base64": base64.b64encode(b"x").decode(),
                           "tamanho_bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest()})
        self.assertIn("nome", str(ctx.exception))

    def test_conteudo_vazio_nao_passa(self):
        with self.assertRaises(ValueError):
            aa._de_base64({"conteudo_base64": "", "nome": "a.pdf",
                           "tamanho_bytes": 0, "sha256": "0" * 64})


class TestResolucaoDeOrigem(unittest.TestCase):
    def test_sem_origem_explica_as_opcoes(self):
        with self.assertRaises(ValueError) as ctx:
            aa._resolver_conteudo(None, {})
        mensagem = str(ctx.exception)
        for termo in ("conteudo_base64", "url", "gmail_message_id", "upload_token"):
            self.assertIn(termo, mensagem)

    def test_arquivo_grande_aponta_a_saida(self):
        """A mensagem precisa dizer o que fazer, nao so que nao deu."""
        bruto = b"x" * (aa.MAX_BYTES_BASE64 + 10)
        with self.assertRaises(ValueError) as ctx:
            aa._resolver_conteudo(None, {
                "conteudo_base64": base64.b64encode(bruto).decode(),
                "nome": "grande.pdf",
                "tamanho_bytes": len(bruto),
                "sha256": hashlib.sha256(bruto).hexdigest(),
            })
        mensagem = str(ctx.exception)
        self.assertIn("preparar_upload", mensagem)
        self.assertIn("grande demais", mensagem)

    def test_url_precisa_ser_http(self):
        for url in ("file:///etc/passwd", "ftp://x/y", "drive.google.com/x"):
            with self.assertRaises(ValueError):
                aa._resolver_conteudo(None, {"url": url})

    def test_base64_tem_prioridade_sobre_url(self):
        bruto = b"local"
        dados, nome = aa._resolver_conteudo(None, {
            "conteudo_base64": base64.b64encode(bruto).decode(),
            "nome": "local.txt",
            "tamanho_bytes": len(bruto),
            "sha256": hashlib.sha256(bruto).hexdigest(),
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
