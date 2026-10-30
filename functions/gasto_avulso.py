"""Gasto avulso do mes e saldo do orcamento, a mesma conta no Telegram e no app.

Modulo puro, espelhado em `src/utils/gastoAvulso.ts` (mesmo padrao de
`bolso_aquisicoes`): a notificacao "Gasto Realizado via Pix" e o "Alerta de
Orcamento" do app mostravam numeros de contas diferentes. Os testes dos dois
lados usam a MESMA fixture; mudou a regra aqui, muda la.

A regra, e o que ela NAO resolve:
- conta so o que esta em `finance_transactions` e nao esta `deleted`;
- o mes e o de Brasilia. Data so com dia ("2026-10-28") vale o dia escrito; data
  com hora e sem fuso e UTC, como `parse_iso_date` do `sync_pix_emails` le;
- o mesmo `google_message_id` ou `pix_id` conta uma vez;
- categoria de movimentacao que nao e consumo (transferencia, investimento,
  poupanca, reserva, conta fixa) fica fora.
NAO separa sozinha um resumo mensal lancado a mao ("Mercado (outubro)") dos Pix
individuais que ele ja inclui: nao ha campo que ligue um ao outro. Isso so a
limpeza dos lancamentos resolve.
"""

import re
import unicodedata
from datetime import datetime, timedelta, timezone

from bolso_aquisicoes import centavos, numero

# ponytail: offset fixo; o Brasil nao tem horario de verao desde 2019. Se voltar, trocar por zoneinfo nos dois lados.
BRT = timezone(timedelta(hours=-3))

CATEGORIAS_FORA_DO_CONSUMO = {"transferencia", "investimento", "poupanca", "reserva", "conta fixa"}

_DATA = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$")


def _normal(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).strip().lower()


def mes_brt(data):
    """(ano, mes 1-12) do lancamento no fuso de Brasilia, ou None se ilegivel."""
    if isinstance(data, datetime):
        dt = data if data.tzinfo else data.replace(tzinfo=timezone.utc)
        local = dt.astimezone(BRT)
        return local.year, local.month
    m = _DATA.match(str(data or "").strip())
    if not m:
        return None
    ano, mes, dia, hora, minuto, seg, fuso = m.groups()
    if hora is None:
        return int(ano), int(mes)
    dt = datetime(int(ano), int(mes), int(dia), int(hora), int(minuto), int(seg or 0), tzinfo=timezone.utc)
    if fuso and fuso != "Z":
        sinal = -1 if fuso[0] == "-" else 1
        hh, mm = int(fuso[1:3]), int(fuso[-2:])
        dt -= sinal * timedelta(hours=hh, minutes=mm)
    local = dt.astimezone(BRT)
    return local.year, local.month


def gasto_avulso_centavos(transacoes, ano: int, mes: int) -> int:
    total, vistos = 0, set()
    for t in transacoes:
        if t.get("status") == "deleted":
            continue
        if _normal(t.get("category")) in CATEGORIAS_FORA_DO_CONSUMO:
            continue
        if mes_brt(t.get("date")) != (ano, mes):
            continue
        chaves = {("g", t.get("google_message_id")), ("p", t.get("pix_id"))} - {("g", None), ("p", None), ("g", ""), ("p", "")}
        if chaves & vistos:
            continue
        vistos |= chaves
        total += centavos(t.get("amount"))
    return total


def orcamento_centavos(settings: dict, ano: int, mes: int):
    """Orcamento do mes (o do mes, senao o geral), ou None quando nao ha."""
    settings = settings or {}
    do_mes = numero((settings.get("monthlyBudgets") or {}).get(f"{ano}-{mes:02d}"))
    valor = do_mes if do_mes > 0 else numero(settings.get("monthlyBudget"))
    return centavos(valor) if valor > 0 else None


def resumo_do_mes(transacoes, settings: dict, ano: int, mes: int) -> dict:
    gasto = gasto_avulso_centavos(transacoes, ano, mes)
    orcamento = orcamento_centavos(settings, ano, mes)
    return {"gasto": gasto, "orcamento": orcamento,
            "saldo": None if orcamento is None else orcamento - gasto}


def mes_atual_brt(agora: datetime | None = None):
    local = (agora or datetime.now(timezone.utc)).astimezone(BRT)
    return local.year, local.month


def _reais(centavos_: int) -> str:
    return f"{centavos_ / 100:.2f}"


def texto_notificacao_pix(valor: float, resumo: dict) -> str:
    """Corpo da notificacao "Gasto Realizado via Pix"; saldo so quando ha orcamento."""
    linhas = [f"Valor: R$ {valor:.2f}", f"Gasto avulso no mês: R$ {_reais(resumo['gasto'])}"]
    if resumo["saldo"] is not None:
        linhas.append(f"Saldo disponível: R$ {_reais(resumo['saldo'])}")
    return "\n".join(linhas)
