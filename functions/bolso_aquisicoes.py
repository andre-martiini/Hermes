"""O bolso de aquisicoes e a cobertura de cada desejo de compra.

Modulo puro: sem Firestore, sem `firebase_functions`. Existe porque a mesma
regra precisa valer em dois lugares que nao podem compartilhar codigo — a tela
(TypeScript, `src/utils/bolsoAquisicoes.ts`) e o MCP (Python, aqui). Foi
justamente essa duplicacao implicita que produziu o defeito: a tela calculava
certo e o MCP devolvia um valor gravado e defasado.

**Os dois arquivos tem de andar juntos.** Qualquer mudanca de regra aqui exige a
mesma mudanca la, e os testes dos dois lados usam a MESMA fixture de propriedade
— se as respostas divergirem, um dos dois quebra.

## O modelo, que e deliberado e nao deve ser "corrigido"

O usuario NAO pre-aloca dinheiro por desejo. Ha um bolso unico, e ele escolhe o
que comprar no momento em que da. Entao a cobertura de cada item e individual —
"se eu so comprasse este, daria?" — e NAO uma fatia reservada.

A consequencia incomoda e que as coberturas **nao sao somaveis**: dois itens de
R$ 2.000 podem aparecer os dois como 100% cobertos com um bolso de R$ 3.870,97, e
comprar os dois nao da. Isso nao e defeito do modelo; e informacao que a
interface precisa dar, e por isso `cobertura_da_fila` existe.
"""

import math
import re

CATEGORIA_POUPANCA = "Poupança"

