import unittest
from datetime import datetime, timedelta, timezone

from autonomy.followup_guard import ADIAR, ENVIAR, SUPRIMIR, revalidar_followup

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def comp(**kw):
    base = {"texto": "Te envio o relatório amanhã", "prometido_em": T0, "estado": "vencida"}
    base.update(kw)
    return base


def ctx(mensagens=(), rascunho=False, atencao=None):
    return {"mensagens": list(mensagens), "rascunho_pendente": rascunho, "estado_atencao": atencao}


def msg(from_me, horas, content="oi", media=None):
    return {"from_me": from_me, "timestamp": T0 + timedelta(hours=horas), "content": content, "media": media}


class RevalidarFollowupTest(unittest.TestCase):
    def test_sem_impedimento_envia(self):
        d = revalidar_followup(comp(), ctx([msg(True, -1, "Te envio o relatório amanhã")]))
        self.assertEqual((d.acao, d.motivo), (ENVIAR, "sem_impedimento"))

    def test_compromisso_encerrado_suprime(self):
        for estado in ("cumprida", "cancelada", None):
            self.assertEqual(revalidar_followup(comp(estado=estado), ctx()).acao, SUPRIMIR)

    def test_dono_ja_tratou_e_rascunho_suprimem(self):
        self.assertEqual(revalidar_followup(comp(), ctx(atencao="resolvido")).motivo, "dono_ja_tratou")
        self.assertEqual(revalidar_followup(comp(), ctx(rascunho=True)).motivo, "rascunho_existente")

    def test_cumprimento_firme_suprime(self):
        d = revalidar_followup(comp(), ctx([msg(True, 3, "Segue o relatório")]))
        self.assertEqual((d.acao, d.motivo), (SUPRIMIR, "ja_cumprido"))

    def test_intervencao_nao_firme_adia(self):
        for texto in ("Vou ver o relatório", "Oi, tudo bem? Como foi o almoço de hoje com o pessoal do trabalho?"):
            d = revalidar_followup(comp(), ctx([msg(True, 3, texto)]))
            self.assertEqual((d.acao, d.motivo), (ADIAR, "intervencao_humana"), texto)

    def test_midia_sozinha_nao_suprime(self):
        d = revalidar_followup(comp(), ctx([msg(True, 3, "", {"filename": "x.pdf"})]))
        self.assertEqual(d.acao, ADIAR)

    def test_novo_dado_da_contraparte_adia(self):
        d = revalidar_followup(comp(), ctx([msg(False, 2, "Preciso do relatório até hoje")]))
        self.assertEqual((d.acao, d.motivo), (ADIAR, "novo_dado_da_contraparte"))

    def test_mensagem_anterior_a_promessa_ignorada(self):
        d = revalidar_followup(comp(), ctx([msg(False, -5), msg(True, -4, "Segue o relatório")]))
        self.assertEqual(d.acao, ENVIAR)

    def test_contexto_invalido_adia(self):
        casos = [
            (None, ctx()), (comp(), None), (comp(), {}),
            (comp(prometido_em=datetime(2026, 10, 20)), ctx()),
            (comp(), ctx([{"from_me": "sim", "timestamp": T0}])),
            (comp(), ctx([{"from_me": True, "timestamp": "ontem"}])),
            (comp(), ctx([None])),
            (comp(), {"mensagens": [], "rascunho_pendente": None}),
        ]
        for c, x in casos:
            d = revalidar_followup(c, x)
            self.assertEqual((d.acao, d.motivo), (ADIAR, "contexto_invalido"), (c, x))

    def test_estado_atencao_desconhecido_adia(self):
        for e in ("Resolvido", "xyz", 5, ["x"]):
            self.assertEqual(revalidar_followup(comp(), ctx(atencao=e)).acao, ADIAR, e)
        for e in ("delegado_ao_agente", "aguardando_andre"):
            self.assertEqual(revalidar_followup(comp(), ctx(atencao=e)).motivo, "atencao_em_tratamento")
        self.assertEqual(revalidar_followup(comp(), ctx(atencao="aberto")).acao, ENVIAR)

    def test_timestamp_igual_conta_exceto_propria_promessa(self):
        self.assertEqual(revalidar_followup(comp(), ctx([msg(False, 0)])).acao, ADIAR)
        self.assertEqual(revalidar_followup(comp(), ctx([msg(True, 0, "Segue o relatório")])).motivo, "ja_cumprido")
        propria = msg(True, 0, "Te envio o relatório amanhã")
        propria["wa_message_id"] = "m1"
        self.assertEqual(revalidar_followup(comp(mensagem_id="m1"), ctx([propria])).acao, ENVIAR)

    def test_tzinfo_sem_offset_e_tipos_estranhos_adiam(self):
        from datetime import tzinfo

        class Z(tzinfo):
            def utcoffset(self, dt): return None
            def dst(self, dt): return None
            def tzname(self, dt): return "Z"

        ruim = datetime(2026, 10, 21, tzinfo=Z())
        self.assertEqual(revalidar_followup(comp(prometido_em=ruim), ctx()).acao, ADIAR)
        self.assertEqual(revalidar_followup(comp(), ctx([{"from_me": True, "timestamp": ruim}])).acao, ADIAR)
        self.assertEqual(revalidar_followup(comp(estado=["x"]), ctx()).acao, SUPRIMIR)

    def test_ordem_das_mensagens_irrelevante(self):
        a = [msg(True, 3, "Segue o relatório"), msg(False, 2)]
        self.assertEqual(revalidar_followup(comp(), ctx(a)).motivo, "ja_cumprido")
        self.assertEqual(revalidar_followup(comp(), ctx(a[::-1])).motivo, "ja_cumprido")


if __name__ == "__main__":
    unittest.main()
