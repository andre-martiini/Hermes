"""Leitura e consolidacao de WhatsApp pelo canal MCP.

O que estes testes protegem, em ordem:

1. **A allowlist.** Conversa de WhatsApp e o dado mais sensivel do Hermes e
   envolve terceiros que nao sabem que ha um agente lendo. Toda porta que
   devolve conteudo tem de recusar chat fora da lista — e a recusa precisa
   valer inclusive no caminho indireto, quando `consolidar` monta o recorte por
   periodo em vez de receber ids prontos.
2. **O teto de mensagens por job**, que o trigger tambem impoe: recusar aqui
   produz mensagem util em vez de um job que falha depois.
3. **O transcript literal fora da resposta por padrao** — e a conversa palavra
   por palavra.
"""

import unittest

from tools import whatsapp_tools as wa

MONITORADO = "5527999999999@c.us"
LIVRE = "5511888888888@c.us"


# --------------------------------------------------------------------------
# Firestore de mentira, so o suficiente para o que o modulo usa
# --------------------------------------------------------------------------

class _Snap:
    def __init__(self, id_, dados):
        self.id = id_
        self._d = dados
        self.exists = dados is not None

    def to_dict(self):
        return dict(self._d) if self._d is not None else {}


class _DocRef:
    def __init__(self, colecao, id_):
        self._col = colecao
        self.id = id_

    def get(self):
        return _Snap(self.id, self._col.dados.get(self.id))

    def set(self, valores, merge=False):
        if merge and self.id in self._col.dados:
            self._col.dados[self.id].update(valores)
        else:
            self._col.dados[self.id] = dict(valores)


class _Query:
    def __init__(self, colecao, docs):
        self._col = colecao
        self._docs = docs

    def where(self, campo, op, valor):
        def bate(par):
            atual = par[1].get(campo)
            if op == "==":
                return atual == valor
            if atual is None:
                return False
            if op == ">=":
                return atual >= valor
            if op == "<=":
                return atual <= valor
            return True
        return _Query(self._col, [p for p in self._docs if bate(p)])

    def order_by(self, campo, direction=None):
        ordenados = sorted(self._docs, key=lambda p: str(p[1].get(campo) or ""),
                           reverse=str(direction or "").upper().startswith("DESC"))
        return _Query(self._col, ordenados)

    def limit(self, n):
        return _Query(self._col, self._docs[:n])

    def stream(self):
        return [_Snap(i, d) for i, d in self._docs]


class _Colecao:
    def __init__(self, dados):
        self.dados = dict(dados)
        self._seq = 0

    def _pares(self):
        return list(self.dados.items())

    def where(self, *a):
        return _Query(self, self._pares()).where(*a)

    def order_by(self, *a, **k):
        return _Query(self, self._pares()).order_by(*a, **k)

    def limit(self, n):
        return _Query(self, self._pares()).limit(n)

    def stream(self):
        return _Query(self, self._pares()).stream()

    def document(self, doc_id=None):
        if doc_id is None:
            self._seq += 1
            doc_id = f"auto{self._seq}"
        return _DocRef(self, doc_id)


class _Db:
    def __init__(self, allowlist, chats=None, mensagens=None, consolidacoes=None):
        self._cols = {
            wa.COL_CHATS: _Colecao(chats or {}),
            wa.COL_MENSAGENS: _Colecao(mensagens or {}),
            wa.COL_CONSOLIDACOES: _Colecao(consolidacoes or {}),
            "system": _Colecao(
                {"settings": {"whatsapp_ingest": {"chats_allowlist": list(allowlist)}}}
            ),
        }

    def collection(self, nome):
        return self._cols.setdefault(nome, _Colecao({}))


class _Ctx:
    def __init__(self, db):
        self.db = db
        self.user_uid = "uid-teste"
        self.task_id = None


