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


if __name__ == "__main__":
    unittest.main(verbosity=2)
