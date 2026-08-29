"""Lista de compras: leitura e escrita, em uma copia so.

Ate 28/08 a mesma logica existia duas vezes — na callable `mutateShoppingList`
(`security_portals.py`, usada pela web) e no ramo `mutar_lista_compras` de
`tools/telegram_extended.py` (MCP, voz, Telegram). As duas divergiram: so a
primeira recusava renomear um item para um nome ja usado, so a segunda deixava
apagar um id inexistente devolvendo sucesso. Este modulo e a unica copia; os
dois pontos de entrada passaram a delegar para ca.

O que motivou a reescrita foi um desaparecimento silencioso. A sequencia natural
de quem troca a lista da semana era:

    clear_planning  -> {"success": true, "affected": 6}
    import_batch    -> {"success": true, "created": 3}

Duas respostas de sucesso, e a tela de compras vazia. `clear_planning` tinha
desmarcado os seis que estavam planejados e `import_batch` criava os novos com
`isPlanned` falso — item nascido assim nao aparece na tela que o usuario abre.
Nenhum dos dois retornos dava como perceber isso: `affected: 6` nao diz se
apagou ou desmarcou, e `created: 3` de cinco linhas enviadas nao diz o que
aconteceu com as outras duas.

As tres decisoes que saem dai, e que valem para os dois canais:

1. **Importar e planejar.** Quem importa uma lista esta montando as compras da
   semana, nao alimentando o cadastro. `import_batch` cria planejado por padrao
   e aceita `isPlanned` explicito para quem quiser o contrario.
2. **Nome ja existente e intencao, nao erro.** Se a chamada pede planejamento e
   o item ja existe, o certo e marcar o que existe. Recusar com "ja existe"
   obrigava um `update` — que exige id, que nao havia de onde tirar.
3. **O retorno explica o efeito.** Toda escrita devolve o que aconteceu com cada
   item e um `detalhe` em texto corrido, para o assistente repassar na hora em
   vez de mandar o usuario conferir na interface.

`consultar` fecha o ciclo: sem ela nao havia como ler o proprio efeito da
escrita nem obter os `item_id` que `update` e `delete` exigem.
"""

from __future__ import annotations

import unicodedata

COLECAO = "shopping_items"

CATEGORIA_PADRAO = "Geral"
QUANTIDADE_PADRAO = "1"
UNIDADE_PADRAO = "un"

# Firestore recusa mais de 500 escritas por commit; a folga cobre o commit final.
_LIMITE_BATCH = 400

_LIMITE_CONSULTA_PADRAO = 200

MOTIVO_JA_EXISTE = "ja_existe"
MOTIVO_DUPLICADO_NO_TEXTO = "duplicado_no_texto"
MOTIVO_NOME_VAZIO = "nome_vazio"

ACOES = ("create", "update", "delete", "import_batch", "clear_planning", "finalize")

_FILTROS = {
    "todos": "todos",
    "all": "todos",
    "planejados": "planejados",
    "planned": "planejados",
    "comprados": "comprados",
    "purchased": "comprados",
    "pendentes": "pendentes",
    "pending": "pendentes",
    "nao_planejados": "nao_planejados",
    "unplanned": "nao_planejados",
}

_CAMPOS_TEXTO = ("nome", "categoria", "quantidade", "unit")

_PADRAO_TEXTO = {
    "nome": "",
    "categoria": CATEGORIA_PADRAO,
    "quantidade": QUANTIDADE_PADRAO,
    "unit": UNIDADE_PADRAO,
}

# Aliases aceitos em cada ponto de entrada: a web manda `itemId`, o schema MCP
# manda `item_id`, e o texto de importacao chega com os dois nomes conforme o
# canal. Normalizar aqui evita que um canal leia um campo que o outro nao manda.
_ALIASES = {
    "itemId": "item_id",
    "import_text": "importText",
    "isplanned": "isPlanned",
    "ispurchased": "isPurchased",
    "unidade": "unit",
}


