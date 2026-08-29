"""Testa a Camada 1 do Resumo Matinal: a regra de escolha dos focos do dia
(`_escolher_foco`), o cálculo de janelas livres na agenda e a varredura de
ações (`_coletar_acoes`) contra um Firestore falso.

A regra de foco é o ponto onde um erro é caro e silencioso: ela decide o que o
usuário vai ver como as 3 coisas do dia. Como a escolha é código e não modelo
(mesma premissa de health_weekly_report.py), ela tem que ser testável — e a
ordem de precedência entre as regras precisa se sustentar quando mais de uma
dispara na mesma ação.

Uso: functions/venv/Scripts/python.exe functions/test_morning_summary.py
"""
import sys
import unittest

sys.path.insert(0, '.')

from morning_summary import (
    _persistir,
    _rotina_verificavel,
    _calcular_janelas_livres,
    _coletar_acoes,
    _escolher_foco,
    _js_weekday,
    _coletar_estrategia,
    _ultima_medida,
    _shift,
)

HOJE = "2026-08-20"  # quinta-feira


# --------------------------------------------------------------------------- #
# Firestore falso                                                              #
# --------------------------------------------------------------------------- #

class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    """Aplica os filtros em memória — só os operadores que o módulo usa."""

    def __init__(self, docs):
        self._docs = docs

    def where(self, field=None, op=None, value=None, filter=None):
        # O módulo usa a API nova (`filter=FieldFilter(...)`); a forma posicional
        # fica aceita para o fake não quebrar se algum callsite antigo aparecer.
        if filter is not None:
            field, op, value = filter.field_path, filter.op_string, filter.value

        def keep(doc):
            atual = doc.to_dict().get(field)
            if op == "==":
                return atual == value
            if op == "in":
                return atual in value
            if atual is None:
                return False
            if op == ">=":
                return atual >= value
            if op == "<=":
                return atual <= value
            if op == "<":
                return atual < value
            raise AssertionError(f"operador não suportado no fake: {op}")

        return _FakeQuery([d for d in self._docs if keep(d)])

    def limit(self, _n):
        return self

    def stream(self):
        return list(self._docs)


class _FakeDb:
    def __init__(self, colecoes):
        self._colecoes = colecoes

    def collection(self, nome):
        return _FakeQuery([_FakeDoc(i, d) for i, d in (self._colecoes.get(nome) or {}).items()])


def _tarefa(**over):
    base = {
        "titulo": "Ação",
        "status": "em andamento",
        "data_limite": HOJE,
        "data_inicio": HOJE,
        "execution_lane": "avanco",
        "plano_acao": [],
    }
    base.update(over)
    return base


def _acoes(tarefas: dict) -> dict:
    return _coletar_acoes(_FakeDb({"tarefas": tarefas}), HOJE)


_SEM_ESTRATEGIA = {"metas": [], "paradas": [], "servidas_hoje": 0}


# --------------------------------------------------------------------------- #

