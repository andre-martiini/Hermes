"""Detector de subproduto: as travas que decidem sozinhas, sem IA.

O criterio de aceite do pedido esta em `TestOCasoDoHandoffSispnaes`: com o
handoff do SISPNAES no sistema, o detector precisa levantar aquela acao. Se nao
pegar esse caso, o criterio esta errado — foi assim que o usuario enunciou.

Os demais travam as tres protecoes que impedem o recurso de virar praga: o
momento (a acao precisa ter ganhado corpo), o teto (poucas por mes, nenhuma em
semana cheia) e a memoria ("nunca para esta acao" e definitivo).

Nada aqui chama modelo. A parte de IA e so a que julga escassez e escreve a
frase; tudo que decide QUANDO e SE perguntar e deterministico de proposito — o
teto nao pode depender do humor do modelo.
"""

import os
import unittest

import deteccao_subproduto as ds

HOJE = "2026-08-29"


def _tarefa(**over):
    base = {"id": "t1", "titulo": "Acao", "acompanhamento": [], "pool_dados": [], "plano_acao": []}
    base.update(over)
    return base


def _diario(caracteres: int, entradas: int = 1):
    pedaco = "x" * max(1, caracteres // entradas)
    return [{"data": HOJE, "nota": pedaco} for _ in range(entradas)]


def _anexo(nome):
    return {"tipo": "arquivo", "nome": nome, "valor": f"https://drive/{nome}"}


def _etapas(feitas: int, total: int = 5):
    """Forma real do plano: `text` + `completed`, como `subtarefas` le."""
    return [{"text": f"Etapa {i}", "completed": i < feitas} for i in range(total)]


class TestOCasoDoHandoffSispnaes(unittest.TestCase):
    """O teste que o proprio pedido define: se nao pegar isto, o criterio esta errado.

    Handoff de 12 secoes do SISPNAES para o novo desenvolvedor. O ativo — relato
    de experiencia sobre transicao de conhecimento em TI no setor publico — ja
    esta escrito; o custo marginal de publicar e quase zero. Era o caso mais
    rentavel da semana e foi desperdicado por ninguem ter perguntado.
    """

    def _acao_do_handoff(self):
        return _tarefa(
            id="sispnaes",
            titulo="Ciclo Sispnaes 2026",
            pool_dados=[_anexo("HANDOFF-SISPNAES.md")],
            acompanhamento=_diario(2000, entradas=4),
            plano_acao=_etapas(4),
        )

    def test_o_handoff_e_levantado_como_candidato(self):
        candidatos = ds.candidatas([self._acao_do_handoff()], {}, HOJE)
        self.assertEqual([c["task_id"] for c in candidatos], ["sispnaes"])

    def test_o_documento_escrito_e_citado_como_evidencia(self):
        """A sugestao precisa apontar o material; sem isso perde o argumento."""
        corpo = ds.corpo_da_acao(self._acao_do_handoff())
        self.assertIn("HANDOFF-SISPNAES.md", corpo["documentos"])
        self.assertTrue(corpo["tem_texto_pronto"])

    def test_o_dossie_leva_o_texto_que_o_usuario_ja_escreveu(self):
        """O ativo mora no diario: e o corpo de texto que ninguem le."""
        dossie = ds.montar_dossie(ds.candidatas([self._acao_do_handoff()], {}, HOJE)[0])
        self.assertEqual(dossie["titulo"], "Ciclo Sispnaes 2026")
        self.assertGreater(len(dossie["diario"]), 1000)
        self.assertIn("HANDOFF-SISPNAES.md", dossie["documentos"])

    def test_quem_ja_tem_texto_pronto_vem_primeiro(self):
        so_etapas = _tarefa(id="etapas", plano_acao=_etapas(4))
        candidatos = ds.candidatas([so_etapas, self._acao_do_handoff()], {}, HOJE)
        self.assertEqual(candidatos[0]["task_id"], "sispnaes")


class TestOMomento(unittest.TestCase):
    """Nao e a conclusao nem a criacao: e quando a acao ganha corpo."""

    def test_acao_vazia_nao_tem_corpo(self):
        self.assertIsNone(ds.corpo_da_acao(_tarefa()))

    def test_documento_anexado_da_corpo_sozinho(self):
        corpo = ds.corpo_da_acao(_tarefa(pool_dados=[_anexo("ROTEIRO.md")]))
        self.assertEqual([s["tipo"] for s in corpo["sinais"]], ["documento"])

    def test_diario_volumoso_da_corpo_sozinho(self):
        corpo = ds.corpo_da_acao(_tarefa(acompanhamento=_diario(ds.CORPO_MIN_CARACTERES_DIARIO)))
        self.assertTrue(corpo["tem_texto_pronto"])

    def test_diario_curto_ainda_nao_e_corpo(self):
        self.assertIsNone(ds.corpo_da_acao(_tarefa(acompanhamento=_diario(200))))

    def test_etapas_concluidas_dao_corpo_sem_a_acao_estar_pronta(self):
        """Acao parcialmente feita ja indica materialidade."""
        corpo = ds.corpo_da_acao(_tarefa(plano_acao=_etapas(ds.CORPO_MIN_ETAPAS_FEITAS, total=9)))
        self.assertIsNotNone(corpo)
        self.assertFalse(corpo["tem_texto_pronto"])

    def test_comprovante_solto_nao_e_materia_prima(self):
        """PDF de comprovante nao vira artigo; sozinho nao da corpo."""
        self.assertIsNone(ds.corpo_da_acao(_tarefa(pool_dados=[_anexo("comprovante.pdf")])))


class TestContagemDeEtapas(unittest.TestCase):
    """A contagem sai de `subtarefas`, que e quem sabe as duas grafias."""

    def test_le_o_formato_novo_com_estado(self):
        plano = [{"text": "a", "estado": "feito"}, {"text": "b", "estado": "pendente"}]
        self.assertEqual(ds._etapas_feitas({"plano_acao": plano}), 1)

    def test_le_o_formato_antigo_com_completed(self):
        plano = [{"text": "a", "completed": True}, {"text": "b", "completed": False}]
        self.assertEqual(ds._etapas_feitas({"plano_acao": plano}), 1)

    def test_etapa_sem_texto_nao_conta(self):
        self.assertEqual(ds._etapas_feitas({"plano_acao": [{"text": "", "completed": True}]}), 0)


class TestOTeto(unittest.TestCase):
    """Sem teto vira praga, e praga e desinstalada."""

    def _sugestoes(self, quantas, mes="2026-08", status=ds.STATUS_PENDENTE):
        return [{"task_id": f"t{i}", "criada_em": f"{mes}-1{i}", "status": status}
                for i in range(quantas)]

    def test_semana_cheia_bloqueia_antes_de_qualquer_chamada(self):
        carga = [{"data": f"2026-08-{d}", "total": 5} for d in range(20, 27)]
        r = ds.pode_rodar([], carga, HOJE)
        self.assertEqual((r["pode"], r["motivo"]), (False, "semana_cheia"))

    def test_semana_folgada_libera(self):
        carga = [{"data": f"2026-08-{d}", "total": 1} for d in range(20, 27)]
        self.assertTrue(ds.pode_rodar([], carga, HOJE)["pode"])

    def test_teto_do_mes_bloqueia(self):
        r = ds.pode_rodar(self._sugestoes(ds.TETO_POR_MES), [], HOJE)
        self.assertEqual((r["pode"], r["motivo"]), (False, "teto_do_mes"))

    def test_sugestao_recusada_ainda_conta_no_teto(self):
        """Recusada interrompeu do mesmo jeito; o teto e de interrupcao."""
        adiadas = self._sugestoes(ds.TETO_POR_MES, status=ds.STATUS_ADIADA)
        self.assertFalse(ds.pode_rodar(adiadas, [], HOJE)["pode"])

    def test_nunca_nao_ocupa_vaga_do_mes(self):
        """"Nunca" e ajuste de escopo, nao interrupcao gasta."""
        nunca = self._sugestoes(ds.TETO_POR_MES, status=ds.STATUS_NUNCA)
        self.assertTrue(ds.pode_rodar(nunca, [], HOJE)["pode"])

    def test_mes_anterior_nao_conta(self):
        self.assertTrue(ds.pode_rodar(self._sugestoes(5, mes="2026-07"), [], HOJE)["pode"])


class TestAMemoria(unittest.TestCase):
    """Sem "nunca para esta acao" o sistema repete a mesma sugestao e vira barulho."""

    def test_nunca_tira_a_acao_de_vez(self):
        decididas = ds.acoes_ja_decididas([{"task_id": "t1", "status": ds.STATUS_NUNCA}])
        self.assertEqual(ds.candidatas([_tarefa(pool_dados=[_anexo("X.md")])], decididas, HOJE), [])

    def test_nunca_vence_status_gravado_depois(self):
        decididas = ds.acoes_ja_decididas([
            {"task_id": "t1", "status": ds.STATUS_NUNCA},
            {"task_id": "t1", "status": ds.STATUS_PENDENTE},
        ])
        self.assertEqual(decididas["t1"], ds.STATUS_NUNCA)

    def test_pendente_tambem_bloqueia(self):
        """Propor de novo o que ja esta na fila e o jeito de o usuario parar de ler a fila."""
        decididas = ds.acoes_ja_decididas([{"task_id": "t1", "status": ds.STATUS_PENDENTE}])
        self.assertEqual(ds.candidatas([_tarefa(pool_dados=[_anexo("X.md")])], decididas, HOJE), [])

    def test_adiada_volta_a_ser_candidata(self):
        """"Agora nao" e sobre o momento, nao sobre a acao."""
        decididas = ds.acoes_ja_decididas([{"task_id": "t1", "status": ds.STATUS_ADIADA}])
        self.assertEqual(len(ds.candidatas([_tarefa(pool_dados=[_anexo("X.md")])], decididas, HOJE)), 1)


class TestSaudeFicaDeFora(unittest.TestCase):
    """Regra transversal: objetivo servido por dado nunca entra em candidato.

    Sem a exclusao, o pilar Saude passaria a exibir progresso feito de contagem
    de acao, concorrendo com o numero real que vem do peso — e a fila encheria de
    caminhada, fisioterapia e consulta.
    """

    def test_objetivo_com_flag_falsa_sai(self):
        objetivos = [
            {"id": "saude", "pilar": "saude", "gerida_por_acoes": False, "status": "ativo"},
            {"id": "intel", "pilar": "intelectual", "gerida_por_acoes": True, "status": "ativo"},
        ]
        self.assertEqual([o["id"] for o in ds.objetivos_elegiveis(objetivos)], ["intel"])

    def test_exclusao_e_pela_flag_e_nao_pelo_nome_do_pilar(self):
        """Objetivo novo orientado a dado nasce fora sem ninguem editar codigo."""
        objetivos = [{"id": "fin", "pilar": "financas", "gerida_por_acoes": False, "status": "ativo"}]
        self.assertEqual(ds.objetivos_elegiveis(objetivos), [])

    def test_sem_flag_gravada_deriva_do_pilar(self):
        objetivos = [{"id": "saude", "pilar": "saude", "status": "ativo"}]
        self.assertEqual(ds.objetivos_elegiveis(objetivos), [])

    def test_objetivo_concluido_nao_recebe_elevacao(self):
        objetivos = [{"id": "x", "pilar": "carreira", "status": "concluido"}]
        self.assertEqual(ds.objetivos_elegiveis(objetivos), [])


class TestAPropostaDaIA(unittest.TestCase):
    """A regra que impede o vinculo decorativo, aplicada ao que o modelo devolve."""

    BASE = {
        "task_id": "sispnaes", "objetivo_id": "intel", "motivo_escassez": "ja_escrito",
        "ativo_possivel": "Relato de experiencia sobre transicao de conhecimento",
        "justificativa": "O handoff ja documenta o metodo de transicao em TI publica.",
        "o_que_ja_existe": "docs/HANDOFF-SISPNAES.md, 12 secoes",
        "passo_que_falta": "Tirar o que e especifico do Ifes e escrever a introducao",
        "custo_estimado": "uma tarde",
    }

    def _validar(self, **over):
        return ds.validar_proposta({**self.BASE, **over}, {"intel"}, {"sispnaes"})

    def test_proposta_completa_passa(self):
        self.assertEqual(self._validar()["motivo_escassez"], "ja_escrito")

    def test_sem_justificativa_nao_propoe(self):
        """Se a IA nao consegue escrever a frase, nao propoe."""
        self.assertIsNone(self._validar(justificativa=""))

    def test_justificativa_generica_demais_nao_passa(self):
        self.assertIsNone(self._validar(justificativa="Serve."))

    def test_motivo_de_escassez_invalido_nao_passa(self):
        self.assertIsNone(self._validar(motivo_escassez="parece_legal"))

    def test_objetivo_fora_da_lista_nao_passa(self):
        """Inclui o caso de a IA apontar um objetivo orientado a dado."""
        self.assertIsNone(ds.validar_proposta(self.BASE, {"outro"}, {"sispnaes"}))

    def test_acao_inventada_nao_passa(self):
        self.assertIsNone(ds.validar_proposta(self.BASE, {"intel"}, {"outra"}))

    def test_sem_o_que_ja_existe_nao_passa(self):
        self.assertIsNone(self._validar(o_que_ja_existe=""))

    def test_custo_ausente_vira_texto_honesto(self):
        self.assertEqual(self._validar(custo_estimado="")["custo_estimado"], "nao estimado")


class TestAJanelaDasConclusoes(unittest.TestCase):
    """De quando contar as conclusoes, e por que nao e uma janela fixa.

    Janela fixa a partir de hoje perde o intervalo inteiro quando uma varredura
    falha ou e pulada — e perde em silencio, que e o pior jeito de perder.
    Ancorada na ultima bem-sucedida, ela cresce sozinha para cobrir o buraco.
    """

    def test_ancora_na_ultima_varredura_e_nao_em_hoje_menos_sete(self):
        corte, motivo = ds.janela_de_conclusao("2026-08-23", "2026-08-30")
        self.assertEqual(corte, "2026-08-23")
        self.assertEqual(motivo, "")

    def test_varredura_pulada_faz_a_janela_crescer(self):
        """O caso que motiva tudo: domingo falhou, o domingo seguinte tem de cobrir os dois."""
        corte, _ = ds.janela_de_conclusao("2026-08-16", "2026-08-30")
        self.assertEqual(corte, "2026-08-16")

    def test_sem_marcador_o_teto_de_dias_segura_o_passivo(self):
        """Primeira rodada nao pode significar "desde sempre"."""
        corte, motivo = ds.janela_de_conclusao("", "2026-08-30")
        self.assertEqual(corte, "2026-08-23")
        self.assertEqual(motivo, "sem_marcador")

    def test_o_corte_por_falta_de_marcador_e_dito_e_nao_silencioso(self):
        """Perder conclusoes pode ser aceitavel; perder sem avisar nao e."""
        self.assertTrue(ds.janela_de_conclusao(None, "2026-08-30")[1])

    def test_a_hora_do_marcador_nao_atrapalha_a_comparacao(self):
        corte, _ = ds.janela_de_conclusao("2026-08-23T18:00:00Z", "2026-08-30")
        self.assertEqual(corte, "2026-08-23")


class TestOMarcadorSoAvancaQuandoOlhou(unittest.TestCase):
    """Marcador avancado sem olhar apaga o intervalo para sempre.

    E o mesmo defeito que a janela ancorada existe para evitar, so que pela
    outra ponta: se "semana cheia" avancasse o marcador, as conclusoes daquela
    semana nunca mais seriam candidatas.
    """

    def test_o_marcador_volta_do_firestore(self):
        db = _Db()
        ds.marcar_varredura(db, "2026-08-30")
        self.assertEqual(ds.ultima_varredura(db), "2026-08-30")

    def test_marcador_ausente_e_vazio_e_nao_erro(self):
        self.assertEqual(ds.ultima_varredura(_Db()), "")

    def test_falha_de_leitura_levanta_em_vez_de_virar_vazio(self):
        """Ausente e ilegivel parecem iguais e nao sao.

        Sem marcador nao ha intervalo anterior a perder. Com marcador ilegivel ha:
        a janela cairia no teto de dias, a rodada terminaria gravando hoje, e tudo
        entre o marcador verdadeiro e o teto sumiria para sempre.
        """
        class _DbQuebrado:
            def collection(self, _n):
                raise RuntimeError("indisponivel")
        with self.assertRaises(ds.MarcadorIndisponivel):
            ds.ultima_varredura(_DbQuebrado())

    def test_marcador_ilegivel_aborta_a_rodada(self):
        class _DbQuebrado(_Db):
            def collection(self, nome):
                if nome == "system_usage":
                    raise RuntimeError("indisponivel")
                return super().collection(nome)

        db = _DbQuebrado()
        # Com objetivo elegivel, para a rodada chegar ate a leitura do marcador em
        # vez de sair antes por falta de objetivo.
        db.collection("estrategia_pessoal").dados["intel"] = {
            "objetivoMacro": "Autoridade intelectual", "pilar": "intelectual",
            "gerida_por_acoes": True}
        rodada = ds.preparar_rodada(db, HOJE, [])
        self.assertFalse(rodada["rodar"])
        self.assertEqual(rodada["motivo"], "marcador_indisponivel")
        self.assertFalse(rodada.get("pode_marcar"))

    def test_semana_cheia_nao_libera_o_marcador(self):
        """`rodar_deteccao` so avanca com `pode_marcar`; aqui ele nao vem."""
        db = _Db()
        cheia = [{"data": HOJE, "total": ds.SEMANA_CHEIA_ACOES + 1}]
        rodada = ds.preparar_rodada(db, HOJE, cheia)
        self.assertFalse(rodada["rodar"])
        self.assertFalse(rodada.get("pode_marcar"))

    def test_nenhuma_acao_com_corpo_avanca_porque_olhou(self):
        """Olhou e nao achou: nada foi perdido, entao a janela nao precisa crescer."""
        db = _Db()
        db.collection("estrategia_pessoal").dados["intel"] = {
            "objetivoMacro": "Autoridade intelectual", "pilar": "intelectual",
            "gerida_por_acoes": True}
        rodada = ds.preparar_rodada(db, HOJE, [])
        self.assertEqual(rodada["motivo"], "nenhuma_acao_com_corpo")
        self.assertTrue(rodada["pode_marcar"])


class TestJanelaRelidaNaoRepeteCard(unittest.TestCase):
    """A outra ponta da janela ancorada.

    Quando o marcador NAO avanca — teto do mes, semana cheia, falha do modelo —
    a rodada seguinte rele a mesma janela de propósito, para nao perder nada. Se
    a deduplicacao nao alcancasse o que ja esta pendente na fila, o mecanismo que
    evita perda passaria a produzir card repetido, que e o jeito mais rapido de o
    usuario parar de ler a fila.

    A garantia esta em dois lugares que precisam valer juntos: `_carregar_sugestoes`
    traz TODA pendente e aceita, de qualquer epoca (sem recorte de data), e
    `candidatas` corta por esse conjunto.
    """

    def _db(self, status_da_sugestao):
        db = _Db()
        db.collection("estrategia_pessoal").dados["intel"] = {
            "objetivoMacro": "Autoridade intelectual", "pilar": "intelectual",
            "gerida_por_acoes": True}
        db.collection("tarefas").dados["sispnaes"] = _tarefa(
            id="sispnaes", status="em andamento", pool_dados=[_anexo("HANDOFF.md")])
        db.collection(ds.COL_ELEVACOES).dados["s1"] = {
            "task_id": "sispnaes", "status": status_da_sugestao,
            "criada_em": "2026-07-05"}
        return db

    def test_pendente_de_outro_mes_ainda_bloqueia_a_releitura(self):
        """O recorte de pendentes nao tem limite de data justamente para isto."""
        rodada = ds.preparar_rodada(self._db(ds.STATUS_PENDENTE), HOJE, [])
        self.assertFalse(rodada["rodar"])
        self.assertEqual(rodada["motivo"], "nenhuma_acao_com_corpo")

    def test_aceita_tambem_bloqueia(self):
        rodada = ds.preparar_rodada(self._db(ds.STATUS_ACEITA), HOJE, [])
        self.assertEqual(rodada["motivo"], "nenhuma_acao_com_corpo")

    def test_adiada_volta_porque_agora_nao_e_sobre_o_momento(self):
        rodada = ds.preparar_rodada(self._db(ds.STATUS_ADIADA), HOJE, [])
        self.assertTrue(rodada["rodar"])
        self.assertEqual([c["task_id"] for c in rodada["candidatos"]], ["sispnaes"])


class TestOModoDegradadoNaoMorreNoLog(unittest.TestCase):
    """Varredura sem o indice roda, nao da erro, e so deixa de ver o melhor caso.

    Silenciosa por natureza — e por isso o estado fica gravado, para o resumo
    matinal mostrar. Log nao e aviso.
    """

    def _db_sem_indice(self):
        class _RecorteQuebrado(_Recorte):
            def where(self, *a, **kw):
                f = kw.get("filter")
                if f is not None and f.field_path == "data_conclusao":
                    raise RuntimeError("indice composto ausente")
                r = _Recorte.where(self, *a, **kw)
                return _RecorteQuebrado(r._dados, r._ids, r._n)

        class _ColQuebrada(_Colecao):
            def where(self, *a, **kw):
                r = _Colecao.where(self, *a, **kw)
                return _RecorteQuebrado(r._dados, r._ids, r._n)

        db = _Db()
        db.cols["tarefas"] = _ColQuebrada()
        db.collection("estrategia_pessoal").dados["intel"] = {
            "objetivoMacro": "Autoridade intelectual", "pilar": "intelectual",
            "gerida_por_acoes": True}
        return db

    @staticmethod
    def _estado(db):
        return (ds._marcador_de_varredura(db).get().to_dict() or {}).get("varredura_degradada")

    def test_a_rodada_sem_indice_grava_o_aviso(self):
        db = self._db_sem_indice()
        ds.preparar_rodada(db, HOJE, [])
        estado = self._estado(db)
        self.assertEqual(estado["motivo"], "indice_ausente")
        self.assertEqual(estado["data"], HOJE)

    def test_a_rodada_completa_limpa_o_aviso(self):
        """E estado, nao evento: fica ate uma varredura completa desligar."""
        db = self._db_sem_indice()
        ds.preparar_rodada(db, HOJE, [])
        self.assertIsNotNone(self._estado(db))

        db.cols["tarefas"] = _Colecao()
        ds.preparar_rodada(db, HOJE, [])
        self.assertIsNone(self._estado(db))

    def test_rodada_degradada_nao_libera_o_marcador(self):
        """O pior jeito de a correcao chegar tarde demais.

        Sem isto, a rodada sem indice avancaria o marcador para hoje. Publicar o
        indice depois nao adiantaria: a janela seguinte comeca depois das
        conclusoes que a rodada degradada nunca viu, e elas somem para sempre.
        """
        db = self._db_sem_indice()
        db.cols["tarefas"].dados["viva"] = _tarefa(
            id="viva", status="em andamento", pool_dados=[_anexo("X.md")])
        self.assertFalse(ds.preparar_rodada(db, HOJE, [])["pode_marcar"])

    def test_degradada_sem_candidata_tambem_nao_libera(self):
        """"Olhou e nao achou" so vale quando olhou a janela inteira."""
        rodada = ds.preparar_rodada(self._db_sem_indice(), HOJE, [])
        self.assertEqual(rodada["motivo"], "nenhuma_acao_com_corpo")
        self.assertFalse(rodada["pode_marcar"])

    def test_o_aviso_nao_impede_a_rodada(self):
        """Perder as concluidas numa rodada e melhor que perder a rodada."""
        db = self._db_sem_indice()
        db.cols["tarefas"].dados["viva"] = _tarefa(
            id="viva", status="em andamento", pool_dados=[_anexo("X.md")])
        rodada = ds.preparar_rodada(db, HOJE, [])
        self.assertTrue(rodada["rodar"])


class TestTodoCaminhoQueConcluiGravaAData(unittest.TestCase):
    """A varredura le `data_conclusao`; quem conclui sem gravar cria um buraco.

    Acao concluida sem a data sai da consulta de vivas e nao entra na de
    concluidas: some da varredura para sempre, e some em silencio — o status fica
    certo, so a data falta.

    Ja aconteceu com a ponte de voz, que eu tinha deixado de fora ao enumerar os
    caminhos. A checagem e estatica e por texto porque a ponte e outro servico,
    sem suite de teste e sem importar daqui; imperfeita, mas quebra se alguem
    tirar a gravacao de volta, que e o que interessa.
    """

    @staticmethod
    def _fonte(caminho):
        alvo = os.path.join(os.path.dirname(os.path.dirname(__file__)), caminho)
        with open(alvo, encoding="utf-8") as f:
            return f.read()

    def test_a_ponte_de_voz_grava_data_conclusao(self):
        fonte = self._fonte(os.path.join("hermes-voice-bridge", "task_tools.py"))
        inicio = fonte.index("def _mudar_status_acao")
        corpo = fonte[inicio:inicio + 3000]
        self.assertIn("data_conclusao", corpo,
                      "A ponte de voz voltou a concluir acao sem gravar data_conclusao; "
                      "essas acoes ficam invisiveis para a varredura de elevacao.")


class TestJanelaMaiorQueOTetoDaConsulta(unittest.TestCase):
    """Mais conclusoes na janela do que a consulta traz.

    Acontece depois de varias varreduras puladas, ou num passivo grande. A rodada
    avalia uma pagina e nada indica que havia mais — entao, se o marcador
    avancasse, as conclusoes que sobraram ficariam fora de TODA janela futura.
    """

    def _db(self, quantas):
        db = _Db()
        db.collection("estrategia_pessoal").dados["intel"] = {
            "objetivoMacro": "Autoridade intelectual", "pilar": "intelectual",
            "gerida_por_acoes": True}
        for i in range(quantas):
            db.collection("tarefas").dados[f"c{i}"] = _tarefa(
                id=f"c{i}", status="concluído", data_conclusao="2026-08-28",
                pool_dados=[_anexo("X.md")])
        return db

    def test_bater_no_teto_nao_libera_o_marcador(self):
        db = self._db(ds.LIMITE_TAREFAS)
        self.assertFalse(ds.preparar_rodada(db, HOJE, [])["pode_marcar"])

    def test_abaixo_do_teto_libera(self):
        db = self._db(3)
        self.assertTrue(ds.preparar_rodada(db, HOJE, [])["pode_marcar"])

    def test_o_truncamento_vira_aviso_e_nao_so_log(self):
        db = self._db(ds.LIMITE_TAREFAS)
        ds.preparar_rodada(db, HOJE, [])
        estado = (ds._marcador_de_varredura(db).get().to_dict() or {}).get("varredura_degradada")
        self.assertEqual(estado["motivo"], "limite_atingido")

    def test_a_rodada_continua_com_o_que_deu_para_ver(self):
        """Ver parte e melhor que nao ver nada; o que nao pode e dizer que viu tudo."""
        self.assertTrue(ds.preparar_rodada(self._db(ds.LIMITE_TAREFAS), HOJE, [])["rodar"])


class TestAPropostaDePassivoEAceita(unittest.TestCase):
    """A cota so serve para alguma coisa se a proposta de passivo puder ser gravada.

    `validar_proposta` confere o `task_id` contra o conjunto de candidatas da
    rodada. Se esse conjunto sair so de `candidatos`, todo id de passivo e
    recusado como inexistente — a cota inteira vira no-op, e o cursor avanca por
    cima, descartando aquelas acoes em silencio. E a mesma falha de sempre: fonte
    nova que nao atravessa todos os consumidores.
    """

    def _rodada(self):
        return {
            "restantes": 3,
            "ja_no_mes": 0,
            "objetivos": [{"id": "intel", "objetivoMacro": "Autoridade intelectual",
                           "pilar": "intelectual"}],
            "candidatos": [],
            "passivo": [{
                "task_id": "antiga", "passivo": True,
                "tarefa": _tarefa(id="antiga", titulo="Handoff de 2024",
                                  status="concluído"),
                "corpo": {"documentos": ["H.md"], "etapas_feitas": 0,
                          "tem_texto_pronto": True, "caracteres_diario": 0},
            }],
        }

    def test_o_id_de_passivo_e_valido_para_a_ferramenta(self):
        gravadas = []
        _tools, mapa = ds._ferramenta_propor(
            _Db(), HOJE, self._rodada(), gravadas,
            reservar=lambda *a, **k: True)
        r = mapa["propor_elevacao"](
            task_id="antiga", objetivo_id="intel", motivo_escassez="ja_escrito",
            o_que_ja_existe="handoff pronto", passo_que_falta="publicar",
            custo_estimado="uma tarde", ativo_possivel="Relato de experiencia",
            justificativa="O handoff ja e o texto do relato.")
        self.assertNotIn("erro", str(r).lower())
        # `aceitas` guarda o id da reserva, que carrega o mes e a acao.
        self.assertEqual(gravadas, [ds.id_da_reserva(HOJE, "antiga")])


class TestAContagemDoQueFaltaDoPassivo(unittest.TestCase):
    """`restantes` e o numero que decide quando mandar parar. Errado, nao serve.

    O cursor carrega `data|task_id` justamente por causa de empate de data.
    Contar o dia inteiro do cursor incluiria ele proprio e as irmas ja
    percorridas, e o numero ficaria travado num valor que nunca desce.
    """

    def _db(self):
        db = _Db()
        for i in range(4):
            db.collection("tarefas").dados[f"a{i}"] = {
                "status": "concluído", "data_conclusao": "2026-05-10"}
        for i in range(3):
            db.collection("tarefas").dados[f"b{i}"] = {
                "status": "concluído", "data_conclusao": "2026-04-01"}
        return db

    def test_conta_so_o_que_esta_atras_do_cursor(self):
        # Cursor em a1: sobram a0 (mesmo dia, id menor) e os tres de abril.
        self.assertEqual(ds.contar_passivo(self._db(), "2026-05-10|a1", "2026-08-29"), 4)

    def test_o_cursor_e_as_irmas_ja_passadas_nao_contam(self):
        """Com o dia inteiro contado seriam 7; a2 e a3 ja passaram."""
        self.assertNotEqual(ds.contar_passivo(self._db(), "2026-05-10|a3", "2026-08-29"), 7)

    def test_no_fim_do_caminho_o_numero_zera(self):
        self.assertEqual(ds.contar_passivo(self._db(), "2026-04-01|b0", "2026-08-29"), 0)


class TestConcluidaQueGanhaCorpoDepois(unittest.TestCase):
    """Acao concluida PODE ganhar corpo depois, e sem isto sumiria para sempre.

    Nao ha guarda de status em `anexar_arquivo` nem na tela de execucao, que
    grava `pool_dados` direto. E o caso e plausivel exatamente aqui: escrever o
    handoff depois de fechar a acao.

    A janela nao a alcanca (`data_conclusao` nao mudou) e o cursor do passivo ja
    passou por ela quando estava vazia. `data_atualizacao` e o unico campo que
    reflete o anexo novo — dai o terceiro recorte.
    """

    def _db(self, data_atualizacao):
        db = _Db()
        db.collection("tarefas").dados["antiga"] = _tarefa(
            id="antiga", status="concluído",
            data_conclusao="2024-03-01",
            data_atualizacao=data_atualizacao,
            pool_dados=[_anexo("Handoff.md")])
        return db

    def test_mexida_depois_do_corte_volta_a_ser_vista(self):
        tarefas, _inc = ds._tarefas_da_varredura(self._db("2026-08-28"), "2026-08-23")
        self.assertEqual([t["id"] for t in tarefas], ["antiga"])

    def test_intocada_continua_fora_da_janela(self):
        """Senao o terceiro recorte traria o passivo inteiro pela porta da janela."""
        tarefas, _inc = ds._tarefas_da_varredura(self._db("2024-03-01"), "2026-08-23")
        self.assertEqual(tarefas, [])

    def test_nao_duplica_com_a_consulta_da_janela(self):
        db = self._db("2026-08-28")
        db.cols["tarefas"].dados["antiga"]["data_conclusao"] = "2026-08-28"
        tarefas, _inc = ds._tarefas_da_varredura(db, "2026-08-23")
        self.assertEqual(len(tarefas), 1)


class TestOPassivoEntraPorCota(unittest.TestCase):
    """618 concluidas de passivo, 124 com corpo. De uma vez, fila ilegivel.

    A cota caminha do mais recente para o mais antigo, com cursor proprio, e
    soma-se as concluidas da janela em vagas separadas do prompt.
    """

    def _db(self, quantas=30, com_corpo=True, ano="2026"):
        db = _Db()
        db.collection("estrategia_pessoal").dados["intel"] = {
            "objetivoMacro": "Autoridade intelectual", "pilar": "intelectual",
            "gerida_por_acoes": True}
        for i in range(quantas):
            db.collection("tarefas").dados[f"p{i:03d}"] = _tarefa(
                id=f"p{i:03d}", status="concluído",
                data_conclusao=f"{ano}-01-{(i % 28) + 1:02d}",
                pool_dados=[_anexo("Doc.md")] if com_corpo else [])
        return db

    def test_a_cota_limita_quantas_saem_por_rodada(self):
        rodada = ds.preparar_rodada(self._db(), "2026-08-29", [])
        self.assertEqual(len(rodada["passivo"]), ds.COTA_PASSIVO)

    def test_vem_do_mais_recente_para_o_mais_antigo(self):
        rodada = ds.preparar_rodada(self._db(), "2026-08-29", [])
        datas = [c["tarefa"]["data_conclusao"] for c in rodada["passivo"]]
        self.assertEqual(datas, sorted(datas, reverse=True))

    def test_a_rodada_seguinte_continua_de_onde_parou(self):
        db = self._db()
        primeira = ds.preparar_rodada(db, "2026-08-29", [])
        ds.avancar_passivo(db, primeira["passivo_cursor"], False, None)
        segunda = ds.preparar_rodada(db, "2026-08-29", [])
        ids_1 = {c["task_id"] for c in primeira["passivo"]}
        ids_2 = {c["task_id"] for c in segunda["passivo"]}
        self.assertEqual(ids_1 & ids_2, set())

    def test_sem_corpo_nao_gasta_cota_e_nao_volta(self):
        """As 494 sem corpo levariam um ano para passar se gastassem cota.

        A cota e de CANDIDATAS, nao de documentos lidos: a rodada atravessa o que
        nao tem corpo para chegar no que tem. Aqui ha 25 sem corpo na frente e
        uma com corpo atras — se o descarte gastasse cota, ela nao seria
        alcancada nesta rodada.
        """
        db = _Db()
        db.collection("estrategia_pessoal").dados["intel"] = {
            "objetivoMacro": "Autoridade intelectual", "pilar": "intelectual",
            "gerida_por_acoes": True}
        for i in range(25):
            db.collection("tarefas").dados[f"vazia{i:03d}"] = _tarefa(
                id=f"vazia{i:03d}", status="concluído",
                data_conclusao=f"2026-03-{i + 1:02d}", pool_dados=[])
        db.collection("tarefas").dados["fundo"] = _tarefa(
            id="fundo", status="concluído", data_conclusao="2026-01-01",
            pool_dados=[_anexo("Handoff.md")])
        rodada = ds.preparar_rodada(db, "2026-08-29", [])
        self.assertEqual([c["task_id"] for c in rodada["passivo"]], ["fundo"])

    def test_o_cursor_anda_sobre_o_que_foi_descartado(self):
        """Concluida sem corpo nao ganha corpo depois: voltar nela e caminhar no lugar."""
        db = self._db(quantas=12, com_corpo=False)
        primeira = ds.preparar_rodada(db, "2026-08-29", [])
        self.assertTrue(primeira["passivo_cursor"])
        ds.avancar_passivo(db, primeira["passivo_cursor"], False, None)
        tarefas, _c, _e = ds._passivo(db, "2026-08-29",
                                      ds.cursor_do_passivo(db), ds.COTA_PASSIVO, {})
        self.assertEqual(tarefas, [])

    def test_o_passivo_nao_segura_o_marcador_da_janela(self):
        """Cursor proprio. Confundir os dois travaria o marcador para sempre."""
        rodada = ds.preparar_rodada(self._db(), "2026-08-29", [])
        self.assertTrue(rodada["pode_marcar"])

    def test_o_prompt_reserva_vagas_para_o_passivo(self):
        """Somar e cortar faria o passivo perder toda disputa de ordenacao."""
        db = self._db()
        for i in range(ds.LIMITE_CANDIDATAS + 5):
            db.collection("tarefas").dados[f"v{i}"] = _tarefa(
                id=f"v{i}", status="em andamento", pool_dados=[_anexo("X.md")])
        rodada = ds.preparar_rodada(db, "2026-08-29", [])
        mensagem = ds.mensagem_da_rodada(rodada)
        self.assertEqual(mensagem.count('"passivo": true'), ds.COTA_PASSIVO)
        self.assertIn("marcadas como passivo", mensagem)

    def test_ja_decidida_nao_gasta_cota(self):
        db = self._db()
        decididas = [{"task_id": f"p{i:03d}", "status": ds.STATUS_NUNCA} for i in range(5)]
        db.collection(ds.COL_ELEVACOES).dados = {
            f"s{i}": {**d, "criada_em": "2026-01-01"} for i, d in enumerate(decididas)}
        rodada = ds.preparar_rodada(db, "2026-08-29", [])
        self.assertEqual(len(rodada["passivo"]), ds.COTA_PASSIVO)
        for c in rodada["passivo"]:
            self.assertNotIn(c["task_id"], {d["task_id"] for d in decididas})

    def test_sem_corte_por_ano(self):
        """A ordem decrescente ja entrega primeiro o que tem valor; nao ha filtro."""
        rodada = ds.preparar_rodada(self._db(quantas=12, ano="2015"), "2026-08-29", [])
        self.assertEqual(len(rodada["passivo"]), ds.COTA_PASSIVO)

    def test_o_cursor_desempata_por_id(self):
        """Varias acoes na mesma data: cursor so de data pularia as irmas."""
        db = self._db()
        for i in range(6):
            db.collection("tarefas").dados[f"empate{i}"] = _tarefa(
                id=f"empate{i}", status="concluído", data_conclusao="2026-02-10",
                pool_dados=[_anexo("Doc.md")])
        vistos = set()
        cursor = ""
        for _ in range(8):
            tarefas, cursor, _esg = ds._passivo(db, "2026-08-29", cursor, 3, {})
            for t in tarefas:
                self.assertNotIn(t["id"], vistos)
                vistos.add(t["id"])
        self.assertGreaterEqual(len({v for v in vistos if v.startswith("empate")}), 5)


class TestORecorteDoPromptTambemSeguraOMarcador(unittest.TestCase):
    """`mensagem_da_rodada` mostra so as primeiras N candidatas.

    O marcador nao pode dizer "tudo avaliado" por cima do que o modelo nunca viu.
    Mas a espera e assimetrica de proposito: viva que sobra volta sozinha na
    proxima rodada (a consulta dela e por status, sem data); concluida que sobra
    so existe dentro da janela, e a janela anda com o marcador.
    """

    @staticmethod
    def _candidatos(status_da_sobra):
        vistas = [{"task_id": f"v{i}", "tarefa": {"status": "em andamento"}}
                  for i in range(ds.LIMITE_CANDIDATAS)]
        return vistas + [{"task_id": "sobra", "tarefa": {"status": status_da_sobra}}]

    def test_concluida_fora_do_recorte_segura_o_marcador(self):
        self.assertFalse(ds.viu_todas_as_concluidas(self._candidatos("concluído")))

    def test_viva_fora_do_recorte_nao_segura(self):
        """Travar aqui pararia o marcador em toda semana movimentada."""
        self.assertTrue(ds.viu_todas_as_concluidas(self._candidatos("em andamento")))

    def test_dentro_do_limite_nada_segura(self):
        dentro = [{"task_id": "c", "tarefa": {"status": "concluído"}}]
        self.assertTrue(ds.viu_todas_as_concluidas(dentro))

    def test_sem_candidata_nenhuma_nao_segura(self):
        self.assertTrue(ds.viu_todas_as_concluidas([]))

    def test_a_rodada_inteira_respeita_isso(self):
        db = _Db()
        db.collection("estrategia_pessoal").dados["intel"] = {
            "objetivoMacro": "Autoridade intelectual", "pilar": "intelectual",
            "gerida_por_acoes": True}
        # Vivas com diario grande vao para a frente da ordenacao; a concluida com
        # anexo de texto tambem tem corpo, mas fica na sobra por volume de diario.
        for i in range(ds.LIMITE_CANDIDATAS):
            db.collection("tarefas").dados[f"v{i}"] = _tarefa(
                id=f"v{i}", status="em andamento",
                pool_dados=[_anexo("Doc.md")],
                acompanhamento=[{"nota": "x" * 5000}])
        db.collection("tarefas").dados["c"] = _tarefa(
            id="c", status="concluído", data_conclusao="2026-08-28",
            pool_dados=[_anexo("Handoff.md")])
        rodada = ds.preparar_rodada(db, HOJE, [])
        self.assertTrue(rodada["rodar"])
        self.assertFalse(rodada["pode_marcar"])
        estado = (ds._marcador_de_varredura(db).get().to_dict() or {}).get("varredura_degradada")
        self.assertEqual(estado["motivo"], "candidatas_demais")


class TestAsConcluidasEntramNaVarredura(unittest.TestCase):
    """O caso que sumia era o melhor: acao terminada na semana e a que com mais
    certeza deixou documento, diario e etapas prontas. O docstring de
    `candidatas` sempre disse que conclusao nao filtra; a consulta a removia
    antes de ela ser chamada.
    """

    @staticmethod
    def _db_com(*tarefas):
        db = _Db()
        for i, t in enumerate(tarefas):
            db.collection("tarefas").dados[t.get("id") or f"t{i}"] = t
        return db

    def test_concluida_dentro_da_janela_entra(self):
        db = self._db_com({"id": "a", "status": "concluído",
                           "data_conclusao": "2026-08-28T10:00:00Z"})
        tarefas, degradacao = ds._tarefas_da_varredura(db, "2026-08-23")
        self.assertEqual([t["id"] for t in tarefas], ["a"])
        self.assertEqual(degradacao, "")

    def test_concluida_antes_do_corte_fica_de_fora(self):
        db = self._db_com({"id": "a", "status": "concluído",
                           "data_conclusao": "2026-08-01"})
        self.assertEqual(ds._tarefas_da_varredura(db, "2026-08-23")[0], [])

    def test_concluida_sem_data_e_passivo_e_nao_regressao(self):
        db = self._db_com({"id": "a", "status": "concluído"})
        self.assertEqual(ds._tarefas_da_varredura(db, "2026-08-23")[0], [])

    def test_as_vivas_continuam_entrando(self):
        db = self._db_com({"id": "viva", "status": "em andamento"},
                          {"id": "parada", "status": "stand-by"},
                          {"id": "velha", "status": "concluído",
                           "data_conclusao": "2020-01-01"})
        self.assertEqual(sorted(t["id"] for t in ds._tarefas_da_varredura(db, "2026-08-23")[0]),
                         ["parada", "viva"])

    def test_cancelada_nunca_entra(self):
        db = self._db_com({"id": "a", "status": "cancelada",
                           "data_conclusao": "2026-08-28"})
        self.assertEqual(ds._tarefas_da_varredura(db, "2026-08-23")[0], [])

    def test_sem_o_indice_a_rodada_segue_com_as_vivas(self):
        """Perder as concluidas numa rodada e melhor que perder a rodada."""
        class _RecorteQuebrado(_Recorte):
            """Levanta no filtro de `data_conclusao`, como o Firestore faz sem o
            indice composto. Precisa ser no `_Recorte` e nao na colecao: o
            segundo `where` da cadeia ja e chamado no recorte."""

            def where(self, *a, **kw):
                f = kw.get("filter")
                if f is not None and f.field_path == "data_conclusao":
                    raise RuntimeError("indice composto ausente")
                r = _Recorte.where(self, *a, **kw)
                return _RecorteQuebrado(r._dados, r._ids, r._n)

        class _ColQuebrada(_Colecao):
            def where(self, *a, **kw):
                r = _Colecao.where(self, *a, **kw)
                return _RecorteQuebrado(r._dados, r._ids, r._n)

        db = _Db()
        db.cols["tarefas"] = _ColQuebrada()
        db.cols["tarefas"].dados["viva"] = {"id": "viva", "status": "em andamento"}
        tarefas, degradacao = ds._tarefas_da_varredura(db, "2026-08-23")
        self.assertEqual([t["id"] for t in tarefas], ["viva"])
        self.assertIn("indice", degradacao)


class _Snap:
    def __init__(self, col, doc_id):
        self._col, self.id = col, doc_id
        self.exists = doc_id in col

    def to_dict(self):
        return dict(self._col.get(self.id) or {})


class _Ref:
    def __init__(self, col, doc_id):
        self._col, self.id = col, doc_id
        self._subcols = {}

    def set(self, dados, merge=False):
        if merge:
            self._col.setdefault(self.id, {}).update(dados)
        else:
            self._col[self.id] = dict(dados)

    def get(self, transaction=None):
        return _Snap(self._col, self.id)

    def update(self, dados):
        self._col.setdefault(self.id, {}).update(dados)

    def collection(self, nome):
        return self._subcols.setdefault(nome, _Colecao())


class _Transacao:
    """Transacao falsa: aplica na hora, sem isolamento.

    A atomicidade real e do Firestore e nao da para exercitar aqui. O que estes
    testes cobrem e o corpo da transacao — a ordem das leituras e escritas, de
    qual mes a vaga volta, e o que acontece quando a sugestao ja saiu de
    pendente. O que se ganha por ter o corpo separado do decorador e justamente
    poder testar essa logica sem Firestore.
    """

    def update(self, ref, dados):
        ref.update(dados)

    def set(self, ref, dados, merge=False):
        if merge and ref.get().exists:
            ref.update(dados)
        else:
            ref.set(dados)


def _aplicar(db, ref, alvo, hoje):
    """O `aplicar` de producao, com a transacao trocada pela falsa."""
    return ds._corpo_da_decisao(_Transacao(), ref,
                                lambda mes: ds._contador_do_mes(db, mes), alvo, hoje)


class _Colecao:
    def __init__(self):
        self.dados, self._seq, self._subcols = {}, 0, {}

    def document(self, doc_id=None):
        if doc_id is None:
            self._seq += 1
            doc_id = f"s{self._seq}"
        doc_id = str(doc_id)
        ref = _Ref(self.dados, doc_id)
        # As subcolecoes vivem na colecao e nao no `_Ref`, porque `document()`
        # devolve um `_Ref` novo a cada chamada — no contador do mes, a segunda
        # chamada precisa enxergar o que a primeira gravou.
        ref._subcols = self._subcols.setdefault(doc_id, {})
        return ref

    def limit(self, n):
        return _Recorte(self.dados, list(self.dados), n)

    def where(self, *a, **kw):
        return _Recorte(self.dados, list(self.dados), None).where(*a, **kw)

    def stream(self):
        return [_Snap(self.dados, i) for i in list(self.dados)]


class _Recorte:
    """Consulta falsa que aplica `where` ANTES de `limit`, como o Firestore.

    A versao anterior deste fake ignorava os filtros e devolvia a colecao
    inteira. Um teste em cima dele nao distinguiria filtrar na consulta de
    filtrar depois de ler — que e exatamente o defeito que estes testes
    precisam pegar.
    """

    def __init__(self, dados, ids, n):
        self._dados, self._ids, self._n = dados, ids, n

    def where(self, *a, **kw):
        f = kw.get("filter")
        if f is not None:
            campo, op, valor = f.field_path, f.op_string, f.value
        else:
            # A forma posicional antiga (`where("status", "in", [...])`) ainda e
            # usada na consulta de tarefas; o fake aceita as duas.
            campo, op, valor = a[0], a[1], a[2]
        def passa(doc_id):
            atual = (self._dados.get(doc_id) or {}).get(campo)
            if op == "==":
                return atual == valor
            if op == "in":
                return atual in valor
            if op == ">=":
                return atual is not None and str(atual) >= str(valor)
            if op == "<=":
                return atual is not None and str(atual) <= str(valor)
            if op == "<":
                return atual is not None and str(atual) < str(valor)
            raise AssertionError(f"operador nao suportado pelo fake: {op}")
        return _Recorte(self._dados, [i for i in self._ids if passa(i)], self._n)

    def limit(self, n):
        return _Recorte(self._dados, self._ids, n)

    def order_by(self, campo, direction="ASCENDING"):
        ordenados = sorted(
            self._ids,
            key=lambda i: str((self._dados.get(i) or {}).get(campo) or ""),
            reverse=(direction == "DESCENDING"))
        return _Recorte(self._dados, ordenados, self._n)

    def count(self):
        total = len(self._ids)

        class _Agregado:
            value = total

        class _Resultado:
            @staticmethod
            def get():
                return [[_Agregado()]]

        return _Resultado()

    def stream(self):
        ids = self._ids if self._n is None else self._ids[:self._n]
        return [_Snap(self._dados, i) for i in ids]


class _Db:
    def __init__(self):
        self.cols = {}

    def collection(self, nome):
        return self.cols.setdefault(nome, _Colecao())


class TestAGravacaoNaoConfiaNoModelo(unittest.TestCase):
    """A validacao mora na tool de escrita, e nao no prompt.

    O modelo pode alucinar um id, insistir depois do limite da rodada, ou apontar
    um objetivo servido por dado. As tres passariam se a checagem estivesse so na
    instrucao — e as tres gravariam sujeira que o usuario leria como sugestao.
    """

    def _rodada(self, restantes=2):
        return {
            "restantes": restantes,
            "objetivos": [{"id": "intel", "objetivoMacro": "Autoridade intelectual",
                           "pilar": "intelectual"}],
            "candidatos": [{"task_id": "sispnaes",
                            "tarefa": _tarefa(id="sispnaes", titulo="Ciclo Sispnaes 2026"),
                            "corpo": {"documentos": ["HANDOFF-SISPNAES.md"], "etapas_feitas": 4,
                                      "tem_texto_pronto": True, "caracteres_diario": 2000}}],
        }

    @staticmethod
    def _reserva(vagas):
        """Reserva falsa com N vagas — a atomicidade real e do Firestore."""
        estado = {"restam": vagas}

        def reservar(db, hoje, teto, ref, payload, ja_no_mes=0):
            # Espelha o contrato da reserva real: id ja usado e recusa.
            if estado["restam"] <= 0 or ref.get().exists:
                return False
            estado["restam"] -= 1
            ref.set(payload)
            return True

        return reservar

    def _propor(self, db, rodada, aceitas, vagas=9, **over):
        _, fmap = ds._ferramenta_propor(db, HOJE, rodada, aceitas,
                                        reservar=self._reserva(vagas))
        return fmap["propor_elevacao"](**{**TestAPropostaDaIA.BASE, **over})

    def test_proposta_boa_e_gravada_com_o_resumo_pronto(self):
        db, aceitas = _Db(), []
        r = self._propor(db, self._rodada(), aceitas)
        self.assertTrue(r["aceita"])
        gravada = db.cols[ds.COL_ELEVACOES].dados[r["sugestao_id"]]
        self.assertEqual(gravada["status"], ds.STATUS_PENDENTE)
        self.assertEqual(gravada["titulo_acao"], "Ciclo Sispnaes 2026")
        self.assertIn("HANDOFF-SISPNAES.md", gravada["resumo"])

    def test_vaga_negada_nao_vira_sugestao_gravada(self):
        """O teto e conferido na reserva, e nao por contador em memoria.

        As tool calls de uma rodada rodam em paralelo; um contador em memoria
        deixaria duas threads passarem pela mesma checagem antes de qualquer uma
        gravar. Aqui o que se verifica e o contrato desta camada: reserva negada
        nao grava e nao entra na lista de aceitas.
        """
        db, aceitas = _Db(), []
        _, fmap = ds._ferramenta_propor(db, HOJE, self._rodada(), aceitas,
                                        reservar=self._reserva(0))
        r = fmap["propor_elevacao"](**TestAPropostaDaIA.BASE)
        self.assertFalse(r["aceita"])
        self.assertIn("teto", r["motivo"])
        self.assertEqual(aceitas, [])
        self.assertEqual(db.cols.get(ds.COL_ELEVACOES, _Colecao()).dados, {})

    def test_a_reserva_e_quem_decide_e_nao_a_contagem_local(self):
        """Duas acoes distintas, uma vaga contada localmente: quem manda e a reserva."""
        rodada = self._rodada(restantes=1)
        rodada["candidatos"].append({
            "task_id": "outra", "tarefa": _tarefa(id="outra", titulo="Outra acao"),
            "corpo": {"documentos": [], "etapas_feitas": 3,
                      "tem_texto_pronto": False, "caracteres_diario": 0}})
        db, aceitas = _Db(), []
        _, fmap = ds._ferramenta_propor(db, HOJE, rodada, aceitas, reservar=self._reserva(2))
        self.assertTrue(fmap["propor_elevacao"](**TestAPropostaDaIA.BASE)["aceita"])
        self.assertTrue(fmap["propor_elevacao"](
            **{**TestAPropostaDaIA.BASE, "task_id": "outra"})["aceita"])
        self.assertEqual(len(aceitas), 2)

    def test_duas_propostas_para_a_mesma_acao_nao_viram_dois_cards(self):
        """Id deterministico por acao e mes: a segunda colide e e recusada.

        Sem isso sairiam dois cards para a mesma acao, gastando duas das tres
        vagas do mes, e marcar "nunca" num deixaria o outro pendente — o oposto
        da permanencia que o card promete.
        """
        db, aceitas = _Db(), []
        _, fmap = ds._ferramenta_propor(db, HOJE, self._rodada(), aceitas,
                                        reservar=self._reserva(5))
        self.assertTrue(fmap["propor_elevacao"](**TestAPropostaDaIA.BASE)["aceita"])
        segunda = fmap["propor_elevacao"](**TestAPropostaDaIA.BASE)
        self.assertFalse(segunda["aceita"])
        self.assertEqual(len(db.cols[ds.COL_ELEVACOES].dados), 1)
        self.assertEqual(len(aceitas), 1)

    def test_o_id_da_reserva_separa_acao_e_mes(self):
        self.assertNotEqual(ds.id_da_reserva("2026-08-29", "t1"),
                            ds.id_da_reserva("2026-09-01", "t1"))
        self.assertNotEqual(ds.id_da_reserva(HOJE, "t1"), ds.id_da_reserva(HOJE, "t2"))

    def test_objetivo_inventado_nao_grava(self):
        db = _Db()
        r = self._propor(db, self._rodada(), [], objetivo_id="saude")
        self.assertFalse(r["aceita"])
        self.assertEqual(db.cols.get(ds.COL_ELEVACOES, _Colecao()).dados, {})

    def test_acao_fora_da_rodada_nao_grava(self):
        self.assertFalse(self._propor(_Db(), self._rodada(), [], task_id="outra")["aceita"])

    def test_justificativa_generica_nao_grava(self):
        self.assertFalse(self._propor(_Db(), self._rodada(), [], justificativa="Ajuda.")["aceita"])


class TestOContadorNaoRecomecaDoZero(unittest.TestCase):
    """O contador transacional nasceu depois das sugestoes.

    Enquanto ele nao existir — primeiro deploy, ou documento perdido — ler zero
    seria licenca para recomecar a contagem do mes com sugestoes ja na base: com
    duas gravadas, mais tres caberiam sob um teto de tres.
    """

    def test_a_rodada_leva_a_contagem_do_historico_como_piso(self):
        db = _Db()
        col = db.collection(ds.COL_ELEVACOES)
        for i in (1, 2):
            col.dados[f"s{i}"] = {"task_id": f"t{i}", "criada_em": HOJE,
                                  "status": ds.STATUS_PENDENTE}
        db.collection("estrategia_pessoal").dados["intel"] = {
            "objetivoMacro": "Autoridade", "pilar": "intelectual", "status": "ativo"}
        db.collection("tarefas").dados["nova"] = {
            "titulo": "Nova", "status": "em andamento",
            "pool_dados": [_anexo("X.md")], "acompanhamento": [], "plano_acao": []}
        rodada = ds.preparar_rodada(db, HOJE, [])
        self.assertTrue(rodada["rodar"])
        self.assertEqual(rodada["ja_no_mes"], 2)
        self.assertEqual(rodada["restantes"], ds.TETO_POR_MES - 2)

    def test_o_piso_chega_na_reserva(self):
        recebido = {}

        def reservar(db, hoje, teto, ref, payload, ja_no_mes=0):
            recebido["ja_no_mes"] = ja_no_mes
            return True

        rodada = TestAGravacaoNaoConfiaNoModelo()._rodada()
        rodada["ja_no_mes"] = 2
        _, fmap = ds._ferramenta_propor(_Db(), HOJE, rodada, [], reservar=reservar)
        fmap["propor_elevacao"](**TestAPropostaDaIA.BASE)
        self.assertEqual(recebido["ja_no_mes"], 2)


class TestFalhaDeLeituraFechaAPorta(unittest.TestCase):
    """Historico ilegivel nao e historico vazio.

    Vazio e o estado em que o teto parece zerado e nenhuma acao parece decidida.
    Uma falha de Firestore viraria permissao para estourar o limite e para
    repropor o que o usuario marcou como "nunca". A trava falha fechada.
    """

    class _DbQuebrado:
        def collection(self, _nome):
            raise RuntimeError("indisponivel")

    def test_carregar_levanta_em_vez_de_devolver_vazio(self):
        with self.assertRaises(ds.HistoricoIndisponivel):
            ds._carregar_sugestoes(self._DbQuebrado(), HOJE)

    def test_rodada_e_abortada_e_nao_roda_sem_historico(self):
        r = ds.preparar_rodada(self._DbQuebrado(), HOJE, [])
        self.assertFalse(r["rodar"])
        self.assertEqual(r["motivo"], "historico_indisponivel")


class TestAMensagemDoModelo(unittest.TestCase):

    def test_leva_objetivos_e_material_das_candidatas(self):
        rodada = TestAGravacaoNaoConfiaNoModelo()._rodada()
        rodada["candidatos"][0]["tarefa"]["acompanhamento"] = _diario(500)
        msg = ds.mensagem_da_rodada(rodada)
        self.assertIn("Autoridade intelectual", msg)
        self.assertIn("HANDOFF-SISPNAES.md", msg)
        self.assertIn("no maximo 2", msg)


class TestADecisaoDoUsuario(unittest.TestCase):
    """Sem alca o detector e inerte: a sugestao aparece e nao ha como responder.

    As tres saidas do card sao o que impede o recurso de virar barulho — "nunca"
    acima de tudo, porque sem ela o sistema repete a mesma sugestao.
    """

    def _db_com_pendente(self):
        db = _Db()
        db.collection(ds.COL_ELEVACOES).dados["s1"] = {
            **TestAPropostaDaIA.BASE, "status": ds.STATUS_PENDENTE, "criada_em": HOJE,
            "titulo_acao": "Ciclo Sispnaes 2026", "nome_objetivo": "Autoridade intelectual",
            "resumo": "resumo",
        }
        return db

    def test_nunca_e_definitivo_e_tira_a_acao_das_proximas_varreduras(self):
        db = self._db_com_pendente()
        r = ds.decidir(db, "s1", "nunca", HOJE, aplicar=_aplicar)
        self.assertEqual(r["status"], ds.STATUS_NUNCA)
        gravada = db.cols[ds.COL_ELEVACOES].dados["s1"]
        decididas = ds.acoes_ja_decididas([gravada])
        self.assertEqual(decididas["sispnaes"], ds.STATUS_NUNCA)

    def test_adiar_devolve_a_acao_para_a_fila_depois(self):
        db = self._db_com_pendente()
        ds.decidir(db, "s1", "adiar", HOJE, aplicar=_aplicar)
        gravada = db.cols[ds.COL_ELEVACOES].dados["s1"]
        decididas = ds.acoes_ja_decididas([gravada])
        self.assertEqual(len(ds.candidatas(
            [_tarefa(id="sispnaes", pool_dados=[_anexo("X.md")])], decididas, HOJE)), 1)

    def test_aceitar_devolve_rascunho_e_o_vinculo_em_separado(self):
        """Dois passos: criar por criar_acao_no_sistema, vincular por editar_acao.

        O vinculo NAO vai no rascunho de criacao de proposito. Nao existe um
        caminho de criacao de acao no Hermes — existem quatro reimplementacoes, e
        um campo novo passado ali funciona numa porta e some nas outras, em
        silencio. Vincular depois e o unico jeito de ele valer sempre.
        """
        r = ds.decidir(self._db_com_pendente(), "s1", "aceitar", HOJE, aplicar=_aplicar)
        rascunho = r["rascunho_da_acao"]
        self.assertNotIn("estrategia_objetivo_id", rascunho)
        self.assertIn("HANDOFF-SISPNAES.md", rascunho["descricao"])
        self.assertTrue(rascunho["titulo"])
        self.assertEqual(r["vincular_depois"]["estrategia_objetivo_id"], "intel")
        self.assertEqual(r["vincular_depois"]["tool"], "editar_acao")

    def test_o_detalhe_avisa_que_sem_o_segundo_passo_a_acao_nasce_solta(self):
        r = ds.decidir(self._db_com_pendente(), "s1", "aceitar", HOJE, aplicar=_aplicar)
        self.assertIn("editar_acao", r["detalhe"])
        self.assertIn("solta", r["detalhe"])

    def test_decidir_duas_vezes_nao_sobrescreve(self):
        db = self._db_com_pendente()
        ds.decidir(db, "s1", "nunca", HOJE, aplicar=_aplicar)
        segunda = ds.decidir(db, "s1", "aceitar", HOJE, aplicar=_aplicar)
        self.assertFalse(segunda["ok"])
        self.assertEqual(db.cols[ds.COL_ELEVACOES].dados["s1"]["status"], ds.STATUS_NUNCA)

    def test_decisao_invalida_lista_as_validas(self):
        r = ds.decidir(self._db_com_pendente(), "s1", "talvez", HOJE, aplicar=_aplicar)
        self.assertFalse(r["ok"])
        self.assertIn("nunca", r["erro"])

    def test_sugestao_inexistente_nao_finge_sucesso(self):
        self.assertFalse(ds.decidir(self._db_com_pendente(), "nao-existe", "aceitar", HOJE, aplicar=_aplicar)["ok"])

    @staticmethod
    def _contador(db, data):
        return (ds._contador_do_mes(db, data).get().to_dict() or {}).get("count")

    @staticmethod
    def _com_contador(db, data, valor):
        ds._contador_do_mes(db, data).set({"count": valor})
        return db

    def test_nunca_devolve_a_vaga_do_mes(self):
        """"Nunca" e ajuste de escopo, nao interrupcao gasta.

        Sem devolver a vaga, tres recusas definitivas bloqueariam o resto do mes —
        e as duas contagens (o contador gravado e `elevacoes_do_mes`) passariam a
        discordar entre si.
        """
        db = self._com_contador(self._db_com_pendente(), HOJE, 3)
        ds.decidir(db, "s1", "nunca", HOJE, aplicar=_aplicar)
        self.assertEqual(self._contador(db, HOJE), 2)

    def test_a_vaga_volta_para_o_mes_da_sugestao_e_nao_para_o_de_hoje(self):
        """Recusar em setembro uma sugestao de agosto nao abre vaga em setembro."""
        db = self._db_com_pendente()
        db.cols[ds.COL_ELEVACOES].dados["s1"]["criada_em"] = "2026-07-15"
        self._com_contador(db, "2026-07-15", 3)
        self._com_contador(db, "2026-08-29", 1)
        ds.decidir(db, "s1", "nunca", "2026-08-29", aplicar=_aplicar)
        self.assertEqual(self._contador(db, "2026-07-15"), 2)
        self.assertEqual(self._contador(db, "2026-08-29"), 1)

    def test_a_vaga_devolvida_nao_deixa_o_contador_negativo(self):
        """Contador negativo seria licenca para estourar o teto no mes seguinte."""
        db = self._com_contador(self._db_com_pendente(), HOJE, 0)
        ds.decidir(db, "s1", "nunca", HOJE, aplicar=_aplicar)
        self.assertEqual(self._contador(db, HOJE), 0)

    def test_adiar_nao_devolve_vaga(self):
        """Adiada interrompeu; a vaga fica gasta ate o mes virar."""
        db = self._com_contador(self._db_com_pendente(), HOJE, 3)
        ds.decidir(db, "s1", "adiar", HOJE, aplicar=_aplicar)
        self.assertEqual(self._contador(db, HOJE), 3)

    def test_a_segunda_recusa_da_mesma_sugestao_nao_devolve_a_vaga_de_novo(self):
        """A checagem de pendente e a devolucao moram na mesma transacao.

        `run_tool_loop` executa as tool calls de uma rodada em paralelo. Separadas,
        duas recusas da mesma sugestao passariam as duas pela checagem antes de
        qualquer uma gravar, e o contador cairia duas vezes — subcontando o mes e
        abrindo vaga que nao existe.
        """
        db = self._com_contador(self._db_com_pendente(), HOJE, 3)
        primeira = ds.decidir(db, "s1", "nunca", HOJE, aplicar=_aplicar)
        segunda = ds.decidir(db, "s1", "nunca", HOJE, aplicar=_aplicar)
        self.assertTrue(primeira["ok"])
        self.assertFalse(segunda["ok"])
        self.assertEqual(self._contador(db, HOJE), 2)

    def test_gravacao_que_falha_nao_e_relatada_como_decidida(self):
        """Meio-caminho aqui prende a vaga: nao da para repetir a decisao."""
        def _explode(*_a):
            raise RuntimeError("indisponivel")

        r = ds.decidir(self._db_com_pendente(), "s1", "nunca", HOJE, aplicar=_explode)
        self.assertFalse(r["ok"])
        self.assertIn("indisponivel", r["erro"])

    def test_listar_acha_a_pendente_no_meio_de_um_historico_grande(self):
        """O filtro tem de estar na consulta, nao no `for` depois da leitura.

        Filtrando depois, o limite se aplica a colecao inteira: passado o corte,
        o recorte lido pode ser todo de sugestoes ja decididas, e esta tool
        responde "nao ha decisoes pendentes" enquanto o resumo matinal — que
        consulta por status — mostra que ha. As duas superficies discordando
        sobre a mesma fila e pior que nao ter a segunda.
        """
        db = _Db()
        col = db.collection(ds.COL_ELEVACOES)
        # As decididas entram ANTES da pendente: se o limite valesse sobre a
        # colecao inteira, a pendente ficaria fora do recorte lido. Com a
        # pendente inserida primeiro o teste passaria dos dois jeitos.
        for i in range(400):
            col.dados[f"velha{i}"] = {"status": ds.STATUS_NUNCA, "criada_em": "2025-01-01",
                                      "titulo_acao": f"antiga {i}"}
        col.dados["s1"] = self._db_com_pendente().cols[ds.COL_ELEVACOES].dados["s1"]
        r = ds.listar_pendentes(db)
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["sugestoes"][0]["sugestao_id"], "s1")

    def test_listar_traz_so_pendentes_com_o_id_para_decidir(self):
        db = self._db_com_pendente()
        db.collection(ds.COL_ELEVACOES).dados["s2"] = {
            "status": ds.STATUS_NUNCA, "titulo_acao": "Outra", "criada_em": HOJE}
        r = ds.listar_pendentes(db)
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["sugestoes"][0]["sugestao_id"], "s1")


class TestOTextoDoCard(unittest.TestCase):

    def test_cada_linha_responde_uma_pergunta_do_usuario(self):
        texto = ds.resumo_para_o_usuario(
            TestAPropostaDaIA.BASE, "Ciclo Sispnaes 2026", "Intelectual")
        for esperado in ("O que ja existe", "Ativo possivel", "Objetivo servido",
                         "Passo que falta", "Custo estimado"):
            self.assertIn(esperado, texto)
        self.assertIn("HANDOFF-SISPNAES.md", texto)
        self.assertIn("Ciclo Sispnaes 2026", texto)


if __name__ == "__main__":
    unittest.main()
