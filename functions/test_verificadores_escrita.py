"""Verificadores por releitura das ferramentas de escrita (verificadores_escrita.py).

Cada ferramenta de escrita é conferida relendo o documento que ela diz ter
gravado. Sucesso só com o dado de volta; erro da ferramenta, documento ausente,
valor divergente ou "nada mudou" viram `falhou`; propostas viram `pendente`.
"""

import json
import unittest
from datetime import datetime, timezone
from unittest import mock

import trava_confirmacao as tc
import verificadores_escrita as ve
from test_registrar_saude import _Db


def _db(**colecoes):
    db = _Db()
    for nome, docs in colecoes.items():
        db.collection(nome).dados.update({k: dict(v) for k, v in docs.items()})
    return db


def _v(nome, db, args, resultado):
    return tc.verificar_ferramenta(db, nome, args, resultado)


class TestAcoes(unittest.TestCase):
    def test_criar_acao_confere_o_titulo(self):
        db = _db(tarefas={"t1": {"titulo": "Pagar  IPTU"}})
        self.assertEqual(_v("criar_acao_no_sistema", db, {"titulo": "pagar iptu"}, "OK|t1").estado, "verificado")
        res = _v("criar_acao_no_sistema", db, {"titulo": "Outra coisa"}, "OK|t1")
        self.assertEqual(res.estado, "falhou")
        self.assertIn("titulo", res.motivo)

    def test_criar_acao_ausente_ou_com_erro(self):
        self.assertIn("não aparece", _v("criar_acao_no_sistema", _db(), {"titulo": "x"}, "OK|t9").motivo)
        res = _v("criar_acao_no_sistema", _db(), {"titulo": "x"}, "ERRO|horário no passado")
        self.assertEqual(res.estado, "falhou")
        self.assertIn("horário no passado", res.motivo)

    def test_registrar_no_diario(self):
        db = _db(tarefas={"t1": {"acompanhamento": [{"data": "x", "nota": "Liguei para o Marcos."}]}})
        resultado = json.dumps({"status": "ok", "task_id": "t1", "titulo": "T"})
        self.assertEqual(_v("registrar_no_diario", db, {"nota": "Liguei para o Marcos."}, resultado).estado,
                         "verificado")
        self.assertEqual(_v("registrar_no_diario", db, {"nota": "Outra nota"}, resultado).estado, "falhou")
        self.assertEqual(_v("registrar_no_diario", db, {"nota": "x"}, "ERRO|Nota vazia.").estado, "falhou")

    def test_editar_plano_confere_alteradas_adicionadas_e_removidas(self):
        db = _db(tarefas={"t1": {"plano_acao": [{"id": "e1", "estado": "feito", "text": "A"},
                                                {"id": "e3", "estado": "pendente", "text": "C"}]}})
        diff = {"alteradas": {"e1": {"estado": ["pendente", "feito"]}}, "adicionadas": ["e3"], "removidas": ["e2"]}
        self.assertEqual(_v("editar_plano_acao", db, {"task_id": "t1"}, "OK|" + json.dumps(diff)).estado,
                         "verificado")
        errado = {"alteradas": {"e1": {"estado": ["feito", "pendente"]}}}
        self.assertIn("e1", _v("editar_plano_acao", db, {"task_id": "t1"}, "OK|" + json.dumps(errado)).motivo)
        sumida = {"adicionadas": ["e9"]}
        self.assertEqual(_v("editar_plano_acao", db, {"task_id": "t1"}, "OK|" + json.dumps(sumida)).estado, "falhou")
        ficou = {"removidas": ["e3"]}
        self.assertEqual(_v("editar_plano_acao", db, {"task_id": "t1"}, "OK|" + json.dumps(ficou)).estado, "falhou")

    def test_texto_longo_resumido_no_diff_confere_pelo_resumo(self):
        # Caso real (04/10/2026): o diff de editar_plano_acao corta texto > 80 caracteres e o
        # verificador comparava o texto inteiro relido com a prévia cortada → falso "falhou".
        import subtarefas

        longo = ("Opcionais D, F e G — FEITO 04/10: texto cinético (rotulo_tela, preso ao destaque), "
                 "trilha fixa do Lyria com ducking relativo à voz e versão vertical 9:16")
        db = _db(tarefas={"t1": {"plano_acao": [{"id": "e1", "estado": "feito", "text": longo}]}})
        diff = subtarefas.diferencas([{"id": "e1", "estado": "pendente", "text": "Opcionais"}],
                                     [{"id": "e1", "estado": "feito", "text": longo}])
        self.assertTrue(diff["alteradas"]["e1"]["text"][1].endswith("..."))
        for nome in ("editar_plano_acao", "editar_etapa"):
            with self.subTest(nome=nome):
                res = _v(nome, db, {"task_id": "t1", "etapa_id": "e1"}, "OK|" + json.dumps(diff))
                self.assertEqual(res.estado, "verificado", res.motivo)

    def test_texto_longo_confere_inteiro_contra_o_pedido(self):
        # Revisão do #416: dois textos com os mesmos 77 primeiros caracteres têm o mesmo resumo;
        # com o texto pedido nos argumentos, a diferença no fim tem de aparecer.
        inicio = "Etapa com um começo idêntico e comprido o bastante para o resumo do diff cortar "
        pedido, gravado = inicio + "no fim A", inicio + "no fim B, sobrescrito por outra escrita"
        db = _db(tarefas={"t1": {"plano_acao": [{"id": "e1", "text": gravado}]}})
        diff = {"alteradas": {"e1": {"text": ["antes", pedido[:77] + "..."]}}}
        casos = (("editar_plano_acao", {"task_id": "t1", "novo_plano": [{"id": "e1", "text": pedido}]}),
                 ("editar_plano_acao", {"task_id": "t1", "etapas": json.dumps([{"id": "e1", "text": pedido}])}),
                 ("editar_etapa", {"task_id": "t1", "etapa_id": "e1", "text": pedido}))
        for nome, args in casos:
            with self.subTest(nome=nome, args=list(args)):
                res = _v(nome, db, args, "OK|" + json.dumps(diff))
                self.assertEqual(res.estado, "falhou")
                self.assertIn("e1", res.motivo)
        db_ok = _db(tarefas={"t1": {"plano_acao": [{"id": "e1", "text": pedido}]}})
        for nome, args in casos:
            with self.subTest(nome=nome, args=list(args), gravado="igual"):
                self.assertEqual(_v(nome, db_ok, args, "OK|" + json.dumps(diff)).estado, "verificado")

    def test_texto_longo_diferente_continua_falhando(self):
        pedido = "Etapa com um texto bem comprido que passa dos oitenta caracteres para o diff cortar no fim"
        gravado = "Outra etapa, com texto diferente mas também comprido o bastante para ser resumido no diff"
        db = _db(tarefas={"t1": {"plano_acao": [{"id": "e1", "text": gravado}]}})
        diff = {"alteradas": {"e1": {"text": ["antes", pedido[:77] + "..."]}}}
        res = _v("editar_plano_acao", db, {"task_id": "t1"}, "OK|" + json.dumps(diff))
        self.assertEqual(res.estado, "falhou")
        self.assertIn("e1", res.motivo)

    def test_apagar_campo_da_etapa_conta_como_verificado(self):
        db = _db(tarefas={"t1": {"plano_acao": [{"id": "e1", "text": "A"}]}})
        diff = {"alteradas": {"e1": {"data_prevista": ["2026-09-25", None]}}}
        self.assertEqual(_v("editar_etapa", db, {"task_id": "t1", "etapa_id": "e1"}, "OK|" + json.dumps(diff)).estado,
                         "verificado")

    def test_nada_mudou_nao_e_escrita(self):
        for retorno in ("OK|Nenhuma etapa mudou: os valores enviados já eram os atuais.",
                        "AVISO|Nada mudou: etapas não citadas foram preservadas."):
            with self.subTest(retorno=retorno):
                res = _v("editar_plano_acao", _db(), {"task_id": "t1"}, retorno)
                self.assertEqual(res.estado, "falhou")
                self.assertIn("já eram os atuais", res.motivo)

    def test_agendar_lembrete(self):
        db = _db(tarefas={"t1": {"reminders": [{"reminder_at": "2026-10-02T09:00:00"}]}})
        self.assertEqual(_v("agendar_lembrete_acao", db, {}, "OK|t1|2026-10-02T09:00:00").estado, "verificado")
        self.assertEqual(_v("agendar_lembrete_acao", db, {}, "OK|t1|2026-10-03T09:00:00").estado, "falhou")

    def test_editar_acao_confere_campos_comparaveis(self):
        db = _db(tarefas={"t1": {"titulo": "Novo", "status": "concluído"}})
        ok = {"status": "completed", "campos_alterados": ["titulo", "status"]}
        self.assertEqual(_v("editar_acao", db, {"task_id": "t1", "titulo": "Novo", "status": "concluido"}, ok).estado,
                         "verificado")
        self.assertEqual(_v("editar_acao", db, {"task_id": "t1", "alteracoes": {"titulo": "Outro"}}, ok).estado,
                         "falhou")
        self.assertEqual(_v("editar_acao", db, {"task_id": "t1"}, {"erro": "Nenhum campo", "aplicado": False}).estado,
                         "falhou")

    def test_lote_com_itens_pulados_falha(self):
        db = _db(tarefas={"a": {}, "b": {}})
        itens = [{"task_id": "a", "alteracoes": {}}, {"task_id": "b", "alteracoes": {}}]
        self.assertEqual(_v("editar_acoes_em_lote", db, {"itens": itens}, {"status": "completed", "count": 2}).estado,
                         "verificado")
        res = _v("editar_acoes_em_lote", db, {"itens": itens}, "Sucesso! 1 ações atualizadas:\n• A")
        self.assertIn("só 1 de 2", res.motivo)

    def test_reagendar_pelo_texto_do_telegram(self):
        db = _db(tarefas={"a": {"data_limite": "2026-10-02"}})
        texto = "✅ 1 ações reagendadas:\n• [A](task:a) → 2026-10-02"
        self.assertEqual(_v("reagendar_acoes_em_lote", db, {}, texto).estado, "verificado")
        self.assertEqual(_v("reagendar_acoes_em_lote", db, {}, texto.replace("10-02", "10-05")).estado, "falhou")

    def test_reagendar_no_mcp_pela_atualizacao_recente(self):
        agora = datetime.now(timezone.utc).isoformat()
        db = _db(tarefas={"a": {"data_atualizacao": agora}, "b": {"data_atualizacao": "2026-01-01T00:00:00"}})
        ok = {"status": "completed", "count": 1}
        self.assertEqual(_v("reagendar_acoes_em_lote", db, {"task_ids": ["a"]}, ok).estado, "verificado")
        self.assertEqual(_v("reagendar_acoes_em_lote", db, {"task_ids": ["a", "b"]}, ok).estado, "falhou")
        self.assertIsNone(_v("reagendar_acoes_em_lote", db, {"filtro_data": "2026-10-01"}, ok))


