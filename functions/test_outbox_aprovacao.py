"""Testes para o fluxo de rascunhos de WhatsApp com aprovação via Telegram (PR 4).

Cobre:
- Lógica pura (transições, montagem de card, expiração temporal)
- Transição atômica de aprovação (aguardando_aprovacao -> pending)
- Proteção contra toque duplo (already_decided)
- Descarte de rascunho e reabertura do item na fila de atenção
- Edição do conteúdo do rascunho sem alterar destinatário
- Expiração de rascunhos antigos (> 48h) sem tocar em outros status
- Validação e resolução rigorosa de destinatário na criação
"""

import datetime
from datetime import timezone, timedelta
import unittest
from unittest import mock

import outbox_aprovacao as oa


# --------------------------------------------------------------------------
# Mock simples de Firestore para testes
# --------------------------------------------------------------------------

class _MockDocSnap:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None
        self.reference = None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRef:
    def __init__(self, col, doc_id: str):
        self.col = col
        self.id = doc_id

    def get(self, transaction=None):
        data = self.col._docs.get(self.id)
        snap = _MockDocSnap(self.id, data)
        snap.reference = self
        return snap

    def set(self, data, merge=False):
        if merge and self.id in self.col._docs:
            self.col._docs[self.id].update(data)
        else:
            self.col._docs[self.id] = dict(data)

    def update(self, data):
        if self.id not in self.col._docs:
            raise KeyError(f"Doc {self.id} does not exist")
        self.col._docs[self.id].update(data)

    def delete(self):
        self.col._docs.pop(self.id, None)


class _MockCollection:
    def __init__(self, db, name: str):
        self.db = db
        self.name = name
        self._docs: dict[str, dict] = {}
        self._id_counter = 1

    def document(self, doc_id: str | None = None):
        if not doc_id:
            doc_id = f"mock-doc-{self._id_counter}"
            self._id_counter += 1
        return _MockDocRef(self, doc_id)

    def add(self, data):
        # Espelha Collection.add do Firestore real (usado por
        # autonomy.policy.registrar_decisao para gravar em
        # "policy_decisions") -- gera um id novo e devolve (update_time,
        # doc_ref), mesmo formato da API real; nada aqui lê o update_time.
        doc_id = f"mock-doc-{self._id_counter}"
        self._id_counter += 1
        self._docs[doc_id] = dict(data)
        return (None, _MockDocRef(self, doc_id))

    def where(self, field, op, val):
        if op == "==":
            return _MockQuery(self, [(k, v) for k, v in self._docs.items() if v.get(field) == val])
        if op == "in":
            return _MockQuery(self, [(k, v) for k, v in self._docs.items() if v.get(field) in val])
        return _MockQuery(self, [])

    def stream(self):
        snaps = []
        for k, v in self._docs.items():
            snap = _MockDocSnap(k, v)
            snap.reference = _MockDocRef(self, k)
            snaps.append(snap)
        return snaps


class _MockQuery:
    def __init__(self, col, items):
        self.col = col
        self.items = items

    def stream(self):
        snaps = []
        for k, v in self.items:
            snap = _MockDocSnap(k, v)
            snap.reference = _MockDocRef(self.col, k)
            snaps.append(snap)
        return snaps


class _MockTransaction:
    def __init__(self, db):
        self.db = db
        self._read_only = False
        self._id = b"mock-tx-id"
        self._max_attempts = 5

    def get(self, ref):
        return ref.get(transaction=self)

    def update(self, ref, data):
        ref.update(data)

    def _rollback(self):
        pass

    def _commit(self):
        pass

    def _clean_up(self):
        # Espelha google.cloud.firestore_v1.transaction.Transaction._clean_up:
        # o decorator @firestore.transactional chama isso antes de cada
        # tentativa, então precisa existir para o mock ser um double fiel.
        self._id = None

    def _begin(self, retry_id=None):
        # Espelha Transaction._begin: marca a transação como "em andamento"
        # (in_progress checa self._id is not None) sem round-trip de rede.
        self._id = retry_id or b"mock-tx-id"


class _MockDb:
    def __init__(self):
        self._cols: dict[str, _MockCollection] = {}

    def collection(self, name: str):
        if name not in self._cols:
            self._cols[name] = _MockCollection(self, name)
        return self._cols[name]

    def transaction(self):
        return _MockTransaction(self)


# --------------------------------------------------------------------------
# Testes Unitários
# --------------------------------------------------------------------------

class TestLogicaPura(unittest.TestCase):
    """Testes de funções puras (sem I/O ou banco)."""

    def test_validar_transicao_aprovacao(self):
        ok, msg = oa.validar_transicao_aprovacao(oa.STATUS_AGUARDANDO)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

        for status in [oa.STATUS_PENDING, oa.STATUS_DESCARTADO, oa.STATUS_SENT, oa.STATUS_EXPIRADO]:
            ok, msg = oa.validar_transicao_aprovacao(status)
            self.assertFalse(ok)
            self.assertIn("já decidido", msg)

        ok, msg = oa.validar_transicao_aprovacao(None)
        self.assertFalse(ok)
        self.assertIn("não encontrado", msg)

    def test_validar_transicao_descarte(self):
        ok, msg = oa.validar_transicao_descarte(oa.STATUS_AGUARDANDO)
        self.assertTrue(ok)

        ok, msg = oa.validar_transicao_descarte(oa.STATUS_PENDING)
        self.assertFalse(ok)
        self.assertIn("já decidido", msg)

    def test_montar_card_telegram(self):
        corpo, botoes = oa.montar_card_telegram(
            destinatario_nome="João Silva",
            motivo="Confirmar reunião",
            content="Oi João, podemos falar às 14h?",
            outbox_id="job-123",
        )
        self.assertIn("João Silva", corpo)
        self.assertIn("Confirmar reunião", corpo)
        self.assertIn("Oi João, podemos falar às 14h?", corpo)

        # 3 botões inline
        self.assertEqual(len(botoes), 1)
        row = botoes[0]
        self.assertEqual(len(row), 3)
        self.assertEqual(row[0]["callback_data"], "outbox:job-123:ok")
        self.assertEqual(row[1]["callback_data"], "outbox:job-123:edit")
        self.assertEqual(row[2]["callback_data"], "outbox:job-123:no")

    def test_avaliar_expirados_puro(self):
        agora = datetime.datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        rascunhos = [
            # 50h atrás -> expirado
            {"id": "r1", "status": oa.STATUS_AGUARDANDO, "created_at": agora - timedelta(hours=50)},
            # 10h atrás -> não expirado
            {"id": "r2", "status": oa.STATUS_AGUARDANDO, "created_at": agora - timedelta(hours=10)},
            # 50h atrás mas já pendente -> não expira
            {"id": "r3", "status": oa.STATUS_PENDING, "created_at": agora - timedelta(hours=50)},
            # 50h atrás mas descartado -> não expira
            {"id": "r4", "status": oa.STATUS_DESCARTADO, "created_at": agora - timedelta(hours=50)},
        ]
        exp = oa.avaliar_expirados(rascunhos, agora, limite_horas=48)
        self.assertEqual(exp, ["r1"])


