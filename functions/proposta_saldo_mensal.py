"""Proposta mensal de saldo disponivel e poupanca (pedido do Andre em 01/11/2026).

O modelo (Andre, 01/11/2026): a poupanca e feita no INICIO do mes, quando
todas as contas fixas ja foram pagas. O que sobra -- renda TOTAL esperada no
mes (inclusive parcela de servico que ainda nao caiu, como a bolsa do PLS MEC
por volta do 7o dia util) menos as contas, o MESMO `saldo_previsto` de
`consultar_financas_v2` -- se divide em duas partes: o saldo disponivel (o
teto variavel do PicPay, ja existente em `gasto_avulso`/`avisos_teto`) e a
poupanca, que e sempre a DIFERENCA entre as duas.

Isso resolve sozinho o caso da renda que cai so no meio do mes: como
`saldo_previsto` usa a renda esperada (nao so a recebida), a parcela futura
ja entra na soma sem tratamento especial -- ela so precisa estar cadastrada
como renda do mes.

O saldo disponivel e PROPOSTO automaticamente pela media dos gastos avulsos
do PicPay (`gasto_avulso.gasto_avulso_centavos`) dos ultimos 3 meses fechados
-- nao do cartao, que mistura parcelamento e assinatura com o gasto variavel
do dia a dia. Se um unico lancamento do mes mais recente for desproporcional
(>= OUTLIER_FRACAO do gasto do mes, com pelo menos 2 lancamentos no mes), o
texto da proposta avisa, mas NUNCA exclui nada por conta propria -- o Andre
e quem decide se ajusta.

Fluxo: `avisos_teto_hora` (telegram_handlers_core.py) chama `verificar_e_propor`
a cada hora; ela so dispara quando todas as contas do mes corrente estao
pagas e a proposta deste mes ainda nao foi enviada (marca atomica em
`proposta_saldo_mensal`, mesma tecnica do `_marca` de avisos_teto). Os botoes
da mensagem sao "Confirmar" (grava direto) e "Ajustar" (arma captura de texto
livre -- a proxima mensagem e o novo valor, tratado por `aplicar_ajuste`).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timezone

import gasto_avulso as ga
from bolso_aquisicoes import centavos

CALLBACK = "saldomes:"
PENDING_AJUSTE = "pending_saldo_mes_ajuste"
COLLECTION_MARCA = "proposta_saldo_mensal"
CATEGORIA_POUPANCA = "Poupança"
# O maior lancamento do mes so e apontado como fora do padrao quando vale pelo
# menos OUTLIER_MULTIPLO vezes a MEDIA DOS OUTROS lancamentos do mes -- nao a
# fracao do total. Com so 2 lancamentos, um deles e sempre >= 50% do total
# (60/40 ja bateria uma fracao de 40%), o que marcaria qualquer mes comum como
# fora do padrao; comparar com a media do resto nao tem esse viés.
OUTLIER_MULTIPLO = 3

MESES_NOME = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
              "agosto", "setembro", "outubro", "novembro", "dezembro")


# --------------------------------------------------------------------------
# Calculo puro (sem Firestore)
# --------------------------------------------------------------------------

def todas_contas_pagas(contas: list[dict]) -> bool:
    """So dispara com pelo menos uma conta no mes, e todas pagas."""
    if not contas:
        return False
    return all(bool(c.get("isPaid")) for c in contas)


def mes_anterior(ano: int, mes: int, voltar: int = 1) -> tuple[int, int]:
    """(ano, mes) `voltar` meses antes de (ano, mes), 1-12."""
    total = (ano * 12 + (mes - 1)) - voltar
    return total // 12, total % 12 + 1


def media_gastos_avulsos_centavos(transacoes: list[dict], ano: int, mes: int, meses: int = 3) -> int | None:
    """Media dos gastos avulsos do PicPay dos `meses` fechados anteriores a (ano, mes)."""
    if meses <= 0:
        return None
    valores = []
    for voltar in range(1, meses + 1):
        a, m = mes_anterior(ano, mes, voltar)
        valores.append(ga.gasto_avulso_centavos(transacoes, a, m))
    return round(sum(valores) / len(valores))


def maior_outlier(transacoes: list[dict], ano: int, mes: int) -> dict | None:
    """O lancamento do mes que, sozinho, distorce a media -- so para avisar, nunca filtra."""
    de = date(ano, mes, 1)
    ate = date(ano, mes, calendar.monthrange(ano, mes)[1])
    candidatos = ga.transacoes_do_teto(transacoes, de, ate)
    if len(candidatos) < 2:
        return None
    valores = [centavos(t.get("amount")) for t in candidatos]
    maior_idx = max(range(len(valores)), key=valores.__getitem__)
    maior_valor = valores[maior_idx]
    resto_total = sum(valores) - maior_valor
    resto_n = len(valores) - 1
    media_resto = resto_total / resto_n if resto_n else 0
    e_outlier = maior_valor > 0 and (media_resto == 0 or maior_valor >= media_resto * OUTLIER_MULTIPLO)
    if not e_outlier:
        return None
    maior = candidatos[maior_idx]
    return {
        "descricao": str(maior.get("description") or maior.get("category") or "um lançamento"),
        "valor_centavos": maior_valor,
    }


def calcular_poupanca_centavos(saldo_previsto_centavos: int, saldo_disponivel_centavos: int) -> int:
    return saldo_previsto_centavos - saldo_disponivel_centavos


def _reais(c: int) -> str:
    return f"{c / 100:.2f}"


def texto_proposta(mes: int, saldo_previsto_centavos: int, saldo_disponivel_centavos: int,
                    outlier: dict | None) -> str:
    poupanca = calcular_poupanca_centavos(saldo_previsto_centavos, saldo_disponivel_centavos)
    linhas = [
        f"📅 Todas as contas de {MESES_NOME[mes - 1]} estão pagas. Sobraram R$ {_reais(saldo_previsto_centavos)}.",
        f"Pela média dos últimos 3 meses de gasto avulso, sugiro R$ {_reais(saldo_disponivel_centavos)} "
        f"de saldo disponível para o PicPay — e R$ {_reais(poupanca)} para a poupança.",
    ]
    if outlier:
        linhas.append(
            f"(um gasto de R$ {_reais(outlier['valor_centavos'])} em \"{outlier['descricao']}\" entrou nessa "
            "média — pode valer ajustar se foi fora do padrão.)"
        )
    linhas.append("Confirma ou ajusta?")
    return "\n\n".join(linhas)


def teclado_proposta(chave: str) -> list[list[dict]]:
    return [[{"text": "✅ Confirmar", "callback_data": f"{CALLBACK}{chave}:ok"},
             {"text": "✏️ Ajustar", "callback_data": f"{CALLBACK}{chave}:ajustar"}]]


# --------------------------------------------------------------------------
# Integracao com Firestore / Telegram
# --------------------------------------------------------------------------

def _carregar_contas_do_mes(db, ano: int, mes: int) -> list[dict]:
    return [d.to_dict() for d in db.collection("fixed_bills")
            .where("year", "==", ano).where("month", "==", mes - 1).stream()]


def _carregar_rendas_do_mes(db, ano: int, mes: int) -> list[dict]:
    return [d.to_dict() for d in db.collection("income_entries")
            .where("year", "==", ano).where("month", "==", mes - 1).stream()
            if (d.to_dict() or {}).get("status") != "deleted"]


def _carregar_transacoes_desde(db, desde_iso: str) -> list[dict]:
    return [d.to_dict() for d in db.collection("finance_transactions").where("date", ">=", desde_iso).stream()]


def saldo_previsto_centavos(db, ano: int, mes: int) -> int:
    """Renda total esperada (recebida ou nao) menos as contas do mes -- mesma conta de consultar_financas_v2."""
    contas = _carregar_contas_do_mes(db, ano, mes)
    rendas = _carregar_rendas_do_mes(db, ano, mes)
    total_contas = sum(centavos(c.get("amount")) for c in contas)
    total_renda = sum(centavos(r.get("amount")) for r in rendas)
    return total_renda - total_contas


def _marcar_proposta(db, chave: str, dados: dict) -> bool:
    """True na primeira vez (cria a marca, com os dados da proposta); False se ja existia."""
    from google.api_core.exceptions import AlreadyExists

    try:
        db.collection(COLLECTION_MARCA).document(chave).create(dados)
        return True
    except AlreadyExists:
        return False


def registrar_decisao(db, ano: int, mes: int, saldo_disponivel_centavos: int,
                       saldo_previsto_centavos_: int) -> dict:
    """Grava o teto do PicPay do mes (finance_settings) e a poupanca (fixed_bills), de uma vez."""
    poupanca_centavos = calcular_poupanca_centavos(saldo_previsto_centavos_, saldo_disponivel_centavos)
    chave_mes = f"{ano}-{mes:02d}"

    db.collection("finance_settings").document("config").update({
        f"monthlyBudgets.{chave_mes}": round(saldo_disponivel_centavos / 100, 2),
    })

    poupanca_ref = db.collection("fixed_bills").document()
    poupanca_ref.set({
        "description": f"Poupança de {MESES_NOME[mes - 1]}",
        "amount": round(poupanca_centavos / 100, 2),
        "category": CATEGORIA_POUPANCA,
        "month": mes - 1,
        "year": ano,
        "isPaid": True,
        "date": datetime.now(timezone.utc).isoformat(),
        "source": "proposta_saldo_mensal",
    })
    return {
        "saldo_disponivel": round(saldo_disponivel_centavos / 100, 2),
        "poupanca": round(poupanca_centavos / 100, 2),
        "poupanca_id": poupanca_ref.id,
    }


def verificar_e_propor(db, token, chat_id, hoje: date) -> None:
    """Chamada a cada hora por `avisos_teto_hora`. So manda a proposta uma vez por mes."""
    if not chat_id:
        return
    ano, mes = hoje.year, hoje.month
    chave = f"{ano}-{mes:02d}"

    contas = _carregar_contas_do_mes(db, ano, mes)
    if not todas_contas_pagas(contas):
        return

    ano_inicio, mes_inicio = mes_anterior(ano, mes, 3)
    desde = f"{ano_inicio:04d}-{mes_inicio:02d}-01"
    transacoes = _carregar_transacoes_desde(db, desde)
    media = media_gastos_avulsos_centavos(transacoes, ano, mes)
    if media is None:
        return
    ano_recente, mes_recente = mes_anterior(ano, mes, 1)
    outlier = maior_outlier(transacoes, ano_recente, mes_recente)
    saldo_previsto = saldo_previsto_centavos(db, ano, mes)

    gravou = _marcar_proposta(db, chave, {
        "em": datetime.now(timezone.utc).isoformat(),
        "ano": ano,
        "mes": mes,
        "saldo_previsto_centavos": saldo_previsto,
        "saldo_disponivel_proposto_centavos": media,
        "decidido": False,
    })
    if not gravou:
        return

    from telegram_utils import _send_telegram_message_with_keyboard

    texto = texto_proposta(mes, saldo_previsto, media, outlier)
    _send_telegram_message_with_keyboard(token, chat_id, texto, teclado_proposta(chave))


def aplicar_ajuste(db, chave: str, texto: str) -> str:
    """Le o valor digitado em resposta a "Ajustar", grava a decisao e devolve a mensagem de resposta."""
    import importar_fatura as _imp

    marca_ref = db.collection(COLLECTION_MARCA).document(chave)
    marca = marca_ref.get()
    if not marca.exists:
        return "Essa proposta não existe mais."
    dados = marca.to_dict() or {}
    if dados.get("decidido"):
        return "Essa proposta já foi decidida."

    try:
        valor = _imp._valor_br(texto.strip())
    except (ValueError, TypeError):
        valor = None
    if valor is None or valor <= 0:
        return "Não entendi o valor. Manda só o número, ex.: 4500."

    resultado = registrar_decisao(db, dados["ano"], dados["mes"], centavos(valor), dados["saldo_previsto_centavos"])
    marca_ref.update({"decidido": True, "decidido_em": datetime.now(timezone.utc).isoformat(), "ajustado": True})
    return (f"✅ Ajustado: R$ {resultado['saldo_disponivel']:.2f} de saldo disponível, "
            f"R$ {resultado['poupanca']:.2f} para a poupança.")


def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id,
           _persist_callback_turn, _pending_web_card, _clear_pending_web_card) -> bool:
    """Trata `saldomes:<chave>:<ok|ajustar>`. Retorna True se tratou."""
    if not data.startswith(CALLBACK):
        return False
    from telegram_callbacks_custos import _edit_message_text
    from telegram_utils import _answer_callback_query, _arm_free_text_capture, _save_session, _send_telegram_message

    resto = data[len(CALLBACK):]
    chave, _, acao = resto.rpartition(":")
    if not chave or acao not in ("ok", "ajustar"):
        _answer_callback_query(token, query_id, "Botão inválido.")
        return True

    marca_ref = db.collection(COLLECTION_MARCA).document(chave)
    marca = marca_ref.get()
    if not marca.exists:
        _answer_callback_query(token, query_id, "Essa proposta não existe mais.")
        return True
    dados = marca.to_dict() or {}
    if dados.get("decidido"):
        _answer_callback_query(token, query_id, "Essa proposta já foi decidida.")
        return True

    if acao == "ajustar":
        _arm_free_text_capture(session, PENDING_AJUSTE, chave)
        _save_session(db, chat_id, session)
        _answer_callback_query(token, query_id, "Me diz o novo valor.")
        pedido = "✏️ Qual o saldo disponível para este mês? (só o número, ex.: 4500)"
        _persist_callback_turn("Botão: ajustar saldo disponível do mês", pedido)
        _send_telegram_message(token, chat_id, pedido)
        return True

    resultado = registrar_decisao(db, dados["ano"], dados["mes"],
                                   dados["saldo_disponivel_proposto_centavos"], dados["saldo_previsto_centavos"])
    marca_ref.update({"decidido": True, "decidido_em": datetime.now(timezone.utc).isoformat()})
    texto_final = (f"✅ Confirmado: R$ {resultado['saldo_disponivel']:.2f} de saldo disponível, "
                   f"R$ {resultado['poupanca']:.2f} para a poupança.")
    _edit_message_text(token, chat_id, (message or {}).get("message_id"), texto_final, [])
    _answer_callback_query(token, query_id, "Registrado!")
    _persist_callback_turn("Botão: confirmar saldo disponível do mês", texto_final)
    return True
