"""Imagens pela API da OpenAI: provedor (`llm_providers/openai_images.py`),
pipeline (`imagens_geradas.py`) e a prévia visível no `consultar_job` do MCP.

Nenhuma chamada real: cliente da OpenAI, Storage e Drive são falsos; o
Firestore é o de `video_fakes.py` (com Increment e merge de verdade).
"""
from __future__ import annotations

import base64
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

import imagens_geradas as ig
from llm_providers import openai_images as oi
from tools.tool_context import ToolContext
from video_fakes import FakeDb

import downloads_mcp


def _png(largura=64, altura=64, modo="RGB") -> bytes:
    saida = io.BytesIO()
    Image.new(modo, (largura, altura), (200, 30, 30, 255)[: len(modo)]).save(saida, "PNG")
    return saida.getvalue()


def _resp(imagens: list[bytes], *, revisado=None, texto=40, img_in=0, saida=1000):
    return SimpleNamespace(
        data=[SimpleNamespace(b64_json=base64.b64encode(d).decode(), revised_prompt=revisado) for d in imagens],
        usage=SimpleNamespace(
            input_tokens=texto + img_in,
            input_tokens_details=SimpleNamespace(text_tokens=texto, image_tokens=img_in),
            output_tokens=saida,
        ),
    )


class _ErroApi(Exception):
    def __init__(self, msg, status=None, body=None, nome=None):
        super().__init__(msg)
        self.status_code = status
        self.body = body
        if nome:
            self.__class__ = type(nome, (_ErroApi,), {})


class FakeBlob:
    def __init__(self, bucket, nome):
        self.bucket, self.name = bucket, nome

    def upload_from_string(self, dados, content_type=None):
        self.bucket.arquivos[self.name] = (dados, content_type)

    def download_as_bytes(self):
        return self.bucket.arquivos[self.name][0]


class FakeBucket:
    def __init__(self):
        self.arquivos = {}

    def blob(self, nome):
        return FakeBlob(self, nome)


class FakeDrive:
    def __init__(self, falhar=False):
        self.criados, self.falhar, self._n = [], falhar, 0

    def files(self):
        drive = self

        class _Files:
            def list(self, **_):
                return SimpleNamespace(execute=lambda: {"files": []})

            def create(self, body=None, media_body=None, fields=None):
                def _exec():
                    if drive.falhar and media_body is not None:
                        raise RuntimeError("drive fora")
                    drive._n += 1
                    fid = f"drive{drive._n}"
                    drive.criados.append((body, media_body is not None))
                    return {"id": fid, "webViewLink": f"https://drive.google.com/file/d/{fid}/view"}
                return SimpleNamespace(execute=_exec)
        return _Files()

    def permissions(self):
        return SimpleNamespace(create=lambda **_: SimpleNamespace(execute=lambda: {}))


