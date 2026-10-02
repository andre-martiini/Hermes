"""Testes de functions/agent_runs.py.

Cobre:
- montar_registro (campos obrigatórios, status, erro condicional e campos opcionais
  do plano "confirmação verificada": origem, estado_verificado, aguarda_usuario,
  reversivel, acoes_afetadas, evidencias)
- registrar (timestamps, expira_em de 90 dias, idempotência por run_id)
- listar_recentes (filtros no Firestore, ordem decrescente, teto de 50, nove
  campos publicados no MCP)
- registrar_execucao (registra sucesso e erro; erro propaga; falha ao registrar
  não derruba a rotina)
"""

from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest import mock

import agent_runs as runs_mod


class _MockDocSnap:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRef:
    def __init__(self, col, doc_id: str):
        self.col = col
        self.id = doc_id

    def get(self):
        data = self.col._docs.get(self.id)
        return _MockDocSnap(self.id, data)

    def set(self, data):
        self.col._docs[self.id] = dict(data)


def _valor(v):
    return v if v is not runs_mod.firestore.SERVER_TIMESTAMP else datetime.now(timezone.utc)


class _MockQuery:
    def __init__(self, col, items, ordem=None, teto=None):
        self.col = col
        self.items = items
        self._ordem = ordem
        self._teto = teto

    def where(self, field, op, val):
        if op == "==":
            filtered = [(k, v) for k, v in self.items if v.get(field) == val]
        elif op == ">=":
            filtered = [(k, v) for k, v in self.items if v.get(field) is not None and _valor(v.get(field)) >= val]
        else:
            raise AssertionError(f"operador não suportado no mock: {op}")
        return _MockQuery(self.col, filtered, self._ordem, self._teto)

    def order_by(self, field, direction=None):
        return _MockQuery(self.col, self.items, (field, direction), self._teto)

    def limit(self, n):
        return _MockQuery(self.col, self.items, self._ordem, n)

    def stream(self):
        items = list(self.items)
        if self._ordem:
            campo, direcao = self._ordem
            items.sort(key=lambda kv: _valor(kv[1].get(campo)) or datetime.min.replace(tzinfo=timezone.utc),
                       reverse=direcao == runs_mod.firestore.Query.DESCENDING)
        if self._teto is not None:
            items = items[: self._teto]
        return [_MockDocSnap(k, v) for k, v in items]


class _MockCollection:
    def __init__(self, db, name: str):
        self.db = db
        self.name = name
        self._docs: dict[str, dict] = {}
        self._counter = 1

    def document(self, doc_id: str):
        return _MockDocRef(self, doc_id)

    def add(self, data):
        doc_id = f"run_{self._counter}"
        self._counter += 1
        self._docs[doc_id] = dict(data)
        return (datetime.now(timezone.utc), _MockDocRef(self, doc_id))

    def _q(self):
        return _MockQuery(self, list(self._docs.items()))

    def where(self, field, op, val):
        return self._q().where(field, op, val)

    def order_by(self, field, direction=None):
        return self._q().order_by(field, direction)

    def stream(self):
        return self._q().stream()


class _MockDB:
    def __init__(self):
        self._collections: dict[str, _MockCollection] = {}

    def collection(self, name: str) -> _MockCollection:
        if name not in self._collections:
            self._collections[name] = _MockCollection(self, name)
        return self._collections[name]