class TestRegraDeFoco(unittest.TestCase):

    def test_precedencia_prazo_duro_vence_degradacao(self):
        """Prazo final é o único prazo que o reset da meia-noite não move — tem
        que vir antes de qualquer outra regra."""
        acoes = _acoes({
            "degradada": _tarefa(titulo="Degradada", degradation_count=7),
            "com_prazo": _tarefa(titulo="Com prazo", prazo_final=HOJE),
        })
        foco = _escolher_foco(acoes, _SEM_ESTRATEGIA, HOJE)
        self.assertEqual(foco[0]["titulo"], "Com prazo")
        self.assertEqual(foco[0]["regra"], "prazo_final_iminente")

    def test_degradacao_critica_so_a_partir_do_terceiro_adiamento(self):
        acoes = _acoes({
            "duas": _tarefa(titulo="Duas vezes", degradation_count=2),
            "tres": _tarefa(titulo="Três vezes", degradation_count=3),
        })
        foco = _escolher_foco(acoes, _SEM_ESTRATEGIA, HOJE)
        criticas = [f for f in foco if f["regra"] == "degradacao_critica"]
        self.assertEqual([f["titulo"] for f in criticas], ["Três vezes"])

    def test_prazo_futuro_distante_nao_dispara(self):
        acoes = _acoes({"t": _tarefa(titulo="Longe", prazo_final="2026-09-30")})
        foco = _escolher_foco(acoes, _SEM_ESTRATEGIA, HOJE)
        self.assertEqual(foco[0]["regra"], "fila_avanco")

    def test_prazo_vencido_dispara_e_diz_que_venceu(self):
        acoes = _acoes({"t": _tarefa(titulo="Vencida", prazo_final="2026-08-18")})
        foco = _escolher_foco(acoes, _SEM_ESTRATEGIA, HOJE)
        self.assertEqual(foco[0]["regra"], "prazo_final_iminente")
        self.assertIn("venceu", foco[0]["motivo"])

    def test_cobrar_dispara_por_prefixo_do_titulo(self):
        """`daily_reset_job` renomeia para [COBRAR] e devolve a lane para 'avanco' —
        o prefixo é o único vestígio do SLA estourado."""
        acoes = _acoes({
            "a": _tarefa(titulo="Normal"),
            "b": _tarefa(titulo="[COBRAR] Resposta do fornecedor"),
        })
        foco = _escolher_foco(acoes, _SEM_ESTRATEGIA, HOJE)
        self.assertEqual(foco[0]["regra"], "sla_estourado")

    def test_meta_parada_puxa_a_acao_vinculada(self):
        acoes = _acoes({
            "solta": _tarefa(titulo="Sem meta"),
            "ligada": _tarefa(titulo="Ligada à meta", estrategia_objetivo_id="m1"),
        })
        estrategia = {
            "metas": [],
            "paradas": [{"id": "m1", "objetivo": "Publicar o artigo", "dias_parada": 21}],
            "servidas_hoje": 0,
        }
        foco = _escolher_foco(acoes, estrategia, HOJE)
        self.assertEqual(foco[0]["titulo"], "Ligada à meta")
        self.assertEqual(foco[0]["regra"], "meta_parada")
        self.assertIn("21 dias", foco[0]["motivo"])

    def test_teto_de_tres_e_sem_repeticao(self):
        acoes = _acoes({
            f"t{i}": _tarefa(titulo=f"Ação {i}", degradation_count=5, prazo_final=HOJE)
            for i in range(8)
        })
        foco = _escolher_foco(acoes, _SEM_ESTRATEGIA, HOJE)
        self.assertEqual(len(foco), 3)
        self.assertEqual(len({f["task_id"] for f in foco}), 3)

    def test_dia_vazio_nao_inventa_foco(self):
        self.assertEqual(_escolher_foco(_acoes({}), _SEM_ESTRATEGIA, HOJE), [])

    def test_foco_carrega_o_proximo_passo_do_plano(self):
        acoes = _acoes({"t": _tarefa(
            titulo="Com plano",
            plano_acao=[
                {"id": "1", "text": "Etapa feita", "completed": True},
                {"id": "2", "text": "Levantar os dados", "completed": False},
                {"id": "3", "text": "Etapa depois", "completed": False},
            ],
        )})
        foco = _escolher_foco(acoes, _SEM_ESTRATEGIA, HOJE)
        self.assertEqual(foco[0]["proximo_passo"], "Levantar os dados")