def _db_padrao():
    return _Db(
        allowlist=[MONITORADO],
        chats={
            MONITORADO: {"chat_id": MONITORADO, "chat_name": "Equipe", "is_group": True,
                         "last_activity_ts": "2026-08-20T10:00:00"},
            LIVRE: {"chat_id": LIVRE, "chat_name": "Pessoal", "is_group": False,
                    "last_activity_ts": "2026-08-25T10:00:00"},
        },
        mensagens={
            f"m{i}": {"id": f"m{i}", "chat_id": MONITORADO, "content": f"msg {i}",
                      "message_type": "chat", "author_name": "Fulano",
                      "timestamp": f"2026-08-2{i}T09:00:00"}
            for i in range(5)
        },
    )


# --------------------------------------------------------------------------


class TestAllowlistBloqueiaLeitura(unittest.TestCase):
    """Toda porta que devolve conteudo recusa chat fora da lista."""

    def setUp(self):
        self.ctx = _Ctx(_db_padrao())

    def test_ler_mensagens_de_chat_livre_e_recusado(self):
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa.ler_mensagens(self.ctx, {"chat_id": LIVRE})

    def test_consolidar_chat_livre_e_recusado(self):
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa.consolidar(self.ctx, {"chat_id": LIVRE, "message_ids": ["m1"]})

    def test_consolidar_por_periodo_tambem_e_recusado(self):
        """O caminho indireto nao pode ser uma porta dos fundos.

        Sem message_ids, `consolidar` monta o recorte chamando `ler_mensagens`.
        Se a checagem so existisse no caminho com ids explicitos, bastaria
        omitir os ids para consolidar conversa nao monitorada.
        """
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa.consolidar(self.ctx, {"chat_id": LIVRE, "desde": "2026-08-01"})

    def test_ler_consolidacao_por_chat_livre_e_recusado(self):
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa.ler_consolidacao(self.ctx, {"chat_id": LIVRE})

    def test_chat_id_vazio_e_recusado(self):
        for args in ({"chat_id": ""}, {}):
            with self.assertRaises(wa.WhatsAppNaoMonitorado):
                wa.ler_mensagens(self.ctx, args)

    def test_mensagem_de_recusa_orienta(self):
        with self.assertRaises(wa.WhatsAppNaoMonitorado) as erro:
            wa.ler_mensagens(self.ctx, {"chat_id": LIVRE})
        texto = str(erro.exception)
        self.assertIn("listar_conversas_whatsapp", texto)
        self.assertIn("Caixa de Entrada", texto)

    def test_chat_monitorado_passa(self):
        r = wa.ler_mensagens(self.ctx, {"chat_id": MONITORADO})
        self.assertEqual(r["chat_id"], MONITORADO)
        self.assertEqual(r["total"], 5)

    def test_allowlist_ausente_bloqueia_tudo(self):
        """Sem `system/settings`, o padrao e negar, nao liberar."""
        ctx = _Ctx(_Db(allowlist=[]))
        ctx.db._cols["system"] = _Colecao({})
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa.ler_mensagens(ctx, {"chat_id": MONITORADO})


class TestLeituraDeMensagens(unittest.TestCase):
    def setUp(self):
        self.ctx = _Ctx(_db_padrao())

    def test_ordem_cronologica(self):
        """A consulta vem decrescente para pegar as ultimas; a resposta inverte."""
        r = wa.ler_mensagens(self.ctx, {"chat_id": MONITORADO})
        quando = [m["quando"] for m in r["mensagens"]]
        self.assertEqual(quando, sorted(quando))

    def test_id_devolvido_e_o_que_consolidar_espera(self):
        r = wa.ler_mensagens(self.ctx, {"chat_id": MONITORADO})
        self.assertTrue(all(m["id"].startswith("m") for m in r["mensagens"]))

    def test_audio_sem_transcricao_e_sinalizado(self):
        """Antes de consolidar, audio tem texto vazio — sem aviso pareceria conversa vazia."""
        self.ctx.db._cols[wa.COL_MENSAGENS].dados["a1"] = {
            "id": "a1", "chat_id": MONITORADO, "message_type": "ptt", "content": "",
            "timestamp": "2026-08-26T09:00:00",
        }
        r = wa.ler_mensagens(self.ctx, {"chat_id": MONITORADO})
        self.assertEqual(r["midia_sem_transcricao"], 1)
        self.assertIn("transcrição", r["observacao"])

    def test_mensagem_propria_aparece_como_eu(self):
        self.ctx.db._cols[wa.COL_MENSAGENS].dados["p1"] = {
            "id": "p1", "chat_id": MONITORADO, "content": "ok", "from_me": True,
            "message_type": "chat", "timestamp": "2026-08-26T10:00:00",
        }
        r = wa.ler_mensagens(self.ctx, {"chat_id": MONITORADO})
        self.assertEqual([m["autor"] for m in r["mensagens"] if m["id"] == "p1"], ["eu"])


