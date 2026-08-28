"""Escrita no modulo Saude — o outro lado da porta de `consultar_saude`.

Ate 28/08/2026 dava para ler peso, dor e caminhada pelo MCP e nao dava para
gravar nada: todo lancamento era digitado a mao na web. O caso que motivou isto
e concreto — uma tarde fora, no celular, com os dois check-ins do dia por fazer.
Falar "registra 93,4" e uma coisa; abrir o sistema e digitar e outra.

## Escreve onde a interface ja escreve

Nao ha coleção nova. Peso vai para `health_weights`, cintura para
`health_waist`, e o resto para `health_exercise_logs/{YYYY-MM-DD}` — as mesmas
que a web e o check-in do Telegram usam. Uma tool de escrita que inventasse
campos proprios criaria uma segunda fonte para o mesmo numero, que e pior que
nao ter tool nenhuma.

## Idempotente por dia e por campo

Registrar peso duas vezes no mesmo dia **atualiza**, nao duplica. Isso importa
porque retorno ambiguo faz quem chama repetir a chamada — foi assim que um plano
de acao virou lixo em 28/08, com tres tentativas seguidas.

`health_weights` e `health_waist` usam id automatico e podem ter mais de um doc
por data; aqui o doc do dia e procurado antes de escrever, e so se cria um novo
quando nao existe.

## Recusa em vez de gravar

Peso de 937 kg, dor 15, data no ano que vem: erro nomeando o campo e o valor.
Um numero errado no historico contamina a media de sete dias e a projecao da
meta, e ninguem percebe — o custo de recusar e uma nova chamada, o de aceitar e
um dado falso que ninguem procura.

## O que NAO existe no modelo

`passos`, `ciatica`, `crise` e horas de sono foram pedidos e nao existem em
lugar nenhum das colecoes de saude. Grava-los criaria campos que nenhuma tela le
— dado morto com aparencia de registro. O que existe e proximo:

    sono_qualidade (1-5)   `sleepQuality.quality`, a escala que o check-in usa
    acordou_com_dor        `sleepQuality.wokeInPain`
    dor_pos_caminhada      `pain.afterWalk`

## Rotina cumprida e derivada, nao gravada

`obter_estado_atual` deduz `pesagem`, `cintura`, `checkin_manha` e
`checkin_noite` da existencia do dado (ver `morning_summary._rotina_verificavel`).
Entao nao ha campo `rotina_feita` a preencher: registrar o peso E marcar a
pesagem. A resposta diz quais rotinas o registro fechou, para o laco ficar
visivel sem criar uma segunda verdade.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

COL_PESOS = "health_weights"
COL_CINTURA = "health_waist"
COL_LOGS = "health_exercise_logs"

# Faixas plausiveis. Largas de proposito: barram o erro de digitacao, nao a
# realidade de ninguem.
_FAIXAS = {
    "peso": (30.0, 300.0, "kg"),
    "cintura": (40.0, 200.0, "cm"),
    "calorias": (0, 20000, "kcal"),
    "dor_manha": (0, 10, ""),
    "dor_noite": (0, 10, ""),
    "dor_pos_caminhada": (0, 10, ""),
    "sono_qualidade": (1, 5, ""),
}

_INTEIROS = {"calorias", "dor_manha", "dor_noite", "dor_pos_caminhada", "sono_qualidade"}

# Pedidos que nao tem onde morar. Nomear a alternativa e o que evita a proxima
# tentativa as cegas.
_NAO_EXISTEM = {
    "passos": "o modulo nao registra passos; o que ha e caminhada em km (walkBlocks, pela web)",
    "sono_horas": "nao ha horas de sono; use `sono_qualidade` (1 a 5), que e a escala do check-in",
    "ciatica": "nao ha campo booleano; o que existe e `radicular.location`, registrado no check-in",
    "crise": "nao ha campo de crise; o que existe e `triggers.types`, registrado no check-in",
}


class ValorRecusado(ValueError):
    """Valor implausivel. Recusar e mais barato que descobrir depois."""


def _numero(campo: str, valor):
    minimo, maximo, unidade = _FAIXAS[campo]
    try:
        n = int(valor) if campo in _INTEIROS else float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise ValorRecusado(f"`{campo}` precisa ser um numero; veio {valor!r}.") from None
    if not (minimo <= n <= maximo):
        raise ValorRecusado(
            f"`{campo}` = {n}{(' ' + unidade) if unidade else ''} esta fora da faixa "
            f"plausivel ({minimo}-{maximo}). Nada foi gravado — confira o valor.")
    return n


def _data_valida(bruto) -> str:
    hoje = date.today().isoformat()
    texto = str(bruto or "").strip() or hoje
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        raise ValorRecusado(f"`data` precisa ser YYYY-MM-DD; veio {bruto!r}.")
    if texto > hoje:
        raise ValorRecusado(
            f"`data` = {texto} esta no futuro. Registro de saude e do que ja aconteceu.")
    return texto


def _gravar_por_data(db, colecao: str, dia: str, campo: str, valor) -> None:
    """Atualiza o doc do dia, ou cria um se nao houver. Nunca duplica."""
    existentes = list(db.collection(colecao).where("date", "==", dia).limit(1).stream())
    if existentes:
        existentes[0].reference.set({campo: valor}, merge=True)
    else:
        db.collection(colecao).document().set({"date": dia, campo: valor})


def registrar(ctx, args: dict) -> dict:
    """Registra o que o USUARIO declarou sobre a saude dele, num dia."""
    recusados = [c for c in _NAO_EXISTEM if args.get(c) is not None]
    if recusados:
        return {"erro": "Campo(s) sem lugar no modulo de saude: "
                        + "; ".join(f"`{c}` — {_NAO_EXISTEM[c]}" for c in recusados)
                        + ". Nada foi gravado.",
                "aplicado": False}

    try:
        dia = _data_valida(args.get("data"))
    except ValorRecusado as exc:
        return {"erro": str(exc), "aplicado": False}

    alterados: list[str] = []
    log_updates: dict = {}
    dor: dict = {}
    sono: dict = {}

    try:
        if args.get("peso") is not None:
            _gravar_por_data(ctx.db, COL_PESOS, dia, "weight", _numero("peso", args["peso"]))
            alterados.append("peso")
        if args.get("cintura") is not None:
            _gravar_por_data(ctx.db, COL_CINTURA, dia, "cm", _numero("cintura", args["cintura"]))
            alterados.append("cintura")

        if args.get("calorias") is not None:
            log_updates["calories"] = _numero("calorias", args["calorias"])
            alterados.append("calorias")
        for campo, chave in (("dor_manha", "morning"), ("dor_noite", "evening"),
                             ("dor_pos_caminhada", "afterWalk")):
            if args.get(campo) is not None:
                dor[chave] = _numero(campo, args[campo])
                alterados.append(campo)
        if args.get("sono_qualidade") is not None:
            sono["quality"] = _numero("sono_qualidade", args["sono_qualidade"])
            alterados.append("sono_qualidade")
        if args.get("acordou_com_dor") is not None:
            sono["wokeInPain"] = bool(args["acordou_com_dor"])
            alterados.append("acordou_com_dor")
    except ValorRecusado as exc:
        # O que ja foi gravado antes da recusa fica; o retorno diz o que passou,
        # para nao restar duvida sobre o estado.
        return {"erro": str(exc), "aplicado": bool(alterados),
                "campos_alterados": alterados, "data": dia}

    if not alterados:
        return {"erro": ("Nenhum valor informado. Passe ao menos um: peso, cintura, "
                         "calorias, dor_manha, dor_noite, dor_pos_caminhada, "
                         "sono_qualidade ou acordou_com_dor."),
                "aplicado": False}

    if dor or sono or log_updates:
        ref = ctx.db.collection(COL_LOGS).document(dia)
        atual = ref.get()
        atual_d = (atual.to_dict() or {}) if atual.exists else {}
        agora = datetime.now(timezone.utc).isoformat()
        if dor:
            log_updates["pain"] = {**(atual_d.get("pain") or {}), **dor,
                                   "mcp_checked_at": agora}
        if sono:
            log_updates["sleepQuality"] = {**(atual_d.get("sleepQuality") or {}), **sono}
        # `entrySource` diz de onde veio o registro do dia; a web usa isso.
        log_updates.setdefault("entrySource", atual_d.get("entrySource") or "mcp")
        ref.set(log_updates, merge=True)

    # As rotinas nao sao gravadas: `morning_summary._rotina_verificavel` as deduz
    # da existencia do dado. Dizer quais fecharam torna o laco visivel sem criar
    # um segundo lugar onde a mesma verdade poderia divergir.
    rotinas = []
    if "peso" in alterados:
        rotinas.append("pesagem")
    if "cintura" in alterados:
        rotinas.append("cintura")
    if "dor_manha" in alterados:
        rotinas.append("checkin_manha")
    if "dor_noite" in alterados:
        rotinas.append("checkin_noite")

    return {
        "status": "completed",
        "data": dia,
        "campos_alterados": alterados,
        "rotinas_concluidas": rotinas,
        "observacao": ("Registrado onde a interface web lê — o valor aparece em "
                       "consultar_saude desta data. Rotina cumprida é deduzida do "
                       "dado, não gravada à parte."),
    }
