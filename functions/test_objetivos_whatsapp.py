"""Modo Objetivo no WhatsApp (objetivos_whatsapp): cadastro, ciclo, pedidos ao André,
conclusão, prazo, pausa quando o André escreve e os botões do Telegram."""

import datetime as dt
import unittest
from unittest import mock

from google.cloud.firestore_v1.transforms import ArrayUnion

import objetivos_whatsapp as ow
import telegram_callbacks_objetivo as tco

UTC = dt.timezone.utc


# ---------------------------------------------------------------------------
# Banco simulado com o que o módulo usa (ArrayUnion, FieldFilter, order_by, limit)
# ---------------------------------------------------------------------------

class _Snap:
    def __init__(self, ref, dados):
        self.reference = ref
        self.id = ref.id
        self._dados = dados
        self.exists = dados is not None

    def to_dict(self):
        return dict(self._dados) if self._dados is not None else None


class _Ref:
    def __init__(self, col, doc_id):
        self.col, self.id = col, doc_id

    def get(self, transaction=None):
        return _Snap(self, self.col.docs.get(self.id))

    def set(self, dados, merge=False):
        if merge and self.id in self.col.docs:
            self.col.docs[self.id].update(dados)
        else:
            self.col.docs[self.id] = dict(dados)

    def update(self, dados):
        atual = self.col.docs.setdefault(self.id, {})
        for chave, valor in dados.items():
            if isinstance(valor, ArrayUnion):
                lista = list(atual.get(chave) or [])
                lista += [v for v in valor.values if v not in lista]
                atual[chave] = lista
            else:
                atual[chave] = valor

    def delete(self):
        self.col.docs.pop(self.id, None)


class _Consulta:
    def __init__(self, col, filtros=(), ordem=None, limite=None):
        self.col, self.filtros, self.ordem, self.limite = col, list(filtros), ordem, limite

    def where(self, campo=None, op=None, valor=None, *, filter=None):
        if filter is not None:
            campo, op, valor = filter.field_path, filter.op_string, filter.value
        return _Consulta(self.col, self.filtros + [(campo, op, valor)], self.ordem, self.limite)

    def order_by(self, campo, direction=None):
        return _Consulta(self.col, self.filtros, (campo, direction == "DESCENDING"), self.limite)

    def limit(self, n):
        return _Consulta(self.col, self.filtros, self.ordem, n)

    def stream(self):
        itens = [(k, v) for k, v in self.col.docs.items()
                 if all(op == "==" and v.get(c) == val for c, op, val in self.filtros)]
        if self.ordem:
            campo, desc = self.ordem
            itens.sort(key=lambda kv: kv[1].get(campo) or dt.datetime.min.replace(tzinfo=UTC), reverse=desc)
        if self.limite is not None:
            itens = itens[: self.limite]
        return [_Snap(_Ref(self.col, k), v) for k, v in itens]


class _Col(_Consulta):
    def __init__(self, nome):
        super().__init__(self)
        self.nome, self.docs, self._n = nome, {}, 0

    def document(self, doc_id=None):
        if not doc_id:
            self._n += 1
            doc_id = f"{self.nome}-{self._n}"
        return _Ref(self, doc_id)

    def add(self, dados):
        ref = self.document()
        ref.set(dados)
        return None, ref


class _Db:
    def __init__(self):
        self.cols = {}

    def collection(self, nome):
        return self.cols.setdefault(nome, _Col(nome))


AGORA = dt.datetime(2026, 10, 15, 14, 0, tzinfo=UTC)

ARGS = {
    "contato": "Clínica Vida",
    "objetivo": "Marcar consulta de dermatologia",
    "criterio_conclusao": "Consulta marcada com data, hora e local",
    "mensagem_abertura": "Oi, boa tarde! Queria marcar uma consulta de dermatologia. Vocês têm horário?",
    "pode_informar": "Nome: André Martini; convênio Allcare; terças ou quintas de manhã",
    "nunca_informar": "CPF, endereço",
    "limites_decisao": "aceitar horário terça ou quinta de manhã até 30/10",
    "prazo_min": 30,
    "acao_id": "acao-1",
    "aprovar_cada_mensagem": False,
}