class TestColetaDeAcoes(unittest.TestCase):

    def test_separa_heranca_da_madrugada_do_que_foi_escolhido(self):
        """A distinção que o briefing das 5h perde hoje."""
        acoes = _acoes({
            "escolhida": _tarefa(titulo="Escolhida"),
            "arrastada": _tarefa(titulo="Arrastada", auto_data_atualizada=True, degradation_count=1),
            "critica": _tarefa(titulo="Crítica", auto_data_atualizada=True, degradation_count=4),
        })
        self.assertEqual(acoes["contadores"]["hoje"], 3)
        self.assertEqual(acoes["contadores"]["herdadas"], 2)
        self.assertEqual(acoes["contadores"]["criticas"], 1)

    def test_lane_desconhecida_cai_em_avanco_sem_aliasing(self):
        acoes = _acoes({
            "a": _tarefa(titulo="A", execution_lane="lane_inexistente"),
            "b": _tarefa(titulo="B", execution_lane="continuo"),
        })
        self.assertEqual([t["titulo"] for t in acoes["por_lane"]["avanco"]], ["A"])
        self.assertEqual([t["titulo"] for t in acoes["por_lane"]["continuo"]], ["B"])

    def test_placeholders_de_data_nao_viram_atraso(self):
        """'-' e '0000-00-00' são usados no lugar de null pelo frontend; se fossem
        comparados como string, ambos ficariam < hoje e o dia inteiro apareceria
        como atrasado."""
        acoes = _acoes({
            "sem_data": _tarefa(titulo="Stand-by", status="stand-by", data_limite="-"),
            "zerada": _tarefa(titulo="Zerada", data_limite="0000-00-00"),
        })
        self.assertEqual(acoes["atrasadas"], [])
        self.assertEqual(acoes["contadores"]["hoje"], 0)

    def test_atrasada_de_verdade_entra(self):
        acoes = _acoes({"t": _tarefa(titulo="Ficou para trás", data_limite="2026-08-17")})
        self.assertEqual([t["titulo"] for t in acoes["atrasadas"]], ["Ficou para trás"])

    def test_carga_da_semana_cobre_sete_dias_a_partir_de_hoje(self):
        acoes = _acoes({
            "hoje": _tarefa(data_limite=HOJE),
            "amanha": _tarefa(data_limite="2026-08-21"),
            "fora": _tarefa(data_limite="2026-09-15"),
        })
        carga = {c["data"]: c["total"] for c in acoes["carga_semana"]}
        self.assertEqual(len(carga), 7)
        self.assertEqual(carga[HOJE], 1)
        self.assertEqual(carga["2026-08-21"], 1)

    def test_prazo_duro_considera_acoes_de_qualquer_dia(self):
        """Uma ação marcada para semana que vem, mas com prazo final em 2 dias,
        precisa aparecer — é exatamente a que se perde."""
        acoes = _acoes({"t": _tarefa(titulo="Escondida", data_limite="2026-08-26", prazo_final="2026-08-22")})
        self.assertEqual([p["titulo"] for p in acoes["prazos_duros"]], ["Escondida"])
        self.assertEqual(acoes["contadores"]["hoje"], 0)

    def test_concluidas_ficam_de_fora(self):
        acoes = _acoes({
            "feita": _tarefa(titulo="Feita", status="concluido"),
            "ativa": _tarefa(titulo="Ativa"),
        })
        self.assertEqual(acoes["contadores"]["ativas"], 1)


class TestJanelasLivres(unittest.TestCase):

    def test_agenda_vazia_deixa_o_dia_inteiro_livre(self):
        janelas = _calcular_janelas_livres([])
        self.assertEqual(janelas, [{"inicio": "07:00", "fim": "19:00", "minutos": 720}])

    def test_buraco_entre_reunioes(self):
        janelas = _calcular_janelas_livres([
            {"inicio": "07:00", "fim": "10:00", "dia_inteiro": False},
            {"inicio": "14:00", "fim": "19:00", "dia_inteiro": False},
        ])
        self.assertEqual(janelas, [{"inicio": "10:00", "fim": "14:00", "minutos": 240}])

    def test_intervalo_curto_demais_nao_conta_como_janela(self):
        janelas = _calcular_janelas_livres([
            {"inicio": "07:00", "fim": "12:00", "dia_inteiro": False},
            {"inicio": "12:30", "fim": "19:00", "dia_inteiro": False},
        ])
        self.assertEqual(janelas, [])

    def test_eventos_sobrepostos_fundem(self):
        janelas = _calcular_janelas_livres([
            {"inicio": "09:00", "fim": "12:00", "dia_inteiro": False},
            {"inicio": "11:00", "fim": "13:00", "dia_inteiro": False},
        ])
        self.assertEqual(janelas, [
            {"inicio": "07:00", "fim": "09:00", "minutos": 120},
            {"inicio": "13:00", "fim": "19:00", "minutos": 360},
        ])

    def test_evento_de_dia_inteiro_nao_bloqueia(self):
        janelas = _calcular_janelas_livres([{"inicio": None, "fim": None, "dia_inteiro": True}])
        self.assertEqual(janelas, [{"inicio": "07:00", "fim": "19:00", "minutos": 720}])

    def test_evento_sem_fim_ocupa_uma_hora(self):
        janelas = _calcular_janelas_livres([{"inicio": "10:00", "fim": None, "dia_inteiro": False}])
        self.assertEqual(janelas, [
            {"inicio": "07:00", "fim": "10:00", "minutos": 180},
            {"inicio": "11:00", "fim": "19:00", "minutos": 480},
        ])


