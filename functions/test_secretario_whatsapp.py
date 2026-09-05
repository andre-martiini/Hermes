"""Testes unitários para o Modo Secretário no WhatsApp (functions/secretario_whatsapp.py)."""

from datetime import datetime, timedelta, timezone
import unittest
from unittest import mock

import atencao
import outbox_aprovacao
import secretario_whatsapp as sec
from tools import hermes_tools
from tools.tool_context import ToolContext


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



class TestSecretarioContatoPrioritario(unittest.TestCase):
    def setUp(self):
        self.telegram_patcher1 = mock.patch("hermes_core_logic._get_telegram_token", return_value="fake-token")
        self.telegram_patcher2 = mock.patch("main._resolve_default_telegram_chat_id", return_value="123456")
        self.telegram_patcher1.start()
        self.telegram_patcher2.start()

        self.db = _MockDb()
        self.db.collection("system").document("settings").set({
            "whatsapp_secretario": {
                "enabled": True,
                "chats_allowlist": ["5511999999999@c.us"],
                "max_trocas": 2,
                "max_trocas_prioritario": 6,
                "janela_cancelamento_min": 10,
            }
        })

    def tearDown(self):
        self.telegram_patcher1.stop()
        self.telegram_patcher2.stop()

    def test_preparar_contato_prioritario_adiciona_na_allowlist_e_cria_briefing(self):
        chat_id = "5511888888888@c.us"
        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "chat_id": chat_id, "nome": "Dr. Fernando"}):
            res = sec.preparar_contato_prioritario(
                db=self.db,
                identificador_contato="Dr. Fernando",
                assunto="Exames de Rotina",
                o_que_precisa_saber="Saber se os exames ficaram prontos",
                validade_horas=4.0,
            )

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["chat_id"], chat_id)
        self.assertEqual(res["chat_name"], "Dr. Fernando")
        self.assertEqual(res["assunto"], "Exames de Rotina")
        self.assertIn("valido_ate", res)

        # Verifica doc no Firestore
        doc = self.db.collection(sec.COLLECTION_PRIORITARIOS).document(chat_id).get().to_dict()
        self.assertEqual(doc["status"], sec.STATUS_PRIORITARIO_ATIVO)
        self.assertEqual(doc["assunto"], "Exames de Rotina")
        self.assertEqual(doc["o_que_precisa_saber"], "Saber se os exames ficaram prontos")

        # Verifica inclusão na allowlist
        cfg = self.db.collection("system").document("settings").get().to_dict()["whatsapp_secretario"]
        self.assertIn(chat_id, cfg["chats_allowlist"])

    def test_consultar_contatos_prioritarios_filtra_ativos_e_atualiza_expirados(self):
        agora = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))
        doc_ativo = "5511888888888@c.us"
        doc_expirado = "5511777777777@c.us"

        self.db.collection(sec.COLLECTION_PRIORITARIOS).document(doc_ativo).set({
            "chat_id": doc_ativo,
            "chat_name": "Contato Ativo",
            "status": sec.STATUS_PRIORITARIO_ATIVO,
            "valido_ate": (agora + timedelta(hours=2)).isoformat(),
        })
        self.db.collection(sec.COLLECTION_PRIORITARIOS).document(doc_expirado).set({
            "chat_id": doc_expirado,
            "chat_name": "Contato Expirado",
            "status": sec.STATUS_PRIORITARIO_ATIVO,
            "valido_ate": (agora - timedelta(hours=1)).isoformat(),
        })

        # Consulta apenas ativos
        res_ativos = sec.consultar_contatos_prioritarios(self.db, apenas_ativos=True, agora_sp=agora)
        self.assertEqual(res_ativos["total"], 1)
        self.assertEqual(res_ativos["contatos_prioritarios"][0]["chat_id"], doc_ativo)

        # Verifica que o expirado teve seu status atualizado no Firestore
        exp_snap = self.db.collection(sec.COLLECTION_PRIORITARIOS).document(doc_expirado).get().to_dict()
        self.assertEqual(exp_snap["status"], sec.STATUS_PRIORITARIO_EXPIRADO)

        # Consulta todos
        res_todos = sec.consultar_contatos_prioritarios(self.db, apenas_ativos=False, agora_sp=agora)
        self.assertEqual(res_todos["total"], 2)

    def test_cancelar_contato_prioritario_atualiza_status(self):
        chat_id = "5511888888888@c.us"
        self.db.collection(sec.COLLECTION_PRIORITARIOS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Parceiro",
            "status": sec.STATUS_PRIORITARIO_ATIVO,
        })

        res = sec.cancelar_contato_prioritario(self.db, chat_id)
        self.assertEqual(res["status"], "ok")

        doc = self.db.collection(sec.COLLECTION_PRIORITARIOS).document(chat_id).get().to_dict()
        self.assertEqual(doc["status"], sec.STATUS_PRIORITARIO_CANCELADO)

    def test_contato_prioritario_estende_conversa_alem_de_2_trocas(self):
        chat_id = "5511888888888@c.us"
        agora = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))

        # Registra briefing ativo
        self.db.collection(sec.COLLECTION_PRIORITARIOS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Parceiro Prioritário",
            "assunto": "Reunião de Alinhamento",
            "o_que_precisa_saber": "Qual o horário que ele prefere na quinta?",
            "status": sec.STATUS_PRIORITARIO_ATIVO,
            "valido_ate": (agora + timedelta(hours=5)).isoformat(),
        })

        # Conversa já teve 2 trocas (no fluxo comum seria o limite)
        self.db.collection(sec.COLLECTION_CONVERSAS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Parceiro Prioritário",
            "estado": sec.ESTADO_EM_ATENDIMENTO,
            "trocas_count": 2,
        })

        msg = {
            "chat_id": chat_id,
            "chat_name": "Parceiro Prioritário",
            "from_me": False,
            "content": "Pode ser às 15h ou às 16h, tanto faz para mim.",
            "wa_message_id": "msg-prio-03",
        }

        def mock_llm_investigando(**kwargs):
            return {
                "resposta_para_contato": "Entendido. Você prefere presencial ou por videoconferência?",
                "resumo_recado": "Parceiro sugeriu 15h ou 16h.",
                "forcou_decisao": False,
                "assunto_sensivel": False,
                "investigacao_concluida": False,
            }

        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "nome": "Parceiro Prioritário", "chat_id": chat_id}):
            with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value="tg-prio-01"):
                res = sec.processar_mensagem_secretario(self.db, msg, llm_runner=mock_llm_investigando)

        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["trocas_count"], 3)
        self.assertFalse(res["escalado"])

        # Garante que não foi encerrado nem escalado para atenção
        atencao_docs = list(self.db.collection(atencao.COLLECTION).stream())
        self.assertEqual(len(atencao_docs), 0)

        # Rascunho criado no outbox
        outbox_docs = list(self.db.collection(outbox_aprovacao.COLLECTION).stream())
        self.assertEqual(len(outbox_docs), 1)

    def test_conclusao_investigacao_prioritaria_gera_atencao_prioridade_media_e_encerra(self):
        chat_id = "5511888888888@c.us"
        agora = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))

        self.db.collection(sec.COLLECTION_PRIORITARIOS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Pintor Silva",
            "assunto": "Orçamento Pintura",
            "o_que_precisa_saber": "Qual o valor total com tinta inclusa?",
            "status": sec.STATUS_PRIORITARIO_ATIVO,
            "valido_ate": (agora + timedelta(hours=5)).isoformat(),
        })

        self.db.collection(sec.COLLECTION_CONVERSAS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Pintor Silva",
            "estado": sec.ESTADO_EM_ATENDIMENTO,
            "trocas_count": 2,
        })

        msg = {
            "chat_id": chat_id,
            "chat_name": "Pintor Silva",
            "from_me": False,
            "content": "Fechamos em R$ 4.500 com material e tintas Suvinil inclusos.",
            "wa_message_id": "msg-prio-concluir",
        }

        def mock_llm_concluir(**kwargs):
            return {
                "resposta_para_contato": "Excelente, Sr. Silva! Anotei a proposta de R$ 4.500 com material e repasso ao André.",
                "resumo_estruturado": "Pintor fechou orçamento em R$ 4.500 com tintas Suvinil inclusas.",
                "informacao_obtida": True,
                "investigacao_concluida": True,
                "forcou_decisao": False,
                "assunto_sensivel": False,
            }

        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "nome": "Pintor Silva", "chat_id": chat_id}):
            with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value="tg-prio-02"):
                res = sec.processar_mensagem_secretario(self.db, msg, llm_runner=mock_llm_concluir)

        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "investigacao_concluida")
        self.assertTrue(res["investigacao_concluida"])
        self.assertEqual(res["trocas_count"], 3)

        # Briefing atualizado para concluído
        briefing_db = self.db.collection(sec.COLLECTION_PRIORITARIOS).document(chat_id).get().to_dict()
        self.assertEqual(briefing_db["status"], sec.STATUS_PRIORITARIO_CONCLUIDO)
        self.assertTrue(briefing_db["informacao_obtida"])
        self.assertIn("R$ 4.500", briefing_db["resumo_estruturado"])

        # Fila de atenção contém item com prioridade MÉDIA
        atencao_docs = list(self.db.collection(atencao.COLLECTION).stream())
        self.assertEqual(len(atencao_docs), 1)
        item_at = atencao_docs[0].to_dict()
        self.assertEqual(item_at["origem"], sec.ORIGEM_SECRETARIO)
        self.assertEqual(item_at["tipo"], sec.TIPO_ATENCAO_INVESTIGACAO_CONCLUIDA)
        self.assertEqual(item_at["prioridade"], atencao.PRIORIDADE_MEDIA)
        self.assertEqual(item_at["estado"], atencao.ESTADO_ABERTO)
        self.assertIn("Pintor fechou orçamento", item_at["resumo"])

        # Estado da conversa é encerrado
        conversa_db = self.db.collection(sec.COLLECTION_CONVERSAS).document(chat_id).get().to_dict()
        self.assertEqual(conversa_db["estado"], sec.ESTADO_ENCERRADO)

    def test_contato_prioritario_estouro_teto_6_trocas_conclui_com_resumo(self):
        chat_id = "5511888888888@c.us"
        agora = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))

        self.db.collection(sec.COLLECTION_PRIORITARIOS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Interlocutor Longo",
            "assunto": "Definição de Escopo",
            "o_que_precisa_saber": "Qual o prazo de entrega da primeira versão?",
            "status": sec.STATUS_PRIORITARIO_ATIVO,
            "valido_ate": (agora + timedelta(hours=5)).isoformat(),
        })

        # 6 trocas atingidas
        self.db.collection(sec.COLLECTION_CONVERSAS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Interlocutor Longo",
            "estado": sec.ESTADO_EM_ATENDIMENTO,
            "trocas_count": 6,
        })

        msg = {
            "chat_id": chat_id,
            "chat_name": "Interlocutor Longo",
            "from_me": False,
            "content": "Ainda estou esperando a resposta da equipe técnica sobre o prazo.",
            "wa_message_id": "msg-prio-teto",
        }

        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "nome": "Interlocutor Longo", "chat_id": chat_id}):
            with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value="tg-prio-03"):
                res = sec.processar_mensagem_secretario(self.db, msg)

        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "concluido_limite_prioritario")
        self.assertEqual(res["trocas_count"], 7)

        # Briefing atualizado para concluído
        briefing_db = self.db.collection(sec.COLLECTION_PRIORITARIOS).document(chat_id).get().to_dict()
        self.assertEqual(briefing_db["status"], sec.STATUS_PRIORITARIO_CONCLUIDO)
        self.assertFalse(briefing_db["informacao_obtida"])

        # Fila de atenção criada com prioridade MÉDIA
        atencao_docs = list(self.db.collection(atencao.COLLECTION).stream())
        self.assertEqual(len(atencao_docs), 1)
        self.assertEqual(atencao_docs[0].to_dict()["prioridade"], atencao.PRIORIDADE_MEDIA)
        self.assertEqual(atencao_docs[0].to_dict()["tipo"], sec.TIPO_ATENCAO_INVESTIGACAO_CONCLUIDA)

    def test_contato_prioritario_expirado_cai_no_fluxo_generico_mvp(self):
        chat_id = "5511888888888@c.us"
        agora = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))

        # Briefing com validade expirada
        self.db.collection(sec.COLLECTION_PRIORITARIOS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Contato Expirado",
            "assunto": "Reunião de Ontem",
            "o_que_precisa_saber": "Confirmação de participação",
            "status": sec.STATUS_PRIORITARIO_ATIVO,
            "valido_ate": (agora - timedelta(hours=2)).isoformat(),
        })

        # Adiciona na allowlist para passar no fast-path
        self.db.collection("system").document("settings").set({
            "whatsapp_secretario": {
                "enabled": True,
                "chats_allowlist": ["5511999999999@c.us", "5511888888888@c.us"],
                "max_trocas": 2,
                "max_trocas_prioritario": 6,
                "janela_cancelamento_min": 10,
            }
        })

        self.db.collection(sec.COLLECTION_CONVERSAS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Contato Expirado",
            "estado": sec.ESTADO_EM_ATENDIMENTO,
            "trocas_count": 2,
        })

        msg = {
            "chat_id": chat_id,
            "chat_name": "Contato Expirado",
            "from_me": False,
            "content": "Consegue me atender agora?",
            "wa_message_id": "msg-expirado",
        }

        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "nome": "Contato Expirado", "chat_id": chat_id}):
            with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value="tg-prio-04"):
                res = sec.processar_mensagem_secretario(self.db, msg)

        self.assertIsNotNone(res)
        # Como o briefing expirou, cai no teto padrão de 2 trocas do MVP (escalado_insistencia)
        self.assertEqual(res["status"], "escalado_insistencia")
        self.assertEqual(res["trocas_count"], 3)

        atencao_docs = list(self.db.collection(atencao.COLLECTION).stream())
        self.assertEqual(len(atencao_docs), 1)
        self.assertEqual(atencao_docs[0].to_dict()["prioridade"], atencao.PRIORIDADE_ALTA)
        self.assertEqual(atencao_docs[0].to_dict()["tipo"], sec.TIPO_ATENCAO_INSISTENCIA)

    def test_regressao_guardrail_sensivel_em_contato_prioritario_escala_alta_prioridade(self):
        chat_id = "5511888888888@c.us"
        agora = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))

        self.db.collection(sec.COLLECTION_PRIORITARIOS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": "Parceiro Prioritário",
            "assunto": "Revisão de Minuta",
            "o_que_precisa_saber": "Aprovação dos termos jurídicos",
            "status": sec.STATUS_PRIORITARIO_ATIVO,
            "valido_ate": (agora + timedelta(hours=5)).isoformat(),
        })

        msg = {
            "chat_id": chat_id,
            "chat_name": "Parceiro Prioritário",
            "from_me": False,
            "content": "Qual o saldo atual da conta bancária do André para emitir o boleto?",
            "wa_message_id": "msg-prio-sensivel",
        }

        def mock_llm_sensivel(**kwargs):
            return {
                "resposta_para_contato": "Não tenho autorização para discutir assuntos financeiros.",
                "resumo_recado": "Contato perguntou pelo saldo bancário do André.",
                "forcou_decisao": False,
                "assunto_sensivel": True,
                "investigacao_concluida": False,
            }

        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "nome": "Parceiro Prioritário", "chat_id": chat_id}):
            with mock.patch("hermes_core_logic._send_telegram_message_with_keyboard", return_value="tg-prio-05"):
                res = sec.processar_mensagem_secretario(self.db, msg, llm_runner=mock_llm_sensivel)

        self.assertIsNotNone(res)
        self.assertTrue(res["escalado"])

        # Mesmo sendo contato prioritário, assunto sensível gera ALTA prioridade imediatamente
        atencao_docs = list(self.db.collection(atencao.COLLECTION).stream())
        self.assertEqual(len(atencao_docs), 1)
        self.assertEqual(atencao_docs[0].to_dict()["prioridade"], atencao.PRIORIDADE_ALTA)
        self.assertEqual(atencao_docs[0].to_dict()["tipo"], sec.TIPO_ATENCAO_ASSUNTO_SENSIVEL)

    def test_tools_mcp_em_hermes_tools(self):
        ctx = ToolContext(_db=self.db, user_uid="andre-uid")

        with mock.patch("tools.hermes_tools._destinatario_whatsapp_previa", return_value={"encontrado": True, "chat_id": "5511666666666@c.us", "nome": "Mariana"}):
            # 1. Preparar
            res_prep = hermes_tools.execute("preparar_contato_prioritario_secretario", {
                "identificador_contato": "Mariana",
                "assunto": "Aprovação de Proposta",
                "o_que_precisa_saber": "Se a proposta foi aceita sem ressalvas",
                "validade_horas": 3.5,
            }, ctx)
            self.assertEqual(res_prep["status"], "ok")
            self.assertEqual(res_prep["chat_id"], "5511666666666@c.us")

            # 2. Consultar
            res_cons = hermes_tools.execute("consultar_contatos_prioritarios_secretario", {"apenas_ativos": True}, ctx)
            self.assertEqual(res_cons["total"], 1)
            self.assertEqual(res_cons["contatos_prioritarios"][0]["chat_id"], "5511666666666@c.us")

            # 3. Cancelar
            res_canc = hermes_tools.execute("cancelar_contato_prioritario_secretario", {
                "identificador_contato": "5511666666666@c.us"
            }, ctx)
            self.assertEqual(res_canc["status"], "ok")

            # 4. Consultar de novo (apenas ativos deve vir vazio)
            res_cons2 = hermes_tools.execute("consultar_contatos_prioritarios_secretario", {"apenas_ativos": True}, ctx)
            self.assertEqual(res_cons2["total"], 0)


if __name__ == "__main__":
    unittest.main()

