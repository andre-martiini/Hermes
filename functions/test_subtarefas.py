"""O contrato da subtarefa.

Dois grupos de teste importam mais que os outros:

1. **`mesclar_plano` preserva o que não conhece.** O merge existia duplicado em
   `main.py` e `tools/telegram_extended.py`, e as duas cópias remontavam a etapa
   como `{id, text, completed}` literal. Qualquer campo novo seria apagado no
   primeiro ajuste de texto, sem erro nenhum — a mesma classe de falha do
   `anexar_arquivo`: grava, responde ok, e a informação não está lá.

2. **A degradação não pune espera.** É a razão de existir da mudança inteira.

Os casos de contorno aqui não são hipotéticos: saíram da varredura das 43 ações
ativas em 2026-08-26 (ação com 12/12 etapas feitas e contador 26; 30 ações com
contador maior que zero e nenhum histórico por etapa; 9 ações sem plano nenhum).

Uso: functions/venv/Scripts/python.exe -m unittest test_subtarefas
"""

import unittest

import subtarefas as st

HOJE = "2026-08-27"


def _etapa(texto, **over):
    base = {"id": texto[:6], "text": texto, "completed": False}
    base.update(over)
    return base


# --------------------------------------------------------------------------- #

class TestCompatibilidadeComOPlanoAntigo(unittest.TestCase):
    """As 226 etapas existentes têm exatamente {id, text, completed}."""

    def test_etapa_sem_estado_deduz_de_completed(self):
        self.assertEqual(st.estado_de({"text": "a", "completed": False}), st.PENDENTE)
        self.assertEqual(st.estado_de({"text": "a", "completed": True}), st.FEITO)

    def test_estado_explicito_manda(self):
        self.assertEqual(
            st.estado_de({"text": "a", "completed": False, "estado": "em_andamento"}),
            st.EM_ANDAMENTO)

    def test_estado_invalido_cai_no_deduzido(self):
        """Valor estranho não pode virar um quarto estado silencioso."""
        self.assertEqual(st.estado_de({"text": "a", "completed": True, "estado": "xpto"}),
                         st.FEITO)

    def test_contagem_bate_com_o_agregado_antigo(self):
        plano = [_etapa("a", completed=True), _etapa("b"), _etapa("c", completed=True)]
        self.assertEqual(st.contar(plano), (2, 3))

    def test_etapa_sem_texto_nao_conta(self):
        self.assertEqual(st.contar([_etapa("a"), {"id": "x", "text": "  "}]), (0, 1))

    def test_plano_de_strings_continua_valendo(self):
        """criar_acao_no_sistema(plano_acao=["passo 1"]) é o uso histórico."""
        plano = st.converter_plano(["passo 1", "passo 2"])
        self.assertEqual([p["text"] for p in plano], ["passo 1", "passo 2"])
        self.assertTrue(all(p["estado"] == st.PENDENTE for p in plano))
        self.assertTrue(all(p["id"] for p in plano))

    def test_completed_continua_sendo_gravado(self):
        """Há telas que só leem `completed`; ele espelha o estado, sempre."""
        p = st.normalizar({"text": "a", "estado": "feito"})
        self.assertTrue(p["completed"])
        p2 = st.normalizar({"text": "a", "estado": "aguardando_terceiro"})
        self.assertFalse(p2["completed"])


