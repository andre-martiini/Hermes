"""O que aconteceu em cada dia de um mes, a partir das acoes do Gaspar.

Feito para o registro da execucao do PGD no Petrvs (skill `pgd-execucao`): o
Claude precisa saber, dia util a dia util, o que foi feito, e quais dias uteis
ficaram sem nada registrado para perguntar ao dono em vez de inventar.

Por que uma tool propria: `consultar_historico_acoes` acha acoes pelo prazo
(`data_limite`), e uma acao com diario em setembro pode ter prazo em outubro;
ela tambem corta o diario nas 3 ultimas entradas. Aqui a varredura e pelo
DIARIO (`acompanhamento[].data`) e pela conclusao (`data_conclusao`), o mesmo
criterio do coletor do diario pessoal, mas com a data convertida para o fuso
de Brasilia: uma nota das 22h vale para o dia em que foi escrita.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")
MAX_CHARS_NOTA = 240
MAX_NOTAS_POR_ACAO_DIA = 4
AREAS_EXCLUIDAS_PADRAO = ("FAMÍLIA",)

_DIAS_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")

# Notas que o proprio sistema escreve ao mexer em data, card ou lembrete: nao
# dizem o que foi feito no trabalho.
_NOTAS_AUTOMATICAS = re.compile(
    r"(A[cç][aã]o editada via card de confirma|A[cç][aã]o editada em lote|Motivo do ajuste:|"
    r"Lembrete agendado para|Campos alterados:)",
    re.IGNORECASE,
)


def _pascoa(ano: int) -> date:
    """Domingo de Pascoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    dia = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> dict[str, tuple[str, str]]:
    """{YYYY-MM-DD: (nome, tipo)}; tipo 'feriado' ou 'ponto_facultativo'.

    So os nacionais. Feriado estadual ou municipal (ex.: em Vitoria) fica para o
    dono dizer, porque depende de onde ele trabalhou.
    """
    fixos = {
        (1, 1): "Confraternização Universal", (4, 21): "Tiradentes", (5, 1): "Dia do Trabalho",
        (9, 7): "Independência do Brasil", (10, 12): "Nossa Senhora Aparecida", (11, 2): "Finados",
        (11, 15): "Proclamação da República", (11, 20): "Dia Nacional de Zumbi e da Consciência Negra",
        (12, 25): "Natal",
    }
    saida = {date(ano, m, d).isoformat(): (nome, "feriado") for (m, d), nome in fixos.items()}
    pascoa = _pascoa(ano)
    for delta, nome, tipo in ((-48, "Carnaval", "ponto_facultativo"), (-47, "Carnaval", "ponto_facultativo"),
                              (-46, "Quarta-feira de Cinzas (até 14h)", "ponto_facultativo"),
                              (-2, "Sexta-feira Santa", "feriado"), (60, "Corpus Christi", "ponto_facultativo")):
        saida[(pascoa + timedelta(days=delta)).isoformat()] = (nome, tipo)
    return saida