class _Base(unittest.TestCase):
    def setUp(self):
        self.db = _Db()
        self.enfileiradas = []
        self.avisos = []
        self.notas = []

        def enfileirar(db, objetivo, texto, *, imediato):
            self.enfileiradas.append({"texto": texto, "imediato": imediato, "objetivo_id": objetivo["id"]})
            return {"status": "pending" if imediato else "aguardando_aprovacao",
                    "outbox_id": f"ob-{len(self.enfileiradas)}"}

        patches = [
            mock.patch.object(ow, "_agora", side_effect=lambda: self.agora),
            mock.patch.object(ow, "_resolver_contato", return_value=("5527999990000@c.us", "Clínica Vida")),
            mock.patch.object(ow, "_enfileirar", side_effect=enfileirar),
            mock.patch.object(ow, "_avisar", side_effect=lambda db, o, texto, botoes: self.avisos.append((texto, botoes))),
            mock.patch.object(ow, "_anotar", side_effect=lambda db, o, nota: self.notas.append(nota)),
            mock.patch.object(ow, "_criar_etapa", return_value="etapa-1"),
            mock.patch.object(ow, "_concluir_etapa"),
            mock.patch.object(ow, "_registrar_execucao"),
            mock.patch.object(ow, "_agenda", return_value="Sem eventos."),
            mock.patch.object(ow, "_adquirir_trava", return_value=True),
            mock.patch.object(ow, "_config", return_value={}),
        ]
        self.agora = AGORA
        for p in patches:
            p.start()
        self.addCleanup(mock.patch.stopall)
        self.concluir_etapa = ow._concluir_etapa

    def _criar(self, **extra):
        res = ow.criar_e_iniciar(self.db, {**ARGS, **extra})
        self.assertEqual(res["status"], "iniciado", res)
        return res["objetivo_id"]

    def _objetivo(self, objetivo_id):
        return self.db.collection(ow.COLECAO).docs[objetivo_id]

    def _mensagem(self, texto, *, from_me=False, minutos=0, mid=None, chat="5527999990000@c.us", **extra):
        return {"chat_id": chat, "from_me": from_me, "content": texto, "wa_message_id": mid or f"m-{texto[:8]}",
                "timestamp": self.agora - dt.timedelta(minutes=minutos), **extra}

    def _guardar(self, mensagem):
        self.db.collection("whatsapp_messages").document(mensagem["wa_message_id"]).set(mensagem)
        return mensagem


def _decisor(*decisoes):
    fila = list(decisoes)
    chamadas = []

    def decidir(db, objetivo, conversa, agenda, feedback=None):
        chamadas.append({"objetivo": objetivo, "conversa": conversa, "agenda": agenda, "feedback": feedback})
        return fila.pop(0) if fila else {"acao": "aguardar", "motivo": "fim do roteiro"}

    decidir.chamadas = chamadas
    return decidir


# ---------------------------------------------------------------------------