class TestMesclarPreservaOQueNaoConhece(unittest.TestCase):
    """O passo zero: sem isto, tudo o que vier depois vaza."""

    def test_ajustar_texto_nao_apaga_os_campos_novos(self):
        atual = [_etapa("Publicar a versão", data_prevista="2026-08-28",
                        estado="aguardando_terceiro", aguardando_de="colegas do MAGO",
                        degradation_count=2)]
        # O copiloto reescreve o texto do passo, sem citar mais nada.
        final = st.mesclar_plano(atual, [{"id": "Public", "text": "Publicar a versão 2.1"}])
        self.assertEqual(final[0]["text"], "Publicar a versão 2.1")
        self.assertEqual(final[0]["data_prevista"], "2026-08-28")
        self.assertEqual(final[0]["estado"], "aguardando_terceiro")
        self.assertEqual(final[0]["aguardando_de"], "colegas do MAGO")
        self.assertEqual(final[0]["degradation_count"], 2)

    def test_campo_desconhecido_tambem_sobrevive(self):
        """A próxima feature não deve depender de alguém lembrar deste merge."""
        atual = [_etapa("a", campo_de_amanha={"algo": 1})]
        final = st.mesclar_plano(atual, [{"id": "a", "text": "a"}])
        self.assertEqual(final[0]["campo_de_amanha"], {"algo": 1})

    def test_match_por_texto_parecido_tambem_preserva(self):
        """Sem id, o merge cai no fuzzy — e era outro caminho que apagava."""
        atual = [_etapa("Levantar o mapa de preços", data_prevista="2026-09-01",
                        degradation_count=9)]
        final = st.mesclar_plano(atual, [{"text": "Levantar o mapa de precos"}])
        self.assertEqual(final[0]["data_prevista"], "2026-09-01")
        self.assertEqual(final[0]["degradation_count"], 9)
        self.assertEqual(final[0]["id"], atual[0]["id"], "o id tem que ser o mesmo")

    def test_conclusao_e_preservada_como_antes(self):
        atual = [_etapa("a", completed=True, estado="feito")]
        final = st.mesclar_plano(atual, [{"id": "a", "text": "a"}])
        self.assertTrue(final[0]["completed"])

    def test_campo_enviado_explicitamente_sobrepoe_o_herdado(self):
        """Quem edita está dizendo o que quer."""
        atual = [_etapa("a", estado="pendente")]
        final = st.mesclar_plano(atual, [{"id": "a", "text": "a", "estado": "em_andamento"}])
        self.assertEqual(final[0]["estado"], "em_andamento")

    def test_etapa_nova_entra_sem_herdar_de_ninguem(self):
        atual = [_etapa("Congelar escopo", degradation_count=5)]
        final = st.mesclar_plano(atual, [
            {"id": "Congel", "text": "Congelar escopo"},
            {"text": "Coisa completamente diferente"},
        ])
        self.assertEqual(len(final), 2)
        self.assertEqual(final[1].get("degradation_count"), None)
        self.assertNotEqual(final[1]["id"], final[0]["id"])

    def test_etapa_removida_do_plano_novo_sai(self):
        atual = [_etapa("a"), _etapa("b")]
        final = st.mesclar_plano(atual, [{"id": "a", "text": "a"}])
        self.assertEqual([f["text"] for f in final], ["a"])


class TestSubtarefaCorrente(unittest.TestCase):

    def test_escolhe_pela_menor_data_prevista(self):
        plano = [_etapa("depois", data_prevista="2026-09-01"),
                 _etapa("antes", data_prevista="2026-08-27")]
        self.assertEqual(st.subtarefa_corrente(plano, HOJE)["text"], "antes")

    def test_ignora_as_concluidas(self):
        plano = [_etapa("feita", data_prevista="2026-08-01", completed=True),
                 _etapa("aberta", data_prevista="2026-09-01")]
        self.assertEqual(st.subtarefa_corrente(plano, HOJE)["text"], "aberta")

    def test_sem_datas_resolve_pela_ordem_do_plano(self):
        """Plano sem datas — todos os 34 planos existentes — se comporta como antes:
        a corrente é a primeira etapa aberta, que é o que `proximo_passo` já fazia."""
        plano = [_etapa("um", completed=True), _etapa("dois"), _etapa("tres")]
        self.assertEqual(st.subtarefa_corrente(plano, HOJE)["text"], "dois")

    def test_todas_concluidas_devolve_none(self):
        """Existe de verdade: ação ativa com 12/12 feitas e contador 26."""
        self.assertIsNone(st.subtarefa_corrente([_etapa("a", completed=True)], HOJE))

    def test_plano_vazio_devolve_none(self):
        self.assertIsNone(st.subtarefa_corrente([], HOJE))

    def test_etapa_sem_data_herda_a_da_acao(self):
        self.assertEqual(st.data_prevista_de({"text": "a"}, "2026-08-27"), "2026-08-27")

    def test_data_propria_vence_a_heranca(self):
        self.assertEqual(
            st.data_prevista_de({"text": "a", "data_prevista": "2026-09-05"}, "2026-08-27"),
            "2026-09-05")