class TestAprovacaoTransicao(unittest.TestCase):
    """Testes da transição atômica de aprovação."""

    def setUp(self):
        self.db = _MockDb()
        self.outbox = self.db.collection(oa.COLLECTION)
        # Nota: nenhum patch de firestore.transactional aqui — o
        # _MockTransaction acima implementa o protocolo real
        # (_clean_up/_begin/_commit/_rollback/_max_attempts/_read_only),
        # então estes testes exercitam o mesmo caminho de código de
        # produção (achado A04), igual TestDescarte já fazia.

    def test_aprovar_rascunho_sucesso(self):
        self.outbox._docs["job-1"] = {
            "status": oa.STATUS_AGUARDANDO,
            "to_number": "5527999990000@c.us",
            "content": "Texto da mensagem",
            "motivo": "Aviso urgente",
            "destinatario_nome": "Fulano",
            "telegram_message_id": 999,
        }

        with mock.patch("core.telegram_api.edit_message", return_value=True) as mock_edit:
            res = oa.aprovar_rascunho(self.db, "job-1", telegram_token="fake-token", chat_id="12345")
            self.assertEqual(res["status"], "ok")
            doc = self.outbox._docs["job-1"]
            self.assertEqual(doc["status"], oa.STATUS_PENDING)
            self.assertEqual(doc["aprovado_via"], "telegram")
            self.assertIsNotNone(doc.get("aprovado_em"))
            self.assertIsNotNone(doc.get("scheduled_for"))
            mock_edit.assert_called_once()
            self.assertIn("Enviado para a fila", mock_edit.call_args[0][3])

    def test_toque_duplo_nao_duplica(self):
        self.outbox._docs["job-1"] = {
            "status": oa.STATUS_AGUARDANDO,
            "to_number": "5527999990000@c.us",
            "content": "Texto",
        }
        # Primeiro clique
        res1 = oa.aprovar_rascunho(self.db, "job-1")
        self.assertEqual(res1["status"], "ok")

        # Segundo clique (toque duplo)
        res2 = oa.aprovar_rascunho(self.db, "job-1")
        self.assertEqual(res2["status"], "already_decided")
        self.assertIn("já decidido", res2["erro"])

    def test_aprovacao_resolve_item_atencao(self):
        self.outbox._docs["job-1"] = {
            "status": oa.STATUS_AGUARDANDO,
            "item_atencao_id": "item-atencao-77",
            "destinatario_nome": "Beltrano",
        }
        with mock.patch("atencao.resolver_item") as mock_resolver:
            res = oa.aprovar_rascunho(self.db, "job-1")
            self.assertEqual(res["status"], "ok")
            mock_resolver.assert_called_once_with(
                self.db,
                item_id="item-atencao-77",
                novo_estado="resolvido",
                desfecho="mensagem aprovada e enviada para a fila",
                ctx=None,
            )

    def test_aprovacao_anota_diario_acao(self):
        self.outbox._docs["job-1"] = {
            "status": oa.STATUS_AGUARDANDO,
            "acao_id": "tarefa-101",
            "motivo": "Cobrança de entrega",
            "destinatario_nome": "Ciclano",
        }
        with mock.patch("tools.hermes_tools.registrar_no_diario") as mock_diario:
            res = oa.aprovar_rascunho(self.db, "job-1")
            self.assertEqual(res["status"], "ok")
            mock_diario.assert_called_once()
            args = mock_diario.call_args[0][1]
            self.assertEqual(args["task_id_alvo"], "tarefa-101")
            self.assertIn("Cobrança de entrega", args["nota"])

    def test_aprovacao_via_cowork_adiciona_sufixo_telegram(self):
        self.outbox._docs["job-cw"] = {
            "status": oa.STATUS_AGUARDANDO,
            "telegram_message_id": 999,
            "destinatario_nome": "Renata",
            "motivo": "Confirmação de entrega",
        }
        with mock.patch("core.telegram_api.edit_message", return_value=True) as mock_edit:
            res = oa.aprovar_rascunho(
                self.db,
                "job-cw",
                aprovado_via="cowork",
                telegram_token="tok",
                chat_id="123",
            )
            self.assertEqual(res["status"], "ok")
            doc = self.outbox._docs["job-cw"]
            self.assertEqual(doc["status"], oa.STATUS_PENDING)
            self.assertEqual(doc["aprovado_via"], "cowork")

            mock_edit.assert_called_once()
            texto_editado = mock_edit.call_args[0][3]
            self.assertIn("(via Cowork)", texto_editado)


class TestDescarte(unittest.TestCase):
    """Testes de descarte de rascunho."""

    def setUp(self):
        self.db = _MockDb()
        self.outbox = self.db.collection(oa.COLLECTION)
        self.atencao = self.db.collection("atencao")

    def test_descartar_sucesso_e_reabre_fila(self):
        self.outbox._docs["job-2"] = {
            "status": oa.STATUS_AGUARDANDO,
            "item_atencao_id": "atencao-55",
            "telegram_message_id": 888,
        }
        self.atencao._docs["atencao-55"] = {
            "estado": "resolvido",
            "desfecho": "algo anterior",
        }

        with mock.patch("core.telegram_api.edit_message", return_value=True) as mock_edit:
            res = oa.descartar_rascunho(self.db, "job-2", telegram_token="tok", chat_id="123")
            self.assertEqual(res["status"], "ok")
            self.assertEqual(self.outbox._docs["job-2"]["status"], oa.STATUS_DESCARTADO)

            # Item da fila de atenção volta para aberto
            item_at = self.atencao._docs["atencao-55"]
            self.assertEqual(item_at["estado"], "aberto")
            self.assertIsNone(item_at["desfecho"])

            mock_edit.assert_called_once()
            self.assertIn("descartado", mock_edit.call_args[0][3].lower())

    def test_descartar_ja_decidido_falha(self):
        self.outbox._docs["job-2"] = {
            "status": oa.STATUS_PENDING,
        }
        res = oa.descartar_rascunho(self.db, "job-2")
        self.assertEqual(res["status"], "already_decided")

    def test_descartar_com_motivo_grava_campo_e_edita_telegram(self):
        self.outbox._docs["job-desc"] = {
            "status": oa.STATUS_AGUARDANDO,
            "telegram_message_id": 777,
            "destinatario_nome": "Felipe",
        }
        with mock.patch("core.telegram_api.edit_message", return_value=True) as mock_edit:
            res = oa.descartar_rascunho(
                self.db,
                "job-desc",
                motivo="Mensagem já enviada por email",
                telegram_token="tok",
                chat_id="123",
            )
            self.assertEqual(res["status"], "ok")
            doc = self.outbox._docs["job-desc"]
            self.assertEqual(doc["status"], oa.STATUS_DESCARTADO)
            self.assertEqual(doc.get("descartado_motivo"), "Mensagem já enviada por email")

            mock_edit.assert_called_once()
            texto_editado = mock_edit.call_args[0][3]
            self.assertIn("Motivo: Mensagem já enviada por email", texto_editado)