class TestCadastro(_Base):
    def test_previa_mostra_o_que_o_andre_confirma(self):
        p = ow.previa(self.db, ARGS)
        self.assertEqual(p["destinatario"], "Clínica Vida")
        self.assertEqual(p["mensagem_de_abertura"], ARGS["mensagem_abertura"])
        self.assertEqual(p["prazo_min"], 30)
        self.assertFalse(p["aprovar_cada_mensagem"])

    def test_prazo_padrao_e_modo_sombra_vem_da_configuracao(self):
        args = {k: v for k, v in ARGS.items() if k not in ("prazo_min", "aprovar_cada_mensagem")}
        p = ow.previa(self.db, args)
        self.assertEqual(p["prazo_min"], ow.PRAZO_PADRAO_MIN)
        self.assertTrue(p["aprovar_cada_mensagem"])

    def test_recusa_campos_faltando_grupo_e_abertura_proibida(self):
        with self.assertRaisesRegex(ValueError, "criterio_conclusao"):
            ow.previa(self.db, {**ARGS, "criterio_conclusao": ""})
        with mock.patch.object(ow, "_resolver_contato", side_effect=ValueError("grupos não são aceitos")):
            with self.assertRaisesRegex(ValueError, "grupos"):
                ow.previa(self.db, ARGS)
        for abertura in ("Oi, sou o assistente do André.", "Oi! Pode me ligar amanhã?", "Meu CPF é 123.456.789-00"):
            with self.subTest(abertura=abertura), self.assertRaisesRegex(ValueError, "barrada"):
                ow.previa(self.db, {**ARGS, "mensagem_abertura": abertura})

    def test_criar_grava_aponta_manda_a_abertura_e_cria_a_etapa(self):
        oid = self._criar()
        obj = self._objetivo(oid)
        self.assertEqual(obj["estado"], ow.EM_ANDAMENTO)
        self.assertEqual(obj["expira_em"], AGORA + dt.timedelta(minutes=30))
        self.assertEqual(obj["etapa_id"], "etapa-1")
        self.assertEqual(self.enfileiradas, [{"texto": ARGS["mensagem_abertura"], "imediato": True, "objetivo_id": oid}])
        self.assertEqual(obj["mensagens_enviadas"][0]["texto"], ARGS["mensagem_abertura"])
        self.assertEqual(ow.objetivo_ativo_do_chat(self.db, "5527999990000@c.us")["id"], oid)

    def test_abertura_vai_imediata_mesmo_no_modo_sombra(self):
        self._criar(aprovar_cada_mensagem=True)
        self.assertTrue(self.enfileiradas[0]["imediato"])

    def test_um_objetivo_por_conversa(self):
        oid = self._criar()
        res = ow.criar_e_iniciar(self.db, ARGS)
        self.assertIn("Já há um objetivo", res["erro"])
        self.assertEqual(res["objetivo_id"], oid)


class TestMensagemDoContato(_Base):
    def test_espera_silencio_e_responde(self):
        oid = self._criar()
        decidir = _decisor({"acao": "responder", "texto": "Pode ser quinta às 9h?", "informacao_nova": True})
        dormir = mock.Mock()
        msg = self._guardar(self._mensagem("Temos quinta às 9h ou sexta às 15h"))
        res = ow.processar_mensagem(self.db, msg, dormir=dormir, decidir=decidir)
        dormir.assert_any_call(ow.ESPERA_SILENCIO_S)
        self.assertEqual(res["status"], "respondido")
        self.assertEqual(self.enfileiradas[-1], {"texto": "Pode ser quinta às 9h?", "imediato": True, "objetivo_id": oid})
        textos = [m["texto"] for m in decidir.chamadas[0]["conversa"]]
        self.assertIn("Temos quinta às 9h ou sexta às 15h", textos)
        self.assertEqual(decidir.chamadas[0]["agenda"], "Sem eventos.")

    def test_mensagens_seguidas_so_a_ultima_responde(self):
        self._criar()
        decidir = _decisor()

        def chega_outra(_segundos):
            self.db.collection(ow.COLECAO).docs[next(iter(self.db.collection(ow.COLECAO).docs))]["ultima_recebida_id"] = "m-seguinte"

        res = ow.processar_mensagem(self.db, self._mensagem("primeira"), dormir=chega_outra, decidir=decidir)
        self.assertEqual(res["status"], "agrupada")
        self.assertEqual(decidir.chamadas, [])

    def test_ignora_mensagem_antiga_grupo_e_conversa_sem_objetivo(self):
        self._criar()
        decidir = _decisor()
        self.assertIsNone(ow.processar_mensagem(self.db, self._mensagem("velha", minutos=11), dormir=mock.Mock(), decidir=decidir))
        self.assertIsNone(ow.processar_mensagem(self.db, self._mensagem("grupo", is_group=True), dormir=mock.Mock(), decidir=decidir))
        self.assertIsNone(ow.processar_mensagem(self.db, self._mensagem("outro", chat="5511@c.us"), dormir=mock.Mock(), decidir=decidir))
        self.assertEqual(decidir.chamadas, [])