class TestFaixaDerivada(unittest.TestCase):
    """Até 26/08/2026 nada escrevia `execution_lane` além do reset da virada."""

    def test_uma_em_andamento_poe_a_acao_em_avanco(self):
        plano = [_etapa("a", estado="em_andamento"),
                 _etapa("b", estado="aguardando_terceiro")]
        self.assertEqual(st.derivar_lane(plano), "avanco")

    def test_todas_as_abertas_esperando_poem_a_acao_em_espera(self):
        plano = [_etapa("feita", completed=True),
                 _etapa("b", estado="aguardando_terceiro"),
                 _etapa("c", estado="aguardando_terceiro")]
        self.assertEqual(st.derivar_lane(plano), "aguardando_terceiro")

    def test_todas_pendentes_cai_em_avanco(self):
        """O caso esmagadoramente comum hoje — nenhuma interface marca estado."""
        self.assertEqual(st.derivar_lane([_etapa("a"), _etapa("b")]), "avanco")

    def test_sem_plano_mantem_o_que_estava(self):
        """9 das 43 ações ativas não têm plano nenhum."""
        self.assertEqual(st.derivar_lane([], "aguardando_terceiro"), "aguardando_terceiro")
        self.assertEqual(st.derivar_lane([], None), "avanco")

    def test_continuo_gravado_nao_e_sobrescrito(self):
        """Nenhum estado de subtarefa expressa `continuo` — deduzir seria inventar."""
        self.assertEqual(st.derivar_lane([_etapa("a")], "continuo"), "continuo")

    def test_lista_de_espera_aparece_mesmo_com_a_acao_em_avanco(self):
        """É a pendência que some hoje: a ação avança e a espera fica invisível."""
        plano = [_etapa("a", estado="em_andamento"),
                 _etapa("b", estado="aguardando_terceiro", aguardando_de="colegas do MAGO")]
        self.assertEqual(st.derivar_lane(plano), "avanco")
        esperando = st.aguardando_terceiros(plano)
        self.assertEqual([e["text"] for e in esperando], ["b"])
        self.assertEqual(esperando[0]["aguardando_de"], "colegas do MAGO")