class _BrokenMockTransaction(_MockTransaction):
    """Simula falha real de transação (ex.: Firestore indisponível ao iniciar
    a transação). Falha em ``_begin`` — antes de qualquer leitura/escrita —
    para provar que, quando a transação nem chega a começar, nenhuma escrita
    desprotegida acontece como fallback."""

    def _begin(self, retry_id=None):
        raise RuntimeError("Firestore indisponível (simulado)")


class _MockDbTransacaoQuebrada(_MockDb):
    def transaction(self):
        return _BrokenMockTransaction(self)


class _MockDbSemTransacao:
    """Mock de DB que não implementa .transaction() — simula um backend sem
    suporte a transação real (achado A04: não deve haver fallback para
    escrita desprotegida nesse caso)."""

    def __init__(self, real_db):
        self._real = real_db

    def collection(self, name):
        return self._real.collection(name)


class TestSemFallbackParaEscritaDesprotegida(unittest.TestCase):
    """Achado A04: quando a transação atômica falha (ou não existe), a função
    deve retornar erro explícito — nunca cair para uma escrita não
    protegida que arrisque condição de corrida com liberar_rascunhos_promovidos."""

    def setUp(self):
        self.real_db = _MockDb()
        self.outbox = self.real_db.collection(oa.COLLECTION)

    def test_aprovar_com_falha_de_transacao_retorna_erro_sem_escrever(self):
        self.outbox._docs["job-falha"] = {
            "status": oa.STATUS_AGUARDANDO,
            "destinatario_nome": "Marcos",
        }
        db_quebrado = _MockDbTransacaoQuebrada()
        db_quebrado._cols[oa.COLLECTION] = self.outbox

        res = oa.aprovar_rascunho(db_quebrado, "job-falha")
        self.assertEqual(res["status"], "erro_transacao")
        self.assertIn("erro", res)
        # Documento não deve ter sido alterado por nenhum caminho alternativo.
        self.assertEqual(self.outbox._docs["job-falha"]["status"], oa.STATUS_AGUARDANDO)

    def test_aprovar_sem_suporte_a_transacao_retorna_erro_sem_escrever(self):
        self.outbox._docs["job-sem-tx"] = {
            "status": oa.STATUS_AGUARDANDO,
            "destinatario_nome": "Marcos",
        }
        db_sem_tx = _MockDbSemTransacao(self.real_db)

        res = oa.aprovar_rascunho(db_sem_tx, "job-sem-tx")
        self.assertEqual(res["status"], "erro_configuracao")
        self.assertEqual(self.outbox._docs["job-sem-tx"]["status"], oa.STATUS_AGUARDANDO)

    def test_descartar_com_falha_de_transacao_retorna_erro_sem_escrever(self):
        self.outbox._docs["job-falha-desc"] = {
            "status": oa.STATUS_AGUARDANDO,
            "destinatario_nome": "Marcos",
        }
        db_quebrado = _MockDbTransacaoQuebrada()
        db_quebrado._cols[oa.COLLECTION] = self.outbox

        res = oa.descartar_rascunho(db_quebrado, "job-falha-desc")
        self.assertEqual(res["status"], "erro_transacao")
        self.assertEqual(self.outbox._docs["job-falha-desc"]["status"], oa.STATUS_AGUARDANDO)

    def test_descartar_sem_suporte_a_transacao_retorna_erro_sem_escrever(self):
        self.outbox._docs["job-sem-tx-desc"] = {
            "status": oa.STATUS_AGUARDANDO,
            "destinatario_nome": "Marcos",
        }
        db_sem_tx = _MockDbSemTransacao(self.real_db)

        res = oa.descartar_rascunho(db_sem_tx, "job-sem-tx-desc")
        self.assertEqual(res["status"], "erro_configuracao")
        self.assertEqual(self.outbox._docs["job-sem-tx-desc"]["status"], oa.STATUS_AGUARDANDO)


class TestEdicao(unittest.TestCase):
    """Testes de substituição de conteúdo em rascunho."""

    def setUp(self):
        self.db = _MockDb()
        self.outbox = self.db.collection(oa.COLLECTION)

    def test_editar_substitui_content_e_reenvia_card(self):
        self.outbox._docs["job-3"] = {
            "status": oa.STATUS_AGUARDANDO,
            "to_number": "+5527999991111",
            "destinatario_nome": "Carlos",
            "content": "Texto velho",
            "motivo": "Follow-up",
        }

        with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value=777) as mock_send, \
                mock.patch("hermes_core_logic._get_telegram_token", return_value="tok"), \
                mock.patch("main._resolve_default_telegram_chat_id", return_value="123"):
            res = oa.aplicar_edicao_rascunho(self.db, "job-3", "Texto novo corrigido pelo dono")
            self.assertEqual(res["status"], "ok")
            doc = self.outbox._docs["job-3"]
            self.assertEqual(doc["content"], "Texto novo corrigido pelo dono")
            self.assertEqual(doc["status"], oa.STATUS_AGUARDANDO)
            self.assertEqual(doc["to_number"], "+5527999991111")
            self.assertEqual(doc["destinatario_nome"], "Carlos")
            self.assertEqual(doc["telegram_message_id"], 777)
            mock_send.assert_called_once()
            self.assertIn("Texto novo corrigido", mock_send.call_args[0][2])