# A gramatica decimal que os dois lados aceitam, escrita uma vez e identica em
# `src/utils/bolsoAquisicoes.ts`. Nao e a sintaxe numerica do Python nem a do
# JavaScript: e a interseccao delas, deliberadamente.
#
# `[0-9]` e nao `\d`: em padrao de `str` o `\d` do Python casa digito decimal
# UNICODE, e `float("\u0661")` devolve 1.0 — enquanto o `\d` do ECMAScript e so
# ASCII e o mesmo texto cairia no padrao do outro lado. A mesma divergencia,
# entrando por dentro da regex que existe para elimina-la.
_DECIMAL = re.compile(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$")

# O espaco ao redor tambem tem de ser explicito, e nao delegado ao `strip()` de
# cada linguagem: os dois conjuntos NAO coincidem, e divergem nos DOIS sentidos.
# `str.strip()` do Python remove U+0085 e U+001C..U+001F, que o `trim()` do
# ECMAScript nao remove; o `trim()` remove U+FEFF, que o Python nao remove. Com
# " \u00851" o Python leria 1 e a tela leria 0. Este e o conjunto que os dois
# concordam, escrito uma vez.
_ESPACO = " \t\n\r\f\v"

# Teto do que vira centavo. Acima de 2**53-1 centavos o inteiro exato do Python e
# o double do JavaScript param de coincidir, e antes disso `1e307 * 100` estoura
# para infinito — onde `math.floor` LEVANTA e o `Math.floor` devolve Infinity em
# silencio. Sao ~90 trilhoes de reais: nenhum valor real chega perto, e o que
# chegar nao e dinheiro, e sim dado corrompido.
_MAX_CENTAVOS = 9007199254740991


def numero(valor, padrao: float = 0.0) -> float:
    """O que o Firestore devolveu, lido como numero por UMA gramatica so.

    Existe porque `float()` e `Number()` aceitam conjuntos DIFERENTES de texto,
    e o Firestore nao tipa o que grava — este modulo ja encontrou valor
    monetario guardado como string mais de uma vez. Confiar na coercao nativa de
    cada linguagem e ter duas regras achando que sao uma:

    - `float("1_0")` da 10 e `Number("1_0")` da NaN.
    - `Number("0x1")` da 1 e `float("0x1")` levanta.
    - `float("NaN")` e `float("Infinity")` passam, e ai `math.floor` levanta e
      derruba a tool inteira; do outro lado o NaN se propaga em silencio e
      corrompe o cofre exibido.
    - `float("abc")` levanta sem ninguem pegar, o que hoje derruba
      `consultar_financas_v2` com uma conta mal gravada.

    Entao nem `float()` nem `Number()` decidem: a gramatica decide, e o que nao
    casar com ela vira `padrao` nos dois lados. Zero para dinheiro, 99 para
    prioridade.

    `bool` e recusado de proposito: em Python ele e subclasse de `int` e
    `float(True)` da 1.0, enquanto no TypeScript `typeof true` nao e `'number'`.
    Aceitar levaria os dois lados a discordar de novo.
    """
    if isinstance(valor, bool):
        return padrao
    if isinstance(valor, (int, float)):
        return float(valor) if math.isfinite(valor) else padrao
    if isinstance(valor, str) and _DECIMAL.match(valor.strip(_ESPACO)):
        convertido = float(valor.strip(_ESPACO))
        # `float("1e400")` da inf sem levantar.
        return convertido if math.isfinite(convertido) else padrao
    return padrao


def centavos(valor) -> int:
    """Reais para centavos inteiros, com meio-para-cima.

    Duas razoes, e as duas ja morderam:

    - Dinheiro em float compara errado na fronteira. Reserva 0,10 mais poupanca
      0,70 da 0.7999999999999999, e uma meta de 0,80 aparece como 100% coberta e
      ao mesmo tempo "nao cabe". Acumular e comparar em centavos inteiros elimina
      a classe toda.
    - `round` do Python arredonda meio-para-PAR e o do JavaScript arredonda
      meio-para-cima. Como a regra vive nas duas linguagens, a mesma entrada
      daria numeros diferentes nos dois lados — exatamente a divergencia que
      este modulo existe para eliminar. Entao o arredondamento e explicito e
      igual dos dois lados, e nao o padrao de cada linguagem.

    A leitura do valor passa por `numero`, e nao por `float()` direto: sem isso
    uma conta gravada como "abc" ou "NaN" levantava aqui e derrubava a tool.

    O teto tem de ser conferido ANTES da multiplicacao: "1e307" e finito e passa
    pela gramatica, mas `1e307 * 100` estoura para infinito, e ai `math.floor`
    levanta `OverflowError` e derruba a tool — enquanto o `Math.floor` do outro
    lado devolve Infinity e contamina o cofre em silencio.
    """
    reais = numero(valor)
    if abs(reais) * 100 > _MAX_CENTAVOS:
        return 0
    return int(math.floor(reais * 100 + 0.5))


def _uma_casa(valor: float) -> float:
    """Uma casa decimal, meio-para-cima — como o JavaScript, e nao como o Python."""
    return math.floor(valor * 10 + 0.5) / 10


def bolso(settings: dict, contas_do_mes) -> float:
    """Quanto ha disponivel para aquisicoes.

    E a reserva de investimento mais — SO se a reserva de emergencia ja estiver
    completa — o que foi efetivamente poupado no mes. A condicao existe porque
    poupanca do mes com emergencia incompleta esta indo para a emergencia, e nao
    para desejo de compra.
    """
    emergencia_atual = centavos(settings.get("emergencyReserveCurrent"))
    emergencia_alvo = centavos(settings.get("emergencyReserveTarget"))
    poupado = sum(
        centavos(c.get("amount")) for c in (contas_do_mes or [])
        if c.get("category") == CATEGORIA_POUPANCA and c.get("isPaid")
    )
    investimento = centavos(settings.get("investmentReserveCurrent"))
    return (investimento + (poupado if emergencia_atual >= emergencia_alvo else 0)) / 100


def cobertura(meta: dict, disponivel: float) -> float:
    """Quanto do bolso este item consome se for comprado sozinho.

    Meta concluida nao recalcula: o valor gravado nela e o que ela custou de
    fato quando foi fechada, e nao uma projecao do bolso de hoje.
    """
    if str(meta.get("status") or "") == "completed":
        return numero(meta.get("currentAmount"))
    alvo = centavos(meta.get("targetAmount"))
    return min(alvo, centavos(disponivel)) / 100 if alvo > 0 else 0.0


def _ordem(meta: dict) -> tuple:
    """Prioridade, com o id como desempate — e o desempate por ORDINAL.

    O desempate nao e capricho. Sem ele, duas metas de mesma `priority` ficam na
    ordem de ENTRADA da lista — e os dois lados recebem a lista de fontes
    diferentes (o MCP monta do Firestore, a tela do snapshot). Com o bolso
    cobrindo so uma das duas, cada lado diria que uma diferente cabe: a mesma
    divergencia entre linguagens que este modulo existe para eliminar, entrando
    por uma porta que a fixture nao olhava.

    A comparacao de string do Python e por ordinal, e o lado TypeScript precisa
    usar `<`/`>` e NAO `localeCompare` — que usa collation de locale e poe `'a'`
    antes de `'B'`, enquanto aqui `'B'` (66) vem antes de `'a'` (97). Id do
    Firestore mistura maiuscula e minuscula, entao o caso e alcancavel; foi
    exatamente assim que o desempate reintroduziu a divergencia que ele veio
    fechar. Ver `compararMetas` em `src/utils/bolsoAquisicoes.ts`.
    """
    return (numero(meta.get("priority"), 99.0), str(meta.get("id") or ""))


def cobertura_da_fila(metas, disponivel: float) -> dict:
    """Ate onde o bolso alcanca quando os itens sao comprados EM ORDEM.

    A cobertura individual responde "da para comprar este?". Esta responde "da
    para comprar este JUNTO com os que vem antes dele?" — e e a pergunta que o
    usuario faz de fato quando olha varios selos de 100% ao mesmo tempo.

    Devolve `{task_id -> cabe_na_fila}` mais quantos itens cabem, na ordem de
    `priority` (que ate agora nao tinha efeito nenhum sobre nada).
    """
    ativas = [m for m in (metas or []) if str(m.get("status") or "") != "completed"]
    ativas.sort(key=_ordem)

    # Em centavos inteiros: somar floats e comparar com o bolso erra na fronteira
    # exata, marcando como "nao cabe" um item que cabe por zero.
    teto = centavos(disponivel)
    cabe, acumulado, quantos = {}, 0, 0
    for meta in ativas:
        alvo = centavos(meta.get("targetAmount"))
        if alvo <= 0:
            cabe[str(meta.get("id"))] = False
            continue
        acumulado += alvo
        entra = acumulado <= teto
        cabe[str(meta.get("id"))] = entra
        if entra:
            quantos += 1
    return {"cabe_na_fila": cabe, "itens_que_cabem": quantos}


def resumo(metas, settings: dict, contas_do_mes) -> dict:
    """O bolso, a cobertura de cada meta e a leitura da fila, de uma vez."""
    disponivel = bolso(settings, contas_do_mes)
    fila = cobertura_da_fila(metas, disponivel)
    # Ordenadas aqui, e nao por quem consome. A tela repetia este `sort` por fora
    # e foi assim que o `localeCompare` entrou: a ordem exibida podia divergir da
    # ordem em que a fila foi avaliada. Uma ordenacao so, e a mesma dos dois lados.
    enriquecidas = []
    for meta in sorted(metas or [], key=_ordem):
        atual = cobertura(meta, disponivel)
        alvo = numero(meta.get("targetAmount"))
        enriquecidas.append({
            **meta,
            # Normalizado na saida, junto com `currentAmount`. Quem le a tool
            # formata este campo — `main.py` faz `f"{...:.2f}"`, que LEVANTA com
            # uma string — e nao tem por que repetir a gramatica para descobrir
            # se o Firestore guardou "8000" ou 8000.
            "targetAmount": alvo,
            # Calculado na leitura, e nao lido do documento: o campo gravado
            # ficava defasado porque so era atualizado quando a meta era editada.
            "currentAmount": centavos(atual) / 100,
            "cobertura_pct": _uma_casa(min(100.0, atual / alvo * 100)) if alvo > 0 else 0.0,
            "cabe_na_fila": fila["cabe_na_fila"].get(str(meta.get("id")), False),
        })
    return {
        "bolso_aquisicoes": centavos(disponivel) / 100,
        "itens_que_cabem_no_bolso": fila["itens_que_cabem"],
        "metas": enriquecidas,
    }