class TestEstrategia(unittest.TestCase):

    def test_meta_sem_acao_hoje_e_sem_movimento_entra_em_paradas(self):
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {"objetivoMacro": "Terminar o mestrado", "pilar": "intelectual", "status": "ativo"},
        }})
        est = _coletar_estrategia(db, HOJE, {}, {"m1": "2026-07-01"})
        self.assertEqual([m["objetivo"] for m in est["paradas"]], ["Terminar o mestrado"])
        self.assertEqual(est["metas"][0]["dias_parada"], 50)

    def test_meta_servida_hoje_nao_entra_em_paradas(self):
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {"objetivoMacro": "Meta viva", "pilar": "carreira", "status": "ativo"},
        }})
        est = _coletar_estrategia(db, HOJE, {"m1": [{"titulo": "Ação de hoje"}]}, {"m1": "2026-07-01"})
        self.assertEqual(est["paradas"], [])
        self.assertEqual(est["servidas_hoje"], 1)

    def test_meta_concluida_e_ignorada(self):
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {"objetivoMacro": "Já foi", "pilar": "saude", "status": "concluido"},
        }})
        self.assertEqual(_coletar_estrategia(db, HOJE, {}, {})["metas"], [])

    def test_progresso_de_metrica_absoluta(self):
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {
                "objetivoMacro": "Chegar a 85kg", "pilar": "saude", "status": "ativo",
                "metricaAlvo": {"valorInicial": 100, "valorAtual": 92.5, "valorObjetivo": 85, "unidade": "kg"},
            },
        }})
        self.assertEqual(_coletar_estrategia(db, HOJE, {}, {})["metas"][0]["progresso_pct"], 50)

    def test_meta_de_peso_le_a_pesagem_em_vez_do_valor_congelado(self):
        """O caso que originou isto: painel marcando 0% com o peso caindo todo dia.

        `metricaAlvo.valorAtual` guarda o valor de quando o objetivo foi criado e
        nunca era sincronizado com `health_weights`. 95 kg -> 80 kg com 93,6 kg
        medidos hoje sao 9% do caminho, nao zero.
        """
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {
                "objetivoMacro": "Sair de 95kg para 80kg", "pilar": "saude", "status": "ativo",
                "metricaAlvo": {"valorInicial": 95, "valorAtual": 95, "valorObjetivo": 80, "unidade": "kg"},
            },
        }})
        meta = _coletar_estrategia(db, HOJE, {}, {}, medicoes={"peso": 93.6})["metas"][0]
        self.assertEqual(meta["progresso_pct"], 9)
        self.assertEqual(meta["progresso_origem"], "automatica")
        self.assertEqual(meta["metrica_fonte"], "peso")
        self.assertEqual(meta["valor_atual"], 93.6)

    def test_metrica_sem_fonte_diz_que_nao_sabe_em_vez_de_zero(self):
        """Zero afirma "nao andou nada"; sem fonte e "ninguem esta medindo"."""
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {
                "objetivoMacro": "Cobrir custos com bolsas", "pilar": "financas", "status": "ativo",
                "metricaAlvo": {"valorInicial": 0, "valorAtual": 0, "valorObjetivo": 100,
                                "unidade": "% de cobertura"},
            },
        }})
        meta = _coletar_estrategia(db, HOJE, {}, {})["metas"][0]
        self.assertIsNone(meta["progresso_pct"])
        self.assertEqual(meta["progresso_origem"], "sem_fonte")
        self.assertIsNone(meta["metrica_fonte"])

    def test_valor_mexido_na_mao_continua_valendo(self):
        """Sem fonte automatica, mas alguem mantem o numero: nao e "sem fonte"."""
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {
                "objetivoMacro": "Publicar 10 artigos", "pilar": "intelectual", "status": "ativo",
                "metricaAlvo": {"valorInicial": 0, "valorAtual": 4, "valorObjetivo": 10, "unidade": "artigos"},
            },
        }})
        meta = _coletar_estrategia(db, HOJE, {}, {})["metas"][0]
        self.assertEqual((meta["progresso_pct"], meta["progresso_origem"]), (40, "manual"))

    def test_meta_sem_metrica_nao_finge_ter_indicador(self):
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {"objetivoMacro": "Ser referencia", "pilar": "carreira", "status": "ativo"},
        }})
        meta = _coletar_estrategia(db, HOJE, {}, {})["metas"][0]
        self.assertIsNone(meta["progresso_pct"])
        self.assertIsNone(meta["progresso_origem"])

    def test_pesagem_ausente_hoje_nao_derruba_para_sem_fonte(self):
        """Sem medicao no periodo, vale o ultimo valor anotado — nao "nao sei"."""
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {
                "objetivoMacro": "Sair de 95kg para 80kg", "pilar": "saude", "status": "ativo",
                "metricaAlvo": {"valorInicial": 95, "valorAtual": 94, "valorObjetivo": 80, "unidade": "kg"},
            },
        }})
        meta = _coletar_estrategia(db, HOJE, {}, {}, medicoes={})["metas"][0]
        self.assertEqual(meta["progresso_origem"], "manual")
        self.assertEqual(meta["progresso_pct"], 7)