class TestExpiracao(unittest.TestCase):
    """Testes de expiração de rascunhos (> 48h)."""

    def setUp(self):
        self.db = _MockDb()
        self.outbox = self.db.collection(oa.COLLECTION)

    def test_expirar_apenas_antigos_em_aguardando(self):
        agora = datetime.datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        self.outbox._docs["velho"] = {
            "status": oa.STATUS_AGUARDANDO,
            "created_at": agora - timedelta(hours=50),
            "telegram_message_id": 111,
        }
        self.outbox._docs["novo"] = {
            "status": oa.STATUS_AGUARDANDO,
            "created_at": agora - timedelta(hours=2),
        }
        self.outbox._docs["pending_antigo"] = {
            "status": oa.STATUS_PENDING,
            "created_at": agora - timedelta(hours=50),
        }

        with mock.patch("core.telegram_api.edit_message", return_value=True) as mock_edit:
            total = oa.expirar_rascunhos_pendentes(
                self.db, agora=agora, limite_horas=48, telegram_token="tok", chat_id="123"
            )
            self.assertEqual(total, 1)
            self.assertEqual(self.outbox._docs["velho"]["status"], oa.STATUS_EXPIRADO)
            self.assertEqual(self.outbox._docs["novo"]["status"], oa.STATUS_AGUARDANDO)
            self.assertEqual(self.outbox._docs["pending_antigo"]["status"], oa.STATUS_PENDING)
            mock_edit.assert_called_once()
            self.assertIn("expirado", mock_edit.call_args[0][3].lower())


class TestCriarEListarRascunho(unittest.TestCase):
    """Testes de criação e listagem."""

    def setUp(self):
        self.db = _MockDb()

    def test_criar_rascunho_destinatario_desconhecido_recusa(self):
        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={
            "encontrado": False, "informado": "numero-invalido", "sugestoes": []
        }):
            res = oa.criar_rascunho(
                self.db,
                contact_number="numero-invalido",
                message="Ola",
                motivo="Teste",
            )
            self.assertEqual(res.get("status"), "destinatario_invalido")
            self.assertIn("Destinatário não encontrado", res.get("erro", ""))

    def test_criar_rascunho_sucesso_dispara_telegram(self):
        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={
            "encontrado": True, "nome": "Mariana", "chat_id": "5527998887777@c.us"
        }), \
                mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value=555) as mock_send, \
                mock.patch("hermes_core_logic._get_telegram_token", return_value="tok"), \
                mock.patch("main._resolve_default_telegram_chat_id", return_value="123"):
            res = oa.criar_rascunho(
                self.db,
                contact_number="+5527998887777",
                message="Relatório pronto",
                motivo="Envio de fechamento",
            )
            self.assertEqual(res["status"], oa.STATUS_AGUARDANDO)
            self.assertEqual(res["destinatario_nome"], "Mariana")
            self.assertTrue(res["telegram_notificado"])
            mock_send.assert_called_once()
            self.assertIn("Mariana", mock_send.call_args[0][2])

    def test_criar_rascunho_envio_imediato_grava_scheduled_for_agora(self):
        """Regressão: envio_imediato não pode gravar scheduled_for null/ausente.

        O worker seleciona jobs pendentes com `scheduled_for <= agora()`, e essa
        comparação no Firestore exclui documentos com o campo null/ausente — um
        job de envio imediato sem scheduled_for fica pending para sempre.
        """
        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={
            "encontrado": True, "nome": "Mariana", "chat_id": "5527998887777@c.us"
        }), mock.patch("hermes_core_logic._send_telegram_message", return_value="tg-1"), \
                mock.patch("hermes_core_logic._get_telegram_token", return_value="tok"), \
                mock.patch("main._resolve_default_telegram_chat_id", return_value="123"):
            antes = datetime.datetime.now(timezone.utc)
            res = oa.criar_rascunho(
                self.db,
                contact_number="+5527998887777",
                message="Resposta automática",
                motivo="Secretário respondeu na hora",
                envio_imediato=True,
            )
            depois = datetime.datetime.now(timezone.utc)

            self.assertEqual(res["status"], oa.STATUS_PENDING)
            doc = self.db.collection(oa.COLLECTION)._docs[res["outbox_id"]]
            scheduled_for = doc.get("scheduled_for")
            self.assertIsNotNone(scheduled_for)
            self.assertLessEqual(antes, scheduled_for)
            self.assertLessEqual(scheduled_for, depois)

            # Reproduz a semântica da query do worker: scheduled_for <= agora().
            # Um valor null/ausente nunca satisfaz essa comparação no Firestore.
            self.assertTrue(scheduled_for <= datetime.datetime.now(timezone.utc))


class TestTipoEEudicaoOutbox(unittest.TestCase):
    """Testes de tipo e rastreio de edição no outbox de WhatsApp (PR 1 da Fase 3)."""

    def setUp(self):
        self.db = _MockDb()

    def test_criar_rascunho_com_tipo_explicitado(self):
        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={
            "encontrado": True, "nome": "Mariana", "chat_id": "5527998887777@c.us"
        }), mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value=123):
            res = oa.criar_rascunho(
                self.db,
                contact_number="+5527998887777",
                message="Confirmação da reunião de amanhã",
                motivo="Alinhar agenda",
                tipo="confirmacao_reuniao",
            )
            self.assertEqual(res["status"], oa.STATUS_AGUARDANDO)
            doc = self.db.collection(oa.COLLECTION)._docs[res["outbox_id"]]
            self.assertEqual(doc["tipo"], "confirmacao_reuniao")
            self.assertFalse(doc["foi_editado"])

    def test_criar_rascunho_sem_tipo_usa_default_outro(self):
        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={
            "encontrado": True, "nome": "Mariana", "chat_id": "5527998887777@c.us"
        }), mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value=123):
            res = oa.criar_rascunho(
                self.db,
                contact_number="+5527998887777",
                message="Mensagem qualquer",
                motivo="Sem tipo explícito",
            )
            self.assertEqual(res["status"], oa.STATUS_AGUARDANDO)
            doc = self.db.collection(oa.COLLECTION)._docs[res["outbox_id"]]
            self.assertEqual(doc["tipo"], "outro")
            self.assertFalse(doc["foi_editado"])

    def test_aplicar_edicao_marca_foi_editado_true(self):
        outbox = self.db.collection(oa.COLLECTION)
        outbox._docs["r1"] = {
            "status": oa.STATUS_AGUARDANDO,
            "content": "Texto original",
            "tipo": "retorno_promessa",
            "foi_editado": False,
        }
        with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value=234):
            res = oa.aplicar_edicao_rascunho(self.db, outbox_id="r1", novo_texto="Texto modificado pelo dono")
            self.assertEqual(res["status"], "ok")
            doc = outbox._docs["r1"]
            self.assertEqual(doc["content"], "Texto modificado pelo dono")
            self.assertTrue(doc["foi_editado"])

            # Segunda edição mantém foi_editado como True
            oa.aplicar_edicao_rascunho(self.db, outbox_id="r1", novo_texto="Texto refinado mais uma vez")
            self.assertTrue(outbox._docs["r1"]["foi_editado"])

    def test_aprovar_rascunho_sem_edicao_mantem_foi_editado_false(self):
        outbox = self.db.collection(oa.COLLECTION)
        outbox._docs["r2"] = {
            "status": oa.STATUS_AGUARDANDO,
            "content": "Texto direto",
            "tipo": "cobranca_terceiro",
            "foi_editado": False,
        }
        res = oa.aprovar_rascunho(self.db, outbox_id="r2")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(outbox._docs["r2"]["status"], oa.STATUS_PENDING)
        self.assertFalse(outbox._docs["r2"]["foi_editado"])

    def test_criar_rascunho_whatsapp_tool_repassa_tipo(self):
        from tools.hermes_tools import criar_rascunho_whatsapp, ToolContext
        ctx = ToolContext(_db=self.db)
        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={
            "encontrado": True, "nome": "Lucas", "chat_id": "5527999991111@c.us"
        }), mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value=123):
            res = criar_rascunho_whatsapp(ctx, {
                "contact_number": "+5527999991111",
                "message": "Aviso de reunião",
                "motivo": "Aviso",
                "tipo": "aviso_agenda",
            })
            self.assertEqual(res["status"], oa.STATUS_AGUARDANDO)
            doc = self.db.collection(oa.COLLECTION)._docs[res["outbox_id"]]
            self.assertEqual(doc["tipo"], "aviso_agenda")
            self.assertFalse(doc["foi_editado"])