class TestDegradacao(unittest.TestCase):

    def test_etapa_pendente_acumula_a_cada_dia(self):
        """Critério 4: adiada 5 dias seguidos chega a 5."""
        plano = [_etapa("levantar mapa de preços")]
        for _ in range(5):
            plano, etapa, macro = st.aplicar_degradacao(plano, HOJE)
        self.assertEqual(plano[0]["degradation_count"], 5)
        self.assertTrue(macro)

    def test_etapa_aguardando_terceiro_nao_degrada(self):
        """Critério 3: 10 dias esperando e o contador segue em 0.

        Esperar terceiro não é procrastinação. Antes disto, a espera escapava só
        no primeiro dia: junto com o [COBRAR], a virada devolvia a faixa para
        `avanco`, e do segundo dia em diante degradava como qualquer outra.
        """
        plano = [_etapa("publicar", estado="aguardando_terceiro",
                        aguardando_de="colegas do MAGO")]
        for _ in range(10):
            plano, etapa, macro = st.aplicar_degradacao(plano, HOJE)
            self.assertIsNone(etapa)
            self.assertFalse(macro, "a macroação também não degrada: é essa etapa que segura")
        self.assertEqual(plano[0].get("degradation_count", 0), 0)

    def test_so_a_etapa_corrente_degrada(self):
        plano = [_etapa("primeira"), _etapa("segunda")]
        plano, _, _ = st.aplicar_degradacao(plano, HOJE)
        self.assertEqual(plano[0]["degradation_count"], 1)
        self.assertEqual(plano[1].get("degradation_count", 0), 0)

    def test_sem_etapa_aberta_a_macroacao_degrada_assim_mesmo(self):
        """Ação com 12/12 etapas feitas e contador 26 — o adiamento aconteceu,
        só não há a quem atribuir."""
        plano = [_etapa("a", completed=True)]
        _, etapa, macro = st.aplicar_degradacao(plano, HOJE)
        self.assertIsNone(etapa)
        self.assertTrue(macro)

    def test_acao_sem_plano_degrada_como_antes(self):
        _, etapa, macro = st.aplicar_degradacao([], HOJE)
        self.assertIsNone(etapa)
        self.assertTrue(macro)

    def test_espera_no_meio_do_plano_nao_bloqueia_a_etapa_de_hoje(self):
        """Espera numa etapa futura não impede a corrente de degradar."""
        plano = [_etapa("hoje", data_prevista="2026-08-27"),
                 _etapa("depois", data_prevista="2026-09-10", estado="aguardando_terceiro")]
        plano, etapa, macro = st.aplicar_degradacao(plano, HOJE)
        self.assertEqual(etapa["text"], "hoje")
        self.assertTrue(macro)


class TestContadorDaMacroacaoEspelha(unittest.TestCase):
    """Espelha, não move — 30 das 43 ações ativas têm contador > 0 e nenhum
    histórico por etapa. Derivar puro zeraria as 30 de uma vez."""

    def test_contador_gravado_nao_regride(self):
        plano = [_etapa("a")]
        self.assertEqual(st.degradacao_da_acao(plano, 26), 26)

    def test_maior_das_etapas_prevalece_quando_passa_o_gravado(self):
        plano = [_etapa("a", degradation_count=4), _etapa("b", degradation_count=7)]
        self.assertEqual(st.degradacao_da_acao(plano, 3), 7)

    def test_acao_sem_plano_usa_so_o_gravado(self):
        self.assertEqual(st.degradacao_da_acao([], 11), 11)

    def test_zero_continua_zero(self):
        self.assertEqual(st.degradacao_da_acao([_etapa("a")], 0), 0)


class TestInconsistencias(unittest.TestCase):
    """Sinaliza, não bloqueia: o dono pode estar registrando um furo que já sabe."""

    def test_etapa_depois_do_prazo_final_e_sinalizada(self):
        plano = [_etapa("a", data_prevista="2026-10-01")]
        avisos = st.inconsistencias(plano, "2026-09-25")
        self.assertEqual(len(avisos), 1)
        self.assertIn("2026-10-01", avisos[0])
        self.assertIn("2026-09-25", avisos[0])

    def test_dentro_do_prazo_nao_avisa(self):
        self.assertEqual(st.inconsistencias([_etapa("a", data_prevista="2026-09-01")],
                                            "2026-09-25"), [])

    def test_acao_sem_prazo_final_nao_tem_o_que_furar(self):
        self.assertEqual(st.inconsistencias([_etapa("a", data_prevista="2030-01-01")], None), [])

    def test_etapa_sem_data_propria_nao_avisa(self):
        self.assertEqual(st.inconsistencias([_etapa("a")], "2026-09-25"), [])