class TestFonteDaMetrica(unittest.TestCase):
    """De onde o indicador tira o numero, e quando ele admite nao ter fonte."""

    def _meta(self, metrica, medicoes=None, pilar="saude"):
        db = _FakeDb({"estrategia_pessoal": {"m1": {
            "objetivoMacro": "Meta", "pilar": pilar, "status": "ativo", "metricaAlvo": metrica,
        }}})
        return _coletar_estrategia(db, HOJE, {}, {}, medicoes=medicoes or {})["metas"][0]

    def test_fonte_gravada_vazia_significa_desligada(self):
        """Chave gravada vazia e resposta, nao ausencia.

        `criar_objetivo_estrategico` grava `fonte` em toda meta absoluta. Sem
        distinguir chave ausente de chave vazia, a meta nova em kg nasceria ligada
        ao peso sem ninguem pedir — e desligar a fonte de uma meta de saude seria
        impossivel, porque a derivacao por unidade a religaria na leitura seguinte.
        """
        meta = self._meta({"valorInicial": 95, "valorAtual": 95, "valorObjetivo": 80,
                           "unidade": "kg", "fonte": ""}, medicoes={"peso": 93.6})
        self.assertIsNone(meta["metrica_fonte"])
        self.assertEqual(meta["progresso_origem"], "sem_fonte")

    def test_sem_a_chave_deriva_da_unidade(self):
        """Objetivo gravado antes do campo existir nao precisa de migracao."""
        meta = self._meta({"valorInicial": 95, "valorAtual": 95, "valorObjetivo": 80,
                           "unidade": "kg"}, medicoes={"peso": 93.6})
        self.assertEqual(meta["metrica_fonte"], "peso")
        self.assertEqual(meta["progresso_pct"], 9)

    def test_fonte_de_cintura_le_a_medida(self):
        meta = self._meta({"valorInicial": 110, "valorAtual": 110, "valorObjetivo": 90,
                           "unidade": "cm", "fonte": "cintura"}, medicoes={"cintura": 104})
        self.assertEqual((meta["progresso_pct"], meta["progresso_origem"]), (30, "automatica"))

    def test_fonte_desconhecida_nao_vira_derivacao(self):
        meta = self._meta({"valorInicial": 95, "valorAtual": 95, "valorObjetivo": 80,
                           "unidade": "kg", "fonte": "chute"}, medicoes={"peso": 93.6})
        self.assertIsNone(meta["metrica_fonte"])


class TestColetaDeCintura(unittest.TestCase):
    """O valor da cintura era descartado: so a data virava sinal de movimento.

    Meta ligada a fonte `cintura` lia sempre None e caia no valor manual antigo —
    a fonte automatica que o campo anuncia nunca chegava a valer.
    """

    def test_valor_mais_recente_de_cintura_e_coletado(self):
        db = _FakeDb({"health_waist": {
            "a": {"date": _shift(HOJE, -3), "cm": 106.0},
            "b": {"date": HOJE, "cm": 104.5},
        }})
        medida = _ultima_medida(db, "health_waist", "cm", HOJE)
        self.assertEqual((medida["ultimo"], medida["data"]), (104.5, HOJE))

    def test_sem_registro_devolve_nada_em_vez_de_zero(self):
        self.assertIsNone(_ultima_medida(_FakeDb({}), "health_waist", "cm", HOJE))

    def test_medida_zerada_nao_conta_como_medicao(self):
        db = _FakeDb({"health_waist": {"a": {"date": HOJE, "cm": 0}}})
        self.assertIsNone(_ultima_medida(db, "health_waist", "cm", HOJE))