class TestMetricasPorTipo(unittest.TestCase):
    """Testes da função metricas_por_tipo (PR 1 da Fase 3)."""

    def setUp(self):
        self.db = _MockDb()
        self.outbox = self.db.collection(oa.COLLECTION)

    def test_amostra_mista_calcula_taxa_correta(self):
        agora = datetime.datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        # 5 aprovados sem edição (status pending e sent)
        for i in range(1, 4):
            self.outbox._docs[f"sent_ok_{i}"] = {
                "tipo": "confirmacao_reuniao",
                "status": oa.STATUS_SENT,
                "foi_editado": False,
                "aprovado_em": agora - timedelta(minutes=i * 10),
            }
        for i in range(1, 3):
            self.outbox._docs[f"pending_ok_{i}"] = {
                "tipo": "confirmacao_reuniao",
                "status": oa.STATUS_PENDING,
                "foi_editado": False,
                "aprovado_em": agora - timedelta(minutes=30 + i * 10),
            }

        # 2 aprovados com edição
        self.outbox._docs["sent_edit_1"] = {
            "tipo": "confirmacao_reuniao",
            "status": oa.STATUS_SENT,
            "foi_editado": True,
            "aprovado_em": agora - timedelta(minutes=60),
        }
        self.outbox._docs["pending_edit_2"] = {
            "tipo": "confirmacao_reuniao",
            "status": oa.STATUS_PENDING,
            "foi_editado": True,
            "aprovado_em": agora - timedelta(minutes=70),
        }

        # Itens que DEVEM ficar de fora da conta:
        self.outbox._docs["descartado_1"] = {
            "tipo": "confirmacao_reuniao",
            "status": oa.STATUS_DESCARTADO,
            "foi_editado": False,
            "descartado_em": agora - timedelta(minutes=5),
        }
        self.outbox._docs["aguardando_1"] = {
            "tipo": "confirmacao_reuniao",
            "status": oa.STATUS_AGUARDANDO,
            "foi_editado": False,
            "created_at": agora - timedelta(minutes=2),
        }
        self.outbox._docs["outro_tipo_1"] = {
            "tipo": "outro",
            "status": oa.STATUS_SENT,
            "foi_editado": False,
            "aprovado_em": agora - timedelta(minutes=1),
        }

        res = oa.metricas_por_tipo(self.db, tipo="confirmacao_reuniao", limite=20)
        self.assertEqual(res["tipo"], "confirmacao_reuniao")
        self.assertEqual(res["amostra"], 7)  # 5 sem edição + 2 com edição
        self.assertEqual(res["aprovados_sem_edicao"], 5)
        self.assertAlmostEqual(res["taxa_sem_edicao"], 5 / 7, places=4)

    def test_limite_de_amostra_respeitado_e_ordenado_por_aprovado_em(self):
        agora = datetime.datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        # Cria 10 rascunhos: os 3 mais recentes com edição, os 7 mais antigos sem edição
        for i in range(10):
            self.outbox._docs[f"doc_{i}"] = {
                "tipo": "retorno_promessa",
                "status": oa.STATUS_SENT,
                "foi_editado": (i < 3),  # i=0,1,2 foram editados (mais recentes)
                "aprovado_em": agora - timedelta(hours=i),
            }

        # Limite = 5: pega os 5 mais recentes (i=0,1,2 foram editados; i=3,4 não foram)
        res = oa.metricas_por_tipo(self.db, tipo="retorno_promessa", limite=5)
        self.assertEqual(res["amostra"], 5)
        self.assertEqual(res["aprovados_sem_edicao"], 2)
        self.assertEqual(res["taxa_sem_edicao"], 2 / 5)

    def test_amostra_zero_retorna_zeros_sem_erro(self):
        res = oa.metricas_por_tipo(self.db, tipo="tipo_inexistente", limite=20)
        self.assertEqual(res["tipo"], "tipo_inexistente")
        self.assertEqual(res["amostra"], 0)
        self.assertEqual(res["aprovados_sem_edicao"], 0)
        self.assertEqual(res["taxa_sem_edicao"], 0.0)

    def test_tipo_vazio_retorna_zeros(self):
        res = oa.metricas_por_tipo(self.db, tipo="", limite=20)
        self.assertEqual(res["amostra"], 0)
        self.assertEqual(res["aprovados_sem_edicao"], 0)
        self.assertEqual(res["taxa_sem_edicao"], 0.0)