class _Base(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.bucket = FakeBucket()
        self.drive = FakeDrive()
        self.client = MagicMock()
        patches = [
            patch.object(ig, "_bucket", lambda: self.bucket),
            patch.object(ig, "_url_publica", lambda blob: f"https://storage.test/{blob.name}"),
            patch.object(ig, "_drive_service", lambda: self.drive),
            patch.object(oi, "cliente", lambda db, **_: self.client),
            patch.dict("os.environ", {"HERMES_IMAGE_DAILY_USD_CAP": "2"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def ctx(self, canal="mcp"):
        return ToolContext(user_uid="dono", canal=canal, _db=self.db)

    def uso(self):
        return next((v for k, v in self.db.docs.items() if k.startswith("system_usage/imagens/daily/")), None)


class TestProvedor(unittest.TestCase):
    def test_tamanho_exato_na_geracao_25_e_fixo_nas_anteriores(self):
        self.assertEqual(oi.tamanho_para("16:9", "gpt-image-2.5-flare"), "1536x864")
        self.assertEqual(oi.tamanho_para("3:4", "gpt-image-2.5-sunburst"), "1056x1408")
        self.assertEqual(oi.tamanho_para("16:9", "gpt-image-2"), "1536x1024")
        for tam in ("1536x864", "864x1536", "1408x1056", "1056x1408"):
            largura, altura = (int(x) for x in tam.split("x"))
            self.assertEqual((largura % 16, altura % 16), (0, 0))

    def test_custo_pelas_tres_faixas_de_token(self):
        tokens = oi.tokens_de(_resp([b"x"], texto=100, img_in=500, saida=2000).usage)
        self.assertEqual(tokens, {"texto": 100, "imagem_entrada": 500, "imagem_saida": 2000})
        # 100*5 + 500*8 + 2000*30 = 64.500 por 1M
        self.assertAlmostEqual(oi.custo_usd("gpt-image-2.5-flare", tokens), 0.0645)
        self.assertAlmostEqual(oi.custo_usd("gpt-image-2", tokens), (500 + 2000 + 30000) / 1e6)
        self.assertAlmostEqual(oi.custo_usd("gpt-image-2.5-sunburst-2026-09-08", tokens), 0.0645)

    def test_gerar_decodifica_base64_e_repassa_parametros(self):
        client = MagicMock()
        client.images.generate.return_value = _resp([b"img1", b"img2"], revisado="rev")
        r = oi.gerar(client, modelo="gpt-image-2.5-flare", prompt="farol", tamanho="1536x864",
                     qualidade="low", fundo="transparent", formato="webp", n=2)
        self.assertEqual(r.imagens, [b"img1", b"img2"])
        self.assertEqual(r.prompts_revisados, ["rev", "rev"])
        kwargs = client.images.generate.call_args.kwargs
        self.assertEqual((kwargs["size"], kwargs["background"], kwargs["moderation"], kwargs["n"]),
                         ("1536x864", "transparent", "auto", 2))

    def test_429_tenta_mais_tres_vezes_com_espera_crescente(self):
        client = MagicMock()
        client.images.generate.side_effect = _ErroApi("Rate limit", status=429)
        esperas = []
        with self.assertRaises(oi.ErroImagem) as ctx:
            oi.gerar(client, modelo="m", prompt="p", tamanho="1024x1024", espera=esperas.append)
        self.assertEqual(ctx.exception.tipo, "limite")
        self.assertEqual(client.images.generate.call_count, 4)
        self.assertEqual(esperas, [5, 15, 30])

    def test_429_que_passa_na_segunda_tentativa(self):
        client = MagicMock()
        client.images.generate.side_effect = [_ErroApi("Rate limit", status=429), _resp([b"ok"])]
        r = oi.gerar(client, modelo="m", prompt="p", tamanho="1024x1024", espera=lambda s: None)
        self.assertEqual(r.imagens, [b"ok"])

    def test_classificacao_dos_erros(self):
        casos = [
            (_ErroApi("x", 429, {"error": {"code": "insufficient_quota"}}), "sem_credito"),
            (_ErroApi("Your organization must be verified to use the model", 403), "verificacao"),
            (_ErroApi("Your request was rejected by the safety system", 400,
                      {"error": {"code": "moderation_blocked"}}), "moderacao"),
            (_ErroApi("boom", 503), "indisponivel"),
            (_ErroApi("timed out", nome="APITimeoutError"), "timeout"),
            (_ErroApi("bad key", 401), "chave"),
        ]
        for exc, tipo in casos:
            with self.subTest(tipo=tipo):
                self.assertEqual(oi.classificar(exc).tipo, tipo)

    def test_moderacao_nao_tenta_de_novo(self):
        client = MagicMock()
        client.images.generate.side_effect = _ErroApi("rejected by the safety system", 400)
        with self.assertRaises(oi.ErroImagem):
            oi.gerar(client, modelo="m", prompt="p", tamanho="1024x1024", espera=lambda s: None)
        self.assertEqual(client.images.generate.call_count, 1)

    def test_ids_dos_modelos_vem_do_ambiente(self):
        with patch.dict("os.environ", {"OPENAI_IMAGE_MODEL_DEFAULT": "gpt-image-3-x",
                                       "OPENAI_IMAGE_MODEL_PREMIUM": "gpt-image-3-y"}):
            self.assertEqual(oi.id_do_modelo("flare"), "gpt-image-3-x")
            self.assertEqual(oi.id_do_modelo("sunburst"), "gpt-image-3-y")
        self.assertEqual(oi.id_do_modelo(None), "gpt-image-2.5-flare")


class TestGerarImagem(_Base):
    def test_mcp_16_9_devolve_arquivo_no_drive_link_de_download_e_previa(self):
        self.client.images.generate.return_value = _resp([_png(1536, 864)], revisado="um farol")
        texto = ig.executar(self.ctx(), {"prompt": "um farol ao entardecer", "proporcao": "16:9"}, modo="gerar")

        self.assertIsInstance(texto, str, "no MCP o resultado de consultar_job é string")
        r = json.loads(texto)
        self.assertEqual(self.client.images.generate.call_args.kwargs["size"], "1536x864")
        self.assertEqual(self.client.images.generate.call_args.kwargs["model"], "gpt-image-2.5-flare")
        img = r["imagens"][0]
        self.assertEqual(img["tamanho"], "1536x864")
        # Criadas: pasta "Imagens geradas", subpasta do mês e o arquivo.
        pasta_mes = self.drive.criados[1][0]
        self.assertEqual(self.drive.criados[0][0]["name"], "Imagens geradas")
        self.assertEqual(self.drive.criados[2], ({"name": img["nome"], "parents": ["drive2"]}, True))
        self.assertRegex(pasta_mes["name"], r"^\d{4}-\d{2}$")
        self.assertEqual(img["drive_file_id"], "drive3")
        # MCP: download pela origem do MCP (o Storage pode estar bloqueado no cliente).
        self.assertTrue(img["link_download"].startswith("https://gestao-hermes.firebaseapp.com/mcp/download/"))
        self.assertTrue(img["link_storage"].startswith("https://storage.test/imagens_geradas/"))
        self.assertIn(img["link_storage"], img["markdown"])
        token = img["link_download"].rsplit("/", 1)[-1]
        corpo, status, cab = downloads_mcp.servir(self.db, self.bucket, token)
        self.assertEqual((status, cab["Content-Type"]), (200, "image/png"))
        self.assertEqual(Image.open(io.BytesIO(corpo)).size, (1536, 864))
        self.assertEqual(img["prompt_revisado"], "um farol")
        self.assertIn(img["previa_path"], self.bucket.arquivos)
        previa = Image.open(io.BytesIO(self.bucket.arquivos[img["previa_path"]][0]))
        self.assertEqual((previa.format, max(previa.size)), ("JPEG", 1024))
        self.assertIn(f"imagens_geradas/{img['id']}", self.db.docs)
        # 40 texto * 5 + 1000 saída * 30 = 30.200 por 1M
        self.assertAlmostEqual(r["custo_estimado_usd"], 0.0302)

        uso = self.uso()
        self.assertEqual((uso["calls"], uso["imagens"]), (1, 1))
        self.assertAlmostEqual(uso["estimated_usd"], 0.0302)
        self.assertEqual(uso["features"]["gerar_imagem"]["imagens"], 1)
        self.assertEqual(uso["tokens"]["imagem_saida"], 1000)

    def test_chamada_antiga_so_com_prompt_no_copiloto_devolve_markdown(self):
        self.client.images.generate.return_value = _resp([_png()])
        texto = ig.executar(self.ctx(canal="web"), {"prompt": "um gato"}, modo="gerar")
        # A foto é a prévia JPEG (cabe no sendPhoto do Telegram); o original vai no link.
        self.assertRegex(texto, r"^!\[um gato\]\(https://storage\.test/imagens_geradas/.+_previa\.jpg\)")
        self.assertRegex(texto, r"\[original\]\(https://storage\.test/imagens_geradas/[^)]+\.png\)")
        kwargs = self.client.images.generate.call_args.kwargs
        self.assertEqual((kwargs["size"], kwargs["quality"]), ("1024x1024", "medium"))

    def test_com_task_id_anexa_na_acao_com_file_json_no_diario(self):
        self.db.docs["tarefas/t1"] = {"titulo": "Slides"}
        self.client.images.generate.return_value = _resp([_png()])
        r = json.loads(ig.executar(self.ctx(), {"prompt": "capa", "task_id": "t1"}, modo="gerar"))

        img = r["imagens"][0]
        self.assertEqual(img["task_id"], "t1")
        tarefa = self.db.docs["tarefas/t1"]
        itens = tarefa["pool_dados"].values
        self.assertEqual(itens[0]["id"], img["pool_item_id"])
        self.assertEqual(itens[0]["drive_file_id"], img["drive_file_id"])
        notas = [e["nota"] for e in tarefa["acompanhamento"].values]
        self.assertTrue(notas[0].startswith("FILE::JSON::"))
        self.assertEqual(json.loads(notas[0][len("FILE::JSON::"):])["v"], img["link_visualizacao"])

    def test_task_id_inexistente_recusa_antes_de_gastar(self):
        r = ig.executar(self.ctx(), {"prompt": "capa", "task_id": "nao-existe"}, modo="gerar")
        self.assertIn("não encontrada", r["erro"])
        self.client.images.generate.assert_not_called()

    def test_quantidade_3_gera_tres_arquivos_separados(self):
        self.client.images.generate.return_value = _resp([_png(), _png(), _png()], saida=3000)
        r = json.loads(ig.executar(self.ctx(), {"prompt": "icone de engrenagem", "quantidade": 3,
                                               "nome_arquivo": "icone"}, modo="gerar"))
        self.assertEqual(self.client.images.generate.call_args.kwargs["n"], 3)
        self.assertEqual([i["nome"] for i in r["imagens"]], ["icone-1.png", "icone-2.png", "icone-3.png"])
        self.assertEqual(len({i["drive_file_id"] for i in r["imagens"]}), 3)
        self.assertEqual(self.uso()["imagens"], 3)

    def test_teto_diario_bloqueia_com_mensagem_clara(self):
        self.db.docs[f"system_usage/imagens/daily/{ig._dia()}"] = {"estimated_usd": 1.99}
        r = ig.executar(self.ctx(), {"prompt": "x", "qualidade": "high"}, modo="gerar")
        self.assertIn("Teto diário de imagens atingido", r["erro"])
        self.assertIn("US$ 2.00", r["erro"])
        self.client.images.generate.assert_not_called()

    def test_teto_do_firestore_vence_a_env(self):
        self.db.docs["config/imagens"] = {"teto_diario_usd": 10}
        self.db.docs[f"system_usage/imagens/daily/{ig._dia()}"] = {"estimated_usd": 1.99}
        self.client.images.generate.return_value = _resp([_png()])
        r = json.loads(ig.executar(self.ctx(), {"prompt": "x"}, modo="gerar"))
        self.assertEqual(r["status"], "ok")

    def test_erros_da_api_viram_mensagem_sem_gasto_registrado(self):
        casos = {
            "verificacao": _ErroApi("organization must be verified", 403),
            "moderacao": _ErroApi("rejected by the safety system", 400),
            "limite": _ErroApi("Rate limit reached", 429),
        }
        for tipo, exc in casos.items():
            with self.subTest(tipo=tipo), patch("time.sleep"):
                self.client.images.generate.side_effect = exc
                r = ig.executar(self.ctx(), {"prompt": "x"}, modo="gerar")
                self.assertEqual(r["erro"], str(oi.ErroImagem(tipo)))
        self.assertIsNone(self.uso())

    def test_transparente_com_jpeg_e_recusado(self):
        r = ig.executar(self.ctx(), {"prompt": "logo", "fundo": "transparente", "formato": "jpeg"}, modo="gerar")
        self.assertIn("transparente", r["erro"])

    def test_openai_fora_do_ar_cai_para_o_google_com_aviso(self):
        self.client.images.generate.side_effect = _ErroApi("upstream", 503)
        parte = SimpleNamespace(inline_data=SimpleNamespace(data=_png()))
        genai = MagicMock()
        genai.models.generate_content.return_value = SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[parte]))])
        ctx = ToolContext(user_uid="dono", canal="mcp", _db=self.db, _genai_client=genai)

        r = json.loads(ig.executar(ctx, {"prompt": "x"}, modo="gerar"))
        self.assertEqual((r["provedor"], r["modelo"]), ("google", ig.MODELO_GOOGLE))
        self.assertTrue(any("plano B" in a for a in r["avisos"]))
        self.assertEqual(self.uso()["provedores"]["google"]["imagens"], 1)

    def test_timeout_nao_cai_para_o_google(self):
        # O pedido pode ainda sair (e ser cobrado) na OpenAI: pagar o Gemini por
        # cima seria cobrança dupla.
        self.client.images.generate.side_effect = _ErroApi("timed out", nome="APITimeoutError")
        genai = MagicMock()
        ctx = ToolContext(user_uid="dono", canal="mcp", _db=self.db, _genai_client=genai)
        r = ig.executar(ctx, {"prompt": "x"}, modo="gerar")
        self.assertEqual(r["erro"], str(oi.ErroImagem("timeout")))
        genai.models.generate_content.assert_not_called()

    def test_drive_fora_ainda_entrega_pelo_storage(self):
        self.drive.falhar = True
        self.client.images.generate.return_value = _resp([_png()])
        r = json.loads(ig.executar(self.ctx(), {"prompt": "x"}, modo="gerar"))
        img = r["imagens"][0]
        self.assertIsNone(img["drive_file_id"])
        self.assertTrue(img["link_download"])
        self.assertTrue(r["avisos"])


