"""Testes das ferramentas do Live Ideas no Gaspar (tools/liveideas_tools.py).

O canal (`liveideas.comando`) e o Firestore são falsos; o Drive também.
"""
import importlib.util
import json
import threading
import time
import unittest
import uuid
from unittest import mock

import imagens_geradas
import liveideas
from autonomy import policy
from tools import anexar_arquivo, hermes_tools, inventory, registry
from tools import liveideas_tools as lt
from tools.tool_context import ToolContext

DEZ = ("gerar", "consultar", "listar", "ler", "ajustar",
       "aplicar", "descartar", "desfazer", "renomear", "apagar")
PROC = "p_abcd1234_wxyz"
REUN = "2026-10-18_09-00-00"
LINK_P = f"https://liveideas.web.app/#/ler/p/{PROC}"


class Snap:
    def __init__(self, id_, dados):
        self.id, self._dados, self.exists = id_, dados, dados is not None

    def to_dict(self):
        return dict(self._dados) if self._dados is not None else None


class Ref:
    def __init__(self, db, col, id_):
        self.db, self.col, self.id = db, col, id_

    def get(self, transaction=None):
        return Snap(self.id, self.db.docs.get((self.col, self.id)))

    def set(self, dados):
        self.db.docs[(self.col, self.id)] = dict(dados)

    def update(self, dados):
        if (self.col, self.id) not in self.db.docs:
            raise LookupError("documento não existe")
        self.db.updates.append((self.col, self.id, dados))
        self.db.docs[(self.col, self.id)].update(dados)


class Colecao:
    def __init__(self, db, nome):
        self.db, self.nome = db, nome

    def document(self, id_=None):
        return Ref(self.db, self.nome, id_ or uuid.uuid4().hex[:20])


class Transacao:
    def update(self, ref, dados):
        ref.update(dados)


class Banco:
    def __init__(self):
        self.docs, self.updates = {}, []

    def collection(self, nome):
        return Colecao(self, nome)

    def transaction(self):
        return Transacao()

    def pedidos(self):
        return {i: d for (c, i), d in self.docs.items() if c == lt.COLECAO}


_TRAVA = threading.Lock()


def _transacional(fn):
    """Como o firestore.transactional: o corpo roda isolado das outras transações."""
    def rodar(tx, *a, **k):
        with _TRAVA:
            return fn(tx, *a, **k)
    return rodar


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Banco()
        self.db.docs[("tarefas", "t1")] = {"titulo": "Ação de teste"}
        self.ctx = ToolContext(user_uid="andre", _db=self.db)
        self.chamadas = []
        self.respostas = {}
        for p in (mock.patch.object(liveideas, "comando", self._comando),
                  mock.patch.object(liveideas, "banco_liveideas", lambda db: "raiz"),
                  mock.patch("firebase_admin.firestore.transactional", _transacional)):
            p.start()
            self.addCleanup(p.stop)

    def _comando(self, raiz, acao, corpo, espera_s=20):
        self.chamadas.append((acao, corpo))
        r = self.respostas[acao]
        if isinstance(r, Exception):
            raise r
        return r(corpo) if callable(r) else r

    def _pedido(self, **campos):
        dados = {"uid": "andre", "anexado": False, **campos}
        self.db.docs[(lt.COLECAO, "ped1")] = dados
        return "ped1"