class TestListagem(unittest.TestCase):
    """Listar nome de conversa nao e ler conteudo — por isso enxerga alem da lista."""

    def setUp(self):
        self.ctx = _Ctx(_db_padrao())

    def test_padrao_traz_so_as_monitoradas(self):
        r = wa.listar_conversas(self.ctx, {})
        self.assertEqual([c["chat_id"] for c in r["conversas"]], [MONITORADO])

    def test_pode_ver_as_nao_monitoradas_marcadas(self):
        r = wa.listar_conversas(self.ctx, {"apenas_monitoradas": False})
        por_id = {c["chat_id"]: c for c in r["conversas"]}
        self.assertTrue(por_id[MONITORADO]["monitorada"])
        self.assertFalse(por_id[LIVRE]["monitorada"])

    def test_contagem_de_monitoradas(self):
        r = wa.listar_conversas(self.ctx, {"apenas_monitoradas": False})
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["monitoradas"], 1)

    def test_mais_recente_primeiro(self):
        r = wa.listar_conversas(self.ctx, {"apenas_monitoradas": False})
        self.assertEqual(r["conversas"][0]["chat_id"], LIVRE)


class TestConsolidar(unittest.TestCase):
    def test_job_criado_com_o_contrato_do_trigger(self):
        ctx = _Ctx(_db_padrao())
        r = wa.consolidar(ctx, {"chat_id": MONITORADO, "message_ids": ["m1", "m2"]})
        self.assertEqual(r["status"], "queued")

        doc = ctx.db._cols[wa.COL_CONSOLIDACOES].dados[r["job_id"]]
        self.assertEqual(doc["status"], "queued")
        self.assertEqual(doc["message_ids"], ["m1", "m2"])
        self.assertEqual(doc["chat_name"], "Equipe")
        self.assertEqual(doc["origem"], "mcp")

    def test_sem_ids_o_periodo_define_o_recorte(self):
        ctx = _Ctx(_db_padrao())
        r = wa.consolidar(ctx, {"chat_id": MONITORADO})
        self.assertEqual(r["n_mensagens"], 5)

    def test_selecao_acima_do_teto_e_recusada_antes_do_job(self):
        ctx = _Ctx(_db_padrao())
        r = wa.consolidar(ctx, {"chat_id": MONITORADO,
                                "message_ids": [f"x{i}" for i in range(wa.MAX_MENSAGENS_POR_JOB + 1)]})
        self.assertIn("erro", r)
        self.assertIn(str(wa.MAX_MENSAGENS_POR_JOB), r["erro"])
        self.assertEqual(ctx.db._cols[wa.COL_CONSOLIDACOES].dados, {})

    def test_teto_espelha_o_do_trigger(self):
        """Divergir do trigger faria o job ser aceito aqui e falhar depois.

        Le a constante do fonte em vez de importar `whatsapp_consolidation`:
        aquele modulo faz `ZoneInfo("America/Sao_Paulo")` no import, que exige a
        base de fusos do sistema — existe no Linux da Cloud Function, nao no
        Windows. Importar so para ler um numero quebraria o teste fora do runtime.
        """
        import pathlib
        import re

        fonte = (pathlib.Path(__file__).parent / "whatsapp_consolidation.py").read_text(
            encoding="utf-8")
        achado = re.search(r"^MAX_MESSAGES_PER_JOB\s*=\s*(\d+)", fonte, re.MULTILINE)
        self.assertIsNotNone(achado, "MAX_MESSAGES_PER_JOB sumiu do trigger")
        self.assertEqual(wa.MAX_MENSAGENS_POR_JOB, int(achado.group(1)))

    def test_recorte_vazio_nao_cria_job(self):
        ctx = _Ctx(_Db(allowlist=[MONITORADO],
                       chats={MONITORADO: {"chat_id": MONITORADO}}))
        r = wa.consolidar(ctx, {"chat_id": MONITORADO})
        self.assertIn("erro", r)
        self.assertEqual(ctx.db._cols[wa.COL_CONSOLIDACOES].dados, {})