class TestMensagemDoAndre(_Base):
    def test_eco_do_gaspar_nao_pausa_e_reconhece_o_outro_id_do_chat(self):
        import mensagens_gaspar

        oid = self._criar()
        mensagens_gaspar.registrar(self.db, "Pode ser quinta às 9h?", origem=ow.ORIGEM, ref_id=oid)
        ow.processar_mensagem(self.db, self._mensagem("Pode ser quinta às 9h?", from_me=True, chat="98765@lid"))
        obj = self._objetivo(oid)
        self.assertEqual(obj["estado"], ow.EM_ANDAMENTO)
        self.assertIn("98765@lid", obj["chat_ids"])
        self.assertEqual(ow.objetivo_ativo_do_chat(self.db, "98765@lid")["id"], oid)

    def test_mensagem_do_andre_pausa_e_avisa(self):
        oid = self._criar()
        res = ow.processar_mensagem(self.db, self._mensagem("Deixa que eu vejo isso", from_me=True))
        self.assertEqual(res["status"], "pausado")
        self.assertEqual(self._objetivo(oid)["estado"], ow.PAUSADO)
        self.assertEqual([b for _, b in self.avisos[-1][1]], ["retomar", "fim"])


class TestDecisoes(_Base):
    def _ciclo(self, oid, *decisoes, dormir=None):
        decidir = _decisor(*decisoes)
        res = ow.executar_ciclo(self.db, oid, decidir=decidir, dormir=dormir or mock.Mock())
        return res, decidir

    def test_resposta_barrada_tenta_de_novo_com_o_motivo(self):
        oid = self._criar()
        res, decidir = self._ciclo(oid, {"acao": "responder", "texto": "Me liga que a gente acerta", "informacao_nova": True},
                                   {"acao": "responder", "texto": "Pode ser quinta às 9h?", "informacao_nova": True})
        self.assertEqual(res["status"], "respondido")
        self.assertIn("fala em ligação ou chamada", decidir.chamadas[1]["feedback"])
        self.assertEqual(self.enfileiradas[-1]["texto"], "Pode ser quinta às 9h?")

    def test_resposta_barrada_duas_vezes_vai_para_o_andre(self):
        oid = self._criar()
        res, _ = self._ciclo(oid, {"acao": "responder", "texto": "Sou o assistente do André", "informacao_nova": True},
                             {"acao": "responder", "texto": "Sou um robô, desculpe", "informacao_nova": True})
        self.assertEqual(res["status"], ow.AGUARDANDO_DONO)
        self.assertIn("barrada", self._objetivo(oid)["pergunta_ao_dono"])
        self.assertEqual(len(self.enfileiradas), 1)  # só a abertura

    def test_dado_vetado_e_numero_nao_liberado_sao_barrados(self):
        oid = self._criar()
        res, _ = self._ciclo(oid, {"acao": "responder", "texto": "Meu endereço é Rua X, 10", "informacao_nova": True},
                             {"acao": "responder", "texto": "A carteirinha é 123456789012", "informacao_nova": True})
        self.assertEqual(res["status"], ow.AGUARDANDO_DONO)

    def test_aguardar_nao_manda_nada(self):
        oid = self._criar()
        res, _ = self._ciclo(oid, {"acao": "aguardar", "motivo": "vão verificar"})
        self.assertEqual(res["status"], "aguardando_contato")
        self.assertEqual(len(self.enfileiradas), 1)

    def test_perguntou_se_robo_nao_responde_e_chama_o_andre(self):
        oid = self._criar()
        self.agora = AGORA + dt.timedelta(minutes=10)
        res, _ = self._ciclo(oid, {"acao": "pedir_ao_dono", "motivo": "perguntou_se_robo",
                                   "pergunta": "Perguntaram se é robô."})
        obj = self._objetivo(oid)
        self.assertEqual(obj["estado"], ow.AGUARDANDO_DONO)
        self.assertEqual(obj["restante_s"], 20 * 60)
        self.assertIn("Perguntaram se é robô", self.avisos[-1][0])
        self.assertEqual([b for _, b in self.avisos[-1][1]], ["resp", "fim"])
        self.assertEqual(len(self.enfileiradas), 1)

    def test_concluir_manda_a_ultima_mensagem_fecha_e_avisa(self):
        oid = self._criar()
        res, _ = self._ciclo(oid, {"acao": "concluir", "resultado": "Quinta 16/10, 9h, Rua Y",
                                   "mensagem_final": "Perfeito, obrigado!"})
        obj = self._objetivo(oid)
        self.assertEqual(res["status"], ow.CONCLUIDO)
        self.assertEqual(obj["resultado"], "Quinta 16/10, 9h, Rua Y")
        self.assertEqual(self.enfileiradas[-1]["texto"], "Perfeito, obrigado!")
        self.assertIsNone(ow.objetivo_ativo_do_chat(self.db, "5527999990000@c.us"))
        self.concluir_etapa.assert_called_once()
        self.assertIn("concluído", self.avisos[-1][0])

    def test_travar_vai_para_o_andre(self):
        oid = self._criar()
        res, _ = self._ciclo(oid, {"acao": "travar", "motivo": "Não atendem o convênio"})
        self.assertEqual(res["status"], ow.AGUARDANDO_DONO)
        self.assertEqual(self._objetivo(oid)["motivo_pergunta"], "travou")

    def test_decisao_invalida_vai_para_o_andre(self):
        oid = self._criar()
        res, _ = self._ciclo(oid, {"acao": "inventada"})
        self.assertEqual(res["status"], ow.AGUARDANDO_DONO)

    def test_tres_rodadas_sem_progresso_param(self):
        oid = self._criar()
        sem = {"acao": "responder", "informacao_nova": False}
        for n, texto in enumerate(("Tudo bem?", "Conseguiu ver?")):
            self.agora += dt.timedelta(minutes=1)
            self._ciclo(oid, {**sem, "texto": texto})
        self.assertEqual(self._objetivo(oid)["sem_progresso"], 2)
        res, _ = self._ciclo(oid, {**sem, "texto": "E aí?"})
        self.assertEqual(res["status"], ow.AGUARDANDO_DONO)
        self.assertEqual(self._objetivo(oid)["motivo_pergunta"], "sem_progresso")

    def test_prazo_vencido_expira_no_ciclo(self):
        oid = self._criar()
        self.agora = AGORA + dt.timedelta(minutes=31)
        res, decidir = self._ciclo(oid, {"acao": "aguardar", "motivo": "x"})
        self.assertEqual(res["status"], ow.EXPIRADO)
        self.assertEqual(decidir.chamadas, [])
        self.assertEqual([b for _, b in self.avisos[-1][1]], ["mais30", "fim"])

    def test_modo_sombra_descarta_o_rascunho_velho(self):
        oid = self._criar(aprovar_cada_mensagem=True)
        with mock.patch("outbox_aprovacao.descartar_rascunho") as descartar:
            self._ciclo(oid, {"acao": "responder", "texto": "Pode ser quinta?", "informacao_nova": True})
            self.agora += dt.timedelta(minutes=1)
            self._ciclo(oid, {"acao": "responder", "texto": "Ou sexta de manhã?", "informacao_nova": True})
        self.assertFalse(self.enfileiradas[-1]["imediato"])
        descartar.assert_called_once_with(self.db, "ob-2")
        self.assertEqual(self._objetivo(oid)["rascunho_pendente_id"], "ob-3")

    def test_intervalo_minimo_entre_envios(self):
        oid = self._criar()
        self.agora = AGORA + dt.timedelta(seconds=5)
        dormir = mock.Mock()
        self._ciclo(oid, {"acao": "responder", "texto": "Pode ser quinta?", "informacao_nova": True}, dormir=dormir)
        dormir.assert_called_once_with(ow.INTERVALO_MIN_ENVIO_S - 5)