class ListaComprasError(Exception):
    """Erro de dominio. `code` e traduzido para HttpsError na borda web."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_name(name: str) -> str:
    """Minusculas sem acento, para comparar nome digitado com nome gravado."""
    texto = str(name or "").lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _payload(dados) -> dict:
    bruto = dict(dados or {})
    for alias, canonico in _ALIASES.items():
        if alias in bruto and canonico not in bruto:
            bruto[canonico] = bruto.pop(alias)
    return bruto


def _texto(valor, padrao: str) -> str:
    limpo = str(valor if valor is not None else "").strip()
    return limpo or padrao


def _inteiro(valor, campo: str) -> int:
    """Converte ou recusa com erro de dominio — nunca deixa vazar um ValueError.

    A borda MCP so traduz `ListaComprasError`; um ValueError cru chegaria ao
    cliente como falha da tool, sem dizer qual parametro estava errado.
    """
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ListaComprasError("invalid_argument", f"{campo} invalido: {valor!r}.")


def _ordem(valor) -> int:
    return _inteiro(valor, "Ordem")


def _resolver_flags(
    planejado: bool,
    comprado: bool,
    pediu_planejado: bool = False,
    pediu_comprado: bool = False,
) -> tuple[bool, bool]:
    """Invariante da lista: comprado implica planejado, desplanejar tira o comprado.

    Os dois `pediu_*` dizem quais flags a chamada informou de fato. Sem isso,
    tirar do planejamento um item ja comprado nao teria efeito: o "comprado"
    herdado do banco reergueria o planejamento que a chamada acabou de pedir
    para tirar. Entre um valor pedido e um valor herdado, quem manda e o pedido.
    """
    if comprado and not planejado:
        if pediu_planejado and not pediu_comprado:
            comprado = False
        else:
            planejado = True
    if not planejado:
        comprado = False
    return planejado, comprado


def _item_publico(item_id: str, dados: dict) -> dict:
    publico = {
        "item_id": item_id,
        "nome": str(dados.get("nome") or ""),
        "categoria": str(dados.get("categoria") or CATEGORIA_PADRAO),
        "quantidade": str(dados.get("quantidade") or QUANTIDADE_PADRAO),
        "unit": str(dados.get("unit") or UNIDADE_PADRAO),
        "isPlanned": bool(dados.get("isPlanned")),
        "isPurchased": bool(dados.get("isPurchased")),
    }
    if dados.get("ordem") is not None:
        publico["ordem"] = dados.get("ordem")
    return publico


def _todos(db) -> list[tuple[str, dict, object]]:
    """(item_id, dados, ref) de cada item do cadastro."""
    return [
        (snap.id, snap.to_dict() or {}, snap.reference)
        for snap in db.collection(COLECAO).stream()
    ]


def _achar_por_nome(db, nome: str, ignorar_id: str = ""):
    alvo = normalize_name(nome)
    for item_id, dados, ref in _todos(db):
        if item_id == ignorar_id:
            continue
        if normalize_name(str(dados.get("nome") or "")) == alvo:
            return item_id, dados, ref
    return None


def _ref(db, item_id: str):
    ref = db.collection(COLECAO).document(str(item_id))
    snap = ref.get()
    if not snap.exists:
        raise ListaComprasError("not_found", "Item nao encontrado.")
    return ref, (snap.to_dict() or {})


def _exigir_id(item_id: str) -> str:
    limpo = str(item_id or "").strip()
    if not limpo:
        raise ListaComprasError(
            "invalid_argument",
            "item_id e obrigatorio. Use consultar_lista_compras para obter o id do item.",
        )
    return limpo


class _Lote:
    """Batch que corta sozinho no limite de escritas do Firestore."""

    def __init__(self, db):
        self._db = db
        self._batch = db.batch()
        self._pendentes = 0

    def set(self, ref, dados):
        self._batch.set(ref, dados)
        self._contar()

    def update(self, ref, dados):
        self._batch.update(ref, dados)
        self._contar()

    def _contar(self):
        self._pendentes += 1
        if self._pendentes >= _LIMITE_BATCH:
            self.commit()

    def commit(self):
        if self._pendentes:
            self._batch.commit()
            self._batch = self._db.batch()
            self._pendentes = 0


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

def consultar(db, filtro=None, busca=None, limite=None) -> dict:
    """Devolve os itens com seus `item_id`, mais a contagem da lista inteira.

    As contagens do topo (`total`, `planejados`, `comprados`) descrevem sempre a
    lista toda, nao a fatia filtrada — senao um filtro faria parecer que os
    outros itens sumiram, que e exatamente o susto que este modulo existe para
    nao repetir.
    """
    escolhido = _FILTROS.get(str(filtro or "todos").strip().lower())
    if escolhido is None:
        raise ListaComprasError(
            "invalid_argument",
            "Filtro invalido. Use: todos, planejados, comprados, pendentes ou nao_planejados.",
        )

    itens = [_item_publico(item_id, dados) for item_id, dados, _ in _todos(db)]
    total = len(itens)
    planejados = sum(1 for i in itens if i["isPlanned"])
    comprados = sum(1 for i in itens if i["isPurchased"])

    if escolhido == "planejados":
        itens = [i for i in itens if i["isPlanned"]]
    elif escolhido == "comprados":
        itens = [i for i in itens if i["isPurchased"]]
    elif escolhido == "pendentes":
        itens = [i for i in itens if i["isPlanned"] and not i["isPurchased"]]
    elif escolhido == "nao_planejados":
        itens = [i for i in itens if not i["isPlanned"]]

    termo = normalize_name(busca or "")
    if termo:
        itens = [
            i for i in itens
            if termo in normalize_name(i["nome"]) or termo in normalize_name(i["categoria"])
        ]

    # Mesma ordem da tela de cadastro, para o que o assistente le bater com o
    # que o usuario ve.
    itens.sort(key=lambda i: (normalize_name(i["categoria"]), normalize_name(i["nome"])))

    encontrados = len(itens)
    teto = _LIMITE_CONSULTA_PADRAO if limite is None else max(1, _inteiro(limite, "Limite"))
    truncado = encontrados > teto
    itens = itens[:teto]

    resposta = {
        "total": total,
        "planejados": planejados,
        "comprados": comprados,
        "filtro": escolhido,
        "encontrados": encontrados,
        "retornados": len(itens),
        "itens": itens,
    }
    if truncado:
        resposta["truncado"] = True
    return resposta


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------

def criar(db, dados) -> dict:
    """Cria o item — ou, se o nome ja existe, aplica ali o que foi pedido.

    Nome repetido nao e erro: e a mesma intencao chegando de novo. Recusar
    obrigava um `update`, que exige um id que quem chamou nao tinha.
    """
    entrada = _payload(dados)
    nome = str(entrada.get("nome") or "").strip()
    if not nome:
        raise ListaComprasError("invalid_argument", "Nome do item e obrigatorio.")

    existente = _achar_por_nome(db, nome)
    if existente:
        item_id, atual, ref = existente
        updates = _updates_informados(entrada, atual, incluir_nome=False)
        if updates:
            ref.update(updates)
        final = {**atual, **updates}
        return {
            "success": True,
            "id": item_id,
            "ja_existia": True,
            "criado": False,
            "atualizado": sorted(updates),
            "item": _item_publico(item_id, final),
            "detalhe": _detalhe_criar_existente(nome, updates, final),
        }

    planejado, comprado = _resolver_flags(
        bool(entrada.get("isPlanned")), bool(entrada.get("isPurchased"))
    )
    payload = {
        "nome": nome,
        "categoria": _texto(entrada.get("categoria"), CATEGORIA_PADRAO),
        "quantidade": _texto(entrada.get("quantidade"), QUANTIDADE_PADRAO),
        "unit": _texto(entrada.get("unit"), UNIDADE_PADRAO),
        "isPlanned": planejado,
        "isPurchased": comprado,
    }
    if entrada.get("ordem") is not None:
        payload["ordem"] = _ordem(entrada.get("ordem"))

    ref = db.collection(COLECAO).document()
    ref.set(payload)
    return {
        "success": True,
        "id": ref.id,
        "ja_existia": False,
        "criado": True,
        "item": _item_publico(ref.id, payload),
        "detalhe": (
            f'"{nome}" criado e ja planejado.' if planejado
            else f'"{nome}" criado no cadastro, sem planejamento — nao aparece na tela de compras.'
        ),
    }


def _detalhe_criar_existente(nome: str, updates: dict, final: dict) -> str:
    if not updates:
        estado = "planejado" if final.get("isPlanned") else "so no cadastro, sem planejamento"
        return f'"{nome}" ja existia e nada mudou: continua {estado}.'
    if updates.get("isPlanned"):
        return f'"{nome}" ja existia e foi marcado como planejado.'
    return f'"{nome}" ja existia; atualizei {", ".join(sorted(updates))}.'


def _updates_informados(entrada: dict, atual: dict, incluir_nome: bool) -> dict:
    """Monta o update so com o que a chamada informou de fato.

    A diferenca entre "campo ausente" e "campo com valor padrao" importa: uma
    criacao que caisse em cima de um item existente aplicando `quantidade: "1"`
    por omissao apagaria a quantidade que o usuario tinha ajustado na tela.
    """
    updates: dict = {}
    campos = _CAMPOS_TEXTO if incluir_nome else _CAMPOS_TEXTO[1:]
    for campo in campos:
        if campo in entrada:
            valor = _texto(entrada.get(campo), _PADRAO_TEXTO[campo])
            if campo == "nome" and not valor:
                raise ListaComprasError("invalid_argument", "Nome invalido.")
            if valor != atual.get(campo):
                updates[campo] = valor
    if "ordem" in entrada and entrada.get("ordem") is not None:
        ordem = _ordem(entrada.get("ordem"))
        if ordem != atual.get("ordem"):
            updates["ordem"] = ordem
    pediu_planejado = "isPlanned" in entrada
    pediu_comprado = "isPurchased" in entrada
    if pediu_planejado or pediu_comprado:
        planejado, comprado = _resolver_flags(
            bool(entrada["isPlanned"]) if pediu_planejado else bool(atual.get("isPlanned")),
            bool(entrada["isPurchased"]) if pediu_comprado else bool(atual.get("isPurchased")),
            pediu_planejado=pediu_planejado,
            pediu_comprado=pediu_comprado,
        )
        if planejado != bool(atual.get("isPlanned")):
            updates["isPlanned"] = planejado
        if comprado != bool(atual.get("isPurchased")):
            updates["isPurchased"] = comprado
    return updates


def atualizar(db, item_id, dados) -> dict:
    entrada = _payload(dados)
    alvo = _exigir_id(item_id)
    ref, atual = _ref(db, alvo)

    if "nome" in entrada:
        novo_nome = str(entrada.get("nome") or "").strip()
        if not novo_nome:
            raise ListaComprasError("invalid_argument", "Nome invalido.")
        conflito = _achar_por_nome(db, novo_nome, ignorar_id=alvo)
        if conflito:
            raise ListaComprasError(
                "already_exists",
                f'Ja existe outro item chamado "{conflito[1].get("nome")}" (item_id {conflito[0]}).',
            )

    updates = _updates_informados(entrada, atual, incluir_nome=True)
    if not updates:
        campos_validos = set(_CAMPOS_TEXTO) | {"ordem", "isPlanned", "isPurchased"}
        if not campos_validos & set(entrada):
            raise ListaComprasError("invalid_argument", "Nenhum campo valido para atualizar.")
        return {
            "success": True,
            "id": alvo,
            "atualizado": [],
            "item": _item_publico(alvo, atual),
            "detalhe": "Nada a mudar: os valores enviados ja eram os gravados.",
        }

    ref.update(updates)
    final = {**atual, **updates}
    return {
        "success": True,
        "id": alvo,
        "atualizado": sorted(updates),
        "item": _item_publico(alvo, final),
        "detalhe": f'"{final.get("nome")}": atualizei {", ".join(sorted(updates))}.',
    }


def remover(db, item_id) -> dict:
    alvo = _exigir_id(item_id)
    ref, atual = _ref(db, alvo)
    ref.delete()
    return {
        "success": True,
        "id": alvo,
        "removido": _item_publico(alvo, atual),
        "detalhe": f'"{atual.get("nome")}" excluido do cadastro.',
    }


def _parse_linhas(texto: str) -> list[tuple[str, str, str]]:
    """Cada linha vira (linha_original, nome, categoria). Linha vazia some."""
    saida = []
    for linha in str(texto or "").splitlines():
        limpa = linha.strip()
        if not limpa:
            continue
        if "|" in limpa:
            nome, categoria = [parte.strip() for parte in limpa.split("|", 1)]
        else:
            nome, categoria = limpa, ""
        saida.append((limpa, nome, categoria or CATEGORIA_PADRAO))
    return saida


def importar_lote(db, texto, is_planned=True) -> dict:
    """Importa uma lista de itens, por padrao ja planejados.

    Nome que ja existe nao e descartado em silencio: o item existente entra no
    planejamento e aparece em `ignorados` com o motivo e o `item_id`. E o que
    faz a sequencia `clear_planning` + `import_batch` devolver a lista inteira
    para a tela, em vez de so a parte que era nova.
    """
    linhas = _parse_linhas(texto)
    if not str(texto or "").strip():
        raise ListaComprasError("invalid_argument", "Texto de importacao e obrigatorio.")

    existentes = {
        normalize_name(str(dados.get("nome") or "")): (item_id, dados, ref)
        for item_id, dados, ref in _todos(db)
    }

    lote = _Lote(db)
    criados: list[str] = []
    ignorados: list[dict] = []
    vistos: set[str] = set()
    planejados_agora = 0

    for linha, nome, categoria in linhas:
        if not nome:
            ignorados.append({"nome": linha, "motivo": MOTIVO_NOME_VAZIO})
            continue

        chave = normalize_name(nome)
        if chave in vistos:
            ignorados.append({"nome": nome, "motivo": MOTIVO_DUPLICADO_NO_TEXTO})
            continue
        vistos.add(chave)

        anterior = existentes.get(chave)
        if anterior:
            item_id, dados, ref = anterior
            ja_planejado = bool(dados.get("isPlanned"))
            planejado = ja_planejado or bool(is_planned)
            if planejado and not ja_planejado:
                lote.update(ref, {"isPlanned": True})
            if planejado:
                planejados_agora += 1
            ignorados.append({
                "nome": dados.get("nome") or nome,
                "motivo": MOTIVO_JA_EXISTE,
                "item_id": item_id,
                "planejado": planejado,
            })
            continue

        ref = db.collection(COLECAO).document()
        lote.set(ref, {
            "nome": nome,
            "categoria": categoria,
            "quantidade": QUANTIDADE_PADRAO,
            "unit": UNIDADE_PADRAO,
            "isPlanned": bool(is_planned),
            "isPurchased": False,
        })
        criados.append(nome)
        if is_planned:
            planejados_agora += 1

    lote.commit()

    return {
        "success": True,
        "created": criados,
        "total_criados": len(criados),
        "ignorados": ignorados,
        "total_ignorados": len(ignorados),
        "planejados": planejados_agora,
        "isPlanned": bool(is_planned),
        "detalhe": _detalhe_importacao(criados, ignorados, planejados_agora, bool(is_planned)),
    }


def _detalhe_importacao(criados, ignorados, planejados, is_planned) -> str:
    partes = [f"{len(criados)} item(ns) criado(s)"]
    ja_existiam = [i for i in ignorados if i["motivo"] == MOTIVO_JA_EXISTE]
    if ja_existiam:
        nomes = ", ".join(str(i["nome"]) for i in ja_existiam)
        marcados = " e foi(ram) marcado(s) como planejado(s)" if is_planned else ""
        partes.append(f"{len(ja_existiam)} ja estava(m) na lista ({nomes}){marcados}")
    duplicados = [i for i in ignorados if i["motivo"] == MOTIVO_DUPLICADO_NO_TEXTO]
    if duplicados:
        partes.append(f"{len(duplicados)} repetido(s) no proprio texto")
    vazios = [i for i in ignorados if i["motivo"] == MOTIVO_NOME_VAZIO]
    if vazios:
        partes.append(f"{len(vazios)} linha(s) sem nome")
    fecho = (
        f"{planejados} item(ns) desta importacao estao planejados e aparecem na tela de compras."
        if is_planned
        else "Nada foi planejado: os itens entraram so no cadastro e nao aparecem na tela de compras."
    )
    return "; ".join(partes) + ". " + fecho


def limpar_planejamento(db, acao="clear_planning") -> dict:
    """Desmarca o planejamento da rodada. Nao exclui nada — e o que o retorno diz.

    `{"affected": 6}` sozinho nao distinguia "apagou seis" de "desmarcou seis".
    """
    itens = _todos(db)
    lote = _Lote(db)
    desmarcados = []
    for item_id, dados, ref in itens:
        if dados.get("isPlanned") or dados.get("isPurchased"):
            lote.update(ref, {"isPlanned": False, "isPurchased": False})
            desmarcados.append({"item_id": item_id, "nome": dados.get("nome") or ""})
    lote.commit()

    restantes = len(itens)
    verbo = "Rodada finalizada" if acao == "finalize" else "Planejamento limpo"
    return {
        "success": True,
        # `affected` fica por compatibilidade com quem ja lia esse campo.
        "affected": len(desmarcados),
        "desmarcados": len(desmarcados),
        "excluidos": 0,
        "itens_desmarcados": desmarcados,
        "itens_no_catalogo": restantes,
        "sem_planejamento": restantes,
        "detalhe": (
            f"{verbo}: {len(desmarcados)} item(ns) deixaram de estar planejados. "
            f"Nenhum item foi excluido — o cadastro segue com {restantes} item(ns), "
            "todos agora sem planejamento."
        ),
    }


def mutar(db, action, dados) -> dict:
    """Ponto unico de entrada de escrita, compartilhado pela web e pelo MCP."""
    entrada = _payload(dados)
    acao = str(action or "").strip()
    if acao not in ACOES:
        raise ListaComprasError(
            "invalid_argument", f"Acao invalida. Use: {', '.join(ACOES)}."
        )

    if acao == "create":
        return criar(db, entrada)
    if acao == "update":
        return atualizar(db, entrada.get("item_id"), entrada)
    if acao == "delete":
        return remover(db, entrada.get("item_id"))
    if acao == "import_batch":
        # Importar e planejar: quem manda a lista da semana quer ve-la na tela.
        is_planned = entrada.get("isPlanned")
        return importar_lote(
            db,
            entrada.get("importText"),
            is_planned=True if is_planned is None else bool(is_planned),
        )
    return limpar_planejamento(db, acao=acao)
