"""P03 sub-entrega 23/N (idempotentHint por handler, passo 3 do plano):
prova por HANDLER REAL, não só por leitura de código, as 5 classificações
que fecham a lista de tools de escrita/leitura_e_escrita "nunca
investigadas" -- ver tools/inventory.py e a docstring de
tools/registry.py::mcp_annotations para o veredito e a evidência de cada
uma.

Um `_FakeDb` único, genérico o bastante para `.document(id).get()/.set()/
.update()` e `.where(campo, "==", valor)` encadeado + `.limit()/.stream()`
-- suficiente para os 5 handlers abaixo, nenhum dos quais usa operador de
consulta além de igualdade. `db.writes` registra cada `.set()`/`.update()`
na ordem em que aconteceram, para os testes contarem gravações sem
depender de mexer no relógio ou em geração de ID.

1. `acompanhar_processo_sipac` -- IDEMPOTENTE: doc `sipac_processos/{uid}_
   {numero}` (ID determinístico) via `.set(merge=True)`; repetir a MESMA
   chamada converge no mesmo `acompanhar`.
2. `consolidar_whatsapp` -- NAO_IDEMPOTENTE: ID automático + `.set()`
   incondicional cria um segundo job a cada repetição.
3. `consultar_contatos_prioritarios_secretario` -- IDEMPOTENTE: expiração
   guardada por status, mesmo desenho de `consultar_autorizacao_argos`
   (sub-entrega 20/N).
4. `registrar_inscricao_bolsa_publica` -- IDEMPOTENTE: `vinculos_projeto`
   checado por project_id+cpf antes de criar.
5. `schedule_whatsapp_message` -- NAO_IDEMPOTENTE: `idempotency_key` só
   protege retry dentro da MESMA confirmação MCP, não uma segunda chamada
   com `mcp_confirmation_id` novo (mesmo caveat de `pausar_conversa`,
   sub-entrega 17/N).
"""

from __future__ import annotations

import datetime
import unittest
from unittest.mock import patch

from tools.tool_context import ToolContext


class _FakeSnapshot:
    def __init__(self, doc_id, data, exists, ref):
        self.id = doc_id
        self._data = data
        self.exists = exists
        self.reference = ref

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, collection, doc_id):
        self._collection = collection
        self.id = doc_id

    def get(self):
        data = self._collection._docs.get(self.id)
        return _FakeSnapshot(self.id, data, exists=data is not None, ref=self)

    def set(self, data, merge=False):
        existing = self._collection._docs.get(self.id) if merge else None
        novo = {**existing, **data} if existing else dict(data)
        self._collection._docs[self.id] = novo
        self._collection._db.writes.append((self._collection.name, self.id, "set", dict(data)))

    def update(self, data):
        self._collection._docs.setdefault(self.id, {}).update(data)
        self._collection._db.writes.append((self._collection.name, self.id, "update", dict(data)))


class _FakeQuery:
    def __init__(self, collection, filtros):
        self._collection = collection
        self._filtros = filtros

    def where(self, campo, op, valor):
        assert op == "==", f"FakeQuery só suporta '==', recebeu {op!r}"
        return _FakeQuery(self._collection, self._filtros + [(campo, valor)])

    def limit(self, n):
        return self

    def stream(self):
        saida = []
        for doc_id, data in self._collection._docs.items():
            if all(data.get(campo) == valor for campo, valor in self._filtros):
                saida.append(_FakeSnapshot(doc_id, data, exists=True,
                                            ref=_FakeDocRef(self._collection, doc_id)))
        return saida


class _FakeCollection:
    def __init__(self, name, db):
        self.name = name
        self._db = db
        self._docs: dict[str, dict] = {}
        self._auto_seq = 0

    def document(self, doc_id=None):
        if doc_id is None:
            self._auto_seq += 1
            doc_id = f"{self.name}-auto-{self._auto_seq}"
        return _FakeDocRef(self, doc_id)

    def where(self, campo, op, valor):
        return _FakeQuery(self, []).where(campo, op, valor)

    def stream(self):
        return [_FakeSnapshot(doc_id, data, exists=True, ref=_FakeDocRef(self, doc_id))
                for doc_id, data in self._docs.items()]


class _FakeDb:
    def __init__(self):
        self._collections: dict[str, _FakeCollection] = {}
        self.writes: list[tuple] = []

    def collection(self, name):
        return self._collections.setdefault(name, _FakeCollection(name, self))