class TestAguardandoJanelaEListarRascunhos(unittest.TestCase):
    """Testes de suporte ao novo status aguardando_janela e montagem de card promovido (PR 2 Fase 3)."""

    def setUp(self):
        self.db = _MockDb()
        self.outbox = self.db.collection(oa.COLLECTION)

    def test_transicoes_aceitam_aguardando_janela(self):
        ok, mot = oa.validar_transicao_aprovacao(oa.STATUS_AGUARDANDO_JANELA)
        self.assertTrue(ok)
        self.assertEqual(mot, "")

        ok, mot = oa.validar_transicao_descarte(oa.STATUS_AGUARDANDO_JANELA)
        self.assertTrue(ok)
        self.assertEqual(mot, "")

    def test_montar_card_telegram_promovido(self):
        texto, botoes = oa.montar_card_telegram_promovido(
            destinatario_nome="Mariana",
            motivo="Confirmação de Reunião",
            content="Olá Mariana, tudo bem?",
            outbox_id="out-123",
            minutos_janela=10,
        )
        self.assertIn("Envio autônomo para Mariana", texto)
        self.assertIn("em até 10 min", texto)
        self.assertIn("Olá Mariana, tudo bem?", texto)
        self.assertEqual(len(botoes), 1)
        self.assertEqual(len(botoes[0]), 1)
        self.assertEqual(botoes[0][0]["text"], "🛑 Cancelar")
        self.assertEqual(botoes[0][0]["callback_data"], "outbox:out-123:no")

    def test_listar_rascunhos_inclui_aguardando_janela_e_envio_liberado_em(self):
        agora = datetime.datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)
        self.outbox._docs["r_regular"] = {
            "status": oa.STATUS_AGUARDANDO,
            "destinatario_nome": "Pedro",
            "content": "Regular",
            "tipo": "outro",
            "created_at": agora - timedelta(minutes=5),
        }
        self.outbox._docs["r_promovido"] = {
            "status": oa.STATUS_AGUARDANDO_JANELA,
            "destinatario_nome": "Carla",
            "content": "Promovido",
            "tipo": "confirmacao_reuniao",
            "created_at": agora - timedelta(minutes=2),
            "envio_liberado_em": agora + timedelta(minutes=8),
        }
        self.outbox._docs["r_descartado"] = {
            "status": oa.STATUS_DESCARTADO,
            "destinatario_nome": "João",
            "content": "Descartado",
            "created_at": agora - timedelta(minutes=10),
        }

        res = oa.listar_rascunhos(self.db, limite=20)
        self.assertEqual(res["total"], 2)
        ids = [item["id"] for item in res["rascunhos"]]
        self.assertIn("r_regular", ids)
        self.assertIn("r_promovido", ids)
        self.assertNotIn("r_descartado", ids)

        item_prom = next(i for i in res["rascunhos"] if i["id"] == "r_promovido")
        self.assertEqual(item_prom["status"], oa.STATUS_AGUARDANDO_JANELA)
        self.assertIsNotNone(item_prom.get("envio_liberado_em"))

    def test_contar_pendentes_inclui_aguardando_e_janela_ignora_outros(self):
        self.outbox._docs["r1"] = {"status": oa.STATUS_AGUARDANDO}
        self.outbox._docs["r2"] = {"status": oa.STATUS_AGUARDANDO_JANELA}
        self.outbox._docs["r3"] = {"status": oa.STATUS_SENT}
        self.outbox._docs["r4"] = {"status": oa.STATUS_DESCARTADO}
        self.outbox._docs["r5"] = {"status": oa.STATUS_EXPIRADO}
        self.outbox._docs["r6"] = {"status": oa.STATUS_PENDING}

        total = oa.contar_pendentes(self.db)
        self.assertEqual(total, 2)