class TestTranscriptLiteral(unittest.TestCase):
    """A conversa palavra por palavra fica fora da resposta por padrao."""

    def _snap(self):
        return _Snap("job1", {
            "chat_id": MONITORADO, "chat_name": "Equipe", "status": "completed",
            "resumo": "resumo curto", "itens_de_acao": [], "decisoes": [],
            "transcript_literal": "linha 1\nlinha 2\nlinha 3",
        })

    def test_omitido_por_padrao(self):
        r = wa._formatar_consolidacao(_Ctx(_db_padrao()), self._snap(), False)
        self.assertNotIn("transcript_literal", r)
        self.assertEqual(r["resumo"], "resumo curto")

    def test_incluido_sob_demanda(self):
        r = wa._formatar_consolidacao(_Ctx(_db_padrao()), self._snap(), True)
        self.assertIn("linha 2", r["transcript_literal"])
        self.assertFalse(r["transcript_truncado"])

    def test_transcript_longo_e_cortado_e_avisado(self):
        snap = _Snap("j", {"chat_id": MONITORADO, "status": "completed",
                           "transcript_literal": "x" * (wa.LIMITE_TRANSCRIPT_CHARS + 10)})
        r = wa._formatar_consolidacao(_Ctx(_db_padrao()), snap, True)
        self.assertEqual(len(r["transcript_literal"]), wa.LIMITE_TRANSCRIPT_CHARS)
        self.assertTrue(r["transcript_truncado"])

    def test_allowlist_reconferida_ao_pedir_transcript(self):
        """Consolidacao antiga pode ser de conversa que saiu do monitoramento."""
        ctx = _Ctx(_Db(allowlist=[]))
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa._formatar_consolidacao(ctx, self._snap(), True)

    def test_resumo_de_conversa_desmonitorada_ainda_e_legivel(self):
        """So o literal e reconferido: o resumo ja foi autorizado quando gerado."""
        ctx = _Ctx(_Db(allowlist=[]))
        r = wa._formatar_consolidacao(ctx, self._snap(), False)
        self.assertEqual(r["resumo"], "resumo curto")

    def test_status_em_andamento_traz_orientacao(self):
        snap = _Snap("j", {"chat_id": MONITORADO, "status": "processing"})
        r = wa._formatar_consolidacao(_Ctx(_db_padrao()), snap, False)
        self.assertIn("message", r)

    def test_job_inexistente_nao_e_excecao(self):
        r = wa.ler_consolidacao(_Ctx(_db_padrao()), {"job_id": "nao-existe"})
        self.assertEqual(r["status"], "not_found")


class TestConversaoDeData(unittest.TestCase):
    def test_data_simples_vira_inicio_do_dia(self):
        self.assertEqual(wa._para_datahora("2026-08-01").hour, 0)

    def test_fim_do_dia_inclui_o_dia_inteiro(self):
        """Sem isto, `ate=2026-08-01` cortaria tudo depois da meia-noite."""
        self.assertEqual(wa._para_datahora("2026-08-01", fim_do_dia=True).hour, 23)

    def test_iso_completo_e_preservado(self):
        self.assertEqual(wa._para_datahora("2026-08-01T15:30:00").hour, 15)

    def test_data_sem_fuso_vira_utc(self):
        self.assertIsNotNone(wa._para_datahora("2026-08-01").tzinfo)