class TestFlagDeMetaGeridaPorAcoes(unittest.TestCase):
    """A exclusao e pela flag do objetivo, nao por lista fixa de nomes de pilar.

    Toda funcionalidade de vinculo, sugestao ou elevacao le esta flag para saber
    quem NAO entra. Enquanto ela fosse `pilar != "saude"`, um objetivo novo
    orientado a dado nasceria dentro dessas funcionalidades, e a unica forma de
    tira-lo seria editar codigo.
    """

    def _meta(self, **campos):
        base = {"objetivoMacro": "Meta", "pilar": "carreira", "status": "ativo"}
        base.update(campos)
        return _coletar_estrategia(_FakeDb({"estrategia_pessoal": {"m1": base}}),
                                   HOJE, {}, {})["metas"][0]

    def test_flag_gravada_manda_sobre_o_pilar(self):
        self.assertFalse(self._meta(pilar="carreira", gerida_por_acoes=False)["gerida_por_acoes"])
        self.assertTrue(self._meta(pilar="saude", gerida_por_acoes=True)["gerida_por_acoes"])

    def test_sem_flag_gravada_deriva_do_pilar(self):
        """Objetivo criado antes do campo existir continua se comportando igual."""
        self.assertTrue(self._meta(pilar="intelectual")["gerida_por_acoes"])
        self.assertFalse(self._meta(pilar="saude")["gerida_por_acoes"])

    def test_meta_orientada_a_dado_fica_fora_do_denominador(self):
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {"objetivoMacro": "Por dado", "pilar": "financas", "status": "ativo",
                   "gerida_por_acoes": False},
            "m2": {"objetivoMacro": "Por acao", "pilar": "carreira", "status": "ativo"},
        }})
        est = _coletar_estrategia(db, HOJE, {"m2": [{"titulo": "x"}]}, {})
        self.assertEqual(est["total_geridas_por_acoes"], 1)
        self.assertEqual(est["servidas_hoje"], 1)


class TestMovimentoDaMeta(unittest.TestCase):

    def test_registro_de_marco_conta_como_movimento(self):
        """Uma meta pode se mexer sem nenhuma ação vinculada — via marco ou métrica."""
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {
                "objetivoMacro": "Meta com marco", "pilar": "carreira", "status": "ativo",
                "marcos": [{"id": "x", "descricao": "Marco", "concluido": False,
                            "registros": [{"id": "r", "data": "2026-08-19", "nota": "andou"}]}],
            },
        }})
        est = _coletar_estrategia(db, HOJE, {}, {})
        self.assertEqual(est["metas"][0]["dias_parada"], 1)
        self.assertEqual(est["paradas"], [])


class TestPilarSaude(unittest.TestCase):
    """O pilar saúde é executado pelos registros do módulo Saúde, não por ações —
    cobrar dele uma ação vinculada produz a afirmação falsa "parada há N dias"
    num dia em que o usuário se pesou de manhã."""

    def _db(self, pilar="saude"):
        return _FakeDb({"estrategia_pessoal": {
            "m1": {"objetivoMacro": "Sair de 95kg para 80kg", "pilar": pilar, "status": "ativo"},
        }})

    def test_meta_de_saude_usa_o_registro_do_modulo_como_movimento(self):
        est = _coletar_estrategia(self._db(), HOJE, {}, {}, movimento_saude=HOJE)
        self.assertEqual(est["metas"][0]["dias_parada"], 0)
        self.assertEqual(est["paradas"], [])

    def test_meta_de_saude_sem_registro_recente_ainda_aparece_como_parada(self):
        est = _coletar_estrategia(self._db(), HOJE, {}, {}, movimento_saude="2026-07-01")
        self.assertEqual([m["objetivo"] for m in est["paradas"]], ["Sair de 95kg para 80kg"])

    def test_meta_de_saude_fica_fora_do_denominador_de_metas_servidas(self):
        db = _FakeDb({"estrategia_pessoal": {
            "m1": {"objetivoMacro": "Meta de saúde", "pilar": "saude", "status": "ativo"},
            "m2": {"objetivoMacro": "Meta de carreira", "pilar": "carreira", "status": "ativo"},
        }})
        est = _coletar_estrategia(db, HOJE, {"m2": [{"titulo": "Ação"}]}, {}, movimento_saude=HOJE)
        self.assertEqual(est["total_geridas_por_acoes"], 1)
        self.assertEqual(est["servidas_hoje"], 1)

    def test_meta_de_outro_pilar_continua_dependendo_de_acoes(self):
        est = _coletar_estrategia(self._db(pilar="carreira"), HOJE, {}, {"m1": "2026-07-01"},
                                  movimento_saude=HOJE)
        self.assertFalse(est["metas"][0]["gerida_por_acoes"] is True and est["paradas"] == [])
        self.assertEqual([m["objetivo"] for m in est["paradas"]], ["Sair de 95kg para 80kg"])