class TestRespostaDoAndre(_Base):
    def test_resposta_retoma_com_o_prazo_que_faltava_e_vai_ao_modelo(self):
        oid = self._criar()
        self.agora = AGORA + dt.timedelta(minutes=25)
        ow.executar_ciclo(self.db, oid, decidir=_decisor({"acao": "pedir_ao_dono", "motivo": "decisao",
                                                          "pergunta": "Sexta às 15h serve?"}))
        self.agora = AGORA + dt.timedelta(hours=2)
        decidir = _decisor({"acao": "responder", "texto": "Sexta às 15h fica ótimo.", "informacao_nova": True})
        res = ow.responder_do_dono(self.db, oid, resposta="Sim, sexta às 15h serve", decidir=decidir)
        obj = self._objetivo(oid)
        self.assertEqual(res["status"], "retomado")
        self.assertEqual(obj["estado"], ow.EM_ANDAMENTO)
        self.assertEqual(obj["expira_em"], self.agora + ow.PRAZO_MINIMO_AO_RETOMAR)
        self.assertEqual(obj["respostas_do_dono"][0]["resposta"], "Sim, sexta às 15h serve")
        self.assertIn("Sim, sexta às 15h serve", ow.montar_prompt(decidir.chamadas[0]["objetivo"]))
        self.assertEqual(self.enfileiradas[-1]["texto"], "Sexta às 15h fica ótimo.")

    def test_mais_prazo_reativa_o_expirado(self):
        oid = self._criar()
        self.agora = AGORA + dt.timedelta(minutes=40)
        ow.varrer(self.db, agora=self.agora)
        self.assertEqual(self._objetivo(oid)["estado"], ow.EXPIRADO)
        ow.responder_do_dono(self.db, oid, estender_min=30, decidir=_decisor())
        obj = self._objetivo(oid)
        self.assertEqual(obj["estado"], ow.EM_ANDAMENTO)
        self.assertEqual(obj["expira_em"], self.agora + dt.timedelta(minutes=30))

    def test_recusa_objetivo_encerrado_e_prazo_invalido(self):
        oid = self._criar()
        self.assertIn("erro", ow.responder_do_dono(self.db, oid, estender_min="muito"))
        ow.encerrar(self.db, oid)
        self.assertIn("erro", ow.responder_do_dono(self.db, oid, resposta="x"))

    def test_encerrar_solta_a_conversa_e_descarta_o_rascunho(self):
        oid = self._criar()
        self._objetivo(oid)["rascunho_pendente_id"] = "ob-9"
        with mock.patch("outbox_aprovacao.descartar_rascunho") as descartar:
            res = ow.encerrar(self.db, oid, "resolvi por fora")
        self.assertEqual(res["status"], ow.CANCELADO)
        descartar.assert_called_once_with(self.db, "ob-9")
        self.assertIsNone(ow.objetivo_ativo_do_chat(self.db, "5527999990000@c.us"))


