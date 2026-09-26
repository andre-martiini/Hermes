"""Hermes Vídeo — roteiro, criação do projeto, máquina de estados e status."""
import unittest
from datetime import datetime, timedelta, timezone

from video import projeto as vp
from video import veo_provider as vv
from video_fakes import FakeDb


def roteiro(**extra):
    base = {
        "titulo": "RSC para servidores",
        "formato": "9:16",
        "biblia": {"estilo": "flat 2D, azul-petróleo e laranja", "personagens": ["servidora de óculos"]},
        "cenas": [
            {"narracao": "O RSC reconhece o que você já sabe fazer.", "descricao_visual": "servidora lendo"},
            # 11 palavras ≈ 4,4 s de fala → clipe de 6 s
            {"narracao": "Veja agora como pedir o reconhecimento em três passos bem simples.",
             "descricao_visual": "tela do sistema"},
            {"narracao": "", "descricao_visual": "logotipo do Ifes"},
        ],
    }
    base.update(extra)
    return base


class TestValidarRoteiro(unittest.TestCase):
    def test_roteiro_valido_normaliza_e_calcula_duracoes(self):
        r, erros, avisos = vp.validar_roteiro(roteiro())
        self.assertEqual(erros, [])
        self.assertEqual(r["formato"], "9:16")
        self.assertEqual(r["modo"], "padrao")
        self.assertEqual(r["modelo_video"], "veo-3.1-lite-generate-001")
        self.assertEqual(r["voz"]["nome"], "Kore")
        self.assertEqual([c["duracao_s"] for c in r["cenas"]], [4, 6, 4])
        self.assertTrue(any("mínimo" in a for a in avisos))

    def test_campos_obrigatorios(self):
        r, erros, _ = vp.validar_roteiro({"cenas": [{"narracao": "oi"}]})
        self.assertIsNone(r)
        self.assertTrue(any("titulo" in e for e in erros))
        self.assertTrue(any("biblia.estilo" in e for e in erros))
        self.assertTrue(any("descricao_visual" in e for e in erros))

    def test_narracao_que_nao_cabe_em_8s_pede_divisao(self):
        longa = " ".join(["palavra"] * 25)  # ~10 s
        r, erros, _ = vp.validar_roteiro(roteiro(cenas=[{"narracao": longa, "descricao_visual": "x"}]))
        self.assertIsNone(r)
        self.assertTrue(any("divida em duas cenas" in e for e in erros))

    def test_formato_e_modo_invalidos(self):
        _, erros, _ = vp.validar_roteiro(roteiro(formato="4:3", modo="turbo"))
        self.assertEqual(len([e for e in erros if "formato" in e or "modo" in e]), 2)

    def test_duracao_total_acima_do_limite_da_v1(self):
        cenas = [{"narracao": " ".join(["p"] * 18), "descricao_visual": "x"}] * 16  # 16 × 8 s = 128 s
        _, erros, _ = vp.validar_roteiro(roteiro(cenas=cenas))
        self.assertTrue(any("120 s" in e for e in erros))