class GerarTest(Base):
    def test_cria_o_pedido_so_depois_da_resposta(self):
        def resposta(corpo):
            self.assertEqual(self.db.pedidos(), {}, "o pedido não pode existir antes da resposta")
            return 200, {"ok": True, "tipo": "processo", "processo": PROC, "geracao": "g1"}
        self.respostas["gerar"] = resposta
        r = hermes_tools.execute("liveideas_gerar",
                                 {"tipo": "processo", "texto": "x" * 50, "titulo": "Diárias", "task_id": "t1"},
                                 self.ctx)
        self.assertEqual(self.chamadas, [("gerar", {"tipo": "processo", "texto": "x" * 50, "titulo": "Diárias"})])
        self.assertEqual((r["tipo"], r["estado"]), ("processo", "gerando"))
        self.assertIn("consulte com liveideas_consultar em uns 30 segundos", r["orientacao"])
        pedido = self.db.pedidos()[r["pedido_id"]]
        self.assertEqual({k: pedido[k] for k in ("uid", "tipo", "processo", "geracao", "task_id", "anexado")},
                         {"uid": "andre", "tipo": "processo", "processo": PROC, "geracao": "g1",
                          "task_id": "t1", "anexado": False})
        self.assertIn("criado", pedido)

    def test_mapa_de_reuniao_gravada_manda_reuniao(self):
        self.respostas["gerar"] = (200, {"ok": True, "tipo": "mapa", "reuniao": "2026-10-18_10-00-00"})
        r = hermes_tools.execute("liveideas_gerar", {"tipo": "mapa", "reuniao_id": REUN}, self.ctx)
        self.assertEqual(self.chamadas, [("gerar", {"tipo": "mapa", "reuniao": REUN})])
        self.assertEqual(self.db.pedidos()[r["pedido_id"]]["reuniao"], "2026-10-18_10-00-00")

    def test_notebook_indisponivel_devolve_a_mensagem_e_nao_cria_pedido(self):
        self.respostas["gerar"] = liveideas.LiveIdeasIndisponivel(liveideas.MSG_SEM_RESPOSTA)
        r = hermes_tools.execute("liveideas_gerar", {"tipo": "mapa", "texto": "y" * 50}, self.ctx)
        self.assertEqual(r, {"erro": liveideas.MSG_SEM_RESPOSTA})
        self.assertEqual(self.db.pedidos(), {})

    def test_recusa_do_notebook_devolve_o_erro_e_nao_cria_pedido(self):
        msg = "ha uma reuniao em andamento no notebook; peca de novo quando ela terminar"
        self.respostas["gerar"] = (409, {"erro": msg})
        r = hermes_tools.execute("liveideas_gerar", {"tipo": "fluxo", "texto": "z" * 50}, self.ctx)
        self.assertEqual(r, {"erro": msg})
        self.assertEqual(self.db.pedidos(), {})

    def test_task_id_com_barra_ou_vazio_e_recusado_antes_do_firestore(self):
        for task_id in ("t1/../x", "   ", ""):
            with self.subTest(task_id=task_id),                  mock.patch.object(self.db, "collection", side_effect=AssertionError("não pode ir ao Firestore")):
                r = lt.gerar(self.ctx, {"tipo": "mapa", "texto": "y" * 50, "task_id": task_id})
                self.assertEqual(r, {"erro": "task_id inválido: informe o id da ação do Gaspar, sem barra"})
        self.assertEqual(self.chamadas, [])

    def test_task_id_com_espacos_em_volta_vale_sem_eles(self):
        self.respostas["gerar"] = (200, {"ok": True, "tipo": "mapa", "reuniao": REUN})
        r = lt.gerar(self.ctx, {"tipo": "mapa", "texto": "y" * 50, "task_id": " t1 "})
        self.assertEqual(self.db.pedidos()[r["pedido_id"]]["task_id"], "t1")

    def test_task_id_inexistente_e_recusado_antes_do_comando(self):
        r = hermes_tools.execute("liveideas_gerar", {"tipo": "mapa", "texto": "y" * 50, "task_id": "nao"}, self.ctx)
        self.assertIn("erro", r)
        self.assertEqual(self.chamadas, [])


