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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_TZ_BR = ZoneInfo("America/Sao_Paulo")

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
    "bem_estar": (0, 10, ""),
    "caminhada_km": (0.1, 50.0, "km"),
    "caminhada_min": (1, 600, "min"),
}

_INTEIROS = {"calorias", "dor_manha", "dor_noite", "dor_pos_caminhada", "sono_qualidade",
             "bem_estar", "caminhada_min"}

# Opcoes do check-in do Telegram, mesmos valores gravados (copia de
# telegram_utils._HEALTH_*, que e pesado de importar aqui; teste garante que
# nao divergem). "nenhum(a)" grava lista vazia, como o Telegram.
_OPCOES_RADICULAR = ["nenhum", "gluteo", "quadril", "coxa", "joelho", "panturrilha", "tornozelo", "pe"]
_OPCOES_TERAPIA = ["pilates", "fisioterapia", "rpg", "acupuntura", "nenhuma"]
_OPCOES_GATILHO = ["espirro_crise_alergica", "viagem_longa_sentado", "dia_muito_sentado",
                   "torcao_no_sono", "carga_assimetrica", "estresse", "outro", "nenhum"]
_OPCOES_ALIMENTACAO = ["sim", "parcial", "nao"]
_OPCOES_MEDICACAO = ["igual_ontem", "nada"]
_MEDS_NADA = {"pregabalina": False, "dipirona": 0, "adorlan": 0, "fexofenadina": False}