class TestCriarProjeto(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()

    def test_cria_projeto_e_cenas_num_batch_com_estimativa(self):
        res = vp.criar_projeto(self.db, "uid-andre", roteiro(acao_id="acao-1"))
        self.assertEqual(res["status"], "ok")
        pid = res["projeto_id"]
        doc = self.db.docs[f"video_projetos/{pid}"]
        self.assertEqual(doc["status"], vp.ROTEIRO)
        self.assertEqual(doc["uid"], "uid-andre")
        self.assertEqual(doc["acao_id"], "acao-1")
        self.assertEqual(doc["custo_real_usd"], 0.0)
        self.assertEqual(doc["orcamento_usd"], res["estimativa"]["teto_projeto_usd"])
        self.assertEqual(sorted(k for k in self.db.docs if "/cenas/" in k),
                         [f"video_projetos/{pid}/cenas/0{i}" for i in (1, 2, 3)])
        self.assertEqual(res["estimativa"]["segundos_video"], 14)

    def test_roteiro_invalido_nao_grava_nada(self):
        res = vp.criar_projeto(self.db, "uid", {"titulo": "x"})
        self.assertEqual(res["status"], "invalido")
        self.assertEqual(self.db.docs, {})

    def test_precos_de_config_entram_na_estimativa(self):
        self.db.docs["config/video_precos"] = {"margem_retrabalho": 1.0, "tts_por_cena": 0.0, "imagem": 0.0}
        res = vp.criar_projeto(self.db, "uid", roteiro())
        self.assertEqual(res["estimativa"]["custo_estimado_usd"], 0.7)  # 14 s × 0,05


class TestMaquinaDeEstados(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.pid = vp.criar_projeto(self.db, "uid", roteiro())["projeto_id"]

    def estado(self):
        return self.db.docs[f"video_projetos/{self.pid}"]["status"]

    def test_caminho_feliz_ate_concluido_e_reabertura(self):
        for para in (vp.PREVIA_GERANDO, vp.AGUARDANDO_STORYBOARD, vp.PREVIA_GERANDO, vp.AGUARDANDO_STORYBOARD,
                     vp.RENDERIZANDO, vp.MONTANDO, vp.CONCLUIDO, vp.RENDERIZANDO):
            vp.transicionar(self.db, self.pid, para)
            self.assertEqual(self.estado(), para)

    def test_pular_etapa_e_recusado_sem_escrever(self):
        escritas = self.db.escritas
        with self.assertRaises(vp.TransicaoInvalida):
            vp.transicionar(self.db, self.pid, vp.RENDERIZANDO)
        self.assertEqual(self.estado(), vp.ROTEIRO)
        self.assertEqual(self.db.escritas, escritas)

    def test_erro_e_cancelado_de_qualquer_estado_nao_final(self):
        vp.transicionar(self.db, self.pid, vp.ERRO, campos={"erro": "cota"})
        self.assertEqual(self.db.docs[f"video_projetos/{self.pid}"]["erro"], "cota")
        vp.transicionar(self.db, self.pid, vp.RENDERIZANDO)  # retomada depois da falha
        vp.transicionar(self.db, self.pid, vp.CANCELADO)
        with self.assertRaises(vp.TransicaoInvalida):
            vp.transicionar(self.db, self.pid, vp.ERRO)
        with self.assertRaises(vp.TransicaoInvalida):
            vp.transicionar(self.db, self.pid, vp.PREVIA_GERANDO)

    def test_origem_restrita_pelo_chamador(self):
        with self.assertRaises(vp.TransicaoInvalida):
            vp.transicionar(self.db, self.pid, vp.PREVIA_GERANDO, de={vp.AGUARDANDO_STORYBOARD})

    def test_projeto_inexistente(self):
        with self.assertRaises(vp.ProjetoNaoEncontrado):
            vp.transicionar(self.db, "nao-existe", vp.PREVIA_GERANDO)

    def test_sem_transacao_recusa(self):
        class SemTx:
            def collection(self, nome):
                return FakeDb().collection(nome)
        with self.assertRaises(vp.SemSuporteTransacao):
            vp.transicionar(SemTx(), self.pid, vp.PREVIA_GERANDO)


class TestExecucaoUnica(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.pid = vp.criar_projeto(self.db, "uid", roteiro())["projeto_id"]
        self.t0 = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)

    def test_dois_workers_no_mesmo_projeto_so_um_reivindica(self):
        self.assertTrue(vp.reivindicar_execucao(self.db, self.pid, "exec-a", agora=self.t0))
        self.assertFalse(vp.reivindicar_execucao(self.db, self.pid, "exec-b", agora=self.t0 + timedelta(minutes=1)))

    def test_a_propria_execucao_retoma(self):
        vp.reivindicar_execucao(self.db, self.pid, "exec-a", agora=self.t0)
        self.assertTrue(vp.reivindicar_execucao(self.db, self.pid, "exec-a", agora=self.t0 + timedelta(minutes=5)))

    def test_lease_vencido_libera_para_outra_execucao(self):
        vp.reivindicar_execucao(self.db, self.pid, "exec-a", agora=self.t0)
        self.assertTrue(vp.reivindicar_execucao(self.db, self.pid, "exec-b", agora=self.t0 + timedelta(minutes=16)))

    def test_liberar_so_a_propria_execucao(self):
        vp.reivindicar_execucao(self.db, self.pid, "exec-a", agora=self.t0)
        self.assertFalse(vp.liberar_execucao(self.db, self.pid, "exec-b"))
        self.assertTrue(vp.liberar_execucao(self.db, self.pid, "exec-a"))
        self.assertTrue(vp.reivindicar_execucao(self.db, self.pid, "exec-b", agora=self.t0))


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.pid = vp.criar_projeto(self.db, "uid-andre", roteiro())["projeto_id"]

    def test_status_resume_cenas_clipes_e_custos(self):
        base = f"video_projetos/{self.pid}/clipes"
        self.db.docs[f"{base}/01_v1"] = {"status": "done"}
        self.db.docs[f"{base}/02_v1"] = {"status": "submetido"}
        st = vp.obter_status(self.db, self.pid, "uid-andre")
        self.assertEqual(st["status"], "ok")
        self.assertEqual(st["estado"], vp.ROTEIRO)
        self.assertEqual([c["ordem"] for c in st["cenas"]], [1, 2, 3])
        self.assertEqual(st["clipes"], {"total": 2, "por_status": {"done": 1, "submetido": 1}})
        self.assertNotIn("erro", st)

    def test_projeto_de_outro_usuario_parece_inexistente(self):
        self.assertEqual(vp.obter_status(self.db, self.pid, "outro-uid")["status"], "nao_encontrado")
        self.assertEqual(vp.obter_status(self.db, "nao-existe", "uid-andre")["status"], "nao_encontrado")


class TestPeloCanalMcp(unittest.TestCase):
    """Critério de pronto da Fase 1: criar um projeto pelo Claude e ver a estimativa."""

    def setUp(self):
        from unittest import mock

        import mcp_server
        from tools.tool_context import ToolContext

        self.mcp = mcp_server
        self.db = FakeDb()
        self.ctx = ToolContext(user_uid="uid-andre", _db=self.db)
        p = mock.patch.object(mcp_server, "_access_config", return_value={"confirm_tools": set()})
        p.start()
        self.addCleanup(p.stop)

    def chamar(self, nome, args):
        import json

        res = self.mcp._handle_tools_call({"name": nome, "arguments": args}, ctx=self.ctx)
        return res, json.loads(res["content"][0]["text"])

    def test_criar_e_consultar_pelo_tools_call(self):
        res, corpo = self.chamar("video_criar_projeto", roteiro())
        self.assertFalse(res.get("isError"), corpo)
        self.assertEqual(corpo["estimativa"]["segundos_video"], 14)
        res, st = self.chamar("video_status", {"projeto_id": corpo["projeto_id"]})
        self.assertFalse(res.get("isError"), st)
        self.assertEqual(st["estado"], "roteiro")
        self.assertEqual(self.db.docs[f"video_projetos/{corpo['projeto_id']}"]["uid"], "uid-andre")

    def test_criar_nao_passa_pelo_gate_de_confirmacao(self):
        self.assertFalse(self.mcp._exige_confirmacao("video_criar_projeto"))

    def test_catalogo_publica_as_duas_com_annotations(self):
        from tools import registry

        tools = {t["name"]: t for t in self.mcp._handle_tools_list()["tools"]}
        self.assertTrue(tools["video_status"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["video_criar_projeto"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["video_criar_projeto"]["annotations"]["idempotentHint"])
        self.assertFalse(registry.is_voice_enabled("video_criar_projeto"))
        self.assertTrue(registry.is_voice_enabled("video_status"))


class TestFakeVeoProvider(unittest.TestCase):
    def test_conta_pedidos_conclui_e_simula_bloqueio(self):
        p = vv.FakeVeoProvider(bloquear_prompts={"marca"}, consultas_ate_concluir=2)
        ok = p.gerar_clipe(vv.PedidoClipe("veo", "cena calma", b"png", 4))
        bloq = p.gerar_clipe(vv.PedidoClipe("veo", "logo da marca", b"png", 6))
        self.assertFalse(p.consultar_operacao(ok).concluida)
        r = p.consultar_operacao(ok)
        self.assertTrue(r.concluida)
        self.assertTrue(p.baixar(r).startswith(b"mp4:"))
        p.consultar_operacao(bloq)
        self.assertTrue(p.consultar_operacao(bloq).bloqueado)
        self.assertEqual(len(p.pedidos), 2)


class TestVertexVeoProvider(unittest.TestCase):
    """Monta o pedido do SDK sem rede: confere que áudio sai desligado e o quadro final vai junto."""

    def test_pedido_leva_last_frame_e_audio_desligado(self):
        from unittest import mock
        cli = mock.Mock()
        cli.models.generate_videos.return_value = mock.Mock(name="op")
        cli.models.generate_videos.return_value.name = "operations/123"
        p = vv.VertexVeoProvider(cliente=cli)
        nome = p.gerar_clipe(vv.PedidoClipe("veo-3.1-lite-generate-001", "prompt", b"ini", 6,
                                            aspecto="9:16", imagem_fim=b"fim"))
        self.assertEqual(nome, "operations/123")
        kwargs = cli.models.generate_videos.call_args.kwargs
        cfg = kwargs["config"]
        self.assertFalse(cfg.generate_audio)
        self.assertEqual(cfg.duration_seconds, 6)
        self.assertEqual(cfg.aspect_ratio, "9:16")
        self.assertEqual(cfg.last_frame.image_bytes, b"fim")
        self.assertEqual(kwargs["source"].image.image_bytes, b"ini")


if __name__ == "__main__":
    unittest.main()