def _ctx(db, **kw) -> ToolContext:
    kw.setdefault("_db", db)
    kw.setdefault("user_uid", "dono")
    return ToolContext(**kw)


class TestAcompanharProcessoSipacIdempotente(unittest.TestCase):
    """`tools/hermes_tools.py::acompanhar_processo_sipac`."""

    def test_repetir_mesma_chamada_converge_no_mesmo_doc(self):
        from tools import hermes_tools

        db = _FakeDb()
        scrape_result = {"status": "Em andamento", "unidadeAtual": "PROAD",
                          "snapshot_hash": "hash-1"}
        ctx = _ctx(db)
        with patch("hermes_core_logic._call_web_callable", return_value=dict(scrape_result)):
            r1 = hermes_tools.acompanhar_processo_sipac(
                ctx, {"numero_processo": "23063.000123/2026-11", "acompanhar": True})
            r2 = hermes_tools.acompanhar_processo_sipac(
                ctx, {"numero_processo": "23063.000123/2026-11", "acompanhar": True})

        self.assertIn("ATIVADO", r1)
        self.assertIn("ATIVADO", r2)
        # ID deterministico: as duas chamadas gravam no MESMO documento, nao
        # em dois documentos distintos.
        colecao = db._collections["sipac_processos"]
        self.assertEqual(len(colecao._docs), 1)
        doc = next(iter(colecao._docs.values()))
        self.assertTrue(doc["acompanhar"])
        self.assertEqual(doc["snapshot_hash"], "hash-1")

    def test_toggle_para_false_desfaz_o_flag_no_mesmo_doc(self):
        from tools import hermes_tools

        db = _FakeDb()
        ctx = _ctx(db)
        with patch("hermes_core_logic._call_web_callable", return_value={"snapshot_hash": "h"}):
            hermes_tools.acompanhar_processo_sipac(
                ctx, {"numero_processo": "111", "acompanhar": True})
            r2 = hermes_tools.acompanhar_processo_sipac(
                ctx, {"numero_processo": "111", "acompanhar": False})

        self.assertIn("DESATIVADO", r2)
        colecao = db._collections["sipac_processos"]
        self.assertEqual(len(colecao._docs), 1)
        self.assertFalse(next(iter(colecao._docs.values()))["acompanhar"])

    def test_achado_snapshot_hash_e_sobrescrito_mesmo_sem_mudanca_real(self):
        """Documenta o achado real da nota do inventário: repetir a chamada
        (ou só chamar uma vez após o cron já ter sincronizado) sobrescreve
        `snapshot_hash` com o hash do scrape feito NA HORA da chamada
        manual -- o mesmo campo que `functions_node/index.js::
        scheduledSipacSync` usa como baseline para decidir se notifica uma
        mudança real. Não muda o veredito de idempotência (o efeito
        acontece já na primeira chamada, não é causado por REPETIR), mas é
        o tipo de interferência que a seção A09/P05 do plano já nomeia."""
        from tools import hermes_tools

        db = _FakeDb()
        ctx = _ctx(db)
        # Simula que o cron já tinha um snapshot_hash de uma sincronização
        # anterior, refletindo o estado real do processo.
        db.collection("sipac_processos").document("dono_111").set(
            {"acompanhar": True, "snapshot_hash": "hash-do-cron"})

        with patch("hermes_core_logic._call_web_callable",
                   return_value={"snapshot_hash": "hash-da-chamada-manual"}):
            hermes_tools.acompanhar_processo_sipac(ctx, {"numero_processo": "111", "acompanhar": True})

        doc = db._collections["sipac_processos"]._docs["dono_111"]
        # O hash do cron foi silenciosamente substituído por esta chamada
        # manual -- se o processo tivesse de fato mudado entre a última
        # sincronização do cron e esta chamada, o cron seguinte compararia
        # contra este hash já atualizado e NAO detectaria a mudança.
        self.assertEqual(doc["snapshot_hash"], "hash-da-chamada-manual")


