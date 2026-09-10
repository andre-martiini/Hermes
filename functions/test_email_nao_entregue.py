"""DEV-2026-0004 sub-entrega 2/9: testes do detector de e-mails não entregues
(item `email_nao_entregue` na fila de atenção).

Reaproveita `MockDb`/`MockDoc`/`MockQuery` de test_atencao.py (mesmo padrão
usado pelos demais detectores de atencao.py) para o lado Firestore, e um fake
Gmail dedicado para o lado da API (thread com metadata From/To + fetch do
corpo completo só da mensagem de devolução).
"""
import base64
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, '.')

from atencao import (
    COLLECTION,
    ESTADO_ABERTO,
    ESTADO_RESOLVIDO,
    PRIORIDADE_ALTA,
    TIPO_EMAIL_NAO_ENTREGUE,
    avaliar_emails_nao_entregues,
    resolver_item,
)
from email_action_linker import (
    _extract_bounce_recipient,
    _extract_bounce_reason,
    _is_delayed_not_failed,
    detectar_emails_nao_entregues,
)
from test_atencao import MockDb


class _Req:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class _FakeGmailBounce:
    """threads_by_id: thread_id -> lista de mensagens (id/internalDate/payload
    com headers From e, quando aplicável, To). full_bodies: message_id ->
    payload completo, só consultado para a mensagem já reconhecida como
    devolução (mesma economia de chamadas que o código de produção faz)."""

    def __init__(self, threads_by_id, full_bodies=None, own_email="andre@ufjf.br", fail_get_profile=False):
        self.threads_by_id = threads_by_id
        self.full_bodies = full_bodies or {}
        self.own_email = own_email
        self.fail_get_profile = fail_get_profile

    def users(self):
        return self

    def threads(self):
        return self

    def messages(self):
        return self

    def getProfile(self, **kwargs):
        if self.fail_get_profile:
            raise RuntimeError("token refresh race (simulado)")
        return _Req({"emailAddress": self.own_email})

    def get(self, **kwargs):
        if kwargs.get("format") == "full":
            msg_id = kwargs["id"]
            return _Req({"id": msg_id, "payload": self.full_bodies.get(msg_id, {"headers": []})})
        thread_id = kwargs["id"]
        return _Req({"messages": self.threads_by_id.get(thread_id, [])})


def _msg(msg_id, internal_date, remetente, destinatario=None):
    headers = [{"name": "From", "value": remetente}]
    if destinatario:
        headers.append({"name": "To", "value": destinatario})
    return {"id": msg_id, "internalDate": internal_date, "payload": {"headers": headers}}


def _full_body(text_body: str) -> dict:
    encoded = base64.urlsafe_b64encode(text_body.encode("utf-8")).decode("ascii").rstrip("=")
    return {"headers": [], "mimeType": "text/plain", "body": {"data": encoded}}


SABRINA_BOUNCE_BODY = (
    "Delivery to the following recipient failed permanently:\n\n"
    "     sabrina.panceri@example.com\n\n"
    "Technical details of permanent failure:\n"
    "The error that the other server returned was:\n"
    "550 5.1.1 <sabrina.panceri@example.com>: Recipient address rejected: User unknown"
)

POLICY_BOUNCE_BODY = (
    "Your message couldn't be delivered.\n"
    "550-5.7.1 [193.61.71.6] The sender's IP address has been blocked\n"
    "550 5.7.1 by the recipient's policy -- contact your mail administrator."
)