class TestVarredura(_Base):
    def test_expira_so_o_vencido_e_livre(self):
        vencido = self._criar()
        self.db.collection(ow.COLECAO_ATIVOS).docs.clear()
        outro = self._criar(contato="Outra")
        self._objetivo(outro)["expira_em"] = AGORA + dt.timedelta(hours=1)
        self.db.collection(ow.COLECAO_ATIVOS).docs.clear()
        travado = self._criar(contato="Mais uma")
        self._objetivo(travado)["processando_desde"] = AGORA + dt.timedelta(minutes=39)
        n = ow.varrer(self.db, agora=AGORA + dt.timedelta(minutes=40))
        self.assertEqual(n, 1)
        self.assertEqual(self._objetivo(vencido)["estado"], ow.EXPIRADO)
        self.assertEqual(self._objetivo(outro)["estado"], ow.EM_ANDAMENTO)
        self.assertEqual(self._objetivo(travado)["estado"], ow.EM_ANDAMENTO)


class TestConversaEPrompt(_Base):
    def test_conversa_em_ordem_com_eu_audio_e_os_dois_ids(self):
        oid = self._criar()
        self._objetivo(oid)["chat_ids"] = ["5527999990000@c.us", "98765@lid"]
        self._guardar(self._mensagem("Oi, tem horário?", from_me=True, minutos=5, mid="a"))
        self._guardar(self._mensagem("", minutos=3, mid="b", message_type="ptt", transcription_text="Temos quinta"))
        self._guardar(self._mensagem("Às 9h", minutos=1, mid="c", chat="98765@lid"))
        conversa = ow._ler_conversa(self.db, self._objetivo(oid))
        self.assertEqual([(m["eu"], m["texto"]) for m in conversa],
                         [(True, "Oi, tem horário?"), (False, "[áudio] Temos quinta"), (False, "Às 9h")])

    def test_prompt_traz_o_objetivo_e_as_regras_do_dono(self):
        prompt = ow.montar_prompt({**ARGS, "respostas_do_dono": [{"pergunta": "Valor?", "resposta": "Até 300"}]})
        for trecho in (ARGS["objetivo"], ARGS["criterio_conclusao"], ARGS["nunca_informar"], "Até 300",
                       "Nunca sugira ligação", "perguntou_se_robo", "Tininha", "PRIMEIRA PESSOA".lower()):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho.lower(), prompt.lower())


