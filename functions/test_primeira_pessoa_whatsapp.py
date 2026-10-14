"""Secretário em primeira pessoa (14/10/2026), registro das mensagens do Gaspar e a
conferência antes de cada envio."""

import datetime as dt
import unittest
from unittest import mock

import mensagens_gaspar
import outbox_aprovacao as oa
import secretario_whatsapp as sec
from test_secretario_whatsapp import _MockDb
from validacao_mensagem import problemas

CHAT = "5511999999999@c.us"


class TestConferencia(unittest.TestCase):
    def test_passa_mensagem_normal(self):
        for texto in ("Oi! Queria marcar uma consulta. Vocês têm horário quinta?",
                      "Eu ia te falar isso ontem, fico ligado aqui.",
                      "Perfeito, até quinta às 9h."):
            with self.subTest(texto=texto):
                self.assertEqual(problemas(texto), [])

    def test_barra_cada_regra_do_dono(self):
        casos = {
            "Sou o assistente do André": "assistente",
            "Aqui é o Gaspar": "assistente",
            "Resposta da IA": "assistente",
            "Pode me ligar amanhã?": "ligação",
            "Fazemos uma videochamada?": "ligação",
            "Pode deixar que eu pago amanhã": "pagamento",
            "Aceito o orçamento": "pagamento",
            "Tininha, chego às 18h": "Tininha",
            "Meu CPF é 123.456.789-00": "número",
        }
        for texto, motivo in casos.items():
            with self.subTest(texto=texto):
                self.assertTrue(any(motivo in p for p in problemas(texto)), problemas(texto))

    def test_numero_liberado_passa_e_dado_vetado_nao(self):
        self.assertEqual(problemas("A carteirinha é 123456789012", pode_informar="carteirinha 123456789012"), [])
        self.assertTrue(problemas("Moro na Rua das Flores, 10", nunca_informar="Rua das Flores; CPF"))

    def test_repeticao_vazio_e_tamanho(self):
        self.assertIn("repete uma mensagem já enviada",
                      problemas("Pode ser quinta às 9h?", ja_enviadas=["pode ser quinta às 9h?"]))
        self.assertEqual(problemas("   "), ["mensagem vazia"])
        self.assertTrue(any("longa" in p for p in problemas("a" * 1300)))


class TestRegistroDoGaspar(unittest.TestCase):
    def test_reconhece_o_eco_mesmo_com_espacos_diferentes(self):
        db = _MockDb()
        mensagens_gaspar.registrar(db, "Anotei,  te retorno.", origem="secretario_whatsapp", chat_id=CHAT)
        self.assertTrue(mensagens_gaspar.eh_do_gaspar(db, {"from_me": True, "content": "Anotei, te retorno."}))
        self.assertFalse(mensagens_gaspar.eh_do_gaspar(db, {"from_me": True, "content": "Outra coisa"}))
        self.assertFalse(mensagens_gaspar.eh_do_gaspar(db, {"from_me": False, "content": "Anotei, te retorno."}))

    def test_registro_vencido_nao_vale(self):
        db = _MockDb()
        mensagens_gaspar.registrar(db, "Anotei.", origem="secretario_whatsapp")
        doc = next(iter(db.collection(mensagens_gaspar.COLECAO)._docs.values()))
        doc["expira_em"] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        self.assertFalse(mensagens_gaspar.eh_do_gaspar(db, {"from_me": True, "content": "Anotei."}))

    # O detector consulta a flag logo depois de descartar a mensagem do bot: a flag
    # desligada encerra ali, e a chamada dela mostra se a mensagem passou da checagem.
    @mock.patch("atencao_whatsapp._flag_promessa", return_value=(False, 4))
    def test_promessa_ignora_a_mensagem_do_gaspar_sem_assinatura(self, flag):
        from atencao_whatsapp import _processar_promessa

        db = _MockDb()
        mensagens_gaspar.registrar(db, "Vou ver e te retorno amanhã.", origem="secretario_whatsapp")
        _processar_promessa(db, {"from_me": True, "chat_id": CHAT, "content": "Vou ver e te retorno amanhã."})
        flag.assert_not_called()
        _processar_promessa(db, {"from_me": True, "chat_id": CHAT, "content": "Amanhã te mando o relatório."})
        flag.assert_called_once()

    def test_banco_simulado_generico_nao_conta_como_registro(self):
        self.assertFalse(mensagens_gaspar.eh_do_gaspar(mock.MagicMock(), {"from_me": True, "content": "Oi"}))

    def test_outbox_registra_so_as_mensagens_autonomas(self):
        db = _MockDb()
        for origem, texto in (("secretario_whatsapp", "Te retorno já"), ("claude", "Mensagem aprovada pelo André")):
            oa.criar_rascunho(db=db, contact_number=CHAT, message=texto, motivo="m", origem=origem,
                              envio_imediato=True, destinatario_resolvido={"chat_id": CHAT, "nome": "Carlos"})
        self.assertTrue(mensagens_gaspar.eh_do_gaspar(db, {"from_me": True, "content": "Te retorno já"}))
        self.assertFalse(mensagens_gaspar.eh_do_gaspar(db, {"from_me": True, "content": "Mensagem aprovada pelo André"}))

    def test_aprovacao_registra_o_texto_final(self):
        from test_outbox_aprovacao import _MockDb as _MockDbOutbox

        db = _MockDbOutbox()
        db.collection(oa.COLLECTION)._docs["job-1"] = {
            "status": oa.STATUS_AGUARDANDO, "to_number": CHAT, "content": "Pode ser quinta às 9h?",
            "motivo": "m", "destinatario_nome": "Clínica", "origem": "objetivo_whatsapp", "ref_id": "obj-1",
        }
        self.assertEqual(oa.aprovar_rascunho(db, "job-1")["status"], "ok")
        registro = mensagens_gaspar.encontrar(db, {"from_me": True, "content": "Pode ser quinta às 9h?"})
        self.assertEqual((registro["origem"], registro["ref_id"]), ("objetivo_whatsapp", "obj-1"))