class TestDetectarEmailsNaoEntregues(unittest.TestCase):
    def _settings(self, enabled=True):
        return {"system": {"settings": {"atencao": {"email_nao_entregue": {"enabled": enabled}}}}}

    def test_desligado_por_padrao_nao_grava_nada(self):
        data = self._settings(enabled=False)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        gmail = _FakeGmailBounce({"t1": [
            _msg("m1", "1", "Sabrina Panceri <sabrina.panceri@example.com>"),
            _msg("m2", "2", "André <andre@ufjf.br>", destinatario="Sabrina Panceri <sabrina.panceri@example.com>"),
            _msg("m3", "3", "Mail Delivery Subsystem <mailer-daemon@googlemail.com>"),
        ]})
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(itens, [])
        doc = db.collection(COLLECTION).document("email_nao_entregue:sabrina.panceri@example.com").get()
        self.assertFalse(doc.exists)

    def test_detecta_devolucao_unica_e_extrai_motivo_e_codigo(self):
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        gmail = _FakeGmailBounce(
            threads_by_id={"t1": [
                _msg("m1", "1000", "Sabrina Panceri <sabrina.panceri@example.com>"),
                _msg("m2", "2000", "André <andre@ufjf.br>", destinatario="Sabrina Panceri <sabrina.panceri@example.com>"),
                _msg("m3", "1757462400000", "Mail Delivery Subsystem <mailer-daemon@googlemail.com>"),
            ]},
            full_bodies={"m3": _full_body(SABRINA_BOUNCE_BODY)},
        )
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["origem"], "email")
        self.assertEqual(item["tipo"], TIPO_EMAIL_NAO_ENTREGUE)
        self.assertEqual(item["prioridade"], PRIORIDADE_ALTA)
        self.assertEqual(item["evidencia"]["destinatario"], "sabrina.panceri@example.com")
        self.assertEqual(item["evidencia"]["codigo_smtp"], "5.1.1")
        self.assertIn("Recipient address rejected", item["evidencia"]["motivo"])
        doc = db.collection(COLLECTION).document("email_nao_entregue:sabrina.panceri@example.com").get()
        self.assertTrue(doc.exists)

    def test_codigo_5_7_x_sugere_revisar_enviar_email_como(self):
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        gmail = _FakeGmailBounce(
            threads_by_id={"t1": [
                _msg("m1", "1000", "FAPES <contato@fapes.es.gov.br>"),
                _msg("m2", "2000", "André Martini <andre.alt@ifes.edu.br>",
                     destinatario="FAPES <contato@fapes.es.gov.br>"),
                _msg("m3", "3000", "postmaster@fapes.es.gov.br"),
            ]},
            full_bodies={"m3": _full_body(POLICY_BOUNCE_BODY)},
        )
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["evidencia"]["codigo_smtp"], "5.7.1")
        self.assertIn("Enviar e-mail como", item["sugestao"])
        self.assertIn("andre.alt@ifes.edu.br", item["sugestao"])

    def test_duas_devolucoes_do_mesmo_destinatario_viram_um_item_so(self):
        """Critério de aceite da demanda: 'Mayana x2 agrupadas'."""
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
            "s2": {"google_message_id": "m4", "gmail_thread_id": "t2", "status": "applied_reactivated"},
        }
        db = MockDb(data)
        mayana_body = SABRINA_BOUNCE_BODY.replace("sabrina.panceri@example.com", "mayana@ifto.edu.br")
        gmail = _FakeGmailBounce(
            threads_by_id={
                "t1": [
                    _msg("m1", "1000", "Mayana <mayana@ifto.edu.br>"),
                    _msg("m2", "2000", "André <andre@ufjf.br>", destinatario="Mayana <mayana@ifto.edu.br>"),
                    _msg("m3", "3000", "mailer-daemon@googlemail.com"),
                ],
                "t2": [
                    _msg("m4", "4000", "Mayana <mayana@ifto.edu.br>"),
                    _msg("m5", "5000", "André <andre@ufjf.br>", destinatario="Mayana <mayana@ifto.edu.br>"),
                    _msg("m6", "6000", "mailer-daemon@googlemail.com"),
                ],
            },
            full_bodies={
                "m3": _full_body(mayana_body),
                "m6": _full_body(mayana_body),
            },
        )
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["evidencia"]["destinatario"], "mayana@ifto.edu.br")

        # Uma segunda passada (ex.: próxima execução agendada, 30 min depois)
        # com a mesma pessoa não duplica o item -- a chave_dedupe é a mesma.
        itens2 = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(len(itens2), 1)
        todos = [d for d in db.collection(COLLECTION).stream() if d.id.startswith("email_nao_entregue:mayana")]
        self.assertEqual(len(todos), 1)

    def test_devolucao_sem_mensagem_anterior_na_thread_e_ignorada(self):
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        gmail = _FakeGmailBounce(threads_by_id={"t1": [
            _msg("m1", "1000", "mailer-daemon@googlemail.com"),
        ]})
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(itens, [])

    def test_to_com_varios_destinatarios_resolve_pelo_corpo_da_devolucao(self):
        """Achado da revisão adversarial: um `To` com mais de um endereço
        quebrava `email.utils.parseaddr` (pensado para um endereço só) e a
        devolução era descartada em silêncio. Com o endereço nomeado no
        próprio corpo da devolução, o item é criado do mesmo jeito."""
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        gmail = _FakeGmailBounce(
            threads_by_id={"t1": [
                _msg("m1", "1000", "Comissão <comissao@ifes.edu.br>"),
                _msg("m2", "2000", "André <andre@ufjf.br>",
                     destinatario="Sabrina Panceri <sabrina.panceri@example.com>, Outro <outro@example.com>"),
                _msg("m3", "3000", "mailer-daemon@googlemail.com"),
            ]},
            full_bodies={"m3": _full_body(SABRINA_BOUNCE_BODY)},
        )
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["evidencia"]["destinatario"], "sabrina.panceri@example.com")

    def test_to_com_varios_destinatarios_sem_pista_no_corpo_e_ignorada(self):
        """Sem endereço nomeado no corpo e mais de um destinatário no `To`,
        não dá para saber quem falhou com confiança -- a devolução é pulada
        em vez de arriscar atribuir à pessoa errada."""
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        gmail = _FakeGmailBounce(
            threads_by_id={"t1": [
                _msg("m1", "1000", "Comissão <comissao@ifes.edu.br>"),
                _msg("m2", "2000", "André Martini <andre.alt@ifes.edu.br>",
                     destinatario="FAPES <contato@fapes.es.gov.br>, Outro <outro@example.com>"),
                _msg("m3", "3000", "postmaster@fapes.es.gov.br"),
            ]},
            full_bodies={"m3": _full_body(POLICY_BOUNCE_BODY)},
        )
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(itens, [])

    def test_avisos_de_devolucao_consecutivos_nao_atribuem_a_andre(self):
        """Achado da revisão adversarial: quando o servidor manda um aviso de
        atraso antes da falha definitiva (as duas mensagens vêm do mesmo
        remetente automático), a versão ingênua ('mensagem anterior = quem
        disparou') atribuiria a devolução ao `To` do PRÓPRIO aviso de atraso
        -- que aponta de volta para o André, gerando um item sem sentido
        'e-mail não entregue a andre@ufjf.br'. A busca deve pular avisos
        automáticos consecutivos e achar a mensagem real do André."""
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        mayana_body = SABRINA_BOUNCE_BODY.replace("sabrina.panceri@example.com", "mayana@ifto.edu.br")
        gmail = _FakeGmailBounce(
            threads_by_id={"t1": [
                _msg("m1", "1000", "André <andre@ufjf.br>", destinatario="Mayana <mayana@ifto.edu.br>"),
                _msg("m2", "2000", "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
                     destinatario="andre@ufjf.br"),
                _msg("m3", "3000", "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
                     destinatario="andre@ufjf.br"),
            ]},
            full_bodies={
                "m2": _full_body("Delayed: vamos continuar tentando por mais algumas horas."),
                "m3": _full_body(mayana_body),
            },
        )
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["evidencia"]["destinatario"], "mayana@ifto.edu.br")
        destinatarios = {i["evidencia"]["destinatario"] for i in itens}
        self.assertNotIn("andre@ufjf.br", destinatarios)

    def test_aviso_de_atraso_sozinho_nao_gera_item(self):
        """Achado da segunda revisão adversarial: um aviso de ATRASO (a
        entrega ainda pode dar certo) não é uma falha definitiva -- não deve
        virar item de prioridade alta na fila de atenção. Thread sem nenhuma
        falha definitiva depois, só o aviso de atraso."""
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        gmail = _FakeGmailBounce(threads_by_id={"t1": [
            _msg("m1", "1000", "André <andre@ufjf.br>", destinatario="Mayana <mayana@ifto.edu.br>"),
            _msg("m2", "2000", "Mail Delivery Subsystem <mailer-daemon@googlemail.com>", destinatario="andre@ufjf.br"),
        ]}, full_bodies={
            "m2": _full_body("Delivery incomplete. We'll keep trying to send your message."),
        })
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(itens, [])

    def test_resposta_de_terceiro_entre_envio_e_devolucao_nao_atribui_ao_terceiro(self):
        """Achado da segunda revisão adversarial: mesmo só pulando remetentes
        automáticos, a busca ingênua podia pegar a resposta de um TERCEIRO
        (não automática, mas também não do André) que por acaso ficou entre
        o envio original e a devolução atrasada de outro destinatário. Usar
        o e-mail da própria conta (`getProfile`) para preferir a mensagem do
        André evita isso."""
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        gmail = _FakeGmailBounce(
            threads_by_id={"t1": [
                _msg("m1", "1000", "André <andre@ufjf.br>", destinatario="Sabrina Panceri <sabrina.panceri@example.com>"),
                _msg("m2", "2000", "Gabriela <gabriela@ifes.edu.br>", destinatario="André <andre@ufjf.br>"),
                _msg("m3", "3000", "Mail Delivery Subsystem <mailer-daemon@googlemail.com>", destinatario="andre@ufjf.br"),
            ]},
            # corpo sem endereço nomeado -- força a resolução pelo cabeçalho
            # `To`, que é onde o bug apareceria (pegando o `To` da resposta
            # da Gabriela em vez do envio original do André).
            full_bodies={"m3": _full_body("550 5.1.1 Recipient address rejected: User unknown")},
        )
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["evidencia"]["destinatario"], "sabrina.panceri@example.com")

    def test_falha_ao_obter_email_da_conta_pula_devolucoes_em_vez_de_arriscar(self):
        """Achado da terceira revisão adversarial: sem conseguir descobrir
        qual é o e-mail da conta (ex.: falha transitória no `getProfile`),
        não dá para diferenciar uma mensagem do André de uma resposta de
        terceiro -- a devolução deve ser pulada, não atribuída com a
        heurística ingênua (que reintroduziria o bug da segunda revisão)."""
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        gmail = _FakeGmailBounce(
            threads_by_id={"t1": [
                _msg("m1", "1000", "André <andre@ufjf.br>", destinatario="Sabrina Panceri <sabrina.panceri@example.com>"),
                _msg("m2", "2000", "Gabriela <gabriela@ifes.edu.br>", destinatario="André <andre@ufjf.br>"),
                _msg("m3", "3000", "Mail Delivery Subsystem <mailer-daemon@googlemail.com>", destinatario="andre@ufjf.br"),
            ]},
            full_bodies={"m3": _full_body("550 5.1.1 Recipient address rejected: User unknown")},
            fail_get_profile=True,
        )
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(itens, [])

    def test_janela_de_diagnostico_ignora_palavra_chave_de_atraso_na_mensagem_original_citada(self):
        """Achado da terceira revisão adversarial: o corpo de uma devolução
        real costuma citar a mensagem original mais abaixo. Sem código SMTP
        reconhecível em lugar nenhum (força o caminho de palavra-chave), uma
        frase de atraso dentro dessa citação -- bem além da janela onde o
        servidor coloca sua própria explicação -- não pode fazer uma falha
        definitiva real ser tratada como simples atraso."""
        linhas_preenchimento = "\n".join(
            f"Detalhe técnico {i} do servidor de origem, sem código reconhecível." for i in range(19)
        )
        corpo = (
            "Sua mensagem não pôde ser entregue por um erro definitivo do servidor.\n"
            f"{linhas_preenchimento}\n"
            "--- Mensagem original ---\n"
            "De: André <andre@ufjf.br>\n"
            "Vamos continuar tentando marcar aquela reunião na próxima semana."
        )
        codigo, _motivo = _extract_bounce_reason(corpo)
        self.assertIsNone(codigo)
        self.assertFalse(_is_delayed_not_failed(corpo, codigo))
        # confirma que a frase de atraso está mesmo fora da janela examinada
        # (senão o teste não provaria nada -- ver `_BOUNCE_DIAGNOSTIC_WINDOW_LINES`).
        linhas_nao_vazias = [l for l in corpo.split("\n") if l.strip()]
        self.assertNotIn(
            "vamos continuar tentando",
            "\n".join(linhas_nao_vazias[:20]).lower(),
        )

    def test_devolucao_nova_no_mesmo_dia_reabre_item_ja_resolvido(self):
        """Achado da revisão adversarial: com granularidade só de dia no
        `prazo`, resolver o item pela manhã esconderia uma devolução nova e
        não relacionada à tarde do mesmo dia. `_internal_date_to_sp_iso` usa
        segundo, não dia -- a segunda devolução deve reabrir o item."""
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        primeiro_ts = int(datetime(2026, 9, 10, 11, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        gmail1 = _FakeGmailBounce(
            threads_by_id={"t1": [
                _msg("m1", str(primeiro_ts - 2000), "Sabrina Panceri <sabrina.panceri@example.com>"),
                _msg("m2", str(primeiro_ts - 1000), "André <andre@ufjf.br>",
                     destinatario="Sabrina Panceri <sabrina.panceri@example.com>"),
                _msg("m3", str(primeiro_ts), "Mail Delivery Subsystem <mailer-daemon@googlemail.com>"),
            ]},
            full_bodies={"m3": _full_body(SABRINA_BOUNCE_BODY)},
        )
        itens1 = detectar_emails_nao_entregues(db, gmail1)
        self.assertEqual(len(itens1), 1)

        chave = "email_nao_entregue:sabrina.panceri@example.com"
        resultado = resolver_item(db, chave, ESTADO_RESOLVIDO, desfecho="Reenviei manualmente por outro canal.")
        self.assertNotIn("erro", resultado)
        self.assertEqual(db.collection(COLLECTION).document(chave).get().to_dict()["estado"], ESTADO_RESOLVIDO)

        # Nova devolução, mesma pessoa, mesmo dia (+6h) -- não relacionada à
        # primeira (ex.: André tentou reenviar manualmente e bateu de novo).
        segundo_ts = primeiro_ts + 6 * 3600 * 1000
        gmail2 = _FakeGmailBounce(
            threads_by_id={"t1": [
                _msg("m1", str(primeiro_ts - 2000), "Sabrina Panceri <sabrina.panceri@example.com>"),
                _msg("m2", str(primeiro_ts - 1000), "André <andre@ufjf.br>",
                     destinatario="Sabrina Panceri <sabrina.panceri@example.com>"),
                _msg("m3", str(primeiro_ts), "Mail Delivery Subsystem <mailer-daemon@googlemail.com>"),
                _msg("m4", str(segundo_ts), "André <andre@ufjf.br>",
                     destinatario="Sabrina Panceri <sabrina.panceri@example.com>"),
                _msg("m5", str(segundo_ts + 1000), "Mail Delivery Subsystem <mailer-daemon@googlemail.com>"),
            ]},
            full_bodies={
                "m3": _full_body(SABRINA_BOUNCE_BODY),
                "m5": _full_body(SABRINA_BOUNCE_BODY),
            },
        )
        itens2 = detectar_emails_nao_entregues(db, gmail2)
        self.assertEqual(len(itens2), 1)
        self.assertEqual(db.collection(COLLECTION).document(chave).get().to_dict()["estado"], ESTADO_ABERTO)

    def test_thread_sem_devolucao_nao_gera_item(self):
        data = self._settings(enabled=True)
        data["email_action_suggestions"] = {
            "s1": {"google_message_id": "m1", "gmail_thread_id": "t1", "status": "applied"},
        }
        db = MockDb(data)
        gmail = _FakeGmailBounce(threads_by_id={"t1": [
            _msg("m1", "1000", "Gabriela <gabriela@ifes.edu.br>"),
            _msg("m2", "2000", "André <andre@ufjf.br>", destinatario="Gabriela <gabriela@ifes.edu.br>"),
            _msg("m3", "3000", "Gabriela <gabriela@ifes.edu.br>"),
        ]})
        itens = detectar_emails_nao_entregues(db, gmail)
        self.assertEqual(itens, [])


class TestExtractBounceReason(unittest.TestCase):
    def test_extrai_codigo_e_linha_de_motivo(self):
        codigo, motivo = _extract_bounce_reason(SABRINA_BOUNCE_BODY)
        self.assertEqual(codigo, "5.1.1")
        self.assertIn("Recipient address rejected", motivo)

    def test_multilinha_550_hifen_extrai_codigo(self):
        codigo, _motivo = _extract_bounce_reason(POLICY_BOUNCE_BODY)
        self.assertEqual(codigo, "5.7.1")

    def test_corpo_vazio_nao_quebra(self):
        codigo, motivo = _extract_bounce_reason("")
        self.assertIsNone(codigo)
        self.assertEqual(motivo, "")

    def test_sem_codigo_smtp_cai_para_primeiras_linhas(self):
        codigo, motivo = _extract_bounce_reason(
            "Mensagem não pôde ser entregue.\nMotivo desconhecido pelo servidor."
        )
        self.assertIsNone(codigo)
        self.assertIn("Mensagem não pôde ser entregue", motivo)

    def test_nao_confunde_octeto_de_ip_ou_versao_de_cabecalho_com_codigo_smtp(self):
        """Achado da revisão adversarial: o padrão solto original casava com
        `10.2.30.41` (IP) ou `X-Mailer: 5.2.1` (versão de cabeçalho) -- exigir
        o código básico de 3 dígitos antes evita esses falsos positivos."""
        corpo = (
            "Received: from mail.internal (unknown [10.2.30.41])\n"
            "\tby mx.example.com with ESMTP id abc123\n"
            "X-Mailer: 5.2.1\n\n"
            "The response from the remote server was:\n"
            "550 5.1.1 <sabrina.panceri@example.com>: Recipient address rejected: User unknown"
        )
        codigo, motivo = _extract_bounce_reason(corpo)
        self.assertEqual(codigo, "5.1.1")
        self.assertIn("Recipient address rejected", motivo)

    def test_reconhece_campo_status_de_um_dsn_sem_codigo_basico_de_3_digitos(self):
        """Achado da segunda revisão adversarial: o campo `Status:` de um DSN
        (RFC 3464) ecoado no corpo legível não tem o código básico de 3
        dígitos na frente -- exigir essa âncora universalmente faria perder
        esse formato, comum o bastante para merecer um segundo padrão."""
        codigo, motivo = _extract_bounce_reason("Your message wasn't delivered.\n\nStatus: 5.1.1\nAction: failed\n")
        self.assertEqual(codigo, "5.1.1")

    def test_status_com_codigo_transitorio_4xx_e_reconhecido(self):
        codigo, _motivo = _extract_bounce_reason("Status: 4.4.1\nAction: delayed\n")
        self.assertEqual(codigo, "4.4.1")


class TestIsDelayedNotFailed(unittest.TestCase):
    def test_codigo_4xx_e_atraso(self):
        self.assertTrue(_is_delayed_not_failed("qualquer corpo", "4.4.1"))

    def test_codigo_5xx_nao_e_atraso(self):
        self.assertFalse(_is_delayed_not_failed("qualquer corpo", "5.1.1"))

    def test_sem_codigo_usa_palavra_chave_do_corpo(self):
        self.assertTrue(_is_delayed_not_failed("We'll keep trying to deliver your message.", None))

    def test_sem_codigo_e_sem_palavra_chave_nao_e_atraso(self):
        self.assertFalse(_is_delayed_not_failed("Delivery failed permanently.", None))


class TestExtractBounceRecipient(unittest.TestCase):
    def test_extrai_endereco_colado_logo_apos_o_codigo_smtp(self):
        corpo = "550 5.1.1 <contato@fapes.es.gov.br>: Recipient address rejected: User unknown"
        self.assertEqual(_extract_bounce_recipient(corpo), "contato@fapes.es.gov.br")

    def test_extrai_endereco_com_dois_pontos_entre_codigo_e_colchete(self):
        """Achado da terceira revisão adversarial: a versão que exigia só
        espaço/tab perdia esta variação de pontuação real."""
        corpo = "550 5.1.1: <contato@fapes.es.gov.br> Recipient address rejected"
        self.assertEqual(_extract_bounce_recipient(corpo), "contato@fapes.es.gov.br")

    def test_extrai_endereco_com_hifen_entre_codigo_e_colchete(self):
        corpo = "5.1.1 - <contato@fapes.es.gov.br> Recipient address rejected"
        self.assertEqual(_extract_bounce_recipient(corpo), "contato@fapes.es.gov.br")

    def test_extrai_endereco_da_frase_gmail_delivery_failed(self):
        self.assertEqual(_extract_bounce_recipient(SABRINA_BOUNCE_BODY), "sabrina.panceri@example.com")

    def test_corpo_sem_endereco_reconhecivel_devolve_none(self):
        self.assertIsNone(_extract_bounce_recipient("Sua mensagem não pôde ser entregue por motivos desconhecidos."))

    def test_corpo_vazio_devolve_none(self):
        self.assertIsNone(_extract_bounce_recipient(""))

    def test_nao_pega_endereco_de_contato_de_ajuda_distante_do_codigo(self):
        """Achado da segunda revisão adversarial: com folga larga entre o
        código e o endereço (a versão original aceitava até 20 caracteres
        quaisquer no meio), um endereço de contato/abuse mencionado perto do
        código -- mas sem ser o diagnóstico em si -- podia ser confundido com
        o destinatário real. Exigir só espaço/tab entre os dois evita isso: a
        função corretamente não acha nada aqui (a frase do Gmail também não
        aparece), então o chamador cai para o cabeçalho `To`."""
        corpo = (
            "Please note error 5.7.1. For help contact <abuse@example.com>.\n"
            "The actual recipient right@example.com was not reachable."
        )
        self.assertIsNone(_extract_bounce_recipient(corpo))


class TestAvaliarEmailsNaoEntreguesPuro(unittest.TestCase):
    def test_agrupa_mesmo_destinatario_no_mesmo_lote_mantendo_a_mais_recente(self):
        from datetime import date

        bounces = [
            {"destinatario": "mayana@ifto.edu.br", "destinatario_nome": "Mayana", "data": "2026-09-08",
             "motivo": "primeira devolução", "codigo_smtp": "4.4.1", "thread_id": "t1", "mensagem_id": "m3"},
            {"destinatario": "mayana@ifto.edu.br", "destinatario_nome": "Mayana", "data": "2026-09-09",
             "motivo": "segunda devolução", "codigo_smtp": "5.1.1", "thread_id": "t2", "mensagem_id": "m6"},
        ]
        itens = avaliar_emails_nao_entregues(bounces, date(2026, 9, 10))
        self.assertEqual(len(itens), 1)
        self.assertIn("segunda devolução", itens[0]["resumo"])
        self.assertEqual(itens[0]["chave_dedupe"], "email_nao_entregue:mayana@ifto.edu.br")

    def test_destinatario_vazio_e_ignorado(self):
        from datetime import date

        itens = avaliar_emails_nao_entregues([{"destinatario": "  "}], date(2026, 9, 10))
        self.assertEqual(itens, [])


if __name__ == '__main__':
    unittest.main()