class TestCapturaNaoEhLeitura(unittest.TestCase):
    """Capturar tudo não pode virar ler tudo (27/08/2026).

    Até esta data a `chats_allowlist` fazia as duas coisas. Ligar captura geral
    daria ao agente, de uma vez, leitura das 450 conversas individuais — e isso
    aconteceria sem ninguém decidir, como efeito colateral de outro pedido.
    """

    def _db_captura_total(self):
        db = _db_padrao()
        db._cols["system"] = _Colecao({"settings": {
            "whatsapp_ingest": {"chats_allowlist": [MONITORADO], "capturar_todos": True},
        }})
        return db

    def test_captura_total_nao_libera_leitura(self):
        ctx = _Ctx(self._db_captura_total())
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa.ler_mensagens(ctx, {"chat_id": LIVRE})

    def test_captura_total_nao_libera_consolidacao(self):
        ctx = _Ctx(self._db_captura_total())
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa.consolidar(ctx, {"chat_id": LIVRE, "desde": "2026-08-01"})

    def test_captura_total_nao_libera_transcript_antigo(self):
        ctx = _Ctx(self._db_captura_total())
        snap = _Snap("j", {"chat_id": LIVRE, "status": "completed",
                           "transcript_literal": "conversa inteira"})
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa._formatar_consolidacao(ctx, snap, True)

    def test_a_lista_continua_valendo_para_quem_esta_nela(self):
        ctx = _Ctx(self._db_captura_total())
        self.assertEqual(wa.ler_mensagens(ctx, {"chat_id": MONITORADO})["total"], 5)

    def test_listagem_distingue_capturada_de_monitorada(self):
        ctx = _Ctx(self._db_captura_total())
        r = wa.listar_conversas(ctx, {"apenas_monitoradas": False})
        por_id = {c["chat_id"]: c for c in r["conversas"]}
        self.assertTrue(por_id[LIVRE]["capturada"], "o Hermes está guardando")
        self.assertFalse(por_id[LIVRE]["monitorada"], "mas o agente não lê")
        self.assertTrue(por_id[MONITORADO]["capturada"])
        self.assertTrue(por_id[MONITORADO]["monitorada"])

    def test_sem_captura_total_capturada_espelha_monitorada(self):
        ctx = _Ctx(_db_padrao())
        r = wa.listar_conversas(ctx, {"apenas_monitoradas": False})
        for c in r["conversas"]:
            self.assertEqual(c["capturada"], c["monitorada"])

    def test_observacao_avisa_que_capturada_nao_e_legivel(self):
        """Sem o aviso, o agente lê 'capturada: true' e insiste no caminho errado."""
        ctx = _Ctx(self._db_captura_total())
        self.assertIn("capturada≠legível", wa.listar_conversas(ctx, {})["observacao"])

    def test_flag_de_captura_e_lida_do_lugar_certo(self):
        self.assertTrue(wa._captura_total(self._db_captura_total()))
        self.assertFalse(wa._captura_total(_db_padrao()))


class TestLeituraTotal(unittest.TestCase):
    """Interruptor ligado pelo dono em 27/08/2026: leitura em qualquer conversa.

    Testar isto importa nos dois sentidos. Ligado, o agente precisa mesmo
    conseguir abrir — senao a ferramenta que ele pediu nao existe. Desligado, o
    bloqueio tem de voltar inteiro, porque e isso que torna a decisao reversivel
    em vez de definitiva.
    """

    def _db(self, leitura_total):
        db = _db_padrao()
        db._cols["system"] = _Colecao({"settings": {"whatsapp_ingest": {
            "chats_allowlist": [MONITORADO],
            "capturar_todos": True,
            "leitura_total": leitura_total,
        }}})
        return db

    def test_ligado_libera_conversa_fora_da_lista(self):
        ctx = _Ctx(self._db(True))
        ctx.db._cols[wa.COL_MENSAGENS].dados["z1"] = {
            "id": "z1", "chat_id": LIVRE, "content": "oi", "message_type": "chat",
            "timestamp": "2026-08-26T09:00:00"}
        self.assertEqual(wa.ler_mensagens(ctx, {"chat_id": LIVRE})["total"], 1)

    def test_ligado_libera_consolidacao_e_transcript(self):
        ctx = _Ctx(self._db(True))
        snap = _Snap("j", {"chat_id": LIVRE, "status": "completed",
                           "transcript_literal": "conversa inteira"})
        r = wa._formatar_consolidacao(ctx, snap, True)
        self.assertEqual(r["transcript_literal"], "conversa inteira")

    def test_chat_id_vazio_continua_recusado(self):
        """Liberar leitura não é aceitar chamada malformada."""
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa.ler_mensagens(_Ctx(self._db(True)), {"chat_id": ""})

    def test_desligado_o_bloqueio_volta_inteiro(self):
        ctx = _Ctx(self._db(False))
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa.ler_mensagens(ctx, {"chat_id": LIVRE})
        with self.assertRaises(wa.WhatsAppNaoMonitorado):
            wa.consolidar(ctx, {"chat_id": LIVRE, "desde": "2026-08-01"})

    def test_listagem_marca_todas_como_monitoradas(self):
        r = wa.listar_conversas(_Ctx(self._db(True)), {})
        self.assertEqual(len(r["conversas"]), 2)
        self.assertTrue(all(c["monitorada"] for c in r["conversas"]))

    def test_observacao_lembra_dos_terceiros(self):
        """O agente precisa saber que o acesso amplo não é permissão de uso amplo."""
        r = wa.listar_conversas(_Ctx(self._db(True)), {})
        self.assertIn("terceiros", r["observacao"])

    def test_flag_lida_do_lugar_certo(self):
        self.assertTrue(wa._leitura_total(self._db(True)))
        self.assertFalse(wa._leitura_total(self._db(False)))
        self.assertFalse(wa._leitura_total(_db_padrao()))