class TestMemoriaEOutros(unittest.TestCase):
    def test_salvar_memoria(self):
        db = _db(knowledge_nodes={"m1": {"texto_memoria": "Gosto de café"}, "m2": {"fato": "Tenho 2 filhos"}})
        self.assertEqual(_v("salvar_memoria_global", db, {"fato": "gosto de cafe"},
                            {"status": "saved", "memory_id": "m1"}).estado, "verificado")
        self.assertEqual(_v("salvar_memoria_global", db, {"fato": "Tenho 2 filhos"},
                            json.dumps({"status": "saved", "id": "m2"})).estado, "verificado")
        self.assertEqual(_v("salvar_memoria_global", db, {}, {"status": "conflict", "memory_id": "m1"}).estado,
                         "pendente")
        self.assertEqual(_v("salvar_memoria_global", db, {}, {"status": "ignored", "reason": "efemero"}).estado,
                         "falhou")
        self.assertEqual(_v("salvar_memoria_global", db, {}, {"status": "ignored", "reason": "duplicate",
                                                               "memory_id": "m1"}).estado, "verificado")

    def test_financeiro_confere_valor_na_colecao_do_tipo(self):
        db = _db(fixed_bills={"f1": {"amount": 173.16}})
        ok = json.dumps({"success": True, "tipo": "obrigacao_fixa", "id": "f1"})
        self.assertEqual(_v("registrar_item_financeiro_v2", db, {"valor": "173,16"}, ok).estado, "verificado")
        self.assertEqual(_v("registrar_item_financeiro_v2", db, {"valor": 10}, ok).estado, "falhou")
        erro = 'ERRO|{"success": false, "reason": "tipo_invalido"}'
        self.assertEqual(_v("registrar_item_financeiro_v2", db, {}, erro).estado, "falhou")

    def test_cancelar_envio_relê_o_status(self):
        db = _db(whatsapp_outbox={"o1": {"status": "canceled"}, "o2": {"status": "pending"}})
        self.assertEqual(_v("cancelar_envio_whatsapp", db, {}, json.dumps({"status": "ok", "outbox_id": "o1"})).estado,
                         "verificado")
        self.assertEqual(_v("cancelar_envio_whatsapp", db, {}, {"status": "ok", "outbox_id": "o2"}).estado, "falhou")
        self.assertEqual(_v("cancelar_envio_whatsapp", db, {}, {"status": "nao_cancelavel"}).estado, "falhou")

    def test_modo_secretario(self):
        db = _db(system={"settings": {"whatsapp_secretario": {"enabled": True}}})
        self.assertEqual(_v("ativar_modo_secretario", db, {}, json.dumps({"success": True})).estado, "verificado")
        self.assertEqual(_v("desativar_modo_secretario", db, {}, json.dumps({"success": True})).estado, "falhou")

    def test_imagem_e_relatorio(self):
        db = _db(imagens_geradas={"a1b2c3d4e5f6": {}}, relatorios={"r1": {}})
        url = "![x](https://x/o/imagens_geradas%2F2026-10%2Fa1b2c3d4e5f6_previa.jpg?alt=media)"
        self.assertEqual(_v("gerar_imagem", db, {}, url).estado, "verificado")
        self.assertEqual(_v("gerar_imagem", db, {}, {"status": "processing", "job_id": "j"}).estado, "pendente")
        self.assertEqual(_v("gerar_relatorio", db, {}, json.dumps({"report_id": "r1"})).estado, "verificado")
        self.assertEqual(_v("gerar_relatorio", db, {}, "⚠️ Erro ao gerar relatório: x").estado, "falhou")

    def test_registrar_saude_rele_peso_por_data(self):
        db = _db(health_weights={"w": {"date": "2026-10-01", "weight": 94.4}})
        ok = {"status": "completed", "data": "2026-10-01", "campos_alterados": ["peso"]}
        self.assertEqual(_v("registrar_saude", db, {"peso": 94.4}, ok).estado, "verificado")
        self.assertEqual(_v("registrar_saude", db, {"peso": 95}, ok).estado, "falhou")

    def test_registrar_peso_reaproveita_o_resultado_ja_verificado(self):
        dados = {"estado": "verificado", "operacao": "registrar_peso", "alvo": "health_weights/x",
                 "valor_relido": {"weight": 94.4, "date": "2026-10-01"}, "confirmacao": "..."}
        self.assertEqual(_v("registrar_peso", _db(), {}, json.dumps(dados)).estado, "verificado")

    def test_propostas_ficam_pendentes_e_leituras_sem_verificacao(self):
        for nome in ("propor_acao_para_confirmacao", "schedule_whatsapp_message", "preparar_edicao_acao"):
            with self.subTest(nome=nome):
                self.assertEqual(_v(nome, _db(), {}, "Proposta gerada").estado, "pendente")
        self.assertIsNone(_v("obter_acao", _db(), {}, "{}"))

    def test_todo_verificador_aceita_retorno_de_erro_sem_explodir(self):
        for nome in ve.VERIFICADORES:
            with self.subTest(nome=nome):
                res = _v(nome, _db(), {"task_id": "t1", "confirmar_contrato": True}, "ERRO|falhou de propósito")
                self.assertIn(res.estado, ("falhou", "pendente"))


