"""Testes de `atualizar_arquivo_drive` (tools/drive_arquivos.py).

O conector do Drive so cria arquivo; esta ferramenta troca o conteudo no MESMO
arquivo. O Drive e substituido por um duble que registra o que seria atualizado:
o comportamento real (ID e link mantidos, conversao de HTML/Markdown/texto em Doc,
md5 do texto comum) foi comprovado contra o Drive de verdade em 20/09/2026.
"""

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import mcp_server
from tools import drive_arquivos, hermes_tools, registry

DOC = "application/vnd.google-apps.document"
BOM = "﻿"


class _Exec:
    def __init__(self, valor=None, erro=None):
        self.valor, self.erro = valor, erro

    def execute(self):
        if self.erro:
            raise self.erro
        return self.valor


def _erro_http(status: int) -> Exception:
    exc = Exception(f"HTTP {status}")
    exc.resp = SimpleNamespace(status=status)
    return exc


class DriveFalso:
    """Duble do servico do Drive (`files()` e `revisions()`)."""

    def __init__(self, meta, *, export=None, md5_errado=False, get_erro=None, update_erro=None,
                 export_erro=None, revisoes=2, revisoes_erro=None, export_seq=None):
        self.meta = meta
        self.export_seq = list(export_seq) if export_seq else None
        self.export_valor = (BOM + "Texto do documento").encode("utf-8") if export is None else export
        self.md5_errado, self.get_erro, self.update_erro = md5_errado, get_erro, update_erro
        self.export_erro, self.revisoes, self.revisoes_erro = export_erro, revisoes, revisoes_erro
        self.get_kw = self.update_kw = None
        self.updates = 0

    def files(self):
        return self

    def revisions(self):
        return self

    def get(self, **kw):
        self.get_kw = kw
        return _Exec(self.meta, self.get_erro)

    def update(self, **kw):
        self.update_kw = kw
        self.updates += 1
        _, dados, _mime = kw["media_body"]
        md5 = "0" * 32 if self.md5_errado else hashlib.md5(dados).hexdigest()
        return _Exec({"id": kw["fileId"], "name": self.meta["name"], "mimeType": self.meta["mimeType"],
                      "modifiedTime": "2026-09-20T15:00:00.000Z", "md5Checksum": md5,
                      "webViewLink": f"https://docs.google.com/document/d/{kw['fileId']}/edit"},
                     self.update_erro)

    def export(self, **kw):
        valor = self.export_seq.pop(0) if self.export_seq else self.export_valor
        return _Exec(valor, self.export_erro)

    def list(self, **kw):
        return _Exec({"revisions": [{"id": str(i)} for i in range(self.revisoes)]}, self.revisoes_erro)


def _meta(mime=DOC, **extra):
    return {"id": "ARQ1234567890", "name": "Relatorio", "mimeType": mime,
            "trashed": False, "ownedByMe": True, "capabilities": {"canEdit": True}, **extra}


def _atualizar(drive, args, *, executar=True):
    args = {"file_id": "ARQ1234567890", "conteudo": "<h1>Novo</h1>", **args}
    with patch.object(drive_arquivos, "_servico_drive", return_value=drive), \
         patch.object(drive_arquivos, "_midia", side_effect=lambda dados, mime: ("midia", dados, mime)):
        return drive_arquivos.atualizar_conteudo(None, args)


class TestGoogleDoc(unittest.TestCase):
    def test_atualiza_no_mesmo_id_com_html_por_padrao(self):
        drive = DriveFalso(_meta())
        r = _atualizar(drive, {})
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["file_id"], "ARQ1234567890")
        self.assertEqual(drive.update_kw["fileId"], "ARQ1234567890")
        self.assertEqual(drive.update_kw["media_body"][2], "text/html")
        self.assertEqual(drive.update_kw["media_body"][1], b"<h1>Novo</h1>")
        self.assertEqual(r["tipo"], DOC)
        self.assertIn("/d/ARQ1234567890/", r["link"])
        self.assertEqual(r["versoes_no_historico"], 2)
        self.assertIs(r["verificado"], True)
        self.assertIn("nada foi criado", r["aviso"])

    def test_aceita_markdown_e_texto_puro(self):
        for tipo in ("text/markdown", "text/plain"):
            with self.subTest(tipo=tipo):
                drive = DriveFalso(_meta())
                self.assertEqual(_atualizar(drive, {"tipo_conteudo": tipo})["status"], "ok")
                self.assertEqual(drive.update_kw["media_body"][2], tipo)

    def test_tipo_de_conteudo_invalido_para_doc_nao_grava(self):
        drive = DriveFalso(_meta())
        r = _atualizar(drive, {"tipo_conteudo": "application/pdf"})
        self.assertIn("erro", r)
        self.assertEqual(drive.updates, 0)

    def test_doc_que_ficou_vazio_apos_a_conversao_e_erro_que_manda_restaurar(self):
        drive = DriveFalso(_meta(), export=(BOM + "  \r\n").encode("utf-8"))
        r = _atualizar(drive, {})
        self.assertIn("erro", r)
        self.assertIn("Historico de versoes", r["erro"])
        self.assertEqual(r["file_id"], "ARQ1234567890")

    def test_falha_ao_verificar_nao_derruba_uma_gravacao_que_aconteceu(self):
        drive = DriveFalso(_meta(), export_erro=RuntimeError("export caiu"))
        r = _atualizar(drive, {})
        self.assertEqual(r["status"], "ok")
        self.assertIs(r["verificado"], False)

    def test_falha_ao_listar_versoes_nao_derruba_e_devolve_none(self):
        r = _atualizar(DriveFalso(_meta(), revisoes_erro=RuntimeError("x")), {})
        self.assertEqual(r["status"], "ok")
        self.assertIsNone(r["versoes_no_historico"])