class TestCasoDeTesteDaEspecificacao(unittest.TestCase):
    """O plano real de 'Revisar Questões do Mago' (a8b60ba1-4053-4e8d-b), §6."""

    def _plano(self):
        return st.converter_plano([
            {"text": "Congelar o escopo das melhorias", "data_prevista": "2026-08-27"},
            {"text": "Corrigir apenas os erros do que foi alterado", "data_prevista": "2026-08-27"},
            {"text": "Anotar em lista as melhorias que ficaram de fora", "data_prevista": "2026-08-27"},
            {"text": "Publicar a versão e encaminhar aos colegas", "data_prevista": "2026-08-28"},
            {"text": "Revisar e preencher as questões atribuídas a mim", "data_prevista": "2026-08-31"},
            {"text": "Encaminhar minhas questões aos colegas", "data_prevista": "2026-09-01"},
            {"text": "Após o retorno: retomar a fila de melhorias"},
        ])

    def test_criterio_1_mostra_a_corrente_e_nao_as_sete(self):
        corrente = st.subtarefa_corrente(self._plano(), "2026-08-27")
        self.assertEqual(corrente["text"], "Congelar o escopo das melhorias")

    def test_criterio_2_avanco_e_espera_ao_mesmo_tempo(self):
        """Em 28/08 a etapa 4 é publicada e passa a aguardar; a 5 segue em andamento."""
        plano = self._plano()
        plano[3] = {**plano[3], "estado": "aguardando_terceiro",
                    "aguardando_de": "colegas do MAGO"}
        plano[4] = {**plano[4], "estado": "em_andamento"}
        plano[:3] = [{**p, "estado": "feito", "completed": True} for p in plano[:3]]

        self.assertEqual(st.derivar_lane(plano), "avanco")
        esperando = st.aguardando_terceiros(plano)
        self.assertEqual(len(esperando), 1)
        self.assertEqual(esperando[0]["aguardando_de"], "colegas do MAGO")

    def test_criterio_3_o_contador_da_etapa_4_fica_parado(self):
        plano = self._plano()
        plano[3] = {**plano[3], "estado": "aguardando_terceiro"}
        plano[:3] = [{**p, "estado": "feito", "completed": True} for p in plano[:3]]
        for _ in range(7):
            plano, _, _ = st.aplicar_degradacao(plano, "2026-08-28")
        self.assertEqual(plano[3].get("degradation_count", 0), 0)

    def test_etapa_sem_data_nao_fura_a_fila(self):
        """A etapa 7 ('após o retorno') não tem data justamente por ser a última.

        Com herança pura ela recebia a data_limite da macroação — 27/08, a mais
        cedo do plano — e virava a corrente na frente de 'publicar a versão',
        marcada para 28/08.
        """
        plano = self._plano()
        plano[:3] = [{**p, "estado": "feito", "completed": True} for p in plano[:3]]
        self.assertEqual(st.subtarefa_corrente(plano, "2026-08-27")["text"],
                         "Publicar a versão e encaminhar aos colegas")

    def test_etapa_sem_data_vira_corrente_quando_sobra_so_ela(self):
        plano = self._plano()
        plano[:6] = [{**p, "estado": "feito", "completed": True} for p in plano[:6]]
        self.assertEqual(st.subtarefa_corrente(plano, "2026-08-27")["text"],
                         "Após o retorno: retomar a fila de melhorias")

    def test_etapa_sem_data_em_plano_misto_nao_exibe_data_emprestada(self):
        plano = self._plano()
        self.assertEqual(st.data_prevista_de(plano[6], "2026-08-27", plano), "")

    def test_plano_sem_data_nenhuma_continua_herdando(self):
        """Os 34 planos existentes caem aqui e não podem mudar de comportamento."""
        plano = st.converter_plano(["um", "dois"])
        self.assertFalse(st.plano_tem_datas(plano))
        self.assertEqual(st.data_prevista_de(plano[1], "2026-08-27", plano), "2026-08-27")