class TestEnvioEncalhado(unittest.TestCase):
    """`pending` que passou da hora não é "esperando": é encalhado.

    Foi o que aconteceu em 28/08 antes do diagnóstico — as mensagens ficavam na
    fila e ninguém sabia dizer se estavam a caminho ou perdidas. Sem esta
    distinção o agente relata "na fila" indefinidamente, que é uma meia-verdade
    pior que um erro.
    """

    def _ctx(self, minutos_atras, worker_ha_seg):
        from datetime import datetime, timedelta, timezone
        agora = datetime.now(timezone.utc)
        db = _db_padrao()
        db._cols[wa.COL_OUTBOX] = _Colecao({"j": {
            "status": "pending", "to_number": "+5527998754054", "content": "oi",
            "created_at": agora - timedelta(minutes=minutos_atras + 1),
            "scheduled_for": agora - timedelta(minutes=minutos_atras),
        }})
        db._cols["system"] = _Colecao({
            "settings": {"whatsapp_ingest": {"chats_allowlist": [MONITORADO]}},
            "whatsapp_worker": {"last_seen": agora - timedelta(seconds=worker_ha_seg),
                                "ready": True},
        })
        return _Ctx(db)

    def test_recem_enfileirado_e_so_espera(self):
        r = wa.consultar_envio(self._ctx(0, 30), {"job_id": "j"})
        self.assertNotIn("status_efetivo", r)
        self.assertIn("60s", r["message"])

    def test_passou_da_hora_vira_encalhado(self):
        r = wa.consultar_envio(self._ctx(10, 30), {"job_id": "j"})
        self.assertEqual(r["status_efetivo"], "encalhado")
        self.assertIn("NAO diga", r["message"])

    def test_encalhado_com_worker_offline_aponta_a_causa(self):
        """A explicação mais provável para não chegar é o worker fora do ar."""
        r = wa.consultar_envio(self._ctx(10, 3600), {"job_id": "j"})
        self.assertFalse(r["worker"]["online"])
        self.assertIn("offline", r["message"])

    def test_encalhado_com_worker_online_aponta_o_envio(self):
        r = wa.consultar_envio(self._ctx(10, 30), {"job_id": "j"})
        self.assertTrue(r["worker"]["online"])
        self.assertIn("este envio", r["message"].replace("neste", "este"))

    def test_estado_do_worker_acompanha_toda_consulta(self):
        """É a pergunta seguinte em qualquer investigação; vem sem ser pedida."""
        r = wa.consultar_envio(self._ctx(0, 30), {"job_id": "j"})
        self.assertIn("worker", r)
        self.assertIn("ha_segundos", r["worker"])

    def test_carimbo_de_enfileiramento_vem_junto(self):
        r = wa.consultar_envio(self._ctx(0, 30), {"job_id": "j"})
        self.assertIsNotNone(r["enfileirado_em"])
        self.assertIsNotNone(r["agendado_para"])