class TestArquivoDeTexto(unittest.TestCase):
    def test_mantem_o_tipo_do_arquivo_e_confere_o_md5(self):
        drive = DriveFalso(_meta("text/markdown"))
        r = _atualizar(drive, {"conteudo": "# Versão 2\nação\n", "tipo_conteudo": "text/html"})
        self.assertEqual(r["status"], "ok")
        self.assertEqual(drive.update_kw["media_body"][2], "text/markdown")
        self.assertEqual(drive.update_kw["media_body"][1], "# Versão 2\nação\n".encode("utf-8"))
        self.assertIs(r["verificado"], True)
        self.assertEqual(r["bytes_enviados"], len("# Versão 2\nação\n".encode("utf-8")))

    def test_md5_diferente_do_enviado_e_erro(self):
        r = _atualizar(DriveFalso(_meta("text/plain"), md5_errado=True), {})
        self.assertIn("erro", r)
        self.assertIn("diferente", r["erro"])

    def test_json_e_aceito_como_texto(self):
        self.assertEqual(_atualizar(DriveFalso(_meta("application/json")), {"conteudo": "{}"})["status"], "ok")

    def test_sem_md5_no_retorno_nao_verifica_mas_grava(self):
        drive = DriveFalso(_meta("text/plain"))
        original = drive.update

        def sem_md5(**kw):
            resultado = original(**kw)
            resultado.valor.pop("md5Checksum")
            return resultado

        drive.update = sem_md5
        r = _atualizar(drive, {})
        self.assertEqual(r["status"], "ok")
        self.assertIs(r["verificado"], False)


