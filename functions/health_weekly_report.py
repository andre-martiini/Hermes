"""
Relatorio Semanal do Hermes (N14).

Fase 1: placa de resultado 100% em codigo (build_weekly_report_card).
Fase 2: regras de decisao / adjustment, tambem 100% em codigo, sem modelo
        (build_weekly_adjustment) -- resultado e texto seco, pronto para exibir.
Fase 3: auditoria do ajuste da semana anterior (build_weekly_audit, tambem em
        codigo) e a narrativa final escrita pelo modelo por cima dos dados ja
        computados (generate_weekly_narrative), com fallback textual quando o
        Gemini nao estiver disponivel.

Regra de arquitetura que atravessa as tres fases: a conta e feita em Python: o
modelo (quando entra, na Fase 3) so redige, nunca calcula, compara ou afirma
causa. Ver REVISAO-INBOX.md para a especificacao completa.

Roda todo domingo as 19h BRT. Semana = segunda 00:00 a domingo 18:59 BRT.
Persiste em health_weekly_reports/{YYYY-Www}.
"""
from datetime import datetime, timedelta, timezone

from firebase_functions import scheduler_fn, options

_RADICULAR_ORDER = ["gluteo", "quadril", "coxa", "joelho", "panturrilha", "tornozelo", "pe"]

PROMPT_VERSION = "n14-v1"

_RED_FLAG_REPORT_TEXT = (
    "Esta semana teve pelo menos um sinal de alerta clínico no registro diário "
    "(dormência na região da sela, alteração no controle de urina ou fezes, "
    "fraqueza progressiva para levantar a ponta do pé, sintoma nas duas pernas "
    "ao mesmo tempo, ou dor ≥ 9/10). Isto não é um diagnóstico — é uma lista de "
    "sinais que, se presentes, indicam buscar atendimento médico o quanto antes. "
    "Nenhum ajuste de rotina é proposto esta semana; a única recomendação é "
    "procurar atendimento."
)


def _week_bounds(reference_date: str):
    """reference_date (YYYY-MM-DD) deve ser um domingo. Retorna (week_start, week_end)."""
    ref = datetime.strptime(reference_date, "%Y-%m-%d")
    week_start = ref - timedelta(days=6)
    return week_start.strftime("%Y-%m-%d"), reference_date


def _dates_in_range(start: str, end: str) -> list[str]:
    d0 = datetime.strptime(start, "%Y-%m-%d")
    d1 = datetime.strptime(end, "%Y-%m-%d")
    return [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((d1 - d0).days + 1)]