class TestEditarImagem(_Base):
    def test_referencias_e_mascara_vao_para_images_edit_no_sunburst(self):
        fontes = {"ref1": (_png(80, 80), "pessoas.png"), "ref2": (_png(), "logo.png"),
                  "masc": (_png(80, 80, "RGBA"), "mascara.png")}
        self.client.images.edit.return_value = _resp([_png()], img_in=1500)

        with patch("tools.anexar_arquivo._resolver_conteudo", lambda ctx, o: fontes[o["drive_file_id"]]):
            r = json.loads(ig.executar(self.ctx(), {
                "prompt": "mantenha as pessoas e troque o fundo",
                "imagens": [{"drive_file_id": "ref1"}, {"drive_file_id": "ref2"}],
                "mascara": {"drive_file_id": "masc"},
            }, modo="editar"))

        kwargs = self.client.images.edit.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-image-2.5-sunburst")
        self.assertEqual([nome for nome, _, _ in kwargs["image"]], ["pessoas.png", "logo.png"])
        nome_m, dados_m, mime_m = kwargs["mask"]
        self.assertEqual(mime_m, "image/png")
        self.assertEqual(Image.open(io.BytesIO(dados_m)).mode, "RGBA", "máscara precisa de canal alfa")
        self.assertEqual(r["tokens"]["imagem_entrada"], 1500)
        self.assertEqual(self.uso()["features"]["editar_imagem"]["calls"], 1)

    def test_mascara_sem_transparencia_e_recusada(self):
        fontes = {"ref": (_png(), "a.png"), "masc": (_png(64, 64, "L"), "mascara.png")}
        with patch("tools.anexar_arquivo._resolver_conteudo", lambda ctx, o: fontes[o["drive_file_id"]]):
            r = ig.executar(self.ctx(), {"prompt": "x", "imagens": [{"drive_file_id": "ref"}],
                                         "mascara": {"drive_file_id": "masc"}}, modo="editar")
        self.assertIn("transparência", r["erro"])
        self.client.images.edit.assert_not_called()

    def test_foto_girada_pelo_exif_segue_na_orientacao_certa(self):
        img = Image.new("RGB", (40, 20), (0, 0, 255))
        exif = img.getexif()
        exif[0x0112] = 6  # girar 90° na exibição
        saida = io.BytesIO()
        img.save(saida, "JPEG", exif=exif)
        nome, dados, mime = ig._como_imagem_de_entrada(saida.getvalue(), "foto.jpeg")
        self.assertEqual((nome, mime), ("foto.jpg", "image/jpeg"))
        self.assertEqual(Image.open(io.BytesIO(dados)).size, (20, 40))

    def test_upload_token_e_consumido_so_depois_do_sucesso(self):
        self.client.images.edit.return_value = _resp([_png()])
        with patch("tools.anexar_arquivo._resolver_conteudo", lambda ctx, o: (_png(), "a.png")), \
                patch("tools.anexar_arquivo.consumir_upload_token") as consumir:
            ig.executar(self.ctx(), {"prompt": "x", "imagens": [{"upload_token": "tok1"}]}, modo="editar")
        consumir.assert_called_once()
        self.assertEqual(consumir.call_args.args[1], "tok1")

    def test_sem_referencia_recusa(self):
        r = ig.executar(self.ctx(), {"prompt": "x", "imagens": []}, modo="editar")
        self.assertIn("imagens", r["erro"])
        self.client.images.edit.assert_not_called()

    def test_referencia_que_nao_e_imagem_recusa(self):
        with patch("tools.anexar_arquivo._resolver_conteudo", lambda ctx, o: (b"%PDF-1.4", "doc.pdf")):
            r = ig.executar(self.ctx(), {"prompt": "x", "imagens": [{"drive_file_id": "a"}]}, modo="editar")
        self.assertIn("não é uma imagem", r["erro"])