class TestRotinasVerificaveis(unittest.TestCase):
    """Marcador de feito só nas rotinas que deixam rastro no sistema. "Almoçar com
    calma" é aviso, não item de checklist — e não deve ganhar marcador nenhum."""

    def test_rotinas_com_rastro_sao_reconhecidas(self):
        casos = [
            ({"id": "daily_weighin", "category": "custom"}, "pesagem"),
            ({"id": "waist_saturday", "category": "custom"}, "cintura"),
            ({"id": "morning_checkin", "category": "checkin_morning"}, "checkin_manha"),
            ({"id": "night_checkin", "category": "checkin_night"}, "checkin_noite"),
        ]
        for rotina, esperado in casos:
            self.assertEqual(_rotina_verificavel(rotina), esperado, rotina["id"])

    def test_avisos_ilustrativos_nao_ganham_marcador(self):
        for rotina_id, categoria in [("lunch_slow", "nutrition"), ("food_window", "nutrition"),
                                     ("strength_training", "spine"), ("fexofenadina_reminder", "custom")]:
            self.assertIsNone(_rotina_verificavel({"id": rotina_id, "category": categoria}), rotina_id)

    def test_categoria_tem_precedencia_sobre_id_renomeado(self):
        """O usuário pode renomear o doc do lembrete na UI; a categoria é o que ele
        de fato controla, então ela decide primeiro."""
        self.assertEqual(
            _rotina_verificavel({"id": "meu_checkin_custom", "category": "checkin_morning"}),
            "checkin_manha",
        )


class TestPersistencia(unittest.TestCase):
    """`merge=True` e um merge recursivo: uma chave que o coletor parou de emitir
    sobrevive no documento para sempre. Foi como `consolidacoes_whatsapp` continuou
    aparecendo na tela depois de removida do codigo."""

    class _FakeDocRef:
        def __init__(self):
            self.payload = None
            self.merge = None

        def set(self, payload, merge=None):
            self.payload, self.merge = payload, merge

    class _FakeDbSet:
        def __init__(self, ref):
            self._ref = ref

        def collection(self, _nome):
            return self

        def document(self, _id):
            return self._ref

    def test_grava_substituindo_cada_campo_do_coletor(self):
        ref = self._FakeDocRef()
        resumo = {"data": HOJE, "filas": {"contas": {"total": 0}}, "contadores": {"hoje": 1}}
        _persistir(self._FakeDbSet(ref), resumo)

        self.assertIsInstance(ref.merge, list, "merge=True apagaria a garantia de substituicao")
        self.assertNotEqual(ref.merge, True)
        # Todo campo produzido pelo coletor e substituido por inteiro...
        self.assertEqual(sorted(ref.merge), sorted(resumo.keys()))
        # ...e nada alem disso e tocado (visto_em / aderencia sobrevivem).
        self.assertNotIn("visto_em", ref.merge)


class TestDiaDaSemana(unittest.TestCase):

    def test_convencao_javascript_domingo_zero(self):
        """`daysOfWeek` das rotinas de saúde vem do Date.getDay() do JS (domingo=0),
        não do weekday() do Python (segunda=0)."""
        self.assertEqual(_js_weekday("2026-08-16"), 0)  # domingo
        self.assertEqual(_js_weekday("2026-08-17"), 1)  # segunda
        self.assertEqual(_js_weekday("2026-08-20"), 4)  # quinta
        self.assertEqual(_js_weekday("2026-08-22"), 6)  # sábado


