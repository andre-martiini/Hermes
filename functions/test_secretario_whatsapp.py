"""Testes unitários para o Modo Secretário no WhatsApp (functions/secretario_whatsapp.py)."""

from datetime import datetime, timezone
import unittest
from unittest import mock

import atencao
import outbox_aprovacao
import secretario_whatsapp as sec


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
            self.col._docs[self.id] = {}
        self.col._docs[self.id].update(data)

    def delete(self):
        self.col._docs.pop(self.id, None)


class _MockQuery:
    def __init__(self, col, items):
        self.col = col
        self.items = items

    def limit(self, count):
        return self

    def stream(self):
        snaps = []
        for k, v in self.items:
            snap = _MockDocSnap(k, v)
            snap.reference = _MockDocRef(self.col, k)
            snaps.append(snap)
        return snaps


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

    def limit(self, count):
        return self

    def where(self, field, op, val):
        if op == "==":
            return _MockQuery(self, [(k, v) for k, v in self._docs.items() if v.get(field) == val])
        return _MockQuery(self, [])

    def stream(self):
        snaps = []
        for k, v in self._docs.items():
            snap = _MockDocSnap(k, v)
            snap.reference = _MockDocRef(self, k)
            snaps.append(snap)
        return snaps


class _MockDb:
    def __init__(self):
        self._cols: dict[str, _MockCollection] = {}

    def collection(self, name: str):
        if name not in self._cols:
            self._cols[name] = _MockCollection(self, name)
        return self._cols[name]


class TestSecretarioRegrasPuras(unittest.TestCase):
    def test_prefixar_assinatura_adiciona_prefixo_se_ausente(self):
        texto = "Olá, o André está em reunião."
        res = sec.prefixar_assinatura(texto)
        self.assertEqual(res, "**Hermes Bot:** Olá, o André está em reunião.")

    def test_prefixar_assinatura_mantem_prefixo_se_ja_presente(self):
        texto = "**Hermes Bot:** Olá, já anotei o seu recado."
        res = sec.prefixar_assinatura(texto)
        self.assertEqual(res, "**Hermes Bot:** Olá, já anotei o seu recado.")

    def test_prefixar_assinatura_limpa_variacoes_duplicadas(self):
        texto = "Hermes Bot: Olá, anotei."
        res = sec.prefixar_assinatura(texto)
        self.assertEqual(res, "**Hermes Bot:** Olá, anotei.")

    def test_chat_na_allowlist_match_exato_e_digitos(self):
        allowlist = ["5511999999999@c.us", "5521888888888"]
        self.assertTrue(sec.chat_na_allowlist("5511999999999@c.us", allowlist))
        self.assertTrue(sec.chat_na_allowlist("5521888888888@c.us", allowlist))
        self.assertFalse(sec.chat_na_allowlist("5531777777777@c.us", allowlist))
        self.assertFalse(sec.chat_na_allowlist("", allowlist))
        self.assertFalse(sec.chat_na_allowlist("5511999999999@c.us", []))

    def test_validar_regra_agenda_ocupado_informa_livre_nunca_confirma(self):
        # Caso ocupado
        conflitos = [{"titulo": "Reunião Diretoria", "data": "2026-09-05", "inicio": "14:00", "fim": "15:00"}]
        res_ocupado = sec.validar_regra_agenda(conflitos)
        self.assertTrue(res_ocupado["ocupado"])
        self.assertTrue(res_ocupado["pode_informar_conflito"])
        self.assertIn("Reunião Diretoria", res_ocupado["motivo"])

        # Caso livre
        res_livre = sec.validar_regra_agenda([])
        self.assertFalse(res_livre["ocupado"])
        self.assertFalse(res_livre["pode_informar_conflito"])
        self.assertIn("NUNCA confirmar disponibilidade", res_livre["motivo"])