class TestHermesToolsOutboxCowork(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()
        self.outbox = self.db.collection(oa.COLLECTION)
        from tools.tool_context import ToolContext
        self.ctx = ToolContext(_db=self.db)

    def test_tools_registradas_no_catalogo_e_needs_confirmation(self):
        from tools import registry
        from mcp_server import _CONFIRMACAO_OBRIGATORIA

        self.assertIn("aprovar_rascunho_whatsapp", registry._CATALOG)
        self.assertIn("descartar_rascunho_whatsapp", registry._CATALOG)

        self.assertTrue(registry.needs_confirmation("aprovar_rascunho_whatsapp"))
        self.assertTrue(registry.needs_confirmation("descartar_rascunho_whatsapp"))

        # Não deve estar em _CONFIRMACAO_OBRIGATORIA
        self.assertNotIn("aprovar_rascunho_whatsapp", _CONFIRMACAO_OBRIGATORIA)
        self.assertNotIn("descartar_rascunho_whatsapp", _CONFIRMACAO_OBRIGATORIA)

    def test_execute_aprovar_rascunho_whatsapp(self):
        from tools import hermes_tools
        self.outbox._docs["r-aprov"] = {
            "status": oa.STATUS_AGUARDANDO,
            "content": "Olá teste",
        }
        res = hermes_tools.execute(
            "aprovar_rascunho_whatsapp",
            {"outbox_id": "r-aprov"},
            self.ctx,
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(self.outbox._docs["r-aprov"]["status"], oa.STATUS_PENDING)
        self.assertEqual(self.outbox._docs["r-aprov"]["aprovado_via"], "cowork")

    def test_execute_descartar_rascunho_whatsapp(self):
        from tools import hermes_tools
        self.outbox._docs["r-desc"] = {
            "status": oa.STATUS_AGUARDANDO,
            "content": "Olá teste descartar",
        }
        res = hermes_tools.execute(
            "descartar_rascunho_whatsapp",
            {"outbox_id": "r-desc", "motivo": "Desnecessário"},
            self.ctx,
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(self.outbox._docs["r-desc"]["status"], oa.STATUS_DESCARTADO)
        self.assertEqual(self.outbox._docs["r-desc"]["descartado_motivo"], "Desnecessário")


class TestLiberarRascunhosPromovidosPreflightAutonomia(unittest.TestCase):
    """P02 sub-entrega 15/N: `liberar_rascunhos_promovidos` é o único caminho
    do outbox que envia sem toque humano por instância — cobre o preflight
    novo de `autonomy.policy.estado_autonomia_atual` (nenhum teste cobria
    esta função antes desta sub-entrega, nem o caminho feliz).

    P02 sub-entrega 17/N: os testes de caminho feliz abaixo agora também
    semeiam `system/mcp_access.tipos_promovidos` (`_set_tipo_promovido`) —
    antes desta sub-entrega, `liberar_rascunhos_promovidos` só confiava no
    status `aguardando_janela` do próprio documento (decidido no passado,
    na criação do rascunho); agora cada liberação reavalia o mandato NA
    HORA (`autonomy.mandatos_io.mandato_tipo_promovido`), então um rascunho
    cujo `tipo` nunca esteve (ou não está mais) em `tipos_promovidos` não é
    mais liberado só por já estar com esse status — ver
    `TestLiberarRascunhosPromovidosMandatoNaHora`, abaixo, para o
    comportamento de degradação quando o mandato não cobre."""

    def setUp(self):
        self.db = _MockDb()
        self.outbox = self.db.collection(oa.COLLECTION)
        self.agora = datetime.datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    def _seed_promovido(self, doc_id="r-prom", tipo="confirmacao_reuniao"):
        self.outbox._docs[doc_id] = {
            "status": oa.STATUS_AGUARDANDO_JANELA,
            "to_number": "5527999990000@c.us",
            "content": "Confirmando a reunião de amanhã",
            "destinatario_nome": "Carla",
            "tipo": tipo,
            "telegram_message_id": 4242,
            "envio_liberado_em": self.agora - timedelta(minutes=1),
        }

    def _set_estado(self, valor: str):
        self.db.collection("system")._docs["autonomy_state"] = {"global": valor}

    def _set_tipo_promovido(self, tipo="confirmacao_reuniao"):
        # Fonte real que `mandato_tipo_promovido` lê -- mesmo documento que
        # `decidir_promocao_autonomia` grava em produção.
        self.db.collection("system")._docs["mcp_access"] = {"tipos_promovidos": [tipo]}

    def test_caminho_feliz_sem_estado_configurado_e_ativo_libera_normalmente(self):
        # Sem system/autonomy_state (nada configurado ainda) -> ATIVO, mesmo
        # comportamento de produção hoje, sem esta sub-entrega.
        self._seed_promovido()
        self._set_tipo_promovido()
        n = oa.liberar_rascunhos_promovidos(self.db, agora=self.agora)
        self.assertEqual(n, 1)
        self.assertEqual(self.outbox._docs["r-prom"]["status"], oa.STATUS_PENDING)
        self.assertEqual(self.outbox._docs["r-prom"]["aprovado_via"], "janela_automatica")

    def test_estado_ativo_explicito_libera_normalmente(self):
        self._seed_promovido()
        self._set_tipo_promovido()
        self._set_estado("ativo")
        n = oa.liberar_rascunhos_promovidos(self.db, agora=self.agora)
        self.assertEqual(n, 1)
        self.assertEqual(self.outbox._docs["r-prom"]["status"], oa.STATUS_PENDING)

    def test_pausado_bloqueia_e_nao_toca_no_rascunho(self):
        self._seed_promovido()
        self._set_tipo_promovido()
        self._set_estado("pausado")
        n = oa.liberar_rascunhos_promovidos(self.db, agora=self.agora)
        self.assertEqual(n, 0)
        self.assertEqual(self.outbox._docs["r-prom"]["status"], oa.STATUS_AGUARDANDO_JANELA)
        self.assertNotIn("aprovado_via", self.outbox._docs["r-prom"])

    def test_somente_preparacao_tambem_bloqueia_envio_automatico(self):
        # "Somente preparação" -> enviar de verdade a terceiros não é
        # preparação; só um toque humano real (aprovar_rascunho via
        # Telegram) continua liberado, não o caminho automático.
        self._seed_promovido()
        self._set_tipo_promovido()
        self._set_estado("somente_preparacao")
        n = oa.liberar_rascunhos_promovidos(self.db, agora=self.agora)
        self.assertEqual(n, 0)
        self.assertEqual(self.outbox._docs["r-prom"]["status"], oa.STATUS_AGUARDANDO_JANELA)

    def test_falha_ao_ler_estado_cai_fail_closed_e_bloqueia(self):
        # estado_autonomia_atual() já trata falha de leitura como
        # SOMENTE_PREPARACAO (fail-closed) — confirma que o preflight herda
        # essa garantia em vez de assumir ATIVO na dúvida.
        self._seed_promovido()

        class _DbQuebrado:
            def collection(self, name):
                raise RuntimeError("Firestore indisponível (simulado)")

        n = oa.liberar_rascunhos_promovidos(_DbQuebrado(), agora=self.agora)
        self.assertEqual(n, 0)


class TestLiberarRascunhosPromovidosMandatoNaHora(unittest.TestCase):
    """P02 sub-entrega 17/N: `liberar_rascunhos_promovidos` religado a um
    `Mandato` real (`autonomy.mandatos_io.mandato_tipo_promovido`), resolvido
    NA HORA da liberação -- não mais só o status `aguardando_janela` gravado
    na criação do rascunho. Ver docs/autonomia/proposta-p02-mandato-io-
    wrapper.md e docs/autonomia/execucao.md (P02 sub-entrega 17/N)."""

    def setUp(self):
        self.db = _MockDb()
        self.outbox = self.db.collection(oa.COLLECTION)
        self.agora = datetime.datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    def _seed_promovido(self, doc_id="r-prom", tipo="confirmacao_reuniao"):
        self.outbox._docs[doc_id] = {
            "status": oa.STATUS_AGUARDANDO_JANELA,
            "to_number": "5527999990000@c.us",
            "content": "Confirmando a reunião de amanhã",
            "destinatario_nome": "Carla",
            "tipo": tipo,
            "telegram_message_id": 4242,
            "envio_liberado_em": self.agora - timedelta(minutes=1),
        }

    def _set_tipo_promovido(self, tipo="confirmacao_reuniao"):
        self.db.collection("system")._docs["mcp_access"] = {"tipos_promovidos": [tipo]}

    def test_tipo_ainda_promovido_libera_e_registra_decisao_allow(self):
        self._seed_promovido()
        self._set_tipo_promovido()
        n = oa.liberar_rascunhos_promovidos(self.db, agora=self.agora)
        self.assertEqual(n, 1)
        self.assertEqual(self.outbox._docs["r-prom"]["status"], oa.STATUS_PENDING)

        decisoes = list(self.db.collection("policy_decisions")._docs.values())
        self.assertEqual(len(decisoes), 1)
        self.assertEqual(decisoes[0]["decision"], "allow")
        self.assertEqual(decisoes[0]["reason_code"], "dentro_de_mandato_vigente")

    def test_tipo_nunca_promovido_degrada_para_aprovacao_manual(self):
        # `aguardando_janela` sem NUNCA ter passado por tipos_promovidos --
        # não deveria acontecer via criar_rascunho() real, mas a checagem
        # nova não confia cegamente no status para decidir enviar sozinho.
        self._seed_promovido()
        n = oa.liberar_rascunhos_promovidos(self.db, agora=self.agora)
        self.assertEqual(n, 0)
        doc = self.outbox._docs["r-prom"]
        self.assertEqual(doc["status"], oa.STATUS_AGUARDANDO)
        self.assertIsNone(doc["envio_liberado_em"])
        self.assertEqual(doc["degradado_motivo"], "mandato_nao_cobre:principal_nao_pode_autoconceder")

    def test_tipo_revogado_entre_criacao_e_liberacao_degrada_para_manual(self):
        # O cenário central desta sub-entrega: o rascunho foi criado quando
        # o tipo estava promovido (por isso está em aguardando_janela), mas
        # o André revogou o tipo (removeu de tipos_promovidos) antes de a
        # janela de cancelamento vencer. Antes desta sub-entrega, isto seria
        # enviado mesmo assim -- agora degrada para aprovação manual.
        self._seed_promovido(tipo="cobranca_terceiro")
        self._set_tipo_promovido(tipo="outro_tipo_ainda_promovido")  # não inclui "cobranca_terceiro"
        n = oa.liberar_rascunhos_promovidos(self.db, agora=self.agora)
        self.assertEqual(n, 0)
        doc = self.outbox._docs["r-prom"]
        self.assertEqual(doc["status"], oa.STATUS_AGUARDANDO)
        self.assertIsNone(doc["envio_liberado_em"])
        self.assertIn("mandato_nao_cobre", doc["degradado_motivo"])

    def test_dois_rascunhos_mesmo_tipo_reusa_mandato_cacheado(self):
        self._seed_promovido(doc_id="r-1", tipo="confirmacao_reuniao")
        self._seed_promovido(doc_id="r-2", tipo="confirmacao_reuniao")
        self._set_tipo_promovido()

        from autonomy import mandatos_io
        with mock.patch(
            "autonomy.mandatos_io.mandato_tipo_promovido",
            wraps=mandatos_io.mandato_tipo_promovido,
        ) as spy:
            n = oa.liberar_rascunhos_promovidos(self.db, agora=self.agora)

        self.assertEqual(n, 2)
        self.assertEqual(self.outbox._docs["r-1"]["status"], oa.STATUS_PENDING)
        self.assertEqual(self.outbox._docs["r-2"]["status"], oa.STATUS_PENDING)
        # O efeito observável do cache: só UMA resolução de mandato para os
        # dois rascunhos do mesmo tipo, não uma por rascunho.
        self.assertEqual(spy.call_count, 1)

    def test_tipo_outro_promovido_nao_derruba_o_lote_e_degrada_so_esse_rascunho(self):
        # Achado BLOQUEANTE da revisão adversarial (P02 sub-entrega 17/N):
        # antes da correção, "outro" em tipos_promovidos (alcançável via
        # decidir_promocao_autonomia -- promocao_autonomia não o exclui da
        # varredura) fazia Mandato.__post_init__ levantar ValueError sem
        # ninguém capturar, derrubando o LOTE inteiro -- inclusive
        # rascunhos de outros tipos, válidos, no mesmo lote. Confirma que
        # isso não acontece mais: o rascunho "outro" degrada para manual,
        # e o rascunho de tipo válido no MESMO lote continua liberado
        # normalmente.
        self._seed_promovido(doc_id="r-outro", tipo="outro")
        self._seed_promovido(doc_id="r-valido", tipo="confirmacao_reuniao")
        self.db.collection("system")._docs["mcp_access"] = {
            "tipos_promovidos": ["outro", "confirmacao_reuniao"],
        }

        n = oa.liberar_rascunhos_promovidos(self.db, agora=self.agora)

        self.assertEqual(n, 1)
        doc_outro = self.outbox._docs["r-outro"]
        self.assertEqual(doc_outro["status"], oa.STATUS_AGUARDANDO)
        self.assertIsNone(doc_outro["envio_liberado_em"])
        self.assertIn("mandato_nao_cobre", doc_outro["degradado_motivo"])
        self.assertEqual(self.outbox._docs["r-valido"]["status"], oa.STATUS_PENDING)

    def test_degradar_e_transacional_nao_sobrescreve_descarte_concorrente(self):
        # Achado BLOQUEANTE da revisão adversarial: a versão original do
        # degrade fazia um .update() cru, sem revalidar status nem
        # transação -- se um humano tivesse cancelado via Telegram (
        # descartar_rascunho, que transaciona para STATUS_DESCARTADO) entre
        # a consulta e esta função alcançar o documento, o .update() cru
        # ressuscitaria silenciosamente o rascunho descartado de volta para
        # aguardando_aprovacao. Testa o helper isoladamente: um documento
        # que JÁ NÃO está mais em aguardando_janela (simulando essa corrida)
        # não deve ser tocado.
        self.outbox._docs["r-descartado"] = {
            "status": oa.STATUS_DESCARTADO,
            "descartado_em": "2026-09-09T11:59:00+00:00",
            "descartado_motivo": "cancelado pelo dono via Telegram",
        }
        degradou = oa._degradar_rascunho_promovido_sem_mandato(
            self.db, "r-descartado", motivo_codigo="mandato_nao_cobre:teste",
        )
        self.assertFalse(degradou)
        doc = self.outbox._docs["r-descartado"]
        self.assertEqual(doc["status"], oa.STATUS_DESCARTADO)
        self.assertEqual(doc["descartado_motivo"], "cancelado pelo dono via Telegram")
        self.assertNotIn("degradado_motivo", doc)

    def test_degradar_funciona_quando_status_ainda_e_aguardando_janela(self):
        self._seed_promovido(doc_id="r-prom")
        degradou = oa._degradar_rascunho_promovido_sem_mandato(
            self.db, "r-prom", motivo_codigo="mandato_nao_cobre:teste",
        )
        self.assertTrue(degradou)
        doc = self.outbox._docs["r-prom"]
        self.assertEqual(doc["status"], oa.STATUS_AGUARDANDO)
        self.assertIsNone(doc["envio_liberado_em"])
        self.assertEqual(doc["degradado_motivo"], "mandato_nao_cobre:teste")

    def test_degradar_sem_suporte_a_transacao_nao_escreve(self):
        self._seed_promovido(doc_id="r-prom")

        class _DbSemTransacao:
            def __init__(self, outer):
                self._outer = outer

            def collection(self, name):
                return self._outer.db.collection(name)

        degradou = oa._degradar_rascunho_promovido_sem_mandato(
            _DbSemTransacao(self), "r-prom", motivo_codigo="mandato_nao_cobre:teste",
        )
        self.assertFalse(degradou)
        self.assertEqual(self.outbox._docs["r-prom"]["status"], oa.STATUS_AGUARDANDO_JANELA)


if __name__ == "__main__":
    unittest.main()