class TestConsolidarWhatsappNaoIdempotente(unittest.TestCase):
    """`tools/whatsapp_tools.py::consolidar`."""

    def test_repetir_mesma_chamada_cria_segundo_job(self):
        from tools import whatsapp_tools

        db = _FakeDb()
        ctx = _ctx(db)
        args = {"chat_id": "555@c.us", "message_ids": ["m1", "m2"]}
        with patch.object(whatsapp_tools, "_exigir_monitorado", return_value=None):
            r1 = whatsapp_tools.consolidar(ctx, dict(args))
            r2 = whatsapp_tools.consolidar(ctx, dict(args))

        self.assertEqual(r1["status"], "queued")
        self.assertEqual(r2["status"], "queued")
        self.assertNotEqual(r1["job_id"], r2["job_id"])
        colecao = db._collections["whatsapp_consolidacoes"]
        # DOIS documentos de consolidacao para o MESMO recorte de mensagens
        # -- a segunda chamada nao encontra/reaproveita a primeira, dispara
        # um segundo job real de transcricao/sintese.
        self.assertEqual(len(colecao._docs), 2)


class TestConsultarContatosPrioritariosIdempotente(unittest.TestCase):
    """`secretario_whatsapp.py::consultar_contatos_prioritarios`."""

    def test_expiracao_converge_apos_primeira_chamada(self):
        import secretario_whatsapp as sw

        db = _FakeDb()
        agora = datetime.datetime(2026, 9, 23, 12, 0, tzinfo=datetime.timezone.utc)
        vencido = (agora - datetime.timedelta(hours=1)).isoformat()
        db.collection(sw.COLLECTION_PRIORITARIOS).document("c1").set({
            "status": sw.STATUS_PRIORITARIO_ATIVO,
            "valido_ate": vencido,
            "identificador_contato": "555",
        })
        db.writes.clear()  # a gravação de setup (fixture) não conta como chamada da tool

        r1 = sw.consultar_contatos_prioritarios(db, apenas_ativos=False, agora_sp=agora)
        r2 = sw.consultar_contatos_prioritarios(db, apenas_ativos=False, agora_sp=agora)

        self.assertEqual(r1["contatos_prioritarios"][0]["status"], sw.STATUS_PRIORITARIO_EXPIRADO)
        self.assertEqual(r2["contatos_prioritarios"][0]["status"], sw.STATUS_PRIORITARIO_EXPIRADO)
        # Só a PRIMEIRA chamada escreveu (encontrou o item ainda ATIVO e
        # vencido); a segunda encontra a guarda (status != ATIVO) e nao
        # grava de novo.
        gravacoes = [w for w in db.writes if w[0] == sw.COLLECTION_PRIORITARIOS]
        self.assertEqual(len(gravacoes), 1)

    def test_item_nao_vencido_nunca_escreve(self):
        import secretario_whatsapp as sw

        db = _FakeDb()
        agora = datetime.datetime(2026, 9, 23, 12, 0, tzinfo=datetime.timezone.utc)
        futuro = (agora + datetime.timedelta(hours=1)).isoformat()
        db.collection(sw.COLLECTION_PRIORITARIOS).document("c1").set({
            "status": sw.STATUS_PRIORITARIO_ATIVO,
            "valido_ate": futuro,
        })
        db.writes.clear()

        sw.consultar_contatos_prioritarios(db, apenas_ativos=True, agora_sp=agora)
        sw.consultar_contatos_prioritarios(db, apenas_ativos=True, agora_sp=agora)

        self.assertEqual(len(db.writes), 0)


class TestRegistrarInscricaoBolsaIdempotente(unittest.TestCase):
    """`tools/telegram_extended.py::execute` (ramo
    `registrar_inscricao_bolsa_publica`)."""

    def _form(self):
        return {"nome": "Fulano", "cpf": "11122233344", "rg": "MG1", "email": "f@x.com",
                "telefone": "319999999"}

    def test_repetir_mesma_inscricao_nao_duplica_vinculo(self):
        from tools import telegram_extended

        db = _FakeDb()
        db.collection("projetos").document("p1").set({"nome": "Projeto X"})
        slots = {"project_id": "p1", "formData": self._form()}

        r1 = telegram_extended.execute("registrar_inscricao_bolsa_publica", slots, db)
        r2 = telegram_extended.execute("registrar_inscricao_bolsa_publica", slots, db)

        import json
        d1, d2 = json.loads(r1), json.loads(r2)
        self.assertTrue(d1["success"])
        self.assertNotIn("alreadyLinked", d1)
        self.assertTrue(d2["success"])
        self.assertTrue(d2["alreadyLinked"])
        self.assertEqual(d1["person_id"], d2["person_id"])

        vinculos = db._collections["vinculos_projeto"]._docs
        self.assertEqual(len(vinculos), 1)
        pessoas = db._collections["perfil_pessoas"]._docs
        self.assertEqual(len(pessoas), 1)

    def test_perfil_existente_por_cpf_e_atualizado_nao_duplicado(self):
        from tools import telegram_extended

        db = _FakeDb()
        db.collection("projetos").document("p1").set({"nome": "Projeto X"})
        db.collection("perfil_pessoas").document("pessoa-existente").set(
            {"cpf": "11122233344", "nome": "Nome Antigo"})
        slots = {"project_id": "p1", "formData": self._form()}

        r = telegram_extended.execute("registrar_inscricao_bolsa_publica", slots, db)

        import json
        d = json.loads(r)
        self.assertEqual(d["person_id"], "pessoa-existente")
        pessoas = db._collections["perfil_pessoas"]._docs
        self.assertEqual(len(pessoas), 1)
        self.assertEqual(pessoas["pessoa-existente"]["nome"], "Fulano")