class TestRecusas(unittest.TestCase):
    def test_tipos_nao_suportados_nao_gravam(self):
        for mime in ("application/vnd.google-apps.folder", "application/vnd.google-apps.spreadsheet",
                     "application/vnd.google-apps.presentation", "application/vnd.google-apps.form",
                     "application/pdf", "image/png",
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
            with self.subTest(mime=mime):
                drive = DriveFalso(_meta(mime))
                r = _atualizar(drive, {})
                self.assertIn("erro", r)
                self.assertIn("Nada foi alterado", r["erro"])
                self.assertEqual(drive.updates, 0)

    def test_planilha_explica_o_risco_das_abas(self):
        r = _atualizar(DriveFalso(_meta("application/vnd.google-apps.spreadsheet")), {})
        self.assertIn("abas", r["erro"])

    def test_conteudo_vazio_ou_so_espacos_nao_chega_ao_drive(self):
        for vazio in ("", "   \n\t", None, 5):
            with self.subTest(conteudo=vazio):
                drive = DriveFalso(_meta())
                with patch.object(drive_arquivos, "_servico_drive") as servico:
                    r = drive_arquivos.atualizar_conteudo(None, {"file_id": "ARQ1234567890", "conteudo": vazio})
                self.assertIn("erro", r)
                servico.assert_not_called()
                self.assertEqual(drive.updates, 0)

    def test_conteudo_acima_do_limite_nao_chega_ao_drive(self):
        with patch.object(drive_arquivos, "_servico_drive") as servico:
            r = drive_arquivos.atualizar_conteudo(
                None, {"file_id": "ARQ1234567890", "conteudo": "x" * (drive_arquivos.MAX_BYTES + 1)})
        self.assertIn("excede", r["erro"])
        servico.assert_not_called()

    def test_sem_file_id(self):
        self.assertIn("file_id", drive_arquivos.atualizar_conteudo(None, {"conteudo": "x"})["erro"])

    def test_arquivo_na_lixeira_ou_sem_permissao_nao_grava(self):
        casos = {"lixeira": {"trashed": True}, "permissao": {"capabilities": {"canEdit": False}}}
        for nome, extra in casos.items():
            with self.subTest(caso=nome):
                drive = DriveFalso({**_meta(), **extra})
                self.assertIn("erro", _atualizar(drive, {}))
                self.assertEqual(drive.updates, 0)

    def test_erros_do_drive_viram_mensagens_legiveis(self):
        r = _atualizar(DriveFalso(_meta(), get_erro=_erro_http(404)), {})
        self.assertIn("nao encontrado", r["erro"])
        r = _atualizar(DriveFalso(_meta(), update_erro=_erro_http(403)), {})
        self.assertIn("permissao", r["erro"])
        r = _atualizar(DriveFalso(_meta(), update_erro=RuntimeError("boom")), {})
        self.assertIn("Falha ao atualizar", r["erro"])


def _texto(n_palavras: int) -> str:
    return " ".join(["palavra"] * n_palavras)


class TestDonoDoArquivo(unittest.TestCase):
    def test_arquivo_de_outra_pessoa_ou_drive_compartilhado_nao_grava(self):
        drive = DriveFalso(_meta(ownedByMe=False))
        r = _atualizar(drive, {})
        self.assertIn("outra pessoa", r["erro"])
        self.assertIn("Nada foi alterado", r["erro"])
        self.assertEqual(drive.updates, 0)

    def test_item_de_drive_compartilhado_nao_grava_mesmo_sem_ownedbyme(self):
        # A API nao preenche `ownedByMe` nesses itens; o sinal e o `driveId`.
        meta = _meta(driveId="0AB12345")
        meta.pop("ownedByMe")
        drive = DriveFalso(meta)
        r = _atualizar(drive, {})
        self.assertIn("Drive compartilhado", r["erro"])
        self.assertEqual(drive.updates, 0)

    def test_arquivo_do_dono_passa(self):
        self.assertEqual(_atualizar(DriveFalso(_meta(ownedByMe=True)), {})["status"], "ok")

    def test_campo_ausente_na_resposta_nao_bloqueia(self):
        meta = _meta()
        meta.pop("ownedByMe")
        self.assertEqual(_atualizar(DriveFalso(meta), {})["status"], "ok")


class TestGuardaContraReescritaTruncada(unittest.TestCase):
    """A ferramenta exige o documento COMPLETO; um envio incompleto apagaria o resto."""

    ATUAL = (BOM + _texto(200)).encode("utf-8")  # ~1600 caracteres

    def _drive(self, **kw):
        return DriveFalso(_meta(), export_seq=[self.ATUAL, self.ATUAL], **kw)

    def test_doc_com_conteudo_muito_menor_e_recusado(self):
        drive = self._drive()
        r = _atualizar(drive, {"conteudo": "<p>" + _texto(20) + "</p>"})
        self.assertIn("permitir_reducao", r["erro"])
        self.assertIn("caracteres", r["erro"])
        self.assertIn("Nada foi alterado", r["erro"])
        self.assertEqual(drive.updates, 0)

    def test_permitir_reducao_libera_o_encurtamento_de_proposito(self):
        drive = self._drive()
        r = _atualizar(drive, {"conteudo": "<p>" + _texto(20) + "</p>", "permitir_reducao": True})
        self.assertEqual(r["status"], "ok")
        self.assertEqual(drive.updates, 1)

    def test_doc_com_tamanho_parecido_passa(self):
        self.assertEqual(_atualizar(self._drive(), {"conteudo": "<p>" + _texto(180) + "</p>"})["status"], "ok")

    def test_so_o_texto_visivel_conta_nao_as_tags(self):
        # ~1100 caracteres brutos de HTML, mas so 50 visiveis: isto e truncamento disfarcado.
        r = _atualizar(self._drive(), {"conteudo": "<p><b><i>x</i></b></p>" * 50})
        self.assertIn("permitir_reducao", r["erro"])

    def test_style_e_script_nao_contam_como_texto(self):
        r = _atualizar(self._drive(), {"conteudo": "<style>" + "a" * 5000 + "</style><p>curto</p>"})
        self.assertIn("permitir_reducao", r["erro"])

    def test_doc_pequeno_nao_aciona_a_guarda(self):
        pequeno = (BOM + _texto(20)).encode("utf-8")  # ~160 caracteres, abaixo do minimo
        drive = DriveFalso(_meta(), export_seq=[pequeno, pequeno])
        self.assertEqual(_atualizar(drive, {"conteudo": "<p>oi</p>"})["status"], "ok")

    def test_arquivo_de_texto_compara_bytes(self):
        casos = (("5000", "x" * 100, False), ("5000", "x" * 3000, True), ("5000", "x" * 100, True))
        for i, (tamanho, conteudo, deve_passar) in enumerate(casos):
            with self.subTest(tamanho=tamanho, novo=len(conteudo), liberado=(i == 2)):
                drive = DriveFalso(_meta("text/plain", size=tamanho))
                args = {"conteudo": conteudo}
                if i == 2:
                    args["permitir_reducao"] = True
                r = _atualizar(drive, args)
                if deve_passar:
                    self.assertEqual(r["status"], "ok")
                else:
                    self.assertIn("bytes", r["erro"])
                    self.assertEqual(drive.updates, 0)

    def test_arquivo_de_texto_sem_tamanho_conhecido_nao_bloqueia(self):
        self.assertEqual(_atualizar(DriveFalso(_meta("text/plain")), {"conteudo": "curto"})["status"], "ok")

    def test_sem_conseguir_medir_a_guarda_nao_bloqueia(self):
        drive = DriveFalso(_meta(), export_erro=RuntimeError("export caiu"))
        r = _atualizar(drive, {"conteudo": "<p>curto</p>"})
        self.assertEqual(r["status"], "ok")
        self.assertEqual(drive.updates, 1)

    def test_estimativa_do_texto_visivel(self):
        visivel = drive_arquivos._texto_visivel
        self.assertEqual(visivel("<h1>Olá</h1><p>mundo <b>bom</b></p><script>alert(1)</script>", "text/html"),
                         "Olá mundo bom")
        self.assertEqual(visivel("# Título\n\n**negrito** [link](http://exemplo.com/x)", "text/markdown"),
                         "Título negrito link")
        self.assertEqual(visivel("  duas   palavras\n", "text/plain"), "duas palavras")


class TestIdDoArquivo(unittest.TestCase):
    def test_link_do_docs_e_do_drive_viram_id(self):
        casos = {
            "https://docs.google.com/document/d/1LozJ2CrFtHI-pDSLY_YTVowtg13knlCp8rgHC2sgffc/edit?usp=drivesdk":
                "1LozJ2CrFtHI-pDSLY_YTVowtg13knlCp8rgHC2sgffc",
            "https://drive.google.com/file/d/18OvOHZfVZl8uUGCL4XiRgPJyKwFLdX1T/view": "18OvOHZfVZl8uUGCL4XiRgPJyKwFLdX1T",
            "https://drive.google.com/open?id=18OvOHZfVZl8uUGCL4XiRgPJyKwFLdX1T": "18OvOHZfVZl8uUGCL4XiRgPJyKwFLdX1T",
            "  ARQ1234567890  ": "ARQ1234567890",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada[:40]):
                drive = DriveFalso(_meta())
                _atualizar(drive, {"file_id": entrada})
                self.assertEqual(drive.get_kw["fileId"], esperado)
                self.assertEqual(drive.update_kw["fileId"], esperado)


class TestRegistroNoMcp(unittest.TestCase):
    NOME = "atualizar_arquivo_drive"

    def test_esta_habilitada_com_handler_e_schema(self):
        self.assertIn(self.NOME, registry.list_mcp_enabled_tools())
        self.assertTrue(hermes_tools.has_tool(self.NOME))
        params = registry.get_schema(self.NOME)["parameters"]
        self.assertEqual(set(params["required"]), {"file_id", "conteudo"})
        self.assertEqual(params["properties"]["tipo_conteudo"]["enum"], ["text/html", "text/markdown", "text/plain"])

    def test_anotacoes_dizem_que_grava_no_drive_do_dono_sem_mundo_aberto(self):
        anot = registry.mcp_annotations(self.NOME)
        self.assertIs(anot.get("readOnlyHint"), False)
        self.assertIs(anot.get("openWorldHint"), False)
        self.assertIs(anot.get("idempotentHint"), True)

    def test_valor_de_tipo_conteudo_fora_do_enum_e_rejeitado_no_preflight(self):
        self.assertEqual(registry.valores_invalidos(self.NOME, {"tipo_conteudo": "text/html"}), [])
        self.assertTrue(registry.valores_invalidos(self.NOME, {"tipo_conteudo": "application/pdf"}))

    def test_o_servidor_instrui_a_atualizar_em_vez_de_criar_de_novo(self):
        texto = mcp_server._handle_initialize({})["instructions"]
        self.assertIn("atualizar_arquivo_drive", texto)
        self.assertIn("NUNCA crie um arquivo novo", texto)

    def test_o_handler_do_catalogo_delega_para_o_modulo(self):
        with patch.object(drive_arquivos, "atualizar_conteudo", return_value={"status": "ok"}) as m:
            r = hermes_tools.execute(self.NOME, {"file_id": "x", "conteudo": "y"}, None)
        self.assertEqual(r, {"status": "ok"})
        m.assert_called_once()


if __name__ == "__main__":
    unittest.main()
