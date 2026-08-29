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


class _Ref:
    def __init__(self, col, doc_id):
        self._col, self.id = col, doc_id

    def set(self, dados):
        self._col[self.id] = dict(dados)


class _Colecao:
    def __init__(self):
        self.dados, self._seq = {}, 0

    def document(self, doc_id=None):
        if doc_id is None:
            self._seq += 1
            doc_id = f"s{self._seq}"
        return _Ref(self.dados, doc_id)


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

    def _propor(self, db, rodada, aceitas, **over):
        _, fmap = ds._ferramenta_propor(db, HOJE, rodada, aceitas)
        return fmap["propor_elevacao"](**{**TestAPropostaDaIA.BASE, **over})

    def test_proposta_boa_e_gravada_com_o_resumo_pronto(self):
        db, aceitas = _Db(), []
        r = self._propor(db, self._rodada(), aceitas)
        self.assertTrue(r["aceita"])
        gravada = db.cols[ds.COL_ELEVACOES].dados[r["sugestao_id"]]
        self.assertEqual(gravada["status"], ds.STATUS_PENDENTE)
        self.assertEqual(gravada["titulo_acao"], "Ciclo Sispnaes 2026")
        self.assertIn("HANDOFF-SISPNAES.md", gravada["resumo"])

    def test_teto_da_rodada_e_conferido_na_gravacao(self):
        db, aceitas = _Db(), []
        self.assertTrue(self._propor(db, self._rodada(restantes=1), aceitas)["aceita"])
        segunda = self._propor(db, self._rodada(restantes=1), aceitas)
        self.assertFalse(segunda["aceita"])
        self.assertEqual(len(db.cols[ds.COL_ELEVACOES].dados), 1)

    def test_objetivo_inventado_nao_grava(self):
        db = _Db()
        r = self._propor(db, self._rodada(), [], objetivo_id="saude")
        self.assertFalse(r["aceita"])
        self.assertEqual(db.cols.get(ds.COL_ELEVACOES, _Colecao()).dados, {})

    def test_acao_fora_da_rodada_nao_grava(self):
        self.assertFalse(self._propor(_Db(), self._rodada(), [], task_id="outra")["aceita"])

    def test_justificativa_generica_nao_grava(self):
        self.assertFalse(self._propor(_Db(), self._rodada(), [], justificativa="Ajuda.")["aceita"])


class TestAMensagemDoModelo(unittest.TestCase):

    def test_leva_objetivos_e_material_das_candidatas(self):
        rodada = TestAGravacaoNaoConfiaNoModelo()._rodada()
        rodada["candidatos"][0]["tarefa"]["acompanhamento"] = _diario(500)
        msg = ds.mensagem_da_rodada(rodada)
        self.assertIn("Autoridade intelectual", msg)
        self.assertIn("HANDOFF-SISPNAES.md", msg)
        self.assertIn("no maximo 2", msg)


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