class TestScheduleWhatsappMessageNaoIdempotente(unittest.TestCase):
    """`tools/schedule_whatsapp_message.py::schedule_whatsapp_message`,
    exposta como tool por `tools/hermes_tools.py::_schedule_whatsapp_message`."""

    def test_sem_idempotency_key_repetir_envia_duas_mensagens(self):
        from tools.schedule_whatsapp_message import schedule_whatsapp_message

        db = _FakeDb()
        r1 = schedule_whatsapp_message(db, "5531999999999", "oi", "2026-09-24T10:00:00Z")
        r2 = schedule_whatsapp_message(db, "5531999999999", "oi", "2026-09-24T10:00:00Z")

        self.assertIn("ENFILEIRADA", r1)
        self.assertIn("ENFILEIRADA", r2)
        self.assertEqual(len(db._collections["whatsapp_outbox"]._docs), 2)

    def test_mesmo_idempotency_key_nao_duplica_mas_confirmacao_nova_sim(self):
        from tools.schedule_whatsapp_message import schedule_whatsapp_message

        db = _FakeDb()
        # Retry de rede DENTRO da mesma confirmacao MCP: protegido. A
        # segunda chamada usa um `message` DIFERENTE de propósito -- se o
        # guard `if not doc_ref.get().exists` (schedule_whatsapp_message.py)
        # não existisse, `.set()` sobrescreveria o conteúdo gravado pela
        # primeira chamada; o teste abaixo prova que o conteúdo ORIGINAL
        # sobrevive, não só que o número de documentos não muda.
        schedule_whatsapp_message(db, "5531999999999", "mensagem original", "2026-09-24T10:00:00Z",
                                   idempotency_key="confirmacao-1")
        schedule_whatsapp_message(db, "5531999999999", "mensagem DIFERENTE (retry mal-formado)",
                                   "2026-09-24T10:00:00Z", idempotency_key="confirmacao-1")
        outbox = db._collections["whatsapp_outbox"]._docs
        self.assertEqual(len(outbox), 1)
        self.assertEqual(outbox["confirmacao-1"]["content"], "mensagem original")

        # Uma SEGUNDA confirmacao MCP (mcp_confirmation_id novo) para o
        # MESMO pedido logico enfileira uma SEGUNDA mensagem real -- exatamente
        # o caveat documentado no inventario.
        schedule_whatsapp_message(db, "5531999999999", "oi", "2026-09-24T10:00:00Z",
                                   idempotency_key="confirmacao-2")
        self.assertEqual(len(db._collections["whatsapp_outbox"]._docs), 2)

    def test_wrapper_mcp_repassa_mcp_confirmation_id_diferente_por_chamada(self):
        from tools import hermes_tools

        db = _FakeDb()
        ctx1 = _ctx(db)
        ctx1.mcp_confirmation_id = "conf-a"
        ctx2 = _ctx(db)
        ctx2.mcp_confirmation_id = "conf-b"
        args = {"contact_number": "5531999999999", "message": "oi",
                "scheduled_time": "2026-09-24T10:00:00Z"}

        hermes_tools._schedule_whatsapp_message(ctx1, args)
        hermes_tools._schedule_whatsapp_message(ctx2, args)

        # Duas invocacoes da TOOL com os MESMOS argumentos de negocio, cada
        # uma com seu proprio mcp_confirmation_id (o caso real de um agente
        # chamando a tool duas vezes) -- duas mensagens reais enfileiradas.
        self.assertEqual(len(db._collections["whatsapp_outbox"]._docs), 2)


if __name__ == "__main__":
    unittest.main()