# Pedidos que nao tem onde morar. Nomear a alternativa e o que evita a proxima
# tentativa as cegas.
_NAO_EXISTEM = {
    "passos": "o modulo nao registra passos; use `caminhada_km` (e `caminhada_min`)",
    "sono_horas": "nao ha horas de sono; use `sono_qualidade` (1 a 5), que e a escala do check-in",
    "ciatica": "nao ha campo booleano; use `radicular_local` (ate onde desce o sintoma)",
    "crise": "nao ha campo de crise; use `gatilhos` (triggers.types) e `dor_*`",
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


def _opcao(campo: str, valor, opcoes: list) -> str:
    texto = str(valor or "").strip().lower()
    if texto not in opcoes:
        raise ValorRecusado(f"`{campo}` = {valor!r} nao e opcao valida. Use: {', '.join(opcoes)}.")
    return texto


def _lista_opcoes(campo: str, valor, opcoes: list, vazio: str) -> list:
    """Aceita um valor ou lista; `vazio` ("nenhum"/"nenhuma") vira [] como no Telegram."""
    itens = [_opcao(campo, v, opcoes) for v in (valor if isinstance(valor, list) else [valor])]
    return list(dict.fromkeys(i for i in itens if i != vazio))


def hoje_brasilia() -> str:
    """O servidor roda em UTC: depois das 21h de Brasilia `date.today()` ja e amanha."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()


def _data_valida(bruto) -> str:
    hoje = hoje_brasilia()
    texto = str(bruto or "").strip() or hoje
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        raise ValorRecusado(f"`data` precisa ser YYYY-MM-DD; veio {bruto!r}.")
    if texto > hoje:
        raise ValorRecusado(
            f"`data` = {texto} esta no futuro. Registro de saude e do que ja aconteceu.")
    return texto


def _gravar_por_data(db, colecao: str, dia: str, campo: str, valor) -> str:
    """Atualiza o doc do dia, ou cria um se nao houver. Nunca duplica. Devolve o caminho gravado."""
    existentes = list(db.collection(colecao).where("date", "==", dia).limit(1).stream())
    if existentes:
        ref = existentes[0].reference
        ref.set({campo: valor}, merge=True)
    else:
        ref = db.collection(colecao).document()
        ref.set({"date": dia, campo: valor})
    return f"{colecao}/{ref.id}"


def gravar_peso_verificado(db, peso, data=None):
    """Unica escrita de peso (MCP, Telegram por texto, audio e Gemini): valida,
    grava e rele o mesmo documento. Devolve um `verificacao.ResultadoOperacao`."""
    from verificacao import falhou, verificar_escrita

    try:
        dia = _data_valida(data)
    except ValorRecusado as exc:
        return falhou("registrar_peso", COL_PESOS, str(exc))
    try:
        valor = float(str(peso).replace(",", "."))
    except (TypeError, ValueError):
        return falhou("registrar_peso", COL_PESOS,
                      f"o peso precisa ser um número; veio {peso!r}. Nada foi gravado.")
    minimo, maximo, _ = _FAIXAS["peso"]
    if not (minimo <= valor <= maximo):
        kg = f"{valor:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        return falhou("registrar_peso", COL_PESOS,
                      f"o peso de {kg} kg está fora da faixa plausível ({minimo:.0f} a {maximo:.0f} kg). "
                      "Nada foi gravado — confira o valor.")
    esperado = {"date": dia, "weight": valor}
    try:
        caminho = _gravar_por_data(db, COL_PESOS, dia, "weight", valor)
    except Exception as exc:
        return falhou("registrar_peso", COL_PESOS, f"falha ao gravar ({exc}). Nada foi gravado.", esperado)
    return verificar_escrita(db, caminho, esperado, operacao="registrar_peso")


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
    sub: dict = {}  # radicular/strength/nutrition/triggers: mesclados no dict existente
    medicacao = None
    caminhada = None

    if args.get("peso") is not None:
        res_peso = gravar_peso_verificado(ctx.db, args["peso"], dia)
        if not res_peso.ok:
            return {"erro": res_peso.motivo, "aplicado": False, "campos_alterados": [], "data": dia}
        alterados.append("peso")

    try:
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
        # Campos do check-in do Telegram, nos mesmos lugares e formatos.
        if args.get("bem_estar") is not None:
            log_updates["wellbeing"] = _numero("bem_estar", args["bem_estar"])
            alterados.append("bem_estar")
        if args.get("radicular_local") is not None:
            sub["radicular"] = {"location": _opcao("radicular_local", args["radicular_local"], _OPCOES_RADICULAR)}
            alterados.append("radicular_local")
        if args.get("treino_forca") is not None:
            sub["strength"] = {"done": bool(args["treino_forca"])}
            alterados.append("treino_forca")
        if args.get("terapia") is not None:
            log_updates["therapy"] = _lista_opcoes("terapia", args["terapia"], _OPCOES_TERAPIA, "nenhuma")
            alterados.append("terapia")
        if args.get("alimentacao") is not None:
            sub.setdefault("nutrition", {})["plan"] = _opcao(
                "alimentacao", args["alimentacao"], _OPCOES_ALIMENTACAO)
            alterados.append("alimentacao")
        if args.get("proteina") is not None:
            sub.setdefault("nutrition", {})["proteinTarget"] = bool(args["proteina"])
            alterados.append("proteina")
        if args.get("medicacao") is not None:
            medicacao = _opcao("medicacao", args["medicacao"], _OPCOES_MEDICACAO)
            alterados.append("medicacao")
        if args.get("gatilhos") is not None:
            sub["triggers"] = {"types": _lista_opcoes("gatilhos", args["gatilhos"], _OPCOES_GATILHO, "nenhum")}
            alterados.append("gatilhos")
        if args.get("caminhada_km") is not None or args.get("caminhada_min") is not None:
            if args.get("caminhada_km") is None:
                raise ValorRecusado("`caminhada_min` sem `caminhada_km`: o painel soma a caminhada "
                                    "em km. Informe os km (os minutos sao opcionais).")
            caminhada = {"distance": _numero("caminhada_km", args["caminhada_km"])}
            if args.get("caminhada_min") is not None:
                caminhada["minutes"] = _numero("caminhada_min", args["caminhada_min"])
            alterados.append("caminhada")
    except ValorRecusado as exc:
        # O que ja foi gravado antes da recusa fica; o retorno diz o que passou,
        # para nao restar duvida sobre o estado.
        return {"erro": str(exc), "aplicado": bool(alterados),
                "campos_alterados": alterados, "data": dia}

    if not alterados:
        return {"erro": ("Nenhum valor informado. Passe ao menos um: peso, cintura, "
                         "calorias, dor_manha, dor_noite, dor_pos_caminhada, "
                         "sono_qualidade, acordou_com_dor, bem_estar, radicular_local, "
                         "treino_forca, terapia, alimentacao, proteina, medicacao, "
                         "gatilhos ou caminhada_km."),
                "aplicado": False}

    if dor or sono or log_updates or sub or medicacao or caminhada:
        ref = ctx.db.collection(COL_LOGS).document(dia)
        atual = ref.get()
        atual_d = (atual.to_dict() or {}) if atual.exists else {}
        for chave, valores in sub.items():
            log_updates[chave] = {**(atual_d.get(chave) or {}), **valores}
        if medicacao == "igual_ontem":
            ontem = (datetime.strptime(dia, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
            doc_ontem = ctx.db.collection(COL_LOGS).document(ontem).get()
            meds_ontem = (doc_ontem.to_dict() or {}).get("meds") if doc_ontem.exists else None
            log_updates["meds"] = meds_ontem or dict(_MEDS_NADA)
        elif medicacao == "nada":
            log_updates["meds"] = dict(_MEDS_NADA)
        if caminhada:
            # Um bloco MCP por dia, id fixo: repetir a chamada substitui, nao duplica.
            bloco_id = f"walk_mcp_{dia}"
            hora = datetime.now(timezone.utc).astimezone(_TZ_BR).strftime("%H:%M")
            blocos = [b for b in (atual_d.get("walkBlocks") or [])
                      if isinstance(b, dict) and b.get("id") != bloco_id]
            blocos.append({"id": bloco_id, "time": hora, **caminhada, "source": "mcp"})
            log_updates["walkBlocks"] = blocos
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