class TestSecretarioFluxoIntegrado(unittest.TestCase):
    def setUp(self):
        self.telegram_patcher1 = mock.patch("hermes_core_logic._get_telegram_token", return_value="fake-token")
        self.telegram_patcher2 = mock.patch("main._resolve_default_telegram_chat_id", return_value="123456")
        self.telegram_patcher1.start()
        self.telegram_patcher2.start()

        self.db = _MockDb()
        # Configura system/settings com whatsapp_secretario habilitado para 5511999999999@c.us
        self.db.collection("system").document("settings").set({
            "whatsapp_secretario": {
                "enabled": True,
                "chats_allowlist": ["5511999999999@c.us"],
                "max_trocas": 2,
                "janela_cancelamento_min": 10,
            }
        })

    def tearDown(self):
        self.telegram_patcher1.stop()
        self.telegram_patcher2.stop()

    def test_desligado_por_padrao(self):
        # Desabilita o toggle
        self.db.collection("system").document("settings").set({
            "whatsapp_secretario": {"enabled": False, "chats_allowlist": ["5511999999999@c.us"]}
        })
        msg = {
            "chat_id": "5511999999999@c.us",
            "from_me": False,
            "text": "Olá André, está por aí?",
            "wa_message_id": "msg-001",
        }
        res = sec.processar_mensagem_secretario(self.db, msg)
        self.assertIsNone(res)
        # Garante que não criou conversas nem outbox
        self.assertEqual(len(self.db.collection(sec.COLLECTION_CONVERSAS)._docs), 0)
        self.assertEqual(len(self.db.collection(outbox_aprovacao.COLLECTION)._docs), 0)

    def test_fora_da_allowlist_ignora(self):
        msg = {
            "chat_id": "5521777777777@c.us",  # Não está na allowlist
            "from_me": False,
            "text": "Oi André!",
            "wa_message_id": "msg-002",
        }
        res = sec.processar_mensagem_secretario(self.db, msg)
        self.assertIsNone(res)
        self.assertEqual(len(self.db.collection(sec.COLLECTION_CONVERSAS)._docs), 0)

    def test_ignora_mensagens_de_grupo(self):
        msg = {
            "chat_id": "5511999999999@c.us",
            "from_me": False,
            "is_group": True,
            "text": "Pessoal, reunião amanhã!",
            "wa_message_id": "msg-003",
        }
        res = sec.processar_mensagem_secretario(self.db, msg)
        self.assertIsNone(res)
        self.assertEqual(len(self.db.collection(sec.COLLECTION_CONVERSAS)._docs), 0)

    def test_mensagem_from_me_marca_assumido_por_andre(self):
        chat_id = "5511999999999@c.us"
        # Pré-existência de conversa em atendimento
        self.db.collection(sec.COLLECTION_CONVERSAS).document(chat_id).set({
            "chat_id": chat_id,
            "estado": sec.ESTADO_EM_ATENDIMENTO,
            "trocas_count": 1,
        })
        # André envia mensagem no chat
        msg = {
            "chat_id": chat_id,
            "from_me": True,
            "text": "Oi fulano, estou assumindo aqui.",
            "wa_message_id": "msg-from-me",
        }
        res = sec.processar_mensagem_secretario(self.db, msg)
        self.assertIsNone(res)
        doc = self.db.collection(sec.COLLECTION_CONVERSAS).document(chat_id).get().to_dict()
        self.assertEqual(doc.get("estado"), sec.ESTADO_ASSUMIDO_POR_ANDRE)

    def test_fluxo_normal_gera_outbox_com_assinatura_e_janela(self):
        chat_id = "5511999999999@c.us"
        msg = {
            "chat_id": chat_id,
            "chat_name": "Carlos Parceiro",
            "from_me": False,
            "content": "Oi André, você consegue ver o relatório que te mandei?",
            "wa_message_id": "msg-100",
        }

        def mock_llm(**kwargs):
            return {
                "resposta_para_contato": "Olá Carlos! O André está em reunião agora. Já anotei sobre o relatório e aviso a ele.",
                "resumo_recado": "Carlos pediu para ver o relatório enviado.",
                "forcou_decisao": False,
                "assunto_sensivel": False,
            }

        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "nome": "Carlos Parceiro", "chat_id": chat_id}):
            with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value="tg-999"):
                res = sec.processar_mensagem_secretario(self.db, msg, llm_runner=mock_llm)

        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["trocas_count"], 1)

        # Verifica estado da conversa
        conversa = self.db.collection(sec.COLLECTION_CONVERSAS).document(chat_id).get().to_dict()
        self.assertEqual(conversa.get("estado"), sec.ESTADO_EM_ATENDIMENTO)
        self.assertEqual(conversa.get("trocas_count"), 1)
        self.assertIn("Carlos pediu para ver o relatório", conversa.get("ultimo_recado"))

        # Verifica rascunho no outbox
        outbox_docs = list(self.db.collection(outbox_aprovacao.COLLECTION).stream())
        self.assertEqual(len(outbox_docs), 1)
        rascunho = outbox_docs[0].to_dict()
        self.assertTrue(rascunho["content"].startswith("**Hermes Bot:** "))
        self.assertEqual(rascunho["tipo"], sec.TIPO_OUTBOX_SECRETARIO)
        self.assertEqual(rascunho["status"], outbox_aprovacao.STATUS_AGUARDANDO_JANELA)
        self.assertIsNotNone(rascunho.get("envio_liberado_em"))
        self.assertEqual(rascunho.get("telegram_message_id"), "tg-999")

    def test_limite_duas_trocas_encerra_e_escala_para_atencao(self):
        chat_id = "5511999999999@c.us"
        # Simula que já ocorreram 2 trocas
        self.db.collection(sec.COLLECTION_CONVERSAS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Carlos Parceiro",
            "estado": sec.ESTADO_EM_ATENDIMENTO,
            "trocas_count": 2,
        })

        msg = {
            "chat_id": chat_id,
            "chat_name": "Carlos Parceiro",
            "from_me": False,
            "content": "Mas você tem certeza que ele não consegue me ligar agora?",
            "wa_message_id": "msg-101",
        }

        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "nome": "Carlos Parceiro", "chat_id": chat_id}):
            with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value="tg-1000"):
                res = sec.processar_mensagem_secretario(self.db, msg)

        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "escalado_insistencia")
        self.assertEqual(res["trocas_count"], 3)

        # Conversa deve ter sido marcada como escalada
        conversa = self.db.collection(sec.COLLECTION_CONVERSAS).document(chat_id).get().to_dict()
        self.assertEqual(conversa.get("estado"), sec.ESTADO_ESCALADO)
        self.assertTrue(conversa.get("escalado"))

        # Fila de atenção deve conter item prioritário
        atencao_docs = list(self.db.collection(atencao.COLLECTION).stream())
        self.assertEqual(len(atencao_docs), 1)
        item_atencao = atencao_docs[0].to_dict()
        self.assertEqual(item_atencao["origem"], sec.ORIGEM_SECRETARIO)
        self.assertEqual(item_atencao["tipo"], sec.TIPO_ATENCAO_INSISTENCIA)
        self.assertEqual(item_atencao["prioridade"], atencao.PRIORIDADE_ALTA)
        self.assertEqual(item_atencao["estado"], atencao.ESTADO_ABERTO)

        # Mensagem no outbox com encerramento polido
        outbox_docs = list(self.db.collection(outbox_aprovacao.COLLECTION).stream())
        self.assertEqual(len(outbox_docs), 1)
        self.assertIn("Já anotei todos os detalhes e vou repassar diretamente", outbox_docs[0].to_dict()["content"])

    def test_forcar_decisao_escala_alta_prioridade(self):
        chat_id = "5511999999999@c.us"
        msg = {
            "chat_id": chat_id,
            "chat_name": "Fornecedor Urgente",
            "from_me": False,
            "content": "Preciso fechar o contrato hoje até as 17h, confirma pra mim!",
            "wa_message_id": "msg-102",
        }

        def mock_llm_forcar(**kwargs):
            return {
                "resposta_para_contato": "Entendo a urgência, mas apenas o André pode confirmar o contrato. Estou avisando ele agora.",
                "resumo_recado": "Fornecedor pressiona por confirmação de contrato hoje até 17h.",
                "forcou_decisao": True,
                "assunto_sensivel": False,
            }

        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "nome": "Fornecedor Urgente", "chat_id": chat_id}):
            with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value="tg-1001"):
                res = sec.processar_mensagem_secretario(self.db, msg, llm_runner=mock_llm_forcar)

        self.assertIsNotNone(res)
        self.assertTrue(res["escalado"])

        # Fila de atenção deve conter item com TIPO_ATENCAO_DECISAO_FORCADA e alta prioridade
        atencao_docs = list(self.db.collection(atencao.COLLECTION).stream())
        self.assertEqual(len(atencao_docs), 1)
        item = atencao_docs[0].to_dict()
        self.assertEqual(item["origem"], sec.ORIGEM_SECRETARIO)
        self.assertEqual(item["tipo"], sec.TIPO_ATENCAO_DECISAO_FORCADA)
        self.assertEqual(item["prioridade"], atencao.PRIORIDADE_ALTA)

    def test_assunto_sensivel_financeiro_ou_saude_escala_alta_prioridade(self):
        chat_id = "5511999999999@c.us"
        msg = {
            "chat_id": chat_id,
            "chat_name": "Contato Curioso",
            "from_me": False,
            "content": "Quanto o André tem na conta PJ para fazermos o pagamento?",
            "wa_message_id": "msg-103",
        }

        def mock_llm_sensivel(**kwargs):
            return {
                "resposta_para_contato": "Não tenho autorização para tratar de assuntos financeiros. Vou repassar seu contato ao André.",
                "resumo_recado": "Contato perguntou sobre saldo financeiro da conta PJ.",
                "forcou_decisao": False,
                "assunto_sensivel": True,
            }

        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "nome": "Contato Curioso", "chat_id": chat_id}):
            with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value="tg-1002"):
                res = sec.processar_mensagem_secretario(self.db, msg, llm_runner=mock_llm_sensivel)

        self.assertIsNotNone(res)
        self.assertTrue(res["escalado"])

        atencao_docs = list(self.db.collection(atencao.COLLECTION).stream())
        self.assertEqual(len(atencao_docs), 1)
        item = atencao_docs[0].to_dict()
        self.assertEqual(item["origem"], sec.ORIGEM_SECRETARIO)
        self.assertEqual(item["tipo"], sec.TIPO_ATENCAO_ASSUNTO_SENSIVEL)
        self.assertEqual(item["prioridade"], atencao.PRIORIDADE_ALTA)


if __name__ == "__main__":
    unittest.main()