class TestGranularidadeDeSubtarefa(unittest.TestCase):
    """Os critérios de aceite da especificação de 26/08/2026, no payload montado.

    Testar aqui e não só em `test_subtarefas` importa porque é este dict que o
    `obter_estado_atual` do MCP devolve — a regra pode estar certa e o campo não
    chegar na resposta.
    """

    def _plano_do_mago(self):
        """4 etapas para hoje, 3 para as semanas seguintes (critério 1)."""
        return [
            {"id": "e1", "text": "Congelar o escopo", "completed": False,
             "data_prevista": HOJE},
            {"id": "e2", "text": "Corrigir os erros", "completed": False,
             "data_prevista": HOJE},
            {"id": "e3", "text": "Anotar o que ficou de fora", "completed": False,
             "data_prevista": HOJE},
            {"id": "e4", "text": "Publicar e pedir validação", "completed": False,
             "data_prevista": HOJE},
            {"id": "e5", "text": "Revisar minhas questões", "completed": False,
             "data_prevista": "2026-08-31"},
            {"id": "e6", "text": "Encaminhar aos colegas", "completed": False,
             "data_prevista": "2026-09-01"},
            {"id": "e7", "text": "Retomar a fila de melhorias", "completed": False},
        ]

    def test_criterio_1_mostra_a_subtarefa_corrente_e_nao_as_sete(self):
        acoes = _acoes({"mago": _tarefa(titulo="Revisar Questões do Mago",
                                        plano_acao=self._plano_do_mago())})
        acao = acoes["por_lane"]["avanco"][0]
        self.assertEqual(acao["subtarefa_do_dia"]["texto"], "Congelar o escopo")
        self.assertEqual(acao["etapas_totais"], 7)
        self.assertEqual(acao["etapas_feitas"], 0)

    def test_criterio_2_avanco_e_pendencia_de_terceiro_ao_mesmo_tempo(self):
        plano = self._plano_do_mago()
        plano[:3] = [{**p, "estado": "feito", "completed": True} for p in plano[:3]]
        plano[3] = {**plano[3], "estado": "aguardando_terceiro",
                    "aguardando_de": "colegas do MAGO"}
        plano[4] = {**plano[4], "estado": "em_andamento"}

        acoes = _acoes({"mago": _tarefa(titulo="Mago", plano_acao=plano)})
        self.assertEqual(len(acoes["por_lane"]["avanco"]), 1,
                         "a ação avança por causa da etapa 5")
        acao = acoes["por_lane"]["avanco"][0]
        self.assertEqual([e["texto"] for e in acao["aguardando_terceiro"]],
                         ["Publicar e pedir validação"])
        self.assertEqual(acao["aguardando_terceiro"][0]["aguardando_de"], "colegas do MAGO")

    def test_acao_toda_em_espera_muda_de_faixa_sozinha(self):
        plano = [{"id": "a", "text": "esperar", "completed": False,
                  "estado": "aguardando_terceiro"}]
        acoes = _acoes({"x": _tarefa(titulo="Só espera", plano_acao=plano)})
        self.assertEqual(len(acoes["por_lane"]["aguardando_terceiro"]), 1)
        self.assertEqual(len(acoes["por_lane"]["avanco"]), 0)

    def test_criterio_5_acao_antiga_sem_os_campos_novos_nao_muda(self):
        """As 34 ações com plano em 26/08/2026 têm etapas só com {id, text, completed}."""
        plano = [{"id": "a", "text": "primeira", "completed": True},
                 {"id": "b", "text": "segunda", "completed": False}]
        acoes = _acoes({"velha": _tarefa(titulo="Velha", plano_acao=plano,
                                         degradation_count=4)})
        acao = acoes["por_lane"]["avanco"][0]
        self.assertEqual(acao["proximo_passo"], "segunda")
        self.assertEqual((acao["etapas_feitas"], acao["etapas_totais"]), (1, 2))
        self.assertEqual(acao["degradation_count"], 4, "o contador gravado não regride")
        self.assertEqual(acao["aguardando_terceiro"], [])

    def test_acao_sem_plano_nao_inventa_subtarefa(self):
        """9 das 43 ações ativas não têm plano nenhum."""
        acoes = _acoes({"sem": _tarefa(titulo="Sem plano", plano_acao=[])})
        acao = acoes["por_lane"]["avanco"][0]
        self.assertIsNone(acao["subtarefa_do_dia"])
        self.assertIsNone(acao["proximo_passo"])

    def test_alerta_critico_nomeia_a_etapa_que_esta_segurando(self):
        """"Adiada 33x" diz que algo está parado, não o quê."""
        plano = [{"id": "a", "text": "levantar o mapa de preços", "completed": False,
                  "degradation_count": 33}]
        acoes = _acoes({"compra": _tarefa(titulo="Processo de Compra",
                                          plano_acao=plano, degradation_count=33)})
        foco = _escolher_foco(acoes, _SEM_ESTRATEGIA, HOJE)
        critico = next(f for f in foco if f["regra"] == "degradacao_critica")
        self.assertIn("levantar o mapa de preços", critico["motivo"])
        self.assertIn("33", critico["motivo"])

    def test_alerta_critico_sem_contador_na_etapa_usa_a_mensagem_antiga(self):
        """Ação que acumulou adiamentos antes da mudança não tem contador por etapa."""
        plano = [{"id": "a", "text": "algum passo", "completed": False}]
        acoes = _acoes({"x": _tarefa(titulo="Velha", plano_acao=plano,
                                     degradation_count=7)})
        foco = _escolher_foco(acoes, _SEM_ESTRATEGIA, HOJE)
        critico = next(f for f in foco if f["regra"] == "degradacao_critica")
        self.assertIn("Adiada automaticamente 7x", critico["motivo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