class TestTrava(unittest.TestCase):
    def test_um_ciclo_por_vez(self):
        from test_mcp_jobs import _MockDB

        db = _MockDB()
        ref = db.collection(ow.COLECAO).document("o1")
        ref.col._docs["o1"] = {"estado": ow.EM_ANDAMENTO}
        self.assertTrue(ow._adquirir_trava(db, ref))
        self.assertFalse(ow._adquirir_trava(db, ref))
        ref.col._docs["o1"]["processando_desde"] = ow._agora() - ow.TRAVA_VALIDADE - dt.timedelta(seconds=1)
        self.assertTrue(ow._adquirir_trava(db, ref))


class TestBotoesDoTelegram(unittest.TestCase):
    def _clicar(self, data, session=None):
        session = {} if session is None else session
        with mock.patch.object(tco, "_answer_callback_query") as responder, \
             mock.patch.object(tco, "_save_session"), mock.patch.object(tco, "_send_telegram_message"):
            tratado = tco.handle(mock.Mock(), "tok", "q1", "123", data, {}, session, None, mock.Mock(), None, None)
        return tratado, responder, session

    def test_outros_botoes_nao_sao_deste_modulo(self):
        self.assertFalse(self._clicar("outbox:x:ok")[0])

    def test_responder_arma_a_captura_da_proxima_mensagem(self):
        tratado, _, session = self._clicar("objwa:o1:resp")
        self.assertTrue(tratado)
        self.assertEqual(session[tco.CAPTURA_RESPOSTA], "o1")

    def test_encerrar_e_mais_prazo(self):
        with mock.patch.object(ow, "encerrar", return_value={"status": "cancelado"}) as encerrar:
            self._clicar("objwa:o1:fim")
        encerrar.assert_called_once()
        with mock.patch.object(ow, "responder_do_dono", return_value={"status": "retomado"}) as resp:
            self._clicar("objwa:o1:mais30")
            self._clicar("objwa:o1:retomar")
        self.assertEqual(resp.call_args_list[0].kwargs["estender_min"], 30)
        self.assertIsNone(resp.call_args_list[1].kwargs["estender_min"])

    def test_acao_desconhecida_e_respondida(self):
        tratado, responder, _ = self._clicar("objwa:o1:xyz")
        self.assertTrue(tratado)
        responder.assert_called_once()


class TestCapturaDaResposta(unittest.TestCase):
    def test_proxima_mensagem_vira_a_resposta(self):
        import telegram_message_deterministic as tmd

        session = {"pending_objetivo_resposta": "o1"}
        with mock.patch.object(tmd, "_save_session"), \
             mock.patch.object(tmd, "_send_telegram_session_message") as enviar, \
             mock.patch.object(tmd, "_try_register_walk_block", return_value=None), \
             mock.patch.object(tmd, "_try_register_weight", return_value=None), \
             mock.patch("objetivos_whatsapp.responder_do_dono", return_value={"status": "retomado"}) as resp:
            tratada = tmd.try_deterministic_reply(mock.Mock(), "tok", "123", "Pode ser sexta", session, "gk",
                                                  "texto", "masculina", {}, mock.Mock())
        self.assertTrue(tratada)
        resp.assert_called_once()
        self.assertEqual(resp.call_args.kwargs["resposta"], "Pode ser sexta")
        self.assertNotIn("pending_objetivo_resposta", session)
        self.assertIn("Sigo a conversa", enviar.call_args.args[3])


if __name__ == "__main__":
    unittest.main()