class TestPreviaNoMcp(_Base):
    def test_blocos_de_previa_so_do_prefixo_de_imagens(self):
        self.bucket.arquivos["imagens_geradas/2026-09/a_previa.jpg"] = (b"jpg-bytes", "image/jpeg")
        self.bucket.arquivos["outra/coisa.jpg"] = (b"segredo", "image/jpeg")
        texto = json.dumps({"imagens": [{"previa_path": "imagens_geradas/2026-09/a_previa.jpg"},
                                        {"previa_path": "outra/coisa.jpg"}]})
        blocos = ig.blocos_de_previa(texto)
        self.assertEqual(blocos, [{"type": "image", "mimeType": "image/jpeg",
                                   "data": base64.b64encode(b"jpg-bytes").decode()}])

    def test_blocos_de_previa_nunca_levanta(self):
        self.assertEqual(ig.blocos_de_previa("não é json"), [])
        self.assertEqual(ig.blocos_de_previa(json.dumps({"imagens": [{"previa_path": "imagens_geradas/x"}]})), [])

    def test_consultar_job_anexa_a_imagem_sem_mudar_o_texto(self):
        import mcp_server

        self.bucket.arquivos["imagens_geradas/2026-09/a_previa.jpg"] = (b"jpg", "image/jpeg")
        resultado = json.dumps({"status": "ok", "imagens": [{"previa_path": "imagens_geradas/2026-09/a_previa.jpg"}]})
        job = {"job_id": "mcpjob-1", "tool": "gerar_imagem", "status": "done", "resultado": resultado}
        ctx = ToolContext(user_uid="dono", canal="mcp", _db=MagicMock())

        with patch.object(mcp_server, "execute_tool", return_value=job), \
                patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), \
                patch.object(mcp_server, "_decisao_piso_mcp", return_value=None, create=True), \
                patch.object(mcp_server, "_audit_log"):
            resp = mcp_server._handle_tools_call({"name": "consultar_job", "arguments": {"job_id": "mcpjob-1"}},
                                                 ctx=ctx)

        self.assertFalse(resp["isError"])
        self.assertEqual(resp["content"][0]["type"], "text")
        self.assertEqual(json.loads(resp["content"][0]["text"])["resultado"], resultado)
        self.assertEqual(resp["content"][1], {"type": "image", "mimeType": "image/jpeg",
                                              "data": base64.b64encode(b"jpg").decode()})


