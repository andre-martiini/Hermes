"""Gasto do teto do PicPay no mes e quanto resta, a mesma conta no Telegram e no app.

Modulo puro, espelhado em `src/utils/gastoAvulso.ts` (mesmo padrao de
`bolso_aquisicoes`): a notificacao "Gasto Realizado via Pix" e o "Alerta de
Orcamento" do app mostravam numeros de contas diferentes. Os testes dos dois
lados usam a MESMA fixture; mudou a regra aqui, muda la.

O modelo (André, 30/10/2026): o salario cai na Caixa, vai para a XP, la saem as
contas do inicio do mes, e o resto vai para o PicPay. O orcamento do mes
(`monthlyBudgets`/`monthlyBudget`) e o TETO de gasto variavel do PicPay; o que
sobra vai para os cofrinhos. Entao o saldo e o teto menos o gasto feito PELA
CONTA PICPAY.

A regra, e o que ela NAO resolve:
- conta so o que esta em `finance_transactions`, nao esta `deleted` e tem
  `conta == "picpay"`. Lancamento sem `conta` (manual antigo, resumo misto
  XP/PicPay) NAO entra: sem sinal de conta, nao se adivinha;
- o mes e o de Brasilia. Data so com dia ("2026-10-28") vale o dia escrito, e
  meia-noite UTC exata tambem: e o que o campo de data do app grava
  (`new Date("2026-11-01").toISOString()`). Data com hora e sem fuso e UTC, como
  `parse_iso_date` do `sync_pix_emails` le;
- o mesmo `google_message_id` ou `pix_id` conta uma vez;
- categoria de movimentacao que nao e consumo (transferencia, investimento,
  aporte, poupanca, reserva, conta fixa, no singular ou plural) fica fora;
- orcamento do mes gravado (mesmo 0) vence o geral; 0 = sem orcamento, sem saldo.
"""

import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

from bolso_aquisicoes import centavos, numero

# ponytail: offset fixo; o Brasil nao tem horario de verao desde 2019. Se voltar, trocar por zoneinfo nos dois lados.
BRT = timezone(timedelta(hours=-3))

CONTA_DO_TETO = "picpay"
CONTAS = ("picpay", "xp", "caixa", "mista")

# Prefixos, para pegar singular e plural ("Investimentos", "Contas fixas").
FORA_DO_CONSUMO = ("transferenc", "investiment", "aporte", "poupanc", "reserva", "conta fixa", "contas fixa")

# `[0-9]` e espaco explicito, e nao `\d`/`strip()`: o `\d` do Python casa digito
# Unicode e o `strip()` remove outro conjunto que o `trim()` do JS (ver bolso_aquisicoes).
_ESPACO = " \t\n\r\f\v"
_DATA = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})"
    r"(?:[T ]([0-9]{2}):([0-9]{2})(?::([0-9]{2})(\.[0-9]+)?)?(Z|[+-][0-9]{2}:?[0-9]{2})?)?$")


def _normal(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).strip(_ESPACO).lower()


def data_brt(data):
    """Dia do lancamento no fuso de Brasilia (`date`), ou None se ilegivel."""
    if isinstance(data, datetime):
        dt = data if data.tzinfo else data.replace(tzinfo=timezone.utc)
        return dt.astimezone(BRT).date()
    m = _DATA.match(str(data or "").strip(_ESPACO))
    if not m:
        return None
    ano, mes, dia, hora, minuto, seg, fracao, fuso = m.groups()
    # ponytail: um Pix real as 21:00:00.000 de Brasilia tambem cairia aqui; com segundos e ms zerados, improvavel.
    meia_noite_utc = fuso == "Z" and (hora, minuto, seg or "00") == ("00", "00", "00") and not (fracao or ".0").strip(".0")
    try:
        if hora is None or meia_noite_utc:
            return date(int(ano), int(mes), int(dia))
        dt = datetime(int(ano), int(mes), int(dia), int(hora), int(minuto), int(seg or 0), tzinfo=timezone.utc)
    except ValueError:
        return None
    if fuso and fuso != "Z":
        sinal = -1 if fuso[0] == "-" else 1
        hh, mm = int(fuso[1:3]), int(fuso[-2:])
        dt -= sinal * timedelta(hours=hh, minutes=mm)
    return dt.astimezone(BRT).date()


def mes_brt(data):
    """(ano, mes 1-12) do lancamento no fuso de Brasilia, ou None se ilegivel."""
    dia = data_brt(data)
    return (dia.year, dia.month) if dia else None


def gasto_avulso_centavos(transacoes, ano: int, mes: int) -> int:
    return gasto_do_teto_centavos(transacoes, date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1]))


def gasto_do_teto_centavos(transacoes, de: date, ate: date) -> int:
    """Gasto que conta no teto entre `de` e `ate` (inclusive, dias de Brasilia)."""
    total, vistos = 0, set()
    for t in transacoes:
        if t.get("status") == "deleted" or _normal(t.get("conta")) != CONTA_DO_TETO:
            continue
        if _normal(t.get("category")).startswith(FORA_DO_CONSUMO):
            continue
        dia = data_brt(t.get("date"))
        if not dia or not de <= dia <= ate:
            continue
        chaves = {f"{k}:{v}" for k, v in (("g", t.get("google_message_id")), ("p", t.get("pix_id"))) if v not in (None, "")}
        if chaves & vistos:
            continue
        vistos |= chaves
        total += centavos(t.get("amount"))
    return total


def orcamento_centavos(settings: dict, ano: int, mes: int):
    """Orcamento do mes (o do mes, senao o geral), ou None quando nao ha."""
    settings = settings or {}
    por_mes = settings.get("monthlyBudgets") or {}
    chave = f"{ano}-{mes:02d}"
    valor = numero(por_mes[chave] if por_mes.get(chave) is not None else settings.get("monthlyBudget"))
    return centavos(valor) if valor > 0 else None


def resumo_do_mes(transacoes, settings: dict, ano: int, mes: int) -> dict:
    gasto = gasto_avulso_centavos(transacoes, ano, mes)
    orcamento = orcamento_centavos(settings, ano, mes)
    return {"gasto": gasto, "orcamento": orcamento,
            "saldo": None if orcamento is None else orcamento - gasto}


def hoje_brt(agora: datetime | None = None):
    """(ano, mes 1-12, dia) de agora em Brasilia."""
    local = (agora or datetime.now(timezone.utc)).astimezone(BRT)
    return local.year, local.month, local.day


def _reais(centavos_: int) -> str:
    return f"{centavos_ / 100:.2f}"


def texto_notificacao_pix(valor: float, resumo: dict, hoje: tuple) -> str:
    """Corpo da notificacao "Gasto Realizado via Pix". `hoje` = (ano, mes, dia) em BRT.

    O que resta no teto e dividido pelos dias que faltam, contando hoje.
    """
    linhas = [f"Valor: R$ {valor:.2f}", f"Gasto no PicPay no mês: R$ {_reais(resumo['gasto'])}"]
    saldo = resumo["saldo"]
    if saldo is not None and saldo > 0:
        ano, mes, dia = hoje
        dias = calendar.monthrange(ano, mes)[1] - dia + 1
        linhas.append(f"Restam R$ {_reais(saldo)} no teto (R$ {_reais(saldo // dias)} por dia até o fim do mês)")
    elif saldo is not None:
        linhas.append(f"Teto do mês estourado em R$ {_reais(-saldo)}")
    return "\n".join(linhas)
