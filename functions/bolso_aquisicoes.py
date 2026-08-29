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


def bolso(settings: dict, contas_do_mes) -> float:
    """Quanto ha disponivel para aquisicoes.

    E a reserva de investimento mais — SO se a reserva de emergencia ja estiver
    completa — o que foi efetivamente poupado no mes. A condicao existe porque
    poupanca do mes com emergencia incompleta esta indo para a emergencia, e nao
    para desejo de compra.
    """
    emergencia_atual = float(settings.get("emergencyReserveCurrent") or 0)
    emergencia_alvo = float(settings.get("emergencyReserveTarget") or 0)
    poupado = sum(
        float(c.get("amount") or 0) for c in (contas_do_mes or [])
        if c.get("category") == CATEGORIA_POUPANCA and c.get("isPaid")
    )
    investimento = float(settings.get("investmentReserveCurrent") or 0)
    return investimento + (poupado if emergencia_atual >= emergencia_alvo else 0.0)


def cobertura(meta: dict, disponivel: float) -> float:
    """Quanto do bolso este item consome se for comprado sozinho.

    Meta concluida nao recalcula: o valor gravado nela e o que ela custou de
    fato quando foi fechada, e nao uma projecao do bolso de hoje.
    """
    if str(meta.get("status") or "") == "completed":
        return float(meta.get("currentAmount") or 0)
    alvo = float(meta.get("targetAmount") or 0)
    return min(alvo, disponivel) if alvo > 0 else 0.0


def _prioridade(meta: dict) -> float:
    try:
        return float(meta.get("priority"))
    except (TypeError, ValueError):
        return 99.0


def cobertura_da_fila(metas, disponivel: float) -> dict:
    """Ate onde o bolso alcanca quando os itens sao comprados EM ORDEM.

    A cobertura individual responde "da para comprar este?". Esta responde "da
    para comprar este JUNTO com os que vem antes dele?" — e e a pergunta que o
    usuario faz de fato quando olha varios selos de 100% ao mesmo tempo.

    Devolve `{task_id -> cabe_na_fila}` mais quantos itens cabem, na ordem de
    `priority` (que ate agora nao tinha efeito nenhum sobre nada).
    """
    ativas = [m for m in (metas or []) if str(m.get("status") or "") != "completed"]
    ativas.sort(key=_prioridade)

    cabe, acumulado, quantos = {}, 0.0, 0
    for meta in ativas:
        alvo = float(meta.get("targetAmount") or 0)
        if alvo <= 0:
            cabe[str(meta.get("id"))] = False
            continue
        acumulado += alvo
        entra = acumulado <= disponivel
        cabe[str(meta.get("id"))] = entra
        if entra:
            quantos += 1
    return {"cabe_na_fila": cabe, "itens_que_cabem": quantos}


def resumo(metas, settings: dict, contas_do_mes) -> dict:
    """O bolso, a cobertura de cada meta e a leitura da fila, de uma vez."""
    disponivel = bolso(settings, contas_do_mes)
    fila = cobertura_da_fila(metas, disponivel)
    enriquecidas = []
    for meta in (metas or []):
        atual = cobertura(meta, disponivel)
        alvo = float(meta.get("targetAmount") or 0)
        enriquecidas.append({
            **meta,
            # Calculado na leitura, e nao lido do documento: o campo gravado
            # ficava defasado porque so era atualizado quando a meta era editada.
            "currentAmount": round(atual, 2),
            "cobertura_pct": round(min(100.0, atual / alvo * 100), 1) if alvo > 0 else 0.0,
            "cabe_na_fila": fila["cabe_na_fila"].get(str(meta.get("id")), False),
        })
    return {
        "bolso_aquisicoes": round(disponivel, 2),
        "itens_que_cabem_no_bolso": fila["itens_que_cabem"],
        "metas": enriquecidas,
    }