class ConsultarTest(Base):
    def setUp(self):
        super().setUp()
        self.publicados = []
        for p in (mock.patch.object(imagens_geradas, "_drive_service", return_value="servico"),
                  mock.patch.object(anexar_arquivo, "_pasta_de_anexos", return_value="pasta-anexos"),
                  mock.patch.object(imagens_geradas, "_publicar_drive", side_effect=self._publicar)):
            p.start()
            self.addCleanup(p.stop)

    def _publicar(self, service, pasta, nome, dados, mime):
        # Review Focus 2: o pedido já está marcado quando o anexo começa.
        self.assertTrue(self.db.docs[(lt.COLECAO, "ped1")]["anexado"])
        time.sleep(0.05)  # dá tempo de uma segunda consulta chegar no meio
        self.publicados.append((service, pasta, nome, dados, mime))
        return "drv1", "https://drive.google.com/file/d/drv1/view"

    def _pronto_processo(self):
        self.respostas["consultar"] = (200, {
            "estado": "pronto", "custo": 0.12, "texto": "Diárias: 3 etapas", "link": LINK_P,
            "titulo": "Diárias", "tipo": "processo", "bpmn": "<bpmn:definitions/>"})

    def _notas_tarefa(self):
        notas, itens = [], []
        for col, id_, dados in self.db.updates:
            if (col, id_) == ("tarefas", "t1"):
                notas += [e["nota"] for e in dados["acompanhamento"].values]
                if "pool_dados" in dados:
                    itens += dados["pool_dados"].values
        return notas, itens

    def test_de_outro_dono_e_negado(self):
        self._pedido(uid="outro", tipo="mapa", reuniao=REUN)
        r = hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertEqual(r, {"erro": "pedido não encontrado"})
        self.assertEqual(self.chamadas, [])

    def test_inexistente_e_negado(self):
        r = hermes_tools.execute("liveideas_consultar", {"pedido_id": "nada"}, self.ctx)
        self.assertEqual(r, {"erro": "pedido não encontrado"})

    def test_notebook_desligado_devolve_a_mensagem_e_o_pedido_segue_intacto(self):
        self._pedido(tipo="processo", processo=PROC, geracao="g1", task_id="t1")
        antes = dict(self.db.docs[(lt.COLECAO, "ped1")])
        self.respostas["consultar"] = liveideas.LiveIdeasIndisponivel(liveideas.MSG_DESLIGADO)
        r = hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertEqual(r, {"erro": "o notebook do Live Ideas está desligado (ligue-o e peça de novo)"})
        self.assertEqual(self.db.docs[(lt.COLECAO, "ped1")], antes)
        self.assertEqual(self.publicados, [])

    def test_gerando_devolve_estado_e_custo(self):
        self._pedido(tipo="processo", processo=PROC, geracao="g1", task_id="t1")
        self.respostas["consultar"] = (200, {"estado": "gerando", "custo": 0.01})
        r = hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertEqual(self.chamadas, [("consultar", {"tipo": "processo", "processo": PROC, "geracao": "g1"})])
        self.assertEqual((r["estado"], r["custo"]), ("gerando", 0.01))
        self.assertNotIn("anexo", r)
        self.assertFalse(self.db.docs[(lt.COLECAO, "ped1")]["anexado"])

    def test_falhou_traz_o_motivo_sem_virar_erro_da_ferramenta(self):
        self._pedido(tipo="mapa", reuniao=REUN)
        self.respostas["consultar"] = (200, {"estado": "falhou", "erro": "a geração parou", "custo": 0})
        r = hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertEqual((r["estado"], r["motivo"]), ("falhou", "a geração parou"))
        self.assertNotIn("erro", r)

    def test_processo_pronto_anexa_o_bpmn_e_anota_no_diario(self):
        self._pedido(tipo="processo", processo=PROC, geracao="g1", task_id="t1")
        self._pronto_processo()
        r = hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertEqual((r["estado"], r["texto"], r["link"], r["custo"]),
                         ("pronto", "Diárias: 3 etapas", LINK_P, 0.12))
        self.assertNotIn("bpmn", r)
        self.assertEqual(self.publicados, [("servico", "pasta-anexos", "Diárias.bpmn",
                                            b"<bpmn:definitions/>", "application/xml")])
        notas, itens = self._notas_tarefa()
        self.assertEqual([(i["nome"], i["drive_file_id"]) for i in itens], [("Diárias.bpmn", "drv1")])
        self.assertIn(f"Processo gerado no Live Ideas: Diárias, {LINK_P}", notas)
        self.assertTrue(any(n.startswith("FILE::JSON::") for n in notas))
        self.assertTrue(self.db.docs[(lt.COLECAO, "ped1")]["anexado"])

    def test_mapa_pronto_so_anota(self):
        self._pedido(tipo="mapa", reuniao=REUN, task_id="t1")
        link = f"https://liveideas.web.app/#/ler/r/{REUN}"
        self.respostas["consultar"] = (200, {"estado": "pronto", "custo": 0.3, "texto": "Resumo",
                                             "link": link, "titulo": "Planejamento", "tipo": "mapa"})
        hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        notas, itens = self._notas_tarefa()
        self.assertEqual(self.publicados, [])
        self.assertEqual(itens, [])
        self.assertEqual(notas, [f"Mapa de ideias gerado no Live Ideas: Planejamento, {link}"])

    def test_fluxo_pronto_so_anota(self):
        self._pedido(tipo="fluxo", reuniao=REUN, task_id="t1")
        link = f"https://liveideas.web.app/#/ler/r/{REUN}"
        self.respostas["consultar"] = (200, {"estado": "pronto", "custo": 0.3, "texto": "Fluxo",
                                             "link": link, "titulo": "Compras", "tipo": "fluxo"})
        hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertEqual(self._notas_tarefa(), ([f"Fluxo gerado no Live Ideas: Compras, {link}"], []))

    def test_sem_task_id_nao_anexa(self):
        self._pedido(tipo="processo", processo=PROC, geracao="g1")
        self._pronto_processo()
        r = hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertNotIn("anexo", r)
        self.assertEqual(self.publicados, [])

    def test_duas_consultas_seguidas_anexam_uma_vez_so(self):
        self._pedido(tipo="processo", processo=PROC, geracao="g1", task_id="t1")
        self._pronto_processo()
        hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertEqual(len(self.publicados), 1)
        self.assertEqual(len(self._notas_tarefa()[1]), 1)

    def test_duas_consultas_simultaneas_anexam_uma_vez_so(self):
        self._pedido(tipo="processo", processo=PROC, geracao="g1", task_id="t1")
        self._pronto_processo()
        ts = [threading.Thread(target=hermes_tools.execute,
                               args=("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(self.publicados), 1)
        self.assertEqual(len(self._notas_tarefa()[1]), 1)

    def test_processo_sem_bpmn_avisa_e_nao_tenta_de_novo(self):
        self._pedido(tipo="processo", processo=PROC, geracao="g1", task_id="t1")
        self.respostas["consultar"] = (200, {"estado": "pronto", "custo": 0.1, "texto": "t", "link": LINK_P,
                                             "titulo": "Diárias", "tipo": "processo"})
        r = hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertEqual(r["anexo"],
                         {"aviso": "o Live Ideas não devolveu o arquivo do processo; anexe pela tela"})
        self.assertTrue(self.db.docs[(lt.COLECAO, "ped1")]["anexado"])
        r = hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertEqual(r["anexo"], "já estava anexado na ação")
        self.assertEqual(self.publicados, [])
        self.assertEqual(self._notas_tarefa(), ([], []))

    def test_falha_no_anexo_desmarca_para_tentar_de_novo(self):
        self._pedido(tipo="processo", processo=PROC, geracao="g1", task_id="t1")
        self._pronto_processo()
        with mock.patch.object(imagens_geradas, "_publicar_drive", side_effect=RuntimeError("drive fora")):
            r = hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertIn("aviso", r["anexo"])
        self.assertFalse(self.db.docs[(lt.COLECAO, "ped1")]["anexado"])
        hermes_tools.execute("liveideas_consultar", {"pedido_id": "ped1"}, self.ctx)
        self.assertEqual(len(self.publicados), 1)


class AjusteTest(Base):
    def test_ajustar_cria_pedido_de_ajuste_e_consultar_devolve_as_propostas(self):
        self.respostas["ajustar"] = (200, {"ok": True, "ajuste": "aj_0123456789"})
        r = hermes_tools.execute("liveideas_ajustar", {"processo_id": PROC, "pedido": "junte as etapas 2 e 3"},
                                 self.ctx)
        self.assertEqual(self.chamadas, [("ajustar", {"processo": PROC, "pedido": "junte as etapas 2 e 3"})])
        self.assertEqual((r["tipo"], r["estado"]), ("ajuste", "gerando"))
        pedido = self.db.pedidos()[r["pedido_id"]]
        self.assertEqual({k: pedido[k] for k in ("uid", "tipo", "ajuste", "processo", "anexado")},
                         {"uid": "andre", "tipo": "ajuste", "ajuste": "aj_0123456789", "processo": PROC,
                          "anexado": False})

        self.respostas["consultar"] = (200, {"estado": "pronto", "resposta": "Juntei.", "custo": 0.02,
                                             "propostas": [{"id": "pr_abcdefghij", "resumo": "Juntei."}]})
        c = hermes_tools.execute("liveideas_consultar", {"pedido_id": r["pedido_id"]}, self.ctx)
        self.assertEqual(self.chamadas[-1], ("consultar", {"tipo": "ajuste", "ajuste": "aj_0123456789"}))
        self.assertEqual(c["propostas"], [{"id": "pr_abcdefghij", "resumo": "Juntei."}])
        self.assertEqual((c["estado"], c["resposta"], c["processo_id"]), ("pronto", "Juntei.", PROC))
        self.assertIn("liveideas_aplicar", c["orientacao"])

    def test_ajustar_com_erro_nao_cria_pedido(self):
        self.respostas["ajustar"] = (404, {"erro": "reuniao nao encontrada"})
        r = hermes_tools.execute("liveideas_ajustar", {"reuniao_id": REUN, "pedido": "x"}, self.ctx)
        self.assertEqual(r, {"erro": "reuniao nao encontrada"})
        self.assertEqual(self.db.pedidos(), {})


class RepasseTest(Base):
    def test_repassa_aplicar_descartar_desfazer_e_renomear(self):
        for acao in ("aplicar", "descartar", "desfazer", "renomear"):
            self.respostas[acao] = (200, {"ok": True, "texto": "novo", "link": LINK_P})
        for acao in ("aplicar", "descartar", "desfazer"):
            r = hermes_tools.execute(f"liveideas_{acao}", {"processo_id": PROC, "proposta_id": "pr_abcdefghij"},
                                     self.ctx)
            self.assertEqual(r, {"ok": True, "texto": "novo", "link": LINK_P})
        hermes_tools.execute("liveideas_renomear", {"reuniao_id": REUN, "titulo": "Novo nome"}, self.ctx)
        self.assertEqual(self.chamadas, [
            ("aplicar", {"processo": PROC, "proposta": "pr_abcdefghij"}),
            ("descartar", {"processo": PROC, "proposta": "pr_abcdefghij"}),
            ("desfazer", {"processo": PROC, "proposta": "pr_abcdefghij"}),
            ("renomear", {"reuniao": REUN, "titulo": "Novo nome"}),
        ])

    def test_listar_e_ler(self):
        self.respostas["listar"] = (200, {"itens": [{"tipo": "processo", "id": PROC, "titulo": "D", "data": "x"}]})
        self.respostas["ler"] = (200, {"texto": "t", "link": LINK_P, "titulo": "D", "tipo": "processo",
                                       "bpmn": "<x/>"})
        self.assertEqual(hermes_tools.execute("liveideas_listar", {"busca": "diarias"}, self.ctx)["itens"][0]["id"],
                         PROC)
        lido = hermes_tools.execute("liveideas_ler", {"processo_id": PROC}, self.ctx)
        self.assertEqual(lido, {"texto": "t", "link": LINK_P, "titulo": "D", "tipo": "processo"})
        self.assertEqual(self.chamadas, [("listar", {"busca": "diarias"}), ("ler", {"processo": PROC})])

    def test_apagar_repassa(self):
        self.respostas["apagar"] = (200, {"ok": True})
        self.assertEqual(hermes_tools.execute("liveideas_apagar", {"reuniao_id": REUN}, self.ctx), {"ok": True})
        self.assertEqual(self.chamadas, [("apagar", {"reuniao": REUN})])


class ApagarConfirmacaoTest(Base):
    def test_apagar_esta_no_piso_de_confirmacao(self):
        # O piso do canal MCP é este mesmo conjunto (test_policy confere a identidade).
        self.assertIn("liveideas_apagar", policy.FLOOR_CONFIRMACAO_OBRIGATORIA)
        for nome in DEZ:
            if nome != "apagar":
                self.assertNotIn(f"liveideas_{nome}", policy.FLOOR_CONFIRMACAO_OBRIGATORIA)

    def test_previa_mostra_titulo_e_data_e_nao_apaga(self):
        self.respostas["listar"] = (200, {"itens": [
            {"tipo": "mapa", "id": "2026-10-17_09-00-00", "titulo": "Outra", "data": "2026-10-17T12:00:00.000Z"},
            {"tipo": "mapa", "id": REUN, "titulo": "Reunião de equipe", "data": "2026-10-18T12:00:00.000Z"}]})
        previa = hermes_tools.preview("liveideas_apagar", self.ctx, {"reuniao_id": REUN})
        self.assertEqual(previa["resumo"], "vai para a lixeira: Reunião de equipe, 18/10/2026")
        self.assertEqual(self.chamadas, [("listar", {})])

    def test_previa_de_processo_filtra_por_tipo(self):
        self.respostas["listar"] = (200, {"itens": [
            {"tipo": "processo", "id": PROC, "titulo": "Diárias", "data": "2026-10-16T15:30:00+00:00"}]})
        previa = hermes_tools.preview("liveideas_apagar", self.ctx, {"processo_id": PROC})
        self.assertEqual(previa["resumo"], "vai para a lixeira: Diárias, 16/10/2026")
        self.assertEqual(self.chamadas, [("listar", {"tipo": "processo"})])

    def test_previa_fora_da_lista_usa_o_titulo_do_ler_sem_data(self):
        self.respostas["listar"] = (200, {"itens": []})
        self.respostas["ler"] = (200, {"texto": "t", "link": "l", "titulo": "Antiga", "tipo": "mapa"})
        previa = hermes_tools.preview("liveideas_apagar", self.ctx, {"reuniao_id": REUN})
        self.assertEqual(previa["resumo"], "vai para a lixeira: Antiga")
        self.assertEqual(self.chamadas, [("listar", {}), ("ler", {"reuniao": REUN})])

    def test_previa_sem_o_titulo_usa_o_id(self):
        self.respostas["listar"] = self.respostas["ler"] = liveideas.LiveIdeasIndisponivel(liveideas.MSG_DESLIGADO)
        previa = hermes_tools.preview("liveideas_apagar", self.ctx, {"processo_id": PROC})
        self.assertEqual(previa["resumo"], f"vai para a lixeira: {PROC}")
        # o listar já esgotou o prazo: o ler não é tentado (a prévia não passa de um prazo de 20 s)
        self.assertEqual(self.chamadas, [("listar", {"tipo": "processo"})])

    @unittest.skipUnless(importlib.util.find_spec("firebase_functions"), "mcp_server precisa de firebase_functions")
    def test_pelo_mcp_a_primeira_chamada_so_devolve_a_previa(self):
        import mcp_server
        from autonomy.contracts import EstadoAutonomia

        self.respostas["listar"] = (200, {"itens": [
            {"tipo": "mapa", "id": REUN, "titulo": "Reunião de equipe", "data": "2026-10-18T12:00:00.000Z"}]})
        self.respostas["apagar"] = AssertionError("apagar não pode ir ao canal sem confirmar_acao")
        with mock.patch.object(mcp_server.autonomy_policy, "estado_autonomia_atual",
                               return_value=EstadoAutonomia.ATIVO),                 mock.patch.object(mcp_server.autonomy_policy, "registrar_decisao"),                 mock.patch.object(mcp_server, "_access_config", return_value={"confirm_tools": set()}):
            ctx = ToolContext(user_uid="andre", canal="mcp", _db=self.db)
            resultado = mcp_server._handle_tools_call(
                {"name": "liveideas_apagar", "arguments": {"reuniao_id": REUN}}, ctx=ctx)
            # Insistir com _confirmed sem confirmation_id também não apaga.
            atalho = mcp_server._handle_tools_call(
                {"name": "liveideas_apagar", "arguments": {"reuniao_id": REUN, "_confirmed": True}}, ctx=ctx)
        corpo = json.loads(resultado["content"][0]["text"])
        self.assertFalse(resultado["isError"])
        self.assertTrue(corpo["confirmation_id"])
        self.assertEqual(corpo["preview"]["resumo"], "vai para a lixeira: Reunião de equipe, 18/10/2026")
        self.assertTrue(atalho["isError"])
        self.assertNotIn("apagar", [acao for acao, _ in self.chamadas])
        guardada = self.db.docs[("mcp_confirmations", corpo["confirmation_id"])]
        self.assertEqual((guardada["tool"], guardada["arguments"]), ("liveideas_apagar", {"reuniao_id": REUN}))


class CatalogoTest(unittest.TestCase):
    def test_as_dez_no_catalogo_inventario_schema_e_handlers(self):
        habilitadas = registry.list_mcp_enabled_tools()
        for nome in DEZ:
            tool = f"liveideas_{nome}"
            self.assertIn(tool, registry._CATALOG)
            self.assertIsNotNone(inventory.get_inventory_entry(tool), tool)
            self.assertEqual(registry.get_schema(tool)["name"], tool)
            self.assertTrue(hermes_tools.has_tool(tool), tool)
            self.assertIn(tool, habilitadas)
        self.assertTrue(registry.needs_confirmation("liveideas_apagar"))


if __name__ == "__main__":
    unittest.main()