class TestGuardaContraEsvaziamento(unittest.TestCase):
    """Apagar um plano inteiro não pode ser efeito colateral de parâmetro errado.

    Em 28/08/2026 uma chamada usou `plano_acao=` onde a tool espera `novo_plano=`.
    A lista nova chegou vazia, o merge fez o que foi mandado, seis etapas sumiram
    — e o retorno foi "OK". Perda de dado silenciosa é o pior desfecho possível
    de uma escrita.
    """

    def test_esvaziar_plano_existente_e_detectado(self):
        atual = [_etapa("a"), _etapa("b")]
        self.assertTrue(st.esvaziaria_o_plano(atual, []))

    def test_plano_que_ja_era_vazio_nao_dispara(self):
        """Sem etapas antes, não há o que perder."""
        self.assertFalse(st.esvaziaria_o_plano([], []))

    def test_substituir_por_outras_etapas_nao_dispara(self):
        atual = [_etapa("a")]
        self.assertFalse(st.esvaziaria_o_plano(atual, [_etapa("nova")]))

    def test_reduzir_sem_zerar_nao_dispara(self):
        atual = [_etapa("a"), _etapa("b"), _etapa("c")]
        self.assertFalse(st.esvaziaria_o_plano(atual, [_etapa("a")]))

    def test_etapa_so_com_espaco_conta_como_vazio(self):
        """Uma lista de etapas sem texto apaga o plano tanto quanto uma lista vazia."""
        atual = [_etapa("a")]
        self.assertTrue(st.esvaziaria_o_plano(atual, [{"id": "x", "text": "   "}]))


class TestObjetoNaCriacaoDoPlano(unittest.TestCase):
    """Etapa enviada como objeto não pode virar o repr do dicionário.

    `str({"texto": ...})` gravava "{'texto': ..., 'data_prevista': ...}" como se
    fosse o texto da etapa. A conversão existia em três lugares e um deles — o do
    MCP — ficou para trás quando os outros dois foram corrigidos.
    """

    def test_objeto_com_chave_texto_e_desempacotado(self):
        plano = st.converter_plano([{"texto": "Obter as planilhas",
                                     "data_prevista": "2026-08-28",
                                     "estado": "pendente"}])
        self.assertEqual(plano[0]["text"], "Obter as planilhas")
        self.assertEqual(plano[0]["data_prevista"], "2026-08-28")
        self.assertNotIn("{", plano[0]["text"])

    def test_objeto_com_chave_text_tambem(self):
        plano = st.converter_plano([{"text": "Montar a comparação"}])
        self.assertEqual(plano[0]["text"], "Montar a comparação")

    def test_string_e_objeto_na_mesma_lista(self):
        plano = st.converter_plano(["passo solto", {"texto": "passo objeto"}])
        self.assertEqual([p["text"] for p in plano], ["passo solto", "passo objeto"])


class TestPlanoQueChegaComoString(unittest.TestCase):
    """Iterar uma string percorre CARACTERES — e foi o que aconteceu.

    Em 28/08/2026 o plano chegou como '["Baixar as propostas", ...]' e a ação
    terminou com ~800 etapas de um caractere: "[", '"', "B", "a"... A escrita
    respondeu OK. Antes disso o mesmo parâmetro era ignorado e o plano ficava
    vazio; ou seja, as duas formas de errar já aconteceram na mesma tool.
    """

    def test_json_de_lista_e_convertido(self):
        plano = st.converter_plano('["Baixar as propostas", "Extrair de cada planilha"]')
        self.assertEqual([p["text"] for p in plano],
                         ["Baixar as propostas", "Extrair de cada planilha"])

    def test_json_de_objetos_tambem(self):
        plano = st.converter_plano('[{"texto": "Baixar", "estado": "pendente"}]')
        self.assertEqual(plano[0]["text"], "Baixar")
        self.assertEqual(plano[0]["estado"], "pendente")

    def test_string_que_nao_e_json_e_recusada(self):
        """Adivinhar aqui produziria uma etapa gigante ou 800 minúsculas."""
        with self.assertRaises(st.PlanoInvalido) as erro:
            st.converter_plano("Baixar as propostas e extrair")
        self.assertIn("LISTA", str(erro.exception))

    def test_numero_e_recusado(self):
        with self.assertRaises(st.PlanoInvalido):
            st.converter_plano(42)

    def test_objeto_solto_vira_lista_de_um(self):
        plano = st.converter_plano({"texto": "etapa única"})
        self.assertEqual([p["text"] for p in plano], ["etapa única"])

    def test_sete_etapas_gravam_sete_etapas_integras(self):
        """O teste que o relato pediu."""
        entrada = [f"Etapa número {i} com texto suficientemente longo" for i in range(1, 8)]
        plano = st.converter_plano(entrada)
        self.assertEqual(len(plano), 7)
        self.assertEqual([p["text"] for p in plano], entrada)