def data_local(valor) -> str | None:
    """YYYY-MM-DD no fuso de Brasilia; aceita ISO, ISO com Z, so data e datetime."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        instante = valor
    else:
        texto = str(valor).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
            return texto
        try:
            instante = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            return texto[:10] if re.match(r"\d{4}-\d{2}-\d{2}", texto) else None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(FUSO).date().isoformat()


def _texto_da_nota(nota) -> str:
    from personal_diary import _diary_note_to_plain_text

    texto = _diary_note_to_plain_text(str(nota or "")).strip()
    if len(texto) > MAX_CHARS_NOTA:
        texto = texto[:MAX_CHARS_NOTA - 1].rstrip() + "…"
    return texto


def montar_mes(tarefas: list[dict], mes: str, excluir_areas=AREAS_EXCLUIDAS_PADRAO, *,
               areas=None, de: int = 1, ate: int | None = None, com_notas: bool = True) -> dict:
    """Agrupa por dia o que as acoes registram no mes `YYYY-MM` (logica pura).

    Um mes inteiro com todas as notas passa de 900 mil caracteres (medido em
    09/2026: 121 acoes, ate 152 notas num dia). Por isso: `areas` restringe as
    areas tematicas, `de`/`ate` fatiam os dias e `com_notas=False` traz so
    titulos e contagens.
    """
    ano, num_mes = (int(p) for p in mes.split("-"))
    ultimo = calendar.monthrange(ano, num_mes)[1]
    feriados = feriados_nacionais(ano)
    excluir = {str(a).strip().upper() for a in (excluir_areas or [])}
    incluir = {str(a).strip().upper() for a in areas} if areas else None
    ate = min(ate or ultimo, ultimo)

    por_dia: dict[str, dict[str, dict]] = {}
    acoes_no_mes: set[str] = set()
    for tarefa in tarefas:
        area = str(tarefa.get("area_tematica") or "").strip().upper()
        if area in excluir or (incluir is not None and area not in incluir):
            continue
        status = str(tarefa.get("status") or "").strip().lower()
        if status.startswith("exclu"):
            continue
        tid = tarefa.get("id")

        def item(dia):
            return por_dia.setdefault(dia, {}).setdefault(tid, {
                "acao_id": tid,
                "titulo": str(tarefa.get("titulo") or "(sem título)"),
                "area_tematica": tarefa.get("area_tematica") or None,
                "processo_sei": tarefa.get("processo_sei") or None,
                "notas": [],
                "total_notas": 0,
                "concluida_no_dia": False,
            })

        for entrada in tarefa.get("acompanhamento") or []:
            if not isinstance(entrada, dict):
                continue
            dia = data_local(entrada.get("data"))
            if not dia or not dia.startswith(mes):
                continue
            nota = str(entrada.get("nota") or "")
            if not nota.strip() or _NOTAS_AUTOMATICAS.search(nota):
                continue
            registro = item(dia)
            registro["total_notas"] += 1
            if com_notas and len(registro["notas"]) < MAX_NOTAS_POR_ACAO_DIA:
                registro["notas"].append(_texto_da_nota(nota))
            acoes_no_mes.add(tid)

        conclusao = data_local(tarefa.get("data_conclusao"))
        if conclusao and conclusao.startswith(mes) and status.startswith("conclu"):
            item(conclusao)["concluida_no_dia"] = True
            acoes_no_mes.add(tid)

    dias, sem_atividade = [], []
    for d in range(max(1, de), ate + 1):
        dia = date(ano, num_mes, d)
        chave = dia.isoformat()
        feriado = feriados.get(chave)
        util = dia.weekday() < 5 and feriado is None
        atividades = sorted(por_dia.get(chave, {}).values(), key=lambda a: a["titulo"])
        if not com_notas:
            atividades = [{k: v for k, v in a.items() if k != "notas"} for a in atividades]
        if not atividades and not util and not (feriado and dia.weekday() < 5):
            continue
        dias.append({
            "data": chave,
            "dia_semana": _DIAS_SEMANA[dia.weekday()],
            "util": util,
            "feriado": {"nome": feriado[0], "tipo": feriado[1]} if feriado else None,
            "atividades": atividades,
        })
        if util and not atividades:
            sem_atividade.append(chave)

    return {
        "mes": mes,
        "dias": dias,
        "dias_uteis_sem_atividade": sem_atividade,
        "acoes_no_mes": len(acoes_no_mes),
        "areas_excluidas": sorted(excluir),
        "areas_incluidas": sorted(incluir) if incluir is not None else None,
        "periodo": f"{mes}-{max(1, de):02d} a {mes}-{ate:02d}",
        "observacao": (
            "Dia a dia pelo diário das ações (fuso de Brasília) e pela conclusão. Notas automáticas de edição "
            f"e lembrete ficam de fora; até {MAX_NOTAS_POR_ACAO_DIA} notas por ação e dia, cada uma cortada em "
            f"{MAX_CHARS_NOTA} caracteres (total_notas diz quantas havia; obter_acao traz a íntegra). "
            "Feriados só nacionais: estaduais e municipais o dono informa. Fim de semana só aparece se teve atividade."
        ),
    }


def consultar(ctx, args: dict) -> dict:
    mes = str(args.get("mes") or "").strip()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mes):
        return {"erro": "`mes` precisa ser YYYY-MM (ex.: 2026-09)."}
    excluir = args.get("excluir_areas")
    areas = args.get("areas")
    for nome, valor in (("excluir_areas", excluir), ("areas", areas)):
        if valor is not None and not isinstance(valor, list):
            return {"erro": f"`{nome}` precisa ser uma lista de áreas temáticas."}
    if excluir is None:
        excluir = AREAS_EXCLUIDAS_PADRAO
    try:
        de = int(args.get("dia_inicio") or 1)
        ate = int(args["dia_fim"]) if args.get("dia_fim") else None
    except (TypeError, ValueError):
        return {"erro": "`dia_inicio` e `dia_fim` são números de dia do mês (1 a 31)."}
    if de < 1 or (ate is not None and ate < de):
        return {"erro": "`dia_inicio` precisa ser 1 ou mais e `dia_fim` não pode ser menor que ele."}
    com_notas = args.get("com_notas", True) is not False
    tarefas = []
    for snap in ctx.db.collection("tarefas").stream():
        dados = snap.to_dict() or {}
        dados["id"] = snap.id
        tarefas.append(dados)
    return montar_mes(tarefas, mes, excluir, areas=areas, de=de, ate=ate, com_notas=com_notas)