def iso_week_key(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _avg(values):
    return sum(values) / len(values) if values else None


def _weight_avg7(db, as_of_date: str):
    """Media dos registros de peso nos 7 dias terminando em as_of_date (inclusive).
    None se houver menos de 3 registros -- media de 2 pontos nao e confiavel."""
    start = (datetime.strptime(as_of_date, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")
    docs = (
        db.collection("health_weights")
        .where("date", ">=", start)
        .where("date", "<=", as_of_date)
        .stream()
    )
    values = [d.to_dict().get("weight") for d in docs if d.to_dict().get("weight") is not None]
    return _avg(values) if len(values) >= 3 else None


def _waist_for_week(db, week_start: str, week_end: str):
    docs = list(
        db.collection("health_waist")
        .where("date", ">=", week_start)
        .where("date", "<=", week_end)
        .stream()
    )
    if not docs:
        return {"value": None, "delta": None}
    latest = max(docs, key=lambda d: d.to_dict().get("date", ""))
    value = latest.to_dict().get("cm")

    prev_start = (datetime.strptime(week_start, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    prev_end = (datetime.strptime(week_end, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    prev_docs = list(
        db.collection("health_waist")
        .where("date", ">=", prev_start)
        .where("date", "<=", prev_end)
        .stream()
    )
    delta = None
    if prev_docs and value is not None:
        prev_value = max(prev_docs, key=lambda d: d.to_dict().get("date", "")).to_dict().get("cm")
        if prev_value is not None:
            delta = round(value - prev_value, 2)
    return {"value": value, "delta": delta}


def _logs_for_week(db, week_start: str, week_end: str) -> dict:
    logs = {}
    for d in _dates_in_range(week_start, week_end):
        doc = db.collection("health_exercise_logs").document(d).get()
        if doc.exists:
            logs[d] = doc.to_dict() or {}
    return logs


def _most_distal_location(logs: dict):
    """Maior indice em _RADICULAR_ORDER entre os registros da semana com sintoma
    presente (exclui 'nenhum'/ausente). None se nao houver nenhum registro."""
    best_idx = None
    for data in logs.values():
        loc = (data.get("radicular") or {}).get("location")
        if loc in _RADICULAR_ORDER:
            idx = _RADICULAR_ORDER.index(loc)
            if best_idx is None or idx > best_idx:
                best_idx = idx
    return best_idx


def _radicular_trend(this_week_idx, last_week_idx) -> str:
    if this_week_idx is None or last_week_idx is None:
        return "sem_dado"
    if this_week_idx > last_week_idx:
        return "descendo"  # mais distal = pior (McKenzie: periferalizacao)
    if this_week_idx < last_week_idx:
        return "subindo"  # mais proximal = melhor (centralizacao)
    return "estável"


def build_weekly_report_card(db, week_end: str) -> dict:
    """Monta a placa de resultado da semana terminando em week_end (domingo,
    YYYY-MM-DD). Somente leitura -- sem efeitos colaterais."""
    week_start, week_end = _week_bounds(week_end)
    prev_week_end = (datetime.strptime(week_start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_week_start, _ = _week_bounds(prev_week_end)

    logs = _logs_for_week(db, week_start, week_end)
    prev_logs = _logs_for_week(db, prev_week_start, prev_week_end)

    weight_avg7 = _weight_avg7(db, week_end)
    weight_avg7_prev = _weight_avg7(db, prev_week_end)
    weight_delta = (
        round(weight_avg7 - weight_avg7_prev, 2)
        if weight_avg7 is not None and weight_avg7_prev is not None
        else None
    )

    km_total = 0.0
    km_days = 0
    for data in logs.values():
        day_km = sum((b.get("distance") or 0) for b in (data.get("walkBlocks") or []))
        if day_km > 0:
            km_total += day_km
            km_days += 1

    morning_vals = [data["pain"]["morning"] for data in logs.values() if (data.get("pain") or {}).get("morning") is not None]
    evening_vals = [data["pain"]["evening"] for data in logs.values() if (data.get("pain") or {}).get("evening") is not None]

    this_week_idx = _most_distal_location(logs)
    last_week_idx = _most_distal_location(prev_logs)

    therapy_planned_docs = (
        db.collection("health_events")
        .where("source", "==", "calendar")
        .where("date", ">=", week_start)
        .where("date", "<=", week_end)
        .stream()
    )
    therapy_planned = sum(
        1 for d in therapy_planned_docs if d.to_dict().get("type") in ("fisioterapia", "modalidade_terapeutica")
    )

    checkin_days = sum(
        1 for data in logs.values()
        if (data.get("pain") or {}).get("morning") is not None
        and (data.get("pain") or {}).get("evening") is not None
    )

    sleep_vals = [data["sleepQuality"]["quality"] for data in logs.values() if (data.get("sleepQuality") or {}).get("quality") is not None]

    return {
        "week_start": week_start,
        "week_end": week_end,
        "weight_avg7": weight_avg7,
        "weight_delta": weight_delta,
        "waist": _waist_for_week(db, week_start, week_end),
        "km_total": round(km_total, 2),
        "km_days": km_days,
        "pain_morning_avg": round(_avg(morning_vals), 1) if len(morning_vals) >= 4 else None,
        "pain_evening_avg": round(_avg(evening_vals), 1) if len(evening_vals) >= 4 else None,
        "radicular_trend": _radicular_trend(this_week_idx, last_week_idx),
        "strength_done": sum(1 for data in logs.values() if (data.get("strength") or {}).get("done")),
        "strength_planned": 3,
        "therapy_done": sum(1 for data in logs.values() if data.get("therapy")),
        "therapy_planned": therapy_planned,
        "checkin_adherence": round(checkin_days / 7, 2),
        "sleep_avg": round(_avg(sleep_vals), 1) if len(sleep_vals) >= 4 else None,
    }


# ---------------------------------------------------------------------------
# Fase 2 -- regras de decisao (100% em codigo, sem modelo)
# ---------------------------------------------------------------------------

def _fmt_pct(x: float) -> str:
    return f"{round(x * 100)}%"


def build_weekly_adjustment(week_logs: dict, card: dict, prev_card: dict | None) -> dict:
    """Aplica as regras de decisao do N14 (Fase 2), na ordem de precedencia, e
    para na primeira que casar. Retorna {"rule": chave estavel para a
    auditoria da Fase 3, "text": frase pronta em portugues -- texto seco, sem
    passar por modelo nenhum -- ou None no caso do sinal vermelho, onde nenhum
    ajuste e proposto}."""
    from hermes_core_logic import _health_red_flag_active

    if any(_health_red_flag_active(data) for data in week_logs.values()):
        return {"rule": "sinal_vermelho", "text": None}

    if card["radicular_trend"] == "descendo":
        return {
            "rule": "reduzir_carga",
            "text": (
                "Reduzir carga nesta semana. O sintoma radicular avançou em direção "
                "ao pé (periferalização) — o sinal clínico mais importante do painel."
            ),
        }

    # Parte 5: semana com dado demais escasso vira "registrar", nao dieta/treino --
    # calcular tendencia ou aderencia sobre poucos pontos e o tipo de erro que
    # o codigo nao deve cometer, entao nem tenta.
    if card["weight_avg7"] is None and card["checkin_adherence"] < 0.5:
        return {
            "rule": "poucos_dados",
            "text": (
                "Semana com pouco registro. Sem pesagens suficientes e com menos da "
                "metade dos check-ins preenchidos, não dá para calcular nada com "
                "confiança. O ajuste desta semana é simples: registrar mais — nada de "
                "mudar dieta ou treino sobre um dado que não existe."
            ),
        }

    if card["checkin_adherence"] < 0.7 or card["strength_done"] < 2:
        return {
            "rule": "aderencia",
            "text": (
                f"Foco em aderência esta semana, nada mais. Check-in em "
                f"{_fmt_pct(card['checkin_adherence'])} e treino de força em "
                f"{card['strength_done']}/{card['strength_planned']}. Apertar dieta ou "
                f"treino numa semana em que a prescrição não foi seguida só mascara o "
                f"problema real."
            ),
        }

    prev_weight_delta = prev_card.get("weight_delta") if prev_card else None

    if (
        card["weight_delta"] is not None and card["weight_delta"] >= 0
        and prev_weight_delta is not None and prev_weight_delta >= 0
        and card["checkin_adherence"] >= 0.8
    ):
        return {
            "rule": "cortar_kcal",
            "text": (
                "Cortar cerca de 200 kcal/dia. O peso ficou estável ou subiu por duas "
                "semanas seguidas, com boa aderência — o gargalo agora é o déficit "
                "calórico, não o volume de treino ou caminhada."
            ),
        }

    if (
        card["weight_delta"] is not None and card["weight_delta"] < -1.2
        and prev_weight_delta is not None and prev_weight_delta < -1.2
    ):
        return {
            "rule": "aumentar_kcal",
            "text": (
                "Aumentar a ingestão. A perda de peso passou de 1,2 kg por semana em "
                "duas semanas seguidas — ritmo rápido demais, com risco de perder "
                "massa magra."
            ),
        }

    return {
        "rule": "manter",
        "text": (
            "Manter a rotina atual. A semana ficou dentro do esperado — nenhuma "
            "mudança em dieta, treino ou caminhada é necessária agora."
        ),
    }


# ---------------------------------------------------------------------------
# Fase 3 -- auditoria do ajuste anterior (100% em codigo) e narrativa (modelo)
# ---------------------------------------------------------------------------

def build_weekly_audit(prev_report: dict | None, card: dict) -> dict:
    """Compara o adjustment_rule persistido na semana passada com o card desta
    semana. 100% em codigo -- devolve dado, nao prosa; quem vira frase e
    generate_weekly_narrative (ou o fallback textual abaixo) por cima disto."""
    if not prev_report:
        return {"has_previous": False}

    prev_rule = prev_report.get("adjustment_rule")
    prev_text = prev_report.get("adjustment")
    if not prev_rule or prev_rule in ("sinal_vermelho", "manter"):
        outcome = "neutro" if prev_rule == "manter" else "sem_dado"
        return {
            "has_previous": bool(prev_rule),
            "previous_rule": prev_rule,
            "previous_text": prev_text,
            "outcome": outcome if prev_rule else "sem_dado",
        }

    weight_delta = card.get("weight_delta")
    outcome = "sem_dado"
    if prev_rule == "cortar_kcal":
        if weight_delta is not None:
            outcome = "funcionou" if weight_delta < 0 else "nao_funcionou"
    elif prev_rule == "aumentar_kcal":
        if weight_delta is not None:
            outcome = "funcionou" if weight_delta > -1.2 else "nao_funcionou"
    elif prev_rule == "reduzir_carga":
        trend = card.get("radicular_trend")
        if trend in ("subindo", "estável"):
            outcome = "funcionou"
        elif trend == "descendo":
            outcome = "nao_funcionou"
    elif prev_rule in ("aderencia", "poucos_dados"):
        if card.get("checkin_adherence", 0) >= 0.7 and card.get("strength_done", 0) >= 2:
            outcome = "funcionou"
        else:
            outcome = "nao_funcionou"

    return {
        "has_previous": True,
        "previous_rule": prev_rule,
        "previous_text": prev_text,
        "outcome": outcome,
        "weight_delta": weight_delta,
    }


def _audit_fallback_text(audit: dict) -> str | None:
    """Frase seca, sempre disponivel, calculada 100% em codigo -- e o que fica
    persistido no campo `audit`. A narrativa (Fase 3, com modelo) reusa este
    texto como uma das entradas, mas nao depende dele para existir."""
    if not audit.get("has_previous"):
        return None
    outcome_text = {
        "funcionou": "o resultado foi na direção esperada",
        "nao_funcionou": "o resultado ainda não apareceu",
        "neutro": "nada mudou, como esperado",
        "sem_dado": "ainda não dá para dizer",
    }.get(audit.get("outcome"), "ainda não dá para dizer")
    previous_text = audit.get("previous_text") or "manter a rotina"
    return f"Semana passada, o ajuste foi: {previous_text} Resultado: {outcome_text}."


def _dry_fallback_narrative(card: dict, adjustment_text: str | None, audit_text: str | None) -> str:
    """Usado quando nao ha chave Gemini configurada ou a chamada falha -- o
    relatorio continua util, so mais seco. Mesmos numeros da placa, nenhuma
    conta nova."""
    def fmt(v, suffix=""):
        return f"{v:.1f}{suffix}".replace(".", ",") if v is not None else "ainda não dá para dizer"

    parts = [
        f"Semana de {card['week_start']} a {card['week_end']}.",
        (
            f"Peso médio de 7 dias: {fmt(card['weight_avg7'], ' kg')}. "
            f"Caminhada: {card['km_total']:.1f} km em {card['km_days']} dia(s). "
            f"Treino de força: {card['strength_done']}/{card['strength_planned']}. "
            f"Aderência ao check-in: {_fmt_pct(card['checkin_adherence'])}."
        ),
        adjustment_text or "Sem ajuste definido esta semana.",
    ]
    if audit_text:
        parts.append(audit_text)
    parts.append(
        "Texto gerado sem modelo de linguagem (Gemini indisponível no momento) — "
        "os números acima batem exatamente com a placa da semana."
    )
    return "\n\n".join(parts)


def _format_card_for_display(card: dict) -> dict:
    """N22: formata o card para exibicao -- pt-BR com virgula, porcentagem em vez
    de fracao, `null` como a string literal "ainda nao da pra dizer" -- antes de
    passar pro modelo. Achado do revisor: o modelo recebia `checkin_adherence:
    0.14` cru e escrevia "0,14" na narrativa, enquanto o tile da UI mostra
    "14%"; e `pain_evening_avg: 3.8` batia com ponto no tile, virgula na
    narrativa. A UI e o modelo devem ler do mesmo texto pronto, nao cada um
    formatar o numero cru do seu jeito. So usado para montar o prompt -- o
    `card` numerico que vai pro Firestore continua intacto, e a UI segue
    formatando os proprios tiles a partir dele."""
    NAO_DA_PRA_DIZER = "ainda não dá para dizer"

    def kg(v):
        return f"{v:.1f}".replace(".", ",") + " kg" if v is not None else NAO_DA_PRA_DIZER

    def cm(v):
        return f"{v:.1f}".replace(".", ",") + " cm" if v is not None else NAO_DA_PRA_DIZER

    def dor(v):
        return f"{v:.1f}".replace(".", ",") + "/10" if v is not None else NAO_DA_PRA_DIZER

    def pct(v):
        return f"{round(v * 100)}%" if v is not None else NAO_DA_PRA_DIZER

    def sono(v):
        return f"{v:.1f}".replace(".", ",") + "/5" if v is not None else NAO_DA_PRA_DIZER

    waist = card.get("waist") or {}
    return {
        "semana": f"{card['week_start']} a {card['week_end']}",
        "peso_medio_7d": kg(card.get("weight_avg7")),
        "peso_variacao_vs_semana_anterior": kg(card.get("weight_delta")) if card.get("weight_delta") is not None else NAO_DA_PRA_DIZER,
        "cintura": cm(waist.get("value")),
        "cintura_variacao": cm(waist.get("delta")) if waist.get("delta") is not None else NAO_DA_PRA_DIZER,
        "caminhada_km_total_semana": f"{card['km_total']:.1f}".replace(".", ",") + " km",
        "caminhada_dias_com_registro": f"{card['km_days']} de 7 dias",
        "dor_manha_media": dor(card.get("pain_morning_avg")),
        "dor_noite_media": dor(card.get("pain_evening_avg")),
        "tendencia_sintoma_radicular": card.get("radicular_trend"),
        "treino_de_forca": f"{card['strength_done']} de {card['strength_planned']} sessões previstas",
        "terapia": f"{card['therapy_done']} de {card['therapy_planned']} sessões previstas",
        "aderencia_ao_checkin": pct(card.get("checkin_adherence")),
        "sono_medio": sono(card.get("sleep_avg")),
    }


def generate_weekly_narrative(db, card: dict, adjustment_text: str | None, audit_text: str | None) -> str | None:
    """Fase 3: o modelo escreve a versao amigavel por cima do que o codigo ja
    decidiu. Nunca calcula, compara semanas ou afirma causa -- essas contas ja
    vieram prontas nos parametros. Retorna None se nao houver chave Gemini ou
    a chamada falhar (o chamador cai para _dry_fallback_narrative)."""
    import json

    from main import get_gemini_api_key
    from gemini_cost_controls import GEMINI_FRONTIER_MODEL, generate_content_logged

    api_key = get_gemini_api_key()
    if not api_key:
        return None

    from google import genai
    from google.genai import types as genai_types

    card_json = json.dumps(_format_card_for_display(card), ensure_ascii=False, indent=2)

    prompt = f"""Você escreve o relatório semanal de saúde do André para ele mesmo ler, em português.

Todos os números abaixo já foram calculados por código — você só redige. Nunca
calcule, some, divida ou compare número nenhum por conta própria; use exatamente
os que estão aqui.

PLACA DA SEMANA (JSON, única fonte de números permitida):
{card_json}

AJUSTE DESTA SEMANA (já decidido por regra — redija-o, não proponha outro):
{adjustment_text or "Nenhum — sem ajuste esta semana."}

AUDITORIA DO AJUSTE DA SEMANA PASSADA (já calculada — só redija):
{audit_text or "Sem relatório da semana anterior para comparar."}

Regras obrigatórias, sem exceção:
- Não calcule, recalcule, some ou compare nenhum número — use só os que estão acima.
- Não afirme causa. Nunca "porque", "por causa de", "graças a".
- Não correlacione nada.
- Não projete data para atingir meta nenhuma.
- Não dê nota, pontuação ou classificação da semana.
- Proponha no máximo o ajuste que já veio pronto acima — nunca um adicional.
- Não toque em medicação, não interprete laudo, não sugira interromper tratamento.
- Segunda pessoa, direto, tom adulto. Sem elogio automático, sem repreensão, sem
  entusiasmo de enfeite — o André lê isso 52 vezes por ano.
- Um campo que chegou como "ainda não dá para dizer" continua exatamente assim
  no texto — nunca vira número nem some.

Formato — seis blocos curtos, cada um com 1 a 3 frases, sem markdown, sem
títulos numerados:
1. O que aconteceu na semana
2. O número que mais importa esta semana
3. O ajuste (a frase que já veio pronta acima, em tom de conversa)
4. Sinais de alerta (quase sempre "nenhum")
5. O que a auditoria da semana anterior mostrou (se houver)
6. Uma pergunta para observar na semana que vem

Responda só o texto corrido, sem JSON, sem "Bloco 1" etc. — só os parágrafos."""

    try:
        client = genai.Client(api_key=api_key)
        response = generate_content_logged(
            client,
            model=GEMINI_FRONTIER_MODEL,
            contents=prompt,
            feature="relatorio_semanal_saude",
            db=db,
            config=genai_types.GenerateContentConfig(temperature=0.4),
        )
        text = (response.text or "").strip()
        return text or None
    except Exception as exc:
        print(f"[RelatorioSaude] Falha ao gerar narrativa: {exc}")
        return None


@scheduler_fn.on_schedule(
    schedule="0 19 * * 0",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
)
def gerar_relatorio_semanal_saude(event: scheduler_fn.ScheduledEvent = None) -> None:
    """Agendada domingo 19h BRT -- monta a placa (Fase 1), decide o ajuste
    (Fase 2), audita o ajuste da semana passada e gera a narrativa (Fase 3), e
    persiste tudo em health_weekly_reports."""
    from main import get_db, _get_telegram_token
    from hermes_core_logic import _get_allowed_chat_id, _send_telegram_message
    from zoneinfo import ZoneInfo

    db = get_db()
    week_end = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
    report_id = iso_week_key(week_end)

    report_ref = db.collection("health_weekly_reports").document(report_id)
    if report_ref.get().exists:
        print(f"[RelatorioSaude] Relatório {report_id} já existe.")
        return

    try:
        week_start, _ = _week_bounds(week_end)
        week_logs = _logs_for_week(db, week_start, week_end)
        card = build_weekly_report_card(db, week_end)

        prev_week_end = (datetime.strptime(week_start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        prev_doc = db.collection("health_weekly_reports").document(iso_week_key(prev_week_end)).get()
        prev_report = prev_doc.to_dict() if prev_doc.exists else None
        prev_card = prev_report.get("card") if prev_report else None

        adjustment = build_weekly_adjustment(week_logs, card, prev_card)
        audit = build_weekly_audit(prev_report, card)
        audit_text = _audit_fallback_text(audit)

        if adjustment["rule"] == "sinal_vermelho":
            text = _RED_FLAG_REPORT_TEXT
            prompt_version = None
        else:
            text = generate_weekly_narrative(db, card, adjustment["text"], audit_text)
            prompt_version = PROMPT_VERSION if text else None
            if text is None:
                text = _dry_fallback_narrative(card, adjustment["text"], audit_text)

        report_ref.set({
            "card": card,
            "adjustment": adjustment["text"],
            "adjustment_rule": adjustment["rule"],
            "text": text,
            "audit": audit_text,
            "prompt_version": prompt_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"[RelatorioSaude] {report_id}: rule={adjustment['rule']} card={card}")

        chat_id = _get_allowed_chat_id()
        if not chat_id:
            print("[RelatorioSaude] Nenhum chat_id configurado; relatório apenas salvo no Firestore.")
            return

        parts = []
        if card["weight_avg7"] is not None:
            parts.append(f"peso média 7d {card['weight_avg7']:.1f} kg")
        parts.append(f"{card['km_total']:.1f} km em {card['km_days']} dia(s)")
        parts.append(f"força {card['strength_done']}/{card['strength_planned']}")
        resumo = ", ".join(parts) + "."
        ajuste_linha = (
            f"\n\nAjuste: {adjustment['text']}"
            if adjustment["text"]
            else "\n\n⚠️ Sinais de alerta identificados — procure atendimento."
        )
        message = f"📊 Relatório semanal disponível ({card['week_start']} a {card['week_end']}).\n\n{resumo}{ajuste_linha}"
        _send_telegram_message(_get_telegram_token(db), chat_id, message)
    except Exception as exc:
        print(f"[RelatorioSaude] Falha ao gerar relatório semanal: {exc}")