class TestMontarRegistro(unittest.TestCase):
    def test_registro_valido_sucesso(self):
        reg = runs_mod.montar_registro(
            rotina="briefing_matinal",
            resumo="Briefing matinal executado, 3 decisões geradas.",
            contadores={"itens_lidos": 5, "decisoes": 3},
        )
        self.assertEqual(reg["rotina"], "briefing_matinal")
        self.assertEqual(reg["resumo"], "Briefing matinal executado, 3 decisões geradas.")
        self.assertEqual(reg["status"], "sucesso")
        self.assertEqual(reg["contadores"]["decisoes"], 3)
        self.assertIsNone(reg["erro"])

    def test_sem_campos_novos_o_registro_e_o_mesmo_de_antes(self):
        reg = runs_mod.montar_registro(rotina="r", resumo="ok")
        self.assertEqual(set(reg), {"rotina", "resumo", "status", "contadores", "erro", "iniciado_em",
                                    "finalizado_em"})

    def test_registro_valido_erro(self):
        reg = runs_mod.montar_registro(
            rotina="varredura_followups",
            resumo="Falha na leitura do outbox.",
            status="erro",
            erro="Timeout de conexão Firestore",
        )
        self.assertEqual(reg["status"], "erro")
        self.assertEqual(reg["erro"], "Timeout de conexão Firestore")

    def test_registro_valido_parcial(self):
        reg = runs_mod.montar_registro(
            rotina="executor_agent_requests",
            resumo="Processou 2 de 3 pedidos com sucesso.",
            status="parcial",
            contadores={"sucesso": 2, "erro": 1},
        )
        self.assertEqual(reg["status"], "parcial")

    def test_rotina_obrigatoria(self):
        self.assertIn("erro", runs_mod.montar_registro(rotina="", resumo="Algo"))
        self.assertIn("erro", runs_mod.montar_registro(rotina=None, resumo="Algo"))

    def test_resumo_obrigatorio(self):
        self.assertIn("erro", runs_mod.montar_registro(rotina="teste", resumo=""))
        self.assertIn("erro", runs_mod.montar_registro(rotina="teste", resumo=None))

    def test_status_invalido(self):
        self.assertIn("erro", runs_mod.montar_registro(rotina="teste", resumo="algo", status="invalido"))

    def test_erro_obrigatorio_quando_status_erro(self):
        res = runs_mod.montar_registro(rotina="teste", resumo="falhou", status="erro")
        self.assertIn("obrigatório quando status é 'erro'", res["erro"])

    def test_contadores_deve_ser_dict(self):
        self.assertIn("erro", runs_mod.montar_registro(rotina="teste", resumo="algo", contadores="invalido"))

    def test_campos_novos(self):
        reg = runs_mod.montar_registro(
            rotina="fila_whatsapp", resumo="1 WhatsApp na fila", origem="Autonoma", estado_verificado="pendente",
            acoes_afetadas=["a1", "a1", "a2"], aguarda_usuario=True, motivo_espera="aprovar o texto",
            reversivel=True, como_desfazer="cancelar_envio_whatsapp(j1) enquanto pending", evidencias=["drive:x"])
        self.assertEqual(reg["origem"], "autonoma")
        self.assertEqual(reg["estado_verificado"], "pendente")
        self.assertEqual(reg["acoes_afetadas"], ["a1", "a2"])
        self.assertTrue(reg["aguarda_usuario"])
        self.assertEqual(reg["motivo_espera"], "aprovar o texto")
        self.assertEqual(reg["como_desfazer"], "cancelar_envio_whatsapp(j1) enquanto pending")
        self.assertEqual(reg["evidencias"], ["drive:x"])

    def test_campos_novos_invalidos_sao_recusados(self):
        self.assertIn("origem", runs_mod.montar_registro(rotina="r", resumo="x", origem="email")["erro"])
        self.assertIn("estado_verificado",
                      runs_mod.montar_registro(rotina="r", resumo="x", estado_verificado="enviado")["erro"])
        self.assertIn("como_desfazer", runs_mod.montar_registro(rotina="r", resumo="x", reversivel=True)["erro"])

    def test_resumo_vira_uma_linha_curta(self):
        reg = runs_mod.montar_registro(rotina="r", resumo="linha 1\nlinha 2\n\n" + "x" * 500)
        self.assertNotIn("\n", reg["resumo"])
        self.assertLessEqual(len(reg["resumo"]), runs_mod.RESUMO_MAX)
        self.assertTrue(reg["resumo"].startswith("linha 1 linha 2"))