class TestDownloadPelaOrigemDoMcp(unittest.TestCase):
    def setUp(self):
        self.db, self.bucket = FakeDb(), FakeBucket()
        self.bucket.arquivos["imagens_geradas/2026-09/a.png"] = (b"png-bytes", "image/png")

    def _token(self, **kw):
        url = downloads_mcp.criar_link(self.db, uid="dono", caminho="imagens_geradas/2026-09/a.png",
                                       nome=kw.get("nome", "capa.png"), mime="image/png", agora=kw.get("agora"))
        self.assertTrue(url.startswith("https://gestao-hermes.firebaseapp.com/mcp/download/"))
        return url.rsplit("/", 1)[-1]

    def test_token_valido_devolve_o_arquivo_sem_cache(self):
        corpo, status, cab = downloads_mcp.servir(self.db, self.bucket, self._token())
        self.assertEqual((corpo, status), (b"png-bytes", 200))
        self.assertIn('filename="capa.png"', cab["Content-Disposition"])
        self.assertIn("no-store", cab["Cache-Control"])

    def test_nome_com_acento_nao_quebra_o_cabecalho(self):
        _, _, cab = downloads_mcp.servir(self.db, self.bucket, self._token(nome="reunião.png"))
        cab["Content-Disposition"].encode("latin-1")
        self.assertIn("filename*=UTF-8''reuni%C3%A3o.png", cab["Content-Disposition"])

    def test_token_expirado_da_410_e_desconhecido_404(self):
        from datetime import datetime, timedelta, timezone

        velho = self._token(agora=datetime.now(timezone.utc) - timedelta(hours=25))
        self.assertEqual(downloads_mcp.servir(self.db, self.bucket, velho)[1], 410)
        self.assertEqual(downloads_mcp.servir(self.db, self.bucket, "nao-existe")[1], 404)
        self.assertEqual(downloads_mcp.servir(self.db, self.bucket, "")[1], 404)

    def test_caminho_fora_do_prefixo_nao_ganha_link_nem_e_servido(self):
        with self.assertRaises(ValueError):
            downloads_mcp.criar_link(self.db, uid="u", caminho="uploads/segredo.pdf", nome="x", mime="x")
        self.db.docs["downloads_mcp/forjado"] = {"caminho": "uploads/segredo.pdf", "expira_em": "9999"}
        self.assertEqual(downloads_mcp.servir(self.db, self.bucket, "forjado")[1], 404)


class TestVersaoDoServidor(unittest.TestCase):
    def test_versao_leva_impressao_do_catalogo(self):
        import mcp_server

        self.assertRegex(mcp_server.SERVER_VERSION, r"^0\.2\.0\+[0-9a-f]{8}$")


class TestRelatorio(unittest.TestCase):
    def test_linha_de_imagens_no_bloco_de_ia(self):
        from datetime import date

        import cost_report

        linhas = cost_report.format_ai_block(None, None, 5.0, date(2026, 9, 26),
                                             imagens={"estimated_usd": 0.42, "imagens": 7,
                                                      "provedores": {"google": {"imagens": 1}}})
        self.assertIn("  • Imagens: 7 imagens (1 pelo Google), US$ 0.42 (~R$ 2,10)", linhas)
        self.assertFalse(any("Imagens" in l for l in cost_report.format_ai_block(None, None, 5.0, date(2026, 9, 26))))


if __name__ == "__main__":
    unittest.main()
