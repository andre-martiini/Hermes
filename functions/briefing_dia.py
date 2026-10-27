"""`briefing_dia/{YYYY-MM-DD}`: o que o agente escreveu no briefing das 05:00.

Hoje o briefing sai so como texto no Telegram. O Painel do dia unificado
(DashboardView) precisa dos mesmos itens estruturados para mostrar Decidir,
Foco, "O agente prepara hoje", Preparo, fora da agenda e Avisos do agente — e
para fazer cada item sumir quando a origem dele e resolvida.

## O que e gravado e o que NAO e

O documento e uma foto das 05:00, atualizavel durante o dia. So entra nele o
que a IA escreve. O que e vivo (acoes, etapas, agenda, filas) continua vindo
das fontes vivas; nenhum numero que da para calcular e gravado (contagem de
etapas do agente, "N de M", conflito de agenda, "em N dias").

Todo item aponta para a origem (`acao_id`, `origem` + `ref`). A tela confere a
origem na hora de renderizar e esconde o item cuja origem ja foi resolvida,
mesmo que o briefing ainda o liste.

## Regras de escrita (`registrar`)

- `decidir` e `eu_faco` fazem MERGE por `id` (em `eu_faco`, `id` ou `acao_id`):
  item novo entra, item existente tem os campos que vierem sobrepostos, item
  que nao veio fica como estava. Nada e apagado por omissao.
- `decidir[].status` e `resolvido_em` NUNCA sao escritos por `registrar`. Quem
  resolve e `resolver_item`, ou a tela (botao Feito). Sem isso, o agente que
  atualiza o briefing as 14h desfaria o "Feito" que o Andre marcou as 9h.
- `hoje`, `preparo`, `fora_da_agenda` e `avisos` sao listas-foto sem id: quando
  vem a lista, ela substitui a anterior; quando nao vem, fica a anterior.
- Tudo e validado antes de gravar. Qualquer erro recusa a chamada inteira, com
  a lista dos problemas, para nao gravar meio briefing.
- Leitura, merge e escrita correm numa transacao, para nao disputar com o
  botao Feito da tela.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

COLECAO = "briefing_dia"

ORIGENS = ("fila_atencao", "whatsapp", "etapa", "acao")
STATUS_DECIDIR = ("pendente", "feito", "dispensado")
STATUS_RESOLVER = ("feito", "dispensado", "pendente")
STATUS_EU_FACO = ("proposto", "aprovado", "pronto", "recusado")
TIPOS_AVISO = ("nao_li", "conversa", "dado_suspeito")

# Um briefing e curto por desenho (cabe numa tela de celular). Os tetos
# protegem o documento e a tela contra uma lista descontrolada, nao
# restringem o uso normal.
MAX_ITENS = 30
MAX_TEXTO = 400
MAX_CURTO = 120
MAX_ID = 64
MAX_REF = 200

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

_SECOES_LISTA = ("hoje", "decidir", "eu_faco", "preparo", "fora_da_agenda", "avisos")
SECOES = _SECOES_LISTA + ("menores",)


def hoje_sp() -> str:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")


def data_valida(valor) -> str | None:
    """`YYYY-MM-DD` de um dia que existe, ou `None`."""
    texto = str(valor or "").strip()
    if not _RE_DATA.match(texto):
        return None
    try:
        date.fromisoformat(texto)
    except ValueError:
        return None
    return texto


# ---------------------------------------------------------------------------
# Validacao (pura)
# ---------------------------------------------------------------------------

class _Erros(list):
    def add(self, secao: str, indice: int | None, mensagem: str) -> None:
        onde = secao if indice is None else f"{secao}[{indice}]"
        self.append(f"{onde}: {mensagem}")


def _texto(item: dict, campo: str, erros: _Erros, secao: str, i: int, *,
           obrigatorio: bool = False, limite: int = MAX_TEXTO) -> str | None:
    bruto = item.get(campo)
    if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
        if obrigatorio:
            erros.add(secao, i, f"`{campo}` e obrigatorio.")
        return None
    if not isinstance(bruto, str):
        erros.add(secao, i, f"`{campo}` precisa ser texto.")
        return None
    valor = bruto.strip()
    if len(valor) > limite:
        erros.add(secao, i, f"`{campo}` tem {len(valor)} caracteres; o maximo e {limite}.")
        return None
    return valor


def _lista(secao: str, valor, erros: _Erros) -> list[dict]:
    if not isinstance(valor, list):
        erros.add(secao, None, "precisa ser uma LISTA de itens.")
        return []
    if len(valor) > MAX_ITENS:
        erros.add(secao, None, f"tem {len(valor)} itens; o maximo e {MAX_ITENS}.")
        return []
    saida = []
    for i, item in enumerate(valor):
        if not isinstance(item, dict):
            erros.add(secao, i, "cada item precisa ser um objeto.")
            continue
        saida.append((i, item))
    return saida


def _id(item: dict, erros: _Erros, secao: str, i: int, *, campo: str = "id",
        obrigatorio: bool = True) -> str | None:
    valor = _texto(item, campo, erros, secao, i, obrigatorio=obrigatorio, limite=MAX_ID)
    if valor and "/" in valor:
        erros.add(secao, i, f"`{campo}` nao pode ter '/'.")
        return None
    return valor


def _validar_hoje(valor, erros: _Erros) -> list[dict]:
    saida = []
    for i, item in _lista("hoje", valor, erros):
        acao_id = _id(item, erros, "hoje", i, campo="acao_id")
        motivo = _texto(item, "motivo", erros, "hoje", i, limite=MAX_CURTO)
        if acao_id:
            saida.append({"acao_id": acao_id, **({"motivo": motivo} if motivo else {})})
    return saida


def _validar_decidir(valor, erros: _Erros) -> list[dict]:
    saida, vistos = [], set()
    for i, item in _lista("decidir", valor, erros):
        item_id = _id(item, erros, "decidir", i)
        quem = _texto(item, "quem", erros, "decidir", i, obrigatorio=True, limite=MAX_CURTO)
        texto = _texto(item, "texto", erros, "decidir", i, obrigatorio=True)
        recomendacao = _texto(item, "recomendacao", erros, "decidir", i)
        tag = _texto(item, "tag", erros, "decidir", i, limite=30)
        origem = _texto(item, "origem", erros, "decidir", i, obrigatorio=True, limite=MAX_CURTO)
        ref = _texto(item, "ref", erros, "decidir", i, obrigatorio=True, limite=MAX_REF)
        acao_id = _id(item, erros, "decidir", i, campo="acao_id", obrigatorio=False)
        if origem and origem not in ORIGENS:
            erros.add("decidir", i, f"`origem` {origem!r} invalida; use uma de: {', '.join(ORIGENS)}.")
            origem = None
        # Etapa so se localiza dentro de uma acao; sem `acao_id` a tela nao
        # consegue conferir se a etapa ja foi feita.
        if origem == "etapa" and not acao_id:
            erros.add("decidir", i, "com origem 'etapa', `acao_id` e obrigatorio (`ref` e o id da etapa).")
        if origem == "acao" and ref and not acao_id:
            acao_id = ref
        ordem = item.get("ordem")
        if ordem is not None and (isinstance(ordem, bool) or not isinstance(ordem, int) or ordem < 0):
            erros.add("decidir", i, "`ordem` precisa ser um inteiro >= 0.")
            ordem = None
        if item_id and item_id in vistos:
            erros.add("decidir", i, f"`id` {item_id!r} repetido na mesma chamada.")
        if item_id:
            vistos.add(item_id)
        if item_id and quem and texto and origem and ref:
            novo = {"id": item_id, "quem": quem, "texto": texto, "origem": origem, "ref": ref}
            for campo, v in (("recomendacao", recomendacao), ("tag", tag), ("acao_id", acao_id)):
                if v:
                    novo[campo] = v
            if ordem is not None:
                novo["ordem"] = ordem
            saida.append(novo)
    return saida


def _validar_eu_faco(valor, erros: _Erros) -> list[dict]:
    saida, vistos = [], set()
    for i, item in _lista("eu_faco", valor, erros):
        acao_id = _id(item, erros, "eu_faco", i, campo="acao_id")
        item_id = _id(item, erros, "eu_faco", i, obrigatorio=False) or acao_id
        texto = _texto(item, "texto", erros, "eu_faco", i, obrigatorio=True)
        status = _texto(item, "status", erros, "eu_faco", i, limite=MAX_CURTO)
        if status and status not in STATUS_EU_FACO:
            erros.add("eu_faco", i, f"`status` {status!r} invalido; use um de: {', '.join(STATUS_EU_FACO)}.")
            status = None
        if item_id and item_id in vistos:
            erros.add("eu_faco", i, f"`id` {item_id!r} repetido na mesma chamada.")
        if item_id:
            vistos.add(item_id)
        if acao_id and item_id and texto:
            novo = {"id": item_id, "acao_id": acao_id, "texto": texto}
            if status:
                novo["status"] = status
            saida.append(novo)
    return saida


def _validar_preparo(valor, erros: _Erros) -> list[dict]:
    saida = []
    for i, item in _lista("preparo", valor, erros):
        dia = item.get("dia")
        if data_valida(dia) is None:
            erros.add("preparo", i, "`dia` precisa ser uma data YYYY-MM-DD valida "
                                    "(o 'em N dias' e calculado na tela, nunca gravado).")
        texto = _texto(item, "texto", erros, "preparo", i, obrigatorio=True)
        if data_valida(dia) and texto:
            saida.append({"dia": str(dia).strip(), "texto": texto})
    return saida


def _validar_fora_da_agenda(valor, erros: _Erros) -> list[dict]:
    saida = []
    for i, item in _lista("fora_da_agenda", valor, erros):
        titulo = _texto(item, "titulo", erros, "fora_da_agenda", i, obrigatorio=True, limite=MAX_CURTO)
        motivo = _texto(item, "motivo", erros, "fora_da_agenda", i, limite=MAX_CURTO)
        horas = {}
        for campo in ("inicio", "fim"):
            h = _texto(item, campo, erros, "fora_da_agenda", i, obrigatorio=(campo == "inicio"), limite=5)
            if h and not _RE_HORA.match(h):
                erros.add("fora_da_agenda", i, f"`{campo}` {h!r} invalido; use HH:MM.")
                h = None
            horas[campo] = h
        if horas["inicio"] and horas["fim"] and horas["fim"] <= horas["inicio"]:
            erros.add("fora_da_agenda", i, "`fim` precisa ser depois de `inicio`.")
        if titulo and horas["inicio"]:
            saida.append({"titulo": titulo, "inicio": horas["inicio"], "fim": horas["fim"],
                          **({"motivo": motivo} if motivo else {})})
    return saida


def _validar_avisos(valor, erros: _Erros) -> list[dict]:
    saida = []
    for i, item in _lista("avisos", valor, erros):
        tipo = _texto(item, "tipo", erros, "avisos", i, obrigatorio=True, limite=MAX_CURTO)
        if tipo and tipo not in TIPOS_AVISO:
            erros.add("avisos", i, f"`tipo` {tipo!r} invalido; use um de: {', '.join(TIPOS_AVISO)}.")
            tipo = None
        texto = _texto(item, "texto", erros, "avisos", i, obrigatorio=True)
        if tipo and texto:
            saida.append({"tipo": tipo, "texto": texto})
    return saida


_VALIDADORES = {
    "hoje": _validar_hoje,
    "decidir": _validar_decidir,
    "eu_faco": _validar_eu_faco,
    "preparo": _validar_preparo,
    "fora_da_agenda": _validar_fora_da_agenda,
    "avisos": _validar_avisos,
}


def validar(args: dict) -> tuple[dict, list[str]]:
    """`(secoes_validadas, erros)`: so as secoes que vieram, ja saneadas."""
    erros = _Erros()
    saida: dict = {}
    for secao in _SECOES_LISTA:
        if args.get(secao) is None:
            continue
        saida[secao] = _VALIDADORES[secao](args[secao], erros)
    if args.get("menores") is not None:
        menores = args["menores"]
        if isinstance(menores, bool) or not isinstance(menores, int) or menores < 0:
            erros.add("menores", None, "precisa ser um inteiro >= 0.")
        else:
            saida["menores"] = menores
    return saida, list(erros)


# ---------------------------------------------------------------------------
# Merge (puro)
# ---------------------------------------------------------------------------

def _mesclar_por_id(atuais: list, novos: list[dict], *, preservar: tuple[str, ...] = (),
                    iniciais: dict | None = None) -> list[dict]:
    """Merge por `id`, mantendo a ordem de chegada.

    Item existente: herda tudo e recebe por cima os campos de `novos`, menos os
    de `preservar` (que so quem resolve pode mudar). Item novo: nasce com
    `iniciais`. O que nao veio fica como estava.
    """
    saida = [dict(i) for i in (atuais or []) if isinstance(i, dict)]
    indice = {str(i.get("id")): n for n, i in enumerate(saida)}
    for item in novos:
        chave = str(item["id"])
        if chave in indice:
            existente = saida[indice[chave]]
            existente.update({k: v for k, v in item.items() if k not in preservar})
        else:
            saida.append({**(iniciais or {}), **item})
            indice[chave] = len(saida) - 1
    return saida


def mesclar(atual: dict | None, secoes: dict) -> dict:
    """O documento depois de aplicar `secoes` (ja validadas) sobre `atual`."""
    doc = dict(atual or {})
    for secao in ("hoje", "preparo", "fora_da_agenda", "avisos"):
        if secao in secoes:
            doc[secao] = secoes[secao]
    if "decidir" in secoes:
        doc["decidir"] = _mesclar_por_id(
            doc.get("decidir"), secoes["decidir"],
            preservar=("status", "resolvido_em"),
            iniciais={"status": "pendente", "resolvido_em": None})
        # `ordem` ausente: a ordem de chegada manda.
        for n, item in enumerate(doc["decidir"], start=1):
            item.setdefault("ordem", n)
    if "eu_faco" in secoes:
        doc["eu_faco"] = _mesclar_por_id(
            doc.get("eu_faco"), secoes["eu_faco"], iniciais={"status": "proposto"})
    if "menores" in secoes:
        doc["menores"] = secoes["menores"]
    for secao in _SECOES_LISTA:
        doc.setdefault(secao, [])
    doc.setdefault("menores", 0)
    return doc


def aplicar_resolucao(doc: dict, item_id: str, status: str, agora_iso: str) -> tuple[dict | None, str | None]:
    """`(doc_novo, erro)`. `doc_novo` e None quando nada muda (idempotente)."""
    itens = [dict(i) for i in (doc.get("decidir") or []) if isinstance(i, dict)]
    alvo = next((i for i in itens if str(i.get("id")) == item_id), None)
    if alvo is None:
        ids = ", ".join(str(i.get("id")) for i in itens) or "(nenhum)"
        return None, f"Item {item_id!r} nao existe em decidir. Itens: {ids}."
    if status == "pendente":
        novo = {"status": "pendente", "resolvido_em": None}
    else:
        novo = {"status": status, "resolvido_em": agora_iso}
    if alvo.get("status") == novo["status"]:
        return None, None
    alvo.update(novo)
    return {**doc, "decidir": itens}, None


# ---------------------------------------------------------------------------
# Firestore
# ---------------------------------------------------------------------------

def _jsonavel(valor):
    """Timestamps do Firestore viram texto ISO na resposta das tools."""
    if isinstance(valor, dict):
        return {k: _jsonavel(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_jsonavel(v) for v in valor]
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


def _transacionar(db, ref, calcular):
    """Le `ref`, chama `calcular(dict|None)` e grava o que ele devolver.

    `calcular` devolve `(escrita|None, resposta)`. Sem transacao nao ha
    fallback para escrita simples (achado A04 do plano de autonomia): a tela
    grava o mesmo documento (botao Feito) e uma escrita desprotegida poderia
    desfazer a marca do Andre.
    """
    from firebase_admin import firestore

    if not hasattr(db, "transaction"):
        raise RuntimeError("o cliente Firestore nao oferece transacao; nada foi gravado")

    def _aplicar(snap):
        atual = snap.to_dict() if snap.exists else None
        return atual, calcular(atual)

    @firestore.transactional
    def _na_transacao(transaction):
        atual, (escrita, resposta) = _aplicar(ref.get(transaction=transaction))
        if escrita is not None:
            transaction.set(ref, escrita)
        return resposta

    return _na_transacao(db.transaction())


def registrar(db, args: dict) -> dict:
    from firebase_admin import firestore

    data = data_valida(args.get("data")) if args.get("data") else hoje_sp()
    if data is None:
        return {"erro": f"`data` {args.get('data')!r} invalida; use YYYY-MM-DD. Nada foi gravado.",
                "aplicado": False}
    secoes, erros = validar(args)
    if erros:
        return {"erro": "Briefing recusado, nada foi gravado: " + " | ".join(erros), "aplicado": False}
    if not secoes:
        return {"erro": "Nada para gravar: envie ao menos uma de "
                        f"{', '.join(SECOES)}. Nada foi gravado.", "aplicado": False}

    ref = db.collection(COLECAO).document(data)

    def _calcular(atual):
        doc = mesclar(atual, secoes)
        doc["data"] = data
        doc["atualizado_em"] = firestore.SERVER_TIMESTAMP
        doc["gerado_em"] = (atual or {}).get("gerado_em") or firestore.SERVER_TIMESTAMP
        return doc, {"criado": atual is None}

    try:
        info = _transacionar(db, ref, _calcular)
    except Exception as exc:
        return {"erro": f"Falha ao gravar o briefing de {data}: {exc}. "
                        "Confira com obter_briefing_dia antes de repetir.", "aplicado": False}

    # Grava-e-relê: a resposta vem do que o banco guardou, nao do que se pediu.
    relido = ref.get()
    if not relido.exists:
        return {"erro": f"O briefing de {data} nao aparece ao reler o banco.", "aplicado": False}
    doc = _jsonavel(relido.to_dict() or {})
    return {
        "status": "completed", "aplicado": True, "data": data, "criado": info["criado"],
        "secoes_gravadas": sorted(secoes), "briefing": doc,
        "nota": "decidir/eu_faco mesclam por id; hoje, preparo, fora_da_agenda e avisos substituem "
                "a lista anterior quando enviados. Status de itens de decidir so muda por "
                "resolver_item_briefing.",
    }


def obter(db, args: dict) -> dict:
    data = data_valida(args.get("data")) if args.get("data") else hoje_sp()
    if data is None:
        return {"erro": f"`data` {args.get('data')!r} invalida; use YYYY-MM-DD."}
    snap = db.collection(COLECAO).document(data).get()
    if not snap.exists:
        return {"data": data, "existe": False,
                "observacao": "Sem briefing gravado para este dia: o agente ainda nao rodou "
                              "registrar_briefing_dia (ou o briefing nao saiu)."}
    doc = _jsonavel(snap.to_dict() or {})
    pendentes = sum(1 for i in doc.get("decidir") or [] if i.get("status", "pendente") == "pendente")
    return {"data": data, "existe": True, "briefing": doc, "decidir_pendentes": pendentes}


def resolver_item(db, args: dict) -> dict:
    from firebase_admin import firestore

    data = data_valida(args.get("data")) if args.get("data") else hoje_sp()
    if data is None:
        return {"erro": f"`data` {args.get('data')!r} invalida; use YYYY-MM-DD.", "aplicado": False}
    item_id = str(args.get("id") or "").strip()
    if not item_id:
        return {"erro": "Informe `id` (o id do item em decidir, visivel em obter_briefing_dia).",
                "aplicado": False}
    status = str(args.get("status") or "").strip().lower()
    if status not in STATUS_RESOLVER:
        return {"erro": f"`status` {args.get('status')!r} invalido; use um de: {', '.join(STATUS_RESOLVER)}.",
                "aplicado": False}

    ref = db.collection(COLECAO).document(data)
    # Texto ISO e nao SERVER_TIMESTAMP: o Firestore nao aceita o sentinela dentro de
    # array, e a tela grava o mesmo formato ao marcar Feito.
    agora = datetime.now(timezone.utc).isoformat()

    def _calcular(atual):
        if atual is None:
            return None, {"erro": f"Nao ha briefing gravado para {data}.", "aplicado": False}
        novo, erro = aplicar_resolucao(atual, item_id, status, agora)
        if erro:
            return None, {"erro": erro, "aplicado": False}
        if novo is None:
            return None, {"status": "completed", "aplicado": False, "mudou": False, "data": data,
                          "id": item_id, "estado": status}
        novo["atualizado_em"] = firestore.SERVER_TIMESTAMP
        return novo, {"status": "completed", "aplicado": True, "mudou": True, "data": data,
                      "id": item_id, "estado": status}

    try:
        resposta = _transacionar(db, ref, _calcular)
    except Exception as exc:
        return {"erro": f"Falha ao resolver {item_id!r} em {data}: {exc}.", "aplicado": False}
    if resposta.get("aplicado"):
        relido = (ref.get().to_dict() or {})
        item = next((i for i in relido.get("decidir") or [] if str(i.get("id")) == item_id), {})
        if item.get("status") != status:
            return {"erro": f"O item {item_id!r} nao ficou {status!r} ao reler o banco.", "aplicado": False}
        resposta["resolvido_em"] = _jsonavel(item.get("resolvido_em"))
    return resposta
