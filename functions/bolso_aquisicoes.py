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

CATEGORIA_POUPANCA = "Poupança"


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
    """
    import math

    return int(math.floor(float(valor or 0) * 100 + 0.5))


def _uma_casa(valor: float) -> float:
    """Uma casa decimal, meio-para-cima — como o JavaScript, e nao como o Python."""
    import math

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
        return float(meta.get("currentAmount") or 0)
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
    try:
        prioridade = float(meta.get("priority"))
    except (TypeError, ValueError):
        prioridade = 99.0
    return (prioridade, str(meta.get("id") or ""))


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
        alvo = float(meta.get("targetAmount") or 0)
        enriquecidas.append({
            **meta,
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