class TestSecretarioPrimeiraPessoa(unittest.TestCase):
    def setUp(self):
        for alvo, valor in (("hermes_core_logic._get_telegram_token", "tok"),
                            ("main._resolve_default_telegram_chat_id", "123"),
                            ("hermes_core_logic._send_telegram_message", None)):
            p = mock.patch(alvo, return_value=valor)
            p.start()
            self.addCleanup(p.stop)
        self.db = _MockDb()
        self.db.collection("system").document("settings").set({
            "whatsapp_secretario": {"enabled": True, "chats_allowlist": [CHAT], "max_trocas": 2},
        })

    def _llm(self, resposta="Estou em reunião agora, te retorno logo.", **extra):
        def llm(**kwargs):
            return {"resposta_para_contato": resposta, "resumo_recado": "recado",
                    "forcou_decisao": False, "assunto_sensivel": False, **extra}
        return llm

    def _receber(self, texto, llm=None, **extra):
        msg = {"chat_id": CHAT, "chat_name": "Carlos", "from_me": False, "content": texto,
               "wa_message_id": f"m-{texto[:6]}", **extra}
        return sec.processar_mensagem_secretario(self.db, msg, llm_runner=llm or self._llm())

    def _enviadas(self):
        return [d.to_dict()["content"] for d in self.db.collection(oa.COLLECTION).stream()]

    def _conversa(self):
        return self.db.collection(sec.COLLECTION_CONVERSAS).document(CHAT).get().to_dict()

    def test_prompt_em_primeira_pessoa_com_as_regras_do_dono(self):
        prompt = sec.montar_system_instruction_secretario(historico=[])
        self.assertIn("PRIMEIRA PESSOA", prompt)
        self.assertNotIn("Gaspar Bot", prompt)
        for regra in ("perguntou_se_robo", "NUNCA sugira ligação", "Tininha", "não paga"):
            with self.subTest(regra=regra):
                self.assertIn(regra, prompt)

    def test_resposta_sai_sem_assinatura_e_o_eco_nao_conta_como_o_andre(self):
        self._receber("Oi André")
        self.assertEqual(self._enviadas(), ["Estou em reunião agora, te retorno logo."])
        sec.processar_mensagem_secretario(self.db, {"chat_id": CHAT, "from_me": True,
                                                    "content": "Estou em reunião agora, te retorno logo."})
        self.assertEqual(self._conversa()["estado"], sec.ESTADO_EM_ATENDIMENTO)

    def test_assinatura_que_o_modelo_escrever_e_removida(self):
        self._receber("Oi André", llm=self._llm("**Gaspar Bot:** Já te respondo."))
        self.assertEqual(self._enviadas(), ["Já te respondo."])

    def test_resposta_barrada_vira_a_resposta_padrao(self):
        self._receber("Oi André", llm=self._llm("Sou o assistente do André, pode me ligar?"))
        self.assertEqual(self._enviadas(), [sec._RESPOSTA_CONTINGENCIA_INICIO])

    def test_pergunta_se_e_robo_nao_responde_e_chama_o_andre(self):
        res = self._receber("Isso é um robô?", llm=self._llm("Não", perguntou_se_robo=True))
        self.assertEqual(res["status"], "perguntou_se_robo")
        self.assertEqual(self._enviadas(), [])
        self.assertEqual(self._conversa()["estado"], sec.ESTADO_ESCALADO)
        itens = [d.to_dict() for d in self.db.collection("atencao").stream()]
        self.assertEqual(itens[0]["tipo"], sec.TIPO_ATENCAO_PERGUNTOU_SE_ROBO)

    def test_fica_calado_depois_que_o_andre_assume(self):
        self._receber("Oi André")
        sec.processar_mensagem_secretario(self.db, {"chat_id": CHAT, "from_me": True, "content": "Fala, Carlos!"})
        self.assertEqual(self._conversa()["estado"], sec.ESTADO_ASSUMIDO_POR_ANDRE)
        res = self._receber("Beleza, então me diz depois")
        self.assertEqual(res["status"], "silencio")
        self.assertEqual(len(self._enviadas()), 1)

    def test_fica_calado_depois_de_escalar_e_volta_depois_do_prazo(self):
        for texto in ("um", "dois", "três"):
            self._receber(texto)
        self.assertEqual(self._conversa()["estado"], sec.ESTADO_ESCALADO)
        self.assertEqual(self._receber("quatro")["status"], "silencio")
        self._conversa_doc = self.db.collection(sec.COLLECTION_CONVERSAS)._docs[CHAT]
        self._conversa_doc["silencio_ate"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
        self.assertEqual(self._receber("cinco")["status"], "ok")

    def test_ignora_mensagem_antiga_e_conversa_com_objetivo_ativo(self):
        velha = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=11)
        self.assertIsNone(self._receber("antiga", timestamp=velha))
        with mock.patch("objetivos_whatsapp.objetivo_ativo_do_chat", return_value={"id": "o1"}):
            self.assertIsNone(self._receber("com objetivo"))
        self.assertEqual(self._enviadas(), [])


if __name__ == "__main__":
    unittest.main()