class TestLadoMcp(unittest.TestCase):
    def test_ferramenta_de_escrita_ganha_verificacao(self):
        ctx = mock.Mock(db=_db(tarefas={"t1": {"titulo": "X"}}))
        texto = tc.verificar_e_anotar_mcp(ctx, "criar_acao_no_sistema", {"titulo": "X"}, "OK|t1")
        self.assertTrue(texto.startswith("OK|t1\n[verificacao: "))
        self.assertIn('"estado": "verificado"', texto)

    def test_ferramenta_com_output_schema_fica_intacta(self):
        ctx = mock.Mock(db=_db())
        resultado = {"total": 0, "runs": []}
        with mock.patch.dict(ve.VERIFICADORES, {"consultar_execucoes_agente": mock.Mock()}) as _:
            self.assertIs(tc.verificar_e_anotar_mcp(ctx, "consultar_execucoes_agente", {}, resultado), resultado)

    def test_nenhuma_ferramenta_verificada_tem_output_schema(self):
        from tools.registry import output_schema

        self.assertEqual([n for n in ve.VERIFICADORES if output_schema(n) is not None], [])

    def test_tools_call_do_servidor_anota_o_retorno(self):
        import mcp_server

        ctx = mock.Mock(db=_db(tarefas={"t1": {"acompanhamento": [{"nota": "ok"}]}}), user_uid="dono", canal="mcp",
                        task_id=None)
        with mock.patch.object(mcp_server.registry, "is_mcp_enabled", return_value=True), \
                mock.patch.object(mcp_server, "_exige_confirmacao", return_value=False), \
                mock.patch.object(mcp_server, "execute_tool",
                                  return_value={"status": "ok", "task_id": "t1", "titulo": "T"}), \
                mock.patch.object(mcp_server, "_audit_log"), \
                mock.patch.object(mcp_server, "_decidir_politica_mcp", return_value=None, create=True):
            r = mcp_server._handle_tools_call({"name": "registrar_no_diario",
                                               "arguments": {"nota": "ok", "task_id_alvo": "t1"}}, ctx=ctx)
        dados = json.loads(r["content"][0]["text"])
        self.assertEqual(dados["verificacao"]["estado"], "verificado")


if __name__ == "__main__":
    unittest.main()