class TestConsultarEnvio(unittest.TestCase):
    """Enfileirar não é enviar — e sem esta consulta não havia como saber.

    Em 28/08/2026 dois envios foram aceitos, falharam no worker por destino
    inválido, e o agente afirmou ao dono que tinha mandado. A tool devolvia
    "agendada com sucesso" e o estado real ficava só no Firestore.
    """

    def _ctx(self, docs):
        db = _db_padrao()
        db._cols[wa.COL_OUTBOX] = _Colecao(docs)
        return _Ctx(db)

    def test_enviada_traz_destino_real_e_id(self):
        """O worker resolve o número, então o destino final pode diferir do pedido."""
        ctx = self._ctx({"j1": {"status": "sent", "to_number": "+5527998754054",
                                "sent_to": "5527998754054@c.us", "wa_message_id": "ABC",
                                "content": "oi"}})
        r = wa.consultar_envio(ctx, {"job_id": "j1"})
        self.assertEqual(r["status"], "sent")
        self.assertEqual(r["destino_pedido"], "+5527998754054")
        self.assertEqual(r["destino_real"], "5527998754054@c.us")
        self.assertEqual(r["wa_message_id"], "ABC")

    def test_falha_traz_o_motivo(self):
        ctx = self._ctx({"j2": {"status": "failed", "to_number": "+5527998754054",
                                "error_message": "o numero nao esta no WhatsApp",
                                "attempts": 1, "content": "oi"}})
        r = wa.consultar_envio(ctx, {"job_id": "j2"})
        self.assertEqual(r["status"], "failed")
        self.assertIn("nao esta no WhatsApp", r["erro"])
        self.assertEqual(r["tentativas"], 1)

    def test_pendente_avisa_para_nao_afirmar_entrega(self):
        """É o caso que gerou o problema: o agente precisa ser barrado no texto."""
        ctx = self._ctx({"j3": {"status": "pending", "to_number": "+55279", "content": "oi"}})
        r = wa.consultar_envio(ctx, {"job_id": "j3"})
        self.assertIn("NAO diga", r["message"])

    def test_job_inexistente_nao_estoura(self):
        r = wa.consultar_envio(self._ctx({}), {"job_id": "sumiu"})
        self.assertEqual(r["status"], "not_found")

    def test_sem_job_id_lista_os_recentes(self):
        ctx = self._ctx({f"j{i}": {"status": "sent", "to_number": f"+552799900{i}",
                                   "content": "x", "created_at": f"2026-08-2{i}"}
                         for i in range(3)})
        r = wa.consultar_envio(ctx, {})
        self.assertEqual(len(r["envios"]), 3)

    def test_conteudo_vem_truncado(self):
        """A fila guarda a mensagem inteira; a consulta não precisa devolvê-la."""
        ctx = self._ctx({"j": {"status": "sent", "to_number": "+55", "content": "z" * 500}})
        self.assertLessEqual(len(wa.consultar_envio(ctx, {"job_id": "j"})["trecho"]), 80)

    def test_aguardando_aprovacao_descreve_estado_e_alerta(self):
        ctx = self._ctx({"j_draft": {"status": "aguardando_aprovacao", "to_number": "+5527999990000",
                                     "destinatario_nome": "Carlos", "motivo": "Reunião de alinhamento",
                                     "content": "Olá Carlos"}})
        r = wa.consultar_envio(ctx, {"job_id": "j_draft"})
        self.assertEqual(r["status"], "aguardando_aprovacao")
        self.assertEqual(r["destinatario_nome"], "Carlos")
        self.assertEqual(r["motivo"], "Reunião de alinhamento")
        self.assertIn("Aguardando aprovação do dono no Telegram", r["message"])
        self.assertIn("NAO diga", r["message"])

    def test_descartado_descreve_estado(self):
        ctx = self._ctx({"j_discard": {"status": "descartado", "to_number": "+5527999990000",
                                       "content": "Olá", "descartado_em": "2026-09-03T18:00:00Z"}})
        r = wa.consultar_envio(ctx, {"job_id": "j_discard"})
        self.assertEqual(r["status"], "descartado")
        self.assertIn("Descartado pelo dono", r["message"])


if __name__ == "__main__":
    unittest.main()
