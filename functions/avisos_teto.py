"""Avisos do teto do PicPay no Telegram (teste pedido pelo André em 30/10/2026; tira-se se não servir).

- Marcos de 50%, 80% e 100% do teto: uma vez cada no mês (checados de hora em hora).
- Ritmo, às 20h: se o gasto vai mais de 15% à frente do mês, quanto dá por dia até o fim.
- Dia 1º às 9h: pagar as contas na XP e mandar o teto para o PicPay.
- Último dia às 20h: o que sobrou vai para o cofrinho (ou quanto estourou).
- Pix a partir de PIX_GRANDE pergunta se é gasto, transferência ou conta fixa
  (`sync_pix_emails` manda; `handle` trata o botão `pixcls:<id>:<g|t|f>`).
- A linha do teto no check-in de domingo vem de `linha_semanal`.

O cálculo é o de `gasto_avulso` (o mesmo da notificação de Pix e do app). Cada envio
cria `avisos_teto/{AAAA-MM}_{chave}` com `create`, que é atômico: não repete.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from firebase_functions import options, scheduler_fn
from google.api_core.exceptions import AlreadyExists

import gasto_avulso as ga
from agent_runs import instrumentada

PIX_GRANDE = 300
MARCOS = (100, 80, 50)  # do maior para o menor: só o maior ainda não avisado vai
HORA_RITMO = 20
HORA_INICIO = 9
FOLGA_RITMO = 1.15
CALLBACK = "pixcls:"
CLASSES = {"g": (None, "gasto"), "t": ("Transferência", "transferência"), "f": ("Conta fixa", "conta fixa")}

R = ga._reais


def _dias_no_mes(hoje: date) -> int:
    return calendar.monthrange(hoje.year, hoje.month)[1]


def marcos_atingidos(resumo: dict) -> list[int]:
    orcamento = resumo["orcamento"]
    if not orcamento:
        return []
    return [m for m in MARCOS if resumo["gasto"] * 100 >= orcamento * m]


def texto_marco(marco: int, resumo: dict, hoje: date) -> str:
    gasto, orcamento, saldo = resumo["gasto"], resumo["orcamento"], resumo["saldo"]
    depois_de_hoje = _dias_no_mes(hoje) - hoje.day
    if marco == 100:
        faltam = f"e ainda faltam {depois_de_hoje} dias no mês" if depois_de_hoje else "no último dia do mês"
        return (f"🚨 Teto do PicPay estourado: R$ {R(gasto)} de R$ {R(orcamento)} "
                f"(R$ {R(-saldo)} acima), {faltam}.")
    dias = depois_de_hoje + 1
    return (f"💳 Você chegou a {marco}% do teto do PicPay (R$ {R(gasto)} de R$ {R(orcamento)}). "
            f"Restam R$ {R(saldo)}: R$ {R(saldo // dias)} por dia até o fim do mês.")


def avisos_da_hora(resumo: dict, hoje: date, hora: int) -> list[tuple[str, str]]:
    """(chave, texto) do início do mês, do ritmo e do fim do mês. Os marcos ficam em `marcos_atingidos`."""
    orcamento, gasto, saldo = resumo["orcamento"], resumo["gasto"], resumo["saldo"]
    if orcamento is None:
        return []
    dias_mes = _dias_no_mes(hoje)
    avisos = []
    if hoje.day == 1 and hora == HORA_INICIO:
        avisos.append(("inicio", f"📅 Mês novo. Pague as contas na XP e mande R$ {R(orcamento)} para o PicPay; "
                                 "o que sobrar vai para o cofrinho."))
    if hora == HORA_RITMO and hoje.day == dias_mes:
        texto = (f"🐷 Fim do mês: sobraram R$ {R(saldo)} no teto do PicPay. Mande para o cofrinho." if saldo > 0
                 else f"Fim do mês: o teto do PicPay estourou em R$ {R(-saldo)}.")
        avisos.append(("fim", texto))
    elif hora == HORA_RITMO and saldo > 0:
        uso, tempo = gasto / orcamento, hoje.day / dias_mes
        if uso > tempo * FOLGA_RITMO and uso > 0.1:
            restantes = dias_mes - hoje.day
            avisos.append((f"ritmo_{hoje.day:02d}",
                           f"⚠️ Você usou {uso:.0%} do teto do PicPay em {tempo:.0%} do mês. Para fechar no teto: "
                           f"R$ {R(saldo // restantes)} por dia nos próximos {restantes} dias."))
    return avisos


def linha_semanal(transacoes, settings: dict, hoje: date) -> str | None:
    """Linha do teto no check-in de domingo, ou None sem teto definido."""
    resumo = ga.resumo_do_mes(transacoes, settings, hoje.year, hoje.month)
    if resumo["orcamento"] is None:
        return None
    semana = ga.gasto_do_teto_centavos(transacoes, hoje - timedelta(days=6), hoje)
    linha = f"💳 Teto do PicPay: R$ {R(semana)} na semana, R$ {R(resumo['gasto'])} de R$ {R(resumo['orcamento'])} no mês."
    if resumo["saldo"] > 0:
        dias = _dias_no_mes(hoje) - hoje.day + 1
        return f"{linha} Restam R$ {R(resumo['saldo'])} (R$ {R(resumo['saldo'] // dias)} por dia)."
    return f"{linha} Estourado em R$ {R(-resumo['saldo'])}."


def carregar_transacoes(db, desde: date) -> list[dict]:
    # Folga de 1 dia: data gravada em UTC pode ser do dia anterior em Brasília.
    limite = (desde - timedelta(days=1)).isoformat()
    return [d.to_dict() for d in db.collection("finance_transactions").where("date", ">=", limite).stream()]


def _marca(db, hoje: date, chave: str) -> bool:
    """True se esta é a primeira vez (cria a marca); False se já foi avisado."""
    try:
        db.collection("avisos_teto").document(f"{hoje:%Y-%m}_{chave}").create({"em": datetime.now().isoformat()})
        return True
    except AlreadyExists:
        return False


@scheduler_fn.on_schedule(
    schedule="10 * * * *",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
@instrumentada("avisos_teto_hora")
def avisos_teto_hora(event: scheduler_fn.ScheduledEvent = None) -> None:
    from zoneinfo import ZoneInfo

    from hermes_core_logic import _get_allowed_chat_id, _send_telegram_message
    from main import _get_telegram_token, get_db

    db = get_db()
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    hoje = agora.date()
    settings_doc = db.collection("finance_settings").document("config").get()
    settings = settings_doc.to_dict() if settings_doc.exists else {}
    resumo = ga.resumo_do_mes(carregar_transacoes(db, hoje.replace(day=1)), settings, hoje.year, hoje.month)

    textos = [texto for chave, texto in avisos_da_hora(resumo, hoje, agora.hour) if _marca(db, hoje, chave)]
    novos = [m for m in marcos_atingidos(resumo) if _marca(db, hoje, f"marco_{m}")]
    if novos:
        textos.append(texto_marco(novos[0], resumo, hoje))  # o maior; os menores ficam marcados sem mensagem
    chat_id = _get_allowed_chat_id()
    if textos and chat_id:
        _send_telegram_message(_get_telegram_token(db), chat_id, "\n\n".join(textos))


def teclado_pix(doc_id: str) -> list[list[dict]]:
    return [[{"text": "🛒 Gasto", "callback_data": f"{CALLBACK}{doc_id}:g"},
             {"text": "🔁 Transferência", "callback_data": f"{CALLBACK}{doc_id}:t"},
             {"text": "🧾 Conta fixa", "callback_data": f"{CALLBACK}{doc_id}:f"}]]


def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id, _persist_callback_turn, _pending_web_card, _clear_pending_web_card) -> bool:
    """Trata `pixcls:<id>:<g|t|f>`: grava a classe do Pix grande e tira os botões."""
    if not data.startswith(CALLBACK):
        return False
    from telegram_callbacks_custos import _edit_message_text
    from telegram_utils import _answer_callback_query

    doc_id, _, classe = data[len(CALLBACK):].rpartition(":")
    if not doc_id or classe not in CLASSES:
        _answer_callback_query(token, query_id, "Botão inválido.")
        return True
    categoria, rotulo = CLASSES[classe]
    ref = db.collection("finance_transactions").document(doc_id)
    if not ref.get().exists:
        _answer_callback_query(token, query_id, "Esse lançamento não existe mais.")
        return True
    campos = {"classificado_como": rotulo, "classificado_em": datetime.now().isoformat()}
    if categoria:
        campos["category"] = categoria
    ref.update(campos)
    efeito = "Conta no teto." if categoria is None else "Saiu do teto."
    texto = f"{(message or {}).get('text') or ''}\n\n✅ Marcado como {rotulo}. {efeito}".strip()
    _edit_message_text(token, chat_id, (message or {}).get("message_id"), texto, [])
    _answer_callback_query(token, query_id, f"Marcado como {rotulo}.")
    return True