class TestPlanoDegenerado(unittest.TestCase):
    """Última barreira: plano de etapas de um caractere é sempre lixo."""

    def test_etapas_de_um_caractere_sao_detectadas(self):
        plano = [_etapa(c) for c in '["Baixar']
        self.assertIsNotNone(st.parece_degenerado(plano))

    def test_plano_normal_passa(self):
        plano = st.converter_plano(["Primeira etapa do plano", "Segunda etapa do plano"])
        self.assertIsNone(st.parece_degenerado(plano))

    def test_uma_etapa_curta_entre_varias_nao_dispara(self):
        """Abreviação legítima não pode bloquear a escrita."""
        plano = st.converter_plano(["OK", "Etapa com texto de verdade",
                                    "Outra etapa com texto", "Mais uma etapa longa"])
        self.assertIsNone(st.parece_degenerado(plano))

    def test_plano_vazio_nao_e_degenerado(self):
        """Vazio é problema de outra guarda, não desta."""
        self.assertIsNone(st.parece_degenerado([]))


class TestCriacaoComObjetos(unittest.TestCase):
    """O teste que o relato pediu: criar com 7 etapas grava 7 etapas íntegras.

    Antes da correção, `str()` no objeto gravava o repr inteiro como se fosse o
    texto — `"{'text': '...', 'estado': 'pendente'}"` — e `estado` e
    `aguardando_de` nunca chegavam aos campos próprios: toda etapa virava
    pendente comum.
    """

    def _sete(self, chave):
        return [{chave: f"Etapa {i} com texto longo o suficiente para ser real",
                 "estado": "pendente"} for i in range(1, 8)]

    def test_sete_objetos_com_chave_text(self):
        plano = st.converter_plano(self._sete("text"))
        self.assertEqual(len(plano), 7)
        self.assertTrue(all(p["text"].startswith("Etapa ") for p in plano))
        self.assertTrue(all("{" not in p["text"] for p in plano), "gravou o repr")

    def test_sete_objetos_com_chave_texto(self):
        """As duas grafias aparecem nas chamadas; nenhuma pode ser stringificada."""
        plano = st.converter_plano(self._sete("texto"))
        self.assertEqual(len(plano), 7)
        self.assertTrue(all("{" not in p["text"] for p in plano))

    def test_campos_auxiliares_vao_para_os_campos_proprios(self):
        plano = st.converter_plano([{
            "text": "Publicar e pedir validação",
            "estado": "aguardando_terceiro",
            "aguardando_de": "desenvolvedor",
            "data_prevista": "2026-08-31",
        }])
        self.assertEqual(plano[0]["estado"], "aguardando_terceiro")
        self.assertEqual(plano[0]["aguardando_de"], "desenvolvedor")
        self.assertEqual(plano[0]["data_prevista"], "2026-08-31")
        self.assertFalse(plano[0]["completed"])

    def test_estado_invalido_no_objeto_nao_vira_estado(self):
        plano = st.converter_plano([{"text": "a", "estado": "quase_pronto"}])
        self.assertEqual(plano[0]["estado"], "pendente")


if __name__ == "__main__":
    unittest.main()