class TestRegistrar(unittest.TestCase):
    def setUp(self):
        self.db = _MockDB()

    def test_registrar_com_sucesso(self):
        res = runs_mod.registrar(
            self.db,
            rotina="briefing_matinal",
            resumo="Executou sem problemas.",
            contadores={"acoes_vistas": 10},
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["run_id"], "run_1")

        d = self.db.collection(runs_mod.COLLECTION).document("run_1").get().to_dict()
        self.assertEqual(d["rotina"], "briefing_matinal")
        self.assertEqual(d["status"], "sucesso")
        self.assertEqual(d["contadores"]["acoes_vistas"], 10)

    def test_expira_em_noventa_dias(self):
        runs_mod.registrar(self.db, rotina="r", resumo="ok")
        d = self.db.collection(runs_mod.COLLECTION).document("run_1").get().to_dict()
        restante = d["expira_em"] - datetime.now(timezone.utc)
        self.assertTrue(timedelta(days=89) < restante <= timedelta(days=90))

    def test_mesmo_run_id_nao_duplica(self):
        runs_mod.registrar(self.db, run_id="briefing:2026-10-01", rotina="briefing", resumo="1ª")
        res = runs_mod.registrar(self.db, run_id="briefing:2026-10-01", rotina="briefing", resumo="2ª")
        docs = self.db.collection(runs_mod.COLLECTION)._docs
        self.assertEqual(list(docs), ["briefing:2026-10-01"])
        self.assertEqual(docs["briefing:2026-10-01"]["resumo"], "2ª")
        self.assertEqual(res["run_id"], "briefing:2026-10-01")

    def test_run_id_com_barra_vira_id_valido(self):
        res = runs_mod.registrar(self.db, run_id="pgd/2026-09", rotina="r", resumo="ok")
        self.assertEqual(res["run_id"], "pgd_2026-09")

    def test_registrar_com_dados_invalidos_retorna_erro(self):
        res = runs_mod.registrar(self.db, rotina="", resumo="algo")
        self.assertIn("erro", res)
        self.assertEqual(len(self.db.collection(runs_mod.COLLECTION)._docs), 0)


def _quando(dia, hora):
    return datetime(2026, 9, dia, hora, 0, tzinfo=timezone.utc)


class TestListarRecentes(unittest.TestCase):
    def setUp(self):
        self.db = _MockDB()
        col = self.db.collection(runs_mod.COLLECTION)
        col._docs["run_1"] = {"rotina": "briefing", "status": "sucesso", "resumo": "Briefing 1",
                              "criado_em": _quando(3, 6), "origem": "agendada"}
        col._docs["run_2"] = {"rotina": "varredura", "status": "erro", "resumo": "Varredura", "erro": "x",
                              "criado_em": _quando(3, 17), "origem": "mcp", "aguarda_usuario": True}
        col._docs["run_3"] = {"rotina": "briefing", "status": "sucesso", "resumo": "Briefing 2",
                              "criado_em": _quando(4, 6), "origem": "agendada", "reversivel": True,
                              "como_desfazer": "x"}

    def test_listar_todos_ordenado_decrescente(self):
        res = runs_mod.listar_recentes(self.db)
        self.assertEqual(res["total"], 3)
        self.assertEqual([r["id"] for r in res["runs"]], ["run_3", "run_2", "run_1"])

    def test_listar_com_filtro_rotina(self):
        res = runs_mod.listar_recentes(self.db, rotina="briefing")
        self.assertEqual([r["id"] for r in res["runs"]], ["run_3", "run_1"])

    def test_filtros_novos(self):
        self.assertEqual([r["id"] for r in runs_mod.listar_recentes(self.db, origem="mcp")["runs"]], ["run_2"])
        self.assertEqual([r["id"] for r in runs_mod.listar_recentes(self.db, status="erro")["runs"]], ["run_2"])
        self.assertEqual([r["id"] for r in runs_mod.listar_recentes(self.db, aguarda_usuario=True)["runs"]],
                         ["run_2"])
        self.assertEqual([r["id"] for r in runs_mod.listar_recentes(self.db, desde="2026-09-03T12:00:00Z")["runs"]],
                         ["run_3", "run_2"])

    def test_desde_invalido_levanta(self):
        with self.assertRaises(ValueError):
            runs_mod.listar_recentes(self.db, desde="ontem")

    def test_teto_de_cinquenta(self):
        col = self.db.collection(runs_mod.COLLECTION)
        for i in range(70):
            col._docs[f"x{i}"] = {"rotina": "r", "status": "sucesso", "resumo": "ok", "criado_em": _quando(5, 0)}
        self.assertEqual(len(runs_mod.listar_recentes(self.db, limite=500)["runs"]), 50)

    def test_resposta_publica_tem_so_os_nove_campos_do_schema(self):
        from tools.registry import output_schema

        publicados = set(output_schema("consultar_execucoes_agente")["properties"]["runs"]["items"]["properties"])
        for item in runs_mod.listar_recentes(self.db)["runs"]:
            self.assertEqual(set(item), publicados)

    def test_completo_traz_os_campos_novos(self):
        run = next(r for r in runs_mod.listar_recentes(self.db, completo=True)["runs"] if r["id"] == "run_3")
        self.assertTrue(run["reversivel"])
        self.assertEqual(run["origem"], "agendada")


class TestRegistrarExecucao(unittest.TestCase):
    def setUp(self):
        self.db = _MockDB()

    def _docs(self):
        return self.db.collection(runs_mod.COLLECTION)._docs

    def test_rotina_que_termina_bem_grava_sucesso_com_inicio_e_fim(self):
        with runs_mod.registrar_execucao(self.db, "briefing_matinal_acoes", run_id="briefing:2026-10-01") as run:
            run.contar(tarefas=7, eventos=3)
        d = self._docs()["briefing:2026-10-01"]
        self.assertEqual(d["status"], "sucesso")
        self.assertEqual(d["origem"], "agendada")
        self.assertEqual(d["contadores"], {"tarefas": 7, "eventos": 3})
        self.assertEqual(d["resumo"], "briefing_matinal_acoes: tarefas=7, eventos=3")
        self.assertIsNotNone(d["iniciado_em"])
        self.assertIsNotNone(d["finalizado_em"])

    def test_excecao_grava_erro_e_continua_propagando(self):
        with self.assertRaises(RuntimeError):
            with runs_mod.registrar_execucao(self.db, "relatorio_custos"):
                raise RuntimeError("BigQuery fora")
        [d] = self._docs().values()
        self.assertEqual(d["status"], "erro")
        self.assertIn("BigQuery fora", d["erro"])

    def test_falha_ao_registrar_nao_derruba_a_rotina(self):
        with mock.patch.object(runs_mod, "registrar", side_effect=RuntimeError("firestore fora")):
            with runs_mod.registrar_execucao(self.db, "r") as run:
                run.contar(x=1)
        self.assertEqual(self._docs(), {})

    def test_marcas_de_espera_reversao_e_parcial(self):
        with runs_mod.registrar_execucao(self.db, "fila_whatsapp", origem="autonoma") as run:
            run.aguardando("aprovar 1 rascunho")
            run.reversivel("cancelar_envio_whatsapp(j1) enquanto pending")
            run.afetou("a1", None, "a2")
            run.verificado("pendente")
            run.parcial("1 de 2 não saiu")
        [d] = self._docs().values()
        self.assertEqual(d["status"], "parcial")
        self.assertTrue(d["aguarda_usuario"])
        self.assertTrue(d["reversivel"])
        self.assertEqual(d["acoes_afetadas"], ["a1", "a2"])
        self.assertEqual(d["estado_verificado"], "pendente")


class TestFerramentasMcp(unittest.TestCase):
    def test_registrar_execucao_agente_aceita_campos_novos_e_origem_mcp(self):
        from tools.hermes_tools import registrar_execucao_agente

        db = _MockDB()
        res = registrar_execucao_agente(mock.Mock(db=db), {
            "rotina": "pgd_execucao", "resumo": "22 registros no Petrvs", "run_id": "pgd:2026-09",
            "aguarda_usuario": True, "motivo_espera": "aprovar 28/09", "acoes_afetadas": ["a1"]})
        d = db.collection(runs_mod.COLLECTION)._docs["pgd:2026-09"]
        self.assertEqual(res["run_id"], "pgd:2026-09")
        self.assertEqual(d["origem"], "mcp")
        self.assertTrue(d["aguarda_usuario"])

    def test_consultar_execucoes_agente_repassa_filtros(self):
        from tools.hermes_tools import consultar_execucoes_agente

        with mock.patch("agent_runs.listar_recentes", return_value={"total": 0, "runs": []}) as listar:
            consultar_execucoes_agente(mock.Mock(db="db"), {"desde": "2026-10-01", "origem": "mcp",
                                                            "aguarda_usuario": False, "limite": 5})
        _, kw = listar.call_args
        self.assertEqual((kw["desde"], kw["origem"], kw["aguarda_usuario"], kw["limite"]),
                         ("2026-10-01", "mcp", False, 5))

    def test_schemas_de_entrada_publicam_os_campos_novos(self):
        import pathlib

        base = pathlib.Path(__file__).parent / "tools" / "schemas"
        reg = json.loads((base / "registrar_execucao_agente.json").read_text(encoding="utf-8"))
        con = json.loads((base / "consultar_execucoes_agente.json").read_text(encoding="utf-8"))
        self.assertLessEqual({"run_id", "origem", "aguarda_usuario", "reversivel", "como_desfazer"},
                             set(reg["parameters"]["properties"]))
        self.assertLessEqual({"desde", "status", "origem", "aguarda_usuario"}, set(con["parameters"]["properties"]))


if __name__ == "__main__":
    unittest.main()
